#!/usr/bin/env bash
# illo.app.pen-only @ 1.0.0
# predicate: a non-pen pointer cannot lay ink, and the gate precedes capture
# Both halves matter. Without the gate a mouse draws (owner: "não deveria").
# With the gate but AFTER setPointerCapture, the mouse holds the pointer and pan
# silently dies. Order is the property, not an implementation detail.
set -uo pipefail
REPO="${1:?repo}"
python3 - "$REPO/index.html" <<'PY'
import re, sys
src = open(sys.argv[1]).read()
m = re.search(r"(?:canvas|document)\.addEventListener\('pointerdown'.*?(?=(?:canvas|document)\.addEventListener\('pointermove'|function handleMove)", src, re.S)
if not m:
    print("FAILURE_TYPE: ASSERTION")
    print("pointerdown handler not found")
    sys.exit(1)
seg = m.group(0)
# strip comments so a comment mentioning a token cannot satisfy the check
code = re.sub(r"//[^\n]*", "", seg)
lines = [l for l in code.split("\n")]
def idx(pat):
    for i, l in enumerate(lines):
        if pat in l:
            return i
    return -1
# The gate moved from a pointerType literal to mayInk() (owner, 2026-10-27: "não dava pra
# desenhar sem caneta") — the PROPERTY is unchanged: a pointer that may not ink is refused
# before capture and before the stroke. Anchor on the call, not on its old spelling.
gate = idx("!mayInk(e)")
cap = idx("setPointerCapture")
draw = idx("drawing = {")
if gate < 0:
    print("FAILURE_TYPE: ASSERTION"); print("no pen gate in pointerdown"); sys.exit(1)
if draw >= 0 and gate > draw:
    print("FAILURE_TYPE: ASSERTION"); print("pen gate is AFTER the stroke is created"); sys.exit(1)
if cap >= 0 and gate > cap:
    print("FAILURE_TYPE: ASSERTION"); print("pen gate is AFTER setPointerCapture — mouse would hold the pointer"); sys.exit(1)
# The gate must cover INK ONLY. If it also covers the eraser, a mouse tap on the
# erase button returns silently and the tool looks broken (bug, 2026-10-29).
if "state.tool === 'pen'" not in code:
    print("FAILURE_TYPE: ASSERTION"); print("pen gate is not scoped to the pen tool — erase is blocked for mouse/finger"); sys.exit(1)
if "state.tool !== 'pan'" in code:
    print("FAILURE_TYPE: ASSERTION"); print("pen gate still keyed on '!== pan' — that blocks the eraser too"); sys.exit(1)
print("pen gate at line %d, capture at %d, stroke at %d" % (gate, cap, draw))
PY
