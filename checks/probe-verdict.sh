#!/usr/bin/env bash
# illo.probe.verdict @ 1.0.0
# predicate: the pressure verdict never claims a sensor from a single value
# MDN, PointerEvent.pressure: hardware without pressure reports a constant 0.5.
# So one distinct value can never prove presence, and 0.5 alone is "I don't know".
# A probe that says "SIM" on one sample is an instrument that lies.
set -uo pipefail
REPO="${1:?repo}"
python3 - "$REPO/probe.html" <<'PY'
import re, sys
src = open(sys.argv[1]).read()
m = re.search(r'function verdict\(vals\)\s*\{(.*?)\n\}', src, re.S)
if not m:
    print("FAILURE_TYPE: ASSERTION"); print("verdict() not found in probe.html"); sys.exit(1)
body = m.group(1)
if 'uniq>=2' not in body.replace(' ', ''):
    print("FAILURE_TYPE: ASSERTION")
    print("verdict() no longer requires >=2 distinct values to claim presence")
    sys.exit(1)
if '0.5' not in body:
    print("FAILURE_TYPE: ASSERTION")
    print("verdict() ignores the 0.5 = no-hardware-pressure rule from the spec")
    sys.exit(1)
print("verdict() requires >=2 distinct values and honours 0.5 = unknown")
PY
