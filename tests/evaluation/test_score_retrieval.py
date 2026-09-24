"""Tests for provenance-aware scoring of the frozen retrieval baseline."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from evaluation import score_retrieval


ROOT = Path(__file__).resolve().parents[2]
FROZEN_RESULT = ROOT / "evaluation" / "results" / "bm25_v0.1.jsonl"


def _source(chunk_id: str, accession: str = "A1") -> dict[str, str]:
    return {"chunk_id": chunk_id, "accession": accession}


def _part(part_id: str, *chunk_ids: str) -> dict:
    return {
        "part_id": part_id,
        "candidate_chunk_ids": list(chunk_ids),
        "candidate_sources": [_source(chunk_id) for chunk_id in chunk_ids],
    }


def _item(*parts: dict) -> dict:
    return {
        "q_id": "QX",
        "item_id": "EX",
        "importance": "core",
        "parts": list(parts),
    }


def _direct_fact(fact_id: str, *chunk_ids: str) -> dict:
    return {
        "fact_id": fact_id,
        "status": "direct_unique" if len(chunk_ids) == 1 else "direct_or",
        "candidate_chunk_ids": list(chunk_ids),
        "candidate_sources": [_source(chunk_id) for chunk_id in chunk_ids],
        "input_fact_ids": [],
    }


def _derived_fact(fact_id: str, inputs: list[str], candidates: list[str]) -> dict:
    return {
        "fact_id": fact_id,
        "status": "derived",
        "candidate_chunk_ids": candidates,
        "candidate_sources": [_source(chunk_id) for chunk_id in candidates],
        "input_fact_ids": inputs,
    }


def _ranked(*chunk_ids: str) -> dict[str, int]:
    return {chunk_id: rank for rank, chunk_id in enumerate(chunk_ids, start=1)}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_evidence_or_candidates_hit_one_atomic_part() -> None:
    state = score_retrieval._evidence_item_state(
        _item(_part("P01", "alternative-a", "alternative-b")),
        _ranked("irrelevant", "alternative-b"),
        k=2,
    )
    assert state["hit_count"] == 1
    assert state["coverage"] == 1.0
    assert state["all_parts"] is True
    assert state["parts"][0]["first_rank"] == 2


def test_evidence_parts_are_and_with_partial_coverage_and_strict_completion() -> None:
    item = _item(_part("P01", "hit"), _part("P02", "miss"))
    partial = score_retrieval._evidence_item_state(item, _ranked("hit"), k=1)
    assert partial["hit_count"] == 1
    assert partial["coverage"] == 0.5
    assert partial["all_parts"] is False

    complete = score_retrieval._evidence_item_state(item, _ranked("hit", "miss"), k=2)
    assert complete["coverage"] == 1.0
    assert complete["all_parts"] is True


def test_derived_numeric_fact_requires_all_recursive_inputs_with_or_leaves() -> None:
    facts = [
        _direct_fact("F1", "a1", "a2"),
        _direct_fact("F2", "b"),
        _derived_fact("F3", ["F1", "F2"], ["a1", "a2", "b"]),
        _derived_fact("F4", ["F3"], ["a1", "a2", "b"]),
    ]
    provenance = score_retrieval.NumericProvenance(facts)
    requirements = provenance.requirements("F4")
    assert [requirement.requirement_id for requirement in requirements] == ["F1", "F2"]
    assert requirements[0].candidate_chunk_ids == ("a1", "a2")

    partial = score_retrieval._fact_state(facts[-1], provenance, _ranked("a2"), k=1)
    assert partial["input_coverage"] == 0.5
    assert partial["strict"] is False

    complete = score_retrieval._fact_state(
        facts[-1], provenance, _ranked("a2", "b"), k=2
    )
    assert complete["strict"] is True


def test_missing_and_malformed_bm25_q_id_are_rejected(tmp_path: Path) -> None:
    missing = tmp_path / "missing.jsonl"
    missing.write_text(json.dumps({"ranked_results": []}) + "\n", encoding="utf-8")
    with pytest.raises(score_retrieval.EvaluationError, match="missing q_id"):
        score_retrieval.load_ranked_results(missing)

    malformed = tmp_path / "malformed.jsonl"
    malformed.write_text(json.dumps({"q_id": None}) + "\n", encoding="utf-8")
    records = score_retrieval.load_ranked_results(malformed)
    with pytest.raises(score_retrieval.EvaluationError, match="non-empty string"):
        score_retrieval.validate_ranked_results(records, {"Q01": "query"})


def test_scoring_is_byte_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_hashes = score_retrieval.run(
        scores_path=first / "scores.json",
        per_question_path=first / "per_question.csv",
        misses_path=first / "misses.csv",
    )
    second_hashes = score_retrieval.run(
        scores_path=second / "scores.json",
        per_question_path=second / "per_question.csv",
        misses_path=second / "misses.csv",
    )
    assert list(first_hashes.values()) == list(second_hashes.values())
    for path in ("scores.json", "per_question.csv", "misses.csv"):
        assert (first / path).read_bytes() == (second / path).read_bytes()


def test_scoring_does_not_mutate_frozen_bm25_result(tmp_path: Path) -> None:
    before = _sha256(FROZEN_RESULT)
    score_retrieval.run(
        scores_path=tmp_path / "scores.json",
        per_question_path=tmp_path / "per_question.csv",
        misses_path=tmp_path / "misses.csv",
    )
    after = _sha256(FROZEN_RESULT)
    assert before == after == "7e276b409b9bebafa3b31acc105d253f90595bf652e2936446995bd5ae6611e1"
