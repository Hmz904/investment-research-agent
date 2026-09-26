"""Create a deterministic self-excluding successor-only authoring manifest."""
from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).resolve().parents[2]
D2=ROOT/'evaluation/d2'
MANIFEST=D2/'D2_V2_TEST_AUTHOR_FREEZE_SHA256.txt'


def build():
    auth=json.loads((D2/'historical_source_authentication_v0.2.json').read_text())
    historical={ROOT/x['import_path'] for x in auth['imported']}
    files=[p for p in D2.rglob('*') if p.is_file() and p not in historical and p!=MANIFEST]
    files += [ROOT/'evaluation/audits/d2_v2_contract_test_author_report_v0.1.md',
              ROOT/'tests/evaluation/test_deterministic_evaluator_contract_v0_2.py',
              ROOT/'tests/evaluation/d2_v2_contract_fixtures.py',ROOT/'tests/evaluation/d2_v2_cd02_fixture.json',
              ROOT/'packaging/d2_v2_authenticated_allowlist.txt',ROOT/'packaging/d2_v2_authenticated_forbidden_paths.txt']
    assert len(files)==len(set(files))
    assert all(p.is_file() and not p.is_symlink() and '__pycache__' not in p.parts for p in files)
    return ''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(ROOT).as_posix()+'\n' for p in sorted(files)).encode()


if __name__=='__main__':
    first=build();MANIFEST.write_bytes(first)
    second=build();assert first==second,'Artifact mutation between generations';MANIFEST.write_bytes(second)
    for line in second.decode().splitlines():
        expected,relative=line.split('  ',1)
        assert hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()==expected,relative
    print('Every listed artifact hash verified: PASS')
    print('Two generations byte-identical: PASS')
    print('Successor artifact count:',len(second.splitlines()))
    print('Manifest SHA-256:',hashlib.sha256(second).hexdigest())
