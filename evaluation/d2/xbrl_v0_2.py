"""Full XBRL universe validation and closed source-map adaptation; no discovery."""
from collections import Counter
from copy import deepcopy
from pathlib import Path
import hashlib
import os

from .validation_v0_2 import (FINGERPRINT, InputError, require, mismatch, validate,
    unique, plain, strict_loads, canonical_json_bytes, UNITS, exact_context, exact_json)

IDENTITY_FIELDS = ('fact_locator', 'stable_fact_id', 'doc_id', 'fact_id', 'accession',
    'concept', 'context_ref', 'entity_identifier', 'entity_scheme', 'unit',
    'unit_measures', 'unit_numerator', 'unit_denominator', 'dimensions', 'chunk_id')


def identity_from_fact(fact):
    row = {k: deepcopy(fact[k]) for k in IDENTITY_FIELDS}
    row['unit'] = row['unit'] or None
    row['temporal'] = {'kind': fact['period_type']}
    if fact['period_type'] == 'instant':
        row['temporal']['instant'] = fact['instant']
    else:
        row['temporal'].update(period_start=fact['period_start'], period_end=fact['period_end'])
    return row


def validate_index(index, values, chunks=None):
    require(isinstance(values, list), 'Numeric catalog must be an array')
    require(all(isinstance(v, dict) and set(v) == {'fact_locator', 'normalized_value'} and
                isinstance(v['fact_locator'], str) for v in values), 'Malformed numeric catalog row')
    if index is None:
        require(not values, 'Numeric catalog without identity index')
        return {}, {}
    if isinstance(index, dict) and index.get('xbrl_artifact_fingerprint') != FINGERPRINT:
        mismatch('XBRL fingerprint mismatch')
    validate('frozen_xbrl_fact_index_v0.1.schema.json', index)
    rows = index['facts']
    require(len(rows) == 7839, 'Incorrect fact count')
    facts = unique(rows, 'fact_locator')
    stable = unique(rows, 'stable_fact_id')
    require(list(stable) == sorted(stable), 'Unsorted fact identities')
    numeric = unique(values, 'fact_locator')
    require(numeric.keys() == facts.keys(), 'Numeric catalog must cover exact universe')
    contexts, filings, units = {}, {}, {}
    for f in rows:
        require(f['fact_locator'] == f['doc_id'] + '#' + f['fact_id'] and
                f['stable_fact_id'] == f['doc_id'] + '::' + f['fact_id'], 'Malformed fact identity')
        temporal = f['temporal']
        if temporal['kind'] == 'duration':
            require(temporal['period_start'] <= temporal['period_end'], 'Inverted duration')
        context = {k: f[k] for k in ('entity_identifier', 'entity_scheme', 'temporal', 'dimensions')}
        key = (f['doc_id'], f['context_ref'])
        require(contexts.setdefault(key, context) == context, 'Inconsistent context identity')
        filing = (f['accession'], f['entity_identifier'], f['entity_scheme'])
        require(filings.setdefault(f['doc_id'], filing) == filing, 'Inconsistent filing identity')
        if f['unit'] is not None:
            key = (f['doc_id'], f['unit'])
            definition = [f[k] for k in ('unit_measures', 'unit_numerator', 'unit_denominator')]
            require(units.setdefault(key, definition) == definition, 'Inconsistent unit identity')
        if chunks is not None and f['chunk_id'] is not None:
            c = chunks.get(f['chunk_id'])
            require(c is not None and c['accession'] == f['accession'], 'Invalid authoritative chunk linkage')
        n = numeric[f['fact_locator']]
        require(set(n) == {'fact_locator', 'normalized_value'}, 'Malformed numeric catalog row')
        if n['normalized_value'] is not None:
            plain(n['normalized_value'])
    return facts, {k: v['normalized_value'] for k, v in numeric.items()}


def validate_paths(paths, facts, values):
    unique(paths, 'path_id')
    unique(paths, 'candidate_id')
    for p in paths:
        f = p['fact_identity']; locator = f['fact_locator']
        require(locator in facts and facts[locator] == f, 'Approved fact not in authoritative universe')
        require(values[locator] is not None and plain(values[locator]) == plain(p['normalized_value']),
                'Approved value disagrees with numeric catalog')
        require(f['unit'] is not None, 'Approved numeric path has no unit')


def validate_normalized_map(mapping, facts, values):
    if mapping is None:
        return {}
    if isinstance(mapping, dict) and mapping.get('xbrl_artifact_fingerprint') != FINGERPRINT:
        mismatch('Map fingerprint mismatch')
    validate('normalized_xbrl_map_v0.2.schema.json', mapping)
    targets = unique(mapping['targets'], 'target_id')
    for t in targets.values():
        validate_paths(t['direct_approved_paths'], facts, values)
        inputs = t['required_input_target_ids']
        require(all(k in targets and targets[k]['question_id'] == t['question_id'] for k in inputs),
                'Unresolved/cross-question map dependency')
        require(set(t['approved_upstream_path_target_ids']) <= set(inputs), 'Unknown approved upstream input')
        if t['source_state'] == 'mapped':
            require(t['state'] == 'DIRECT_APPROVED' and bool(t['direct_approved_paths']) and not inputs,
                    'Inconsistent direct map state')
        elif t['source_state'] != 'derived_via_inputs':
            require(t['state'] == 'NO_APPROVED_XBRL_PATH' and not inputs and not t['direct_approved_paths'],
                    'Inconsistent nonmapped state')
    resolved = {}
    active = set()
    def approved(k):
        require(k not in active, 'Cyclic map lineage')
        if k in resolved:
            return resolved[k]
        active.add(k); t = targets[k]
        children = [approved(i) for i in t['required_input_target_ids']]
        yes = t['state'] == 'DIRECT_APPROVED' or bool(children) and all(children)
        if t['source_state'] == 'derived_via_inputs':
            require(t['state'] == ('DERIVED_VIA_APPROVED_INPUTS' if yes else 'NO_APPROVED_XBRL_PATH'),
                    'Derived state disagrees with recursive leaves')
            require(t['approved_upstream_path_target_ids'] == (t['required_input_target_ids'] if yes else []),
                    'Derived approved lineage disagreement')
        active.remove(k); resolved[k] = yes
        return yes
    for k in targets:
        approved(k)
    return targets


def adapt_dev_xbrl_map_v0_2(source, *, source_sha256, fact_index, numeric_values):
    try:
        exact_json(source)
        # Shape validation precedes any filtering or projection, including malformed unapproved rows.
        validate('dev_xbrl_source_map_v0.2.schema.json', source)
        require(isinstance(source_sha256, str) and len(source_sha256) == 64 and
                all(c in '0123456789abcdef' for c in source_sha256), 'Invalid source SHA')
        if hashlib.sha256(canonical_json_bytes(source)).hexdigest() != source_sha256:
            mismatch('Canonical source-object SHA mismatch')
        facts, values = validate_index(fact_index, numeric_values)
        targets = unique(source['targets'], 'target_id')
        counts = Counter(t['final_mapping_status'] for t in targets.values())
        require(all(source['final_status_counts'][k] == counts[k] for k in source['final_status_counts']),
                'Final status counts disagree')
        seen_candidates = set(); paths = {}
        for tid, t in targets.items():
            candidates = t['stage1_candidates'] + t['stage2_candidates'] + t['stage3_candidates']
            by_id = unique(candidates, 'candidate_id')
            require(not seen_candidates.intersection(by_id), 'Duplicate candidate ID')
            seen_candidates.update(by_id)
            for field, status, count_key in [('approved_candidate_ids', 'APPROVE', 'approved'),
                    ('rejected_candidate_ids', 'REJECT', 'rejected'),
                    ('unresolved_candidate_ids', 'NEEDS_SOURCE_CHECK', 'unresolved')]:
                ids = [c['candidate_id'] for c in candidates if c['human_review_status'] == status]
                require(set(ids) == set(t[field]) and len(ids) == len(t[field]), 'Invalid review partition')
                if 'candidate_review_counts' in t:
                    require(t['candidate_review_counts'][count_key] == len(ids), 'Invalid review count')
            require(all(i in targets and targets[i]['question_id'] == t['question_id'] for i in t['required_input_ids']),
                    'Unresolved input target')
            paths[tid] = []
            for c in candidates:
                require(c['target_id'] == tid and c['fact_locator'] == c['fact']['fact_locator'], 'Candidate owner/locator disagreement')
                f = identity_from_fact(c['fact']); loc = f['fact_locator']
                require(loc in facts and facts[loc] == f, 'Source fact differs from authoritative identity')
                require(values[loc] is not None and plain(values[loc]) == plain(c['fact']['normalized_value']),
                        'Source fact value mismatch')
                if c['human_review_status'] == 'APPROVE':
                    require(c['fact']['chunk_id'] in t['approved_chunk_ids'], 'Stage-1 anchor absent')
                    require(c['fact']['accession'] in t['source_accessions'], 'Source accession outside target scope')
                    require(t['temporal_resolution']['resolved_temporal'] == f['temporal'], 'Candidate temporal mismatch')
                    require(c['source_check_status'] == 'SOURCE_CHECK_PASS' and c['temporal_consistency_status'] == 'PASS_EXACT_BOUND_TEMPORAL',
                            'Approved candidate lacks source/temporal check')
                    require(c['proposed_sign_relationship'] == 'same_sign', 'Missing schema-bound opposite-sign approval')
                    require(t['gold_xbrl_concept'] is None or t['gold_xbrl_concept'] == f['concept'], 'Target concept mismatch')
                    # Check the signed comparison coordinate against the frozen
                    # raw-unit definitions. Neither the review label nor a copied
                    # comparison value authenticates these semantic quantities.
                    raw_units = {('iso4217:USD',): 'USD', ('xbrli:shares',): 'shares', ('xbrli:pure',): 'pure'}
                    raw_label = raw_units.get(tuple(f['unit_measures']))
                    if f['unit_numerator'] == ['iso4217:USD'] and f['unit_denominator'] == ['xbrli:shares']:
                        raw_label = 'USD_per_share'
                    gu = t['gold_unit']
                    if raw_label is None and gu == f['unit']:
                        factor = '1'
                    else:
                        require(raw_label is not None and gu in UNITS and UNITS[gu][0] == raw_label,
                                'Source unit comparison is not registered')
                        factor = UNITS[gu][1]
                    with exact_context(t['gold_value'], values[loc], factor):
                        gold_value = plain(t['gold_value']) * plain(factor)
                        require(gold_value == plain(c['gold_comparison_value']) and
                                plain(values[loc]) == plain(c['candidate_comparison_value']), 'Source comparison coordinate disagreement')
                    paths[tid].append(dict(path_id=c['candidate_id'], candidate_id=c['candidate_id'],
                        fact_identity=f, normalized_value=c['fact']['normalized_value'], review_status='APPROVE',
                        sign_relationship='same_sign', sign_approval=None))
            state = t['final_mapping_status']; lineage = t['provenance_lineage']
            if state == 'derived_via_inputs':
                require(t['required_input_ids'] == lineage['required_input_ids'] and
                        t['derived_input_lineage'] == lineage['input_lineage'] and
                        [x['input_target_id'] for x in t['derived_input_lineage']] == t['required_input_ids'],
                        'Derived lineage copies disagree')
                for item in t['derived_input_lineage']:
                    upstream = targets[item['input_target_id']]
                    require(item['legacy_chunk_ids'] == [p['chunk_id'] for p in upstream['legacy_source_paths']] and
                            item['legacy_provenance_ids'] == [p['reference_id'] for p in upstream['legacy_source_paths']],
                            'Repeated upstream provenance disagrees')
            else:
                require(lineage['legacy_source_paths'] == t['legacy_source_paths'], 'Legacy lineage copies disagree')
                require(lineage['approved_xbrl_fact_locators'] == [p['fact_identity']['fact_locator'] for p in paths[tid]],
                        'Approved lineage copy mismatch')
                tr = t['temporal_resolution']
                require(lineage['selected_temporal_candidate_id'] == tr['selected_temporal_candidate_id'], 'Temporal IDs disagree')
                selected = lineage['selected_temporal_candidate']
                if tr['status'] == 'RESOLVED_HUMAN_CLOSED_SET':
                    require(tr['selected_temporal_candidate_id'] in tr['closed_candidate_ids'] and selected is not None and
                            selected['temporal_candidate_id'] == tr['selected_temporal_candidate_id'] and
                            selected['temporal'] == tr['resolved_temporal'], 'Invalid closed temporal selection')
                if state in ('mapped', 'no_xbrl_counterpart_in_frozen_corpus'):
                    require(tr['status'].startswith('RESOLVED_') and tr['resolved_temporal'] is not None, 'Missing exact temporal resolution')
                if state == 'mapped':
                    require(bool(paths[tid]), 'Mapped target has no approved paths')
                if state == 'no_xbrl_counterpart_in_frozen_corpus':
                    require(not paths[tid] and not t['unresolved_candidate_ids'] and t['stage_completion']['stage3'] == 'completed',
                            'Incomplete no-counterpart search')
        active = set(); ready = {}
        def resolve(tid):
            require(tid not in active, 'Cyclic source dependencies')
            if tid in ready:
                return ready[tid]
            active.add(tid); t = targets[tid]
            children = [resolve(k) for k in t['required_input_ids']]
            ready[tid] = bool(paths[tid]) or bool(children) and all(children)
            active.remove(tid)
            return ready[tid]
        normalized = []
        for tid, t in targets.items():
            yes = resolve(tid)
            state = 'DIRECT_APPROVED' if paths[tid] else 'DERIVED_VIA_APPROVED_INPUTS' if yes else 'NO_APPROVED_XBRL_PATH'
            normalized.append(dict(target_id=tid, question_id=t['question_id'], state=state,
                source_state=t['final_mapping_status'], direct_approved_paths=paths[tid],
                required_input_target_ids=deepcopy(t['required_input_ids']),
                approved_upstream_path_target_ids=deepcopy(t['required_input_ids']) if yes else []))
        result = dict(normalized_map_schema_version='normalized_xbrl_map_v0.2', adapter_version='dev_xbrl_map_adapter_v0.2',
            source_schema_version=source['schema_version'], source_sha256=source_sha256,
            xbrl_artifact_fingerprint=FINGERPRINT, targets=normalized)
        validate_normalized_map(result, facts, values)
        return {'evaluator_status': 'EVAL_OK', 'normalized_map': result, 'errors': []}
    except InputError as error:
        return {'evaluator_status': error.status, 'normalized_map': None,
                'errors': [{'code': error.code, 'path': error.path, 'message': str(error)}]}


def load_frozen_xbrl_v0_2(*, data_root):
    """Authenticate bytes before invoking the frozen tool; no model dependency."""
    from scripts.frozen_bundle import data_entries, verify_files
    from src.tools.xbrl_tool import XBRLTool
    from src.tools.retrieval_tool import RetrievalTool
    root = Path(data_root)
    require(root.is_absolute() and root.resolve() == root, 'Explicit absolute nonsymlink data root required')
    manifest_path = Path(__file__).resolve().parents[2] / 'packaging/frozen_runtime_bundle_v0.1.json'
    raw = manifest_path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == 'e5db9ce8b1bebbd2f52ddc7f7b1bd073346506c1ac2dc48b1949a75f4b0835a9',
            'Frozen bundle manifest hash mismatch')
    entries = data_entries(strict_loads(raw))
    for base, dirs, files in os.walk(root, followlinks=False):
        require(all(not (Path(base) / n).is_symlink() for n in dirs + files), 'Symlink in data root')
    verify_files(root, entries, reject_unexpected=True)
    tool = XBRLTool.from_frozen_ingestion(data_root=root)
    require(tool.xbrl_artifact_fingerprint == FINGERPRINT and tool.fact_count == 7839, 'Frozen XBRL identity mismatch')
    # The frozen public query API caps results; the immutable in-memory universe
    # supplies the full identity index, including the 640 unlinked facts.
    records = [f.to_dict() for f in tool._facts]
    index = dict(index_schema_version='frozen_xbrl_fact_index_v0.1', xbrl_artifact_fingerprint=FINGERPRINT,
                 expected_fact_count=7839, facts=[identity_from_fact(f) for f in records])
    values = [dict(fact_locator=f['fact_locator'], normalized_value=f['normalized_value']) for f in records]
    chunks = []
    for entry in entries:
        if entry['role'] != 'CHUNK_ARTIFACT':
            continue
        document = strict_loads((root / entry['path']).read_bytes())
        for c in document['chunks']:
            require(c['doc_id'] == document['doc_id'] and c['accession'] == document['accession'],
                    'Chunk/document identity mismatch')
            chunks.append(dict(chunk_id=c['chunk_id'], accession=c['accession'],
                locator=RetrievalTool._locator(c), source_allowed=True))
    chunks.sort(key=lambda c: c['chunk_id'])
    validate_index(index, values, unique(chunks, 'chunk_id'))
    return {'fact_index': index, 'numeric_values': values, 'chunk_catalog': chunks}
