"""Permitted static authoring checks. Never imports/collects/runs evaluator tests."""
import ast
import hashlib
import json
from pathlib import Path
import runpy
import subprocess

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT=Path(__file__).resolve().parents[2]
D2=ROOT/'evaluation/d2'


def main():
    authentication=json.loads((D2/'historical_source_authentication_v0.2.json').read_text())
    for entry in authentication['imported']:
        assert hashlib.sha256((ROOT/entry['import_path']).read_bytes()).hexdigest()==entry['historical_sha256']
    forbidden=set((ROOT/'packaging/d2_v2_authenticated_forbidden_paths.txt').read_text().splitlines())|{'benchmark/frozen','benchmark/dev/v0.1/review'}
    declared=set((ROOT/'packaging/d2_forbidden_paths_v0.1.txt').read_text().splitlines())
    assert declared <= forbidden
    assert not [p for p in forbidden if (ROOT/p).exists() or (ROOT/p).is_symlink()]
    files=subprocess.check_output(['rg','--files','--hidden','-g','!.git'],cwd=ROOT,text=True).splitlines()
    assert not [p for p in files if any(p==f or p.startswith(f+'/') for f in forbidden)]
    suite=ROOT/'tests/evaluation/test_deterministic_evaluator_contract_v0_2.py'
    fixture=ROOT/'tests/evaluation/d2_v2_contract_fixtures.py'
    for p in (suite,fixture,Path(__file__)):
        compile(p.read_text(),str(p),'exec')
    tree=ast.parse(suite.read_text());counts=[]
    for node in tree.body:
        if isinstance(node,(ast.Import,ast.ImportFrom)):
            names=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module or '']
            assert not any('deterministic_evaluator' in name for name in names)
        if not isinstance(node,ast.FunctionDef) or not node.name.startswith('test_'):continue
        count=1;parameterized=False
        for deco in node.decorator_list:
            if isinstance(deco,ast.Call) and isinstance(deco.func,ast.Attribute) and deco.func.attr=='parametrize':
                assert isinstance(deco.args[1],ast.List)
                names=ast.literal_eval(deco.args[0]).split(',');case_nodes=deco.args[1].elts
                if len(names)>1:assert all(isinstance(c,(ast.Tuple,ast.List)) and len(c.elts)==len(names) for c in case_nodes)
                count*=len(case_nodes);parameterized=True
        counts.append({'function':node.name,'cases':count,'parameterized':parameterized})
    schema_paths=sorted(D2.glob('*.schema.json'))+[D2/'deterministic_evaluator_output_schema_v0.1.json',D2/'deterministic_evaluator_output_schema_v0.2.json']
    schemas={p.name:json.loads(p.read_text()) for p in schema_paths}
    for schema in schemas.values():Draft202012Validator.check_schema(schema)
    registry=Registry().with_resources((s['$id'],Resource.from_contents(s)) for s in schemas.values())
    def check_refs(value,current):
        if isinstance(value,dict):
            if '$ref' in value:
                registry.resolver(base_uri=current['$id']).lookup(value['$ref'])
                name,_,pointer=value['$ref'].partition('#')
                target=schemas[name] if name else current
                if pointer:
                    assert pointer.startswith('/')
                    for part in pointer[1:].split('/'):
                        target=target[part.replace('~1','/').replace('~0','~')]
            for child in value.values():check_refs(child,current)
        elif isinstance(value,list):
            for child in value:check_refs(child,current)
    for schema in schemas.values():check_refs(schema,schema)
    def validate(name,value):
        Draft202012Validator(schemas[name],registry=registry,format_checker=FormatChecker()).validate(value)
    # Execute only our input fixture builders for structural validation.
    # This file never imports the test module or evaluator.
    fixtures=runpy.run_path(str(fixture))
    agent_schema=json.loads((ROOT/'evaluation/agent_output_schema_v0.1.1.json').read_text())
    for name in ['request','derived_request','two_input_request','xbrl_request']:
        r=fixtures[name]();validate('evaluation_request_v0.2.schema.json',r)
        a=fixtures['get_output'](r)
        Draft202012Validator(agent_schema,format_checker=FormatChecker()).validate(a)
    for case in ['larger_pass','both_pass','unequal_partials','canonical_diagnostics','different_denominators']:
        for reverse in [False,True]:
            r=fixtures['cd02_request'](case,reverse)
            validate('evaluation_request_v0.2.schema.json',r)
            Draft202012Validator(agent_schema,format_checker=FormatChecker()).validate(fixtures['get_output'](r))
    selector=schemas['variant_selection_v0.2.schema.json']
    Draft202012Validator({'$ref':selector['$id']+'#/$defs/request'},registry=registry).validate(fixtures['cd02_selector_request']())
    # Literal schema fixtures, never evaluator outputs or test executions.
    selection_literals=[
        {'selection_schema_version':'variant_selection_v0.2','eligible_variant_ids':['V1','V2'],'complete_passing_variant_ids':['V2'],'selected_variant_id':'V2','selection_mode':'COMPLETE_PASS','complete_deterministic_pass':True,'reason_codes':[]},
        {'selection_schema_version':'variant_selection_v0.2','eligible_variant_ids':['V1','V2'],'complete_passing_variant_ids':[],'selected_variant_id':'V1','selection_mode':'CANONICAL_DIAGNOSTIC','complete_deterministic_pass':False,'reason_codes':['NO_COMPLETE_VARIANT_PASS']},
        {'selection_schema_version':'variant_selection_v0.2','eligible_variant_ids':[],'complete_passing_variant_ids':[],'selected_variant_id':None,'selection_mode':'NO_ELIGIBLE_VARIANT','complete_deterministic_pass':False,'reason_codes':['NO_ELIGIBLE_VARIANT']},
    ]
    for literal in selection_literals:
        validate('variant_selection_v0.2.schema.json',literal)
        Draft202012Validator({'$ref':selector['$id']+'#/$defs/response'},registry=registry).validate({'evaluator_status':'EVAL_OK','selection':literal,'reason_codes':[]})
    Draft202012Validator({'$ref':selector['$id']+'#/$defs/response'},registry=registry).validate({'evaluator_status':'EVAL_INPUT_INVALID','selection':None,'reason_codes':['UNKNOWN_VARIANT_IDENTIFIER']})
    occurrence={'occurrence':1,'claim_id':'C001','variant_id':'V2','numeric_correct':True,'formula_correct':None,'arithmetic_correct':None,'approved_path_valid':True,'input_correctness':None,'unit_result':None,'precision_result':None,'sign_result':True,'basis_result':True,'variant_selection':selection_literals[0],'input_results':[],'reason_codes':[]}
    result_id=schemas['deterministic_evaluator_output_schema_v0.2.json']['$id']
    Draft202012Validator({'$ref':result_id+'#/properties/metrics/anyOf/0/properties/answer_group_results/items/properties/occurrences/items'},registry=registry).validate(occurrence)
    src,index,values=fixtures['source_map_fixture'](ROOT)
    validate('dev_xbrl_source_map_v0.2.schema.json',src)
    validate('frozen_xbrl_fact_index_v0.1.schema.json',index)
    assert len(values)==7839 and len({v['fact_locator'] for v in values})==7839
    # Positive source no-counterpart fixture structure, no adapter execution.
    t=next(t for t in src['targets'] if t['final_mapping_status']=='unmappable')
    t['final_mapping_status']='no_xbrl_counterpart_in_frozen_corpus';t['unmappable_reason_code']=None
    t['temporal_resolution'].update(status='RESOLVED_EXACT_TARGET_DATE',mode='EXACT_TARGET_DATE',resolution_rule_id='exact_target_date_v0.1',resolved_temporal={'kind':'instant','instant':'2024-03-31'})
    t['stage_completion']['stage3']='completed';src['final_status_counts']['unmappable']-=1;src['final_status_counts']['no_xbrl_counterpart_in_frozen_corpus']+=1
    validate('dev_xbrl_source_map_v0.2.schema.json',src)
    matrix=json.loads((D2/'d2_v2_preregistration_42_row_matrix.json').read_text())
    assert [row['row_id'] for row in matrix]==[f'D{i:02}' for i in range(1,43)]
    tests={c['function'] for c in counts}
    assert all(row['independent_tests'] and set(row['independent_tests'])<=tests for row in matrix)
    for row in matrix:
        for schema in row['machine_schema']:assert (D2/schema).is_file(),schema
    classifications={name:sum(r['classification']==name for r in matrix) for name in ['COVERED_DETERMINISTIC','PENDING_JUDGE','CONTRACT_DECISION_REQUIRED']}
    assert classifications=={'COVERED_DETERMINISTIC':39,'PENDING_JUDGE':3,'CONTRACT_DECISION_REQUIRED':0}
    witness=json.loads((ROOT/'tests/evaluation/d2_v2_cd02_fixture.json').read_text())['schema_valid_request_witness']
    validate('evaluation_request_v0.2.schema.json',witness)
    Draft202012Validator(agent_schema,format_checker=FormatChecker()).validate(fixtures['get_output'](witness))
    # Parse every new JSON artifact, including the decision fixture, without scoring it.
    for p in list(D2.glob('*.json'))+[ROOT/'tests/evaluation/d2_v2_cd02_fixture.json']:json.loads(p.read_text())
    sources=['evaluation/eval_protocol_v0.2.md','evaluation/eval_protocol_v0.2.1.md','evaluation/eval_protocol_v0.2.2.md','docs/agent/execution_taxonomy_v0.1.md','evaluation/agent_output_schema_v0.1.1.json','evaluation/xbrl_gold_mapping_spec_v0.1.md','evaluation/xbrl_gold_mapping_spec_v0.1.2.md','evaluation/xbrl_mapping_schema_v0.1.json','docs/tools/calculator_tool_v0.1.md','docs/tools/xbrl_tool_v0.1.md','packaging/frozen_runtime_bundle_v0.1.json','evaluation/dev/xbrl/dev_xbrl_map_v0.1.json']
    result={'status':'STATIC_VALIDATION_PASSED','historical_import_count':len(authentication['imported']),
            'historical_import_hashes_unchanged':True,'physical_absence_checks':'PASS','recursive_discovery_checks':'PASS',
            'schema_local_reference_resolution':'PASS','schema_self_validation_count':len(schemas),'successor_schema_count':sum('v0.2' in n or n=='frozen_xbrl_fact_index_v0.1.schema.json' for n in schemas),
            'cd02_request_structures_checked':10,'cd02_selector_input_structure':'PASS','cd02_selection_response_and_occurrence_structures':'PASS',
            'fixture_structural_checks':'PASS','test_file_compilation':'PASS_WITHOUT_IMPORT',
            'test_functions':len(counts),'parameterized_functions':sum(c['parameterized'] for c in counts),
            'parameterized_cases':sum(c['cases'] for c in counts if c['parameterized']),'total_cases':sum(c['cases'] for c in counts),
            'test_cases_executed':0,'test_collection_performed':False,'evaluator_imported':False,
            'matrix_counts':classifications,'test_counts':counts,
            'permitted_source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources}}
    (D2/'d2_v2_static_validation.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ['test_counts','permitted_source_sha256']},indent=2))


if __name__=='__main__':main()
