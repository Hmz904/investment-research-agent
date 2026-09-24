"""Gold-blind synthetic tests for ToolRuntime / ToolRegistry v0.1."""

from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import dataclass
from typing import Any

import pytest

import src.tools.runtime as runtime_module
from src.tools.calculator_tool import (
    CalculationInput,
    CalculatorDivisionByZeroError,
    CalculatorTool,
)
from src.tools.runtime import (
    CALCULATOR_TOOL_COMMIT,
    RETRIEVAL_TOOL_COMMIT,
    TOOL_SPEC_SHA256,
    XBRL_TOOL_COMMIT,
    DuplicateCallIDError,
    ToolCallRequest,
    ToolCallValidationError,
    ToolRegistry,
    ToolTraceLedger,
    ToolVersionMismatchError,
    UnknownOperationError,
    UnknownToolError,
    canonical_tool_specs_json,
)


@dataclass(frozen=True)
class _FakeTrace:
    tool: str
    operation: str
    arguments: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "operation": self.operation,
            "arguments": self.arguments,
        }

    def canonical_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ) + "\n"


@dataclass(frozen=True)
class _FakeResponse:
    value: str
    trace: _FakeTrace

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "trace": self.trace.to_dict()}


class _RecordingRetrieval:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def search(self, **arguments: Any) -> _FakeResponse:
        self.calls.append(arguments)
        return _FakeResponse(
            "retrieval-result", _FakeTrace("retrieval", "search", arguments)
        )


class _RecordingXBRL:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def search_concepts(self, **arguments: Any) -> _FakeResponse:
        self.calls.append(("search_concepts", arguments))
        return _FakeResponse(
            "concept-result", _FakeTrace("xbrl", "search_concepts", arguments)
        )

    def query_facts(self, **arguments: Any) -> _FakeResponse:
        self.calls.append(("query_facts", arguments))
        return _FakeResponse(
            "facts-result", _FakeTrace("xbrl", "query_facts", arguments)
        )


class _RecordingCalculator:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def calculate(self, **arguments: Any) -> _FakeResponse:
        self.calls.append(arguments)
        trace_arguments = {
            **arguments,
            "inputs": {
                name: value.to_dict() for name, value in arguments["inputs"].items()
            },
        }
        return _FakeResponse(
            "calculator-result",
            _FakeTrace("calculator", "calculate", trace_arguments),
        )


@pytest.fixture
def injected_registry() -> tuple[
    ToolRegistry, _RecordingRetrieval, _RecordingXBRL, _RecordingCalculator
]:
    retrieval = _RecordingRetrieval()
    xbrl = _RecordingXBRL()
    calculator = _RecordingCalculator()
    registry = ToolRegistry(
        retrieval_tool=retrieval,
        xbrl_tool=xbrl,
        calculator_tool=calculator,
    )
    return registry, retrieval, xbrl, calculator


def test_registry_exposes_exactly_four_deterministically_ordered_operations(
    injected_registry: tuple[
        ToolRegistry, _RecordingRetrieval, _RecordingXBRL, _RecordingCalculator
    ],
) -> None:
    registry = injected_registry[0]
    expected = [
        "calculator.calculate",
        "retrieval.search",
        "xbrl.query_facts",
        "xbrl.search_concepts",
    ]
    assert [spec.qualified_name for spec in registry.list_tools()] == expected
    assert [spec.qualified_name for spec in registry.list_tools()] == expected


def test_registry_reports_frozen_versions_and_commits(injected_registry) -> None:
    registry = injected_registry[0]
    assert registry.get_tool_spec("retrieval.search").tool_version == (
        "retrieval_tool_v0.1"
    )
    assert registry.get_tool_spec("xbrl", "query_facts").tool_version == (
        "xbrl_tool_v0.1"
    )
    assert registry.get_tool_spec("calculator.calculate").tool_version == (
        "calculator_tool_v0.1"
    )
    assert RETRIEVAL_TOOL_COMMIT == "cce61f3fa6b2e4f1fca548c0c931330d9de5a96c"
    assert XBRL_TOOL_COMMIT == "d3bceec1db9d608bd702a5cf3b5329f9710697ea"
    assert CALCULATOR_TOOL_COMMIT == "72108f24b03b3d6114f04a29366178cde9de97d9"


def test_registry_lookup_unknown_tool_and_operation_are_explicit(
    injected_registry,
) -> None:
    registry = injected_registry[0]
    with pytest.raises(UnknownToolError, match="unknown tool"):
        registry.get_tool_spec("missing.search")
    with pytest.raises(UnknownOperationError, match="unknown operation"):
        registry.get_tool_spec("retrieval.missing")


def test_specs_match_frozen_public_signatures_without_unsupported_parameters(
    injected_registry,
) -> None:
    registry = injected_registry[0]
    actual = {
        "retrieval.search": {"query", "top_k"},
        "xbrl.search_concepts": {"query", "top_k"},
        "xbrl.query_facts": {
            "concept",
            "accession",
            "company",
            "form_type",
            "filing_fiscal_period",
            "period_start",
            "period_end",
            "instant",
            "unit",
            "include_dimensions",
        },
        "calculator.calculate": {"expression", "inputs", "result_metadata"},
    }
    implementations = {
        "retrieval.search": runtime_module.RetrievalTool.search,
        "xbrl.search_concepts": runtime_module.XBRLTool.search_concepts,
        "xbrl.query_facts": runtime_module.XBRLTool.query_facts,
        "calculator.calculate": runtime_module.CalculatorTool.calculate,
    }
    for spec in registry.list_tools():
        properties = set(spec.argument_schema["properties"])
        signature = inspect.signature(implementations[spec.qualified_name])
        signature_names = set(signature.parameters)
        signature_names.remove("self")
        assert properties == actual[spec.qualified_name] == signature_names
        assert spec.argument_schema["additionalProperties"] is False
        assert set(spec.required_arguments) | set(spec.optional_arguments) == properties
        assert set(spec.required_arguments).isdisjoint(spec.optional_arguments)
        for name in signature_names:
            parameter = signature.parameters[name]
            if parameter.default is inspect.Parameter.empty:
                assert name in spec.required_arguments
                assert "default" not in spec.argument_schema["properties"][name]
            else:
                assert name in spec.optional_arguments
                assert (
                    spec.argument_schema["properties"][name]["default"]
                    == parameter.default
                )


def test_specs_match_frozen_defaults_nullability_and_bounds(injected_registry) -> None:
    registry = injected_registry[0]
    retrieval = registry.get_tool_spec("retrieval.search").argument_schema
    concept_search = registry.get_tool_spec("xbrl.search_concepts").argument_schema
    for schema in (retrieval, concept_search):
        assert schema["required"] == ["query"]
        assert schema["properties"]["top_k"] == {
            "type": "integer",
            "minimum": 1,
            "maximum": 50,
            "default": 10,
        }

    facts = registry.get_tool_spec("xbrl.query_facts").argument_schema
    assert facts["required"] == ["concept"]
    nullable_filters = {
        "accession",
        "company",
        "form_type",
        "filing_fiscal_period",
        "period_start",
        "period_end",
        "instant",
        "unit",
    }
    assert all(
        facts["properties"][name]["type"] == ["string", "null"]
        and facts["properties"][name]["default"] is None
        for name in nullable_filters
    )
    assert facts["properties"]["include_dimensions"] == {
        "type": "boolean",
        "default": True,
    }

    calculator = registry.get_tool_spec("calculator.calculate").argument_schema
    assert calculator["required"] == ["expression", "inputs"]
    assert calculator["properties"]["result_metadata"]["default"] is None
    input_schema = calculator["properties"]["inputs"]["additionalProperties"]
    assert input_schema["required"] == ["value"]
    assert set(input_schema["properties"]) == {
        "value",
        "unit",
        "basis",
        "period",
        "provenance",
    }
    assert input_schema["additionalProperties"] is False
    assert input_schema["properties"]["value"]["type"] == "string"
    for name in ("unit", "basis", "period"):
        assert input_schema["properties"][name]["type"] == ["string", "null"]
    provenance_types = input_schema["properties"]["provenance"]["anyOf"]
    assert {alternative["type"] for alternative in provenance_types} == {
        "null",
        "object",
    }


def test_tool_descriptions_are_neutral(injected_registry) -> None:
    descriptions = " ".join(
        spec.description.casefold() for spec in injected_registry[0].list_tools()
    )
    prohibited = (
        "subtract h1",
        "use xbrl",
        "numeric questions",
        "thesis questions",
        "prefer one context",
        "benchmark",
    )
    assert not any(phrase in descriptions for phrase in prohibited)


def test_tool_spec_serialization_and_hash_are_byte_stable() -> None:
    first = canonical_tool_specs_json()
    second = canonical_tool_specs_json()
    assert first.encode("utf-8") == second.encode("utf-8")
    assert first.endswith("\n") and not first.endswith("\n\n")
    assert TOOL_SPEC_SHA256 == hashlib.sha256(first.encode("utf-8")).hexdigest()
    assert TOOL_SPEC_SHA256 == (
        "879a710485ac42b6dc0793b0556ce811d4efb151b52a7ae69f90334d489db70d"
    )
    assert "/mnt/" not in first
    assert "timestamp" not in first.casefold()


def test_valid_request_copies_caller_arguments() -> None:
    arguments = {"query": "revenue", "top_k": 3}
    request = ToolCallRequest("tool_call_0001", "retrieval", "search", arguments)
    arguments["query"] = "mutated"
    assert request.arguments == {"query": "revenue", "top_k": 3}


def test_raw_and_effective_arguments_distinguish_omitted_from_explicit_default(
    injected_registry,
) -> None:
    registry = injected_registry[0]
    omitted = registry.invoke(
        ToolCallRequest("tool_call_0001", "retrieval", "search", {"query": "q"})
    )
    explicit = registry.invoke(
        ToolCallRequest(
            "tool_call_0002",
            "retrieval",
            "search",
            {"query": "q", "top_k": 10},
        )
    )
    assert omitted.request_arguments == {"query": "q"}
    assert explicit.request_arguments == {"query": "q", "top_k": 10}
    assert omitted.effective_arguments == explicit.effective_arguments == {
        "query": "q",
        "top_k": 10,
    }
    assert omitted.canonical_json() != explicit.canonical_json()


@pytest.mark.parametrize(
    "call_id", ["", "1tool", "tool.call", "tool call", "a" * 65, "naïve"]
)
def test_invalid_call_id_is_rejected(call_id: str) -> None:
    with pytest.raises(ToolCallValidationError, match="call_id"):
        ToolCallRequest(call_id, "retrieval", "search", {"query": "q"})


@pytest.mark.parametrize(
    ("tool_name", "operation", "arguments", "message"),
    [
        ("retrieval", "search", {"query": "q", "extra": 1}, "unknown"),
        ("retrieval", "search", {}, "missing"),
        ("retrieval", "search", {"query": 7}, "type string"),
        ("retrieval", "search", {"query": "q", "top_k": None}, "integer"),
        ("retrieval", "search", {"query": "q", "top_k": True}, "integer"),
        ("retrieval", "search", {"query": "q", "top_k": 0}, "at least"),
        ("retrieval", "search", {"query": "q", "top_k": 51}, "at most"),
        ("xbrl", "query_facts", {"concept": ""}, "at least"),
        (
            "xbrl",
            "query_facts",
            {"concept": "us-gaap:Assets", "include_dimensions": None},
            "boolean",
        ),
        (
            "xbrl",
            "query_facts",
            {"concept": "us-gaap:Assets", "accession": "bad"},
            "does not match",
        ),
        (
            "xbrl",
            "query_facts",
            {"concept": "us-gaap:Assets", "instant": "2026-02-30"},
            "ISO date",
        ),
        (
            "xbrl",
            "query_facts",
            {
                "concept": "us-gaap:Assets",
                "instant": "2026-03-31",
                "period_start": "2026-01-01",
            },
            "cannot be combined",
        ),
        (
            "calculator",
            "calculate",
            {"expression": "a", "inputs": {"a": {"value": 1}}},
            "type string",
        ),
        (
            "calculator",
            "calculate",
            {
                "expression": "a",
                "inputs": {"a": {"value": "1", "unsupported": "x"}},
            },
            "unknown",
        ),
        (
            "calculator",
            "calculate",
            {
                "expression": "a",
                "inputs": {"bad-name": {"value": "1"}},
            },
            "property name",
        ),
        (
            "calculator",
            "calculate",
            {
                "expression": "a",
                "inputs": {"a": {"value": "1"}},
                "result_metadata": {"ratio": 1.5},
            },
            "allowed type",
        ),
    ],
)
def test_invalid_arguments_fail_before_invocation(
    injected_registry, tool_name, operation, arguments, message
) -> None:
    registry, retrieval, xbrl, calculator = injected_registry
    result = registry.invoke(
        ToolCallRequest("tool_call_0001", tool_name, operation, arguments)
    )
    assert result.status == "error"
    assert result.error is not None
    assert result.error.error_code == "runtime.invalid_arguments"
    assert message in result.error.safe_message
    assert result.effective_arguments is None
    assert not retrieval.calls
    assert not xbrl.calls
    assert not calculator.calls


def test_unknown_tool_and_operation_return_error_envelopes_without_dispatch(
    injected_registry,
) -> None:
    registry, retrieval, xbrl, calculator = injected_registry
    unknown_tool = registry.invoke(
        ToolCallRequest("tool_call_0001", "missing", "search", {})
    )
    unknown_operation = registry.invoke(
        ToolCallRequest("tool_call_0002", "retrieval", "missing", {})
    )
    assert unknown_tool.error is not None
    assert unknown_tool.error.error_code == "runtime.unknown_tool"
    assert unknown_operation.error is not None
    assert unknown_operation.error.error_code == "runtime.unknown_operation"
    assert not retrieval.calls and not xbrl.calls and not calculator.calls


def test_each_operation_dispatches_to_only_its_exact_method(injected_registry) -> None:
    registry, retrieval, xbrl, calculator = injected_registry
    calls = (
        ToolCallRequest("call_a", "retrieval", "search", {"query": "  exact  "}),
        ToolCallRequest("call_b", "xbrl", "search_concepts", {"query": "cash"}),
        ToolCallRequest(
            "call_c",
            "xbrl",
            "query_facts",
            {"concept": "us-gaap:Cash", "include_dimensions": False},
        ),
        ToolCallRequest(
            "call_d",
            "calculator",
            "calculate",
            {"expression": "a + b", "inputs": {"a": {"value": "1"}, "b": {"value": "2"}}},
        ),
    )
    results = [registry.invoke(call) for call in calls]
    assert all(result.status == "success" for result in results)
    assert retrieval.calls == [{"query": "  exact  ", "top_k": 10}]
    assert xbrl.calls == [
        ("search_concepts", {"query": "cash", "top_k": 10}),
        (
            "query_facts",
            {
                "concept": "us-gaap:Cash",
                "accession": None,
                "company": None,
                "form_type": None,
                "filing_fiscal_period": None,
                "period_start": None,
                "period_end": None,
                "instant": None,
                "unit": None,
                "include_dimensions": False,
            },
        ),
    ]
    assert len(calculator.calls) == 1


def test_calculator_input_conversion_is_mechanical(injected_registry) -> None:
    registry, _, _, calculator = injected_registry
    raw_input = {
        "value": "1.2300",
        "unit": "opaque-unit",
        "basis": "opaque-basis",
        "period": "opaque-period",
        "provenance": {"fact": "exact-id", "ordinal": 2},
    }
    result = registry.invoke(
        ToolCallRequest(
            "tool_call_0001",
            "calculator",
            "calculate",
            {
                "expression": "amount",
                "inputs": {"amount": raw_input},
                "result_metadata": {"source": "caller"},
            },
        )
    )
    assert result.status == "success"
    converted = calculator.calls[0]["inputs"]["amount"]
    assert isinstance(converted, CalculationInput)
    assert converted.to_dict() == raw_input
    assert calculator.calls[0]["expression"] == "amount"
    assert calculator.calls[0]["result_metadata"] == {"source": "caller"}


def test_explicit_nullable_calculator_fields_are_not_coerced(injected_registry) -> None:
    registry, _, _, calculator = injected_registry
    result = registry.invoke(
        ToolCallRequest(
            "tool_call_0001",
            "calculator",
            "calculate",
            {
                "expression": "amount",
                "inputs": {
                    "amount": {
                        "value": "1.00",
                        "unit": None,
                        "basis": None,
                        "period": None,
                        "provenance": None,
                    }
                },
                "result_metadata": None,
            },
        )
    )
    assert result.status == "success"
    converted = calculator.calls[0]["inputs"]["amount"]
    assert converted.value == "1.00"
    assert converted.unit is None
    assert converted.basis is None
    assert converted.period is None
    assert converted.provenance is None
    assert result.request_arguments["result_metadata"] is None
    assert result.effective_arguments["result_metadata"] is None


def test_native_result_is_not_modified_or_replaced(injected_registry) -> None:
    registry, retrieval, _, _ = injected_registry
    result = registry.invoke(
        ToolCallRequest("tool_call_0001", "retrieval", "search", {"query": "q"})
    )
    assert result.result is not None
    assert result.result.value == "retrieval-result"
    assert retrieval.calls == [{"query": "q", "top_k": 10}]


def test_native_trace_is_preserved_and_exact_bytes_are_hashed(injected_registry) -> None:
    result = injected_registry[0].invoke(
        ToolCallRequest("tool_call_0001", "retrieval", "search", {"query": "q"})
    )
    assert result.result is not None
    assert result.tool_trace is result.result.trace
    expected = hashlib.sha256(
        result.tool_trace.canonical_json().encode("utf-8")
    ).hexdigest()
    assert result.tool_trace_sha256 == expected
    assert result.tool_spec_sha256 == TOOL_SPEC_SHA256


class _FailingCalculator:
    def __init__(self) -> None:
        self.call_count = 0

    def calculate(self, **arguments: Any) -> None:
        self.call_count += 1
        raise CalculatorDivisionByZeroError("division by zero")


def test_typed_tool_error_is_preserved_and_not_retried() -> None:
    failing = _FailingCalculator()
    registry = ToolRegistry(
        retrieval_tool=_RecordingRetrieval(),
        xbrl_tool=_RecordingXBRL(),
        calculator_tool=failing,
    )
    result = registry.invoke(
        ToolCallRequest(
            "tool_call_0001",
            "calculator",
            "calculate",
            {"expression": "a / zero", "inputs": {"a": {"value": "1"}, "zero": {"value": "0"}}},
        )
    )
    assert result.status == "error"
    assert result.result is None
    assert result.error is not None
    assert result.error.error_type == "CalculatorDivisionByZeroError"
    assert result.error.error_code == "calculator.calculator_division_by_zero_error"
    assert result.error.safe_message == "division by zero"
    assert result.tool_trace is None
    assert result.tool_trace_sha256 is None
    assert failing.call_count == 1
    assert result.canonical_json() == result.canonical_json()


def test_identical_injected_failures_have_byte_identical_error_records() -> None:
    failing = _FailingCalculator()
    registry = ToolRegistry(
        retrieval_tool=_RecordingRetrieval(),
        xbrl_tool=_RecordingXBRL(),
        calculator_tool=failing,
    )
    call = ToolCallRequest(
        "tool_call_0001",
        "calculator",
        "calculate",
        {
            "expression": "a / zero",
            "inputs": {"a": {"value": "1"}, "zero": {"value": "0"}},
        },
    )
    first = registry.invoke(call)
    second = registry.invoke(call)
    assert first.canonical_json().encode("utf-8") == second.canonical_json().encode(
        "utf-8"
    )
    assert failing.call_count == 2


def test_real_calculator_integration_through_registry() -> None:
    registry = ToolRegistry(
        retrieval_tool=_RecordingRetrieval(),
        xbrl_tool=_RecordingXBRL(),
        calculator_tool=CalculatorTool(),
    )
    result = registry.invoke(
        ToolCallRequest(
            "tool_call_0001",
            "calculator",
            "calculate",
            {"expression": "a + b", "inputs": {"a": {"value": "1"}, "b": {"value": "2"}}},
        )
    )
    assert result.status == "success"
    assert result.result.result == "3"
    assert result.tool_trace is result.result.trace


def test_common_success_envelope_is_deterministic(injected_registry) -> None:
    registry = injected_registry[0]
    call = ToolCallRequest("tool_call_0001", "retrieval", "search", {"query": "q"})
    first = registry.invoke(call)
    second = registry.invoke(call)
    assert first.canonical_json().encode("utf-8") == second.canonical_json().encode(
        "utf-8"
    )
    assert first.canonical_json().endswith("\n")
    assert "timestamp" not in first.canonical_json().casefold()
    canonical = json.loads(first.canonical_json())
    assert "result" not in canonical
    assert "tool_trace" not in canonical
    assert canonical["tool_trace_sha256"] == first.tool_trace_sha256


def test_ledger_preserves_append_order_and_rejects_duplicate_call_id(
    injected_registry,
) -> None:
    registry = injected_registry[0]
    second = registry.invoke(
        ToolCallRequest("tool_call_0002", "xbrl", "search_concepts", {"query": "q"})
    )
    first = registry.invoke(
        ToolCallRequest("tool_call_0001", "retrieval", "search", {"query": "q"})
    )
    ledger = ToolTraceLedger()
    ledger.append(second)
    ledger.append(first)
    assert [record.call_id for record in ledger.records] == [
        "tool_call_0002",
        "tool_call_0001",
    ]
    with pytest.raises(DuplicateCallIDError, match="duplicate call_id"):
        ledger.append(first)


def test_identical_ledgers_serialize_and_hash_byte_identically(
    injected_registry,
) -> None:
    result = injected_registry[0].invoke(
        ToolCallRequest("tool_call_0001", "retrieval", "search", {"query": "q"})
    )
    first = ToolTraceLedger()
    second = ToolTraceLedger()
    first.append(result)
    second.append(result)
    assert first.canonical_json().encode("utf-8") == second.canonical_json().encode(
        "utf-8"
    )
    assert first.sha256() == second.sha256()
    assert first.canonical_json().endswith("\n")


def test_injected_instances_are_reused_across_calls(injected_registry) -> None:
    registry, retrieval, _, _ = injected_registry
    tool_identity = id(retrieval)
    for index in range(3):
        result = registry.invoke(
            ToolCallRequest(f"tool_call_{index:04d}", "retrieval", "search", {"query": "q"})
        )
        assert result.status == "success"
    assert id(registry._tools["retrieval"]) == tool_identity
    assert len(retrieval.calls) == 3


def test_from_frozen_tools_constructs_each_tool_once(monkeypatch) -> None:
    counts = {"retrieval": 0, "xbrl": 0, "calculator": 0}

    class RetrievalFactory(_RecordingRetrieval):
        @classmethod
        def from_frozen_stack(cls):
            counts["retrieval"] += 1
            return cls()

    class XBRLFactory(_RecordingXBRL):
        @classmethod
        def from_frozen_ingestion(cls):
            counts["xbrl"] += 1
            return cls()

    class CalculatorFactory(_RecordingCalculator):
        def __init__(self):
            counts["calculator"] += 1
            super().__init__()

    monkeypatch.setattr(runtime_module, "RetrievalTool", RetrievalFactory)
    monkeypatch.setattr(runtime_module, "XBRLTool", XBRLFactory)
    monkeypatch.setattr(runtime_module, "CalculatorTool", CalculatorFactory)
    registry = ToolRegistry.from_frozen_tools()
    registry.invoke(
        ToolCallRequest("tool_call_0001", "retrieval", "search", {"query": "q"})
    )
    registry.invoke(
        ToolCallRequest("tool_call_0002", "retrieval", "search", {"query": "q"})
    )
    assert counts == {"retrieval": 1, "xbrl": 1, "calculator": 1}


def test_production_factory_rejects_frozen_module_version_mismatch(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        runtime_module, "NATIVE_RETRIEVAL_TOOL_VERSION", "retrieval_tool_v9.9"
    )
    with pytest.raises(ToolVersionMismatchError, match="module version mismatch"):
        ToolRegistry.from_frozen_tools()


def test_production_registry_rejects_mismatched_response_version() -> None:
    registry = ToolRegistry(
        retrieval_tool=_RecordingRetrieval(),
        xbrl_tool=_RecordingXBRL(),
        calculator_tool=_RecordingCalculator(),
        _production_frozen=True,
    )
    result = registry.invoke(
        ToolCallRequest("tool_call_0001", "retrieval", "search", {"query": "q"})
    )
    assert result.status == "error"
    assert result.error is not None
    assert result.error.error_code == "runtime.tool_version_mismatch"
    assert result.error.error_type == "ToolVersionMismatchError"


def test_runtime_source_has_no_agent_llm_network_or_evaluation_dependency() -> None:
    source = inspect.getsource(runtime_module)
    prohibited_imports = (
        "import requests",
        "import openai",
        "from openai",
        "gold_map",
        "eval_protocol",
        "tests/locked",
        "benchmark",
    )
    assert not any(term in source.casefold() for term in prohibited_imports)
