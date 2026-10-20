/* Printable farmer report - renders /api/scene into a one-page sheet. */
(function () {
  "use strict";
  const W = 120, H = 80, CLASSES = ["healthy", "nitrogen", "waterlogging", "pest", "soil", "water"];
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (v, d) => (v === null || v === undefined ? "—" : Number(v).toFixed(d === undefined ? 1 : d));
  function hexRgb(h) { const n = parseInt(h.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }

  function draw(canvas, colorFn, zones) {
    const ctx = canvas.getContext("2d");
    const off = document.createElement("canvas"); off.width = W; off.height = H;
    const o = off.getContext("2d"), img = o.createImageData(W, H);
    for (let i = 0; i < W * H; i++) { const c = colorFn(i); img.data[i * 4] = c[0]; img.data[i * 4 + 1] = c[1]; img.data[i * 4 + 2] = c[2]; img.data[i * 4 + 3] = 255; }
    o.putImageData(img, 0, 0);
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(off, 0, 0, canvas.width, canvas.height);
    const sx = canvas.width / W, sy = canvas.height / H;
    ctx.beginPath();
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      const i = y * W + x;
      if (x < W - 1 && zones[i] !== zones[i + 1]) { ctx.moveTo((x + 1) * sx, y * sy); ctx.lineTo((x + 1) * sx, (y + 1) * sy); }
      if (y < H - 1 && zones[i] !== zones[i + W]) { ctx.moveTo(x * sx, (y + 1) * sy); ctx.lineTo((x + 1) * sx, (y + 1) * sy); }
    }
    ctx.strokeStyle = "rgba(255,255,255,.8)"; ctx.lineWidth = 1; ctx.stroke();
  }

  async function main() {
    const q = new URLSearchParams(location.search);
    const params = new URLSearchParams({ seed: q.get("seed") || 42, flight: q.get("flight") || 5, k: q.get("k") || 5 });
    let meta, sc;
    try {
      [meta, sc] = await Promise.all([fetch("/api/meta").then((r) => r.json()), fetch("/api/scene?" + params).then((r) => r.json())]);
    } catch (e) { $("meta").textContent = "Could not load report: " + e.message; return; }
    if (sc.error) { $("meta").textContent = sc.error; return; }
    const info = {}; meta.classes.forEach((c) => { info[c.id] = c; });
    const rep = sc.report, s = rep.summary;
    $("title").firstChild.nodeValue = rep.title + " ";
    $("titleTa").textContent = rep.title_ta;
    $("meta").innerHTML = "<span>Field seed " + sc.seed + "</span><span>Crop: maize, " + sc.das + " days after sowing</span><span>Field " + fmt(s.field_ha, 2) + " ha · crop " + fmt(s.crop_ha, 2) + " ha</span><span>Printed " + new Date().toLocaleDateString("en-IN") + "</span>";
    const a = s.alert;
    if (a) { $("alert").className = "alert-box " + a.level; $("alert").innerHTML = "<b>" + esc(a.title) + "</b><br>" + esc(a.en) + "<br>" + esc(a.ta); }
    const L = sc.layers, cols = CLASSES.map((c) => hexRgb(info[c].color));
    draw($("mapStress"), (i) => cols[L.cls[i]], L.zone);
    const pur = hexRgb("#7c3aed"), amb = hexRgb("#f59e0b");
    draw($("mapRx"), (i) => {
      if (L.cls[i] === 5) return [30, 64, 140];
      if (L.rx_pesticide[i]) return pur;
      if (L.rx_urea[i]) return amb;
      const g = Math.round(60 + 120 * Math.max(0, Math.min(0.9, L.ndvi[i] / 1000)));
      return [Math.round(g * 0.75), Math.round(g * 0.85), Math.round(g * 0.7)];
    }, L.zone);
    $("legend").innerHTML = CLASSES.map((c) => '<span class="sw"><i style="background:' + info[c].color + '"></i>' + esc(info[c].en) + " / " + esc(info[c].ta) + "</span>").join("");
    $("lines").innerHTML = rep.lines.map((l) => '<li class="' + l.level + '">' + esc(l.en) + '<span class="ta">' + esc(l.ta) + "</span></li>").join("");
    const rp = sc.prescriptions.pesticide, ru = sc.prescriptions.urea, mv = sc.mission.vra.totals, mu = sc.mission.uniform.totals;
    const tiles = [
      [fmt(rp.vra.amount, 3) + " L", "pesticide (vs " + fmt(rp.uniform.amount, 2) + " L blanket)"],
      [fmt(ru.vra.amount, 1) + " kg", "urea (vs " + fmt(ru.uniform.amount, 1) + " kg blanket)"],
      ["₹" + Math.round(s.rs_saved), "chemical cost saved"],
      [mv.sorties + " sortie" + (mv.sorties > 1 ? "s" : ""), fmt(mv.flight_time_s / 60, 1) + " min flight (blanket: " + mu.sorties + ", " + fmt(mu.flight_time_s / 60, 1) + " min)"],
    ];
    $("totals").innerHTML = tiles.map((t) => "<div><b>" + esc(t[0]) + "</b><span>" + esc(t[1]) + "</span></div>").join("");
    const order = { pest: 0, nitrogen: 1, waterlogging: 2, healthy: 3, soil: 4, water: 5 };
    $("zones").innerHTML = sc.zones.slice().sort((x, y) => order[x.label] - order[y.label] || y.cells - x.cells).map((z) =>
      "<tr><td>Z" + z.id + '</td><td><span class="swatch" style="background:' + info[z.label].color + '"></span>' + esc(info[z.label].en) + '</td><td class="num">' + Math.round(z.area_m2).toLocaleString("en-IN") + '</td><td class="num">' + fmt(z.ndvi, 2) + "</td><td>" + esc(z.why) + "</td></tr>").join("");
  }
  $("printBtn").addEventListener("click", () => window.print());
  main();
})();
