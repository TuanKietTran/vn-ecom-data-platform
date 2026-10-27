#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose_file="$repo_root/docker/compose.yml"
env_file="$repo_root/.env.example"
profiles=(
  core,dagster
  core,airflow
  core,dagster,full
  core,airflow,full
)

if ! command -v docker >/dev/null 2>&1; then
  echo "error: docker is required to validate compose profiles" >&2
  exit 127
fi

for profile_set in "${profiles[@]}"; do
  COMPOSE_PROFILES="$profile_set" docker compose --env-file "$env_file" -f "$compose_file" config --quiet
  printf 'ok %s\n' "$profile_set"
done
