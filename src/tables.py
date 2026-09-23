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


_FINANCIAL_CHANGE_UNIT_RE = re.compile(
    r"(?P<unit>ppt|pts?|pp|bps?|bp)\s*$",
    re.IGNORECASE,
)


def parse_number_text(
    text: str,
    *,
    numeric_cell_context: bool = False,
) -> dict[str, Any] | None:
    """Parse a table cell into its numeric value and simple numeric flags."""
    t = normalize_text(text)
    if not t:
        return None
    change_match = _FINANCIAL_CHANGE_UNIT_RE.search(t)
    change_unit: str | None = None
    if change_match:
        suffix = change_match.group("unit").lower()
        change_unit = "basis_point" if suffix in {"bp", "bps"} else "percentage_point"
        number_text = t[: change_match.start()].rstrip()
    else:
        number_text = t

    is_percent = "%" in number_text
    cleaned = number_text.replace("$", "").replace("\u00a0", "").replace(" ", "")
    cleaned = cleaned.replace("%", "")
    cleaned = cleaned.replace(",", "")
    negative = False
    if cleaned.startswith("(") and numeric_cell_context:
        negative = True
        cleaned = cleaned[1:]
        if cleaned.endswith(")"):
            cleaned = cleaned[:-1]
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
        "change_unit": change_unit,
    }


def is_numeric_data_cell(text: str) -> bool:
    parsed = parse_number_text(text, numeric_cell_context=True)
    if parsed is None:
        return False
    if parsed.get("change_unit"):
        return True
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


def _column_header_texts_for_rows(
    grid: list[list[Tag | None]],
    rows: list[int],
    col: int,
) -> list[str]:
    """Return de-duplicated header text for one column and header band."""
    texts: list[str] = []
    for row in rows:
        cell = grid[row][col]
        if cell is None:
            continue
        text = _cell_text(cell)
        if text and (not texts or texts[-1] != text):
            texts.append(text)
    return texts


def _row_is_data(
    grid: list[list[Tag | None]],
    row: int,
    ncols: int,
) -> bool:
    """Identify a data row, including rows whose values are small integers."""
    label_found = False
    visited: set[int] = set()
    for col in range(ncols):
        cell = grid[row][col]
        if cell is None or id(cell) in visited:
            continue
        visited.add(id(cell))
        text = _cell_text(cell)
        if not text:
            continue
        parsed = parse_number_text(text, numeric_cell_context=True)
        is_bare_year = bool(re.fullmatch(r"\d{4}", normalize_text(text).strip("()")))
        numeric = parsed is not None and not is_bare_year
        if not label_found and not numeric:
            label_found = True
            continue
        if label_found and numeric:
            return True
    return False


def _row_starts_repeated_header_band(
    grid: list[list[Tag | None]],
    row: int,
    ncols: int,
) -> bool:
    """Detect a period-bearing column-header restart inside a physical table.

    SEC filings sometimes serialize two statements (for example quarterly and
    year-to-date stockholders' equity) as one HTML ``table``.  A period header
    spanning several logical columns is structural evidence that subsequent
    rows belong to a new header band.  Requiring a non-data row and a spanning
    cell avoids treating dated row labels as header restarts.
    """
    if _row_is_data(grid, row, ncols):
        return False

    visited: set[int] = set()
    for col in range(ncols):
        cell = grid[row][col]
        if cell is None or id(cell) in visited:
            continue
        visited.add(id(cell))
        text = _cell_text(cell)
        if not text or _cell_span_width(grid, row, ncols, cell) <= 1:
            continue
        if infer_period([text]) is not None:
            return True
    return False


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

_TRAILING_ROW_FOOTNOTE_RE = re.compile(
    r"^(?P<label>.+?)\s+(?P<marker>\(\d{1,3}\)|\([a-z]\)|\[\d{1,3}\]|\d{1,3}\))\s*$",
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


def _split_row_label_footnote(text: str) -> tuple[str, list[str]]:
    """Separate a trailing structural footnote marker from a semantic row label."""
    match = _TRAILING_ROW_FOOTNOTE_RE.match(text)
    if not match:
        return text, []
    label = normalize_text(match.group("label"))
    marker = normalize_text(match.group("marker"))
    return label, [marker]


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
        c is not None
        and c is not cell
        and parse_number_text(_cell_text(c), numeric_cell_context=True) is not None
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


def _duration_from_dates(start_iso: str, end_iso: str) -> int | None:
    try:
        start = date.fromisoformat(start_iso)
        end = date.fromisoformat(end_iso)
    except (TypeError, ValueError):
        return None
    if end < start:
        return None
    days = (end - start).days + 1
    return max(1, round(days / (365.2425 / 12)))


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
        if (
            duration_months is not None
            and _duration_from_dates(start_iso, end_iso) != duration_months
        ):
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


def _fact_context_signature(fact: dict[str, Any]) -> tuple[Any, ...]:
    dimensions = tuple(
        sorted(
            (dimension.get("axis", ""), dimension.get("member", ""))
            for dimension in fact.get("dimensions", [])
        )
    )
    members = tuple(sorted(fact.get("members", [])))
    unit_measures = tuple(sorted(fact.get("unit_measures", [])))
    return (
        fact.get("period_start"),
        fact.get("period_end"),
        _duration_from_dates(fact.get("period_start"), fact.get("period_end")),
        fact.get("unit"),
        unit_measures,
        fact.get("scale"),
        dimensions,
        members,
        fact.get("concept"),
        fact.get("context_id"),
    )


def check_numeric_cell_xbrl_consistency(
    cell: dict[str, Any],
    fact: dict[str, Any],
) -> dict[str, Any]:
    """Compare the table-display and inline-XBRL paths without erasing sign semantics."""
    cell_value = cell.get("parsed_value")
    fact_value = fact.get("parsed_value")
    magnitude_matches = (
        cell_value is not None
        and fact_value is not None
        and abs(float(cell_value)) == abs(float(fact_value))
    )

    raw_text = str(cell.get("raw_text") or "").strip()
    table_negative_display = raw_text.startswith("(") or raw_text.startswith("-")
    table_display_sign_valid = cell_value is not None and (
        (table_negative_display and float(cell_value) <= 0)
        or (not table_negative_display and float(cell_value) >= 0)
    )
    xbrl_negative = bool(fact.get("is_negative"))
    xbrl_sign_valid = fact_value is not None and (
        (xbrl_negative and float(fact_value) <= 0)
        or (not xbrl_negative and float(fact_value) >= 0)
    )
    display_signs_equal = table_negative_display == xbrl_negative

    cell_period_end = cell.get("period_end")
    fact_period_end = fact.get("period_end") or fact.get("instant_date")
    period_end_matches = bool(cell_period_end and fact_period_end) and (
        cell_period_end == fact_period_end
    )
    fact_duration = _duration_from_dates(
        fact.get("period_start"), fact.get("period_end")
    )
    cell_duration = cell.get("duration_months")
    duration_matches = (
        (cell_duration is None and fact_duration is None)
        or (
            cell_duration is not None
            and fact_duration is not None
            and cell_duration == fact_duration
        )
    )

    unit_label = str(cell.get("unit_label") or "").casefold()
    unit_scale = cell.get("unit_scale")
    fact_scale = fact.get("scale")
    measures = {str(measure).casefold() for measure in fact.get("unit_measures", [])}
    if "million" in unit_label:
        unit_matches = unit_scale == 6 and fact_scale == 6 and any(
            "usd" in measure for measure in measures
        )
    elif unit_scale is not None:
        unit_matches = unit_scale == fact_scale
    else:
        unit_matches = bool(fact.get("unit") or measures)

    identity_present = bool(cell.get("row_label") and fact.get("concept"))
    consistent = all(
        (
            magnitude_matches,
            table_display_sign_valid,
            xbrl_sign_valid,
            period_end_matches,
            duration_matches,
            unit_matches,
            identity_present,
        )
    )
    return {
        "consistent": consistent,
        "magnitude_matches": magnitude_matches,
        "table_display_sign": "negative" if table_negative_display else "nonnegative",
        "xbrl_fact_sign": "negative" if xbrl_negative else "nonnegative",
        "table_display_sign_valid": table_display_sign_valid,
        "xbrl_sign_valid": xbrl_sign_valid,
        "display_signs_equal": display_signs_equal,
        "period_end_matches": period_end_matches,
        "duration_matches": duration_matches,
        "unit_matches": unit_matches,
        "row_label": cell.get("row_label"),
        "concept": fact.get("concept"),
        "identity_present": identity_present,
    }


def _reconcile_period_with_direct_facts(
    period: dict[str, Any] | None,
    facts: list[dict[str, Any]],
    column_label: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Prefer an unambiguous directly attached XBRL period over conflicting headers."""
    temporal_facts = [
        fact
        for fact in facts
        if fact.get("period_start") and fact.get("period_end")
        or fact.get("instant_date")
    ]
    if not temporal_facts:
        return period, None

    def temporal_signature(fact: dict[str, Any]) -> tuple[str | None, str | None, str | None, int | None]:
        if fact.get("instant_date"):
            return None, None, fact["instant_date"], None
        start = fact.get("period_start") or None
        end = fact.get("period_end") or None
        return start, end, None, _duration_from_dates(start, end) if start and end else None

    signatures = {temporal_signature(fact) for fact in temporal_facts}
    if len(signatures) != 1:
        if period is None:
            return period, {
                "status": "direct_xbrl_ambiguous",
                "direct_fact_count": len(temporal_facts),
                "temporal_signature_count": len(signatures),
            }
        return period, {
            "status": "direct_xbrl_ambiguous",
            "direct_fact_count": len(temporal_facts),
            "temporal_signature_count": len(signatures),
        }

    start, end, instant, duration = next(iter(signatures))
    current = period or {}
    if current.get("instant_date"):
        current_signature = (
            None,
            None,
            current.get("instant_date"),
            None,
        )
    else:
        current_signature = (
            current.get("period_start") or None,
            current.get("period_end") or None,
            None,
            current.get("duration_months"),
        )
    if current_signature == (start, end, instant, duration):
        return period, None

    reconciled = dict(current)
    reconciled["period_start"] = start
    reconciled["period_end"] = end or instant
    reconciled["instant_date"] = instant
    reconciled["duration_months"] = duration
    reconciled.setdefault("period_label", column_label)
    reconciled["period_source"] = "xbrl_fact"
    reconciled["period_resolution_source"] = "xbrl_fact"
    context_ids = {fact.get("context_id") for fact in temporal_facts}
    reconciled["period_resolution_context_id"] = (
        next(iter(context_ids)) if len(context_ids) == 1 else None
    )
    return reconciled, {
        "status": "direct_xbrl_overrode_header",
        "header_period_start": current.get("period_start"),
        "header_period_end": current.get("period_end"),
        "header_duration_months": current.get("duration_months"),
        "direct_period_start": start,
        "direct_period_end": end or instant,
        "direct_instant_date": instant,
        "direct_duration_months": duration,
        "direct_fact_count": len(temporal_facts),
        "temporal_signature_count": 1,
    }


def _enrich_period_from_cell_facts(
    period: dict[str, Any] | None,
    facts: list[dict[str, Any]],
    parsed_value: float | int,
    column_label: str,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Fill period fields only from one unambiguous, exact XBRL context."""
    candidates = [
        fact
        for fact in facts
        if fact.get("period_start") and fact.get("period_end")
    ]
    value_matches = [
        fact
        for fact in candidates
        if fact.get("parsed_value") is not None
        and abs(float(fact["parsed_value"])) == abs(float(parsed_value))
    ]
    if not value_matches:
        return period, {
            "status": "no_compatible_fact",
            "matching_fact_count": 0,
            "compatible_context_count": 0,
        }
    candidates = value_matches

    if period and period.get("period_end"):
        candidates = [
            fact
            for fact in candidates
            if fact.get("period_end") == period["period_end"]
        ]
    if period and period.get("period_start"):
        candidates = [
            fact
            for fact in candidates
            if fact.get("period_start") == period["period_start"]
        ]
    if period and period.get("duration_months"):
        candidates = [
            fact
            for fact in candidates
            if _duration_from_dates(fact.get("period_start"), fact.get("period_end"))
            == period["duration_months"]
        ]

    if not candidates:
        return period, {
            "status": "no_compatible_fact",
            "matching_fact_count": len(value_matches),
            "compatible_context_count": 0,
        }

    signatures = {_fact_context_signature(fact) for fact in candidates}
    if len(signatures) != 1:
        return period, {
            "status": "rejected_ambiguous",
            "matching_fact_count": len(value_matches),
            "compatible_context_count": len(signatures),
        }

    fact = candidates[0]
    start_iso = fact["period_start"]
    end_iso = fact["period_end"]
    enriched = dict(period or {})
    changed = False
    if not enriched.get("period_start"):
        enriched["period_start"] = start_iso
        changed = True
    if not enriched.get("period_end"):
        enriched["period_end"] = end_iso
        changed = True
    if not enriched.get("duration_months"):
        enriched["duration_months"] = _duration_from_dates(start_iso, end_iso)
        changed = True
    if changed:
        enriched.setdefault("instant_date", None)
        enriched.setdefault("period_label", column_label)
        enriched.setdefault("period_source", "xbrl_fact")
        enriched["period_resolution_source"] = "xbrl_fact"
        enriched["period_resolution_context_id"] = fact.get("context_id")
    return enriched, {
        "status": "assigned_unique",
        "matching_fact_count": len(value_matches),
        "compatible_context_count": 1,
    }


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

    active_header_rows = [row for row in range(header_rows) if row not in meta_rows]
    active_column_labels = column_labels
    active_column_periods = column_periods
    header_bands: list[dict[str, Any]] = [
        {
            "row_start": active_header_rows[0] if active_header_rows else 0,
            "row_end": active_header_rows[-1] if active_header_rows else -1,
            "column_labels": column_labels,
            "column_periods": column_periods,
        }
    ]

    footnote_references = _extract_footnote_references(grid, ncols, header_rows)

    unit_scale, _detected_label = detect_unit_scale(
        caption, *(c for row in header_texts for c in row)
    )
    if unit_label is None:
        unit_label = _detected_label

    rows_out: list[dict[str, Any]] = []
    footnotes: list[str] = []
    r = header_rows
    while r < len(grid):
        if _row_starts_repeated_header_band(grid, r, ncols):
            band_start = r
            r += 1
            while r < len(grid) and not _row_is_data(grid, r, ncols):
                r += 1
            active_header_rows = list(range(band_start, r))
            active_column_labels = []
            active_column_periods = []
            for col in range(ncols):
                texts = _column_header_texts_for_rows(
                    grid, active_header_rows, col
                )
                active_column_labels.append(" ".join(texts))
                active_column_periods.append(infer_period(texts, contexts))
            header_bands.append(
                {
                    "row_start": band_start,
                    "row_end": r - 1,
                    "column_labels": active_column_labels,
                    "column_periods": active_column_periods,
                }
            )
            continue

        row_cells = grid[r]
        row_label = ""
        row_footnote_references: list[str] = []
        seen: set[int] = set()
        row_facts: list[dict[str, Any]] = []

        # Determine the row label from the left-most non-numeric cell.
        for c in range(ncols):
            cell = row_cells[c]
            if cell is None:
                continue
            text = _cell_text(cell)
            if text and not is_numeric_data_cell(text):
                row_label, row_footnote_references = _split_row_label_footnote(text)
                for marker in row_footnote_references:
                    if marker not in footnote_references:
                        footnote_references.append(marker)
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

            parsed = parse_number_text(raw_text, numeric_cell_context=True)
            facts = _cell_facts(cell, fact_by_id)
            row_facts.extend(facts)

            column_label = (
                active_column_labels[c] if c < len(active_column_labels) else ""
            )
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
            change_unit = parsed.get("change_unit") if parsed else None
            if change_unit:
                percent = False
                cell_unit_scale = None
                cell_unit_label = change_unit
            elif percent:
                cell_unit_scale = None
                cell_unit_label = "percent"

            period = active_column_periods[c] if parsed is not None else None
            period_reconciliation: dict[str, Any] | None = None
            if parsed is not None and facts:
                period, period_reconciliation = _reconcile_period_with_direct_facts(
                    period,
                    facts,
                    column_label,
                )
            period_fallback: dict[str, Any] | None = None
            has_duration_fact = any(
                fact.get("period_start") and fact.get("period_end")
                for fact in facts
            )
            period_incomplete = period is None or any(
                not period.get(field)
                for field in ("period_start", "period_end", "duration_months")
            )
            if parsed is not None and facts and has_duration_fact and period_incomplete:
                period, period_fallback = _enrich_period_from_cell_facts(
                    period,
                    facts,
                    parsed["parsed_value"],
                    column_label,
                )
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
            if change_unit:
                cell_record["change_unit"] = change_unit
            if period_fallback:
                cell_record["period_fallback"] = period_fallback
            if period_reconciliation:
                cell_record["period_reconciliation"] = period_reconciliation
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
            row_record: dict[str, Any] = {
                "row_label": row_label,
                "cells": cells_out,
                "xbrl_facts": row_facts,
            }
            if row_footnote_references:
                row_record["footnote_references"] = row_footnote_references
            rows_out.append(row_record)
        r += 1

    table_text = normalize_text(table.get_text(" ", strip=True))
    return {
        "caption": caption,
        "num_rows": len(grid),
        "num_cols": ncols,
        "header_rows": header_texts,
        "header_bands": header_bands,
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
