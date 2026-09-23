"""The fixed source corpus for Week 1 SEC filing ingestion.

This is the explicit source list from prompts/week1_ingestion.md.  It is kept
independent of the benchmark directory on purpose.
"""

from __future__ import annotations

from typing import Any


SOURCES: list[dict[str, Any]] = [
    # NVIDIA - historical references
    {
        "doc_id": "NVDA_FY26Q2_10Q",
        "cik": "1045810",
        "company": "NVIDIA",
        "form": "10-Q",
        "accession": "0001045810-25-000209",
        "fiscal_period": "FY26Q2",
        "calendar_period": "2025Q2",
        "doc_role": "primary",
        "exhibit_number": "",
        "source_role": "historical_reference",
    },
    {
        "doc_id": "NVDA_FY26Q4_8K_EX991",
        "cik": "1045810",
        "company": "NVIDIA",
        "form": "8-K",
        "accession": "0001045810-26-000019",
        "fiscal_period": "FY26Q4",
        "calendar_period": "2025Q4",
        "doc_role": "exhibit",
        "exhibit_number": "99.1",
        "source_role": "historical_reference",
    },
    # NVIDIA - benchmark periods
    {
        "doc_id": "NVDA_FY27Q1_10Q",
        "cik": "1045810",
        "company": "NVIDIA",
        "form": "10-Q",
        "accession": "0001045810-26-000052",
        "fiscal_period": "FY27Q1",
        "calendar_period": "2026Q1",
        "doc_role": "primary",
        "exhibit_number": "",
        "source_role": "benchmark_period",
    },
    {
        "doc_id": "NVDA_FY27Q1_8K_EX991",
        "cik": "1045810",
        "company": "NVIDIA",
        "form": "8-K",
        "accession": "0001045810-26-000051",
        "fiscal_period": "FY27Q1",
        "calendar_period": "2026Q1",
        "doc_role": "exhibit",
        "exhibit_number": "99.1",
        "source_role": "benchmark_period",
    },
    {
        "doc_id": "NVDA_FY27Q2_10Q",
        "cik": "1045810",
        "company": "NVIDIA",
        "form": "10-Q",
        "accession": "0001045810-26-000075",
        "fiscal_period": "FY27Q2",
        "calendar_period": "2026Q2",
        "doc_role": "primary",
        "exhibit_number": "",
        "source_role": "benchmark_period",
    },
    {
        "doc_id": "NVDA_FY27Q2_8K_EX991",
        "cik": "1045810",
        "company": "NVIDIA",
        "form": "8-K",
        "accession": "0001045810-26-000073",
        "fiscal_period": "FY27Q2",
        "calendar_period": "2026Q2",
        "doc_role": "exhibit",
        "exhibit_number": "99.1",
        "source_role": "benchmark_period",
    },
    # Microsoft
    {
        "doc_id": "MSFT_FY26Q3_10Q",
        "cik": "789019",
        "company": "Microsoft",
        "form": "10-Q",
        "accession": "0001193125-26-191507",
        "fiscal_period": "FY26Q3",
        "calendar_period": "2026Q1",
        "doc_role": "primary",
        "exhibit_number": "",
        "source_role": "benchmark_period",
    },
    {
        "doc_id": "MSFT_FY26Q3_8K_EX991",
        "cik": "789019",
        "company": "Microsoft",
        "form": "8-K",
        "accession": "0001193125-26-191457",
        "fiscal_period": "FY26Q3",
        "calendar_period": "2026Q1",
        "doc_role": "exhibit",
        "exhibit_number": "99.1",
        "source_role": "benchmark_period",
    },
    {
        "doc_id": "MSFT_FY26_10K",
        "cik": "789019",
        "company": "Microsoft",
        "form": "10-K",
        "accession": "0001193125-26-323660",
        "fiscal_period": "FY26",
        "calendar_period": "2025Q3-2026Q2",
        "doc_role": "primary",
        "exhibit_number": "",
        "source_role": "benchmark_period",
    },
    {
        "doc_id": "MSFT_FY26Q4_8K_EX991",
        "cik": "789019",
        "company": "Microsoft",
        "form": "8-K",
        "accession": "0001193125-26-323632",
        "fiscal_period": "FY26Q4",
        "calendar_period": "2026Q2",
        "doc_role": "exhibit",
        "exhibit_number": "99.1",
        "source_role": "benchmark_period",
    },
    # Meta
    {
        "doc_id": "META_2026Q1_10Q",
        "cik": "1326801",
        "company": "Meta",
        "form": "10-Q",
        "accession": "0001628280-26-028526",
        "fiscal_period": "2026Q1",
        "calendar_period": "2026Q1",
        "doc_role": "primary",
        "exhibit_number": "",
        "source_role": "benchmark_period",
    },
    {
        "doc_id": "META_2026Q1_8K_EX991",
        "cik": "1326801",
        "company": "Meta",
        "form": "8-K",
        "accession": "0001628280-26-028364",
        "fiscal_period": "2026Q1",
        "calendar_period": "2026Q1",
        "doc_role": "exhibit",
        "exhibit_number": "99.1",
        "source_role": "benchmark_period",
    },
    {
        "doc_id": "META_2026Q2_10Q",
        "cik": "1326801",
        "company": "Meta",
        "form": "10-Q",
        "accession": "0001628280-26-050705",
        "fiscal_period": "2026Q2",
        "calendar_period": "2026Q2",
        "doc_role": "primary",
        "exhibit_number": "",
        "source_role": "benchmark_period",
    },
    {
        "doc_id": "META_2026Q2_8K_EX991",
        "cik": "1326801",
        "company": "Meta",
        "form": "8-K",
        "accession": "0001628280-26-050596",
        "fiscal_period": "2026Q2",
        "calendar_period": "2026Q2",
        "doc_role": "exhibit",
        "exhibit_number": "99.1",
        "source_role": "benchmark_period",
    },
]


def get_source(doc_id: str) -> dict[str, Any]:
    for source in SOURCES:
        if source["doc_id"] == doc_id:
            return source
    raise KeyError(doc_id)

