"""Pure unit tests that do not require the downloaded ``data/`` corpus."""

from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import warnings

from src.chunking import chunk_blocks
from src.parser import SectionTracker, classify_heading, extract_blocks
from src.storage import INGESTION_SCHEMA_VERSION, corpus_fingerprint
from src.tables import (
    _duration_months,
    _enrich_period_from_cell_facts,
    _reconcile_period_with_direct_facts,
    build_retrieval_text,
    extract_table,
    infer_period,
    parse_number_text,
)


FIXTURES = Path(__file__).parent / "fixtures"


def _soup(path: Path) -> BeautifulSoup:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        return BeautifulSoup(path.read_text(encoding="utf-8"), "lxml")


def _table_soup(html: str) -> BeautifulSoup:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        return BeautifulSoup(html, "lxml")


def test_parenthesized_accounting_negative() -> None:
    assert parse_number_text("(4,028)") is None
    assert parse_number_text("(4,028)", numeric_cell_context=True)["parsed_value"] == -4028
    assert parse_number_text("( 30,876", numeric_cell_context=True)["parsed_value"] == -30876
    assert parse_number_text("$39,306")["parsed_value"] == 39306
    assert parse_number_text("784")["parsed_value"] == 784


def test_financial_change_units() -> None:
    for text in ("0.1 pts", "0.1 pt", "0.1 pp", "0.1 ppt"):
        parsed = parse_number_text(text, numeric_cell_context=True)
        assert parsed is not None
        assert parsed["parsed_value"] == 0.1
        assert parsed["change_unit"] == "percentage_point"
        assert parsed["is_percent"] is False

    for text in ("10 bps", "10 bp"):
        parsed = parse_number_text(text, numeric_cell_context=True)
        assert parsed is not None
        assert parsed["parsed_value"] == 10
        assert parsed["change_unit"] == "basis_point"

    assert parse_number_text("(1)ppt") is None
    parsed = parse_number_text("(1)ppt", numeric_cell_context=True)
    assert parsed is not None
    assert parsed["parsed_value"] == -1
    assert parsed["change_unit"] == "percentage_point"


def test_financial_change_unit_table_metadata_preserves_raw_text() -> None:
    soup = _table_soup(
        """
        <table>
          <tr><th></th><th>Q/Q</th><th>Y/Y</th></tr>
          <tr><td>Gross margin</td><td>0.1 pts</td><td>10 bps</td></tr>
        </table>
        """
    )
    table = extract_table(soup.find("table"), {}, [])
    cells = {
        cell["raw_text"]: cell
        for row in table["rows"]
        for cell in row["cells"]
        if cell.get("parsed_value") is not None
    }
    assert cells["0.1 pts"]["parsed_value"] == 0.1
    assert cells["0.1 pts"]["unit_label"] == "percentage_point"
    assert cells["0.1 pts"]["change_unit"] == "percentage_point"
    assert cells["10 bps"]["parsed_value"] == 10
    assert cells["10 bps"]["unit_label"] == "basis_point"
    assert cells["10 bps"]["change_unit"] == "basis_point"


def test_corpus_fingerprint_excludes_runtime_metadata_and_entry_order() -> None:
    entries = [
        {
            "doc_id": "B",
            "raw_sha256": "raw-b",
            "parsed_sha256": "parsed-b",
            "chunk_sha256": "chunk-b",
            "generated_at": "first",
            "local_path": "/temporary/one",
        },
        {
            "doc_id": "A",
            "raw_sha256": "raw-a",
            "parsed_sha256": "parsed-a",
            "chunk_sha256": "chunk-a",
            "generated_at": "second",
            "local_path": "/temporary/two",
        },
    ]
    first = corpus_fingerprint(entries)
    for entry in entries:
        entry["generated_at"] = "changed"
        entry["local_path"] = "/different/runtime/path"
    assert corpus_fingerprint(list(reversed(entries))) == first
    assert INGESTION_SCHEMA_VERSION == "0.1.1"


def test_note_level_section_path() -> None:
    updates = classify_heading("Note 7. Revenue")
    assert updates.get("note") == "Note 7"

    tracker = SectionTracker()
    tracker.apply({"part": "Part I"})
    tracker.apply({"item": "Item 1"})
    path = tracker.apply(updates)
    assert path[-1] == "Note 7"

    soup = _soup(FIXTURES / "note_heading.html")
    blocks = extract_blocks(soup, "DOC", "ACC", "benchmark_period", {}, [])
    note_paragraphs = [
        b for b in blocks if "Revenue is recognized" in b["text"]
    ]
    assert note_paragraphs
    assert note_paragraphs[0]["section_path"][-1] == "Note 7"


def test_paragraph_boundary_chunking() -> None:
    soup = _soup(FIXTURES / "paragraphs.html")
    blocks = extract_blocks(soup, "DOC", "ACC", "benchmark_period", {}, [])
    chunks = chunk_blocks("DOC", "ACC", "benchmark_period", blocks)

    # Paragraph text is never split across chunks.
    for block in blocks:
        if block["block_type"] == "paragraph":
            assert sum(1 for c in chunks if block["text"] in c["text"]) == 1

    # A single chunk never crosses a section boundary.
    overview_chunk = next(c for c in chunks if "Alpha one" in c["text"])
    assert "Beta one" not in overview_chunk["text"]


def test_duration_months_parsing() -> None:
    assert _duration_months("Three Months Ended") == 3
    assert _duration_months("Six Months Ended") == 6
    assert _duration_months("Nine Months Ended") == 9
    assert _duration_months("Twelve Months Ended") == 12
    assert _duration_months("Revenue") is None
    assert _duration_months("As of June 30, 2026") is None

    period = infer_period(["Three Months Ended", "June 30, 2026"], contexts=[])
    assert period is not None
    assert period["duration_months"] == 3
    assert period["period_start"] is None
    assert period["period_end"] == "2026-06-30"


def test_false_footnote_detection() -> None:
    soup = _table_soup(
        """
        <table>
          <tr><th></th><th>Three Months Ended</th><th>Six Months Ended</th></tr>
          <tr><td>Foreign exchange effect</td><td>(685)</td><td>(2,433)</td></tr>
          <tr><td colspan="3">(1)</td></tr>
        </table>
        """
    )
    table = extract_table(soup.find("table"), {}, [])
    assert "(685)" not in table["footnotes"]
    assert "(2,433)" not in table["footnotes"]
    assert "(1)" in table["footnotes"]


def test_numeric_one_data_cell_is_not_footnote() -> None:
    soup = _table_soup(
        """
        <table>
          <tr><th></th><th>Amount</th><th>Other</th></tr>
          <tr><td>Net income</td><td>(1)</td><td>2,000</td></tr>
        </table>
        """
    )
    table = extract_table(soup.find("table"), {}, [])
    assert table["footnotes"] == []
    cell = next(c for row in table["rows"] for c in row["cells"] if c["raw_text"] == "(1)")
    assert cell["parsed_value"] == -1
    assert cell["is_percent"] is False


def test_structural_footnote_reference_and_body() -> None:
    soup = _table_soup(
        """
        <body>
          <table>
            <tr><td colspan="2">Revenue by Market Platform (1)</td></tr>
            <tr><td>Data Center</td><td>75,246</td></tr>
          </table>
          <div><span>(1) In the first quarter, we changed our presentation and recast comparable periods.</span></div>
        </body>
        """
    )
    blocks = extract_blocks(soup, "DOC", "ACC", "benchmark_period", {}, [])
    table_block = next(b for b in blocks if b["block_type"] == "table")
    assert "(1)" in table_block["table"]["footnote_references"]
    assert any(
        "In the first quarter" in body for body in table_block["table"]["footnotes"]
    )
    body_block = next(b for b in blocks if "In the first quarter" in b["text"])
    assert body_block["block_type"] == "footnote"


def test_row_label_footnote_reference_and_body_after_separator() -> None:
    soup = _table_soup(
        """
        <body>
          <table>
            <tr><th></th><th>Three Months Ended June 30, 2026</th></tr>
            <tr><td>General and administrative (1)</td><td>5,609</td></tr>
          </table>
          <p>____________________</p>
          <p>(1) The expense includes a legal settlement.</p>
        </body>
        """
    )
    blocks = extract_blocks(soup, "DOC", "ACC", "benchmark_period", {}, [])
    table_block = next(block for block in blocks if block["block_type"] == "table")
    table = table_block["table"]
    row = next(row for row in table["rows"] if row["row_label"])
    assert row["row_label"] == "General and administrative"
    assert row["footnote_references"] == ["(1)"]
    assert table["footnote_references"] == ["(1)"]
    label_cell = next(cell for cell in row["cells"] if cell["col"] == 0)
    assert label_cell["raw_text"] == "General and administrative (1)"
    assert table["footnotes"] == ["(1) The expense includes a legal settlement."]
    body_block = next(block for block in blocks if "legal settlement" in block["text"])
    assert body_block["block_type"] == "footnote"


def test_standalone_table_metadata_is_inherited() -> None:
    soup = _table_soup(
        """
        <body>
          <p>CONSOLIDATED CASH FLOWS STATEMENTS</p>
          <p>(In millions) (Unaudited)</p>
          <table>
            <tr><th></th><th>Three Months Ended June 30, 2026</th></tr>
            <tr><td>Cash from operations</td><td>5,609</td></tr>
          </table>
        </body>
        """
    )
    blocks = extract_blocks(soup, "DOC", "ACC", "benchmark_period", {}, [])
    table = next(block["table"] for block in blocks if block["block_type"] == "table")
    assert table["caption"] == "CONSOLIDATED CASH FLOWS STATEMENTS"
    assert table["unit_label"] == "millions"
    assert table["unit_scale"] == 6
    assert table["qualifiers"] == ["Unaudited"]
    cell = next(
        cell
        for row in table["rows"]
        for cell in row["cells"]
        if cell.get("parsed_value") == 5609
    )
    assert cell["unit_label"] == "millions"
    assert cell["unit_scale"] == 6


def test_cell_period_falls_back_to_exact_inline_xbrl_fact() -> None:
    soup = _table_soup(
        """
        <table>
          <tr><th></th><th>Year Ended June 30,</th></tr>
          <tr><th></th><th>2026</th></tr>
          <tr><td>Capital expenditures</td><td><ix:nonfraction id="fact-1">( 1,000</ix:nonfraction></td><td>)</td></tr>
        </table>
        """
    )
    fact = {
        "fact_id": "fact-1",
        "context_id": "context-1",
        "parsed_value": 1000,
        "period_start": "2025-07-01",
        "period_end": "2026-06-30",
    }
    table = extract_table(soup.find("table"), {"fact-1": fact}, [])
    cell = next(
        cell
        for row in table["rows"]
        for cell in row["cells"]
        if cell.get("raw_text") == "( 1,000"
    )
    assert cell["parsed_value"] == -1000
    assert cell["period_start"] == "2025-07-01"
    assert cell["period_end"] == "2026-06-30"
    assert cell["duration_months"] == 12
    assert cell["period_resolution_source"] == "xbrl_fact"
    assert cell["period_resolution_context_id"] == "context-1"
    assert cell["period_reconciliation"]["status"] == "direct_xbrl_overrode_header"


def test_value_match_fallback_assigns_one_unique_context() -> None:
    facts = [
        {
            "fact_id": "fact-1",
            "context_id": "context-1",
            "parsed_value": 1000,
            "period_start": "2025-07-01",
            "period_end": "2026-06-30",
            "unit": "USD",
            "unit_measures": ["iso4217:USD"],
            "scale": 6,
            "dimensions": [],
            "members": [],
            "concept": "example:CapitalExpenditures",
        }
    ]
    period, audit = _enrich_period_from_cell_facts(None, facts, -1000, "2026")
    assert period is not None
    assert period["period_start"] == "2025-07-01"
    assert period["period_end"] == "2026-06-30"
    assert audit == {
        "status": "assigned_unique",
        "matching_fact_count": 1,
        "compatible_context_count": 1,
    }


def test_cell_period_fallback_rejects_incompatible_contexts() -> None:
    facts = [
        {
            "fact_id": "fact-1",
            "concept": "example:CapitalExpenditures",
            "context_id": "context-1",
            "parsed_value": 1000,
            "period_start": "2025-07-01",
            "period_end": "2026-06-30",
            "unit": "USD",
            "unit_measures": ["iso4217:USD"],
            "scale": 6,
            "dimensions": [],
            "members": [],
        },
        {
            "fact_id": "fact-2",
            "concept": "example:CapitalExpenditures",
            "context_id": "context-2",
            "parsed_value": 1000,
            "period_start": "2026-04-01",
            "period_end": "2026-06-30",
            "unit": "USD",
            "unit_measures": ["iso4217:USD"],
            "scale": 6,
            "dimensions": [
                {"axis": "example:RegionAxis", "member": "example:USMember"}
            ],
            "members": ["example:USMember"],
        },
    ]
    period, audit = _enrich_period_from_cell_facts(None, facts, 1000, "2026")
    assert period is None
    assert audit == {
        "status": "rejected_ambiguous",
        "matching_fact_count": 2,
        "compatible_context_count": 2,
    }


def test_direct_xbrl_period_overrides_conflicting_header() -> None:
    header = {
        "period_start": None,
        "period_end": "2026-06-30",
        "instant_date": None,
        "duration_months": 3,
        "period_source": "header",
        "period_label": "Three Months Ended June 30, 2026",
    }
    facts = [
        {
            "context_id": "six-month-context",
            "period_start": "2026-01-01",
            "period_end": "2026-06-30",
            "instant_date": "",
        }
    ]
    period, audit = _reconcile_period_with_direct_facts(
        header, facts, "Three Months Ended June 30, 2026"
    )
    assert period is not None
    assert period["period_start"] == "2026-01-01"
    assert period["period_end"] == "2026-06-30"
    assert period["duration_months"] == 6
    assert period["period_resolution_source"] == "xbrl_fact"
    assert audit == {
        "status": "direct_xbrl_overrode_header",
        "header_period_start": None,
        "header_period_end": "2026-06-30",
        "header_duration_months": 3,
        "direct_period_start": "2026-01-01",
        "direct_period_end": "2026-06-30",
        "direct_instant_date": None,
        "direct_duration_months": 6,
        "direct_fact_count": 1,
        "temporal_signature_count": 1,
    }


def test_direct_xbrl_period_reconciliation_refuses_ambiguous_contexts() -> None:
    header = {
        "period_end": "2026-06-30",
        "duration_months": 3,
        "period_source": "header",
    }
    facts = [
        {"context_id": "q2", "period_start": "2026-04-01", "period_end": "2026-06-30"},
        {"context_id": "h1", "period_start": "2026-01-01", "period_end": "2026-06-30"},
    ]
    period, audit = _reconcile_period_with_direct_facts(header, facts, "period")
    assert period == header
    assert audit == {
        "status": "direct_xbrl_ambiguous",
        "direct_fact_count": 2,
        "temporal_signature_count": 2,
    }


def test_repeated_period_header_band_resets_column_metadata() -> None:
    soup = _table_soup(
        """
        <table>
          <tr><td></td><td colspan="2">Three Months Ended June 30, 2026</td></tr>
          <tr><td></td><td>Shares</td><td>Amount</td></tr>
          <tr><td>Quarter activity</td><td>1,000</td><td>2,000</td></tr>
          <tr><td></td><td colspan="2">Six Months Ended June 30, 2026</td></tr>
          <tr><td></td><td>Shares</td><td>Amount</td></tr>
          <tr><td>Year-to-date activity</td><td>30</td><td>40</td></tr>
        </table>
        """
    )
    table = extract_table(soup.find("table"), {}, [])
    cells = {
        (cell["row_label"], cell["raw_text"]): cell
        for row in table["rows"]
        for cell in row["cells"]
        if cell.get("parsed_value") is not None
    }

    assert cells[("Quarter activity", "1,000")]["duration_months"] == 3
    assert cells[("Year-to-date activity", "30")]["duration_months"] == 6
    assert (
        cells[("Year-to-date activity", "30")]["column_label"]
        == "Six Months Ended June 30, 2026 Shares"
    )
    assert len(table["header_bands"]) == 2
    assert all(
        row["row_label"] not in {
            "Six Months Ended June 30, 2026",
            "Shares",
        }
        for row in table["rows"]
    )


def test_percentage_semantics() -> None:
    soup = _table_soup(
        """
        <table>
          <tr><td colspan="3">Reconciliation</td></tr>
          <tr><td colspan="3">(In millions, except percentages)</td></tr>
          <tr><td></td><td>Three Months Ended June 30, 2026</td><td></td></tr>
          <tr><td>GAAP revenue</td><td>60,801</td><td>47,516</td></tr>
          <tr><td>GAAP revenue year-over-year change %</td><td>28</td><td>%</td></tr>
        </table>
        """
    )
    table = extract_table(soup.find("table"), {}, [])
    cell = next(
        c
        for row in table["rows"]
        for c in row["cells"]
        if c.get("raw_text") == "28"
    )
    assert cell["parsed_value"] == 28
    assert cell["is_percent"] is True
    assert cell["unit_label"] == "percent"
    assert cell["unit_scale"] is None


def test_table_metadata_normalization() -> None:
    soup = _table_soup(
        """
        <table>
          <tr><td colspan="3">Reconciliation of GAAP to Non-GAAP Results</td></tr>
          <tr><td colspan="3">(In millions, except percentages)</td></tr>
          <tr><td colspan="3">(Unaudited)</td></tr>
          <tr><td></td><td>Three Months Ended June 30,</td><td></td></tr>
          <tr><td></td><td>2026</td><td>2025</td></tr>
          <tr><td>Revenue</td><td>1,000</td><td>900</td></tr>
        </table>
        """
    )
    table = extract_table(soup.find("table"), {}, [])
    assert table["caption"] == "Reconciliation of GAAP to Non-GAAP Results"
    assert table["unit_label"] == "millions, except percentages"
    assert table["qualifiers"] == ["Unaudited"]
    assert "Reconciliation" not in table["column_labels"][1]
    assert "(In millions" not in table["column_labels"][1]
    assert table["column_labels"][1] == "Three Months Ended June 30, 2026"


def test_retrieval_text_serialization() -> None:
    soup = _table_soup(
        """
        <table>
          <tr><td colspan="3">Reconciliation of GAAP to Non-GAAP Results</td></tr>
          <tr><td colspan="3">(In millions, except percentages)</td></tr>
          <tr><td></td><td>Three Months Ended June 30, 2026</td><td>Six Months Ended June 30, 2026</td></tr>
          <tr><td>Foreign exchange effect</td><td>(685)</td><td>(2,433)</td></tr>
        </table>
        """
    )
    table = extract_table(soup.find("table"), {}, [])
    text = build_retrieval_text(table)
    assert "Three Months Ended June 30, 2026: (685)" in text
    assert "Six Months Ended June 30, 2026: (2,433)" in text
    assert "Row: Foreign exchange effect" in text


def test_retrieval_text_percent_suffix() -> None:
    soup = _table_soup(
        """
        <table>
          <tr><td colspan="3">Reconciliation</td></tr>
          <tr><td colspan="3">(In millions, except percentages)</td></tr>
          <tr><td></td><td>Three Months Ended June 30, 2026</td><td></td></tr>
          <tr><td>GAAP revenue</td><td>60,801</td><td>47,516</td></tr>
          <tr><td>GAAP revenue year-over-year change %</td><td>28</td><td>%</td></tr>
        </table>
        """
    )
    table = extract_table(soup.find("table"), {}, [])
    text = build_retrieval_text(table)
    assert "Three Months Ended June 30, 2026: 28%" in text
    assert "Three Months Ended June 30, 2026: 60,801" in text


def test_note_persistence_across_continuation_header() -> None:
    soup2 = _table_soup(
        """
        <body>
          <div><span>Note 7. Revenue</span></div>
          <div><span>Revenue is recognized when control transfers.</span></div>
          <div><span>Notes to Condensed Consolidated Financial Statements (Continued)</span></div>
          <div><span>After continuation.</span></div>
        </body>
        """
    )
    blocks = extract_blocks(soup2, "DOC", "ACC", "benchmark_period", {}, [])
    after = [b for b in blocks if "After continuation" in b["text"]]
    assert after and after[0]["section_path"][-1] == "Note 7"


def test_exhibit_root_section() -> None:
    soup = _table_soup(
        "<body><div><span>Free cash flow reconciliation</span></div></body>"
    )
    blocks = extract_blocks(
        soup, "DOC", "ACC", "benchmark_period", {}, [], root_section="Exhibit 99.1"
    )
    assert blocks
    assert blocks[0]["section_path"][0] == "Exhibit 99.1"
