#!/usr/bin/env python3
"""Validate GitHub's environment configuration and actual run approval evidence."""
import json
import sys
from pathlib import Path
from release import require


def validate_approval(environment, reviews, actor):
    require(environment.get('name') == 'production', 'Wrong approval environment')
    rules = [r for r in environment.get('protection_rules', []) if r.get('type') == 'required_reviewers']
    require(bool(rules) and bool(rules[0].get('reviewers')) and rules[0].get('prevent_self_review') is True,
            'SETUP REQUIRED: production must require reviewers and prevent self-review')
    # The documented environment REST response does not always expose bypass
    # configuration. Verify a real approval instead of assuming a missing field.
    require(environment.get('can_admins_bypass') is not True,
            'SETUP REQUIRED: disable production administrator bypass')
    require(any(review.get('state') == 'approved'
                and review.get('user', {}).get('login') not in (None, actor)
                and any(item.get('id') == environment.get('id') and item.get('name') == 'production'
                        for item in review.get('environments', []))
                for review in reviews), 'Explicit production approval for this workflow run required')


if __name__ == '__main__':
    validate_approval(json.loads(Path(sys.argv[1]).read_text()),
                      json.loads(Path(sys.argv[2]).read_text()), sys.argv[3])
