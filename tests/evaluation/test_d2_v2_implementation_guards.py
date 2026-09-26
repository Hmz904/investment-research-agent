"""Additional implementation checks; the independent frozen suite is unchanged."""
from copy import deepcopy
from decimal import Decimal, localcontext
import hashlib

import pytest
from jsonschema import Draft202012Validator

from evaluation.d2 import deterministic_evaluator as api
from evaluation.d2.validation_v0_2 import InputError, _Validator, canonical_json_bytes
from evaluation.d2.source_adapters_v0_2 import adapt_gold_bundle_v0_2
from d2_v2_contract_fixtures import (request, xbrl_request, get_output, put_output,
    cd02_selector_request, source_map_fixture, precision)


@pytest.mark.parametrize('values', [[True, 1], [False, 0], [1, Decimal('1.00')],
    [{'x': [1, True]}, {'x': [Decimal('1.0'), True]}], [{'x': True}, {'x': 1}],
    [{'a': 1, 'b': 2}, {'b': 2, 'a': 1}], [None, None]])
def test_linear_unique_items_matches_draft202012(values):
    schema = {'type': 'array', 'uniqueItems': True}
    assert _Validator(schema).is_valid(values) == Draft202012Validator(schema).is_valid(values)


def test_unknown_typed_status_and_python_float_are_input_errors():
    for status in ({}, [], 1, False):
        r = request(); r['slot_record']['execution_status'] = status
        assert api.evaluate_v0_2(r)['evaluator_status'] == 'EVAL_INPUT_INVALID'
    r = request(); r['gold_bundle']['answer_groups'][0]['multiplicity'] = 1.0
    assert api.evaluate_v0_2(r)['evaluator_status'] == 'EVAL_INPUT_INVALID'


def test_exact_comparison_does_not_depend_on_ambient_decimal_context():
    r = request(); a = get_output(r)
    value = '123456789012345678901234567890.1234567890123456789'
    for t in (r['gold_bundle']['numeric_targets'][0], r['gold_bundle']['answer_groups'][0]['variants'][0]):
        t['accepted_value'] = value
        t['precision'].update(reference_value=value, interval=dict(lower=value, upper=value,
                               lower_inclusive=True, upper_inclusive=True))
    a['claims'][0]['numeric_value']['value'] = Decimal(value)
    put_output(r, a)
    baseline = api.evaluate_v0_2(r)
    with localcontext() as context:
        context.prec = 3
        assert api.evaluate_v0_2(r) == baseline
    assert baseline['metrics']['complete_numeric_answer'] is True


def test_selector_lexicographic_order_and_omitted_ineligible_result():
    r = cd02_selector_request()
    r['approved_variants'][0]['variant_id'] = 'V10'
    r['candidate_results'][0]['variant_id'] = 'V10'
    for result in r['candidate_results']:
        result['complete_deterministic_pass'] = True
    assert api.select_variant_v0_2(r)['selection']['selected_variant_id'] == 'V10'
    r['approved_variants'][0]['structurally_applicable'] = False
    r['candidate_results'] = r['candidate_results'][1:]
    assert api.select_variant_v0_2(r)['selection']['selected_variant_id'] == 'V2'


def test_disconnected_dangling_calculation_invalidates_contract():
    from d2_v2_contract_fixtures import calculation
    r = request(); a = get_output(r); a['calculations'] = [calculation('K001', 'K999')]
    z = api.evaluate_v0_2(put_output(r, a))
    assert z['calculation_graph']['invalid_calculation_ids'] == ['K001']
    assert z['metrics']['numeric_value_correctness'] == {'numerator': 1, 'denominator': 1}
    assert z['metrics']['complete_numeric_answer'] is False


def test_xbrl_false_accession_counts_as_hallucinated():
    r = xbrl_request(); a = get_output(r)
    a['claims'][0]['provenance'][0]['accession'] = '0000000002-24-000001'
    z = api.evaluate_v0_2(put_output(r, a))
    assert z['metrics']['hallucinated_identity_count'] == 1
    assert 'wrong_fact_identity' in z['reason_codes']


def test_nonnumeric_xbrl_cannot_support_narrative_claim():
    r = xbrl_request(); a = get_output(r)
    a['claims'][0].update(claim_type='factual'); a['claims'][0].pop('numeric_value')
    r['xbrl_numeric_values'][1]['normalized_value'] = None
    a['claims'][0]['provenance'][0]['fact_locator'] = 'SYNTH_DOC#f0001'
    z = api.evaluate_v0_2(put_output(r, a))
    assert z['metrics']['provenance_validity'] == {'numerator': 0, 'denominator': 1}
    assert z['metrics']['provenance_findings'][0]['FACT_IDENTITY_VALID'] is True


def test_map_canonical_object_hash_is_checked_before_projection():
    from pathlib import Path
    s, index, values = source_map_fixture(Path(__file__).resolve().parents[2])
    z = api.adapt_dev_xbrl_map_v0_2(s, source_sha256='0' * 64, fact_index=index, numeric_values=values)
    assert z['evaluator_status'] == 'EVAL_CONTRACT_MISMATCH'
    assert z['normalized_map'] is None


@pytest.mark.parametrize('field,value', [('applicable', 'false'), ('numerator', True),
                                       ('denominator', 0), ('extra', 1)])
def test_aggregate_closed_typed_records(field, value):
    record = dict(slot_id='S1', execution_status='RUN_COMPLETED', applicable=True, numerator=1, denominator=1)
    record[field] = value
    with pytest.raises(InputError):
        api.aggregate_metrics_v0_2([record])


def test_declared_v01_gold_upgrade_is_explicit_and_authenticated():
    r = request(); gold = deepcopy(r['gold_bundle'])
    gold.update(bundle_schema_version='gold_bundle_v0.1', adapter_version='gold_bundle_adapter_v0.1', source_format_version='gold_bundle_v0.1')
    gold.pop('source_sha256')
    for t in (gold['numeric_targets'][0], gold['answer_groups'][0]['variants'][0]):
        p = t['precision']; p['precision_schema_version'] = 'precision_record_v0.1'
        for k in ('precision_rule_id', 'comparison_unit', 'reference_value', 'interval'):
            p.pop(k)
    raw = canonical_json_bytes(gold)
    args = dict(declared_source_format='gold_bundle_v0.1', source_sha256=hashlib.sha256(raw).hexdigest(),
                chunk_catalog=r['chunk_catalog'], normalized_map=None, fact_index=None, numeric_values=[])
    z = adapt_gold_bundle_v0_2(raw, **args)
    assert z['evaluator_status'] == 'EVAL_OK'
    assert z['gold_bundle']['numeric_targets'][0]['precision']['interval'] == r['gold_bundle']['numeric_targets'][0]['precision']['interval']
    args['source_sha256'] = '0' * 64
    assert adapt_gold_bundle_v0_2(raw, **args)['evaluator_status'] == 'EVAL_CONTRACT_MISMATCH'


def test_arithmetic_is_separate_from_claim_to_result_binding():
    from d2_v2_contract_fixtures import derived_request
    r = derived_request(); a = get_output(r)
    a['calculations'][0]['inputs'][0]['value'] = Decimal('9')
    a['calculations'][0]['result']['value'] = Decimal('9')
    z = api.evaluate_v0_2(put_output(r, a))
    assert z['metrics']['arithmetic_correctness'] is True
    assert z['metrics']['numeric_value_correctness'] == {'numerator': 1, 'denominator': 1}
    assert z['metrics']['complete_numeric_answer'] is False


def test_provenance_counts_claims_while_numeric_counts_groups():
    from d2_v2_contract_fixtures import claim
    r = request(); r['gold_bundle']['answer_groups'][0]['multiplicity'] = 2
    a = get_output(r); a['claims'].append(claim('C002')); a['answer_claim_ids'].append('C002')
    z = api.evaluate_v0_2(put_output(r, a))
    assert z['metrics']['numeric_value_correctness'] == {'numerator': 1, 'denominator': 1}
    assert z['metrics']['benchmark_provenance_correctness'] == {'numerator': 2, 'denominator': 2}


def test_unreferenced_calculation_is_still_audited():
    from d2_v2_contract_fixtures import calculation
    r = request(); a = get_output(r); a['calculations'] = [calculation()]
    a['calculations'][0]['expression'] = 'I001/0'
    z = api.evaluate_v0_2(put_output(r, a))
    assert z['evaluator_status'] == 'EVAL_OK'
    assert z['metrics']['arithmetic_correctness'] is False
    assert z['metrics']['numeric_value_correctness'] == {'numerator': 1, 'denominator': 1}
