#!/usr/bin/env python3
"""Explicit-file snapshots; never discovers or schedules production data."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import tarfile
import tempfile
import time
import uuid


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def regular(path):
    path = Path(path)
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('absolute non-symlink path required')
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError('regular file required')
    return path


def sqlite_check(path):
    with sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True) as db:
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('SQLite integrity check failed')
        if db.execute('PRAGMA foreign_key_check').fetchone() is not None:
            raise ValueError('SQLite foreign key check failed')


def snapshot(config_path, root):
    config = json.loads(Path(config_path).read_text())
    entries = config['entries']
    if not entries or not isinstance(config.get('exclusions'), list):
        raise ValueError('explicit entries and exclusions inventory required')
    if any(e.get('secret', False) for e in entries):
        raise ValueError('secrets require external secret-store recovery; never stage them here')
    root = Path(root).absolute()
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError('symlink destination forbidden')
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.stat().st_mode & 0o077:
        raise ValueError('backup root must have mode 0700')
    target = root / ('snapshot-' + dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex)
    target.mkdir(mode=0o700)
    manifest = {'version': 1, 'status': 'snapshot-complete-not-restore-verified',
                'created_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                'consistency': 'per-file; no cross-database or database/files transaction guaranteed',
                'exclusions': config['exclusions'], 'files': []}
    try:
        names = set()
        for entry in entries:
            name = entry['name']
            if not name or name in ('.', '..') or '/' in name or '\\' in name or name in names or name in ('manifest.json', 'restore-validation.json'):
                raise ValueError('invalid or duplicate entry name')
            names.add(name)
            source = regular(entry['source'])
            if source.is_relative_to(root):
                raise ValueError('source cannot be inside backup root')
            output = target / name
            original = source.stat()
            if entry['kind'] == 'sqlite':
                deadline = time.monotonic() + float(config.get('sqlite_timeout_seconds', 60))
                def progress(status, remaining, total):
                    if time.monotonic() > deadline:
                        raise TimeoutError('SQLite backup deadline exceeded')
                with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=5) as src:
                    with sqlite3.connect(output) as dst:
                        src.backup(dst, pages=256, progress=progress, sleep=0.05)
                        dst.execute('PRAGMA journal_mode=DELETE')
                sqlite_check(output)
            elif entry['kind'] == 'stable-file':
                if entry.get('consistency_basis') not in ('immutable', 'application-export'):
                    raise ValueError('live files require immutable files or application-consistent exports')
                shutil.copyfile(source, output)
                after = source.stat()
                if (original.st_ino, original.st_size, original.st_mtime_ns, original.st_ctime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                    raise ValueError('source changed while copying')
            else:
                raise ValueError('unsupported entry kind')
            output.chmod(0o600)
            with output.open('rb') as synced:
                os.fsync(synced.fileno())
            manifest['files'].append({'name': name, 'kind': entry['kind'], 'sha256': digest(output),
                                      'size': output.stat().st_size,
                                      'original_uid': original.st_uid, 'original_gid': original.st_gid,
                                      'original_mode': stat.S_IMODE(original.st_mode)})
        write_json(target / 'manifest.json', manifest)
        for directory in (target, root):
            fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try: os.fsync(fd)
            finally: os.close(fd)
        return target
    except BaseException:
        # Incomplete snapshots deliberately have no completed manifest.
        raise


def write_json(path, value):
    with path.open('x', encoding='utf-8') as out:
        os.chmod(path, 0o600)
        json.dump(value, out, indent=2)
        out.write('\n')
        out.flush()
        os.fsync(out.fileno())


def validate(folder, restore_dir):
    folder = Path(folder).absolute()
    regular(folder / 'manifest.json')
    manifest = json.loads((folder / 'manifest.json').read_text())
    if manifest.get('version') != 1 or manifest.get('status') != 'snapshot-complete-not-restore-verified' or not manifest.get('files'):
        raise ValueError('invalid manifest')
    expected = {'manifest.json'}
    for item in manifest['files']:
        name = item['name']
        if Path(name).name != name or name in ('.', '..') or name in expected:
            raise ValueError('unsafe manifest path')
        expected.add(name)
        source = regular(folder / name)
        if source.stat().st_size != item['size'] or digest(source) != item['sha256']:
            raise ValueError('checksum mismatch')
        if item['kind'] not in ('sqlite', 'stable-file'):
            raise ValueError('unknown snapshot kind')
    if {p.name for p in folder.iterdir()} != expected:
        raise ValueError('unexpected snapshot files')
    restore_dir = Path(restore_dir).absolute()
    if any(p.is_symlink() for p in (restore_dir, *restore_dir.parents)) or restore_dir.exists():
        raise ValueError('restore validation requires a NEW non-symlink directory')
    restore_dir.mkdir(mode=0o700)
    for item in manifest['files']:
        restored = restore_dir / item['name']
        shutil.copyfile(folder / item['name'], restored)
        restored.chmod(0o600)
        if digest(restored) != item['sha256']:
            raise ValueError('restored checksum mismatch')
        if item['kind'] == 'sqlite':
            sqlite_check(restored)
    # This receipt is evidence of structural restoration, not application acceptance.
    write_json(restore_dir / 'restore-validation.json', {
        'status': 'structural-restore-verified', 'manifest_sha256': digest(folder / 'manifest.json'),
        'validated_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'limitations': 'Application semantics, cross-file consistency and full recovery require an isolated application drill.'})
    return restore_dir


def seal(folder, output, recipients):
    # Validate before encrypting; age receives only a stream, no plaintext tar on disk.
    with tempfile.TemporaryDirectory(prefix='risklive-verify-') as temp:
        validate(folder, Path(temp) / 'restore')
    output = Path(output).absolute()
    if not recipients or any(p.is_symlink() for p in (output.parent, *output.parent.parents)):
        raise ValueError('recipients and non-symlink output required')
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            proc = subprocess.Popen(['age', *[v for r in recipients for v in ('-r', r)]], stdin=subprocess.PIPE, stdout=stream)
            try:
                with tarfile.open(fileobj=proc.stdin, mode='w|') as archive:
                    for path in sorted(Path(folder).iterdir()):
                        regular(path.absolute())
                        archive.add(path, arcname=path.name, recursive=False)
                proc.stdin.close()
                if proc.wait() != 0:
                    raise RuntimeError('age failed')
                stream.flush()
                os.fsync(stream.fileno())
            except BaseException:
                proc.kill()
                proc.wait()
                raise
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return {'encrypted_file': str(output), 'sha256': digest(output), 'offhost_recovery_verified': False}


def retention(root, keep):
    """Prune completed snapshots only after a verified off-host successor exists.

    This tool intentionally emits a plan only: off-host recoverability cannot be
    inferred from local checksums or a local age encryption command.
    """
    if keep < 1:
        raise ValueError('keep must be at least one')
    root = Path(root).absolute()
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError('symlink root forbidden')
    snapshots = []
    for child in root.iterdir():
        if child.name.startswith('snapshot-') and child.is_dir() and not child.is_symlink():
            manifest = child / 'manifest.json'
            if manifest.is_file() and not manifest.is_symlink():
                data = json.loads(manifest.read_text())
                if data.get('status') == 'snapshot-complete-not-restore-verified':
                    snapshots.append((data['created_at'], str(child)))
    snapshots.sort(reverse=True)
    return {'keep_count': keep, 'retain': [p for _, p in snapshots[:keep]],
            'deletion_candidates': [p for _, p in snapshots[keep:]],
            'deleted': [], 'approval_required': 'Confirm independently restorable off-host copy before manual deletion; incomplete directories excluded.'}


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('snapshot'); p.add_argument('config'); p.add_argument('root')
    p = sub.add_parser('validate'); p.add_argument('snapshot'); p.add_argument('new_restore_directory')
    p = sub.add_parser('retention-plan'); p.add_argument('root'); p.add_argument('--keep', type=int, required=True)
    p = sub.add_parser('seal'); p.add_argument('snapshot'); p.add_argument('output'); p.add_argument('--recipient', action='append', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'snapshot': print(snapshot(args.config, args.root))
        elif args.command == 'validate': print(validate(args.snapshot, args.new_restore_directory))
        elif args.command == 'retention-plan': print(json.dumps(retention(args.root, args.keep), indent=2))
        else: print(json.dumps(seal(args.snapshot, args.output, args.recipient)))
    except (ValueError, OSError, KeyError, sqlite3.Error, RuntimeError) as exc:
        parser.exit(1, f'{type(exc).__name__}: backup operation failed; inspect privately\n')


if __name__ == '__main__':
    main()
