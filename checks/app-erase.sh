#!/usr/bin/env bash
# illo.app.erase @ 2.0.0
# predicate: the eraser is a RUBBER and it keeps its invariants (10 cases)
# Two generations of assertion live in .erase-test.mjs:
#   1-7  topology (a cut leaves two lines, a stub is dropped, nothing is announced)
#   8-10 METRIC   (a still finger a few px off the line erases it; a segment inside the rubber
#        erases even when no sample is; the answer does not depend on sample spacing)
# v2 exists because v1 passed 7/7 while the owner still had to say "as vezes funciona, as vezes
# nao" (2026-11-11). All three metric cases FAIL on the v1 eraseAt -- verified.
# The owner's own rule from the old era still holds: a cut was tested before it existed, and a
# new feature must not silently change what a cut removes.
set -uo pipefail
REPO="${1:?repo}"
out=$(cd "$REPO" && node .erase-test.mjs 2>&1)
tail -1 <<< "$out"
grep -q "^10/10 passed" <<< "$out" || {
  echo "FAILURE_TYPE: ASSERTION"
  echo "$out" | grep -E "^(PASS|FAIL)" | grep FAIL
  exit 1
}
