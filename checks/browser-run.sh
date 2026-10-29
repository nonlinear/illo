#!/usr/bin/env bash
# illo.app.browser-erase runner @ 1.0.0
# Wraps the Playwright probe so a missing browser reports ENVIRONMENT_BLOCKED instead of
# PASS or FAIL. An unrun check must never look like a passing one.
set -uo pipefail
REPO="${1:?repo}"
if ! python3 -c "import playwright" 2>/dev/null; then
  echo "FAILURE_TYPE: ENVIRONMENT"
  echo "python playwright not installed -- browser probe cannot run"
  exit 1
fi
exec python3 "$REPO/checks/browser-erase.py" "$REPO"
