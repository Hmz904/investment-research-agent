"""Synthetic historical-wire inputs for the prospective S1 tests; no scoring."""
from copy import deepcopy
from decimal import Decimal

from d2_v2_contract_fixtures import (
    claim, derived_request, exact, get_output, output, precision, put_output, request,
)


def quantum_request(candidate, reference, q, lower, upper, inclusive):
    r = request()
    p = precision(reference, 'QUANTUM', q, lower, upper, inclusive)
    for record in (r['gold_bundle']['numeric_targets'][0],
                   r['gold_bundle']['answer_groups'][0]['variants'][0]):
        record.update(accepted_value=reference, precision=deepcopy(p))
    a = output()
    a['claims'] = [claim(value=candidate)]
    return put_output(r, a)


def d19_request(candidate='37'):
    r = derived_request()
    for t in r['gold_bundle']['numeric_targets']:
        t.update(accepted_value='37', precision=exact('37'))
    v = r['gold_bundle']['answer_groups'][0]['variants'][0]
    v.update(accepted_value='37', precision=exact('37'))
    # Historical S2 interval is preserved in the input. Successor interpretation
    # must supersede it, not reject these satisfiable primitive constraints.
    v['derived_specification']['output_precision'] = precision('37', 'QUANTUM', '10', '37', '37', False)
    a = get_output(r)
    a['claims'][0]['numeric_value'].update(value=Decimal(candidate), display_value=candidate)
    a['calculations'][0]['inputs'][0]['value'] = Decimal('37')
    a['calculations'][0]['result'].update(value=Decimal('37'), display_value='37')
    return put_output(r, a)
