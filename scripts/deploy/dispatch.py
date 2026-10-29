#!/usr/bin/env python3
"""Root-owned deployment entrypoint. JSON protocol only; no shell evaluation."""
import fcntl
import json
import os
from pathlib import Path
import sys


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
    info = policy_path.stat()
    if info.st_uid != 0 or info.st_mode & 0o022:
        raise ValueError('Deployment policy must be root-owned and not writable by others')
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
        result = module.handle(verb, request, policy)
        print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('DEPLOYMENT BLOCKED: ' + str(error), file=sys.stderr)
        sys.exit(1)
