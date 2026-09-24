"""Gold-blind tests for deterministic reciprocal-rank fusion."""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import pytest

from src.hybrid_retrieval import (
    reciprocal_rank_fusion,
    stable_json_line,
    validate_artifact_hash,
)


def _candidate(chunk_id: str, rank: int, **metadata: object) -> dict[str, object]:
    return {
        "rank": rank,
        "score": float(100 - rank),
        "chunk_id": chunk_id,
        "accession": metadata.pop("accession", f"ACC-{chunk_id}"),
        "company": metadata.pop("company", "Example Co"),
        "form": metadata.pop("form", "10-Q"),
        "filing_date": metadata.pop("filing_date", "2026-04-30"),
        "period_of_report": metadata.pop("period_of_report", "2026-03-31"),
        "section_path": metadata.pop("section_path", ["Part I", "Item 2"]),
        "source_role": metadata.pop("source_role", "benchmark_period"),
        "chunk_text": metadata.pop("chunk_text", f"Text for {chunk_id}"),
        "retrieval_text": metadata.pop("retrieval_text", f"Text for {chunk_id}"),
        **metadata,
    }


def _record(
    candidates: list[dict[str, object]],
    *,
    q_id: str = "Q01",
    query_en: str = "example query",
) -> dict[str, object]:
    return {
        "q_id": q_id,
        "query_en": query_en,
        "corpus_fingerprint": "corpus",
        "ranked_results": candidates,
    }


def test_exact_rrf_arithmetic_and_one_indexed_ranks() -> None:
    bm25 = _record([_candidate("both", 1), _candidate("bm25-only", 2)])
    embedding = _record([_candidate("embedding-only", 1), _candidate("both", 2)])
    by_id = {
        result["chunk_id"]: result
        for result in reciprocal_rank_fusion(bm25, embedding, rrf_k=60, top_k=3)
    }

    assert by_id["both"]["bm25_rank"] == 1
    assert by_id["both"]["embedding_rank"] == 2
    assert by_id["both"]["bm25_contribution"] == 1 / 61
    assert by_id["both"]["embedding_contribution"] == 1 / 62
    assert by_id["both"]["hybrid_score"] == 1 / 61 + 1 / 62
    assert by_id["bm25-only"]["hybrid_score"] == 1 / 62
    assert by_id["bm25-only"]["embedding_rank"] is None
    assert by_id["bm25-only"]["embedding_contribution"] == 0.0
    assert by_id["embedding-only"]["hybrid_score"] == 1 / 61
    assert by_id["embedding-only"]["bm25_rank"] is None
    assert by_id["embedding-only"]["bm25_contribution"] == 0.0


def test_deduplicates_by_chunk_id_using_first_component_position() -> None:
    duplicate = _candidate("same", 2)
    duplicate["score"] = 1.0
    bm25 = _record([_candidate("same", 1), duplicate])
    embedding = _record([])

    fused = reciprocal_rank_fusion(bm25, embedding)

    assert len(fused) == 1
    assert fused[0]["bm25_rank"] == 1
    assert fused[0]["bm25_contribution"] == 1 / 61


def test_deterministic_ordering_and_chunk_id_tie_break() -> None:
    bm25 = _record([_candidate("z", 1), _candidate("a", 2)])
    embedding = _record([_candidate("a", 1), _candidate("z", 2)])

    first = reciprocal_rank_fusion(bm25, embedding)
    second = reciprocal_rank_fusion(bm25, embedding)

    assert [result["chunk_id"] for result in first] == ["a", "z"]
    assert first == second
    assert [result["rank"] for result in first] == [1, 2]


def test_top_k_behavior() -> None:
    bm25 = _record([_candidate("a", 1), _candidate("b", 2)])
    embedding = _record([_candidate("c", 1)])
    assert len(reciprocal_rank_fusion(bm25, embedding, top_k=2)) == 2
    assert reciprocal_rank_fusion(bm25, embedding, top_k=0) == []


def test_metadata_propagation_and_component_scores() -> None:
    bm25_candidate = _candidate("a", 1, fiscal_period="FY26Q1")
    embedding_candidate = _candidate("a", 1, fiscal_period="FY26Q1")
    bm25_candidate["score"] = 12.5
    embedding_candidate["score"] = 0.75

    result = reciprocal_rank_fusion(
        _record([bm25_candidate]),
        _record([embedding_candidate]),
    )[0]

    assert result["accession"] == "ACC-a"
    assert result["company"] == "Example Co"
    assert result["form"] == "10-Q"
    assert result["fiscal_period"] == "FY26Q1"
    assert result["section_path"] == ["Part I", "Item 2"]
    assert result["source_role"] == "benchmark_period"
    assert result["chunk_text"] == "Text for a"
    assert result["retrieval_text"] == "Text for a"
    assert result["bm25_score"] == 12.5
    assert result["embedding_score"] == 0.75


def test_metadata_conflict_is_rejected() -> None:
    bm25 = _record([_candidate("a", 1, company="First")])
    embedding = _record([_candidate("a", 1, company="Second")])
    with pytest.raises(ValueError, match="metadata conflict.*company"):
        reciprocal_rank_fusion(bm25, embedding)


def test_query_and_corpus_mismatches_are_rejected() -> None:
    with pytest.raises(ValueError, match="q_id mismatch"):
        reciprocal_rank_fusion(_record([]), _record([], q_id="Q02"))
    with pytest.raises(ValueError, match="query_en mismatch"):
        reciprocal_rank_fusion(_record([]), _record([], query_en="different"))
    embedding = _record([])
    embedding["corpus_fingerprint"] = "other"
    with pytest.raises(ValueError, match="corpus_fingerprint mismatch"):
        reciprocal_rank_fusion(_record([]), embedding)


def test_source_inputs_are_not_mutated() -> None:
    bm25 = _record([_candidate("a", 1)])
    embedding = _record([_candidate("a", 1)])
    before = copy.deepcopy((bm25, embedding))
    reciprocal_rank_fusion(bm25, embedding)
    assert (bm25, embedding) == before


def test_serialization_is_deterministic_and_sorted() -> None:
    value = {"z": 1, "a": {"y": 2, "b": 3}}
    first = stable_json_line(value)
    second = stable_json_line(dict(reversed(list(value.items()))))
    assert first == second == '{"a":{"b":3,"y":2},"z":1}\n'


def test_frozen_artifact_hash_validation(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.jsonl"
    artifact.write_bytes(b"frozen\n")
    expected = hashlib.sha256(b"frozen\n").hexdigest()
    assert validate_artifact_hash(artifact, expected) == expected
    with pytest.raises(ValueError, match="artifact hash mismatch"):
        validate_artifact_hash(artifact, "0" * 64)


def test_production_files_do_not_reference_gold_evaluation_inputs() -> None:
    root = Path(__file__).resolve().parent.parent
    production_sources = [
        root / "src" / "hybrid_retrieval.py",
        root / "evaluation" / "run_hybrid.py",
    ]
    forbidden_fragments = (
        "score_retrieval",
        "numeric_answers",
        "evidence_checklist",
        "benchmark/provenance",
        "evaluation/results/" + "bm25_vs_embedding_v0.1.csv",
    )
    for source in production_sources:
        text = source.read_text(encoding="utf-8")
        assert all(fragment not in text for fragment in forbidden_fragments)
