#!/usr/bin/env bash
# illo.app.no-phantom-writes @ 1.0.0
# predicate: pressure is read from the event, never invented
# pt() must map a non-pen to 1.0 and a pen with no signal to 0.5. The two are
# different lies if swapped: a mouse would draw thin, a pen would draw fat.
set -uo pipefail
REPO="${1:?repo}"
python3 - "$REPO/index.html" <<'PY'
import re, sys
src = open(sys.argv[1]).read()
m = re.search(r"function pt\(e\)\s*\{(.*?)\n  \}", src, re.S)
if not m:
    print("FAILURE_TYPE: ASSERTION"); print("function pt(e) not found"); sys.exit(1)
body = re.sub(r"//[^\n]*", "", m.group(1))
if "pointerType === 'pen'" not in body:
    print("FAILURE_TYPE: ASSERTION"); print("pt() does not branch on pointerType"); sys.exit(1)
if "e.pressure" not in body:
    print("FAILURE_TYPE: ASSERTION"); print("pt() does not read e.pressure"); sys.exit(1)
if not re.search(r":\s*1\b", body):
    print("FAILURE_TYPE: ASSERTION"); print("pt() no longer maps non-pen to full width (1.0)"); sys.exit(1)
print("pt() reads e.pressure and maps non-pen to 1.0")
PY
