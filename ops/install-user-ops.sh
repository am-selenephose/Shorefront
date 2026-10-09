#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${SHOREFRONT_ENV_FILE:?Set SHOREFRONT_ENV_FILE to the operational environment file}"
: "${SHOREFRONT_COMPOSE_PROJECT:?Set SHOREFRONT_COMPOSE_PROJECT to the operational Compose project}"
BACKUP_DIR="${SHOREFRONT_BACKUP_DIR:-$HOME/.local/share/shorefront/backups}"
RETENTION_DAYS="${SHOREFRONT_BACKUP_RETENTION_DAYS:-14}"
[[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]] || { echo "invalid retention days" >&2; exit 2; }
[[ -f "$SHOREFRONT_ENV_FILE" ]] || { echo "environment file not found" >&2; exit 2; }
for value in "$ROOT" "$SHOREFRONT_ENV_FILE" "$SHOREFRONT_COMPOSE_PROJECT" "$BACKUP_DIR"; do
  [[ "$value" != *$'\n'* ]] || { echo "newline in systemd value is not supported" >&2; exit 2; }
done

unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$unit_dir" "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

cat > "$unit_dir/shorefront-operational-health.service" <<UNIT
[Unit]
Description=Shorefront operational health verification
After=default.target

[Service]
Type=oneshot
Environment="SHOREFRONT_ENV_FILE=$SHOREFRONT_ENV_FILE"
Environment="SHOREFRONT_COMPOSE_PROJECT=$SHOREFRONT_COMPOSE_PROJECT"
ExecStart="$ROOT/ops/operational-healthcheck.sh"
UNIT

cat > "$unit_dir/shorefront-operational-health.timer" <<'UNIT'
[Unit]
Description=Check Shorefront operational health every five minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
AccuracySec=30s
Persistent=true

[Install]
WantedBy=timers.target
UNIT

cat > "$unit_dir/shorefront-operational-backup.service" <<UNIT
[Unit]
Description=Shorefront operational PostgreSQL backup
After=default.target

[Service]
Type=oneshot
Environment="SHOREFRONT_ENV_FILE=$SHOREFRONT_ENV_FILE"
Environment="SHOREFRONT_COMPOSE_PROJECT=$SHOREFRONT_COMPOSE_PROJECT"
Environment="SHOREFRONT_BACKUP_DIR=$BACKUP_DIR"
Environment="SHOREFRONT_BACKUP_RETENTION_DAYS=$RETENTION_DAYS"
ExecStart="$ROOT/ops/scheduled-backup.sh"
UNIT

cat > "$unit_dir/shorefront-operational-backup.timer" <<'UNIT'
[Unit]
Description=Create a daily Shorefront operational backup

[Timer]
OnCalendar=daily
RandomizedDelaySec=30min
Persistent=true

[Install]
WantedBy=timers.target
UNIT

chmod 600 "$unit_dir"/shorefront-operational-*.service "$unit_dir"/shorefront-operational-*.timer
systemctl --user daemon-reload
systemctl --user enable --now shorefront-operational-health.timer shorefront-operational-backup.timer
printf 'installed health_timer=%s backup_timer=%s backup_dir=%s retention_days=%s\n' \
  shorefront-operational-health.timer shorefront-operational-backup.timer "$BACKUP_DIR" "$RETENTION_DAYS"
