"""Generate the v0.2.1 candidate manifest twice; finalize after code commit.

A metadata-only follow-up binds the actual implementation commit, avoiding a
self-referential Git hash. Historical candidate manifests remain untouched.
"""
import argparse
import hashlib
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT/'evaluation/d2/D2_V2_1_IMPLEMENTATION_CANDIDATE_SHA256.txt'
PATHS = [
    'evaluation/d2/D2_V2_TEST_AUTHOR_FREEZE_SHA256.txt',
    'evaluation/d2/D2_V2_AUDIT_REGRESSION_FREEZE_SHA256.txt',
    'evaluation/d2/D2_V2_1_TEST_AUTHOR_PATCH_FREEZE_SHA256.txt',
    'evaluation/d2/deterministic_evaluator.py',
    'evaluation/d2/validation_v0_2.py',
    'evaluation/d2/xbrl_v0_2.py',
    'evaluation/d2/source_adapters_v0_2.py',
    'evaluation/d2/verify_candidate_v0_2.py',
    'evaluation/d2/verify_repair1_v0_2.py',
    'evaluation/d2/verify_v0_2_1.py',
    'evaluation/d2/v0_2_1_candidate_manifest.py',
    'tests/evaluation/test_d2_v2_implementation_guards.py',
    'evaluation/audits/d2_v2_1_implementation_validation.json',
    'evaluation/audits/d2_v2_1_implementation_tests.txt',
    'evaluation/audits/d2_v2_1_implementation_report.md',
]


def generate(implementation_commit):
    assert implementation_commit == 'PENDING_LOCAL_COMMIT' or re.fullmatch('[0-9a-f]{40}', implementation_commit)
    header = (
        '# D2 v0.2.1 implementation candidate; external interpretation of historical wire inputs\n'
        '# D2-A: 6a2e577543f8df58e88ba2acda2b14ca945ae1fc\n'
        '# D2-B: 4946e302027f4aab7b09e493ae82f208d5ad75ee\n'
        '# historical_test_manifest_sha256: f69e14f586a6d2fd94b5500d05db5a984c8180cd609d3e2582316ef481c29e22\n'
        '# original_implementation: 69beb0dc2b110db26cf3ed6d4b2fdf2ba4193ff4\n'
        '# repair1_regression_commit: 08d16333d8081d001c5c5c534c042e7c2acda09c\n'
        '# repair1_regression_manifest_sha256: e010615bc9f27a68e5914da5ee3fadfb0cd52b42211b12366586aaa8cba3cd47\n'
        '# repair1_implementation: 20d6efd74e466dcc592768b43efdb38b59fba44a\n'
        '# repair1_final_candidate: 0bcf1f32524df3a555ef0f09b15c0e4bdd9fb60d\n'
        '# D2_V021_CONTRACT_PATCH_COMMIT: 0b6d22fc563dec40b0ae0ad643b30d0d1792d207\n'
        '# patch_freeze_manifest_sha256: 49508f8c7421a93910f5188de629f277f44f37d05a2b178e9226e6d554bf0545\n'
        f'# D2_V021_IMPLEMENTATION_COMMIT: {implementation_commit}\n'
    )
    return (header + ''.join(f'{hashlib.sha256((ROOT/p).read_bytes()).hexdigest()}  {p}\n'
                            for p in sorted(PATHS))).encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--implementation-commit', required=True)
    args = parser.parse_args()
    first, second = generate(args.implementation_commit), generate(args.implementation_commit)
    assert first == second, 'Manifest double generation differs'
    MANIFEST.write_bytes(first)
    for line in first.decode().splitlines():
        if not line.startswith('#'):
            sha, path = line.split(maxsplit=1)
            assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest() == sha
    print(hashlib.sha256(first).hexdigest())


if __name__ == '__main__':
    main()
