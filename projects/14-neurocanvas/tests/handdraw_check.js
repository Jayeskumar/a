// Hand-drawing check: drive the real UI with mouse strokes the way a person draws.
//
//   python app.py &                        (from projects/14-neurocanvas)
//   NODE_PATH="$(npm root -g)" node tests/handdraw_check.js [http://127.0.0.1:8014/] [repeats] [teach]
//
// The stroke shapes below were written by hand for this check (they are NOT the
// training templates). Each design is drawn `repeats` times at a random size,
// position and tilt with a little wobble, and we read the prediction off the
// page. It also checks that the browser's preprocessing (JS) matches the
// server's (Python) on the same canvas: both must produce the same 16x16 grid.
// With `teach`, it then draws 3 fresh copies of every style it got wrong, adds them
// in Teach-it mode, fine-tunes, re-tests everything, and finally resets the model.
const { chromium } = require('playwright');

const DESIGNS = {
  0: [
    [{ smooth: true, pts: ellipse(0.5, 0.5, 0.3, 0.45, -80, -80 - 375) }],
    [{ smooth: true, pts: ellipse(0.5, 0.5, 0.4, 0.42, -100, -100 + 360) }],
  ],
  1: [
    [{ pts: [[0.52, 0.05], [0.47, 0.95]] }],
    [{ pts: [[0.33, 0.22], [0.56, 0.04], [0.56, 0.95]] }],
  ],
  2: [
    [{ smooth: true, pts: [[0.18, 0.28], [0.3, 0.1], [0.55, 0.05], [0.78, 0.2], [0.72, 0.42], [0.45, 0.66], [0.15, 0.92]] }, { pts: [[0.15, 0.92], [0.86, 0.9]] }],
    [{ smooth: true, pts: [[0.25, 0.3], [0.5, 0.08], [0.76, 0.25], [0.6, 0.55], [0.22, 0.9], [0.5, 0.86], [0.82, 0.88]] }],
  ],
  3: [
    [{ smooth: true, pts: [[0.2, 0.15], [0.5, 0.04], [0.75, 0.2], [0.68, 0.38], [0.44, 0.48], [0.74, 0.6], [0.8, 0.78], [0.55, 0.95], [0.2, 0.88]] }],
    [{ smooth: true, pts: [[0.25, 0.12], [0.6, 0.06], [0.72, 0.25], [0.5, 0.45], [0.7, 0.55], [0.75, 0.8], [0.45, 0.95], [0.22, 0.85]] }],
  ],
  4: [
    [{ pts: [[0.6, 0.05], [0.14, 0.64], [0.86, 0.64]] }, { pts: [[0.62, 0.3], [0.62, 0.96]] }],
    [{ pts: [[0.25, 0.05], [0.2, 0.56], [0.82, 0.56]] }, { pts: [[0.66, 0.1], [0.66, 0.96]] }],
  ],
  5: [
    [{ pts: [[0.3, 0.06], [0.25, 0.45]] }, { smooth: true, pts: [[0.25, 0.45], [0.5, 0.38], [0.75, 0.5], [0.78, 0.72], [0.6, 0.92], [0.35, 0.94], [0.18, 0.82]] }, { pts: [[0.3, 0.06], [0.8, 0.05]] }],
    [{ pts: [[0.78, 0.06], [0.3, 0.06], [0.27, 0.42]] }, { smooth: true, pts: [[0.27, 0.42], [0.55, 0.4], [0.74, 0.58], [0.68, 0.85], [0.42, 0.95], [0.2, 0.86]] }],
  ],
  6: [
    [{ smooth: true, pts: [[0.7, 0.05], [0.45, 0.2], [0.28, 0.45], [0.25, 0.7], [0.4, 0.93], [0.65, 0.9], [0.75, 0.72], [0.62, 0.55], [0.4, 0.55], [0.27, 0.68]] }],
    [{ smooth: true, pts: [[0.6, 0.04], [0.35, 0.3], [0.25, 0.62], [0.35, 0.9], [0.62, 0.92], [0.72, 0.7], [0.5, 0.52], [0.3, 0.62]] }],
  ],
  7: [
    [{ pts: [[0.15, 0.1], [0.85, 0.1], [0.42, 0.95]] }],
    [{ pts: [[0.18, 0.12], [0.82, 0.08], [0.5, 0.95]] }, { pts: [[0.42, 0.5], [0.8, 0.5]] }],
  ],
  8: [
    [{ smooth: true, pts: [[0.66, 0.16], [0.5, 0.05], [0.3, 0.15], [0.35, 0.36], [0.65, 0.6], [0.7, 0.82], [0.5, 0.95], [0.3, 0.82], [0.35, 0.6], [0.65, 0.36], [0.68, 0.18]] }],
    [{ smooth: true, pts: ellipse(0.5, 0.27, 0.2, 0.22, 90, 90 + 360) }, { smooth: true, pts: ellipse(0.5, 0.71, 0.27, 0.24, -90, -90 + 360) }],
  ],
  9: [
    [{ smooth: true, pts: [[0.7, 0.25], [0.5, 0.07], [0.3, 0.2], [0.3, 0.4], [0.5, 0.5], [0.7, 0.36], [0.72, 0.2]] }, { pts: [[0.72, 0.2], [0.7, 0.96]] }],
    [{ smooth: true, pts: [[0.72, 0.3], [0.5, 0.06], [0.28, 0.22], [0.35, 0.45], [0.62, 0.42], [0.72, 0.3], [0.7, 0.65], [0.55, 0.95], [0.35, 0.92]] }],
  ],
};

function ellipse(cx, cy, rx, ry, a0, a1) {
  const pts = [], n = 28;
  for (let i = 0; i <= n; i++) {
    const a = (a0 + (a1 - a0) * i / n) * Math.PI / 180;
    pts.push([cx + rx * Math.cos(a), cy + ry * Math.sin(a)]);
  }
  return pts;
}
function catmull(pts, k) {                       // smooth a polyline through its points
  if (pts.length < 3) return pts;
  const out = [];
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(0, i - 1)], p1 = pts[i], p2 = pts[i + 1], p3 = pts[Math.min(pts.length - 1, i + 2)];
    for (let s = 0; s < k; s++) {
      const t = s / k, t2 = t * t, t3 = t2 * t;
      out.push([0, 1].map(d => 0.5 * ((2 * p1[d]) + (-p0[d] + p2[d]) * t + (2 * p0[d] - 5 * p1[d] + 4 * p2[d] - p3[d]) * t2 + (-p0[d] + 3 * p1[d] - 3 * p2[d] + p3[d]) * t3)));
    }
  }
  out.push(pts[pts.length - 1]);
  return out;
}
let seed = 12345;
const rand = () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648);

async function drawDesign(page, box, design) {
  await page.click('#btn-clear');
  const size = 0.5 + 0.28 * rand();                       // digit height as a share of the pad
  const ox = 0.5 + (rand() - 0.5) * (1 - size) * 0.8, oy = 0.5 + (rand() - 0.5) * (1 - size) * 0.8;
  const tilt = (rand() - 0.5) * 0.25, cs = Math.cos(tilt), sn = Math.sin(tilt);
  for (const stroke of design) {
    const pts = stroke.smooth ? catmull(stroke.pts, 6) : stroke.pts;
    const dense = [];
    for (let i = 0; i < pts.length - 1; i++) {
      const n = Math.max(1, Math.ceil(Math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) / 0.045));
      for (let s = 0; s < n; s++) dense.push([pts[i][0] + (pts[i + 1][0] - pts[i][0]) * s / n, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * s / n]);
    }
    dense.push(pts[pts.length - 1]);
    const map = p => {
      const u = (p[0] - 0.5) * size * 0.75, v = (p[1] - 0.5) * size;   // digits are ~0.75 as wide as tall
      const x = ox + u * cs - v * sn + (rand() - 0.5) * 0.006, y = oy + u * sn + v * cs + (rand() - 0.5) * 0.006;
      return [box.x + x * box.width, box.y + y * box.height];
    };
    const first = map(dense[0]);
    await page.mouse.move(first[0], first[1]);
    await page.mouse.down();
    for (const p of dense.slice(1)) { const q = map(p); await page.mouse.move(q[0], q[1]); }
    await page.mouse.up();
  }
  await page.waitForTimeout(350);
}

async function parity(page) {                                // JS vs Python preprocessing on one canvas
  const raw = await page.evaluate(() => {
    const c = document.querySelector('#pad'), g = c.getContext('2d');
    const a = g.getImageData(0, 0, c.width, c.height).data, out = [];
    for (let i = 3; i < a.length; i += 4) out.push(a[i] / 255);
    return out;
  });
  const sent = await page.evaluate(async (raw) => {
    const r = await fetch('/api/predict', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ raw: { width: 280, height: 280, data: raw } }) });
    return (await r.json()).input;
  }, raw);
  const js = await page.evaluate(() => window.__ncLastInput || null);
  if (!js) return null;
  let m = 0;
  for (let i = 0; i < 256; i++) m = Math.max(m, Math.abs(js[i] - sent[i]));
  return m;
}

async function evaluateAll(page, box, repeats, label, checkParity) {
  const results = [];
  let parityChecked = 0, parityMax = 0;
  for (const d of Object.keys(DESIGNS)) {
    for (const [vi, design] of DESIGNS[d].entries()) {
      for (let r = 0; r < repeats; r++) {
        await drawDesign(page, box, design);
        const pred = await page.$eval('#big-digit', e => e.textContent);
        const conf = await page.$eval('#conf', e => e.textContent);
        results.push({ digit: +d, style: vi, pred: +pred, conf });
        if (checkParity && r === 0) {
          const m = await parity(page);
          if (m !== null) { parityMax = Math.max(parityMax, m); parityChecked++; }
        }
      }
    }
  }
  const ok = results.filter(r => r.digit === r.pred).length;
  console.log('[' + label + '] hand-drawn accuracy: ' + ok + ' / ' + results.length + ' = ' + (100 * ok / results.length).toFixed(1) + '%');
  const per = {};
  for (const r of results) { per[r.digit] = per[r.digit] || [0, 0]; per[r.digit][1]++; if (r.digit === r.pred) per[r.digit][0]++; }
  console.log('[' + label + '] per digit: ' + Object.keys(per).map(k => k + ':' + per[k][0] + '/' + per[k][1]).join('  '));
  console.log('[' + label + '] mistakes: ' + (results.filter(r => r.digit !== r.pred).map(r => r.digit + '(style ' + r.style + ')->' + r.pred + ' ' + r.conf).join(', ') || 'none'));
  if (checkParity) console.log('JS vs Python preprocessing: ' + parityChecked + ' drawings compared, max abs pixel difference ' + parityMax.toExponential(2) + ' (server rounds to 3 decimals)');
  return results;
}

(async () => {
  const url = process.argv[2] || 'http://127.0.0.1:8014/';
  const repeats = +(process.argv[3] || 3);
  const teach = process.argv[4] === 'teach';
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto(url, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1200);
  const box = await page.locator('#pad').boundingBox();
  const before = await evaluateAll(page, box, repeats, 'pretrained', true);
  if (teach) {
    // Teach it: for every (digit, style) it got wrong, draw 3 fresh copies, label them, fine-tune.
    const post = (path, body) => page.evaluate(async ([path, body]) => {
      const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      return r.json();
    }, [path, body]);
    await post('/api/teach/clear', {});
    const weak = [...new Set(before.filter(r => r.digit !== r.pred).map(r => r.digit + ':' + r.style))];
    let added = 0;
    for (const key of weak) {
      const [d, vi] = key.split(':').map(Number);
      for (let k = 0; k < 3; k++) {
        await drawDesign(page, box, DESIGNS[d][vi]);
        const px = await page.evaluate(() => window.__ncLastInput);
        await post('/api/teach/add', { pixels: px.map(v => Math.round(v * 1000) / 1000), label: d, source: 'handdraw-check' });
        added++;
      }
    }
    if (added) {
      const rep = await post('/api/teach/finetune', {});
      console.log('taught ' + added + ' drawings of ' + weak.join(', ') + ' in ' + rep.steps + ' steps (' + rep.seconds + ' s); synthetic test ' +
        (100 * rep.test_acc_before).toFixed(1) + '% -> ' + (100 * rep.test_acc_after).toFixed(1) + '%');
      await page.click('#btn-clear');
      await page.waitForTimeout(500);
      await evaluateAll(page, box, repeats, 'after teaching', false);
      await post('/api/model/reset', {});
      await post('/api/teach/clear', {});
    } else console.log('nothing to teach: no mistakes');
  }
  await page.click('#btn-clear');
  await browser.close();
  if (errors.length) { console.log('page errors:\n' + errors.join('\n')); process.exit(1); }
})();
