"""D2 v2 deterministic evaluator. Explicit catalogs in; canonical results out.

This module performs no project-data reads, retrieval, model inference, judging,
or orchestration. Use the authenticated loader for production catalogs.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from decimal import Decimal
import hashlib

from .validation_v0_2 import (
    InputError, require, mismatch, strict_loads, canonical_decimal, canonical_json_bytes,
    result_sha256, validate, schemas, unique, validate_precision, numeric_match,
    formula_tree, audit_arithmetic_v0_2, adapt_precision_v0_2, select_variant_v0_2,
    FAILURES, INFRA, STATUSES, EVENTS, calculator, exact_json,
)
from .xbrl_v0_2 import (validate_index, validate_paths, validate_normalized_map,
                        adapt_dev_xbrl_map_v0_2, load_frozen_xbrl_v0_2)
from .source_adapters_v0_2 import adapt_dev_gold_bundle_v0_2, adapt_gold_bundle_v0_2


def ratio(numerator, denominator):
    return {'numerator': numerator, 'denominator': denominator} if denominator else None


def conjunction(values):
    values = [v for v in values if v is not None]
    return all(values) if values else None


def _base_result():
    return dict(result_schema_version='deterministic_evaluator_result_v0.2',
        evaluator_version='deterministic_evaluator_v0.2', question_id=None,
        scheduled_slot_id=None, effective_attempt_id=None, execution_status=None,
        evaluator_status='EVAL_OK', evaluation_completion=None, agent_output_contract_valid=None,
        calculation_graph=None, assignment=None, included_in_scored_denominator=False,
        checkpoint_valid=False, metrics=None, reason_codes=[], errors=[])


def _recognize(request):
    exact_json(request)
    require(isinstance(request, dict), 'Request must be an object')
    expected = schemas()[0]['evaluation_request_v0.2.schema.json']['properties']['contract_identity']['properties']
    identity = request.get('contract_identity')
    require(isinstance(identity, dict), 'Missing contract identity')
    for k, definition in expected.items():
        if k in identity:
            require(isinstance(identity[k], str), 'Contract identity must be a string: ' + k)
        if k in identity and identity[k] != definition['const']:
            mismatch('Unknown contract identity: ' + k)
    versions = [('request_schema_version', request, 'evaluation_request_v0.2'),
        ('bundle_schema_version', request.get('gold_bundle'), 'gold_bundle_v0.2'),
        ('adapter_version', request.get('gold_bundle'), 'gold_bundle_adapter_v0.2'),
        ('slot_record_schema_version', request.get('slot_record'), 'evaluation_slot_record_v0.2'),
        ('adapter_version', request.get('slot_record'), 'evaluation_slot_record_adapter_v0.2'),
        ('normalized_map_schema_version', request.get('normalized_xbrl_map'), 'normalized_xbrl_map_v0.2'),
        ('adapter_version', request.get('normalized_xbrl_map'), 'dev_xbrl_map_adapter_v0.2'),
        ('index_schema_version', request.get('frozen_xbrl_fact_index'), 'frozen_xbrl_fact_index_v0.1')]
    for key, obj, version in versions:
        if isinstance(obj, dict) and key in obj:
            require(isinstance(obj[key], str), 'Version must be a string: ' + key)
            if obj[key] != version:
                mismatch('Unsupported version: ' + key)
    slot = request.get('slot_record')
    if isinstance(slot, dict):
        for obj in [slot] + (slot.get('attempts') if isinstance(slot.get('attempts'), list) else []):
            if isinstance(obj, dict) and 'execution_status' in obj:
                require(isinstance(obj['execution_status'], str), 'Status must be a string')
                if obj['execution_status'] not in STATUSES:
                    mismatch('Unknown execution status')
        if isinstance(slot.get('events'), list):
            require(all(isinstance(e, str) for e in slot['events']), 'Event IDs must be strings')
            if any(e not in EVENTS for e in slot['events']):
                mismatch('Unknown/inactive event')
    for key in ('frozen_xbrl_fact_index', 'normalized_xbrl_map'):
        obj = request.get(key)
        if isinstance(obj, dict) and 'xbrl_artifact_fingerprint' in obj and obj['xbrl_artifact_fingerprint'] != identity.get('xbrl_artifact_fingerprint'):
            mismatch('XBRL fingerprint disagreement')


def _validate_slot(request):
    slot = request['slot_record']; attempts = slot['attempts']
    unique(attempts, 'attempt_id')
    require(attempts[0]['replacement_for_attempt_id'] is None, 'Original attempt cannot replace another')
    last = attempts[-1]
    require(last['attempt_id'] == slot['effective_attempt_id'] and last['execution_status'] == slot['execution_status'],
            'Effective attempt disagreement')
    if len(attempts) == 2:
        require(attempts[0]['execution_status'] == INFRA and
                last['replacement_for_attempt_id'] == attempts[0]['attempt_id'] and
                slot['replacement_for_slot_id'] == slot['scheduled_slot_id'], 'Invalid replacement lineage')
    else:
        require(slot['replacement_for_slot_id'] is None, 'Unexpected replacement slot')
    status = slot['execution_status']
    require(slot['infrastructure_exhausted'] == (status == INFRA), 'Infrastructure flag disagreement')
    require(slot['agent_output_present'] == (status == 'RUN_COMPLETED'), 'Output presence flag disagreement')
    if status == INFRA:
        require(len(attempts) == 2, 'Pending replacement is not a finalized evaluation')
    if status != 'RUN_COMPLETED':
        require(request['agent_output_json'] is None and request['agent_output_sha256'] is None, 'Terminal slot has scoreable output')
        return None
    require(request['agent_output_json'] is not None and request['agent_output_sha256'] is not None, 'Completed slot lacks payload')
    if hashlib.sha256(request['agent_output_json'].encode('utf-8')).hexdigest() != request['agent_output_sha256']:
        mismatch('Raw output SHA mismatch')
    output = strict_loads(request['agent_output_json'])
    if isinstance(output, dict) and 'schema_version' in output and output['schema_version'] != 'agent_output_v0.1.1':
        mismatch('Unsupported agent output schema')
    validate('agent_output_schema_v0.1.1.json', output)
    require(output['q_id'] == slot['question_id'], 'Output question mismatch')
    claims = unique(output['claims'], 'claim_id')
    unique(output['calculations'], 'calculation_id')
    for c in output['calculations']:
        unique(c['inputs'], 'input_id')
    require(all(i in claims for i in output['answer_claim_ids']), 'Unresolved answer claim')
    return output


def _validate_gold(gold, facts, values, chunks, mapping):
    require(gold['source_format_version'] in ('gold_bundle_v0.2', 'gold_bundle_v0.1', 'dev_gold_csv_bundle_v0.1'),
            'Unsupported declared gold representation')
    targets = unique(gold['numeric_targets'], 'target_id')
    groups = unique(gold['answer_groups'], 'answer_group_id')
    dependencies = defaultdict(set)
    for t in targets.values():
        validate_precision(t['precision'], t['accepted_value'], t['unit'])
        validate_paths(t['approved_xbrl_paths'], facts, values)
        unique(t['approved_chunk_paths'], 'path_id')
        for path in t['approved_chunk_paths']:
            unique(path['members'], 'chunk_id')
            for c in path['members']:
                require(c['chunk_id'] in chunks and all(chunks[c['chunk_id']][k] == v for k, v in c.items()),
                        'Approved chunk identity absent or inconsistent')
        if t['approved_xbrl_paths']:
            mt = mapping.get(t['target_id'])
            require(mt is not None and mt['question_id'] == gold['question_id'] and
                    mt['direct_approved_paths'] == t['approved_xbrl_paths'], 'Gold approved paths disagree with target map')
    shared = ('accepted_value', 'unit', 'period', 'basis', 'precision', 'variant_family', 'approved_chunk_paths', 'approved_xbrl_paths')
    for group in groups.values():
        unique(group['variants'], 'variant_id')
        for variant in group['variants']:
            require(variant['numeric_target_id'] in targets, 'Unknown numeric target')
            target = targets[variant['numeric_target_id']]
            require(all(variant[k] == target[k] for k in shared), 'Variant and target semantics disagree')
            spec = variant['derived_specification']
            if spec is None:
                continue
            require(spec['derived_target_id'] == variant['numeric_target_id'], 'Derived target disagreement')
            require(spec['output_unit'] == variant['unit'], 'Derived output unit disagreement')
            validate_precision(spec['output_precision'], variant['accepted_value'], variant['unit'])
            roles = unique(spec['required_inputs'], 'input_role')
            unique(spec['allowed_formula_variants'], 'formula_variant_id')
            for i in roles.values():
                require(i['source_target_id'] in targets and (i['source_answer_group_id'] is None or
                        i['source_answer_group_id'] in groups), 'Unknown required input reference')
                if i['source_answer_group_id'] is not None:
                    require(any(v['numeric_target_id'] == i['source_target_id'] for v in
                                groups[i['source_answer_group_id']]['variants']), 'Input target/group disagreement')
                dependencies[variant['numeric_target_id']].add(i['source_target_id'])
            for f in spec['allowed_formula_variants']:
                try:
                    tree = calculator._ExpressionParser(f['canonical_formula']).parse()
                    require(set(calculator._used_names(tree)) == roles.keys(), 'Formula roles disagree with required inputs')
                except calculator.CalculatorToolError as error:
                    raise InputError('Malformed frozen formula') from error
    pending = {k: set(v) for k, v in dependencies.items()}
    while pending:
        leaves = {k for k, v in pending.items() if not v.intersection(pending)}
        require(bool(leaves), 'Cyclic gold target dependency')
        for k in leaves:
            del pending[k]
    return targets


def _graph(output):
    calculations = {c['calculation_id']: c for c in output['calculations']}
    pending = {k: {i['source_calculation_id'] for i in c['inputs'] if i['source_type'] == 'prior_calculation'}
               for k, c in calculations.items()}
    # Remove proven-valid leaves. Missing references and cycles remain, together
    # with every node transitively depending on them, without recursive traversal.
    good = set()
    while True:
        leaves = {k for k, edges in pending.items() if edges <= good}
        if not leaves:
            break
        good.update(leaves)
        for k in leaves:
            del pending[k]
    dependent = sorted(c['claim_id'] for c in output['claims'] if any(k not in good for k in c.get('calculation_ids', [])))
    valid = not pending and not dependent
    return dict(graph_schema_version='calculation_graph_validation_v0.2', valid=valid,
        invalid_calculation_ids=sorted(pending), dependent_claim_ids=dependent,
        reason_codes=[] if valid else ['INVALID_CALCULATION_REFERENCE_GRAPH'])


def _provenance(owner):
    if 'provenance' in owner:
        return owner['provenance']
    return [dict(provenance_type='chunk', **c) for c in owner.get('citations', [])]


class _Scorer:
    def __init__(self, request, output, facts, values, targets, graph):
        self.request, self.output, self.facts, self.values = request, output, facts, values
        self.targets, self.graph = targets, graph
        self.chunks = {c['chunk_id']: c for c in request['chunk_catalog']}
        self.calcs = {c['calculation_id']: c for c in output['calculations']}
        self.findings = {}; self.owners = {}; self.bindings = {}
        self.hallucinated = set()
        for claim in output['claims']:
            self._owner(('claim', claim['claim_id']), claim, claim['claim_type'] == 'numeric')
        for calc in output['calculations']:
            for item in calc['inputs']:
                self._owner(('calculation_input', calc['calculation_id'] + '/' + item['input_id']), item, True)

    def _owner(self, key, owner, numeric):
        self.owners[key] = owner
        found = []
        for index, p in enumerate(_provenance(owner)):
            reasons = []; fact_valid = eligible = None
            if p['provenance_type'] == 'chunk':
                c = self.chunks.get(p['chunk_id'])
                if c is None:
                    reasons.append('nonexistent_chunk_id')
                    self.hallucinated.add((key, index))
                else:
                    if c['accession'] != p['accession']:
                        reasons.append('wrong_accession')
                        self.hallucinated.add((key, index))
                    if c['locator'] != p['locator']:
                        reasons.append('metadata_inconsistent')
                    if not c['source_allowed']:
                        reasons.append('outside_source_contract')
                identity_valid = not reasons
            else:
                f = self.facts.get(p['fact_locator'])
                if f is None:
                    reasons.append('nonexistent_fact_locator')
                    self.hallucinated.add((key, index))
                else:
                    if f['accession'] != p['accession']:
                        self.hallucinated.add((key, index))
                    fields = {k: f[k] for k in ('accession', 'concept', 'context_ref', 'unit')}
                    fields.update({k: v for k, v in f['temporal'].items() if k != 'kind'})
                    if any(p.get(k) != v for k, v in fields.items()) or any(k in p and k not in fields for k in ('instant', 'period_start', 'period_end')):
                        reasons.append('wrong_fact_identity')
                    if 'chunk_id' in p and p['chunk_id'] != f['chunk_id']:
                        reasons.append('wrong_chunk_linkage')
                fact_valid = not reasons
                eligible = f is not None and f['unit'] is not None and self.values[p['fact_locator']] is not None
                # The raw XBRL union represents numeric facts even on a
                # narrative claim; nonnumeric facts always require a chunk route.
                identity_valid = fact_valid and eligible
                if fact_valid and not eligible:
                    reasons.append('nonnumeric_fact')
            found.append(dict(owner_type=key[0], owner_id=key[1], record_index=index,
                provenance_type=p['provenance_type'], identity_valid=bool(identity_valid),
                FACT_IDENTITY_VALID=fact_valid, APPROVED_PATH_VALID=False, numeric_eligible=eligible,
                reason_codes=sorted(reasons)))
        self.findings[key] = found

    def path(self, key, target):
        records = _provenance(self.owners[key]); findings = self.findings[key]
        accepted = set()
        for path in target['approved_chunk_paths']:
            matching = []
            for member in path['members']:
                matching.append([i for i, p in enumerate(records) if p['provenance_type'] == 'chunk' and
                    findings[i]['identity_valid'] and all(p.get(k) == v for k, v in member.items())])
            if all(matching):
                accepted.update(i for ids in matching for i in ids)
        for path in target['approved_xbrl_paths']:
            accepted.update(i for i, p in enumerate(records) if p['provenance_type'] == 'xbrl_fact' and
                findings[i]['identity_valid'] and p['fact_locator'] == path['fact_identity']['fact_locator'])
        return bool(accepted), {key: accepted}

    def derived(self, calc_id, spec, family, active=None):
        active = set() if active is None else active
        calc = self.calcs.get(calc_id)
        roles = spec['required_inputs']
        items = calc['inputs'] if calc is not None else []
        names = [i['name'] for i in items]
        role_names = [r['input_role'] for r in roles]
        explicit = any(n in role_names for n in names)
        binding_ok = len(items) == len(roles)
        if explicit:
            binding_ok &= len(set(names)) == len(names) and set(names) == set(role_names)
            # Invalid extra/mixed bindings still retain independently inspectable
            # provenance for uniquely identified required roles. They receive no
            # numeric/formula binding credit and cannot fill another role.
            bound = {i['name']: i for i in items if i['name'] in role_names and names.count(i['name']) == 1}
        else:
            bound = {r['input_role']: item for r, item in zip(roles, items)}
        input_results = []; bindings = {}; families = set(); upstream_ok = True
        for role in roles:
            target = self.targets[role['source_target_id']]; item = bound.get(role['input_role'])
            correct = approved = False
            if target['variant_family'] is not None:
                families.add(target['variant_family'])
            if item is not None and calc is not None:
                correct = numeric_match(item, target)[0] and binding_ok
                key = ('calculation_input', calc_id + '/' + item['input_id'])
                if item['source_type'] == 'prior_calculation':
                    prior = item['source_calculation_id']
                    approved, prior_ok, prior_bindings = self.upstream(prior, target, active | {calc_id})
                    bindings.update(prior_bindings)
                    upstream_ok &= prior_ok
                    if prior in self.calcs:
                        pr = self.calcs[prior]['result']
                        correct &= Decimal(item['value']) == Decimal(pr['value']) and item['unit'] == pr['unit']
                elif item['source_type'] == 'cited_fact':
                    approved, own = self.path(key, target); bindings.update(own)
                else:
                    approved = False
            input_results.append(dict(input_role=role['input_role'], source_target_id=role['source_target_id'],
                                      numeric_correct=bool(correct), approved_path_valid=bool(approved)))
        formula_ok = arithmetic_ok = False
        if calc is not None:
            try:
                renames = {item['input_id']: name for name, item in bound.items()}
                form = formula_tree(calc['expression'], renames)
                formula_ok = binding_ok and any(form == formula_tree(f['canonical_formula']) for f in spec['allowed_formula_variants'])
            except (calculator.CalculatorToolError, InputError):
                pass
            arithmetic_ok = audit_arithmetic_v0_2(calc['expression'],
                {i['input_id']: canonical_decimal(i['value']) for i in items}, canonical_decimal(calc['result']['value']))['arithmetic_correct']
            arithmetic_ok &= calc['result']['unit'] == spec['output_unit'] and upstream_ok
        family_ok = not families or (len(families) == 1 and (family is None or family in families))
        return dict(input_results=input_results, formula_correct=bool(formula_ok), arithmetic_correct=bool(arithmetic_ok),
            approved_path_valid=all(i['approved_path_valid'] for i in input_results), bindings=bindings, family_ok=family_ok)

    def upstream(self, calc_id, target, active):
        if calc_id in active or calc_id in self.graph['invalid_calculation_ids'] or calc_id not in self.calcs:
            return False, False, {}
        calc = self.calcs[calc_id]
        variants = sorted((v for g in self.request['gold_bundle']['answer_groups'] for v in g['variants']
            if v['numeric_target_id'] == target['target_id'] and v['derived_specification'] is not None), key=lambda v: v['variant_id'])
        specs = [v['derived_specification'] for v in variants]
        if specs:
            # Evaluate coherent candidates; canonical first passing specification.
            outcomes = [self.derived(calc_id, s, target['variant_family'], active) for s in specs]
            passed = [o for o in outcomes if o['formula_correct'] and o['arithmetic_correct'] and o['approved_path_valid'] and
                      all(i['numeric_correct'] for i in o['input_results']) and o['family_ok']]
            chosen = (passed or outcomes)[0]
            return chosen['approved_path_valid'], bool(passed), chosen['bindings']
        # A direct target forwarded through an identity calculation retains its
        # leaf provenance; arbitrary arithmetic cannot manufacture a direct fact.
        if len(calc['inputs']) != 1:
            return False, False, {}
        item = calc['inputs'][0]
        try:
            identity = formula_tree(calc['expression']) == ('name', item['input_id'])
        except (calculator.CalculatorToolError, InputError):
            identity = False
        numeric = numeric_match(item, target)[0]
        arithmetic = audit_arithmetic_v0_2(calc['expression'], {item['input_id']: canonical_decimal(item['value'])},
                                          canonical_decimal(calc['result']['value']))['arithmetic_correct']
        if item['source_type'] == 'prior_calculation':
            approved, valid, bindings = self.upstream(item['source_calculation_id'], target, active | {calc_id})
        elif item['source_type'] == 'cited_fact':
            approved, bindings = self.path(('calculation_input', calc_id + '/' + item['input_id']), target)
            valid = True
        else:
            approved, valid, bindings = False, False, {}
        return approved, bool(identity and numeric and arithmetic and valid and calc['result']['unit'] == target['unit']), bindings

    def candidate(self, claim, variant):
        numeric, unit, precision, sign, basis = numeric_match(claim['numeric_value'], variant)
        path, bindings = self.path(('claim', claim['claim_id']), variant)
        out = dict(numeric_correct=numeric, unit_result=unit, precision_result=precision,
            sign_result=sign, basis_result=basis, formula_correct=None, arithmetic_correct=None,
            approved_path_valid=path, input_results=[], input_correctness=None,
            bindings=bindings, family_ok=True, result_bound=True, reason_codes=[])
        spec = variant['derived_specification']
        if spec is not None:
            ids = claim.get('calculation_ids', [])
            calc_id = ids[-1] if ids else None
            if claim['claim_id'] in self.graph['dependent_claim_ids']:
                calc_id = None
            derived = self.derived(calc_id, spec, variant['variant_family'])
            out.update(derived)
            # Final-value matching remains independent of formula/arithmetic, but
            # complete pass also binds the reported calculation to this claim.
            calc = self.calcs.get(calc_id)
            if calc is not None:
                result_candidate = dict(calc['result'], period=claim['numeric_value']['period'], basis=claim['numeric_value']['basis'])
                out['result_bound'] = numeric_match(result_candidate, variant)[0]
                if not out['result_bound']:
                    out['reason_codes'].append('CALCULATION_OUTPUT_MISMATCH')
            out['input_correctness'] = ratio(sum(i['numeric_correct'] for i in out['input_results']), len(out['input_results']))
            if not all(i['numeric_correct'] for i in out['input_results']):
                out['reason_codes'].append('REQUIRED_INPUT_MISMATCH')
            if not out['formula_correct']:
                out['reason_codes'].append('FORMULA_MISMATCH')
            if not out['arithmetic_correct']:
                out['reason_codes'].append('ARITHMETIC_MISMATCH')
        if claim['claim_id'] in self.graph['dependent_claim_ids']:
            out['numeric_correct'] = False
        out['complete'] = bool(out['numeric_correct'] and out['approved_path_valid'] and out['family_ok'] and out['result_bound'] and
            out['formula_correct'] is not False and out['arithmetic_correct'] is not False and
            all(i['numeric_correct'] and i['approved_path_valid'] for i in out['input_results']))
        return out

    def occurrence(self, claim, group, number):
        candidates = {v['variant_id']: self.candidate(claim, v) for v in group['variants']} if claim else {}
        select = select_variant_v0_2(dict(selection_schema_version='variant_selection_v0.2',
            approved_variants=[dict(variant_id=v['variant_id'], variant_family=v['variant_family'], structurally_applicable=True)
                               for v in group['variants']] if claim else [],
            candidate_results=[dict(variant_id=k, complete_deterministic_pass=v['complete']) for k, v in candidates.items()],
            explicit_variant_id=None, explicit_family_id=None))['selection']
        vid = select['selected_variant_id']
        result = dict(occurrence=number, claim_id=claim['claim_id'] if claim else None, variant_id=vid,
            numeric_correct=False, formula_correct=None, arithmetic_correct=None, approved_path_valid=False,
            input_correctness=None, unit_result=None, precision_result=None, sign_result=None, basis_result=None,
            variant_selection=select, input_results=[], reason_codes=select['reason_codes'])
        family = None
        if vid is not None:
            chosen = candidates[vid]
            for key in result.keys() & chosen.keys():
                result[key] = chosen[key]
            result['reason_codes'] = sorted(set(chosen['reason_codes'] + select['reason_codes']))
            for key, indices in chosen['bindings'].items():
                self.bindings.setdefault(key, set()).update(indices)
            family = next(v['variant_family'] for v in group['variants'] if v['variant_id'] == vid)
        return result, family


def _metrics_template(slot):
    props = schemas()[0]['deterministic_evaluator_output_schema_v0.2.json']['properties']['metrics']['anyOf'][0]['properties']
    metrics = {k: None for k in props}
    metrics.update(schema_valid=True, completion_dependent_zero=False, answer_group_results=[],
        variant_consistency='NOT_APPLICABLE', invalid_identity_count=0, hallucinated_identity_count=0,
        outside_source_count=0, provenance_findings=[],
        judge_dependent={k: 'PENDING_JUDGE' for k in props['judge_dependent']['required']},
        event_counts={k: slot['events'].count(k) for k in EVENTS})
    return metrics


def _score(request, output, facts, values, targets):
    result = _base_result(); slot = request['slot_record']; status = slot['execution_status']
    result.update(question_id=slot['question_id'], scheduled_slot_id=slot['scheduled_slot_id'],
                  effective_attempt_id=slot['effective_attempt_id'], execution_status=status, checkpoint_valid=True)
    included = status != INFRA
    result['included_in_scored_denominator'] = included
    result['evaluation_completion'] = dict(evaluation_status='EVAL_COMPLETE' if included else 'EVAL_INCOMPLETE',
        scheduled_slot_count=1, scored_slot_count=int(included), missing_infrastructure_slot_ids=[] if included else [slot['scheduled_slot_id']])
    if not included:
        return result
    metrics = _metrics_template(slot); result['metrics'] = metrics
    groups = request['gold_bundle']['answer_groups']
    if status in FAILURES:
        metrics.update(schema_valid=False, completion_dependent_zero=True, numeric_value_correctness=ratio(0, len(groups)),
            complete_numeric_answer=False if groups else None, benchmark_provenance_correctness=ratio(0, len(groups)),
            provenance_completeness=False if groups else None, deterministic_grounded_prerequisites=False if groups else None)
        return result
    graph = _graph(output); result['calculation_graph'] = graph
    result['agent_output_contract_valid'] = graph['valid']
    scorer = _Scorer(request, output, facts, values, targets, graph)
    eligible = [c for c in output['claims'] if c['claim_type'] == 'numeric' and c['material'] and c['claim_id'] in output['answer_claim_ids']]
    assigned = []; offset = 0; all_occurrences = []; consistency = defaultdict(set); consistent = True
    for group in groups:
        occurrences = []; families = set()
        for number in range(1, group['multiplicity'] + 1):
            claim = eligible[offset] if offset < len(eligible) else None
            offset += 1
            occurrence, family = scorer.occurrence(claim, group, number)
            occurrences.append(occurrence)
            assigned.append(dict(answer_group_id=group['answer_group_id'], occurrence=number, claim_id=occurrence['claim_id']))
            if family is not None:
                families.add(family)
        coherent = len(families) <= 1
        consistent &= coherent
        if group['question_consistency_group'] is not None:
            consistency[group['question_consistency_group']].update(families)
        metrics['answer_group_results'].append(dict(answer_group_id=group['answer_group_id'], multiplicity=group['multiplicity'],
            correct=coherent and all(o['variant_selection']['complete_deterministic_pass'] for o in occurrences), occurrences=occurrences))
        all_occurrences.extend(occurrences)
    consistent &= all(len(families) <= 1 for families in consistency.values())
    if not consistent:
        for group, report in zip(groups, metrics['answer_group_results']):
            if group['question_consistency_group'] in consistency and len(consistency[group['question_consistency_group']]) > 1:
                report['correct'] = False
    result['assignment'] = dict(assignment_schema_version='answer_group_assignment_v0.2', assignments=assigned,
                                extra_claim_ids=[c['claim_id'] for c in eligible[offset:]])
    findings = []
    for key, rows in scorer.findings.items():
        for row in rows:
            row['APPROVED_PATH_VALID'] = row['record_index'] in scorer.bindings.get(key, set())
            findings.append(row)
    metrics['provenance_findings'] = findings
    metrics['provenance_validity'] = ratio(sum(f['identity_valid'] for f in findings), len(findings))
    metrics['invalid_identity_count'] = sum(not f['identity_valid'] for f in findings)
    metrics['hallucinated_identity_count'] = len(scorer.hallucinated)
    metrics['outside_source_count'] = sum('outside_source_contract' in f['reason_codes'] for f in findings)
    metrics['numeric_value_correctness'] = ratio(sum(all(o['numeric_correct'] for o in g['occurrences'])
        for g in metrics['answer_group_results']), len(groups))
    inputs = [i for o in all_occurrences for i in o['input_results']]
    metrics['required_input_correctness'] = ratio(sum(i['numeric_correct'] for i in inputs), len(inputs))
    metrics['formula_correctness'] = conjunction(o['formula_correct'] for o in all_occurrences)
    calculation_audits = [audit_arithmetic_v0_2(c['expression'],
        {i['input_id']: canonical_decimal(i['value']) for i in c['inputs']}, canonical_decimal(c['result']['value']))
        for c in output['calculations']]
    metrics['arithmetic_correctness'] = conjunction([o['arithmetic_correct'] for o in all_occurrences] +
                                                   [a['arithmetic_correct'] for a in calculation_audits])
    family_applicable = any(v['variant_family'] is not None for g in groups for v in g['variants'])
    metrics['variant_consistency'] = ('PASS' if consistent else 'FAIL') if family_applicable else 'NOT_APPLICABLE'
    # This metric counts material claims with assigned benchmark provenance;
    # numeric value correctness above retains its distinct group denominator.
    provenance_occurrences = [o for o in all_occurrences if o['claim_id'] is not None]
    metrics['benchmark_provenance_correctness'] = ratio(sum(o['approved_path_valid'] for o in provenance_occurrences),
                                                       len(provenance_occurrences))
    metrics['provenance_completeness'] = all(o['approved_path_valid'] for o in all_occurrences) if groups else None
    metrics['complete_numeric_answer'] = (graph['valid'] and consistent and all(g['correct'] for g in metrics['answer_group_results'])) if groups else None
    if not graph['valid']:
        metrics['complete_numeric_answer'] = False
    metrics['deterministic_grounded_prerequisites'] = (bool(metrics['complete_numeric_answer']) and
        metrics['provenance_completeness'] and metrics['invalid_identity_count'] == 0) if groups else None
    result['reason_codes'] = sorted(set(graph['reason_codes'] + [r for o in all_occurrences for r in o['reason_codes']] +
        [r for f in findings for r in f['reason_codes']] +
        (['ARITHMETIC_MISMATCH'] if any(not a['arithmetic_correct'] for a in calculation_audits) else [])))
    return result


def evaluate_v0_2(request):
    """Evaluate one normalized scheduled slot, preserving system/agent separation."""
    accepted = False
    try:
        _recognize(request)
        validate('evaluation_request_v0.2.schema.json', request)
        chunks = unique(request['chunk_catalog'], 'chunk_id')
        facts, values = validate_index(request['frozen_xbrl_fact_index'], request['xbrl_numeric_values'], chunks)
        mapping = validate_normalized_map(request['normalized_xbrl_map'], facts, values)
        targets = _validate_gold(request['gold_bundle'], facts, values, chunks, mapping)
        require(request['gold_bundle']['question_id'] == request['slot_record']['question_id'], 'Gold/slot question mismatch')
        output = _validate_slot(request)
        accepted = True
        result = _score(request, output, facts, values, targets)
        validate('deterministic_evaluator_output_schema_v0.2.json', result)
        return result
    except InputError as error:
        result = _base_result()
        result.update(evaluator_status='EVAL_INTERNAL_ERROR' if accepted else error.status,
                      errors=[dict(code=error.code, path=error.path, message=str(error))])
        return result
    except Exception as error:
        result = _base_result()
        result.update(evaluator_status='EVAL_INTERNAL_ERROR', errors=[dict(code='INTERNAL_ERROR', path='/',
            message=type(error).__name__ + ': ' + str(error))])
        return result


def aggregate_metrics_v0_2(slots):
    require(isinstance(slots, list), 'Aggregate records must be an array')
    for slot in slots:
        require(isinstance(slot, dict) and set(slot) == {'slot_id', 'execution_status', 'applicable', 'numerator', 'denominator'},
                'Malformed aggregate record')
        require(isinstance(slot['slot_id'], str) and slot['slot_id'] and
                isinstance(slot['execution_status'], str) and type(slot['applicable']) is bool,
                'Malformed aggregate identity/applicability')
    unique(slots, 'slot_id')
    missing = []; numerator = denominator = scored = 0
    for slot in slots:
        require(slot['execution_status'] in STATUSES, 'Unknown status')
        if slot['execution_status'] == INFRA:
            require(slot['numerator'] is None and slot['denominator'] is None, 'Infrastructure cannot carry a quality score')
            missing.append(slot['slot_id'])
        else:
            scored += 1
            if slot['applicable']:
                n, d = slot['numerator'], slot['denominator']
                require(type(n) is int and type(d) is int and 0 <= n <= d and d > 0, 'Invalid metric counts')
                require(slot['execution_status'] not in FAILURES or n == 0, 'Terminal failure must contribute zero')
                numerator += n; denominator += d
            else:
                require(slot['numerator'] is None and slot['denominator'] is None, 'Inapplicable metric has counts')
    return dict(scheduled_slot_count=len(slots), scored_slot_count=scored, metric=ratio(numerator, denominator),
        missing_infrastructure_slot_ids=sorted(missing), evaluation_status='EVAL_INCOMPLETE' if missing else 'EVAL_COMPLETE',
        deterministic_subtotal=None)
