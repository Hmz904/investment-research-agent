# Agent DEV v0.1 design notes

Status: **draft for review; exclude from future production-agent context**

These notes document benchmark construction decisions. They contain DEV gold
intent and a comparison against locked-test targets, so they must not be
placed in a production agent prompt or tool context.

## Boundary and method

The 16-question `bench_v0.1.1` release became locked TEST at the Week 2
precommit. It was historically used for Week 1 retrieval development and
evaluation; the project does not claim it was untouched before that boundary.
For this design audit, the locked questions, numeric targets, and evidence
items were inspected only to identify their target facts and avoid overlap.
No locked artifact was changed.

All DEV questions are answerable from the frozen 14-document SEC corpus with
corpus fingerprint
`56df698d50b13cf15e913c1c60dbc96b1fd0fab44adb7b1f40ba99771c4b7c96`.
The source contract is limited to 10-Q, 10-K, and earnings 8-K Exhibit 99.1.

## Question rationale and non-duplication

### DEV01 — NVIDIA free-cash-flow sequential decline (numeric)

- Why it exists: tests extraction of a company-defined non-GAAP measure from
  two reconciliation tables, period alignment, and an absolute plus relative
  sequential calculation.
- Failure mode: using revenue or GAAP operating cash flow as free cash flow;
  reversing the decline sign; using the six-month column; or hiding incorrect
  inputs behind a plausible percentage.
- Why it is not locked TEST: locked NVIDIA numeric targets are FY27Q1 Data
  Center revenue/growth and FY27Q2 GAAP gross-margin change. No locked target
  asks for NVIDIA free cash flow or its Q1-to-Q2 decline.

### DEV02 — Microsoft OpenAI EPS impact swing (numeric)

- Why it exists: tests GAAP/non-GAAP basis discipline, sign interpretation,
  prior-year comparison, and a three-stage calculation from a dense table.
- Failure mode: treating the adjustment column as the GAAP effect without
  checking direction; mixing net income and EPS; or reporting only the current
  quarter without the prior-year swing.
- Why it is not locked TEST: locked Microsoft numeric targets are cash
  additions to PP&E for FY26Q3 and derived FY26Q4. The OpenAI-related EPS
  reconciliation is not a locked numeric or evidence target.

### DEV03 — Meta Q2 cash taxes from cumulative 10-Q facts (numeric)

- Why it exists: tests iXBRL/table extraction, quarter-versus-YTD period
  selection, and derivation of a single quarter from separate 10-Q filings.
- Failure mode: returning the $1.999B six-month amount as Q2; using the
  prior-year column; or providing $1.458B without the $0.541B and $1.999B
  inputs.
- Why it is not locked TEST: locked Meta numeric targets concern annual capex
  guidance and its Q1-to-Q2 revision. Cash income-tax payments are not a
  locked target.

### DEV04 — NVIDIA Edge Computing update (update)

- Why it exists: tests a mixed temporal signal, the new market-platform
  taxonomy, driver/offset synthesis, and disciplined product-level
  attribution.
- Failure mode: calling both growth measures accelerating; overlooking the
  consumer-PC offset; or assigning platform revenue to one announced product.
- Why it is not locked TEST: locked NVIDIA evidence focuses on Data Center
  demand acceleration, customer concentration, and related Data Center
  platform recasts. DEV04 targets Edge Computing revenue and its distinct
  workstation/consumer-PC disclosure.

### DEV05 — Microsoft More Personal Computing deterioration (update)

- Why it exists: tests multi-line operating-segment synthesis across Q3 and
  Q4, including one still-positive submetric and a profit-direction reversal.
- Failure mode: reducing the answer to segment revenue; overlooking Search's
  positive growth; or attributing all operating-profit deterioration to Xbox
  charges without a quantified bridge.
- Why it is not locked TEST: locked Microsoft evidence targets Azure,
  Intelligent Cloud, AI infrastructure returns/costs, commercial RPO, and
  changes in AI risk factors. More Personal Computing, Windows, Xbox, and
  Search are not locked target claims.

### DEV06 — Meta infrastructure commitments (update)

- Why it exists: tests distinction among uncommenced leases, contractual
  commitments, contingent obligations, restricted cash, and a subsequent
  event. These are economically important forward obligations but are not
  interchangeable with current capex.
- Failure mode: adding the July $68B leases into the June 30 balance; treating
  all commitments as cash already spent; or omitting the unchanged contingent
  $14.72B amount.
- Why it is not locked TEST: locked Meta evidence targets advertising growth,
  capex guidance, quarterly capex, margin/cash-flow pressure, legal and
  severance charges, and debt issuance. It does not target the Q1/Q2 lease and
  contractual-commitment balances or their period classification.

### DEV07 — Cross-company stock-compensation intensity (comparison)

- Why it exists: tests three-document table retrieval, uniform ratio
  construction, ranking, and comparability caveats.
- Failure mode: using YTD rather than single-quarter stock compensation;
  ignoring NVIDIA's later quarter end; treating a cash-flow addback as cash
  compensation; or ranking raw dollars instead of percentages.
- Why it is not locked TEST: locked cross-company questions compare cash PP&E
  intensity and AI-infrastructure co-movement. They do not target
  stock/share-based compensation or its ratio to revenue.

### DEV08 — NVIDIA debt and shareholder returns (thesis)

- Why it exists: tests multi-part financing-cash-flow synthesis and a direct
  causal-overreach trap. It also requires explaining that the distribution
  increase came mainly from dividends rather than repurchases.
- Failure mode: equating simultaneous debt issuance and distributions with
  traced use of proceeds; missing the dividend step-up; or comparing gross
  flows without net financing cash flow.
- Why it is not locked TEST: no locked question targets NVIDIA debt issuance,
  repurchases, dividends, or funding attribution. Locked NVIDIA questions
  concern operating demand, gross margin, concentration, and cross-company
  infrastructure signals.

## Quality audit

| Audit criterion | Result |
|---|---|
| Exactly eight questions | Pass: 3 numeric and 5 evidence/update/comparison/thesis |
| No locked-target duplication | Pass: checked against question wording, numeric facts, and evidence claims, not merely q_type |
| Answerable from frozen corpus | Pass: every target resolves to listed frozen chunk IDs and accessions |
| Source-scope compliance | Pass: only 10-Q and earnings 8-K Exhibit 99.1 anchors are used; 10-K remains allowed but is not required |
| Fiscal-period clarity | Pass: questions name fiscal labels and/or exact quarter-end dates; period caveats are scored where material |
| Excluded-source dependence | Pass: no transcript, unfiled deck, news, Bloomberg, or external web fact is required |
| Causal discipline | Pass: product attribution, Xbox-cost attribution, commitment recognition, and debt-use claims have explicit guardrails |
| Production-code leakage | Pass: annotations live only under `benchmark/dev/v0.1`; no production code references DEV IDs or gold |
| Evidence anchors | Pass: every numeric fact and evidence part has chunk/accession provenance; multi-part AND semantics are explicit |

## Intended coverage

- Period selection: DEV01, DEV02, DEV03, DEV06, DEV07
- Numeric derivation: DEV01, DEV02, DEV03, DEV07, DEV08
- Tables and iXBRL: DEV01-DEV03, DEV05, DEV07-DEV08; DEV03 uses the
  `us-gaap:IncomeTaxesPaidNet` iXBRL fact
- Multi-part evidence synthesis: DEV04-DEV08
- Temporal update: DEV04-DEV06 and DEV08
- Cross-document/cross-company comparison: DEV04-DEV08, especially DEV07
- Cautious causal interpretation: DEV04, DEV05, DEV06, and DEV08

No DEV outcome has been observed or used to alter these targets.

## Provenance normalization and source audit

The original annotation CSVs already attached chunks to individual numeric
facts and evidence parts. The original `provenance.csv`, however, was a
reverse question/chunk index with multiple target IDs packed into one field.
It was therefore not sufficiently explicit as the authoritative scoring map.

The normalized `provenance.csv` now records one row per target/reference
member and identifies the exact `fact_id` or `(item_id, part_id)`. Direct
candidate references are OR alternatives. When a comparison or derived
semantic part requires more than one filing chunk, one named candidate source
bundle lists those members with an explicit AND operator; alternate bundles
would remain OR. Derived numeric facts have no direct-chunk shortcut and are
resolved through all declared input facts; their source union is retained only
as `derived_input_union` audit lineage.

Final correction-pass audit counts (active/retired status is computed from
the corrected annotations):

- numeric facts: 17, with 9 active answer variants across 6 answer groups;
- direct numeric candidate references: 9;
- derived numeric input-union lineage references: 9;
- evidence items: 28;
- evidence parts: 52 active and 1 retired;
- evidence candidate references: 54 active and 1 retired;
- numeric provenance member rows: 31;
- evidence provenance member rows: 89 active and 2 retired;
- total provenance rows retained for audit: 122;
- orphan targets or provenance rows: 0;
- unresolved source mappings: 0; and
- numeric dependency cycles: 0.

The immutable first-review snapshot is
`benchmark/dev/v0.1/review/dev_gold_review_round1.csv`: 45 `APPROVE`, 15
`REJECT`, and 4 `NEEDS_SOURCE_CHECK`. The corrected packet is
`benchmark/dev/v0.1/review/dev_gold_review.csv`. The final human re-review
approved all 69 active semantic units; the packet retains one retired
DEV04 E05/P2 row with its historical rejection. `SOURCE_CHECK_PASS` remains
Codex source verification, not human approval. The row-level machine trace is
`benchmark/dev/v0.1/review/dev_gold_review_delta.csv`.

### Focused source-audit conclusions

- **DEV01:** The FY27Q2 release chunk `69f2e4ec59c4d8b3` independently shows
  the prior-quarter FY27Q1 free-cash-flow value of `$48.554B` on the same
  company-defined basis and at the same precision. It is an OR alternative to
  the original FY27Q1-release source for `NF001`.
- **DEV02:** The Chinese question asks for the GAAP/non-GAAP “difference” and
  how its direction/magnitude changed, but does not define a subtraction
  order. The Microsoft FY26Q4 three-month reconciliation reports GAAP
  diluted EPS of `$4.81`, an OpenAI adjustment displayed as `$(0.07)`, and
  adjusted/non-GAAP EPS of `$4.74`. The FY25Q4 comparison reports `$3.65`,
  `+$0.21`, and `$3.86`. Under the benchmark's explicit `GAAP - non-GAAP`
  convention, the impacts are `+$0.07` and `-$0.21`, so the year-over-year
  swing is `+$0.28`. Because the wording is neutral, the same answer groups
  also accept the company's displayed adjustment-column convention:
  `-$0.07`, `+$0.21`, and a `-$0.28` change. The two conventions have explicit
  distinct basis labels; opposite signs are never accepted under one label.
- **DEV03:** Meta's Q1 10-Q reports `$541 million` of cash paid for income
  taxes, net, for the three months ended March 31, 2026. The Q2 10-Q reports
  `$1.999 billion` for the six months ended June 30, 2026. The requested Q2
  single-quarter magnitude is therefore `$1.458 billion = $1.999 billion -
  $0.541 billion`; the annotation does not substitute the H1 YTD fact for Q2.
- **DEV04:** Management qualitatively attributes Edge Computing growth to
  Blackwell workstation demand/sales. DEV04 E05/P2 is now explicitly retired
  as a duplicate of E04/P1. Active E05/P3 uses only the Q2 platform table and
  Q2 discussion to state that Blackwell is qualitatively identified as a
  driver but its product-level contribution is not quantified. Active E05/P4
  retains the taxonomy chunk only to identify robotics, automotive, and AI-RAN
  as other listed categories; the Q1 platform composition remains background,
  not a Q2 current fact.
- **DEV05:** The exact Segment Results tables independently support the exact
  `$13.192B` and `$12.854B` MPC values and prior-year comparators. E01/P1 and
  E02/P1 now state the accepted display precision explicitly: approximately
  `$13.2B`/down approximately 1% and approximately `$12.9B`/down
  approximately 4%, with the exact Segment Results values shown in
  parentheses. Each rounded Business Highlights path and exact-table path is
  independently sufficient; the exact-table rates are `-1.3387%` and
  `-4.4383%`, rounded to the reported whole percentages. The discrete-items
  paragraph is a comparison with April 29 guidance, not a decomposition of
  the YoY MPC operating-income decline, and it supplies no item-by-item MPC
  causal bridge.
- **DEV06:** The full frozen March 31 and June 30 chunks contain the annotated
  balances, 2026/2027 buckets, restricted money-market cash, `$14.72B`
  contingent cloud-capacity amount and provider-resale qualifier, Reality
  Labs hardware, and July lease event. The March 31 2026 bucket covers the
  remaining nine months, while the June 30 bucket covers the remaining six;
  despite that shorter window, the amount rises from `$42.25B` to `$53.52B`.
  The additional approximately `$68B` of leases entered into in July is a
  subsequent event excluded from the June 30 reporting-date balance.
- **DEV06 capex boundary:** The June 30 commitment balances are future
  obligations, not themselves evidence of Q2 cash spending or Q2 purchases of
  property and equipment. Meta separately reports capital expenditures as
  including purchases of property and equipment plus principal payments on
  finance leases. The boundary therefore does not claim that applicable
  obligations can never enter future reported capex.
- **DEV06 April transition trap:** The Q1 filing also says that April 2026
  infrastructure contracts increased non-cancelable contractual commitments
  by approximately `$24B`. This is a Q1 subsequent event inside the Q1-to-Q2
  transition window. An agent must not mechanically add that `$24B` on top of
  the June 30 balance or on top of the already-observed Q1-to-Q2 change. This
  is a qualitative-error-analysis note only, not a new scored DEV part.
- **DEV08:** The frozen FY27Q2 10-Q debt note says the `$25.0B` senior notes
  were issued “for general corporate purposes.” That is a broad, non-earmarked
  purpose. Read with the Q2 cash-flow statement, it supports co-occurrence and
  aggregate financing-flow offset but does not trace specific debt dollars to
  Q2 repurchases or dividends; direct dollar-for-dollar causality remains
  unsupported by those cited frozen passages. The final wording uses
  “stated general-corporate purpose,” rather than “broad permitted use.”

### DEV08 management-return versus cash-flow amounts

The question does not explicitly require reconciliation of management's
approximately `$20.0B`/`$26.0B` “returned to shareholders” statements with
the cash-flow amounts of `$19.555B`/`$25.779B`. No additional required scored
part was added. The measures must not be described as numerically identical:
the difference likely reflects reporting, settlement, and/or timing basis,
and would require an explicit reconciliation before being equated.

### Temporal-role correction audit

The all-row audit split DEV06 June 30 balances (`current`) from their Q1-to-Q2
changes (`change`), moved the scheduled-bucket comparison to `change`, made
DEV05 Search `current` only while retaining the 12%-to-10% moderation solely
in DEV05 E03, changed the Q1 DEV04 platform taxonomy and DEV06 category/capex
boundaries to `not_applicable`, and changed the DEV08 Q2 causal boundary from
`change` to `current`. No other row labeled `current` embeds the benchmark's
prior-to-current comparison.

One overbroad DEV07 comparability sentence was narrowed during this audit.
The retained part states only what the cited cash-flow disclosures establish:
the numerator is a non-cash compensation-expense addback, so the revenue ratio
is not a complete measure of compensation economics. No DEV question target
was changed to simplify provenance.

## DEV / locked-TEST chunk-overlap audit

This audit measures shared source chunks, not target duplication. Candidate
chunks were collected from the normalized DEV fact/part provenance and from
all locked-TEST numeric and evidence gold candidate references.

- Unique DEV gold chunks: **29**
- Unique locked-TEST gold chunks: **72**
- DEV chunks also used anywhere in locked TEST: **13**
- DEV chunk-overlap rate: **44.83%** (`13 / 29`)

### Overlap by DEV question

| DEV q_id | Unique DEV chunks | Also in TEST | Overlap chunks |
|---|---:|---:|---|
| DEV01 | 2 | 0 | — |
| DEV02 | 1 | 0 | — |
| DEV03 | 2 | 0 | — |
| DEV04 | 5 | 4 | `3e9b386d72ec488d`, `6e776edb42ae8862`, `79ddd90f5c73467d`, `c2dd3127ada7a30d` |
| DEV05 | 5 | 4 | `0d90ceeeffa01abc`, `6793b711b7fa258c`, `cd43ad63db9cabc4`, `e5efb84cd87d6e58` |
| DEV06 | 4 | 1 | `6f45839ef280a11c` |
| DEV07 | 6 | 4 | `10b5f2f74c4f4541`, `6f45839ef280a11c`, `b4efe4ad5d1fb104`, `e19520eac6dfcec3` |
| DEV08 | 5 | 1 | `513ec1bcd5f5b923` |

### Overlap by locked-TEST question

Only locked questions with nonzero overlap are shown.

| TEST q_id | Shared chunks with any DEV question |
|---|---:|
| Q01 | 1 |
| Q02 | 3 |
| Q03 | 1 |
| Q05 | 4 |
| Q07 | 1 |
| Q10 | 5 |
| Q14 | 1 |
| Q15 | 3 |
| Q16 | 5 |

### Nonzero DEV ↔ TEST pairs

| DEV | TEST | Shared chunks | Classification |
|---|---|---:|---|
| DEV04 | Q01 | 1 | A — same table chunk; Edge Computing vs Data Center numeric target |
| DEV04 | Q02 | 2 | A — same filing/chunks; Edge Computing vs Data Center demand thesis |
| DEV04 | Q05 | 3 | A — same market-platform tables/MD&A; Edge Computing vs Data Center update |
| DEV04 | Q16 | 3 | A — same NVIDIA operating disclosure; Edge Computing vs cross-company Data Center/capex thesis |
| DEV05 | Q07 | 1 | A — broad Q3 release chunk; MPC lines vs Azure/AI-return evidence |
| DEV05 | Q10 | 3 | A — broad releases/segment table; MPC rows vs Intelligent Cloud/Azure update |
| DEV05 | Q15 | 1 | A — broad Q4 release chunk; MPC charge caveat vs cross-company cash-PP&E intensity |
| DEV06 | Q14 | 1 | A — same Meta cash-flow chunk; commitment/capex boundary vs advertising/capex update |
| DEV06 | Q15 | 1 | A — same Meta cash-flow chunk; commitment/capex boundary vs cash-PP&E intensity |
| DEV06 | Q16 | 1 | A — same Meta cash-flow chunk; commitment/capex boundary vs cross-company infrastructure thesis |
| DEV07 | Q03 | 1 | A — same NVIDIA financial statement; SBC/revenue ratio vs gross-margin change |
| DEV07 | Q05 | 1 | A — same NVIDIA financial statement; SBC intensity vs Data Center update |
| DEV07 | Q10 | 2 | A — same Microsoft statements; SBC/revenue ratio vs cloud-return update |
| DEV07 | Q14 | 1 | A — same Meta cash-flow statement; SBC intensity vs advertising/capex update |
| DEV07 | Q15 | 2 | A — same cash-flow statements; SBC intensity vs cash-PP&E intensity |
| DEV07 | Q16 | 2 | A — same cash-flow statements; SBC intensity vs AI-infrastructure co-movement |
| DEV08 | Q02 | 1 | A — same Q1 announcement; capital returns vs Data Center demand evidence |

For the specifically reviewed `DEV05 ↔ Q10` pair, the shared chunks are
`cd43ad63db9cabc4`, `e5efb84cd87d6e58`, and `0d90ceeeffa01abc`.
The first two are broad earnings-release business-highlights chunks and the
third is a multi-segment table. DEV05 targets More Personal Computing,
Windows, Xbox, Search, and MPC operating income. Q10 targets Azure,
Intelligent Cloud profitability/margins, RPO, AI infrastructure cost, and
return realization. The shared container chunks do not create a shared
semantic target.

All 17 nonzero question pairs are **Category A: same chunk, different
target/claim**. **Category B: same or materially overlapping target = 0.**
No DEV question was removed merely because a broad filing chunk is shared.
