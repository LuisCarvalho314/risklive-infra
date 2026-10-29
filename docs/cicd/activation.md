# Activation checklist

Nothing was pushed, published, deployed, restarted or provisioned during coding.
`release.json` is unchanged historical evidence. Production remains unverified
until a separately approved first cutover completes.

## GitHub

- Review the application and infrastructure `feat/cicd-integration` branches.
  The application control workflow is pinned to the reviewed infrastructure SHA.
  Set `RISKLIVE_INFRA_REVISION` to that same SHA, also installed in host policies.
  When reviewing/merging with rewritten commits, update the pin and policies.
- Protect the default and designated development branches. Set the application's
  `RISKLIVE_DEVELOPMENT_BRANCH` (default publishing branch: `develop`), and trust
  that branch in both `RISKLIVE_CANDIDATE_BRANCHES` (app development controls) and
  `CANDIDATE_BRANCHES` (infra production controls). Never allow PR branches.
- App environments: `registry-publishing` and `development`. Infra environments:
  `production-plan` and `production`. Restrict environments to reviewed default
  deployment refs. Production requires reviewers, prevents self-review, and must
  disable administrator bypass. The workflow also verifies an actual approval in
  the run's review history before deployment.
- Provision harmless seed GHCR packages `risklive-app` and `risklive-web` as
  **private**, disable repository inheritance, grant explicit Actions access,
  and verify denied anonymous access. No RiskLive layer may be uploaded first.
  The privacy guard checks this automatically before any application publication.
  Set app `GHCR_PUBLICATION_ENABLED=true` only after this setup.
- Development environment secrets: `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS`.
  App variables: `DEV_SSH_HOST`, `DEV_SSH_USER=risklive-deploy-dev`.
  Infra `production-plan`/`production` each need their own `DEPLOY_SSH_KEY`,
  `DEPLOY_KNOWN_HOSTS`, `DEPLOY_HOST`, and `DEPLOY_USER` secrets, with users
  `risklive-deploy-prod-plan` and `risklive-deploy-prod` respectively.
  Production API secrets stay on the VM.
- Keep `RISKLIVE_DEV_AUTODEPLOY=false` until the first manual start passes.
  Retain GHCR image versions and host release records; candidate Actions
  artifacts last 90 days. Do not delete images referenced by active/history.

## VM (separate operator authorization required)

- Review [restricted-access provisioning](access.md). Install root-owned Python
  3.11+ at `/usr/local/bin/python3`; the VM system Python 3.8 is insufficient.
  Verify Docker Compose >=2.24.4. Provision three independent SSH keypairs and
  fixed-operation users with the provided script. No Docker group membership or
  self-hosted runner is needed. Verify host keys through a trusted console.
- Install root-owned standalone application config clones and deployment
  controllers/policies. No user-writable checkout or Conda interpreter may execute
  as root. Configure only read access to private GHCR packages for host pulls.
- Reuse existing `/opt/risklive/dev-data`, marker, environment files and state.
  Initialize only if absent using existing `dev.sh init`. Keep root ownership of
  config/env/marker and application UID ownership of writable state. Cache the
  reviewed development Caddy image; `dev.sh` deliberately uses `--pull never`.
- Install [development policy](development-automation.md), independently of
  production. Verify fixed SSH operations and rejection of arbitrary commands,
  cross-environment operations, PTYs and forwarding. Start with `status` only.
- Before production activation, reconcile mixed worktrees; review the unified
  Compose model, persistent paths, Caddy digest/config, existing singleton
  scheduler and SQLite/state compatibility. Generate the reviewed policy with
  `prepare_prod_policy.py`; install a tested, fresh backup-readiness marker.
  Authorize the first cutover for an exact candidate identity only after review.
  Record directional compatibility pairs for subsequent deployments/rollback.
  Follow [production transition instructions](production-automation.md).

## First safe development deployment

1. After the above setup, push an approved app change to a trusted publishing
   branch. Wait for **CI**, including tests, container builds, scans and private
   publication, to finish successfully. Record its run ID.
2. On the app default branch, dispatch **Development controls** with `status`,
   then with `start` and that `candidate_run_id`.
3. Review the job summary and result artifact: exact app/web digests, source and
   config revisions, healthy app/web/proxy, scheduler absent, paid APIs disabled.
   Inspect `127.0.0.1:8188` through an approved SSH tunnel if desired.
4. Enable `RISKLIVE_DEV_AUTODEPLOY=true`. Successful designated-branch candidates
   now update only an already enabled/running environment.
5. `stop` preserves state and disabled intent. An earlier successful run ID with
   `redeploy` selects a previous candidate. `start` deliberately re-enables it.

Paid API testing remains a separately authorized operator action through the
existing isolated `dev.sh live-test --acknowledge-paid-api-calls ...` interface;
ordinary deployment credentials cannot execute it.

## Validation limits

Live GitHub Actions runs, package visibility/anonymous checks, actual Docker image
builds/scans/pulls, SSH provisioning, VM rollout health, backup readiness, and the
first production migration remain untested. No claim of a live deployed pipeline
is made. Local workflow YAML, shell steps and embedded Python syntax were checked;
`actionlint` was unavailable because external DNS is blocked in this sandbox.

Backend and real SECA integration tests passed. The exact Light source passed
Rust tests with a cached alternate dependency lock; the committed lock requires
an uncached dependency and must pass exact locked compilation in hosted CI.
Frontend typecheck and 114 unit tests passed. A normal Next.js build could not
fetch Google Fonts offline; compilation, type/lint checks, static pages and
standalone build passed using temporary font-response mocks, never committed or
used for published images. The optional Liwan socket-listener test cannot run
under sandbox socket restrictions; its two Compose/config tests passed.
