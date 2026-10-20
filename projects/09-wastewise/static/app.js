/* WasteWise dashboard - vanilla JS, no libraries, no network calls except our own /api. */
'use strict';

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const SVGNS = 'http://www.w3.org/2000/svg';
const DOWS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const LABEL = { wet: 'Wet', dry: 'Dry', recyclable: 'Recyclable', hazardous: 'Hazardous' };
const BIN_COL = { wet: '#16a34a', dry: '#2563eb', recyclable: '#d97706', hazardous: '#dc2626' };

const S = {
  town: null, plan: null, state: null, mode: 'smart', decFilter: 'pick',
  t: 0, playing: false, raf: 0, last: 0, mapH: null,
  fcBin: null, fc: null, lb: null, evaluation: null, impact: null, impTimer: 0,
  busy: false, loaded: {}
};

// ------------------------------------------------------------------ helpers
function svg(tag, attrs, parent) {
  const e = document.createElementNS(SVGNS, tag);
  if (attrs) for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = (v, d = 0) => Number(v || 0).toLocaleString('en-IN', { maximumFractionDigits: d, minimumFractionDigits: d });
const pc = (v) => Math.round((v || 0) * 100) + '%';
const inr = (v) => '₹' + fmt(v, 0);
function clock(min) {
  const h = 6 + min / 60;
  const hh = Math.floor(h), mm = Math.round((h - hh) * 60) % 60;
  return String(hh).padStart(2, '0') + ':' + String(mm).padStart(2, '0');
}
function compact(v) {
  const a = Math.abs(v);
  if (a >= 1e7) return fmt(v / 1e7, 2) + ' Cr';
  if (a >= 1e5) return fmt(v / 1e5, 2) + ' L';
  if (a >= 1e4) return fmt(v / 1e3, 1) + 'K';
  return fmt(v, 0);
}

async function api(path, body) {
  const opt = body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
  const r = await fetch(path, opt);
  let data;
  try { data = await r.json(); } catch (e) { data = { error: 'Unexpected response from server' }; }
  if (!r.ok) throw new Error(data.error || ('HTTP ' + r.status));
  return data;
}

let toastTimer = 0;
function toast(msg, err) {
  const t = $('#toast');
  t.textContent = msg;
  t.classList.toggle('err', !!err);
  t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), err ? 5000 : 3600);
}

function statusOf(l) {
  if (l >= 0.999) return { v: '--critical', t: 'Overflowing' };
  if (l >= 0.75) return { v: '--serious', t: 'Nearly full' };
  if (l >= 0.5) return { v: '--warning', t: 'Half full' };
  return { v: '--good', t: 'OK' };
}

function showTip(tip, wrap, evt, html) {
  tip.innerHTML = html;
  const r = wrap.getBoundingClientRect();
  let x = evt.clientX - r.left + 14, y = evt.clientY - r.top + 14;
  tip.classList.add('show');
  const tw = tip.offsetWidth, th = tip.offsetHeight;
  if (x + tw > r.width) x = Math.max(4, evt.clientX - r.left - tw - 14);
  if (y + th > r.height) y = Math.max(4, evt.clientY - r.top - th - 10);
  tip.style.left = x + 'px';
  tip.style.top = y + 'px';
}
const hideTip = (tip) => tip.classList.remove('show');

function binShape(g, type, cx, cy, r, style) {
  let e;
  if (type === 'wet') e = svg('circle', { cx, cy, r }, g);
  else if (type === 'dry') e = svg('rect', { x: cx - r * 0.9, y: cy - r * 0.9, width: r * 1.8, height: r * 1.8, rx: 3 }, g);
  else e = svg('path', { d: `M${cx} ${cy - r * 1.15} L${cx + r * 1.1} ${cy + r * 0.8} L${cx - r * 1.1} ${cy + r * 0.8} Z` }, g);
  e.setAttribute('class', 'shape');
  if (style) e.setAttribute('style', style);
  return e;
}
function shapeIcon(type, color) {
  const fill = color || 'var(--text-2)';
  if (type === 'wet') return `<svg viewBox="0 0 14 14"><circle cx="7" cy="7" r="5.5" style="fill:${fill}"/></svg>`;
  if (type === 'dry') return `<svg viewBox="0 0 14 14"><rect x="1.5" y="1.5" width="11" height="11" rx="2" style="fill:${fill}"/></svg>`;
  return `<svg viewBox="0 0 14 14"><path d="M7 1 L13 12 L1 12 Z" style="fill:${fill}"/></svg>`;
}

// ------------------------------------------------------------------ map
const MAP = { x0: -0.3, x1: 6.3, y0: -1.15, y1: 4.2, s: 100 };
const MX = (x) => (x - MAP.x0) * MAP.s;
const MY = (y) => (MAP.y1 - y) * MAP.s;
const truckVar = (i) => `var(--t${(i % 3) + 1})`;

function manhattanPoints(events, off) {
  const pts = [];
  for (let i = 0; i < events.length; i++) {
    const e = events[i];
    if (i > 0) {
      const p = events[i - 1];
      if (p.x !== e.x && p.y !== e.y) pts.push([e.x + off, p.y + off]);
    }
    pts.push([e.x + off, e.y + off]);
  }
  return pts;
}

function renderMap(el, opt) {
  const town = S.town;
  const small = !!opt.small;
  el.innerHTML = '';
  const W = (MAP.x1 - MAP.x0) * MAP.s, H = (MAP.y1 - MAP.y0) * MAP.s;
  el.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg('rect', { x: 0, y: 0, width: W, height: H, style: 'fill:var(--surface-2)' }, el);
  // wards
  town.wards.forEach((w, i) => {
    const [x0, y0, x1, y1] = w.rect;
    svg('rect', { x: MX(x0), y: MY(y1), width: (x1 - x0) * MAP.s, height: (y1 - y0) * MAP.s, class: 'ward', style: `fill:var(${(i + Math.floor(i / 3)) % 2 ? '--ward-b' : '--ward-a'})` }, el);
  });
  // streets
  const st = svg('g', {}, el);
  for (let k = 0; k <= 24; k++) {
    const x = k * 0.25;
    svg('line', { x1: MX(x), y1: MY(0), x2: MX(x), y2: MY(4), class: 'street' + (k % 4 === 0 ? ' main' : '') }, st);
  }
  for (let k = 0; k <= 16; k++) {
    const y = k * 0.25;
    svg('line', { x1: MX(0), y1: MY(y), x2: MX(6), y2: MY(y), class: 'street' + (k % 4 === 0 ? ' main' : '') }, st);
  }
  const dep = town.depot;
  svg('line', { x1: MX(dep.x), y1: MY(dep.y), x2: MX(dep.x), y2: MY(0), class: 'street main' }, st);
  // routes
  const routes = [];
  if (opt.run) {
    const rg = svg('g', {}, el);
    opt.run.trucks.forEach((tr, i) => {
      if (!tr.stops) return;
      const off = (i - 1) * 0.045;
      const pts = manhattanPoints(tr.events, off).map((p) => MX(p[0]).toFixed(1) + ',' + MY(p[1]).toFixed(1)).join(' ');
      svg('polyline', { points: pts, class: 'route-casing' }, rg);
      const pl = svg('polyline', { points: pts, class: 'route', style: `stroke:${truckVar(i)}` }, rg);
      routes.push(pl);
    });
  }
  // depot
  const dg = svg('g', { class: 'depot' }, el);
  svg('rect', { x: MX(dep.x) - 13, y: MY(dep.y) - 9, width: 26, height: 18, rx: 4 }, dg);
  const dt = svg('path', { d: `M${MX(dep.x) - 7} ${MY(dep.y) + 3} h14 M${MX(dep.x) - 5} ${MY(dep.y) - 3} h10`, style: 'stroke:var(--surface);stroke-width:2' }, dg);
  dt.setAttribute('fill', 'none');
  if (!small) {
    const tx = svg('text', { x: MX(dep.x) - 20, y: MY(dep.y) + 4, 'text-anchor': 'end' }, dg);
    tx.textContent = 'Depot / transfer station';
  }
  // bins
  const bg = svg('g', {}, el);
  const binEls = {};
  const scale = small ? 1.25 : 1;
  town.bins.forEach((b) => {
    const lvl = opt.levels[b.id] != null ? opt.levels[b.id] : 0;
    const r = (b.capacity >= 1100 ? 10 : b.capacity >= 660 ? 8.5 : 7) * scale;
    const g = svg('g', { class: 'bin', 'data-id': b.id, tabindex: small ? -1 : 0 }, bg);
    const cx = MX(b.x), cy = MY(b.y);
    if (opt.highlight && opt.highlight.has(b.id)) svg('circle', { cx, cy, r: r + 4.5, class: 'ring' }, g);
    if (lvl >= 0.999) svg('circle', { cx, cy, r: r + 3, class: 'overflow-pulse' }, g);
    const sh = binShape(g, b.type, cx, cy, r, `fill:var(${statusOf(lvl).v})`);
    binEls[b.id] = { g, shape: sh, level: lvl };
  });
  if (!small) {
    town.wards.forEach((w) => {
      const t = svg('text', { x: MX(w.rect[0]) + 8, y: MY(w.rect[3]) + 17, class: 'ward-label' }, el);
      t.textContent = w.id + ' · ' + w.name;
    });
  }
  // trucks
  const trucks = [];
  if (opt.run && !small) {
    const tg = svg('g', {}, el);
    opt.run.trucks.forEach((tr, i) => {
      const g = svg('g', { class: 'truck', 'data-truck': tr.truck }, tg);
      svg('circle', { r: 11, cx: 0, cy: 0, style: `fill:${truckVar(i)}` }, g);
      const t = svg('text', { x: 0, y: 0.5 }, g);
      t.textContent = String(i + 1);
      g.setAttribute('transform', `translate(${MX(dep.x) + (i - 1) * 24},${MY(dep.y) + 22})`);
      if (!tr.stops) g.setAttribute('opacity', '0.45');
      trucks.push(g);
    });
  }
  return { binEls, trucks, routes };
}

function truckPos(ev, t) {
  if (!ev.length) return null;
  if (t <= ev[0].depart) return { x: ev[0].x, y: ev[0].y, state: 'depot' };
  for (let i = 0; i < ev.length; i++) {
    const e = ev[i], n = ev[i + 1];
    if (t >= e.arrive && t <= e.depart) return { x: e.x, y: e.y, state: e.node === 'DEPOT' ? 'unloading' : 'service', node: e.node };
    if (n && t > e.depart && t < n.arrive) {
      const f = (t - e.depart) / Math.max(1e-6, n.arrive - e.depart);
      const dx = n.x - e.x, dy = n.y - e.y, tot = Math.abs(dx) + Math.abs(dy);
      const s = f * tot;
      if (s <= Math.abs(dx)) return { x: e.x + Math.sign(dx) * s, y: e.y, state: 'driving' };
      return { x: n.x, y: e.y + Math.sign(dy) * (s - Math.abs(dx)), state: 'driving' };
    }
  }
  const l = ev[ev.length - 1];
  return { x: l.x, y: l.y, state: 'done' };
}

function currentRun() { return S.plan ? S.plan[S.mode] : null; }

function drawMainMap() {
  const run = currentRun();
  const levels = S.state.levels[S.mode];
  const hl = new Set();
  run.trucks.forEach((t) => t.events.forEach((e) => { if (e.node !== 'DEPOT') hl.add(e.node); }));
  S.mapH = renderMap($('#map'), { levels, run, highlight: hl });
  S.visit = {};
  run.trucks.forEach((t) => t.events.forEach((e) => { if (e.node !== 'DEPOT') S.visit[e.node] = e.arrive; }));
  $('#map-sub').textContent = S.mode === 'smart'
    ? `· WasteWise: ${run.kpis.stops} bins on ${run.trucks.filter((t) => t.stops).length} trucks`
    : `· Fixed beat: ${run.kpis.stops} bins, ${run.unvisited.length} left for tomorrow`;
  bindMapTips();
  updatePlayback();
}

function updatePlayback() {
  const run = currentRun();
  if (!run || !S.mapH) return;
  const t = S.t;
  run.trucks.forEach((tr, i) => {
    const g = S.mapH.trucks[i];
    if (!g || !tr.stops) return;
    const p = truckPos(tr.events, t);
    const off = (i - 1) * 0.045;
    if (p.state === 'depot' && t <= 0) g.setAttribute('transform', `translate(${MX(S.town.depot.x) + (i - 1) * 24},${MY(S.town.depot.y) + 22})`);
    else g.setAttribute('transform', `translate(${MX(p.x + off).toFixed(1)},${MY(p.y + off).toFixed(1)})`);
  });
  for (const id in S.mapH.binEls) {
    const b = S.mapH.binEls[id];
    const done = S.visit[id] != null && t >= S.visit[id];
    b.shape.setAttribute('style', `fill:var(${done ? '--good' : statusOf(b.level).v})`);
    b.g.setAttribute('opacity', done ? '0.55' : '1');
  }
  $('#clock').textContent = clock(t);
  $('#scrub').value = String(Math.round(t));
}

function bindMapTips() {
  const wrap = $('#map-wrap'), tip = $('#tip');
  const dec = {};
  S.plan.decisions.forEach((d) => { dec[d.bin] = d; });
  $$('#map .bin').forEach((g) => {
    const id = g.getAttribute('data-id');
    const b = S.town.bins.find((x) => x.id === id);
    const ward = S.town.wards.find((w) => w.id === b.ward);
    const html = () => {
      const lvl = S.state.levels[S.mode][id];
      const v = S.visit[id];
      let line = '';
      if (S.mode === 'smart') line = dec[id] ? `<br>${esc(dec[id].reason)}` : '';
      else line = v != null ? `<br>Fixed beat empties it at ${clock(v)}` : '<br>Fixed beat does not reach it today';
      return `<b>${id}</b> · ${esc(ward.name)} (${b.ward})<br>${LABEL[b.type]} bin · ${fmt(b.capacity)} L<br>Level at 00:00: <b>${pc(lvl)}</b> (${statusOf(lvl).t})` +
        (v != null ? `<br>Truck arrives ${clock(v)}` : '') + line;
    };
    g.addEventListener('mousemove', (e) => showTip(tip, wrap, e, html()));
    g.addEventListener('mouseleave', () => hideTip(tip));
    g.addEventListener('click', () => openForecast(id));
    g.addEventListener('keydown', (e) => { if (e.key === 'Enter') openForecast(id); });
  });
}

function setPlaying(on) {
  S.playing = on;
  const b = $('#play');
  b.querySelector('span').textContent = on ? 'Pause' : 'Play routes';
  b.querySelector('svg').innerHTML = on ? '<path d="M4 3h3v10H4zM9 3h3v10H9z"/>' : '<path d="M4 2.5v11l9-5.5z"/>';
  if (on) {
    if (S.t >= maxT()) S.t = 0;
    S.last = performance.now();
    cancelAnimationFrame(S.raf);
    S.raf = requestAnimationFrame(tick);
  } else cancelAnimationFrame(S.raf);
}
function maxT() {
  const run = currentRun();
  let m = 0;
  if (run) run.trucks.forEach((t) => { m = Math.max(m, t.minutes); });
  return Math.max(30, Math.ceil(m));
}
function tick(now) {
  const dt = Math.min(0.1, (now - S.last) / 1000);
  S.last = now;
  S.t = Math.min(maxT(), S.t + dt * Number($('#speed').value));
  updatePlayback();
  if (S.t >= maxT()) { setPlaying(false); return; }
  S.raf = requestAnimationFrame(tick);
}

// ------------------------------------------------------------------ routes tab
function renderHeader() {
  const d = S.plan.day;
  $('#day-label').textContent = `Day ${d.day} · ${d.label}`;
  $('#market-badge').hidden = !d.market_day;
  $('#tomorrow-badge').hidden = !S.plan.tomorrow_market;
}

function renderKpis() {
  const s = S.plan.smart.kpis, f = S.plan.fixed.kpis, sv = S.plan.savings;
  const ico = {
    road: '<svg class="ico" viewBox="0 0 24 24"><path d="M5 21 9 3M19 21 15 3M12 6v2M12 11v2M12 16v2"/></svg>',
    fuel: '<svg class="ico" viewBox="0 0 24 24"><path d="M4 21V5a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v16M3 21h12M6 9h6M14 8h2a2 2 0 0 1 2 2v6a1.5 1.5 0 0 0 3 0V9l-3-3"/></svg>',
    leaf: '<svg class="ico" viewBox="0 0 24 24"><path d="M5 19c0-8 5-13 15-14-1 10-6 15-14 15M5 19c3-4 6-6 9-7"/></svg>',
    bin: '<svg class="ico" viewBox="0 0 24 24"><path d="M5 7h14l-1.3 13a2 2 0 0 1-2 1.8H8.3a2 2 0 0 1-2-1.8zM4 7h16M9 7V4h6v3"/></svg>',
    warn: '<svg class="ico" viewBox="0 0 24 24"><path d="M12 3 2 21h20zM12 10v5M12 18v.5"/></svg>'
  };
  const tiles = [
    { cls: 'hero', label: ico.road + 'Distance today', value: `${fmt(s.km, 1)}<small>km</small>`, delta: `<b>−${fmt(sv.km_pct, 0)}%</b> vs ${fmt(f.km, 1)} km on the fixed beat` },
    { label: ico.fuel + 'Diesel saved today', value: `${fmt(sv.fuel_l, 1)}<small>L</small>`, delta: `<b>${inr(sv.inr)}</b> · ${fmt(s.fuel_l, 1)} L used vs ${fmt(f.fuel_l, 1)} L` },
    { label: ico.leaf + 'CO₂ avoided today', value: `${fmt(sv.co2_kg, 1)}<small>kg</small>`, delta: `${fmt(s.co2_kg, 1)} kg emitted vs ${fmt(f.co2_kg, 1)} kg` },
    { label: ico.bin + 'Bins collected', value: `${s.stops}<small>/ ${S.town.bins.length}</small>`, delta: `avg <b>${pc(s.avg_fill_at_pickup)}</b> full at pickup (fixed: ${pc(f.avg_fill_at_pickup)})` },
    { label: ico.warn + 'Overflowing bins today', value: `${s.overflow_bins}<small>bins</small>`, delta: `fixed beat: <b style="color:var(--critical)">${f.overflow_bins}</b> bins, ${fmt(f.overflow_l)} L spilled` }
  ];
  $('#kpis').innerHTML = tiles.map((t) => `<div class="kpi ${t.cls || ''}"><div class="label">${t.label}</div><div class="value">${t.value}</div><div class="delta">${t.delta}</div></div>`).join('');
}

function cmpTable(el, f, s, rows, heads) {
  heads = heads || ['Fixed beat', 'WasteWise'];
  let html = `<thead><tr><th></th><th><span class="key" style="background:var(--fixed)"></span>${heads[0]}</th><th><span class="key" style="background:var(--smart)"></span>${heads[1]}</th><th>Change</th></tr></thead><tbody>`;
  rows.forEach(([label, key, d, kind]) => {
    const a = f[key], b = s[key];
    const isPct = kind === 'pct';
    const show = (v) => isPct ? pc(v) : (kind === 'inr' ? inr(v) : fmt(v, d));
    const higherBetter = kind === 'pct';
    let ch = '';
    if (isPct) ch = (b - a >= 0 ? '+' : '−') + Math.abs(Math.round((b - a) * 100)) + ' pts';
    else if (a) ch = (b <= a ? '−' : '+') + Math.abs(Math.round(100 * (1 - b / a))) + '%';
    else ch = b === 0 ? '–' : '+' + show(b);
    const sWins = higherBetter ? b > a : b < a;
    const fWins = higherBetter ? a > b : a < b;
    html += `<tr><td>${label}</td><td class="${fWins ? 'win' : 'lose'}">${show(a)}</td><td class="${sWins ? 'win' : 'lose'}">${show(b)}</td><td class="${sWins ? 'good-txt' : fWins ? 'bad-txt' : ''}">${ch}</td></tr>`;
  });
  el.innerHTML = html + '</tbody>';
}

const CMP_ROWS = [
  ['Distance (km)', 'km', 1], ['Diesel (L)', 'fuel_l', 1], ['CO₂ (kg)', 'co2_kg', 1],
  ['Diesel cost', 'cost_inr', 0, 'inr'], ['Truck-hours', 'truck_hours', 1], ['Bins emptied', 'stops', 0],
  ['Avg fill at pickup', 'avg_fill_at_pickup', 0, 'pct'], ['Half-empty pickups (<50%)', 'half_empty_pickups', 0],
  ['Overflowing bins', 'overflow_bins', 0], ['Litres spilled', 'overflow_l', 0]
];

function renderCompare() {
  cmpTable($('#compare'), S.plan.fixed.kpis, S.plan.smart.kpis, CMP_ROWS);
  const n = S.plan.naive_all;
  $('#naive-note').innerHTML = `Literally visiting all ${n.bins} bins in fixed order needs <b>${fmt(n.km, 1)} km</b> and <b>${fmt(n.truck_hours, 1)} truck-hours</b> - more than the fleet's ${S.town.trucks.length} × ${S.plan.shift.minutes / 60} h window, so the fixed beat leaves <b>${S.plan.fixed.unvisited.length}</b> bins for tomorrow (it resumes there).`;
}

function renderAlgo() {
  const a = S.plan.algorithm;
  const dec = S.plan.decisions;
  const nA = dec.filter((d) => d.collect && d.rule === 'A').length, nB = dec.filter((d) => d.collect && d.rule === 'B').length;
  const mx = Math.max(a.fixed_order_km, a.clarke_wright_km, a.two_opt_km, 1);
  const bar = (v, warm) => `<div class="bar-track"><div class="bar-fill ${warm ? 'warm' : ''}" style="width:${(100 * v / mx).toFixed(1)}%"></div></div>`;
  const used = S.plan.smart.trucks.filter((t) => t.stops).length;
  $('#algo').innerHTML = `<ol class="steps">
    <li><span class="n">1</span><span class="t">Forecast picks bins<small>rule A (≥75% at pickup): ${nA} · rule B (overflow guard): ${nB}</small></span><span class="v">${a.bins} / ${S.town.bins.length}</span></li>
    <li><span class="n">2</span><span class="t">Same bins, fixed route-chart order<small>${a.fixed_order_trips} trips, naive sequence</small>${bar(a.fixed_order_km, true)}</span><span class="v">${fmt(a.fixed_order_km, 1)} km</span></li>
    <li><span class="n">3</span><span class="t">Clarke–Wright savings<small>${a.merges} merges from ${a.savings_considered} pairs · ${a.rejected_capacity} blocked by capacity</small>${bar(a.clarke_wright_km)}</span><span class="v">${fmt(a.clarke_wright_km, 1)} km</span></li>
    <li><span class="n">4</span><span class="t">2-opt uncrossing<small>${a.two_opt_moves} improving move${a.two_opt_moves === 1 ? '' : 's'} · never makes a route longer</small>${bar(a.two_opt_km)}</span><span class="v">${fmt(a.two_opt_km, 1)} km</span></li>
    <li><span class="n">5</span><span class="t">Pack trips on trucks<small>longest trip first, ${S.plan.shift.start}–${S.plan.shift.end} window${a.deferred.length ? ` · ${a.deferred.length} bins deferred` : ''}</small></span><span class="v">${a.trips} trip${a.trips === 1 ? '' : 's'} · ${used} truck${used === 1 ? '' : 's'}</span></li>
  </ol>
  <div class="pairs">${a.top_savings.slice(0, 5).map((p) => `<span>${p.a} ↔ ${p.b} saves ${fmt(p.saving_km, 1)} km</span>`).join('')}</div>`;
  $('#algo-ms').textContent = `solved in ${fmt(a.total_ms, 2)} ms`;
}

function renderTrucks() {
  const run = currentRun();
  const cap = S.town.trucks[0].capacity;
  $('#truck-sub').textContent = S.mode === 'smart' ? 'WasteWise plan' : 'fixed beat';
  $('#trucks').innerHTML = run.trucks.map((t, i) => {
    if (!t.stops) return `<div class="truck-row"><span class="truck-dot" style="background:${truckVar(i)}">${i + 1}</span><div><b>${t.name}</b><div class="meta">Stays at the depot today - free for bulky-waste or drain duty</div></div><div class="right"><b>0 km</b></div></div>`;
    const trips = t.trips ? t.trips.length : t.unloads;
    const load = t.trips ? t.trips.map((x) => fmt(x.planned_load_l) + ' L').join(' + ') : '';
    const meta = S.mode === 'smart'
      ? `${t.stops} bins · ${trips} trip${trips === 1 ? '' : 's'} · planned load ${load} (of ${fmt(cap)} L each)`
      : `${t.stops} bins · ${t.unloads} unload${t.unloads === 1 ? '' : 's'} · empties every bin it reaches`;
    return `<div class="truck-row"><span class="truck-dot" style="background:${truckVar(i)}">${i + 1}</span><div><b>${t.name}</b><div class="meta">${meta}</div></div><div class="right"><b>${fmt(t.km, 1)} km</b><br>back ${t.finish} · ${fmt(t.fuel_l, 1)} L</div></div>`;
  }).join('');
}

function meter(l) {
  const st = statusOf(l);
  return `<span class="meter"><span class="trk"><span class="fl" style="width:${Math.min(100, l * 100).toFixed(0)}%;background:var(${st.v})"></span></span>${pc(l)}</span>`;
}

function renderDecisions() {
  const deferred = new Set(S.plan.algorithm.deferred);
  let rows = S.plan.decisions.slice();
  if (S.decFilter === 'pick') rows = rows.filter((d) => d.collect);
  rows.sort((a, b) => (b.collect - a.collect) || (b.urgency - a.urgency));
  const wname = {};
  S.town.wards.forEach((w) => { wname[w.id] = w.name; });
  const ttf = (h) => h == null ? '>14 d' : h < 24 ? fmt(h, 0) + ' h' : fmt(h / 24, 1) + ' d';
  let html = '<thead><tr><th>Bin</th><th>Ward</th><th>Type</th><th>Level 00:00</th><th class="r">At pickup</th><th class="r">If skipped (+σ)</th><th class="r">Full in</th><th>Decision</th><th>Why</th></tr></thead><tbody>';
  rows.forEach((d) => {
    const tag = deferred.has(d.bin) ? '<span class="rule def">Deferred</span>'
      : d.collect ? `<span class="rule ${d.rule}">Collect · rule ${d.rule}</span>` : '<span class="rule skip">Skip</span>';
    html += `<tr class="${d.collect ? 'pick' : ''}" data-bin="${d.bin}"><td><b>${d.bin}</b></td><td>${esc(wname[d.ward])}</td><td><span class="type-pill">${shapeIcon(d.type)}${LABEL[d.type]}</span></td><td>${meter(d.level)}</td><td class="r">${pc(d.at_pickup)}</td><td class="r">${pc(d.if_skipped_hi)}</td><td class="r">${ttf(d.hours_to_full)}</td><td>${tag}</td><td class="small">${esc(d.reason)}</td></tr>`;
  });
  if (!rows.length) html += '<tr><td colspan="9" class="empty">No bins need collection today.</td></tr>';
  $('#decisions').innerHTML = html + '</tbody>';
  $$('#decisions tr[data-bin]').forEach((tr) => tr.addEventListener('click', () => openForecast(tr.getAttribute('data-bin'))));
}

function renderLegend() {
  const st = [['--good', 'Below 50%'], ['--warning', '50–75%'], ['--serious', '75–100%'], ['--critical', 'Overflowing']];
  const run = currentRun();
  $('#map-legend').innerHTML =
    st.map(([v, t]) => `<span class="item"><span class="sw" style="background:var(${v})"></span>${t}</span>`).join('') +
    ['wet', 'dry', 'recyclable'].map((t) => `<span class="item">${shapeIcon(t)}${LABEL[t]}</span>`).join('') +
    run.trucks.map((t, i) => `<span class="item"><span class="line" style="background:${truckVar(i)}"></span>T${i + 1}</span>`).join('') +
    '<span class="item muted">ring = collected today · size = 240 / 660 / 1100 L</span>';
}

function renderRoutesTab() {
  renderHeader();
  renderKpis();
  renderCompare();
  renderAlgo();
  renderTrucks();
  renderLegend();
  drawMainMap();
  renderDecisions();
}

// ------------------------------------------------------------------ charts
function chartFrame(el, W, H, m, ymax, yfmt, ticks) {
  el.innerHTML = '';
  el.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const g = svg('g', { class: 'grid' }, el);
  const ax = svg('g', { class: 'axis' }, el);
  const y = (v) => m.t + (H - m.t - m.b) * (1 - v / ymax);
  const n = ticks || 4;
  for (let k = 0; k <= n; k++) {
    const v = ymax * k / n;
    svg('line', { x1: m.l, x2: W - m.r, y1: y(v), y2: y(v) }, g);
    const t = svg('text', { x: m.l - 6, y: y(v) + 4, 'text-anchor': 'end' }, ax);
    t.textContent = yfmt(v);
  }
  return { y, ax };
}
function niceMax(v) {
  if (v <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  for (const k of [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (k * p >= v) return k * p;
  return 10 * p;
}

function lineChart(el, tipEl, labels, series, opts) {
  const W = 640, H = 220, m = { l: 40, r: 14, t: 12, b: 26 };
  const n = labels.length;
  const ymax = niceMax(Math.max(1, ...series.flatMap((s) => s.values)) * 1.05);
  const { y, ax } = chartFrame(el, W, H, m, ymax, (v) => fmt(v, 0));
  const x = (i) => m.l + (n <= 1 ? (W - m.l - m.r) / 2 : (W - m.l - m.r) * i / (n - 1));
  const bw = n > 1 ? (W - m.l - m.r) / (n - 1) : 20;
  (opts.market || []).forEach((mk, i) => { if (mk) svg('rect', { x: x(i) - bw / 2, y: m.t, width: bw, height: H - m.t - m.b, class: 'market' }, el); });
  const step = Math.max(1, Math.ceil(n / 8));
  labels.forEach((l, i) => {
    const lastOk = i === n - 1 && (n - 1) % step >= step / 2;
    if (i % step && !lastOk) return;
    const t = svg('text', { x: x(i), y: H - 8, 'text-anchor': 'middle' }, ax);
    t.textContent = l;
  });
  series.forEach((s) => {
    const pts = s.values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
    svg('polyline', { points: pts, fill: 'none', style: `stroke:${s.color};stroke-width:2;stroke-linejoin:round;stroke-linecap:round` }, el);
    const li = s.values.length - 1;
    if (li >= 0) svg('circle', { cx: x(li), cy: y(s.values[li]), r: 4, style: `fill:${s.color};stroke:var(--surface);stroke-width:2` }, el);
  });
  const cross = svg('line', { y1: m.t, y2: H - m.b, style: 'stroke:var(--axis);stroke-width:1', opacity: 0 }, el);
  const wrap = el.parentNode;
  for (let i = 0; i < n; i++) {
    const r = svg('rect', { x: x(i) - bw / 2, y: m.t, width: Math.max(bw, 8), height: H - m.t - m.b, class: 'hit' }, el);
    r.addEventListener('mousemove', (e) => {
      cross.setAttribute('x1', x(i)); cross.setAttribute('x2', x(i)); cross.setAttribute('opacity', 1);
      showTip(tipEl, wrap, e, `<b>${esc(labels[i])}</b>${opts.market && opts.market[i] ? ' · market day' : ''}<br>` + series.map((s) => `${s.name}: <b>${fmt(s.values[i], opts.d || 1)}</b> ${opts.unit || ''}`).join('<br>'));
    });
    r.addEventListener('mouseleave', () => { cross.setAttribute('opacity', 0); hideTip(tipEl); });
  }
}

function groupedBars(el, tipEl, labels, series, opts) {
  const W = 640, H = 200, m = { l: 34, r: 12, t: 12, b: 26 };
  const n = labels.length;
  const ymax = niceMax(Math.max(2, ...series.flatMap((s) => s.values)));
  const { y, ax } = chartFrame(el, W, H, m, ymax, (v) => fmt(v, 0), Math.min(4, ymax));
  const band = (W - m.l - m.r) / Math.max(1, n);
  const bw = Math.min(10, (band - 4) / series.length);
  const step = Math.max(1, Math.ceil(n / 8));
  const wrap = el.parentNode;
  labels.forEach((l, i) => {
    const x0 = m.l + band * i;
    if (opts.market && opts.market[i]) svg('rect', { x: x0, y: m.t, width: band, height: H - m.t - m.b, class: 'market' }, el);
    series.forEach((s, k) => {
      const v = s.values[i];
      if (v > 0) {
        const bx = x0 + band / 2 - (bw * series.length + 2 * (series.length - 1)) / 2 + k * (bw + 2);
        const top = y(v), base = y(0);
        const r = Math.min(3, bw / 2, base - top);
        svg('path', { d: `M${bx} ${base} V${top + r} Q${bx} ${top} ${bx + r} ${top} H${bx + bw - r} Q${bx + bw} ${top} ${bx + bw} ${top + r} V${base} Z`, style: `fill:${s.color}` }, el);
      }
    });
    if (!(i % step) || (i === n - 1 && (n - 1) % step >= step / 2)) {
      const t = svg('text', { x: x0 + band / 2, y: H - 8, 'text-anchor': 'middle' }, ax);
      t.textContent = l;
    }
    const hit = svg('rect', { x: x0, y: m.t, width: band, height: H - m.t - m.b, class: 'hit' }, el);
    hit.addEventListener('mousemove', (e) => showTip(tipEl, wrap, e, `<b>${esc(labels[i])}</b>${opts.market && opts.market[i] ? ' · market day' : ''}<br>` + series.map((s) => `${s.name}: <b>${fmt(s.values[i])}</b> ${opts.unit || ''}`).join('<br>')));
    hit.addEventListener('mouseleave', () => hideTip(tipEl));
  });
}

// ------------------------------------------------------------------ simulator tab
function renderSim() {
  const st = S.state;
  const tf = st.totals.fixed, ts = st.totals.smart;
  $('#sim-days').textContent = tf.days ? `· ${tf.days} simulated day${tf.days === 1 ? '' : 's'}` : '· no days run yet';
  $('#sim-status').textContent = `Today: day ${st.today.day} (${st.today.label})`;
  if (tf.days) cmpTable($('#sim-compare'), tf, ts, CMP_ROWS);
  else $('#sim-compare').innerHTML = '<tbody><tr><td class="empty">Press <b>Next day</b> or <b>Run to day 30</b> - both worlds get exactly the same waste, only the collection policy differs.</td></tr></tbody>';
  const ov = (lv) => lv;
  renderMap($('#map-fixed'), { levels: ov(st.levels.fixed), small: true });
  renderMap($('#map-smart'), { levels: ov(st.levels.smart), small: true });
  const df = st.daily.fixed, ds = st.daily.smart;
  const labels = df.map((d) => 'D' + d.day);
  const market = df.map((d) => !!d.market_day);
  if (df.length) {
    lineChart($('#chart-km'), $('#tip-km'), labels, [
      { name: 'Fixed beat', color: 'var(--fixed)', values: df.map((d) => d.km) },
      { name: 'WasteWise', color: 'var(--smart)', values: ds.map((d) => d.km) }], { market, unit: 'km', d: 1 });
    groupedBars($('#chart-ovf'), $('#tip-ovf'), labels, [
      { name: 'Fixed beat', color: 'var(--fixed)', values: df.map((d) => d.overflow_bins) },
      { name: 'WasteWise', color: 'var(--smart)', values: ds.map((d) => d.overflow_bins) }], { market, unit: 'bins' });
  } else {
    ['#chart-km', '#chart-ovf'].forEach((s) => {
      const e = $(s); e.innerHTML = ''; e.setAttribute('viewBox', '0 0 640 120');
      const t = svg('text', { x: 320, y: 64, 'text-anchor': 'middle', class: 'axis' }, e);
      t.textContent = 'Run some days to see the comparison';
    });
  }
  const ev = st.events;
  $('#events').innerHTML = ev.length ? ev.map((e) => {
    const f = e.fixed_overflows, s = e.smart_overflows;
    const lst = (o) => o.length ? o.map((x) => `${x.bin}`).join(', ') + ` (${fmt(o.reduce((a, b) => a + b.litres, 0))} L)` : 'none';
    return `<li><span><b>${esc(e.label)}</b>${e.market_day ? '<br><span class="badge warm">market day</span>' : ''}</span><span><span class="${f.length ? 'bad-txt' : ''}">Fixed beat:</span> ${lst(f)} · ${fmt(e.fixed_km, 1)} km<br><span class="${s.length ? 'bad-txt' : 'good-txt'}">WasteWise:</span> ${lst(s)} · ${fmt(e.smart_km, 1)} km</span></li>`;
  }).join('') : '<li class="empty" style="display:block">No days simulated yet.</li>';
}

// ------------------------------------------------------------------ forecast tab
function openForecast(id) {
  S.fcBin = id;
  switchTab('forecast');
}

async function loadForecast() {
  if (!S.fcBin) {
    const urgent = S.plan.decisions.slice().sort((a, b) => b.urgency - a.urgency);
    S.fcBin = urgent[0].bin;
  }
  $('#bin-select').value = S.fcBin;
  try {
    S.fc = await api('/api/forecast?bin=' + encodeURIComponent(S.fcBin));
  } catch (e) { toast(e.message, true); return; }
  renderForecast();
  if (!S.evaluation) loadEvaluation().then(renderFcOverall);
  else renderFcOverall();
}

function renderForecastPicker() {
  const wn = {};
  S.town.wards.forEach((w) => { wn[w.id] = w.name; });
  $('#bin-select').innerHTML = S.town.bins.map((b) => `<option value="${b.id}">${b.id} · ${esc(wn[b.ward])} · ${LABEL[b.type]} ${b.capacity} L</option>`).join('');
  const urgent = S.plan.decisions.slice().sort((a, b) => b.urgency - a.urgency).slice(0, 6);
  $('#urgent-chips').innerHTML = urgent.map((d) => `<button type="button" class="chip ${d.bin === S.fcBin ? 'on' : ''}" data-bin="${d.bin}">${d.bin} · ${pc(d.if_skipped_hi)}</button>`).join('');
  $$('#urgent-chips .chip').forEach((c) => c.addEventListener('click', () => { S.fcBin = c.getAttribute('data-bin'); renderForecastPicker(); loadForecast(); }));
}

function renderForecast() {
  const f = S.fc;
  const hist = f.history, fc = f.forecast;
  const all = hist.map((h) => ({ ...h, kind: 'obs' })).concat(fc.map((x) => ({ ...x, kind: 'fc' })));
  const el = $('#chart-fc'), tip = $('#tip-fc');
  const W = 680, H = 230, m = { l: 40, r: 10, t: 12, b: 28 };
  const ymax = niceMax(Math.max(...all.map((a) => a.hi || a.value)) * 100 * 1.08);
  const { y, ax } = chartFrame(el, W, H, m, ymax, (v) => fmt(v, 0) + '%');
  const n = all.length, band = (W - m.l - m.r) / n, bw = Math.min(10, band - 2);
  const wrap = el.parentNode;
  const fitPts = [];
  const gMk = svg('g', {}, el), gBar = svg('g', {}, el), gLine = svg('g', {}, el), gHit = svg('g', {}, el);
  all.forEach((a, i) => {
    const x0 = m.l + band * i, cx = x0 + band / 2;
    if (a.market_day) svg('rect', { x: x0, y: m.t, width: band, height: H - m.t - m.b, class: 'market' }, gMk);
    const v = a.value * 100, top = y(v), base = y(0), r = Math.min(3, bw / 2, Math.max(0, base - top));
    svg('path', { d: `M${cx - bw / 2} ${base} V${top + r} Q${cx - bw / 2} ${top} ${cx - bw / 2 + r} ${top} H${cx + bw / 2 - r} Q${cx + bw / 2} ${top} ${cx + bw / 2} ${top + r} V${base} Z`, style: `fill:${a.kind === 'obs' ? 'var(--smart)' : 'var(--warm)'};opacity:${a.kind === 'obs' ? 0.85 : 1}` }, gBar);
    if (a.kind === 'fc') {
      svg('line', { x1: cx, x2: cx, y1: y(a.hi * 100), y2: y(a.lo * 100), style: 'stroke:var(--text-2);stroke-width:1.5' }, gLine);
      svg('line', { x1: cx - 3, x2: cx + 3, y1: y(a.hi * 100), y2: y(a.hi * 100), style: 'stroke:var(--text-2);stroke-width:1.5' }, gLine);
    }
    if (a.kind === 'obs' && a.fitted != null) fitPts.push(`${cx.toFixed(1)},${y(a.fitted * 100).toFixed(1)}`);
    if (i % 7 === 0 || i === hist.length) {
      const t = svg('text', { x: cx, y: H - 9, 'text-anchor': 'middle' }, ax);
      t.textContent = i === hist.length ? 'today' : a.date.slice(5);
    }
    const hit = svg('rect', { x: x0, y: m.t, width: band, height: H - m.t - m.b, class: 'hit' }, gHit);
    hit.addEventListener('mousemove', (e) => showTip(tip, wrap, e, `<b>${a.dow} ${a.date}</b>${a.market_day ? ' · market day' : ''}<br>` +
      (a.kind === 'obs' ? `Observed: <b>${fmt(v, 1)}%</b>` + (a.fitted != null ? `<br>Model (1-step): ${fmt(a.fitted * 100, 1)}%` : '') : `Forecast: <b>${fmt(v, 1)}%</b><br>±1σ range ${fmt(a.lo * 100, 0)}–${fmt(a.hi * 100, 0)}%`)));
    hit.addEventListener('mouseleave', () => hideTip(tip));
  });
  svg('polyline', { points: fitPts.join(' '), fill: 'none', style: 'stroke:var(--text-2);stroke-width:2;stroke-linejoin:round' }, gLine);
  const xt = m.l + band * hist.length;
  svg('line', { x1: xt, x2: xt, y1: m.t, y2: H - m.b, style: 'stroke:var(--text-2);stroke-width:1' }, gLine);
  $('#fc-legend').innerHTML = '<span class="item"><span class="sw" style="background:var(--smart)"></span>Observed daily fill (sensor)</span><span class="item"><span class="line" style="background:var(--text-2)"></span>Model one-step fit</span><span class="item"><span class="sw" style="background:var(--warm)"></span>Forecast ±1σ</span><span class="item"><span class="sw" style="background:var(--warm-wash);border:1px solid var(--border)"></span>Market day</span>';

  // projection
  {
    const pe = $('#chart-proj'), pt = $('#tip-proj');
    const raw = [f.level].concat(f.if_not_collected).map((v) => v * 100);
    const vals = raw.map((v) => Math.min(v, 100));
    const labs = ['now'].concat(fc.map((x) => x.dow));
    const W2 = 320, H2 = 190, m2 = { l: 38, r: 10, t: 12, b: 24 };
    const ym = 125;
    const fr = chartFrame(pe, W2, H2, m2, ym, (v) => fmt(v, 0) + '%', 5);
    const x = (i) => m2.l + (W2 - m2.l - m2.r) * i / (vals.length - 1);
    [[100, '--critical', 'full - waste spills', -5], [75, '--warm', 'rule A: 75%', 13]].forEach(([v, c, t, dy]) => {
      svg('line', { x1: m2.l, x2: W2 - m2.r, y1: fr.y(v), y2: fr.y(v), style: `stroke:var(${c});stroke-width:1.5` }, pe);
      const tx = svg('text', { x: W2 - m2.r, y: fr.y(v) + dy, 'text-anchor': 'end', class: 'lbl' }, pe);
      tx.textContent = t;
    });
    labs.forEach((l, i) => { const t = svg('text', { x: x(i), y: H2 - 7, 'text-anchor': 'middle' }, fr.ax); t.textContent = l; });
    svg('polyline', { points: vals.map((v, i) => `${x(i)},${fr.y(v)}`).join(' '), fill: 'none', style: 'stroke:var(--smart);stroke-width:2;stroke-linejoin:round' }, pe);
    vals.forEach((v, i) => {
      const c = svg('circle', { cx: x(i), cy: fr.y(v), r: 4, style: `fill:var(${statusOf(v / 100).v});stroke:var(--surface);stroke-width:2` }, pe);
      const hit = svg('circle', { cx: x(i), cy: fr.y(v), r: 12, class: 'hit' }, pe);
      hit.addEventListener('mousemove', (e) => showTip(pt, pe.parentNode, e, `<b>${labs[i]}</b><br>Level: <b>${fmt(Math.min(raw[i], 100), 0)}%</b>${raw[i] >= 100 ? `<br>overflowing - ${fmt(raw[i] - 100, 0)}% of capacity spilled` : ''}`));
      hit.addEventListener('mouseleave', () => hideTip(pt));
      return c;
    });
  }
  // seasonal index
  {
    const se = $('#chart-season'), stp = $('#tip-season');
    const W3 = 320, H3 = 190, m3 = { l: 32, r: 8, t: 16, b: 24 };
    const vals = f.season.map((s) => s.index);
    const ym = niceMax(Math.max(...vals) * 1.15);
    const fr = chartFrame(se, W3, H3, m3, ym, (v) => fmt(v, 1));
    const band = (W3 - m3.l - m3.r) / 7, bw = Math.min(22, band - 8);
    const imax = vals.indexOf(Math.max(...vals));
    f.season.forEach((s, i) => {
      const cx = m3.l + band * i + band / 2, top = fr.y(s.index), base = fr.y(0), r = Math.min(4, base - top);
      svg('path', { d: `M${cx - bw / 2} ${base} V${top + r} Q${cx - bw / 2} ${top} ${cx - bw / 2 + r} ${top} H${cx + bw / 2 - r} Q${cx + bw / 2} ${top} ${cx + bw / 2} ${top + r} V${base} Z`, style: 'fill:var(--smart)' }, se);
      const t = svg('text', { x: cx, y: H3 - 7, 'text-anchor': 'middle' }, fr.ax); t.textContent = s.dow;
      if (i === imax) { const v = svg('text', { x: cx, y: top - 5, 'text-anchor': 'middle', class: 'val' }, se); v.textContent = '×' + fmt(s.index, 2); }
      const hit = svg('rect', { x: cx - band / 2, y: m3.t, width: band, height: H3 - m3.t - m3.b, class: 'hit' }, se);
      hit.addEventListener('mousemove', (e) => showTip(stp, se.parentNode, e, `<b>${s.dow}</b>: ×${fmt(s.index, 2)} of an average day${s.dow === S.town.constants.market_weekday ? '<br>weekly market (santhai) day' : ''}`));
      hit.addEventListener('mouseleave', () => hideTip(stp));
    });
    svg('line', { x1: m3.l, x2: W3 - m3.r, y1: fr.y(1), y2: fr.y(1), style: 'stroke:var(--text-2);stroke-width:1' }, se);
  }
  // info card
  const b = f.bin, d = f.decision;
  const lv = f.level, st = statusOf(lv);
  const circ = 2 * Math.PI * 38;
  const tag = d.collect ? `<span class="rule ${d.rule}">Collect today · rule ${d.rule}</span>` : '<span class="rule skip">Skip today</span>';
  $('#fc-info').innerHTML = `<div class="card-head"><h2>${b.id} · ${esc(f.ward_name)} <span class="sub">(${b.ward})</span></h2>${tag}</div>
    <div class="gauge"><svg viewBox="0 0 92 92"><circle cx="46" cy="46" r="38" style="fill:none;stroke:var(--surface-2);stroke-width:10"/><circle cx="46" cy="46" r="38" transform="rotate(-90 46 46)" style="fill:none;stroke:var(${st.v});stroke-width:10;stroke-linecap:round" stroke-dasharray="${(circ * Math.min(1, lv)).toFixed(1)} ${circ.toFixed(1)}"/><text x="46" y="52" text-anchor="middle" style="fill:var(--text);font-size:19px;font-weight:750">${pc(lv)}</text></svg>
    <div><div class="muted small">Level at 00:00 today · ${st.t}</div><div class="big">${f.hours_to_full == null ? 'Not full in 14 d' : 'Full in ' + (f.hours_to_full < 48 ? fmt(f.hours_to_full, 0) + ' h' : fmt(f.hours_to_full / 24, 1) + ' days')}</div><div class="muted small">${f.full_at ? 'predicted ' + esc(f.full_at) + ' if not collected' : ''}</div></div></div>
    <div class="reason">${esc(d.reason)}</div>
    <dl class="stat-list" style="margin-top:12px">
      <dt>Type · capacity</dt><dd><span class="type-pill">${shapeIcon(b.type)}${LABEL[b.type]}</span> · ${fmt(b.capacity)} L</dd>
      <dt>Forecast today / tomorrow</dt><dd>+${pc(d.forecast_today)} / +${pc(d.forecast_tomorrow)}</dd>
      <dt>Forecast error σ</dt><dd>${fmt(f.model.sigma * 100, 1)} pts</dd>
      <dt>Model</dt><dd>seasonal exp. smoothing</dd>
      <dt>α (level) · γ (weekday)</dt><dd>${f.model.alpha} · ${f.model.gamma} <span class="muted small">grid-searched</span></dd>
    </dl>`;
  const names = { naive: 'Naive (yesterday)', seasonal_naive: 'Same weekday last week', ses: 'Simple exp. smoothing', ols_weekday: 'Linear regression + weekday', seasonal_es: 'Seasonal exp. smoothing (used)' };
  const mae = f.backtest_mae;
  const best = Object.keys(mae).reduce((a, k) => mae[k] < mae[a] ? k : a, 'naive');
  $('#fc-backtest').innerHTML = '<thead><tr><th>Model</th><th>MAE</th></tr></thead><tbody>' + Object.keys(names).map((k) => `<tr><td>${names[k]}</td><td class="${k === best ? 'win' : ''}">${fmt(mae[k] * 100, 1)} pts</td></tr>`).join('') + '</tbody>';
  $$('#urgent-chips .chip').forEach((c) => c.classList.toggle('on', c.getAttribute('data-bin') === S.fcBin));
}

function renderFcOverall() {
  if (!S.evaluation) return;
  const e = S.evaluation.forecast;
  $('#fc-overall').innerHTML = `All ${S.town.bins.length} bins: seasonal smoothing MAE <b>${fmt(e.mae.seasonal_es * 100, 1)}</b> pts vs naive ${fmt(e.mae.naive * 100, 1)} pts (<b>${fmt(e.seasonal_es_vs_naive_pct, 0)}% lower error</b>); weekday regression ${fmt(e.mae.ols_weekday * 100, 1)} pts. Mean daily fill ${fmt(e.mean_daily_fill * 100, 0)}% of capacity.`;
}

// ------------------------------------------------------------------ segregation tab
const ASK_CHIPS = ['banana peel', 'plastic bottle', 'தேங்காய் ஓடு', 'chips packet', 'battery', 'பால் பாக்கெட்', 'old newspaper', 'sanitary napkin', 'மீன் கழிவு', 'tube light', 'rotten tomato'];

function binIcon(color) {
  return `<svg class="binico" viewBox="0 0 64 72"><rect x="6" y="10" width="52" height="7" rx="3" fill="${color}"/><path d="M10 20h44l-4 46a4 4 0 0 1-4 4H18a4 4 0 0 1-4-4z" fill="${color}"/><rect x="24" y="4" width="16" height="6" rx="2" fill="${color}"/><path d="M24 30v30M32 30v30M40 30v30" stroke="#fff" stroke-width="3" stroke-linecap="round" opacity=".7"/></svg>`;
}

async function classify(item) {
  if (!item || !item.trim()) { toast('Type an item first, e.g. "banana peel"', true); return; }
  try {
    const r = await api('/api/classify', { item });
    const probs = Object.keys(r.probabilities).map((k) => `<div class="prob"><span>${LABEL[k]}</span><span class="trk"><span class="fl" style="display:block;width:${(r.probabilities[k] * 100).toFixed(0)}%;background:${BIN_COL[k]}"></span></span><span class="num">${pc(r.probabilities[k])}</span></div>`).join('');
    const ev = r.evidence.filter((e) => e.weight > 0).slice(0, 3).map((e) => `<span class="chip" style="cursor:default">${esc(e.word)} <b>+${fmt(e.weight, 1)}</b></span>`).join(' ');
    $('#verdict').innerHTML = `<div class="verdict">${binIcon(r.color)}<div>
      <h3>${esc(r.bin)}</h3><div class="ta">${esc(r.bin_ta)}</div>
      <div style="margin-top:6px"><span class="badge">${r.method === 'exact-match' ? 'Rule: exact dictionary match' : 'Naive Bayes'}</span> <span class="badge ${r.unsure ? 'warm' : ''}">confidence ${pc(r.confidence)}</span></div>
      ${r.unsure ? '<p class="small bad-txt" style="margin:6px 0 0">Not sure - best guess shown. Ask your ward volunteer.</p>' : ''}
      <p class="small" style="margin:8px 0 4px">${esc(r.why)}</p>
      ${ev ? `<div class="small muted">Evidence (log-odds vs ${LABEL[r.runner_up]}):</div><div class="chips" style="margin:4px 0 6px">${ev}</div>` : ''}
      ${probs}
      <p class="small muted" style="margin:8px 0 0">Tip: ${esc(r.tip)}</p></div></div>`;
  } catch (e) { toast(e.message, true); }
}

function renderSegForm() {
  $('#rep-ward').innerHTML = S.town.wards.map((w) => `<option value="${w.id}">${w.id} · ${esc(w.name)}</option>`).join('');
  $('#rep-bins').innerHTML = ['wet', 'dry', 'recyclable', 'hazardous'].map((k, i) => `<label><input type="radio" name="bin_used" value="${k}" ${i === 0 ? 'checked' : ''}><span class="sw" style="background:${BIN_COL[k]}"></span>${LABEL[k]}</label>`).join('');
  $('#ask-chips').innerHTML = ASK_CHIPS.map((c) => `<button type="button" class="chip">${esc(c)}</button>`).join('');
  $$('#ask-chips .chip').forEach((c) => c.addEventListener('click', () => { $('#ask-input').value = c.textContent; classify(c.textContent); }));
}

async function loadLeaderboard() {
  try { S.lb = await api('/api/leaderboard'); } catch (e) { toast(e.message, true); return; }
  renderLeaderboard();
}

function renderLeaderboard() {
  const lb = S.lb;
  $('#lb-sub').textContent = `${fmt(lb.total_reports)} reports · ${pc(lb.overall_compliance)} correctly segregated`;
  $('#pts-rule').textContent = `+${lb.rules.correct} correct · +${lb.rules.participation} for reporting`;
  $('#leaderboard').innerHTML = lb.wards.map((w, i) => `<div class="lb-row ${i === 0 ? 'first' : ''}"><span class="lb-rank">${w.rank}</span>
    <div class="name">${esc(w.name)} <span class="badge ${w.compliance < 0.65 ? 'bad' : w.compliance < 0.8 ? 'warm' : ''}">${esc(w.badge)}</span><small>${w.ward} · ${w.participants} households · ${w.reports} reports</small></div>
    <div class="bar-cell"><div class="small muted">compliance ${pc(w.compliance)}</div><div class="bar-track"><div class="bar-fill" style="width:${(w.compliance * 100).toFixed(0)}%"></div></div></div>
    <div class="pts">${fmt(w.score, 0)}<small>${fmt(w.points)} pts</small></div></div>`).join('');
  $('#champions').innerHTML = lb.top_households.map((h, i) => `<li><span>${i + 1}. <b>${esc(h.household)}</b></span><span class="num">${fmt(h.points)} pts</span></li>`).join('');
  $('#feed').innerHTML = lb.recent.map((r) => `<li><span>${esc(r.item)} <span class="muted">→ ${LABEL[r.bin_used]}</span></span><span class="${r.correct ? 'good-txt' : 'bad-txt'}">${r.correct ? '+' + r.points : 'should be ' + LABEL[r.correct_bin]}</span></li>`).join('');
}

async function submitReport(e) {
  e.preventDefault();
  const body = { ward: $('#rep-ward').value, household: $('#rep-hh').value.trim() || undefined, item: $('#rep-item').value.trim(), bin_used: ($('input[name=bin_used]:checked') || {}).value };
  if (!body.item) { toast('Which item was thrown away?', true); return; }
  try {
    const r = await api('/api/report', body);
    S.lb = r.leaderboard;
    renderLeaderboard();
    const ok = r.report.correct;
    $('#rep-result').innerHTML = ok ? `<span class="good-txt">Correct! +${r.report.points} green points for ${esc(r.report.ward)}</span>`
      : `<span class="bad-txt">That goes in: ${esc(r.verdict.bin)}.</span> +${r.report.points} points for reporting.`;
    toast(ok ? `+${r.report.points} green points!` : `Not quite - ${r.verdict.bin}`);
  } catch (err) { toast(err.message, true); }
}

// ------------------------------------------------------------------ impact tab
async function loadEvaluation() {
  try { S.evaluation = await api('/api/evaluation'); } catch (e) { toast(e.message, true); }
  return S.evaluation;
}

async function loadImpact() {
  const q = `diesel=${$('#s-diesel').value}&bins=${$('#s-bins').value}&kmpl=${$('#s-kmpl').value}`;
  try { S.impact = await api('/api/impact?' + q); } catch (e) { toast(e.message, true); return; }
  renderImpact();
  if (!S.evaluation) await loadEvaluation();
  renderEvaluation();
}

function renderImpact() {
  const im = S.impact, a = im.annual;
  $('#imp-sub').textContent = `· ${im.basis_days}-day simulation × 365 days · ${fmt(im.scale_bins)} bins · diesel ${inr(im.diesel_inr_per_l)}/L`;
  const tiles = [
    ['hero', 'Diesel saved / year', compact(a.fuel_saved_l), 'litres', `${fmt(im.pct.fuel, 0)}% less fuel`],
    ['', 'Money saved / year', inr(a.money_saved_inr), '', 'diesel cost only, no wages'],
    ['', 'CO₂ avoided / year', fmt(a.co2_saved_t, 1), 'tonnes', '2.68 kg CO₂ per litre (approx.)'],
    ['', 'Truck distance avoided', compact(a.km_saved), 'km / year', `${fmt(im.pct.km, 0)}% shorter routes`],
    ['', 'Truck-hours freed', compact(a.truck_hours_freed), 'h / year', 'crew time for sweeping & drains'],
    ['', 'Overflow events avoided', compact(a.overflow_events_avoided), 'per year', `${compact(a.spilled_litres_avoided)} L less street spill`]
  ];
  $('#imp-hero').innerHTML = tiles.map(([c, l, v, u, d]) => `<div class="kpi ${c}"><div class="label">${l}</div><div class="value">${v}<small>${u}</small></div><div class="delta">${d}</div></div>`).join('');
  const ft = im.month_totals.fixed, st = im.month_totals.smart;
  $('#month-sub').textContent = `${ft.days} days, same waste, same fleet`;
  const minis = [['Distance', 'km', 'km'], ['Diesel', 'fuel_l', 'L'], ['CO₂', 'co2_kg', 'kg'], ['Overflowing bin-days', 'overflow_bins', '']];
  $('#month-minis').innerHTML = minis.map(([t, k, u]) => {
    const a1 = ft[k], b1 = st[k], mx = Math.max(a1, b1, 1);
    const H = 170, base = 146, sc = (v) => (base - 26) * v / mx;
    const bar = (x, v, col) => { const hgt = sc(v), r = Math.min(4, hgt); return hgt > 0 ? `<path d="M${x} ${base} V${base - hgt + r} Q${x} ${base - hgt} ${x + r} ${base - hgt} H${x + 24 - r} Q${x + 24} ${base - hgt} ${x + 24} ${base - hgt + r} V${base} Z" style="fill:${col}"/>` : ''; };
    const red = a1 ? Math.round(100 * (1 - b1 / a1)) : 0;
    return `<div><h3>${t} <span class="muted small">${red >= 0 ? '−' : '+'}${Math.abs(red)}%</span></h3><svg class="chart" viewBox="0 0 300 ${H}" style="max-height:200px">
      <line x1="20" x2="280" y1="${base}" y2="${base}" style="stroke:var(--axis)"/>
      ${bar(88, a1, 'var(--fixed)')}${bar(188, b1, 'var(--smart)')}
      <text class="val" x="100" y="${base - sc(a1) - 6}" text-anchor="middle">${compact(a1)}</text>
      <text class="val" x="200" y="${base - sc(b1) - 6}" text-anchor="middle">${compact(b1)}</text>
      <text class="axis" x="100" y="${base + 16}" text-anchor="middle">Fixed beat</text><text class="axis" x="200" y="${base + 16}" text-anchor="middle">WasteWise</text></svg></div>`;
  }).join('');
  $('#assume').innerHTML = '<thead><tr><th>Constant</th><th>Value</th><th>Why</th></tr></thead><tbody>' + im.assumptions.map((x) => `<tr><td><code>${x.name}</code></td><td class="num">${x.value} ${esc(x.unit)}</td><td class="muted">${esc(x.note)}</td></tr>`).join('') + '</tbody>';
  $('#formulas').innerHTML = '<h3 style="margin:12px 0 4px">Formulas</h3>' + im.formulas.map((f) => `<div class="formula">${esc(f)}</div>`).join('') +
    '<h3 style="margin:12px 0 4px">Caveats</h3><ul class="small muted" style="margin:0;padding-left:18px">' + im.caveats.map((c) => `<li>${esc(c)}</li>`).join('') + '</ul>';
}

function renderEvaluation() {
  const e = S.evaluation;
  if (!e) return;
  const m = e.month, fc = e.forecast, cl = e.classifier;
  $('#evaluation').innerHTML = `<dl class="stat-list">
    <dt>Distance saved vs fixed beat (${m.days}-day sim)</dt><dd class="good-txt">${fmt(m.savings_pct.km, 1)}%</dd>
    <dt>Diesel &amp; CO₂ saved</dt><dd class="good-txt">${fmt(m.savings_pct.fuel_l, 1)}%</dd>
    <dt>Overflowing bin-days reduced</dt><dd class="good-txt">${fmt(m.savings_pct.overflow_bins, 0)}%</dd>
    <dt>Routing only: Clarke–Wright vs fixed order (same bins)</dt><dd>${fmt(m.routing_only.cw_vs_fixed_pct, 1)}% shorter</dd>
    <dt>2-opt on top of Clarke–Wright</dt><dd>${fmt(m.routing_only.two_opt_extra_pct, 1)}% shorter</dd>
    <dt>Solver time per day (mean / max)</dt><dd>${fmt(m.solver_ms.mean, 2)} / ${fmt(m.solver_ms.max, 2)} ms</dd>
    <dt>Forecast MAE: seasonal smoothing vs naive</dt><dd>${fmt(fc.mae.seasonal_es * 100, 1)} vs ${fmt(fc.mae.naive * 100, 1)} pts</dd>
    <dt>Classifier hold-out accuracy (unseen names)</dt><dd>${pc(cl.accuracy)} <span class="muted small">(${cl.test} items)</span></dd>
  </dl><p class="note">All numbers recomputed live by the Python backend from the deterministic simulation (seed 2026).</p>`;
}

// ------------------------------------------------------------------ tabs & actions
function switchTab(name) {
  $$('.tab').forEach((t) => t.setAttribute('aria-selected', String(t.getAttribute('data-tab') === name)));
  $$('.panel').forEach((p) => p.classList.toggle('active', p.id === 'tab-' + name));
  if (name !== 'routes') setPlaying(false);
  if (name === 'sim') renderSim();
  if (name === 'forecast') { renderForecastPicker(); loadForecast(); }
  if (name === 'seg' && !S.lb) loadLeaderboard();
  if (name === 'impact') loadImpact();
}

async function refresh() {
  const [plan, state] = await Promise.all([api('/api/plan'), api('/api/state')]);
  S.plan = plan;
  S.state = state;
  S.t = 0;
  renderRoutesTab();
  if ($('#tab-sim').classList.contains('active')) renderSim();
}

async function withBusy(fn) {
  if (S.busy) return;
  S.busy = true;
  $$('.top-actions .btn, .toolbar .btn').forEach((b) => { b.disabled = true; });
  try { await fn(); } catch (e) { toast(e.message, true); }
  finally {
    S.busy = false;
    $$('.top-actions .btn, .toolbar .btn').forEach((b) => { b.disabled = false; });
  }
}

async function advance(days) {
  await withBusy(async () => {
    setPlaying(false);
    const r = await api('/api/sim/advance', { days });
    await refresh();
    if ($('#tab-forecast').classList.contains('active')) loadForecast();
    const last = r.days[r.days.length - 1];
    const fo = r.days.reduce((a, d) => a + d.kpis.fixed.overflow_bins, 0), so = r.days.reduce((a, d) => a + d.kpis.smart.overflow_bins, 0);
    toast(days === 1
      ? `${last.label}${last.market_day ? ' (market day)' : ''} done - overflowing bins: fixed beat ${fo}, WasteWise ${so}`
      : `${days} days simulated - overflowing bin-days: fixed beat ${fo}, WasteWise ${so}`);
  });
}

async function runDemo() {
  await withBusy(async () => {
    setPlaying(false);
    const r = await api('/api/demo', {});
    S.lb = null;
    S.fcBin = null;
    S.mode = 'smart';
    $$('#mode-seg button').forEach((b) => b.setAttribute('aria-pressed', String(b.getAttribute('data-mode') === 'smart')));
    await refresh();
    switchTab('routes');
    toast(r.message + ' - watch the trucks');
    setPlaying(true);
  });
}

function bind() {
  $$('.tab').forEach((t) => t.addEventListener('click', () => switchTab(t.getAttribute('data-tab'))));
  $('#run-demo').addEventListener('click', runDemo);
  $('#next-day').addEventListener('click', () => advance(1));
  $('#reset').addEventListener('click', () => withBusy(async () => { setPlaying(false); await api('/api/sim/reset', {}); await refresh(); toast('Back to day 0'); }));
  $('#sim-next').addEventListener('click', () => advance(1));
  $('#sim-week').addEventListener('click', () => advance(7));
  $('#sim-month').addEventListener('click', () => {
    const left = 30 - S.state.today.day;
    if (left <= 0) { toast('Already past day 30 - reset to start again'); return; }
    advance(left);
  });
  $('#sim-reset').addEventListener('click', () => withBusy(async () => { await api('/api/sim/reset', {}); await refresh(); renderSim(); toast('Back to day 0'); }));
  $$('#mode-seg button').forEach((b) => b.addEventListener('click', () => {
    S.mode = b.getAttribute('data-mode');
    $$('#mode-seg button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    renderTrucks(); renderLegend(); drawMainMap();
  }));
  $$('#dec-seg button').forEach((b) => b.addEventListener('click', () => {
    S.decFilter = b.getAttribute('data-f');
    $$('#dec-seg button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    renderDecisions();
  }));
  $('#play').addEventListener('click', () => setPlaying(!S.playing));
  $('#scrub').addEventListener('input', (e) => { setPlaying(false); S.t = Number(e.target.value); updatePlayback(); });
  $('#bin-select').addEventListener('change', (e) => { S.fcBin = e.target.value; loadForecast(); });
  $('#ask-form').addEventListener('submit', (e) => { e.preventDefault(); classify($('#ask-input').value); });
  $('#report-form').addEventListener('submit', submitReport);
  ['diesel', 'bins', 'kmpl'].forEach((k) => $('#s-' + k).addEventListener('input', (e) => {
    $('#o-' + k).textContent = k === 'kmpl' ? Number(e.target.value).toFixed(1) : fmt(e.target.value);
    clearTimeout(S.impTimer);
    S.impTimer = setTimeout(loadImpact, 180);
  }));
}

async function init() {
  bind();
  try {
    S.town = await api('/api/town');
    $('#scrub').max = String(S.town.constants.shift_min);
    renderSegForm();
    await refresh();
  } catch (e) {
    toast('Could not load data: ' + e.message, true);
    return;
  }
  // deep links for demos/screenshots: #t=95 (playback minute), #tab=sim
  const h = new URLSearchParams(location.hash.slice(1));
  if (h.get('t')) { S.t = Math.max(0, Math.min(maxT(), Number(h.get('t')) || 0)); updatePlayback(); }
  if (h.get('tab')) switchTab(h.get('tab'));
}

init();
