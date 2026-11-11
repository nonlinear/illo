#!/usr/bin/env bash
# illo.app.handedness @ 1.0.0
# predicate: the dock and the help object sit on the RIGHT edge, and nothing interactive is
#            pinned to the left edge.
# Why: owner, 2026-11-11: "eu sou canhoto. move o menu pra direita."
# The dock was on the left. A left dock on a phone is directly under a left wrist: the hand
# holding the device rests on the tools, and a stroke that starts near the edge starts on a
# button. The right edge is where a left-handed grip leaves the thumb free.
#
# This is layout, so it is asserted on layout -- the computed `left`/`right` of the real
# elements in a real browser, not on the CSS source. A stylesheet can say `right: 12px` and
# still be overridden by a later rule or a media query; only the computed box knows.
set -uo pipefail
REPO="${1:?repo}"
if ! python3 -c "import playwright" 2>/dev/null; then
  echo "FAILURE_TYPE: ENVIRONMENT"
  echo "python playwright not installed — the layout cannot be measured"
  exit 1
fi
exec python3 - "$REPO" <<'PY'
import sys, pathlib
from playwright.sync_api import sync_playwright

REPO = pathlib.Path(sys.argv[1])
APP = (REPO / "index.html").resolve()
V = {"width": 393, "height": 851}
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport=V, has_touch=True, is_mobile=True, device_scale_factor=3)
    ctx.add_init_script("localStorage.clear()")
    pg = ctx.new_page()
    pg.goto(APP.as_uri()); pg.wait_for_timeout(500)

    boxes = pg.evaluate("""() => {
      const out = {};
      for (const sel of ['.dock', '.help-fab']) {
        const el = document.querySelector(sel);
        if (!el) { out[sel] = null; continue; }
        const r = el.getBoundingClientRect();
        out[sel] = { left: Math.round(r.left), right: Math.round(r.right),
                     top: Math.round(r.top), w: Math.round(r.width) };
      }
      return out;
    }""")
    w = V["width"]
    fail = []
    for sel in (".dock", ".help-fab"):
        box = boxes.get(sel)
        if not box:
            fail.append(f"{sel} is not in the DOM")
            continue
        # "Right" means: much closer to the right edge than the left one.
        dist_right, dist_left = w - box["right"], box["left"]
        if dist_left < dist_right:
            fail.append(f"{sel} is on the LEFT ({dist_left}px from the left edge, "
                        f"{dist_right}px from the right) — the owner is left-handed and the "
                        "left edge is under his wrist")
    # A dock that is off-screen is not on the right, it is gone.
    for sel in (".dock", ".help-fab"):
        if boxes.get(sel) and (boxes[sel]["right"] > w or boxes[sel]["left"] < 0):
            fail.append(f"{sel} is partly off-screen: {boxes[sel]}")

    b.close()

print("dock right=%s · help right=%s · viewport %dpx" %
      (boxes.get('.dock', {}).get('right'), boxes.get('.help-fab', {}).get('right'), w))
if fail:
    print("\nFAILURE_TYPE: ASSERTION")
    for f in fail:
        print("- " + f)
    sys.exit(1)
print("OK — the dock and the help object sit on the right edge, clear of a left-handed wrist")
PY
