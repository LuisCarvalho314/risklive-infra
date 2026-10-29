# Backup and recovery runbook

No real production files were read or copied for this implementation. Existing
backups under `/opt/risklive/backups` remain unverified. No jobs were scheduled.
Only synthetic WAL SQLite data has completed the structural restoration test.

## Inventory and consistency decisions

The baseline documents production app/scheduler mounts at
`/opt/risklive/data/{results,logs,runtime}`, environments at
`/opt/risklive/data/env/{app,web,caddy}.env`, and named volumes
`risklive-prod_caddy_data` / `risklive-prod_caddy_config`. Distinct legacy
`/opt/risklive/{results,logs,runtime}` directories must not be conflated with
production state. Development state and credentials require independent backups.

| State | Required treatment before a real backup |
| --- | --- |
| SQLite databases | Operator identifies exact files; online SQLite backup API includes committed WAL data without copying live WAL/SHM files. Each snapshot is individually consistent. |
| SECA | Inventory all stores and their dependencies. SQLite is supported individually; other mutable state requires an application export or storage snapshot with application consistency guarantees. |
| RAG indexes and source documents | Recover immutable source/versioned documents separately; use an application export for actively written indexes. Record index/source/model versions. Do not tar active indexes. |
| Results | Include only immutable completed outputs or application exports; reconcile their relationship to database rows. |
| Logs | Treat as optional operational evidence, use supported rotation/export; never assert a live copy is a consistent application backup. |
| Runtime | Exclude locks, sockets, PID files, caches and temporary writes. Inventory indispensable state and use its actual consistency mechanism. |
| Environment secrets | Recover from independently managed encrypted secret storage, separate from data snapshots. This tool refuses explicitly classified secret entries. Inventory classification is operator responsibility. |
| Caddy volumes | Export using a reviewed consistency mechanism and protect certificates/private keys as secrets. This tool does not copy active Docker volume directories. |
| Existing backup directories | Preserve until independent restoration establishes completeness, freshness, keys and compatibility. |

Do not infer that one SQLite snapshot plus file copies provides a transaction
across databases, SECA, indexes and results. A full recovery point needs an
application-level export/checkpoint protocol, or an application-consistent storage
snapshot. That protocol is not established by the baseline; no downtime or
production modifications have been introduced to invent one.

## Explicit inventory and snapshot

Obtain approval before reading/copying any real production data. Create the
inventory **outside Git**, restrict it to mode 0600, and review every entry for
secrets, mutable writes and sensitive filenames. Never use broad directory globs.
The following is a synthetic example, not a production inventory:

```json
{
  "sqlite_timeout_seconds": 60,
  "entries": [
    {"name": "state.db", "kind": "sqlite", "source": "/secure/synthetic/state.db"},
    {"name": "document.bin", "kind": "stable-file", "source": "/secure/synthetic/document.bin", "consistency_basis": "immutable"}
  ],
  "exclusions": ["secrets in separate secret store", "mutable index awaiting export", "transient locks"]
}
```

`stable-file` requires `consistency_basis` equal to `immutable` or
`application-export`; that classification is an operator assertion, not a
filesystem consistency guarantee. Size, inode and timestamp checks detect some
changes but cannot prove a mutable file safe. SQLite uses a separate read-only
connection and bounded online backup, never a checkpoint on production. Test the
load impact in development before authorizing production snapshots. Sources and
destinations must be trusted paths without symlinks; the tool is not a sandbox
against concurrent malicious filesystem changes.

```bash
python3 -I scripts/backup/recovery.py snapshot /secure/inventory.json /secure/backups
python3 -I scripts/backup/recovery.py validate /secure/backups/SNAPSHOT /secure/NEW-restore-drill
python3 -I scripts/backup/recovery.py retention-plan /secure/backups --keep 14
```

The root must be mode 0700; snapshots are mode 0700 and files/manifests mode 0600.
Snapshots record checksums, original UID/GID/modes, exclusions and individual
consistency limitations. No automatic ownership changes occur. A failed run may
leave an incomplete directory without a completed manifest: investigate it
privately; retention excludes it. Source names and source paths are deliberately
omitted from snapshot manifests, but entry names can still reveal information.

`validate` requires a new directory and refuses to overwrite an existing path.
It checks the complete file inventory and SHA256 values, copies to a separate
restore location, compares restored bytes and runs SQLite integrity and foreign
key checks. The receipt binds the manifest hash to a structural restore check.
It does not establish application semantics or full disaster recovery readiness.
Retention prints candidates only; it never deletes data. Set `--keep` to the
reviewed count and use an independently verified off-host successor before any
manual deletion. Define age/time policies, RPO and capacity externally before
operating a scheduled service; no scheduler is supplied or enabled here.

## Encryption and off-host storage

Use an encrypted local disk for plaintext snapshots. Install and independently
verify `age`, then encrypt only after structural validation:

```bash
python3 -I scripts/backup/recovery.py seal /secure/backups/SNAPSHOT /secure/SNAPSHOT.tar.age --recipient age1REPLACE_WITH_REAL_RECIPIENT
```

The command streams a tar to `age`, never writes a plaintext tar, refuses output
overwrite and reports the encrypted file checksum. `age` is not installed in the
agent environment: real encryption/decryption and key recovery remain untested.
No upload or paid storage call is made. Transfer encrypted artifacts and their
checksums through an approved off-host tool/service; use a separate account,
least privilege, immutable/versioned objects and independently retained keys.
Retain decrypted manifests inside encryption if artifact names are sensitive.
Checksums are corruption detection, not authentication: use trusted inventory,
authenticated age recipients, and protected artifact/receipt storage.

Prove key access on a separate host, decrypt to a restricted staging area and
inspect archive paths before extraction into a new empty directory. Run
`validate` there. Keep private keys out of snapshots and off the production VM.
A successful `seal` or transfer does not prove off-host recovery. This tool does
not accept arbitrary archive extraction inputs or restore over running services.

## Acceptance drill and remaining storage requirements

On a disposable isolated host with external API access disabled, restore verified
images/configuration, data exports and independently recovered secrets. Restore
original UID/GID/modes deliberately on that host; validate application-specific
SECA state, SQLite queries, RAG lookups and document/index version correspondence.
Restore Caddy volumes privately and validate certificates/configuration. Record
release, snapshot manifest hash, off-host object version, decryption success,
application checks, elapsed recovery time and measured recovery point. Keep
these receipts privately. Only that exercise can establish a verified restorable
production backup; synthetic integrity tests establish tooling behavior only.

Required operator decisions: actual database and state inventory, export/checkpoint
contracts, encrypted storage capacity (snapshot + restore drill + encrypted
artifact), off-host destination/immutability/retention, key escrow and rotation,
bandwidth, monitoring/alerts, approved cadence and RPO/RTO. No production backup,
secret recovery, Caddy volume export or end-to-end application recovery is claimed.

Offline tests: `python3 -I -m unittest discover -s tests/backup -v`.
