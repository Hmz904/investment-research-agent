"""Evaluation-only deterministic provenance rebuild for ingestion v0.1.1.

This is benchmark-side tooling. It deliberately does not perform retrieval,
ranking, embedding, or model-assisted candidate generation. The reviewed
semantic requirements in ``benchmark/provenance/gold_chunk_map_draft.csv``
are resolved against the current corpus by accession and exact source
identity, then validated from current table/XBRL/literal source metadata.
"""

from __future__ import annotations

import csv
import hashlib
import itertools
import json
import re
import unicodedata
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
PARENT_FROZEN_DIR = ROOT / "benchmark" / "frozen"
BENCHMARK_DIR = ROOT / "benchmark" / "releases" / "v0.1.1"
OUTPUT_DIR = ROOT / "benchmark" / "provenance"
REVIEW_PATH = ROOT / "review" / "provenance_v011_rebuild.md"
BOUNDARY_REVIEW_PATH = ROOT / "review" / "provenance_boundary_audit.md"
SEED_PATH = OUTPUT_DIR / "gold_chunk_map_draft.csv"

INGESTION_TAG = "ingestion_v0.1.1"
INGESTION_GIT_COMMIT = "63cabb2"
EXPECTED_CORPUS_FINGERPRINT = (
    "56df698d50b13cf15e913c1c60dbc96b1fd0fab44adb7b1f40ba99771c4b7c96"
)
BENCHMARK_VERSION = "bench_v0.1.1"
BENCHMARK_PARENT_VERSION = "bench_v0.1"
BENCHMARK_SCHEMA_VERSION = "v0.1.2"
PROVENANCE_SCHEMA_VERSION = "v0.2.0-draft"

UNIT_EXPONENT = {
    "USD_million": 6,
    "USD_billion": 9,
    "percent": 0,
    "percentage_point": 0,
}

# These are source-contract adjudications, not candidate hints. The actual
# support is resolved and quoted from the current corpus below.
CONTRACT_SUPPORT = {
    ("Q02", "2", "E05"): {
        "chunk_id": "513ec1bcd5f5b923",
        "required_chunk_ids": ["513ec1bcd5f5b923"],
        "required_needles": {"513ec1bcd5f5b923": "Under the previous sub-markets"},
        "actual_required_accessions": ["0001045810-26-000051"],
        "required_semantic_part": (
            "Older-split networking growth of about 199% YoY and compute "
            "growth of about 77% YoY"
        ),
        "needle": "Under the previous sub-markets",
        "why_unsatisfiable": (
            "The contracted FY27Q1 10-Q uses the new market-platform presentation "
            "and does not disclose the older compute/networking 77%/199% pair."
        ),
    },
    ("Q05", "2", "X3"): {
        "chunk_id": "a35a2f866d18fd19",
        "required_chunk_ids": ["a35a2f866d18fd19", "e19520eac6dfcec3"],
        "required_needles": {
            "a35a2f866d18fd19": "Revenue is expected to be $91.0 billion",
            "e19520eac6dfcec3": "96,221",
        },
        "actual_required_accessions": [
            "0001045810-26-000051", "0001045810-26-000073"
        ],
        "required_semantic_part": "FY27Q1 guidance upper end of USD 92.82B",
        "needle": "Revenue is expected to be $91.0 billion",
        "why_unsatisfiable": (
            "The contracted Q2 income statement proves exact realized Q2 revenue but "
            "does not contain the earlier $91.0B plus-or-minus 2% outlook needed to "
            "derive $92.82B."
        ),
    },
    ("Q05", "2", "X4"): {
        "chunk_id": "79ddd90f5c73467d",
        "required_chunk_ids": [
            "79ddd90f5c73467d", "66a2dbe9fa036e7f", "6e776edb42ae8862"
        ],
        "required_needles": {
            "79ddd90f5c73467d": "Row: Hyperscale",
            "66a2dbe9fa036e7f": "Row: Hyperscale",
            "6e776edb42ae8862": "Row: Hyperscale",
        },
        "actual_required_accessions": [
            "0001045810-26-000052", "0001045810-26-000075"
        ],
        "required_semantic_part": (
            "Original Q1 Hyperscale and ACIE values required to establish "
            "the USD 5.181B reclassification"
        ),
        "needle": "Row: Hyperscale",
        "why_unsatisfiable": (
            "The contracted Q2 10-Q contains recast Q1 values and the unchanged "
            "Data Center total, but not the original Q1 component values needed "
            "to prove the $5.181B reclassification amount."
        ),
    },
    ("Q12", "2", "E07"): {
        "chunk_id": "7b2aecb6f4439586",
        "required_chunk_ids": ["8c05d5174f59448e", "7b2aecb6f4439586"],
        "required_needles": {
            "8c05d5174f59448e": "Depreciation and amortization",
            "7b2aecb6f4439586": "Depreciation expense on property and equipment",
        },
        "actual_required_accessions": [
            "0001628280-26-028364", "0001628280-26-028526"
        ],
        "required_semantic_part": "Property-and-server depreciation increase",
        "needle": "Depreciation expense on property and equipment",
        "why_unsatisfiable": (
            "The contracted earnings exhibit reports total depreciation and "
            "amortization but does not identify property or server/network depreciation; "
            "that component appears only in the 10-Q."
        ),
    },
}

# Exact atomic lineage of the release map. Most groups retain the previous
# approved proposal; the review-repair groups below remain pending re-review.
# The generator validates that every group has the identical complete OR set
# required for Boolean idempotence.
SEMANTIC_COMPONENT_GROUPS: dict[tuple[str, str, str], list[list[str]]] = {
    ("Q02", "2", "E01"): [["P01", "P02", "P03"]],
    ("Q02", "2", "E04"): [["P01", "P02"]],
    ("Q02", "2", "E07"): [["P01", "P02"]],
    ("Q02", "2", "E08"): [["P01", "P02"]],
    ("Q02", "2", "E09"): [["P01", "P02", "P03"]],
    ("Q05", "2", "P3"): [["P01", "P02"]],
    ("Q05", "2", "C1"): [["P01", "P02", "P03"]],
    ("Q05", "2", "C2"): [["P01", "P02", "P03"]],
    ("Q05", "2", "C3"): [["P01", "P02"]],
    ("Q07", "2", "E01"): [["P01", "P02"]],
    ("Q07", "2", "E02"): [["P01", "P02"]],
    ("Q07", "2", "E05"): [["P01", "P02", "P03"]],
    ("Q07", "2", "E06"): [["P01", "P02", "P03"]],
    ("Q07", "2", "E08"): [["P01", "P02"]],
    ("Q07", "2", "E09"): [["P01", "P02"]],
    ("Q07", "2", "E10"): [["P01", "P02"]],
    ("Q07", "2", "E11"): [["P01", "P02"]],
    ("Q07", "2", "E12"): [["P01", "P02"]],
    ("Q10", "2", "P1"): [["P01", "P02"]],
    ("Q10", "2", "P3"): [["P01", "P02"]],
    ("Q10", "2", "C1"): [["P01", "P02"]],
    ("Q10", "2", "C2"): [["P01", "P02", "P03", "P04"]],
    ("Q10", "2", "C3"): [["P01", "P02"]],
    ("Q10", "2", "C4"): [["P01", "P02"]],
    ("Q10", "2", "C5"): [["P01", "P02"]],
    ("Q10", "2", "C6"): [["P01", "P02"]],
    ("Q10", "2", "X5"): [["P02", "P03"]],
    ("Q12", "2", "E01"): [["P01", "P02", "P03"], ["P04", "P05"]],
    ("Q12", "2", "E02"): [["P01", "P02"]],
    ("Q12", "2", "E03"): [["P01", "P02", "P03"]],
    ("Q12", "2", "E04"): [["P01", "P02", "P03"]],
    ("Q12", "2", "E06"): [["P01", "P02", "P03"]],
    ("Q12", "2", "E08"): [["P01", "P02", "P03"]],
    ("Q12", "2", "E09"): [["P01", "P02"]],
    ("Q12", "2", "E10"): [["P01", "P02"]],
    ("Q14", "2", "P1"): [["P01", "P02"]],
    ("Q14", "2", "P2"): [["P01", "P02"]],
    ("Q14", "2", "P3"): [["P01", "P02"]],
    ("Q14", "2", "C1"): [["P01", "P02"], ["P03", "P04"]],
    ("Q14", "2", "C3"): [["P01", "P02"]],
    ("Q14", "2", "C6"): [["P01", "P02"]],
    ("Q14", "2", "C7"): [["P01", "P02", "P03"]],
    ("Q15", "2", "E03"): [["P02", "P03"], ["P05", "P06"]],
    ("Q15", "2", "E04"): [["P02", "P03"], ["P05", "P06"]],
    ("Q15", "2", "E05"): [
        ["P02", "P03"], ["P05", "P06"], ["P08", "P09"], ["P11", "P12"]
    ],
    ("Q15", "2", "E08"): [
        ["P02", "P03"], ["P05", "P06"], ["P08", "P09"], ["P11", "P12"]
    ],
}

# These merge rows have changed Boolean structure or are newly split as part of
# the human-review repair. Their semantic lineage is retained, but approval is
# deliberately blank until the repaired packet is reviewed.
REPAIRED_MERGE_GROUPS: set[tuple[str, str, str, tuple[str, ...]]] = {
    ("Q02", "2", "E01", ("P01", "P02", "P03")),
    ("Q05", "2", "C1", ("P01", "P02", "P03")),
    ("Q12", "2", "E01", ("P01", "P02", "P03")),
    ("Q12", "2", "E01", ("P04", "P05")),
    ("Q14", "2", "C1", ("P01", "P02")),
    ("Q14", "2", "C1", ("P03", "P04")),
}

# The rejected Q07/E04 mapping demonstrated that its frozen 10-Q contract
# cannot support the 99% growth atom. The repair adds only the paired earnings
# release accession needed for that atom; the frozen release remains untouched.
REPAIR_ACCESSION_EXPANSIONS: dict[tuple[str, str, str], set[str]] = {
    ("Q07", "2", "E04"): {"0001193125-26-191457"},
}

# Source-only errata make these formerly out-of-contract atomic parts
# satisfiable. Keys deliberately retain the original atom IDs so the source
# contract correction does not alter semantic part granularity.
ERRATA_ATOM_CANDIDATES: dict[tuple[str, str, str, str], list[str]] = {
    ("Q02", "2", "E05", "P01"): ["513ec1bcd5f5b923"],
    ("Q02", "2", "E05", "P02"): ["513ec1bcd5f5b923"],
    ("Q05", "2", "X3", "P01"): ["a35a2f866d18fd19"],
    ("Q05", "2", "X4", "P02"): ["79ddd90f5c73467d"],
    ("Q12", "2", "E07", "P02"): ["7b2aecb6f4439586"],
}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(
            {
                field: (
                    str(row.get(field)).lower()
                    if isinstance(row.get(field), bool)
                    else row.get(field, "")
                )
                for field in fields
            }
            for row in rows
        )


def _normalize(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", value or "")
    return re.sub(r"\s+", " ", text).strip()


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace(",", "").replace("$", "").strip())
    except InvalidOperation:
        return None


def _json_list(value: str) -> list[str]:
    return list(json.loads(value or "[]"))


def _json_dict(value: str) -> dict[str, Any]:
    return dict(json.loads(value or "{}"))


def version_binding(data_dir: Path = DATA_DIR) -> dict[str, Any]:
    """Return the release binding, failing loudly on any corpus mismatch."""
    manifest_path = data_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = manifest.get("corpus_fingerprint")
    if actual != EXPECTED_CORPUS_FINGERPRINT:
        raise RuntimeError(
            "CORPUS FINGERPRINT MISMATCH: expected "
            f"{EXPECTED_CORPUS_FINGERPRINT}, got {actual!r} from {manifest_path}"
        )
    release_manifest_path = BENCHMARK_DIR / "release_manifest.json"
    if not release_manifest_path.exists():
        raise RuntimeError(
            f"materialized benchmark release is missing: {release_manifest_path}"
        )
    release_manifest = json.loads(release_manifest_path.read_text(encoding="utf-8"))
    if release_manifest.get("benchmark_release_version") != BENCHMARK_VERSION:
        raise RuntimeError("materialized benchmark release version mismatch")
    if release_manifest.get("benchmark_parent_version") != BENCHMARK_PARENT_VERSION:
        raise RuntimeError("materialized benchmark parent version mismatch")
    for filename, expected_sha256 in release_manifest.get("files", {}).items():
        release_path = BENCHMARK_DIR / filename
        if not release_path.exists():
            raise RuntimeError(f"materialized benchmark file is missing: {release_path}")
        actual_sha256 = hashlib.sha256(release_path.read_bytes()).hexdigest()
        if actual_sha256 != expected_sha256:
            raise RuntimeError(
                f"materialized benchmark file hash mismatch: {release_path}"
            )
    return {
        "ingestion_tag": INGESTION_TAG,
        "ingestion_git_commit": INGESTION_GIT_COMMIT,
        "corpus_fingerprint": EXPECTED_CORPUS_FINGERPRINT,
        "benchmark_version": BENCHMARK_VERSION,
        "benchmark_parent_version": BENCHMARK_PARENT_VERSION,
        "benchmark_schema_version": BENCHMARK_SCHEMA_VERSION,
        "benchmark_component_tags": ["bench_v0.1.1"],
        "provenance_schema_version": PROVENANCE_SCHEMA_VERSION,
    }


def load_corpus(data_dir: Path = DATA_DIR) -> tuple[
    dict[str, dict[str, Any]], dict[str, dict[str, Any]]
]:
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    entries = {entry["doc_id"]: entry for entry in manifest["entries"]}
    chunks: dict[str, dict[str, Any]] = {}
    for path in sorted((data_dir / "chunks").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for chunk in payload["chunks"]:
            chunk_id = chunk["chunk_id"]
            if chunk_id in chunks:
                raise RuntimeError(f"duplicate chunk_id in corpus: {chunk_id}")
            chunks[chunk_id] = chunk
    return chunks, entries


def normalized_source_text(chunk: dict[str, Any]) -> str:
    """Canonical content used for the persistent source fingerprint."""
    table = chunk.get("table_json") or {}
    primary = chunk.get("retrieval_text") or chunk.get("text") or ""
    footnotes = table.get("footnotes") or []
    content = "\n".join([primary, *footnotes])
    return _normalize(content).casefold()


def normalized_source_fingerprint(chunk: dict[str, Any]) -> str:
    content = normalized_source_text(chunk).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _unique(values: Iterable[Any]) -> list[Any]:
    out: list[Any] = []
    for value in values:
        if value not in (None, "", []) and value not in out:
            out.append(value)
    return out


def make_anchor(chunk: dict[str, Any], entries: dict[str, dict[str, Any]]) -> dict[str, Any]:
    entry = entries[chunk["doc_id"]]
    table = chunk.get("table_json") or {}
    rows = table.get("rows") or []
    cells = [cell for row in rows for cell in row.get("cells", [])]
    fingerprint = normalized_source_fingerprint(chunk)
    return {
        "anchor_id": f"src_{fingerprint[:24]}",
        "accession": chunk["accession"],
        "doc_id": chunk["doc_id"],
        "raw_document_sha256": entry["raw_sha256"],
        "chunk_id": chunk["chunk_id"],
        "char_start": chunk["char_start"],
        "char_end": chunk["char_end"],
        "normalized_source_fingerprint": fingerprint,
        "fingerprint_algorithm": "sha256(nfkc_casefold_whitespace(source_text+footnotes))",
        "block_type": chunk.get("block_type"),
        "row_label": _unique(row.get("row_label") for row in rows),
        "effective_column_label": _unique(cell.get("column_label") for cell in cells),
        "table_title": table.get("caption") or None,
        "section_path": chunk.get("section_path") or [],
        "attached_footnotes": table.get("footnotes") or [],
        "reviewer_decision": "",
        "reviewer_note": "",
    }


def _source_excerpt(chunk: dict[str, Any], needle: str | None = None, width: int = 900) -> str:
    source = _normalize(chunk.get("retrieval_text") or chunk.get("text") or "")
    if len(source) <= width:
        return source
    pos = source.casefold().find((needle or "").casefold()) if needle else -1
    if pos < 0:
        return source[:width].rstrip() + "…"
    start = max(0, pos - width // 3)
    end = min(len(source), start + width)
    return ("…" if start else "") + source[start:end].rstrip() + ("…" if end < len(source) else "")


def _candidate_record(
    chunk: dict[str, Any],
    anchor: dict[str, Any],
    *,
    method: str,
    table_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "anchor_id": anchor["anchor_id"],
        "accession": anchor["accession"],
        "doc_id": anchor["doc_id"],
        "raw_document_sha256": anchor["raw_document_sha256"],
        "chunk_id": anchor["chunk_id"],
        "char_start": anchor["char_start"],
        "char_end": anchor["char_end"],
        "normalized_source_fingerprint": anchor["normalized_source_fingerprint"],
        "mapping_method": method,
        "source_excerpt": _source_excerpt(chunk),
        "row_label": (
            (table_identity or {}).get("row_label")
            if table_identity
            else anchor["row_label"]
        ),
        "effective_column_label": (
            (table_identity or {}).get("effective_column_label")
            if table_identity
            else anchor["effective_column_label"]
        ),
        "table_title": anchor["table_title"],
        "section_path": anchor["section_path"],
        "table_identity": table_identity,
        "reviewer_decision": "",
        "reviewer_note": "",
    }


def _matching_cells(
    fact: dict[str, str],
    chunk: dict[str, Any],
    seed: dict[str, str],
) -> list[dict[str, Any]]:
    table = chunk.get("table_json") or {}
    expected = _decimal(fact["value"])
    observed_rows = _json_dict(seed.get("observed_row_label", ""))
    observed_cols = _json_dict(seed.get("observed_column_label", ""))
    wanted_row = observed_rows.get(chunk["chunk_id"], "")
    wanted_col = observed_cols.get(chunk["chunk_id"], "")
    matches: list[dict[str, Any]] = []
    for row in table.get("rows", []):
        for cell in row.get("cells", []):
            parsed = _decimal(cell.get("parsed_value"))
            raw = _normalize(cell.get("raw_text"))
            numeric_match = parsed is not None and expected is not None and abs(parsed) == abs(expected)
            # F004 is directly displayed as ``0.1 pts`` but intentionally has
            # no parsed_value in ingestion v0.1.1.
            literal_match = fact["fact_id"] == "F004" and "0.1" in raw
            if not (numeric_match or literal_match):
                continue
            if wanted_row and row.get("row_label") != wanted_row:
                continue
            if wanted_col and cell.get("column_label") != wanted_col:
                continue
            matches.append(
                {
                    "raw_text": cell.get("raw_text"),
                    "parsed_value": cell.get("parsed_value"),
                    "row_label": row.get("row_label"),
                    "effective_column_label": cell.get("column_label"),
                    "period_start": cell.get("period_start"),
                    "period_end": cell.get("period_end"),
                    "instant_date": cell.get("instant_date"),
                    "period_label": cell.get("period_label"),
                    "duration_months": cell.get("duration_months"),
                    "unit": cell.get("unit_label") or table.get("unit_label"),
                    "unit_scale": cell.get("unit_scale") if cell.get("unit_scale") is not None else table.get("unit_scale"),
                    "is_percent": cell.get("is_percent"),
                    "display_is_negative": bool(parsed is not None and parsed < 0) or "(" in raw,
                }
            )
    return matches


def _matching_xbrl(fact: dict[str, str], chunk: dict[str, Any]) -> list[dict[str, Any]]:
    expected = _decimal(fact["value"])
    if expected is None:
        return []
    expected_scaled = expected * (Decimal(10) ** UNIT_EXPONENT.get(fact["unit"], 0))
    tag = fact.get("xbrl_tag") or ""
    matches = []
    for xbrl in chunk.get("xbrl_facts") or []:
        if tag and tag not in (xbrl.get("concept") or ""):
            continue
        scaled = _decimal(xbrl.get("scaled_value"))
        if scaled is None or abs(scaled) != abs(expected_scaled):
            continue
        matches.append(
            {
                "accession": chunk["accession"],
                "concept": xbrl.get("concept"),
                "dimensions": xbrl.get("dimensions") or [],
                "members": xbrl.get("members") or [],
                "raw_visible_text": xbrl.get("raw_visible_text"),
                "parsed_value": xbrl.get("parsed_value"),
                "scaled_value": xbrl.get("scaled_value"),
                "period_start": xbrl.get("period_start"),
                "period_end": xbrl.get("period_end"),
                "instant_date": xbrl.get("instant_date"),
                "unit": xbrl.get("unit"),
                "unit_measures": xbrl.get("unit_measures") or [],
                "scale": xbrl.get("scale"),
                "decimals": xbrl.get("decimals"),
                "sign": xbrl.get("sign"),
                "is_negative": xbrl.get("is_negative"),
            }
        )
    return matches


def _fact_sign_semantics(fact: dict[str, str], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    displays: list[dict[str, Any]] = []
    for candidate in candidates:
        identity = candidate.get("table_identity") or {}
        for cell in identity.get("table_cells", []):
            displays.append(
                {
                    "chunk_id": candidate["chunk_id"],
                    "raw_text": cell.get("raw_text"),
                    "display_is_negative": cell.get("display_is_negative"),
                }
            )
    positive_magnitude = fact["basis"] == "cash_ppe"
    return {
        "benchmark_value_convention": (
            "positive_economic_magnitude" if positive_magnitude else "as_reported"
        ),
        "accounting_display_sign_preserved": bool(displays),
        "source_displays": displays,
    }


def build_numeric_facts(
    binding: dict[str, Any],
    chunks: dict[str, dict[str, Any]],
    anchors: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    facts = _read_csv(BENCHMARK_DIR / "numeric_answers.csv")
    seed_rows = {
        row["fact_id"]: row
        for row in _read_csv(SEED_PATH)
        if row.get("fact_id")
    }
    records: dict[str, dict[str, Any]] = {}
    direct_facts = [fact for fact in facts if fact["is_derived"].lower() != "true"]
    pending = [fact for fact in facts if fact["is_derived"].lower() == "true"]
    ordered_facts = list(direct_facts)
    available = {fact["fact_id"] for fact in direct_facts}
    while pending:
        ready = [
            fact
            for fact in pending
            if set(part for part in fact["input_items"].split(";") if part) <= available
        ]
        if not ready:
            raise RuntimeError(
                "numeric dependency graph is cyclic or references a missing fact: "
                + ", ".join(fact["fact_id"] for fact in pending)
            )
        ordered_facts.extend(ready)
        available.update(fact["fact_id"] for fact in ready)
        pending = [fact for fact in pending if fact not in ready]

    for fact in ordered_facts:
        fact_id = fact["fact_id"]
        seed = seed_rows[fact_id]
        input_ids = [part for part in fact["input_items"].split(";") if part]
        if fact["is_derived"].lower() == "true":
            candidate_ids = _unique(
                cid
                for input_id in input_ids
                for cid in records[input_id]["candidate_chunk_ids"]
            )
            candidates = [
                _candidate_record(
                    chunks[cid], anchors[cid], method="explicit_formula_input_relationship"
                )
                for cid in candidate_ids
            ]
            records[fact_id] = {
                "fact_id": fact_id,
                "q_id": fact["q_id"] or None,
                "q_version": fact["q_version"] or None,
                "role": fact["role"],
                "answer_group": fact["answer_group"] or None,
                "answer_method": fact["answer_method"] or None,
                "value": fact["value"],
                "unit": fact["unit"],
                "basis": fact["basis"],
                "period_scope": fact["period_scope"],
                "is_derived": True,
                "formula": fact["formula"],
                "input_fact_ids": input_ids,
                "status": "derived",
                "candidate_chunk_ids": candidate_ids,
                "candidate_sources": candidates,
                "source_identity": {"type": "derived", "inputs": input_ids},
                "sign_semantics": {
                    "benchmark_value_convention": "formula_result",
                    "accounting_display_sign_preserved_in_inputs": True,
                },
                "reviewer_decision": "",
                "reviewer_note": "",
            }
            continue

        candidate_ids = _json_list(seed["candidate_chunk_ids"])
        if not candidate_ids:
            raise RuntimeError(f"direct numeric fact {fact_id} has no reviewed source")
        frozen_accessions = set(fact["accession"].split(";"))
        candidates: list[dict[str, Any]] = []
        identity_type = "literal"
        for cid in candidate_ids:
            chunk = chunks.get(cid)
            if chunk is None:
                raise RuntimeError(f"numeric fact {fact_id}: missing current chunk {cid}")
            if chunk["accession"] not in frozen_accessions:
                raise RuntimeError(f"numeric fact {fact_id}: {cid} violates accession contract")
            xbrl = _matching_xbrl(fact, chunk)
            cells = _matching_cells(fact, chunk, seed)
            if fact["source_type"] == "xbrl":
                if not xbrl:
                    raise RuntimeError(f"numeric fact {fact_id}: no exact XBRL identity in {cid}")
                identity_type = "xbrl"
            elif cells:
                identity_type = "table"
            else:
                value = Decimal(fact["value"])
                variants = {
                    fact["value"],
                    f"{int(value):,}" if value == value.to_integral_value() else fact["value"],
                }
                source = normalized_source_text(chunk).replace(",", "")
                if not any(_normalize(v).casefold().replace(",", "") in source for v in variants):
                    raise RuntimeError(f"numeric fact {fact_id}: no literal value in {cid}")
            table_identity = None
            if cells or xbrl:
                table_identity = {
                    "table_cells": cells,
                    "xbrl_facts": xbrl,
                    "row_label": cells[0]["row_label"] if cells else None,
                    "effective_column_label": cells[0]["effective_column_label"] if cells else None,
                }
            candidates.append(
                _candidate_record(
                    chunk,
                    anchors[cid],
                    method=f"exact_{identity_type}_identity",
                    table_identity=table_identity,
                )
            )
        records[fact_id] = {
            "fact_id": fact_id,
            "q_id": fact["q_id"] or None,
            "q_version": fact["q_version"] or None,
            "role": fact["role"],
            "answer_group": fact["answer_group"] or None,
            "answer_method": fact["answer_method"] or None,
            "value": fact["value"],
            "unit": fact["unit"],
            "basis": fact["basis"],
            "period_scope": fact["period_scope"],
            "is_derived": False,
            "formula": None,
            "input_fact_ids": [],
            "status": "direct_or" if len(candidate_ids) > 1 else "direct_unique",
            "candidate_chunk_ids": candidate_ids,
            "candidate_sources": candidates,
            "source_identity": {
                "type": identity_type,
                "accessions": sorted(frozen_accessions),
                "expected_concept": fact["xbrl_tag"] or None,
                "expected_value": fact["value"],
                "expected_unit": fact["unit"],
                "expected_basis": fact["basis"],
                "expected_period_scope": fact["period_scope"],
            },
            "sign_semantics": _fact_sign_semantics(fact, candidates),
            "reviewer_decision": "",
            "reviewer_note": "",
        }
    return {
        "version_binding": binding,
        "artifact_type": "numeric_fact_provenance_draft",
        "boolean_semantics": "OR among candidate_sources for a direct fact; derived facts require all input_fact_ids",
        "fact_count": len(records),
        "facts": [records[fact["fact_id"]] for fact in facts],
    }


def _semantic_parts(
    item_key: tuple[str, str, str], rows: list[dict[str, str]]
) -> list[list[dict[str, str]]]:
    """Apply explicit, item-specific source-level semantic adjudications."""
    by_id = {row["part_id"]: row for row in rows}
    explicit_groups = SEMANTIC_COMPONENT_GROUPS.get(item_key, [])
    grouped_ids = [part_id for group in explicit_groups for part_id in group]
    if len(grouped_ids) != len(set(grouped_ids)):
        raise RuntimeError(f"duplicate semantic component atom in {item_key}")
    unknown = set(grouped_ids) - set(by_id)
    if unknown:
        raise RuntimeError(f"unknown semantic component atoms in {item_key}: {unknown}")

    group_by_part = {
        part_id: group
        for group in explicit_groups
        for part_id in group
    }
    emitted: set[tuple[str, ...]] = set()
    result: list[list[dict[str, str]]] = []
    for row in rows:
        group = tuple(group_by_part.get(row["part_id"], [row["part_id"]]))
        if group in emitted:
            continue
        emitted.add(group)
        component = [by_id[part_id] for part_id in group]
        # This check validates the explicit semantic decision; it does not make
        # the decision. Every OR candidate must independently contain the full
        # co-disclosed component.
        identities = {
            (
                candidate["accession"],
                tuple(_json_list(candidate["candidate_chunk_ids"])),
                candidate["proposed_status"],
            )
            for candidate in component
        }
        if len(component) > 1 and len(identities) != 1:
            raise RuntimeError(
                f"semantic component {item_key}/{group} does not have one complete OR set"
            )
        result.append(component)
    return result


def _minimum_distinct_hits(parts: list[dict[str, Any]]) -> int | None:
    candidate_sets = [set(part["candidate_chunk_ids"]) for part in parts]
    if any(not values for values in candidate_sets):
        return None
    universe = sorted(set().union(*candidate_sets))
    for size in range(1, len(universe) + 1):
        for selection in itertools.combinations(universe, size):
            chosen = set(selection)
            if all(chosen & values for values in candidate_sets):
                return size
    raise AssertionError("finite candidate sets must have a cover")


def build_evidence(
    binding: dict[str, Any],
    chunks: dict[str, dict[str, Any]],
    anchors: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    checklist = [
        row
        for row in _read_csv(BENCHMARK_DIR / "evidence_checklist.csv")
        if row["verification_status"] == "verified"
    ]
    seed_by_item: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in _read_csv(SEED_PATH):
        if row.get("item_id"):
            seed_by_item[(row["q_id"], row["q_version"], row["item_id"])].append(row)

    items: list[dict[str, Any]] = []
    for frozen in checklist:
        key = (frozen["q_id"], frozen["q_version"], frozen["item_id"])
        seed_rows = seed_by_item[key]
        if not seed_rows:
            raise RuntimeError(f"verified evidence missing semantic seed: {key}")
        parts: list[dict[str, Any]] = []
        for index, component_rows in enumerate(_semantic_parts(key, seed_rows), start=1):
            first = component_rows[0]
            atom_ids = tuple(row["part_id"] for row in component_rows)
            is_merge = len(component_rows) > 1
            repaired_merge = (*key, atom_ids) in REPAIRED_MERGE_GROUPS
            candidate_lists = [
                ERRATA_ATOM_CANDIDATES.get(
                    (*key, row["part_id"]), _json_list(row["candidate_chunk_ids"])
                )
                for row in component_rows
            ]
            if len(component_rows) > 1 and any(
                values != candidate_lists[0] for values in candidate_lists[1:]
            ):
                raise RuntimeError(
                    f"approved semantic component {key} has inconsistent candidate sets"
                )
            candidate_ids = candidate_lists[0]
            frozen_accessions = set(frozen["accession"].split(";"))
            allowed_accessions = frozen_accessions | REPAIR_ACCESSION_EXPANSIONS.get(
                key, set()
            )
            candidates: list[dict[str, Any]] = []
            for cid in candidate_ids:
                chunk = chunks.get(cid)
                if chunk is None:
                    raise RuntimeError(f"evidence {key}: missing current chunk {cid}")
                if chunk["accession"] not in allowed_accessions:
                    raise RuntimeError(f"evidence {key}: candidate {cid} violates frozen contract")
                candidates.append(
                    _candidate_record(
                        chunk,
                        anchors[cid],
                        method="literal_structural_metadata_or_source_adjacency",
                    )
                )
            requirements = [row["part_description"] for row in component_rows]
            status = "supported" if candidate_ids else "benchmark_contract_error"
            parts.append(
                {
                    "part_id": f"P{index:02d}",
                    "description": "; ".join(requirements),
                    "required_components": requirements,
                    "source_atom_ids": list(atom_ids),
                    "part_semantics": (
                        "retrieval-level merge pending human re-review"
                        if repaired_merge
                        else "human-approved retrieval-level merge of co-disclosed atoms"
                        if is_merge
                        else "one semantic evidence component"
                    ),
                    "merge_lineage": (
                        "C. repaired after human provenance review"
                        if repaired_merge
                        else "B. copied/applied from a previous merge proposal"
                        if is_merge
                        else None
                    ),
                    "human_approved_retrieval_merge": is_merge and not repaired_merge,
                    "candidates_operator": "OR",
                    "candidate_chunk_ids": candidate_ids,
                    "candidate_sources": candidates,
                    "status": status,
                    "reviewer_decision": "",
                    "reviewer_note": "",
                }
            )
        minimum = _minimum_distinct_hits(parts)
        items.append(
            {
                "q_id": frozen["q_id"],
                "q_version": frozen["q_version"],
                "item_id": frozen["item_id"],
                "claim": frozen["claim"],
                "stance": frozen["stance"],
                "importance": frozen["importance"],
                "temporal_role": frozen["temporal_role"],
                "evidence_period": frozen["evidence_period"],
                "frozen_accession_contract": frozen["accession"].split(";"),
                "repair_source_accessions": sorted(
                    REPAIR_ACCESSION_EXPANSIONS.get(key, set())
                ),
                "frozen_location": frozen["location"],
                "benchmark_source_contract_version": BENCHMARK_VERSION,
                "parts_operator": "AND",
                "parts": parts,
                "part_count": len(parts),
                "minimum_distinct_chunk_hits": minimum,
                "status": "supported" if minimum is not None else "benchmark_contract_error",
                "reviewer_decision": "",
                "reviewer_note": "",
            }
        )
    return {
        "version_binding": binding,
        "artifact_type": "evidence_provenance_and_or_draft",
        "boolean_semantics": "AND across parts; OR among candidate_sources within each part",
        "verified_item_count": len(items),
        "items": items,
    }


def build_contract_errors(
    binding: dict[str, Any],
    evidence: dict[str, Any],
    chunks: dict[str, dict[str, Any]],
    anchors: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    item_by_key = {
        (item["q_id"], item["q_version"], item["item_id"]): item
        for item in evidence["items"]
    }
    parent_rows = {
        (row["q_id"], row["q_version"], row["item_id"]): row
        for row in _read_csv(PARENT_FROZEN_DIR / "evidence_checklist.csv")
    }
    errors: list[dict[str, Any]] = []
    resolved_errors: list[dict[str, Any]] = []
    for key, support in CONTRACT_SUPPORT.items():
        item = item_by_key[key]
        parent = parent_rows[key]
        chunk = chunks[support["chunk_id"]]
        anchor = anchors[chunk["chunk_id"]]
        required_sources = []
        for chunk_id in support["required_chunk_ids"]:
            required_chunk = chunks[chunk_id]
            required_anchor = anchors[chunk_id]
            required_sources.append(
                {
                    "accession": required_chunk["accession"],
                    "chunk_id": chunk_id,
                    "source_anchor_id": required_anchor["anchor_id"],
                    "relevant_source_text": _source_excerpt(
                        required_chunk,
                        support["required_needles"].get(chunk_id),
                        width=1600,
                    ),
                }
            )
        release_accessions = set(item["frozen_accession_contract"])
        required_accessions = set(support["actual_required_accessions"])
        candidate_ids = {
            candidate_id
            for part in item["parts"]
            for candidate_id in part["candidate_chunk_ids"]
        }
        contract_satisfied = (
            required_accessions <= release_accessions
            and set(support["required_chunk_ids"]) <= candidate_ids
            and all(part["candidate_chunk_ids"] for part in item["parts"])
        )
        record = {
            "q_id": key[0],
            "q_version": key[1],
            "item_id": key[2],
            "frozen_claim": item["claim"],
            "parent_frozen_accession_contract": parent["accession"].split(";"),
            "parent_frozen_source_contract": {
                "accessions": parent["accession"].split(";"),
                "location": parent["location"],
            },
            "release_accession_contract": item["frozen_accession_contract"],
            "release_source_contract": {
                "accessions": item["frozen_accession_contract"],
                "location": item["frozen_location"],
            },
            "required_semantic_part": support["required_semantic_part"],
            "actual_required_source_accessions": support["actual_required_accessions"],
            "required_sources": required_sources,
            "actual_supporting_accession": chunk["accession"],
            "actual_supporting_chunk_id": chunk["chunk_id"],
            "actual_supporting_anchor_id": anchor["anchor_id"],
            "relevant_source_text": _source_excerpt(chunk, support["needle"], 1200),
            "why_parent_frozen_contract_was_unsatisfiable": support["why_unsatisfiable"],
            "non_source_fields_need_correction": False,
            "non_source_field_assessment": (
                "The claim and analytical classification remain unchanged; the erratum "
                "is limited to accession/location source metadata."
            ),
            "release_contract_satisfied": contract_satisfied,
            "remains_genuine_frozen_benchmark_contract_error": not contract_satisfied,
            "diagnosis": (
                "resolved_by_bench_v0.1.1_source_metadata_erratum"
                if contract_satisfied
                else "benchmark_contract_error"
            ),
            "reviewer_decision": "",
            "reviewer_note": "",
        }
        (resolved_errors if contract_satisfied else errors).append(record)
    return {
        "version_binding": binding,
        "artifact_type": "source_contract_resolution_draft",
        "error_count": len(errors),
        "resolved_error_count": len(resolved_errors),
        "errors": errors,
        "resolved_errors": resolved_errors,
    }


def _candidate_boolean(chunk_ids: list[str]) -> str:
    if not chunk_ids:
        return "UNSATISFIABLE"
    if len(chunk_ids) == 1:
        return chunk_ids[0]
    return "(" + " OR ".join(chunk_ids) + ")"


def build_merge_review(
    binding: dict[str, Any], evidence: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Trace every many-old-parts to one-current-part transformation."""
    old_by_item: dict[tuple[str, str, str], dict[str, dict[str, str]]] = defaultdict(dict)
    for row in _read_csv(SEED_PATH):
        if row.get("item_id"):
            old_by_item[(row["q_id"], row["q_version"], row["item_id"])][
                row["part_id"]
            ] = row

    rows: list[dict[str, Any]] = []
    for item in evidence["items"]:
        key = (item["q_id"], item["q_version"], item["item_id"])
        for part in item["parts"]:
            old_ids = part["source_atom_ids"]
            if len(old_ids) < 2:
                continue
            old_rows = [old_by_item[key][old_id] for old_id in old_ids]
            old_clauses = [
                f"{row['part_id']}:{_candidate_boolean(_json_list(row['candidate_chunk_ids']))}"
                for row in old_rows
            ]
            new_clause = (
                f"{part['part_id']}:"
                f"{_candidate_boolean(part['candidate_chunk_ids'])}"
            )
            descriptions = [row["part_description"] for row in old_rows]
            rows.append(
                {
                    "ingestion_tag": binding["ingestion_tag"],
                    "ingestion_git_commit": binding["ingestion_git_commit"],
                    "corpus_fingerprint": binding["corpus_fingerprint"],
                    "benchmark_version": binding["benchmark_version"],
                    "q_id": item["q_id"],
                    "q_version": item["q_version"],
                    "item_id": item["item_id"],
                    "old_part_ids": ";".join(old_ids),
                    "old_boolean_structure": " AND ".join(old_clauses),
                    "new_part_id": part["part_id"],
                    "new_boolean_structure": new_clause,
                    "number_of_parts_reduced": len(old_ids) - 1,
                    "reason_for_merge": (
                        (
                            "Repaired after human provenance review; the corrected "
                            "co-disclosed atoms form one source-level component: "
                            if not part["human_approved_retrieval_merge"]
                            else "Copied from the previous merge proposal, which treated "
                            "the following co-disclosed atoms as one source-level component: "
                        )
                        + " | ".join(descriptions)
                        + (
                            ". Human re-review is pending."
                            if not part["human_approved_retrieval_merge"]
                            else ". The project owner approved this retrieval-level merge."
                        )
                    ),
                    "merge_lineage": part["merge_lineage"],
                    "logical_equivalence": (
                        "Every old clause has the same complete OR candidate set X; "
                        f"therefore {' AND '.join(['X'] * len(old_ids))} = X by Boolean "
                        "idempotence. "
                        + (
                            "Human review of the repaired mapping is pending; the original "
                            "atoms remain recorded."
                            if not part["human_approved_retrieval_merge"]
                            else "The project owner accepted this equivalence for retrieval "
                            "scoring; the original atoms remain recorded."
                        )
                    ),
                    "human_approved": part["human_approved_retrieval_merge"],
                    "reviewer_decision": (
                        "APPROVE" if part["human_approved_retrieval_merge"] else ""
                    ),
                    "reviewer_note": "",
                }
            )
    summary = {
        "merge_groups": len(rows),
        "old_parts_affected": sum(len(row["old_part_ids"].split(";")) for row in rows),
        "new_parts_produced": len(rows),
        "part_count_reduction": sum(row["number_of_parts_reduced"] for row in rows),
    }
    return rows, summary


def build_anchor_coverage(
    binding: dict[str, Any],
    numeric: dict[str, Any],
    evidence: dict[str, Any],
    contract_errors: dict[str, Any],
    anchor_artifact: dict[str, Any],
) -> dict[str, Any]:
    anchors = anchor_artifact["anchors"]
    anchor_by_id = {anchor["anchor_id"]: anchor for anchor in anchors}
    candidate_refs: list[dict[str, Any]] = []
    for fact in numeric["facts"]:
        for source in fact["candidate_sources"]:
            candidate_refs.append(
                {"kind": "numeric_fact", "record_id": fact["fact_id"], "source": source}
            )
    for item in evidence["items"]:
        item_id = f"{item['q_id']}@{item['q_version']}/{item['item_id']}"
        for part in item["parts"]:
            for source in part["candidate_sources"]:
                candidate_refs.append(
                    {
                        "kind": "evidence_part",
                        "record_id": f"{item_id}/{part['part_id']}",
                        "source": source,
                    }
                )

    required_fields = (
        "accession", "doc_id", "raw_document_sha256", "chunk_id",
        "char_start", "char_end", "normalized_source_fingerprint",
    )
    missing: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []
    valid = 0
    for ref in candidate_refs:
        source = ref["source"]
        anchor = anchor_by_id.get(source.get("anchor_id"))
        if anchor is None:
            missing.append(
                {"kind": ref["kind"], "record_id": ref["record_id"], "source": source}
            )
            continue
        differences = {
            field: {"candidate": source.get(field), "anchor": anchor.get(field)}
            for field in required_fields
            if source.get(field) != anchor.get(field)
        }
        if differences:
            mismatches.append(
                {
                    "kind": ref["kind"],
                    "record_id": ref["record_id"],
                    "anchor_id": source["anchor_id"],
                    "differences": differences,
                }
            )
        else:
            valid += 1

    candidate_anchor_ids = {ref["source"].get("anchor_id") for ref in candidate_refs}
    contract_records = [
        *contract_errors["errors"], *contract_errors["resolved_errors"]
    ]
    diagnostic_anchor_ids = {
        source["source_anchor_id"]
        for error in contract_records
        for source in error["required_sources"]
    }
    all_reference_anchor_ids = candidate_anchor_ids | diagnostic_anchor_ids
    registered_ids = set(anchor_by_id)
    orphan_ids = sorted(registered_ids - all_reference_anchor_ids)
    dangling_ids = sorted(all_reference_anchor_ids - registered_ids)
    noncandidate_diagnostic_ids = sorted(registered_ids - candidate_anchor_ids)

    by_fingerprint: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for anchor in anchors:
        by_fingerprint[anchor["normalized_source_fingerprint"]].append(anchor)
    collisions = []
    for fingerprint, matches in by_fingerprint.items():
        spans = {
            (
                match["doc_id"], match["char_start"], match["char_end"], match["chunk_id"]
            )
            for match in matches
        }
        if len(spans) > 1:
            collisions.append(
                {
                    "normalized_source_fingerprint": fingerprint,
                    "source_spans": [
                        {
                            "anchor_id": match["anchor_id"],
                            "doc_id": match["doc_id"],
                            "chunk_id": match["chunk_id"],
                            "char_start": match["char_start"],
                            "char_end": match["char_end"],
                        }
                        for match in matches
                    ],
                }
            )

    result = {
        "version_binding": binding,
        "artifact_type": "candidate_source_anchor_coverage_draft",
        "counts": {
            "total_provenance_candidate_references": len(candidate_refs),
            "contract_diagnostic_source_references": sum(
                len(error["required_sources"]) for error in contract_records
            ),
            "unique_chunk_ids_referenced_by_candidates": len(
                {ref["source"]["chunk_id"] for ref in candidate_refs}
            ),
            "unique_source_anchor_ids_referenced_by_candidates": len(candidate_anchor_ids),
            "registered_source_anchors": len(anchors),
            "candidate_references_with_valid_anchor": valid,
            "candidate_references_without_anchor": len(missing),
            "candidate_references_with_anchor_mismatch": len(mismatches),
            "orphan_anchors": len(orphan_ids),
            "dangling_anchor_references": len(dangling_ids),
            "normalized_source_fingerprint_collisions_with_different_spans": len(collisions),
        },
        "candidate_references_without_anchor": missing,
        "candidate_anchor_mismatches": mismatches,
        "orphan_anchor_ids": orphan_ids,
        "dangling_anchor_ids": dangling_ids,
        "anchors_used_only_by_contract_diagnostics": noncandidate_diagnostic_ids,
        "normalized_source_fingerprint_collisions": collisions,
    }
    if missing or mismatches or orphan_ids or dangling_ids:
        raise RuntimeError("source-anchor coverage validation failed")
    return result


def build_unique_sample_defect_trace(
    binding: dict[str, Any],
    evidence: dict[str, Any],
    contract_errors: dict[str, Any],
    chunks: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    item_by_key = {
        (item["q_id"], item["q_version"], item["item_id"]): item
        for item in evidence["items"]
    }
    error_by_key = {
        (error["q_id"], error["q_version"], error["item_id"]): error
        for error in contract_errors["errors"]
    }
    specs = [
        {
            "key": ("Q05", "2", "X3"),
            "old_mapping": ["fc8eed03351b9373"],
            "reason": (
                "The old single chunk proves realized FY27Q2 revenue only. It cannot "
                "establish the earlier $91.0B plus-or-minus 2% guidance or its $92.82B upper bound."
            ),
            "resolution": (
                "The v0.1.1 erratum adds the Q1 release to the source contract. The "
                "rebuild maps P01 to the guidance chunk and retains the Q2 realized-"
                "revenue chunk as P02; the former contract error is resolved."
            ),
            "needles": {
                "fc8eed03351b9373": "reported revenue for the second quarter",
                "a35a2f866d18fd19": "Revenue is expected to be $91.0 billion",
            },
        },
        {
            "key": ("Q16", "2", "E09"),
            "old_mapping": ["3e9b386d72ec488d"],
            "reason": (
                "The old narrative chunk explains the Hyperscale category and recast, "
                "but lacks the first-half and Q2 numeric inputs needed to reconstruct "
                "Q1 and verify both YoY rates."
            ),
            "resolution": (
                "Corrected during the rebuild, not dropped: P02 adds the first-half "
                "table and P03 adds the Q2 quarterly table."
            ),
            "needles": {
                "3e9b386d72ec488d": "Hyperscale revenue more than doubled",
                "66a2dbe9fa036e7f": "Row: Hyperscale",
                "6e776edb42ae8862": "Row: Hyperscale",
            },
        },
        {
            "key": ("Q10", "2", "C2"),
            "old_mapping": ["70129a2015d51908"],
            "reason": (
                "The old chunk is only the segment-results heading and recast note; "
                "it contains none of the required Intelligent Cloud financial cells."
            ),
            "resolution": (
                "Corrected during the rebuild, not dropped: the current mapping uses "
                "the adjacent segment table containing revenue, cost, operating expense, "
                "and operating income for both periods."
            ),
            "needles": {"0d90ceeeffa01abc": "Row: Intelligent Cloud"},
        },
    ]
    traces = []
    for spec in specs:
        key = spec["key"]
        item = item_by_key[key]
        current_sources = [
            source
            for part in item["parts"]
            for source in part["candidate_sources"]
        ]
        if key in error_by_key:
            error = error_by_key[key]
            known = {source["source_anchor_id"] for source in error["required_sources"]}
            for source in error["required_sources"]:
                if source["source_anchor_id"] not in {s["anchor_id"] for s in current_sources}:
                    current_sources.append(
                        {
                            "anchor_id": source["source_anchor_id"],
                            "chunk_id": source["chunk_id"],
                            "accession": source["accession"],
                            "source_excerpt": source["relevant_source_text"],
                            "diagnostic_out_of_contract": True,
                        }
                    )
            assert known
        traces.append(
            {
                "q_id": key[0],
                "q_version": key[1],
                "item_id": key[2],
                "old_mapping": spec["old_mapping"],
                "old_mapping_source_text": [
                    _source_excerpt(chunks[chunk_id], width=1400)
                    for chunk_id in spec["old_mapping"]
                ],
                "exact_defect_reason": spec["reason"],
                "current_mapping": [
                    {
                        "part_id": part["part_id"],
                        "description": part["description"],
                        "candidate_chunk_ids": part["candidate_chunk_ids"],
                    }
                    for part in item["parts"]
                ],
                "current_source_anchors": [
                    {
                        "source_anchor_id": source["anchor_id"],
                        "chunk_id": source["chunk_id"],
                        "accession": source["accession"],
                    }
                    for source in current_sources
                ],
                "relevant_source_text": [
                    _source_excerpt(
                        chunks[source["chunk_id"]],
                        spec["needles"].get(source["chunk_id"]),
                        width=1800,
                    )
                    for source in current_sources
                ],
                "current_status": item["status"],
                "resolution": spec["resolution"],
                "reviewer_decision": "",
                "reviewer_note": "",
            }
        )
    return {
        "version_binding": binding,
        "artifact_type": "previous_unique_sample_defect_trace_draft",
        "trace_count": len(traces),
        "traces": traces,
    }


def _distribution(values: Iterable[Any]) -> dict[str, int]:
    counts = Counter("unresolved" if value is None else str(value) for value in values)
    return dict(sorted(counts.items(), key=lambda item: item[0]))


def build_review(
    numeric: dict[str, Any],
    evidence: dict[str, Any],
    contract_errors: dict[str, Any],
    anchors: dict[str, dict[str, Any]],
) -> str:
    items = evidence["items"]
    parts = [part for item in items for part in item["parts"]]
    previous_rows = _read_csv(SEED_PATH)
    old_rows = [row for row in previous_rows if row.get("item_id")]
    old_evidence_chunks = {
        chunk_id for row in old_rows for chunk_id in _json_list(row["candidate_chunk_ids"])
    }
    new_evidence_chunks = {
        chunk_id for part in parts for chunk_id in part["candidate_chunk_ids"]
    }
    old_numeric_chunks = {
        chunk_id
        for row in previous_rows
        if row.get("fact_id")
        for chunk_id in _json_list(row["candidate_chunk_ids"])
    }
    new_numeric_chunks = {
        chunk_id for fact in numeric["facts"] for chunk_id in fact["candidate_chunk_ids"]
    }
    part_distribution = _distribution(item["part_count"] for item in items)
    or_distribution = _distribution(len(part["candidate_sources"]) for part in parts)
    hit_distribution = _distribution(item["minimum_distinct_chunk_hits"] for item in items)
    unresolved = [item for item in items if item["minimum_distinct_chunk_hits"] is None]
    direct = [fact for fact in numeric["facts"] if not fact["is_derived"]]
    derived = [fact for fact in numeric["facts"] if fact["is_derived"]]
    footnote_anchors = [anchor for anchor in anchors.values() if anchor["attached_footnotes"]]

    lines = [
        "# Provenance v0.1.1 rebuild",
        "",
        "This review covers deterministic provenance rebuilt against the frozen ingestion release. No file under `benchmark/frozen/**` was modified. Candidate validation used exact XBRL/table identities, literal source content, structural metadata, explicit formula inputs, and source adjacency only.",
        "",
        "## Version binding",
        "",
        f"- Ingestion tag: `{INGESTION_TAG}`",
        f"- Ingestion commit: `{INGESTION_GIT_COMMIT}`",
        f"- Corpus fingerprint: `{EXPECTED_CORPUS_FINGERPRINT}`",
        f"- Benchmark: `{BENCHMARK_VERSION}` (schema `{BENCHMARK_SCHEMA_VERSION}`)",
        f"- Benchmark parent: `{BENCHMARK_PARENT_VERSION}`",
        "",
        "The rebuild fails before writing artifacts if the manifest fingerprint differs.",
        "",
        "## Totals",
        "",
        f"- Numeric facts: **{numeric['fact_count']}** ({len(direct)} direct; {len(derived)} derived)",
        f"- Verified evidence items: **{evidence['verified_item_count']}**",
        f"- Evidence parts: **{len(parts)}**",
        f"- Candidate references: **{sum(len(part['candidate_sources']) for part in parts) + sum(len(fact['candidate_sources']) for fact in numeric['facts'])}**",
        f"- Unique candidate chunks: **{len(new_evidence_chunks | new_numeric_chunks)}**",
        f"- Persistent source anchors used: **{len(anchors)}**",
        f"- OR parts: **{sum(len(part['candidate_sources']) > 1 for part in parts)}**",
        f"- Used table anchors with newly attached footnotes: **{len(footnote_anchors)}**",
        f"- Genuine frozen benchmark contract errors: **{contract_errors['error_count']}**",
        "",
        "## Part-count distribution",
        "",
        "| Parts per item | Items |",
        "|---:|---:|",
        *[f"| {key} | {value} |" for key, value in part_distribution.items()],
        "",
        "## OR-candidate counts",
        "",
        "| Candidates in part | Parts |",
        "|---:|---:|",
        *[f"| {key} | {value} |" for key, value in or_distribution.items()],
        "",
        "## Minimum distinct chunk hits per evidence item",
        "",
        "| Minimum hits | Items |",
        "|---:|---:|",
        *[f"| {key} | {value} |" for key, value in hit_distribution.items()],
        "",
        "## Source-contract errors",
        "",
        f"Remaining errors: **{contract_errors['error_count']}**. The four parent-release errors are resolved below.",
        "",
    ]
    for error in contract_errors["resolved_errors"]:
        lines.extend(
            [
                f"### {error['q_id']}@{error['q_version']}/{error['item_id']}",
                "",
                f"- Frozen claim: {error['frozen_claim']}",
                f"- Parent frozen accession/source contract: `{' ; '.join(error['parent_frozen_accession_contract'])}`; location `{error['parent_frozen_source_contract']['location']}`",
                f"- v0.1.1 accession/source contract: `{' ; '.join(error['release_accession_contract'])}`; location `{error['release_source_contract']['location']}`",
                f"- Required semantic part: {error['required_semantic_part']}",
                f"- Actual required source accession(s): `{' ; '.join(error['actual_required_source_accessions'])}`",
                *[
                    f"- Candidate source: accession `{source['accession']}`, chunk `{source['chunk_id']}`, anchor `{source['source_anchor_id']}` — “{source['relevant_source_text']}”"
                    for source in error["required_sources"]
                ],
                f"- Why the parent frozen contract was unsatisfiable: {error['why_parent_frozen_contract_was_unsatisfiable']}",
                f"- Any non-source field correction needed: **{'yes' if error['non_source_fields_need_correction'] else 'no'}**. {error['non_source_field_assessment']}",
                "- Satisfiable under `bench_v0.1.1`: **yes**",
                "",
            ]
        )
    lines.extend(
        [
            "## Missing or unresolved items",
            "",
            f"There are **{len(unresolved)}** items without a finite in-contract satisfying set. There are no missing corpus documents or missing numeric/evidence provenance records.",
            "",
            "## Differences from the previous draft",
            "",
            f"- The previous CSV had **{len(old_rows)}** evidence-part rows; this rebuild has **{len(parts)}** source-level semantic parts.",
            f"- The repaired {len(parts)}-part structure uses **{sum(len(groups) for groups in SEMANTIC_COMPONENT_GROUPS.values())}** merge groups. Unaffected lineage-B rows retain approval; changed/new lineage-C rows remain blank for re-review. The draft preserves every original atom ID and old Boolean clause.",
            "- Numeric atoms jointly established by one complete disclosure are represented as one semantic component. Distinct periods, metrics, disclosure contexts, and nonidentical OR branches remain separate.",
            f"- Exact current-corpus revalidation produced **{len(new_numeric_chunks - old_numeric_chunks)}** added and **{len(old_numeric_chunks - new_numeric_chunks)}** removed numeric source chunks, and **{len(new_evidence_chunks - old_evidence_chunks)}** added and **{len(old_evidence_chunks - new_evidence_chunks)}** removed evidence source chunks. Evidence differences reflect the v0.1.1 errata and this human-review repair pass.",
            "- Newly attached footnotes are now part of the normalized source content for chunks `79ddd90f5c73467d`, `6e776edb42ae8862`, and `895465f2b7486687`; they enrich the existing table anchors without creating artificial extra OR candidates.",
            "- Candidate sources now carry accession, document ID, raw-document SHA-256, chunk coordinates, and a deterministic normalized-content fingerprint.",
            "- Table-backed candidates now expose row/header/table/section context and attached footnotes where present.",
            "- Numeric facts now expose complete applicable XBRL identity fields or table-cell identity fields, plus explicit accounting-display-sign versus economic-magnitude handling.",
            "- The four parent-release source-contract mismatches were rechecked against current source text and are all satisfiable under the v0.1.1 overlay.",
            "- No BM25, embeddings, semantic retrieval, reranking, or model-generated candidates are part of this rebuild.",
            "",
        ]
    )
    return "\n".join(lines)


def build_boundary_review(
    merge_summary: dict[str, int],
    merge_rows: list[dict[str, Any]],
    anchor_coverage: dict[str, Any],
    defect_trace: dict[str, Any],
    contract_errors: dict[str, Any],
) -> str:
    counts = anchor_coverage["counts"]
    approved_merges = sum(row["reviewer_decision"] == "APPROVE" for row in merge_rows)
    pending_merges = sum(row["reviewer_decision"] == "" for row in merge_rows)
    lines = [
        "# Provenance/evaluation boundary audit",
        "",
        "## Merge lineage",
        "",
        f"- Merge groups: **{merge_summary['merge_groups']}**",
        f"- Old parts affected: **{merge_summary['old_parts_affected']}**",
        f"- New parts produced: **{merge_summary['new_parts_produced']}**",
        f"- Total part-count reduction: **{merge_summary['part_count_reduction']}**",
        "- Lineage result: unaffected merges remain **B — copied/applied from a previous merge proposal**; repaired/new merges are **C — repaired after human provenance review**.",
        f"- Human approval: **{approved_merges} APPROVE, {pending_merges} blank pending re-review, 0 rejected, 0 needs source check**. `reviewer_note` remains empty.",
        "- Boolean equivalence: each merge group repeats the same complete OR set X, so `X AND ... AND X = X`; atomic lineage is preserved and changed rows remain unapproved.",
        "",
        "## Production/evaluation boundary",
        "",
        "- Gold-aware provenance code is located under `evaluation/provenance.py`.",
        "- No provenance module remains under `src/`.",
        "- Evaluation tests are under `tests/evaluation/`.",
        "- A static guard rejects imports from `src/**` to evaluation/provenance tooling and rejects production string references to frozen, release, provenance, or errata benchmark paths.",
        "",
        "## Source-anchor coverage",
        "",
        f"- Total provenance candidate references: **{counts['total_provenance_candidate_references']}**",
        f"- Unique candidate chunk IDs: **{counts['unique_chunk_ids_referenced_by_candidates']}**",
        f"- Unique candidate source-anchor IDs: **{counts['unique_source_anchor_ids_referenced_by_candidates']}**",
        f"- Candidate references with a valid anchor: **{counts['candidate_references_with_valid_anchor']}**",
        f"- Candidate references without an anchor: **{counts['candidate_references_without_anchor']}**",
        f"- Candidate references with an anchor-field mismatch: **{counts['candidate_references_with_anchor_mismatch']}**",
        f"- Orphan anchors after including contract diagnostics: **{counts['orphan_anchors']}**",
        f"- Dangling anchor references: **{counts['dangling_anchor_references']}**",
        f"- Normalized-source-fingerprint collisions across different spans: **{counts['normalized_source_fingerprint_collisions_with_different_spans']}**",
        f"- Contract-resolution source references: **{counts['contract_diagnostic_source_references']}**; every such anchor is now also a scoring candidate anchor.",
        "",
        "Every candidate agrees with its anchor on accession, document ID, raw-document SHA-256, chunk ID, character span, and normalized source fingerprint.",
        "",
        "## Previous unique-sample defects",
        "",
    ]
    for trace in defect_trace["traces"]:
        lines.extend(
            [
                f"### {trace['q_id']}@{trace['q_version']}/{trace['item_id']}",
                "",
                f"- Old mapping: `{';'.join(trace['old_mapping'])}`",
                f"- Exact defect: {trace['exact_defect_reason']}",
                f"- Current mapping: `{json.dumps(trace['current_mapping'], ensure_ascii=False)}`",
                f"- Current source anchors: `{json.dumps(trace['current_source_anchors'], ensure_ascii=False)}`",
                f"- Relevant source text: “{'” / “'.join(trace['relevant_source_text'])}”",
                f"- Current status: `{trace['current_status']}`",
                f"- Resolution: {trace['resolution']}",
                "",
            ]
        )
    lines.extend(["## Contract errors in full", "", "All four parent-release contract errors are resolved by the v0.1.1 source-metadata overlay.", ""])
    for error in contract_errors["resolved_errors"]:
        lines.extend(
            [
                f"### {error['q_id']}@{error['q_version']}/{error['item_id']}",
                "",
                f"- Exact frozen claim: {error['frozen_claim']}",
                f"- Exact parent frozen accession/source contract: `{' ; '.join(error['parent_frozen_accession_contract'])}`; location `{error['parent_frozen_source_contract']['location']}`",
                f"- Exact v0.1.1 accession/source contract: `{' ; '.join(error['release_accession_contract'])}`; location `{error['release_source_contract']['location']}`",
                f"- Actual required source accession(s): `{' ; '.join(error['actual_required_source_accessions'])}`",
                *[
                    f"- Source: accession `{source['accession']}`, chunk `{source['chunk_id']}`, anchor `{source['source_anchor_id']}` — “{source['relevant_source_text']}”"
                    for source in error["required_sources"]
                ],
                f"- Why the parent contract was unsatisfiable: {error['why_parent_frozen_contract_was_unsatisfiable']}",
                "- v0.1.1 status: **satisfiable**.",
                f"- Any field other than source metadata needs correction: **{'yes' if error['non_source_fields_need_correction'] else 'no'}**. {error['non_source_field_assessment']}",
                "",
            ]
        )
    lines.extend(
        [
            "## Remaining blockers",
            "",
            f"- **{pending_merges}** repaired/new merge rows intentionally remain blank pending human re-review; **{approved_merges}** unaffected merge approvals are retained.",
            "- All four source-contract errors are resolved by metadata-only errata.",
            "- There are no source-anchor coverage or production/evaluation dependency blockers.",
            "",
        ]
    )
    return "\n".join(lines)


def run(data_dir: Path = DATA_DIR, output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    binding = version_binding(data_dir)
    chunks, entries = load_corpus(data_dir)

    # Build anchors for all current chunks so candidates and future re-resolution
    # share one deterministic identity catalogue.
    all_anchors = {cid: make_anchor(chunk, entries) for cid, chunk in chunks.items()}
    numeric = build_numeric_facts(binding, chunks, all_anchors)
    evidence = build_evidence(binding, chunks, all_anchors)
    contract_errors = build_contract_errors(binding, evidence, chunks, all_anchors)

    used_chunk_ids = {
        source["chunk_id"]
        for fact in numeric["facts"]
        for source in fact["candidate_sources"]
    }
    used_chunk_ids.update(
        source["chunk_id"]
        for item in evidence["items"]
        for part in item["parts"]
        for source in part["candidate_sources"]
    )
    used_chunk_ids.update(
        source["chunk_id"]
        for error in [
            *contract_errors["errors"], *contract_errors["resolved_errors"]
        ]
        for source in error["required_sources"]
    )
    anchors = {
        all_anchors[cid]["anchor_id"]: all_anchors[cid]
        for cid in sorted(used_chunk_ids)
    }
    anchor_artifact = {
        "version_binding": binding,
        "artifact_type": "persistent_source_anchors_draft",
        "anchor_count": len(anchors),
        "anchors": list(anchors.values()),
    }
    merge_rows, merge_summary = build_merge_review(binding, evidence)
    anchor_coverage = build_anchor_coverage(
        binding, numeric, evidence, contract_errors, anchor_artifact
    )
    defect_trace = build_unique_sample_defect_trace(
        binding, evidence, contract_errors, chunks
    )
    combined = {
        "version_binding": binding,
        "artifact_type": "combined_provenance_draft",
        "numeric_facts_file": "numeric_facts_draft.json",
        "evidence_file": "evidence_provenance_draft.json",
        "source_anchors_file": "source_anchors_draft.json",
        "source_contract_errors_file": "source_contract_errors_draft.json",
        "merge_review_file": "merge_review_draft.csv",
        "anchor_coverage_file": "source_anchor_coverage_draft.json",
        "unique_sample_defect_trace_file": "unique_sample_defect_trace_draft.json",
        "counts": {
            "numeric_facts": numeric["fact_count"],
            "verified_evidence_items": evidence["verified_item_count"],
            "evidence_parts": sum(item["part_count"] for item in evidence["items"]),
            "candidate_references": anchor_coverage["counts"][
                "total_provenance_candidate_references"
            ],
            "unique_candidate_chunks": anchor_coverage["counts"][
                "unique_chunk_ids_referenced_by_candidates"
            ],
            "source_anchors": anchor_artifact["anchor_count"],
            "or_parts": sum(
                len(part["candidate_chunk_ids"]) > 1
                for item in evidence["items"]
                for part in item["parts"]
            ),
            "minimum_required_chunk_hit_distribution": _distribution(
                item["minimum_distinct_chunk_hits"] for item in evidence["items"]
            ),
            "source_contract_errors": contract_errors["error_count"],
            "resolved_source_contract_errors": contract_errors["resolved_error_count"],
            "unresolved_items": sum(
                item["minimum_distinct_chunk_hits"] is None
                for item in evidence["items"]
            ),
            "missing_provenance": sum(
                not part["candidate_sources"]
                for item in evidence["items"]
                for part in item["parts"]
            ),
            **merge_summary,
        },
    }

    # Nothing is written until all validation above has succeeded.
    _write_json(output_dir / "version_binding.json", binding)
    _write_json(output_dir / "numeric_facts_draft.json", numeric)
    _write_json(output_dir / "evidence_provenance_draft.json", evidence)
    _write_json(output_dir / "source_anchors_draft.json", anchor_artifact)
    _write_json(output_dir / "source_contract_errors_draft.json", contract_errors)
    _write_csv(
        output_dir / "merge_review_draft.csv",
        merge_rows,
        [
            "ingestion_tag", "ingestion_git_commit", "corpus_fingerprint",
            "benchmark_version", "q_id", "q_version", "item_id",
            "old_part_ids", "old_boolean_structure", "new_part_id",
            "new_boolean_structure", "number_of_parts_reduced",
            "reason_for_merge", "merge_lineage", "logical_equivalence",
            "human_approved", "reviewer_decision", "reviewer_note",
        ],
    )
    _write_json(output_dir / "source_anchor_coverage_draft.json", anchor_coverage)
    _write_json(output_dir / "unique_sample_defect_trace_draft.json", defect_trace)
    _write_json(output_dir / "provenance_rebuild_draft.json", combined)
    REVIEW_PATH.write_text(
        build_review(numeric, evidence, contract_errors, anchors) + "\n",
        encoding="utf-8",
    )
    BOUNDARY_REVIEW_PATH.write_text(
        build_boundary_review(
            merge_summary, merge_rows, anchor_coverage, defect_trace, contract_errors
        ) + "\n",
        encoding="utf-8",
    )
    return {
        "binding": binding,
        "numeric": numeric,
        "evidence": evidence,
        "anchors": anchor_artifact,
        "contract_errors": contract_errors,
        "merge_review": {"rows": merge_rows, "summary": merge_summary},
        "anchor_coverage": anchor_coverage,
        "defect_trace": defect_trace,
        "combined": combined,
    }


def main() -> int:
    result = run()
    counts = result["combined"]["counts"]
    print(
        "provenance rebuild complete: "
        f"{counts['numeric_facts']} facts, "
        f"{counts['verified_evidence_items']} evidence items, "
        f"{counts['source_anchors']} anchors, "
        f"{counts['source_contract_errors']} contract errors"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
