import importlib.util
from pathlib import Path
import sys
import unittest
import tempfile
import json
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

    def test_rollback_plan_resolves_verified_release(self):
        candidate = {'release_id': 'old', 'source': {'revision': 'a'*40}, 'images': {}}
        current = {'candidate': candidate, 'config_revision': 'b'*40}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'releases').mkdir()
            (root/'active.json').write_text(json.dumps(current))
            (root/'releases/old.json').write_text(json.dumps({**current, 'verified': True}))
            policy = {'state_dir': tmp, 'config_revision': 'b'*40}
            with patch.object(prod, 'plan', return_value=([], {}, {})) as check, patch.object(prod, 'candidate_identity', return_value='identity'):
                result = prod.handle('plan', {'release_id': 'old'}, policy)
                self.assertEqual(result['release_id'], 'old')
                self.assertEqual(check.call_args.args[0], candidate)

    def test_plan_rejects_unapproved_initial_cutover(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(prod, 'plan', return_value=([], {}, {})):
                with self.assertRaisesRegex(ValueError, 'Initial cutover'):
                    prod.handle('plan', {'candidate': {}}, {'state_dir': tmp})

    def test_plan_rejects_incompatible_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = {'candidate': {'source': {'revision': 'a'*40}}, 'config_revision': 'b'*40}
            (Path(tmp)/'active.json').write_text(json.dumps(old))
            with patch.object(prod, 'plan', return_value=([], {}, {})):
                with self.assertRaisesRegex(ValueError, 'compatibility'):
                    prod.handle('plan', {'candidate': {'source': {'revision': 'c'*40}}}, {'state_dir': tmp, 'config_revision': 'b'*40})

    def test_failed_health_detected(self):
        with patch.object(prod.time, 'monotonic', side_effect=[0, 200]):
            self.assertFalse(prod.health([], {}, timeout=1))


if __name__ == '__main__':
    unittest.main()
