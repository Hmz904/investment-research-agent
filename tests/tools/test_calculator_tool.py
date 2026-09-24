"""Gold-blind synthetic tests for CalculatorTool v0.1."""

from __future__ import annotations

import ast
import json
from decimal import ROUND_DOWN, getcontext, localcontext

import pytest

from src.tools.calculator_tool import (
    DECIMAL_PRECISION,
    DECIMAL_ROUNDING,
    MAX_EXPRESSION_CHARACTERS,
    MAX_EXPRESSION_DEPTH,
    MAX_EXPRESSION_NODES,
    MAX_VARIABLES,
    CalculationInput,
    CalculatorDivisionByZeroError,
    CalculatorMetadataError,
    CalculatorResourceLimitError,
    CalculatorTool,
    EmptyExpressionError,
    InvalidExpressionSyntaxError,
    InvalidVariableNameError,
    LiteralOnlyExpressionError,
    MalformedDecimalError,
    MissingVariableError,
    NonFiniteInputError,
    UnsupportedExpressionError,
    UnusedInputError,
    canonical_calculation_trace_json,
)


def _calculate(expression: str, **values: str):
    inputs = {name: CalculationInput(value) for name, value in values.items()}
    return CalculatorTool().calculate(expression, inputs)


@pytest.mark.parametrize(
    ("expression", "values", "expected"),
    [
        ("a + b", {"a": "12", "b": "3"}, "15"),
        ("a - b", {"a": "12", "b": "3"}, "9"),
        ("a * b", {"a": "12", "b": "3"}, "36"),
        ("a / b", {"a": "12", "b": "3"}, "4"),
        ("(a + b) * c", {"a": "2", "b": "3", "c": "4"}, "20"),
        ("-a + +b", {"a": "2", "b": "3"}, "1"),
    ],
)
def test_basic_arithmetic(
    expression: str, values: dict[str, str], expected: str
) -> None:
    assert _calculate(expression, **values).result == expected


@pytest.mark.parametrize(
    ("expression", "values", "expected"),
    [
        ("large_a - large_b", {"large_a": "9876543210", "large_b": "1234567890"}, "8641975320"),
        ("part / total * 100", {"part": "27", "total": "120"}, "22.5"),
        ("current - prior", {"current": "41", "prior": "58"}, "-17"),
        ("reported - comparison", {"reported": "4.81", "comparison": "4.74"}, "0.07"),
    ],
)
def test_generic_financial_style_arithmetic(
    expression: str, values: dict[str, str], expected: str
) -> None:
    assert _calculate(expression, **values).result == expected


def test_decimal_addition_has_no_binary_float_artifact() -> None:
    response = _calculate("left + right", left="0.1", right="0.2")
    assert response.result == "0.3"
    assert "00000000000000004" not in response.result


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("0.1 + 0.2 + anchor", "0.3"),
        ("4.81 - 4.74 + anchor", "0.07"),
        ("1.005 - 1 + anchor", "0.005"),
        ("-0.28 + anchor", "-0.28"),
    ],
)
def test_expression_literals_are_parsed_from_exact_lexical_text(
    expression: str, expected: str
) -> None:
    response = _calculate(expression, anchor="0")
    assert response.result == expected
    assert "000000000000000" not in response.result


@pytest.mark.parametrize(
    ("expression", "values", "expected"),
    [
        ("value", {"value": "1458"}, "1458"),
        ("value + zero", {"value": "1.2300", "zero": "0"}, "1.23"),
        ("value", {"value": "0.070"}, "0.07"),
        ("value * one", {"value": "-0", "one": "1"}, "0"),
        ("value", {"value": "-0.000"}, "0"),
        ("value", {"value": "1000000000000000000000"}, "1000000000000000000000"),
        ("value - value", {"value": "9.99"}, "0"),
    ],
)
def test_canonical_numeric_serialization(
    expression: str, values: dict[str, str], expected: str
) -> None:
    assert _calculate(expression, **values).result == expected


def test_nonterminating_division_uses_frozen_context() -> None:
    response = _calculate("one / three", one="1", three="3")
    assert response.result == "0." + ("3" * DECIMAL_PRECISION)
    assert response.trace.decimal_context == {
        "precision": 50,
        "rounding": "ROUND_HALF_EVEN",
    }


def test_ambient_decimal_context_is_ignored_and_unchanged() -> None:
    before = getcontext().copy()
    with localcontext() as ambient:
        ambient.prec = 2
        ambient.rounding = ROUND_DOWN
        response = _calculate("one / seven", one="1", seven="7")
        assert response.result == "0." + ("142857" * 8) + "14"
        exact_input = _calculate(
            "exact",
            exact="1.2345678901234567890123456789012345678901234567890123456789",
        )
        assert exact_input.result == (
            "1.2345678901234567890123456789012345678901234567890123456789"
        )
        assert ambient.prec == 2
        assert ambient.rounding == ROUND_DOWN
    after = getcontext()
    assert after.prec == before.prec
    assert after.rounding == before.rounding
    assert after.Emin == before.Emin
    assert after.Emax == before.Emax
    assert after.traps == before.traps
    assert DECIMAL_ROUNDING == "ROUND_HALF_EVEN"


@pytest.mark.parametrize(
    "expression",
    [
        "abs(a)",
        "a ** 2",
        "a.real",
        "a[0]",
        "a = 1",
        "a == 1",
        "a // 2",
        "a % 2",
    ],
)
def test_unsupported_python_syntax_is_rejected(expression: str) -> None:
    with pytest.raises(UnsupportedExpressionError):
        _calculate(expression, a="2")


@pytest.mark.parametrize("expression", ["a b", "(a + b", "a +", "'a'"])
def test_invalid_syntax_is_rejected(expression: str) -> None:
    with pytest.raises(InvalidExpressionSyntaxError):
        CalculatorTool().calculate(expression, {"a": CalculationInput("1")})


@pytest.mark.parametrize("expression", ["", " ", "\t\n"])
def test_empty_expression_is_rejected(expression: str) -> None:
    with pytest.raises(EmptyExpressionError):
        CalculatorTool().calculate(expression, {})


def test_missing_variable_is_rejected() -> None:
    with pytest.raises(MissingVariableError, match="missing"):
        _calculate("known + absent", known="1")


def test_missing_variable_fails_before_arithmetic() -> None:
    with pytest.raises(MissingVariableError, match="missing"):
        _calculate("missing / zero", zero="0")


def test_unused_supplied_input_is_rejected() -> None:
    with pytest.raises(UnusedInputError, match="unused"):
        _calculate("used + used", used="1", extra="2")


def test_literal_only_expression_is_rejected() -> None:
    with pytest.raises(LiteralOnlyExpressionError):
        CalculatorTool().calculate("1999 - 541", {})


def test_dependency_detection_uses_parsed_variable_nodes() -> None:
    response = _calculate("aa - a", a="2", aa="11")
    assert response.result == "9"
    assert response.used_input_names == ("a", "aa")


def test_repeated_variable_is_one_logical_dependency_but_is_evaluated_twice() -> None:
    response = _calculate("a + a", a="2.5")
    assert response.result == "5"
    assert response.used_input_names == ("a",)


@pytest.mark.parametrize("name", ["9lives", "bad-name", "has space", "naïve"])
def test_invalid_variable_name_is_rejected(name: str) -> None:
    with pytest.raises(InvalidVariableNameError):
        CalculatorTool().calculate("valid", {name: CalculationInput("1")})


@pytest.mark.parametrize("value", ["$1,999", "54%", "1.2B", "1e3", ".5", "1.", " 1"])
def test_non_plain_decimal_inputs_are_rejected(value: str) -> None:
    with pytest.raises(MalformedDecimalError):
        _calculate("value", value=value)


@pytest.mark.parametrize(
    "value", ["NaN", "sNaN", "Infinity", "+Infinity", "-Infinity"]
)
def test_nonfinite_inputs_are_rejected(value: str) -> None:
    with pytest.raises(NonFiniteInputError):
        _calculate("value", value=value)


@pytest.mark.parametrize("zero", ["0", "-0", "0.000"])
def test_division_by_zero_is_rejected(zero: str) -> None:
    with pytest.raises(CalculatorDivisionByZeroError):
        _calculate("one / zero", one="1", zero=zero)


def test_expression_character_limit_is_frozen() -> None:
    expression = "a" + (" " * MAX_EXPRESSION_CHARACTERS)
    with pytest.raises(CalculatorResourceLimitError, match="character"):
        _calculate(expression, a="1")


def test_expression_depth_limit_is_frozen() -> None:
    expression = ("(" * (MAX_EXPRESSION_DEPTH + 1)) + "a" + (")" * (MAX_EXPRESSION_DEPTH + 1))
    with pytest.raises(CalculatorResourceLimitError, match="depth"):
        _calculate(expression, a="1")


def test_expression_node_limit_is_frozen() -> None:
    expression = "+".join("a" for _ in range((MAX_EXPRESSION_NODES // 2) + 1))
    with pytest.raises(CalculatorResourceLimitError, match="node"):
        _calculate(expression, a="1")


def test_variable_count_limit_is_frozen() -> None:
    inputs = {
        f"v{index}": CalculationInput(str(index))
        for index in range(MAX_VARIABLES + 1)
    }
    with pytest.raises(CalculatorResourceLimitError, match="variable"):
        CalculatorTool().calculate("v0", inputs)


def test_xbrl_like_provenance_passes_through_exactly() -> None:
    provenance = {
        "type": "xbrl_fact",
        "fact_locator": "EXAMPLE_10Q#fact-7",
        "accession": "0000000001-26-000001",
        "concept": "example:Metric",
        "context_ref": "duration-context",
    }
    response = CalculatorTool().calculate(
        "fact",
        {
            "fact": CalculationInput(
                "120.00",
                unit="USD_millions",
                basis="reported",
                period="example period",
                provenance=provenance,
            )
        },
    )
    record = response.inputs[0]
    assert record.provenance == provenance
    assert record.unit == "USD_millions"
    assert record.basis == "reported"
    assert record.period == "example period"
    assert record.value == "120.00"
    assert record.normalized_value == "120"
    assert response.trace.inputs[0].provenance == provenance


def test_chunk_like_provenance_passes_through_exactly() -> None:
    provenance = {
        "type": "chunk",
        "chunk_id": "chunk-example-001",
        "accession": "0000000001-26-000001",
        "locator": "Example > Section",
    }
    response = CalculatorTool().calculate(
        "amount", {"amount": CalculationInput("7", provenance=provenance)}
    )
    assert response.inputs[0].provenance == provenance


def test_provenance_does_not_influence_arithmetic() -> None:
    first = CalculatorTool().calculate(
        "amount * two",
        {
            "amount": CalculationInput("7", provenance={"source": "first"}),
            "two": CalculationInput("2", provenance={"source": "constant"}),
        },
    )
    second = CalculatorTool().calculate(
        "amount * two",
        {
            "amount": CalculationInput("7", provenance={"source": "second"}),
            "two": CalculationInput("2", provenance={"source": "elsewhere"}),
        },
    )
    assert first.result == second.result == "14"


def test_non_json_safe_provenance_is_rejected() -> None:
    with pytest.raises(CalculatorMetadataError):
        CalculatorTool().calculate(
            "amount",
            {"amount": CalculationInput("1", provenance={"bad": float("nan")})},
        )


@pytest.mark.parametrize("unsafe", [1.25, float("nan"), float("inf")])
def test_all_float_metadata_is_rejected(unsafe: float) -> None:
    with pytest.raises(CalculatorMetadataError, match="float"):
        CalculatorTool().calculate(
            "amount",
            {"amount": CalculationInput("1", provenance={"unsafe": unsafe})},
        )


def test_provenance_and_result_metadata_are_deep_copied_without_mutation() -> None:
    provenance = {
        "identity": {"fact_locator": "DOC#fact-1"},
        "path": ["first", "second"],
    }
    result_metadata = {"display": {"unit": "caller-unit"}, "scale": 2}
    expected_provenance = {
        "identity": {"fact_locator": "DOC#fact-1"},
        "path": ["first", "second"],
    }
    expected_result_metadata = {
        "display": {"unit": "caller-unit"},
        "scale": 2,
    }

    response = CalculatorTool().calculate(
        "amount",
        {"amount": CalculationInput("5", provenance=provenance)},
        result_metadata=result_metadata,
    )
    assert provenance == expected_provenance
    assert result_metadata == expected_result_metadata

    provenance["identity"]["fact_locator"] = "MUTATED"  # type: ignore[index]
    provenance["path"].append("third")  # type: ignore[union-attr]
    result_metadata["display"]["unit"] = "MUTATED"  # type: ignore[index]
    assert response.inputs[0].provenance == expected_provenance
    assert response.result_metadata == expected_result_metadata
    assert response.trace.inputs[0].provenance == expected_provenance
    assert response.trace.result_metadata == expected_result_metadata


def test_result_metadata_is_explicitly_passed_through_not_inferred() -> None:
    metadata = {"unit": "caller_declared_units", "display": "55.56 units"}
    response = CalculatorTool().calculate(
        "a - b",
        {"a": CalculationInput("123.45"), "b": CalculationInput("67.89")},
        result_metadata=metadata,
    )
    assert response.result_metadata == metadata
    assert response.trace.result_metadata == metadata


def test_opaque_economically_incompatible_metadata_does_not_block_arithmetic() -> None:
    response = CalculatorTool().calculate(
        "usd_amount + share_count",
        {
            "usd_amount": CalculationInput(
                "10", unit="USD", basis="GAAP", period="Q1"
            ),
            "share_count": CalculationInput(
                "3", unit="shares", basis="non-GAAP", period="YTD"
            ),
        },
    )
    assert response.result == "13"


def test_trace_is_byte_identical_stably_ordered_and_timestamp_free() -> None:
    tool = CalculatorTool()
    first = tool.calculate(
        "z + a",
        {"z": CalculationInput("2.00"), "a": CalculationInput("1")},
    )
    second = tool.calculate(
        "z + a",
        {"a": CalculationInput("1"), "z": CalculationInput("2.00")},
    )
    first_json = first.trace.canonical_json()
    second_json = canonical_calculation_trace_json(second.trace)
    assert first_json == second_json
    assert first_json.endswith("\n")
    assert "timestamp" not in first_json.casefold()
    assert first.trace.input_names == ("a", "z")
    assert first.trace.used_input_names == ("a", "z")
    assert [item.name for item in first.trace.inputs] == ["a", "z"]
    payload = json.loads(first_json)
    assert payload["result"] == "3"

    def assert_no_float(value: object) -> None:
        assert not isinstance(value, float)
        if isinstance(value, dict):
            for nested in value.values():
                assert_no_float(nested)
        elif isinstance(value, list):
            for nested in value:
                assert_no_float(nested)

    assert_no_float(payload)


def test_normalized_expression_is_deterministic() -> None:
    response = _calculate(" ( value + 1.2300 ) * -scale ", value="2", scale="3")
    assert response.normalized_expression == "((value + 1.23) * (-scale))"


@pytest.mark.parametrize(
    ("expression", "expected_normalized", "expected_result"),
    [
        ("a - (b - c)", "(a - (b - c))", "12"),
        ("(a - b) - c", "((a - b) - c)", "8"),
        ("a / (b / c)", "(a / (b / c))", "4"),
        ("(a / b) / c", "((a / b) / c)", "1"),
    ],
)
def test_normalized_expression_preserves_structure_and_original_expression(
    expression: str, expected_normalized: str, expected_result: str
) -> None:
    response = _calculate(expression, a="20", b="10", c="2")
    assert response.expression == expression
    assert response.trace.expression == expression
    assert response.normalized_expression == expected_normalized
    assert response.trace.normalized_expression == expected_normalized
    assert response.result == expected_result


def test_calculator_module_has_no_other_tool_or_network_runtime_dependency() -> None:
    import src.tools.calculator_tool as calculator_module

    source = calculator_module.__loader__.get_source(calculator_module.__name__)  # type: ignore[union-attr]
    assert source is not None
    tree = ast.parse(source)
    imported_modules: set[str] = set()
    direct_calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.add(node.module)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            direct_calls.add(node.func.id)

    forbidden_module_parts = {
        "benchmark",
        "gold",
        "evaluation",
        "retrieval_tool",
        "xbrl_tool",
        "requests",
        "httpx",
        "urllib",
        "socket",
        "subprocess",
        "importlib",
    }
    for module_name in imported_modules:
        assert forbidden_module_parts.isdisjoint(module_name.split("."))
    assert {"eval", "exec", "compile", "__import__"}.isdisjoint(direct_calls)
