#!/bin/sh
set -eu

ROOT=/workspace/portflow
TOOLS=/workspace/.portflow-tools
VENV="$ROOT/apps/api/.venv"
SCHEMA="${PORTFLOW_DB_SCHEMA:-portflow_portfolio}"
LOCKDIR=/workspace/.portflow-boot.lock

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

schema = os.environ.get("PORTFLOW_DB_SCHEMA", "portflow_portfolio")
if not schema.replace("_", "").isalnum():
    raise SystemExit("invalid PORTFLOW_DB_SCHEMA")

with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
    conn.commit()
PY

export DATABASE_URL="$("$VENV/bin/python" - <<'PY'
import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

schema = os.environ.get("PORTFLOW_DB_SCHEMA", "portflow_portfolio")
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
export PORTFLOW_SCHEMA_MODE=verify
export PORTFLOW_STATIC_DIR="$ROOT/apps/web/dist"
export PORTFLOW_PUBLIC_MODE=1
export PORTFLOW_APPROVERS_JSON="${PORTFLOW_APPROVERS_JSON:-[]}"
export PORTFLOW_INTEGRATIONS_JSON="${PORTFLOW_INTEGRATIONS_JSON:-[]}"

cd "$ROOT/apps/api"
"$VENV/bin/python" -m portflow_api.migrate

exec "$VENV/bin/python" -m uvicorn portflow_api.main:app \
  --host 0.0.0.0 \
  --port 8080 \
  --proxy-headers \
  --forwarded-allow-ips='*'
