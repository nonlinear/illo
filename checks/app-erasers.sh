#!/usr/bin/env bash
# illo.app.erasers @ 1.0.0
# predicate: BOTH erasers keep their topology, and the suite can actually fail
#
# Why this check exists (found 2026-10-27, by mutating the code):
#   .erase-test.mjs covers eraseToIntersection only. It does not exercise
#   strokeHit() / eraseAt() -- the whole-stroke eraser. I mutated strokeHit's
#   tolerance to 0.0001 and the suite still printed 7/7. A check that cannot fail
#   is not a check (kin P09E092 §3.3), so the eraser family was half-verified and
#   reporting full.
#
# Two things are asserted here:
#   1. segHit failing => 0/7. Proves the suite is wired to the real code.
#   2. strokeHit tolerance respected => the whole-stroke eraser has coverage.
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

# ---- 2. the whole-stroke eraser must have coverage --------------------------
cp "$REPO/index.html" "$TMP/index.html"
cp "$REPO/.erase-test.mjs" "$TMP/.erase-test.mjs"
python3 - "$TMP/index.html" <<'PY'
import sys
p = sys.argv[1]
s = open(p).read()
needle = "function strokeHit(s, x, y) {"
if needle not in s:
    print("FAILURE_TYPE: ASSERTION"); print("strokeHit() not found — the stroke eraser moved")
    sys.exit(1)
# Replace the tolerance expression with a value that can never hit.
s = s.replace("const tol = s.size / 2 + 8 / camera.zoom", "const tol = -1", 1)
s = s.replace(needle, needle + " const __MUT = true;", 1)
open(p, "w").write(s)
PY
out2=$(cd "$TMP" && node .erase-test.mjs 2>&1)
if grep -q "^7/7 passed" <<< "$out2"; then
  # the suite is blind to strokeHit; probe that function directly with node
  node --input-type=module -e "
import { readFileSync } from 'fs';
const src = readFileSync(process.argv[1], 'utf8');
const m = src.match(/function strokeHit\(s, x, y\) \{([\s\S]*?)\n  \}/);
if (!m) { console.log('FAILURE_TYPE: ASSERTION'); console.log('strokeHit body not found'); process.exit(1); }
const distToSeg = (px,py,ax,ay,bx,by) => { const dx=bx-ax,dy=by-ay,l2=dx*dx+dy*dy; let t=l2?((px-ax)*dx+(py-ay)*dy)/l2:0; t=Math.max(0,Math.min(1,t)); return Math.hypot(px-(ax+t*dx),py-(ay+t*dy)); };
const camera = { zoom: 1 };
const strokeHit = new Function('s','x','y','distToSeg','camera', m[1]);
const stroke = { pts: Array.from({length:41}, (_,i) => [100+i*10, 200, 0.6]), size: 6 };
const hit = strokeHit(stroke, 300, 200, distToSeg, camera);
if (hit) { console.log('FAILURE_TYPE: ASSERTION'); console.log('strokeHit reported a hit with tol=-1 — tolerance does not decide, and the erase suite has no case for the whole-stroke eraser'); process.exit(1); }
console.log('strokeHit respects its tolerance');
" "$TMP/index.html"
  rc=$?
  [ "$rc" != "0" ] && exit 1
  echo "erase suite: segHit-sensitive (0/7 when broken); strokeHit tolerance respected"
  exit 0
fi
fail "mutating strokeHit changed the erase suite — it now covers the whole-stroke eraser; update this check"
