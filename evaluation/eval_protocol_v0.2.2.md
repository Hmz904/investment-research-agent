# End-to-end agent evaluation protocol v0.2.2

Status: **draft evaluation-semantics extension; no DEV or locked-TEST agent run
has occurred**

Parent protocol: `evaluation/eval_protocol_v0.2.1.md`

This protocol incorporates v0.2.1 by reference and changes only the additions
listed here. Every v0.2.1 rule not explicitly clarified below remains
unchanged, including DEV acceptance philosophy, three-run reporting,
authorized locked-TEST checkpoints, evidence scoring, causal/source-scope
semantics, and the deterministic/judge boundary.

Normative companion contracts are:

- `evaluation/xbrl_gold_mapping_spec_v0.1.md`;
- `evaluation/xbrl_mapping_schema_v0.1.json`;
- `evaluation/xbrl_mapping_review_rubric_v0.1.md`; and
- `docs/agent/execution_taxonomy_v0.1.md` at annotated tag
  `execution_taxonomy_v0.1` (commit
  `f20a6d97dcb6babb00ae5e14b287073ea5312c6b`) for the canonical execution
  taxonomy and infrastructure policy; and
- `docs/agent/agent_execution_policy_preflight_v0.1.md` for non-taxonomy
  execution-policy decisions.

## 1. Registered unit dimensions and exact normalization

The unit registry is closed. Each registered label has one semantic dimension,
canonical unit, positive exact Decimal factor, and rule ID.

| label | dimension | canonical unit | factor | rule ID |
|---|---|---|---:|---|
| `USD` | `monetary` | `USD` | `1` | `monetary_usd_identity_v0.1` |
| `USD_thousand` | `monetary` | `USD` | `1000` | `monetary_usd_thousand_to_usd_v0.1` |
| `USD_million` | `monetary` | `USD` | `1000000` | `monetary_usd_million_to_usd_v0.1` |
| `USD_billion` | `monetary` | `USD` | `1000000000` | `monetary_usd_billion_to_usd_v0.1` |
| `shares` | `share_count` | `shares` | `1` | `shares_identity_v0.1` |
| `shares_thousand` | `share_count` | `shares` | `1000` | `shares_thousand_to_shares_v0.1` |
| `shares_million` | `share_count` | `shares` | `1000000` | `shares_million_to_shares_v0.1` |
| `shares_billion` | `share_count` | `shares` | `1000000000` | `shares_billion_to_shares_v0.1` |
| `USD_per_share` | `monetary_per_share` | `USD_per_share` | `1` | `usd_per_share_identity_v0.1` |
| `USD_per_basic_share` | `monetary_per_share` | `USD_per_share` | `1` | `usd_per_basic_share_alias_v0.1` |
| `USD_per_diluted_share` | `monetary_per_share` | `USD_per_share` | `1` | `usd_per_diluted_share_alias_v0.1` |
| `pure` | `ratio` | `pure` | `1` | `ratio_pure_identity_v0.1` |
| `percent` | `ratio` | `pure` | `0.01` | `ratio_percent_to_pure_v0.1` |
| `percentage_point` | `percentage_point` | `percentage_point` | `1` | `percentage_point_identity_v0.1` |

Normalization is exact `Decimal(submitted_value) * Decimal(factor)`. Binary
float is forbidden. It preserves sign, performs representational conversion
only, and does not require CalculatorTool. Different dimensions never compare
as equivalent.

Registered authoritative raw-XBRL aliases are closed as well: raw `USD` maps
to `monetary`, raw `shares` to `share_count`, raw `USD/shares` to
`monetary_per_share`, and raw `pure` to `ratio`. The raw unit remains in every
approved path. `USD/shares` establishes only a dimension; it does not establish
basic versus diluted, adjusted versus unadjusted, or GAAP versus non-GAAP.
Those are concept/basis questions.

`0.56 pure` equals `56 percent`. `percentage_point` is a separate dimension:
a move from 40 percent to 50 percent is +10 percentage points but +25 percent
relative change. No implicit conversion is allowed. `basis_point` is not
registered because no frozen non-gold project contract requires it.

Unit comparison first tests exact label identity. Identical unit strings yield
`unit_match_status="exact_label_match"`, including for an unregistered label;
values then use the frozen precision and sign rules without scale conversion.
This does not infer a dimension, alias, or registry entry. Different labels
compare only through a frozen exact registry relationship and then yield
`unit_match_status="registered_equivalence"`. Different labels without such a
relationship yield `unit_match_status="unregistered_unit"`, no equivalence
credit, and no crash. A later alias requires a versioned evaluation revision
and cannot be added during locked TEST.

## 2. Gold-recorded precision and numeric matching

Mapping candidate generation and evaluator comparison use the same versioned
Decimal equivalence function. After establishing either unchanged exact-label
identity or registered same-dimension normalization, it permits only:

1. exact canonical equality under `precision_exact_v0.1`;
2. an already-recorded positive power-of-ten display quantum under
   `precision_rounding_quantum_v0.1` with `ROUND_HALF_EVEN`; or
3. an absolute tolerance already supplied by frozen gold/evaluation semantics
   under `precision_absolute_tolerance_v0.1`.

Every non-exact rule records its rule ID, frozen source, quantum or tolerance,
and comparison interval/unit. A reviewer may not invent or widen a
candidate-specific tolerance or select a rule after seeing a candidate. If no
registered precision rule exists, review cannot create one.

## 3. Mapping sign and agent-answer basis semantics

Scale normalization never changes sign; no stage uses `abs(value)` matching.
For gold-to-XBRL mapping, an opposite-sign relation is accepted only on one
specific approved path as `opposite_sign_explicitly_approved`. That path must
record gold/display sign, authoritative XBRL sign, declared basis relation,
gold canonical/economic sign, source-bound rationale, and `APPROVE`. It is not
reusable by concept, table, or other target. Insufficient evidence yields
`NEEDS_SOURCE_CHECK`.

Agent-answer scoring is separate. Each acceptable gold answer is a
pre-registered variant with variant ID, value, unit, basis, sign convention,
and optional variant family. An agent answer is acceptable if and only if it
matches one registered variant under the frozen unit, precision, sign/basis,
and family-consistency rules. The agent's basis label may identify a registered
variant; it cannot create a new acceptable convention. Existing linked-answer
family rules continue to reject mixed-family answers.

If a legacy target lacks complete pre-registered sign-variant coverage, that is
an evaluation/benchmark limitation and must be disclosed in future reporting.
It does not authorize an agent-created variant or a checkpoint-time TEST repair.

## 4. XBRL mapping states and sequential candidate generation

Candidate review status and target mapping status are different namespaces.
Candidates use exactly `APPROVE`, `REJECT`, or `NEEDS_SOURCE_CHECK`. Final
direct-target mapping status uses exactly:

- `mapped`: at least one authoritative XBRL path completed required human
  review with `APPROVE`;
- `no_xbrl_counterpart_in_frozen_corpus`: the complete frozen deterministic
  search finished with no approved or unresolved eligible candidate; this is
  a local-corpus availability result, not a claim about the external world;
- `unmappable`: potentially relevant structured evidence or a semantic case
  exists, but the frozen representation/rules cannot adjudicate it faithfully.

Both non-mapped states retain legacy chunk authority and are not automatically
agent errors. No-counterpart targets are excluded from the unmappable rate.
Unmappable IDs and counts are reported, and no checkpoint-time repair is
allowed. Derived targets use a separate `derived_via_inputs` resolution mode;
their required inputs remain an AND-set and are not direct mapping statuses.
Every required input still needs independently adjudicable support through an
allowed frozen provenance route; resolution mode alone cannot earn full
grounded correctness.

The workflow is strictly sequential:

1. generate Stage-1 direct chunk-linked candidates;
2. human-review Stage 1 and record approved lineage;
3. generate Stage 2 only from an approved Stage-1 parent;
4. human-review Stage 2;
5. generate Stage 3 only for unresolved targets using frozen predicates;
6. human-review Stage 3; and
7. finalize target status.

Stage 2 requires the same entity, exact concept, economic instant/duration,
axis/member structure, and exact canonical signed quantity after registered
unit normalization, or the exact signed quantity under same-label identity.
Different raw strings may compare only through a registered alias/scale.
Filing-local `context_ref` may differ. A recast or otherwise different numeric
value is not a Stage-2 duplicate.

Stage 3 candidates must satisfy all available frozen predicates: target entity,
exact-label identity or registered compatible unit equivalence, target
precision match, exact target
instant/duration, required dimensions, same-entity accession, and a filing
that directly covers the target period or a later filing explicitly containing
that period as a comparative context. Reviewers adjudicate emitted candidates;
they never choose or broaden the search scope. Stage 3 alone may emit a
different concept, which always starts `NEEDS_SOURCE_CHECK`.

`no_xbrl_counterpart_in_frozen_corpus` is assigned only after Stage 1,
applicable Stage 2, and Stage 3 complete, with no approved candidate and no
unresolved candidate that instead requires source checking or `unmappable`.
Absence of a direct chunk-linked fact is insufficient.

## 5. DEV and locked-TEST timing

Before the first DEV agent output, freeze the mapping algorithm, schema, and
rubric; construct and review the DEV mapping; and freeze that mapping and the
deterministic evaluator. TEST mapping is not constructed then.

Before DEV mapping construction, the authorized D session performs the
unit-completeness audit specified by the mapping contract: enumerate distinct
DEV-gold labels, classify each as registered, exact-label-only supported, or
requiring a proposed alias, and make no silent alias change. Any alias change
must be versioned and reviewed before DEV agent outputs.

At the first authorized `agent_v0.1` locked-TEST checkpoint, use one controlled
evaluation window:

1. confirm agent implementation, prompt, model/configuration, evaluator, and
   manifest are frozen;
2. register TEST access;
3. open TEST gold;
4. run the already-frozen mapping algorithm;
5. apply the already-frozen rubric;
6. freeze `test_xbrl_map_v0.1` with commit/tag;
7. only then generate or inspect TEST agent outputs;
8. run three reportable replicates per question; and
9. score with the frozen evaluator and TEST mapping.

The sealed-output/hash-first alternative is not used. Reuse this TEST mapping
at later authorized checkpoints unless a versioned protocol says otherwise.

## 6. Canonical execution IDs and evaluation treatment

`docs/agent/execution_taxonomy_v0.1.md` is the sole normative source for
execution meanings and infrastructure constants. This protocol only maps its
stable IDs/statuses to evaluation treatment:

| canonical ID/status | evaluation treatment |
|---|---|
| `EVT_FIXED_TOP_K_VIOLATION` | report frequency; no automatic zero if the run later completes |
| `EVT_TOOL_ARGUMENT_REJECTED` | report frequency; no automatic zero if the run later completes |
| `EVT_TOOL_ZERO_RESULT` | report frequency; no automatic zero if the run later completes |
| `EVT_TOOL_DOMAIN_ERROR_RECOVERABLE` | report frequency; no automatic zero if the run later completes |
| `EVT_TOOL_RESULT_TOO_LARGE` | reserved and inactive; no event is expected unless a later frozen execution policy activates it |
| `FAIL_TOOL_BUDGET_EXHAUSTED` | terminal agent failure; retain scheduled denominator slot, no replacement, zero where valid completion is required |
| `FAIL_STEP_BUDGET_EXHAUSTED` | same terminal-agent-failure treatment |
| `FAIL_FINAL_SCHEMA_INVALID` | same terminal-agent-failure treatment |
| `FAIL_NO_VALID_FINAL_OUTPUT` | same terminal-agent-failure treatment |
| `FAIL_AGENT_ORCHESTRATION_UNRECOVERABLE` | same terminal-agent-failure treatment |
| `RUN_COMPLETED` | score normally, including schema-valid wrong or poorly grounded answers |
| `INFRA_RUN_RETRY_EXHAUSTED` / `infrastructure_failed` | apply the canonical infrastructure retry/replacement policy; never treat as agent quality |
| `EVAL_INCOMPLETE` | report that the required replicate set could not be completed; it is not a run or agent-failure score |

There is no execution-failure ID for wrong answers, unsupported claims,
hallucinated citations, causal overreach, or other quality defects in an
otherwise schema-valid completed run.

## 7. Canonical infrastructure policy reference

The human-approved provider-attempt, total-retry, and replacement caps—and
same-logical-turn replay semantics—are normative only in
`docs/agent/execution_taxonomy_v0.1.md`. This protocol does not duplicate those
constants. Evaluation applies that policy to
`INFRA_RUN_RETRY_EXHAUSTED`: a successful permitted replacement fills the same
scheduled slot; exhausted replacement capacity makes the evaluation incomplete
with status `EVAL_INCOMPLETE` and does not impute an agent-quality zero.

## 8. Denominators and unchanged parent semantics

Terminal `FAIL_*` runs remain scheduled reportable replicates and contribute
zero to metrics requiring valid completion. Recoverable `EVT_*` counts are
reported separately. `RUN_COMPLETED` is scored normally regardless of answer
quality. An unresolved infrastructure slot is disclosed as missing
infrastructure, not silently excluded or converted to agent error.

All other v0.2.1 aggregation, three-run, no-best-run, evidence, citation,
numeric, source-scope, causal, and judge-boundary rules remain unchanged.
