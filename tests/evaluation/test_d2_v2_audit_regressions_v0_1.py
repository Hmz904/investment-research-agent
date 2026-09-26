"""Exact independent-auditor F1–F4 inputs; additive to the frozen 257 cases."""
from pathlib import Path

import pytest

from evaluation.d2 import deterministic_evaluator as api
from evaluation.d2.validation_v0_2 import strict_loads, validate
from evaluation.d2.xbrl_v0_2 import load_frozen_xbrl_v0_2


FIXTURES = Path(__file__).with_name('d2_v2_audit_regressions_v0_1')
DATA_ROOT = Path('/mnt/d/projects/thesisagent-d2-v2-runtime-data')


def fixture(name):
    return strict_loads((FIXTURES / name).read_bytes())


@pytest.fixture(scope='module')
def runtime():
    result = load_frozen_xbrl_v0_2(data_root=DATA_ROOT)
    assert len(result['fact_index']['facts']) == 7839
    assert result['fact_index']['xbrl_artifact_fingerprint'] == (
        'acaf087ee2c4fb7427377cae5f1968da26c75d4dfa565f67f1e056b2c4cc4eb6')
    return result


def adapt(source, runtime):
    validate('dev_xbrl_source_map_v0.2.schema.json', source)
    return api.adapt_dev_xbrl_map_v0_2(
        source, source_sha256=api.result_sha256(source),
        fact_index=runtime['fact_index'], numeric_values=runtime['numeric_values'])


def test_f1_deep_valid_calculation_chain():
    request = fixture('deep_valid_DAG.request.json')
    output = strict_loads(request['agent_output_json'])
    assert len(output['calculations']) == 1100
    result = api.evaluate_v0_2(request)
    assert result['evaluator_status'] == 'EVAL_OK', result['errors']
    assert result['calculation_graph']['valid'] is True
    assert result['agent_output_contract_valid'] is True
    assert result['metrics']['complete_numeric_answer'] is True
    assert result['included_in_scored_denominator'] is True
    assert result['evaluation_completion']['scored_slot_count'] == 1


def test_f2_derived_precision_is_independent_of_target_tolerance():
    result = api.evaluate_v0_2(fixture('derived_output_precision_ignored.request.json'))
    assert result['evaluator_status'] == 'EVAL_OK', result['errors']
    occurrence = result['metrics']['answer_group_results'][0]['occurrences'][0]
    assert occurrence['numeric_correct'] is True
    assert occurrence['precision_result']['matched'] is True
    assert occurrence['variant_selection']['complete_deterministic_pass'] is False
    assert result['metrics']['complete_numeric_answer'] is False


def test_f3_false_same_sign_approval_is_invalid(runtime):
    source = fixture('map_false_same_sign_approval.source.json')
    target = next(t for t in source['targets'] if t['target_id'] == 'NF012')
    approved = next(c for c in target['stage1_candidates'] if c['human_review_status'] == 'APPROVE')
    assert target['gold_value'] == '-541'
    assert approved['gold_comparison_value'] == '-541000000'
    assert approved['candidate_comparison_value'] == '541000000'
    assert approved['proposed_sign_relationship'] == 'same_sign'
    result = adapt(source, runtime)
    assert result['evaluator_status'] == 'EVAL_INPUT_INVALID'
    assert result['normalized_map'] is None


def test_f4_blocked_earlier_stage_cannot_finalize_no_counterpart(runtime):
    source = fixture('no_counterpart_stage1_blocked.source.json')
    target = source['targets'][0]
    assert target['temporal_resolution']['resolved_temporal'] is not None
    assert not any(target[f'stage{n}_candidates'] for n in (1, 2, 3))
    assert target['stage_completion']['stage1'] == 'blocked_missing_exact_temporal_requirement'
    assert target['stage_completion']['stage3'] == 'completed'
    result = adapt(source, runtime)
    assert result['evaluator_status'] == 'EVAL_INPUT_INVALID'
    assert result['normalized_map'] is None


def test_f4_all_stages_complete_positive_control(runtime):
    result = adapt(fixture('no_counterpart_all_complete.source.json'), runtime)
    assert result['evaluator_status'] == 'EVAL_OK', result['errors']
    assert result['normalized_map']['targets'][0]['state'] == 'NO_APPROVED_XBRL_PATH'
