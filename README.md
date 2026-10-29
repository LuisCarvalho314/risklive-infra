# RiskLive infrastructure on jarvis

Infrastructure baseline with local hardening branches. GitHub metadata on
2026-10-29 reports both RiskLive repositories as **public**; an `origin` remote
is configured. No pushes or visibility changes are authorised by this work.
This repository owns host settings, release inventory, a Caddy bind-path override,
read-only operational checks and reconstruction instructions. The `risklive`
application repository continues to own Dockerfiles, CI, service Compose files,
development safety checks and proxy implementation. Nothing here changes live
files or starts, stops, rebuilds or redeploys containers.

Production was identified from operator-provided Docker/systemd output on
2026-10-29. It is project `risklive-prod`, with container Caddy on `0.0.0.0:8888`.
App/scheduler use `risklive-app:8a6775ac9a5c`; web uses
`risklive-web:8a42195ba06d`; Caddy uses `caddy:2.8.4-alpine`.
`release.json` pins their observed local image IDs and the application
configuration revisions/hashes. These image IDs are not registry digests.

The containers were created from three checkouts. The production model here
references the existing release Compose file and overlays only the Caddyfile
bind source to preserve its current location. It is a reconstruction model,
not a claim that one historical Compose invocation created the whole stack.
Creation-time environment and Caddy's in-memory configuration remain unverified.

Requirements: Git, Python 3.11+, Bash, and Docker Compose 2.24.4+ with
`config --no-env-resolution` (validated with 2.35.1). Docker Engine access is
needed only for optional image/live inspection. Versioned images, external
credentials and persistent state are separate dependencies.

```bash
cd /home/azureuser/risklive-infra
git config core.hooksPath .githooks
python3 -I scripts/baseline.py
# Optional, in an authorised operator SSH shell:
python3 -I scripts/baseline.py --verify-images --sudo
bash scripts/inspect-live.sh --sudo
```

The default settings template describes current jarvis paths. Copy it outside
both repositories for local changes and pass `--settings /absolute/path/file`.
Checks render Compose with service env expansion disabled and never contact
external APIs. The pinned application configurations must be available on disk.

- [Discovery, ownership and remaining gaps](docs/discovery.md)
- [Reconstruction, development and rollback](docs/reconstruction.md)
- [Read-only operator verification](docs/verification.md)

Production state is under `/opt/risklive/data`; development state is under
`/opt/risklive/dev-data`. Credentials, images, volumes, databases, RAG indexes,
reports, logs, certificates and backups stay outside Git. The ignore file denies
all paths except the explicit baseline allowlist; the local pre-commit hook also
checks staged paths, file types and common secret patterns. Manual staged review
remains necessary; force-add and bypassed hooks can defeat these protections.

Before any approved publication, review the tracked operational inventory and
reachable history, and verify the intended destination and access policy.
Existing local Caddy/development revisions are not recoverable from GitHub.

Hardening tools and runbooks:

- [Git/security audit and preservation](docs/security/audit.md)
- [Image provenance and recovery](docs/images/recovery.md)
- [Backup and restore validation](docs/backup/recovery.md)
- [Release preflight and migration](docs/deployment/release-management.md)
- [Rollback](docs/deployment/rollback.md)
- [CI/CD proposal](docs/cicd/architecture.md)
- [Consolidated validation and remaining gaps](docs/integration/report.md)

The baseline check validates historical reconstruction. Deployment preflight is
a separate promotion gate and intentionally rejects the unverified historical
release. Synthetic backup tests do not establish production recoverability.

## Executable CI/CD

The implemented candidate, development, production and rollback workflows are
described in [activation](docs/cicd/activation.md),
[release contract](docs/cicd/release-contract.md),
[development controls](docs/cicd/development-automation.md),
[production cutover](docs/cicd/production-automation.md), and
[restricted SSH access](docs/cicd/access.md). Historical `release.json` is preserved.

Read-only inventory: `python scripts/deploy/release.py inventory /var/lib/risklive-deploy`.
Host operation audit records are under `/var/lib/risklive-deploy/audit`; environment
release histories are separate. Policies and full rendered models stay on the VM;
workflow results report deployment provenance and health only.
