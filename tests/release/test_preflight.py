import copy
import importlib.util
from pathlib import Path
import tempfile
import subprocess
import unittest

spec = importlib.util.spec_from_file_location('preflight', Path(__file__).resolve().parents[2] / 'scripts/release/preflight.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve()
        for part in ('results', 'logs', 'runtime'):
            (root / part).mkdir()
        env = {}
        for role in ('app', 'web', 'caddy'):
            path = root / (role + '.env')
            path.write_text('DO_NOT_READ=synthetic')
            env[role] = str(path)
        digest = 'sha256:' + 'a' * 64
        rev = 'b' * 40
        self.d = {'checkout': str(root), 'caddy_file': 'Caddyfile', 'files_sha256': {'Caddyfile': 'unused'}, 'revision': rev, 'platform': 'linux/amd64'}
        self.r = {'project': 'risklive-prod', 'production': {'data_root': str(root), 'environment_files': env, 'named_volumes': ['risklive-prod_caddy_data', 'risklive-prod_caddy_config'], 'network': 'risklive-prod_internal', 'http_bind': '0.0.0.0:8888', 'images': {}}}
        self.s = {'COMPOSE_PROJECT_NAME': 'risklive-prod', **{k.upper() + '_ENV_FILE': v for k, v in env.items()}}
        self.c = {'name': 'risklive-prod', 'services': {}, 'networks': {'internal': {'name': 'risklive-prod_internal'}}, 'volumes': {k: {'name': 'risklive-prod_' + k} for k in ('caddy_data', 'caddy_config')}}
        for name in p.SERVICES:
            ref = 'ghcr.io/example/' + ('app' if name == 'scheduler' else name) + '@' + digest
            self.r['production']['images'][name] = {'reference': ref, 'local_image_id': digest, 'provenance': {'platform': 'linux/amd64', 'source_revision': rev, 'registry': {'reference': ref, 'digest': digest, 'platform': 'linux/amd64', 'source_revision': rev, 'verification': 'retrieved-and-tested'}}}
            svc = {'image': ref, 'networks': {'internal': {}}, 'env_file': [{'path': env['app' if name == 'scheduler' else name]}]}
            if name == 'caddy':
                svc['ports'] = [{'host_ip': '0.0.0.0', 'published': '8888', 'target': 80}]
                svc['volumes'] = [{'type': 'bind', 'source': str(root / 'Caddyfile'), 'target': '/etc/caddy/Caddyfile', 'read_only': True}] + [{'type': 'volume', 'source': k, 'target': v} for k, v in (('caddy_data', '/data'), ('caddy_config', '/config'))]
            else:
                svc['volumes'] = [{'type': 'bind', 'source': str(root / part), 'target': '/app/' + part, 'read_only': name == 'web'} for part in ['results', 'logs'] + (['runtime'] if name != 'web' else [])]
            self.c['services'][name] = svc
        self.rehash()

    def rehash(self):
        self.d['rendered_config_sha256'] = p.config_hash(self.c)

    def check(self):
        return p.check_model(self.r, self.d, self.c, self.s)

    def test_valid_synthetic_release(self):
        self.assertIn('DRY RUN ONLY', self.check()[-1])

    def test_git_and_worktree_hashes(self):
        root = Path(self.tmp.name)
        subprocess.run(['git', 'init', '-q', str(root)], check=True)
        path = root / 'compose.yml'
        path.write_text('services: {}')
        subprocess.run(['git', '-C', str(root), 'add', 'compose.yml'], check=True)
        subprocess.run(['git', '-C', str(root), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture'], check=True)
        rev = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
        self.r['deployment'] = {'status': 'verified', 'revision': rev, 'compose_files': ['compose.yml'], 'files_sha256': {'compose.yml': p.file_hash(path.read_bytes())}}
        self.r['production']['images']['app']['provenance']['source_revision'] = rev
        p.resolve_config(self.r, root)
        path.write_text('drift')
        with self.assertRaisesRegex(ValueError, 'Checkout config drift'):
            p.resolve_config(self.r, root)

    def test_historical_inventory_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Historical inventory'):
            p.resolve_config(self.r, Path(self.tmp.name))

    def test_unreviewed_config_change(self):
        self.c['services']['app']['command'] = ['unexpected']
        with self.assertRaisesRegex(ValueError, 'previously reviewed'):
            self.check()

    def test_semantic_drift_rejected_even_if_rehashed(self):
        cases = [lambda: self.c['services']['web'].update(ports=[{'published': '9999'}]),
                 lambda: self.c['services']['app']['volumes'][0].update(source='/tmp'),
                 lambda: self.c['services']['app'].update(privileged=True),
                 lambda: self.c['services']['caddy']['ports'][0].update(published='80'),
                 lambda: self.c['services']['scheduler'].update(env_file=[{'path': '/tmp/incorrect.env'}])]
        original = copy.deepcopy(self.c)
        for mutate in cases:
            self.c = copy.deepcopy(original)
            mutate()
            self.rehash()
            with self.assertRaises(ValueError):
                self.check()

    def test_shared_runtime_semantics_reject_drift_even_with_rehashed_policy(self):
        def validate():
            p.check_runtime_model(self.c, self.r['production']['data_root'],
                                  self.r['production']['environment_files'],
                                  str(Path(self.d['checkout']) / self.d['caddy_file']),
                                  self.r['production']['http_bind'])
        validate()
        original = copy.deepcopy(self.c)
        mutations = [
            lambda: self.c['services']['app']['volumes'][0].update(source='/tmp/rehashed'),
            lambda: self.c['services']['web']['volumes'][0].update(read_only=False),
            lambda: self.c['services']['app'].update(privileged=True),
            lambda: self.c['services']['scheduler'].update(network_mode='host'),
            lambda: self.c['services']['caddy']['volumes'][0].update(read_only=False),
            lambda: self.c['volumes']['caddy_data'].update(name='another-project-data'),
            lambda: self.c['services']['web'].update(ports=[{'published':'8188','target':3000}]),
        ]
        for mutate in mutations:
            self.c = copy.deepcopy(original)
            mutate()
            self.rehash()
            with self.assertRaises(ValueError):
                validate()

    def test_missing_environment(self):
        Path(self.r['production']['environment_files']['web']).unlink()
        with self.assertRaisesRegex(ValueError, 'Environment file missing'):
            self.check()

    def test_tag_only_image_rejected(self):
        self.r['production']['images']['web']['provenance']['registry'] = None
        with self.assertRaisesRegex(ValueError, 'Verified registry'):
            self.check()

    def test_different_frontend_revision_rejected(self):
        self.r['production']['images']['web']['provenance']['registry']['source_revision'] = 'c' * 40
        with self.assertRaisesRegex(ValueError, 'source mismatch'):
            self.check()

    def test_full_scheduler_record_mismatch_rejected(self):
        self.r['production']['images']['scheduler']['local_image_id'] = 'sha256:' + 'c' * 64
        with self.assertRaisesRegex(ValueError, 'image records differ'):
            self.check()

    def test_outer_platform_mismatch_rejected(self):
        self.r['production']['images']['web']['provenance']['platform'] = 'linux/arm64'
        with self.assertRaisesRegex(ValueError, 'platform mismatch'):
            self.check()

    def test_unsupported_platform_rejected(self):
        self.d['platform'] = 'windows/amd64'
        with self.assertRaisesRegex(ValueError, 'Unsupported deployment platform'):
            self.check()

    def test_malformed_registry_reference_rejected(self):
        image = self.r['production']['images']['web']
        image['provenance']['registry']['reference'] = 'bad registry@sha256:' + 'a' * 64
        self.c['services']['web']['image'] = image['provenance']['registry']['reference']
        self.rehash()
        with self.assertRaisesRegex(ValueError, 'Immutable image reference'):
            self.check()

    def test_registry_digest_mismatch_rejected(self):
        self.r['production']['images']['web']['provenance']['registry']['digest'] = 'sha256:' + 'c' * 64
        with self.assertRaisesRegex(ValueError, 'Registry digest mismatch'):
            self.check()

    def test_symlink_env_rejected(self):
        path = Path(self.r['production']['environment_files']['web'])
        path.unlink()
        path.symlink_to(Path(self.r['production']['environment_files']['app']))
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.check()


if __name__ == '__main__':
    unittest.main()
