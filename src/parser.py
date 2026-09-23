"""HTML-to-block parsing for SEC documents."""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup, NavigableString, Tag

from .tables import extract_table, normalize_text


SKIP_TAGS = {
    "script",
    "style",
    "noscript",
    "title",
    "head",
    "link",
    "meta",
    "ix:hidden",
    "ix:references",
    "ix:resources",
}

BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li"}
CONTAINER_TAGS = {"body", "html", "div", "section", "article", "main", "blockquote"}
INLINE_TAGS = {
    "span",
    "a",
    "b",
    "strong",
    "i",
    "em",
    "sub",
    "sup",
    "br",
    "font",
    "small",
    "u",
    "s",
    "big",
    "code",
    "tt",
    "wbr",
    "ix:nonfraction",
    "ix:nonnumeric",
}


class SectionTracker:
    def __init__(self) -> None:
        self.part: str | None = None
        self.item: str | None = None
        self.section: str | None = None
        self.note: str | None = None

    def path(self) -> list[str]:
        parts: list[str] = []
        for value in (self.part, self.item, self.section, self.note):
            if value:
                parts.append(value)
        return parts

    def apply(self, updates: dict[str, str]) -> list[str]:
        if "part" in updates:
            self.part = updates["part"]
            self.item = None
            self.section = None
            self.note = None
        if "item" in updates:
            self.item = updates["item"]
            self.section = None
            self.note = None
        if "note" in updates:
            self.note = updates["note"]
            self.section = None
        if "section" in updates:
            self.section = updates["section"]
            self.note = None
        return self.path()


_PART_RE = re.compile(r"^PART\s*([IVX]+)", re.IGNORECASE)
_ITEM_RE = re.compile(r"^ITEM\s*(\d+\s*[A-Z]?(?:\s*,\s*\d+\s*[A-Z]?)*)", re.IGNORECASE)
_NOTE_RE = re.compile(r"^NOTE\s*(\d+)", re.IGNORECASE)


def _compact(text: str) -> str:
    text = (
        text.replace("\u2019", "'")
        .replace("\u2018", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
    )
    return re.sub(r"[\s\u00a0]+", "", text).lower()


def classify_heading(text: str) -> dict[str, str]:
    """Return part/item/note/section updates for a heading-like string."""
    raw = normalize_text(text)
    compact = _compact(raw)
    updates: dict[str, str] = {}

    part_match = _PART_RE.search(raw)
    if part_match:
        updates["part"] = f"Part {part_match.group(1).upper()}"

    item_match = _ITEM_RE.search(raw)
    if item_match:
        updates["item"] = f"Item {item_match.group(1).strip().upper()}"

    note_match = _NOTE_RE.search(raw)
    if note_match:
        updates["note"] = f"Note {note_match.group(1)}"

    # Section keywords only identify real headings when the text is short and
    # looks like a title.  Prose paragraphs routinely mention "Risk Factors"
    # or "Financial Statements"; those must not reset the section tracker.
    looks_like_title = (
        len(raw) <= 140
        and not raw.endswith(".")
        and bool(raw)
        and raw[0].isupper()
    )
    if looks_like_title:
        if "riskfactors" in compact:
            updates["section"] = "Risk Factors"
        elif "management'sdiscussionandanalysisoffinancialconditionandresultsofoperations" in compact:
            updates["section"] = "Management's Discussion and Analysis"
        elif "condensedconsolidated" in compact or "financialstatements" in compact:
            updates["section"] = "Financial Statements"

    return updates


def _is_bold_short(element: Tag, text: str) -> bool:
    style = (element.get("style") or "").lower()
    if "font-weight:700" in style or "font-weight:800" in style or "font-weight:bold" in style:
        return len(text) <= 140
    return False


def _element_facts(
    element: Tag, fact_by_id: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for fact in element.find_all(("ix:nonfraction", "ix:nonnumeric")):
        if fact.find(("ix:nonfraction", "ix:nonnumeric")) is not None:
            continue
        fid = fact.get("id", "")
        record = fact_by_id.get(fid)
        if record is not None:
            facts.append(record)
    return facts


def _skip(name: str | None) -> bool:
    if name is None:
        return False
    if name in SKIP_TAGS:
        return True
    if name.startswith(("xbrli", "xbrldi", "ixt", "link", "meta")):
        return True
    # ``ix:continuation`` wraps visible narrative content and must be
    # traversed.  ``ix:nonnumeric`` and ``ix:nonfraction`` are handled in
    # ``walk`` because text-block facts sometimes contain whole tables.
    if name.startswith("ix:") and name not in {
        "ix:continuation",
        "ix:nonnumeric",
        "ix:nonfraction",
    }:
        return True
    return False


def _has_non_inline_element(element: Tag) -> bool:
    for descendant in element.find_all(True):
        if descendant is element:
            continue
        if descendant.name in INLINE_TAGS:
            continue
        return True
    return False


def extract_blocks(
    soup: BeautifulSoup,
    doc_id: str,
    accession: str,
    source_role: str,
    fact_by_id: dict[str, dict[str, Any]],
    contexts: list[dict[str, Any]],
    root_section: str | None = None,
) -> list[dict[str, Any]]:
    tracker = SectionTracker()
    blocks: list[dict[str, Any]] = []

    def emit_text(element: Tag | NavigableString, text: str) -> None:
        text = normalize_text(text)
        if not text:
            return
        block_type = "paragraph"
        heading_updates: dict[str, str] | None = None
        if isinstance(element, Tag):
            heading_updates = classify_heading(text)
            if not heading_updates and _is_bold_short(element, text):
                heading_updates = {"section": text}
            if heading_updates:
                block_type = "heading"
        else:
            heading_updates = classify_heading(text)
            if heading_updates:
                block_type = "heading"

        if heading_updates:
            section_path = tracker.apply(heading_updates)
        else:
            section_path = tracker.path()

        facts: list[dict[str, Any]] = []
        if isinstance(element, Tag):
            facts = _element_facts(element, fact_by_id)

        blocks.append(
            {
                "doc_id": doc_id,
                "accession": accession,
                "source_role": source_role,
                "block_type": block_type,
                "section_path": section_path,
                "text": text,
                "xbrl_facts": facts,
            }
        )

    def emit_table(element: Tag) -> None:
        table = extract_table(element, fact_by_id, contexts)
        facts: list[dict[str, Any]] = []
        for row in table["rows"]:
            facts.extend(row.get("xbrl_facts", []))
        blocks.append(
            {
                "doc_id": doc_id,
                "accession": accession,
                "source_role": source_role,
                "block_type": "table",
                "section_path": tracker.path(),
                "text": table["table_text"],
                "table": table,
                "xbrl_facts": facts,
            }
        )

    def walk(element: Any) -> None:
        if isinstance(element, NavigableString):
            text = normalize_text(str(element))
            if text:
                emit_text(element, text)
            return
        if not isinstance(element, Tag):
            return
        name = element.name
        if _skip(name):
            return
        if name == "table":
            emit_table(element)
            return
        if name in ("ix:nonnumeric", "ix:nonfraction"):
            if element.find(["table", "div", "p", "ul", "ol", "section", "article"]) is not None:
                for child in element.children:
                    if isinstance(child, Tag) or (
                        isinstance(child, NavigableString) and str(child).strip()
                    ):
                        walk(child)
            else:
                emit_text(element, element.get_text(" ", strip=True))
            return
        if name in BLOCK_TAGS:
            emit_text(element, element.get_text(" ", strip=True))
            return
        if name == "div":
            if not _has_non_inline_element(element):
                emit_text(element, element.get_text(" ", strip=True))
                return
        elif name not in CONTAINER_TAGS:
            # Inline element with no further structural children: emit directly
            # when it is not already owned by a text block.
            if not _has_non_inline_element(element):
                emit_text(element, element.get_text(" ", strip=True))
                return

        for child in element.children:
            if isinstance(child, Tag) or (
                isinstance(child, NavigableString) and str(child).strip()
            ):
                walk(child)

    root = soup.body if soup.body is not None else soup
    walk(root)

    # Assign deterministic document positions and character offsets.
    offset = 0
    for position, block in enumerate(blocks):
        block["position"] = position
        block["char_start"] = offset
        block["char_end"] = offset + len(block["text"])
        offset = block["char_end"] + 1

    _fix_running_headers(blocks)
    if root_section:
        for block in blocks:
            if block["section_path"][:1] != [root_section]:
                block["section_path"] = [root_section] + block["section_path"]
    _attach_table_footnotes(blocks)
    return blocks


_BARE_PART_RE = re.compile(r"^PART\s+[IVX]+\.?$", re.IGNORECASE)
_BARE_ITEM_RE = re.compile(r"^ITEM\s+\d+\s*[A-Z]?(?:\s*,\s*\d+\s*[A-Z]?)*\.?$", re.IGNORECASE)


def _is_bare_heading_text(text: str) -> bool:
    text = normalize_text(text)
    return bool(_BARE_PART_RE.match(text) or _BARE_ITEM_RE.match(text))


def _is_notes_container_heading(text: str) -> bool:
    compact = _compact(text)
    return (
        "notestocondensedconsolidatedfinancialstatements" in compact
        or "notestoconsolidatedfinancialstatements" in compact
    )


def _is_running_header(blocks: list[dict[str, Any]], index: int) -> bool:
    """True when a bare PART/Item heading is only a repeating page header."""
    block = blocks[index]
    if block["block_type"] != "heading" or not _is_bare_heading_text(block["text"]):
        return False
    for look_index in range(index + 1, min(index + 4, len(blocks))):
        nxt = blocks[look_index]
        if not nxt["text"]:
            continue
        if nxt["block_type"] == "heading":
            if _is_bare_heading_text(nxt["text"]):
                continue
            # A real section title follows, so this is a genuine heading chain.
            return False
        # Reached ordinary content without a section title: this is a running
        # page header and should not change the active section.
        return True
    return False


def _fix_running_headers(blocks: list[dict[str, Any]]) -> None:
    """Rebuild section paths, ignoring repeated bare PART/Item page headers."""
    tracker = SectionTracker()
    for index, block in enumerate(blocks):
        if block["block_type"] == "heading":
            updates = classify_heading(block["text"])
            if _is_running_header(blocks, index):
                block["section_path"] = tracker.path()
                continue
            if _is_notes_container_heading(block["text"]) and tracker.note is not None:
                block["section_path"] = tracker.path()
                continue
            block["section_path"] = tracker.apply(updates)
        else:
            block["section_path"] = tracker.path()


_LEADING_FOOTNOTE_MARKER_RE = re.compile(
    r"^\s*(\(\d{1,3}\)|\([a-z]\)|\[\d{1,3}\]|\d{1,3}\))\s+"
)


def _attach_table_footnotes(blocks: list[dict[str, Any]]) -> None:
    """Attach immediately-following footnote-body paragraphs to a table."""
    for i, block in enumerate(blocks):
        if block["block_type"] != "table":
            continue
        refs = set(block.get("table", {}).get("footnote_references", []))
        if not refs:
            continue

        bodies: list[str] = []
        j = i + 1
        while j < len(blocks):
            nxt = blocks[j]
            if nxt["block_type"] in ("table", "heading"):
                break
            if nxt["section_path"] != block["section_path"]:
                break
            text = (nxt.get("text") or "").strip()
            match = _LEADING_FOOTNOTE_MARKER_RE.match(text)
            if not match or match.group(1) not in refs:
                break
            bodies.append(text)
            nxt["block_type"] = "footnote"
            j += 1

        if bodies:
            block["table"]["footnotes"] = block["table"].get("footnotes", []) + bodies
