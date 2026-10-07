#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${SHOREFRONT_ENV_FILE:?Set SHOREFRONT_ENV_FILE to the operational environment file}"
: "${SHOREFRONT_COMPOSE_PROJECT:?Set SHOREFRONT_COMPOSE_PROJECT to the operational Compose project}"
: "${SHOREFRONT_BACKUP_DIR:?Set SHOREFRONT_BACKUP_DIR to a protected backup directory}"
RETENTION_DAYS="${SHOREFRONT_BACKUP_RETENTION_DAYS:-14}"
[[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]] || { echo "invalid retention days" >&2; exit 2; }
[[ -f "$SHOREFRONT_ENV_FILE" ]] || { echo "environment file not found" >&2; exit 2; }

umask 077
mkdir -p "$SHOREFRONT_BACKUP_DIR"
chmod 700 "$SHOREFRONT_BACKUP_DIR"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
out="$SHOREFRONT_BACKUP_DIR/shorefront-$stamp.dump"

SHOREFRONT_OPERATIONAL=1 \
SHOREFRONT_ENV_FILE="$SHOREFRONT_ENV_FILE" \
SHOREFRONT_COMPOSE_PROJECT="$SHOREFRONT_COMPOSE_PROJECT" \
  "$ROOT/ops/backup-postgres.sh" "$out"
sha256sum "$out" > "$out.sha256"
chmod 600 "$out" "$out.sha256"
find "$SHOREFRONT_BACKUP_DIR" -maxdepth 1 -type f \
  \( -name "shorefront-*.dump" -o -name "shorefront-*.dump.sha256" \) \
  -mtime +"$RETENTION_DAYS" -delete
printf "backup_complete=%s retention_days=%s\n" "$out" "$RETENTION_DAYS"
