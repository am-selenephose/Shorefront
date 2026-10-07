#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${SHOREFRONT_ENV_FILE:?Set SHOREFRONT_ENV_FILE to the operational environment file}"
: "${SHOREFRONT_COMPOSE_PROJECT:?Set SHOREFRONT_COMPOSE_PROJECT to the operational Compose project}"
[[ -f "$SHOREFRONT_ENV_FILE" ]] || { echo "environment file not found" >&2; exit 2; }

port="$(awk -F= '$1=="SHOREFRONT_HTTP_PORT"{print $2; exit}' "$SHOREFRONT_ENV_FILE")"
[[ "$port" =~ ^[0-9]+$ ]] || { echo "invalid SHOREFRONT_HTTP_PORT" >&2; exit 2; }
base="http://127.0.0.1:$port"
ready="$(curl --fail --silent --show-error --max-time 5 "$base/readyz")"
python - "$ready" <<'PY'
import json, sys
value = json.loads(sys.argv[1])
assert value.get("ok") is True, value
assert value.get("runtime_mode") == "operational", value
PY

metrics_status="$(curl --silent --output /dev/null --write-out '%{http_code}' --max-time 5 "$base/metrics")"
[[ "$metrics_status" == "404" ]] || { echo "public metrics endpoint unexpectedly returned $metrics_status" >&2; exit 1; }

compose=(docker compose --env-file "$SHOREFRONT_ENV_FILE" -p "$SHOREFRONT_COMPOSE_PROJECT" -f "$ROOT/docker-compose.prod.yml" -f "$ROOT/docker-compose.operational.yml")
running="$(${compose[@]} ps --status running --services)"
for service in postgres api web; do
  grep -qx "$service" <<<"$running" || { echo "service_not_running=$service" >&2; exit 1; }
done

internal_metrics="$(${compose[@]} exec -T api python - <<'PY'
from urllib.request import urlopen
body = urlopen("http://127.0.0.1:8100/metrics", timeout=5).read().decode()
print(body)
PY
)"
grep -q "shorefront_" <<<"$internal_metrics" || { echo "internal metrics payload missing Shorefront metrics" >&2; exit 1; }
printf 'health=ok runtime=operational services=postgres,api,web public_metrics=hidden\n'
