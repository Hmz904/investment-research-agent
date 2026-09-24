"""Contract tests for agent_output_schema_v0.1.1.

Fixtures are synthetic and do not use DEV or locked-TEST examples.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "evaluation" / "agent_output_schema_v0.1.1.json"
V0_SCHEMA_PATH = ROOT / "evaluation" / "agent_output_schema_v0.1.json"
CASES_PATH = ROOT / "tests" / "fixtures" / "agent_output_schema_v0.1.1_provenance_cases.json"
COMPAT_PATHS = (
    ROOT / "tests" / "fixtures" / "agent_output_v0.1_chunk_only.json",
    ROOT / "tests" / "fixtures" / "agent_output_v0.1_chunk_calculation.json",
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


SCHEMA = _load(SCHEMA_PATH)
CASES = _load(CASES_PATH)
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


def _claim_output(provenance: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "agent_output_v0.1.1",
        "q_id": "FIXTURE_SCHEMA_001",
        "answer": "Synthetic fixture answer.",
        "answer_claim_ids": ["C001"],
        "claims": [
            {
                "claim_id": "C001",
                "text": "Synthetic fixture claim.",
                "claim_type": "factual",
                "entities": ["Fixture Entity"],
                "material": True,
                "period": "fixture period",
                "requires_citation": True,
                "temporal_role": "current",
                "provenance": provenance,
            }
        ],
        "calculations": [],
    }


def _calculation_output(provenance: dict[str, Any]) -> dict[str, Any]:
    output = _claim_output([copy.deepcopy(provenance)])
    output["claims"][0].update(
        {
            "claim_type": "numeric",
            "numeric_value": {
                "value": 20,
                "unit": "USD",
                "period": "fixture period",
                "basis": "fixture basis",
                "display_value": "$20",
            },
            "calculation_ids": ["K001"],
        }
    )
    output["calculations"] = [
        {
            "calculation_id": "K001",
            "expression": "I001 * 2",
            "inputs": [
                {
                    "input_id": "I001",
                    "name": "fixture input",
                    "value": 10,
                    "unit": "USD",
                    "period": "fixture period",
                    "basis": "fixture basis",
                    "source_type": "cited_fact",
                    "provenance": [copy.deepcopy(provenance)],
                }
            ],
            "result": {"value": 20, "unit": "USD", "display_value": "$20"},
        }
    ]
    return output


def _errors(instance: dict[str, Any]) -> list[str]:
    return [error.message for error in VALIDATOR.iter_errors(instance)]


def test_schema_is_valid_draft_2020_12() -> None:
    Draft202012Validator.check_schema(SCHEMA)


@pytest.mark.parametrize("case_name", sorted(CASES["valid"]))
def test_valid_claim_provenance_fixtures(case_name: str) -> None:
    assert _errors(_claim_output([CASES["valid"][case_name]])) == []


@pytest.mark.parametrize("case_name", sorted(CASES["invalid"]))
def test_invalid_claim_provenance_fixtures(case_name: str) -> None:
    assert _errors(_claim_output([CASES["invalid"][case_name]])), case_name


def test_claim_accepts_multiple_distinct_provenance_records() -> None:
    records = [
        CASES["valid"]["narrative"],
        CASES["valid"]["xbrl_instant_without_chunk"],
    ]
    assert _errors(_claim_output(records)) == []


def test_legacy_only_claim_is_valid() -> None:
    payload = _load(COMPAT_PATHS[0])
    payload["schema_version"] = "agent_output_v0.1.1"
    assert "provenance" not in payload["claims"][0]
    assert _errors(payload) == []


def test_new_provenance_only_claim_is_valid() -> None:
    payload = _claim_output([CASES["valid"]["narrative"]])
    assert "citations" not in payload["claims"][0]
    assert _errors(payload) == []


@pytest.mark.parametrize("equivalent", [False, True], ids=["contradictory", "equivalent"])
def test_dual_claim_representations_are_rejected(equivalent: bool) -> None:
    narrative = copy.deepcopy(CASES["valid"]["narrative"])
    payload = _claim_output([narrative])
    legacy = {
        "chunk_id": narrative["chunk_id"] if equivalent else "contradictory_chunk",
        "accession": narrative["accession"],
        "locator": narrative["locator"],
    }
    payload["claims"][0]["citations"] = [legacy]
    assert _errors(payload)


@pytest.mark.parametrize(
    "case_name",
    ["narrative", "xbrl_duration_without_chunk"],
)
def test_calculation_input_accepts_each_provenance_type(case_name: str) -> None:
    assert _errors(_calculation_output(CASES["valid"][case_name])) == []


def test_xbrl_calculation_input_does_not_require_narrative_citation() -> None:
    output = _calculation_output(CASES["valid"]["xbrl_instant_without_chunk"])
    assert "citations" not in output["calculations"][0]["inputs"][0]
    assert _errors(output) == []


@pytest.mark.parametrize("equivalent", [False, True], ids=["contradictory", "equivalent"])
def test_dual_calculation_input_representations_are_rejected(equivalent: bool) -> None:
    narrative = copy.deepcopy(CASES["valid"]["narrative"])
    output = _calculation_output(narrative)
    legacy = {
        "chunk_id": narrative["chunk_id"] if equivalent else "contradictory_chunk",
        "accession": narrative["accession"],
        "locator": narrative["locator"],
    }
    output["calculations"][0]["inputs"][0]["citations"] = [legacy]
    assert _errors(output)


@pytest.mark.parametrize("case_name", ["xbrl_null_unit", "xbrl_empty_unit"])
def test_nonnumeric_xbrl_unit_shapes_are_rejected(case_name: str) -> None:
    assert _errors(_claim_output([CASES["invalid"][case_name]]))


@pytest.mark.parametrize("compat_path", COMPAT_PATHS, ids=lambda path: path.stem)
def test_v0_1_chunk_only_output_remains_valid_after_version_adaptation(
    compat_path: Path,
) -> None:
    v0_payload = _load(compat_path)
    Draft202012Validator(
        _load(V0_SCHEMA_PATH), format_checker=FormatChecker()
    ).validate(v0_payload)

    adapted = copy.deepcopy(v0_payload)
    adapted["schema_version"] = "agent_output_v0.1.1"
    assert _errors(adapted) == []


def test_discriminator_definitions_have_closed_shapes() -> None:
    defs = SCHEMA["$defs"]
    assert defs["provenance"]["oneOf"] == [
        {"$ref": "#/$defs/narrative_provenance"},
        {"$ref": "#/$defs/xbrl_fact_provenance"},
    ]
    assert defs["narrative_provenance"]["additionalProperties"] is False
    assert defs["xbrl_fact_provenance"]["additionalProperties"] is False
