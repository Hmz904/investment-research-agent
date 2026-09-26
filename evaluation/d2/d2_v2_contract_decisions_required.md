# D2 v2 human contract decisions — resolved register

Open genuine normative decisions: **0**. Freeze-blocking decisions: **0**.
The earlier missing-source stop was SOURCE AVAILABILITY / ISOLATION CONFIGURATION
BLOCKED. Authenticated rehydration resolved it; it was not a human contract decision.

## CD-01 — resolved by explicit human instruction

Schema-valid RUN_COMPLETED with an invalid calculation-reference graph is an
agent semantic contract violation. Preserve RUN_COMPLETED/EVAL_OK and scored
slot; contract-valid=false, INVALID_CALCULATION_REFERENCE_GRAPH, complete numeric
answer=false; graph-dependent numeric credit zero, independent direct claims
ordinary. No synthetic FAIL, evaluator error or infrastructure incompleteness.

## CD-02 — resolved prospectively by explicit human instruction

The authenticated sources left no-complete-pass partial selection undefined.
The user supplied CD-02 after reviewing the authenticated candidate. This current
candidate is continued; no earlier blocked draft is reused. Higher-level rules and
historical v0.1 files remain unchanged.

Exact sources:

- `deterministic_evaluator_contract_supplement_v0.1.md` R5: “Variant selection
  occurs only within the assigned group.” R5 fixes claim assignment but does
  not order variants by failed components.
- Same document R8: “Each assigned answer group selects one complete approved
  variant”; “The evaluator never selects different variants per component to
  maximize score”; and “If multiple complete variants pass identically, the
  lexicographically smallest frozen variant_id is reported.”
- Same document R6: every required input independently passes value, unit,
  precision, provenance and family checks; extras cannot repair missing inputs.
- `eval_protocol_v0.2.1.md` §5: variants within a group are OR; required-input
  correctness has an input-count denominator.
- Same protocol §11: a correct final number with wrong input/formula retains
  final-value credit, but failed components and grounded credit do not.
- `gold_bundle_v0.1.schema.json` `$defs/variant` and
  `$defs/derived_specification`: multiple distinct variants may have the same
  value/unit/period/basis/family but different required inputs/formulas. There
  is no disjointness or equal-partial-vector constraint.


Resolution: determine structural eligibility first, honoring permitted explicit
identifiers. Independently test whole coherent candidates. If any pass completely,
select the smallest passing ID; otherwise select the smallest eligible ID for ALL
partial diagnostics. If none is eligible, select null and NO_ELIGIBLE_VARIANT.
Never maximize partial metrics or combine variant components. Unknown explicit IDs
are contract-invalid without fallback. Judge-dependent metrics remain PENDING_JUDGE.

The previous options (new whole-candidate ordering, excluding ambiguous gold, or
set-valued partial diagnostics) are closed: the human selected the explicit whole-
candidate lexicographic convention, not gold exclusion or set-valued scoring.

Test impact: D14, D15, D16 and D19 are now COVERED_DETERMINISTIC. Required A–H
regressions include complete alternatives, passing ties, unequal failed partials,
canonical formula/input diagnostics, serialized order invariance, explicit valid
and invalid IDs, and empty eligibility. The synthetic witness is retained with
literal canonical expected results. No decision remains unaccounted for.
