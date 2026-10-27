// Geometry harness for erase-to-intersection. Extracts the real functions from
// index.html and runs them on real topology. Asserts on stroke geometry, not pixels.
import fs from 'node:fs';

const html = fs.readFileSync(new URL('./index.html', import.meta.url), 'utf8');
const from = html.indexOf('function segHit');
const end = html.indexOf('function unmergePoints');
let src = html.slice(from, end);
src = src.replaceAll('state.strokes', 'STROKES');

const factory = new Function(
  'STROKES',
  'SEG_MIN',
  'SEG_EPS',
  `let flashMsgs = [];
   function flash(m) { flashMsgs.push(m); }
   function distToSeg(px,py,ax,ay,bx,by){const dx=bx-ax,dy=by-ay,l2=dx*dx+dy*dy;let t=l2?((px-ax)*dx+(py-ay)*dy)/l2:0;t=Math.max(0,Math.min(1,t));return Math.hypot(px-(ax+t*dx),py-(ay+t*dy));}
   const state = { strokes: STROKES, size: 6 };
   const camera = { x: 0, y: 0, zoom: 1 };
   function pushHistory() {}
   function redrawAll() {}
   ${src}
   return { eraseToIntersection, getFlash: () => flashMsgs, reset: () => { flashMsgs = []; } };`
);

const SEG_MIN = 0.5, SEG_EPS = 0.5;

// Horizontal spans, snapped to a 2px grid and joined. The verticals are scenery --
// assert on the line being cut, never on the whole picture. The snap absorbs SEG_EPS,
// the sub-pixel nudge the splitter leaves at the cut seam.
// lo snaps DOWN and hi snaps UP, so the SEG_EPS seam nudge (601 vs 600) reads as 600,
// while a real gap (400 vs 405) stays a gap.
const snapLo = v => Math.floor(v / 2) * 2;
const snapHi = v => Math.ceil(v / 2) * 2;
const hs = spans => spans.filter(s => s.axis === 'h')
  .map(s => `${snapLo(s.lo)}-${snapHi(s.hi)}`).join(' | ');


function run(name, strokes, tap, expect) {
  const S = structuredClone(strokes);
  const api = factory(S, SEG_MIN, SEG_EPS);
  const ok = api.eraseToIntersection(tap);
  // Flashes are collected per module instance, and every case builds its own instance.
  const flash = api.getFlash().join(' | ') || '(silence)';
  if (process.env.DBG) console.log('   [dbg] flashMsgs=', JSON.stringify(api.getFlash()));
  // Report per-stroke span on its dominant axis. A stroke is 'v' when its vertical
  // extent is the larger one. This is formatting only -- the assertions read `spans`.
  const spans = S.map(s => {
    const xs = s.pts.map(p => p[0]), ys = s.pts.map(p => p[1]);
    const w = Math.max(...xs) - Math.min(...xs), hgt = Math.max(...ys) - Math.min(...ys);
    return w >= hgt
      ? { axis: 'h', lo: Math.round(Math.min(...xs)), hi: Math.round(Math.max(...xs)) }
      : { axis: 'v', lo: Math.round(Math.min(...ys)), hi: Math.round(Math.max(...ys)) };
  });
  const got = spans.map(s => `${s.lo}->${s.hi}${s.axis === 'v' ? 'v' : ''}`).join(' + ');
  const pass = expect(got, ok, flash, spans);
  console.log(`${pass ? 'PASS' : 'FAIL'}  ${name}\n      got=${got || '(nothing)'}  removed=${ok}  flash=${flash}`);
  return pass;
}


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

const results = [];

// 1. Isolated line, tap in the middle -> two halves survive.
results.push(run('isolated line, tap mid', [line(100, 700, 200)], [400, 200],
  (got, ok) => ok && got.split(' + ').length === 2));

// 2. Crossings at 400 and 600, tap 500 -> the 400..600 piece goes, both ends survive.
results.push(run('crossings at 400 and 600, tap 500', [line(100, 700, 200), vert(100, 300, 400), vert(100, 300, 600)], [500, 200],
  (got, ok, f, sp) => ok && f === 'Erased to intersection' && hs(sp) === '100-400 | 600-700'));

// 2b. One crossing at 400, tap 200 -> the tapped side runs to the line's END
//     (there is no crossing left of the tap), so 100..400 goes and only 400..700 stays.
results.push(run('one crossing at 400, tap 200 -> runs to the end', [line(100, 700, 200), vert(100, 300, 400)], [200, 200],
  (got, ok, f, sp) => ok && f === 'Erased to intersection' && hs(sp) === '400-700'));

// 3. Tap exactly ON the crossing -> must NOT be silent. The cut jumps over the
//    junction, and with nothing further left it runs to the END: 100..400 goes.
results.push(run('tap ON crossing 400 -> jumps, cuts to the end', [line(100, 700, 200), vert(100, 300, 400)], [400, 200],
  (got, ok, f, sp) => ok === true && f !== '(silence)' && hs(sp) === '400-700'));

// 4. Tap on crossing 400 with crossing 600 further out -> jump lands on 600.
results.push(run('tap ON crossing 400, next crossing 600', [line(100, 700, 200), vert(100, 300, 400), vert(100, 300, 600)], [400, 200],
  (got, ok, f, sp) => ok === true && f !== '(silence)' && hs(sp) === '100-400 | 600-700'));

// 5. The demo scribble must never be a cutting edge.
const welcome = { ...line(300, 320, 200), _welcome: true };
results.push(run('_welcome scribble cannot stop a cut', [{ ...line(100, 700, 200) }, welcome], [400, 200],
  (got, ok, f) => ok && f === 'Cut line in two'));

// 6. A stroke with a vertex exactly on the crossing still cuts.
const bend = { tool: 'pen', color: '#000', size: 6, pts: [[100, 200, 0.6], [500, 200, 0.6], [700, 200, 0.6]] };
results.push(run('vertex-on-crossing topology', [bend, vert(100, 300, 500)], [550, 200],
  (got, ok, f, sp) => ok === true && hs(sp) === '100-500'));

console.log(`\n${results.filter(Boolean).length}/${results.length} passed`);
process.exit(results.every(Boolean) ? 0 : 1);
