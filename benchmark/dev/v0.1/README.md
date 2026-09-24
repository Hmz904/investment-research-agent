# Agent DEV benchmark v0.1

Status: **frozen after final human review**

This directory is the Week 2 development benchmark. It is separate from the
16-question locked test established by `docs/agent/agent_precommit_v0.1.md`.
The DEV set may be run repeatedly and may guide prompt, retrieval-tool
interface, control-flow, and tool-use-policy iteration. It is not a test set.

## Binding corpus and source contract

- Corpus: the existing frozen 14-document SEC corpus
- Corpus fingerprint: `56df698d50b13cf15e913c1c60dbc96b1fd0fab44adb7b1f40ba99771c4b7c96`
- Allowed: SEC 10-Q, SEC 10-K, and earnings 8-K Exhibit 99.1
- Excluded: transcripts, unfiled IR decks, news, Bloomberg, third-party
  research, and external web sources

An answer may be factually true and still be out of scope. Excluded-source
reliance is a `source_scope_violation` under `evaluation/eval_protocol_v0.2.md`.

## Files

- `questions.csv`: eight questions, exactly three numeric and five
  evidence/thesis/update/comparison questions.
- `numeric_answers.csv`: numeric targets, required inputs, formulas, units,
  periods, bases, accessions, and chunk anchors.
- `evidence_checklist.csv`: semantic evidence items and their required parts.
- `provenance.csv`: normalized fact/part-to-candidate-reference mappings.
- `review/dev_gold_review_round1.csv`: immutable snapshot of the first human
  review over the original 64 semantic units.
- `review/dev_gold_review.csv`: final packet after human re-review; every
  active semantic unit is explicitly `APPROVE`. Retired rows retain their
  audit decision and are not active gold.
- `review/dev_gold_review_delta.csv`: machine-readable classification of
  carried approvals, changed rows, source-verification rows, and new rows.

## Annotation semantics

Numeric questions reuse the benchmark answer-group convention:

- distinct `answer_group` values are AND requirements;
- verified variants within one group are OR alternatives;
- every derived answer lists all `required_input_facts` and a formula;
- values are evaluated at the annotated unit, basis, period, and display
  precision; and
- a correct final value does not conceal incorrect required inputs.

DEV02 additionally declares `variant_family` and
`question_consistency_group` in `numeric_answers.csv`. All three DEV02 answer
groups must be matched within one family (`V1_GAAP_MINUS_NON_GAAP` or
`V2_COMPANY_REPORTED_ADJUSTMENT_COLUMN`) for a response to be consistent;
mixed-family answers are invalid even when each individual number matches a
per-group variant.

Evidence rows are part-level annotations. Rows sharing `(q_id, item_id)` form
one semantic item. `within_item_logic=AND` means every listed `part_id` is
required for strict completion of that item.

`evidence_checklist.csv`, `provenance.csv`, and the final review packet carry
an explicit `status` field. `ACTIVE` rows participate in scoring and required
provenance; `RETIRED` rows remain auditable historical trace but are excluded
from active denominators and active-human-approval counts.

Temporal roles are exclusive at the part level: earlier-period-only facts are
`prior_period`, current-period-only facts are `current`, comparisons are
`change`, cross-company facts are `cross_company`, and static/contextual
definitions use `not_applicable`. A current part must not embed the benchmark's
prior-to-current comparison.

`provenance.csv` is authoritative for source mapping. Each direct numeric fact
and evidence part maps to one or more named candidate references; candidate
references for the same target are OR alternatives. A candidate reference is
either one source chunk or, for a comparison/derived semantic claim that no
single chunk states, an explicitly named source bundle whose members are AND.
This bundle is target-specific and may not be reused as a broad question-level
anchor. Derived numeric facts have no direct candidate shortcut: their
provenance is the AND of their declared input facts, and the file records that
input-union lineage as non-candidate audit metadata.

The `supporting_chunk_ids` and `anchor_logic` columns in the annotation CSVs
are denormalized readability fields. Scoring must use the normalized
candidate-reference and derived-input records in `provenance.csv`.

Importance weights reuse the locked benchmark values:

- `core = 3.0`
- `supporting = 1.5`
- `optional = 0.5`

The annotations are intentionally source-anchored but lighter weight than the
locked test. They must not be imported into production agent code or included
in a future locked-test production context.

`SOURCE_CHECK_PASS` records Codex verification against the frozen corpus; it
is not itself human approval. Final human decisions are recorded separately
in the review packet, with retired rows excluded from active scoring.

## Split policy

DEV may be rerun and used for iteration. Locked TEST may be run only after an
agent version and its prompt, tool contract, and control policy are frozen.
Results from a locked-test run cannot mutate that same version; any response
requires a new version. No test-question-specific production logic is
permitted.

The 16 locked questions were historically used for Week 1 retrieval
development and evaluation. The locked-test boundary begins at the Week 2
precommit; this project does not claim that those questions were untouched
throughout its entire history.
