#!/usr/bin/env python3
"""Approval-key authorised production rollout. Never restores databases."""
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.request import urlopen
from preflight import canonical
from release import (validate_candidate, require, config_hash, validate_revision,
                     candidate_identity, validate_dev_evidence, atomic_json, record_once)

SERVICES = {'app', 'web', 'scheduler', 'caddy'}


def run(args, **kwargs):
    result = subprocess.run(args, capture_output=True, text=True, **kwargs)
    require(result.returncode == 0, 'Deployment command failed: ' + ' '.join(args[:3]) + ' (output suppressed)')
    return result.stdout


def load(path):
    return json.loads(Path(path).read_text())


def trusted(path):
    p = Path(path)
    require(p.is_absolute() and p.resolve() == p, 'Noncanonical production path')
    for item in (p, *p.parents):
        stat = item.stat()
        require(stat.st_uid == 0 and not stat.st_mode & 0o022, 'Production configuration must be root-owned and not writable by others')
    return p


def compatible(current, target, policy):
    a = current['source']['revision']; b = target['source']['revision']
    return a == b or [a, b] in policy.get('compatible_transitions', [])


def compose(policy, candidate):
    root = trusted(policy['app_root'])
    revision = run(['git', '-C', str(root), 'rev-parse', 'HEAD']).strip()
    require(revision == policy['app_revision'], 'Pinned configuration checkout changed')
    settings = dict(policy['settings'])
    settings.update(APP_IMAGE=candidate['images']['app'], WEB_IMAGE=candidate['images']['web'])
    require(settings['COMPOSE_PROJECT_NAME'] == 'risklive-prod', 'Wrong production project')
    require(settings['RISKLIVE_DATA_DIR'] == '/opt/risklive/data', 'Production data root changed')
    require(settings['CADDY_HTTP_BIND'] == '0.0.0.0:8888', 'Production ingress changed')
    for role in ('APP', 'WEB', 'CADDY'):
        expected = '/opt/risklive/data/env/' + role.lower() + '.env'
        require(settings[role + '_ENV_FILE'] == expected, 'Production environment path changed')
        require(Path(expected).resolve() == Path(expected) and Path(expected).is_file(), 'Production environment file missing or symlinked')
    for part in ('results', 'logs', 'runtime'):
        p = canonical(str(Path('/opt/risklive/data') / part))
        require(p.is_dir() and p.resolve() == p, 'Production persistent storage missing or symlinked')
    args = ['docker', 'compose', '--env-file', '/dev/null', '--project-name', 'risklive-prod']
    for name in policy['compose_files']:
        p = trusted(str(root / name))
        import hashlib
        require(hashlib.sha256(p.read_bytes()).hexdigest() == policy['files_sha256'][name], 'Compose file drift')
        args += ['-f', str(p)]
    env = {'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin', 'HOME': '/root', **settings}
    model = json.loads(run(args + ['config', '--no-env-resolution', '--format', 'json'], env=env))
    require(model.get('name') == 'risklive-prod' and set(model['services']) == SERVICES, 'Unexpected production services')
    require(model['services']['app']['image'] == model['services']['scheduler']['image'] == candidate['images']['app'], 'App/scheduler image mismatch')
    require(model['services']['web']['image'] == candidate['images']['web'], 'Web image mismatch')
    # The full model, including every mount, path, command and network, must be
    # reviewed once. Only app/web image references may change per release.
    normalized = copy.deepcopy(model)
    for service in ('app', 'scheduler', 'web'):
        normalized['services'][service]['image'] = '<candidate>'
    require(config_hash(normalized) == policy['reviewed_model_sha256'], 'Exact production Compose model is not reviewed')
    for service in model['services'].values():
        require(not service.get('build') and not service.get('container_name'), 'Build/fixed container names forbidden')
    require('@sha256:' in model['services']['caddy']['image'], 'Caddy must be digest pinned in reviewed host overlay')
    return args, env, model


def verify_images(candidate, model):
    for role in ('app', 'web'):
        image = candidate['images'][role]
        run(['docker', 'pull', image])
        metadata = json.loads(run(['docker', 'image', 'inspect', image]))[0]
        labels = metadata.get('Config', {}).get('Labels') or {}
        require(labels.get('org.opencontainers.image.revision') == candidate['source']['revision'], 'Pulled image source provenance mismatch')
        require(image in metadata.get('RepoDigests', []), 'Pulled image digest identity mismatch')
        if role == 'app':
            require(labels.get('io.risklive.seca.revision') == candidate['source']['seca_revision'], 'Pulled app SECA provenance mismatch')
        require(labels.get('org.opencontainers.image.source') == 'https://github.com/LuisCarvalho314/risklive', 'Pulled image repository provenance mismatch')
    run(['docker', 'pull', model['services']['caddy']['image']])


def scheduler_inventory():
    ids = run(['docker', 'ps', '-aq', '--filter', 'label=com.docker.compose.service=scheduler']).split()
    for cid in ids:
        meta = json.loads(run(['docker', 'inspect', cid]))[0]
        require(meta['Config']['Labels'].get('com.docker.compose.project') == 'risklive-prod', 'Another project has a scheduler; operator reconciliation required')
    require(len(ids) <= 1, 'Duplicate production scheduler detected')


def health(args, env, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ids = run(args + ['ps', '-aq'], env=env).split()
        healthy = len(ids) == 4
        seen = set()
        for cid in ids:
            meta = json.loads(run(['docker', 'inspect', cid]))[0]
            role = meta['Config']['Labels'].get('com.docker.compose.service')
            seen.add(role)
            state = meta['State']
            healthy &= state.get('Running', False)
            if role == 'scheduler':
                healthy &= state.get('Restarting', False) is False
                # Check PID 1 and scheduler singleton; no scheduler task is executed.
                healthy &= 'app.scheduler' in ' '.join(meta['Config'].get('Cmd') or [])
            else:
                healthy &= state.get('Health', {}).get('Status') == 'healthy'
        if healthy and seen == SERVICES:
            try:
                with urlopen('http://127.0.0.1:8888/', timeout=10) as response:
                    if response.status == 200:
                        return True
            except OSError:
                pass
        time.sleep(3)
    return False


def plan(candidate, request, policy):
    validate_candidate(candidate)
    require(request.get('config_revision') == policy['config_revision'], 'Unapproved infrastructure config revision')
    validate_revision(policy['config_revision'])
    evidence = load(Path(policy.get('dev_state_dir', '/var/lib/risklive-deploy/dev')) / 'results' / (candidate_identity(candidate) + '.json'))
    validate_dev_evidence(candidate, evidence, policy['config_revision'])
    backup = load(trusted(policy['backup_readiness_file']))
    require(backup.get('verified') is True and backup.get('data_root') == '/opt/risklive/data', 'Verified production backup readiness required')
    require(time.time() - backup.get('verified_at_epoch', 0) < policy.get('backup_max_age_seconds', 86400), 'Backup readiness expired')
    args, env, model = compose(policy, candidate)
    scheduler_inventory()
    return args, env, model


def handle(verb, request, policy):
    state = Path(policy.get('state_dir', '/var/lib/risklive-deploy/prod'))
    state.mkdir(parents=True, exist_ok=True)
    active_file = state / 'active.json'
    if verb == 'status':
        return load(active_file) if active_file.exists() else {'status': 'historical-unverified'}
    candidate = request.get('candidate')
    if verb == 'rollback' or (verb == 'plan' and candidate is None):
        require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', request.get('release_id', '')), 'Invalid rollback release')
        prior = load(state / 'releases' / (request['release_id'] + '.json'))
        require(prior.get('verified') is True, 'Rollback target was not verified')
        require(prior['config_revision'] == policy['config_revision'], 'Rollback configuration requires explicit retained policy activation')
        candidate = prior['candidate']
    args, env, model = plan(candidate, request, policy)
    if verb == 'plan':
        return {'status': 'ready', 'release_id': candidate['release_id'], 'candidate_identity': candidate_identity(candidate), 'images': candidate['images']}
    require(verb in {'deploy', 'rollback'}, 'Unknown production operation')
    # Access to this operation is granted only by the production-specific key,
    # released to the approval-gated workflow. A JSON approval flag grants nothing.
    current = load(active_file) if active_file.exists() else None
    if current is None:
        require(policy.get('initial_cutover_approved') is True, 'Initial cutover requires explicit reviewed host policy approval')
        require(policy.get('legacy_state_compatibility_verified') is True, 'Legacy state compatibility not verified')
        require(policy.get('initial_cutover_candidate_identity') == candidate_identity(candidate), 'Initial cutover candidate not explicitly approved')
    else:
        require(current['config_revision'] == policy['config_revision'], 'Configuration transition requires separately reviewed policy activation')
        require(compatible(current['candidate'], candidate, policy), 'Unsafe state transition: database compatibility not established')
    release_file = state / 'releases' / (candidate['release_id'] + '.json')
    if release_file.exists():
        require(load(release_file)['candidate'] == candidate, 'Immutable release ID collision')
    verify_images(candidate, model)
    event = {'candidate': candidate, 'config_revision': policy['config_revision'], 'operator': request.get('operator'), 'run_url': request.get('run_url'), 'at_epoch': int(time.time())}
    events = state / 'events'; events.mkdir(exist_ok=True)
    record_once(events / (str(time.time_ns()) + '.json'), {**event, 'event': 'rollout-started'})
    try:
        run(args + ['up', '-d', '--no-build', '--remove-orphans', '--scale', 'scheduler=1'], env=env)
        require(health(args, env, policy.get('health_timeout_seconds', 180)), 'Post-deployment health checks failed')
        scheduler_inventory()
    except Exception:
        if current and compatible(candidate, current['candidate'], policy):
            old_args, old_env, old_model = compose(policy, current['candidate'])
            verify_images(current['candidate'], old_model)
            run(old_args + ['up', '-d', '--no-build', '--remove-orphans', '--scale', 'scheduler=1'], env=old_env)
            require(health(old_args, old_env), 'Deployment and compatible image rollback both failed; operator intervention required')
            record_once(events / (str(time.time_ns()) + '.json'), {**event, 'event': 'health-failed-image-rollback-succeeded'})
        else:
            record_once(events / (str(time.time_ns()) + '.json'), {**event, 'event': 'health-failed-no-compatible-rollback'})
        raise
    result = {**event, 'verified': True, 'status': 'healthy', 'model_sha256': config_hash(model)}
    release_file = state / 'releases' / (candidate['release_id'] + '.json')
    if not release_file.exists():
        record_once(release_file, result)
    else:
        require(load(release_file)['candidate'] == candidate, 'Immutable release ID collision')
    if current:
        atomic_json(state / 'previous.json', current)
    atomic_json(active_file, result)
    record_once(events / (str(time.time_ns()) + '.json'), {**event, 'event': 'rollout-healthy'})
    return result
