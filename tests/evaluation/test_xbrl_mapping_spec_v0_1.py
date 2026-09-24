"""Synthetic contract tests for gold-to-XBRL mapping specification v0.1.

Fixtures contain no DEV/TEST rows, questions, mappings, or agent outputs.
Helpers are executable contract examples, not evaluator implementation.
"""

from __future__ import annotations

import copy
import json
import re
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "evaluation" / "xbrl_mapping_schema_v0.1.json"
PROTOCOL_PATH = ROOT / "evaluation" / "eval_protocol_v0.2.2.md"
EXECUTION_POLICY_PATH = (
    ROOT / "docs" / "agent" / "agent_execution_policy_preflight_v0.1.md"
)
TAXONOMY_PATH = ROOT / "docs" / "agent" / "execution_taxonomy_v0.1.md"
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())

NORMALIZATION = {
    "USD": (Decimal("1"), "monetary", "USD", "monetary_usd_identity_v0.1"),
    "USD_thousand": (
        Decimal("1000"), "monetary", "USD",
        "monetary_usd_thousand_to_usd_v0.1",
    ),
    "USD_million": (
        Decimal("1000000"), "monetary", "USD",
        "monetary_usd_million_to_usd_v0.1",
    ),
    "USD_billion": (
        Decimal("1000000000"), "monetary", "USD",
        "monetary_usd_billion_to_usd_v0.1",
    ),
    "shares": (Decimal("1"), "share_count", "shares", "shares_identity_v0.1"),
    "shares_thousand": (
        Decimal("1000"), "share_count", "shares", "shares_thousand_to_shares_v0.1",
    ),
    "shares_million": (
        Decimal("1000000"), "share_count", "shares", "shares_million_to_shares_v0.1",
    ),
    "shares_billion": (
        Decimal("1000000000"), "share_count", "shares", "shares_billion_to_shares_v0.1",
    ),
    "USD_per_share": (
        Decimal("1"), "monetary_per_share", "USD_per_share",
        "usd_per_share_identity_v0.1",
    ),
    "USD_per_basic_share": (
        Decimal("1"), "monetary_per_share", "USD_per_share",
        "usd_per_basic_share_alias_v0.1",
    ),
    "USD_per_diluted_share": (
        Decimal("1"), "monetary_per_share", "USD_per_share",
        "usd_per_diluted_share_alias_v0.1",
    ),
    "pure": (Decimal("1"), "ratio", "pure", "ratio_pure_identity_v0.1"),
    "percent": (
        Decimal("0.01"), "ratio", "pure", "ratio_percent_to_pure_v0.1",
    ),
    "percentage_point": (
        Decimal("1"), "percentage_point", "percentage_point",
        "percentage_point_identity_v0.1",
    ),
}

RAW_ALIASES = {
    "USD": ("monetary", "USD", "raw_xbrl_usd_v0.1"),
    "shares": ("share_count", "shares", "raw_xbrl_shares_v0.1"),
    "USD/shares": (
        "monetary_per_share", "USD_per_share", "raw_xbrl_usd_per_shares_v0.1",
    ),
    "pure": ("ratio", "pure", "raw_xbrl_pure_v0.1"),
}


def _normalize(value: str, unit: str) -> dict[str, Any]:
    registered = NORMALIZATION.get(unit)
    if registered is None:
        return {
            "submitted_value": value,
            "submitted_unit": unit,
            "unit_match_status": "unregistered_unit",
            "dimension": None,
            "canonical_value": None,
            "canonical_unit": None,
            "normalization_rule_id": None,
        }
    factor, dimension, canonical_unit, rule_id = registered
    return {
        "submitted_value": value,
        "submitted_unit": unit,
        "unit_match_status": "registered",
        "dimension": dimension,
        "canonical_value": str(Decimal(value) * factor),
        "canonical_unit": canonical_unit,
        "normalization_rule_id": rule_id,
    }


def _unit_match(left_unit: str, right_unit: str) -> str:
    if left_unit == right_unit:
        return "exact_label_match"
    left = NORMALIZATION.get(left_unit)
    right = NORMALIZATION.get(right_unit)
    if left is None or right is None:
        return "unregistered_unit"
    return (
        "registered_equivalence"
        if left[1:3] == right[1:3]
        else "dimension_mismatch"
    )


def _numeric_match(left_value: str, left_unit: str, right_value: str, right_unit: str) -> bool:
    status = _unit_match(left_unit, right_unit)
    if status == "exact_label_match":
        return Decimal(left_value) == Decimal(right_value)
    if status != "registered_equivalence":
        return False
    left = _normalize(left_value, left_unit)
    right = _normalize(right_value, right_unit)
    return left["canonical_value"] == right["canonical_value"]


def _unit_and_concept_match(
    gold_unit: str, gold_concept: str, raw_unit: str, xbrl_concept: str
) -> bool:
    gold = NORMALIZATION.get(gold_unit)
    raw = RAW_ALIASES.get(raw_unit)
    if gold is None or raw is None or gold[1:3] != raw[:2]:
        return False
    return gold_concept == xbrl_concept


def _round_to_quantum(value: Decimal, quantum: Decimal) -> Decimal:
    return quantum * (value / quantum).to_integral_value(rounding=ROUND_HALF_EVEN)


def _mapping_sign_allowed(
    gold_sign: str,
    xbrl_sign: str,
    relationship: str,
    source_check_completed: bool,
) -> bool:
    if relationship == "same_sign":
        return gold_sign == xbrl_sign
    return (
        relationship == "opposite_sign_explicitly_approved"
        and source_check_completed
        and {gold_sign, xbrl_sign} == {"positive", "negative"}
    )


def _agent_matches_registered_variant(
    value: str, unit: str, basis: str, variants: list[dict[str, Any]]
) -> bool:
    for variant in variants:
        expected = variant["normalization"]
        if basis != variant["basis"]:
            continue
        if _numeric_match(
            value,
            unit,
            expected["submitted_value"],
            expected["submitted_unit"],
        ):
            return True
    return False


def _errors(instance: dict[str, Any]) -> list[str]:
    return [error.message for error in VALIDATOR.iter_errors(instance)]


def _lineage_errors(target: dict[str, Any]) -> list[str]:
    """Test-local executable form of cross-record lineage invariants."""
    candidates = {item["candidate_id"]: item for item in target["review_candidates"]}
    errors: list[str] = []
    for candidate in candidates.values():
        if candidate["candidate_stage"] != 2:
            continue
        parent = candidates.get(candidate.get("parent_candidate_id"))
        if parent is None or parent["candidate_stage"] != 1:
            errors.append("stage2_parent_not_stage1")
            continue
        if parent["review_status"] != "APPROVE":
            errors.append("stage2_parent_not_approved")
        if candidate["fact"]["concept"] != parent["fact"]["concept"]:
            errors.append("stage2_concept_changed")
        if (
            candidate["fact"]["normalization"]["canonical_value"]
            != parent["fact"]["normalization"]["canonical_value"]
        ):
            errors.append("stage2_canonical_value_changed")
    return errors


def _derived_grounding_errors(target: dict[str, Any]) -> list[str]:
    """Test-local executable form of derived-input support invariants."""
    required = set(target["required_input_target_ids"])
    support = {item["input_target_id"]: item for item in target["derived_input_support"]}
    errors: list[str] = []
    if set(support) != required:
        errors.append("derived_support_ids_do_not_match_required_inputs")
    all_supported = all(
        item["support_status"] == "adjudicable_supported"
        and item["provenance_route"] in {"legacy_chunk_path", "approved_xbrl_path"}
        for item in support.values()
    )
    if target["derived_grounding_eligibility"] == "eligible" and not all_supported:
        errors.append("derived_eligible_with_unsupported_input")
    return errors


def _unit_audit_errors(target: dict[str, Any]) -> list[str]:
    """Test-local executable form of pairwise unit audit invariants."""
    records = target["review_candidates"] + target["approved_xbrl_paths"]
    errors: list[str] = []
    for record in records:
        if record["unit_match_status"] == "exact_label_match":
            if record["submitted_unit_label"] != record["reference_unit_label"]:
                errors.append("exact_label_strings_differ")
            if record["unit_equivalence_rule_id"] is not None:
                errors.append("exact_label_has_registered_rule")
        if (
            record["unit_match_status"] == "registered_equivalence"
            and record["unit_equivalence_rule_id"] is None
        ):
            errors.append("registered_equivalence_missing_rule")
    return errors


def _precision() -> dict[str, Any]:
    return {
        "rule_id": "precision_rounding_quantum_v0.1",
        "rule_source": "synthetic frozen display specification",
        "source_precision_text": "synthetic nearest million",
        "quantum": "1",
        "submitted_unit": "USD_million",
        "canonical_quantum": "1000000",
        "canonical_unit": "USD",
        "comparison_unit_basis": "registered_canonical",
        "rounding_mode": "ROUND_HALF_EVEN",
        "canonical_comparison_interval": {
            "lower": "41500000",
            "upper": "42500000",
            "lower_inclusive": True,
            "upper_inclusive": True,
            "canonical_unit": "USD",
            "comparison_unit_basis": "registered_canonical",
        },
    }


def _fact(
    *, suffix: str = "1", accession: str = "0000000001-00-000001",
    context_ref: str = "ctx-1", concept: str = "synthetic:Revenue",
    canonical_value: str = "42000000", temporal: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalization = _normalize(canonical_value, "USD")
    return {
        "fact_locator": f"SYNTH_DOC_{suffix}#fact-{suffix}",
        "accession": accession,
        "company": "Synthetic Corp",
        "concept": concept,
        "context_ref": context_ref,
        "raw_unit": "USD",
        "raw_unit_alias_rule_id": "raw_xbrl_usd_v0.1",
        "normalized_value": canonical_value,
        "normalization": normalization,
        "temporal": temporal or {"kind": "instant", "instant": "2026-03-31"},
        "dimensions": [],
        "chunk_id": f"synthetic_chunk_{suffix}",
    }


def _candidate(fact: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": "candidate_1",
        "candidate_stage": 1,
        "lineage_id": "lineage_1",
        "generation_rule_id": "stage1_direct_chunk_link_v0.1",
        "fact": copy.deepcopy(fact),
        "concept_relation": "same_exact_concept",
        "numeric_relation": "signed_equivalent",
        "comparison_value_relation": "exact_equal",
        "submitted_unit_label": "USD_million",
        "reference_unit_label": "USD",
        "unit_match_status": "registered_equivalence",
        "unit_equivalence_rule_id": "monetary_usd_million_to_usd_v0.1",
        "precision_rule_id": "precision_rounding_quantum_v0.1",
        "proposed_sign_relationship": "same_sign",
        "reason_codes": ["direct_chunk_link"],
        "initial_review_status": "NEEDS_SOURCE_CHECK",
        "source_check_completed": True,
        "review_status": "APPROVE",
        "review_rationale": "Synthetic review rationale.",
    }


def _mapped_artifact() -> dict[str, Any]:
    fact = _fact()
    precision = _precision()
    gold_normalization = _normalize("42", "USD_million")
    return {
        "schema_version": "xbrl_gold_mapping_schema_v0.1",
        "mapping_id": "synthetic_dev_map_v0.1",
        "split": "DEV",
        "benchmark_version": "synthetic_benchmark_v0.1",
        "benchmark_artifact_sha256": "a" * 64,
        "xbrl_artifact_fingerprint": "b" * 64,
        "mapping_algorithm_version": "xbrl_gold_mapping_algorithm_v0.1",
        "human_review_rubric_version": "xbrl_mapping_review_rubric_v0.1",
        "agent_outputs_generated_or_inspected_before_mapping_freeze": False,
        "authorized_access_log_reference": None,
        "targets": [
            {
                "gold_target_id": "SYNTH_TARGET_001",
                "source_gold_ref": {
                    "q_id": "SYNTH_Q_001", "fact_id": "SYNTH_FACT_001",
                    "role": "answer",
                },
                "target_kind": "direct",
                "required_input_target_ids": [],
                "derived_input_support": [],
                "derived_grounding_eligibility": "not_applicable",
                "entity": {"company": "Synthetic Corp", "cik": "1"},
                "source_accessions": ["0000000001-00-000001"],
                "legacy_chunk_paths": [
                    {
                        "path_id": "legacy_path_1",
                        "chunk_id": "synthetic_chunk_1",
                        "accession": "0000000001-00-000001",
                        "locator": "Synthetic note",
                    }
                ],
                "gold_numeric_target": {
                    "normalization": gold_normalization,
                    "precision": precision,
                    "gold_basis": "synthetic GAAP basis",
                    "gold_display_sign": "positive",
                    "gold_sign_basis": "economic_signed_value",
                    "gold_canonical_economic_value": "42000000",
                    "gold_canonical_economic_sign": "positive",
                    "per_share_economic_subtype": "not_applicable",
                    "registered_answer_variants": [
                        {
                            "variant_id": "variant_gaap",
                            "normalization": copy.deepcopy(gold_normalization),
                            "precision": copy.deepcopy(precision),
                            "basis": "synthetic GAAP basis",
                            "sign_convention": "economic_signed_value",
                            "answer_sign": "positive",
                            "variant_family": "synthetic_family_a",
                        }
                    ],
                },
                "temporal_requirement": {"kind": "instant", "instant": "2026-03-31"},
                "dimensional_requirement": {"availability": "exact", "dimensions": []},
                "mapping_resolution_mode": "direct_xbrl_paths",
                "mapping_status": "mapped",
                "stage_completion": {
                    "stage1_completed": True,
                    "stage2_state": "not_applicable",
                    "stage3_completed": False,
                    "approved_candidate_count": 1,
                    "unresolved_candidate_count": 0,
                },
                "finalization_notes": "Synthetic mapped target.",
                "approved_xbrl_paths": [
                    {
                        "path_id": "xbrl_path_1",
                        "candidate_id": "candidate_1",
                        "fact": copy.deepcopy(fact),
                        "accepted_sign_relationship": "same_sign",
                        "gold_display_sign": "positive",
                        "gold_canonical_economic_sign": "positive",
                        "authoritative_xbrl_sign": "positive",
                        "submitted_unit_label": "USD_million",
                        "reference_unit_label": "USD",
                        "unit_match_status": "registered_equivalence",
                        "unit_equivalence_rule_id": "monetary_usd_million_to_usd_v0.1",
                        "declared_basis_relationship": "same economic basis",
                        "source_check_completed": True,
                        "review_status": "APPROVE",
                        "review_rationale": "Synthetic same-target rationale.",
                    }
                ],
                "review_candidates": [_candidate(fact)],
                "mapping_algorithm_version": "xbrl_gold_mapping_algorithm_v0.1",
                "human_review_rubric_version": "xbrl_mapping_review_rubric_v0.1",
            }
        ],
    }


def test_schema_is_valid_draft_2020_12() -> None:
    Draft202012Validator.check_schema(SCHEMA)


def test_currency_and_share_scales_use_exact_decimal() -> None:
    assert _normalize("2", "USD_million")["canonical_value"] == "2000000"
    assert _normalize("2", "USD_million")["dimension"] == "monetary"
    assert _normalize("2", "shares_million")["canonical_value"] == "2000000"
    assert _normalize("2", "shares_million")["canonical_unit"] == "shares"


def test_per_share_raw_alias_is_dimensional_not_economic_subtype() -> None:
    basic = _normalize("1.25", "USD_per_basic_share")
    diluted = _normalize("1.25", "USD_per_diluted_share")
    assert basic["dimension"] == diluted["dimension"] == "monetary_per_share"
    assert RAW_ALIASES["USD/shares"][:2] == ("monetary_per_share", "USD_per_share")
    assert _unit_match(
        "USD_per_basic_share", "USD_per_diluted_share"
    ) == "registered_equivalence"
    assert not _unit_and_concept_match(
        "USD_per_basic_share",
        "synthetic:BasicEPS",
        "USD/shares",
        "synthetic:DilutedEPS",
    )


def test_per_diluted_share_label_validates_against_raw_usd_per_shares() -> None:
    artifact = _mapped_artifact()
    target = artifact["targets"][0]
    exact_precision = {
        "rule_id": "precision_exact_v0.1",
        "rule_source": "synthetic frozen exact-value specification",
        "source_precision_text": "synthetic exact per-share value",
    }
    gold_normalization = _normalize("2.50", "USD_per_diluted_share")
    target["gold_numeric_target"].update(
        {
            "normalization": gold_normalization,
            "precision": exact_precision,
            "gold_canonical_economic_value": "2.50",
            "per_share_economic_subtype": "diluted",
            "registered_answer_variants": [
                {
                    "variant_id": "variant_diluted",
                    "normalization": copy.deepcopy(gold_normalization),
                    "precision": copy.deepcopy(exact_precision),
                    "basis": "synthetic GAAP basis",
                    "sign_convention": "economic_signed_value",
                    "answer_sign": "positive",
                    "variant_family": "synthetic_diluted_family",
                }
            ],
        }
    )
    per_share_fact = target["approved_xbrl_paths"][0]["fact"]
    per_share_fact.update(
        {
            "concept": "synthetic:DilutedEPS",
            "raw_unit": "USD/shares",
            "raw_unit_alias_rule_id": "raw_xbrl_usd_per_shares_v0.1",
            "normalized_value": "2.50",
            "normalization": _normalize("2.50", "USD_per_share"),
        }
    )
    target["review_candidates"][0]["fact"] = copy.deepcopy(per_share_fact)
    target["review_candidates"][0]["precision_rule_id"] = "precision_exact_v0.1"
    target["review_candidates"][0]["submitted_unit_label"] = "USD_per_diluted_share"
    target["review_candidates"][0]["reference_unit_label"] = "USD/shares"
    target["review_candidates"][0][
        "unit_equivalence_rule_id"
    ] = "raw_xbrl_usd_per_shares_v0.1"
    target["approved_xbrl_paths"][0][
        "unit_equivalence_rule_id"
    ] = "raw_xbrl_usd_per_shares_v0.1"
    target["approved_xbrl_paths"][0][
        "submitted_unit_label"
    ] = "USD_per_diluted_share"
    target["approved_xbrl_paths"][0]["reference_unit_label"] = "USD/shares"
    assert _errors(artifact) == []


def test_pure_percent_and_percentage_point_dimensions() -> None:
    assert _normalize("0.56", "pure")["canonical_value"] == _normalize(
        "56", "percent"
    )["canonical_value"]
    assert _unit_match("pure", "percent") == "registered_equivalence"
    assert _unit_match("percent", "percentage_point") == "dimension_mismatch"


def test_unknown_same_label_fallback_and_different_unknown_rejection() -> None:
    assert _unit_match(
        "synthetic_unit_x", "synthetic_unit_x"
    ) == "exact_label_match"
    assert _unit_match(
        "synthetic_unit_x", "synthetic_unit_y"
    ) == "unregistered_unit"
    assert _numeric_match("7", "synthetic_unit_x", "7", "synthetic_unit_x")
    assert not _numeric_match("7", "synthetic_unit_x", "8", "synthetic_unit_x")
    assert not _numeric_match("-7", "synthetic_unit_x", "7", "synthetic_unit_x")
    assert "synthetic_unit_x" not in NORMALIZATION
    assert "synthetic_unit_x" not in RAW_ALIASES

    unknown = _normalize("7", "synthetic_unit_x")
    assert unknown["unit_match_status"] == "unregistered_unit"
    assert unknown["dimension"] is None
    assert unknown["normalization_rule_id"] is None


def test_registered_unit_and_rule_pair_is_closed() -> None:
    artifact = _mapped_artifact()
    normalization = artifact["targets"][0]["gold_numeric_target"]["normalization"]
    normalization["normalization_rule_id"] = "monetary_usd_identity_v0.1"
    assert _errors(artifact)


def test_schema_maps_same_unknown_label_without_creating_alias() -> None:
    artifact = _mapped_artifact()
    target = artifact["targets"][0]
    exact_precision = {
        "rule_id": "precision_exact_v0.1",
        "rule_source": "synthetic frozen exact-value specification",
        "source_precision_text": "synthetic exact unknown-label value",
    }
    unknown_normalization = _normalize("7", "synthetic_unit_x")
    target["gold_numeric_target"].update(
        {
            "normalization": copy.deepcopy(unknown_normalization),
            "precision": exact_precision,
            "gold_canonical_economic_value": "7",
            "registered_answer_variants": [
                {
                    "variant_id": "variant_same_unknown_label",
                    "normalization": copy.deepcopy(unknown_normalization),
                    "precision": copy.deepcopy(exact_precision),
                    "basis": "synthetic same-label basis",
                    "sign_convention": "economic_signed_value",
                    "answer_sign": "positive",
                    "variant_family": None,
                }
            ],
        }
    )
    fact = target["approved_xbrl_paths"][0]["fact"]
    fact.update(
        {
            "raw_unit": "synthetic_unit_x",
            "raw_unit_alias_rule_id": None,
            "normalized_value": "7",
            "normalization": copy.deepcopy(unknown_normalization),
        }
    )
    path = target["approved_xbrl_paths"][0]
    path["submitted_unit_label"] = "synthetic_unit_x"
    path["reference_unit_label"] = "synthetic_unit_x"
    path["unit_match_status"] = "exact_label_match"
    path["unit_equivalence_rule_id"] = None
    candidate = target["review_candidates"][0]
    candidate["fact"] = copy.deepcopy(fact)
    candidate["submitted_unit_label"] = "synthetic_unit_x"
    candidate["reference_unit_label"] = "synthetic_unit_x"
    candidate["unit_match_status"] = "exact_label_match"
    candidate["unit_equivalence_rule_id"] = None
    candidate["precision_rule_id"] = "precision_exact_v0.1"
    assert _errors(artifact) == []
    assert target["mapping_status"] == "mapped"
    assert _unit_audit_errors(target) == []
    assert "synthetic_unit_x" not in NORMALIZATION


def test_sign_preservation_and_path_specific_exception() -> None:
    assert _normalize("-30.876", "USD_million")["canonical_value"] == "-30876000.000"
    assert _mapping_sign_allowed("positive", "positive", "same_sign", False)
    assert not _mapping_sign_allowed("positive", "negative", "same_sign", True)
    assert not _mapping_sign_allowed(
        "positive", "negative", "opposite_sign_explicitly_approved", False
    )
    assert _mapping_sign_allowed(
        "positive", "negative", "opposite_sign_explicitly_approved", True
    )

    artifact = _mapped_artifact()
    path = artifact["targets"][0]["approved_xbrl_paths"][0]
    path["authoritative_xbrl_sign"] = "negative"
    assert _errors(artifact)
    path["accepted_sign_relationship"] = "opposite_sign_explicitly_approved"
    path["declared_basis_relationship"] = "Synthetic opposite presentation basis."
    assert _errors(artifact) == []


def test_agent_cannot_invent_answer_basis_variant() -> None:
    variants = _mapped_artifact()["targets"][0]["gold_numeric_target"][
        "registered_answer_variants"
    ]
    assert _agent_matches_registered_variant(
        "42", "USD_million", "synthetic GAAP basis", variants
    )
    assert not _agent_matches_registered_variant(
        "-42", "USD_million", "agent invented opposite basis", variants
    )


def test_rounding_uses_frozen_precision_and_rejects_ad_hoc_rule() -> None:
    gold = Decimal("42000000")
    quantum = Decimal("1000000")
    assert _round_to_quantum(Decimal("42400000"), quantum) == gold
    assert _round_to_quantum(Decimal("42500000"), quantum) == gold
    assert _round_to_quantum(Decimal("42600000"), quantum) != gold

    artifact = _mapped_artifact()
    artifact["targets"][0]["review_candidates"][0][
        "precision_rule_id"
    ] = "reviewer_ad_hoc_tolerance"
    assert _errors(artifact)


def test_approved_or_paths_allow_different_context_refs() -> None:
    artifact = _mapped_artifact()
    target = artifact["targets"][0]
    fact = _fact(
        suffix="2", accession="0000000001-00-000002",
        context_ref="comparison-context",
    )
    target["approved_xbrl_paths"].append(
        {
            "path_id": "xbrl_path_2", "candidate_id": "candidate_2",
            "fact": fact, "accepted_sign_relationship": "same_sign",
            "gold_display_sign": "positive",
            "gold_canonical_economic_sign": "positive",
            "authoritative_xbrl_sign": "positive",
            "submitted_unit_label": "USD_million",
            "reference_unit_label": "USD",
            "unit_match_status": "registered_equivalence",
            "unit_equivalence_rule_id": "monetary_usd_million_to_usd_v0.1",
            "declared_basis_relationship": "same economic basis",
            "source_check_completed": True, "review_status": "APPROVE",
            "review_rationale": "Synthetic cross-filing alternative.",
        }
    )
    assert _errors(artifact) == []
    assert {p["fact"]["context_ref"] for p in target["approved_xbrl_paths"]} == {
        "ctx-1", "comparison-context"
    }


def test_instant_and_duration_paths_validate() -> None:
    artifact = _mapped_artifact()
    duration = {"kind": "duration", "period_start": "2026-01-01", "period_end": "2026-03-31"}
    target = artifact["targets"][0]
    target["temporal_requirement"] = copy.deepcopy(duration)
    target["approved_xbrl_paths"][0]["fact"]["temporal"] = copy.deepcopy(duration)
    target["review_candidates"][0]["fact"]["temporal"] = copy.deepcopy(duration)
    assert _errors(artifact) == []


def test_three_direct_target_statuses_and_candidate_reject_separation() -> None:
    assert _errors(_mapped_artifact()) == []

    no_counterpart = _mapped_artifact()
    target = no_counterpart["targets"][0]
    target["mapping_resolution_mode"] = "legacy_chunk_only"
    target["mapping_status"] = "no_xbrl_counterpart_in_frozen_corpus"
    target["no_xbrl_counterpart_reason"] = "Synthetic complete search found none."
    target["approved_xbrl_paths"] = []
    target["review_candidates"][0]["review_status"] = "REJECT"
    target["stage_completion"] = {
        "stage1_completed": True, "stage2_state": "not_applicable",
        "stage3_completed": True, "approved_candidate_count": 0,
        "unresolved_candidate_count": 0,
    }
    assert _errors(no_counterpart) == []
    assert target["review_candidates"][0]["review_status"] == "REJECT"
    assert target["mapping_status"] == "no_xbrl_counterpart_in_frozen_corpus"

    unmappable = _mapped_artifact()
    target = unmappable["targets"][0]
    target["mapping_resolution_mode"] = "legacy_chunk_only"
    target["mapping_status"] = "unmappable"
    target["unmappable_reason"] = "Synthetic unresolved semantic limitation."
    target["approved_xbrl_paths"] = []
    target["review_candidates"][0]["review_status"] = "NEEDS_SOURCE_CHECK"
    target["stage_completion"]["approved_candidate_count"] = 0
    target["stage_completion"]["unresolved_candidate_count"] = 1
    assert _errors(unmappable) == []


def test_no_counterpart_requires_complete_search_and_no_unresolved_candidate() -> None:
    artifact = _mapped_artifact()
    target = artifact["targets"][0]
    target["mapping_resolution_mode"] = "legacy_chunk_only"
    target["mapping_status"] = "no_xbrl_counterpart_in_frozen_corpus"
    target["no_xbrl_counterpart_reason"] = "Synthetic complete search found none."
    target["approved_xbrl_paths"] = []
    target["stage_completion"]["approved_candidate_count"] = 0
    target["stage_completion"]["stage3_completed"] = False
    assert _errors(artifact)
    target["stage_completion"]["stage3_completed"] = True
    target["stage_completion"]["unresolved_candidate_count"] = 1
    assert _errors(artifact)


def test_stage2_requires_approved_stage1_parent_and_exact_signature() -> None:
    artifact = _mapped_artifact()
    target = artifact["targets"][0]
    stage2 = copy.deepcopy(target["review_candidates"][0])
    stage2.update(
        {
            "candidate_id": "candidate_2",
            "candidate_stage": 2,
            "generation_rule_id": "stage2_approved_stage1_same_concept_cross_filing_v0.1",
            "parent_candidate_id": "candidate_1",
            "parent_review_status": "APPROVE",
            "reason_codes": ["same_concept_cross_filing"],
        }
    )
    stage2["fact"]["fact_locator"] = "SYNTH_DOC_2#fact-2"
    stage2["fact"]["accession"] = "0000000001-00-000002"
    stage2["fact"]["context_ref"] = "comparison-context"
    stage2["fact"]["chunk_id"] = "synthetic_chunk_2"
    target["review_candidates"].append(stage2)
    assert _errors(artifact) == []
    assert _lineage_errors(target) == []

    stage2["parent_review_status"] = "REJECT"
    assert _errors(artifact)
    stage2["parent_review_status"] = "APPROVE"
    stage2["parent_candidate_id"] = "missing_parent"
    assert _lineage_errors(target) == ["stage2_parent_not_stage1"]
    stage2["parent_candidate_id"] = "candidate_1"
    stage2["concept_relation"] = "different_concept"
    assert _errors(artifact)
    stage2["concept_relation"] = "same_exact_concept"
    stage2["comparison_value_relation"] = "different"
    assert _errors(artifact)
    stage2["comparison_value_relation"] = "exact_equal"
    stage2["fact"]["normalization"]["canonical_value"] = "41000000"
    assert _lineage_errors(target) == ["stage2_canonical_value_changed"]


def test_stage3_different_concept_begins_needs_source_check() -> None:
    artifact = _mapped_artifact()
    candidate = artifact["targets"][0]["review_candidates"][0]
    candidate.update(
        {
            "candidate_stage": 3,
            "generation_rule_id": "stage3_deterministic_constrained_search_v0.1",
            "concept_relation": "different_concept",
            "reason_codes": ["different_concept_requires_source_check"],
            "source_check_completed": False,
            "review_status": "NEEDS_SOURCE_CHECK",
        }
    )
    assert _errors(artifact) == []
    candidate["review_status"] = "APPROVE"
    assert _errors(artifact)
    candidate["source_check_completed"] = True
    assert _errors(artifact) == []


def test_derived_target_uses_separate_resolution_mode() -> None:
    artifact = _mapped_artifact()
    target = artifact["targets"][0]
    target.update(
        {
            "target_kind": "derived",
            "required_input_target_ids": ["SYNTH_INPUT_001", "SYNTH_INPUT_002"],
            "derived_input_support": [
                {
                    "input_target_id": "SYNTH_INPUT_001",
                    "support_status": "adjudicable_supported",
                    "provenance_route": "legacy_chunk_path",
                    "adjudication_note": "Synthetic supported input one.",
                },
                {
                    "input_target_id": "SYNTH_INPUT_002",
                    "support_status": "adjudicable_supported",
                    "provenance_route": "approved_xbrl_path",
                    "adjudication_note": "Synthetic supported input two.",
                },
            ],
            "derived_grounding_eligibility": "eligible",
            "mapping_resolution_mode": "derived_via_inputs",
            "mapping_status": None,
            "stage_completion": None,
            "finalization_notes": "Synthetic derived target uses required inputs.",
            "approved_xbrl_paths": [],
            "review_candidates": [],
        }
    )
    assert _errors(artifact) == []
    assert _derived_grounding_errors(target) == []

    target["derived_input_support"][1].update(
        {
            "support_status": "unsupported",
            "provenance_route": "none",
            "adjudication_note": "Synthetic unsupported required input.",
        }
    )
    assert _errors(artifact)
    assert _derived_grounding_errors(target) == [
        "derived_eligible_with_unsupported_input"
    ]
    target["derived_grounding_eligibility"] = "ineligible_unsupported_input"
    assert _errors(artifact) == []
    assert _derived_grounding_errors(target) == []


def test_test_mapping_requires_access_log_reference() -> None:
    artifact = _mapped_artifact()
    artifact["split"] = "TEST"
    assert _errors(artifact)
    artifact["authorized_access_log_reference"] = "synthetic_access_log_entry"
    assert _errors(artifact) == []


def test_execution_ids_have_one_canonical_source_and_protocol_mapping() -> None:
    taxonomy = TAXONOMY_PATH.read_text(encoding="utf-8")
    policy = EXECUTION_POLICY_PATH.read_text(encoding="utf-8")
    protocol = PROTOCOL_PATH.read_text(encoding="utf-8")
    identifiers = [
        "EVT_FIXED_TOP_K_VIOLATION",
        "EVT_TOOL_ARGUMENT_REJECTED",
        "EVT_TOOL_ZERO_RESULT",
        "EVT_TOOL_DOMAIN_ERROR_RECOVERABLE",
        "EVT_TOOL_RESULT_TOO_LARGE",
        "FAIL_TOOL_BUDGET_EXHAUSTED",
        "FAIL_STEP_BUDGET_EXHAUSTED",
        "FAIL_FINAL_SCHEMA_INVALID",
        "FAIL_NO_VALID_FINAL_OUTPUT",
        "FAIL_AGENT_ORCHESTRATION_UNRECOVERABLE",
        "INFRA_RUN_RETRY_EXHAUSTED",
        "RUN_COMPLETED",
        "EVAL_INCOMPLETE",
    ]
    for identifier in identifiers:
        assert identifier in taxonomy
        assert identifier in protocol
    table_ids = re.findall(
        r"^\| `((?:EVT|FAIL)_[A-Z0-9_]+)`", taxonomy, re.MULTILINE
    )
    assert len(table_ids) == len(set(table_ids))
    status_ids = ["RUN_COMPLETED", "INFRA_RUN_RETRY_EXHAUSTED", "EVAL_INCOMPLETE"]
    all_declared_ids = table_ids + status_ids
    assert len(all_declared_ids) == len(set(all_declared_ids)) == len(identifiers)
    assert "execution_taxonomy_v0.1.md" in policy
    assert "execution_taxonomy_v0.1.md" in protocol
    assert "sole normative source" in taxonomy


def test_oversized_event_is_reserved_and_eval_incomplete_is_evaluation_level() -> None:
    taxonomy = TAXONOMY_PATH.read_text(encoding="utf-8")
    assert "`EVT_TOOL_RESULT_TOO_LARGE` must not be emitted" in taxonomy
    assert "**Reserved; not active for agent_v0.1.**" in taxonomy
    assert "`EVAL_INCOMPLETE` is an evaluation-level status" in taxonomy
    assert "It is not an agent failure, tool\nevent, terminal run status" in taxonomy


def test_infrastructure_caps_exist_only_in_standalone_taxonomy() -> None:
    taxonomy = TAXONOMY_PATH.read_text(encoding="utf-8")
    policy = EXECUTION_POLICY_PATH.read_text(encoding="utf-8")
    protocol = PROTOCOL_PATH.read_text(encoding="utf-8")
    canonical_assignments = [
        "MAX_PROVIDER_ATTEMPTS_PER_REQUEST = 3",
        "MAX_TOTAL_INFRASTRUCTURE_RETRIES_PER_RUN = 8",
        "MAX_REPLACEMENT_RUNS_PER_SCHEDULED_REPLICATE = 1",
    ]
    for assignment in canonical_assignments:
        assert assignment in taxonomy
        assert assignment not in policy
        assert assignment not in protocol


def test_future_prompt_contract_preserves_authoritative_sign_generically() -> None:
    policy = EXECUTION_POLICY_PATH.read_text(encoding="utf-8")
    sign_contract = policy.split("NUMERIC SIGN DISCIPLINE", maxsplit=1)[1].split(
        "The frozen prompt was not modified here.", maxsplit=1
    )[0]
    assert "authoritative numeric sign returned by XBRLTool" in sign_contract
    assert "never use absolute-value matching" in sign_contract
    assert "source-reported value/sign" in sign_contract
    for company_name in ["NVIDIA", "Microsoft", "Amazon", "Apple"]:
        assert company_name not in sign_contract
