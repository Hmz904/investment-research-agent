from __future__ import annotations

import json

from evaluation.materialize_dev_xbrl_map_v0_1 import (
    COVERAGE_PATH,
    MAP_PATH,
    render_artifacts,
)


def test_final_dev_xbrl_map_is_current_and_deterministic() -> None:
    first = render_artifacts()
    second = render_artifacts()
    assert first == second
    assert all(path.read_bytes() == content for path, content in first.items())


def test_final_dev_xbrl_map_applies_only_authorized_human_decisions() -> None:
    final_map = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    assert final_map["final_status_counts"] == {
        "mapped": 2,
        "derived_via_inputs": 9,
        "no_xbrl_counterpart_in_frozen_corpus": 0,
        "unmappable": 6,
    }
    by_id = {target["target_id"]: target for target in final_map["targets"]}
    assert set(by_id) == {f"NF{index:03d}" for index in range(1, 18)}
    for target_id in ("NF001", "NF002", "NF005", "NF006", "NF007", "NF008"):
        assert by_id[target_id]["final_mapping_status"] == "unmappable"
        assert by_id[target_id]["unmappable_reason_code"] == "TEMPORAL_NO_ANCHOR_METADATA"
        assert by_id[target_id]["stage_completion"]["stage3"] == "blocked_missing_exact_temporal_requirement"
    expected = {
        "NF012": (
            "TCC-31b1f6eab46385db",
            "XBRLCAND-64c41d8cf6d297f8",
            "2026-03-31",
        ),
        "NF013": (
            "TCC-f5206ab8eb1933a4",
            "XBRLCAND-7c4b2618999be1ab",
            "2026-06-30",
        ),
    }
    for target_id, (temporal_id, candidate_id, period_end) in expected.items():
        target = by_id[target_id]
        assert target["final_mapping_status"] == "mapped"
        assert target["temporal_resolution"]["status"] == "RESOLVED_HUMAN_CLOSED_SET"
        assert target["temporal_resolution"]["selected_temporal_candidate_id"] == temporal_id
        assert target["temporal_resolution"]["resolved_temporal"] == {
            "kind": "duration",
            "period_start": "2026-01-01",
            "period_end": period_end,
        }
        assert target["approved_candidate_ids"] == [candidate_id]
        assert target["stage1_candidates"][0]["temporal_consistency_status"] == "PASS_EXACT_BOUND_TEMPORAL"
        assert target["stage1_candidates"][0]["human_review_status"] == "APPROVE"
        assert target["stage_completion"]["stage3"] == "not_applicable_target_resolved_by_passing_candidate"


def test_final_dev_coverage_is_complete() -> None:
    coverage = json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))
    assert coverage["total_dev_numeric_targets"] == 17
    assert coverage["direct_mapped"] == 2
    assert coverage["derived_via_approved_inputs"] == 9
    assert coverage["no_xbrl_counterpart_in_frozen_corpus"] == 0
    assert coverage["unmappable"] == 6
    assert coverage["unmappable_reason_counts"] == {
        "TEMPORAL_NO_ANCHOR_METADATA": 6
    }
    assert coverage["pending_or_unresolved_human_decisions"] == 0
    assert coverage["human_reviewed_temporal_targets"] == 2
    assert coverage["approved_stage1_targets"] == 2
