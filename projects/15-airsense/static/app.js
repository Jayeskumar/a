/* AirSense dashboard - vanilla JS, hand-drawn canvas map and SVG charts. No libraries. */
'use strict';

const $ = (s, r) => (r || document).querySelector(s);
const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
const NS = 'http://www.w3.org/2000/svg';
const sleep = ms => new Promise(r => setTimeout(r, ms));

const S = {
  meta: null, frames: null, sources: null, evalData: null,
  hour: 0, layer: 'aqi', method: 'idw', playing: false, speed: 1, timer: null,
  sel: { type: 'sensor', id: 'S13' }, profile: 'general', sensorId: 'S13', days: 7,
  sensorCache: {}, gridCache: {}, tour: false, healthLoc: 'S13', point: null,
};

// ------------------------------------------------------------------ helpers
function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  if (attrs) for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === 'class') e.className = v; else if (k === 'text') e.textContent = v;
    else if (k === 'html') e.innerHTML = v; else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v);
  }
  for (const k of kids) if (k != null) e.append(k.nodeType ? k : document.createTextNode(k));
  return e;
}
function svg(tag, attrs) {
  const e = document.createElementNS(NS, tag);
  if (attrs) for (const [k, v] of Object.entries(attrs)) if (v != null) e.setAttribute(k, v);
  return e;
}
function esc(s) { return String(s).replace(/ug\/m3/g, 'µg/m³').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
const fmt = (v, d = 0) => (v == null || Number.isNaN(v)) ? '-' : Number(v).toFixed(d);
const sgn = v => (v < 0 ? '- ' : '+ ') + Math.abs(v);
const pct = (v, d = 0) => v == null ? '-' : (v * 100).toFixed(d) + '%';
const cssVar = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

async function api(path, body) {
  const opt = body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
  const r = await fetch(path, opt);
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || ('HTTP ' + r.status));
  return j;
}

function toast(msg, ms = 3800) {
  const t = $('#toast');
  t.textContent = msg; t.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { t.hidden = true; }, ms);
}

// ------------------------------------------------------------------ AQI (mirrors airsense/aqi.py)
function subIndex(p, c) {
  if (c == null) return null;
  const k = S.meta.knots[p];
  if (c >= k[k.length - 1][0]) return 500;
  for (let i = 0; i < k.length - 1; i++) {
    const [b0, i0] = k[i], [b1, i1] = k[i + 1];
    if (c >= b0 && c <= b1) return b1 === b0 ? i0 : i0 + (i1 - i0) * (c - b0) / (b1 - b0);
  }
  return 500;
}
function aqiOf(p25, p10) {
  const a = subIndex('pm25', p25), b = subIndex('pm10', p10);
  if (a == null && b == null) return null;
  return Math.floor(Math.max(a == null ? -1 : a, b == null ? -1 : b) + 0.5);
}
function cat(aqi) {
  const cs = S.meta.categories;
  if (aqi == null) return null;
  for (const c of cs) if (aqi <= c.hi) return c;
  return cs[cs.length - 1];
}
function catChip(aqi, label) {
  const c = cat(aqi);
  if (!c) return el('span', { class: 'cat-chip', style: 'background:var(--surface-2);color:var(--muted)' }, 'no data');
  return el('span', { class: 'cat-chip', style: `background:${c.color};color:${c.ink}` }, label || c.name);
}
const hexRgb = h => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];

// sequential single-hue ramps (light -> dark) for non-AQI layers
const RAMPS = {
  sigma: ['#e3f4f8', '#0891B2', '#0b3b4a'],
  sources: ['#efeafc', '#7a65e0', '#3a2a8f'],
};
function rampColor(name, t) {
  const r = RAMPS[name].map(hexRgb);
  t = Math.max(0, Math.min(1, t));
  const [a, b, u] = t < 0.5 ? [r[0], r[1], t * 2] : [r[1], r[2], (t - 0.5) * 2];
  return [0, 1, 2].map(i => Math.round(a[i] + (b[i] - a[i]) * u));
}

// ------------------------------------------------------------------ boot
async function boot() {
  try {
    await loadAll();
  } catch (e) {
    $('#map-sub').textContent = 'Could not load data: ' + e.message;
    return;
  }
  bindUI();
}

async function loadAll() {
  const [meta, frames, sources] = await Promise.all([api('/api/meta'), api('/api/frames'), api('/api/sources')]);
  S.meta = meta; S.frames = frames; S.sources = sources;
  S.sensorCache = {}; S.gridCache = {}; S.evalData = null;
  S.hour = meta.now;
  S.idx = {}; frames.sensors.forEach((id, i) => { S.idx[id] = i; });
  S.sensorById = {}; meta.sensors.forEach(s => { S.sensorById[s.id] = s; });
  computeStrip();
  initProfiles();
  renderKpis();
  renderEventChips();
  $('#slider').max = meta.hours - 1;
  $('#slider').value = S.hour;
  setupMap();
  renderSensorList();
  renderHealthStatic();
  renderCalcForm();
  setHour(S.hour);
  selectSensor(S.sel.type === 'sensor' ? S.sel.id : 'S13', false);
}

function initProfiles() {
  const sel = $('#profile-select');
  sel.innerHTML = '';
  for (const [k, name] of Object.entries(S.meta.profiles)) sel.append(el('option', { value: k }, name));
  sel.value = S.profile;
  const chips = $('#profile-chips');
  chips.innerHTML = '';
  for (const [k, name] of Object.entries(S.meta.profiles)) {
    chips.append(el('button', { class: 'chip' + (k === S.profile ? ' on' : ''), 'data-p': k, type: 'button', onclick: () => setProfile(k) }, name));
  }
}

function setProfile(p) {
  S.profile = p;
  $('#profile-select').value = p;
  $$('#profile-chips .chip').forEach(c => c.classList.toggle('on', c.dataset.p === p));
  refreshSpot();
  renderHealth();
  renderHealthStatic();
}

// ------------------------------------------------------------------ KPIs
function kpi(label, value, note, chip) {
  const v = el('div', { class: 'k-value' }, value);
  if (chip) v.append(chip);
  return el('div', { class: 'kpi' }, el('div', { class: 'k-label' }, label), v, el('div', { class: 'k-note', title: note }, note));
}

function renderKpis() {
  const t = S.hour, F = S.frames, m = S.meta.metrics;
  const vals = F.aqi[t].filter(v => v != null).sort((a, b) => a - b);
  const med = vals.length ? vals[Math.floor(vals.length / 2)] : null;
  let wi = -1, wv = -1;
  F.aqi[t].forEach((v, i) => { if (v != null && v > wv) { wv = v; wi = i; } });
  const worst = wi >= 0 ? S.sensorById[F.sensors[wi]] : null;
  const ref = F.ref_aqi['REF-A'][t];
  const box = $('#kpis');
  box.innerHTML = '';
  box.append(
    kpi('Town now (median, 1-h)', fmt(med), vals.length ? `range ${vals[0]}-${vals[vals.length - 1]} across ${vals.length} sensors` : 'no data', catChip(med)),
    kpi('Official station (24-h)', fmt(ref), 'REF-A, CPCB method: one number for the whole town', catChip(ref)),
    kpi('Worst spot now', fmt(wv), worst ? worst.name : '-', catChip(wv)),
    kpi('Hidden exposure', fmt(m.hidden_exposure_pct, 0) + '%', 'of unhealthy sensor-hours the single station missed'),
    kpi('Calibration error cut', '\u2212' + fmt(m.calibration_rmse_reduction_pct, 0) + '%', 'PM2.5 RMSE vs reference, raw → calibrated'),
    kpi('Forecast error vs persistence', '\u2212' + fmt(m.forecast_gain_pct, 0) + '%', `MAE ${fmt(m.forecast_mae, 1)} vs ${fmt(m.persistence_mae, 1)} µg/m³ over 24 h`),
  );
}

// ------------------------------------------------------------------ time
function computeStrip() {
  const F = S.frames;
  S.townMedian = F.aqi.map(row => {
    const v = row.filter(x => x != null).sort((a, b) => a - b);
    return v.length ? v[Math.floor(v.length / 2)] : null;
  });
}

function drawStrip() {
  const c = $('#strip');
  const w = c.clientWidth || 600, h = 14, dpr = window.devicePixelRatio || 1;
  c.width = w * dpr; c.height = h * dpr;
  const g = c.getContext('2d');
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  const n = S.townMedian.length;
  for (let i = 0; i < n; i++) {
    const cc = cat(S.townMedian[i]);
    g.fillStyle = cc ? cc.color : '#999';
    g.fillRect(i / n * w, 0, w / n + 0.6, h);
  }
  g.fillStyle = cssVar('--text');
  const x = (S.hour + 0.5) / n * w;
  g.fillRect(x - 1, 0, 2, h);
}

function eventAt(t) {
  return S.meta.events.find(e => t >= e.start_hour && t <= e.end_hour + (e.kind === 'fireworks' ? 6 : 2));
}

function setHour(t) {
  S.hour = Math.max(0, Math.min(S.meta.hours - 1, t));
  $('#slider').value = S.hour;
  $('#time-label').textContent = S.meta.labels[S.hour];
  const [wd, ws] = S.frames.wind[S.hour];
  const rain = S.frames.rain[S.hour];
  const ev = eventAt(S.hour);
  $('#time-extra').textContent = (ev ? ev.name + ' · ' : '') + `wind from ${compass(wd)} ${ws} m/s` + (rain > 0.2 ? ` · rain ${rain} mm/h` : '') + (S.hour === S.meta.now ? ' · latest hour' : '');
  drawWind(wd, ws);
  drawStrip();
  renderKpis();
  drawMap();
  if (!S.playing) { scheduleGrid(); refreshSpot(); }
  else refreshSpotLight();
}

function compass(d) {
  const n = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];
  return n[Math.floor(((d % 360) + 11.25) / 22.5) % 16];
}

function drawWind(dir, speed) {
  const box = $('#wind');
  // arrow points where the wind blows TO
  const to = (dir + 180) % 360;
  box.innerHTML = `<svg viewBox="-16 -16 32 32" aria-hidden="true"><circle r="14" fill="none" stroke="currentColor" stroke-opacity=".3"/>
    <g transform="rotate(${to})"><path d="M0 -11 L5 2 L0 -1 L-5 2 Z" fill="var(--brand)"/><line x1="0" y1="-1" x2="0" y2="10" stroke="var(--brand)" stroke-width="2"/></g></svg>
    <span>Wind from <b>${compass(dir)}</b><br>${speed} m/s</span>`;
}

function renderEventChips() {
  const box = $('#event-chips');
  box.innerHTML = '';
  const seen = new Set();
  const add = (label, h, title) => box.append(el('button', { class: 'chip', type: 'button', title, onclick: () => { stopTour(); pause(); setHour(h); } }, label));
  for (const e of S.meta.events) {
    const peak = e.kind === 'fireworks' ? e.start_hour + 4 : e.kind === 'rain' ? e.start_hour + 8 : e.kind === 'burning' ? e.start_hour + 3 : e.start_hour + 3;
    const day = S.meta.labels[e.start_hour].slice(4, 10);
    const short = { burning: 'Crop burning', fireworks: 'Festival fireworks', rain: 'Rain washout', construction: 'Construction starts' }[e.kind] || e.name;
    const key = e.name + day;
    if (seen.has(key)) continue;
    seen.add(key);
    add(`${short} ${day}`, peak, `${e.name}: jump to ${S.meta.labels[peak]}`);
  }
  add('Now', S.meta.now, 'Latest hour');
}

function play() {
  if (S.playing) return pause();
  S.playing = true;
  $('#play').innerHTML = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 3h3v10H4zM9 3h3v10H9z"/></svg>';
  $('#play').setAttribute('aria-label', 'Pause');
  if (S.hour >= S.meta.hours - 1) setHour(0);
  const tick = () => {
    if (!S.playing) return;
    if (S.hour >= S.meta.hours - 1) { pause(); return; }
    setHour(S.hour + 1);
    S.timer = setTimeout(tick, 260 / S.speed);
  };
  S.timer = setTimeout(tick, 100);
}
function pause() {
  S.playing = false;
  clearTimeout(S.timer);
  $('#play').innerHTML = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 2.5v11l9-5.5z"/></svg>';
  $('#play').setAttribute('aria-label', 'Play');
  scheduleGrid();
  refreshSpot();
}

// ------------------------------------------------------------------ map
const MAP = { nx: 180, ny: 120 };

function setupMap() {
  const c = $('#map');
  MAP.c = c;
  MAP.base = document.createElement('canvas');
  MAP.heat = document.createElement('canvas');
  MAP.heat.width = MAP.nx; MAP.heat.height = MAP.ny;
  if (!MAP.observer) {
    MAP.observer = new ResizeObserver(() => { resizeMap(); drawMap(); drawStrip(); });
    MAP.observer.observe($('#map-wrap'));
  }
  resizeMap();
}

function resizeMap() {
  const wrap = $('#map-wrap');
  const w = wrap.clientWidth, h = wrap.clientHeight;
  if (!w || !h) return;
  const dpr = window.devicePixelRatio || 1;
  MAP.w = w; MAP.h = h; MAP.dpr = dpr;
  MAP.c.width = w * dpr; MAP.c.height = h * dpr;
  MAP.base.width = w * dpr; MAP.base.height = h * dpr;
  drawBase();
}

const kx = x => x / S.meta.map.w_km * MAP.w;
const ky = y => MAP.h - y / S.meta.map.h_km * MAP.h;
const ikx = px => px / MAP.w * S.meta.map.w_km;
const iky = py => (MAP.h - py) / MAP.h * S.meta.map.h_km;

function lm(id) { return S.meta.map.landmarks.find(l => l.id === id); }

function drawBase() {
  const g = MAP.base.getContext('2d');
  g.setTransform(MAP.dpr, 0, 0, MAP.dpr, 0, 0);
  const W = MAP.w, H = MAP.h, km = W / S.meta.map.w_km;
  g.fillStyle = cssVar('--map-bg'); g.fillRect(0, 0, W, H);
  const dark = cssVar('color-scheme') === 'dark' || matchMedia('(prefers-color-scheme: dark)').matches;
  // hill
  const hill = lm('hill');
  const hg = g.createRadialGradient(kx(hill.x), ky(hill.y), 2, kx(hill.x), ky(hill.y), km * 1.1);
  hg.addColorStop(0, dark ? 'rgba(80,140,90,.55)' : 'rgba(120,175,120,.55)'); hg.addColorStop(1, 'rgba(120,175,120,0)');
  g.fillStyle = hg; g.beginPath(); g.ellipse(kx(hill.x), ky(hill.y), km * 1.1, km * 0.8, 0, 0, Math.PI * 2); g.fill();
  // fields (crop rows)
  const f = lm('fields');
  g.save(); g.beginPath(); g.rect(kx(f.x - 0.7), ky(f.y + 1.1), km * 1.6, km * 2.0); g.clip();
  g.fillStyle = dark ? 'rgba(150,140,70,.18)' : 'rgba(190,170,90,.22)'; g.fillRect(0, 0, W, H);
  g.strokeStyle = dark ? 'rgba(170,160,90,.25)' : 'rgba(160,140,60,.25)'; g.lineWidth = 1;
  for (let i = -40; i < 40; i++) { g.beginPath(); g.moveTo(kx(f.x - 0.7) + i * 7, ky(f.y + 1.1)); g.lineTo(kx(f.x - 0.7) + i * 7 + 60, ky(f.y - 0.9)); g.stroke(); }
  g.restore();
  // lake
  g.fillStyle = dark ? 'rgba(70,120,160,.45)' : 'rgba(120,170,215,.55)';
  g.beginPath(); g.ellipse(kx(2.55), ky(4.75), km * 0.42, km * 0.26, -0.3, 0, Math.PI * 2); g.fill();
  // industrial zone
  const ind = lm('industry');
  g.fillStyle = dark ? 'rgba(150,150,160,.18)' : 'rgba(120,120,130,.16)';
  roundRect(g, kx(ind.x - 0.75), ky(ind.y + 0.55), km * 1.5, km * 1.1, 8); g.fill();
  // town centre
  const c = lm('centre');
  g.fillStyle = dark ? 'rgba(200,200,210,.07)' : 'rgba(80,80,90,.07)';
  g.beginPath(); g.arc(kx(c.x), ky(c.y), km * 1.2, 0, Math.PI * 2); g.fill();
  // town roads (decorative)
  const roads = [[[6.0, 4.6], [4.3, 3.1], [3.5, 2.3], [1.2, 2.4]], [[6.0, 4.6], [3.0, 4.2], [0.6, 4.4]], [[6.0, 4.6], [2.2, 5.6], [1.8, 7.4]],
    [[6.0, 4.6], [7.6, 3.4], [9.0, 2.9], [10.6, 1.5]], [[6.0, 4.6], [8.0, 4.4], [10.8, 3.4], [12, 3.1]], [[6.0, 4.6], [6.2, 1.5], [6.3, 0]],
    [[6.0, 4.6], [5.2, 5.8], [4.6, 6.5]], [[6.0, 4.6], [7.0, 6.6], [6.4, 7.8], [6.3, 8]], [[8.0, 4.4], [8.6, 5.75], [10.2, 7.0], [11.4, 8]], [[7.6, 3.4], [8.2, 2.5], [8.4, 0]]];
  for (const [wdt, col] of [[5, cssVar('--map-road-edge')], [3, cssVar('--map-road')]]) {
    g.strokeStyle = col; g.lineWidth = wdt; g.lineCap = 'round'; g.lineJoin = 'round';
    for (const r of roads) { g.beginPath(); r.forEach(([x, y], i) => i ? g.lineTo(kx(x), ky(y)) : g.moveTo(kx(x), ky(y))); g.stroke(); }
  }
  // highway
  for (const [wdt, col] of [[9, dark ? '#4a3f2a' : '#d9b46a'], [5, dark ? '#8a7448' : '#f6dc9a']]) {
    g.strokeStyle = col; g.lineWidth = wdt;
    g.beginPath(); S.meta.map.highway.forEach(([x, y], i) => i ? g.lineTo(kx(x), ky(y)) : g.moveTo(kx(x), ky(y))); g.stroke();
  }
}

function roundRect(g, x, y, w, h, r) {
  g.beginPath(); g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r);
  g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath();
}

function idwAt(pts, x, y) {
  let num = 0, den = 0;
  for (let i = 0; i < pts.length; i++) {
    const dx = pts[i][0] - x, dy = pts[i][1] - y, d2 = dx * dx + dy * dy;
    if (d2 < 1e-9) return pts[i][2];
    const w = 1 / d2;   // IDW power 2, same as airsense/interpolate.py
    num += w * pts[i][2]; den += w;
  }
  return den ? num / den : null;
}

function layerPoints(t) {
  const F = S.frames, a24 = S.layer === 'aqi24';
  const p25 = a24 ? F.pm25_24[t] : F.pm25[t], p10 = a24 ? F.pm10_24[t] : F.pm10[t];
  const P25 = [], P10 = [];
  F.sensors.forEach((id, i) => {
    const s = S.sensorById[id];
    if (p25[i] != null) P25.push([s.x, s.y, p25[i]]);
    if (p10[i] != null) P10.push([s.x, s.y, p10[i]]);
  });
  return { P25, P10 };
}

function sensorAqi(i, t) {
  const F = S.frames;
  if (S.layer === 'aqi24') return F.aqi24[t][i];
  if (S.layer === 'pm25') return F.pm25[t][i] == null ? null : Math.round(subIndex('pm25', F.pm25[t][i]));
  return F.aqi[t][i];
}

function drawHeat() {
  const t = S.hour, nx = MAP.nx, ny = MAP.ny, W = S.meta.map.w_km, H = S.meta.map.h_km;
  const g = MAP.heat.getContext('2d');
  const img = g.createImageData(nx, ny);
  const L = S.layer;
  const key = `${S.method}|${t}`;
  const kg = S.method === 'kriging' && !S.playing ? S.gridCache[key] : null;
  if (L === 'sources') {
    // CWT grid drawn at its own resolution and scaled with bilinear smoothing
    const cw = S.sources.cwt, vals = cw.values, sm = [];
    for (let j = 0; j < cw.ny; j++) {
      sm.push([]);
      for (let i = 0; i < cw.nx; i++) {
        let tot = 0, cnt = 0;
        for (let b = Math.max(0, j - 1); b <= Math.min(cw.ny - 1, j + 1); b++) for (let a = Math.max(0, i - 1); a <= Math.min(cw.nx - 1, i + 1); a++) {
          const v = vals[b][a]; if (v != null) { tot += v; cnt++; }
        }
        sm[j].push(cnt >= 3 ? tot / cnt : null);
      }
    }
    let mx = 0; sm.forEach(r => r.forEach(v => { if (v != null && v > mx) mx = v; }));
    const src = MAP.src || (MAP.src = document.createElement('canvas'));
    src.width = cw.nx; src.height = cw.ny;
    const sg = src.getContext('2d'), sim = sg.createImageData(cw.nx, cw.ny);
    for (let j = 0; j < cw.ny; j++) for (let i = 0; i < cw.nx; i++) {
      const v = sm[j][i], o = ((cw.ny - 1 - j) * cw.nx + i) * 4;
      if (v == null || v <= 0) { sim.data[o + 3] = 0; continue; }
      const [r, gg, b] = rampColor('sources', v / mx);
      sim.data[o] = r; sim.data[o + 1] = gg; sim.data[o + 2] = b; sim.data[o + 3] = Math.round(60 + 170 * Math.min(1, v / mx));
    }
    sg.putImageData(sim, 0, 0);
    return 'src';
  } else if (L === 'sigma') {
    const gr = S.gridCache[`kriging|${t}`];
    if (!gr || !gr.pm25.sd) { g.clearRect(0, 0, nx, ny); return false; }
    const sd = gr.pm25.sd; let mx = 1;
    sd.forEach(r => r.forEach(v => { if (v > mx) mx = v; }));
    S.sigmaMax = mx;
    for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
      const gi = Math.floor(i / nx * gr.pm25.nx), gj = gr.pm25.ny - 1 - Math.floor(j / ny * gr.pm25.ny);
      const v = sd[gj][gi];
      const [r, gg, b] = rampColor('sigma', v / mx);
      const o = (j * nx + i) * 4;
      img.data[o] = r; img.data[o + 1] = gg; img.data[o + 2] = b; img.data[o + 3] = 175;
    }
  } else {
    const { P25, P10 } = layerPoints(t);
    for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
      const x = (i + 0.5) / nx * W, y = H - (j + 0.5) / ny * H;
      let a;
      if (kg && L !== 'aqi24') {
        const gi = Math.floor(i / nx * kg.pm25.nx), gj = kg.pm25.ny - 1 - Math.floor(j / ny * kg.pm25.ny);
        const v25 = kg.pm25.values[gj][gi], v10 = kg.pm10.values[gj][gi];
        a = L === 'pm25' ? subIndex('pm25', v25) : aqiOf(v25, v10);
      } else {
        const v25 = idwAt(P25, x, y), v10 = L === 'pm25' ? null : idwAt(P10, x, y);
        a = L === 'pm25' ? subIndex('pm25', v25) : aqiOf(v25, v10);
      }
      const c = cat(a);
      const o = (j * nx + i) * 4;
      if (!c) { img.data[o + 3] = 0; continue; }
      const [r, gg, b] = c._rgb || (c._rgb = hexRgb(c.color));
      img.data[o] = r; img.data[o + 1] = gg; img.data[o + 2] = b; img.data[o + 3] = 150;
    }
  }
  g.putImageData(img, 0, 0);
  return true;
}

function drawMap() {
  if (!MAP.w || !S.frames) return;
  const g = MAP.c.getContext('2d');
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.drawImage(MAP.base, 0, 0);
  g.setTransform(MAP.dpr, 0, 0, MAP.dpr, 0, 0);
  const ok = drawHeat();
  const dark = matchMedia('(prefers-color-scheme: dark)').matches;
  g.imageSmoothingEnabled = true; g.imageSmoothingQuality = 'high';
  if (ok === 'src') {
    const cw = S.sources.cwt, wpx = cw.nx * cw.cell_km / S.meta.map.w_km * MAP.w, hpx = cw.ny * cw.cell_km / S.meta.map.h_km * MAP.h;
    g.globalAlpha = 0.9;
    g.drawImage(MAP.src, 0, MAP.h - hpx, wpx, hpx);
  } else if (ok) {
    g.globalAlpha = dark ? 0.95 : 0.72;
    g.drawImage(MAP.heat, 0, 0, MAP.w, MAP.h);
  }
  g.globalAlpha = 1;
  drawLabels(g);
  if (S.layer === 'sources') drawHotspots(g);
  drawSensors(g);
  drawScale(g);
  renderMapLegend();
}

function drawLabels(g) {
  const ink = cssVar('--text-2'), halo = cssVar('--map-bg');
  g.font = '600 11px system-ui, sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
  const lab = (txt, x, y) => {
    const hw = g.measureText(txt).width / 2 + 4;
    x = Math.min(MAP.w - hw, Math.max(hw, x));
    g.lineWidth = 3; g.strokeStyle = halo; g.strokeText(txt, x, y); g.fillStyle = ink; g.fillText(txt, x, y);
  };
  const L = S.meta.map.landmarks;
  const pos = { centre: [0.95, -0.9], industry: [0, -0.8], construction: [-0.95, 0.25], fields: [0, 1.3], hill: [0, -0.95] };
  const names = { centre: 'Town centre', industry: 'Industrial cluster', construction: 'Flyover works', fields: 'Farm fields', hill: 'Hill & temple' };
  for (const l of L) {
    if (l.x == null) continue;
    const [dx, dy] = pos[l.id] || [0, 0.4];
    lab(names[l.id] || l.name, kx(l.x + dx), ky(l.y + dy));
  }
  // construction icon
  const c = lm('construction');
  g.fillStyle = '#e8a33a'; g.beginPath(); g.moveTo(kx(c.x) - 6, ky(c.y) + 5); g.lineTo(kx(c.x) + 6, ky(c.y) + 5); g.lineTo(kx(c.x), ky(c.y) - 6); g.closePath(); g.fill();
  // industry chimneys
  const ind = lm('industry');
  g.fillStyle = cssVar('--muted');
  for (const dx of [-0.3, 0, 0.3]) g.fillRect(kx(ind.x + dx) - 3, ky(ind.y) - 8, 6, 14);
  g.save(); g.translate(kx(2.0), ky(7.72)); g.rotate(0.23); lab('Highway', 0, 0); g.restore();
}

function drawHotspots(g) {
  const hs = S.sources.hotspots;
  g.font = '650 11px system-ui, sans-serif'; g.textAlign = 'left'; g.textBaseline = 'middle';
  hs.forEach((h, i) => {
    const x = Math.min(MAP.w - 150, Math.max(14, kx(h.x))), y = Math.min(MAP.h - 14, Math.max(14, ky(h.y)));
    g.strokeStyle = '#3a2a8f'; g.lineWidth = 2; g.beginPath(); g.arc(x, y, 11, 0, Math.PI * 2); g.stroke();
    g.fillStyle = '#3a2a8f'; g.beginPath(); g.arc(x, y, 3, 0, Math.PI * 2); g.fill();
    const txt = `#${i + 1} ${h.landmark_id ? h.likely.split(' (')[0] : 'Unmapped'}`;
    g.lineWidth = 3; g.strokeStyle = cssVar('--surface'); g.strokeText(txt, x + 14, y);
    g.fillStyle = cssVar('--text'); g.fillText(txt, x + 14, y);
  });
  // rose arrows: from each sensor toward its peak wind-from direction
  for (const r of S.sources.roses) {
    if (r.peak_dir == null || !r.peak_ratio || r.peak_ratio < 2) continue;
    const len = Math.min(60, 10 + r.peak_ratio * 6), a = r.peak_dir * Math.PI / 180;
    const x0 = kx(r.x), y0 = ky(r.y), x1 = x0 + Math.sin(a) * len, y1 = y0 - Math.cos(a) * len;
    g.strokeStyle = 'rgba(58,42,143,.75)'; g.lineWidth = 2; g.beginPath(); g.moveTo(x0, y0); g.lineTo(x1, y1); g.stroke();
    const ah = 6, b = Math.atan2(y1 - y0, x1 - x0);
    g.beginPath(); g.moveTo(x1, y1); g.lineTo(x1 - ah * Math.cos(b - 0.5), y1 - ah * Math.sin(b - 0.5)); g.lineTo(x1 - ah * Math.cos(b + 0.5), y1 - ah * Math.sin(b + 0.5)); g.closePath();
    g.fillStyle = 'rgba(58,42,143,.85)'; g.fill();
  }
}

function drawSensors(g) {
  const t = S.hour, F = S.frames, surf = cssVar('--surface');
  // reference stations
  for (const r of S.meta.references) {
    const x = kx(r.x), y = ky(r.y);
    const ra = F.ref_aqi[r.id][t], c = cat(ra);
    g.fillStyle = c ? c.color : '#999'; g.strokeStyle = cssVar('--text'); g.lineWidth = 2;
    g.fillRect(x - 13, y - 13, 26, 26); g.strokeRect(x - 13, y - 13, 26, 26);
  }
  F.sensors.forEach((id, i) => {
    const s = S.sensorById[id], x = kx(s.x), y = ky(s.y);
    const flag = F.flag[t][i], miss = F.missing[t][i];
    const a = sensorAqi(i, t), c = cat(a);
    g.beginPath(); g.arc(x, y, 8.5, 0, Math.PI * 2); g.fillStyle = surf; g.fill();
    g.beginPath(); g.arc(x, y, 6.5, 0, Math.PI * 2);
    if (flag || miss || !c) {
      g.fillStyle = cssVar('--surface-2'); g.fill(); g.strokeStyle = flag ? cssVar('--critical') : cssVar('--muted'); g.lineWidth = 2; g.stroke();
      g.strokeStyle = flag ? cssVar('--critical') : cssVar('--muted'); g.lineWidth = 1.6;
      g.beginPath(); g.moveTo(x - 3, y - 3); g.lineTo(x + 3, y + 3); g.moveTo(x + 3, y - 3); g.lineTo(x - 3, y + 3); g.stroke();
    } else { g.fillStyle = c.color; g.fill(); g.strokeStyle = 'rgba(0,0,0,.35)'; g.lineWidth = 1; g.stroke(); }
    if (S.sel.type === 'sensor' && S.sel.id === id) {
      g.strokeStyle = cssVar('--brand'); g.lineWidth = 3; g.beginPath(); g.arc(x, y, 12, 0, Math.PI * 2); g.stroke();
    }
  });
  if (S.sel.type === 'point' && S.point) {
    const x = kx(S.point.x), y = ky(S.point.y);
    g.fillStyle = cssVar('--brand'); g.strokeStyle = surf; g.lineWidth = 2;
    g.beginPath(); g.moveTo(x, y); g.bezierCurveTo(x - 9, y - 12, x - 8, y - 22, x, y - 22); g.bezierCurveTo(x + 8, y - 22, x + 9, y - 12, x, y); g.fill(); g.stroke();
    g.fillStyle = surf; g.beginPath(); g.arc(x, y - 15, 3, 0, Math.PI * 2); g.fill();
  }
}

function drawScale(g) {
  const km = MAP.w / S.meta.map.w_km, x0 = MAP.w - 14 - 2 * km, y0 = MAP.h - 16;
  g.strokeStyle = cssVar('--text-2'); g.lineWidth = 2;
  g.beginPath(); g.moveTo(x0, y0 - 4); g.lineTo(x0, y0); g.lineTo(x0 + 2 * km, y0); g.lineTo(x0 + 2 * km, y0 - 4); g.stroke();
  g.font = '11px system-ui, sans-serif'; g.fillStyle = cssVar('--text-2'); g.textAlign = 'center'; g.textBaseline = 'bottom';
  g.fillText('2 km', x0 + km, y0 - 3);
}

function renderMapLegend() {
  const box = $('#map-legend');
  const L = S.layer;
  let html = '';
  if (L === 'sigma') {
    html = `<span class="ltitle">Kriging std. dev. PM2.5</span><span class="lrow">0 <i class="ramp" style="background:linear-gradient(90deg,${RAMPS.sigma.join(',')})"></i> ${fmt(S.sigmaMax || 0)} µg/m³</span><span class="lrow muted">higher far from sensors</span>`;
  } else if (L === 'sources') {
    html = `<span class="ltitle">Upwind excess (CWT)</span><span class="lrow">low <i class="ramp" style="background:linear-gradient(90deg,${RAMPS.sources.join(',')})"></i> high</span><span class="lrow muted">arrows: each sensor's dirtiest wind direction</span>`;
  } else {
    const title = L === 'aqi24' ? 'AQI 24-h (CPCB)' : L === 'pm25' ? 'PM2.5 sub-index' : 'AQI 1-h';
    html = `<span class="ltitle">${title}</span>` + S.meta.categories.map(c => `<span class="lrow" title="AQI ${c.lo}-${c.hi}"><i class="sw" style="background:${c.color}"></i>${c.name}</span>`).join('');
    html += `<span class="lrow muted">&#9632; reference &middot; &#10005; flagged</span>`;
  }
  box.innerHTML = html;
}

function hitSensor(px, py) {
  let best = null, bd = 14;
  for (const s of S.meta.sensors) {
    const d = Math.hypot(kx(s.x) - px, ky(s.y) - py);
    if (d < bd) { bd = d; best = s; }
  }
  return best;
}

function bindMap() {
  const c = $('#map'), tip = $('#map-tip');
  c.addEventListener('mousemove', ev => {
    const r = c.getBoundingClientRect(), px = ev.clientX - r.left, py = ev.clientY - r.top;
    const s = hitSensor(px, py), t = S.hour, F = S.frames;
    let html;
    if (s) {
      const i = S.idx[s.id], a = F.aqi[t][i], fl = F.flag[t][i];
      const fn = ['', 'stuck reading', 'spike', 'drift - needs re-calibration'][fl];
      html = `<b>${esc(s.id)} · ${esc(s.name)}</b><br>AQI ${fmt(a)} ${a != null ? '(' + cat(a).name + ')' : ''}<br>PM2.5 ${fmt(F.pm25[t][i], 1)} · PM10 ${fmt(F.pm10[t][i], 1)} µg/m³` +
        (fl ? `<br><span class="bad">Flagged: ${fn}</span>` : '') + (F.missing[t][i] ? '<br><span class="muted">offline this hour</span>' : '');
    } else {
      const x = ikx(px), y = iky(py), { P25, P10 } = layerPoints(t);
      const v25 = idwAt(P25, x, y), v10 = idwAt(P10, x, y), a = aqiOf(v25, v10);
      html = `<b>${x.toFixed(1)} km E, ${y.toFixed(1)} km N</b><br>~AQI ${fmt(a)} (IDW) · PM2.5 ${fmt(v25, 0)}<br><span class="muted">Click for kriging estimate &plusmn; uncertainty</span>`;
    }
    tip.innerHTML = html; tip.hidden = false;
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    tip.style.left = Math.min(px + 14, MAP.w - tw - 6) + 'px';
    tip.style.top = Math.max(6, Math.min(py + 14, MAP.h - th - 6)) + 'px';
  });
  c.addEventListener('mouseleave', () => { tip.hidden = true; });
  c.addEventListener('click', ev => {
    const r = c.getBoundingClientRect(), px = ev.clientX - r.left, py = ev.clientY - r.top;
    const s = hitSensor(px, py);
    if (s) selectSensor(s.id, true);
    else selectPoint(ikx(px), iky(py));
  });
}

// kriging grids are fetched for paused frames only
function scheduleGrid() {
  clearTimeout(scheduleGrid._t);
  const need = S.method === 'kriging' || S.layer === 'sigma';
  if (!need) return;
  scheduleGrid._t = setTimeout(async () => {
    const t = S.hour, key = `kriging|${t}`;
    if (!S.gridCache[key]) {
      try {
        const [a, b] = await Promise.all([api(`/api/grid?hour=${t}&method=kriging&field=pm25&nx=48&ny=32`),
          api(`/api/grid?hour=${t}&method=kriging&field=pm10&nx=48&ny=32`)]);
        S.gridCache[key] = { pm25: a, pm10: b };
      } catch (e) { toast('Kriging grid failed: ' + e.message); return; }
    }
    if (S.hour === t && !S.playing) drawMap();
  }, 120);
}

// ------------------------------------------------------------------ spot panel
function selectSensor(id, refresh = true) {
  S.sel = { type: 'sensor', id };
  S.sensorId = id;
  S.healthLoc = id;
  drawMap();
  if (refresh) refreshSpot();
  renderSensorList();
}

function selectPoint(x, y) {
  S.sel = { type: 'point' };
  S.point = { x: Math.round(x * 100) / 100, y: Math.round(y * 100) / 100 };
  S.healthLoc = 'point';
  drawMap();
  refreshSpot();
  renderHealthLocations();
}

async function getSensor(id) {
  if (!S.sensorCache[id]) S.sensorCache[id] = await api('/api/sensor?id=' + encodeURIComponent(id));
  return S.sensorCache[id];
}

function gauge(box, aqi, lo, hi) {
  const cs = S.meta.categories, R = 70, r0 = 52, cx = 85, cy = 82;
  const ang = v => Math.PI * (1 - Math.min(500, Math.max(0, v)) / 500);
  const pt = (a, rr) => [cx + rr * Math.cos(a), cy - rr * Math.sin(a)];
  const s = svg('svg', { viewBox: '0 0 170 102', role: 'img', 'aria-label': `AQI gauge ${aqi == null ? 'no data' : aqi}` });
  for (const c of cs) {
    const a0 = ang(c.lo === 0 ? 0 : c.lo - 1) - 0.012, a1 = ang(c.hi) + 0.012;
    const [x0, y0] = pt(a0, R), [x1, y1] = pt(a1, R), [x2, y2] = pt(a1, r0), [x3, y3] = pt(a0, r0);
    const large = (a0 - a1) > Math.PI ? 1 : 0;
    s.append(svg('path', { d: `M${x0} ${y0} A${R} ${R} 0 ${large} 1 ${x1} ${y1} L${x2} ${y2} A${r0} ${r0} 0 ${large} 0 ${x3} ${y3}Z`, fill: c.color, opacity: aqi == null || cat(aqi) === c ? 1 : 0.35 }));
  }
  if (lo != null && hi != null && aqi != null) {
    const [ax, ay] = pt(ang(lo), R + 5), [bx, by] = pt(ang(hi), R + 5);
    s.append(svg('path', { d: `M${ax} ${ay} A${R + 5} ${R + 5} 0 0 1 ${bx} ${by}`, fill: 'none', stroke: 'var(--text-2)', 'stroke-width': 2, 'stroke-linecap': 'round' }));
  }
  if (aqi != null) {
    const a = ang(aqi), [x0, y0] = pt(a, r0 - 9), [x1, y1] = pt(a, R + 1);
    s.append(svg('line', { x1: x0, y1: y0, x2: x1, y2: y1, stroke: 'var(--surface)', 'stroke-width': 6, 'stroke-linecap': 'round' }));
    s.append(svg('line', { x1: x0, y1: y0, x2: x1, y2: y1, stroke: 'var(--text)', 'stroke-width': 3, 'stroke-linecap': 'round' }));
  }
  const tv = svg('text', { x: cx, y: cy - 4, 'text-anchor': 'middle', 'font-size': 28, 'font-weight': 700, fill: 'var(--text)' });
  tv.textContent = aqi == null ? '-' : aqi;
  s.append(tv);
  const tc = svg('text', { x: cx, y: cy + 17, 'text-anchor': 'middle', 'font-size': 12, 'font-weight': 650, fill: 'var(--text-2)' });
  tc.textContent = aqi == null ? 'no data' : cat(aqi).name;
  s.append(tc);
  box.innerHTML = ''; box.append(s);
}

function healthBox(box, aqi, adviceObj) {
  const c = cat(aqi);
  if (!c) { box.innerHTML = '<p class="muted">No valid reading for this hour.</p>'; box.style.borderLeftColor = ''; return; }
  box.style.borderLeftColor = c.color;
  const adv = adviceObj ? adviceObj.advice : '';
  const prof = S.meta.profiles[S.profile];
  box.innerHTML = `<p><b>${esc(c.name)}</b> - ${esc(c.health)} <span class="muted">(CPCB)</span></p>` + (adv ? `<p><b>${esc(prof)}:</b> ${esc(adv)}</p>` : '');
}

function profileAdvice(aqi) {
  const c = cat(aqi);
  return c ? S.meta.profileAdvice && S.meta.profileAdvice[S.profile] ? S.meta.profileAdvice[S.profile][c.key] : null : null;
}

let spotSeq = 0;
async function refreshSpot() {
  const seq = ++spotSeq;
  const t = S.hour;
  if (S.sel.type === 'sensor') {
    const id = S.sel.id, s = S.sensorById[id], i = S.idx[id], F = S.frames;
    $('#spot-title').textContent = `${s.id} · ${s.name}`;
    $('#spot-sub').textContent = `${S.meta.labels[t]} · calibrated low-cost sensor`;
    $('#spot-open').hidden = false;
    const a = F.aqi[t][i];
    gauge($('#gauge'), a);
    const fl = F.flag[t][i];
    const p25 = F.pm25[t][i], p10 = F.pm10[t][i];
    const prom = p25 == null ? '-' : (subIndex('pm25', p25) >= subIndex('pm10', p10 || 0) ? 'PM2.5' : 'PM10');
    $('#spot-facts').innerHTML = `<span>PM2.5 <b>${fmt(p25, 1)}</b> µg/m³</span><span>PM10 <b>${fmt(p10, 1)}</b> µg/m³</span>` +
      `<span>Prominent: <b>${prom}</b></span><span>24-h AQI (CPCB): <b>${fmt(F.aqi24[t][i])}</b></span>` +
      (fl ? `<span class="bad">QA flag: ${['', 'stuck', 'spike', 'drift'][fl]} - excluded from map</span>` : '');
    let adv = null;
    try { if (a != null) adv = await api(`/api/advice?aqi=${a}&profile=${S.profile}`); } catch (e) { adv = null; }
    if (seq !== spotSeq) return;
    healthBox($('#spot-health'), a, adv);
    try {
      const d = await getSensor(id);
      if (seq !== spotSeq) return;
      spotWhySensor(d, t);
      spotForecast(d.forecast);
    } catch (e) { $('#spot-why').textContent = e.message; }
  } else {
    const p = S.point;
    $('#spot-title').textContent = 'Your spot';
    $('#spot-sub').textContent = `${p.x.toFixed(2)} km E, ${p.y.toFixed(2)} km N · ${S.meta.labels[t]} · no sensor here`;
    $('#spot-open').hidden = true;
    try {
      const [e, fc] = await Promise.all([api(`/api/estimate?x=${p.x}&y=${p.y}&hour=${t}`), api(`/api/forecast?x=${p.x}&y=${p.y}&profile=${S.profile}`)]);
      if (seq !== spotSeq) return;
      gauge($('#gauge'), e.aqi, e.aqi_lo, e.aqi_hi);
      $('#spot-facts').innerHTML = `<span>PM2.5 <b>${fmt(e.pm25.kriging, 1)}</b> &plusmn; ${fmt(1.645 * e.pm25.sd, 1)}</span><span>PM10 <b>${fmt(e.pm10.kriging, 1)}</b> &plusmn; ${fmt(1.645 * e.pm10.sd, 1)}</span>` +
        `<span>90% interval: AQI <b>${e.aqi_lo}-${e.aqi_hi}</b></span><span>IDW says PM2.5 ${fmt(e.pm25.idw, 1)}</span><span>Prominent: <b>${e.prominent}</b></span>`;
      let adv = null;
      try { adv = await api(`/api/advice?aqi=${e.aqi}&profile=${S.profile}`); } catch (er) { adv = null; }
      if (seq !== spotSeq) return;
      healthBox($('#spot-health'), e.aqi, adv);
      spotWhyPoint(e);
      spotForecast(fc);
      if ($('#tab-health').hidden === false) renderHealth();
    } catch (err) { $('#spot-why').textContent = err.message; }
  }
}

function refreshSpotLight() {
  // cheap update during playback (no network)
  if (S.sel.type !== 'sensor') return;
  const i = S.idx[S.sel.id], t = S.hour, F = S.frames;
  gauge($('#gauge'), F.aqi[t][i]);
  $('#spot-sub').textContent = `${S.meta.labels[t]} · calibrated low-cost sensor`;
}

function spotWhySensor(d, t) {
  const m = d.calibration.pm25, raw = d.raw_pm25[t], rh = d.rh[t], cal = d.cal_pm25[t];
  const box = $('#spot-why');
  if (raw == null || rh == null) { box.innerHTML = '<p class="muted">Sensor offline this hour.</p>'; return; }
  const aw = Math.min(rh, 95) / 100, gf = 1 + m.kappa / 1.65 * aw / (1 - aw);
  const flag = d.flags[t];
  box.innerHTML = `<div class="kv"><span>Raw sensor PM2.5</span><span>${fmt(raw, 1)} µg/m³</span>` +
    `<span>Humidity ${fmt(rh, 0)}%</span><span>inflates optical reading x${gf.toFixed(2)} (kappa ${m.kappa})</span>` +
    `<span>Dry-corrected</span><span>${fmt(raw / gf, 1)} µg/m³</span>` +
    `<span>After regression</span><span><b>${fmt(cal, 1)} µg/m³</b> (b1=${m.coef.PM_dry}, RH ${m.coef.RH}, T ${m.coef.T})</span>` +
    `<span>Official station</span><span>${fmt(d.ref_pm25[t], 1)} µg/m³ at ${esc(d.nearest_reference)}${d.colocated ? ' (co-located)' : ''}</span></div>` +
    (flag ? `<p class="bad">Flagged ${flag}: ${esc((d.events.find(e => t >= e.start_hour && t <= e.end_hour) || {}).reason || '')}</p>` : '');
}

function spotWhyPoint(e) {
  const box = $('#spot-why');
  box.innerHTML = '<p class="muted" style="margin:0 0 4px">Nearest sensors and their IDW weights:</p>' + e.nearest.map(n =>
    `<div class="wrow"><span>${esc(n.id)} ${esc(n.name)} <span class="muted">${n.km} km</span></span><span class="barbox"><span class="bar" style="display:block;width:${Math.round(n.weight * 100)}%"></span></span><span class="num">${fmt(n.pm25, 0)} ug</span></div>`).join('') +
    `<p class="muted" style="margin:6px 0 0">${esc(e.method_note)} Nearest sensor ${e.nearest_km} km away.</p>`;
}

function spotForecast(fc) {
  $('#fc-sub').textContent = `${fc.where} · from ${fc.labels[0]} · ${S.meta.profiles[S.profile]}`;
  aqiBars($('#spot-forecast'), fc, 150);
  runBox($('#spot-run'), fc);
}

function runBox(box, fc) {
  const b = fc.best_run;
  if (!b) { box.innerHTML = 'No daytime hours in the forecast window.'; return; }
  const al = fc.alerts.filter(a => a.level === 'alert');
  box.innerHTML = `Best time for a run: <b>${b.label}</b> (AQI ${b.aqi}, ${b.category}; upper bound ${b.upper}). Avoid <b>${b.worst_label}</b> (AQI ${b.worst_aqi}). ` +
    `<span class="${b.ok_for_profile ? 'ok' : 'bad'}">${esc(b.verdict)}.</span>` +
    (al.length ? `<br><b>Alert:</b> ${esc(al[0].message)}` : '');
}

// ------------------------------------------------------------------ SVG charts
function niceStep(raw) {
  const p = Math.pow(10, Math.floor(Math.log10(raw))), m = raw / p;
  return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 2.5 ? 2.5 : m <= 5 ? 5 : 10) * p;
}
// round axis maximum: a multiple of a 1/2/2.5/5 step, about 4 gridlines
function niceScale(v) {
  if (!(v > 0)) v = 10;
  const step = niceStep(v / 4);
  return { max: step * Math.ceil(v / step - 1e-9), step };
}
function niceMax(v) { return niceScale(v).max; }
function yGrid(s, sc, Y, x0, x1) {
  for (let v = 0; v <= sc.max + 1e-9; v += sc.step) {
    const y = Y(v);
    s.append(svg('line', { x1: x0, x2: x1, y1: y, y2: y, class: v ? 'gridline' : 'axis' }));
    const t = svg('text', { x: x0 - 6, y: y + 4, 'text-anchor': 'end' });
    t.textContent = sc.step < 1 ? v.toFixed(sc.step < 0.1 ? 2 : 1) : String(Math.round(v)); s.append(t);
  }
}

// Plain-language names for the forecast regression features (airsense/forecast.py FEATURES).
const FEATURE_NAMES = { 'a(t)': 'PM2.5 anomaly now', 'a(t-1)': 'anomaly 1 h ago', 'a(t-23)': 'anomaly 23 h ago',
  'ln wind': 'wind speed', 'rain': 'rain now', 'rain 12h': 'rain, last 12 h', 'RH': 'humidity',
  'cos wind': 'wind from N/S', 'sin wind': 'wind from E/W', 'Sunday': 'Sunday' };
function lineChart(box, o) {
  const W = Math.max(320, box.clientWidth || 600), H = o.height || 230;
  const m = { l: 42, r: 12, t: o.yLabel ? 24 : 10, b: 26 };
  const n = o.n;
  let ymax = 0;
  for (const s of o.series) for (const v of s.values) if (v != null && v > ymax) ymax = v;
  if (o.band) for (const v of o.band.hi) if (v != null && v > ymax) ymax = v;
  const sc = niceScale(o.ymax || ymax * 1.02);
  ymax = sc.max;
  const X = i => m.l + (n <= 1 ? 0 : i / (n - 1)) * (W - m.l - m.r);
  const Y = v => H - m.b - v / ymax * (H - m.t - m.b);
  const s = svg('svg', { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img', 'aria-label': o.label || 'chart' });
  for (const sh of o.shades || []) s.append(svg('rect', { x: X(sh.from) - 1, y: m.t, width: Math.max(2, X(sh.to) - X(sh.from) + 2), height: H - m.t - m.b, fill: sh.color }));
  yGrid(s, sc, Y, m.l, W - m.r);
  if (o.yLabel) { const t = svg('text', { x: 2, y: 11, class: 'ylab' }); t.textContent = o.yLabel; s.append(t); }
  for (const [i, lab] of o.xticks || []) {
    const t = svg('text', { x: X(i), y: H - 8, 'text-anchor': 'middle' }); t.textContent = lab; s.append(t);
  }
  for (const th of o.thresholds || []) {
    if (th.v > ymax) continue;
    s.append(svg('line', { x1: m.l, x2: W - m.r, y1: Y(th.v), y2: Y(th.v), stroke: th.color, 'stroke-width': 1.5, opacity: 0.9 }));
    const t = svg('text', { x: W - m.r - 2, y: Y(th.v) - 4, 'text-anchor': 'end' }); t.textContent = th.label; s.append(t);
  }
  if (o.band) {
    let d = '', seg = [];
    const flush = () => {
      if (seg.length > 1) d += 'M' + seg.map(i => `${X(i)} ${Y(o.band.hi[i])}`).join('L') + 'L' + seg.slice().reverse().map(i => `${X(i)} ${Y(o.band.lo[i])}`).join('L') + 'Z';
      seg = [];
    };
    for (let i = 0; i < n; i++) { if (o.band.lo[i] == null || o.band.hi[i] == null) flush(); else seg.push(i); }
    flush();
    s.append(svg('path', { d, fill: o.band.color || 'var(--band)' }));
  }
  for (const se of o.series) {
    let d = '', pen = false;
    se.values.forEach((v, i) => { if (v == null) { pen = false; return; } d += (pen ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(v).toFixed(1); pen = true; });
    s.append(svg('path', { d, fill: 'none', stroke: se.color, 'stroke-width': se.width || 2, 'stroke-dasharray': se.dash || null, 'stroke-linejoin': 'round', 'stroke-linecap': 'round', opacity: se.opacity || 1 }));
    if (se.dots) se.values.forEach((v, i) => { if (v != null) s.append(svg('circle', { cx: X(i), cy: Y(v), r: 4, fill: se.color, stroke: 'var(--surface)', 'stroke-width': 2 })); });
  }
  // hover layer
  const hl = svg('line', { y1: m.t, y2: H - m.b, class: 'hoverline', visibility: 'hidden' });
  s.append(hl);
  const hit = svg('rect', { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: 'transparent' });
  s.append(hit);
  box.innerHTML = '';
  box.style.position = 'relative';
  box.append(s);
  const tip = el('div', { class: 'ctip', hidden: true });
  box.append(tip);
  hit.addEventListener('mousemove', ev => {
    const r = s.getBoundingClientRect(), sc = W / r.width;
    const x = (ev.clientX - r.left) * sc;
    const i = Math.max(0, Math.min(n - 1, Math.round((x - m.l) / (W - m.l - m.r) * (n - 1))));
    hl.setAttribute('x1', X(i)); hl.setAttribute('x2', X(i)); hl.setAttribute('visibility', 'visible');
    tip.innerHTML = `<b>${esc(o.xlabel ? o.xlabel(i) : i)}</b>` + o.series.map(se => `<div class="trow"><span class="dot" style="background:${se.color}"></span>${esc(se.name)}: ${fmt(se.values[i], o.decimals == null ? 1 : o.decimals)}</div>`).join('') +
      (o.band ? `<div class="trow muted">interval ${fmt(o.band.lo[i], 0)}-${fmt(o.band.hi[i], 0)}</div>` : '') + (o.extra ? o.extra(i) : '');
    tip.hidden = false;
    const px = X(i) / sc, tw = tip.offsetWidth;
    tip.style.left = Math.min(Math.max(0, px + 12), r.width - tw - 4) + 'px';
    tip.style.top = '6px';
  });
  hit.addEventListener('mouseleave', () => { tip.hidden = true; hl.setAttribute('visibility', 'hidden'); });
}

function aqiBars(box, fc, H) {
  const W = Math.max(300, box.clientWidth || 380);
  H = H || 200;
  const m = { l: 34, r: 8, t: 22, b: 22 }, n = fc.aqi.length;
  const sc = niceScale(Math.max(...fc.aqi_hi.map(v => v || 0), 60));
  const ymax = sc.max;
  const bw = (W - m.l - m.r) / n;
  const Y = v => H - m.b - v / ymax * (H - m.t - m.b);
  const s = svg('svg', { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img', 'aria-label': '24-hour AQI forecast' });
  yGrid(s, sc, Y, m.l, W - m.r);
  { const t = svg('text', { x: 2, y: 11, class: 'ylab' }); t.textContent = 'AQI (CPCB) · hour of day'; s.append(t); }
  const best = fc.best_run ? fc.best_run.index : -1;
  const thr = S.meta.profileThreshold ? S.meta.profileThreshold[S.profile] : null;
  const tip = el('div', { class: 'ctip', hidden: true });
  fc.aqi.forEach((v, i) => {
    const c = cat(v), x = m.l + i * bw;
    if (i === best) s.append(svg('rect', { x: x - 1, y: m.t, width: bw + 2, height: H - m.t - m.b, fill: 'var(--brand-wash)' }));
    const r = svg('rect', { x: x + 1, y: Y(v), width: Math.max(1, bw - 2), height: Math.max(1, H - m.b - Y(v)), rx: Math.min(4, bw / 3), fill: c ? c.color : '#999' });
    s.append(r);
    if (fc.aqi_lo[i] != null && fc.aqi_hi[i] != null) s.append(svg('line', { x1: x + bw / 2, x2: x + bw / 2, y1: Y(fc.aqi_lo[i]), y2: Y(fc.aqi_hi[i]), stroke: 'var(--text-2)', 'stroke-width': 1.2, opacity: 0.7 }));
    if (i % 3 === 0) { const t = svg('text', { x: x + bw / 2, y: H - 7, 'text-anchor': 'middle' }); t.textContent = fc.labels[i].slice(-5, -3); s.append(t); }
    const hit = svg('rect', { x, y: m.t, width: bw, height: H - m.t - m.b, fill: 'transparent' });
    hit.addEventListener('mousemove', ev => {
      const rr = box.getBoundingClientRect();
      tip.innerHTML = `<b>${esc(fc.labels[i])}</b><div>AQI ${v} (${c ? c.name : '-'})</div><div class="muted">80% interval ${fc.aqi_lo[i]}-${fc.aqi_hi[i]}</div><div class="muted">PM2.5 ${fmt(fc.pm25[i], 1)} µg/m³</div>`;
      tip.hidden = false;
      tip.style.left = Math.min(ev.clientX - rr.left + 10, rr.width - tip.offsetWidth - 4) + 'px'; tip.style.top = '4px';
    });
    hit.addEventListener('mouseleave', () => { tip.hidden = true; });
    s.append(hit);
  });
  if (thr && thr <= ymax) {
    s.append(svg('line', { x1: m.l, x2: W - m.r, y1: Y(thr), y2: Y(thr), stroke: 'var(--critical)', 'stroke-width': 1.5 }));
    const t = svg('text', { x: W - m.r - 2, y: Y(thr) - 4, 'text-anchor': 'end' }); t.textContent = 'alert level'; s.append(t);
  }
  box.innerHTML = ''; box.style.position = 'relative'; box.append(s, tip);
}

function barList(box, rows, max, unit) {
  box.innerHTML = '';
  const wrap = el('div', { class: 'mini-bars' });
  for (const r of rows) {
    wrap.append(el('div', { class: 'mb' }, el('span', { text: r.label }),
      el('span', { class: 'track' }, el('span', { class: 'fill', style: `display:block;width:${Math.max(1, Math.min(100, r.v / max * 100))}%;background:${r.color}` })),
      el('span', { class: 'num', text: fmt(r.v, r.d == null ? 1 : r.d) + (unit || '') })));
  }
  box.append(wrap);
}

function rose(box, r) {
  const sz = 240, c = sz / 2, R = 92;
  const s = svg('svg', { viewBox: `0 0 ${sz} ${sz}`, role: 'img', 'aria-label': 'Pollution rose' });
  const mx = Math.max(1, ...r.sectors.map(x => x.mean_excess || 0));
  for (const f of [0.33, 0.66, 1]) s.append(svg('circle', { cx: c, cy: c, r: R * f, fill: 'none', stroke: 'var(--grid)' }));
  for (const [lab, a] of [['N', 0], ['E', 90], ['S', 180], ['W', 270]]) {
    const rad = a * Math.PI / 180, t = svg('text', { x: c + Math.sin(rad) * (R + 13), y: c - Math.cos(rad) * (R + 13) + 4, 'text-anchor': 'middle', 'font-weight': 650 });
    t.textContent = lab; s.append(t);
  }
  for (const sec of r.sectors) {
    if (!sec.mean_excess) continue;
    const rr = Math.max(3, Math.sqrt(sec.mean_excess / mx) * R);
    const a0 = (sec.dir - 10) * Math.PI / 180, a1 = (sec.dir + 10) * Math.PI / 180;
    const p = `M${c} ${c}L${c + Math.sin(a0) * rr} ${c - Math.cos(a0) * rr}A${rr} ${rr} 0 0 1 ${c + Math.sin(a1) * rr} ${c - Math.cos(a1) * rr}Z`;
    const peak = sec.dir === r.peak_dir;
    const w = svg('path', { d: p, fill: peak ? '#3a2a8f' : 'var(--brand)', opacity: peak ? 0.95 : 0.55, stroke: 'var(--surface)', 'stroke-width': 1 });
    const ti = svg('title'); ti.textContent = `${sec.label}: ${sec.mean_excess} µg/m³ excess over ${sec.hours} h`; w.append(ti);
    s.append(w);
  }
  const t = svg('text', { x: 2, y: 11 }); t.textContent = `outer ring ${fmt(mx, 0)} µg/m³`; s.append(t);
  box.innerHTML = ''; box.append(s);
}

// ------------------------------------------------------------------ sensors tab
function renderSensorList() {
  const box = $('#sensor-list');
  if (!S.frames) return;
  const t = S.meta.now, F = S.frames;
  box.innerHTML = '';
  for (const id of F.sensors) {
    const s = S.sensorById[id], i = S.idx[id], a = F.aqi[t][i], fl = F.flag[t][i];
    const row = el('button', { class: 'srow' + (id === S.sensorId ? ' on' : ''), type: 'button', onclick: () => { selectSensor(id, true); renderSensorDetail(); } },
      el('span', { class: 'sid', text: id }),
      el('span', { class: 'sname' }, s.name, fl ? el('span', { class: 'sflag', text: '  ' + ['', 'stuck', 'spike', 'drift'][fl] }) : null),
      catChip(a, a == null ? 'off' : String(a)));
    box.append(row);
  }
}

async function renderSensorDetail() {
  const id = S.sensorId;
  let d;
  try { d = await getSensor(id); } catch (e) { $('#sd-title').textContent = e.message; return; }
  if (id !== S.sensorId) return;
  const s = d.sensor, n = S.meta.hours, from = Math.max(0, n - S.days * 24);
  $('#sd-title').textContent = `${s.id} · ${s.name}`;
  const ref = S.meta.references.find(r => r.id === d.nearest_reference);
  const km = Math.hypot(ref.x - s.x, ref.y - s.y);
  $('#sd-sub').textContent = `${s.x} km E, ${s.y} km N · neighbours ${S.sensorById[id].neighbours.join(', ')} · ${d.colocated ? 'co-located with ' + ref.id : 'nearest official station ' + ref.id + ' ' + km.toFixed(1) + ' km away'}`;
  const sl = a => a.slice(from);
  const flags = sl(d.flags);
  const shades = [];
  const colors = { stuck: 'var(--flag-stuck)', spike: 'var(--flag-spike)', drift: 'var(--flag-drift)' };
  let st = null;
  flags.forEach((f, i) => {
    if (f && (st == null || flags[i - 1] !== f)) st = i;
    if (f && (i === flags.length - 1 || flags[i + 1] !== f)) { shades.push({ from: st, to: i, color: colors[f] }); st = null; }
  });
  const ticks = [];
  for (let i = 0; i < n - from; i += 24 * (S.days > 7 ? 4 : 1)) ticks.push([i, S.meta.labels[from + i].slice(4, 10)]);
  $('#sd-legend').innerHTML = `<span><i style="background:var(--s2)"></i>Raw sensor</span><span><i style="background:var(--s1)"></i>Calibrated</span>` +
    `<span><i style="background:var(--ref)"></i>${d.colocated ? 'Reference (co-located)' : 'Official station ' + esc(ref.id)}</span>` +
    `<span><i class="box" style="background:var(--flag-spike)"></i>spike</span><span><i class="box" style="background:var(--flag-stuck)"></i>stuck</span><span><i class="box" style="background:var(--flag-drift)"></i>drift</span>`;
  lineChart($('#sd-chart'), {
    n: n - from, height: 250, label: 'PM2.5 time series', yLabel: 'PM2.5 µg/m³',
    series: [{ name: 'Raw', color: 'var(--s2)', values: sl(d.raw_pm25), width: 1.3, opacity: 0.85 },
      { name: d.colocated ? 'Reference' : 'Official station', color: 'var(--ref)', values: sl(d.ref_pm25), width: 1.3, opacity: 0.7 },
      { name: 'Calibrated', color: 'var(--s1)', values: sl(d.cal_pm25), width: 2 }],
    shades, xticks: ticks, xlabel: i => S.meta.labels[from + i], decimals: 1,
    extra: i => { const f = flags[i]; return f ? `<div class="bad">flag: ${f}</div>` : `<div class="muted">RH ${fmt(d.rh[from + i], 0)}%</div>`; },
  });
  const evb = $('#sd-events');
  evb.innerHTML = d.events.length ? '' : '<p class="muted" style="margin:0">No faults flagged on this sensor.</p>';
  for (const e of d.events) evb.append(el('div', { class: 'ev ' + e.type, html: `<b>${e.type}</b> · ${esc(S.meta.labels[e.start_hour])}${e.end_hour !== e.start_hour ? ' to ' + esc(S.meta.labels[e.end_hour]) : ''} - ${esc(e.reason)}` }));
  // calibration card
  const c = d.calibration.pm25, c10 = d.calibration.pm10;
  const cal = $('#sd-cal');
  cal.innerHTML = `<div class="kv"><span>Co-location</span><span>${esc(d.calibration.station)}, ${c.n_train} training hours</span>` +
    `<span>Humidity kappa</span><span>${c.kappa} (PM10 ${c10.kappa})</span>` +
    `<span>Model</span><span>${c.intercept} ${sgn(c.coef.PM_dry)} x PM_dry ${sgn(c.coef.RH)} x RH ${sgn(c.coef.T)} x T</span></div>` +
    `<p class="mini-h" style="margin-top:6px">PM2.5 RMSE on 2 hold-out days</p><div id="sd-cal-bars"></div>` +
    (d.field_validation ? `<p class="hint">Field check vs reference over 4 weeks: raw MAE ${d.field_validation.raw.mae} → calibrated ${d.field_validation.calibrated.mae} µg/m³ (R² ${d.field_validation.calibrated.r2}).</p>` : '');
  const T = c.test, mx = Math.max(T.raw.rmse, T.mlr.rmse, T.hybrid.rmse);
  barList($('#sd-cal-bars'), [{ label: 'Raw', v: T.raw.rmse, color: 'var(--s2)' }, { label: 'MLR only', v: T.mlr.rmse, color: 'var(--s3)' },
    { label: 'Humidity + MLR', v: T.hybrid.rmse, color: 'var(--s1)' }], mx, '');
  rose($('#sd-rose'), d.rose);
  const r = d.rose;
  $('#sd-rose-hint').innerHTML = r.peak_dir == null ? 'Not enough wind data.' :
    `Dirtiest wind: from <b>${r.peak_label}</b> (${r.peak_excess} µg/m³ excess, ${r.peak_ratio}x this sensor's average). ` +
    (r.upwind.length ? 'Upwind: ' + r.upwind.map(u => `<b>${esc(u.name)}</b> (${u.km} km)`).join(', ') + '.' : 'No mapped source upwind - worth a site visit.');
  const fc = d.forecast;
  lineChart($('#sd-fc'), {
    n: 24, height: 170, series: [{ name: 'Forecast', color: 'var(--s1)', values: fc.pm25 }, { name: 'Persistence', color: 'var(--s2)', values: fc.pm25.map(() => fc.persistence_pm25), width: 1.5, dash: '5 4' }],
    band: { lo: fc.pm25_lo, hi: fc.pm25_hi }, xticks: [[0, fc.labels[0].slice(-5)], [8, fc.labels[8].slice(-5)], [16, fc.labels[16].slice(-5)], [23, fc.labels[23].slice(-5)]],
    xlabel: i => fc.labels[i], label: '24 hour PM2.5 forecast', yLabel: 'PM2.5 µg/m³',
  });
  const w = $('#sd-fc-why');
  w.innerHTML = fc.contributions.length ? '<p class="muted" style="margin:6px 0 2px">What moves the next hour (log-anomaly effect):</p>' +
    fc.contributions.slice().sort((a, b) => Math.abs(b.effect) - Math.abs(a.effect)).slice(0, 4).map(x =>
      `<div class="wrow"><span title="${esc(x.feature)}">${esc(FEATURE_NAMES[x.feature] || x.feature)}</span><span class="barbox"><span class="bar" style="display:block;width:${Math.min(100, Math.abs(x.effect) * 200)}%;background:${x.effect >= 0 ? 'var(--s2)' : 'var(--s1)'}"></span></span><span class="num">${x.effect >= 0 ? '+' : ''}${x.effect}</span></div>`).join('')
    : (fc.stale ? '<p class="muted">Sensor flagged or offline at the forecast origin: forecast falls back to its daily profile.</p>' : '');
}

// ------------------------------------------------------------------ health tab
function renderHealthLocations() {
  const sel = $('#health-loc');
  sel.innerHTML = '';
  if (S.point) sel.append(el('option', { value: 'point' }, `My map spot (${S.point.x.toFixed(1)}, ${S.point.y.toFixed(1)} km)`));
  for (const s of S.meta.sensors) sel.append(el('option', { value: s.id }, `${s.id} · ${s.name}`));
  sel.value = S.healthLoc === 'point' && !S.point ? S.sensorId : S.healthLoc;
}

async function renderHealth() {
  const loc = $('#health-loc').value || S.healthLoc;
  let fc;
  try {
    fc = loc === 'point' && S.point ? await api(`/api/forecast?x=${S.point.x}&y=${S.point.y}&profile=${S.profile}`)
      : await api(`/api/forecast?id=${encodeURIComponent(loc)}&profile=${S.profile}`);
  } catch (e) { $('#health-alerts').innerHTML = `<li>${esc(e.message)}</li>`; return; }
  aqiBars($('#health-chart'), fc, 240);
  runBox($('#health-run'), fc);
  const ul = $('#health-alerts');
  ul.innerHTML = '';
  if (!fc.alerts.length) ul.append(el('li', { html: `<b>No alerts</b> for ${esc(S.meta.profiles[S.profile])} in the next 24 h at ${esc(fc.where)}.` }));
  for (const a of fc.alerts) {
    const c = S.meta.categories.find(x => x.name === a.category);
    const li = el('li', { html: `<b>${a.level === 'alert' ? 'Alert' : 'Heads-up'}</b> ${esc(a.message)}<span class="rule">Rule: ${esc(a.rule)}</span>` });
    if (c) li.style.borderLeftColor = c.color;
    ul.append(li);
  }
  healthBox($('#health-now'), fc.aqi[0], fc.advice_next_hour);
}

function renderHealthStatic() {
  if (!S.meta) return;
  renderHealthLocations();
  const tb = $('#cat-table');
  const prof = S.meta.profiles[S.profile];
  tb.innerHTML = `<thead><tr><th>Category</th><th class="num">AQI</th><th>Health impact (CPCB)</th><th>${esc(prof)} - what to do</th></tr></thead>`;
  const body = el('tbody');
  for (const c of S.meta.categories) {
    const adv = S.meta.profileAdvice ? S.meta.profileAdvice[S.profile][c.key] : '';
    body.append(el('tr', null, el('td', null, el('span', { class: 'cat-chip', style: `background:${c.color};color:${c.ink}` }, c.name)), el('td', { class: 'num', text: `${c.lo}-${c.hi}` }), el('td', { text: c.health }), el('td', { text: adv || '' })));
  }
  tb.append(body);
}

// ------------------------------------------------------------------ report tab
async function renderReport() {
  if (!S.evalData) {
    try { S.evalData = await api('/api/evaluation'); } catch (e) { $('#report-kpis').textContent = e.message; return; }
  }
  const E = S.evalData, cal = E.calibration, fe = E.faults, fc = E.forecast, ip = E.interpolation;
  const k = $('#report-kpis');
  k.innerHTML = '';
  k.append(
    kpi('Calibration RMSE', `${cal.pm25.mean.raw.rmse} \u2192 ${cal.pm25.mean.hybrid.rmse}`, `µg/m³ PM2.5, -${cal.pm25.rmse_reduction_pct}% (PM10 -${cal.pm10.rmse_reduction_pct}%)`),
    kpi('Fault detection', `${pct(fe.overall.event_precision)} / ${pct(fe.overall.event_recall)}`, `precision / recall, ${fe.overall.detected} flags vs ${fe.overall.injected} injected`),
    kpi('Forecast MAE (24 h)', fmt(fc.mae.model, 2), `vs persistence ${fc.mae.persistence}, seasonal ${fc.mae.seasonal} µg/m³`),
    kpi('Interpolation MAE', `${fmt(ip.kriging.mae, 2)}`, `kriging vs ${fmt(ip.nearest_ref.mae, 2)} using the one official station`),
    kpi('Forecast interval', `${fc.interval_coverage_80}%`, 'of actuals inside the 80% interval (target 80%)'),
  );
  // calibration grouped bars
  $('#cal-legend').innerHTML = '<span><i class="box" style="background:var(--s2)"></i>Raw</span><span><i class="box" style="background:var(--s3)"></i>MLR only</span><span><i class="box" style="background:var(--s1)"></i>Humidity correction + MLR</span>';
  groupBars($('#cal-chart'), [['PM2.5', cal.pm25.mean], ['PM10', cal.pm10.mean]]);
  const fv = cal.field_validation.map(f => `${f.sensor} vs ${f.reference}: MAE ${f.raw.mae} → ${f.calibrated.mae} µg/m³ (R² ${f.calibrated.r2})`).join('; ');
  $('#cal-notes').innerHTML = `<p><b>Field check (4 weeks, sensors left next to the references):</b> ${esc(fv)}.</p>` +
    `<p><b>All 25 sensors vs synthetic ground truth:</b> MAE ${cal.field_vs_truth_pm25.raw_mae} → ${cal.field_vs_truth_pm25.cal_mae} µg/m³ over ${cal.field_vs_truth_pm25.n} healthy sensor-hours.</p>` +
    `<p class="muted">Per-sensor humidity kappa ranges ${Math.min(...cal.pm25.sensors.map(s => s.kappa))}-${Math.max(...cal.pm25.sensors.map(s => s.kappa))}. MLR alone cannot follow the non-linear humidity growth; the kappa-Koehler step fixes it.</p>`;
  // faults
  const ft = $('#fault-table');
  ft.innerHTML = '<thead><tr><th>Fault</th><th class="num">Injected</th><th class="num">Flagged</th><th class="num">Precision</th><th class="num">Recall</th><th class="num">Hour P / R</th><th>Delay</th></tr></thead>';
  const tb = el('tbody');
  for (const t of ['stuck', 'spike', 'drift']) {
    const r = fe[t];
    tb.append(el('tr', null, el('td', { text: t }), el('td', { class: 'num', text: r.injected }), el('td', { class: 'num', text: r.detected }),
      el('td', { class: 'num', text: pct(r.event_precision) }), el('td', { class: 'num', text: pct(r.event_recall) }),
      el('td', { class: 'num', text: r.hour_precision == null ? '-' : `${pct(r.hour_precision)} / ${pct(r.hour_recall)}` }),
      el('td', { text: r.detection_delay_h ? r.detection_delay_h.map(h => (h / 24).toFixed(0) + ' d').join(', ') : 'next hour' })));
  }
  tb.append(el('tr', { class: 'hl' }, el('td', { html: '<b>overall</b>' }), el('td', { class: 'num', text: fe.overall.injected }), el('td', { class: 'num', text: fe.overall.detected }),
    el('td', { class: 'num', text: pct(fe.overall.event_precision) }), el('td', { class: 'num', text: pct(fe.overall.event_recall) }), el('td'), el('td')));
  ft.append(tb);
  const sw = $('#sweep-table');
  sw.innerHTML = '<thead><tr><th>Spike z threshold</th>' + E.spike_threshold_sweep.map(r => `<th class="num">${r.z}</th>`).join('') + '</tr></thead>';
  sw.append(el('tbody', { html: '<tr><td>Precision</td>' + E.spike_threshold_sweep.map(r => `<td class="num">${pct(r.precision)}</td>`).join('') + '</tr>' +
    '<tr><td>Recall</td>' + E.spike_threshold_sweep.map(r => `<td class="num">${pct(r.recall)}</td>`).join('') + '</tr>' }));
  // forecast by horizon
  $('#fc-eval-sub').textContent = `Rolling-origin back-test: trained on ${fc.train_days} days, ${fc.n_forecasts} forecasts per horizon on the last ${fc.holdout_days} days (every ${fc.origin_step_h} h, all sensors)`;
  $('#fc-legend').innerHTML = '<span><i style="background:var(--s1)"></i>AirSense model</span><span><i style="background:var(--s2)"></i>Persistence</span><span><i style="background:var(--s3)"></i>Same hour yesterday</span>';
  const bh = fc.by_horizon;
  lineChart($('#fc-chart'), {
    n: 24, height: 220, series: [{ name: 'Persistence', color: 'var(--s2)', values: bh.map(r => r.persistence) }, { name: 'Same hour yesterday', color: 'var(--s3)', values: bh.map(r => r.seasonal) },
      { name: 'AirSense', color: 'var(--s1)', values: bh.map(r => r.model), width: 2.5 }],
    xticks: [[0, '1 h'], [5, '6 h'], [11, '12 h'], [17, '18 h'], [23, '24 h']], xlabel: i => `${i + 1} h ahead (MAE µg/m³)`, decimals: 2, label: 'MAE by horizon', yLabel: 'MAE, PM2.5 µg/m³',
  });
  // interpolation
  const it = $('#interp-table');
  const names = { idw1: 'IDW, p = 1', idw2: 'IDW, p = 2 (map)', idw3: 'IDW, p = 3', kriging: 'Ordinary kriging', nearest_ref: 'One official station (today)' };
  const best = Math.min(...Object.keys(names).map(k2 => ip[k2].mae));
  it.innerHTML = '<thead><tr><th>Method</th><th class="num">MAE</th><th class="num">RMSE</th><th class="num">R&sup2;</th><th class="num">Category right</th></tr></thead>';
  const ib = el('tbody');
  for (const [k2, nm] of Object.entries(names)) {
    const r = ip[k2];
    ib.append(el('tr', { class: r.mae === best ? 'hl' : null }, el('td', { text: nm }), el('td', { class: 'num', text: fmt(r.mae, 2) }), el('td', { class: 'num', text: fmt(r.rmse, 2) }),
      el('td', { class: 'num', text: fmt(r.r2, 3) }), el('td', { class: 'num', text: pct(r.category_accuracy, 1) })));
  }
  it.append(ib);
  const v = E.variogram, bins = v.bins, hmax = bins[bins.length - 1].h;
  const curve = bins.map(b => v.model.nugget + v.model.psill * (1 - Math.exp(-b.h / v.model.range)));
  lineChart($('#vario-chart'), {
    n: bins.length, height: 160, series: [{ name: 'Empirical', color: 'var(--s2)', values: bins.map(b => b.gamma), width: 0.01, dots: true }, { name: 'Fitted exponential', color: 'var(--s1)', values: curve }],
    xticks: bins.filter((b, i) => i % 2 === 0).map((b, i) => [i * 2, b.h.toFixed(1) + ' km']), xlabel: i => `lag ${bins[i].h.toFixed(2)} km, ${bins[i].n} pairs`, decimals: 3, label: 'Variogram', yLabel: 'semivariance γ(h)',
  });
  // fault list
  const fl = $('#fault-list');
  fl.innerHTML = '';
  const fv2 = await api('/api/faults');
  for (const e of fv2.events) {
    fl.append(el('li', { html: `<b>${esc(e.sensor)} ${e.type}</b> · ${esc(S.meta.labels[e.start_hour])} <span class="${e.matches_injected ? 'ok' : 'bad'}">${e.matches_injected ? 'matches injected fault' : 'false alarm'}</span><span class="rule">${esc(e.reason)}</span>` }));
  }
  // hotspots
  const ht = $('#hot-table');
  ht.innerHTML = '<thead><tr><th>#</th><th>Hotspot (km E, N)</th><th>Likely source</th><th class="num">Distance</th></tr></thead>';
  const hb = el('tbody');
  E.hotspots.forEach((h, i) => hb.append(el('tr', null, el('td', { text: i + 1 }), el('td', { text: `${h.x}, ${h.y}` }), el('td', { text: h.likely }), el('td', { class: 'num', text: h.landmark_km == null ? '-' : h.landmark_km + ' km' }))));
  ht.append(hb);
  const H = E.hidden_exposure;
  $('#hidden-box').innerHTML = `<p><b>Hidden exposure:</b> ${H.missed_by_station} of ${H.unhealthy_sensor_hours} unhealthy sensor-hours (${H.missed_pct}%) happened while the single official station read 100 or less. Worst: ` +
    H.top.slice(0, 3).map(t2 => `${esc(t2.name)} (${t2.missed_by_station} h)`).join(', ') + '.</p>';
  const tm = E.timings_ms;
  $('#timing-box').innerHTML = `<p class="muted">Full pipeline on this laptop: ${E.compute_ms} ms (calibration ${tm.calibration}, QA ${tm.fault_detection}, AQI ${tm.aqi}, interpolation ${tm.interpolation}, forecast ${tm.forecast}, sources ${tm.sources} ms). Pure Python, no libraries.</p>`;
}

function groupBars(box, groups) {
  const W = Math.max(320, box.clientWidth || 500), H = 210, m = { l: 40, r: 10, t: 14, b: 26 };
  const keys = [['raw', 'var(--s2)', 'Raw'], ['mlr', 'var(--s3)', 'MLR only'], ['hybrid', 'var(--s1)', 'Humidity + MLR']];
  const sc = niceScale(Math.max(...groups.flatMap(g => keys.map(k2 => g[1][k2[0]].rmse))) * 1.08);
  const ymax = sc.max;
  const Y = v => H - m.b - v / ymax * (H - m.t - m.b);
  const s = svg('svg', { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img', 'aria-label': 'Calibration RMSE' });
  yGrid(s, sc, Y, m.l, W - m.r);
  const gw = (W - m.l - m.r) / groups.length, bw = Math.min(46, gw / 4.5);
  groups.forEach(([name, g], gi) => {
    const x0 = m.l + gi * gw + gw / 2 - (keys.length * (bw + 2)) / 2;
    keys.forEach(([k2, col, lab], ki) => {
      const v = g[k2].rmse, x = x0 + ki * (bw + 2);
      s.append(svg('rect', { x, y: Y(v), width: bw, height: H - m.b - Y(v), fill: col, rx: 4 }));
      const t = svg('text', { x: x + bw / 2, y: Y(v) - 4, 'text-anchor': 'middle', fill: 'var(--text)' }); t.textContent = fmt(v, 1); s.append(t);
      const ti = svg('title'); ti.textContent = `${name} ${lab}: RMSE ${v} µg/m³`; s.lastChild.append(ti);
    });
    const t = svg('text', { x: m.l + gi * gw + gw / 2, y: H - 8, 'text-anchor': 'middle', 'font-weight': 650 }); t.textContent = name + ' RMSE (µg/m³)'; s.append(t);
  });
  box.innerHTML = ''; box.append(s);
}

// ------------------------------------------------------------------ calculator tab
const CALC_EXAMPLES = {
  'Clean morning': { pm25: 22, pm10: 45, no2: 18, so2: 6, co: 0.5, o3: 30, nh3: 15 },
  'Highway evening': { pm25: 84, pm10: 160, no2: 92, so2: 12, co: 2.4, o3: 40, nh3: 20 },
  'Festival night': { pm25: 255, pm10: 340, no2: 60, so2: 85, co: 2.0, o3: 25, nh3: 22 },
  'PM2.5 only (invalid)': { pm25: 75 },
};

function renderCalcForm() {
  const f = $('#calc-form');
  f.innerHTML = '';
  const units = { pm25: ['PM2.5', 'µg/m³, 24-h'], pm10: ['PM10', 'µg/m³, 24-h'], no2: ['NO2', 'µg/m³, 24-h'], so2: ['SO2', 'µg/m³, 24-h'], co: ['CO', 'mg/m³, 8-h'], o3: ['O3', 'µg/m³, 8-h'], nh3: ['NH3', 'µg/m³, 24-h'] };
  for (const [k, [nm, u]] of Object.entries(units)) {
    f.append(el('label', null, el('span', null, nm + ' ', el('small', { text: u })), el('input', { type: 'number', min: 0, step: 'any', name: k, inputmode: 'decimal', placeholder: 'not measured' })));
  }
  const ex = $('#calc-examples');
  ex.innerHTML = '';
  for (const name of Object.keys(CALC_EXAMPLES)) ex.append(el('button', { class: 'chip', type: 'button', onclick: () => { fillCalc(CALC_EXAMPLES[name]); computeCalc(); } }, name));
  const bp = $('#bp-table');
  $('#bp-source').textContent = 'Source: ' + S.meta.aqi_source + '. Concentrations in µg/m³ (CO in mg/m³). Averaging: 24-h, except CO and O3 (8-h). Severe upper bounds are an extrapolation for the formula only.';
  const bpData = S.meta.breakpoints;
  if (bpData) {
    const order = ['pm25', 'pm10', 'no2', 'so2', 'co', 'o3', 'nh3'];
    bp.innerHTML = '<thead><tr><th>Category</th><th class="num">AQI</th>' + order.map(p => `<th class="num">${S.meta.pollutants[p][0]}</th>`).join('') + '</tr></thead>';
    const tb = el('tbody');
    S.meta.categories.forEach((c, i) => {
      tb.append(el('tr', { html: `<td><span class="cat-chip" style="background:${c.color};color:${c.ink}">${c.name}</span></td><td class="num">${c.lo}-${c.hi}</td>` +
        order.map(p => { const r = bpData[p][i]; return `<td class="num">${i === 5 ? '&gt;' + r[0] : r[0] + '-' + r[1]}</td>`; }).join('') }));
    });
    bp.append(tb);
  }
  if (!S.calcInit) { fillCalc(CALC_EXAMPLES['Highway evening']); S.calcInit = true; }
}

function fillCalc(v) {
  for (const inp of $$('#calc-form input')) inp.value = v[inp.name] != null ? v[inp.name] : '';
}

async function computeCalc() {
  const body = {};
  for (const inp of $$('#calc-form input')) if (inp.value !== '') body[inp.name] = Number(inp.value);
  body.profile = S.profile;
  let r;
  try { r = await api('/api/aqi', body); } catch (e) { $('#calc-facts').innerHTML = `<span class="bad">${esc(e.message)}</span>`; return; }
  gauge($('#calc-gauge'), r.aqi);
  const pn = p => S.meta.pollutants[p][0];
  $('#calc-facts').innerHTML = r.aqi == null ? '<span>No data entered.</span>' :
    `<span>AQI <b>${r.aqi}</b> · ${r.category}</span><span>Prominent: <b>${r.prominent.map(pn).join(', ')}</b></span>` +
    `<span class="${r.valid ? 'ok' : 'bad'}">${r.valid ? 'Valid AQI' : 'Not a valid AQI'}: ${esc(r.reason)}</span>`;
  const rows = Object.entries(r.sub_indices).sort((a, b) => b[1] - a[1]).map(([p, v]) => ({ label: pn(p), v, d: 0, color: (cat(Math.round(v)) || {}).color || '#999' }));
  barList($('#calc-bars'), rows, 500, '');
  const why = Object.entries(r.rows || {}).map(([p, row]) => `${pn(p)} ${body[p]} falls in ${row.c_lo}-${row.c_hi} → ${row.i_lo}-${row.i_hi}`).join('; ');
  healthBox($('#calc-health'), r.aqi, r.advice);
  if (r.aqi != null) $('#calc-health').append(el('p', { class: 'muted', text: 'Linear interpolation: ' + why + '.' }));
}

// ------------------------------------------------------------------ demo tour
async function runDemo() {
  const btn = $('#run-demo');
  btn.disabled = true;
  pause();
  try {
    const r = await api('/api/demo/reset', {});
    toast(`${r.message} in ${r.compute_ms} ms`);
    const keep = S.sel;
    await loadAll();
    S.sel = keep;
  } catch (e) { toast('Demo reset failed: ' + e.message); btn.disabled = false; return; }
  btn.disabled = false;
  switchTab('map');
  S.tour = true;
  const fest = S.meta.events.find(e => e.kind === 'fireworks');
  const rain = S.meta.events.find(e => e.kind === 'rain' && e.end_hour - e.start_hour > 20) || S.meta.events.find(e => e.kind === 'rain');
  const steps = [
    async () => { setLayer('aqi'); selectSensor('S02', false); setHour(fest.start_hour - 2); toast('Festival night: watch fireworks smoke build over the town centre...'); await playFor(14, 3); },
    async () => { toast('Peak: hourly AQI turns Severe near the bus stand while the edges stay Poor. One station cannot show this gradient.', 4200); await sleep(3800); },
    async () => { setHour(rain.start_hour + 6); selectSensor('S01', true); toast('Monsoon rain washes PM out. Raw sensors over-read in humid air; calibration (gauge) follows the reference.', 4500); await sleep(4200); },
    async () => { setLayer('sources'); toast('Source hints: upwind rays from all sensors pin the industrial cluster and the highway.', 4200); await sleep(4000); },
    async () => { setLayer('aqi'); setHour(S.meta.now); selectSensor('S13', true); toast('Now: Workshop Row by the highway. The forecast panel shows the best hour for a run tomorrow.', 4500); },
  ];
  for (const st of steps) { if (!S.tour) break; await st(); }
  S.tour = false;
}
async function playFor(hours, speed) {
  const end = Math.min(S.meta.hours - 1, S.hour + hours);
  while (S.tour && S.hour < end) { S.playing = true; setHour(S.hour + 1); await sleep(300 / speed); }
  S.playing = false;
  if (S.tour) { scheduleGrid(); refreshSpot(); }
}
function stopTour() { S.tour = false; }

// ------------------------------------------------------------------ tabs + UI
function switchTab(name) {
  for (const t of $$('.tab')) t.setAttribute('aria-selected', String(t.dataset.tab === name));
  for (const p of $$('.panel')) p.hidden = p.id !== 'tab-' + name;
  if (name === 'map') { resizeMap(); drawMap(); drawStrip(); }
  if (name === 'sensor') { renderSensorList(); renderSensorDetail(); }
  if (name === 'health') { renderHealthLocations(); renderHealth(); }
  if (name === 'report') renderReport();
  if (name === 'calc') computeCalc();
  try { localStorage.setItem('airsense-tab', name); } catch (e) { /* storage unavailable */ }
}

function setLayer(l) {
  S.layer = l;
  $$('#layer-seg button').forEach(b => b.classList.toggle('on', b.dataset.layer === l));
  const sub = {
    aqi: 'Hourly AQI from calibrated sensors (indicative: CPCB uses 24-h averages). Click anywhere for an estimate with uncertainty.',
    aqi24: '24-hour average AQI, CPCB method (PM from sensors, gases from the nearest reference station).',
    pm25: 'PM2.5 sub-index only. Compare with AQI 1-h: construction dust is a PM10 problem.',
    sigma: 'Kriging standard deviation: how unsure the map is. Lowest at sensors, highest in the gaps.',
    sources: 'Where polluted air comes from: concentration-weighted upwind rays (all 4 weeks) and each sensor\'s dirtiest wind direction.',
  }[l];
  $('#map-sub').textContent = sub;
  scheduleGrid();
  drawMap();
}

function bindUI() {
  for (const t of $$('.tab')) t.addEventListener('click', () => switchTab(t.dataset.tab));
  $$('#layer-seg button').forEach(b => b.addEventListener('click', () => { stopTour(); setLayer(b.dataset.layer); }));
  $$('#method-seg button').forEach(b => b.addEventListener('click', () => {
    S.method = b.dataset.method;
    $$('#method-seg button').forEach(x => x.classList.toggle('on', x === b));
    if (S.method === 'kriging') toast('Kriging is computed on the server for paused frames; playback uses IDW.');
    scheduleGrid(); drawMap();
  }));
  $$('#speed-seg button').forEach(b => b.addEventListener('click', () => { S.speed = Number(b.dataset.speed); $$('#speed-seg button').forEach(x => x.classList.toggle('on', x === b)); }));
  $$('#range-seg button').forEach(b => b.addEventListener('click', () => { S.days = Number(b.dataset.days); $$('#range-seg button').forEach(x => x.classList.toggle('on', x === b)); renderSensorDetail(); }));
  $('#slider').addEventListener('input', e => { stopTour(); if (S.playing) pause(); setHour(Number(e.target.value)); });
  $('#play').addEventListener('click', () => { stopTour(); play(); });
  $('#profile-select').addEventListener('change', e => setProfile(e.target.value));
  $('#health-loc').addEventListener('change', e => { S.healthLoc = e.target.value; renderHealth(); });
  $('#spot-open').addEventListener('click', () => switchTab('sensor'));
  $('#run-demo').addEventListener('click', runDemo);
  $('#calc-go').addEventListener('click', computeCalc);
  $('#calc-clear').addEventListener('click', () => { fillCalc({}); computeCalc(); });
  $('#calc-form').addEventListener('submit', e => { e.preventDefault(); computeCalc(); });
  $('#calc-form').addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); computeCalc(); } });
  bindMap();
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { drawBase(); drawMap(); });
  let tab = null;
  try { tab = localStorage.getItem('airsense-tab'); } catch (e) { tab = null; }
  if (tab && tab !== 'map' && $('#tab-' + tab)) switchTab(tab);
}

boot();
