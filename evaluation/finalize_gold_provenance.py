"""Finalize reviewed provenance into deterministic benchmark gold artifacts.

This module only promotes already-materialized candidate mappings.  It does not
perform retrieval, candidate generation, or source resolution.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
PROVENANCE_DIR = ROOT / "benchmark" / "provenance"
REVIEW_DIR = PROVENANCE_DIR / "review"
GOLD_DIR = PROVENANCE_DIR / "gold"
RELEASE_DIR = ROOT / "benchmark" / "releases" / "v0.1.1"

BENCHMARK_VERSION = "bench_v0.1.1"
BENCHMARK_TAG = "bench_v0.1.1"
INGESTION_TAG = "ingestion_v0.1.1"
INGESTION_GIT_COMMIT = "63cabb2"
CORPUS_FINGERPRINT = (
    "56df698d50b13cf15e913c1c60dbc96b1fd0fab44adb7b1f40ba99771c4b7c96"
)
GOLD_SCHEMA = "investment-research-provenance-gold-map"
GOLD_SCHEMA_VERSION = "1.0.0"

ORIGINAL_REVIEW_FILES = (
    "evidence_single_reviewed.csv",
    "evidence_or_reviewed.csv",
    "numeric_unique_reviewed.csv",
    "numeric_or_reviewed.csv",
    "numeric_derived_reviewed.csv",
)
REPAIR_REVIEW_FILE = "provenance_repair_review_reviewed.csv"
MERGE_REVIEW_FILE = "merge_review_final_reviewed.csv"
GOLD_ARTIFACTS = (
    "version_binding.json",
    "numeric_fact_provenance.json",
    "evidence_provenance.json",
    "source_anchors.json",
    "merge_lineage.json",
    "review_decisions.json",
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _evidence_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row["q_id"]),
        str(row["q_version"]),
        str(row["item_id"]),
        str(row["part_id"]),
    )


def _fact_key(row: dict[str, Any]) -> str:
    return str(row["fact_id"])


def _mapping_key(key: tuple[str, str, str, str]) -> dict[str, str]:
    return dict(zip(("q_id", "q_version", "item_id", "part_id"), key))


def _candidate_identity(source: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(source["accession"]),
        str(source["chunk_id"]),
        str(source.get("anchor_id") or source.get("source_anchor_id")),
    )


def _decision_id(category: str, filename: str, record_number: int) -> str:
    return f"{category}:{filename}:{record_number:04d}"


def _review_lineage(
    decision: dict[str, Any], *, supersedes: str | None = None
) -> dict[str, Any]:
    result = {
        "decision": decision["decision"],
        "decision_id": decision["decision_id"],
        "review_record_number": decision["review_record_number"],
        "review_source": decision["review_source"],
        "reviewer_note": decision["reviewer_note"],
    }
    if supersedes:
        result["supersedes_decision_id"] = supersedes
    return result


def _validate_draft_binding(payload: dict[str, Any]) -> None:
    binding = payload["version_binding"]
    expected = {
        "benchmark_version": BENCHMARK_VERSION,
        "ingestion_tag": INGESTION_TAG,
        "ingestion_git_commit": INGESTION_GIT_COMMIT,
        "corpus_fingerprint": CORPUS_FINGERPRINT,
    }
    for key, value in expected.items():
        if binding.get(key) != value:
            raise RuntimeError(f"draft binding mismatch for {key}: {binding.get(key)!r}")


def build_version_binding() -> dict[str, Any]:
    release_manifest_path = RELEASE_DIR / "release_manifest.json"
    release_manifest = _read_json(release_manifest_path)
    if release_manifest.get("benchmark_release_version") != BENCHMARK_VERSION:
        raise RuntimeError("benchmark release version mismatch")
    for filename, expected in release_manifest["files"].items():
        actual = _sha256(RELEASE_DIR / filename)
        if actual != expected:
            raise RuntimeError(f"benchmark release hash mismatch for {filename}")

    release_commit = _git("rev-list", "-n", "1", BENCHMARK_TAG)
    if not release_commit:
        raise RuntimeError(f"benchmark tag does not resolve: {BENCHMARK_TAG}")
    return {
        "benchmark_version": BENCHMARK_VERSION,
        "benchmark_tag": BENCHMARK_TAG,
        "ingestion_tag": INGESTION_TAG,
        "ingestion_git_commit": INGESTION_GIT_COMMIT,
        "corpus_fingerprint": CORPUS_FINGERPRINT,
        "benchmark_release_git_commit": release_commit,
        "benchmark_release_git_tag": BENCHMARK_TAG,
        "benchmark_release_manifest_sha256": _sha256(release_manifest_path),
        "benchmark_parent_version": release_manifest["benchmark_parent_version"],
        "benchmark_schema_version": "v0.1.2",
        "gold_schema": GOLD_SCHEMA,
        "gold_schema_version": GOLD_SCHEMA_VERSION,
    }


def _load_review_decisions() -> tuple[
    list[dict[str, Any]],
    dict[tuple[str, str, str, str], dict[str, Any]],
    dict[tuple[str, str, str, str], dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[tuple[str, str, str, str], dict[str, Any]],
    list[dict[str, Any]],
]:
    decisions: list[dict[str, Any]] = []
    original_evidence: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    repaired_evidence: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    numeric: dict[str, dict[str, Any]] = {}
    merge: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    input_summaries: list[dict[str, Any]] = []

    all_paths = [REVIEW_DIR / name for name in ORIGINAL_REVIEW_FILES]
    all_paths += [REVIEW_DIR / REPAIR_REVIEW_FILE, PROVENANCE_DIR / MERGE_REVIEW_FILE]
    for path in all_paths:
        rows = _read_csv(path)
        counts = {decision: 0 for decision in ("APPROVE", "REJECT", "NEEDS_SOURCE_CHECK")}
        for row in rows:
            decision = row["reviewer_decision"]
            if decision not in counts:
                raise RuntimeError(f"invalid review decision in {path}: {decision!r}")
            counts[decision] += 1
        input_summaries.append(
            {
                "path": str(path.relative_to(ROOT)),
                "sha256": _sha256(path),
                "row_count": len(rows),
                "decision_counts": counts,
            }
        )

    rejected_ids: dict[tuple[str, str, str, str], str] = {}
    for filename in ORIGINAL_REVIEW_FILES:
        path = REVIEW_DIR / filename
        for record_number, row in enumerate(_read_csv(path), start=1):
            decision_id = _decision_id("original", filename, record_number)
            record: dict[str, Any] = {
                "decision_id": decision_id,
                "decision": row["reviewer_decision"],
                "reviewer_note": row["reviewer_note"],
                "review_source": str(path.relative_to(ROOT)),
                "review_record_number": record_number,
                "active": row["reviewer_decision"] == "APPROVE",
            }
            if filename.startswith("evidence_"):
                key = _evidence_key(row)
                record["scope"] = "evidence_mapping"
                record["mapping_keys"] = [_mapping_key(key)]
                record["review_row"] = row
                if key in original_evidence:
                    raise RuntimeError(f"duplicate original evidence review: {key}")
                original_evidence[key] = record
                if row["reviewer_decision"] == "REJECT":
                    rejected_ids[key] = decision_id
            else:
                fact_id = _fact_key(row)
                record["scope"] = "numeric_mapping"
                record["mapping_keys"] = [{"fact_id": fact_id}]
                record["review_row"] = row
                if fact_id in numeric:
                    raise RuntimeError(f"duplicate numeric review: {fact_id}")
                numeric[fact_id] = record
            decisions.append(record)

    repair_path = REVIEW_DIR / REPAIR_REVIEW_FILE
    for record_number, row in enumerate(_read_csv(repair_path), start=1):
        filename = repair_path.name
        decision_id = _decision_id("repair", filename, record_number)
        old_key = (row["q_id"], row["q_version"], row["item_id"], row["old_part_id"])
        if old_key not in rejected_ids:
            raise RuntimeError(f"repair has no rejected original mapping: {old_key}")
        proposed = json.loads(row["proposed_mapping_json"])
        mapping_keys = [
            (row["q_id"], row["q_version"], row["item_id"], part["part_id"])
            for part in proposed
        ]
        record = {
            "decision_id": decision_id,
            "decision": row["reviewer_decision"],
            "reviewer_note": row["reviewer_note"],
            "review_source": str(repair_path.relative_to(ROOT)),
            "review_record_number": record_number,
            "scope": "evidence_mapping_repair",
            "active": row["reviewer_decision"] == "APPROVE",
            "mapping_keys": [_mapping_key(key) for key in mapping_keys],
            "supersedes_decision_id": rejected_ids[old_key],
            "review_row": row,
            "proposed_mapping": proposed,
        }
        for key, proposed_part in zip(mapping_keys, proposed):
            if key in repaired_evidence:
                raise RuntimeError(f"duplicate repaired evidence review: {key}")
            repaired_evidence[key] = {**record, "proposed_part": proposed_part}
        decisions.append(record)
        original_evidence[old_key]["superseded_by_decision_id"] = decision_id

    merge_path = PROVENANCE_DIR / MERGE_REVIEW_FILE
    merge_rows = _read_csv(merge_path)
    for record_number, row in enumerate(merge_rows, start=1):
        decision_id = _decision_id("merge", merge_path.name, record_number)
        key = (row["q_id"], row["q_version"], row["item_id"], row["new_part_id"])
        record = {
            "decision_id": decision_id,
            "decision": row["reviewer_decision"],
            "reviewer_note": row["reviewer_note"],
            "review_source": str(merge_path.relative_to(ROOT)),
            "review_record_number": record_number,
            "scope": "evidence_merge",
            "active": row["reviewer_decision"] == "APPROVE",
            "mapping_keys": [_mapping_key(key)],
            "review_row": row,
        }
        if key in merge:
            raise RuntimeError(f"duplicate merge review: {key}")
        merge[key] = record
        decisions.append(record)

    original = [d for d in decisions if d["decision_id"].startswith("original:")]
    if len(original) != 302 or sum(d["decision"] == "APPROVE" for d in original) != 290:
        raise RuntimeError("original review counts do not match the authoritative final review")
    if sum(d["decision"] == "REJECT" for d in original) != 12:
        raise RuntimeError("original rejection count is not 12")
    if len(numeric) != 71 or any(d["decision"] != "APPROVE" for d in numeric.values()):
        raise RuntimeError("numeric review is not 71 / 71 APPROVE")
    repairs = [d for d in decisions if d["decision_id"].startswith("repair:")]
    if len(repairs) != 12 or any(d["decision"] != "APPROVE" for d in repairs):
        raise RuntimeError("repair review is not 12 / 12 APPROVE")
    if len(merge) != 56 or any(d["decision"] != "APPROVE" for d in merge.values()):
        raise RuntimeError("merge review is not 56 / 56 APPROVE")
    if any(d["decision"] == "NEEDS_SOURCE_CHECK" for d in decisions):
        raise RuntimeError("NEEDS_SOURCE_CHECK remains in authoritative review inputs")

    return decisions, original_evidence, repaired_evidence, numeric, merge, input_summaries


def _validate_original_evidence(part: dict[str, Any], decision: dict[str, Any]) -> None:
    row = decision["review_row"]
    actual = {_candidate_identity(source) for source in part["candidate_sources"]}
    if "candidates_json" in row:
        reviewed = {_candidate_identity(source) for source in json.loads(row["candidates_json"])}
    else:
        reviewed = {(row["accession"], row["chunk_id"], row["source_anchor_id"])}
    if actual != reviewed or part["description"] != row["semantic_requirement"]:
        raise RuntimeError(f"approved evidence mapping changed: {_evidence_key(row)}")


def _validate_repaired_evidence(part: dict[str, Any], decision: dict[str, Any]) -> None:
    proposed = decision["proposed_part"]
    actual = {_candidate_identity(source) for source in part["candidate_sources"]}
    reviewed = {_candidate_identity(source) for source in proposed["candidates"]}
    if (
        actual != reviewed
        or part["description"] != proposed["semantic_requirement"]
        or part["source_atom_ids"] != proposed["source_atom_ids"]
    ):
        raise RuntimeError(
            f"approved repaired evidence mapping changed: {decision['mapping_keys']}"
        )


def _validate_numeric(fact: dict[str, Any], decision: dict[str, Any]) -> None:
    row = decision["review_row"]
    if str(fact.get("q_id") or "") != row["q_id"]:
        raise RuntimeError(f"numeric q_id changed: {fact['fact_id']}")
    if Decimal(str(fact["value"])) != Decimal(row["value"]) or fact["unit"] != row["unit"]:
        raise RuntimeError(f"numeric value changed: {fact['fact_id']}")
    if "alternatives_json" in row:
        reviewed = {
            _candidate_identity(source) for source in json.loads(row["alternatives_json"])
        }
        actual = {_candidate_identity(source) for source in fact["candidate_sources"]}
        if actual != reviewed:
            raise RuntimeError(f"numeric OR candidates changed: {fact['fact_id']}")
    elif "source_anchor_id" in row:
        reviewed = (row["accession"], row["chunk_id"], row["source_anchor_id"])
        actual = {_candidate_identity(source) for source in fact["candidate_sources"]}
        if actual != {reviewed}:
            raise RuntimeError(f"numeric unique candidate changed: {fact['fact_id']}")
    else:
        reviewed_inputs = [value for value in row["input_fact_ids"].split(";") if value]
        reviewed_union = json.loads(row["derived_candidate_union_json"])
        if fact["input_fact_ids"] != reviewed_inputs or fact["candidate_chunk_ids"] != reviewed_union:
            raise RuntimeError(f"numeric derived lineage changed: {fact['fact_id']}")


def _build_merge_artifact(
    binding: dict[str, Any], merge: dict[tuple[str, str, str, str], dict[str, Any]]
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for decision in sorted(merge.values(), key=lambda item: item["decision_id"]):
        source = decision["review_row"]
        row = dict(source)
        row["human_approved"] = source["human_approved"].lower() == "true"
        row["number_of_parts_reduced"] = int(source["number_of_parts_reduced"])
        row["old_part_ids"] = source["old_part_ids"].split(";")
        row["reason_for_merge"] = row["reason_for_merge"].replace(
            "Human re-review is pending.",
            "The final human review approved this retrieval-level merge.",
        )
        row["logical_equivalence"] = row["logical_equivalence"].replace(
            "Human review of the repaired mapping is pending;",
            "Final human review approved the repaired mapping;",
        )
        row["review_lineage"] = _review_lineage(decision)
        rows.append(row)
    return {
        "artifact_type": "gold_merge_lineage",
        "version_binding": binding,
        "merge_count": len(rows),
        "approved_merge_count": sum(row["reviewer_decision"] == "APPROVE" for row in rows),
        "merges": rows,
    }


def _validate_anchors(
    numeric: dict[str, Any], evidence: dict[str, Any], anchors: dict[str, Any]
) -> dict[str, int]:
    by_id = {anchor["anchor_id"]: anchor for anchor in anchors["anchors"]}
    candidates = [
        source for fact in numeric["facts"] for source in fact["candidate_sources"]
    ] + [
        source
        for item in evidence["items"]
        for part in item["parts"]
        for source in part["candidate_sources"]
    ]
    required = (
        "accession", "doc_id", "raw_document_sha256", "chunk_id", "char_start",
        "char_end", "normalized_source_fingerprint",
    )
    used: set[str] = set()
    for source in candidates:
        anchor_id = source["anchor_id"]
        if anchor_id not in by_id:
            raise RuntimeError(f"dangling anchor reference: {anchor_id}")
        anchor = by_id[anchor_id]
        if any(source[field] != anchor[field] for field in required):
            raise RuntimeError(f"candidate/anchor mismatch: {anchor_id}")
        used.add(anchor_id)
    orphan = set(by_id) - used
    if orphan:
        raise RuntimeError(f"orphan anchors: {sorted(orphan)}")
    return {
        "numeric_candidate_references": sum(
            len(fact["candidate_sources"]) for fact in numeric["facts"]
        ),
        "evidence_candidate_references": sum(
            len(part["candidate_sources"])
            for item in evidence["items"]
            for part in item["parts"]
        ),
        "candidate_references_with_valid_anchor": len(candidates),
        "registered_source_anchors": len(by_id),
        "orphan_anchors": 0,
        "dangling_anchor_references": 0,
    }


def build_gold_artifacts() -> dict[str, dict[str, Any]]:
    binding = build_version_binding()
    numeric = deepcopy(_read_json(PROVENANCE_DIR / "numeric_facts_draft.json"))
    evidence = deepcopy(_read_json(PROVENANCE_DIR / "evidence_provenance_draft.json"))
    anchors = deepcopy(_read_json(PROVENANCE_DIR / "source_anchors_draft.json"))
    for payload in (numeric, evidence, anchors):
        _validate_draft_binding(payload)

    (
        decisions, original_evidence, repaired_evidence, numeric_reviews,
        merge_reviews, review_inputs,
    ) = _load_review_decisions()

    numeric["version_binding"] = binding
    numeric["artifact_type"] = "gold_numeric_fact_provenance"
    for fact in numeric["facts"]:
        decision = numeric_reviews.get(fact["fact_id"])
        if decision is None or decision["decision"] != "APPROVE":
            raise RuntimeError(f"numeric mapping lacks approval: {fact['fact_id']}")
        _validate_numeric(fact, decision)
        fact["reviewer_decision"] = "APPROVE"
        fact["reviewer_note"] = decision["reviewer_note"]
        fact["review_lineage"] = _review_lineage(decision)
        for source in fact["candidate_sources"]:
            source["reviewer_decision"] = "APPROVE"
            source["reviewer_note"] = decision["reviewer_note"]
            source["mapping_review_decision_id"] = decision["decision_id"]

    evidence["version_binding"] = binding
    evidence["artifact_type"] = "gold_evidence_provenance_and_or"
    evidence_mapping_count = 0
    for item in evidence["items"]:
        item_decision_ids: list[str] = []
        for part in item["parts"]:
            key = (item["q_id"], str(item["q_version"]), item["item_id"], part["part_id"])
            original = original_evidence.get(key)
            repaired = repaired_evidence.get(key)
            if original and original["decision"] == "APPROVE":
                _validate_original_evidence(part, original)
                decision = original
                lineage = _review_lineage(decision)
            elif repaired and repaired["decision"] == "APPROVE":
                _validate_repaired_evidence(part, repaired)
                decision = repaired
                lineage = _review_lineage(
                    decision, supersedes=decision["supersedes_decision_id"]
                )
            else:
                raise RuntimeError(f"evidence mapping lacks final approval: {key}")
            part["reviewer_decision"] = "APPROVE"
            part["reviewer_note"] = decision["reviewer_note"]
            part["review_lineage"] = lineage
            for source in part["candidate_sources"]:
                source["reviewer_decision"] = "APPROVE"
                source["reviewer_note"] = decision["reviewer_note"]
                source["mapping_review_decision_id"] = decision["decision_id"]
            item_decision_ids.append(decision["decision_id"])
            evidence_mapping_count += 1

            is_merge = len(part["source_atom_ids"]) > 1
            merge_decision = merge_reviews.get(key)
            if is_merge:
                if merge_decision is None or merge_decision["decision"] != "APPROVE":
                    raise RuntimeError(f"scoring merge lacks final approval: {key}")
                part["human_approved_retrieval_merge"] = True
                part["part_semantics"] = (
                    "human-approved retrieval-level merge of co-disclosed atoms"
                )
                part["merge_review_lineage"] = _review_lineage(merge_decision)
            elif merge_decision is not None:
                raise RuntimeError(f"merge review points to an unmerged part: {key}")

        item["reviewer_decision"] = "APPROVE"
        item["reviewer_note"] = ""
        item["review_lineage"] = {
            "approval_basis": "all_final_part_mappings_approved",
            "part_decision_ids": item_decision_ids,
        }

    if evidence_mapping_count != 234 or len(evidence["items"]) != 113:
        raise RuntimeError("final evidence counts are not 113 items / 234 parts")
    if len(numeric["facts"]) != 71:
        raise RuntimeError("final numeric fact count is not 71")
    if any(item["minimum_distinct_chunk_hits"] is None for item in evidence["items"]):
        raise RuntimeError("unresolved evidence remains")
    if any(
        not part["candidate_sources"]
        for item in evidence["items"]
        for part in item["parts"]
    ):
        raise RuntimeError("missing evidence provenance remains")

    anchors["version_binding"] = binding
    anchors["artifact_type"] = "gold_persistent_source_anchors"
    anchor_validation = _validate_anchors(numeric, evidence, anchors)
    for anchor in anchors["anchors"]:
        anchor.pop("reviewer_decision", None)
        anchor.pop("reviewer_note", None)
        anchor["validation_status"] = "VALID"
        anchor["validation_basis"] = (
            "identity-matched to at least one approved final provenance mapping"
        )
    anchors["validation"] = anchor_validation

    merge_artifact = _build_merge_artifact(binding, merge_reviews)
    merge_keys = {
        (item["q_id"], str(item["q_version"]), item["item_id"], part["part_id"])
        for item in evidence["items"]
        for part in item["parts"]
        if len(part["source_atom_ids"]) > 1
    }
    if merge_keys != set(merge_reviews):
        raise RuntimeError("approved merge set does not equal the scoring merge set")

    public_decisions = []
    for decision in decisions:
        public_decisions.append(
            {key: value for key, value in decision.items() if key not in {"review_row", "proposed_mapping"}}
        )
    active = [decision for decision in public_decisions if decision["active"]]
    original = [d for d in public_decisions if d["decision_id"].startswith("original:")]
    repair = [d for d in public_decisions if d["decision_id"].startswith("repair:")]
    merge = [d for d in public_decisions if d["decision_id"].startswith("merge:")]
    review_artifact = {
        "artifact_type": "gold_review_decisions",
        "version_binding": binding,
        "review_inputs": review_inputs,
        "summary": {
            "original_review_rows": len(original),
            "original_approvals": sum(d["decision"] == "APPROVE" for d in original),
            "original_rejections_superseded": sum(d["decision"] == "REJECT" for d in original),
            "numeric_mapping_approvals": len(numeric_reviews),
            "repair_review_rows": len(repair),
            "repair_approvals": sum(d["decision"] == "APPROVE" for d in repair),
            "repair_approved_final_evidence_mappings": len(repaired_evidence),
            "final_evidence_mapping_approvals": evidence_mapping_count,
            "merge_review_rows": len(merge),
            "merge_approvals": sum(d["decision"] == "APPROVE" for d in merge),
            "active_rejections": sum(d["decision"] == "REJECT" for d in active),
            "active_needs_source_check": sum(
                d["decision"] == "NEEDS_SOURCE_CHECK" for d in active
            ),
        },
        "decisions": public_decisions,
    }
    if review_artifact["summary"]["active_rejections"]:
        raise RuntimeError("an active REJECT remains")
    if review_artifact["summary"]["active_needs_source_check"]:
        raise RuntimeError("an active NEEDS_SOURCE_CHECK remains")

    return {
        "version_binding.json": binding,
        "numeric_fact_provenance.json": numeric,
        "evidence_provenance.json": evidence,
        "source_anchors.json": anchors,
        "merge_lineage.json": merge_artifact,
        "review_decisions.json": review_artifact,
    }


def build_manifest(gold_dir: Path = GOLD_DIR) -> dict[str, Any]:
    binding = _read_json(gold_dir / "version_binding.json")
    artifacts = {
        name: {
            "sha256": _sha256(gold_dir / name),
            "bytes": (gold_dir / name).stat().st_size,
        }
        for name in GOLD_ARTIFACTS
    }
    manifest = {
        "artifact_type": "gold_map_manifest",
        "gold_schema": GOLD_SCHEMA,
        "gold_schema_version": GOLD_SCHEMA_VERSION,
        "fingerprint_algorithm": "sha256-canonical-json",
        "fingerprint_excludes": ["timestamps", "gold_map_fingerprint"],
        "benchmark_binding": {
            "benchmark_version": binding["benchmark_version"],
            "benchmark_tag": binding["benchmark_tag"],
            "benchmark_release_git_commit": binding["benchmark_release_git_commit"],
            "benchmark_release_git_tag": binding["benchmark_release_git_tag"],
        },
        "ingestion_binding": {
            "ingestion_tag": binding["ingestion_tag"],
            "ingestion_git_commit": binding["ingestion_git_commit"],
            "corpus_fingerprint": binding["corpus_fingerprint"],
        },
        "artifacts": artifacts,
    }
    manifest["gold_map_fingerprint"] = hashlib.sha256(_canonical_json(manifest)).hexdigest()
    return manifest


def run(gold_dir: Path = GOLD_DIR) -> dict[str, Any]:
    artifacts = build_gold_artifacts()
    for name in GOLD_ARTIFACTS:
        _write_json(gold_dir / name, artifacts[name])
    first_manifest = build_manifest(gold_dir)
    second_manifest = build_manifest(gold_dir)
    if first_manifest["gold_map_fingerprint"] != second_manifest["gold_map_fingerprint"]:
        raise RuntimeError("gold-map fingerprint is not deterministic")
    _write_json(gold_dir / "gold_manifest.json", first_manifest)
    return first_manifest


def main() -> int:
    manifest = run()
    print(manifest["gold_map_fingerprint"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
