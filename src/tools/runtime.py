"""Deterministic ToolRuntime / ToolRegistry v0.1.

This module exposes only the four frozen public tool operations.  It performs
structural request validation, transparent dispatch, and common trace wrapping;
it contains no tool selection, retries, query rewriting, or agent policy.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from .calculator_tool import (
    MAX_DECIMAL_CHARACTERS,
    MAX_EXPRESSION_CHARACTERS,
    MAX_EXPRESSION_DEPTH,
    MAX_EXPRESSION_NODES,
    MAX_VARIABLES,
    CalculationInput,
    CalculatorArithmeticError,
    CalculatorTool,
    CalculatorToolError,
    TOOL_VERSION as NATIVE_CALCULATOR_TOOL_VERSION,
)
from .retrieval_tool import (
    MAX_TOP_K as RETRIEVAL_MAX_TOP_K,
    RETRIEVAL_STACK_COMMIT,
    RETRIEVAL_STACK_VERSION,
    RetrievalInputError,
    RetrievalTool,
    RetrievalToolError,
    TOOL_VERSION as NATIVE_RETRIEVAL_TOOL_VERSION,
)
from .xbrl_tool import (
    MAX_TOP_K as XBRL_MAX_TOP_K,
    XBRLInputError,
    XBRLTool,
    XBRLToolError,
    TOOL_VERSION as NATIVE_XBRL_TOOL_VERSION,
)


TOOL_RUNTIME_VERSION = "tool_runtime_v0.1"
TRACE_LEDGER_VERSION = "tool_trace_ledger_v0.1"

RETRIEVAL_TOOL_COMMIT = "cce61f3fa6b2e4f1fca548c0c931330d9de5a96c"
XBRL_TOOL_COMMIT = "d3bceec1db9d608bd702a5cf3b5329f9710697ea"
CALCULATOR_TOOL_COMMIT = "72108f24b03b3d6114f04a29366178cde9de97d9"

RETRIEVAL_TOOL_VERSION = "retrieval_tool_v0.1"
XBRL_TOOL_VERSION = "xbrl_tool_v0.1"
CALCULATOR_TOOL_VERSION = "calculator_tool_v0.1"

_CALL_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_VARIABLE_NAME_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"
_DECIMAL_PATTERN = r"^[+-]?[0-9]+(?:\.[0-9]+)?$"
_ACCESSION_PATTERN = r"^\d{10}-\d{2}-\d{6}$"
_NON_WHITESPACE_PATTERN = r".*\S.*"


class ToolRuntimeError(Exception):
    """Base class for deterministic common-runtime failures."""


class ToolCallValidationError(ToolRuntimeError, ValueError):
    """A common tool-call request is malformed."""


class UnknownToolError(ToolRuntimeError, LookupError):
    """The requested logical tool is not registered."""


class UnknownOperationError(ToolRuntimeError, LookupError):
    """The requested operation is not exposed by a registered tool."""


class ToolArgumentValidationError(ToolRuntimeError, ValueError):
    """Arguments do not satisfy the frozen machine-readable tool spec."""


class ToolDispatchError(ToolRuntimeError, RuntimeError):
    """A registered tool returned an invalid response or trace."""


class ToolVersionMismatchError(ToolRuntimeError, RuntimeError):
    """A production factory or response does not match the frozen version."""


class DuplicateCallIDError(ToolRuntimeError, ValueError):
    """A trace ledger already contains the supplied call ID."""


@dataclass(frozen=True)
class ToolSpec:
    """Machine-readable specification for one exposed operation."""

    tool_name: str
    tool_version: str
    operation: str
    description: str
    argument_schema: Mapping[str, Any]
    required_arguments: tuple[str, ...]
    optional_arguments: tuple[str, ...]
    argument_constraints: Mapping[str, Any]

    @property
    def qualified_name(self) -> str:
        return f"{self.tool_name}.{self.operation}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "operation": self.operation,
            "description": self.description,
            "argument_schema": copy.deepcopy(dict(self.argument_schema)),
            "required_arguments": list(self.required_arguments),
            "optional_arguments": list(self.optional_arguments),
            "argument_constraints": copy.deepcopy(dict(self.argument_constraints)),
        }


_EXACT_JSON_VALUE_SCHEMA: dict[str, Any] = {
    "anyOf": [
        {"type": "null"},
        {"type": "string"},
        {"type": "boolean"},
        {"type": "integer"},
        {"type": "array", "items": {"$ref": "#/$defs/exact_json_value"}},
        {
            "type": "object",
            "additionalProperties": {"$ref": "#/$defs/exact_json_value"},
        },
    ]
}

_CALCULATION_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["value"],
    "properties": {
        "value": {
            "type": "string",
            "maxLength": MAX_DECIMAL_CHARACTERS,
            "pattern": _DECIMAL_PATTERN,
        },
        "unit": {"type": ["string", "null"]},
        "basis": {"type": ["string", "null"]},
        "period": {"type": ["string", "null"]},
        "provenance": {
            "anyOf": [
                {"type": "null"},
                {
                    "type": "object",
                    "additionalProperties": {
                        "$ref": "#/$defs/exact_json_value"
                    },
                },
            ]
        },
    },
}


def _object_schema(
    properties: Mapping[str, Any],
    required: Sequence[str],
    *,
    definitions: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": copy.deepcopy(dict(properties)),
        "required": list(required),
    }
    if definitions is not None:
        schema["$defs"] = copy.deepcopy(dict(definitions))
    return schema


_TOOL_SPECS: tuple[ToolSpec, ...] = tuple(
    sorted(
        (
            ToolSpec(
                tool_name="retrieval",
                tool_version=RETRIEVAL_TOOL_VERSION,
                operation="search",
                description=(
                    "Search frozen narrative filing chunks using the frozen "
                    "retrieval stack."
                ),
                argument_schema=_object_schema(
                    {
                        "query": {
                            "type": "string",
                            "minLength": 1,
                            "pattern": _NON_WHITESPACE_PATTERN,
                        },
                        "top_k": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": RETRIEVAL_MAX_TOP_K,
                            "default": 10,
                        },
                    },
                    ("query",),
                ),
                required_arguments=("query",),
                optional_arguments=("top_k",),
                argument_constraints={
                    "additional_arguments": False,
                    "query": {"non_whitespace": True},
                    "top_k": {"minimum": 1, "maximum": RETRIEVAL_MAX_TOP_K},
                },
            ),
            ToolSpec(
                tool_name="xbrl",
                tool_version=XBRL_TOOL_VERSION,
                operation="search_concepts",
                description=(
                    "Discover exact concepts available in the frozen local XBRL "
                    "corpus."
                ),
                argument_schema=_object_schema(
                    {
                        "query": {
                            "type": "string",
                            "minLength": 1,
                            "pattern": _NON_WHITESPACE_PATTERN,
                        },
                        "top_k": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": XBRL_MAX_TOP_K,
                            "default": 10,
                        },
                    },
                    ("query",),
                ),
                required_arguments=("query",),
                optional_arguments=("top_k",),
                argument_constraints={
                    "additional_arguments": False,
                    "query": {"non_whitespace": True},
                    "top_k": {"minimum": 1, "maximum": XBRL_MAX_TOP_K},
                },
            ),
            ToolSpec(
                tool_name="xbrl",
                tool_version=XBRL_TOOL_VERSION,
                operation="query_facts",
                description=(
                    "Retrieve reported local XBRL facts for an exact concept and "
                    "optional structured filters."
                ),
                argument_schema=_object_schema(
                    {
                        "concept": {"type": "string", "minLength": 1},
                        "accession": {
                            "type": ["string", "null"],
                            "pattern": _ACCESSION_PATTERN,
                            "default": None,
                        },
                        "company": {
                            "type": ["string", "null"],
                            "minLength": 1,
                            "default": None,
                        },
                        "form_type": {
                            "type": ["string", "null"],
                            "minLength": 1,
                            "default": None,
                        },
                        "filing_fiscal_period": {
                            "type": ["string", "null"],
                            "minLength": 1,
                            "default": None,
                        },
                        "period_start": {
                            "type": ["string", "null"],
                            "format": "date",
                            "default": None,
                        },
                        "period_end": {
                            "type": ["string", "null"],
                            "format": "date",
                            "default": None,
                        },
                        "instant": {
                            "type": ["string", "null"],
                            "format": "date",
                            "default": None,
                        },
                        "unit": {
                            "type": ["string", "null"],
                            "default": None,
                        },
                        "include_dimensions": {
                            "type": "boolean",
                            "default": True,
                        },
                    },
                    ("concept",),
                ),
                required_arguments=("concept",),
                optional_arguments=(
                    "accession",
                    "company",
                    "form_type",
                    "filing_fiscal_period",
                    "period_start",
                    "period_end",
                    "instant",
                    "unit",
                    "include_dimensions",
                ),
                argument_constraints={
                    "additional_arguments": False,
                    "exact_match_filters": [
                        "concept",
                        "accession",
                        "company",
                        "form_type",
                        "filing_fiscal_period",
                        "period_start",
                        "period_end",
                        "instant",
                        "unit",
                    ],
                    "mutually_exclusive": [
                        ["instant", "period_start"],
                        ["instant", "period_end"],
                    ],
                },
            ),
            ToolSpec(
                tool_name="calculator",
                tool_version=CALCULATOR_TOOL_VERSION,
                operation="calculate",
                description=(
                    "Evaluate a restricted exact Decimal arithmetic expression over "
                    "explicitly provided numeric inputs."
                ),
                argument_schema=_object_schema(
                    {
                        "expression": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": MAX_EXPRESSION_CHARACTERS,
                            "pattern": _NON_WHITESPACE_PATTERN,
                        },
                        "inputs": {
                            "type": "object",
                            "maxProperties": MAX_VARIABLES,
                            "propertyNames": {"pattern": _VARIABLE_NAME_PATTERN},
                            "additionalProperties": _CALCULATION_INPUT_SCHEMA,
                        },
                        "result_metadata": {
                            "anyOf": [
                                {"type": "null"},
                                {
                                    "type": "object",
                                    "additionalProperties": {
                                        "$ref": "#/$defs/exact_json_value"
                                    },
                                },
                            ],
                            "default": None,
                        },
                    },
                    ("expression", "inputs"),
                    definitions={"exact_json_value": _EXACT_JSON_VALUE_SCHEMA},
                ),
                required_arguments=("expression", "inputs"),
                optional_arguments=("result_metadata",),
                argument_constraints={
                    "additional_arguments": False,
                    "expression": {
                        "non_whitespace": True,
                        "maximum_characters": MAX_EXPRESSION_CHARACTERS,
                        "maximum_nodes": MAX_EXPRESSION_NODES,
                        "maximum_depth": MAX_EXPRESSION_DEPTH,
                        "grammar": (
                            "expression := term ((+ | -) term)*; "
                            "term := unary ((* | /) unary)*; "
                            "unary := (+ | -)* primary; "
                            "primary := variable | literal | ( expression )"
                        ),
                    },
                    "input_names": {"pattern": _VARIABLE_NAME_PATTERN},
                    "input_count": {"maximum": MAX_VARIABLES},
                    "input_values": {
                        "exact_decimal_string_pattern": _DECIMAL_PATTERN,
                        "maximum_characters": MAX_DECIMAL_CHARACTERS,
                    },
                    "variable_binding": {
                        "literal_only_expression_allowed": False,
                        "all_expression_variables_required": True,
                        "unused_inputs_allowed": False,
                    },
                    "metadata_numbers": "integers_or_strings_only",
                },
            ),
        ),
        key=lambda spec: (spec.tool_name, spec.operation),
    )
)


def canonical_tool_specs_json(specs: Sequence[ToolSpec] = _TOOL_SPECS) -> str:
    """Serialize the complete tool contract deterministically with one newline."""
    ordered = sorted(specs, key=lambda spec: (spec.tool_name, spec.operation))
    payload = {
        "tool_contract_version": TOOL_RUNTIME_VERSION,
        "operations": [spec.to_dict() for spec in ordered],
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ) + "\n"


def _copy_spec(spec: ToolSpec) -> ToolSpec:
    return ToolSpec(
        tool_name=spec.tool_name,
        tool_version=spec.tool_version,
        operation=spec.operation,
        description=spec.description,
        argument_schema=copy.deepcopy(dict(spec.argument_schema)),
        required_arguments=tuple(spec.required_arguments),
        optional_arguments=tuple(spec.optional_arguments),
        argument_constraints=copy.deepcopy(dict(spec.argument_constraints)),
    )


TOOL_SPEC_SHA256 = hashlib.sha256(
    canonical_tool_specs_json().encode("utf-8")
).hexdigest()


@dataclass(frozen=True)
class ToolCallRequest:
    """One caller-identified explicit tool operation request."""

    call_id: str
    tool_name: str
    operation: str
    arguments: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.call_id, str) or not _CALL_ID_RE.fullmatch(
            self.call_id
        ):
            raise ToolCallValidationError(
                "call_id must match [A-Za-z][A-Za-z0-9_-]{0,63}"
            )
        if not isinstance(self.tool_name, str) or not self.tool_name:
            raise ToolCallValidationError("tool_name must be a non-empty string")
        if not isinstance(self.operation, str) or not self.operation:
            raise ToolCallValidationError("operation must be a non-empty string")
        if not isinstance(self.arguments, Mapping):
            raise ToolCallValidationError("arguments must be a mapping")
        try:
            copied = copy.deepcopy(dict(self.arguments))
            _canonical_json(copied)
        except (TypeError, ValueError, RecursionError) as exc:
            raise ToolCallValidationError(
                "arguments must be finite canonical-JSON-compatible values"
            ) from exc
        object.__setattr__(self, "arguments", copied)


@dataclass(frozen=True)
class ToolErrorEnvelope:
    """Deterministic, traceback-free error representation."""

    error_type: str
    error_code: str
    safe_message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "error_type": self.error_type,
            "error_code": self.error_code,
            "safe_message": self.safe_message,
        }


@dataclass(frozen=True)
class ToolInvocationResult:
    """Common envelope around exactly one completed invocation attempt."""

    call_id: str
    tool_name: str
    tool_version: str | None
    operation: str
    request_arguments: Mapping[str, Any]
    effective_arguments: Mapping[str, Any] | None
    status: Literal["success", "error"]
    result: Any | None
    tool_trace: Any | None
    tool_trace_sha256: str | None
    tool_spec_sha256: str
    frozen_dependencies: Mapping[str, str]
    error: ToolErrorEnvelope | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return the stable common record without reserializing domain results."""
        return {
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "operation": self.operation,
            "request_arguments": copy.deepcopy(dict(self.request_arguments)),
            "effective_arguments": (
                None
                if self.effective_arguments is None
                else copy.deepcopy(dict(self.effective_arguments))
            ),
            "status": self.status,
            "tool_trace_sha256": self.tool_trace_sha256,
            "tool_spec_sha256": self.tool_spec_sha256,
            "frozen_dependencies": copy.deepcopy(dict(self.frozen_dependencies)),
            "error": None if self.error is None else self.error.to_dict(),
        }

    def canonical_json(self) -> str:
        """Serialize stable identities and hashes, never the full domain result."""
        return _canonical_json(self.to_dict())


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ) + "\n"


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "object":
        return isinstance(value, Mapping)
    if expected == "array":
        return isinstance(value, (list, tuple))
    return False


def _resolve_ref(schema: Mapping[str, Any], root: Mapping[str, Any]) -> Mapping[str, Any]:
    reference = schema.get("$ref")
    if reference is None:
        return schema
    prefix = "#/$defs/"
    if not isinstance(reference, str) or not reference.startswith(prefix):
        raise ToolDispatchError(f"unsupported internal schema reference: {reference!r}")
    definition = root.get("$defs", {}).get(reference[len(prefix) :])
    if not isinstance(definition, Mapping):
        raise ToolDispatchError(f"unknown internal schema reference: {reference!r}")
    return definition


def _validate_schema(
    value: Any,
    schema: Mapping[str, Any],
    *,
    path: str,
    root: Mapping[str, Any],
) -> None:
    schema = _resolve_ref(schema, root)
    alternatives = schema.get("anyOf")
    if isinstance(alternatives, list):
        for alternative in alternatives:
            try:
                _validate_schema(value, alternative, path=path, root=root)
                return
            except ToolArgumentValidationError:
                pass
        raise ToolArgumentValidationError(f"{path} does not match an allowed type")

    declared_type = schema.get("type")
    expected_types = (
        declared_type if isinstance(declared_type, list) else [declared_type]
    )
    if declared_type is not None and not any(
        _matches_type(value, expected) for expected in expected_types
    ):
        names = ", ".join(str(item) for item in expected_types)
        raise ToolArgumentValidationError(f"{path} must have type {names}")
    if value is None:
        return

    if isinstance(value, str):
        minimum_length = schema.get("minLength")
        maximum_length = schema.get("maxLength")
        if minimum_length is not None and len(value) < minimum_length:
            raise ToolArgumentValidationError(
                f"{path} must contain at least {minimum_length} character(s)"
            )
        if maximum_length is not None and len(value) > maximum_length:
            raise ToolArgumentValidationError(
                f"{path} must contain at most {maximum_length} character(s)"
            )
        pattern = schema.get("pattern")
        if pattern is not None and re.fullmatch(pattern, value, flags=re.DOTALL) is None:
            raise ToolArgumentValidationError(f"{path} does not match {pattern}")
        if schema.get("format") == "date":
            try:
                parsed = date.fromisoformat(value)
            except ValueError as exc:
                raise ToolArgumentValidationError(
                    f"{path} must be a canonical ISO date"
                ) from exc
            if parsed.isoformat() != value:
                raise ToolArgumentValidationError(
                    f"{path} must be a canonical ISO date"
                )

    if isinstance(value, int) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ToolArgumentValidationError(
                f"{path} must be at least {schema['minimum']}"
            )
        if "maximum" in schema and value > schema["maximum"]:
            raise ToolArgumentValidationError(
                f"{path} must be at most {schema['maximum']}"
            )

    if isinstance(value, Mapping):
        if "maxProperties" in schema and len(value) > schema["maxProperties"]:
            raise ToolArgumentValidationError(
                f"{path} may contain at most {schema['maxProperties']} properties"
            )
        property_names = schema.get("propertyNames", {})
        name_pattern = property_names.get("pattern")
        if name_pattern is not None:
            for key in value:
                if not isinstance(key, str) or re.fullmatch(name_pattern, key) is None:
                    raise ToolArgumentValidationError(
                        f"{path} property name {key!r} does not match {name_pattern}"
                    )
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        missing = [name for name in required if name not in value]
        if missing:
            raise ToolArgumentValidationError(
                f"{path} missing required argument(s): {', '.join(missing)}"
            )
        additional = schema.get("additionalProperties", True)
        unknown = [name for name in value if name not in properties]
        if additional is False and unknown:
            raise ToolArgumentValidationError(
                f"{path} contains unknown argument(s): "
                + ", ".join(sorted(str(name) for name in unknown))
            )
        for key, item in value.items():
            property_schema = properties.get(key)
            if property_schema is None and isinstance(additional, Mapping):
                property_schema = additional
            if property_schema is not None:
                _validate_schema(
                    item,
                    property_schema,
                    path=f"{path}.{key}",
                    root=root,
                )

    if isinstance(value, (list, tuple)) and "items" in schema:
        for index, item in enumerate(value):
            _validate_schema(
                item, schema["items"], path=f"{path}[{index}]", root=root
            )


def _validate_arguments(spec: ToolSpec, arguments: Mapping[str, Any]) -> None:
    schema = spec.argument_schema
    _validate_schema(arguments, schema, path="arguments", root=schema)
    if spec.qualified_name == "xbrl.query_facts":
        instant = arguments.get("instant")
        if instant is not None and (
            arguments.get("period_start") is not None
            or arguments.get("period_end") is not None
        ):
            raise ToolArgumentValidationError(
                "arguments.instant cannot be combined with period_start or period_end"
            )


def _effective_arguments(
    spec: ToolSpec, request_arguments: Mapping[str, Any]
) -> dict[str, Any]:
    """Copy raw arguments and add only defaults declared by the frozen spec."""
    effective = copy.deepcopy(dict(request_arguments))
    for name, property_schema in spec.argument_schema["properties"].items():
        if name not in effective and "default" in property_schema:
            effective[name] = copy.deepcopy(property_schema["default"])
    return effective


_FROZEN_DEPENDENCIES: dict[str, dict[str, str]] = {
    "retrieval": {
        "retrieval_tool_version": RETRIEVAL_TOOL_VERSION,
        "retrieval_tool_commit": RETRIEVAL_TOOL_COMMIT,
        "retrieval_stack_version": RETRIEVAL_STACK_VERSION,
        "retrieval_stack_commit": RETRIEVAL_STACK_COMMIT,
    },
    "xbrl": {
        "xbrl_tool_version": XBRL_TOOL_VERSION,
        "xbrl_tool_commit": XBRL_TOOL_COMMIT,
    },
    "calculator": {
        "calculator_tool_version": CALCULATOR_TOOL_VERSION,
        "calculator_tool_commit": CALCULATOR_TOOL_COMMIT,
    },
}


def _error_code(tool_name: str, error: Exception) -> str:
    if isinstance(error, UnknownToolError):
        return "runtime.unknown_tool"
    if isinstance(error, UnknownOperationError):
        return "runtime.unknown_operation"
    if isinstance(error, ToolArgumentValidationError):
        return "runtime.invalid_arguments"
    if isinstance(error, ToolDispatchError):
        return "runtime.invalid_tool_response"
    if isinstance(error, ToolVersionMismatchError):
        return "runtime.tool_version_mismatch"
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", type(error).__name__).lower()
    if isinstance(error, (RetrievalToolError, XBRLToolError, CalculatorToolError)):
        return f"{tool_name}.{snake}"
    return f"{tool_name or 'runtime'}.unexpected_error"


def _safe_error_message(error: Exception) -> str:
    if isinstance(error, (ToolRuntimeError, RetrievalInputError, XBRLInputError)):
        return str(error)
    if isinstance(error, (CalculatorToolError, CalculatorArithmeticError)):
        return str(error)
    if isinstance(error, RetrievalToolError):
        return f"Frozen retrieval tool failed with {type(error).__name__}."
    if isinstance(error, XBRLToolError):
        return f"Frozen XBRL tool failed with {type(error).__name__}."
    return "The tool invocation failed with an unexpected error."


def _verify_frozen_factory_bindings() -> None:
    actual = {
        "retrieval": NATIVE_RETRIEVAL_TOOL_VERSION,
        "xbrl": NATIVE_XBRL_TOOL_VERSION,
        "calculator": NATIVE_CALCULATOR_TOOL_VERSION,
    }
    expected = {
        "retrieval": RETRIEVAL_TOOL_VERSION,
        "xbrl": XBRL_TOOL_VERSION,
        "calculator": CALCULATOR_TOOL_VERSION,
    }
    for tool_name in sorted(expected):
        if actual[tool_name] != expected[tool_name]:
            raise ToolVersionMismatchError(
                f"{tool_name} module version mismatch: "
                f"expected={expected[tool_name]} actual={actual[tool_name]}"
            )


class ToolRegistry:
    """Stable registry of preconstructed frozen tool instances."""

    def __init__(
        self,
        *,
        retrieval_tool: Any,
        xbrl_tool: Any,
        calculator_tool: Any,
        _production_frozen: bool = False,
    ) -> None:
        self._tools = {
            "retrieval": retrieval_tool,
            "xbrl": xbrl_tool,
            "calculator": calculator_tool,
        }
        self._production_frozen = _production_frozen
        self._specs = {spec.qualified_name: spec for spec in _TOOL_SPECS}
        self._runtime = ToolRuntime(self)

    @classmethod
    def from_frozen_tools(cls) -> "ToolRegistry":
        """Construct each production tool once for reuse by this registry."""
        _verify_frozen_factory_bindings()
        retrieval = RetrievalTool.from_frozen_stack()
        xbrl = XBRLTool.from_frozen_ingestion()
        calculator = CalculatorTool()
        expected_types = (
            ("retrieval", retrieval, RetrievalTool),
            ("xbrl", xbrl, XBRLTool),
            ("calculator", calculator, CalculatorTool),
        )
        for tool_name, instance, expected_type in expected_types:
            if not isinstance(instance, expected_type):
                raise ToolVersionMismatchError(
                    f"{tool_name} production factory returned "
                    f"{type(instance).__name__}, expected {expected_type.__name__}"
                )
        return cls(
            retrieval_tool=retrieval,
            xbrl_tool=xbrl,
            calculator_tool=calculator,
            _production_frozen=True,
        )

    @property
    def tool_spec_sha256(self) -> str:
        return TOOL_SPEC_SHA256

    def list_tools(self) -> tuple[ToolSpec, ...]:
        """Return all four specs in deterministic tool/operation order."""
        return tuple(_copy_spec(spec) for spec in _TOOL_SPECS)

    def get_tool_spec(
        self, name: str, operation: str | None = None
    ) -> ToolSpec:
        """Resolve ``tool.operation`` or separate tool and operation names."""
        qualified_name = name if operation is None else f"{name}.{operation}"
        spec = self._specs.get(qualified_name)
        if spec is not None:
            return _copy_spec(spec)
        tool_name = name.split(".", 1)[0]
        if tool_name not in self._tools:
            raise UnknownToolError(f"unknown tool: {tool_name}")
        requested_operation = (
            name.split(".", 1)[1]
            if operation is None and "." in name
            else operation or ""
        )
        raise UnknownOperationError(
            f"unknown operation for {tool_name}: {requested_operation}"
        )

    def invoke(self, call: ToolCallRequest) -> ToolInvocationResult:
        return self._runtime.invoke(call)


class ToolRuntime:
    """Validate and dispatch exactly one explicit request without retries."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def invoke(self, call: ToolCallRequest) -> ToolInvocationResult:
        if not isinstance(call, ToolCallRequest):
            raise ToolCallValidationError("call must be a ToolCallRequest")

        spec: ToolSpec | None = None
        effective_arguments: dict[str, Any] | None = None
        try:
            spec = self._registry.get_tool_spec(call.tool_name, call.operation)
            _validate_arguments(spec, call.arguments)
            effective_arguments = _effective_arguments(spec, call.arguments)
            native_result = self._dispatch(call, effective_arguments)
            if self._registry._production_frozen:
                native_version = getattr(native_result, "tool_version", None)
                if native_version != spec.tool_version:
                    raise ToolVersionMismatchError(
                        f"{call.tool_name} response version mismatch: "
                        f"expected={spec.tool_version} actual={native_version}"
                    )
            native_trace = getattr(native_result, "trace", None)
            if native_trace is None:
                raise ToolDispatchError("tool response does not expose a native trace")
            canonical_method = getattr(native_trace, "canonical_json", None)
            if not callable(canonical_method):
                raise ToolDispatchError(
                    "native tool trace does not expose canonical_json()"
                )
            native_trace_json = canonical_method()
            if not isinstance(native_trace_json, str):
                raise ToolDispatchError("native canonical trace must be text")
            native_trace_sha256 = hashlib.sha256(
                native_trace_json.encode("utf-8")
            ).hexdigest()
            return ToolInvocationResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                tool_version=spec.tool_version,
                operation=call.operation,
                request_arguments=copy.deepcopy(dict(call.arguments)),
                effective_arguments=copy.deepcopy(effective_arguments),
                status="success",
                result=native_result,
                tool_trace=native_trace,
                tool_trace_sha256=native_trace_sha256,
                tool_spec_sha256=TOOL_SPEC_SHA256,
                frozen_dependencies=copy.deepcopy(
                    _FROZEN_DEPENDENCIES[call.tool_name]
                ),
            )
        except Exception as error:
            tool_version = (
                spec.tool_version
                if spec is not None
                else {
                    "retrieval": RETRIEVAL_TOOL_VERSION,
                    "xbrl": XBRL_TOOL_VERSION,
                    "calculator": CALCULATOR_TOOL_VERSION,
                }.get(call.tool_name)
            )
            envelope = ToolErrorEnvelope(
                error_type=type(error).__name__,
                error_code=_error_code(call.tool_name, error),
                safe_message=_safe_error_message(error),
            )
            return ToolInvocationResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                tool_version=tool_version,
                operation=call.operation,
                request_arguments=copy.deepcopy(dict(call.arguments)),
                effective_arguments=(
                    None
                    if effective_arguments is None
                    else copy.deepcopy(effective_arguments)
                ),
                status="error",
                result=None,
                tool_trace=None,
                tool_trace_sha256=None,
                tool_spec_sha256=TOOL_SPEC_SHA256,
                frozen_dependencies=copy.deepcopy(
                    _FROZEN_DEPENDENCIES.get(call.tool_name, {})
                ),
                error=envelope,
            )

    def _dispatch(
        self, call: ToolCallRequest, effective_arguments: Mapping[str, Any]
    ) -> Any:
        tool = self._registry._tools[call.tool_name]
        arguments = copy.deepcopy(dict(effective_arguments))
        if call.tool_name == "calculator" and call.operation == "calculate":
            input_records = arguments["inputs"]
            arguments["inputs"] = {
                name: CalculationInput(**copy.deepcopy(dict(record)))
                for name, record in input_records.items()
            }
        method = getattr(tool, call.operation)
        return method(**arguments)


@dataclass
class ToolTraceLedger:
    """Append-only, call-ordered sequence of completed invocation records."""

    _records: list[ToolInvocationResult] = field(default_factory=list)
    _call_ids: set[str] = field(default_factory=set)

    @property
    def records(self) -> tuple[ToolInvocationResult, ...]:
        return tuple(self._records)

    def append(self, result: ToolInvocationResult) -> None:
        if not isinstance(result, ToolInvocationResult):
            raise TypeError("ledger records must be ToolInvocationResult instances")
        if result.call_id in self._call_ids:
            raise DuplicateCallIDError(
                f"duplicate call_id in trace ledger: {result.call_id}"
            )
        self._records.append(result)
        self._call_ids.add(result.call_id)

    def canonical_json(self) -> str:
        payload = {
            "ledger_version": TRACE_LEDGER_VERSION,
            "records": [record.to_dict() for record in self._records],
        }
        return _canonical_json(payload)

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


__all__ = [
    "CALCULATOR_TOOL_COMMIT",
    "DuplicateCallIDError",
    "RETRIEVAL_TOOL_COMMIT",
    "TOOL_RUNTIME_VERSION",
    "TOOL_SPEC_SHA256",
    "TRACE_LEDGER_VERSION",
    "ToolArgumentValidationError",
    "ToolCallRequest",
    "ToolCallValidationError",
    "ToolDispatchError",
    "ToolErrorEnvelope",
    "ToolInvocationResult",
    "ToolRegistry",
    "ToolRuntime",
    "ToolRuntimeError",
    "ToolSpec",
    "ToolTraceLedger",
    "ToolVersionMismatchError",
    "UnknownOperationError",
    "UnknownToolError",
    "XBRL_TOOL_COMMIT",
    "canonical_tool_specs_json",
]
