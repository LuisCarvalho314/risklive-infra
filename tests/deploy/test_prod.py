import importlib.util
from pathlib import Path
import sys
import unittest
import tempfile
import json
from unittest.mock import patch, mock_open
from types import SimpleNamespace
import io
import hashlib
import dispatch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/deploy'))
sys.path.insert(0, str(ROOT / 'scripts/release'))
import prod
import ssh_gate


class ProductionTests(unittest.TestCase):
    def test_ssh_only_fixed_operations(self):
        self.assertEqual(ssh_gate.command('prod', 'deploy')[-1], 'deploy')
        self.assertEqual(ssh_gate.command('prod-plan', 'plan')[-1], 'plan')
        with self.assertRaises(ValueError):
            ssh_gate.command('prod-plan', 'deploy')
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

    def rollout_fixture(self, root, reverse=True):
        old = {'release_id': 'old', 'source': {'revision': 'a'*40}, 'images': {'app': 'old-app', 'web': 'old-web'}}
        new = {'release_id': 'new', 'source': {'revision': 'b'*40}, 'images': {'app': 'new-app', 'web': 'new-web'}}
        active = {'candidate': old, 'config_revision': 'c'*40, 'verified': True}
        (root/'active.json').write_text(json.dumps(active))
        pairs = [['a'*40, 'b'*40]]
        if reverse:
            pairs.append(['b'*40, 'a'*40])
        policy = {'state_dir': str(root), 'config_revision': 'c'*40, 'compatible_transitions': pairs}
        request = {'candidate': new, 'config_revision': 'c'*40, 'operator': 'operator', 'run_url': 'https://github.com/run'}
        return active, new, policy, request

    def test_successful_rollout_retains_previous_and_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old, new, policy, request = self.rollout_fixture(root)
            with patch.object(prod, 'plan', return_value=(['docker','compose'], {}, {})), patch.object(prod, 'verify_images'), patch.object(prod, 'run', return_value=''), patch.object(prod, 'health', return_value=True), patch.object(prod, 'scheduler_inventory'):
                result = prod.handle('deploy', request, policy)
            self.assertTrue(result['verified'])
            self.assertEqual(json.loads((root/'previous.json').read_text()), old)
            self.assertEqual(json.loads((root/'active.json').read_text())['candidate'], new)
            history = root/'releases/new.json'
            original = history.read_bytes()
            self.assertEqual(json.loads(original)['candidate'], new)
            self.assertEqual(len(list((root/'events').glob('*.json'))), 2)
            # Status is read-only and does not mutate immutable release history.
            prod.handle('status', {}, policy)
            self.assertEqual(history.read_bytes(), original)

    def test_failed_health_rolls_back_compatible_images_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old, new, policy, request = self.rollout_fixture(root)
            with patch.object(prod, 'plan', return_value=(['docker','compose'], {}, {})), patch.object(prod, 'compose', return_value=(['docker','compose'], {}, {})), patch.object(prod, 'verify_images') as images, patch.object(prod, 'run', return_value='') as commands, patch.object(prod, 'health', side_effect=[False, True]):
                with self.assertRaisesRegex(ValueError, 'health checks'):
                    prod.handle('deploy', request, policy)
            self.assertEqual(images.call_count, 2)
            self.assertEqual(commands.call_count, 2)
            self.assertEqual(json.loads((root/'active.json').read_text()), old)
            self.assertFalse((root/'releases/new.json').exists())
            event_text = ''.join(x.read_text() for x in (root/'events').glob('*.json'))
            self.assertIn('health-failed-image-rollback-succeeded', event_text)
            for call in commands.call_args_list:
                self.assertNotIn('down', call.args[0])
                self.assertNotIn('-v', call.args[0])
                self.assertNotIn('restore', ' '.join(call.args[0]))

    def test_unknown_reverse_compatibility_never_restores_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old, new, policy, request = self.rollout_fixture(root, reverse=False)
            with patch.object(prod, 'plan', return_value=(['docker','compose'], {}, {})), patch.object(prod, 'verify_images') as images, patch.object(prod, 'compose') as rollback, patch.object(prod, 'run', return_value='') as commands, patch.object(prod, 'health', return_value=False):
                with self.assertRaisesRegex(ValueError, 'health checks'):
                    prod.handle('deploy', request, policy)
            rollback.assert_not_called()
            self.assertEqual(images.call_count, 1)
            self.assertEqual(commands.call_count, 1)
            self.assertEqual(json.loads((root/'active.json').read_text()), old)
            self.assertIn('health-failed-no-compatible-rollback', ''.join(x.read_text() for x in (root/'events').glob('*.json')))
            self.assertFalse(any('restore' in ' '.join(call.args[0]) for call in commands.call_args_list))

    def test_production_path_change_rejected_before_mutation(self):
        policy = {'app_root': '/opt/config', 'app_revision': 'a'*40, 'settings': {'COMPOSE_PROJECT_NAME': 'risklive-prod', 'RISKLIVE_DATA_DIR': '/tmp/changed-production'}}
        with patch.object(prod, 'trusted', return_value=Path('/opt/config')), patch.object(prod, 'run', return_value='a'*40) as commands:
            with self.assertRaisesRegex(ValueError, 'data root changed'):
                prod.compose(policy, {'images': {'app': 'app@digest', 'web': 'web@digest'}})
        self.assertEqual(commands.call_count, 1)
        self.assertEqual(commands.call_args.args[0][0], 'git')

    def test_mount_drift_rejected_before_docker_mutation(self):
        candidate = {'images': {'app': 'app@digest', 'web': 'web@digest'}}
        model = {'name': 'risklive-prod', 'services': {role: {'image': candidate['images']['web' if role == 'web' else 'app']} for role in ('app','scheduler','web','caddy')}}
        model['services']['app']['volumes'] = [{'source': '/tmp/unsafe', 'target': '/app/runtime'}]
        policy = {'app_root': '/opt/config', 'app_revision': 'a'*40, 'settings': {'COMPOSE_PROJECT_NAME': 'risklive-prod', 'RISKLIVE_DATA_DIR': '/opt/risklive/data', 'CADDY_HTTP_BIND': '0.0.0.0:8888', **{role+'_ENV_FILE': '/opt/risklive/data/env/'+role.lower()+'.env' for role in ('APP','WEB','CADDY')}}, 'compose_files': ['compose.yml'], 'files_sha256': {'compose.yml': hashlib.sha256(b'fixture').hexdigest()}, 'reviewed_model_sha256': '0'*64}
        with patch.object(prod, 'trusted', side_effect=lambda p: Path(p)), patch.object(Path, 'is_file', return_value=True), patch.object(Path, 'is_dir', return_value=True), patch.object(Path, 'resolve', lambda self: self), patch.object(Path, 'read_bytes', return_value=b'fixture'), patch.object(prod, 'run', side_effect=['a'*40, json.dumps(model)]) as commands:
            with self.assertRaisesRegex(ValueError, 'Compose model is not reviewed'):
                prod.compose(policy, candidate)
        self.assertEqual(commands.call_count, 2)
        self.assertIn('config', commands.call_args.args[0])
        self.assertNotIn('up', commands.call_args.args[0])

    def test_dispatch_conflicting_deployment_is_rejected(self):
        fake_stdin = SimpleNamespace(buffer=io.BytesIO(b'{}'))
        stat = SimpleNamespace(st_uid=0, st_mode=0o100600)
        with patch.object(dispatch.sys, 'argv', ['/usr/local/sbin/risklive-deploy-prod', 'status']), patch.object(dispatch.sys, 'stdin', fake_stdin), patch.object(Path, 'stat', return_value=stat), patch.object(Path, 'read_text', return_value='{}'), patch.object(Path, 'mkdir'), patch.object(Path, 'open', mock_open()), patch.object(dispatch.fcntl, 'flock', side_effect=BlockingIOError):
            with self.assertRaisesRegex(ValueError, 'Conflicting deployment'):
                dispatch.main()

    def test_failed_health_detected(self):
        with patch.object(prod.time, 'monotonic', side_effect=[0, 200]):
            self.assertFalse(prod.health([], {}, timeout=1))


if __name__ == '__main__':
    unittest.main()
