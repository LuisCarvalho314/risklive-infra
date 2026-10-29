import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('recovery', Path(__file__).resolve().parents[2] / 'scripts/backup/recovery.py')
r = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(r)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / 'source.db'
        self.db = sqlite3.connect(self.source)
        self.addCleanup(self.db.close)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE evidence (value TEXT)')
        self.db.execute("INSERT INTO evidence VALUES ('committed WAL value')")
        self.db.commit()
        self.config = self.base / 'config.json'
        self.entries = [{'name': 'state.db', 'kind': 'sqlite', 'source': str(self.source)}]

    def backup(self):
        self.config.write_text(json.dumps({'entries': self.entries, 'exclusions': ['runtime transient locks']}))
        return r.snapshot(self.config, self.base / 'backups')

    def test_live_wal_snapshot_restores_committed_values(self):
        self.db.execute("INSERT INTO evidence VALUES ('uncommitted')")
        snapshot = self.backup()
        restored = r.validate(snapshot, self.base / 'restore')
        with sqlite3.connect(restored / 'state.db') as db:
            self.assertEqual(db.execute('SELECT * FROM evidence').fetchall(), [('committed WAL value',)])
        self.assertEqual((snapshot.stat().st_mode & 0o777), 0o700)
        self.assertEqual(((snapshot / 'state.db').stat().st_mode & 0o777), 0o600)
        self.assertEqual(json.loads((restored / 'restore-validation.json').read_text())['status'], 'structural-restore-verified')

    def test_corrupt_snapshot_rejected(self):
        snapshot = self.backup()
        (snapshot / 'state.db').write_bytes(b'bad')
        with self.assertRaises(ValueError): r.validate(snapshot, self.base / 'restore')

    def test_symlink_source_rejected(self):
        link = self.base / 'alias.db'; link.symlink_to(self.source)
        self.entries[0]['source'] = str(link)
        with self.assertRaises(ValueError): self.backup()

    def test_secrets_rejected(self):
        self.entries[0]['secret'] = True
        with self.assertRaises(ValueError): self.backup()

    def test_mutable_file_rejected(self):
        self.entries[0]['kind'] = 'stable-file'
        with self.assertRaises(ValueError): self.backup()

    def test_restore_never_overwrites_existing_directory(self):
        snapshot = self.backup()
        with self.assertRaises(ValueError): r.validate(snapshot, self.base)

    def test_manifest_traversal_rejected(self):
        snapshot = self.backup()
        path = snapshot / 'manifest.json'; m = json.loads(path.read_text())
        m['files'][0]['name'] = '../source.db'; path.write_text(json.dumps(m))
        with self.assertRaises(ValueError): r.validate(snapshot, self.base / 'restore')

    def test_retention_is_configurable_non_destructive(self):
        first = self.backup(); second = self.backup()
        plan = r.retention(self.base / 'backups', 1)
        self.assertEqual(len(plan['deletion_candidates']), 1)
        self.assertTrue(first.exists() and second.exists())
        with self.assertRaises(ValueError): r.retention(self.base / 'backups', 0)

    def test_unexpected_file_rejected(self):
        snapshot = self.backup(); (snapshot / 'extra').write_text('unexpected')
        with self.assertRaises(ValueError): r.validate(snapshot, self.base / 'restore')


if __name__ == '__main__': unittest.main()
