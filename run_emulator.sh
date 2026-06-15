#!/usr/bin/env bash
# Launch the pistomp-recovery emulator (interactive pygame window) via uv.
# Any arguments are forwarded to the emulator, e.g.:
#   ./run_emulator.sh --force-crash
#   ./run_emulator.sh --log DEBUG
set -euo pipefail

cd "$(dirname "$0")"
exec uv run pistomp-recovery-emulator "$@"
