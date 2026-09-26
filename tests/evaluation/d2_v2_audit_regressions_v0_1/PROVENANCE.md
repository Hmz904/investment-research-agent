# Independent-audit regressions v0.1

These fixtures are byte-for-byte copies of the independent auditor's persisted
counterexamples at /mnt/d/projects/d2-v2-independent-audit-blocked-v0.1.
No locked TEST material or real agent output is present.

Authenticated independent evidence:
- row_evidence.json: 3bd990818c88d218c7cc8e5e4bdc88b5f3fe8d3b174156b58f397c68ae55d942
- all_probe_results.json: c667cb78fcf60e65f6277a0e04496a0222b90bacd847b63094febae57aaee606

F1: deep_valid_DAG: 1,100 identity calculations K901 through K2000,
valid acyclic graph; must remain EVAL_OK, complete, and scored.
F2: derived_output_precision_ignored: 37.4 accepted by target 37 +/- 0.5,
but violates derived EXACT 37; EVAL_OK with incomplete derived pass.
F3: map_false_same_sign_approval: NF012 gold -541 USD_million and copied
comparison -541000000 versus authoritative +541000000, labeled same_sign;
must reject input with no normalized map.
F4: no_counterpart_stage1_blocked: exact temporal binding, empty candidates,
Stage 3 completed but Stage 1 blocked; must reject with no normalized map.
The auditor's no_counterpart_all_complete is the positive F4 control.

F3/F4 use the full authenticated 7,839-fact universe loaded only from
/mnt/d/projects/thesisagent-d2-v2-runtime-data. Fixtures remain unmodified;
source SHA values are computed from canonical objects as required by the API.
The original frozen test-author suite and manifest are not modified.
