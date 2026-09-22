#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE=(docker compose)
if [[ -n "${PORTFLOW_ENV_FILE:-}" ]]; then
  COMPOSE+=(--env-file "$PORTFLOW_ENV_FILE")
elif [[ -f "$ROOT/.env" ]]; then
  COMPOSE+=(--env-file "$ROOT/.env")
fi
if [[ -n "${PORTFLOW_COMPOSE_PROJECT:-}" ]]; then
  COMPOSE+=(-p "$PORTFLOW_COMPOSE_PROJECT")
fi
COMPOSE+=(-f "$ROOT/docker-compose.prod.yml")

DUMP="${1:-}"

if [[ -z "$DUMP" || ! -s "$DUMP" ]]; then
  echo "usage: PORTFLOW_RESTORE_CONFIRM=YES $0 /path/to/portflow.dump" >&2
  exit 2
fi

if [[ "${PORTFLOW_RESTORE_CONFIRM:-}" != "YES" ]]; then
  echo "restore refused: set PORTFLOW_RESTORE_CONFIRM=YES" >&2
  exit 3
fi

"${COMPOSE[@]}" stop web api
"${COMPOSE[@]}" exec -T postgres \
  pg_restore -U portflow -d portflow --clean --if-exists --no-owner < "$DUMP"
"${COMPOSE[@]}" run --rm migrate
"${COMPOSE[@]}" up -d api web

echo "restore=complete"
