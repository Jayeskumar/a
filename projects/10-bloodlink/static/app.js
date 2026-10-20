"use strict";
/* BloodLink frontend - vanilla JS, no libraries, no network calls except our own /api. */

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const tipAttr = (html) => ` data-tip="${esc(html)}"`;
const fmt1 = (v) => (Math.round(v * 10) / 10).toFixed(1);
const fmtMin = (t) => (t == null ? "not met" : t < 60 ? `${Math.round(t)} min` : `${Math.floor(t / 60)} h ${String(Math.round(t % 60)).padStart(2, "0")} min`);

async function api(path, body) {
  const opt = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const r = await fetch("/api/" + path, opt);
  let j = {};
  try { j = await r.json(); } catch (e) { j = { error: "bad response" }; }
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("on");
  clearTimeout(toast._h);
  toast._h = setTimeout(() => t.classList.remove("on"), 4200);
}

const S = {
  meta: null, req: { hospital_id: "H1", group: "A+", units: 3, urgency: "critical" },
  match: null, sim: null, simKey: "", pts: null, ptsById: {}, inv: null, month: null,
  mc: {}, factor: "", play: null, product: "red", donors: [], donorSel: null,
};
const COMP_COLORS = { compat: "var(--c1)", distance: "var(--c2)", response: "var(--c3)", fairness: "var(--c4)" };
const STRAT_COLORS = { waves: "var(--s-red)", broadcast: "var(--s-blue)", first_come: "var(--s-aqua)" };

/* ------------------------------------------------------------------ tooltip */
(function tooltips() {
  const tip = $("#tip");
  document.addEventListener("mousemove", (e) => {
    const t = e.target && e.target.closest ? e.target.closest("[data-tip]") : null;
    if (!t) { tip.classList.remove("on"); return; }
    tip.innerHTML = t.getAttribute("data-tip");
    tip.classList.add("on");
    const w = tip.offsetWidth, h = tip.offsetHeight;
    let x = e.clientX + 14, y = e.clientY + 14;
    if (x + w > window.innerWidth - 8) x = e.clientX - w - 14;
    if (y + h > window.innerHeight - 8) y = e.clientY - h - 14;
    tip.style.left = x + "px";
    tip.style.top = y + "px";
  });
  document.addEventListener("mouseleave", () => tip.classList.remove("on"));
})();

/* ------------------------------------------------------------------ tabs */
function showTab(name) {
  $$(".tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  $$(".tab").forEach((t) => t.classList.toggle("active", t.id === "tab-" + name));
  if (name === "sim") ensureSim();
  if (name === "network") ensureNetwork();
  if (name === "donor" && !S.donors.length) loadDonors();
  try { localStorage.setItem("bl-tab", name); } catch (e) { /* storage unavailable */ }
}
$$(".tab-btn").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));

/* ------------------------------------------------------------------ map */
function makeProj(box) {
  const k = Math.cos((((box.lat0 + box.lat1) / 2) * Math.PI) / 180);
  const sc = box.sc || 620;
  return { box, W: Math.round((box.lon1 - box.lon0) * k * sc), H: Math.round((box.lat1 - box.lat0) * sc), kmPx: sc / 111.2,
    P: (lat, lon) => [(lon - box.lon0) * k * sc, (box.lat1 - lat) * sc] };
}
const REGION = makeProj({ lat0: 11.08, lat1: 11.84, lon0: 77.46, lon1: 78.36 });
let BOX, P, MW, MH, KM_PX;
function useProj(pr) { BOX = pr.box; P = pr.P; MW = pr.W; MH = pr.H; KM_PX = pr.kmPx; }
useProj(REGION);

function baseMap() {
  let g = "";
  for (let la = Math.ceil(BOX.lat0 * 10) / 10; la < BOX.lat1; la += 0.1) {
    const y = P(la, BOX.lon0)[1].toFixed(1);
    g += `<line class="gridline" x1="0" x2="${MW}" y1="${y}" y2="${y}"/>`;
  }
  for (let lo = Math.ceil(BOX.lon0 * 10) / 10; lo < BOX.lon1; lo += 0.1) {
    const x = P(BOX.lat0, lo)[0].toFixed(1);
    g += `<line class="gridline" x1="${x}" x2="${x}" y1="0" y2="${MH}"/>`;
  }
  for (const t of S.meta.towns) {
    const [x, y] = P(t.lat, t.lon);
    if (x < 0 || y < 0 || x > MW || y > MH) continue;
    // phones use larger map labels: flip names near the right edge to the left of the town so they are not cut off
    const flip = window.innerWidth <= 600 && x + 10 + t.name.length * 12 > MW;
    g += `<text class="town" x="${(flip ? x - 10 : x + 10).toFixed(1)}" y="${(y - 10).toFixed(1)}"${flip ? ' text-anchor="end"' : ""}>${esc(t.name.toUpperCase())}</text>`;
  }
  // scale bar 10 km
  g += `<g transform="translate(${MW - 92},${MH - 16})"><line x1="0" x2="${(10 * KM_PX).toFixed(1)}" y1="0" y2="0" stroke="var(--muted)" stroke-width="2"/><text class="town" x="0" y="-5">10 KM</text></g>`;
  return g;
}

function hospitalIcon(h, big) {
  const [x, y] = P(h.lat, h.lon);
  const s = big ? 1.35 : 1;
  return `<g transform="translate(${x.toFixed(1)},${y.toFixed(1)}) scale(${s})"${tipAttr(`<b>${esc(h.name)}</b><br>Hospital`)}>
    <rect x="-7" y="-7" width="14" height="14" rx="3.5" fill="var(--card)" stroke="var(--brand)" stroke-width="1.6"/>
    <path d="M-1.6 -4.6h3.2v3h3v3.2h-3v3h-3.2v-3h-3v-3.2h3z" fill="var(--brand)"/></g>`;
}

function bankIcon(b, label, scale) {
  const [x, y] = P(b.lat, b.lon);
  const s = scale || 1;
  return `<g transform="translate(${x.toFixed(1)},${y.toFixed(1)})"${tipAttr(label || `<b>${esc(b.name)}</b><br>Blood bank`)}>
    <g transform="scale(${s.toFixed(2)})"><path d="M0 -9C0 -9 -6.5 -1.5 -6.5 2.6a6.5 6.5 0 0 0 13 0C6.5 -1.5 0 -9 0 -9z" fill="var(--text)" stroke="var(--card)" stroke-width="1.5"/>
    <circle cx="0" cy="2.6" r="2.2" fill="var(--card)"/></g></g>`;
}

function legendItem(html, label) { return `<span>${html}${esc(label)}</span>`; }
const LG = {
  dot: (c, ring) => `<i class="lg-dot" style="background:${ring ? "transparent" : c};border:${ring ? "1.5px solid " + c : "0"}"></i>`,
  hosp: `<svg width="12" height="12" viewBox="-7 -7 14 14"><rect x="-6" y="-6" width="12" height="12" rx="3" fill="var(--card)" stroke="var(--brand)" stroke-width="1.6"/><path d="M-1.4 -4h2.8v2.6h2.6v2.8h-2.6v2.6h-2.8v-2.6h-2.6v-2.8h2.6z" fill="var(--brand)"/></svg>`,
  bank: `<svg width="12" height="13" viewBox="-7 -10 14 17"><path d="M0 -9C0 -9 -6.5 -1.5 -6.5 2.6a6.5 6.5 0 0 0 13 0C6.5 -1.5 0 -9 0 -9z" fill="var(--text)"/></svg>`,
};

/* ------------------------------------------------------------------ request form */
function renderForm() {
  const m = S.meta;
  $("#hospital").innerHTML = m.hospitals.map((h) => `<option value="${h.id}">${esc(h.name)}</option>`).join("");
  $("#hospital").value = S.req.hospital_id;
  $("#groupSeg").innerHTML = m.groups.map((g) => `<button type="button" data-g="${g}" class="${g === S.req.group ? "on" : ""}">${g}</button>`).join("");
  $("#urgSeg").innerHTML = m.urgencies.map((u) => `<button type="button" data-u="${u}" class="${u === S.req.urgency ? "on" : ""}">${u[0].toUpperCase() + u.slice(1)}</button>`).join("");
  $("#units").textContent = S.req.units;
}
function syncForm() {
  $("#hospital").value = S.req.hospital_id;
  $$("#groupSeg button").forEach((b) => b.classList.toggle("on", b.dataset.g === S.req.group));
  $$("#urgSeg button").forEach((b) => b.classList.toggle("on", b.dataset.u === S.req.urgency));
  $("#units").textContent = S.req.units;
}
$("#hospital").addEventListener("change", (e) => { S.req.hospital_id = e.target.value; findDonors(); });
$("#groupSeg").addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b) return; S.req.group = b.dataset.g; syncForm(); findDonors(); });
$("#urgSeg").addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b) return; S.req.urgency = b.dataset.u; syncForm(); findDonors(); });
$("#uMinus").addEventListener("click", () => { S.req.units = Math.max(1, S.req.units - 1); syncForm(); findDonors(); });
$("#uPlus").addEventListener("click", () => { S.req.units = Math.min(10, S.req.units + 1); syncForm(); findDonors(); });
$("#findBtn").addEventListener("click", () => findDonors());

/* ------------------------------------------------------------------ match */
async function findDonors() {
  try {
    S.match = await api("match", Object.assign({ limit: 40 }, S.req));
  } catch (e) { toast("Match failed: " + e.message); return; }
  S.sim = null;
  renderKpis();
  renderRank();
  renderMatchMap();
  renderExcluded();
  const h = S.meta.hospitals.find((x) => x.id === S.req.hospital_id);
  $("#simReq").textContent = `${S.req.units} unit${S.req.units > 1 ? "s" : ""} ${S.req.group} - ${S.req.urgency} - ${h ? h.name : ""}`;
  if ($("#tab-sim").classList.contains("active")) ensureSim();
}

function renderKpis() {
  const m = S.match, c = m.counts;
  const top = m.ranked[0];
  const rules = c.ineligible_by_rule || {};
  const ruleTxt = Object.entries(rules).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${v} ${k}`).join(" - ") || "none";
  const tiles = [
    ["Registry donors", c.registry, "synthetic, 7 towns"],
    ["Red-cell compatible", c.compatible, m.acceptable_groups.join(", ")],
    ["Eligible and ranked", c.ranked, "scored and explained", "accent"],
    ["Excluded by safety gates", c.ineligible + c.unavailable, `${ruleTxt}${c.unavailable ? " - " + c.unavailable + " unavailable" : ""}`],
    ["Best match ETA", top ? `${Math.round(top.travel_min)} min` : "-", top ? `${top.name} - ${fmt1(top.km)} km` : "no donor"],
    ["First wave", m.first_wave, `alerts for ${m.request.units} unit${m.request.units > 1 ? "s" : ""} + buffer`],
  ];
  $("#kpis").innerHTML = tiles.map(([l, v, s, cls]) => `<div class="card kpi ${cls || ""}"><div class="label">${esc(l)}</div><div class="value">${esc(v)}</div><div class="sub" title="${esc(s)}">${esc(s)}</div></div>`).join("");
}

function compBar(x) {
  return `<div class="bar">${x.components.map((k) => `<i style="width:${(k.points * 100).toFixed(1)}%;background:${COMP_COLORS[k.key]}"></i>`).join("")}</div>`;
}

function renderRank() {
  const m = S.match;
  $("#compLegend").innerHTML = [["compat", "Compatibility 30"], ["distance", "Proximity 30"], ["response", "Response 25"], ["fairness", "Fairness 15"]]
    .map(([k, l]) => `<span><i style="background:${COMP_COLORS[k]}"></i>${l}</span>`).join("");
  $("#rankSub").textContent = `${m.ranked_total} eligible - showing top ${m.ranked.length} - first wave highlighted`;
  if (!m.ranked.length) { $("#rankList").innerHTML = `<div class="empty">No eligible compatible donor in the registry. Check the blood bank network tab for stock.</div>`; return; }
  $("#rankList").innerHTML = m.ranked.map((x) => {
    const tip = x.components.map((k) => `${esc(k.label)}: <b>+${fmt1(k.points * 100)}</b>`).join("<br>");
    return `<div class="rank-row ${x.rank <= m.first_wave ? "wave1" : ""}" data-id="${x.id}">
      <div class="rk">${x.rank}</div>
      <div class="who"><b>${esc(x.name)}</b><span><span class="grp ${x.exact ? "" : "sub"}">${x.group}</span>${esc(x.town)} - ${x.age} y - ${x.sex}</span></div>
      <div class="dist"><b>${fmt1(x.km)} km</b><br><span class="muted">~${Math.round(x.travel_min)} min</span></div>
      <div class="bar-cell"${tipAttr(tip)}>${compBar(x)}</div>
      <div class="score">${fmt1(x.score * 100)}</div>
      <div class="detail">
        ${x.components.map((k) => `<div class="comp"><i class="sw" style="background:${COMP_COLORS[k.key]}"></i><b>${esc(k.label)}</b><span>${esc(k.detail)}</span><span class="pts">+${fmt1(k.points * 100)} / ${Math.round(k.weight * 100)}</span></div>`).join("")}
        <div class="explain">${esc(x.explanation)}</div>
      </div></div>`;
  }).join("");
  const first = $("#rankList .rank-row");
  if (first) first.classList.add("open");
}
$("#rankList").addEventListener("click", (e) => {
  const row = e.target.closest(".rank-row");
  if (!row || e.target.closest(".detail")) return;
  const open = row.classList.contains("open");
  $$("#rankList .rank-row.open").forEach((r) => r.classList.remove("open"));
  if (!open) row.classList.add("open");
  highlightDonor(row.dataset.id);
});

function highlightDonor(id) {
  useProj(REGION);
  $$("#matchMap .sel").forEach((n) => n.remove());
  const d = S.ptsById[id];
  if (!d) return;
  const [x, y] = P(d.lat, d.lon);
  const svg = $("#matchMap");
  svg.insertAdjacentHTML("beforeend", `<circle class="sel" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="11" fill="none" stroke="var(--text)" stroke-width="2"/>`);
}

function renderMatchMap() {
  useProj(REGION);
  const svg = $("#matchMap");
  svg.setAttribute("viewBox", `0 0 ${MW} ${MH}`);
  const m = S.match;
  const h = S.meta.hospitals.find((x) => x.id === S.req.hospital_id) || { lat: m.request.lat, lon: m.request.lon, name: m.request.place };
  const [hx, hy] = P(m.request.lat, m.request.lon);
  const ranked = new Map(m.ranked.map((x) => [x.id, x]));
  const rankedAll = new Set(m.ranked_ids);
  const exc = new Map(m.excluded.filter((x) => x.category !== "Incompatible").map((x) => [x.id, x]));
  let g = baseMap();
  for (const km of [10, 20, 30]) {
    g += `<circle class="ring" cx="${hx.toFixed(1)}" cy="${hy.toFixed(1)}" r="${(km * KM_PX).toFixed(1)}"/>`;
    g += `<text class="ring-label" x="${(hx + km * KM_PX * 0.707 + 3).toFixed(1)}" y="${(hy - km * KM_PX * 0.707).toFixed(1)}">${km} km</text>`;
  }
  // links to first wave
  for (const x of m.ranked.slice(0, m.first_wave)) {
    const [x1, y1] = P(x.lat, x.lon);
    g += `<line class="link" x1="${hx.toFixed(1)}" y1="${hy.toFixed(1)}" x2="${x1.toFixed(1)}" y2="${y1.toFixed(1)}"/>`;
  }
  let dots = "", ex = "", others = "";
  for (const d of S.pts) {
    const [x, y] = P(d.lat, d.lon);
    const cx = x.toFixed(1), cy = y.toFixed(1);
    if (rankedAll.has(d.id)) {
      const r = ranked.get(d.id);
      if (r && r.rank <= m.first_wave) continue;
      const t = r ? `<b>#${r.rank} ${esc(r.name)}</b> (${r.group})<br>${fmt1(r.km)} km - score ${fmt1(r.score * 100)}` : `<b>${d.id}</b> (${d.group}) - eligible, ranked lower`;
      dots += `<circle class="hit" cx="${cx}" cy="${cy}" r="3.6" fill="var(--brand)" fill-opacity=".55" stroke="var(--card)" stroke-width="1"${tipAttr(t)}/>`;
    } else if (exc.has(d.id)) {
      const e = exc.get(d.id);
      ex += `<circle class="hit" cx="${cx}" cy="${cy}" r="3.2" fill="var(--card)" stroke="var(--muted)" stroke-width="1.3"${tipAttr(`<b>${esc(e.name)}</b> (${e.group}) - excluded<br>${esc(e.reason)}`)}/>`;
    } else {
      others += `<circle cx="${cx}" cy="${cy}" r="2.2" fill="var(--map-dot)"${tipAttr(`${d.id} (${d.group}) - not compatible with ${esc(m.request.group)}`)}/>`;
    }
  }
  g += others + ex + dots;
  for (const b of S.meta.banks) g += bankIcon(b);
  for (const hh of S.meta.hospitals) if (hh.id !== S.req.hospital_id) g += hospitalIcon(hh, false);
  // first wave on top with rank numbers
  for (const x of m.ranked.slice(0, m.first_wave).reverse()) {
    const [cx, cy] = P(x.lat, x.lon);
    g += `<g class="hit" transform="translate(${cx.toFixed(1)},${cy.toFixed(1)})"${tipAttr(`<b>#${x.rank} ${esc(x.name)}</b> (${x.group})<br>${fmt1(x.km)} km - ~${Math.round(x.travel_min)} min<br>score ${fmt1(x.score * 100)}`)}>
      <circle r="8" fill="var(--brand)" stroke="var(--card)" stroke-width="2"/><text y="3.6" text-anchor="middle" font-size="10" font-weight="700" fill="#fff">${x.rank}</text></g>`;
  }
  g += `<circle class="pulse" cx="${hx.toFixed(1)}" cy="${hy.toFixed(1)}" r="16"/>`;
  g += hospitalIcon(Object.assign({}, h, { lat: m.request.lat, lon: m.request.lon }), true);
  svg.innerHTML = g;
  $("#matchLegend").innerHTML = [
    legendItem(`<i class="lg-dot" style="background:var(--brand);width:14px;height:14px"></i>`, "First wave (rank)"),
    legendItem(LG.dot("var(--brand)"), "Eligible, ranked"),
    legendItem(LG.dot("var(--muted)", true), "Compatible but excluded"),
    legendItem(LG.dot("var(--map-dot)"), "Incompatible group"),
    legendItem(LG.hosp, "Hospital"),
    legendItem(LG.bank, "Blood bank"),
  ].join("");
  const sel = $("#rankList .rank-row.open");
  if (sel) highlightDonor(sel.dataset.id);
}

let exFilter = "compat";
function renderExcluded() {
  const m = S.match;
  const cats = { compat: m.excluded.filter((x) => x.category !== "Incompatible"), Incompatible: m.excluded.filter((x) => x.category === "Incompatible") };
  const c = m.counts;
  $("#exChips").innerHTML = `<button class="chip ${exFilter === "compat" ? "on" : ""}" data-f="compat">Compatible but ineligible / unavailable (${c.ineligible + c.unavailable})</button>
    <button class="chip ${exFilter === "Incompatible" ? "on" : ""}" data-f="Incompatible">Incompatible group (${c.incompatible})</button>`;
  const rows = cats[exFilter];
  $("#exTable").innerHTML = `<tr><th>Donor</th><th>Group</th><th>Town</th><th>Gate</th><th>Reason</th></tr>` +
    (rows.length ? rows.map((x) => `<tr><td><b>${esc(x.name)}</b> <span class="muted mono">${x.id}</span></td><td><span class="grp sub">${x.group}</span></td><td>${esc(x.town)}</td><td><span class="st ${x.category === "Ineligible" ? "short" : x.category === "Unavailable" ? "low" : "none"}">${esc(x.code)}</span></td><td>${esc(x.reason)}</td></tr>`).join("")
      : `<tr><td colspan="5" class="empty">Nobody in this category.</td></tr>`);
}
$("#exChips").addEventListener("click", (e) => { const b = e.target.closest(".chip"); if (!b) return; exFilter = b.dataset.f; renderExcluded(); });

/* ------------------------------------------------------------------ charts */
function niceStep(range, n) {
  const raw = range / Math.max(1, n);
  const p = Math.pow(10, Math.floor(Math.log10(raw || 1)));
  const f = raw / p;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p;
}
function ticks(max, n) { const s = niceStep(max, n); const out = []; for (let v = 0; v <= max + 1e-9; v += s) out.push(Math.round(v * 100) / 100); return out; }

function lineChart(svg, o) {
  const vb = svg.viewBox.baseVal, W = vb.width, H = vb.height;
  const m = { l: o.ml || 30, r: o.mr || 14, t: 12, b: 22 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const xMax = o.xMax, yMax = Math.max(1, o.yMax);
  const X = (x) => m.l + (Math.min(x, xMax) / xMax) * iw, Y = (y) => m.t + ih - (y / yMax) * ih;
  let g = "";
  const yt = o.yTicks || ticks(yMax, 4);
  for (const v of yt) g += `<line class="gl" x1="${m.l}" x2="${W - m.r}" y1="${Y(v).toFixed(1)}" y2="${Y(v).toFixed(1)}"/><text class="tick" x="${m.l - 6}" y="${(Y(v) + 3.5).toFixed(1)}" text-anchor="end">${v}</text>`;
  for (const v of ticks(xMax, o.xTicks || 6)) g += `<text class="tick" x="${X(v).toFixed(1)}" y="${H - 5}" text-anchor="middle">${o.xFmt ? o.xFmt(v) : v}</text>`;
  g += `<line class="ax" x1="${m.l}" x2="${W - m.r}" y1="${Y(0)}" y2="${Y(0)}"/>`;
  const labels = [];
  for (const s of o.series) {
    const clip = o.clipX == null ? Infinity : o.clipX;
    const pts = s.points.filter((p) => p[0] <= clip);
    if (!pts.length) continue;
    let d = `M${X(pts[0][0]).toFixed(1)},${Y(pts[0][1]).toFixed(1)}`;
    for (let i = 1; i < pts.length; i++) {
      d += s.step ? `H${X(pts[i][0]).toFixed(1)}V${Y(pts[i][1]).toFixed(1)}` : `L${X(pts[i][0]).toFixed(1)},${Y(pts[i][1]).toFixed(1)}`;
    }
    const last = s.points[s.points.length - 1];
    if (s.step && clip < last[0]) d += `H${X(clip).toFixed(1)}`;
    g += `<path class="series" d="${d}" stroke="${s.color}"/>`;
    if (s.marker && s.marker[0] <= clip) labels.push({ x: X(s.marker[0]), y: Y(s.marker[1]), color: s.color, text: s.marker[2] });
  }
  labels.sort((a, b) => a.x - b.x);
  // end labels: when the next marker is close, put this label on the left of its marker so the two
  // never overlap or sit on top of the neighbouring step line; otherwise stack them vertically
  const narrow = window.innerWidth <= 600, gap = o.labelGap || (narrow ? 130 : 74), room = narrow ? 115 : 70;
  let prev = null;
  labels.forEach((l, i) => {
    const next = labels[i + 1];
    l.left = l.x > W - m.r - room || (!!next && next.x - l.x < gap && l.x - m.l > room);
    l.drop = prev && !prev.left && !l.left && l.x - prev.x < gap ? prev.drop + (narrow ? 22 : 15) : 0;
    prev = l;
    const ly = o.labelsBelow ? l.y + (narrow ? 24 : 16) + l.drop : l.y - 9 - l.drop;
    g += `<circle cx="${l.x.toFixed(1)}" cy="${l.y.toFixed(1)}" r="4.5" fill="${l.color}" stroke="var(--card)" stroke-width="2"/>`;
    g += `<text class="lbl-end" x="${(l.x + (l.left ? -7 : 7)).toFixed(1)}" y="${ly.toFixed(1)}" text-anchor="${l.left ? "end" : "start"}">${esc(l.text)}</text>`;
  });
  if (o.clipX != null && o.clipX < xMax) g += `<line class="playhead" x1="${X(o.clipX).toFixed(1)}" x2="${X(o.clipX).toFixed(1)}" y1="${m.t}" y2="${m.t + ih}"/>`;
  g += `<line class="cross" id="${svg.id}-x" x1="0" x2="0" y1="${m.t}" y2="${m.t + ih}" style="display:none"/>`;
  g += `<rect x="${m.l}" y="${m.t}" width="${iw}" height="${ih}" fill="transparent" class="hover"/>`;
  svg.innerHTML = g;
  const cross = svg.querySelector(".cross");
  const tip = $("#tip");
  svg.onmousemove = (e) => {
    const r = svg.getBoundingClientRect();
    const sx = ((e.clientX - r.left) / r.width) * W;
    if (sx < m.l || sx > W - m.r) { cross.style.display = "none"; tip.classList.remove("on"); return; }
    const xv = ((sx - m.l) / iw) * xMax;
    cross.setAttribute("x1", sx); cross.setAttribute("x2", sx); cross.style.display = "";
    const rows = o.series.map((s) => {
      const p = s.points.filter((q) => q[0] <= xv).pop();
      const v = p ? p[1] : 0;
      return `<span class="sw-line" style="background:${s.color}"></span>${esc(s.name)}: <b>${v}</b>`;
    });
    tip.innerHTML = `<b>${o.xFmt ? o.xFmt(Math.round(xv)) : Math.round(xv)}</b><br>` + rows.join("<br>");
    tip.classList.add("on");
    tip.style.left = Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 8) + "px";
    tip.style.top = (e.clientY + 14) + "px";
  };
  svg.onmouseleave = () => { cross.style.display = "none"; tip.classList.remove("on"); };
}

function sparkline(vals, w, h) {
  if (!vals.length) return "";
  const max = Math.max(1, ...vals);
  const pts = vals.map((v, i) => `${((i / (vals.length - 1)) * (w - 4) + 2).toFixed(1)},${(h - 2 - (v / max) * (h - 4)).toFixed(1)}`);
  const last = pts[pts.length - 1].split(",");
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><polyline points="${pts.join(" ")}" fill="none" stroke="var(--muted)" stroke-width="1.5" stroke-linejoin="round"/><circle cx="${last[0]}" cy="${last[1]}" r="2.5" fill="var(--brand)"/></svg>`;
}

/* ------------------------------------------------------------------ simulation */
async function ensureSim() {
  if (!S.match) return;
  const seed = parseInt($("#seed").value, 10) || 0;
  const key = JSON.stringify([S.req, seed]);
  if (S.sim && S.simKey === key) return;
  stopPlay();
  try {
    S.sim = await api("simulate", Object.assign({ seed }, S.req));
    S.simKey = key;
  } catch (e) { toast("Simulation failed: " + e.message); return; }
  renderSimStatic();
  loadMC();
}
$("#seed").addEventListener("change", () => { S.sim = null; ensureSim(); });

function simXMax() {
  const st = S.sim.strategies;
  const ends = Object.values(st).map((s) => (s.fulfilled ? s.time_to_fulfil : 360));
  return Math.min(360, Math.max(60, Math.ceil((Math.max(...ends) + 10) / 30) * 30));
}

function drawSimChart(clip) {
  const st = S.sim.strategies;
  const series = S.sim.order.map((k) => {
    const s = st[k];
    return { name: s.label, color: STRAT_COLORS[k], step: true, points: s.curve, marker: s.fulfilled ? [s.time_to_fulfil, s.units, fmtMin(s.time_to_fulfil)] : null };
  });
  lineChart($("#simChart"), { series, xMax: simXMax(), yMax: S.sim.request.units, yTicks: ticks(S.sim.request.units, Math.min(5, S.sim.request.units)), xFmt: (v) => v + "m", clipX: clip, ml: 28, mr: 20, labelsBelow: true });
}

function renderSimStatic() {
  const st = S.sim.strategies;
  $("#simLegend").innerHTML = S.sim.order.map((k) => `<span><span class="sw-line" style="background:${STRAT_COLORS[k]}"></span>${esc(st[k].label)} - ${st[k].fulfilled ? fmtMin(st[k].time_to_fulfil) : "not fulfilled in 6 h"}</span>`).join("");
  drawSimChart(null);
  const rows = [
    ["Time to fulfil", (s) => (s.fulfilled ? s.time_to_fulfil : Infinity), (s) => fmtMin(s.fulfilled ? s.time_to_fulfil : null)],
    ["Alerts / calls sent", (s) => s.alerts, (s) => s.alerts],
    ["Trips not needed", (s) => s.surplus_trips, (s) => s.surplus_trips],
    ["Wasted trips (ineligible)", (s) => s.wasted_trips, (s) => s.wasted_trips],
    ["Calls to ineligible", (s) => s.wasted_calls, (s) => s.wasted_calls],
  ];
  const order = S.sim.order;
  $("#cmpTable").innerHTML = `<tr><th></th>${order.map((k) => `<th class="n"><span class="sw-line" style="background:${STRAT_COLORS[k]}"></span>${esc(st[k].label.split(" ")[0])}</th>`).join("")}</tr>` +
    rows.map(([label, val, show]) => {
      const vals = order.map((k) => val(st[k]));
      const best = Math.min(...vals);
      return `<tr><td>${label}</td>${order.map((k, i) => `<td class="n ${vals[i] === best && vals.filter((v) => v === best).length < order.length ? "win" : ""}">${esc(show(st[k]))}</td>`).join("")}</tr>`;
    }).join("");
  const w = st.waves;
  $("#unitsDone").textContent = `0 / ${w.units}`;
  $("#clock").textContent = "0 min";
  $("#progBar").style.width = "0%";
  $("#timeline").innerHTML = `<div class="empty">Press <b>Play live timeline</b> to watch ${w.waves} wave${w.waves === 1 ? "" : "s"} unfold (${w.alerts} alerts).</div>`;
  drawSimMap(Infinity, true);
}

function evRow(e) {
  const ico = { wave: "W", accept: "+", standby: "S", decline: "-", silent: "", arrive: "A", collect: "U", fulfilled: "✓", noshow: "!", defer: "!", surplus: "i", info: "i" }[e.kind] || "";
  return `<div class="ev ${e.kind}"><span class="t">${fmt1(e.t)}m</span><span class="ico">${ico}</span><span>${esc(e.text)}${e.rank ? ` <span class="muted small">#${e.rank}</span>` : ""}</span></div>`;
}

function stopPlay() { if (S.play) { cancelAnimationFrame(S.play.raf); S.play = null; } }

function playSim() {
  if (!S.sim) return;
  stopPlay();
  const w = S.sim.strategies.waves;
  const end = simXMax();
  const dur = 10000;
  const t0 = performance.now();
  const evs = w.events;
  let shown = 0;
  $("#timeline").innerHTML = "";
  const tick = (now) => {
    const t = Math.min(end, ((now - t0) / dur) * end);
    while (shown < evs.length && evs[shown].t <= t) { $("#timeline").insertAdjacentHTML("beforeend", evRow(evs[shown])); shown++; }
    const tl = $("#timeline"); tl.scrollTop = tl.scrollHeight;
    const done = evs.filter((e) => e.kind === "collect" && e.t <= t).length;
    $("#clock").textContent = `${Math.floor(t)} min`;
    $("#unitsDone").textContent = `${done} / ${w.units}`;
    $("#progBar").style.width = `${(100 * done) / w.units}%`;
    drawSimChart(t);
    drawSimMap(t);
    if (t < end) S.play = { raf: requestAnimationFrame(tick) };
    else { S.play = null; drawSimChart(null); }
  };
  S.play = { raf: requestAnimationFrame(tick) };
}

function skipSim() {
  if (!S.sim) return;
  stopPlay();
  const w = S.sim.strategies.waves;
  $("#timeline").innerHTML = w.events.map(evRow).join("");
  const done = w.collected;
  $("#clock").textContent = `${Math.round(w.fulfilled ? w.time_to_fulfil : 360)} min`;
  $("#unitsDone").textContent = `${done} / ${w.units}`;
  $("#progBar").style.width = `${(100 * done) / w.units}%`;
  drawSimChart(null);
  drawSimMap(Infinity);
}
$("#playBtn").addEventListener("click", () => ensureSim().then(playSim));
$("#skipBtn").addEventListener("click", () => ensureSim().then(skipSim));

const SIM_STATES = {
  alerted: ["var(--c4)", "Alerted, no reply yet"], accepted: ["var(--brand)", "Accepted, on the way"],
  standby: ["var(--c1)", "Standby"], declined: ["var(--faint)", "Declined / silent"],
  donating: ["var(--c3)", "Arrived / donating"], donated: ["var(--good)", "Unit collected"],
  failed: ["var(--crit)", "No-show / deferred"], stood: ["var(--muted)", "Stood down"],
};
function drawSimMap(t, quiet) {
  const r = S.sim.request;
  useProj(makeProj({ lat0: r.lat - 0.19, lat1: r.lat + 0.19, lon0: r.lon - 0.25, lon1: r.lon + 0.25, sc: 720 }));
  const svg = $("#simMap");
  svg.setAttribute("viewBox", `0 0 ${MW} ${MH}`);
  const w = S.sim.strategies.waves;
  const state = {};
  for (const e of w.events) {
    if (e.t > t) break;
    if (e.kind === "wave" && e.ids) e.ids.forEach((id) => { state[id] = "alerted"; });
    else if (e.donor) {
      const map = { accept: "accepted", standby: "standby", decline: "declined", arrive: "donating", collect: "donated", noshow: "failed", defer: "failed", surplus: "stood" };
      if (map[e.kind]) state[e.donor] = map[e.kind];
    }
  }
  if (quiet && t === Infinity) { for (const k of Object.keys(state)) delete state[k]; }
  const [hx, hy] = P(r.lat, r.lon);
  let g = baseMap();
  for (const km of [5, 10, 20]) {
    g += `<circle class="ring" cx="${hx.toFixed(1)}" cy="${hy.toFixed(1)}" r="${(km * KM_PX).toFixed(1)}"/>`;
    g += `<text class="ring-label" x="${(hx + km * KM_PX * 0.707 + 3).toFixed(1)}" y="${(hy - km * KM_PX * 0.707).toFixed(1)}">${km} km</text>`;
  }
  for (const [id, s] of Object.entries(state)) {
    const d = S.ptsById[id];
    if (!d) continue;
    const [x, y] = P(d.lat, d.lon);
    if (s === "accepted" || s === "donating") g += `<line class="link" x1="${hx.toFixed(1)}" y1="${hy.toFixed(1)}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}"/>`;
    g += `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${s === "declined" ? 4 : 6.5}" fill="${SIM_STATES[s][0]}" stroke="var(--card)" stroke-width="2"${tipAttr(`<b>${id}</b> (${d.group})<br>${SIM_STATES[s][1]}`)}/>`;
  }
  g += hospitalIcon({ lat: r.lat, lon: r.lon, name: r.place }, true);
  svg.innerHTML = g;
  $("#simMapLegend").innerHTML = Object.values(SIM_STATES).map(([c, l]) => legendItem(LG.dot(c), l)).join("");
}

$("#commitBtn").addEventListener("click", async () => {
  if (!S.match) return;
  const seed = parseInt($("#seed").value, 10) || 0;
  try {
    const r = await api("broadcast", Object.assign({ seed }, S.req));
    const a = r.applied;
    toast(`Sent: ${a.alerted} alerted, ${a.accepted} accepted, ${a.donated} donated. Donors are now marked as contacted - the next match shows the fairness and interval effects.`);
    await loadPoints();
    await findDonors();
    S.donors = [];
    ensureSim();
  } catch (e) { toast("Broadcast failed: " + e.message); }
});

async function loadMC() {
  const key = S.factor || "default";
  if (!S.mc[key]) {
    $("#mcTable").innerHTML = `<tr><td class="empty">Running 300 simulated requests...</td></tr>`;
    try { S.mc[key] = await api("evaluate?n=300" + (S.factor ? "&factor=" + S.factor : "")); } catch (e) { toast("Evaluation failed: " + e.message); return; }
  }
  const mc = S.mc[key];
  $("#mcN").textContent = mc.n;
  $("#mcSub").textContent = `Monte Carlo over random hospital, group, 1-4 units; BloodLink faster than broadcast in ${mc.paired.vs_broadcast_faster_pct}% and than the phone list in ${mc.paired.vs_first_come_faster_pct}% of jointly fulfilled requests`;
  const cols = [["fulfilled_pct", "Fulfilled", "%"], ["within_60_pct", "In 60 min", "%"], ["within_120_pct", "In 2 h", "%"], ["median_min", "Median", " min"], ["p90_min", "P90", " min"], ["mean_alerts", "Alerts", ""], ["mean_surplus_trips", "Trips not needed", ""], ["mean_wasted_trips", "Wasted trips", ""]];
  const strat = ["waves", "broadcast", "first_come"];
  const better = { fulfilled_pct: "max", within_60_pct: "max", within_120_pct: "max", median_min: "min", p90_min: "min", mean_alerts: "min", mean_surplus_trips: "min", mean_wasted_trips: "min" };
  $("#mcTable").innerHTML = `<tr><th>Strategy</th>${cols.map((c) => `<th class="n">${c[1]}</th>`).join("")}</tr>` +
    strat.map((k) => `<tr><td><span class="sw-line" style="background:${STRAT_COLORS[k]}"></span>${esc(mc[k].label)}</td>${cols.map(([c, , u]) => {
      const vals = strat.map((s) => mc[s][c]).filter((v) => v != null);
      const best = better[c] === "max" ? Math.max(...vals) : Math.min(...vals);
      const v = mc[k][c];
      return `<td class="n ${v === best ? "win" : ""}">${v == null ? "-" : v + u}</td>`;
    }).join("")}</tr>`).join("");
}
$("#factorSeg").addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b) return;
  $$("#factorSeg button").forEach((x) => x.classList.toggle("on", x === b));
  S.factor = b.dataset.f; loadMC();
});

/* ------------------------------------------------------------------ network */
async function ensureNetwork(force) {
  if (!S.inv || force) {
    try { S.inv = await api("inventory"); } catch (e) { toast("Inventory failed: " + e.message); return; }
    renderNetwork();
  }
  if (!S.month) {
    try { S.month = await api("inventory/month?seeds=20"); } catch (e) { toast("Month simulation failed: " + e.message); return; }
    renderMonth();
  }
}

const ST_LABEL = { short: "SHORT", low: "LOW", "expiry-risk": "RISK", ok: "", excess: "", idle: "no demand", none: "" };
function renderNetwork() {
  const inv = S.inv, groups = S.meta.groups;
  const total = inv.banks.reduce((a, b) => a + b.total_units, 0);
  const atRisk = inv.banks.reduce((a, b) => a + b.at_risk, 0);
  const shortCells = inv.banks.reduce((a, b) => a + Object.values(b.groups).filter((s) => s.status === "short" || s.status === "low").length, 0);
  const shipments = new Set(inv.transfers.map((t) => t.from + t.to)).size;
  const bt = inv.forecast_backtest;
  const tiles = [
    ["Red-cell units in stock", total, `${inv.banks.length} banks, day ${inv.today}`],
    ["Projected to expire unused", atRisk, "FEFO projection at forecast demand", "accent"],
    ["Bank x group cells short/low", shortCells, `< ${inv.target_cover_days} days of cover`],
    ["Suggested transfers", `${inv.transfer_units} units`, `${shipments} routes, ${inv.transfers.length} group moves`],
    ["Forecast error (MA-7)", `${bt.mae_ma7}/day`, `naive yesterday: ${bt.mae_naive}/day (MAE, 180 d)`],
    ["Expiring in 5 days", inv.expiring_soon_total, inv.expiring_soon[0] ? `first: ${inv.expiring_soon[0].group} at ${inv.expiring_soon[0].bank}` : "none"],
  ];
  $("#netKpis").innerHTML = tiles.map(([l, v, s, cls]) => `<div class="card kpi ${cls || ""}"><div class="label">${esc(l)}</div><div class="value">${esc(v)}</div><div class="sub" title="${esc(s)}">${esc(s)}</div></div>`).join("");
  let h = `<tr><th>Bank</th>${groups.map((g) => `<th class="n" style="text-align:center">${g}</th>`).join("")}<th class="n">Total</th><th class="n">Demand/day</th><th>Last 28 days</th></tr>`;
  for (const b of inv.banks) {
    h += `<tr><td><b>${esc(b.name.replace(" (demo)", ""))}</b><br><span class="muted small">${esc(b.town)}</span></td>`;
    for (const g of groups) {
      const s = b.groups[g];
      const tip = `<b>${esc(b.town)} ${g}</b><br>${s.units} units, ${s.at_risk} projected to expire unused<br>forecast ${s.rate}/day - cover ${s.days_cover == null ? "n/a" : s.days_cover + " d"}<br>target ${s.target} units${s.earliest_days_left != null ? `<br>first expiry in ${s.earliest_days_left} d` : ""}`;
      h += `<td class="cell ${s.status}"${tipAttr(tip)}><div class="u">${s.units}</div><div class="c">${s.days_cover == null ? "-" : s.days_cover > 99 ? "99+ d" : s.days_cover + " d"}</div><div class="ic">${ST_LABEL[s.status] || ""}${s.at_risk && (s.status === "ok" || s.status === "excess") ? s.at_risk + " risk" : ""}</div></td>`;
    }
    h += `<td class="n"><b>${b.total_units}</b></td><td class="n">${b.demand_ma}</td><td>${sparkline(b.history, 110, 28)}</td></tr>`;
  }
  h += `<tr><td><b>Network</b></td>${groups.map((g) => { const n = inv.network[g]; return `<td class="cell"><div class="u">${n.units}</div><div class="c">${n.days_cover == null ? "-" : n.days_cover + " d"}</div></td>`; }).join("")}<td class="n"><b>${total}</b></td><td class="n">${fmt1(inv.banks.reduce((a, b) => a + b.demand_ma, 0))}</td><td></td></tr>`;
  $("#invTable").innerHTML = h;

  $("#trSummary").textContent = inv.transfers.length ? `${inv.transfer_units} units across ${inv.transfers.length} moves` : "No transfers needed right now";
  $("#trList").innerHTML = inv.transfers.length ? inv.transfers.map((t) => `<div class="transfer">
      <div class="route">${esc(t.from_name.replace(" Blood Centre", ""))} &rarr; ${esc(t.to_name.replace(" Blood Centre", ""))} <span class="grp">${t.group}</span> <b>${t.units}</b> unit${t.units > 1 ? "s" : ""}</div>
      <div><span class="prio ${t.priority}">${t.priority}</span> <span class="muted small">${fmt1(t.km)} km</span></div>
      <div class="why">${esc(t.reason)}</div></div>`).join("") : `<div class="empty">Stock is balanced.</div>`;
  renderNetMap();
  const fb = $("#fBank");
  if (!fb.options.length) {
    fb.innerHTML = S.meta.banks.map((b) => `<option value="${b.id}">${esc(b.name.replace(" (demo)", ""))}</option>`).join("");
    $("#fGroup").innerHTML = groups.map((g) => `<option ${g === "O+" ? "selected" : ""}>${g}</option>`).join("");
  }
}

function renderNetMap() {
  useProj(REGION);
  const svg = $("#netMap");
  svg.setAttribute("viewBox", `0 0 ${MW} ${MH}`);
  const inv = S.inv;
  let g = `<defs><marker id="arrowHead" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="var(--brand)"/></marker></defs>`;
  g += baseMap();
  const pos = {};
  inv.banks.forEach((b) => { pos[b.id] = P(b.lat, b.lon); });
  const routes = {};
  for (const t of inv.transfers) {
    const k = t.from + ">" + t.to;
    (routes[k] = routes[k] || { from: t.from, to: t.to, units: 0, parts: [], km: t.km }).units += t.units;
    routes[k].parts.push(`${t.units} ${t.group}`);
  }
  for (const r of Object.values(routes)) {
    const [x1, y1] = pos[r.from], [x2, y2] = pos[r.to];
    const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
    const dx = x2 - x1, dy = y2 - y1, len = Math.hypot(dx, dy) || 1;
    const off = Math.min(40, len * 0.18);
    const cx = mx - (dy / len) * off, cy = my + (dx / len) * off;
    // shorten the end so the arrow stops before the icon
    const ex = x2 - (dx / len) * 12, ey = y2 - (dy / len) * 12;
    const wdt = Math.min(6, 1.5 + r.units / 8);
    const tip = `<b>${esc(r.from)} &rarr; ${esc(r.to)}</b> (${fmt1(r.km)} km)<br>${esc(r.parts.join(", "))}`;
    g += `<path d="M${x1.toFixed(1)},${y1.toFixed(1)} Q${cx.toFixed(1)},${cy.toFixed(1)} ${ex.toFixed(1)},${ey.toFixed(1)}" fill="none" stroke="var(--brand)" stroke-opacity=".75" stroke-width="${wdt.toFixed(1)}" marker-end="url(#arrowHead)"${tipAttr(tip)}/>`;
    const lx = 0.25 * x1 + 0.5 * cx + 0.25 * x2, ly = 0.25 * y1 + 0.5 * cy + 0.25 * y2;
    g += `<g${tipAttr(tip)}><rect x="${(lx - 16).toFixed(1)}" y="${(ly - 9).toFixed(1)}" width="32" height="17" rx="8" fill="var(--card)" stroke="var(--brand)" stroke-width="1"/><text x="${lx.toFixed(1)}" y="${(ly + 3.5).toFixed(1)}" text-anchor="middle" font-size="10.5" font-weight="700" fill="var(--text)">${r.units}</text></g>`;
  }
  for (const h of S.meta.hospitals) g += hospitalIcon(h, false);
  for (const b of inv.banks) {
    const sc = 1 + Math.min(1.2, b.total_units / 160);
    const tip = `<b>${esc(b.name)}</b><br>${b.total_units} units - demand ~${b.demand_ma}/day<br>${b.at_risk} projected to expire unused${b.short_groups.length ? "<br>short/low: " + b.short_groups.join(", ") : ""}`;
    g += bankIcon(b, tip, sc);
    const [x, y] = pos[b.id];
    g += `<text x="${(x + 12).toFixed(1)}" y="${(y + 14).toFixed(1)}" font-size="11" font-weight="700" fill="var(--text)">${b.total_units}</text>`;
  }
  svg.innerHTML = g;
  $("#netLegend").innerHTML = [legendItem(LG.bank, "Blood bank (size = stock, number = units)"), legendItem(`<span class="sw-line" style="background:var(--brand)"></span>`, "Suggested transfer (label = units)"), legendItem(LG.hosp, "Hospital")].join("");
}

$("#applyTr").addEventListener("click", async () => {
  try {
    const r = await api("inventory/transfers/apply", {});
    toast(`Moved ${r.moved} units on ${r.shipments} routes (demo: delivered instantly). Stock and risk recomputed.`);
    ensureNetwork(true);
  } catch (e) { toast("Apply failed: " + e.message); }
});

$("#fIssue").addEventListener("click", async () => {
  const body = { bank_id: $("#fBank").value, group: $("#fGroup").value, units: parseInt($("#fUnits").value, 10) || 1, allow_substitutes: $("#fSub").checked };
  try {
    const r = await api("inventory/issue", body);
    $("#fResult").innerHTML = `<div class="small" style="margin-bottom:6px">${esc(r.explanation)}.</div>` +
      (r.issued.length ? `<table class="tbl"><tr><th>Unit</th><th>Group</th><th>Tier</th><th>Additive</th><th>Expires</th><th class="n">Days left</th></tr>${r.issued.map((u) => `<tr><td class="mono">${u.id}</td><td><span class="grp ${u.tier === "exact" ? "" : "sub"}">${u.group}</span></td><td>${u.tier}</td><td>${u.additive}</td><td>${u.expires}</td><td class="n">${u.days_left}</td></tr>`).join("")}</table>` : "") +
      (r.unmet ? `<div class="verdict no">${r.unmet} unit${r.unmet > 1 ? "s" : ""} short - use a transfer or a donor request</div>` : "");
    ensureNetwork(true);
  } catch (e) { toast("Issue failed: " + e.message); }
});

function renderMonth() {
  const m = S.month, s = m.summary;
  $("#monthSub").textContent = `${s.days} days x ${s.seeds} random months, same demand and collections in both`;
  const tiles = [
    ["Expired units", `${Math.round(s.without.expired.mean)} → ${Math.round(s.with.expired.mean)}`, `-${s.expired_reduction_pct}% with transfers`],
    ["Unmet demand", `${Math.round(s.without.unmet.mean)} → ${Math.round(s.with.unmet.mean)}`, `-${s.unmet_reduction_pct}% units`],
    ["Units moved", Math.round(s.with.moved.mean), `of ~${Math.round(s.with.demand.mean)} demanded`],
    ["Cold-box trips", Math.round(s.with.shipments.mean), `~${Math.round(s.with.trip_km.mean)} km per month`],
  ];
  $("#monthKpis").innerHTML = tiles.map(([l, v, sub]) => `<div class="card kpi"><div class="label">${esc(l)}</div><div class="value" style="font-size:20px">${esc(v)}</div><div class="sub">${esc(sub)}</div></div>`).join("");
  const ex = m.example;
  const cum = (arr, key) => { let a = 0; return [[0, 0]].concat(arr.map((d) => [d.day + 1, (a += d[key])])); };
  const mk = (key) => [
    { name: "Without transfers", color: "var(--s-blue)", points: cum(ex.daily_without, key) },
    { name: "With BloodLink transfers", color: "var(--s-red)", points: cum(ex.daily_with, key) },
  ];
  for (const [id, key] of [["#monthExp", "expired"], ["#monthUnmet", "unmet"]]) {
    const series = mk(key);
    const yMax = Math.max(5, ...series.map((x) => x.points[x.points.length - 1][1]));
    series.forEach((x) => { const p = x.points[x.points.length - 1]; x.marker = [p[0], p[1], String(p[1])]; });
    lineChart($(id), { series, xMax: s.days, yMax: yMax * 1.12, yTicks: ticks(yMax, 4), xFmt: (v) => "d" + v, xTicks: 5, ml: 30, mr: 16, labelGap: 0 });
  }
  $("#monthLegend").innerHTML = `<span><span class="sw-line" style="background:var(--s-blue)"></span>Without transfers</span><span><span class="sw-line" style="background:var(--s-red)"></span>With BloodLink transfers</span><span class="muted">charts: month with seed 1; tiles: mean of ${s.seeds} months</span>`;
}

/* ------------------------------------------------------------------ donor app */
async function loadDonors() {
  try { S.donors = (await api("donors?limit=300")).donors; } catch (e) { toast("Donor list failed: " + e.message); return; }
  renderDonorList();
  if (!S.donorSel && S.donors.length) selectDonor(S.donors[0].id);
  // show a worked self-check with the pre-filled sample answers instead of an empty card
  if (!$("#scResult").innerHTML.trim()) $("#scBtn").click();
}
function renderDonorList() {
  const q = $("#dq").value.trim().toLowerCase();
  const rows = S.donors.filter((d) => !q || d.name.toLowerCase().includes(q) || d.id.toLowerCase().includes(q) || d.town.toLowerCase().includes(q)).slice(0, 120);
  $("#dList").innerHTML = rows.map((d) => `<div class="dl-item ${d.id === S.donorSel ? "on" : ""}" data-id="${d.id}"><span><b>${esc(d.name)}</b><br><small>${d.id} - ${esc(d.town)}</small></span><span><span class="grp">${d.group}</span><span class="st ${d.eligible && d.available ? "ok" : "short"}">${d.eligible && d.available ? "ready" : "wait"}</span></span></div>`).join("") || `<div class="empty">No match.</div>`;
}
$("#dq").addEventListener("input", renderDonorList);
$("#dList").addEventListener("click", (e) => { const it = e.target.closest(".dl-item"); if (it) selectDonor(it.dataset.id); });

const BADGE_ICON = (earned) => `<svg viewBox="0 0 28 28"><circle cx="14" cy="14" r="12" fill="${earned ? "var(--brand)" : "var(--faint)"}"/><path d="M14 6.5c0 0-5 5.8-5 8.8a5 5 0 0 0 10 0c0-3-5-8.8-5-8.8z" fill="#fff"/></svg>`;

function checksHtml(el) {
  return `<ul class="checks">${el.rules.map((r) => `<li><span class="ck ${r.pass === true ? "pass" : r.pass === false ? "fail" : "na"}">${r.pass === true ? "✓" : r.pass === false ? "✕" : "?"}</span><span><b>${esc(r.label)}</b><br><span class="muted">${esc(r.detail)}</span></span></li>`).join("")}</ul>`;
}
function verdictHtml(el, today) {
  if (el.eligible) return `<div class="verdict yes">✓ Eligible to donate today</div>`;
  if (el.next_eligible_date) return `<div class="verdict no"><span>Not yet - next eligible <b>${el.next_eligible_date}</b> (${el.days_until_eligible} days)</span></div>`;
  return `<div class="verdict no">Not eligible under these rules - please talk to the blood bank doctor</div>`;
}

async function selectDonor(id) {
  S.donorSel = id;
  $$("#dList .dl-item").forEach((x) => x.classList.toggle("on", x.dataset.id === id));
  let r;
  try { r = await api("donors/" + id); } catch (e) { toast(e.message); return; }
  const d = r.donor, el = r.eligibility;
  const ring = (() => {
    const total = el.interval_days, left = el.days_until_eligible || 0;
    const frac = el.eligible ? 1 : Math.max(0, Math.min(1, 1 - left / total));
    const C = 2 * Math.PI * 26;
    return `<svg width="70" height="70" viewBox="0 0 70 70"${tipAttr(el.eligible ? "Ready to donate" : `${left} days until eligible`)}><circle cx="35" cy="35" r="26" fill="none" stroke="var(--brand-100)" stroke-width="7"/><circle cx="35" cy="35" r="26" fill="none" stroke="${el.eligible ? "var(--good)" : "var(--brand)"}" stroke-width="7" stroke-linecap="round" stroke-dasharray="${(C * frac).toFixed(1)} ${C.toFixed(1)}" transform="rotate(-90 35 35)"/><text x="35" y="39" text-anchor="middle" font-size="13" font-weight="800" fill="var(--text)">${el.eligible ? "✓" : left + "d"}</text></svg>`;
  })();
  $("#dProfile").innerHTML = `<div class="profile-head"><div class="big-grp">${d.group}</div><div style="flex:1;min-width:0"><h3 style="margin:0">${esc(d.name)} <small class="mono">${d.id}</small></h3><div class="muted small">${esc(d.town)} - age ${el.age} - ${d.sex === "M" ? "male" : "female"} - ${d.weight_kg} kg - registered ${d.registered}</div>
      <label class="toggle small" style="margin-top:6px"><input type="checkbox" id="dAvail" ${d.available ? "checked" : ""}> Available for emergency alerts</label></div>${ring}</div>
    ${verdictHtml(el)}
    ${checksHtml(el)}
    <div class="mini-stats"><div><b>${d.donations}</b><span>donations</span></div><div><b>up to ${r.lives_helped_upto}</b><span>patients helped*</span></div><div><b>${Math.round(d.response_rate * 100)}%</b><span>${d.alerts_received ? `response (${d.alerts_accepted}/${d.alerts_received})` : "prior (no alerts yet)"}</span></div></div>
    <h3 style="margin-top:14px">Badges</h3>
    <div class="badges">${r.badges.map((b) => `<div class="badge ${b.earned ? "" : "off"}"${tipAttr(esc(b.desc))}>${BADGE_ICON(b.earned)}<b>${esc(b.name)}</b></div>`).join("")}</div>
    <p class="muted small" style="margin:10px 0 0">* one whole-blood donation separated into components can help up to 3 patients (commonly cited). Last donation: ${d.last_donation || "never"}; last alerted: ${d.last_contacted ? d.last_contacted.replace("T", " ") : "never"}.</p>`;
  $("#dAvail").addEventListener("change", async (e) => {
    try { await api(`donors/${id}/availability`, { available: e.target.checked }); toast(e.target.checked ? "You will receive emergency alerts again." : "Paused: you won't be alerted until you switch this back on."); S.donors = []; loadPoints().then(() => { if (S.match) findDonors(); }); loadDonors(); } catch (err) { toast(err.message); }
  });
}

function localToday() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
$("#scBtn").addEventListener("click", async () => {
  const body = { today: localToday(), age: parseInt($("#scAge").value, 10), sex: $("#scSex").value, weight_kg: parseFloat($("#scW").value), last_donation: $("#scLast").value || null, hb: $("#scHb").value || null, unwell: $("#scUnwell").checked };
  if (!Number.isFinite(body.age) || !Number.isFinite(body.weight_kg)) {
    $("#scResult").innerHTML = `<div class="verdict no">Please enter your age and weight.</div>`;
    return;
  }
  try {
    const el = await api("eligibility", body);
    $("#scResult").innerHTML = verdictHtml(el) + checksHtml(el) + `<p class="muted small">Rules are commonly cited Indian whole-blood criteria - verify with your blood bank. The blood bank still checks Hb, BP and history before every donation.</p>`;
  } catch (e) { $("#scResult").innerHTML = `<div class="verdict no">${esc(e.message)}</div>`; }
});

/* ------------------------------------------------------------------ method */
function renderMatrix() {
  const c = S.meta.compatibility, g = c.groups, mx = c[S.product];
  const cnt = g.reduce((a, r) => a + g.filter((d) => mx[r][d]).length, 0);
  $("#mxSub").textContent = `${S.product === "red" ? "Red cells" : "Plasma"}: rows = patient, columns = donor - ${cnt}/64 pairs compatible`;
  $("#matrix").innerHTML = `<tr><th>patient \\ donor</th>${g.map((d) => `<th>${d}</th>`).join("")}</tr>` +
    g.map((r) => `<tr><th>${r}</th>${g.map((d) => `<td class="${mx[r][d] ? "y" : "n"} ${r === d ? "exact" : ""}"${tipAttr(`${S.product === "red" ? "Red cells" : "Plasma"} from <b>${d}</b> to patient <b>${r}</b>: ${mx[r][d] ? "compatible" : "NOT compatible"}`)}>${mx[r][d] ? "✓" : "✕"}</td>`).join("")}</tr>`).join("");
  $("#mxNotes").innerHTML = c.notes.map((n) => `<li>${esc(n)}</li>`).join("");
}
$("#mxSeg").addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b) return; S.product = b.dataset.p; $$("#mxSeg button").forEach((x) => x.classList.toggle("on", x === b)); renderMatrix(); });

function renderMethod() {
  renderMatrix();
  $("#constTable").innerHTML = `<tr><th>Area</th><th>Assumption</th><th>Value</th><th>Source / reasoning</th></tr>` +
    S.meta.constants.map((c) => `<tr><td class="muted small">${esc(c.group)}</td><td>${esc(c.name)}</td><td><b>${esc(c.value)}</b></td><td class="muted small">${esc(c.source)}</td></tr>`).join("");
  $("#safetyText").textContent = S.meta.disclaimer + " Donor data in this demo is synthetic; a real deployment needs consent, data-protection compliance and blood bank SOP sign-off.";
}

/* ------------------------------------------------------------------ boot */
async function loadPoints() {
  S.pts = (await api("map")).donors;
  S.ptsById = {};
  S.pts.forEach((d) => { S.ptsById[d.id] = d; });
}

async function runDemo() {
  S.req = { hospital_id: "H1", group: "A+", units: 3, urgency: "critical" };
  syncForm();
  showTab("match");
  await findDonors();
  const sub = $("#rankSub");
  sub.textContent = "Demo: 3 units A+, critical, Tiruchengode - " + sub.textContent;
}
$("#runDemo").addEventListener("click", runDemo);
$("#resetBtn").addEventListener("click", async () => {
  try {
    await api("demo/reset", {});
    S.inv = null; S.donors = []; S.donorSel = null; S.sim = null;
    await loadPoints();
    await findDonors();
    if ($("#tab-network").classList.contains("active")) ensureNetwork(true);
    toast("Demo state restored: registry, contact history and stock reset.");
  } catch (e) { toast("Reset failed: " + e.message); }
});

(async function boot() {
  try {
    S.meta = await api("meta");
    await loadPoints();
  } catch (e) { toast("Could not reach the BloodLink server: " + e.message); return; }
  renderForm();
  renderMethod();
  await findDonors();
  let tab = "match";
  try { tab = localStorage.getItem("bl-tab") || "match"; } catch (e) { /* ignore */ }
  if (tab !== "match" && $("#tab-" + tab)) showTab(tab);
})();
