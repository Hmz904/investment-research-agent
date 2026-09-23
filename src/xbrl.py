"""Inline-XBRL metadata extraction from SEC HTML documents."""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup, Tag


FACT_TAGS = ("ix:nonfraction", "ix:nonnumeric")


def _text(el: Tag | None) -> str:
    if el is None:
        return ""
    return " ".join(el.get_text(" ", strip=True).split())


def parse_contexts(soup: BeautifulSoup) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    for ctx in soup.find_all("xbrli:context"):
        cid = ctx.get("id", "")
        entity_identifier = ""
        scheme = ""
        identifier_el = ctx.find("xbrli:identifier")
        if identifier_el is not None:
            entity_identifier = _text(identifier_el)
            scheme = identifier_el.get("scheme", "")

        period_start = ""
        period_end = ""
        instant_date = ""
        period_el = ctx.find("xbrli:period")
        if period_el is not None:
            start_el = period_el.find("xbrli:startdate")
            end_el = period_el.find("xbrli:enddate")
            instant_el = period_el.find("xbrli:instant")
            if start_el is not None:
                period_start = _text(start_el)
            if end_el is not None:
                period_end = _text(end_el)
            if instant_el is not None:
                instant_date = _text(instant_el)

        dimensions: list[dict[str, str]] = []
        members: list[str] = []
        for segment in ctx.find_all("xbrli:segment"):
            for member in segment.find_all("xbrldi:explicitmember"):
                dim = {
                    "axis": member.get("dimension", ""),
                    "member": _text(member),
                }
                dimensions.append(dim)
                if dim["member"]:
                    members.append(dim["member"])
            for typed in segment.find_all("xbrldi:typedmember"):
                dimension = typed.get("dimension", "")
                value_el = typed.find()
                value = _text(value_el) if value_el is not None else ""
                dimensions.append({"axis": dimension, "member": value})
                if value:
                    members.append(value)

        contexts.append(
            {
                "id": cid,
                "entity_identifier": entity_identifier,
                "scheme": scheme,
                "period_start": period_start,
                "period_end": period_end,
                "instant_date": instant_date,
                "dimensions": dimensions,
                "members": members,
            }
        )
    return contexts


def parse_units(soup: BeautifulSoup) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for unit in soup.find_all("xbrli:unit"):
        uid = unit.get("id", "")
        measures = [_text(m) for m in unit.find_all("xbrli:measure", recursive=False)]
        divide_el = unit.find("xbrli:divide")
        numerator: list[str] = []
        denominator: list[str] = []
        if divide_el is not None:
            num_el = divide_el.find("xbrli:unitnumerator")
            den_el = divide_el.find("xbrli:unitdenominator")
            if num_el is not None:
                numerator = [_text(m) for m in num_el.find_all("xbrli:measure")]
            if den_el is not None:
                denominator = [_text(m) for m in den_el.find_all("xbrli:measure")]
        units.append(
            {
                "id": uid,
                "measures": measures,
                "numerator": numerator,
                "denominator": denominator,
            }
        )
    return units


def _parse_fact_number(text: str, sign: str | None) -> tuple[float | int | None, bool]:
    """Parse a visible XBRL fact number into a display-space numeric value.

    Accounting parentheses are interpreted as negatives.  The returned value
    intentionally does NOT apply the XBRL ``scale`` exponent; ``scale`` is kept
    separately so callers can reconstruct the full value when needed.
    """
    if text is None:
        return None, False
    cleaned = text.replace("\u00a0", " ").strip()
    is_negative = sign == "-" or (cleaned.startswith("(") and cleaned.endswith(")"))
    cleaned = cleaned.replace(",", "").replace(" ", "")
    cleaned = cleaned.strip("()")
    if cleaned.startswith("-"):
        is_negative = True
        cleaned = cleaned[1:]
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]
    if not re.fullmatch(r"\d+(?:\.\d+)?", cleaned):
        return None, is_negative
    value: float | int
    if "." in cleaned:
        value = float(cleaned)
    else:
        value = int(cleaned)
    if is_negative:
        value = -value
    return value, is_negative


def parse_facts(
    soup: BeautifulSoup,
    contexts: list[dict[str, Any]],
    units: list[dict[str, Any]],
    doc_id: str,
    accession: str,
    source_role: str,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    context_by_id = {c["id"]: c for c in contexts}
    unit_by_id = {u["id"]: u for u in units}

    facts: list[dict[str, Any]] = []
    fact_by_id: dict[str, dict[str, Any]] = {}

    for fact in soup.find_all(FACT_TAGS):
        # Nested facts (for example numeric facts inside a text-block fact)
        # are not themselves standalone facts.  Keep only the innermost ones.
        if fact.find(FACT_TAGS) is not None:
            continue

        fact_id = fact.get("id", "")
        concept = fact.get("name", "")
        context_id = fact.get("contextref", "")
        unit_ref = fact.get("unitref", "")
        scale_attr = fact.get("scale")
        decimals = fact.get("decimals", "")
        sign = fact.get("sign")
        raw_text = _text(fact)

        ctx = context_by_id.get(context_id, {})
        unit = unit_by_id.get(unit_ref, {})
        parsed_value, is_negative = _parse_fact_number(raw_text, sign)

        try:
            scale = int(scale_attr) if scale_attr is not None else 0
        except (TypeError, ValueError):
            scale = 0

        scaled_value = None
        if parsed_value is not None:
            scaled_value = float(parsed_value) * (10.0**scale)

        fact_record: dict[str, Any] = {
            "doc_id": doc_id,
            "accession": accession,
            "source_role": source_role,
            "fact_id": fact_id,
            "concept": concept,
            "context_id": context_id,
            "period_start": ctx.get("period_start", ""),
            "period_end": ctx.get("period_end", ""),
            "instant_date": ctx.get("instant_date", ""),
            "dimensions": ctx.get("dimensions", []),
            "members": ctx.get("members", []),
            "unit": unit_ref,
            "unit_measures": unit.get("measures", []),
            "decimals": decimals,
            "scale": scale,
            "sign": sign,
            "raw_visible_text": raw_text,
            "parsed_value": parsed_value,
            "scaled_value": scaled_value,
            "is_negative": is_negative,
        }
        facts.append(fact_record)
        if fact_id:
            fact_by_id[fact_id] = fact_record

    return facts, fact_by_id


def parse_inline_xbrl(
    soup: BeautifulSoup,
    doc_id: str,
    accession: str,
    source_role: str,
) -> dict[str, Any]:
    contexts = parse_contexts(soup)
    units = parse_units(soup)
    facts, fact_by_id = parse_facts(
        soup, contexts, units, doc_id, accession, source_role
    )
    return {
        "contexts": contexts,
        "units": units,
        "facts": facts,
        "fact_by_id": fact_by_id,
    }

