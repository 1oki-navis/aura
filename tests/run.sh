#!/bin/sh
# Runs every Stride suite: legacy stress (test_liftlog.py), v16, v20 and v23.
# Env overrides: STRIDE_APP (app folder), PY (python with Playwright),
# STRIDE_START / STRIDE_EXPORT (personal backups, never committed).
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
if [ -z "${STRIDE_APP:-}" ]; then
  if [ -f "$HERE/../index.html" ]; then STRIDE_APP="$(cd "$HERE/.." && pwd)"; else STRIDE_APP="$HOME/Downloads/gym-app"; fi
fi
export STRIDE_APP
VENV="$HOME/.copilot/session-state/c1fb52d9-6476-4d2e-a4a5-572348b68684/files/venv/bin/python"
if [ -z "${PY:-}" ]; then if [ -x "$VENV" ]; then PY="$VENV"; else PY=python3; fi; fi
START="${STRIDE_START:-$HOME/Library/Mobile Documents/com~apple~CloudDocs/Gym Plan/liftlog-start.json}"
EXPORT="${STRIDE_EXPORT:-$HERE/v22-export.json}"
for f in "$START" "$EXPORT"; do
  [ -f "$f" ] || { echo "Missing test data: $f (see tests/README.md)"; exit 2; }
done
cd "$STRIDE_APP"
if lsof -ti tcp:8765 >/dev/null 2>&1; then
  for p in $(lsof -ti tcp:8765); do kill "$p"; done
fi
python3 -m http.server 8765 >/dev/null 2>&1 &
PID=$!
trap 'kill "$PID" 2>/dev/null || true' EXIT
sleep 1
cd "$HERE"
# Keep going so every suite reports, then fail if any failed
RC=0
"$PY" test_liftlog.py || RC=1
# The other suites start their own server on 8765, so free the port first
kill "$PID" 2>/dev/null || true
sleep 1
"$PY" test_v16.py || RC=1
"$PY" test_v20.py || RC=1
"$PY" test_v23.py || RC=1
exit "$RC"
