#!/usr/bin/env bash
# illo.app.erase @ 1.0.0
# predicate: erase-to-intersection keeps its topology (7 invariants)
# The owner's own rule: erase to intersection was tested before it existed.
# A new feature must not silently change what a cut removes.
set -uo pipefail
REPO="${1:?repo}"
out=$(cd "$REPO" && node .erase-test.mjs 2>&1)
tail -1 <<< "$out"
grep -q "^7/7 passed" <<< "$out" || {
  echo "FAILURE_TYPE: ASSERTION"
  echo "$out" | grep -E "^(PASS|FAIL)" | grep FAIL
  exit 1
}
