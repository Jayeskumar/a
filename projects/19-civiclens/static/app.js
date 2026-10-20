"use strict";
/* CivicLens front-end: vanilla JS, hand-drawn SVG and canvas charts, no libraries. */

const $ = (s, el) => (el || document).querySelector(s);
const $$ = (s, el) => Array.from((el || document).querySelectorAll(s));
const SVGNS = "http://www.w3.org/2000/svg";

const S = {
  town: null, summary: null, models: null, samples: [], loc: null, tab: "triage",
  rendered: {}, demoRunning: false, lastResult: null, mapData: null, hot: null, heat: null,
  sla: null, risk: null, wards: null, topics: null, emWeek: null,
};
const DEPT_SHORT = { ROADS: "Roads", SANITATION: "Sanitation", STREETLIGHT: "Streetlights", WATER: "Water",
  DRAINAGE: "Drainage", ANIMAL: "Animals", HOSTEL: "Hostel", OTHER: "General" };
const LANG = { en: "English", ta: "Tamil", tg: "Tanglish" };
const feat = (f) => f.replace("=", " ");
const CODE3 = { ROADS: "Road", SANITATION: "San", STREETLIGHT: "Light", WATER: "Water", DRAINAGE: "Drain", ANIMAL: "Anim", HOSTEL: "Host", OTHER: "Gen" };

// ------------------------------------------------------------------ helpers
async function api(path, opts) {
  const r = await fetch(path, opts);
  let j = null;
  try { j = await r.json(); } catch (e) { j = { error: r.statusText }; }
  if (!r.ok) throw new Error((j && j.error) || ("HTTP " + r.status));
  return j;
}
const post = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });

function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  if (attrs) for (const k in attrs) {
    const v = attrs[k];
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") e.className = v;
    else if (k === "style") e.style.cssText = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    e.appendChild(typeof c === "object" ? c : document.createTextNode(String(c)));
  }
  return e;
}
function s(tag, attrs, text) {
  const e = document.createElementNS(SVGNS, tag);
  if (attrs) for (const k in attrs) if (attrs[k] !== null && attrs[k] !== undefined) e.setAttribute(k, attrs[k]);
  if (text !== undefined) e.textContent = text;
  return e;
}
const clear = (el) => { while (el && el.firstChild) el.removeChild(el.firstChild); return el; };
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const pct = (x, d) => (x === null || x === undefined) ? "–" : (100 * x).toFixed(d === undefined ? 1 : d) + "%";
const num = (x) => (x === null || x === undefined) ? "–" : Number(x).toLocaleString("en-IN");
const days = (x) => (x === null || x === undefined) ? "–" : (x < 1 / 24 ? Math.max(1, Math.round(x * 1440)) + " min" : x < 1 ? (x * 24).toFixed(0) + " h" : x.toFixed(1) + " d");
function fmtTs(ts) {
  if (!ts) return "";
  const [d, t] = ts.split("T");
  const dt = new Date(d + "T00:00:00");
  const mon = dt.toLocaleString("en-GB", { month: "short" });
  return dt.getDate() + " " + mon + " " + (t || "");
}
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { t.hidden = true; }, 2600);
}
function priBadge(p) { return h("span", { class: "pri p" + p, title: (S.town && S.town.priorities[p]) || "" }, "P" + p + " " + ["", "Critical", "High", "Normal", "Low"][p]); }
function idLink(id) { return h("a", { class: "idlink", href: "#", onclick: (e) => { e.preventDefault(); openComplaint(id); } }, id); }

// tooltip
const tip = () => $("#tip");
function showTip(evt, nodes) {
  const t = tip();
  clear(t);
  nodes.forEach((n) => t.appendChild(typeof n === "string" ? h("div", null, n) : n));
  t.hidden = false;
  const pad = 14, w = t.offsetWidth, ht = t.offsetHeight;
  let x = evt.clientX + pad, y = evt.clientY + pad;
  if (x + w > window.innerWidth - 8) x = evt.clientX - w - pad;
  if (y + ht > window.innerHeight - 8) y = evt.clientY - ht - pad;
  t.style.left = Math.max(4, x) + "px";
  t.style.top = Math.max(4, y) + "px";
}
function hideTip() { tip().hidden = true; }
function tipRow(color, value, label) {
  return h("div", null, h("span", { class: "tl", style: "background:" + color }), h("b", null, value), " ", label);
}

// ------------------------------------------------------------------ theme
function initTheme() {
  let saved = null;
  try { saved = localStorage.getItem("civiclens-theme"); } catch (e) { saved = null; }
  if (saved) document.documentElement.setAttribute("data-theme", saved);
  $("#themeBtn").addEventListener("click", () => {
    const cur = document.documentElement.getAttribute("data-theme") ||
      (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const next = cur === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("civiclens-theme", next); } catch (e) { /* private mode */ }
    rerender();
  });
}

// ------------------------------------------------------------------ tabs
function initTabs() {
  $$("#tabs button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
}
function showTab(tab) {
  S.tab = tab;
  $$("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  $$(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === "tab-" + tab));
  renderTab(tab);
}
async function renderTab(tab) {
  try {
    if (tab === "triage") renderTriageCharts();
    if (tab === "map") await renderMapTab();
    if (tab === "sla") await renderSlaTab();
    if (tab === "models") await renderModelsTab();
    if (tab === "topics") await renderTopicsTab();
  } catch (e) { toast("Could not load: " + e.message); }
}
let _rz = null;
function rerender() { clearTimeout(_rz); _rz = setTimeout(() => { renderTab(S.tab); drawMiniMap(); }, 120); }

// ------------------------------------------------------------------ SVG charts
function chartBox(el, height) {
  clear(el);
  const W = Math.max(260, el.clientWidth || 400);
  const svg = s("svg", { viewBox: "0 0 " + W + " " + height, height: height, role: "img" });
  el.appendChild(svg);
  return { svg, W, H: height };
}
function niceMax(v) {
  if (v <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * p >= v) return m * p;
  return 10 * p;
}

/* Line chart with crosshair tooltip. opts: {xs, series:[{name,color,values,dash}], yMax, yFmt, xLabel(i), height, vlines:[{x,label,color}], legend} */
function lineChart(el, o) {
  const H = o.height || 200, { svg, W } = chartBox(el, H);
  const m = { l: 40, r: o.directLabels === false ? 12 : 86, t: 10, b: 24 };
  const xs = o.xs, n = xs.length;
  const xmin = o.xNumeric ? xs[0] : 0, xmax = o.xNumeric ? xs[n - 1] : n - 1;
  const yMax = o.yMax || niceMax(Math.max(1, ...o.series.flatMap((se) => se.values)));
  const X = (i) => m.l + ((o.xNumeric ? xs[i] : i) - xmin) / ((xmax - xmin) || 1) * (W - m.l - m.r);
  const Xv = (v) => m.l + (v - xmin) / ((xmax - xmin) || 1) * (W - m.l - m.r);
  const Y = (v) => m.t + (1 - v / yMax) * (H - m.t - m.b);
  const fmt = o.yFmt || ((v) => num(Math.round(v)));
  for (let k = 0; k <= 4; k++) {
    const v = yMax * k / 4, y = Y(v);
    svg.appendChild(s("line", { x1: m.l, x2: W - m.r, y1: y, y2: y, class: k === 0 ? "axis" : "gridline" }));
    svg.appendChild(s("text", { x: m.l - 6, y: y + 4, "text-anchor": "end" }, fmt(v)));
  }
  const step = Math.max(1, Math.ceil(n / 7));
  for (let i = 0; i < n; i += step) svg.appendChild(s("text", { x: X(i), y: H - 6, "text-anchor": "middle" }, o.xLabel ? o.xLabel(i) : xs[i]));
  (o.vlines || []).forEach((v) => {
    const x = Xv(v.x);
    svg.appendChild(s("line", { x1: x, x2: x, y1: m.t, y2: H - m.b, stroke: v.color, "stroke-width": 1.5, "stroke-dasharray": "4 3" }));
    svg.appendChild(s("text", { x: x + 4, y: m.t + 10, class: "lbl" }, v.label));
  });
  const labels = [];
  o.series.forEach((se) => {
    const d = se.values.map((v, i) => (i ? "L" : "M") + X(i).toFixed(1) + " " + Y(v).toFixed(1)).join(" ");
    svg.appendChild(s("path", { d, fill: "none", stroke: se.color, "stroke-width": 2, "stroke-linejoin": "round", "stroke-dasharray": se.dash || null }));
    labels.push({ y: Y(se.values[n - 1]) + 4, name: se.name });
  });
  if (o.directLabels !== false) {                      // nudge end labels apart so they never overlap
    labels.sort((a, b) => a.y - b.y);
    for (let i = 1; i < labels.length; i++) if (labels[i].y - labels[i - 1].y < 13) labels[i].y = labels[i - 1].y + 13;
    labels.forEach((l) => svg.appendChild(s("text", { x: X(n - 1) + 6, y: l.y, class: "lbl" }, l.name)));
  }
  const hl = s("line", { class: "hover-line", y1: m.t, y2: H - m.b, visibility: "hidden" });
  svg.appendChild(hl);
  const dots = o.series.map((se) => { const c = s("circle", { r: 4, fill: se.color, stroke: css("--surface"), "stroke-width": 2, visibility: "hidden" }); svg.appendChild(c); return c; });
  const hit = s("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, class: "hit" });
  svg.appendChild(hit);
  hit.addEventListener("pointermove", (evt) => {
    const r = svg.getBoundingClientRect(), px = (evt.clientX - r.left) * (W / r.width);
    let best = 0, bd = 1e9;
    for (let i = 0; i < n; i++) { const d = Math.abs(X(i) - px); if (d < bd) { bd = d; best = i; } }
    hl.setAttribute("x1", X(best)); hl.setAttribute("x2", X(best)); hl.setAttribute("visibility", "visible");
    o.series.forEach((se, k) => { dots[k].setAttribute("cx", X(best)); dots[k].setAttribute("cy", Y(se.values[best])); dots[k].setAttribute("visibility", "visible"); });
    showTip(evt, [h("div", null, o.tipTitle ? o.tipTitle(best) : String(xs[best]))].concat(o.series.map((se) => tipRow(se.color, fmt(se.values[best]), se.name))));
  });
  hit.addEventListener("pointerleave", () => { hl.setAttribute("visibility", "hidden"); dots.forEach((d) => d.setAttribute("visibility", "hidden")); hideTip(); });
  if (o.legend !== false && o.series.length > 1) {
    el.appendChild(h("div", { class: "legend" }, o.series.map((se) => h("span", null, h("span", { class: "sw", style: "background:" + se.color }), se.name))));
  }
}

/* Horizontal bars. rows: [{label, value, color, note}] */
function hbars(el, rows, o) {
  o = o || {};
  const rh = o.rowH || 24, H = rows.length * rh + 8, { svg, W } = chartBox(el, H);
  const lw = o.labelW || 120, vw = 64;
  const max = o.max || niceMax(Math.max(1e-9, ...rows.map((r) => Math.abs(r.value))));
  const fmt = o.fmt || ((v) => num(v));
  rows.forEach((r, i) => {
    const y = 4 + i * rh, bw = Math.max(2, Math.abs(r.value) / max * (W - lw - vw - 8));
    svg.appendChild(s("text", { x: lw - 8, y: y + rh / 2 + 4, "text-anchor": "end", class: "lbl" }, r.label));
    const bar = s("rect", { x: lw, y: y + 5, width: bw, height: rh - 10, rx: 3, fill: r.color || css("--s1") });
    svg.appendChild(bar);
    svg.appendChild(s("text", { x: lw + bw + 6, y: y + rh / 2 + 4, class: "val" }, fmt(r.value)));
    const hit = s("rect", { x: 0, y, width: W, height: rh, class: "hit" });
    hit.addEventListener("pointermove", (evt) => { bar.setAttribute("opacity", "0.8"); showTip(evt, [h("b", null, r.label), h("div", null, fmt(r.value) + (r.note ? " · " + r.note : ""))]); });
    hit.addEventListener("pointerleave", () => { bar.setAttribute("opacity", "1"); hideTip(); });
    svg.appendChild(hit);
  });
}

/* Grouped horizontal bars: cats x series */
function groupedBars(el, cats, series, o) {
  o = o || {};
  const gh = 14 * series.length + 10, H = cats.length * gh + 8, { svg, W } = chartBox(el, H);
  const lw = 104, vw = 48, max = o.max || 1;
  const fmt = o.fmt || ((v) => v.toFixed(2));
  cats.forEach((c, i) => {
    const y0 = 4 + i * gh;
    svg.appendChild(s("text", { x: lw - 8, y: y0 + gh / 2 + 3, "text-anchor": "end", class: "lbl" }, c));
    series.forEach((se, k) => {
      const v = se.values[i], y = y0 + 4 + k * 14, bw = Math.max(2, v / max * (W - lw - vw));
      const bar = s("rect", { x: lw, y, width: bw, height: 11, rx: 2, fill: se.color });
      svg.appendChild(bar);
      svg.appendChild(s("text", { x: lw + bw + 5, y: y + 10, class: "val" }, fmt(v)));
      const hit = s("rect", { x: 0, y: y - 1, width: W, height: 14, class: "hit" });
      hit.addEventListener("pointermove", (evt) => { bar.setAttribute("opacity", ".8"); showTip(evt, [h("b", null, c), tipRow(se.color, fmt(v), se.name)]); });
      hit.addEventListener("pointerleave", () => { bar.setAttribute("opacity", "1"); hideTip(); });
      svg.appendChild(hit);
    });
  });
  el.appendChild(h("div", { class: "legend" }, series.map((se) => h("span", null, h("span", { class: "sw box", style: "background:" + se.color }), se.name))));
}

/* Box plot per department (days) with SLA tick */
function boxChart(el, rows) {
  const rh = 30, H = rows.length * rh + 30, { svg, W } = chartBox(el, H);
  const lw = 110, r = 20;
  const max = niceMax(Math.max(...rows.map((x) => Math.max(x.p90 || 0, x.sla))));
  const X = (v) => lw + v / max * (W - lw - r);
  for (let k = 0; k <= 5; k++) {
    const v = max * k / 5, x = X(v);
    svg.appendChild(s("line", { x1: x, x2: x, y1: 4, y2: H - 22, class: "gridline" }));
    svg.appendChild(s("text", { x, y: H - 6, "text-anchor": "middle" }, v.toFixed(v < 10 ? 1 : 0) + " d"));
  }
  const col = css("--s1"), red = css("--brand");
  rows.forEach((b, i) => {
    const y = 6 + i * rh, cy = y + rh / 2 - 2;
    svg.appendChild(s("text", { x: lw - 8, y: cy + 4, "text-anchor": "end", class: "lbl" }, b.label));
    if (!b.n) return;
    svg.appendChild(s("line", { x1: X(b.p10), x2: X(b.p90), y1: cy, y2: cy, stroke: col, "stroke-width": 1.5 }));
    const box = s("rect", { x: X(b.p25), y: cy - 8, width: Math.max(2, X(b.p75) - X(b.p25)), height: 16, rx: 3, fill: col, "fill-opacity": 0.25, stroke: col, "stroke-width": 1.5 });
    svg.appendChild(box);
    svg.appendChild(s("line", { x1: X(b.median), x2: X(b.median), y1: cy - 8, y2: cy + 8, stroke: col, "stroke-width": 3 }));
    svg.appendChild(s("line", { x1: X(b.sla), x2: X(b.sla), y1: cy - 11, y2: cy + 11, stroke: red, "stroke-width": 2.5 }));
    const hit = s("rect", { x: 0, y, width: W, height: rh, class: "hit" });
    hit.addEventListener("pointermove", (evt) => showTip(evt, [h("b", null, b.label), "median " + days(b.median) + " · p25-p75 " + days(b.p25) + "-" + days(b.p75), "p10-p90 " + days(b.p10) + "-" + days(b.p90) + " · SLA " + b.sla + " d · n=" + b.n]));
    hit.addEventListener("pointerleave", hideTip);
    svg.appendChild(hit);
  });
}

/* Diverging bars for model weights */
function divBars(el, rows, o) {
  o = o || {};
  const rh = 22, H = rows.length * rh + 8, { svg, W } = chartBox(el, H);
  const lw = 170, max = Math.max(...rows.map((r) => Math.abs(r.value)), 1e-9);
  const half = (W - lw - 100) / 2, mid = lw + 50 + half;
  svg.appendChild(s("line", { x1: mid, x2: mid, y1: 0, y2: H, class: "axis" }));
  rows.forEach((r, i) => {
    const y = 4 + i * rh, bw = Math.abs(r.value) / max * half;
    const pos = r.value >= 0;
    svg.appendChild(s("text", { x: lw - 8, y: y + rh / 2 + 4, "text-anchor": "end", class: "lbl" }, r.label));
    svg.appendChild(s("rect", { x: pos ? mid : mid - bw, y: y + 4, width: Math.max(1, bw), height: rh - 8, rx: 3, fill: pos ? css("--brand") : css("--s1") }));
    svg.appendChild(s("text", { x: pos ? mid + bw + 4 : mid - bw - 4, y: y + rh / 2 + 4, "text-anchor": pos ? "start" : "end", class: "val" }, (r.value > 0 ? "+" : "") + r.value.toFixed(2)));
  });
  if (o.caption) el.appendChild(h("div", { class: "legend" }, h("span", null, h("span", { class: "sw box", style: "background:" + css("--brand") }), "raises breach risk"), h("span", null, h("span", { class: "sw box", style: "background:" + css("--s1") }), "lowers breach risk")));
}

// ------------------------------------------------------------------ boot
async function boot() {
  initTheme();
  initTabs();
  try {
    const [town, summary, samples] = await Promise.all([api("/api/town"), api("/api/summary"), api("/api/demo/samples")]);
    S.town = town; S.summary = summary; S.samples = samples.samples;
  } catch (e) { toast("Server not reachable: " + e.message); return; }
  initTriage();
  renderSummary();
  await loadQueue();
  renderTriageCharts();
  window.addEventListener("resize", rerender);
  $("#demoBtn").addEventListener("click", runDemo);
  $("#resetBtn").addEventListener("click", resetDemo);
  $("#modalX").addEventListener("click", closeModal);
  $("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });
}

function deptOptions(sel, allLabel, exclude) {
  clear(sel);
  sel.appendChild(h("option", { value: "" }, allLabel || "All departments"));
  S.town.departments.forEach((d) => { if (!(exclude || []).includes(d.code)) sel.appendChild(h("option", { value: d.code }, d.name)); });
}

function renderSummary() {
  const sm = S.summary, k = sm.kpis;
  $("#sourcePill").textContent = sm.town + " · " + num(k.complaints) + " complaints · " + fmtTs(sm.period[0] + "T").trim() + " → " + fmtTs(sm.now);
  const tiles = [
    { l: "Open now", v: num(k.open), n: num(k.incidents) + " incidents in total" },
    { l: "Open & SLA breached", v: num(k.open_breached), n: "need escalation", alert: k.open_breached > 0 },
    { l: "P1 critical open", v: num(k.p1_open), n: "safety first", alert: k.p1_open > 0 },
    { l: "Median resolution", v: days(k.median_res_days_4w), n: "last 4 weeks" },
    { l: "SLA compliance", v: pct(k.sla_compliance_4w, 0), n: "last 4 weeks" },
    { l: "Duplicates merged", v: num(k.duplicates_merged), n: "MinHash LSH + geo + time" },
    { l: "Emerging hotspots", v: num(k.emerging_this_week), n: "this week, z ≥ 3", alert: k.emerging_this_week > 0 },
  ];
  const box = clear($("#kpis"));
  tiles.forEach((t) => box.appendChild(h("div", { class: "kpi" + (t.alert ? " alert" : "") }, h("div", { class: "k-label" }, t.l), h("div", { class: "k-value" }, t.v), h("div", { class: "k-note" }, t.n))));
}

// ------------------------------------------------------------------ triage
function initTriage() {
  deptOptions($("#qDept"));
  ["#qDept", "#qPri", "#qOpen"].forEach((id) => $(id).addEventListener("change", loadQueue));
  let t = null;
  $("#qSearch").addEventListener("input", () => { clearTimeout(t); t = setTimeout(loadQueue, 250); });
  const ch = $("#cChannel");
  S.town.channels.forEach((c) => ch.appendChild(h("option", { value: c }, c)));
  const ws = $("#cWard");
  S.town.wards.forEach((w) => ws.appendChild(h("option", { value: w.code }, w.code + " " + w.name)));
  ws.value = "W07";
  setLoc(S.town.wards[6].center[0], S.town.wards[6].center[1], false);
  ws.addEventListener("change", () => { const w = S.town.wards.find((x) => x.code === ws.value); setLoc(w.center[0], w.center[1], false); });
  const ex = $("#examples");
  S.samples.forEach((sm, i) => ex.appendChild(h("button", { class: "chip", type: "button", title: sm.text, onclick: () => useSample(i) }, sm.label)));
  $("#analyzeBtn").addEventListener("click", () => submitComplaint(false));
  $("#fileBtn").addEventListener("click", () => submitComplaint(true));
  $("#miniMap").addEventListener("click", (e) => {
    const c = $("#miniMap"), r = c.getBoundingClientRect(), b = S.town.bounds;
    const lon = b[1] + (e.clientX - r.left) / r.width * (b[3] - b[1]);
    const lat = b[2] - (e.clientY - r.top) / r.height * (b[2] - b[0]);
    setLoc(lat, lon, true);
  });
}
function wardAt(lat, lon) {
  return S.town.wards.find((w) => lat >= w.bounds[0] && lat <= w.bounds[2] && lon >= w.bounds[1] && lon <= w.bounds[3]) || S.town.wards[0];
}
function setLoc(lat, lon, syncWard) {
  S.loc = [lat, lon];
  const w = wardAt(lat, lon);
  if (syncWard !== false) $("#cWard").value = w.code;
  $("#cLoc").textContent = lat.toFixed(4) + ", " + lon.toFixed(4) + " · " + w.name;
  drawMiniMap();
}
function useSample(i) {
  const sm = S.samples[i];
  $("#cText").value = sm.text;
  $("#cChannel").value = sm.channel;
  setLoc(sm.lat, sm.lon, true);
  $("#formHint").textContent = sm.expect_dup_of ? "expected: duplicate of " + sm.expect_dup_of : "";
}

function setupCanvas(c, cssH) {
  const dpr = window.devicePixelRatio || 1, w = c.clientWidth || 300;
  const hgt = cssH || c.clientHeight || 110;
  c.width = Math.round(w * dpr); c.height = Math.round(hgt * dpr);
  c.style.height = hgt + "px";
  const ctx = c.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, w, h: hgt };
}
function projector(w, hh) {
  const b = S.town.bounds;
  return { x: (lon) => (lon - b[1]) / (b[3] - b[1]) * w, y: (lat) => (b[2] - lat) / (b[2] - b[0]) * hh };
}
function drawWards(ctx, P, labels, emph) {
  S.town.wards.forEach((w) => {
    const x0 = P.x(w.bounds[1]), x1 = P.x(w.bounds[3]), y0 = P.y(w.bounds[2]), y1 = P.y(w.bounds[0]);
    if (emph && emph[w.code]) { ctx.fillStyle = css("--accent-soft"); ctx.fillRect(x0, y0, x1 - x0, y1 - y0); }
    ctx.strokeStyle = css("--axis"); ctx.lineWidth = 1; ctx.strokeRect(x0 + 0.5, y0 + 0.5, x1 - x0, y1 - y0);
    if (labels) {
      ctx.fillStyle = css("--muted"); ctx.font = "600 11px system-ui, sans-serif";
      ctx.fillText(w.code, x0 + 6, y0 + 14);
      ctx.font = "11px system-ui, sans-serif";
      ctx.fillText(w.name, x0 + 6, y0 + 27);
    }
  });
}
function drawMiniMap() {
  const c = $("#miniMap");
  if (!c || !S.town || !c.clientWidth) return;
  const { ctx, w, h: hh } = setupCanvas(c, 84);
  const P = projector(w, hh);
  ctx.clearRect(0, 0, w, hh);
  drawWards(ctx, P, false);
  ctx.fillStyle = css("--muted"); ctx.font = "10px system-ui, sans-serif";
  S.town.wards.forEach((wd) => ctx.fillText(wd.code, P.x(wd.bounds[1]) + 3, P.y(wd.bounds[2]) + 11));
  if (S.loc) {
    const x = P.x(S.loc[1]), y = P.y(S.loc[0]);
    ctx.fillStyle = css("--brand"); ctx.beginPath(); ctx.arc(x, y, 5, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = css("--surface"); ctx.lineWidth = 2; ctx.stroke();
  }
}

async function loadQueue() {
  const p = new URLSearchParams({ limit: 60 });
  if ($("#qDept").value) p.set("dept", $("#qDept").value);
  if ($("#qPri").value) p.set("priority", $("#qPri").value);
  if ($("#qOpen").checked) p.set("status", "open");
  if ($("#qSearch").value.trim()) p.set("q", $("#qSearch").value.trim());
  let res;
  try { res = await api("/api/queue?" + p.toString()); } catch (e) { toast(e.message); return; }
  $("#queueSub").textContent = "newest first · clock " + fmtTs(res.now);
  const tb = clear($("#queueTbl tbody"));
  if (!res.complaints.length) tb.appendChild(h("tr", null, h("td", { colspan: 7, class: "meta" }, "No complaints match these filters.")));
  res.complaints.forEach((c) => tb.appendChild(queueRow(c)));
}
function slaCell(c) {
  if (c.status === "resolved") return h("span", { class: "sla-done", title: "resolved in " + days(c.res_days) }, (c.breached ? "late " : "done ") + days(c.res_days));
  if (c.breached) return h("span", { class: "sla-bad" }, "overdue");
  const left = c.sla_days - c.age_days;
  return h("span", { class: "sla-ok", title: "due " + fmtTs(c.due) }, days(left) + " left");
}
function queueRow(c) {
  const dup = c.dup_of ? h("span", null, "of ", idLink(c.dup_of)) : (c.inc_size > 1 ? h("span", { class: "meta" }, c.inc_size + " reports") : h("span", { class: "meta" }, "new"));
  return h("tr", { class: c.live ? "live" : "", "data-id": c.id },
    h("td", null, idLink(c.id), h("div", { class: "meta" }, fmtTs(c.ts))),
    h("td", null, priBadge(c.priority)),
    h("td", { class: "txt" }, h("div", { class: "t", title: c.text }, c.text),
      h("div", null, c.live ? h("span", { class: "tag new" }, "NEW") : null, h("span", { class: "tag" }, LANG[c.lang] || c.lang), h("span", { class: "tag" }, c.channel))),
    h("td", null, DEPT_SHORT[c.dept] || c.dept, h("div", { class: "conf" }, pct(c.conf, 0) + " conf.")),
    h("td", null, dup),
    h("td", null, c.ward, h("div", { class: "meta" }, c.ward_name)),
    h("td", null, slaCell(c)));
}

async function submitComplaint(record) {
  const text = $("#cText").value.trim();
  if (!text) { toast("Type a complaint or pick an example first"); return; }
  const body = { text, lat: S.loc[0], lon: S.loc[1], channel: $("#cChannel").value };
  $("#fileBtn").disabled = $("#analyzeBtn").disabled = true;
  try {
    const res = await post(record ? "/api/complaints" : "/api/analyze", body);
    renderResult(res, record);
    if (record) await afterFiling(res.id);
  } catch (e) { toast(e.message); }
  finally { $("#fileBtn").disabled = $("#analyzeBtn").disabled = false; }
}
async function afterFiling(id) {
  try {
    S.summary = await api("/api/summary");
    renderSummary();
    await loadQueue();
    const row = $('#queueTbl tr[data-id="' + id + '"]');
    if (row) { row.classList.add("flash"); }
    S.rendered = {};
  } catch (e) { toast(e.message); }
}

function tokColor(w, maxAbs) {
  const a = Math.min(1, Math.abs(w) / (maxAbs || 1));
  if (a < 0.06) return "transparent";
  return w > 0 ? "rgba(220,38,38," + (0.12 + 0.55 * a).toFixed(2) + ")" : "rgba(59,130,246," + (0.10 + 0.4 * a).toFixed(2) + ")";
}
function barRows(rows, red) {
  return h("div", { class: "bars" }, rows.map((r) => h("div", { class: "bar-row" }, h("span", { class: "lab", title: r.label }, r.label),
    h("span", { class: "track" }, h("span", { class: "fill" + (red && r.hi ? " red" : ""), style: "width:" + (100 * Math.max(0, Math.min(1, r.value))).toFixed(1) + "%" })),
    h("span", { class: "v" }, pct(r.value, 0)))));
}
function renderResult(res, record) {
  S.lastResult = res;
  const out = clear($("#result"));
  out.classList.remove("empty");
  $("#resultSub").textContent = (record ? "filed as " + res.id : "analysis only (not filed)") + " · " + res.total_ms.toFixed(1) + " ms end-to-end";
  const r = res.routing, u = res.urgency, d = res.duplicate;
  out.appendChild(h("div", { class: "res-head" },
    h("div", { class: "res-tile" }, h("div", { class: "lab" }, "Routed to"), h("div", { class: "val", title: r.dept_name }, DEPT_SHORT[r.dept] || r.dept_name), h("div", { class: "small" }, pct(r.confidence, 0) + " confidence · NB says " + (DEPT_SHORT[r.nb_dept] || r.nb_dept))),
    h("div", { class: "res-tile" + (u.priority === 1 ? " alert" : "") }, h("div", { class: "lab" }, "Priority"), h("div", { class: "val" }, priBadge(u.priority)), h("div", { class: "small", title: u.reason }, u.reason)),
    h("div", { class: "res-tile" + (d.is_duplicate ? " alert" : "") }, h("div", { class: "lab" }, "Duplicate check"),
      h("div", { class: "val" }, d.is_duplicate ? h("span", null, "of ", idLink(d.of)) : "New incident"),
      h("div", { class: "small" }, d.is_duplicate ? "P(same) " + pct(d.match.score, 0) + " · " + d.match.dist_m + " m · " + days(d.match.gap_h / 24) + " later" : d.lsh_candidates + " LSH candidates checked"))));

  // 1 language + routing
  const maxAbs = Math.max(0.2, ...r.tokens.map((t) => Math.abs(t.w)));
  const toks = h("div", { class: "tokens" }, r.tokens.map((t) => h("span", { class: "tok", style: "background:" + tokColor(t.w, maxAbs), title: (t.w >= 0 ? "+" : "") + t.w.toFixed(2) + " toward " + r.dept_name }, t.t)));
  out.appendChild(h("div", { class: "step" },
    h("h5", null, h("span", null, "1-2 · Language: " + res.lang_name + " · why " + r.dept_name + "?"), h("span", { class: "ms" }, res.latency_ms.routing_ms.toFixed(1) + " ms")),
    toks,
    barRows(r.lr_probs.slice(0, 3).map((p, i) => ({ label: "LR · " + (DEPT_SHORT[p.dept] || p.dept), value: p.p, hi: i === 0 })), true),
    h("div", { class: "meta wrap" }, "Concepts: " + (res.concepts.slice(0, 12).join(", ") || "none") + " · red words push toward the routed department, blue away")));

  // 3 urgency
  out.appendChild(h("div", { class: "step" },
    h("h5", null, h("span", null, "3 · Urgency: rules + model"), h("span", { class: "ms" }, res.latency_ms.urgency_ms.toFixed(1) + " ms")),
    h("div", null, u.rules.length ? u.rules.map((f) => h("span", { class: "rule-chip " + f.kind, title: "matched concepts: " + f.matched.join(" + ") }, f.label + (f.kind === "soft" ? "" : " · " + f.kind))) : h("span", { class: "meta" }, "No rule fired; the model decides.")),
    barRows(u.probs.map((p, i) => ({ label: "P" + (i + 1) + " " + ["Critical", "High", "Normal", "Low"][i], value: p, hi: i + 1 === u.priority })), true)));

  // 4 duplicates
  let dupBody;
  if (d.is_duplicate) {
    const m = d.match;
    dupBody = h("div", { class: "dup-box" }, h("div", null, idLink(m.id), " ", h("span", { class: "q" }, "“" + m.text + "”")),
      h("div", { class: "meta wrap" }, "text similarity " + m.jaccard.toFixed(2) + " (MinHash) · " + m.dist_m + " m apart · " + days(m.gap_h / 24) + " earlier · P(same incident) " + pct(m.score, 0)),
      m.explain ? h("div", { class: "meta wrap" }, "logit contributions: " + m.explain.map((e) => e.feature + " " + (e.contribution >= 0 ? "+" : "") + e.contribution.toFixed(2)).join(", ")) : null);
  } else {
    const top = d.checked.slice(0, 2);
    dupBody = h("div", { class: "dup-box" }, h("div", null, "No open complaint matches: this starts a new incident."),
      top.map((m) => h("div", { class: "meta wrap" }, m.id + ": similarity " + m.jaccard.toFixed(2) + ", " + m.dist_m + " m, rejected (" + (m.why_not.join(", ") || "low score") + ")")));
  }
  out.appendChild(h("div", { class: "step" }, h("h5", null, h("span", null, "4 · Duplicate search (MinHash LSH, " + d.lsh_candidates + " candidates)"), h("span", { class: "ms" }, res.latency_ms.dedup_ms.toFixed(1) + " ms")), dupBody));

  // 5-6 hotspot + SLA
  const hs = res.hotspot, sl = res.sla;
  out.appendChild(h("div", { class: "step" },
    h("h5", null, h("span", null, "5-6 · Hotspot and SLA"), h("span", { class: "ms" }, (res.latency_ms.hotspot_ms + res.latency_ms.sla_ms).toFixed(1) + " ms")),
    h("div", { class: "kv" },
      h("span", { class: "k" }, "Location"), h("span", null, res.ward + " " + res.ward_name),
      h("span", { class: "k" }, "Hotspot"), h("span", null, hs ? "inside " + hs.id + " (" + hs.n + " incidents, " + hs.dist_m + " m from centre)" : "not inside a known hotspot"),
      h("span", { class: "k" }, "Emerging"), h("span", null, res.emerging ? h("b", { class: "sla-bad" }, "yes: " + res.emerging.x + " incidents this week vs " + res.emerging.lambda + "/week usual (z = " + res.emerging.z.toFixed(1) + ")") : "ward is at its usual level"),
      h("span", { class: "k" }, "SLA"), h("span", null, sl.days + " days → due " + fmtTs(sl.due) + " · dept backlog " + sl.backlog),
      h("span", { class: "k" }, "Breach risk"), h("span", null, h("b", null, pct(sl.breach_risk, 0)), sl.factors.length ? " · driven by " + sl.factors.map((f) => feat(f.feature)).join(", ") : ""))));
}

// ------------------------------------------------------------------ demo
async function runDemo() {
  if (S.demoRunning) return;
  S.demoRunning = true;
  $("#demoBtn").disabled = true;
  showTab("triage");
  try {
    for (let i = 0; i < S.samples.length; i++) {
      useSample(i);
      const sm = S.samples[i];
      const res = await post("/api/complaints", { text: sm.text, lat: sm.lat, lon: sm.lon, channel: sm.channel });
      renderResult(res, true);
      await afterFiling(res.id);
      toast((i + 1) + "/" + S.samples.length + " · " + sm.label + " → " + DEPT_SHORT[res.routing.dept] + ", P" + res.urgency.priority + (res.duplicate.is_duplicate ? ", duplicate of " + res.duplicate.of : ""));
      await new Promise((r) => setTimeout(r, 1400));
    }
  } catch (e) { toast("Demo stopped: " + e.message); }
  finally { S.demoRunning = false; $("#demoBtn").disabled = false; }
}
async function resetDemo() {
  try {
    const r = await post("/api/demo/reset", {});
    toast(r.message);
    S.summary = await api("/api/summary");
    S.samples = (await api("/api/demo/samples")).samples;
    renderSummary();
    await loadQueue();
    S.rendered = {};
    clear($("#result")).classList.add("empty");
    $("#result").appendChild(h("p", null, "Pick an example or type a complaint, then Analyse or File."));
    $("#resultSub").textContent = "";
    renderTab(S.tab);
  } catch (e) { toast(e.message); }
}

function renderTriageCharts() {
  const sm = S.summary;
  if (!sm) return;
  lineChart($("#weeklyChart"), {
    xs: sm.week_starts, height: 190, xLabel: (i) => "W" + (i + 1),
    tipTitle: (i) => "Week " + (i + 1) + " (from " + sm.week_starts[i] + ")",
    series: [{ name: "complaints", color: css("--s2"), values: sm.weekly }, { name: "incidents", color: css("--s1"), values: sm.weekly_incidents }],
  });
  const rows = sm.by_dept.slice().sort((a, b) => b.n - a.n).map((d) => ({ label: DEPT_SHORT[d.dept], value: d.n, color: css("--s1"), note: d.name }));
  hbars($("#deptChart"), rows, { labelW: 92, rowH: 23 });
  const box = clear($("#emergingList"));
  if (!sm.emerging.length) box.appendChild(h("p", { class: "note" }, "No ward-department combination is unusually high this week."));
  sm.emerging.forEach((f) => box.appendChild(emItem(f)));
}
function sparkline(series, flagIdx) {
  const W = 120, H = 28, max = Math.max(1, ...series);
  const svg = s("svg", { width: W, height: H, viewBox: "0 0 " + W + " " + H, class: "spark" });
  const bw = W / series.length;
  series.forEach((v, i) => svg.appendChild(s("rect", { x: i * bw + 1, y: H - (v / max) * (H - 2), width: bw - 2, height: Math.max(1, (v / max) * (H - 2)), rx: 1, fill: i === flagIdx ? css("--brand") : css("--axis") })));
  return svg;
}
function emItem(f) {
  return h("div", { class: "em-item" },
    h("div", null, h("div", { class: "ttl" }, f.dept_name + " · " + f.ward + " " + f.ward_name),
      h("div", { class: "st" }, f.x + " incidents vs " + f.lambda + "/week baseline · p = " + (f.p < 0.001 ? f.p.toExponential(1) : f.p.toFixed(3)) + (f.planted ? " · planted " + f.planted : ""))),
    h("div", null, h("div", { class: "z" }, "z = " + f.z.toFixed(1)), sparkline(f.series, f.week - 1)));
}

// ------------------------------------------------------------------ complaint modal
async function openComplaint(id) {
  let c;
  try { c = await api("/api/complaint/" + encodeURIComponent(id)); } catch (e) { toast(e.message); return; }
  const body = clear($("#modalBody"));
  body.appendChild(h("h3", { id: "modalTitle" }, c.id + " · " + c.dept_name));
  body.appendChild(h("p", { style: "font-size:15px" }, c.text));
  const kv = h("div", { class: "kv" });
  const add = (k, v) => { kv.appendChild(h("span", { class: "k" }, k)); kv.appendChild(typeof v === "object" ? v : h("span", null, v)); };
  add("Filed", fmtTs(c.ts) + " via " + c.channel + " (" + (LANG[c.lang] || c.lang) + ")");
  add("Ward", c.ward + " " + c.ward_name + " · " + c.lat.toFixed(5) + ", " + c.lon.toFixed(5));
  add("Routed to", c.dept_name + " (" + pct(c.conf, 0) + " confidence)");
  add("Priority", h("span", null, priBadge(c.priority), " ", c.priority_reason));
  add("Rules fired", c.rules.length ? c.rules.join(", ") : "none");
  add("Duplicate of", c.dup_of ? h("span", null, idLink(c.dup_of), c.dup_info ? " · similarity " + c.dup_info.jaccard + ", " + c.dup_info.dist_m + " m, " + c.dup_info.gap_h + " h later" : "") : "—");
  add("Incident", c.inc_size + " report(s), root " + c.root + (c.siblings.length ? " · others: " : ""));
  if (c.siblings.length) kv.lastChild.appendChild(h("span", null, c.siblings.map((x, i) => [i ? ", " : "", idLink(x)])));
  add("Status", c.status === "resolved" ? "resolved in " + days(c.res_days) + (c.breached ? " (SLA breached)" : " (within SLA)") : "open for " + days(c.age_days) + (c.breached ? " — overdue" : " · due " + fmtTs(c.due)));
  if (c.breach_risk !== undefined) add("Breach risk", pct(c.breach_risk, 0) + (c.breach_factors.length ? " · " + c.breach_factors.map((f) => feat(f.feature)).join(", ") : ""));
  if (c.ground_truth) add("Ground truth (synthetic)", c.ground_truth.dept + " · P" + c.ground_truth.urgency + " · " + c.ground_truth.issue + " · " + c.ground_truth.incident + (c.ground_truth.planted ? " · planted " + c.ground_truth.planted : ""));
  body.appendChild(kv);
  $("#modal").hidden = false;
  $("#modalX").focus();
}
function closeModal() { $("#modal").hidden = true; }

// ------------------------------------------------------------------ map tab
async function renderMapTab() {
  if (!S.rendered.mapInit) {
    deptOptions($("#mDept"), "All departments", ["HOSTEL"]);
    deptOptions($("#hDept"), "All departments");
    $("#mEps").value = S.town.defaults.eps_m; $("#mMin").value = S.town.defaults.min_pts;
    const emw = $("#emWeek");
    for (let w = 13; w >= 5; w--) emw.appendChild(h("option", { value: w }, "Week " + w + (w === 13 ? " (this week)" : "")));
    ["#mDept", "#mWeeks", "#mPlanted"].forEach((id) => $(id).addEventListener("change", loadMap));
    ["#mEps", "#mMin"].forEach((id) => $(id).addEventListener("input", () => { $("#mEpsV").textContent = $("#mEps").value; $("#mMinV").textContent = $("#mMin").value; clearTimeout(S._mt); S._mt = setTimeout(loadMap, 200); }));
    $("#hDept").addEventListener("change", loadHeat);
    emw.addEventListener("change", loadEmerging);
    const cv = $("#bigMap");
    cv.addEventListener("pointermove", mapHover);
    cv.addEventListener("pointerleave", hideTip);
    const hc = $("#heatGrid");
    hc.addEventListener("pointermove", heatHover);
    hc.addEventListener("pointerleave", hideTip);
    S.rendered.mapInit = true;
  }
  $("#mEpsV").textContent = $("#mEps").value; $("#mMinV").textContent = $("#mMin").value;
  await Promise.all([loadMap(), loadHeat(), loadEmerging()]);
}
async function loadMap() {
  const dept = $("#mDept").value, weeks = $("#mWeeks").value;
  const p = new URLSearchParams();
  if (dept) p.set("dept", dept);
  if (weeks) p.set("weeks", weeks);
  const hp = new URLSearchParams(p); hp.set("eps", $("#mEps").value); hp.set("min_pts", $("#mMin").value);
  const [md, hot] = await Promise.all([api("/api/map?" + p), api("/api/hotspots?" + hp)]);
  S.mapData = md; S.hot = hot;
  drawBigMap();
  renderHotspotTable();
}
function drawBigMap() {
  const c = $("#bigMap");
  if (!c.clientWidth || !S.mapData) return;
  const w = c.clientWidth, hh = Math.round(w * 0.8);
  const { ctx } = setupCanvas(c, hh);
  const P = projector(w, hh);
  ctx.clearRect(0, 0, w, hh);
  const emph = {};
  (S.summary.emerging || []).forEach((f) => { emph[f.ward] = true; });
  drawWards(ctx, P, true, emph);
  ctx.fillStyle = css("--axis");
  S.town.places.forEach((pl) => { if (pl.kind !== "st") ctx.fillRect(P.x(pl.lon) - 2, P.y(pl.lat) - 2, 4, 4); });
  const sel = $("#mDept").value;
  const col = css("--s1"), muted = css("--s4");
  S._pts = [];
  S.mapData.points.forEach((pt) => {
    const x = P.x(pt[2]), y = P.y(pt[1]);
    S._pts.push([x, y, pt]);
    ctx.globalAlpha = sel ? 0.85 : 0.55;
    ctx.fillStyle = sel ? col : muted;
    ctx.beginPath(); ctx.arc(x, y, pt[5] ? 3.6 : 2.6, 0, Math.PI * 2); ctx.fill();
    if (pt[5]) { ctx.globalAlpha = 1; ctx.strokeStyle = css("--ink"); ctx.lineWidth = 1; ctx.stroke(); }
  });
  ctx.globalAlpha = 1;
  const mPerPx = (S.town.bounds[3] - S.town.bounds[1]) * 109020 / w;
  if ($("#mPlanted").checked) {
    ctx.setLineDash([4, 4]); ctx.strokeStyle = css("--ink-2"); ctx.lineWidth = 1.5;
    S.hot.planted.forEach((p) => { ctx.beginPath(); ctx.arc(P.x(p.center[1]), P.y(p.center[0]), Math.max(10, 2.2 * p.sigma_m / mPerPx), 0, Math.PI * 2); ctx.stroke(); });
    ctx.setLineDash([]);
  }
  const placed = [];
  S.hot.clusters.forEach((hs) => {
    const x = P.x(hs.center[1]), y = P.y(hs.center[0]), r = Math.max(8, hs.radius_m / mPerPx);
    ctx.fillStyle = "rgba(220,38,38,0.14)"; ctx.strokeStyle = css("--brand"); ctx.lineWidth = 2.5;
    ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
  });
  S.hot.clusters.forEach((hs) => {
    const x = P.x(hs.center[1]), r = Math.max(8, hs.radius_m / mPerPx);
    let y = P.y(hs.center[0]) - 3;
    const label = hs.id + " · " + hs.n;
    ctx.font = "700 11px system-ui, sans-serif";
    const tw = ctx.measureText(label).width, lx = x + r + 3;
    while (placed.some((b) => lx < b[0] + b[2] && lx + tw > b[0] && Math.abs(y - b[1]) < 13)) y += 13;
    placed.push([lx, y, tw]);
    ctx.fillStyle = css("--surface"); ctx.globalAlpha = 0.8; ctx.fillRect(lx - 2, y - 10, tw + 4, 13); ctx.globalAlpha = 1;
    ctx.fillStyle = css("--ink"); ctx.fillText(label, lx, y);
  });
  const lg = clear($("#mapLegend"));
  lg.appendChild(h("span", null, h("span", { class: "sw box", style: "background:" + (sel ? col : muted) }), "incident (one dot per de-duplicated incident)"));
  lg.appendChild(h("span", null, h("span", { class: "sw ring", style: "border-color:" + css("--ink") }), "still open"));
  lg.appendChild(h("span", null, h("span", { class: "sw ring", style: "border-color:" + css("--brand") }), "DBSCAN hotspot"));
  if ($("#mPlanted").checked) lg.appendChild(h("span", null, h("span", { class: "sw dash", style: "border-color:" + css("--ink-2") }), "planted ground truth"));
  lg.appendChild(h("span", null, h("span", { class: "sw box", style: "background:" + css("--accent-soft") }), "ward with an emerging hotspot this week"));
  $("#mapSub").textContent = num(S.mapData.points.length) + " incidents" + (sel ? " · " + DEPT_SHORT[sel] : " · all departments");
}
function mapHover(evt) {
  if (!S._pts) return;
  const r = $("#bigMap").getBoundingClientRect(), x = evt.clientX - r.left, y = evt.clientY - r.top;
  let best = null, bd = 144;
  S._pts.forEach((p) => { const d = (p[0] - x) ** 2 + (p[1] - y) ** 2; if (d < bd) { bd = d; best = p; } });
  if (!best) {
    const w = r.width, hh = r.height, b = S.town.bounds;
    const lon = b[1] + x / w * (b[3] - b[1]), lat = b[2] - y / hh * (b[2] - b[0]);
    const wd = wardAt(lat, lon);
    showTip(evt, [h("b", null, wd.code + " " + wd.name), wd.name_ta]);
    return;
  }
  const pt = best[2];
  showTip(evt, [h("b", null, pt[0]), DEPT_SHORT[S.mapData.departments[pt[3]]] + " · P" + pt[4] + " · " + pt[6] + " report(s)", (pt[5] ? "open" : "resolved") + " · week " + pt[7]]);
}
function renderHotspotTable() {
  const hot = S.hot, ev = hot.evaluation;
  $("#hsSub").textContent = "eps " + hot.eps_m + " m · minPts " + hot.min_pts + " · " + hot.clusters.length + " clusters";
  const er = clear($("#hsEval"));
  const matched = hot.clusters.filter((c) => c.planted).length;
  [["Hotspots found", hot.clusters.length, "current settings"], ["Match planted", matched + " / " + hot.clusters.length, "precision " + (hot.clusters.length ? pct(matched / hot.clusters.length, 0) : "–")],
    ["Default settings", pct(ev.persistent_recall, 0), "recall of 6 planted persistent hotspots"], ["Centre error", (ev.mean_center_error_m || 0).toFixed(0) + " m", "mean, matched clusters"]]
    .forEach((t) => er.appendChild(h("div", { class: "eval" }, h("div", { class: "lab" }, t[0]), h("div", { class: "val" }, t[1]), h("div", { class: "small" }, t[2]))));
  const tb = clear($("#hsTbl tbody"));
  hot.clusters.forEach((c) => tb.appendChild(h("tr", null, h("td", { class: "nw" }, h("b", null, c.id)), h("td", null, DEPT_SHORT[c.dept]), h("td", null, c.ward, h("div", { class: "meta" }, c.ward_name)),
    h("td", { class: "num nw" }, c.n), h("td", { class: "num nw" }, c.radius_m.toFixed(0) + " m"), h("td", { class: "num" }, c.recent_4w),
    h("td", { class: "nw" }, c.planted ? h("span", { class: "ok-mark" }, "✓ " + c.planted + " (" + c.planted_error_m.toFixed(0) + " m)") : h("span", { class: "no-mark" }, "not planted")))));
  if (!hot.clusters.length) tb.appendChild(h("tr", null, h("td", { colspan: 7, class: "meta" }, "No cluster at these settings. Lower minPts or raise eps.")));
}
async function loadHeat() {
  const d = $("#hDept").value;
  S.heat = await api("/api/heatgrid" + (d ? "?dept=" + d : ""));
  drawHeat();
}
function heatColor(v, max) {
  const t = Math.min(1, v / (max || 1));
  const stops = [css("--seq0"), css("--seq1"), css("--seq2"), css("--seq3"), css("--seq4")];
  return stops[Math.min(4, Math.floor(t * 4.999))];
}
function drawHeat() {
  const c = $("#heatGrid"), hg = S.heat;
  if (!c.clientWidth || !hg) return;
  const rows = hg.rows.length, cols = hg.weeks.length, lw = 150, top = 20, ch = 19;
  const hh = top + rows * ch + 6;
  const { ctx, w } = setupCanvas(c, hh);
  const cw = (w - lw - 8) / cols;
  ctx.clearRect(0, 0, w, hh);
  ctx.font = "11px system-ui, sans-serif"; ctx.fillStyle = css("--muted"); ctx.textAlign = "center";
  hg.weeks.forEach((wk, j) => ctx.fillText("W" + wk, lw + j * cw + cw / 2, 13));
  ctx.textAlign = "right";
  hg.rows.forEach((r, i) => {
    const y = top + i * ch;
    ctx.fillStyle = css("--ink-2"); ctx.fillText(r.ward + " " + r.name, lw - 8, y + 13);
    r.counts.forEach((v, j) => {
      ctx.fillStyle = heatColor(v, hg.max);
      ctx.fillRect(lw + j * cw + 1, y + 1, cw - 2, ch - 2);
      if (r.flags[j]) { ctx.strokeStyle = css("--ink"); ctx.lineWidth = 2; ctx.strokeRect(lw + j * cw + 2, y + 2, cw - 4, ch - 4); }
    });
  });
  ctx.textAlign = "left";
  S._heatGeom = { lw, top, ch, cw };
}
function heatHover(evt) {
  const g = S._heatGeom, hg = S.heat;
  if (!g || !hg) return;
  const r = $("#heatGrid").getBoundingClientRect(), x = evt.clientX - r.left, y = evt.clientY - r.top;
  const j = Math.floor((x - g.lw) / g.cw), i = Math.floor((y - g.top) / g.ch);
  if (i < 0 || j < 0 || i >= hg.rows.length || j >= hg.weeks.length) { hideTip(); return; }
  const row = hg.rows[i];
  showTip(evt, [h("b", null, row.ward + " " + row.name), "Week " + hg.weeks[j] + " (from " + hg.week_starts[j] + ")", row.counts[j] + " incidents" + (row.flags[j] ? " · EMERGING" : "")]);
}
async function loadEmerging() {
  const wk = $("#emWeek").value || 13;
  const res = await api("/api/emerging?week=" + wk);
  const ev = res.evaluation;
  $("#emSub").textContent = "week of " + res.week_start;
  const er = clear($("#emEval"));
  [["Planted surges caught", ev.surges_detected.length + " / " + ev.planted_surges, ev.surges_detected.join(", ")], ["False flags", ev.false_flags, "of " + num(ev.tested_cells) + " ward-weeks (" + pct(ev.false_flag_rate, 1) + ")"]]
    .forEach((t) => er.appendChild(h("div", { class: "eval" }, h("div", { class: "lab" }, t[0]), h("div", { class: "val" }, t[1]), h("div", { class: "small" }, t[2]))));
  const box = clear($("#emList"));
  if (!res.flags.length) box.appendChild(h("p", { class: "note" }, "Nothing unusual in week " + wk + "."));
  res.flags.forEach((f) => box.appendChild(emItem(f)));
}

// ------------------------------------------------------------------ SLA tab
async function renderSlaTab() {
  if (!S.rendered.sla) {
    [S.sla, S.risk, S.wards] = await Promise.all([api("/api/sla"), api("/api/at-risk?limit=40"), api("/api/wards")]);
    const kd = $("#kmDept");
    if (!kd.options.length) {
      S.sla.departments.forEach((d) => kd.appendChild(h("option", { value: d.dept }, d.name)));
      kd.value = "WATER";
      kd.addEventListener("change", drawKM);
    }
    S.rendered.sla = true;
  }
  drawKM();
  boxChart($("#boxChart"), S.sla.departments.map((d) => Object.assign({ label: DEPT_SHORT[d.dept], sla: d.sla_days }, d.stats)));
  const tb = clear($("#scoreTbl tbody"));
  $("#scoreSub").textContent = "clock " + fmtTs(S.sla.now) + " · overall KM median " + days(S.sla.overall_median);
  S.sla.departments.forEach((d) => tb.appendChild(h("tr", null, h("td", null, h("b", null, d.name)), h("td", { class: "num" }, d.sla_days + " d"),
    h("td", { class: "num" }, num(d.received)), h("td", { class: "num" }, d.open), h("td", { class: "num" + (d.open_breached ? " sla-bad" : "") }, d.open_breached),
    h("td", { class: "num" }, days(d.stats.median)), h("td", { class: "num" }, days(d.stats.p90)), h("td", { class: "num" }, days(d.km_median)),
    h("td", { class: "num" }, d.open_after_sla_pct.toFixed(0) + "%"), h("td", { class: "num" }, compBar(d.compliance_4w)), h("td", { class: "num" }, num(d.duplicates)))));
  const rk = S.risk;
  $("#riskSub").textContent = rk.n_at_risk + " of " + rk.n_open_within_sla + " open complaints likely to breach (≥ " + pct(rk.threshold, 0) + ") · " + rk.n_overdue + " already overdue";
  const rb = clear($("#riskTbl tbody"));
  rk.at_risk.forEach((c) => rb.appendChild(h("tr", null, h("td", { class: "txt" }, idLink(c.id), h("div", { class: "meta wrap", title: c.text }, c.text.slice(0, 80) + (c.text.length > 80 ? "…" : ""))),
    h("td", null, DEPT_SHORT[c.dept]), h("td", null, priBadge(c.priority)), h("td", { class: "num" }, c.hours_left.toFixed(0) + " h"),
    h("td", { class: "num" }, h("b", { class: c.breach_risk >= rk.threshold ? "sla-bad" : "" }, pct(c.breach_risk, 0))),
    h("td", { class: "meta wrap" }, c.factors.map((f) => feat(f.feature)).join(", ") || "—"))));
  if (!rk.at_risk.length) rb.appendChild(h("tr", null, h("td", { colspan: 6, class: "meta" }, "No open complaint inside its SLA window.")));
  const be = S.sla.breach_model, er = clear($("#breachEval"));
  [["ROC-AUC", be.auc.toFixed(3), "weeks " + be.test_weeks + " hold-out (n=" + be.n_test + ")"], ["Dept-rate baseline", be.auc_dept_baseline.toFixed(3), "AUC of 'breach rate of the department'"],
    ["Precision / recall", pct(be.precision, 0) + " / " + pct(be.recall, 0), "at risk ≥ " + pct(be.threshold, 0)], ["Brier", be.brier.toFixed(3), "base rate " + pct(be.test_rate, 0)]]
    .forEach((t) => er.appendChild(h("div", { class: "eval" }, h("div", { class: "lab" }, t[0]), h("div", { class: "val" }, t[1]), h("div", { class: "small" }, t[2]))));
  divBars($("#breachChart"), be.top_risk_factors.slice(0, 6).concat(be.top_protective.slice(0, 5)).map((f) => ({ label: feat(f.feature), value: f.weight })), { caption: true });
  const wb = clear($("#wardTbl tbody"));
  S.wards.wards.forEach((w) => wb.appendChild(h("tr", null, h("td", { class: "num" }, w.rank), h("td", null, h("b", null, w.ward + " " + w.name), " ", h("span", { class: "meta" }, w.name_ta)),
    h("td", { class: "num" }, num(w.complaints)), h("td", { class: "num" }, num(w.incidents)), h("td", { class: "num" }, w.open), h("td", { class: "num" }, w.p1),
    h("td", { class: "num" }, days(w.median_res)), h("td", { class: "num" }, compBar(w.breach_rate, true)))));
}
function compBar(v, bad) {
  if (v === null || v === undefined) return "–";
  const wrap = h("span", { style: "display:inline-flex;align-items:center;gap:6px;justify-content:flex-end" });
  const track = h("span", { style: "display:inline-block;width:70px;height:7px;border-radius:4px;background:" + css("--grid") + ";overflow:hidden" },
    h("span", { style: "display:block;height:100%;width:" + (100 * v).toFixed(0) + "%;background:" + (bad ? css("--brand") : css("--s1")) }));
  wrap.appendChild(track); wrap.appendChild(h("span", null, pct(v, 0)));
  return wrap;
}
function drawKM() {
  const code = $("#kmDept").value, d = S.sla.departments.find((x) => x.dept === code);
  lineChart($("#kmChart"), {
    xs: d.curve.map((p) => p.day), xNumeric: true, height: 280, yMax: 100, yFmt: (v) => v.toFixed(0) + "%",
    xLabel: (i) => d.curve[i].day + "d", tipTitle: (i) => "after " + d.curve[i].day + " days",
    series: [{ name: DEPT_SHORT[code], color: css("--s2"), values: d.curve.map((p) => p.open_pct) },
      { name: "all depts", color: css("--s4"), values: S.sla.overall_curve.map((p) => p.open_pct), dash: "5 4" }],
    vlines: [{ x: d.sla_days, label: "SLA " + d.sla_days + " d", color: css("--brand") }], directLabels: false,
  });
}

// ------------------------------------------------------------------ models tab
async function renderModelsTab() {
  if (!S.models) S.models = await api("/api/models");
  const M = S.models, R = M.routing;
  $("#routeSub").textContent = R.n_train + " train / " + R.n_test + " test complaints · " + num(R.n_features) + " features (word 1-2 grams, grapheme 3-4 grams, concepts) · split " + R.split;
  const tl = clear($("#routeTiles"));
  ["lr", "nb"].forEach((k) => {
    const m = R.models[k];
    tl.appendChild(h("div", { class: "eval" }, h("div", { class: "lab" }, m.label), h("div", { class: "val" }, pct(m.accuracy) + " acc · F1 " + m.macro_f1.toFixed(3)),
      h("div", { class: "small" }, "Tamil " + pct(m.by_language.ta.accuracy, 0) + " · Tanglish " + pct(m.by_language.tg.accuracy, 0) + " · English " + pct(m.by_language.en.accuracy, 0) + " · ECE " + m.ece.toFixed(3) + " · train " + m.train_s + " s · " + m.predict_ms.toFixed(2) + " ms/doc")));
  });
  tl.appendChild(h("div", { class: "eval" }, h("div", { class: "lab" }, "NB and LR agree"), h("div", { class: "val" }, pct(R.agreement, 0)), h("div", { class: "small" }, "disagreements are flagged for a human")));
  const cats = R.departments.map((d) => DEPT_SHORT[d]);
  groupedBars($("#f1Chart"), cats, [{ name: "Logistic regression", color: css("--s2"), values: R.models.lr.per_class.map((p) => p.f1) },
    { name: "Naive Bayes", color: css("--s1"), values: R.models.nb.per_class.map((p) => p.f1) }], { max: 1 });
  const drawCM = () => {
    const cm = R.models[$("#cmModel").value].confusion, wrap = clear($("#cmTable"));
    const max = Math.max(...cm.flat());
    const t = h("table", { class: "tbl cm" }, h("thead", null, h("tr", null, h("th", null, "true ↓ / predicted →"), R.departments.map((c) => h("th", { class: "num", title: DEPT_SHORT[c] }, CODE3[c])))),
      h("tbody", null, cm.map((row, i) => h("tr", null, h("th", { class: "rowh" }, cats[i]), row.map((v, j) => h("td", { class: "cell", style: "background:" + (v ? (i === j ? "rgba(42,120,214," + (0.15 + 0.6 * v / max).toFixed(2) + ")" : "rgba(220,38,38," + Math.min(0.75, 0.15 + 3 * v / max).toFixed(2) + ")") : "transparent") }, v || ""))))));
    wrap.appendChild(t);
  };
  const drawTW = () => {
    const box = clear($("#topWords")), k = $("#twModel").value;
    R.departments.forEach((d) => box.appendChild(h("div", { class: "tw" }, h("div", { class: "d" }, R.dept_names[R.departments.indexOf(d)]), R.models[k].top_words[d].map((w) => h("span", { class: "w" }, w)))));
  };
  if (!S.rendered.modelsInit) { $("#cmModel").addEventListener("change", drawCM); $("#twModel").addEventListener("change", drawTW); S.rendered.modelsInit = true; }
  drawCM(); drawTW();
  const mk = clear($("#mistakes"));
  R.mistakes.slice(0, 6).forEach((m) => mk.appendChild(h("div", { class: "mistake" }, h("div", { class: "q" }, "“" + m.text + "”"), h("div", { class: "meta" }, "true " + DEPT_SHORT[m.true] + " → predicted " + DEPT_SHORT[m.pred]))));
  // urgency
  const U = M.urgency;
  $("#urgSub").textContent = U.n_test + " hold-out complaints · under-triage = truly P1/P2 sent to P3/P4";
  const ub = clear($("#urgTbl tbody"));
  [["rules", "Safety rules only"], ["model", "Model only (TF-IDF + rule features, OvR LR)"], ["combined", "Rules + model (served)"]].forEach(([k, lab]) => {
    const v = U.variants[k];
    ub.appendChild(h("tr", null, h("td", null, k === "combined" ? h("b", null, lab) : lab), h("td", { class: "num" }, pct(v.accuracy)), h("td", { class: "num" }, v.macro_f1.toFixed(3)),
      h("td", { class: "num" }, pct(v.p1_recall)), h("td", { class: "num" }, pct(v.p1_precision)), h("td", { class: "num" }, pct(v.under_triage))));
  });
  const rb = clear($("#rulesTbl tbody"));
  U.rules.forEach((r) => rb.appendChild(h("tr", null, h("td", null, r.label), h("td", null, h("span", { class: "rule-chip " + r.kind }, r.kind)), h("td", { class: "num" }, r.fires), h("td", { class: "num" }, (r.weight_p1 > 0 ? "+" : "") + r.weight_p1.toFixed(2)))));
  // duplicates
  const D = M.duplicates;
  $("#dupSub").textContent = "learned on weeks " + D.tune_weeks + ", measured on weeks " + D.eval_weeks + " (" + num(D.n_eval) + " complaints)";
  const dt = clear($("#dupTiles"));
  [["Pairwise F1", D.pairwise.f1.toFixed(3), "P " + pct(D.pairwise.precision, 0) + " · R " + pct(D.pairwise.recall, 0)], ["Text-only baseline", D.text_only_baseline.f1.toFixed(3), "MinHash ≥ 0.5, no geo"],
    ["Place+time baseline", D.geo_time_baseline.f1.toFixed(3), "≤ 100 m, ≤ 2 days"], ["LSH work saved", pct(D.lsh.reduction, 1), num(D.lsh.candidate_pairs) + " of " + num(D.lsh.all_pairs) + " pairs; recall " + pct(D.lsh.candidate_recall, 0)]]
    .forEach((t) => dt.appendChild(h("div", { class: "eval" }, h("div", { class: "lab" }, t[0]), h("div", { class: "val" }, t[1]), h("div", { class: "small" }, t[2]))));
  const sum = (a) => a.reduce((x, y) => x + y, 0) || 1;
  const dupShare = D.sim_hist.dup.map((v) => v / sum(D.sim_hist.dup)), nonShare = D.sim_hist.non_dup.map((v) => v / sum(D.sim_hist.non_dup));
  const xs = dupShare.map((_, i) => (i + 0.5) / 10);
  lineChart($("#lshChart"), {
    xs, xNumeric: true, height: 180, yMax: 1, yFmt: (v) => v.toFixed(2), xLabel: (i) => xs[i].toFixed(2), tipTitle: (i) => "similarity " + (i / 10).toFixed(1) + "-" + ((i + 1) / 10).toFixed(1),
    series: [{ name: "P(candidate)", color: css("--ink-2"), values: xs.map((x) => 1 - Math.pow(1 - Math.pow(x, D.lsh.rows), D.lsh.bands)) },
      { name: "true duplicates", color: css("--s2"), values: dupShare }, { name: "other pairs", color: css("--s1"), values: nonShare }],
  });
  lineChart($("#tuneChart"), {
    xs: D.tuning.map((t) => t.threshold), xNumeric: true, height: 140, yMax: 1, yFmt: (v) => v.toFixed(1), xLabel: (i) => D.tuning[i].threshold.toFixed(2),
    tipTitle: (i) => "threshold " + D.tuning[i].threshold, vlines: [{ x: D.threshold, label: "chosen " + D.threshold, color: css("--brand") }],
    series: [{ name: "precision", color: css("--s1"), values: D.tuning.map((t) => t.precision) }, { name: "recall", color: css("--s3"), values: D.tuning.map((t) => t.recall) }, { name: "F1", color: css("--s2"), values: D.tuning.map((t) => t.f1) }],
  });
  const HS = M.hotspots, EM = M.emerging, B = M.breach, oe = clear($("#otherEval"));
  [["Hotspot precision", pct(HS.precision, 0), HS.matched + " of " + HS.detected + " DBSCAN clusters are planted"], ["Hotspot recall", pct(HS.persistent_recall, 0), "of 6 planted persistent hotspots · centre error " + (HS.mean_center_error_m || 0).toFixed(0) + " m"],
    ["Emerging surges", EM.surges_detected.length + " / " + EM.planted_surges, EM.false_flags + " false flags in " + num(EM.tested_cells) + " ward-weeks"], ["Breach AUC", B.auc.toFixed(3), "vs " + B.auc_dept_baseline.toFixed(3) + " department baseline"]]
    .forEach((t) => oe.appendChild(h("div", { class: "eval" }, h("div", { class: "lab" }, t[0]), h("div", { class: "val" }, t[1]), h("div", { class: "small" }, t[2]))));
  const tm = clear($("#timings"));
  Object.entries(M.timings).forEach(([k, v]) => tm.appendChild(h("span", null, k.replace(/_s$/, "") + ": " + v + " s")));
}

// ------------------------------------------------------------------ topics tab
async function renderTopicsTab() {
  const sel = $("#tK");
  if (!sel.options.length) {
    for (let k = 3; k <= 8; k++) sel.appendChild(h("option", { value: k }, k));
    sel.addEventListener("change", async () => { S.topics = await api("/api/topics?k=" + sel.value); drawTopics(); });
  }
  if (!S.topics) { S.topics = await api("/api/topics"); sel.value = S.topics.k; }
  drawTopics();
}
function drawTopics() {
  const T = S.topics;
  $("#tHint").textContent = T.n_docs + " incidents routed to General / Other · best k by silhouette = " + T.best_k + " · purity vs planted sub-topics " + pct(T.purity, 0);
  hbars($("#silChart"), T.silhouette.map((r) => ({ label: "k = " + r.k, value: r.silhouette, color: r.k === T.k ? css("--brand") : css("--s1"), note: "inertia " + r.inertia })), { labelW: 50, fmt: (v) => v.toFixed(3), max: 1 });
  const box = clear($("#topicCards"));
  T.clusters.forEach((c) => box.appendChild(h("div", { class: "card" },
    h("div", { class: "card-h" }, h("h3", null, "Topic " + (c.topic + 1) + " · " + c.size + " incidents"), h("span", { class: "sub" }, c.recent_4w + " in last 4 weeks")),
    h("div", { class: "terms" }, c.terms.map((t) => h("span", null, t))),
    h("div", { class: "meta wrap" }, "matches planted '" + c.planted_topic + "' (" + pct(c.purity, 0) + " pure) · " + Object.entries(c.languages).map(([k, v]) => (LANG[k] || k) + " " + v).join(", ")),
    c.examples.map((e) => h("div", { class: "ex" }, idLink(e.id), " ", e.text)))));
}

document.addEventListener("DOMContentLoaded", boot);
