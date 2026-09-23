# Benchmark Protocol

Schema version: `v0.1.2`

Benchmark tags:
- `bench_v0.1-numeric`
- `bench_v0.1-checklist`
- `bench_v0.1-full`

This document freezes the annotation and scoring rules for benchmark v0.1.
Frozen benchmark records must never be modified in place. Any factual,
wording, annotation, or scoring change requires a new question/evidence
version and a new benchmark tag.

---

## 1. Source contract

Allowed source types:
- SEC 10-Q
- SEC 10-K
- Earnings 8-K Exhibit 99.1

Excluded from v0.1:
- Earnings-call transcripts
- Investor-relations slides unless filed as Exhibit 99.1
- News
- Third-party research
- Web commentary

A fact may be true but still be out of scope.

Evidence from an excluded source:
- does not count as a benchmark hit;
- is recorded as `source_scope_violation`.

Q09 has an additional comparison constraint:
- comparison baseline must be `(Microsoft FY26 Q3 10-Q, Microsoft FY26 10-K)`;
- annual-to-annual FY25 10-K vs FY26 10-K comparisons do not substitute for
  the required baseline.

---

## 2. Frozen question sets

### Numeric benchmark

- Q01@1
- Q03@1
- Q06@2
- Q08@2
- Q11@1
- Q13@2

### Checklist benchmark

- Q02@2
- Q04@2
- Q05@2
- Q07@2
- Q09@2
- Q10@2
- Q12@2
- Q14@2
- Q15@2
- Q16@2

Full benchmark = all 16 questions above.

---

## 3. Numeric-answer semantics

`numeric_answers.csv` uses globally unique `fact_id`.

### Roles

`role = answer`
- participates directly in scoring.

`role = input`
- does not directly participate in question scoring;
- may be either a directly reported fact or a derived fact;
- may be used by other formulas.

`input_items` may reference any existing fact_id, regardless of whether the
referenced row has role `answer` or `input`.

The fact dependency graph must be acyclic.

### Answer groups and methods

Within one numeric question:

- different `answer_group` values are AND conditions;
- different verified answer variants inside the same `answer_group` are OR
  conditions.

A numeric question is fully correct only if every required answer_group has
at least one correctly matched verified variant.

Example:
- Q01 revenue and YoY growth are two different answer groups: both required.
- Q03 reported +0.1pp and derived-exact +0.0418pp are two valid methods for
  the same answer group: either is acceptable.

### Display precision

Different accounting/measurement methods must not be merged using a wide
tolerance.

Each verified answer variant is evaluated independently at its annotated
display precision. Reasonable equivalent rounding is accepted.

If a directly reported value and a value derived from other reported values
differ only by independently rounded inputs, both may be acceptable only
when:
1. they describe the same economic quantity;
2. period and accounting basis are compatible; and
3. the discrepancy is fully explainable by the source values' rounding.

Claims should prefer the directly reported value where one exists.

### Signs

For expenditure questions, benchmark values use positive expenditure
magnitudes unless the question explicitly asks for the cash-flow statement
sign.

---

## 4. Evidence-checklist semantics

Evidence importance levels:

- `core`: weight 3.0
- `supporting`: weight 1.5
- `optional`: weight 0.5

Report at least:
1. weighted evidence score; and
2. unweighted core-evidence recall.

The exact semantic evidence-matching implementation is deferred to the
evaluation stage, but the annotation semantics in this document are frozen.

### Update questions

For update questions, a valid answer must demonstrate temporal updating
rather than simply answering the latest-period thesis from scratch.

Where applicable, the checklist contains:
- `prior_period`
- `current`
- `change`

At least one core item from each required temporal role must be recovered.

### Correction evidence

When new evidence directly overturns or materially revises a prior-period
checklist item, its importance should by default be no lower than that of the
item being revised, unless the same information is already covered by another
core item.

---

## 5. Stance and mixed evidence

Allowed stance values include:
- `support`
- `contradict`
- `context`

Evidence containing meaningful facts pointing in opposite directions should
use `stance = context` rather than being duplicated into separate support and
contradict items solely to obtain extra scoring weight.

The claim should state both directions clearly.

Comparison questions may also use `context`; the comparison conclusion is
carried by the claim rather than introducing a new stance enum.

---

## 6. Provenance and versioning

### Evidence IDs

Once assigned, `item_id` must never be reused.

Deleted or invalidated evidence becomes:
`verification_status = retired`

IDs must not be renumbered after deletion.

Cross-question evidence references must use the complete form:

`(q_id, q_version, item_id)`

### Fact identity

Financial fact identity is provenance-sensitive.

At minimum, distinguish facts by:
- concept/economic quantity;
- period;
- accession.

Two facts with the same numeric value may remain separate if they originate
from different filings or represent different PIT/recast states.

Example:
a Q1 value first reported in the Q1 filing and the numerically identical value
reconfirmed/recast in the Q2 filing may have separate fact_ids.

### Direct disclosure

When a value is directly disclosed by the company, the directly reported fact
is preferred over reconstructing it from component values.

Derived values may still be stored for consistency checks.

### Recasts

Historical values must never be silently overwritten after a later filing
recasts prior periods.

Keep both:
- the original point-in-time disclosure;
- the later recast version.

Which version is appropriate depends on the research question.

---

## 7. Evidence periods and accessions

For simple current-period evidence, `evidence_period` and `accession` may be
single values.

For change or cross-company evidence, ordered lists are permitted.

The provenance must allow the evaluator to recover which period and filing
supports each part of the comparison.

---

## 8. Error taxonomy

Evaluator records these failure modes separately from ordinary missing
evidence.

### `basis_mismatch`

The facts are individually valid and in scope, but economically incompatible
accounting or management definitions are compared without normalization.

Example:
Meta management capex including finance-lease principal payments vs
Microsoft cash Additions to PP&E.

### `source_scope_violation`

The answer relies on evidence outside the frozen source contract.

### `period_misalignment`

The answer compares non-equivalent time periods as though they were aligned.

Example:
matching Microsoft and Meta solely by fiscal-quarter number rather than
calendar dates.

### `causal_overreach`

Source, period, and accounting basis may all be correct, but the answer
promotes correlation, co-movement, or aggregate consistency into a causal or
customer-level relationship that the filings do not identify.

### `reverse_control_false_positive`

The answer claims a known reverse-control item is new, expanded, relevant, or
causal when the frozen annotation says otherwise.

---

## 9. Question-specific rules

### Q07

Gross-margin evidence must identify the reporting level.

- "Microsoft Cloud gross margin" may match the Microsoft Cloud item.
- "Company-wide GAAP gross margin" may match the company-wide item.
- An unspecified statement such as "gross margin declined" does not match
  either item.

### Q09

A checklist hit requires:
1. finding the correct risk-factor content; and
2. not classifying it as `wording_only`.

`new_topic` vs `material_expansion` classification is reported separately as
an auxiliary classification-accuracy metric and does not by itself determine
whether the evidence item was found.

Q09 reverse controls:
- C7
- C8
- C13a
- C14
- C15

Claiming these as newly introduced or materially expanded is a reverse-control
false positive.

### Q12

Reverse control:
Meta Q1 net income growth of approximately 61% was materially affected by a
large income-tax benefit and must not be treated as direct evidence that AI
infrastructure investment was generating operating returns.

### Q14

For the operating-profit sensitivity item, a valid hit must:
1. mention the disclosed legal-proceeding charges and severance expenses; and
2. note that even after mechanically adding back those specified charges,
   the derived operating margin remains materially below the prior-year level.

This calculation is a benchmark sensitivity analysis, not a company-reported
non-GAAP measure.

Reverse control:
attributing the full reported Q2 operating-profit decline to AI investment
without separating the specified legal and severance expenses.

### Q16

Aggregate capex/revenue co-movement does not identify Microsoft- or
Meta-specific purchases from NVIDIA.

Reverse controls include:
- claiming Microsoft capex caused NVIDIA revenue growth;
- claiming Meta capex caused NVIDIA revenue growth;
- assigning an observed portion of NVIDIA revenue to Microsoft or Meta
  without filing evidence.

Such claims are recorded as `causal_overreach`.

---

## 10. Reverse controls

Reverse controls do not receive positive checklist weight.

They are retained to measure false-positive behavior.

A reverse-control false positive should be reported separately from ordinary
evidence recall.

---

## 11. Annotation verification

Verification statuses:
- `pending`
- `verified`
- `rejected_misinterpretation`
- `rejected_not_found`
- `needs_revision`
- `retired`

Annotation provenance fields should distinguish:
- `labeled_by`
- `verified_by`
- `verified_date`

Where draft provenance is retained, use:
- `claude_draft`
- `reviewer_added`

---

## 12. Annotation Revision Audit

The originally planned blind human-vs-LLM calibration was not performed,
because the benchmark was built iteratively and all final items were exposed
to reviewer feedback.

Do not report the revision audit as inter-annotator agreement or blind
calibration.

Instead retain initial drafts and later compute an `Annotation Revision Audit`
with categories such as:
- unchanged
- wording_only_revision
- stance_change
- importance_change
- numeric_correction
- source_or_provenance_correction
- deleted_or_retired
- reviewer_added
- inferential_overreach_correction

The audit should be generated programmatically from retained drafts and the
frozen benchmark where possible.

---

## 13. Freeze discipline

Frozen benchmark rows are immutable.

If a factual or annotation error is discovered:
1. do not edit the frozen version in place;
2. create a new question/evidence/fact version as appropriate;
3. retire the superseded version where necessary;
4. create a new benchmark tag.

---

## 14. Known benchmark notes

Q08:
The answer can be derived from the FY26 10-K annual value minus FY26 nine-month
YTD data, but FY26 Q4 Exhibit 99.1 also directly reports the quarterly value.
Therefore Q08 is a strict period-derivation test only under a 10-K-only
retrieval restriction.

Potential v0.2 extensions:
- earnings-call transcripts;
- Microsoft management capex / finance-lease alternative normalization;
- Q4 Microsoft Cloud quarterly margin;
- Microsoft FY27 useful-life accounting-estimate change;
- annual-to-annual risk-factor comparison.

---

## 15. Calendar alignment and period-scope semantics

`calendar_period` is an approximate calendar-alignment label, not the
authoritative accounting period.

For non-calendar fiscal quarters such as NVIDIA:
- FY27Q1 is aligned approximately with calendar 2026Q1;
- FY27Q2 is aligned approximately with calendar 2026Q2.

The underlying fiscal quarters are offset from exact calendar quarters.
Cross-company analysis must therefore use the actual filing period dates and
explicitly disclose material timing mismatch. Q16 specifically tests this
limitation.

`period_scope` in `numeric_answers.csv` is a descriptive, human-readable
label. It must not be parsed as an authoritative machine taxonomy.
Single-quarter, YTD, annual, recast, and derived status should instead be
determined from explicit fact/table period metadata, provenance, and formula
fields.

A blank `tolerance` means that the default benchmark rule applies: compare
against each answer variant at the precision represented by that variant.
Scoring code should preserve the lexical representation of `value` before
numeric conversion so that values such as `92`, `0.1`, and `92.386` retain
their annotated precision.

When multiple accessions or fact references are stored in one CSV field,
they are semicolon-separated. Ordered lists should preserve the logical
ordering of the corresponding comparison or derivation.

---

## 16. Scoring eligibility

Only evidence rows with `verification_status = verified` are eligible for
positive checklist scoring.

Rows with `verification_status = retired` are retained for provenance,
revision-audit history, or negative/control purposes and carry zero positive
weight.

In particular, Q15@2 E07 is retained as a source-scope control because its
earnings-call figures are outside the v0.1 source contract. Reliance on those
figures records `source_scope_violation`; the row itself cannot produce a
positive evidence hit.

---

## 17. Evidence-type and temporal-role enums

Allowed `evidence_type` values:
- financial_metric
- management_guidance
- risk_factor
- customer_demand
- capacity_supply
- competitive
- regulatory
- accounting_policy
- other

`temporal_role` describes the role of evidence in benchmark reasoning:

- `current`: evidence anchored in the current benchmark period. A metric may
  itself be YoY and still be `current`.
- `prior_period`: evidence explicitly carried forward from a prior benchmark
  state in an update question.
- `change`: evidence explicitly comparing or revising two benchmark/source
  states, rather than merely reporting a current-period YoY metric.
- `cross_company`: evidence whose claim explicitly compares multiple companies.

`depends_on` identifies prior benchmark question states required by the
question's reasoning workflow. Mere reuse of a fact or evidence theme from
another question does not by itself create a dependency.

---

## 18. Source-manifest composition

The v0.1 retrieval corpus consists of all 14 documents listed in
`source_manifest.csv`.

Twelve documents belong to the principal benchmark periods.

Two additional NVIDIA filings are historical-reference documents included
because benchmark questions require prior-period evidence:

- NVIDIA FY26 Q2 10-Q, accession `0001045810-25-000209`
- NVIDIA FY26 Q4 earnings 8-K Exhibit 99.1, accession
  `0001045810-26-000019`

Each source-manifest row has a `source_role`:

- `benchmark_period`
- `historical_reference`

Historical-reference documents are part of the allowed retrieval corpus even
though they are not themselves target benchmark periods.

This distinction is intentional: some questions require the agent to retrieve
historical filings in order to establish the correct comparison baseline.
