# RetrievalTool v0.1

## Contract

`RetrievalTool.search(query: str, top_k: int = 10)` executes the frozen
production retrieval stack for an arbitrary new query:

```text
full frozen corpus
-> frozen BM25 top 50 + embedding_v0.1 top 50
-> exact chunk_id union
-> reranker_v0.1 over every union member
-> requested top_k (1 through 50)
```

It does not read or replay benchmark ranking files. It performs no query
rewrite, decomposition, metadata filtering, RRF score fusion, score
normalization, boosting, heuristic adjustment, or fallback retrieval.
Public `top_k` is applied only after every member of the BM25/dense union has
been scored and ranked. It never changes either component's requested depth,
the union, or the reranker input set. Consequently, `reranker_rank` is the
rank in the fully reranked union, before the public response is truncated.

The production constructor is:

```python
from src.tools import RetrievalTool

tool = RetrievalTool.from_frozen_stack()
response = tool.search("an arbitrary corpus-relevant query", top_k=10)
```

`from_frozen_stack()` loads the corpus, builds the BM25 index, validates and
loads the dense cache/model, and loads the reranker exactly once per tool
instance. The temporary dense-cache copy is also made only during this
initialization. `search()` reuses those stored resources; it does not reload
the corpus or models, recopy the cache, or rebuild either index. Direct
construction accepts compatible retriever and scorer dependencies for unit
testing without loading the production cross-encoder.

## Frozen identities

- retrieval stack: `retrieval_stack_v0.1` at
  `963b089e17983eec954c30970e408c7efc53a9f8`
- dense model: `BAAI/bge-base-en-v1.5` at
  `a5beb1e3e68b9ab74eb54cfd186867f64f240e1a`
- reranker: `BAAI/bge-reranker-v2-m3` at
  `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`
- reranker scoring: raw logits, CPU float32, evaluation/inference mode,
  `max_length=1024`, passage-only truncation, and ascending `chunk_id` for
  exact score ties

The embedding cache is copied to a temporary directory during initialization.
This lets the existing dense implementation validate an exact cache hit while
making it impossible for cache-rebuild behavior to modify frozen artifacts.

## Response schema

`RetrievalResponse` contains:

- `tool_version`
- `query`
- `top_k`
- `candidate_pool_size`
- `results`
- `trace`

Each `RetrievalResult` contains:

- `rank`, `reranker_rank`, and raw `reranker_score`
- `bm25_rank` and `embedding_rank` (nullable)
- citation fields `chunk_id`, `accession`, and `locator`
- canonical `text`, `doc_id`, `company`, and `form_type`
- `filing_date`, `period_of_report`, `fiscal_period`, and `calendar_period`
- `source_role`, `doc_role`, `exhibit_number`, and `block_type`
- `section_path`, `char_start`, and `char_end`
- `table_metadata` when present, preserving canonical `table_json`,
  `period_columns`, `unit_scale`, and `xbrl_facts`

The citation names align with `agent_output_schema_v0.1`. Every public result
is built from the canonical corpus record keyed by `chunk_id`, after accession,
text, retrieval text, and immutable document metadata have been checked
against both component outputs. `locator` propagates an explicit corpus
locator when present. Otherwise it mechanically serializes the authoritative
`section_path`; chunks without a section path use their authoritative document
ID and character offsets. It performs no semantic reconstruction, mutable
result-time rewrite, or model-generated locator inference.

## Deterministic trace

`RetrievalTrace` records the tool/version, exact query, requested depth,
component and union counts, ordered returned chunk IDs, corpus/retrieval-stack
identity, and frozen BM25/dense/reranker configuration. It contains no gold,
labels, evaluation scores, or timestamp. `canonical_trace_json()` uses sorted
keys, compact separators, UTF-8-compatible JSON, finite numbers only, and a
terminal newline for future content hashing.

## Errors

The tool fails explicitly for empty queries, `top_k` outside 1–50, missing or
invalid artifacts, a component returning more than the requested 50 ranked
candidates, duplicate candidate IDs, component/corpus metadata conflicts,
candidates outside the frozen corpus, incomplete reranker scores, non-finite
scores, and declared model/revision mismatches. The frozen components are
always asked for 50; if lexical retrieval has fewer matching chunks, the tool
uses exactly those returned chunks without filling them through a fallback. It
never silently switches retrieval strategy.

## Version boundary

RetrievalTool v0.1 always searches the full frozen corpus. Metadata filtering
is deferred to a future tool-layer version. Any such filter changes candidate
generation and must not be described as `retrieval_stack_v0.1` benchmark
behavior.
