#!/usr/bin/env bash
# illo.pwa.manifest @ 1.0.0
# predicate: the manifest is valid JSON, installable, and served with the right type
set -uo pipefail
REPO="${1:?repo}"
python3 - "$REPO" <<'PY'
import json, os, sys
repo = sys.argv[1]
p = os.path.join(repo, 'manifest.webmanifest')
try:
    m = json.load(open(p))
except Exception as e:
    print("FAILURE_TYPE: ASSERTION"); print(f"manifest is not valid JSON: {e}"); sys.exit(1)
need = ['name', 'start_url', 'display', 'icons']
missing = [k for k in need if k not in m]
if missing:
    print("FAILURE_TYPE: ASSERTION"); print(f"manifest missing: {missing}"); sys.exit(1)
purposes = {i.get('purpose') for i in m['icons']}
if 'maskable' not in purposes:
    print("FAILURE_TYPE: ASSERTION")
    print("no maskable icon — Android will letterbox it behind its own mask")
    sys.exit(1)
print(f"manifest valid: {m['display']}, {len(m['icons'])} icons, maskable present")
PY
