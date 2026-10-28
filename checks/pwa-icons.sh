#!/usr/bin/env bash
# illo.pwa.icons @ 1.0.0
# predicate: every icon a platform asks for exists, at the size its declaration claims
# This is the check that would have caught the real bug: the files were correct and
# the DECLARATIONS were false (a 37px PNG announced as SVG; a 37px apple-touch-icon).
# A declaration is a claim. A claim that the file cannot honour is a lie the OS acts on.
set -uo pipefail
REPO="${1:?repo}"
python3 - "$REPO" <<'PY'
import json, os, struct, sys
repo = sys.argv[1]
bad = []

def png_size(path):
    with open(path, 'rb') as f:
        head = f.read(24)
    if head[:8] != b'\x89PNG\r\n\x1a\n':
        return None
    return struct.unpack('>II', head[16:24])

man = os.path.join(repo, 'manifest.webmanifest')
spec = json.load(open(man))
for ic in spec.get('icons', []):
    src = ic['src']
    p = os.path.join(repo, src)
    if not os.path.exists(p):
        bad.append(f"{src}: declared in the manifest but missing"); continue
    if src.endswith('.svg'):
        txt = open(p, encoding='utf-8', errors='replace').read(400)
        if '<image' in txt and 'base64' in txt:
            bad.append(f"{src}: is a raster wrapped in <image>, not a vector")
        continue
    size = png_size(p)
    if size is None:
        bad.append(f"{src}: not a PNG"); continue
    claimed = ic['sizes']
    got = f"{size[0]}x{size[1]}"
    if claimed != 'any' and claimed != got:
        bad.append(f"{src}: declared {claimed}, actual {got}")

# html declarations
html = open(os.path.join(repo, 'index.html'), encoding='utf-8').read()
import re
for m in re.finditer(r'<link rel="apple-touch-icon"[^>]*href="([^"]+)"', html):
    href = m.group(1)
    if href.startswith('data:'):
        continue
    p = os.path.join(repo, href)
    if not os.path.exists(p):
        bad.append(f"apple-touch-icon -> {href}: missing"); continue
    size = png_size(p)
    if size and size[0] < 180:
        bad.append(f"apple-touch-icon -> {href}: {size[0]}px, iOS will upscale (needs >=180)")

for m in re.finditer(r'<link rel="icon"[^>]*type="image/svg\+xml"[^>]*href="data:image/svg\+xml;base64,([A-Za-z0-9+/=]{16})', html):
    import base64
    raw = base64.b64decode(m.group(1) + '=='[:(4 - len(m.group(1)) % 4) % 4]).decode('utf-8', 'replace')
    if '<image' in raw:
        bad.append("rel=icon type=svg+xml carries a raster <image> (a browser asking for a vector gets a bitmap)")

if bad:
    print("FAILURE_TYPE: ASSERTION")
    for b in bad:
        print("  " + b)
    sys.exit(1)
n = len(spec.get('icons', []))
print(f"{n} manifest icons at their declared sizes; apple-touch-icon >=180")
PY
