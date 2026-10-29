#!/usr/bin/env python3
"""illo.app.browser-erase @ 1.0.1
predicate: in a real Chromium, a MOUSE click with the eraser CUTS a stroke, and the
           reload object sits in the dock after the tools and reloads without losing work.

Why a browser and not a static check: the pen-gate bug (2026-10-29) parsed fine, had every
function present, and passed 14/14 static checks -- while the erase button did nothing at
all for a mouse or a finger, because the pointerdown handler returned early. Static checks
prove the shape of the code. Only a real event sequence proves the behaviour.

Why the seeding protocol looks odd: navigations that go through the AVFoundation/file URL
loader in a fresh Playwright page reset localStorage to the previous snapshot. So the test
seeds on a blank page of the SAME origin and then NAVIGATES (not reload) to the app. That
path keeps the seed. Same-origin redirect on http behaves identically.
"""
import sys, pathlib, json, time

from playwright.sync_api import sync_playwright

REPO = sys.argv[1] if len(sys.argv) > 1 else str(pathlib.Path(__file__).resolve().parent.parent)
APP = pathlib.Path(REPO, "index.html").resolve()
KEY = "offline-sketch-v1"

# horizontal line A crossing vertical line B at x=600, y=400
SEED = json.dumps({
    "strokes": [
        {"tool": "pen", "color": "#18181B", "size": 6, "pts": [[300, 400, 1], [900, 400, 1]]},
        {"tool": "pen", "color": "#18181B", "size": 6, "pts": [[600, 200, 1], [600, 600, 1]]},
    ],
    "tool": "pen", "color": "#18181B", "size": 6,
    "camera": {"x": 0, "y": 0, "zoom": 1},
})

fail = []
report = {}
blank = APP.parent / ".browser-erase-blank.html"

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 720})
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))

    blank.write_text("<!doctype html><title>seed</title>")
    try:
        pg.goto(blank.as_uri())
        pg.evaluate("(s) => localStorage.setItem('" + KEY + "', s)", SEED)
        pg.goto(APP.as_uri())                 # NAVIGATE, not reload: keeps the seed
        pg.wait_for_timeout(400)

        loaded = pg.evaluate("(k) => { const r = localStorage.getItem(k); return r ? JSON.parse(r).strokes.length : null; }", KEY)
        report["strokes_loaded"] = loaded
        if loaded != 2:
            print(json.dumps(report, indent=2))
            print("FAILURE_TYPE: HARNESS")
            print("- the two test strokes did not load; nothing below would be trustworthy")
            sys.exit(2)

        # ---- the eraser, driven by a MOUSE: the exact case that was silently dead ----
        pg.click("#toolEraser")
        report["eraser_active"] = pg.evaluate("() => document.getElementById('toolEraser').classList.contains('active')")
        if not report["eraser_active"]:
            fail.append("the eraser button did not take the active state")

        pg.mouse.click(450, 400)              # plain left click, pointerType=mouse
        # save() is debounced 400ms and the harness must read the SETTLED state, not a
        # snapshot taken mid-flush: 300ms read the pre-cut value and called a working cut
        # a failure. Wait for the stored geometry itself to change, then report.
        deadline = time.time() + 3.0
        while time.time() < deadline:
            geo = pg.evaluate("(k) => JSON.parse(localStorage.getItem(k)).strokes.map(s => "
                              "({x0: s.pts[0][0], y0: s.pts[0][1], x1: s.pts[s.pts.length-1][0], n: s.pts.length}))", KEY)
            if any(abs(g["y0"] - 400) < 1 and g["x0"] >= 599 for g in geo):
                break
            time.sleep(0.05)
        flash = pg.evaluate("() => document.getElementById('flash').textContent")
        report["flash"] = flash
        if not flash:
            fail.append("MOUSE click with eraser gave no feedback at all (the 2026-10-29 bug is back)")

        geo = pg.evaluate("(k) => JSON.parse(localStorage.getItem(k)).strokes.map(s => "
                          "({x0: s.pts[0][0], y0: s.pts[0][1], x1: s.pts[s.pts.length-1][0], n: s.pts.length}))", KEY)
        report["geometry_after_erase"] = geo
        horiz = [g for g in geo if abs(g["y0"] - 400) < 1]
        if not horiz:
            fail.append("the horizontal line is gone from state entirely")
        else:
            cut = any(g["x0"] >= 599 for g in horiz)   # head was [300..600]; a cut leaves [600..900]
            report["cut_detected"] = cut
            if not cut:
                fail.append("the horizontal line is untouched: erase-to-intersection did not happen")

        # ---- the reload object: present, after the tools, and it navigates ----
        dock = pg.evaluate("() => [...document.querySelectorAll('.dock button.tool')].map(b => b.id)")
        report["dock_order"] = dock
        if "toolReload" not in dock:
            fail.append("no reload object in the dock")
        else:
            if dock.index("toolReload") < dock.index("toolPan"):
                fail.append("reload is not after pan in the dock")

            strokes_before = len(geo)
            pg.evaluate("() => { window.__marker = 1; }")
            try:
                with pg.expect_navigation(timeout=5000):
                    pg.click("#toolReload")
                report["reload_navigated"] = True
            except Exception as exc:
                report["reload_navigated"] = False
                fail.append("reload did not navigate: " + str(exc).splitlines()[0])
            pg.wait_for_timeout(400)
            if pg.evaluate("() => window.__marker === undefined") is not True:
                fail.append("reload did not actually rebuild the page")
            after = pg.evaluate("(k) => { const r = localStorage.getItem(k); return r ? JSON.parse(r).strokes.length : null; }", KEY)
            report["strokes_after_reload"] = after
            if after != strokes_before:
                fail.append("reload cost work: %s strokes before, %s after" % (strokes_before, after))

        report["page_errors"] = errors
        if errors:
            fail.append("page errors: %s" % errors[:3])
    finally:
        blank.unlink(missing_ok=True)
        b.close()

print(json.dumps(report, indent=2))
if fail:
    print("FAILURE_TYPE: BEHAVIOUR")
    for f in fail:
        print("- " + f)
    sys.exit(1)
print("mouse click with eraser cut the line to the intersection · reload object follows the tools · reload keeps the drawing")
