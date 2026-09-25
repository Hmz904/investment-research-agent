"""Deterministic evaluation-side XBRL mapping candidate generation.

This module implements the mechanical discovery portions of
``xbrl_gold_mapping_algorithm_v0.1``.  It deliberately does not perform
semantic review or final mapping approval.  Callers supply source-check
decisions separately and may use passing source checks for pending-review
Stage-2 lineage without representing them as human approval.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import Any, Iterable, Mapping, Sequence


ALGORITHM_VERSION = "xbrl_gold_mapping_algorithm_v0.1"

SOURCE_CHECK_PASS = "SOURCE_CHECK_PASS"
SOURCE_CHECK_REJECT = "SOURCE_CHECK_REJECT"
SOURCE_CHECK_UNRESOLVED = "SOURCE_CHECK_UNRESOLVED"
SOURCE_CHECK_STATUSES = {
    SOURCE_CHECK_PASS,
    SOURCE_CHECK_REJECT,
    SOURCE_CHECK_UNRESOLVED,
}

CANDIDATE_DISCOVERY_STATES = frozenset(
    {
        "NO_CANDIDATES_DISCOVERED",
        "CANDIDATES_DISCOVERED_SOURCE_CHECK_PENDING",
        "CANDIDATES_DISCOVERED_SOURCE_CHECK_PASS",
        "CANDIDATES_DISCOVERED_ALL_REJECTED",
    }
)
FINAL_PROPOSED_MAPPING_STATES = frozenset(
    {
        "PENDING_TEMPORAL_ADJUDICATION",
        "PROPOSED_MAPPED",
        "PROPOSED_UNMAPPABLE",
        "PROPOSED_NO_XBRL_COUNTERPART_IN_FROZEN_CORPUS",
    }
)

_DECIMAL_RE = re.compile(r"^[+-]?[0-9]+(?:\.[0-9]+)?$")


@dataclass(frozen=True)
class UnitRule:
    factor: Decimal
    dimension: str
    canonical_unit: str
    rule_id: str


UNIT_REGISTRY: dict[str, UnitRule] = {
    "USD": UnitRule(Decimal("1"), "monetary", "USD", "monetary_usd_identity_v0.1"),
    "USD_thousand": UnitRule(Decimal("1000"), "monetary", "USD", "monetary_usd_thousand_to_usd_v0.1"),
    "USD_million": UnitRule(Decimal("1000000"), "monetary", "USD", "monetary_usd_million_to_usd_v0.1"),
    "USD_billion": UnitRule(Decimal("1000000000"), "monetary", "USD", "monetary_usd_billion_to_usd_v0.1"),
    "shares": UnitRule(Decimal("1"), "share_count", "shares", "shares_identity_v0.1"),
    "shares_thousand": UnitRule(Decimal("1000"), "share_count", "shares", "shares_thousand_to_shares_v0.1"),
    "shares_million": UnitRule(Decimal("1000000"), "share_count", "shares", "shares_million_to_shares_v0.1"),
    "shares_billion": UnitRule(Decimal("1000000000"), "share_count", "shares", "shares_billion_to_shares_v0.1"),
    "USD_per_share": UnitRule(Decimal("1"), "monetary_per_share", "USD_per_share", "usd_per_share_identity_v0.1"),
    "USD_per_basic_share": UnitRule(Decimal("1"), "monetary_per_share", "USD_per_share", "usd_per_basic_share_alias_v0.1"),
    "USD_per_diluted_share": UnitRule(Decimal("1"), "monetary_per_share", "USD_per_share", "usd_per_diluted_share_alias_v0.1"),
    "pure": UnitRule(Decimal("1"), "ratio", "pure", "ratio_pure_identity_v0.1"),
    "percent": UnitRule(Decimal("0.01"), "ratio", "pure", "ratio_percent_to_pure_v0.1"),
    "percentage_point": UnitRule(Decimal("1"), "percentage_point", "percentage_point", "percentage_point_identity_v0.1"),
}

RAW_XBRL_UNIT_REGISTRY: dict[str, UnitRule] = {
    "USD": UnitRule(Decimal("1"), "monetary", "USD", "raw_xbrl_usd_v0.1"),
    "shares": UnitRule(Decimal("1"), "share_count", "shares", "raw_xbrl_shares_v0.1"),
    "USD/shares": UnitRule(Decimal("1"), "monetary_per_share", "USD_per_share", "raw_xbrl_usd_per_shares_v0.1"),
    "pure": UnitRule(Decimal("1"), "ratio", "pure", "raw_xbrl_pure_v0.1"),
}


def parse_decimal(value: str) -> Decimal:
    """Parse one plain decimal under the frozen lexical contract."""
    if not isinstance(value, str) or not _DECIMAL_RE.fullmatch(value):
        raise ValueError(f"invalid plain decimal: {value!r}")
    try:
        return Decimal(value)
    except InvalidOperation as exc:  # pragma: no cover - guarded by regex
        raise ValueError(f"invalid plain decimal: {value!r}") from exc


def canonical_decimal(value: Decimal) -> str:
    """Serialize a Decimal in canonical, non-scientific plain notation."""
    if value.is_zero():
        return "0"
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def normalize_value(value: str, unit: str, *, raw_xbrl: bool = False) -> dict[str, Any]:
    registry = RAW_XBRL_UNIT_REGISTRY if raw_xbrl else UNIT_REGISTRY
    rule = registry.get(unit)
    if rule is None:
        return {
            "submitted_value": value,
            "submitted_unit": unit,
            "unit_match_status": "unregistered_unit",
            "dimension": None,
            "canonical_value": None,
            "canonical_unit": None,
            "normalization_rule_id": None,
        }
    canonical = parse_decimal(value) * rule.factor
    return {
        "submitted_value": value,
        "submitted_unit": unit,
        "unit_match_status": "registered",
        "dimension": rule.dimension,
        "canonical_value": canonical_decimal(canonical),
        "canonical_unit": rule.canonical_unit,
        "normalization_rule_id": rule.rule_id,
    }


def compare_units(left_unit: str, right_unit: str, *, right_is_raw_xbrl: bool = False) -> dict[str, Any]:
    """Apply exact-label-first unit comparison and closed equivalence rules."""
    if left_unit == right_unit:
        return {
            "unit_match_status": "exact_label_match",
            "unit_equivalence_rule_id": None,
            "dimension": None,
            "canonical_unit": left_unit,
        }
    left = UNIT_REGISTRY.get(left_unit)
    right_registry = RAW_XBRL_UNIT_REGISTRY if right_is_raw_xbrl else UNIT_REGISTRY
    right = right_registry.get(right_unit)
    if left is None or right is None:
        return {
            "unit_match_status": "unregistered_unit",
            "unit_equivalence_rule_id": None,
            "dimension": None,
            "canonical_unit": None,
        }
    if (left.dimension, left.canonical_unit) != (right.dimension, right.canonical_unit):
        return {
            "unit_match_status": "dimension_mismatch",
            "unit_equivalence_rule_id": None,
            "dimension": None,
            "canonical_unit": None,
        }
    return {
        "unit_match_status": "registered_equivalence",
        "unit_equivalence_rule_id": right.rule_id if right_is_raw_xbrl else left.rule_id,
        "dimension": left.dimension,
        "canonical_unit": left.canonical_unit,
    }


def raw_xbrl_unit_label(fact: Mapping[str, Any]) -> str:
    """Render the frozen raw-unit aliases from authoritative XBRL measures."""
    measures = tuple(fact.get("unit_measures") or ())
    numerator = tuple(fact.get("unit_numerator") or ())
    denominator = tuple(fact.get("unit_denominator") or ())
    if measures == ("iso4217:USD",):
        return "USD"
    if measures == ("xbrli:shares",):
        return "shares"
    if measures == ("xbrli:pure",):
        return "pure"
    if numerator == ("iso4217:USD",) and denominator == ("xbrli:shares",):
        return "USD/shares"
    if numerator or denominator:
        return f"{'*'.join(numerator)}/{'*'.join(denominator)}"
    if measures:
        return "*".join(measures)
    return str(fact.get("unit", ""))


def precision_matches(candidate: Decimal, gold: Decimal, precision: Mapping[str, Any]) -> bool:
    rule_id = precision["rule_id"]
    if rule_id == "precision_exact_v0.1":
        return candidate == gold
    if rule_id == "precision_rounding_quantum_v0.1":
        quantum = parse_decimal(str(precision["canonical_quantum"]))
        return quantum * (candidate / quantum).to_integral_value(rounding=ROUND_HALF_EVEN) == gold
    if rule_id == "precision_absolute_tolerance_v0.1":
        tolerance = parse_decimal(str(precision["canonical_absolute_tolerance"]))
        return abs(candidate - gold) <= tolerance
    raise ValueError(f"unregistered precision rule: {rule_id!r}")


def _sign(value: Decimal) -> str:
    if value.is_zero():
        return "zero"
    return "positive" if value > 0 else "negative"


def _temporal(fact: Mapping[str, Any]) -> dict[str, Any]:
    if fact.get("period_type") == "instant":
        return {"kind": "instant", "instant": fact.get("instant")}
    return {
        "kind": "duration",
        "period_start": fact.get("period_start"),
        "period_end": fact.get("period_end"),
    }


def _dimensions(fact: Mapping[str, Any]) -> list[dict[str, str]] | None:
    dimensions = fact.get("dimensions")
    if dimensions is None:
        return None
    return sorted(
        ({"axis": str(item["axis"]), "member": str(item["member"])} for item in dimensions),
        key=lambda item: (item["axis"], item["member"]),
    )


def _fact_sort_key(fact: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(fact.get("accession", "")),
        str(fact.get("concept", "")),
        str(fact.get("context_ref", "")),
        str(fact.get("fact_locator", "")),
    )


def candidate_sort_key(candidate: Mapping[str, Any]) -> tuple[Any, ...]:
    fact = candidate["fact"]
    return (candidate["candidate_stage"],) + _fact_sort_key(fact) + (candidate["candidate_id"],)


def _candidate_id(target_id: str, stage: int, fact_locator: str, parent_id: str | None) -> str:
    identity = json.dumps(
        [target_id, stage, fact_locator, parent_id],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"XBRLCAND-{hashlib.sha256(identity).hexdigest()[:16]}"


def _comparison(target: Mapping[str, Any], fact: Mapping[str, Any]) -> dict[str, Any] | None:
    raw_unit = raw_xbrl_unit_label(fact)
    unit = compare_units(str(target["gold_unit"]), raw_unit, right_is_raw_xbrl=True)
    if unit["unit_match_status"] not in {"exact_label_match", "registered_equivalence"}:
        return None
    normalized_value = fact.get("normalized_value")
    if normalized_value is None:
        return None
    candidate_value = parse_decimal(str(normalized_value))
    if unit["unit_match_status"] == "exact_label_match":
        gold_value = parse_decimal(str(target["gold_value"]))
    else:
        gold_rule = UNIT_REGISTRY[str(target["gold_unit"])]
        gold_value = parse_decimal(str(target["gold_value"])) * gold_rule.factor
    precision = target["precision"]
    if "comparison_gold_value" in precision:
        gold_value = parse_decimal(str(precision["comparison_gold_value"]))
    if precision["rule_id"] == "precision_rounding_quantum_v0.1" and unit["unit_match_status"] == "exact_label_match":
        local_precision = dict(precision)
        local_precision["canonical_quantum"] = precision["quantum"]
    elif precision["rule_id"] == "precision_absolute_tolerance_v0.1" and unit["unit_match_status"] == "exact_label_match":
        local_precision = dict(precision)
        local_precision["canonical_absolute_tolerance"] = precision["absolute_tolerance"]
    else:
        local_precision = precision
    direct_match = precision_matches(candidate_value, gold_value, local_precision)
    opposite_match = precision_matches(-candidate_value, gold_value, local_precision)
    if not direct_match and not opposite_match:
        return None
    return {
        "raw_unit_label": raw_unit,
        "unit": unit,
        "gold_comparison_value": canonical_decimal(gold_value),
        "candidate_comparison_value": canonical_decimal(candidate_value),
        "numeric_relation": "signed_equivalent" if direct_match else "opposite_sign_magnitude_only",
        "proposed_sign_relationship": "same_sign" if direct_match else "unresolved",
    }


def _make_candidate(
    target: Mapping[str, Any],
    fact: Mapping[str, Any],
    *,
    stage: int,
    generation_rule_id: str,
    comparison: Mapping[str, Any],
    parent_candidate_id: str | None = None,
    parent_source_check_status: str | None = None,
) -> dict[str, Any]:
    target_concept = target.get("gold_xbrl_concept") or None
    fact_concept = str(fact.get("concept", ""))
    if target_concept is None:
        concept_relation = "gold_concept_unavailable"
    elif target_concept == fact_concept:
        concept_relation = "same_exact_concept"
    else:
        concept_relation = "different_concept"
    fact_copy = json.loads(json.dumps(fact, ensure_ascii=False, sort_keys=True))
    fact_copy["raw_unit_label"] = comparison["raw_unit_label"]
    fact_copy["raw_unit_alias_rule_id"] = (
        RAW_XBRL_UNIT_REGISTRY[comparison["raw_unit_label"]].rule_id
        if comparison["raw_unit_label"] in RAW_XBRL_UNIT_REGISTRY
        else None
    )
    candidate = {
        "candidate_id": _candidate_id(
            str(target["target_id"]), stage, str(fact["fact_locator"]), parent_candidate_id
        ),
        "candidate_stage": stage,
        "parent_candidate_id": parent_candidate_id,
        "parent_source_check_status": parent_source_check_status,
        "generation_rule_id": generation_rule_id,
        "target_id": target["target_id"],
        "fact_locator": fact["fact_locator"],
        "fact": fact_copy,
        "concept_relation": concept_relation,
        "numeric_relation": comparison["numeric_relation"],
        "gold_comparison_value": comparison["gold_comparison_value"],
        "candidate_comparison_value": comparison["candidate_comparison_value"],
        "submitted_unit_label": target["gold_unit"],
        "reference_unit_label": comparison["raw_unit_label"],
        "unit_match_status": comparison["unit"]["unit_match_status"],
        "unit_equivalence_rule_id": comparison["unit"]["unit_equivalence_rule_id"],
        "comparison_dimension": comparison["unit"]["dimension"],
        "canonical_unit": comparison["unit"]["canonical_unit"],
        "precision_rule_id": target["precision"]["rule_id"],
        "proposed_sign_relationship": comparison["proposed_sign_relationship"],
        "initial_source_check_status": SOURCE_CHECK_UNRESOLVED,
        "source_check_status": SOURCE_CHECK_UNRESOLVED,
        "source_check_rationale": "",
        "source_check_evidence": "",
        "generation_reason": "",
        "human_review_status": "",
        "human_review_notes": "",
    }
    return candidate


def generate_stage1(target: Mapping[str, Any], facts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    chunks = set(target.get("approved_chunk_ids") or ())
    if not chunks:
        return []
    candidates: list[dict[str, Any]] = []
    for fact in sorted(facts, key=_fact_sort_key):
        if fact.get("chunk_id") not in chunks or fact.get("company") != target.get("entity_company"):
            continue
        comparison = _comparison(target, fact)
        if comparison is None:
            continue
        candidate = _make_candidate(
            target,
            fact,
            stage=1,
            generation_rule_id="stage1_direct_chunk_link_v0.1",
            comparison=comparison,
        )
        candidate["generation_reason"] = (
            "Authoritative fact chunk_id intersects approved gold chunk provenance; "
            "entity, frozen unit comparison, precision, and sign-generation predicates passed."
        )
        candidates.append(candidate)
    return _deduplicate(candidates)


def _same_temporal(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return _temporal(left) == _temporal(right)


def _same_dimensions(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return _dimensions(left) == _dimensions(right)


def generate_stage2(
    target: Mapping[str, Any],
    facts: Sequence[Mapping[str, Any]],
    stage1_candidates: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Generate cross-filing duplicates from passing source-check lineage."""
    candidates: list[dict[str, Any]] = []
    for parent in sorted(stage1_candidates, key=candidate_sort_key):
        if parent.get("source_check_status") != SOURCE_CHECK_PASS:
            continue
        parent_fact = parent["fact"]
        for fact in sorted(facts, key=_fact_sort_key):
            if fact.get("accession") == parent_fact.get("accession"):
                continue
            if fact.get("company") != parent_fact.get("company"):
                continue
            if fact.get("concept") != parent_fact.get("concept"):
                continue
            if not _same_temporal(fact, parent_fact) or not _same_dimensions(fact, parent_fact):
                continue
            comparison = _comparison(target, fact)
            if comparison is None or comparison["numeric_relation"] != "signed_equivalent":
                continue
            if comparison["candidate_comparison_value"] != parent["candidate_comparison_value"]:
                continue
            candidate = _make_candidate(
                target,
                fact,
                stage=2,
                generation_rule_id="stage2_passing_lineage_exact_duplicate_v0.1",
                comparison=comparison,
                parent_candidate_id=str(parent["candidate_id"]),
                parent_source_check_status=SOURCE_CHECK_PASS,
            )
            candidate["generation_reason"] = (
                "Cross-filing fact has the passing Stage-1 parent's entity, exact concept, "
                "economic dates, dimensions, and canonical signed quantity."
            )
            candidates.append(candidate)
    return _deduplicate(candidates)


def _target_temporal_matches(target: Mapping[str, Any], fact: Mapping[str, Any]) -> bool:
    requirement = target.get("temporal_requirement") or {}
    if requirement.get("kind") not in {"instant", "duration"}:
        return False
    return dict(requirement) == _temporal(fact)


def _target_dimensions_match(target: Mapping[str, Any], fact: Mapping[str, Any]) -> bool:
    requirement = target.get("dimensional_requirement") or {"availability": "unavailable"}
    if requirement.get("availability") != "exact":
        return True
    expected = sorted(
        requirement.get("dimensions", []), key=lambda item: (item["axis"], item["member"])
    )
    return expected == _dimensions(fact)


def generate_stage3(
    target: Mapping[str, Any],
    facts: Sequence[Mapping[str, Any]],
    prior_candidates: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    """Run the frozen constrained search, or report its closed limitation."""
    temporal = target.get("temporal_requirement") or {}
    if temporal.get("kind") not in {"instant", "duration"}:
        return [], "blocked_missing_exact_temporal_requirement"
    if any(
        item.get("source_check_status") == SOURCE_CHECK_PASS
        and _target_temporal_matches(target, item["fact"])
        for item in prior_candidates
    ):
        return [], "not_applicable_target_resolved_by_passing_candidate"
    eligible_accessions = set(target.get("stage3_eligible_accessions") or ())
    if not eligible_accessions:
        return [], "blocked_missing_deterministic_filing_eligibility"
    seen_locators = {item["fact_locator"] for item in prior_candidates}
    candidates: list[dict[str, Any]] = []
    for fact in sorted(facts, key=_fact_sort_key):
        if fact.get("fact_locator") in seen_locators:
            continue
        if fact.get("company") != target.get("entity_company"):
            continue
        if fact.get("accession") not in eligible_accessions:
            continue
        if not _target_temporal_matches(target, fact) or not _target_dimensions_match(target, fact):
            continue
        comparison = _comparison(target, fact)
        if comparison is None or comparison["numeric_relation"] != "signed_equivalent":
            continue
        candidate = _make_candidate(
            target,
            fact,
            stage=3,
            generation_rule_id="stage3_mechanical_constrained_search_v0.1",
            comparison=comparison,
        )
        candidate["generation_reason"] = (
            "Fact satisfies frozen entity, exact temporal, available dimension, filing "
            "eligibility, unit, signed-value, and precision predicates."
        )
        candidates.append(candidate)
    return _deduplicate(candidates), "completed"


def build_derived_input_lineage(
    required_input_ids: Sequence[str], input_statuses: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Represent every required input and its independently adjudicable route."""
    lineage: list[dict[str, Any]] = []
    for input_id in sorted(set(required_input_ids)):
        status = input_statuses.get(input_id)
        if status is None:
            lineage.append(
                {
                    "input_target_id": input_id,
                    "support_status": "missing_input_status",
                    "provenance_route": None,
                    "xbrl_proposed_status": None,
                }
            )
        else:
            lineage.append({"input_target_id": input_id, **dict(status)})
    return lineage


def _deduplicate(candidates: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    by_identity: dict[tuple[Any, ...], dict[str, Any]] = {}
    for candidate in candidates:
        identity = (
            candidate["target_id"],
            candidate["candidate_stage"],
            candidate["fact_locator"],
            candidate.get("parent_candidate_id"),
        )
        by_identity.setdefault(identity, candidate)
    return sorted(by_identity.values(), key=candidate_sort_key)


def apply_source_checks(
    candidates: Sequence[Mapping[str, Any]], checks: Mapping[str, Mapping[str, str]]
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for item in candidates:
        candidate = dict(item)
        check = checks.get(str(candidate["candidate_id"]))
        if check is not None:
            status = check["source_check_status"]
            if status not in SOURCE_CHECK_STATUSES:
                raise ValueError(f"invalid source-check status: {status!r}")
            candidate["source_check_status"] = status
            candidate["source_check_rationale"] = check.get("source_check_rationale", "")
            candidate["source_check_evidence"] = check.get("source_check_evidence", "")
        output.append(candidate)
    return sorted(output, key=candidate_sort_key)


def provisional_direct_status(
    candidates: Sequence[Mapping[str, Any]], stage3_state: str
) -> str:
    """Apply pending-review direct-target finalization without human approval."""
    if any(item.get("source_check_status") == SOURCE_CHECK_PASS for item in candidates):
        return "PROPOSED_MAPPED"
    if any(item.get("source_check_status") == SOURCE_CHECK_UNRESOLVED for item in candidates):
        return "PROPOSED_UNMAPPABLE"
    if stage3_state == "completed":
        return "PROPOSED_NO_XBRL_COUNTERPART_IN_FROZEN_CORPUS"
    return "PROPOSED_UNMAPPABLE"


def candidate_discovery_state(candidates: Sequence[Mapping[str, Any]]) -> str:
    """Summarize discovery/source-check evidence independently of final mapping."""
    if not candidates:
        return "NO_CANDIDATES_DISCOVERED"
    statuses = {item.get("source_check_status") for item in candidates}
    if SOURCE_CHECK_PASS in statuses:
        return "CANDIDATES_DISCOVERED_SOURCE_CHECK_PASS"
    if SOURCE_CHECK_UNRESOLVED in statuses:
        return "CANDIDATES_DISCOVERED_SOURCE_CHECK_PENDING"
    return "CANDIDATES_DISCOVERED_ALL_REJECTED"


def candidate_matches_temporal(
    candidate: Mapping[str, Any], resolved_temporal: Mapping[str, Any] | None
) -> bool:
    """Require exact equality between a candidate context and bound target time."""
    if not resolved_temporal or resolved_temporal.get("kind") not in {"instant", "duration"}:
        return False
    return _temporal(candidate["fact"]) == dict(resolved_temporal)


def temporal_precedence_direct_status(
    candidates: Sequence[Mapping[str, Any]],
    stage3_state: str,
    *,
    temporal_resolution_status: str,
    resolved_temporal: Mapping[str, Any] | None,
    unmappable_reason_code: str | None,
) -> str:
    """Apply v0.1.2 temporal precedence to provisional final adjudication."""
    if resolved_temporal is None:
        if unmappable_reason_code is not None:
            return "PROPOSED_UNMAPPABLE"
        return "PENDING_TEMPORAL_ADJUDICATION"
    consistent = [
        item for item in candidates if candidate_matches_temporal(item, resolved_temporal)
    ]
    if any(item.get("source_check_status") == SOURCE_CHECK_PASS for item in consistent):
        return "PROPOSED_MAPPED"
    if any(item.get("source_check_status") == SOURCE_CHECK_UNRESOLVED for item in consistent):
        return "PROPOSED_UNMAPPABLE"
    if stage3_state == "completed":
        return "PROPOSED_NO_XBRL_COUNTERPART_IN_FROZEN_CORPUS"
    return "PROPOSED_UNMAPPABLE"


def canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        + "\n"
    ).encode("utf-8")
