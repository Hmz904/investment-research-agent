# Eight human-reported historical blockers: independent successor cases

This audit input is exactly the current human-supplied list. No implementation,
old implementation test, historical evaluator output or validation audit was used
to rediscover failures. Coverage below means authored assertions, not executed tests.
CD-01 and CD-02 are explicitly human-resolved; no contract-decision gate remains.

| Blocker | Successor contract | Machine contract | Independent cases |
|---|---|---|---|
| A unresolved/cyclic references | S3, explicit CD-01 | calculation_graph_validation_v0.2; result v0.2 | test_D03_CD01_invalid_graph: self, 2-node, 3-node, missing source, downstream invalidity; test_D03_valid_DAG; test_D03_CD01_independent_direct_claim. Literal RUN_COMPLETED/EVAL_OK, invalid contract flag, retained denominator, false complete numeric answer and dependent zero are asserted. |
| B ignored multiplicity | S4 | GoldBundle v0.2; answer_group_assignment_v0.2 | test_D14_multiplicity: m=2/one claim, two valid, one wrong, extras; test_D14_positional_assignment_no_rescue: reordered values, earlier mismatch and cross-group rescue prohibited. Group denominator retained. |
| C invalid negative tolerance became agent mismatch | S5 | PrecisionRecord v0.2 | test_D11_invalid_tolerance_is_not_agent_mismatch: negative, malformed, NaN, exponent and float; test_D11_inclusive_tolerance: zero and boundaries; test_D11_no_precision_fallback_after_bad_tolerance. Literal EVAL_INPUT_INVALID/null metrics asserted. |
| D non-power-of-ten quantum | S5; hierarchy overrides dual-rounding | PrecisionRecord v0.2 | test_D10_invalid_quantum_is_input_invalid: 0.03, 0, negative, malformed; test_D10_quantum_exact_power_and_half_even: 1,10,0.1,0.01, positive/negative HALF_EVEN boundaries and unrounded-gold comparison. |
| E permissive concrete source map | S6 | dev_xbrl_source_map_v0.2; NormalizedXBRLMap v0.2 | test_D25_D26_strict_concrete_source_schema: malformed semantic fields and nested approved identity; test_D25_source_semantic_validation_before_adaptation: partitions/counts, copied locator, temporal mismatch, duplicate target, missing upstream input. |
| F rejected no-counterpart | S6 | NormalizedXBRLMap v0.2; concrete source schema | test_D26_nonmapped_legacy_route and test_D26_concrete_source_valid_nonmapped_states cover both unmappable and no_xbrl_counterpart_in_frozen_corpus. No approved XBRL path is invented; legitimate chunk authority survives. |
| G fact existence conflated with approval | S7 | FrozenXBRLFactIndex v0.1; request/result v0.2 | test_D24_D25_authoritative_identity_vs_approval: present approved, present unapproved, forged; test_D24_identity_field_disagreement; test_D24_D25_invalid_authoritative_configuration: map references missing fact, wrong identity, bad count, duplicate ID and wrong fingerprint; exact duration and nonnumeric eligibility cases. |
| H omitted explicit EVAL_INCOMPLETE | S2/S9 | EvaluationSlotRecord and EvaluationCompletion v0.2; result v0.2 | test_D37_D38_replacement_completion: successful/exhausted replacement; test_D36_all_literal_terminal_statuses: all five FAIL_*; test_D39_unknown_or_wrong_namespace_status: unknown status, reserved event and EVAL_INCOMPLETE in wrong namespace; test_D37_invalid_replacement_lineage. |

Broader assertions additionally cover exact/fallback/registered units, sign and
basis, value/period mismatches, coherent variants and identical-pass reporting ties,
input-role/positional binding, no algebraic repair, calculator grammar/precision,
chunk AND paths and wrong-target identity, derived input provenance AND, stable
hallucinated counts, mechanical source scope without prose heuristics, literal judge
sentinels, nonapplicable metrics, aggregate denominators and canonical byte/hash
repeatability. The full original D01–D42 mapping is in the adjacent JSON/Markdown
matrix. All four CD-02-affected rows now have complete deterministic coverage;
39 rows are deterministic and three remain PENDING_JUDGE.
