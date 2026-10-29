#!/usr/bin/env bash
# Explicit operator-run provisioning only. Never invoked by CI.
set -euo pipefail
[[ $EUID == 0 ]] || { echo 'Run as root after reviewing this script'; exit 1; }
[[ $# == 2 && -f $1 && -f $2 ]] || { echo 'usage: provision-access.sh dev.pub prod.pub'; exit 1; }
root=$(cd -- "$(dirname -- "$0")/../.." && pwd)
install -d -m 0755 /usr/local/lib/risklive-deploy /etc/risklive-deploy
install -d -m 0700 /var/lib/risklive-deploy
install -m 0644 "$root"/scripts/deploy/*.py /usr/local/lib/risklive-deploy/
install -m 0644 "$root/scripts/release/preflight.py" /usr/local/lib/risklive-deploy/preflight.py
for env in dev prod; do
  user="risklive-deploy-$env"
  id "$user" >/dev/null 2>&1 || useradd --create-home --shell /bin/sh "$user"
  # No docker group, shell-capable sudo, PTYs, forwarding, or user-controlled code.
  install -d -m 0700 -o root -g root "/home/$user/.ssh"
  pub=$1; [[ $env == prod ]] && pub=$2
  [[ $(wc -l < "$pub") == 1 ]] || { echo 'Exactly one public key required'; exit 1; }
  printf 'restrict,command="/usr/bin/python3 /usr/local/lib/risklive-deploy/ssh_gate.py %s" %s\n' "$env" "$(cat "$pub")" > "/home/$user/.ssh/authorized_keys"
  chmod 0600 "/home/$user/.ssh/authorized_keys"
  # Separate copied entrypoints preserve the filename-based environment constraint.
  install -m 0755 "$root/scripts/deploy/dispatch.py" "/usr/local/sbin/risklive-deploy-$env"
  # Entry point imports exclusively root-owned modules.
  sed -i '/import sys/a sys.path.insert(0, "/usr/local/lib/risklive-deploy")' "/usr/local/sbin/risklive-deploy-$env"
  verbs='start, update, stop, redeploy, status'
  [[ $env == prod ]] && verbs='plan, deploy, rollback, status'
  python3 - "$env" "$user" "$verbs" <<'PY'
import sys
from pathlib import Path
name,user,verbs=sys.argv[1:]
commands=', '.join('/usr/local/sbin/risklive-deploy-'+name+' '+v.strip() for v in verbs.split(','))
Path('/etc/sudoers.d/'+user).write_text(user+' ALL=(root) NOPASSWD: '+commands+'\n')
PY
  chmod 0440 "/etc/sudoers.d/$user"
  visudo -cf "/etc/sudoers.d/$user"
done
