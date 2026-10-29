"""Offline lifecycle tests: no Docker daemon, paid APIs or production writes."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts/deploy'))
import dev
from release import candidate_identity

INTEGRATION_CHECKS = dev.integration_checks


def candidate():
    return {'schema_version': 1, 'release_id': 'candidate-123',
            'source': {'repository': 'LuisCarvalho314/risklive', 'revision': 'a' * 40, 'seca_revision': 'b' * 40},
            'images': {role: 'ghcr.io/luiscarvalho314/risklive-' + role + '@sha256:' + 'c' * 64
                       for role in ('app', 'web')},
            'ci': {'conclusion': 'success', 'run_id': '123',
                   'run_url': 'https://github.com/LuisCarvalho314/risklive/actions/runs/123'},
            'state': {'compatibility': 'sqlite-v1'}}


class DevelopmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.data = self.root / 'dev-data'
        self.data.mkdir()
        (self.data / '.risklive-development').touch()
        self.state = self.root / 'state'
        self.policy = {'app_root': str(self.root / 'app'), 'state_dir': str(self.state),
                       'data_root': str(self.data), 'config_revision': 'd' * 40,
                       'app_revision': 'e' * 40}
        self.request = {'candidate': candidate(), 'config_revision': 'd' * 40,
                        'operator': 'tester', 'run_url': 'https://github.com/example/run'}
        self.patches = [patch.object(dev, 'DATA_ROOT', self.data),
                        patch.object(dev, 'app_config', return_value=self.root / 'app'),
                        patch.object(dev, 'compose_config', return_value={}),
                        patch.object(dev, 'pull_candidate'), patch.object(dev, 'run', return_value='abc'),
                        patch.object(dev, 'integration_checks', return_value={'healthy': True, 'integration_passed': True})]
        self.mocks = [p.start() for p in self.patches]

    def tearDown(self):
        for patcher in reversed(self.patches):
            patcher.stop()
        self.tmp.cleanup()

    def test_update_does_not_wake_stopped_environment(self):
        result = dev.handle('update', {}, self.policy)
        self.assertEqual(result['reason'], 'development-disabled')
        self.mocks[4].assert_not_called()
        self.mocks[3].assert_not_called()

    def test_successful_start_records_exact_candidate(self):
        result = dev.handle('start', self.request, self.policy)
        self.assertTrue(result['enabled'])
        self.assertEqual(result['candidate']['images'], candidate()['images'])
        evidence = json.loads((self.state / 'results' / (candidate_identity(candidate()) + '.json')).read_text())
        self.assertTrue(evidence['healthy'] and evidence['integration_passed'])
        command = self.mocks[4].call_args.args[0]
        self.assertEqual(command[-1], 'up')
        self.assertNotIn('scheduler', command)

    def test_stop_start_preserves_database_rag_and_results(self):
        for name in ('database.sqlite', 'rag.index', 'results.json'):
            (self.data / name).write_bytes(b'preserved-state')
        dev.handle('start', self.request, self.policy)
        dev.handle('stop', self.request, self.policy)
        self.assertFalse(dev.handle('status', {}, self.policy)['enabled'])
        dev.handle('start', self.request, self.policy)
        for name in ('database.sqlite', 'rag.index', 'results.json'):
            self.assertEqual((self.data / name).read_bytes(), b'preserved-state')
        for call in self.mocks[4].call_args_list:
            self.assertNotIn('-v', call.args[0])
            self.assertNotIn('--volumes', call.args[0])

    def test_missing_digest_rejected_before_pull(self):
        self.request['candidate']['images']['app'] = 'risklive:latest'
        with self.assertRaisesRegex(ValueError, 'digest'):
            dev.handle('start', self.request, self.policy)
        self.mocks[3].assert_not_called()

    def test_unsuccessful_ci_rejected(self):
        self.request['candidate']['ci']['conclusion'] = 'failure'
        with self.assertRaisesRegex(ValueError, 'Successful CI'):
            dev.handle('start', self.request, self.policy)
        self.mocks[3].assert_not_called()

    def test_failed_health_does_not_record_success_or_enable(self):
        self.mocks[5].side_effect = ValueError('health failure')
        with self.assertRaisesRegex(ValueError, 'health failure'):
            dev.handle('start', self.request, self.policy)
        self.assertFalse((self.state / 'active.json').exists())
        self.assertFalse(dev.handle('status', {}, self.policy)['enabled'])
        evidence = json.loads((self.state / 'results' / (candidate_identity(candidate()) + '.json')).read_text())
        self.assertFalse(evidence['healthy'])

    def test_update_with_stopped_containers_skips(self):
        dev.handle('start', self.request, self.policy)
        self.mocks[4].return_value = ''
        self.mocks[3].reset_mock()
        result = dev.handle('update', self.request, self.policy)
        self.assertEqual(result['reason'], 'development-not-running')
        self.mocks[3].assert_not_called()

    def test_clean_environment_excludes_production_paths_and_profile(self):
        env = dev.safe_env(self.data, 'candidate-123')
        self.assertNotIn('APP_ENV_FILE', env)
        self.assertNotIn('COMPOSE_PROFILES', env)
        self.assertNotIn('COMPOSE_FILE', env)
        self.assertEqual(env['RISKLIVE_DEV_DATA_DIR'], str(self.data))

    def test_scheduler_running_rejected(self):
        container = {'Config': {'Labels': {'com.docker.compose.service': 'scheduler'}},
                     'State': {'Running': True}}
        self.mocks[4].side_effect = ['scheduler-id', json.dumps([container])]
        with self.assertRaisesRegex(ValueError, 'Unexpected'):
            INTEGRATION_CHECKS({}, candidate())

    def test_paid_api_enabled_rejected(self):
        containers = self.containers()
        containers[0]['Config']['Env'] = ['RISKLIVE_EXTERNAL_APIS_ENABLED=true', 'DISABLE_SCHEDULER=true']
        self.mocks[4].side_effect = ['ids', json.dumps(containers), json.dumps([{'Id': 'app-id'}])]
        with self.assertRaisesRegex(ValueError, 'External APIs'):
            INTEGRATION_CHECKS({}, candidate())

    def test_failed_container_health_rejected(self):
        containers = self.containers()
        containers[0]['State']['Health']['Status'] = 'unhealthy'
        self.mocks[4].side_effect = ['ids', json.dumps(containers)]
        with self.assertRaisesRegex(ValueError, 'Unhealthy'):
            INTEGRATION_CHECKS({}, candidate())

    def containers(self):
        return [{'Config': {'Labels': {'com.docker.compose.service': role},
                            'Env': ['RISKLIVE_EXTERNAL_APIS_ENABLED=false', 'DISABLE_SCHEDULER=true']},
                 'Image': role + '-id', 'State': {'Running': True, 'Health': {'Status': 'healthy'}},
                 'Mounts': []} for role in ('app', 'web', 'caddy')]

    def test_live_api_operation_not_allowed(self):
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            dev.handle('live-test', self.request, self.policy)


if __name__ == '__main__':
    unittest.main()
