# D2 sparse development boundary v0.1

Purpose: prevent accidental working-tree exposure before the TEST checkpoint
and preserve independence of the D2 contract/test author.

`packaging/d2_sparse_paths_v0.1.txt` is an exact-file allowlist for non-cone
sparse checkout. Entries were selected from Git path metadata, the
`locked_test_data` marker, the existing access notes, the production-boundary
path list, and evaluation protocols. Forbidden contents were not inspected.
It admits runtime source, evaluation protocols/schemas, execution taxonomy,
permitted DEV inputs, and narrowly selected test infrastructure. It excludes
each currently known locked file in `benchmark/frozen/` by exact path,
including its mixed-content protocol. The initial allowlist mistakenly
admitted that protocol; see `precheckpoint_test_access_event_v0.3.md`. This
correction does not introduce a blanket exclusion for future non-TEST files.
New D2 contract/test files may be authored locally and added explicitly.
Historical D2 normative documents absent from the base commit may be imported
by exact filename and recorded with source hashes; never copy the evaluator
or old evaluator tests.

Create from the latest isolation correction commit, not the superseded
initial isolation commit (no full checkout occurs first):

```sh
git worktree add --no-checkout -b d2-v2-contract-tests /tmp/thesisagent-d2-v2-dev ISOLATION_COMMIT
git -C /tmp/thesisagent-d2-v2-dev sparse-checkout init --no-cone
git -C /tmp/thesisagent-d2-v2-dev sparse-checkout set --no-cone --stdin < packaging/d2_sparse_paths_v0.1.txt
git -C /tmp/thesisagent-d2-v2-dev read-tree -mu HEAD
```

`/tmp/thesisagent-d2-v2-dev` is the default because it is an authorized writable
root in this environment. A persistent sibling location requires filesystem
approval. Commits remain in the canonical repository's shared Git database.
Do not copy ignored/untracked files, caches, environment files, or `data/`.

Verify each path in `packaging/d2_forbidden_paths_v0.1.txt` with `test ! -e`;
also reject symlinks at those paths. Verify ordinary `rg --files` emits none
of those paths or their descendants. Repeat after imports and before freeze.
The old evaluator and implementation-authored test file are forbidden even
when they are absent from the source commit. No tests may execute in the
test-author session; only standalone schema/fixture and syntax checks.

Protection: broad ordinary searches and accidental file opens cannot read
material physically omitted from this worktree. Exact-file allowlisting also
omits unclassified new paths until deliberately reviewed by metadata.

Limitations: `.ignore` is a convenience layer, bypassable by `rg --no-ignore`,
explicit file arguments, and Git-history commands. Git history still contains
historical objects: this protects against ACCIDENTAL working-tree exposure,
not deliberate git-object retrieval. Other worktrees, absolute paths, mounts,
runtime data provisioning, and new untracked files can bypass the boundary.
This is not a sandbox or an OS security boundary. Do not disable sparsity,
merge, switch to a broader checkout, provision data, or run the old evaluator
during independent authoring. A later implementation session needs an explicit
boundary transition to admit implementation files while retaining TEST isolation.
