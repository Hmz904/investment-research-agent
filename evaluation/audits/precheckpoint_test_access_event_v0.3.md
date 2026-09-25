# Current-session sparse-boundary exposure incident

Recorded: 2026-09-25T16:26:40Z (recording time, not exact command start).
Classification: `UNAUTHORIZED_PRECHECKPOINT_TEST_ACCESS`.

The three historical incidents are recorded separately. This is a new fourth
accidental pre-checkpoint exposure, in the isolation / independent D2 v2
contract-author session.

The allowlist mistakenly admitted `benchmark/frozen/protocol.md`. The prior
D2 preregistration references this document as a legacy semantics source;
the author treated the protocol filename/reference as sufficient evidence
that the entire file was safe. A subsequent explicit `cat` of that file in
the sparse worktree emitted question-specific locked TEST rules and benchmark
notes. No question-specific contents are reproduced in this incident note.

The exposure bypassed no sparse rule: the rule itself was incomplete. The
earlier physical-absence verification accurately checked its declared list,
but that list omitted this mixed-content document. Therefore the initial
isolation commit is not a sufficient isolation certificate. A normative
document reference does not prove every section is development-safe.

The author stopped independent D2 contract/test design immediately after
recognizing the exposure. Before exposure, the session had authored a partial
v0.2 supplement, one proposed unresolved decision, and seven candidate machine
schemas, and imported nine historical normative files. These remain unfinished
and must not be presented as an independent freeze. No independent test suite
or complete 42-row reconstruction was authored. This session produced code-like
machine contracts and documentation; it must not be described as producing
"no code" or "no design".

No old evaluator implementation or implementation-authored evaluator test was
opened/imported. No evaluator tests ran. No real DEV/TEST agent outputs, judge,
locked benchmark scoring, implementation repair, tags, push, or Release assets
were produced. The previous committed-object fresh-clone technical gate was
not rerun or changed by this event.

Remediation: remove this exact mixed-content path from the sparse allowlist,
add it to the forbidden-path inventory and root `.ignore`, verify physical
absence again, and preserve the partial artifacts with an explicit blocked
report. Do not exclude all of `benchmark/frozen/` by pattern. Future legitimate
non-TEST files require explicit independent boundary evidence before admission.

The present session cannot certify no TEST access. A new clean authoring
session with the corrected boundary is required; do not inspect or repair the
evaluator yet. This permanent procedural record does not erase or rewrite the
three historical incidents.
