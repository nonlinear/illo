#!/usr/bin/env bash
# illo.app.reload @ 2.0.0
# predicate: reload is NOT a dock object. The dock is pen · eraser · undo · redo, and nothing
#            else. reloadApp() still exists, but it is keyboard-only (R on a laptop).
# Why: the owner runs this fullscreen on Android with no keyboard, so a reload object was
# added on 2026-10-29 for exactly that. On 2026-11-11 he removed it himself:
#   "eu tiraria todos os outros functions. cor, reload. so teria pen, eraser, undo, redo."
# A reload is not a drawing tool. This check now holds the REMOVAL, so the object cannot
# creep back in the next time someone ("someone" = an agent) decides a fullscreen phone
# needs it. The old version asserted the opposite and is why this file says @ 2.0.0.
set -uo pipefail
REPO="${1:?repo}"
python3 - "$REPO" <<'PY'
import re, sys, pathlib
html = pathlib.Path(sys.argv[1], "index.html").read_text()

# The dock contains <div class="divider"> children, so a lazy `.*?</div>` stops at the
# first divider and reports "pen, eraser" -- a regex bug that reads as a product bug.
# Anchor on the dock's own closing tag instead: from `<div class="dock` to the `</div>`
# that follows the LAST button inside it (the divider is the only nested div).
start = html.index('<div class="dock')
end = html.index('<button class="help-fab"', start)
dock_html = html[start:end]
if '</div>' not in dock_html:
    print("FAILURE_TYPE: ASSERTION"); print("no dock in index.html"); sys.exit(1)
if 'id="toolReload"' in dock_html:
    print("FAILURE_TYPE: ASSERTION")
    print("the reload object is back in the dock — the owner removed it on 2026-11-11 "
          "(the dock is pen · eraser · undo · redo)")
    sys.exit(1)

# reloadApp() may stay: it is keyboard-only, and the PWA still needs a way to hard-refresh
# on a laptop. What must not come back is the OBJECT.
ids = re.findall(r'id="(tool[A-Za-z]+)"', dock_html)
want = ["toolPen", "toolEraser", "toolUndo", "toolRedo"]
if ids != want:
    print("FAILURE_TYPE: ASSERTION")
    print("the dock holds %s — want exactly %s" % (ids, want))
    sys.exit(1)

print("no reload object in the dock · dock is pen · eraser · undo · redo · reloadApp is keyboard-only")
PY
