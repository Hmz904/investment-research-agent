# XBRL temporal freeze handoff v0.1

This is post-freeze administrative documentation. It is not part of the three frozen packages and does not move their tags.

## A. Freeze status

**LOCAL TECHNICAL FREEZE COMPLETE**

Independent pre-freeze audit: **FREEZE READY**

**BLOCKERS: NONE**

Full main-repository test: **443 passed in 104.65s**

## B. Commit topology

| Commit | Full SHA | Purpose |
| --- | --- | --- |
| Commit 1 | `48851744c4e05e777e27e1c74264ac419e3c2213` | Test isolation and TEST-access boundary |
| Commit 2 | `b84bf129f441d32cf8496e0cdd746935b6fd54a6` | v0.1.2 XBRL temporal specification/catalog |
| Commit 3 | `f1a14d1bbf16bc5d7835a49e5d6419a0cdc8012b` | Human-reviewed DEV XBRL map |
| Commit 4 | `6f6d4a32e5e95ce6a89e509a31e85920b5100f0b` | Post-freeze audit-history documentation |

## C. Frozen annotated tags

| Annotated tag | Tag object SHA | Peeled commit SHA |
| --- | --- | --- |
| `xbrl_gold_mapping_spec_v0.1.2` | `660296a30843dc08cfd19b1bb291cd71de8bc19c` | `b84bf129f441d32cf8496e0cdd746935b6fd54a6` (Commit 2) |
| `temporal_context_catalog_v0.1` | `37026ce687e0dc6bd0f733e5f4a562f705a80127` | `b84bf129f441d32cf8496e0cdd746935b6fd54a6` (Commit 2) |
| `dev_xbrl_map_v0.1` | `3af6343e8241e629f73506fecfab2cc185db0248` | `f1a14d1bbf16bc5d7835a49e5d6419a0cdc8012b` (Commit 3) |

Commit 4 and this handoff commit are outside the frozen-tag boundary.

## D. Corpus identity

- Entries: **14**
- Corpus fingerprint: `56df698d50b13cf15e913c1c60dbc96b1fd0fab44adb7b1f40ba99771c4b7c96`
- `data/manifest.json` SHA-256: `8498751b5d862950c800f92904492cf332b099842000c475941ac6cd7f8c8339`

The ingestion isolation fix did not alter corpus identity.

## E. Data-tree validation

| Inventory | Count |
| --- | ---: |
| Audit clean room: audited data files | 45 |
| Main repository: data files | 132 |
| `ONLY_MAIN` | 87 |
| `ONLY_AUD` | 0 |
| `CHANGED` | 0 |

The 87 additional main-repository files are pre-existing runtime/local material, primarily `model_cache/**` and `provenance/**`. The audit-cleanroom inventory digest is not the complete main-repository data digest.

The complete main-repository pre/post-full-pytest inventory-manifest digest observed was `3462abc2cb2d69dadea5c9289f85c82f9c1bdaa68b1b2f10cb103112e02c85d3`; it was byte-identical before and after the 443-test run.

## F. Temporal/XBRL frozen state

The final temporal catalog contains **2505 rows**:

- `DIRECTLY_OBSERVED_CONTEXT`: 2066
- `DETERMINISTICALLY_DERIVED`: 44
- `MERGED_AGREEING_EVIDENCE`: 395

Unsafe month-only authoritative inference `table_duration_end_months_to_start_v0.1` has status **RETIRED / REJECTED AS AUTHORITATIVE TEMPORAL RULE**. Active rows from this retired month-only rule: **0**.

## G. Conflict coverage

Dimension conflict:

- 464 diagnostics
- 89 affected chunks
- 0 affected chunks without surviving direct-XBRL exact-temporal coverage

Period-metadata conflict:

- 204 diagnostics
- 45 affected chunks
- 0 affected chunks without surviving direct-XBRL exact-temporal coverage
- 0 affected chunks without surviving authoritative temporal catalog coverage

These are **CHUNK-LEVEL** coverage statements only.

## H. DEV map

There are **17 numeric DEV targets**.

- Direct mapped: `NF012`, `NF013`
- Derived: `NF003`, `NF004`, `NF009`, `NF010`, `NF011`, `NF014`, `NF015`, `NF016`, `NF017`
- Unmappable: `NF001`, `NF002`, `NF005`, `NF006`, `NF007`, `NF008`
- Reason for all six unmappable targets: `TEMPORAL_NO_ANCHOR_METADATA`

Approved XBRL provenance paths exist for `NF012`, `NF013`, and `NF014`. Therefore, **3 / 17 numeric DEV targets have approved XBRL provenance paths**. The other 14 are not characterized as invalid; legacy chunk provenance remains valid.

## I. Direct human-approved XBRL mappings

### NF012

- TCC: `TCC-31b1f6eab46385db`
- Candidate: `XBRLCAND-64c41d8cf6d297f8`
- Concept: `us-gaap:IncomeTaxesPaidNet`
- Value: `541000000 USD`
- Period: `2026-01-01` → `2026-03-31`
- Dimensions: `[]`
- Context: `c-1`

### NF013

- TCC: `TCC-f5206ab8eb1933a4`
- Candidate: `XBRLCAND-7c4b2618999be1ab`
- Concept: `us-gaap:IncomeTaxesPaidNet`
- Value: `1999000000 USD`
- Period: `2026-01-01` → `2026-06-30`
- Dimensions: `[]`
- Context: `c-1`

## J. Cross-entity validation

- META A: **PASS**
- META I: **PASS**
- NVIDIA A: **PASS**
- NVIDIA I: **PASS**
- MICROSOFT A: **PASS**
- MICROSOFT I: **PASS**

All Category I validations exercised genuine Stage 3 with nonempty exact dimensions.

## K. Key artifact hashes

| Artifact | SHA-256 |
| --- | --- |
| `evaluation/xbrl/temporal_context_catalog_v0.1.json` | `63f6ec4bcbe5319ad9d63fa2186fdc23b4b78cdf5d7df4ff10d179245d161478` |
| `evaluation/xbrl/temporal_rule_review_v0.1.csv` | `a4216560b550e2865a0642eb00057f9d1258c8f438f8a48331d29b8cd87a5109` |
| `evaluation/xbrl/temporal_conflict_review_sample_v0.1.csv` | `03c032f8e14219f8a424f842cdb8502ad0600ac189ed0655a6a09f86c94ae535` |
| `evaluation/dev/xbrl/dev_temporal_human_review_v0.1.csv` | `e596b207f168f844bdeecd346b32397703023bd88a7b1e4ef34d1579b1d1d98e` |
| `evaluation/dev/xbrl/dev_xbrl_mapping_review_packet_v0.1.csv` | `1fcc56252dff3460717703e63dadc4b4a978bf9e335bd9fef517e8f7e1489bcd` |
| `evaluation/dev/xbrl/dev_xbrl_map_v0.1.json` | `f129bf95b8a3428922ca5b87171f61e7a15481fc34586c37e22dfa23d33a2a53` |
| `evaluation/dev/xbrl/dev_xbrl_map_coverage_v0.1.json` | `59ef14f5ed7ffa7ba3eaea42abcde8100759c43d8d0633b09d9d44c70a3796cc` |
| `evaluation/xbrl/temporal_pseudo_target_selection_v0.2.json` | `ad6bd7a7a5b9972008c111b7bca2690c95055666976b37ebe85de7d0cf174660` |
| `evaluation/xbrl/temporal_pseudo_target_validation_v0.2.json` | `f383b209e9bdeeea4e69d1eba5235a99b94db0674923e4e912113c2f0a988a2d` |
| Original D1: `evaluation/dev/xbrl/dev_xbrl_mapping_candidates_v0.1.json` | `2816b480f73f13d9490b4c75b758dbb60d36b295d6f618943b72a2681b7aad56` |

## L. Historical boundary events

### 1. Historical unauthorized pre-checkpoint TEST/provenance access

- Persistent record: `evaluation/audits/precheckpoint_test_access_event_v0.1.md`
- Classification: `UNAUTHORIZED_PRECHECKPOINT_TEST_ACCESS`
- Important: `evaluation/test_access_log.csv` does **not** contain a separate row with this exact event ID.

### 2. D1 restricted-session procedural deviation

- Persistent record: `evaluation/audits/d1_procedural_deviation_v0.1.md`
- Full pytest was run during a restricted DEV session. Quiet output exposed no assertion diff or TEST content, but the procedure was violated.

### 3. Mapping-contract repair access note

- Persistent record: `evaluation/audits/mapping_contract_repair_access_note_v0.1.md`
- Embedded release-integrity metadata from test source code was printed while classifying locked-test markers.

### 4. Manifest diagnostic raw-file read

- Persistent record: `evaluation/audits/manifest_diagnostic_raw_read_deviation_v0.1.md`
- A disposable diagnostic workspace followed absolute manifest `local_path` values and read 14 main-repository raw files.
- It was read-only, involved no locked TEST/gold access, made no main-repository modification, and was superseded by explicit `data_dir` test isolation.

## M. Known limitations

- XBRL provenance coverage is deliberately conservative.
- Exact authoritative temporal metadata is sparse.
- Only 3/17 numeric DEV targets have an approved XBRL provenance path.
- Legacy chunk provenance remains valid elsewhere.
- The evaluator prefers false negatives to heuristic temporal inference.
- Sparse XBRL coverage is not retrieval failure.
- DEV and historical TEST retrieval evaluation share the same frozen corpus: target-level holdout, not document/chunk holdout.
- TEST was not historically virgin because Week-1 retrieval evaluation had already used the TEST questions.
- The agent-level TEST lock begins under the later preregistered protocol.
- Absolute manifest `local_path` values remain an isolation-hygiene concern.
- A future v0.2 may separate temporal identity and dimensional semantics more explicitly.

## N. Abandoned v0.1.1 branch

The fiscal-label resolver / v0.1.1 line is **ABANDONED** and **NEVER FROZEN**. It was superseded by v0.1.2 exact temporal binding. Its remaining local untracked files are not part of the frozen package and must not be staged.

## O. Next work

Primary next task: **D2 deterministic evaluator**.

Before judge-model optimization:

- Implement the deterministic evaluator.
- Freeze evaluator semantics.
- Freeze structured provenance validation.
- Freeze derived-calculation validation.
- Use the frozen DEV XBRL map.
- Preserve TEST checkpoint restrictions.

The production/model line can proceed in parallel:

- Choose the model.
- Run a compatibility probe.
- Decide K.
- Decide oversized-XBRL-result behavior.
- Decide table-header rendering.

Deferred coordinated revision package:

- `execution_taxonomy_v0.1.1`: `FAIL_CONTEXT_WINDOW_EXCEEDED`; add `EVT_TOOL_RESULT_TOO_LARGE` if needed.
- `eval_protocol_v0.2.3`.
- `agent_architecture_v0.2`: same-turn retries, policy-event fields, model-specific tool behavior, and `submit_answer` only if the compatibility probe justifies it.

Do not mix those changes into the frozen v0.1.2 package.
