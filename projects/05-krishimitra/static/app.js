/* KrishiMitra front-end: vanilla JS, no libraries, no network calls except our own /api. */
(function () {
  "use strict";

  var I18N = window.KM_I18N;
  var SVGNS = "http://www.w3.org/2000/svg";
  var SLIDER = { N: [0, 200, 1], P: [0, 150, 1], K: [0, 300, 1], ph: [4, 9, 0.1],
                 temperature: [10, 42, 0.5], humidity: [20, 100, 1], rainfall: [100, 2600, 10] };
  var state = { lang: "en", meta: null, result: null, preset: 0, rainFactor: 1, speaking: false };

  try { var saved = window.localStorage.getItem("km-lang"); if (saved === "ta" || saved === "en") state.lang = saved; } catch (e) { /* storage blocked */ }

  // ---------------------------------------------------------------- helpers
  function $(id) { return document.getElementById(id); }
  function tr(key, params) {
    var s = (I18N[state.lang] && I18N[state.lang][key]);
    if (s === undefined) s = I18N.en[key];
    if (s === undefined) return key;
    if (params) Object.keys(params).forEach(function (k) { s = s.split("{" + k + "}").join(params[k]); });
    return s;
  }
  function L(obj) { return obj ? (obj[state.lang] || obj.en || "") : ""; }
  function h(tag, attrs, kids) {
    var e = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      if (k === "text") e.textContent = attrs[k];
      else if (k === "cls") e.className = attrs[k];
      else if (k === "style") e.setAttribute("style", attrs[k]);
      else if (k.slice(0, 2) === "on") e.addEventListener(k.slice(2), attrs[k]);
      else e.setAttribute(k, attrs[k]);
    });
    (kids || []).forEach(function (c) { if (c != null) e.appendChild(typeof c === "string" ? document.createTextNode(c) : c); });
    return e;
  }
  function s(tag, attrs, text) {
    var e = document.createElementNS(SVGNS, tag);
    Object.keys(attrs || {}).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    if (text != null) e.textContent = text;
    return e;
  }
  function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); return el; }
  function fmt(n, d) {
    if (n === null || n === undefined || isNaN(n)) return "–";
    return Number(n).toLocaleString("en-IN", { maximumFractionDigits: d === undefined ? 0 : d, minimumFractionDigits: 0 });
  }
  function isoToday() {
    var d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
    return d.toISOString().slice(0, 10);
  }
  function addDays(iso, n) {
    var d = new Date(iso + "T00:00:00Z"); d.setUTCDate(d.getUTCDate() + n);
    return d.toISOString().slice(0, 10);
  }
  function dayDiff(a, b) { return Math.round((new Date(b + "T00:00:00Z") - new Date(a + "T00:00:00Z")) / 864e5); }
  function fmtDate(iso, withYear) {
    var d = new Date(iso + "T00:00:00Z"), m = tr("months")[d.getUTCMonth()];
    var out = state.lang === "ta" ? m + " " + d.getUTCDate() : d.getUTCDate() + " " + m;
    return withYear ? out + " " + d.getUTCFullYear() : out;
  }
  function weekday(iso) { return tr("days")[new Date(iso + "T00:00:00Z").getUTCDay()]; }
  function niceStep(raw) {
    var p = Math.pow(10, Math.floor(Math.log(Math.max(raw, 1e-6)) / Math.LN10)), f = raw / p;
    return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * p;
  }
  function cropName(c) { var m = state.meta && state.meta.crops.filter(function (x) { return x.crop === c; })[0]; return m ? L(m.name) : c; }
  var toastTimer = null;
  function toast(msg) {
    var t = $("toast"); t.textContent = msg; t.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(function () { t.hidden = true; }, 3200);
  }

  function api(path, body) {
    var opt = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
    return fetch(path, opt).then(function (r) {
      return r.json().then(function (j) {
        if (!r.ok) throw new Error(j && j.error ? j.error : ("HTTP " + r.status));
        return j;
      });
    });
  }

  // ---------------------------------------------------------------- static UI
  function applyStatic() {
    document.documentElement.lang = state.lang === "ta" ? "ta" : "en";
    Array.prototype.forEach.call(document.querySelectorAll("[data-i18n]"), function (e) { e.textContent = tr(e.getAttribute("data-i18n")); });
    $("langEn").classList.toggle("active", state.lang === "en");
    $("langTa").classList.toggle("active", state.lang === "ta");
    $("langEn").setAttribute("aria-pressed", state.lang === "en");
    $("langTa").setAttribute("aria-pressed", state.lang === "ta");
    if (!state.meta) return;
    state.meta.features.forEach(function (f) { var l = $("lbl-" + f); if (l) l.textContent = featLabel(f); });
    fillSelect($("soil"), Object.keys(state.meta.soils).map(function (k) { return [k, L(state.meta.soils[k])]; }));
    fillSelect($("method"), Object.keys(state.meta.methods).map(function (k) { return [k, L(state.meta.methods[k])]; }));
    fillSelect($("cropChoice"), [["", tr("auto")]].concat(state.meta.crops.map(function (c) { return [c.crop, L(c.name)]; })));
    renderChips();
    $("disclaimer").textContent = L(state.meta.disclaimer);
  }
  function featLabel(f) {
    var u = state.meta.units[f];
    if (state.lang === "ta") u = ({ mm: "மி.மீ", "kg/ha": "கிலோ/எக்டேர்" })[u] || u;
    return tr("f_" + f) + (u ? " · " + u : "");
  }
  function fillSelect(sel, opts) {
    var v = sel.value; clear(sel);
    opts.forEach(function (o) { sel.appendChild(h("option", { value: o[0], text: o[1] })); });
    if (v !== undefined) sel.value = v;
    if (sel.selectedIndex < 0) sel.selectedIndex = 0;
  }
  function buildFeatureInputs() {
    var box = clear($("featureInputs"));
    state.meta.features.forEach(function (f) {
      var lim = state.meta.limits[f], sl = SLIDER[f];
      var num = h("input", { type: "number", id: "f-" + f, min: lim[0], max: lim[1], step: sl[2], inputmode: "decimal", "aria-label": f });
      var rng = h("input", { type: "range", id: "r-" + f, min: sl[0], max: sl[1], step: sl[2], "aria-label": f, tabindex: "-1" });
      num.addEventListener("input", function () { rng.value = num.value; });
      rng.addEventListener("input", function () { num.value = rng.value; });
      rng.addEventListener("change", function () { submit(); });
      box.appendChild(h("div", { cls: "feat" }, [
        h("div", { cls: "feat-top" }, [h("label", { "for": "f-" + f, id: "lbl-" + f, text: featLabel(f) }), num]),
        rng
      ]));
    });
  }
  function setFeature(f, v) { $("f-" + f).value = v; $("r-" + f).value = v; }

  function renderChips() {
    var box = clear($("presetChips"));
    state.meta.presets.forEach(function (p, i) {
      box.appendChild(h("button", { type: "button", cls: "chip" + (i === state.preset ? " active" : ""), id: "preset-" + p.id,
        text: L(p.name), onclick: function () { loadPreset(i, true); } }));
    });
  }

  function loadPreset(i, announce) {
    var p = state.meta.presets[i];
    state.preset = i; state.rainFactor = p.rain_factor || 1;
    Object.keys(p.inputs).forEach(function (f) { setFeature(f, p.inputs[f]); });
    $("soil").value = p.soil; $("method").value = p.method;
    $("area").value = p.area_acres; $("lat").value = p.lat;
    $("sowing").value = addDays(isoToday(), -p.sowing_days_ago);
    $("cropChoice").value = "";
    renderChips();
    if (announce) toast(tr("loaded", { name: L(p.name) }));
    return submit();
  }

  function payload() {
    var body = {};
    state.meta.features.forEach(function (f) { body[f] = parseFloat($("f-" + f).value); });
    body.soil = $("soil").value; body.method = $("method").value;
    body.area_acres = parseFloat($("area").value); body.lat = parseFloat($("lat").value);
    body.sowing_date = $("sowing").value || addDays(isoToday(), -20);
    body.start_date = isoToday();
    body.rain_factor = state.rainFactor;
    if ($("cropChoice").value) body.crop = $("cropChoice").value;
    return body;
  }

  function submit() {
    var err = $("formError"); err.hidden = true;
    document.body.classList.add("loading");
    return api("/api/advise", payload()).then(function (res) {
      state.result = res; render();
    }).catch(function (e) {
      err.textContent = e.message || tr("netErr"); err.hidden = false; toast(tr("netErr"));
    }).then(function () { document.body.classList.remove("loading"); });
  }

  // ---------------------------------------------------------------- render
  function render() {
    var r = state.result; if (!r) return;
    renderSummary(r); renderRec(r); renderWhy(r); renderFert(r); renderIrr(r); renderMarket(r); renderCalendar(r);
    var m = state.meta.metrics;
    $("footMetrics").textContent = tr("trainInfo", { n: m.n_train, t: m.rf_trees, ms: fmt(r.elapsed_ms, 1) });
  }

  function renderSummary(r) {
    var top = r.recommendation.top3[0], f = r.fertiliser, irr = r.irrigation, d = r.market.decision;
    $("sCrop").textContent = cropName(top.crop);
    $("sCropSub").textContent = Math.round(top.prob * 100) + "% · " + (r.recommendation.agreement ? tr("agree") : tr("disagree"));
    var p = {}; f.products.forEach(function (x) { p[x.product] = x.kg_per_acre; });
    var sf = clear($("sFert"));
    sf.appendChild(document.createTextNode(fmt(p.urea) + " / " + fmt(p.dap) + " / " + fmt(p.mop) + " "));
    sf.appendChild(h("small", { text: state.lang === "ta" ? "கிலோ" : "kg" }));
    $("sFertSub").textContent = tr("fertSub") + " · " + cropName(r.crop);
    $("sWater").textContent = irr.week.litres_per_acre > 0 ? fmt(irr.week.litres_per_acre) + " L" : tr("noIrr");
    $("sWaterSub").textContent = tr("litresAcre") + " · " + fmt(irr.week.gross_irrigation_mm, 1) + " mm · " + L(state.meta.methods[irr.method]);
    $("sMkt").textContent = d.action === "hold" ? tr("holdN", { n: d.weeks }) : tr("sellNow");
    $("sMktSub").textContent = tr("band") + " " + fmt(d.band[0]) + "–" + fmt(d.band[1]) + " " + unitL(r.market.unit);
  }
  function compactL(n) {
    if (n >= 1e5) return (n / 1e5).toFixed(2) + (state.lang === "ta" ? " லட்சம்" : " lakh");
    return fmt(n);
  }
  function unitL(u) {
    if (state.lang !== "ta") return u;
    return u.replace("quintal", "குவிண்டால்").replace("nuts", "காய்கள்");
  }

  function renderRec(r) {
    var box = clear($("top3")), rec = r.recommendation;
    rec.top3.forEach(function (c, i) {
      var other = state.lang === "ta" ? c.name.en : c.name.ta;
      box.appendChild(h("button", { type: "button", cls: "crop-opt" + (c.crop === r.crop ? " sel" : ""),
        onclick: function () { $("cropChoice").value = c.crop; submit(); } }, [
        h("span", { cls: "rank", text: String(i + 1) }),
        h("span", null, [h("span", { cls: "nm", text: L(c.name) + " " }), h("span", { cls: "alt", text: other }),
          h("div", { cls: "bar" }, [h("i", { style: "width:" + Math.max(2, c.prob * 100).toFixed(1) + "%" })])]),
        h("span", { cls: "pct", text: (c.prob * 100).toFixed(c.prob > 0.995 ? 0 : 1) + "%" })
      ]));
    });
    var m = state.meta.metrics, mc = clear($("modelCompare"));
    function card(name, acc, top) {
      return h("div", { cls: "mc" }, [h("b", { text: name }), h("div", { cls: "v", text: (acc * 100).toFixed(1) + "%" }),
        h("div", { cls: "s", text: tr("accuracy") }),
        top ? h("div", { cls: "s", text: cropName(top.crop) + " " + (top.prob * 100).toFixed(0) + "%" }) : null]);
    }
    mc.appendChild(card(tr("gnb"), m.gnb_accuracy, rec.gnb_top3[0]));
    mc.appendChild(card(tr("rf"), m.rf_accuracy, rec.rf_top3[0]));
    mc.appendChild(card(tr("blend"), m.blend_accuracy, rec.top3[0]));
    mc.appendChild(h("div", { cls: "agree" + (rec.agreement ? "" : " no"), text: rec.agreement ? tr("agree") : tr("disagree") }));
  }

  function renderWhy(r) {
    var ex = r.recommendation.explanation, box = clear($("whyBars"));
    $("whyVs").textContent = cropName(ex.crop) + " · " + tr("vs", { crop: cropName(ex.versus) });
    var maxAbs = 1;
    ex.features.forEach(function (f) { maxAbs = Math.max(maxAbs, Math.abs(f.gnb_log_odds)); });
    maxAbs = Math.min(maxAbs, 12);
    ex.features.forEach(function (f) {
      var v = Math.max(-maxAbs, Math.min(maxAbs, f.gnb_log_odds)), w = Math.abs(v) / maxAbs * 50;
      var range = tr("typical") + " " + f.typical_range[0] + "–" + f.typical_range[1];
      box.appendChild(h("div", { cls: "why-row", title: "log-odds " + f.gnb_log_odds + " | z " + f.z }, [
        h("div", { cls: "lbl" }, [tr("f_" + f.feature) + " = " + fmt(f.value, 1),
          h("small", { cls: f.in_range ? "" : "out", text: f.in_range ? range : tr("outOfRange") + " (" + f.typical_range[0] + "–" + f.typical_range[1] + ")" })]),
        h("div", { cls: "dbar" }, [h("i", { cls: v >= 0 ? "pos" : "neg", style: "width:" + Math.max(w, 0.8).toFixed(1) + "%" })]),
        h("div", { cls: "rfv", text: (f.rf_contribution >= 0 ? "+" : "") + (f.rf_contribution * 100).toFixed(1) + "%" })
      ]));
    });
  }

  function renderFert(r) {
    var f = r.fertiliser;
    $("fertCrop").textContent = cropName(r.crop) + " · " + fmt(f.area_acres, 2) + " ac";
    var box = clear($("fertProducts"));
    f.products.forEach(function (p) {
      box.appendChild(h("div", { cls: "prod p-" + p.product }, [
        h("div", { cls: "pn", text: tr(p.product) }),
        h("div", { cls: "pv" }, [fmt(p.kg_per_acre, 1) + " ", h("small", { text: tr("kgAcre") })]),
        h("div", { cls: "pb", text: tr("bagsFarm", { n: fmt(p.bags_total, 1), kg: fmt(p.kg_total), a: fmt(f.area_acres, 2) }) })
      ]));
    });
    var npk = clear($("npkBars"));
    npk.appendChild(h("div", { cls: "npk-key" }, [h("span", null, [h("i", { style: "background:var(--leaf);opacity:.55" }), tr("fromSoil")]),
      h("span", null, [h("i", { style: "background:var(--amber)" }), tr("deficit")]), h("span", { text: tr("need") + " = 100%" })]));
    [["N", "N"], ["P2O5", "P₂O₅"], ["K2O", "K₂O"]].forEach(function (k) {
      var need = f.requirement_kg_ha[k[0]] || 0.0001, def = f.deficit_kg_ha[k[0]], soil = Math.max(0, need - def);
      npk.appendChild(h("div", { cls: "npk-row" }, [h("b", { text: k[1] }),
        h("div", { cls: "stack", title: need + " kg/ha" }, [h("i", { cls: "soil", style: "width:" + (soil / need * 100).toFixed(1) + "%" }),
          h("i", { cls: "def", style: "width:" + (def / need * 100).toFixed(1) + "%" })]),
        h("span", { cls: "num", text: fmt(f.deficit_kg_acre[k[0]], 1) + " " + tr("perAcre") })]));
    });
    var sc = clear($("fertSchedule"));
    f.schedule.forEach(function (x) { sc.appendChild(h("li", null, [h("b", { text: L(x.when) + ": " }), L(x.what)])); });
    var org = clear($("organic"));
    f.organic.forEach(function (o) {
      org.appendChild(h("div", { cls: "org" }, [h("b", { text: L(o.name) }),
        "NPK ≈ " + o.pct_npk.join("-") + "%", h("br"), tr("replace25", { kg: fmt(o.kg_per_acre) })]));
    });
    var tips = clear($("fertTips"));
    f.tips.forEach(function (x) { tips.appendChild(h("li", { text: L(x) })); });
    $("fertFormula").textContent = f.formula + "\nN " + f.requirement_kg_ha.N + " / P2O5 " + f.requirement_kg_ha.P2O5 + " / K2O " + f.requirement_kg_ha.K2O +
      " kg/ha (approx.) − soil credit " + f.soil_credit_kg_ha.N + " / " + f.soil_credit_kg_ha.P2O5 + " / " + f.soil_credit_kg_ha.K2O;
  }

  function renderIrr(r) {
    var irr = r.irrigation, d0 = irr.days[0] || {};
    $("irrSummary").textContent = L(irr.summary);
    $("irrMeta").textContent = tr("irrMeta", { stage: tr("st_" + d0.stage), kc: d0.kc, need: irr.daily_need_mm, litres: fmt(irr.daily_need_litres_per_acre) });
    // chart
    var W = 560, H = 200, pl = 34, pr = 8, pt = 16, pb = 34, n = irr.days.length;
    var maxV = 1;
    irr.days.forEach(function (d) { maxV = Math.max(maxV, d.etc, d.peff, d.gross_mm); });
    var stepV = niceStep(maxV * 1.1 / 4); maxV = stepV * 4;
    var svg = s("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": "7-day water balance" });
    var y = function (v) { return pt + (H - pt - pb) * (1 - v / maxV); };
    for (var g = 0; g <= 4; g++) {
      var gv = maxV * g / 4;
      svg.appendChild(s("line", { x1: pl, x2: W - pr, y1: y(gv), y2: y(gv), style: "stroke:var(--grid)" }));
      svg.appendChild(s("text", { x: pl - 4, y: y(gv) + 3, "text-anchor": "end", "font-size": 10, style: "fill:var(--muted)" }, fmt(gv, 1)));
    }
    svg.appendChild(s("text", { x: 2, y: 10, "font-size": 10, style: "fill:var(--muted)" }, "mm"));
    var gw = (W - pl - pr) / n, bw = Math.min(16, gw / 4);
    irr.days.forEach(function (d, i) {
      var cx = pl + gw * i + gw / 2;
      [["etc", "var(--amber)", -1], ["peff", "var(--water)", 0], ["gross_mm", "var(--leaf)", 1]].forEach(function (b) {
        var v = d[b[0]], x = cx + b[2] * (bw + 2) - bw / 2;
        svg.appendChild(s("rect", { x: x, y: y(v), width: bw, height: Math.max(0, y(0) - y(v)), rx: 3, style: "fill:" + b[1] }));
      });
      if (d.irrigate) svg.appendChild(s("text", { x: cx + bw + 2, y: y(d.gross_mm) - 4, "text-anchor": "middle", "font-size": 10, "font-weight": 700, style: "fill:var(--leaf-strong)" }, fmt(d.gross_mm, 0)));
      svg.appendChild(s("text", { x: cx, y: H - 18, "text-anchor": "middle", "font-size": 11, "font-weight": 600, style: "fill:var(--text)" }, weekday(d.date)));
      svg.appendChild(s("text", { x: cx, y: H - 5, "text-anchor": "middle", "font-size": 10, style: "fill:var(--muted)" }, fmtDate(d.date)));
    });
    clear($("irrChart")).appendChild(svg);
    // table
    var tb = clear($("irrTable"));
    var cols = [["date", function (d) { return weekday(d.date) + " " + fmtDate(d.date); }], ["temp", function (d) { return fmt(d.tmax, 1) + " / " + fmt(d.tmin, 1); }], ["rain", "rain"],
      ["et0", "et0"], ["etc", "etc"], ["irrigate", function (d) { return d.irrigate ? null : tr("none"); }], ["litresAcre", function (d) { return d.irrigate ? compactL(d.litres_per_acre) : "–"; }]];
    tb.appendChild(h("thead", null, [h("tr", null, cols.map(function (c) { return h("th", { text: tr(c[0]) }); }))]));
    var body = h("tbody");
    irr.days.forEach(function (d) {
      body.appendChild(h("tr", null, cols.map(function (c) {
        if (c[0] === "irrigate" && d.irrigate) return h("td", null, [h("span", { cls: "yes", text: fmt(d.gross_mm, 1) + " mm" })]);
        var v = typeof c[1] === "function" ? c[1](d) : d[c[1]];
        return h("td", { text: typeof v === "number" ? fmt(v, 2) : String(v) });
      })));
    });
    tb.appendChild(body);
    $("irrFormula").textContent = irr.formula + "\nRa (" + fmtDate(d0.date) + ", " + irr.lat + "°) = " + d0.ra_mj + " MJ/m²/day → ET0 " + d0.et0 +
      " mm; efficiency " + irr.efficiency + "; refill at " + irr.refill_mm + " mm deficit";
  }

  function renderMarket(r) {
    var mk = r.market, d = mk.decision;
    var dec = clear($("mktDecision"));
    dec.className = "decision" + (d.action === "hold" ? " hold" : "");
    dec.appendChild(h("div", { cls: "act", text: d.action === "hold" ? tr("holdN", { n: d.weeks }) : tr("sellNow") }));
    dec.appendChild(h("div", { cls: "why-txt" }, [L(d.text), d.reason ? h("div", { cls: "muted", text: L(d.reason) }) : null,
      h("div", { cls: "muted", text: tr("today") + ": " + fmt(mk.current) + " " + unitL(mk.unit) + " · " + tr("trendWk", { v: fmt(mk.trend_per_week, 1) }) })]));
    // chart: last 52 weeks + 12-week forecast
    var hist = mk.history.slice(-52), fc = mk.forecast;
    var W = 560, H = 210, pl = 46, pr = 8, pt = 12, pb = 24, n = hist.length + fc.length;
    var lo = Infinity, hi = -Infinity;
    hist.forEach(function (p) { lo = Math.min(lo, p.price); hi = Math.max(hi, p.price); });
    fc.forEach(function (p) { lo = Math.min(lo, p.low); hi = Math.max(hi, p.high); });
    var pad = (hi - lo) * 0.08; lo -= pad; hi += pad;
    var x = function (i) { return pl + (W - pl - pr) * i / (n - 1); };
    var y = function (v) { return pt + (H - pt - pb) * (1 - (v - lo) / (hi - lo)); };
    var svg = s("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": "price history and forecast" });
    for (var g = 0; g <= 4; g++) {
      var gv = lo + (hi - lo) * g / 4;
      svg.appendChild(s("line", { x1: pl, x2: W - pr, y1: y(gv), y2: y(gv), style: "stroke:var(--grid)" }));
      svg.appendChild(s("text", { x: pl - 4, y: y(gv) + 3, "text-anchor": "end", "font-size": 10, style: "fill:var(--muted)" }, fmt(gv)));
    }
    var lastMonth = -1;
    hist.concat(fc).forEach(function (p, i) {
      var m = new Date(p.date + "T00:00:00Z").getUTCMonth();
      if (m !== lastMonth && i > 0 && m % 2 === 0) svg.appendChild(s("text", { x: x(i), y: H - 6, "text-anchor": "middle", "font-size": 10, style: "fill:var(--muted)" }, tr("months")[m]));
      lastMonth = m;
    });
    var k = hist.length - 1;
    var band = fc.map(function (p, i) { return x(k + 1 + i) + "," + y(p.high); }).concat(fc.slice().reverse().map(function (p, i) { return x(k + fc.length - i) + "," + y(p.low); }));
    band.unshift(x(k) + "," + y(hist[k].price)); band.push(x(k) + "," + y(hist[k].price));
    svg.appendChild(s("polygon", { points: band.join(" "), style: "fill:var(--amber);opacity:.18" }));
    svg.appendChild(s("polyline", { points: hist.map(function (p, i) { return x(i) + "," + y(p.price); }).join(" "), style: "fill:none;stroke:var(--muted);stroke-width:1.6" }));
    svg.appendChild(s("polyline", { points: hist.filter(function (p) { return p.ma12 != null; }).map(function (p) { return x(hist.indexOf(p)) + "," + y(p.ma12); }).join(" "), style: "fill:none;stroke:var(--leaf);stroke-width:2.4" }));
    svg.appendChild(s("polyline", { points: [x(k) + "," + y(hist[k].price)].concat(fc.map(function (p, i) { return x(k + 1 + i) + "," + y(p.price); })).join(" "), style: "fill:none;stroke:var(--amber);stroke-width:2.4;stroke-dasharray:5 4" }));
    svg.appendChild(s("line", { x1: x(k), x2: x(k), y1: pt, y2: H - pb, style: "stroke:var(--text);stroke-dasharray:2 3;opacity:.5" }));
    svg.appendChild(s("circle", { cx: x(k), cy: y(hist[k].price), r: 4, style: "fill:var(--text)" }));
    svg.appendChild(s("text", { x: x(k) - 4, y: pt + 9, "text-anchor": "end", "font-size": 10, "font-weight": 700, style: "fill:var(--text)" }, tr("today")));
    if (d.action === "hold") {
      var hp = fc[d.weeks - 1], hx = x(k + d.weeks);
      svg.appendChild(s("circle", { cx: hx, cy: y(hp.price), r: 5, style: "fill:var(--amber);stroke:var(--surface);stroke-width:2" }));
    }
    clear($("mktChart")).appendChild(svg);
    // seasonal index
    var si = clear($("siBars")), mx = Math.max.apply(null, mk.seasonal_index), mn = Math.min.apply(null, mk.seasonal_index);
    var now = new Date(mk.as_of + "T00:00:00Z").getUTCMonth();
    mk.seasonal_index.forEach(function (v, i) {
      var hgt = 15 + 70 * (v - mn) / ((mx - mn) || 1);
      si.appendChild(h("div", { cls: i === now ? "now" : "", title: tr("months")[i] + ": " + v.toFixed(3) }, [
        h("i", { cls: v === mx ? "hi" : "", style: "height:" + hgt.toFixed(0) + "%" }), h("span", { text: tr("months")[i].slice(0, 3) })]));
    });
  }

  function renderCalendar(r) {
    var cal = r.calendar, st = cal.stages;
    $("calMeta").textContent = tr("durationDays", { n: cal.duration_days }) + " · " + tr("harvestOn", { date: fmtDate(cal.harvest_date, true) }) +
      " · " + (cal.perennial ? tr("perennial") : tr("das", { n: cal.days_after_sowing }));
    var start = st.reduce(function (a, b) { return b.start < a ? b.start : a; }, st[0].start);
    var end = st.reduce(function (a, b) { return b.end > a ? b.end : a; }, st[0].end);
    var total = Math.max(1, dayDiff(start, end));
    var W = 1000, lw = 190, rh = 28, top = 26, H = top + st.length * rh + 8;
    var x = function (iso) { return lw + (W - lw - 10) * dayDiff(start, iso) / total; };
    var svg = s("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": "crop calendar" });
    // month ticks
    var d = new Date(start + "T00:00:00Z"); d.setUTCDate(1); d.setUTCMonth(d.getUTCMonth() + 1);
    var step = total > 300 ? 2 : 1;
    while (d.toISOString().slice(0, 10) < end) {
      var iso = d.toISOString().slice(0, 10), xx = x(iso);
      if (xx > W - 50) break;
      svg.appendChild(s("line", { x1: xx, x2: xx, y1: top - 6, y2: H - 4, style: "stroke:var(--grid)" }));
      svg.appendChild(s("text", { x: xx + 3, y: top - 10, "font-size": 12, style: "fill:var(--muted)" }, tr("months")[d.getUTCMonth()] + (d.getUTCMonth() === 0 ? " " + d.getUTCFullYear() : "")));
      d.setUTCMonth(d.getUTCMonth() + step);
    }
    var colors = { land_prep: "var(--muted)", nursery: "var(--water)", initial: "#84cc16", development: "var(--leaf)", mid: "var(--amber)", late: "#a16207", harvest: "#dc2626" };
    st.forEach(function (row, i) {
      var yy = top + i * rh;
      svg.appendChild(s("text", { x: 4, y: yy + 18, "font-size": 13, "font-weight": 600, style: "fill:var(--text)" }, L(row.label)));
      var x1 = x(row.start), x2 = Math.max(x(row.end), x1 + 3);
      svg.appendChild(s("rect", { x: x1, y: yy + 5, width: x2 - x1, height: rh - 10, rx: 6, style: "fill:" + colors[row.key] + ";opacity:.9" }));
      var label = fmtDate(row.start) + (row.kc ? " · Kc " + row.kc : "");
      if (x2 - x1 > 110) svg.appendChild(s("text", { x: x1 + 6, y: yy + 18, "font-size": 11, "font-weight": 600, style: "fill:#fff" }, label));
    });
    if (cal.today >= start && cal.today <= end) {
      var tx = x(cal.today);
      svg.appendChild(s("line", { x1: tx, x2: tx, y1: top - 4, y2: H - 2, style: "stroke:var(--text);stroke-width:2;stroke-dasharray:4 3" }));
      svg.appendChild(s("text", { x: tx + 4, y: H - 6, "font-size": 11, "font-weight": 700, style: "fill:var(--text)" }, tr("today")));
    }
    clear($("calendar")).appendChild(svg);
    var ops = clear($("calOps"));
    cal.operations.forEach(function (o) { ops.appendChild(h("li", null, [h("b", { text: fmtDate(o.date, true) }), L(o.text)])); });
  }

  // ---------------------------------------------------------------- speech
  function speak() {
    var btn = $("speakBtn");
    var synth = window.speechSynthesis;
    if (!synth || typeof window.SpeechSynthesisUtterance === "undefined") { toast(tr("speechNA")); return; }
    try {
      if (state.speaking || synth.speaking) { synth.cancel(); state.speaking = false; btn.classList.remove("on"); return; }
      if (!state.result) return;
      var u = new window.SpeechSynthesisUtterance(L(state.result.speech));
      u.lang = state.lang === "ta" ? "ta-IN" : "en-IN";
      var voices = synth.getVoices() || [];
      var v = voices.filter(function (x) { return x.lang && x.lang.toLowerCase().indexOf(state.lang) === 0; })[0];
      if (v) u.voice = v; else if (state.lang === "ta") toast(tr("noTaVoice")); else toast(tr("reading"));
      u.rate = 0.95;
      u.onend = u.onerror = function () { state.speaking = false; btn.classList.remove("on"); };
      state.speaking = true; btn.classList.add("on");
      synth.speak(u);
    } catch (e) {
      state.speaking = false; btn.classList.remove("on"); toast(tr("speechNA"));
    }
  }

  function setLang(l) {
    state.lang = l;
    try { window.localStorage.setItem("km-lang", l); } catch (e) { /* ignore */ }
    try { if (window.speechSynthesis && state.speaking) { window.speechSynthesis.cancel(); state.speaking = false; } } catch (e) { /* ignore */ }
    applyStatic(); render();
  }

  // ---------------------------------------------------------------- boot
  function boot() {
    $("langEn").addEventListener("click", function () { setLang("en"); });
    $("langTa").addEventListener("click", function () { setLang("ta"); });
    $("speakBtn").addEventListener("click", speak);
    $("demoBtn").addEventListener("click", function () { loadPreset((state.preset + 1) % state.meta.presets.length, true); });
    $("farmForm").addEventListener("submit", function (e) { e.preventDefault(); submit(); });
    ["soil", "method", "cropChoice", "sowing"].forEach(function (id) { $(id).addEventListener("change", submit); });
    applyStatic();
    api("/api/meta").then(function (meta) {
      state.meta = meta;
      buildFeatureInputs();
      applyStatic();
      return loadPreset(0, false);
    }).catch(function () { toast(tr("netErr")); });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
