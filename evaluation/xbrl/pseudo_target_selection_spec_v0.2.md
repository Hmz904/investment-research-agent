# Frozen-corpus pseudo-target selection procedure v0.2

Status: **selection rules fixed before v0.2 candidate outcomes are inspected**

Version: `pseudo_target_selection_spec_v0.2`

Inputs are only frozen local XBRL facts, ingestion metadata, and `temporal_context_catalog_v0.1`. Benchmark questions, target IDs, gold, answer values, labels, review decisions, and agent outputs are prohibited. Facts are ordered by stable authoritative fact identity. Categories are processed A through I. Within each category, the first structurally eligible unused fact or tuple is selected; if all eligible facts were used, the first is reused and reuse is recorded. Selection is never retried because of validation outcome.

Categories A-H preserve v0.1 intent under provenance-anchor temporal resolution:

1. **A — direct chunk-linked:** first numeric registered-unit fact with an authoritative chunk and exact context.
2. **B — dimensional/segment:** first A-eligible fact with a nonempty complete axis/member structure.
3. **C — comparative context:** first chunk-linked numeric fact whose exact end/instant precedes its filing's authoritative period of report.
4. **D — Stage-2 duplicate:** first cross-filing pair with the same entity, exact concept, exact temporal object, dimensions, raw-unit representation, and signed canonical value; the first fact is chunk-linked.
5. **E — exact anchor temporal resolution:** first chunk-linked fact whose approved chunk plus exact concept uniquely resolves its XBRL context before mapping search. The old benchmark-label parser is not used.
6. **F — Stage-3 different concept:** first pair sharing entity, exact temporal object, dimensions, registered unit dimension, and signed canonical value but having different concepts. The target has no approved chunk, so Stage 3 surfaces the pair; different-concept semantic identity remains unresolved without source review.
7. **G — comparative durations:** first same-entity, same-end pair of distinct duration contexts, followed by the first numeric fact in each.
8. **H — instant:** first chunk-linked numeric instant fact.
9. **I — DIMENSIONAL_STAGE3:** first stable numeric fact with nonempty dimensions and exact context for which removing approved chunks causes Stage 3 to execute instead of complete resolution by Stage 1. The target retains the exact dimensions and source accession. No benchmark input or reselection is allowed. If none exists, record `COVERAGE_GAP_NO_NATURAL_DIMENSIONAL_STAGE3_CASE`; never fabricate a fact.

Validation exercises Stage 1, Stage 2, Stage 3, dimensions, comparative contexts, exact anchor resolution, a synthetic closed-set fallback over precomputed catalog rows, and different-concept source-check behavior. Rules are not changed in response to results.
