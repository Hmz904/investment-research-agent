from __future__ import annotations

import copy

import pytest

from evaluation.temporal_context_catalog import (
    DETERMINISTICALLY_DERIVED,
    DIRECTLY_OBSERVED_CONTEXT,
    EVALUATOR_CANNOT_REPRESENT,
    MERGED_AGREEING_EVIDENCE,
    NEEDS_HUMAN_CLOSED_SET,
    RESOLVED_ANCHOR_METADATA,
    RESOLVED_EXACT_TARGET_DATE,
    RESOLVED_HUMAN_CLOSED_SET,
    TEMPORAL_HUMAN_SELECT_NONE,
    TEMPORAL_NO_ANCHOR_METADATA,
    TEMPORAL_EVIDENCE_TYPES,
    UNMAPPABLE_REASON_CODES,
    UNRESOLVED_NO_CANDIDATE,
    build_temporal_catalog,
    resolve_target_temporal,
    table_temporal,
    target_specific_candidate_rows,
    validate_reviewer_selection,
)
from evaluation.xbrl_mapping import (
    SOURCE_CHECK_PASS,
    candidate_matches_temporal,
    generate_stage3,
    provisional_direct_status,
    temporal_precedence_direct_status,
)


def _fact(suffix: str, *, start: str = "2026-01-01", end: str = "2026-03-31", dimensions=None):
    return {
        "stable_fact_id": f"DOC::{suffix}", "fact_id": suffix, "doc_id": "DOC",
        "concept": "us-gaap:Revenue", "raw_value": "1", "normalized_value": "1",
        "unit": "usd", "unit_measures": ["iso4217:USD"], "unit_numerator": [],
        "unit_denominator": [], "context_ref": f"ctx-{suffix}", "period_type": "duration",
        "instant": None, "period_start": start, "period_end": end,
        "dimensions": [] if dimensions is None else dimensions,
        "accession": "0000000001-26-000001", "company": "Synthetic", "cik": "1",
        "form_type": "10-Q", "filing_date": "2026-04-01", "period_of_report": end,
        "filing_fiscal_period": "Q1", "calendar_period": "2026Q1",
        "chunk_id": "chunk-1", "fact_locator": f"DOC#{suffix}",
        "decimals": "0", "scale": 0, "sign": None, "is_negative": False,
        "namespace_prefix": "us-gaap", "local_name": "Revenue", "duration_days": 89,
        "entity_identifier": "1", "entity_scheme": "scheme", "source_role": "fixture",
        "doc_role": "primary",
    }


def _manifest():
    return [{
        "doc_id": "DOC", "accession": "0000000001-26-000001", "company": "Synthetic",
        "cik": "1", "form": "10-Q", "filing_date": "2026-04-01",
        "period_of_report": "2026-03-31",
    }]


def _catalog_rows(rows):
    return {"rows": rows, "conflicts": []}


def _table_row(row_id: str, temporal: dict[str, str]):
    return {
        "temporal_row_id": row_id, "entity": "Synthetic", "accession": "0000000001-26-000001",
        "temporal": temporal, "temporal_evidence_type": "DETERMINISTICALLY_DERIVED",
        "generation_rule_id": "table_cell_exact_period_v0.1",
        "source_metadata_identities": {"chunk_ids": ["chunk-1"], "table_identity": {"table_column": 1}},
        "evidence_fingerprints": ["a" * 64],
    }


def _linked_fact(
    suffix: str,
    *,
    start: str = "2026-01-01",
    end: str = "2026-03-31",
    dimensions=None,
):
    return {
        "fact_id": suffix,
        "concept": "us-gaap:Revenue",
        "context_id": f"ctx-{suffix}",
        "period_start": start,
        "period_end": end,
        "instant_date": None,
        "dimensions": [] if dimensions is None else dimensions,
    }


def _table_document(period: dict, linked_facts=None):
    cell = {
        "col": 1,
        "row_label": "Revenue",
        "column_label": "Synthetic period",
        "parsed_value": 1,
        "period_start": period.get("period_start"),
        "period_end": period.get("period_end"),
        "instant_date": period.get("instant_date"),
        "duration_months": period.get("duration_months"),
        "period_resolution_source": period.get("period_resolution_source"),
        "period_resolution_context_id": period.get("period_resolution_context_id"),
        "xbrl_facts": list(linked_facts or []),
    }
    return [{
        "doc_id": "DOC",
        "accession": "0000000001-26-000001",
        "chunks": [{
            "doc_id": "DOC",
            "accession": "0000000001-26-000001",
            "chunk_id": "chunk-1",
            "table_json": {"rows": [{"cells": [cell]}]},
        }],
    }]


def _table_catalog(period: dict, linked_facts=None):
    return build_temporal_catalog(
        [],
        _manifest(),
        _table_document(period, linked_facts),
        xbrl_artifact_fingerprint="a" * 64,
        corpus_fingerprint="b" * 64,
    )


def _target(**updates):
    target = {
        "target_id": "T", "entity_company": "Synthetic", "approved_chunk_ids": ["chunk-1"],
        "source_accessions": ["0000000001-26-000001"], "gold_xbrl_concept": None,
        "temporal_requirement": {"kind": "unresolved"},
    }
    target.update(updates)
    return target


def test_exact_date_priority_over_conflicting_anchor() -> None:
    facts = [_fact("a"), _fact("b", start="2025-01-01", end="2025-03-31")]
    result = resolve_target_temporal(
        _target(gold_xbrl_concept="us-gaap:Revenue", temporal_requirement={"kind": "duration", "period_start": "2024-01-01", "period_end": "2024-03-31"}),
        _catalog_rows([]), facts,
    )
    assert result["temporal_resolution_status"] == RESOLVED_EXACT_TARGET_DATE
    assert result["resolved_temporal"]["period_start"] == "2024-01-01"


def test_anchor_table_temporal_resolution() -> None:
    temporal = {"kind": "duration", "period_start": "2026-01-01", "period_end": "2026-03-31"}
    result = resolve_target_temporal(_target(), _catalog_rows([_table_row("TCR-one", temporal)]), [])
    assert result["temporal_resolution_status"] == RESOLVED_ANCHOR_METADATA
    assert result["temporal_resolution_mode"] == "ANCHOR_TABLE_PERIOD"


def test_anchor_xbrl_context_resolution() -> None:
    result = resolve_target_temporal(_target(gold_xbrl_concept="us-gaap:Revenue"), _catalog_rows([]), [_fact("a")])
    assert result["temporal_resolution_status"] == RESOLVED_ANCHOR_METADATA
    assert result["temporal_resolution_mode"] == "ANCHOR_XBRL_CONTEXT"


def test_conflicting_anchor_periods_are_ambiguous() -> None:
    facts = [_fact("a"), _fact("b", start="2025-01-01", end="2025-03-31")]
    rows = [
        _table_row("TCR-one", {"kind": "duration", "period_start": "2026-01-01", "period_end": "2026-03-31"}),
        _table_row("TCR-two", {"kind": "duration", "period_start": "2025-01-01", "period_end": "2025-03-31"}),
    ]
    result = resolve_target_temporal(
        _target(gold_xbrl_concept="us-gaap:Revenue"), _catalog_rows(rows), facts
    )
    assert result["temporal_resolution_status"] == NEEDS_HUMAN_CLOSED_SET
    assert [candidate["temporal"] for candidate in result["candidate_rows"]] == [
        {"kind": "duration", "period_end": "2025-03-31", "period_start": "2025-01-01"},
        {"kind": "duration", "period_end": "2026-03-31", "period_start": "2026-01-01"},
    ]
    selected_id = result["candidate_rows"][1]["temporal_candidate_id"]
    selected = resolve_target_temporal(
        _target(gold_xbrl_concept="us-gaap:Revenue"),
        _catalog_rows(rows),
        facts,
        reviewer_selection=f"SELECT {selected_id}",
    )
    assert selected["temporal_resolution_status"] == RESOLVED_HUMAN_CLOSED_SET
    assert selected["selected_temporal_candidate_id"] == selected_id


def test_human_readable_period_label_is_never_machine_input() -> None:
    result = resolve_target_temporal(
        _target(gold_period_label="FY99Q4_single_quarter"), _catalog_rows([]), []
    )
    assert result["temporal_resolution_status"] == UNRESOLVED_NO_CANDIDATE
    assert result["human_readable_period_labels_used"] is False


def test_target_specific_closed_candidate_set_and_reviewer_contract() -> None:
    rows = [
        _table_row("TCR-one", {"kind": "duration", "period_start": "2026-01-01", "period_end": "2026-03-31"}),
        _table_row("TCR-two", {"kind": "duration", "period_start": "2025-01-01", "period_end": "2025-03-31"}),
        {**_table_row("TCR-other", {"kind": "instant", "instant": "2026-03-31"}), "entity": "Other"},
    ]
    pending = resolve_target_temporal(_target(), _catalog_rows(rows), [])
    assert pending["temporal_resolution_status"] == NEEDS_HUMAN_CLOSED_SET
    candidate_ids = [item["temporal_candidate_id"] for item in pending["candidate_rows"]]
    assert {row_id for item in pending["candidate_rows"] for row_id in item["contributing_temporal_row_ids"]} == {"TCR-one", "TCR-two"}
    with pytest.raises(ValueError):
        resolve_target_temporal(_target(), _catalog_rows(rows), [], reviewer_selection="2026-03-31")
    with pytest.raises(ValueError):
        validate_reviewer_selection("SELECT TCR-other", candidate_ids)
    assert validate_reviewer_selection("SELECT NONE", candidate_ids) is None
    selected = resolve_target_temporal(
        _target(), _catalog_rows(rows), [], reviewer_selection=f"SELECT {candidate_ids[0]}"
    )
    assert selected["temporal_resolution_status"] == RESOLVED_HUMAN_CLOSED_SET
    none = resolve_target_temporal(
        _target(), _catalog_rows(rows), [], reviewer_selection="SELECT NONE"
    )
    assert none["unmappable_reason_code"] == TEMPORAL_HUMAN_SELECT_NONE


def test_no_candidate_set_fails_closed() -> None:
    result = resolve_target_temporal(_target(), _catalog_rows([]), [])
    assert result["temporal_resolution_status"] == UNRESOLVED_NO_CANDIDATE
    assert result["unmappable_reason_code"] == TEMPORAL_NO_ANCHOR_METADATA
    assert UNMAPPABLE_REASON_CODES == {
        TEMPORAL_NO_ANCHOR_METADATA,
        TEMPORAL_HUMAN_SELECT_NONE,
        EVALUATOR_CANNOT_REPRESENT,
    }


def test_temporal_evidence_enum_and_catalog_determinism() -> None:
    fact = _fact("a")
    forward = build_temporal_catalog([fact], _manifest(), [], xbrl_artifact_fingerprint="a" * 64, corpus_fingerprint="b" * 64)
    reverse = build_temporal_catalog(list(reversed([fact])), list(reversed(_manifest())), [], xbrl_artifact_fingerprint="a" * 64, corpus_fingerprint="b" * 64)
    assert forward == reverse
    assert forward["rows"][0]["temporal_evidence_type"] == DIRECTLY_OBSERVED_CONTEXT
    assert {row["temporal_evidence_type"] for row in forward["rows"]} <= TEMPORAL_EVIDENCE_TYPES


@pytest.mark.parametrize(
    ("months", "end", "expected_start"),
    [
        (3, "2026-06-30", "2026-04-01"),
        (6, "2026-06-30", "2026-01-01"),
        (9, "2026-09-30", "2026-01-01"),
    ],
)
def test_fixed_calendar_answers_require_explicit_start(
    months: int, end: str, expected_start: str
) -> None:
    month_only, rule = table_temporal(
        {"period_end": end, "duration_months": months}, ["header"]
    )
    assert month_only is None and rule is None
    explicit, rule = table_temporal(
        {"period_start": expected_start, "period_end": end}, ["header_explicit"]
    )
    assert explicit == {
        "kind": "duration", "period_start": expected_start, "period_end": end
    }
    assert rule == "table_cell_exact_period_v0.1"


def test_month_only_metadata_generates_no_authoritative_catalog_row() -> None:
    catalog = _table_catalog(
        {
            "period_start": None,
            "period_end": "2026-06-30",
            "duration_months": 3,
            "period_resolution_source": "header",
        }
    )
    assert catalog["rows"] == []
    assert catalog["table_period_provenance_audit"]["prior_month_only_rows_removed"] == 1


def test_ingestion_inferred_period_cannot_masquerade_as_explicit() -> None:
    catalog = _table_catalog(
        {
            "period_start": "2026-04-01",
            "period_end": "2026-06-30",
            "duration_months": 3,
            "period_resolution_source": "xbrl_context",
            "period_resolution_context_id": "ctx-derived",
        }
    )
    assert catalog["rows"] == []
    audit = catalog["table_period_provenance_audit"]
    assert audit["prior_table_cell_exact_period_classification"]["INGESTION_DERIVED_OR_INFERRED"] == 1
    assert audit["prior_table_cell_exact_period_removed_fail_closed"] == 1


def test_explicit_exact_table_period_remains_authoritative() -> None:
    catalog = _table_catalog(
        {
            "period_start": "2026-04-01",
            "period_end": "2026-06-30",
            "duration_months": 3,
            "period_resolution_source": "header_explicit",
        }
    )
    assert len(catalog["rows"]) == 1
    row = catalog["rows"][0]
    assert row["temporal_evidence_type"] == DETERMINISTICALLY_DERIVED
    assert row["generation_rule_id"] == "table_cell_exact_period_v0.1"


def test_inferred_table_period_plus_agreeing_xbrl_produces_merged_evidence() -> None:
    exact = _linked_fact("agree", start="2026-04-01", end="2026-06-30")
    catalog = _table_catalog(
        {
            "period_start": "2026-04-01",
            "period_end": "2026-06-30",
            "duration_months": 3,
            "period_resolution_source": "xbrl_context",
        },
        [exact],
    )
    assert len(catalog["rows"]) == 1
    row = catalog["rows"][0]
    assert row["temporal_evidence_type"] == MERGED_AGREEING_EVIDENCE
    assert row["generation_rule_id"] == "table_xbrl_agreement_v0.1"


def test_inferred_table_period_plus_disagreeing_xbrl_fails_closed() -> None:
    catalog = _table_catalog(
        {
            "period_start": "2026-04-01",
            "period_end": "2026-06-30",
            "duration_months": 3,
            "period_resolution_source": "xbrl_context",
        },
        [_linked_fact("conflict", start="2026-01-01", end="2026-06-30")],
    )
    assert catalog["rows"] == []
    assert [item["reason"] for item in catalog["conflicts"]] == [
        "table period conflicts with linked XBRL context"
    ]


def test_explicit_52_53_week_xbrl_dates_are_preserved_without_month_arithmetic() -> None:
    exact = _linked_fact("retail", start="2026-01-26", end="2026-04-26")
    catalog = _table_catalog(
        {
            "period_start": None,
            "period_end": "2026-04-26",
            "duration_months": 3,
            "period_resolution_source": "header",
        },
        [exact],
    )
    assert catalog["rows"][0]["temporal"] == {
        "kind": "duration", "period_start": "2026-01-26", "period_end": "2026-04-26"
    }
    assert catalog["rows"][0]["temporal_evidence_type"] == MERGED_AGREEING_EVIDENCE


def test_linked_dimension_disagreement_fails_closed_instead_of_becoming_empty() -> None:
    dimensions_a = [{"axis": "example:Axis", "member": "example:A"}]
    dimensions_b = [{"axis": "example:Axis", "member": "example:B"}]
    catalog = _table_catalog(
        {
            "period_start": "2026-01-01",
            "period_end": "2026-03-31",
            "duration_months": 3,
            "period_resolution_source": "xbrl_fact",
        },
        [
            _linked_fact("a", dimensions=dimensions_a),
            _linked_fact("b", dimensions=dimensions_b),
        ],
    )
    assert catalog["rows"] == []
    assert [item["reason"] for item in catalog["conflicts"]] == [
        "linked XBRL contexts disagree on dimensions"
    ]


def test_agreeing_temporal_candidates_aggregate_all_provenance_deterministically() -> None:
    temporal = {"kind": "duration", "period_start": "2026-01-01", "period_end": "2026-03-31"}
    first = _table_row("TCR-a", temporal)
    second = {
        **_table_row("TCR-b", temporal),
        "temporal_evidence_type": "MERGED_AGREEING_EVIDENCE",
        "generation_rule_id": "table_xbrl_agreement_v0.1",
        "source_metadata_identities": {
            "chunk_ids": ["chunk-1"], "table_identity": {"table_column": 2}
        },
        "evidence_fingerprints": ["b" * 64],
    }
    forward = target_specific_candidate_rows(_target(), _catalog_rows([first, second]))
    reverse = target_specific_candidate_rows(_target(), _catalog_rows([second, first]))
    assert forward == reverse
    assert len(forward) == 1
    candidate = forward[0]
    assert candidate["contributing_temporal_row_ids"] == ["TCR-a", "TCR-b"]
    assert candidate["evidence_fingerprints"] == ["a" * 64, "b" * 64]
    assert candidate["temporal_evidence_types"] == [
        "DETERMINISTICALLY_DERIVED", "MERGED_AGREEING_EVIDENCE"
    ]
    assert candidate["generation_rule_ids"] == [
        "table_cell_exact_period_v0.1", "table_xbrl_agreement_v0.1"
    ]


def test_stage3_and_no_xbrl_finalization_require_exact_completed_search() -> None:
    target = {
        **_target(), "gold_value": "1", "gold_unit": "USD",
        "precision": {"rule_id": "precision_exact_v0.1", "comparison_gold_value": "1"},
        "dimensional_requirement": {"availability": "exact", "dimensions": []},
        "stage3_eligible_accessions": ["0000000001-26-000001"],
    }
    candidates, state = generate_stage3(target, [_fact("a")], [])
    assert candidates == [] and state == "blocked_missing_exact_temporal_requirement"
    assert provisional_direct_status([], state) == "PROPOSED_UNMAPPABLE"
    assert provisional_direct_status([], "completed") == "PROPOSED_NO_XBRL_COUNTERPART_IN_FROZEN_CORPUS"


def test_stage1_discovery_cannot_finalize_before_temporal_binding() -> None:
    candidate = {"source_check_status": SOURCE_CHECK_PASS, "fact": _fact("a")}
    target = {
        **_target(), "gold_value": "1", "gold_unit": "USD",
        "precision": {"rule_id": "precision_exact_v0.1", "comparison_gold_value": "1"},
        "stage3_eligible_accessions": ["0000000001-26-000001"],
    }
    candidates, state = generate_stage3(target, [_fact("a")], [candidate])
    assert candidates == [] and state == "blocked_missing_exact_temporal_requirement"
    assert temporal_precedence_direct_status(
        [candidate], state,
        temporal_resolution_status=NEEDS_HUMAN_CLOSED_SET,
        resolved_temporal=None,
        unmappable_reason_code=None,
    ) == "PENDING_TEMPORAL_ADJUDICATION"


def test_bound_temporal_must_match_candidate_context_before_mapping() -> None:
    candidate = {"source_check_status": SOURCE_CHECK_PASS, "fact": _fact("a")}
    matching = {"kind": "duration", "period_start": "2026-01-01", "period_end": "2026-03-31"}
    mismatch = {"kind": "duration", "period_start": "2025-01-01", "period_end": "2025-03-31"}
    assert candidate_matches_temporal(candidate, matching)
    assert not candidate_matches_temporal(candidate, mismatch)
    assert temporal_precedence_direct_status(
        [candidate], "not_applicable_target_resolved_by_passing_candidate",
        temporal_resolution_status=RESOLVED_HUMAN_CLOSED_SET,
        resolved_temporal=matching,
        unmappable_reason_code=None,
    ) == "PROPOSED_MAPPED"
    assert temporal_precedence_direct_status(
        [candidate], "blocked_missing_exact_temporal_requirement",
        temporal_resolution_status=RESOLVED_HUMAN_CLOSED_SET,
        resolved_temporal=mismatch,
        unmappable_reason_code=None,
    ) != "PROPOSED_MAPPED"


def test_dimensional_stage3_behavior() -> None:
    dimension = [{"axis": "example:Axis", "member": "example:Member"}]
    fact = _fact("d", dimensions=dimension)
    target = {
        **_target(approved_chunk_ids=[]), "gold_value": "1", "gold_unit": "USD",
        "gold_xbrl_concept": "us-gaap:Revenue",
        "precision": {"rule_id": "precision_exact_v0.1", "comparison_gold_value": "1"},
        "temporal_requirement": {"kind": "duration", "period_start": "2026-01-01", "period_end": "2026-03-31"},
        "dimensional_requirement": {"availability": "exact", "dimensions": dimension},
        "stage3_eligible_accessions": [fact["accession"]],
    }
    candidates, state = generate_stage3(target, [fact], [])
    assert state == "completed"
    assert [item["fact_locator"] for item in candidates] == [fact["fact_locator"]]
    MERGED_AGREEING_EVIDENCE,
