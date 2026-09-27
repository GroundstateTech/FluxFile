#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
echo "FluxFile: run_fluxfile.sh is kept for compatibility; launching fluxfile.sh."
exec bash ./fluxfile.sh
