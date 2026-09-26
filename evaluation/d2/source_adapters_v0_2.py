"""Explicit byte-authenticated input adapters, separate from slot scoring."""
from collections import defaultdict
from copy import deepcopy
import csv
import hashlib
import io
import re

from .validation_v0_2 import (InputError, require, mismatch, validate, unique, plain,
    strict_loads, canonical_json_bytes, adapt_precision_v0_2, precision_interval, validate_precision)
from .xbrl_v0_2 import validate_index, validate_normalized_map

CSV_COLUMNS = {
    'questions.csv': 'q_id,version,split,company,fiscal_period,calendar_period,q_type,question,source_scope,depends_on,status',
    'numeric_answers.csv': 'fact_id,q_id,role,answer_group,variant_group,accepted_value,unit,display_precision,tolerance,period,basis,xbrl_tag,accession,direct_or_derived,formula,required_input_facts,supporting_chunk_ids,anchor_logic,locator,notes,variant_family,question_consistency_group',
    'evidence_checklist.csv': 'q_id,item_id,part_id,item_claim,part_claim,importance,weight,stance,temporal_role,evidence_period,within_item_logic,anchor_logic,supporting_chunk_ids,accessions,locator,notes,status',
    'provenance.csv': 'provenance_id,target_type,q_id,fact_id,item_id,part_id,reference_id,reference_kind,references_operator,members_operator,member_index,via_input_fact_id,chunk_id,accession,doc_id,company,form,fiscal_period,calendar_period,locator,source_role,source_contract_status,source_check_status,audit_note,status',
}


def authenticated_bytes(path, expected_sha256):
    """Caller supplies the exact permitted source path and frozen byte hash."""
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        mismatch('Source byte SHA mismatch')
    return raw


def _csv(raw, name):
    require(isinstance(raw, bytes), 'CSV adapter requires original bytes')
    try:
        reader = csv.DictReader(io.StringIO(raw.decode('utf-8'), newline=''), strict=True)
        require(reader.fieldnames == CSV_COLUMNS[name].split(','), 'Unsupported CSV header: ' + name)
        rows = list(reader)
        require(all(None not in row and all(v is not None for v in row.values()) for row in rows), 'Ragged CSV row')
        return rows
    except (UnicodeError, csv.Error) as error:
        raise InputError('Invalid CSV: ' + name) from error


def _list(value):
    if value == '':
        return []
    result = value.split(';')
    require(all(result) and len(set(result)) == len(result), 'Malformed/duplicate semicolon list')
    return result


def adapt_dev_gold_bundle_v0_2(files, *, declared_source_format, source_hashes,
                               chunk_catalog, normalized_map, fact_index, numeric_values):
    """Adapt the documented CSV set into question-scoped normalized bundles.

    `files` maps the four declared CSV names to bytes. `source_hashes` binds each
    source to a caller's frozen manifest; no path/split/content format guessing.
    Narrative annotation locator prose is retained in the authenticated original;
    canonical chunk identity comes from the independently authenticated catalog.
    """
    try:
        require(declared_source_format == 'dev_gold_csv_bundle_v0.1', 'Unsupported declared source format')
        require(set(files) == set(CSV_COLUMNS) == set(source_hashes), 'CSV source set mismatch')
        for name, raw in files.items():
            require(isinstance(raw, bytes), 'Expected source bytes')
            if hashlib.sha256(raw).hexdigest() != source_hashes[name]:
                mismatch('CSV source hash mismatch: ' + name)
        parsed = {k: _csv(v, k) for k, v in files.items()}
        questions = unique(parsed['questions.csv'], 'q_id')
        numeric = unique(parsed['numeric_answers.csv'], 'fact_id')
        unique(parsed['provenance.csv'], 'provenance_id')
        chunks = unique(chunk_catalog, 'chunk_id')
        facts, values = validate_index(fact_index, numeric_values, chunks)
        mapping = validate_normalized_map(normalized_map, facts, values)
        paths = defaultdict(lambda: defaultdict(list)); lineage = defaultdict(list)
        parts = {}; evidence = defaultdict(list)
        for row in parsed['evidence_checklist.csv']:
            require(row['q_id'] in questions and row['status'] in ('ACTIVE', 'RETIRED'), 'Invalid evidence scope/status')
            key = (row['q_id'], row['item_id'], row['part_id'])
            require(key not in parts, 'Duplicate evidence part')
            parts[key] = row
            require(row['within_item_logic'] == 'AND' and row['anchor_logic'] in ('OR', 'AND'), 'Unsupported evidence logic')
            require(row['importance'] in ('core', 'supporting', 'optional'), 'Unknown importance')
            require(plain(row['weight']) == plain({'core': '3.0', 'supporting': '1.5', 'optional': '0.5'}[row['importance']]),
                    'Evidence weight disagreement')
            if row['status'] == 'ACTIVE':
                evidence[row['q_id']].append(dict(item_id=row['item_id'], part_id=row['part_id'],
                    required_semantics=row['part_claim'], importance=row['importance'], stance=row['stance'] or None,
                    temporal_role=row['temporal_role']))
        for row in parsed['provenance.csv']:
            require(row['q_id'] in questions and row['status'] in ('ACTIVE', 'RETIRED'), 'Invalid provenance scope/status')
            require(row['target_type'] in ('numeric_fact', 'evidence_part'), 'Unknown target type')
            key = row['fact_id'] if row['target_type'] == 'numeric_fact' else (row['q_id'], row['item_id'], row['part_id'])
            if row['target_type'] == 'numeric_fact':
                require(key in numeric and numeric[key]['q_id'] == row['q_id'], 'Unknown numeric provenance target')
            else:
                require(key in parts and parts[key]['status'] == row['status'], 'Unknown/inconsistent evidence provenance target')
            require(row['reference_kind'] in ('direct_candidate', 'candidate_source_bundle', 'derived_input_union'), 'Unknown reference kind')
            require(row['source_contract_status'] == 'allowed' and row['source_check_status'] == 'SOURCE_CHECK_PASS', 'Unapproved source')
            c = chunks.get(row['chunk_id'])
            require(c is not None and c['accession'] == row['accession'], 'Source chunk/accession mismatch')
            require(re.fullmatch('[1-9][0-9]*', row['member_index']), 'Invalid reference member index')
            if row['reference_kind'] == 'derived_input_union':
                require(row['target_type'] == 'numeric_fact' and row['references_operator'] == 'NOT_APPLICABLE' and
                        row['members_operator'] == 'AND' and row['via_input_fact_id'] in numeric, 'Invalid derived lineage')
                lineage[key].append(row['via_input_fact_id'])
            else:
                require(row['references_operator'] == 'OR' and row['members_operator'] ==
                        ('ATOM' if row['reference_kind'] == 'direct_candidate' else 'AND'), 'Invalid provenance Boolean structure')
                if row['status'] == 'ACTIVE':
                    paths[key][row['reference_id']].append(row)
        normalized_targets = {}; specs = {}
        for tid, row in numeric.items():
            require(row['q_id'] in questions and row['role'] in ('input', 'answer'), 'Invalid numeric scope/role')
            require(row['direct_or_derived'] in ('direct', 'derived'), 'Unknown numeric representation')
            plain(row['accepted_value'])
            metadata = {}
            if row['tolerance'] != '':
                metadata['tolerance'] = row['tolerance']
            if row['display_precision'] != '':
                require(re.fullmatch('[0-9]+', row['display_precision']), 'Invalid display precision')
                metadata['display_precision'] = int(row['display_precision'])
            precision = adapt_precision_v0_2(metadata, reference_value=row['accepted_value'], unit=row['unit'])
            require(precision['evaluator_status'] == 'EVAL_OK', 'Invalid precision')
            chunk_paths = []
            for path_id, members in paths[tid].items():
                require([int(m['member_index']) for m in members] == list(range(1, len(members) + 1)), 'Noncontiguous reference members')
                chunk_paths.append(dict(path_id=path_id, members=[{k: chunks[m['chunk_id']][k] for k in
                    ('chunk_id', 'accession', 'locator')} for m in members]))
            mapped = mapping.get(tid)
            if mapped is not None:
                require(mapped['question_id'] == row['q_id'], 'Map question mismatch')
            target = dict(target_id=tid, accepted_value=row['accepted_value'], unit=row['unit'], period=row['period'],
                basis=row['basis'], precision=precision['precision'], variant_family=row['variant_family'] or None,
                approved_chunk_paths=chunk_paths, approved_xbrl_paths=deepcopy(mapped['direct_approved_paths']) if mapped else [])
            normalized_targets[tid] = target
            inputs = _list(row['required_input_facts'])
            require(all(i in numeric and numeric[i]['q_id'] == row['q_id'] for i in inputs), 'Unknown/cross-question input')
            if row['direct_or_derived'] == 'direct':
                require(not inputs and not row['formula'] and not lineage[tid], 'Direct target carries derived lineage')
                specs[tid] = None
            else:
                require(inputs and row['formula'] and not chunk_paths and set(lineage[tid]) == set(inputs), 'Derived lineage mismatch')
                specs[tid] = dict(derived_target_id=tid,
                    required_inputs=[dict(input_role=i, source_target_id=i, source_answer_group_id=None) for i in inputs],
                    allowed_formula_variants=[dict(formula_variant_id=tid + '.formula.v1', canonical_formula=row['formula'])],
                    output_unit=row['unit'], output_precision=deepcopy(target['precision']))
        source_digest = hashlib.sha256(canonical_json_bytes(source_hashes)).hexdigest()
        bundles = []
        for qid in questions:
            groups = {}
            for tid, row in numeric.items():
                if row['q_id'] != qid or row['role'] != 'answer':
                    continue
                require(row['answer_group'] and row['variant_group'], 'Missing answer identity')
                g = groups.setdefault(row['answer_group'], dict(answer_group_id=row['answer_group'], multiplicity=1,
                    question_consistency_group=row['question_consistency_group'] or None, variants=[]))
                require(g['question_consistency_group'] == (row['question_consistency_group'] or None), 'Group consistency metadata mismatch')
                v = deepcopy(normalized_targets[tid]); v['numeric_target_id'] = v.pop('target_id')
                v.update(variant_id=row['variant_group'], sign_policy='REGISTERED_VARIANT', derived_specification=specs[tid])
                g['variants'].append(v)
            bundle = dict(bundle_schema_version='gold_bundle_v0.2', adapter_version='gold_bundle_adapter_v0.2',
                source_format_version=declared_source_format, source_sha256=source_digest, question_id=qid,
                numeric_targets=[t for tid, t in normalized_targets.items() if numeric[tid]['q_id'] == qid],
                answer_groups=list(groups.values()), judge_dependent_gold={'items': evidence[qid]})
            validate('gold_bundle_v0.2.schema.json', bundle)
            from .deterministic_evaluator import _validate_gold
            _validate_gold(bundle, facts, values, chunks, mapping)
            bundles.append(bundle)
        return {'evaluator_status': 'EVAL_OK', 'gold_bundles': bundles, 'errors': []}
    except InputError as error:
        return {'evaluator_status': error.status, 'gold_bundles': None,
                'errors': [dict(code=error.code, path=error.path, message=str(error))]}


def adapt_gold_bundle_v0_2(raw, *, declared_source_format, source_sha256,
                          chunk_catalog, normalized_map, fact_index, numeric_values):
    """Strict normalized v0.1/v0.2 dispatch with authoritative path enrichment."""
    try:
        require(declared_source_format in ('gold_bundle_v0.1', 'gold_bundle_v0.2'), 'Unsupported declared source format')
        require(isinstance(raw, bytes), 'Expected original JSON bytes')
        if hashlib.sha256(raw).hexdigest() != source_sha256:
            mismatch('Gold source hash mismatch')
        gold = strict_loads(raw)
        validate(declared_source_format + '.schema.json', gold)
        facts, values = validate_index(fact_index, numeric_values, unique(chunk_catalog, 'chunk_id'))
        mapping = validate_normalized_map(normalized_map, facts, values)
        if declared_source_format == 'gold_bundle_v0.1':
            gold.update(bundle_schema_version='gold_bundle_v0.2', adapter_version='gold_bundle_adapter_v0.2',
                        source_sha256=source_sha256)
            def upgrade(record, tid):
                p = record['precision']; p.update(precision_schema_version='precision_record_v0.2',
                    reference_value=record['accepted_value'], comparison_unit=record['unit'], precision_rule_id={
                    'EXACT': 'precision_exact_v0.1', 'QUANTUM': 'precision_rounding_quantum_v0.1',
                    'ABS_TOLERANCE': 'precision_absolute_tolerance_v0.1'}[p['mode']])
                p['interval'] = precision_interval(p)
                paths = []
                for old in record['approved_xbrl_paths']:
                    approved = mapping.get(tid, {}).get('direct_approved_paths', [])
                    match = [p for p in approved if p['path_id'] == old['path_id'] and all(p['fact_identity'][k] == old[k]
                        for k in ('fact_locator', 'accession', 'concept', 'context_ref', 'unit', 'temporal'))]
                    require(len(match) == 1, 'Legacy XBRL path lacks exact approved identity')
                    paths.append(deepcopy(match[0]))
                record['approved_xbrl_paths'] = paths
            for t in gold['numeric_targets']:
                upgrade(t, t['target_id'])
            for g in gold['answer_groups']:
                for v in g['variants']:
                    upgrade(v, v['numeric_target_id'])
                    spec = v['derived_specification']
                    if spec is not None:
                        record = dict(accepted_value=v['accepted_value'], unit=spec['output_unit'],
                                      precision=spec['output_precision'], approved_xbrl_paths=[])
                        upgrade(record, v['numeric_target_id'])
            # v0.1's open judge object is accepted only if it already supplies
            # the successor's closed semantics; missing meaning is never invented.
        validate('gold_bundle_v0.2.schema.json', gold)
        from .deterministic_evaluator import _validate_gold
        _validate_gold(gold, facts, values, unique(chunk_catalog, 'chunk_id'), mapping)
        return {'evaluator_status': 'EVAL_OK', 'gold_bundle': gold, 'errors': []}
    except InputError as error:
        return {'evaluator_status': error.status, 'gold_bundle': None,
                'errors': [dict(code=error.code, path=error.path, message=str(error))]}
