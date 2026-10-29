#!/usr/bin/env bash
# illo.app.reload @ 1.0.0
# predicate: the dock carries a reload object AFTER the tools, it saves before reloading,
#            and there is no menu hiding it.
# Why: the owner runs this fullscreen on Android with no keyboard and no address bar.
# "Just reload the page" was not an instruction he could follow (2026-10-29).
set -uo pipefail
REPO="${1:?repo}"
python3 - "$REPO/index.html" <<'PY'
import re, sys
src = open(sys.argv[1]).read()
code = re.sub(r"<!--.*?-->", "", src, flags=re.S)
html = re.sub(r"//[^\n]*", "", code)

# 1. the button exists inside the dock, and it is a real button
dock = re.search(r'<div class="dock panel"[^>]*>(.*?)</div>\s*<button class="help-fab"', src, re.S)
if not dock:
    print("FAILURE_TYPE: ASSERTION"); print("dock block not found"); sys.exit(1)
dock_html = dock.group(1)
if 'id="toolReload"' not in dock_html:
    print("FAILURE_TYPE: ASSERTION"); print("no reload object in the dock"); sys.exit(1)

# 2. it sits AFTER the tools (pen, eraser, pan) -- not a menu, not a hidden affordance
order = re.findall(r'id="(tool[A-Za-z]+)"', dock_html)
if "toolReload" not in order:
    print("FAILURE_TYPE: ASSERTION"); print("reload button is not a tool-class object in the dock"); sys.exit(1)
for t in ("toolPen", "toolEraser", "toolPan"):
    if t in order and order.index("toolReload") < order.index(t):
        print("FAILURE_TYPE: ASSERTION"); print("reload is not after %s" % t); sys.exit(1)

# 3. it SAVES before reloading, or a reload costs a stroke
m = re.search(r"function reloadApp\(\)\s*\{(.*?)\}", html, re.S)
if not m:
    print("FAILURE_TYPE: ASSERTION"); print("no reloadApp()"); sys.exit(1)
body = m.group(1)
if "save()" not in body:
    print("FAILURE_TYPE: ASSERTION"); print("reloadApp() does not save first -- a reload would lose work"); sys.exit(1)
if "location.reload()" not in body:
    print("FAILURE_TYPE: ASSERTION"); print("reloadApp() does not reload"); sys.exit(1)
if not re.search(r"getElementById\('toolReload'\)\.onclick\s*=\s*reloadApp", html):
    print("FAILURE_TYPE: ASSERTION"); print("the reload object is not wired to reloadApp"); sys.exit(1)

# 4. no menu on the surface (the owner's second complaint: a menu froze and could not change)
if re.search(r"<select|<menu|class=\"menu|role=\"menu", code, re.I):
    print("FAILURE_TYPE: ASSERTION"); print("a menu appeared on the surface"); sys.exit(1)

print("reload object after the tools in the dock · saves, then reloads · no menu")
PY
