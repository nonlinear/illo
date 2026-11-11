#!/usr/bin/env python3
"""illo.app.dock-and-eraser — four objects, and an eraser that is a rubber.

Owner, 2026-11-11:
  *"eu tiraria todos os outros functions. cor, reload. so teria pen, eraser, undo, redo."*
  *"o erase to intersection eh confuso. as vezes funciona as vezes nao."*
  *"so paralisa quando muda pra erase."*

Two contracts, and both are about the same thing: an object on screen must do exactly one
thing, every time.

  THE DOCK IS FOUR OBJECTS: pen, eraser, undo, redo. Not five, not eight. Colour, reload,
  pan, size and clear were removed -- a dead object in the dock is the "button that does
  nothing" the owner already rejected, and hiding it only postpones the complaint.

  THE ERASER IS A RUBBER. It used to ask a geometry question -- find the nearest crossing on
  each side of the tap and delete the piece between them. On a clean crossing it cut; on a
  line that merely came close it did nothing; on a junction it guessed. A tool that sometimes
  works is a coin. Now it answers one question, "is there ink under the finger", and the
  answer is the same every time because it is measured.

  THE LEDGER MUST COUNT ONCE. A dock object is a real <button>, so the browser fires `click`
  on pointerup -- AND the document listener replays the tap. setTool() survived that by being
  idempotent; Undo did not, and rolled back TWO steps, so Undo from an erased line landed on
  the blank page. This probe counts.

Exit 0 with evidence; exit 1 with FAILURE_TYPE: ASSERTION.
"""
import sys, json, pathlib

from playwright.sync_api import sync_playwright

REPO = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parent.parent)
APP = (REPO / "index.html").resolve()
VIEWPORT = {"width": 393, "height": 851}

# Reads the LIVE drawing, not localStorage: save() is debounced 400ms and a probe that reads
# the store measures the timer, not the app.
LIVE = """() => {
  const c = document.querySelector('#pad');
  return null;
}"""


def main():
    out, fail = {}, []
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport=VIEWPORT, has_touch=True, is_mobile=True, device_scale_factor=3)
        ctx.add_init_script("localStorage.clear()")
        pg = ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(APP.as_uri())
        pg.wait_for_timeout(700)
        cdp = ctx.new_cdp_session(pg)

        def box(sel):
            bb = pg.locator(sel).bounding_box()
            return bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2

        def tap(sel):
            x, y = box(sel)
            cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y, "id": 7}]})
            pg.wait_for_timeout(90)
            cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
            pg.wait_for_timeout(400)

        def stroke(y, x0, x1):
            cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x0, "y": y, "id": 7}]})
            for i in range(13):
                cdp.send("Input.dispatchTouchEvent", {"type": "touchMove",
                         "touchPoints": [{"x": x0 + (x1 - x0) * i / 12, "y": y, "id": 7}]})
                pg.wait_for_timeout(12)
            cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
            pg.wait_for_timeout(500)

        # The store is the only window into an IIFE app. Save is debounced, so wait it out.
        def page_state():
            pg.wait_for_timeout(550)
            return pg.evaluate("()=>JSON.parse(localStorage.getItem('offline-sketch-v1')||'{}')")

        def pieces(st):
            return [[len(s["pts"]), round(s["pts"][0][0]), round(s["pts"][-1][0])]
                    for s in st.get("strokes", []) if not s.get("_welcome")]

        # --- 1. THE DOCK IS EXACTLY FOUR OBJECTS ------------------------------------------
        dock = pg.evaluate("()=>[...document.querySelectorAll('.dock button')].map(b=>b.id||b.className)")
        out["dock"] = dock
        want = ["toolPen", "toolEraser", "toolUndo", "toolRedo"]
        if dock != want:
            fail.append(f"the dock is not the four objects: {dock} (want {want}). Anything extra "
                        "is an object the owner removed -- colour, reload, pan, size, clear.")

        # --- 2. THE ERASER IS A RUBBER: an isolated line, cut in the middle -----------------
        stroke(400, 120, 320)
        st = page_state()
        out["drawn"] = pieces(st)
        if len(pieces(st)) != 1:
            fail.append(f"a plain line did not land as one stroke: {out['drawn']}")

        tap("#toolEraser")
        if page_state().get("tool") != "eraser":
            fail.append("the Erase object did not select the eraser")
        stroke(400, 215, 225)                    # a short drag straight through the middle
        after = page_state()
        out["after_middle_erase"] = pieces(after)
        if len(pieces(after)) != 2:
            fail.append("the eraser did not split an isolated line through the middle "
                        f"(the old erase-to-intersection needed a CROSSING and did nothing here): "
                        f"{out['after_middle_erase']}")

        # --- 2b. THE DOCK SHOWS THE TOOL THAT WAS CHOSEN -----------------------------------
        # canvas.style.cursor used to be the ONLY thing that changed when the tool changed, and
        # a latching `cell` cursor plus one canvas matrix is how a frozen canvas and a changed
        # tool looked identical on the phone. The object itself must say it.
        def dock_state():
            return pg.evaluate("()=>[...document.querySelectorAll('.dock button')].map(b=>({"
                               "id:b.id, active:b.classList.contains('active'),"
                               "bg:getComputedStyle(b).backgroundColor,"
                               "fg:getComputedStyle(b).color}))")

        ds = {d["id"]: d for d in dock_state()}
        out["dock_visual"] = ds
        if not ds.get("toolEraser", {}).get("active"):
            fail.append("the Erase object does not carry .active after being tapped -- the tool "
                        "changed and the dock did not say so")
        if ds.get("toolPen", {}).get("active"):
            fail.append("Pen is still .active while Erase is chosen -- two tools are shown at once")
        out["dock_paint"] = [ds["toolEraser"]["bg"], ds["toolPen"]["bg"]]
        # and the GLYPHS must differ: pen and eraser shipped the same near-black stroke drawing
        def glyph(sel):
            return pg.evaluate("sel=>document.querySelector(sel).querySelector('svg').outerHTML", sel)
        if glyph("#toolPen") == glyph("#toolEraser"):
            fail.append("pen and eraser draw the SAME glyph -- the hand cannot tell them apart")

        # --- 3. THE LEDGER COUNTS ONCE: undo restores the whole line in ONE step ------------
        tap("#toolUndo")
        undone = page_state()
        out["after_undo"] = pieces(undone)
        if len(pieces(undone)) != 1 or pieces(undone)[0][0] < 10:
            fail.append("Undo did not restore the uncut line in one step "
                        f"(got {out['after_undo']}). Two steps is the double-click bug: the "
                        "browser's own click AND the replayed tap both fired undo().")

        tap("#toolRedo")
        redone = page_state()
        out["after_redo"] = pieces(redone)
        if len(pieces(redone)) != 2:
            fail.append(f"Redo did not put the cut back: {out['after_redo']}")

        # --- 3b. A STILL FINGER, A FEW PIXELS OFF THE LINE, STILL ERASES --------------------
        # v1 of the rubber tested SAMPLE POINTS against the eraser. A still tap is reported 1-3px
        # off the line the eye sees, and on a fast stroke the samples are 30-40px apart -- wider
        # than the 19px rubber -- so the ink under the finger could survive untouched. That is
        # "as vezes funciona, as vezes nao" in its cheapest form.
        # THE LINE IS DRAWN ON A CLEAN PAGE. A FIRST attempt put it at y=560 next to the older
        # line at y=400 and the stroke silently never landed: same 600px length, same pen, page
        # otherwise identical -- and the y=560 line at x=120..340 is not there. Whether that is
        # the palm/latch family or something in the gesture bookkeeping is NOT decided here; it
        # is recorded in the epic and the probe stops measuring two things at once.
        pg.evaluate("()=>localStorage.clear()")
        pg.reload()
        pg.wait_for_timeout(600)
        cdp = ctx.new_cdp_session(pg)
        stroke(560, 120, 340)
        tap("#toolEraser")
        if pg.evaluate("()=>JSON.parse(localStorage.getItem('offline-sketch-v1')||'{}').tool") != "eraser":
            fail.append("the Erase object did not select the eraser on the still-tap case")

        def ink_px(x0, y0, w, h):
            return pg.evaluate("""([x0,y0,w,h]) => {
              const c = document.getElementById('pad'), g = c.getContext('2d');
              const dpr = c.width / c.clientWidth;
              const d = g.getImageData(Math.round(x0*dpr), Math.round(y0*dpr),
                                       Math.round(w*dpr), Math.round(h*dpr)).data;
              let n = 0; for (let i = 3; i < d.length; i += 4) if (d[i] > 8) n++;
              return n;
            }""", [x0, y0, w, h])

        # where the line was actually painted, so the assertion measures ink and not a guess
        out["still_tap_rows"] = pg.evaluate("""() => {
          const c = document.getElementById('pad'), g = c.getContext('2d');
          const dpr = c.width / c.clientWidth; const d = g.getImageData(0, 0, c.width, c.height).data;
          const out = [];
          for (let y = 0; y < c.height; y += 3) { let n = 0;
            for (let x = 0; x < c.width; x++) if (d[(y * c.width + x) * 4 + 3] > 8) n++;
            if (n > 0) out.push([Math.round(y / dpr), n]); }
          return out;
        }""")
        rows = out["still_tap_rows"]
        if not rows:
            fail.append("the setup line for the still-tap case was never painted")
        cy = rows[len(rows) // 2][0] if rows else 560
        ink_before = ink_px(225, cy - 8, 30, 16)
        cdp.send("Input.dispatchTouchEvent", {"type": "touchStart",
                 "touchPoints": [{"x": 240, "y": cy, "id": 7}]})
        pg.wait_for_timeout(90)
        cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
        pg.wait_for_timeout(500)
        ink_after = ink_px(225, cy - 8, 30, 16)
        pieces_now = len(pieces(page_state()))
        out["still_tap"] = {"line_y": cy, "before_px": ink_before, "after_px": ink_after,
                            "pieces": pieces_now}
        if ink_before < 20:
            fail.append(f"the setup line painted no ink under the tap ({ink_before}px at y={cy})")
        if ink_after > 0:
            fail.append(f"a still finger ON the line left the ink there ({ink_before} -> "
                        f"{ink_after}px at y={cy}): the rubber tested samples, not the ink")
        if pieces_now < 2:
            fail.append(f"the still tap did not split the line (pieces={pieces_now})")

        # --- 4. A DRAG OVER THE END LEAVES NO SPECK ---------------------------------------
        stroke(700, 150, 330)
        st = page_state()
        tap("#toolEraser")
        stroke(700, 155, 168)                    # sweep the very beginning of that line
        end = page_state()
        runs = pieces(end)
        out["after_end_erase"] = runs
        if any(r[0] < 2 for r in runs):
            fail.append(f"a one-point stub survived the erase: {runs}. A speck is not a line "
                        "and cannot be erased again.")

        if out["dock_paint"][0] == out["dock_paint"][1]:
            fail.append("the chosen object is painted the same as the unchosen one (%s) -- a "
                        "state the eye cannot see" % out["dock_paint"][0])
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
        print("OK — the dock is pen·eraser·undo·redo, the eraser cuts where the finger is, "
              "Undo counts one step per gesture, and no stub survives")
    return 0 if not fail else 1


if __name__ == "__main__":
    sys.exit(main())
