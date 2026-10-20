/* NeuroCanvas front-end. Vanilla JS, no libraries, no network calls except our own /api. */
'use strict';
(function () {
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const GRID = 16, FIT = 12, INK = 0.08;
  const PEN = 18;                      // pen width on the 280 px pad (~= stroke widths in training data)
  const state = { model: null, weights: null, lastPixels: null, lastRes: null, overlay: 'sal', tab: 'draw' };

  // ---------------------------------------------------------------- api / ui utils
  async function api(path, body) {
    const opt = body === undefined ? {} :
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
    const r = await fetch(path, opt);
    let data = null;
    try { data = await r.json(); } catch (e) { data = null; }
    if (!r.ok) throw new Error((data && data.error) || ('HTTP ' + r.status));
    return data;
  }
  let toastTimer = null;
  function toast(msg) {
    const t = $('#toast');
    t.textContent = msg;
    t.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove('show'), 2600);
  }
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const pct = (p, d = 1) => (100 * p).toFixed(d) + '%';
  const sgn = (v, d = 2) => (v >= 0 ? '+' : '') + v.toFixed(d);

  // ---------------------------------------------------------------- theme + colours
  function isDark() {
    const t = document.documentElement.getAttribute('data-theme');
    if (t) return t === 'dark';
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  }
  let PAL = null;
  function hexRgb(h) {
    h = h.replace('#', '').trim();
    if (h.length === 3) h = h.split('').map(c => c + c).join('');
    const n = parseInt(h, 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function palette() {
    if (PAL) return PAL;
    const cs = getComputedStyle(document.documentElement);
    const v = n => hexRgb(cs.getPropertyValue(n) || '#888888');
    PAL = { heat: [v('--heat-0'), v('--heat-1'), v('--heat-2'), v('--heat-3'), v('--heat-4')],
      pos: v('--pos'), neg: v('--neg'), base: v('--surface-2'), brand: v('--brand'), muted: v('--muted') };
    return PAL;
  }
  const rgb = c => 'rgb(' + (c[0] | 0) + ',' + (c[1] | 0) + ',' + (c[2] | 0) + ')';
  const mix = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
  function heat(t) {                     // sequential: 0 = surface-like, 1 = brightest
    const s = palette().heat;
    t = Math.max(0, Math.min(1, t || 0)) * (s.length - 1);
    const i = Math.min(s.length - 2, Math.floor(t));
    return rgb(mix(s[i], s[i + 1], t - i));
  }
  function diverge(v) {                  // -1..1 -> neg ... base ... pos
    const p = palette();
    v = Math.max(-1, Math.min(1, v || 0));
    return rgb(mix(p.base, v >= 0 ? p.pos : p.neg, Math.pow(Math.abs(v), 0.8)));
  }
  function ink(v) {                      // what the network sees: white ink on the dark board
    const b = [8, 10, 24], w = [236, 240, 255];
    return rgb(mix(b, w, Math.max(0, Math.min(1, v))));
  }

  // ---------------------------------------------------------------- preprocessing (mirror of neurocanvas/preprocess.py)
  const rnd = v => Math.floor(v + 0.5);  // round half up, same as preprocess._round
  function bbox(img, w, h) {
    let x0 = w, y0 = h, x1 = -1, y1 = -1;
    for (let y = 0; y < h; y++) {
      let first = -1, last = -1;
      for (let x = 0; x < w; x++) if (img[y * w + x] > INK) { if (first < 0) first = x; last = x; }
      if (first >= 0) { if (y < y0) y0 = y; y1 = y; if (first < x0) x0 = first; if (last > x1) x1 = last; }
    }
    return x1 < 0 ? null : [x0, y0, x1, y1];
  }
  function weights1d(start, size, nOut, nSrc) {
    const step = size / nOut, out = [];
    for (let o = 0; o < nOut; o++) {
      const a = start + o * step, b = a + step, cells = [];
      for (let i = Math.floor(a); i < b && i < nSrc; i++) {
        const lo = Math.max(a, i), hi = Math.min(b, i + 1);
        if (hi > lo && i >= 0) cells.push([i, hi - lo]);
      }
      out.push(cells);
    }
    return out;
  }
  function resample(img, w, h, box, ow, oh) {
    const [x0, y0, x1, y1] = box, bw = x1 - x0 + 1, bh = y1 - y0 + 1;
    const cols = weights1d(x0, bw, ow, w), rows = weights1d(y0, bh, oh, h);
    const norm = (ow / bw) * (oh / bh), out = new Array(ow * oh).fill(0);
    for (let oy = 0; oy < oh; oy++) for (let ox = 0; ox < ow; ox++) {
      let acc = 0;
      for (const [iy, wy] of rows[oy]) { const base = iy * w; for (const [ix, wx] of cols[ox]) acc += img[base + ix] * wy * wx; }
      out[oy * ow + ox] = acc * norm;
    }
    return out;
  }
  function centreOfMass(p, w, h) {
    let t = 0, sx = 0, sy = 0;
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const v = p[y * w + x];
      if (v) { t += v; sx += v * (x + 0.5); sy += v * (y + 0.5); }
    }
    return t > 0 ? [sx / t, sy / t] : [w / 2, h / 2];
  }
  function preprocess(img, w, h) {
    const out = new Array(GRID * GRID).fill(0);
    const box = bbox(img, w, h);
    if (!box) return { px: out, info: null };
    const bw = box[2] - box[0] + 1, bh = box[3] - box[1] + 1;
    const scale = FIT / Math.max(bw, bh);
    const ow = Math.max(1, rnd(bw * scale)), oh = Math.max(1, rnd(bh * scale));
    const patch = resample(img, w, h, box, ow, oh);
    const [cx, cy] = centreOfMass(patch, ow, oh);
    const offx = GRID / 2 - cx, offy = GRID / 2 - cy;
    // fractional, area-preserving shift (mirror of preprocess.shift_splat)
    const ix = Math.floor(offx), iy = Math.floor(offy), fx = offx - ix, fy = offy - iy;
    const wts = [[0, 0, (1 - fx) * (1 - fy)], [1, 0, fx * (1 - fy)], [0, 1, (1 - fx) * fy], [1, 1, fx * fy]];
    for (let py = 0; py < oh; py++) for (let px = 0; px < ow; px++) {
      const v = patch[py * ow + px];
      if (!v) continue;
      for (const [dx, dy, wt] of wts) {
        const gx = px + ix + dx, gy = py + iy + dy;
        if (wt && gx >= 0 && gx < GRID && gy >= 0 && gy < GRID) out[gy * GRID + gx] += v * wt;
      }
    }
    let peak = 0;
    for (const v of out) if (v > peak) peak = v;
    if (peak > 0) for (let i = 0; i < out.length; i++) out[i] /= peak;
    return { px: out, info: { box, sx: ow / bw, sy: oh / bh, offx, offy } };
  }

  // ---------------------------------------------------------------- drawing pad
  class DrawPad {
    constructor(canvas, overlay, emptyEl, onChange) {
      this.c = canvas; this.o = overlay; this.emptyEl = emptyEl; this.onChange = onChange;
      this.ctx = canvas.getContext('2d', { willReadFrequently: true });
      this.strokes = []; this.cur = null; this.demo = false; this.anim = 0;
      canvas.addEventListener('pointerdown', e => this.down(e));
      canvas.addEventListener('pointermove', e => this.move(e));
      ['pointerup', 'pointercancel'].forEach(t => canvas.addEventListener(t, () => this.up()));
      canvas.addEventListener('lostpointercapture', () => this.up());
    }
    pos(e) {
      const r = this.c.getBoundingClientRect();
      return [(e.clientX - r.left) * this.c.width / r.width, (e.clientY - r.top) * this.c.height / r.height];
    }
    down(e) {
      e.preventDefault();
      if (this.demo || this.anim) this.reset(false);
      try { this.c.setPointerCapture(e.pointerId); } catch (err) { /* older browsers */ }
      this.cur = [this.pos(e)];
      this.strokes.push(this.cur);
      this.paint();
      this.changed(false);
    }
    move(e) {
      if (!this.cur) return;
      const evs = e.getCoalescedEvents ? e.getCoalescedEvents() : [e];
      for (const ev of (evs.length ? evs : [e])) this.cur.push(this.pos(ev));
      this.paint();
      this.changed(false);
    }
    up() {
      if (!this.cur) return;
      this.cur = null;
      this.changed(true);
    }
    paint() {
      const g = this.ctx;
      g.clearRect(0, 0, this.c.width, this.c.height);
      g.strokeStyle = '#ffffff'; g.fillStyle = '#ffffff';
      g.lineWidth = PEN; g.lineCap = 'round'; g.lineJoin = 'round';
      for (const s of this.strokes) {
        if (!s.length) continue;
        if (s.length === 1) { g.beginPath(); g.arc(s[0][0], s[0][1], PEN / 2, 0, Math.PI * 2); g.fill(); continue; }
        g.beginPath(); g.moveTo(s[0][0], s[0][1]);
        for (let i = 1; i < s.length; i++) g.lineTo(s[i][0], s[i][1]);
        g.stroke();
      }
      if (this.emptyEl) this.emptyEl.style.display = this.strokes.length ? 'none' : '';
    }
    reset(notify) {
      cancelAnimationFrame(this.anim); this.anim = 0;
      this.strokes = []; this.cur = null; this.demo = false;
      this.paint(); this.clearOverlay();
      if (notify !== false) this.changed(true);
    }
    undo() { if (this.anim) return; this.strokes.pop(); this.demo = false; this.paint(); this.changed(true); }
    isEmpty() { return this.strokes.length === 0; }
    clearOverlay() { if (this.o) this.o.getContext('2d').clearRect(0, 0, this.o.width, this.o.height); }
    changed(final) { if (this.onChange) this.onChange(final, this); }
    animate(strokes, ms) {
      this.reset(false);
      this.demo = true;
      const W = this.c.width, H = this.c.height;
      const pts = strokes.map(s => s.map(p => [p[0] * W, p[1] * H]));
      const total = pts.reduce((a, s) => a + s.length, 0);
      const t0 = performance.now();
      return new Promise(resolve => {
        const step = now => {
          const n = Math.min(total, Math.ceil(total * (now - t0) / ms));
          let left = n;
          this.strokes = [];
          for (const s of pts) { if (left <= 0) break; this.strokes.push(s.slice(0, left)); left -= s.length; }
          this.paint();
          if (n < total) { this.changed(false); this.anim = requestAnimationFrame(step); }
          else { this.anim = 0; this.changed(true); resolve(); }
        };
        this.anim = requestAnimationFrame(step);
      });
    }
    read() {
      const W = this.c.width, H = this.c.height;
      const d = this.ctx.getImageData(0, 0, W, H).data;
      const img = new Float32Array(W * H);
      for (let i = 0; i < W * H; i++) img[i] = d[i * 4 + 3] / 255;
      return preprocess(img, W, H);
    }
    /* paint grid-cell values back onto the drawing (inverse of the crop/scale/shift) */
    overlayGrid(vals, info) {
      if (!this.o) return;
      const g = this.o.getContext('2d');
      g.clearRect(0, 0, this.o.width, this.o.height);
      if (!vals || !info) return;
      let m = 0;
      for (const v of vals) m = Math.max(m, Math.abs(v));
      if (!m) return;
      // paint the 16x16 map into a tiny canvas, then let the browser upscale it
      // smoothly onto the drawing (bilinear) so it reads as a glow, not a mosaic
      const small = document.createElement('canvas');
      small.width = GRID; small.height = GRID;
      const sg = small.getContext('2d'), img = sg.createImageData(GRID, GRID);
      for (let i = 0; i < GRID * GRID; i++) {
        const v = vals[i] / m, a = Math.abs(v), c = v > 0 ? [34, 211, 238] : [251, 113, 133];   // neon on the dark board
        img.data[i * 4] = c[0]; img.data[i * 4 + 1] = c[1]; img.data[i * 4 + 2] = c[2];
        img.data[i * 4 + 3] = a < 0.2 ? 0 : Math.round(235 * Math.pow((a - 0.2) / 0.8, 0.9));
      }
      sg.putImageData(img, 0, 0);
      g.imageSmoothingEnabled = true;
      g.imageSmoothingQuality = 'high';
      g.drawImage(small, info.box[0] - info.offx / info.sx, info.box[1] - info.offy / info.sy, GRID / info.sx, GRID / info.sy);
    }
  }

  // live predictor: at most one request in flight, latest drawing wins
  function makePredictor(pad, onResult, onEmpty) {
    // One request in flight at a time; the newest drawing always wins. Sequence
    // numbers make sure a slow, older response can never overwrite a newer one.
    let inflight = false, dirty = false, seq = 0, shown = 0;
    async function send() {
      if (inflight) return;
      dirty = false;
      const my = ++seq;
      if (pad.isEmpty()) { shown = my; onEmpty(); return; }
      const { px, info } = pad.read();
      if (!info) { shown = my; onEmpty(); return; }
      inflight = true;
      try {
        const t0 = performance.now();
        const res = await api('/api/predict', { pixels: px.map(v => Math.round(v * 1000) / 1000) });
        res.rtt = performance.now() - t0;
        if (my > shown && !pad.isEmpty()) { shown = my; onResult(res, info, px); }
      } catch (e) { toast('Prediction failed: ' + e.message); }
      finally {
        inflight = false;
        if (dirty) setTimeout(send, 15);
      }
    }
    return function schedule() { dirty = true; send(); };
  }

  // ---------------------------------------------------------------- small renderers
  function gridCanvas(canvas, vals, mode, n) {
    n = n || GRID;
    const g = canvas.getContext('2d');
    canvas.width = n; canvas.height = n;
    let m = 0;
    if (mode === 'div' && vals) for (const v of vals) m = Math.max(m, Math.abs(v));
    for (let i = 0; i < n * n; i++) {
      const v = vals ? vals[i] : 0;
      g.fillStyle = mode === 'div' ? diverge(m ? v / m : 0) : mode === 'heat' ? heat(v) : ink(v);
      g.fillRect(i % n, Math.floor(i / n), 1, 1);
    }
  }
  function bytesToFloats(b) { return b.map(v => v / 255); }

  function buildBars(el, mini) {
    el.innerHTML = '';
    for (let k = 0; k < 10; k++) {
      const col = document.createElement('div');
      col.className = 'bar-col';
      col.innerHTML = (mini ? '' : '<div class="bar-val">–</div>') +
        '<div class="bar-track"><div class="bar" style="height:0%"></div></div><div class="bar-label">' + k + '</div>';
      el.appendChild(col);
    }
  }
  function setBars(el, probs, pred) {
    const cols = el.children;
    for (let k = 0; k < 10; k++) {
      const p = probs ? probs[k] : 0;
      cols[k].classList.toggle('win', probs !== null && k === pred);
      cols[k].querySelector('.bar').style.height = (100 * p).toFixed(1) + '%';
      const v = cols[k].querySelector('.bar-val');
      if (v) v.textContent = probs ? (p >= 0.995 ? '100%' : p >= 0.01 ? Math.round(100 * p) + '%' : p > 0.0005 ? '<1%' : '0') : '–';
    }
  }

  // ---------------------------------------------------------------- network graph (SVG)
  function colsFor(size) { return size <= 4 ? size : size <= 32 ? 4 : size <= 64 ? 8 : Math.ceil(Math.sqrt(size)); }
  function netSVG(res) {
    const W = 660, H = 330, layers = res.layers, nh = layers.length;
    const parts = [], pos = {};
    // input image
    const ix = 14, iy = 100, ic = 8;
    parts.push('<text class="col-title" x="' + (ix + 64) + '" y="22" text-anchor="middle">Input 16×16</text>');
    parts.push('<text x="' + (ix + 64) + '" y="38" text-anchor="middle">256 pixels</text>');
    for (let i = 0; i < 256; i++) {
      parts.push('<rect x="' + (ix + (i % 16) * ic) + '" y="' + (iy + Math.floor(i / 16) * ic) + '" width="' + ic + '" height="' + ic + '" fill="' + ink(res.input[i]) + '"/>');
    }
    // hidden layers
    const x0 = 190, x1 = 545, span = (x1 - x0) / nh;
    layers.forEach((L, h) => {
      const cols = colsFor(L.size), rows = Math.ceil(L.size / cols);
      const cell = Math.min(20, 222 / rows, (span - 30) / cols), gap = cell * 0.2;
      const cx = x0 + span * (h + 0.5), gw = cols * cell, gh = rows * cell, gx = cx - gw / 2, gy = 175 - gh / 2;
      let m = 0;
      for (const a of L.act) m = Math.max(m, Math.abs(a));
      const top = new Set(L.top.map(t => t.unit));
      pos[h + 1] = {};
      parts.push('<text class="col-title" x="' + cx + '" y="22" text-anchor="middle">Hidden ' + (h + 1) + '</text>');
      parts.push('<text x="' + cx + '" y="38" text-anchor="middle">' + L.size + ' ' + (state.model ? state.model.activation : '') + ' · ' + L.active + ' on</text>');
      for (let j = 0; j < L.size; j++) {
        const x = gx + (j % cols) * cell, y = gy + Math.floor(j / cols) * cell;
        pos[h + 1][j] = [x + cell / 2, y + cell / 2];
        const a = L.act[j], t = top.has(j);
        const fill = m ? heat(Math.abs(a) / m) : heat(0);
        parts.push('<rect class="node" x="' + (x + gap / 2).toFixed(1) + '" y="' + (y + gap / 2).toFixed(1) + '" width="' + (cell - gap).toFixed(1) +
          '" height="' + (cell - gap).toFixed(1) + '" rx="3" fill="' + fill + '"' + (t ? ' stroke="var(--brand)" stroke-width="2"' : ' stroke="var(--border)"') +
          '><title>hidden ' + (h + 1) + ' #' + j + ': activation ' + a.toFixed(3) + '</title></rect>');
      }
    });
    // output column
    const ox = 604;
    parts.push('<text class="col-title" x="' + ox + '" y="22" text-anchor="middle">Output</text>');
    parts.push('<text x="' + ox + '" y="38" text-anchor="middle">softmax</text>');
    pos.out = {};
    for (let k = 0; k < 10; k++) {
      const y = 58 + k * 27;
      pos.out[k] = [ox - 12, y];
      const p = res.probs[k], win = k === res.pred;
      parts.push('<circle cx="' + ox + '" cy="' + y + '" r="11.5" fill="' + heat(p) + '"' + (win ? ' stroke="var(--accent)" stroke-width="2.5"' : ' stroke="var(--border)"') + '><title>digit ' + k + ': p = ' + p.toFixed(4) + '</title></circle>');
      parts.push('<text class="out-label" x="' + ox + '" y="' + (y + 4.5) + '" text-anchor="middle" style="pointer-events:none;' + (p > 0.45 ? 'fill:#fff' : '') + '">' + k + '</text>');
      parts.push('<text x="' + (ox + 18) + '" y="' + (y + 4) + '"' + (win ? ' style="fill:var(--accent);font-weight:700"' : '') + '>' + (p >= 0.995 ? '100' : Math.round(100 * p)) + '%</text>');
    }
    // edges (drawn underneath the nodes)
    const edges = [];
    let maxW = 0;
    for (const e of res.edges) maxW = Math.max(maxW, Math.abs(e.w));
    const curve = (a, b, w, col) => {
      const dx = (b[0] - a[0]) / 2, r = Math.abs(w) / (maxW || 1);
      return '<path d="M' + a[0].toFixed(1) + ',' + a[1].toFixed(1) + ' C' + (a[0] + dx).toFixed(1) + ',' + a[1].toFixed(1) + ' ' + (b[0] - dx).toFixed(1) + ',' + b[1].toFixed(1) + ' ' + b[0].toFixed(1) + ',' + b[1].toFixed(1) +
        '" fill="none" stroke="' + col + '" stroke-width="' + (0.5 + 3.2 * r).toFixed(2) + '" stroke-opacity="' + (0.12 + 0.7 * r).toFixed(2) + '"/>';
    };
    const p = palette();
    for (const e of res.edges) {
      const a = pos[e.from[0]] && pos[e.from[0]][e.from[1]];
      const b = e.to[0] === 'out' ? pos.out[e.to[1]] : pos[e.to[0]] && pos[e.to[0]][e.to[1]];
      if (a && b) edges.push(curve(a, b, e.w, rgb(e.w >= 0 ? p.pos : p.neg)));
    }
    // input -> top first-layer units (thickness = contribution to the winner)
    const t1 = layers[0].top;
    let mc = 0;
    for (const t of t1) mc = Math.max(mc, Math.abs(t.contrib));
    for (const t of t1) {
      const b = pos[1][t.unit], r = Math.abs(t.contrib) / (mc || 1);
      edges.push('<path d="M' + (ix + 128) + ',' + (iy + 64) + ' C' + (ix + 160) + ',' + (iy + 64) + ' ' + (b[0] - 30) + ',' + b[1] + ' ' + b[0] + ',' + b[1] +
        '" fill="none" stroke="' + rgb(t.contrib >= 0 ? p.pos : p.neg) + '" stroke-width="' + (0.5 + 2.5 * r).toFixed(2) + '" stroke-opacity="' + (0.1 + 0.5 * r).toFixed(2) + '"/>');
    }
    return '<g>' + edges.join('') + '</g>' + parts.join('');
  }

  // ---------------------------------------------------------------- DRAW tab
  const pad = new DrawPad($('#pad'), $('#pad-overlay'), $('#pad-empty'), (final) => { $('#pad-badge').style.opacity = pad.demo ? 1 : 0; predictDraw(); });
  const predictDraw = makePredictor(pad, renderDraw, renderDrawEmpty);
  buildBars($('#bars'));

  function renderDrawEmpty() {
    state.lastPixels = null; state.lastRes = null;
    setBars($('#bars'), null);
    const bd = $('#big-digit'); bd.textContent = '?'; bd.classList.add('empty');
    $('#conf').textContent = '–';
    $('#why').innerHTML = 'Draw a digit (or press <b>Demo digit</b>) and the network will explain what it saw.';
    $('#votes').innerHTML = '<span class="muted">Waiting for a drawing…</span>';
    $('#net').innerHTML = '<text x="330" y="170" text-anchor="middle">Draw a digit to see the neurons light up</text>';
    $('#units').innerHTML = '';
    $('#lat').textContent = '–';
    gridCanvas($('#see-input'), null, 'ink'); gridCanvas($('#see-sal'), null, 'div');
    pad.clearOverlay();
  }

  async function ensureWeights(version) {
    if (state.weights && state.weights.model_version === version) return state.weights;
    state.weights = await api('/api/weights');
    return state.weights;
  }

  function renderDraw(res, info, px) {
    state.lastPixels = res.input; state.lastRes = res;
    window.__ncLastInput = px;           // exposed for tests/handdraw_check.js (JS vs Python parity)
    setBars($('#bars'), res.probs, res.pred);
    const bd = $('#big-digit'); bd.textContent = res.pred; bd.classList.remove('empty');
    $('#conf').textContent = pct(res.confidence);
    const r2 = res.runner_up, z = res.logits[res.pred];
    const last = res.layers[res.layers.length - 1], voter = last.top[0];
    let why = 'It looks like a <b>' + res.pred + '</b> (' + pct(res.confidence) + '). Runner-up: <b>' + r2 + '</b> (' + pct(res.probs[r2]) + ').<br>' +
      'Score z<sub>' + res.pred + '</sub> = ' + z.toFixed(2) + ': <span class="pos">' + sgn(res.evidence.pixels, 1) + ' from your pixels</span> (gradient × input) and ' +
      sgn(res.evidence.bias, 1) + ' from biases.';
    if (voter) why += ' Loudest voter: hidden-' + res.layers.length + ' neuron #' + voter.unit + ' (' + sgn(voter.contrib, 1) + ').';
    if (res.confidence < 0.6) why += '<br><b>Unsure</b>: torn between ' + res.pred + ' and ' + r2 + '. Try the Teach it tab to show it your style.';
    $('#why').innerHTML = why;
    $('#lat').textContent = 'network ' + res.latency_ms.toFixed(1) + ' ms (forward + backward, pure Python) · round trip ' + Math.round(res.rtt) + ' ms';
    $('#lat-model').textContent = res.model;
    gridCanvas($('#see-input'), res.input, 'ink');
    gridCanvas($('#see-sal'), res.saliency, 'div');
    if (state.overlay === 'sal') pad.overlayGrid(res.saliency, info); else pad.clearOverlay();
    $('#net').innerHTML = netSVG(res);
    $('#net-sub').textContent = res.layers.map(l => l.active + '/' + l.size).join(' · ') + ' neurons active';
    // votes: last hidden layer contributions to the winning logit
    let mv = 0;
    for (const t of last.top) mv = Math.max(mv, Math.abs(t.contrib));
    $('#votes').innerHTML = last.top.slice(0, 6).map(t =>
      '<div class="pc-row" style="grid-template-columns:62px 1fr 52px"><span class="dim">#' + t.unit + ' <span class="muted">a=' + t.act.toFixed(1) + '</span></span>' +
      '<div class="pc-track"><div style="width:' + (100 * Math.abs(t.contrib) / (mv || 1)).toFixed(0) + '%;background:' + (t.contrib >= 0 ? 'var(--pos)' : 'var(--neg)') + '"></div></div>' +
      '<b class="' + (t.contrib >= 0 ? 'pos' : 'neg') + '" style="text-align:right;color:' + (t.contrib >= 0 ? 'var(--pos)' : 'var(--neg)') + '">' + sgn(t.contrib, 2) + '</b></div>').join('') +
      '<p class="hint">Hidden-' + res.layers.length + ' neurons ranked by how much they add to the score for ' + res.pred + ' (activation × outgoing weight).</p>';
    ensureWeights(res.model_version).then(w => {
      if (state.lastRes !== res) return;
      const top = res.layers[0].top.slice(0, 6);
      $('#units').innerHTML = top.map((t, i) => '<div class="unit"><canvas id="u' + i + '" width="16" height="16"></canvas><div class="u-id">L1 #' + t.unit +
        '</div><div class="u-c ' + (t.contrib >= 0 ? 'pos' : 'neg') + '">a=' + t.act.toFixed(2) + ' · ' + sgn(t.contrib, 1) + '</div></div>').join('');
      top.forEach((t, i) => gridCanvas($('#u' + i), w.layer1[t.unit], 'div'));
    }).catch(() => {});
  }

  // demo digits
  const sel = $('#demo-digit');
  for (let k = 0; k < 10; k++) sel.insertAdjacentHTML('beforeend', '<option value="' + k + '">' + k + '</option>');
  async function demoDigit(digit, seed, targetPad, ms) {
    const q = [];
    if (digit !== undefined && digit !== '' && digit !== null) q.push('digit=' + digit);
    if (seed !== undefined) q.push('seed=' + seed);
    const d = await api('/api/demo' + (q.length ? '?' + q.join('&') : ''));
    await (targetPad || pad).animate(d.strokes, ms || 650);
    return d;
  }
  $('#btn-demo').addEventListener('click', () => demoDigit(sel.value).catch(e => toast(e.message)));
  $('#btn-clear').addEventListener('click', () => pad.reset());
  $('#btn-undo').addEventListener('click', () => pad.undo());
  $$('#overlay-mode button').forEach(b => b.addEventListener('click', () => {
    $$('#overlay-mode button').forEach(x => x.classList.toggle('on', x === b));
    state.overlay = b.dataset.v;
    predictDraw();
  }));
  $('#btn-run-demo').addEventListener('click', () => { showTab('draw'); demoDigit('').catch(e => toast(e.message)); });

  // ---------------------------------------------------------------- EXPLAIN tab
  const LRS = [0.005, 0.01, 0.05, 0.1, 0.5];
  let exLabel = 'auto';
  $('#ex-label').innerHTML = ['auto'].concat([0, 1, 2, 3, 4, 5, 6, 7, 8, 9]).map(v => '<button class="chip' + (v === 'auto' ? ' on' : '') + '" data-v="' + v + '">' + (v === 'auto' ? 'auto (its guess)' : v) + '</button>').join('');
  $$('#ex-label .chip').forEach(c => c.addEventListener('click', () => {
    $$('#ex-label .chip').forEach(x => x.classList.toggle('on', x === c));
    exLabel = c.dataset.v; runExplain();
  }));
  $('#ex-lr').addEventListener('input', () => { $('#ex-lr-v').textContent = LRS[+$('#ex-lr').value]; });
  $('#ex-lr').addEventListener('change', runExplain);
  $('#ex-run').addEventListener('click', runExplain);
  $('#ex-demo').addEventListener('click', async () => {
    try { await demoDigit(sel.value); await waitFor(() => state.lastRes); runExplain(); } catch (e) { toast(e.message); }
  });
  function waitFor(fn, ms) {
    return new Promise(res => { const t0 = performance.now(); const tick = () => (fn() || performance.now() - t0 > (ms || 1500)) ? res() : setTimeout(tick, 40); tick(); });
  }
  let exSeq = 0;
  async function runExplain() {
    const box = $('#steps');
    if (!state.lastPixels) {
      box.innerHTML = '<div class="card muted">Nothing on the Draw pad yet. Press <b>Demo digit</b> or draw on the Draw &amp; inspect tab.</div>';
      gridCanvas($('#ex-input'), null, 'ink'); gridCanvas($('#ex-sal'), null, 'div');
      return;
    }
    const seq = ++exSeq;
    gridCanvas($('#ex-input'), state.lastPixels, 'ink');
    if (state.lastRes) gridCanvas($('#ex-sal'), state.lastRes.saliency, 'div');
    try {
      const body = { pixels: state.lastPixels, lr: LRS[+$('#ex-lr').value] };
      if (exLabel !== 'auto') body.label = +exLabel;
      const d = await api('/api/explain', body);
      if (seq !== exSeq) return;
      box.innerHTML = d.steps.map(s => {
        const back = /^(Backprop|Saliency|One gradient)/.test(s.title);
        let h = '<div class="card step' + (back ? ' back' : '') + '"><h3>' + esc(s.title) + '</h3><p>' + esc(s.text) + '</p>';
        if (s.math) h += '<div class="math">' + esc(s.math) + '</div>';
        if (s.table) {
          h += '<div class="tbl-wrap"><table class="tbl"><thead><tr>' + s.table.cols.map(c => '<th>' + esc(c) + '</th>').join('') + '</tr></thead><tbody>' +
            s.table.rows.map(r => '<tr>' + r.map(c => '<td>' + esc(c) + '</td>').join('') + '</tr>').join('') + '</tbody></table></div>';
        }
        return h + '</div>';
      }).join('');
    } catch (e) { box.innerHTML = '<div class="card">Could not explain: ' + esc(e.message) + '</div>'; }
  }

  // ---------------------------------------------------------------- TRAIN tab
  const T = {
    lr: [0.001, 0.003, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 1.5, 2.0],
    h1: [4, 8, 16, 32, 64, 128], h2: [0, 8, 16, 32], n: [100, 250, 500, 1000, 2000, 5000],
  };
  const PRESETS = [
    { name: 'Sensible defaults', why: 'lr 0.05, 32 neurons, 2,000 images: ~96% test in 3 epochs', v: { lr: 4, h1: 3, h2: 0, ep: 8, n: 4, act: 'relu', batch: 32, mom: 0.9 } },
    { name: 'Learning rate far too high (2.0)', why: 'steps overshoot: it collapses to guessing (10%)', v: { lr: 10, h1: 3, h2: 0, ep: 4, n: 4, act: 'relu', batch: 32, mom: 0.9 } },
    { name: 'Tiny brain: 4 hidden neurons', why: 'too little capacity: stuck near 85%', v: { lr: 4, h1: 0, h2: 0, ep: 8, n: 4, act: 'relu', batch: 32, mom: 0.9 } },
    { name: 'Overfitting: only 100 images', why: 'train accuracy hits 100%, test stays near 88%', v: { lr: 5, h1: 5, h2: 0, ep: 20, n: 0, act: 'relu', batch: 16, mom: 0.9 } },
    { name: 'Slow: no momentum, lr 0.01', why: 'same network: ~79% after 8 epochs instead of ~98%', v: { lr: 2, h1: 3, h2: 0, ep: 8, n: 4, act: 'relu', batch: 32, mom: 0 } },
    { name: 'Deeper with tanh: 64 + 32', why: 'like the pretrained net, but tanh instead of ReLU', v: { lr: 4, h1: 4, h2: 3, ep: 6, n: 4, act: 'tanh', batch: 32, mom: 0.9 } },
  ];
  function setForm(v) {
    $('#f-lr').value = v.lr; $('#f-h1').value = v.h1; $('#f-h2').value = v.h2; $('#f-ep').value = v.ep; $('#f-n').value = v.n;
    $('#f-act').value = v.act; $('#f-batch').value = String(v.batch); $('#f-mom').value = String(v.mom);
    formLabels();
  }
  function formLabels() {
    $('#lr-v').textContent = T.lr[+$('#f-lr').value];
    $('#h1-v').textContent = T.h1[+$('#f-h1').value];
    const h2 = T.h2[+$('#f-h2').value];
    $('#h2-v').textContent = h2 ? h2 : 'none';
    $('#ep-v').textContent = $('#f-ep').value;
    $('#n-v').textContent = T.n[+$('#f-n').value].toLocaleString();
  }
  ['#f-lr', '#f-h1', '#f-h2', '#f-ep', '#f-n'].forEach(s => $(s).addEventListener('input', formLabels));
  $('#presets').innerHTML = PRESETS.map((p, i) => '<button class="preset" data-i="' + i + '"><b>' + esc(p.name) + '</b>' + esc(p.why) + '</button>').join('');
  $$('#presets .preset').forEach(b => b.addEventListener('click', () => { setForm(PRESETS[+b.dataset.i].v); startTraining(); }));
  setForm(PRESETS[0].v);

  function formParams() {
    return { lr: T.lr[+$('#f-lr').value], hidden: T.h1[+$('#f-h1').value], hidden2: T.h2[+$('#f-h2').value],
      epochs: +$('#f-ep').value, train_size: T.n[+$('#f-n').value], activation: $('#f-act').value,
      batch: +$('#f-batch').value, momentum: +$('#f-mom').value, l2: 0.0001 };
  }
  let pollTimer = null;
  async function startTraining() {
    try {
      const st = await api('/api/train/start', formParams());
      renderTrain(st);
      poll();
    } catch (e) { toast(e.message); }
  }
  function poll() {
    clearTimeout(pollTimer);
    pollTimer = setTimeout(async () => {
      try {
        const st = await api('/api/train/status');
        renderTrain(st);
        if (st.state === 'running') poll();
      } catch (e) { toast('Lost contact with the trainer: ' + e.message); }
    }, 400);
  }
  $('#btn-train').addEventListener('click', startTraining);
  $('#btn-stop').addEventListener('click', async () => { try { renderTrain(await api('/api/train/stop', {})); } catch (e) { toast(e.message); } });
  $('#btn-adopt').addEventListener('click', async () => {
    try {
      const r = await api('/api/train/adopt', {});
      toast('The Draw tab now uses ' + r.source);
      await modelChanged();
    } catch (e) { toast(e.message); }
  });

  function lineChart(svg, opt) {
    const W = opt.w || 420, H = opt.h || 220, L = 40, R = 12, Tp = 30, B = 28;   // top band holds the legend
    const xMax = Math.max(opt.xMax || 1, 1e-9), yMin = opt.yMin || 0, yMax = opt.yMax > yMin ? opt.yMax : yMin + 1;
    const X = x => L + (W - L - R) * x / xMax, Y = y => Tp + (H - Tp - B) * (1 - (y - yMin) / (yMax - yMin));
    const out = [];
    for (let i = 0; i <= 4; i++) {
      const yv = yMin + (yMax - yMin) * i / 4, y = Y(yv);
      out.push('<line x1="' + L + '" x2="' + (W - R) + '" y1="' + y + '" y2="' + y + '" stroke="var(--grid)"/>');
      out.push('<text x="' + (L - 6) + '" y="' + (y + 3.5) + '" text-anchor="end">' + (opt.yFmt ? opt.yFmt(yv) : yv.toFixed(2)) + '</text>');
    }
    const step = Math.max(1, Math.ceil(xMax / 10));          // whole-number ticks
    for (let xv = 0; xv <= xMax + 1e-9; xv += step) {
      out.push('<text x="' + X(xv) + '" y="' + (H - 10) + '" text-anchor="middle">' + xv + '</text>');
    }
    out.push('<text x="' + (W - R) + '" y="' + (H - 0.5) + '" text-anchor="end">' + esc(opt.xLabel || 'epoch') + '</text>');
    for (const s of opt.series) {
      const pts = s.pts.filter(p => p[1] !== null && isFinite(p[1]));
      if (!pts.length) continue;
      const clip = v => Math.max(yMin, Math.min(yMax, v));
      const d = pts.map((p, i) => (i ? 'L' : 'M') + X(p[0]).toFixed(1) + ',' + Y(clip(p[1])).toFixed(1)).join(' ');
      out.push('<path d="' + d + '" fill="none" stroke="' + s.color + '" stroke-width="' + (s.width || 2) + '"' + (s.dash ? ' stroke-dasharray="' + s.dash + '"' : '') + ' stroke-linejoin="round" stroke-opacity="' + (s.opacity || 1) + '"/>');
      if (s.dots) for (const p of pts) out.push('<circle cx="' + X(p[0]).toFixed(1) + '" cy="' + Y(clip(p[1])).toFixed(1) + '" r="3" fill="' + s.color + '"/>');
    }
    let lx = L + 8;
    for (const s of opt.series) {
      if (!s.label) continue;
      out.push('<line x1="' + lx + '" x2="' + (lx + 16) + '" y1="10" y2="10" stroke="' + s.color + '" stroke-width="2.5"' + (s.dash ? ' stroke-dasharray="' + s.dash + '"' : '') + '/>');
      out.push('<text x="' + (lx + 21) + '" y="13.5" style="fill:var(--text-dim)">' + esc(s.label) + '</text>');
      lx += 30 + 6.2 * s.label.length;
    }
    if (opt.empty) out.push('<text x="' + (W / 2) + '" y="' + (H / 2) + '" text-anchor="middle">' + esc(opt.empty) + '</text>');
    svg.innerHTML = out.join('');
  }

  let lastTilesKey = '';
  function renderTrain(st) {
    const badge = $('#run-badge');
    badge.textContent = st.state; badge.className = 'badge ' + st.state;
    const running = st.state === 'running';
    $('#btn-stop').disabled = !running; $('#btn-train').disabled = running;
    $('#btn-adopt').disabled = !(st.state === 'done' || st.state === 'stopped') || !!st.diverged;
    const hist = st.history || [], p = st.params;
    if (!p) { lineChart($('#ch-loss'), { series: [], empty: 'No run yet' }); lineChart($('#ch-acc'), { series: [], empty: 'No run yet' }); return; }
    const epochs = p.epochs, done = (st.epoch || 0) + (running && st.n_batches ? st.batch / st.n_batches : 0);
    $('#run-progress').style.width = (100 * Math.min(1, done / epochs)).toFixed(1) + '%';
    let msg = st.sizes.join('-') + ' · ' + p.activation + ' · lr ' + p.lr + ' · epoch ' + (st.epoch || 0) + '/' + epochs + ' · ' + (st.elapsed || 0).toFixed(1) + ' s';
    if (st.diverged) msg += ' · loss blew up (NaN/∞): the learning rate is too high';
    if (st.error) msg += ' · error: ' + st.error;
    $('#run-status').textContent = msg;
    const lastH = hist[hist.length - 1];
    $('#k-loss').textContent = lastH && lastH.loss !== null ? lastH.loss.toFixed(3) : (st.batch_loss && st.batch_loss.length && st.batch_loss[st.batch_loss.length - 1][1] !== null ? st.batch_loss[st.batch_loss.length - 1][1].toFixed(3) : '–');
    if (lastH && lastH.diverged) $('#k-loss').textContent = '∞';
    $('#k-train').textContent = lastH && lastH.train_acc !== null ? pct(lastH.train_acc) : '–';
    $('#k-test').textContent = lastH && lastH.test_acc !== null ? pct(lastH.test_acc) : (st.test_acc0 !== undefined ? pct(st.test_acc0) : '–');
    $('#k-params').textContent = st.n_params.toLocaleString();
    const pal = palette();
    const bl = (st.batch_loss || []).filter(q => q[1] !== null);
    let ym = 0.5;
    for (const q of bl) ym = Math.max(ym, Math.min(q[1], 4));
    for (const h of hist) if (h.loss !== null) ym = Math.max(ym, Math.min(h.loss, 4));
    lineChart($('#ch-loss'), { xMax: epochs, yMin: 0, yMax: Math.ceil(ym * 4) / 4, series: [
      { pts: bl, color: rgb(pal.muted), width: 1.1, opacity: 0.7, label: 'each batch' },
      { pts: [[0, null]].concat(hist.map(h => [h.epoch, h.loss])), color: rgb(pal.brand), width: 2.5, dots: true, label: 'epoch mean' }] });
    const accPts = k => [[0, st.test_acc0 !== undefined ? st.test_acc0 : null]].concat(hist.map(h => [h.epoch, h[k]])).filter(q => q[1] !== null);
    lineChart($('#ch-acc'), { xMax: epochs, yMin: 0, yMax: 1, yFmt: v => Math.round(v * 100) + '%', series: [
      { pts: accPts('train_acc').slice(1), color: rgb(pal.brand), width: 2.5, dots: true, label: 'train' },
      { pts: accPts('test_acc'), color: rgb(pal.pos), width: 2.5, dots: true, dash: '5 3', label: 'test' }] });
    const key = st.run + ':' + st.epoch;
    if (st.tiles && key !== lastTilesKey) {
      lastTilesKey = key;
      const tiles = $('#tiles');
      if (tiles.children.length !== st.tiles.length) tiles.innerHTML = st.tiles.map(() => '<canvas width="16" height="16"></canvas>').join('');
      st.tiles.forEach((t, i) => gridCanvas(tiles.children[i], t, 'div'));
      $('#tiles-sub').textContent = st.tiles.length + ' of ' + p.hidden + ' neurons after epoch ' + (st.epoch || 0) + ' · cyan = positive, rose = negative';
    }
  }

  // ---------------------------------------------------------------- EVALUATION tab
  let evalData = null, cmSel = null, sampleDigit = 'all';
  async function loadEval() {
    try {
      evalData = await api('/api/evaluation');
      renderEval();
    } catch (e) { toast('Evaluation failed: ' + e.message); }
  }
  function renderEval() {
    const e = evalData;
    if (!e) return;
    const kp = [
      [pct(e.accuracy), 'test accuracy (' + e.n.toLocaleString() + ' synthetic digits)'],
      [e.n_wrong, 'mistakes on the test set'],
      [e.ms_per_image.toFixed(2) + ' ms', 'forward pass per image · ' + e.inspect_ms_median.toFixed(1) + ' ms with saliency'],
      [e.train_seconds ? Math.round(e.train_seconds) + ' s' : '–', 'training time, pure Python (' + (state.model ? state.model.n_params.toLocaleString() : '') + ' weights)'],
    ];
    $('#eval-kpis').innerHTML = kp.map(k => '<div class="kpi"><div class="v">' + k[0] + '</div><div class="l">' + esc(k[1]) + '</div></div>').join('');
    // confusion matrix
    let mOff = 1;
    e.confusion.forEach((r, i) => r.forEach((v, j) => { if (i !== j) mOff = Math.max(mOff, v); }));
    const pal = palette();
    let h = '<tr><th></th>' + [0, 1, 2, 3, 4, 5, 6, 7, 8, 9].map(k => '<th>' + k + '</th>').join('') + '</tr>';
    e.confusion.forEach((r, i) => {
      const n = r.reduce((a, b) => a + b, 0) || 1;
      h += '<tr><th>' + i + '</th>' + r.map((v, j) => {
        const bg = i === j ? rgb(mix(pal.base, pal.brand, 0.25 + 0.75 * v / n)) : (v ? rgb(mix(pal.base, pal.neg, 0.25 + 0.75 * v / mOff)) : 'var(--surface-2)');
        const col = i === j && v / n > 0.5 ? '#fff' : '';
        return '<td data-t="' + i + '" data-p="' + j + '" class="' + (v ? '' : 'zero') + (cmSel && cmSel[0] === i && cmSel[1] === j ? ' sel' : '') + '" style="background:' + bg + (col ? ';color:' + col : '') + '" title="true ' + i + ', predicted ' + j + ': ' + v + '">' + v + '</td>';
      }).join('') + '</tr>';
    });
    $('#cm').innerHTML = h;
    $$('#cm td').forEach(td => td.addEventListener('click', () => {
      const t = +td.dataset.t, p = +td.dataset.p;
      cmSel = (cmSel && cmSel[0] === t && cmSel[1] === p) || t === p ? null : [t, p];
      renderEval();
    }));
    $('#per-class').innerHTML = e.per_class.map(c => '<div class="pc-row" style="grid-template-columns:22px 1fr 96px"><b>' + c.digit + '</b><div class="pc-track"><div style="width:' + (100 * c.recall).toFixed(1) + '%"></div></div><span>' + pct(c.recall) + ' <span class="muted">(' + pct(c.precision, 0) + ')</span></span></div>').join('');
    const hist = e.history || [];
    if (hist.length) {
      $('#hist-sub').textContent = hist.length + ' epochs on ' + (state.model && state.model.pretrained.n_train || '') + ' images';
      lineChart($('#ch-hist'), { w: 640, h: 230, xMax: hist.length, yMin: 0, yMax: 1, yFmt: v => v.toFixed(2), series: [
        { pts: hist.map(r => [r.epoch, Math.min(1, r.loss)]), color: rgb(pal.neg), width: 2, dots: true, label: 'loss' },
        { pts: hist.map(r => [r.epoch, r.test_acc]), color: rgb(pal.pos), width: 2.5, dots: true, label: 'test accuracy' }] });
    } else {
      $('#hist-sub').textContent = '';
      lineChart($('#ch-hist'), { w: 640, h: 230, series: [], empty: 'Current network: ' + (e.model || '') });
    }
    let wrong = e.misclassified;
    if (cmSel) wrong = wrong.filter(w => w.true === cmSel[0] && w.pred === cmSel[1]);
    $('#wrong-sub').textContent = (cmSel ? 'true ' + cmSel[0] + ' → predicted ' + cmSel[1] + ' · ' : '') + 'showing ' + wrong.length + ' of ' + e.n_wrong + ' · most confident first';
    $('#wrong').innerHTML = wrong.length ? wrong.map((w, i) => '<div class="g-item"><canvas id="w' + i + '" width="16" height="16"></canvas><span class="good">' + w.true + '</span>→<span class="bad">' + w.pred + '</span> ' + Math.round(100 * w.conf) + '%</div>').join('') : '<p class="muted small">No mistakes here.</p>';
    wrong.forEach((w, i) => gridCanvas($('#w' + i), bytesToFloats(w.pixels), 'ink'));
  }
  $('#sample-digits').innerHTML = ['all', 0, 1, 2, 3, 4, 5, 6, 7, 8, 9].map(v => '<button class="chip' + (v === 'all' ? ' on' : '') + '" data-v="' + v + '">' + v + '</button>').join('');
  $$('#sample-digits .chip').forEach(c => c.addEventListener('click', () => {
    $$('#sample-digits .chip').forEach(x => x.classList.toggle('on', x === c));
    sampleDigit = c.dataset.v; loadSamples();
  }));
  async function loadSamples() {
    try {
      const d = await api('/api/samples?n=40' + (sampleDigit === 'all' ? '' : '&digit=' + sampleDigit) + '&offset=' + (sampleDigit === 'all' ? 0 : 0));
      $('#samples').innerHTML = d.samples.map((s, i) => '<div class="g-item"><canvas id="s' + i + '" width="16" height="16"></canvas>' + s.label + '</div>').join('');
      d.samples.forEach((s, i) => gridCanvas($('#s' + i), bytesToFloats(s.pixels), 'ink'));
    } catch (e) { toast(e.message); }
  }

  // ---------------------------------------------------------------- TEACH tab
  let tLabel = null;
  const tpad = new DrawPad($('#tpad'), $('#tpad-overlay'), $('#tpad-empty'), () => predictTeach());
  buildBars($('#tbars'), true);
  const predictTeach = makePredictor(tpad, (res) => {
    setBars($('#tbars'), res.probs, res.pred);
    $('#t-pred').innerHTML = 'Current guess: <b>' + res.pred + '</b> (' + pct(res.confidence) + ')' + (tLabel !== null ? (res.pred === tLabel ? ' · <span style="color:var(--ok)">already right</span>' : ' · <span style="color:var(--neg)">wrong, teach it!</span>') : '');
  }, () => { setBars($('#tbars'), null); $('#t-pred').textContent = 'Current guess: –'; });
  $('#t-label').innerHTML = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9].map(v => '<button class="chip" data-v="' + v + '">' + v + '</button>').join('');
  $$('#t-label .chip').forEach(c => c.addEventListener('click', () => {
    $$('#t-label .chip').forEach(x => x.classList.toggle('on', x === c));
    tLabel = +c.dataset.v; predictTeach();
  }));
  $('#t-clear-pad').addEventListener('click', () => tpad.reset());
  $('#t-add').addEventListener('click', async () => {
    if (tpad.isEmpty()) return toast('Draw a digit first');
    if (tLabel === null) return toast('Pick the correct label (0–9) first');
    try {
      await api('/api/teach/add', { pixels: tpad.read().px.map(v => Math.round(v * 1000) / 1000), label: tLabel });
      tpad.reset(); toast('Added a ' + tLabel + ' to the teaching set');
      loadTeach();
    } catch (e) { toast(e.message); }
  });
  $('#t-demo').addEventListener('click', async () => {
    try { const r = await api('/api/teach/demo', {}); toast('Added ' + r.added + ' LCD-style digits'); loadTeach(); } catch (e) { toast(e.message); }
  });
  $('#t-clear').addEventListener('click', async () => { try { await api('/api/teach/clear', {}); loadTeach(); } catch (e) { toast(e.message); } });
  $('#ft-steps').addEventListener('input', () => { $('#ft-steps-v').textContent = $('#ft-steps').value; });
  $('#ft-rep').addEventListener('input', () => { $('#ft-rep-v').textContent = $('#ft-rep').value; });
  $('#t-tune').addEventListener('click', async () => {
    const btn = $('#t-tune');
    btn.disabled = true; btn.textContent = 'Teaching…';
    try {
      const r = await api('/api/teach/finetune', { steps: +$('#ft-steps').value, replay: +$('#ft-rep').value });
      renderFinetune(r);
      await modelChanged();
    } catch (e) { toast(e.message); }
    finally { btn.disabled = false; btn.textContent = 'Teach it!'; }
  });
  $('#t-reset').addEventListener('click', async () => {
    try { await api('/api/model/reset', {}); toast('Back to the pretrained network'); $('#ft-result').innerHTML = ''; await modelChanged(); } catch (e) { toast(e.message); }
  });
  async function loadTeach() {
    try {
      const d = await api('/api/teach');
      $('#t-count').textContent = d.items.length;
      $('#t-items').innerHTML = d.items.length ? d.items.map((it, i) => '<div class="g-item t-item"><canvas id="ti' + i + '" width="16" height="16"></canvas><button class="x" data-id="' + it.id + '" title="Remove">×</button>' +
        '<b>' + it.label + '</b> ' + (it.pred === it.label ? '<span class="good">✓' + Math.round(100 * it.p_label) + '%</span>' : '<span class="bad">✗ ' + it.pred + '</span>') + '</div>').join('')
        : '<p class="muted small">Empty. Draw something on the left and add it, or press <b>Load demo lesson</b>.</p>';
      d.items.forEach((it, i) => gridCanvas($('#ti' + i), it.pixels, 'ink'));
      $$('#t-items .x').forEach(b => b.addEventListener('click', async () => {
        try { await api('/api/teach/delete', { id: +b.dataset.id }); loadTeach(); } catch (e) { toast(e.message); }
      }));
      const right = d.items.filter(it => it.pred === it.label).length;
      $('#t-lcd').innerHTML = (d.items.length ? 'Gets <b>' + right + ' / ' + d.items.length + '</b> of your examples right. ' : '') +
        'On 30 <i>other</i> LCD-style digits it has never been shown: <b>' + pct(d.lcd_check_acc, 0) + '</b> correct (' + esc(d.model) + ').';
    } catch (e) { toast(e.message); }
  }
  function renderFinetune(r) {
    const pal = palette();
    const cmp = (a, b, f) => '<span>' + f(a) + '</span><span class="arrow">→</span><span class="after" style="color:' + (b >= a ? 'var(--ok)' : 'var(--neg)') + '">' + f(b) + '</span>';
    $('#ft-result').innerHTML =
      '<div class="kv" style="grid-template-columns:1fr 1fr">' +
      '<div class="kpi"><div class="v cmp">' + cmp(r.correct_before, r.correct_after, v => v + '/' + r.examples.length) + '</div><div class="l">your examples right (fixed ' + r.fixed + ')</div></div>' +
      '<div class="kpi"><div class="v cmp">' + cmp(r.lcd_check_before, r.lcd_check_after, v => pct(v, 0)) + '</div><div class="l">unseen LCD digits (generalisation)</div></div>' +
      '<div class="kpi"><div class="v cmp">' + cmp(r.test_acc_before, r.test_acc_after, v => pct(v, 1)) + '</div><div class="l">original test set (forgetting?)</div></div>' +
      '<div class="kpi"><div class="v">' + r.seconds.toFixed(1) + ' s</div><div class="l">' + r.steps + ' SGD steps, ' + r.replay + ' replayed images each</div></div></div>' +
      '<div class="chart" style="margin-top:8px"><svg id="ch-ft" viewBox="0 0 420 150"></svg></div>';
    lineChart($('#ch-ft'), { h: 150, xMax: r.losses.length, yMin: 0, yMax: Math.max(0.5, Math.ceil(Math.max.apply(null, r.losses) * 4) / 4), xLabel: 'step', series: [
      { pts: r.losses.map((l, i) => [i + 1, l]), color: rgb(pal.brand), width: 2, label: 'batch loss' }] });
  }

  // ---------------------------------------------------------------- model state + tabs
  async function refreshModel() {
    try {
      state.model = await api('/api/model');
      const m = state.model, pre = m.source === 'pretrained';
      $('#model-pill').classList.toggle('tuned', !pre);
      $('#model-pill-text').textContent = (pre ? 'pretrained' : m.source) + ' · ' + m.sizes.join('-') + (pre && m.pretrained.test_acc ? ' · ' + pct(m.pretrained.test_acc) + ' test' : '');
    } catch (e) { $('#model-pill-text').textContent = 'server offline?'; }
  }
  async function modelChanged() {
    state.weights = null; evalData = null;
    await refreshModel();
    predictDraw(); predictTeach();
    if (state.tab === 'teach') loadTeach();
    if (state.tab === 'eval') loadEval();
  }
  function showTab(name) {
    state.tab = name;
    $$('.tab').forEach(t => t.classList.toggle('is-active', t.dataset.tab === name));
    $$('.view').forEach(v => v.classList.toggle('is-active', v.id === 'view-' + name));
    if (name === 'explain') runExplain();
    if (name === 'eval') { if (!evalData) loadEval(); else renderEval(); if (!$('#samples').children.length) loadSamples(); }
    if (name === 'teach') loadTeach();
    if (name === 'train') api('/api/train/status').then(st => { renderTrain(st); if (st.state === 'running') poll(); }).catch(() => {});
    try { localStorage.setItem('nc-tab', name); } catch (e) { /* private mode */ }
  }
  $$('.tab').forEach(t => t.addEventListener('click', () => showTab(t.dataset.tab)));
  $('#btn-theme').addEventListener('click', () => {
    const next = isDark() ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    try { localStorage.setItem('nc-theme', next); } catch (e) { /* ignore */ }
    PAL = null; rerender();
  });
  if (window.matchMedia) {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    if (mq.addEventListener) mq.addEventListener('change', () => { PAL = null; rerender(); });
  }
  function rerender() {
    predictDraw(); predictTeach();
    if (evalData) renderEval();
    if (state.tab === 'train') api('/api/train/status').then(renderTrain).catch(() => {});
  }

  // ---------------------------------------------------------------- boot
  renderDrawEmpty();
  refreshModel().then(() => {
    // Open with a demo digit already being drawn, so the first screen is alive.
    setTimeout(() => { if (pad.isEmpty()) demoDigit(3, 11).catch(() => {}); }, 150);
  });
})();
