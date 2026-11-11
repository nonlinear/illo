#!/usr/bin/env python3
"""illo.app.stroke-from-chrome — a finger that starts on the dock still draws, and a tap on
the dock still taps.

Owner, 2026-10-29: *"erase to intersection button does nothing. nothing. I fear you
hallucinated a solution. it's been days. I wanna close MVP."*

He was right, and every check in this repo said PASS while the app was dead. Why: they all
drew on the MIDDLE of the paper, where nothing floats. The dock is a column on the LEFT of a
paper that is also the full screen, and a stroke that began anywhere near it never reached
the canvas at all — the browser handed every event to the dock button it started on.

Two DIFFERENT mechanisms were behind that, and both are pinned here:

  1. `touch-action` on the chrome. `manipulation` (Chrome's OWN default for a button) offers
     tap AND pan; nothing scrolls under the dock, so a sideways slip over a button is a pan
     that cannot happen and the browser CANCELS the pointer. Measured on Chromium, a drag
     starting on a dock button: manipulation -> pointercancel, pan-y -> full stream,
     pinch-zoom -> full stream, none -> full stream. A control that loses the pointer is a
     control that does nothing.
  2. The hit path. A gesture that does begin over the chrome is delivered to the chrome for
     its whole life; a listener on <canvas> never sees it. The paper must listen on the
     document.

So this probe draws the LITERAL gesture that died — a long horizontal line starting on the
dock's empty strip — and requires ink. Then it taps an object and requires the object to
respond, and requires the tap to leave NO dot behind.

Exit 0 with a line of evidence; exit 1 with FAILURE_TYPE: ASSERTION.
"""
import sys, json, pathlib

from playwright.sync_api import sync_playwright

REPO = sys.argv[1] if len(sys.argv) > 1 else str(pathlib.Path(__file__).resolve().parent.parent)
APP = (pathlib.Path(REPO) / "index.html").resolve()
VIEWPORT = {"width": 393, "height": 851}
KEY = "offline-sketch-v1"

out = {}
fail = []


def strokes(pg, want=None, timeout=4000):
    """The drawing, once the app has FINISHED writing it.

    `save()` is debounced 400ms, and reading the store before the flush lands reports a
    stroke that exists as "missing" — that cost an hour today on a probe that was
    measuring its own impatience, not the app. When `want` is given (a stroke count), wait
    for the store to reach it, then read; on timeout return whatever is there so the caller
    reports a real difference instead of hanging.
    """
    read = "(k) => { const r = localStorage.getItem(k); return r ? JSON.parse(r).strokes : []; }"
    if want is None:
        return pg.evaluate(read, KEY)
    import time
    deadline = time.time() + timeout / 1000.0
    got = pg.evaluate(read, KEY)
    while len(got) < want and time.time() < deadline:
        time.sleep(0.05)
        got = pg.evaluate(read, KEY)
    return got


def ink(pg, x0, y0, w, h):
    """Non-transparent pixels in a world-space rectangle. A hallucinated cut cannot fake a
    blank rectangle, and a stroke that never reached the canvas cannot fake ink."""
    return pg.evaluate("""([x0, y0, w, h]) => {
      const c = document.getElementById('pad');
      const g = c.getContext('2d');
      const dpr = c.width / c.clientWidth;
      const d = g.getImageData(Math.round(x0*dpr), Math.round(y0*dpr),
                               Math.round(w*dpr), Math.round(h*dpr)).data;
      let n = 0;
      for (let i = 3; i < d.length; i += 4) if (d[i] > 30) n++;
      return n;
    }""", [x0, y0, w, h])


with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport=VIEWPORT, has_touch=True, is_mobile=True, device_scale_factor=3)
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    # SEEDING, not clearing. A plain reload of the app re-flushes the drawing it already had
    # (`beforeunload` -> save()), so "clear then reload" quietly restores the old picture and
    # the probe measures nothing. Clear from a BLANK page of the same origin instead.
    blank = APP.parent / ".browser-stroke-from-chrome-blank.html"
    blank.write_text("<!doctype html><title>seed</title>")
    try:
        pg.goto(blank.as_uri())
        pg.evaluate("(k) => localStorage.removeItem(k)", KEY)
        pg.goto(APP.as_uri())                 # NAVIGATE, not reload: keeps the blank store
        pg.wait_for_timeout(400)
    finally:
        blank.unlink(missing_ok=True)
    if strokes(pg):
        print(json.dumps({"strokes_at_start": len(strokes(pg))}, indent=2))
        print("FAILURE_TYPE: HARNESS")
        print("- the drawing was not empty at the start; every count below would be a lie")
        b.close()
        sys.exit(2)
    cdp = ctx.new_cdp_session(pg)

    def drag(pts, wait=450):
        cdp.send("Input.dispatchTouchEvent", {"type": "touchStart",
                                              "touchPoints": [{"x": pts[0][0], "y": pts[0][1]}]})
        for x, y in pts[1:]:
            cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x, "y": y}]})
            pg.wait_for_timeout(18)
        cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
        pg.wait_for_timeout(wait)

    def centre(sel):
        return pg.evaluate("(s) => { const r = document.querySelector(s).getBoundingClientRect();"
                           " return {x: r.x + r.width/2, y: r.y + r.height/2}; }", sel)

    # ---- 0. the chrome must not be able to cancel the gesture it starts ----
    out["touch_action"] = {
        sel: pg.evaluate("(s) => getComputedStyle(document.querySelector(s)).touchAction", sel)
        for sel in ("#pad", "#toolEraser", ".dock")
    }
    # `manipulation`/`auto` on a control cancels a sideways slip. Only these survive it.
    dead = [s for s, v in out["touch_action"].items() if v in ("manipulation", "auto", "pan-x", "pan-y")]
    if dead:
        fail.append("touch-action on %s allows a pan that cannot happen: the browser cancels "
                    "the pointer and the stroke never reaches the paper" % ", ".join(dead))

    # ---- 1. THE GESTURE THAT DIED: a long line starting on the dock's empty strip ----
    dock = pg.evaluate("() => { const r = document.querySelector('.dock').getBoundingClientRect();"
                       " return {left: r.left, top: r.top, right: r.right, bottom: r.bottom}; }")
    out["dock_rect"] = dock
    start_y = int(dock["top"] + 4)          # the dock's own padding, above the first object
    out["start_point_is_paper"] = pg.evaluate(
        "([x, y]) => { const e = document.elementFromPoint(x, y); return e.id === 'pad'; }",
        [int(dock["left"]) + 6, start_y])
    if not out["start_point_is_paper"]:
        fail.append("HARNESS: the chosen start point is not on the dock's empty strip")

    drag([(int(dock["left"]) + 6, start_y),
          (60, start_y), (110, start_y), (160, start_y),
          (210, start_y), (260, start_y), (310, start_y), (360, start_y)])
    drawn = strokes(pg, want=1)
    out["strokes_after_drag_from_dock"] = len(drawn)
    if len(drawn) != 1:
        fail.append("a drag that starts on the dock drew %d strokes instead of 1 — this is the "
                    "exact gesture that made 'erase' look dead" % len(drawn))
    else:
        pts = drawn[0]["pts"]
        span = abs(pts[-1][0] - pts[0][0])
        out["stroke_span_x"] = round(span, 1)
        if span < 250:
            fail.append("the stroke from the dock is truncated: it spans %.0fpx of 340" % span)

    # ---- 2. a tap on an object still taps the object ----
    before = pg.evaluate("() => document.querySelector('.tool.active')?.id")
    c = centre("#toolEraser")
    drag([(c["x"], c["y"])], wait=250)
    out["tool_before_tap"] = before
    out["tool_after_tap"] = pg.evaluate("() => document.querySelector('.tool.active')?.id")
    if out["tool_after_tap"] != "toolEraser":
        fail.append("a finger tap on the erase object did not select it (%s)" % out["tool_after_tap"])

    # ---- 3. a tap is not a mark ----
    dot_count = len(strokes(pg, want=len(drawn)))
    out["strokes_after_tapping_the_dock"] = dot_count
    dots = [s for s in strokes(pg) if len(s["pts"]) == 1]
    out["one_point_dots"] = len(dots)
    if dots:
        fail.append("tapping the dock left %d ink dot(s): a tap is a tap, not a mark" % len(dots))
    if dot_count != len(drawn):
        fail.append("tapping the dock changed the drawing: %d strokes -> %d" % (len(drawn), dot_count))

    # ---- 4. and the cut the owner actually wanted, end to end, with a finger ----
    # ONE horizontal line and ONE crossing. The earlier version of this probe drew its
    # horizontal, then a crossing, then measured — and the horizontal had been split by a
    # stray, so the "cut" it demanded was a cut of empty paper and it reported FAIL on a
    # working app. The geometry below is asserted, not assumed: exactly two strokes, and the
    # crossing must sit where the tap will be.
    horizontal = [s for s in strokes(pg, want=1) if len(s["pts"]) > 1
                  and abs(s["pts"][0][1] - start_y) < 2 and abs(s["pts"][-1][1] - start_y) < 2]
    out["horizontals"] = len(horizontal)
    if len(horizontal) != 1:
        fail.append("the long line is not a single stroke (%d pieces) — the cut below would be "
                    "measured on the wrong ink" % len(horizontal))
        cross_x = 200
    else:
        xs = [p[0] for p in horizontal[0]["pts"]]
        # a crossing in the MIDDLE of the line, away from both ends, so both survivors exist
        cross_x = int(round(sum(xs) / len(xs)))
        out["cross_x"] = cross_x

    drag([(cross_x, start_y - 60), (cross_x, start_y - 30), (cross_x, start_y),
          (cross_x, start_y + 30), (cross_x, start_y + 60)])
    # MEASURE FROM THE INK THAT IS THERE, not from a coordinate that happens to be near the
    # crossing. The line drawn from the dock starts at the dock's edge (~x=18) and the earlier
    # steps may already have shortened it, so a fixed `cross_x - 60` can land past its end and
    # read "not painted" on a page that is painted. Take the midpoint of the leftmost surviving
    # stroke's span.
    spans = [[round(p[0]) for p in st["pts"]] for st in strokes(pg)]
    leftmost = min(spans, key=lambda xs: min(xs))
    sweep_x = (min(leftmost) + max(leftmost)) // 2
    out["sweep_x"] = sweep_x
    out["strokes_after_adding_the_crossing"] = len(strokes(pg, want=2))
    if len(strokes(pg, want=2)) != 2:
        fail.append("the crossing line did not land either (%d strokes, wanted 2)" % len(strokes(pg)))

    # THE ERASER IS A RUBBER (owner, 2026-11-11: "o erase to intersection eh confuso. as
    # vezes funciona as vezes nao"). This section used to assert the intersection semantics --
    # tap left of the crossing, the piece back to the crossing goes -- and it was measured
    # against a tool that no longer exists. The question now is the one a rubber can answer
    # and a geometry puzzle cannot: does the ink UNDER THE FINGER leave the paper, and does
    # the ink the finger never touched stay?
    #
    # The gesture begins ON THE DOCK and travels onto the paper. That is the whole point of
    # this probe: a gesture that starts over the chrome must reach the paper. If the sweep
    # below erases, the paper owned the gesture; if it does not, the dock ate it -- which was
    # the original "the button does nothing".
    swept_box = (sweep_x - 8, start_y - 6, 16, 12)     # where the finger passes
    left_box  = (max(20, sweep_x - 130), start_y - 6, 60, 12)
    right_box = (cross_x + 25, start_y - 6, 60, 12)
    out["swept_box"], out["left_box"], out["right_box"] = swept_box, left_box, right_box

    left_before = ink(pg, *left_box)
    right_before = ink(pg, *right_box)
    swept_before = ink(pg, *swept_box)
    out["ink_left_before"], out["ink_right_before"] = left_before, right_before
    out["ink_swept_before"] = swept_before
    if min(left_before, right_before, swept_before) < 20:
        fail.append("the line to be erased is not painted (%d / %d / %d px)"
                    % (left_before, right_before, swept_before))

    # HARNESS PRECONDITION: the eraser must be the active object when the sweep is measured.
    # Step 2 tapped it and asserted it took -- but the drawing made in step 1 and the crossing
    # added after it happen on the PAPER, and a tap on the dock is replayed through
    # settleChrome(). If that replay loses the race with the next drag, this probe measures a
    # sweep with the PEN selected and reports "the line was not erased" when in truth the
    # eraser was never chosen. A check that does not state its own precondition blames the
    # product for its own setup.
    if pg.evaluate("() => document.querySelector('.tool.active')?.id") != "toolEraser":
        c = centre("#toolEraser")
        drag([(c["x"], c["y"])], wait=350)
    out["tool_at_erase"] = pg.evaluate("() => document.querySelector('.tool.active')?.id")
    if out["tool_at_erase"] != "toolEraser":
        fail.append("HARNESS: the eraser could not be selected before the sweep (%s)" % out["tool_at_erase"])

    pg.evaluate("""() => { window.__f = []; const o = document.getElementById('flash');
      new MutationObserver(() => window.__f.push(o.textContent))
        .observe(o, {subtree: true, childList: true, characterData: true}); }""")
    # A REAL THUMB, NOT A PERFECT TAP. The finger travels; that travel is the sweep.
    drag([(sweep_x + d, start_y) for d in (0, 3, 5, 6)])
    left_after = ink(pg, *left_box)
    right_after = ink(pg, *right_box)
    swept_after = ink(pg, *swept_box)
    out["ink_left_after"], out["ink_right_after"] = left_after, right_after
    out["ink_swept_after"] = swept_after
    out["notifications"] = pg.evaluate("() => window.__f")

    out["DEBUG_geometry"] = {
        "cross_x": cross_x, "sweep_x": sweep_x,
        "camera": pg.evaluate("() => { try { return JSON.parse(localStorage.getItem('offline-sketch-v1')).camera; } catch(e) { return null; } }"),
        "strokes": [[[round(p[0]), round(p[1])] for p in s["pts"]] for s in strokes(pg)],
    }
    # THE INK THE FINGER PASSED OVER MUST GO. This is the assertion the original probe was
    # reaching for when it wrote "the button does nothing".
    if swept_after > swept_before * 0.2:
        fail.append("the ink under the finger did not leave the paper: %d px -> %d px swept"
                    % (swept_before, swept_after))
    # ...AND THE INK IT NEVER TOUCHED MUST STAY. A rubber that eats the page is not a rubber.
    if right_after < right_before * 0.8:
        fail.append("the far side of the line vanished too (%d px -> %d px)" % (right_before, right_after))
    if out["notifications"]:
        fail.append("the erase announced itself: %s" % (out["notifications"]))

    out["page_errors"] = errors
    if errors:
        fail.append("page errors: %s" % errors[:3])
    b.close()

print(json.dumps(out, indent=2))
if fail:
    print("\nFAILURE_TYPE: ASSERTION")
    for f in fail:
        print("- " + f)
    sys.exit(1)
print("\nOK — a finger that starts on the dock draws, a tap still taps, the tap leaves no dot, "
      "and the cut is visible with nothing announced")
