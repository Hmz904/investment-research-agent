# Investment Research Agent — Week 1 SEC Filing Ingestion

This repository contains the SEC filing ingestion layer for the investment
research agent. It downloads 14 specified SEC filings, stores immutable raw
bytes, parses HTML/inline-XBRL into ordered blocks, extracts structured tables
and fact-level period provenance, and writes deterministic chunks plus an
ingestion manifest.

The pipeline is intentionally scoped to ingestion only. It does not implement
retrieval, embeddings, reranking, LLM calls, or agent logic.

## Setup

Create and activate a virtual environment, then install pinned dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` is a complete freeze of the currently working environment.

## Configure the SEC user agent

The HTTP client reads `SEC_USER_AGENT` from the environment only. Set it to a
contact string (your name and affiliation) before running the pipeline:

```bash
export SEC_USER_AGENT='Your Name your-contact-here'
```

Do not store a real email address or any API key in this repository.

## Run the pipeline

```bash
python -m src.pipeline
```

This discovers the 14 filing documents from SEC EDGAR index pages, downloads or
reuses immutable raw files under `data/raw/`, and writes:

- `data/parsed/*.json` — ordered blocks
- `data/chunks/*.json` — deterministic chunks
- `data/manifest.json` — ingestion manifest

The second and later runs reuse valid raw files and verify their SHA-256
hashes rather than re-downloading them.

## Tests

```bash
pytest -q
```

Test organization:

- `tests/test_unit.py` uses committed fixtures under `tests/fixtures/` and does
  not require the downloaded corpus.
- `tests/test_ingestion.py` is the corpus acceptance/integration suite and
  requires generated `data/` output from a completed pipeline run.

