# Execution taxonomy and infrastructure policy v0.1

Status: **immutable-ready contract; freeze requires a later human commit/tag**

This document is the sole normative source for stable execution-event IDs,
terminal agent-failure IDs, completed-run status, infrastructure-exhaustion
status, evaluation-incomplete status, and the approved infrastructure
retry/replacement constants. Execution-policy and evaluation documents may
reference these definitions and assign policy or scoring treatment, but must
not redefine them.

This contract does not choose retrieval K, result rendering, oversized-result
handling, pagination, model/provider, or structured-output mode.

## 1. Recoverable agent events

Recoverable events are observable agent requests or domain-tool outcomes. They
do not terminate a run while applicable tool-call and agent-step budgets
remain. They are logged and may be exposed to the model. Agent-generated
invalid requests are not infrastructure failures.

| stable ID | operational meaning | activation |
|---|---|---|
| `EVT_FIXED_TOP_K_VIOLATION` | The model explicitly supplies a retrieval `top_k` different from the active frozen fixed K. Pre-dispatch rejects the attempt; ToolRuntime is not called; the attempted domain call and model step are consumed. | Active only if a fixed-K policy is frozen. |
| `EVT_TOOL_ARGUMENT_REJECTED` | Pre-dispatch schema/argument validation rejects invalid model-generated domain-tool parameters. ToolRuntime is not called; the attempted domain call and model step are consumed. | Active. |
| `EVT_TOOL_ZERO_RESULT` | A valid dispatched domain-tool request completes successfully with no result. The dispatched domain call and model step are consumed. | Active. |
| `EVT_TOOL_DOMAIN_ERROR_RECOVERABLE` | ToolRuntime or a domain tool returns a deterministic recoverable error, including a correctable XBRL request. The dispatched domain call and model step are consumed. | Active. |
| `EVT_TOOL_RESULT_TOO_LARGE` | A domain-tool result exceeded the active frozen model-visible result budget and was not exposed in full. | **Reserved; not active for agent_v0.1.** |

`EVT_TOOL_RESULT_TOO_LARGE` must not be emitted unless a later frozen execution
policy defines the applicable result budget, recoverability mechanism, and
model-visible behavior. Reserving the ID does not select or activate any
oversized-result policy.

Recoverable-event frequency is reportable independently of final answer
quality. A run that later completes is not automatically incorrect because a
recoverable event occurred.

## 2. Terminal agent failures

| stable ID | operational meaning |
|---|---|
| `FAIL_TOOL_BUDGET_EXHAUSTED` | The domain-tool-call budget is exhausted before a valid final submission. |
| `FAIL_STEP_BUDGET_EXHAUSTED` | The agent-step budget is exhausted before a valid final submission. |
| `FAIL_FINAL_SCHEMA_INVALID` | The submitted final output fails the frozen output schema. |
| `FAIL_NO_VALID_FINAL_OUTPUT` | The model ends without the required valid final output. |
| `FAIL_AGENT_ORCHESTRATION_UNRECOVERABLE` | An unrecoverable agent-controlled orchestration state prevents completion. |

These states terminate the run. They are agent-quality failures, are never
infrastructure replacements, and retain their scheduled replicate slot.

## 3. Completed-run status

`RUN_COMPLETED` means the run produced a final object valid under the frozen
output schema. It says nothing about answer quality. A `RUN_COMPLETED` answer
may be factually wrong, poorly grounded, incomplete, have an invalid citation,
use a wrong period/context/unit, or overstate causality. Those are evaluator
outcomes, not execution failures, and do not trigger retry or replacement.

## 4. Infrastructure and evaluation-level statuses

`INFRA_RUN_RETRY_EXHAUSTED` is the run-level infrastructure identifier assigned
when an applicable per-request or per-run infrastructure retry limit is
exhausted. Its runtime status is `infrastructure_failed`. It is neither a
recoverable agent event nor an agent-quality failure.

`EVAL_INCOMPLETE` is an evaluation-level status used only when the required
reportable replicate set cannot be completed after the frozen infrastructure
retry and replacement policy is exhausted. It is not an agent failure, tool
event, terminal run status, or completed-run status. The missing scheduled
replicate is reported explicitly and no agent-quality score is imputed.

## 5. Human-approved infrastructure constants

These names and values are canonical:

```text
MAX_PROVIDER_ATTEMPTS_PER_REQUEST = 3
MAX_TOTAL_INFRASTRUCTURE_RETRIES_PER_RUN = 8
MAX_REPLACEMENT_RUNS_PER_SCHEDULED_REPLICATE = 1
```

`MAX_PROVIDER_ATTEMPTS_PER_REQUEST` includes the original request, so one
logical provider request permits at most two retries.

`MAX_TOTAL_INFRASTRUCTURE_RETRIES_PER_RUN` counts retries only; original
requests are excluded.

`MAX_REPLACEMENT_RUNS_PER_SCHEDULED_REPLICATE` permits one mechanically
triggered replacement run with a new `run_id` after infrastructure exhaustion.

## 6. Retry and replacement invariants

- Retry only the same logical request at the same logical model/tool turn.
- Preserve all prior successful conversation, tool-ledger, prompt, tool-spec,
  model/configuration, and structured-output state.
- Never restart the entire run because a later turn has an infrastructure
  failure.
- Retryable provider classes are 429/rate limit, provider 5xx, transport or
  connection interruption, and documented transient provider failures.
- A local infrastructure failure is retryable only when the same logical step
  can be repeated without changing prior model-visible state and required
  immutable artifacts can be revalidated.
- Infrastructure replacement depends only on `infrastructure_failed` caused by
  exhausted infrastructure handling.
- Bad answers, schema failures, tool misuse, agent budget exhaustion,
  hallucination, and recoverable agent events never trigger replacement.
- After replacement exhaustion, the required evaluation may become
  `EVAL_INCOMPLETE`.

Every original attempt, retry, exhaustion state, and replacement relationship
must remain observable in the applicable run/debug metadata without changing
model-visible history between retries.
