# D2 v0.2.1 final closed acceptance audit v0.1

## A. Verdict

**D2 V0.2.1 FREEZE READY**

Audit date: 2026-09-26. Workspace: `/mnt/d/projects/thesisagent-d2-v021-final-acceptance`.
HEAD matched `134a16aa3a40faa7ac233f1d5918353795163c07`. The worktree was clean before execution and remained clean until this report was created.

Only the pre-registered acceptance set was executed. No production code, tests, contracts, or probe expectations were modified. No new probes, semantic requirements, or implementation repairs were introduced. No forbidden benchmark directories, review directory, evaluation/results, locked TEST material, or canonical repository data/ were accessed. No model, judge, real agent output, or agent/orchestrator work was used.

## B. Immutable lineage

All named predecessor commits exist and are ancestors of the audited HEAD; committed history preserves the following order.

| Role | Commit |
|---|---|
| Historical D2-A | `6a2e577543f8df58e88ba2acda2b14ca945ae1fc` |
| Historical D2-B | `4946e302027f4aab7b09e493ae82f208d5ad75ee` |
| Repair-1 regressions | `08d16333d8081d001c5c5c534c042e7c2acda09c` |
| Repair-1 implementation | `20d6efd74e466dcc592768b43efdb38b59fba44a` |
| v0.2.1 contract patch | `0b6d22fc563dec40b0ae0ad643b30d0d1792d207` |
| v0.2.1 implementation | `02c55adfd6b93d8cd55a0f0322442ca87c223fe0` |
| Previous candidate metadata | `229003a46ea33321d0573ad94e2f4bb128f5a21a` |
| Pre-scoring regression | `651c172f0ef5d952caf8df744c0b1316f592efb3` |
| Pre-scoring production patch | `e33e3dddaf23fc6629e40b2a4f967665ce92ac8d` |
| Final metadata / audited candidate | `134a16aa3a40faa7ac233f1d5918353795163c07` |

## C. Five manifest identities

Paths below are relative to `evaluation/d2/`. Every manifest identity and every entry passed before execution and after execution.

| Manifest | Entries | SHA-256 |
|---|---:|---|
| `D2_V2_TEST_AUTHOR_FREEZE_SHA256.txt` | 27 | `f69e14f586a6d2fd94b5500d05db5a984c8180cd609d3e2582316ef481c29e22` |
| `D2_V2_AUDIT_REGRESSION_FREEZE_SHA256.txt` | 7 | `e010615bc9f27a68e5914da5ee3fadfb0cd52b42211b12366586aaa8cba3cd47` |
| `D2_V2_1_TEST_AUTHOR_PATCH_FREEZE_SHA256.txt` | 14 | `49508f8c7421a93910f5188de629f277f44f37d05a2b178e9226e6d554bf0545` |
| `D2_V2_1_PRESCORING_GATE_REGRESSION_SHA256.txt` | 2 | `d3b979c154a8dfbb290c9da6d23c2765dfac4e1af2f5922bfa46e584c184b496` |
| `D2_V2_1_IMPLEMENTATION_CANDIDATE_V0_2_SHA256.txt` | 24 | `36a7a88e76242ae03ca273c64d51ae5538264d4909f653fa240c75a2667790d6` |

The 74 manifest entries cover 72 distinct governed paths. The frozen runner also verified nine authenticated historical normative imports.

## D. Pre-scoring enforcement and future TEST policy

Mode: **MANDATORY_PRECHECK**. DEV fail-closed before scoring: **yes**. Future TEST policy fail-closed before scoring: **yes**.

After candidate/manifest authentication, the first executable acceptance check was `test_d2_v2_1_prescoring_gate.py`: **6/6 PASS**. Its instruments exercise the actual CLI dispatch for `tests`, `harness`, and `determinism`.

| Frozen control | Observed events in each mode | Scoring calls |
|---|---|---:|
| Invalid NF004 metadata | frozen_inputs → gold_integrity_precheck | 0 |
| Valid DEV gold | frozen_inputs → gold_integrity_precheck → scoring_callback → frozen_inputs | 1 |

Invalid gold produced `checkpoint_valid=false`, `aggregate_reportability=NON-REPORTABLE`, and repair/rerun required, without a scoring payload or scoring log. Valid DEV gold required all **17/17** targets to pass before dispatch. This demonstrates actual ordering, beyond aggregate publication blocking.

`verify_v0_2_1.main` authenticates frozen evaluator inputs, calls `validate_gold_integrity_before_scoring(validate_dev)`, then dispatches scoring validation. Existing aggregate reportability checks follow scoring; immutable guards are repeated before successful output is written.

The immutable supplement v0.2.1 §P6 and `d2_v2_1_prescoring_gate_report.md` Future TEST policy require: authorized frozen TEST gold/map opened and authenticated → the same shared integrity gate with the authorized complete TEST validator → PASS → first TEST agent-output scoring → aggregate reportability validation. Failure invalidates the checkpoint, prohibits scoring/aggregates, and requires repair/versioning and a fresh precheck. The policy is explicit; no TEST material was opened.

## E. EVAL_INTERNAL_ERROR policy

PASS. Unexpected evaluator/programming exceptions remain `EVAL_INTERNAL_ERROR`. `evaluate_v0_2` preserves system/agent separation. The frozen `internal_error_namespace` fault-injection probe passed.

For any scheduled `EVAL_INTERNAL_ERROR`, the formal checkpoint policy returned exactly `checkpoint_valid=false`, `aggregate_reportability=NON-REPORTABLE`, and `evaluator_repair_and_rerun_required=true`. Supplement §P6 requires an evaluator patch/version and affected checkpoint rerun for reportable DEV/TEST evaluation. Such exceptions are not agent failures.

## F. Historical supersession and active historical suite

**257 historical cases: 256 active PASS, one superseded S2 assertion.** Exact superseded node:

```text
tests/evaluation/test_deterministic_evaluator_contract_v0_2.py::test_D10_quantum_exact_power_and_half_even[1.24-1.23-0.1-1.23-1.23-False-False]
```

Historical bytes are unchanged: SHA-256 `cf914735ddce5b9ba768136fec9532f0a0e9f9cdc034f262d09aed0be9e0f90f`; the diff from D2-B is empty.

The frozen accounting runner executed every historical node, including the superseded assertion. Across its five suites raw pytest returned 298 passed / one failed, exit 1. The sole failure was exactly the node above, whose historical false expectation conflicts with the prospectively frozen S1 replacement. The accounting runner required precisely this outcome and returned PASS. There were no skips, xfails, missing executions, setup errors, or other failures. The additive `test_S1_quantum_classes` case for candidate 1.24/reference 1.23/q 0.1 was active and passed.

## G–J. Frozen suites

| Suite | Active result |
|---|---:|
| Historical contract | 256/256 PASS |
| Successor precision | 11/11 PASS |
| DEV integrity utility tests | 4/4 PASS |
| Pre-scoring ordering regressions | 6/6 PASS |
| Repair-1 auditor regressions | 5/5 PASS |
| Implementation guards | 22/22 PASS |

Successor precision covers independent quantization, NF004, D19, off-grid references, HALF_EVEN ties, preserved historical inputs, regenerated diagnostic intervals, and ordinary agent numeric failure versus evaluator-input failure. The frozen incompatible-constraint control is covered by the four integrity utility tests.

Repair-1 results: F1's 1,100-node valid DAG remains scoreable; F2 enforces derived output precision; F3 rejects the false sign relation; F4 rejects incomplete no-counterpart finalization; the all-stages-complete positive control passes.

## K. Corrected 150-probe harness

**150/150 PASS**. The frozen runner authenticated original harness sources and historical evidence, preserved all 150 active probe inputs, names, order and row bindings, retained 148 expectations, and replaced exactly `inconsistent_derived_output_precision` (D19) and `offgrid_gold` with the frozen successor expectations.

Harness identity SHA-256: `f0c0ee4320be80ccfe6d053308ed7f52ee62088190541c5f5066c7dc8aa978d9`.
Successor expectations SHA-256: `0aa76243856afde1e2d67193ad87a0b17e77dc72a8254b8e93496e52445f0357`.
D19 input SHA-256: `e0fb2e80d3cee77ae99fc383c3e3e394c16bb54769f9063d03384be1c7e758b4`.

The entire current harness validation payload, including recorded input hashes, equals the frozen pre-scoring candidate payload. No probe 151 was added. The unchanged harness's retired runtime no-counterpart parent and its existing conditional child remain explicitly outside the 150, following the frozen collector accounting. The separately frozen `map_states.py` F4 case remains active and passes. No new exclusions were introduced.

## L–M. DEV integrity and XBRL integration

**17/17 DEV numeric targets PASS**, including NF004 and approved variants. Every workflow invocation ran this precheck before scoring dispatch. Repeated prechecks are not additional distinct targets.

Runtime root used exclusively: `/mnt/d/projects/thesisagent-d2-v2-runtime-data`.
All 45 provisioned files authenticated. XBRL facts: **7,839**.
Fingerprint: `acaf087ee2c4fb7427377cae5f1968da26c75d4dfa565f67f1e056b2c4cc4eb6`.

**8/8 permitted DEV bundles PASS**, all EVAL_OK with synthetic outputs. The harness includes these eight checks; each fresh determinism process also validated the eight bundles, yielding 16 repeated bundle evaluations. No real agent output was generated.

## N. S1 / NF004 / D19

PASS. Production `validation_v0_2.numeric_match` implements `Q_q(x) = q * ROUND_HALF_EVEN(x/q)` and compares independently quantized candidate and reference. Historical S2 empty intervals do not control scoring; an off-grid raw reference does not imply an empty acceptance set.

- NF004: reference 56.0468756436 percent, display precision 1, q=0.1; Q(reference)=56.0. Candidate 56.0 passes; 56.1 fails. Neither causes evaluator-input invalidity solely from the off-grid reference.
- D19: target EXACT 37, derived QUANTUM 10, reference 37. Q_10(37)=40 on both sides. Candidate 37 returns EVAL_OK and complete=true. Candidate 38 returns EVAL_OK with ordinary numeric failure and complete=false; it is not evaluator-input-invalid.

## O. CD-01 / CD-02 / CD-03

All required frozen behavior passes.

- CD-01: an invalid agent graph yields RUN_COMPLETED/EVAL_OK, agent_output_contract_valid=false, INVALID_CALCULATION_REFERENCE_GRAPH, and retained slot/denominator. Dependent derived claims receive no numeric credit; independent direct claims score normally. Unexpected evaluator bugs retain EVAL_INTERNAL_ERROR.
- CD-02: select the lexicographically smallest complete-passing eligible variant; with none, select the lexicographically smallest eligible variant for canonical diagnostics. No partial-score maximization or component mixing. String order remains V1 < V10 < V2.
- CD-03 accounting: corrected S1 permits off-grid references and different precision modes. The frozen integrity witness control accepts EXACT 37 plus QUANTUM 10(reference 37), rejects candidate 38, and rejects the incompatible added QUANTUM 10(reference 50) constraint. Existing coordinate/schema checks remain fail-closed. No new constraint solver or EXACT37/EXACT38 probe was introduced.

## P. Successor matrix

**42 rows: 39 PASS, 3 PENDING_JUDGE, 0 PARTIAL, 0 FAIL, 0 unresolved.**
Rows D31, D32 and D33 remain literal PENDING_JUDGE. Each row reconciles to the frozen probe evidence; no judge or proxy was run.

## Q. Determinism

Two fresh Python processes × ten repetitions × five frozen cases = **100 executions**. Cases: F1, F2, XBRL adapter, NF004 and D19. Canonical outputs were identical within each process; `cmp` confirmed complete process reports byte-identical across processes.

Required and observed process-report SHA-256:
`e36b771ae704a17c3c4c5ba730ce9974ac0f0fae214c90d9c17e0f4e6d70d6a1`.

The unchanged harness's existing ten-repeat determinism check also passed. Its canonical output SHA-256 is `0f24ab09fb4b49591f1fe10b44427e9f89e002d6a138788d7df8fc1323fcd073`.

## R. Exact acceptance accounting

- Frozen accounting runner: 299 executed test nodes = 257 historical + 11 precision + 4 integrity utility + 5 Repair-1 + 22 guards. Of these, 298 are active passes and one is explicitly superseded historical evidence.
- First ordering run: six additional active test nodes. Combined pytest accounting: **305 executed nodes, 304 active PASS, one superseded, zero skipped, zero active failures**. The ordering check requested again in the checklist is this same six-case run, not an additional six cases.
- Independent harness: **150 active probes**, all passing; the eight DEV bundle probes are included, not another eight unique harness probes.
- DEV gold integrity: **17 distinct targets**, all passing; repeated workflow validations do not enlarge the target set. Four utility tests above validate the integrity machinery and its controls.
- Successor matrix: **42 reconciled rows**, not 42 additional executable probes; 39 deterministic passes and three permitted PENDING_JUDGE rows.
- Determinism: **five registered cases / 100 executions**, plus 16 repeated DEV bundle evaluations in the two processes. These repetitions do not enlarge the active fixture set. The harness's own frozen repeat check is also preserved.

These are separate measurement units; summing test nodes, target records, matrix rows and repeated executions into one test total would double-count coverage. No pre-registered check is omitted.

## S. Final manifest guards

PASS. All five SHA-256 identities and all 74 entries (72 distinct paths) were rechecked after execution and remained unchanged. The runner's nine historical import guards passed. Historical suite bytes remain identical to D2-B. Current tests, harness, DEV integrity and determinism validation payloads equal their frozen pre-scoring candidate counterparts. HEAD is unchanged. This report is the only repository artifact added by the audit.

## T. Execution evidence and reproduction

The existing audit interpreter was `/mnt/d/projects/d2-v2-independent-audit-blocked-v0.1/venv/bin/python`. Commands used `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests/evaluation:.`, with this workspace as cwd.

First run:

```sh
python -m pytest -q -s -p no:cacheprovider tests/evaluation/test_d2_v2_1_prescoring_gate.py
```

After its six passes, the unchanged frozen workflow ran once in tests mode, once in harness mode, and in two fresh determinism processes:

```sh
python -m evaluation.d2.verify_v0_2_1 tests --output /tmp/d2_final_acceptance_tests.json
python -m evaluation.d2.verify_v0_2_1 harness --output /tmp/d2_final_acceptance_harness.json
python -m evaluation.d2.verify_v0_2_1 determinism --output /tmp/d2_final_acceptance_determinism_a.json
python -m evaluation.d2.verify_v0_2_1 determinism --output /tmp/d2_final_acceptance_determinism_b.json
cmp /tmp/d2_final_acceptance_determinism_a.json /tmp/d2_final_acceptance_determinism_b.json
```

| Temporary execution evidence | SHA-256 |
|---|---|
| `/tmp/d2_final_acceptance_tests.json` | `07fea7be6e3bc7c175e0a1d30b80449f8a30eb10fb1039ece58f7b4ebfec914e` |
| `/tmp/d2_final_acceptance_harness.json` | `869b329b1cad4b25f499703ef79844e77b158de59849282143bca327b1e4daeb` |
| Both determinism process JSON files | `e36b771ae704a17c3c4c5ba730ce9974ac0f0fae214c90d9c17e0f4e6d70d6a1` |

Raw suite output is `/tmp/d2_final_acceptance_tests.txt`. The canonical validation evidence matches the committed candidate evidence authenticated by the final manifest. Exactly one repository report is created: `evaluation/audits/d2_v2_1_final_acceptance_audit_v0.1.md`. Its SHA-256 is returned separately to avoid a self-referential digest.

## U. Freeze recommendation and next step

D2 v0.2.1 deterministic evaluator has passed the final closed acceptance audit and is freeze-ready. Do not perform additional evaluator semantic audits. Next step: freeze/merge/tag the D2 lineage, run authorized main-repository validation, push the evaluator/spec tags, then begin agent_v0.1 production work. The first authorized TEST agent checkpoint remains closed until this freeze is complete.
