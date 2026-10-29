#!/usr/bin/env python3
"""Offline image evidence checks; never calls Docker or a registry."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tarfile

DIGEST = re.compile(r'sha256:[0-9a-f]{64}')
SHA = re.compile(r'[0-9a-f]{40}')
PLATFORM = re.compile(r'linux/(?:amd64|arm64)(?:/v[0-9]+)?')


def validate_manifest(release, require_recoverable=False):
    errors = []
    images = release.get('production', {}).get('images', {})
    if set(images) != {'app', 'scheduler', 'web', 'caddy'}:
        errors.append('Expected app, scheduler, web and caddy image records')
    for role, image in images.items():
        def check(ok, message):
            if not ok:
                errors.append(role + ': ' + message)
        check(bool(DIGEST.fullmatch(image.get('local_image_id', ''))), 'invalid observed local image ID')
        reference = image.get('reference', '')
        check(bool(reference) and ':latest' not in reference, 'missing or floating observed reference')
        p = image.get('provenance', {})
        revision = p.get('source_revision')
        check(revision is None or bool(SHA.fullmatch(revision)), 'invalid source revision')
        platform = p.get('platform')
        check(platform is None or bool(PLATFORM.fullmatch(platform)), 'invalid platform')
        recoverable = False
        registry = p.get('registry')
        if registry is not None:
            digest = registry.get('digest', '')
            ref = registry.get('reference', '')
            valid = (bool(DIGEST.fullmatch(digest)) and ref.endswith('@' + digest)
                     and bool(re.fullmatch(r'[a-z0-9][a-z0-9.:-]*/[a-z0-9._/-]+@sha256:[0-9a-f]{64}', ref))
                     and bool(PLATFORM.fullmatch(registry.get('platform', '')))
                     and registry.get('verification') == 'retrieved-and-tested'
                     and registry.get('source_revision') == revision
                     and (role == 'caddy' or bool(SHA.fullmatch(revision or '')))
                     and platform == registry.get('platform'))
            check(valid, 'invalid verified registry evidence')
            recoverable |= valid
        archive = p.get('archive')
        if archive is not None:
            valid = (bool(re.fullmatch(r'[0-9a-f]{64}', archive.get('sha256', '')))
                     and archive.get('image_id') == image.get('local_image_id')
                     and bool(PLATFORM.fullmatch(archive.get('platform', '')))
                     and archive.get('platform') == platform
                     and archive.get('verification') == 'restore-tested'
                     and bool(archive.get('storage')))
            check(valid, 'invalid verified archive evidence')
            recoverable |= valid
        if require_recoverable:
            check(recoverable, 'no verified off-host recovery evidence')
    if images.get('app') != images.get('scheduler'):
        errors.append('app and scheduler image records differ')
    return errors


def validate_archive(path, image):
    """Validate Docker-save archive identity without extracting or loading it.

    This checks bytes and config identity only, not runnable/restore-tested status.
    """
    archive = image['provenance']['archive']
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    if h.hexdigest() != archive['sha256']:
        raise ValueError('archive checksum mismatch')
    with tarfile.open(path, 'r:*') as tar:
        names = tar.getnames()
        if len(names) != len(set(names)):
            raise ValueError('duplicate archive members')
        for member in tar.getmembers():
            if member.name.startswith('/') or '..' in Path(member.name).parts or not (member.isfile() or member.isdir()):
                raise ValueError('unsafe archive member')
        def read_small(name):
            member = tar.getmember(name)
            if not member.isfile() or member.size > 1024 * 1024:
                raise ValueError('invalid metadata member')
            return tar.extractfile(member).read()
        manifest = json.loads(read_small('manifest.json'))
        if len(manifest) != 1:
            raise ValueError('expected single-image archive')
        config = read_small(manifest[0]['Config'])
        if 'sha256:' + hashlib.sha256(config).hexdigest() != image['local_image_id']:
            raise ValueError('archive image identity mismatch')
        meta = json.loads(config)
        actual = meta['os'] + '/' + meta['architecture']
        if meta.get('variant'):
            actual += '/' + meta['variant']
        if actual != archive['platform']:
            raise ValueError('archive platform mismatch')
        if not manifest[0].get('Layers'):
            raise ValueError('archive has no layers')
        for layer in manifest[0]['Layers']:
            if not tar.getmember(layer).isfile():
                raise ValueError('missing layer')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', type=Path, default=Path(__file__).resolve().parents[2] / 'release.json')
    parser.add_argument('--require-recoverable', action='store_true')
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--service', choices=['app', 'scheduler', 'web', 'caddy'])
    args = parser.parse_args()
    release = json.loads(args.release.read_text())
    errors = validate_manifest(release, args.require_recoverable)
    if errors:
        raise ValueError('; '.join(errors))
    if args.archive:
        if not args.service:
            raise ValueError('--archive requires --service')
        validate_archive(args.archive, release['production']['images'][args.service])
    print('Image evidence structure valid. Recovery ' + ('evidence recorded.' if args.require_recoverable else 'not established by this check.'))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError, tarfile.TarError) as error:
        print('Image validation failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
