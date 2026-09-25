from __future__ import annotations

import copy

from evaluation.xbrl_mapping import (
    SOURCE_CHECK_PASS,
    SOURCE_CHECK_UNRESOLVED,
    build_derived_input_lineage,
    compare_units,
    generate_stage1,
    generate_stage2,
    generate_stage3,
)


def _precision() -> dict[str, str]:
    return {
        "rule_id": "precision_rounding_quantum_v0.1",
        "quantum": "1",
        "canonical_quantum": "1000000",
    }


def _target(**overrides: object) -> dict[str, object]:
    target: dict[str, object] = {
        "target_id": "NF_SYNTH",
        "entity_company": "Synthetic",
        "gold_value": "42",
        "gold_unit": "USD_million",
        "precision": _precision(),
        "gold_xbrl_concept": "us-gaap:Revenue",
        "approved_chunk_ids": ["chunk-gold"],
        "temporal_requirement": {
            "kind": "duration",
            "period_start": "2026-01-01",
            "period_end": "2026-03-31",
        },
        "dimensional_requirement": {"availability": "exact", "dimensions": []},
        "stage3_eligible_accessions": ["0000000001-26-000001", "0000000001-26-000002"],
    }
    target.update(overrides)
    return target


def _fact(
    *,
    suffix: str = "1",
    accession: str = "0000000001-26-000001",
    concept: str = "us-gaap:Revenue",
    value: str = "42000000",
    chunk_id: str | None = "chunk-gold",
    context_ref: str = "ctx-1",
    dimensions: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    return {
        "stable_fact_id": f"SYNTH::{suffix}",
        "fact_id": f"f-{suffix}",
        "doc_id": f"SYNTH_{suffix}",
        "concept": concept,
        "namespace_prefix": concept.split(":", 1)[0],
        "local_name": concept.split(":", 1)[-1],
        "raw_value": value,
        "normalized_value": value,
        "unit": "usd",
        "unit_measures": ["iso4217:USD"],
        "unit_numerator": [],
        "unit_denominator": [],
        "decimals": "-6",
        "scale": 0,
        "sign": None,
        "is_negative": value.startswith("-"),
        "context_ref": context_ref,
        "period_type": "duration",
        "instant": None,
        "period_start": "2026-01-01",
        "period_end": "2026-03-31",
        "duration_days": 90,
        "dimensions": [] if dimensions is None else dimensions,
        "accession": accession,
        "company": "Synthetic",
        "cik": "1",
        "entity_identifier": "1",
        "entity_scheme": "synthetic",
        "form_type": "10-Q",
        "filing_date": "2026-04-30",
        "period_of_report": "2026-03-31",
        "filing_fiscal_period": "Q1",
        "calendar_period": "2026Q1",
        "source_role": "benchmark_period",
        "doc_role": "primary",
        "chunk_id": chunk_id,
        "fact_locator": f"SYNTH_{suffix}#f-{suffix}",
    }


def test_stage1_chunk_linked_generation() -> None:
    linked = _fact()
    unlinked = _fact(suffix="2", chunk_id="other")
    candidates = generate_stage1(_target(), [unlinked, linked])
    assert [item["fact_locator"] for item in candidates] == [linked["fact_locator"]]
    assert candidates[0]["candidate_stage"] == 1


def test_exact_label_unknown_unit_is_supported_without_alias() -> None:
    match = compare_units("widgets", "widgets", right_is_raw_xbrl=True)
    assert match == {
        "unit_match_status": "exact_label_match",
        "unit_equivalence_rule_id": None,
        "dimension": None,
        "canonical_unit": "widgets",
    }
    assert compare_units("widgets", "widget", right_is_raw_xbrl=True)["unit_match_status"] == "unregistered_unit"


def test_registered_unit_equivalence_uses_raw_alias() -> None:
    match = compare_units("USD_million", "USD", right_is_raw_xbrl=True)
    assert match["unit_match_status"] == "registered_equivalence"
    assert match["unit_equivalence_rule_id"] == "raw_xbrl_usd_v0.1"


def test_stage2_requires_passing_stage1_lineage() -> None:
    parent = generate_stage1(_target(), [_fact()])[0]
    duplicate = _fact(suffix="2", accession="0000000001-26-000002", chunk_id=None)
    assert generate_stage2(_target(), [duplicate], [parent]) == []
    parent["source_check_status"] = SOURCE_CHECK_PASS
    candidates = generate_stage2(_target(), [duplicate], [parent])
    assert len(candidates) == 1
    assert candidates[0]["parent_candidate_id"] == parent["candidate_id"]


def test_stage2_requires_same_exact_concept() -> None:
    parent = generate_stage1(_target(), [_fact()])[0]
    parent["source_check_status"] = SOURCE_CHECK_PASS
    other = _fact(
        suffix="2",
        accession="0000000001-26-000002",
        concept="us-gaap:SalesRevenueNet",
        chunk_id=None,
    )
    assert generate_stage2(_target(), [other], [parent]) == []


def test_stage2_excludes_recast_value() -> None:
    parent = generate_stage1(_target(), [_fact()])[0]
    parent["source_check_status"] = SOURCE_CHECK_PASS
    recast = _fact(
        suffix="2",
        accession="0000000001-26-000002",
        value="42100000",
        chunk_id=None,
    )
    assert generate_stage2(_target(), [recast], [parent]) == []


def test_stage3_applies_deterministic_predicates() -> None:
    eligible = _fact(suffix="2", accession="0000000001-26-000002", chunk_id=None)
    wrong_period = copy.deepcopy(eligible)
    wrong_period.update(
        {
            "stable_fact_id": "SYNTH::3",
            "fact_locator": "SYNTH_3#f-3",
            "period_start": "2025-01-01",
            "period_end": "2025-03-31",
        }
    )
    candidates, state = generate_stage3(_target(), [wrong_period, eligible], [])
    assert state == "completed"
    assert [item["fact_locator"] for item in candidates] == [eligible["fact_locator"]]


def test_different_concept_stage3_begins_unresolved() -> None:
    fact = _fact(
        suffix="2",
        accession="0000000001-26-000002",
        concept="synthetic:EconomicallyEquivalentRevenue",
        chunk_id=None,
    )
    candidates, state = generate_stage3(_target(), [fact], [])
    assert state == "completed"
    assert candidates[0]["concept_relation"] == "different_concept"
    assert candidates[0]["source_check_status"] == SOURCE_CHECK_UNRESOLVED


def test_derived_input_lineage_preserves_each_required_input() -> None:
    lineage = build_derived_input_lineage(
        ["NF002", "NF001", "NF001"],
        {
            "NF001": {"support_status": "adjudicable_supported", "provenance_route": "legacy_chunk_path"},
            "NF002": {"support_status": "missing", "provenance_route": None},
        },
    )
    assert [item["input_target_id"] for item in lineage] == ["NF001", "NF002"]
    assert lineage[1]["support_status"] == "missing"


def test_candidate_order_is_independent_of_input_order() -> None:
    first = _fact(suffix="a", accession="0000000001-26-000002", context_ref="ctx-b")
    second = _fact(suffix="b", accession="0000000001-26-000001", context_ref="ctx-a")
    forward = generate_stage1(_target(), [first, second])
    reverse = generate_stage1(_target(), [second, first])
    assert forward == reverse


def test_duplicate_candidate_prevention() -> None:
    fact = _fact()
    candidates = generate_stage1(_target(), [fact, copy.deepcopy(fact)])
    assert len(candidates) == 1


def test_stage3_fails_closed_without_exact_temporal_metadata() -> None:
    target = _target(
        temporal_requirement={"kind": "unresolved", "source_period_label": "Q1"}
    )
    candidates, state = generate_stage3(target, [_fact()], [])
    assert candidates == []
    assert state == "blocked_missing_exact_temporal_requirement"
