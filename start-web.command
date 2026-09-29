#!/bin/bash
# One-click launcher for the local web server (macOS double-clickable .command)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR" || exit 1
WEB_SCRIPT="$ROOT_DIR/web_server.py"

if [ ! -f "$WEB_SCRIPT" ]; then
  echo "Error: web_server.py was not found at $WEB_SCRIPT." >&2
  exit 1
fi

if [ -f "$ROOT_DIR/.venv/bin/activate" ]; then
  echo "Activating virtual environment from .venv"
  # shellcheck source=/dev/null
  source "$ROOT_DIR/.venv/bin/activate"
elif [ -f "$ROOT_DIR/venv/bin/activate" ]; then
  echo "Activating virtual environment from venv"
  # shellcheck source=/dev/null
  source "$ROOT_DIR/venv/bin/activate"
fi

PY=python3
if ! command -v "$PY" >/dev/null 2>&1; then
  PY=python
fi

if ! command -v "$PY" >/dev/null 2>&1; then
  echo "Error: Python is not installed or not in PATH." >&2
  exit 1
fi

echo "Starting web_server.py with automatic reload. It will use http://127.0.0.1:8000 or the next free port."
"$PY" -u "$WEB_SCRIPT" --host 127.0.0.1 --port 8000 --open-browser --browser chrome "$@"
