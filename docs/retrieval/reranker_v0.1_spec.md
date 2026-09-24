# `reranker_v0.1` production specification

## Status and experimental boundary

This specification is frozen before implementation and before any gold
evaluation of `reranker_v0.1`. It contains no gold metrics, per-question
benchmark results, miss counts, or evaluation-derived tuning decisions.

The required sequence is:

```text
spec freeze
-> new clean production session
-> implementation
-> deterministic tests
-> ranking artifact
-> commit/tag reranker_v0.1
-> new evaluation-only session
-> eval_protocol_v0.1 scoring
-> reranker_eval_v0.1 freeze
```

No gold evaluation is permitted before the `reranker_v0.1` ranking artifact
is frozen.

## Frozen inputs and candidate pool

For each frozen query, construct:

```text
candidate_pool =
    frozen bm25_v0.1 top 50
    UNION
    frozen embedding_v0.1 top 50
```

- Read the already-frozen component ranking artifacts. Do not rerun either
  component retriever.
- BM25 input:
  `evaluation/results/bm25_v0.1.jsonl`, SHA-256
  `7e276b409b9bebafa3b31acc105d253f90595bf652e2936446995bd5ae6611e1`.
- Embedding input:
  `evaluation/results/embedding_v0.1.jsonl`, SHA-256
  `d997bb8ac72ba2e003eea440b0e805e3dd9722b053874162bee7d6754bc2bfa3`.
- Use frozen English `query_en` from `retrieval_queries_v0.1.1` and require
  exact query identity across both component records.
- Deduplicate the union by exact `chunk_id`.
- Preserve each component rank when present; use null for absence.
- Candidate-pool size may vary by question and is expected to be between 50
  and 100 inclusive.
- Do not use only the `hybrid_v0.1` final top 50.

This architectural choice is made before reranker gold evaluation. Reranking
only the hybrid final top 50 would make reranker@50 use exactly the same
candidate set as hybrid@50 and would prevent testing whether the cross-encoder
can promote candidates that RRF placed at rank 51 or below.

## Frozen model identity

- Model ID: `BAAI/bge-reranker-v2-m3`
- Hugging Face revision/commit:
  `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`
- Tokenizer revision: the same repository commit; there is no separately
  pinned tokenizer repository or revision.
- Architecture declared by the pinned config:
  `XLMRobertaForSequenceClassification`.

Raw-file SHA-256 fingerprints resolved at that exact revision:

| File | SHA-256 |
|---|---|
| `config.json` | `13dcd6c31d9fec9d1d8e158702072f62d7fa7d312a64b9fe057bec9a08cfe41a` |
| `tokenizer_config.json` | `7e4c1cc848840aeccdd763458c18dd525eb0f795c992e00ebe9c28554e7db2d4` |
| `special_tokens_map.json` | `8c785abebea9ae3257b61681b4e6fd8365ceafde980c21970d001e834cf10835` |
| `tokenizer.json` | `69564b696052886ed0ac63fa393e928384e0f8caada38c1f4864a9bfbf379c15` |
| `sentencepiece.bpe.model` | `cfc8146abe2a0488e9e2a0c56de7952f7c11ab059eca145a0a727afce0db2865` |

Do not compare or select among alternative reranker models for v0.1.

## Pair encoding and truncation

- Encode the frozen English `query_en` and candidate passage as the model's
  native cross-encoder pair.
- Use no query instruction, prompt prefix, query rewrite, metadata bonus,
  lexical bonus, or handcrafted financial rule.
- Fixed maximum encoded pair length: 1024 tokens, including special tokens.
- Preserve the query in full. Use passage-only truncation when required
  (`truncation="only_second"` or its exact library equivalent).
- Assert rather than silently truncate if the query plus required special
  tokens cannot fit the fixed pair budget.
- Record deterministic truncation diagnostics during implementation, including
  whether passage truncation occurred and the original and retained token
  counts. Diagnostics must not change v0.1 behavior.

## Scoring and ordering

- Run the cross-encoder as a sequence-classification model and use its raw
  relevance logit as `reranker_score`.
- Do not apply a sigmoid for ranking.
- Do not interpolate with BM25, embedding, or RRF scores.
- Sort first by `reranker_score` descending.
- Resolve exact score ties by `chunk_id` ascending.

## Output contract

Write exactly 50 unique ranked chunks per question. Ranks are contiguous and
1-indexed. Each ranked record must preserve, where available:

- `q_id`;
- frozen `query_en`;
- `chunk_id`;
- raw `reranker_score`;
- 1-indexed `reranker_rank`;
- frozen BM25 rank or null;
- frozen embedding rank or null;
- frozen RRF score when deterministically reconstructable from component
  ranks using `k=60` and weights `1.0/1.0`;
- `hybrid_v0.1` final rank when the chunk appears there, otherwise null;
- accession and document identity fields;
- model ID and exact model revision;
- the candidate-pool definition;
- `max_length=1024`.

The artifact-level metadata must also bind the component input hashes, query
artifact/version, corpus fingerprint, runtime configuration, candidate count
per question, and serialization format. If duplicate component entries for a
`chunk_id` disagree on immutable document or text identity, fail rather than
choose one silently.

Use deterministic UTF-8 JSONL serialization with a fixed key order or sorted
keys, fixed separators, and `\n` line endings. Non-finite scores are invalid.

## Runtime and determinism

The production baseline is frozen as:

- CPU;
- float32;
- `model.eval()`;
- `torch.inference_mode()` or `torch.no_grad()`;
- seed 0;
- 4 intra-op threads;
- 1 inter-op thread;
- fixed batch size 4;
- deterministic execution settings where supported.

Two complete production runs from the same frozen inputs must produce
byte-identical serialized ranking artifacts. A mismatch is a validity failure;
do not choose one run based on benchmark performance.

## Deferred scope

The following are deferred to v0.2 or separately frozen ablations and must not
enter `reranker_v0.1`:

- query rewrite baseline;
- explicit query-decomposition retrieval baseline;
- deeper component candidate pools;
- RRF tuning;
- sliding-window embedding;
- long-context embedding changes;
- score fusion between reranker and RRF;
- numeric-specific fallback rules.

Week 2 agent behavior may generate or search with its own queries. That does
not modify or retroactively redefine any frozen retrieval baseline.
