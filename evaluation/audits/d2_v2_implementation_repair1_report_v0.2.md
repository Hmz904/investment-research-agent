# D2 v2 Implementation Repair-1 candidate v0.2

Verdict: **D2 V2 REPAIR-1 CANDIDATE READY**.

This candidate repairs exactly the independent auditor's F1–F4 blockers in
blocked implementation base `69beb0dc2b110db26cf3ed6d4b2fdf2ba4193ff4`.
It supersedes that implementation candidate; it does not freeze D2 v2.
The independent re-audit has not been performed.

## Dependencies and evidence

- D2-A: `6a2e577543f8df58e88ba2acda2b14ca945ae1fc`.
- D2-B: `4946e302027f4aab7b09e493ae82f208d5ad75ee`.
- Original test-author freeze: `evaluation/d2/D2_V2_TEST_AUTHOR_FREEZE_SHA256.txt`.
  SHA-256: `f69e14f586a6d2fd94b5500d05db5a984c8180cd609d3e2582316ef481c29e22`.
- Independent evidence root: `/mnt/d/projects/d2-v2-independent-audit-blocked-v0.1`.
- `row_evidence.json` SHA-256:
  `3bd990818c88d218c7cc8e5e4bdc88b5f3fe8d3b174156b58f397c68ae55d942`.
- `all_probe_results.json` SHA-256:
  `c667cb78fcf60e65f6277a0e04496a0222b90bacd847b63094febae57aaee606`.

Both evidence hashes and all 27 original manifest entries were verified before
production changes. Both dependency commits are ancestors of this worktree.
The historical normative imports were also reverified (nine files).
Only the four named counterexamples and the auditor's positive F4 control were
used for reproduction; the complete 150-probe harness was not rerun here.

## Additive regression freeze

Five tests in `tests/evaluation/test_d2_v2_audit_regressions_v0_1.py`: four exact
counterexamples plus one positive Stage-1/2/3 completion control. The five JSON
fixtures are byte-for-byte copies from the independent evidence root. Their
provenance note and the test file are bound by the new seven-entry manifest:

`evaluation/d2/D2_V2_AUDIT_REGRESSION_FREEZE_SHA256.txt`

SHA-256: `e010615bc9f27a68e5914da5ee3fadfb0cd52b42211b12366586aaa8cba3cd47`.

Two independent generations produced identical bytes. The suite was run against
the untouched implementation base: **4 failed, 1 passed**, with exactly the four
audited failures. Baseline output is persisted in
`d2_v2_repair1_baseline_v0.2.txt` beside this report.

AUDIT_REGRESSION_COMMIT: `08d16333d8081d001c5c5c534c042e7c2acda09c`.

This commit precedes every production edit. No regression expectation or frozen
artifact was changed after that commit.

## F1: calculation dependency depth

Baseline: the auditor's 1,100 identity calculations (K901 through K2000) returned
EVAL_INTERNAL_ERROR with RecursionError, null metrics, and an excluded slot.

Repair: derived and upstream calculation resolution now yield dependency frames
to an explicit iterative stack. This preserves depth-first dependency evaluation,
canonical candidate order, active-cycle checks, and the existing CD-01 graph
validation without consuming Python call depth. No depth limit or broad exception
reclassification was added. Unknown programming exceptions retain EVAL_INTERNAL_ERROR.

Post-repair: EVAL_OK; graph valid; agent-output contract valid; complete numeric
answer true; scored slot count 1; included in the scored denominator.

## F2: derived output precision

Baseline: submitted/calculated 37.4 passed target 37 +/- 0.5 and incorrectly
passed the derived specification's EXACT 37 requirement.

Repair: use the existing Decimal/unit/precision comparison machinery to enforce
derived output_precision independently on the submitted claim and calculation
result. Upstream derived specification selection also requires its output
precision. Existing ordinary target comparison and partial numeric credit remain
independent. Existing CALCULATION_OUTPUT_MISMATCH diagnostics identify the failed
complete result binding; no new schema, precision mode, or CD-03 is introduced.
Malformed precision metadata still fails during evaluator input validation.

Post-repair: EVAL_OK; ordinary numeric/precision checks pass; derived complete
pass false; complete_numeric_answer false.

## F3: sign relationship

Baseline: NF012 gold -541 USD_million, copied gold comparison -541000000, and
authoritative +541000000 were accepted under same_sign and emitted an approved
path.

Repair: after authenticating copied comparison coordinates, validate positive,
negative, and zero sign classes against the authoritative signed fact quantity.
The existing fail-closed requirement for schema-bound path-specific opposite-sign
approval remains unchanged; this concrete source adapter cannot manufacture that
approval from a human APPROVE label. Decimal zero follows the existing comparison
semantics; sign normalization or absolute-value equivalence is not introduced.

Post-repair: EVAL_INPUT_INVALID; normalized_map is null; no approved path emitted.

## F4: no-counterpart search completion

Baseline: a schema-valid empty search with resolved temporal identity and Stage 3
completed finalized as NO_APPROVED_XBRL_PATH despite blocked Stage 1.

Repair: require completed Stage 1 and Stage 3. Under mapping specification 6.2,
Stage 2 uses approved Stage-1 parents; accept its not-applicable marker only when
no such lineage exists, otherwise require completion. The existing no-approved-
candidate and no-unresolved-candidate requirements remain. This implements
mapping specification section 7 and the v0.1.2 temporal finalization rule without
performing any new search.

Post-repair: EVAL_INPUT_INVALID; normalized_map is null. The exact auditor control
with all three stages completed remains EVAL_OK / NO_APPROVED_XBRL_PATH.

## Required validation

- Auditor regressions: **5 passed, 0 failed**.
- Original frozen contract cases: **257 passed, 0 failed**.
- Original implementation guards: **22 passed, 0 failed**.
- Total targeted pytest cases: **284 passed, 0 failed, 0 skipped**.
- Test output: `d2_v2_repair1_targeted_tests_v0.2.txt`.
- Original manifest and every original frozen artifact reverified unchanged.
- Audit-regression manifest and all seven entries reverified unchanged.

Reproduction commands (the existing audit venv supplies dependencies only):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests/evaluation:. /mnt/d/projects/d2-v2-independent-audit-blocked-v0.1/venv/bin/python -m pytest -q tests/evaluation/test_d2_v2_audit_regressions_v0_1.py tests/evaluation/test_deterministic_evaluator_contract_v0_2.py tests/evaluation/test_d2_v2_implementation_guards.py --tb=short
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests/evaluation:. /mnt/d/projects/d2-v2-independent-audit-blocked-v0.1/venv/bin/python -m evaluation.d2.verify_repair1_v0_2 --data-root /mnt/d/projects/thesisagent-d2-v2-runtime-data --output /tmp/d2_repair1_process_a.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests/evaluation:. /mnt/d/projects/d2-v2-independent-audit-blocked-v0.1/venv/bin/python -m evaluation.d2.verify_repair1_v0_2 --data-root /mnt/d/projects/thesisagent-d2-v2-runtime-data --output /tmp/d2_repair1_process_b.json
cmp /tmp/d2_repair1_process_a.json /tmp/d2_repair1_process_b.json
```

## XBRL / DEV integration and determinism

Only `/mnt/d/projects/thesisagent-d2-v2-runtime-data` was used as runtime data.
The loader authenticated its 45 provisioned files and produced **7,839 facts**,
fingerprint `acaf087ee2c4fb7427377cae5f1968da26c75d4dfa565f67f1e056b2c4cc4eb6`.
The DEV map and four CSV sources were checked against their pinned byte hashes.
All **eight DEV bundles (DEV01–DEV08)** adapted and evaluated with EVAL_OK using
synthetic limitation outputs; these are input integration checks, not agent scores.

Two fresh Python processes each ran ten repetitions of each of F1, F2, and the
full authenticated XBRL source-map adapter: **60 case executions total**, plus
**16 DEV bundle evaluations** (eight per process). Every per-case canonical
output matched within each process; the entire process reports matched byte for
byte across processes. Their shared SHA-256 is:
`9d2da5c4d051da7606d445fa4099eff020aad903689a51d7c6dd82a4a3dc1d59`.

Combined F1/F2/XBRL canonical output SHA-256:
`ed8cb5ff2ee67e2006f739c2955800c6542ffdab7e46d8d4cec7d929ea153d34`.

Individual output SHA-256:
- F1: `44aedf01458b1af7508cee607441a9de0b0278ecfad51b96577c2a1ff94ab5dc`.
- F2: `be4acb8d5b855c8566d64ad03bacc4cec7c79530e607ec587727187f91032bf6`.
- XBRL: `c46e549769c7aba1c082e96e72f779e039ea9445954d9bbd88c413ebd3715b40`.

Canonical outputs and all eight DEV result hashes are persisted in
`d2_v2_implementation_repair1_validation_v0.2.json` beside this report.

## Candidate identity

D2_REPAIR1_COMMIT: `20d6efd74e466dcc592768b43efdb38b59fba44a`.

New manifest: `evaluation/d2/D2_V2_IMPLEMENTATION_CANDIDATE_V0_2_SHA256.txt`.
The original blocked candidate manifest remains unchanged. The new manifest
binds production modules, validation code/results, this report, implementation
guards, and both test freeze manifests. Its header records all dependency SHAs.
It is generated twice and checked for byte identity, then verified entry by entry.
The repair commit SHA is filled in a metadata-only follow-up after the production
commit exists, avoiding a self-referential Git/SHA-256 hash. That follow-up changes
only this report and the new candidate manifest.

## Boundaries and next step

Original frozen tests modified: no. D2 contract modified: no. TEST accessed: no.
Judge: no. Model inference: no. Real agent output: no. Orchestrator work: no.
Merge/tag/push: no. Independent re-audit: no.
CD-01, CD-02, multiplicity, precision modes, variant families, authoritative fact
universe, EVAL_INCOMPLETE, status namespace, assignment, PENDING_JUDGE, Decimal
arithmetic, and provenance rules remain unchanged.

Run one pre-registered targeted independent re-audit. Re-run the complete
150-probe independent harness, the four F1–F4 reproducer regressions, the
257 frozen contract cases, and the affected 42-row dispositions. Do not
expand exploratory scope unless an existing pre-registered probe itself
reveals a new blocker. If all deterministic rows resolve to PASS and the
three judge rows remain PENDING_JUDGE, freeze D2 v2.
