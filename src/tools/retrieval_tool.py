"""RetrievalTool v0.1 over the frozen production retrieval stack.

The tool executes lexical and dense retrieval for each new query, constructs
their exact chunk-id union, and applies the pinned cross-encoder. It never
reads benchmark rankings, gold annotations, or evaluation artifacts.
"""

from __future__ import annotations

import copy
import json
import math
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from src.embedding_retrieval import (
    DEFAULT_MODEL_ID as EMBEDDING_MODEL_ID,
    DEFAULT_MODEL_REVISION as EMBEDDING_MODEL_REVISION,
    DenseRetriever,
)
from src.reranker_retrieval import (
    BATCH_SIZE as RERANKER_BATCH_SIZE,
    CANDIDATE_DEPTH,
    MAX_LENGTH,
    MODEL_ID as RERANKER_MODEL_ID,
    MODEL_REVISION as RERANKER_MODEL_REVISION,
    CandidateScorer,
    TransformerCrossEncoder,
    build_candidate_union,
    rank_scored_candidates,
)
from src.retrieval import (
    BM25_IMPLEMENTATION,
    BM25_IMPLEMENTATION_VERSION,
    DEFAULT_B,
    DEFAULT_K1,
    TOKENIZER_VERSION,
    BM25Retriever,
    load_ingested_corpus,
)


TOOL_NAME = "RetrievalTool"
TOOL_VERSION = "retrieval_tool_v0.1"
RETRIEVAL_STACK_VERSION = "retrieval_stack_v0.1"
RETRIEVAL_STACK_COMMIT = "963b089e17983eec954c30970e408c7efc53a9f8"
EXPECTED_CORPUS_FINGERPRINT = (
    "56df698d50b13cf15e913c1c60dbc96b1fd0fab44adb7b1f40ba99771c4b7c96"
)
EXPECTED_INGESTION_SCHEMA_VERSION = "0.1.1"
MAX_TOP_K = 50

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DATA_DIR = _PROJECT_ROOT / "data"
_DEFAULT_EMBEDDING_CACHE = _DEFAULT_DATA_DIR / "embedding_cache" / "embedding_v0.1"
_DEFAULT_MODEL_CACHE = _DEFAULT_DATA_DIR / "model_cache" / "huggingface"

_IDENTITY_FIELDS = (
    "doc_id",
    "accession",
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
    "section_path",
)


class RetrievalToolError(Exception):
    """Base class for deterministic RetrievalTool failures."""


class RetrievalInputError(RetrievalToolError, ValueError):
    """The tool call violates the public input contract."""


class RetrievalArtifactError(RetrievalToolError, RuntimeError):
    """A required frozen corpus, index, or model artifact is unavailable."""


class RetrievalModelRevisionError(RetrievalArtifactError):
    """A retrieval component declares a non-frozen model revision."""


class RetrievalUpstreamError(RetrievalToolError, RuntimeError):
    """A retrieval component returned an invalid candidate set."""


class RetrievalMetadataError(RetrievalUpstreamError):
    """Component metadata conflicts with another component or the corpus."""


class RankedRetriever(Protocol):
    """Injectable lexical/dense component contract."""

    def search(self, query: str, *, top_k: int) -> Sequence[Any]: ...


@dataclass(frozen=True)
class RetrievalResult:
    """One reranker-ranked result with citation-ready corpus metadata."""

    rank: int
    chunk_id: str
    text: str
    accession: str
    locator: str
    doc_id: str
    company: str | None
    form_type: str | None
    filing_date: str | None
    period_of_report: str | None
    fiscal_period: str | None
    calendar_period: str | None
    source_role: str | None
    doc_role: str | None
    exhibit_number: str | None
    block_type: str | None
    section_path: tuple[str, ...]
    char_start: int | None
    char_end: int | None
    table_metadata: Mapping[str, Any] | None
    reranker_score: float
    reranker_rank: int
    bm25_rank: int | None
    embedding_rank: int | None

    def to_dict(self) -> dict[str, Any]:
        payload = copy.deepcopy(self.__dict__)
        payload["section_path"] = list(self.section_path)
        return payload


@dataclass(frozen=True)
class RetrievalTrace:
    """Deterministic, gold-blind audit trace for one tool call."""

    tool_name: str
    tool_version: str
    query: str
    requested_top_k: int
    bm25_candidate_count: int
    embedding_candidate_count: int
    union_candidate_count: int
    returned_count: int
    returned_chunk_ids: tuple[str, ...]
    retrieval_stack_version: str
    retrieval_stack_commit: str
    corpus_fingerprint: str
    bm25_metadata: Mapping[str, Any]
    embedding_metadata: Mapping[str, Any]
    reranker_metadata: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = copy.deepcopy(self.__dict__)
        payload["returned_chunk_ids"] = list(self.returned_chunk_ids)
        return payload

    def canonical_json(self) -> str:
        return canonical_trace_json(self)


@dataclass(frozen=True)
class RetrievalResponse:
    """Public RetrievalTool v0.1 response."""

    tool_version: str
    query: str
    top_k: int
    candidate_pool_size: int
    results: tuple[RetrievalResult, ...]
    trace: RetrievalTrace

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_version": self.tool_version,
            "query": self.query,
            "top_k": self.top_k,
            "candidate_pool_size": self.candidate_pool_size,
            "results": [result.to_dict() for result in self.results],
            "trace": self.trace.to_dict(),
        }


def canonical_trace_json(trace: RetrievalTrace | Mapping[str, Any]) -> str:
    """Return canonical UTF-8 JSON text suitable for future hashing."""
    payload = trace.to_dict() if isinstance(trace, RetrievalTrace) else dict(trace)
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ) + "\n"


class RetrievalTool:
    """Reusable wrapper around the frozen BM25+dense union and reranker.

    Heavy immutable resources are supplied once at construction and reused by
    every ``search`` call. ``from_frozen_stack`` is the production factory;
    direct construction supports deterministic test doubles.
    """

    def __init__(
        self,
        *,
        bm25_retriever: RankedRetriever,
        embedding_retriever: RankedRetriever,
        reranker: CandidateScorer,
        corpus_records: Sequence[Mapping[str, Any]],
        corpus_fingerprint: str,
    ) -> None:
        if corpus_fingerprint != EXPECTED_CORPUS_FINGERPRINT:
            raise RetrievalArtifactError(
                "corpus fingerprint mismatch: "
                f"expected={EXPECTED_CORPUS_FINGERPRINT} actual={corpus_fingerprint}"
            )
        self._bm25 = bm25_retriever
        self._embedding = embedding_retriever
        self._reranker = reranker
        self._corpus_fingerprint = corpus_fingerprint
        self._records = self._index_corpus_records(corpus_records)
        self._validate_declared_component_identities()

    @classmethod
    def from_frozen_stack(
        cls,
        *,
        data_dir: str | Path = _DEFAULT_DATA_DIR,
        embedding_cache_dir: str | Path = _DEFAULT_EMBEDDING_CACHE,
        model_cache_dir: str | Path = _DEFAULT_MODEL_CACHE,
    ) -> "RetrievalTool":
        """Initialize all frozen production resources once for repeated calls."""
        data_path = Path(data_dir)
        embedding_cache_path = Path(embedding_cache_dir)
        model_cache_path = Path(model_cache_dir)
        required = (
            (data_path / "manifest.json", "corpus manifest"),
            (data_path / "chunks", "corpus chunk directory"),
            (embedding_cache_path / "index_metadata.json", "embedding index metadata"),
            (embedding_cache_path / "embeddings.npy", "embedding matrix"),
            (model_cache_path, "model cache"),
        )
        for path, label in required:
            if not path.exists():
                raise RetrievalArtifactError(f"missing {label}: {path}")

        try:
            snapshot = load_ingested_corpus(
                data_path,
                expected_corpus_fingerprint=EXPECTED_CORPUS_FINGERPRINT,
                expected_ingestion_schema_version=EXPECTED_INGESTION_SCHEMA_VERSION,
                verify_chunk_hashes=True,
            )
            bm25 = BM25Retriever(k1=DEFAULT_K1, b=DEFAULT_B)
            bm25.build_index(snapshot.records)

            # Work from an exact temporary copy so a cache mismatch can never
            # rewrite a frozen embedding artifact.
            with tempfile.TemporaryDirectory(prefix="retrieval_tool_dense_cache_") as tmp:
                temporary_cache = Path(tmp)
                shutil.copy2(
                    embedding_cache_path / "index_metadata.json",
                    temporary_cache / "index_metadata.json",
                )
                shutil.copy2(
                    embedding_cache_path / "embeddings.npy",
                    temporary_cache / "embeddings.npy",
                )
                dense = DenseRetriever(
                    cache_dir=temporary_cache,
                    model_cache_dir=model_cache_path,
                    local_files_only=True,
                )
                dense.build_index(
                    snapshot.records,
                    corpus_fingerprint=snapshot.corpus_fingerprint,
                )
                if dense.cache_status != "hit":
                    raise RetrievalArtifactError(
                        "frozen embedding cache did not validate as an exact cache hit"
                    )

            reranker = TransformerCrossEncoder(
                model_id=RERANKER_MODEL_ID,
                model_revision=RERANKER_MODEL_REVISION,
                cache_dir=model_cache_path,
                local_files_only=True,
            )
        except RetrievalToolError:
            raise
        except FileNotFoundError as exc:
            raise RetrievalArtifactError(f"missing frozen artifact: {exc.filename}") from exc
        except (OSError, RuntimeError) as exc:
            raise RetrievalArtifactError(
                f"failed to initialize frozen retrieval artifacts: {exc}"
            ) from exc
        except ValueError as exc:
            message = str(exc)
            if "model_revision" in message or "model revision" in message:
                raise RetrievalModelRevisionError(message) from exc
            raise RetrievalArtifactError(
                f"frozen retrieval artifact validation failed: {message}"
            ) from exc

        return cls(
            bm25_retriever=bm25,
            embedding_retriever=dense,
            reranker=reranker,
            corpus_records=snapshot.records,
            corpus_fingerprint=snapshot.corpus_fingerprint,
        )

    def search(self, query: str, top_k: int = 10) -> RetrievalResponse:
        """Execute frozen BM25 top50 + dense top50 -> union -> reranker."""
        normalized_query = self._validate_call(query, top_k)
        try:
            bm25_results = self._component_results(
                self._bm25.search(normalized_query, top_k=CANDIDATE_DEPTH),
                component="BM25",
            )
            embedding_results = self._component_results(
                self._embedding.search(normalized_query, top_k=CANDIDATE_DEPTH),
                component="embedding",
            )
            bm25_record = self._component_record(normalized_query, bm25_results)
            embedding_record = self._component_record(
                normalized_query, embedding_results
            )
            union = build_candidate_union(
                bm25_record,
                embedding_record,
                expected_depth=None,
            )
        except RetrievalToolError:
            raise
        except ValueError as exc:
            message = str(exc)
            if "duplicate" in message:
                raise RetrievalUpstreamError(message) from exc
            if "metadata conflict" in message or "mismatch" in message:
                raise RetrievalMetadataError(message) from exc
            raise RetrievalUpstreamError(message) from exc

        for candidate in union:
            self._validate_candidate_against_corpus(candidate)

        try:
            pair_scores = self._reranker.score_candidates(normalized_query, union)
            fully_ranked = rank_scored_candidates(
                union,
                pair_scores,
                top_k=len(union),
            )
            ranked = fully_ranked[:top_k]
        except RetrievalToolError:
            raise
        except ValueError as exc:
            raise RetrievalUpstreamError(str(exc)) from exc

        union_ids = {str(candidate["chunk_id"]) for candidate in union}
        ranked_ids = [str(candidate["chunk_id"]) for candidate in ranked]
        if len(ranked_ids) != top_k:
            raise RetrievalUpstreamError(
                f"reranker returned {len(ranked_ids)} results; expected {top_k}"
            )
        if len(set(ranked_ids)) != len(ranked_ids):
            raise RetrievalUpstreamError("reranker returned duplicate chunk_ids")
        if not set(ranked_ids).issubset(union_ids):
            raise RetrievalUpstreamError("reranker returned a result outside component union")

        results = tuple(self._public_result(candidate) for candidate in ranked)
        trace = RetrievalTrace(
            tool_name=TOOL_NAME,
            tool_version=TOOL_VERSION,
            query=normalized_query,
            requested_top_k=top_k,
            bm25_candidate_count=len(bm25_results),
            embedding_candidate_count=len(embedding_results),
            union_candidate_count=len(union),
            returned_count=len(results),
            returned_chunk_ids=tuple(result.chunk_id for result in results),
            retrieval_stack_version=RETRIEVAL_STACK_VERSION,
            retrieval_stack_commit=RETRIEVAL_STACK_COMMIT,
            corpus_fingerprint=self._corpus_fingerprint,
            bm25_metadata={
                "implementation": BM25_IMPLEMENTATION,
                "implementation_version": BM25_IMPLEMENTATION_VERSION,
                "tokenizer_version": TOKENIZER_VERSION,
                "k1": DEFAULT_K1,
                "b": DEFAULT_B,
                "candidate_depth": CANDIDATE_DEPTH,
            },
            embedding_metadata={
                "model_id": EMBEDDING_MODEL_ID,
                "model_revision": EMBEDDING_MODEL_REVISION,
                "candidate_depth": CANDIDATE_DEPTH,
                "query_instruction": None,
                "similarity": "dot_product_over_l2_normalized_vectors",
            },
            reranker_metadata={
                "model_id": RERANKER_MODEL_ID,
                "model_revision": RERANKER_MODEL_REVISION,
                "candidate_pool": "bm25_top50_union_embedding_top50",
                "score": "raw_cross_encoder_logit",
                "max_length": MAX_LENGTH,
                "truncation": "only_second",
                "device": "cpu",
                "dtype": "float32",
                "batch_size": RERANKER_BATCH_SIZE,
                "tie_break": "chunk_id_ascending",
            },
        )
        return RetrievalResponse(
            tool_version=TOOL_VERSION,
            query=normalized_query,
            top_k=top_k,
            candidate_pool_size=len(union),
            results=results,
            trace=trace,
        )

    @staticmethod
    def _validate_call(query: str, top_k: int) -> str:
        if not isinstance(query, str) or not query.strip():
            raise RetrievalInputError("query must be a non-empty string")
        if isinstance(top_k, bool) or not isinstance(top_k, int):
            raise RetrievalInputError("top_k must be an integer")
        if top_k < 1 or top_k > MAX_TOP_K:
            raise RetrievalInputError("top_k must be between 1 and 50 inclusive")
        return query.strip()

    @staticmethod
    def _index_corpus_records(
        records: Sequence[Mapping[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        indexed: dict[str, dict[str, Any]] = {}
        for record in records:
            chunk_id = str(record.get("chunk_id", ""))
            accession = str(record.get("accession", ""))
            doc_id = str(record.get("doc_id", ""))
            if not chunk_id or not accession or not doc_id:
                raise RetrievalMetadataError(
                    "each corpus record requires chunk_id, accession, and doc_id"
                )
            if chunk_id in indexed:
                raise RetrievalMetadataError(f"duplicate corpus chunk_id: {chunk_id}")
            indexed[chunk_id] = copy.deepcopy(dict(record))
        if not indexed:
            raise RetrievalArtifactError("frozen corpus contains no chunks")
        return indexed

    def _validate_declared_component_identities(self) -> None:
        dense_config = getattr(self._embedding, "config", None)
        if isinstance(dense_config, Mapping):
            model_id = dense_config.get("model_id")
            revision = dense_config.get("model_revision")
            if model_id is not None and model_id != EMBEDDING_MODEL_ID:
                raise RetrievalModelRevisionError(
                    f"embedding model mismatch: expected={EMBEDDING_MODEL_ID} actual={model_id}"
                )
            if revision is not None and revision != EMBEDDING_MODEL_REVISION:
                raise RetrievalModelRevisionError(
                    "embedding model revision mismatch: "
                    f"expected={EMBEDDING_MODEL_REVISION} actual={revision}"
                )
        reranker_model = getattr(self._reranker, "model_id", None)
        reranker_revision = getattr(self._reranker, "model_revision", None)
        if reranker_model is not None and reranker_model != RERANKER_MODEL_ID:
            raise RetrievalModelRevisionError(
                f"reranker model mismatch: expected={RERANKER_MODEL_ID} actual={reranker_model}"
            )
        if reranker_revision is not None and reranker_revision != RERANKER_MODEL_REVISION:
            raise RetrievalModelRevisionError(
                "reranker model revision mismatch: "
                f"expected={RERANKER_MODEL_REVISION} actual={reranker_revision}"
            )

    @staticmethod
    def _component_results(results: Sequence[Any], *, component: str) -> list[dict[str, Any]]:
        converted: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in results:
            if isinstance(item, Mapping):
                payload = copy.deepcopy(dict(item))
            else:
                to_dict = getattr(item, "to_dict", None)
                if not callable(to_dict):
                    raise RetrievalUpstreamError(
                        f"{component} result must be a mapping or expose to_dict()"
                    )
                payload = copy.deepcopy(dict(to_dict()))
            chunk_id = str(payload.get("chunk_id", ""))
            if not chunk_id:
                raise RetrievalUpstreamError(f"{component} result missing chunk_id")
            if chunk_id in seen:
                raise RetrievalUpstreamError(
                    f"duplicate {component} chunk_id: {chunk_id}"
                )
            seen.add(chunk_id)
            converted.append(payload)
        if len(converted) > CANDIDATE_DEPTH:
            raise RetrievalUpstreamError(
                f"{component} returned {len(converted)} candidates; "
                f"maximum is {CANDIDATE_DEPTH}"
            )
        return converted

    def _component_record(
        self, query: str, results: Sequence[Mapping[str, Any]]
    ) -> dict[str, Any]:
        return {
            "q_id": TOOL_VERSION,
            "query_en": query,
            "corpus_fingerprint": self._corpus_fingerprint,
            "ranked_results": list(results),
        }

    def _validate_candidate_against_corpus(self, candidate: Mapping[str, Any]) -> None:
        chunk_id = str(candidate.get("chunk_id", ""))
        record = self._records.get(chunk_id)
        if record is None:
            raise RetrievalMetadataError(
                f"component candidate not present in frozen corpus: {chunk_id}"
            )
        for field in _IDENTITY_FIELDS:
            candidate_value = candidate.get(field)
            record_value = record.get(field)
            if field == "section_path":
                candidate_value = tuple(candidate_value or ())
                record_value = tuple(record_value or ())
            elif candidate_value is not None:
                candidate_value = str(candidate_value)
                record_value = None if record_value is None else str(record_value)
            if candidate_value != record_value:
                raise RetrievalMetadataError(
                    f"candidate/corpus metadata conflict for chunk_id={chunk_id!r}, "
                    f"field={field!r}: {candidate_value!r} != {record_value!r}"
                )
        canonical_text = str(record.get("text") or "")
        canonical_retrieval_text = str(
            record.get("retrieval_text")
            if record.get("retrieval_text") is not None
            else canonical_text
        )
        if candidate.get("chunk_text") != canonical_text:
            raise RetrievalMetadataError(
                f"candidate/corpus text conflict for chunk_id={chunk_id!r}"
            )
        if candidate.get("retrieval_text") != canonical_retrieval_text:
            raise RetrievalMetadataError(
                f"candidate/corpus retrieval_text conflict for chunk_id={chunk_id!r}"
            )

    def _public_result(self, candidate: Mapping[str, Any]) -> RetrievalResult:
        chunk_id = str(candidate["chunk_id"])
        record = self._records[chunk_id]
        score = float(candidate["reranker_score"])
        if not math.isfinite(score):
            raise RetrievalUpstreamError(
                f"non-finite reranker score for chunk_id={chunk_id}"
            )
        return RetrievalResult(
            rank=int(candidate["rank"]),
            chunk_id=chunk_id,
            text=str(record.get("text") or ""),
            accession=str(record["accession"]),
            locator=self._locator(record),
            doc_id=str(record["doc_id"]),
            company=self._optional_text(record, "company"),
            form_type=self._optional_text(record, "form"),
            filing_date=self._optional_text(record, "filing_date"),
            period_of_report=self._optional_text(record, "period_of_report"),
            fiscal_period=self._optional_text(record, "fiscal_period"),
            calendar_period=self._optional_text(record, "calendar_period"),
            source_role=self._optional_text(record, "source_role"),
            doc_role=self._optional_text(record, "doc_role"),
            exhibit_number=self._optional_text(record, "exhibit_number"),
            block_type=self._optional_text(record, "block_type"),
            section_path=tuple(str(part) for part in (record.get("section_path") or ())),
            char_start=self._optional_int(record, "char_start"),
            char_end=self._optional_int(record, "char_end"),
            table_metadata=self._table_metadata(record),
            reranker_score=score,
            reranker_rank=int(candidate["reranker_rank"]),
            bm25_rank=self._optional_int(candidate, "bm25_rank"),
            embedding_rank=self._optional_int(candidate, "embedding_rank"),
        )

    @staticmethod
    def _locator(record: Mapping[str, Any]) -> str:
        explicit = record.get("locator")
        if isinstance(explicit, str) and explicit.strip():
            return explicit
        section_path = [str(part) for part in (record.get("section_path") or ())]
        if section_path:
            return " > ".join(section_path)
        start = record.get("char_start")
        end = record.get("char_end")
        if isinstance(start, int) and isinstance(end, int):
            return f"{record['doc_id']} chars {start}-{end}"
        raise RetrievalMetadataError(
            f"chunk has no authoritative locator fields: {record.get('chunk_id')}"
        )

    @staticmethod
    def _table_metadata(record: Mapping[str, Any]) -> Mapping[str, Any] | None:
        fields = ("table_json", "period_columns", "unit_scale", "xbrl_facts")
        if record.get("block_type") != "table" and not any(
            record.get(field) for field in fields
        ):
            return None
        return {field: copy.deepcopy(record.get(field)) for field in fields}

    @staticmethod
    def _optional_text(record: Mapping[str, Any], field: str) -> str | None:
        value = record.get(field)
        return None if value is None else str(value)

    @staticmethod
    def _optional_int(record: Mapping[str, Any], field: str) -> int | None:
        value = record.get(field)
        return None if value is None else int(value)
