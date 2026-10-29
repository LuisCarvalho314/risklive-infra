# Development automation

The application workflow **Development controls** provides `start`, `stop`,
`redeploy` and `status`. It calls the infrastructure reusable workflow
**Development deployment**. Run manual controls on the application's default
branch, protected by repository rules. Automatic updates accept successful push
runs of **CI** from `RISKLIVE_DEVELOPMENT_BRANCH` only. Pull requests cannot access
this deployment job.

## One-time activation

Do these steps only after operator authorization to configure host access.
Nothing in this coding task installed access, changed host services, or deployed.

1. Merge/review infrastructure and application changes through the normal review
   process. Replace the application reusable workflow `uses: ...@...` reference
   with the immutable reviewed infrastructure commit. Set application repository
   variable `RISKLIVE_INFRA_REVISION` to that same full 40-character commit.
2. Protect the application's default and designated development branches. Create
   the **development** GitHub environment in the **application** repository.
   Restrict its deployment branches to the default branch; workflow-run controls
   execute from that branch. Add required reviewers if desired for manual starts.
3. Put `DEPLOY_SSH_KEY` and `DEPLOY_KNOWN_HOSTS` in that environment. The key must
   belong only to the restricted `risklive-deploy-dev` identity. Verify the VM SSH
   host key through an existing trusted administrative channel; never populate
   known_hosts with an unauthenticated `ssh-keyscan` in Actions.
4. Set repository variables `DEV_SSH_HOST` and `DEV_SSH_USER=risklive-deploy-dev`.
   Set `RISKLIVE_DEVELOPMENT_BRANCH` explicitly (for example `develop`). Set
   `RISKLIVE_CANDIDATE_BRANCHES` to a comma-separated list of trusted candidate
   branches, including that development branch. Leave
   `RISKLIVE_DEV_AUTODEPLOY=false` until the first manual deployment passes.
5. Use the secure-access provisioning procedure to install root-owned scripts,
   policy, deployment lock and restricted SSH/sudo operations. The default safe
   PATH must resolve a root-owned Python 3.11+ and Docker Compose 2.24.4+.
   The VM's existing system Python may be older: check it before activation.
   The deployment identity gets no Docker group membership or writable code.
6. Install an application configuration checkout under a root-owned path such as
   `/opt/risklive-deploy/app-config`, pinned to a reviewed application commit
   containing the existing development script, overlays and validators. Its
   complete parent chain and executable configuration must be root-owned and
   unwritable by other users. Keep it distinct from writable application state.
7. Initialize **only a new** `/opt/risklive/dev-data` with that checkout's existing
   `deployment/scripts/dev.sh init` if it does not exist. Reuse a correctly
   initialized existing root; do not reinitialize or copy production data. Ensure
   env files/marker are root-owned and not group/world writable. Set results,
   logs and runtime ownership to the application's container UID/GID 10001 as
   described in the application development guide. Keep dev credentials offline.
8. Configure root's Docker registry authentication with a separately authorized,
   read-only GHCR package identity. No production API keys go to GitHub Actions.
   Confirm the private candidate packages are accessible to the VM account.

Example root-owned `/etc/risklive-deploy/dev.json` (substitute reviewed full Git
SHAs, never tags or branch names):

```json
{
  "config_revision": "<40-character-reviewed-infra-commit>",
  "app_root": "/opt/risklive-deploy/app-config",
  "app_revision": "<40-character-reviewed-application-config-commit>",
  "state_dir": "/var/lib/risklive-deploy/dev",
  "data_root": "/opt/risklive/dev-data"
}
```

The app configuration revision is independent of the candidate application
revision: the configuration checkout supplies Compose files and isolation
validators; CI supplies the already built application images. Record and review
configuration changes separately. Host evidence records both revisions.

## First safe deployment

1. Enable image publication only after the package privacy checks documented by
   the publishing workflow succeed. Run CI on a protected trusted branch and
   select a completed successful run containing the `risklive-candidate` artifact.
2. From the application's default branch, run **Development controls** with
   `action=status`. A disabled environment is expected; status does not start it.
3. Run **Development controls**, `action=start`, and `candidate_run_id` equal to
   that successful CI run ID. The workflow fetches its candidate artifact,
   verifies the successful exact-source CI run, and sends JSON to the restricted
   SSH operation. No shell command or host path is accepted as workflow input.
4. Inspect the deployment result artifact and job summary. They report the source
   revision, immutable app/web digests, configuration revision and integration
   result. Confirm the development endpoint through an approved SSH tunnel to
   `127.0.0.1:8188`; it is not publicly published.
5. Set `RISKLIVE_DEV_AUTODEPLOY=true` after the successful manual validation.
   Later successful designated-branch candidates update development only while
   it is enabled and project containers are already running. They do not start
   an environment that was deliberately stopped or has no running containers.

The existing application `dev.sh` accepts local image tags, so the host pulls the
selected digest, verifies digest/source/SECA labels, and adds a release-specific
local alias before invoking `dev.sh`. It never builds on the VM or pulls a moving
remote tag. Compose starts only app, web and Caddy with `--no-deps --no-build`,
then verifies their actual running image IDs, health, API/scheduler flags, writable
mounts and fixed HTTP endpoints. The application's existing isolation validator
also checks the exact expanded model before any lifecycle operation.

## Routine controls and evidence

- `stop` records disabled intent before shutdown. It invokes the existing
  non-destructive Compose shutdown and retains databases, RAG indexes and results.
  Pushes remain unable to wake it, even if shutdown itself needs intervention.
- `start` explicitly re-enables development after a successful deployment. Supply
  a successful candidate run ID; existing persistent data remains in place.
- `redeploy` selects an earlier candidate by its successful CI run ID. Retain CI
  artifacts for the required rollback period; an expired candidate artifact must
  be recovered through the approved immutable release inventory process.
- `status` reports enabled intent and the last successful active candidate.
  It does not claim that last-known container health is a live health probe.

The root-owned state directory contains `active.json`, `enabled.json`, immutable
candidate records and deployment history. Development result files under
`results/<candidate_identity>.json` identify exact candidate digests and both
configuration revisions. Production promotion consumes successful health and
integration evidence for that candidate. A failed deployment records failed
result evidence; it neither marks a new active release nor automatically rolls
back or restores development databases. Review the failed Actions result and
host logs before explicitly redeploying.

## Separately authorized live API tests

Normal automation always retains the offline overlay, isolated internal network,
`RISKLIVE_EXTERNAL_APIS_ENABLED=false` and `DISABLE_SCHEDULER=true`. The remote
identity cannot request arbitrary commands or a `live-test` operation.

A separately authorized operator may use the application's existing
`deployment/scripts/dev.sh live-test --acknowledge-paid-api-calls COMMAND [ARGS...]`
from the pinned checkout, with a reviewed test command and only development
credentials in `/opt/risklive/dev-data/env/live.env`. Follow the existing app guide
for the paid-API acknowledgment and isolated foreground container. This exception
is deliberately outside automated deployment credentials and never starts the
production scheduler or mounts production data.
