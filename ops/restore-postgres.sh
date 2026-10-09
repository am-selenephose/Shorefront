#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE=(docker compose)
if [[ -n "${SHOREFRONT_ENV_FILE-${PORTFLOW_ENV_FILE-}}" ]]; then
  COMPOSE+=(--env-file "${SHOREFRONT_ENV_FILE-${PORTFLOW_ENV_FILE-}}")
elif [[ -f "$ROOT/.env" ]]; then
  COMPOSE+=(--env-file "$ROOT/.env")
fi
if [[ -n "${SHOREFRONT_COMPOSE_PROJECT-${PORTFLOW_COMPOSE_PROJECT-}}" ]]; then
  COMPOSE+=(-p "${SHOREFRONT_COMPOSE_PROJECT-${PORTFLOW_COMPOSE_PROJECT-}}")
fi
COMPOSE+=(-f "$ROOT/docker-compose.prod.yml")
if [[ "${SHOREFRONT_UPGRADE:-0}" == "1" ]]; then
  PROJECT="${SHOREFRONT_COMPOSE_PROJECT-${PORTFLOW_COMPOSE_PROJECT-}}"
  : "${PROJECT:?Set the existing Compose project for upgrade}"
  COMPOSE+=(-f "$ROOT/docker-compose.upgrade.yml")
fi
if [[ "${SHOREFRONT_OPERATIONAL:-0}" == "1" ]]; then
  COMPOSE+=(-f "$ROOT/docker-compose.operational.yml")
fi
if [[ "${SHOREFRONT_TLS:-0}" == "1" ]]; then
  COMPOSE+=(-f "$ROOT/docker-compose.tls.yml")
fi

DUMP="${1:-}"

if [[ -z "$DUMP" || ! -s "$DUMP" ]]; then
  echo "usage: SHOREFRONT_RESTORE_CONFIRM=YES $0 /path/to/shorefront.dump" >&2
  exit 2
fi

if [[ "${SHOREFRONT_RESTORE_CONFIRM-${PORTFLOW_RESTORE_CONFIRM-}}" != "YES" ]]; then
  echo "restore refused: set SHOREFRONT_RESTORE_CONFIRM=YES" >&2
  exit 3
fi

case "${SHOREFRONT_OPERATIONAL-}" in
  0|1) ;;
  *)
    echo "restore refused: explicitly set SHOREFRONT_OPERATIONAL=1 for customer data or =0 for an isolated training database" >&2
    exit 4
    ;;
esac

# Validate required owner/origin, volume and TLS settings before stopping services
# or loading any database bytes. -q avoids printing resolved credentials.
"${COMPOSE[@]}" config -q
"${COMPOSE[@]}" stop web api
"${COMPOSE[@]}" exec -T postgres \
  sh -c 'exec pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --exit-on-error --single-transaction' < "$DUMP"
"${COMPOSE[@]}" run --rm migrate
"${COMPOSE[@]}" up -d api web

echo "restore=complete"
