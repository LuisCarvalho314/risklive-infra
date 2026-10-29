# RiskLive infrastructure on jarvis

Private infrastructure baseline; local Git only, with no remote configured.
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

No hosted repository exists yet. If publishing is later authorised, create a
**private** `risklive-infra` remote and verify its visibility before pushing.
