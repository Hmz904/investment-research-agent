"""Deterministic block-to-chunk conversion."""

from __future__ import annotations

import hashlib
from typing import Any

from .tables import build_retrieval_text


TARGET_MIN_TOKENS = 400
TARGET_MAX_TOKENS = 800
TABLE_ROW_GROUP = 40


def _tokens(text: str) -> int:
    return len(text.split())


def _chunk_id(doc_id: str, position: int, char_start: int, char_end: int, suffix: str = "") -> str:
    raw = f"{doc_id}:{position}:{char_start}:{char_end}:{suffix}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _make_chunk(
    doc_id: str,
    accession: str,
    source_role: str,
    section_path: list[str],
    block_type: str,
    text: str,
    char_start: int,
    char_end: int,
    position: int,
    suffix: str = "",
    table_json: dict[str, Any] | None = None,
    period_columns: list[dict[str, Any]] | None = None,
    unit_scale: int | None = None,
    xbrl_facts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "chunk_id": _chunk_id(doc_id, position, char_start, char_end, suffix),
        "doc_id": doc_id,
        "accession": accession,
        "source_role": source_role,
        "section_path": section_path,
        "block_type": block_type,
        "text": text,
        "table_json": table_json,
        "period_columns": period_columns or [],
        "unit_scale": unit_scale,
        "xbrl_facts": xbrl_facts or [],
        "char_start": char_start,
        "char_end": char_end,
        "prev_chunk_id": None,
        "next_chunk_id": None,
        "token_count": _tokens(text),
    }


def _table_period_columns(table: dict[str, Any]) -> list[dict[str, Any]]:
    labels = table.get("column_labels", [])
    periods = table.get("column_periods", [])
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for idx, period in enumerate(periods):
        if not period:
            continue
        label = labels[idx] if idx < len(labels) else ""
        key = (
            period.get("period_start", ""),
            period.get("period_end", ""),
            label,
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "column_label": label,
                "period_start": period.get("period_start"),
                "period_end": period.get("period_end"),
                "instant_date": period.get("instant_date"),
                "period_label": period.get("period_label"),
                "period_source": period.get("period_source"),
                "duration_months": period.get("duration_months"),
                "period_resolution_source": period.get("period_resolution_source"),
            }
        )
    return out


def _table_chunks(
    doc_id: str,
    accession: str,
    source_role: str,
    block: dict[str, Any],
) -> list[dict[str, Any]]:
    table = block["table"]
    rows = table.get("rows", [])
    base_char = block["char_start"]
    retrieval_text = build_retrieval_text(table)
    if len(rows) <= TABLE_ROW_GROUP:
        chunk = _make_chunk(
            doc_id=doc_id,
            accession=accession,
            source_role=source_role,
            section_path=block["section_path"],
            block_type="table",
            text=block["text"],
            char_start=block["char_start"],
            char_end=block["char_end"],
            position=block["position"],
            table_json=table,
            period_columns=_table_period_columns(table),
            unit_scale=table.get("unit_scale"),
            xbrl_facts=block.get("xbrl_facts", []),
        )
        chunk["retrieval_text"] = retrieval_text
        return [chunk]

    chunks: list[dict[str, Any]] = []
    offset = base_char
    for group_index in range(0, len(rows), TABLE_ROW_GROUP):
        group_rows = rows[group_index : group_index + TABLE_ROW_GROUP]
        group_table = dict(table)
        group_table["rows"] = group_rows
        group_table["repeated_headers"] = True
        group_text = "\n".join(
            " | ".join(
                cell.get("raw_text", "")
                for cell in row.get("cells", [])
            )
            for row in group_rows
        )
        char_start = offset
        char_end = offset + len(group_text)
        offset = char_end + 1
        facts: list[dict[str, Any]] = []
        for row in group_rows:
            facts.extend(row.get("xbrl_facts", []))
        chunk = _make_chunk(
            doc_id=doc_id,
            accession=accession,
            source_role=source_role,
            section_path=block["section_path"],
            block_type="table",
            text=group_text,
            char_start=char_start,
            char_end=char_end,
            position=block["position"],
            suffix=str(group_index),
            table_json=group_table,
            period_columns=_table_period_columns(table),
            unit_scale=table.get("unit_scale"),
            xbrl_facts=facts,
        )
        chunk["retrieval_text"] = build_retrieval_text(group_table)
        chunks.append(chunk)
    return chunks


def chunk_blocks(
    doc_id: str,
    accession: str,
    source_role: str,
    blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []

    # Text chunks first.
    current: list[dict[str, Any]] = []

    def flush_text() -> None:
        if not current:
            return
        text = "\n\n".join(b["text"] for b in current)
        facts: list[dict[str, Any]] = []
        for b in current:
            facts.extend(b.get("xbrl_facts", []))
        block_type = current[0]["block_type"] if len(current) == 1 else "text"
        chunks.append(
            _make_chunk(
                doc_id=doc_id,
                accession=accession,
                source_role=source_role,
                section_path=current[0]["section_path"],
                block_type=block_type,
                text=text,
                char_start=current[0]["char_start"],
                char_end=current[-1]["char_end"],
                position=current[0]["position"],
                xbrl_facts=facts,
            )
        )
        current.clear()

    for block in blocks:
        if block["block_type"] == "table":
            flush_text()
            chunks.extend(_table_chunks(doc_id, accession, source_role, block))
            continue
        if block["block_type"] == "heading" and current:
            flush_text()

        if current and current[0]["section_path"] != block["section_path"]:
            flush_text()

        candidate_tokens = _tokens("\n\n".join(b["text"] for b in current + [block]))
        if current and candidate_tokens > TARGET_MAX_TOKENS and _tokens(
            "\n\n".join(b["text"] for b in current)
        ) >= TARGET_MIN_TOKENS:
            flush_text()

        current.append(block)

    flush_text()

    # Link chunks in order.
    for idx, chunk in enumerate(chunks):
        if idx > 0:
            chunk["prev_chunk_id"] = chunks[idx - 1]["chunk_id"]
        if idx + 1 < len(chunks):
            chunk["next_chunk_id"] = chunks[idx + 1]["chunk_id"]

    return chunks
