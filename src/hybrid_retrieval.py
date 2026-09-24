"""Deterministic reciprocal-rank fusion for ranked retrieval results."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


_COMPONENT_ONLY_FIELDS = frozenset({"rank", "score"})


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of *path* without interpreting its contents."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_artifact_hash(path: Path, expected_sha256: str) -> str:
    """Verify a frozen input artifact and return its digest."""
    actual_sha256 = sha256_file(path)
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"artifact hash mismatch for {path}: "
            f"expected={expected_sha256} actual={actual_sha256}"
        )
    return actual_sha256


def stable_json_line(value: Mapping[str, Any]) -> str:
    """Serialize one deterministic, compact JSON Lines record."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"


def _validate_query_pair(
    bm25_record: Mapping[str, Any],
    embedding_record: Mapping[str, Any],
) -> None:
    for field in ("q_id", "query_en"):
        bm25_value = bm25_record.get(field)
        embedding_value = embedding_record.get(field)
        if not isinstance(bm25_value, str) or not bm25_value:
            raise ValueError(f"BM25 record requires a non-empty {field}")
        if not isinstance(embedding_value, str) or not embedding_value:
            raise ValueError(f"embedding record requires a non-empty {field}")
        if bm25_value != embedding_value:
            raise ValueError(
                f"component {field} mismatch: "
                f"bm25={bm25_value!r} embedding={embedding_value!r}"
            )

    bm25_fingerprint = bm25_record.get("corpus_fingerprint")
    embedding_fingerprint = embedding_record.get("corpus_fingerprint")
    if (
        bm25_fingerprint is not None
        and embedding_fingerprint is not None
        and bm25_fingerprint != embedding_fingerprint
    ):
        raise ValueError(
            "component corpus_fingerprint mismatch: "
            f"bm25={bm25_fingerprint!r} "
            f"embedding={embedding_fingerprint!r}"
        )


def _ranked_candidates(
    record: Mapping[str, Any],
    *,
    component: str,
) -> Sequence[Mapping[str, Any]]:
    candidates = record.get("ranked_results")
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        raise TypeError(f"{component} ranked_results must be a sequence")
    for position, candidate in enumerate(candidates, start=1):
        if not isinstance(candidate, Mapping):
            raise TypeError(
                f"{component} candidate at position {position} must be a mapping"
            )
        declared_rank = candidate.get("rank")
        if declared_rank is not None and declared_rank != position:
            raise ValueError(
                f"{component} rank mismatch at position {position}: "
                f"declared={declared_rank!r}"
            )
    return candidates


def _candidate_metadata(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(value)
        for key, value in candidate.items()
        if key not in _COMPONENT_ONLY_FIELDS
    }


def _merge_metadata(
    existing: dict[str, Any],
    incoming: Mapping[str, Any],
    *,
    chunk_id: str,
) -> None:
    for key, value in incoming.items():
        if key in existing and existing[key] != value:
            raise ValueError(
                f"metadata conflict for chunk_id={chunk_id!r}, field={key!r}: "
                f"bm25={existing[key]!r} embedding={value!r}"
            )
        if key not in existing:
            existing[key] = copy.deepcopy(value)


def reciprocal_rank_fusion(
    bm25_results: Mapping[str, Any],
    embedding_results: Mapping[str, Any],
    *,
    rrf_k: int = 60,
    top_k: int = 50,
) -> list[dict[str, Any]]:
    """Fuse two query records using equal-weight reciprocal-rank fusion.

    The two inputs are query-level records containing ``q_id``, ``query_en``,
    and ``ranked_results``. List position supplies the 1-indexed component
    rank. A repeated chunk within a component is counted only at its first
    position. Exact score ties are resolved by ascending ``chunk_id``.
    """
    if isinstance(rrf_k, bool) or not isinstance(rrf_k, int) or rrf_k < 0:
        raise ValueError("rrf_k must be a non-negative integer")
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 0:
        raise ValueError("top_k must be a non-negative integer")

    _validate_query_pair(bm25_results, embedding_results)
    bm25_candidates = _ranked_candidates(bm25_results, component="BM25")
    embedding_candidates = _ranked_candidates(
        embedding_results,
        component="embedding",
    )

    fused_by_chunk: dict[str, dict[str, Any]] = {}
    for component, candidates in (
        ("bm25", bm25_candidates),
        ("embedding", embedding_candidates),
    ):
        seen_in_component: set[str] = set()
        for rank, candidate in enumerate(candidates, start=1):
            chunk_id = candidate.get("chunk_id")
            if not isinstance(chunk_id, str) or not chunk_id:
                raise ValueError(
                    f"{component} candidate at position {rank} requires chunk_id"
                )
            metadata = _candidate_metadata(candidate)
            if chunk_id in seen_in_component:
                _merge_metadata(
                    fused_by_chunk[chunk_id]["metadata"],
                    metadata,
                    chunk_id=chunk_id,
                )
                continue
            seen_in_component.add(chunk_id)

            entry = fused_by_chunk.get(chunk_id)
            if entry is None:
                entry = {
                    "metadata": metadata,
                    "bm25_rank": None,
                    "embedding_rank": None,
                    "bm25_score": None,
                    "embedding_score": None,
                    "bm25_contribution": 0.0,
                    "embedding_contribution": 0.0,
                }
                fused_by_chunk[chunk_id] = entry
            else:
                _merge_metadata(entry["metadata"], metadata, chunk_id=chunk_id)

            entry[f"{component}_rank"] = rank
            entry[f"{component}_score"] = copy.deepcopy(candidate.get("score"))
            entry[f"{component}_contribution"] = 1.0 / (rrf_k + rank)

    fused: list[dict[str, Any]] = []
    for entry in fused_by_chunk.values():
        result = {
            **entry["metadata"],
            "bm25_rank": entry["bm25_rank"],
            "embedding_rank": entry["embedding_rank"],
            "bm25_score": entry["bm25_score"],
            "embedding_score": entry["embedding_score"],
            "bm25_contribution": entry["bm25_contribution"],
            "embedding_contribution": entry["embedding_contribution"],
            "hybrid_score": (
                entry["bm25_contribution"] + entry["embedding_contribution"]
            ),
        }
        fused.append(result)

    fused.sort(key=lambda result: (-result["hybrid_score"], result["chunk_id"]))
    selected = fused[:top_k]
    for rank, result in enumerate(selected, start=1):
        result["rank"] = rank
    return selected
