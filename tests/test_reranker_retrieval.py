"""Gold-blind tests for deterministic frozen-union cross-encoder reranking."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from src.reranker_retrieval import (
    MAX_LENGTH,
    MODEL_ID,
    MODEL_REVISION,
    PairScore,
    add_hybrid_ranks,
    build_candidate_union,
    rank_scored_candidates,
    sha256_file,
)


def _candidate(chunk_id: str, rank: int, **metadata: object) -> dict[str, object]:
    return {
        "rank": rank,
        "score": float(100 - rank),
        "chunk_id": chunk_id,
        "doc_id": metadata.pop("doc_id", f"DOC-{chunk_id}"),
        "accession": metadata.pop("accession", f"ACC-{chunk_id}"),
        "chunk_text": metadata.pop("chunk_text", f"Text {chunk_id}"),
        "retrieval_text": metadata.pop("retrieval_text", f"Passage {chunk_id}"),
        **metadata,
    }


def _record(
    candidates: list[dict[str, object]],
    *,
    q_id: str = "Q01",
    query_en: str = "authoritative frozen query",
) -> dict[str, object]:
    return {
        "q_id": q_id,
        "query_en": query_en,
        "corpus_fingerprint": "corpus",
        "ranked_results": candidates,
    }


def _score(chunk_id: str, value: float) -> PairScore:
    return PairScore(
        chunk_id=chunk_id,
        score=value,
        original_token_count=10,
        retained_token_count=10,
        original_passage_token_count=5,
        retained_passage_token_count=5,
        passage_truncated=False,
    )


def test_candidate_union_deduplicates_and_preserves_provenance() -> None:
    bm25 = _record([_candidate("both", 1), _candidate("bm25-only", 2)])
    embedding = _record(
        [_candidate("embedding-only", 1), _candidate("both", 2)]
    )
    union = build_candidate_union(bm25, embedding, expected_depth=2)
    by_id = {candidate["chunk_id"]: candidate for candidate in union}

    assert set(by_id) == {"both", "bm25-only", "embedding-only"}
    assert by_id["both"]["bm25_rank"] == 1
    assert by_id["both"]["embedding_rank"] == 2
    assert by_id["bm25-only"]["embedding_rank"] is None
    assert by_id["embedding-only"]["bm25_rank"] is None
    assert all(
        candidate["bm25_rank"] is not None
        or candidate["embedding_rank"] is not None
        for candidate in union
    )


def test_duplicate_chunk_within_component_is_rejected() -> None:
    bm25 = _record([_candidate("same", 1), _candidate("same", 2)])
    embedding = _record([_candidate("a", 1), _candidate("b", 2)])
    with pytest.raises(ValueError, match="duplicate BM25 chunk_id"):
        build_candidate_union(bm25, embedding, expected_depth=2)


def test_immutable_candidate_conflict_is_rejected() -> None:
    bm25 = _record([_candidate("same", 1, doc_id="FIRST")])
    embedding = _record([_candidate("same", 1, doc_id="SECOND")])
    with pytest.raises(ValueError, match="metadata conflict.*doc_id"):
        build_candidate_union(bm25, embedding, expected_depth=1)


def test_query_integrity_and_component_identity_are_required() -> None:
    bm25 = _record([_candidate("a", 1)])
    embedding = _record([_candidate("b", 1)], query_en="rewritten query")
    with pytest.raises(ValueError, match="query_en mismatch"):
        build_candidate_union(bm25, embedding, expected_depth=1)


def test_stable_tie_break_and_input_order_independence() -> None:
    candidates = [
        {**_candidate("z", 1), "bm25_rank": 1},
        {**_candidate("a", 2), "bm25_rank": 2},
        {**_candidate("middle", 3), "bm25_rank": 3},
    ]
    scores = [_score("middle", 2.0), _score("z", 1.0), _score("a", 1.0)]
    first = rank_scored_candidates(candidates, scores, top_k=3)
    second = rank_scored_candidates(
        list(reversed(candidates)), list(reversed(scores)), top_k=3
    )

    assert [item["chunk_id"] for item in first] == ["middle", "a", "z"]
    assert first == second
    assert [item["reranker_rank"] for item in first] == [1, 2, 3]


def test_no_duplicate_or_out_of_union_score_can_enter_output() -> None:
    candidates = [_candidate("a", 1), _candidate("b", 2)]
    with pytest.raises(ValueError, match="outside candidate union"):
        rank_scored_candidates(
            candidates,
            [_score("a", 2.0), _score("outside", 1.0)],
            top_k=2,
        )
    with pytest.raises(ValueError, match="duplicate score"):
        rank_scored_candidates(
            candidates,
            [_score("a", 2.0), _score("a", 1.0)],
            top_k=2,
        )


def test_exactly_fifty_unique_outputs_from_frozen_union() -> None:
    candidates = [_candidate(f"chunk-{index:03d}", index + 1) for index in range(75)]
    scores = [_score(str(item["chunk_id"]), float(index)) for index, item in enumerate(candidates)]
    ranked = rank_scored_candidates(candidates, scores, top_k=50)
    union_ids = {item["chunk_id"] for item in candidates}
    output_ids = [item["chunk_id"] for item in ranked]
    assert len(output_ids) == 50
    assert len(set(output_ids)) == 50
    assert set(output_ids) <= union_ids
    assert [item["reranker_rank"] for item in ranked] == list(range(1, 51))


def test_hybrid_rank_is_audit_only_and_outside_union_is_rejected() -> None:
    candidates = build_candidate_union(
        _record([_candidate("a", 1), _candidate("b", 2)]),
        _record([_candidate("b", 1), _candidate("c", 2)]),
        expected_depth=2,
    )
    hybrid = _record([_candidate("b", 1), _candidate("a", 2)])
    annotated = add_hybrid_ranks(
        candidates,
        hybrid,
        q_id="Q01",
        query_en="authoritative frozen query",
        corpus_fingerprint="corpus",
        expected_depth=2,
    )
    assert {item["chunk_id"]: item["hybrid_rank"] for item in annotated} == {
        "a": 2,
        "b": 1,
        "c": None,
    }
    outside = _record([_candidate("outside", 1)])
    with pytest.raises(ValueError, match="outside frozen union"):
        add_hybrid_ranks(
            candidates,
            outside,
            q_id="Q01",
            query_en="authoritative frozen query",
            corpus_fingerprint="corpus",
            expected_depth=1,
        )


def test_model_revision_metadata_is_present_and_pinned() -> None:
    assert MODEL_ID == "BAAI/bge-reranker-v2-m3"
    assert MODEL_REVISION == "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
    assert MAX_LENGTH == 1024


def test_production_source_has_no_gold_or_scoring_dependency() -> None:
    root = Path(__file__).resolve().parent.parent
    source = (root / "src" / "reranker_retrieval.py").read_text(encoding="utf-8")
    forbidden_fragments = (
        "score_" + "retrieval",
        "numeric_" + "answers",
        "evidence_" + "checklist",
        "benchmark/" + "provenance",
        "_scores." + "json",
        "_misses." + "csv",
    )
    assert all(fragment not in source for fragment in forbidden_fragments)


@pytest.mark.locked_test_data
def test_frozen_upstream_ranked_artifacts_remain_byte_identical() -> None:
    root = Path(__file__).resolve().parent.parent
    expected = {
        "bm25_v0.1.jsonl": "7e276b409b9bebafa3b31acc105d253f90595bf652e2936446995bd5ae6611e1",
        "embedding_v0.1.jsonl": "d997bb8ac72ba2e003eea440b0e805e3dd9722b053874162bee7d6754bc2bfa3",
        "hybrid_v0.1.jsonl": "17f2f07fd24163b443dd3909aaa81fd188a8dbef77786532d7eb432094769846",
    }
    for filename, digest in expected.items():
        assert sha256_file(root / "evaluation" / "results" / filename) == digest


def test_candidate_union_does_not_mutate_inputs() -> None:
    bm25 = _record([_candidate("a", 1)])
    embedding = _record([_candidate("a", 1)])
    before = copy.deepcopy((bm25, embedding))
    build_candidate_union(bm25, embedding, expected_depth=1)
    assert (bm25, embedding) == before
