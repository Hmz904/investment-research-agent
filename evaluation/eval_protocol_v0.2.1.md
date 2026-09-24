# End-to-end agent evaluation protocol v0.2.1

Status: **proposed structured-provenance extension; no locked-test agent run has occurred**

This protocol evaluates end-to-end ThesisAgent outputs. It does not evaluate
retrieval rankings and does not replace `eval_protocol_v0.1`. No overall
agent score or primary metric is defined. This version changes only the
structured-provenance contract needed by `agent_output_v0.1.1`; all other v0.2
evaluation policies and scoring semantics remain unchanged.

## 1. Scope and chronology

The evaluation unit is one agent output for one authoritative benchmark
question. The agent version, system prompt, tool contract, retrieval backend,
control policy, output schema, runtime configuration, and any judge prompt
must be frozen before a locked-test run.

The Week 1 retrieval stack is closed at `retrieval_stack_v0.1`. The default
Week 2 backend remains the precommitted frozen BM25-top50 union
embedding-top50 candidate pool followed by `reranker_v0.1`. Agent-generated
queries and future tool-layer filters do not alter or become part of the
historical retrieval benchmark.

### DEV and locked TEST

DEV:

- is `benchmark/dev/v0.1`;
- may be run repeatedly;
- may guide prompt iteration, retrieval-tool interface iteration, agent
  control-flow iteration, and tool-use policy; and
- produces development results, not test results.

Locked TEST:

- is the existing 16-question `bench_v0.1.1` release from the Week 2
  precommit boundary forward;
- may be run only after an agent version is frozen;
- cannot be used to mutate the version that produced the result;
- requires a new, separately versioned agent for any response to findings;
  and
- forbids question-specific production logic.

The 16 questions were historically used during Week 1 retrieval development
and evaluation. The project must report that chronology honestly and must not
claim that the test set was untouched throughout the whole project. The
locked-test boundary begins at the Week 2 precommit.

### Locked-TEST access policy

Exactly three agent-level locked-TEST checkpoints are preregistered:

1. frozen single-agent baseline: `agent_v0.1`;
2. frozen multi-agent baseline: `multi_agent_v0.1`; and
3. final frozen release candidate: `final_agent_v1.0`, or an explicitly
   documented equivalent final-release tag if repository naming later
   requires it.

No other locked-TEST access is permitted merely for prompt, tool, retrieval,
control-flow, or policy tuning. A validity rerun caused by a documented
infrastructure failure is not automatically authorized: it must preserve the
same frozen checkpoint and be recorded with the failure and rerun reason.

Every execution that exposes locked-TEST questions, outputs, gold, or scores
to an agent-evaluation workflow must append one immutable record to
`evaluation/test_access_log.csv`. The record must contain:

- timestamp;
- checkpoint/version;
- commit SHA;
- tag;
- agent provider and exact model/version;
- agent prompt/template SHA-256;
- tool-stack and tool-policy versions;
- judge protocol version, or `none` when no judge is used;
- all run IDs;
- reason for access; and
- hashes of raw outputs, score reports, judge artifacts, and manifests.

The access log starts with a header only; no fake historical agent entry is
added. Historical Week 1 retrieval evaluations of these 16 questions remain
part of the disclosed chronology, but predate the agent-level locked-test
boundary and are not backfilled as agent checkpoint executions.

## 2. Required inputs and pre-evaluation checks

The evaluator consumes:

1. authoritative questions and benchmark annotations for the selected split;
2. the frozen 14-document corpus and chunk metadata;
3. one output per `q_id` conforming to
   `evaluation/agent_output_schema_v0.1.1.json`;
4. the frozen agent/run manifest and, when available, operational telemetry;
5. the frozen judge specification and prompt if semantic judging is needed.

Before scoring, deterministically verify:

- the expected `q_id` set is exact and unique;
- every output is valid against the output schema;
- every `answer_claim_ids` reference resolves;
- every claim and calculation ID is unique within the output;
- every calculation reference resolves without cycles;
- every narrative-provenance `chunk_id` exists in the frozen corpus and its
  accession and locator match authoritative chunk metadata exactly;
- every XBRL `fact_locator` exists in the frozen XBRL artifact and its
  accession, concept, context reference, unit, temporal fields, and any
  supplied authoritative chunk linkage match exactly;
- run, corpus, benchmark, schema, and agent-version fingerprints match their
  frozen manifests; and
- outputs and evaluator inputs have not been modified after the run.

A malformed output is reported as an invalid output and receives no repaired
credit. The evaluator and judge must not infer missing IDs, provenance,
periods, units, or calculation inputs.

## 3. Output and serialization contract

The output schema requires an explicit `answer`, separately inspectable
claims, claim-bound provenance, and calculations with visible operands. For a
numeric claim, `numeric_value` makes value, unit, period, basis, and displayed
form independently auditable.

Canonical serialization is UTF-8 JSON with lexicographically sorted object
keys, compact separators, a terminal newline, and the array ordering declared
by the schema. NaN and infinities are forbidden. Evaluations retain the exact
output SHA-256.

The final answer text is not a substitute for structured claims. Conversely,
structured claims do not excuse a final answer that omits or contradicts its
material conclusion. A deterministic consistency check flags an answer when
the cited `answer_claim_ids` do not jointly express the final answer; semantic
ambiguity in that relationship may be sent to the frozen judge.

## 4. General aggregation rules

- Report per-question results and macro aggregates; retain integer
  numerators and denominators.
- A question with no applicable items is excluded from that metric's
  denominator, not scored as zero.
- Importance weights are fixed at `core=3.0`, `supporting=1.5`, and
  `optional=0.5`.
- Do not average unrelated dimensions into a composite.
- Do not select a headline metric after observing DEV or TEST results.
- Deterministic outcomes take precedence over judge output in the domains
  reserved to deterministic scoring.

### DEV change declaration and acceptance rule

Before running DEV for any proposed agent change, record the proposed version
and one or more intended development targets. Allowed target descriptions
include citation formatting, numeric calculation correctness, evidence
completeness, tool selection, tool-call efficiency, or a specifically
documented operational failure. The declaration must be timestamped and
retained with the DEV run manifest; it cannot be rewritten after results are
observed.

Every accepted revision must pass these hard gates:

- output-schema validity = 100%;
- provenance identity validity = 100%;
- `source_scope_violation` = 0;
- hallucinated or nonexistent provenance identity = 0; and
- deterministic calculation parsing succeeds for every submitted
  calculation.

Before `judge_protocol_v0.1` exists and is frozen:

- only deterministic/rule-based DEV results may be used for acceptance;
- numeric value correctness must not regress;
- complete numeric correctness must not regress;
- strict grounded numeric correctness must not regress; and
- semantic evidence quality must not be claimed as improved using an
  unfrozen judge or informal model review.

An accepted revision must pass every hard gate, avoid regression in all
deterministic protected metrics above, and improve its predeclared target or
fix its predeclared operational failure. A change that merely improves an
undeclared metric after inspection is not accepted on that basis. This rule
does not define or imply an overall DEV score.

After `judge_protocol_v0.1` is frozen, judge-derived semantic metrics may
participate only as specified by that frozen judge protocol and the
predeclared change target.

## 5. Numeric answer correctness

### 5.1 Frozen answer semantics

Reuse the benchmark conventions:

- distinct answer groups within a question are AND requirements;
- verified variants within one answer group are OR alternatives;
- only an answer variant with the correct economic concept, period, unit,
  accounting basis, and sign can match;
- derived answers require every finalized input recursively;
- quarter and YTD values are distinct;
- GAAP and non-GAAP values are distinct;
- percentages and percentage-point changes are distinct; and
- directly reported and derived variants may both be accepted only where the
  gold explicitly defines them as variants of the same group.
- When a question declares a `question_consistency_group` and
  `variant_family` metadata, every matched answer group in that consistency
  group must use one common family. A response mixing families across answer
  groups is invalid even if each individual value, unit, period, basis, and
  sign matches an allowed variant. For DEV02, the permitted families are
  `V1_GAAP_MINUS_NON_GAAP` and `V2_COMPANY_REPORTED_ADJUSTMENT_COLUMN`.

Values are compared at each variant's annotated lexical/display precision.
Deterministic, dimensionally valid conversions such as USD billions to USD
millions are allowed. A wide tolerance must not merge different methods,
periods, or bases. Expenditure magnitudes use the benchmark sign convention
unless the question explicitly requests cash-flow statement signs.

### 5.2 Numeric scoring

For each answer group, match the structured numeric claim against all
approved variants. Report:

1. **Value correctness** — correctly matched answer groups divided by all
   required answer groups. A match includes value, unit, period, basis, sign,
   and display precision.
2. **Required-input correctness** — correct required derived-input facts
   divided by all required input facts. Inputs are scored individually before
   the final calculation.
3. **Complete numeric answer correctness** — fraction of numeric questions
   for which every answer group is correct and every required input is
   correct. A direct-answer question with no required derived inputs depends
   only on all answer groups.

Also retain per-question counts and variant IDs matched. Numeric answer
correctness does not, by itself, confer citation or grounded credit.

This family-consistency rule is deterministic metadata validation. No LLM
judge is needed to decide whether opposite-sign DEV02 variants are compatible.

## 6. Evidence and thesis content coverage

Evidence annotations follow the existing provenance semantics:

- parts within an evidence item are AND requirements;
- semantically equivalent approved variants within one part are OR
  alternatives;
- an item is strict-complete only when all required parts are expressed; and
- stance and temporal role are part of the target meaning when annotated.

For each evidence item, `item_coverage = matched_required_parts /
required_parts`. Report:

1. **Item coverage** — macro mean item coverage.
2. **All-parts rate** — items with coverage 1.0 divided by all items.
3. **Weighted partial coverage** — sum of `importance_weight *
   item_coverage` divided by total importance weight.
4. **Weighted strict coverage** — sum of importance weights for all-parts
   items divided by total importance weight.
5. **Core coverage** — strict all-parts completion among core items.

Coverage evaluates substantive content, not whether a nearby citation exists.
Citation dimensions are scored separately.

## 7. Citation and provenance correctness

Every provenance record is associated with exactly one structured claim or
calculation input. Claim-support provenance and calculation-input provenance
remain separately attributable and are never pooled merely because they occur
in the same output. Score four different concepts.

### 7.1 Provenance identity validity

Narrative provenance is valid only if:

- `chunk_id` exists in the frozen corpus;
- accession exactly matches that chunk; and
- locator exactly matches the authoritative chunk metadata.

XBRL fact provenance is valid only if:

- `fact_locator` exists in the frozen XBRL artifact;
- accession, concept, context reference, and unit match the authoritative
  fact exactly;
- the submitted instant or duration fields match the authoritative fact
  context exactly; and
- optional `chunk_id`, when supplied, matches the fact's authoritative chunk
  linkage.

An authoritative XBRL fact without chunk linkage remains valid structured
provenance when its fact identity fields are correct. Absence of `chunk_id`
does not invalidate it and must not be penalized. A fabricated or mismatched
optional linkage is invalid.

Legacy v0.1 `citations` are normalized by the evaluator as narrative
provenance for backward-compatible payloads; this adapter adds the
`provenance_type=chunk` discriminator without repairing any identity field.
For each claim and calculation input, `citations` and `provenance` are
mutually exclusive. Supplying both is schema-invalid even when they encode the
same chunk, so contradictory dual sources of truth cannot enter evaluation.

`XBRLFactProvenance` in `agent_output_v0.1.1` represents numeric XBRL facts
only. The authoritative XBRLTool result must have a non-null normalized numeric
value and a nonempty raw unit reference, and the submitted `unit` must match
that reference exactly. Nonnumeric, nil, and dash XBRL facts are not valid
structured provenance for `agent_v0.1`; a claim needing them must use valid
narrative provenance or be reported as insufficiently supported. The evaluator
must never infer or invent a unit.

Report valid provenance records divided by all submitted provenance records,
plus invalid counts by failure type. Source and fact identity are
deterministic and cannot be overridden by a judge.

### 7.2 Provenance support / precision

Identity validity and semantic support are distinct. Valid narrative
provenance supports its associated claim only when the cited chunk, alone or
as an explicitly combined provenance set, entails the material factual
content at the stated period and basis. A citation to the correct document but
an unrelated chunk is valid for identity but unsupported for entailment.

Valid XBRL provenance supports a claim only when the authoritative structured
fact supports the quantitative or directly reported factual content asserted,
including value, concept, period, unit, and accounting basis where applicable.
One numeric fact is not automatically sufficient support for a broader
narrative, comparison, explanation, or causal interpretation. Interpretive
claims must be supported through their material factual premises and, where
needed, narrative evidence.

Report supported claim-provenance sets divided by valid claim-provenance sets.

### 7.3 Citation/provenance completeness / recall

First enumerate material factual claims requiring support. Report the number
with sufficient valid, supporting provenance divided by all such claims.
Apply the obligation by claim type:

- a material narrative factual claim requires sufficient narrative provenance
  unless its complete factual content is directly represented by structured
  fact provenance;
- a direct structured numeric claim may be fully supported by valid XBRL fact
  provenance without narrative chunk linkage; and
- a derived numeric claim requires auditable calculation inputs and valid
  provenance for every required input.

Interpretive conclusions require support for their material factual premises;
purely rhetorical transitions and clearly labeled arithmetic restatements do
not create additional provenance obligations. Do not penalize an unlinked
XBRL fact solely for lacking `chunk_id`.

### 7.4 Provenance correctness

Where the benchmark defines approved provenance, a claim has correct
provenance only if its records satisfy an approved path:

- candidate chunks within one direct part are OR alternatives;
- candidate XBRL fact references within one direct part are OR alternatives;
- a part may require a declared combination of chunk and XBRL fact references;
- all parts of a multi-part evidence item are required;
- a derived numeric answer requires the provenance of all required inputs;
  and
- an arbitrary relevant chunk or fact from the same accession is not a
  substitute.

Report provenance-correct material claims divided by material claims with a
benchmark-defined provenance path. This metric is separate from general
provenance support because a source can semantically support a claim without
belonging to the benchmark's approved path.

The agent-evaluation adapter consumes a generalized approved-path interface:

```text
part := OR(candidate_reference | combination)
combination := AND(candidate_reference, ...)
candidate_reference := chunk_ref(chunk_id) | xbrl_fact_ref(fact_locator)
claim_path := AND(part, ...)
```

Current DEV and locked-TEST gold contracts encode approved chunk candidate
references and derived-input relationships, but do not provide a general
structured XBRL fact-reference variant. This protocol does not mutate frozen
gold or retrofit benchmark-specific mappings. Before structured-fact approved
matching is scored, a separately versioned evaluation adapter must translate
future reviewed gold into this interface while preserving the existing
chunk-only AND/OR semantics. Until then, XBRL identity validity and semantic
support can be evaluated, but no benchmark approved-path credit may be
invented for absent XBRL mappings.

## 8. Grounded answer strictness

Strict grounded success always requires both substantive correctness and
sufficient valid provenance.

- **Numeric strict grounded correctness** requires complete numeric answer
  correctness, every calculation-audit component required by the question,
  valid and supporting provenance for all required inputs and direct answers,
  and approved provenance where defined.
- **Evidence strict grounded correctness** requires all core evidence items,
  every required update role when applicable, valid/supporting provenance for
  the material answer claims, provenance completeness, and approved provenance
  where defined.

Report numeric and evidence strict-grounded rates separately. Do not combine
them into one score.

An unsupported correct answer receives substantive correctness but no strict
grounded credit. A well-cited incorrect answer receives citation metrics but
no answer-correctness or strict-grounded credit.

## 9. Source-scope violations and unsupported claims

A `source_scope_violation` occurs when the answer relies on, cites, or
attributes a material fact to a source outside the contract, including:

- an earnings-call transcript;
- an unfiled investor-relations deck;
- news, Bloomberg, external web content, or third-party research;
- a document outside the frozen corpus/source contract; or
- an external fact unavailable from allowed evidence that is asserted as
  support for the answer.

An unsupported claim is different: it is a material claim for which the
submitted allowed-source provenance is absent or does not support the claim.
Unsupported claims do not become source-scope violations unless the output
actually relies on or attributes them to an excluded source. A statement may
be both when both conditions hold.

Report violation and unsupported-claim counts, affected-question counts, and
rates using material factual claims as the claim-level denominator.

## 10. Hallucinated and invalid provenance

Classify citation failures deterministically where possible:

- `nonexistent_chunk_id` — no such frozen chunk;
- `wrong_accession` — chunk exists but citation accession differs;
- `metadata_inconsistent` — locator or document metadata materially conflicts
  with the chunk;
- `outside_source_contract` — the cited source is not allowed; and
- `unrelated_evidence` — identity is valid but the text does not support the
  associated claim.

Classify XBRL provenance failures deterministically where possible:

- `nonexistent_fact_locator` — no such fact exists in the frozen XBRL artifact;
- `wrong_fact_identity` — accession, concept, context reference, unit, or
  temporal fields differ from the authoritative fact;
- `wrong_chunk_linkage` — optional `chunk_id` is not the fact's authoritative
  linkage;
- `outside_source_contract` — the fact's source is not allowed; and
- `unsupported_fact_use` — identity is valid but the fact does not support the
  associated claim or calculation input.

The first four narrative failures and first four XBRL failures are invalid
provenance. `unrelated_evidence` and `unsupported_fact_use` are valid for
identity but fail semantic support. Report invalid citation/provenance
count/rate and hallucinated identity count/rate; hallucinated identities are
the subset with nonexistent IDs or falsely paired accessions. No evaluator or
judge may repair them.

## 11. Calculation audit

For every derived numeric answer, score these components separately:

1. **Formula correctness** — the expression represents the required economic
   calculation and uses all required inputs with the correct operators.
2. **Input-value correctness** — each supplied input value, unit, period, and
   basis matches an approved input fact.
3. **Input-provenance correctness** — every input has valid, supporting,
   provenance-correct NarrativeProvenance, XBRLFactProvenance, or a sufficient
   combination as applicable.
4. **Arithmetic correctness** — evaluating the submitted expression with the
   submitted inputs yields the submitted unrounded result, subject only to
   declared display rounding.
5. **Final-value correctness** — the result matches an approved answer variant
   at its annotated precision.

The evaluator parses the structured operands and recomputes arithmetic. The
judge cannot override arithmetic or numeric identity. Algebraically different
formulas are accepted only when deterministic normalization or fixed test
vectors establish equivalence to the approved formula. Otherwise the formula
is referred to documented human adjudication before results are finalized;
an LLM judge does not invent an equivalence.

A correct final number with a wrong formula, wrong input identity, wrong
period or unit, or unsupported input retains final-value credit only. It does
not receive the failed component or strict-grounded credit.

## 12. Update questions

Update questions preserve three roles:

- `prior_period` — accurate baseline;
- `current` — accurate new-period evidence; and
- `change` — an explicit comparison explaining what was reinforced, revised,
  or overturned.

Report coverage for each role separately. Strict update completion requires
at least one matched core item in every role required by that question and
all question-specific core update items. Merely answering the latest period
does not satisfy an update question.

## 13. Causal overreach

`causal_overreach` is a factual-discipline failure in which the answer turns
co-movement, management commentary, timing, aggregate consistency, or an
unallocated accounting change into a causal statement not established by the
allowed evidence.

Examples include claiming that a buyer's aggregate capex caused a supplier's
revenue, that one product caused a broad platform's revenue change without a
product breakout, or that debt proceeds funded a particular distribution
when the filing does not trace use of proceeds.

Cautious wording such as “is consistent with,” “coincided with,” “may have
contributed,” or “the filing does not establish causality” is not a failure
when it accurately reflects the evidence. Hedging does not rescue a claim
whose substantive causal attribution remains unsupported.

Report count and rate by material interpretive claims and affected questions.

## 14. Deterministic versus LLM-judge boundary

Use deterministic rules wherever possible.

| Deterministic only | Frozen LLM judge permitted |
|---|---|
| Schema validity, ID resolution, corpus/chunk/fact existence, accession and source identity, XBRL concept/context/unit/temporal identity | Whether free-text wording expresses a required semantic evidence part |
| Numeric values, units, periods, bases, signs, precision, answer groups, and variants | Whether a valid cited passage semantically entails its associated claim |
| Formula operands, input facts, arithmetic, and final numeric comparison | Whether an uncatalogued factual statement is material and requires citation |
| Approved chunk/XBRL provenance-path membership and AND/OR logic | Whether wording materially overstates causality |
| Source-contract membership and mechanical counts/aggregation | Whether final answer prose materially contradicts its structured claims |

The judge may not override numeric arithmetic, invent provenance, alter gold,
decide source or fact identity, repair malformed provenance, add missing evidence, or
change deterministic failures.

## 15. Future `judge_protocol_v0.1` boundary

No judge is selected or authorized by this protocol. Semantic judging requires
a separately frozen future artifact, `judge_protocol_v0.1`. Before the first
judge-derived DEV result is used for agent iteration, that artifact must
freeze:

- provider, model family, exact model ID, and immutable version/snapshot where
  available;
- `temperature = 0` and all other sampling parameters;
- full prompt text and prompt SHA-256;
- exact judge input and output schemas;
- maximum input/output tokens;
- retry policy and malformed/missing-output policy;
- caching policy; and
- a DEV-only human calibration procedure completed before semantic scores are
  trusted for agent iteration.

Calibration must not inspect, label, tune against, or adjudicate locked-TEST
judgments. A different model family from the production agent is preferred
where practical to reduce same-family self-preference, but this is not a hard
guarantee of unbiased judging.

Judge inputs and outputs must be cached as immutable evaluation artifacts and
recorded with hashes. API calls are not assumed to be byte-deterministic, even
at temperature zero. Changing the judge model, prompt, input/output schema, or
rubric after freeze requires a new judge protocol version; it must not silently
replace results from `judge_protocol_v0.1`.

### 15.1 Exact judge input

One request evaluates one question and uses this logical JSON structure:

```json
{
  "judge_spec_version": "agent_judge_v0.1",
  "question": {"q_id": "...", "text": "...", "q_type": "..."},
  "gold_items": [
    {
      "item_id": "...",
      "part_id": "...",
      "required_semantics": "...",
      "importance": "core|supporting|optional",
      "stance": "...",
      "temporal_role": "..."
    }
  ],
  "agent_output": {
    "answer": "...",
    "answer_claim_ids": ["..."],
    "claims": [
      {
        "claim_id": "C001",
        "text": "...",
        "claim_type": "factual|comparative|interpretive|limitation",
        "entities": ["..."],
        "material": true,
        "period": "...",
        "requires_citation": true,
        "temporal_role": "prior_period|current|change|cross_company|not_applicable",
        "citations": [
          {"chunk_id": "...", "accession": "...", "locator": "..."}
        ]
      }
    ]
  },
  "citation_texts": [
    {
      "claim_id": "...",
      "chunk_id": "...",
      "accession": "...",
      "locator": "...",
      "text": "exact frozen chunk text"
    }
  ],
  "deterministic_findings": {
    "schema_valid": true,
    "invalid_citations": [
      {"claim_id": "C001", "chunk_id": "...", "reason": "wrong_accession"}
    ],
    "source_scope_findings": [
      {"claim_id": "C001", "present": false, "reason": ""}
    ],
    "numeric_claim_ids_excluded_from_judgment": ["C002"]
  }
}
```

Only schema-valid claims and exact frozen chunk text are supplied. Invalid
citations remain visible as deterministic findings but receive no fabricated
text.

### 15.2 Judge rubric dimensions

The judge returns decisions only for:

1. `semantic_item_match` for each gold evidence part;
2. `citation_support` for each valid claim-citation set;
3. `material_claim_requires_citation` for uncatalogued claims;
4. `causal_overreach` for each material interpretive claim; and
5. `answer_claim_consistency` between final prose and referenced claims.

Each decision is a boolean plus a short evidence-bound rationale. The judge
must use the supplied text only and must abstain when the supplied evidence
is insufficient.

### 15.3 Required judge output

```json
{
  "judge_spec_version": "agent_judge_v0.1",
  "q_id": "...",
  "semantic_item_matches": [
    {"item_id": "...", "part_id": "...", "matched": true, "claim_ids": ["C001"], "rationale": "..."}
  ],
  "citation_support": [
    {"claim_id": "C001", "chunk_ids": ["..."], "supported": true, "rationale": "..."}
  ],
  "materiality": [
    {"claim_id": "C001", "requires_citation": true, "rationale": "..."}
  ],
  "causal_overreach": [
    {"claim_id": "C001", "present": false, "rationale": "..."}
  ],
  "answer_claim_consistency": {"consistent": true, "rationale": "..."},
  "abstentions": [
    {"dimension": "citation_support", "target_id": "C001", "reason": "insufficient supplied text"}
  ]
}
```

Unknown keys are forbidden in the frozen judge-output schema. A malformed,
truncated, or nonconforming judge response is an evaluation error, not a
scored answer and not permission to repair content. The exact machine schema
and prompt shown here are placeholders and must be finalized in the separately
frozen `judge_protocol_v0.1` before first use.

## 16. Required score panel

Report the following with per-question detail and aggregate numerators and
denominators.

### Numeric

- value/answer-group correctness;
- required-input correctness;
- complete numeric answer correctness;
- formula correctness;
- arithmetic correctness; and
- numeric strict grounded correctness.

### Evidence

- item coverage;
- all-parts rate;
- weighted partial coverage;
- weighted strict coverage;
- core coverage; and
- evidence strict grounded correctness.

### Citation

- citation validity;
- citation support/precision;
- citation completeness/recall; and
- benchmark provenance correctness.

### Safety and discipline

- source-scope violation count/rate;
- invalid and hallucinated citation count/rate;
- unsupported material claim count/rate;
- causal-overreach count/rate; and
- update-role coverage where applicable.

### Operational

- total and per-question tool calls;
- retrieval calls;
- unique and total retrieved chunks; and
- latency and token use only when captured reproducibly from a frozen runtime
  with a documented measurement method.

Operational measures are descriptive and are not correctness scores. Missing
latency/token telemetry is reported as unavailable, never reconstructed.

## 17. Reproducibility and change control

Every frozen agent version must have a manifest frozen before evaluation. It
must record:

- provider and exact model ID/version where available;
- complete system prompt and prompt/template SHA-256;
- temperature, `top_p`, and every other configurable sampling setting;
- tool versions and tool-policy version;
- maximum agent steps and tool-call limits;
- context construction and truncation policy;
- runtime and relevant library versions; and
- seed policy when the provider supports reproducible seeds.

For a reportable frozen DEV evaluation, run every DEV question three
independent times. For every authorized locked-TEST checkpoint, run every TEST
question three independent times. Never select the best run. Retain and report:

- every individual run and explicit run ID;
- the mean across runs where meaningful;
- minimum, maximum, or range;
- success/failure counts for discrete metrics; and
- all raw outputs and artifact hashes.

If reproducible seeds are supported, freeze the seed policy before execution.
If exact seeds are unsupported, preserve explicit run IDs and raw outputs.
Single-run DEV executions are allowed for debugging but must be labeled
`DEBUG/NON-REPORTABLE` and must not be presented as frozen evaluation results.

The evaluator must preserve raw outputs, judge inputs/outputs, run manifests,
and report artifact hashes. Deterministic scoring repeated against identical
inputs must be byte-identical. Judge reproducibility is reported separately;
temperature zero does not by itself guarantee byte identity.

Before locked TEST, freeze this protocol, the output schema, deterministic
scorer version, applicable judge protocol, and all manifests. Any later
semantic change requires a new protocol version and cannot be applied silently
to prior results.

## 18. Future retrieval-tool contract notes (not implemented)

The future agent retrieval tool should expose at minimum:

- query;
- chunk ID and chunk text;
- reranker rank;
- accession and document identity;
- company and form type;
- filing, fiscal, and reporting-period metadata;
- section/table metadata where available; and
- source anchor or locator.

Filters may be considered for company, accession/document, form type, and
fiscal/reporting period. Filtering is a new tool-layer operation. It must not
modify, replace, or be reported as the frozen `retrieval_stack_v0.1`
benchmark, and no retrieval tool is implemented by this protocol.
