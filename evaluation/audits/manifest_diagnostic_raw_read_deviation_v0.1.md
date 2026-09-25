# Manifest Diagnostic Raw-Read Deviation v0.1

Date: 2026-09-25

## Status

CLOSED — superseded by explicit ingestion test isolation.

## Event

During diagnosis of the `data/manifest.json` test-side-effect issue, a
disposable diagnostic workspace inherited absolute `local_path` values from
the copied corpus manifest.

As a result, the diagnostic reproduction read 14 raw corpus files from the
main repository rather than exclusively from the disposable workspace.

## Boundary impact

- Access was read-only.
- No locked TEST/gold material was accessed.
- No main-repository file was modified.
- No canonical corpus content changed.
- No mapping, temporal, or evaluation semantics changed.

After the external-path dependency was discovered, no further diagnostic
pytest experiments were run under that configuration.

## Root cause

The copied manifest contained absolute raw-file `local_path` values, while
the ingestion pipeline exposed only the module-level canonical `DATA_DIR`.
The diagnostic copy therefore remained capable of resolving raw inputs
outside its intended isolation root.

## Remediation

`src.pipeline.run()` was changed to support an explicit `data_dir` while
preserving the original default production behavior.

The ingestion integration test was made self-contained:

- raw inputs are copied beneath `tmp_path`;
- manifest `local_path` values are rewritten beneath that temporary tree;
- path-confinement assertions prevent escape from the isolated corpus;
- the real pipeline runs against the explicit temporary `data_dir`.

Post-fix validation showed:

- targeted ingestion test passed;
- restricted suite passed: 402 passed, 41 deselected;
- final full suite passed: 443 passed;
- canonical `data/manifest.json` remained byte-identical;
- corpus fingerprint remained
  `56df698d50b13cf15e913c1c60dbc96b1fd0fab44adb7b1f40ba99771c4b7c96`.

## Future hygiene

Disposable or clean-room environments should reject or rewrite absolute
manifest paths that resolve outside the intended isolation root.
