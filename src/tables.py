"""Generic SEC table extraction with header-driven period provenance."""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from bs4 import Tag


MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\u00a0", " ").replace("\u2009", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _cell_text(cell: Tag) -> str:
    return normalize_text(cell.get_text(" ", strip=True))


def parse_number_text(text: str) -> dict[str, Any] | None:
    """Parse a table cell into its numeric value and simple numeric flags."""
    t = normalize_text(text)
    if not t:
        return None
    is_percent = "%" in t
    cleaned = t.replace("$", "").replace("\u00a0", "").replace(" ", "")
    cleaned = cleaned.replace("%", "")
    cleaned = cleaned.replace(",", "")
    negative = False
    if cleaned.startswith("(") and cleaned.endswith(")"):
        negative = True
        cleaned = cleaned[1:-1]
    elif cleaned.startswith("-"):
        negative = True
        cleaned = cleaned[1:]
    elif cleaned.startswith("+"):
        cleaned = cleaned[1:]
    cleaned = cleaned.strip()
    if not re.fullmatch(r"\d+(?:\.\d+)?", cleaned):
        return None
    try:
        value: float | int
        if "." in cleaned:
            value = float(cleaned)
        else:
            value = int(cleaned)
    except ValueError:
        return None
    if negative:
        value = -value
    return {
        "parsed_value": value,
        "is_percent": is_percent,
        "is_negative": negative,
        "has_comma": "," in t,
    }


def is_numeric_data_cell(text: str) -> bool:
    parsed = parse_number_text(text)
    if parsed is None:
        return False
    if parsed["is_percent"]:
        return True
    if parsed["has_comma"]:
        return True
    # A bare four-digit year is a header label, not a data value.
    if re.fullmatch(r"\d{4}", normalize_text(text).strip("()")):
        return False
    if abs(parsed["parsed_value"]) >= 1000:
        return True
    return False


def build_grid(table: Tag) -> tuple[list[list[Tag | None]], int]:
    rows = table.find_all("tr")
    ncols = 0
    for tr in rows:
        total = sum(int(c.get("colspan") or 1) for c in tr.find_all(["td", "th"], recursive=False))
        ncols = max(ncols, total)

    grid: list[list[Tag | None]] = [[None] * ncols for _ in range(len(rows))]
    for ri, tr in enumerate(rows):
        ci = 0
        for cell in tr.find_all(["td", "th"], recursive=False):
            while ci < ncols and grid[ri][ci] is not None:
                ci += 1
            colspan = int(cell.get("colspan") or 1)
            rowspan = int(cell.get("rowspan") or 1)
            for dr in range(rowspan):
                for dc in range(colspan):
                    rr = ri + dr
                    cc = ci + dc
                    if rr < len(grid) and cc < ncols:
                        grid[rr][cc] = cell
            ci += colspan
    return grid, ncols


def _row_cells(grid: list[list[Tag | None]], row: int) -> list[Tag | None]:
    return grid[row]


def find_first_data_row(grid: list[list[Tag | None]], ncols: int) -> int:
    for ri in range(len(grid)):
        row = grid[ri]
        label_text = ""
        label_found = False
        for ci in range(ncols):
            cell = row[ci]
            if cell is None:
                continue
            text = _cell_text(cell)
            if not text:
                continue
            if not label_found and not is_numeric_data_cell(text):
                label_text = text
                label_found = True
                continue
            if label_found and is_numeric_data_cell(text):
                return ri
    return len(grid)


def _header_rows_for(grid: list[list[Tag | None]], ncols: int) -> int:
    first_data = find_first_data_row(grid, ncols)
    return max(0, first_data)


def _column_header_texts(
    grid: list[list[Tag | None]],
    ncols: int,
    header_rows: int,
    col: int,
    skip_rows: set[int] | None = None,
) -> list[str]:
    skip_rows = skip_rows or set()
    texts: list[str] = []
    for r in range(header_rows):
        if r in skip_rows:
            continue
        cell = grid[r][col]
        if cell is None:
            continue
        text = _cell_text(cell)
        if text and (not texts or texts[-1] != text):
            texts.append(text)
    return texts


def detect_unit_scale(*texts: str) -> tuple[int | None, str | None]:
    joined = " ".join(texts).lower()
    pairs = [
        ("billion", 9, "billions"),
        ("million", 6, "millions"),
        ("thousand", 3, "thousands"),
    ]
    for keyword, exponent, label in pairs:
        if keyword in joined:
            return exponent, label
    return None, None


_MONTH_RE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
    r"\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(?:,?\s*(20\d{2}))?",
    re.IGNORECASE,
)
_MONTH_ONLY_RE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*,?\s*(20\d{2})?",
    re.IGNORECASE,
)
_ISO_RE = re.compile(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b")
_YEAR_RE = re.compile(r"\b(20\d{2})\b")


def _last_day_of_month(year: int, month: int) -> int:
    if month == 12:
        nxt_year, nxt_month = year + 1, 1
    else:
        nxt_year, nxt_month = year, month + 1
    first_of_next = date(nxt_year, nxt_month, 1)
    return (first_of_next - timedelta(days=1)).day


def _extract_date_values(joined: str) -> tuple[list[date], list[int]]:
    dates: list[date] = []
    years_pos: list[tuple[int, int]] = []

    for m in _ISO_RE.finditer(joined):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            dates.append(date(y, mo, d))
        except ValueError:
            pass

    for m in _YEAR_RE.finditer(joined):
        years_pos.append((m.start(), int(m.group(1))))

    for m in _MONTH_RE.finditer(joined):
        month = MONTHS[m.group(1).lower()]
        day = int(m.group(2))
        year = int(m.group(3)) if m.group(3) else None
        if year is None:
            for pos, y in years_pos:
                if pos >= m.end() and pos <= m.end() + 12:
                    year = y
                    break
        if year is None:
            continue
        try:
            dates.append(date(year, month, day))
        except ValueError:
            pass

    existing_months = {(d.year, d.month) for d in dates}
    for m in _MONTH_ONLY_RE.finditer(joined):
        month = MONTHS[m.group(1).lower()]
        year = int(m.group(2)) if m.group(2) else None
        if year is None or (year, month) in existing_months:
            continue
        try:
            dates.append(date(year, month, _last_day_of_month(year, month)))
            existing_months.add((year, month))
        except ValueError:
            pass

    # De-duplicate while preserving order.
    unique: list[date] = []
    seen: set[date] = set()
    for d in dates:
        if d not in seen:
            seen.add(d)
            unique.append(d)
    unique.sort()
    return unique, [y for _, y in sorted(years_pos)]


def _duration_months(joined: str) -> int | None:
    low = joined.lower()
    patterns = [
        (r"\btwelve\s*months?\b", 12),
        (r"\byear\s+ended\b", 12),
        (r"\bfiscal\s+year\b", 12),
        (r"\bnine\s*months?\b", 9),
        (r"\bsix\s*months?\b", 6),
        (r"\bthree\s*months?\b", 3),
        (r"\bquarter\b", 3),
        (r"\bone\s*month\b", 1),
        (r"\bmonth\s+ended\b", 1),
    ]
    for pattern, months in patterns:
        if re.search(pattern, low):
            return months
    return None


_FOOTNOTE_MARKER_RE = re.compile(
    r"^(?:\(\d{1,3}\)|\([a-z]\)|\[\d{1,3}\]|\d{1,3}\))\s*$",
    re.IGNORECASE,
)

_FOOTNOTE_MARKER_IN_TEXT_RE = re.compile(
    r"\(\d{1,3}\)|\([a-z]\)|\[\d{1,3}\]|\b\d{1,3}\)",
    re.IGNORECASE,
)

_UNIT_META_RE = re.compile(
    r"^\(\s*\$?\s*(?:in\s*\$?\s*)?(millions?|thousands?|billions?)"
    r"\s*(?:,\s*except\s+percentages?)?\s*\)\s*$",
    re.IGNORECASE,
)

_QUALIFIER_META_RE = re.compile(
    r"^\(\s*(unaudited|audited|continued|restated)\s*\)\s*$",
    re.IGNORECASE,
)


def _is_footnote_marker(text: str) -> bool:
    return bool(_FOOTNOTE_MARKER_RE.match(text))


def _footnote_markers_in_text(text: str) -> list[str]:
    return _FOOTNOTE_MARKER_IN_TEXT_RE.findall(text)


def _extract_footnote_references(
    grid: list[list[Tag | None]], ncols: int, header_rows: int
) -> list[str]:
    """Collect footnote references attached to headings/labels (not data cells)."""
    refs: list[str] = []
    seen: set[str] = set()
    for r in range(header_rows):
        visited: set[int] = set()
        for c in range(ncols):
            cell = grid[r][c]
            if cell is None or id(cell) in visited:
                continue
            visited.add(id(cell))
            text = _cell_text(cell)
            for marker in _footnote_markers_in_text(text):
                if marker not in seen:
                    seen.add(marker)
                    refs.append(marker)
            for sup in cell.find_all(["sup", "sub"]):
                marker = _cell_text(sup)
                if _is_footnote_marker(marker) and marker not in seen:
                    seen.add(marker)
                    refs.append(marker)
    return refs


def _is_unit_meta(text: str) -> bool:
    return bool(_UNIT_META_RE.match(text))


def _is_qualifier_meta(text: str) -> bool:
    return bool(_QUALIFIER_META_RE.match(text))


def _is_metadata_cell(text: str) -> bool:
    return _is_unit_meta(text) or _is_qualifier_meta(text)


def _is_title_text(text: str) -> bool:
    if not text or _is_metadata_cell(text):
        return False
    if _duration_months(text) is not None:
        return False
    if _extract_date_values(text)[0]:
        return False
    return parse_number_text(text) is None


def _cell_span_width(grid: list[list[Tag | None]], row: int, ncols: int, cell: Tag) -> int:
    width = 0
    for c in range(ncols):
        if grid[row][c] is cell:
            width += 1
    return width


def _metadata_info(
    grid: list[list[Tag | None]], ncols: int, header_rows: int
) -> tuple[set[int], str, str | None, list[str]]:
    """Identify full-width/unit/qualifier metadata rows and their meaning."""
    meta_rows: set[int] = set()
    caption = ""
    unit_label: str | None = None
    qualifiers: list[str] = []

    for r in range(header_rows):
        cells: dict[int, tuple[Tag, str]] = {}
        for c in range(ncols):
            cell = grid[r][c]
            if cell is None:
                continue
            text = _cell_text(cell)
            if not text:
                continue
            cells[id(cell)] = (cell, text)
        if not cells:
            continue

        if len(cells) == 1:
            cell, text = next(iter(cells.values()))
            width = _cell_span_width(grid, r, ncols, cell)
            if width >= ncols - 1:
                if _is_unit_meta(text):
                    meta_rows.add(r)
                    unit_label = _normalize_unit_label(text)
                elif _is_qualifier_meta(text):
                    meta_rows.add(r)
                    qualifiers.append(text.strip("()"))
                elif _is_title_text(text):
                    meta_rows.add(r)
                    if not caption:
                        caption = text
                continue

        non_empty = [text for _, text in cells.values()]
        if non_empty and all(_is_metadata_cell(text) for text in non_empty):
            meta_rows.add(r)
            for _, text in cells.values():
                if _is_unit_meta(text):
                    unit_label = _normalize_unit_label(text)
                elif _is_qualifier_meta(text):
                    qualifiers.append(text.strip("()"))
            continue

        # A single label-cell row with no data cells is a table title.
        if len(cells) == 1:
            cell, text = next(iter(cells.values()))
            if _is_title_text(text) and not caption:
                caption = text

    return meta_rows, caption, unit_label, qualifiers


def _normalize_unit_label(text: str) -> str:
    inner = text.strip("()").strip()
    inner = re.sub(r"^\$?\s*in\s*\$?\s*", "", inner, flags=re.IGNORECASE)
    return inner


def _row_label_denotes_percent(row_label: str) -> bool:
    low = (row_label or "").lower()
    if any(token in low for token in ("%", "percent", "percentage")):
        return True
    # Singular "rate" denotes a percentage rate; plural "rates" (for example
    # foreign-exchange or interest rates) does not.
    return bool(re.search(r"\brate\b", low))


def _column_label_denotes_percent(column_label: str) -> bool:
    low = (column_label or "").lower()
    return any(token in low for token in ("% change", "change %", "percent", "percentage"))


def _has_percent_sibling(
    grid: list[list[Tag | None]], row: int, col_start: int, col_end: int, ncols: int
) -> bool:
    for c in (col_start - 1, col_end + 1):
        if 0 <= c < ncols:
            cell = grid[row][c]
            if cell is not None and "%" in _cell_text(cell):
                return True
    return False


def _cell_is_percent(
    raw_text: str,
    row_label: str,
    column_label: str,
    grid: list[list[Tag | None]],
    row: int,
    col_start: int,
    col_end: int,
    ncols: int,
) -> bool:
    if "%" in raw_text:
        return True
    if _row_label_denotes_percent(row_label):
        return True
    if _column_label_denotes_percent(column_label):
        return True
    if _has_percent_sibling(grid, row, col_start, col_end, ncols):
        return True
    return False


def _is_genuine_footnote_cell(
    raw_text: str,
    cell: Tag,
    row_cells: list[Tag | None],
    column_label: str,
) -> bool:
    if not _is_footnote_marker(raw_text):
        return False
    # Structural evidence: a superscript/subscript marker is a reference.
    if cell.find(["sup", "sub"]) is not None:
        return True
    # A marker sitting in an effective data column is a numeric value, not a
    # footnote reference (for example a lone "(118)" meaning -118).
    if (column_label or "").strip():
        return False
    # A marker in a row with no numeric data values is a footnote reference.
    row_has_numeric = any(
        c is not None and c is not cell and parse_number_text(_cell_text(c)) is not None
        for c in row_cells
    )
    return not row_has_numeric


def build_retrieval_text(table: dict[str, Any]) -> str:
    """Deterministic, retrieval-safe row-by-row table serialization."""
    lines: list[str] = []
    caption = (table.get("caption") or "").strip()
    if caption:
        lines.append(f"Table: {caption}")

    unit_label = (table.get("unit_label") or "").strip()
    if unit_label:
        if unit_label.lower().startswith(("usd", "us $")):
            lines.append(f"Unit: {unit_label}")
        else:
            lines.append(f"Unit: USD {unit_label}")

    qualifiers = [q for q in table.get("qualifiers", []) if q]
    if qualifiers:
        lines.append("Qualifiers: " + ", ".join(qualifiers))

    for row in table.get("rows", []):
        row_label = (row.get("row_label") or "").strip()
        if not row_label:
            continue
        lines.append(f"Row: {row_label}")
        for cell in row.get("cells", []):
            if cell.get("parsed_value") is None:
                continue
            column_label = (cell.get("column_label") or "").strip()
            if not column_label:
                continue
            raw_text = (cell.get("raw_text") or "").strip()
            display_text = raw_text
            if cell.get("is_percent") and not display_text.endswith("%"):
                display_text = f"{display_text}%"
            lines.append(f"- {column_label}: {display_text}")
    return "\n".join(lines)


def _months_between(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month)


def _resolve_start_from_contexts(
    period_end: date,
    duration_months: int | None,
    contexts: list[dict[str, Any]],
) -> tuple[str | None, str | None]:
    """Resolve an exact duration start from compatible inline-XBRL contexts.

    Only contexts that end on the same date and (when known) have the same
    duration class are considered.  When several remain, the most general
    context (fewest dimensions) wins, with ``context_id`` as a deterministic
    tie-breaker.  No calendar-month approximation is ever invented here.
    """
    end_iso = period_end.isoformat()
    candidates: list[tuple[int, str, str]] = []
    for ctx in contexts:
        if ctx.get("instant_date") or not ctx.get("period_start"):
            continue
        if ctx.get("period_end") != end_iso:
            continue
        start_iso = ctx["period_start"]
        try:
            start = date.fromisoformat(start_iso)
        except ValueError:
            continue
        if duration_months is not None and _months_between(start, period_end) != duration_months:
            continue
        candidates.append((len(ctx.get("dimensions", [])), ctx.get("id", ""), start_iso))

    if not candidates:
        return None, None
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2], candidates[0][1]


def infer_period(
    headers: list[str],
    contexts: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    joined = " ".join(headers)
    low = joined.lower()
    dates, _years = _extract_date_values(joined)
    contexts = contexts or []
    duration = _duration_months(joined)

    explicit_start_end = bool(
        re.search(r"\bfrom\b", low)
        or ("-" in joined and len(dates) >= 2)
        or ("to" in low and len(dates) >= 2)
    )
    if explicit_start_end and len(dates) >= 2:
        return {
            "period_start": dates[0].isoformat(),
            "period_end": dates[-1].isoformat(),
            "instant_date": None,
            "period_label": " ".join(headers),
            "period_source": "header",
            "period_resolution_source": "header_explicit",
            "period_resolution_context_id": None,
            "duration_months": duration,
        }

    if duration is not None and dates:
        end = dates[-1]
        start, context_id = _resolve_start_from_contexts(end, duration, contexts)
        return {
            "period_start": start,
            "period_end": end.isoformat(),
            "instant_date": None,
            "period_label": " ".join(headers),
            "period_source": "header",
            "period_resolution_source": "xbrl_context" if start else "header",
            "period_resolution_context_id": context_id,
            "duration_months": duration,
        }

    instant = bool(re.search(r"\bas\s+of\b|\bat\s+\w+", low))
    if dates:
        d = dates[-1]
        return {
            "period_start": d.isoformat(),
            "period_end": d.isoformat(),
            "instant_date": d.isoformat(),
            "period_label": " ".join(headers),
            "period_source": "header",
            "period_resolution_source": "header_explicit",
            "period_resolution_context_id": None,
            "duration_months": duration,
        }
    return None


def _cell_facts(cell: Tag, fact_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for fact in cell.find_all(("ix:nonfraction", "ix:nonnumeric")):
        if fact.find(("ix:nonfraction", "ix:nonnumeric")) is not None:
            continue
        fid = fact.get("id", "")
        record = fact_by_id.get(fid)
        if record is not None:
            facts.append(record)
    return facts


def extract_table(
    table: Tag,
    fact_by_id: dict[str, dict[str, Any]],
    contexts: list[dict[str, Any]],
) -> dict[str, Any]:
    grid, ncols = build_grid(table)
    header_rows = _header_rows_for(grid, ncols)

    caption_el = table.find("caption")
    caption = _cell_text(caption_el) if caption_el is not None else ""
    meta_rows, meta_caption, meta_unit_label, qualifiers = _metadata_info(
        grid, ncols, header_rows
    )
    if meta_caption:
        caption = meta_caption
    if meta_unit_label:
        unit_label = meta_unit_label
    else:
        unit_label = None

    header_texts: list[list[str]] = []
    for r in range(header_rows):
        row_texts: list[str] = []
        seen: set[int] = set()
        for c in range(ncols):
            cell = grid[r][c]
            if cell is None or id(cell) in seen:
                continue
            seen.add(id(cell))
            text = _cell_text(cell)
            row_texts.append(text)
        header_texts.append(row_texts)

    column_labels: list[str] = []
    column_periods: list[dict[str, Any] | None] = []
    for col in range(ncols):
        texts = _column_header_texts(grid, ncols, header_rows, col, meta_rows)
        column_labels.append(" ".join(t for t in texts if t))
        column_periods.append(infer_period(texts, contexts))

    footnote_references = _extract_footnote_references(grid, ncols, header_rows)

    unit_scale, _detected_label = detect_unit_scale(
        caption, *(c for row in header_texts for c in row)
    )
    if unit_label is None:
        unit_label = _detected_label

    rows_out: list[dict[str, Any]] = []
    footnotes: list[str] = []
    for r in range(header_rows, len(grid)):
        row_cells = grid[r]
        row_label = ""
        seen: set[int] = set()
        row_facts: list[dict[str, Any]] = []

        # Determine the row label from the left-most non-numeric cell.
        for c in range(ncols):
            cell = row_cells[c]
            if cell is None:
                continue
            text = _cell_text(cell)
            if text and not is_numeric_data_cell(text):
                row_label = text
                break

        cells_out: list[dict[str, Any]] = []
        for c in range(ncols):
            cell = row_cells[c]
            if cell is None or id(cell) in seen:
                continue
            seen.add(id(cell))
            raw_text = _cell_text(cell)
            if not raw_text:
                continue

            # Determine the contiguous span of this cell.
            col_end = c
            while col_end + 1 < ncols and row_cells[col_end + 1] is cell:
                col_end += 1

            parsed = parse_number_text(raw_text)
            facts = _cell_facts(cell, fact_by_id)
            row_facts.extend(facts)

            column_label = column_labels[c] if c < len(column_labels) else ""
            percent = _cell_is_percent(
                raw_text=raw_text,
                row_label=row_label,
                column_label=column_label,
                grid=grid,
                row=r,
                col_start=c,
                col_end=col_end,
                ncols=ncols,
            )
            cell_unit_scale = unit_scale
            cell_unit_label = unit_label
            if percent:
                cell_unit_scale = None
                cell_unit_label = "percent"

            period = column_periods[c] if parsed is not None else None
            cell_record: dict[str, Any] = {
                "col": c,
                "col_end": col_end,
                "row_label": row_label,
                "column_label": column_label,
                "raw_text": raw_text,
                "parsed_value": parsed["parsed_value"] if parsed else None,
                "is_percent": percent,
                "unit_scale": cell_unit_scale,
                "unit_label": cell_unit_label,
                "period_start": period["period_start"] if period else None,
                "period_end": period["period_end"] if period else None,
                "instant_date": period["instant_date"] if period else None,
                "period_label": period["period_label"] if period else None,
                "period_source": period["period_source"] if period else None,
                "period_resolution_source": period["period_resolution_source"] if period else None,
                "period_resolution_context_id": period["period_resolution_context_id"] if period else None,
                "duration_months": period["duration_months"] if period else None,
                "xbrl_facts": facts,
            }
            cells_out.append(cell_record)

            if _is_genuine_footnote_cell(
                raw_text=raw_text,
                cell=cell,
                row_cells=row_cells,
                column_label=column_label,
            ):
                if raw_text not in footnotes:
                    footnotes.append(raw_text)

        if row_label or cells_out:
            rows_out.append(
                {
                    "row_label": row_label,
                    "cells": cells_out,
                    "xbrl_facts": row_facts,
                }
            )

    table_text = normalize_text(table.get_text(" ", strip=True))
    return {
        "caption": caption,
        "num_rows": len(grid),
        "num_cols": ncols,
        "header_rows": header_texts,
        "column_labels": column_labels,
        "column_periods": column_periods,
        "unit_scale": unit_scale,
        "unit_label": unit_label,
        "qualifiers": qualifiers,
        "footnote_references": footnote_references,
        "rows": rows_out,
        "footnotes": footnotes,
        "table_text": table_text,
    }
