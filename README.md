# Investment Research Agent — Week 1 SEC Filing Ingestion

This repository contains the SEC filing ingestion layer for the investment
research agent. It downloads 14 specified SEC filings, stores immutable raw
bytes, parses HTML/inline-XBRL into ordered blocks, extracts structured tables
and fact-level period provenance, and writes deterministic chunks plus an
ingestion manifest.

The repository also includes a deterministic lexical BM25 retrieval baseline.
It does not implement embeddings, hybrid retrieval, reranking, query rewriting,
LLM retrieval, or agent logic.

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

## BM25 retrieval baseline

`src.retrieval.BM25Retriever` indexes canonical ingestion chunks in sorted
`chunk_id` order. It indexes `retrieval_text` when ingestion provides it
(including row-aware table text), otherwise it indexes canonical chunk `text`.
The direct Okapi BM25 implementation uses `k1=1.5`, `b=0.75`, Robertson's
positive IDF, unique query terms, and `chunk_id` as the score tie-breaker.

Tokenizer `sec_lexical_v1` applies Unicode NFKC normalization, canonicalizes
common dashes and apostrophes, case-folds, and extracts lexical alphanumeric
tokens. It preserves hyphen/slash/apostrophe compounds, decimals, percentages,
and comma-grouped numbers (with grouping commas removed). It does not stem,
remove stop words, add aliases, or perform semantic expansion.

Run the frozen-query, gold-blind baseline with:

```bash
python -m evaluation.run_bm25
```

The runner verifies the ingestion schema, corpus fingerprint, and per-document
chunk hashes, then writes deterministic JSON Lines to
`evaluation/results/bm25_v0.1.jsonl`. It reads only the frozen retrieval query
artifact and does not score relevance.

## Tests

```bash
pytest -q
```

Test organization:

- `tests/test_unit.py` uses committed fixtures under `tests/fixtures/` and does
  not require the downloaded corpus.
- `tests/test_ingestion.py` is the corpus acceptance/integration suite and
  requires generated `data/` output from a completed pipeline run.
- `tests/test_retrieval.py` checks tokenization, hand-computed BM25 scoring,
  deterministic ordering, metadata handling, and ingestion-record immutability.
