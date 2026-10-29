#!/usr/bin/env python3
"""Unprivileged forced SSH command. Forward stdin to a fixed sudo operation."""
import os
import re
import subprocess
import sys


def command(environment, original):
    allowed = {'dev': {'start', 'update', 'stop', 'redeploy', 'status'},
               'prod': {'plan', 'deploy', 'rollback', 'status'},
               'prod-plan': {'plan', 'status'}}
    if environment not in allowed or original not in allowed[environment]:
        raise ValueError('Only an allowlisted deployment operation is accepted')
    if environment == 'prod-plan':
        environment = 'prod'
    return ['/usr/bin/sudo', '-n', '/usr/local/sbin/risklive-deploy-' + environment, original]


if __name__ == '__main__':
    try:
        sys.exit(subprocess.call(command(sys.argv[1], os.environ.get('SSH_ORIGINAL_COMMAND', ''))))
    except (ValueError, IndexError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
