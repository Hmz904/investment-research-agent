# D2 v0.2.1 implementation candidate

Verdict: **D2 V0.2.1 IMPLEMENTATION CANDIDATE READY**.

Base / normative patch: `0b6d22fc563dec40b0ae0ad643b30d0d1792d207`.
D2_V021_IMPLEMENTATION_COMMIT: `PENDING_LOCAL_COMMIT`.

## Implementation

QUANTUM uses Decimal and ROUND_HALF_EVEN to compare Q_q(candidate) directly
with Q_q(reference). Both operands use the same positive power-of-ten quantum
after registered unit conversion. EXACT, ABS_TOLERANCE, signed comparison,
basis, period, variant selection, assignment and provenance behavior are preserved.

Historical precision ingress still undergoes strict v0.2 schema, primitive and
coordinate validation. A separate v0.2.1 projection regenerates QUANTUM
intervals around the rounded reference, with HALF_EVEN endpoint parity. The
historical input remains unchanged. EXACT and tolerance intervals retain their
existing validation. Scoring never uses the historical S2 interval.

NF004: reference 56.0468756436 percent, q=0.1, quantized reference 56.0.
Candidate 56.0 passes; 56.1 fails. Positive/negative HALF_EVEN ties pass the
frozen successor expectations. D19: EXACT 37 and QUANTUM 10(reference=37)
admit 37, return EVAL_OK and complete=true. Candidate 38 fails the exact
constraint with EVAL_OK, retained denominator and ordinary numeric failure.

### Precision consistency / requested CD-03 accounting

The frozen successor explicitly introduces no new CD-03 or general solver.
Existing wire validation requires each applicable precision reference/unit to
agree with its target/variant. Under S1 the shared raw reference belongs to
EXACT, nonnegative tolerance and QUANTUM acceptance sets, so these constraints
have a common witness. Different modes and off-grid references are valid.
Malformed or conflicting coordinates fail before agent scoring with
EVAL_INPUT_INVALID, null metrics and an excluded slot. No broad solver was added.

The frozen integrity test checks EXACT 37 plus QUANTUM 10(reference=37) as
valid, then adds QUANTUM 10(reference=50) and rejects the canonical witness.
This incompatible-constraint control passed. EXACT 37 plus EXACT 38 is not a
frozen successor evaluator test; no new exploratory case was authored or run.
Repair-1's 37 +/- 0.5 plus EXACT 37 remains valid and rejects candidate 37.4
for complete derived credit.

### Checkpoint reportability

`checkpoint_reportability_v0_2_1` accepts all scheduled evaluator results and
the authorized split's numeric integrity outcome. Any EVAL_INTERNAL_ERROR
sets checkpoint_valid=false, aggregate_reportability=NON-REPORTABLE, and
requires evaluator repair/versioning and checkpoint rerun. A failed integrity
gate also blocks reportability. The existing pre-registered fault-injection
result verifies this policy; its row remains EVAL_INTERNAL_ERROR with null
metrics. No exception is reclassified as arbitrary agent invalidity.
Formal checkpoint callers must apply this gate before publishing aggregates.
No formal agent checkpoint or TEST source adapter was invoked here.

## Test accounting

| Suite | Collected | Active passed | Superseded |
|---|---:|---:|---:|
| Historical contract | 257 | 256 | 1 |
| Successor precision | 11 | 11 | 0 |
| DEV integrity utility tests | 4 | 4 | 0 |
| Repair-1 auditor regressions | 5 | 5 | 0 |
| Existing implementation guards | 22 | 22 | 0 |
| Total | 299 | 298 | 1 |

Exactly this unchanged historical node is superseded:

```text
tests/evaluation/test_deterministic_evaluator_contract_v0_2.py::test_D10_quantum_exact_power_and_half_even[1.24-1.23-0.1-1.23-1.23-False-False]
```

Its candidate=1.24, reference=1.23, q=0.1 historical false assertion was actually
executed and failed under S1. Raw pytest reports 298 passed / 1 failed, exit 1.
The explicit active-suite runner requires precisely that sole failure, all 299
executions, all expected collection counts, and no skips/setup errors. It records
all node outcomes in the machine-readable validation artifact. The additive
successor asserts the true result and passes. Nothing is edited, skipped or
xfail-marked in the historical file. Active result: 298/298, zero active failures.

F1, F2, F3, F4 and the positive no-counterpart control all pass. Iterative
1,100-node DAG handling, derived output precision, sign relationship and
search-stage validation are preserved. CD-01 and CD-02 pass: invalid graph
handling retains independent direct credit and the slot; variant selection uses
complete-pass eligibility followed by string lexical order, or canonical lexical
diagnostics when none pass. V1 < V10 < V2 remains unchanged.

## Corrected audit and successor matrix

**150/150 PASS** against versioned expectations, with 148 expectations unchanged
and exactly two replacements: `inconsistent_derived_output_precision` (D19) and
`offgrid_gold`. Original harness sources, input constructors and historical
observations are unchanged. The wrapper selects this checkout, isolated runtime
and a new temporary output directory. D19's regenerated input bytes equal the
frozen SHA-256 `e0fb2e80d3cee77ae99fc383c3e3e394c16bb54769f9063d03384be1c7e758b4`.
All active probe names, order, row bindings and expectations are checked against
the frozen successor list. Request hashes and source bindings are recorded.

Harness accounting detail: the historical collector already excludes
`runtime_probes.py`'s retired `valid_no_xbrl_counterpart_in_frozen_corpus` control.
With S1 that existing control reaches its existing conditional
`no_counterpart_stage1_blocked` child. Both runtime records are explicitly listed
outside the frozen 150 in `retired_runtime_accounting`. The active F4 input is
the separately frozen `map_states.py` control, which is retained and passes.
No probe was invented or added to the active set; no other case is excluded.
The authenticated source files themselves are executed unchanged.

Successor matrix: **39 PASS / 3 PENDING_JUDGE / 0 FAIL / 0 PARTIAL /
0 unresolved**. Each row is linked to passing original probe evidence; successor
precision tests additionally cover D10 and D19. No judge or proxy was used.

## DEV and determinism

Frozen DEV numeric integrity gate: **17/17 PASS**, NF001–NF017, including NF004
and approved signed variants. No DEV gold changed.

Runtime root: `/mnt/d/projects/thesisagent-d2-v2-runtime-data` only.
45 provisioned files authenticated; **7,839 XBRL facts**; fingerprint:
`acaf087ee2c4fb7427377cae5f1968da26c75d4dfa565f67f1e056b2c4cc4eb6`.
All **eight DEV bundles** validate with EVAL_OK using synthetic limitation
outputs. These are integration checks, not real agent results.

Two fresh Python processes each execute ten repetitions of F1, F2, the XBRL
adapter, NF004 and D19: **100 case executions**, plus eight DEV bundle checks
per process (16 total). Canonical outputs are byte-identical within and across
processes. Full process report SHA-256:
`e36b771ae704a17c3c4c5ba730ce9974ac0f0fae214c90d9c17e0f4e6d70d6a1`.

- NF004: `bf151e42cc5bd4cb4ba6960db45dfacac67cdb6ec620da254e312cf006093ac2`.
- D19: `5e02e88a66e65974488e9d6fb926702b73e9d9784b6e7e17865b252c87cf1517`.
- F1: `44aedf01458b1af7508cee607441a9de0b0278ecfad51b96577c2a1ff94ab5dc`.
- F2: `be4acb8d5b855c8566d64ad03bacc4cec7c79530e607ec587727187f91032bf6`.
- XBRL: `c46e549769c7aba1c082e96e72f779e039ea9445954d9bbd88c413ebd3715b40`.

The last three hashes and their combined hash
`ed8cb5ff2ee67e2006f739c2955800c6542ffdab7e46d8d4cec7d929ea153d34`
remain identical to Repair-1. The original harness's ten-repeat determinism
check also passes. Full canonical Repair-1 outputs and per-bundle hashes are
persisted in `d2_v2_1_implementation_validation.json`.

## Reproduction

Use the existing audit environment for dependencies, with this checkout as cwd:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests/evaluation:. /mnt/d/projects/d2-v2-independent-audit-blocked-v0.1/venv/bin/python -m evaluation.d2.verify_v0_2_1 tests --output /tmp/d2_v021_tests.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests/evaluation:. /mnt/d/projects/d2-v2-independent-audit-blocked-v0.1/venv/bin/python -m evaluation.d2.verify_v0_2_1 harness --output /tmp/d2_v021_harness.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests/evaluation:. /mnt/d/projects/d2-v2-independent-audit-blocked-v0.1/venv/bin/python -m evaluation.d2.verify_v0_2_1 determinism --output /tmp/d2_v021_determinism_a.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests/evaluation:. /mnt/d/projects/d2-v2-independent-audit-blocked-v0.1/venv/bin/python -m evaluation.d2.verify_v0_2_1 determinism --output /tmp/d2_v021_determinism_b.json
cmp /tmp/d2_v021_determinism_a.json /tmp/d2_v021_determinism_b.json
```

## Immutable guards and candidate identity

All 27 historical, seven Repair-1 and 14 successor governed artifacts remain
byte-identical, as do the nine authenticated historical normative imports.
Manifest hashes:

- Historical: `f69e14f586a6d2fd94b5500d05db5a984c8180cd609d3e2582316ef481c29e22`.
- Repair-1: `e010615bc9f27a68e5914da5ee3fadfb0cd52b42211b12366586aaa8cba3cd47`.
- Successor patch: `49508f8c7421a93910f5188de629f277f44f37d05a2b178e9226e6d554bf0545`.

All named lineage commits are verified ancestors. Candidate manifest:
`evaluation/d2/D2_V2_1_IMPLEMENTATION_CANDIDATE_SHA256.txt`.
Its header binds D2-A, D2-B, original implementation, Repair-1 regression,
implementation and final candidate, contract patch, all freeze manifests, and
the implementation commit. It covers production modules and validation code,
results and report. Two generations must be byte-identical; every entry is
verified. As in Repair-1, a metadata-only follow-up binds the actual production
commit after it exists, avoiding a self-referential Git hash. Historical candidate
manifests are preserved.

## Boundary and next step

Historical frozen tests modified: no. Contract modified: no. TEST accessed: no.
The frozen synthetic split-label identity test uses no TEST material.
Judge: no. Model: no. Real agent output: no. Agent/orchestrator work: no.
Independent re-audit started: no. Merge/tag/push: no.

Run the final pre-registered targeted independent re-audit against the D2
v0.2.1 implementation candidate. Use the corrected 150-probe expectations,
the active historical suite plus successor replacements, Repair-1 regressions,
17-target DEV self-consistency, eight DEV bundles, 42-row successor matrix,
and determinism checks. Do not add exploratory probes. If all pass, freeze
D2 v0.2.1.
