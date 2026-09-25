# Pre-checkpoint TEST access event v0.1

Incident classification: `UNAUTHORIZED_PRECHECKPOINT_TEST_ACCESS`

Before this clean-room session, a restricted pre-freeze audit accidentally emitted lines from `benchmark/provenance/numeric_facts_draft.json` and `benchmark/provenance/gold/numeric_fact_provenance.json`. The cause was an over-broad text search. The access occurred before an authorized TEST checkpoint. No TEST scoring or agent output generation occurred.

The affected audit explicitly stated that its substantive conclusions did not rely on the inadvertently emitted snippets. Nevertheless, that audit is invalid as clean anti-leakage certification.

This session starts from a physically isolated clean room and must not rely on any leaked TEST-provenance content.
