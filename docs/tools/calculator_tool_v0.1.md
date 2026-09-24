# CalculatorTool v0.1

## Contract

`CalculatorTool` is a deterministic arithmetic engine. It receives an explicit
expression and explicitly named exact-decimal inputs, evaluates only the v0.1
grammar, and returns a canonical decimal string plus a deterministic audit
trace.

```python
from src.tools import CalculationInput, CalculatorTool

tool = CalculatorTool()
response = tool.calculate(
    "a - b",
    {
        "a": CalculationInput(
            value="123.45",
            unit="caller_declared_unit",
            provenance={"type": "xbrl_fact", "fact_locator": "DOC#fact-1"},
        ),
        "b": CalculationInput(
            value="67.89",
            provenance={"type": "chunk", "chunk_id": "chunk-example-001"},
        ),
    },
    result_metadata={"unit": "caller_declared_unit"},
)

assert response.result == "55.56"
```

The public method is:

```python
CalculatorTool.calculate(
    expression: str,
    inputs: Mapping[str, CalculationInput],
    *,
    result_metadata: Mapping[str, Any] | None = None,
) -> CalculationResponse
```

There is no production constructor, artifact load, network path, or dependency
on RetrievalTool or XBRLTool. A CalculatorTool instance has no mutable state.

## Responsibility boundary

CalculatorTool guarantees deterministic Decimal arithmetic under the frozen
policy below. It does **not** guarantee or decide:

- which facts should be inputs;
- whether a fact or reporting period is correct;
- whether one duration should be subtracted from another;
- whether units are compatible or need conversion;
- whether GAAP and non-GAAP bases are compatible;
- which accounting definition applies;
- the economic interpretation of the result; or
- whether provenance provides adequate citation support.

Those are agent and evaluation responsibilities. Input `unit`, `basis`,
`period`, and `provenance` fields are opaque audit metadata. They never change
the calculation. CalculatorTool does not fetch, construct, interpret, or
semantically validate provenance. It never infers a result unit. Optional
`result_metadata` exists only for metadata explicitly supplied by the caller.

## Expression grammar

The complete v0.1 grammar is:

```text
expression := term (("+" | "-") term)*
term       := unary (("*" | "/") unary)*
unary      := ("+" | "-")* primary
primary    := variable | literal | "(" expression ")"
variable   := [A-Za-z_][A-Za-z0-9_]*
literal    := [0-9]+ ("." [0-9]+)?
```

ASCII whitespace may occur between tokens. Binary operators are
left-associative. Parentheses and the usual multiplication/division precedence
apply. Literal signs are unary operators. Scientific notation and abbreviated
forms such as `.5` or `1.` are not part of the grammar.

Function calls, attributes, indexing, exponentiation, floor division, modulo,
assignments, comparisons, imports, conditionals, strings, collections, and all
other Python syntax are unsupported. The parser is purpose-built for this
grammar. It does not use `eval`, `exec`, or arbitrary Python evaluation.

`normalized_expression` is a deterministic fully parenthesized structural
form. It removes whitespace and redundant source parentheses and canonicalizes
numeric literals. For example, `(value + 1.2300) * -scale` becomes
`((value + 1.23) * (-scale))`. The original expression is retained separately.

## Decimal policy

Inputs and expression literals are constructed directly from strings with
`Decimal`; there is no binary-float conversion. Every arithmetic operation
runs inside a fresh local context with:

- precision: 50 significant digits;
- rounding: `ROUND_HALF_EVEN`;
- the standard Decimal exponent bounds and traps supplied by `Context`; and
- no mutation of the process-global Decimal context.

The precision and rounding mode appear in every trace. Terminating arithmetic
is exact when representable within 50 significant digits. A non-terminating
operation is deterministically rounded by that context. For example, `1 / 3`
produces `0.` followed by exactly 50 threes. CalculatorTool performs no display
quantization or caller-facing rounding.

## Canonical numeric serialization

Results, normalized input values, and normalized expression literals use
plain decimal notation:

- exponent notation is not emitted;
- insignificant fractional trailing zeros are removed;
- a trailing decimal point is removed;
- every signed zero is serialized as `"0"`; and
- non-finite values are forbidden.

Thus `Decimal("1458")` becomes `"1458"`, `Decimal("1.2300")` becomes
`"1.23"`, and `Decimal("-0")` becomes `"0"`. The original input string is
also retained in each `CalculationInputRecord.value`, while its canonical form
is exposed as `normalized_value`.

## Input contract

`inputs` is a mapping from a case-sensitive conservative ASCII identifier to a
`CalculationInput`. A value must be a plain exact decimal string matching
`[+-]?[0-9]+(\.[0-9]+)?`. Values such as `$1,999`, `54%`, `1.2B`, `1e3`, NaN,
and Infinity are rejected rather than coerced.

Every expression variable must have one input, and every supplied input must be
used. Pure-literal expressions are rejected, preserving a named-input audit
trail. Because the API is a mapping, duplicate exact keys cannot be represented
at the call boundary; CalculatorTool performs no case folding or other logical
name normalization. `a` and `A` are distinct variables.

Input records in the response and trace are ordered lexicographically by name,
independent of mapping insertion order. `used_input_names` follows the same
stable order.

Opaque provenance must be a canonical-JSON-safe mapping with string keys. It
may contain nested mappings, lists/tuples, strings, booleans, exact integers,
and null. Python floats (including finite floats), Decimal objects, and other
arbitrary objects are rejected rather than coerced. Exact non-integer metadata
numbers should be supplied as strings. This structural check only makes deterministic trace
serialization possible; it does not validate source meaning or support.
Caller metadata is deep-copied and passed through without invention.

## Response and trace

`CalculationResponse` contains:

- `tool_version`;
- original `expression` and `normalized_expression`;
- ordered validated `inputs`;
- ordered `used_input_names`;
- canonical string `result`;
- explicit caller `result_metadata`, or null; and
- `CalculationTrace`.

Each input record contains its `name`, original string `value`, canonical
`normalized_value`, and any supplied `unit`, `basis`, `period`, and
`provenance` fields. Absent optional fields remain absent from dictionary/JSON
representations.

The trace contains:

- `tool_name` and `tool_version`;
- original and normalized expressions;
- ordered `input_names` and complete ordered input records;
- ordered `used_input_names`;
- canonical string `result`;
- Decimal `precision` and `rounding`; and
- caller-supplied result metadata.

`canonical_calculation_trace_json()` and `trace.canonical_json()` serialize
with lexicographically sorted object keys, compact separators, UTF-8-compatible
JSON, finite numbers only, and exactly one terminal newline. There is no
timestamp. Identical calls produce byte-identical trace text.

The response field names align mechanically with the frozen
`agent_output_schema_v0.1` calculation concept: an explicit expression,
ordered named inputs, and a result. The tool deliberately returns exact values
as strings. Any future agent integration that converts those strings to the
schema's JSON-number fields must do so explicitly without changing the frozen
schema. Structured XBRL provenance beyond that schema remains a future schema
version concern.

## Deterministic errors

All calls either return a complete result or raise an exception; no partial
result is returned. The public error hierarchy distinguishes:

- empty expressions;
- invalid grammar;
- explicitly unsupported syntax/operators;
- missing variables;
- invalid variable names;
- unused supplied inputs;
- literal-only expressions;
- malformed decimal strings;
- non-finite inputs;
- non-canonical-JSON-safe metadata;
- resource-limit violations;
- division by zero;
- other Decimal arithmetic failures; and
- non-finite results.

## Frozen resource limits

CalculatorTool v0.1 enforces:

- at most 1,024 expression characters;
- at most 256 expression nodes;
- at most 32 expression-tree/parenthesis levels;
- at most 64 distinct variables and supplied inputs; and
- at most 1,024 characters in each input decimal string.

These are parser and resource-safety limits only. They encode no financial or
benchmark-specific policy.
