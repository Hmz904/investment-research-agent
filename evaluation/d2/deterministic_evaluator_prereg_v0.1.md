# Deterministic evaluator v0.1 preregistration

Historical first-gate status: **STOPPED AT AMBIGUITY GATE — D2 NOT READY — NO
EVALUATOR IMPLEMENTATION EXISTED**

Current status: **B1–B7 resolved prospectively by the frozen D2 supplement;
second ambiguity gate passed before implementation**

This document was created before evaluator code. It records the deterministic
semantics that can be recovered from the frozen local contracts and the exact
contract gaps that prevent an implementation without inventing rules.

## Contract precedence and scope

1. `evaluation/eval_protocol_v0.2.2.md` is the primary evaluator contract and
   incorporates unchanged v0.2.1/v0.2 semantics.
2. `docs/agent/execution_taxonomy_v0.1.md` is the sole source for execution
   meanings, retry/replacement constants, and infrastructure classification.
3. `evaluation/agent_output_schema_v0.1.1.json` defines submitted-output
   syntax.
4. `evaluation/xbrl_gold_mapping_spec_v0.1.2.md` inherits the mapping rules in
   `evaluation/xbrl_gold_mapping_spec_v0.1.md`; the latter's companion schema
   and review rubric define the documented mapping representation.
5. `benchmark/dev/v0.1/README.md` and `benchmark/frozen/protocol.md` document
   the legacy chunk-gold semantics. Concrete DEV CSV files are examples/data,
   not parser specifications.
6. `docs/tools/calculator_tool_v0.1.md` defines the only frozen arithmetic
   grammar and Decimal execution policy available locally.

No overall agent score or composite is defined. The planned result therefore
contains a deterministic metric panel with integer numerators and denominators,
not a newly invented aggregate score.

## Planned explicit input model

Subject to resolution of the blocking items below, one evaluation request
would explicitly carry:

- a versioned normalized question/gold bundle plus the original schema-bound
  source bytes;
- raw agent-output JSON bytes and the declared output-schema identity;
- a schema-bound run/execution record with scheduled-slot and replacement
  identity;
- the frozen corpus chunk-identity index;
- the legacy approved chunk-provenance bundle;
- an optional approved structured-XBRL map and authoritative XBRL fact index;
- protocol, taxonomy, mapping-specification, calculator, and schema version
  identities and fingerprints.

No split-global state would be read. Split selection would select data only;
it would not select scoring code or parser behavior.

## Normative semantics matrix

`PENDING_JUDGE` below is a literal non-score state. A pending field is excluded
from deterministic numerators and denominators and cannot be approximated.

| ID | Deterministic requirement | Normative source | Required input fields | Deterministic rule | Planned output field | Score effect | Failure behavior | Planned synthetic coverage |
|---|---|---|---|---|---|---|---|---|
| D01 | Version and fingerprint binding | eval v0.2.1 §§2,17; run/output/mapping schemas | protocol/schema versions and hashes; corpus/benchmark/map fingerprints | Require exact declared frozen identities before scoring | `contract_identity` | none directly | evaluator/input failure; never agent zero | wrong protocol, schema, corpus, and map identities |
| D02 | Agent-output syntax | agent output schema v0.1.1; eval v0.2.1 §2 | raw JSON bytes | Validate Draft 2020-12 schema without repair; reject unknown keys and non-finite numbers | `schema_valid` | malformed terminal output is zero only when the run status normatively is `FAIL_FINAL_SCHEMA_INVALID` | otherwise evaluator/input mismatch if record and payload disagree | valid legacy/new provenance; malformed payload; dual provenance rejection |
| D03 | Cross-reference integrity | eval v0.2.1 §2 | claim IDs, answer claim IDs, calculation IDs, calculation references | IDs unique, all references resolve, calculation graph acyclic | `reference_integrity` | required for valid completion | fail closed; no inferred IDs | duplicates, dangling IDs, cycle |
| D04 | Exact decimal handling | XBRL mapping spec v0.1 §1; eval v0.2.2 §§1–2; calculator §Decimal policy | original JSON numeric lexemes; gold decimal strings; factors/quantum/tolerance strings | Parse directly to `Decimal`; never via binary float; forbid exponent notation where the mapping lexical contract applies; canonicalize signed zero to `0` | per-comparison canonical decimal audit | controls all numeric results | malformed numeric evaluator input fails closed | long decimals, signed zero, exponent/non-finite rejection |
| D05 | Exact unit-label identity | eval v0.2.2 §1; mapping spec v0.1 §2.2 | submitted and gold unit strings | Codepoint-for-codepoint identity passes as `exact_label_match`, including an otherwise unregistered label; no conversion or inferred dimension | `unit_result.status` | permits numeric comparison | no crash | identical registered and identical unregistered labels |
| D06 | Registered unit equivalence | eval v0.2.2 §1; mapping spec v0.1 §2 | units, values | Use only the closed monetary, share-count, per-share, ratio/percent, and percentage-point registry and exact positive factors | `unit_result` with rule ID and canonical coordinate | permits numeric comparison | different dimensions reject | USD scales, share scales, EPS aliases, pure/percent |
| D07 | Unregistered different labels | eval v0.2.2 §1 | two distinct unregistered labels | Return `unregistered_unit`; do not infer an alias | `unit_result.status` | unit/value match fails | non-crashing deterministic failure | distinct synthetic unknown labels |
| D08 | Percentage points | eval v0.2.2 §1 | units | `percentage_point` is a separate dimension from `percent`/`pure` | `unit_result` | incompatible units fail | ordinary answer failure | percent versus percentage-point rejection |
| D09 | Exact precision | eval v0.2.2 §2; mapping spec v0.1 §3 | canonical values; registered precision rule | Exact equality for `precision_exact_v0.1` | `precision_result` | answer/input value component | ordinary mismatch | exact pass/fail |
| D10 | Quantum precision | same | frozen positive power-of-ten quantum, source, interval; canonical values | Apply `ROUND_HALF_EVEN` exactly and honor tie-dependent interval endpoints | `precision_result` with quantum, interval, rule/source | answer/input value component | absent/unregistered rule is evaluator/gold failure, not invented tolerance | positive/negative boundary pass/fail and ties |
| D11 | Absolute tolerance | same | frozen nonnegative tolerance, source, interval | Inclusive `abs(candidate-gold) <= tolerance` in the comparison coordinate | `precision_result` | answer/input value component | absent rule fails closed | both inclusive endpoints and just-outside cases |
| D12 | Sign preservation | eval v0.2.2 §3; mapping spec v0.1 §4 | signed Decimal values; registered answer variants | Never use absolute value; normalization never flips sign | `sign_result` | opposite sign fails the matched variant | ordinary answer failure | sign reversal rejection |
| D13 | Approved sign/basis variant | eval v0.2.2 §3; mapping spec v0.1 §4.1 | registered agent-answer variant value, basis and sign convention | Agent answer may match only a pre-registered variant; mapping-path sign exceptions do not create agent variants | `matched_variant_id`, `sign_result`, `basis_result` | variant may pass only as registered | unregistered basis/sign fails | explicitly registered opposite-sign family accepted; invented basis rejected |
| D14 | Answer groups and variants | eval v0.2.1 §5 | answer groups, approved variants, submitted numeric claims | Groups are AND; variants in a group are OR; concept, period, unit, basis, sign and precision all match | per-group result and `value_correctness` numerator/denominator | matched groups / required groups | malformed gold is evaluator failure | multi-group all-pass and partial cases |
| D15 | Variant-family consistency | eval v0.2.1 §5; eval v0.2.2 §3 | `question_consistency_group`, `variant_family`, selected variants | Every matched group in one consistency group uses one family | `variant_consistency` and selected families | mixed family invalidates affected numeric answer | deterministic answer failure | coherent V1, coherent V2, mixed V1/V2 |
| D16 | Required derived inputs | eval v0.2.1 §§5,11 | required input target IDs; submitted calculation inputs | Score every required input before final result; AND requirement; recurse acyclically | per-input results and `required_input_correctness` | correct required inputs / all required inputs | missing/invalid input fails that component | one wrong input despite correct final number |
| D17 | Formula identity/equivalence | eval v0.2.1 §11; calculator expression grammar | frozen formula; submitted expression; target/input binding | Accept exact frozen operation identity or only a frozen deterministic normalization/fixed-vector equivalence | `formula_correctness` | separate component; required for strict grounding | unspecified equivalence cannot be guessed | exact formula, wrong operator, algebraic alternative |
| D18 | Arithmetic recomputation | eval v0.2.1 §11; calculator contract | expression, named exact inputs, submitted result | Parse the frozen grammar, require every supplied input used, use fresh Decimal context precision 50 and `ROUND_HALF_EVEN`, recompute submitted unrounded result | `arithmetic_correctness` | separate component; required for strict grounding | parse/domain errors are deterministic calculation failures for schema-valid completed output | precedence, division, unused/missing input, wrong result |
| D19 | Final derived value/unit/precision | eval v0.2.1 §§5,11 | calculation result and approved answer variant | Independently apply value, unit, basis/sign, final precision checks | `final_value_correctness`, `final_unit_result`, `final_precision_result` | final-value credit may survive other lineage failures; strict grounding may not | ordinary component failure | correct final with wrong input/formula; correct lineage with wrong final |
| D20 | Structured derived lineage completeness | eval v0.2.1 §§7.3,11 | all required inputs and each input provenance | Every required cited fact has sufficient submitted provenance records and resolves through an allowed frozen route | `derived_provenance_completeness` | required-input provenance and strict grounding | missing required provenance fails deterministically | missing one required input provenance |
| D21 | Chunk provenance identity | eval v0.2.1 §§7.1,10; output schema | chunk ID, accession, locator; authoritative chunk index | Exact existing ID, accession, locator, and allowed-corpus identity | per-record validity and failure code | citation/provenance validity numerator/denominator | classify nonexistent ID, wrong accession, metadata inconsistency, outside contract | valid, forged, wrong accession/locator |
| D22 | Cross-question approved chunk path | eval v0.2.1 §7.4; DEV README provenance semantics | q_id, target, normalized candidate references/bundles, submitted chunk records | Candidate references within a part are OR; bundle members and multi-part paths are AND; arbitrary same-accession chunks do not substitute | `chunk_provenance_correctness` | benchmark provenance correctness | wrong-question chunk identity may remain globally valid but gets no approved-path credit | valid chunk from wrong question |
| D23 | Legacy derived chunk path | DEV README; eval v0.2.1 §7.4 | `via_input_fact_id`, normalized candidate/bundle records, required inputs | Derived target has no direct shortcut; recursively require the union/AND of approved input paths | `provenance_path_type=derived_inputs` and per-input path result | required for grounded derived credit | fail closed on missing lineage | full lineage and missing member |
| D24 | XBRL fact identity | eval v0.2.1 §7.1; output schema | fact locator, accession, concept, context, raw unit, exact temporal branch, optional chunk linkage; authoritative fact index | All fields equal the authoritative numeric, non-nil fact; optional linkage, if present, must equal authoritative linkage | `xbrl_provenance_validity` and failure code | provenance validity | forged locator/identity/linkage rejects; absence of optional chunk does not | instant/duration, missing optional link, forged fields, nonnumeric fact |
| D25 | Approved XBRL path | eval v0.2.2 §§3–4; mapping spec v0.1 §§5–7; v0.1.2 temporal extension | submitted exact fact identity; approved paths for target | Credit only exact membership in a frozen human-approved path; never search, infer temporal meaning, or promote an unmappable target | `xbrl_approved_path_validity` | benchmark provenance correctness | valid but unapproved fact gets identity credit only | approved fact, forged fact, valid unapproved target fact |
| D26 | Nonmapped XBRL states | eval v0.2.2 §4; mapping spec/rubric | final mapping status/resolution mode | `unmappable` and `no_xbrl_counterpart_in_frozen_corpus` retain legacy chunk authority and are not automatic agent failures | path diagnostics | no invented XBRL credit or penalty for unavailable route | malformed state is evaluator/map failure | legacy-only pass with no approved XBRL path |
| D27 | Provenance representation validity | output schema v0.1.1; eval v0.2.1 §7.1 | claim/input `citations` or `provenance` | Normalize legacy citations to chunk provenance without repair; the two representations are mutually exclusive | `structured_provenance_validity` | schema/provenance panel | schema-invalid dual source fails without credit | legacy, new union, dual representation |
| D28 | Provenance completeness | eval v0.2.1 §7.3 | material claims, provenance, derived obligations | Direct numeric and derived-input structural obligations are deterministic; semantic materiality/support obligations remain pending | deterministic completeness subfields plus judge field | only applicable deterministic denominators scored | do not infer support/materiality | direct numeric present/absent; derived full/partial |
| D29 | Invalid/hallucinated identity counts | eval v0.2.1 §10 | submitted provenance findings | Count stable deterministic failure classes; hallucinated subset is nonexistent IDs or falsely paired accessions | counts and rates with integer denominators | separate panel only | stable reason ordering | multiple simultaneous failures |
| D30 | Source-contract membership | eval v0.2.1 §9 | authoritative document/fact membership and submitted provenance | Mechanical outside-corpus/source records are deterministic; prose reliance on an unstructured excluded source is judge-dependent | deterministic `source_scope_identity_findings`; semantic field pending | separate count/rate | no keyword heuristic | allowed/outside identity |
| D31 | Strict grounded numeric gate | eval v0.2.1 §8 | numeric, calculation, identity, approved-path, and support results | Require every deterministic numeric/calculation/path component; semantic support remains pending until a judge exists | deterministic prerequisites plus `numeric_strict_grounded_correctness=PENDING_JUDGE` when support is unresolved | never award final strict credit while a required judge component is pending | no heuristic completion | correct number with bad path; all deterministic prerequisites |
| D32 | Final-answer claim references | eval v0.2.1 §§2–3,14 | answer claim IDs and claims | Mechanical reference resolution is deterministic; whether prose jointly expresses/contradicts claims is judge-dependent | `answer_claim_reference_validity`; `answer_claim_consistency=PENDING_JUDGE` | reference failure invalidates output integrity; semantic result excluded | no text heuristic | resolved/dangling references; pending semantic consistency |
| D33 | Judge-dependent evidence metrics | eval v0.2.1 §§6–7,12–15 | semantic evidence items, claims, valid cited text | No judge is authorized; semantic item match, citation support, uncatalogued materiality, causal overreach, nuanced update/evidence coverage, and semantic answer consistency are literal pending states | named `PENDING_JUDGE` fields | excluded from deterministic aggregates | never 0/1, omitted, regexed, or embedded | assert every judge field remains pending |
| D34 | Recoverable events | eval v0.2.2 §6; taxonomy §1 | canonical event IDs | Report frequency; no automatic zero when a run completes | ordered event counts | none automatically | unknown event fails loudly; reserved oversized event inactive | active events; reserved event rejection |
| D35 | Completed run | eval v0.2.2 §6; taxonomy §3 | canonical `RUN_COMPLETED`; schema-valid output | Score normally even if wrong or poorly grounded | `execution_status`, normal metric panel | ordinary scoring | inconsistency with invalid/missing final payload is evaluator/input failure | completed wrong answer |
| D36 | Terminal agent failure | eval v0.2.2 §§6,8; taxonomy §2; preflight §14 | one of five frozen `FAIL_*`; scheduled slot | Retain slot; never replace; zero for metrics requiring valid completion | failure code; zeroed applicable panel; denominator inclusion | zero numerator and included denominator for applicable correctness/coverage metrics | no fabricated output-level diagnostics | each terminal code |
| D37 | Infrastructure exhaustion/replacement | eval v0.2.2 §§6–8; taxonomy §§4–6; preflight §14 | infra attempt/replacement linkage and slot identity | Same logical slot; permitted successful replacement fills it; after replacement exhaustion disclose missing infrastructure | infra slot result and evaluation completeness | unresolved slot excluded from scored denominator; scheduled count retained | never agent zero | replacement success and exhausted replacement |
| D38 | Evaluation-level incompleteness | taxonomy §4; eval v0.2.2 §§6–8 | required replicate set and infrastructure slot results | `EVAL_INCOMPLETE` is only the frozen post-infrastructure-exhaustion evaluation state | `evaluation_status` | no imputed quality score | do not use as a run status | incomplete replicate set |
| D39 | Unknown future status | taxonomy closed enums; task boundary | status/event string | Accept only frozen v0.1 IDs; no `FAIL_CONTEXT_WINDOW_EXCEEDED`; do not activate `EVT_TOOL_RESULT_TOO_LARGE` | evaluator error code | no agent score | loud evaluator/input failure | unknown future status |
| D40 | Denominators and no composite | eval v0.2.1 §4; eval v0.2.2 §8; preflight §14 | applicable items and scheduled slots | Exclude non-applicable questions; include terminal failures where completion required; exclude unresolved infra; preserve numerators/denominators; never average unrelated dimensions | metric panel with counts | exactly per metric | zero-denominator metric is not applicable, not zero | N/A, terminal, infra combinations |
| D41 | Canonical result bytes | eval v0.2.1 §§3,17; calculator serialization | completed result object | UTF-8 JSON, lexicographic object keys, compact separators, schema-declared array order, one newline, no timestamps/random IDs/non-finite values; stable reason ordering | canonical bytes and SHA-256 | none | serialization failure is evaluator failure | two-run byte/hash identity |
| D42 | DEV/TEST algorithm identity | eval v0.2.2 §5 and task substitution contract | explicit bundle/map inputs and versions | Same parser and scoring algorithms; split is data metadata only | contract identities | none | unsupported representation is evaluation-system failure | equivalent DEV/TEST-shaped synthetic bundles through same entry point |

## Judge-dependent fields

The following exact logical fields are planned as `PENDING_JUDGE` until a
separately frozen judge protocol exists:

- `semantic_item_match`
- `citation_support`
- `material_claim_requires_citation`
- `causal_overreach`
- `answer_claim_consistency`
- `evidence_item_coverage`
- `evidence_all_parts_rate`
- `evidence_weighted_partial_coverage`
- `evidence_weighted_strict_coverage`
- `evidence_core_coverage`
- `evidence_strict_grounded_correctness`
- `unsupported_material_claim_rate`
- `numeric_strict_grounded_correctness` whenever semantic support is a
  required unresolved component

Mechanical provenance identity, approved-path membership, numeric matching,
calculation, and schema/reference checks are not judge fields.

## Ambiguity classification

### Resolved by frozen contract

| Topic | Classification | Frozen resolution |
|---|---|---|
| Registered units and scaling | RESOLVED BY FROZEN CONTRACT | Closed registry and exact Decimal factors in eval v0.2.2 §1. |
| Same unknown label | RESOLVED BY FROZEN CONTRACT | Exact-label fallback succeeds without dimension inference. |
| Different unknown labels | RESOLVED BY FROZEN CONTRACT | `unregistered_unit`, no credit, no crash. |
| Percent versus percentage point | RESOLVED BY FROZEN CONTRACT | Different dimensions. |
| Numeric rounding modes | RESOLVED BY FROZEN CONTRACT when a registered rule and parameters are present | Exact, power-of-ten quantum with `ROUND_HALF_EVEN`, or inclusive absolute tolerance only. |
| Sign | RESOLVED BY FROZEN CONTRACT | Preserve sign; only registered answer variants pass agent scoring. |
| Variant families | RESOLVED BY FROZEN CONTRACT once claim-to-target assignment is known | One family per consistency group; mixed families fail. |
| Chunk identity and legacy Boolean paths | RESOLVED BY FROZEN CONTRACT once the source bundle parses | Exact identity; OR candidates, AND bundle/parts/derived inputs. |
| XBRL fact identity | RESOLVED BY FROZEN CONTRACT once map syntax parses | Exact locator and all authoritative identity fields; optional chunk linkage is exact if supplied. |
| Judge boundary | RESOLVED BY FROZEN CONTRACT | Listed semantic metrics remain `PENDING_JUDGE`; no heuristic proxy. |
| Terminal agent and infrastructure scoring | RESOLVED BY FROZEN CONTRACT once a canonical status can be obtained | Terminal agent failures are retained zeros for applicable metrics; unresolved infrastructure is disclosed and excluded from scored denominator. |
| Unknown future statuses | RESOLVED BY FROZEN CONTRACT | Fail loudly; no deferred v0.2.3 identifiers. |
| Canonical serialization | RESOLVED BY FROZEN CONTRACT | Sorted compact UTF-8 JSON plus one newline; no unstable metadata. |

### Blocking ambiguities

#### B1 — no schema-bound representation of the canonical execution taxonomy

`evaluation/agent_run_schema_v0.1.json` requires
`canonical_record.status = success|failure`, uses lowercase legacy failure
codes such as `provider_failure`, binds `eval_protocol_v0.2.1`, and cannot
represent canonical `RUN_COMPLETED`, the five `FAIL_*` statuses,
`INFRA_RUN_RETRY_EXHAUSTED`, replacement linkage, or `EVAL_INCOMPLETE`.
The explicitly referenced execution-policy preflight confirms that the current
run schema needs a future amendment and that sidecars carry some states, but no
frozen sidecar schema or legacy-to-taxonomy adapter is supplied.

**Exact human decision required:** freeze either (a) a canonical run-record /
slot-record schema that directly represents taxonomy v0.1, or (b) a complete,
versioned adapter mapping every allowed legacy run-record and sidecar state to
exact taxonomy IDs, including the treatment of legacy `provider_failure` and
all impossible/inconsistent combinations.

#### B2 — the frozen DEV map does not conform to the referenced mapping schema

The frozen `evaluation/dev/xbrl/dev_xbrl_map_v0.1.json` declares
`schema_version=dev_xbrl_map_v0.1` and fields such as `target_id`,
`final_mapping_status`, `legacy_source_paths`, and stage candidate arrays. The
referenced `evaluation/xbrl_mapping_schema_v0.1.json` instead requires
`schema_version=xbrl_gold_mapping_schema_v0.1` and a materially different
`mapping_target` layout (`gold_target_id`, `mapping_status`,
`approved_xbrl_paths`, and others). No frozen JSON Schema for
`dev_xbrl_map_v0.1` is present.

**Exact human decision required:** freeze a schema and cross-record validation
contract for the already-frozen `dev_xbrl_map_v0.1` representation and require
future TEST maps to use it, or supply a separately frozen, semantics-preserving
adapter into `xbrl_gold_mapping_schema_v0.1`. The evaluator cannot infer a TEST
map parser from the DEV concrete layout.

#### B3 — no complete frozen gold-bundle syntax covers DEV and historical TEST

The DEV README and frozen benchmark protocol define many CSV semantics, but no
machine schema enumerates every required/optional field, allowed concrete
legacy representation, null encoding, list encoding for every field, duplicate
policy, referential constraints, or version dispatch for both the current DEV
files and the earlier TEST annotation format. The task expressly says the two
concrete formats may differ and forbids a DEV-layout-only parser.

**Exact human decision required:** freeze a versioned gold-bundle schema and
adapter contract that enumerates all allowed DEV and historical TEST
representations and maps them into one normalized question/gold/provenance
model. It must state which schema/version discriminator selects each allowed
representation and which deviations are evaluation-system failures.

#### B4 — no frozen evaluator/input-failure status for malformed gold or maps

The taxonomy defines `EVAL_INCOMPLETE` only for an unfilled scheduled
replicate after infrastructure retry/replacement exhaustion. It does not define
a status for malformed gold, an unsupported gold representation, a malformed
approved map, protocol mismatch, or internal evaluator failure. Reusing
`EVAL_INCOMPLETE` for these cases would change its frozen meaning. The protocol
states that malformed judge output is an evaluation error, but supplies no
stable deterministic evaluator-error ID or denominator/report schema.

**Exact human decision required:** freeze the evaluator/input failure status
namespace and its artifact/denominator behavior. Confirm explicitly that these
failures are not agent zeros and whether the overall replicate-set status is a
new status distinct from infrastructure-only `EVAL_INCOMPLETE`.

#### B5 — submitted numeric claims have no frozen binding to answer groups or targets

`agent_output_schema_v0.1.1` gives numeric claims value/unit/period/basis but no
gold `fact_id`, answer-group ID, or variant ID. The protocol does not define
whether matching uses first-match, maximum bipartite matching, permits one
claim to satisfy multiple groups, permits multiple claims for one group, or
how to break ties among otherwise matching variants. These choices affect
value correctness and family consistency.

**Exact human decision required:** freeze a deterministic claim-to-answer-group
assignment rule, including multiplicity and tie-breaking, or version the output
schema to carry an explicit target/group binding before any agent output is
generated.

#### B6 — derived calculation inputs have no frozen binding to required gold facts

Gold formulas and required inputs use gold fact IDs such as `NF001`, while the
agent schema exposes calculation-local `input_id`/`name` and no gold fact ID.
The protocol requires input-by-input identity validation but does not define
the assignment algorithm when values/periods/bases overlap. It also permits
algebraically different formulas only under “deterministic normalization or
fixed test vectors,” neither of which is frozen for evaluator use.

**Exact human decision required:** freeze (a) the binding from each submitted
calculation input to one required gold fact, including uniqueness and
tie-breaking, and (b) the accepted formula-equivalence procedure. An explicit
gold-target identifier in a versioned schema is one possible resolution; an
exact versioned adapter rule is another.

#### B7 — DEV precision annotations are not registered precision-rule records

The primary protocol permits only a registered exact rule, a frozen positive
power-of-ten quantum, or a frozen absolute tolerance with source and interval.
The DEV CSV supplies `display_precision` values (`0`, `1`, `2`) and blank
`tolerance`; the final DEV XBRL map does not carry complete registered
precision records. The older benchmark protocol says blank tolerance uses
lexical/display precision, but does not normatively define the conversion from
the integer `display_precision` field to a quantum, interval endpoints, and
rule-source record. Treating `2` as quantum `0.01` is plausible but would be an
invented adapter rule.

**Exact human decision required:** freeze the adapter that converts every
legacy precision representation into one complete v0.2.2 registered precision
record, including exact/quantum/tolerance selection, comparison coordinate,
source ID, and tie-inclusive interval endpoints.

## Ambiguity gate result

At least one blocking ambiguity exists; seven are recorded above. Therefore:

- no evaluator implementation may be written;
- no evaluator output schema may be frozen around invented behavior;
- no synthetic scoring fixtures may encode a preferred unstated decision;
- no DEV integration validation may run; and
- no D2 freeze-candidate manifest may be created.

## TEST DATA SUBSTITUTION CONTRACT

At the authorized TEST checkpoint:

1. evaluator implementation is already frozen;
2. evaluator tests are already frozen;
3. parser/schema is already frozen;
4. only TEST data bundles/maps replace DEV data bundles/maps;
5. no scoring logic changes;
6. no parser patch is allowed merely because TEST concrete formatting differs
   from DEV if both should conform to the same frozen schema;
7. TEST parse failure is an evaluation-system failure and is reported loudly;
8. it is not converted into an agent zero; and
9. any necessary evaluator code repair invalidates that checkpoint and
   requires a new evaluator version and documented procedure.

This contract cannot be implemented until B2–B4 are resolved by frozen
material.

## Planned test matrix after ambiguity resolution

The minimum matrix remains the 28 requested cases: correct direct chunk,
correct approved XBRL, correct derived lineage, wrong number, precision
boundary pass/fail, registered-unit incompatibility, same/different unknown
labels, sign reversal, registered sign variant, mixed family, forged and
cross-question chunks, forged/unapproved/approved XBRL identities, wrong
derived input, wrong formula/result, missing derived provenance, incomplete
structured provenance, malformed output, terminal failures, infrastructure
denominator treatment, evaluator/gold parse failure, unknown future status,
pending judge fields, and repeated byte/hash determinism. Additional tests in
the matrix above cover cross-reference cycles, taxonomy/run-record
inconsistency, map/gold schema version dispatch, and precision ties.

## Human contract resolutions after ambiguity gate

Resolution date: 2026-09-25

Resolution source for every row:
`evaluation/d2/deterministic_evaluator_contract_supplement_v0.1.md`.

The original D2 attempt stopped with `D2 NOT READY` before evaluator code
existed. These decisions were then frozen before implementation, before any
DEV agent output was generated or observed, and without consulting TEST.

| Original blocker | Frozen resolution | Status | Agent output observed? | TEST consulted? |
|---|---|---|---|---|
| B1: no schema-bound canonical execution representation | `EvaluationSlotRecord v0.1` plus `evaluation_slot_record_adapter_v0.1`; closed taxonomy status set and one-slot replacement semantics | RESOLVED BEFORE IMPLEMENTATION | no | no |
| B2: concrete DEV map lacked a matching evaluator schema | `DEVXBRLMapAdapter v0.1` plus `NormalizedXBRLMap v0.1`; closed direct/derived/no-path states | RESOLVED BEFORE IMPLEMENTATION | no | no |
| B3: no complete common gold-bundle syntax | `GoldBundle v0.1`, explicit source-format dispatch, normalized-only scoring, loud unsupported-format failure | RESOLVED BEFORE IMPLEMENTATION | no | no |
| B4: evaluator/input failure namespace absent | `EvaluatorStatus v0.1`; non-OK results have null score, no denominator inclusion, invalid checkpoint | RESOLVED BEFORE IMPLEMENTATION | no | no |
| B5: numeric claim/group assignment unspecified | explicit ID when schema-permitted; otherwise frozen one-to-one positional binding with no best-fit search | RESOLVED BEFORE IMPLEMENTATION | no | no |
| B6: derived input/formula binding unspecified | explicit role or positional lineage; syntactic allowlisted formula variants only; no algebraic search | RESOLVED BEFORE IMPLEMENTATION | no | no |
| B7: legacy precision representation unspecified | `PrecisionRecord v0.1`; tolerance first, then decimal-place quantum with half-even, else exact | RESOLVED BEFORE IMPLEMENTATION | no | no |

The supplement does not revise `eval_protocol_v0.2.2`, the execution taxonomy,
the agent output schema, or the frozen XBRL mapping package. The original
blocking analysis above remains as the audit history of the mandatory stop.

## Second ambiguity gate

Gate date: 2026-09-25

This reclassification was performed after the supplement and its machine
schemas were written and before evaluator implementation. `PENDING_JUDGE` is
used only where the frozen contract requires semantic judgment.

| Matrix row | Classification | Resolution basis |
|---|---|---|
| D01 | RESOLVED | Explicit contract/hash fields plus `EvaluatorStatus v0.1` |
| D02 | RESOLVED | Frozen output schema and slot/output consistency rules |
| D03 | RESOLVED | Closed reference and cycle checks |
| D04 | RESOLVED | Exact lexical Decimal parsing and canonicalization |
| D05 | RESOLVED | Exact-label-first unit rule |
| D06 | RESOLVED | Closed unit registry |
| D07 | RESOLVED | Different unknown labels reject deterministically |
| D08 | RESOLVED | Percentage-point dimension remains distinct |
| D09 | RESOLVED | `PrecisionRecord.EXACT` |
| D10 | RESOLVED | `PrecisionRecord.QUANTUM` and half-even rule |
| D11 | RESOLVED | `PrecisionRecord.ABS_TOLERANCE` |
| D12 | RESOLVED | Signed normalized comparison |
| D13 | RESOLVED | Registered variants only |
| D14 | RESOLVED | GoldBundle groups plus R5 assignment |
| D15 | RESOLVED | R8 coherent-family selection |
| D16 | RESOLVED | R6 explicit/positional required-input lineage |
| D17 | RESOLVED | Allowlisted syntactic formula variants only |
| D18 | RESOLVED | Frozen calculator grammar and Decimal policy |
| D19 | RESOLVED | GoldBundle output unit/precision |
| D20 | RESOLVED | Required-input AND lineage |
| D21 | RESOLVED | Exact frozen chunk identity |
| D22 | RESOLVED | Target-specific normalized chunk paths |
| D23 | RESOLVED | Recursive required-input chunk lineage |
| D24 | RESOLVED | Exact structured fact identity |
| D25 | RESOLVED | Normalized frozen approved XBRL paths only |
| D26 | RESOLVED | Closed normalized map states and legacy fallback |
| D27 | RESOLVED | Frozen provenance union and legacy adapter |
| D28 | RESOLVED | Deterministic structural completeness isolated from semantic support |
| D29 | RESOLVED | Closed stable identity-failure reasons |
| D30 | RESOLVED | Mechanical source identity only; semantic reliance delegated to D33 |
| D31 | PENDING_JUDGE | Final strict grounded result requires semantic support judgment |
| D32 | PENDING_JUDGE | Mechanical references resolve; prose/claim consistency requires judge |
| D33 | PENDING_JUDGE | Frozen judge boundary expressly reserves these metrics |
| D34 | RESOLVED | Closed event set; reserved oversized event inactive |
| D35 | RESOLVED | `EvaluationSlotRecord.RUN_COMPLETED` |
| D36 | RESOLVED | Closed terminal statuses and denominator-zero rule |
| D37 | RESOLVED | One-slot retry/replacement semantics |
| D38 | RESOLVED | Infrastructure-only `EVAL_INCOMPLETE` preserved |
| D39 | RESOLVED | Unknown status is contract mismatch |
| D40 | RESOLVED | Explicit slot and applicability denominator rules |
| D41 | RESOLVED | Canonical JSON byte contract |
| D42 | RESOLVED | Normalized GoldBundle and map inputs; no split branch |

Second-gate totals:

- `RESOLVED`: 39
- `PENDING_JUDGE`: 3
- `BLOCKING`: 0

Continuation condition is satisfied. D2 implementation may proceed without
changing these frozen decisions.
