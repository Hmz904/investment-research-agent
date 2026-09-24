# Week 2 agent precommit v0.1

## Status

This policy is frozen before `reranker_v0.1` gold evaluation and before Week 2
agent prompt or tool-policy iteration. It separates development from locked
testing and prevents post-hoc retriever selection.

## Precommitted retrieval backend

The default Week 2 agent retrieval backend is fixed as:

```text
frozen bm25_v0.1 top 50 UNION frozen embedding_v0.1 top 50
-> reranker_v0.1
-> ranked retrieval output
```

This choice is fixed regardless of `reranker_v0.1` gold performance. The
backend must not be selected between hybrid and reranker after observing the
reranker evaluation.

The only permitted reason not to use `reranker_v0.1` is a non-performance
validity failure, such as:

- a corrupted artifact;
- a candidate-set invariant violation;
- a non-reproducible ranking;
- an implementation or runtime failure that prevents valid execution.

A poor benchmark score is not an allowed fallback reason. `hybrid_v0.1`
remains a frozen comparison baseline and upstream historical baseline; it is
not a post-hoc fallback chosen using the test set.

## Locked-test policy

From this commit onward, the existing 16-question benchmark is the locked
test set.

- Do not tune agent prompts against its answers.
- Do not tune tool policies against its per-question failures.
- Do not change agent logic in response to its evaluation results.
- Evaluate only an already-frozen agent version against it.
- Test results may motivate a new, separately versioned agent, but must not
  mutate the version already evaluated.

Retrieval experiments completed before this boundary remain historically
valid and must be described honestly as prior retrieval-stage evaluation.

## Week 2 development set policy

Before agent prompt iteration, Week 2 will create a separate development set
with exactly eight questions:

- three numeric questions;
- five evidence, thesis, update, or comparison questions.

Every development question must be answerable from the existing frozen
14-document corpus. Its target facts or evidence must not duplicate the locked
16-question benchmark targets. Development questions may cover the same
general failure-mode taxonomy, but must use different target facts and
evidence. Lightweight, source-anchored annotations are sufficient.

The development set may be used freely for prompt and tool-policy iteration.
Development results are not test results. This policy freezes the set design;
the eight questions are not created in this session.

## End-to-end evaluation gate

Before the first locked-test agent run,
`evaluation/eval_protocol_v0.2.md` must be written and frozen. It will define
end-to-end answer and citation evaluation.

**No locked-test agent execution is permitted before `eval_protocol_v0.2` is
frozen.**

The full v0.2 protocol is outside this precommit document and is not created
in this session.

## Future scope boundary

The following remain deferred to v0.2 or separately frozen ablations:

- query rewrite baseline;
- explicit query-decomposition retrieval baseline;
- deeper component candidate pools;
- RRF tuning;
- sliding-window embedding;
- long-context embedding changes;
- score fusion between reranker and RRF;
- numeric-specific fallback rules.

Week 2 agent behavior may generate or search with its own queries. Such agent
behavior does not retroactively modify the frozen BM25, embedding, hybrid, or
reranker retrieval baselines.
