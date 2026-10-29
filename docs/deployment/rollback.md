# Rollback procedure (operator approval required)

There is no currently verified unified rollback release. Historical local image
IDs and mixed checkout inventory are evidence, not proof of recoverability.
Do not designate the current baseline as a tested rollback target.

Before a future deployment, select a previous operationally verified manifest
from the release ledger. Verify its manifest checksum and configuration revision,
retrieve/test its immutable images on the intended platform, restore-test its
backup and confirm the old application can read the *current* state schema.
Rolling binaries back does not reverse database migrations, scheduler side
effects, results or external actions. If backward compatibility is uncertain,
stop and prepare a separately approved data recovery plan; never overwrite live
data to make a rollback pass.

Run the same read-only preflight against the previous release and its original
non-secret settings. Retain the current release manifest and exact image refs.
Review ports, environment paths, mounts, Caddy configuration and running project
identity. Obtain explicit operator approval naming the rollback target and data
handling decision before any Compose operation. Do not run both schedulers.

After the approved operator cutover, verify app/web health, proxy routing,
expected mounts, scheduler singleton identity, release/image identities and
scientific job continuity using non-mutating checks. Record the attempt and
outcome in the release ledger. Failed health checks do not authorize repeated
recreation or database restoration; stop and escalate the specific failure.

Synthetic preflight tests validate rejection of inconsistent release definitions.
They do not verify the running stack or production rollback execution.
