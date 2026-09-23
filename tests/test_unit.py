"""Pure unit tests that do not require the downloaded ``data/`` corpus."""

from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import warnings

from src.chunking import chunk_blocks
from src.parser import SectionTracker, classify_heading, extract_blocks
from src.tables import (
    _duration_months,
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
    assert parse_number_text("(4,028)")["parsed_value"] == -4028
    assert parse_number_text("$39,306")["parsed_value"] == 39306
    assert parse_number_text("784")["parsed_value"] == 784


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
