import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.request import Request
import zipfile

sys.path.insert(0, str(Path(__file__).parents[2] / 'scripts/deploy'))
import fetch_candidate as fetcher
from test_release import candidate


def artifact(value):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr('candidate.json', json.dumps(value))
    return stream.getvalue()


def good_run():
    return {'status': 'completed', 'conclusion': 'success', 'path': '.github/workflows/ci.yml',
            'event': 'push', 'head_branch': 'develop', 'head_repository': {'full_name': 'LuisCarvalho314/risklive'},
            'head_sha': 'a' * 40}


class FetchCandidateTests(unittest.TestCase):
    def fetch(self, run=None, value=None, artifacts=None):
        responses = [run if run is not None else good_run(),
                     {'artifacts': artifacts if artifacts is not None else [{'name': 'risklive-candidate', 'expired': False, 'id': 42}]},
                     artifact(value if value is not None else candidate())]
        with patch.object(fetcher, 'get', side_effect=responses):
            return fetcher.fetch('123', ['develop'])

    def test_fetch_verified_exact_candidate(self):
        self.assertEqual(self.fetch(), candidate())

    def test_reject_untrusted_pr_failed_ci_wrong_workflow_or_repository(self):
        for field, value in [('event', 'pull_request'), ('conclusion', 'failure'),
                             ('head_branch', 'fork'), ('path', '.github/workflows/other.yml'),
                             ('head_repository', {'full_name': 'attacker/risklive'})]:
            run = good_run()
            run[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'trusted CI'):
                self.fetch(run=run)

    def test_reject_different_exact_source(self):
        run = good_run()
        run['head_sha'] = 'b' * 40
        with self.assertRaisesRegex(ValueError, 'revision/run'):
            self.fetch(run=run)

    def test_reject_candidate_of_another_successful_run(self):
        value = candidate()
        value['ci']['run_id'] = '124'
        value['ci']['run_url'] = value['ci']['run_url'][:-3] + '124'
        with self.assertRaisesRegex(ValueError, 'revision/run'):
            self.fetch(value=value)

    def test_reject_missing_or_expired_artifact(self):
        for artifacts in ([], [{'name': 'risklive-candidate', 'expired': True, 'id': 42}]):
            with self.assertRaisesRegex(ValueError, 'unexpired'):
                self.fetch(artifacts=artifacts)

    def test_redirect_drops_bearer_credential(self):
        request = Request('https://api.github.com/artifact', headers={'Authorization': 'Bearer synthetic'})
        redirected = fetcher.SafeRedirect().redirect_request(request, None, 302, 'Found', {}, 'https://blob.example/artifact.zip')
        self.assertIsNone(redirected.get_header('Authorization'))


if __name__ == '__main__':
    unittest.main()
