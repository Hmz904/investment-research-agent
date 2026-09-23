# Benchmark errata overlays

Errata overlays correct source-identification metadata without modifying the
immutable files under `benchmark/frozen/`. An overlay is applied by exact row
identity and exact old value; a mismatch fails materialization.

For `bench_v0.1.1`, the target row identity is `(q_id, q_version, item_id)` in
`evidence_checklist.csv`.

Allowed metadata-only fields for this release:

- `accession`
- `location`
- other source-identification metadata only when explicitly added to the
  release allowlist and covered by a release-diff test

Disallowed without a true question or item version bump:

- question or claim wording
- numeric answers or values
- stance, importance, or temporal role
- formulas or answer semantics
- any other semantic annotation

Materialization must be deterministic, must preserve unaffected rows and files,
and must emit a machine-readable release diff. The materialized release—not the
parent frozen directory—is the benchmark source to which release provenance is
bound.
