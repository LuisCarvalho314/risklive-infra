# Read-only verification

Use a normal authorised SSH shell on jarvis. The agent's sandbox cannot execute
these privileged checks. The script deliberately excludes container environment,
command arguments and arbitrary labels. Keep any collected output outside Git.

```bash
cd /home/azureuser/risklive-infra
bash scripts/inspect-live.sh --sudo
python3 -I scripts/baseline.py --verify-images --sudo
```

Equivalent essential commands, each on a single line to avoid broken pastes:

```bash
sudo docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
sudo docker compose ls --all --format json
sudo systemctl --no-pager show caddy caddy-api docker --property=Id,LoadState,ActiveState,SubState,UnitFileState,FragmentPath,MainPID
sudo ss -ltnp '( sport = :80 or sport = :443 or sport = :8888 or sport = :8188 or sport = :5001 or sport = :3000 or sport = :9042 )'
sudo docker image inspect risklive-app:8a6775ac9a5c risklive-web:8a42195ba06d caddy:2.8.4-alpine --format '{{.Id}} {{json .RepoTags}} {{json .RepoDigests}} {{.Os}}/{{.Architecture}}'
sudo docker network inspect risklive-prod_internal --format 'name={{.Name}} driver={{.Driver}} internal={{.Internal}} ipam={{json .IPAM.Config}}'
sudo docker volume inspect risklive-prod_caddy_data risklive-prod_caddy_config --format '{{.Name}} {{.Driver}} {{.Mountpoint}}'
```

If a pager is already showing `END`, press `q` before pasting more commands.
`--no-pager` prevents the earlier systemctl problem. Do not change daemon socket
permissions or enable host Caddy to obtain evidence.

To compare creation-time environment with `/opt/risklive/data/env`, an authorised
operator must review the values privately. Do not paste full container Env,
full Caddy runtime config, environment files, certificates or image archive
contents into an issue or commit. Record only reconciled non-secret changes and
secret-store references. Caddy loaded-config equality and complete runtime
equivalence are not asserted by this baseline's checks.

For local static checks, `python3 -I scripts/baseline.py` verifies source hashes
against pinned Git blobs and working files, renders Compose without reading
service env files, checks production topology and invokes the application's
offline/live development validators. `--emit production` or `--emit development`
prints the rendered model with env-file paths, not expanded secret values.
`--verify-images` additionally compares local tags to the manifest's image IDs.
No check pulls an image, builds, calls an external API or creates a container.
