from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from evaluation.build_dev_xbrl_mapping_v0_1_2_diagnostic import (
    HUMAN_REVIEW_PATH,
    render_artifacts as render_dev,
)
from evaluation.build_temporal_context_catalog import (
    CATALOG_PATH,
    CONFLICT_REVIEW_PATH,
    REVIEW_PATH,
    RULE_REVIEW_PATH,
    render_artifacts as render_catalog,
)
from evaluation.validate_temporal_mapping import render_artifacts as render_pseudo


def test_temporal_catalog_and_blank_review_are_current() -> None:
    rendered = render_catalog()
    for path, content in rendered.items():
        assert path.read_bytes() == content
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    assert len(catalog["rows"]) == 2505
    assert catalog["duplicate_temporal_row_ids"] == []
    assert catalog["table_period_provenance_audit"] == {
        "inferred_table_rows_preserved_by_xbrl_agreement": 266,
        "month_only_rows_preserved_by_xbrl_agreement": 0,
        "prior_month_only_authoritative_rows": 191,
        "prior_month_only_rows_removed": 191,
        "prior_table_cell_exact_period_classification": {
            "EXPLICIT_EXACT": 44,
            "INGESTION_DERIVED_OR_INFERRED": 257,
            "UNCLEAR": 0,
        },
        "prior_table_cell_exact_period_recoverable_via_xbrl_agreement": 0,
        "prior_table_cell_exact_period_removed_fail_closed": 257,
        "prior_table_cell_exact_period_retained": 44,
        "prior_table_cell_exact_period_rows": 301,
    }
    with REVIEW_PATH.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert all(row["human_review_status"] == "" for row in rows)
    assert all(row["human_review_notes"] == "" for row in rows)
    assert all(row["reviewer_identity"] == "" for row in rows)


def test_dev_v0_1_2_outputs_are_current_and_do_not_parse_labels() -> None:
    rendered = render_dev()
    for path, content in rendered.items():
        assert path.read_bytes() == content
        if path.suffix == ".json":
            assert json.loads(content)["human_readable_period_labels_used"] is False
    mapping = json.loads(next(content for path, content in rendered.items() if "mapping_candidates" in path.name))
    temporal = json.loads(next(content for path, content in rendered.items() if "temporal_resolution" in path.name))
    assert len(mapping["formerly_temporal_blocked_target_ids"]) == 6
    assert all(target["human_review_status"] == "" for target in mapping["targets"])
    by_id = {target["target_id"]: target for target in mapping["targets"]}
    assert by_id["NF001"]["unmappable_reason_code"] == "TEMPORAL_NO_ANCHOR_METADATA"
    assert by_id["NF002"]["unmappable_reason_code"] == "TEMPORAL_NO_ANCHOR_METADATA"
    for target_id in ("NF001", "NF002", "NF005", "NF006", "NF007", "NF008"):
        assert by_id[target_id]["final_mapping_state"] == "PROPOSED_UNMAPPABLE"
        assert by_id[target_id]["unmappable_reason_code"] == "TEMPORAL_NO_ANCHOR_METADATA"
    for target_id in ("NF012", "NF013"):
        assert by_id[target_id]["final_mapping_state"] == "PENDING_TEMPORAL_ADJUDICATION"
        assert by_id[target_id]["candidate_discovery_state"] == "CANDIDATES_DISCOVERED_SOURCE_CHECK_PASS"
        assert by_id[target_id]["source_check_state"]["SOURCE_CHECK_PASS"] == 1
        assert by_id[target_id]["stage_completion"]["stage3"] == "blocked_missing_exact_temporal_requirement"
    temporal_by_id = {target["target_id"]: target for target in temporal["targets"]}
    assert all(len(temporal_by_id[target_id]["closed_candidates"]) == 4 for target_id in ("NF012", "NF013"))
    assert all(
        candidate["contributing_temporal_row_ids"]
        for target_id in ("NF012", "NF013")
        for candidate in temporal_by_id[target_id]["closed_candidates"]
    )

    with HUMAN_REVIEW_PATH.open(newline="", encoding="utf-8") as handle:
        review_rows = list(csv.DictReader(handle))
    assert {row["target_id"] for row in review_rows} == {"NF012", "NF013"}
    assert len(review_rows) == 8
    assert all(row["allowed_decisions"] == "SELECT <temporal_candidate_id>|SELECT NONE" for row in review_rows)
    assert all(json.loads(row["contributing_temporal_row_ids"]) for row in review_rows)
    assert {
        row["target_id"]: row["human_temporal_decision"]
        for row in review_rows
    } == {
        "NF012": "SELECT TCC-31b1f6eab46385db",
        "NF013": "SELECT TCC-f5206ab8eb1933a4",
    }
    assert all(row["human_temporal_notes"] == "" for row in review_rows)


def test_rule_and_conflict_review_artifacts_are_deterministic_and_reviewed() -> None:
    assert render_catalog() == render_catalog()
    with RULE_REVIEW_PATH.open(newline="", encoding="utf-8") as handle:
        rules = list(csv.DictReader(handle))
    assert {row["rule_id"] for row in rules} == {
        "xbrl_context_exact_dates_v0.1",
        "table_cell_exact_period_v0.1",
        "table_duration_end_months_to_start_v0.1",
        "table_xbrl_agreement_v0.1",
    }
    retired = next(row for row in rules if row["rule_id"] == "table_duration_end_months_to_start_v0.1")
    assert retired["authoritative_generator_status"] == "RETIRED_UNSAFE_FOR_AUTHORITATIVE_TEMPORAL_ROWS"
    assert retired["prior_catalog_row_count"] == "191"
    assert retired["catalog_row_count"] == "0"
    assert {
        row["rule_id"]: row["human_rule_decision"] for row in rules
    } == {
        "table_cell_exact_period_v0.1": "APPROVE",
        "table_duration_end_months_to_start_v0.1": (
            "RETIRED / REJECT AS AUTHORITATIVE TEMPORAL RULE"
        ),
        "table_xbrl_agreement_v0.1": "APPROVE",
        "xbrl_context_exact_dates_v0.1": "APPROVE",
    }
    assert all(row["human_rule_notes"] == "" for row in rules)
    with CONFLICT_REVIEW_PATH.open(newline="", encoding="utf-8") as handle:
        conflicts = list(csv.DictReader(handle))
    assert len(conflicts) == 10
    assert Counter(row["conflict_type"] for row in conflicts) == {
        "LINKED_XBRL_DIMENSION_CONFLICT": 5,
        "TABLE_COLUMN_PERIOD_METADATA_CONFLICT": 5,
    }
    assert all(
        row["human_conflict_classification"] == "APPROVE CLASSIFICATION"
        for row in conflicts
    )
    assert all(
        row["human_review_notes"] == "APPROVE FAIL-CLOSED HANDLING"
        for row in conflicts
    )


def test_catalog_review_completion_contract_has_three_layers() -> None:
    spec = Path("evaluation/temporal_context_catalog_spec_v0.1.md").read_text(encoding="utf-8")
    assert "Layer A — generation-rule families" in spec
    assert "Layer B — rows actually used for target adjudication" in spec
    assert "Layer C — deterministic conflict sample" in spec
    assert "first `min(5, group_size)`" in spec


def test_pseudo_v0_2_is_deterministic_and_has_natural_dimensional_stage3() -> None:
    first = render_pseudo()
    second = render_pseudo()
    assert first == second
    for path, content in first.items():
        assert path.read_bytes() == content
    selection = json.loads(next(content for path, content in first.items() if "selection" in path.name))
    assert [row["category"][0] for row in selection["selections"]] == list("ABCDEFGHI")
    category_i = selection["selections"][-1]
    assert category_i["selection_status"].startswith("SELECTED")
    validation = json.loads(next(content for path, content in first.items() if "validation" in path.name))
    result_i = validation["results"][-1]["targets"][0]
    assert result_i["stage1_candidates"] == []
    assert result_i["stage3_state"] == "completed"
    assert result_i["stage3_candidates"]
