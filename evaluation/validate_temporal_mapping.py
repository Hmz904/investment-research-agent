"""Corpus-only pseudo-target selection and validation for temporal v0.2."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from evaluation.temporal_context_catalog import (
    NEEDS_HUMAN_CLOSED_SET,
    RESOLVED_ANCHOR_METADATA,
    canonical_json_bytes,
    fact_temporal,
    resolve_target_temporal,
)
from evaluation.xbrl_mapping import (
    SOURCE_CHECK_PASS,
    SOURCE_CHECK_UNRESOLVED,
    apply_source_checks,
    generate_stage1,
    generate_stage2,
    generate_stage3,
    raw_xbrl_unit_label,
)
from src.tools.xbrl_tool import XBRLTool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = PROJECT_ROOT / "evaluation" / "xbrl" / "temporal_context_catalog_v0.1.json"
OUTPUT_DIR = PROJECT_ROOT / "evaluation" / "xbrl"
SELECTION_PATH = OUTPUT_DIR / "temporal_pseudo_target_selection_v0.2.json"
VALIDATION_PATH = OUTPUT_DIR / "temporal_pseudo_target_validation_v0.2.json"
SELECTION_VERSION = "pseudo_target_selection_v0.2"
VALIDATION_VERSION = "temporal_pseudo_target_validation_v0.2"

RAW_TO_TARGET_UNIT = {
    "USD": "USD", "shares": "shares", "USD/shares": "USD_per_share", "pure": "pure",
}


def _temporal(fact: Mapping[str, Any]) -> dict[str, str]:
    result = fact_temporal(fact)
    if result is None:
        raise ValueError("pseudo fact lacks exact temporal metadata")
    return result


def _key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _dimensions(fact: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((item["axis"], item["member"]) for item in (fact.get("dimensions") or [])))


def _eligible(fact: Mapping[str, Any], *, chunk: bool = False) -> bool:
    return (
        fact.get("normalized_value") is not None
        and raw_xbrl_unit_label(fact) in RAW_TO_TARGET_UNIT
        and fact_temporal(fact) is not None
        and (not chunk or bool(fact.get("chunk_id")))
    )


def _summary(fact: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "stable_fact_id": fact["stable_fact_id"], "fact_locator": fact["fact_locator"],
        "accession": fact["accession"], "company": fact["company"], "cik": fact["cik"],
        "concept": fact["concept"], "context_ref": fact["context_ref"],
        "normalized_value": fact["normalized_value"], "raw_unit_label": raw_xbrl_unit_label(fact),
        "temporal": _temporal(fact), "dimensions": fact["dimensions"], "chunk_id": fact.get("chunk_id"),
    }


def _first_unused(candidates: Sequence[Any], used: set[str], locators: Any) -> tuple[Any | None, bool]:
    if not candidates:
        return None, False
    for candidate in candidates:
        identities = set(locators(candidate))
        if not identities & used:
            used.update(identities)
            return candidate, False
    candidate = candidates[0]
    used.update(locators(candidate))
    return candidate, True


def _target(
    target_id: str, fact: Mapping[str, Any], *, chunks: list[str], temporal: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    raw_unit = raw_xbrl_unit_label(fact)
    return {
        "target_id": target_id,
        "entity_company": fact["company"],
        "gold_value": fact["normalized_value"],
        "gold_unit": RAW_TO_TARGET_UNIT[raw_unit],
        "precision": {"rule_id": "precision_exact_v0.1", "comparison_gold_value": fact["normalized_value"]},
        "gold_xbrl_concept": fact["concept"],
        "approved_chunk_ids": chunks,
        "source_accessions": [fact["accession"]],
        "temporal_requirement": dict(temporal) if temporal else {"kind": "unresolved"},
        "dimensional_requirement": {"availability": "exact", "dimensions": fact["dimensions"] or []},
        "stage3_eligible_accessions": [fact["accession"]],
    }


def select_pseudo_targets(
    facts: Sequence[Mapping[str, Any]], catalog: Mapping[str, Any]
) -> dict[str, Any]:
    ordered = sorted(facts, key=lambda fact: fact["stable_fact_id"])
    used: set[str] = set()
    selections: list[dict[str, Any]] = []

    def add(category: str, selected: Any | None, reused: bool, rationale: str, gap: str = "COVERAGE_GAP") -> None:
        if selected is None:
            selections.append({"category": category, "selection_status": gap, "rationale": rationale, "facts": []})
            return
        selected_facts = list(selected) if isinstance(selected, tuple) else [selected]
        selections.append(
            {
                "category": category,
                "selection_status": "SELECTED_WITH_REUSE" if reused else "SELECTED",
                "rationale": rationale,
                "facts": [_summary(fact) for fact in selected_facts],
            }
        )

    a = [fact for fact in ordered if _eligible(fact, chunk=True)]
    selected, reused = _first_unused(a, used, lambda fact: [fact["fact_locator"]])
    add("A_DIRECT_CHUNK_LINKED", selected, reused, "First exact-context numeric fact with authoritative chunk linkage.")

    selected, reused = _first_unused([fact for fact in a if fact.get("dimensions")], used, lambda fact: [fact["fact_locator"]])
    add("B_DIMENSIONAL_SEGMENT", selected, reused, "First chunk-linked fact with a nonempty complete dimension set.")

    comparative = [
        fact for fact in a
        if (_temporal(fact).get("period_end") or _temporal(fact).get("instant")) < str(fact.get("period_of_report") or "")
    ]
    selected, reused = _first_unused(comparative, used, lambda fact: [fact["fact_locator"]])
    add("C_COMPARATIVE_CONTEXT", selected, reused, "First exact context ending before the filing period of report.")

    duplicate_groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for fact in ordered:
        if _eligible(fact):
            duplicate_groups[(fact["company"], fact["concept"], _key(_temporal(fact)), _dimensions(fact), raw_xbrl_unit_label(fact), fact["normalized_value"])].append(fact)
    pairs: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    for group in duplicate_groups.values():
        for left in group:
            if not left.get("chunk_id"):
                continue
            right = next((item for item in group if item["accession"] != left["accession"]), None)
            if right:
                pairs.append((left, right))
                break
    pairs.sort(key=lambda pair: (pair[0]["stable_fact_id"], pair[1]["stable_fact_id"]))
    selected, reused = _first_unused(pairs, used, lambda pair: [item["fact_locator"] for item in pair])
    add("D_STAGE2_CROSS_FILING_DUPLICATE", selected, reused, "First exact cross-filing duplicate under Stage-2 predicates.")

    anchor_temporals: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for fact in ordered:
        if fact.get("chunk_id") and fact_temporal(fact) is not None:
            anchor_temporals[(fact["company"], fact["chunk_id"], fact["concept"])].add(_key(_temporal(fact)))
    e = [
        fact for fact in a
        if len(anchor_temporals[(fact["company"], fact["chunk_id"], fact["concept"])]) == 1
    ]
    selected, reused = _first_unused(e, used, lambda fact: [fact["fact_locator"]])
    add("E_EXACT_ANCHOR_TEMPORAL_RESOLUTION", selected, reused, "First exact-concept chunk anchor with one authoritative XBRL temporal object.")

    structural: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for fact in ordered:
        if _eligible(fact):
            structural[(fact["company"], _key(_temporal(fact)), _dimensions(fact), RAW_TO_TARGET_UNIT[raw_xbrl_unit_label(fact)], fact["normalized_value"])].append(fact)
    f_pairs: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    for group in structural.values():
        for left in group:
            right = next((item for item in group if item["concept"] != left["concept"]), None)
            if right:
                f_pairs.append((left, right))
                break
    f_pairs.sort(key=lambda pair: (pair[0]["stable_fact_id"], pair[1]["stable_fact_id"]))
    selected, reused = _first_unused(f_pairs, used, lambda pair: [item["fact_locator"] for item in pair])
    add("F_STAGE3_DIFFERENT_CONCEPT", selected, reused, "First natural different-concept pair sharing all mechanical Stage-3 predicates.")

    durations: dict[tuple[str, str], dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for fact in ordered:
        if _eligible(fact) and fact.get("period_type") == "duration":
            durations[(fact["company"], str(fact["period_end"]))].setdefault(str(fact["period_start"]), fact)
    g_pairs = [tuple(group[start] for start in sorted(group)[:2]) for _, group in sorted(durations.items()) if len(group) >= 2]
    selected, reused = _first_unused(g_pairs, used, lambda pair: [item["fact_locator"] for item in pair])
    add("G_COMPARATIVE_DURATIONS", selected, reused, "First same-end pair with distinct exact duration starts.")

    selected, reused = _first_unused([fact for fact in a if fact["period_type"] == "instant"], used, lambda fact: [fact["fact_locator"]])
    add("H_INSTANT", selected, reused, "First chunk-linked numeric instant fact.")

    # With no approved chunk, an eligible exact-context fact is structurally
    # absent from Stage 1 and is itself guaranteed to satisfy the frozen
    # Stage-3 predicates in its source accession. Validation executes that
    # consequence below; selection does not inspect the candidate outcome.
    i_candidates = [fact for fact in ordered if _eligible(fact) and fact.get("dimensions")]
    selected, reused = _first_unused(i_candidates, used, lambda fact: [fact["fact_locator"]])
    add(
        "I_DIMENSIONAL_STAGE3", selected, reused,
        "First dimensioned exact-context fact for which Stage 1 is empty and Stage 3 executes.",
        "COVERAGE_GAP_NO_NATURAL_DIMENSIONAL_STAGE3_CASE",
    )

    return {
        "schema_version": SELECTION_VERSION,
        "selection_algorithm_version": SELECTION_VERSION,
        "selection_spec": "evaluation/xbrl/pseudo_target_selection_spec_v0.2.md",
        "input_temporal_catalog_sha256": hashlib.sha256(canonical_json_bytes(catalog)).hexdigest(),
        "input_xbrl_artifact_fingerprint": catalog["xbrl_artifact_fingerprint"],
        "benchmark_inputs_used": False,
        "agent_outputs_used": False,
        "selections": selections,
    }


def _checks(candidates: Sequence[Mapping[str, Any]], source: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    output: dict[str, dict[str, str]] = {}
    for candidate in candidates:
        exact = candidate["fact_locator"] == source["fact_locator"]
        same_concept = candidate["fact"]["concept"] == source["concept"]
        status = SOURCE_CHECK_PASS if exact or (candidate["candidate_stage"] in {2, 3} and same_concept) else SOURCE_CHECK_UNRESOLVED
        output[candidate["candidate_id"]] = {
            "source_check_status": status,
            "source_check_rationale": (
                "Exact source identity or exact-concept duplicate validates the synthetic fixture; no human approval is inferred."
                if status == SOURCE_CHECK_PASS
                else "Equal value/date/unit with a different concept does not prove semantic identity."
            ),
            "source_check_evidence": source["fact_locator"],
        }
    return output


def _closed_set_fixture(catalog: Mapping[str, Any], facts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in catalog["rows"]:
        for chunk_id in row["source_metadata_identities"].get("chunk_ids", []):
            groups[(row["entity"], chunk_id)].append(row)
    for (entity, chunk_id), rows in sorted(groups.items()):
        temporal_count = len({_key(row["temporal"]) for row in rows})
        if temporal_count < 2:
            continue
        result = resolve_target_temporal(
            {
                "target_id": "PSEUDO_CLOSED_SET",
                "entity_company": entity,
                "approved_chunk_ids": [chunk_id],
                "source_accessions": sorted({row["accession"] for row in rows}),
                "temporal_requirement": {"kind": "unresolved"},
                "gold_xbrl_concept": None,
            },
            catalog,
            facts,
        )
        if result["temporal_resolution_status"] == NEEDS_HUMAN_CLOSED_SET:
            return {
                "validation_status": "EXECUTED",
                "temporal_resolution_status": result["temporal_resolution_status"],
                "candidate_ids": [
                    item["temporal_candidate_id"] for item in result["candidate_rows"]
                ],
                "human_fields_blank": True,
            }
    return {"validation_status": "COVERAGE_GAP", "candidate_ids": [], "human_fields_blank": True}


def run_validation(
    selection: Mapping[str, Any], facts: Sequence[Mapping[str, Any]], catalog: Mapping[str, Any]
) -> dict[str, Any]:
    by_locator = {fact["fact_locator"]: fact for fact in facts}
    results: list[dict[str, Any]] = []
    for item in selection["selections"]:
        category = item["category"]
        if not item["selection_status"].startswith("SELECTED"):
            results.append({"category": category, "validation_status": item["selection_status"], "targets": []})
            continue
        selected = [by_locator[fact["fact_locator"]] for fact in item["facts"]]
        sources = selected if category == "G_COMPARATIVE_DURATIONS" else [selected[0]]
        target_results: list[dict[str, Any]] = []
        for index, source in enumerate(sources, 1):
            chunks = [] if category in {"F_STAGE3_DIFFERENT_CONCEPT", "I_DIMENSIONAL_STAGE3"} else ([source["chunk_id"]] if source.get("chunk_id") else [])
            target = _target(f"PSEUDO_{category}_{index}", source, chunks=chunks, temporal=None if category == "E_EXACT_ANCHOR_TEMPORAL_RESOLUTION" else _temporal(source))
            resolution = resolve_target_temporal(target, catalog, facts)
            if resolution["temporal_resolution_status"] == RESOLVED_ANCHOR_METADATA:
                target["temporal_requirement"] = resolution["resolved_temporal"]
            stage1 = generate_stage1(target, facts)
            stage1 = apply_source_checks(stage1, _checks(stage1, source))
            stage2 = generate_stage2(target, facts, stage1)
            stage2 = apply_source_checks(stage2, _checks(stage2, source))
            stage3, state = generate_stage3(target, facts, stage1 + stage2)
            stage3 = apply_source_checks(stage3, _checks(stage3, source))
            target_results.append(
                {
                    "pseudo_target_id": target["target_id"],
                    "source_fact_locator": source["fact_locator"],
                    "temporal_resolution_status": resolution["temporal_resolution_status"],
                    "temporal_resolution_mode": resolution["temporal_resolution_mode"],
                    "resolved_temporal_requirement": target["temporal_requirement"],
                    "stage1_candidates": stage1,
                    "stage2_candidates": stage2,
                    "stage3_candidates": stage3,
                    "stage3_state": state,
                    "dimension_requirement": target["dimensional_requirement"],
                }
            )
        results.append({"category": category, "validation_status": "EXECUTED", "targets": target_results})
    return {
        "schema_version": VALIDATION_VERSION,
        "validation_version": VALIDATION_VERSION,
        "selection_algorithm_version": selection["selection_algorithm_version"],
        "input_selection_sha256": hashlib.sha256(canonical_json_bytes(selection)).hexdigest(),
        "benchmark_inputs_used": False,
        "agent_outputs_used": False,
        "closed_set_fallback_validation": _closed_set_fixture(catalog, facts),
        "results": results,
    }


def render_artifacts() -> dict[Path, bytes]:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    tool = XBRLTool.from_frozen_ingestion()
    facts = [fact.to_dict() for fact in tool._facts]
    selection = select_pseudo_targets(facts, catalog)
    validation = run_validation(selection, facts, catalog)
    return {SELECTION_PATH: canonical_json_bytes(selection), VALIDATION_PATH: canonical_json_bytes(validation)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = render_artifacts()
    if args.check:
        stale = [path for path, content in rendered.items() if not path.exists() or path.read_bytes() != content]
        if stale:
            raise SystemExit("stale temporal pseudo artifacts: " + ", ".join(str(path) for path in stale))
        return
    for path, content in rendered.items():
        path.write_bytes(content)


if __name__ == "__main__":
    main()
