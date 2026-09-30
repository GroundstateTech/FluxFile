#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "FluxFile requires Python 3.10+." >&2
  exit 1
fi

if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "FluxFile requires Python 3.10+; found $(python3 --version 2>&1)." >&2
  exit 1
fi

if [ -d .venv ] && [ ! -x .venv/bin/python ]; then
  echo "FluxFile: incomplete virtual environment detected; rebuilding .venv..."
  rm -rf .venv
fi

if [ ! -x .venv/bin/python ]; then
  echo "FluxFile: creating Python virtual environment..."
  if ! python3 -m venv .venv; then
    echo >&2
    echo "FluxFile could not create .venv." >&2
    echo "On Ubuntu, install the required packages with:" >&2
    echo "  sudo apt update && sudo apt install -y python3-venv python3-pip python3-tk" >&2
    exit 1
  fi
fi

.venv/bin/python scripts/bootstrap.py
exec .venv/bin/python fluxfile.py
