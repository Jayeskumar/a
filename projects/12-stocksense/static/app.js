/* StockSense dashboard - vanilla JS, hand-drawn SVG charts, no external libraries. */
'use strict';

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
const NS = 'http://www.w3.org/2000/svg';
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const MODEL_VAR = { snaive: '--s-blue', ma: '--s-aqua', hw: '--s-violet', linreg: '--s-orange' };
const MODEL_SHORT = { snaive: 'Seasonal naive', ma: 'Moving avg', hw: 'Holt-Winters', linreg: 'Regression' };
const STATUS = {
  urgent: ['▲', 'Urgent'], order: ['●', 'Order'], ok: ['✓', 'OK'], overstock: ['◆', 'Overstock'],
};

const state = {
  service: 0.95, tab: 'overview', filter: 'need', search: '', ruleSearch: '',
  summary: null, trend: null, plan: null, whatif: null, lb: null, skus: null, fest: null,
  abc: null, basket: null, sim: null, health: null,
  sku: null, skuDetail: null, hidden: new Set(['snaive', 'ma']), simSku: null,
  simSort: { key: 'gain', dir: -1 }, abcCell: null, openRows: new Set(), support: 0.02, conf: 0.3,
};

/* ------------------------------------------------------------------ utils */
function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function cssVar(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
function fmtINR(v) {
  if (v == null || isNaN(v)) return '–';
  const a = Math.abs(v), sign = v < 0 ? '−' : '';
  if (a >= 1e7) return sign + '₹' + (a / 1e7).toFixed(2) + ' Cr';
  if (a >= 1e5) return sign + '₹' + (a / 1e5).toFixed(2) + ' L';
  if (a >= 1e4) return sign + '₹' + (a / 1e3).toFixed(1) + 'k';
  return sign + '₹' + Math.round(a).toLocaleString('en-IN');
}
function fmtINRFull(v) { return v == null ? '–' : '₹' + Math.round(v).toLocaleString('en-IN'); }
function fmtNum(v, d = 0) { return v == null || isNaN(v) ? '–' : Number(v).toLocaleString('en-IN', { maximumFractionDigits: d, minimumFractionDigits: d }); }
function fmtPct(v, d = 1) { return v == null || isNaN(v) ? '–' : (v * 100).toFixed(d) + '%'; }
function fmtCompact(v) {
  const a = Math.abs(v);
  if (a >= 1e7) return (v / 1e7).toFixed(a >= 1e8 ? 0 : 1) + 'Cr';
  if (a >= 1e5) return (v / 1e5).toFixed(a >= 1e6 ? 0 : 1) + 'L';
  if (a >= 1e3) return (v / 1e3).toFixed(a >= 1e4 ? 0 : 1) + 'k';
  return String(Math.round(v * 100) / 100);
}
function fmtDate(iso, year) {
  if (!iso) return '';
  const [y, m, d] = iso.split('-').map(Number);
  return d + ' ' + MONTHS[m - 1] + (year ? ' ' + y : '');
}
function chg(pct, goodWhenDown = true) {
  if (pct == null) return '';
  const good = goodWhenDown ? pct < 0 : pct > 0;
  const cls = Math.abs(pct) < 0.05 ? '' : good ? 'delta-good' : 'delta-bad';
  return `<span class="${cls}">${pct > 0 ? '+' : pct < 0 ? '−' : ''}${Math.abs(pct).toFixed(1)}%</span>`;
}
function statusChip(s) { const [i, t] = STATUS[s] || ['', s]; return `<span class="status ${esc(s)}">${i} ${t}</span>`; }
function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }
function toast(msg, ms = 2600) {
  const t = $('#toast'); t.textContent = msg; t.classList.add('show');
  clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove('show'), ms);
}
async function api(path, opts) {
  const r = await fetch(path, opts);
  let j = null;
  try { j = await r.json(); } catch (e) { j = { error: 'unexpected response' }; }
  if (!r.ok) throw new Error((j && j.error) || r.statusText);
  return j;
}
const svc = () => 'service=' + state.service;
function shortName(n) { return String(n).replace(/\s+\d+(\.\d+)?\s*(kg|g|ml|L)\b/i, '').replace(/\s*\(.*?\)\s*/g, ' ').trim(); }

/* ------------------------------------------------------------------ tooltip */
const tip = {
  el: null,
  show(html, x, y) {
    const t = this.el; t.innerHTML = html; t.classList.add('show');
    const r = t.getBoundingClientRect();
    let left = x + 14, top = y + 14;
    if (left + r.width > window.innerWidth - 8) left = x - r.width - 14;
    if (top + r.height > window.innerHeight - 8) top = y - r.height - 14;
    t.style.left = Math.max(8, left) + 'px'; t.style.top = Math.max(8, top) + 'px';
  },
  hide() { this.el.classList.remove('show'); },
};
function tipRows(head, rows) {
  return `<div class="t-head">${esc(head)}</div>` + rows.map(r =>
    `<div class="t-row"><span>${r.color ? `<i class="line-key" style="background:${r.color}"></i>` : ''}${esc(r.name)}</span><b>${esc(r.value)}</b></div>`).join('');
}

/* ------------------------------------------------------------------ charts */
function svgEl(tag, attrs, parent) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}
function niceTicks(min, max, count) {
  if (!(max > min)) max = min + 1;
  const step0 = (max - min) / count;
  const mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const norm = step0 / mag;
  const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag;
  const lo = Math.floor(min / step + 1e-9) * step, hi = Math.ceil(max / step - 1e-9) * step;
  const ticks = [];
  for (let v = lo; v <= hi + step / 2; v += step) ticks.push(Math.round(v * 1e6) / 1e6);
  return { lo, hi: hi > lo ? hi : lo + step, ticks };
}
function legend(el, items) {
  el.innerHTML = '';
  items.forEach(it => {
    const k = document.createElement(it.onClick ? 'button' : 'span');
    k.className = 'key' + (it.off ? ' off' : '');
    if (it.onClick) { k.type = 'button'; k.addEventListener('click', it.onClick); k.setAttribute('aria-pressed', String(!it.off)); }
    const sw = document.createElement('i');
    sw.className = 'swatch' + (it.type === 'box' ? ' box' : it.type === 'band' ? ' band box' : it.type === 'dot' ? ' box' : '');
    if (it.type === 'dot') sw.style.borderRadius = '50%';
    sw.style.background = it.color;
    k.appendChild(sw);
    k.appendChild(document.createTextNode(it.name));
    el.appendChild(k);
  });
}

/**
 * Line / band / bar chart with a crosshair tooltip listing every series at the hovered x.
 * cfg: {x: labels[], xv?: numeric x[], series: [{name, values, color, width, dash, band:{lo,hi}, fmt}],
 *       bars: [{name, values, color}], dots: [{i, v, color, label}], vlines: [{i, label}],
 *       hlines: [{y, label}], split, yFormat, xFormat, yMin, tipHead(i), extraTip(i)}
 */
function lineChart(el, cfg) {
  el.innerHTML = '';
  const W = Math.max(260, el.clientWidth || 600), H = el.clientHeight || 260;
  const n = cfg.x.length;
  if (!n) { el.innerHTML = '<p class="empty-note">No data</p>'; return; }
  let ymax = -Infinity, ymin = Infinity;
  const consider = v => { if (v != null && isFinite(v)) { ymax = Math.max(ymax, v); ymin = Math.min(ymin, v); } };
  cfg.series.forEach(s => { s.values.forEach(consider); if (s.band) { s.band.hi.forEach(consider); s.band.lo.forEach(consider); } });
  (cfg.bars || []).forEach(b => b.values.forEach(consider));
  (cfg.hlines || []).forEach(h => consider(h.y));
  if (!isFinite(ymax)) { ymax = 1; ymin = 0; }
  const t = niceTicks(cfg.yMin != null ? Math.min(cfg.yMin, ymin) : ymin, cfg.yMax != null ? cfg.yMax : ymax, cfg.yTicks || 4);
  const fy = cfg.yFormat || fmtCompact;
  const labelW = Math.max(...t.ticks.map(v => fy(v).length)) * 6.4 + 12;
  const m = { l: Math.max(30, labelW), r: 14, t: 16, b: 24 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  let xs;
  if (cfg.xv) {
    const a = Math.min(...cfg.xv), b = Math.max(...cfg.xv);
    xs = i => m.l + (b > a ? (cfg.xv[i] - a) / (b - a) : 0.5) * iw;
  } else {
    xs = i => m.l + (n > 1 ? i / (n - 1) : 0.5) * iw;
  }
  const ys = v => m.t + ih - (v - t.lo) / (t.hi - t.lo) * ih;
  const svg = svgEl('svg', { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img', 'aria-label': cfg.label || 'chart', tabindex: 0 });
  const cGrid = cssVar('--grid'), cMuted = cssVar('--muted'), cSurface = cssVar('--surface');
  const gA = svgEl('g', { class: 'axis' }, svg);
  t.ticks.forEach(v => {
    const y = ys(v);
    svgEl('line', { x1: m.l, x2: W - m.r, y1: y, y2: y, stroke: cGrid, 'stroke-width': 1 }, gA);
    svgEl('text', { x: m.l - 8, y: y + 4, 'text-anchor': 'end' }, gA).textContent = fy(v);
  });
  svgEl('line', { x1: m.l, x2: W - m.r, y1: ys(t.lo), y2: ys(t.lo), stroke: cssVar('--axis'), 'stroke-width': 1 }, gA);
  const fx = cfg.xFormat || (v => v);
  const nt = Math.max(2, Math.min(cfg.xTicks || Math.floor(iw / 90), n));
  const idxs = cfg.xTickIdx || Array.from({ length: nt }, (_, k) => Math.round(k * (n - 1) / (nt - 1)));
  idxs.forEach(i => {
    const anchor = i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle';
    svgEl('text', { x: xs(i), y: H - 6, 'text-anchor': anchor }, gA).textContent = fx(cfg.x[i], i);
  });
  if (cfg.split != null && cfg.split < n) {
    const step = n > 1 ? iw / (n - 1) : 0;
    const x0 = xs(cfg.split) - step / 2;
    svgEl('rect', { x: x0, y: m.t, width: W - m.r - x0, height: ih, fill: cssVar('--brand-wash'), opacity: 0.55 }, svg);
    svgEl('line', { x1: x0, x2: x0, y1: m.t, y2: m.t + ih, stroke: cssVar('--axis'), 'stroke-width': 1 }, svg);
    const lab = svgEl('text', { x: x0 + 6, y: m.t + 11, fill: cMuted, 'font-size': 11 }, svg);
    lab.textContent = cfg.splitLabel || 'forecast →';
  }
  (cfg.vlines || []).forEach(v => {
    if (v.i < 0 || v.i >= n) return;
    const x = xs(v.i);
    svgEl('line', { x1: x, x2: x, y1: m.t, y2: m.t + ih, stroke: v.color || cMuted, 'stroke-width': 1, opacity: 0.7 }, svg);
    // keep the label inside the plot: flip it to the left of its line when it would run past the right edge
    const anchor = v.anchor === 'end' || x + 4 + String(v.label).length * 6.4 > W - 2 ? 'end' : 'start';
    const tx = svgEl('text', { x: x + (anchor === 'end' ? -4 : 4), y: m.t + (v.y || 24), fill: v.color || cMuted, 'font-size': 11, 'text-anchor': anchor, 'font-weight': 600 }, svg);
    tx.textContent = v.label;
  });
  (cfg.hlines || []).forEach(h => {
    const y = ys(h.y);
    svgEl('line', { x1: m.l, x2: W - m.r, y1: y, y2: y, stroke: cssVar('--axis'), 'stroke-width': 1 }, svg);
    svgEl('text', { x: m.l + 6, y: y - 5, fill: cMuted, 'font-size': 11, 'text-anchor': 'start' }, svg).textContent = h.label;
  });
  // bars (under lines)
  (cfg.bars || []).forEach(b => {
    const bw = Math.max(1.5, Math.min(24, (iw / n) * 0.62));
    const g = svgEl('g', {}, svg);
    b.values.forEach((v, i) => {
      if (v == null || v <= 0) return;
      const y = ys(v), y0 = ys(Math.max(0, t.lo));
      svgEl('rect', { x: xs(i) - bw / 2, y, width: bw, height: Math.max(0.5, y0 - y), fill: b.color, opacity: b.opacity || 0.35, rx: Math.min(2, bw / 3) }, g);
    });
  });
  // bands + lines
  const pathFor = (vals) => {
    let d = '', pen = false;
    vals.forEach((v, i) => {
      if (v == null || !isFinite(v)) { pen = false; return; }
      d += (pen ? 'L' : 'M') + xs(i).toFixed(1) + ' ' + ys(v).toFixed(1);
      pen = true;
    });
    return d;
  };
  cfg.series.forEach(s => {
    if (!s.band) return;
    let d = '';
    const idx = s.band.lo.map((v, i) => (v == null ? null : i)).filter(i => i != null);
    if (!idx.length) return;
    idx.forEach((i, k) => { d += (k ? 'L' : 'M') + xs(i).toFixed(1) + ' ' + ys(s.band.hi[i]).toFixed(1); });
    idx.slice().reverse().forEach(i => { d += 'L' + xs(i).toFixed(1) + ' ' + ys(s.band.lo[i]).toFixed(1); });
    svgEl('path', { d: d + 'Z', fill: s.color, opacity: 0.13, stroke: 'none' }, svg);
  });
  cfg.series.forEach(s => {
    const d = pathFor(s.values);
    if (!d) return;
    svgEl('path', { d, fill: 'none', stroke: s.color, 'stroke-width': s.width || 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round', 'stroke-dasharray': s.dash || 'none', opacity: s.opacity || 1 }, svg);
    if (s.endDot) {
      const last = s.values.map((v, i) => (v == null ? -1 : i)).filter(i => i >= 0).pop();
      if (last != null) svgEl('circle', { cx: xs(last), cy: ys(s.values[last]), r: 4, fill: s.color, stroke: cSurface, 'stroke-width': 2 }, svg);
    }
  });
  (cfg.dots || []).forEach(p => {
    svgEl('circle', { cx: xs(p.i), cy: ys(p.v), r: p.r || 4, fill: p.color, stroke: cSurface, 'stroke-width': 2 }, svg);
  });
  // hover layer
  const cross = svgEl('line', { y1: m.t, y2: m.t + ih, stroke: cMuted, 'stroke-width': 1, opacity: 0 }, svg);
  const hl = svgEl('g', {}, svg);
  const hit = svgEl('rect', { x: m.l, y: m.t, width: iw, height: ih, fill: 'transparent' }, svg);
  const nearest = px => {
    if (cfg.xv) {
      let best = 0, bd = Infinity;
      for (let i = 0; i < n; i++) { const dd = Math.abs(xs(i) - px); if (dd < bd) { bd = dd; best = i; } }
      return best;
    }
    return Math.max(0, Math.min(n - 1, Math.round((px - m.l) / iw * (n - 1))));
  };
  const showAt = (i, cx, cy) => {
    const x = xs(i);
    cross.setAttribute('x1', x); cross.setAttribute('x2', x); cross.setAttribute('opacity', 0.6);
    hl.innerHTML = '';
    const rows = [];
    cfg.series.forEach(s => {
      const v = s.values[i];
      if (v == null) return;
      svgEl('circle', { cx: x, cy: ys(v), r: 4, fill: s.color, stroke: cSurface, 'stroke-width': 2 }, hl);
      rows.push({ name: s.name, value: (s.fmt || fy)(v), color: s.color });
      if (s.band && s.band.lo[i] != null) rows.push({ name: '80% band', value: (s.fmt || fy)(s.band.lo[i]) + ' – ' + (s.fmt || fy)(s.band.hi[i]) });
    });
    (cfg.bars || []).forEach(b => { if (b.values[i] != null) rows.push({ name: b.name, value: (b.fmt || fy)(b.values[i]), color: b.color }); });
    if (cfg.extraTip) rows.push(...cfg.extraTip(i));
    const head = cfg.tipHead ? cfg.tipHead(i) : String(cfg.x[i]);
    tip.show(tipRows(head, rows), cx, cy);
  };
  let focusI = n - 1;
  hit.addEventListener('pointermove', ev => {
    const r = svg.getBoundingClientRect();
    const px = (ev.clientX - r.left) * (W / r.width);
    focusI = nearest(px);
    showAt(focusI, ev.clientX, ev.clientY);
  });
  const clear = () => { cross.setAttribute('opacity', 0); hl.innerHTML = ''; tip.hide(); };
  hit.addEventListener('pointerleave', clear);
  svg.addEventListener('blur', clear);
  svg.addEventListener('keydown', ev => {
    if (ev.key !== 'ArrowLeft' && ev.key !== 'ArrowRight') return;
    ev.preventDefault();
    focusI = Math.max(0, Math.min(n - 1, focusI + (ev.key === 'ArrowLeft' ? -1 : 1)));
    const r = svg.getBoundingClientRect();
    showAt(focusI, r.left + xs(focusI) * r.width / W, r.top + m.t + 10);
  });
  el.appendChild(svg);
}

/** HTML horizontal bars: rows [{label, value, max, color, text, title}] */
function hbars(el, rows, opts = {}) {
  const max = opts.max || Math.max(1e-9, ...rows.map(r => Math.max(r.value || 0, r.value2 || 0)));
  el.innerHTML = `<div class="hbars">${rows.map(r => {
    const w = Math.max(0.5, 100 * (r.value || 0) / max);
    const w2 = r.value2 != null ? Math.max(0.5, 100 * r.value2 / max) : null;
    return `<div class="hbar${w2 != null ? ' pair' : ''}" title="${esc(r.title || '')}">
      <span class="lbl">${esc(r.label)}</span>
      <span class="track"><span class="fill" style="width:${w}%;background:${r.color}"></span>${w2 != null ? `<span class="fill b2" style="width:${w2}%;background:${r.color2}"></span>` : ''}</span>
      <span class="val">${r.text}</span></div>`;
  }).join('')}</div>`;
}

/* ------------------------------------------------------------------ loading */
async function loadCore() {
  document.body.classList.add('loading');
  try {
    const [summary, trend, plan, whatif, lb, skus, fest] = await Promise.all([
      api('/api/summary?' + svc()), api('/api/trend'), api('/api/reorder?' + svc()),
      api('/api/whatif?' + svc()), api('/api/leaderboard'), api('/api/skus?' + svc()), api('/api/festivals'),
    ]);
    Object.assign(state, { summary, trend, plan, whatif, lb, skus: skus.skus, fest: fest.festivals });
    state.abc = state.basket = state.sim = state.skuDetail = null;
    if (!state.sku || !skus.skus.some(s => s.sku === state.sku)) {
      const top = plan.rows.find(r => r.status === 'urgent') || plan.rows[0];
      state.sku = top ? top.sku : skus.skus[0].sku;
    }
    renderHeader(); renderOverview(); renderReorder(); fillSkuSelect();
    renderData();
    await showTab(state.tab, true);
  } catch (e) {
    toast('Could not load data: ' + e.message, 5000);
  } finally {
    document.body.classList.remove('loading');
  }
}

async function refreshService() {
  try {
    const [summary, plan, whatif] = await Promise.all([
      api('/api/summary?' + svc()), api('/api/reorder?' + svc()), api('/api/whatif?' + svc())]);
    Object.assign(state, { summary, plan, whatif });
    state.sim = null; state.skuDetail = null;
    renderOverview(); renderReorder();
    if (state.tab === 'sim') await ensureSim();
    if (state.tab === 'sku') await loadSku(state.sku);
  } catch (e) { toast(e.message, 4000); }
}

/* ------------------------------------------------------------------ header + tabs */
function renderHeader() {
  const s = state.summary;
  const src = s.source === 'demo' ? 'Demo store' : 'Your data';
  $('#dataBadge').textContent = `${src} · ${s.skus} SKUs · ${s.days} days · today ${fmtDate(s.today, true)}`;
  const n = s.reorder.items_to_order;
  $('#tabReorderCount').textContent = n ? String(n) : '';
  $('#footInfo').textContent = `runs fully offline, Python standard library only · analysis built in ${s.build_seconds}s`;
}

async function showTab(name, force) {
  state.tab = name;
  $$('.tabs button').forEach(b => { const on = b.dataset.tab === name; b.classList.toggle('active', on); b.setAttribute('aria-selected', String(on)); });
  $$('.view').forEach(v => v.classList.toggle('active', v.id === 'view-' + name));
  try { localStorage.setItem('ss-tab', name); } catch (e) { /* storage unavailable */ }
  if (name === 'overview') renderOverview();
  if (name === 'reorder') renderReorder();
  if (name === 'sku') { if (!state.skuDetail || force) await loadSku(state.sku); else renderSku(); renderLbTable(); }
  if (name === 'abc') await ensureAbc();
  if (name === 'basket') await ensureBasket();
  if (name === 'sim') await ensureSim();
  if (name === 'data') renderData();
}

/* ------------------------------------------------------------------ overview */
function renderOverview() {
  const s = state.summary;
  if (!s) return;
  const h = s.holdout, sim = s.simulation, f = (s.festivals || [])[0];
  const tiles = [
    { label: 'Revenue, last 30 days', value: fmtINR(s.revenue_30d), note: `${chg(s.revenue_change_pct, false)} vs previous 30 days` },
    { label: 'Forecast, next 28 days', value: fmtINR(s.forecast_28d), note: 'best model per SKU, summed' },
    { label: 'Reorder today', value: `${s.reorder.items_to_order} SKUs`, note: `${s.reorder.urgent} urgent · ${fmtINR(s.reorder.order_value)} order value`, accent: true },
    { label: 'Forecast error (unseen 14 days)', value: `${fmtNum(h.wape, 1)}% WAPE`, note: `vs ${fmtNum(h.wape_naive, 1)}% seasonal naive · <span class="delta-good">${fmtNum(h.error_reduction_pct, 0)}% less error</span>` },
    sim ? { label: 'Stock-out days, 90-day replay', value: `${chg(sim.change_pct.stockout_days)}`, note: `${fmtNum(sim.gut.stockout_days)} → ${fmtNum(sim.stocksense.stockout_days)} SKU-days vs gut feel` }
      : { label: 'Stock-out days, last 90', value: fmtNum(s.stockout_days_90d), note: 'flagged in history' },
    f ? { label: `${f.name} in ${f.days_away} days`, value: '+' + fmtINR(f.extra_revenue), note: `expected extra sales · ${fmtDate(f.date)} (approx.)` }
      : { label: 'Next festival', value: '—', note: 'none in the next 45 days' },
  ];
  $('#kpis').innerHTML = tiles.map(t => `<div class="kpi${t.accent ? ' accent' : ''}"><div class="label">${esc(t.label)}</div>
    <div class="value">${t.value}</div><div class="note">${t.note}</div></div>`).join('');
  renderTrend();
  renderReorderTop();
  renderFestival();
  renderLbSummary();
  renderSimHead();
}

function renderTrend() {
  const tr = state.trend;
  if (!tr) return;
  const hist = tr.history.slice(-91), fc = tr.forecast;
  const x = hist.map(r => r.date).concat(fc.map(r => r.date));
  const nH = hist.length;
  const actual = hist.map(r => r.revenue).concat(fc.map(() => null));
  const fcast = hist.map(() => null).concat(fc.map(r => r.revenue));
  const lo = hist.map(() => null).concat(fc.map(r => r.lo));
  const hi = hist.map(() => null).concat(fc.map(r => r.hi));
  const cA = cssVar('--s-actual'), cF = cssVar('--brand');
  const vlines = (tr.festivals || []).map(f => ({ i: x.indexOf(f.date), label: f.name, color: cssVar('--brand-strong') })).filter(v => v.i >= 0);
  lineChart($('#trendChart'), {
    x, label: 'Store revenue history and forecast',
    series: [
      { name: 'Actual sales', values: actual, color: cA, width: 1.6, fmt: fmtINRFull },
      { name: 'Forecast', values: fcast, color: cF, width: 2.2, band: { lo, hi }, endDot: true, fmt: fmtINRFull },
    ],
    split: nH, vlines, yFormat: v => '₹' + fmtCompact(v), xFormat: d => fmtDate(d), yMin: 0,
    tipHead: i => fmtDate(x[i], true) + (i >= nH ? ' · forecast' : '') + ((i < nH ? hist[i].festival : fc[i - nH].festival) ? ' · ' + (i < nH ? hist[i].festival : fc[i - nH].festival) + ' week' : ''),
    extraTip: i => (i < nH && hist[i].stockouts ? [{ name: 'SKUs out of stock', value: String(hist[i].stockouts) }] : []),
  });
  legend($('#trendLegend'), [
    { name: 'Actual', color: cA }, { name: 'Forecast', color: cF }, { name: '80% band', color: cF, type: 'band' }]);
}

function renderReorderTop() {
  const rows = state.plan.rows.filter(r => r.order_qty > 0).slice(0, 7);
  $('#reorderTopSub').textContent = `${state.plan.totals.items_to_order} SKUs at ${fmtPct(state.service)} service · highest rupee risk first`;
  const ul = $('#reorderTop');
  if (!rows.length) { ul.innerHTML = '<li class="empty-note">Nothing to order today.</li>'; return; }
  ul.innerHTML = rows.map(r => `<li data-sku="${esc(r.sku)}" tabindex="0">
    ${statusChip(r.status)}
    <div style="min-width:0"><div class="nm">${esc(r.name)}</div>
      <div class="meta">on hand ${fmtNum(r.on_hand)} · ROP ${fmtNum(r.rop)} · run-out risk ${fmtPct(r.risk_skip, 0)}</div></div>
    <div class="qty">${fmtNum(r.order_qty)} units<small>${fmtINR(r.order_value)}</small></div></li>`).join('');
  $$('#reorderTop li[data-sku]').forEach(li => {
    const go = () => openSku(li.dataset.sku);
    li.addEventListener('click', go);
    li.addEventListener('keydown', e => { if (e.key === 'Enter') go(); });
  });
}

function renderFestival() {
  const body = $('#festBody');
  const f = (state.fest || [])[0];
  if (!f) { body.innerHTML = '<p class="empty-note">No festival in the next 45 days. StockSense keeps watching the calendar.</p>'; return; }
  $('#festSub').textContent = `Uplift learned from last year's ${f.name} sales (dates approx.)`;
  body.innerHTML = `<div class="fest-head"><span class="big">+${fmtINR(f.extra_revenue)}</span>
      <span class="hint">expected extra sales · ${esc(f.name)} ${fmtDate(f.date)} · in ${f.days_away} days</span></div>
    ${f.skus.slice(0, 6).map(r => `<div class="fest-row"><span class="nm">${esc(r.name)}</span>
      <span class="up">+${fmtNum(r.uplift_pct)}%</span><span class="hint">order by ${fmtDate(r.order_by)}</span></div>`).join('')}`;
}

function renderLbSummary() {
  const lb = state.lb;
  const total = state.skus.length;
  const rows = Object.entries(lb.models).map(([k, m]) => ({
    label: MODEL_SHORT[k], value: m.wins, color: cssVar(MODEL_VAR[k]),
    text: `${m.wins}`, title: `${m.name}: wins ${m.wins} of ${total} SKUs, mean sMAPE ${m.mean_smape}%`,
  }));
  const el = $('#lbSummary');
  hbars(el, rows, { max: total });
  const h = lb.holdout;
  el.insertAdjacentHTML('beforeend', `<p class="explain">Picked on folds 1–3, scored on the unseen last 14 days:
    <b>${fmtNum(h.wape, 1)}%</b> WAPE vs <b>${fmtNum(h.wape_naive, 1)}%</b> for seasonal naive
    (sMAPE ${fmtNum(h.smape, 1)}% vs ${fmtNum(h.smape_naive, 1)}%).</p>`);
}

function renderSimHead() {
  const sim = state.summary.simulation, el = $('#simHead');
  if (!sim) { el.innerHTML = '<p class="empty-note">Need ~6 months of history to replay 90 days.</p>'; return; }
  const g = sim.gut, k = sim.stocksense;
  const cG = cssVar('--s-slate'), cK = cssVar('--brand');
  const items = [
    ['Stock-out SKU-days', g.stockout_days, k.stockout_days, fmtNum, 'stockout_days'],
    ['Lost sales', g.lost_sales, k.lost_sales, fmtINR, 'lost_sales'],
    ['Expired units', g.expired_units, k.expired_units, fmtNum, 'expired_units'],
    ['Total cost', g.total_cost, k.total_cost, fmtINR, 'total_cost'],
  ];
  // each metric on its own scale: the two bars compare gut feel vs StockSense within a row
  el.innerHTML = '<div class="hbars">' + items.map(([l, a, b, f, key]) => {
    const mx = Math.max(a, b, 1e-9);
    return `<div class="hbar pair" title="${esc(`${l}: gut feel ${f(a)} → StockSense ${f(b)}`)}"><span class="lbl">${esc(l)}</span>
      <span class="track"><span class="fill" style="width:${Math.max(0.5, 100 * a / mx)}%;background:${cG}"></span>
      <span class="fill b2" style="width:${Math.max(0.5, 100 * b / mx)}%;background:${cK}"></span></span>
      <span class="val">${chg(sim.change_pct[key])}</span></div>`;
  }).join('') + '</div>';
  el.insertAdjacentHTML('beforeend', `<div class="legend" style="margin-top:10px"></div>
    <p class="explain">Gut feel: fixed weekly order. StockSense: daily forecast-driven reorder point, trained only on data before the window.
    Fill rate ${fmtPct(g.fill_rate)} → <b>${fmtPct(k.fill_rate)}</b>.</p>`);
  legend(el.querySelector('.legend'), [{ name: 'Gut feel', color: cG, type: 'box' }, { name: 'StockSense', color: cK, type: 'box' }]);
}

/* ------------------------------------------------------------------ reorder */
function renderReorder() {
  const p = state.plan, w = state.whatif;
  if (!p) return;
  $('#slServiceVal').textContent = fmtPct(state.service);
  $('#zVal').textContent = p.z.toFixed(3);
  $('#optVal').textContent = w ? fmtPct(w.optimum, 1) : '–';
  const t = p.totals;
  $('#reorderTotals').innerHTML = [
    { label: 'SKUs to order today', value: fmtNum(t.items_to_order), note: `${t.urgent} urgent (will run out before delivery)`, accent: true },
    { label: 'Order value (at cost)', value: fmtINR(t.order_value), note: 'case-pack rounded' },
    { label: 'Sales protected by ordering', value: fmtINR(t.sales_saved), note: `of ${fmtINR(t.sales_at_risk)} at risk if skipped` },
    { label: 'Cash tied up in overstock', value: fmtINR(t.excess_value), note: `${t.overstock} SKUs far above need` },
  ].map(k => `<div class="kpi${k.accent ? ' accent' : ''}"><div class="label">${esc(k.label)}</div><div class="value">${k.value}</div><div class="note">${esc(k.note)}</div></div>`).join('');
  $('#reorderSub').textContent = `${fmtDate(p.date, true)} · service level ${fmtPct(p.service)} · click a row for the reasoning`;
  renderWhatif();
  renderReorderTable();
}

function renderWhatif() {
  const w = state.whatif;
  if (!w) return;
  const pts = w.curve;
  const x = pts.map(p => p.service);
  const cH = cssVar('--s-blue'), cS = cssVar('--brand'), cT = cssVar('--s-actual');
  const at = pts.findIndex(p => Math.abs(p.service - state.service) < 1e-6);
  const opt = pts.findIndex(p => Math.abs(p.service - w.optimum) < 1e-6);
  lineChart($('#whatifChart'), {
    x, xv: x, label: 'Service level trade-off',
    series: [
      { name: 'Safety-stock holding', values: pts.map(p => p.holding_cost), color: cH, fmt: fmtINRFull },
      { name: 'Expected lost margin', values: pts.map(p => p.stockout_cost), color: cS, fmt: fmtINRFull },
      { name: 'Total', values: pts.map(p => p.total_cost), color: cT, width: 2.4, fmt: fmtINRFull },
    ],
    // the two markers are often one step apart: label the left one leftwards so neither text sits on the other's line
    vlines: [{ i: at, label: 'you ' + fmtPct(state.service), y: 12, anchor: opt > at ? 'end' : 'start' }, ...(opt !== at ? [{ i: opt, label: 'optimum', y: 28, color: cssVar('--good-text'), anchor: opt < at ? 'end' : 'start' }] : [])],
    dots: opt >= 0 ? [{ i: opt, v: pts[opt].total_cost, color: cssVar('--good') }] : [],
    yFormat: v => '₹' + fmtCompact(v), xFormat: v => (v * 100).toFixed(v >= 0.99 ? 1 : 0) + '%', yMin: 0,
    xTickIdx: x.map((v, i) => i).filter(i => [0.8, 0.85, 0.9, 0.95, 0.999].some(s => Math.abs(x[i] - s) < 1e-6)),
    tipHead: i => 'Service level ' + fmtPct(x[i]),
    extraTip: i => [{ name: 'Expected fill rate', value: fmtPct(pts[i].fill_rate, 2) }, { name: 'Safety stock value', value: fmtINRFull(pts[i].ss_value) }],
  });
  legend($('#whatifLegend'), [{ name: 'Safety-stock holding / yr', color: cH }, { name: 'Expected lost margin / yr', color: cS }, { name: 'Total', color: cT }]);
  const a = w.at;
  $('#whatifExplain').innerHTML = `At <b>${fmtPct(state.service)}</b>: safety stock worth ${fmtINR(a.ss_value)} costs ${fmtINR(a.holding_cost)}/yr to hold;
    expected lost margin ${fmtINR(a.stockout_cost)}/yr; expected fill rate ${fmtPct(a.fill_rate, 2)}.
    The cost-optimal level is about <b>${fmtPct(w.optimum)}</b> — above it, every extra point of service costs more than the sales it saves.`;
  const show = pts.filter(p => [0.9, 0.95, 0.99, w.optimum, state.service].some(v => Math.abs(p.service - v) < 1e-6));
  $('#whatifTable').innerHTML = '<thead><tr><th>Service</th><th class="num">Holding/yr</th><th class="num">Lost margin/yr</th><th class="num">Fill rate</th></tr></thead><tbody>' +
    show.map(p => `<tr${Math.abs(p.service - state.service) < 1e-6 ? ' style="font-weight:650"' : ''}><td style="white-space:nowrap">${fmtPct(p.service)}${Math.abs(p.service - w.optimum) < 1e-6 ? ' <span class="chip">optimum</span>' : ''}${Math.abs(p.service - state.service) < 1e-6 ? ' <span class="chip brand">you</span>' : ''}</td>
      <td class="num">${fmtINR(p.holding_cost)}</td><td class="num">${fmtINR(p.stockout_cost)}</td><td class="num">${fmtPct(p.fill_rate, 2)}</td></tr>`).join('') + '</tbody>';
}

function filteredPlan() {
  const q = state.search.trim().toLowerCase();
  return state.plan.rows.filter(r => {
    if (state.filter === 'need' && !r.order_qty) return false;
    if (state.filter === 'urgent' && r.status !== 'urgent') return false;
    if (state.filter === 'overstock' && r.status !== 'overstock') return false;
    if (q && !(r.name.toLowerCase().includes(q) || r.sku.toLowerCase().includes(q))) return false;
    return true;
  });
}

function renderReorderTable() {
  const rows = filteredPlan();
  const tbl = $('#reorderTable');
  const head = `<thead><tr><th>Status</th><th>Item</th><th class="num">On hand</th><th class="num">Forecast/day</th>
    <th class="num">Lead</th><th class="num">Reorder pt</th><th class="num">Order</th><th class="num">Value</th>
    <th class="num" title="Probability of running out before the next delivery: if you skip today → if you order today">Run-out risk</th>
    <th class="num" title="Expected lost sales if today's order is skipped">Sales at risk</th></tr></thead>`;
  if (!rows.length) { tbl.innerHTML = head + '<tbody><tr><td colspan="10" class="empty-note">No SKUs match this filter.</td></tr></tbody>'; return; }
  tbl.innerHTML = head + '<tbody>' + rows.map(r => {
    const open = state.openRows.has(r.sku);
    return `<tr class="clickable" data-sku="${esc(r.sku)}">
      <td>${statusChip(r.status)}</td>
      <td><div class="nm">${esc(r.name)}</div><div class="sku">${esc(r.sku)} · ${esc(r['class'])} · ${esc(MODEL_SHORT[r.model] || r.model)}</div></td>
      <td class="num"><input class="stock${r.assumed_stock ? ' assumed' : ''}" type="number" min="0" step="1" value="${r.on_hand}" aria-label="Stock on hand for ${esc(r.name)}" data-sku="${esc(r.sku)}" title="${r.assumed_stock ? 'Assumed - type the real count' : 'Edit to recompute'}"></td>
      <td class="num">${fmtNum(r.d_avg, 1)}</td>
      <td class="num">${r.lead_time} d</td>
      <td class="num">${fmtNum(r.rop)}</td>
      <td class="num"><b>${r.order_qty ? fmtNum(r.order_qty) : '–'}</b>${r.order_qty ? `<div class="sku">case ${r.pack}</div>` : ''}</td>
      <td class="num">${r.order_qty ? fmtINR(r.order_value) : '–'}</td>
      <td class="num"><span class="risk">${fmtPct(r.risk_skip, 0)}${r.order_qty ? `<span class="arrow">→</span>${fmtPct(r.risk_order, 0)}` : ''}</span></td>
      <td class="num">${r.sales_at_risk >= 1 ? fmtINR(r.sales_at_risk) : '–'}</td></tr>
      <tr class="detail" ${open ? '' : 'hidden'}><td colspan="10">${esc(r.reason)}
        <div class="chips" style="margin-top:6px"><span class="chip">SS ${fmtNum(r.ss, 1)}</span><span class="chip">σ/day ${fmtNum(r.sigma_e, 2)}</span>
        <span class="chip">EOQ ${fmtNum(r.eoq)}</span><span class="chip">Q* ${fmtNum(r.q_star)} (${esc(r.q_binding)})</span>
        <span class="chip">cover ${r.days_cover == null ? '–' : fmtNum(r.days_cover, 1) + ' d'}</span>
        ${r.perishable ? `<span class="chip">perishable · ${r.shelf_life} d shelf life</span>` : ''}
        <button class="link" data-open="${esc(r.sku)}" type="button">Open in SKU explorer →</button></div></td></tr>`;
  }).join('') + '</tbody>';
  $$('#reorderTable tr.clickable').forEach(tr => tr.addEventListener('click', e => {
    if (e.target.closest('input')) return;
    const sku = tr.dataset.sku, det = tr.nextElementSibling;
    if (state.openRows.has(sku)) { state.openRows.delete(sku); det.hidden = true; } else { state.openRows.add(sku); det.hidden = false; }
  }));
  $$('#reorderTable [data-open]').forEach(b => b.addEventListener('click', () => openSku(b.dataset.open)));
  $$('#reorderTable input.stock').forEach(inp => inp.addEventListener('change', () => updateStock(inp.dataset.sku, inp.value)));
}

async function updateStock(sku, value) {
  const v = Number(value);
  if (!isFinite(v) || v < 0) { toast('Stock must be a number ≥ 0'); return; }
  try {
    await api('/api/stock', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sku, on_hand: Math.round(v), on_order: 0 }) });
    state.openRows.add(sku);
    await refreshService();
    const s = state.summary; $('#tabReorderCount').textContent = s.reorder.items_to_order ? String(s.reorder.items_to_order) : '';
    toast('Stock updated - plan recomputed');
  } catch (e) { toast(e.message, 4000); }
}

function exportOrders() {
  const rows = state.plan.rows.filter(r => r.order_qty > 0);
  const lines = [['sku', 'name', 'status', 'order_qty', 'case_pack', 'order_value', 'on_hand', 'reorder_point']]
    .concat(rows.map(r => [r.sku, r.name, r.status, r.order_qty, r.pack, r.order_value, r.on_hand, r.rop]));
  const csv = lines.map(l => l.map(v => /[",\n]/.test(String(v)) ? '"' + String(v).replace(/"/g, '""') + '"' : v).join(',')).join('\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
  a.download = `stocksense_orders_${state.plan.date}.csv`;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

/* ------------------------------------------------------------------ SKU explorer */
function fillSkuSelect() {
  const sel = $('#skuSelect');
  const cats = {};
  state.skus.forEach(s => { (cats[s.category] = cats[s.category] || []).push(s); });
  sel.innerHTML = '';
  Object.keys(cats).forEach(c => {
    const og = document.createElement('optgroup'); og.label = c;
    cats[c].forEach(s => { const o = document.createElement('option'); o.value = s.sku; o.textContent = `${s.name} (${s.sku})`; og.appendChild(o); });
    sel.appendChild(og);
  });
  sel.value = state.sku;
  const simSel = $('#simSku');
  simSel.innerHTML = '';
  state.skus.forEach(s => { const o = document.createElement('option'); o.value = s.sku; o.textContent = s.name; simSel.appendChild(o); });
}

function openSku(sku) { state.sku = sku; $('#skuSelect').value = sku; state.skuDetail = null; showTab('sku'); window.scrollTo({ top: 0, behavior: 'smooth' }); }

async function loadSku(sku) {
  try {
    state.skuDetail = await api('/api/sku/' + encodeURIComponent(sku) + '?' + svc());
    state.sku = sku; $('#skuSelect').value = sku;
    renderSku();
  } catch (e) { toast(e.message, 4000); }
}

function renderSku() {
  const d = state.skuDetail;
  if (!d) return;
  const it = d.item, p = d.plan, cls = d['class'];
  $('#skuTitle').textContent = it.name;
  $('#skuSub').textContent = `${it.sku} · ${it.category} · ₹${fmtNum(it.price, 2)} MRP · ₹${fmtNum(it.cost, 2)} cost · shelf life ${it.shelf_life} d · lead time ${it.lead_time} d`;
  const up = d.uplift, bigUp = Object.entries(up).filter(([, v]) => v >= 0.5).sort((a, b) => b[1] - a[1])[0];
  $('#skuChips').innerHTML = `<span class="chip brand">${esc(cls['class'])} · ${esc(cls.strategy)}</span>
    <span class="chip">Model: ${esc(d.model_names[d.forecast.chosen])}</span>${statusChip(p.status)}
    ${bigUp ? `<span class="chip">${bigUp[0] === 'diwali' ? 'Diwali' : bigUp[0] === 'pongal' ? 'Pongal' : 'Festival'} +${Math.round(bigUp[1] * 100)}%</span>` : ''}`;
  renderSkuChart();
  $('#skuWhy').innerHTML = `${esc(d.why_model)} Red dots mark stock-out days: sales were censored, so StockSense imputed the demand before fitting.`;
  // leaderboard
  const maxS = Math.max(...d.leaderboard.map(r => r.smape || 0), 1);
  $('#skuLeaderboard').innerHTML = d.leaderboard.map(r => `<div class="lb-row" title="MAPE ${r.mape == null ? '–' : r.mape + '%'} · MAE ${r.mae} · RMSE ${r.rmse} · bias ${r.bias}">
      <span class="nmw"><i class="dotkey" style="background:${cssVar(MODEL_VAR[r.model])}"></i><span>${esc(r.name)}${r.chosen ? ' <span class="best">✓</span>' : ''}</span></span>
      <span class="bar-cell"><span class="b" style="width:${100 * (r.smape || 0) / maxS}%;background:${cssVar(MODEL_VAR[r.model])}"></span></span>
      <span class="val${r.chosen ? ' best' : ''}">${fmtNum(r.smape, 1)}%</span></div>`).join('') +
    `<p class="explain">sMAPE (lower is better) over ${d.folds.length} folds; MAPE of the winner ${d.leaderboard.find(r => r.chosen).mape == null ? '–' : fmtNum(d.leaderboard.find(r => r.chosen).mape, 1) + '%'}. Hover a row for MAE, RMSE and bias.</p>`;
  const n0 = state.summary.history_start, n1 = state.summary.history_end;
  const span = (Date.parse(n1) - Date.parse(n0)) / 864e5 + 1;
  const pos = iso => 100 * ((Date.parse(iso) - Date.parse(n0)) / 864e5) / span;
  $('#foldSub').textContent = 'Rolling-origin folds: train on the past, test on the next 14 days';
  $('#foldViz').innerHTML = d.folds.map((f, i) => `<div class="fold"><span>Fold ${i + 1}</span><span class="tl" title="train to ${fmtDate(f.train_end, true)}, test ${fmtDate(f.test_start)}–${fmtDate(f.test_end)}">
      <span class="tr" style="width:${pos(f.test_start)}%"></span><span class="te" style="left:${pos(f.test_start)}%;width:${Math.max(1.2, pos(f.test_end) - pos(f.test_start) + 100 / span)}%"></span></span></div>`).join('') +
    `<div class="legend" style="margin-top:6px"><span class="key"><i class="swatch box" style="background:${cssVar('--s-slate')};opacity:.5"></i>training data</span><span class="key"><i class="swatch box" style="background:${cssVar('--brand')}"></i>test window</span></div>`;
  renderPolicy(); renderDrivers(); renderSkuBasket(); renderSkuSim();
}

function renderSkuChart() {
  const d = state.skuDetail;
  const H = d.history, F = d.forecast;
  const nH = H.dates.length;
  const x = H.dates.concat(F.dates);
  const pad = arr => H.dates.map(() => null).concat(arr);
  const cA = cssVar('--s-actual');
  const series = [{ name: 'Actual sales', values: H.qty.concat(F.dates.map(() => null)), color: cA, width: 1.5, fmt: v => fmtNum(v, 1) }];
  Object.keys(F.models).forEach(mk => {
    if (state.hidden.has(mk) && mk !== F.chosen) return;
    const chosen = mk === F.chosen;
    series.push({
      name: d.model_names[mk] + (chosen ? ' (chosen)' : ''), values: pad(F.models[mk]), color: cssVar(MODEL_VAR[mk]),
      width: chosen ? 2.4 : 1.5, dash: chosen ? null : '5 4', band: chosen ? { lo: pad(F.lo), hi: pad(F.hi) } : null, fmt: v => fmtNum(v, 1),
    });
  });
  const dots = [];
  H.stockout.forEach((f, i) => { if (f) dots.push({ i, v: H.clean[i], color: cssVar('--critical') }); });
  const fests = (state.trend.festivals || []).map(f => ({ i: x.indexOf(f.date), label: f.name, color: cssVar('--brand-strong') })).filter(v => v.i >= 0);
  lineChart($('#skuChart'), {
    x, series, dots, split: nH, vlines: fests, yMin: 0, xFormat: v => fmtDate(v), yFormat: v => fmtCompact(v),
    label: 'SKU sales history and forecasts',
    tipHead: i => fmtDate(x[i], true) + (i >= nH ? ' · forecast' : ''),
    extraTip: i => {
      const out = [];
      if (i < nH && H.stockout[i]) out.push({ name: 'Stock-out: imputed demand', value: fmtNum(H.clean[i], 1), color: cssVar('--critical') });
      if (i < nH && H.promo[i]) out.push({ name: 'Promotion day', value: 'yes' });
      return out;
    },
  });
  legend($('#skuLegend'), Object.keys(F.models).map(mk => ({
    name: MODEL_SHORT[mk] + (mk === F.chosen ? ' ✓' : ''), color: cssVar(MODEL_VAR[mk]), off: state.hidden.has(mk) && mk !== F.chosen,
    onClick: mk === F.chosen ? null : () => { if (state.hidden.has(mk)) state.hidden.delete(mk); else state.hidden.add(mk); renderSkuChart(); },
  })).concat([{ name: 'Actual', color: cA }, { name: 'Stock-out', color: cssVar('--critical'), type: 'dot' }]));
}

function renderPolicy() {
  const d = state.skuDetail, p = d.policy, r = d.plan, it = d.item;
  const lines = [
    [`Forecast demand, next ${p.protection_days} days`, fmtNum(p.prot_demand, 1), `lead time ${p.lead_time} d + 1 review day`],
    ['Forecast error σ per day', fmtNum(p.sigma_e, 2), 'RMSE of the chosen model in backtests'],
    [`σ over ${p.protection_days} days`, fmtNum(p.sigma_p, 2), `√(${p.protection_days}·σ² + d²·σL²), σL = ${it.lead_sd} d`],
    [`Safety stock (z = ${fmtNum(p.z, 3)})`, fmtNum(p.ss, 1), `inv-normal(${fmtPct(p.service)}) × σ`],
    ['Reorder point', fmtNum(p.rop, 1), 'demand over P days + safety stock'],
    ['EOQ √(2DS/H)', fmtNum(p.eoq, 0), `D ${fmtNum(p.annual_demand)}/yr · S ₹${fmtNum(p.order_cost)} · H ₹${fmtNum(p.holding_cost_unit, 2)}/unit-yr`],
    ['Order quantity Q*', fmtNum(p.q_star), `${p.q_binding}${p.perishable ? ` · sell within ${p.usable_days} d` : ''} · case ${it.pack}`],
    ['Stock on hand → order today', `${fmtNum(r.on_hand)} → ${r.order_qty ? fmtNum(r.order_qty) : 'none'}`, r.order_qty ? fmtINRFull(r.order_value) + ' at cost' : 'above reorder point'],
    ['Run-out risk: skip → order', `${fmtPct(r.risk_skip, 0)}${r.order_qty ? ' → ' + fmtPct(r.risk_order, 0) : ''}`, `expected lost sales ${fmtINR(r.sales_at_risk)} if skipped`],
    ['Cost-optimal service level', fmtPct(d.optimal_service, 1), '1 − HQ / (HQ + D·margin)'],
  ];
  $('#skuPolicy').innerHTML = `<div class="formula">${lines.map(([a, b, c]) => `<div class="ln"><span>${esc(a)}<br><span class="eq">${esc(c)}</span></span><b>${esc(b)}</b></div>`).join('')}</div>
    <div class="reason">${esc(r.reason)}</div>`;
}

function renderDrivers() {
  const d = state.skuDetail;
  const up = d.uplift;
  const names = { diwali: 'Diwali', pongal: 'Pongal', other: 'Other festivals' };
  const maxU = Math.max(0.5, ...Object.values(up).map(Math.abs));
  const coef = d.regression;
  const base = Math.max(1e-6, Math.abs(coef[0].coef));
  const dow = coef.filter(c => / vs Mon$/.test(c.feature));
  const maxD = Math.max(0.05, ...dow.map(c => Math.abs(c.coef / base)));
  const pos = cssVar('--brand'), neg = cssVar('--s-blue');
  const promo = coef.find(c => c.feature === 'Promotion'), trend = coef.find(c => c.feature === 'Trend per year');
  $('#skuDrivers').innerHTML = `<div class="hint" style="margin-bottom:6px">Peak festival uplift (learned, vs a normal day)</div>
    <div class="hbars">${Object.keys(up).map(k => `<div class="hbar" title="${d.uplift_detail && d.uplift_detail[k].se != null ? `raw estimate ${Math.round(d.uplift_detail[k].raw * 100)}% ± ${Math.round(d.uplift_detail[k].se * 100)}% (1 s.e.), shrunk toward 0 by its noise` : 'not seen in history'}"><span class="lbl">${names[k]}</span>
      <span class="track"><span class="fill" style="width:${Math.max(0.5, 100 * Math.max(0, up[k]) / maxU)}%;background:${pos}"></span></span>
      <span class="val">${up[k] >= 0 ? '+' : '−'}${Math.round(Math.abs(up[k]) * 100)}%</span></div>`).join('')}</div>
    <div class="hint" style="margin-top:4px">Each festival is seen once, so noisy estimates are shrunk toward 0 (hover for raw ± s.e.).</div>
    <div class="hint" style="margin:12px 0 6px">Day-of-week effect vs Monday (regression, % of base level)</div>
    <div class="hbars">${dow.map(c => {
      const v = c.coef / base, w = 50 * Math.abs(v) / maxD;
      return `<div class="hbar"><span class="lbl">${esc(c.feature.slice(0, 3))}</span>
        <span class="track"><span style="position:absolute;left:50%;top:-2px;bottom:-2px;width:1px;background:${cssVar('--axis')}"></span>
        <span class="fill" style="left:${v >= 0 ? 50 : 50 - w}%;width:${Math.max(0.5, w)}%;background:${v >= 0 ? pos : neg};border-radius:${v >= 0 ? '0 4px 4px 0' : '4px 0 0 4px'}"></span></span>
        <span class="val">${v >= 0 ? '+' : '−'}${Math.abs(v * 100).toFixed(0)}%</span></div>`;
    }).join('')}</div>
    <p class="explain">Base level ${fmtNum(coef[0].coef, 1)}/day · trend ${trend.coef >= 0 ? '+' : ''}${fmtNum(trend.coef, 2)}/day per year${Math.abs(promo.coef) > 0.01 ? ` · promotion ${promo.coef >= 0 ? '+' : ''}${fmtNum(promo.coef, 1)}/day` : ''}.</p>`;
}

function renderSkuBasket() {
  const d = state.skuDetail, el = $('#skuBasket');
  if (!d.basket.length) { el.innerHTML = '<p class="empty-note">No strong rule starts from this SKU at the current thresholds.</p>'; return; }
  el.innerHTML = d.basket.map(r => `<div class="sugg"><span class="ic">⇄</span><div>
    <div class="act">${esc(r.consequent_names.join(' + '))}</div>
    <div class="why">${fmtPct(r.confidence, 0)} of bills with this item also have it · lift ${fmtNum(r.lift, 1)}× · ${r.count} bills</div></div></div>`).join('');
}

function renderSkuSim() {
  const d = state.skuDetail, s = d.simulation;
  if (!s) { $('#skuSimChart').innerHTML = '<p class="empty-note">Simulation needs more history.</p>'; return; }
  $('#skuSimSub').textContent = `Gut feel: fixed ${s.gut_order} units ${s.gut_cycle} → ${fmtNum(s.gut.stockout_days)} stock-out days, ${fmtNum(s.gut.expired_units)} expired · StockSense (${MODEL_SHORT[s.model]}): ${fmtNum(s.stocksense.stockout_days)} stock-out days, ${fmtNum(s.stocksense.expired_units)} expired`;
  trajChart($('#skuSimChart'), s.trajectory, s.dates, $('#skuSimLegend'));
}

function trajChart(el, tr, dates, legendEl) {
  const cG = cssVar('--s-slate'), cK = cssVar('--brand'), cD = cssVar('--s-actual');
  const dots = [];
  tr.gut.lost.forEach((v, i) => { if (v > 0) dots.push({ i, v: 0, color: cG, r: 3.5 }); });
  tr.stocksense.lost.forEach((v, i) => { if (v > 0) dots.push({ i, v: 0, color: cK, r: 3.5 }); });
  lineChart(el, {
    x: dates, label: 'Stock on hand under both policies',
    bars: [{ name: 'Demand', values: tr.gut.demand, color: cD, opacity: 0.18, fmt: v => fmtNum(v) }],
    series: [
      { name: 'Gut feel stock', values: tr.gut.on_hand, color: cG, width: 1.8, fmt: v => fmtNum(v) },
      { name: 'StockSense stock', values: tr.stocksense.on_hand, color: cK, width: 2.2, fmt: v => fmtNum(v) },
    ],
    dots, yMin: 0, xFormat: v => fmtDate(v), tipHead: i => fmtDate(dates[i], true),
    extraTip: i => {
      const out = [];
      if (tr.gut.lost[i]) out.push({ name: 'Gut feel lost sales', value: fmtNum(tr.gut.lost[i]) + ' units', color: cG });
      if (tr.stocksense.lost[i]) out.push({ name: 'StockSense lost sales', value: fmtNum(tr.stocksense.lost[i]) + ' units', color: cK });
      if (tr.gut.expired[i]) out.push({ name: 'Gut feel expired', value: fmtNum(tr.gut.expired[i]) });
      if (tr.stocksense.expired[i]) out.push({ name: 'StockSense expired', value: fmtNum(tr.stocksense.expired[i]) });
      if (tr.gut.order[i]) out.push({ name: 'Gut feel ordered', value: fmtNum(tr.gut.order[i]) });
      if (tr.stocksense.order[i]) out.push({ name: 'StockSense ordered', value: fmtNum(tr.stocksense.order[i]) });
      return out;
    },
  });
  legend(legendEl, [{ name: 'Gut feel', color: cG }, { name: 'StockSense', color: cK }, { name: 'Daily demand', color: cD, type: 'box' },
    { name: 'Stock-out day (dot on axis)', color: cssVar('--muted'), type: 'dot' }]);
}

function renderLbTable() {
  const lb = state.lb;
  if (!lb) return;
  $('#lbMethod').textContent = lb.method;
  const models = Object.keys(lb.models);
  $('#lbTable').innerHTML = `<thead><tr><th>SKU</th>${models.map(m => `<th class="num">${esc(MODEL_SHORT[m])}</th>`).join('')}<th class="num">Gain vs naive</th></tr></thead><tbody>` +
    lb.per_sku.map(r => `<tr class="clickable" data-sku="${esc(r.sku)}"><td><div class="nm">${esc(r.name)}</div><div class="sku">${esc(r.sku)}</div></td>
      ${models.map(m => `<td class="num${m === r.chosen ? ' best' : ''}">${fmtNum(r.smape[m], 1)}%${m === r.chosen ? ' ✓' : ''}</td>`).join('')}
      <td class="num">${r.gain_vs_naive > 0 ? '−' + fmtNum(r.gain_vs_naive, 1) + ' pts' : '–'}</td></tr>`).join('') +
    `<tr><td><b>Mean sMAPE</b> · wins</td>${models.map(m => `<td class="num"><b>${fmtNum(lb.models[m].mean_smape, 1)}%</b> · ${lb.models[m].wins}</td>`).join('')}<td></td></tr></tbody>`;
  $$('#lbTable tr[data-sku]').forEach(tr => tr.addEventListener('click', () => openSku(tr.dataset.sku)));
}

/* ------------------------------------------------------------------ ABC-XYZ */
async function ensureAbc() {
  if (!state.abc) { try { state.abc = await api('/api/abcxyz'); } catch (e) { toast(e.message); return; } }
  renderAbc();
}

function renderAbc() {
  const a = state.abc;
  const cols = { X: 'X · steady', Y: 'Y · variable', Z: 'Z · erratic' };
  const maxShare = Math.max(...a.cells.map(c => c.revenue_share), 1e-9);
  let html = '<div></div>' + Object.values(cols).map(c => `<div class="hdr">${c}</div>`).join('');
  ['A', 'B', 'C'].forEach(r => {
    html += `<div class="rowhdr">${r}</div>`;
    a.cells.filter(c => c.abc === r).forEach(c => {
      const lvl = c.count ? Math.min(5, 1 + Math.floor(4 * Math.sqrt(c.revenue_share / maxShare) + 0.0001)) : 0;
      const bg = lvl ? cssVar('--seq-' + lvl) : 'var(--surface-2)';
      const darkInk = lvl >= 5;
      html += `<div class="mcell${darkInk ? ' dark-ink' : ''}${c.count ? '' : ' empty'}${state.abcCell === c.cell ? ' sel' : ''}" data-cell="${c.cell}" style="background:${bg}" tabindex="0"
        title="${esc(c.advice)}">
        <div class="top"><span class="code">${c.cell}</span><span class="share">${c.count} SKU · ${fmtPct(c.revenue_share, 1)} rev</span></div>
        <div class="strat">${esc(c.strategy)}</div>
        <div class="skus">${c.skus.slice(0, 8).map(s => `<span data-sku="${esc(s.sku)}" title="${esc(s.name)} · CV ${s.cv}">${esc(shortName(s.name))}</span>`).join('')}${c.skus.length > 8 ? `<span>+${c.skus.length - 8}</span>` : ''}</div></div>`;
    });
  });
  const m = $('#abcMatrix');
  m.innerHTML = html;
  $$('.mcell', m).forEach(el => {
    const pick = () => { state.abcCell = el.dataset.cell; renderAbc(); };
    el.addEventListener('click', e => { const s = e.target.closest('[data-sku]'); if (s && s.dataset.sku) { openSku(s.dataset.sku); return; } pick(); });
    el.addEventListener('keydown', e => { if (e.key === 'Enter') pick(); });
  });
  // pareto
  const rows = a.pareto;
  const cB = cssVar('--brand');
  lineChart($('#paretoChart'), {
    x: rows.map((r, i) => i + 1), label: 'Pareto curve',
    series: [{ name: 'Cumulative revenue', values: rows.map(r => r.cum_share * 100), color: cB, fmt: v => v.toFixed(1) + '%' }],
    vlines: ['B', 'C'].map(c => ({ i: rows.findIndex(r => r.abc === c), label: c + ' from #' + (rows.findIndex(r => r.abc === c) + 1), y: 150 })).filter(v => v.i > 0),
    hlines: [{ y: a.thresholds.A * 100, label: '80%' }, { y: a.thresholds.B * 100, label: '95%' }],
    yMin: 0, yMax: 100, yFormat: v => v + '%', xFormat: v => '#' + v,
    tipHead: i => { const f = state.skus.find(s => s.sku === rows[i].sku); return `#${i + 1} ${f ? f.name : rows[i].sku}`; },
    extraTip: i => [{ name: 'Revenue (365 d)', value: fmtINRFull(rows[i].revenue) }, { name: 'Class', value: rows[i].abc + a.per_sku[rows[i].sku].xyz + ` (CV ${a.per_sku[rows[i].sku].cv})` }],
  });
  const cell = a.cells.find(c => c.cell === state.abcCell) || a.cells.slice().sort((p, q) => q.revenue_share - p.revenue_share)[0];
  $('#cellDetail').innerHTML = `<h3>${cell.cell} · ${esc(cell.strategy)}</h3><p style="margin:0 0 6px">${esc(cell.advice)} Suggested service level ≈ <b>${fmtPct(cell.service_level, 0)}</b>.</p>
    <div class="chips">${cell.skus.map(s => `<span class="chip" data-sku="${esc(s.sku)}" style="cursor:pointer">${esc(s.name)} · CV ${s.cv}</span>`).join('') || '<span class="hint">No SKUs in this cell.</span>'}</div>`;
  $$('#cellDetail [data-sku]').forEach(c => c.addEventListener('click', () => openSku(c.dataset.sku)));
}

/* ------------------------------------------------------------------ basket */
async function ensureBasket() {
  if (!state.basket) {
    try { state.basket = await api(`/api/basket?min_support=${state.support}&min_confidence=${state.conf}`); } catch (e) { toast(e.message); return; }
  }
  renderBasket();
}

function renderBasket() {
  const b = state.basket, names = b.names;
  $('#slSupportVal').textContent = fmtPct(state.support, 1);
  $('#slConfVal').textContent = fmtPct(state.conf, 0);
  $('#basketInfo').textContent = `${fmtNum(b.bills)} bills · ${b.rule_count} rules with lift ≥ ${b.min_lift} · ${b.note}`;
  const icon = { adjacent: '⇄', bundle: '＋', 'same-bay': '▦' };
  $('#suggestions').innerHTML = b.suggestions.length ? b.suggestions.map(s => `<div class="sugg"><span class="ic">${icon[s.kind] || '•'}</span>
    <div><div class="act">${esc(s.action)}</div><div class="why">${esc(s.why)}</div></div></div>`).join('') : '<p class="empty-note">No rule is strong enough at these thresholds.</p>';
  const q = state.ruleSearch.trim().toLowerCase();
  const nm = arr => arr.map(s => names[s] || s).join(' + ');
  const rules = b.rules.filter(r => !q || (nm(r.antecedent) + ' ' + nm(r.consequent)).toLowerCase().includes(q));
  const maxL = Math.max(1, ...b.rules.map(r => r.lift));
  $('#rulesTable').innerHTML = `<thead><tr><th>If a bill has…</th><th>…it likely also has</th><th class="num">Support</th><th class="num">Confidence</th><th>Lift</th><th class="num">Bills</th></tr></thead><tbody>` +
    (rules.length ? rules.map(r => `<tr><td>${esc(nm(r.antecedent))}</td><td><b>${esc(nm(r.consequent))}</b></td>
      <td class="num">${fmtPct(r.support, 1)}</td><td class="num">${fmtPct(r.confidence, 0)}</td>
      <td><span class="bar-cell"><span class="b" style="width:${70 * r.lift / maxL}%"></span>${fmtNum(r.lift, 2)}×</span></td><td class="num">${r.count}</td></tr>`).join('')
      : '<tr><td colspan="6" class="empty-note">No rules match.</td></tr>') + '</tbody>';
}

/* ------------------------------------------------------------------ simulation */
async function ensureSim() {
  if (!state.sim) { try { state.sim = await api('/api/simulation?' + svc()); } catch (e) { toast(e.message); return; } }
  renderSim();
}

function renderSim() {
  const s = state.sim;
  if (!s.ready) { $('#simLede').textContent = s.message; $('#simCompare').innerHTML = ''; return; }
  const g = s.gut, k = s.stocksense;
  $('#simLede').innerHTML = `We replayed the real demand of <b>${fmtDate(s.start, true)} – ${fmtDate(s.end, true)}</b> (${s.days} days, ${state.skus.length} SKUs) twice:
    once with the shopkeeper's <b>fixed weekly order</b>, once following StockSense every morning at <b>${fmtPct(s.service)}</b> service —
    with models chosen and tuned only on data from before the window.`;
  const tiles = [
    ['Stock-out SKU-days', g.stockout_days, k.stockout_days, fmtNum, s.change_pct.stockout_days, true],
    ['Lost sales', g.lost_sales, k.lost_sales, fmtINR, s.change_pct.lost_sales, true],
    ['Fill rate', g.fill_rate, k.fill_rate, v => fmtPct(v, 1), g.fill_rate ? 100 * (k.fill_rate - g.fill_rate) / g.fill_rate : null, false],
    ['Expired units', g.expired_units, k.expired_units, fmtNum, s.change_pct.expired_units, true],
    ['Avg stock value', g.avg_inventory_value, k.avg_inventory_value, fmtINR, s.change_pct.avg_inventory_value, true],
    ['Orders placed', g.orders, k.orders, fmtNum, s.change_pct.orders, true],
    ['Total cost', g.total_cost, k.total_cost, fmtINR, s.change_pct.total_cost, true],
  ];
  $('#simCompare').innerHTML = tiles.map(([l, a, b, f, pct, down]) => `<div class="cmp"><div class="label">${esc(l)}</div>
    <div class="pair"><span class="from">${f(a)} →</span><span class="to">${f(b)}</span></div><div class="chg">${chg(pct, down)} <span class="hint">vs gut feel</span></div></div>`).join('');
  const cG = cssVar('--s-slate'), cK = cssVar('--brand');
  const parts = [['Holding', 'holding_cost'], ['Ordering', 'ordering_cost'], ['Waste (expired)', 'waste_cost'], ['Lost margin', 'lost_margin'], ['Total', 'total_cost']];
  hbars($('#simCost'), parts.map(([l, key]) => ({ label: l, value: g[key], value2: k[key], color: cG, color2: cK,
    text: fmtINR(k[key]), title: `${l}: gut feel ${fmtINRFull(g[key])} → StockSense ${fmtINRFull(k[key])}` })));
  legend($('#simCostLegend'), [{ name: 'Gut feel', color: cG, type: 'box' }, { name: 'StockSense (value shown)', color: cK, type: 'box' }]);
  $('#simAssumptions').innerHTML = s.assumptions.map(a => `<li>${esc(a)}</li>`).join('') +
    '<li>StockSense deliberately holds more stock of fast movers (EOQ: fewer, larger orders); total cost still falls.</li>';
  if (!state.simSku) {
    const best = s.rows.slice().sort((p, q) => (q.gut.stockout_days - q.stocksense.stockout_days) - (p.gut.stockout_days - p.stocksense.stockout_days))[0];
    state.simSku = best.sku;
  }
  $('#simSku').value = state.simSku;
  renderSimTraj();
  renderSimTable();
}

function renderSimTraj() {
  const s = state.sim, row = s.rows.find(r => r.sku === state.simSku) || s.rows[0];
  $('#simTrajSub').textContent = `${row.name}: gut feel orders ${row.gut_order} ${row.gut_cycle}; StockSense uses ${MODEL_SHORT[row.model]} + reorder point`;
  trajChart($('#simTraj'), s.trajectories[row.sku], s.dates, $('#simTrajLegend'));
}

function renderSimTable() {
  const s = state.sim, sort = state.simSort;
  const cols = [
    ['name', 'SKU', r => r.name, false], ['gso', 'Stock-outs gut', r => r.gut.stockout_days, true], ['kso', 'Stock-outs SS', r => r.stocksense.stockout_days, true],
    ['gexp', 'Expired gut', r => r.gut.expired_units, true], ['kexp', 'Expired SS', r => r.stocksense.expired_units, true],
    ['ginv', 'Avg stock gut', r => r.gut.avg_inventory_value, true], ['kinv', 'Avg stock SS', r => r.stocksense.avg_inventory_value, true],
    ['gain', 'Cost saved', r => r.gut.total_cost - r.stocksense.total_cost, true],
  ];
  const getter = (cols.find(c => c[0] === sort.key) || cols[7])[2];
  const rows = s.rows.slice().sort((a, b) => { const x = getter(a), y = getter(b); return (x > y ? 1 : x < y ? -1 : 0) * sort.dir; });
  const fm = (key, v) => (key.endsWith('inv') || key === 'gain') ? fmtINR(v) : fmtNum(v);
  $('#simTable').innerHTML = `<thead><tr>${cols.map(c => `<th class="sortable${c[3] ? ' num' : ''}" data-k="${c[0]}">${c[1]}${sort.key === c[0] ? (sort.dir > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('')}</tr></thead><tbody>` +
    rows.map(r => `<tr class="clickable" data-sku="${esc(r.sku)}">${cols.map(c => c[0] === 'name'
      ? `<td><div class="nm">${esc(r.name)}</div><div class="sku">${esc(r.sku)} · gut ${r.gut_order}/${r.gut_cycle === 'daily' ? 'day' : 'wk'}</div></td>`
      : `<td class="num">${fm(c[0], c[2](r))}</td>`).join('')}</tr>`).join('') + '</tbody>';
  $$('#simTable th[data-k]').forEach(th => th.addEventListener('click', () => {
    const k = th.dataset.k; state.simSort = { key: k, dir: state.simSort.key === k ? -state.simSort.dir : -1 }; renderSimTable();
  }));
  $$('#simTable tr[data-sku]').forEach(tr => tr.addEventListener('click', () => { state.simSku = tr.dataset.sku; $('#simSku').value = state.simSku; renderSimTraj(); }));
}

/* ------------------------------------------------------------------ data tab */
async function renderData() {
  const s = state.summary;
  if (!s) return;
  $('#assumptionTable').innerHTML = '<thead><tr><th>Assumption</th><th>Value</th><th>Why</th></tr></thead><tbody>' +
    s.assumptions.map(a => `<tr><td class="nm">${esc(a.name)}</td><td>${esc(a.value)}</td><td class="hint">${esc(a.note)}</td></tr>`).join('') + '</tbody>';
  const w = s.warnings || [];
  $('#dataWarnings').innerHTML = (s.source === 'upload' ? `<div class="msg ok">Analysing your upload: ${s.skus} SKUs, ${fmtDate(s.history_start, true)} – ${fmtDate(s.history_end, true)}.${s.stockouts_detected != null ? ` ${s.stockouts_detected} probable stock-out days detected automatically.` : ''}</div>` : '') +
    w.map(x => `<div class="msg warn">${esc(x)}</div>`).join('');
  if (!state.health) { try { state.health = await api('/api/health'); } catch (e) { return; } }
  $('#apiTable').innerHTML = '<thead><tr><th>Method</th><th>Path</th><th>Returns</th></tr></thead><tbody>' +
    state.health.endpoints.map(e => `<tr><td>${esc(e.method)}</td><td>${esc(e.path)}</td><td class="hint">${esc(e.desc)}</td></tr>`).join('') + '</tbody>';
}

async function uploadFile(file) {
  if (!file) return;
  if (file.size > 8 * 1024 * 1024) { toast('File larger than 8 MB'); return; }
  const out = $('#uploadResult');
  out.innerHTML = `<div class="msg">Analysing ${esc(file.name)}…</div>`;
  try {
    const text = await file.text();
    const r = await api('/api/upload', { method: 'POST', headers: { 'Content-Type': 'text/csv' }, body: text });
    out.innerHTML = `<div class="msg ok">Loaded ${r.skus} SKUs × ${r.days} days (${fmtDate(r.start, true)} – ${fmtDate(r.end, true)}) in ${r.seconds}s.</div>`;
    state.sku = null; state.simSku = null; state.health = null;
    await loadCore();
    toast(`Your data is live: ${r.skus} SKUs analysed`);
  } catch (e) {
    out.innerHTML = `<div class="msg err">Upload rejected: ${esc(e.message)}</div>`;
    if (state.tab !== 'data') showTab('data');
  }
}

/* ------------------------------------------------------------------ wiring */
function applyTheme(t) {
  if (t) document.documentElement.setAttribute('data-theme', t); else document.documentElement.removeAttribute('data-theme');
}
function currentDark() {
  const t = document.documentElement.getAttribute('data-theme');
  return t ? t === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
}
function rerenderCharts() {
  if (!state.summary) return;
  if (state.tab === 'overview') renderOverview();
  if (state.tab === 'reorder') renderWhatif();
  if (state.tab === 'sku' && state.skuDetail) renderSku();
  if (state.tab === 'abc' && state.abc) renderAbc();
  if (state.tab === 'sim' && state.sim) renderSim();
}

function init() {
  tip.el = $('#tooltip');
  try { const t = localStorage.getItem('ss-theme'); if (t) applyTheme(t); } catch (e) { /* ignore */ }
  try { const tb = localStorage.getItem('ss-tab'); if (tb && $(`.tabs button[data-tab="${tb}"]`)) state.tab = tb; } catch (e) { /* ignore */ }
  $$('.tabs button').forEach(b => b.addEventListener('click', () => showTab(b.dataset.tab)));
  $$('[data-goto]').forEach(b => b.addEventListener('click', () => showTab(b.dataset.goto)));
  $('#btnTheme').addEventListener('click', () => {
    const next = currentDark() ? 'light' : 'dark';
    applyTheme(next);
    try { localStorage.setItem('ss-theme', next); } catch (e) { /* ignore */ }
    rerenderCharts();
  });
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', rerenderCharts);
  $('#btnDemo').addEventListener('click', async () => {
    const b = $('#btnDemo'); b.disabled = true;
    try {
      const r = await api('/api/demo', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      state.sku = null; state.simSku = null; state.health = null; $('#uploadResult').innerHTML = '';
      state.tab = 'overview';
      await loadCore();
      toast(`Demo store loaded: ${r.skus} SKUs × ${r.days} days analysed in ${r.seconds}s`);
    } catch (e) { toast(e.message, 4000); } finally { b.disabled = false; }
  });
  $('#fileInput').addEventListener('change', e => { uploadFile(e.target.files[0]); e.target.value = ''; });
  const dz = $('#dropZone');
  ['dragenter', 'dragover'].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add('over'); }));
  ['dragleave', 'drop'].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove('over'); }));
  dz.addEventListener('drop', e => uploadFile(e.dataTransfer.files[0]));
  dz.addEventListener('keydown', e => { if (e.key === 'Enter') $('#fileInput').click(); });
  // reorder controls
  const onService = debounce(() => refreshService(), 160);
  $('#slService').addEventListener('input', e => {
    state.service = Math.round(Number(e.target.value) * 10) / 1000;
    $('#slServiceVal').textContent = fmtPct(state.service);
    onService();
  });
  $$('#reorderFilter button').forEach(b => b.addEventListener('click', () => {
    state.filter = b.dataset.f; $$('#reorderFilter button').forEach(x => x.classList.toggle('active', x === b)); renderReorderTable();
  }));
  $('#reorderSearch').addEventListener('input', debounce(e => { state.search = e.target.value; renderReorderTable(); }, 120));
  $('#btnExport').addEventListener('click', exportOrders);
  // sku explorer
  $('#skuSelect').addEventListener('change', e => loadSku(e.target.value));
  const step = d => {
    const list = state.skus.map(s => s.sku);
    const i = list.indexOf(state.sku);
    loadSku(list[(i + d + list.length) % list.length]);
  };
  $('#skuPrev').addEventListener('click', () => step(-1));
  $('#skuNext').addEventListener('click', () => step(1));
  // basket
  const onBasket = debounce(async () => {
    try { state.basket = await api(`/api/basket?min_support=${state.support}&min_confidence=${state.conf}`); renderBasket(); } catch (e) { toast(e.message); }
  }, 200);
  $('#slSupport').addEventListener('input', e => { state.support = Number(e.target.value) / 100; $('#slSupportVal').textContent = fmtPct(state.support, 1); onBasket(); });
  $('#slConf').addEventListener('input', e => { state.conf = Number(e.target.value) / 100; $('#slConfVal').textContent = fmtPct(state.conf, 0); onBasket(); });
  $('#ruleSearch').addEventListener('input', debounce(e => { state.ruleSearch = e.target.value; renderBasket(); }, 120));
  // simulation
  $('#simSku').addEventListener('change', e => { state.simSku = e.target.value; renderSimTraj(); });
  window.addEventListener('resize', debounce(rerenderCharts, 180));
  window.addEventListener('scroll', () => tip.hide(), { passive: true });
  loadCore();
}

document.addEventListener('DOMContentLoaded', init);
