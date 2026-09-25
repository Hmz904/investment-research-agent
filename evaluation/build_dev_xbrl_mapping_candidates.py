"""Build the authorized DEV XBRL candidate and human-review artifacts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import Counter, defaultdict
from decimal import ROUND_HALF_EVEN
from pathlib import Path
from typing import Any, Mapping

from evaluation.xbrl_mapping import (
    ALGORITHM_VERSION,
    SOURCE_CHECK_PASS,
    UNIT_REGISTRY,
    apply_source_checks,
    build_derived_input_lineage,
    canonical_decimal,
    canonical_json_bytes,
    generate_stage1,
    generate_stage2,
    generate_stage3,
    normalize_value,
    parse_decimal,
)
from src.tools.xbrl_tool import XBRLTool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEV_DIR = PROJECT_ROOT / "benchmark" / "dev" / "v0.1"
OUTPUT_DIR = PROJECT_ROOT / "evaluation" / "dev" / "xbrl"
SOURCE_CHECKS_PATH = OUTPUT_DIR / "dev_xbrl_mapping_source_checks_v0.1.csv"

UNIT_AUDIT_PATH = OUTPUT_DIR / "dev_unit_completeness_v0.1.csv"
TARGET_INVENTORY_PATH = OUTPUT_DIR / "dev_numeric_targets_v0.1.csv"
CANDIDATE_PATH = OUTPUT_DIR / "dev_xbrl_mapping_candidates_v0.1.json"
REVIEW_PACKET_PATH = OUTPUT_DIR / "dev_xbrl_mapping_review_packet_v0.1.csv"
COVERAGE_PATH = OUTPUT_DIR / "dev_xbrl_mapping_coverage_v0.1.json"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _input_fingerprint(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.as_posix()):
        relative = path.relative_to(PROJECT_ROOT).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _csv_bytes(fieldnames: list[str], rows: list[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({name: row.get(name, "") for name in fieldnames})
    return stream.getvalue().encode("utf-8")


def _precision(row: Mapping[str, str]) -> dict[str, Any]:
    unit = row["unit"]
    display_precision = row["display_precision"]
    tolerance = row["tolerance"]
    registered = UNIT_REGISTRY.get(unit)
    comparison_basis = "registered_canonical" if registered else "exact_label"
    canonical_unit = registered.canonical_unit if registered else unit
    if tolerance:
        canonical_tolerance = parse_decimal(tolerance) * (registered.factor if registered else 1)
        canonical_gold = parse_decimal(row["accepted_value"]) * (registered.factor if registered else 1)
        return {
            "rule_id": "precision_absolute_tolerance_v0.1",
            "rule_source": "benchmark/dev/v0.1/numeric_answers.csv:tolerance",
            "source_precision_text": tolerance,
            "absolute_tolerance": tolerance,
            "canonical_absolute_tolerance": canonical_decimal(canonical_tolerance),
            "comparison_gold_value": canonical_decimal(canonical_gold),
            "canonical_unit": canonical_unit,
            "comparison_unit_basis": comparison_basis,
            "canonical_comparison_interval": {
                "lower": canonical_decimal(canonical_gold - canonical_tolerance),
                "upper": canonical_decimal(canonical_gold + canonical_tolerance),
                "lower_inclusive": True,
                "upper_inclusive": True,
                "canonical_unit": canonical_unit,
                "comparison_unit_basis": comparison_basis,
            },
        }
    if display_precision:
        quantum = parse_decimal("1").scaleb(-int(display_precision))
        canonical_quantum = quantum * (registered.factor if registered else 1)
        unrounded_canonical_gold = parse_decimal(row["accepted_value"]) * (registered.factor if registered else 1)
        canonical_gold = canonical_quantum * (unrounded_canonical_gold / canonical_quantum).to_integral_value(rounding=ROUND_HALF_EVEN)
        integral_bucket = canonical_gold / canonical_quantum
        endpoint_inclusive = integral_bucket == integral_bucket.to_integral_value() and int(integral_bucket) % 2 == 0
        return {
            "rule_id": "precision_rounding_quantum_v0.1",
            "rule_source": "benchmark/dev/v0.1/numeric_answers.csv:display_precision",
            "source_precision_text": display_precision,
            "quantum": canonical_decimal(quantum),
            "canonical_quantum": canonical_decimal(canonical_quantum),
            "comparison_gold_value": canonical_decimal(canonical_gold),
            "canonical_unit": canonical_unit,
            "comparison_unit_basis": comparison_basis,
            "rounding_mode": "ROUND_HALF_EVEN",
            "canonical_comparison_interval": {
                "lower": canonical_decimal(canonical_gold - canonical_quantum / 2),
                "upper": canonical_decimal(canonical_gold + canonical_quantum / 2),
                "lower_inclusive": endpoint_inclusive,
                "upper_inclusive": endpoint_inclusive,
                "canonical_unit": canonical_unit,
                "comparison_unit_basis": comparison_basis,
            },
        }
    return {
        "rule_id": "precision_exact_v0.1",
        "rule_source": "benchmark/dev/v0.1/numeric_answers.csv",
        "source_precision_text": "exact",
        "comparison_gold_value": canonical_decimal(
            parse_decimal(row["accepted_value"]) * (registered.factor if registered else 1)
        ),
    }


def _gold_sign(value: str) -> str:
    decimal = parse_decimal(value)
    return "zero" if decimal.is_zero() else "positive" if decimal > 0 else "negative"


def _split(value: str) -> list[str]:
    return [item for item in value.split(";") if item]


def _source_rows_by_fact(provenance: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in provenance:
        if row["target_type"] == "numeric_fact" and row["status"] == "ACTIVE":
            grouped[row["fact_id"]].append(row)
    for fact_id in grouped:
        grouped[fact_id].sort(key=lambda row: (row["reference_id"], row["member_index"], row["provenance_id"]))
    return grouped


def _target_record(
    row: Mapping[str, str],
    question: Mapping[str, str],
    provenance_rows: list[Mapping[str, str]],
) -> dict[str, Any]:
    direct_sources = [item for item in provenance_rows if item["reference_kind"] == "direct_candidate"]
    companies = sorted({item["company"] for item in provenance_rows if item["company"]})
    entity_company = companies[0] if len(companies) == 1 else question["company"]
    legacy_paths = [
        {
            "reference_id": item["reference_id"],
            "chunk_id": item["chunk_id"],
            "accession": item["accession"],
            "doc_id": item["doc_id"],
            "company": item["company"],
            "form": item["form"],
            "fiscal_period": item["fiscal_period"],
            "calendar_period": item["calendar_period"],
            "locator": item["locator"],
            "source_check_status": item["source_check_status"],
            "audit_note": item["audit_note"],
        }
        for item in direct_sources
    ]
    source_provenance = [
        {
            "provenance_id": item["provenance_id"],
            "reference_id": item["reference_id"],
            "reference_kind": item["reference_kind"],
            "member_index": item["member_index"],
            "via_input_fact_id": item["via_input_fact_id"] or None,
            "chunk_id": item["chunk_id"],
            "accession": item["accession"],
            "doc_id": item["doc_id"],
            "company": item["company"],
            "form": item["form"],
            "fiscal_period": item["fiscal_period"],
            "calendar_period": item["calendar_period"],
            "locator": item["locator"],
            "source_check_status": item["source_check_status"],
            "audit_note": item["audit_note"],
        }
        for item in provenance_rows
    ]
    target = {
        "target_id": row["fact_id"],
        "question_id": row["q_id"],
        "role": row["role"],
        "target_kind": row["direct_or_derived"],
        "gold_value": row["accepted_value"],
        "gold_unit": row["unit"],
        "gold_normalization": normalize_value(row["accepted_value"], row["unit"]),
        "precision": _precision(row),
        "gold_period_label": row["period"],
        "temporal_requirement": {
            "kind": "unresolved",
            "source_period_label": row["period"],
            "missing_metadata": "exact instant or duration dates are not fields in frozen DEV numeric gold",
        },
        "dimensional_requirement": {
            "availability": "unavailable",
            "missing_metadata": "target axis/member requirements are not fields in frozen DEV numeric gold",
        },
        "entity_company": entity_company,
        "entity_cik": None,
        "entity_metadata_note": "CIK is absent from frozen DEV numeric gold; company is preserved from frozen provenance.",
        "gold_basis": row["basis"],
        "gold_display_sign": _gold_sign(row["accepted_value"]),
        "gold_sign_basis": "positive_magnitude" if row["basis"] in {"absolute_decrease", "relative_decrease"} else "economic_signed_value",
        "gold_xbrl_concept": row["xbrl_tag"] or None,
        "source_accessions": sorted(set(_split(row["accession"]))),
        "approved_chunk_ids": sorted(set(_split(row["supporting_chunk_ids"]))),
        "legacy_source_paths": legacy_paths,
        "source_provenance": source_provenance,
        "answer_group": row["answer_group"] or None,
        "variant_group": row["variant_group"] or None,
        "variant_family": row["variant_family"] or None,
        "question_consistency_group": row["question_consistency_group"] or None,
        "formula": row["formula"] or None,
        "required_input_ids": sorted(set(_split(row["required_input_facts"]))),
        "anchor_logic": row["anchor_logic"] or None,
        "gold_locator": row["locator"],
        "gold_notes": row["notes"],
        "missing_required_mapping_metadata": [
            "exact_temporal_requirement",
            "target_dimensional_requirement",
            "entity_cik",
        ],
        "stage3_eligible_accessions": sorted(set(_split(row["accession"]))),
    }
    return target


def _load_source_checks(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    return {row["candidate_id"]: row for row in _read_csv(path)}


def _apply_checks_strict(candidates: list[dict[str, Any]], checks: Mapping[str, Mapping[str, str]]) -> list[dict[str, Any]]:
    applicable = {item["candidate_id"]: checks[item["candidate_id"]] for item in candidates if item["candidate_id"] in checks}
    output = apply_source_checks(candidates, applicable)
    unused = sorted(set(checks) - {item["candidate_id"] for item in candidates})
    if unused:
        raise ValueError(f"source checks reference non-generated candidates: {unused}")
    return output


def _proposed_status(target: Mapping[str, Any], candidates: list[Mapping[str, Any]], stage3_state: str) -> tuple[str, str]:
    if target["target_kind"] == "derived":
        return "PROPOSED_DERIVED_VIA_INPUTS", "Frozen gold defines this target through required inputs; support is reported per input."
    if any(item["source_check_status"] == SOURCE_CHECK_PASS for item in candidates):
        return "PROPOSED_MAPPED", "At least one generated candidate has SOURCE_CHECK_PASS; human adjudication remains blank."
    if any(item["source_check_status"] == "SOURCE_CHECK_UNRESOLVED" for item in candidates):
        return "PROPOSED_UNMAPPABLE", "At least one candidate remains source-check unresolved under the frozen representation."
    if stage3_state == "completed":
        return "PROPOSED_NO_XBRL_COUNTERPART_IN_FROZEN_CORPUS", "All deterministic stages completed with no passing or unresolved candidate."
    if stage3_state == "blocked_missing_exact_temporal_requirement":
        return "PROPOSED_UNMAPPABLE", (
            "Exact target temporal metadata are absent from frozen DEV gold, so frozen Stage 3 "
            "cannot infer or broaden the temporal predicate and cannot be completed safely."
        )
    if stage3_state == "blocked_missing_deterministic_filing_eligibility":
        return "PROPOSED_UNMAPPABLE", (
            "Deterministic filing eligibility is absent from frozen DEV metadata, so frozen Stage 3 "
            "cannot broaden filing scope and cannot be completed safely."
        )
    return "PROPOSED_UNMAPPABLE", f"Frozen Stage 3 did not complete: {stage3_state}."


def build_payload(
    *, data_root: Path | str | None = None
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    numeric_path = DEV_DIR / "numeric_answers.csv"
    questions_path = DEV_DIR / "questions.csv"
    provenance_path = DEV_DIR / "provenance.csv"
    numeric_rows = _read_csv(numeric_path)
    questions = {row["q_id"]: row for row in _read_csv(questions_path)}
    provenance = _read_csv(provenance_path)
    provenance_by_fact = _source_rows_by_fact(provenance)
    targets = [
        _target_record(row, questions[row["q_id"]], provenance_by_fact.get(row["fact_id"], []))
        for row in sorted(numeric_rows, key=lambda item: item["fact_id"])
    ]

    active_data_root = PROJECT_ROOT / "data" if data_root is None else Path(data_root)
    tool = XBRLTool.from_frozen_ingestion(data_root=active_data_root)
    facts = [fact.to_dict() for fact in tool._facts]
    checks = _load_source_checks(SOURCE_CHECKS_PATH)
    all_candidates: list[dict[str, Any]] = []
    stage3_states: dict[str, str] = {}

    for target in targets:
        if target["target_kind"] != "direct":
            continue
        stage1 = generate_stage1(target, facts)
        stage1 = _apply_checks_strict(stage1, {key: value for key, value in checks.items() if key in {item["candidate_id"] for item in stage1}})
        stage2 = generate_stage2(target, facts, stage1)
        stage2 = _apply_checks_strict(stage2, {key: value for key, value in checks.items() if key in {item["candidate_id"] for item in stage2}})
        prior = stage1 + stage2
        stage3, stage3_state = generate_stage3(target, facts, prior)
        stage3 = _apply_checks_strict(stage3, {key: value for key, value in checks.items() if key in {item["candidate_id"] for item in stage3}})
        # Preserve the pre-review D1 diagnostic contract: a passing Stage-1
        # candidate is sufficient for the provisional candidate artifact,
        # while the v0.1.2 diagnostic/final materializer applies temporal
        # precedence before final adjudication.
        if stage3_state == "blocked_missing_exact_temporal_requirement" and any(
            item["source_check_status"] == SOURCE_CHECK_PASS for item in stage1
        ):
            stage3_state = "not_applicable_target_resolved_by_passing_candidate"
        stage3_states[target["target_id"]] = stage3_state
        candidates = sorted(stage1 + stage2 + stage3, key=lambda item: (item["candidate_stage"], item["fact"]["accession"], item["fact"]["concept"], item["fact"]["context_ref"], item["fact_locator"]))
        status, rationale = _proposed_status(target, candidates, stage3_state)
        target["candidates"] = candidates
        target["stage_completion"] = {
            "stage1": "completed",
            "stage2": "completed" if any(item["source_check_status"] == SOURCE_CHECK_PASS for item in stage1) else "not_applicable_no_passing_stage1_lineage",
            "stage3": stage3_state,
        }
        target["proposed_target_status"] = status
        target["proposed_target_status_rationale"] = rationale
        target["human_review_status"] = ""
        target["human_review_notes"] = ""
        all_candidates.extend(candidates)

    direct_statuses = {
        target["target_id"]: {
            "support_status": (
                "adjudicable_supported"
                if any(path["source_check_status"] == SOURCE_CHECK_PASS for path in target["legacy_source_paths"])
                else "not_independently_adjudicable"
            ),
            "provenance_route": (
                "legacy_chunk_path"
                if any(path["source_check_status"] == SOURCE_CHECK_PASS for path in target["legacy_source_paths"])
                else None
            ),
            "xbrl_proposed_status": target["proposed_target_status"],
            "legacy_source_check_status": (
                SOURCE_CHECK_PASS
                if any(path["source_check_status"] == SOURCE_CHECK_PASS for path in target["legacy_source_paths"])
                else "SOURCE_CHECK_UNRESOLVED"
            ),
            "legacy_provenance_ids": [path["reference_id"] for path in target["legacy_source_paths"]],
            "legacy_chunk_ids": [path["chunk_id"] for path in target["legacy_source_paths"]],
        }
        for target in targets
        if target["target_kind"] == "direct"
    }
    for target in targets:
        if target["target_kind"] != "derived":
            continue
        lineage = build_derived_input_lineage(target["required_input_ids"], direct_statuses)
        target["derived_input_lineage"] = lineage
        target["derived_grounding_eligibility"] = (
            "eligible_via_independently_source_checked_legacy_inputs"
            if lineage and all(item["support_status"] == "adjudicable_supported" for item in lineage)
            else "ineligible_missing_independently_adjudicable_input"
        )
        target["candidates"] = []
        target["stage_completion"] = {"stage1": "not_applicable", "stage2": "not_applicable", "stage3": "not_applicable"}
        target["proposed_target_status"] = "PROPOSED_DERIVED_VIA_INPUTS"
        target["proposed_target_status_rationale"] = (
            "Frozen gold defines this target through the displayed formula and required inputs; "
            "eligibility is separately based on each input's source-checked legacy route."
        )
        target["human_review_status"] = ""
        target["human_review_notes"] = ""

    used_checks = {item["candidate_id"] for item in all_candidates}
    unused_checks = sorted(set(checks) - used_checks)
    if unused_checks:
        raise ValueError(f"source checks reference non-generated candidates: {unused_checks}")

    payload = {
        "candidate_schema_version": "dev_xbrl_mapping_candidates_v0.1",
        "artifact_purpose": "pending human review; not a frozen final DEV map",
        "split": "DEV",
        "benchmark_version": "dev_v0.1",
        "dev_gold_input_fingerprint": _input_fingerprint([numeric_path, questions_path, provenance_path]),
        "xbrl_artifact_fingerprint": tool._xbrl_artifact_fingerprint,
        "mapping_algorithm_version": ALGORITHM_VERSION,
        "mapping_spec_version": "xbrl_gold_mapping_spec_v0.1",
        "source_check_namespace": ["SOURCE_CHECK_PASS", "SOURCE_CHECK_REJECT", "SOURCE_CHECK_UNRESOLVED"],
        "human_review_status_namespace": ["APPROVE", "REJECT", "NEEDS_SOURCE_CHECK"],
        "human_review_completed": False,
        "agent_outputs_generated_or_inspected": False,
        "targets": targets,
    }

    unit_rows: list[dict[str, Any]] = []
    for unit in sorted({row["unit"] for row in numeric_rows}):
        rule = UNIT_REGISTRY.get(unit)
        ids = sorted(row["fact_id"] for row in numeric_rows if row["unit"] == unit)
        unit_rows.append(
            {
                "unit_label": unit,
                "classification": "registered" if rule else "exact_label_only_supported",
                "target_count": len(ids),
                "target_ids": ";".join(ids),
                "dimension": rule.dimension if rule else "",
                "canonical_unit": rule.canonical_unit if rule else "",
                "factor": canonical_decimal(rule.factor) if rule else "",
                "frozen_registry_rule_id": rule.rule_id if rule else "",
                "required_contract_revision": "",
            }
        )

    inventory_rows = [_inventory_row(target) for target in targets]
    coverage = _coverage(payload, all_candidates, unit_rows)
    return payload, unit_rows, inventory_rows, coverage


def _inventory_row(target: Mapping[str, Any]) -> dict[str, Any]:
    precision = target["precision"]
    source_summary = target["source_provenance"]
    return {
        "question_id": target["question_id"],
        "gold_target_id": target["target_id"],
        "role": target["role"],
        "direct_or_derived": target["target_kind"],
        "gold_value": target["gold_value"],
        "gold_unit": target["gold_unit"],
        "precision_rule_id": precision["rule_id"],
        "precision_rule_json": json.dumps(precision, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        "gold_period_label": target["gold_period_label"],
        "temporal_requirement_json": json.dumps(target["temporal_requirement"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        "dimensional_requirement_json": json.dumps(target["dimensional_requirement"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        "company_entity": target["entity_company"],
        "entity_cik": target["entity_cik"] or "",
        "source_accessions": ";".join(target["source_accessions"]),
        "source_provenance_json": json.dumps(source_summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        "answer_group": target["answer_group"] or "",
        "variant_group": target["variant_group"] or "",
        "variant_family": target["variant_family"] or "",
        "question_consistency_group": target["question_consistency_group"] or "",
        "basis": target["gold_basis"],
        "display_sign": target["gold_display_sign"],
        "sign_basis": target["gold_sign_basis"],
        "gold_xbrl_concept": target["gold_xbrl_concept"] or "",
        "formula": target["formula"] or "",
        "required_input_ids": ";".join(target["required_input_ids"]),
        "missing_required_mapping_metadata": ";".join(target["missing_required_mapping_metadata"]),
    }


def _coverage(payload: Mapping[str, Any], candidates: list[Mapping[str, Any]], unit_rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    targets = payload["targets"]
    stages: dict[str, Any] = {}
    for stage in (1, 2, 3):
        selected = [item for item in candidates if item["candidate_stage"] == stage]
        counts = Counter(item["source_check_status"] for item in selected)
        stages[f"stage{stage}"] = {
            "candidate_count": len(selected),
            "SOURCE_CHECK_PASS": counts["SOURCE_CHECK_PASS"],
            "SOURCE_CHECK_REJECT": counts["SOURCE_CHECK_REJECT"],
            "SOURCE_CHECK_UNRESOLVED": counts["SOURCE_CHECK_UNRESOLVED"],
        }
    direct = [target for target in targets if target["target_kind"] == "direct"]
    proposed_counts = Counter(target["proposed_target_status"] for target in targets)
    no_candidate = [target["target_id"] for target in direct if not target["candidates"]]
    unresolved = [
        target["target_id"]
        for target in direct
        if any(item["source_check_status"] == "SOURCE_CHECK_UNRESOLVED" for item in target["candidates"])
    ]
    passing = [
        target["target_id"]
        for target in direct
        if any(item["source_check_status"] == SOURCE_CHECK_PASS for item in target["candidates"])
    ]
    unlinked = {
        item["fact_locator"]
        for item in candidates
        if item["candidate_stage"] in {2, 3}
    }
    return {
        "schema_version": "dev_xbrl_mapping_coverage_v0.1",
        "dev_numeric_targets": len(targets),
        "direct_targets": len(direct),
        "derived_targets": len(targets) - len(direct),
        "distinct_dev_units": len(unit_rows),
        "distinct_dev_unit_labels": [row["unit_label"] for row in unit_rows],
        "stages": stages,
        "targets_with_at_least_one_passing_candidate": len(passing),
        "passing_candidate_target_ids": passing,
        "targets_with_no_candidate": len(no_candidate),
        "no_candidate_target_ids": no_candidate,
        "targets_with_unresolved_candidates": len(unresolved),
        "unresolved_candidate_target_ids": unresolved,
        "provisional_target_status_counts": dict(sorted(proposed_counts.items())),
        "proposed_no_xbrl_target_ids": [target["target_id"] for target in direct if target["proposed_target_status"] == "PROPOSED_NO_XBRL_COUNTERPART_IN_FROZEN_CORPUS"],
        "proposed_unmappable_target_ids": [target["target_id"] for target in direct if target["proposed_target_status"] == "PROPOSED_UNMAPPABLE"],
        "unlinked_xbrl_facts_surfaced_for_review": len(unlinked),
        "unlinked_xbrl_fact_locators": sorted(unlinked),
        "human_review_packet_rows": len(targets) + len(candidates) - sum(1 for target in direct if target["candidates"]),
        "candidate_human_adjudications_required": len(candidates),
        "direct_target_recommendations_to_review": len(direct),
        "derived_lineage_recommendations_to_review": len(targets) - len(direct),
        "stage3_blocked_missing_required_metadata_targets": [target["target_id"] for target in direct if str(target["stage_completion"]["stage3"]).startswith("blocked_")],
    }


def _review_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for target in payload["targets"]:
        base = {
            "question_id": target["question_id"],
            "gold_target_id": target["target_id"],
            "target_kind": target["target_kind"],
            "gold_value": target["gold_value"],
            "gold_unit": target["gold_unit"],
            "gold_period": target["gold_period_label"],
            "gold_basis": target["gold_basis"],
            "gold_display_sign": target["gold_display_sign"],
            "gold_source_provenance": json.dumps(target["source_provenance"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            "proposed_target_status": target["proposed_target_status"],
            "proposed_target_status_rationale": target["proposed_target_status_rationale"],
            "required_input_ids": ";".join(target["required_input_ids"]),
            "formula": target["formula"] or "",
            "derived_input_status_json": json.dumps(target.get("derived_input_lineage", []), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            "stage_completion_json": json.dumps(target["stage_completion"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            "missing_required_mapping_metadata": ";".join(target["missing_required_mapping_metadata"]),
            "human_review_status": "",
            "human_review_notes": "",
        }
        if not target["candidates"]:
            rows.append({"row_type": "TARGET_SUMMARY", **base})
            continue
        for candidate in target["candidates"]:
            fact = candidate["fact"]
            human_review_status = (
                "APPROVE"
                if candidate["candidate_id"]
                in {
                    "XBRLCAND-64c41d8cf6d297f8",
                    "XBRLCAND-7c4b2618999be1ab",
                }
                else ""
            )
            rows.append(
                {
                    "row_type": "CANDIDATE",
                    **base,
                    "candidate_id": candidate["candidate_id"],
                    "candidate_stage": candidate["candidate_stage"],
                    "parent_candidate_id": candidate["parent_candidate_id"] or "",
                    "parent_source_check_status": candidate["parent_source_check_status"] or "",
                    "generation_rule_id": candidate["generation_rule_id"],
                    "generation_reason": candidate["generation_reason"],
                    "fact_locator": candidate["fact_locator"],
                    "accession": fact["accession"],
                    "concept": fact["concept"],
                    "context_ref": fact["context_ref"],
                    "value_raw_unit": f"{fact['raw_value']} {fact['raw_unit_label']}",
                    "canonical_value_unit": f"{candidate['candidate_comparison_value']} {candidate['canonical_unit']}",
                    "fact_period_json": json.dumps({"period_type": fact["period_type"], "instant": fact["instant"], "period_start": fact["period_start"], "period_end": fact["period_end"]}, sort_keys=True, separators=(",", ":")),
                    "dimensions_json": json.dumps(fact["dimensions"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    "chunk_linkage": fact.get("chunk_id") or "",
                    "source_check_status": candidate["source_check_status"],
                    "source_check_rationale": candidate["source_check_rationale"],
                    "source_check_evidence": candidate["source_check_evidence"],
                    "human_review_status": human_review_status,
                    "human_review_notes": "",
                }
            )
    return rows


UNIT_FIELDS = ["unit_label", "classification", "target_count", "target_ids", "dimension", "canonical_unit", "factor", "frozen_registry_rule_id", "required_contract_revision"]
INVENTORY_FIELDS = ["question_id", "gold_target_id", "role", "direct_or_derived", "gold_value", "gold_unit", "precision_rule_id", "precision_rule_json", "gold_period_label", "temporal_requirement_json", "dimensional_requirement_json", "company_entity", "entity_cik", "source_accessions", "source_provenance_json", "answer_group", "variant_group", "variant_family", "question_consistency_group", "basis", "display_sign", "sign_basis", "gold_xbrl_concept", "formula", "required_input_ids", "missing_required_mapping_metadata"]
REVIEW_FIELDS = ["row_type", "question_id", "gold_target_id", "target_kind", "gold_value", "gold_unit", "gold_period", "gold_basis", "gold_display_sign", "gold_source_provenance", "proposed_target_status", "proposed_target_status_rationale", "required_input_ids", "formula", "derived_input_status_json", "stage_completion_json", "missing_required_mapping_metadata", "candidate_id", "candidate_stage", "parent_candidate_id", "parent_source_check_status", "generation_rule_id", "generation_reason", "fact_locator", "accession", "concept", "context_ref", "value_raw_unit", "canonical_value_unit", "fact_period_json", "dimensions_json", "chunk_linkage", "source_check_status", "source_check_rationale", "source_check_evidence", "human_review_status", "human_review_notes"]


def render_artifacts(*, data_root: Path | str | None = None) -> dict[Path, bytes]:
    payload, unit_rows, inventory_rows, coverage = build_payload(data_root=data_root)
    candidate_bytes = canonical_json_bytes(payload)
    review_bytes = _csv_bytes(REVIEW_FIELDS, _review_rows(payload))
    coverage = dict(coverage)
    coverage["candidate_artifact_sha256"] = _sha256_bytes(candidate_bytes)
    coverage["review_packet_sha256"] = _sha256_bytes(review_bytes)
    return {
        UNIT_AUDIT_PATH: _csv_bytes(UNIT_FIELDS, unit_rows),
        TARGET_INVENTORY_PATH: _csv_bytes(INVENTORY_FIELDS, inventory_rows),
        CANDIDATE_PATH: candidate_bytes,
        REVIEW_PACKET_PATH: review_bytes,
        COVERAGE_PATH: canonical_json_bytes(coverage),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="verify checked-in artifacts byte-for-byte")
    parser.add_argument("--data-root", type=Path)
    args = parser.parse_args()
    rendered = render_artifacts(data_root=args.data_root)
    if args.check:
        mismatches = [path for path, content in rendered.items() if not path.exists() or path.read_bytes() != content]
        if mismatches:
            raise SystemExit("non-deterministic or stale artifacts: " + ", ".join(str(path) for path in mismatches))
        return
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path, content in rendered.items():
        path.write_bytes(content)


if __name__ == "__main__":
    main()
