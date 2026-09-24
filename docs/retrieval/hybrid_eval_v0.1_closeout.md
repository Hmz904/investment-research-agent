# `hybrid_eval_v0.1` closeout

## Status and bindings

This document closes the already-frozen `hybrid_v0.1` evaluation. It records
results from the immutable evaluation artifacts; it does not redefine the
evaluation protocol or any retrieval behavior.

- Benchmark: `bench_v0.1.1`
- Gold map: `gold_map_v0.1`
- Ingestion: `ingestion_v0.1.1`
- Retrieval queries: `retrieval_queries_v0.1.1`
- Evaluation protocol: `eval_protocol_v0.1`
- Ranked system: `hybrid_v0.1`
- Evaluation tag: `hybrid_eval_v0.1`
- Evaluation commit: `0afbbf156b5711d0d682e15401d9eee3b5c9b3b2`

The local annotated tag resolves to that exact commit. The worktree was clean
at the start of this documentation session. An `origin` remote exists, but a
read-only `git ls-remote` check found no remote `hybrid_eval_v0.1` tag. No tag
was moved or recreated.

## Hybrid metric panel

All values below come from
`evaluation/results/hybrid_v0.1_scores.json`. Every frozen K is reported.

### Evidence metrics

| K | Part recall | Item coverage | All-parts rate | Weighted strict | Weighted partial | Core recall |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.004273504274 | 0.008849557522 | 0.008849557522 | 0.012765957447 | 0.012765957447 | 0.020408163265 |
| 3 | 0.012820512821 | 0.022123893805 | 0.017699115044 | 0.019148936170 | 0.025531914894 | 0.020408163265 |
| 5 | 0.038461538462 | 0.053097345133 | 0.035398230088 | 0.031914893617 | 0.054255319149 | 0.020408163265 |
| 10 | 0.141025641026 | 0.163716814159 | 0.106194690265 | 0.134042553191 | 0.191489361702 | 0.183673469388 |
| 20 | 0.213675213675 | 0.263274336283 | 0.203539823009 | 0.242553191489 | 0.295478723404 | 0.306122448980 |
| 50 | 0.431623931624 | 0.449410029499 | 0.345132743363 | 0.372340425532 | 0.482127659574 | 0.408163265306 |

### Numeric metrics

| K | Strict fact coverage | Group coverage | Strict multi-input rate | Complete-question rate | Mean input coverage |
|---:|---:|---:|---:|---:|---:|
| 1 | 0.000000000000 | 0.000000000000 | 0.000000000000 | 0.000000000000 | 0.090909090909 |
| 3 | 0.272727272727 | 0.333333333333 | 0.000000000000 | 0.333333333333 | 0.386363636364 |
| 5 | 0.272727272727 | 0.333333333333 | 0.000000000000 | 0.333333333333 | 0.386363636364 |
| 10 | 0.818181818182 | 0.888888888889 | 0.600000000000 | 0.833333333333 | 0.886363636364 |
| 20 | 0.818181818182 | 0.888888888889 | 0.600000000000 | 0.833333333333 | 0.886363636364 |
| 50 | 0.818181818182 | 0.888888888889 | 0.600000000000 | 0.833333333333 | 0.886363636364 |

## Complete aggregate comparison

Each cell is `BM25 / embedding / hybrid`. This reports every frozen aggregate
metric at every frozen K. The authoritative row-wise representation, including
signed `hybrid_minus_bm25` and `hybrid_minus_embedding` columns, is
`evaluation/results/retrieval_comparison_v0.1.csv`. No composite score or
overall winner is defined.

| Metric | K=1 | K=3 | K=5 | K=10 | K=20 | K=50 |
|---|---|---|---|---|---|---|
| Part recall | 0.008547008547 / 0.000000000000 / 0.004273504274 | 0.021367521368 / 0.017094017094 / 0.012820512821 | 0.068376068376 / 0.055555555556 / 0.038461538462 | 0.119658119658 / 0.119658119658 / 0.141025641026 | 0.192307692308 / 0.192307692308 / 0.213675213675 | 0.358974358974 / 0.435897435897 / 0.431623931624 |
| Item coverage | 0.011061946903 / 0.000000000000 / 0.008849557522 | 0.026548672566 / 0.008849557522 / 0.022123893805 | 0.087020648968 / 0.061946902655 / 0.053097345133 | 0.152654867257 / 0.130530973451 / 0.163716814159 | 0.205309734513 / 0.188053097345 / 0.263274336283 | 0.400294985251 / 0.429203539823 / 0.449410029499 |
| All-parts rate | 0.008849557522 / 0.000000000000 / 0.008849557522 | 0.017699115044 / 0.000000000000 / 0.017699115044 | 0.053097345133 / 0.035398230088 / 0.035398230088 | 0.106194690265 / 0.088495575221 / 0.106194690265 | 0.159292035398 / 0.115044247788 / 0.203539823009 | 0.283185840708 / 0.318584070796 / 0.345132743363 |
| Weighted strict | 0.012765957447 / 0.000000000000 / 0.012765957447 | 0.025531914894 / 0.000000000000 / 0.019148936170 | 0.063829787234 / 0.051063829787 / 0.031914893617 | 0.121276595745 / 0.097872340426 / 0.134042553191 | 0.185106382979 / 0.123404255319 / 0.242553191489 | 0.319148936170 / 0.336170212766 / 0.372340425532 |
| Weighted partial | 0.015957446809 / 0.000000000000 / 0.012765957447 | 0.038297872340 / 0.011436170213 / 0.025531914894 | 0.112765957447 / 0.079521276596 / 0.054255319149 | 0.179787234043 / 0.139361702128 / 0.191489361702 | 0.235851063830 / 0.202127659574 / 0.295478723404 | 0.432872340426 / 0.446542553191 / 0.482127659574 |
| Core recall | 0.020408163265 / 0.000000000000 / 0.020408163265 | 0.040816326531 / 0.000000000000 / 0.020408163265 | 0.081632653061 / 0.081632653061 / 0.020408163265 | 0.142857142857 / 0.122448979592 / 0.183673469388 | 0.224489795918 / 0.142857142857 / 0.306122448980 | 0.367346938776 / 0.367346938776 / 0.408163265306 |
| Strict fact coverage | 0.090909090909 / 0.000000000000 / 0.000000000000 | 0.272727272727 / 0.000000000000 / 0.272727272727 | 0.454545454545 / 0.000000000000 / 0.272727272727 | 0.727272727273 / 0.090909090909 / 0.818181818182 | 0.818181818182 / 0.272727272727 / 0.818181818182 | 0.818181818182 / 0.636363636364 / 0.818181818182 |
| Group coverage | 0.111111111111 / 0.000000000000 / 0.000000000000 | 0.333333333333 / 0.000000000000 / 0.333333333333 | 0.555555555556 / 0.000000000000 / 0.333333333333 | 0.777777777778 / 0.111111111111 / 0.888888888889 | 0.888888888889 / 0.333333333333 / 0.888888888889 | 0.888888888889 / 0.666666666667 / 0.888888888889 |
| Strict multi-input rate | 0.000000000000 / 0.000000000000 / 0.000000000000 | 0.000000000000 / 0.000000000000 / 0.000000000000 | 0.400000000000 / 0.000000000000 / 0.000000000000 | 0.600000000000 / 0.000000000000 / 0.600000000000 | 0.600000000000 / 0.000000000000 / 0.600000000000 | 0.600000000000 / 0.200000000000 / 0.600000000000 |
| Complete-question rate | 0.166666666667 / 0.000000000000 / 0.000000000000 | 0.333333333333 / 0.000000000000 / 0.333333333333 | 0.500000000000 / 0.000000000000 / 0.333333333333 | 0.666666666667 / 0.166666666667 / 0.833333333333 | 0.833333333333 / 0.333333333333 / 0.833333333333 | 0.833333333333 / 0.666666666667 / 0.833333333333 |
| Mean input coverage | 0.204545454545 / 0.000000000000 / 0.090909090909 | 0.386363636364 / 0.000000000000 / 0.386363636364 | 0.477272727273 / 0.045454545455 / 0.386363636364 | 0.750000000000 / 0.250000000000 / 0.886363636364 | 0.886363636364 / 0.431818181818 / 0.886363636364 | 0.931818181818 / 0.795454545455 / 0.886363636364 |

## Miss diagnostics

Counts are mechanical labels from the frozen scorer. Labels can overlap, so
category counts need not sum to diagnostic-row counts.

| System | K | Domain | Diagnostic rows | `correct_document_wrong_chunk` | `relevant_chunk_below_k` | `no_relevant_document_in_top50` | `multi_part_partial_hit` |
|---|---:|---|---:|---:|---:|---:|---:|
| BM25 | 10 | Evidence | 101 | 67 | 42 | 15 | 10 |
| Embedding | 10 | Evidence | 103 | 84 | 49 | 8 | 11 |
| Hybrid | 10 | Evidence | 101 | 68 | 49 | 8 | 13 |
| BM25 | 10 | Numeric | 3 | 1 | 3 | 0 | 1 |
| Embedding | 10 | Numeric | 10 | 10 | 6 | 0 | 3 |
| Hybrid | 10 | Numeric | 2 | 2 | 0 | 0 | 1 |
| BM25 | 50 | Evidence | 81 | 76 | 0 | 15 | 27 |
| Embedding | 50 | Evidence | 77 | 77 | 0 | 8 | 26 |
| Hybrid | 50 | Evidence | 74 | 73 | 0 | 8 | 25 |
| BM25 | 50 | Numeric | 2 | 2 | 0 | 0 | 2 |
| Embedding | 50 | Numeric | 4 | 4 | 0 | 0 | 3 |
| Hybrid | 50 | Numeric | 2 | 2 | 0 | 0 | 1 |

## Legacy compatibility diagnostic

`relevant_document_below_k_wrong_chunk` is retained as a legacy compatibility
diagnostic. It is not added to the canonical four-category protocol.

Its operational definition comes from `_miss_row` in the frozen scorer, not
from its name. The scorer first computes a non-complete evidence-item or
numeric-fact row and appends any applicable canonical labels in this order:

1. `multi_part_partial_hit` when at least one required state is hit and the
   item/fact has more than one required state;
2. `relevant_chunk_below_k` when an approved candidate chunk for a missing
   requirement appears in the saved top 50 at a rank greater than K;
3. `correct_document_wrong_chunk` when an accession associated with any
   missing requirement occurs in the retrieved top K;
4. `no_relevant_document_in_top50` when at least one missing requirement has
   none of its associated accessions in the saved top 50.

Only if the label list is still empty does the scorer append
`relevant_document_below_k_wrong_chunk`. Therefore, for every missing
requirement represented by such a row:

- no required state was hit in a way that triggers the partial-hit label;
- no approved candidate chunk occurs at ranks K+1 through 50;
- no associated accession occurs in the top K; and
- every missing requirement has at least one associated accession somewhere
  in the saved top 50.

At K=10 this mechanically corresponds to the relevant accession being present
only below K within the saved top 50 while the approved chunk is absent from
that range, subject to the no-partial condition above. This statement follows
the predicates in the code; the label text itself is not used to infer the
definition.

The legacy label cannot overlap any canonical label on the same row because
it is appended only when none has been appended. The same `_miss_row` function
is used for evidence and numeric diagnostics and for BM25, embedding, and
hybrid, so its semantics are identical across all three systems. The frozen
artifacts contain the following counts:

| System | K=10 evidence | K=10 numeric | K=50 evidence | K=50 numeric |
|---|---:|---:|---:|---:|
| BM25 | 15 | 0 | 0 | 0 |
| Embedding | 12 | 0 | 0 | 0 |
| Hybrid | 18 | 0 | 0 | 0 |

It was retained because changing or removing it would alter frozen diagnostic
semantics and would prevent byte-identical reproduction of the historical
BM25 and embedding evaluation artifacts.

## Evaluation-side change review

The reviewed range was `e5e2aa4..0afbbf1` for
`evaluation/score_retrieval.py` and
`tests/evaluation/test_score_retrieval.py`.

The scorer change is limited to the evaluation-side system/metadata
generalization needed to recognize and validate the flat hybrid metadata,
enforce the frozen hybrid result depth, serialize its configuration binding,
and produce the requested three-system aggregate and per-question comparison.
Evidence scoring, numeric scoring, K values, metric definitions, miss
construction, and all diagnostic-label logic are unchanged. No production
retrieval module is imported or modified.

Regression coverage retains the existing byte-identical BM25 reproduction
test, adds byte-identical reproduction checks for all historical embedding
evaluation outputs, and tests the hybrid metadata binding and deterministic
three-way comparison schema.

## Frozen artifact hashes

| Artifact | SHA-256 |
|---|---|
| `evaluation/results/hybrid_v0.1_scores.json` | `bd0a59fbcd6de7dad10e879b90d3f7176e98dfa1f4a6fe642adbe406647afef8` |
| `evaluation/results/hybrid_v0.1_per_question.csv` | `edf9f51d747dbfcc551d367e1da4f77955b0567da1ba45f44bce526bc1e0ea94` |
| `evaluation/results/hybrid_v0.1_misses.csv` | `b84af0a3c49d87ca98869760dc73d4ca795ff30c0bb2b0e537608c0ab36da9fd` |
| `evaluation/results/retrieval_comparison_v0.1.csv` | `414d6751b83cde6ab3e503c0a950dc3f9f5001f7000679987b4a26a46a457372` |
