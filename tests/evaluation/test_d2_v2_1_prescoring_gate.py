"""Audit-derived ordering regression; reuses the frozen invalid NF004 control."""
from copy import deepcopy
import csv
import json
import sys

import pytest

from evaluation.d2 import dev_numeric_self_consistency_v0_2_1 as gold
from evaluation.d2 import verify_v0_2_1 as workflow


@pytest.mark.parametrize('mode', ['tests', 'harness', 'determinism'])
@pytest.mark.parametrize('valid', [False, True], ids=['invalid_gold', 'valid_dev'])
def test_gold_integrity_precedes_scoring(mode, valid, monkeypatch, tmp_path):
    events = []
    scorer_calls = []
    original_guards = workflow.guards

    def frozen_inputs():
        result = original_guards()
        events.append('frozen_inputs')
        return result

    def integrity():
        events.append('gold_integrity_precheck')
        if valid:
            return gold.validate_dev()
        # Exact control from the frozen test_inconsistent_metadata_fails.
        gold_path, meta_path = [gold.ROOT / p for p in gold.SOURCES]
        with gold_path.open() as stream:
            row = next(r for r in csv.DictReader(stream) if r['fact_id'] == 'NF004')
        with meta_path.open() as stream:
            meta = next(r for r in csv.DictReader(stream) if r['gold_target_id'] == 'NF004')
        bad = deepcopy(meta)
        bad['precision_rule_json'] = bad['precision_rule_json'].replace(
            '"comparison_gold_value":"0.56"', '"comparison_gold_value":"0.57"')
        assert bad != meta
        return gold.check_target(row, bad)

    def scoring():
        events.append('scoring_callback')
        scorer_calls.append(mode)
        result = {'observable_scoring_callback': mode}
        return (result, 'instrumented scoring entrypoint\n') if mode == 'tests' else result

    output = tmp_path / 'checkpoint.json'
    monkeypatch.setattr(workflow, 'guards', frozen_inputs)
    monkeypatch.setattr(workflow, 'validate_dev', integrity)
    monkeypatch.setattr(workflow, {'tests': 'test_accounting', 'harness': 'audit_replay',
                                 'determinism': 'determinism'}[mode], scoring)
    monkeypatch.setattr(sys, 'argv', ['verify_v0_2_1', mode, '--output', str(output)])
    if valid:
        workflow.main()
        result = json.loads(output.read_bytes())
        assert result['dev_integrity']['passed'] == result['dev_integrity']['total'] == 17
        assert result['validation'] == {'observable_scoring_callback': mode}
        assert len(scorer_calls) == 1
        assert events[:3] == ['frozen_inputs', 'gold_integrity_precheck', 'scoring_callback']
    else:
        with pytest.raises(SystemExit) as stopped:
            workflow.main()
        assert stopped.value.code == 1
        result = json.loads(output.read_bytes())
        assert result['checkpoint_valid'] is False
        assert result['aggregate_reportability'] == 'NON-REPORTABLE'
        assert result['evaluator_repair_and_rerun_required'] is True
        assert 'canonical display disagreement' in result['gold_integrity_error']
        assert 'validation' not in result and 'aggregate_metrics' not in result
        assert not output.with_suffix('.txt').exists()
        assert len(scorer_calls) == 0
        assert events == ['frozen_inputs', 'gold_integrity_precheck']
    print(json.dumps({'mode': mode, 'valid_gold': valid,
                      'scoring_invocation_count': len(scorer_calls), 'events': events}, sort_keys=True))
