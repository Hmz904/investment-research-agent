"""Static alignment checks for the proposed agent evaluation contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]


def _load(relative_path: str) -> dict[str, Any]:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def test_manifest_pins_required_evaluation_and_runtime_identities() -> None:
    schema = _load("evaluation/agent_manifest_schema_v0.1.json")
    Draft202012Validator.check_schema(schema)

    required = set(schema["required"])
    assert {"system_prompt", "tool_contract", "output_schema", "evaluation_contract"} <= required
    assert schema["properties"]["output_schema"]["properties"]["version"]["const"] == "agent_output_v0.1.1"
    evaluation = schema["properties"]["evaluation_contract"]
    assert evaluation["properties"]["eval_protocol_version"]["const"] == "eval_protocol_v0.2.1"
    tools = schema["properties"]["tool_contract"]
    assert tools["properties"]["tool_runtime_version"]["const"] == "tool_runtime_v0.1"
    assert tools["properties"]["tool_trace_ledger_version"]["const"] == "tool_trace_ledger_v0.1"
    assert "tool_spec_sha256" in tools["required"]


def test_run_record_pins_prompt_protocol_schema_model_budgets_and_ledger() -> None:
    schema = _load("evaluation/agent_run_schema_v0.1.json")
    Draft202012Validator.check_schema(schema)
    canonical = schema["$defs"]["canonical_record"]
    required = set(canonical["required"])

    assert {
        "eval_protocol_version",
        "eval_protocol_sha256",
        "system_prompt_version",
        "system_prompt_sha256",
        "tool_runtime_version",
        "tool_spec_sha256",
        "output_schema_version",
        "output_schema_sha256",
        "model",
        "sampling",
        "max_tool_calls",
        "max_agent_steps",
        "tool_trace_ledger_version",
        "tool_call_ledger_sha256",
        "ordered_call_ids",
        "ordered_tool_calls",
    } <= required
    properties = canonical["properties"]
    assert properties["eval_protocol_version"]["const"] == "eval_protocol_v0.2.1"
    assert properties["tool_runtime_version"]["const"] == "tool_runtime_v0.1"
    assert properties["output_schema_version"]["const"] == "agent_output_v0.1.1"


def test_contracts_exclude_chain_of_thought_fields() -> None:
    for relative_path in (
        "evaluation/agent_manifest_schema_v0.1.json",
        "evaluation/agent_run_schema_v0.1.json",
    ):
        text = (ROOT / relative_path).read_text(encoding="utf-8").lower()
        assert "chain_of_thought" not in text
        assert '"reasoning"' not in text
