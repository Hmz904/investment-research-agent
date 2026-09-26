"""Targeted Repair-1 validation; authenticated DEV inputs and synthetic outputs only."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys

from .deterministic_evaluator import evaluate_v0_2
from .source_adapters_v0_2 import CSV_COLUMNS, adapt_dev_gold_bundle_v0_2
from .validation_v0_2 import canonical_json_bytes, require, result_sha256, strict_loads
from .verify_candidate_v0_2 import ROOT, DEV_MAP_SHA, DEV_CSV_SHA, verify_frozen_contracts
from .xbrl_v0_2 import adapt_dev_xbrl_map_v0_2, load_frozen_xbrl_v0_2


def verify(data_root):
    require(data_root.resolve() == Path('/mnt/d/projects/thesisagent-d2-v2-runtime-data'),
            'Repair-1 requires the isolated provisioned data root')
    frozen = verify_frozen_contracts()
    manifest = ROOT / 'evaluation/d2/D2_V2_AUDIT_REGRESSION_FREEZE_SHA256.txt'
    require(hashlib.sha256(manifest.read_bytes()).hexdigest() ==
            'e010615bc9f27a68e5914da5ee3fadfb0cd52b42211b12366586aaa8cba3cd47', 'Audit regression manifest changed')
    for line in manifest.read_text().splitlines():
        expected, relative = line.split(maxsplit=1)
        require(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected,
                'Audit regression artifact changed: ' + relative)
    runtime = load_frozen_xbrl_v0_2(data_root=data_root)
    map_bytes = (ROOT / 'evaluation/dev/xbrl/dev_xbrl_map_v0.1.json').read_bytes()
    require(hashlib.sha256(map_bytes).hexdigest() == DEV_MAP_SHA, 'DEV source map changed')
    source = strict_loads(map_bytes)

    def adapt(value):
        return adapt_dev_xbrl_map_v0_2(value, source_sha256=result_sha256(value),
            fact_index=runtime['fact_index'], numeric_values=runtime['numeric_values'])

    normalized = adapt(source)
    require(normalized['evaluator_status'] == 'EVAL_OK', str(normalized['errors']))
    files = {name: (ROOT / 'benchmark/dev/v0.1' / name).read_bytes() for name in CSV_COLUMNS}
    hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
    require(hashes == DEV_CSV_SHA, 'DEV CSV changed')
    bundles = adapt_dev_gold_bundle_v0_2(files, declared_source_format='dev_gold_csv_bundle_v0.1',
        source_hashes=hashes, chunk_catalog=runtime['chunk_catalog'], normalized_map=normalized['normalized_map'],
        fact_index=runtime['fact_index'], numeric_values=runtime['numeric_values'])
    require(bundles['evaluator_status'] == 'EVAL_OK', str(bundles['errors']))
    require(len(bundles['gold_bundles']) == 8, 'Expected eight permitted DEV bundles')
    sys.path.insert(0, str(ROOT / 'tests/evaluation'))
    from d2_v2_contract_fixtures import request, put_output
    dev_results = {}
    for gold in bundles['gold_bundles']:
        case = request()
        case.update(gold_bundle=gold, chunk_catalog=runtime['chunk_catalog'],
            frozen_xbrl_fact_index=runtime['fact_index'], xbrl_numeric_values=runtime['numeric_values'],
            normalized_xbrl_map=normalized['normalized_map'])
        case['slot_record']['question_id'] = gold['question_id']
        output = dict(schema_version='agent_output_v0.1.1', q_id=gold['question_id'],
            answer='Synthetic validation placeholder; no answer attempted.', answer_claim_ids=['C901'],
            claims=[dict(claim_id='C901', text='Synthetic limitation.', claim_type='limitation',
                entities=['Synthetic'], material=False, period='not applicable', requires_citation=False,
                temporal_role='not_applicable')], calculations=[])
        result = evaluate_v0_2(put_output(case, output))
        require(result['evaluator_status'] == 'EVAL_OK', str(result['errors']))
        dev_results[gold['question_id']] = dict(evaluator_status=result['evaluator_status'], sha256=result_sha256(result))

    fixtures = ROOT / 'tests/evaluation/d2_v2_audit_regressions_v0_1'
    f1 = strict_loads((fixtures / 'deep_valid_DAG.request.json').read_bytes())
    f2 = strict_loads((fixtures / 'derived_output_precision_ignored.request.json').read_bytes())
    cases = dict(F1=lambda: evaluate_v0_2(f1), F2=lambda: evaluate_v0_2(f2),
                 XBRL_adapter=lambda: adapt(source))
    outputs = {}
    for name, run in cases.items():
        repeats = [run() for _ in range(10)]
        require(all(r['evaluator_status'] == 'EVAL_OK' for r in repeats), 'Failed determinism case: ' + name)
        raw = canonical_json_bytes(repeats[0])
        require(all(canonical_json_bytes(r) == raw for r in repeats), 'Nondeterministic case: ' + name)
        outputs[name] = repeats[0]
    require(outputs['F1']['metrics']['complete_numeric_answer'] is True, 'F1 did not pass completely')
    require(outputs['F2']['metrics']['complete_numeric_answer'] is False, 'F2 ignored output precision')
    verify_frozen_contracts()
    return dict(validation_version='d2_v2_implementation_repair1_v0.2', frozen_contracts=frozen,
        audit_regression_manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
        data_root=str(data_root), fact_count=len(runtime['fact_index']['facts']),
        xbrl_artifact_fingerprint=runtime['fact_index']['xbrl_artifact_fingerprint'],
        fact_index_sha256=result_sha256(runtime['fact_index']), numeric_catalog_sha256=result_sha256(runtime['numeric_values']),
        dev_bundle_count=len(dev_results), dev_results=dev_results, repeats_per_case_per_process=10,
        deterministic_result_hashes={name: result_sha256(result) for name, result in outputs.items()},
        deterministic_combined_sha256=result_sha256(outputs), deterministic_outputs=outputs,
        model_used=False, real_agent_output_used=False, judge_used=False, locked_test_accessed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.write_bytes(canonical_json_bytes(verify(args.data_root)))


if __name__ == '__main__':
    main()
