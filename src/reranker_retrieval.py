"""Deterministic cross-encoder reranking over frozen retrieval candidates.

The production ``reranker_v0.1`` candidate pool is the exact set union of
the frozen BM25 top 50 and embedding top 50 for each query.  Component ranks
and scores are retained only as audit provenance and never enter scoring.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import random
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


MODEL_ID = "BAAI/bge-reranker-v2-m3"
MODEL_REVISION = "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
MODEL_ARCHITECTURE = "XLMRobertaForSequenceClassification"
MAX_LENGTH = 1024
BATCH_SIZE = 4
SEED = 0
TORCH_NUM_THREADS = 4
TORCH_NUM_INTEROP_THREADS = 1
RRF_K = 60
CANDIDATE_DEPTH = 50
OUTPUT_DEPTH = 50
CANDIDATE_POOL_VERSION = "bm25_v0.1_top50_union_embedding_v0.1_top50"

MODEL_FILE_SHA256 = {
    "config.json": "13dcd6c31d9fec9d1d8e158702072f62d7fa7d312a64b9fe057bec9a08cfe41a",
    "sentencepiece.bpe.model": "cfc8146abe2a0488e9e2a0c56de7952f7c11ab059eca145a0a727afce0db2865",
    "special_tokens_map.json": "8c785abebea9ae3257b61681b4e6fd8365ceafde980c21970d001e834cf10835",
    "tokenizer.json": "69564b696052886ed0ac63fa393e928384e0f8caada38c1f4864a9bfbf379c15",
    "tokenizer_config.json": "7e4c1cc848840aeccdd763458c18dd525eb0f795c992e00ebe9c28554e7db2d4",
}

_COMPONENT_FIELDS = frozenset({"rank", "score"})


def sha256_file(path: str | Path) -> str:
    """Return the SHA-256 digest of a file without interpreting its content."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_artifact_hash(path: str | Path, expected_sha256: str) -> str:
    """Require *path* to have the registered SHA-256 digest."""
    actual_sha256 = sha256_file(path)
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"artifact hash mismatch for {path}: "
            f"expected={expected_sha256} actual={actual_sha256}"
        )
    return actual_sha256


def stable_json_line(value: Mapping[str, Any]) -> str:
    """Serialize one compact deterministic UTF-8 JSON Lines record."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ) + "\n"


def _require_nonempty_string(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def validate_component_record(
    record: Mapping[str, Any],
    *,
    component: str,
    expected_depth: int | None = CANDIDATE_DEPTH,
) -> Sequence[Mapping[str, Any]]:
    """Validate one frozen component record and return its ranked candidates."""
    _require_nonempty_string(record.get("q_id"), label=f"{component} q_id")
    _require_nonempty_string(record.get("query_en"), label=f"{component} query_en")
    candidates = record.get("ranked_results")
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        raise ValueError(f"{component} ranked_results must be a sequence")
    if expected_depth is not None and len(candidates) != expected_depth:
        raise ValueError(
            f"expected {expected_depth} {component} candidates; got {len(candidates)}"
        )

    seen: set[str] = set()
    for position, candidate in enumerate(candidates, start=1):
        if not isinstance(candidate, Mapping):
            raise ValueError(f"{component} candidate {position} must be an object")
        if candidate.get("rank") != position:
            raise ValueError(
                f"invalid {component} rank at position {position}: "
                f"{candidate.get('rank')!r}"
            )
        chunk_id = _require_nonempty_string(
            candidate.get("chunk_id"),
            label=f"{component} chunk_id at position {position}",
        )
        if chunk_id in seen:
            raise ValueError(f"duplicate {component} chunk_id: {chunk_id}")
        seen.add(chunk_id)
    return candidates


def _candidate_metadata(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(value)
        for key, value in candidate.items()
        if key not in _COMPONENT_FIELDS
    }


def _merge_candidate_metadata(
    existing: dict[str, Any],
    incoming: Mapping[str, Any],
    *,
    chunk_id: str,
) -> None:
    for key, value in incoming.items():
        if key in existing and existing[key] != value:
            raise ValueError(
                f"immutable candidate metadata conflict for chunk_id={chunk_id!r}, "
                f"field={key!r}: {existing[key]!r} != {value!r}"
            )
        if key not in existing:
            existing[key] = copy.deepcopy(value)


def build_candidate_union(
    bm25_record: Mapping[str, Any],
    embedding_record: Mapping[str, Any],
    *,
    expected_depth: int | None = CANDIDATE_DEPTH,
) -> list[dict[str, Any]]:
    """Build the exact chunk-id union with component provenance.

    The returned list is normalized to ascending ``chunk_id`` so component
    input ordering cannot affect model batching or final output.
    """
    bm25_candidates = validate_component_record(
        bm25_record,
        component="BM25",
        expected_depth=expected_depth,
    )
    embedding_candidates = validate_component_record(
        embedding_record,
        component="embedding",
        expected_depth=expected_depth,
    )
    for field in ("q_id", "query_en"):
        if bm25_record.get(field) != embedding_record.get(field):
            raise ValueError(f"component {field} mismatch")
    bm25_corpus = bm25_record.get("corpus_fingerprint")
    embedding_corpus = embedding_record.get("corpus_fingerprint")
    if bm25_corpus != embedding_corpus:
        raise ValueError("component corpus_fingerprint mismatch")

    by_chunk: dict[str, dict[str, Any]] = {}
    for component, candidates in (
        ("bm25", bm25_candidates),
        ("embedding", embedding_candidates),
    ):
        for position, candidate in enumerate(candidates, start=1):
            chunk_id = str(candidate["chunk_id"])
            metadata = _candidate_metadata(candidate)
            entry = by_chunk.get(chunk_id)
            if entry is None:
                entry = {
                    **metadata,
                    "bm25_rank": None,
                    "embedding_rank": None,
                    "bm25_score": None,
                    "embedding_score": None,
                }
                by_chunk[chunk_id] = entry
            else:
                provenance = {
                    key: entry[key]
                    for key in (
                        "bm25_rank",
                        "embedding_rank",
                        "bm25_score",
                        "embedding_score",
                    )
                }
                comparable = {
                    key: value
                    for key, value in entry.items()
                    if key not in provenance
                }
                _merge_candidate_metadata(comparable, metadata, chunk_id=chunk_id)
                entry = {**comparable, **provenance}
                by_chunk[chunk_id] = entry
            entry[f"{component}_rank"] = position
            entry[f"{component}_score"] = copy.deepcopy(candidate.get("score"))

    union = [by_chunk[chunk_id] for chunk_id in sorted(by_chunk)]
    for candidate in union:
        if candidate["bm25_rank"] is None and candidate["embedding_rank"] is None:
            raise AssertionError("candidate lacks frozen-component provenance")
        candidate["rrf_score"] = (
            (0.0 if candidate["bm25_rank"] is None else 1.0 / (RRF_K + candidate["bm25_rank"]))
            + (
                0.0
                if candidate["embedding_rank"] is None
                else 1.0 / (RRF_K + candidate["embedding_rank"])
            )
        )
        candidate["hybrid_rank"] = None
    return union


def add_hybrid_ranks(
    candidates: Sequence[Mapping[str, Any]],
    hybrid_record: Mapping[str, Any] | None,
    *,
    q_id: str,
    query_en: str,
    corpus_fingerprint: str,
    expected_depth: int = OUTPUT_DEPTH,
) -> list[dict[str, Any]]:
    """Attach frozen hybrid final ranks as optional audit metadata."""
    copied = [copy.deepcopy(dict(candidate)) for candidate in candidates]
    if hybrid_record is None:
        return copied
    if hybrid_record.get("q_id") != q_id:
        raise ValueError(f"hybrid q_id mismatch for {q_id}")
    if hybrid_record.get("query_en") != query_en:
        raise ValueError(f"hybrid query_en mismatch for {q_id}")
    if hybrid_record.get("corpus_fingerprint") != corpus_fingerprint:
        raise ValueError(f"hybrid corpus_fingerprint mismatch for {q_id}")
    hybrid_results = validate_component_record(
        hybrid_record,
        component="hybrid",
        expected_depth=expected_depth,
    )
    union_ids = {str(candidate["chunk_id"]) for candidate in copied}
    rank_by_chunk: dict[str, int] = {}
    for position, result in enumerate(hybrid_results, start=1):
        chunk_id = str(result["chunk_id"])
        if chunk_id not in union_ids:
            raise ValueError(f"hybrid candidate outside frozen union: {chunk_id}")
        rank_by_chunk[chunk_id] = position
    for candidate in copied:
        candidate["hybrid_rank"] = rank_by_chunk.get(str(candidate["chunk_id"]))
    return copied


@dataclass(frozen=True)
class PairScore:
    """One raw model score and its gold-blind tokenizer diagnostics."""

    chunk_id: str
    score: float
    original_token_count: int
    retained_token_count: int
    original_passage_token_count: int
    retained_passage_token_count: int
    passage_truncated: bool


class CandidateScorer(Protocol):
    """Injectable scoring interface for deterministic ranking tests."""

    def score_candidates(
        self,
        query_en: str,
        candidates: Sequence[Mapping[str, Any]],
    ) -> list[PairScore]: ...


class TransformerCrossEncoder:
    """Pinned BGE sequence-classification cross-encoder on CPU float32."""

    def __init__(
        self,
        *,
        model_id: str = MODEL_ID,
        model_revision: str = MODEL_REVISION,
        cache_dir: str | Path | None = None,
        model_path: str | Path | None = None,
        local_files_only: bool = False,
    ) -> None:
        if model_id != MODEL_ID:
            raise ValueError(f"reranker_v0.1 requires model_id={MODEL_ID}")
        if model_revision != MODEL_REVISION:
            raise ValueError(
                f"reranker_v0.1 requires model_revision={MODEL_REVISION}"
            )
        try:
            import numpy as np
            import torch
            import transformers
            from huggingface_hub import hf_hub_download
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError as exc:  # pragma: no cover - deployment failure path
            raise RuntimeError(
                "reranker_v0.1 requires compatible torch and transformers packages"
            ) from exc

        random.seed(SEED)
        np.random.seed(SEED)
        torch.manual_seed(SEED)
        torch.use_deterministic_algorithms(True)
        torch.set_num_threads(TORCH_NUM_THREADS)
        try:
            torch.set_num_interop_threads(TORCH_NUM_INTEROP_THREADS)
        except RuntimeError:
            if torch.get_num_interop_threads() != TORCH_NUM_INTEROP_THREADS:
                raise

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
        tokenizer = AutoTokenizer.from_pretrained(
            model_source,
            use_fast=True,
            **common_kwargs,
        )
        model = AutoModelForSequenceClassification.from_pretrained(
            model_source,
            use_safetensors=True,
            **common_kwargs,
        )
        model.to(device="cpu", dtype=torch.float32)
        model.eval()
        if model.__class__.__name__ != MODEL_ARCHITECTURE:
            raise ValueError(
                f"unexpected model architecture: {model.__class__.__name__}"
            )
        if int(model.config.num_labels) != 1:
            raise ValueError(f"expected one relevance logit; got {model.config.num_labels}")

        resolved_fingerprints: dict[str, str] = {}
        for filename, expected_sha256 in sorted(MODEL_FILE_SHA256.items()):
            resolved = (
                hf_hub_download(
                    repo_id=model_id,
                    filename=filename,
                    revision=model_revision,
                    cache_dir=None if cache_dir is None else str(cache_dir),
                    local_files_only=local_files_only,
                )
                if model_path is None
                else str(Path(model_path) / filename)
            )
            resolved_fingerprints[filename] = validate_artifact_hash(
                resolved,
                expected_sha256,
            )

        self._torch = torch
        self._tokenizer = tokenizer
        self._model = model
        self._runtime_config: dict[str, Any] = {
            "device": "cpu",
            "dtype": "float32",
            "batch_size": BATCH_SIZE,
            "seed": SEED,
            "model_eval": not model.training,
            "inference_mode": True,
            "torch_deterministic_algorithms": bool(
                torch.are_deterministic_algorithms_enabled()
            ),
            "torch_num_threads": int(torch.get_num_threads()),
            "torch_num_interop_threads": int(torch.get_num_interop_threads()),
            "torch_version": torch.__version__,
            "transformers_version": transformers.__version__,
            "tokenizer_class": tokenizer.__class__.__name__,
            "model_class": model.__class__.__name__,
            "pair_encoding": "native_query_passage",
            "truncation": "only_second",
            "max_length": MAX_LENGTH,
            "query_instruction": None,
            "model_file_sha256": resolved_fingerprints,
        }

    @property
    def runtime_config(self) -> Mapping[str, Any]:
        return copy.deepcopy(self._runtime_config)

    def score_candidates(
        self,
        query_en: str,
        candidates: Sequence[Mapping[str, Any]],
    ) -> list[PairScore]:
        """Return raw logits in normalized ascending chunk-id input order."""
        _require_nonempty_string(query_en, label="query_en")
        ordered = sorted(candidates, key=lambda item: str(item.get("chunk_id", "")))
        chunk_ids = [
            _require_nonempty_string(item.get("chunk_id"), label="candidate chunk_id")
            for item in ordered
        ]
        if len(set(chunk_ids)) != len(chunk_ids):
            raise ValueError("candidate chunk_ids must be unique")
        passages = [
            _require_nonempty_string(
                item.get("retrieval_text"),
                label=f"retrieval_text for {chunk_id}",
            )
            for item, chunk_id in zip(ordered, chunk_ids, strict=True)
        ]

        query_ids = self._tokenizer(
            query_en,
            add_special_tokens=False,
            truncation=False,
        )["input_ids"]
        query_token_count = len(query_ids)
        pair_special_tokens = int(self._tokenizer.num_special_tokens_to_add(pair=True))
        if query_token_count + pair_special_tokens > MAX_LENGTH:
            raise ValueError(
                "query plus required pair special tokens exceeds max_length: "
                f"query_tokens={query_token_count} special_tokens={pair_special_tokens}"
            )

        results: list[PairScore] = []
        with self._torch.inference_mode():
            for start in range(0, len(ordered), BATCH_SIZE):
                batch_chunk_ids = chunk_ids[start : start + BATCH_SIZE]
                batch_passages = passages[start : start + BATCH_SIZE]
                passage_encodings = self._tokenizer(
                    batch_passages,
                    add_special_tokens=False,
                    padding=False,
                    truncation=False,
                )["input_ids"]
                inputs = self._tokenizer(
                    [query_en] * len(batch_passages),
                    batch_passages,
                    padding=True,
                    truncation="only_second",
                    max_length=MAX_LENGTH,
                    return_tensors="pt",
                )
                outputs = self._model(**inputs)
                logits = outputs.logits.to(dtype=self._torch.float32, device="cpu").reshape(-1)
                if logits.numel() != len(batch_passages):
                    raise ValueError("model did not return exactly one logit per pair")

                retained_lengths = inputs["attention_mask"].sum(dim=1).tolist()
                for chunk_id, passage_ids, retained_length, logit in zip(
                    batch_chunk_ids,
                    passage_encodings,
                    retained_lengths,
                    logits.tolist(),
                    strict=True,
                ):
                    original_passage = len(passage_ids)
                    original_total = (
                        query_token_count + original_passage + pair_special_tokens
                    )
                    retained_total = int(retained_length)
                    retained_passage = (
                        retained_total - query_token_count - pair_special_tokens
                    )
                    if retained_passage < 0 or retained_passage > original_passage:
                        raise AssertionError("invalid tokenizer passage retention accounting")
                    score = float(logit)
                    if not math.isfinite(score):
                        raise ValueError(f"non-finite reranker score for {chunk_id}")
                    results.append(
                        PairScore(
                            chunk_id=chunk_id,
                            score=score,
                            original_token_count=original_total,
                            retained_token_count=retained_total,
                            original_passage_token_count=original_passage,
                            retained_passage_token_count=retained_passage,
                            passage_truncated=retained_passage < original_passage,
                        )
                    )
        return results


def rank_scored_candidates(
    candidates: Sequence[Mapping[str, Any]],
    pair_scores: Sequence[PairScore],
    *,
    top_k: int = OUTPUT_DEPTH,
) -> list[dict[str, Any]]:
    """Join scores to candidates and rank by raw logit then chunk ID."""
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 0:
        raise ValueError("top_k must be a non-negative integer")
    by_id: dict[str, Mapping[str, Any]] = {}
    for candidate in candidates:
        chunk_id = _require_nonempty_string(
            candidate.get("chunk_id"), label="candidate chunk_id"
        )
        if chunk_id in by_id:
            raise ValueError(f"duplicate candidate chunk_id: {chunk_id}")
        by_id[chunk_id] = candidate
    score_by_id: dict[str, PairScore] = {}
    for pair_score in pair_scores:
        if pair_score.chunk_id in score_by_id:
            raise ValueError(f"duplicate score for chunk_id: {pair_score.chunk_id}")
        if pair_score.chunk_id not in by_id:
            raise ValueError(f"score outside candidate union: {pair_score.chunk_id}")
        if not math.isfinite(pair_score.score):
            raise ValueError(f"non-finite reranker score for {pair_score.chunk_id}")
        score_by_id[pair_score.chunk_id] = pair_score
    if set(score_by_id) != set(by_id):
        missing = sorted(set(by_id) - set(score_by_id))
        raise ValueError(f"missing reranker scores for candidates: {missing}")

    ranked = [
        {**copy.deepcopy(dict(candidate)), "reranker_score": score_by_id[chunk_id].score}
        for chunk_id, candidate in by_id.items()
    ]
    ranked.sort(key=lambda item: (-item["reranker_score"], item["chunk_id"]))
    selected = ranked[:top_k]
    for rank, result in enumerate(selected, start=1):
        result["rank"] = rank
        result["reranker_rank"] = rank
    return selected


def _length_summary(values: Sequence[int]) -> dict[str, float | int]:
    if not values:
        return {"count": 0, "min": 0, "median": 0.0, "max": 0}
    return {
        "count": len(values),
        "min": min(values),
        "median": float(statistics.median(values)),
        "max": max(values),
    }


def truncation_diagnostics(
    pair_scores: Sequence[PairScore],
) -> dict[str, Any]:
    """Summarize deterministic, gold-blind pair tokenization behavior."""
    truncated = [score for score in pair_scores if score.passage_truncated]
    count = len(pair_scores)
    return {
        "input_pair_count": count,
        "truncated_pair_count": len(truncated),
        "truncated_pair_proportion": 0.0 if count == 0 else len(truncated) / count,
        "original_token_count": _length_summary(
            [score.original_token_count for score in pair_scores]
        ),
        "retained_token_count": _length_summary(
            [score.retained_token_count for score in pair_scores]
        ),
        "truncated_pairs": [
            {
                "chunk_id": score.chunk_id,
                "original_token_count": score.original_token_count,
                "retained_token_count": score.retained_token_count,
                "original_passage_token_count": score.original_passage_token_count,
                "retained_passage_token_count": score.retained_passage_token_count,
                "passage_truncated": True,
            }
            for score in sorted(truncated, key=lambda item: item.chunk_id)
        ],
    }
