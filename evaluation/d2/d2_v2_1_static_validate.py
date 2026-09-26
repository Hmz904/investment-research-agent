"""Static patch validation only. Never imports or runs a production evaluator."""
import ast
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import runpy
import sys

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]
D2 = ROOT/'evaluation/d2'
AUDIT = Path('/mnt/d/projects/d2-v2-independent-audit-blocked-v0.1')
FROZEN = {
    'D2_V2_TEST_AUTHOR_FREEZE_SHA256.txt': 'f69e14f586a6d2fd94b5500d05db5a984c8180cd609d3e2582316ef481c29e22',
    'D2_V2_AUDIT_REGRESSION_FREEZE_SHA256.txt': 'e010615bc9f27a68e5914da5ee3fadfb0cd52b42211b12366586aaa8cba3cd47',
}
PATCH_FILES = [
    'evaluation/d2/deterministic_evaluator_contract_supplement_v0.2.1.md',
    'evaluation/d2/precision_record_v0.2.1.schema.json',
    'evaluation/audits/d2_v2_quantum_audit_semantics_erratum_v0.1.md',
    'evaluation/audits/d2_v2_audit_expectations_v0.2.json',
    'tests/evaluation/d2_v2_1_precision_fixtures.py',
    'tests/evaluation/test_d2_v2_1_precision_contract.py',
    'evaluation/d2/dev_numeric_self_consistency_v0_2_1.py',
    'tests/evaluation/test_d2_v2_1_dev_self_consistency.py',
    'evaluation/d2/d2_v2_1_dev_numeric_self_consistency.json',
    'evaluation/d2/d2_v2_1_preregistration_42_row_matrix.json',
    'evaluation/d2/d2_v2_1_preregistration_42_row_matrix.md',
    'evaluation/d2/d2_v2_1_static_validate.py',
    'evaluation/d2/d2_v2_1_static_validation.json',
    'evaluation/audits/d2_v2_1_contract_patch_report_v0.1.md',
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_history():
    counts = {}
    for name, digest in FROZEN.items():
        manifest = D2/name
        assert sha(manifest) == digest
        entries = [line.split(maxsplit=1) for line in manifest.read_text().splitlines()
                   if line and not line.startswith('#')]
        for expected, name in entries:
            assert name.startswith(('evaluation/d2/', 'evaluation/audits/', 'tests/evaluation/', 'packaging/'))
            assert 'deterministic_evaluator.py' not in name
            assert sha(ROOT/name) == expected, name
        counts[manifest.name] = len(entries)
    auth = json.loads((D2/'historical_source_authentication_v0.2.json').read_text())
    for entry in auth['imported']:
        assert entry['import_path'].startswith('evaluation/d2/')
        assert sha(ROOT/entry['import_path']) == entry['historical_sha256']
    return counts


def test_cases(path):
    source = path.read_text()
    compile(source, str(path), 'exec')
    cases = []
    for node in ast.parse(source).body:
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith('test_'):
            continue
        count = 1
        for deco in node.decorator_list:
            if isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute) and deco.func.attr == 'parametrize':
                assert isinstance(deco.args[1], (ast.List, ast.Tuple))
                count *= len(deco.args[1].elts)
        cases.append({'name': node.name, 'cases': count})
    return cases


def validate():
    history = frozen_history()
    schema_paths = sorted(D2.glob('*.schema.json')) + [ROOT/'evaluation/agent_output_schema_v0.1.1.json']
    schemas = {p.name: json.loads(p.read_text()) for p in schema_paths}
    successor = schemas['precision_record_v0.2.1.schema.json']
    Draft202012Validator.check_schema(successor)
    registry = Registry().with_resources((s['$id'], Resource.from_contents(s)) for s in schemas.values())
    def check(name, data):
        Draft202012Validator(schemas[name], registry=registry, format_checker=FormatChecker()).validate(data)
    # Only this machine schema literally encoded S2; no unrelated schema versioning.
    s2 = []
    for name, schema in schemas.items():
        if 'v0.2.' in name and any(term in json.dumps(schema).lower() for term in ['unrounded gold', 'off-grid reference has an empty']):
            s2.append(name)
    assert s2 == ['precision_record_v0.2.schema.json']
    for name in [p for p in PATCH_FILES if p.endswith('.py')]:
        compile((ROOT/name).read_text(), str(ROOT/name), 'exec')
    cases = test_cases(ROOT/'tests/evaluation/test_d2_v2_1_precision_contract.py')
    assert sum(c['cases'] for c in cases) == 11
    assert sum(c['cases'] for c in test_cases(ROOT/'tests/evaluation/test_deterministic_evaluator_contract_v0_2.py')) == 257
    # Execute only independent math and fixture builders. Never import a test
    # module or production evaluation package, and never collect evaluator tests.
    gate = runpy.run_path(str(D2/'dev_numeric_self_consistency_v0_2_1.py'))
    sys.path.insert(0, str(ROOT/'tests/evaluation'))
    fixtures = runpy.run_path(str(ROOT/'tests/evaluation/d2_v2_1_precision_fixtures.py'))
    tree = ast.parse((ROOT/'tests/evaluation/test_d2_v2_1_precision_contract.py').read_text())
    quantum_cases = ast.literal_eval(next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'test_S1_quantum_classes').decorator_list[0].args[1])
    requests = []
    for c, r, q, lo, hi, inc, expected in quantum_cases:
        assert gate['matches'](c, r, 'QUANTUM', q) is expected
        requests.append(fixtures['quantum_request'](c, r, q, lo, hi, inc))
    requests += [fixtures['d19_request'](c) for c in ['37', '38']]
    requests.append(fixtures['quantum_request']('56.0', '56.0468756436', '0.1', '55.95', '56.05', True))
    projections = 0
    def project(record):
        nonlocal projections
        check('precision_record_v0.2.schema.json', record)
        normalized = deepcopy(record)
        normalized['precision_schema_version'] = 'precision_record_v0.2.1'
        if normalized['mode'] == 'QUANTUM':
            gate['quantum'](normalized['quantum'])
            assert normalized['rounding_mode'] == 'ROUND_HALF_EVEN'
            del normalized['interval']
        check('precision_record_v0.2.1.schema.json', normalized)
        projections += 1
    def inspect_records(value):
        if isinstance(value, dict):
            if 'precision_schema_version' in value:
                project(value)
            for child in value.values():
                inspect_records(child)
        elif isinstance(value, list):
            for child in value:
                inspect_records(child)
    for request in requests:
        check('evaluation_request_v0.2.schema.json', request)
        check('agent_output_schema_v0.1.1.json', json.loads(request['agent_output_json']))
        inspect_records(request)
    # Schema/domain negative control, without a production validator.
    bad = deepcopy(requests[0]['gold_bundle']['numeric_targets'][0]['precision'])
    bad['precision_schema_version'] = 'precision_record_v0.2.1'
    bad['quantum'] = '0.03'
    try:
        check('precision_record_v0.2.1.schema.json', bad)
    except ValidationError:
        pass
    else:
        raise AssertionError('invalid quantum accepted by successor schema')
    artifact_path = ROOT/'evaluation/audits/d2_v2_audit_expectations_v0.2.json'
    artifact = json.loads(artifact_path.read_text())
    assert sha(AUDIT/'all_probe_results.json') == artifact['historical_all_probe_results_sha256']
    assert sha(AUDIT/'row_evidence.json') == '3bd990818c88d218c7cc8e5e4bdc88b5f3fe8d3b174156b58f397c68ae55d942'
    for name, digest in artifact['historical_harness_source_sha256'].items():
        assert '/' not in name
        assert sha(AUDIT/name) == digest
    lines = ''.join(f'{digest}  {name}\n' for name, digest in sorted(artifact['historical_harness_source_sha256'].items()))
    assert hashlib.sha256(lines.encode()).hexdigest() == artifact['historical_harness_identity_sha256']
    original = json.loads((AUDIT/'all_probe_results.json').read_text())
    old = [{k:r[k] for k in ['name', 'rows', 'expected']} for r in original]
    new = artifact['probes']
    assert len(old) == len(new) == artifact['probe_count'] == 150
    changed = []
    for a, b in zip(old, new):
        assert a.keys() == b.keys() and a['name'] == b['name'] and a['rows'] == b['rows']
        if a['expected'] != b['expected']:
            changed.append(a['name'])
    assert set(changed) == {'inconsistent_derived_output_precision', 'offgrid_gold'} and len(changed) == 2
    assert artifact['unchanged_expectation_count'] == 148 and artifact['changed_expectation_count'] == 2
    for change in artifact['changes']:
        assert change['old_expected'] == next(r['expected'] for r in old if r['name'] == change['name'])
        assert change['new_expected'] == next(r['expected'] for r in new if r['name'] == change['name'])
        assert change['successor_result_requirements'] == {'evaluator_status': 'EVAL_OK', 'metrics.complete_numeric_answer': True}
    d19 = AUDIT/artifact['historical_d19_request']['path']
    assert sha(d19) == artifact['historical_d19_request']['sha256']
    raw = d19.read_bytes()
    request = json.loads(raw)
    check('evaluation_request_v0.2.schema.json', request)
    inspect_records(request)
    v = request['gold_bundle']['answer_groups'][0]['variants'][0]
    assert v['precision']['mode'] == 'EXACT' and v['accepted_value'] == '37'
    p = v['derived_specification']['output_precision']
    assert (p['reference_value'], p['quantum'], p['rounding_mode']) == ('37', '10', 'ROUND_HALF_EVEN')
    assert p['interval'] == {'lower':'37', 'upper':'37', 'lower_inclusive':False, 'upper_inclusive':False}
    assert gate['satisfies']('37', [{'reference':'37', 'mode':'EXACT'}, {'reference':'37', 'mode':'QUANTUM', 'parameter':'10'}])
    assert d19.read_bytes() == raw
    before = json.loads((D2/'d2_v2_preregistration_42_row_matrix.json').read_text())
    after = json.loads((D2/'d2_v2_1_preregistration_42_row_matrix.json').read_text())
    assert [r['row_id'] for r in before] == [r['row_id'] for r in after] == [f'D{i:02}' for i in range(1,43)]
    assert [a['row_id'] for a,b in zip(before,after) if a != b] == ['D10','D19']
    counts = dict(Counter(r['classification'] for r in after))
    assert counts == {'COVERED_DETERMINISTIC':39, 'PENDING_JUDGE':3}
    counts['CONTRACT_DECISION_REQUIRED'] = 0
    test_names = {c['name'] for c in cases + test_cases(ROOT/'tests/evaluation/test_deterministic_evaluator_contract_v0_2.py')}
    for row in after:
        assert set(row['independent_tests']) <= test_names
        assert all((D2/p).is_file() for p in row['machine_schema'])
    dev = gate['validate_dev']()
    assert dev == json.loads((D2/'d2_v2_1_dev_numeric_self_consistency.json').read_text())
    assert not any(name.endswith('deterministic_evaluator') for name in sys.modules)
    return {'validation_kind':'static_authoring_only', 'historical_manifest_entries':history,
            'historical_normative_imports_verified':9, 'new_schemas_validated':['precision_record_v0.2.1.schema.json'],
            'historical_257_cases_unchanged':True, 'patch_test_cases':cases, 'patch_test_count':11,
            'fixture_requests_shape_validated':len(requests)+1, 'precision_projections_shape_validated':projections,
            'audit_probe_count':150, 'audit_expectations_unchanged':148, 'audit_expectations_changed':changed,
            'audit_input_policy':'unchanged original constructors and request bytes; expectation-only successor representation',
            'd19_original_input_sha256':sha(d19), 'd19_original_bytes_unchanged':True,
            'historical_harness_identity_sha256':artifact['historical_harness_identity_sha256'],
            'successor_expectation_sha256':sha(artifact_path), 'matrix':counts,
            'dev_total':dev['total'], 'dev_passed':dev['passed'],
            'production_evaluator_imported':False, 'production_evaluator_tests_run':False,
            'TEST_accessed':False, 'judge_used':False, 'real_agent_output_used':False}


def manifest():
    header = '# D2 v0.2.1 test-author patch freeze\n'
    header += '# Immutable v0.2 test-author manifest SHA-256: '+FROZEN['D2_V2_TEST_AUTHOR_FREEZE_SHA256.txt']+'\n'
    header += '# Immutable Repair-1 regression manifest SHA-256: '+FROZEN['D2_V2_AUDIT_REGRESSION_FREEZE_SHA256.txt']+'\n'
    return header + ''.join(f'{sha(ROOT/name)}  {name}\n' for name in sorted(PATCH_FILES))


if __name__ == '__main__':
    if sys.argv[1:] == ['--manifest']:
        print(manifest(), end='')
    elif not sys.argv[1:]:
        print(json.dumps(validate(), indent=2, sort_keys=True))
    else:
        raise SystemExit('usage: d2_v2_1_static_validate.py [--manifest]')
