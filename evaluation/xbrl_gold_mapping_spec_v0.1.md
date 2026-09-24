# Gold-to-XBRL mapping specification v0.1

Status: **draft evaluation-only specification; contains no DEV or TEST mapping
rows**

This contract defines closed unit normalization, precision and sign semantics,
deterministic candidate generation, review lineage, and target finalization. It
does not modify gold, build a mapping, implement an evaluator, or authorize
locked-TEST access.

Normative companions are `evaluation/xbrl_mapping_schema_v0.1.json`,
`evaluation/xbrl_mapping_review_rubric_v0.1.md`, and
`evaluation/eval_protocol_v0.2.2.md`.

## 1. Decimal lexical contract

Every value, factor, quantum, tolerance, and interval endpoint is parsed from a
plain decimal string into `Decimal`. Binary float is forbidden. Numeric strings
match `^[+-]?[0-9]+(?:\.[0-9]+)?$`; scientific notation, commas, symbols,
`NaN`, and infinities are invalid. Canonical serialization uses plain notation,
removes insignificant fractional zeroes, and writes every signed zero as `0`.

Implementations use a local Decimal context sufficient for the exact operands.
Parsing, scaling, subtraction, and tolerance comparison trap `Inexact` and
`Rounded`. The only intentional rounding is the registered quantum operation.

## 2. Closed unit-dimension registry

The evaluator representation is closed:

| submitted/gold label | dimension | canonical unit | factor | rule ID |
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

The four scaled share labels are generic evaluator representations. They do not
authorize spelling variants or other aliases.

Normalization is exactly:

```text
canonical_value = Decimal(submitted_value) * Decimal(factor)
```

It preserves sign and is representational, not derived arithmetic; it does not
require CalculatorTool.

### 2.1 Authoritative raw-XBRL aliases

Only these raw-unit associations are registered:

| raw XBRL unit | dimension | canonical unit | alias rule ID |
|---|---|---|---|
| `USD` | `monetary` | `USD` | `raw_xbrl_usd_v0.1` |
| `shares` | `share_count` | `shares` | `raw_xbrl_shares_v0.1` |
| `USD/shares` | `monetary_per_share` | `USD_per_share` | `raw_xbrl_usd_per_shares_v0.1` |
| `pure` | `ratio` | `pure` | `raw_xbrl_pure_v0.1` |

Every approved path preserves the raw authoritative string plus the evaluator
dimension, canonical unit, normalization rule, and raw-alias rule.

`USD_per_basic_share` and `USD_per_diluted_share` normalize to the same
dimension and may both correspond to raw `USD/shares`. Unit matching therefore
cannot distinguish basic from diluted EPS and cannot establish adjusted,
GAAP, or non-GAAP basis. Exact concept semantics, gold semantics, and review
must establish those properties. A unit alias never overrides concept/basis.

### 2.2 Layered matching and unknown units

Unit comparison proceeds in this order:

1. **Exact label identity.** If the submitted and reference unit strings are
   exactly equal, record `unit_match_status="exact_label_match"`. This is valid
   even when the label is unregistered. Compare numeric values directly in the
   unchanged label under the frozen precision/sign rule; perform no conversion.
2. **Registered equivalence.** If labels differ, require an exact relationship
   in the frozen registry, compatible registered dimensions, and exact Decimal
   scale conversion. Record
   `unit_match_status="registered_equivalence"` and the applicable registered
   rule ID.
3. **No relationship.** If different labels have no registered relationship,
   record `unit_match_status="unregistered_unit"` and reject unit equivalence
   without crashing.

Exact-label identity states only that both sides declare the same string. It
does not infer a semantic dimension, alias, scale, or registry entry and has no
registered rule ID. Unit success never overrides concept, period, sign, basis,
dimension/context, or precision mismatch. Audit records preserve both raw unit
strings, the match status, and a rule ID only for registered equivalence.
Equality is codepoint-for-codepoint on the schema-parsed strings; this contract
does not trim whitespace, fold case, or rewrite punctuation.
An individual unknown-unit normalization record may still carry
`unit_match_status="unregistered_unit"` as its registry-lookup result; the
pairwise candidate/path comparison separately records `exact_label_match`.

A new alias requires a versioned evaluation revision and cannot be added during
locked TEST.

`0.56 pure == 56 percent`. `percentage_point` is a different dimension and is
never coerced to/from `percent`. `basis_point` remains unregistered because no
frozen non-gold contract requires it.

## 3. Gold-recorded precision

Every target resolves frozen precision metadata to one registered rule before
candidate review. Mapping candidate generation and evaluator numeric comparison
use the same function.

The comparison coordinate is the registered canonical unit after registered
equivalence, or the unchanged raw label/value after exact-label identity. An
unregistered exact label acquires no semantic dimension from this coordinate.

### 3.1 Registered rules

- `precision_exact_v0.1`: values in the comparison coordinate are exactly
  equal.
- `precision_rounding_quantum_v0.1`: a frozen positive integral power-of-ten
  quantum `q` is expressed in the comparison coordinate and
  `q * to_integral_value(candidate / q, ROUND_HALF_EVEN) == gold`.
- `precision_absolute_tolerance_v0.1`: a frozen nonnegative comparison tolerance
  `t` permits `abs(candidate - gold) <= t`.

Every non-exact record includes `precision_rule_id`, its frozen `rule_source`,
the quantum/tolerance, and the exact inclusive comparison interval and unit.
For quantum rounding, the interval must be the exact set implied by the frozen
display value, quantum, and `ROUND_HALF_EVEN`, including endpoint inclusion as
determined by the tie rule. For absolute tolerance it is `[gold-t, gold+t]`.

A reviewer may not invent or widen tolerance, choose a rule after observing a
candidate, or infer significant digits from display text. If no registered rule
exists, no review-time rule is created; the case requires source checking and
may finalize as `unmappable`.

## 4. Sign and basis

Normalization never flips sign and no operation uses `abs(value)` to establish
equivalence. Every target records display sign, sign basis, canonical economic
sign/value when resolvable, and accounting/economic basis.

For mapping, `same_sign` is the normal relationship. An opposite-sign fact may
be accepted only on one path as `opposite_sign_explicitly_approved`. That path
must record:

- gold/display sign;
- gold canonical/economic sign;
- authoritative XBRL sign;
- declared basis relationship;
- source-bound rationale;
- completed source check; and
- `review_status="APPROVE"`.

The exception is path-specific; it is never promoted to a concept rule,
table-wide reversal, or global alias. Insufficient evidence remains
`NEEDS_SOURCE_CHECK`.

### 4.1 Agent answer versus gold

Agent scoring does not inherit mapping sign exceptions. Every acceptable answer
is pre-registered as a gold variant containing `variant_id`, value/unit,
precision rule, basis, sign convention, and optional `variant_family`.

An agent answer is acceptable if and only if it matches one registered variant
under the closed unit registry, that variant's frozen precision rule, exact
sign/basis requirements, and existing answer-family consistency rules. The
agent may name the registered basis it claims; it cannot make a wrong sign or
value acceptable by inventing a basis label. For linked values, mixing
otherwise valid variants from incompatible families remains invalid.

## 5. Artifact identities and status namespaces

Each approved path independently pins authoritative `fact_locator`, accession,
company, concept, `context_ref`, raw unit, raw-alias rule when registered,
submitted/reference units, comparison value, unit-match mode, instant or
duration dates, dimensions, optional `chunk_id`, and reviewed sign
relationship. Approved paths form an OR-set and need not share filing-local
`context_ref`.

Candidate review status is exactly:

- `APPROVE`: this candidate represents the same economic target;
- `REJECT`: evidence establishes this candidate does not; or
- `NEEDS_SOURCE_CHECK`: available structured metadata are insufficient.

These do not directly determine target status. In particular, `REJECT` does
not mean no counterpart exists, and `NEEDS_SOURCE_CHECK` is not itself a final
target status.

Final direct-target mapping status is exactly:

- `mapped`: one or more approved paths completed review;
- `no_xbrl_counterpart_in_frozen_corpus`: the complete frozen search found no
  approved or unresolved eligible counterpart in the local corpus; or
- `unmappable`: a potentially relevant structured candidate or semantic case
  cannot be adjudicated faithfully under the frozen representation/rules.

No-counterpart is a data-availability result only, not an external-world claim,
evaluator failure, or agent error. Unmappable is an evaluator/mapping limitation
and is also not automatically agent error. Both retain legacy chunk authority;
only unmappable contributes to the reported unmappable rate.

Derived targets are not direct mapping targets. They use
`mapping_resolution_mode="derived_via_inputs"`, a null direct mapping status,
and the AND of reviewed required-input target IDs. They are never searched by
their final numeric value. Resolution mode does not itself establish grounded
support: every required input must be independently adjudicable through an
allowed frozen legacy-chunk or approved-XBRL provenance route. Any unsupported
required input makes the derived target ineligible for full grounded
correctness.

## 6. Sequential deterministic candidate generation

The sequence is mandatory:

1. generate Stage-1 candidates;
2. review Stage 1;
3. record approved Stage-1 lineage;
4. generate Stage 2 only from that approved lineage;
5. review Stage 2;
6. generate Stage 3 for still-unresolved targets;
7. review Stage 3; and
8. finalize direct-target status.

Candidates record `candidate_id`, `candidate_stage`, `parent_candidate_id`
where applicable, `generation_rule_id`, precision and unit match state,
initial/final review status, and rationale. No separate Git commit is required
between stages, but lineage is machine-auditable. Stable ordering is by
`(candidate_stage, accession, concept, context_ref, fact_locator)`.

Cross-record semantic validation supplements JSON Schema validation: candidate
IDs are unique within a target; each Stage-2 `parent_candidate_id` resolves to
a Stage-1 candidate in that target whose final status is `APPROVE`; copied
parent status agrees with the parent record; every approved path resolves to an
`APPROVE` candidate and exactly reproduces that candidate's authoritative fact;
recorded completion counts equal the candidate records; and a derived target's
support-record IDs equal its required-input IDs. Derived grounding eligibility
is `eligible` only when every support record is `adjudicable_supported` through
an allowed frozen route. An `exact_label_match` record also requires byte-for-
byte equality of the preserved submitted/reference labels and a null registered
rule ID. Any mismatch fails the mapping artifact closed.

### 6.1 Stage 1 — direct chunk-linked discovery

For a target with approved legacy chunks, enumerate facts whose authoritative
`chunk_id` equals an approved gold chunk. Require target entity, unit
compatibility under the exact-label-first procedure in Section 2.2, numeric
equivalence under the pre-registered precision rule, and compatible sign/basis.
Preserve concept, dates, dimensions, filing, and fact identity. Chunk plus value
never auto-approves a candidate.

The sole discovery exception is a directly linked fact whose value in the
applicable comparison coordinate is the exact sign-negation of the target under
the same precision representation. It may be emitted with
`numeric_relation="opposite_sign_magnitude_only"`, an unresolved proposed sign
relationship, and `NEEDS_SOURCE_CHECK`; it is explicitly not numerically
equivalent and cannot be approved without the path-specific sign procedure in
Section 4. This exact-negation branch is not an `abs(value)` matching rule and
is not available for unconstrained Stage-3 value search.

### 6.2 Stage 2 — approved-lineage exact duplicate discovery

Each Stage-2 candidate must name a Stage-1 parent whose final review status is
`APPROVE` and satisfy all of:

1. same entity;
2. same exact XBRL concept;
3. same economic instant or exact duration dates;
4. same sorted axis/member structure;
5. exact same signed numeric quantity after exact-label identity or registered
   normalization, as applicable; and
6. compatible approved sign/basis relationship.

Raw unit strings may be identical without a registry entry; if they differ,
they may compare only through registered exact aliases/scales.
`context_ref` may differ because it is filing-local. A recast comparative or
any other different numeric value is not a Stage-2 duplicate even if concept
and period match; it requires its own direct gold relationship and cannot be
forced into Stage 2.

### 6.3 Stage 3 — mechanical constrained search

For each unresolved target, enumerate only frozen facts satisfying every
available predicate:

1. fact entity equals target entity;
2. value matches under the target's frozen precision rule;
3. unit comparison passes exact-label identity first, or otherwise passes a
   registered compatible equivalence;
4. exact target instant or duration dates match;
5. exact axis/member structure matches when target requirements exist;
6. accession belongs to the target entity; and
7. the filing directly covers the target period, or is a later filing that
   explicitly contains the target period as a comparative context.

There is no reviewer-defined search scope. Reviewers adjudicate only emitted
candidates. Stage 3 alone may emit a different concept; every such candidate
starts `NEEDS_SOURCE_CHECK` and can become `APPROVE` only after source-bound
review establishes the same economic target.

If a required predicate cannot be derived from frozen metadata, do not infer or
broaden it. Record the limitation for source review and, if frozen semantics
cannot resolve it, finalize as `unmappable`.

## 7. Finalization rules

After all sequential review:

- assign `mapped` when at least one candidate is approved and copied exactly
  into the approved OR-set;
- assign `no_xbrl_counterpart_in_frozen_corpus` only when Stage 1, applicable
  Stage 2, and Stage 3 completed, no candidate is approved, and no unresolved
  candidate/constraint remains that requires source checking or unmappable
  treatment;
- assign `unmappable` when a potentially relevant candidate or semantic
  limitation remains but frozen rules cannot decide safely.

No direct chunk-linked fact is not enough for no-counterpart. A rejected
candidate alone also does not prove no-counterpart until the complete search
finishes. No-counterpart and unmappable records have no approved XBRL path and
retain legacy paths. XBRL provenance may still receive identity/semantic checks
where deterministically possible, but no approved-path credit is awarded.

## 8. Review and anti-leakage timing

The rubric adjudicates entity, concept, value, registered precision, unit
dimension/alias, sign/basis, temporal meaning, dimensions, comparative role,
authoritative identity, and same economic target. Review never expands search
or uses agent outputs.

Before first DEV output, freeze this algorithm/schema/rubric, build and review
the DEV mapping, and freeze the mapping plus deterministic evaluator. Do not
build TEST mapping then.

Before DEV mapping construction, the authorized future D session enumerates
all distinct DEV-gold unit labels and compares them with this frozen registry.
Its unit-completeness audit classifies each label as `registered`,
`exact-label-only supported`, or `requires proposed new evaluator alias`.
Nothing is added silently. Any proposed alias requires a reviewed, versioned
evaluation-contract change before DEV agent outputs exist. This procedure is
specified here but no DEV unit row is read in this session.

At the first authorized `agent_v0.1` TEST checkpoint: freeze the agent and
evaluation stack, log access, open TEST gold, run this frozen algorithm and
rubric, freeze `test_xbrl_map_v0.1`, and only then generate or inspect TEST
outputs. Reuse that map later unless a versioned protocol says otherwise.
TEST units remain unseen until that authorized checkpoint. Exact-label fallback
remains available there, but no alias may be added during the checkpoint.

## 9. Versioning and closed failure behavior

Algorithm version is `xbrl_gold_mapping_algorithm_v0.1`; schema version is
`xbrl_gold_mapping_schema_v0.1`; rubric version is
`xbrl_mapping_review_rubric_v0.1`.

Malformed records, unregistered units/rules, non-Decimal values, missing
constraints, invalid lineage, inconsistent duplicate identities, or an
authoritative fact mismatch fail closed and never receive equivalence credit.
They are not repaired during scoring. Semantic changes require an explicit new
version and cannot be applied retroactively within a checkpoint.
