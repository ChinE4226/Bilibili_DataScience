#!/bin/bash
# One-click launcher for main/main.py (macOS double-clickable .command)
# All comments and output are in English.

set -euo pipefail

# Change to the repository directory (script location)
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR" || exit 1
MAIN_SCRIPT="$ROOT_DIR/main/main.py"

if [ ! -f "$MAIN_SCRIPT" ]; then
  echo "Error: main.py was not found at $MAIN_SCRIPT." >&2
  exit 1
fi

# Try to activate a virtual environment if present
if [ -f "$ROOT_DIR/.venv/bin/activate" ]; then
  echo "Activating virtual environment from .venv"
  # shellcheck source=/dev/null
  source "$ROOT_DIR/.venv/bin/activate"
elif [ -f "$ROOT_DIR/venv/bin/activate" ]; then
  echo "Activating virtual environment from venv"
  source "$ROOT_DIR/venv/bin/activate"
fi

# Prefer python3, fallback to python
PY=python3
if ! command -v "$PY" >/dev/null 2>&1; then
  PY=python
fi

if ! command -v "$PY" >/dev/null 2>&1; then
  echo "Error: Python is not installed or not in PATH." >&2
  exit 1
fi

# Run main.py with forwarded arguments and unbuffered output
echo "Starting main/main.py (using $PY) ..."
if "$PY" -u "$MAIN_SCRIPT" "$@"; then
  echo "main.py exited successfully."
else
  EXIT_CODE=$?
  echo "main.py exited with code $EXIT_CODE" >&2
  exit "$EXIT_CODE"
fi
