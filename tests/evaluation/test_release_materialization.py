"""Metadata-only bench_v0.1.1 errata and materialization tests."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from evaluation import materialize_release


pytestmark = pytest.mark.locked_test_data


ROOT = Path(__file__).resolve().parents[2]
ERRATA = ROOT / "benchmark" / "errata" / "bench_v0.1.1.csv"
RELEASE = ROOT / "benchmark" / "releases" / "v0.1.1"


EXPECTED_CHANGES = {
    ("Q02", "2", "E05", "accession", "0001045810-26-000052", "0001045810-26-000051"),
    ("Q02", "2", "E05", "location", "Item 2 MD&A; Data Center discussion", "Exhibit 99.1; Data Center discussion"),
    ("Q05", "2", "X3", "accession", "0001045810-26-000073", "0001045810-26-000051;0001045810-26-000073"),
    ("Q05", "2", "X3", "location", "Exhibit 99.1; realized Q2 results compared with prior outlook", "Exhibit 99.1; Q1 outlook and Q2 realized results"),
    ("Q05", "2", "X4", "accession", "0001045810-26-000075", "0001045810-26-000052;0001045810-26-000075"),
    ("Q05", "2", "X4", "location", "Item 2 MD&A; market-platform reclassification note", "Item 2 MD&A; original and recast Revenue by Market Platform presentations"),
    ("Q12", "2", "E07", "accession", "0001628280-26-028364", "0001628280-26-028364;0001628280-26-028526"),
    ("Q12", "2", "E07", "location", "Exhibit 99.1; cash flow and expense disclosures", "Exhibit 99.1; cash flow statement AND Form 10-Q; Part I Item 1 Note 6; property and server/network depreciation"),
}


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_errata_contains_exactly_four_approved_source_contract_corrections() -> None:
    rows = materialize_release.load_errata()
    observed = {
        (
            row["q_id"], row["q_version"], row["item_id"], row["field_name"],
            row["old_value"], row["new_value"],
        )
        for row in rows
    }
    assert observed == EXPECTED_CHANGES
    assert {row["field_name"] for row in rows} == {"accession", "location"}
    assert all(row["supporting_chunk_id"] for row in rows)
    assert all(row["supporting_anchor_id"] for row in rows)


def test_errata_rejects_semantic_fields(tmp_path: Path) -> None:
    with ERRATA.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    rows[0]["field_name"] = "claim"
    invalid = tmp_path / "invalid.csv"
    with invalid.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(RuntimeError, match="not source-metadata allowlisted"):
        materialize_release.load_errata(invalid)


def test_materialization_is_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    materialize_release.materialize(first)
    materialize_release.materialize(second)
    first_files = {path.name: path.read_bytes() for path in first.iterdir()}
    second_files = {path.name: path.read_bytes() for path in second.iterdir()}
    assert first_files == second_files


def test_materialized_release_diff_is_exact_and_semantics_are_unchanged() -> None:
    diff = json.loads((RELEASE / "release_diff.json").read_text(encoding="utf-8"))
    assert diff["affected_item_count"] == 4
    assert diff["changed_field_count"] == 8
    assert diff["allowed_changed_fields"] == ["accession", "location"]
    observed = {
        (
            row["q_id"], row["q_version"], row["item_id"], row["field_name"],
            row["old_value"], row["new_value"],
        )
        for row in diff["changes"]
    }
    assert observed == EXPECTED_CHANGES
    assert set(diff["semantic_change_counts"].values()) == {0}
    assert all(diff["validation"].values())


def test_unaffected_release_files_are_byte_identical_to_parent() -> None:
    frozen = ROOT / "benchmark" / "frozen"
    for filename in materialize_release.RELEASE_FILES:
        if filename != materialize_release.TARGET_FILE:
            assert (frozen / filename).read_bytes() == (RELEASE / filename).read_bytes()

    parent_rows = _rows(frozen / materialize_release.TARGET_FILE)
    release_rows = _rows(RELEASE / materialize_release.TARGET_FILE)
    changed = []
    for before, after in zip(parent_rows, release_rows, strict=True):
        for field in before:
            if before[field] != after[field]:
                changed.append((before["q_id"], before["q_version"], before["item_id"], field))
    assert set(changed) == {
        (q_id, q_version, item_id, field)
        for q_id, q_version, item_id, field, _old, _new in EXPECTED_CHANGES
    }
