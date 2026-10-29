# Executable release contract

`release.json` remains the original historical inventory. It is deliberately not
converted into a verified deployment or used as proof of a unified release.

Candidates are `candidate.json` in the `risklive-candidate` artifact of the
application CI run. `schemas/candidate-v1.json` documents the shape;
`scripts/deploy/release.py` enforces the registry, repository, immutable app/web
digests, full source and SECA revisions (Light plus `seca_v2_revision` for V2), successful run identity, and state
compatibility identifier. A candidate identity is SHA-256 of canonical sorted,
compact JSON. Changing either image or provenance invalidates development evidence.

The compatibility identifier is a claim, not permission to restore state or roll
back. Production additionally requires the host's reviewed compatibility policy,
backup readiness and the exact candidate's successful development evidence.

The application and SECA revisions describe image contents. `config_revision`
describes the independently pinned infrastructure deployment controller/config.
The application checkout used for Compose configuration is pinned separately in
host policy; it contains the existing deployment scripts and Compose overlays.
No application implementation, environment secrets or database contents belong in
this repository.

The host keeps candidate records, environment active/previous records, health
results and an audit trail. Historical records must not be edited to repair a
failed deployment; a subsequent event records the failure or rollback. Mutable
active pointers are atomically replaced. `record_once` rejects a release ID
reused for different candidate contents.

Validate an artifact without Docker or host access:

```sh
python scripts/deploy/release.py validate candidate.json
```

GitHub's Container registry has granular visibility and permits anonymous pulls
of public packages. Repository visibility alone does not establish package
privacy. Publication must verify existing private packages and denied anonymous
access before uploading any application layer. The workflow intentionally blocks
until this one-time setup can be verified. See the
[GitHub package access documentation](https://docs.github.com/en/packages/learn-github-packages/configuring-a-packages-access-control-and-visibility)
and [Container registry authentication](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).

The two SECA gitlinks are intentional: the current V2 source changes the Light
snapshot format incompatibly. Retaining the original Light pin avoids requiring
a production state migration merely to enable CI/CD. Both pins are captured in
the app commit and OCI image labels; no SECA source is copied into infra.
