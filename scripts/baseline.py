#!/usr/bin/env python3
"""Read-only baseline checks. Never invoke build, pull, run, up, down or restart."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    '.gitignore', '.githooks/pre-commit', 'README.md', 'release.json',
    'docs/discovery.md', 'docs/reconstruction.md', 'docs/verification.md',
    'hosts/jarvis/deployment.env.example', 'hosts/jarvis/app.env.example',
    'hosts/jarvis/web.env.example', 'hosts/jarvis/compose.override.yml',
    'scripts/baseline.py', 'scripts/inspect-live.sh',
}

# Reviewed hardening paths are optional on independent implementation branches.
ALLOWED = REQUIRED | {
    'docs/security/audit.md',
    'scripts/security/scan.py',
    'tests/security/test_scan.py',
    'scripts/images/validate.py',
    'tests/images/test_images.py',
    'docs/images/recovery.md',
    'scripts/backup/recovery.py',
    'tests/backup/test_recovery.py',
    'docs/backup/recovery.md',
    'scripts/release/preflight.py',
    'tests/release/test_preflight.py',
    'docs/deployment/release-management.md',
    'docs/deployment/rollback.md',
    'docs/cicd/architecture.md',
    'docs/cicd/promotion.md',
    'docs/cicd/candidate-build.yml.example',
    'tests/integration/test_hygiene.py',
    'docs/integration/report.md',
}



def require(condition, message):
    if not condition:
        raise ValueError(message)


def command(args, **kwargs):
    return subprocess.check_output(args, **kwargs)


def hygiene(staged=False):
    entries = command(['git', '-C', str(ROOT), 'ls-files', '--stage', '-z']).split(b'\0')
    files = {}
    for entry in filter(None, entries):
        meta, name = entry.split(b'\t', 1)
        mode, oid, stage = meta.split()
        name = name.decode()
        require(mode in (b'100644', b'100755') and stage == b'0', 'Unsafe index entry: ' + name)
        require(name in ALLOWED, 'Unapproved tracked path: ' + name)
        if staged:
            files[name] = command(['git', '-C', str(ROOT), 'cat-file', 'blob', oid.decode()])
        else:
            path = ROOT / name
            require(not any(p.is_symlink() for p in (path, *path.parents)), 'Symlink forbidden: ' + name)
            files[name] = path.read_bytes()
    require(REQUIRED.issubset(files), 'Baseline files missing from worktree/index')
    credential = re.compile(r'\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})')
    assignment = re.compile(r'^\s*(?:export\s+)?([A-Z][A-Z0-9_]*(?:KEY|SECRET|TOKEN|PASSWORD|HASH)[A-Z0-9_]*)\s*=\s*(.*?)\s*$', re.M)
    for name, data in files.items():
        require(len(data) < 200000 and b'\0' not in data, 'Binary/oversized content: ' + name)
        content = data.decode('utf-8')
        require(not credential.search(content), 'Possible credential in ' + name)
        require(not re.search(r'-----BEGIN [A-Z ]*PRIVATE KEY-----', content), 'Private key in ' + name)
        for match in assignment.finditer(content):
            value = match.group(2).strip('\"\'')
            require(value in ('', 'replace_me'), 'Non-placeholder credential assignment in ' + name)
    release = json.loads(files['release.json'])
    require(release['schema_version'] == 1, 'Unknown release schema')
    for source in release['sources'].values():
        require(re.fullmatch(r'[0-9a-f]{40}', source['revision']), 'Unpinned source revision')
        require(all(re.fullmatch(r'[0-9a-f]{64}', h) for h in source['files_sha256'].values()), 'Invalid source hash')
    for image in release['production']['images'].values():
        require(':latest' not in image['reference'], 'Floating production tag')
        require(re.fullmatch(r'sha256:[0-9a-f]{64}', image['local_image_id']), 'Missing production image identity')
    print('Staged content checks passed.' if staged else 'Infrastructure content checks passed.')
    return release


def settings(path):
    values = {}
    for line in path.read_text().splitlines():
        if line.strip() and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            require(re.fullmatch(r'[A-Z_]+', key) is not None, 'Invalid settings key')
            require(key not in values and '$' not in value and '\n' not in value, 'Invalid setting: ' + key)
            values[key] = value
    return values


def check_sources(release, values):
    roots = {
        'production': values['RISKLIVE_PRODUCTION_CHECKOUT'],
        'caddy': values['RISKLIVE_CADDY_CHECKOUT'],
        'development': values['RISKLIVE_DEVELOPMENT_CHECKOUT'],
    }
    for name, root in roots.items():
        require(Path(root).is_absolute(), 'Source path must be absolute')
        source = release['sources'][name]
        for relative, digest in source['files_sha256'].items():
            pinned = command(['git', '--no-optional-locks', '-C', root, 'show', source['revision'] + ':' + relative])
            path = Path(root) / relative
            require(not path.is_symlink(), 'Symlinked application config: ' + str(path))
            require(hashlib.sha256(pinned).hexdigest() == digest, 'Git source mismatch: ' + relative)
            require(hashlib.sha256(path.read_bytes()).hexdigest() == digest, 'Working config drift: ' + str(path))
    expected_caddy = str(Path(roots['caddy']) / 'deployment/caddy/Caddyfile.prod')
    require(values['RISKLIVE_CADDY_FILE'] == expected_caddy, 'Unexpected Caddy path')
    print('Pinned application configuration matches Git and on-disk files.')


def compose(files, values):
    # Ignore inherited Compose settings and automatic .env discovery. Do not read
    # service env files: config output must never expand production credentials.
    environment = {k: os.environ[k] for k in ('PATH', 'HOME', 'LANG', 'TMPDIR') if k in os.environ}
    environment.update(values)
    args = ['docker', 'compose', '--env-file', '/dev/null', '--project-name', values['COMPOSE_PROJECT_NAME']]
    for path in files:
        args += ['-f', str(path)]
    args += ['--profile', '*', 'config', '--no-env-resolution', '--format', 'json']
    return json.loads(command(args, env=environment, cwd=ROOT))


def check_config(release, values, emit):
    require(values['COMPOSE_PROJECT_NAME'] == release['project'], 'Production project drift')
    for key in ('RISKLIVE_DATA_DIR', 'APP_ENV_FILE', 'WEB_ENV_FILE', 'CADDY_ENV_FILE', 'RISKLIVE_DEV_DATA_DIR'):
        require(Path(values[key]).is_absolute() and Path(values[key]).resolve() == Path(values[key]), 'Noncanonical path: ' + key)
    prod_root = Path(values['RISKLIVE_DATA_DIR'])
    dev_root = Path(values['RISKLIVE_DEV_DATA_DIR'])
    require(not dev_root.is_relative_to(prod_root) and not prod_root.is_relative_to(dev_root), 'Overlapping persistent roots')
    for root in (prod_root, dev_root):
        for checkout in (ROOT, Path(values['RISKLIVE_PRODUCTION_CHECKOUT']), Path(values['RISKLIVE_DEVELOPMENT_CHECKOUT'])):
            require(not root.is_relative_to(checkout) and not checkout.is_relative_to(root), 'State and checkout overlap')
    source = Path(values['RISKLIVE_PRODUCTION_CHECKOUT'])
    production = compose([source / 'deployment/compose/docker-compose.prod.yml', ROOT / 'hosts/jarvis/compose.override.yml'], values)
    require(set(production['services']) == {'app', 'scheduler', 'web', 'caddy'}, 'Unexpected production services')
    require(production['name'] == release['project'], 'Production project mismatch')
    for name, service in production['services'].items():
        require(service['image'] == release['production']['images'][name]['reference'], 'Image drift: ' + name)
        require(set(service['networks']) == {'internal'}, 'Network drift: ' + name)
        require(not service.get('build'), 'Application build configuration forbidden')
        require(not service.get('container_name'), 'Unexpected fixed container name')
        volumes = {v['target']: v for v in service.get('volumes', [])}
        if name != 'caddy':
            require(not service.get('ports'), 'Unexpected public service port: ' + name)
            expected = ['results', 'logs'] + (['runtime'] if name in ('app', 'scheduler') else [])
            require(set(volumes) == {'/app/' + p for p in expected}, 'Unexpected mounts: ' + name)
            for part in expected:
                mount = volumes['/app/' + part]
                require(mount['type'] == 'bind' and mount['source'] == str(prod_root / part), 'Mount source drift')
                require(mount.get('read_only', False) == (name == 'web'), 'Mount permissions drift')
        else:
            ports = service['ports']
            require(len(ports) == 1 and ports[0]['target'] == 80 and str(ports[0]['published']) == '8888' and ports[0]['host_ip'] == '0.0.0.0', 'Production ingress drift')
            require(set(volumes) == {'/etc/caddy/Caddyfile', '/data', '/config'}, 'Unexpected Caddy mounts')
            require(volumes['/etc/caddy/Caddyfile']['source'] == values['RISKLIVE_CADDY_FILE'] and volumes['/etc/caddy/Caddyfile']['read_only'], 'Caddy bind drift')
    require(production['networks']['internal']['name'] == release['production']['network'], 'Network name drift')
    for volume in ('caddy_data', 'caddy_config'):
        require(production['volumes'][volume]['name'] in release['production']['named_volumes'], 'Caddy volume drift')
    dev_values = dict(values, COMPOSE_PROJECT_NAME='risklive-dev', RISKLIVE_DATA_DIR=str(dev_root),
                      APP_IMAGE='risklive-dev-app:' + values['RISKLIVE_DEV_IMAGE_TAG'], WEB_IMAGE='risklive-dev-web:' + values['RISKLIVE_DEV_IMAGE_TAG'])
    for role in ('APP', 'WEB', 'CADDY'):
        dev_values[role + '_ENV_FILE'] = str(dev_root / 'env' / (role.lower() + '.env'))
    dev_source = Path(values['RISKLIVE_DEVELOPMENT_CHECKOUT'])
    dev_files = [dev_source / 'deployment/compose' / ('docker-compose.' + layer + '.yml') for layer in ('prod', 'smoke', 'dev')]
    development = compose(dev_files, dev_values)
    validator = dev_source / 'deployment/scripts/validate-dev.py'
    subprocess.run([sys.executable, '-I', str(validator), str(dev_root)], input=json.dumps(development).encode(), check=True)
    dev_values['RISKLIVE_DEV_LIVE_ENV_FILE'] = str(dev_root / 'env/live.env')
    live = compose(dev_files + [dev_source / 'deployment/compose/docker-compose.dev-live.yml'], dev_values)
    subprocess.run([sys.executable, '-I', str(validator), str(dev_root), '--live'], input=json.dumps(live).encode(), check=True)
    print('Production mounts/images/ports and upstream offline/live development checks passed (no daemon access).')
    if emit:
        print(json.dumps(production if emit == 'production' else development, indent=2))


def check_images(release, sudo):
    prefix = ['sudo', 'docker'] if sudo else ['docker']
    for image in {v['reference']: v for v in release['production']['images'].values()}.values():
        actual = command(prefix + ['image', 'inspect', '--format', '{{.Id}}', image['reference']], text=True).strip()
        require(actual == image['local_image_id'], 'Image tag no longer matches recorded ID: ' + image['reference'])
    print('All production image tags match recorded local image IDs.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--staged', action='store_true', help='Check only index blobs; used by pre-commit')
    parser.add_argument('--settings', type=Path, default=ROOT / 'hosts/jarvis/deployment.env.example')
    parser.add_argument('--emit', choices=['production', 'development'], help='Print config without expanding service env files')
    parser.add_argument('--verify-images', action='store_true', help='Additionally inspect local production image IDs')
    parser.add_argument('--sudo', action='store_true', help='Use sudo only for image inspection')
    args = parser.parse_args()
    release = hygiene(args.staged)
    if args.staged:
        return
    values = settings(args.settings)
    check_sources(release, values)
    check_config(release, values, args.emit)
    if args.verify_images:
        check_images(release, args.sudo)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError, KeyError) as error:
        print('Baseline validation failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
