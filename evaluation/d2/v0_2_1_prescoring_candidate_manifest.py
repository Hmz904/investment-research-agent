"""Generate the successor operational candidate twice, preserving prior identity.

As with the preceding candidate, a metadata-only follow-up binds the actual
operational patch commit after it exists, avoiding a self-referential Git hash.
"""
import argparse
import hashlib
import re

from .v0_2_1_candidate_manifest import ROOT, PATHS as PREVIOUS_PATHS

MANIFEST = ROOT / 'evaluation/d2/D2_V2_1_IMPLEMENTATION_CANDIDATE_V0_2_SHA256.txt'
REGRESSION_COMMIT = '651c172f0ef5d952caf8df744c0b1316f592efb3'
PATHS = sorted(set(PREVIOUS_PATHS) | {
    'evaluation/d2/D2_V2_1_IMPLEMENTATION_CANDIDATE_SHA256.txt',
    'evaluation/d2/D2_V2_1_PRESCORING_GATE_REGRESSION_SHA256.txt',
    'evaluation/d2/prescoring_gate_v0_2_1.py',
    'evaluation/d2/v0_2_1_prescoring_candidate_manifest.py',
    'tests/evaluation/test_d2_v2_1_prescoring_gate.py',
    'evaluation/audits/d2_v2_1_prescoring_regression_provenance.md',
    'evaluation/audits/d2_v2_1_prescoring_gate_report.md',
    'evaluation/audits/d2_v2_1_prescoring_gate_validation.json',
    'evaluation/audits/d2_v2_1_prescoring_gate_tests.txt',
})


def generate(patch_commit):
    assert patch_commit == 'PENDING_LOCAL_COMMIT' or re.fullmatch('[0-9a-f]{40}', patch_commit)
    header = (
        '# D2 v0.2.1 successor implementation candidate v0.2: operational pre-scoring gate\n'
        '# D2_V021_CONTRACT_PATCH_COMMIT: 0b6d22fc563dec40b0ae0ad643b30d0d1792d207\n'
        '# patch_freeze_manifest_sha256: 49508f8c7421a93910f5188de629f277f44f37d05a2b178e9226e6d554bf0545\n'
        '# D2_V021_IMPLEMENTATION_COMMIT: 02c55adfd6b93d8cd55a0f0322442ca87c223fe0\n'
        '# previous_candidate_metadata_commit: 229003a46ea33321d0573ad94e2f4bb128f5a21a\n'
        '# previous_candidate_manifest_sha256: 063cf8d12f4f090ec8e8e2c09dde177823115815194fdeb1a86b2e5bc7581a6d\n'
        f'# PRESCORING_REGRESSION_COMMIT: {REGRESSION_COMMIT}\n'
        '# prescoring_regression_manifest_sha256: d3b979c154a8dfbb290c9da6d23c2765dfac4e1af2f5922bfa46e584c184b496\n'
        f'# D2_PRESCORING_GATE_COMMIT: {patch_commit}\n'
    )
    return (header + ''.join(f'{hashlib.sha256((ROOT / p).read_bytes()).hexdigest()}  {p}\n'
                             for p in PATHS)).encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--patch-commit', required=True)
    args = parser.parse_args()
    first, second = generate(args.patch_commit), generate(args.patch_commit)
    assert first == second, 'Manifest double generation differs'
    MANIFEST.write_bytes(first)
    for line in first.decode().splitlines():
        if not line.startswith('#'):
            sha, path = line.split(maxsplit=1)
            assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == sha
    print(hashlib.sha256(first).hexdigest())


if __name__ == '__main__':
    main()
