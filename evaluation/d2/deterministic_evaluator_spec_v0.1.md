# Deterministic Evaluator v0.1 — implementation specification

Status: D2 freeze candidate, 2026-09-25.  This specification is subordinate
to `eval_protocol_v0.2.2`, `execution_taxonomy_v0.1`,
`agent_output_schema_v0.1.1`, and the frozen mapping specifications.  The
D2-specific representation decisions are frozen in
`deterministic_evaluator_contract_supplement_v0.1.md`.

## Scope and API

The evaluator is model/provider independent and evaluates one scheduled slot
from an explicit `EvaluationRequest` containing `gold_bundle`,
`slot_record`, optional `agent_output`, normalized XBRL map, chunk catalog,
and version/hash `contract_identity`.  It does not read split state, runtime
sidecars, or implicit global paths while scoring.  Runtime records and source
gold files are normalized by deterministic adapters before scoring.

The public implementation is `evaluation/d2/deterministic_evaluator.py`.
Important entry points are `adapt_evaluation_slot_record`,
`adapt_dev_gold_bundle`, `adapt_dev_xbrl_map`, `evaluate`,
`canonical_json_bytes`, and `result_sha256`.

## Normalization and contract checks

`EvaluationSlotRecord v0.1` is the only execution representation consumed by
the scorer.  A scheduled slot is one denominator slot; infrastructure
replacement inherits its slot identity, an exhausted infrastructure slot is
excluded, and terminal `FAIL_*` retains the slot and receives protocol-defined
completion-dependent zero.  Only the frozen v0.1 taxonomy values are accepted;
future statuses and inactive events fail with `EVAL_CONTRACT_MISMATCH`.

`GoldBundle v0.1` is the only gold representation consumed by scoring.
Adapters require an explicit declared source format/version and normalize only
schema-permitted representation differences.  They never infer DEV/TEST from
path names and never perform semantic matching.  The DEV adapter parses the
frozen CSV bundle into ordered answer groups, numeric targets, precision
records, approved chunk paths, and derived specifications.

`DEVXBRLMapAdapter v0.1` validates the frozen concrete map and emits
`DIRECT_APPROVED`, `DERIVED_VIA_APPROVED_INPUTS`, or
`NO_APPROVED_XBRL_PATH`.  It never runs mapping stages or discovers facts.

## Deterministic scoring

Numeric values are parsed as `Decimal`.  Registered units use the frozen
registry and scale conversion; `percentage_point` is distinct from `percent`.
Identical labels for otherwise unregistered units use the explicit same-label
fallback; different labels are incompatible.  Signed values are preserved.
Precision uses `PrecisionRecord v0.1`: explicit absolute tolerance takes
priority over display precision, display precision uses independent
ROUND_HALF_EVEN quantization, and otherwise comparison is exact.  No binary
float or universal epsilon is used.

Claims bind to explicit answer-group IDs when present; otherwise serialized
numeric-claim order binds positionally to frozen gold-group order.  There is
no value, semantic, embedding, permutation, or best-fit reassignment.  A
group selects one coherent approved variant family; mixed families fail.

Chunk provenance requires exact approved identity for the target and question.
XBRL provenance requires exact identity in the normalized approved map.
Legacy chunk provenance remains valid for `NO_APPROVED_XBRL_PATH` targets.

Derived answers validate required input identity, value, unit, precision,
provenance, and family before evaluating one explicitly listed canonical
formula variant.  Formula canonicalization removes only inert syntax; it does
not perform algebraic equivalence.  The calculator recomputes the result and
checks output unit and precision.

## Statuses, output, and judge boundary

Evaluator-level failures are distinct from execution statuses:
`EVAL_OK`, `EVAL_INPUT_INVALID`, `EVAL_CONTRACT_MISMATCH`, and
`EVAL_INTERNAL_ERROR`.  Non-OK evaluator status yields null agent score and
dependent metrics, `included_in_scored_denominator=false`, and
`checkpoint_valid=false`; it is never converted to an agent zero.

The canonical result is validated by
`deterministic_evaluator_output_schema_v0.1.json` and serialized with sorted
keys, stable arrays, canonical decimals, and no timestamps or random IDs.
Judge-dependent fields are literal `PENDING_JUDGE` and are excluded from
deterministic aggregates.

## TEST substitution contract

At the authorized TEST checkpoint the already frozen evaluator, adapters,
schemas, tests, and scoring rules remain unchanged.  Only TEST data bundles
and maps replace DEV bundles and maps.  A TEST parse or schema failure is an
evaluation-system failure, not an agent zero; repair requires a new evaluator
version/checkpoint procedure.

## Validation boundary

All D2-specific synthetic tests pass.  DEV gold and the frozen DEV XBRL map
parse successfully, including direct and derived approved-map states.  The
repository-wide non-locked run has one unrelated baseline failure because its
temporal renderer requires the deliberately excluded
`benchmark/provenance/**` tree; the frozen temporal artifact itself remained
unchanged.  No TEST material, network, model output, or judge was used.
