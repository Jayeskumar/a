/* PulseGuard front-end: vanilla JS, no external libraries, polls the local API. */
(function () {
  "use strict";

  var BAND_LABEL = { low: "Low", low_medium: "Low–medium", medium: "Medium", high: "High" };
  var VITALS = [
    { key: "rr", label: "Resp. rate", unit: "/min", ref: "rr" },
    { key: "spo2", label: "SpO2", unit: "%", ref: "spo2_1" },
    { key: "sbp", label: "Systolic BP", unit: "mmHg", ref: "sbp" },
    { key: "hr", label: "Pulse", unit: "/min", ref: "hr" },
    { key: "temp", label: "Temperature", unit: "°C", ref: "temp" }
  ];
  var POINT_COLOR = { 1: "var(--lowmed)", 2: "var(--medium)", 3: "var(--high)" };

  var state = {
    view: "ward", ward: null, drawerPid: null, detail: null, reference: null, evaluation: null,
    alertSig: "", inflight: false, calc: { scale: 1, o2: false, acvpu: "A" }, calcValid: false,
    handoverText: "", pollCount: 0
  };

  // ------------------------------------------------------------------ utils
  function $(sel) { return document.querySelector(sel); }
  function $all(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }
  function esc(v) {
    return String(v === null || v === undefined ? "" : v).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function api(path, opts) {
    opts = opts || {};
    var init = { method: opts.method || "GET", headers: {} };
    if (opts.body !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(opts.body);
    }
    return fetch(path, init).then(function (r) {
      return r.json().then(function (data) {
        if (!r.ok) { var e = new Error(data.error || ("HTTP " + r.status)); e.data = data; e.status = r.status; throw e; }
        return data;
      });
    });
  }
  function fmt(v, d) { return typeof v === "number" ? v.toFixed(d) : esc(v); }
  function bandClass(b) { return "b-" + b; }
  function signed(v, d) {
    var t = v.toFixed(d === undefined ? 1 : d);
    if (Number(t) === 0) return t.replace("-", "");
    return (v > 0 ? "+" : "") + t;
  }

  // --------------------------------------------------------------- controls
  function control(action, extra) {
    var body = Object.assign({ action: action }, extra || {});
    return api("/api/sim", { method: "POST", body: body }).then(function () {
      state.alertSig = "";
      return poll(true);
    }).catch(function (e) { console.warn(e.message); });
  }
  $("#btn-play").addEventListener("click", function () {
    control(state.ward && state.ward.clock.playing ? "pause" : "play");
  });
  $("#btn-skip").addEventListener("click", function () { control("skip", { hours: 1 }); });
  $("#btn-reset").addEventListener("click", function () { control("reset"); });
  $("#btn-demo").addEventListener("click", function () { closeDrawer(); showView("ward"); control("demo"); });

  function renderClock(c) {
    $("#clock").textContent = c.clock;
    $("#clock-sub").textContent = (c.finished ? "Scenario finished · " : (c.playing ? "Live · " : "Paused · ")) +
      c.minutes_per_step + " min per reading";
    $("#btn-play").textContent = c.playing ? "❚❚ Pause" : "▶ Play";
    var seg = $("#speed");
    var html = c.speeds.map(function (s) {
      return '<button type="button" data-speed="' + s + '" class="' + (s === c.speed ? "on" : "") +
        '" title="' + (s * c.minutes_per_step) + ' simulated minutes per second">' + s + "×</button>";
    }).join("");
    if (seg.innerHTML !== html) seg.innerHTML = html;
  }
  $("#speed").addEventListener("click", function (e) {
    var b = e.target.closest("button[data-speed]");
    if (b) control("speed", { speed: Number(b.getAttribute("data-speed")) });
  });

  // ------------------------------------------------------------------ tabs
  function showView(v) {
    state.view = v;
    $all(".tab").forEach(function (t) { t.classList.toggle("on", t.getAttribute("data-view") === v); });
    $all(".view").forEach(function (s) { s.hidden = s.id !== "view-" + v; });
    if (v === "handover") loadHandover();
    if (v === "eval") loadEvaluation();
    if (v === "ref") renderReference();
    if (v === "calc") fillPatientSelect();
  }
  $all(".tab").forEach(function (t) {
    t.addEventListener("click", function () { showView(t.getAttribute("data-view")); });
  });

  // ------------------------------------------------------------------ ward
  function sparkline(scores, band) {
    var w = 200, h = 34, n = scores.length;
    var max = Math.max(9, Math.max.apply(null, scores.concat([0])) + 1);
    function x(i) { return n <= 1 ? w : (i / (n - 1)) * (w - 4) + 2; }
    function y(v) { return h - 3 - (v / max) * (h - 6); }
    var pts = scores.map(function (s, i) { return x(i).toFixed(1) + "," + y(s).toFixed(1); }).join(" ");
    var last = scores[n - 1] || 0;
    return '<svg class="spark" viewBox="0 0 ' + w + " " + h + '" preserveAspectRatio="none" aria-label="NEWS2 trend over last 6 hours">' +
      '<line x1="0" x2="' + w + '" y1="' + y(5) + '" y2="' + y(5) + '" stroke="var(--medium)" stroke-dasharray="3 3" stroke-width="1" opacity=".6"/>' +
      '<line x1="0" x2="' + w + '" y1="' + y(7) + '" y2="' + y(7) + '" stroke="var(--high)" stroke-dasharray="3 3" stroke-width="1" opacity=".6"/>' +
      (n > 1 ? '<polyline points="' + pts + '" fill="none" stroke="var(--c)" stroke-width="2" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>' : "") +
      '<circle cx="' + x(n - 1) + '" cy="' + y(last) + '" r="2.6" fill="var(--c)"/></svg>';
  }

  function renderChips(s) {
    var c = s.band_counts;
    var items = [
      ["high", "High (≥7)", c.high], ["medium", "Medium (5–6)", c.medium],
      ["low_medium", "Low–med (single 3)", c.low_medium], ["low", "Low (0–4)", c.low]
    ];
    var html = items.map(function (it) {
      return '<div class="chip ' + bandClass(it[0]) + '"><span class="dot" style="background:var(--c)"></span><b>' + it[2] +
        '</b><span class="muted">' + it[1] + "</span></div>";
    }).join("");
    html += '<div class="chip b-trend"><span class="dot" style="background:var(--c)"></span><b>' + s.early_warnings +
      '</b><span class="muted">Early warnings (trend)</span></div>';
    html += '<div class="chip help">Tiles are sorted by acuity. Click a patient for the per-parameter score breakdown, vital-sign charts and trend analysis.</div>';
    $("#chips").innerHTML = html;
  }

  function vitalSpan(p, key, text) {
    var pts = p.points[key] || 0;
    return '<span class="' + (pts >= 2 ? "hot" : "") + '" title="' + pts + ' NEWS2 points">' + text + "</span>";
  }

  function renderTiles(patients) {
    $("#tiles").innerHTML = patients.map(function (p) {
      var v = p.vitals;
      var tr = p.trend;
      var arrow = tr.direction === "rising" ? "↑" : (tr.direction === "falling" ? "↓" : "→");
      return '<div class="tile ' + bandClass(p.band) + (tr.early_warning ? " ew" : "") + '" role="button" tabindex="0" data-pid="' + esc(p.id) + '">' +
        '<div class="row"><div class="score" title="NEWS2 aggregate score">' + p.score + '</div><div style="min-width:0;flex:1">' +
        '<div class="bed">Bed ' + p.bed + " · " + p.age + p.sex + "</div>" +
        '<div class="name">' + esc(p.name) + '</div><div class="diag" title="' + esc(p.diagnosis) + '">' + esc(p.diagnosis) + "</div></div></div>" +
        '<div class="row" style="gap:6px;flex-wrap:wrap"><span class="band-pill">' + esc(p.band_label) + " risk</span>" +
        (tr.early_warning ? '<span class="badge trend" title="' + esc(tr.reason) + '">↗ Early warning</span>' : "") +
        (p.scale === 2 ? '<span class="badge scale2" title="SpO2 scored on Scale 2 (hypercapnic respiratory failure)">SpO2 Scale 2</span>' : "") +
        (p.unacked_alerts ? '<span class="badge alerts">' + p.unacked_alerts + " alert" + (p.unacked_alerts > 1 ? "s" : "") + "</span>" : "") +
        "</div>" + sparkline(p.spark, p.band) +
        '<div class="vitals">' + vitalSpan(p, "rr", "RR " + v.rr) + vitalSpan(p, "spo2", "SpO2 " + v.spo2 + (v.o2 ? " O₂" : "")) +
        vitalSpan(p, "sbp", "BP " + v.sbp) + vitalSpan(p, "hr", "HR " + v.hr) + vitalSpan(p, "temp", "T " + fmt(v.temp, 1)) +
        vitalSpan(p, "acvpu", v.acvpu) + "</div>" +
        '<div class="foot"><span>Trend ' + arrow + " " + signed(tr.score_slope || 0) + "/h</span><span>" + esc(p.frequency) + "</span></div></div>";
    }).join("");
  }
  $("#tiles").addEventListener("click", function (e) {
    var t = e.target.closest(".tile");
    if (t) openPatient(t.getAttribute("data-pid"));
  });
  $("#tiles").addEventListener("keydown", function (e) {
    var t = e.target.closest(".tile");
    if (t && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); openPatient(t.getAttribute("data-pid")); }
  });

  function alertHtml(a) {
    var cls = a.type === "trend" ? "b-trend" : bandClass(a.band);
    var label = a.type === "trend" ? "Trend early warning" : (BAND_LABEL[a.band] + " risk");
    return '<div class="alert ' + cls + (a.acknowledged ? " acked" : "") + '">' +
      '<div class="head"><span class="band-pill">' + esc(label) + '</span><span class="muted">' + esc(a.clock) + "</span></div>" +
      '<div class="msg"><a href="#" data-open="' + esc(a.patient_id) + '" style="color:inherit">Bed ' + a.bed + " · " + esc(a.patient) + "</a> — " + esc(a.message) + "</div>" +
      (a.contributors && a.contributors.length ? '<div class="contrib">' + a.contributors.map(esc).join(" · ") + "</div>" : "") +
      '<details><summary>Escalation: ' + esc(a.frequency) + "</summary><div>" + esc(a.response) + "</div></details>" +
      '<div class="act">' + (a.acknowledged
        ? '<span class="muted" style="font-size:12px">✓ Acknowledged by ' + esc(a.ack_by) + " at " + esc(a.ack_clock) + "</span>"
        : '<span class="muted" style="font-size:12px">Awaiting acknowledgement</span><button class="btn small primary" data-ack="' + a.id + '">Acknowledge</button>') +
      "</div></div>";
  }

  function renderAlerts(alerts, unacked) {
    var sig = alerts.map(function (a) { return a.id + (a.acknowledged ? "a" : "u"); }).join(",");
    $("#feed-count").textContent = unacked ? "(" + unacked + " unacknowledged)" : "";
    var badge = $("#tab-alerts");
    badge.hidden = !unacked;
    badge.textContent = unacked;
    if (sig === state.alertSig) return;
    state.alertSig = sig;
    $("#alerts").innerHTML = alerts.length ? alerts.map(alertHtml).join("") :
      '<div class="empty">No alerts yet. Press <b>Run demo</b> to start the ward clock.</div>';
  }
  document.addEventListener("click", function (e) {
    var ack = e.target.closest("[data-ack]");
    if (ack) {
      ack.disabled = true;
      api("/api/alerts/" + ack.getAttribute("data-ack") + "/ack", { method: "POST", body: { by: "Nurse on duty" } })
        .then(function () { state.alertSig = ""; return poll(true); })
        .catch(function (err) { console.warn(err.message); });
      return;
    }
    var op = e.target.closest("[data-open]");
    if (op) { e.preventDefault(); openPatient(op.getAttribute("data-open")); }
  });

  // ---------------------------------------------------------------- drawer
  function openPatient(pid) {
    state.drawerPid = pid;
    $("#overlay").hidden = false;
    $("#drawer").hidden = false;
    loadDetail();
  }
  function closeDrawer() {
    state.drawerPid = null;
    state.detail = null;
    $("#overlay").hidden = true;
    $("#drawer").hidden = true;
    $("#drawer").innerHTML = "";
  }
  $("#overlay").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && state.drawerPid) closeDrawer(); });

  function loadDetail() {
    var pid = state.drawerPid;
    if (!pid) return Promise.resolve();
    return api("/api/patients/" + encodeURIComponent(pid)).then(function (d) {
      if (state.drawerPid !== pid) return;
      state.detail = d;
      renderDrawer(d);
    }).catch(function (e) { console.warn(e.message); });
  }

  function zonesFor(refKey) {
    if (!state.reference) return [];
    var param = state.reference.parameters.filter(function (p) { return p.key === refKey; })[0];
    if (!param) return [];
    var zones = [], lower = -Infinity;
    param.rows.forEach(function (r) {
      if (refKey === "spo2_2" && r.range.indexOf("oxygen") >= 0) return;
      var upper = r.upper === null ? Infinity : r.upper;
      zones.push({ lo: lower, hi: upper, pts: r.points });
      lower = upper;
    });
    return zones;
  }

  function lineChart(hist, key, opts) {
    var w = 260, h = 120, padL = 32, padR = 6, padT = 6, padB = 18;
    var vals = hist.map(function (r) { return r[key]; });
    var ts = hist.map(function (r) { return r.t; });
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    var hasProj = opts.projection !== undefined && opts.projection !== null;
    if (hasProj) { lo = Math.min(lo, opts.projection); hi = Math.max(hi, opts.projection); }
    if (opts.min !== undefined) lo = Math.min(lo, opts.min);
    if (opts.max !== undefined) hi = Math.max(hi, opts.max);
    var span = hi - lo || 1;
    lo -= span * 0.1; hi += span * 0.1;
    var t0 = ts[0], tLast = ts[ts.length - 1], t1 = tLast + (opts.horizon || 0);
    if (t1 === t0) t1 = t0 + 1;
    function X(t) { return padL + (t - t0) / (t1 - t0) * (w - padL - padR); }
    function Y(v) { return padT + (1 - (v - lo) / (hi - lo)) * (h - padT - padB); }
    var out = '<svg viewBox="0 0 ' + w + " " + h + '" role="img" aria-label="' + esc(opts.label) + ' chart">';
    (opts.zones || []).forEach(function (z) {
      if (!z.pts) return;
      var a = Math.max(lo, z.lo), b = Math.min(hi, z.hi);
      if (b <= a) return;
      out += '<rect x="' + padL + '" width="' + (w - padL - padR) + '" y="' + Y(b) + '" height="' + (Y(a) - Y(b)) +
        '" fill="' + POINT_COLOR[z.pts] + '" opacity="' + (0.08 + 0.06 * z.pts) + '"/>';
    });
    [lo + (hi - lo) * 0.1, (lo + hi) / 2, hi - (hi - lo) * 0.1].forEach(function (v) {
      out += '<text x="' + (padL - 4) + '" y="' + (Y(v) + 3) + '" text-anchor="end" font-size="12" fill="var(--muted)">' +
        (opts.dec ? v.toFixed(opts.dec) : Math.round(v)) + "</text>";
    });
    var step = Math.max(1, Math.ceil((t1 - t0) / 4));
    for (var t = Math.ceil(t0); t <= t1; t += step) {
      var hh = (6 + Math.floor(t)) % 24;
      out += '<text x="' + X(t) + '" y="' + (h - 3) + '" text-anchor="' + (X(t) > w - 20 ? "end" : "middle") + '" font-size="12" fill="var(--muted)">' + (hh < 10 ? "0" : "") + hh + ":00</text>";
    }
    if (opts.horizon) {
      out += '<rect x="' + X(tLast) + '" width="' + (X(t1) - X(tLast)) + '" y="' + padT + '" height="' + (h - padT - padB) +
        '" fill="var(--surface-2)" opacity=".7"><title>Next ' + opts.horizon + ' h (projection)</title></rect>';
    }
    var pts = hist.map(function (r) { return X(r.t).toFixed(1) + "," + Y(r[key]).toFixed(1); }).join(" ");
    out += '<polyline points="' + pts + '" fill="none" stroke="' + (opts.color || "var(--brand)") + '" stroke-width="1.8" stroke-linejoin="round"/>';
    hist.forEach(function (r) {
      if (r.source === "manual") out += '<circle cx="' + X(r.t) + '" cy="' + Y(r[key]) + '" r="3.5" fill="var(--surface)" stroke="var(--text)" stroke-width="1.5"><title>Manual observation</title></circle>';
    });
    if (hasProj) {
      var last = hist[hist.length - 1];
      out += '<line x1="' + X(last.t) + '" y1="' + Y(last[key]) + '" x2="' + X(t1) + '" y2="' + Y(opts.projection) +
        '" stroke="var(--trend)" stroke-width="1.6" stroke-dasharray="4 3"><title>Projected trend</title></line>';
    }
    return out + "</svg>";
  }

  function breakdownTable(res) {
    return '<table><thead><tr><th>Parameter</th><th class="num">Value</th><th>Chart band</th><th class="num">Points</th><th style="width:28%">Contribution</th></tr></thead><tbody>' +
      res.parameters.map(function (p) {
        var share = res.total ? Math.round(p.points / res.total * 100) : 0;
        return "<tr><td>" + esc(p.label) + '</td><td class="num mono">' + esc(p.value) + (p.unit ? " " + esc(p.unit) : "") + "</td><td>" + esc(p.range) +
          '</td><td class="num"><span class="pts p' + p.points + '">' + p.points + '</span></td><td><div class="bar" style="--c:' + (POINT_COLOR[p.points] || "var(--muted)") +
          '"><i style="width:' + share + '%"></i></div><span class="note">' + (p.points ? share + "% of score" : "–") + "</span></td></tr>";
      }).join("") + '<tr><td colspan="3"><b>Aggregate NEWS2</b></td><td class="num"><b>' + res.total + "</b></td><td>" +
      (res.red_params.length ? '<span class="note">Red score (3) in: ' + res.parameters.filter(function (p) { return p.points === 3; }).map(function (p) { return esc(p.label); }).join(", ") + "</span>" : "") + "</td></tr></tbody></table>";
  }

  function responseBox(res) {
    return '<div class="response ' + bandClass(res.band) + '"><b>' + esc(res.band_label) + " clinical risk · " + esc(res.frequency) + "</b><div>" + esc(res.response) + "</div></div>";
  }

  function trendPanel(tr) {
    if (!tr || !tr.enough_data) return '<div class="note">' + esc(tr ? tr.reason : "No data") + "</div>";
    var head = tr.early_warning
      ? '<div class="callout"><b>↗ Early warning.</b> ' + esc(tr.reason) + "</div>"
      : '<div class="note">Status: ' + esc(tr.reason) + "</div>";
    return head + '<table style="margin-top:6px"><thead><tr><th>Vital</th><th class="num">Slope / h</th><th class="num">R²</th><th class="num">Now → +' + tr.horizon_h +
      ' h</th><th class="num">Points</th></tr></thead><tbody>' + tr.vitals.map(function (v) {
        return "<tr" + (v.worsening ? ' style="background:var(--trend-bg)"' : "") + "><td>" + esc(v.label) + (v.worsening ? " ↗" : "") +
          '</td><td class="num mono">' + signed(v.slope_per_h, 2) + '</td><td class="num mono">' + v.r2.toFixed(2) +
          '</td><td class="num mono">' + esc(v.current) + " → " + (v.significant ? esc(v.projected) : '<span class="muted">n.s.</span>') +
          '</td><td class="num">' + v.points_now + " → " + v.points_projected + "</td></tr>";
      }).join("") + '</tbody></table><div class="note" style="margin-top:6px">Least-squares line over the last ' + tr.window +
      " readings. Aggregate score slope " + signed(tr.score_slope, 2) + "/h (R² " + tr.score_r2.toFixed(2) + "). Projected NEWS2 in " + tr.horizon_h + " h: <b>" +
      tr.projected_score + "</b> (now " + tr.current_score + "). Only trends with R² ≥ 0.55 and a clinically meaningful change are projected (n.s. = not significant).</div>";
  }

  function renderDrawer(d) {
    var p = d.patient, res = d.breakdown, tr = d.trend || {};
    var hist = d.history;
    var projBy = {};
    (tr.vitals || []).forEach(function (v) { if (v.significant) projBy[v.key] = v.projected; });
    var charts = '<div class="chart"><h3><span>NEWS2 score</span><span>' + p.score + "</span></h3>" +
      lineChart(hist, "score", { label: "NEWS2", min: 0, max: 8, color: "var(--text)", horizon: tr.horizon_h, projection: tr.enough_data ? tr.projected_score : null, zones: [{ lo: 4.5, hi: 6.5, pts: 2 }, { lo: 6.5, hi: Infinity, pts: 3 }] }) + "</div>";
    VITALS.forEach(function (v) {
      var refKey = v.key === "spo2" && p.scale === 2 ? "spo2_2" : v.ref;
      charts += '<div class="chart"><h3><span>' + v.label + " (" + v.unit + ")</span><span>" + (v.key === "temp" ? fmt(p.vitals.temp, 1) : esc(p.vitals[v.key])) + "</span></h3>" +
        lineChart(hist, v.key, { label: v.label, zones: zonesFor(refKey), dec: v.key === "temp" ? 1 : 0, projection: projBy[v.key], horizon: tr.horizon_h }) + "</div>";
    });
    var s1 = d.scale1_comparison
      ? '<div class="callout" style="margin-top:8px"><b>SpO2 Scale 2 in use.</b> This COPD patient\'s target is 88–92%. Scored on Scale 1 the same vitals would give NEWS2 ' +
        d.scale1_comparison.total + " (" + esc(d.scale1_comparison.band_label) + "), because SpO2 ≤91% scores 3 on Scale 1 – an escalation that is not clinically indicated for this patient.</div>" : "";
    var html = '<div class="dhead ' + bandClass(p.band) + '"><div class="score">' + p.score + '</div><div style="flex:1;min-width:0"><div class="bed muted" style="font-size:12px">Bed ' +
      p.bed + " · " + p.age + p.sex + " · last reading " + esc(p.last_clock) + (p.source === "manual" ? " (manual)" : "") + '</div><h2 style="font-size:18px">' + esc(p.name) +
      '</h2><div class="muted">' + esc(p.diagnosis) + '</div></div><button class="btn" id="btn-manual">Record manual obs</button><button class="btn" id="btn-close" aria-label="Close">✕</button></div>' +
      '<div class="dbody">' + responseBox(res) +
      '<div class="card panel"><h2>Why this score? Per-parameter breakdown</h2>' + breakdownTable(res) + s1 + "</div>" +
      '<div class="card panel"><h2>Vital signs (shaded = NEWS2 scoring zones; dashed = projected trend)</h2><div class="charts">' + charts + "</div></div>" +
      '<div class="card panel"><h2>Trend detector</h2>' + trendPanel(tr) + "</div>" +
      '<div class="grid2"><div class="card panel"><h2>Alerts for this patient</h2>' + (d.alerts.length ? d.alerts.slice(0, 6).map(alertHtml).join("") : '<div class="note">None.</div>') +
      '</div><div class="card panel"><h2>Handover note</h2><pre class="mono" style="white-space:pre-wrap;font-size:12px;margin:0">' + esc(d.handover) + "</pre></div></div></div>";
    var drawer = $("#drawer");
    var scroll = drawer.scrollTop;
    drawer.innerHTML = html;
    drawer.scrollTop = scroll;
    $("#btn-close").addEventListener("click", closeDrawer);
    $("#btn-manual").addEventListener("click", function () { prefillCalc(d); });
  }

  // ------------------------------------------------------------ calculator
  var EXAMPLES = {
    normal: { rr: 16, spo2: 98, sbp: 124, hr: 72, temp: 36.8, scale: 1, o2: false, acvpu: "A" },
    sepsis: { rr: 23, spo2: 95, sbp: 104, hr: 112, temp: 38.6, scale: 1, o2: false, acvpu: "A" },
    copd: { rr: 20, spo2: 89, sbp: 136, hr: 88, temp: 36.9, scale: 2, o2: false, acvpu: "A" },
    shock: { rr: 28, spo2: 91, sbp: 86, hr: 134, temp: 39.4, scale: 1, o2: true, acvpu: "C" }
  };
  function setSeg(id, val) {
    $all("#" + id + " button").forEach(function (b) { b.classList.toggle("on", b.getAttribute("data-v") === String(val)); });
  }
  function setCalc(v) {
    ["rr", "spo2", "sbp", "hr", "temp"].forEach(function (k) { $("#f-" + k).value = v[k]; });
    state.calc.scale = v.scale; state.calc.o2 = !!v.o2; state.calc.acvpu = v.acvpu;
    setSeg("f-scale", v.scale); setSeg("f-o2", v.o2 ? 1 : 0); setSeg("f-acvpu", v.acvpu);
    scheduleCalc();
  }
  $all("[data-ex]").forEach(function (b) {
    b.addEventListener("click", function () { setCalc(EXAMPLES[b.getAttribute("data-ex")]); });
  });
  [["f-scale", "scale", Number], ["f-o2", "o2", function (v) { return v === "1"; }], ["f-acvpu", "acvpu", String]].forEach(function (s) {
    $("#" + s[0]).addEventListener("click", function (e) {
      var b = e.target.closest("button[data-v]");
      if (!b) return;
      state.calc[s[1]] = s[2](b.getAttribute("data-v"));
      setSeg(s[0], b.getAttribute("data-v"));
      scheduleCalc();
    });
  });
  $("#calc-form").addEventListener("input", scheduleCalc);
  $("#calc-form").addEventListener("submit", function (e) { e.preventDefault(); });
  $("#f-patient").addEventListener("change", updateSaveBtn);

  var calcTimer = null;
  function scheduleCalc() { clearTimeout(calcTimer); calcTimer = setTimeout(runCalc, 120); }
  function calcBody() {
    var body = { scale: state.calc.scale, o2: state.calc.o2, acvpu: state.calc.acvpu };
    ["rr", "spo2", "sbp", "hr", "temp"].forEach(function (k) {
      var v = $("#f-" + k).value;
      body[k] = v === "" ? null : Number(v);
    });
    return body;
  }
  function runCalc() {
    var body = calcBody();
    api("/api/news2", { method: "POST", body: body }).then(function (res) {
      showFieldErrors({}, body);
      state.calcValid = true;
      $("#calc-result").innerHTML = '<div class="big-result ' + bandClass(res.band) + '"><div class="score">' + res.total + '</div><div><div class="band-pill">' +
        esc(res.band_label) + ' clinical risk</div><h2 style="font-size:18px;margin-top:4px">' + esc(res.frequency) + '</h2><div class="note">Computed in ' + res.compute_us +
        " µs on the server · SpO2 Scale " + res.scale + '</div></div></div><div class="panel" style="padding-top:0">' + responseBox(res) +
        '<div style="margin-top:10px">' + breakdownTable(res) + "</div></div>";
      updateSaveBtn();
    }).catch(function (e) {
      state.calcValid = false;
      updateSaveBtn();
      var errs = (e.data && e.data.details) || {};
      showFieldErrors(errs, body);
      var missing = Object.keys(errs).filter(function (k) { return body[k] === null; });
      $("#calc-result").innerHTML = '<div class="panel muted">' + (missing.length ? "Waiting for: " + missing.map(function (k) {
        return { rr: "respiration rate", spo2: "SpO2", sbp: "systolic BP", hr: "pulse", temp: "temperature" }[k] || k;
      }).join(", ") + "." : "Please correct the highlighted values.") + "</div>";
    });
  }
  function showFieldErrors(errs, body) {
    ["rr", "spo2", "sbp", "hr", "temp"].forEach(function (k) {
      var show = errs[k] && body[k] !== null;
      $("#f-" + k).classList.toggle("bad", !!show);
      $('[data-err="' + k + '"]').textContent = show ? errs[k] : "";
    });
  }
  function fillPatientSelect() {
    if (!state.ward) return;
    var sel = $("#f-patient"), cur = sel.value;
    var opts = '<option value="">– bedside calculator only –</option>' + state.ward.patients.slice().sort(function (a, b) { return a.bed - b.bed; }).map(function (p) {
      return '<option value="' + esc(p.id) + '">Bed ' + p.bed + " · " + esc(p.name) + (p.scale === 2 ? " (Scale 2)" : "") + "</option>";
    }).join("");
    if (sel.innerHTML !== opts) { sel.innerHTML = opts; sel.value = cur; }
    updateSaveBtn();
  }
  function updateSaveBtn() { $("#btn-save-obs").disabled = !(state.calcValid && $("#f-patient").value); }
  function prefillCalc(d) {
    var v = d.patient.vitals;
    closeDrawer();
    showView("calc");
    fillPatientSelect();
    $("#f-patient").value = d.patient.id;
    setCalc({ rr: v.rr, spo2: v.spo2, sbp: v.sbp, hr: v.hr, temp: v.temp, scale: d.patient.scale, o2: v.o2, acvpu: v.acvpu });
    $("#save-msg").textContent = "Prefilled with the latest monitor reading – edit and record.";
  }
  $("#btn-save-obs").addEventListener("click", function () {
    var pid = $("#f-patient").value;
    if (!pid) return;
    api("/api/patients/" + encodeURIComponent(pid) + "/observations", { method: "POST", body: calcBody() }).then(function (r) {
      $("#save-msg").textContent = "Recorded for " + pid + " at the current ward time · NEWS2 " + r.reading.score +
        (r.alerts.length ? " · " + r.alerts.length + " alert(s) raised" : "") + ".";
      state.alertSig = "";
      poll(true);
    }).catch(function (e) { $("#save-msg").textContent = "Not saved: " + e.message; });
  });

  // -------------------------------------------------------------- handover
  function loadHandover() {
    return api("/api/handover").then(function (h) {
      state.handoverText = h.text;
      $("#handover-clock").textContent = "Generated at " + h.clock + " (simulated ward time)";
      $("#handover-list").innerHTML = h.patients.map(function (p) {
        return '<div class="card handover-item ' + bandClass(p.band) + '"><pre>' + esc(p.text) + "</pre></div>";
      }).join("");
    }).catch(function (e) { console.warn(e.message); });
  }
  $("#btn-print").addEventListener("click", function () { window.print(); });
  $("#btn-copy").addEventListener("click", function () {
    var txt = state.handoverText;
    var done = function () { $("#btn-copy").textContent = "Copied ✓"; setTimeout(function () { $("#btn-copy").textContent = "Copy as text"; }, 1500); };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(txt).then(done, function () { fallbackCopy(txt); done(); });
    } else { fallbackCopy(txt); done(); }
  });
  function fallbackCopy(txt) {
    var ta = document.createElement("textarea");
    ta.value = txt; ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); } catch (e) { /* ignore */ }
    document.body.removeChild(ta);
  }

  // ------------------------------------------------------------- reference
  function renderReference() {
    var r = state.reference;
    if (!r) return;
    $("#ref-source").textContent = "Source: " + r.source;
    $("#ref-params").innerHTML = r.parameters.map(function (p) {
      return '<div class="card panel"><h2>' + esc(p.label) + '</h2><table><tbody>' + p.rows.map(function (row) {
        return "<tr><td>" + esc(row.range) + '</td><td class="num"><span class="pts p' + row.points + '">' + row.points + "</span></td></tr>";
      }).join("") + "</tbody></table></div>";
    }).join("");
    $("#ref-bands").innerHTML = '<table><thead><tr><th>Band</th><th>Trigger</th><th>Monitoring</th><th>Clinical response</th></tr></thead><tbody>' +
      r.bands.map(function (b) {
        return '<tr class="' + bandClass(b.band) + '"><td><span class="band-pill">' + esc(b.label) + "</span></td><td>" + esc(b.rule) + "</td><td>" + esc(b.frequency) +
          "</td><td>" + esc(b.response) + "</td></tr>";
      }).join("") + "</tbody></table><ul class=\"note\">" + r.notes.map(function (n) { return "<li>" + esc(n) + "</li>"; }).join("") + "</ul>";
  }

  // ------------------------------------------------------------ evaluation
  function loadEvaluation() {
    if (state.evaluation) return renderEvaluation(state.evaluation);
    api("/api/evaluation").then(function (e) { state.evaluation = e; renderEvaluation(e); })
      .catch(function (e) { $("#eval-body").innerHTML = '<div class="card panel">Evaluation failed: ' + esc(e.message) + "</div>"; });
  }
  function hrs(v) { return v === null || v === undefined ? "–" : v.toFixed(2).replace(/\.?0+$/, "") + " h"; }
  function clockOf(t) {
    if (t === null || t === undefined) return "–";
    var m = Math.round(360 + t * 60), hh = Math.floor(m / 60) % 24, mm = m % 60;
    return (hh < 10 ? "0" : "") + hh + ":" + (mm < 10 ? "0" : "") + mm;
  }
  function timeline(rows) {
    // drawn at the container's real pixel width so labels stay ~12 px on any screen
    var avail = ($("#eval-body").clientWidth || 1200) - 30;
    var w = Math.max(320, Math.min(1200, avail)), rowH = 30, h = rows.length * rowH + 28;
    var padL = w < 700 ? 104 : 130, padR = 20, tStep = w < 520 ? 6 : (w < 900 ? 4 : 2);
    function X(t) { return padL + t / 24 * (w - padL - padR); }
    var out = '<svg viewBox="0 0 ' + w + " " + h + '" role="img" aria-label="Detection timeline">';
    for (var t = 0; t <= 24; t += tStep) {
      out += '<line x1="' + X(t) + '" x2="' + X(t) + '" y1="4" y2="' + (h - 18) + '" stroke="var(--border)"/><text x="' + X(t) + '" y="' + (h - 4) +
        '" font-size="12" text-anchor="middle" fill="var(--muted)">' + clockOf(t) + "</text>";
    }
    rows.forEach(function (r, i) {
      var y = 6 + i * rowH + rowH / 2;
      out += '<text x="4" y="' + (y + 4) + '" font-size="13" fill="var(--text)">' + esc(r.name) + "</text>";
      out += '<line x1="' + X(r.onset_h) + '" x2="' + X(24) + '" y1="' + y + '" y2="' + y + '" stroke="var(--medium)" stroke-width="8" opacity=".22" stroke-linecap="round"><title>Deterioration from ' + clockOf(r.onset_h) + "</title></line>";
      function mark(t, color, label, shape) {
        if (t === null || t === undefined) return "";
        var tip = "<title>" + label + " " + clockOf(t) + "</title>";
        if (shape === "sq") return '<rect x="' + (X(t) - 6) + '" y="' + (y - 6) + '" width="12" height="12" fill="none" stroke="' + color + '" stroke-width="2.5">' + tip + "</rect>";
        return '<circle cx="' + X(t) + '" cy="' + y + '" r="' + (shape === "big" ? 7 : 5) + '" fill="' + color + '">' + tip + "</circle>";
      }
      out += mark(r.t_manual, "var(--muted)", "4-hourly round sees NEWS2≥5", "sq") + mark(r.t_threshold, "var(--medium)", "Continuous NEWS2≥5", "big") +
        mark(r.t_trend, "var(--trend)", "PulseGuard trend alert", "dot");
    });
    return '<div class="legend"><span><i style="background:var(--trend)"></i>PulseGuard trend alert</span><span><i style="background:var(--medium)"></i>Continuous NEWS2 ≥5</span>' +
      '<span><i style="border:2px solid var(--muted);border-radius:0;width:8px;height:8px"></i>4-hourly paper round sees NEWS2 ≥5</span><span><i style="background:var(--medium);opacity:.3"></i>Deterioration under way</span></div>' +
      out + "</svg>";
  }
  function renderEvaluation(e) {
    var lt = e.lead_vs_threshold_h || {}, lm = e.lead_vs_manual_h || {}, lat = e.latency;
    var demo = e.demo_ward.filter(function (r) { return r.kind === "deteriorating"; });
    var kpis = [
      [hrs(lt.median), "median extra warning vs. continuous NEWS2≥5 alert (" + e.deteriorating_episodes + " episodes, " + e.seeds + " seeds)"],
      [hrs(lm.median), "median earlier than a 4-hourly paper-chart round reaching NEWS2≥5"],
      [e.detected_by_trend_before_threshold + "/" + e.deteriorating_episodes, "episodes where the trend alert fired before the threshold"],
      [e.stable_trend_alerts_per_patient_day.toFixed(3), "trend false alerts per non-deteriorating patient-day (" + e.stable_trend_alerts + " in " + e.stable_patient_days + ")"],
      [e.copd_scale1_red_readings + " → " + e.copd_scale2_red_readings, "COPD readings that would trigger escalation: Scale 1 → Scale 2"],
      [lat.news2_score_us + " µs", "NEWS2 scoring latency (score + trend: " + lat.score_plus_trend_us + " µs)"]
    ];
    var ho = e.holdout;
    var hoHtml = ho ? '<div class="card panel" style="margin-bottom:12px"><h2>Held-out check (seeds ' + esc(ho.seeds) + ', never used for tuning)</h2><div class="note">' +
      "Median extra warning vs. continuous threshold <b>" + hrs(ho.lead_vs_threshold_h.median) + "</b> · vs. 4-hourly round <b>" + hrs(ho.lead_vs_manual_h.median) +
      "</b> · trend fired first in <b>" + ho.detected_by_trend_before_threshold + "/" + ho.deteriorating_episodes + "</b> episodes · false trend alerts <b>" +
      ho.stable_trend_alerts + "</b> in " + ho.stable_patient_days + " patient-days (" + ho.stable_trend_alerts_per_patient_day.toFixed(3) + "/day). The headline cards above use the tuning seeds 1–30.</div></div>" : "";
    $("#eval-body").innerHTML = '<div class="kpis">' + kpis.map(function (k) {
      return '<div class="card kpi"><b>' + esc(k[0]) + "</b><span>" + esc(k[1]) + "</span></div>";
    }).join("") + '</div>' + hoHtml + '<div class="card panel timeline"><h2>Demo ward (seed 42): when would each deterioration be noticed?</h2>' + timeline(demo) +
      '<table style="margin-top:8px"><thead><tr><th>Patient</th><th>Onset</th><th>Trend alert</th><th>NEWS2 ≥5</th><th>4-h round</th><th class="num">Lead vs threshold</th><th class="num">Lead vs round</th></tr></thead><tbody>' +
      demo.map(function (r) {
        return "<tr><td>" + esc(r.name) + "</td><td>" + clockOf(r.onset_h) + "</td><td>" + clockOf(r.t_trend) + "</td><td>" + clockOf(r.t_threshold) + "</td><td>" + clockOf(r.t_manual) +
          '</td><td class="num">' + hrs(r.lead_vs_threshold) + '</td><td class="num">' + hrs(r.lead_vs_manual) + "</td></tr>";
      }).join("") + '</tbody></table><p class="note">Simulated data only. Lead time = time between PulseGuard\'s first alert and the comparison alert. Full method in REPORT.md.</p></div>' +
      (e.sensitivity ? '<div class="card panel" style="margin-top:12px"><h2>Trade-off: early warning vs. false alerts (' + e.seeds + ' seeds)</h2><table><thead><tr><th>Setting</th><th class="num">Median lead vs threshold</th><th class="num">Trend fired first</th><th class="num">False trend alerts</th><th class="num">Per patient-day</th></tr></thead><tbody>' +
        e.sensitivity.map(function (r) {
          return "<tr><td>" + esc(r.label) + '</td><td class="num">' + hrs(r.lead_vs_threshold_median_h) + '</td><td class="num">' + r.trend_first + "/" + r.episodes +
            '</td><td class="num">' + r.false_trend_alerts + '</td><td class="num">' + r.false_per_patient_day.toFixed(3) + "</td></tr>";
        }).join("") + '</tbody></table><p class="note">All knobs live in pulseguard/config.py. The shipped setting balances ~1 h of extra warning against roughly one false trend alert per 38 patient-days.</p></div>' : "");
  }

  // ------------------------------------------------------------------ poll
  function poll(force) {
    if (state.inflight && !force) return Promise.resolve();
    state.inflight = true;
    return api("/api/ward").then(function (s) {
      var prevStep = state.ward ? state.ward.clock.step : -1;
      state.ward = s;
      renderClock(s.clock);
      renderChips(s);
      renderTiles(s.patients);
      renderAlerts(s.alerts, s.unacked_alerts);
      var changed = s.clock.step !== prevStep || force;
      if (state.drawerPid && changed) loadDetail();
      if (state.view === "handover" && changed) loadHandover();
      if (state.view === "calc") fillPatientSelect();
    }).catch(function (e) { console.warn("poll failed", e.message); })
      .then(function () { state.inflight = false; });
  }

  api("/api/news2/reference").then(function (r) { state.reference = r; }).catch(function () { /* charts work without zones */ })
    .then(function () { return poll(true); });
  setInterval(poll, 1000);
})();
