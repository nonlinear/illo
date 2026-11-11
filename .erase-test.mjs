// Geometry harness for the ERASER. Extracts the real function from index.html and runs it on
// real strokes. Asserts on stroke geometry, not pixels.
//
// v2 adds the METRIC cases, because v1 passed while the owner still had to say "as vezes
// funciona, as vezes nao" (2026-11-11, the second time). v1 asked "is a SAMPLE under the
// rubber". The question the hand asks is "is the INK under the rubber", and the two are not
// the same: a line's samples are wherever the device reported them, its body is 1.1px wide
// even when its size says 6, and a still finger is reported a pixel or two off the line it
// can see. Cases 8-10 measure those, and they FAIL on the v1 eraseAt.
//
// What the rubber promises:
//   1. ink under the finger goes;
//   2. ink the finger did not touch stays, to the point;
//   3. a stroke cut in two survives as TWO strokes (a hole cannot be rendered);
//   4. a stub of one point is dropped -- a speck is not a line;
//   5. it says nothing (ZERO NOTIFICATIONS, owner 2026-10-29).
import fs from 'node:fs';


const html = fs.readFileSync(new URL('./index.html', import.meta.url), 'utf8');

// Pull the eraser and the primitives it really uses out of the app, so the thing under test
// is the shipped code and not a copy that can drift.
const grab = (name) => {
  const start = html.indexOf(`function ${name}(`);
  if (start < 0) throw new Error(`${name}() not found in index.html`);
  let depth = 0, i = html.indexOf('{', start);
  for (let j = i; j < html.length; j++) {
    if (html[j] === '{') depth++;
    else if (html[j] === '}') { depth--; if (depth === 0) return html.slice(start, j + 1); }
  }
  throw new Error(`${name}() is not balanced`);
};

const pieces = ['distToSeg', 'radiusFor', 'eraseRadius', 'strokeRadius', 'eraseAt'].map(grab).join('\n');

const factory = new Function(
  'STROKES', 'SIZE',
  `let flashMsgs = [];
   function flash(m) { flashMsgs.push(m); }
   const state = { strokes: STROKES, size: SIZE };
   const camera = { x: 0, y: 0, zoom: 1 };
   const PRESSURE_FLOOR = 0.10;
   const PRESSURE_EXP = 2.6;
   let erasedAny = false;
   let redraws = 0;
   function redrawAll() { redraws++; }
   function pushHistory() {}
   ${pieces}
   return {
     eraseAt,
     // eraseAt REASSIGNS state.strokes (it builds a new array of survivors), so the harness
     // must read the result back out of the app's own state -- the caller's array stays
     // untouched, which is correct behaviour and a trap for a test that watches it.
     getStrokes: () => state.strokes,
     getFlash: () => flashMsgs,
     getErased: () => erasedAny,
     getRedraws: () => redraws,
   };`
);

const line = (x1, x2, y, n = 40) => {
  const pts = [];
  for (let i = 0; i <= n; i++) pts.push([x1 + (x2 - x1) * i / n, y, 0.6]);
  return { tool: 'pen', color: '#000', size: 6, pts };
};
const vert = (y1, y2, x, n = 40) => {
  const pts = [];
  for (let i = 0; i <= n; i++) pts.push([x, y1 + (y2 - y1) * i / n, 0.6]);
  return { tool: 'pen', color: '#000', size: 6, pts };
};

// Horizontal spans of every surviving stroke, snapped to a 2px grid so the report reads as
// geometry. The rubber does not nudge seams, so the grid is presentation only.
const snap = v => Math.round(v / 2) * 2;
const spans = (S) => S.map(s => {
  const xs = s.pts.map(p => p[0]), ys = s.pts.map(p => p[1]);
  const w = Math.max(...xs) - Math.min(...xs), h = Math.max(...ys) - Math.min(...ys);
  return w >= h
    ? { axis: 'h', lo: snap(Math.min(...xs)), hi: snap(Math.max(...xs)) }
    : { axis: 'v', lo: snap(Math.min(...ys)), hi: snap(Math.max(...ys)) };
}).sort((a, b) => a.lo - b.lo);
const report = (S) => spans(S)
  .map(s => `${s.lo}->${s.hi}${s.axis === 'v' ? 'v' : ''}`).join(' + ') || '(nothing)';
const hs = (S) => spans(S).filter(s => s.axis === 'h').map(s => `${s.lo}-${s.hi}`).join(' | ');

const results = [];

function run(name, strokes, touch, expect, size = 6) {
  const S = structuredClone(strokes);
  const api = factory(S, size);
  const ok = api.eraseAt(touch);
  const flash = api.getFlash().join(' | ') || '(silence)';
  const A = api.getStrokes();          // the survivors live in the app's state, not in S
  const got = report(A);
  const pass = expect({ got, ok, flash, S: A, spans: spans(A), erasedAny: api.getErased() });
  console.log(`${pass ? 'PASS' : 'FAIL'}  ${name}\n      got=${got}  removed=${ok}  flash=${flash}`);
  return pass;
}

// 1. THE MIDDLE OF AN ISOLATED LINE, WITH NO CROSSING ANYWHERE.
//    This is the case the old tool failed by DESIGN -- it needed a crossing to cut to, so
//    a line drawn on its own was untouchable. The rubber does not ask the question.
results.push(run('isolated line, finger in the middle -> two pieces, the gap is where the finger was',
  [line(100, 700, 200)], [400, 200],
  ({ ok, flash, S, spans }) => ok && flash === '(silence)' && spans.length === 2
    && spans[0].hi < 400 && spans[1].lo > 400));

// 2. WHAT THE FINGER DID NOT TOUCH SURVIVES, TO THE POINT.
//    A sweep near the left end must leave the rest of the line exactly as it was.
results.push(run('sweep near the left end -> the rest of the line is untouched',
  [line(100, 700, 200)], [120, 200],
  ({ ok, flash, S, spans }) => ok && flash === '(silence)' && spans.length === 1
    && spans[0].lo > 120 && spans[0].hi === 700));

// 3. A STUB IS NOT A LINE. Sweeping the very end leaves a single point at most, and a single
//    point is dropped rather than left as a speck nobody can erase again.
results.push(run('sweep over the first sample -> no one-point stub survives',
  [line(100, 700, 200)], [100, 200],
  ({ ok, S, spans }) => ok && S.every(s => s.pts.length >= 2)));

// 4. A CROSSING IS NOTHING SPECIAL. The old tool treated a junction as a decision to make.
//    The rubber removes the ink under the finger and leaves the OTHER line alone.
results.push(run('rub across a crossing -> the other line is untouched',
  [line(100, 700, 200), vert(100, 300, 400)], [400, 200],
  ({ ok, flash, S }) => ok && flash === '(silence)'
    && S.some(s => s.pts.every(p => p[0] === 400))          // the vertical is whole
    && S.filter(s => s.pts.some(p => p[1] === 200)).length === 2)); // the horizontal is cut

// 5. THE EMPTY PAGE SAYS NOTHING AND CHANGES NOTHING. A miss is not an event.
results.push(run('finger on empty paper -> nothing happens, silently',
  [line(100, 700, 200)], [400, 900],
  ({ ok, flash, S }) => ok === false && flash === '(silence)' && S.length === 1
    && S[0].pts.length === 41));

// 6. THE DEMO SCRIBBLE IS NOT INK. It is skipped, exactly as save()/export/erase skipped it.
results.push(run('the _welcome scribble is never erased',
  [{ ...line(300, 320, 200), _welcome: true }], [310, 200],
  ({ ok, S }) => ok === false && S.length === 1));

// 7. ONE ANSWER, EVERY TIME. The same touch on the same drawing is the same result, run
//    three times. This is the whole complaint about the old tool, stated as an assertion.
{
  const base = [line(100, 700, 200), vert(100, 300, 400)];
  const answers = [0, 1, 2].map(() => {
    const S = structuredClone(base);
    const api = factory(S, 6);
    api.eraseAt([400, 200]);
    return report(api.getStrokes());
  });
  const pass = new Set(answers).size === 1;
  console.log(`${pass ? 'PASS' : 'FAIL'}  the same touch gives the same answer, three times\n      got=${answers.join(' | ')}`);
  results.push(pass);
}

// 8. A STILL FINGER IS NOT AN AIMED STYLUS. Chromium reported the owner's tap at y=390 on a
//    line at y=400 -- 10px off, still inside the rubber, and v1 erased it by luck of y only.
//    This is the same touch moved to y=397, the value that was measured: on the line's ink and
//    NOT on any sample, because the samples sit at y=400.
//    The assertion is about the TOUCH, not about a 20px window: the rubber is 19.2px wide and
//    it is right for it to take the ink out to x~206-240. What must be true is that no sample
//    within 12px of the finger (half the rubber, so the hole is real) survived, and that the
//    far end of the line did.
results.push(run('a still tap 3px off the line still erases it',
  [line(120, 320, 400)], [220, 397],
  ({ ok, S }) => ok
    && S.every(s => !s.pts.some(p => Math.abs(p[0] - 220) <= 12 && Math.abs(p[1] - 400) < 2))
    && S.some(s => Math.max(...s.pts.map(p => p[0])) === 320)));

// 9. THE BODY OF THE LINE COUNTS. The app draws a 6px line 1.1px wide (radiusFor caps the nib
//    at 0.5 so the raster always paints) and its samples can be 40px apart on a fast stroke --
//    wider than the 19px rubber. v1 asked the segment the distance to a POINT, with no width,
//    so a segment that passes 9.7px away was "missed" while the ink it paints is 0.55px from
//    the finger: under the finger and untouched.
results.push(run('a segment inside the rubber erases even when no sample is',
  [{ tool: 'pen', color: '#000', size: 6, pts: [[100, 200, 1], [140, 200, 1], [180, 209.7, 1], [220, 200, 1], [260, 200, 1]] }],
  [160, 200],
  ({ ok, S, spans }) => ok && spans.length === 2));

// 10. THE ANSWER DOES NOT DEPEND ON SAMPLE SPACING. The same line sampled every 8px and every
//     40px, touched at the same world point, must give the same topology. v1 gave a different
//     answer for a touch that landed in the middle of a long gap.
{
//     What must be equal is the TOPOLOGY and the fact that the ink under the finger is gone;
//     a coarse trace can only approximate the far edge of the hole, because its next sample
//     is the only point the surviving run can start from.
{
  const answers = [8, 40].map(spacing => {
    const S = [line(100, 700, 200, Math.round(600 / spacing))];
    const api = factory(S, 6);
    api.eraseAt([400, 200]);
    const A = api.getStrokes();
    const nearTouch = A.some(s => s.pts.some(p => Math.abs(p[0] - 400) <= 12 && Math.abs(p[1] - 200) < 2));
    return { n: A.length, nearTouch, witness: report(A) };
  });
  const pass = answers.every(a => a.n === 2 && !a.nearTouch);
  console.log(`${pass ? 'PASS' : 'FAIL'}  same touch, spacing 8px vs 40px -> two pieces and no ink at the finger\n      got=${answers.map(a => `${a.n} piece(s) ${a.witness}`).join(' | ')}`);
  results.push(pass);
}
}

console.log(`\n${results.filter(Boolean).length}/${results.length} passed`);
process.exit(results.every(Boolean) ? 0 : 1);
