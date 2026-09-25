"""Deterministic dense retrieval over canonical ingested SEC chunks.

The frozen ``embedding_v0.1`` baseline uses one pinned BGE encoder for both
queries and passages, CLS pooling, float32 L2-normalized vectors, and cosine
similarity implemented as a dot product.  No query instruction, text rewrite,
secondary chunking, or benchmark-specific metadata is used.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol, Sequence

import numpy as np


EMBEDDING_IMPLEMENTATION = "thesisagent_dense_embedding"
EMBEDDING_IMPLEMENTATION_VERSION = "1"
DEFAULT_MODEL_ID = "BAAI/bge-base-en-v1.5"
DEFAULT_MODEL_REVISION = "a5beb1e3e68b9ab74eb54cfd186867f64f240e1a"
DEFAULT_BATCH_SIZE = 32
DEFAULT_SEED = 0
DEFAULT_TORCH_THREADS = 4

_METADATA_FIELDS = (
    "company",
    "form",
    "filing_date",
    "period_of_report",
    "fiscal_period",
    "calendar_period",
    "source_role",
    "doc_role",
    "exhibit_number",
    "block_type",
)


def stable_json_dumps(value: Any) -> str:
    """Serialize *value* using the baseline's deterministic JSON format."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def stable_json_line(value: Any) -> str:
    """Return one deterministically serialized JSON Lines record."""
    return stable_json_dumps(value) + "\n"


def normalize_embeddings(values: np.ndarray) -> np.ndarray:
    """Return a float32, row-wise L2-normalized embedding matrix."""
    matrix = np.asarray(values, dtype=np.float32)
    if matrix.ndim == 1:
        matrix = matrix.reshape(1, -1)
    if matrix.ndim != 2:
        raise ValueError("embeddings must be a one- or two-dimensional array")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if np.any(~np.isfinite(matrix)) or np.any(~np.isfinite(norms)):
        raise ValueError("embeddings must contain only finite values")
    if np.any(norms == 0):
        raise ValueError("cannot L2-normalize a zero embedding")
    return np.ascontiguousarray(matrix / norms, dtype=np.float32)


def _framed_sha256(values: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for value in values:
        encoded = value.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def _matrix_sha256(matrix: np.ndarray) -> str:
    canonical = np.ascontiguousarray(matrix, dtype=np.float32)
    return hashlib.sha256(canonical.tobytes(order="C")).hexdigest()


class DenseEncoder(Protocol):
    """Small injectable encoder interface used by ``DenseRetriever``."""

    @property
    def config(self) -> Mapping[str, Any]: ...

    @property
    def embedding_dimension(self) -> int: ...

    @property
    def max_sequence_length(self) -> int: ...

    def encode(self, texts: Sequence[str]) -> np.ndarray: ...

    def token_lengths(self, texts: Sequence[str]) -> list[int]: ...


class TransformerDenseEncoder:
    """Pinned Hugging Face BGE encoder executed deterministically on CPU."""

    def __init__(
        self,
        *,
        model_id: str = DEFAULT_MODEL_ID,
        model_revision: str = DEFAULT_MODEL_REVISION,
        batch_size: int = DEFAULT_BATCH_SIZE,
        seed: int = DEFAULT_SEED,
        torch_threads: int = DEFAULT_TORCH_THREADS,
        cache_dir: str | Path | None = None,
        model_path: str | Path | None = None,
        local_files_only: bool = False,
    ) -> None:
        if model_id != DEFAULT_MODEL_ID:
            raise ValueError(f"embedding_v0.1 requires model_id={DEFAULT_MODEL_ID}")
        if model_revision != DEFAULT_MODEL_REVISION:
            raise ValueError(
                "embedding_v0.1 requires model_revision="
                f"{DEFAULT_MODEL_REVISION}"
            )
        if not isinstance(batch_size, int) or batch_size <= 0:
            raise ValueError("batch_size must be a positive integer")
        if not isinstance(torch_threads, int) or torch_threads <= 0:
            raise ValueError("torch_threads must be a positive integer")

        try:
            import torch
            import transformers
            from transformers import AutoModel, AutoTokenizer
        except ImportError as exc:  # pragma: no cover - exercised by deployment
            raise RuntimeError(
                "embedding_v0.1 requires compatible torch and transformers packages"
            ) from exc

        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        torch.use_deterministic_algorithms(True)
        torch.set_num_threads(torch_threads)
        interop_threads = 1
        try:
            torch.set_num_interop_threads(interop_threads)
        except RuntimeError:
            # PyTorch permits setting this only before parallel work starts.
            interop_threads = torch.get_num_interop_threads()

        model_source = model_id if model_path is None else str(Path(model_path))
        common_kwargs: dict[str, Any] = {
            "local_files_only": local_files_only,
            "trust_remote_code": False,
        }
        if model_path is None:
            common_kwargs.update(
                revision=model_revision,
                cache_dir=None if cache_dir is None else str(cache_dir),
            )
        tokenizer = AutoTokenizer.from_pretrained(model_source, **common_kwargs)
        model = AutoModel.from_pretrained(
            model_source,
            use_safetensors=True,
            **common_kwargs,
        )
        model.to("cpu")
        model.eval()

        native_max_length = int(tokenizer.model_max_length)
        if native_max_length <= 0 or native_max_length > 1_000_000:
            raise ValueError(
                f"invalid native tokenizer model_max_length: {native_max_length}"
            )
        dimension = int(model.config.hidden_size)

        backend_tokenizer = getattr(tokenizer, "backend_tokenizer", None)
        backend_serialization = (
            backend_tokenizer.to_str()
            if backend_tokenizer is not None
            else stable_json_dumps(tokenizer.get_vocab())
        )
        tokenizer_identity = {
            "class": tokenizer.__class__.__name__,
            "vocab_size": int(tokenizer.vocab_size),
            "model_max_length": native_max_length,
            "special_tokens_map": tokenizer.special_tokens_map,
            "backend_sha256": hashlib.sha256(
                backend_serialization.encode("utf-8")
            ).hexdigest(),
        }
        model_config_payload = model.config.to_dict()
        # ``transformers`` injects the load location into this otherwise
        # semantic configuration. Preserve the frozen logical model identity
        # when loading the same verified bytes from a relocated model root.
        model_config_payload["_name_or_path"] = model_id
        model_config_fingerprint = hashlib.sha256(
            stable_json_dumps(model_config_payload).encode("utf-8")
        ).hexdigest()

        self._torch = torch
        self._tokenizer = tokenizer
        self._model = model
        self._batch_size = batch_size
        self._dimension = dimension
        self._max_sequence_length = native_max_length
        self._config: dict[str, Any] = {
            "model_id": model_id,
            "model_revision": model_revision,
            "encoder": "AutoModel",
            "query_instruction": None,
            "query_and_passage_encoder": "same",
            "pooling": "cls_token_last_hidden_state",
            "embedding_dtype": "float32",
            "normalization": "l2",
            "similarity": "dot_product_over_l2_normalized_vectors",
            "device": "cpu",
            "batch_size": batch_size,
            "model_max_sequence_length": native_max_length,
            "tokenizer_truncation": True,
            "secondary_chunking": False,
            "seed": seed,
            "model_eval": not model.training,
            "torch_deterministic_algorithms": bool(
                torch.are_deterministic_algorithms_enabled()
            ),
            "torch_num_threads": int(torch.get_num_threads()),
            "torch_num_interop_threads": int(interop_threads),
            "torch_version": torch.__version__,
            "transformers_version": transformers.__version__,
            "tokenizer": tokenizer_identity,
            "model_config_fingerprint": model_config_fingerprint,
            "embedding_dimension": dimension,
        }

    @property
    def config(self) -> Mapping[str, Any]:
        return dict(self._config)

    @property
    def embedding_dimension(self) -> int:
        return self._dimension

    @property
    def max_sequence_length(self) -> int:
        return self._max_sequence_length

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self._dimension), dtype=np.float32)
        matrices: list[np.ndarray] = []
        with self._torch.inference_mode():
            for start in range(0, len(texts), self._batch_size):
                batch = list(texts[start : start + self._batch_size])
                inputs = self._tokenizer(
                    batch,
                    padding=True,
                    truncation=True,
                    max_length=self._max_sequence_length,
                    return_tensors="pt",
                )
                outputs = self._model(**inputs)
                pooled = outputs.last_hidden_state[:, 0].to(
                    dtype=self._torch.float32,
                    device="cpu",
                )
                matrices.append(pooled.numpy().copy())
        return np.ascontiguousarray(np.concatenate(matrices, axis=0), dtype=np.float32)

    def token_lengths(self, texts: Sequence[str]) -> list[int]:
        lengths: list[int] = []
        for start in range(0, len(texts), self._batch_size):
            batch = list(texts[start : start + self._batch_size])
            encoded = self._tokenizer(
                batch,
                add_special_tokens=True,
                padding=False,
                truncation=False,
                return_length=True,
            )
            batch_lengths = encoded.get("length")
            if batch_lengths is None:
                batch_lengths = [len(token_ids) for token_ids in encoded["input_ids"]]
            lengths.extend(int(length) for length in batch_lengths)
        return lengths


@dataclass(frozen=True)
class _DenseDocument:
    chunk_id: str
    doc_id: str
    accession: str
    company: str | None
    form: str | None
    filing_date: str | None
    period_of_report: str | None
    fiscal_period: str | None
    calendar_period: str | None
    source_role: str | None
    doc_role: str | None
    exhibit_number: str | None
    block_type: str | None
    section_path: tuple[str, ...]
    chunk_text: str
    retrieval_text: str

    def metadata_value(self, key: str) -> Any:
        if key == "section_path":
            return self.section_path
        if key in _METADATA_FIELDS or key in {"chunk_id", "doc_id", "accession"}:
            return getattr(self, key)
        raise ValueError(f"unsupported metadata filter: {key}")


@dataclass(frozen=True)
class DenseSearchResult:
    """One ranked dense result with canonical chunk and filing metadata."""

    rank: int
    score: float
    chunk_id: str
    doc_id: str
    accession: str
    company: str | None
    form: str | None
    filing_date: str | None
    period_of_report: str | None
    fiscal_period: str | None
    calendar_period: str | None
    source_role: str | None
    doc_role: str | None
    exhibit_number: str | None
    block_type: str | None
    section_path: tuple[str, ...]
    chunk_text: str
    retrieval_text: str

    def to_dict(self) -> dict[str, Any]:
        payload = dict(self.__dict__)
        payload["section_path"] = list(self.section_path)
        return payload


class DenseRetriever:
    """Deterministic in-memory cosine retriever with an optional local cache."""

    def __init__(
        self,
        encoder: DenseEncoder | None = None,
        *,
        cache_dir: str | Path | None = None,
        model_cache_dir: str | Path | None = None,
        model_path: str | Path | None = None,
        local_files_only: bool = False,
    ) -> None:
        self._encoder = encoder or TransformerDenseEncoder(
            cache_dir=model_cache_dir,
            model_path=model_path,
            local_files_only=local_files_only,
        )
        self._cache_dir = None if cache_dir is None else Path(cache_dir)
        self._documents: tuple[_DenseDocument, ...] = ()
        self._embeddings: np.ndarray | None = None
        self._token_lengths: tuple[int, ...] = ()
        self._index_metadata: dict[str, Any] = {}
        self._cache_status = "disabled" if cache_dir is None else "not_built"

    @property
    def config(self) -> dict[str, Any]:
        return {
            "implementation": EMBEDDING_IMPLEMENTATION,
            "implementation_version": EMBEDDING_IMPLEMENTATION_VERSION,
            **dict(self._encoder.config),
        }

    @property
    def index_metadata(self) -> dict[str, Any]:
        self._require_index()
        return dict(self._index_metadata)

    @property
    def index_fingerprint(self) -> str:
        self._require_index()
        return str(self._index_metadata["index_fingerprint"])

    @property
    def indexed_chunk_count(self) -> int:
        return len(self._documents)

    @property
    def cache_status(self) -> str:
        return self._cache_status

    @property
    def truncation_diagnostics(self) -> dict[str, int | float]:
        self._require_index()
        lengths = np.asarray(self._token_lengths, dtype=np.int64)
        maximum = self._encoder.max_sequence_length
        exceeding = int(np.count_nonzero(lengths > maximum))

        def percentile(value: float) -> float:
            if not lengths.size:
                return 0.0
            return float(np.percentile(lengths, value, method="linear"))

        return {
            "model_max_sequence_length": int(maximum),
            "chunk_count": int(lengths.size),
            "chunks_exceeding_model_max": exceeding,
            "percent_exceeding_model_max": (
                float(exceeding * 100.0 / lengths.size) if lengths.size else 0.0
            ),
            "median_token_length": percentile(50),
            "p90_token_length": percentile(90),
            "p95_token_length": percentile(95),
            "p99_token_length": percentile(99),
            "max_token_length": int(lengths.max()) if lengths.size else 0,
        }

    @property
    def statistics(self) -> dict[str, Any]:
        self._require_index()
        return {
            "indexed_chunk_count": self.indexed_chunk_count,
            "embedding_dimension": int(self._encoder.embedding_dimension),
            "index_fingerprint": self.index_fingerprint,
            "embedding_matrix_sha256": self._index_metadata[
                "embedding_matrix_sha256"
            ],
            "ordered_chunk_id_fingerprint": self._index_metadata[
                "ordered_chunk_id_fingerprint"
            ],
            "indexed_text_fingerprint": self._index_metadata[
                "indexed_text_fingerprint"
            ],
            "cache_status": self._cache_status,
            "truncation_diagnostics": self.truncation_diagnostics,
        }

    def build_index(
        self,
        records: Iterable[Mapping[str, Any]],
        *,
        corpus_fingerprint: str,
    ) -> None:
        """Embed sorted canonical records without mutating source objects."""
        source_records = sorted(records, key=lambda item: str(item.get("chunk_id", "")))
        documents: list[_DenseDocument] = []
        seen: set[str] = set()

        for source in source_records:
            chunk_id = str(source.get("chunk_id", ""))
            doc_id = str(source.get("doc_id", ""))
            accession = str(source.get("accession", ""))
            if not chunk_id or not doc_id or not accession:
                raise ValueError("each record requires chunk_id, doc_id, and accession")
            if chunk_id in seen:
                raise ValueError(f"duplicate chunk_id: {chunk_id}")
            seen.add(chunk_id)
            chunk_text = str(source.get("text") or "")
            retrieval_value = source.get("retrieval_text")
            retrieval_text = (
                str(retrieval_value) if retrieval_value is not None else chunk_text
            )
            raw_section_path = source.get("section_path") or ()
            if isinstance(raw_section_path, str):
                section_path = (raw_section_path,)
            else:
                section_path = tuple(str(part) for part in raw_section_path)

            def optional_text(field: str) -> str | None:
                value = source.get(field)
                return None if value is None else str(value)

            documents.append(
                _DenseDocument(
                    chunk_id=chunk_id,
                    doc_id=doc_id,
                    accession=accession,
                    company=optional_text("company"),
                    form=optional_text("form"),
                    filing_date=optional_text("filing_date"),
                    period_of_report=optional_text("period_of_report"),
                    fiscal_period=optional_text("fiscal_period"),
                    calendar_period=optional_text("calendar_period"),
                    source_role=optional_text("source_role"),
                    doc_role=optional_text("doc_role"),
                    exhibit_number=optional_text("exhibit_number"),
                    block_type=optional_text("block_type"),
                    section_path=section_path,
                    chunk_text=chunk_text,
                    retrieval_text=retrieval_text,
                )
            )

        texts = [document.retrieval_text for document in documents]
        token_lengths = self._encoder.token_lengths(texts)
        if len(token_lengths) != len(documents):
            raise ValueError("encoder returned an invalid token-length count")

        identity = {
            "embedding_config": self.config,
            "corpus_fingerprint": str(corpus_fingerprint),
            "indexed_chunk_count": len(documents),
            "ordered_chunk_id_fingerprint": _framed_sha256(
                document.chunk_id for document in documents
            ),
            "indexed_text_fingerprint": _framed_sha256(texts),
        }
        embeddings = self._load_cache(identity, len(documents))
        if embeddings is None:
            embeddings = normalize_embeddings(self._encoder.encode(texts))
            expected_shape = (len(documents), self._encoder.embedding_dimension)
            if embeddings.shape != expected_shape:
                raise ValueError(
                    f"encoder returned shape {embeddings.shape}; expected {expected_shape}"
                )
            matrix_hash = _matrix_sha256(embeddings)
            metadata = self._complete_metadata(identity, matrix_hash)
            self._write_cache(embeddings, metadata)
            self._cache_status = "miss" if self._cache_dir is not None else "disabled"
        else:
            matrix_hash = _matrix_sha256(embeddings)
            metadata = self._complete_metadata(identity, matrix_hash)
            self._cache_status = "hit"

        self._documents = tuple(documents)
        self._embeddings = embeddings
        self._token_lengths = tuple(int(length) for length in token_lengths)
        self._index_metadata = metadata

    def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        filters: Mapping[str, Any] | None = None,
    ) -> list[DenseSearchResult]:
        """Return cosine-ranked chunks with ascending ``chunk_id`` tie-breaks."""
        self._require_index()
        if not isinstance(query, str):
            raise TypeError("query must be a string")
        if not isinstance(top_k, int):
            raise TypeError("top_k must be an integer")
        if top_k <= 0 or not query.strip() or not self._documents:
            return []

        active_filters = dict(filters or {})
        for key in active_filters:
            if key not in _METADATA_FIELDS and key not in {
                "section_path", "chunk_id", "doc_id", "accession"
            }:
                raise ValueError(f"unsupported metadata filter: {key}")
        candidate_indices = [
            index
            for index, document in enumerate(self._documents)
            if all(
                document.metadata_value(key) == value
                for key, value in active_filters.items()
            )
        ]
        if not candidate_indices:
            return []

        query_embedding = normalize_embeddings(self._encoder.encode([query]))
        expected_shape = (1, self._encoder.embedding_dimension)
        if query_embedding.shape != expected_shape:
            raise ValueError(
                f"encoder returned query shape {query_embedding.shape}; "
                f"expected {expected_shape}"
            )
        assert self._embeddings is not None
        candidate_matrix = self._embeddings[candidate_indices]
        scores = np.asarray(candidate_matrix @ query_embedding[0], dtype=np.float32)
        chunk_ids = np.asarray(
            [self._documents[index].chunk_id for index in candidate_indices]
        )
        order = np.lexsort((chunk_ids, -scores))[:top_k]

        results: list[DenseSearchResult] = []
        for rank, candidate_position in enumerate(order, start=1):
            document_index = candidate_indices[int(candidate_position)]
            document = self._documents[document_index]
            results.append(
                DenseSearchResult(
                    rank=rank,
                    score=float(scores[int(candidate_position)]),
                    **document.__dict__,
                )
            )
        return results

    def _complete_metadata(
        self, identity: Mapping[str, Any], matrix_hash: str
    ) -> dict[str, Any]:
        stable_payload = {
            **dict(identity),
            "embedding_dimension": int(self._encoder.embedding_dimension),
            "embedding_matrix_dtype": "float32",
            "embedding_matrix_sha256": matrix_hash,
        }
        return {
            **stable_payload,
            "index_fingerprint": hashlib.sha256(
                stable_json_dumps(stable_payload).encode("utf-8")
            ).hexdigest(),
        }

    def _load_cache(
        self, identity: Mapping[str, Any], row_count: int
    ) -> np.ndarray | None:
        if self._cache_dir is None:
            return None
        metadata_path = self._cache_dir / "index_metadata.json"
        matrix_path = self._cache_dir / "embeddings.npy"
        if not metadata_path.is_file() or not matrix_path.is_file():
            return None
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            for key, value in identity.items():
                if metadata.get(key) != value:
                    return None
            matrix = np.load(matrix_path, allow_pickle=False)
        except (OSError, ValueError, json.JSONDecodeError):
            return None
        expected_shape = (row_count, self._encoder.embedding_dimension)
        if matrix.dtype != np.float32 or matrix.shape != expected_shape:
            return None
        matrix = np.ascontiguousarray(matrix, dtype=np.float32)
        if metadata.get("embedding_matrix_sha256") != _matrix_sha256(matrix):
            return None
        return matrix

    def _write_cache(
        self, matrix: np.ndarray, metadata: Mapping[str, Any]
    ) -> None:
        if self._cache_dir is None:
            return
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        matrix_descriptor, matrix_temporary = tempfile.mkstemp(
            dir=self._cache_dir,
            prefix=".embeddings.",
            suffix=".npy.tmp",
        )
        metadata_descriptor, metadata_temporary = tempfile.mkstemp(
            dir=self._cache_dir,
            prefix=".index_metadata.",
            suffix=".json.tmp",
        )
        try:
            with os.fdopen(matrix_descriptor, "wb") as handle:
                np.save(handle, matrix, allow_pickle=False)
                handle.flush()
                os.fsync(handle.fileno())
            with os.fdopen(
                metadata_descriptor, "w", encoding="utf-8", newline="\n"
            ) as handle:
                handle.write(stable_json_line(metadata))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(matrix_temporary, self._cache_dir / "embeddings.npy")
            os.replace(metadata_temporary, self._cache_dir / "index_metadata.json")
        except Exception:
            for temporary in (matrix_temporary, metadata_temporary):
                try:
                    os.unlink(temporary)
                except OSError:
                    pass
            raise

    def _require_index(self) -> None:
        if self._embeddings is None:
            raise RuntimeError("build_index must be called before retrieval")
