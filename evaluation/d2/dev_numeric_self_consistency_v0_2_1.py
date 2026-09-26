"""DEV-only gold integrity gate. Independent normative math; no evaluator imports.

Run directly. Reads only the two pinned DEV numeric files. No agent scoring.
The small precision helpers also accept explicit records for static validation.
"""
import csv
from decimal import Decimal, ROUND_HALF_EVEN, localcontext, Inexact, Rounded
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
SOURCES = {
    'benchmark/dev/v0.1/numeric_answers.csv':
        'c6f82689fe8dd1adb1b5b054c393c4a7a5c2ffbc046ff8d100909127fcefcb0e',
    'evaluation/dev/xbrl/dev_numeric_targets_v0.1.csv':
        'ad35e1bf23366c4564883c407e062cf319f06469cea7cfd9bc89451b5696d793',
}
# Only labels present in these pinned DEV files; mapping specification v0.1 §2.
UNITS = {'USD_million': ('USD', '1000000'),
         'percent': ('pure', '0.01'),
         'USD_per_diluted_share': ('USD_per_share', '1')}


def decimal(text):
    if not isinstance(text, str) or not re.fullmatch(r'[+-]?[0-9]+(?:\.[0-9]+)?', text):
        raise ValueError('invalid plain Decimal')
    return Decimal(text)


def quantum(text):
    value = decimal(text)
    digits = ''.join(map(str, value.as_tuple().digits)).rstrip('0')
    if value <= 0 or digits != '1':
        raise ValueError('quantum must be a positive power of ten')
    return value


def context_precision(*values):
    return 20 + sum(len(v.as_tuple().digits) + abs(v.as_tuple().exponent) for v in values)


def quantized(value, q):
    quantum(format(q, 'f'))
    with localcontext() as ctx:
        ctx.prec = context_precision(value, q)
        ctx.traps[Inexact] = ctx.traps[Rounded] = True
        # to_integral_value intentionally performs the sole registered rounding.
        return q * (value / q).to_integral_value(rounding=ROUND_HALF_EVEN)


def matches(candidate, reference, mode, parameter=None):
    c, r = decimal(candidate), decimal(reference)
    if mode == 'EXACT':
        return c == r
    if mode == 'QUANTUM':
        q = quantum(parameter)
        return quantized(c, q) == quantized(r, q)
    if mode == 'ABS_TOLERANCE':
        t = decimal(parameter)
        if t < 0:
            raise ValueError('negative tolerance')
        with localcontext() as ctx:
            ctx.prec = context_precision(c, r, t)
            ctx.traps[Inexact] = ctx.traps[Rounded] = True
            return abs(c-r) <= t
    raise ValueError('unknown precision mode')


def satisfies(candidate, constraints):
    """Check a witness against all constraints; does not search for a solution."""
    return all(matches(candidate, **record) for record in constraints)


def check_target(row, metadata):
    tid = row['fact_id']
    def require(condition, message):
        if not condition:
            raise ValueError(f'{tid}: {message}')
    require(metadata['gold_target_id'] == tid, 'target identity disagreement')
    for gold_key, meta_key in [('accepted_value', 'gold_value'), ('unit', 'gold_unit'),
                              ('q_id', 'question_id'), ('role', 'role'),
                              ('direct_or_derived', 'direct_or_derived'),
                              ('variant_group', 'variant_group'), ('basis', 'basis'),
                              ('variant_family', 'variant_family'),
                              ('formula', 'formula'), ('required_input_facts', 'required_input_ids')]:
        require(row[gold_key] == metadata[meta_key], f'{gold_key} disagreement')
    raw = decimal(row['accepted_value'])
    rule = json.loads(metadata['precision_rule_json'])
    if row['tolerance']:
        mode, parameter = 'ABS_TOLERANCE', row['tolerance']
        decimal(parameter)
        require(decimal(parameter) >= 0, 'negative tolerance')
    elif row['display_precision']:
        require(re.fullmatch(r'[0-9]+', row['display_precision']) is not None, 'invalid display precision')
        mode = 'QUANTUM'
        parameter = format(Decimal((0, (1,), -int(row['display_precision']))), 'f')
    else:
        mode, parameter = 'EXACT', None
    # Frozen DEV rows currently all declare display quantum. Fail closed if their
    # metadata layout changes; no inferred fallback or unvalidated new adapter.
    require(mode == 'QUANTUM', 'pinned DEV metadata adapter requires QUANTUM')
    q = quantum(parameter)
    display = quantized(raw, q)
    expected_rule = 'precision_rounding_quantum_v0.1'
    require(rule['rule_id'] == metadata['precision_rule_id'] == expected_rule, 'rule ID disagreement')
    require(rule['rounding_mode'] == 'ROUND_HALF_EVEN', 'rounding mode disagreement')
    require(rule['rule_source'] == 'benchmark/dev/v0.1/numeric_answers.csv:display_precision', 'rule source disagreement')
    require(rule['source_precision_text'] == row['display_precision'], 'precision source disagreement')
    require(quantum(rule['quantum']) == q, 'source quantum disagreement')
    unit, factor_text = UNITS[row['unit']]
    factor = decimal(factor_text)
    with localcontext() as ctx:
        ctx.prec = context_precision(raw, q, factor)
        ctx.traps[Inexact] = ctx.traps[Rounded] = True
        canonical_raw, canonical_display, canonical_q = raw*factor, display*factor, q*factor
        require(rule['canonical_unit'] == unit, 'canonical unit disagreement')
        require(quantum(rule['canonical_quantum']) == canonical_q, 'canonical quantum disagreement')
        require(decimal(rule['comparison_gold_value']) == canonical_display, 'canonical display disagreement')
        # Gold/display witness must satisfy target/variant and, for a derived
        # row, inherited final-output precision (R6/R7). All current DEV output
        # precision is recorded by this same row; there is no extra override.
        constraints = [{'reference': row['accepted_value'], 'mode': mode, 'parameter': parameter}]
        require(satisfies(format(display, 'f'), constraints), 'gold/display witness fails target precision')
        require(matches(format(canonical_display, 'f'), format(canonical_raw, 'f'),
                        'QUANTUM', rule['canonical_quantum']), 'normalized raw reference mismatch')
        require(matches(format(canonical_display, 'f'), rule['comparison_gold_value'],
                        'QUANTUM', rule['canonical_quantum']), 'metadata precision mismatch')
        interval = rule['canonical_comparison_interval']
        k = canonical_display/canonical_q
        inclusive = int(k) % 2 == 0
        require(interval['canonical_unit'] == unit, 'interval unit disagreement')
        require(decimal(interval['lower']) == canonical_display-canonical_q/2 and
                decimal(interval['upper']) == canonical_display+canonical_q/2 and
                interval['lower_inclusive'] is inclusive and interval['upper_inclusive'] is inclusive,
                'S1 diagnostic interval disagreement')
    return {'target_id': tid, 'role': row['role'], 'variant': row['variant_group'] or None,
            'reference': row['accepted_value'], 'quantum': parameter,
            'display_value': format(display, 'f'), 'canonical_unit': unit,
            'canonical_display_value': format(canonical_display, 'f'),
            'constraints_checked': ['target', 'metadata_comparison'] +
                (['answer_variant', 'derived_output'] if row['direct_or_derived'] == 'derived' else []),
            'result': 'PASS'}


def validate_dev():
    loaded = []
    for name, digest in SOURCES.items():
        raw = (ROOT/name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError(f'{name}: frozen source hash mismatch')
        loaded.append(list(csv.DictReader(raw.decode().splitlines())))
    gold, metadata = loaded
    ids = {f'NF{i:03}' for i in range(1, 18)}
    if len(gold) != 17 or len(metadata) != 17 or {r['fact_id'] for r in gold} != ids or {r['gold_target_id'] for r in metadata} != ids:
        raise ValueError('DEV must contain exactly NF001–NF017, including approved variants')
    by_id = {r['gold_target_id']: r for r in metadata}
    results = [check_target(row, by_id[row['fact_id']]) for row in sorted(gold, key=lambda r: r['fact_id'])]
    return {'gate_version': 'd2_dev_numeric_self_consistency_v0.2.1',
            'contract': 'd2_contract_v0.2.1', 'source_sha256': SOURCES,
            'total': 17, 'passed': 17, 'failed': 0, 'targets': results,
            'production_evaluator_used': False, 'agent_output_used': False, 'TEST_accessed': False}


if __name__ == '__main__':
    print(json.dumps(validate_dev(), indent=2, sort_keys=True))
