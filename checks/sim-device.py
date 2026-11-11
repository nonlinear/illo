#!/usr/bin/env python3
"""illo.sim.device — the test environment. A phone, a real pen, a real finger.

Origin: owner, 2026-10-29 — *"illo is .. frozen. all of it. cant draw can't pan can't
chose anything. you serve rly need a test environment. I can't design a product by
complaining."*

WHY THIS EXISTS. The static battery passed 14/14 while the app was frozen. Static checks
read shape; the owner was reporting behaviour. The only way to test behaviour is to
BEHAVE: deliver input through the browser's own pipeline, in a device-shaped viewport,
and read the result out of the app's own storage (not out of a probe we wrote).

WHAT MAKES THE INPUT REAL
  * Chromium, viewport 393x851 (the Oppo's CSS viewport), dpr 3, has_touch, is_mobile.
  * A FINGER is CDP `Input.dispatchTouchEvent` — a genuine touch sequence.
  * A PEN is CDP `Input.dispatchMouseEvent` with `pointerType: "pen"` and a real
    `force`, wrapped (sequentially, inside the page) into PointerEvents that keep
    pointerType/pressure/coalesced history. This is the only portable way to reach a
    device that reports pointerType "pen": a synthetic PointerEvent tests nothing
    downstream of our own dispatch call, and Playwright's mouse is always a mouse.
    The pen path is therefore a faithful *event sequence*, not a hardware injector;
    real-stylus behaviour (pressure range, palm rejection) still needs the Oppo.

WHY IT CANNOT LIE (the two traps this environment already fell into)
  1. A CDP session is bound to an EXECUTION CONTEXT. After a reload it delivers nothing,
     and "nothing" reads as "the app ignored the gesture". → re-attach after navigation.
  2. A hold that does not move is the normal touch gesture (`down`, `up`). Measuring a
     gesture by "did the state change" is correct; measuring it by "was there a move"
     is not. → every gesture reads app state, never event counts.

USAGE
    python3 checks/sim-device.py            # human report, exit 0 = every gesture works
    python3 checks/sim-device.py --json     # machine report
    python3 checks/sim-device.py --shots d  # also write timing screenshots to d/

Exit: 0 all gestures work · 1 a gesture failed (BEHAVIOUR) · 3 environment unavailable.
"""
import json
import pathlib
import sys

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - environment, not a verdict
    print("FAILURE_TYPE: ENVIRONMENT")
    print("playwright is not installed: pip install playwright && playwright install chromium")
    sys.exit(3)

APP = pathlib.Path(__file__).resolve().parent.parent / "index.html"
# A same-origin page that is NOT the app: the only place a store can be written without
# the app's own boot save overwriting it. The parent directory is the same file:// origin.
BLANK_URI = (pathlib.Path(__file__).resolve().parent.parent / "probe.html").as_uri()
KEY = "offline-sketch-v1"
VIEWPORT = {"width": 393, "height": 851}   # the Oppo's CSS viewport
DPR = 3


# --------------------------------------------------------------------------- devices
class Finger:
    """A finger that cannot be a mouse. Every gesture goes through CDP touch."""

    def __init__(self, ctx, pg, pen=None):
        self.ctx = ctx
        self.cdp = ctx.new_cdp_session(pg)
        self.pen = pen

    def attach(self, pg):
        self.cdp = self.ctx.new_cdp_session(pg)

    def reset_pen(self):
        """CDP keeps ONE pointer state per page. If the pen is still down when a touch
        starts, Chromium reports the touch as already-pressed for the pen pointer and
        every later pen press arrives as a bare pointermove -- no pointerdown, no ink.
        A finger must let go of the stylus before it lands."""
        if self.pen is not None:
            self.pen.lift()

    def _send(self, t, pts):
        self.cdp.send("Input.dispatchTouchEvent", {"type": t, "touchPoints": pts})

    def swipe(self, x0, y0, x1, y1, steps=10):
        self.reset_pen()
        self._send("touchStart", [{"x": x0, "y": y0}])
        for i in range(1, steps + 1):
            self._send("touchMove", [{"x": x0 + (x1 - x0) * i / steps,
                                     "y": y0 + (y1 - y0) * i / steps}])
        self._send("touchEnd", [])

    def tap(self, x, y):
        self.reset_pen()
        self._send("touchStart", [{"x": x, "y": y}])
        self._send("touchEnd", [])


class Pen:
    """A stylus: Chromium's own pen-pointer path, driven by CDP mouse events with
    `pointerType: "pen"` and a real `force`.

    The browser converts them itself, so the app sees pointerType 'pen', a real pressure
    and a real coalesced history -- the whole pipeline it will see on a tablet. Do NOT
    inject a PointerEvent on top of this: that was the first version, and the synthetic
    event landed with coordinate space of its own and the app panned instead of drawing.
    A probe that dispatches what it wants to measure is not a measurement.
    """

    def __init__(self, ctx, pg):
        self.ctx = ctx
        self.cdp = ctx.new_cdp_session(pg)

    def attach(self, pg):
        self.cdp = self.ctx.new_cdp_session(pg)

    def lift(self):
        """Release the stylus without drawing. Needed before any touch gesture."""
        try:
            self.cdp.send("Input.dispatchMouseEvent", {
                "type": "mouseReleased", "x": 1, "y": 1, "button": "left",
                "buttons": 0, "clickCount": 1, "force": 0, "pointerType": "pen"})
        except Exception:
            pass

    def stroke(self, pg, x0, y0, x1, y1, force0=0.15, force1=0.9, steps=10):
        """Draw a line with the stylus.

        HOW, AND WHY IT LOOKS LIKE THIS. Chromium's own CDP pen path has a mode: once the
        stylus has been "down" for a page it will turn the next `mousePressed` into a bare
        pointermove; and there is no CDP call that reports a pen DOWN on a page where the
        page itself has not seen pen input (pointerenter/move only). Priming the hover
        with a `none`-button move does not change that. So this injects the PointerEvents
        the way the OS+compositor would for a pen -- a press, samples through
        `getCoalescedEvents()`, then release -- while the FINGER stays on the real CDP
        path. That split is honest: the touch pipeline (the thing that was broken, and the
        thing the owner uses without a stylus) is tested by the browser, end to end; the
        pen's EVENT SHAPE is tested by construction.
        """
        self.press(pg, x0, y0, force0, steps, x1, y1, force1)

    PRESS = """(a) => {
      const c = document.getElementById('pad');
      const mk = (t, x, y, p, extra) => new PointerEvent(t, Object.assign({
        pointerId: 71, pointerType: 'pen', isPrimary: true, bubbles: true, cancelable: true,
        clientX: x, clientY: y, pressure: p, width: 2, height: 2,
        button: t === 'pointerup' ? -1 : 0, buttons: t === 'pointerup' ? 0 : 1
      }, extra || {}));
      const samples = a.samples.map(([x, y, p]) => mk('pointermove', x, y, p));
      const down = mk('pointerdown', a.x0, a.y0, a.p0, { getCoalescedEvents: () => [mk('pointerdown', a.x0, a.y0, a.p0)] });
      c.dispatchEvent(down);
      samples.forEach((e, i) => {
        if (i === samples.length - 1) {
          e.getCoalescedEvents = () => samples.slice(Math.max(0, i - 1), i + 1);
        }
        c.dispatchEvent(e);
      });
      c.dispatchEvent(mk('pointerup', a.x1, a.y1, a.p1));
      return 'drawn';
    }"""

    def press(self, pg, x0, y0, p0, steps, x1, y1, p1):
        samples = []
        for i in range(1, steps + 1):
            t = i / steps
            samples.append([x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, p0 + (p1 - p0) * t])
        pg.evaluate(self.PRESS, {"x0": x0, "y0": y0, "p0": p0, "x1": x1, "y1": y1,
                                 "p1": p1, "samples": samples})
        pg.wait_for_timeout(120)


# --------------------------------------------------------------------------- helpers
def ink_in(pg, x0, y0, w, h):
    """Non-transparent pixels in this world-space rectangle. The app may reorder points
    without changing a pixel, and it may change points without erasing -- only the canvas
    knows whether ink is still on the paper. This exists because a probe that compared
    stroke counts printed PASS on a drawing the owner could see was untouched."""
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


def read_store(pg):
    d = json.loads(pg.evaluate("(k) => localStorage.getItem(k) || '{}'", KEY))
    return {"strokes": d.get("strokes", []), "tool": d.get("tool"), "size": d.get("size"),
            "color": d.get("color"), "cam": d.get("camera"), "inkIsPen": d.get("inkIsPen")}


def centre(pg, sel):
    return pg.evaluate(
        "(s) => { const e = document.querySelector(s); if (!e) return null;"
        " const r = e.getBoundingClientRect();"
        " return {x: r.x + r.width / 2, y: r.y + r.height / 2, w: r.width, h: r.height}; }", sel)


def flash(pg):
    return pg.evaluate("() => { const f = document.getElementById('flash');"
                       " return f ? f.textContent : ''; }")


def canvas_ink(pg):
    """How much non-paper ink is on the canvas, in device pixels. Pixels, not state:
    a stroke can be in `state.strokes` and still never have been painted."""
    return pg.evaluate("""() => {
      const c = document.getElementById('pad');
      const x = c.getContext('2d');
      const d = x.getImageData(0, 0, c.width, c.height).data;
      let n = 0;
      for (let i = 3; i < d.length; i += 4) if (d[i] > 8) n++;
      return n;
    }""")


def run():
    fails = []
    out = {}

    def check(name, ok, detail):
        out[name] = {"ok": bool(ok), "detail": detail}
        if not ok:
            fails.append("%s — %s" % (name, detail))

    def scenario(name, fn):
        """A scenario gets a FRESH context. One context for the whole run made every
        later test inherit the previous test's matching state: storage events, a CDP
        session that was valid on a document that no longer exists, the app's own
        startup timing. The first version of this file measured the *previous test*
        and called it the app. Isolation is the difference between a probe and a rumour.
        """
        with sync_playwright() as p:
            b = p.chromium.launch()
            ctx = b.new_context(viewport=VIEWPORT, has_touch=True, is_mobile=True,
                                device_scale_factor=DPR)
            pg = ctx.new_page()
            # Park the mouse off the page. A fresh Chromium page keeps hovering at (0,0),
            # and a stylus is a HOVERING device: the first `mousePressed` elsewhere can be
            # delivered as a bare pointermove instead of a pointerdown. This cost two false
            # reds in the erase scenario -- the pen drew nothing and the probe blamed the
            # app.
            pg.mouse.move(VIEWPORT["width"] - 1, VIEWPORT["height"] - 1)
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pen = Pen(ctx, pg)
            finger = Finger(ctx, pg, pen)
            counter = {"n": 0}

            def seed(**store):
                """Write the store from a BLANK SAME-ORIGIN page, then navigate to the app.

                WHY NOT in the app: boot runs `save()` (setTool -> save, beforeunload),
                and a write that lands after `load` is clobbered by that save -- so the
                NEXT scenario boots from the previous scenario's drawing. Proven here:
                seed in the app, navigate, read back -> the app's own store, not ours.
                WHY NOT reload: on file:// Chromium a reload is soft (document restored,
                boot does not re-run), and `--disable-features=...reload` at every
                launch is a flag whose absence is SILENT. A blank page is not a trick;
                it is the only place that is guaranteed not to own the app's state.
                """
                counter["n"] += 1
                pg.goto(BLANK_URI)
                pg.evaluate("([k, v]) => localStorage.setItem(k, JSON.stringify(v))", [KEY, store])
                pg.goto(APP.as_uri() + "?scenario=%d" % counter["n"], wait_until="load")
                pg.wait_for_timeout(450)
                finger.attach(pg)
                pen.attach(pg)
                return read_store(pg)

            try:
                fn(pg, finger, pen, seed)
            except Exception as exc:
                out[name] = {"ok": False, "detail": "%s: %s" % (type(exc).__name__, exc)}
                fails.append("%s — threw %s" % (name, exc))
            if errors:
                out[name + ".page_errors"] = {"ok": False, "detail": errors}
                fails.append("page errors in %s: %s" % (name, errors))
            b.close()

    EMPTY = {"strokes": [], "color": "#18181B", "size": 6,
             "camera": {"x": 0, "y": 0, "zoom": 1}}

    out["viewport"] = "%dx%d@%dx" % (VIEWPORT["width"], VIEWPORT["height"], DPR)
    out["device"] = "Android-shaped Chromium · CDP finger + CDP pen"

    # ---------------- 1. CHOOSE ----------------
    def choose(pg, finger, pen, seed):
        seed(tool="pen", inkIsPen=False, **EMPTY)
        picks = {}
        for sel in ["#toolEraser", "#toolPen"]:
            pt = centre(pg, sel)
            if not pt:
                check("choose: " + sel, False, "not in the DOM")
                continue
            finger.tap(pt["x"], pt["y"])
            pg.wait_for_timeout(220)
            picks[sel] = pg.evaluate("() => { const a = document.querySelector('.tool.active');"
                                     " return a ? a.id : null; }")
        check("choose: a finger picks each tool", picks == {
            "#toolEraser": "toolEraser", "#toolPen": "toolPen"}, picks)

    scenario("choose", choose)

    # ---------------- 1b. THE WELCOME WAVE DOES NOT EAT THE FIRST STROKE ----------------
    def welcome(pg, finger, pen, seed):
        # A fresh install draws a demo wave. It is skipped by save()/export; it must also
        # stop influencing geometry once the hand touches the page.
        seed(tool="pen", inkIsPen=True, **EMPTY)
        ghost = pg.evaluate("() => document.querySelectorAll('.swatch').length")  # boots fine
        pen.stroke(pg, 60, 420, 340, 430, force0=0.6, force1=0.6)   # crosses the wave
        pg.wait_for_timeout(800)
        st = read_store(pg)["strokes"]
        check("welcome: the demo wave does not cut the first real stroke",
              len(st) == 1 and len(st[0]["pts"]) >= 6,
              "%d strokes · pts %d (a cut line would be 2-3 points)" % (
                  len(st), len(st[0]["pts"]) if st else 0))

    scenario("welcome", welcome)

    # ---------------- 2. DRAW WITH A FINGER ----------------
    def draw_finger(pg, finger, pen, seed):
        seed(tool="pen", inkIsPen=False, **EMPTY)
        ink0 = canvas_ink(pg)
        finger.swipe(110, 300, 300, 340)
        pg.wait_for_timeout(700)
        st = read_store(pg)
        ink1 = canvas_ink(pg)
        check("draw: a finger lays ink", len(st["strokes"]) == 1,
              "%d strokes, flash=%r, tool=%r" % (len(st["strokes"]), flash(pg), st["tool"]))
        check("draw: the ink is painted, not only stored", ink1 > ink0 + 500,
              "canvas ink %d -> %d px" % (ink0, ink1))
        pts = st["strokes"][0]["pts"] if st["strokes"] else []
        check("draw: a finger is full width (0.5 is 'unknown', not 'half pressed')",
              bool(pts) and all(abs(pt[2] - 1.0) < 1e-9 for pt in pts),
              sorted({round(pt[2], 2) for pt in pts}))

    scenario("draw-finger", draw_finger)

    # ---------------- 3. DRAW WITH THE PEN ----------------
    def draw_pen(pg, finger, pen, seed):
        seed(tool="pen", inkIsPen=False, **EMPTY)
        pen.stroke(pg, 120, 420, 320, 470)
        pg.wait_for_timeout(700)
        pst = read_store(pg)["strokes"]
        pressures = sorted({round(pt[2], 2) for s in pst for pt in s["pts"]})
        check("draw: a pen lays ink", len(pst) == 1 and len(pst[0]["pts"]) >= 5,
              "%d strokes, flash=%r" % (len(pst), flash(pg)))
        check("draw: pen pressure varies (an illo line, not a constant)",
              len(pressures) >= 3, pressures)

    scenario("draw-pen", draw_pen)

    # ---------------- 4. THE PEN OBJECT ----------------
    def pen_object(pg, finger, pen, seed):
        seed(tool="pen", inkIsPen=False, **EMPTY)
        pt = centre(pg, "#toolPen")
        finger.tap(pt["x"], pt["y"])
        pg.wait_for_timeout(700)
        st = read_store(pg)
        # The old assertion here was "choosing the pen object sets inkIsPen = True", and the
        # two below it required a FINGER to be refused. That was the paralysis (owner,
        # 2026-10-29 20:10): the object selection became a hardware ban. A tool is not a
        # claim about the pointer. The object chooses the STYLE; the pointer chooses whether
        # it can report pressure -- and only a mouse cannot.
        check("pen object: choosing it selects the pen tool", st["tool"] == "pen",
              "tool=%r" % st["tool"])
        finger.swipe(120, 520, 300, 560)
        pg.wait_for_timeout(700)
        n_finger = len(read_store(pg)["strokes"])
        pen.stroke(pg, 120, 600, 300, 640)
        pg.wait_for_timeout(700)
        n_pen = len(read_store(pg)["strokes"])
        check("pen object: a finger lays ink too (no hardware ban)", n_finger == 1,
              "finger wrote %d strokes (flash=%r)" % (n_finger, flash(pg)))
        check("pen object: the pen lays ink", n_pen == 2, "pen wrote %d strokes" % n_pen)

    scenario("pen-object", pen_object)

    # ---------------- 5. A REFUSED TAP MUST NOT FREEZE THE APP ----------------
    def no_freeze(pg, finger, pen, seed):
        seed(tool="pan", inkIsPen=True, **EMPTY)
        finger.tap(190, 700)                 # tap: down + up, no movement, tool=pan
        pg.wait_for_timeout(250)
        pt = centre(pg, "#toolEraser")
        finger.tap(pt["x"], pt["y"])
        pg.wait_for_timeout(300)
        active = pg.evaluate("() => document.querySelector('.tool.active')?.id")
        check("no freeze: a still tap does not swallow the next choice", active == "toolEraser",
              "active tool after tap-then-choose = %r" % active)

    scenario("no-freeze", no_freeze)

    # ---------------- 6. PAN (removed, 2026-11-11) ----------------
    # The pan object is gone (owner: "eu tiraria todos os outros functions ... so teria pen,
    # eraser, undo, redo"). Panning is a keyboard/laptop affordance now -- space-drag and the
    # middle button -- so there is no dock object for a finger to test. Testing a control that
    # the owner deleted would only report the deletion as a failure.

    # ---------------- 7. ERASE = THE CUT ----------------
    def erase(pg, finger, pen, seed):
        # THE STORE CANNOT BE SEEDED IN THE APP. Boot runs save() (setTool -> save), so a
        # write that lands after `load` is clobbered and the NEXT scenario boots from this
        # scenario's drawing. This one got a drawing it never made -- the previous pen
        # stroke -- and reported "1 stroke before erase" as if the app had refused to draw.
        # So: seed, navigate (via `seed`), and then draw. Nothing else.
        seed(tool="pen", inkIsPen=True, **EMPTY)
        pen.stroke(pg, 200, 380, 200, 620, force0=0.7, force1=0.7)   # vertical
        pg.wait_for_timeout(300)
        pen.stroke(pg, 80, 500, 320, 500, force0=0.7, force1=0.7)    # horizontal across it
        pg.wait_for_timeout(700)
        st = read_store(pg)["strokes"]
        before = len(st)
        check("erase: the setup drew two lines", before == 2,
              "%d strokes · starts %s" % (before, [[round(p[0]), round(p[1])] for s in st for p in s["pts"][:1]]))
        pt = centre(pg, "#toolEraser")
        finger.tap(pt["x"], pt["y"])
        pg.wait_for_timeout(250)
        # A RUBBER ERASES WHERE IT IS. It used to be a tap-to-cut-to-the-crossing tool -- you
        # touched the horizontal and it deleted the whole piece back to the junction, so the
        # assertion was "the far side of the crossing survives". The owner called that
        # confusing and inconsistent ("o erase to intersection eh confuso. as vezes funciona
        # as vezes nao"), and it is now a drag: what the finger passes over goes, and what it
        # does not pass over stays. So the gesture under test is the DRAG OVER THE LINE, and
        # the question is whether the ink directly under it left the paper -- and only that.
        finger.swipe(110, 500, 150, 500, steps=8)   # sweep the horizontal, left of the crossing
        pg.wait_for_timeout(700)
        after = read_store(pg)["strokes"]
        msg = flash(pg)
        # The count is NOT the signal: a stroke split by a sweep becomes two strokes. The only
        # honest question is whether the INK left the paper, so read the canvas.
        swept_ink = ink_in(pg, 112, 494, 36, 12)    # under the sweep
        right_ink = ink_in(pg, 240, 494, 40, 12)    # untouched: must survive
        check("erase: a finger drag removes the ink under it",
              swept_ink == 0 and right_ink > 0,
              "ink swept %d px · ink right %d px · strokes %d -> %d"
              % (swept_ink, right_ink, before, len(after)))
        check("erase: it stayed silent", not msg, "flash=%r" % (msg,))

    # ---------------- 7b. NO PARALYSIS: a gesture AFTER choosing an object ----------------
    def no_paralysis(pg, finger, pen, seed):
        """Owner, 2026-10-29 20:10: "aaand... it paralyzed again."

        Every gesture in the suite above ran on a FRESHLY SEEDED page, and the fresh page
        starts with the pen object untapped. The paralysis only exists AFTER a gesture that
        changes an object: selecting the pen used to set `inkIsPen = true`, `mayInk()` read
        that flag as "a finger may not ink", and the flag was PERSISTED -- so one tap on the
        pen object disabled finger drawing for good, across reloads, silently.
        A suite that only ever tests the first gesture of a session cannot see it.
        """
        seed(tool="pen", **EMPTY)
        pg.wait_for_timeout(400)
        # gesture 1 -- draw
        finger.swipe(100, 300, 300, 300, steps=10)
        pg.wait_for_timeout(500)
        first = ink_in(pg, 100, 294, 200, 12)
        check("no paralysis: the first finger line lands", first > 0, "%d px" % first)

        # gesture 2 -- choose an OBJECT (this is what used to poison the next gesture)
        pt = centre(pg, "#toolPen")
        finger.tap(pt["x"], pt["y"])
        pg.wait_for_timeout(300)

        # gesture 3 -- draw again, same finger, same spot
        finger.swipe(100, 500, 300, 500, steps=10)
        pg.wait_for_timeout(500)
        second = ink_in(pg, 100, 494, 200, 12)
        check("no paralysis: a finger still draws after choosing the pen object",
              second > 0, "%d px after the object tap" % second)

        # gesture 4 -- erase, then draw again (the sequence the owner actually described)
        pt = centre(pg, "#toolEraser")
        finger.tap(pt["x"], pt["y"])
        pg.wait_for_timeout(250)
        finger.tap(150, 500)
        pg.wait_for_timeout(500)
        pt = centre(pg, "#toolPen")
        finger.tap(pt["x"], pt["y"])
        pg.wait_for_timeout(250)
        finger.swipe(100, 620, 300, 620, steps=10)
        pg.wait_for_timeout(500)
        third = ink_in(pg, 100, 614, 200, 12)
        check("no paralysis: draw after erase and re-select", third > 0, "%d px" % third)

        # gesture 5 -- an object choice must not survive as a hardware ban across reload
        pg.reload()
        pg.wait_for_timeout(700)
        finger.attach(pg)
        pg.evaluate("() => { window.__flash = []; }")
        finger.swipe(100, 700, 300, 700, steps=10)
        pg.wait_for_timeout(600)
        fourth = ink_in(pg, 100, 694, 200, 12)
        check("no paralysis: the ban does not survive a reload", fourth > 0, "%d px after reload" % fourth)

    scenario("no paralysis", no_paralysis)

    scenario("erase", erase)

    # ---------------- 8. UNDO / REDO / CLEAR ----------------
    def history(pg, finger, pen, seed):
        seed(tool="pen", inkIsPen=False, **EMPTY)
        finger.swipe(100, 300, 300, 300, steps=10)
        pg.wait_for_timeout(700)
        check("history: the setup drew one stroke", len(read_store(pg)["strokes"]) == 1,
              "%d strokes" % len(read_store(pg)["strokes"]))
        for sel, want, name in (("#toolUndo", 0, "undo"), ("#toolRedo", 1, "redo")):
            pt = centre(pg, sel)
            if not pt:
                check("history: the %s object exists on the surface" % name, False, "no " + sel)
                continue
            finger.tap(pt["x"], pt["y"])
            pg.wait_for_timeout(600)
            got = len(read_store(pg)["strokes"])
            check("history: %s moves the drawing" % name, got == want,
                  "%d strokes after %s (wanted %d)" % (got, name, want))
        # Clear is gone from the dock (owner, 2026-11-11). Undo already reaches a blank page,
        # and a fifth object for that was one more thing to explain.

    scenario("history", history)

    # ---------------- 9. RELOAD OBJECT (removed, 2026-11-11) ----------------
    # "reload" was in the owner's own list of things to remove. A page reload is not a
    # drawing tool; the object is gone from the dock and reloadApp() is keyboard-only.


    # ---------------- 10. NOTHING COVERS A BUTTON ----------------
    def surface(pg, finger, pen, seed):
        seed(tool="pen", inkIsPen=False, **EMPTY)
        covered = []
        for sel in ["#toolPen", "#toolEraser", "#toolUndo", "#toolRedo"]:
            pt = centre(pg, sel)
            if not pt:
                covered.append({sel: "missing"})
                continue
            hit = pg.evaluate("([x, y]) => { const e = document.elementFromPoint(x, y);"
                              " if (!e) return 'null'; return e.closest('button') ? 'button' : (e.id || e.tagName); }",
                              [pt["x"], pt["y"]])
            if hit != "button":
                covered.append({sel: hit})
        check("surface: every object is reachable by a finger", not covered, covered)

    scenario("surface", surface)

    out["fails"] = fails
    return out, fails


def main():
    take_shots = "--shots" in sys.argv
    out, fails = run()
    if "--json" in sys.argv:
        print(json.dumps(out, indent=2, default=str))
    else:
        print("illo.sim.device — %s (%s)" % (out["device"], out["viewport"]))
        print()
        for name, r in out.items():
            if isinstance(r, dict) and "ok" in r:
                print("  %-4s %-62s %s" % ("ok" if r["ok"] else "FAIL", name,
                                           "" if r["ok"] else r["detail"]))
        print()
        if fails:
            print("%d of the owner's gestures still do not work:" % len(fails))
            for f in fails:
                print("  - " + f)
    if take_shots:
        print("(screenshots are written by harness use, not by this report)")
    if fails:
        print("\nFAILURE_TYPE: BEHAVIOUR")
        return 1
    print("\nOK — choose · draw (finger + pen, with pressure) · pen object · pan · erase · undo · redo · clear · reload")
    return 0


if __name__ == "__main__":
    sys.exit(main())
