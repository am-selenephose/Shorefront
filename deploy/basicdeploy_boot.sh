#!/usr/bin/env bash
set -euo pipefail

ROOT=/workspace/portflow
TOOLS=/workspace/.portflow-tools
VENV="$ROOT/apps/api/.venv"
SCHEMA="${PORTFLOW_DB_SCHEMA:-portflow_portfolio}"

mkdir -p "$TOOLS/bin"

if [[ ! -x "$TOOLS/bin/uv" ]]; then
  curl -LsSf https://astral.sh/uv/install.sh \
    | env UV_INSTALL_DIR="$TOOLS/bin" sh
fi

UV="$TOOLS/bin/uv"

if [[ ! -x "$VENV/bin/python" ]]; then
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
query = dict(parse_qsl(parts.query, keep_blank_values=True))
query["options"] = f"-csearch_path={schema}"
print(urlunsplit((
    parts.scheme,
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
export PORTFLOW_APPROVERS_JSON="${PORTFLOW_APPROVERS_JSON:-[]}"

cd "$ROOT/apps/api"
"$VENV/bin/python" -m portflow_api.migrate

exec "$VENV/bin/python" -m uvicorn portflow_api.main:app \
  --host 0.0.0.0 \
  --port 8080 \
  --proxy-headers \
  --forwarded-allow-ips='*'
