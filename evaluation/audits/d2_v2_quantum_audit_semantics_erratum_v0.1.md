# D2 v2 QUANTUM audit semantics erratum v0.1

This is a prospective expectation correction for D2 v0.2.1. The original
150-probe harness, inputs, observations and pass/fail evidence remain immutable.
No TEST material was involved. No production evaluator was inspected or run.

## Source adjudication

Exact sections used:

1. Historical D2 contract supplement v0.1 §R7, “PrecisionRecord v0.1”: candidate
   and gold are independently quantized using ROUND_HALF_EVEN.
2. Evaluation protocol v0.2.2 §2, “Gold-recorded precision and numeric matching”:
   positive power-of-ten display quantum and the same Decimal equivalence rule.
3. XBRL gold mapping specification v0.1 §3, “Gold-recorded precision,” and §3.1,
   “Registered rules,” including the paragraph defining the interval from the
   frozen display value. The equation's gold operand does not require the raw
   stored reference to be an exact unrounded operand.
4. XBRL gold mapping specification v0.1.2, “Version lineage and exact delta”:
   v0.1 precision rules are inherited unchanged.

The clean human adjudication established that D2 v0.2 §S5 introduced S2's
raw-reference restriction and empty-preimage rule. The higher-level source did
not require them. S1 is Q_q(candidate)==Q_q(reference), where
Q_q(x)=q*round_half_even(x/q), with a common positive power-of-ten q.

## Exactly two successor expectation changes

| Original probe name | Historical expected behavior | v0.2.1 expected behavior |
|---|---|---|
| inconsistent_derived_output_precision | EVAL_INPUT_INVALID (“reject inconsistent gold precision before scoring”) | EVAL_OK and complete_numeric_answer=true |
| offgrid_gold | EVAL_OK and complete_numeric_answer=false | EVAL_OK and complete_numeric_answer=true |

D19's original input is historical evidence: target EXACT 37, derived reference
37 and QUANTUM 10. Under S1, Q_10(37)=40 on both sides, so 37 satisfies both
constraints. The historical expected EVAL_INPUT_INVALID depended on S2 and was
not a valid inference from the higher-level source. No CD-03 is introduced.

The original D19 record also stores (37,37), both endpoints excluded. That
interval is derived from superseded S2 semantics. The authorized v0.2.1
normalization preserves original request bytes and derives comparison semantics
from reference, quantum and ROUND_HALF_EVEN. Prefer direct quantized equality;
if emitted diagnostically, its S1 interval is [35,45], inclusive. This is an
explicit versioned normalization change, not silent repair of historical data.

offgrid_gold uses candidate 37.1, reference 37.1 and q=1. Both operands quantize
to 37, so the existing complete synthetic input passes under S1. Its empty S2
interval is superseded in the same way. No other expectation changes.

The successor representation contains 150 ordered probe entries, 148 identical
expectations and precisely these two replacements. Input constructors and
parameters remain bound to the unchanged historical harness. The replacement
predicates apply only to new evaluation under v0.2.1; historical observed results
and passed flags are never recalculated or rewritten. No probe 151 is added.

## Artifact identities

Historical evidence root:
`/mnt/d/projects/d2-v2-independent-audit-blocked-v0.1`.

| Identity | SHA-256 |
|---|---|
| Original all_probe_results.json | c667cb78fcf60e65f6277a0e04496a0222b90bacd847b63094febae57aaee606 |
| Original row_evidence.json | 3bd990818c88d218c7cc8e5e4bdc88b5f3fe8d3b174156b58f397c68ae55d942 |
| Original probes.py | f50f818c5fe7d9ce99b976fa3c749f2a0b59506a7e5dd3c8c5c79bdffcfe3a70 |
| Original D19 request bytes | e0fb2e80d3cee77ae99fc383c3e3e394c16bb54769f9063d03384be1c7e758b4 |
| Original seven-file harness identity | f0c0ee4320be80ccfe6d053308ed7f52ee62088190541c5f5066c7dc8aa978d9 |
| Successor d2_v2_audit_expectations_v0.2.json | 0aa76243856afde1e2d67193ad87a0b17e77dc72a8254b8e93496e52445f0357 |

The historical harness identity is SHA-256 of sorted UTF-8 lines
`<file_sha256>  <relative_name>\n` for the seven source files enumerated in the
successor artifact. Individual source hashes and the D19 request dependency
are recorded there. The successor logical harness identity is the pair of that
unchanged source identity and the successor expectation-artifact hash; runtime
path selection must not alter constructors, predicates outside the two names,
or input content. No executable historical harness source is replaced here.

## Frozen contract-test traceability

The original 257 cases remain unchanged. Their D10 parameter case
candidate=1.24/reference=1.23/q=0.1 also has an S2 expected failure. The successor
precision suite adds the S1 pass expectation. A future run must disclose that
historical expectation as superseded rather than edit, skip, or silently xfail
it. This is distinct from the 150-probe harness's exactly two replacements.

The prior local blocker report records the user's earlier decisions; the user's
subsequent explicit correction authorizes both changes and versioned interval
normalization. That report is preserved as session history and is not part of
the normative patch freeze.
