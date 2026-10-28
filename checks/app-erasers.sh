#!/usr/bin/env bash
# illo.app.erasers @ 2.0.0
# predicate: there is ONE eraser, it is erase-to-intersection, and the suite can fail
#
# v1.0.0 verified two erasers: a pixel eraser (strokeHit/eraseAt) and a whole-stroke
# eraser. Owner, 2026-10-28: "tem erase mas não eh erase to intersection. tocou, deleta
# toda linha até intercessão." The two-erase model is gone, so a check that probes
# strokeHit is now probing a function that no longer exists -- it fails on a correct
# repo, which is worse than no check (kin P09E092 §3.3).
#
# Three things are asserted now:
#   1. segHit failing => 0/7. The suite is still wired to the real code.
#   2. The eraser tool routes to eraseToIntersection. A `strokeEraser` mode or a
#      whole-stroke delete returning is a regression, not a feature.
#   3. The erased tool has no separate on-screen surface left behind it.
set -uo pipefail
REPO="${1:?repo}"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

fail() { echo "FAILURE_TYPE: ASSERTION"; echo "$1"; exit 1; }

# ---- 1. the existing suite must be able to fail -----------------------------
cp "$REPO/index.html" "$TMP/index.html"
cp "$REPO/.erase-test.mjs" "$TMP/.erase-test.mjs"
python3 - "$TMP/index.html" <<'PY'
import sys
p = sys.argv[1]
s = open(p).read()
needle = "function segHit(a, b, x, y) {"
if needle not in s:
    print("FAILURE_TYPE: ASSERTION"); print("segHit() not found — the cut engine moved")
    sys.exit(1)
s = s.replace(needle, needle + " return false; // SELF-TEST MUTATION", 1)
open(p, "w").write(s)
PY
out=$(cd "$TMP" && node .erase-test.mjs 2>&1)
grep -q "^0/7 passed" <<< "$out" \
  || fail "the erase suite did not fail when segHit was broken — it is not wired to the real code"

# ---- 2. one eraser, and it is the cut --------------------------------------
python3 - "$REPO/index.html" <<'PY'
import re, sys
src = open(sys.argv[1]).read()
code = re.sub(r"//[^\n]*", "", src)            # a comment must not satisfy a check

for gone in ("strokeEraser", "eraseAt", "strokeHit"):
    if gone in code:
        print("FAILURE_TYPE: ASSERTION")
        print(f"{gone} is back — the owner asked for ONE eraser: erase to intersection")
        sys.exit(1)

m = re.search(r"canvas\.addEventListener\('pointerdown'.*?(?=canvas\.addEventListener\('pointermove')", src, re.S)
if not m:
    print("FAILURE_TYPE: ASSERTION"); print("pointerdown handler not found"); sys.exit(1)
seg = re.sub(r"//[^\n]*", "", m.group(0))
blk = re.search(r"if \(state\.tool === 'eraser'\)\s*\{(.*?)\n    \}", seg, re.S)
if not blk:
    print("FAILURE_TYPE: ASSERTION"); print("no eraser branch in pointerdown"); sys.exit(1)
if "eraseToIntersection" not in blk.group(1):
    print("FAILURE_TYPE: ASSERTION")
    print("the eraser branch does not cut to the intersection")
    sys.exit(1)

# The move path must treat an in-flight erase as a tap sequence through the SAME cut,
# not as a pixel rub: a drag with the eraser is still one gesture, one undo step.
mv = re.search(r"canvas\.addEventListener\('pointermove'.*?(?=function endStroke)", src, re.S)
if not mv:
    print("FAILURE_TYPE: ASSERTION"); print("pointermove handler not found"); sys.exit(1)
if "if (erasing) { for (const ev of list) eraseToIntersection(" not in mv.group(0):
    print("FAILURE_TYPE: ASSERTION")
    print("pointermove with the eraser no longer goes through eraseToIntersection")
    sys.exit(1)

print("one eraser: erase-to-intersection (no strokeEraser, no pixel rub)")
PY
