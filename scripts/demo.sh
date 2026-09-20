#!/usr/bin/env bash
# Run the whole system in demo mode: no VM, no NemoClaw, no credentials.
#
#   ./scripts/demo.sh     agent host on :8000, Glass Box on :3000
#
# DEMO_LOOP keeps the scripted session running so a recording does not go
# quiet halfway through a take.
set -euo pipefail
cd "$(dirname "$0")/.."

export DEMO=true
export DEMO_LOOP="${DEMO_LOOP:-1}"

if [ ! -d apps/glassbox/node_modules ]; then
  echo "Installing Glass Box dependencies..."
  npm install --prefix apps/glassbox --no-audit --no-fund
fi

echo "First start takes ~30s while Next compiles. Ctrl-C stops both."
python -m apps.host &
HOST_PID=$!
trap 'kill $HOST_PID 2>/dev/null || true' EXIT

npm run dev --prefix apps/glassbox
