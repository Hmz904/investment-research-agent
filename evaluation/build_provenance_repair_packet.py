"""Build the compact packet for the 12 rejected provenance mappings only."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
PROVENANCE_DIR = ROOT / "benchmark" / "provenance"
REVIEW_DIR = PROVENANCE_DIR / "review"
CHUNK_DIR = ROOT / "data" / "chunks"
CSV_PATH = REVIEW_DIR / "provenance_repair_review.csv"
MARKDOWN_PATH = ROOT / "review" / "provenance_repair_review.md"
ORIGINAL_REVIEW_FILES = (
    "evidence_or_reviewed.csv",
    "evidence_single_reviewed.csv",
    "numeric_derived_reviewed.csv",
    "numeric_or_reviewed.csv",
    "numeric_unique_reviewed.csv",
)

REPAIR_KEYS = {
    ("Q02", "2", "E01", "P01"),
    ("Q04", "2", "E03", "P01"),
    ("Q04", "2", "E03", "P02"),
    ("Q05", "2", "C1", "P01"),
    ("Q05", "2", "X3", "P02"),
    ("Q05", "2", "X4", "P01"),
    ("Q07", "2", "E04", "P01"),
    ("Q07", "2", "E07", "P02"),
    ("Q09", "2", "E06", "P01"),
    ("Q10", "2", "P2", "P02"),
    ("Q12", "2", "E01", "P01"),
    ("Q14", "2", "C1", "P01"),
}

PROPOSED_PARTS = {
    ("Q07", "2", "E04", "P01"): ["P01", "P02"],
    ("Q12", "2", "E01", "P01"): ["P01", "P02"],
    ("Q14", "2", "C1", "P01"): ["P01", "P02"],
}

SOURCE_NEEDLES = {
    "68c69be5eec33035": "foreign exchange rate risk",
    "243d1503e2597719": "foreign exchange rate risk",
    "c2dd3127ada7a30d": "Data Center revenue was",
    "79ddd90f5c73467d": "Row: Data Center",
    "3e9b386d72ec488d": "Data Center revenue was",
    "6e776edb42ae8862": "Row: Data Center",
    "66a2dbe9fa036e7f": "Row: Hyperscale",
    "fc8eed03351b9373": "reported revenue for the second quarter",
    "e19520eac6dfcec3": "Row: Revenue",
    "e11153b1bfb5ab46": "Concentration of Revenue",
    "d9d340e3f0b87b61": "Concentration of Revenue",
    "cd43ad63db9cabc4": "commercial remaining performance obligation",
    "f0db369c68121f7b": "Revenue allocated to remaining performance obligations",
    "93cacd7d82b5cdf0": "CASH FLOWS STATEMENTS",
    "2d9496c49d2f3337": "Row: Revenue",
    "3b71f81f22a8aa92": "Our cloud and AI strategy",
    "3601d950af0768d8": "Other digital safety abuses",
    "6eab04595fe303b6": "Ad impressions",
    "eb7ce4994d2626b3": "Row: GAAP advertising revenue",
    "130fcc4fc2110081": "Ad impressions",
    "874f02d4f152c4a1": "Row: GAAP advertising revenue",
}

SOURCE_RADII = {
    "e11153b1bfb5ab46": 2600,
    "d9d340e3f0b87b61": 2600,
    "3601d950af0768d8": 1700,
}

MERGE_LINEAGE = {
    ("Q02", "2", "E01", "P01"): (
        "B -> C: the approved three-atom merge remains, but its OR set changed "
        "from two candidates to the precision-safe table only; re-review pending."
    ),
    ("Q05", "2", "C1", "P01"): (
        "B -> C: the approved three-atom merge remains, but its OR set changed "
        "from two candidates to the precision-safe table only; re-review pending."
    ),
    ("Q07", "2", "E04", "P01"): (
        "B removed: the former P01/P02 merge is restored to two required AND "
        "parts because the candidates do not support the same atoms."
    ),
    ("Q12", "2", "E01", "P01"): (
        "B -> two C groups: former five-atom merge becomes P01=(atoms P01-P03) "
        "AND P02=(atoms P04-P05); re-review pending."
    ),
    ("Q14", "2", "C1", "P01"): (
        "B -> two C groups: former four-atom merge becomes P01=(atoms P01-P02) "
        "AND P02=(atoms P03-P04); re-review pending."
    ),
}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _key(row: dict[str, str]) -> tuple[str, str, str, str]:
    return row["q_id"], row["q_version"], row["item_id"], row["part_id"]


def _chunks() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(CHUNK_DIR.glob("*.json")):
        for chunk in _load_json(path)["chunks"]:
            result[chunk["chunk_id"]] = chunk
    return result


def _source_text(chunk: dict[str, Any]) -> str:
    return chunk.get("retrieval_text") or chunk.get("text") or ""


def _excerpt(chunk_id: str, text: str, radius: int = 900) -> str:
    """Keep the packet compact while retaining the operative source passage."""
    needle = SOURCE_NEEDLES.get(chunk_id, "")
    index = text.casefold().find(needle.casefold()) if needle else -1
    if index < 0:
        index = 0
    start = max(0, index - 250)
    end = min(len(text), index + len(needle) + SOURCE_RADII.get(chunk_id, radius))
    prefix = "…" if start else ""
    suffix = "…" if end < len(text) else ""
    return prefix + text[start:end].strip() + suffix


def _candidate(chunk: dict[str, Any], anchor_id: str) -> dict[str, Any]:
    return {
        "accession": chunk["accession"],
        "chunk_id": chunk["chunk_id"],
        "source_anchor_id": anchor_id,
        "relevant_source_text": _excerpt(chunk["chunk_id"], _source_text(chunk)),
    }


def _boolean(part_id: str, candidate_ids: list[str]) -> str:
    value = candidate_ids[0] if len(candidate_ids) == 1 else (
        "(" + " OR ".join(candidate_ids) + ")"
    )
    return f"{part_id}:{value}"


def _authoritative_rows() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    evidence = []
    numeric = []
    for filename in ORIGINAL_REVIEW_FILES:
        path = REVIEW_DIR / filename
        rows = _read_csv(path)
        if path.name.startswith("evidence_"):
            evidence.extend(rows)
        else:
            numeric.extend(rows)
    return evidence, numeric


def _validate_ground_truth(
    evidence_rows: list[dict[str, str]],
    numeric_rows: list[dict[str, str]],
    evidence: dict[str, Any],
    numeric: dict[str, Any],
) -> None:
    all_rows = evidence_rows + numeric_rows
    decisions = [row["reviewer_decision"] for row in all_rows]
    if len(all_rows) != 302 or decisions.count("APPROVE") != 290:
        raise RuntimeError("authoritative review must contain 302 rows and 290 approvals")
    if decisions.count("REJECT") != 12 or decisions.count("NEEDS_SOURCE_CHECK") != 0:
        raise RuntimeError("authoritative review rejection counts changed")
    rejected = {_key(row) for row in evidence_rows if row["reviewer_decision"] == "REJECT"}
    if rejected != REPAIR_KEYS:
        raise RuntimeError("authoritative rejected evidence set differs from repair scope")

    part_by_key = {
        (item["q_id"], item["q_version"], item["item_id"], part["part_id"]): part
        for item in evidence["items"]
        for part in item["parts"]
    }
    for row in evidence_rows:
        if row["reviewer_decision"] != "APPROVE":
            continue
        actual = part_by_key[_key(row)]["candidate_sources"]
        if "candidates_json" in row:
            expected = json.loads(row["candidates_json"])
            expected_ids = [
                (source["accession"], source["chunk_id"], source["source_anchor_id"])
                for source in expected
            ]
        else:
            expected_ids = [(row["accession"], row["chunk_id"], row["source_anchor_id"])]
        actual_ids = [
            (source["accession"], source["chunk_id"], source["anchor_id"])
            for source in actual
        ]
        if actual_ids != expected_ids:
            raise RuntimeError(f"approved evidence mapping changed: {_key(row)}")

    fact_by_id = {fact["fact_id"]: fact for fact in numeric["facts"]}
    for row in numeric_rows:
        fact = fact_by_id[row["fact_id"]]
        if "alternatives_json" in row:
            expected_ids = [
                (source["accession"], source["chunk_id"], source["source_anchor_id"])
                for source in json.loads(row["alternatives_json"])
            ]
            actual_ids = [
                (source["accession"], source["chunk_id"], source["anchor_id"])
                for source in fact["candidate_sources"]
            ]
            if actual_ids != expected_ids:
                raise RuntimeError(f"approved numeric OR mapping changed: {row['fact_id']}")
        elif "chunk_id" in row:
            source = fact["candidate_sources"][0]
            expected = (row["accession"], row["chunk_id"], row["source_anchor_id"])
            actual = (source["accession"], source["chunk_id"], source["anchor_id"])
            if actual != expected:
                raise RuntimeError(f"approved numeric mapping changed: {row['fact_id']}")
        else:
            expected_union = json.loads(row["derived_candidate_union_json"])
            expected_anchors = json.loads(row["input_provenance_anchors_json"])
            actual_anchors = {
                input_id: [
                    source["anchor_id"]
                    for source in fact_by_id[input_id]["candidate_sources"]
                ]
                for input_id in fact["input_fact_ids"]
            }
            if fact["candidate_chunk_ids"] != expected_union or actual_anchors != expected_anchors:
                raise RuntimeError(f"approved derived mapping changed: {row['fact_id']}")


def build() -> list[dict[str, Any]]:
    chunks = _chunks()
    evidence = _load_json(PROVENANCE_DIR / "evidence_provenance_draft.json")
    numeric = _load_json(PROVENANCE_DIR / "numeric_facts_draft.json")
    reviewed_evidence, reviewed_numeric = _authoritative_rows()
    _validate_ground_truth(reviewed_evidence, reviewed_numeric, evidence, numeric)

    item_by_key = {
        (item["q_id"], item["q_version"], item["item_id"]): item
        for item in evidence["items"]
    }
    rejected_rows = [
        row for row in reviewed_evidence if row["reviewer_decision"] == "REJECT"
    ]
    rejected_rows.sort(key=_key)
    packet_rows: list[dict[str, Any]] = []
    for old in rejected_rows:
        key = _key(old)
        if "candidates_json" in old:
            old_sources = json.loads(old["candidates_json"])
        else:
            old_sources = [{
                "accession": old["accession"],
                "chunk_id": old["chunk_id"],
                "source_anchor_id": old["source_anchor_id"],
                "relevant_source_text": old["relevant_source_text"],
            }]
        compact_old_sources = [
            _candidate(chunks[source["chunk_id"]], source["source_anchor_id"])
            for source in old_sources
        ]

        item = item_by_key[key[:3]]
        proposed_ids = PROPOSED_PARTS.get(key, [key[3]])
        part_by_id = {part["part_id"]: part for part in item["parts"]}
        proposed = []
        for part_id in proposed_ids:
            part = part_by_id[part_id]
            proposed.append({
                "part_id": part_id,
                "semantic_requirement": part["description"],
                "source_atom_ids": part["source_atom_ids"],
                "candidates": [
                    _candidate(chunks[source["chunk_id"]], source["anchor_id"])
                    for source in part["candidate_sources"]
                ],
                "merge_lineage": part["merge_lineage"],
            })

        old_ids = [source["chunk_id"] for source in compact_old_sources]
        old_boolean = _boolean(old["part_id"], old_ids)
        new_boolean = " AND ".join(
            _boolean(
                part["part_id"],
                [source["chunk_id"] for source in part["candidates"]],
            )
            for part in proposed
        )
        packet_rows.append({
            "q_id": old["q_id"],
            "q_version": old["q_version"],
            "item_id": old["item_id"],
            "old_part_id": old["part_id"],
            "old_semantic_requirement": old["semantic_requirement"],
            "old_mapping_json": _json(compact_old_sources),
            "proposed_mapping_json": _json(proposed),
            "newly_split": len(proposed) > 1,
            "old_boolean_structure": old_boolean,
            "new_boolean_structure": new_boolean,
            "affected_merge_lineage": MERGE_LINEAGE.get(key, "none"),
            "reviewer_decision": "",
            "reviewer_note": "",
        })

    if len(packet_rows) != 12:
        raise RuntimeError("repair packet must contain exactly 12 rejected mappings")
    fields = list(packet_rows[0])
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(packet_rows)

    lines = [
        "# Provenance repair review",
        "",
        "Only the 12 mappings rejected in the completed human review are included. "
        "Reviewer decisions are intentionally blank.",
        "",
    ]
    for row in packet_rows:
        identity = f"{row['q_id']}/{row['item_id']}/{row['old_part_id']}"
        lines.extend([
            f"## {identity}",
            "",
            f"- Old requirement: {row['old_semantic_requirement']}",
            f"- Newly split: {str(row['newly_split']).lower()}",
            f"- Old Boolean structure: `{row['old_boolean_structure']}`",
            f"- New Boolean structure: `{row['new_boolean_structure']}`",
            f"- Merge lineage: {row['affected_merge_lineage']}",
            "- Reviewer decision: **[blank]**",
            "- Reviewer note: **[blank]**",
            "",
            "### Rejected old mapping",
            "",
        ])
        for source in json.loads(row["old_mapping_json"]):
            lines.extend([
                f"Source `{source['chunk_id']}` / `{source['source_anchor_id']}` "
                f"(accession `{source['accession']}`):",
                "",
                "> " + source["relevant_source_text"].replace("\n", "\n> "),
                "",
            ])
        lines.extend(["### Proposed corrected mapping", ""])
        for part in json.loads(row["proposed_mapping_json"]):
            lines.extend([
                f"#### {part['part_id']} — {part['semantic_requirement']}",
                "",
            ])
            for source in part["candidates"]:
                lines.extend([
                    f"Source `{source['chunk_id']}` / `{source['source_anchor_id']}` "
                    f"(accession `{source['accession']}`):",
                    "",
                    "> " + source["relevant_source_text"].replace("\n", "\n> "),
                    "",
                ])
    MARKDOWN_PATH.parent.mkdir(parents=True, exist_ok=True)
    MARKDOWN_PATH.write_text("\n".join(lines), encoding="utf-8")
    return packet_rows


def main() -> int:
    rows = build()
    print(f"provenance repair packet complete: {len(rows)} rejected mappings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
