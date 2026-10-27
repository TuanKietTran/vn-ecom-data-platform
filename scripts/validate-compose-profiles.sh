#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose_file="$repo_root/docker/compose.yml"
env_file="$repo_root/.env.example"
# AISettings fields in src/vnecom/ai/config.py are exposed with this prefix.
ai_settings=(ENABLED PROVIDER BASE_URL API_KEY MODEL TIMEOUT_S)
profiles=(
  core,dagster
  core,airflow
  core,dagster,full
  core,airflow,full
  core,dagster,ai
  core,airflow,ai
  core,dagster,full,ai
  core,airflow,full,ai
)

if ! command -v docker >/dev/null 2>&1; then
  echo "error: docker is required to validate compose profiles" >&2
  exit 127
fi

compose=(docker compose --env-file "$env_file" -f "$compose_file")

assert_service() {
  local services="$1" expected="$2" profile_set="$3"
  if ! grep -Fxq "$expected" <<<"$services"; then
    echo "error: profile '$profile_set' is missing expected service '$expected'" >&2
    exit 1
  fi
}

assert_absent() {
  local services="$1" unexpected="$2" profile_set="$3"
  if grep -Fxq "$unexpected" <<<"$services"; then
    echo "error: profile '$profile_set' unexpectedly exposes service '$unexpected'" >&2
    exit 1
  fi
}

default_services="$(env -u COMPOSE_PROFILES "${compose[@]}" config --services)"
assert_absent "$default_services" ai-api default
printf 'ok default (ai-api excluded)\n'

for profile_set in "${profiles[@]}"; do
  services="$(COMPOSE_PROFILES="$profile_set" "${compose[@]}" config --services)"
  COMPOSE_PROFILES="$profile_set" "${compose[@]}" config --quiet
  if [[ ",$profile_set," == *,ai,* ]]; then
    assert_service "$services" ai-api "$profile_set"
    config_json="$(COMPOSE_PROFILES="$profile_set" "${compose[@]}" config --format json)"
    for setting in "${ai_settings[@]}"; do
      if ! grep -Fq "\"VNECOM_AI_${setting}\":" <<<"$config_json"; then
        echo "error: profile '$profile_set' does not pass VNECOM_AI_${setting} to ai-api" >&2
        exit 1
      fi
    done
  else
    assert_absent "$services" ai-api "$profile_set"
  fi
  if [[ ",$profile_set," == *,dagster,* ]]; then
    assert_service "$services" dagster-webserver "$profile_set"
  else
    assert_absent "$services" dagster-webserver "$profile_set"
  fi
  if [[ ",$profile_set," == *,airflow,* ]]; then
    assert_service "$services" airflow-apiserver "$profile_set"
  else
    assert_absent "$services" airflow-apiserver "$profile_set"
  fi
  if [[ ",$profile_set," == *,full,* ]]; then
    assert_service "$services" trino "$profile_set"
    assert_service "$services" redpanda "$profile_set"
  else
    assert_absent "$services" trino "$profile_set"
    assert_absent "$services" redpanda "$profile_set"
  fi
  printf 'ok %s\n' "$profile_set"
done
