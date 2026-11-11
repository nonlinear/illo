#!/usr/bin/env python3
"""illo.app.tool-paralysis — after the tool changes, the app must still answer.

Owner, 2026-11-11, twice: *"quando muda o tool, paralisa tudo."* / *"paralisa depois de
trocar de tool."* Both hands, finger and pen.

THE MECHANISM. The first statement of the pointerdown handler was

    if (e.pointerType === 'touch' && activeId !== null && activeType === 'pen') return;

Palm rejection: while the pen draws, a resting palm must not mark. Correct -- but it read
`activeId`, and `activeId` is cleared in ONE place, `endStroke()`. Android does not always
deliver that pointerup to the page (pointercancel, OS palm rejection, focus change, a system
gesture). When it does not, `activeId` is never cleared. From that moment EVERY finger tap
hits that `return` and is discarded in silence -- the gate is silent by instruction, so
nothing is said. The app is not frozen: dock, paper and drawing are all on screen. It is DEAF.
The tool change is merely the first gesture that reveals the stuck state, which is why the
sentence is "paralisa DEPOIS de trocar de tool".

This probe drives the literal failure:

  1. a pen stroke whose pointerup never arrives        (the Android case)
  2. a finger tapping a tool                           (must change the tool)
  3. a stroke after that                               (must land)

and one guard: with the pen GENUINELY down, a palm must still not mark.

Exit 0 with evidence; exit 1 with FAILURE_TYPE: ASSERTION.
"""
import sys, json, pathlib

from playwright.sync_api import sync_playwright

REPO = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parent.parent)
APP = (REPO / "index.html").resolve()
VIEWPORT = {"width": 393, "height": 851}
STORE = "()=>JSON.parse(localStorage.getItem('offline-sketch-v1')||'{}')"
# Must match PEN_STALE_MS in index.html, with margin.
STALE_WAIT_MS = 1600


def main():
    out, fail = {}, []
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport=VIEWPORT, has_touch=True, is_mobile=True, device_scale_factor=3)
        pg = ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(APP.as_uri())
        pg.evaluate("()=>localStorage.clear()")
        pg.reload()
        pg.wait_for_timeout(500)
        cdp = ctx.new_cdp_session(pg)

        def store():
            return pg.evaluate(STORE)

        def n():
            return len(store().get("strokes", []))

        def tool():
            return store().get("tool")

        def centre(sel):
            bb = pg.locator(sel).bounding_box()
            return bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2

        def pen_down(y, f=0.7):
            cdp.send("Input.dispatchTouchEvent",
                     {"type": "touchStart", "touchPoints": [{"x": 200, "y": y, "id": 1, "force": f}]})

        def pen_to(x, y, f=0.7):
            cdp.send("Input.dispatchTouchEvent",
                     {"type": "touchMove", "touchPoints": [{"x": x, "y": y, "id": 1, "force": f}]})
            pg.wait_for_timeout(12)

        def pen_up():
            cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
            pg.wait_for_timeout(450)

        def finger_tap(x, y, hold=90):
            cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y, "id": 7}]})
            pg.wait_for_timeout(hold)
            cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
            pg.wait_for_timeout(400)

        def finger_stroke(y):
            cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": 200, "y": y, "id": 7}]})
            for i in range(13):
                cdp.send("Input.dispatchTouchEvent",
                         {"type": "touchMove", "touchPoints": [{"x": 200 + i * 10, "y": y, "id": 7}]})
                pg.wait_for_timeout(12)
            cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
            pg.wait_for_timeout(450)

        # --- 1. baseline: a pen stroke lands, and a finger stroke lands -------------------
        pen_down(250)
        for i in range(13):
            pen_to(200 + i * 10, 250)
        pen_up()
        out["baseline_pen"] = n()
        finger_stroke(300)
        out["baseline_finger"] = n()
        if out["baseline_pen"] != 1:
            fail.append(f"baseline: a plain pen stroke did not land (n={out['baseline_pen']})")
        if out["baseline_finger"] != 2:
            fail.append(f"baseline: a plain finger stroke did not land (n={out['baseline_finger']})")

        # --- 2. A PEN STROKE WHOSE POINTERUP NEVER ARRIVES ---------------------------------
        # The pen goes down and moves; the gesture is then abandoned, which is what the OS does
        # when it takes the touch away. `activeId` is now set with nobody to clear it.
        pen_down(500)
        for i in range(6):
            pen_to(200 + i * 10, 500)
        pg.wait_for_timeout(STALE_WAIT_MS)          # the pen has not spoken for > PEN_STALE_MS
        cdp.send("Input.dispatchTouchEvent", {"type": "touchCancel", "touchPoints": []})
        pg.wait_for_timeout(150)

        # --- 3. THE OWNER'S SENTENCE: change the tool, then work --------------------------
        tx, ty = centre("#toolEraser")
        finger_tap(tx, ty)
        out["tool_after_tap"] = tool()
        if out["tool_after_tap"] != "eraser":
            fail.append("PARALYSIS: after a pen gesture whose pointerup was lost, a finger tap on "
                        f"the Erase object did NOT change the tool (tool={out['tool_after_tap']!r}). "
                        "The palm gate latched on an `activeId` nobody will ever clear, so every "
                        "finger tap is discarded in silence. This is the exact stuck state behind "
                        "\"paralisa depois de trocar de tool\".")

        px, py = centre("#toolPen")
        finger_tap(px, py)
        out["tool_after_pen"] = tool()
        if out["tool_after_pen"] != "pen":
            fail.append(f"the Pen object could not be re-selected (tool={out['tool_after_pen']!r})")

        before = n()
        finger_stroke(620)
        after = n()
        out["draw_after_switch"] = {"before": before, "after": after}
        if after <= before:
            fail.append(f"PARALYSIS: after the tool changed, the next stroke did not land ({before} -> {after}).")

        # --- 4. THE GUARD: a palm must STILL not mark while the pen genuinely draws -------
        # Palm rejection has to survive the fix, or the fix is a regression with a green check.
        pg.evaluate("()=>localStorage.clear()")
        pg.reload()
        pg.wait_for_timeout(500)
        cdp2 = ctx.new_cdp_session(pg)
        before = n()
        cdp2.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": 200, "y": 300, "id": 1, "force": 0.7}]})
        for i in range(4):
            cdp2.send("Input.dispatchTouchEvent",
                      {"type": "touchMove", "touchPoints": [{"x": 200 + i * 10, "y": 300, "id": 1, "force": 0.7}]})
            pg.wait_for_timeout(20)
        # a palm lands while the pen is LIVE (it spoke 20ms ago) and drags across the paper
        cdp2.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [
            {"x": 200 + 40, "y": 300, "id": 1, "force": 0.7}, {"x": 150, "y": 400, "id": 8}]})
        for i in range(13):
            cdp2.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [
                {"x": 200 + 40, "y": 300, "id": 1, "force": 0.7}, {"x": 150 + i * 10, "y": 400, "id": 8}]})
            pg.wait_for_timeout(12)
        pg.wait_for_timeout(200)
        palm_strokes = pg.evaluate("()=>JSON.parse(localStorage.getItem('offline-sketch-v1')||'{}').strokes.length")
        out["palm_while_pen_live"] = {"before": before, "with_palm": palm_strokes}
        if palm_strokes > before:
            fail.append("REGRESSION: a palm marked the paper while the pen was drawing "
                        f"({before} -> {palm_strokes}). Palm rejection must not be traded away.")

        out["pageerrors"] = errors
        if errors:
            fail.append(f"pageerror: {errors[:3]}")
        b.close()

    print(json.dumps({"ok": not fail, "out": out}, indent=2))
    if fail:
        print("\nFAILURE_TYPE: ASSERTION")
        for f in fail:
            print(f"- {f}")
    else:
        print("OK — after a tool change the app answers: finger taps change the tool, strokes "
              "land, and a palm still does not mark while the pen is live")
    return 0 if not fail else 1


if __name__ == "__main__":
    sys.exit(main())
