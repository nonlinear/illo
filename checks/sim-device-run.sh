#!/usr/bin/env bash
# illo.sim.device runner @ 1.0.0
# The check CONTRACT is checks/definitions/sim/device.yaml; this is one way to satisfy it.
# Missing Playwright → ENVIRONMENT (never PASS, never FAIL): an unexercised property is
# not a proven property, but an absent instrument is not a product regression either.
set -uo pipefail
REPO="${1:?repo}"
if ! python3 -c "import playwright" 2>/dev/null; then
  echo "FAILURE_TYPE: ENVIRONMENT"
  echo "python playwright not installed — the device simulation cannot run"
  exit 1
fi
exec python3 "$REPO/checks/sim-device.py"
