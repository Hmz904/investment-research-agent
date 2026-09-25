# Gold-to-XBRL mapping specification v0.1.2

Status: **development successor; not frozen; no human approvals**

## Version lineage and exact delta

- `v0.1` is the frozen original mapping contract.
- `v0.1.1` is an abandoned provisional temporal-label-parser draft retained only for audit history.
- `v0.1.2` is the provenance-anchor temporal-resolution successor.

Version 0.1.2 inherits every v0.1 rule except the temporal-resolution extension in this document and the directly necessary audit fields. The final pre-review clarifications (a) make exact temporal binding precede final direct-target mapping adjudication, (b) add closed unmappable reason codes, (c) define the catalog human-review workload, and (d) retire unsafe month-only exact-period reconstruction while preserving all provenance for agreeing candidates. They do not change unit, precision, sign/basis, Stage-2 exact-concept, Stage-2 exact-value, candidate review, TEST checkpoint, or execution-taxonomy semantics.

## Authoritative temporal hierarchy

The same ordered mechanism applies to DEV and future TEST. Resolution completes before Stage-3 candidate search.

1. **Exact target metadata.** An authoritative target `instant` or `period_start` plus `period_end` is used unchanged, with `temporal_resolution_mode=EXACT_TARGET_DATE` and status `RESOLVED_EXACT_TARGET_DATE`. No parser is involved.
2. **Approved provenance anchor.** Approved frozen anchors may resolve exact dates only from frozen machine metadata. Modes remain explicit: `ANCHOR_TABLE_PERIOD`, `ANCHOR_XBRL_CONTEXT`, and `ANCHOR_EXACT_SOURCE_METADATA`. A unique exact temporal object is required. Every result preserves anchor, table/cell/header or XBRL context identity where available, ingestion identity/version, `resolution_rule_id`, and evidence fingerprint. Conflicting machine interpretations return `AMBIGUOUS_MACHINE_EVIDENCE`; no heuristic tie-break is allowed.
3. **Human closed set.** If anchors do not select one exact temporal object, a target-specific candidate set is precomputed from `temporal_context_catalog_v0.1` using only authoritative pre-review entity, approved accession, chunk/table/source identity, filing metadata, exact XBRL linkage, and other frozen source-scope constraints. Gold numeric value, benchmark period-label spelling, mapping candidates, agent output, and reviewer free search are prohibited. Insufficient scope returns `UNRESOLVED_NO_CANDIDATE` instead of broadening. A nonempty set returns `NEEDS_HUMAN_CLOSED_SET`.
4. **Unmappable.** If none of the allowed mechanisms resolves the target, it remains unmappable because the evaluation adapter lacks authoritative temporal meaning.

Only an exact resolved instant or duration may become the Stage-3 temporal key. A pending human decision keeps Stage 3 closed.

## Temporal precedence for direct targets

For every direct numeric target without authoritative exact target dates, Stage-1 candidate discovery may occur before temporal adjudication, but discovery and even `SOURCE_CHECK_PASS` cannot finalize the target as mapped. The target must first receive one unique exact binding from approved-anchor machine metadata or `SELECT <temporal_candidate_id>` from its frozen closed set. A candidate counted toward `PROPOSED_MAPPED` must have an exact temporal object equal to that binding. A candidate never creates target temporal truth and never expands or narrows the closed set. Multiple authoritative Stage-1 contexts remain pending human closed-set adjudication. Stage 3 is prohibited until binding exists.

The diagnostic reports three independent closed state dimensions:

- candidate discovery: `NO_CANDIDATES_DISCOVERED`, `CANDIDATES_DISCOVERED_SOURCE_CHECK_PENDING`, `CANDIDATES_DISCOVERED_SOURCE_CHECK_PASS`, or `CANDIDATES_DISCOVERED_ALL_REJECTED`;
- temporal resolution: the closed temporal statuses below; and
- provisional final mapping: `PENDING_TEMPORAL_ADJUDICATION`, `PROPOSED_MAPPED`, `PROPOSED_UNMAPPABLE`, or `PROPOSED_NO_XBRL_COUNTERPART_IN_FROZEN_CORPUS`.

Thus a source check may pass while final mapping remains `PENDING_TEMPORAL_ADJUDICATION`. Stage-1 evidence is retained, not discarded.

## Approved-anchor rules

### Table/cell metadata

Frozen ingestion fields may include chunk and table identity, row/column identity, `column_periods`, cell `period_start`, `period_end`, `instant_date`, `duration_months`, `period_resolution_source`, `period_resolution_context_id`, linked inline-XBRL facts, and reconciliation metadata. `duration_months` plus an end date is not authoritative exact temporal truth and may never be converted into an exact start, including by `(end + 1 day) - N months`. Such arithmetic is invalid for 52/53-week fiscal calendars as well as vulnerable to calendar off-by-one errors.

Populated start/end fields are not automatically authoritative. `table_cell_exact_period_v0.1` requires explicit exact provenance (`period_resolution_source=header_explicit`). Ingestion-derived or inferred fields (`header`, `xbrl_context`, or `xbrl_fact`) cannot masquerade as explicit table truth. Inferred evidence may enter `table_xbrl_agreement_v0.1` only when a direct authoritative linkage independently provides one unique exact XBRL temporal object, all applicable linked contexts and dimension sets agree, and the table does not contradict it. Any disagreement fails closed.

### XBRL context

An approved anchor may use an exact target concept/context/fact linkage already present in frozen metadata. The linked context supplies either `instant` or `period_start` plus `period_end`. Same value alone, same concept alone without the approved anchor, nearby facts, and future candidate results are not authoritative linkages.

## Human-readable labels

`period_scope`, `source_period_label`, fiscal descriptors, and DEV annotation strings are display/audit metadata only. They are never parsed or used to establish, select, or adjudicate dates. The abandoned v0.1.1 parser is not part of benchmark resolution. Any internal parser for system-generated labels must accept only system-generated input, fail closed, and have no DEV/TEST adjudication role.

## Closed human adjudication

The review packet freezes aggregated candidate IDs before review. Each candidate retains all agreeing catalog row IDs, source identities, evidence fingerprints, evidence types, and generation-rule IDs. The only valid decisions are `SELECT <temporal_candidate_id>` and `SELECT NONE`. A reviewer cannot type dates, search for periods, add a source, reinterpret a label, or expand the set. Human fields remain blank until an authorized review.

## Closed statuses and finalization

Temporal status is one of `RESOLVED_EXACT_TARGET_DATE`, `RESOLVED_ANCHOR_METADATA`, `RESOLVED_HUMAN_CLOSED_SET`, `NEEDS_HUMAN_CLOSED_SET`, `UNRESOLVED_NO_CANDIDATE`, or `AMBIGUOUS_MACHINE_EVIDENCE`.

Only after exact temporal resolution and completion of every applicable deterministic Stage-1/2/3 search may an empty search support `no_xbrl_counterpart_in_frozen_corpus`. Failure to resolve temporal meaning yields `unmappable`; absence of a parsed fiscal label is irrelevant.

An unmappable temporal path records exactly one of the following closed audit reason codes when applicable:

- `TEMPORAL_NO_ANCHOR_METADATA`: approved anchor/source scope has no authoritative exact machine temporal metadata and cannot produce a defensible closed candidate set;
- `TEMPORAL_HUMAN_SELECT_NONE`: a nonempty frozen closed set was shown and the reviewer selected `NONE`; or
- `EVALUATOR_CANNOT_REPRESENT`: relevant economic/source semantics exist but cannot be faithfully represented by the frozen evaluator/mapping contract.

These codes are explanatory metadata only. They do not change scoring, assert that no XBRL fact exists externally, or convert `unmappable` into `no_xbrl_counterpart_in_frozen_corpus`.

## Known evaluation-adapter limitation

When an approved anchor lacks safe exact temporal metadata, an agent may still cite authoritative legacy chunk evidence and an XBRL identity may remain structurally plausible. The evaluator nevertheless cannot award an approved XBRL mapping path without authoritative target temporal binding. This contract intentionally prefers false negatives over heuristic temporal inference and does not expand the closed candidate set to recover such cases.

## Additional audit fields

Each direct target records exact-target-date presence, approved anchors, discovered anchor metadata, temporal status/mode, exact temporal object when resolved, aggregated candidate IDs and all contributing row IDs when applicable, selected candidate (blank in this session), unresolved reason, resolution rule IDs, source evidence identities, and evidence fingerprints.

This document does not freeze v0.1.2, the temporal catalog, a final DEV map, an evaluator, or a production agent.
