#!/usr/bin/env bash
set -euo pipefail

ROOT=/workspace/portflow

if [[ ! -f "$ROOT/apps/api/pyproject.toml" ]]; then
  echo "PortFlow deploy bundle is missing apps/api/pyproject.toml" >&2
  exit 2
fi

if [[ ! -f "$ROOT/apps/web/dist/index.html" ]]; then
  echo "PortFlow deploy bundle is missing built apps/web/dist/index.html" >&2
  exit 3
fi

cp "$ROOT/deploy/basicdeploy_boot.sh" /workspace/.bd_boot.sh
chmod +x /workspace/.bd_boot.sh "$ROOT/deploy/basicdeploy_boot.sh"

exec /workspace/.bd_boot.sh
