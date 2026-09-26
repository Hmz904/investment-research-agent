# D2 deterministic evaluator successor contract supplement v0.2

Status: **INDEPENDENT CONTRACT/TEST AUTHOR FREEZE — CD-01 AND CD-02 RESOLVED**.
CD-01 and CD-02 are explicit prospective human resolutions. Historical normative source authentication succeeded.
This document and its successor schemas/tests were authored anew from authenticated
v0.1 normative files and permitted higher-level sources. Neither previous blocked
v0.2 draft set is an authority or a source. Historical v0.1 files remain unchanged.

## S1. Authority, authentication and validation

Precedence, highest first: evaluation protocol v0.2.2 with inherited v0.2.1/v0.2;
execution taxonomy v0.1; agent-output schema v0.1.1; XBRL mapping specification
v0.1.2 with inherited v0.1; historical D2 supplement v0.1; historical D2
preregistration v0.1; historical D2 specification v0.1. CalculatorTool v0.1
provides the explicitly referenced arithmetic grammar/context. XBRLTool v0.1
provides artifact-supported fact fields and identity construction. Current human
CD-01 supplies its explicit new output-contract resolution; CD-02 supplies the
coherent variant-selection and canonical partial-diagnostic convention. The human-provided
eight findings are the only historical implementation audit input.

The historical candidate manifest SHA-256 is
`48df2edd4b8d6e7362f27404d71b8e833860f465b6ee1d5fca15b10416ebd044`.
`historical_source_authentication_v0.2.json` records nine allowed imported paths,
their exact historical hashes and successful verification. The historical
cleanroom was accessed only to read the manifest and hash/copy those allowed
normative files. References in them never authorize opening locked sources,
implementation, old tests, outputs or review records.

The earlier clean attempt was SOURCE AVAILABILITY / ISOLATION CONFIGURATION
BLOCKED, not a human decision. Rehydration resolves that problem. CD-02 is a
separate partial-variant decision, now explicitly resolved by the human. Its
source conflict and resolution are retained in `d2_v2_contract_decisions_required.md`.

All machine input is strictly parsed, schema-validated and semantically validated
before adaptation/scoring. Draft 2020-12 format checking is mandatory. Reject
unknown keys, duplicate JSON keys, wrong types, nonfinite numbers, unresolved
schema references and unknown declared formats. No string/list/bool coercion,
row dropping, missing-field default or fallback parser is allowed. JSON Schema
cannot attest cross-record equality, acyclicity or artifact authenticity:
semantic constraints below and in `x-semantic-validation` are mandatory parts
of validation, not optional comments. A shape-valid object is not thereby an
authenticated fact, reviewed path or valid evaluator input.

Raw JSON number lexemes go directly to Decimal, including agent-output numbers;
never decode via binary float. Plain-string mapping/calculator inputs obey their
stricter plain-decimal grammar, which excludes exponent notation. Canonical
numeric output is plain notation, no trailing fractional zeroes, signed zero `0`.
Authoritative manifests bind source bytes, run output bytes, corpus, benchmark,
protocol, schema and adapter identities before scoring. Unknown future protocol,
schema, fingerprint, adapter or taxonomy is EVAL_CONTRACT_MISMATCH; malformed
supported data is EVAL_INPUT_INVALID. Neither is an agent zero.

### Eight-blocker hierarchy matrix

| Blocker | Authoritative source | Lower-level conflict or gap | Successor resolution |
|---|---|---|---|
| A calculation references | protocol v0.2.1 §2; taxonomy §3; human CD-01 | prereg D03 requires graph validity but no semantic-invalid completed-run output; historical audit reports cycles/dangling refs mishandled | S3, graph/result schemas; preserve runtime and EVAL_OK |
| B multiplicity | protocol v0.2.1 §5; supplement R5; GoldBundle multiplicity | R5 recognizes multiplicity but the historical implementation reportedly ignored it | S4, expanded occurrence assignment, group-level AND correctness |
| C negative tolerance | protocol v0.2.2 §2; mapping v0.1 §3; supplement R7 | historical audit reports malformed frozen tolerance treated as agent mismatch | S5, strict nonnegative config validation → EVAL_INPUT_INVALID |
| D arbitrary quantum | protocol v0.2.2 §2; mapping v0.1 §3.1 | precision v0.1 schema admits any positive decimal; R7/spec also say independently round gold and candidate | S5, exact powers of ten; higher-level candidate-rounding equation replaces dual-rounding |
| E concrete DEV source map | prereg B2; supplement R2; protocol v0.2.1 §2 | normalized schema did not validate the raw concrete DEV shape before adaptation | S6, strict source schema plus cross-record validation before projection |
| F no-counterpart state | protocol v0.2.2 §4; mapping v0.1 §5 | R2 only lists unmappable as NO_APPROVED_XBRL_PATH | S6, both nonmapped source states accepted; retain legitimate legacy routes |
| G fact existence | protocol v0.2.1 §§7.1,7.4; XBRLTool contract | historical spec says XBRL identity is in normalized approved map; no complete index schema | S7, full authoritative index independent from target-specific authorization |
| H replacement exhaustion | taxonomy §§4–6; protocol v0.2.2 §§6–8; prereg D38 | original result schema has no explicit evaluation-completion field | S2/S9, EVAL_INCOMPLETE separate from EvaluatorStatus |

A further hierarchy correction is mechanical: R2's all-approved-XBRL derived
chain cannot remove the higher-level legitimate legacy-input route. A derived
target with one nonmapped leaf has no fully approved XBRL chain but may still
satisfy the GoldBundle's required input provenance through legacy chunks.

## S2. Request, runtime, error and completion contracts

`evaluation_request_v0.2.schema.json` defines one explicit scheduled-slot request.
It contains normalized gold, slot record, raw agent-output JSON and its SHA,
chunk catalog, optional normalized XBRL map, optional authoritative fact index,
and fingerprint-bound numeric values. There is no implicit split-global state.
The `split` label is metadata only and never selects scoring or parsing code.
The source loader authenticates supplied catalogs against frozen manifests;
synthetic tests supply synthetic catalogs with the same structural contract.

`evaluation_slot_record_v0.2.schema.json` preserves R1's normalized execution
namespace: RUN_COMPLETED; the five literal FAIL statuses; and
INFRA_RUN_RETRY_EXHAUSTED. The latter is the normalized identifier for raw
`infrastructure_failed`; it is not a quality failure. EVAL_INCOMPLETE belongs
only to evaluation completion, never slot execution or EvaluatorStatus.

A slot has one original attempt and at most one replacement, with distinct IDs.
The replacement names the original attempt and the same scheduled slot. Its
predecessor must be INFRA_RUN_RETRY_EXHAUSTED. The effective attempt is the last
attempt; its status and ID must equal the slot's fields. Replacement after a
completed run/terminal agent failure, a third attempt, mismatched slot links,
duplicate IDs or impossible flags is EVAL_INPUT_INVALID. Status/event enum
recognition precedes generic schema errors so unknown future IDs and the inactive
EVT_TOOL_RESULT_TOO_LARGE yield EVAL_CONTRACT_MISMATCH, not a catch-all zero.

The original R1 legacy mappings remain exact: success→RUN_COMPLETED;
tool_budget_exhausted→FAIL_TOOL_BUDGET_EXHAUSTED;
step_budget_exhausted→FAIL_STEP_BUDGET_EXHAUSTED;
malformed_final_output→FAIL_FINAL_SCHEMA_INVALID;
orchestration_failure and unrecoverable_tool_error→
FAIL_AGENT_ORCHESTRATION_UNRECOVERABLE. provider_failure requires an explicit
infrastructure exhaustion sidecar. FAIL_NO_VALID_FINAL_OUTPUT requires an explicit
canonical status. Never infer a status from free text or quality.

Preserve taxonomy caps of 3 provider attempts per request, 8 infrastructure retries
per run and 1 replacement per slot, with same-logical-turn replay and immutable
prior state. Evaluator authoring does not run or modify orchestration.

EvaluatorStatus remains the authenticated four-value namespace:
EVAL_OK, EVAL_INPUT_INVALID, EVAL_CONTRACT_MISMATCH, EVAL_INTERNAL_ERROR.
Unexpected evaluator faults after accepted inputs use the last value. Non-OK
results have metrics=null, included_in_scored_denominator=false,
checkpoint_valid=false and evaluation_completion=null. They cannot masquerade
as EVAL_INCOMPLETE. An invalid source map/gold/precision cannot be ignored merely
because the agent answer would fail anyway. Unknown source representation is
EVAL_INPUT_INVALID per historical R3, distinct from a recognized version's hash
or contract-identity mismatch.

RUN_COMPLETED requires a present schema-valid raw output and matching SHA. Missing
or schema-invalid completed payload is EVAL_INPUT_INVALID. Terminal FAIL records
carry no scoreable agent_output; malformed original payload may be retained by
external audit storage but is not repaired/imported as scoreable data. No
fabricated claim-level diagnostics are generated for absent terminal payloads.

A successful replacement fills its original denominator slot. An effective
infrastructure record is an explicitly missing slot with metrics=null, no imputed
quality zero, and included_in_scored_denominator=false. At a finalized exhausted
replicate set, completion is EVAL_INCOMPLETE. A pending, still-permitted replacement
is not a finalized evaluation input and must not be silently scored. Terminal
FAIL_* retains its slot and zeroes applicable completion-dependent metrics.
Recoverable active EVT_* events do not zero a later completion.

`evaluation_completion_v0.2.schema.json` records scheduled/scored slot counts and
missing infrastructure IDs. Counts are nonnegative, IDs unique, and scored plus
missing equals scheduled for EVAL_OK finalized evaluations. EVAL_COMPLETE has no
missing slots; EVAL_INCOMPLETE has at least one. This field is separate from
EvaluatorStatus even when both contain the prefix EVAL_.

## S3. CD-01: calculation-reference graph

**New human resolution CD-01.** A schema-valid RUN_COMPLETED output containing
an unresolved source_calculation_id, self-reference, two-node cycle or longer
cycle is an AGENT-OUTPUT SEMANTIC CONTRACT VIOLATION.

Preserve execution_status=RUN_COMPLETED and evaluator_status=EVAL_OK. Emit
agent_output_contract_valid=false and INVALID_CALCULATION_REFERENCE_GRAPH.
Retain the scheduled slot in the scored denominator; complete_numeric_answer=false.
No graph-dependent derived/material claim receives numeric correctness credit,
including final-value credit. A direct claim proven independent of the invalid
graph remains eligible under ordinary rules. Never substitute EVAL_INPUT_INVALID,
EVAL_CONTRACT_MISMATCH, EVAL_INTERNAL_ERROR, EVAL_INCOMPLETE, infrastructure failure
or synthetic FAIL_* for this condition.

Construct edges K→J from every prior-calculation input of K referencing J.
Inspect all submitted calculations, not only a final claim's reachable subset.
Reject unresolved calculation_ids on claims as a dangling calculation dependency
under this graph contract. Mark existing nodes in a cyclic component or reaching
one, and existing nodes reaching a missing reference. Dependent claims are those
reaching marked or missing nodes. Diagnostics contain unique sorted existing
invalid calculation IDs and dependent claim IDs. Traversal must terminate on
cycles. A disconnected invalid calculation still invalidates the output contract
and complete answer, while independent direct claims can pass.

Non-graph duplicate claim/calculation/input IDs and unresolved answer-claim IDs
retain historical R4's EVAL_INPUT_INVALID treatment. Do not silently broaden
CD-01 to rewrite already specified unrelated errors. For a valid graph the graph
flag is true with empty diagnostics; other contract/quality checks still apply.
The machine schemas explicitly represent graph validity and output-contract
validity separately from schema_valid and raw execution status.

## S4. Assignment, multiplicity, variants and GoldBundle

`gold_bundle_v0.2.schema.json` retains the authenticated normalized target/group
interface, tightens precision and fact paths, and closes judge-gold structures.
Validate unique group, variant, target, path and role IDs in their declared scope;
all numeric-target and required-input references resolve; target dependencies
are acyclic; target/variant duplicate records agree on shared semantic fields;
formula roles equal the required role set; no unversioned format guessing occurs.
Numeric targets/catalogs are question-scoped. A target-specific approved path
cannot transfer merely because another target has the same value/accession.

Source dispatch preserves historical explicit declared formats. Normalized v0.2
is accepted directly. A declared v0.1 bundle is validated with its authenticated
schema, then upgraded using only S5 and the exact authoritative identity catalogs;
missing required semantic identity cannot be fabricated. The documented DEV CSV
adapter is an explicit preprocessing representation, never inferred from paths
or split labels. Unsupported source representations fail loudly. Future TEST
must use a supported declared source or frozen normalized v0.2; no parser patch
or scoring change is authorized at the checkpoint.

Answer groups retain frozen order. Expand a group with multiplicity m into m
required occurrences, numbered 1…m. Eligible material numeric answer claims retain
serialized claims-array order; answer_claim_ids identifies final-answer membership
but never reorders claims. No current v0.1.1 claim accepts answer_group_id, so do
not add a field forbidden by the frozen schema. If a separately frozen future
schema explicitly permits stable bindings, its versioned adapter must honor them
first, reject unknown/duplicate explicit IDs as R5 requires, and never infer them.
The current contract does not authorize that future schema.

Positional assignment consumes one eligible claim per expanded occurrence.
Missing claims leave occurrences unmatched. Extras stay extra and cannot replace
an earlier mismatch, fill two occurrences or spill across explicit groups.
No semantic/value/embedding/best-fit matching, reordering or permutation search.
Numeric value correctness counts a group only when all m assigned occurrences
have numeric_correct=true. Its ratio remains numeric-correct GROUPS / required
GROUPS (protocol §5), with occurrence diagnostics;
multiplicity does not silently replace this denominator with occurrence count.

Groups are AND requirements; variants in one assigned group are OR alternatives.
Value correctness remains a numeric component: matching the final number can
retain value credit when other deterministic requirements fail. Group `correct`
and complete_numeric_answer require complete deterministic pass of every required
occurrence, subject to CD-01 and question-family consistency. They do not imply
judge-dependent strict grounded correctness.

### S4.1. CD-02 — Human resolution: coherent variant selection

Construct eligibility BEFORE evaluating partial results. Eligibility uses only
frozen group membership, approved family membership, permitted explicit identifiers
and structural input/formula binding applicability. Formula correctness, input
values, provenance matches, evidence coverage, numeric closeness, number of passed
components and semantic/judge metrics MUST NOT influence eligibility. Structural
applicability is not a formula-similarity or formula-correctness filter. Missing or
wrong inputs ordinarily fail the applicable candidate; they do not justify hiding
that candidate as ineligible. No best-fit permutation or cross-group rescue.

If the source schema supplies a valid explicit variant or family identifier,
restrict eligibility to it before scoring. Unknown identifiers or contradictory
explicit variant/family bindings are contract-invalid under R4/S2:
EVAL_INPUT_INVALID, null metrics, never fallback. Raw v0.1.1 supplies neither
identifier, and adding one to that raw output remains a schema error. The versioned
normalized selector interface below exercises identifier handling without extending
or authorizing a new agent-output schema.

Evaluate the COMPLETE deterministic predicate independently for each eligible
variant: final numeric semantics (value, unit, period, basis, sign, precision),
all required input semantics, approved provenance, applicable frozen formula and
arithmetic, and family compatibility. Every component uses the SAME candidate's
requirements. Direct variants have no derived formula/input requirements. Judge
fields are excluded from this predicate and remain PENDING_JUDGE.

1. At least one complete passing variant: complete deterministic pass is true;
   report the lexicographically smallest COMPLETE PASSING variant_id. A smaller
   failing variant cannot override a passing variant. The selection is reporting
   only; all its component diagnostics come from that passing variant.
2. Eligible variants exist but none completely passes: complete pass is false;
   select the lexicographically smallest ELIGIBLE variant_id as the CANONICAL
   DIAGNOSTIC VARIANT. Every variant-dependent reason, formula/input report and
   explicitly defined component metric uses that single variant, including its
   input denominator. No numeric, formula, provenance or partial-score maximum.
3. No eligible variant: select null; complete pass is false; report
   NO_ELIGIBLE_VARIANT. No alternative family may be invented or searched for.
   No candidate-dependent diagnostics exist: null inapplicable scalar diagnostics,
   empty input_results, false numeric/approved-path fields. A missing assigned
   claim has an empty eligible set; its required occurrence still fails.

IDs use Unicode codepoint lexicographic order, independently of serialization
order. Eligible and complete-passing ID arrays are sorted and unique. The new
variant_selection_v0.2 schema records eligible IDs, passing IDs, selected ID,
mode and complete pass. The selected ID MUST be the minimum of the proper set;
passing IDs MUST be a subset of eligible IDs. These are mandatory semantic
validation checks in addition to the closed JSON schema. `variant_id` in occurrence
reports mirrors selected_variant_id. `input_results` preserves the selected
variant's frozen required-input order and roles/target IDs; none may come from a
different candidate. Occurrence reason_codes contain only canonical diagnostics
plus the selection reason; nonselected mismatch reasons cannot leak into metrics
or the aggregate reason list. Graph/global input errors remain independently
reportable. Input, formula and arithmetic failures use REQUIRED_INPUT_MISMATCH,
FORMULA_MISMATCH and ARITHMETIC_MISMATCH, respectively; deduplicate/sort reasons.

Every answer group, including all its multiplicity occurrences, uses one coherent
family. Question consistency groups additionally retain R8 across groups: all
selected components and upstream input families must be compatible; V1/V2 mixing fails consistency and complete numeric
answer. CD-02 does not permit changing positional assignment, repairing input
bindings or maximizing component scores to achieve consistency.

This prospectively extends R8's reporting tie rule to nonidentical passing sets
and the formerly undefined no-complete-pass case. It does not change the frozen
historical documents. Regression cases A–H are literal independent expectations.

## S5. Units, exact precision and sign

Use exactly the 14-label registry in protocol v0.2.2 §1 and raw-XBRL aliases in
mapping v0.1 §2. Identical labels yield exact_label_match even when unregistered;
no dimension or scale is inferred. Different labels need a registered
same-dimension exact relationship, producing registered_equivalence and its rule
ID, or yield unregistered_unit and ordinary mismatch without crashing. Strings
are codepoint-exact; do not trim, case-fold or rewrite punctuation. Basic/diluted
EPS aliases do not override basis. percentage_point is distinct from percent/pure.
Normalization is exact Decimal multiplication by the positive frozen factor and
preserves sign. It needs no CalculatorTool call.

Precision source precedence is R7: explicit tolerance, otherwise nonnegative
integer display_precision p→quantum 10^-p, otherwise EXACT. Strictly validate
before normalization. A malformed/negative tolerance is EVAL_INPUT_INVALID and
cannot fall back to p or become an agent mismatch. Zero tolerance is valid.
Do not accept Python float as a plain-decimal configuration representation.
Booleans are not precision integers. Normalize tolerance/quantum into the same
comparison coordinate as gold before comparison; preserve source metadata.

QUANTUM must be positive and exactly an integral power of ten. 1, 10, 0.1 and
0.01 pass; 0.03, zero and negative values fail. The normalized schema uses a
canonical plain-decimal lexical representation. Valid alternative plain lexical
spellings may be canonicalized only after strict Decimal validation. Exponents,
NaN, infinity, commas and symbols are forbidden in mapping/calculator strings.

Higher-level mapping §3.1 overrides historical R7/spec's dual-rounding language:
QUANTUM passes iff q × round_half_even(candidate/q) equals the UNROUNDED reference.
Do not round gold to invent equivalence. An off-grid reference has an empty
preimage; its interval is encoded as equal reference endpoints, both exclusive.
EXACT uses exact coordinate equality. ABS_TOLERANCE uses inclusive
abs(candidate−reference)≤t. Preserve sign before precision; no magnitude matching,
float epsilon or universal fallback tolerance.

Every precision record carries rule ID, source encoding/value, reference,
comparison unit and exact interval. Recompute the interval and reject disagreement.
EXACT interval is the singleton reference, inclusive. Tolerance interval is
[reference−t,reference+t]. For on-grid quantum reference kq, bounds are ±q/2;
both ties are included iff k is even. For q=.1: 1.15 and 1.25 map to 1.2;
neither 1.25 nor 1.35 maps to 1.3. Negative boundaries use the same HALF_EVEN rule.
Canonical comparison arithmetic has enough Decimal precision to avoid unintended
rounding; trap unintended Inexact/Rounded. This is separate from CalculatorTool's
intentional fixed precision 50 arithmetic context.

An approved opposite-sign XBRL mapping relation is exact-path-specific and requires
the frozen sign/basis rationale and approval metadata. It does not create an
agent-answer variant. Only separately registered signed answer variants may pass.

## S6. Strict concrete source map and normalization

`dev_xbrl_source_map_v0.2.schema.json` validates the concrete allowed DEV object,
not the incompatible older generic mapping envelope. Validate the entire source
before projection: IDs, semantic fields, nested fact identities, review partitions,
counts, temporal bindings, stage metadata and repeated lineage. No malformed row
may disappear during filtering. `normalized_xbrl_map_v0.2.schema.json` then
validates the emitted representation. All schema errors are EVAL_INPUT_INVALID.

Required semantic checks:

- Unique targets and candidate IDs; every candidate's target_id matches its owner;
  duplicated locator fields agree; reference IDs and upstream targets resolve.
- Approved/rejected/unresolved IDs form disjoint exact review-status partitions;
  their counts and final_status_counts agree with records; only APPROVE candidates
  enter approved paths. Documentary review strings do not override statuses.
- Each full approved fact identity matches the authoritative index; values match
  the separately bound numeric catalog; units, dimensions and dates are exact.
- Approved temporal selection belongs to its frozen closed set. All duplicate
  temporal/lineage copies agree. Resolved exact metadata is required before final
  mapped/no-counterpart status. Human-readable labels never establish dates.
- Stage-2 requires an approved Stage-1 parent and all higher-level same-entity,
  exact-concept, period/dimension/unit/signed-value predicates. Stage-3 requires
  frozen exact temporal and source scope. No stage is run during normalization.
- Derived source input arrays agree with lineage copies and form an acyclic AND
  dependency graph. No final derived fact is fabricated.

The concrete source schema closes currently empty Stage-2/3 candidate-array shapes
rather than accepting untyped objects. This is a declared DEV representation
limit, not a change to higher-level mapping discovery. Future data can supply a
schema-valid normalized map; source encodings outside a supported schema fail
closed instead of prompting checkpoint-time parser patching.

Normalization: mapped→DIRECT_APPROVED with nonempty exact reviewed paths;
unmappable and no_xbrl_counterpart_in_frozen_corpus→NO_APPROVED_XBRL_PATH with empty
direct paths. Preserve source_state so unmappable counts exclude no-counterpart.
Both retain legacy authority in GoldBundle. No-counterpart requires complete
applicable frozen search with no approved or unresolved candidate; missing exact
temporal adjudication is unmappable, not no-counterpart.

A source derived_via_inputs target becomes DERIVED_VIA_APPROVED_INPUTS only if
all recursive leaves have approved XBRL paths. Otherwise it has NO_APPROVED_XBRL_PATH
with source_state=derived_via_inputs, preserved required input IDs and no fabricated
approved upstream paths. Independently legitimate legacy input routes remain
eligible under protocol v0.2.2 §4. Thus neither status label alone confers full
provenance nor lack of XBRL approval suppresses valid chunk support.

Approved chunk paths retain OR between paths and AND between members. Multi-part
paths preserve every required part. Required derived inputs are AND. Where a source
requires combined chunk/XBRL evidence, it must enter through an explicit schema-bound
combined path; separate OR alternatives cannot be silently interpreted as AND.
The inherited GoldBundle path fields describe chunk or XBRL alternatives; unsupported
mixed source encodings fail as input-invalid rather than being flattened.

## S7. FrozenXBRLFactIndex v0.1 and provenance identity

Schema: `frozen_xbrl_fact_index_v0.1.schema.json`.
Fingerprint: `acaf087ee2c4fb7427377cae5f1968da26c75d4dfa565f67f1e056b2c4cc4eb6`.
Complete universe: exactly 7,839 facts, including 640 with no chunk linkage. Never
substitute the 7,199 linked facts or question-approved map as the universe.
No production fact data is imported/generated by this authoring session.

Identity rows contain only supported identity/context fields: doc_id, fact_id,
style-preserving concept, accession, fact_locator, stable_fact_id, context_ref,
entity identifier/scheme, raw unit plus direct/numerator/denominator measures,
exact instant/duration, ordered axis/member dimensions, optional authoritative
chunk linkage. `temporal.kind` packages the tool's period_type without inference.
Null unit or chunk link means source absence. No taxonomy URI, SEC frame, labels,
separate fiscal year, presentation metadata, inferred accounting basis or fabricated
link is permitted. Ordered dimensions remain source-ordered.

Validate locator=doc_id#fact_id and stable_fact_id=doc_id::fact_id, unique identities,
consistent filing/context/entity/unit identity, ISO dates and start≤end, exact row
count and sorted stable IDs. Validate every non-null chunk link independently
against the authoritative chunk catalog. No economic deduplication or same-period
fact substitution. A fingerprint string alone is not authentication: the upstream
artifact loader must verify source hashes and catalog correspondence.

FACT_IDENTITY_VALID means the submitted fact exists and all submitted identity
fields equal its authoritative row. APPROVED_PATH_VALID separately means that
identity-valid fact belongs to the question/target's reviewed path. A real
unapproved fact is identity-valid/path-invalid, never nonexistent or forged.
Report the two predicates per provenance record. A wrong raw accession/concept/
context/unit/date is wrong_fact_identity; a wrong optional link is wrong_chunk_linkage;
an absent locator is nonexistent_fact_locator. Missing optional chunk linkage is
not a penalty. No unlinked fact may masquerade as a narrative chunk citation.

The identity index includes nonnumeric facts. The request's separately bound
xbrl_numeric_values uses only tool-supported fact_locator and normalized_value;
it has exactly one row per authoritative identity and preserves null for nil,
dash or nonnumeric facts. Numeric structured provenance additionally requires
non-null value and nonempty raw unit (protocol v0.2.1 §7.1). Identity existence does
not invent numeric eligibility. Submitted schema v0.1.1 has no dimensions field;
validate authoritative context/map dimensions without adding forbidden raw fields.

Narrative identity requires exact chunk_id, accession, locator and allowed source.
Legacy citations gain only the chunk discriminator, never repaired identity.
Chunk identity and approved target membership are independent. Count every submitted
claim/input record separately; never pool provenance across owners. Hallucinated
identity counts only nonexistent IDs and falsely paired accessions. Other identity
failures are invalid but not automatically hallucinated. Mechanical outside-source
findings are separate; free-text reliance on excluded sources remains judge-dependent.

## S8. Derived binding, formula and arithmetic

Preserve R6 literally. If any input name exactly matches a required input_role,
all inputs must use exact required roles, with unique complete bindings. Mixed
explicit/unbound names are invalid. Otherwise use input array order against frozen
required-input order. No value matching, trimming or case folding. Names not equal
to any role are positional labels, not guessed unknown role references. Extra
inputs never repair a missing role and must also satisfy CalculatorTool use rules.
Every required input gets independent target, value, unit, precision, basis,
provenance and family validation. References to prior calculations recursively
validate the actual upstream lineage; no final-number shortcut.

Formula canonicalization removes only whitespace, redundant parentheses, inert
unary plus and insignificant Decimal literal zeros/signed zero, and renames local
input IDs to their bound role tokens. Use the CalculatorTool structural parse tree;
operator association/order is preserved. No commutation, distribution, factoring,
subtraction-to-addition rewrite or general symbolic equivalence. Compare to an
explicitly frozen canonical_formula; additional equivalent formulas need a frozen
variant. The example `(base + 0)` is different from `base` unless explicitly listed.

Arithmetic uses exactly CalculatorTool grammar, fresh Decimal Context precision 50,
ROUND_HALF_EVEN, left association, operator precedence, finite values, named inputs,
all supplied inputs used and no missing variables. Preserve its limits: 1,024
expression characters, 256 nodes, depth 32, 64 inputs, 1,024 chars/input decimal.
No Python eval/exec, functions, exponentiation or scientific literals. Recompute
the unrounded result and compare exactly; output/display precision is a separate
final comparison. Parse/domain failures in a schema-valid completed calculation
are deterministic calculation failures, not evaluator/internal errors.

A correct final number with a wrong formula, wrong required input or unsupported
input ordinarily retains final-value credit only. Complete numeric answer requires all required numeric inputs and, under CD-02,
a complete passing eligible variant for each occurrence. Formula/arithmetic/
provenance failures still retain the ordinary independent final-value component;
they cannot produce a complete group pass. Deterministic grounded prerequisites
remain necessary but not sufficient for judge-dependent strict grounding. CD-01 overrides final credit specifically
for graph-dependent claims. Independent direct claims retain ordinary treatment.
Final strict grounded correctness remains PENDING_JUDGE where support is unresolved.

## S9. Results, counts, pending judge and serialization

`deterministic_evaluator_output_schema_v0.2.json` is closed and supplies separate
runtime, evaluator status, completion, agent semantic validity, graph, assignment,
metric and error fields. Ratios preserve integer numerators/denominators with
0≤numerator≤denominator; no applicable observations means null, not 0/0 or zero.
Group results include occurrence IDs, selected variant IDs, unit/precision/sign/
basis audit fields and per-input correctness. Null denotes genuinely inapplicable
or unavailable information, not an inferred success.

Terminal failures contribute zero to applicable completion-dependent metrics and
retain their slot. Do not fabricate provenance records or formula diagnostics
from missing outputs. Exhausted infrastructure is missing, excluded from scored
quality denominators but retained in scheduled counts. Aggregate per metric and
retain per-question counts; no best-run selection or unrelated-score composite.
`deterministic_subtotal` is always null. Normal reportable evaluation still requires
three replicates per question; single-slot authoring fixtures are not run reports.

Every listed historical judge field is present as literal PENDING_JUDGE:
semantic_item_match, citation_support, material_claim_requires_citation,
causal_overreach, answer_claim_consistency, evidence_item_coverage,
evidence_all_parts_rate, evidence_weighted_partial_coverage,
evidence_weighted_strict_coverage, evidence_core_coverage,
evidence_strict_grounded_correctness, unsupported_material_claim_rate and
numeric_strict_grounded_correctness. No lexical, embedding, citation-presence,
approved-path or numeric proxy replaces them. They are excluded from deterministic
aggregates. Mechanical references, identity, math and path membership are not judge
fields. Additional semantic update/evidence metrics remain pending, not guessed.

Serialize UTF-8 JSON, sorted keys, compact separators, exact plain Decimal strings,
schema-declared array order and exactly one terminal newline. Diagnostic ID/reason
sets are deduplicated and lexicographically sorted; assignment/path/input arrays keep
frozen semantic order. No timestamps, generated IDs or process-global Decimal state.
Repeated identical requests produce identical bytes and SHA-256. Preserve all raw
input/output identities externally; no trace can silently overwrite source data.

## S10. Public test interface and static-only authoring boundary

A later implementation session supplies these versioned entry points in the
historically named evaluator module. This session does not import, inspect, run or
repair that module. Tests defer its import until their pytest fixture is executed
in the authorized implementation session. No wrapper may manufacture expected
behavior to bypass production scoring.

| Entry point | Input and result contract |
|---|---|
| evaluate_v0_2(request) | Request/result schemas above; mappings with raw output JSON; no implicit files or split-selected algorithms |
| adapt_precision_v0_2(metadata, reference_value=..., unit=...) | Strict tolerance/display_precision metadata → `{evaluator_status, precision, errors}`; precision null on error; S5 precedence and coordinate normalization |
| adapt_dev_xbrl_map_v0_2(source, source_sha256=..., fact_index=..., numeric_values=...) | Strict source object → `{evaluator_status, normalized_map, errors}`; no partial map on failure; supplied object hash is canonical source JSON SHA; an external strict byte loader preserves/authenticates original artifact bytes |
| audit_arithmetic_v0_2(expression, values, submitted_result) | Frozen calculator audit → `{arithmetic_correct, result, reason_codes}`; false and explicit reasons for input/parser/domain failure; no scoring shortcut |
| aggregate_metrics_v0_2(records) | Unique slot IDs, canonical statuses, applicability and integer counts → scheduled/scored counts, ratio/null, missing infra IDs, EVAL_COMPLETE/EVAL_INCOMPLETE, null subtotal; never consumes semantic pending as numbers |
| select_variant_v0_2(request) | variant_selection_v0.2 `$defs/request` → `$defs/response`; shared production selector, S4.1 semantics below |
| canonical_json_bytes(result), result_sha256(result) | Exact canonical serialization/hash contract; existing normative public names retained |

The selector's approved_variants is a trusted normalized projection of the frozen
assigned group, never an agent-provided eligibility mask. structurally_applicable
is computed only from the frozen structural rules in S4.1; current raw v0.1.1
explicit IDs normalize to null. candidate_results are coherent complete predicates
computed by the production evaluator, not agent assertions. The component interface
permits results for ineligible approved candidates for independent testing; they
cannot influence selection. Production evaluation constructs eligibility first and
evaluates only eligible candidates. Each eligible ID must have exactly one result;
unknown or duplicate approved/result IDs, missing eligible results and malformed
shapes are EVAL_INPUT_INVALID. Supplied ineligible results must still be well formed.
Unknown explicit IDs produce UNKNOWN_VARIANT_IDENTIFIER or UNKNOWN_FAMILY_IDENTIFIER;
conflicting valid identifiers produce CONFLICTING_VARIANT_IDENTIFIERS. Selection
validation precedes use of candidate outcomes. Empty eligibility is an ordinary
EVAL_OK deterministic failure, not evaluator-input-invalid. Selector responses
contain selection or null and literal reason codes; no diagnostic metric is
computed by combining its candidate records. The evaluator must use this same
selection rule when populating full occurrence/component reports.

Public component inputs must be validated fail-closed. For aggregate records,
applicable completed/terminal slots require counts; nonapplicable or infrastructure
rows require null counts. Terminal completion-dependent numerator is zero.
Component arithmetic reports only arithmetic, not final correctness or provenance.
Input builders in the new tests produce synthetic records only, with literal
expected values in test cases. No implementation constants are imported.

Static authoring checks are limited to Python compilation without test/evaluator
import, JSON parse, schema self-validation/reference resolution, fixture structural
checks and hashing. Tests are not collected or run. No DEV agent output, judge,
TEST data, implementation repair or orchestration work is authorized.

The complete D01–D42 matrix is reconstructed directly from authenticated prereg
rows. D31–D33 remain PENDING_JUDGE. D14/D15/D16/D19 now include CD-02's complete
selection and canonical partial diagnostics. All 39 deterministic rows have
explicit coverage; zero CONTRACT_DECISION_REQUIRED rows remain. The freeze
contains contracts and pre-authored tests only. Implementation correctness is
unverified until a separate implementation-repair session runs these tests.
