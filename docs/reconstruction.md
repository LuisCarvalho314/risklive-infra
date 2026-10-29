# Reconstruction and operation

These instructions describe future provisioning on a fresh VM. Do not execute
provisioning, restoration or Compose startup against existing jarvis as part of
version control. There is no automatic deployment script in this repository.

## Dependencies and application configuration

Install Git, Python 3.11+, Bash, Docker Engine and Compose 2.24.4+ supporting
`config --no-env-resolution`. Record target OS/architecture and match the image
platform. Preserve the existing HTTP ingress on 8888 and its intended external
Azure/firewall/DNS routing; those external rules have not been inventoried here.
Host Caddy and caddy-api remain disabled/inactive when using container Caddy.

Clone this infrastructure repository separately. Before any future push, its
hosted remote must be private. No remote has been created or configured by this
baseline. In each infrastructure clone enable its local guard:

```bash
git config core.hooksPath .githooks
```

Use the application repository URL recorded in `release.json` and fetch its
pinned commits. On a NEW VM, recreate these independent application checkouts or
worktrees (the original absolute paths are supported):

| Path under /home/azureuser | Application revision | Purpose |
| --- | --- | --- |
| risklive-dev | f562f1425c1408712bd5168560fd227b44b89467 | Mounted Caddyfile |
| risklive-dev/.worktrees/seca-v2-release | 8a6775ac9a5cd8bef2462d400b853e28a1875884 | Four-service production Compose |
| risklive-on-demand-dev | e1f28218f857362c890d1648062d27b7ce2585ef | Existing dev implementation |

For example, clone the application into `risklive-dev`, check out the Caddy
revision detached, then use `git worktree add --detach PATH REVISION` for the
other two paths. This is application source management in the application
repository; no application implementation belongs in this infrastructure repo.
Do not check out/reset existing dirty worktrees. The historical web worktree at
`8a42195ba06de8bac84bf7f1bd232f34c8d68f27` need not be copied to reconstruct the
model: its Compose bytes equal the pinned release base. Its image stays distinct.

If different checkout locations are needed on the new VM, copy
`hosts/jarvis/deployment.env.example` to an external path, edit the absolute
checkout/Caddy/data/env paths and pass it with `--settings`. The script checks
the pinned files' hashes rather than changing application branches. Existing
jarvis paths are not relocated by this task.

## Images and persistent state

Acquire the exact three production images in `release.json` from trusted
external image archives or a verified registry. The app image is shared by app
and scheduler. The web release is intentionally older. Image availability is a
restore prerequisite; no image archives or registry publication were verified.
Builds belong to the pinned application Dockerfiles/CI, outside this repository.
A rebuild is not guaranteed to reproduce the recorded local image ID.

For trusted saved images, `sudo docker image load --input /secure/path/image.tar`
is a future fresh-VM operation. Keep archives external and access-controlled;
images can contain sensitive files. Do not overwrite current production tags on
jarvis. Verify all tags against `local_image_id` before deployment using the
baseline checker. An image's local `sha256` ID is not its registry manifest digest;
do not use it as `repository@sha256:...`. If images must change, reconcile the new
IDs/digests and update the release manifest in a separately reviewed change.

Restore production `results`, `logs` if needed, and `runtime` under
`/opt/risklive/data` from an application-consistent backup. Runtime can include
SECA state; results can include datasets, models and RAG artifacts. Restore
`risklive-prod_caddy_data` and `risklive-prod_caddy_config` as named Docker volumes
with those exact names. Inspect and preserve backup UID/GID/permissions. The
application image's documented UID/GID is 10001:10001. Do not apply recursive
ownership changes to existing production. Keep production/dev roots disjoint.

Restore `/opt/risklive/data/env/{app,web,caddy}.env` from secure configuration,
with restricted permissions. If unavailable, seed templates from the pinned
application production revision, reconcile `hosts/jarvis/app.env.example` and
`web.env.example`, then supply real credentials and operational values privately.
The app template is a key-name inventory/delta, not a verified complete runtime
environment. Recover scheduler/API/SECA settings from secure configuration and
compare privately with the old deployment. Set Caddy's site to `http://:80` to
match the observed on-disk production environment. No secrets are stored here.

## Validate and future startup

```bash
cd /home/azureuser/risklive-infra
python3 -I scripts/baseline.py --settings /secure/path/deployment.env
python3 -I scripts/baseline.py --settings /secure/path/deployment.env --verify-images --sudo
```

The checker uses configuration only and does not test secret values or restore
completeness. Reconcile the unresolved runtime details in `release.json` before
using this model for a real deployment. On a fresh VM after that review, Compose
uses the external settings, the pinned application base and the path-only overlay:

```bash
# Future fresh-VM startup only; not run during this baseline task.
# Clear inherited COMPOSE_* / image / data / env-path variables first:
# shell exports override --env-file. Use a clean operator shell.
sudo docker compose --env-file /secure/path/deployment.env --project-name risklive-prod -f /home/azureuser/risklive-dev/.worktrees/seca-v2-release/deployment/compose/docker-compose.prod.yml -f /home/azureuser/risklive-infra/hosts/jarvis/compose.override.yml up -d --no-build --pull never --wait app scheduler web caddy
```

Do not invoke the application's generic deploy helper for this baseline without
the host override: it would select a different Caddyfile location. The new model
is not used to recreate existing containers automatically. Future migration of
creation authority to it requires review of rendered configuration against live
settings and a controlled deployment window. No image tag, volume name, published
port or live file is changed by committing this repository.

## On-demand development

Continue using the existing application `deployment/scripts/dev.sh`; no dev
Compose implementation is copied here. Export `RISKLIVE_DEV_DATA_DIR` if using a
different canonical isolated root. For a fresh root only, `dev.sh init` seeds
external directories and credentials templates; never initialise over an
existing root. Restore the development marker/state from its own backup when
recovering an existing environment. Keep development credentials separate.

If development binaries are unavailable, build them from the pinned development
application revision using the application's build action. Choose a new explicit
`RISKLIVE_DEV_IMAGE_TAG`; do not retag production images. The manifest currently
records only expected default `:local` tags, because no dev image inventory was
provided. Record actual development image IDs in a future manifest update when
available. Exact recovery of previous dev binaries cannot yet be guaranteed.

Normal `dev.sh up` starts only app/web/Caddy, publishes `127.0.0.1:8188`, uses
isolated writable state, disables scheduler/analytics and external API use, and
blocks outbound application networking. `dev.sh config` may expand env values:
keep its output private. Use this repo's checker for shareable static validation.
Only `dev.sh live-test --acknowledge-paid-api-calls COMMAND [ARGS...]` enables an
explicit disposable API-using app command with `/opt/risklive/dev-data/env/live.env`.
Do not run it during reconstruction validation or use production credentials.

## Rollback, maintenance and Git hygiene

Record each future approved release as a manifest change with service-specific
image identities and source hashes. To roll back, select a previously reviewed
manifest commit and matching application configurations/images in separate
checkouts, validate, then plan a controlled deployment. Do not reset live dirty
worktrees or assume all service images share a revision. Restore data only from
a compatible, validated backup in a separate maintenance procedure; never unpack
backups over running production. Never use `down -v` for production maintenance.

Use the read-only inspection script for routine inventory. Backup jobs, retention,
monitoring and Azure routing were not verified, so this repo does not invent
authoritative configurations for them. Document them here only when discovered.

The explicit ignore allowlist and pre-commit hook block ordinary staging of new
secrets/runtime/application paths. Review `git diff --cached --stat` and
`git diff --cached` before every commit. A new infrastructure file requires an
intentional update to both `.gitignore` and the validator allowlist. Do not use
force-add or bypass hooks for secret files. The initial baseline is local only;
there is no push or merge in this task.
