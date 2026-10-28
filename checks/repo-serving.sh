#!/usr/bin/env bash
# illo.repo.serving @ 1.0.0
# predicate: the app is being served at 127.0.0.1:3003
# If this fails the fault is the harness or the machine, NOT the product.
set -uo pipefail
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:3003/ 2>/dev/null)
if [ "$code" != "200" ]; then
  echo "FAILURE_TYPE: ENVIRONMENT"
  echo "127.0.0.1:3003 returned '$code' (expected 200)"
  launchctl list 2>/dev/null | grep -i illo || echo "no illo launchd job found"
  exit 1
fi
echo "127.0.0.1:3003 → 200"
