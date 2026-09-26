"""Independent gold integrity tests, no production imports or scoring."""
from copy import deepcopy
import csv
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    'd2_v021_normative_gate', ROOT/'evaluation/d2/dev_numeric_self_consistency_v0_2_1.py')
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


class GoldIntegrityTests(unittest.TestCase):
    def test_all_17_and_nf004(self):
        result = gate.validate_dev()
        self.assertEqual((result['total'], result['passed'], result['failed']), (17, 17, 0))
        nf004 = next(r for r in result['targets'] if r['target_id'] == 'NF004')
        self.assertEqual(nf004['display_value'], '56.0')
        self.assertEqual(nf004['result'], 'PASS')

    def test_inconsistent_metadata_fails(self):
        gold_path, meta_path = [ROOT/p for p in gate.SOURCES]
        with gold_path.open() as stream:
            gold = next(r for r in csv.DictReader(stream) if r['fact_id'] == 'NF004')
        with meta_path.open() as stream:
            meta = next(r for r in csv.DictReader(stream) if r['gold_target_id'] == 'NF004')
        bad = deepcopy(meta)
        bad['precision_rule_json'] = bad['precision_rule_json'].replace('"comparison_gold_value":"0.56"', '"comparison_gold_value":"0.57"')
        self.assertNotEqual(bad, meta)
        with self.assertRaisesRegex(ValueError, 'canonical display disagreement'):
            gate.check_target(gold, bad)

    def test_witness_must_satisfy_every_applicable_constraint(self):
        valid = [{'reference': '37', 'mode': 'EXACT'},
                 {'reference': '37', 'mode': 'QUANTUM', 'parameter': '10'}]
        self.assertTrue(gate.satisfies('37', valid))
        self.assertFalse(gate.satisfies('38', valid))
        invalid = valid + [{'reference': '50', 'mode': 'QUANTUM', 'parameter': '10'}]
        self.assertFalse(gate.satisfies('37', invalid))

    def test_primitive_domain_and_half_even(self):
        with self.assertRaises(ValueError):
            gate.matches('37', '37', 'QUANTUM', '0.03')
        self.assertTrue(gate.matches('1.25', '1.23', 'QUANTUM', '0.1'))
        self.assertFalse(gate.matches('1.35', '1.23', 'QUANTUM', '0.1'))


if __name__ == '__main__':
    unittest.main()
