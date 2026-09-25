"""Gold-blind synthetic tests for XBRLTool v0.1."""

from __future__ import annotations

import ast
import json
import warnings
from collections import Counter
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from src.xbrl import parse_inline_xbrl
from src.tools.xbrl_tool import (
    EXPECTED_CORPUS_FINGERPRINT,
    EXPECTED_INGESTION_SCHEMA_VERSION,
    XBRLArtifactError,
    XBRLDuplicateFactIDError,
    XBRLInputError,
    XBRLMetadataError,
    XBRLNumericError,
    XBRLTool,
    canonical_xbrl_trace_json,
)


def _record(index: int, **overrides: object) -> dict[str, object]:
    instant_date = overrides.pop("instant_date", "2026-03-31")
    period_start = overrides.pop("period_start", "")
    period_end = overrides.pop("period_end", "")
    raw = overrides.pop("raw_visible_text", "100")
    return {
        "doc_id": overrides.pop("doc_id", "EXAMPLE_10Q"),
        "accession": overrides.pop("accession", "0000000001-26-000001"),
        "source_role": overrides.pop("source_role", "local_fixture"),
        "fact_id": overrides.pop("fact_id", f"f-{index}"),
        "concept": overrides.pop("concept", "us-gaap:Assets"),
        "context_id": overrides.pop("context_id", f"c-{index}"),
        "period_start": period_start,
        "period_end": period_end,
        "instant_date": instant_date,
        "dimensions": overrides.pop("dimensions", []),
        "members": overrides.pop("members", []),
        "unit": overrides.pop("unit", "usd"),
        "unit_measures": overrides.pop("unit_measures", ["iso4217:USD"]),
        "decimals": overrides.pop("decimals", "-6"),
        "scale": overrides.pop("scale", 0),
        "sign": overrides.pop("sign", None),
        "raw_visible_text": raw,
        "parsed_value": overrides.pop("parsed_value", 100),
        "scaled_value": overrides.pop("scaled_value", 100.0),
        "is_negative": overrides.pop("is_negative", False),
        "company": overrides.pop("company", "Example Corp"),
        "cik": overrides.pop("cik", "1"),
        "entity_identifier": overrides.pop("entity_identifier", "0000000001"),
        "entity_scheme": overrides.pop(
            "entity_scheme", "http://www.sec.gov/CIK"
        ),
        "form_type": overrides.pop("form_type", "10-Q"),
        "filing_date": overrides.pop("filing_date", "2026-04-30"),
        "period_of_report": overrides.pop("period_of_report", "2026-03-31"),
        "fiscal_period": overrides.pop("fiscal_period", "FY26Q1"),
        "calendar_period": overrides.pop("calendar_period", "2026Q1"),
        "doc_role": overrides.pop("doc_role", "primary"),
        "chunk_id": overrides.pop("chunk_id", f"chunk-{index}"),
        **overrides,
    }


def _tool(records: list[Mapping[str, object]] | None = None) -> XBRLTool:
    return XBRLTool(
        fact_records=records or [_record(1)],
        xbrl_artifact_fingerprint="fixture-xbrl-fingerprint",
        ingestion_schema_version="fixture-schema",
        corpus_fingerprint="fixture-corpus-fingerprint",
    )


@pytest.fixture(scope="module")
def production_tool() -> XBRLTool:
    def blocked_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access attempted by XBRLTool")

    with patch("socket.socket", side_effect=blocked_network):
        return XBRLTool.from_frozen_ingestion(
            data_root=Path(__file__).resolve().parents[2] / "data"
        )


@pytest.mark.parametrize("query", ["", "   ", "\t\n"])
def test_empty_concept_query_is_rejected(query: str) -> None:
    with pytest.raises(XBRLInputError, match="non-empty"):
        _tool().search_concepts(query)


@pytest.mark.parametrize("top_k", [0, -1, 51, True, 1.5])
def test_invalid_concept_top_k_is_rejected(top_k: object) -> None:
    with pytest.raises(XBRLInputError, match="top_k"):
        _tool().search_concepts("assets", top_k=top_k)  # type: ignore[arg-type]


def test_concept_discovery_uses_deterministic_lexical_order_and_tie_break() -> None:
    tool = _tool(
        [
            _record(1, concept="us-gaap:CashAndCashEquivalentsAtCarryingValue"),
            _record(2, concept="ext:CashAndCashEquivalents"),
            _record(3, concept="abc:CashAndCashEquivalents"),
            _record(4, concept="us-gaap:Cash"),
        ]
    )
    first = tool.search_concepts("cash and cash equivalents", top_k=4)
    second = tool.search_concepts("cash and cash equivalents", top_k=4)

    assert [item.concept for item in first.results] == [
        "abc:CashAndCashEquivalents",
        "ext:CashAndCashEquivalents",
        "us-gaap:CashAndCashEquivalentsAtCarryingValue",
        "us-gaap:Cash",
    ]
    assert first.to_dict() == second.to_dict()
    assert first.results[0].namespace_prefix == "abc"
    assert first.results[0].local_name == "CashAndCashEquivalents"
    assert first.results[0].fact_count == 1


def test_concept_result_reports_only_observed_local_metadata() -> None:
    records = [
        _record(1, concept="us-gaap:Assets", company="Example Corp"),
        _record(
            2,
            concept="us-gaap:Assets",
            doc_id="SECOND_10Q",
            accession="0000000002-26-000002",
            company="Second Corp",
            cik="2",
            entity_identifier="0000000002",
            unit="shares",
            unit_measures=["xbrli:shares"],
        ),
    ]
    result = _tool(records).search_concepts("Assets").results[0]
    assert result.fact_count == 2
    assert result.unit_refs_observed == ("shares", "usd")
    assert result.unit_measures_observed == (
        ("iso4217:USD",),
        ("xbrli:shares",),
    )
    assert result.unit_numerators_observed == ()
    assert result.unit_denominators_observed == ()
    assert result.companies_observed == ("Example Corp", "Second Corp")
    assert not hasattr(result, "label")
    assert not hasattr(result, "namespace")


def test_exact_concept_query_returns_all_facts_in_stable_identity_order() -> None:
    records = [
        _record(20, fact_id="f-20"),
        _record(1, fact_id="f-01"),
        _record(2, concept="us-gaap:Liabilities"),
    ]
    response = _tool(records).query_facts(concept="us-gaap:Assets")
    assert response.matched_count == 2
    assert [fact.stable_fact_id for fact in response.facts] == [
        "EXAMPLE_10Q::f-01",
        "EXAMPLE_10Q::f-20",
    ]


def test_exact_accession_company_form_and_fiscal_filters() -> None:
    records = [
        _record(1),
        _record(
            2,
            doc_id="SECOND_10K",
            accession="0000000002-26-000002",
            company="Second Corp",
            cik="2",
            entity_identifier="0000000002",
            form_type="10-K",
            fiscal_period="FY26",
        ),
    ]
    tool = _tool(records)
    assert tool.query_facts(
        concept="us-gaap:Assets", accession="0000000001-26-000001"
    ).matched_count == 1
    assert tool.query_facts(
        concept="us-gaap:Assets",
        company="Second Corp",
        form_type="10-K",
        filing_fiscal_period="FY26",
    ).facts[0].doc_id == "SECOND_10K"
    assert tool.query_facts(
        concept="us-gaap:Assets", company="second corp"
    ).matched_count == 0


def test_instant_fact_and_exact_instant_filter() -> None:
    fact = _tool().query_facts(
        concept="us-gaap:Assets", instant="2026-03-31"
    ).facts[0]
    assert fact.period_type == "instant"
    assert fact.instant == "2026-03-31"
    assert fact.period_start is None
    assert fact.period_end is None
    assert fact.duration_days is None


def test_q2_quarter_and_ytd_duration_contexts_remain_distinct() -> None:
    records = [
        _record(
            1,
            concept="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
            instant_date="",
            period_start="2026-04-01",
            period_end="2026-06-30",
            raw_visible_text="25",
            parsed_value=25,
            fiscal_period="FY26Q2",
        ),
        _record(
            2,
            concept="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
            instant_date="",
            period_start="2026-01-01",
            period_end="2026-06-30",
            raw_visible_text="50",
            parsed_value=50,
            fiscal_period="FY26Q2",
        ),
    ]
    response = _tool(records).query_facts(
        concept="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        period_end="2026-06-30",
    )
    assert response.matched_count == 2
    assert {fact.filing_fiscal_period for fact in response.facts} == {"FY26Q2"}
    assert [(fact.period_start, fact.duration_days) for fact in response.facts] == [
        ("2026-04-01", 91),
        ("2026-01-01", 181),
    ]


def test_unit_filter_is_exact_raw_unit_reference() -> None:
    records = [
        _record(1, unit="usd", unit_measures=["iso4217:USD"]),
        _record(2, unit="U_USD", unit_measures=["iso4217:USD"]),
    ]
    response = _tool(records).query_facts(concept="us-gaap:Assets", unit="usd")
    assert [fact.fact_id for fact in response.facts] == ["f-1"]
    assert response.facts[0].unit_measures == ("iso4217:USD",)


def test_divide_unit_numerator_and_denominator_are_preserved() -> None:
    fact = _tool(
        [
            _record(
                1,
                unit="usdPerShare",
                unit_measures=[],
                unit_numerator=["iso4217:USD"],
                unit_denominator=["xbrli:shares"],
            )
        ]
    ).query_facts(concept="us-gaap:Assets").facts[0]
    assert fact.unit_numerator == ("iso4217:USD",)
    assert fact.unit_denominator == ("xbrli:shares",)


def test_dimensional_contexts_and_semantic_duplicates_are_not_collapsed() -> None:
    dimensions = [
        {
            "axis": "us-gaap:StatementBusinessSegmentsAxis",
            "member": "ext:CloudMember",
        }
    ]
    records = [
        _record(1, context_id="consolidated", dimensions=[]),
        _record(2, context_id="segment", dimensions=dimensions),
        _record(3, context_id="segment-copy", dimensions=dimensions),
    ]
    response = _tool(records).query_facts(concept="us-gaap:Assets")
    assert response.matched_count == 3
    assert response.facts[0].dimensions == ()
    assert response.facts[1].dimensions is not None
    assert response.facts[1].dimensions[0].member == "ext:CloudMember"
    assert response.facts[2].dimensions == response.facts[1].dimensions


def test_include_dimensions_false_omits_payload_without_changing_rows() -> None:
    tool = _tool(
        [
            _record(1, dimensions=[]),
            _record(2, dimensions=[{"axis": "ext:Axis", "member": "ext:Member"}]),
        ]
    )
    included = tool.query_facts(concept="us-gaap:Assets")
    omitted = tool.query_facts(
        concept="us-gaap:Assets", include_dimensions=False
    )
    assert omitted.matched_count == included.matched_count == 2
    assert [fact.stable_fact_id for fact in omitted.facts] == [
        fact.stable_fact_id for fact in included.facts
    ]
    assert all(fact.dimensions is None for fact in omitted.facts)
    assert omitted.filters["include_dimensions"] is False


def test_known_concept_can_validly_return_zero_rows() -> None:
    response = _tool().query_facts(
        concept="us-gaap:Assets", filing_fiscal_period="FY99Q4"
    )
    assert response.matched_count == 0
    assert response.facts == ()
    assert response.trace.concepts == ("us-gaap:Assets",)


def test_unknown_exact_concept_is_distinct_from_zero_match() -> None:
    with pytest.raises(XBRLInputError, match="unknown exact concept"):
        _tool().query_facts(concept="us-gaap:NotObserved")


def test_exact_decimal_negative_value_and_decimals_metadata_are_preserved() -> None:
    records = [
        _record(
            1,
            raw_visible_text="0.07",
            parsed_value=0.07,
            scale=0,
            decimals="2",
        ),
        _record(
            2,
            raw_visible_text="(0.28)",
            parsed_value=-0.28,
            scale=0,
            decimals="2",
        ),
        _record(
            3,
            raw_visible_text="48,554",
            parsed_value=48554,
            scale=3,
            decimals="-3",
        ),
    ]
    facts = _tool(records).query_facts(concept="us-gaap:Assets").facts
    assert [fact.raw_value for fact in facts] == ["0.07", "(0.28)", "48,554"]
    assert [fact.normalized_value for fact in facts] == [
        "0.07",
        "-0.28",
        "48554000",
    ]
    assert [fact.decimals for fact in facts] == ["2", "2", "-3"]
    assert all(isinstance(fact.normalized_value, str) for fact in facts)


def test_nonnumeric_or_nil_ingested_value_remains_none() -> None:
    fact = _tool(
        [_record(1, raw_visible_text="—", parsed_value=None, scaled_value=None)]
    ).query_facts(concept="us-gaap:Assets").facts[0]
    assert fact.raw_value == "—"
    assert fact.normalized_value is None


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"accession": "bad"}, "accession"),
        ({"instant": "2026-02-30"}, "malformed instant"),
        (
            {"instant": "2026-03-31", "period_start": "2026-01-01"},
            "cannot be combined",
        ),
    ],
)
def test_invalid_structured_filters_are_rejected(
    kwargs: dict[str, object], message: str
) -> None:
    with pytest.raises(XBRLInputError, match=message):
        _tool().query_facts(concept="us-gaap:Assets", **kwargs)  # type: ignore[arg-type]


def test_malformed_numeric_value_marked_parsed_is_explicit_error() -> None:
    with pytest.raises(XBRLNumericError, match="malformed numeric value"):
        _tool([_record(1, raw_visible_text="not-a-number", parsed_value=1)])


def test_duplicate_stable_fact_id_is_explicit_error() -> None:
    with pytest.raises(XBRLDuplicateFactIDError, match="duplicate stable fact ID"):
        _tool([_record(1), _record(2, fact_id="f-1")])


def test_inconsistent_accession_entity_metadata_is_explicit_error() -> None:
    with pytest.raises(XBRLMetadataError, match="inconsistent accession/entity"):
        _tool(
            [
                _record(1),
                _record(
                    2,
                    company="Other Corp",
                    cik="2",
                    entity_identifier="0000000002",
                ),
            ]
        )


def test_entity_identifier_must_match_manifest_cik() -> None:
    with pytest.raises(XBRLMetadataError, match="CIK mismatch"):
        _tool([_record(1, cik="2")])


def test_source_identity_and_optional_chunk_link_are_preserved() -> None:
    facts = _tool(
        [_record(1, chunk_id=None), _record(2, chunk_id="authoritative-chunk")]
    ).query_facts(concept="us-gaap:Assets").facts
    assert facts[0].fact_locator == "EXAMPLE_10Q#f-1"
    assert facts[0].chunk_id is None
    assert facts[1].fact_locator == "EXAMPLE_10Q#f-2"
    assert facts[1].chunk_id == "authoritative-chunk"


def test_production_fact_identities_are_global_unique_and_document_scoped(
    production_tool: XBRLTool,
) -> None:
    facts = production_tool._facts
    stable_ids = [fact.stable_fact_id for fact in facts]
    fact_locators = [fact.fact_locator for fact in facts]
    bare_counts = Counter(fact.fact_id for fact in facts)

    assert production_tool.fact_count == 7_839
    assert production_tool.concept_count == 746
    assert production_tool.xbrl_artifact_fingerprint == (
        "acaf087ee2c4fb7427377cae5f1968da26c75d4dfa565f67f1e056b2c4cc4eb6"
    )
    assert len(stable_ids) == len(set(stable_ids)) == 7_839
    assert len(fact_locators) == len(set(fact_locators)) == 7_839
    assert any(count > 1 for count in bare_counts.values())
    assert sum(fact.chunk_id is not None for fact in facts) == 7_199
    assert sum(fact.chunk_id is None for fact in facts) == 640

    trace = production_tool.query_facts(concept="us-gaap:Assets").trace
    assert trace.returned_fact_ids
    assert all("::" in stable_id for stable_id in trace.returned_fact_ids)
    assert trace.returned_fact_ids == tuple(
        fact.stable_fact_id
        for fact in production_tool.query_facts(concept="us-gaap:Assets").facts
    )


def test_production_decimal_scale_sign_and_nonnumeric_semantics(
    production_tool: XBRLTool,
) -> None:
    root = Path(__file__).resolve().parents[2]
    manifest = json.loads((root / "data" / "manifest.json").read_text(encoding="utf-8"))
    entry = next(
        item for item in manifest["entries"] if item["doc_id"] == "META_2026Q1_10Q"
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        soup = BeautifulSoup(Path(entry["local_path"]).read_bytes(), "lxml")
    ingested = parse_inline_xbrl(
        soup,
        doc_id=entry["doc_id"],
        accession=entry["accession"],
        source_role=entry["source_role"],
    )
    source_by_id = {fact["fact_id"]: fact for fact in ingested["facts"]}
    cases = {
        "f-119": {"normalized": "10.57", "scale": 0, "sign": None, "decimals": "2"},
        "f-100": {
            "normalized": "7572000000",
            "scale": 6,
            "sign": None,
            "decimals": "-6",
        },
        "f-111": {
            "normalized": "-1120000000",
            "scale": 6,
            "sign": "-",
            "decimals": "-6",
        },
        "f-138": {
            "normalized": "121179000000",
            "scale": 6,
            "sign": None,
            "decimals": "-6",
        },
        "f-24": {
            "normalized": "2196045588",
            "scale": 0,
            "sign": None,
            "decimals": "INF",
        },
    }
    for fact_id, expected in cases.items():
        source = source_by_id[fact_id]
        public = production_tool._facts_by_id[f"META_2026Q1_10Q::{fact_id}"]
        ingestion_meaning = Decimal(str(source["parsed_value"])) * (
            Decimal(10) ** source["scale"]
        )
        assert public.normalized_value == expected["normalized"]
        assert Decimal(public.normalized_value) == ingestion_meaning
        assert public.scale == source["scale"] == expected["scale"]
        assert public.sign == source["sign"] == expected["sign"]
        assert public.decimals == source["decimals"] == expected["decimals"]
        assert public.unit == source["unit"]

    signed_source = source_by_id["f-111"]
    assert signed_source["raw_visible_text"] == "1,120"
    assert signed_source["parsed_value"] == -1120
    assert production_tool._facts_by_id[
        "META_2026Q1_10Q::f-111"
    ].normalized_value == "-1120000000"

    nonnumeric_source = source_by_id["f-1"]
    nonnumeric_public = production_tool._facts_by_id["META_2026Q1_10Q::f-1"]
    assert nonnumeric_source["concept"] == "dei:DocumentType"
    assert nonnumeric_source["parsed_value"] is None
    assert nonnumeric_public.raw_value == "10-Q"
    assert nonnumeric_public.normalized_value is None


def test_trace_serialization_is_canonical_timestamp_free_and_stable() -> None:
    tool = _tool([_record(2), _record(1)])
    trace = tool.query_facts(concept="us-gaap:Assets").trace
    first = canonical_xbrl_trace_json(trace)
    second = canonical_xbrl_trace_json(dict(reversed(list(trace.to_dict().items()))))
    assert first.encode("utf-8") == second.encode("utf-8")
    assert first.endswith("\n")
    assert ": " not in first and ", " not in first
    payload = json.loads(first)
    assert payload["returned_fact_ids"] == [
        "EXAMPLE_10Q::f-1",
        "EXAMPLE_10Q::f-2",
    ]
    assert payload["operation"] == "query_facts"
    assert "timestamp" not in payload
    with pytest.raises(ValueError, match="JSON compliant"):
        canonical_xbrl_trace_json({"non_finite": float("nan")})


def test_concept_trace_has_ordered_concepts_and_no_fact_ids() -> None:
    trace = _tool(
        [_record(1, concept="abc:Cash"), _record(2, concept="xyz:Cash")]
    ).search_concepts("cash", top_k=2).trace
    assert trace.returned_concept_ids == ("abc:Cash", "xyz:Cash")
    assert trace.returned_fact_ids == ()
    assert trace.matched_count == trace.returned_count == 2


def test_missing_production_artifact_fails_explicitly(tmp_path: Path) -> None:
    with pytest.raises(XBRLArtifactError, match="missing local XBRL manifest"):
        XBRLTool.from_frozen_ingestion(data_dir=tmp_path / "missing")


def test_frozen_factory_loads_files_and_indices_once_per_instance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.tools.xbrl_tool as module

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "manifest.json").write_text(
        json.dumps(
            {
                "ingestion_schema_version": EXPECTED_INGESTION_SCHEMA_VERSION,
                "corpus_fingerprint": EXPECTED_CORPUS_FINGERPRINT,
                "entries": [{"doc_id": "fixture"}],
            }
        ),
        encoding="utf-8",
    )
    counts = {"links": 0, "facts": 0}

    def fake_links(
        cls: type[XBRLTool], path: Path, entries: object
    ) -> dict[tuple[str, str], str]:
        counts["links"] += 1
        return {}

    def fake_facts(
        cls: type[XBRLTool],
        path: Path,
        entries: object,
        links: object,
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        counts["facts"] += 1
        return [_record(1)], [
            {
                "doc_id": "fixture",
                "accession": "0000000001-26-000001",
                "raw_sha256": "fixture",
                "xbrl_fact_count": 1,
            }
        ]

    monkeypatch.setattr(module.XBRLTool, "_load_chunk_links", classmethod(fake_links))
    monkeypatch.setattr(module.XBRLTool, "_load_fact_records", classmethod(fake_facts))
    tool = XBRLTool.from_frozen_ingestion(data_dir=data_dir)
    initialized = dict(counts)
    tool.search_concepts("assets")
    tool.query_facts(concept="us-gaap:Assets")
    tool.query_facts(concept="us-gaap:Assets", instant="2026-03-31")
    assert initialized == {"links": 1, "facts": 1}
    assert counts == initialized


def test_tool_source_has_no_benchmark_evaluation_or_network_dependency() -> None:
    root = Path(__file__).resolve().parents[2]
    source = (root / "src" / "tools" / "xbrl_tool.py").read_text(encoding="utf-8")
    forbidden_fragments = (
        "benchmark/" + "dev",
        "benchmark/" + "frozen",
        "numeric_" + "answers",
        "evidence_" + "checklist",
        "evaluation/" + "results",
        "data/provenance",
    )
    assert all(fragment not in source for fragment in forbidden_fragments)
    imported_modules = {
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and node.module is not None
    } | {
        alias.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not any(
        module == "evaluation"
        or module.startswith("evaluation.")
        or module == "benchmark"
        or module.startswith("benchmark.")
        or module == "requests"
        or module.startswith("urllib")
        or module == "src.sec"
        for module in imported_modules
    )
