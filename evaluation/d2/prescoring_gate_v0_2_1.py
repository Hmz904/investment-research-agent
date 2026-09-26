"""Shared mandatory precondition for reportable DEV and authorized TEST scoring.

The caller supplies the split's deterministic, frozen-input integrity validator.
DEV uses the unchanged frozen validate_dev(). For TEST, open the authorized
frozen gold/map first and bind its validator here before scoring any output.
The validator must authenticate the complete target set and check all applicable
numeric constraints; this wrapper contains no split-specific numeric semantics.
"""
from .validation_v0_2 import require


def validate_gold_integrity_before_scoring(validate_integrity):
    """Return a complete PASS record or raise before the caller enters scoring.

Validators return total/passed/failed and one target result per required target,
using the frozen DEV integrity record shape. Exceptions and incomplete/failing
records prohibit scoring. They require checkpoint invalidation, evaluator/gold
repair and versioning, and a fresh precheck on rerun.
"""
    result = validate_integrity()
    require(isinstance(result, dict), 'Missing gold integrity result')
    require(all(type(result.get(k)) is int for k in ('total', 'passed', 'failed')),
            'Invalid gold integrity counts')
    require(result['total'] > 0 and result['passed'] == result['total'] and result['failed'] == 0,
            'Gold integrity precheck did not pass every target')
    targets = result.get('targets')
    require(isinstance(targets, list) and len(targets) == result['total'] and
            all(isinstance(target, dict) and target.get('result') == 'PASS' for target in targets),
            'Incomplete gold integrity target results')
    return result
