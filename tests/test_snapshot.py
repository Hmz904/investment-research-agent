"""Corpus-stats regression snapshot test.

Any per-document decrease is a failure.  Any increase is also a failure unless
the snapshot is explicitly regenerated with ``--regenerate-snapshots``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SNAPSHOT = Path(__file__).resolve().parent / "snapshots" / "corpus_stats.json"

METRICS = (
    "tables",
    "chunks",
    "xbrl_facts",
    "numeric_cells_with_header_periods",
    "percent_cells",
    "footnotes",
)


def _current_stats() -> dict[str, dict[str, int]]:
    stats: dict[str, dict[str, int]] = {}
    for path in sorted((DATA / "parsed").glob("*.json")):
        doc_id = path.name[:-5]
        parsed = json.loads(path.read_text(encoding="utf-8"))
        blocks = parsed["blocks"]
        chunks = json.loads(
            (DATA / "chunks" / f"{doc_id}.json").read_text(encoding="utf-8")
        )["chunks"]

        tables = 0
        numeric_cells = 0
        percent_cells = 0
        footnotes = 0
        for block in blocks:
            if block.get("block_type") != "table":
                continue
            tables += 1
            table = block.get("table", {})
            footnotes += len(table.get("footnotes", []))
            for row in table.get("rows", []):
                for cell in row.get("cells", []):
                    if cell.get("parsed_value") is None:
                        continue
                    if cell.get("period_source") == "header":
                        numeric_cells += 1
                    if cell.get("is_percent"):
                        percent_cells += 1

        stats[doc_id] = {
            "tables": tables,
            "chunks": len(chunks),
            "xbrl_facts": parsed.get("xbrl_fact_count", 0),
            "numeric_cells_with_header_periods": numeric_cells,
            "percent_cells": percent_cells,
            "footnotes": footnotes,
        }
    return stats


def test_corpus_stats_snapshot(request: pytest.FixtureRequest) -> None:
    current = _current_stats()
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    if request.config.getoption("--regenerate-snapshots"):
        SNAPSHOT.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
        return

    failures: list[str] = []
    for doc_id in sorted(set(snapshot) | set(current)):
        expected = snapshot.get(doc_id, {})
        actual = current.get(doc_id, {})
        for metric in METRICS:
            exp = expected.get(metric, 0)
            act = actual.get(metric, 0)
            if act < exp:
                failures.append(
                    f"{doc_id} {metric} decreased: {exp} -> {act}"
                )
            elif act > exp:
                failures.append(
                    f"{doc_id} {metric} increased: {exp} -> {act} "
                    "(run pytest with --regenerate-snapshots to accept)"
                )

    assert not failures, "\n".join(failures)

