#!/usr/bin/env bash
# illo.app.erase-finger runner @ 1.0.0
set -uo pipefail
REPO="${1:?repo}"
if ! python3 -c "import playwright" 2>/dev/null; then
  echo "FAILURE_TYPE: ENVIRONMENT"
  echo "python playwright not installed — the finger simulation cannot run"
  exit 1
fi
exec python3 "$REPO/checks/browser-erase-finger.py"
