import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/deploy'))
sys.path.insert(0, str(ROOT / 'scripts/release'))
import prod
import ssh_gate


class ProductionTests(unittest.TestCase):
    def test_ssh_only_fixed_operations(self):
        self.assertEqual(ssh_gate.command('prod', 'deploy')[-1], 'deploy')
        for value in ('deploy; id', 'deploy x', 'start', '$(id)', ''):
            with self.assertRaises(ValueError):
                ssh_gate.command('prod', value)

    def test_compatibility_is_reviewed_directionally(self):
        a = {'source': {'revision': 'a'*40}, 'state': {'compatibility': 'same'}}
        b = {'source': {'revision': 'b'*40}, 'state': {'compatibility': 'same'}}
        self.assertFalse(prod.compatible(a, b, {}))
        self.assertTrue(prod.compatible(a, b, {'compatible_transitions': [['a'*40, 'b'*40]]}))
        self.assertFalse(prod.compatible(b, a, {'compatible_transitions': [['a'*40, 'b'*40]]}))

    def test_duplicate_scheduler_rejected(self):
        with patch.object(prod, 'run', return_value='one two'):
            with self.assertRaises(Exception):
                prod.scheduler_inventory()

    def test_failed_health_detected(self):
        with patch.object(prod.time, 'monotonic', side_effect=[0, 200]):
            self.assertFalse(prod.health([], {}, timeout=1))


if __name__ == '__main__':
    unittest.main()
