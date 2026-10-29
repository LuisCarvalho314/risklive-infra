#!/usr/bin/env bash
# Read-only operator evidence. Never print container Env, args or arbitrary labels.
set -euo pipefail
docker_command=(docker)
if [[ $# == 1 && $1 == --sudo ]]; then
  docker_command=(sudo docker)
elif [[ $# != 0 ]]; then
  echo 'Usage: inspect-live.sh [--sudo]' >&2
  exit 2
fi
"${docker_command[@]}" ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
"${docker_command[@]}" compose ls --all --format json
ids=()
container_ids=$("${docker_command[@]}" ps -aq)
while IFS= read -r id; do
  [[ -z "$id" ]] || ids+=("$id")
done <<< "$container_ids"
if [[ ${#ids[@]} -gt 0 ]]; then
  "${docker_command[@]}" inspect --format '
name={{.Name}}
image_reference={{.Config.Image}}
image_id={{.Image}}
status={{.State.Status}}
compose_project={{index .Config.Labels "com.docker.compose.project"}}
compose_service={{index .Config.Labels "com.docker.compose.service"}}
compose_files={{index .Config.Labels "com.docker.compose.project.config_files"}}
compose_working_dir={{index .Config.Labels "com.docker.compose.project.working_dir"}}
network_mode={{.HostConfig.NetworkMode}}
networks={{range $name, $config := .NetworkSettings.Networks}}{{$name}} {{end}}
ports={{json .NetworkSettings.Ports}}
mounts={{json .Mounts}}
' "${ids[@]}"
fi
if [[ ${1:-} == --sudo ]]; then
  sudo systemctl --no-pager show caddy caddy-api docker --property=Id,LoadState,ActiveState,SubState,UnitFileState,FragmentPath,MainPID
  sudo ss -ltnp '( sport = :80 or sport = :443 or sport = :8888 or sport = :8188 or sport = :5001 or sport = :3000 or sport = :9042 )'
else
  systemctl --no-pager show caddy caddy-api docker --property=Id,LoadState,ActiveState,SubState,UnitFileState,FragmentPath,MainPID
  ss -ltnp '( sport = :80 or sport = :443 or sport = :8888 or sport = :8188 or sport = :5001 or sport = :3000 or sport = :9042 )'
fi
