"""Build deterministic temporal-context catalog and blank review packet."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from evaluation.temporal_context_catalog import build_temporal_catalog, canonical_json_bytes
from src.tools.xbrl_tool import XBRLTool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "evaluation" / "xbrl"
CATALOG_PATH = OUTPUT_DIR / "temporal_context_catalog_v0.1.json"
REVIEW_PATH = OUTPUT_DIR / "temporal_context_catalog_review_v0.1.csv"
COVERAGE_PATH = OUTPUT_DIR / "temporal_context_catalog_coverage_v0.1.json"
RULE_REVIEW_PATH = OUTPUT_DIR / "temporal_rule_review_v0.1.csv"
CONFLICT_REVIEW_PATH = OUTPUT_DIR / "temporal_conflict_review_sample_v0.1.csv"
PREDECESSOR_PATH = OUTPUT_DIR / "fiscal_period_resolution_v0.1.json"

REVIEW_FIELDS = [
    "temporal_row_id", "entity", "cik", "accession", "form_type", "filing_date",
    "temporal", "context_ref", "dimensions", "source_metadata_identities",
    "evidence_fingerprints", "temporal_evidence_type", "generation_rule_id",
    "human_review_status", "human_review_notes", "reviewer_identity",
]

RULE_REVIEW_FIELDS = [
    "rule_id", "authoritative_generator_status", "prior_catalog_row_count",
    "evidence_types", "evidence_inputs", "derivation_or_merge_condition",
    "failure_condition", "catalog_row_count", "representative_temporal_row_ids",
    "representative_examples", "human_rule_decision", "human_rule_notes", "reviewer_identity",
]

CONFLICT_REVIEW_FIELDS = [
    "conflict_id", "conflict_type", "reason", "accession", "chunk_id", "table_column",
    "evidence_fingerprint", "sampling_rule", "human_conflict_classification",
    "human_review_notes", "reviewer_identity",
]

RULE_FAMILY_CONTRACT = {
    "xbrl_context_exact_dates_v0.1": {
        "authoritative_generator_status": "ACTIVE",
        "prior_catalog_row_count": "",
        "evidence_inputs": "frozen XBRL accession, context_ref, exact context dates, and dimensions",
        "derivation_or_merge_condition": "group facts with identical accession, context_ref, temporal object, and dimensions",
        "failure_condition": "context_ref or exact instant/duration dates are absent",
    },
    "table_cell_exact_period_v0.1": {
        "authoritative_generator_status": "ACTIVE_EXPLICIT_PROVENANCE_ONLY",
        "prior_catalog_row_count": 301,
        "evidence_inputs": "frozen table cell/header exact instant or exact period_start and period_end",
        "derivation_or_merge_condition": "retain the unique exact period encoded for one table column",
        "failure_condition": "exact fields are absent, invalid, or conflict within the column",
    },
    "table_duration_end_months_to_start_v0.1": {
        "authoritative_generator_status": "RETIRED_UNSAFE_FOR_AUTHORITATIVE_TEMPORAL_ROWS",
        "prior_catalog_row_count": 191,
        "evidence_inputs": "frozen exact period_end and positive integral duration_months",
        "derivation_or_merge_condition": "none; duration_months plus end cannot establish exact start",
        "failure_condition": "always fail closed unless authoritative linked XBRL independently supplies exact dates under table_xbrl_agreement_v0.1",
    },
    "table_xbrl_agreement_v0.1": {
        "authoritative_generator_status": "ACTIVE",
        "prior_catalog_row_count": "",
        "evidence_inputs": "frozen table temporal metadata plus every linked exact XBRL context",
        "derivation_or_merge_condition": "table temporal object and all linked context temporal objects agree exactly",
        "failure_condition": "any linked exact context disagrees with the table temporal object",
    },
}

CONFLICT_TYPE_BY_REASON = {
    "conflicting frozen cell/header period metadata": "TABLE_COLUMN_PERIOD_METADATA_CONFLICT",
    "table period conflicts with linked XBRL context": "TABLE_XBRL_TEMPORAL_CONFLICT",
    "linked XBRL contexts disagree on temporal object": "LINKED_XBRL_TEMPORAL_DISAGREEMENT",
    "linked XBRL contexts disagree on dimensions": "LINKED_XBRL_DIMENSION_CONFLICT",
}

HUMAN_RULE_DECISIONS = {
    "table_cell_exact_period_v0.1": "APPROVE",
    "table_duration_end_months_to_start_v0.1": (
        "RETIRED / REJECT AS AUTHORITATIVE TEMPORAL RULE"
    ),
    "table_xbrl_agreement_v0.1": "APPROVE",
    "xbrl_context_exact_dates_v0.1": "APPROVE",
}

HUMAN_CONFLICT_CLASSIFICATION = "APPROVE CLASSIFICATION"
HUMAN_CONFLICT_FAIL_CLOSED_DECISION = "APPROVE FAIL-CLOSED HANDLING"


def _csv_bytes(rows: list[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=REVIEW_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                field: (
                    json.dumps(row[field], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                    if field in {"temporal", "dimensions", "source_metadata_identities", "evidence_fingerprints"}
                    else row.get(field, "")
                )
                for field in REVIEW_FIELDS
            }
        )
    return stream.getvalue().encode("utf-8")


def _dict_csv_bytes(rows: list[Mapping[str, Any]], fields: list[str]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _rule_review_bytes(catalog: Mapping[str, Any]) -> bytes:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in catalog["rows"]:
        grouped.setdefault(str(row["generation_rule_id"]), []).append(row)
    unknown = sorted(set(grouped) - set(RULE_FAMILY_CONTRACT))
    if unknown:
        raise ValueError(f"unregistered temporal generation-rule families: {unknown}")
    rows: list[dict[str, Any]] = []
    for rule_id in sorted(RULE_FAMILY_CONTRACT):
        family = sorted(grouped.get(rule_id, []), key=lambda item: item["temporal_row_id"])
        example = family[0] if family else None
        rows.append(
            {
                "rule_id": rule_id,
                "evidence_types": json.dumps(
                    sorted({row["temporal_evidence_type"] for row in family}), separators=(",", ":")
                ),
                **RULE_FAMILY_CONTRACT[rule_id],
                "catalog_row_count": len(family),
                "representative_temporal_row_ids": json.dumps(
                    [example["temporal_row_id"]] if example else [], separators=(",", ":")
                ),
                "representative_examples": json.dumps(
                    ([
                        {
                            "temporal_row_id": example["temporal_row_id"],
                            "temporal": example["temporal"],
                            "accession": example.get("accession"),
                            "source_identity": example["source_metadata_identities"],
                        }
                    ] if example else []),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "human_rule_decision": HUMAN_RULE_DECISIONS[rule_id],
                "human_rule_notes": "",
                "reviewer_identity": "",
            }
        )
    return _dict_csv_bytes(rows, RULE_REVIEW_FIELDS)


def _conflict_review_bytes(catalog: Mapping[str, Any]) -> bytes:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for diagnostic in catalog["conflicts"]:
        reason = str(diagnostic["reason"])
        if reason not in CONFLICT_TYPE_BY_REASON:
            raise ValueError(f"unregistered temporal conflict reason: {reason!r}")
        grouped.setdefault(CONFLICT_TYPE_BY_REASON[reason], []).append(diagnostic)
    rows: list[dict[str, Any]] = []
    sampling_rule = "group by conflict_type; sort by conflict_id; select first min(5, group_size)"
    for conflict_type in sorted(grouped):
        for diagnostic in sorted(grouped[conflict_type], key=lambda item: item["conflict_id"])[:5]:
            rows.append(
                {
                    **diagnostic,
                    "conflict_type": conflict_type,
                    "sampling_rule": sampling_rule,
                    "human_conflict_classification": HUMAN_CONFLICT_CLASSIFICATION,
                    "human_review_notes": HUMAN_CONFLICT_FAIL_CLOSED_DECISION,
                    "reviewer_identity": "",
                }
            )
    return _dict_csv_bytes(rows, CONFLICT_REVIEW_FIELDS)


def render_artifacts(*, data_root: Path | str | None = None) -> dict[Path, bytes]:
    active_data_root = PROJECT_ROOT / "data" if data_root is None else Path(data_root)
    tool = XBRLTool.from_frozen_ingestion(data_root=active_data_root)
    manifest = json.loads((active_data_root / "manifest.json").read_text(encoding="utf-8"))
    chunk_documents = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((active_data_root / "chunks").glob("*.json"))
    ]
    predecessor_count = 0
    if PREDECESSOR_PATH.exists():
        predecessor_count = len(json.loads(PREDECESSOR_PATH.read_text(encoding="utf-8"))["rows"])
    catalog = build_temporal_catalog(
        [fact.to_dict() for fact in tool._facts],
        manifest["entries"],
        chunk_documents,
        xbrl_artifact_fingerprint=tool._xbrl_artifact_fingerprint,
        corpus_fingerprint=tool._corpus_fingerprint,
        migrated_resolver_row_count=predecessor_count,
    )
    catalog_bytes = canonical_json_bytes(catalog)
    review_rows = [
        {**row, "human_review_status": "", "human_review_notes": "", "reviewer_identity": ""}
        for row in catalog["rows"]
    ]
    review_bytes = _csv_bytes(review_rows)
    rule_review_bytes = _rule_review_bytes(catalog)
    conflict_review_bytes = _conflict_review_bytes(catalog)
    counts = Counter(row["temporal_evidence_type"] for row in catalog["rows"])
    rule_counts = Counter(row["generation_rule_id"] for row in catalog["rows"])
    conflict_type_counts = Counter(
        CONFLICT_TYPE_BY_REASON[item["reason"]] for item in catalog["conflicts"]
    )
    coverage = {
        "schema_version": "temporal_context_catalog_coverage_v0.1",
        "prior_catalog_total_rows": 3417,
        "total_rows": len(catalog["rows"]),
        "net_rows_removed_from_prior_catalog": 3417 - len(catalog["rows"]),
        "prior_temporal_evidence_type_counts": {
            "DETERMINISTICALLY_DERIVED": 492,
            "DIRECTLY_OBSERVED_CONTEXT": 2066,
            "MERGED_AGREEING_EVIDENCE": 859,
        },
        "temporal_evidence_type_counts": dict(sorted(counts.items())),
        "generation_rule_family_counts": dict(sorted(rule_counts.items())),
        "conflicting_rows": len(catalog["conflicts"]),
        "conflict_type_counts": dict(sorted(conflict_type_counts.items())),
        "conflict_review_sample_size": sum(min(5, count) for count in conflict_type_counts.values()),
        "table_period_provenance_audit": catalog["table_period_provenance_audit"],
        "duplicate_identities": len(catalog["duplicate_temporal_row_ids"]),
        "migrated_predecessor_rows_recomputed": predecessor_count,
        "catalog_sha256": hashlib.sha256(catalog_bytes).hexdigest(),
        "review_packet_sha256": hashlib.sha256(review_bytes).hexdigest(),
        "rule_review_sha256": hashlib.sha256(rule_review_bytes).hexdigest(),
        "conflict_review_sample_sha256": hashlib.sha256(conflict_review_bytes).hexdigest(),
    }
    return {
        CATALOG_PATH: catalog_bytes,
        REVIEW_PATH: review_bytes,
        COVERAGE_PATH: canonical_json_bytes(coverage),
        RULE_REVIEW_PATH: rule_review_bytes,
        CONFLICT_REVIEW_PATH: conflict_review_bytes,
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
            raise SystemExit("stale temporal catalog artifacts: " + ", ".join(str(path) for path in stale))
        return
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path, content in rendered.items():
        path.write_bytes(content)


if __name__ == "__main__":
    main()
