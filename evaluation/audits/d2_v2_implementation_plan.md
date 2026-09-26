# D2 v2 implementation plan

Base: 4946e302027f4aab7b09e493ae82f208d5ad75ee.
Frozen test-author manifest: f69e14f586a6d2fd94b5500d05db5a984c8180cd609d3e2582316ef481c29e22.

The resumed preflight independently verified all 27 frozen manifest entries and
all 45 project-data files against the tracked runtime bundle manifest
e5db9ce8b1bebbd2f52ddc7f7b1bd073346506c1ac2dc48b1949a75f4b0835a9.
The only project-data root is /mnt/d/projects/thesisagent-d2-v2-runtime-data.
XBRLTool.from_frozen_ingestion with explicit data_root produced fingerprint
acaf087ee2c4fb7427377cae5f1968da26c75d4dfa565f67f1e056b2c4cc4eb6
and exactly 7,839 facts. No model root or inference is needed.

Implementation order:
1. Strict parsing, local schema validation, exact precision and component APIs.
2. Full-universe identity validation, authenticated runtime loading, and strict
   concrete DEV map normalization before projection.
3. Slot validation, CD-01 graph handling, positional occurrence assignment,
   CD-02 coherent variant diagnostics, lineage, and deterministic metric panel.
4. Unchanged independent suite, real DEV input integration, byte/hash repeatability,
   and final frozen-file hash verification.
5. Candidate report and implementation artifact manifest, or an explicit blocker.

No frozen contract/test edits, TEST contents, real agent outputs, judge,
orchestrator changes, model provisioning, merge, tag, or push are included.
The historical evaluator is absent from this checkout; implementation will be
written from the authenticated contracts and independent tests.
