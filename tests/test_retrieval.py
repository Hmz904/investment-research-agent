"""Gold-blind unit tests for production lexical retrieval."""

from __future__ import annotations

import copy
import math

import pytest

from src.retrieval import BM25Retriever, tokenize


def _record(chunk_id: str, text: str, **metadata: object) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "doc_id": metadata.pop("doc_id", f"DOC-{chunk_id}"),
        "accession": metadata.pop("accession", f"ACC-{chunk_id}"),
        "section_path": metadata.pop("section_path", ["Item 1"]),
        "text": text,
        **metadata,
    }


def test_tokenization_is_deterministic_and_preserves_financial_terms() -> None:
    text = "ＮＶＩＤＩＡ’s 10‑K: $1,234.50, 39.3%, FY27Q1 / AI/ML."
    expected = ["nvidia's", "10-k", "1234.50", "39.3%", "fy27q1", "ai/ml"]
    assert tokenize(text) == expected
    assert tokenize(text) == tokenize(text)


def test_tokenization_handles_punctuation_and_empty_text() -> None:
    assert tokenize("Revenue, profit; cash—flow...") == [
        "revenue",
        "profit",
        "cash-flow",
    ]
    assert tokenize("") == []
    assert tokenize("--- ... $$$") == []


def test_bm25_matches_hand_checkable_scores() -> None:
    retriever = BM25Retriever(k1=1.5, b=0.75)
    retriever.build_index(
        [
            _record("b", "apple carrot"),
            _record("a", "apple apple banana"),
            _record("c", "carrot"),
        ]
    )
    results = retriever.search("apple")
    inverse_document_frequency = math.log(1 + (3 - 2 + 0.5) / (2 + 0.5))
    expected_a = inverse_document_frequency * (2 * 2.5) / (
        2 + 1.5 * (1 - 0.75 + 0.75 * 3 / 2)
    )
    assert [result.chunk_id for result in results] == ["a", "b"]
    assert results[0].score == pytest.approx(expected_a)
    assert results[1].score == pytest.approx(inverse_document_frequency)


def test_empty_and_unmatched_queries_return_no_results() -> None:
    retriever = BM25Retriever()
    retriever.build_index([_record("a", "revenue growth")])
    assert retriever.search("") == []
    assert retriever.search("!!!") == []
    assert retriever.search("unmatched") == []


def test_table_row_aware_retrieval_text_is_indexed() -> None:
    retriever = BM25Retriever()
    retriever.build_index(
        [
            _record(
                "table",
                "visual table text without the target",
                block_type="table",
                retrieval_text="row_label Hyperscale current_period 48,710",
            )
        ]
    )
    result = retriever.search("Hyperscale 48,710")[0]
    assert result.chunk_id == "table"
    assert result.chunk_text == "visual table text without the target"
    assert result.retrieval_text == "row_label Hyperscale current_period 48,710"


def test_ranking_and_tie_breaking_are_deterministic() -> None:
    records = [_record("z", "same term"), _record("a", "same term")]
    first = BM25Retriever()
    first.build_index(records)
    second = BM25Retriever()
    second.build_index(reversed(records))
    assert [item.chunk_id for item in first.search("same")] == ["a", "z"]
    assert [item.to_dict() for item in first.search("same")] == [
        item.to_dict() for item in second.search("same")
    ]
    assert first.index_fingerprint == second.index_fingerprint


def test_top_k_and_exact_metadata_filtering() -> None:
    retriever = BM25Retriever()
    retriever.build_index(
        [
            _record("a", "growth", company="Alpha"),
            _record("b", "growth", company="Beta"),
            _record("c", "growth", company="Beta"),
        ]
    )
    assert len(retriever.search("growth", top_k=2)) == 2
    assert retriever.search("growth", top_k=0) == []
    assert [
        result.chunk_id
        for result in retriever.search("growth", top_k=10, filters={"company": "Beta"})
    ] == ["b", "c"]
    with pytest.raises(ValueError, match="unsupported metadata filter"):
        retriever.search("growth", filters={"unknown": "value"})


def test_result_propagates_canonical_metadata() -> None:
    retriever = BM25Retriever()
    retriever.build_index(
        [
            _record(
                "chunk-1",
                "capital expenditures",
                doc_id="DOC",
                accession="0001",
                company="Example Co",
                form="10-Q",
                filing_date="2026-04-30",
                period_of_report="2026-03-31",
                fiscal_period="FY26Q1",
                calendar_period="2026Q1",
                section_path=["Part I", "Item 2"],
                block_type="text",
            )
        ]
    )
    result = retriever.search("expenditures")[0]
    assert result.doc_id == "DOC"
    assert result.accession == "0001"
    assert result.company == "Example Co"
    assert result.form == "10-Q"
    assert result.filing_date == "2026-04-30"
    assert result.period_of_report == "2026-03-31"
    assert result.fiscal_period == "FY26Q1"
    assert result.calendar_period == "2026Q1"
    assert result.section_path == ("Part I", "Item 2")


def test_build_index_does_not_mutate_corpus_records() -> None:
    records = [
        _record(
            "table",
            "source text",
            section_path=["Note 1"],
            table_json={"rows": [{"cells": [{"raw_text": "Revenue"}]}]},
            retrieval_text="Revenue | 100",
        )
    ]
    before = copy.deepcopy(records)
    retriever = BM25Retriever()
    retriever.build_index(records)
    retriever.search("Revenue")
    assert records == before


def test_parameter_and_top_k_validation() -> None:
    with pytest.raises(ValueError, match="k1"):
        BM25Retriever(k1=-1)
    with pytest.raises(ValueError, match="b"):
        BM25Retriever(b=1.1)
    retriever = BM25Retriever()
    retriever.build_index([_record("a", "term")])
    with pytest.raises(TypeError, match="top_k"):
        retriever.search("term", top_k=1.5)  # type: ignore[arg-type]
