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

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${1:-$ROOT/backups/shorefront-$STAMP.dump}"

mkdir -p "$(dirname "$OUT")"
"${COMPOSE[@]}" exec -T postgres \
  sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$OUT"

test -s "$OUT"
echo "backup=$OUT"
