"""Authorized DEV temporal and mapping diagnostics for v0.1.2."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any, Mapping

from evaluation.temporal_context_catalog import (
    RESOLVED_ANCHOR_METADATA,
    RESOLVED_EXACT_TARGET_DATE,
    RESOLVED_HUMAN_CLOSED_SET,
    canonical_json_bytes,
    resolve_target_temporal,
)
from evaluation.xbrl_mapping import (
    apply_source_checks,
    candidate_discovery_state,
    candidate_matches_temporal,
    generate_stage1,
    generate_stage2,
    generate_stage3,
    temporal_precedence_direct_status,
)
from src.tools.xbrl_tool import XBRLTool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
D1_PATH = PROJECT_ROOT / "evaluation" / "dev" / "xbrl" / "dev_xbrl_mapping_candidates_v0.1.json"
CATALOG_PATH = PROJECT_ROOT / "evaluation" / "xbrl" / "temporal_context_catalog_v0.1.json"
TEMPORAL_OUTPUT_PATH = PROJECT_ROOT / "evaluation" / "dev" / "xbrl" / "dev_temporal_resolution_v0.1.2_diagnostic.json"
MAPPING_OUTPUT_PATH = PROJECT_ROOT / "evaluation" / "dev" / "xbrl" / "dev_xbrl_mapping_candidates_v0.1.2_diagnostic.json"
HUMAN_REVIEW_PATH = PROJECT_ROOT / "evaluation" / "dev" / "xbrl" / "dev_temporal_human_review_v0.1.csv"

RESOLVED_STATUSES = {
    RESOLVED_EXACT_TARGET_DATE, RESOLVED_ANCHOR_METADATA, RESOLVED_HUMAN_CLOSED_SET,
}

HUMAN_REVIEW_FIELDS = [
    "target_id",
    "approved_anchor_source_identity",
    "temporal_machine_status",
    "closed_candidate_ids",
    "temporal_candidate_id",
    "contributing_temporal_row_ids",
    "exact_temporal",
    "accessions",
    "source_identities",
    "evidence_types",
    "generation_rule_ids",
    "allowed_decisions",
    "human_temporal_decision",
    "human_temporal_notes",
]

HUMAN_TEMPORAL_DECISIONS = {
    "NF012": "SELECT TCC-31b1f6eab46385db",
    "NF013": "SELECT TCC-f5206ab8eb1933a4",
}


def _json_cell(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _compact_anchor_identities(target: Mapping[str, Any]) -> list[dict[str, Any]]:
    fields = ("provenance_id", "reference_id", "accession", "doc_id", "chunk_id", "form", "locator")
    return [
        {field: anchor.get(field) for field in fields}
        for anchor in target.get("source_provenance", [])
    ]


def _human_review_csv(temporal_targets: list[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=HUMAN_REVIEW_FIELDS, lineterminator="\n")
    writer.writeheader()
    for target in temporal_targets:
        if target["temporal_resolution_status"] != "NEEDS_HUMAN_CLOSED_SET":
            continue
        candidate_ids = target["closed_candidate_ids"]
        for candidate in target["closed_candidates"]:
            writer.writerow(
                {
                    "target_id": target["target_id"],
                    "approved_anchor_source_identity": _json_cell(
                        target["approved_anchor_source_identity"]
                    ),
                    "temporal_machine_status": target["temporal_resolution_status"],
                    "closed_candidate_ids": _json_cell(candidate_ids),
                    "temporal_candidate_id": candidate["temporal_candidate_id"],
                    "contributing_temporal_row_ids": _json_cell(
                        candidate["contributing_temporal_row_ids"]
                    ),
                    "exact_temporal": _json_cell(candidate["temporal"]),
                    "accessions": _json_cell(candidate["accessions"]),
                    "source_identities": _json_cell(candidate["source_identities"]),
                    "evidence_types": _json_cell(candidate["temporal_evidence_types"]),
                    "generation_rule_ids": _json_cell(candidate["generation_rule_ids"]),
                    "allowed_decisions": "SELECT <temporal_candidate_id>|SELECT NONE",
                    "human_temporal_decision": HUMAN_TEMPORAL_DECISIONS[target["target_id"]],
                    "human_temporal_notes": "",
                }
            )
    return stream.getvalue().encode("utf-8")


def _checks_from_d1(d1: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    checks: dict[str, dict[str, str]] = {}
    for target in d1["targets"]:
        for candidate in target.get("candidates", []):
            checks[candidate["candidate_id"]] = {
                "source_check_status": candidate["source_check_status"],
                "source_check_rationale": candidate.get("source_check_rationale", ""),
                "source_check_evidence": candidate.get("source_check_evidence", ""),
            }
    return checks


def _apply_available_checks(
    candidates: list[dict[str, Any]], checks: Mapping[str, Mapping[str, str]]
) -> list[dict[str, Any]]:
    return apply_source_checks(
        candidates,
        {item["candidate_id"]: checks[item["candidate_id"]] for item in candidates if item["candidate_id"] in checks},
    )


def build_diagnostics(
    *, data_root: Path | str | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    d1 = json.loads(D1_PATH.read_text(encoding="utf-8"))
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    active_data_root = PROJECT_ROOT / "data" if data_root is None else Path(data_root)
    tool = XBRLTool.from_frozen_ingestion(data_root=active_data_root)
    facts = [fact.to_dict() for fact in tool._facts]
    checks = _checks_from_d1(d1)
    temporal_targets: list[dict[str, Any]] = []
    mapping_targets: list[dict[str, Any]] = []

    for original in d1["targets"]:
        if original["target_kind"] != "direct":
            continue
        resolution = resolve_target_temporal(original, catalog, facts)
        temporal_targets.append(
            {
                "question_id": original["question_id"],
                "target_id": original["target_id"],
                "exact_target_dates_present": resolution["exact_target_dates_present"],
                "approved_provenance_anchors": original.get("source_provenance", []),
                "approved_anchor_source_identity": _compact_anchor_identities(original),
                "anchor_temporal_metadata_discovered": resolution["anchor_temporal_metadata_discovered"],
                "temporal_resolution_status": resolution["temporal_resolution_status"],
                "temporal_resolution_mode": resolution["temporal_resolution_mode"],
                "resolved_temporal": resolution["resolved_temporal"],
                "closed_candidate_ids": [
                    item["temporal_candidate_id"] for item in resolution["candidate_rows"]
                ],
                "closed_candidates": resolution["candidate_rows"],
                "unresolved_reason": resolution["unresolved_reason"],
                "unmappable_reason_code": resolution["unmappable_reason_code"],
                "human_readable_period_labels_used": False,
                "selected_temporal_candidate_id": "",
                "reviewer_rationale": "",
                "reviewer_identity": "",
                "reviewer_status": "",
            }
        )

        target = dict(original)
        resolved = resolution["temporal_resolution_status"] in RESOLVED_STATUSES
        if resolved:
            target["temporal_requirement"] = resolution["resolved_temporal"]
        else:
            target["temporal_requirement"] = {
                "kind": "unresolved",
                "reason": resolution["temporal_resolution_status"],
            }
        stage1 = _apply_available_checks(generate_stage1(target, facts), checks)
        stage2 = _apply_available_checks(generate_stage2(target, facts, stage1), checks)
        stage3, stage3_state = generate_stage3(target, facts, stage1 + stage2)
        stage3 = _apply_available_checks(stage3, checks)
        all_candidates = stage1 + stage2 + stage3
        annotated_candidates = []
        for candidate in all_candidates:
            annotated = dict(candidate)
            annotated["temporal_consistency_status"] = (
                "EXACT_MATCH_BOUND_TEMPORAL"
                if resolved and candidate_matches_temporal(candidate, resolution["resolved_temporal"])
                else "MISMATCH_BOUND_TEMPORAL"
                if resolved
                else "PENDING_TEMPORAL_BINDING"
            )
            annotated_candidates.append(annotated)
        stage1_count = len(stage1)
        stage2_count = len(stage2)
        stage1 = annotated_candidates[:stage1_count]
        stage2 = annotated_candidates[stage1_count:stage1_count + stage2_count]
        stage3 = annotated_candidates[stage1_count + stage2_count:]
        all_candidates = annotated_candidates
        proposed = temporal_precedence_direct_status(
            all_candidates,
            stage3_state,
            temporal_resolution_status=resolution["temporal_resolution_status"],
            resolved_temporal=resolution["resolved_temporal"],
            unmappable_reason_code=resolution["unmappable_reason_code"],
        )
        mapping_targets.append(
            {
                "question_id": original["question_id"],
                "target_id": original["target_id"],
                "temporal_resolution_status": resolution["temporal_resolution_status"],
                "temporal_resolution_mode": resolution["temporal_resolution_mode"],
                "resolved_period": resolution["resolved_temporal"],
                "closed_candidate_ids": [
                    item["temporal_candidate_id"] for item in resolution["candidate_rows"]
                ],
                "candidate_discovery_state": candidate_discovery_state(all_candidates),
                "candidate_discovery_counts": {
                    "stage1": len(stage1),
                    "stage2": len(stage2),
                    "stage3": len(stage3),
                },
                "stage1_candidates": stage1,
                "stage2_candidates": stage2,
                "stage3_candidates": stage3,
                "stage_completion": {
                    "stage1": "completed",
                    "stage2": "completed" if stage2 or any(item.get("source_check_status") == "SOURCE_CHECK_PASS" for item in stage1) else "not_applicable_no_passing_stage1_lineage",
                    "stage3": stage3_state,
                },
                "source_check_state": {
                    "SOURCE_CHECK_PASS": sum(item.get("source_check_status") == "SOURCE_CHECK_PASS" for item in all_candidates),
                    "SOURCE_CHECK_REJECT": sum(item.get("source_check_status") == "SOURCE_CHECK_REJECT" for item in all_candidates),
                    "SOURCE_CHECK_UNRESOLVED": sum(item.get("source_check_status") == "SOURCE_CHECK_UNRESOLVED" for item in all_candidates),
                },
                "unmappable_reason_code": resolution["unmappable_reason_code"],
                "final_mapping_state": proposed,
                "proposed_mapping_status": proposed,
                "human_review_status": "",
                "human_review_notes": "",
            }
        )

    formerly_blocked = {
        target["target_id"]
        for target in d1["targets"]
        if target.get("target_kind") == "direct"
        and target.get("stage_completion", {}).get("stage3") == "blocked_missing_exact_temporal_requirement"
    }
    completed_former = sorted(
        item["target_id"] for item in mapping_targets
        if item["target_id"] in formerly_blocked and item["stage_completion"]["stage3"] == "completed"
    )
    common = {
        "artifact_status": "provisional diagnostic; not final mapping; no human approvals",
        "mapping_spec_version": "xbrl_gold_mapping_spec_v0.1.2",
        "temporal_catalog_version": catalog["catalog_version"],
        "temporal_catalog_sha256": hashlib.sha256(CATALOG_PATH.read_bytes()).hexdigest(),
        "base_d1_artifact": "evaluation/dev/xbrl/dev_xbrl_mapping_candidates_v0.1.json",
        "original_d1_artifact_overwritten": False,
        "human_readable_period_labels_used": False,
        "agent_outputs_used": False,
    }
    temporal_payload = {
        "schema_version": "dev_temporal_resolution_v0.1.2_diagnostic",
        **common,
        "targets": temporal_targets,
    }
    mapping_payload = {
        "schema_version": "dev_xbrl_mapping_candidates_v0.1.2_diagnostic",
        **common,
        "formerly_temporal_blocked_target_ids": sorted(formerly_blocked),
        "formerly_temporal_blocked_stage3_completed_target_ids": completed_former,
        "all_six_formerly_temporal_blocked_resolved_without_label_parsing": len(formerly_blocked) == 6 and len(completed_former) == 6,
        "targets": mapping_targets,
    }
    return temporal_payload, mapping_payload


def render_artifacts(*, data_root: Path | str | None = None) -> dict[Path, bytes]:
    temporal, mapping = build_diagnostics(data_root=data_root)
    return {
        TEMPORAL_OUTPUT_PATH: canonical_json_bytes(temporal),
        MAPPING_OUTPUT_PATH: canonical_json_bytes(mapping),
        HUMAN_REVIEW_PATH: _human_review_csv(temporal["targets"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--data-root", type=Path)
    args = parser.parse_args()
    rendered = render_artifacts(data_root=args.data_root)
    if args.check:
        stale = [path for path, content in rendered.items() if not path.exists() or path.read_bytes() != content]
        if stale:
            raise SystemExit("stale DEV v0.1.2 diagnostics: " + ", ".join(str(path) for path in stale))
        return
    for path, content in rendered.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


if __name__ == "__main__":
    main()
