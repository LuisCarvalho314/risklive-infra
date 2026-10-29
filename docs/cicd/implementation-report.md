# Implementation and validation report

Final consolidation branches are `feat/cicd-integration` in both repositories.
Infra starts at `infra/hardening-integration` (`7371b91`); app starts at the
existing isolated-stack branch `feat/on-demand-dev-stack` (`e1f2821`). All original
worktrees and uncommitted user files are left alone. Independent implementation
branches are retained: app `feat/automated-image-publishing` and
`feat/automated-dev-deployment`; infra `feat/automated-dev-deployment`,
`feat/automated-prod-deployment`, and `feat/secure-deployment-access`.
Integration fixes and final workflow pinning are on the consolidation branches.

| Workflow | Repository / file | Purpose |
|---|---|---|
| CI | app `.github/workflows/ci.yml` | Backend, frontend, both pinned SECA suites, app/web build/scan, gated private publication and digest artifact |
| Development controls | app `.github/workflows/development.yml` | Manual start/stop/redeploy/status; trusted successful designated-branch CI automatic updates |
| Development deployment | infra `.github/workflows/development.yml` | Reusable protected dev job, exact candidate fetch, restricted SSH deployment and result artifact |
| Production deployment | infra `.github/workflows/production.yml` | Read-only host plan, actual protected-environment approval, exact rollout/health and compatible rollback |
| Infrastructure validation | infra `.github/workflows/validate.yml` | Offline tests, allowlisted content/secret checks and shell syntax |

## Validation results

- Infrastructure: **83 tests passed** across backup (9), deployment/contract/
  approval/artifact tests (45), image recovery (4), hygiene (5), hardened release
  preflight (15), and security scanning (5).
- App backend: **205 passed**, with 32 real V2 tests intentionally skipped under
  the broad suite's subprocess guard and separately executed below.
- Real V2 integration/crash recovery: **32 passed**. Persistent Light replay
  probe passed across 8 process boundaries and 3 models.
- Rust Light: **153 passed** using the exact pinned Light source and a temporary
  cached alternate dependency lock. Exact committed locked build remains a hosted
  CI check because `futures-channel 0.3.34` is not cached locally.
- Rust V2: **40 passed / 4 ignored**. Publication privacy/metadata: **6 passed**.
  Liwan Compose/config: **2 passed**; optional local socket proxy test is blocked
  by sandbox socket restrictions.
- Frontend: typecheck passed; **114 tests passed in 22 files**. Next.js standalone
  build passed through compilation, type/lint checks, 11 generated pages and
  traces using temporary offline font-response mocks. Ordinary Google Fonts
  fetches cannot run through this sandbox's blocked DNS. Mocks are not committed
  or used in CI/Docker publication.
- Existing application `deployment/scripts/check-dev.py` passed. Real development
  Compose expansion and its existing isolation validator passed without daemon
  operations, using Python 3.11.
- All 6 workflow/composite YAML files parse; their shell steps and embedded Python
  blocks pass syntax validation. Python compilation, shell syntax, diff whitespace,
  staged infrastructure hygiene and secret scan passed. The application candidate
  producer's output passes the infrastructure candidate validator.

Tests use synthetic state and mocked Docker operations; they did not deploy.
No images were built/published locally, no SSH access was changed, and production
was not restarted. GHCR privacy cannot be confirmed from this session, so enabling
publication still requires the workflow's live privacy checks. See
[activation.md](activation.md) for every one-time requirement, the first safe
development start, and live checks still outstanding.

The task preserves original Light state semantics, historical `release.json`,
production data and secrets. Automatic rollback changes images only, never data;
unknown state/config compatibility records a failed rollout without database
restoration. Full reviewed configuration snapshots remain host-side and workflow
outputs expose provenance/status only.

## Files changed

### Application

- `.github/actions/build-candidate/action.yml`
- `.github/workflows/ci.yml`
- `.github/workflows/development.yml`
- `.gitmodules`
- `docker/Dockerfile.app`
- `docker/seca-v2/Cargo.lock`
- `docker/seca-v2/SOURCE.sha256`
- `docker/seca-v2/SOURCE_REVISION`
- `docker/seca/README.md`
- `docs/cicd/image-publication.md`
- `experimental-v2`
- `scripts/ci/candidate.py`
- `scripts/ci/package_privacy.py`
- `scripts/ci/publish.sh`
- `scripts/ci/tests/test_publication.py`
- `tests/integration/seca_light_probe.py`

### Infrastructure

- `.github/workflows/development.yml`
- `.github/workflows/production.yml`
- `.github/workflows/validate.yml`
- `.gitignore`
- `README.md`
- `docs/cicd/access.md`
- `docs/cicd/activation.md`
- `docs/cicd/architecture.md`
- `docs/cicd/development-automation.md`
- `docs/cicd/implementation-report.md`
- `docs/cicd/production-automation.md`
- `docs/cicd/release-contract.md`
- `schemas/candidate-v1.json`
- `scripts/baseline.py`
- `scripts/deploy/approval.py`
- `scripts/deploy/dev.py`
- `scripts/deploy/dispatch.py`
- `scripts/deploy/fetch_candidate.py`
- `scripts/deploy/prepare_prod_policy.py`
- `scripts/deploy/prod.py`
- `scripts/deploy/provision-access.sh`
- `scripts/deploy/release.py`
- `scripts/deploy/ssh_gate.py`
- `scripts/release/preflight.py`
- `tests/deploy/test_approval.py`
- `tests/deploy/test_dev.py`
- `tests/deploy/test_fetch_candidate.py`
- `tests/deploy/test_prod.py`
- `tests/deploy/test_release.py`
- `tests/release/test_preflight.py`
