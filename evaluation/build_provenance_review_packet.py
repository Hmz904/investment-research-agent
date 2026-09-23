"""Build a human-review packet from the existing v0.1.1 provenance map.

This utility is presentation-only: it reads the frozen provenance artifacts,
does not resolve or alter candidates, and emits blank reviewer fields.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
PROVENANCE_DIR = ROOT / "benchmark" / "provenance"
CHUNK_DIR = ROOT / "data" / "chunks"
REVIEW_DIR = PROVENANCE_DIR / "review"
MARKDOWN_PATH = ROOT / "review" / "provenance_human_review.md"
ALLOWED_DECISIONS = ["APPROVE", "REJECT", "NEEDS_SOURCE_CHECK"]


def _load(name: str) -> dict[str, Any]:
    return json.loads((PROVENANCE_DIR / name).read_text(encoding="utf-8"))


def _load_mapped_chunks() -> dict[str, dict[str, Any]]:
    chunks: dict[str, dict[str, Any]] = {}
    for path in sorted(CHUNK_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for chunk in payload["chunks"]:
            chunks[chunk["chunk_id"]] = chunk
    return chunks


def _full_mapped_source_text(
    source: dict[str, Any], chunks: dict[str, dict[str, Any]]
) -> str:
    chunk = chunks[source["chunk_id"]]
    for field in ("accession", "doc_id", "char_start", "char_end"):
        if chunk.get(field) != source.get(field):
            raise RuntimeError(
                f"mapped source metadata mismatch for {source['chunk_id']}/{field}"
            )
    return chunk.get("retrieval_text") or chunk.get("text") or source["source_excerpt"]


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def _section(source: dict[str, Any]) -> str:
    value = source.get("section_path") or []
    return " > ".join(value) if isinstance(value, list) else str(value)


def _source_metadata(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "doc_id": source.get("doc_id"),
        "chunk_id": source.get("chunk_id"),
        "source_anchor_id": source.get("anchor_id"),
        "char_start": source.get("char_start"),
        "char_end": source.get("char_end"),
        "mapping_method": source.get("mapping_method"),
        "section_path": source.get("section_path"),
        "table_title": source.get("table_title"),
        "row_label": source.get("row_label"),
        "effective_column_label": source.get("effective_column_label"),
        "normalized_source_fingerprint": source.get("normalized_source_fingerprint"),
    }


def _support_reason(requirement: str, source: dict[str, Any], complete: bool = False) -> str:
    context = _section(source) or "the anchored source span"
    identity = source.get("table_identity") or {}
    cells = identity.get("table_cells") or []
    xbrl = identity.get("xbrl_facts") or []
    if cells:
        cell = cells[0]
        basis = (
            f"the exact table cell at row {cell.get('row_label')!r}, column "
            f"{cell.get('effective_column_label')!r}, value {cell.get('raw_text')!r}"
        )
    elif xbrl:
        fact = xbrl[0]
        basis = (
            f"the exact XBRL identity {fact.get('concept')!r}, value "
            f"{fact.get('scaled_value')!r}, period ending "
            f"{fact.get('period_end') or fact.get('instant_date')!r}"
        )
    elif source.get("table_title"):
        basis = (
            f"the anchored table {source.get('table_title')!r}, with row context "
            f"{source.get('row_label')!r} and column context "
            f"{source.get('effective_column_label')!r}"
        )
    else:
        basis = "the quoted disclosure in the anchored span"
    completeness = (
        " It is mapped as an independent complete alternative and does not rely "
        "on another OR candidate."
        if complete
        else ""
    )
    return (
        f"In {context}, {basis} supplies the existing mapped support for: "
        f"{requirement}.{completeness} This is a packet explanation, not reviewer approval."
    )


def _md(value: Any) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", "<br>")


def build() -> dict[str, Any]:
    evidence = _load("evidence_provenance_draft.json")
    numeric = _load("numeric_facts_draft.json")
    chunks = _load_mapped_chunks()
    binding = evidence["version_binding"]

    single_rows: list[dict[str, Any]] = []
    or_rows: list[dict[str, Any]] = []
    evidence_md: list[str] = []
    or_md: list[str] = []

    for item in evidence["items"]:
        for part in item["parts"]:
            requirement = part["description"]
            candidates = part["candidate_sources"]
            if len(candidates) == 1:
                source = candidates[0]
                reason = _support_reason(requirement, source)
                single_rows.append(
                    {
                        "q_id": item["q_id"],
                        "q_version": item["q_version"],
                        "item_id": item["item_id"],
                        "part_id": part["part_id"],
                        "claim": item["claim"],
                        "semantic_requirement": requirement,
                        "accession": source["accession"],
                        "chunk_id": source["chunk_id"],
                        "source_anchor_id": source["anchor_id"],
                        "section_path": _section(source),
                        "relevant_source_text": _full_mapped_source_text(source, chunks),
                        "support_explanation": reason,
                        "reviewer_decision": "",
                        "reviewer_note": "",
                    }
                )
                evidence_md.extend(
                    [
                        f"### {item['q_id']}/{item['item_id']}/{part['part_id']}",
                        "",
                        f"- Claim: {item['claim']}",
                        f"- Semantic requirement: {requirement}",
                        f"- Source: accession `{source['accession']}`, chunk `{source['chunk_id']}`, anchor `{source['anchor_id']}`",
                        f"- Section: `{_section(source)}`",
                        f"- Why mapped: {reason}",
                        "- Reviewer decision: **[blank]**",
                        "- Reviewer note: **[blank]**",
                        "",
                        "> " + _full_mapped_source_text(source, chunks).replace("\n", "\n> "),
                        "",
                    ]
                )
            else:
                candidate_records = []
                for source in candidates:
                    reason = _support_reason(requirement, source, complete=True)
                    candidate_records.append(
                        {
                            "accession": source["accession"],
                            "chunk_id": source["chunk_id"],
                            "source_anchor_id": source["anchor_id"],
                            "section_path": source["section_path"],
                            "relevant_source_text": _full_mapped_source_text(source, chunks),
                            "current_mapping_claims_independent_complete_support": True,
                            "equivalence_explanation": reason,
                        }
                    )
                or_rows.append(
                    {
                        "q_id": item["q_id"],
                        "q_version": item["q_version"],
                        "item_id": item["item_id"],
                        "part_id": part["part_id"],
                        "claim": item["claim"],
                        "semantic_requirement": requirement,
                        "candidate_count": len(candidate_records),
                        "candidates_json": _json(candidate_records),
                        "reviewer_decision": "",
                        "reviewer_note": "",
                    }
                )
                or_md.extend(
                    [
                        f"### {item['q_id']}/{item['item_id']}/{part['part_id']}",
                        "",
                        f"- Claim: {item['claim']}",
                        f"- Complete semantic requirement: {requirement}",
                        "- Reviewer decision: **[blank]**",
                        "- Reviewer note: **[blank]**",
                        "",
                    ]
                )
                for index, candidate in enumerate(candidate_records, start=1):
                    or_md.extend(
                        [
                            f"#### Candidate {index}",
                            "",
                            f"- Source: accession `{candidate['accession']}`, chunk `{candidate['chunk_id']}`, anchor `{candidate['source_anchor_id']}`",
                            f"- Section: `{' > '.join(candidate['section_path'])}`",
                            "- Current mapping assessment: **independently complete; human verification required**",
                            f"- Why equivalent: {candidate['equivalence_explanation']}",
                            "",
                            "> " + candidate["relevant_source_text"].replace("\n", "\n> "),
                            "",
                        ]
                    )

    facts_by_id = {fact["fact_id"]: fact for fact in numeric["facts"]}
    unique_rows: list[dict[str, Any]] = []
    numeric_or_rows: list[dict[str, Any]] = []
    derived_rows: list[dict[str, Any]] = []

    for fact in numeric["facts"]:
        if fact["status"] == "direct_unique":
            source = fact["candidate_sources"][0]
            requirement = f"fact value {fact['value']} {fact['unit']} on basis {fact['basis']}"
            unique_rows.append(
                {
                    "fact_id": fact["fact_id"],
                    "q_id": fact["q_id"] or "",
                    "value": fact["value"],
                    "unit": fact["unit"],
                    "accession": source["accession"],
                    "source_anchor_id": source["anchor_id"],
                    "chunk_id": source["chunk_id"],
                    "source_metadata_json": _json(_source_metadata(source)),
                    "source_text": _full_mapped_source_text(source, chunks),
                    "support_explanation": _support_reason(requirement, source),
                    "reviewer_decision": "",
                    "reviewer_note": "",
                }
            )
        elif fact["status"] == "direct_or":
            alternatives = []
            requirement = f"fact value {fact['value']} {fact['unit']} on basis {fact['basis']}"
            for source in fact["candidate_sources"]:
                alternatives.append(
                    {
                        "accession": source["accession"],
                        "chunk_id": source["chunk_id"],
                        "source_anchor_id": source["anchor_id"],
                        "source_metadata": _source_metadata(source),
                        "source_text": _full_mapped_source_text(source, chunks),
                        "equivalence_explanation": _support_reason(
                            requirement, source, complete=True
                        ),
                        "current_mapping_claims_equivalent_fact_identity": True,
                    }
                )
            numeric_or_rows.append(
                {
                    "fact_id": fact["fact_id"],
                    "q_id": fact["q_id"] or "",
                    "value": fact["value"],
                    "unit": fact["unit"],
                    "basis": fact["basis"],
                    "alternative_count": len(alternatives),
                    "alternatives_json": _json(alternatives),
                    "reviewer_decision": "",
                    "reviewer_note": "",
                }
            )
        elif fact["status"] == "derived":
            input_anchors = {
                input_id: [
                    source["anchor_id"]
                    for source in facts_by_id[input_id]["candidate_sources"]
                ]
                for input_id in fact["input_fact_ids"]
            }
            required_union: list[str] = []
            for input_id in fact["input_fact_ids"]:
                for candidate_id in facts_by_id[input_id]["candidate_chunk_ids"]:
                    if candidate_id not in required_union:
                        required_union.append(candidate_id)
            union_exact = required_union == fact["candidate_chunk_ids"]
            derived_rows.append(
                {
                    "fact_id": fact["fact_id"],
                    "q_id": fact["q_id"] or "",
                    "value": fact["value"],
                    "unit": fact["unit"],
                    "formula": fact["formula"],
                    "input_fact_ids": ";".join(fact["input_fact_ids"]),
                    "input_provenance_anchors_json": _json(input_anchors),
                    "required_input_candidate_union_json": _json(required_union),
                    "derived_candidate_union_json": _json(fact["candidate_chunk_ids"]),
                    "provenance_union_exactly_matches_required_inputs": union_exact,
                    "union_explanation": (
                        "The derived provenance is the ordered, de-duplicated union of "
                        "the listed input facts' candidate chunks."
                        if union_exact
                        else "The derived candidate union differs from its required inputs."
                    ),
                    "reviewer_decision": "",
                    "reviewer_note": "",
                }
            )
        else:
            raise RuntimeError(f"unexpected numeric provenance status: {fact['status']}")

    if (len(single_rows), len(or_rows), len(unique_rows), len(numeric_or_rows), len(derived_rows)) != (
        216, 15, 38, 8, 25
    ):
        raise RuntimeError("review-packet counts do not match the fixed provenance map")
    if not all(row["provenance_union_exactly_matches_required_inputs"] for row in derived_rows):
        raise RuntimeError("derived provenance input union validation failed")

    _write_csv(
        REVIEW_DIR / "evidence_single_candidate_review.csv",
        [
            "q_id", "q_version", "item_id", "part_id", "claim",
            "semantic_requirement", "accession", "chunk_id", "source_anchor_id",
            "section_path", "relevant_source_text", "support_explanation",
            "reviewer_decision", "reviewer_note",
        ],
        single_rows,
    )
    _write_csv(
        REVIEW_DIR / "evidence_or_part_review.csv",
        [
            "q_id", "q_version", "item_id", "part_id", "claim",
            "semantic_requirement", "candidate_count", "candidates_json",
            "reviewer_decision", "reviewer_note",
        ],
        or_rows,
    )
    _write_csv(
        REVIEW_DIR / "numeric_unique_fact_review.csv",
        [
            "fact_id", "q_id", "value", "unit", "accession", "source_anchor_id",
            "chunk_id", "source_metadata_json", "source_text", "support_explanation",
            "reviewer_decision", "reviewer_note",
        ],
        unique_rows,
    )
    _write_csv(
        REVIEW_DIR / "numeric_or_fact_review.csv",
        [
            "fact_id", "q_id", "value", "unit", "basis", "alternative_count",
            "alternatives_json", "reviewer_decision", "reviewer_note",
        ],
        numeric_or_rows,
    )
    _write_csv(
        REVIEW_DIR / "numeric_derived_fact_review.csv",
        [
            "fact_id", "q_id", "value", "unit", "formula", "input_fact_ids",
            "input_provenance_anchors_json", "required_input_candidate_union_json",
            "derived_candidate_union_json",
            "provenance_union_exactly_matches_required_inputs", "union_explanation",
            "reviewer_decision", "reviewer_note",
        ],
        derived_rows,
    )

    counts = {
        "single_candidate_evidence_parts": len(single_rows),
        "or_evidence_parts": len(or_rows),
        "unique_numeric_facts": len(unique_rows),
        "or_numeric_facts": len(numeric_or_rows),
        "derived_numeric_facts": len(derived_rows),
        "total_review_decisions_required": len(single_rows) + len(or_rows) + len(unique_rows) + len(numeric_or_rows) + len(derived_rows),
    }
    manifest = {
        "artifact_type": "provenance_human_review_packet",
        "version_binding": binding,
        "fixed_context": {
            "bench_v0.1.1_source_errata": "approved; excluded from this review",
            "retrieval_level_merge_groups": "55 approved; excluded from this review",
        },
        "allowed_reviewer_decisions": ALLOWED_DECISIONS,
        "blank_review_fields_required": True,
        "decision_unit": "one decision per evidence part or numeric fact",
        "counts": counts,
        "sheets": [
            "evidence_single_candidate_review.csv",
            "evidence_or_part_review.csv",
            "numeric_unique_fact_review.csv",
            "numeric_or_fact_review.csv",
            "numeric_derived_fact_review.csv",
        ],
    }
    (REVIEW_DIR / "review_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    numeric_md = [
        "## Numeric fact review",
        "",
        "### Unique direct facts (38)",
        "",
        "| Fact | Value | Accession / anchor / metadata | Source text and support basis | Decision | Note |",
        "|---|---:|---|---|---|---|",
    ]
    for row in unique_rows:
        numeric_md.append(
            f"| {_md(row['fact_id'])} | {_md(row['value'] + ' ' + row['unit'])} | "
            f"`{_md(row['accession'])}` / `{_md(row['source_anchor_id'])}`<br>{_md(row['source_metadata_json'])} | "
            f"{_md(row['source_text'])}<br><br>Why: {_md(row['support_explanation'])} |  |  |"
        )
    numeric_md.extend(
        [
            "",
            "### OR-mapped direct facts (8)",
            "",
            "Each candidate below is an independently complete equivalent in the current mapping; this statement is presented for human verification and is not approval.",
            "",
        ]
    )
    for row in numeric_or_rows:
        numeric_md.extend(
            [
                f"#### {row['fact_id']} — {row['value']} {row['unit']}",
                "",
                "| Candidate | Source text | Why equivalent |",
                "|---|---|---|",
            ]
        )
        for candidate in json.loads(row["alternatives_json"]):
            numeric_md.append(
                f"| `{candidate['accession']}` / `{candidate['chunk_id']}` / `{candidate['source_anchor_id']}` | "
                f"{_md(candidate['source_text'])} | {_md(candidate['equivalence_explanation'])} |"
            )
        numeric_md.extend(["", "Reviewer decision: **[blank]**  ", "Reviewer note: **[blank]**", ""])
    numeric_md.extend(
        [
            "### Derived facts (25)",
            "",
            "| Fact | Value | Formula | Input facts | Input provenance anchors | Exact input union | Decision | Note |",
            "|---|---:|---|---|---|---|---|---|",
        ]
    )
    for row in derived_rows:
        numeric_md.append(
            f"| {row['fact_id']} | {_md(row['value'] + ' ' + row['unit'])} | `{_md(row['formula'])}` | "
            f"`{_md(row['input_fact_ids'])}` | {_md(row['input_provenance_anchors_json'])} | "
            f"{'yes' if row['provenance_union_exactly_matches_required_inputs'] else 'no'} — {_md(row['union_explanation'])} |  |  |"
        )

    markdown = [
        "# Provenance human review packet",
        "",
        "This packet presents the existing `bench_v0.1.1` gold-provenance mapping for final human review. It does not alter mappings or generate candidates. The source errata and all 55 retrieval-level merge groups are already approved and are not review questions here.",
        "",
        "Allowed decisions: `APPROVE`, `REJECT`, `NEEDS_SOURCE_CHECK`. Every decision and note field is intentionally blank.",
        "",
        "## Counts",
        "",
        *[f"- {key.replace('_', ' ').capitalize()}: **{value}**" for key, value in counts.items()],
        "",
        "## Evidence single-candidate review (216 parts)",
        "",
        *evidence_md,
        "## Evidence OR-part review (15 parts)",
        "",
        *or_md,
        *numeric_md,
        "",
    ]
    MARKDOWN_PATH.write_text("\n".join(markdown), encoding="utf-8")
    return manifest


def main() -> int:
    manifest = build()
    counts = manifest["counts"]
    print(
        "human review packet complete: "
        f"{counts['single_candidate_evidence_parts']} single evidence, "
        f"{counts['or_evidence_parts']} OR evidence, "
        f"{counts['unique_numeric_facts']} unique numeric, "
        f"{counts['or_numeric_facts']} OR numeric, "
        f"{counts['derived_numeric_facts']} derived numeric"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
