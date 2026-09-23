"""Deterministically materialize metadata-only benchmark errata releases."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
FROZEN_DIR = ROOT / "benchmark" / "frozen"
ERRATA_PATH = ROOT / "benchmark" / "errata" / "bench_v0.1.1.csv"
RELEASE_DIR = ROOT / "benchmark" / "releases" / "v0.1.1"

PARENT_VERSION = "bench_v0.1"
RELEASE_VERSION = "bench_v0.1.1"
TARGET_FILE = "evidence_checklist.csv"
ROW_KEY = ("q_id", "q_version", "item_id")
ALLOWED_FIELDS = {"accession", "location"}
SEMANTIC_FIELDS = {
    "claim", "stance", "importance", "temporal_role", "evidence_type",
    "evidence_period", "verification_status", "verification_note",
}
RELEASE_FILES = (
    "questions.csv",
    "numeric_answers.csv",
    "evidence_checklist.csv",
    "source_manifest.csv",
    "protocol.md",
)
REQUIRED_ERRATA_COLUMNS = {
    "benchmark_parent_version", "benchmark_release_version", "q_id",
    "q_version", "item_id", "field_name", "old_value", "new_value",
    "reason", "supporting_accession", "supporting_chunk_id",
    "supporting_anchor_id",
}

PROTOCOL_ADDENDUM = """# Benchmark protocol addendum — bench_v0.1.1

Parent release: `bench_v0.1`

`bench_v0.1` and every file under `benchmark/frozen/` remain immutable.
`bench_v0.1.1` is a source-metadata-only errata release. It changes exactly
four evidence-item source contracts through the overlay in
`benchmark/errata/bench_v0.1.1.csv`.

No question wording, claim wording, numeric answer, stance, importance,
temporal role, formula, or answer semantics changed.

## Overlay rules

1. Match an evidence row by `(q_id, q_version, item_id)`.
2. Permit only release-allowlisted source-identification metadata fields.
3. Require the materialized field to equal `old_value` before applying
   `new_value`; otherwise fail.
4. Reject duplicate updates to the same row and field.
5. Preserve every unaffected field and row.
6. Emit and validate a machine-readable release diff.

Provenance used to score this release must bind to the materialized
`bench_v0.1.1` files, not directly to the parent frozen annotations.
"""


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_errata(path: Path = ERRATA_PATH) -> list[dict[str, str]]:
    fields, rows = _read_csv(path)
    missing = REQUIRED_ERRATA_COLUMNS - set(fields)
    if missing:
        raise RuntimeError(f"errata is missing required columns: {sorted(missing)}")
    seen: set[tuple[str, str, str, str]] = set()
    for row in rows:
        if row["benchmark_parent_version"] != PARENT_VERSION:
            raise RuntimeError("errata parent version mismatch")
        if row["benchmark_release_version"] != RELEASE_VERSION:
            raise RuntimeError("errata release version mismatch")
        field = row["field_name"]
        if field not in ALLOWED_FIELDS:
            raise RuntimeError(f"errata field is not source-metadata allowlisted: {field}")
        if field in SEMANTIC_FIELDS:
            raise RuntimeError(f"semantic errata field is forbidden: {field}")
        key = (row["q_id"], row["q_version"], row["item_id"], field)
        if key in seen:
            raise RuntimeError(f"duplicate errata update: {key}")
        seen.add(key)
        if not row["reason"] or not row["supporting_accession"]:
            raise RuntimeError(f"errata lacks source justification: {key}")
    affected = {(r["q_id"], r["q_version"], r["item_id"]) for r in rows}
    expected = {
        ("Q02", "2", "E05"),
        ("Q05", "2", "X3"),
        ("Q05", "2", "X4"),
        ("Q12", "2", "E07"),
    }
    if affected != expected or len(rows) != 8:
        raise RuntimeError(
            f"bench_v0.1.1 must contain exactly eight field rows for four items: {affected}"
        )
    return rows


def _apply_evidence_errata(
    source: Path, destination: Path, errata: list[dict[str, str]]
) -> None:
    fields, rows = _read_csv(source)
    indexed = {tuple(row[field] for field in ROW_KEY): row for row in rows}
    if len(indexed) != len(rows):
        raise RuntimeError("evidence checklist row keys are not unique")
    for correction in errata:
        key = tuple(correction[field] for field in ROW_KEY)
        row = indexed.get(key)
        if row is None:
            raise RuntimeError(f"errata target row does not exist: {key}")
        field = correction["field_name"]
        if row[field] != correction["old_value"]:
            raise RuntimeError(
                f"errata old_value mismatch for {key}/{field}: "
                f"expected {correction['old_value']!r}, found {row[field]!r}"
            )
        row[field] = correction["new_value"]
    _write_csv(destination, fields, rows)


def build_release_diff(
    parent_dir: Path, release_dir: Path, errata: list[dict[str, str]]
) -> dict[str, Any]:
    changes: list[dict[str, str]] = []
    affected_items: set[tuple[str, str, str]] = set()
    for filename in RELEASE_FILES:
        parent = parent_dir / filename
        release = release_dir / filename
        if filename != TARGET_FILE:
            if parent.read_bytes() != release.read_bytes():
                raise RuntimeError(f"unapproved release-file change: {filename}")
            continue
        parent_fields, parent_rows = _read_csv(parent)
        release_fields, release_rows = _read_csv(release)
        if parent_fields != release_fields or len(parent_rows) != len(release_rows):
            raise RuntimeError("evidence checklist schema or row count changed")
        for before, after in zip(parent_rows, release_rows, strict=True):
            before_key = tuple(before[field] for field in ROW_KEY)
            after_key = tuple(after[field] for field in ROW_KEY)
            if before_key != after_key:
                raise RuntimeError(f"evidence row identity changed: {before_key} -> {after_key}")
            for field in parent_fields:
                if before[field] == after[field]:
                    continue
                if field not in ALLOWED_FIELDS:
                    raise RuntimeError(
                        f"unapproved field changed for {before_key}: {field}"
                    )
                affected_items.add(before_key)
                changes.append(
                    {
                        "file": filename,
                        "q_id": before["q_id"],
                        "q_version": before["q_version"],
                        "item_id": before["item_id"],
                        "field_name": field,
                        "old_value": before[field],
                        "new_value": after[field],
                    }
                )
    approved = {
        (r["q_id"], r["q_version"], r["item_id"], r["field_name"], r["old_value"], r["new_value"])
        for r in errata
    }
    observed = {
        (c["q_id"], c["q_version"], c["item_id"], c["field_name"], c["old_value"], c["new_value"])
        for c in changes
    }
    if observed != approved:
        raise RuntimeError("materialized release diff does not exactly match errata overlay")
    if len(affected_items) != 4 or len(changes) != 8:
        raise RuntimeError("release must change exactly two metadata fields on four items")
    return {
        "benchmark_parent_version": PARENT_VERSION,
        "benchmark_release_version": RELEASE_VERSION,
        "affected_item_count": len(affected_items),
        "changed_field_count": len(changes),
        "allowed_changed_fields": sorted(ALLOWED_FIELDS),
        "changes": changes,
        "semantic_change_counts": {
            "question_wording": 0,
            "claim_wording": 0,
            "numeric_facts": 0,
            "numeric_answers_or_values": 0,
            "stance": 0,
            "importance": 0,
            "temporal_role": 0,
            "formula": 0,
            "answer_semantics": 0,
        },
        "validation": {
            "only_allowlisted_metadata_changed": True,
            "all_unaffected_rows_preserved": True,
            "all_unaffected_release_files_byte_identical": True,
        },
    }


def materialize(
    output_dir: Path = RELEASE_DIR,
    parent_dir: Path = FROZEN_DIR,
    errata_path: Path = ERRATA_PATH,
) -> dict[str, Any]:
    errata = load_errata(errata_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    expected_names = {
        *RELEASE_FILES,
        "protocol_addendum.md",
        "release_diff.json",
        "release_manifest.json",
    }
    unexpected = sorted(
        path.name for path in output_dir.iterdir() if path.name not in expected_names
    )
    if unexpected:
        raise RuntimeError(
            f"materialized release directory contains unexpected entries: {unexpected}"
        )
    for filename in RELEASE_FILES:
        source = parent_dir / filename
        destination = output_dir / filename
        if filename == TARGET_FILE:
            _apply_evidence_errata(source, destination, errata)
        else:
            shutil.copyfile(source, destination)
    (output_dir / "protocol_addendum.md").write_text(
        PROTOCOL_ADDENDUM, encoding="utf-8"
    )
    diff = build_release_diff(parent_dir, output_dir, errata)
    (output_dir / "release_diff.json").write_text(
        json.dumps(diff, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = {
        "benchmark_parent_version": PARENT_VERSION,
        "benchmark_release_version": RELEASE_VERSION,
        "errata_file": str(errata_path.relative_to(ROOT)),
        "files": {
            path.name: _sha256(path)
            for path in sorted(output_dir.iterdir())
            if path.is_file() and path.name != "release_manifest.json"
        },
    }
    (output_dir / "release_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {"diff": diff, "manifest": manifest, "errata": errata}


def main() -> int:
    result = materialize()
    print(
        "materialized bench_v0.1.1: "
        f"{result['diff']['affected_item_count']} items, "
        f"{result['diff']['changed_field_count']} metadata fields"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
