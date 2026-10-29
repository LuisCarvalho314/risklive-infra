#!/usr/bin/env python3
"""Generate a reviewable policy from operator-supplied rendered JSON; no Docker calls."""
import argparse
import copy
import hashlib
import json
from pathlib import Path


def prepare(model, template):
    if model.get('name') != 'risklive-prod' or set(model['services']) != {'app','scheduler','web','caddy'}:
        raise ValueError('Expected exact production service inventory')
    normalized = copy.deepcopy(model)
    for role in ('app','scheduler','web'):
        normalized['services'][role]['image'] = '<candidate>'
    template['reviewed_model_sha256'] = hashlib.sha256(json.dumps(normalized,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    root = Path(template['app_root'])
    template['files_sha256'] = {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in template['compose_files']}
    template['initial_cutover_approved'] = False
    template['legacy_state_compatibility_verified'] = False
    return template


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rendered-model', required=True, type=Path)
    parser.add_argument('--template', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args=parser.parse_args()
    result=prepare(json.loads(args.rendered_model.read_text()),json.loads(args.template.read_text()))
    with args.output.open('x') as stream:
        json.dump(result,stream,indent=2);stream.write('\n')
