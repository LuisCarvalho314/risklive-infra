# Git and infrastructure security audit

Evidence collected on jarvis on 2026-10-29, against infrastructure baseline
`75fa415`. Inspection was read-only. Application repositories were inspected for
Git/worktree metadata and dirty-path status only; runtime data, secret files and
application history contents were not scanned or copied. Infrastructure Git blob
contents were scanned, including its unreachable blob. No refs were created,
history rewritten, visibility changed, production state touched or history pushed.

## Source availability

| Role | Full source commit | Local reachability | GitHub API |
| --- | --- | --- | --- |
| Production application | `8a6775ac9a5cd8bef2462d400b853e28a1875884` | `feat/seca-v2-newsmap`, `repair/seca-v2-ui`; remote-tracking `origin/main` and feature refs | Available |
| Production web | `8a42195ba06de8bac84bf7f1bd232f34c8d68f27` | Remote-tracking `origin/main`; detached production worktree | Available |
| Caddy configuration | `f562f1425c1408712bd5168560fd227b44b89467` | `feat/liwan-feasibility`, `feat/on-demand-dev-stack`, `feat/rag_ingestion`; no containing remote-tracking ref | 422: no commit found |
| Development infrastructure | `e1f28218f857362c890d1648062d27b7ce2585ef` | `feat/on-demand-dev-stack`; no containing remote-tracking ref | 422: no commit found |

All four objects resolve as commits in `/home/azureuser/risklive-dev` and its
linked application worktrees. No source revision is missing from that local
object store. Remote-tracking refs are cached local evidence; no fetch was run.
GitHub API checks were performed by the coordinating agent. A failed API lookup
establishes unavailability through that repository endpoint, not universal
absence from every GitHub object store.

The independent clone `/opt/risklive/repo` is at
`4b46d279814d7d62e921d28184a37b10c431bbf0`, branch
`vm-fix-newsmap-loader`; its linked release worktree is detached at
`360e945a9271717f9cb114ccf48e951c0b13a323`. None of the four requested commits
resolves in that object store. `/home/azureuser/opt/risklive/repo/risklive` is a
separate clone at `ffc01a62a5bbfba1ddf64372988d90f0e921df7d`; none of the four
requested commits resolves there either. These clones cannot substitute for
preservation of the production-linked object store.

## Security findings

1. **Visibility documentation is incorrect.** GitHub repository metadata reports
   both `LuisCarvalho314/risklive` and `LuisCarvalho314/risklive-infra` as public.
   Infrastructure already has an SSH `origin` remote. Its README's claims of
   private/local-only storage, no remote and no hosted repository are false.
   Integration must correct those statements. API size zero does not prove that
   no remote refs or content have ever existed. No visibility change was made.
2. **Infrastructure topology is sensitive inventory.** Tracked host name, account
   and checkout paths, `/opt` storage layout, Compose project/network/volume
   names and public binding `0.0.0.0:8888` disclose operational structure. These
   are not credentials, but the public repository should be reviewed by its
   owner before any additional publication. Docker's internal network name is
   present; its subnet, Azure private IPs, NSGs, DNS and firewall state remain
   unverified. Public binding alone does not establish internet exposure.
3. **Local-only source creates VM-loss risk.** Caddy and development commits are
   protected from ordinary local garbage collection by existing branches, but
   share one VM/object store. A branch is not an off-host backup. Publishing
   either commit also publishes its reachable ancestry and requires review.
4. **No credential match in the inspected infrastructure objects.** At audit time
   the store contained one commit, six trees and fourteen blobs, including
   dangling blob `c16de46c46f9523e5852329830cfaf04e8b97c1e`. Index and all-blob
   scanner checks returned no findings; `git fsck --full --no-reflogs` reported
   only that dangling blob. This is a bounded pattern scan, not proof of an
   absence of all secrets. Application runtime/history content was deliberately
   excluded; pre-existing discovery documentation notes older application Caddy
   password hashes, which require a separate authorised history audit.
5. **Local safeguards need enforcement beyond Git hooks.** Baseline's exact-path
   allowlist, blob checks and pre-commit hook are useful. Hooks require local
   installation and can be bypassed. New scanner detects common provider tokens,
   private keys, Azure connection secrets, bcrypt hashes, non-placeholder secret
   assignments, risky index modes and sensitive artifact paths. It reports only
   rule names and file paths/object IDs. Integration should invoke it from the
   hook and non-deploying CI after reviewing all new paths. Enable hosted secret
   scanning/push protection where available and review branch protections with
   operator approval; no settings were changed here.

## Proposed preservation plan (not executed)

Review each local branch's complete reachable history, including tracked blobs,
submodule repositories/gitlinks, sensitive configuration, licences and any
previously tracked runtime artifacts. Avoid commands that print secret values.
If credentials are found, rotate/revoke them before publication; any history
rewrite is a separate approved plan coordinated with all worktree owners.

After approval, create explicitly named archival refs at the exact four full
commits, such as `preserve/2026-10-29-production-app`,
`preserve/2026-10-29-production-web`, `preserve/2026-10-29-caddy-config` and
`preserve/2026-10-29-development-infra`. Annotated tags with the same descriptive
names are another option; select one naming convention and record full IDs.
Preserve the SECA submodule commit objects in separate bundles: a parent Git
bundle records gitlinks but does not include submodule object databases.

Create restricted Git bundles containing only the reviewed refs and their
required ancestry, run `git bundle verify`, restore into an isolated empty
repository, and verify all four commit objects and pinned configuration hashes.
Encrypt bundles and copy them to approved off-host storage with independent key
custody; test retrieval/decryption/clone. Store checksums and the verification
record outside Git. A bundle residing only on jarvis is not disaster recovery.

Only after explicit approval, push the reviewed preservation refs to a verified
private destination. The application remote is currently public, so pushing
there cannot serve as a private preservation strategy. Do not silently use
`--all` or `--mirror`, publish local branches, change repository visibility, or
rewrite history. No preservation refs, bundles, remote operations or visibility
changes were performed during this task.

## Repeatable checks

Run against the infrastructure repository only; these commands read indexed or
Git object bytes and never read untracked environment files or runtime mounts:

```bash
python3 -I scripts/security/scan.py
python3 -I scripts/security/scan.py --history
python3 -m unittest discover -s tests/security -v
```

Exit code 0 means no supported pattern matched the checked scope; 1 means review
is required; 2 means the check could not complete. Findings never include matched
values. The history option scans every blob currently in the local object store,
including unreachable objects, without deleting or rewriting anything. The
scanner has no network access and cannot detect rotated/custom tokens, secret
splitting, every binary encoding, or missing objects from other clones. Treat
results as one safeguard alongside manual review and provider scanning.

## Worktree inventory

This records paths and dirty tracked-file counts only. Existing changes were left
untouched, including application lockfiles/frontend state, legacy tracked results
and logs, and SECA algorithm work. Counts are observations, not staged changes
made by this task. Infrastructure implementation worktrees are tracked separately
by the integration report.

| Repository or worktree | Tracked dirty paths |
| --- | --- |
| `/home/azureuser/risklive-infra` | 0 |
| `/home/azureuser/risklive-release-360e945` | 0 |
| `/home/azureuser/risklive-release-360e945/experimental` | 0 |
| `/home/azureuser/risklive_valyu/risklive` | 5 |
| `/home/azureuser/secalight-single-owner` | 15 |
| `/home/azureuser/secalight-evidence` | 6 |
| `/home/azureuser/secalight-evidence-base` | 0 |
| `/home/azureuser/github/risk_live` | 9 |
| `/home/azureuser/secalight-integration` | 0 |
| `/home/azureuser/opt/risklive/repo/risklive` | 4 |
| `/home/azureuser/opt/risklive/repo/risklive/experimental` | 1 |
| `/home/azureuser/risklive-dev` | 2 |
| `/home/azureuser/risklive-dev/.worktrees/seca-v2-release` | 0 |
| `/home/azureuser/risklive-dev/.worktrees/seca-v2-release/experimental` | 0 |
| `/home/azureuser/risklive-dev/.worktrees/seca-v2-repair` | 0 |
| `/home/azureuser/risklive-dev/.worktrees/seca-v2-prod` | 0 |
| `/home/azureuser/risklive-dev/.worktrees/seca-v2-build` | 0 |
| `/home/azureuser/risklive-dev/.worktrees/seca-v2-build/experimental` | 0 |
| `/home/azureuser/risklive-dev/seca-baseline` | 0 |
| `/home/azureuser/risklive-dev/experimental` | 5 |
| `/home/azureuser/risklive-dev/experimental/.worktrees/seca-ingestion-state` | 0 |
| `/home/azureuser/risklive-dev/experimental/.worktrees/seca-evaluation` | 0 |
| `/home/azureuser/risklive-dev/experimental/.worktrees/seca-benchmark-repro` | 0 |
| `/home/azureuser/risklive-dev/seca-architecture-iteration-2-main` | 0 |
| `/home/azureuser/secalight-refactor` | 0 |
| `/home/azureuser/secalight-transactions` | 10 |
| `/home/azureuser/risk_live/risk_live` | 32 |
| `/home/azureuser/secalight-simplify` | 0 |
| `/home/azureuser/risklive-on-demand-dev` | 0 |
| `/home/azureuser/risklive-on-demand-dev/experimental` | 0 |
| `/home/azureuser/risklive-rag-ingestion` | 2 |
| `/opt/risklive/repo` | 6 |
