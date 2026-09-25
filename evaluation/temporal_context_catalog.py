"""Benchmark-independent temporal catalog and fail-closed target resolver."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any, Mapping, Sequence


CATALOG_VERSION = "temporal_context_catalog_v0.1"
INGESTION_VERSION = "frozen_inline_xbrl_ingestion_v0.1.1"

DIRECTLY_OBSERVED_CONTEXT = "DIRECTLY_OBSERVED_CONTEXT"
DETERMINISTICALLY_DERIVED = "DETERMINISTICALLY_DERIVED"
MERGED_AGREEING_EVIDENCE = "MERGED_AGREEING_EVIDENCE"
TEMPORAL_EVIDENCE_TYPES = frozenset(
    {DIRECTLY_OBSERVED_CONTEXT, DETERMINISTICALLY_DERIVED, MERGED_AGREEING_EVIDENCE}
)

RESOLVED_EXACT_TARGET_DATE = "RESOLVED_EXACT_TARGET_DATE"
RESOLVED_ANCHOR_METADATA = "RESOLVED_ANCHOR_METADATA"
RESOLVED_HUMAN_CLOSED_SET = "RESOLVED_HUMAN_CLOSED_SET"
NEEDS_HUMAN_CLOSED_SET = "NEEDS_HUMAN_CLOSED_SET"
UNRESOLVED_NO_CANDIDATE = "UNRESOLVED_NO_CANDIDATE"
AMBIGUOUS_MACHINE_EVIDENCE = "AMBIGUOUS_MACHINE_EVIDENCE"

TEMPORAL_NO_ANCHOR_METADATA = "TEMPORAL_NO_ANCHOR_METADATA"
TEMPORAL_HUMAN_SELECT_NONE = "TEMPORAL_HUMAN_SELECT_NONE"
EVALUATOR_CANNOT_REPRESENT = "EVALUATOR_CANNOT_REPRESENT"
UNMAPPABLE_REASON_CODES = frozenset(
    {
        TEMPORAL_NO_ANCHOR_METADATA,
        TEMPORAL_HUMAN_SELECT_NONE,
        EVALUATOR_CANNOT_REPRESENT,
    }
)


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _row_id(identity: Any) -> str:
    return "TCR-" + _fingerprint(identity)[:16]


def _dimensions(value: Any) -> list[dict[str, str]]:
    if not value:
        return []
    return sorted(
        ({"axis": str(item["axis"]), "member": str(item["member"])} for item in value),
        key=lambda item: (item["axis"], item["member"]),
    )


def fact_temporal(fact: Mapping[str, Any]) -> dict[str, str] | None:
    if fact.get("period_type") == "instant" and fact.get("instant"):
        return {"kind": "instant", "instant": str(fact["instant"])}
    if fact.get("period_start") and fact.get("period_end"):
        return {
            "kind": "duration",
            "period_start": str(fact["period_start"]),
            "period_end": str(fact["period_end"]),
        }
    return None


def _cell_fact_temporal(fact: Mapping[str, Any]) -> dict[str, str] | None:
    instant = fact.get("instant_date") or fact.get("instant")
    if instant:
        return {"kind": "instant", "instant": str(instant)}
    if fact.get("period_start") and fact.get("period_end"):
        return {
            "kind": "duration",
            "period_start": str(fact["period_start"]),
            "period_end": str(fact["period_end"]),
        }
    return None


EXPLICIT_TABLE_PERIOD_SOURCES = frozenset({"header_explicit"})
INFERRED_TABLE_PERIOD_SOURCES = frozenset({"header", "xbrl_context"})
XBRL_TABLE_PERIOD_SOURCES = frozenset({"xbrl_fact"})


def classify_table_period_provenance(period_resolution_sources: Sequence[str]) -> str:
    sources = {str(item) for item in period_resolution_sources if item}
    if sources and sources <= EXPLICIT_TABLE_PERIOD_SOURCES:
        return "EXPLICIT_EXACT"
    if sources & (INFERRED_TABLE_PERIOD_SOURCES | XBRL_TABLE_PERIOD_SOURCES):
        return "INGESTION_DERIVED_OR_INFERRED"
    return "UNCLEAR"


def _table_temporal_object(period: Mapping[str, Any]) -> dict[str, str] | None:
    if period.get("instant_date"):
        return {"kind": "instant", "instant": str(period["instant_date"])}
    if period.get("period_start") and period.get("period_end"):
        start, end = str(period["period_start"]), str(period["period_end"])
        if start == end:
            return {"kind": "instant", "instant": end}
        return {"kind": "duration", "period_start": start, "period_end": end}
    return None


def table_temporal(
    period: Mapping[str, Any], period_resolution_sources: Sequence[str]
) -> tuple[dict[str, str] | None, str | None]:
    """Return only explicitly supported exact table time; never infer a start."""
    if classify_table_period_provenance(period_resolution_sources) != "EXPLICIT_EXACT":
        return None, None
    temporal = _table_temporal_object(period)
    if temporal is not None:
        return temporal, "table_cell_exact_period_v0.1"
    return None, None


def _table_evidence_contradicts(
    period: Mapping[str, Any], authoritative_temporal: Mapping[str, Any]
) -> bool:
    table_exact = _table_temporal_object(period)
    if table_exact is not None:
        return table_exact != dict(authoritative_temporal)
    endpoint = authoritative_temporal.get("instant") or authoritative_temporal.get("period_end")
    if period.get("period_end") and str(period["period_end"]) != str(endpoint):
        return True
    if period.get("period_start"):
        return str(period["period_start"]) != str(authoritative_temporal.get("period_start"))
    return False


def _filing_fields(entry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "entity": entry.get("company"),
        "cik": entry.get("cik"),
        "accession": entry.get("accession"),
        "form_type": entry.get("form"),
        "filing_date": entry.get("filing_date"),
        "period_of_report": entry.get("period_of_report"),
    }


def build_temporal_catalog(
    facts: Sequence[Mapping[str, Any]],
    manifest_entries: Sequence[Mapping[str, Any]],
    chunk_documents: Sequence[Mapping[str, Any]],
    *,
    xbrl_artifact_fingerprint: str,
    corpus_fingerprint: str,
    migrated_resolver_row_count: int = 0,
) -> dict[str, Any]:
    """Build exact context and table-period rows without benchmark inputs."""
    manifest_by_accession = {str(item["accession"]): item for item in manifest_entries}
    manifest_by_doc = {str(item["doc_id"]): item for item in manifest_entries}
    grouped_facts: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for fact in facts:
        temporal = fact_temporal(fact)
        if temporal is None or not fact.get("context_ref"):
            continue
        identity = (
            str(fact["accession"]),
            str(fact["context_ref"]),
            _canonical(temporal),
            _canonical(_dimensions(fact.get("dimensions"))),
        )
        grouped_facts[identity].append(fact)

    rows: list[dict[str, Any]] = []
    for identity in sorted(grouped_facts):
        items = sorted(grouped_facts[identity], key=lambda item: str(item["stable_fact_id"]))
        first = items[0]
        temporal = fact_temporal(first)
        assert temporal is not None
        entry = manifest_by_accession.get(str(first["accession"]), {})
        source = {
            "doc_id": first.get("doc_id"),
            "chunk_ids": sorted({str(item["chunk_id"]) for item in items if item.get("chunk_id")}),
            "context_refs": [str(first["context_ref"])],
            "fact_locators": [str(item["fact_locator"]) for item in items],
            "stable_fact_ids": [str(item["stable_fact_id"]) for item in items],
            "concepts": sorted({str(item["concept"]) for item in items}),
            "table_identity": None,
        }
        evidence = {"temporal": temporal, "dimensions": _dimensions(first.get("dimensions")), "source": source}
        rows.append(
            {
                "temporal_row_id": _row_id(["xbrl", *identity]),
                **_filing_fields(entry or first),
                "temporal": temporal,
                "context_ref": str(first["context_ref"]),
                "dimensions": _dimensions(first.get("dimensions")),
                "source_metadata_identities": source,
                "evidence_fingerprints": [_fingerprint(evidence)],
                "temporal_evidence_type": DIRECTLY_OBSERVED_CONTEXT,
                "generation_rule_id": "xbrl_context_exact_dates_v0.1",
                "ingestion_artifact_identity": INGESTION_VERSION,
            }
        )

    conflicts: list[dict[str, Any]] = []
    table_identities: set[str] = set()
    table_audit: dict[str, Any] = {
        "prior_table_cell_exact_period_rows": 0,
        "prior_table_cell_exact_period_classification": {
            "EXPLICIT_EXACT": 0,
            "INGESTION_DERIVED_OR_INFERRED": 0,
            "UNCLEAR": 0,
        },
        "prior_table_cell_exact_period_retained": 0,
        "prior_table_cell_exact_period_removed_fail_closed": 0,
        "prior_table_cell_exact_period_recoverable_via_xbrl_agreement": 0,
        "prior_month_only_authoritative_rows": 0,
        "prior_month_only_rows_removed": 0,
        "inferred_table_rows_preserved_by_xbrl_agreement": 0,
        "month_only_rows_preserved_by_xbrl_agreement": 0,
    }
    for document in sorted(chunk_documents, key=lambda item: (str(item.get("doc_id")), str(item.get("accession")))):
        entry = manifest_by_doc.get(str(document.get("doc_id")), manifest_by_accession.get(str(document.get("accession")), {}))
        for chunk in sorted(document.get("chunks", []), key=lambda item: str(item.get("chunk_id"))):
            table = chunk.get("table_json")
            if not table:
                continue
            cells: list[Mapping[str, Any]] = []
            for row_index, table_row in enumerate(table.get("rows", [])):
                for cell in table_row.get("cells", []):
                    if cell.get("parsed_value") is not None:
                        cells.append({**cell, "_row_index": row_index})
            by_column: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
            for cell in cells:
                by_column[int(cell["col"])].append(cell)
            for column in sorted(by_column):
                column_cells = by_column[column]
                period_candidates = [
                    {
                        "period_start": cell.get("period_start"),
                        "period_end": cell.get("period_end"),
                        "instant_date": cell.get("instant_date"),
                        "duration_months": cell.get("duration_months"),
                    }
                    for cell in column_cells
                ]
                encoded_periods = {_canonical(item) for item in period_candidates if any(item.values())}
                if len(encoded_periods) > 1:
                    conflicts.append(
                        {
                            "conflict_id": "TCF-" + _fingerprint([chunk.get("chunk_id"), column, sorted(encoded_periods)])[:16],
                            "accession": chunk.get("accession"),
                            "chunk_id": chunk.get("chunk_id"),
                            "table_column": column,
                            "reason": "conflicting frozen cell/header period metadata",
                            "evidence_fingerprint": _fingerprint(sorted(encoded_periods)),
                        }
                    )
                    continue
                if not encoded_periods:
                    continue
                period = json.loads(next(iter(encoded_periods)))
                period_resolution_sources = sorted(
                    {
                        str(cell.get("period_resolution_source"))
                        for cell in column_cells
                        if cell.get("period_resolution_source")
                    }
                )
                provenance_classification = classify_table_period_provenance(
                    period_resolution_sources
                )
                linked_facts = [fact for cell in column_cells for fact in (cell.get("xbrl_facts") or [])]
                linked_with_temporal = [
                    (fact, item)
                    for fact in linked_facts
                    for item in [_cell_fact_temporal(fact)]
                    if item is not None
                ]
                linked_temporals = {
                    _canonical(item) for _, item in linked_with_temporal
                }
                old_table_exact = _table_temporal_object(period)
                if not linked_temporals and old_table_exact is not None:
                    table_audit["prior_table_cell_exact_period_rows"] += 1
                    table_audit["prior_table_cell_exact_period_classification"][
                        provenance_classification
                    ] += 1
                month_only = bool(
                    period.get("period_end")
                    and period.get("duration_months") is not None
                    and not period.get("period_start")
                    and not period.get("instant_date")
                )
                if month_only and not linked_temporals:
                    table_audit["prior_month_only_authoritative_rows"] += 1
                    table_audit["prior_month_only_rows_removed"] += 1

                if len(linked_temporals) > 1:
                    conflicts.append(
                        {
                            "conflict_id": "TCF-" + _fingerprint(
                                ["linked_temporal", chunk.get("chunk_id"), column, sorted(linked_temporals)]
                            )[:16],
                            "accession": chunk.get("accession"),
                            "chunk_id": chunk.get("chunk_id"),
                            "table_column": column,
                            "reason": "linked XBRL contexts disagree on temporal object",
                            "evidence_fingerprint": _fingerprint(sorted(linked_temporals)),
                        }
                    )
                    continue
                dimension_sets = {
                    _canonical(_dimensions(fact.get("dimensions")))
                    for fact, _ in linked_with_temporal
                }
                if len(dimension_sets) > 1:
                    conflicts.append(
                        {
                            "conflict_id": "TCF-" + _fingerprint(
                                ["linked_dimensions", chunk.get("chunk_id"), column, sorted(dimension_sets)]
                            )[:16],
                            "accession": chunk.get("accession"),
                            "chunk_id": chunk.get("chunk_id"),
                            "table_column": column,
                            "reason": "linked XBRL contexts disagree on dimensions",
                            "evidence_fingerprint": _fingerprint(sorted(dimension_sets)),
                        }
                    )
                    continue

                if linked_temporals:
                    temporal = json.loads(next(iter(linked_temporals)))
                    if _table_evidence_contradicts(period, temporal):
                        conflicts.append(
                            {
                                "conflict_id": "TCF-" + _fingerprint(
                                    ["table_xbrl", chunk.get("chunk_id"), column, period, temporal]
                                )[:16],
                                "accession": chunk.get("accession"),
                                "chunk_id": chunk.get("chunk_id"),
                                "table_column": column,
                                "reason": "table period conflicts with linked XBRL context",
                                "evidence_fingerprint": _fingerprint([period, temporal]),
                            }
                        )
                        continue
                    evidence_type = MERGED_AGREEING_EVIDENCE
                    rule_id = "table_xbrl_agreement_v0.1"
                    if provenance_classification != "EXPLICIT_EXACT":
                        table_audit["inferred_table_rows_preserved_by_xbrl_agreement"] += 1
                    if month_only:
                        table_audit["month_only_rows_preserved_by_xbrl_agreement"] += 1
                else:
                    temporal, rule_id = table_temporal(period, period_resolution_sources)
                    if temporal is None or rule_id is None:
                        if old_table_exact is not None:
                            table_audit["prior_table_cell_exact_period_removed_fail_closed"] += 1
                        continue
                    evidence_type = DETERMINISTICALLY_DERIVED
                    table_audit["prior_table_cell_exact_period_retained"] += 1

                context_refs = sorted({str(fact.get("context_id")) for fact in linked_facts if fact.get("context_id")})
                dimensions = json.loads(next(iter(dimension_sets))) if len(dimension_sets) == 1 else []
                table_identity = {
                    "chunk_id": chunk.get("chunk_id"),
                    "table_column": column,
                    "column_label_fingerprint": _fingerprint([cell.get("column_label") for cell in column_cells]),
                    "row_indices": sorted({int(cell["_row_index"]) for cell in column_cells}),
                }
                identity = _canonical([chunk.get("accession"), table_identity, temporal, context_refs, dimensions])
                if identity in table_identities:
                    continue
                table_identities.add(identity)
                source = {
                    "doc_id": chunk.get("doc_id"),
                    "chunk_ids": [str(chunk.get("chunk_id"))],
                    "context_refs": context_refs,
                    "fact_locators": sorted(
                        {f"{chunk.get('doc_id')}#{fact.get('fact_id')}" for fact in linked_facts if fact.get("fact_id")}
                    ),
                    "stable_fact_ids": [],
                    "concepts": sorted({str(fact.get("concept")) for fact in linked_facts if fact.get("concept")}),
                    "table_identity": table_identity,
                    "period_resolution_sources": period_resolution_sources,
                    "period_resolution_context_ids": sorted(
                        {
                            str(cell.get("period_resolution_context_id"))
                            for cell in column_cells
                            if cell.get("period_resolution_context_id")
                        }
                    ),
                    "table_period_provenance_classification": provenance_classification,
                }
                evidence = {
                    "temporal": temporal,
                    "period_resolution_sources": period_resolution_sources,
                    "source": source,
                }
                rows.append(
                    {
                        "temporal_row_id": _row_id(["table", identity]),
                        **_filing_fields(entry or chunk),
                        "temporal": temporal,
                        "context_ref": context_refs[0] if len(context_refs) == 1 else None,
                        "dimensions": dimensions,
                        "source_metadata_identities": source,
                        "evidence_fingerprints": [_fingerprint(evidence)],
                        "temporal_evidence_type": evidence_type,
                        "generation_rule_id": rule_id,
                        "ingestion_artifact_identity": INGESTION_VERSION,
                    }
                )

    rows.sort(key=lambda row: row["temporal_row_id"])
    duplicate_ids = sorted(
        row_id for row_id, count in __import__("collections").Counter(row["temporal_row_id"] for row in rows).items() if count > 1
    )
    for row in rows:
        if row["temporal_evidence_type"] not in TEMPORAL_EVIDENCE_TYPES:
            raise ValueError("invalid temporal_evidence_type")
    return {
        "schema_version": CATALOG_VERSION,
        "catalog_version": CATALOG_VERSION,
        "artifact_status": "development; not frozen; no human approvals",
        "ingestion_artifact_identity": INGESTION_VERSION,
        "xbrl_artifact_fingerprint": xbrl_artifact_fingerprint,
        "corpus_fingerprint": corpus_fingerprint,
        "prohibited_inputs": [
            "benchmark_target_ids", "benchmark_period_labels", "benchmark_answer_values",
            "review_outcomes", "agent_outputs",
        ],
        "migrated_predecessor_summary": {
            "predecessor": "fiscal_period_resolution_v0.1",
            "predecessor_rows_recomputed_from_source": migrated_resolver_row_count,
            "predecessor_labels_not_carried_forward": True,
        },
        "rows": rows,
        "conflicts": sorted(conflicts, key=lambda item: item["conflict_id"]),
        "table_period_provenance_audit": table_audit,
        "duplicate_temporal_row_ids": duplicate_ids,
    }


def _exact_temporal_from_target(target: Mapping[str, Any]) -> dict[str, str] | None:
    exact = target.get("exact_temporal")
    if isinstance(exact, Mapping) and exact.get("kind") in {"instant", "duration"}:
        return dict(exact)
    requirement = target.get("temporal_requirement")
    if isinstance(requirement, Mapping) and requirement.get("kind") in {"instant", "duration"}:
        return dict(requirement)
    if target.get("instant"):
        return {"kind": "instant", "instant": str(target["instant"])}
    if target.get("period_start") and target.get("period_end"):
        return {
            "kind": "duration",
            "period_start": str(target["period_start"]),
            "period_end": str(target["period_end"]),
        }
    return None


def target_specific_candidate_rows(target: Mapping[str, Any], catalog: Mapping[str, Any]) -> list[dict[str, Any]]:
    entity = target.get("entity_company") or target.get("entity")
    chunk_ids = set(target.get("approved_chunk_ids") or ())
    accessions = set(target.get("source_accessions") or ())
    eligible: list[Mapping[str, Any]] = []
    for row in catalog["rows"]:
        if row.get("entity") != entity:
            continue
        source = row["source_metadata_identities"]
        row_chunks = set(source.get("chunk_ids") or ())
        if chunk_ids:
            if not (row_chunks & chunk_ids):
                continue
        elif accessions:
            if row.get("accession") not in accessions:
                continue
        else:
            continue
        eligible.append(row)
    by_temporal: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in sorted(eligible, key=lambda item: item["temporal_row_id"]):
        by_temporal[_canonical(row["temporal"])].append(row)
    candidates: list[dict[str, Any]] = []
    for temporal_key in sorted(by_temporal):
        agreeing = sorted(by_temporal[temporal_key], key=lambda item: item["temporal_row_id"])
        row_ids = [str(row["temporal_row_id"]) for row in agreeing]
        temporal = json.loads(temporal_key)
        candidate_id = "TCC-" + _fingerprint(
            [str(target.get("target_id", "")), temporal, row_ids]
        )[:16]
        source_identities = sorted(
            (row["source_metadata_identities"] for row in agreeing), key=_canonical
        )
        candidates.append(
            {
                "temporal_candidate_id": candidate_id,
                "contributing_temporal_row_ids": row_ids,
                "entity": agreeing[0].get("entity"),
                "accessions": sorted(
                    {str(row["accession"]) for row in agreeing if row.get("accession")}
                ),
                "temporal": temporal,
                "temporal_evidence_types": sorted(
                    {str(row["temporal_evidence_type"]) for row in agreeing}
                ),
                "generation_rule_ids": sorted(
                    {str(row["generation_rule_id"]) for row in agreeing}
                ),
                "source_identities": source_identities,
                "evidence_fingerprints": sorted(
                    {
                        str(fingerprint)
                        for row in agreeing
                        for fingerprint in row["evidence_fingerprints"]
                    }
                ),
            }
        )
    return candidates


def validate_reviewer_selection(selection: str, candidate_ids: Sequence[str]) -> str | None:
    if selection == "SELECT NONE":
        return None
    prefix = "SELECT "
    if not selection.startswith(prefix):
        raise ValueError("review decision must be SELECT <temporal_candidate_id> or SELECT NONE")
    candidate_id = selection[len(prefix):]
    if candidate_id not in set(candidate_ids):
        raise ValueError("reviewer selection is outside the frozen candidate set")
    return candidate_id


def validate_unmappable_reason_code(reason_code: str | None) -> None:
    if reason_code is not None and reason_code not in UNMAPPABLE_REASON_CODES:
        raise ValueError(f"invalid unmappable reason code: {reason_code!r}")


def resolve_target_temporal(
    target: Mapping[str, Any],
    catalog: Mapping[str, Any],
    facts: Sequence[Mapping[str, Any]],
    *,
    reviewer_selection: str | None = None,
) -> dict[str, Any]:
    """Apply exact target, approved anchor, then closed-set resolution."""
    exact = _exact_temporal_from_target(target)
    base = {
        "exact_target_dates_present": exact is not None,
        "approved_anchor_ids": {
            "chunk_ids": sorted(set(target.get("approved_chunk_ids") or ())),
            "accessions": sorted(set(target.get("source_accessions") or ())),
        },
        "human_readable_period_labels_used": False,
        "candidate_rows": [],
        "selected_temporal_candidate_id": "",
        "reviewer_rationale": "",
        "reviewer_identity": "",
        "reviewer_status": "",
        "unmappable_reason_code": None,
    }
    if exact is not None:
        return {
            **base,
            "temporal_resolution_status": RESOLVED_EXACT_TARGET_DATE,
            "temporal_resolution_mode": "EXACT_TARGET_DATE",
            "resolved_temporal": exact,
            "resolution_rule_id": "exact_target_date_priority_v0.1",
            "anchor_temporal_metadata_discovered": [],
            "unresolved_reason": None,
        }

    entity = target.get("entity_company") or target.get("entity")
    chunks = set(target.get("approved_chunk_ids") or ())
    accessions = set(target.get("source_accessions") or ())
    concept = target.get("gold_xbrl_concept")
    linked = []
    if concept and (chunks or accessions):
        for fact in facts:
            if fact.get("company") != entity or fact.get("concept") != concept:
                continue
            if chunks and fact.get("chunk_id") not in chunks:
                continue
            if not chunks and accessions and fact.get("accession") not in accessions:
                continue
            temporal = fact_temporal(fact)
            if temporal is not None:
                linked.append((fact, temporal))
    linked_temporals = {_canonical(temporal) for _, temporal in linked}
    if len(linked_temporals) == 1:
        temporal = json.loads(next(iter(linked_temporals)))
        metadata = [
            {
                "fact_locator": fact.get("fact_locator"),
                "context_ref": fact.get("context_ref"),
                "temporal": item,
                "evidence_fingerprint": _fingerprint([fact.get("stable_fact_id"), item]),
            }
            for fact, item in sorted(linked, key=lambda pair: str(pair[0].get("stable_fact_id")))
        ]
        return {
            **base,
            "temporal_resolution_status": RESOLVED_ANCHOR_METADATA,
            "temporal_resolution_mode": "ANCHOR_XBRL_CONTEXT",
            "resolved_temporal": temporal,
            "resolution_rule_id": "approved_chunk_exact_concept_context_v0.1",
            "anchor_temporal_metadata_discovered": metadata,
            "unresolved_reason": None,
        }
    candidates = target_specific_candidate_rows(target, catalog)
    linked_conflict = len(linked_temporals) > 1
    if linked_conflict:
        base["candidate_rows"] = candidates
        if not candidates:
            return {
                **base,
                "temporal_resolution_status": AMBIGUOUS_MACHINE_EVIDENCE,
                "temporal_resolution_mode": None,
                "resolved_temporal": None,
                "resolution_rule_id": "approved_chunk_exact_concept_context_v0.1",
                "anchor_temporal_metadata_discovered": [
                    json.loads(item) for item in sorted(linked_temporals)
                ],
                "unresolved_reason": (
                    "approved exact-concept anchor links to conflicting exact XBRL periods, "
                    "and no catalog row is available for closed-set adjudication"
                ),
            }
        # Multiple authoritative exact contexts cannot silently make target
        # temporal truth.  They proceed through the same precomputed catalog
        # closed set as every other unresolved anchor.
        if reviewer_selection is None:
            return {
                **base,
                "temporal_resolution_status": NEEDS_HUMAN_CLOSED_SET,
                "temporal_resolution_mode": None,
                "resolved_temporal": None,
                "resolution_rule_id": "target_specific_closed_candidate_set_v0.1",
                "anchor_temporal_metadata_discovered": [
                    json.loads(item) for item in sorted(linked_temporals)
                ],
                "unresolved_reason": (
                    "multiple authoritative exact-concept contexts remain; "
                    "human selection is restricted to the precomputed closed set"
                ),
            }

    table_candidates = [
        item
        for item in candidates
        if any(source.get("table_identity") for source in item["source_identities"])
    ]
    table_temporals = {_canonical(item["temporal"]) for item in table_candidates}
    if not linked_conflict and len(table_temporals) == 1:
        temporal = json.loads(next(iter(table_temporals)))
        return {
            **base,
            "temporal_resolution_status": RESOLVED_ANCHOR_METADATA,
            "temporal_resolution_mode": "ANCHOR_TABLE_PERIOD",
            "resolved_temporal": temporal,
            "resolution_rule_id": "approved_chunk_unique_table_period_v0.1",
            "anchor_temporal_metadata_discovered": table_candidates,
            "unresolved_reason": None,
        }
    base["candidate_rows"] = candidates
    if not candidates:
        return {
            **base,
            "temporal_resolution_status": UNRESOLVED_NO_CANDIDATE,
            "temporal_resolution_mode": None,
            "resolved_temporal": None,
            "resolution_rule_id": "target_specific_closed_candidate_set_v0.1",
            "anchor_temporal_metadata_discovered": [],
            "unresolved_reason": "approved source scope contains no exact catalog temporal row",
            "unmappable_reason_code": TEMPORAL_NO_ANCHOR_METADATA,
        }
    if reviewer_selection is None:
        return {
            **base,
            "temporal_resolution_status": NEEDS_HUMAN_CLOSED_SET,
            "temporal_resolution_mode": None,
            "resolved_temporal": None,
            "resolution_rule_id": "target_specific_closed_candidate_set_v0.1",
            "anchor_temporal_metadata_discovered": candidates,
            "unresolved_reason": "one or more exact periods require selection from the precomputed closed set",
        }
    selected = validate_reviewer_selection(
        reviewer_selection, [item["temporal_candidate_id"] for item in candidates]
    )
    if selected is None:
        return {
            **base,
            "temporal_resolution_status": UNRESOLVED_NO_CANDIDATE,
            "temporal_resolution_mode": "HUMAN_CLOSED_SET_SELECT_NONE",
            "resolved_temporal": None,
            "resolution_rule_id": "human_closed_set_selection_v0.1",
            "anchor_temporal_metadata_discovered": candidates,
            "unresolved_reason": "reviewer selected NONE",
            "unmappable_reason_code": TEMPORAL_HUMAN_SELECT_NONE,
        }
    chosen = next(item for item in candidates if item["temporal_candidate_id"] == selected)
    return {
        **base,
        "temporal_resolution_status": RESOLVED_HUMAN_CLOSED_SET,
        "temporal_resolution_mode": "HUMAN_CLOSED_SET_SELECTION",
        "resolved_temporal": chosen["temporal"],
        "resolution_rule_id": "human_closed_set_selection_v0.1",
        "anchor_temporal_metadata_discovered": candidates,
        "selected_temporal_candidate_id": selected,
        "unresolved_reason": None,
    }
