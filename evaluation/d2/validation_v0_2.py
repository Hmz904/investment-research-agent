"""Strict local contracts and exact arithmetic shared by the D2 v2 evaluator."""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, Context, Inexact, Rounded, ROUND_HALF_EVEN, localcontext
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator, FormatChecker, ValidationError, validators
from referencing import Registry, Resource
from src.tools import calculator_tool as calculator

D2 = Path(__file__).resolve().parent
FINGERPRINT = 'acaf087ee2c4fb7427377cae5f1968da26c75d4dfa565f67f1e056b2c4cc4eb6'
PLAIN = re.compile(r'[+-]?[0-9]+(?:\.[0-9]+)?\Z')
FAILURES = frozenset(['FAIL_TOOL_BUDGET_EXHAUSTED', 'FAIL_STEP_BUDGET_EXHAUSTED',
    'FAIL_FINAL_SCHEMA_INVALID', 'FAIL_NO_VALID_FINAL_OUTPUT', 'FAIL_AGENT_ORCHESTRATION_UNRECOVERABLE'])
INFRA = 'INFRA_RUN_RETRY_EXHAUSTED'
STATUSES = FAILURES | {INFRA, 'RUN_COMPLETED'}
EVENTS = ('EVT_FIXED_TOP_K_VIOLATION', 'EVT_TOOL_ARGUMENT_REJECTED',
          'EVT_TOOL_ZERO_RESULT', 'EVT_TOOL_DOMAIN_ERROR_RECOVERABLE')


class InputError(ValueError):
    def __init__(self, message, code='INVALID_INPUT', path='/', status='EVAL_INPUT_INVALID'):
        super().__init__(message)
        self.code, self.path, self.status = code, path, status


def require(condition, message, **kwargs):
    if not condition:
        raise InputError(message, **kwargs)


def mismatch(message):
    raise InputError(message, code='CONTRACT_MISMATCH', status='EVAL_CONTRACT_MISMATCH')


def strict_loads(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    def constant(value):
        raise InputError('Nonfinite JSON number: ' + value)
    try:
        return json.loads(raw, parse_float=Decimal, parse_int=int,
                          parse_constant=constant, object_pairs_hook=pairs)
    except (ValueError, TypeError) as error:
        if isinstance(error, InputError):
            raise
        raise InputError('Invalid JSON') from error


def plain(value):
    require(isinstance(value, str) and PLAIN.fullmatch(value), 'Expected plain decimal string')
    return Decimal(value)


def canonical_decimal(value):
    require(isinstance(value, (Decimal, int)) and not isinstance(value, bool), 'Expected exact number')
    value = Decimal(value)
    require(value.is_finite(), 'Nonfinite number')
    if value == 0:
        return '0'
    text = format(value, 'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


def canonical_json_bytes(value):
    def convert(item):
        if isinstance(item, Decimal):
            return canonical_decimal(item)
        if isinstance(item, float):
            raise InputError('Binary float forbidden')
        if isinstance(item, dict):
            require(all(isinstance(k, str) for k in item), 'JSON keys must be strings')
            return {k: convert(v) for k, v in item.items()}
        if isinstance(item, list):
            return [convert(v) for v in item]
        return item
    return (json.dumps(convert(value), sort_keys=True, ensure_ascii=False,
                       separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')


def result_sha256(value):
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _json_equality_key(value):
    # JSON Schema equality distinguishes booleans from numbers but equates
    # numerically equal number representations, including nested values.
    if isinstance(value, bool):
        return ('boolean', value)
    if isinstance(value, (int, Decimal, float)):
        return ('number', value)
    if isinstance(value, dict):
        return ('object', frozenset((k, _json_equality_key(v)) for k, v in value.items()))
    if isinstance(value, list):
        return ('array', tuple(_json_equality_key(v) for v in value))
    return (type(value).__name__, value)


def _unique_items(validator, unique_items, instance, schema):
    if unique_items and validator.is_type(instance, 'array'):
        seen = set()
        for item in instance:
            key = _json_equality_key(item)
            if key in seen:
                yield ValidationError('Array has duplicate items')
                return
            seen.add(key)


# Equivalent uniqueItems validation in linear time for the 7,839-row universe.
_Validator = validators.extend(Draft202012Validator, {'uniqueItems': _unique_items})


def _evolve(validator, **changes):
    # All admitted resources are Draft 2020-12. Preserve the equivalent custom
    # keyword implementation when following a resource's explicit $schema.
    for name, alias in [('schema', 'schema'), ('_ref_resolver', 'resolver'),
                        ('format_checker', 'format_checker'), ('_registry', 'registry'),
                        ('_resolver', '_resolver')]:
        changes.setdefault(alias, getattr(validator, name))
    return _Validator(**changes)


_Validator.evolve = _evolve


@lru_cache(maxsize=1)
def schemas():
    paths = list(D2.glob('*.schema.json')) + [D2 / 'deterministic_evaluator_output_schema_v0.2.json',
                                            D2.parent / 'agent_output_schema_v0.1.1.json']
    loaded = {p.name: strict_loads(p.read_text()) for p in paths}
    checker = FormatChecker()
    def inspect(node):
        if isinstance(node, dict):
            if 'format' in node:
                require(node['format'] in checker.checkers, 'Unknown declared schema format')
            for v in node.values():
                inspect(v)
        elif isinstance(node, list):
            for v in node:
                inspect(v)
    for schema in loaded.values():
        Draft202012Validator.check_schema(schema)
        inspect(schema)
    registry = Registry().with_resources((s['$id'], Resource.from_contents(s)) for s in loaded.values())
    return loaded, registry, checker


def validate(name, value, definition=None):
    loaded, registry, checker = schemas()
    schema = loaded[name]
    if definition:
        schema = {'$ref': schema['$id'] + '#/$defs/' + definition}
    try:
        _Validator(schema, registry=registry, format_checker=checker).validate(value)
    except ValidationError as error:
        raise InputError(error.message, path='/' + '/'.join(map(str, error.absolute_path))) from error


def exact_json(value):
    """Reject non-JSON objects and binary float before schema adaptation."""
    active = set()
    def visit(item):
        if isinstance(item, (dict, list)):
            require(id(item) not in active, 'Cyclic Python input is not JSON')
            active.add(id(item))
            if isinstance(item, dict):
                require(all(isinstance(k, str) for k in item), 'Non-string JSON key')
                children = item.values()
            else:
                children = item
            for child in children:
                visit(child)
            active.remove(id(item))
        else:
            require(item is None or isinstance(item, (str, bool, int, Decimal)), 'Unsupported JSON value type')
            if isinstance(item, Decimal):
                require(item.is_finite(), 'Nonfinite number')
    visit(value)


def unique(rows, key):
    result = {}
    for row in rows:
        require(row[key] not in result, 'Duplicate ' + key)
        result[row[key]] = row
    return result


def exact_context(*values):
    """Size the context from decimal operands, independent of ambient context."""
    decimals = [Decimal(v) for v in values]
    digits = sum(len(v.as_tuple().digits) + abs(v.as_tuple().exponent) for v in decimals)
    return localcontext(Context(prec=max(100, digits + 20), traps=[Inexact, Rounded]))


def precision_interval(p):
    ref = plain(p['reference_value'])
    mode = p['mode']
    parameter = p['quantum'] if mode == 'QUANTUM' else p['absolute_tolerance']
    amount = plain(parameter) if parameter is not None else Decimal(0)
    with exact_context(ref, amount):
        inclusive = True
        if mode == 'EXACT':
            low = high = ref
        elif mode == 'ABS_TOLERANCE':
            require(amount >= 0, 'Negative tolerance')
            low, high = ref - amount, ref + amount
        else:
            require(amount > 0 and amount.normalize().as_tuple().digits == (1,), 'Quantum must be power of ten')
            k = (ref / amount).to_integral_value(rounding=ROUND_HALF_EVEN)
            center = k * amount
            low, high = center - amount / 2, center + amount / 2
            inclusive = k % 2 == 0
    return {'lower': canonical_decimal(low), 'upper': canonical_decimal(high),
            'lower_inclusive': inclusive, 'upper_inclusive': inclusive}


def validate_precision(p, value, unit):
    validate('precision_record_v0.2.schema.json', p)
    require(plain(p['reference_value']) == plain(value) and p['comparison_unit'] == unit,
            'Precision coordinate disagrees with gold')
    expected = precision_interval(p)
    if p['mode'] != 'QUANTUM':
        require(all(plain(p['interval'][k]) == plain(expected[k]) for k in ('lower', 'upper')) and
                all(p['interval'][k] == expected[k] for k in ('lower_inclusive', 'upper_inclusive')),
                'Precision interval disagreement')
    # P3: historical wire records keep their bytes and identity. Only their
    # QUANTUM derived interval is superseded in this separate S1 projection.
    successor = deepcopy(p)
    successor.update(precision_schema_version='precision_record_v0.2.1', interval=expected)
    validate('precision_record_v0.2.1.schema.json', successor)
    return successor


def adapt_precision_v0_2(metadata, *, reference_value, unit):
    try:
        require(isinstance(metadata, dict), 'Precision metadata must be an object')
        plain(reference_value)
        p = dict(precision_schema_version='precision_record_v0.2', mode='EXACT', quantum=None,
                 absolute_tolerance=None, rounding_mode=None, source_encoding='legacy_exact', source_value=None,
                 precision_rule_id='precision_exact_v0.1', comparison_unit=unit, reference_value=reference_value)
        if 'tolerance' in metadata:
            t = plain(metadata['tolerance'])
            require(t >= 0, 'Negative tolerance')
            p.update(mode='ABS_TOLERANCE', absolute_tolerance=canonical_decimal(t), source_encoding='legacy_tolerance',
                     source_value=metadata['tolerance'], precision_rule_id='precision_absolute_tolerance_v0.1')
        elif 'display_precision' in metadata:
            digits = metadata['display_precision']
            require(type(digits) is int and digits >= 0, 'Invalid decimal-place precision')
            q = Decimal((0, (1,), -digits))
            p.update(mode='QUANTUM', quantum=canonical_decimal(q), source_encoding='legacy_display_precision',
                     source_value=str(digits), rounding_mode='ROUND_HALF_EVEN', precision_rule_id='precision_rounding_quantum_v0.1')
        p['interval'] = precision_interval(p)
        validate_precision(p, reference_value, unit)
        return {'evaluator_status': 'EVAL_OK', 'precision': p, 'errors': []}
    except InputError as error:
        return {'evaluator_status': 'EVAL_INPUT_INVALID', 'precision': None,
                'errors': [{'code': error.code, 'path': error.path, 'message': str(error)}]}


# label -> canonical unit, positive exact factor, frozen rule ID
UNITS = {
    'USD': ('USD', '1', 'monetary_usd_identity_v0.1'),
    'shares': ('shares', '1', 'shares_identity_v0.1'),
    'USD_per_share': ('USD_per_share', '1', 'usd_per_share_identity_v0.1'),
    'USD_per_basic_share': ('USD_per_share', '1', 'usd_per_basic_share_alias_v0.1'),
    'USD_per_diluted_share': ('USD_per_share', '1', 'usd_per_diluted_share_alias_v0.1'),
    'pure': ('pure', '1', 'ratio_pure_identity_v0.1'),
    'percent': ('pure', '0.01', 'ratio_percent_to_pure_v0.1'),
    'percentage_point': ('percentage_point', '1', 'percentage_point_identity_v0.1'),
}
for _base, _prefix in [('USD', 'monetary_usd'), ('shares', 'shares')]:
    for _scale, _factor in [('thousand', '1000'), ('million', '1000000'), ('billion', '1000000000')]:
        UNITS[_base + '_' + _scale] = (_base, _factor, f'{_prefix}_{_scale}_to_{_base.lower()}_v0.1')


def numeric_match(candidate, target):
    cv, gv = Decimal(candidate['value']), plain(target['accepted_value'])
    cu, gu = candidate['unit'], target['unit']
    unit = dict(status='unregistered_unit', comparison_unit=None, normalization_rule_id=None,
                candidate_value=None, reference_value=None)
    p = target['precision']
    match = False
    with exact_context(cv, gv, p['quantum'] or '0', p['absolute_tolerance'] or '0', '1000000000'):
        if cu == gu:
            unit.update(status='exact_label_match', comparison_unit=gu)
            factor = Decimal(1)
        elif cu in UNITS and gu in UNITS and UNITS[cu][0] == UNITS[gu][0]:
            cv *= Decimal(UNITS[cu][1]); factor = Decimal(UNITS[gu][1]); gv *= factor
            unit.update(status='registered_equivalence', comparison_unit=UNITS[gu][0],
                        normalization_rule_id=UNITS[cu][2])
        else:
            factor = None
        sign = (cv > 0) == (gv > 0) and (cv < 0) == (gv < 0)
        if factor is not None:
            unit.update(candidate_value=canonical_decimal(cv), reference_value=canonical_decimal(gv))
            if p['mode'] == 'EXACT':
                match = cv == gv
            elif p['mode'] == 'ABS_TOLERANCE':
                match = abs(cv - gv) <= plain(p['absolute_tolerance']) * factor
            else:
                q = plain(p['quantum']) * factor
                match = (q * (cv / q).to_integral_value(rounding=ROUND_HALF_EVEN) ==
                         q * (gv / q).to_integral_value(rounding=ROUND_HALF_EVEN))
    basis = candidate.get('basis') == target['basis']
    correct = bool(match and sign and basis and candidate.get('period') == target['period'])
    return correct, unit, {'mode': p['mode'], 'matched': bool(match), 'rule_id': p['precision_rule_id']}, sign, basis


def formula_tree(expression, renames=None):
    require(len(expression) <= calculator.MAX_EXPRESSION_CHARACTERS, 'Formula too long')
    root = calculator._ExpressionParser(expression).parse()
    def visit(node):
        if isinstance(node, calculator._NameNode):
            return ('name', (renames or {}).get(node.name, node.name))
        if isinstance(node, calculator._LiteralNode):
            return ('literal', canonical_decimal(node.value))
        if isinstance(node, calculator._UnaryNode):
            child = visit(node.operand)
            if node.operator == '+':
                return child
            if child[0] == 'literal' and Decimal(child[1]) == 0:
                return ('literal', '0')
            return ('unary', node.operator, child)
        return ('binary', node.operator, visit(node.left), visit(node.right))
    return visit(root)


def audit_arithmetic_v0_2(expression, values, submitted_result):
    try:
        require(isinstance(values, dict), 'Arithmetic inputs must be an object')
        expected = plain(submitted_result)
        response = calculator.CalculatorTool().calculate(expression,
            {k: calculator.CalculationInput(value=v) for k, v in values.items()})
        correct = Decimal(response.result) == expected
        return {'arithmetic_correct': correct, 'result': response.result,
                'reason_codes': [] if correct else ['ARITHMETIC_MISMATCH']}
    except (calculator.CalculatorToolError, InputError, TypeError, ValueError):
        return {'arithmetic_correct': False, 'result': None, 'reason_codes': ['INVALID_CALCULATION']}


def select_variant_v0_2(request):
    try:
        validate('variant_selection_v0.2.schema.json', request, 'request')
        variants = unique(request['approved_variants'], 'variant_id')
        results = unique(request['candidate_results'], 'variant_id')
        require(results.keys() <= variants.keys(), 'Unknown candidate result')
        vid, family = request['explicit_variant_id'], request['explicit_family_id']
        require(vid is None or vid in variants, 'Unknown variant', code='UNKNOWN_VARIANT_IDENTIFIER')
        require(family is None or family in {v['variant_family'] for v in variants.values()},
                'Unknown family', code='UNKNOWN_FAMILY_IDENTIFIER')
        require(vid is None or family is None or variants[vid]['variant_family'] == family,
                'Conflicting identifiers', code='CONFLICTING_VARIANT_IDENTIFIERS')
        eligible = sorted(k for k, v in variants.items() if v['structurally_applicable'] and
                          (vid is None or vid == k) and (family is None or family == v['variant_family']))
        require(set(eligible) <= results.keys(), 'Missing eligible candidate result')
        passing = [k for k in eligible if results[k]['complete_deterministic_pass']]
        selected = (passing or eligible or [None])[0]
        mode = 'COMPLETE_PASS' if passing else 'CANONICAL_DIAGNOSTIC' if eligible else 'NO_ELIGIBLE_VARIANT'
        selection = dict(selection_schema_version='variant_selection_v0.2', eligible_variant_ids=eligible,
                         complete_passing_variant_ids=passing, selected_variant_id=selected, selection_mode=mode,
                         complete_deterministic_pass=bool(passing), reason_codes=[] if passing else
                         ['NO_COMPLETE_VARIANT_PASS' if eligible else 'NO_ELIGIBLE_VARIANT'])
        validate('variant_selection_v0.2.schema.json', selection)
        return {'evaluator_status': 'EVAL_OK', 'selection': selection, 'reason_codes': []}
    except InputError as error:
        return {'evaluator_status': error.status, 'selection': None, 'reason_codes': [error.code]}
