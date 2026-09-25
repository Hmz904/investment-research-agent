# Temporal v0.1.2 reproducibility erratum v0.1

This erratum corrects a reproducibility omission. It does not change temporal
row or conflict semantics and does not reactivate abandoned v0.1.1 logic.

The historical migration input
`evaluation/xbrl/fiscal_period_resolution_v0.1.json` was present when the
v0.1.2 temporal artifacts were produced but was omitted from Git. Its omission
changed only the migration metadata path responsible for
`predecessor_rows_recomputed_from_source`, from 50 to 0. Consequently, the
catalog and coverage bytes could not be regenerated from tracked repository
content alone even though the temporal rows and conflicts were semantically
unaffected.

The restored input has SHA-256:

`667e35a2ad2423876bd9ed21b8eba3ea8034fc3b4e4f8665eab76b817a5fa95e`

It is classified as both **HISTORICAL MIGRATION INPUT** and
**VALIDATION/REPRODUCIBILITY INPUT**. The exact historical bytes were recovered
from a prior cleanroom; no historical artifact was regenerated. The other 15
abandoned v0.1.1 files remain excluded, and abandoned v0.1.1 semantic logic
remains inactive.

The earlier benchmark/provenance explanation for the regeneration defect was
incorrect. A separate ignored-data and absolute-path packaging defect was
subsequently identified and is outside this minimal temporal erratum.

All existing tags remain immutable.
