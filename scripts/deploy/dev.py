#!/usr/bin/env python3
"""Restricted development controller. Uses the application's existing isolated stack.

The caller supplies a root-owned policy and holds the deployment lock. No user
supplied commands, paths, Compose options, credentials or API switches are accepted.
"""
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request
import uuid

from release import (atomic_json, candidate_identity, record_candidate, record_once,
                     validate_candidate, validate_revision)

DATA_ROOT = Path('/opt/risklive/dev-data')


def run(args, env=None):
    return subprocess.run([str(a) for a in args], env=env, check=True,
                          text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def safe_env(data_root, tag):
    # Deliberately exclude inherited Compose variables and production env paths.
    return {'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
            'HOME': '/root', 'RISKLIVE_DEV_DATA_DIR': str(data_root),
            'RISKLIVE_DEV_IMAGE_TAG': tag}


def read_json(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def trusted(path):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError('Development configuration path must be canonical')
    for part in (path, *path.parents):
        info = part.stat()
        if info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('Development executable configuration must be root-owned and not writable by others')
    return path


def app_config(policy, request):
    revision = validate_revision(request.get('config_revision'), 'configuration revision')
    if revision != policy.get('config_revision'):
        raise ValueError('Installed configuration revision differs from requested revision')
    root = trusted(policy['app_root'])
    for relative in ('deployment/scripts/dev.sh', 'deployment/scripts/validate-dev.py',
                     'deployment/compose/docker-compose.prod.yml',
                     'deployment/compose/docker-compose.smoke.yml',
                     'deployment/compose/docker-compose.dev.yml',
                     'deployment/caddy/Caddyfile.prod'):
        trusted(root / relative)
    expected = validate_revision(policy.get('app_revision'), 'installed application config revision')
    actual = run(['git', '-C', root, 'rev-parse', 'HEAD']).strip()
    if actual != expected:
        raise ValueError('Application configuration checkout revision drift')
    # Files driving privileged Docker operations must match the provisioned commit.
    if run(['git', '-C', root, 'status', '--porcelain', '--untracked-files=no', '--',
            'deployment']).strip():
        raise ValueError('Application deployment configuration has local changes')
    return root


def compose_config(root, env):
    env = dict(env, COMPOSE_PROJECT_NAME='risklive-dev', RISKLIVE_DATA_DIR=str(DATA_ROOT),
               APP_IMAGE='risklive-dev-app:' + env['RISKLIVE_DEV_IMAGE_TAG'],
               WEB_IMAGE='risklive-dev-web:' + env['RISKLIVE_DEV_IMAGE_TAG'],
               APP_ENV_FILE=str(DATA_ROOT / 'env/app.env'),
               WEB_ENV_FILE=str(DATA_ROOT / 'env/web.env'),
               CADDY_ENV_FILE=str(DATA_ROOT / 'env/caddy.env'))
    files = ['docker-compose.prod.yml', 'docker-compose.smoke.yml', 'docker-compose.dev.yml']
    args = ['docker', 'compose', '--project-name', 'risklive-dev']
    for name in files:
        args += ['-f', str(root / 'deployment/compose' / name)]
    config = json.loads(run(args + ['--profile', '*', 'config', '--format', 'json'], env))
    # Reuse the application's isolation validator as the source of truth.
    subprocess.run(['python3', '-I', str(root / 'deployment/scripts/validate-dev.py'), str(DATA_ROOT)],
                   input=json.dumps(config), text=True, check=True, env=env,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if config['services']['app']['environment'].get('DISABLE_SCHEDULER') != 'true':
        raise ValueError('Development scheduler must be disabled')
    return config


def pull_candidate(candidate, tag, env):
    for role, ref in candidate['images'].items():
        run(['docker', 'pull', ref], env)
        image = json.loads(run(['docker', 'image', 'inspect', ref], env))[0]
        if ref not in image.get('RepoDigests', []):
            raise ValueError('Pulled image digest mismatch')
        labels = image.get('Config', {}).get('Labels', {}) or {}
        if labels.get('org.opencontainers.image.revision') != candidate['source']['revision']:
            raise ValueError('Pulled image source revision mismatch')
        if labels.get('org.opencontainers.image.source') != 'https://github.com/LuisCarvalho314/risklive':
            raise ValueError('Pulled image source repository mismatch')
        if labels.get('org.risklive.seca.revision') != candidate['source']['seca_revision']:
            raise ValueError('Pulled image SECA revision mismatch')
        if candidate['source'].get('seca_v2_revision') and labels.get('org.risklive.seca-v2.revision') != candidate['source']['seca_v2_revision']:
            raise ValueError('Pulled image SECA V2 revision mismatch')
        run(['docker', 'tag', ref, 'risklive-dev-' + role + ':' + tag], env)


def integration_checks(env, candidate):
    # Check every project container, so a stray scheduler cannot hide in a profile.
    ids = run(['docker', 'ps', '-aq', '--filter', 'label=com.docker.compose.project=risklive-dev'], env).split()
    if not ids:
        raise ValueError('Development containers absent')
    containers = json.loads(run(['docker', 'inspect', *ids], env))
    running = {}
    for container in containers:
        role = container['Config']['Labels']['com.docker.compose.service']
        if container['State']['Running']:
            if role not in ('app', 'web', 'caddy') or role in running:
                raise ValueError('Unexpected or duplicate running development service')
            running[role] = container
    if set(running) != {'app', 'web', 'caddy'}:
        raise ValueError('Development serving stack incomplete')
    for role, container in running.items():
        if container['State'].get('Health', {}).get('Status') != 'healthy':
            raise ValueError('Unhealthy development service: ' + role)
        for mount in container.get('Mounts', []):
            if mount.get('RW') and not Path(mount['Source']).resolve().is_relative_to(DATA_ROOT):
                raise ValueError('Development container has writable mount outside development root')
        if role in ('app', 'web'):
            expected = json.loads(run(['docker', 'image', 'inspect', candidate['images'][role]], env))[0]['Id']
            if container['Image'] != expected:
                raise ValueError('Running development image differs from selected digest')
            values = dict(v.split('=', 1) for v in container['Config'].get('Env', []) if '=' in v)
            if values.get('RISKLIVE_EXTERNAL_APIS_ENABLED') != 'false':
                raise ValueError('External APIs enabled in development serving stack')
            if role == 'app' and values.get('DISABLE_SCHEDULER') != 'true':
                raise ValueError('Scheduler enabled in development app')
    # Fixed GET endpoints only. Never trigger scheduled jobs or paid API work.
    for endpoint in ('/healthz', '/'):
        with urllib.request.urlopen('http://127.0.0.1:8188' + endpoint, timeout=15) as response:
            if response.status != 200 or not response.read(2 * 1024 * 1024):
                raise ValueError('Development HTTP integration check failed')
    return {'healthy': True, 'integration_passed': True}


def handle(action, request, policy):
    if action not in ('start', 'update', 'stop', 'redeploy', 'status'):
        raise ValueError('Unsupported development operation')
    state = Path(policy.get('state_dir', '/var/lib/risklive-deploy/dev'))
    state.mkdir(parents=True, exist_ok=True)
    enabled = read_json(state / 'enabled.json', {'enabled': False})['enabled']
    active = read_json(state / 'active.json')
    if action == 'status':
        return {'enabled': enabled, 'active': active}
    # Automatic updates must never enable a deliberately stopped environment.
    if action == 'update' and not enabled:
        return {'status': 'skipped', 'reason': 'development-disabled', 'enabled': False}
    if action == 'update':
        running = run(['docker', 'ps', '-q', '--filter', 'label=com.docker.compose.project=risklive-dev'])
        if not running.strip():
            return {'status': 'skipped', 'reason': 'development-not-running', 'enabled': True}
    root = app_config(policy, request)
    if Path(policy.get('data_root', str(DATA_ROOT))) != DATA_ROOT or DATA_ROOT.resolve() != DATA_ROOT:
        raise ValueError('Development data root must be /opt/risklive/dev-data without symlinks')
    if not (DATA_ROOT / '.risklive-development').is_file():
        raise ValueError('Development data must be initialized with dev.sh init before automation')
    trusted(DATA_ROOT / '.risklive-development')
    for role in ('app', 'web', 'caddy'):
        trusted(DATA_ROOT / 'env' / (role + '.env'))
    script = root / 'deployment/scripts/dev.sh'
    if action == 'stop':
        # Persist intent first; even if shutdown fails, pushes must not wake it.
        atomic_json(state / 'enabled.json', {'enabled': False})
        tag = active['candidate']['release_id'] if active else 'local'
        run([script, 'down'], safe_env(DATA_ROOT, tag))
        return {'status': 'stopped', 'enabled': False, 'active': active}
    candidate = validate_candidate(request.get('candidate'))
    identity = candidate_identity(candidate)
    tag = candidate['release_id']
    env = safe_env(DATA_ROOT, tag)
    compose_config(root, env)
    record_candidate(state, candidate)
    pull_candidate(candidate, tag, env)
    # dev.sh runs only app/web/caddy, --no-deps --no-build --pull never --wait.
    try:
        run([script, 'restart' if active else 'up'], env)
        checks = integration_checks(env, candidate)
    except Exception:
        failed = {'candidate_identity': identity, 'healthy': False, 'integration_passed': False,
                  'config_revision': request['config_revision'], 'release_id': tag}
        atomic_json(state / 'results' / (identity + '.json'), failed)
        record_once(state / 'history' / (str(time.time_ns()) + '-failed.json'), failed)
        raise
    evidence = dict(checks, candidate_identity=identity,
                    config_revision=request['config_revision'], release_id=tag,
                    images=candidate['images'], source=candidate['source'],
                    app_config_revision=policy['app_revision'])
    deployment = {'candidate': candidate, 'candidate_identity': identity,
                  'config_revision': request['config_revision'], 'evidence': evidence,
                  'operator': request.get('operator'), 'run_url': request.get('run_url')}
    event = dict(deployment, checked_at=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
    record_once(state / 'history' / (str(time.time_ns()) + '-' + uuid.uuid4().hex + '.json'), event)
    atomic_json(state / 'results' / (identity + '.json'), evidence)
    atomic_json(state / 'active.json', deployment)
    atomic_json(state / 'enabled.json', {'enabled': True})
    return dict(deployment, status='deployed', enabled=True)
