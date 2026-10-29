#!/usr/bin/env python3
"""Read-only release plan. Never creates containers or reads environment contents."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

SHA = re.compile(r'[0-9a-f]{40}\Z')
DIGEST = re.compile(r'[a-z0-9][a-z0-9.:-]*/[a-z0-9._/-]+@sha256:[0-9a-f]{64}\Z')
IMAGE_ID = re.compile(r'sha256:[0-9a-f]{64}\Z')
PLATFORM = re.compile(r'linux/(?:amd64|arm64)(?:/v[0-9]+)?\Z')
SERVICES = {'app', 'scheduler', 'web', 'caddy'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(value):
    p = Path(value)
    require(p.is_absolute() and p.resolve() == p, 'Noncanonical or symlink path: ' + str(p))
    return p


def file_hash(data):
    return hashlib.sha256(data).hexdigest()


def config_hash(config):
    return file_hash(json.dumps(config, sort_keys=True, separators=(',', ':')).encode())


def run(args, **kwargs):
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, **kwargs)
    require(result.returncode == 0, 'Read-only command failed: ' + ' '.join(args[:3]) + ' (details suppressed to protect environment)')
    return result.stdout


def resolve_config(release, repo):
    d = release.get('deployment')
    require(isinstance(d, dict), 'Historical inventory only: deployment definition is missing')
    require(d.get('status') == 'verified', 'Deployment definition is not verified')
    require(SHA.fullmatch(d['revision']), 'Deployment needs full application revision')
    require(d['revision'] == release['production']['images']['app']['provenance']['source_revision'], 'Application/config revision mismatch')
    root = canonical(str(repo))
    files = d['files_sha256']
    require(files and d['compose_files'], 'Pinned Compose file inventory is missing')
    require(set(d['compose_files']).issubset(files), 'Compose file is not hashed')
    for name, digest in files.items():
        p = Path(name)
        require(not p.is_absolute() and '..' not in p.parts, 'Unsafe pinned path')
        path = canonical(str(root / p))
        pinned = run(['git', '--no-optional-locks', '-C', str(root), 'show', d['revision'] + ':' + name])
        require(file_hash(pinned) == digest, 'Pinned Git hash mismatch: ' + name)
        require(path.is_file() and file_hash(path.read_bytes()) == digest, 'Checkout config drift: ' + name)
    return d, root


def render(d, root, settings):
    require(all(isinstance(k, str) and isinstance(v, str) for k, v in settings.items()), 'Settings must be string values')
    env = {k: os.environ[k] for k in ('PATH', 'HOME', 'LANG', 'TMPDIR') if k in os.environ}
    env.update(settings)
    # No automatic .env discovery, service env resolution or Docker daemon access.
    args = ['docker', 'compose', '--env-file', '/dev/null', '--project-name', settings['COMPOSE_PROJECT_NAME']]
    for name in d['compose_files']:
        args.extend(['-f', str(root / name)])
    args.extend(['--profile', '*', 'config', '--no-env-resolution', '--format', 'json'])
    return json.loads(run(args, env=env, cwd=root))


def check_model(release, d, config, settings):
    prod = release['production']
    require(PLATFORM.fullmatch(d.get('platform', '')), 'Unsupported deployment platform')
    require(set(prod['images']) == SERVICES, 'Unexpected image inventory')
    require(settings['COMPOSE_PROJECT_NAME'] == release['project'] == 'risklive-prod', 'Production project identity mismatch')
    require(config.get('name') == release['project'], 'Rendered Compose project mismatch')
    require(set(config['services']) == SERVICES, 'Unexpected service inventory')
    require(config_hash(config) == d['rendered_config_sha256'], 'Rendered model differs from previously reviewed configuration')
    data = canonical(prod['data_root'])
    require(data.is_dir(), 'Persistent data root missing')
    require(set(prod['environment_files']) == {'app', 'web', 'caddy'}, 'Environment path inventory mismatch')
    for role, name in prod['environment_files'].items():
        path = canonical(name)
        require(path.is_file(), 'Environment file missing: ' + name)
        require(settings.get(role.upper() + '_ENV_FILE') == name, 'Settings environment path drift: ' + role)
    require(prod['images']['scheduler'] == prod['images']['app'], 'App/scheduler image records differ')
    expected_volumes = set(prod['named_volumes'])
    require(set(v['name'] for v in config.get('volumes', {}).values()) == expected_volumes, 'Named volume inventory mismatch')
    require(config['networks']['internal']['name'] == prod['network'], 'Production network mismatch')
    for name, svc in config['services'].items():
        image = prod['images'][name]
        provenance = image['provenance']
        require(IMAGE_ID.fullmatch(image.get('local_image_id', '')), 'Invalid observed local image identity: ' + name)
        require(bool(image.get('reference')) and ':latest' not in image['reference'], 'Invalid observed image reference: ' + name)
        registry = provenance.get('registry')
        require(registry and registry.get('verification') == 'retrieved-and-tested', 'Verified registry recovery required: ' + name)
        reference = registry['reference']
        require(DIGEST.fullmatch(reference), 'Immutable image reference required: ' + name)
        require(svc.get('image') == reference, 'Rendered image reference mismatch: ' + name)
        require(registry.get('platform') == d['platform'] == provenance.get('platform'), 'Image platform mismatch: ' + name)
        require(provenance.get('source_revision') == registry.get('source_revision'), 'Outer provenance source mismatch: ' + name)
        require(provenance.get('source_revision') is None or SHA.fullmatch(provenance['source_revision']), 'Invalid provenance source revision: ' + name)
        require(registry.get('digest') == reference.split('@')[1], 'Registry digest mismatch: ' + name)
        if name in ('app', 'scheduler', 'web'):
            require(registry.get('source_revision') == d['revision'], 'Backend/frontend release revision mismatch: ' + name)
        require(not svc.get('build') and not svc.get('container_name'), 'Build or fixed container name forbidden: ' + name)
        require(not svc.get('privileged') and not svc.get('network_mode') and not svc.get('pid'), 'Unsafe host access: ' + name)
        require(set(svc.get('networks', {})) == {'internal'}, 'Service network mismatch: ' + name)
        envs = svc.get('env_file', [])
        paths = [v['path'] if isinstance(v, dict) else v for v in envs]
        require(paths == [prod['environment_files']['app' if name == 'scheduler' else name]], 'Service environment path mismatch: ' + name)
        mounts = svc.get('volumes', [])
        volumes = {m['target']: m for m in mounts}
        require(len(volumes) == len(mounts), 'Duplicate mount target')
        if name == 'caddy':
            require(set(volumes) == {'/etc/caddy/Caddyfile', '/data', '/config'}, 'Caddy mount targets mismatch')
            caddy = canonical(str(Path(d['checkout']) / d['caddy_file']))
            require(d['caddy_file'] in d['files_sha256'], 'Caddy configuration must be pinned')
            require(volumes['/etc/caddy/Caddyfile'].get('type') == 'bind' and volumes['/etc/caddy/Caddyfile']['source'] == str(caddy) and volumes['/etc/caddy/Caddyfile'].get('read_only'), 'Caddy bind mismatch')
            for target, logical in (('/data', 'caddy_data'), ('/config', 'caddy_config')):
                require(volumes[target].get('type') == 'volume' and volumes[target]['source'] == logical, 'Caddy volume mismatch')
            host, port = prod['http_bind'].rsplit(':', 1)
            ports = svc.get('ports', [])
            require(len(ports) == 1 and ports[0].get('host_ip') == host and str(ports[0].get('published')) == port and ports[0].get('target') == 80 and ports[0].get('protocol', 'tcp') == 'tcp', 'Production ingress mismatch')
        else:
            require(not svc.get('ports'), 'Unexpected published service port: ' + name)
            parts = ['results', 'logs'] + (['runtime'] if name != 'web' else [])
            require(set(volumes) == {'/app/' + p for p in parts}, 'Persistent mount inventory mismatch: ' + name)
            for part in parts:
                mount = volumes['/app/' + part]
                path = canonical(str(data / part))
                require(path.is_dir(), 'Persistent mount missing: ' + str(path))
                require(mount.get('type') == 'bind' and mount.get('source') == str(path), 'Persistent mount source mismatch: ' + name)
                require(mount.get('read_only', False) == (name == 'web'), 'Persistent mount permissions mismatch: ' + name)
    return ['Project: ' + release['project'], 'Revision: ' + d['revision'], 'Ingress: ' + prod['http_bind'],
            'Configuration and immutable images match reviewed release.', 'Persistent mounts and environment paths exist (contents not read).',
            'DRY RUN ONLY: no Docker daemon changes; no deployment authorization implied.']


def preflight(release, repo, settings):
    d, root = resolve_config(release, repo)
    require(str(root) == d['checkout'], 'Authoritative checkout path mismatch')
    return check_model(release, d, render(d, root, settings), settings)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path('release.json'))
    parser.add_argument('--repository', type=Path, required=True)
    parser.add_argument('--settings-json', type=Path, required=True, help='Non-secret Compose interpolation settings')
    parser.add_argument('--dry-run', action='store_true', help='Explicit plan mode (all invocations are read-only)')
    args = parser.parse_args()
    try:
        for line in preflight(json.loads(args.manifest.read_text()), args.repository, json.loads(args.settings_json.read_text())):
            print(line)
        return 0
    except (ValueError, KeyError, TypeError, OSError) as error:
        print('PREFLIGHT BLOCKED: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
