# Authoritative production releases

The existing manifest remains historical inventory. It records separate app,
web and Caddy checkouts and observed image IDs; it is not an approved unified
release. `scripts/release/preflight.py` therefore fails closed on this manifest.
No deployment command is implemented. All invocations are dry runs, independent
of `--dry-run`. The tool never accesses the Docker daemon or reads service env
contents. It uses Git object/config reads and `docker compose config` only.

## Future manifest contract

Keep `schema_version: 1` and historical `sources`, `production.images.reference`,
`local_image_id` and `observed_compose_by_service` unchanged. Agent 2 owns image
`provenance`: promotion requires an actually retrieved and tested registry
reference, digest, platform and source revision. An image archive is useful for
recovery but is deliberately insufficient for this registry-based promotion path.
App, scheduler and web must correspond to the same full application revision;
the complete app/scheduler image records must match. Outer provenance platform
and source revision must match the verified registry evidence, and the platform
must use the supported Linux amd64/arm64 form. Upstream Caddy has independent provenance.
Never turn local image IDs into registry digests.

After separate operator review, a release candidate may add `deployment`:

```json
{
  "status": "verified",
  "revision": "FULL_40_HEX_APPLICATION_REVISION",
  "checkout": "/absolute/immutable/application-checkout",
  "compose_files": ["deployment/compose/docker-compose.prod.yml"],
  "caddy_file": "deployment/caddy/Caddyfile.prod",
  "files_sha256": {
    "deployment/compose/docker-compose.prod.yml": "ACTUAL_SHA256",
    "deployment/caddy/Caddyfile.prod": "ACTUAL_SHA256"
  },
  "platform": "linux/amd64",
  "rendered_config_sha256": "ACTUAL_CANONICAL_RENDERED_CONFIG_SHA256"
}
```

These are placeholders, not a usable release. Hash every Compose layer and
referenced configuration file. Use a single reviewed application checkout,
including the Caddy configuration; configuration remains in the app repository.
Each file must match both its pinned Git object and on-disk content. Symlinked
paths are rejected. Immutable image references must be used by the rendered
Compose model, including Caddy (the historical Compose file hardcodes its tag,
so a future app configuration revision must address that).

`rendered_config_sha256` is SHA256 of UTF-8
`json.dumps(model, sort_keys=True, separators=(',', ':'))`, where model is the
exact Compose JSON from the invocation below. This records the whole reviewed
model, including commands, security settings, dependencies, restart policy and
health checks, in addition to semantic checks. Only set `status: verified` after
reviewing that full model and isolated development validation; the tool cannot
establish that a human review happened. A checksum is not a signature or approval.

Provide non-secret string-valued Compose interpolation settings in a JSON file
outside Git. Include `COMPOSE_PROJECT_NAME`, `RISKLIVE_DATA_DIR`, image variables,
environment *paths*, ingress and any variables required by pinned Compose files.
Never put credentials in this settings file. Service env files stay outside Git.

```sh
python3 -I scripts/release/preflight.py --manifest release.json \
  --repository /absolute/immutable/application-checkout \
  --settings-json /absolute/operator/nonsecret-settings.json --dry-run
python3 -I -m unittest discover -s tests/release -v
```

Compose must support `config --no-env-resolution --format json`; failures block
preflight. Its stderr/config is suppressed to avoid leaking values. The tool
checks project `risklive-prod`, only the expected four services, immutable images,
platforms, environment path existence, production ingress from inventory,
network identity, bind paths/read-only flags and Caddy named volume names.
It verifies host directories exist but cannot establish their data contents,
backup freshness, Docker volume contents, Azure networking, image availability,
actual host architecture, port occupancy or running container identity. Those
require separately authorized operational verification. A passing dry run alone
is not permission to deploy.

## Migration and release ledger

1. Preserve the historical inventory and all currently referenced source commits.
2. Publish/retrieve/test immutable images only after explicit approval; retain
   verified evidence. Produce app and frontend from one tested application commit.
3. Prepare a single pinned configuration checkout with a reviewed production
   Compose configuration, immutable images and current persistent paths. Do not
   move data or edit the existing production worktrees.
4. Record candidate manifest, non-secret settings checksum, CI evidence,
   development integration results, image verification, restore drill and reviewed
   rendered model hash in an operator-managed release ledger. A release ID is the
   manifest SHA256, not a mutable label.
5. Run preflight; separately verify runtime environment drift, active Caddy
   config, existing Docker volume contents, production port ownership and current
   container project labels without printing secrets. Resolve all discrepancies.
6. Obtain explicit cutover approval with the concrete release and rollback plan.
   Cutover and post-deployment health checks are future operator actions.
7. Mark the release verified in the ledger only after operational checks pass.
   Preserve previous manifest/settings/configuration/image evidence for rollback.

No scheduler, systemd, Docker or production state changes are part of this work.
