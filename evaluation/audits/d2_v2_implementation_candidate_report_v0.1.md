# D2 v2 implementation candidate report

Verdict: **D2 V2 IMPLEMENTATION CANDIDATE READY**.

The local candidate implements the authenticated v0.2 contracts and passes all
257 unchanged independent contract cases plus 22 implementation checks. It
validates all eight permitted DEV gold bundles and all 17 DEV mapping targets
against the independently authenticated runtime universe. Two separate processes
produce byte-identical input-validation reports and synthetic result hashes.

This is a local, uncommitted implementation candidate on base
`4946e302027f4aab7b09e493ae82f208d5ad75ee`. No merge, tag, push, release, real
agent run, or evaluator freeze has been performed.

## Provisioning and immutable inputs

The only project-data root accessed was
`/mnt/d/projects/thesisagent-d2-v2-runtime-data`. All 45 runtime files passed
size and SHA-256 verification against the tracked bundle manifest, whose SHA-256
is `e5db9ce8b1bebbd2f52ddc7f7b1bd073346506c1ac2dc48b1949a75f4b0835a9`.
Symlinks and unexpected managed files are rejected before XBRL ingestion.

`XBRLTool.from_frozen_ingestion(data_root=...)` independently produced:

- fingerprint: `acaf087ee2c4fb7427377cae5f1968da26c75d4dfa565f67f1e056b2c4cc4eb6`;
- facts: **7,839**, including **640 without chunk linkage**;
- canonical narrative chunks: **1,662**.

The loader fails closed on either fingerprint or count mismatch. The archive
itself was not reopened; archive size/hash verification before extraction remains
the human-provided provisioning evidence. No sibling project-data tree was read.

All 27 entries in `D2_V2_TEST_AUTHOR_FREEZE_SHA256.txt` and all nine authenticated
historical normative imports were reverified. The author manifest remains
`f69e14f586a6d2fd94b5500d05db5a984c8180cd609d3e2582316ef481c29e22`.
The permitted DEV map and four CSV source files were independently compared with
their exact Git blobs at the clean implementation base; those byte hashes are
pinned in the input-validation command and retained in the validation artifact.
No existing tracked file was changed, including frozen schemas, contracts,
fixtures, tests, runtime tools, mappings, and benchmark annotations.

The workspace virtual environment contains the pinned Python packages needed for
XBRL parsing, schema validation, and testing. Its package versions are recorded in
the validation JSON. Package import requires NumPy because the existing tool
package imports retrieval modules. No retrieval instance, model inference,
model-root requirement, model download, or full inference environment was used.

## Implementation

- `evaluation/d2/deterministic_evaluator.py`: explicit scheduled-slot evaluation,
  status separation, CD-01 graph validation, positional multiplicity, coherent
  CD-02 selection, recursive calculation lineage, provenance and metric panels.
- `evaluation/d2/validation_v0_2.py`: strict duplicate-key/Decimal parsing, local
  Draft 2020-12 schemas with format checking, exact precision intervals and units,
  frozen CalculatorTool parsing/arithmetic, and the shared production selector.
- `evaluation/d2/xbrl_v0_2.py`: authenticated runtime loading, complete fact and
  numeric catalogs, independent identity/path validation, and strict concrete
  source-map adaptation before projection.
- `evaluation/d2/source_adapters_v0_2.py`: explicit authenticated DEV CSV and
  normalized v0.1/v0.2 gold adapters. Unsupported encodings fail closed.
- `evaluation/d2/verify_candidate_v0_2.py`: repeatable input-only DEV integration,
  frozen-hash verification, and independent synthetic determinism probes.

The normalized evaluator is a pure request interface. Production callers must
authenticate source bytes/catalogs through the loaders; a supplied fingerprint
string alone is not treated as proof of authenticity. Synthetic test catalogs
exercise the same structural and scoring interface. Source-format dispatch is
explicit, and the split label never selects a scoring algorithm.

The inherited v0.1 gold adapter enriches XBRL paths only from an exact approved
target map and authoritative identity catalog. It rejects missing semantics.
CSV provenance keeps OR paths and AND members; derived input unions remain
lineage, never direct-path shortcuts. Only supported schema-bound representations
are accepted; no checkpoint-time parser repair is implied.

## Eight historical repairs

| Requirement | Candidate behavior |
|---|---|
| A: graph defects | Missing/cyclic references propagate to dependent calculations and claims; retain RUN_COMPLETED, EVAL_OK and the slot; independent direct value credit remains available. |
| B: multiplicity | Expand required occurrences in frozen order; preserve claim-array order and extras; numeric value denominator remains groups. |
| C: tolerance | Reject malformed/negative configuration before scoring; zero is valid; no display-precision fallback after an invalid tolerance. |
| D: quantum | Require exact positive powers of ten; HALF_EVEN candidate rounding compares with unrounded gold; recompute intervals exactly. |
| E: concrete map | Validate full source shape, review partitions/counts, copied identities, temporal selection, source scope and dependency lineage before projection. |
| F: nonmapped states | Preserve unmappable and no-counterpart distinctly; preserve legacy support for derived leaves lacking approved XBRL paths. |
| G: universe | Use all 7,839 identities and separately bound values; distinguish real unapproved facts from forged identities; check optional chunk linkage exactly. |
| H: replacement | Validate one original and at most one replacement in the same slot; exhausted infrastructure is EVAL_INCOMPLETE without a quality zero; terminal failures retain their slot. |

CD-02 uses Unicode lexicographic ID order, including `V10` before `V2`. Passing
candidates take precedence; otherwise every partial diagnostic and input
denominator comes from the same canonical eligible candidate. Empty eligibility
and invalid explicit identifiers follow the frozen conventions. No best-fit
claim assignment or partial-score optimization is performed.

All 42 preregistration rows retain the frozen classification: 39 deterministic
rows and three judge-dependent rows. Every required judge field remains literal
`PENDING_JUDGE`; `deterministic_subtotal` remains null. No proxy judge was added.

## Validation and reproducibility

Final test result: **279 passed; 0 failed; 0 errors; 0 skipped**.
The 257 frozen cases were not edited. The 22 additional checks cover malformed
typed inputs, exact arithmetic under a changed ambient Decimal context,
lexicographic selection, ineligible selector records, source authentication,
v0.1 upgrade, disconnected calculations, XBRL eligibility/false accession,
metric denominators, and equivalence of optimized JSON Schema uniqueness checks.

```sh
PYTHONPATH=tests/evaluation:. .venv/bin/python -m pytest -q tests/evaluation/test_deterministic_evaluator_contract_v0_2.py tests/evaluation/test_d2_v2_implementation_guards.py --disable-warnings
.venv/bin/python -m evaluation.d2.verify_candidate_v0_2 --data-root /mnt/d/projects/thesisagent-d2-v2-runtime-data
```

Real DEV input integration yields eight question bundles, 17 numeric targets,
two DIRECT_APPROVED map targets, one DERIVED_VIA_APPROVED_INPUTS target, and
14 NO_APPROVED_XBRL_PATH targets. These are input-validation counts, not agent
performance results. All other derived targets retain their legitimate legacy
input routes.

Both separate-process validation outputs have SHA-256
`05bcd7d7dea66ed91540c0c3bb8556765efd456f65d01ddac9f9b5973dec6790`.
Catalog, normalized-map, gold-bundle and direct/derived/XBRL/CD-02 synthetic result
hashes are recorded in `d2_v2_implementation_validation_v0.1.json`.

The implementation manifest `D2_V2_IMPLEMENTATION_CANDIDATE_SHA256.txt` binds the
new code, supplemental tests, implementation plan, validation artifact, this
report, and the unchanged test-author manifest. It excludes itself and is
independently checked after generation.

No locked TEST contents, forbidden review tree contents, historical evaluator,
old implementation tests, real agent output, judge, or orchestration logic were
used. References to those sources in permitted documents were not followed.
