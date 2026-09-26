# Deterministic evaluator contract supplement v0.1

Status: **FROZEN D2 NORMATIVE SUPPLEMENT**

Freeze date: 2026-09-25

This supplement was frozen after the first D2 ambiguity gate and before any
evaluator implementation, DEV agent output, evaluator-aware prompt tuning,
judge optimization, or TEST access. No agent output and no TEST material were
consulted. It operationalizes representation and assignment details left
underspecified by `evaluation/eval_protocol_v0.2.2.md` without modifying that
protocol, `execution_taxonomy_v0.1`, `agent_output_schema_v0.1.1`, or the
frozen XBRL mapping package.

The decisions below are prospective. They must not be changed in response to
agent behavior or evaluation performance. Any semantic change requires a new
version and invalidates use of this version for the affected checkpoint. A
future `eval_protocol_v0.2.3` may incorporate these rules only without
semantic drift.

## R1. EvaluationSlotRecord v0.1

The evaluator scores one canonical `EvaluationSlotRecord v0.1` per scheduled
replicate slot. It never scores raw runtime sidecars directly. The versioned
adapter `evaluation_slot_record_adapter_v0.1` deterministically normalizes
frozen runtime records and audit sidecars.

Required fields are `question_id`, `scheduled_replicate_id`,
`scheduled_slot_id`, `effective_attempt_id`, `replacement_for_slot_id`,
`execution_status`, `agent_output_present`, `infrastructure_exhausted`, and
ordered observable runtime/event references. Recognized statuses are exactly:

- `RUN_COMPLETED`;
- `FAIL_TOOL_BUDGET_EXHAUSTED`;
- `FAIL_STEP_BUDGET_EXHAUSTED`;
- `FAIL_FINAL_SCHEMA_INVALID`;
- `FAIL_NO_VALID_FINAL_OUTPUT`;
- `FAIL_AGENT_ORCHESTRATION_UNRECOVERABLE`; and
- `INFRA_RUN_RETRY_EXHAUSTED`.

`EVAL_INCOMPLETE` is not a slot execution status and retains only its frozen
infrastructure-set meaning. `FAIL_CONTEXT_WINDOW_EXCEEDED` is unknown.
`EVT_TOOL_RESULT_TOO_LARGE` remains inactive.

A scheduled replicate creates one denominator slot. Infrastructure retries and
the single permitted replacement do not create slots. A successful replacement
uses the original `scheduled_slot_id`, records that same ID in
`replacement_for_slot_id`, and supplies its attempt as `effective_attempt_id`.
An exhausted infrastructure slot is missing and excluded from scored
denominators. A terminal agent `FAIL_*` retains the slot and is zero for
completion-dependent deterministic metrics. `RUN_COMPLETED` is scored
normally. Unknown statuses and impossible field combinations are contract or
input errors. The adapter never infers a status from free text; missing
required source representation is an error.

The legacy run adapter uses this closed mapping: `success` maps to
`RUN_COMPLETED`; `tool_budget_exhausted`, `step_budget_exhausted`,
`malformed_final_output`, and `orchestration_failure` map to their same-purpose
canonical `FAIL_*` IDs; `unrecoverable_tool_error` maps to
`FAIL_AGENT_ORCHESTRATION_UNRECOVERABLE`; and `provider_failure` requires an
explicit frozen infrastructure sidecar proving `INFRA_RUN_RETRY_EXHAUSTED`.
`FAIL_NO_VALID_FINAL_OUTPUT` requires an explicit canonical adapter status
because the legacy failure enum has no unambiguous counterpart. No other
mapping is allowed.

Machine schema:
`evaluation/d2/evaluation_slot_record_v0.1.schema.json`.

## R2. DEVXBRLMapAdapter v0.1

`DEVXBRLMapAdapter v0.1` validates the concrete frozen
`dev_xbrl_map_v0.1` object and emits
`NormalizedXBRLMap v0.1`. It does not rewrite the source map or run Stage
1/2/3 discovery.

Canonical target states are:

- `DIRECT_APPROVED`: source `final_mapping_status=mapped`; only exact
  human-approved source candidates become direct approved paths.
- `DERIVED_VIA_APPROVED_INPUTS`: source
  `final_mapping_status=derived_via_inputs`; every declared required upstream
  target must resolve to a direct approved path or recursively approved
  derived lineage. This state never creates a direct fact for the final target.
- `NO_APPROVED_XBRL_PATH`: source `final_mapping_status=unmappable`; legacy
  chunk provenance remains eligible.

Unknown states, missing semantic fields, inconsistent approved candidate IDs,
or unresolved required input IDs fail loudly. The adapter cannot discover
facts, anchors, dimensions, concepts, contexts, temporal bindings, unit
aliases, or equivalences.

For the frozen DEV map, `NF012` and `NF013` normalize to `DIRECT_APPROVED` and
`NF014` normalizes to `DERIVED_VIA_APPROVED_INPUTS` through those two upstream
targets, without a fabricated direct fact.

Machine schema:
`evaluation/d2/normalized_xbrl_map_v0.1.schema.json`.

## R3. GoldBundle v0.1 and source dispatch

The scorer accepts only a validated normalized `GoldBundle v0.1`. Source-file
adapters are separate deterministic preprocessing steps and never select
scoring algorithms.

A bundle contains its schema/adapter/source identities, question ID, ordered
answer groups with stable IDs and multiplicity (an evidence-only question may
have an empty answer-group array), approved variants and families, a catalog
of all answer and required-input numeric target identities, exact decimal value strings, unit labels, precision
records, explicit sign policy, approved chunk and XBRL paths, derived
specifications, and separately identified judge-dependent gold.

Source dispatch is explicit. D2 v0.1 recognizes:

1. `gold_bundle_v0.1` for already normalized objects; and
2. `dev_gold_csv_bundle_v0.1` for the exact documented DEV CSV set, only when
   the caller declares that source format and supplies the required files.

Paths, filenames, split labels, column resemblance, or content are never used
to guess the format. Documented null/list forms may be normalized; semantic
equivalence is never added because encodings look similar. No unobserved TEST
encoding is preregistered. At the authorized TEST checkpoint, data must enter
through an already-supported declared adapter or as a schema-valid frozen
`GoldBundle v0.1`. Otherwise the result is `EVAL_INPUT_INVALID`, never an agent
zero or silent skip. Repair requires a new evaluator version and checkpoint
procedure.

Machine schema: `evaluation/d2/gold_bundle_v0.1.schema.json`.

## R4. EvaluatorStatus v0.1

The evaluator-level namespace is separate from execution taxonomy:

- `EVAL_OK`;
- `EVAL_INPUT_INVALID` for malformed evaluation inputs, impossible duplicate
  IDs, unsupported declared representations, and malformed gold/map/runtime
  records;
- `EVAL_CONTRACT_MISMATCH` for protocol/schema/hash/adapter mismatch or an
  unsupported future taxonomy status; and
- `EVAL_INTERNAL_ERROR` for an unexpected deterministic evaluator failure
  after valid inputs were accepted.

For every non-OK status, agent score and dependent deterministic metrics are
null, `included_in_scored_denominator=false`, and `checkpoint_valid=false`.
Errors are explicit and auditable and never become agent failures.
`PENDING_JUDGE` is a metric-field value compatible with `EVAL_OK`.
`EVAL_INCOMPLETE` retains only its existing infrastructure meaning.

Machine schema: `evaluation/d2/evaluator_status_v0.1.schema.json`.

## R5. Claim-to-answer-group assignment

Assignment never uses semantics, values, embeddings, best fit, permutation, or
score maximization.

An explicit stable `answer_group_id` permitted by a source output schema is
authoritative. Duplicate or unknown explicit IDs are invalid. The current
`agent_output_schema_v0.1.1` has no such field, so its adapter supplies no
explicit binding and uses positional binding.

For positional binding, answer groups retain frozen array order and numeric
material answer claims retain serialized `claims` array order. Claim `i` binds
to group `i`, one-to-one. A claim cannot satisfy two groups. A group cannot
consume multiple claims unless its frozen `multiplicity` is greater than one.
Too few claims leave required groups unmatched. Extra claims stay extra and
never replace an earlier binding. Variant selection occurs only within the
assigned group. If a future frozen output schema permits explicit IDs, its
versioned adapter may populate the already-defined explicit binding field;
positional order then cannot override it.

This rule is part of the evaluator contract and must be disclosed in future
agent prompt/schema documentation rather than hidden as a matching heuristic.

## R6. Derived input and formula binding

Each derived specification contains a target ID, ordered required inputs with
stable `input_role` and source target/group identity, allowed formula variants,
output unit, and output precision.

An explicit input-role/target ID permitted by the source representation is
authoritative. For `agent_output_schema_v0.1.1`, a calculation input `name`
exactly equal to a frozen `input_role` is an explicit role binding; no case
folding or trimming is performed. If no submitted input name equals any frozen
role token, inputs bind positionally. A mixture of explicit role tokens and
unbound names is invalid rather than partly positional. Duplicate and unknown
role tokens are invalid. Inputs are never assigned by coincident value.

Every required input independently passes identity, numeric value, unit,
precision, provenance, and family consistency. Extra inputs do not repair a
missing input.

Formula acceptance is syntactic and allowlisted. No symbolic algebra or search
is performed. Canonicalization removes only whitespace, redundant outer
parentheses, insignificant Decimal lexical zeros/signed zero, inert unary plus,
and replaces calculation-local input IDs with their frozen `input_role` tokens.
Operator order, association, distribution, factoring, commutation, and sign
transformations are preserved. A submitted canonical formula must equal one
explicitly frozen `canonical_formula` and reports that `formula_variant_id`.

DEV formula variants are materialized prospectively from the already-frozen
gold formulas. Each current formula receives one ID of the form
`<derived_target_id>.formula.v1`; no algebraic alternatives are added. The
calculator then recomputes the result from validated inputs. A correct final
number alone is insufficient.

## R7. PrecisionRecord v0.1

Modes are exactly `EXACT`, `QUANTUM`, and `ABS_TOLERANCE`.

Legacy adapter priority is:

1. A present explicit numeric tolerance produces `ABS_TOLERANCE`; it is parsed
   exactly, must be nonnegative, and is normalized into the same unit
   coordinate as the gold value. Display precision remains source metadata.
2. Otherwise a present nonnegative integer decimal-place value `p` produces
   `QUANTUM` with `quantum=Decimal(10) ** (-p)` and
   `rounding_mode=ROUND_HALF_EVEN`. Candidate and gold are independently
   quantized and compared.
3. Otherwise use `EXACT` after registered unit normalization.

Unit normalization precedes precision. Sign is checked on signed normalized
values. There is no binary epsilon, universal fallback epsilon, or implicit
absolute-value operation. Invalid precision/tolerance is input-invalid.

Machine schema: `evaluation/d2/precision_record_v0.1.schema.json`.

## R8. Variant-family coherence

Each assigned answer group selects one complete approved variant. All numeric,
unit, precision, basis, sign, provenance, formula, and derived-input components
used for that answer must be compatible with the same selected family. Derived
inputs obey the question consistency group; V1/V2 mixing is invalid. The
evaluator never selects different variants per component to maximize score.

If multiple complete variants pass identically, the lexicographically smallest
frozen `variant_id` is reported. This tie-break does not change pass/fail.

## R9. Judge boundary

Judge-dependent fields remain literal `PENDING_JUDGE`. They are excluded from
deterministic aggregates. No regex, keyword, embedding, semantic similarity,
or other deterministic proxy is permitted.

## Freeze and change control

This supplement and its five machine schemas are frozen before evaluator code.
They resolve B1–B7 from the original preregistration without erasing that
history. No post-hoc change based on DEV or TEST agent performance is allowed.
No real agent output, judge output, network resource, original repository, or
TEST material was used.
