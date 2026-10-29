# Infrastructure hardening integration review

Reviewed on jarvis on 2026-10-29 from baseline `75fa415`, consolidated locally on
`infra/hardening-integration` in an isolated worktree. Five implementation agents
used distinct branches/worktrees; the four-agent concurrency limit required waves.
No branch was pushed or merged to main. Existing application changes were preserved.

## Reviewed workstreams

The commit column identifies commits **on the integration branch**, which are
cherry-picks of the original focused implementation commits.

| Agent | Work completed | Integrated commit | Tests | Remaining blockers |
| --- | --- | --- | --- | --- |
| Git & Security | Repository/worktree and missing-source audit; protected preservation proposal; redacted index/all-blob scanner | `ff820c2` | 5 unit tests; index/history clean | Local-only Caddy/dev history needs approved private off-host preservation; public visibility policy unresolved; app history not content-scanned |
| Docker Images | Additive observed-versus-verified provenance, archive identity checks, recovery/publication preparation | `874ef9e` | 4 unit tests; structure passes; strict recovery correctly blocks | Docker socket denied; platforms, registry digests, exact binary archives and off-host retrieval unverified |
| Backup & Recovery | Online SQLite snapshots, checksums, restricted permissions, separate restore validation, encryption interface, retention plans | `00ecae1` | 9 synthetic tests, including committed WAL restoration | No production data read; real inventory, cross-file consistency, secrets/Caddy recovery, storage and off-host drill unresolved; age unavailable |
| Deployment & Rollback | Read-only fail-closed preflight, pinned model/config checks, migration and verified-release rollback runbooks | `2919f3b` | 14 offline tests; historical dry-run correctly blocks | No verified unified deployment or rollback release; operational identity/ports/state compatibility require verification |
| CI/CD | Existing workflow audit, inactive candidate-build proposal, publication/approval/secrets architecture, promotion ledger | `f9fac7e` | YAML parse and manual-trigger/read-only/no-publish/no-deploy assertions | No active pipeline installed; action pinning, actionlint, scanner/provenance choices, package privacy and protected environments unresolved |

Original focused commits: Security `e3b34ae`, Images `93ff008`, Backup `92108cf`,
Deployment `82d7cb0`, CI/CD `ba71078`. Shared integration groundwork is `d80f498`
(reviewed exact paths, indexed scanner hook, tracked-file hygiene, visibility
corrections) and `bbac9b2` (synthetic missing-index fixture correction). Five more
integration safeguard tests pass, including rejection of unknown indexed paths,
missing baseline files and worktree symlinks, and use of the indexed scanner
rather than an unstaged replacement. Total: **37 offline unit tests passed**.

## Review decisions and schema compatibility

All five outputs were inspected before consolidation; none was blindly merged or
excluded. Review identified incomplete app/scheduler and outer image-provenance
consistency checks in preflight. The deployment owner fixed these before its
focused commit, adding rejection tests. The security owner corrected scanner
script-root discovery so execution from the hook's restricted temporary file works.
The initial integration missing-file fixture failed because the synthetic index
had no commit; a separate correction commit fixed the fixture without history
rewriting. Final tests all pass.

Schema 1 remains additive. Historical `reference`, `local_image_id`, sources,
configuration hashes, observed mounts/ports and worktree inventory are unchanged.
Per-image `provenance.registry` and `.archive` remain null without verification.
Recovery validation accepts recorded verified registry or archive evidence;
future deployment promotion deliberately requires retrieved-and-tested immutable
registry references, one app/web/config revision and a separately verified
`deployment` definition. Archives preserve legacy recovery options but are not
authorisation for registry-based promotion. No digest or verification was invented.

The shared allowlist permits only exact reviewed source/docs/test paths and keeps
all baseline files mandatory. Independent branches may omit other workstreams.
Both staged and tracked-file checks reject unknown paths; the commit hook also
runs the indexed redacted scanner once present. Caches, databases, archives,
environments and other runtime artifacts remain ignored and forbidden. Hosted
secret scanning/CI enforcement is a future settings/workflow task; hooks alone
cannot enforce policy against intentional bypass.

## Validation evidence and limits

- Baseline validator passes: pinned Git/on-disk application configuration and
  reconstructed Compose images/mounts/ports, including upstream offline checks.
  This is static historical reconstruction, not production promotion readiness.
- Image structure validation passes. Strict recoverability returns failure for
  app, scheduler, web and Caddy because no verified off-host evidence is recorded.
- Deployment CLI dry run returns `PREFLIGHT BLOCKED: Historical inventory only:
  deployment definition is missing`. Positive synthetic model checks pass.
- Security index and every local Git blob, including unreachable objects, return
  no supported credential-pattern findings. This bounded scan is not proof that
  no possible secret exists. No application data/history content was scanned.
- Workflow YAML parses; trigger, permissions, approval-environment and absence of
  publication/deployment commands were asserted. The file remains outside
  `.github/workflows` and cannot run. No hosted run or image build is claimed.
- ShellCheck and actionlint are unavailable. `bash -n scripts/inspect-live.sh`
  and `sh -n .githooks/pre-commit` pass; these are syntax checks, not lint parity.
- Historical manifest equality was checked after removing only the new provenance
  and image-recovery fields. `hosts/` is unchanged. `git diff --check` passes.
- The commit hook passes with the indexed scanner. No credentials, runtime data,
  binary archives or application implementation were added to Git.

No production deployment, container recreation, image build/retag/push/removal,
Docker/scheduler restart, database mutation, backup job scheduling, paid API call,
visibility change or history publication occurred. Production behaviour is
unchanged by these repository-only changes; live daemon/state equivalence was
not independently established because daemon access is denied and real data
inspection was not authorised. Main remains at `75fa415`.

## Recovery gaps and next approved actions

All four requested source commits exist in the production-linked local Git store.
The app `8a6775ac` and web `8a42195b` are accessible through GitHub. Caddy
`f562f142` and development `e1f28218` are locally branch-reachable but unavailable
through that GitHub commit endpoint. Independent legacy clones lack all four.
Preserve reviewed parent history and separate submodule objects off-host; a local
branch or bundle alone does not survive VM loss.

Exact production images are **not yet proven recoverable**. Local configuration
IDs are retained as observations; platforms, registry manifests and protected
archives are unknown. Synthetic SQLite restoration validates tooling only;
**no production backup is verified restorable**. Environment creation-time values,
active Caddy configuration, cross-store consistency, Caddy certificates, secret
recovery, Azure networking and RPO/RTO remain unresolved. There is no verified
unified rollback target. CI review also found production SECA V2/crash-recovery
coverage absent from the inspected development workflow; future releases must
retain the relevant suites.

Explicit operator approval is required before publishing any branches/local
history or images; changing repository/package visibility or hosted protections;
reading/copying real production data or secrets for inventory/backup/restore;
creating production backup schedules; performing any cutover, container/service
restart, rollback or production state restoration. Review the concrete runbooks,
exact revisions/artifacts, storage/key plan and recovery evidence first. Read-only
Docker metadata inspection needs an appropriately permitted operator shell; it
must avoid full environment dumps. No such approval is implied by these commits.
