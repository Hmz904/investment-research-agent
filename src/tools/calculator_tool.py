"""CalculatorTool v0.1: deterministic, provenance-preserving Decimal arithmetic.

The tool intentionally knows nothing about accounting, periods, units, or fact
selection.  It evaluates a deliberately small expression language and carries
caller-supplied audit metadata through to its response and trace.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import (
    Context,
    Decimal,
    DecimalException,
    DivisionByZero,
    InvalidOperation,
    ROUND_HALF_EVEN,
    localcontext,
)
from typing import Any


TOOL_NAME = "CalculatorTool"
TOOL_VERSION = "calculator_tool_v0.1"

DECIMAL_PRECISION = 50
DECIMAL_ROUNDING = ROUND_HALF_EVEN
MAX_EXPRESSION_CHARACTERS = 1024
MAX_EXPRESSION_NODES = 256
MAX_EXPRESSION_DEPTH = 32
MAX_VARIABLES = 64
MAX_DECIMAL_CHARACTERS = 1024

_DECIMAL_CONTEXT = Context(prec=DECIMAL_PRECISION, rounding=DECIMAL_ROUNDING)
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_INPUT_DECIMAL_RE = re.compile(r"^[+-]?[0-9]+(?:\.[0-9]+)?$")


class CalculatorToolError(Exception):
    """Base class for deterministic CalculatorTool failures."""


class CalculatorInputError(CalculatorToolError, ValueError):
    """The tool call violates the public input contract."""


class EmptyExpressionError(CalculatorInputError):
    """The expression is empty or whitespace-only."""


class InvalidExpressionSyntaxError(CalculatorInputError):
    """The expression is not valid CalculatorTool grammar."""


class UnsupportedExpressionError(CalculatorInputError):
    """The expression requests syntax or an operation outside v0.1."""


class MissingVariableError(CalculatorInputError):
    """The expression references a variable absent from the input mapping."""


class InvalidVariableNameError(CalculatorInputError):
    """An input mapping key is not a conservative ASCII identifier."""


class UnusedInputError(CalculatorInputError):
    """A supplied input is not referenced by the expression."""


class LiteralOnlyExpressionError(CalculatorInputError):
    """The expression has no named input and therefore no input audit trail."""


class MalformedDecimalError(CalculatorInputError):
    """An input value is not a supported exact decimal string."""


class NonFiniteInputError(CalculatorInputError):
    """An input is NaN or infinite."""


class CalculatorMetadataError(CalculatorInputError):
    """Opaque metadata cannot be represented safely in the canonical trace."""


class CalculatorResourceLimitError(CalculatorInputError):
    """An expression, input set, or decimal exceeds a frozen v0.1 limit."""


class CalculatorArithmeticError(CalculatorToolError, ArithmeticError):
    """Base class for deterministic arithmetic failures."""


class CalculatorDivisionByZeroError(CalculatorArithmeticError, ZeroDivisionError):
    """The expression attempts division by zero."""


class NonFiniteResultError(CalculatorArithmeticError):
    """Evaluation did not produce a finite Decimal result."""


@dataclass(frozen=True)
class CalculationInput:
    """One exact decimal input plus caller-owned opaque audit metadata."""

    value: str
    unit: str | None = None
    basis: str | None = None
    period: str | None = None
    provenance: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"value": self.value}
        if self.unit is not None:
            payload["unit"] = self.unit
        if self.basis is not None:
            payload["basis"] = self.basis
        if self.period is not None:
            payload["period"] = self.period
        if self.provenance is not None:
            payload["provenance"] = copy.deepcopy(dict(self.provenance))
        return payload


@dataclass(frozen=True)
class CalculationInputRecord:
    """Validated input as represented in a response and audit trace."""

    name: str
    value: str
    normalized_value: str
    unit: str | None
    basis: str | None
    period: str | None
    provenance: Mapping[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "value": self.value,
            "normalized_value": self.normalized_value,
        }
        if self.unit is not None:
            payload["unit"] = self.unit
        if self.basis is not None:
            payload["basis"] = self.basis
        if self.period is not None:
            payload["period"] = self.period
        if self.provenance is not None:
            payload["provenance"] = copy.deepcopy(dict(self.provenance))
        return payload


@dataclass(frozen=True)
class CalculationTrace:
    """Deterministic, timestamp-free audit trace for one calculation."""

    tool_name: str
    tool_version: str
    expression: str
    normalized_expression: str
    input_names: tuple[str, ...]
    inputs: tuple[CalculationInputRecord, ...]
    used_input_names: tuple[str, ...]
    result: str
    decimal_context: Mapping[str, Any]
    result_metadata: Mapping[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "expression": self.expression,
            "normalized_expression": self.normalized_expression,
            "input_names": list(self.input_names),
            "inputs": [item.to_dict() for item in self.inputs],
            "used_input_names": list(self.used_input_names),
            "result": self.result,
            "decimal_context": copy.deepcopy(dict(self.decimal_context)),
            "result_metadata": (
                None
                if self.result_metadata is None
                else copy.deepcopy(dict(self.result_metadata))
            ),
        }
        return payload

    def canonical_json(self) -> str:
        return canonical_calculation_trace_json(self)


@dataclass(frozen=True)
class CalculationResponse:
    """Public CalculatorTool v0.1 response."""

    tool_version: str
    expression: str
    normalized_expression: str
    inputs: tuple[CalculationInputRecord, ...]
    used_input_names: tuple[str, ...]
    result: str
    result_metadata: Mapping[str, Any] | None
    trace: CalculationTrace

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_version": self.tool_version,
            "expression": self.expression,
            "normalized_expression": self.normalized_expression,
            "inputs": [item.to_dict() for item in self.inputs],
            "used_input_names": list(self.used_input_names),
            "result": self.result,
            "result_metadata": (
                None
                if self.result_metadata is None
                else copy.deepcopy(dict(self.result_metadata))
            ),
            "trace": self.trace.to_dict(),
        }


def canonical_calculation_trace_json(
    trace: CalculationTrace | Mapping[str, Any],
) -> str:
    """Return canonical UTF-8-compatible JSON text suitable for hashing."""
    payload = trace.to_dict() if isinstance(trace, CalculationTrace) else dict(trace)
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ) + "\n"


@dataclass(frozen=True)
class _Token:
    kind: str
    text: str
    position: int


@dataclass(frozen=True)
class _LiteralNode:
    value: Decimal


@dataclass(frozen=True)
class _NameNode:
    name: str


@dataclass(frozen=True)
class _UnaryNode:
    operator: str
    operand: "_ExpressionNode"


@dataclass(frozen=True)
class _BinaryNode:
    operator: str
    left: "_ExpressionNode"
    right: "_ExpressionNode"


_ExpressionNode = _LiteralNode | _NameNode | _UnaryNode | _BinaryNode


def _tokenize(expression: str) -> tuple[_Token, ...]:
    tokens: list[_Token] = []
    position = 0
    while position < len(expression):
        character = expression[position]
        if character.isspace():
            position += 1
            continue
        if character.isascii() and (character.isalpha() or character == "_"):
            end = position + 1
            while end < len(expression):
                next_character = expression[end]
                if not (
                    next_character.isascii()
                    and (next_character.isalnum() or next_character == "_")
                ):
                    break
                end += 1
            tokens.append(_Token("NAME", expression[position:end], position))
            position = end
            continue
        if character.isascii() and character.isdigit():
            end = position + 1
            while end < len(expression) and expression[end].isascii() and expression[end].isdigit():
                end += 1
            if end < len(expression) and expression[end] == ".":
                decimal_point = end
                end += 1
                fraction_start = end
                while end < len(expression) and expression[end].isascii() and expression[end].isdigit():
                    end += 1
                if end == fraction_start:
                    raise InvalidExpressionSyntaxError(
                        f"decimal literal requires digits after '.' at position {decimal_point}"
                    )
            tokens.append(_Token("NUMBER", expression[position:end], position))
            position = end
            continue
        two_characters = expression[position : position + 2]
        if two_characters in {"**", "//", "==", "!=", "<=", ">=", ":="}:
            raise UnsupportedExpressionError(
                f"unsupported operator {two_characters!r} at position {position}"
            )
        if character in "+-*/":
            tokens.append(_Token("OP", character, position))
            position += 1
            continue
        if character == "(":
            tokens.append(_Token("LPAREN", character, position))
            position += 1
            continue
        if character == ")":
            tokens.append(_Token("RPAREN", character, position))
            position += 1
            continue
        if character in ".[]{}=<>!,:;%^&|~":
            raise UnsupportedExpressionError(
                f"unsupported syntax {character!r} at position {position}"
            )
        raise InvalidExpressionSyntaxError(
            f"invalid character {character!r} at position {position}"
        )
    tokens.append(_Token("EOF", "", len(expression)))
    return tuple(tokens)


class _ExpressionParser:
    def __init__(self, expression: str) -> None:
        self._tokens = _tokenize(expression)
        self._index = 0
        self._node_count = 0

    @property
    def current(self) -> _Token:
        return self._tokens[self._index]

    def parse(self) -> _ExpressionNode:
        node = self._parse_expression(parenthesis_depth=0)
        if self.current.kind != "EOF":
            raise InvalidExpressionSyntaxError(
                f"unexpected token {self.current.text!r} at position {self.current.position}"
            )
        if _expression_depth(node) > MAX_EXPRESSION_DEPTH:
            raise CalculatorResourceLimitError(
                f"expression exceeds maximum depth {MAX_EXPRESSION_DEPTH}"
            )
        return node

    def _new_node(self, node: _ExpressionNode) -> _ExpressionNode:
        self._node_count += 1
        if self._node_count > MAX_EXPRESSION_NODES:
            raise CalculatorResourceLimitError(
                f"expression exceeds maximum node count {MAX_EXPRESSION_NODES}"
            )
        return node

    def _advance(self) -> _Token:
        token = self.current
        self._index += 1
        return token

    def _parse_expression(self, parenthesis_depth: int) -> _ExpressionNode:
        node = self._parse_term(parenthesis_depth)
        while self.current.kind == "OP" and self.current.text in {"+", "-"}:
            operator = self._advance().text
            right = self._parse_term(parenthesis_depth)
            node = self._new_node(_BinaryNode(operator, node, right))
        return node

    def _parse_term(self, parenthesis_depth: int) -> _ExpressionNode:
        node = self._parse_unary(parenthesis_depth)
        while self.current.kind == "OP" and self.current.text in {"*", "/"}:
            operator = self._advance().text
            right = self._parse_unary(parenthesis_depth)
            node = self._new_node(_BinaryNode(operator, node, right))
        return node

    def _parse_unary(self, parenthesis_depth: int) -> _ExpressionNode:
        operators: list[str] = []
        while self.current.kind == "OP" and self.current.text in {"+", "-"}:
            operators.append(self._advance().text)
            if len(operators) >= MAX_EXPRESSION_DEPTH:
                raise CalculatorResourceLimitError(
                    f"expression exceeds maximum depth {MAX_EXPRESSION_DEPTH}"
                )
        node = self._parse_primary(parenthesis_depth)
        for operator in reversed(operators):
            node = self._new_node(_UnaryNode(operator, node))
        return node

    def _parse_primary(self, parenthesis_depth: int) -> _ExpressionNode:
        token = self.current
        if token.kind == "NUMBER":
            self._advance()
            return self._new_node(_LiteralNode(Decimal(token.text)))
        if token.kind == "NAME":
            self._advance()
            if self.current.kind == "LPAREN":
                raise UnsupportedExpressionError(
                    f"function calls are unsupported at position {token.position}"
                )
            return self._new_node(_NameNode(token.text))
        if token.kind == "LPAREN":
            if parenthesis_depth + 1 > MAX_EXPRESSION_DEPTH:
                raise CalculatorResourceLimitError(
                    f"expression exceeds maximum depth {MAX_EXPRESSION_DEPTH}"
                )
            self._advance()
            node = self._parse_expression(parenthesis_depth + 1)
            if self.current.kind != "RPAREN":
                raise InvalidExpressionSyntaxError(
                    f"missing ')' for '(' at position {token.position}"
                )
            self._advance()
            return node
        if token.kind == "EOF":
            raise InvalidExpressionSyntaxError("expression ended where an operand was required")
        raise InvalidExpressionSyntaxError(
            f"unexpected token {token.text!r} at position {token.position}"
        )


def _expression_depth(root: _ExpressionNode) -> int:
    maximum = 0
    pending: list[tuple[_ExpressionNode, int]] = [(root, 1)]
    while pending:
        node, depth = pending.pop()
        maximum = max(maximum, depth)
        if isinstance(node, _UnaryNode):
            pending.append((node.operand, depth + 1))
        elif isinstance(node, _BinaryNode):
            pending.append((node.left, depth + 1))
            pending.append((node.right, depth + 1))
    return maximum


def _used_names(root: _ExpressionNode) -> tuple[str, ...]:
    names: set[str] = set()
    pending = [root]
    while pending:
        node = pending.pop()
        if isinstance(node, _NameNode):
            names.add(node.name)
        elif isinstance(node, _UnaryNode):
            pending.append(node.operand)
        elif isinstance(node, _BinaryNode):
            pending.append(node.right)
            pending.append(node.left)
    return tuple(sorted(names))


def _canonical_decimal(value: Decimal) -> str:
    if not value.is_finite():
        raise NonFiniteResultError("calculation result is not finite")
    if value.is_zero():
        return "0"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _normalized_expression(node: _ExpressionNode) -> str:
    if isinstance(node, _LiteralNode):
        return _canonical_decimal(node.value)
    if isinstance(node, _NameNode):
        return node.name
    if isinstance(node, _UnaryNode):
        return f"({node.operator}{_normalized_expression(node.operand)})"
    return (
        f"({_normalized_expression(node.left)} {node.operator} "
        f"{_normalized_expression(node.right)})"
    )


def _evaluate(
    node: _ExpressionNode,
    values: Mapping[str, Decimal],
    context: Context,
) -> Decimal:
    if isinstance(node, _LiteralNode):
        return node.value
    if isinstance(node, _NameNode):
        return values[node.name]
    if isinstance(node, _UnaryNode):
        operand = _evaluate(node.operand, values, context)
        return context.plus(operand) if node.operator == "+" else context.minus(operand)

    left = _evaluate(node.left, values, context)
    right = _evaluate(node.right, values, context)
    if node.operator == "+":
        return context.add(left, right)
    if node.operator == "-":
        return context.subtract(left, right)
    if node.operator == "*":
        return context.multiply(left, right)
    if right.is_zero():
        raise CalculatorDivisionByZeroError("division by zero")
    return context.divide(left, right)


def _copy_json_metadata(value: Mapping[str, Any], *, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise CalculatorMetadataError(f"{label} must be a mapping")

    def validate(item: Any, path: str, ancestors: set[int]) -> None:
        if item is None or isinstance(item, (str, bool, int)):
            return
        if isinstance(item, float):
            raise CalculatorMetadataError(
                f"{path} contains a float; metadata numbers must be exact integers or strings"
            )
        if isinstance(item, Mapping):
            identity = id(item)
            if identity in ancestors:
                raise CalculatorMetadataError(f"{path} contains a cycle")
            ancestors.add(identity)
            for key, nested in item.items():
                if not isinstance(key, str):
                    raise CalculatorMetadataError(f"{path} contains a non-string key")
                validate(nested, f"{path}.{key}", ancestors)
            ancestors.remove(identity)
            return
        if isinstance(item, (list, tuple)):
            identity = id(item)
            if identity in ancestors:
                raise CalculatorMetadataError(f"{path} contains a cycle")
            ancestors.add(identity)
            for index, nested in enumerate(item):
                validate(nested, f"{path}[{index}]", ancestors)
            ancestors.remove(identity)
            return
        raise CalculatorMetadataError(
            f"{path} has unsupported metadata type {type(item).__name__}"
        )

    validate(value, label, set())
    copied = copy.deepcopy(dict(value))
    try:
        json.dumps(copied, ensure_ascii=False, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError, RecursionError) as error:
        raise CalculatorMetadataError(f"{label} is not canonical-JSON-safe") from error
    return copied


class CalculatorTool:
    """Evaluate the frozen CalculatorTool v0.1 arithmetic language."""

    def calculate(
        self,
        expression: str,
        inputs: Mapping[str, CalculationInput],
        *,
        result_metadata: Mapping[str, Any] | None = None,
    ) -> CalculationResponse:
        """Calculate an expression without selecting or interpreting its inputs."""
        if not isinstance(expression, str):
            raise InvalidExpressionSyntaxError("expression must be a string")
        if not expression.strip():
            raise EmptyExpressionError("expression must be non-empty")
        if len(expression) > MAX_EXPRESSION_CHARACTERS:
            raise CalculatorResourceLimitError(
                "expression exceeds maximum character count "
                f"{MAX_EXPRESSION_CHARACTERS}"
            )
        if not isinstance(inputs, Mapping):
            raise CalculatorInputError("inputs must be a mapping")
        if len(inputs) > MAX_VARIABLES:
            raise CalculatorResourceLimitError(
                f"inputs exceed maximum variable count {MAX_VARIABLES}"
            )

        root = _ExpressionParser(expression).parse()
        used_input_names = _used_names(root)
        if not used_input_names:
            raise LiteralOnlyExpressionError(
                "expression must reference at least one named input"
            )
        if len(used_input_names) > MAX_VARIABLES:
            raise CalculatorResourceLimitError(
                f"expression exceeds maximum variable count {MAX_VARIABLES}"
            )

        values: dict[str, Decimal] = {}
        records_by_name: dict[str, CalculationInputRecord] = {}
        for name, calculation_input in inputs.items():
            if not isinstance(name, str) or not _IDENTIFIER_RE.fullmatch(name):
                raise InvalidVariableNameError(
                    f"invalid variable name {name!r}; expected [A-Za-z_][A-Za-z0-9_]*"
                )
            if not isinstance(calculation_input, CalculationInput):
                raise CalculatorInputError(
                    f"input {name!r} must be a CalculationInput"
                )
            if not isinstance(calculation_input.value, str):
                raise MalformedDecimalError(
                    f"input {name!r} value must be an exact decimal string"
                )
            if len(calculation_input.value) > MAX_DECIMAL_CHARACTERS:
                raise CalculatorResourceLimitError(
                    f"input {name!r} exceeds maximum decimal character count "
                    f"{MAX_DECIMAL_CHARACTERS}"
                )
            try:
                value = Decimal(calculation_input.value)
            except InvalidOperation as error:
                raise MalformedDecimalError(
                    f"input {name!r} is not a decimal string"
                ) from error
            if not value.is_finite():
                raise NonFiniteInputError(f"input {name!r} must be finite")
            if not _INPUT_DECIMAL_RE.fullmatch(calculation_input.value):
                raise MalformedDecimalError(
                    f"input {name!r} must use plain decimal notation"
                )
            for field_name in ("unit", "basis", "period"):
                field_value = getattr(calculation_input, field_name)
                if field_value is not None and not isinstance(field_value, str):
                    raise CalculatorInputError(
                        f"input {name!r} {field_name} must be a string or None"
                    )
            provenance = (
                None
                if calculation_input.provenance is None
                else _copy_json_metadata(
                    calculation_input.provenance,
                    label=f"input {name!r} provenance",
                )
            )
            values[name] = value
            records_by_name[name] = CalculationInputRecord(
                name=name,
                value=calculation_input.value,
                normalized_value=_canonical_decimal(value),
                unit=calculation_input.unit,
                basis=calculation_input.basis,
                period=calculation_input.period,
                provenance=provenance,
            )

        supplied_names = set(values)
        used_names = set(used_input_names)
        missing = sorted(used_names - supplied_names)
        if missing:
            raise MissingVariableError(
                "missing input variable(s): " + ", ".join(missing)
            )
        unused = sorted(supplied_names - used_names)
        if unused:
            raise UnusedInputError("unused input variable(s): " + ", ".join(unused))

        copied_result_metadata = (
            None
            if result_metadata is None
            else _copy_json_metadata(result_metadata, label="result_metadata")
        )
        try:
            with localcontext(_DECIMAL_CONTEXT) as context:
                result_decimal = _evaluate(root, values, context)
        except CalculatorDivisionByZeroError:
            raise
        except DivisionByZero as error:
            raise CalculatorDivisionByZeroError("division by zero") from error
        except DecimalException as error:
            raise CalculatorArithmeticError(
                f"decimal arithmetic failed: {type(error).__name__}"
            ) from error

        result = _canonical_decimal(result_decimal)
        input_names = tuple(sorted(records_by_name))
        records = tuple(records_by_name[name] for name in input_names)
        normalized_expression = _normalized_expression(root)
        trace = CalculationTrace(
            tool_name=TOOL_NAME,
            tool_version=TOOL_VERSION,
            expression=expression,
            normalized_expression=normalized_expression,
            input_names=input_names,
            inputs=records,
            used_input_names=used_input_names,
            result=result,
            decimal_context={
                "precision": DECIMAL_PRECISION,
                "rounding": DECIMAL_ROUNDING,
            },
            result_metadata=copied_result_metadata,
        )
        return CalculationResponse(
            tool_version=TOOL_VERSION,
            expression=expression,
            normalized_expression=normalized_expression,
            inputs=records,
            used_input_names=used_input_names,
            result=result,
            result_metadata=copied_result_metadata,
            trace=trace,
        )
