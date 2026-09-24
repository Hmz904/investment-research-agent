# XBRL mapping human-review rubric v0.1

Status: **draft evaluation-only rubric; no mapping decisions are included**

Rubric version: `xbrl_mapping_review_rubric_v0.1`

Review uses only frozen target/source metadata, the frozen corpus, and
authoritative XBRL records. Agent outputs are prohibited inputs. The generator
defines search scope; the reviewer may adjudicate semantic equivalence but may
not add facts, broaden predicates, or choose which unlinked facts to search.

## 1. Candidate-level decisions

Every emitted candidate receives exactly one decision:

- `APPROVE`: all applicable checks pass and the fact represents the same
  economic target. It may become an approved OR-path.
- `REJECT`: authoritative evidence establishes a mismatch. Record failed
  checks and reproducible rationale.
- `NEEDS_SOURCE_CHECK`: structured metadata are insufficient to decide safely.
  This is mandatory initially for every Stage-3 different-concept candidate
  and every unresolved sign/basis case.

`REJECT` does not mean that no XBRL counterpart exists or that the target is
unmappable. `NEEDS_SOURCE_CHECK` is a candidate state, not a final target
status. No other candidate token is allowed.

## 2. Required checks for `APPROVE`

The reviewer affirmatively confirms every applicable item:

1. **Entity** — company/entity and CIK agree with the target.
2. **Economic concept** — exact concept semantics represent the same economic
   quantity; numeric equality alone is insufficient.
3. **Value** — canonical signed value satisfies the frozen comparison rule.
4. **Registered precision** — `precision_rule_id`, frozen rule source,
   quantum/tolerance, and interval are pre-registered; no reviewer-created or
   widened tolerance is used.
5. **Unit comparison** — exact equal labels may use
   `exact_label_match` without conversion or inferred dimension. Different
   labels require `registered_equivalence`, compatible registered dimensions,
   and exact scaling. The recorded rule ID is absent for exact-label fallback.
6. **Per-share subtype/basis** — raw `USD/shares` does not by itself establish
   basic/diluted, adjusted, or GAAP status; concept and target semantics do.
7. **Sign/basis** — economic signs and bases agree, or one path-specific
   `opposite_sign_explicitly_approved` relationship records both signs,
   declared basis relation, and source-bound rationale.
8. **Period type and dates** — instant versus duration and exact dates agree.
9. **Quarter/YTD/annual meaning** — duration semantics agree where applicable;
   filing labels alone are insufficient.
10. **Dimensions** — complete axis/member structure is exact and economically
    appropriate.
11. **Filing/comparative role** — accession and original/comparative-column
    interpretation support the target.
12. **No conflicting context** — no consolidation, segment, class, geography,
    or other context metadata conflicts.
13. **Authoritative provenance identity** — locator, accession, concept,
    context, raw unit, value, dates, dimensions, and optional chunk link match
    the authoritative record exactly.
14. **Same economic target** — the complete evidence supports the target, not
    merely an equal number.

An inapplicable check must be identified and explained; it cannot be silently
skipped.

## 3. Stage and lineage rules

- Stage 1 direct chunk/value linkage is candidate discovery only.
- Stage 2 requires a named Stage-1 parent whose final status is `APPROVE`.
  It must retain the exact concept, entity, economic dates, dimensions, and
  canonical signed quantity. A different concept or numeric value is a
  generation defect, not a review judgment. Recast values are not Stage-2
  duplicates.
- Stage 3 receives only mechanically generated candidates satisfying frozen
  entity, value/precision, unit, temporal, dimension, accession, and filing
  eligibility predicates.
- Every Stage-3 different-concept candidate starts `NEEDS_SOURCE_CHECK`. It may
  become `APPROVE` only after source-bound review establishes the same target.
- Reviewers do not scan unrelated facts, widen periods, add aliases, create
  tolerance, or alter generation scope.

## 4. Rationale and opposite-sign requirements

Each review record identifies target and candidate IDs, stage, parent lineage
where applicable, generation rule, decision, checks passed/failed/unresolved,
source/accession/context evidence, precision and unit conclusion, sign/basis
conclusion, temporal/dimension conclusion, reviewer/date audit metadata, and a
concise reproducible rationale.

For `opposite_sign_explicitly_approved`, record gold/display sign,
gold canonical/economic sign, authoritative XBRL sign, the exact declared
basis relationship, and why the specific source and concept still represent
the same target. “Same magnitude” is insufficient. The decision applies only
to that path.

## 5. Target-level finalization

Direct targets use a separate final namespace:

- `mapped`: at least one candidate completed `APPROVE`, and each approved path
  exactly matches its authoritative fact.
- `no_xbrl_counterpart_in_frozen_corpus`: all Stage-1 discovery, applicable
  approved-lineage Stage 2, and deterministic Stage 3 completed; no candidate
  was approved; and no unresolved candidate/constraint remains. This says only
  that the frozen local process found no eligible counterpart.
- `unmappable`: potentially relevant structured evidence or a semantic
  limitation remains, but frozen rules cannot adjudicate faithfully.

No-counterpart is not evaluator failure, agent error, or a claim about external
XBRL availability, and it is excluded from the unmappable rate. Unmappable is
an evaluator/mapping limitation and is not automatically agent error. Both
retain legacy chunk authority and receive no XBRL approved-path credit.

Derived targets use the separate `derived_via_inputs` resolution mode and an
AND-set of required inputs; they do not receive one of the direct-target
mapping statuses. Every required input must independently have an allowed,
adjudicable frozen provenance route. An unsupported required input makes the
derived target ineligible for full grounded correctness; resolution mode alone
never supplies support.

No-counterpart cannot be inferred from “no Stage-1 fact” or from one or more
`REJECT` decisions alone. A remaining `NEEDS_SOURCE_CHECK` candidate at freeze
requires resolution or `unmappable`; it cannot be relabeled no-counterpart.
