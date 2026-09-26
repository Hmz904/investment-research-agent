# D2 v0.2.1 contract/test patch report

Verdict: **D2 V0.2.1 CONTRACT PATCH READY**.
This verdict covers normative/test authoring and static validation. Production
implementation conformance has not been tested in this session.

## Correction and authority

The v0.2 §S5 contract-authoring error interpreted the higher-level mapping rule
as requiring an exact raw reference operand. The clean adjudication restores
historical R7's S1 rule: for positive power-of-ten q,
Q_q(x)=q*round_half_even(x/q); pass iff Q_q(candidate)==Q_q(reference).
Both operands use Decimal semantics and the same ROUND_HALF_EVEN quantum.

The successor supplement P1 and audit erratum list the exact authoritative
sections. P2–P4 replace only affected QUANTUM semantics and explicitly version
the interpretation of historical S2 intervals as superseded derived metadata.
EXACT, ABS_TOLERANCE, source precedence and unrelated scoring rules are preserved.
No general constraint solver, CD-03, or judge proxy was added.

## Successor artifacts

- Contract: `evaluation/d2/deterministic_evaluator_contract_supplement_v0.2.1.md`.
- Only required schema successor: `evaluation/d2/precision_record_v0.2.1.schema.json`.
- Erratum: `evaluation/audits/d2_v2_quantum_audit_semantics_erratum_v0.1.md`.
- Corrected expectation representation: `evaluation/audits/d2_v2_audit_expectations_v0.2.json`.
- Additive assertions: `tests/evaluation/test_d2_v2_1_precision_contract.py`
  and its small synthetic fixture module.
- DEV integrity utility: `evaluation/d2/dev_numeric_self_consistency_v0_2_1.py`,
  with four independent integrity tests and persisted 17-target results.
- Successor matrix: `evaluation/d2/d2_v2_1_preregistration_42_row_matrix.json`
  and its Markdown rendering.
- Static validation utility/report: `evaluation/d2/d2_v2_1_static_validate.py`
  and `evaluation/d2/d2_v2_1_static_validation.json`.

The original 257 contract cases, v0.2 artifacts, nine authenticated historical
normative imports, D2-A and D2-B are unchanged. All 27 original test-author
manifest entries and all seven Repair-1 regression entries were reverified.
Their manifest hashes remain respectively:

```text
f69e14f586a6d2fd94b5500d05db5a984c8180cd609d3e2582316ef481c29e22
e010615bc9f27a68e5914da5ee3fadfb0cd52b42211b12366586aaa8cba3cd47
```

## Audit expectations and input preservation

150 total; 148 unchanged; exactly two changed expectations, solely due to S1:

- `inconsistent_derived_output_precision`: EVAL_INPUT_INVALID becomes EVAL_OK
  with complete_numeric_answer=true. Target EXACT 37 and derived QUANTUM
  10/reference 37 admit 37. The original request bytes, including the stale
  interval, retain SHA-256
  `e0fb2e80d3cee77ae99fc383c3e3e394c16bb54769f9063d03384be1c7e758b4`.
- `offgrid_gold`: EVAL_OK/complete=false becomes EVAL_OK/complete=true because
  candidate/reference 37.1 with q=1 independently quantize to 37.

All 150 inputs remain bound to the original unchanged harness constructors.
Only the two named predicates are replaced by the expectation representation.
All source hashes and historical evidence hashes were checked without running
the harness. No historical observed result or passed flag was rewritten.
No probe 151 was added.

Historical seven-file harness identity:
`f0c0ee4320be80ccfe6d053308ed7f52ee62088190541c5f5066c7dc8aa978d9`.
Successor expectation artifact SHA-256:
`0aa76243856afde1e2d67193ad87a0b17e77dc72a8254b8e93496e52445f0357`.
Together these identify the successor logical harness; exact encoding and
component hashes are recorded in the artifact and erratum.

## Validation results

- Successor precision schema: Draft 2020-12 self-validation passed; local
  references resolved through schema/fixture validation. No other v0.2 machine
  schema literally embeds the corrected S2 rule.
- Patch precision cases: **11**, syntax compiled only. No evaluator import,
  pytest collection, or execution. Expected literals derive from P2–P4.
- Fixture validation: **12** historical-wire requests (11 patch requests plus
  original D19), with **30** separate successor precision projections validated.
- DEV numeric gold self-consistency: **17/17 PASS**. All NF001–NF017 targets,
  including the approved signed V2 variants, were checked. Frozen source hashes
  matched; no gold was changed. Four independent gate tests passed, including
  bad-metadata and incompatible-constraint controls.
- NF004: raw reference **56.0468756436**, p=**1**, q=**0.1**, display value
  **56.0%**, canonical value **0.56 pure**. Target, metadata, answer-variant and
  inherited derived-output precision checks pass.
- Matrix: **42** unchanged row identities; only D10 and D19 records updated;
  **39 COVERED_DETERMINISTIC / 3 PENDING_JUDGE / 0 CONTRACT_DECISION_REQUIRED**.

One preserved original 257-suite D10 parameter expectation also encodes S2:
1.24 versus 1.23 at q=0.1, historically false and prospectively true. The additive
suite asserts the S1 result. The next session must disclose the historical
assertion's supersession when running the unchanged original suite. Do not
silently edit, skip, xfail, or claim all 257 old expectations agree with S1.

Reproduction commands for this authoring validation only:

```sh
PYTHONDONTWRITEBYTECODE=1 python evaluation/d2/dev_numeric_self_consistency_v0_2_1.py
PYTHONDONTWRITEBYTECODE=1 python tests/evaluation/test_d2_v2_1_dev_self_consistency.py -v
PYTHONDONTWRITEBYTECODE=1 /mnt/d/projects/d2-v2-independent-audit-blocked-v0.1/venv/bin/python evaluation/d2/d2_v2_1_static_validate.py
```

## Operational checkpoint rules

Before the first authorized TEST agent output is scored, the numeric gold
self-consistency gate must run on frozen TEST gold after TEST gold/map are
legitimately opened. Use the same precision checks with the then-authorized
source adapter. Gate failure means checkpoint_valid=false; agent scoring MUST
NOT proceed until evaluator/gold semantics are repaired and versioned.

For formal reportable DEV/TEST evaluation, ANY scheduled EVAL_INTERNAL_ERROR
makes checkpoint_valid=false and aggregate results NON-REPORTABLE until the
evaluator defect is repaired/versioned and the affected checkpoint is rerun.
Row-level unexpected programming errors remain EVAL_INTERNAL_ERROR. They are
not converted into agent contract violations. These are operational policies,
independent of agent scoring.

## Freeze and commit identity

Manifest: `evaluation/d2/D2_V2_1_TEST_AUTHOR_PATCH_FREEZE_SHA256.txt`.
It covers only the 14 new successor normative/test/validation/report artifacts
and records immutable dependencies on both historical freeze manifests.
Two independent generations are required to be byte-identical and every entry
verified before the local commit. The manifest omits itself and historical files
to avoid self-reference and preserve historical freezes.

Base: `0bcf1f32524df3a555ef0f09b15c0e4bdd9fb60d`.
Commit message: `correct D2 v0.2.1 quantum precision semantics`.
The actual D2_V021_CONTRACT_PATCH_COMMIT is reported after commit creation in
the final handoff; it is intentionally not inserted into a file hashed by that
same commit. Resolve it independently with:

```sh
git log -1 --format=%H -- evaluation/d2/D2_V2_1_TEST_AUTHOR_PATCH_FREEZE_SHA256.txt
```

The prior local blocker report is preserved outside this freeze as session
history. The user's corrected authorization resolves both earlier blockers.

## Boundary and next session

Production evaluator inspected: no. Production evaluator modified: no.
Production evaluator tests run: no. TEST accessed: no. Judge: no.
Real agent output: no. Blocked Repair-2 incorporated: no. Orchestrator work: no.
Merge/tag/push: no.

Start a new D2 v0.2.1 implementation-patch session from the Repair-1
candidate plus this normative patch. Preserve all historical frozen artifacts.
Change only the QUANTUM implementation and directly required validation
logic, then run the original 257 cases, Repair-1 regressions, v0.2.1 patch
tests, corrected 150-probe harness, 17-target DEV self-consistency gate,
eight DEV bundles, and determinism validation.

Stop after the local normative/test patch freeze. No implementation work is
authorized by this authoring report.
