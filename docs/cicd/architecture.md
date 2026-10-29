# CI/CD architecture and current audit

This proposal is inactive. No application workflows or GitHub settings were changed. The companion `candidate-build.yml.example` lives outside `.github/workflows`; it cannot run here. It is a narrow, non-publishing candidate build proposal, not the complete production pipeline. It must pass the activation checklist below before being moved into the application repository.

## Existing application validation

Inspected Git objects in `LuisCarvalho314/risklive` at production app `8a6775ac9a5cd8bef2462d400b853e28a1875884` and development infrastructure `e1f28218f857362c890d1648062d27b7ce2585ef`. Their `.github/workflows/ci.yml` SHA256 values are respectively `aad905454556673ec743a9c0f230ab0c412c876d43bf333a65efd7fa13c9ac02` and `3aec02ebf7a67253ac1abb17c90b317cc519f13c86cc4d23ef4ff64c020f4b1e`.

| Area | Existing checks | Gap for release promotion |
|---|---|---|
| Backend | Python 3.11, uv 0.9.15, locked dev dependencies, isolated full pytest tree, scheduler disabled | No demonstrated packaged-image integration or dependency/vulnerability gate |
| Frontend | Node 20, pnpm 10.30.3, frozen lockfile, typecheck, unit tests, Next.js build | No frontend Docker build in existing CI; no paired digest release |
| SECA | Pinned submodule and file hashes, Rust 1.92.0, copied production Cargo.lock, locked tests/builds, Python/Rust integration | Production revision additionally tests/builds V2 and its crash recovery; development revision replaces that with the legacy production-converter probe. Preserve both relevant suites in the future release branch; do not infer one workflow proves the other |
| Docker | SECA job builds application image without publication | No registry login, push, registry digest capture, signed provenance, SBOM, image scan, retrieval test or rollout |
| Workflow | PR and main/develop/dev/** pushes; contents read; checkout credentials disabled | Mutable action version tags; branch/environment protections were not inspected |

No successful hosted run is claimed from static workflow inspection. Existing workflows must be reviewed on the exact candidate revision. A green run on another branch or SHA is insufficient.

## Intended release chain

Application commit -> required backend/frontend/SECA checks -> paired app/web image builds -> dependency and image scans + SBOM/provenance -> separately approved publication to verified private packages -> pull by immutable digest -> isolated development validation -> reviewed infrastructure manifest change -> manual production approval -> separately authorised operator deployment -> health verification and rollback ledger.

Use existing GitHub Actions, Compose and the infrastructure preflight. No Kubernetes, Terraform or new control plane is required. Keep PR checks credential-free on GitHub-hosted disposable runners; never use `pull_request_target` to run PR code with write credentials and never expose a production-connected self-hosted runner to public PRs.

The inactive candidate build proposal requires a manual main dispatch, full input SHA equal to the selected main SHA, an existing successful push CI run for that SHA, and a protected review environment. It builds both Dockerfiles from one checkout with matching revision labels and no push permission. It does not retain the images; it proves only buildability. It intentionally omits publication, scanner installation, SBOM attachment and promotion automation until reviewed tools, action SHAs and package privacy controls are selected. Existing mutable Docker bases and apt packages also prevent guaranteed bit-for-bit rebuilds; preserve the tested binaries when publication is implemented.

## Publication design, not installed

A separate manual workflow must bind immutable revision, platform, CI run and scan policy to its approval. Its publication job alone receives `packages: write`; preceding checks retain read-only permissions. Verify an already-private GHCR package and access policy before pushing production binaries. Both source repositories are currently public, so repository visibility cannot establish package privacy. A safe operator-controlled staging package may be needed to verify first-publication behaviour before approving any production binary upload. Do not rely on a post-push privacy change.

Use pinned, reviewed build/login/attestation/scanner actions. Build app and web once from the same full Git SHA and pinned SECA commit. Export SBOM and provenance that bind source, builder identity, dependencies, platform and resulting artifact digest; a revision label alone is a claim. Capture manifest digests from actual publication output, then authenticate and retrieve each digest on an independent validation runner. Inspect the retrieved config identity and architecture and run synthetic tests before recording `retrieved-and-tested`. Multi-platform index and per-platform manifest digests are different; pin the tested platform and document which digest the release references. Scan dependencies and final images, set an explicit severity/exception policy with expiry, and block promotion on failures. Do not publish scan reports containing secrets or production data.

Require successful Rust/SECA V2 and legacy integration where relevant, Python and pnpm lockfile audits, OS/image vulnerability scanning, and secret scanning of changed source and publication context. Scanner versions and vulnerability database timestamps belong in the evidence. Dependency advisories can change after build, so rescan retained rollback images before reuse and record operator risk acceptance rather than silently disabling scans.

The publication workflow must produce a candidate evidence document, not overwrite production `release.json`. An operator-reviewed infrastructure change records retrieved image IDs, immutable references, platform, source revision and evidence links under the shared contract. A registry push alone never sets `verification: retrieved-and-tested`.

## Permissions and secrets inventory

| Job or system | Permission / credential | Scope and handling |
|---|---|---|
| PR/backend/frontend/SECA | `contents: read` only | No secrets; disable scheduler and real API use; synthetic fixtures |
| Proposed candidate build | `contents: read`, `actions: read` | `github.token` reads exact-revision CI run; no registry or host credentials |
| Approved image publication | `contents: read`, `packages: write`; optionally `id-token: write`, `attestations: write` only for the chosen attestation mechanism | Job-scoped token, main-only protected environment; no PR publication |
| Development digest pull | Minimal `read:packages` credential or supported narrowly scoped token | Private-package read only; short-lived preferred; mask logs and avoid command-line token values |
| Infrastructure promotion review | `contents: read` by default; narrowly scoped separate bot only if later approved to propose a PR | No direct main write; avoid PAT with broad repository administration scope |
| Production | No Actions host credential installed by this task | Later choose operator-driven Compose deployment; no SSH private key, Azure credential, environment secret or backup decryption key in CI |
| Off-host archive recovery | Separate encryption keys and storage credentials | Protected operator storage; not Actions artifacts or Git; retrieval/decryption tested independently |

GitHub environment names alone do not enforce review. Before activation, inspect and configure required reviewers, prevent self-approval where supported, restrict deployment branches and verify applicable plan/features. Branch protections must require complete exact-SHA CI coverage and CODEOWNERS/review for workflow and deployment changes. These settings need operator approval; none were changed here.

## Validation and activation checklist

1. Pin all referenced Actions to reviewed full commits and validate the proposal with actionlint. The current version tags mirror existing CI for review only; they are an explicit activation blocker.
2. Configure and verify the protected `image-candidate-review` environment and main branch protections. Confirm public fork PRs cannot reach credentials or write-capable jobs.
3. Exercise exact-SHA CI lookup with success, failed, absent, wrong-SHA and non-main cases; retry/rerun policy must be documented. The prototype deliberately fails if no matching run is returned and never falls back to another commit.
4. Run the build proposal in an approved disposable environment; check both revision labels and pinned SECA, preserve V2 coverage, and confirm the web Dockerfile builds. No build was executed during this task.
5. Add pinned scanner, SBOM and provenance steps in a separately reviewed change; test a known vulnerable synthetic fixture causes a gate failure. Select explicit vulnerability waivers with owner and expiry.
6. Validate private-package authentication and visibility before approving publication; test denied unauthenticated retrieval. Publish only with explicit approval, then retrieve and test the actual digests on synthetic isolated development state.
7. Exercise the promotion and rollback procedure with synthetic manifests; run image validation and release preflight. Confirm the current historical inventory fails promotion readiness.

Offline validation of this proposal during the task parses YAML, checks read-only permissions/manual trigger and absence of publishing/deployment commands. It does not validate hosted credentials, GitHub environment protection, image builds, scanner coverage or actual recovery.
