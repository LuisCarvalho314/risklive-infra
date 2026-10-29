import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('security_scan', Path(__file__).resolve().parents[2] / 'scripts/security/scan.py')
scan = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scan)


class SecurityScanTests(unittest.TestCase):
    def test_tokens_are_redacted(self):
        value = b'ghp_' + b'A' * 30
        self.assertEqual(scan.findings(value), ['provider-token'])
        self.assertNotIn(value.decode(), str(scan.findings(value)))

    def test_placeholder_and_expansion(self):
        self.assertEqual(scan.findings(b'API_TOKEN=replace_me\nOTHER_SECRET=${SECRET_FROM_VAULT}\n'), [])
        self.assertIn('non-placeholder-secret-assignment', scan.findings(b'API_TOKEN=' + b'a' * 16))

    def test_hash_and_connection(self):
        self.assertIn('password-hash', scan.findings(b'$2b$' + b'12$' + b'A' * 53))
        self.assertIn('connection-secret', scan.findings(b'Account' + b'Key=' + b'A' * 30))

    def test_index_and_dangling_blob(self):
        with tempfile.TemporaryDirectory() as root:
            def git(*args, data=None):
                return subprocess.check_output(['git', '-C', root, *args], input=data, stderr=subprocess.DEVNULL)
            git('init', '-q')
            Path(root, 'safe.md').write_text('placeholder only')
            git('add', 'safe.md')
            self.assertEqual(scan.scan(Path(root)), [])
            secret = b'ghp_' + b'B' * 30
            oid = git('hash-object', '-w', '--stdin', data=secret).decode().strip()
            result = scan.scan(Path(root), history=True)
            self.assertEqual(result, [{'object': oid, 'rules': ['provider-token']}])
            self.assertNotIn(secret.decode(), str(result))

    def test_sensitive_index_path(self):
        with tempfile.TemporaryDirectory() as root:
            subprocess.run(['git', '-C', root, 'init', '-q'], check=True)
            Path(root, 'state.sqlite').write_text('synthetic fixture')
            subprocess.run(['git', '-C', root, 'add', 'state.sqlite'], check=True)
            self.assertEqual(scan.scan(Path(root))[0]['rules'], ['sensitive-artifact-path'])


if __name__ == '__main__':
    unittest.main()
