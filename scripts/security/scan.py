#!/usr/bin/env python3
"""Redacted offline checks of infrastructure index or all local Git blob objects."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

MAX_BYTES = 2_000_000
RULES = {
    'provider-token': re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16})\b'),
    'private-key': re.compile(rb'-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----'),
    'connection-secret': re.compile(rb'(?i)(?:AccountKey|SharedAccessSignature|SharedAccessKey)\s*=\s*[^;\s\'"]{12,}'),
    'password-hash': re.compile(rb'\$2[aby]\$[0-9]{2}\$[./A-Za-z0-9]{53}'),
}
ASSIGNMENT = re.compile(rb'(?im)^\s*(?:export\s+)?([A-Z][A-Z0-9_]*(?:KEY|SECRET|TOKEN|PASSWORD)[A-Z0-9_]*)\s*=\s*([^\r\n]*)')
FORBIDDEN = re.compile(r'(?i)(?:^|/)(?:\.env(?:\..*)?|[^/]+\.(?:sqlite3?|db|tar|tgz|age|pem|key)|(?:logs|runtime|backups)/.*)$')


def findings(data):
    result = [name for name, regex in RULES.items() if regex.search(data)]
    for match in ASSIGNMENT.finditer(data):
        value = match[2].strip().strip(b'\'"')
        if value and value not in (b'replace_me', b'example', b'changeme') and not value.startswith((b'${', b'$')):
            result.append('non-placeholder-secret-assignment')
            break
    return sorted(set(result))


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.PIPE)


def scan(repo, history=False):
    """Never return source bytes or matching values. History includes dangling blobs."""
    records = []
    if history:
        entries = git(repo, 'cat-file', '--batch-all-objects', '--batch-check=%(objectname) %(objecttype) %(objectsize)').splitlines()
        objects = [(x.split()[0].decode(), int(x.split()[2])) for x in entries if x.split()[1] == b'blob']
        for oid, size in objects:
            rules = ['oversized-object-review-required'] if size > MAX_BYTES else findings(git(repo, 'cat-file', 'blob', oid))
            if rules:
                records.append({'object': oid, 'rules': rules})
    else:
        for entry in filter(None, git(repo, 'ls-files', '--stage', '-z').split(b'\0')):
            meta, path_bytes = entry.split(b'\t', 1)
            mode, oid, stage = meta.split()
            path = path_bytes.decode('utf-8', 'replace')
            rules = []
            if stage != b'0' or mode not in (b'100644', b'100755'):
                rules.append('unsafe-index-entry')
            if FORBIDDEN.search(path) and not path.endswith('.example'):
                rules.append('sensitive-artifact-path')
            size = int(git(repo, 'cat-file', '-s', oid.decode()))
            rules.extend(['oversized-object-review-required'] if size > MAX_BYTES else findings(git(repo, 'cat-file', 'blob', oid.decode())))
            if rules:
                records.append({'path': path, 'rules': sorted(set(rules))})
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parent.parent.parent)
    parser.add_argument('--history', action='store_true', help='Scan every local blob, including unreachable objects')
    args = parser.parse_args()
    records = scan(args.repo, args.history)
    print(json.dumps({'scope': 'all-local-blobs' if args.history else 'index', 'findings': records}, indent=2))
    return bool(records)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print('Security scan could not complete: ' + type(error).__name__, file=sys.stderr)
        sys.exit(2)
