#!/usr/bin/env python3
"""Root-owned deployment entrypoint. JSON protocol only; no shell evaluation."""
import fcntl
import json
import os
from pathlib import Path
import sys
import time
import uuid


def main():
    environment = Path(sys.argv[0]).name.rsplit('-', 1)[-1]
    if environment not in {'dev', 'prod'} or len(sys.argv) != 2:
        raise ValueError('Invoke installed risklive-deploy-dev|prod with one operation')
    allowed = {'dev': {'start', 'update', 'stop', 'redeploy', 'status'},
               'prod': {'plan', 'deploy', 'rollback', 'status'}}
    verb = sys.argv[1]
    if verb not in allowed[environment]:
        raise ValueError('Operation not allowed')
    os.umask(0o077)
    policy_path = Path('/etc/risklive-deploy') / (environment + '.json')
    if policy_path.resolve() != policy_path:
        raise ValueError('Deployment policy must not traverse symlinks')
    for path in (policy_path, *policy_path.parents):
        info = path.stat()
        if info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('Deployment policy and ancestors must be root-owned and not writable by others')
    policy = json.loads(policy_path.read_text())
    payload = sys.stdin.buffer.read(1024 * 1024 + 1)
    if len(payload) > 1024 * 1024:
        raise ValueError('Request too large')
    request = json.loads(payload or b'{}')
    lock = Path('/var/lib/risklive-deploy/deployment.lock')
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Conflicting deployment is already running') from None
        module = __import__(environment)
        from release import record_once
        event = {'environment': environment, 'operation': verb,
                 'operator': request.get('operator'), 'run_url': request.get('run_url'),
                 'config_revision': request.get('config_revision'),
                 'at_epoch': int(time.time())}
        # Only audit allowlisted provenance, never the request body or secrets.
        audit = Path('/var/lib/risklive-deploy/audit')
        record_once(audit / (str(time.time_ns()) + '-' + uuid.uuid4().hex + '.json'),
                    dict(event, status='started'))
        try:
            result = module.handle(verb, request, policy)
        except Exception:
            record_once(audit / (str(time.time_ns()) + '-' + uuid.uuid4().hex + '.json'),
                        dict(event, status='failed'))
            raise
        record_once(audit / (str(time.time_ns()) + '-' + uuid.uuid4().hex + '.json'),
                    dict(event, status='completed'))
        print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('DEPLOYMENT BLOCKED: ' + str(error), file=sys.stderr)
        sys.exit(1)
