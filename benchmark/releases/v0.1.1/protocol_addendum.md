# Benchmark protocol addendum — bench_v0.1.1

Parent release: `bench_v0.1`

`bench_v0.1` and every file under `benchmark/frozen/` remain immutable.
`bench_v0.1.1` is a source-metadata-only errata release. It changes exactly
four evidence-item source contracts through the overlay in
`benchmark/errata/bench_v0.1.1.csv`.

No question wording, claim wording, numeric answer, stance, importance,
temporal role, formula, or answer semantics changed.

## Overlay rules

1. Match an evidence row by `(q_id, q_version, item_id)`.
2. Permit only release-allowlisted source-identification metadata fields.
3. Require the materialized field to equal `old_value` before applying
   `new_value`; otherwise fail.
4. Reject duplicate updates to the same row and field.
5. Preserve every unaffected field and row.
6. Emit and validate a machine-readable release diff.

Provenance used to score this release must bind to the materialized
`bench_v0.1.1` files, not directly to the parent frozen annotations.
