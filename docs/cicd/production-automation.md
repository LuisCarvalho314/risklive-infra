# Production activation and controlled cutover

`Production deployment` (`.github/workflows/production.yml`) accepts a successful application CI run ID, or a previously verified release ID for rollback. It runs only from infrastructure `main` inside the protected `production` environment. The job verifies required reviewers, prevented self-review and disabled administrative bypass through the read-only GitHub environments API. Approval releases the production-specific SSH key; the host never trusts a caller-supplied approval boolean.

The host keeps immutable release records and append-only event files under `/var/lib/risklive-deploy/prod`. `active.json` and `previous.json` are pointers to verified records. The historical root `release.json` stays untouched. App/web images are pulled by digest, OCI source labels are checked, and the reviewed exact Compose model is deployed with project `risklive-prod`. App and scheduler always share an image. No build, volume deletion or database restoration is available.

Before the first migration, reconcile the existing worktrees into a root-owned configuration checkout under `/opt/risklive/config/<revision>`. Preserve existing `/opt/risklive/data/{results,logs,runtime}` and environment files. Review the current scheduler container and stop/reconcile any scheduler outside project `risklive-prod` during the separately approved cutover. Do not enable analytics profiles. Review/pin Caddy to its tested digest using a host configuration overlay; no app implementation belongs in infrastructure. Do not execute the first cutover as part of coding or provisioning.

Create `/etc/risklive-deploy/prod.json` from this template outside the repository, replacing placeholder revisions and using the root-owned checkout paths. All referenced checkout files and ancestor directories must be root-owned and unwritable by deployment users.

```json
{
  "config_revision": "<40 hex infrastructure revision>",
  "app_root": "/opt/risklive/config/<application config revision>",
  "app_revision": "<40 hex application config revision>",
  "compose_files": ["deployment/compose/docker-compose.prod.yml", "deployment/compose/approved-host.yml"],
  "settings": {
    "COMPOSE_PROJECT_NAME": "risklive-prod",
    "RISKLIVE_DATA_DIR": "/opt/risklive/data",
    "APP_ENV_FILE": "/opt/risklive/data/env/app.env",
    "WEB_ENV_FILE": "/opt/risklive/data/env/web.env",
    "CADDY_ENV_FILE": "/opt/risklive/data/env/caddy.env",
    "CADDY_HTTP_BIND": "0.0.0.0:8888"
  },
  "backup_readiness_file": "/etc/risklive-deploy/backup-readiness.json",
  "backup_max_age_seconds": 86400,
  "compatible_transitions": [],
  "initial_cutover_approved": false,
  "legacy_state_compatibility_verified": false
}
```

Render the exact candidate Compose configuration using these settings and `docker compose --env-file /dev/null --project-name risklive-prod ... config --no-env-resolution --format json`. Review every service, mount, environment path, command, network and port. The overlay must pin Caddy, preserve its configuration and named volumes, and retain the production scheduler replica count of one. Use `prepare_prod_policy.py --rendered-model reviewed-model.json --template template.json --output proposed-policy.json` to compute the full model and file hashes without calling Docker. Changing app/web images is the only allowed model variation. The resulting policy defaults cutover authorization to false; operator review must explicitly set both legacy compatibility and first-cutover approval after validating state and configuration.

The separately validated backup readiness JSON contains `verified: true`, `data_root: "/opt/risklive/data"`, and integer `verified_at_epoch`; install it as root only after testing the existing backup/recovery tooling. It is a readiness assertion, never a request to restore data. No backup data is placed in GitHub or this repository. Refresh the marker before its configured maximum age expires.

Deploy the same candidate to development first. Healthy integration evidence is root-owned and binds the exact candidate identity and infrastructure configuration revision. A production plan verifies this evidence, paths, backup readiness, Compose hash and scheduler singleton. Then manually dispatch `Production deployment` with operation `plan` and candidate run ID. Review output, dispatch `deploy`, and approve the protected environment when ready. GitHub and host locks prevent overlapping rollouts.

Post-rollout checks require healthy app/web/Caddy containers, exactly one running scheduler with its intended command, and HTTP 200 through host port 8888. On health failure, image rollback occurs only when a reviewed directional revision pair appears in `compatible_transitions`; list both directions only after both are verified. Matching arbitrary image-supplied compatibility strings grants no permission. With unknown state compatibility the deployment fails and records the failure for an operator. No automatic database restore occurs. Explicit rollback selects a prior healthy host record and also requires a reviewed compatible transition; its old image/configuration model must still validate against the approved host policy.

Configuration changes require a new reviewed policy/model and infrastructure revision. Retain old checkout/model/policy versions outside the repository when changing configuration; rollback across configuration versions requires operator review/activation of the corresponding retained policy before dispatch. This prevents silently changing production mounts while rolling back images.
