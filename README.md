# Investment Research Agent — Week 1 SEC Filing Ingestion

This repository contains the SEC filing ingestion layer for the investment
research agent. It downloads 14 specified SEC filings, stores immutable raw
bytes, parses HTML/inline-XBRL into ordered blocks, extracts structured tables
and fact-level period provenance, and writes deterministic chunks plus an
ingestion manifest.

The repository also includes frozen deterministic lexical BM25 and dense BGE
retrieval baselines. It does not implement hybrid retrieval, reranking, query
rewriting, LLM retrieval, or agent logic.

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

## Dense embedding retrieval baseline

`src.embedding_retrieval.DenseRetriever` implements `embedding_v0.1` with
`BAAI/bge-base-en-v1.5` pinned to commit
`a5beb1e3e68b9ab74eb54cfd186867f64f240e1a`. It uses the same encoder for
queries and passages with no instruction prefix, CLS pooling, float32 L2
normalization, and a dot product over normalized vectors. CPU inference uses a
fixed batch size of 32 and deterministic PyTorch settings. Inputs longer than
the tokenizer's native 512-token limit are truncated without rechunking, and
pre-truncation token-length diagnostics are reported.

Run the frozen-query, gold-blind dense baseline with:

```bash
python -m evaluation.run_embedding
```

Model files and the validated embedding cache are stored under ignored
`data/` directories; model weights are not committed. The runner verifies the
frozen query SHA-256, ingestion schema, corpus fingerprint, per-document chunk
hashes, and 1,662-chunk universe before writing deterministic JSON Lines to
`evaluation/results/embedding_v0.1.jsonl`. It does not evaluate relevance.

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
- `tests/test_embedding_retrieval.py` uses a fake encoder to check dense ranking,
  normalization, cache invalidation, metadata, and deterministic serialization
  without downloading model weights.
