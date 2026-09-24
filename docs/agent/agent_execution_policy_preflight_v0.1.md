# Production execution-policy preflight v0.1

Status: reviewed production-side preflight. The infrastructure retry and
replacement limits in Section 13 are `HUMAN-APPROVED`. The unresolved choices
listed in Section 17 remain open. This document does not implement the agent,
evaluator, provider integration, retries, pagination, or a new model-visible
action. It did not read DEV/TEST gold or run the complete pytest suite.

Frozen inputs:

- `agent_architecture_v0.1`: `1c61afa444967d2c3d80276d9992375b094457f9`
- `tool_runtime_v0.1`: `9aff4d5c31ec9ac4c1c52434d67da99da8ec696c`
- tool specification SHA-256:
  `879a710485ac42b6dc0793b0556ce811d4efb151b52a7ae69f90334d489db70d`
- final semantic output schema: `agent_output_schema_v0.1.1`

Numeric policy settings below are either explicitly marked
`HUMAN-APPROVED` or remain `PROPOSAL_FOR_HUMAN_DECISION`.

## 1. Frozen public API audit

### Retrieval

`retrieval.search(query: str, top_k: int = 10)` requires a non-whitespace
query and accepts integer `top_k` in `[1, 50]`. Retrieval always builds the
frozen BM25/dense union and reranks it before applying public `top_k`.

### XBRL concept discovery

`xbrl.search_concepts(query: str, top_k: int = 10)` requires a non-whitespace
query and accepts integer `top_k` in `[1, 50]`. It returns observed exact QNames;
it does not provide taxonomy labels or synonyms.

### Exact `xbrl.query_facts` surface

The exact public signature is:

```text
xbrl.query_facts(
    *,
    concept: str,
    accession: str | null = null,
    company: str | null = null,
    form_type: str | null = null,
    filing_fiscal_period: str | null = null,
    period_start: str | null = null,
    period_end: str | null = null,
    instant: str | null = null,
    unit: str | null = null,
    include_dimensions: bool = true,
)
```

`concept` is required and must be a case-sensitive exact observed concept.
Every supplied filter is exact equality. The available filters are:

- `accession`: exact SEC accession shape;
- `company`: exact filing company value;
- `form_type`: exact filing form;
- `filing_fiscal_period`: exact filing-level value, not a fact fiscal-year
  classifier;
- `period_start` and `period_end`: exact duration boundaries;
- `instant`: exact instant date;
- `unit`: exact raw ingested unit reference; and
- `include_dimensions`: defaults to `true` and only changes returned dimension
  payload, never row selection.

`instant` cannot be combined with either duration boundary. There is no
`context_ref`, dimension axis/member, fiscal-year, frame, label, taxonomy,
limit, page, cursor, preferred-context, latest, consolidated, or
dimensionless filter. There is no implicit quarter/YTD classification, sign
change, rescaling, deduplication, or fact selection. Results contain every
matching row in stable fact-identity order. This is the complete filter
surface used by the oversized-result analysis.

### Calculator

`calculator.calculate(expression, inputs, result_metadata=None)` evaluates the
frozen exact-decimal expression grammar over explicitly named inputs. Inputs,
units, and provenance are retained; the calculator performs no semantic source
selection or unit conversion.

## 2. Size audits

The complete machine-readable measurements are in
[`tool_output_volume_preflight_v0.1.json`](../../evaluation/audits/tool_output_volume_preflight_v0.1.json).
Approximate tokens use the available
`BAAI/bge-reranker-v2-m3` `tokenizer.json`; this is explicitly approximate and
is not a provider/model choice.

### All 1,662 chunks

| measure | p50 | p95 | p99 | max |
|---|---:|---:|---:|---:|
| characters | 339.5 | 4,868.95 | 5,286 | 6,864 |
| approximate tokenizer units | 91 | 1,044 | 1,121.78 | 1,555 |

Descriptive bounds, not quality estimates:

| K | K×p99 chars | K×max chars | K×p99 approx tokens | K×max approx tokens |
|---:|---:|---:|---:|---:|
| 5 | 26,430 | 34,320 | 5,608.9 | 7,775 |
| 10 | 52,860 | 68,640 | 11,217.8 | 15,550 |
| 20 | 105,720 | 137,280 | 22,435.6 | 31,100 |
| 50 | 264,300 | 343,200 | 56,089 | 77,750 |

These bounds use chunk text only. Native result serialization can be much
larger because table metadata can contain repeated structured payloads.

### Retrieval audit

The accepted audit dataset contains one completed `RetrievalTool` response for
each of the ten required generic queries with `top_k=50`. An earlier CPU-stalled
attempt produced no returned query result and was stopped before being included
in the dataset. K=5, 10, and 20 are prefixes of each accepted returned
response; all 30 prefix checks passed (`top5`, `top10`, and `top20` for every
query).

The table reports native ordered `RetrievalResult.to_dict()` serialization,
including native table metadata, followed by cumulative chunk text characters.
This is an upper-volume audit, not the proposed compact model rendering.

| query | candidate pool | K=5 chars/tokens | K=10 chars/tokens | K=20 chars/tokens | K=50 chars/tokens | K=50 chunk chars |
|---|---:|---:|---:|---:|---:|---:|
| auditor tenure | 51 | 438,270 / 210,092 | 1,014,716 / 481,140 | 1,538,612 / 729,992 | 1,890,155 / 892,500 | 61,094 |
| environmental regulation | 85 | 25,741 / 6,155 | 54,152 / 13,081 | 103,538 / 25,113 | 237,894 / 58,492 | 206,425 |
| director independence | 50 | 14,218 / 3,945 | 38,889 / 10,365 | 86,543 / 23,501 | 140,537 / 42,538 | 96,683 |
| pension obligations | 92 | 587,319 / 277,405 | 828,805 / 389,152 | 2,059,499 / 959,238 | 3,114,935 / 1,440,209 | 85,439 |
| inventory accounting | 93 | 15,850 / 6,025 | 82,207 / 34,128 | 832,638 / 402,673 | 1,675,565 / 793,013 | 90,694 |
| goodwill impairment | 79 | 25,697 / 6,698 | 49,932 / 14,095 | 88,698 / 25,991 | 1,450,255 / 678,915 | 109,389 |
| foreign subsidiaries | 80 | 31,166 / 12,354 | 57,877 / 18,891 | 85,941 / 27,284 | 127,375 / 43,340 | 72,426 |
| tax jurisdictions | 72 | 22,462 / 7,090 | 127,030 / 56,907 | 193,034 / 80,110 | 843,662 / 381,777 | 119,383 |
| executive compensation | 80 | 29,942 / 12,914 | 695,722 / 328,009 | 2,148,035 / 1,007,131 | 2,823,866 / 1,323,796 | 78,600 |
| property and equipment | 85 | 11,705 / 5,407 | 47,763 / 18,984 | 397,231 / 186,218 | 1,875,770 / 873,063 | 73,542 |

Across the ten queries, the largest native serialized result was 3,114,935
characters / 1,440,209 approximate tokenizer units at K=50. The largest
individual returned chunk was 5,871 characters; the largest cumulative K=50
chunk text was 206,425 characters.

### Exhaustive 746-concept XBRL audit

All 746 exact concepts were enumerated from the frozen XBRL artifact. Each was
queried once in broad exact-concept form with the default
`include_dimensions=true`; no manual concept sample was used. The audit
covered 7,839 facts.

| measure across concepts | p50 | p90 | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|
| fact count | 4 | 22.5 | 40.75 | 85 | 260 |
| unique context count | 3 | 15 | 32 | 79 | 186 |
| facts with dimensions | 0 | 12.5 | 29.5 | 77.65 | 207 |
| serialized characters | 6,153.5 | 25,104 | 50,230.25 | 114,822.25 | 290,843 |
| approximate tokenizer units | 3,052 | 13,001.5 | 25,851.75 | 59,343.35 | 149,882 |

Largest serialized payloads were:

- `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`: 239 facts,
  186 contexts, 187 dimensional facts, 290,843 characters;
- `us-gaap:StockholdersEquity`: 260 facts, 108 contexts, 207 dimensional
  facts, 289,282 characters;
- `us-gaap:Revenues`: 156 facts, 114 contexts, 126 dimensional facts, 160,725
  characters;
- `us-gaap:DebtInstrumentCarryingAmount`: 127 facts, 116 contexts, 118
  dimensional facts, 149,649 characters; and
- `us-gaap:NetIncomeLoss`: 125 facts, 32 contexts, 23 dimensional facts,
  129,006 characters.

No financial interpretation was applied to these names.

## 3. Fixed retrieval K

### Proposed policy

`PROPOSAL_FOR_HUMAN_DECISION`: adopt one fixed retrieval K, selected only from
the size and context evidence above. Candidate choices are:

- K=5: lowest volume; K×p99 chunk text is about 5,609 approximate tokens and
  K×max is 7,775, before prompts/turns;
- K=10: about 11,218 p99 / 15,550 max chunk-text tokenizer units;
- K=20: about 22,436 p99 / 31,100 max; and
- K=50: about 56,089 p99 / 77,750 max, with native metadata often much larger.

The size-only recommendation is K=5 or K=10. This is not a retrieval-quality
recommendation and uses no historical benchmark result. The human must select
and freeze K.

### Enforcement

`ARCHITECTURE_STATUS = COMPATIBLE_WITH_AGENT_ARCHITECTURE_V0.1` for the
following orchestrator-side gate, subject to recording the event as described
below:

1. omitted `top_k`: insert configured K;
2. explicit `top_k == K`: dispatch normally; and
3. explicit `top_k != K`: emit deterministic recoverable
   `EVT_FIXED_TOP_K_VIOLATION`, do not dispatch ToolRuntime, consume one
   attempted domain-tool call and one model response step, and continue if
   budgets remain.

The explicit conflict is never silently overridden. The request, configured K,
actual value, call identity, and outcome are retained in an append-only
policy-event sidecar ledger. A future run-record amendment should add a
canonical policy-event array; until then its sidecar content hash is recorded
with available noncanonical debug metadata. The four ToolRuntime operations
remain unchanged.

`REQUIRED_FUTURE_PROMPT_CHANGE`: the future frozen system prompt must say:

> Retrieval depth is fixed at K. Omit `top_k` or use exactly K. Any other
> `top_k` value is rejected; the rejected attempt consumes one tool-call
> budget unit.

The literal selected K must be inserted only after human decision and prompt
refreezing. The current frozen prompt is unchanged.

## 4. Model-visible retrieval rendering

`PROPOSAL_FOR_HUMAN_DECISION`: the smallest useful default projection is an
ordered array containing:

```text
rank, chunk_id, accession, locator, company, form_type, filing_date,
period_of_report, section_path, block_type, text
```

`rank` is the final returned rank. `chunk_id`, `accession`, and `locator` are
copied exactly. `text` is copied exactly; it is never rewritten. The filing
and section metadata helps the model distinguish sources without exposing
internal scorer details.

The default model projection should omit `reranker_score`, `bm25_rank`, and
`embedding_rank`. They remain in native output and audit traces. A raw
retrieval score is a ranking signal, not evidence confidence; exposing it can
make a model overinterpret retrieval order as reliability. The component ranks
are similarly useful for audit diagnosis but not for source reasoning.

Native `table_metadata` should not be passed wholesale: the audit shows that
embedded table/XBRL metadata can multiply payload size. The default projection
may retain only a separately specified compact table descriptor if the human
freezes one; it must not rewrite table source text or fabricate facts. Exact
numeric work should use `xbrl.query_facts`.

`HUMAN_DECISION_STATUS = UNRESOLVED`: compact table rendering must retain
enough authoritative table-header, column-label, period, and unit/scale
information for the model to interpret columns correctly. Dropping all native
table metadata is not assumed safe. No rendering projection or compact table
descriptor is finalized or implemented in this preflight.

`ARCHITECTURE_STATUS = COMPATIBLE_WITH_AGENT_ARCHITECTURE_V0.1`: this is a
deterministic rendering of an existing tool result, not a new action. The
projection contract and any compact table descriptor are behavior-affecting
settings and require a DEV revision when changed.

## 5. Model-visible XBRL and calculator rendering

`PROPOSAL_FOR_HUMAN_DECISION`: XBRL facts should be rendered in stable
fact-identity order with the exact fields needed for reasoning:

```text
fact_locator, stable_fact_id, accession, company, cik, form_type, filing_date,
period_of_report, filing_fiscal_period, concept, normalized_value, raw_value,
context_ref, period_type, instant, period_start, period_end, unit,
unit_measures, unit_numerator, unit_denominator, decimals, scale, sign,
dimensions, chunk_id, source_role, doc_role
```

Absent temporal fields remain absent/null as returned. Numeric lexical identity,
dates, raw units, dimensions, and authoritative optional `chunk_id` are copied
without interpretation. The renderer must not select consolidated,
dimensionless, latest, quarter, YTD, or annual facts; change signs; rescale;
deduplicate; or substitute a later filing.

Calculator rendering contains the original expression, normalized expression,
ordered named inputs, exact original and normalized values, units, periods,
bases, input provenance, caller result metadata, and exact result. Native
calculation traces and XBRL/retrieval trace hashes remain audit-side unless a
hash is specifically needed for reasoning identity.

## 6. Oversized XBRL results

The exhaustive audit shows that broad exact-concept results can reach 290,843
characters / approximately 149,882 tokenizer units. This cannot be assumed to
fit an unresolved provider context.

### Policy A: explicit refinement

Available exact filters can narrow by accession, company, form, filing fiscal
period, duration boundaries, instant, and raw unit. They cannot narrow by
context ID or individual dimension. Therefore explicit refinement is useful
when the model already knows an exact filing/date/unit, but is not sufficient
as a universal hidden narrowing mechanism. No financial heuristic may be
added. `ARCHITECTURE_STATUS = COMPATIBLE_WITH_AGENT_ARCHITECTURE_V0.1` for
model-directed use of the existing filters.

### Policy B: truncation

Arbitrary head/tail truncation is not recommended. It permanently hides facts,
can remove the only relevant context, and falsely makes a complete response
look complete. A deterministic size check may return a structured
`xbrl_result_too_large` error containing counts and the available exact filter
surface, allowing explicit refinement. It must not silently return a partial
fact list. This safe-error/refinement behavior is
`ARCHITECTURE_STATUS = COMPATIBLE_WITH_AGENT_ARCHITECTURE_V0.1`.

### Policy C: continuation/pagination

The frozen API has no limit, cursor, page, or continuation argument. A
defensible continuation design would store the complete immutable response in a
content-addressed run-local result store, order by stable fact identity, use a
page identity of `(result_hash, page_number, page_size)`, and make duplicate or
reordered pages detectable. A model request for the next page would need to
identify the result and page; each request would consume an agent step and a
domain-tool-call budget unit if represented as a tool action. The run record
would need to retain page events and the result-store hash.

That request is a new model-visible continuation primitive, because the four
frozen ToolRuntime operations cannot express it and silently issuing pages from
the orchestrator would hide an action from the model. Therefore:

`ARCHITECTURE_STATUS = REQUIRES_ARCHITECTURE_AMENDMENT` for pagination.

Minimal amendment: explicitly add a versioned continuation operation and update
the four-operation/tool-spec/run-ledger architecture, or explicitly add a
versioned model-visible continuation protocol outside ToolRuntime. Neither is
implemented here. Until that decision, the general oversized-result solution
is `BLOCKED_PENDING_HUMAN_DECISION`; the safe interim behavior is exact
refinement or an observable oversized-result error.

## 7. Advisory context requirement

The context budget must separate system prompt, tool schemas, question,
accumulated model/tool turns, the largest plausible rendered result, final
structured output, and safety headroom. Provider/model tokenization is
unresolved, so these are advisory only.

`PROPOSAL_FOR_HUMAN_DECISION`: under a compact retrieval projection and K=5,
32K provider tokens is a practical lower advisory range for one large result
plus prompt/schema/turn overhead and headroom. K=10 or unusually large
accumulated turns make 64K a safer advisory range. These are not frozen
allocations. Supporting an unrefined p99 broad XBRL response would require on
the order of 60K approximate tokenizer units before the rest of the
conversation, while the measured maximum is about 150K; this is evidence for
refinement/oversize handling, not a request to freeze a 150K context.

Therefore `minimum_practical_context_window` is advisory `32K–64K provider
tokens`, conditional on compact retrieval rendering and explicit XBRL
refinement; it is not provider-specific and is not frozen.

## 8. Structured final output modes

The semantic final object must validate directly against
`agent_output_schema_v0.1.1`, including its discriminated narrative/XBRL
provenance union, exact temporal branch, optional authoritative `chunk_id`,
and legacy-citation/new-provenance mutual exclusion.

Mode A is provider-native constrained structured output with domain tool use.
The final answer is a direct structured model response, validated exactly once;
domain tool use remains the four frozen operations.

`ARCHITECTURE_STATUS = COMPATIBLE_WITH_AGENT_ARCHITECTURE_V0.1` for Mode A,
provided the selected provider supports both domain tool calls and constrained
final output without changing the frozen tool runtime. Provider support must be
probed and frozen later.

Mode B is a model-visible `submit_answer` output primitive carrying the final
JSON. It would access no corpus, reason, repair, or coerce; validate directly
against the output schema; not count toward `max_tool_calls=12`; count as a
model/agent step; and be recorded in `AgentRunRecord`.

Because the architecture exposes exactly four ToolRuntime operations and
prohibits hidden tools, a model-visible submit action is a fifth model-visible
primitive if implemented as an action. It is not silently treated as a normal
domain operation:

`ARCHITECTURE_STATUS = REQUIRES_ARCHITECTURE_AMENDMENT` for Mode B.

Minimal amendment: define and version the submit primitive, its accounting,
schema, provider mapping, and run-record representation. This session does
not choose Mode A versus Mode B.

`HUMAN_DECISION_STATUS = UNRESOLVED`: native constrained output versus a
`submit_answer` fallback remains open pending provider/model compatibility
testing.

## 9. Synthetic provider compatibility probe

Design only; no benchmark questions and no real provider call are used here.
Use one deterministic fake question and fake tool responses containing only
synthetic IDs/values. The probe matrix must exercise:

1. one domain tool call;
2. multiple sequential domain tool calls;
3. a recoverable malformed tool call;
4. a domain tool call followed by a final structured answer;
5. the `oneOf`/discriminated provenance union;
6. nested provenance arrays;
7. instant XBRL provenance;
8. duration XBRL provenance;
9. optional `chunk_id` present and absent;
10. legacy citations and new provenance supplied together, rejected;
11. malformed final schema, rejected with no repair/resubmit;
12. provider-native constrained output;
13. submit-answer fallback only where the provider supports it.

Record request/response shape, tool-call sequencing, schema rejection,
structured-output support, finish reasons, and model-visible history. The
probe must assert same-turn history preservation for any later retry design.
It tests API/runtime compatibility, not research quality.

## 10. Category A — recoverable agent events

Stable recoverable-event IDs and their budget/dispatch semantics are defined
only by `docs/agent/execution_taxonomy_v0.1.md`. This preflight applies those
events to the execution mechanisms described above; it does not redefine them.
In particular, the taxonomy's reserved `EVT_TOOL_RESULT_TOO_LARGE` is not
activated here. Activation requires a later frozen oversized-result policy
that defines a result budget, recovery mechanism, and model-visible behavior.

The current run schema has no canonical policy-event array. Until a reviewed
schema amendment, use an append-only, content-hashed sidecar ledger and link
its hash in captured noncanonical debug metadata; do not pretend a
pre-dispatch rejection was a ToolRuntime dispatch.

## 11. Category B — terminal agent failures

Terminal agent-failure IDs and operational meanings are defined only by
`docs/agent/execution_taxonomy_v0.1.md`. The reporting treatment remains in
Section 14. Infrastructure exhaustion is not a terminal agent failure.

## 12. Category C — valid but incorrect or poorly grounded output

The completed-run status and its separation from answer-quality outcomes are
defined only by `docs/agent/execution_taxonomy_v0.1.md`. Evaluation treatment
is defined by `evaluation/eval_protocol_v0.2.2.md`; this preflight adds no
independent completed-run semantics.

## 13. Category D — infrastructure failure and approved retry policy

The sole normative definitions of infrastructure states, retry/replacement
invariants, and human-approved limits are in
`docs/agent/execution_taxonomy_v0.1.md`. Provider and local infrastructure
failures remain separate from agent quality. Same-turn retry and replacement
are applied exactly by reference to that contract.

Every original and retry attempt is observable in noncanonical/debug telemetry
and a versioned infrastructure-attempt sidecar; the canonical run record retains
only fields its frozen schema can represent until amended.

Run-level infrastructure exhaustion and evaluation-level incompleteness use the
taxonomy-defined `INFRA_RUN_RETRY_EXHAUSTED`, `infrastructure_failed`, and
`EVAL_INCOMPLETE` states. These states must not be reclassified as agent
failure.

The approved retry mechanism remains external to ToolRuntime, which itself has
no retry. `ARCHITECTURE_STATUS = REQUIRES_ARCHITECTURE_AMENDMENT` under the
literal frozen architecture because it currently prohibits orchestration and
ToolRuntime retries. The minimal future amendment is to permit same-turn
infrastructure replay and add attempt accounting without changing the four
model-visible domain operations. Replacement is scheduler-level and introduces
no model-visible action:
`ARCHITECTURE_STATUS = COMPATIBLE_WITH_AGENT_ARCHITECTURE_V0.1`.

## 14. Reportable accounting

For each scheduled replicate, retain exactly one outcome slot: successful
schema-valid run (whether correct or incorrect), terminal agent failure, or a
successful infrastructure replacement. Terminal agent failures remain in the
scheduled set, are never replaced or excluded, receive a failure category, and
contribute to the reported failure rate.

For correctness/coverage metrics requiring a valid final answer, use scheduled
slots resolved as schema-valid completion or terminal agent failure as the
denominator; a terminal agent failure receives zero credit. A successful run
with recoverable events receives ordinary evaluator credit and separately
reported event counts. Valid-but-wrong runs receive whatever score the frozen
evaluator assigns, not automatic execution-failure zeroing. An unresolved
infrastructure slot after replacement exhaustion is missing infrastructure:
exclude it from the scored denominator, report the scheduled count and
incomplete status explicitly, and do not convert it into an agent zero.
The evaluation-level status for that condition is the taxonomy-defined
`EVAL_INCOMPLETE`.

## 15. DEV revision accounting

Revision 0 is the initial candidate configuration selected before any DEV
behavior is observed. It does not consume the revision cap.

After Revision 0, the maximum accepted behavior-affecting DEV revisions is six.
A behavior-affecting revision is any change capable of changing model-visible
context, available actions, decoding, orchestration control flow, or final
answer for at least one otherwise valid run. This includes prompt examples or
wording, tool-use instructions, retrieval K, rendering, context policy,
pagination, provider/model, sampling, budgets, structured-output mode, and
behavior-relevant orchestration.

Track separately:

- total DEV executions;
- proposed revisions;
- accepted behavior revisions;
- rejected revisions; and
- bugfix-exempt revisions.

## 16. Bugfix exemption

A bugfix is exempt from the six accepted behavior revisions only if all four
conditions hold:

1. implementation demonstrably violates an already-frozen specification;
2. a regression test demonstrates the violation;
3. the fix restores the specified behavior only; and
4. intended prompt, policy, and schema semantics do not change.

Discovery source is irrelevant. A DEV bad case that motivates new intended
behavior is a normal behavior-affecting revision, not an exempt bugfix. Every
exempt change is logged.

## 17. Unresolved human decisions

The following remain explicitly unresolved and are not frozen by this
closeout:

- retrieval K;
- XBRL oversized-result strategy;
- pagination/continuation;
- provider-native constrained structured output versus a `submit_answer`
  primitive; and
- model/provider selection.

No rendering change is finalized or implemented. In particular, any future
compact table projection must preserve sufficient authoritative table-header,
column-label, period, and unit/scale metadata for correct interpretation.

## 18. Compatibility matrix

| mechanism | architecture status | note |
|---|---|---|
| fixed retrieval K enforcement | `COMPATIBLE_WITH_AGENT_ARCHITECTURE_V0.1` | orchestrator pre-dispatch gate; no new action |
| pre-dispatch policy violation handling | `COMPATIBLE_WITH_AGENT_ARCHITECTURE_V0.1` with sidecar caveat | canonical policy-event field needs future run-schema amendment |
| compact result rendering | `COMPATIBLE_WITH_AGENT_ARCHITECTURE_V0.1` | projection of existing result |
| safe oversized-result error + explicit refinement | `COMPATIBLE_WITH_AGENT_ARCHITECTURE_V0.1` | no hidden filtering or truncation |
| arbitrary XBRL truncation | not recommended | permanently hides facts |
| pagination/continuation | `REQUIRES_ARCHITECTURE_AMENDMENT` | new model-visible continuation primitive |
| native constrained final output | `COMPATIBLE_WITH_AGENT_ARCHITECTURE_V0.1` | direct final structured response |
| `submit_answer` primitive | `REQUIRES_ARCHITECTURE_AMENDMENT` | fifth model-visible primitive under current reading |
| same-turn infrastructure retry | `REQUIRES_ARCHITECTURE_AMENDMENT` | frozen architecture currently forbids retries |
| replacement-run mechanics | `COMPATIBLE_WITH_AGENT_ARCHITECTURE_V0.1` | external scheduler; only infra failure |

No architecture amendment, frozen tool, ToolRuntime, prompt, evaluator, or
agent implementation was changed in this preflight.

## 19. Required future prompt changes

1. State the selected fixed retrieval K and the omit-or-exactly-K rule.
2. State that a conflicting explicit `top_k` is rejected and consumes one
   tool-call budget unit.
3. State the chosen model-visible retrieval projection and that ranking scores
   are not evidence confidence.
4. State the selected oversized-XBRL behavior after human decision (explicit
   refinement/error or an amended continuation protocol).
5. Add **NUMERIC SIGN DISCIPLINE**:
   - when grounding a numeric fact in structured XBRL evidence, preserve the
     authoritative numeric sign returned by XBRLTool;
   - do not flip sign merely because a nearby rendered table uses parentheses,
     cash-flow presentation conventions, or another display convention;
   - communicate direction or interpretation explicitly in the claim/basis
     instead of silently changing the numeric sign;
   - when only narrative/table evidence supports a fact, preserve the
     source-reported value/sign and state the relevant basis when needed; and
   - never use absolute-value matching as a reasoning shortcut.

The sign discipline is generic source-consistency guidance. It creates no
company-, benchmark-, or concept-specific sign reversal and does not let the
agent create a new acceptable gold answer variant.

The frozen prompt was not modified here.

## 20. Validation and handoff

Non-gold validation performed:

- one accepted completed `top_k=50` response per required generic query (after
  an earlier no-result CPU stall); all prefix checks passed;
- exhaustive 746-concept XBRL query audit over the local frozen artifact;
- JSON artifact generation and syntax validation;
- no complete pytest/integration suite;
- no DEV/TEST gold access; and
- `git diff --check` and final `git status` are to be reported after artifact
  creation.

This preflight stops before commit or tag.
