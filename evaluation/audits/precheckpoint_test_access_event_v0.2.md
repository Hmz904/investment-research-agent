# Third historical pre-checkpoint access incident

Recorded: 2026-09-25. Incident classification:
`UNAUTHORIZED_PRECHECKPOINT_TEST_ACCESS`.

During the prior fresh-clone reproducibility validation session, an over-broad
preflight `rg` search included `review/` and surfaced review text. This was the
third historical accidental pre-checkpoint exposure, not an authorized TEST
checkpoint. This note records the user's incident account without reopening
the exposed material; the precise exposure timestamp was not supplied.

Tracked changes in that session were limited to already-prespecified
reproducibility-gate / tool-spec-gate / inventory maintenance. It is incorrect
to characterize the session as producing "no code". There was no D2 evaluator
design, agent architecture or prompt design, benchmark-driven scoring-rule
modification, real agent output, TEST scoring, or frozen semantic artifact
change.

The authoritative fresh-clone gate was deterministic and isolated and passed
against committed object `232b8e0c8de82d8d1ca8b73016d7d297dda07911`:
401 passed, 0 failed, 41 deselected, with frozen identities unchanged. The
technical gate result remains valid. The exposure remains a permanent
procedural incident; technical validity is not a clean-access certification.

Remediation: root `.ignore`, a fail-closed allowlist sparse development
worktree, and physical absence verification before independent D2 authoring.
Earlier incident notes and access-log records remain unmodified.
