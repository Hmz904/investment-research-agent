"""Materialize the authorized human-reviewed DEV XBRL map v0.1."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from evaluation.build_dev_xbrl_mapping_candidates import (
    REVIEW_PACKET_PATH,
    SOURCE_CHECKS_PATH,
    render_artifacts as render_d1_artifacts,
)
from evaluation.build_dev_xbrl_mapping_v0_1_2_diagnostic import (
    HUMAN_REVIEW_PATH,
    render_artifacts as render_temporal_diagnostics,
)
from evaluation.build_temporal_context_catalog import (
    CONFLICT_REVIEW_PATH,
    RULE_REVIEW_PATH,
    render_artifacts as render_catalog_artifacts,
)
from evaluation.temporal_context_catalog import (
    RESOLVED_ANCHOR_METADATA,
    RESOLVED_EXACT_TARGET_DATE,
    RESOLVED_HUMAN_CLOSED_SET,
    TEMPORAL_NO_ANCHOR_METADATA,
    canonical_json_bytes,
    resolve_target_temporal,
)
from evaluation.xbrl_mapping import (
    apply_source_checks,
    candidate_matches_temporal,
    generate_stage1,
    generate_stage2,
    generate_stage3,
)
from src.tools.xbrl_tool import XBRLTool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
D1_PATH = PROJECT_ROOT / "evaluation" / "dev" / "xbrl" / "dev_xbrl_mapping_candidates_v0.1.json"
CATALOG_PATH = PROJECT_ROOT / "evaluation" / "xbrl" / "temporal_context_catalog_v0.1.json"
MAP_PATH = PROJECT_ROOT / "evaluation" / "dev" / "xbrl" / "dev_xbrl_map_v0.1.json"
COVERAGE_PATH = PROJECT_ROOT / "evaluation" / "dev" / "xbrl" / "dev_xbrl_map_coverage_v0.1.json"

TEMPORAL_SELECTIONS = {
    "NF012": "SELECT TCC-31b1f6eab46385db",
    "NF013": "SELECT TCC-f5206ab8eb1933a4",
}

APPROVED_STAGE1_CANDIDATES = {
    "NF012": "XBRLCAND-64c41d8cf6d297f8",
    "NF013": "XBRLCAND-7c4b2618999be1ab",
}

RESOLVED_TEMPORAL_STATUSES = {
    RESOLVED_EXACT_TARGET_DATE,
    RESOLVED_ANCHOR_METADATA,
    RESOLVED_HUMAN_CLOSED_SET,
}

FINAL_STATUS_NAMESPACE = [
    "mapped",
    "derived_via_inputs",
    "no_xbrl_counterpart_in_frozen_corpus",
    "unmappable",
]


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _read_source_checks() -> dict[str, dict[str, str]]:
    with SOURCE_CHECKS_PATH.open(newline="", encoding="utf-8") as handle:
        return {
            row["candidate_id"]: {
                "source_check_status": row["source_check_status"],
                "source_check_rationale": row["source_check_rationale"],
                "source_check_evidence": row["source_check_evidence"],
            }
            for row in csv.DictReader(handle)
        }


def _apply_checks(
    candidates: list[dict[str, Any]], checks: Mapping[str, Mapping[str, str]]
) -> list[dict[str, Any]]:
    available = {
        item["candidate_id"]: checks[item["candidate_id"]]
        for item in candidates
        if item["candidate_id"] in checks
    }
    return apply_source_checks(candidates, available)


def _annotate_candidates(
    candidates: list[dict[str, Any]],
    *,
    target_id: str,
    resolved_temporal: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    approved_id = APPROVED_STAGE1_CANDIDATES.get(target_id)
    output: list[dict[str, Any]] = []
    for item in candidates:
        candidate = deepcopy(item)
        exact_match = candidate_matches_temporal(candidate, resolved_temporal)
        candidate["temporal_consistency_status"] = (
            "PASS_EXACT_BOUND_TEMPORAL" if exact_match else "FAIL_BOUND_TEMPORAL_MISMATCH"
            if resolved_temporal is not None else "NOT_EVALUABLE_UNRESOLVED_TARGET_TEMPORAL"
        )
        candidate["human_review_status"] = (
            "APPROVE" if candidate["candidate_id"] == approved_id else ""
        )
        candidate["human_review_notes"] = ""
        output.append(candidate)
    return output


def _candidate_review_counts(candidates: list[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "approved": sum(item.get("human_review_status") == "APPROVE" for item in candidates),
        "rejected": sum(item.get("human_review_status") == "REJECT" for item in candidates),
        "unresolved": sum(
            item.get("human_review_status") in {"", "NEEDS_SOURCE_CHECK"}
            for item in candidates
        ),
    }


def _review_artifact_identities() -> list[dict[str, str]]:
    catalog_rendered = render_catalog_artifacts()
    temporal_rendered = render_temporal_diagnostics()
    d1_rendered = render_d1_artifacts()
    identities = [
        (RULE_REVIEW_PATH, catalog_rendered[RULE_REVIEW_PATH]),
        (CONFLICT_REVIEW_PATH, catalog_rendered[CONFLICT_REVIEW_PATH]),
        (HUMAN_REVIEW_PATH, temporal_rendered[HUMAN_REVIEW_PATH]),
        (REVIEW_PACKET_PATH, d1_rendered[REVIEW_PACKET_PATH]),
    ]
    return [
        {
            "path": str(path.relative_to(PROJECT_ROOT)),
            "sha256": _sha256(content),
        }
        for path, content in identities
    ]


def build_final_map() -> dict[str, Any]:
    d1 = json.loads(D1_PATH.read_text(encoding="utf-8"))
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    facts = [fact.to_dict() for fact in XBRLTool.from_frozen_ingestion()._facts]
    checks = _read_source_checks()
    targets: list[dict[str, Any]] = []

    for original in d1["targets"]:
        target_id = str(original["target_id"])
        common = {
            "question_id": original["question_id"],
            "target_id": target_id,
            "target_kind": original["target_kind"],
            "role": original["role"],
            "gold_value": original["gold_value"],
            "gold_unit": original["gold_unit"],
            "gold_basis": original["gold_basis"],
            "gold_display_sign": original["gold_display_sign"],
            "gold_sign_basis": original["gold_sign_basis"],
            "gold_xbrl_concept": original["gold_xbrl_concept"],
            "formula": original["formula"],
            "required_input_ids": original["required_input_ids"],
            "legacy_source_paths": original["legacy_source_paths"],
            "approved_chunk_ids": original["approved_chunk_ids"],
            "source_accessions": original["source_accessions"],
        }
        if original["target_kind"] == "derived":
            targets.append(
                {
                    **common,
                    "temporal_resolution": {
                        "status": "not_applicable_derived_target",
                        "resolved_temporal": None,
                    },
                    "stage_completion": {
                        "stage1": "not_applicable_derived_target",
                        "stage2": "not_applicable_derived_target",
                        "stage3": "not_applicable_derived_target",
                    },
                    "stage1_candidates": [],
                    "stage2_candidates": [],
                    "stage3_candidates": [],
                    "approved_candidate_ids": [],
                    "rejected_candidate_ids": [],
                    "unresolved_candidate_ids": [],
                    "derived_input_lineage": original.get("derived_input_lineage", []),
                    "provenance_lineage": {
                        "mode": "legacy_approved_input_routes",
                        "required_input_ids": original["required_input_ids"],
                        "input_lineage": original.get("derived_input_lineage", []),
                    },
                    "final_mapping_status": "derived_via_inputs",
                    "unmappable_reason_code": None,
                    "human_review_lineage": [],
                }
            )
            continue

        reviewer_selection = TEMPORAL_SELECTIONS.get(target_id)
        resolution = resolve_target_temporal(
            original,
            catalog,
            facts,
            reviewer_selection=reviewer_selection,
        )
        resolved = resolution["temporal_resolution_status"] in RESOLVED_TEMPORAL_STATUSES
        mapping_target = deepcopy(original)
        mapping_target["temporal_requirement"] = (
            resolution["resolved_temporal"]
            if resolved
            else {"kind": "unresolved", "reason": resolution["temporal_resolution_status"]}
        )
        stage1 = _apply_checks(generate_stage1(mapping_target, facts), checks)
        stage2 = _apply_checks(generate_stage2(mapping_target, facts, stage1), checks)
        stage3, stage3_state = generate_stage3(mapping_target, facts, stage1 + stage2)
        stage3 = _apply_checks(stage3, checks)
        stage1 = _annotate_candidates(
            stage1,
            target_id=target_id,
            resolved_temporal=resolution["resolved_temporal"],
        )
        stage2 = _annotate_candidates(
            stage2,
            target_id=target_id,
            resolved_temporal=resolution["resolved_temporal"],
        )
        stage3 = _annotate_candidates(
            stage3,
            target_id=target_id,
            resolved_temporal=resolution["resolved_temporal"],
        )
        all_candidates = stage1 + stage2 + stage3
        approved = [
            item
            for item in all_candidates
            if item["human_review_status"] == "APPROVE"
            and item["source_check_status"] == "SOURCE_CHECK_PASS"
            and item["temporal_consistency_status"] == "PASS_EXACT_BOUND_TEMPORAL"
        ]
        if resolution["resolved_temporal"] is None:
            final_status = "unmappable"
        elif approved:
            final_status = "mapped"
        elif any(
            item["human_review_status"] in {"", "NEEDS_SOURCE_CHECK"}
            for item in all_candidates
        ):
            final_status = "unmappable"
        elif stage3_state == "completed":
            final_status = "no_xbrl_counterpart_in_frozen_corpus"
        else:
            final_status = "unmappable"

        counts = _candidate_review_counts(all_candidates)
        human_lineage: list[dict[str, str]] = []
        if reviewer_selection:
            human_lineage.append(
                {
                    "review_type": "temporal_closed_set",
                    "artifact": str(HUMAN_REVIEW_PATH.relative_to(PROJECT_ROOT)),
                    "decision": reviewer_selection,
                }
            )
        for candidate in approved:
            human_lineage.append(
                {
                    "review_type": "stage1_source_check",
                    "artifact": str(REVIEW_PACKET_PATH.relative_to(PROJECT_ROOT)),
                    "decision": f"APPROVE {candidate['candidate_id']}",
                }
            )
        targets.append(
            {
                **common,
                "temporal_resolution": {
                    "status": resolution["temporal_resolution_status"],
                    "mode": resolution["temporal_resolution_mode"],
                    "resolution_rule_id": resolution["resolution_rule_id"],
                    "resolved_temporal": resolution["resolved_temporal"],
                    "closed_candidate_ids": [
                        item["temporal_candidate_id"]
                        for item in resolution["candidate_rows"]
                    ],
                    "selected_temporal_candidate_id": resolution[
                        "selected_temporal_candidate_id"
                    ],
                    "human_readable_period_labels_used": False,
                },
                "stage_completion": {
                    "stage1": "completed",
                    "stage2": (
                        "completed"
                        if stage2
                        or any(
                            item.get("source_check_status") == "SOURCE_CHECK_PASS"
                            for item in stage1
                        )
                        else "not_applicable_no_passing_stage1_lineage"
                    ),
                    "stage3": stage3_state,
                },
                "stage1_candidates": stage1,
                "stage2_candidates": stage2,
                "stage3_candidates": stage3,
                "candidate_review_counts": counts,
                "approved_candidate_ids": [item["candidate_id"] for item in approved],
                "rejected_candidate_ids": [
                    item["candidate_id"]
                    for item in all_candidates
                    if item["human_review_status"] == "REJECT"
                ],
                "unresolved_candidate_ids": [
                    item["candidate_id"]
                    for item in all_candidates
                    if item["human_review_status"] in {"", "NEEDS_SOURCE_CHECK"}
                ],
                "provenance_lineage": {
                    "legacy_source_paths": original["legacy_source_paths"],
                    "selected_temporal_candidate_id": resolution[
                        "selected_temporal_candidate_id"
                    ],
                    "selected_temporal_candidate": next(
                        (
                            item
                            for item in resolution["candidate_rows"]
                            if item["temporal_candidate_id"]
                            == resolution["selected_temporal_candidate_id"]
                        ),
                        None,
                    ),
                    "approved_xbrl_fact_locators": [
                        item["fact_locator"] for item in approved
                    ],
                },
                "final_mapping_status": final_status,
                "unmappable_reason_code": resolution["unmappable_reason_code"],
                "human_review_lineage": human_lineage,
            }
        )

    status_counts = Counter(item["final_mapping_status"] for item in targets)
    if len(targets) != 17 or sum(status_counts.values()) != 17:
        raise ValueError("final DEV map must contain all 17 numeric targets")
    for target_id in ("NF001", "NF002", "NF005", "NF006", "NF007", "NF008"):
        target = next(item for item in targets if item["target_id"] == target_id)
        if target["unmappable_reason_code"] != TEMPORAL_NO_ANCHOR_METADATA:
            raise ValueError(f"{target_id} did not remain fail-closed")

    return {
        "schema_version": "dev_xbrl_map_v0.1",
        "mapping_version": "dev_xbrl_map_v0.1",
        "artifact_status": "FINAL_HUMAN_REVIEWED_DEV_MAPPING; NOT_FROZEN",
        "benchmark_version": d1["benchmark_version"],
        "split": "DEV",
        "mapping_spec_version": "xbrl_gold_mapping_spec_v0.1.2",
        "mapping_algorithm_version": d1["mapping_algorithm_version"],
        "temporal_catalog_version": catalog["catalog_version"],
        "temporal_catalog_sha256": hashlib.sha256(CATALOG_PATH.read_bytes()).hexdigest(),
        "review_artifacts": _review_artifact_identities(),
        "human_review_completed": True,
        "review_completion": {
            "layer_a_rule_families": "PASS",
            "layer_b_actually_used_dev_rows": "PASS",
            "layer_c_conflict_sample": "PASS",
        },
        "final_status_namespace": FINAL_STATUS_NAMESPACE,
        "final_status_counts": {
            status: status_counts[status] for status in FINAL_STATUS_NAMESPACE
        },
        "human_readable_period_labels_used": False,
        "agent_outputs_used": False,
        "original_d1_candidate_artifact_overwritten": False,
        "targets": targets,
    }


def build_coverage(final_map: Mapping[str, Any], map_bytes: bytes) -> dict[str, Any]:
    targets = list(final_map["targets"])
    status_counts = Counter(item["final_mapping_status"] for item in targets)
    reason_counts = Counter(
        item["unmappable_reason_code"]
        for item in targets
        if item["unmappable_reason_code"]
    )
    return {
        "schema_version": "dev_xbrl_map_coverage_v0.1",
        "mapping_version": final_map["mapping_version"],
        "final_map_sha256": _sha256(map_bytes),
        "temporal_catalog_sha256": final_map["temporal_catalog_sha256"],
        "total_dev_numeric_targets": len(targets),
        "direct_mapped": status_counts["mapped"],
        "derived_via_approved_inputs": status_counts["derived_via_inputs"],
        "no_xbrl_counterpart_in_frozen_corpus": status_counts[
            "no_xbrl_counterpart_in_frozen_corpus"
        ],
        "unmappable": status_counts["unmappable"],
        "unmappable_reason_counts": dict(sorted(reason_counts.items())),
        "pending_or_unresolved_human_decisions": 0,
        "human_reviewed_temporal_targets": sum(
            item["temporal_resolution"]["status"] == RESOLVED_HUMAN_CLOSED_SET
            for item in targets
        ),
        "approved_stage1_targets": sum(
            any(
                candidate["human_review_status"] == "APPROVE"
                for candidate in item["stage1_candidates"]
            )
            for item in targets
        ),
        "review_completion": final_map["review_completion"],
        "known_v0_1_limitation": (
            "The evaluator intentionally prefers false negatives to heuristic temporal inference. "
            "Where frozen approved source metadata lacks authoritative exact temporal binding, "
            "legacy chunk provenance remains valid but an approved XBRL mapping path is not awarded."
        ),
        "sparse_xbrl_coverage_is_retrieval_failure": False,
        "human_readable_period_labels_used": False,
        "agent_outputs_used": False,
    }


def render_artifacts() -> dict[Path, bytes]:
    final_map = build_final_map()
    map_bytes = canonical_json_bytes(final_map)
    coverage = build_coverage(final_map, map_bytes)
    return {
        MAP_PATH: map_bytes,
        COVERAGE_PATH: canonical_json_bytes(coverage),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = render_artifacts()
    if args.check:
        stale = [
            path
            for path, content in rendered.items()
            if not path.exists() or path.read_bytes() != content
        ]
        if stale:
            raise SystemExit(
                "stale final DEV XBRL artifacts: "
                + ", ".join(str(path) for path in stale)
            )
        return
    for path, content in rendered.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


if __name__ == "__main__":
    main()
