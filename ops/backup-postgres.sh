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

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${1:-$ROOT/backups/portflow-$STAMP.dump}"

mkdir -p "$(dirname "$OUT")"
"${COMPOSE[@]}" exec -T postgres \
  pg_dump -U portflow -d portflow -Fc > "$OUT"

test -s "$OUT"
echo "backup=$OUT"
