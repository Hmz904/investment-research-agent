# D2 deterministic evaluator contract supplement v0.2.1

Status: prospective normative/test correction to v0.2; implementation unvalidated.

## P1. Scope, authority and history

This successor corrects a confirmed contract-authoring error in v0.2 §S5 and
its §S1 blocker-D explanation. Historical R7 supports S1: independently
quantize candidate and reference. The mapping specification does not require
its gold operand to be the raw unrounded stored number. v0.2's S2 restriction
and empty-preimage rule were an over-interpretation of that source.

Authority remains v0.2 §S1's source hierarchy, interpreted by the clean human
adjudication. Exact relevant sections are historical supplement v0.1 §R7;
evaluation protocol v0.2.2 §2; mapping specification v0.1 §§3 and 3.1, including
the frozen display-value interval paragraph; and mapping v0.1.2 “Version lineage
and exact delta.” Mapping v0.1 §1 and protocol v0.2.2 §1 retain Decimal and unit
semantics. These sources coherently support S1 under the adjudication.

All other v0.2 rules, CD-01/CD-02, EXACT, ABS_TOLERANCE, sign/basis, unit
normalization, multiplicity, assignment, provenance and judge boundaries remain
in force. No CD-03, general constraint solver, or judge proxy is introduced.

Immutable dependencies:

- D2-A: `6a2e577543f8df58e88ba2acda2b14ca945ae1fc`.
- D2-B: `4946e302027f4aab7b09e493ae82f208d5ad75ee`.
- v0.2 test-author manifest SHA-256:
  `f69e14f586a6d2fd94b5500d05db5a984c8180cd609d3e2582316ef481c29e22`.
- Repair-1 regression manifest SHA-256:
  `e010615bc9f27a68e5914da5ee3fadfb0cd52b42211b12366586aaa8cba3cd47`.

Historical contracts, schemas, 257 tests and audit evidence remain immutable.
Blocked Repair-2 is not a source. This patch contains no production repair.

## P2. Authoritative QUANTUM comparison

For positive power-of-ten q, in a common comparison coordinate:

```text
Q_q(x) = q * round_half_even(x / q)
QUANTUM(candidate, reference) passes iff Q_q(candidate) == Q_q(reference).
```

Both operands are independently quantized with the same q and ROUND_HALF_EVEN.
The raw reference need not lie on the grid. An off-grid raw reference never
implies an empty acceptance set. Prefer direct quantized equality for scoring.
Use Decimal without binary float intermediates or unintended arithmetic rounding.
Keep v0.2's positive integral power-of-ten domain and strict lexical validation.

EXACT remains candidate == reference. ABS_TOLERANCE remains inclusive
abs(candidate-reference) <= t for nonnegative t. R7 precedence remains explicit
tolerance, otherwise nonnegative integer display precision, otherwise EXACT.
Unit normalization and signed comparisons retain their existing frozen rules.

For display_precision p, q=10^(-p). Interpret the frozen raw numeric value
through its display-precision equivalence class Q_q(reference).
NF004: raw reference 56.0468756436, p=1, q=0.1, Q_q(reference)=56.0.
Candidate 56.0 passes, consistent with the permitted DEV metadata note:
“Accept 56.0% at requested display precision.” Candidate 56.1 fails.

If a diagnostic interval is materialized, let k=round_half_even(reference/q).
Its center is kq, its bounds are kq-q/2 and kq+q/2, and both endpoints are
included iff k is even. Negative values use the same parity rule. For q=0.1,
1.15 and 1.25 quantize to 1.2; -1.25 quantizes to -1.2.

## P3. Versioned normalization of historical precision records

The v0.2.1 interpretation explicitly supersedes historical S2-derived QUANTUM
interval metadata. Preserve source bytes, source hashes, primitive fields and
source version identifiers. After strict historical wire-shape validation and
primitive/domain validation, construct a separate successor precision record
from reference_value, quantum and ROUND_HALF_EVEN. Discard the historical
QUANTUM interval from the scoring representation, or regenerate it under P2
for diagnostics. Do not reject a valid off-grid reference because its historical
S2 interval is empty. This is an authorized versioned normalization change;
the historical record itself is never silently repaired or relabeled.

`precision_record_v0.2.1.schema.json` describes the successor normalized record.
Its interval is optional for QUANTUM and, if present, is derived under S1 and
checked for consistency. EXACT and ABS_TOLERANCE retain their required intervals
and validation. No malformed primitive, unknown field, wrong type, invalid q,
or unsupported rounding mode is excused by this normalization.

Historical request/gold schemas remain the frozen ingress shapes. Their v0.2
precision references authenticate historical records; they do not govern the
new internal successor projection. Do not insert a v0.2.1 precision record into
an unchanged v0.2 wire schema. Bind the selected v0.2.1 interpretation externally
in the checkpoint's contract/patch manifest alongside the original input hash.
The successor test/harness run selects this interpretation; the original wire
identities and all 150 probe inputs remain exactly unchanged. Unknown identities
still fail closed. No unrelated wire schema is versioned by this patch.

## P4. Precision consistency and D19

Evaluator-side precision configuration is invalid only for an actual frozen
schema/domain violation or genuinely applicable constraints that are mutually
impossible under their correct frozen semantics. An off-grid raw QUANTUM
reference alone never proves inconsistency. This patch does not prescribe a
new general constraint solver.

D19's target EXACT 37, derived QUANTUM 10, reference 37 admits candidate 37:
Q_10(37)=40 on both sides. The intersection contains 37. Its historical empty
interval is superseded derived metadata under P3; the diagnostic S1 interval
is [35,45], inclusive. The existing complete synthetic D19 request therefore
expects EVAL_OK and complete_numeric_answer=true, not EVAL_INPUT_INVALID.

A candidate such as 38 belongs to that QUANTUM class but violates EXACT 37.
It yields an ordinary numeric failure/incomplete answer under existing rules,
with EVAL_OK, not evaluator-input invalidity. Required-input, formula and
arithmetic checks remain independent.

## P5. Audit/test succession

The v0.2 expectation representation for the original 150-probe harness changes
exactly two expectations: inconsistent_derived_output_precision (D19) and
offgrid_gold. Both now require EVAL_OK and complete_numeric_answer=true.
The other 148 expectations, every probe input, source harness and all historical
observations remain unchanged. The erratum records the source identities.
No probe 151 is added. Historical passed/failed observations are not relabeled.

The original 257 contract cases remain frozen. One parameter case in
test_D10_quantum_exact_power_and_half_even has candidate=1.24, reference=1.23,
q=0.1, an S2 empty interval and historical match=false. Under this successor
its expected comparison is true. The additive suite records that S1 assertion.
Future validation must run and report the historical suite unchanged, identify
this superseded assertion explicitly, and separately report v0.2.1 conformance.
Do not modify, skip or silently xfail the frozen case or claim all historical
expectations agree with S1. This does not add a third audit-harness change.

## P6. Numeric gold integrity and checkpoint reportability

For every numeric target and approved numeric variant, the canonical gold/display
representation must satisfy all applicable target, variant and derived-output
precision constraints under their frozen semantics. This is evaluator/gold
integrity, not agent scoring. It uses no model output. The DEV utility binds the
permitted numeric gold and metadata and covers all 17 NF001–NF017 targets,
including signed approved variants and NF004; no gold is changed to pass.
Any failing target blocks the checkpoint and must be reported.

Before the first authorized TEST agent output is scored, run the same integrity
validation after frozen TEST gold/map are legitimately opened at the authorized
checkpoint. Use its then-authorized source adapter with the same precision
checks; never reuse DEV identities as TEST inputs. If the gate fails,
checkpoint_valid=false and agent scoring MUST NOT proceed until evaluator/gold
semantics are repaired and versioned. TEST is not opened in this session.

For formal reportable DEV/TEST evaluation, if ANY scheduled evaluation unit
produces EVAL_INTERNAL_ERROR, checkpoint_valid=false and aggregate results are
NON-REPORTABLE until the evaluator defect is repaired/versioned and the affected
checkpoint is rerun. Unexpected evaluator/programming errors remain
EVAL_INTERNAL_ERROR at row level; they never become arbitrary agent violations.
This is operational/reportability policy, independent of agent scoring.
