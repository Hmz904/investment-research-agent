# D2 v0.2.1 operational pre-scoring gate patch

Verdict: **D2 V0.2.1 PRE-SCORING GATE PATCH READY**.

Base candidate: `229003a46ea33321d0573ad94e2f4bb128f5a21a`.
Contract patch: `0b6d22fc563dec40b0ae0ad643b30d0d1792d207`.
Semantic implementation: `02c55adfd6b93d8cd55a0f0322442ca87c223fe0`.
PRESCORING_REGRESSION_COMMIT: `651c172f0ef5d952caf8df744c0b1316f592efb3`.
D2_PRESCORING_GATE_COMMIT: `e33e3dddaf23fc6629e40b2a4f967665ce92ac8d`.

## Finding and repair

Enforcement mode: **MANDATORY_PRECHECK**. Previously, the DEV runner called
validate_dev() only after its selected tests, harness or determinism execution.
Rejecting aggregate publication afterward did not prevent scoring from starting.

The runner now enforces this order:

1. Authenticate the evaluator-side frozen contracts, manifests and artifacts.
2. Call the shared validate_gold_integrity_before_scoring(validate_dev) gate.
   The unchanged frozen validator authenticates both DEV numeric sources and
   validates all 17 required targets. The shared wrapper requires complete PASS.
3. Only after success, enter the selected tests/harness/determinism entrypoint.
4. Execute the existing validation and aggregate reportability assertions,
   recheck immutable guards, and write the successful validation report.

Failure in steps 1 or 2 exits with status 1 and writes only an invalid-checkpoint
diagnostic: checkpoint_valid=false, aggregate_reportability=NON-REPORTABLE,
evaluator_repair_and_rerun_required=true. No scoring callback, scoring validation
payload or aggregate scoring output is produced. Repair and version the
evaluator/gold defect, then rerun the precheck before any scoring.

Production changes are limited to a shared precondition module and moving the
existing DEV integrity call ahead of the runner's dispatch. The frozen normative
integrity code is unchanged. The wrapper accepts an authorized split's complete
deterministic validator; it adds no numeric semantics or DEV-specific rules.

## Direct ordering evidence

The additive regression was authored, run against the base (six failures),
double-generated into a byte-identical freeze manifest, and committed before
production edits. It reuses the exact frozen NF004 inconsistent-metadata control
from test_inconsistent_metadata_fails, with no new numeric probe or fixture.

For each of tests, harness and determinism, the actual CLI dispatch is exercised
with an instrumented scoring entrypoint:

| Control | Observed order | Scoring calls per mode | Outcome |
|---|---|---:|---|
| Frozen invalid NF004 metadata | frozen_inputs, gold_integrity_precheck | 0 | Invalid, NON-REPORTABLE, repair/rerun required |
| Valid frozen DEV state | frozen_inputs, gold_integrity_precheck, scoring_callback, frozen_inputs | 1 | 17/17 PASS before callback |

The negative case observes `NF004: canonical display disagreement`; it verifies
that neither validation results nor aggregate metrics nor a scoring log are
produced. All six ordering checks pass. This proves pre-entry enforcement,
independently of aggregate reportability after scoring.

Regression manifest:
`evaluation/d2/D2_V2_1_PRESCORING_GATE_REGRESSION_SHA256.txt`.
SHA-256: `d3b979c154a8dfbb290c9da6d23c2765dfac4e1af2f5922bfa46e584c184b496`.

## Targeted validation

| Check | Result |
|---|---|
| Additive ordering regression | 6/6 PASS (two controls in three existing modes) |
| v0.2.1 successor precision | 11/11 PASS |
| Historical suite | 256 active PASS / 1 superseded assertion executed unchanged |
| Frozen DEV integrity utility tests | 4/4 PASS |
| Repair-1 regressions | 5/5 PASS |
| Implementation guards | 22/22 PASS |
| Corrected registered harness | 150/150 PASS |
| DEV gold integrity | 17/17 PASS |
| DEV bundles | 8/8 EVAL_OK per fresh process |
| Successor matrix | 39 PASS / 3 PENDING_JUDGE / 0 FAIL |

The frozen suites produce exactly the pre-existing superseded historical
QUANTUM assertion failure: 298 active passes, one historical failure, raw pytest
exit 1. The existing accounting runner verifies that sole failure and returns
PASS. No historical test was edited, skipped or marked xfail.

Tests, harness observations, DEV integrity and determinism validation payloads
are identical to those in the preceding candidate's validation JSON. The new
machine-readable evidence and raw logs are respectively
`d2_v2_1_prescoring_gate_validation.json` and `d2_v2_1_prescoring_gate_tests.txt`.

## Determinism and error policy

Two fresh processes, ten repeats each of the five existing cases: 100 executions,
plus eight DEV bundles per process. Canonical process reports are byte-identical,
including the prior candidate's hash:
`e36b771ae704a17c3c4c5ba730ce9974ac0f0fae214c90d9c17e0f4e6d70d6a1`.
The existing harness determinism check also passes. Per-case hashes and canonical
Repair-1 results are retained in the validation JSON.

Unexpected evaluator/programming failures still produce EVAL_INTERNAL_ERROR.
For formal reportable checkpoints, any such row makes checkpoint_valid=false
and the aggregate NON-REPORTABLE; evaluator repair/versioning and rerun are
required. The existing frozen fault-injection control verifies that policy.
This post-scoring policy remains separate from the mandatory integrity precheck.
The precheck diagnostic does not assign or change any row-level evaluator status.

## Future TEST policy

The existing frozen contract §P6 remains authoritative. At the first authorized
TEST checkpoint, the caller must:

1. Open and authenticate the authorized frozen TEST gold/map.
2. Bind the authorized deterministic validator for its complete numeric target
   set to the SAME validate_gold_integrity_before_scoring gate. The validator
   must check all applicable frozen numeric/self-consistency constraints and
   return the complete per-target PASS record required by the shared API.
3. Begin the first TEST agent-output scoring only after that gate returns PASS.
4. If it raises, mark the checkpoint invalid and NON-REPORTABLE, prohibit
   scoring/aggregates, repair/version the defect, and rerun the precheck.
5. After successful scoring, apply checkpoint_reportability_v0_2_1 to every
   scheduled evaluator result before producing a reportable aggregate.

No TEST material was accessed. This records the future mandatory call order;
it does not implement or exercise an unauthorized TEST adapter or duplicate §P6.

## Immutable guards and candidate identity

Before edits and after validation, all frozen manifests and their governed
artifacts verified unchanged: 27 historical, seven Repair-1, 14 patch artifacts,
and nine historical normative imports. The original implementation candidate
manifest and every entry were verified before edits. Its manifest bytes remain
unchanged as the historical candidate identity; the successor records the changed
workflow under a new manifest name.

| Manifest | SHA-256 |
|---|---|
| Historical test-author | f69e14f586a6d2fd94b5500d05db5a984c8180cd609d3e2582316ef481c29e22 |
| Repair-1 regression | e010615bc9f27a68e5914da5ee3fadfb0cd52b42211b12366586aaa8cba3cd47 |
| v0.2.1 patch freeze | 49508f8c7421a93910f5188de629f277f44f37d05a2b178e9226e6d554bf0545 |
| Previous implementation candidate | 063cf8d12f4f090ec8e8e2c09dde177823115815194fdeb1a86b2e5bc7581a6d |

New candidate manifest:
`evaluation/d2/D2_V2_1_IMPLEMENTATION_CANDIDATE_V0_2_SHA256.txt`.
Its generator requires two byte-identical generations and verifies every entry.
It retains the preceding candidate identity and records the contract patch,
semantic implementation, regression commit and operational patch commit lineage.
A metadata-only follow-up binds the actual operational commit after it exists,
as in the preceding candidate, avoiding a self-referential commit hash.

## Reproduction

Use the existing audit environment and this checkout as cwd:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests/evaluation:. /mnt/d/projects/d2-v2-independent-audit-blocked-v0.1/venv/bin/python -m pytest -q -s -p no:cacheprovider tests/evaluation/test_d2_v2_1_prescoring_gate.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests/evaluation:. /mnt/d/projects/d2-v2-independent-audit-blocked-v0.1/venv/bin/python -m evaluation.d2.verify_v0_2_1 tests --output /tmp/d2_prescoring_tests.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests/evaluation:. /mnt/d/projects/d2-v2-independent-audit-blocked-v0.1/venv/bin/python -m evaluation.d2.verify_v0_2_1 harness --output /tmp/d2_prescoring_harness.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests/evaluation:. /mnt/d/projects/d2-v2-independent-audit-blocked-v0.1/venv/bin/python -m evaluation.d2.verify_v0_2_1 determinism --output /tmp/d2_prescoring_determinism_a.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests/evaluation:. /mnt/d/projects/d2-v2-independent-audit-blocked-v0.1/venv/bin/python -m evaluation.d2.verify_v0_2_1 determinism --output /tmp/d2_prescoring_determinism_b.json
cmp /tmp/d2_prescoring_determinism_a.json /tmp/d2_prescoring_determinism_b.json
```

## Boundary and next step

Scoring semantics changed: no. Frozen tests modified: no. TEST accessed: no.
Judge: no. Real agent output: no. Orchestrator work: no. New numeric probes: no.
Open-ended audit, merge, tag or push: no.

Repeat the same closed final D2 v0.2.1 acceptance audit. The audit must first
verify gold-integrity precheck ordering for both DEV workflow and future TEST
policy, then execute the already pre-registered validation set. Do not add
new probes. If all checks pass, freeze D2 v0.2.1.
