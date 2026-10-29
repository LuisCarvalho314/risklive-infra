#!/usr/bin/env bash
# Explicit operator-run provisioning only. Never invoked by CI.
set -euo pipefail
[[ $EUID == 0 ]] || { echo 'Run as root after reviewing this script'; exit 1; }
[[ $# == 3 && -f $1 && -f $2 && -f $3 ]] || { echo 'usage: provision-access.sh dev.pub prod.pub prod-plan.pub'; exit 1; }
# Validate the interpreter before any account or filesystem provisioning.
[[ -x /usr/local/bin/python3 ]] || { echo 'SETUP REQUIRED: root-owned Python >=3.11 at /usr/local/bin/python3'; exit 1; }
/usr/local/bin/python3 - <<'PYVERIFY'
import os, pathlib, sys
if sys.version_info < (3,11):
    raise SystemExit('SETUP REQUIRED: Python >=3.11')
p=pathlib.Path('/usr/local/bin/python3').resolve()
for item in (p,*p.parents):
    st=item.stat()
    if st.st_uid != 0 or st.st_mode & 0o022:
        raise SystemExit('SETUP REQUIRED: root-owned interpreter and non-writable ancestors')
PYVERIFY
root=$(cd -- "$(dirname -- "$0")/../.." && pwd)
install -d -m 0755 /usr/local/lib/risklive-deploy /etc/risklive-deploy
install -d -m 0700 /var/lib/risklive-deploy
install -m 0644 "$root"/scripts/deploy/*.py /usr/local/lib/risklive-deploy/
install -m 0644 "$root/scripts/release/preflight.py" /usr/local/lib/risklive-deploy/preflight.py
for env in dev prod prod-plan; do
  user="risklive-deploy-$env"
  id "$user" >/dev/null 2>&1 || useradd --create-home --shell /bin/sh "$user"
  # No docker group, shell-capable sudo, PTYs, forwarding, or user-controlled code.
  install -d -m 0700 -o root -g root "/home/$user/.ssh"
  pub=$1; [[ $env == prod ]] && pub=$2; [[ $env == prod-plan ]] && pub=$3
  [[ $(wc -l < "$pub") == 1 ]] || { echo 'Exactly one public key required'; exit 1; }
  printf 'restrict,command="/usr/local/bin/python3 /usr/local/lib/risklive-deploy/ssh_gate.py %s" %s\n' "$env" "$(cat "$pub")" > "/home/$user/.ssh/authorized_keys"
  chmod 0600 "/home/$user/.ssh/authorized_keys"
  # Separate copied entrypoints preserve the filename-based environment constraint.
  target_env=$env; [[ $env == prod-plan ]] && target_env=prod
  install -m 0755 "$root/scripts/deploy/dispatch.py" "/usr/local/sbin/risklive-deploy-$target_env"
  sed -i '1c#!/usr/local/bin/python3' "/usr/local/sbin/risklive-deploy-$target_env"
  # Entry point imports exclusively root-owned modules.
  sed -i '/import sys/a sys.path.insert(0, "/usr/local/lib/risklive-deploy")' "/usr/local/sbin/risklive-deploy-$target_env"
  verbs='start, update, stop, redeploy, status'
  [[ $env == prod ]] && verbs='plan, deploy, rollback, status'
  [[ $env == prod-plan ]] && verbs='plan, status'
  python3 - "$target_env" "$user" "$verbs" <<'PY'
import sys
from pathlib import Path
name,user,verbs=sys.argv[1:]
commands=', '.join('/usr/local/sbin/risklive-deploy-'+name+' '+v.strip() for v in verbs.split(','))
Path('/etc/sudoers.d/'+user).write_text(user+' ALL=(root) NOPASSWD: '+commands+'\n')
PY
  chmod 0440 "/etc/sudoers.d/$user"
  visudo -cf "/etc/sudoers.d/$user"
done
