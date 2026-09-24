# Single-agent v0.1 architecture preregistration

Status: **proposed; compatibility design resolved, freeze pending review**

This document preregisters the design of the eventual `agent_v0.1` single-model baseline. It is a design artifact only. It does not implement or run an agent, authorize DEV execution, choose a model or judge, or authorize a commit or tag.

## 1. Blocking compatibility finding

Frozen `evaluation/agent_output_schema_v0.1.json` cannot faithfully represent structured XBRL provenance. Its sole provenance definition, `citation`, requires `chunk_id`, `accession`, and `locator`, rejects other fields, and is required for a claim with `requires_citation=true` and for a calculation input with `source_type=cited_fact`. XBRLTool exposes 7,839 authoritative facts, of which 7,199 have authoritative chunk linkage and 640 do not. Consequently, using v0.1 for an unlinked fact would either fabricate `chunk_id` or omit required source identity. It also has no fields for `fact_locator`, `concept`, `context_ref`, applicable fact dates, or unit.

The reviewed `evaluation/agent_output_schema_v0.1.1.json` resolves that representation gap without mutating frozen v0.1. It retains the v0.1 `citations` field as a deprecated compatibility representation and adds a preferred `provenance` array on claims and calculation inputs. Each new provenance record is exactly one branch of a closed, discriminated union: NarrativeProvenance or XBRLFactProvenance. For each claim or calculation input, legacy `citations` and new `provenance` are mutually exclusive; supplying both is schema-invalid, including equivalent duplicates. Existing conforming v0.1 payloads remain structurally conforming after changing only `schema_version` to `agent_output_v0.1.1`.

### XBRL mapping in v0.1.1

| XBRLTool fact output | Proposed output field | Rule |
|---|---|---|
| `fact_locator` | `provenance[].fact_locator` | Required exact identity |
| `accession` | `provenance[].accession` | Required exact accession |
| `concept` | `provenance[].concept` | Required exact QName |
| `context_ref` | `provenance[].context_ref` | Required exact context reference |
| duration `period_start`, `period_end` | same names | Both required for a duration; `instant` forbidden |
| instant `instant` | `instant` | Required for an instant; duration dates forbidden |
| raw unit reference | `provenance[].unit` | Required exact unit string for numeric provenance |
| authoritative `chunk_id` | `provenance[].chunk_id` | Optional; present only when returned by XBRLTool |

XBRLFactProvenance requires `provenance_type=xbrl_fact`; NarrativeProvenance requires `provenance_type=chunk`. The XBRL object is not a narrative citation: `fact_locator` is the XBRLTool-constructed `doc_id#fact_id` identity, not a source-text locator, and the closed object forbids `locator`. Exactly one temporal form is required: `instant`, or both `period_start` and `period_end`. This structured XBRL branch is numeric-only: the authoritative fact must have a non-null normalized numeric value and nonempty raw unit, which must be copied exactly. Nonnumeric, nil, and dash facts require narrative support or an insufficient-evidence response. A numeric fact without chunk linkage remains fully representable and must omit `chunk_id`. Claim-level provenance supports directly reported XBRL claims; calculation-input provenance separately retains the inputs of derived results.

`evaluation/eval_protocol_v0.2.1.md` is the frozen minimum extension defining deterministic XBRL identity validity, semantic support, completeness, calculation-input provenance, and a generalized approved-path adapter interface without retroactively changing frozen v0.2. It is frozen with the output schema in Commit A `db3d0f6e8addc3b5165a3e9a72c9d3ce15c1ed71`, tagged `agent_output_schema_v0.1.1` and `eval_protocol_v0.2.1`.

The existing retrieval scorers remain frozen and unchanged. A future, separately versioned agent evaluator should provide a generalized provenance validator over authoritative chunk metadata and the frozen XBRL artifact, then normalize approved chunk/XBRL candidate references into the protocol's AND/OR path interface. Because current gold contracts encode chunk candidates but not general structured fact references, the evaluator must not invent XBRL gold mappings; a future reviewed adapter layer is required. No agent scorer is implemented in this preregistration session.

## 2. Purpose and boundaries

The eventual `agent_v0.1` is one model in one fresh conversation per question. The orchestrator may expose exactly four frozen ToolRuntime operations:

1. `retrieval.search`
2. `xbrl.search_concepts`
3. `xbrl.query_facts`
4. `calculator.calculate`

The agent has no web, live EDGAR, external search, filesystem search, Python or code execution, benchmark helper, hidden tool, second agent, or judge. It receives only the user question, frozen system prompt/policy, frozen tool specifications, and explicit tool outputs from that run. AgentRuntime contains no embedded judge.

## 3. Control loop and fixed budgets

The orchestrator starts a fresh model conversation, supplies the deterministic run ID outside the model context where practical, and assigns sequential call IDs. One agent step is one model response after the initial prompt or a tool result. A response may request at most one tool invocation or submit one final output. Tool dispatch itself is not a separate agent step.

- `max_tool_calls = 12`
- `max_agent_steps = 16`
- call IDs: `tool_call_0001`, `tool_call_0002`, ...
- no ToolRuntime retry, orchestration retry, fallback tool, secondary model, or LLM repair pass
- every dispatch attempt counts, including validation failures, tool errors, zero results, and model-initiated retries
- budgets never vary by question and are never increased during DEV

The orchestrator validates a submitted final object exactly once against the selected frozen output schema. It does not repair, coerce, fill, or resubmit malformed content. A valid submission ends in `success`; otherwise the run ends in the applicable explicit failure state.

## 4. Generic tool-use policy

Narrative and filing-table claims use `retrieval.search` when chunk evidence is needed. The agent may issue general, corpus-relevant queries but receives no benchmark-specific retrieval recipes.

For structured reported facts, `xbrl.search_concepts` may discover observed exact QNames and `xbrl.query_facts` may retrieve exact local facts. The agent must inspect accession, context reference, actual start/end or instant dates, dimensions, and unit. Filing fiscal-period metadata does not establish fact duration. XBRLTool does not choose quarter versus YTD, a preferred dimensional context, accounting basis, or economic meaning.

Every reported final number that is not directly present in evidence and is obtained through arithmetic must use `calculator.calculate`. The agent must select semantically and temporally suitable inputs before calculation. CalculatorTool does not validate units, periods, dimensions, basis, definitions, or input suitability.

The policy contains no company rule, target concept name, question-specific calculation, DEV example, or benchmark recipe.

## 5. Grounding, citation, and calculation policy

The agent may not answer material filing facts from parametric memory. Before a substantive final answer, it must obtain source-backed evidence from the frozen tools. Every material factual claim must be bound to supporting provenance. Narrative claims use exact `chunk_id`, `accession`, and `locator`. Structured numeric claims use exact XBRL fact provenance and may additionally use authoritative chunk linkage when returned. Unsupported material claims are prohibited; unsupported requests receive an explicit insufficient-evidence response rather than invented support.

Provenance identity is copied directly and unchanged from tool output. The agent never fabricates or prettifies a chunk ID, accession, locator, fact locator, concept, context, date, or unit. A provenance record must support its associated claim or calculation input; a record attached to unrelated content is inadequate. No chunk ID may be invented for any of the 640 unlinked facts.

For each derived numeric result, the final structured output exposes the expression, named inputs, exact values, units, periods, bases, source provenance, and CalculatorTool result. No arithmetic-derived audited result may be calculated silently in prose. Directly reported values do not require CalculatorTool merely to repeat them.

## 6. Question isolation and reproducibility

Each question is an independent fresh run with a new conversation. There is no prior question text or answer, accumulated tool output, shared conversation state, semantic cache, or writable model memory. Shared immutable model weights, frozen tool instances/resources, and content-addressed immutable artifacts are allowed. Tool result caching, if later introduced, must be content-addressed, return byte-equivalent frozen outputs, and be frozen in the manifest before use.

Before the first reportable run, the manifest must freeze provider, exact model ID/version or snapshot where available, temperature, `top_p`, all other sampling parameters, seed policy, system-prompt SHA-256, tool-spec SHA-256, ToolRuntime and tool commits, output-schema version/hash, budgets, context construction/truncation, orchestration/runtime versions, and relevant library versions. Provider and model remain unresolved blockers in this session.

The orchestrator supplies deterministic run IDs, for example `DEV01_run1`, `DEV01_run2`, and `DEV01_run3`. The model never supplies or changes a canonical run ID. Timestamps, random UUIDs, request IDs, memory addresses, and temporary paths are excluded from canonical hashes.

## 7. Observable AgentRunRecord

`evaluation/agent_run_schema_v0.1.json` defines an observable record and stores no private chain-of-thought. Its canonical portion contains:

- run and question identity, exact question text and SHA-256;
- agent version and manifest SHA-256;
- prompt, tool specification, and selected output-schema identities;
- provider/model/version and sampling configuration;
- terminal status and counters;
- ToolRuntime ledger SHA-256 plus ordered call IDs and observable call metadata;
- final structured output and hash on success; or structured failure information on failure.

Latency, usage, provider request IDs, and timestamps may be retained only as noncanonical metadata when actually and reproducibly available. They never enter deterministic record hashes. The full ToolRuntime ledger and raw provider artifacts are retained separately by content hash; the run record does not reconstruct unavailable telemetry.

## 8. Terminal states

Success requires one valid structured object matching the selected frozen schema. Failure produces no fabricated answer and uses one of these codes:

- `tool_budget_exhausted`
- `step_budget_exhausted`
- `unrecoverable_tool_error`
- `malformed_final_output`
- `provider_failure`
- `orchestration_failure`

Tool and step budgets are checked before another call or model response. A failed or malformed run is retained and reported, not silently rerun or converted to success.

## 9. System prompt

The complete proposed prompt is `docs/agent/agent_v0.1_system_prompt.txt`. Its byte-finalized SHA-256 is `9093d04ac2fc3e30460a4132049c838f2da7d3c16ad3579d5545fce22e008986` and must be frozen before reportable evaluation. The prompt contains only generic role, source boundary, allowed tool semantics, grounding, calculations, provenance, output, insufficient-evidence, and budget policy.

## 10. Manifest contract

`evaluation/agent_manifest_schema_v0.1.json` is the schema for the future frozen manifest. It deliberately requires nonempty provider/model fields; no valid reportable manifest can be produced while those decisions are unresolved. It pins the Commit A output-schema SHA-256 `8d3cab3d5d4a07e9474ef26173631898e195ea08d5ef4f2dc7a88bb008831657`, evaluation-protocol SHA-256 `d98b63268c78ca3a516de02ab931ea6efa8d2590a402118d33c268d5013074d4`, prompt SHA-256 `9093d04ac2fc3e30460a4132049c838f2da7d3c16ad3579d5545fce22e008986`, `tool_runtime_v0.1`, the tool specification hash, `tool_trace_ledger_v0.1`, budgets, sampling, and runtime/library versions rather than referring only to mutable paths or environment names. The run schema repeats the run-observable identities and retains only observable tool-call summaries and ledger hashes; it stores no chain-of-thought.

## 11. DEV iteration discipline

`evaluation/dev_iteration_log.csv` is initialized with a header only. `sequence_id` is the canonical primary ordering key; `timestamp` is optional noncanonical metadata. Before every DEV-driven change, append a declaration containing the candidate version and predeclared target before running DEV. Do not rewrite it after results are seen and do not create historical entries.

Until `judge_protocol_v0.1` is separately frozen and DEV-only calibrated, `judge_protocol_version` is `none`, `judge_metric_summary` is `not_permitted`, and only deterministic signals may affect acceptance. The hard gates and nonregression rules carried forward unchanged in proposed `eval_protocol_v0.2.1` remain binding. Single-run debugging is labeled `DEBUG/NON-REPORTABLE`. Reportable DEV and each authorized locked-TEST checkpoint use three independent runs per question with no best-run selection.

## 12. Freeze order and versioning

Review and freeze the compatible output schema and corresponding evaluation protocol/scorer design first. Then freeze provider/model and sampling, system prompt, manifest, implementation, and reportable DEV process before the authorized `agent_v0.1` locked-TEST checkpoint. No locked TEST is accessed in architecture work.

`agent_v0.1` is reserved for the eventual frozen implementation, not these documents. If these design artifacts are frozen, use `agent_architecture_v0.1` or an equivalent repository convention. Any later change to the prompt, tool policy, budgets, output schema, or observable trace contract requires an explicit new version.

## 13. Frozen identities and unresolved decisions

Pinned inputs:

- retrieval stack `963b089e17983eec954c30970e408c7efc53a9f8`
- Week 2 scaffold / DEV / eval protocol / output schema commit `bd26a38e7873a1d9c6c7a09cb97872925a51550a`
- RetrievalTool `cce61f3fa6b2e4f1fca548c0c931330d9de5a96c`
- XBRLTool `d3bceec1db9d608bd702a5cf3b5329f9710697ea`
- CalculatorTool `72108f24b03b3d6114f04a29366178cde9de97d9`
- ToolRuntime `9aff4d5c31ec9ac4c1c52434d67da99da8ec696c`
- tool-spec SHA-256 `879a710485ac42b6dc0793b0556ce811d4efb151b52a7ae69f90334d489db70d`

Blocking decisions before any reportable agent run:

1. approve/freeze v0.1.1 structured-XBRL provenance and v0.2.1 evaluation semantics, then implement and freeze a separately versioned agent evaluator in a later authorized session;
2. select and freeze provider, exact model/version, sampling parameters, seed behavior, token limits, and provider API/library version;
3. define exact context-window construction and deterministic truncation after model selection;
4. select and freeze orchestrator/runtime and relevant library versions;
5. implement and validate the agent in a later implementation session; and
6. separately freeze and calibrate `judge_protocol_v0.1` before using any judge-derived DEV signal.

Frozen output-schema SHA-256: `8d3cab3d5d4a07e9474ef26173631898e195ea08d5ef4f2dc7a88bb008831657`. Frozen eval-protocol SHA-256: `d98b63268c78ca3a516de02ab931ea6efa8d2590a402118d33c268d5013074d4`. Frozen prompt SHA-256: `9093d04ac2fc3e30460a4132049c838f2da7d3c16ad3579d5545fce22e008986`.
