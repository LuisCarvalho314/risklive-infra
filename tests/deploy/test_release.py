import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('release_contract', Path(__file__).parents[2] / 'scripts/deploy/release.py')
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


def candidate():
    return {'schema_version': 1, 'release_id': 'sha-' + 'a' * 40,
            'source': {'repository': 'LuisCarvalho314/risklive', 'revision': 'a' * 40, 'seca_revision': 'b' * 40},
            'images': {'app': 'ghcr.io/luiscarvalho314/risklive-app@sha256:' + 'c' * 64,
                       'web': 'ghcr.io/luiscarvalho314/risklive-web@sha256:' + 'd' * 64},
            'ci': {'conclusion': 'success', 'run_id': '123', 'run_url': 'https://github.com/LuisCarvalho314/risklive/actions/runs/123'},
            'state': {'compatibility': 'sqlite-v1'}}


class ReleaseContractTests(unittest.TestCase):
    def test_successful_candidate_and_identity(self):
        c = candidate()
        self.assertEqual(release.validate_candidate(c), c)
        self.assertEqual(release.candidate_identity(c), release.candidate_identity(json.loads(json.dumps(c))))
        changed = copy.deepcopy(c)
        changed['images']['app'] = changed['images']['app'][:-1] + '0'
        self.assertNotEqual(release.candidate_identity(c), release.candidate_identity(changed))

    def test_reject_missing_digest_and_wrong_registry(self):
        for ref in ('ghcr.io/luiscarvalho314/risklive-app:latest', 'ghcr.io/other/risklive-app@sha256:' + 'a' * 64, None):
            c = candidate()
            c['images']['app'] = ref
            with self.assertRaisesRegex(ValueError, 'digest'):
                release.validate_candidate(c)

    def test_reject_unsuccessful_ci_and_wrong_run(self):
        c = candidate()
        c['ci']['conclusion'] = 'failure'
        with self.assertRaisesRegex(ValueError, 'Successful CI'):
            release.validate_candidate(c)
        c = candidate()
        c['ci']['run_url'] += '0'
        with self.assertRaisesRegex(ValueError, 'URL'):
            release.validate_candidate(c)

    def test_reject_unsafe_record_names(self):
        for name in ('../x', 'a/b', '-x', '', 'x\n'):
            c = candidate()
            c['release_id'] = name
            with self.assertRaises(ValueError):
                release.validate_candidate(c)

    def test_immutable_record_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as root:
            c = candidate()
            release.record_candidate(root, c)
            release.record_candidate(root, c)
            c['state']['compatibility'] = 'another'
            with self.assertRaisesRegex(ValueError, 'Immutable'):
                release.record_candidate(root, c)

    def test_development_results_bind_exact_candidate_and_config(self):
        c = candidate()
        evidence = {'candidate_identity': release.candidate_identity(c), 'config_revision': 'e' * 40,
                    'healthy': True, 'integration_passed': True}
        release.validate_dev_evidence(c, evidence, 'e' * 40)
        for field, value in [('candidate_identity', '0' * 64), ('healthy', False), ('integration_passed', False), ('config_revision', 'HEAD')]:
            bad = dict(evidence, **{field: value})
            with self.assertRaises(ValueError):
                release.validate_dev_evidence(c, bad, 'e' * 40)

    def test_atomic_pointer_preserves_previous_record(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'dev/active.json'
            release.atomic_json(path, {'release_id': 'first'})
            release.record_once(Path(root) / 'history/first.json', {'release_id': 'first'})
            release.atomic_json(path, {'release_id': 'second'})
            self.assertEqual(json.loads(path.read_text())['release_id'], 'second')
            self.assertEqual(json.loads((Path(root) / 'history/first.json').read_text())['release_id'], 'first')


if __name__ == '__main__':
    unittest.main()
