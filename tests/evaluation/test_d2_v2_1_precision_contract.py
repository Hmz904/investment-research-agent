"""Prospective S1 assertions. Authoring: syntax/fixture validation ONLY.

Expected literals come from supplement v0.2.1 P2–P4, never implementation.
The next implementation session must externally bind v0.2.1 interpretation
before invoking these assertions over unchanged historical v0.2 wire inputs.
"""
from copy import deepcopy
import importlib

import pytest

from d2_v2_1_precision_fixtures import d19_request, quantum_request


@pytest.fixture
def api():
    # Deferred until an authorized implementation session; never called here.
    return importlib.import_module('evaluation.d2.deterministic_evaluator')


@pytest.mark.parametrize('candidate,reference,q,lower,upper,inclusive,expected', [
    # NF004-style raw reference; original S2 empty interval remains source data.
    ('56.0', '56.0468756436', '0.1', '56.0468756436', '56.0468756436', False, True),
    ('56.1', '56.0468756436', '0.1', '56.0468756436', '56.0468756436', False, False),
    # Existing offgrid_gold audit primitive inputs.
    ('37.1', '37.1', '1', '37.1', '37.1', False, True),
    # Preserved original 257-suite S2 parameter case, with additive S1 assertion.
    ('1.24', '1.23', '0.1', '1.23', '1.23', False, True),
    # HALF_EVEN on candidate and reference, including negative and odd ties.
    ('1.25', '1.23', '0.1', '1.23', '1.23', False, True),
    ('1.35', '1.23', '0.1', '1.23', '1.23', False, False),
    ('-1.25', '-1.23', '0.1', '-1.23', '-1.23', False, True),
    ('1.2', '1.25', '0.1', '1.25', '1.25', False, True),
])
def test_S1_quantum_classes(api, candidate, reference, q, lower, upper, inclusive, expected):
    r = quantum_request(candidate, reference, q, lower, upper, inclusive)
    preserved = deepcopy(r)
    result = api.evaluate_v0_2(r)
    assert r == preserved, 'successor interpretation must not mutate historical input'
    assert result['evaluator_status'] == 'EVAL_OK'
    occurrence = result['metrics']['answer_group_results'][0]['occurrences'][0]
    assert occurrence['precision_result']['matched'] is expected
    assert result['metrics']['complete_numeric_answer'] is expected
    assert result['included_in_scored_denominator'] is True


@pytest.mark.parametrize('candidate,expected', [('37', True), ('38', False)])
def test_S1_D19_exact_and_derived_quantum(api, candidate, expected):
    r = d19_request(candidate)
    preserved = deepcopy(r)
    result = api.evaluate_v0_2(r)
    assert r == preserved
    assert result['evaluator_status'] == 'EVAL_OK'
    assert result['checkpoint_valid'] is True
    assert result['included_in_scored_denominator'] is True
    assert result['metrics']['numeric_value_correctness'] == {'numerator': int(expected), 'denominator': 1}
    assert result['metrics']['complete_numeric_answer'] is expected
    # 38 is inside Q_10(reference=37)'s class, but fails EXACT 37. It must
    # remain ordinary answer failure, never EVAL_INPUT_INVALID.


def test_S1_nonempty_interval_is_diagnostic(api):
    # Same primitive off-grid reference with the regenerated diagnostic interval.
    r = quantum_request('56.0', '56.0468756436', '0.1', '55.95', '56.05', True)
    result = api.evaluate_v0_2(r)
    assert result['evaluator_status'] == 'EVAL_OK'
    assert result['metrics']['complete_numeric_answer'] is True
