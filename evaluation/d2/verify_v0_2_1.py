"""Bounded implementation validation for the externally selected v0.2.1 contract.

Execute frozen tests unchanged and classify the sole superseded assertion
explicitly. Replay authenticated audit constructors with exactly two successor
predicates. Historical evidence is read only; new scratch output goes to /tmp.
"""
from __future__ import annotations
import argparse
from collections import Counter
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile

from . import deterministic_evaluator as ev
from .validation_v0_2 import canonical_json_bytes, require, result_sha256
from .verify_candidate_v0_2 import ROOT, verify_frozen_contracts
from .verify_repair1_v0_2 import verify as verify_repair1
from .dev_numeric_self_consistency_v0_2_1 import validate_dev
from .prescoring_gate_v0_2_1 import validate_gold_integrity_before_scoring

HISTORICAL = 'tests/evaluation/test_deterministic_evaluator_contract_v0_2.py'
SUPERSEDED = HISTORICAL + '::test_D10_quantum_exact_power_and_half_even[1.24-1.23-0.1-1.23-1.23-False-False]'
SUITES = {HISTORICAL: 257,
    'tests/evaluation/test_d2_v2_1_precision_contract.py': 11,
    'tests/evaluation/test_d2_v2_1_dev_self_consistency.py': 4,
    'tests/evaluation/test_d2_v2_audit_regressions_v0_1.py': 5,
    'tests/evaluation/test_d2_v2_implementation_guards.py': 22}
MANIFESTS = {
    'D2_V2_TEST_AUTHOR_FREEZE_SHA256.txt': 'f69e14f586a6d2fd94b5500d05db5a984c8180cd609d3e2582316ef481c29e22',
    'D2_V2_AUDIT_REGRESSION_FREEZE_SHA256.txt': 'e010615bc9f27a68e5914da5ee3fadfb0cd52b42211b12366586aaa8cba3cd47',
    'D2_V2_1_TEST_AUTHOR_PATCH_FREEZE_SHA256.txt': '49508f8c7421a93910f5188de629f277f44f37d05a2b178e9226e6d554bf0545'}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def guards():
    verify_frozen_contracts()
    counts = {}
    for name, expected in MANIFESTS.items():
        raw = (ROOT/'evaluation/d2'/name).read_bytes()
        require(digest(raw) == expected, 'Manifest changed: ' + name)
        entries = [line.split(maxsplit=1) for line in raw.decode().splitlines() if not line.startswith('#')]
        for sha, relative in entries:
            require(digest((ROOT/relative).read_bytes()) == sha, 'Frozen artifact changed: ' + relative)
        counts[name] = dict(sha256=expected, entries=len(entries))
    return counts


def test_accounting():
    import pytest
    class Accounting:
        def __init__(self):
            self.nodes = []
            self.calls = {}
            self.errors = []
        def pytest_collection_finish(self, session):
            self.nodes = [item.nodeid for item in session.items]
        def pytest_runtest_logreport(self, report):
            if report.when == 'call':
                self.calls[report.nodeid] = report.outcome
            elif report.outcome != 'passed':
                self.errors.append(report.nodeid + ':' + report.when)
    plugin = Accounting()
    log = io.StringIO()
    with redirect_stdout(log):
        status = pytest.main(['-q', '--tb=short', '-p', 'no:cacheprovider', *SUITES], plugins=[plugin])
    require(status == 1 and not plugin.errors, 'Unexpected frozen-suite execution status')
    require(Counter(n.split('::')[0] for n in plugin.nodes) == Counter(SUITES), 'Frozen collection count changed')
    require(len(plugin.calls) == 299, 'Missing test execution')
    require({n for n, outcome in plugin.calls.items() if outcome != 'passed'} == {SUPERSEDED},
            'Unexpected historical/successor failure or skip')
    return dict(historical_total=257, historical_active=256, historical_active_passed=256,
                superseded_count=1, superseded_node=SUPERSEDED,
                superseded_observation='Original false assertion executed unchanged and failed under S1',
                successor_precision=dict(collected=11, passed=11, failed=0),
                integrity_tests_passed=4, repair1_passed=5, guards_passed=22,
                active_total=298, active_passed=298, skipped=0,
                nodes=plugin.calls, original_pytest_exit_code=int(status)), log.getvalue()


def audit_replay():
    expectations_path = ROOT/'evaluation/audits/d2_v2_audit_expectations_v0.2.json'
    expectations = json.loads(expectations_path.read_bytes())
    historical_root = Path(expectations['historical_evidence_root'])
    sources = {}
    for name, sha in expectations['historical_harness_source_sha256'].items():
        raw = (historical_root/name).read_bytes()
        require(digest(raw) == sha, 'Historical harness changed: ' + name)
        sources[name] = raw
    identity = ''.join(f'{digest(sources[n])}  {n}\n' for n in sorted(sources))
    require(digest(identity.encode()) == expectations['historical_harness_identity_sha256'], 'Harness identity mismatch')
    historical_raw = (historical_root/'all_probe_results.json').read_bytes()
    require(digest(historical_raw) == expectations['historical_all_probe_results_sha256'], 'Historical evidence changed')
    historical = json.loads(historical_raw)
    changes = {c['name']: c for c in expectations['changes']}
    require(set(changes) == {'offgrid_gold', 'inconsistent_derived_output_precision'}, 'Unexpected replacement')
    successor_entries = expectations['probes']
    require(len(historical) == len(successor_entries) == 150, 'Probe count changed')
    for old, new in zip(historical, successor_entries):
        require(old['name'] == new['name'] and old['rows'] == new['rows'], 'Probe identity changed')
        require(new['expected'] == (changes[old['name']]['new_expected'] if old['name'] in changes else old['expected']),
                'Unauthorized expectation change')
    d19 = expectations['historical_d19_request']
    require(digest((historical_root/d19['path']).read_bytes()) == d19['sha256'], 'D19 evidence changed')
    scratch = Path(tempfile.mkdtemp(prefix='d2_v021_harness_'))
    spec = importlib.util.spec_from_file_location('probes', historical_root/'probes.py')
    p = importlib.util.module_from_spec(spec)
    sys.modules['probes'] = p
    old_path = sys.path[:]
    spec.loader.exec_module(p)
    sys.path[:] = old_path
    # All production modules are imported from this checkout before loading p.
    require(Path(p.ev.__file__).resolve() == ROOT/'evaluation/d2/deterministic_evaluator.py', 'Wrong implementation')
    p.ROOT, p.OUT = ROOT, scratch
    original_run = p.run
    inputs, outputs = {}, {}
    def run(name, request, expected, predicate, rows):
        raw = p.dump(request).encode()
        inputs[name] = digest(raw)
        if name == 'inconsistent_derived_output_precision':
            require(inputs[name] == d19['sha256'], 'D19 constructor bytes changed')
        if name in changes:
            require(expected == changes[name]['old_expected'], 'Original predicate binding changed')
            expected = changes[name]['new_expected']
            def predicate(result):
                for field, value in changes[name]['successor_result_requirements'].items():
                    actual = result
                    for key in field.split('.'):
                        actual = actual[key]
                    if actual != value:
                        return False
                return True
        result = original_run(name, request, expected, predicate, rows)
        outputs[name] = result
        return result
    p.run = run
    records = []
    retired_runtime_records = []
    with redirect_stdout(io.StringIO()):
        p.main()
        records.extend(p.RESULTS)
        for name in ['extra_probes.py', 'runtime_probes.py', 'precision_repro.py', 'map_states.py', 'final_probes.py']:
            p.RESULTS = []
            namespace = {'__name__': 'd2_v021_replay', '__file__': str(historical_root/name)}
            exec(compile(sources[name], str(historical_root/name), 'exec'), namespace)
            sys.path[:] = old_path
            current = p.RESULTS
            if name == 'runtime_probes.py':
                # The original collector retired this malformed control. S1
                # makes it reach its existing conditional child, whose name is
                # also used by the separately frozen map_states.py F4 input.
                # Neither retired parent nor its child belongs to the frozen
                # 150. Keep their provenance explicit; never replace F4.
                retired_names = {'valid_no_xbrl_counterpart_in_frozen_corpus',
                                 'no_counterpart_stage1_blocked'}
                retired_runtime_records = [dict(source=name, name=r['name'],
                    reason='Outside frozen 150: retired runtime control or its conditional child')
                    for r in current if r['name'] in retired_names]
                current = [r for r in current if r['name'] not in retired_names]
            records.extend(current)
    # Preserve the original collect_evidence.py's existing exclusion exactly.
    records = [r for r in records if r['name'] != 'valid_no_xbrl_counterpart_in_frozen_corpus']
    require(len(records) == 150, 'Replay count changed')
    for actual, expected in zip(records, successor_entries):
        require(all(actual[k] == expected[k] for k in ('name', 'rows', 'expected')), 'Replay expectation drift')
    require(all(r['passed'] for r in records), 'Failed audit probes: ' + str([r['name'] for r in records if not r['passed']]))
    matrix = json.loads((ROOT/'evaluation/d2/d2_v2_1_preregistration_42_row_matrix.json').read_bytes())
    rows = []
    for row in matrix:
        probes = [r for r in records if row['row_id'] in r['rows']]
        require(probes, 'Uncovered matrix row')
        disposition = 'PENDING_JUDGE' if row['classification'] == 'PENDING_JUDGE' else 'PASS'
        rows.append(dict(row_id=row['row_id'], result=disposition, probes=[r['name'] for r in probes]))
    require(Counter(r['result'] for r in rows) == {'PASS': 39, 'PENDING_JUDGE': 3}, 'Matrix counts changed')
    policy = ev.checkpoint_reportability_v0_2_1([outputs['baseline'], outputs['internal_error_namespace']], gold_integrity_passed=True)
    require(policy == dict(checkpoint_valid=False, aggregate_reportability='NON-REPORTABLE', evaluator_repair_and_rerun_required=True), 'P6 internal-error gate failed')
    require(ev.checkpoint_reportability_v0_2_1([outputs['baseline']], gold_integrity_passed=True)['checkpoint_valid'], 'Valid checkpoint rejected')
    require(not ev.checkpoint_reportability_v0_2_1([outputs['baseline']], gold_integrity_passed=False)['checkpoint_valid'], 'Gold integrity failure ignored')
    compact = [dict(name=r['name'], rows=r['rows'], expected=r['expected'], passed=r['passed'],
                    observation_sha256=result_sha256(r['observed']), input_sha256=inputs.get(r['name'])) for r in records]
    return dict(total=150, passed=150, unchanged_expectations=148, changed_expectations=sorted(changes),
                harness_identity_sha256=expectations['historical_harness_identity_sha256'],
                expectations_sha256=digest(expectations_path.read_bytes()), records=compact, matrix=rows,
                retired_runtime_accounting=retired_runtime_records,
                checkpoint_internal_error_policy=policy, runtime=json.loads((scratch/'runtime_summary.json').read_bytes()),
                historical_determinism_sha256=digest((scratch/'deterministic_output.json').read_bytes()))


def determinism():
    repair = verify_repair1(Path('/mnt/d/projects/thesisagent-d2-v2-runtime-data'))
    from d2_v2_1_precision_fixtures import d19_request, quantum_request
    cases = dict(D19=d19_request(), NF004=quantum_request('56.0', '56.0468756436', '0.1', '56.0468756436', '56.0468756436', False))
    hashes = {}
    for name, request in cases.items():
        results = [ev.evaluate_v0_2(request) for _ in range(10)]
        require(all(r['evaluator_status'] == 'EVAL_OK' and r['metrics']['complete_numeric_answer'] is True for r in results), 'Corrected precision failed')
        raw = canonical_json_bytes(results[0])
        require(all(canonical_json_bytes(r) == raw for r in results), 'Corrected precision nondeterministic')
        hashes[name] = digest(raw)
    return dict(repair1=repair, corrected_quantum_hashes=hashes, repeats_per_case=10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['tests', 'harness', 'determinism'])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT/'tests/evaluation'))
    # Mandatory checkpoint precondition: no test/harness/evaluator entrypoint
    # may execute before frozen inputs and all 17 DEV targets pass integrity.
    try:
        frozen = guards()
        dev_integrity = validate_gold_integrity_before_scoring(validate_dev)
    except Exception as exc:
        # Diagnostic only: no scoring results or aggregate scoring payload.
        args.output.write_bytes(canonical_json_bytes(dict(
            checkpoint_valid=False, aggregate_reportability='NON-REPORTABLE',
            evaluator_repair_and_rerun_required=True,
            enforcement_mode='MANDATORY_PRECHECK',
            gold_integrity_error=f'{type(exc).__name__}: {exc}')))
        print(args.mode, 'BLOCKED: pre-scoring integrity precheck failed', flush=True)
        raise SystemExit(1) from exc
    if args.mode == 'tests':
        result, log = test_accounting()
        args.output.with_suffix('.txt').write_text(log)
    elif args.mode == 'harness':
        result = audit_replay()
    else:
        result = determinism()
    require(guards() == frozen, 'Immutable artifacts changed during validation')
    result = dict(contract_interpretation='d2_contract_v0.2.1', patch_commit='0b6d22fc563dec40b0ae0ad643b30d0d1792d207',
                  frozen_manifests=frozen, dev_integrity=dev_integrity, validation=result)
    args.output.write_bytes(canonical_json_bytes(result))
    print(args.mode, 'PASS', digest(args.output.read_bytes()), flush=True)


if __name__ == '__main__':
    main()
