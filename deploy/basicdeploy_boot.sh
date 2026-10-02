#!/bin/sh
set -eu

ROOT="${SHOREFRONT_ROOT:-/workspace/shorefront}"
TOOLS=/workspace/.shorefront-tools
VENV="$ROOT/apps/api/.venv"
SCHEMA="${SHOREFRONT_DB_SCHEMA-${PORTFLOW_DB_SCHEMA-}}"
LOCKDIR=/workspace/.shorefront-boot.lock

# Never infer a new database schema from a renamed deployment folder.
: "${SCHEMA:?Set SHOREFRONT_DB_SCHEMA explicitly; upgrades must select the existing schema}"
case "$SCHEMA" in
  *[!a-zA-Z0-9_]*|[0-9]*) echo "invalid SHOREFRONT_DB_SCHEMA" >&2; exit 2 ;;
esac
if [ "${#SCHEMA}" -gt 63 ]; then
  echo "SHOREFRONT_DB_SCHEMA is too long" >&2
  exit 2
fi
export SHOREFRONT_DB_SCHEMA="$SCHEMA"
if [ "${SHOREFRONT_BOOT_PREFLIGHT_ONLY:-0}" = "1" ]; then
  echo "preflight=ok (schema configuration only; no database connection checked)"
  exit 0
fi

acquire_boot_lock() {
  if mkdir "$LOCKDIR" 2>/dev/null; then
    echo "$$" > "$LOCKDIR/pid"
    return 0
  fi

  old_pid=""
  if [ -f "$LOCKDIR/pid" ]; then
    old_pid="$(cat "$LOCKDIR/pid" 2>/dev/null || true)"
  fi
  if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
    exit 0
  fi

  rm -rf "$LOCKDIR"
  if ! mkdir "$LOCKDIR" 2>/dev/null; then
    exit 0
  fi
  echo "$$" > "$LOCKDIR/pid"
}

acquire_boot_lock
mkdir -p "$TOOLS/bin"

if [ ! -x "$TOOLS/bin/uv" ]; then
  curl -LsSf https://astral.sh/uv/install.sh \
    | env UV_INSTALL_DIR="$TOOLS/bin" sh
fi

UV="$TOOLS/bin/uv"

if [ ! -x "$VENV/bin/python" ]; then
  "$UV" python install 3.13
  cd "$ROOT/apps/api"
  "$UV" sync --frozen --no-dev --no-install-project \
    --python 3.13
fi

RAW_DATABASE_URL="${DATABASE_URL:?BasicDeploy must provide DATABASE_URL}"

"$VENV/bin/python" - <<'PY'
import os
import psycopg

schema = os.environ["SHOREFRONT_DB_SCHEMA"]
if not schema.replace("_", "").isalnum():
    raise SystemExit("invalid SHOREFRONT_DB_SCHEMA")

with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
    conn.commit()
PY

export DATABASE_URL="$("$VENV/bin/python" - <<'PY'
import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

schema = os.environ["SHOREFRONT_DB_SCHEMA"]
parts = urlsplit(os.environ["DATABASE_URL"])
scheme = parts.scheme
if scheme in {"postgres", "postgresql"}:
    scheme = "postgresql+psycopg"
elif scheme != "postgresql+psycopg":
    raise SystemExit(f"unsupported DATABASE_URL scheme: {scheme}")

query = dict(parse_qsl(parts.query, keep_blank_values=True))
query["options"] = f"-csearch_path={schema}"
print(urlunsplit((
    scheme,
    parts.netloc,
    parts.path,
    urlencode(query),
    parts.fragment,
)))
PY
)"

export PYTHONPATH="$ROOT/apps/api/src"
export SHOREFRONT_SCHEMA_MODE=verify
export SHOREFRONT_STATIC_DIR="$ROOT/apps/web/dist"
export SHOREFRONT_PUBLIC_MODE=1
export SHOREFRONT_APPROVERS_JSON="${SHOREFRONT_APPROVERS_JSON-${PORTFLOW_APPROVERS_JSON-[]}}"
export SHOREFRONT_INTEGRATIONS_JSON="${SHOREFRONT_INTEGRATIONS_JSON-${PORTFLOW_INTEGRATIONS_JSON-[]}}"

cd "$ROOT/apps/api"
"$VENV/bin/python" -m shorefront_api.migrate

exec "$VENV/bin/python" -m uvicorn shorefront_api.main:app \
  --host 0.0.0.0 \
  --port 8080 \
  --proxy-headers \
  --forwarded-allow-ips='*'
