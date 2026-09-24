# Retrieval Evaluation Protocol v0.1

Status:

- **RETROSPECTIVE documentation/freeze for `bm25_v0.1`**
- **PROSPECTIVE frozen evaluation protocol for all subsequent retrieval systems**

This document was written after the first gold evaluation of `bm25_v0.1`.
It is not a preregistration for that BM25 evaluation and does not claim that
its metric panel was selected before the BM25 results were observed. It
records and freezes the scoring semantics and metrics that were actually used.

For every later retrieval system—including `embedding_v0.1`, `hybrid_v0.1`,
`reranker_v0.1`, and subsequent versions—this document is prospective: the
protocol is frozen before that system's gold results are observed and must be
applied without performance-driven changes.

## Experimental chronology

1. Clean-room retrieval queries were generated.
2. `bm25_v0.1` was implemented without access to gold relevance judgments.
3. `bm25_v0.1` was frozen.
4. The first BM25 gold evaluation was performed.
5. The evaluation protocol was formally documented and frozen in this file.
6. All later retrieval methods will use this frozen protocol prospectively.

The chronology above is part of the experimental record. In particular, step
5 must not be described as preceding or preregistering step 4.

## Frozen dependency and artifact bindings

| Dependency or artifact | Version/path | SHA-256 or binding |
|---|---|---|
| Benchmark release | `bench_v0.1.1` | frozen release |
| Gold map | `gold_map_v0.1` | `dfc5246bc625085b9412eb0918444751f944930905fbbd4b33cb97adda50ed57` |
| Retrieval queries | `benchmark/retrieval_queries_v0.1.csv` | `4de3208bf457e0670d691e95284c5675006c825be85a2dca159e6f5268a61c1c` |
| Retrieval-query freeze commit | `4ee3bb8` | contains the authoritative root-level query artifact above |
| Retrieval-query freeze tag | `retrieval_queries_v0.1.1` | corrected immutable tag |
| BM25 version/tag | `bm25_v0.1` | immutable existing tag |
| BM25 ranked results | `evaluation/results/bm25_v0.1.jsonl` | `7e276b409b9bebafa3b31acc105d253f90595bf652e2936446995bd5ae6611e1` |
| BM25 scores | `evaluation/results/bm25_v0.1_scores.json` | `ce4bbd92446869b43b57d11ea9fdf0c1fb83a19775395d4eca71ad3a34c0b3d0` |
| BM25 per-question results | `evaluation/results/bm25_v0.1_per_question.csv` | `e8c95984c0afab82f6670b8d172ad4a7b3f2f4c3569b956868c8cd8834954c7f` |
| BM25 miss diagnostics | `evaluation/results/bm25_v0.1_misses.csv` | `6630141d744a0bc62396cfa28cfa66ad8b5d7dc809d60b1f88148395c656cf7c` |

The earlier `retrieval_queries_v0.1` tag is a historical misbinding: it was
created at a commit that did not contain the required root-level
`benchmark/retrieval_queries_v0.1.csv` artifact. That historical tag must not
be moved or rewritten. The authoritative query binding for this protocol is
the file and SHA-256 shown above at freeze commit `4ee3bb8`, immutably tagged
as `retrieval_queries_v0.1.1`.

The query-freeze prerequisite is satisfied. An exact consistency check
confirmed that all 16 `q_id -> query_en` mappings in the authoritative query
artifact match the queries embedded in the already frozen `bm25_v0.1` ranked
result. This was a mapping-identity check only; it did not alter the frozen
result or the retrospective status of its evaluation.

The BM25 ranked results must not be recomputed or modified. The historical
BM25 evaluation artifacts above must remain byte-identical. Later systems
must bind to the same benchmark release, gold map, retrieval-query mapping,
and corpus unless a separately versioned protocol explicitly supersedes this
one.

Before evaluating a future system, verify that the exact `q_id -> query_en`
mapping in `benchmark/retrieval_queries_v0.1.csv` matches the mapping embedded
in that system's frozen ranked-result artifact. This is an identity check,
not a relevance or performance check. A mismatch is a blocker and neither
artifact may be silently changed.

## Frozen provenance semantics

### Evidence provenance

- Parts within a final evidence item are AND requirements.
- Candidate chunks within one part are OR alternatives.
- A part is hit at K when any approved candidate for that part occurs in the
  top K.
- Item coverage at K is the number of hit required parts divided by the
  number of required parts.
- An item satisfies all-parts at K only when every required part is hit.
- Final approved merge lineage is used exactly as represented in gold;
  superseded draft mappings are not reconstructed.

### Numeric provenance

- Candidate chunks for a direct fact are OR alternatives.
- A derived fact requires all of its finalized input facts recursively.
- A derived fact's candidate-chunk union is provenance metadata, not an OR
  shortcut.
- Only `role=answer` facts participate directly in numeric answer scoring.
- Verified variants in the same answer group are OR alternatives.
- Distinct answer groups within one question are AND requirements.

These semantics were used for the first BM25 evaluation and must not be
changed in response to its observed results.

## Frozen K values

Evaluate every system at:

`K = 1, 3, 5, 10, 20, 50`

No K may be added, removed, or selected as the headline K based on observed
performance under protocol v0.1.

## Frozen metric panel

### Evidence metrics

1. **Part recall at K** — fraction of final evidence parts whose OR candidate
   set is hit.
2. **Item coverage at K** — mean fraction of required parts hit per evidence
   item.
3. **All-parts rate at K** — fraction of evidence items for which every final
   required part is hit.
4. **Benchmark-weighted strict score at K** — importance-weighted strict
   all-parts item recovery using only the benchmark-defined weights:
   `core=3.0`, `supporting=1.5`, and `optional=0.5`.
5. **Weighted partial coverage at K** — the same benchmark importance weights
   applied to item coverage rather than strict completion.
6. **Core recall at K** — unweighted strict all-parts recovery among core
   evidence items.

Question-level evidence results must also be retained so aggregate results do
not hide difficult questions.

### Numeric metrics

1. **Strict fact coverage at K** — fraction of scored answer-fact variants
   whose complete provenance requirements are retrieved.
2. **Group coverage at K** — fraction of answer groups for which at least one
   verified answer variant has complete provenance retrieval.
3. **Strict multi-input rate at K** — fraction of multi-input derived answer
   facts for which every required input provenance component is retrieved.
4. **Complete-question rate at K** — fraction of numeric questions for which
   every required answer group is hit.
5. **Mean input coverage at K** — mean fraction of required provenance inputs
   retrieved across scored answer-fact variants.

Evidence and numeric metrics remain separate. No composite benchmark score is
defined.

## No retroactive primary metric

The frozen benchmark protocol did not define one overall primary or headline
retrieval metric. Accordingly, `bm25_v0.1` is reported as the metric panel
above. This document does not retroactively select a primary metric after
observing BM25 performance.

Future systems must also be reported using the complete frozen panel. A new
primary metric may be introduced only by a separately versioned protocol that
is frozen before the affected systems' gold results are observed; it must not
be back-projected as preregistered for `bm25_v0.1`.

## Frozen miss diagnostics

At K=10 and K=50, retain deterministic item/fact miss diagnostics and the
following mechanical failure labels:

- `correct_document_wrong_chunk`
- `relevant_chunk_below_k`
- `no_relevant_document_in_top50`
- `multi_part_partial_hit`

Diagnostics must preserve q_id, item/fact identity, missing requirements,
approved candidate chunk IDs, retrieved top-K chunk IDs, relevant-accession
wrong-chunk status, and first relevant rank below K when present within the
saved top 50. Diagnostics must not be used to tune a system after its results
are observed under the same version.

## Future-system evaluation gate

Before revealing gold scores for any later retrieval system:

1. Freeze and identify the system's ranked-result artifact and SHA-256.
2. Verify its query mapping against
   `benchmark/retrieval_queries_v0.1.csv` without inspecting retrieval
   quality.
3. Verify the benchmark, gold-map, corpus, and query-artifact bindings.
4. Run the complete repository test suite from the project virtual
   environment:

   ```bash
   ./.venv/bin/python -m pytest -q
   ```

5. Apply the existing scorer and the complete metric panel at every frozen K.
6. Produce deterministic score, per-question, and miss-diagnostic artifacts
   without changing retrieval outputs or scoring semantics.

Question-level bootstrap confidence intervals are not part of protocol v0.1.
If added later, they must be identified as a post-BM25 protocol amendment,
specified before the affected future systems are evaluated, and applied
identically to every future system. They must never be presented as
preregistered for the first BM25 evaluation.
