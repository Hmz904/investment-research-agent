"""Independent D2 v2 normative tests. Authoring phase: compile only, never import.

The implementation module is loaded solely by pytest's deferred fixture in a
NEW implementation-repair session. No expected constant comes from that module.
"""
from copy import deepcopy
from decimal import Decimal
import hashlib
import importlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from referencing import Registry, Resource

from d2_v2_contract_fixtures import (
    calculation, chunk, claim, derived_request, exact, fact, fact_index,
    get_output, json_bytes, output, precision, put_output, request, target,
    variant, xbrl_request,
)

ROOT = Path(__file__).resolve().parents[2]
D2 = ROOT / 'evaluation/d2'


@pytest.fixture
def api():
    # Must not be invoked in the authoring session.
    return importlib.import_module('evaluation.d2.deterministic_evaluator')


def validate(schema_name, instance, definition=None):
    files = list(D2.glob('*.schema.json')) + [D2 / 'deterministic_evaluator_output_schema_v0.2.json']
    schemas = [json.loads(p.read_text()) for p in files]
    registry = Registry().with_resources((s['$id'], Resource.from_contents(s)) for s in schemas)
    schema = json.loads((D2 / schema_name).read_text())
    if definition is not None:
        schema = {'$schema': schema['$schema'], '$ref': schema['$id'] + '#/$defs/' + definition}
    Draft202012Validator(schema, registry=registry, format_checker=FormatChecker()).validate(instance)


def evaluate(api, r):
    result = api.evaluate_v0_2(r)
    validate('deterministic_evaluator_output_schema_v0.2.json', result)
    return result


def numeric_request(candidate, gold='10', cu='USD', gu='USD', p=None):
    r = request(); t = r['gold_bundle']['numeric_targets'][0]; v = r['gold_bundle']['answer_groups'][0]['variants'][0]
    for record in (t, v):
        record.update(accepted_value=gold, unit=gu, precision=deepcopy(p or exact(gold, gu)))
    a = output(); a['claims'] = [claim(value=candidate, unit=cu)]
    return put_output(r, a)


def assert_system_error(result, status):
    assert result['evaluator_status'] == status
    assert result['metrics'] is None
    assert result['included_in_scored_denominator'] is False
    assert result['checkpoint_valid'] is False
    assert result['evaluation_completion'] is None


@pytest.mark.parametrize('field,value', [
    ('protocol_version', 'eval_protocol_v9'), ('taxonomy_version', 'execution_taxonomy_v9'),
    ('agent_output_schema_version', 'agent_output_v9'), ('mapping_spec_version', 'mapping_v9'),
    ('evaluator_contract_version', 'd2_contract_v9'), ('xbrl_artifact_fingerprint', '0' * 64),
    ('corpus_fingerprint', '0' * 64),
])
def test_D01_contract_identity(api, field, value):
    r = request(); r['contract_identity'][field] = value
    assert_system_error(evaluate(api, r), 'EVAL_CONTRACT_MISMATCH')


def test_D01_output_hash_binding(api):
    r = request(); r['agent_output_sha256'] = '0' * 64
    assert_system_error(evaluate(api, r), 'EVAL_CONTRACT_MISMATCH')


@pytest.mark.parametrize('defect', ['unknown_key', 'dual_provenance', 'missing_answer', 'missing_unit', 'nonfinite', 'duplicate_json_key'])
def test_D02_schema_invalid_completed_payload(api, defect):
    r = request(); a = output()
    if defect == 'unknown_key': a['extra'] = True
    elif defect == 'dual_provenance': a['claims'][0]['citations'] = [chunk()]
    elif defect == 'missing_answer': del a['answer']
    elif defect == 'missing_unit': del a['claims'][0]['numeric_value']['unit']
    put_output(r, a)
    if defect == 'nonfinite': r['agent_output_json'] = r['agent_output_json'].replace('"value":10', '"value":NaN')
    if defect == 'duplicate_json_key': r['agent_output_json'] = r['agent_output_json'].replace('"q_id":"SYNTH_Q"', '"q_id":"SYNTH_Q","q_id":"SYNTH_Q"')
    r['agent_output_sha256'] = hashlib.sha256(r['agent_output_json'].encode()).hexdigest()
    assert_system_error(evaluate(api, r), 'EVAL_INPUT_INVALID')


@pytest.mark.parametrize('legacy', [False, True])
def test_D02_D27_valid_provenance_representations(api, legacy):
    r = request(); a = output()
    if legacy:
        a['claims'][0].pop('provenance'); a['claims'][0]['citations'] = [chunk()]
    result = evaluate(api, put_output(r, a))
    assert result['evaluator_status'] == 'EVAL_OK'
    assert result['metrics']['schema_valid'] is True
    assert result['metrics']['provenance_validity'] == {'numerator': 1, 'denominator': 1}


@pytest.mark.parametrize('edges,bad', [
    ([('K001', 'K001')], ['K001']),
    ([('K001', 'K002'), ('K002', 'K001')], ['K001', 'K002']),
    ([('K001', 'K002'), ('K002', 'K003'), ('K003', 'K001')], ['K001', 'K002', 'K003']),
    ([('K001', 'K999')], ['K001']),
    ([('K001', 'K999'), ('K002', 'K001')], ['K001', 'K002']),
])
def test_D03_CD01_invalid_graph(api, edges, bad):
    r = derived_request(); a = get_output(r); a['calculations'] = [calculation(k, dep) for k, dep in edges]
    z = evaluate(api, put_output(r, a))
    assert z['execution_status'] == 'RUN_COMPLETED'
    assert z['evaluator_status'] == 'EVAL_OK'
    assert z['agent_output_contract_valid'] is False
    assert z['included_in_scored_denominator'] is True
    assert z['calculation_graph']['invalid_calculation_ids'] == bad
    assert z['calculation_graph']['dependent_claim_ids'] == ['C001']
    assert 'INVALID_CALCULATION_REFERENCE_GRAPH' in z['reason_codes']
    assert z['metrics']['complete_numeric_answer'] is False
    assert z['metrics']['numeric_value_correctness'] == {'numerator': 0, 'denominator': 1}


def test_D03_valid_DAG(api):
    r = derived_request(); a = get_output(r)
    a['calculations'] = [calculation('K001', 'K002'), calculation('K002')]
    z = evaluate(api, put_output(r, a))
    assert z['evaluator_status'] == 'EVAL_OK'
    assert z['calculation_graph']['valid'] is True
    assert z['agent_output_contract_valid'] is True
    assert z['metrics']['complete_numeric_answer'] is True


def test_D03_CD01_independent_direct_claim(api):
    r = request(); a = output(); a['calculations'] = [calculation('K001', 'K001')]
    z = evaluate(api, put_output(r, a))
    assert z['evaluator_status'] == 'EVAL_OK'
    assert z['agent_output_contract_valid'] is False
    assert z['calculation_graph']['dependent_claim_ids'] == []
    assert z['metrics']['numeric_value_correctness'] == {'numerator': 1, 'denominator': 1}
    assert z['metrics']['complete_numeric_answer'] is False


@pytest.mark.parametrize('defect', ['duplicate_claim', 'duplicate_calculation', 'unresolved_answer'])
def test_D03_D32_non_graph_reference_errors(api, defect):
    r = request(); a = output()
    if defect == 'duplicate_claim': a['claims'].append(deepcopy(a['claims'][0]))
    if defect == 'duplicate_calculation': a['calculations'] = [calculation(), calculation()]
    if defect == 'unresolved_answer': a['answer_claim_ids'] = ['C999']
    assert_system_error(evaluate(api, put_output(r, a)), 'EVAL_INPUT_INVALID')


@pytest.mark.parametrize('candidate,gold,match', [
    ('0.12345678901234567890123456789', '0.12345678901234567890123456789', True),
    ('0.12345678901234567890123456788', '0.12345678901234567890123456789', False),
    ('-0', '0', True), ('10.00', '10', True), ('11', '10', False),
])
def test_D04_D09_exact_decimal(api, candidate, gold, match):
    z = evaluate(api, numeric_request(candidate, gold))
    assert z['evaluator_status'] == 'EVAL_OK'
    assert z['metrics']['complete_numeric_answer'] is match


@pytest.mark.parametrize('bad', ['1e2', 'NaN', 'Infinity', '1,000', '$10', ' 10', '.5'])
def test_D04_malformed_gold_decimal(api, bad):
    r = request(); r['gold_bundle']['numeric_targets'][0]['accepted_value'] = bad
    assert_system_error(evaluate(api, r), 'EVAL_INPUT_INVALID')


@pytest.mark.parametrize('candidate,cu,gold,gu,match', [
    ('1', 'USD_thousand', '1000', 'USD', True), ('1', 'USD_million', '1000000', 'USD', True),
    ('1', 'USD_billion', '1000000000', 'USD', True), ('1', 'shares_thousand', '1000', 'shares', True),
    ('1', 'shares_million', '1000000', 'shares', True), ('1', 'shares_billion', '1000000000', 'shares', True),
    ('1', 'USD_per_basic_share', '1', 'USD_per_share', True), ('1', 'USD_per_diluted_share', '1', 'USD_per_share', True),
    ('56', 'percent', '0.56', 'pure', True), ('10', 'percentage_point', '10', 'percent', False),
    ('10', 'percentage_point', '10', 'pure', False), ('10', 'CUSTOM', '10', 'CUSTOM', True),
    ('10', 'CUSTOM', '10', 'custom', False), ('10', 'USD', '10', 'shares', False),
    ('10', ' USD', '10', 'USD', False), ('10', 'basis_point', '0.1', 'percent', False),
])
def test_D05_D08_units(api, candidate, cu, gold, gu, match):
    z = evaluate(api, numeric_request(candidate, gold, cu, gu))
    assert z['evaluator_status'] == 'EVAL_OK'
    assert z['metrics']['complete_numeric_answer'] is match


@pytest.mark.parametrize('candidate,gold,q,lower,upper,inclusive,match', [
    ('1.15', '1.2', '0.1', '1.15', '1.25', True, True),
    ('1.25', '1.2', '0.1', '1.15', '1.25', True, True),
    ('1.25001', '1.2', '0.1', '1.15', '1.25', True, False),
    ('1.25', '1.3', '0.1', '1.25', '1.35', False, False),
    ('1.35', '1.3', '0.1', '1.25', '1.35', False, False),
    ('-1.25', '-1.2', '0.1', '-1.25', '-1.15', True, True),
    ('15', '20', '10', '15', '25', True, True),
    ('2.5', '2', '1', '1.5', '2.5', True, True),
    ('1.225', '1.22', '0.01', '1.215', '1.225', True, True),
    ('1.24', '1.23', '0.1', '1.23', '1.23', False, False),
])
def test_D10_quantum_exact_power_and_half_even(api, candidate, gold, q, lower, upper, inclusive, match):
    p = precision(gold, 'QUANTUM', q, lower, upper, inclusive)
    z = evaluate(api, numeric_request(candidate, gold, p=p))
    assert z['evaluator_status'] == 'EVAL_OK'
    assert z['metrics']['complete_numeric_answer'] is match


@pytest.mark.parametrize('q', ['0.03', '0', '-0.1', 'NaN', '1e-2'])
def test_D10_invalid_quantum_is_input_invalid(api, q):
    p = precision('10', 'QUANTUM', q, '9.5', '10.5')
    assert_system_error(evaluate(api, numeric_request('10', p=p)), 'EVAL_INPUT_INVALID')


@pytest.mark.parametrize('tolerance', ['-1', 'bad', 'NaN', '1e-2', 0.1])
def test_D11_invalid_tolerance_is_not_agent_mismatch(api, tolerance):
    p = precision('10', 'ABS_TOLERANCE', tolerance, '9', '11')
    assert_system_error(evaluate(api, numeric_request('10', p=p)), 'EVAL_INPUT_INVALID')


@pytest.mark.parametrize('candidate,t,low,high,match', [
    ('10', '0', '10', '10', True), ('10.00000000000000001', '0', '10', '10', False),
    ('9', '1', '9', '11', True), ('11', '1', '9', '11', True), ('11.0001', '1', '9', '11', False),
])
def test_D11_inclusive_tolerance(api, candidate, t, low, high, match):
    z = evaluate(api, numeric_request(candidate, p=precision('10', 'ABS_TOLERANCE', t, low, high)))
    assert z['metrics']['complete_numeric_answer'] is match


@pytest.mark.parametrize('metadata,mode,parameter', [
    ({'tolerance': '0.2', 'display_precision': 2}, 'ABS_TOLERANCE', '0.2'),
    ({'display_precision': 2}, 'QUANTUM', '0.01'), ({}, 'EXACT', None),
])
def test_D09_D11_legacy_precision_precedence(api, metadata, mode, parameter):
    z = api.adapt_precision_v0_2(metadata, reference_value='10', unit='USD')
    assert z['evaluator_status'] == 'EVAL_OK'
    validate('precision_record_v0.2.schema.json', z['precision'])
    assert z['precision']['mode'] == mode
    assert z['precision']['absolute_tolerance'] == (parameter if mode == 'ABS_TOLERANCE' else None)
    assert z['precision']['quantum'] == (parameter if mode == 'QUANTUM' else None)


def test_D11_no_precision_fallback_after_bad_tolerance(api):
    z = api.adapt_precision_v0_2({'tolerance': '-1', 'display_precision': 2}, reference_value='10', unit='USD')
    assert z['evaluator_status'] == 'EVAL_INPUT_INVALID'
    assert z['precision'] is None


@pytest.mark.parametrize('candidate,gold', [('-10', '10'), ('10', '-10')])
def test_D12_no_sign_repair(api, candidate, gold):
    z = evaluate(api, numeric_request(candidate, gold))
    assert z['metrics']['complete_numeric_answer'] is False


@pytest.mark.parametrize('basis,match', [('GAAP', True), ('invented_basis', False)])
def test_D13_registered_signed_variant(api, basis, match):
    r = numeric_request('-10', '-10'); a = get_output(r); a['claims'][0]['numeric_value']['basis'] = basis
    r['gold_bundle']['answer_groups'][0]['variants'][0]['sign_policy'] = 'REGISTERED_VARIANT'
    assert evaluate(api, put_output(r, a))['metrics']['complete_numeric_answer'] is match


@pytest.mark.parametrize('values,correct,extras', [
    (['10'], False, []), (['10', '10'], True, []),
    (['9', '10'], False, []), (['10', '10', '9'], True, ['C003']),
])
def test_D14_multiplicity(api, values, correct, extras):
    r = request(); r['gold_bundle']['answer_groups'][0]['multiplicity'] = 2
    a = output(); a['claims'] = [claim('C00' + str(i+1), v) for i, v in enumerate(values)]
    a['answer_claim_ids'] = [c['claim_id'] for c in a['claims']]
    z = evaluate(api, put_output(r, a))
    assert z['metrics']['complete_numeric_answer'] is correct
    assert z['assignment']['extra_claim_ids'] == extras
    assert z['metrics']['numeric_value_correctness']['denominator'] == 1
    assert len(z['metrics']['answer_group_results'][0]['occurrences']) == 2


@pytest.mark.parametrize('values,correct_count', [(['10', '20'], 2), (['20', '10'], 0), (['9', '20', '10'], 1)])
def test_D14_positional_assignment_no_rescue(api, values, correct_count):
    r = request(); t = target('T2', '20'); r['gold_bundle']['numeric_targets'].append(t)
    r['gold_bundle']['answer_groups'].append({'answer_group_id': 'G2', 'multiplicity': 1, 'question_consistency_group': None, 'variants': [variant(t, 'V2')]})
    a = output(); a['claims'] = [claim('C00'+str(i+1), v) for i,v in enumerate(values)]
    a['answer_claim_ids'] = list(reversed([c['claim_id'] for c in a['claims']]))
    z = evaluate(api, put_output(r, a))
    assert z['metrics']['numeric_value_correctness'] == {'numerator': correct_count, 'denominator': 2}
    assert z['assignment']['assignments'][0]['claim_id'] == 'C001'


@pytest.mark.parametrize('family2,passes', [('F1', True), ('F2', False)])
def test_D15_variant_family_coherence(api, family2, passes):
    r = request(); g = r['gold_bundle']; g['numeric_targets'][0]['variant_family'] = 'F1'
    g['answer_groups'][0]['question_consistency_group'] = 'LINK'; g['answer_groups'][0]['variants'][0]['variant_family'] = 'F1'
    t = target('T2', '20'); t['variant_family'] = family2; g['numeric_targets'].append(t)
    g['answer_groups'].append({'answer_group_id': 'G2', 'multiplicity': 1, 'question_consistency_group': 'LINK', 'variants': [variant(t, 'V2')]})
    a = output(); a['claims'].append(claim('C002', '20')); a['answer_claim_ids'].append('C002')
    z = evaluate(api, put_output(r, a))
    assert z['metrics']['variant_consistency'] == ('PASS' if passes else 'FAIL')
    assert z['metrics']['complete_numeric_answer'] is passes


def test_D15_identical_pass_reporting_tie(api):
    r = request(); v = r['gold_bundle']['answer_groups'][0]['variants'][0]; v['variant_id'] = 'Z'
    second = deepcopy(v); second['variant_id'] = 'A'; r['gold_bundle']['answer_groups'][0]['variants'].append(second)
    z = evaluate(api, r)
    assert z['metrics']['answer_group_results'][0]['occurrences'][0]['variant_id'] == 'A'


@pytest.mark.parametrize('input_value,correct', [('10', True), ('9', False)])
def test_D16_D19_required_input_independent_of_final(api, input_value, correct):
    r = derived_request(); a = get_output(r); a['calculations'][0]['inputs'][0]['value'] = Decimal(input_value)
    z = evaluate(api, put_output(r, a))
    assert z['metrics']['required_input_correctness'] == {'numerator': 1 if correct else 0, 'denominator': 1}
    assert z['metrics']['numeric_value_correctness'] == {'numerator': 1, 'denominator': 1}
    assert z['metrics']['complete_numeric_answer'] is correct


@pytest.mark.parametrize('expression,formula_ok,arithmetic_ok', [
    ('I001', True, True), (' (( +I001 )) ', True, True),
    ('I001+0.00', False, True), ('I001*1', False, True),
    ('I001-1', False, False), ('I001/0', False, False),
    ('I001**1', False, False), ('abs(I001)', False, False),
    ('10', False, False), ('I999', False, False),
])
def test_D17_D18_formula_and_arithmetic(api, expression, formula_ok, arithmetic_ok):
    r = derived_request(); a = get_output(r); a['calculations'][0]['expression'] = expression
    z = evaluate(api, put_output(r, a))
    assert z['evaluator_status'] == 'EVAL_OK'
    assert z['metrics']['formula_correctness'] is formula_ok
    assert z['metrics']['arithmetic_correctness'] is arithmetic_ok
    assert z['metrics']['numeric_value_correctness'] == {'numerator': 1, 'denominator': 1}


def test_D17_explicitly_frozen_formula_alternative(api):
    r = derived_request(); v = r['gold_bundle']['answer_groups'][0]['variants'][0]
    v['derived_specification']['allowed_formula_variants'].append({'formula_variant_id': 'T1.formula.v2', 'canonical_formula': '(base + 0)'})
    a = get_output(r); a['calculations'][0]['expression'] = 'I001+0'
    z = evaluate(api, put_output(r, a))
    assert z['metrics']['formula_correctness'] is True


@pytest.mark.parametrize('result,correct', [('10', True), ('11', False)])
def test_D18_wrong_submitted_result(api, result, correct):
    r = derived_request(); a = get_output(r); a['calculations'][0]['result']['value'] = Decimal(result)
    z = evaluate(api, put_output(r, a))
    assert z['metrics']['arithmetic_correctness'] is correct


@pytest.mark.parametrize('remove,complete', [(False, True), (True, False)])
def test_D20_D23_D28_required_provenance(api, remove, complete):
    r = derived_request(); a = get_output(r)
    if remove:
        # Schema-valid literal input cannot masquerade as a source-bound required fact.
        item = a['calculations'][0]['inputs'][0]; item['source_type'] = 'literal_constant'; item['provenance'] = []
    z = evaluate(api, put_output(r, a))
    assert z['metrics']['provenance_completeness'] is complete
    assert z['metrics']['deterministic_grounded_prerequisites'] is complete


@pytest.mark.parametrize('field,value,reason,hallucinated', [
    ('chunk_id', 'forged', 'nonexistent_chunk_id', 1),
    ('accession', '0000000002-24-000001', 'wrong_accession', 1),
    ('locator', 'wrong locator', 'metadata_inconsistent', 0),
])
def test_D21_D29_chunk_identity_errors(api, field, value, reason, hallucinated):
    r = request(); a = output(); a['claims'][0]['provenance'][0][field] = value
    z = evaluate(api, put_output(r, a))
    assert z['metrics']['provenance_validity'] == {'numerator': 0, 'denominator': 1}
    assert z['metrics']['invalid_identity_count'] == 1
    assert z['metrics']['hallucinated_identity_count'] == hallucinated
    assert reason in z['reason_codes']


def test_D22_wrong_target_chunk_remains_identity_valid(api):
    r = request(); a = output(); a['claims'][0]['provenance'] = [{'provenance_type': 'chunk', **chunk('chunk-b')}]
    z = evaluate(api, put_output(r, a))
    assert z['metrics']['provenance_validity'] == {'numerator': 1, 'denominator': 1}
    assert z['metrics']['benchmark_provenance_correctness'] == {'numerator': 0, 'denominator': 1}


@pytest.mark.parametrize('members,citations,approved', [
    (['chunk-a', 'chunk-b'], ['chunk-a'], False), (['chunk-a', 'chunk-b'], ['chunk-a', 'chunk-b'], True),
    (['chunk-b'], ['chunk-b'], True),
])
def test_D22_chunk_path_AND(api, members, citations, approved):
    r = request(); path = [{'path_id': 'AND1', 'members': [chunk(n) for n in members]}]
    r['gold_bundle']['numeric_targets'][0]['approved_chunk_paths'] = deepcopy(path)
    r['gold_bundle']['answer_groups'][0]['variants'][0]['approved_chunk_paths'] = path
    a = output(); a['claims'][0]['provenance'] = [{'provenance_type': 'chunk', **chunk(n)} for n in citations]
    z = evaluate(api, put_output(r, a))
    assert z['metrics']['benchmark_provenance_correctness'] == {'numerator': 1 if approved else 0, 'denominator': 1}


@pytest.mark.parametrize('locator,valid,approved,reason', [
    ('SYNTH_DOC#f0000', 1, 1, None), ('SYNTH_DOC#f0001', 1, 0, None),
    ('SYNTH_DOC#forged', 0, 0, 'nonexistent_fact_locator'),
])
def test_D24_D25_authoritative_identity_vs_approval(api, locator, valid, approved, reason):
    r = xbrl_request(); a = get_output(r); a['claims'][0]['provenance'][0]['fact_locator'] = locator
    z = evaluate(api, put_output(r, a))
    assert z['metrics']['provenance_validity'] == {'numerator': valid, 'denominator': 1}
    assert z['metrics']['benchmark_provenance_correctness'] == {'numerator': approved, 'denominator': 1}
    assert z['metrics']['provenance_findings'][0]['FACT_IDENTITY_VALID'] is bool(valid)
    assert z['metrics']['provenance_findings'][0]['APPROVED_PATH_VALID'] is bool(approved)
    if reason: assert reason in z['reason_codes']
    else:
        assert 'nonexistent_fact_locator' not in z['reason_codes']
        assert z['metrics']['hallucinated_identity_count'] == 0


@pytest.mark.parametrize('field,value,reason', [
    ('accession', '0000000002-24-000001', 'wrong_fact_identity'), ('concept', 'us-gaap:Liabilities', 'wrong_fact_identity'),
    ('context_ref', 'ctx-2', 'wrong_fact_identity'), ('unit', 'shares', 'wrong_fact_identity'),
    ('instant', '2024-03-30', 'wrong_fact_identity'), ('chunk_id', 'chunk-a', 'wrong_chunk_linkage'),
])
def test_D24_identity_field_disagreement(api, field, value, reason):
    r = xbrl_request(); a = get_output(r); a['claims'][0]['provenance'][0][field] = value
    z = evaluate(api, put_output(r, a))
    assert z['metrics']['provenance_validity'] == {'numerator': 0, 'denominator': 1}
    assert reason in z['reason_codes']


def test_D24_nonnumeric_identity_is_not_numeric_provenance(api):
    r = xbrl_request(); r['xbrl_numeric_values'][1]['normalized_value'] = None
    a = get_output(r); a['claims'][0]['provenance'][0]['fact_locator'] = 'SYNTH_DOC#f0001'
    z = evaluate(api, put_output(r, a))
    assert z['metrics']['provenance_validity'] == {'numerator': 0, 'denominator': 1}
    assert 'nonexistent_fact_locator' not in z['reason_codes']


@pytest.mark.parametrize('defect', ['missing_fact', 'identity_disagreement', 'bad_count', 'duplicate_locator', 'wrong_fingerprint'])
def test_D24_D25_invalid_authoritative_configuration(api, defect):
    r = xbrl_request()
    if defect == 'missing_fact':
        for p in (r['normalized_xbrl_map']['targets'][0]['direct_approved_paths'], r['gold_bundle']['numeric_targets'][0]['approved_xbrl_paths'], r['gold_bundle']['answer_groups'][0]['variants'][0]['approved_xbrl_paths']):
            p[0]['fact_identity']['fact_id'] = 'absent'; p[0]['fact_identity']['fact_locator'] = 'SYNTH_DOC#absent'; p[0]['fact_identity']['stable_fact_id'] = 'SYNTH_DOC::absent'
    elif defect == 'identity_disagreement':r['normalized_xbrl_map']['targets'][0]['direct_approved_paths'][0]['fact_identity']['context_ref'] = 'wrong'
    elif defect == 'bad_count':r['frozen_xbrl_fact_index']['facts'].pop()
    elif defect == 'duplicate_locator':r['frozen_xbrl_fact_index']['facts'][1] = deepcopy(r['frozen_xbrl_fact_index']['facts'][0])
    elif defect == 'wrong_fingerprint':r['frozen_xbrl_fact_index']['xbrl_artifact_fingerprint'] = '0'*64
    assert_system_error(evaluate(api, r), 'EVAL_CONTRACT_MISMATCH' if defect == 'wrong_fingerprint' else 'EVAL_INPUT_INVALID')


@pytest.mark.parametrize('state', ['unmappable', 'no_xbrl_counterpart_in_frozen_corpus'])
def test_D26_nonmapped_legacy_route(api, state):
    r = request(); r['normalized_xbrl_map'] = {'normalized_map_schema_version': 'normalized_xbrl_map_v0.2', 'adapter_version': 'dev_xbrl_map_adapter_v0.2',
        'source_schema_version': 'normalized_xbrl_map_v0.2', 'source_sha256': 'b'*64,
        'xbrl_artifact_fingerprint': 'acaf087ee2c4fb7427377cae5f1968da26c75d4dfa565f67f1e056b2c4cc4eb6',
        'targets': [{'target_id': 'T1', 'question_id': 'SYNTH_Q', 'state': 'NO_APPROVED_XBRL_PATH', 'source_state': state,
                     'direct_approved_paths': [], 'required_input_target_ids': [], 'approved_upstream_path_target_ids': []}]}
    z = evaluate(api, r)
    assert z['evaluator_status'] == 'EVAL_OK'
    assert z['metrics']['benchmark_provenance_correctness'] == {'numerator': 1, 'denominator': 1}
    assert z['metrics']['complete_numeric_answer'] is True


@pytest.mark.parametrize('bad_path,bad_value', [
    (['gold_value'], {}), (['gold_basis'], []), (['approved_candidate_ids'], 'not-a-list'),
    (['final_mapping_status'], 'future'), (['candidate_review_counts', 'approved'], -1),
    (['stage1_candidates', 0, 'fact', 'context_ref'], []),
    (['stage1_candidates', 0, 'fact', 'dimensions'], 'dimensionless'),
    (['stage1_candidates', 0, 'fact', 'accession'], 'forged'),
])
def test_D25_D26_strict_concrete_source_schema(api, bad_path, bad_value):
    src = json.loads((ROOT/'evaluation/dev/xbrl/dev_xbrl_map_v0.1.json').read_text())
    t = next(t for t in src['targets'] if t['final_mapping_status'] == 'mapped')
    node = t
    for key in bad_path[:-1]:node = node[key]
    node[bad_path[-1]] = bad_value
    # Invalid source must fail before any index projection or defaulting.
    z = api.adapt_dev_xbrl_map_v0_2(src, source_sha256=hashlib.sha256(json_bytes(src)).hexdigest(), fact_index=None, numeric_values=[])
    assert z['evaluator_status'] == 'EVAL_INPUT_INVALID'
    assert z['normalized_map'] is None


def test_D30_outside_source_identity(api):
    r = request(); r['chunk_catalog'][0]['source_allowed'] = False
    z = evaluate(api, r)
    assert z['metrics']['outside_source_count'] == 1
    assert 'outside_source_contract' in z['reason_codes']
    assert z['metrics']['provenance_validity'] == {'numerator': 0, 'denominator': 1}


@pytest.mark.parametrize('field', [
    'semantic_item_match', 'citation_support', 'material_claim_requires_citation', 'causal_overreach',
    'answer_claim_consistency', 'evidence_item_coverage', 'evidence_all_parts_rate',
    'evidence_weighted_partial_coverage', 'evidence_weighted_strict_coverage', 'evidence_core_coverage',
    'evidence_strict_grounded_correctness', 'unsupported_material_claim_rate', 'numeric_strict_grounded_correctness',
])
def test_D31_D32_D33_literal_judge_boundary(api, field):
    z = evaluate(api, request())
    assert z['metrics']['judge_dependent'][field] == 'PENDING_JUDGE'
    assert z['metrics']['deterministic_subtotal'] is None


@pytest.mark.parametrize('event', ['EVT_FIXED_TOP_K_VIOLATION', 'EVT_TOOL_ARGUMENT_REJECTED', 'EVT_TOOL_ZERO_RESULT', 'EVT_TOOL_DOMAIN_ERROR_RECOVERABLE'])
def test_D34_recoverable_events(api, event):
    r = request(); r['slot_record']['events'] = [event]
    z = evaluate(api, r)
    assert z['metrics']['event_counts'][event] == 1
    assert z['evaluator_status'] == 'EVAL_OK'
    assert z['metrics']['complete_numeric_answer'] is True


@pytest.mark.parametrize('status', ['FAIL_TOOL_BUDGET_EXHAUSTED', 'FAIL_STEP_BUDGET_EXHAUSTED', 'FAIL_FINAL_SCHEMA_INVALID', 'FAIL_NO_VALID_FINAL_OUTPUT', 'FAIL_AGENT_ORCHESTRATION_UNRECOVERABLE'])
def test_D36_all_literal_terminal_statuses(api, status):
    r = request(); s = r['slot_record']; s.update(execution_status=status, agent_output_present=False)
    s['attempts'][0]['execution_status'] = status; r['agent_output_json'] = None; r['agent_output_sha256'] = None
    z = evaluate(api, r)
    assert z['execution_status'] == status
    assert z['evaluator_status'] == 'EVAL_OK'
    assert z['included_in_scored_denominator'] is True
    assert z['metrics']['completion_dependent_zero'] is True
    assert z['metrics']['numeric_value_correctness'] == {'numerator': 0, 'denominator': 1}
    assert z['metrics']['complete_numeric_answer'] is False


@pytest.mark.parametrize('replacement,completion,included', [
    ('RUN_COMPLETED', 'EVAL_COMPLETE', True), ('INFRA_RUN_RETRY_EXHAUSTED', 'EVAL_INCOMPLETE', False),
])
def test_D37_D38_replacement_completion(api, replacement, completion, included):
    r = request(); s = r['slot_record']; s.update(execution_status=replacement, effective_attempt_id='run-2', replacement_for_slot_id='slot-1',
        agent_output_present=replacement == 'RUN_COMPLETED', infrastructure_exhausted=replacement == 'INFRA_RUN_RETRY_EXHAUSTED')
    s['attempts'] = [{'attempt_id': 'run-1', 'execution_status': 'INFRA_RUN_RETRY_EXHAUSTED', 'replacement_for_attempt_id': None},
                     {'attempt_id': 'run-2', 'execution_status': replacement, 'replacement_for_attempt_id': 'run-1'}]
    if not included:r['agent_output_json'] = None; r['agent_output_sha256'] = None
    z = evaluate(api, r)
    assert z['evaluator_status'] == 'EVAL_OK'
    assert z['included_in_scored_denominator'] is included
    assert z['evaluation_completion']['evaluation_status'] == completion
    assert z['evaluation_completion']['scheduled_slot_count'] == 1
    assert z['evaluation_completion']['scored_slot_count'] == (1 if included else 0)
    assert z['evaluation_completion']['missing_infrastructure_slot_ids'] == ([] if included else ['slot-1'])
    if not included:assert z['metrics'] is None


@pytest.mark.parametrize('field,bad', [('execution_status','FAIL_FUTURE'), ('execution_status','FAIL_CONTEXT_WINDOW_EXCEEDED'), ('execution_status','EVAL_INCOMPLETE'), ('events',['EVT_TOOL_RESULT_TOO_LARGE']), ('events',['EVT_FUTURE'])])
def test_D39_unknown_or_wrong_namespace_status(api, field, bad):
    r = request(); r['slot_record'][field] = bad
    assert_system_error(evaluate(api, r), 'EVAL_CONTRACT_MISMATCH')


def test_D35_completed_wrong_answer(api):
    z = evaluate(api, numeric_request('999'))
    assert z['execution_status'] == 'RUN_COMPLETED'
    assert z['evaluator_status'] == 'EVAL_OK'
    assert z['included_in_scored_denominator'] is True
    assert z['metrics']['complete_numeric_answer'] is False


def test_D40_nonapplicable_numeric_panel(api):
    r = request(); r['gold_bundle']['answer_groups'] = []; r['gold_bundle']['numeric_targets'] = []
    a = output(); c = a['claims'][0]; c['claim_type'] = 'factual'; c.pop('numeric_value')
    z = evaluate(api, put_output(r, a))
    assert z['metrics']['numeric_value_correctness'] is None
    assert z['metrics']['complete_numeric_answer'] is None
    assert z['metrics']['deterministic_subtotal'] is None


def test_D41_canonical_bytes_and_hash(api):
    z = evaluate(api, request()); again = evaluate(api, request())
    expected = json_bytes(z)
    assert api.canonical_json_bytes(z) == expected
    assert api.canonical_json_bytes(again) == expected
    assert api.result_sha256(z) == hashlib.sha256(expected).hexdigest()
    assert expected.endswith(b'\n') and not expected.endswith(b'\n\n')


def test_D42_same_algorithm_for_synthetic_split_labels(api):
    dev = request(); other = deepcopy(dev); other['split'] = 'TEST'
    # This is a synthetic label substitution; no locked TEST artifact is read.
    a = evaluate(api, dev); b = evaluate(api, other)
    assert a == b


@pytest.mark.parametrize('source', ['future_gold', '', 'test_csv_guessed'])
def test_D42_unsupported_source_dispatch(api, source):
    r = request(); r['gold_bundle']['source_format_version'] = source
    assert_system_error(evaluate(api, r), 'EVAL_INPUT_INVALID')


@pytest.mark.parametrize('names,reverse,correct', [
    (['base','adjustment'], False, True), (['base','adjustment'], True, True),
    (['x','y'], False, True), (['x','y'], True, False),
    (['base','y'], False, False), (['base','base'], False, False),
])
def test_D16_explicit_or_positional_input_binding(api, names, reverse, correct):
    from d2_v2_contract_fixtures import two_input_request
    r = two_input_request(); a = get_output(r); c = a['calculations'][0]
    for item, name in zip(c['inputs'], names):item['name'] = name
    if reverse:c['inputs'].reverse()
    z = evaluate(api, put_output(r, a))
    assert z['evaluator_status'] == 'EVAL_OK'
    assert z['metrics']['complete_numeric_answer'] is correct
    if correct:assert z['metrics']['required_input_correctness'] == {'numerator':2,'denominator':2}


@pytest.mark.parametrize('expression,correct', [
    ('I001-I002', True), ('(I001)-(I002)', True),
    ('I001+(-I002)', False), ('-I002+I001', False), ('I002-I001', False),
])
def test_D17_no_algebraic_formula_repair(api, expression, correct):
    from d2_v2_contract_fixtures import two_input_request
    r = two_input_request(); a = get_output(r); a['calculations'][0]['expression'] = expression
    z = evaluate(api, put_output(r, a))
    assert z['metrics']['formula_correctness'] is correct


@pytest.mark.parametrize('expression,values,result,correct', [
    ('a+b*c', {'a':'1','b':'2','c':'3'}, '7', True),
    ('a/b', {'a':'1','b':'3'}, '0.33333333333333333333333333333333333333333333333333', True),
    ('a+b', {'a':'0.1','b':'0.2'}, '0.3', True),
    ('a+b', {'a':'0.1','b':'0.2'}, '0.30000000000000004', False),
    ('a', {'a':'1','unused':'2'}, '1', False),
    ('a+b', {'a':'1'}, '1', False),
])
def test_D18_calculator_component_contract(api, expression, values, result, correct):
    # Public component entry point is frozen by S8; no expected calculator constants imported.
    z = api.audit_arithmetic_v0_2(expression, values, result)
    assert z['arithmetic_correct'] is correct


@pytest.mark.parametrize('state', ['unmappable','no_xbrl_counterpart_in_frozen_corpus'])
def test_D26_concrete_source_valid_nonmapped_states(api, state):
    from d2_v2_contract_fixtures import source_map_fixture
    s,index,values = source_map_fixture(ROOT)
    t = next(t for t in s['targets'] if t['final_mapping_status']=='unmappable')
    if state == 'no_xbrl_counterpart_in_frozen_corpus':
        t['final_mapping_status'] = state; t['unmappable_reason_code'] = None
        t['temporal_resolution'].update(status='RESOLVED_EXACT_TARGET_DATE',mode='EXACT_TARGET_DATE',
            resolution_rule_id='exact_target_date_v0.1',resolved_temporal={'kind':'instant','instant':'2024-03-31'})
        t['stage_completion']['stage3'] = 'completed'
        s['final_status_counts']['unmappable'] -= 1; s['final_status_counts'][state] += 1
    z = api.adapt_dev_xbrl_map_v0_2(s,source_sha256=hashlib.sha256(json_bytes(s)).hexdigest(),fact_index=index,numeric_values=values)
    assert z['evaluator_status'] == 'EVAL_OK'
    validate('normalized_xbrl_map_v0.2.schema.json',z['normalized_map'])
    nt = next(row for row in z['normalized_map']['targets'] if row['target_id']==t['target_id'])
    assert nt['state'] == 'NO_APPROVED_XBRL_PATH'
    assert nt['source_state'] == state
    assert nt['direct_approved_paths'] == []


@pytest.mark.parametrize('defect', ['approved_id','count','fact_copy','temporal','duplicate_target','missing_input'])
def test_D25_source_semantic_validation_before_adaptation(api, defect):
    from d2_v2_contract_fixtures import source_map_fixture
    s,index,values = source_map_fixture(ROOT)
    t = next(t for t in s['targets'] if t['final_mapping_status']=='mapped')
    if defect=='approved_id':t['approved_candidate_ids']=['unknown']
    if defect=='count':t['candidate_review_counts']['approved']=2
    if defect=='fact_copy':t['stage1_candidates'][0]['fact_locator']='different#fact'
    if defect=='temporal':t['stage1_candidates'][0]['fact']['period_end']='2024-01-01'
    if defect=='duplicate_target':s['targets'].append(deepcopy(t))
    if defect=='missing_input':next(t for t in s['targets'] if t['target_kind']=='derived')['required_input_ids']=['unknown']
    z=api.adapt_dev_xbrl_map_v0_2(s,source_sha256=hashlib.sha256(json_bytes(s)).hexdigest(),fact_index=index,numeric_values=values)
    assert z['evaluator_status']=='EVAL_INPUT_INVALID'
    assert z['normalized_map'] is None


@pytest.mark.parametrize('defect', ['wrong_slot','third_attempt','replacement_after_failure','same_attempt_id'])
def test_D37_invalid_replacement_lineage(api, defect):
    r=request();s=r['slot_record'];s['effective_attempt_id']='run-2';s['replacement_for_slot_id']='slot-1'
    s['attempts']=[{'attempt_id':'run-1','execution_status':'INFRA_RUN_RETRY_EXHAUSTED','replacement_for_attempt_id':None},
                   {'attempt_id':'run-2','execution_status':'RUN_COMPLETED','replacement_for_attempt_id':'run-1'}]
    if defect=='wrong_slot':s['replacement_for_slot_id']='other-slot'
    if defect=='third_attempt':s['attempts'].append(deepcopy(s['attempts'][1]))
    if defect=='replacement_after_failure':s['attempts'][0]['execution_status']='FAIL_NO_VALID_FINAL_OUTPUT'
    if defect=='same_attempt_id':s['attempts'][1]['attempt_id']='run-1'
    assert_system_error(evaluate(api,r),'EVAL_INPUT_INVALID')


@pytest.mark.parametrize('status',['EVAL_INPUT_INVALID','EVAL_CONTRACT_MISMATCH','EVAL_INTERNAL_ERROR'])
def test_D01_D39_evaluator_error_schema(status):
    z={'result_schema_version':'deterministic_evaluator_result_v0.2','evaluator_version':'deterministic_evaluator_v0.2',
       'question_id':None,'scheduled_slot_id':None,'effective_attempt_id':None,'execution_status':None,
       'evaluator_status':status,'evaluation_completion':None,'agent_output_contract_valid':None,'calculation_graph':None,
       'assignment':None,'included_in_scored_denominator':False,'checkpoint_valid':False,'metrics':None,
       'reason_codes':[],'errors':[{'code':'SYNTHETIC_ERROR','path':'/','message':'Synthetic schema fixture'}]}
    validate('deterministic_evaluator_output_schema_v0.2.json',z)
    z['included_in_scored_denominator']=True
    with pytest.raises(ValidationError):validate('deterministic_evaluator_output_schema_v0.2.json',z)


def test_D40_aggregate_denominators(api):
    # Structural aggregate input isolates counting from any implementation evaluator outputs.
    z=api.aggregate_metrics_v0_2([
        {'slot_id':'S1','execution_status':'RUN_COMPLETED','applicable':True,'numerator':1,'denominator':1},
        {'slot_id':'S2','execution_status':'FAIL_NO_VALID_FINAL_OUTPUT','applicable':True,'numerator':0,'denominator':1},
        {'slot_id':'S3','execution_status':'INFRA_RUN_RETRY_EXHAUSTED','applicable':True,'numerator':None,'denominator':None},
        {'slot_id':'S4','execution_status':'RUN_COMPLETED','applicable':False,'numerator':None,'denominator':None},
    ])
    assert z=={'scheduled_slot_count':4,'scored_slot_count':3,'metric':{'numerator':1,'denominator':2},
               'missing_infrastructure_slot_ids':['S3'],'evaluation_status':'EVAL_INCOMPLETE','deterministic_subtotal':None}


@pytest.mark.parametrize('cu,gu,status', [('CUSTOM','CUSTOM','exact_label_match'),('CUSTOM','other','unregistered_unit'),('USD_per_basic_share','USD_per_share','registered_equivalence')])
def test_D05_D07_unit_audit_status(api,cu,gu,status):
    z=evaluate(api,numeric_request('10','10',cu,gu))
    assert z['metrics']['answer_group_results'][0]['occurrences'][0]['unit_result']['status']==status


@pytest.mark.parametrize('field,value',[('period','YTD'),('basis','non-GAAP')])
def test_D13_D14_no_period_or_basis_rescue(api,field,value):
    r=request();a=output();a['claims'][0]['numeric_value'][field]=value
    z=evaluate(api,put_output(r,a))
    assert z['metrics']['complete_numeric_answer'] is False


def test_D23_derived_AND_of_two_provenance_routes(api):
    from d2_v2_contract_fixtures import two_input_request
    r=two_input_request();a=get_output(r)
    a['calculations'][0]['inputs'][1]['provenance']=[{'provenance_type':'chunk',**chunk('chunk-b')}]
    z=evaluate(api,put_output(r,a))
    assert z['metrics']['provenance_completeness'] is False
    assert z['metrics']['deterministic_grounded_prerequisites'] is False
    assert z['metrics']['numeric_value_correctness']=={'numerator':1,'denominator':1}


def test_D24_exact_duration_identity(api):
    r=xbrl_request(); temporal={'kind':'duration','period_start':'2024-01-01','period_end':'2024-03-31'}
    for f in r['frozen_xbrl_fact_index']['facts']:f['temporal']=deepcopy(temporal)
    paths=[r['normalized_xbrl_map']['targets'][0]['direct_approved_paths'][0],r['gold_bundle']['numeric_targets'][0]['approved_xbrl_paths'][0],r['gold_bundle']['answer_groups'][0]['variants'][0]['approved_xbrl_paths'][0]]
    for p in paths:p['fact_identity']['temporal']=deepcopy(temporal)
    a=get_output(r);p=a['claims'][0]['provenance'][0];p.pop('instant');p.update(period_start='2024-01-01',period_end='2024-03-31')
    z=evaluate(api,put_output(r,a))
    assert z['metrics']['provenance_validity']=={'numerator':1,'denominator':1}


def test_D29_stable_multiple_identity_counts(api):
    r=request();a=output();a['claims'].append(claim('C002'));a['answer_claim_ids'].append('C002')
    a['claims'][0]['provenance'][0]['chunk_id']='forged'
    a['claims'][1]['provenance'][0]['accession']='0000000002-24-000001'
    z=evaluate(api,put_output(r,a))
    assert z['metrics']['invalid_identity_count']==2
    assert z['metrics']['hallucinated_identity_count']==2
    assert z['metrics']['provenance_validity']=={'numerator':0,'denominator':2}
    assert z['reason_codes']==sorted(set(z['reason_codes']))


def test_D30_no_prose_source_scope_heuristic(api):
    r=request();a=output();a['answer']='Synthetic prose mentioning news and a causal claim; semantic judgment is pending.'
    z=evaluate(api,put_output(r,a))
    assert z['metrics']['outside_source_count']==0
    assert z['metrics']['judge_dependent']['causal_overreach']=='PENDING_JUDGE'
    assert z['metrics']['judge_dependent']['answer_claim_consistency']=='PENDING_JUDGE'


@pytest.mark.parametrize('case,reverse,selected,passing', [
    ('larger_pass', False, 'V2', ['V2']),
    ('larger_pass', True, 'V2', ['V2']),
    ('both_pass', False, 'V1', ['V1', 'V2']),
    ('both_pass', True, 'V1', ['V1', 'V2']),
])
def test_CD02_A_B_E_complete_alternatives(api, case, reverse, selected, passing):
    from d2_v2_contract_fixtures import cd02_request
    z = evaluate(api, cd02_request(case, reverse))
    group = z['metrics']['answer_group_results'][0]; o = group['occurrences'][0]
    assert group['correct'] is True
    assert z['metrics']['complete_numeric_answer'] is True
    assert z['metrics']['numeric_value_correctness'] == {'numerator': 1, 'denominator': 1}
    assert o['variant_id'] == selected
    assert o['variant_selection'] == {
        'selection_schema_version': 'variant_selection_v0.2',
        'eligible_variant_ids': ['V1', 'V2'], 'complete_passing_variant_ids': passing,
        'selected_variant_id': selected, 'selection_mode': 'COMPLETE_PASS',
        'complete_deterministic_pass': True, 'reason_codes': [],
    }


@pytest.mark.parametrize('case,reverse,correct_inputs,input_flags,formula_ok', [
    ('unequal_partials', False, 0, [False, False], False),
    ('unequal_partials', True, 0, [False, False], False),
    ('canonical_diagnostics', False, 1, [True, False], True),
    ('canonical_diagnostics', True, 1, [True, False], True),
])
def test_CD02_C_D_E_all_partial_diagnostics_canonical(api, case, reverse, correct_inputs, input_flags, formula_ok):
    from d2_v2_contract_fixtures import cd02_request
    z = evaluate(api, cd02_request(case, reverse)); m = z['metrics']
    group = m['answer_group_results'][0]; o = group['occurrences'][0]
    assert group['correct'] is False
    assert m['complete_numeric_answer'] is False
    assert o['variant_id'] == 'A'
    assert o['variant_selection'] == {
        'selection_schema_version': 'variant_selection_v0.2',
        'eligible_variant_ids': ['A', 'B'], 'complete_passing_variant_ids': [],
        'selected_variant_id': 'A', 'selection_mode': 'CANONICAL_DIAGNOSTIC',
        'complete_deterministic_pass': False, 'reason_codes': ['NO_COMPLETE_VARIANT_PASS'],
    }
    assert o['numeric_correct'] is True
    assert o['formula_correct'] is formula_ok
    assert o['arithmetic_correct'] is False
    assert o['approved_path_valid'] is True
    assert o['input_correctness'] == {'numerator': correct_inputs, 'denominator': 2}
    assert o['input_results'] == [
        {'input_role': 'a', 'source_target_id': 'A_a', 'numeric_correct': input_flags[0], 'approved_path_valid': True},
        {'input_role': 'b', 'source_target_id': 'A_b', 'numeric_correct': input_flags[1], 'approved_path_valid': True},
    ]
    expected_reasons = (['ARITHMETIC_MISMATCH', 'NO_COMPLETE_VARIANT_PASS', 'REQUIRED_INPUT_MISMATCH'] if formula_ok else
                        ['ARITHMETIC_MISMATCH', 'FORMULA_MISMATCH', 'NO_COMPLETE_VARIANT_PASS', 'REQUIRED_INPUT_MISMATCH'])
    assert o['reason_codes'] == expected_reasons
    if formula_ok: assert 'FORMULA_MISMATCH' not in z['reason_codes']
    assert m['formula_correctness'] is formula_ok
    assert m['arithmetic_correctness'] is False
    assert m['required_input_correctness'] == {'numerator': correct_inputs, 'denominator': 2}
    assert m['numeric_value_correctness'] == {'numerator': 1, 'denominator': 1}


@pytest.mark.parametrize('variant_id,family_id,eligible,selected,passes,mode', [
    ('V1', None, ['V1'], 'V1', False, 'CANONICAL_DIAGNOSTIC'),
    ('V2', None, ['V2'], 'V2', True, 'COMPLETE_PASS'),
    (None, 'F1', ['V1'], 'V1', False, 'CANONICAL_DIAGNOSTIC'),
    (None, 'F2', ['V2'], 'V2', True, 'COMPLETE_PASS'),
    ('V1', 'F1', ['V1'], 'V1', False, 'CANONICAL_DIAGNOSTIC'),
])
def test_CD02_F_explicit_identifier_restricts_before_results(api, variant_id, family_id, eligible, selected, passes, mode):
    from d2_v2_contract_fixtures import cd02_selector_request
    r = cd02_selector_request(); r.update(explicit_variant_id=variant_id, explicit_family_id=family_id)
    z = api.select_variant_v0_2(r)
    validate('variant_selection_v0.2.schema.json', z, 'response')
    assert z['evaluator_status'] == 'EVAL_OK'
    assert z['selection'] == {
        'selection_schema_version': 'variant_selection_v0.2',
        'eligible_variant_ids': eligible, 'complete_passing_variant_ids': [selected] if passes else [],
        'selected_variant_id': selected, 'selection_mode': mode,
        'complete_deterministic_pass': passes,
        'reason_codes': [] if passes else ['NO_COMPLETE_VARIANT_PASS'],
    }


@pytest.mark.parametrize('variant_id,family_id,reason', [
    ('UNKNOWN', None, 'UNKNOWN_VARIANT_IDENTIFIER'),
    (None, 'UNKNOWN', 'UNKNOWN_FAMILY_IDENTIFIER'),
    ('V1', 'F2', 'CONFLICTING_VARIANT_IDENTIFIERS'),
])
def test_CD02_G_invalid_identifier_no_fallback(api, variant_id, family_id, reason):
    from d2_v2_contract_fixtures import cd02_selector_request
    r = cd02_selector_request(); r.update(explicit_variant_id=variant_id, explicit_family_id=family_id)
    z = api.select_variant_v0_2(r)
    validate('variant_selection_v0.2.schema.json', z, 'response')
    assert z == {'evaluator_status': 'EVAL_INPUT_INVALID', 'selection': None, 'reason_codes': [reason]}


@pytest.mark.parametrize('explicit,empty_group', [(None, False), ('V2', False), (None, True)])
def test_CD02_H_empty_eligibility(api, explicit, empty_group):
    from d2_v2_contract_fixtures import cd02_selector_request
    r = cd02_selector_request(); r['explicit_variant_id'] = explicit
    for v in r['approved_variants']: v['structurally_applicable'] = False
    if empty_group: r.update(approved_variants=[], candidate_results=[])
    z = api.select_variant_v0_2(r)
    validate('variant_selection_v0.2.schema.json', z, 'response')
    assert z == {'evaluator_status': 'EVAL_OK', 'reason_codes': [], 'selection': {
        'selection_schema_version': 'variant_selection_v0.2',
        'eligible_variant_ids': [], 'complete_passing_variant_ids': [],
        'selected_variant_id': None, 'selection_mode': 'NO_ELIGIBLE_VARIANT',
        'complete_deterministic_pass': False, 'reason_codes': ['NO_ELIGIBLE_VARIANT'],
    }}


def test_CD02_H_unmatched_occurrence_no_selected_variant(api):
    r = request(); r['gold_bundle']['answer_groups'][0]['multiplicity'] = 2
    z = evaluate(api, r); o = z['metrics']['answer_group_results'][0]['occurrences'][1]
    assert o['variant_id'] is None
    assert o['variant_selection']['selection_mode'] == 'NO_ELIGIBLE_VARIANT'
    assert o['variant_selection']['reason_codes'] == ['NO_ELIGIBLE_VARIANT']
    assert o['input_results'] == []
    assert z['metrics']['complete_numeric_answer'] is False


@pytest.mark.parametrize('field', ['variant_id', 'variant_family', 'answer_group_id'])
def test_CD02_raw_v011_does_not_gain_identifier_fields(api, field):
    r = request(); a = output(); a['claims'][0][field] = 'V1'
    assert_system_error(evaluate(api, put_output(r, a)), 'EVAL_INPUT_INVALID')


@pytest.mark.parametrize('defect', ['unknown_key', 'duplicate_variant', 'duplicate_result', 'unknown_result', 'missing_result', 'string_boolean'])
def test_CD02_selector_fail_closed(api, defect):
    from d2_v2_contract_fixtures import cd02_selector_request
    r = cd02_selector_request()
    if defect == 'unknown_key': r['partial_score'] = 100
    elif defect == 'duplicate_variant': r['approved_variants'].append(deepcopy(r['approved_variants'][0]))
    elif defect == 'duplicate_result': r['candidate_results'].append(deepcopy(r['candidate_results'][0]))
    elif defect == 'unknown_result': r['candidate_results'][0]['variant_id'] = 'UNKNOWN'
    elif defect == 'missing_result': r['candidate_results'].pop()
    elif defect == 'string_boolean': r['approved_variants'][0]['structurally_applicable'] = 'false'
    z = api.select_variant_v0_2(r)
    validate('variant_selection_v0.2.schema.json', z, 'response')
    assert z['evaluator_status'] == 'EVAL_INPUT_INVALID'
    assert z['selection'] is None
    assert z['reason_codes']


@pytest.mark.parametrize('reverse', [False, True])
def test_CD02_D19_canonical_input_denominator(api, reverse):
    from d2_v2_contract_fixtures import cd02_request
    z = evaluate(api, cd02_request('different_denominators', reverse))
    o = z['metrics']['answer_group_results'][0]['occurrences'][0]
    assert o['variant_id'] == 'A'
    assert o['variant_selection']['complete_passing_variant_ids'] == []
    assert o['input_correctness'] == {'numerator': 0, 'denominator': 1}
    assert z['metrics']['required_input_correctness'] == {'numerator': 0, 'denominator': 1}
    assert o['input_results'] == [{'input_role': 'a', 'source_target_id': 'A_a', 'numeric_correct': False, 'approved_path_valid': True}]
    assert z['metrics']['complete_numeric_answer'] is False


def test_CD02_D14_multiplicity_cannot_mix_families(api):
    r = request(); g = r['gold_bundle']; g['answer_groups'][0]['multiplicity'] = 2
    t1 = target('T1', '10'); t1['variant_family'] = 'F1'
    t2 = target('T2', '20'); t2['variant_family'] = 'F2'
    g['numeric_targets'] = [t1, t2]
    g['answer_groups'][0]['variants'] = [variant(t1, 'V1'), variant(t2, 'V2')]
    a = output(); a['claims'].append(claim('C002', '20')); a['answer_claim_ids'].append('C002')
    z = evaluate(api, put_output(r, a))
    assert z['metrics']['variant_consistency'] == 'FAIL'
    assert z['metrics']['answer_group_results'][0]['correct'] is False
    assert z['metrics']['complete_numeric_answer'] is False
