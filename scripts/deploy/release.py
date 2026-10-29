#!/usr/bin/env python3
"""Shared immutable candidate contract and host-owned release inventory.

Candidate artifacts contain provenance, never secrets. Host verification (CI API,
image labels, dev evidence and operator policy) is additional to schema validation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

REVISION = re.compile(r'[0-9a-f]{40}\Z')
RELEASE_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z')
COMPATIBILITY = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z')
REGISTRY = 'ghcr.io/luiscarvalho314/'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def validate_revision(value, label='revision'):
    require(isinstance(value, str) and bool(REVISION.fullmatch(value)), 'Invalid full Git ' + label)
    return value


def config_hash(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def validate_candidate(candidate):
    require(isinstance(candidate, dict), 'Candidate must be an object')
    require(candidate.get('schema_version') == 1, 'Unsupported candidate schema')
    rid = candidate.get('release_id')
    require(isinstance(rid, str) and bool(RELEASE_ID.fullmatch(rid)), 'Invalid release_id')
    source = candidate.get('source', {})
    require(isinstance(source, dict) and source.get('repository') == 'LuisCarvalho314/risklive', 'Unexpected application repository')
    validate_revision(source.get('revision'), 'source revision')
    validate_revision(source.get('seca_revision'), 'SECA-Light revision')
    if 'seca_v2_revision' in source:
        validate_revision(source['seca_v2_revision'], 'SECA V2 revision')
    images = candidate.get('images', {})
    require(isinstance(images, dict) and set(images) == {'app', 'web'}, 'App and web image digests required')
    for role in ('app', 'web'):
        ref = images[role]
        pattern = re.escape(REGISTRY + 'risklive-' + role) + r'@sha256:[0-9a-f]{64}\Z'
        require(isinstance(ref, str) and bool(re.fullmatch(pattern, ref)), 'Immutable ' + role + ' image digest required')
    ci = candidate.get('ci', {})
    require(isinstance(ci, dict) and ci.get('conclusion') == 'success', 'Successful CI required')
    run_id = ci.get('run_id')
    require(isinstance(run_id, str) and bool(re.fullmatch(r'[1-9][0-9]*', run_id)), 'Invalid CI run_id')
    require(ci.get('run_url') == 'https://github.com/LuisCarvalho314/risklive/actions/runs/' + run_id, 'CI run URL mismatch')
    state = candidate.get('state', {})
    require(isinstance(state, dict) and isinstance(state.get('compatibility'), str) and bool(COMPATIBILITY.fullmatch(state['compatibility'])), 'State compatibility identifier required')
    return candidate


def candidate_identity(candidate):
    return config_hash(validate_candidate(candidate))


def atomic_json(path, value):
    """Replace a mutable pointer atomically. Immutable records use record_once."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def record_once(path, value):
    """Never rewrite historical evidence; retrying identical records is safe."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        require(path.read_bytes() == encoded, 'Immutable release record already exists with different contents')
        return
    with os.fdopen(fd, 'wb') as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


def record_candidate(root, candidate):
    identity = candidate_identity(candidate)
    record_once(Path(root) / 'candidates' / (candidate['release_id'] + '.json'), candidate)
    return identity


def validate_dev_evidence(candidate, evidence, config_revision=None):
    require(isinstance(evidence, dict), 'Development evidence required')
    require(evidence.get('candidate_identity') == candidate_identity(candidate), 'Development evidence candidate mismatch')
    require(evidence.get('healthy') is True, 'Successful development health checks required')
    require(evidence.get('integration_passed') is True, 'Successful development integration checks required')
    validate_revision(evidence.get('config_revision'), 'development config revision')
    if config_revision is not None:
        require(evidence['config_revision'] == config_revision, 'Development config revision mismatch')
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    validate = sub.add_parser('validate')
    validate.add_argument('candidate', type=Path)
    inventory = sub.add_parser('inventory')
    inventory.add_argument('state_root', type=Path)
    args = parser.parse_args()
    if args.command == 'validate':
        value = json.loads(args.candidate.read_text())
        print(json.dumps({'release_id': validate_candidate(value)['release_id'], 'candidate_identity': candidate_identity(value)}))
    else:
        root = args.state_root
        result = {'candidates': [], 'active': {}}
        seen = set()
        paths = list((root / 'candidates').glob('*.json')) + list((root / 'dev/candidates').glob('*.json')) + list((root / 'prod/releases').glob('*.json'))
        for path in sorted(paths):
            value = json.loads(path.read_text())
            c = validate_candidate(value.get('candidate', value))
            identity = candidate_identity(c)
            if identity not in seen:
                result['candidates'].append({'release_id': c['release_id'], 'candidate_identity': identity, 'source': c['source'], 'images': c['images']})
                seen.add(identity)
        for env in ('dev', 'prod'):
            result['active'][env] = {}
            for pointer in ('active', 'previous', 'enabled'):
                path = root / env / (pointer + '.json')
                if path.exists():
                    result['active'][env][pointer] = json.loads(path.read_text())
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
