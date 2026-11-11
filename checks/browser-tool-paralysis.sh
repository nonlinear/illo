#!/usr/bin/env bash
# illo.app.tool-paralysis runner @ 1.0.0
set -uo pipefail
REPO="${1:?repo}"
if ! python3 -c "import playwright" 2>/dev/null; then
  echo "FAILURE_TYPE: ENVIRONMENT"
  echo "python playwright not installed — the gesture simulation cannot run"
  exit 1
fi
exec python3 "$REPO/checks/browser-tool-paralysis.py" "$REPO"
