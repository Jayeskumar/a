/* AgriSky dashboard - vanilla JS, canvas + inline SVG, no external libraries. */
(function () {
  "use strict";

  // ------------------------------------------------------------------ constants
  const W = 120, H = 80;
  const SCALE = 7, PAD_L = 10, PAD_T = 2, PAD_R = 2, PAD_B = 2;
  const CW = (W + PAD_L + PAD_R) * SCALE, CH = (H + PAD_T + PAD_B) * SCALE;
  const CLASSES = ["healthy", "nitrogen", "waterlogging", "pest", "soil", "water"];
  const VEG = ["#a50026", "#d73027", "#f46d43", "#fdae61", "#fee08b", "#d9ef8b", "#a6d96a", "#66bd63", "#1a9850", "#006837"];
  const WET = ["#8c510a", "#bf812d", "#dfc27d", "#f6e8c3", "#c7eae5", "#5ab4ac", "#1d6fb8", "#08306b"];
  const DIV = ["#b2182b", "#d6604d", "#f4a582", "#fddbc7", "#f7f7f7", "#d9f0d3", "#a6dba0", "#1b7837"];
  const CLUSTER_COLORS = ["#7c3aed", "#f59e0b", "#ec4899", "#14b8a6", "#84cc16", "#6366f1", "#f97316", "#22c55e"];
  const LAYERS = [
    { id: "cir", name: "Colour-IR", caption: "False-colour infrared composite (NIR → red, Red → green, Green → blue). Dense healthy canopy glows red; thin or damaged canopy turns dull; water is near-black." },
    { id: "ndvi", name: "NDVI", index: true, ramp: VEG },
    { id: "ndre", name: "NDRE", index: true, ramp: VEG },
    { id: "gndvi", name: "GNDVI", index: true, ramp: VEG },
    { id: "savi", name: "SAVI", index: true, ramp: VEG },
    { id: "ndwi", name: "NDWI", index: true, ramp: WET },
    { id: "cluster", name: "k-means", caption: "k-means clusters over crop cells after the 3×3 mode filter (brown = bare-soil mask, blue = water mask). Colours are cluster ids ordered by NDVI." },
    { id: "stress", name: "Stress", caption: "Management zones labelled by the explainable rule list. Click a zone in the table to see which rule fired and why." },
    { id: "truth", name: "Truth", caption: "Ground truth from the synthetic generator (what the field really has) - used only to measure accuracy." },
    { id: "dndvi", name: "ΔNDVI", caption: "NDVI change since the previous flight, minus the field's median change (so normal crop growth cancels out). Red = falling faster than the rest of the field." },
    { id: "rx", name: "Prescription", caption: "Variable-rate prescription: only coloured cells get product. Pesticide = pest zones + safety ring at the full label rate; urea = nitrogen-deficient zones, dose scaled by the red-edge deficit." },
  ];
  const $ = (id) => document.getElementById(id);
  const S = {
    meta: null, metrics: null, scene: null, seed: 42, flight: 5, k: 5, layer: "stress",
    product: "pesticide", plan: "vra", selectedZone: null, missions: null, anim: null,
    playing: null, loading: false, mProduct: "pesticide",
  };

  // ------------------------------------------------------------------ helpers
  function hexRgb(h) { const n = parseInt(h.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
  function lut(stops) {
    const rgb = stops.map(hexRgb), out = [];
    for (let i = 0; i < 256; i++) {
      const t = i / 255 * (rgb.length - 1), a = Math.floor(t), b = Math.min(rgb.length - 1, a + 1), f = t - a;
      out.push([0, 1, 2].map((c) => Math.round(rgb[a][c] + (rgb[b][c] - rgb[a][c]) * f)));
    }
    return out;
  }
  const LUTS = { veg: lut(VEG), wet: lut(WET), div: lut(DIV) };
  function clamp(v, a, b) { return v < a ? a : v > b ? b : v; }
  function fmt(v, d) { return v === null || v === undefined || isNaN(v) ? "—" : Number(v).toFixed(d === undefined ? 1 : d); }
  function fmtInt(v) { return v === null || v === undefined ? "—" : Math.round(v).toLocaleString("en-IN"); }
  function esc(s) { return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
  function classInfo(c) { const m = S.meta.classes.find((x) => x.id === c); return m || { en: c, ta: c, color: "#888" }; }
  // SVG charts are drawn at their container's pixel width so 12px labels stay 12px on phones.
  function fitW(id, def) { const el = $(id), w = el && el.clientWidth; return w ? Math.max(300, Math.min(640, Math.round(w))) : def; }
  // Canvas labels scale with the displayed map size so they stay legible on small screens.
  function mapLabelScale() { const w = $("mapCanvas").clientWidth || CW; return clamp(0.85 * CW / w, 1, 2.6); }
  function cssVar(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
  async function api(path, opts) {
    const r = await fetch(path, opts);
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || ("HTTP " + r.status));
    return data;
  }
  function missionParams() {
    const num = (id, lo, hi) => clamp(parseFloat($(id).value) || lo, lo, hi);
    return {
      swath: Math.round(num("mSwath", 1, 10)), tank: num("mTank", 0.5, 40),
      endurance: num("mEndurance", 60, 3600), speed: num("mSpeed", 1, 10), orient: $("mOrient").value,
    };
  }
  const wx = (x) => (x + PAD_L) * SCALE, wy = (y) => (y + PAD_T) * SCALE;

  // ------------------------------------------------------------------ data loading
  async function init() {
    S.meta = await api("/api/meta");
    try { S.metrics = await api("/api/metrics"); } catch (e) { S.metrics = null; }
    buildTabs();
    renderAssumptions();
    bindEvents();
    await loadScene();
  }

  async function loadScene() {
    S.loading = true;
    const p = missionParams();
    const q = new URLSearchParams({ seed: S.seed, flight: S.flight, k: S.k, swath: p.swath, tank: p.tank, endurance: p.endurance, speed: p.speed, orient: p.orient });
    try {
      S.scene = await api("/api/scene?" + q.toString());
    } catch (e) {
      $("alertBox").className = "alert amber";
      $("alertBox").innerHTML = '<span class="dot"></span><div><b>Could not load field</b><p>' + esc(e.message) + "</p></div>";
      S.loading = false;
      return;
    }
    S.missions = S.mProduct === "pesticide" ? S.scene.mission : null;
    if (!S.missions) await loadMissions(true);
    const zs = S.scene.zones;
    if (S.selectedZone === null || !zs[S.selectedZone] || zs[S.selectedZone].label === "healthy") {
      const order = ["pest", "nitrogen", "waterlogging"];
      let pick = null;
      for (const lab of order) { const z = zs.filter((z) => z.label === lab).sort((a, b) => b.cells - a.cells)[0]; if (z) { pick = z.id; break; } }
      S.selectedZone = pick;
    }
    S.loading = false;
    renderAll();
  }

  async function loadMissions(silent) {
    const p = missionParams();
    const body = (plan) => JSON.stringify({ seed: S.seed, flight: S.flight, k: S.k, product: S.mProduct, plan, ...p });
    try {
      const [vra, uniform] = await Promise.all(["vra", "uniform"].map((plan) => api("/api/mission", { method: "POST", headers: { "Content-Type": "application/json" }, body: body(plan) })));
      S.missions = { vra, uniform };
      $("missionErr").textContent = "";
    } catch (e) {
      $("missionErr").textContent = e.message;
      if (!silent) return;
    }
    if (!silent) { renderMission(); drawPathStatic(); }
  }

  // ------------------------------------------------------------------ rendering
  function renderAll() {
    renderFlights(); renderAlert(); renderKpis(); renderMap(); renderZones(); renderChange();
    renderRx(); renderMission(); renderKmeans(); renderAccuracy(); renderReport();
    const href = "report.html?seed=" + S.seed + "&flight=" + S.flight + "&k=" + S.k;
    $("reportLink").href = href; $("reportLink2").href = href;
    const ex = "?seed=" + S.seed + "&flight=" + S.flight + "&k=" + S.k + "&download=1";
    $("csvLink").href = "/api/export/prescription.csv" + ex;
    $("geoLink").href = "/api/export/prescription.geojson" + ex;
  }

  function buildTabs() {
    $("layerTabs").innerHTML = LAYERS.map((l) => '<button type="button" class="tab' + (l.id === S.layer ? " active" : "") + '" data-layer="' + l.id + '" role="tab">' + esc(l.name) + "</button>").join("");
  }

  function renderFlights() {
    const fl = S.scene.flights;
    const maxPest = Math.max(1, ...fl.map((f) => f.pest_m2));
    $("flightChips").innerHTML = fl.map((f) => {
      const n = f.index + 1;
      return '<button type="button" class="flight-chip' + (n === S.flight ? " active" : "") + '" data-flight="' + n + '" role="tab">' +
        "<b>Flight " + n + "</b><span>Day " + f.day + " · " + f.das + " DAS · pest " + fmtInt(f.pest_m2) + " m²</span>" +
        '<div class="bar"><i style="width:' + (100 * f.pest_m2 / maxPest).toFixed(0) + '%"></i></div></button>';
    }).join("");
  }

  function renderAlert() {
    const a = S.scene.change.spread.alert;
    $("alertBox").className = "alert " + a.level;
    $("alertBox").innerHTML = '<span class="dot"></span><div><b>' + esc(a.title) + "</b><p>" + esc(a.en) + '</p><p class="ta">' + esc(a.ta) + "</p></div>";
  }

  function renderKpis() {
    const sc = S.scene, rep = sc.report.summary, rxp = sc.prescriptions.pesticide, rxu = sc.prescriptions.urea;
    const crop = rep.crop_ha * 1e4;
    const stressed = rep.pest_m2 + rep.nitrogen_m2 + rep.waterlogging_m2;
    const sp = sc.change.spread.front_speed_m_day;
    const mv = S.scene.mission.vra.totals, mu = S.scene.mission.uniform.totals;
    const tiles = [
      { v: fmt(100 * rep.healthy_m2 / crop, 0) + "%", l: "crop area healthy", c: "good" },
      { v: fmtInt(stressed) + " m²", l: "stressed: pest " + fmtInt(rep.pest_m2) + " · N " + fmtInt(rep.nitrogen_m2) + " · water " + fmtInt(rep.waterlogging_m2), c: "bad" },
      { v: sp === null || sp === undefined ? "—" : fmt(sp, 2) + " m/d", l: "pest front speed (" + (sc.change.spread.trend ? "+" + fmt(sc.change.spread.trend.growth_m2_day, 0) + " m²/day" : "needs 2 flights") + ")", c: "bad" },
      { v: fmt(rxp.savings.pct, 0) + "%", l: "pesticide saved vs blanket spray (urea " + fmt(rxu.savings.pct, 0) + "%)", c: "good" },
      { v: "₹" + fmtInt(rep.rs_saved), l: "chemical cost saved this round (≈ ₹" + fmtInt(rep.rs_saved / rep.crop_ha) + "/ha)", c: "good" },
      { v: mv.sorties + " vs " + mu.sorties, l: "drone sorties: prescription vs whole field (" + fmt(mv.flight_time_s / 60, 1) + " vs " + fmt(mu.flight_time_s / 60, 1) + " min)", c: "sky" },
    ];
    $("kpis").innerHTML = tiles.map((t) => '<div class="kpi ' + t.c + '"><div class="v">' + t.v + '</div><div class="l">' + esc(t.l) + "</div></div>").join("");
  }

  // ---------------- map
  function layerColorFn() {
    const L = S.scene.layers, id = S.layer;
    const cls = L.cls;
    if (id === "cir") {
      return (i) => {
        const n = L.nir[i] / 1000, r = L.red[i] / 1000, g = L.green[i] / 1000;
        const s = (v, m) => Math.round(255 * Math.pow(clamp(v / m, 0, 1), 0.8));
        return [s(n, 0.58), s(r, 0.2), s(g, 0.17)];
      };
    }
    const lay = LAYERS.find((l) => l.id === id);
    if (lay && lay.index) {
      const rng = S.meta.indices[id].range, lo = rng[0], hi = rng[1];
      const tb = id === "ndwi" ? LUTS.wet : LUTS.veg;
      const arr = L[id];
      return (i) => tb[Math.round(255 * clamp((arr[i] / 1000 - lo) / (hi - lo), 0, 1))];
    }
    if (id === "cluster") {
      const k = S.scene.k, cl = L.cluster;
      const soil = hexRgb("#a16207"), water = hexRgb("#1d4ed8"), cc = CLUSTER_COLORS.map(hexRgb);
      return (i) => cl[i] === k ? soil : cl[i] === k + 1 ? water : cc[cl[i] % cc.length];
    }
    if (id === "stress" || id === "truth") {
      const arr = id === "stress" ? cls : L.truth;
      const cols = CLASSES.map((c) => hexRgb(classInfo(c).color));
      const ref = S.scene.reference.ndvi;
      return (i) => {   // subtle shading by NDVI so within-zone vigour stays visible
        const c = cols[arr[i]];
        if (arr[i] >= 4) return c;
        const f = clamp(1 + 1.1 * (L.ndvi[i] / 1000 - ref), 0.72, 1.12);
        return [clamp(Math.round(c[0] * f), 0, 255), clamp(Math.round(c[1] * f), 0, 255), clamp(Math.round(c[2] * f), 0, 255)];
      };
    }
    if (id === "dndvi") {
      if (!L.dndvi) return () => [120, 120, 120];
      const arr = L.dndvi;
      return (i) => (cls[i] >= 4 ? [110, 105, 95] : LUTS.div[Math.round(255 * clamp((arr[i] / 1000 + 0.3) / 0.6, 0, 1))]);
    }
    if (id === "rx") {
      const urea = S.product === "urea";
      const arr = urea ? L.rx_urea : L.rx_pesticide;
      const hot = hexRgb(urea ? "#f59e0b" : "#7c3aed");
      const maxv = urea ? 90 : 400;
      return (i) => {
        const g = Math.round(40 + 140 * clamp(L.ndvi[i] / 1000, 0, 0.9));
        const base = cls[i] === 5 ? [30, 64, 140] : [g * 0.55, g * 0.62, g * 0.5];
        if (!arr[i]) return base.map(Math.round);
        const t = 0.55 + 0.45 * clamp(arr[i] / maxv, 0, 1);
        return base.map((b, c) => Math.round(b * (1 - t) + hot[c] * t));
      };
    }
    return () => [128, 128, 128];
  }

  function drawSurroundings(ctx) {
    const dark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    ctx.fillStyle = dark ? "#1b2416" : "#3f5233";
    ctx.fillRect(0, 0, CW, CH);
    ctx.fillStyle = dark ? "#3a3833" : "#6b665e";
    ctx.fillRect(0, 0, wx(-3), CH);
    ctx.strokeStyle = "rgba(255,255,255,.55)"; ctx.setLineDash([10, 10]); ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(wx(-8.5), 0); ctx.lineTo(wx(-8.5), CH); ctx.stroke(); ctx.setLineDash([]);
    const home = S.meta.defaults.home;
    ctx.fillStyle = "#0284c7"; ctx.beginPath(); ctx.arc(wx(home[0]), wy(home[1]), 13, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#fff"; ctx.font = "bold 14px system-ui, sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText("H", wx(home[0]), wy(home[1]) + 1);
    ctx.font = Math.round(11 * mapLabelScale()) + "px system-ui, sans-serif";
    const hw = ctx.measureText("home").width;
    ctx.fillText("home", Math.max(hw / 2 + 3, wx(home[0])), wy(home[1]) + 16 + 8 * mapLabelScale());
  }

  function renderMap() {
    const cv = $("mapCanvas"), ctx = cv.getContext("2d");
    drawSurroundings(ctx);
    const off = document.createElement("canvas"); off.width = W; off.height = H;
    const octx = off.getContext("2d"), img = octx.createImageData(W, H);
    const col = layerColorFn();
    for (let i = 0; i < W * H; i++) { const c = col(i); img.data[i * 4] = c[0]; img.data[i * 4 + 1] = c[1]; img.data[i * 4 + 2] = c[2]; img.data[i * 4 + 3] = 255; }
    octx.putImageData(img, 0, 0);
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(off, wx(0), wy(0), W * SCALE, H * SCALE);
    if ($("tglOutline").checked && S.layer !== "cluster") drawOutlines(ctx);
    if (S.layer === "dndvi") drawHotspots(ctx);
    drawZoneLabels(ctx);
    // compass + scale bar
    // scale bar sits in the bottom margin; its label gets a dark pill so it never blends into the crop
    const ks = mapLabelScale(), fs = Math.round(11 * ks), barY = wy(H) + 5;
    ctx.fillStyle = "rgba(255,255,255,.9)"; ctx.fillRect(wx(98), barY, 20 * SCALE, 3);
    ctx.font = "600 " + fs + "px system-ui, sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    const sw = ctx.measureText("20 m").width + 10 * ks, sh = fs + 6 * ks, sx = wx(98) + 10 * SCALE;
    ctx.fillStyle = "rgba(10,20,8,.82)"; roundRect(ctx, sx - sw / 2, barY - sh - 2, sw, sh, sh / 2); ctx.fill();
    ctx.fillStyle = "#fff"; ctx.fillText("20 m", sx, barY - sh / 2 - 1);
    ctx.textBaseline = "alphabetic"; ctx.textAlign = "left";
    const lay = LAYERS.find((l) => l.id === S.layer);
    $("mapBadge").textContent = lay.name + " · flight " + S.flight;
    let cap = lay.caption || "";
    if (lay.index) { const ii = S.meta.indices[S.layer]; cap = ii.name + " = " + ii.formula + " - " + ii.meaning + ". Reference canopy " + ii.name + " = " + fmt(S.scene.reference[S.layer], 3) + "."; }
    if (S.layer === "dndvi" && !S.scene.layers.dndvi) cap = "Flight 1 has no earlier flight to compare with - pick flight 2 or later.";
    $("mapCaption").textContent = cap;
    renderLegend();
    drawPathStatic();
  }

  function drawOutlines(ctx) {
    const z = S.scene.layers.zone;
    ctx.beginPath();
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      const i = y * W + x;
      if (x < W - 1 && z[i] !== z[i + 1]) { ctx.moveTo(wx(x + 1), wy(y)); ctx.lineTo(wx(x + 1), wy(y + 1)); }
      if (y < H - 1 && z[i] !== z[i + W]) { ctx.moveTo(wx(x), wy(y + 1)); ctx.lineTo(wx(x + 1), wy(y + 1)); }
    }
    ctx.strokeStyle = "rgba(255,255,255,.75)"; ctx.lineWidth = 1.2; ctx.stroke();
    if (S.selectedZone !== null) {
      ctx.beginPath();
      const s = S.selectedZone;
      for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
        const i = y * W + x; if (z[i] !== s) continue;
        if (x === W - 1 || z[i + 1] !== s) { ctx.moveTo(wx(x + 1), wy(y)); ctx.lineTo(wx(x + 1), wy(y + 1)); }
        if (x === 0 || z[i - 1] !== s) { ctx.moveTo(wx(x), wy(y)); ctx.lineTo(wx(x), wy(y + 1)); }
        if (y === H - 1 || z[i + W] !== s) { ctx.moveTo(wx(x), wy(y + 1)); ctx.lineTo(wx(x + 1), wy(y + 1)); }
        if (y === 0 || z[i - W] !== s) { ctx.moveTo(wx(x), wy(y)); ctx.lineTo(wx(x + 1), wy(y)); }
      }
      ctx.strokeStyle = "#facc15"; ctx.lineWidth = 3; ctx.stroke();
    }
  }

  function drawHotspots(ctx) {
    const d = S.scene.change.diff; if (!d) return;
    ctx.strokeStyle = "#fff"; ctx.setLineDash([6, 4]); ctx.lineWidth = 2;
    d.hotspots.forEach((h) => { ctx.strokeRect(wx(h.bbox[0]) - 3, wy(h.bbox[1]) - 3, (h.bbox[2] - h.bbox[0] + 1) * SCALE + 6, (h.bbox[3] - h.bbox[1] + 1) * SCALE + 6); });
    ctx.setLineDash([]);
  }

  function drawZoneLabels(ctx) {
    if (!["stress", "rx", "ndvi", "ndre", "cir"].includes(S.layer)) return;
    const ks = mapLabelScale(), fs = Math.round(11 * ks), lh = Math.round(18 * ks);
    ctx.font = "bold " + fs + "px system-ui, sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    S.scene.zones.forEach((z) => {
      if (!["pest", "nitrogen", "waterlogging"].includes(z.label) || z.cells < 40) return;
      const t = "Z" + z.id + " " + classInfo(z.label).en.split(" (")[0];
      const x = wx(z.centroid[0]), y = wy(z.centroid[1]);
      const w = ctx.measureText(t).width + 12 * ks;
      const cx = clamp(x, wx(0) + w / 2 + 2, wx(W) - w / 2 - 2);
      ctx.fillStyle = "rgba(10,20,8,.78)"; roundRect(ctx, cx - w / 2, y - lh / 2, w, lh, lh / 2); ctx.fill();
      ctx.fillStyle = "#fff"; ctx.fillText(t, cx, y + 1);
    });
  }
  function roundRect(ctx, x, y, w, h, r) { ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath(); }

  function renderLegend() {
    const id = S.layer, lay = LAYERS.find((l) => l.id === id);
    let html = "";
    const ramp = (stops, lo, hi, label) => '<span>' + label + " " + lo + '</span><span class="ramp" style="background:linear-gradient(90deg,' + stops.join(",") + ')"></span><span>' + hi + "</span>";
    if (lay.index) { const r = S.meta.indices[id].range; html = ramp(id === "ndwi" ? WET : VEG, r[0], r[1], S.meta.indices[id].name); }
    else if (id === "cir") html = '<span class="sw"><i style="background:#e0483f"></i>dense canopy</span><span class="sw"><i style="background:#8f7a6a"></i>thin / damaged</span><span class="sw"><i style="background:#6f8f77"></i>bare soil</span><span class="sw"><i style="background:#101820"></i>water</span>';
    else if (id === "stress" || id === "truth") html = CLASSES.map((c) => '<span class="sw"><i style="background:' + classInfo(c).color + '"></i>' + esc(classInfo(c).en) + "</span>").join("");
    else if (id === "cluster") html = S.scene.kmeans.centroids.map((c, j) => '<span class="sw"><i style="background:' + CLUSTER_COLORS[j % CLUSTER_COLORS.length] + '"></i>C' + j + " (NDVI " + fmt(c.ndvi, 2) + ")</span>").join("") + '<span class="sw"><i style="background:#a16207"></i>soil mask</span><span class="sw"><i style="background:#1d4ed8"></i>water mask</span>';
    else if (id === "dndvi") html = ramp(DIV, "−0.30", "+0.30", "ΔNDVI");
    else if (id === "rx") html = S.product === "urea" ? '<span class="sw"><i style="background:#f59e0b"></i>urea (kg/ha, darker = more)</span><span class="sw"><i style="background:#4a5a3a"></i>no product</span>' : '<span class="sw"><i style="background:#7c3aed"></i>pesticide @ label rate</span><span class="sw"><i style="background:#4a5a3a"></i>no spray</span><span class="sw"><i style="background:#1e408c"></i>water (3 m no-spray)</span>';
    $("legend").innerHTML = html;
  }

  // ---------------- spray path
  // animation clock: spray legs at spray speed, ferry / return legs shown 3x faster
  const ANIM_SPEED = { spray: 4, gap: 4, shift: 7, ferry: 21, rth: 21 };
  function missionLegs(m) {
    const segs = []; let total = 0, dist = 0;
    m.sorties.forEach((s) => s.legs.forEach((leg) => {
      for (let j = 1; j < leg.pts.length; j++) {
        const a = leg.pts[j - 1], b = leg.pts[j], d = Math.hypot(b[0] - a[0], b[1] - a[1]);
        const w = d / (ANIM_SPEED[leg.kind] || 7);
        segs.push({ a, b, d, w, kind: leg.kind, sortie: s.id, start: total }); total += w; dist += d;
      }
    }));
    return { segs, total, dist };
  }

  function drawSeg(ctx, sg, frac, swath, faint) {
    const a = sg.a, b = sg.b, ex = a[0] + (b[0] - a[0]) * frac, ey = a[1] + (b[1] - a[1]) * frac;
    ctx.beginPath(); ctx.moveTo(wx(a[0]), wy(a[1])); ctx.lineTo(wx(ex), wy(ey));
    if (sg.kind === "spray") {
      ctx.strokeStyle = faint ? "rgba(190,242,100,.18)" : "rgba(190,242,100,.42)"; ctx.lineWidth = swath * SCALE; ctx.lineCap = "butt"; ctx.stroke();
      ctx.beginPath(); ctx.moveTo(wx(a[0]), wy(a[1])); ctx.lineTo(wx(ex), wy(ey));
      ctx.strokeStyle = faint ? "rgba(255,255,255,.35)" : "#ecfccb"; ctx.lineWidth = 1.4; ctx.stroke();
    } else {
      ctx.setLineDash(sg.kind === "shift" || sg.kind === "gap" ? [3, 3] : [8, 6]);
      ctx.strokeStyle = faint ? "rgba(125,211,252,.35)" : "#7dd3fc"; ctx.lineWidth = sg.kind === "shift" || sg.kind === "gap" ? 1.2 : 2; ctx.stroke(); ctx.setLineDash([]);
    }
  }

  function currentMission() { return S.missions ? S.missions[S.plan] : null; }

  function drawPathStatic() {
    const cv = $("pathCanvas"), ctx = cv.getContext("2d");
    ctx.clearRect(0, 0, CW, CH);
    if (S.anim) return;
    const m = currentMission();
    if (!m || !$("tglPath").checked) return;
    const sw = m.params.swath_m, L = missionLegs(m);
    L.segs.forEach((sg) => drawSeg(ctx, sg, 1, sw, true));
  }

  function drawDrone(ctx, x, y) {
    const X = wx(x), Y = wy(y);
    ctx.fillStyle = "rgba(0,0,0,.25)"; ctx.beginPath(); ctx.arc(X + 3, Y + 4, 9, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = "#fff"; ctx.lineWidth = 2.2;
    ctx.beginPath(); ctx.moveTo(X - 9, Y - 9); ctx.lineTo(X + 9, Y + 9); ctx.moveTo(X + 9, Y - 9); ctx.lineTo(X - 9, Y + 9); ctx.stroke();
    [[-9, -9], [9, -9], [-9, 9], [9, 9]].forEach((o) => { ctx.beginPath(); ctx.arc(X + o[0], Y + o[1], 4.5, 0, Math.PI * 2); ctx.fillStyle = "rgba(186,230,253,.9)"; ctx.fill(); ctx.strokeStyle = "#0369a1"; ctx.lineWidth = 1; ctx.stroke(); });
    ctx.fillStyle = "#65A30D"; ctx.beginPath(); ctx.arc(X, Y, 4.5, 0, Math.PI * 2); ctx.fill(); ctx.strokeStyle = "#fff"; ctx.lineWidth = 1.5; ctx.stroke();
  }

  function animateMission() {
    const m = currentMission();
    if (!m || !m.sorties.length) { $("hud").style.display = "block"; $("hud").innerHTML = "Nothing to spray for this payload on this flight."; return; }
    stopAnim();
    $("tglPath").checked = true;
    const L = missionLegs(m), sw = m.params.swath_m;
    const dur = clamp(3000 + L.dist * 3.2, 4500, 16000);
    const ctx = $("pathCanvas").getContext("2d");
    const sortieInfo = {};
    m.sorties.forEach((s) => { sortieInfo[s.id] = s; });
    const sprayBySortie = {};
    L.segs.forEach((sg) => { if (sg.kind === "spray") sprayBySortie[sg.sortie] = (sprayBySortie[sg.sortie] || 0) + sg.d; });
    const t0 = performance.now();
    $("hud").style.display = "block";
    function frame(now) {
      const prog = clamp((now - t0) / dur, 0, 1), dist = prog * L.total;
      ctx.clearRect(0, 0, CW, CH);
      L.segs.forEach((sg) => drawSeg(ctx, sg, 1, sw, true));
      let pos = L.segs[0].a, cur = L.segs[0], sprayDone = {}, distInSortie = {};
      for (const sg of L.segs) {
        if (sg.start > dist) break;
        const f = clamp((dist - sg.start) / (sg.w || 1e-9), 0, 1);
        drawSeg(ctx, sg, f, sw, false);
        pos = [sg.a[0] + (sg.b[0] - sg.a[0]) * f, sg.a[1] + (sg.b[1] - sg.a[1]) * f]; cur = sg;
        if (sg.kind === "spray") sprayDone[sg.sortie] = (sprayDone[sg.sortie] || 0) + sg.d * f;
        distInSortie[sg.sortie] = (distInSortie[sg.sortie] || 0) + sg.d * f;
      }
      drawDrone(ctx, pos[0], pos[1]);
      const si = sortieInfo[cur.sortie];
      const used = si.payload * ((sprayDone[cur.sortie] || 0) / (sprayBySortie[cur.sortie] || 1));
      const batt = si.battery_pct * ((distInSortie[cur.sortie] || 0) / (si.distance_m || 1));
      const label = { spray: "spraying", ferry: "flying to field", rth: "returning home", shift: "turning to next lane", gap: "crossing gap (nozzles off)" }[cur.kind];
      $("hud").innerHTML = "<b>Sortie " + si.id + "/" + m.sorties.length + "</b> · " + label + "<br>" + esc(m.payload_name) + " left " + fmt(m.params.tank - used, 2) + " " + m.payload_unit + " · battery used " + fmt(batt, 0) + "%";
      if (prog < 1) S.anim = requestAnimationFrame(frame);
      else { S.anim = null; $("hud").innerHTML = "<b>Mission complete</b> · " + m.totals.sorties + " sortie" + (m.totals.sorties > 1 ? "s" : "") + " · " + fmt(m.totals.distance_m / 1000, 2) + " km · " + fmt(m.totals.payload, 2) + " " + m.payload_unit + " · every target cell sprayed once"; }
    }
    S.anim = requestAnimationFrame(frame);
  }
  function stopAnim() { if (S.anim) { cancelAnimationFrame(S.anim); S.anim = null; } }

  // ---------------- zones
  function renderZones() {
    const order = { pest: 0, nitrogen: 1, waterlogging: 2, healthy: 3, soil: 4, water: 5 };
    const zs = S.scene.zones.slice().sort((a, b) => order[a.label] - order[b.label] || b.cells - a.cells);
    $("zoneBadge").textContent = "k = " + S.scene.k + " · " + S.scene.raw_zone_count + " pieces → " + zs.length + " zones";
    $("zoneRows").innerHTML = zs.map((z) => {
      const ci = classInfo(z.label);
      return '<tr class="click' + (z.id === S.selectedZone ? " sel" : "") + '" data-zone="' + z.id + '"><td>Z' + z.id + '</td><td><span class="swatch" style="background:' + ci.color + '"></span>' + esc(ci.en) + (z.spreading ? ' <b style="color:var(--danger)">↗</b>' : "") +
        '</td><td class="num">' + fmtInt(z.area_m2) + '</td><td class="num">' + fmt(z.ndvi, 2) + '</td><td class="num">' + fmt(z.ndre, 2) + '</td><td class="num">' + fmt(z.confidence * 100, 0) + "%</td></tr>";
    }).join("");
    const acc = S.scene.accuracy;
    $("accBadge").textContent = "vs truth " + fmt(acc.accuracy * 100, 1) + "%";
    renderWhy();
  }

  function renderWhy() {
    const z = S.scene.zones.find((x) => x.id === S.selectedZone);
    if (!z) { $("whyBox").innerHTML = '<span class="muted">Click a zone to see the rule that fired.</span>'; return; }
    const ci = classInfo(z.label), ref = S.scene.reference;
    const tr = z.trace.map((t) => '<li class="' + (t.passed && t.rule === z.label ? "pass" : "fail") + '">' + esc(t.rule) + ": " + esc(t.text) + (t.passed ? " ✓" : " ✗") + "</li>").join("");
    $("whyBox").innerHTML = "<b>Why is Z" + z.id + " “" + esc(ci.en) + "”?</b> <span class=\"muted\">(" + esc(ci.ta) + ", confidence " + fmt(z.confidence * 100, 0) + "%)</span><div>" + esc(z.why) + "</div>" +
      '<ol>' + tr + "</ol>" +
      '<div class="muted small">Reference canopy (top-quartile NDVI cells): NDVI ' + fmt(ref.ndvi, 3) + " · NDRE " + fmt(ref.ndre, 3) + " · NIR " + fmt(ref.nir, 3) + " · Red " + fmt(ref.red, 3) + " · NDWI " + fmt(ref.ndwi, 3) + (z.ndvi_rate_week !== null ? " · zone NDVI vs field " + (z.ndvi_rate_week >= 0 ? "+" : "") + fmt(z.ndvi_rate_week, 3) + "/week" : "") + "</div>";
  }

  // ---------------- change chart
  function renderChange() {
    const ch = S.scene.change, sp = ch.spread, truth = ch.truth;
    const series = sp.series, proj = sp.projection;
    const lastDay = series[series.length - 1].day;
    let maxDay = Math.max(28, lastDay + 7);
    if (proj && !proj.already_reached) maxDay = Math.max(maxDay, Math.min(lastDay + 28, Math.ceil(proj.day) + 3));
    let maxA = Math.max(50, ...series.map((s) => s.area_m2), ...truth.series.map((s) => s.area_m2));
    if (proj) maxA = Math.max(maxA, proj.target_m2 * 1.08);
    const Wd = fitW("changeChart", 380), Hd = 200, l = 46, r = 12, t = 16, b = 26;
    const X = (d) => l + (Wd - l - r) * d / maxDay, Y = (a) => t + (Hd - t - b) * (1 - a / maxA);
    let g = '<svg viewBox="0 0 ' + Wd + " " + Hd + '" role="img" aria-label="Pest area per flight with trend and projection">';
    const grid = cssVar("--grid"), muted = cssVar("--muted");
    for (let k = 0; k <= 4; k++) { const a = maxA * k / 4; g += '<line x1="' + l + '" x2="' + (Wd - r) + '" y1="' + Y(a) + '" y2="' + Y(a) + '" stroke="' + grid + '"/><text x="' + (l - 5) + '" y="' + (Y(a) + 4) + '" font-size="12" text-anchor="end" fill="' + muted + '">' + Math.round(a) + "</text>"; }
    const dayStep = (Wd - l - r) / maxDay * 7 < 44 ? 14 : 7;
    for (let d = 0; d <= maxDay; d += dayStep) g += '<text x="' + X(d) + '" y="' + (Hd - b + 17) + '" font-size="12" text-anchor="' + (d === 0 ? "start" : "middle") + '" fill="' + muted + '">day ' + d + "</text>";
    g += '<text x="2" y="' + (t - 4) + '" font-size="12" fill="' + muted + '">m²</text>';
    if (proj) {
      g += '<line x1="' + l + '" x2="' + (Wd - r) + '" y1="' + Y(proj.target_m2) + '" y2="' + Y(proj.target_m2) + '" stroke="#dc2626" stroke-dasharray="4 4"/><text x="' + (l + 6) + '" y="' + (Y(proj.target_m2) - 5) + '" font-size="12" font-weight="600" fill="' + cssVar("--danger") + '">' + proj.target_pct + "% of crop</text>";
      const pc = proj.curve.filter((p) => p.day >= lastDay && p.day <= maxDay && p.area_m2 <= maxA);
      if (pc.length > 1) g += '<polyline fill="none" stroke="#dc2626" stroke-width="2" stroke-dasharray="5 4" points="' + pc.map((p) => X(p.day) + "," + Y(p.area_m2)).join(" ") + '"/>';
    }
    if (sp.trend) {
      const fc = proj ? proj.curve.filter((p) => p.day <= lastDay) : sp.trend.fit;
      g += '<polyline fill="none" stroke="#65A30D" stroke-width="2.4" points="' + fc.map((p) => X(p.day) + "," + Y(p.area_m2)).join(" ") + '"/>';
    }
    truth.series.forEach((p) => { g += '<circle cx="' + X(p.day) + '" cy="' + Y(p.area_m2) + '" r="5" fill="none" stroke="' + muted + '" stroke-width="1.5"/>'; });
    series.forEach((p) => { g += '<circle cx="' + X(p.day) + '" cy="' + Y(p.area_m2) + '" r="4" fill="#dc2626"/>'; });
    g += '<line x1="' + X(lastDay) + '" x2="' + X(lastDay) + '" y1="' + t + '" y2="' + (Hd - b) + '" stroke="#0284c7" stroke-dasharray="2 3"/>';
    g += "</svg>";
    g += '<div class="chart-key"><span><i class="dotk" style="background:#dc2626"></i>detected</span><span><i class="dotk ring"></i>generator truth</span>' +
      '<span><i class="linek" style="border-color:#65A30D"></i>√area OLS fit</span><span><i class="linek dash" style="border-color:#dc2626"></i>projection</span></div>';
    $("changeChart").innerHTML = g;
    const d = ch.diff, tr = sp.trend;
    const rows = [
      ["Front speed (est.)", sp.front_speed_m_day === null ? "—" : fmt(sp.front_speed_m_day, 2) + " m/day"],
      ["Generator truth", fmt(truth.front_speed_m_day, 2) + " m/day"],
      ["Area growth now", tr ? "+" + fmt(tr.growth_m2_day, 1) + " m²/day" : "—"],
      ["√area fit R²", tr ? fmt(tr.r2, 3) : "—"],
      ["Reaches " + (proj ? proj.target_pct : 10) + "% of crop", proj ? (proj.already_reached ? "already" : "in ~" + fmt(proj.days_from_last, 0) + " days") : "—"],
      ["Decline hotspots", d ? d.hotspots.length + " (" + fmtInt(d.declining_cells) + " cells)" : "flight 1"],
      ["Field median ΔNDVI", d ? (d.field_shift >= 0 ? "+" : "") + fmt(d.field_shift, 3) : "—"],
      ["Intervals measured", sp.intervals.length],
    ];
    $("changeStats").innerHTML = rows.map((r) => "<div><span>" + esc(r[0]) + "</span><b>" + esc(String(r[1])) + "</b></div>").join("");
  }

  // ---------------- prescription
  function renderRx() {
    const rx = S.scene.prescriptions[S.product];
    document.querySelectorAll("#productSeg button").forEach((b) => b.classList.toggle("active", b.dataset.product === S.product));
    const u = rx.uniform, v = rx.vra, unit = rx.unit;
    const bar = (label, val, max, color, txt) => '<div class="cmp-row"><span>' + label + '</span><div class="cmp-bar"><i style="width:' + (max ? 100 * val / max : 0).toFixed(1) + "%;background:" + color + '"></i></div><b class="num">' + txt + "</b></div>";
    $("rxCompare").innerHTML =
      bar("Whole field", u.amount, u.amount, "#a8a29e", fmt(u.amount, unit === "L" ? 2 : 1) + " " + unit) +
      bar("AgriSky VRA", v.amount, u.amount, S.product === "urea" ? "#f59e0b" : "#7c3aed", fmt(v.amount, unit === "L" ? 3 : 1) + " " + unit) +
      bar("Cost saved", rx.savings.rs, u.cost_rs, "#65A30D", "₹" + fmtInt(rx.savings.rs)) +
      '<div class="small"><b style="color:var(--lime-strong);font-size:1.05rem">' + fmt(rx.savings.pct, 1) + "% less " + esc(S.product) + "</b> · treated " + fmtInt(rx.target_area_m2) + " of " + fmtInt(rx.crop_area_m2) + " m² (" + fmt(rx.savings.area_pct_treated, 1) + "%)</div>";
    $("rxRows").innerHTML = rx.rows.length ? rx.rows.map((r) => {
      const ci = r.label === "buffer" ? { en: "Safety ring", color: "#c4b5fd" } : classInfo(r.label);
      return '<tr><td>' + (r.zone === "ring" ? "ring" : "Z" + r.zone) + '</td><td title="' + esc(r.why) + '"><span class="swatch" style="background:' + ci.color + '"></span>' + esc(r.why) + '</td><td class="num">' + fmtInt(r.area_m2) + '</td><td class="num">' + fmt(r.dose, 1) + " " + r.unit + '</td><td class="num">' + fmt(r.amount, unit === "L" ? 3 : 2) + " " + unit + "</td></tr>";
    }).join("") : '<tr><td colspan="5" class="muted">No zone needs ' + esc(S.product) + " on this flight.</td></tr>";
    const a = rx.assumptions;
    $("rxNote").textContent = S.product === "pesticide"
      ? "Label rate " + a.pesticide_l_ha + " L/ha product (illustrative) in " + a.spray_volume_l_ha + " L/ha drone tank mix, ₹" + a.pesticide_rs_l + "/L (illustrative). Never under-dosed: VRA = only where needed. " + rx.notes.excluded_near_water_cells + " cells skipped within " + a.water_no_spray_m + " m of water."
      : "Base corrective dose " + a.urea_base_kg_ha + " kg/ha urea (illustrative), scaled 0.6–1.5× by the NDRE deficit; ₹" + a.urea_rs_kg + "/kg (₹266.50 per 45-kg bag, approx.). Waterlogged zones are held until drained.";
  }

  // ---------------- mission
  function renderMission() {
    document.querySelectorAll("#planSeg button").forEach((b) => b.classList.toggle("active", b.dataset.plan === S.plan));
    const m = currentMission();
    if (!m) { $("missionStats").innerHTML = ""; $("sortieRows").innerHTML = ""; return; }
    const t = m.totals, other = S.missions[S.plan === "vra" ? "uniform" : "vra"].totals, u = m.payload_unit;
    const blk = m.blocks.map((b) => {
      const o = b.options, names = { h: "E–W", v: "N–S" };
      const alt = Object.keys(o).filter((k) => k !== b.orientation)[0];
      return names[b.orientation] + " lanes" + (alt ? " (" + o[b.orientation].turns + " turns vs " + o[alt].turns + " " + names[alt] + ")" : "");
    });
    const rows = [
      ["Sorties", t.sorties], ["Flight distance", fmt(t.distance_m / 1000, 2) + " km"],
      ["Flight time", fmt(t.flight_time_s / 60, 1) + " min"], ["Mission time (incl. refills)", fmt(t.mission_time_s / 60, 1) + " min"],
      ["Payload used", fmt(t.payload, 2) + " " + u], ["Turns", t.turns],
      ["Path efficiency (spray / all)", fmt(t.path_efficiency * 100, 0) + "%"], ["In-field efficiency", fmt(t.infield_efficiency * 100, 0) + "%"],
      ["Target cells covered once", fmtInt(t.covered_once) + " / " + fmtInt(t.target_cells)], ["Missed · double-sprayed", t.missed + " · " + t.covered_multi],
      ["Overspray (edge of swath)", fmtInt(t.overspray_cells) + " m² (" + fmt(t.overspray_pct, 1) + "%)"], ["Planner time", fmt(m.plan_ms, 0) + " ms"],
    ];
    $("missionStats").innerHTML = rows.map((r) => "<div><span>" + esc(r[0]) + "</span><b>" + esc(String(r[1])) + "</b></div>").join("");
    $("sortieRows").innerHTML = m.sorties.map((s) => '<tr><td>#' + s.id + '</td><td class="num">' + fmt(s.distance_m / 1000, 2) + '</td><td class="num">' + fmt(s.time_s / 60, 1) + '</td><td class="num">' + fmt(s.payload, 2) + " " + u + " (" + fmt(s.tank_pct, 0) + '%)</td><td class="num">' + fmt(s.battery_pct, 0) + '%</td><td class="num">' + s.turns + "</td></tr>").join("") ||
      '<tr><td colspan="6" class="muted">No target cells for this payload.</td></tr>';
    const cmp = S.plan === "vra"
      ? "Whole-field spraying would need " + other.sorties + " sortie(s), " + fmt(other.distance_m / 1000, 2) + " km and " + fmt(other.payload, 1) + " " + u + "."
      : "The prescription mission needs only " + other.sorties + " sortie(s), " + fmt(other.distance_m / 1000, 2) + " km and " + fmt(other.payload, 2) + " " + u + ".";
    $("missionNote").textContent = blk.join("; ") + ". " + cmp + " Boustrophedon passes one swath wide; RTH when tank or battery (" + Math.round(m.params.reserve * 100) + "% reserve) would run short.";
  }

  // ---------------- k-means
  function renderKmeans() {
    const km = S.scene.kmeans, hist = km.history;
    const Wd = fitW("kmChart", 380), Hd = 136, l = 46, r = 12, t = 12, b = 26;
    const maxI = Math.max(...hist), minI = Math.min(...hist);
    const X = (i) => l + (Wd - l - r) * i / Math.max(1, hist.length - 1), Y = (v) => t + (Hd - t - b) * (1 - (v - minI) / ((maxI - minI) || 1));
    const muted = cssVar("--muted"), grid = cssVar("--grid");
    let g = '<svg viewBox="0 0 ' + Wd + " " + Hd + '" role="img" aria-label="k-means inertia per iteration">';
    [minI, (minI + maxI) / 2, maxI].forEach((v) => { g += '<line x1="' + l + '" x2="' + (Wd - r) + '" y1="' + Y(v) + '" y2="' + Y(v) + '" stroke="' + grid + '"/><text x="' + (l - 5) + '" y="' + (Y(v) + 4) + '" font-size="12" text-anchor="end" fill="' + muted + '">' + Math.round(v) + "</text>"; });
    g += '<polyline fill="none" stroke="#0284c7" stroke-width="2" points="' + hist.map((v, i) => X(i) + "," + Y(v)).join(" ") + '"/>';
    g += '<text x="' + (Wd - r) + '" y="' + (t + 12) + '" font-size="12" text-anchor="end" fill="' + muted + '">inertia (within-cluster SS, sample of ' + fmtInt(km.sample_size) + ")</text>" +
      '<text x="' + l + '" y="' + (Hd - 6) + '" font-size="12" fill="' + muted + '">iteration 1</text><text x="' + (Wd - r) + '" y="' + (Hd - 6) + '" font-size="12" text-anchor="end" fill="' + muted + '">iteration ' + km.iterations + " · " + (km.converged ? "converged" : "max iter") + "</text></svg>";
    $("kmChart").innerHTML = g;
    $("kmTable").innerHTML = '<table><thead><tr><th>Cluster</th><th class="num">cells</th><th class="num">NDVI</th><th class="num">NDRE</th><th class="num">NDWI</th><th class="num">SAVI</th></tr></thead><tbody>' +
      km.centroids.map((c, j) => '<tr><td><span class="swatch" style="background:' + CLUSTER_COLORS[j % CLUSTER_COLORS.length] + '"></span>C' + j + '</td><td class="num">' + fmtInt(c.cells) + '</td><td class="num">' + fmt(c.ndvi, 3) + '</td><td class="num">' + fmt(c.ndre, 3) + '</td><td class="num">' + fmt(c.ndwi, 3) + '</td><td class="num">' + fmt(c.savi, 3) + "</td></tr>").join("") +
      '<tr><td><span class="swatch" style="background:#a16207"></span>soil mask</td><td class="num">' + fmtInt(km.masked_soil) + '</td><td colspan="4" class="muted">NDVI &lt; 0.35</td></tr><tr><td><span class="swatch" style="background:#1d4ed8"></span>water mask</td><td class="num">' + fmtInt(km.masked_water) + '</td><td colspan="4" class="muted">NDWI &gt; 0</td></tr></tbody></table>';
  }

  // ---------------- accuracy
  function renderAccuracy() {
    const a = S.scene.accuracy, ab = { healthy: "Hlth", nitrogen: "N", waterlogging: "Wlog", pest: "Pest", soil: "Soil", water: "Watr" };
    let max = 1; a.matrix.forEach((r) => r.forEach((v) => { if (v > max) max = v; }));
    let h = '<table class="cm"><thead><tr><th>truth ↓ / pred →</th>' + a.classes.map((c) => "<th>" + ab[c] + "</th>").join("") + '<th>recall</th></tr></thead><tbody>';
    a.matrix.forEach((row, i) => {
      h += "<tr><th>" + ab[a.classes[i]] + "</th>" + row.map((v, j) => {
        const alpha = v ? 0.12 + 0.6 * Math.sqrt(v / max) : 0;
        const col = i === j ? "101,163,13" : "220,38,38";
        return '<td style="background:rgba(' + col + "," + alpha.toFixed(2) + ')">' + v + "</td>";
      }).join("") + "<td>" + fmt(a.per_class[a.classes[i]].recall * 100, 0) + "%</td></tr>";
    });
    h += "</tbody></table>";
    $("cmBox").innerHTML = h;
    $("accNote").textContent = fmt(a.accuracy * 100, 1) + "% · macro-F1 " + fmt(a.macro_f1, 3);
    if (S.metrics && S.metrics.holdout) {
      const ho = S.metrics.holdout;
      $("holdoutNote").textContent = "on " + ho.seeds.length + " unseen fields × 5 flights the mean cell accuracy is " + fmt(ho.accuracy_mean * 100, 1) + "% (min " + fmt(ho.accuracy_min * 100, 1) + "%), macro-F1 " + fmt(ho.macro_f1_mean, 3);
    }
  }

  // ---------------- report
  function renderReport() {
    $("reportLines").innerHTML = S.scene.report.lines.map((l) => '<li class="' + l.level + '">' + esc(l.en) + '<span class="ta">' + esc(l.ta) + "</span></li>").join("");
  }

  function renderAssumptions() {
    const a = S.meta.assumptions;
    const rows = [
      ["Urea price", "₹" + a.urea_rs_per_kg + "/kg (₹266.50 per 45-kg bag, approx.)"],
      ["Urea corrective dose", a.urea_base_kg_ha + " kg/ha (illustrative)"],
      ["Pesticide label rate", a.pesticide_l_ha + " L/ha, ₹" + a.pesticide_rs_per_l + "/L (illustrative)"],
      ["Drone tank mix", a.spray_volume_l_ha + " L/ha (approx.)"],
      ["Pest safety ring · water buffer", a.pest_buffer_m + " m · " + a.water_no_spray_m + " m"],
      ["Drone", S.meta.defaults.tank + " L tank, " + S.meta.defaults.swath + " m swath, " + S.meta.defaults.endurance + " s battery (approx.)"],
    ];
    $("assumptions").innerHTML = rows.map((r) => "<div><span>" + esc(r[0]) + "</span><b>" + esc(r[1]) + "</b></div>").join("");
  }

  // ---------------- calculator
  async function calc() {
    const v = (id) => clamp(parseFloat($(id).value) || 0, 0, 1);
    try {
      const r = await api("/api/indices", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ green: v("cG"), red: v("cR"), rededge: v("cE"), nir: v("cN") }) });
      $("calcOut").innerHTML = ["ndvi", "gndvi", "ndre", "savi", "ndwi"].map((k) => "<div><b>" + fmt(r.indices[k], 3) + "</b><span>" + k.toUpperCase() + "</span></div>").join("");
    } catch (e) { $("calcOut").textContent = e.message; }
  }

  // ------------------------------------------------------------------ events
  function cellAt(ev) {
    const cv = $("mapCanvas"), rect = cv.getBoundingClientRect();
    const px = (ev.clientX - rect.left) * CW / rect.width, py = (ev.clientY - rect.top) * CH / rect.height;
    const x = Math.floor(px / SCALE - PAD_L), y = Math.floor(py / SCALE - PAD_T);
    if (x < 0 || y < 0 || x >= W || y >= H) return null;
    return { x, y, i: y * W + x, px: ev.clientX - rect.left, py: ev.clientY - rect.top, rw: rect.width };
  }

  function bindEvents() {
    $("layerTabs").addEventListener("click", (e) => {
      const b = e.target.closest("[data-layer]"); if (!b) return;
      S.layer = b.dataset.layer;
      document.querySelectorAll("#layerTabs .tab").forEach((t) => t.classList.toggle("active", t.dataset.layer === S.layer));
      renderMap();
    });
    $("flightChips").addEventListener("click", (e) => {
      const b = e.target.closest("[data-flight]"); if (!b) return;
      stopPlay(); S.flight = parseInt(b.dataset.flight, 10); loadScene();
    });
    $("zoneRows").addEventListener("click", (e) => {
      const tr = e.target.closest("[data-zone]"); if (!tr) return;
      S.selectedZone = parseInt(tr.dataset.zone, 10);
      document.querySelectorAll("#zoneRows tr").forEach((r) => r.classList.toggle("sel", r === tr));
      renderWhy(); renderMap();
    });
    $("productSeg").addEventListener("click", (e) => {
      const b = e.target.closest("[data-product]"); if (!b) return;
      S.product = b.dataset.product; renderRx();
      if (S.layer === "rx") renderMap();
    });
    $("planSeg").addEventListener("click", (e) => {
      const b = e.target.closest("[data-plan]"); if (!b) return;
      stopAnim(); $("hud").style.display = "none";
      S.plan = b.dataset.plan; renderMission(); drawPathStatic();
    });
    let deb = null;
    ["mSwath", "mTank", "mEndurance", "mSpeed", "mOrient", "mProduct"].forEach((id) => $(id).addEventListener("change", () => {
      clearTimeout(deb);
      S.mProduct = $("mProduct").value;
      deb = setTimeout(() => { stopAnim(); $("hud").style.display = "none"; loadMissions(false); }, 150);
    }));
    $("animBtn").addEventListener("click", animateMission);
    $("tglOutline").addEventListener("change", renderMap);
    $("tglPath").addEventListener("change", () => { stopAnim(); $("hud").style.display = "none"; drawPathStatic(); });
    $("kSelect").addEventListener("change", () => { S.k = parseInt($("kSelect").value, 10); loadScene(); });
    $("seedInput").addEventListener("change", () => {
      const v = clamp(parseInt($("seedInput").value, 10) || 0, 0, 1000000); $("seedInput").value = v; S.seed = v; S.selectedZone = null; loadScene();
    });
    $("demoBtn").addEventListener("click", runDemo);
    let rsT = 0;
    window.addEventListener("resize", () => { clearTimeout(rsT); rsT = setTimeout(() => { if (S.scene && !S.anim) { renderMap(); renderChange(); renderKmeans(); } }, 250); });
    $("playBtn").addEventListener("click", () => (S.playing ? stopPlay() : playWeeks()));
    ["cG", "cR", "cE", "cN"].forEach((id) => $(id).addEventListener("input", calc));
    const tip = $("tooltip");
    $("mapCanvas").addEventListener("mousemove", (ev) => {
      if (!S.scene) return;
      const c = cellAt(ev); if (!c) { tip.style.display = "none"; return; }
      const L = S.scene.layers, z = S.scene.zones[L.zone[c.i]];
      const rxv = L.rx_pesticide[c.i] / 1000, ur = L.rx_urea[c.i];
      tip.innerHTML = "x " + c.x + " m, y " + c.y + " m · Zone Z" + z.id + "<br>NDVI " + fmt(L.ndvi[c.i] / 1000, 3) + " · NDRE " + fmt(L.ndre[c.i] / 1000, 3) + " · NDWI " + fmt(L.ndwi[c.i] / 1000, 3) +
        (L.dndvi ? " · ΔNDVI " + fmt(L.dndvi[c.i] / 1000, 3) : "") + "<br>AgriSky: <b>" + esc(classInfo(z.label).en) + "</b> · truth: " + esc(classInfo(CLASSES[L.truth[c.i]]).en) +
        (rxv || ur ? "<br>Rx: " + (rxv ? "pesticide " + rxv + " L/ha " : "") + (ur ? "urea " + ur + " kg/ha" : "") : "");
      tip.style.display = "block";
      const left = c.px + 14 + 260 > c.rw ? c.px - 270 : c.px + 14;
      tip.style.left = Math.max(4, left) + "px"; tip.style.top = (c.py + 12) + "px";
    });
    $("mapCanvas").addEventListener("mouseleave", () => { tip.style.display = "none"; });
    $("mapCanvas").addEventListener("click", (ev) => {
      if (!S.scene) return;
      const c = cellAt(ev); if (!c) return;
      const L = S.scene.layers;
      $("cG").value = (L.green[c.i] / 1000).toFixed(3); $("cR").value = (L.red[c.i] / 1000).toFixed(3);
      $("cE").value = (L.rededge[c.i] / 1000).toFixed(3); $("cN").value = (L.nir[c.i] / 1000).toFixed(3);
      $("calcNote").textContent = "Cell (" + c.x + ", " + c.y + ") of flight " + S.flight + ": server NDVI " + fmt(L.ndvi[c.i] / 1000, 3) + " — recompute it by hand: (NIR − Red)/(NIR + Red) = (" + $("cN").value + " − " + $("cR").value + ")/(" + $("cN").value + " + " + $("cR").value + ").";
      calc();
      S.selectedZone = L.zone[c.i]; renderZones(); renderMap();
    });
  }

  async function runDemo() {
    stopPlay(); stopAnim();
    S.seed = 42; $("seedInput").value = 42; S.k = 5; $("kSelect").value = "5"; S.flight = 5; S.layer = "stress"; S.plan = "vra"; S.product = "pesticide";
    S.mProduct = "pesticide"; $("mProduct").value = "pesticide";
    $("mSwath").value = 4; $("mTank").value = 10; $("mEndurance").value = 540; $("mSpeed").value = 4; $("mOrient").value = "auto";
    S.selectedZone = null;
    buildTabs();
    await loadScene();
    animateMission();
  }

  async function playWeeks() {
    stopAnim(); $("hud").style.display = "none";
    S.playing = true; $("playBtn").classList.add("primary");
    for (let f = 1; f <= 5 && S.playing; f++) {
      S.flight = f; await loadScene();
      await new Promise((r) => setTimeout(r, 1300));
    }
    stopPlay();
  }
  function stopPlay() { S.playing = null; $("playBtn").classList.remove("primary"); }

  init().then(calc);
})();
