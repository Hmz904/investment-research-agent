"""Integrity checks for the finalized provenance gold map."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from evaluation import finalize_gold_provenance


pytestmark = pytest.mark.locked_test_data


ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "benchmark" / "provenance" / "gold"
EXPECTED_BINDING = {
    "benchmark_version": "bench_v0.1.1",
    "benchmark_tag": "bench_v0.1.1",
    "ingestion_tag": "ingestion_v0.1.1",
    "ingestion_git_commit": "63cabb2",
    "corpus_fingerprint": (
        "56df698d50b13cf15e913c1c60dbc96b1fd0fab44adb7b1f40ba99771c4b7c96"
    ),
}


def _load(name: str) -> dict:
    return json.loads((GOLD / name).read_text(encoding="utf-8"))


def test_gold_binding_is_exact_and_records_release_git_metadata() -> None:
    binding = _load("version_binding.json")
    for key, value in EXPECTED_BINDING.items():
        assert binding[key] == value
    assert binding["benchmark_release_git_tag"] == "bench_v0.1.1"
    assert binding["benchmark_release_git_commit"] == (
        "b0197d17018fe29d6863b7c35b572b3fa599059b"
    )


def test_all_numeric_and_evidence_mappings_have_approved_lineage() -> None:
    numeric = _load("numeric_fact_provenance.json")
    evidence = _load("evidence_provenance.json")

    assert numeric["fact_count"] == len(numeric["facts"]) == 71
    assert sum(len(fact["candidate_sources"]) for fact in numeric["facts"]) == 101
    for fact in numeric["facts"]:
        assert fact["reviewer_decision"] == "APPROVE"
        assert fact["review_lineage"]["decision"] == "APPROVE"
        assert all(
            source["reviewer_decision"] == "APPROVE"
            and source["mapping_review_decision_id"]
            for source in fact["candidate_sources"]
        )

    parts = [part for item in evidence["items"] for part in item["parts"]]
    assert evidence["verified_item_count"] == len(evidence["items"]) == 113
    assert len(parts) == 234
    assert sum(len(part["candidate_sources"]) for part in parts) == 246
    assert sum(len(part["candidate_sources"]) > 1 for part in parts) == 12
    assert all(item["reviewer_decision"] == "APPROVE" for item in evidence["items"])
    assert all(item["minimum_distinct_chunk_hits"] is not None for item in evidence["items"])
    for part in parts:
        assert part["candidate_sources"]
        assert part["reviewer_decision"] == "APPROVE"
        assert part["review_lineage"]["decision"] == "APPROVE"
        assert all(
            source["reviewer_decision"] == "APPROVE"
            and source["mapping_review_decision_id"]
            for source in part["candidate_sources"]
        )


def test_all_candidates_have_valid_non_orphaned_persistent_anchors() -> None:
    numeric = _load("numeric_fact_provenance.json")
    evidence = _load("evidence_provenance.json")
    anchors = _load("source_anchors.json")
    by_id = {anchor["anchor_id"]: anchor for anchor in anchors["anchors"]}
    candidates = [
        source for fact in numeric["facts"] for source in fact["candidate_sources"]
    ] + [
        source
        for item in evidence["items"]
        for part in item["parts"]
        for source in part["candidate_sources"]
    ]
    required = {
        "accession", "doc_id", "raw_document_sha256", "chunk_id", "char_start",
        "char_end", "normalized_source_fingerprint",
    }
    assert anchors["anchor_count"] == len(by_id) == 72
    assert all(anchor["validation_status"] == "VALID" for anchor in by_id.values())
    assert len(candidates) == 347
    for source in candidates:
        anchor = by_id[source["anchor_id"]]
        assert all(source[field] == anchor[field] for field in required)
    assert {source["anchor_id"] for source in candidates} == set(by_id)
    assert anchors["validation"] == {
        "numeric_candidate_references": 101,
        "evidence_candidate_references": 246,
        "candidate_references_with_valid_anchor": 347,
        "registered_source_anchors": 72,
        "orphan_anchors": 0,
        "dangling_anchor_references": 0,
    }


def test_final_review_and_merge_invariants() -> None:
    evidence = _load("evidence_provenance.json")
    reviews = _load("review_decisions.json")
    merges = _load("merge_lineage.json")
    summary = reviews["summary"]
    assert summary == {
        "original_review_rows": 302,
        "original_approvals": 290,
        "original_rejections_superseded": 12,
        "numeric_mapping_approvals": 71,
        "repair_review_rows": 12,
        "repair_approvals": 12,
        "repair_approved_final_evidence_mappings": 15,
        "final_evidence_mapping_approvals": 234,
        "merge_review_rows": 56,
        "merge_approvals": 56,
        "active_rejections": 0,
        "active_needs_source_check": 0,
    }
    active = [decision for decision in reviews["decisions"] if decision["active"]]
    assert not any(
        decision["decision"] in {"REJECT", "NEEDS_SOURCE_CHECK"}
        for decision in active
    )

    scoring_merges = [
        part
        for item in evidence["items"]
        for part in item["parts"]
        if len(part["source_atom_ids"]) > 1
    ]
    assert merges["merge_count"] == merges["approved_merge_count"] == 56
    assert len(scoring_merges) == 56
    assert all(part["human_approved_retrieval_merge"] for part in scoring_merges)
    assert all(part["merge_review_lineage"]["decision"] == "APPROVE" for part in scoring_merges)
    assert "pending human re-review" not in json.dumps(evidence).lower()
    assert "re-review is pending" not in json.dumps(merges).lower()


def test_manifest_hashes_and_fingerprint_are_deterministic(tmp_path: Path) -> None:
    manifest = _load("gold_manifest.json")
    assert set(manifest["artifacts"]) == set(finalize_gold_provenance.GOLD_ARTIFACTS)
    for name, metadata in manifest["artifacts"].items():
        content = (GOLD / name).read_bytes()
        assert hashlib.sha256(content).hexdigest() == metadata["sha256"]
        assert len(content) == metadata["bytes"]

    fingerprint_payload = dict(manifest)
    fingerprint = fingerprint_payload.pop("gold_map_fingerprint")
    assert hashlib.sha256(
        finalize_gold_provenance._canonical_json(fingerprint_payload)
    ).hexdigest() == fingerprint
    assert not ({"created_at", "generated_at", "timestamp"} & set(manifest))

    first = tmp_path / "first"
    second = tmp_path / "second"
    first_manifest = finalize_gold_provenance.run(first)
    second_manifest = finalize_gold_provenance.run(second)
    assert first_manifest["gold_map_fingerprint"] == second_manifest["gold_map_fingerprint"]
    assert {
        path.name: path.read_bytes() for path in first.iterdir()
    } == {
        path.name: path.read_bytes() for path in second.iterdir()
    }
