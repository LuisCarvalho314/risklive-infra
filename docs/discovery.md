# Discovery and ownership

Evidence date: 2026-10-29. Filesystem inspection was read-only. Docker and systemd
evidence was supplied by the operator from jarvis; the agent's environment cannot
access the Docker socket, system bus or netlink. `sudo` there fails because its
binary lacks the required root ownership/setuid configuration. No permissions or
services were changed to work around this restriction.

## Observed production

| Service | Image tag | Compose creation source |
| --- | --- | --- |
| app | risklive-app:8a6775ac9a5c | risklive-dev/.worktrees/seca-v2-release |
| scheduler | risklive-app:8a6775ac9a5c | risklive-dev/.worktrees/seca-v2-release |
| web | risklive-web:8a42195ba06d | risklive-dev/.worktrees/seca-v2-prod |
| caddy | caddy:2.8.4-alpine | risklive-dev |

All paths above are relative to `/home/azureuser`; each creation label names
`deployment/compose/docker-compose.prod.yml` in that checkout. Compose lists one
project, `risklive-prod`, aggregating those files across its four containers.
This is service creation history, not evidence of a three-file overlay command.

App/web/Caddy were healthy; scheduler was running. All four containers join only
`risklive-prod_internal`. Only Caddy publishes a host port: `0.0.0.0:8888` to
container TCP 80. Image-declared 443/2019 ports are not host-published ports.

App and scheduler bind `/opt/risklive/data/{results,logs,runtime}` read/write.
Web binds results and logs read-only. Caddy binds
`/home/azureuser/risklive-dev/deployment/caddy/Caddyfile.prod` read-only and uses
the named volumes `risklive-prod_caddy_data` and `risklive-prod_caddy_config`.
The host services `caddy.service` and `caddy-api.service` are inactive and disabled.
`docker.service` is active and enabled. Host Caddy is not the observed ingress.
Do not enable it alongside container ingress: both configurations use port 8888.

## Authoritative configuration

The release and web worktrees have identical production Compose bytes. Their
configuration is already committed in the application repository. The main
checkout's newer Compose adds optional Liwan analytics; no Liwan container or
analytics network was observed. The currently mounted Caddyfile comes from this
newer checkout. Its on-disk content is pinned separately, without copying it.

`risklive-infra` uses the release worktree's four-service base, existing image
references and a single host-specific Caddy path override. The original three
checkouts and creation labels are retained in `release.json`. No existing Compose
file is moved, overwritten, duplicated here or removed from application Git.
Switching production to this reconstruction model would change creation labels
and potentially inherited runtime settings; it requires a separately reviewed
deployment. This task does not perform that switch.

The application checkout `/opt/risklive/repo` is an older, different Git clone at
`4b46d279814d7d62e921d28184a37b10c431bbf0`. Its Compose is not the source named
by current production containers. Its relative mounts, latest-tag defaults,
80/443 publishing and older Caddy assumptions must not replace the observed stack.
Another clone exists at `/home/azureuser/opt/risklive/repo/risklive`; it is also
not named by current production labels. Both clones and the main worktree have
unrelated changes, which this task leaves alone.

`/etc/caddy/Caddyfile` and its backup are legacy, unversioned host files. The
inactive file forwards localhost 5001/3000; current containers do not publish
those ports. The backup and older tracked Caddy configurations contain password
hashes, so they are not imported. No custom RiskLive service, cron or logrotate
configuration was found in accessible `/etc/systemd/system`, `/etc/cron.d`,
`/etc/logrotate.d` or `/usr/local/bin`. This does not establish the absence of
privileged or external automation.

## Development and external state

The clean `/home/azureuser/risklive-on-demand-dev` worktree at
`e1f28218f857362c890d1648062d27b7ce2585ef` already tracks the production base,
smoke/dev/live overlays, `dev.sh`, validators and templates. It shares Git history
with `/home/azureuser/risklive-dev`. No development containers appeared in
`docker ps -a`. `/opt/risklive/dev-data` exists with its development marker and
separate env/results/logs/runtime/Caddy directories. Development image existence
and IDs are unverified; `:local` references in the manifest are helper defaults,
not observed binary pins.

Real environment files exist at `/opt/risklive/data/env` and
`/opt/risklive/dev-data/env`, including separate dev `live.env`. Values containing
credentials were not copied. Production's Azure key names differ from older
upstream examples; the host app template records that delta with placeholders.
Production Caddy's on-disk environment file sets `CADDY_SITE_ADDRESS=http://:80`.
No inspected deployment/env directory entries were symlinks.

`/opt/risklive/{results,logs,runtime}` are additional distinct directories, not
aliases of `data/`. They are not mounted by the observed containers. Backups live
under `/opt/risklive/backups`; their completeness and restoreability are unknown.
Do not delete, consolidate or import any of these directories.

## Remaining limits

Docker labels do not preserve the original env-file paths, shell exports or all
creation arguments. Existing host env files are reconstruction inputs, not proof
of current container environment. Do not publicly dump `docker inspect` or Env.
Caddy's on-disk file may differ from its loaded runtime configuration. Image IDs
are known, but registry manifest digests, image archives and platform were not
collected. The pasted socket command was swallowed by the systemctl pager; Docker
inspect still establishes the published binding. Azure NSGs/firewalls, DNS,
external jobs, exact development images and backup validation remain unresolved.
