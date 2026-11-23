#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CP_DIR="$(cd "${APP_DIR}/../../services/control-plane" && pwd)"

echo "==> Ensuring Python Syncro Control Plane environment is ready..."
if [[ ! -x "${CP_DIR}/.venv/bin/syncro" ]]; then
  (
    cd "${CP_DIR}"
    if command -v uv >/dev/null 2>&1; then
      uv venv .venv
      uv pip install --python .venv/bin/python -e ".[dev]"
    else
      python3 -m venv .venv
      .venv/bin/pip install -e ".[dev]"
    fi
  )
fi

echo "==> Building Syncro Electron Desktop & native shared library..."
cd "${APP_DIR}"
[[ -d node_modules ]] || npm install
bash native/build-native.sh
npm run build

echo "==> Launching Syncro Deployer as a standalone native desktop window..."
exec npx electron .
