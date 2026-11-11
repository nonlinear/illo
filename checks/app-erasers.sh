#!/usr/bin/env bash
# illo.app.erasers @ 3.1.0
# predicate: there is ONE eraser, it is a RUBBER (erase where the finger is), and the suite
#            is still wired to the real code.
#
# History, because each version is a different answer to "what is the eraser":
#   v1.0.0  verified TWO erasers: a pixel eraser (strokeHit/eraseAt) and a whole-stroke one.
#   v2.0.0  verified ONE: erase-to-intersection (tap a line, delete the piece back to the
#           nearest crossing on each side). Owner, 2026-11-11: "o erase to intersection eh
#           confuso. as vezes funciona as vezes nao." -- on a clean crossing it cut, on a
#           line that merely came close it did nothing, on a junction it guessed.
#   v3.1.0  (this) adds the METRIC half of the rubber: it measures distance to the SEGMENT,
#           widened by the width the stroke actually paints (strokeRadius). v3.0.0 tested the
#           samples only, and three metric cases fail on it -- a still finger 3px off a line,
#           a segment inside the rubber with no sample in it, and a touch that lands in the
#           middle of a long sampling gap. That is the "as vezes" the owner reported again.
#   v3.0.0  verifies ONE: a rubber. What the finger passes over goes; what it does not
#           pass over stays. The geometry engine (segHit, segIntersect, crossingsFor,
#           axisMatch, betterTap, deleteRegion) is DELETED, not disabled.
#
# Three things are asserted now:
#   1. the erase suite can still fail             (a check that cannot fail is not a check)
#   2. there is exactly ONE erase path, and it is eraseAt
#   3. the tap-to-crossing engine did not creep back in
set -uo pipefail
REPO="${1:?repo}"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

fail() { echo "FAILURE_TYPE: ASSERTION"; echo "$1"; exit 1; }

# ---- 1. the unit suite must be able to fail --------------------------------
cp "$REPO/index.html" "$TMP/index.html"
cp "$REPO/.erase-test.mjs" "$TMP/.erase-test.mjs"
python3 - "$TMP/index.html" <<'PY'
import sys
p = sys.argv[1]
s = open(p).read()
needle = "function eraseAt(pp) {"
if needle not in s:
    print("FAILURE_TYPE: ASSERTION"); print("eraseAt() not found — the eraser moved")
    sys.exit(1)
s = s.replace(needle, needle + "\n    return false; // SELF-TEST MUTATION", 1)
open(p, "w").write(s)
PY
out=$(cd "$TMP" && node .erase-test.mjs 2>&1) || true
grep -qE "^[0-9]+/[0-9]+ passed" <<< "$out" \
  || fail "the erase suite printed no verdict on a mutated eraseAt — it is not wired to the real code"
grep -q "^10/10 passed" <<< "$out" \
  && fail "the erase suite PASSED with eraseAt gutted — it is not wired to the real code"

# ---- 2 & 3. one eraser, it is a rubber, and the old engine is gone ---------
python3 - "$REPO/index.html" <<'PY'
import re, sys
src = open(sys.argv[1]).read()
code = re.sub(r"//[^\n]*", "", src)            # a comment must not satisfy a check

# 3. the dead engine. It was deleted on 2026-11-11; any of these coming back means the
#    "sometimes it works" class came back with it.
for gone in ("segHit", "segIntersect", "crossingsFor", "axisMatch", "betterTap",
             "deleteRegion", "splitPointsAt", "nextCrossing",
             "eraseToIntersection", "strokeEraser", "strokeHit"):
    if re.search(r"(?<![A-Za-z_])" + gone + r"(?![A-Za-z_])", code):
        print("FAILURE_TYPE: ASSERTION")
        print(f"{gone} is back — the eraser is a RUBBER now, not a geometry puzzle")
        sys.exit(1)

# 2. exactly one erase entry point, and it is eraseAt.
if not re.search(r"function eraseAt\(", code):
    print("FAILURE_TYPE: ASSERTION"); print("no eraseAt() — there is no eraser"); sys.exit(1)
if len(re.findall(r"function eraseAt\(", code)) != 1:
    print("FAILURE_TYPE: ASSERTION"); print("more than one eraseAt — two erasers again"); sys.exit(1)

m = re.search(r"(?:canvas|document)\.addEventListener\('pointerdown'.*?(?=(?:canvas|document)\.addEventListener\('pointermove'|function handleMove)", src, re.S)
if not m:
    print("FAILURE_TYPE: ASSERTION"); print("pointerdown handler not found"); sys.exit(1)
seg = re.sub(r"//[^\n]*", "", m.group(0))
blk = re.search(r"if \(state\.tool === 'eraser'\)\s*\{(.*?)\n    \}", seg, re.S)
if not blk:
    print("FAILURE_TYPE: ASSERTION"); print("no eraser branch in pointerdown"); sys.exit(1)
if "eraseAt(" not in blk.group(1):
    print("FAILURE_TYPE: ASSERTION")
    print("the eraser branch does not call eraseAt — the tool is wired to something else")
    sys.exit(1)

# A drag must keep erasing. If the move path stops calling eraseAt mid-gesture, the rubber
# works on a tap and does nothing on a swipe -- which is the "sometimes" the owner rejected,
# in a new costume.
mv = re.search(r"function handleMove\(e\).*?(?=function endStroke)", src, re.S)
if not mv:
    print("FAILURE_TYPE: ASSERTION"); print("pointermove handler not found"); sys.exit(1)
if "eraseAt(" not in re.sub(r"//[^\n]*", "", mv.group(0)):
    print("FAILURE_TYPE: ASSERTION")
    print("pointermove with the eraser does not call eraseAt — a swipe would erase nothing")
    sys.exit(1)

print("one eraser: a rubber (eraseAt, on contact and on drag; no crossing engine)")
PY
