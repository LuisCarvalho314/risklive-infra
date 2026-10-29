import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('baseline_hygiene', ROOT / 'scripts/baseline.py')
b = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(b)


class HygieneTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        for name in b.REQUIRED:
            dest = self.root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, dest)
        self.git('add', '.')
        original = b.ROOT
        b.ROOT = self.root
        self.addCleanup(setattr, b, 'ROOT', original)

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_optional_implementation_paths_can_be_absent(self):
        self.assertEqual(b.hygiene(True)['schema_version'], 1)

    def test_unknown_indexed_path_rejected(self):
        (self.root / 'unexpected.txt').write_text('synthetic')
        self.git('add', '-f', 'unexpected.txt')
        with self.assertRaisesRegex(ValueError, 'Unapproved tracked path'):
            b.hygiene(True)

    def test_missing_required_file_rejected(self):
        self.git('rm', 'README.md')
        with self.assertRaisesRegex(ValueError, 'Baseline files missing'):
            b.hygiene(True)

    def test_worktree_symlink_rejected(self):
        path = self.root / 'README.md'
        path.unlink()
        path.symlink_to('/dev/null')
        with self.assertRaisesRegex(ValueError, 'Symlink forbidden'):
            b.hygiene(False)

    def test_hook_uses_index_scanner(self):
        scanner = self.root / 'scripts/security/scan.py'
        scanner.parent.mkdir()
        scanner.write_text('import sys\nsys.exit(1)\n')
        self.git('add', 'scripts/security/scan.py')
        scanner.write_text('import sys\nsys.exit(0)\n')
        result = subprocess.run(['sh', '.githooks/pre-commit'], cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'Staged content checks passed', result.stdout)


if __name__ == '__main__':
    unittest.main()
