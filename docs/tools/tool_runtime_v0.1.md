# ToolRuntime / ToolRegistry v0.1

## Scope

ToolRuntime v0.1 is a deterministic integration layer over the three frozen
Week 2 tools. It exposes their public operations, validates explicit calls,
dispatches once, and wraps the native response and trace in one common
envelope. It does not select a tool, rewrite arguments, interpret results,
retry, fall back, rank, truncate, or perform agent reasoning.

The frozen dependencies are:

- `retrieval_stack_v0.1` at
  `963b089e17983eec954c30970e408c7efc53a9f8`;
- `retrieval_tool_v0.1` at
  `cce61f3fa6b2e4f1fca548c0c931330d9de5a96c`;
- `xbrl_tool_v0.1` at
  `d3bceec1db9d608bd702a5cf3b5329f9710697ea`; and
- `calculator_tool_v0.1` at
  `72108f24b03b3d6114f04a29366178cde9de97d9`.

No frozen tool implementation is duplicated or modified by this layer.

## Registry API

Production construction initializes each tool exactly once and retains those
instances for the registry lifetime:

```python
from src.tools import ToolRegistry

registry = ToolRegistry.from_frozen_tools()
specs = registry.list_tools()
retrieval_spec = registry.get_tool_spec("retrieval.search")
result = registry.invoke(call)
```

Tests and lightweight integrations inject already-constructed compatible
instances directly:

```python
registry = ToolRegistry(
    retrieval_tool=retrieval,
    xbrl_tool=xbrl,
    calculator_tool=calculator,
)
```

There is no global mutable tool singleton. `invoke()` never reconstructs a
tool, index, model, or fact table. Production construction verifies the three
imported module versions and factory result types against the versions pinned
by ToolRuntime v0.1. Production responses are also required to declare the
same frozen `tool_version`; a mismatch becomes a deterministic error instead
of being labeled as the expected version.

## Exposed operations

Exactly four qualified operations are exposed, in lexicographic registry
order:

1. `calculator.calculate` -> `CalculatorTool.calculate()`
2. `retrieval.search` -> `RetrievalTool.search()`
3. `xbrl.query_facts` -> `XBRLTool.query_facts()`
4. `xbrl.search_concepts` -> `XBRLTool.search_concepts()`

Internal and helper methods are not registered.

## Machine-readable specifications

Each `ToolSpec` contains:

- logical `tool_name` and frozen `tool_version`;
- `operation` and a factual neutral `description`;
- an object-shaped, JSON-Schema-like `argument_schema`;
- ordered `required_arguments` and `optional_arguments`; and
- structured `argument_constraints`.

Every argument schema sets `additionalProperties=false` at the call boundary.
It records only the frozen public defaults. After validation, the runtime
mechanically resolves omitted declared defaults into `effective_arguments`
and dispatches exactly that mapping. It does not resolve explicit null to a
default or invent undeclared values.

`retrieval.search` and `xbrl.search_concepts` accept a non-whitespace `query`
and optional integer `top_k` from 1 through 50 (default 10).

`xbrl.query_facts` requires exact non-empty `concept` and advertises only the
frozen exact filters: `accession`, `company`, `form_type`,
`filing_fiscal_period`, `period_start`, `period_end`, `instant`, `unit`, and
`include_dimensions`. Dates must be canonical ISO dates. `instant` cannot be
combined with either duration boundary. `include_dimensions` defaults to
true. No limit, context preference, fiscal-year, label, or taxonomy parameter
is exposed.

`calculator.calculate` requires `expression` and `inputs` and permits optional
`result_metadata`. Input records map mechanically to frozen
`CalculationInput(value, unit, basis, period, provenance)` fields. The schema
records the expression/resource limits, conservative variable-name syntax,
plain exact-decimal value syntax, maximum input count, exact JSON metadata
types, and variable-binding rules. It does not add financial semantics.

## Canonical specification and hash

`canonical_tool_specs_json()` serializes the complete specification payload as
UTF-8-compatible JSON with:

- tool/operation ordering by `(tool_name, operation)`;
- lexicographically sorted object keys;
- compact `,` and `:` separators;
- non-ASCII characters retained;
- non-finite numbers rejected; and
- exactly one terminal newline.

The payload contains no timestamp or path. The SHA-256 includes the terminal
newline. The v0.1 value is:

```text
879a710485ac42b6dc0793b0556ce811d4efb151b52a7ae69f90334d489db70d
```

This is exposed as `TOOL_SPEC_SHA256` and
`registry.tool_spec_sha256`. Any description, exposed operation, argument
name, default, schema, or constraint change changes the payload and requires a
future tool-contract version.

## Request contract

```python
ToolCallRequest(
    call_id: str,
    tool_name: str,
    operation: str,
    arguments: Mapping[str, Any],
)
```

`call_id` is caller-supplied and must match
`[A-Za-z][A-Za-z0-9_-]{0,63}`. Values such as `tool_call_0001` are valid. The
runtime never creates, changes, or repairs an ID and has no clock or random-ID
dependency. Request arguments are copied at construction and must be finite,
canonical-JSON-compatible data.

Unknown tools and operations fail explicitly. Schema validation occurs before
dispatch and rejects missing, unknown, incorrectly typed, malformed, and
out-of-bound structural arguments. It performs no coercion. Deeper
operation-owned validation, such as Calculator expression parsing or exact
XBRL concept existence, remains in the frozen tool and its typed error
hierarchy.

## Dispatch and adaptation

The runtime invokes exactly the requested registered method exactly once with
the effective arguments. It does not strip or otherwise normalize query text,
expand filters beyond declared frozen defaults, or alter a native result.

`request_arguments` is an exact copy of the caller's mapping.
`effective_arguments` is a separate copy containing only the mechanically
resolved defaults declared in the selected frozen spec. Thus an omitted
`top_k` and explicit `top_k=10` retain different raw request identities while
dispatching the same effective value. If validation fails before default
resolution, `effective_arguments` is null because nothing was dispatched.

The only type adaptation is for Calculator input records. Each JSON-like input
object is copied into one frozen `CalculationInput`; field values are passed
unchanged. The native `CalculationResponse`, `RetrievalResponse`,
`ConceptSearchResponse`, or `FactQueryResponse` object is retained separately
and by identity in the common result.

There are no automatic retries for malformed input, empty results, errors, or
any other outcome. A subsequent attempt must be a new explicit request with a
new caller-supplied `call_id`.

## Common result and errors

Every completed dispatch attempt returns `ToolInvocationResult` with:

- `call_id`, logical `tool_name`, frozen `tool_version`, and `operation`;
- copied `request_arguments`;
- deterministic `effective_arguments`, or null before dispatch resolution;
- `status`, either `success` or `error`;
- the typed native `result` on success;
- the native `tool_trace` on success;
- SHA-256 of the exact native canonical trace bytes;
- the complete `tool_spec_sha256`;
- relevant frozen dependency versions and commits; and
- a structured `error` on failure.

Success has `error=None`. Failure has no result, native trace, partial result,
or native-trace hash. `ToolErrorEnvelope` contains deterministic `error_type`,
stable `error_code`, and `safe_message`; it contains no traceback. Frozen
typed tool failures retain their concrete exception class name as
`error_type`. Unexpected exception messages are not copied into the canonical
record.

`ToolInvocationResult.canonical_json()` serializes the common record with the
same sorted-key, compact, finite-number, terminal-newline policy. The canonical
common record deliberately excludes the full native result and native trace.
It includes their stable native-trace SHA-256 identity instead. The typed
native objects remain available on `ToolInvocationResult` for runtime use, but
the common layer does not create a second serialization or numeric
reinterpretation of domain results.

## Native trace preservation

The runtime obtains the native trace from `response.trace` and calls that
trace's own `canonical_json()`. SHA-256 is computed directly over the UTF-8
encoding of that exact returned text. The typed native trace object remains in
the common envelope; the common layer neither reinterprets it nor substitutes
its own domain trace.

## Sequential ledger

`ToolTraceLedger` is an append-only in-memory sequence of completed common
results. It does not generate call IDs. `append()` rejects a duplicate
`call_id`, and `records` returns records in append order without sorting.

`canonical_json()` emits an object containing `ledger_version` and the ordered
common records under the common canonical JSON policy. `sha256()` hashes those
exact UTF-8 bytes, including the terminal newline. Identical ordered ledgers
serialize byte-identically. This ledger is only a sequence of tool
invocations; it is not an agent trace.

## Isolation

The module imports only the three frozen tool modules and Python standard
library facilities. It adds no LLM, agent, network, benchmark, gold,
evaluation-result, DEV, or TEST dependency. Production construction uses the
existing frozen local factories; the runtime itself performs no I/O.
