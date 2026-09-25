# Frozen fresh-clone reproducibility v0.1

The frozen runtime has two independently verified payloads:

- `frozen_runtime_bundle_v0.1.json` declares the 45 project-owned data files.
- `frozen_model_payloads_v0.1.json` declares the 12 logical model files at two
  immutable Hugging Face revisions. Model weights are not part of the project
  data archive.

`data/manifest.json` is preserved byte-for-byte. Its absolute `local_path`
values are historical metadata only. Frozen runtime code constructs raw paths
only beneath an explicit `data_root`, verifies every raw SHA-256, and has no
legacy absolute-path or network fallback.

## Environment

Use CPython 3.14.7 on Linux x86_64 and install the version lock:

```text
python3.14 -m venv .venv
.venv/bin/python -m pip install --requirement requirements.lock
.venv/bin/python scripts/verify_frozen_environment.py
```

The verifier binds the environment to the lock-file SHA-256 recorded in
`frozen_environment_v0.1.json`. `requirements.lock` pins exact package
versions but does not contain distribution hashes; this is a version-locked
environment, not a cryptographically locked wheel set.

The retrieval determinism sentinel is certified only for Linux x86_64,
CPython 3.14.7, CPU PyTorch, and the exact package versions in the lock. Other
platforms may run successfully, but their ranking hash is not certified. A
sentinel mismatch on another architecture or backend, including macOS ARM,
is an environment-identity failure and is not automatically an
implementation defect.

## Provisioning

Online project-data provisioning uses the future immutable Release URL (never
`latest`) and downloads model files only at their declared commit revisions:

```text
.venv/bin/python scripts/provision_frozen_data.py \
  --data-root "$PWD/data" \
  --bundle <immutable-release-asset-url> \
  --model-root "$PWD/data/frozen_models"
```

For offline CI/audit, the offline directory contains the registered archive at
its exact asset name and model files at
`models/<model-id-with-slashes-replaced-by-double-hyphens>/<revision>/<file>`:

```text
.venv/bin/python scripts/provision_frozen_data.py \
  --data-root "$PWD/data" \
  --bundle thesisagent-frozen-runtime-data-v0.1.tar \
  --model-root "$PWD/data/frozen_models" \
  --offline-bundle-dir /absolute/path/to/offline-payloads
```

Both destinations must be explicit absolute paths. `--verify-only` performs no
mutation. Provisioning verifies archive and per-file hashes, rejects unsafe or
unexpected archive content, stages both payloads completely, and then installs
new destination trees by atomic rename.

## Frozen checks

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  -m evaluation.build_temporal_context_catalog --check --data-root "$PWD/data"
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  -m evaluation.materialize_dev_xbrl_map_v0_1 --check --data-root "$PWD/data"
PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python -m evaluation.validate_retrieval_determinism --check \
  --data-root "$PWD/data" --model-root "$PWD/data/frozen_models"
```

The permanent freeze gate accepts only an explicit offline payload directory,
creates a randomized non-local clone, installs through the provisioner, runs
the complete suite selected by `-m "not locked_test_data"` plus the frozen
checks, and requires the tracked tree to remain clean. Python-level network
connections are disabled during frozen validation; this is not a claim that
the entire operating system has no network access.

```text
.venv/bin/python scripts/fresh_clone_freeze_gate.py \
  --offline-bundle-dir /absolute/path/to/offline-payloads \
  --bundle thesisagent-frozen-runtime-data-v0.1.tar
```

## Runtime-facing changes and preserved identities

- Ingestion and `src.pipeline.run` distinguish explicit frozen mode from
  discovery mode and accept an explicit `data_root`.
- `XBRLTool.from_frozen_ingestion` accepts an explicit `data_root` and never
  treats historical manifest paths as runtime-authoritative.
- `RetrievalTool.from_frozen_stack` accepts explicit `data_root` and
  `model_root` values.
- `ToolRegistry.from_frozen_tools` accepts and passes explicit `data_root` and
  `model_root` values. These are construction parameters, not model-visible
  tool arguments.
- The embedding and reranker stack loads only verified payloads below the
  explicit `model_root`.

These runtime-root changes preserve the semantic retrieval ranking identity,
XBRL fingerprint, corpus fingerprint, and model-visible tool specification.
The historical and candidate tool-spec SHA-256 is
`879a710485ac42b6dc0793b0556ce811d4efb151b52a7ae69f90334d489db70d`.

## Test-selection reconciliation

The earlier 397-test rehearsal used an explicit path subset. Relative to the
current 400-test non-locked collection it omitted the four tests in
`tests/evaluation/test_dev_xbrl_mapping_artifacts.py` and included one test in
`tests/test_reranker_retrieval.py` that is marked `locked_test_data`; hence
`400 - 4 + 1 = 397`. The gate now uses the complete non-locked marker
selection.

The earlier 443-test baseline comprised 402 non-locked and 41 locked tests.
That worktree included 16 tests from the three subsequently abandoned v0.1.1
test modules. Those modules remain excluded, while this repair adds 14 new
collected reproducibility cases. Collection-only reconciliation is therefore
441 total tests: 400 non-locked and 41 locked. No test ceased collection
because of an explicit-root API change.

The independent post-commit audit must run the complete
`pytest -q -m "not locked_test_data"` selection. After that passes, the human
operator must run complete main-repository `pytest -q`, including all
`locked_test_data` tests.

## Future version and release placement

No correction tag is created by the candidate commits. After independent
audit, both `temporal_context_catalog_v0.1.1` and the umbrella
`frozen_runtime_repro_v0.1` should point to the final Phase-B reproducibility
commit. The former certifies the corrected fresh-clone-reproducible temporal
package; Phase A remains referenced by the erratum but receives no separate
temporal tag.

The component-level runtime changes above do not presently require separate
`ingestion_v0.1.2`, `xbrl_tool_v0.1.1`, `retrieval_tool_v0.1.1`,
`tool_runtime_v0.1.1`, or `retrieval_stack_v0.1.1` tags. An independent audit
may recommend them if it establishes a strong reason.

The intended data release tag is `frozen_runtime_data_v0.1`, also pointing to
the final Phase-B commit. Only after independent audit and post-commit
fresh-clone validation may the immutable
`thesisagent-frozen-runtime-data-v0.1.tar` asset be attached. There is no
mutable `latest` alias.
