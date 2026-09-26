"""Synthetic input builders only; no scorer, expected-score computation or real output."""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json

FINGERPRINT = 'acaf087ee2c4fb7427377cae5f1968da26c75d4dfa565f67f1e056b2c4cc4eb6'


def json_bytes(value):
    def encode(v):
        if isinstance(v, Decimal):
            assert v.is_finite()
            return format(v, 'f')
        if isinstance(v, dict):
            return '{' + ','.join(json.dumps(k, ensure_ascii=False) + ':' + encode(v[k]) for k in sorted(v)) + '}'
        if isinstance(v, list):
            return '[' + ','.join(encode(x) for x in v) + ']'
        assert not isinstance(v, float)
        return json.dumps(v, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    return (encode(value) + '\n').encode()


def exact(value='10', unit='USD'):
    return {'precision_schema_version': 'precision_record_v0.2', 'mode': 'EXACT', 'quantum': None,
            'absolute_tolerance': None, 'rounding_mode': None, 'source_encoding': 'synthetic_frozen_exact',
            'source_value': None, 'precision_rule_id': 'precision_exact_v0.1', 'comparison_unit': unit,
            'reference_value': value, 'interval': {'lower': value, 'upper': value, 'lower_inclusive': True, 'upper_inclusive': True}}


def precision(value, mode, parameter, lower, upper, inclusive=True, unit='USD'):
    p = exact(value, unit)
    p.update(mode=mode, source_encoding='synthetic_frozen_' + mode, source_value=parameter,
             interval={'lower': lower, 'upper': upper, 'lower_inclusive': inclusive, 'upper_inclusive': inclusive})
    if mode == 'QUANTUM':
        p.update(quantum=parameter, rounding_mode='ROUND_HALF_EVEN', precision_rule_id='precision_rounding_quantum_v0.1')
    else:
        p.update(absolute_tolerance=parameter, precision_rule_id='precision_absolute_tolerance_v0.1')
    return p


def chunk(name='chunk-a'):
    return {'chunk_id': name, 'accession': '0000000001-24-000001', 'locator': 'Synthetic table ' + name}


def target(tid='T1', value='10', unit='USD', paths=True):
    return {'target_id': tid, 'accepted_value': value, 'unit': unit, 'period': 'Q1', 'basis': 'GAAP',
            'precision': exact(value, unit), 'variant_family': None,
            'approved_chunk_paths': [{'path_id': tid + '.chunk', 'members': [chunk()]}] if paths else [], 'approved_xbrl_paths': []}


def variant(t=None, vid='V1'):
    t = target() if t is None else t
    return {'variant_id': vid, 'variant_family': t['variant_family'], 'numeric_target_id': t['target_id'],
            **{k: deepcopy(t[k]) for k in ['accepted_value', 'unit', 'period', 'basis', 'precision', 'approved_chunk_paths', 'approved_xbrl_paths']},
            'sign_policy': 'SIGNED_EXACT', 'derived_specification': None}


def claim(cid='C001', value='10', unit='USD'):
    return {'claim_id': cid, 'text': 'Synthetic numeric claim', 'claim_type': 'numeric', 'entities': ['SYNTH'],
            'material': True, 'period': 'Q1', 'requires_citation': True, 'temporal_role': 'current',
            'numeric_value': {'value': Decimal(value), 'unit': unit, 'period': 'Q1', 'basis': 'GAAP', 'display_value': value},
            'provenance': [{'provenance_type': 'chunk', **chunk()}]}


def output():
    return {'schema_version': 'agent_output_v0.1.1', 'q_id': 'SYNTH_Q', 'answer': 'Synthetic answer',
            'answer_claim_ids': ['C001'], 'claims': [claim()], 'calculations': []}


def put_output(request, agent):
    raw = json_bytes(agent)
    request['agent_output_json'] = raw.decode()
    request['agent_output_sha256'] = hashlib.sha256(raw).hexdigest()
    return request


def get_output(request):
    return json.loads(request['agent_output_json'], parse_float=Decimal, parse_int=Decimal)


def request():
    t = target()
    r = {'request_schema_version': 'evaluation_request_v0.2', 'split': 'DEV',
         'contract_identity': {'protocol_version': 'eval_protocol_v0.2.2', 'taxonomy_version': 'execution_taxonomy_v0.1',
                              'agent_output_schema_version': 'agent_output_v0.1.1', 'mapping_spec_version': 'xbrl_gold_mapping_spec_v0.1.2',
                              'evaluator_contract_version': 'd2_contract_v0.2', 'xbrl_artifact_fingerprint': FINGERPRINT,
                              'corpus_fingerprint': '56df698d50b13cf15e913c1c60dbc96b1fd0fab44adb7b1f40ba99771c4b7c96'},
         'gold_bundle': {'bundle_schema_version': 'gold_bundle_v0.2', 'adapter_version': 'gold_bundle_adapter_v0.2',
                         'source_format_version': 'gold_bundle_v0.2', 'source_sha256': 'a' * 64, 'question_id': 'SYNTH_Q',
                         'numeric_targets': [t], 'answer_groups': [{'answer_group_id': 'G1', 'multiplicity': 1,
                             'question_consistency_group': None, 'variants': [variant(t)]}], 'judge_dependent_gold': {'items': []}},
         'slot_record': {'slot_record_schema_version': 'evaluation_slot_record_v0.2', 'adapter_version': 'evaluation_slot_record_adapter_v0.2',
                         'question_id': 'SYNTH_Q', 'scheduled_replicate_id': 'rep-1', 'scheduled_slot_id': 'slot-1',
                         'effective_attempt_id': 'run-1', 'replacement_for_slot_id': None, 'execution_status': 'RUN_COMPLETED',
                         'agent_output_present': True, 'infrastructure_exhausted': False, 'observable_runtime_references': [],
                         'attempts': [{'attempt_id': 'run-1', 'execution_status': 'RUN_COMPLETED', 'replacement_for_attempt_id': None}], 'events': []},
         'agent_output_json': None, 'agent_output_sha256': None,
         'chunk_catalog': [{**chunk(), 'source_allowed': True}, {**chunk('chunk-b'), 'source_allowed': True}],
         'normalized_xbrl_map': None, 'frozen_xbrl_fact_index': None, 'xbrl_numeric_values': []}
    return put_output(r, output())


def calculation(kid='K001', dependency=None):
    item = {'input_id': 'I001', 'name': 'base', 'value': Decimal('10'), 'unit': 'USD', 'period': 'Q1', 'basis': 'GAAP',
            'source_type': 'cited_fact', 'provenance': [{'provenance_type': 'chunk', **chunk()}]}
    if dependency is not None:
        item.update(source_type='prior_calculation', source_calculation_id=dependency)
        item.pop('provenance')
    return {'calculation_id': kid, 'expression': 'I001', 'inputs': [item],
            'result': {'value': Decimal('10'), 'unit': 'USD', 'display_value': '10'}}


def derived_request():
    r = request(); g = r['gold_bundle']; t = target('BASE'); g['numeric_targets'].append(t)
    v = g['answer_groups'][0]['variants'][0]
    v['derived_specification'] = {'derived_target_id': 'T1', 'required_inputs': [{'input_role': 'base', 'source_target_id': 'BASE', 'source_answer_group_id': None}],
                                  'allowed_formula_variants': [{'formula_variant_id': 'T1.formula.v1', 'canonical_formula': 'base'}],
                                  'output_unit': 'USD', 'output_precision': exact()}
    a = output(); a['claims'][0]['calculation_ids'] = ['K001']; a['calculations'] = [calculation()]
    return put_output(r, a)


def fact(i=0):
    fid = 'f' + str(i).zfill(4)
    return {'fact_locator': 'SYNTH_DOC#' + fid, 'stable_fact_id': 'SYNTH_DOC::' + fid, 'doc_id': 'SYNTH_DOC', 'fact_id': fid,
            'accession': '0000000001-24-000001', 'concept': 'us-gaap:Assets', 'context_ref': 'ctx-1',
            'entity_identifier': '0000000001', 'entity_scheme': 'http://www.sec.gov/CIK', 'unit': 'USD',
            'unit_measures': ['iso4217:USD'], 'unit_numerator': [], 'unit_denominator': [],
            'temporal': {'kind': 'instant', 'instant': '2024-03-31'}, 'dimensions': [], 'chunk_id': None}


def fact_index():
    return {'index_schema_version': 'frozen_xbrl_fact_index_v0.1', 'xbrl_artifact_fingerprint': FINGERPRINT,
            'expected_fact_count': 7839, 'facts': [fact(i) for i in range(7839)]}


def xbrl_request():
    r = request(); r['frozen_xbrl_fact_index'] = fact_index()
    r['xbrl_numeric_values'] = [{'fact_locator': f['fact_locator'], 'normalized_value': '10'} for f in r['frozen_xbrl_fact_index']['facts']]
    path = {'path_id': 'P1', 'candidate_id': 'CAN1', 'fact_identity': fact(), 'normalized_value': '10',
            'review_status': 'APPROVE', 'sign_relationship': 'same_sign', 'sign_approval': None}
    r['normalized_xbrl_map'] = {'normalized_map_schema_version': 'normalized_xbrl_map_v0.2', 'adapter_version': 'dev_xbrl_map_adapter_v0.2',
                              'source_schema_version': 'normalized_xbrl_map_v0.2', 'source_sha256': 'b' * 64,
                              'xbrl_artifact_fingerprint': FINGERPRINT, 'targets': [{'target_id': 'T1', 'question_id': 'SYNTH_Q',
                                  'state': 'DIRECT_APPROVED', 'source_state': 'mapped', 'direct_approved_paths': [path],
                                  'required_input_target_ids': [], 'approved_upstream_path_target_ids': []}]}
    for t in r['gold_bundle']['numeric_targets']:t['approved_xbrl_paths'] = [deepcopy(path)]
    r['gold_bundle']['answer_groups'][0]['variants'][0]['approved_xbrl_paths'] = [deepcopy(path)]
    a = output(); f = fact(); a['claims'][0]['provenance'] = [{'provenance_type': 'xbrl_fact',
        **{k: f[k] for k in ['fact_locator', 'accession', 'concept', 'context_ref', 'unit']}, 'instant': '2024-03-31'}]
    return put_output(r, a)


def two_input_request():
    r = derived_request(); g = r['gold_bundle']; g['numeric_targets'][1] = target('BASE', '13')
    g['numeric_targets'].append(target('ADJUSTMENT', '3'))
    spec = g['answer_groups'][0]['variants'][0]['derived_specification']
    spec['required_inputs'].append({'input_role': 'adjustment', 'source_target_id': 'ADJUSTMENT', 'source_answer_group_id': None})
    spec['allowed_formula_variants'] = [{'formula_variant_id': 'T1.formula.v1', 'canonical_formula': '(base - adjustment)'}]
    a = get_output(r); c = a['calculations'][0]; c['expression'] = 'I001-I002'; c['inputs'][0]['value'] = Decimal('13')
    second = deepcopy(c['inputs'][0]); second.update(input_id='I002', name='adjustment', value=Decimal('3')); c['inputs'].append(second)
    return put_output(r, a)


def source_map_fixture(root):
    # Permitted DEV mapping used only as input structure, never as real output.
    s = json.loads((root/'evaluation/dev/xbrl/dev_xbrl_map_v0.1.json').read_text())
    source_facts = [c['fact'] for t in s['targets'] for c in t['stage1_candidates']]
    rows = []
    values = []
    for f in source_facts:
        row = {k: deepcopy(f[k]) for k in ['fact_locator','stable_fact_id','doc_id','fact_id','accession','concept','context_ref','entity_identifier','entity_scheme','unit','unit_measures','unit_numerator','unit_denominator','dimensions','chunk_id']}
        row['temporal'] = {'kind': f['period_type'], **({'instant': f['instant']} if f['period_type']=='instant' else {'period_start':f['period_start'],'period_end':f['period_end']})}
        rows.append(row); values.append({'fact_locator':f['fact_locator'],'normalized_value':f['normalized_value']})
    for i in range(7839-len(rows)):
        f = fact(i); rows.append(f); values.append({'fact_locator':f['fact_locator'],'normalized_value':'10'})
    rows.sort(key=lambda f:f['stable_fact_id']); values.sort(key=lambda f:f['fact_locator'])
    index = {'index_schema_version':'frozen_xbrl_fact_index_v0.1','xbrl_artifact_fingerprint':FINGERPRINT,'expected_fact_count':7839,'facts':rows}
    return s,index,values


def cd02_request(case, reverse=False):
    """Synthetic inputs only; no expected scoring logic or evaluator dependency."""
    from pathlib import Path
    if case in ('larger_pass', 'both_pass'):
        r = request()
        t1 = target('OUT_V1', '11' if case == 'larger_pass' else '10')
        t2 = target('OUT_V2', '10')
        r['gold_bundle']['numeric_targets'] = [t1, t2]
        r['gold_bundle']['answer_groups'][0]['variants'] = [variant(t1, 'V1'), variant(t2, 'V2')]
    else:
        r = json.loads((Path(__file__).parent / 'd2_v2_cd02_fixture.json').read_text())['schema_valid_request_witness']
        if case == 'unequal_partials':
            replacements = {'A_a': '6', 'A_b': '4', 'B_a': '12'}
            for t in r['gold_bundle']['numeric_targets']:
                if t['target_id'] in replacements:
                    value = replacements[t['target_id']]
                    t.update(accepted_value=value, precision=exact(value))
            variants = r['gold_bundle']['answer_groups'][0]['variants']
            variants[0]['derived_specification']['allowed_formula_variants'][0]['canonical_formula'] = '(a + b)'
            variants[1]['derived_specification']['allowed_formula_variants'][0]['canonical_formula'] = '((a - b) + 1)'
        elif case == 'different_denominators':
            for t in r['gold_bundle']['numeric_targets']:
                if t['target_id'] == 'A_a': t.update(accepted_value='10', precision=exact('10'))
            spec = r['gold_bundle']['answer_groups'][0]['variants'][0]['derived_specification']
            spec['required_inputs'] = spec['required_inputs'][:1]
            spec['allowed_formula_variants'][0]['canonical_formula'] = 'a'
        elif case != 'canonical_diagnostics':
            raise ValueError(case)
    if reverse:
        r['gold_bundle']['answer_groups'][0]['variants'].reverse()
    return r


def cd02_selector_request():
    return {
        'selection_schema_version': 'variant_selection_v0.2',
        'approved_variants': [
            {'variant_id': 'V1', 'variant_family': 'F1', 'structurally_applicable': True},
            {'variant_id': 'V2', 'variant_family': 'F2', 'structurally_applicable': True},
        ],
        'explicit_variant_id': None,
        'explicit_family_id': None,
        'candidate_results': [
            {'variant_id': 'V1', 'complete_deterministic_pass': False},
            {'variant_id': 'V2', 'complete_deterministic_pass': True},
        ],
    }
