"""Deterministic ingestion-v0.1.1 provenance rebuild tests."""

from __future__ import annotations

import hashlib
import csv
import json
from pathlib import Path

import pytest

from evaluation import build_provenance_repair_packet, provenance


ROOT = Path(__file__).resolve().parents[2]
PROV = ROOT / "benchmark" / "provenance"
EXPECTED_BINDING = {
    "ingestion_tag": "ingestion_v0.1.1",
    "ingestion_git_commit": "63cabb2",
    "corpus_fingerprint": (
        "56df698d50b13cf15e913c1c60dbc96b1fd0fab44adb7b1f40ba99771c4b7c96"
    ),
    "benchmark_version": "bench_v0.1.1",
    "benchmark_parent_version": "bench_v0.1",
    "benchmark_schema_version": "v0.1.2",
}
FROZEN_SHA256 = {
    "evidence_checklist.csv": "de6371765fa7d7f5ef729d1bb2c8ece3147de3e9031d6a0aabdc796002ce9ce7",
    "numeric_answers.csv": "a6b9b49c98ff6b3052bd43cfbc9ca1e10dccaf1ae64fea588b3945fdc4510ce1",
    "protocol.md": "a4d67d7b0e4a41e1c80d18188508ce2933fa518c7dafff601b9f5eb43c7f9eb3",
    "questions.csv": "8019db55145518a844eade8c02687bd7069d04de1ff428faa5337a6672c24dcd",
    "source_manifest.csv": "1513c62b3379639af91e1aae7e4193d725eefece494aa2c988bdf4b9b4c75916",
}


@pytest.fixture(scope="module")
def rebuilt() -> dict:
    return provenance.run()


def _load(name: str) -> dict:
    return json.loads((PROV / name).read_text(encoding="utf-8"))


def test_frozen_benchmark_is_byte_unchanged() -> None:
    for name, expected in FROZEN_SHA256.items():
        content = (ROOT / "benchmark" / "frozen" / name).read_bytes()
        assert hashlib.sha256(content).hexdigest() == expected


def test_fingerprint_gate_fails_loudly(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(
        json.dumps({"corpus_fingerprint": "wrong"}), encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="CORPUS FINGERPRINT MISMATCH"):
        provenance.version_binding(tmp_path)


def test_artifacts_exist_and_all_have_version_binding(rebuilt: dict) -> None:
    names = (
        "version_binding.json",
        "numeric_facts_draft.json",
        "evidence_provenance_draft.json",
        "source_anchors_draft.json",
        "source_contract_errors_draft.json",
        "source_anchor_coverage_draft.json",
        "unique_sample_defect_trace_draft.json",
        "provenance_rebuild_draft.json",
    )
    for name in names:
        payload = _load(name)
        binding = payload if name == "version_binding.json" else payload["version_binding"]
        for key, value in EXPECTED_BINDING.items():
            assert binding[key] == value
    assert (ROOT / "review" / "provenance_v011_rebuild.md").exists()
    assert (ROOT / "review" / "provenance_boundary_audit.md").exists()

    merge_rows = list(csv.DictReader((PROV / "merge_review_draft.csv").open()))
    assert merge_rows
    for row in merge_rows:
        for key, value in EXPECTED_BINDING.items():
            if key in row:
                assert row[key] == value
        assert row["reviewer_decision"] in {"", "APPROVE"}
        assert row["human_approved"] == str(
            row["reviewer_decision"] == "APPROVE"
        ).lower()
        assert row["reviewer_note"] == ""


def test_all_71_numeric_facts_have_deterministic_provenance(rebuilt: dict) -> None:
    facts = rebuilt["numeric"]["facts"]
    assert len(facts) == 71
    assert len({fact["fact_id"] for fact in facts}) == 71
    assert sum(not fact["is_derived"] for fact in facts) == 46
    assert sum(fact["is_derived"] for fact in facts) == 25
    assert {fact["status"] for fact in facts} == {
        "direct_unique", "direct_or", "derived"
    }
    for fact in facts:
        assert fact["candidate_sources"], fact["fact_id"]
        assert fact["reviewer_decision"] == ""
        assert fact["reviewer_note"] == ""


def test_authoritative_review_invariants_and_repair_packet(rebuilt: dict) -> None:
    rows = build_provenance_repair_packet.build()
    assert len(rows) == 12
    assert {_key for _key in (
        (row["q_id"], row["q_version"], row["item_id"], row["old_part_id"])
        for row in rows
    )} == build_provenance_repair_packet.REPAIR_KEYS
    assert all(row["reviewer_decision"] == "" for row in rows)
    assert sum(row["newly_split"] for row in rows) == 3

    reviewed_evidence, reviewed_numeric = (
        build_provenance_repair_packet._authoritative_rows()
    )
    decisions = [
        row["reviewer_decision"] for row in reviewed_evidence + reviewed_numeric
    ]
    assert len(decisions) == 302
    assert decisions.count("APPROVE") == 290
    assert decisions.count("REJECT") == 12
    assert decisions.count("NEEDS_SOURCE_CHECK") == 0
    assert len(reviewed_numeric) == 71


def test_xbrl_facts_carry_full_identity(rebuilt: dict) -> None:
    xbrl_facts = [
        fact for fact in rebuilt["numeric"]["facts"]
        if fact["source_identity"]["type"] == "xbrl"
    ]
    assert {fact["fact_id"] for fact in xbrl_facts} == {"F009", "F010", "F011", "F071"}
    required = {
        "accession", "concept", "dimensions", "members", "scaled_value",
        "period_start", "period_end", "instant_date", "unit", "unit_measures",
    }
    for fact in xbrl_facts:
        for candidate in fact["candidate_sources"]:
            identities = candidate["table_identity"]["xbrl_facts"]
            assert identities
            assert required <= identities[0].keys()
            assert fact["source_identity"]["expected_concept"] in identities[0]["concept"]


def test_table_facts_carry_cell_identity(rebuilt: dict) -> None:
    table_facts = [
        fact for fact in rebuilt["numeric"]["facts"]
        if fact["source_identity"]["type"] == "table"
    ]
    assert len(table_facts) == 36
    required = {
        "raw_text", "parsed_value", "row_label", "effective_column_label",
        "period_start", "period_end", "duration_months", "unit", "unit_scale",
    }
    for fact in table_facts:
        for candidate in fact["candidate_sources"]:
            cells = candidate["table_identity"]["table_cells"]
            assert cells, (fact["fact_id"], candidate["chunk_id"])
            assert required <= cells[0].keys()
            assert "table_title" in candidate
            assert candidate["section_path"]


def test_derived_fact_provenance_is_exact_input_union(rebuilt: dict) -> None:
    by_id = {fact["fact_id"]: fact for fact in rebuilt["numeric"]["facts"]}
    for fact in by_id.values():
        if not fact["is_derived"]:
            continue
        expected = []
        for input_id in fact["input_fact_ids"]:
            for chunk_id in by_id[input_id]["candidate_chunk_ids"]:
                if chunk_id not in expected:
                    expected.append(chunk_id)
        assert fact["candidate_chunk_ids"] == expected
        assert fact["formula"]


def test_cash_ppe_sign_semantics_are_explicit(rebuilt: dict) -> None:
    cash_ppe = [
        fact for fact in rebuilt["numeric"]["facts"]
        if not fact["is_derived"] and fact["basis"] == "cash_ppe"
    ]
    assert cash_ppe
    for fact in cash_ppe:
        assert fact["sign_semantics"]["benchmark_value_convention"] == "positive_economic_magnitude"
    assert any(
        display["display_is_negative"]
        for fact in cash_ppe
        for display in fact["sign_semantics"]["source_displays"]
    )


def test_evidence_has_explicit_and_or_structure(rebuilt: dict) -> None:
    items = rebuilt["evidence"]["items"]
    assert len(items) == 113
    assert sum(item["part_count"] for item in items) == 234
    assert {item["parts_operator"] for item in items} == {"AND"}
    for item in items:
        assert item["parts"]
        assert item["part_count"] == len(item["parts"])
        assert item["reviewer_decision"] == ""
        assert item["reviewer_note"] == ""
        for part in item["parts"]:
            assert part["candidates_operator"] == "OR"
            assert part["source_atom_ids"]
            assert part["reviewer_decision"] == ""
            assert part["reviewer_note"] == ""


def test_merge_lineage_is_complete_and_repaired_rows_are_blank(rebuilt: dict) -> None:
    review = rebuilt["merge_review"]
    assert review["summary"] == {
        "merge_groups": 56,
        "old_parts_affected": 126,
        "new_parts_produced": 56,
        "part_count_reduction": 70,
    }
    assert len(review["rows"]) == 56
    assert sum(row["reviewer_decision"] == "APPROVE" for row in review["rows"]) == 50
    assert sum(row["reviewer_decision"] == "" for row in review["rows"]) == 6
    for row in review["rows"]:
        if row["reviewer_decision"] == "APPROVE":
            assert row["merge_lineage"] == "B. copied/applied from a previous merge proposal"
            assert row["human_approved"] is True
        else:
            assert row["merge_lineage"] == "C. repaired after human provenance review"
            assert row["human_approved"] is False
        assert row["reviewer_note"] == ""
        assert "idempotence" in row["logical_equivalence"]
        assert row["number_of_parts_reduced"] == len(row["old_part_ids"].split(";")) - 1


def test_minimum_distinct_hits_follow_and_or_sets(rebuilt: dict) -> None:
    for item in rebuilt["evidence"]["items"]:
        assert item["minimum_distinct_chunk_hits"] == provenance._minimum_distinct_hits(item["parts"])
    distribution = {
        value: sum(item["minimum_distinct_chunk_hits"] == value for item in rebuilt["evidence"]["items"])
        for value in (None, 1, 2, 3, 4, 5, 6)
    }
    assert distribution == {None: 0, 1: 41, 2: 53, 3: 7, 4: 6, 5: 1, 6: 5}


def test_every_candidate_has_persistent_anchor(rebuilt: dict) -> None:
    anchors = rebuilt["anchors"]["anchors"]
    by_id = {anchor["anchor_id"]: anchor for anchor in anchors}
    required = {
        "accession", "doc_id", "raw_document_sha256", "chunk_id",
        "char_start", "char_end", "normalized_source_fingerprint",
    }
    assert rebuilt["anchors"]["anchor_count"] == 72
    for anchor in anchors:
        assert required <= anchor.keys()
        assert len(anchor["raw_document_sha256"]) == 64
        assert len(anchor["normalized_source_fingerprint"]) == 64
        assert anchor["char_start"] < anchor["char_end"]

    candidates = [
        source
        for fact in rebuilt["numeric"]["facts"]
        for source in fact["candidate_sources"]
    ] + [
        source
        for item in rebuilt["evidence"]["items"]
        for part in item["parts"]
        for source in part["candidate_sources"]
    ]
    for source in candidates:
        anchor = by_id[source["anchor_id"]]
        for field in required:
            assert source[field] == anchor[field]


def test_candidate_level_anchor_coverage_is_complete(rebuilt: dict) -> None:
    counts = rebuilt["anchor_coverage"]["counts"]
    assert counts == {
        "total_provenance_candidate_references": 347,
        "contract_diagnostic_source_references": 8,
        "unique_chunk_ids_referenced_by_candidates": 72,
        "unique_source_anchor_ids_referenced_by_candidates": 72,
        "registered_source_anchors": 72,
        "candidate_references_with_valid_anchor": 347,
        "candidate_references_without_anchor": 0,
        "candidate_references_with_anchor_mismatch": 0,
        "orphan_anchors": 0,
        "dangling_anchor_references": 0,
        "normalized_source_fingerprint_collisions_with_different_spans": 0,
    }
    assert rebuilt["anchor_coverage"]["candidate_references_without_anchor"] == []
    assert rebuilt["anchor_coverage"]["candidate_anchor_mismatches"] == []
    assert rebuilt["anchor_coverage"]["orphan_anchor_ids"] == []
    assert rebuilt["anchor_coverage"]["dangling_anchor_ids"] == []


def test_table_anchors_include_context_and_attached_footnotes(rebuilt: dict) -> None:
    table_anchors = [anchor for anchor in rebuilt["anchors"]["anchors"] if anchor["table_title"]]
    assert table_anchors
    for anchor in table_anchors:
        assert "row_label" in anchor
        assert "effective_column_label" in anchor
        assert "section_path" in anchor
    assert sum(bool(anchor["attached_footnotes"]) for anchor in table_anchors) == 3


def test_four_contract_errors_are_resolved_by_release_errata(rebuilt: dict) -> None:
    result = rebuilt["contract_errors"]
    assert result["error_count"] == 0
    assert result["errors"] == []
    resolved = result["resolved_errors"]
    assert {(e["q_id"], e["item_id"]) for e in resolved} == {
        ("Q02", "E05"), ("Q05", "X3"), ("Q05", "X4"), ("Q12", "E07")
    }
    for error in resolved:
        assert error["remains_genuine_frozen_benchmark_contract_error"] is False
        assert error["release_contract_satisfied"] is True
        assert set(error["actual_required_source_accessions"]) <= set(
            error["release_accession_contract"]
        )
        assert error["required_semantic_part"]
        assert error["relevant_source_text"]
        assert error["required_sources"]
        assert error["why_parent_frozen_contract_was_unsatisfiable"]
        assert error["non_source_fields_need_correction"] is False


def test_previous_unique_sample_defects_are_traced(rebuilt: dict) -> None:
    traces = {
        (trace["q_id"], trace["item_id"]): trace
        for trace in rebuilt["defect_trace"]["traces"]
    }
    assert set(traces) == {("Q05", "X3"), ("Q16", "E09"), ("Q10", "C2")}
    assert traces[("Q05", "X3")]["current_status"] == "supported"
    assert traces[("Q16", "E09")]["current_status"] == "supported"
    assert traces[("Q10", "C2")]["current_status"] == "supported"
    assert "not dropped" in traces[("Q16", "E09")]["resolution"]
    assert "not dropped" in traces[("Q10", "C2")]["resolution"]
    assert [part["candidate_chunk_ids"] for part in traces[("Q16", "E09")]["current_mapping"]] == [
        ["3e9b386d72ec488d"], ["66a2dbe9fa036e7f"], ["6e776edb42ae8862"]
    ]
    assert traces[("Q10", "C2")]["current_mapping"][0]["candidate_chunk_ids"] == [
        "0d90ceeeffa01abc"
    ]


def test_review_preserves_required_sections() -> None:
    review = (ROOT / "review" / "provenance_v011_rebuild.md").read_text(encoding="utf-8")
    for heading in (
        "## Totals",
        "## Part-count distribution",
        "## OR-candidate counts",
        "## Minimum distinct chunk hits per evidence item",
        "## Source-contract errors",
        "## Missing or unresolved items",
        "## Differences from the previous draft",
    ):
        assert heading in review
    boundary_review = (ROOT / "review" / "provenance_boundary_audit.md").read_text(
        encoding="utf-8"
    )
    for heading in (
        "## Merge lineage",
        "## Production/evaluation boundary",
        "## Source-anchor coverage",
        "## Previous unique-sample defects",
        "## Contract errors in full",
        "## Remaining blockers",
    ):
        assert heading in boundary_review
