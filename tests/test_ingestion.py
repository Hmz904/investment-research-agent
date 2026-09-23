"""Week 1 SEC filing ingestion acceptance tests.

Expected values are intentionally hard-coded here.  Production parsing code in
``src/`` contains no test-specific or company-specific rules.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import pytest


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


@pytest.fixture(scope="session", autouse=True)
def ensure_pipeline_ran() -> None:
    if not (DATA / "manifest.json").exists():
        from src.pipeline import run

        run()


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _manifest_entries() -> list[dict[str, Any]]:
    return _load_json(DATA / "manifest.json")["entries"]


def _blocks(doc_id: str) -> list[dict[str, Any]]:
    return _load_json(DATA / "parsed" / f"{doc_id}.json")["blocks"]


def _chunks(doc_id: str) -> list[dict[str, Any]]:
    return _load_json(DATA / "chunks" / f"{doc_id}.json")["chunks"]


def _facts(doc_id: str) -> Iterator[dict[str, Any]]:
    for block in _blocks(doc_id):
        yield from block.get("xbrl_facts", [])


def _cells(doc_id: str) -> Iterator[tuple[dict[str, Any], dict[str, Any]]]:
    for block in _blocks(doc_id):
        if block.get("block_type") != "table":
            continue
        for row in block.get("table", {}).get("rows", []):
            for cell in row.get("cells", []):
                yield row, cell


def test_a_nvda_fy27q1_data_center_revenue() -> None:
    facts = [f for f in _facts("NVDA_FY27Q1_10Q") if f["raw_visible_text"] in {"75,246", "39,112"}]
    data_center = [
        f for f in facts
        if any("DataCenterMember" in member for member in f.get("members", []))
    ]
    assert {f["raw_visible_text"] for f in data_center} == {"75,246", "39,112"}
    periods = {(f["period_start"], f["period_end"]) for f in data_center}
    assert len(periods) == 2

    table_chunks = [
        c for c in _chunks("NVDA_FY27Q1_10Q")
        if "75,246" in c["text"] and "39,112" in c["text"]
    ]
    assert table_chunks


def test_b_nvda_fy27q2_hyperscale_recast() -> None:
    cells = [
        (row, cell) for row, cell in _cells("NVDA_FY27Q2_10Q")
        if cell["raw_text"] in {"48,710", "43,050"}
    ]
    hyperscale = [(r, c) for r, c in cells if r["row_label"] == "Hyperscale"]
    assert {c["raw_text"] for _, c in hyperscale} == {"48,710", "43,050"}

    recast = [c for _, c in hyperscale if c["raw_text"] == "43,050"]
    assert recast and recast[0]["period_source"] == "header"
    assert "Apr 26, 2026" in (recast[0]["period_label"] or "")
    assert recast[0]["period_start"] == "2026-01-26"
    assert recast[0]["period_end"] == "2026-04-26"
    assert recast[0]["period_resolution_source"] == "xbrl_context"

    current = [c for _, c in hyperscale if c["raw_text"] == "48,710"]
    assert current and current[0]["period_start"] == "2026-04-27"
    assert current[0]["period_end"] == "2026-07-26"
    assert current[0]["period_resolution_source"] == "xbrl_context"

    context = [
        c for c in _chunks("NVDA_FY27Q2_10Q")
        if "ACIE" in c["text"] and "Hyperscale" in c["text"]
    ]
    assert context


def test_c_msft_fy26q3_cash_flow_facts() -> None:
    facts = [
        f for f in _facts("MSFT_FY26Q3_10Q")
        if f["concept"] == "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment"
        and f["raw_visible_text"] in {"30,876", "80,146"}
    ]
    by_value = {f["raw_visible_text"]: f for f in facts}
    assert by_value["30,876"]["period_start"] == "2026-01-01"
    assert by_value["30,876"]["period_end"] == "2026-03-31"
    assert by_value["80,146"]["period_start"] == "2025-07-01"
    assert by_value["80,146"]["period_end"] == "2026-03-31"


def test_d_msft_fy26q4_intelligent_cloud_cells() -> None:
    wanted = {"$39,306", "16,876", "$15,955"}
    found = {
        cell["raw_text"]: cell
        for row, cell in _cells("MSFT_FY26Q4_8K_EX991")
        if cell["raw_text"] in wanted and cell["period_source"] == "header"
    }
    assert set(found) == wanted
    for cell in found.values():
        assert "2026-06-30" == cell["period_end"]
        assert "Three Months" in (cell["period_label"] or "")
        assert cell["period_start"] is None

    row_labels = {
        cell["raw_text"]: cell["row_label"]
        for row, cell in _cells("MSFT_FY26Q4_8K_EX991")
        if cell["raw_text"] in wanted and cell["period_source"] == "header"
    }
    assert row_labels["16,876"] == "Cost of revenue"


def test_e_msft_fy26_10k_risk_factors_chunk() -> None:
    chunks = [
        c for c in _chunks("MSFT_FY26_10K")
        if "underutilization of infrastructure" in c["text"]
    ]
    assert chunks
    assert any("Risk Factors" in c["section_path"] for c in chunks)


def test_f_meta_2026q2_free_cash_flow_cells() -> None:
    cells = {
        cell["raw_text"]: cell
        for row, cell in _cells("META_2026Q2_8K_EX991")
        if cell["raw_text"] in {"784", "8,549"} and cell["period_source"] == "header"
    }
    assert cells["784"]["period_end"] == "2026-06-30"
    assert cells["8,549"]["period_end"] == "2025-06-30"


def test_g_corpus_integrity_and_second_run_reuse() -> None:
    entries = _manifest_entries()
    assert len(entries) == 14
    assert len({e["doc_id"] for e in entries}) == 14
    assert len({e["accession"] for e in entries}) == 14
    assert sum(1 for e in entries if e["source_role"] == "benchmark_period") == 12
    assert sum(1 for e in entries if e["source_role"] == "historical_reference") == 2

    for entry in entries:
        raw_path = Path(entry["local_path"])
        assert raw_path.exists()
        actual_sha = __import__("hashlib").sha256(raw_path.read_bytes()).hexdigest()
        assert actual_sha == entry["sha256"]

    from src.pipeline import run

    summary = run()
    assert summary["downloaded_raw_files"] == 0
    assert summary["reused_raw_files"] == 14


def test_extra_meta_q1_segment_cells() -> None:
    cells = {
        cell["raw_text"]: cell
        for row, cell in _cells("META_2026Q1_8K_EX991")
        if cell["raw_text"] in {"26,900", "(4,028)"}
    }
    assert cells["26,900"]["parsed_value"] == 26900
    assert cells["(4,028)"]["parsed_value"] == -4028


def test_extra_nvda_q2_ar_concentration_paragraph() -> None:
    blocks = [
        b for b in _blocks("NVDA_FY27Q2_10Q")
        if "Five direct customers" in b["text"]
        and all(pct in b["text"] for pct in ("22 %", "14 %", "13 %", "11 %", "10 %"))
    ]
    assert blocks
    assert blocks[0]["section_path"]
    assert blocks[0]["accession"] == "0001045810-26-000075"


def test_extra_msft_10k_mda_chunk() -> None:
    chunks = [
        c for c in _chunks("MSFT_FY26_10K")
        if "Intelligent Cloud" in c["text"]
        and "Management's Discussion and Analysis" in c["section_path"]
    ]
    assert chunks
    assert chunks[0]["token_count"] <= 1200


def test_meta_percentage_cell_semantics() -> None:
    cell = next(
        c
        for row, c in _cells("META_2026Q2_8K_EX991")
        if c.get("raw_text") == "28"
        and "year-over-year change" in (c.get("row_label") or "")
    )
    assert cell["parsed_value"] == 28
    assert cell["is_percent"] is True
    assert cell["unit_label"] == "percent"
    assert cell["unit_scale"] is None


def test_nvda_75246_table_note_section_path() -> None:
    blocks = _blocks("NVDA_FY27Q1_10Q")
    table = next(
        b for b in blocks
        if b.get("block_type") == "table" and "75,246" in b.get("text", "")
    )
    assert "Note 13" in table["section_path"]


def test_meta_table_retrieval_text() -> None:
    chunk = next(
        c for c in _chunks("META_2026Q2_8K_EX991")
        if "784" in c.get("retrieval_text", "") and "Free cash flow" in c.get("retrieval_text", "")
    )
    assert "Three Months Ended June 30, 2026: 784" in chunk["retrieval_text"]
