"""Bind the Repair-1 candidate without modifying either immutable test manifest.

The final repair commit is supplied after committing production code, avoiding
a cryptographic self-reference. Finalization changes metadata only.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'evaluation/d2/D2_V2_IMPLEMENTATION_CANDIDATE_V0_2_SHA256.txt'
PATHS = [
    'evaluation/d2/D2_V2_TEST_AUTHOR_FREEZE_SHA256.txt',
    'evaluation/d2/D2_V2_AUDIT_REGRESSION_FREEZE_SHA256.txt',
    'evaluation/d2/deterministic_evaluator.py',
    'evaluation/d2/validation_v0_2.py',
    'evaluation/d2/xbrl_v0_2.py',
    'evaluation/d2/source_adapters_v0_2.py',
    'evaluation/d2/verify_candidate_v0_2.py',
    'evaluation/d2/verify_repair1_v0_2.py',
    'evaluation/d2/repair1_candidate_manifest.py',
    'tests/evaluation/test_d2_v2_implementation_guards.py',
    'evaluation/audits/d2_v2_repair1_baseline_v0.2.txt',
    'evaluation/audits/d2_v2_repair1_targeted_tests_v0.2.txt',
    'evaluation/audits/d2_v2_implementation_repair1_validation_v0.2.json',
    'evaluation/audits/d2_v2_implementation_repair1_report_v0.2.md',
]


def generate(repair_commit):
    header = (
        '# D2 v2 implementation candidate v0.2: Repair-1; supersedes blocked v0.1\n'
        '# D2-A: 6a2e577543f8df58e88ba2acda2b14ca945ae1fc\n'
        '# D2-B: 4946e302027f4aab7b09e493ae82f208d5ad75ee\n'
        '# test_author_manifest_sha256: f69e14f586a6d2fd94b5500d05db5a984c8180cd609d3e2582316ef481c29e22\n'
        '# AUDIT_REGRESSION_COMMIT: 08d16333d8081d001c5c5c534c042e7c2acda09c\n'
        '# audit_regression_manifest_sha256: e010615bc9f27a68e5914da5ee3fadfb0cd52b42211b12366586aaa8cba3cd47\n'
        '# blocked_implementation_base: 69beb0dc2b110db26cf3ed6d4b2fdf2ba4193ff4\n'
        f'# D2_REPAIR1_COMMIT: {repair_commit}\n'
    )
    return (header + ''.join(f'{hashlib.sha256((ROOT / p).read_bytes()).hexdigest()}  {p}\n'
                            for p in sorted(PATHS))).encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repair-commit', required=True)
    args = parser.parse_args()
    first, second = generate(args.repair_commit), generate(args.repair_commit)
    assert first == second, 'Manifest double generation differs'
    MANIFEST.write_bytes(first)
    print(hashlib.sha256(first).hexdigest())


if __name__ == '__main__':
    main()
