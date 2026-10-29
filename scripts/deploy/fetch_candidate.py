#!/usr/bin/env python3
"""Fetch a candidate only from a successful trusted application CI run."""
import io
import json
import os
from pathlib import Path
import re
import sys
from urllib.request import Request, HTTPRedirectHandler, build_opener
from release import validate_candidate
import zipfile


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None:
            redirected.remove_header("Authorization")
        return redirected


def get(path, binary=False):
    req = Request('https://api.github.com/' + path, headers={
        'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28'})
    with build_opener(SafeRedirect()).open(req, timeout=30) as response:
        data = response.read(8 * 1024 * 1024 + 1)
    if len(data) > 8 * 1024 * 1024:
        raise ValueError("Candidate response too large")
    return data if binary else json.loads(data)


def fetch(run_id, branches):
    if not re.fullmatch(r'[0-9]+', run_id):
        raise ValueError('Invalid CI run ID')
    repo = 'LuisCarvalho314/risklive'
    run = get(f'repos/{repo}/actions/runs/{run_id}')
    if not (run.get('conclusion') == 'success' and run.get('status') == 'completed'
            and run.get('path') == '.github/workflows/ci.yml'
            and run.get('event') in {'push', 'workflow_dispatch'}
            and run.get('head_branch') in branches
            and run.get('head_repository', {}).get('full_name') == repo):
        raise ValueError('Candidate did not originate from successful trusted CI')
    artifacts = get(f'repos/{repo}/actions/runs/{run_id}/artifacts')['artifacts']
    matching = [a for a in artifacts if a['name'] == 'risklive-candidate' and not a['expired']]
    if len(matching) != 1:
        raise ValueError('Exactly one unexpired risklive-candidate artifact required')
    data = get(f"repos/{repo}/actions/artifacts/{matching[0]['id']}/zip", binary=True)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        matching_names = [x for x in archive.infolist() if x.filename == 'candidate.json']
        if len(matching_names) != 1 or matching_names[0].file_size > 1024 * 1024:
            raise ValueError('Invalid candidate artifact contents')
        candidate = json.loads(archive.read('candidate.json'))
    validate_candidate(candidate)
    if candidate['source']['revision'] != run['head_sha'] or str(candidate['ci']['run_id']) != run_id:
        raise ValueError('Candidate exact revision/run mismatch')
    return candidate


if __name__ == '__main__':
    candidate = fetch(sys.argv[1], os.environ.get('CANDIDATE_BRANCHES', 'main,develop').split(','))
    Path(sys.argv[2]).write_text(json.dumps(candidate, sort_keys=True) + '\n')
