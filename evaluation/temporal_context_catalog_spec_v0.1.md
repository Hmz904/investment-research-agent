# Temporal context catalog specification v0.1

Status: **development; benchmark-independent; not frozen**

The catalog is generated only from frozen local corpus, ingestion, table, filing, and inline-XBRL metadata. Benchmark target IDs, benchmark period labels, benchmark answer values, review outcomes, and agent outputs are prohibited construction inputs.

## Row contract

Every row has a stable `temporal_row_id`, entity and CIK when available, accession, form type, filing date, exactly one economic `temporal` object (`instant` or duration `period_start`/`period_end`), optional `context_ref`, dimensions where relevant, source metadata identities, evidence fingerprints, `temporal_evidence_type`, and `generation_rule_id`.

`temporal_evidence_type` is stored directly and is exactly one of:

- `DIRECTLY_OBSERVED_CONTEXT`: exact dates are present in an authoritative frozen XBRL context;
- `DETERMINISTICALLY_DERIVED`: a versioned frozen rule derives exact dates from authoritative machine metadata; or
- `MERGED_AGREEING_EVIDENCE`: independent table/header and XBRL context evidence agree exactly.

Derived rows are never labeled observed. Conflicting linked evidence is emitted as a diagnostic and is not silently selected. Row order and canonical JSON serialization are deterministic and contain no timestamps.

## Generation rules

- `xbrl_context_exact_dates_v0.1` groups frozen facts by accession, exact `context_ref`, temporal object, and dimensions.
- `table_cell_exact_period_v0.1` retains a frozen table-cell/header temporal object only when `period_resolution_source=header_explicit` establishes that its exact dates were explicitly present. The existence of populated `period_start` and `period_end` fields alone is insufficient.
- `table_duration_end_months_to_start_v0.1` is `RETIRED_UNSAFE_FOR_AUTHORITATIVE_TEMPORAL_ROWS`. An end date plus `duration_months` never establishes an exact start. No replacement calendar-month formula is permitted; in particular, 52/53-week fiscal periods must not be converted through calendar-month arithmetic.
- `table_xbrl_agreement_v0.1` records merged evidence only when authoritative direct linkage supplies one unique exact XBRL temporal object, every applicable linked exact context agrees, linked dimension sets agree, and table evidence does not contradict it. Inferred table evidence may participate because XBRL independently supplies exact dates; inference itself is not the authoritative source.

Frozen `period_resolution_source` is the controlling provenance discriminator. `header_explicit` is explicit; `header`, `xbrl_context`, and `xbrl_fact` are derived/inferred for the table-only rule. `period_resolution_context_id`, direct `xbrl_facts`, and reconciliation metadata remain audit evidence. Any table/XBRL temporal disagreement or linked-dimension disagreement emits a conflict diagnostic and generates no merged row. Ambiguous dimensions never become `dimensions=[]`.

Source identities preserve document, chunk, table column, context, and linked fact identities where present. Evidence fingerprints are SHA-256 over canonical source evidence.

## Candidate-set use

The catalog is not itself a benchmark mapping. A target-specific closed set must constrain rows by authoritative target entity and approved chunk/source/accession identities before grouping agreeing rows by exact temporal object. Every grouped candidate aggregates all contributing `temporal_row_id` values, source identities, evidence fingerprints, evidence types, and generation-rule IDs in stable canonical order; it never chooses the lexically first row as an arbitrary provenance representative. It must not use a target numeric value, human period label, mapping outcome, agent output, or reviewer search. If those constraints yield no defensible row, generation fails closed.

## Prospective human-review scope

The catalog is not an exhaustive row-by-row approval workload. Human review is complete only when all three layers below are complete. The layers define review scope prospectively; no outcome may change their selection rules.

### Layer A — generation-rule families

Every family capable of producing `DETERMINISTICALLY_DERIVED` or `MERGED_AGREEING_EVIDENCE` is reviewed at rule level. The reviewer approves or rejects rule semantics, not all generated rows. The `DIRECTLY_OBSERVED_CONTEXT` identity-binding family is also reviewed at rule level; its individual rows do not all require manual approval. `temporal_rule_review_v0.1.csv` records for every distinct family its `rule_id`, evidence inputs, derivation or merge condition, failure condition, catalog row count, and deterministic representative example(s). Human rule decisions and notes start blank.

### Layer B — rows actually used for target adjudication

Every aggregated temporal candidate actually presented for a human target decision is reviewed individually, including every DEV candidate now and every TEST candidate only at a later authorized TEST checkpoint. All contributing catalog rows and provenance remain visible. A candidate cannot be selected unless its exact temporal object and every contributing source/provenance identity are reviewable. `dev_temporal_human_review_v0.1.csv` contains only mechanically pending DEV targets and allows exactly `SELECT <temporal_candidate_id>` or `SELECT NONE`; it has no arbitrary date field.

### Layer C — deterministic conflict sample

Conflict diagnostics are sampled, not exhaustively adjudicated. Before outcomes are viewed, diagnostics are grouped by the closed `conflict_type` taxonomy, sorted within each group by stable `conflict_id`, and the first `min(5, group_size)` are selected. `temporal_conflict_review_sample_v0.1.csv` records that sample. Its purpose is to validate conflict classification and fail-closed behavior, never to override a diagnostic. Conflicts remain fail-closed, and serialization order is never a semantic tie-break.

The legacy all-row catalog CSV is a deterministic machine export and does not define the human approval workload. Completion requires Layer A rule review, Layer B individual review of every actually presented row, and Layer C review of the prospectively selected sample—no more and no less.
