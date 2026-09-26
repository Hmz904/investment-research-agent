# Pre-scoring ordering regression provenance

Source: the user-supplied closed final re-audit finding against candidate
229003a46ea33321d0573ad94e2f4bb128f5a21a. Enforcement is MANDATORY_PRECHECK,
but the DEV runner executes tests/harness/determinism before validate_dev().
Post-scoring reportability rejection does not satisfy pre-scoring enforcement.

The additive regression instruments the existing runner's three scoring-related
entrypoints. Its negative control copies exactly the NF004 metadata mutation in
the frozen test_inconsistent_metadata_fails in
tests/evaluation/test_d2_v2_1_dev_self_consistency.py (patch-freeze manifest
49508f8c7421a93910f5188de629f277f44f37d05a2b178e9226e6d554bf0545).
No new precision case or fixture is introduced. The positive control uses the
unchanged validate_dev() and all 17 permitted targets.

Required negative observation: frozen inputs checked, integrity precheck fails,
zero scoring callback invocations, checkpoint invalid and NON-REPORTABLE,
repair/versioning and rerun required, no scoring validation/aggregate payload.
Required positive observation: frozen inputs checked, 17/17 integrity PASS,
then exactly one instrumented scoring callback invocation per mode.

This file and the additive test alone form the ordering regression freeze.
They must be committed before production workflow changes. Historical and
successor tests, normative integrity code and contract artifacts stay unchanged.
