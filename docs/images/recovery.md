# Image provenance and recovery

## Observed evidence

The release inventory preserves operator-observed production IDs: app and scheduler share `c98694c54c5a…`; web is `1f04ca8075d0…`; Caddy is `612f0ff47f33…`. These are local image configuration identities, never registry manifest digests. The app tag corresponds to source `8a6775ac9a5cd8bef2462d400b853e28a1875884`; web to `8a42195ba06de8bac84bf7f1bd232f34c8d68f27`. Tag spelling is not cryptographic build provenance. Architecture, RepoDigests, OCI source labels, installed tags and archive availability remain unverified. Docker socket inspection in this session was denied. No escalation, image modification or registry retrieval occurred.

At the app revision, CI tests Python, Rust SECA and frontend code and builds an app image without publication. The app Dockerfile verifies SECA source hashes, locks Rust and Python dependencies and pins the Rust base digest, but uv and Python base tags and apt dependencies can drift. The web Dockerfile locks pnpm dependencies but uses mutable Node/Alpine base tags. Rebuilding these commits may produce functionally related images; it cannot promise the observed byte identities. App and web currently originate from different commits. No evidence establishes a recoverable registry copy of the current binaries.

## Strategy

For exact current binaries, prefer operator-approved `docker save` of each unique observed image ID into restricted storage, then encrypt and copy off-host. Never archive the entire Docker data root. Export is not performed here and requires approval. Verify the save archive config ID and architecture, hash its complete bytes, and load/test it on an isolated recovery host with synthetic state and no production credentials or API egress. Record `restore-tested` only after that exercise; retain evidence outside Git. Off-host retrieval and decryption must also be tested. An archive on jarvis alone does not survive VM failure.

For future releases, prefer explicitly private GHCR packages, immutable digest references, build attestations, dependency/vulnerability scans and a single app/web source revision. Both repositories are currently public: do not assume registry privacy follows repository visibility. Before the first approved publication, verify package privacy and access rules using a harmless staging package under operator control. Never publish production binaries to an unverified package. Decide access and retention before publication; retain previous verified release digests against garbage collection.

Protected archives offer recovery without registry dependency and can preserve legacy identities, but require encrypted off-host storage, retention, key custody and manual provenance records. Private GHCR offers authenticated retrieval and CI attestations, but needs scoped credentials, package visibility review and retention safeguards. Use both for critical releases when practical.

## Manifest contract

Schema 1 remains additive. Historical `reference` and `local_image_id` stay unchanged. Each image gains `provenance`:

- `source_revision`: full application commit or null for upstream images; `source_verification` describes evidence strength.
- `platform`: null until inspected, then e.g. `linux/amd64`.
- `registry`: null until verified; otherwise `reference` (registry path with `@sha256:` manifest digest), `digest`, `platform`, `source_revision`, `verification: retrieved-and-tested`.
- `archive`: null until verified; otherwise complete-file `sha256` (64 hex without prefix), `image_id`, `platform`, `storage` (nonsecret storage description), `verification: restore-tested`.

The validator checks recorded evidence consistency; it cannot authenticate an operator's attestation, prove registry availability, or demonstrate runtime compatibility. A local ID must never be copied into `registry.digest` without actual registry evidence. App and scheduler records must agree.

```bash
python3 -I scripts/images/validate.py
python3 -I scripts/images/validate.py --require-recoverable
python3 -I scripts/images/validate.py --archive /protected/off-host-retrieved/image.tar --service web
python3 -m unittest discover -s tests/images -v
```

The first command validates structure. The second intentionally fails for today's unverified inventory. Archive validation checks full-file checksum, safe metadata members, config identity and platform without extracting/loading it. It does not execute layers or establish a successful restore. Never place archives, production inspect output, registry credentials or image contents in Git.

## Publication preparation (inactive)

No runnable publication workflow is installed by this workstream. The CI proposal must require manual dispatch, protected approval, package privacy verification, `contents: read` and narrowly scoped `packages: write`; untrusted PR jobs get neither publication credentials nor write permissions. Build app and web from the same full approved application revision with pinned submodule, OCI revision labels, SBOM and provenance. Capture the digest emitted by the build/push operation; do not calculate one from a local config ID. Authenticated pull by digest and synthetic development integration testing precede the manifest promotion proposal. Updating a release manifest never grants production deployment approval.

Before legacy recovery is claimed complete: inspect image metadata in an authorised shell without dumping environment; preserve exact binaries off-host under encryption; verify retrieval, decryption, load and synthetic smoke tests; record platform and observed registry/archive evidence; rerun strict validation. Registry credentials, decryption keys and backup data stay outside both repositories. No production restart or cutover is necessary for this preparation.
