from __future__ import annotations

import csv
import hashlib
import json

from evaluation.build_dev_xbrl_mapping_candidates import (
    CANDIDATE_PATH,
    COVERAGE_PATH,
    REVIEW_PACKET_PATH,
    SOURCE_CHECKS_PATH,
    UNIT_AUDIT_PATH,
)


def test_dev_candidate_artifact_hashes_match_existing_d1_coverage() -> None:
    coverage = json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))
    assert hashlib.sha256(CANDIDATE_PATH.read_bytes()).hexdigest() == coverage[
        "candidate_artifact_sha256"
    ]
    assert hashlib.sha256(REVIEW_PACKET_PATH.read_bytes()).hexdigest() == coverage[
        "review_packet_sha256"
    ]


def test_dev_candidate_artifact_has_complete_pending_review_structure() -> None:
    artifact = json.loads(CANDIDATE_PATH.read_text(encoding="utf-8"))
    targets = artifact["targets"]
    assert len(targets) == 17
    assert sum(target["target_kind"] == "direct" for target in targets) == 8
    assert sum(target["target_kind"] == "derived" for target in targets) == 9
    assert all(target["human_review_status"] == "" for target in targets)
    assert all(target["human_review_notes"] == "" for target in targets)

    candidates = [candidate for target in targets for candidate in target["candidates"]]
    assert len({candidate["candidate_id"] for candidate in candidates}) == len(candidates)
    assert all(candidate["human_review_status"] == "" for candidate in candidates)
    assert all(candidate["human_review_notes"] == "" for candidate in candidates)
    assert {candidate["source_check_status"] for candidate in candidates} == {"SOURCE_CHECK_PASS"}

    target_ids = {target["target_id"] for target in targets}
    for target in targets:
        assert set(target["required_input_ids"]) <= target_ids
        if target["target_kind"] == "derived":
            assert {item["input_target_id"] for item in target["derived_input_lineage"]} == set(target["required_input_ids"])


def test_dev_unit_audit_has_no_alias_blocker() -> None:
    with UNIT_AUDIT_PATH.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert {row["unit_label"] for row in rows} == {
        "USD_million",
        "USD_per_diluted_share",
        "percent",
    }
    assert {row["classification"] for row in rows} == {"registered"}
    assert all(row["required_contract_revision"] == "" for row in rows)


def test_source_checks_cover_candidates_and_only_authorized_reviews_are_approved() -> None:
    artifact = json.loads(CANDIDATE_PATH.read_text(encoding="utf-8"))
    candidate_ids = {
        candidate["candidate_id"]
        for target in artifact["targets"]
        for candidate in target["candidates"]
    }
    with SOURCE_CHECKS_PATH.open(newline="", encoding="utf-8") as handle:
        source_checks = list(csv.DictReader(handle))
    assert {row["candidate_id"] for row in source_checks} == candidate_ids
    assert {row["source_check_status"] for row in source_checks} == {"SOURCE_CHECK_PASS"}

    with REVIEW_PACKET_PATH.open(newline="", encoding="utf-8") as handle:
        review_rows = list(csv.DictReader(handle))
    assert len(review_rows) == 17
    approved = {
        row["candidate_id"]
        for row in review_rows
        if row["human_review_status"] == "APPROVE"
    }
    assert approved == {
        "XBRLCAND-64c41d8cf6d297f8",
        "XBRLCAND-7c4b2618999be1ab",
    }
    assert all(
        row["human_review_status"] in {"", "APPROVE"} for row in review_rows
    )
    assert all(row["human_review_notes"] == "" for row in review_rows)
