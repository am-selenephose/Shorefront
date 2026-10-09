#!/bin/sh
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-/tmp/shorefront-public-deploy.tgz}"
TMP="$(mktemp -d)"

cleanup() {
  rm -rf "$TMP"
}
trap cleanup EXIT HUP INT TERM

if [ ! -f "$ROOT/apps/web/dist/index.html" ]; then
  echo "missing apps/web/dist/index.html; run the web production build first" >&2
  exit 2
fi

mkdir -p   "$TMP/shorefront/deploy"   "$TMP/shorefront/apps/api"   "$TMP/shorefront/apps/web/dist"

cp "$ROOT/deploy/basicdeploy_boot.sh" "$TMP/shorefront/deploy/"
cp "$ROOT/deploy/basicdeploy_prepare.sh" "$TMP/shorefront/deploy/"

(
  cd "$ROOT/apps/api"
  tar     --exclude='*/__pycache__'     --exclude='*.pyc'     --exclude='.venv'     -cf -     src pyproject.toml uv.lock
) | (
  cd "$TMP/shorefront/apps/api"
  tar -xf -
)

cp -R "$ROOT/apps/web/dist/." "$TMP/shorefront/apps/web/dist/"

chmod +x   "$TMP/shorefront/deploy/basicdeploy_boot.sh"   "$TMP/shorefront/deploy/basicdeploy_prepare.sh"

tar -czf "$OUT" -C "$TMP" shorefront

if tar -tzf "$OUT" | grep -q '/.venv/'; then
  echo "bundle unexpectedly contains .venv" >&2
  exit 3
fi
if tar -tzf "$OUT" | grep -q '__pycache__'; then
  echo "bundle unexpectedly contains __pycache__" >&2
  exit 4
fi

echo "bundle=$OUT"
sha256sum "$OUT"
