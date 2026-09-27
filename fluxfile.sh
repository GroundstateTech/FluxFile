#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "FluxFile requires Python 3.10+." >&2
  exit 1
fi

if [ -d .venv ] && [ ! -f .venv/bin/activate ]; then
  echo "FluxFile: incomplete virtual environment detected; rebuilding .venv..."
  rm -rf .venv
fi

if [ ! -f .venv/bin/activate ]; then
  echo "FluxFile: creating Python virtual environment..."
  if ! python3 -m venv .venv; then
    echo >&2
    echo "FluxFile could not create .venv." >&2
    echo "On Ubuntu, install the virtual-environment package with:" >&2
    echo "  sudo apt update && sudo apt install -y python3-venv python3-pip python3-tk" >&2
    exit 1
  fi
fi

# shellcheck disable=SC1091
. .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

exec python fluxfile.py
