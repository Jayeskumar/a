"use strict";
/* LogSentinel dashboard - vanilla JS, no dependencies, no network beyond /api. */

const SEV_ORDER = ["critical", "high", "medium", "low", "info"];
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

function cssvar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
function sevColor(s) { return cssvar("--sev-" + s) || cssvar("--accent"); }

function el(tag, attrs, kids) {
  const n = document.createElement(tag);
  if (attrs) for (const k in attrs) {
    if (k === "class") n.className = attrs[k];
    else if (k === "html") n.innerHTML = attrs[k];
    else if (k === "text") n.textContent = attrs[k];
    else if (k.startsWith("on") && typeof attrs[k] === "function") n.addEventListener(k.slice(2), attrs[k]);
    else if (attrs[k] != null) n.setAttribute(k, attrs[k]);
  }
  if (kids) (Array.isArray(kids) ? kids : [kids]).forEach(c => c != null && n.append(c.nodeType ? c : document.createTextNode(c)));
  return n;
}
function svg(tag, attrs) {
  const n = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const k in attrs) if (attrs[k] != null) n.setAttribute(k, attrs[k]);
  return n;
}
async function api(path, opts) {
  const r = await fetch(path, opts);
  const t = await r.text();
  let j; try { j = JSON.parse(t); } catch (e) { j = { raw: t }; }
  if (!r.ok) throw new Error((j && j.error) || ("HTTP " + r.status));
  return j;
}
function fmtTime(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  return d.toLocaleString(undefined, { month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
function fmtAxis(epoch) {
  const d = new Date(epoch * 1000);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" }) + " " +
    d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });
}
const CLOCK_FMT = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
function fmtClock(iso) {
  if (!iso) return "-";
  return CLOCK_FMT.format(new Date(iso));   // cached formatter: the live tail formats thousands of lines
}

const state = { summary: null, alerts: [], incidents: [], rpm: null };

/* ----------------------------------------------------------- load + render */
async function loadAll() {
  const [summary, alerts, incidents, rpm] = await Promise.all([
    api("/api/summary"), api("/api/alerts"), api("/api/incidents"), api("/api/rpm"),
  ]);
  state.summary = summary; state.alerts = alerts.alerts;
  state.incidents = incidents.incidents; state.rpm = rpm.points;
  renderSummary(summary);
  populateCategoryFilter(summary.categories);
  renderAlertTable();
  renderIncidents();
  renderRpm(rpm.points);
}

function renderSummary(s) {
  $("#source-label").textContent = s.source_label;
  $("#source-label").title = s.source_label;
  const sev = s.severity;
  const kpis = [
    { v: s.events.toLocaleString(), l: "log lines analysed" },
    { v: s.alerts, l: "alerts raised" },
    { v: s.incidents, l: "incidents" },
    { v: sev.critical + sev.high, l: "critical + high", crit: (sev.critical + sev.high) > 0 },
  ];
  $("#kpis").replaceChildren(...kpis.map(k =>
    el("div", { class: "kpi" + (k.crit ? " crit" : "") }, [
      el("div", { class: "v", text: String(k.v) }),
      el("div", { class: "l", text: k.l }),
    ])));
  $("#tabcount-alerts").textContent = s.alerts ? "(" + s.alerts + ")" : "";
  $("#tabcount-incidents").textContent = s.incidents ? "(" + s.incidents + ")" : "";
  renderDonut(sev);
  renderAttackers(s.top_attackers);
  renderCategories(s.categories);
  const bn = $("#blocklist-note");
  const nblock = Object.values(s.top_attackers).length;
  bn.textContent = nblock ? (s.top_attackers.length + " IP(s) flagged medium+") : "";
}

/* ---- donut ---- */
function polar(cx, cy, r, deg) {
  const a = (deg - 90) * Math.PI / 180;
  return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
}
function arcPath(cx, cy, r, start, end) {
  const [x0, y0] = polar(cx, cy, r, end);
  const [x1, y1] = polar(cx, cy, r, start);
  const large = end - start <= 180 ? 0 : 1;
  return `M ${x0} ${y0} A ${r} ${r} 0 ${large} 0 ${x1} ${y1}`;
}
function renderDonut(sev) {
  const total = SEV_ORDER.reduce((a, s) => a + (sev[s] || 0), 0);
  const wrap = $("#donut"); wrap.replaceChildren();
  const size = 180, cx = size / 2, cy = size / 2, r = 70, sw = 24;
  const s = svg("svg", { viewBox: `0 0 ${size} ${size}`, width: size, height: size, role: "img", "aria-label": "Alerts by severity" });
  if (total === 0) {
    s.append(svg("circle", { cx, cy, r, fill: "none", stroke: cssvar("--surface-3"), "stroke-width": sw }));
  } else {
    let acc = 0;
    const gap = 3; // degrees of surface gap between segments
    SEV_ORDER.forEach(name => {
      const v = sev[name] || 0; if (!v) return;
      const frac = v / total, span = frac * 360;
      const a0 = acc + (span > gap ? gap / 2 : 0);
      const a1 = acc + span - (span > gap ? gap / 2 : 0);
      const p = svg("path", { d: arcPath(cx, cy, r, a0, a1), fill: "none", stroke: sevColor(name), "stroke-width": sw, "stroke-linecap": "butt" });
      s.append(p);
      acc += span;
    });
  }
  s.append(svg("text", { x: cx, y: cy + 2, "text-anchor": "middle", fill: cssvar("--text"), "font-size": 32, "font-weight": 700 }));
  s.lastChild.textContent = total;
  s.append(svg("text", { x: cx, y: cy + 22, "text-anchor": "middle", fill: cssvar("--muted"), "font-size": 12 }));
  s.lastChild.textContent = "alerts";
  wrap.append(s);
  const legend = el("div", { class: "legend" });
  SEV_ORDER.forEach(name => {
    const v = sev[name] || 0;
    legend.append(el("div", { class: "legend-row" }, [
      el("span", { class: "swatch", style: `background:${sevColor(name)}` }),
      el("span", { text: name }),
      el("span", { class: "n", text: String(v) }),
    ]));
  });
  wrap.append(legend);
}

function renderAttackers(rows) {
  const box = $("#attackers"); box.replaceChildren();
  if (!rows.length) { box.append(el("p", { class: "muted small", text: "No attacker IPs." })); return; }
  const max = Math.max(...rows.map(r => r.score));
  rows.forEach(r => {
    box.append(el("div", { class: "bar-row" }, [
      el("button", { class: "ip", type: "button", title: "Show the " + r.alerts + " alert(s) from " + r.src, text: r.src, onclick: () => filterToSrc(r.src) }),
      el("div", { class: "bar-track", title: r.alerts + " alert(s): " + r.categories.join(", ") }, el("div", { class: "bar-fill", style: `width:${Math.max(4, 100 * r.score / max)}%;background:${sevColor(r.worst)}` })),
      el("span", { class: "val", text: String(r.score) }),
    ]));
  });
}
function renderCategories(cats) {
  const box = $("#categories"); box.replaceChildren();
  const ents = Object.entries(cats);
  if (!ents.length) { box.append(el("p", { class: "muted small", text: "No categories." })); return; }
  const max = Math.max(...ents.map(e => e[1]));
  ents.forEach(([name, n]) => {
    box.append(el("div", { class: "cat-row" }, [
      el("span", { class: "cname", text: name, title: name }),
      el("span", { class: "ctrack" }, el("span", { class: "cbar", style: `width:${Math.max(8, 100 * n / max)}%` })),
      el("span", { class: "cn", text: String(n) }),
    ]));
  });
}

/* ---- rpm chart ---- */
function renderRpm(points) {
  const wrap = $("#rpm"); wrap.replaceChildren();
  if (!points || !points.length) { wrap.append(el("p", { class: "muted small", text: "No data." })); return; }
  const W = Math.max(300, Math.round(wrap.clientWidth || 1000));
  const H = W < 560 ? 200 : 260, pad = { l: 52, r: 14, t: 14, b: 28 };
  const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
  const maxY = Math.max(...points.map(p => p.count), ...points.map(p => p.baseline)) * 1.1 || 1;
  const n = points.length;
  const X = i => pad.l + (n === 1 ? iw / 2 : iw * i / (n - 1));
  const Y = v => pad.t + ih - ih * Math.min(v, maxY) / maxY;
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none", role: "img", "aria-label": "Requests per minute" });

  // gridlines + y labels
  for (let g = 0; g <= 4; g++) {
    const y = pad.t + ih * g / 4, val = Math.round(maxY * (1 - g / 4));
    s.append(svg("line", { x1: pad.l, y1: y, x2: W - pad.r, y2: y, stroke: cssvar("--grid"), "stroke-width": 1 }));
    const tx = svg("text", { x: pad.l - 8, y: y + 4, "text-anchor": "end", fill: cssvar("--muted"), "font-size": 12 });
    tx.textContent = val; s.append(tx);
  }
  const yt = svg("text", { x: 13, y: pad.t + ih / 2, "text-anchor": "middle", fill: cssvar("--muted"), "font-size": 12, transform: `rotate(-90 13 ${pad.t + ih / 2})` });
  yt.textContent = "requests / min"; s.append(yt);
  // x time labels (dated, evenly spaced; fewer on narrow screens)
  const nt = W < 560 ? 3 : 5;
  for (let k = 0; k < nt; k++) {
    const i = Math.round((n - 1) * k / (nt - 1));
    const t = svg("text", { x: X(i), y: H - 8, "text-anchor": k === 0 ? "start" : k === nt - 1 ? "end" : "middle", fill: cssvar("--muted"), "font-size": 12 });
    t.textContent = fmtAxis(points[i].t); s.append(t);
  }

  // observed area + line
  let area = `M ${X(0)} ${Y(0)}`, line = "";
  points.forEach((p, i) => { area += ` L ${X(i)} ${Y(p.count)}`; line += (i ? " L " : "M ") + X(i) + " " + Y(p.count); });
  area += ` L ${X(n - 1)} ${Y(0)} Z`;
  const grad = svg("linearGradient", { id: "rpmg", x1: 0, y1: 0, x2: 0, y2: 1 });
  grad.append(svg("stop", { offset: "0%", "stop-color": cssvar("--accent"), "stop-opacity": 0.35 }));
  grad.append(svg("stop", { offset: "100%", "stop-color": cssvar("--accent"), "stop-opacity": 0 }));
  const defs = svg("defs", {}); defs.append(grad); s.append(defs);
  s.append(svg("path", { d: area, fill: "url(#rpmg)", stroke: "none" }));
  // baseline (EWMA) dashed
  let bl = ""; points.forEach((p, i) => { bl += (i ? " L " : "M ") + X(i) + " " + Y(p.baseline); });
  s.append(svg("path", { d: bl, fill: "none", stroke: cssvar("--baseline"), "stroke-width": 1.5, "stroke-dasharray": "5 4" }));
  s.append(svg("path", { d: line, fill: "none", stroke: cssvar("--accent"), "stroke-width": 2 }));
  // anomaly markers
  points.forEach((p, i) => {
    if (!p.anomaly) return;
    s.append(svg("circle", { cx: X(i), cy: Y(p.count), r: 5, fill: cssvar("--sev-critical"), stroke: cssvar("--surface"), "stroke-width": 2 }));
  });

  // crosshair + hover
  const cross = svg("line", { x1: 0, y1: pad.t, x2: 0, y2: pad.t + ih, stroke: cssvar("--text-dim"), "stroke-width": 1, opacity: 0 });
  const dot = svg("circle", { r: 4, fill: cssvar("--accent"), stroke: cssvar("--surface"), "stroke-width": 2, opacity: 0 });
  s.append(cross); s.append(dot);
  const tip = el("div", { class: "rpm-tip" });
  wrap.append(s); wrap.append(tip);
  const rect = svg("rect", { x: pad.l, y: pad.t, width: iw, height: ih, fill: "transparent" });
  s.append(rect);
  function move(ev) {
    const b = s.getBoundingClientRect();
    const rel = (ev.clientX - b.left) / b.width * W;
    let i = Math.round((rel - pad.l) / (iw / (n - 1)));
    i = Math.max(0, Math.min(n - 1, i));
    const p = points[i];
    cross.setAttribute("x1", X(i)); cross.setAttribute("x2", X(i)); cross.setAttribute("opacity", 1);
    dot.setAttribute("cx", X(i)); dot.setAttribute("cy", Y(p.count)); dot.setAttribute("opacity", 1);
    tip.style.opacity = 1;
    tip.style.left = (X(i) / W * b.width) + "px";
    tip.style.top = (Y(p.count) / H * b.height) + "px";
    tip.innerHTML = `${fmtClock(new Date(p.t * 1000).toISOString())} · <b>${p.count}</b> req/min` +
      `<br>baseline ${p.baseline} · z ${p.z}` + (p.anomaly ? ` · <span style="color:${cssvar("--sev-critical")}">ANOMALY</span>` : "");
  }
  rect.addEventListener("mousemove", move);
  rect.addEventListener("mouseleave", () => { cross.setAttribute("opacity", 0); dot.setAttribute("opacity", 0); tip.style.opacity = 0; });
}

/* ----------------------------------------------------------- alerts table */
function populateCategoryFilter(cats) {
  const sel = $("#f-category");
  const cur = sel.value;
  sel.replaceChildren(el("option", { value: "", text: "all" }));
  Object.keys(cats).forEach(c => sel.append(el("option", { value: c, text: c })));
  sel.value = cur;
}
function sevPill(s) { return el("span", { class: "sev sev-" + s, text: s }); }

function currentFilters() {
  return { severity: $("#f-severity").value, category: $("#f-category").value, src: $("#f-src").value.trim() };
}
async function renderAlertTable() {
  const f = currentFilters();
  const qs = new URLSearchParams();
  if (f.severity) qs.set("severity", f.severity);
  if (f.category) qs.set("category", f.category);
  if (f.src) qs.set("src", f.src);
  const data = await api("/api/alerts?" + qs.toString());
  const tb = $("#alert-rows"); tb.replaceChildren();
  $("#alert-total").textContent = data.total + " alert" + (data.total === 1 ? "" : "s");
  if (!data.alerts.length) { tb.append(el("tr", {}, el("td", { colspan: 6, class: "muted", text: "No alerts match these filters." }))); return; }
  data.alerts.forEach(a => {
    const tr = el("tr", { onclick: () => openAlert(a.id) }, [
      el("td", {}, sevPill(a.severity)),
      el("td", { class: "mono", text: a.rule }),
      el("td", {}, el("div", {}, [el("b", { text: a.title }), el("div", { class: "muted small", text: a.detail.slice(0, 96) + (a.detail.length > 96 ? "…" : "") })])),
      el("td", { class: "mono", text: a.src || "-" }),
      el("td", { class: "small", text: fmtTime(a.start) }),
      el("td", {}, a.mitre.slice(0, 2).map(m => el("span", { class: "chip", text: m.id }))),
    ]);
    tb.append(tr);
  });
}

async function openAlert(id) {
  const a = await api("/api/alert/" + id);
  const body = $("#drawer-body"); body.replaceChildren();
  body.append(el("h2", {}, [sevPill(a.severity), " ", a.title]));
  body.append(el("p", { class: "muted small", text: a.rule + " · " + a.category }));
  body.append(el("p", { text: a.detail }));

  const kv = el("dl", { class: "kv" });
  kv.append(el("dt", { text: "Source IP" }), el("dd", { text: a.src || "n/a" }));
  kv.append(el("dt", { text: "First seen" }), el("dd", { text: fmtTime(a.start) }));
  kv.append(el("dt", { text: "Last seen" }), el("dd", { text: fmtTime(a.end) }));
  kv.append(el("dt", { text: "Evidence" }), el("dd", { text: a.evidence_count + " line(s)" }));
  body.append(kv);

  body.append(el("h3", { text: "MITRE ATT&CK" }));
  a.mitre.forEach(m => body.append(el("div", { class: "mitre-item" }, [
    el("div", {}, [el("span", { class: "mid", text: m.id }), " ", el("span", { class: "mname", text: m.name })]),
    m.why ? el("div", { class: "mwhy", text: m.why }) : null,
  ])));

  body.append(el("h3", { text: "Evidence (showing " + a.evidence.length + " of " + a.evidence_count + ")" }));
  body.append(el("pre", { class: "evidence", text: a.evidence.join("\n") }));

  body.append(el("h3", { text: "Recommended response" }));
  body.append(el("ol", { class: "resp-list" }, a.response.map(r => el("li", { text: r }))));
  openDrawer();
}

/* ----------------------------------------------------------- incidents */
function renderIncidents() {
  const box = $("#incident-list"); box.replaceChildren();
  if (!state.incidents.length) { box.append(el("p", { class: "muted", text: "No incidents." })); return; }
  state.incidents.forEach(inc => {
    const card = el("div", { class: "inc-card sev-" + inc.severity, onclick: () => openIncident(inc.id) });
    const head = el("div", { class: "inc-head" }, [
      el("span", { class: "iid", text: inc.id }),
      sevPill(inc.severity),
      el("span", { class: "isrc", text: inc.src || "n/a" }),
      el("span", { class: "muted small", text: inc.alert_count + " alert" + (inc.alert_count === 1 ? "" : "s") }),
      el("span", { class: "grow" }),
      el("span", { class: "muted small", text: fmtTime(inc.start) }),
    ]);
    card.append(head);
    card.append(el("div", { class: "inc-sum", text: inc.summary }));
    const kc = el("div", { class: "killchain" });
    inc.phases.forEach((p, i) => {
      if (i) kc.append(el("span", { class: "kc-arrow", text: "→" }));
      kc.append(el("span", { class: "kc-step", text: p }));
    });
    card.append(kc);
    const mi = el("div", { style: "margin-top:8px" }, inc.mitre.map(m => el("span", { class: "chip", text: m.id + " " + m.name })));
    card.append(mi);
    box.append(card);
  });
}

async function openIncident(id) {
  const inc = await api("/api/incident/" + id);
  const body = $("#drawer-body"); body.replaceChildren();
  body.append(el("h2", {}, [sevPill(inc.severity), " Incident ", inc.id]));
  body.append(el("p", { class: "muted small", text: inc.summary }));

  const kv = el("dl", { class: "kv" });
  kv.append(el("dt", { text: "Source IP" }), el("dd", { text: inc.src || "n/a" }));
  kv.append(el("dt", { text: "Window" }), el("dd", { text: fmtTime(inc.start) + " → " + fmtTime(inc.end) }));
  kv.append(el("dt", { text: "Kill-chain" }), el("dd", { text: inc.phases.join(" → ") }));
  body.append(kv);

  body.append(el("h3", { text: "Kill-chain timeline" }));
  const tl = el("ul", { class: "timeline" });
  inc.timeline.forEach(t => {
    tl.append(el("li", { class: "tl-item sev-" + t.severity }, [
      el("div", { class: "tl-phase", text: t.phase }),
      el("div", { text: t.title }),
      el("div", { class: "tl-time", text: fmtTime(t.ts) + " · " + t.rule }),
    ]));
  });
  body.append(tl);

  body.append(el("h3", { text: "Alerts in this incident" }));
  (inc.alerts || []).forEach(a => {
    body.append(el("div", { class: "mitre-item", style: "cursor:pointer", onclick: () => openAlert(a.id) }, [
      el("div", {}, [sevPill(a.severity), " ", el("b", { text: a.title })]),
      el("div", { class: "mwhy", text: a.detail.slice(0, 120) }),
    ]));
  });

  body.append(el("h3", { text: "Export" }));
  body.append(el("div", { class: "btn-row" }, [
    el("button", { class: "btn btn-primary", text: "Open HTML report", onclick: () => window.open("/api/report/" + id + "?format=html", "_blank") }),
    el("button", { class: "btn", text: "Download Markdown", onclick: () => downloadText("/api/report/" + id + "?format=md", id + ".md") }),
  ]));
  openDrawer();
}

/* ----------------------------------------------------------- drawer */
function openDrawer() { $("#drawer").hidden = false; $("#drawer-scrim").hidden = false; }
function closeDrawer() { $("#drawer").hidden = true; $("#drawer-scrim").hidden = true; }

/* ----------------------------------------------------------- live tail */
const tail = { buf: [], offset: 0, done: false, playing: false, timer: null, lit: 0, loading: false };
async function tailFetch() {
  if (tail.done || tail.loading) return;
  tail.loading = true;
  try {
    const d = await api("/api/stream?offset=" + tail.offset + "&limit=500");
    tail.buf.push(...d.events); tail.offset = d.next; tail.done = d.done;
    $("#tail-progress").textContent = tail.cursor + " / " + d.total + " lines";
    tail.total = d.total;
  } finally { tail.loading = false; }
}
function tailReset() {
  tail.buf = []; tail.offset = 0; tail.done = false; tail.cursor = 0; tail.lit = 0; tail.total = 0;
  $("#tail-console").replaceChildren();
  $("#tail-alertcount").textContent = "0 alerts lit";
  $("#tail-progress").textContent = "0 / 0 lines";
}
function tailStep() {
  if (tail.cursor >= tail.buf.length) {
    if (tail.done) { tailStop(true); return; }
    tailFetch(); return; // wait for buffer
  }
  const e = tail.buf[tail.cursor++];
  const con = $("#tail-console");
  const cls = "tail-line" + (e.sev ? " hit sev-" + e.sev : "");
  const row = el("div", { class: cls });
  if (e.sev) { row.append(el("span", { class: "badge", text: e.sev.toUpperCase() })); tail.lit++; $("#tail-alertcount").textContent = tail.lit + " alerts lit"; }
  row.append(el("span", { class: "ts", text: fmtClock(e.iso) + " " }));
  row.append(document.createTextNode(e.line));
  con.append(row);
  if (tail.buf.length - tail.cursor < 450) tailFetch();
}
function tailPaint() {   // once per tick, not per line: avoids a forced layout for every appended line
  const con = $("#tail-console");
  while (con.childElementCount > 500) con.removeChild(con.firstChild);   // keep DOM bounded
  con.scrollTop = con.scrollHeight;
  $("#tail-progress").textContent = tail.cursor + " / " + (tail.total || tail.buf.length) + " lines";
}
function tailLoop() {
  if (!tail.playing) return;
  let n = Math.max(1, Math.round(+$("#tail-speed").value / 40));
  // Fast-forward through plain benign traffic so the replay reaches the attacks quickly;
  // drop back to the chosen speed as soon as an alerted line is within the look-ahead.
  if ($("#tail-ffwd").checked) {
    let quiet = tail.buf.length - tail.cursor > 0;
    for (let k = tail.cursor; k < Math.min(tail.buf.length, tail.cursor + 150); k++) if (tail.buf[k].sev) { quiet = false; break; }
    if (quiet) n = Math.max(n, 120);
    $("#tail-progress").classList.toggle("ffwd", quiet);
  }
  for (let i = 0; i < n && tail.playing; i++) tailStep();
  tailPaint();
  if (tail.playing) tail.timer = setTimeout(tailLoop, 40);
}
function tailPlay() {
  tail.playing = true;
  $("#tail-play").disabled = true; $("#tail-pause").disabled = false;
  if (!tail.buf.length) tailFetch().then(tailLoop); else tailLoop();
}
function tailStop(finished) {
  tail.playing = false;
  clearTimeout(tail.timer);
  $("#tail-play").disabled = false; $("#tail-pause").disabled = true;
  $("#tail-progress").classList.remove("ffwd");
  if (finished) $("#tail-play").textContent = "▶ Replay finished";
}

/* ----------------------------------------------------------- upload / export */
function downloadText(url, name) {
  fetch(url).then(r => r.text()).then(t => {
    const b = new Blob([t], { type: "text/plain" });
    const a = el("a", { href: URL.createObjectURL(b), download: name });
    document.body.append(a); a.click(); a.remove();
  });
}
async function runUpload() {
  const err = $("#upload-err"); err.hidden = true;
  const text = $("#upload-text").value;
  if (!text.trim()) { err.textContent = "Paste or choose a log first."; err.hidden = false; return; }
  try {
    await api("/api/analyze", { method: "POST", headers: { "Content-Type": "text/plain" }, body: text });
    $("#upload-modal").hidden = true;
    tailReset(); $("#tail-play").textContent = "▶ Play replay";
    await loadAll();
    switchTab("alerts");
  } catch (e) { err.textContent = e.message; err.hidden = false; }
}

/* ----------------------------------------------------------- tabs + misc */
function switchTab(name) {
  $$(".tab").forEach(t => t.classList.toggle("is-active", t.dataset.tab === name));
  $$(".panel").forEach(p => p.classList.toggle("is-active", p.id === "tab-" + name));
  if (name === "eval" && !state.evalLoaded) loadEval();
  if (name === "overview" && state.rpm) renderRpm(state.rpm); // size the chart to the now-visible card
}
function filterToSrc(src) { $("#f-src").value = src; switchTab("alerts"); renderAlertTable(); }

async function loadEval() {
  state.evalLoaded = true;
  const rowsBox = $("#eval-rows"); rowsBox.replaceChildren(el("tr", {}, el("td", { colspan: 4, class: "muted", text: "measuring…" })));
  const d = await api("/api/evaluation");
  $("#eval-kpis").replaceChildren(...[
    { v: Math.round(d.recall * 100) + "%", l: "recall (" + d.labels_detected + " attacks)" },
    { v: Math.round(d.precision * 100) + "%", l: "precision (IP-level)" },
    { v: d.benign_false_positives, l: "false positives on benign-only log" },
    { v: d.throughput_lines_per_s.toLocaleString(), l: "lines/sec parse throughput" },
  ].map(k => el("div", { class: "kpi" }, [el("div", { class: "v", text: String(k.v) }), el("div", { class: "l", text: k.l })])));
  rowsBox.replaceChildren();
  Object.entries(d.per_type).forEach(([t, r]) => {
    const rec = Math.round(100 * r.detected / r.labels);
    const col = rec === 100 ? cssvar("--accent") : cssvar("--sev-high");
    const pill = el("span", { class: "sev", style: `color:${col};background:color-mix(in srgb, ${col} 16%, transparent)`, text: rec + "%" });
    rowsBox.append(el("tr", {}, [
      el("td", { text: t.replace(/_/g, " ") }),
      el("td", { class: "mono", text: String(r.labels) }),
      el("td", { class: "mono", text: String(r.detected) }),
      el("td", {}, pill),
    ]));
  });
}

function wire() {
  $$(".tab").forEach(t => t.addEventListener("click", () => switchTab(t.dataset.tab)));
  $("#btn-reset").addEventListener("click", async () => {
    $("#btn-reset").disabled = true;
    try { await api("/api/demo/reset", { method: "POST" }); tailReset(); $("#tail-play").textContent = "▶ Play replay"; await loadAll(); switchTab("overview"); }
    finally { $("#btn-reset").disabled = false; }
  });
  $("#btn-upload").addEventListener("click", () => { $("#upload-modal").hidden = false; });
  $("#upload-close").addEventListener("click", () => { $("#upload-modal").hidden = true; });
  $("#upload-run").addEventListener("click", runUpload);
  $("#upload-file").addEventListener("change", ev => {
    const f = ev.target.files[0]; if (!f) return;
    const rd = new FileReader(); rd.onload = () => { $("#upload-text").value = rd.result; }; rd.readAsText(f);
  });
  ["#f-severity", "#f-category"].forEach(s => $(s).addEventListener("change", renderAlertTable));
  $("#f-src").addEventListener("input", debounce(renderAlertTable, 250));
  $("#f-clear").addEventListener("click", () => { $("#f-severity").value = ""; $("#f-category").value = ""; $("#f-src").value = ""; renderAlertTable(); });
  $("#drawer-close").addEventListener("click", closeDrawer);
  $("#drawer-scrim").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", e => { if (e.key === "Escape") { closeDrawer(); $("#upload-modal").hidden = true; } });
  $("#btn-blocklist").addEventListener("click", () => downloadText("/api/blocklist", "logsentinel-blocklist.txt"));
  $("#tail-play").addEventListener("click", tailPlay);
  $("#tail-pause").addEventListener("click", () => tailStop(false));
  $("#tail-restart").addEventListener("click", () => { tailStop(false); tailReset(); $("#tail-play").textContent = "▶ Play replay"; });
  $("#btn-theme").addEventListener("click", () => {
    const next = document.documentElement.getAttribute("data-theme") === "light" ? "dark" : "light";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("ls-theme", next); } catch (e) {}
    if (state.rpm) renderRpm(state.rpm);        // redraw SVG with new theme colours
    if (state.summary) { renderDonut(state.summary.severity); renderAttackers(state.summary.top_attackers); }
  });
}
window.addEventListener("resize", debounce(() => { if (state.rpm) renderRpm(state.rpm); }, 200));
function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

tailReset();
wire();
loadAll().catch(e => { $("#kpis").innerHTML = '<p class="err">Failed to load: ' + e.message + "</p>"; });
