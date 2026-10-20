/* WattWise dashboard - vanilla JS, hand-drawn SVG charts, no external libraries. */
(function () {
  'use strict';

  var NS = 'http://www.w3.org/2000/svg';
  var $ = function (s) { return document.querySelector(s); };
  var state = {
    building: 'cse_lab', buildings: [], overview: null, series: null, heat: null,
    anomalies: null, board: null, evaluation: null, solar: null, whatif: null, tab: 'overview'
  };
  var LEVERS = [
    { key: 'auto_off', label: 'Auto-off', color: 'var(--s1)' },
    { key: 'ac', label: 'AC setpoint', color: 'var(--s2)' },
    { key: 'led', label: 'LED retrofit', color: 'var(--s3)' },
    { key: 'bldc', label: 'BLDC fans', color: 'var(--s4)' }
  ];
  var DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  // ------------------------------------------------------------------ helpers
  function api(path, opts) {
    return fetch(path, opts).then(function (r) {
      return r.json().then(function (j) {
        if (!r.ok) { throw new Error(j.error || r.statusText); }
        return j;
      });
    });
  }
  function post(path, body) {
    return api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
  }
  function svg(tag, attrs, parent) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs) { if (attrs[k] !== undefined && attrs[k] !== null) { e.setAttribute(k, attrs[k]); } }
    if (parent) { parent.appendChild(e); }
    return e;
  }
  function html(tag, attrs, text) {
    var e = document.createElement(tag);
    for (var k in (attrs || {})) { e.setAttribute(k, attrs[k]); }
    if (text !== undefined) { e.textContent = text; }
    return e;
  }
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function num(n, d) {
    if (n === null || n === undefined || isNaN(n)) { return '–'; }
    return Number(n).toLocaleString('en-IN', { maximumFractionDigits: d || 0, minimumFractionDigits: d || 0 });
  }
  function inr(n) {
    if (n === null || n === undefined || isNaN(n)) { return '–'; }
    var a = Math.abs(n), s = n < 0 ? '-' : '';
    if (a >= 1e7) { return s + '₹' + (a / 1e7).toFixed(2) + ' Cr'; }
    if (a >= 1e5) { return s + '₹' + (a / 1e5).toFixed(2) + ' L'; }
    return s + '₹' + num(a);
  }
  function compact(n) {
    var a = Math.abs(n);
    if (a >= 1e6) { return (n / 1e6).toFixed(1) + 'M'; }
    if (a >= 1e3) { return (n / 1e3).toFixed(a >= 1e4 ? 0 : 1) + 'k'; }
    return num(n);
  }
  function parseTs(s) { // ISO local time 'YYYY-MM-DDTHH:MM:SS'
    var p = s.split(/[-T:]/);
    return new Date(+p[0], +p[1] - 1, +p[2], +p[3] || 0, +p[4] || 0);
  }
  function hourLabel(h) { return h === 0 ? '12 AM' : h === 12 ? '12 PM' : h < 12 ? h + ' AM' : (h - 12) + ' PM'; }
  function fmtTs(d) { return DAYS[d.getDay()] + ' ' + d.getDate() + ' ' + MONTHS[d.getMonth()] + ', ' + hourLabel(d.getHours()); }
  function fmtDay(d) { return d.getDate() + ' ' + MONTHS[d.getMonth()]; }
  function cssVar(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
  function hexToRgb(h) {
    h = h.replace('#', '');
    if (h.length === 3) { h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2]; }
    return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
  }
  function mix(a, b, t) {
    return 'rgb(' + [0, 1, 2].map(function (i) { return Math.round(a[i] + (b[i] - a[i]) * t); }).join(',') + ')';
  }
  function niceMax(v) {
    if (v <= 0) { return 1; }
    var p = Math.pow(10, Math.floor(Math.log10(v))), f = v / p;
    return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * p;
  }
  function buildingName(id) {
    for (var i = 0; i < state.buildings.length; i++) { if (state.buildings[i].id === id) { return state.buildings[i].name; } }
    return id;
  }

  // ------------------------------------------------------------------ tooltip & toast
  var tip = $('#tooltip');
  function showTip(evt, content) {
    tip.innerHTML = content;
    tip.hidden = false;
    var r = tip.getBoundingClientRect();
    var x = evt.clientX + 14, y = evt.clientY + 14;
    if (x + r.width > window.innerWidth - 8) { x = evt.clientX - r.width - 14; }
    if (y + r.height > window.innerHeight - 8) { y = evt.clientY - r.height - 14; }
    tip.style.left = Math.max(8, x) + 'px';
    tip.style.top = Math.max(8, y) + 'px';
  }
  function hideTip() { tip.hidden = true; }
  var toastTimer = null;
  function toast(msg, ms) {
    var t = $('#toast');
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.hidden = true; }, ms || 5000);
  }
  function tipRow(color, label, value, dashed) {
    var sw = color ? '<i class="sw ' + (dashed ? 'sw-dash' : 'sw-line') + '" style="border-color:' + color + '"></i>' : '';
    return '<div class="t-r">' + sw + esc(label) + '<b>' + esc(value) + '</b></div>';
  }

  // ------------------------------------------------------------------ tabs
  function showTab(name) {
    if (!document.getElementById('tab-' + name)) { name = 'overview'; }
    state.tab = name;
    Array.prototype.forEach.call(document.querySelectorAll('.tab'), function (b) {
      b.setAttribute('aria-selected', b.getAttribute('data-tab') === name ? 'true' : 'false');
    });
    Array.prototype.forEach.call(document.querySelectorAll('.panel'), function (p) {
      p.hidden = p.id !== 'tab-' + name;
    });
    if (history.replaceState) { history.replaceState(null, '', '#' + name); }
    if (name === 'solar' && !state.solar) { loadSolarDefaults(); }
    if (name === 'whatif' && !state.whatif) { runWhatIf(); }
    if (name === 'leaderboard') { renderLeaderboard(); }
    if (name === 'report') { renderReport(); }
    renderVisible();
  }

  // ------------------------------------------------------------------ KPI tiles
  function kpi(label, value, unit, note, cls) {
    return '<div class="kpi ' + (cls || '') + '"><div class="label"><i></i>' + esc(label) + '</div>' +
      '<div class="value">' + value + (unit ? '<small>' + esc(unit) + '</small>' : '') + '</div>' +
      '<div class="note">' + note + '</div></div>';
  }
  function renderKpis() {
    var o = state.overview;
    if (!o) { return; }
    $('#kpis').innerHTML = [
      kpi('Energy · last 30 days', compact(o.last30.kwh), 'kWh', '<b>' + inr(o.last30.cost_inr) + '</b> at ₹' + o.assumptions.tariff_inr_per_kwh + '/kWh'),
      kpi('Carbon · last 30 days', num(o.last30.co2_kg / 1000, 1), 't CO₂', '≈ <b>' + num(o.last30.trees_to_offset_per_year) + '</b> trees/yr to offset'),
      kpi('Waste detected · 8 weeks', num(o.waste.kwh), 'kWh', '<b>' + o.waste.events + ' events</b> · ' + inr(o.waste.cost_inr) + ' · ' + num(o.waste.co2_kg) + ' kg CO₂', 'alert'),
      kpi('Forecast · next 7 days', compact(o.forecast_next_week.kwh), 'kWh', '<b>' + inr(o.forecast_next_week.cost_inr) + '</b> · ' + num(o.forecast_next_week.co2_kg / 1000, 1) + ' t CO₂'),
      kpi('Forecast accuracy', num(o.forecast_mape_avg, 1) + '%', 'MAPE', 'hold-out week, avg of 6 buildings'),
      kpi('Rooftop solar potential', num(o.solar_all_roofs.kwp), 'kWp', 'payback <b>' + num(o.solar_all_roofs.payback_years, 1) + ' yr</b> · ' + num(o.solar_all_roofs.co2_avoided_t_per_year) + ' t CO₂/yr', 'good')
    ].join('');
  }

  // ------------------------------------------------------------------ building chips
  function renderChips() {
    var box = $('#building-chips');
    box.innerHTML = '';
    state.buildings.forEach(function (b) {
      var c = html('button', { type: 'button', 'class': 'chip', 'data-building': b.id,
        'aria-pressed': b.id === state.building ? 'true' : 'false', title: b.type + ' · ' + b.waste_events + ' waste events' });
      c.textContent = b.name.replace(' Block', '');
      if (b.waste_events) { c.appendChild(html('span', { 'class': 'dot', 'aria-hidden': 'true' })); }
      c.addEventListener('click', function () { selectBuilding(b.id); });
      box.appendChild(c);
    });
  }
  function selectBuilding(id) {
    state.building = id;
    Array.prototype.forEach.call(document.querySelectorAll('#building-chips .chip'), function (c) {
      c.setAttribute('aria-pressed', c.getAttribute('data-building') === id ? 'true' : 'false');
    });
    return Promise.all([
      api('/api/series?building=' + id + '&days=14'),
      api('/api/heatmap?building=' + id)
    ]).then(function (r) {
      state.series = r[0];
      state.heat = r[1];
      renderLine();
      renderWhy();
      renderHeatmap();
      renderTimeline();
    }).catch(function (e) { toast('Could not load building: ' + e.message); });
  }

  // ------------------------------------------------------------------ line chart
  function renderLine() {
    var s = state.series, box = $('#line-chart');
    if (!s || !box.clientWidth) { return; }
    $('#chart-title').textContent = s.name + ' · actual vs forecast';
    box.innerHTML = '';
    var W = box.clientWidth, H = 300, m = { l: 40, r: 64, t: 12, b: 26 };
    var actT = s.actual.timestamps.map(parseTs), btT = s.backtest.timestamps.map(parseTs), fcT = s.forecast.timestamps.map(parseTs);
    var t0 = actT[0].getTime(), t1 = fcT[fcT.length - 1].getTime() + 3600e3;
    var maxV = Math.max(Math.max.apply(null, s.actual.kwh), Math.max.apply(null, s.forecast.kwh), Math.max.apply(null, s.backtest.kwh));
    var yMax = niceMax(maxV * 1.08);
    var x = function (t) { return m.l + (t - t0) / (t1 - t0) * (W - m.l - m.r); };
    var y = function (v) { return m.t + (1 - v / yMax) * (H - m.t - m.b); };
    var root = svg('svg', { viewBox: '0 0 ' + W + ' ' + H, width: W, height: H, role: 'img', 'aria-label': s.name + ' hourly kWh' }, box);

    // grid + y ticks
    for (var i = 0; i <= 4; i++) {
      var v = yMax * i / 4, yy = y(v);
      svg('line', { x1: m.l, x2: W - m.r, y1: yy, y2: yy, 'class': i === 0 ? 'baseline' : 'gridline' }, root);
      var tx = svg('text', { x: m.l - 8, y: yy + 4, 'text-anchor': 'end', 'class': 'tick' }, root);
      tx.textContent = num(v);
      tx.setAttribute('style', 'fill:var(--muted);font-size:11px');
    }
    // x ticks: every N days at midnight
    var days = Math.round((t1 - t0) / 86400e3);
    var step = Math.max(1, Math.ceil(days / Math.max(3, Math.floor((W - m.l - m.r) / 70))));
    for (var d = 0; d <= days; d += step) {
      var dt = new Date(actT[0].getTime() + d * 86400e3), xx = x(dt.getTime());
      if (xx > W - m.r) { break; }
      svg('line', { x1: xx, x2: xx, y1: H - m.b, y2: H - m.b + 4, 'class': 'baseline' }, root);
      var lt = svg('text', { x: xx, y: H - 8, 'text-anchor': 'middle', style: 'fill:var(--muted);font-size:11px' }, root);
      lt.textContent = DAYS[dt.getDay()] + ' ' + dt.getDate();
    }
    // waste bands
    s.events.forEach(function (e) {
      var a = Math.max(t0, parseTs(e.start).getTime()), b = parseTs(e.end).getTime() + 3600e3;
      svg('rect', { x: x(a), y: m.t, width: Math.max(2, x(b) - x(a)), height: H - m.t - m.b, 'class': 'band' }, root);
      svg('line', { x1: x(a), x2: x(a), y1: m.t, y2: H - m.b, 'class': 'band-edge' }, root);
    });
    // "now" divider
    var nowT = fcT[0].getTime();
    svg('line', { x1: x(nowT), x2: x(nowT), y1: m.t, y2: H - m.b, 'class': 'now-line' }, root);
    var nl = svg('text', { x: x(nowT) + 5, y: m.t + 10, style: 'fill:var(--text-2);font-size:11px;font-weight:600' }, root);
    nl.textContent = 'Forecast →';
    if (W >= 600) {
      var hl = svg('text', { x: x(btT[0].getTime()) + 5, y: m.t + 10, style: 'fill:var(--muted);font-size:11px' }, root);
      hl.textContent = 'Hold-out week (back-test)';
    }

    function path(ts, vals) {
      return vals.map(function (v, k) { return (k ? 'L' : 'M') + x(ts[k].getTime()).toFixed(1) + ' ' + y(v).toFixed(1); }).join('');
    }
    var fT = btT.concat(fcT), fV = s.backtest.kwh.concat(s.forecast.kwh);
    svg('path', { d: path(actT, s.actual.kwh), fill: 'none', style: 'stroke:var(--s1)', 'stroke-width': 2, 'stroke-linejoin': 'round' }, root);
    svg('path', { d: path(fT, fV), fill: 'none', style: 'stroke:var(--s2)', 'stroke-width': 2, 'stroke-dasharray': '5 3', 'stroke-linejoin': 'round' }, root);
    // direct labels at line ends
    var la = svg('text', { x: x(actT[actT.length - 1].getTime()) - 4, y: m.t + 26, 'text-anchor': 'end', style: 'fill:var(--text-2);font-size:11px;font-weight:600' }, root);
    la.textContent = 'Actual';
    var lf = svg('text', { x: W - m.r + 6, y: y(fV[fV.length - 1]) + 4, style: 'fill:var(--text-2);font-size:11px;font-weight:600' }, root);
    lf.textContent = 'Forecast';

    // hover layer
    var hover = svg('g', { style: 'display:none' }, root);
    var hLine = svg('line', { y1: m.t, y2: H - m.b, 'class': 'hover-line' }, hover);
    var dotA = svg('circle', { r: 4.5, style: 'fill:var(--s1);stroke:var(--surface)', 'stroke-width': 2 }, hover);
    var dotF = svg('circle', { r: 4.5, style: 'fill:var(--s2);stroke:var(--surface)', 'stroke-width': 2 }, hover);
    var hit = svg('rect', { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: 'transparent' }, root);
    var actIdx = {}, fIdx = {};
    actT.forEach(function (t, k) { actIdx[t.getTime()] = k; });
    fT.forEach(function (t, k) { fIdx[t.getTime()] = k; });
    hit.addEventListener('mousemove', function (evt) {
      var r = root.getBoundingClientRect();
      var px = (evt.clientX - r.left) * (W / r.width);
      var t = t0 + (px - m.l) / (W - m.l - m.r) * (t1 - t0);
      t = Math.round(t / 3600e3) * 3600e3;
      var d = new Date(t), ai = actIdx[t], fi = fIdx[t];
      if (ai === undefined && fi === undefined) { return; }
      hover.style.display = '';
      hLine.setAttribute('x1', x(t)); hLine.setAttribute('x2', x(t));
      var out = '<div class="t-h">' + fmtTs(d) + '</div>';
      if (ai !== undefined) {
        dotA.style.display = ''; dotA.setAttribute('cx', x(t)); dotA.setAttribute('cy', y(s.actual.kwh[ai]));
        out += tipRow('var(--s1)', 'Actual', num(s.actual.kwh[ai], 1) + ' kWh');
      } else { dotA.style.display = 'none'; }
      if (fi !== undefined) {
        dotF.style.display = ''; dotF.setAttribute('cx', x(t)); dotF.setAttribute('cy', y(fV[fi]));
        out += tipRow('var(--s2)', fi < btT.length ? 'Back-test forecast' : 'Forecast', num(fV[fi], 1) + ' kWh', true);
      } else { dotF.style.display = 'none'; }
      var temp = ai !== undefined ? s.actual.temp_c[ai] : (fi >= btT.length ? s.forecast.temp_c[fi - btT.length] : null);
      if (temp !== null && temp !== undefined) { out += tipRow(null, 'Temperature', num(temp, 1) + ' °C'); }
      s.events.forEach(function (e) {
        if (t >= parseTs(e.start).getTime() && t <= parseTs(e.end).getTime()) {
          out += '<div class="t-p"><b>Waste event:</b> ' + esc(e.reason) + '</div>';
        }
      });
      showTip(evt, out);
    });
    hit.addEventListener('mouseleave', function () { hover.style.display = 'none'; hideTip(); });
  }

  // ------------------------------------------------------------------ why panel
  function renderWhy() {
    var s = state.series;
    if (!s) { return; }
    var f = s.forecast, p = f.peak, w = p.why, sens = f.weather_sensitivity_kwh_per_degc;
    var peakT = parseTs(p.timestamp);
    $('#why-body').innerHTML =
      '<div><div class="muted">Next 7 days · ' + esc(s.name) + '</div>' +
      '<div class="why-big">' + num(f.total_kwh) + ' kWh</div>' +
      '<div class="muted">' + inr(f.cost_inr) + ' · ' + num(f.co2_kg) + ' kg CO₂</div></div>' +
      '<div class="why-eq">Peak <b>' + num(p.kwh, 1) + ' kWh</b> on <b>' + fmtTs(peakT) + '</b> = calendar baseline <b>' +
      num(w.calendar_baseline_kwh, 1) + '</b> (' + esc(w.daytype) + ', ' + hourLabel(w.hour) + ') + weather <b>' +
      num(w.weather_effect_kwh, 1) + '</b> (' + num(w.temperature_c, 1) + ' °C → ' + num(w.cooling_degrees, 1) + ' cooling degrees)</div>' +
      '<div class="why-row"><span>Extra kWh per °C, weekday daytime</span><b>' + num(sens.workday_daytime, 2) + '</b></div>' +
      '<div class="why-row"><span>Back-test MAPE, hold-out week</span><b>' + num(s.backtest.mape.regression, 1) + '%</b></div>' +
      '<div class="why-row"><span>…excluding waste-event hours</span><b>' + num(s.backtest.mape_excluding_waste_hours, 1) + '%</b></div>' +
      '<p class="muted" style="font-size:12px" title="' + esc(f.model) + '">Regression on day-type × hour + temperature, built from scratch. Waste hours are trimmed from training so they never become "normal".</p>';
  }

  // ------------------------------------------------------------------ timeline
  function renderTimeline() {
    var box = $('#timeline-chart'), o = state.overview, a = state.anomalies;
    if (!o || !a || !box.clientWidth) { return; }
    box.innerHTML = '';
    var W = box.clientWidth, rowH = 26, lab = Math.min(118, W * 0.28), m = { t: 4, b: 22, r: 8 };
    var H = m.t + rowH * state.buildings.length + m.b;
    var nH = o.period.hours, t0 = parseTs(o.period.start).getTime();
    var x = function (i) { return lab + i / nH * (W - lab - m.r); };
    var root = svg('svg', { viewBox: '0 0 ' + W + ' ' + H, width: W, height: H, role: 'img', 'aria-label': 'Waste events timeline' }, box);
    state.buildings.forEach(function (b, r) {
      var yy = m.t + r * rowH;
      if (b.id === state.building) {
        svg('rect', { x: 0, y: yy, width: W, height: rowH, rx: 6, style: 'fill:var(--brand-wash)' }, root);
      }
      svg('line', { x1: lab, x2: W - m.r, y1: yy + rowH / 2, y2: yy + rowH / 2, 'class': 'gridline' }, root);
      var t = svg('text', { x: 6, y: yy + rowH / 2 + 4, style: 'fill:var(--text-2);font-size:11.5px;font-weight:' + (b.id === state.building ? 700 : 500) + ';cursor:pointer' }, root);
      t.textContent = b.name;
      t.addEventListener('click', function () { selectBuilding(b.id); });
    });
    // week ticks
    for (var wk = 0; wk <= nH / 168; wk++) {
      var xx = x(wk * 168);
      svg('line', { x1: xx, x2: xx, y1: m.t, y2: H - m.b, 'class': 'gridline' }, root);
      if (wk < nH / 168) {
        var tl = svg('text', { x: xx + 2, y: H - 6, style: 'fill:var(--muted);font-size:11px' }, root);
        tl.textContent = fmtDay(new Date(t0 + wk * 7 * 86400e3));
      }
    }
    var rowOf = {};
    state.buildings.forEach(function (b, r) { rowOf[b.id] = r; });
    a.events.forEach(function (e) {
      var r = rowOf[e.building], yy = m.t + r * rowH;
      var x1 = x(e.start_index), x2 = x(e.end_index + 1);
      var g = svg('g', { style: 'cursor:pointer' }, root);
      svg('rect', { x: x1 - 4, y: yy, width: Math.max(10, x2 - x1 + 8), height: rowH, fill: 'transparent' }, g);
      svg('rect', { x: x1, y: yy + 6, width: Math.max(5, x2 - x1), height: rowH - 12, rx: 3, style: 'fill:var(--critical);stroke:var(--surface)', 'stroke-width': 1 }, g);
      g.addEventListener('mousemove', function (evt) {
        showTip(evt, '<div class="t-h">' + esc(e.building_name) + ' · ' + fmtTs(parseTs(e.start)) + '</div>' +
          tipRow(null, 'Duration', e.hours + ' h') + tipRow(null, 'Wasted', num(e.wasted_kwh, 1) + ' kWh') +
          tipRow(null, 'Cost', inr(e.cost_inr)) + tipRow(null, 'CO₂', num(e.co2_kg, 1) + ' kg') +
          '<div class="t-p">' + esc(e.reason) + '</div>');
      });
      g.addEventListener('mouseleave', hideTip);
      g.addEventListener('click', function () { selectBuilding(e.building); });
    });
  }
  function renderAlerts() {
    var a = state.anomalies;
    if (!a) { return; }
    var ul = $('#alerts');
    ul.innerHTML = '';
    a.events.slice(0, 4).forEach(function (e) {
      var li = html('li', { title: e.rule_fired });
      li.innerHTML = '<span class="ico" aria-label="alert">!</span><span class="reason"><b>' + esc(e.building_name) + '</b> · ' +
        esc(e.reason.replace(e.building_name + ' ', '')) + '</span><span class="cost">' + inr(e.cost_inr) + '<small>' + num(e.wasted_kwh) + ' kWh</small></span>';
      li.addEventListener('click', function () { selectBuilding(e.building); });
      ul.appendChild(li);
    });
  }

  // ------------------------------------------------------------------ heatmap
  function renderHeatmap() {
    var hm = state.heat, box = $('#heatmap');
    if (!hm || !box.clientWidth) { return; }
    $('#heat-title').textContent = hm.name + ' · load heatmap';
    box.innerHTML = '';
    var W = box.clientWidth, m = { l: 40, t: 4, b: 22, r: 4 }, cellH = 8;
    var nD = hm.days.length, cw = (W - m.l - m.r) / nD, H = m.t + 24 * cellH + m.b;
    var lo = hexToRgb(cssVar('--heat-lo') || '#eef7f1'), hi = hexToRgb(cssVar('--heat-hi') || '#0a5a2c');
    var root = svg('svg', { viewBox: '0 0 ' + W + ' ' + H, width: W, height: H, role: 'img', 'aria-label': 'Heatmap of hourly load' }, box);
    var flags = [];
    hm.days.forEach(function (d, i) {
      for (var h = 0; h < 24; h++) {
        var v = d.kwh[h] / hm.max;
        svg('rect', { x: m.l + i * cw, y: m.t + h * cellH, width: Math.max(1, cw - 1), height: cellH - 1, fill: mix(lo, hi, Math.sqrt(v)) }, root);
        if (d.flags[h]) { flags.push([i, h]); }
      }
      if (i % 7 === 0) {
        var t = svg('text', { x: m.l + i * cw, y: H - 6, style: 'fill:var(--muted);font-size:11px' }, root);
        t.textContent = fmtDay(parseTs(d.date + 'T00:00:00'));
      }
    });
    flags.forEach(function (f) {
      svg('rect', { x: m.l + f[0] * cw + 0.5, y: m.t + f[1] * cellH + 0.5, width: Math.max(1, cw - 2), height: cellH - 2, fill: 'none', style: 'stroke:var(--critical)', 'stroke-width': 1.5 }, root);
    });
    [0, 6, 12, 18].forEach(function (h) {
      var t = svg('text', { x: m.l - 6, y: m.t + h * cellH + cellH, 'text-anchor': 'end', style: 'fill:var(--muted);font-size:11px' }, root);
      t.textContent = hourLabel(h);
    });
    var sel = svg('rect', { width: cw, height: cellH, fill: 'none', style: 'stroke:var(--text);display:none', 'stroke-width': 1.5 }, root);
    root.addEventListener('mousemove', function (evt) {
      var r = root.getBoundingClientRect();
      var px = (evt.clientX - r.left) * (W / r.width), py = (evt.clientY - r.top) * (H / r.height);
      var i = Math.floor((px - m.l) / cw), h = Math.floor((py - m.t) / cellH);
      if (i < 0 || i >= nD || h < 0 || h > 23) { sel.style.display = 'none'; hideTip(); return; }
      var d = hm.days[i];
      sel.setAttribute('x', m.l + i * cw); sel.setAttribute('y', m.t + h * cellH); sel.style.display = '';
      showTip(evt, '<div class="t-h">' + d.weekday + ' ' + fmtDay(parseTs(d.date + 'T00:00:00')) + ', ' + hourLabel(h) + '</div>' +
        tipRow(null, 'Load', num(d.kwh[h], 1) + ' kWh') + (d.holiday ? tipRow(null, 'Holiday', d.holiday) : '') +
        (d.flags[h] ? '<div class="t-p"><b style="color:var(--critical)">Flagged as waste</b></div>' : ''));
    });
    root.addEventListener('mouseleave', function () { sel.style.display = 'none'; hideTip(); });
  }

  // ------------------------------------------------------------------ solar
  function solarForm() { return $('#solar-form'); }
  function loadSolarDefaults() {
    var sel = $('#solar-building');
    if (!sel.options.length) {
      sel.appendChild(html('option', { value: 'campus' }, 'Whole campus (all roofs)'));
      state.buildings.forEach(function (b) { sel.appendChild(html('option', { value: b.id }, b.name)); });
      sel.appendChild(html('option', { value: '' }, 'Custom (type your own)'));
      sel.value = 'library';
      sel.addEventListener('change', function () { if (sel.value) { prefillSolar(sel.value); } });
    }
    prefillSolar(sel.value || 'library');
  }
  function prefillSolar(bid) {
    var f = solarForm();
    return post('/api/solar', { building: bid }).then(function (r) {
      f.roof_area_m2.value = Math.round(r.inputs.roof_area_m2);
      f.monthly_kwh.value = Math.round(r.inputs.monthly_kwh);
      f.monthly_bill_inr.value = '';
      showSolar(r);
    }).catch(function (e) { $('#solar-error').textContent = e.message; });
  }
  function submitSolar(evt) {
    if (evt) { evt.preventDefault(); }
    var f = solarForm(), body = {};
    ['roof_area_m2', 'monthly_kwh', 'monthly_bill_inr', 'tariff', 'cost_per_kwp'].forEach(function (k) {
      if (f[k].value !== '') { body[k] = Number(f[k].value); }
    });
    $('#solar-error').textContent = '';
    post('/api/solar', body).then(showSolar).catch(function (e) { $('#solar-error').textContent = e.message; });
  }
  function showSolar(r) {
    state.solar = r;
    $('#solar-error').textContent = '';
    $('#solar-kpis').innerHTML = [
      kpi('System size', num(r.kwp, 1), 'kWp', 'limited by <b>' + esc(r.limited_by) + '</b>'),
      kpi('Generation · year 1', compact(r.annual_generation_kwh), 'kWh', '<b>' + num(r.coverage_pct, 1) + '%</b> of consumption'),
      kpi('Simple payback', num(r.simple_payback_years, 1), 'years', 'capex <b>' + inr(r.capex_inr) + '</b> · saves ' + inr(r.annual_saving_inr) + '/yr', 'good'),
      kpi('CO₂ avoided', num(r.co2_avoided_t_per_year, 1), 't/yr', '<b>' + num(r.co2_avoided_t_lifetime) + ' t</b> over ' + r.lifetime_years + ' yrs ≈ ' + num(r.trees_equivalent) + ' trees')
    ].join('');
    $('#solar-sub').textContent = 'Net ' + inr(r.lifetime_net_saving_inr) + ' over ' + r.lifetime_years + ' years after capex and O&M. Hover a bar for that year.';
    $('#solar-explain').innerHTML = r.explain.map(function (s) { return '<li>' + esc(s) + '</li>'; }).join('');
    var a = r.assumptions;
    $('#solar-assume').textContent = 'Assumptions: ' + [a.yield, a.area, a.cost, a.degradation + ' degradation', a.om + ' O&M', a.emission_factor].join(' · ');
    renderSolarChart();
  }
  function renderSolarChart() {
    var r = state.solar, box = $('#solar-chart');
    if (!r || !box.clientWidth) { return; }
    box.innerHTML = '';
    var W = box.clientWidth, H = 230, m = { l: 58, r: 10, t: 12, b: 26 };
    var vals = [{ year: 0, cumulative_inr: -r.capex_inr }].concat(r.cashflow);
    var maxV = Math.max.apply(null, vals.map(function (v) { return v.cumulative_inr; }));
    var minV = Math.min.apply(null, vals.map(function (v) { return v.cumulative_inr; }));
    var top = niceMax(Math.max(maxV, 1)), bot = -niceMax(Math.max(-minV, 1));
    var y = function (v) { return m.t + (top - v) / (top - bot) * (H - m.t - m.b); };
    var bw = (W - m.l - m.r) / vals.length;
    var root = svg('svg', { viewBox: '0 0 ' + W + ' ' + H, width: W, height: H, role: 'img', 'aria-label': 'Cumulative solar cash flow' }, box);
    [bot, bot / 2, 0, top / 2, top].forEach(function (v) {
      svg('line', { x1: m.l, x2: W - m.r, y1: y(v), y2: y(v), 'class': v === 0 ? 'baseline' : 'gridline' }, root);
      var t = svg('text', { x: m.l - 6, y: y(v) + 4, 'text-anchor': 'end', style: 'fill:var(--muted);font-size:11px' }, root);
      t.textContent = inr(v).replace('.00', '');
    });
    vals.forEach(function (v, i) {
      var x0 = m.l + i * bw + 1, h = Math.abs(y(v.cumulative_inr) - y(0));
      var g = svg('g', {}, root);
      svg('rect', { x: m.l + i * bw, y: m.t, width: bw, height: H - m.t - m.b, fill: 'transparent' }, g);
      svg('rect', { x: x0, y: v.cumulative_inr >= 0 ? y(v.cumulative_inr) : y(0), width: Math.max(2, bw - 2), height: Math.max(1, h), rx: 2,
        style: 'fill:' + (v.cumulative_inr >= 0 ? 'var(--brand)' : 'var(--critical)') }, g);
      if (i % 5 === 0) {
        var t = svg('text', { x: x0 + bw / 2, y: H - 8, 'text-anchor': 'middle', style: 'fill:var(--muted);font-size:11px' }, root);
        t.textContent = 'Yr ' + v.year;
      }
      g.addEventListener('mousemove', function (evt) {
        showTip(evt, '<div class="t-h">Year ' + v.year + '</div>' + tipRow(null, 'Cumulative', inr(v.cumulative_inr)) +
          (v.generation_kwh ? tipRow(null, 'Generation', num(v.generation_kwh) + ' kWh') + tipRow(null, 'Saving', inr(v.saving_inr)) : tipRow(null, 'Investment', inr(r.capex_inr))));
      });
      g.addEventListener('mouseleave', hideTip);
    });
    if (r.payback_year_with_degradation) {
      var px = m.l + (r.payback_year_with_degradation + 0.5) * bw;
      svg('line', { x1: px, x2: px, y1: m.t, y2: H - m.b, 'class': 'now-line', 'stroke-dasharray': '4 3' }, root);
      var pl = svg('text', { x: px + 5, y: m.t + 10, style: 'fill:var(--text-2);font-size:11px;font-weight:600' }, root);
      pl.textContent = 'Payback ≈ ' + num(r.payback_year_with_degradation, 1) + ' yr';
    }
  }

  // ------------------------------------------------------------------ what-if
  var whatifTimer = null;
  function whatifBody() {
    var f = $('#whatif-form');
    return {
      ac_setpoint_delta: Number(f.ac_setpoint_delta.value), auto_off: f.auto_off.checked,
      auto_off_hour: Number(f.auto_off_hour.value), led_pct: Number(f.led_pct.value), bldc_pct: Number(f.bldc_pct.value)
    };
  }
  function runWhatIf() {
    var b = whatifBody();
    $('#v-ac').textContent = '+' + b.ac_setpoint_delta + ' °C';
    $('#v-led').textContent = b.led_pct + '%';
    $('#v-bldc').textContent = b.bldc_pct + '%';
    clearTimeout(whatifTimer);
    whatifTimer = setTimeout(function () {
      post('/api/whatif', b).then(function (r) { state.whatif = r; renderWhatIf(); })
        .catch(function (e) { toast('What-if failed: ' + e.message); });
    }, 120);
  }
  function renderWhatIf() {
    var r = state.whatif;
    if (!r) { return; }
    $('#whatif-kpis').innerHTML = [
      kpi('Monthly saving', compact(r.monthly_saving_kwh), 'kWh', '<b>' + num(r.saving_pct, 1) + '%</b> of ' + compact(r.monthly_baseline_kwh) + ' kWh', 'good'),
      kpi('Money saved', inr(r.monthly_saving_inr), '/month', '<b>' + inr(r.annual_saving_inr) + '</b> per year'),
      kpi('CO₂ avoided', num(r.monthly_co2_saved_kg / 1000, 1), 't/month', '≈ <b>' + num(r.trees_equivalent) + '</b> trees\' yearly absorption'),
      kpi('Biggest lever', LEVERS.reduce(function (a, l) { return r.by_lever_kwh[l.key] > r.by_lever_kwh[a.key] ? l : a; }, LEVERS[0]).label, '', 'by monthly kWh saved')
    ].join('');
    $('#whatif-explain').innerHTML = r.explain.map(function (s) { return '<li>' + esc(s) + '</li>'; }).join('');
    $('#whatif-legend').innerHTML = LEVERS.map(function (l) {
      return '<span><i class="sw sw-box" style="background:' + l.color + '"></i>' + l.label + ' · ' + num(r.by_lever_kwh[l.key]) + ' kWh</span>';
    }).join('');
    var box = $('#whatif-chart');
    if (!box.clientWidth) { return; }
    box.innerHTML = '';
    var rows = r.buildings.slice().sort(function (a, b) { return b.saving_kwh.total - a.saving_kwh.total; });
    var W = box.clientWidth, rowH = 34, lab = Math.min(130, W * 0.3), valW = 92, m = { t: 4, b: 4 };
    var H = m.t + rows.length * rowH + m.b;
    var maxV = Math.max(1, Math.max.apply(null, rows.map(function (b) { return b.saving_kwh.total; })));
    var sc = (W - lab - valW) / niceMax(maxV);
    var root = svg('svg', { viewBox: '0 0 ' + W + ' ' + H, width: W, height: H, role: 'img', 'aria-label': 'Savings by building' }, box);
    rows.forEach(function (b, i) {
      var yy = m.t + i * rowH;
      var t = svg('text', { x: 0, y: yy + rowH / 2 + 4, style: 'fill:var(--text-2);font-size:12px' }, root);
      t.textContent = b.name;
      svg('line', { x1: lab, x2: lab, y1: yy + 6, y2: yy + rowH - 6, 'class': 'baseline' }, root);
      var x0 = lab;
      LEVERS.forEach(function (l) {
        var v = b.saving_kwh[l.key];
        if (v <= 0) { return; }
        var w = v * sc;
        var seg = svg('rect', { x: x0, y: yy + 8, width: Math.max(1, w - 2), height: rowH - 16, rx: 3, style: 'fill:' + l.color }, root);
        seg.addEventListener('mousemove', function (evt) {
          showTip(evt, '<div class="t-h">' + esc(b.name) + ' · ' + l.label + '</div>' + tipRow(null, 'Saving', num(v) + ' kWh/month') +
            tipRow(null, 'Money', inr(v * state.overview.assumptions.tariff_inr_per_kwh)) + (l.key === 'auto_off' ? tipRow(null, 'Essential base kept', num(b.essential_base_kw, 1) + ' kW') : ''));
        });
        seg.addEventListener('mouseleave', hideTip);
        x0 += w;
      });
      var vt = svg('text', { x: x0 + 6, y: yy + rowH / 2 + 4, style: 'fill:var(--text);font-size:12px;font-weight:600' }, root);
      vt.textContent = num(b.saving_kwh.total) + ' kWh · ' + num(b.saving_pct, 1) + '%';
    });
  }

  // ------------------------------------------------------------------ leaderboard
  function renderLeaderboard() {
    var lb = state.board;
    if (!lb) { return; }
    $('#lb-sub').textContent = 'Ranked by weather-normalised % saving vs each building\'s own baseline · challenge period ' + lb.challenge_period;
    $('#lb-method').textContent = lb.method + ' Points: ' + lb.points_rule + '.';
    var maxAbs = Math.max.apply(null, lb.rows.map(function (r) { return Math.abs(r.saving_pct); })) || 1;
    var box = $('#leaderboard');
    box.innerHTML = '';
    lb.rows.forEach(function (r) {
      var champ = r.badges.indexOf('Green Champion') >= 0;
      var row = html('div', { 'class': 'lb-row' + (champ ? ' champ' : '') });
      var w = Math.abs(r.saving_pct) / maxAbs * 50;
      row.innerHTML = '<div class="rank">' + (champ ? '🏆' : '#' + r.rank) + '</div>' +
        '<div class="lb-name"><b>' + esc(r.name) + '</b><span>' + esc(r.type) + (r.initiative ? ' · ' + esc(r.initiative) : '') + '</span></div>' +
        '<div class="lb-bar" title="' + num(r.saved_kwh) + ' kWh saved"><span class="zero"></span><span class="fill ' + (r.saving_pct >= 0 ? 'pos' : 'neg') + '" style="width:' + w.toFixed(1) + '%"></span></div>' +
        '<div class="lb-pct">' + (r.saving_pct > 0 ? '+' : '') + num(r.saving_pct, 1) + '%<small>' + num(r.saved_kwh) + ' kWh · ' + inr(r.saved_inr) + ' · ' + r.points + ' pts</small></div>' +
        '<div class="badges">' + r.badges.map(function (b) {
          var cls = b === 'Green Champion' ? 'gold' : b === 'Needs Attention' ? 'warn' : '';
          return '<span class="badge ' + cls + '">' + (b === 'Needs Attention' ? '▲ ' : b === 'Green Champion' ? '★ ' : '✓ ') + esc(b) + '</span>';
        }).join('') + '</div>';
      box.appendChild(row);
    });
  }

  // ------------------------------------------------------------------ report
  function renderReport() {
    var ev = state.evaluation;
    if (!ev) { return; }
    var an = ev.anomaly, fc = ev.forecast;
    $('#report-kpis').innerHTML = [
      kpi('Forecast MAPE (regression)', num(fc.average_mape.regression, 1) + '%', '', 'vs Holt-Winters <b>' + num(fc.average_mape.holt_winters, 1) + '%</b>, naive ' + num(fc.average_mape.seasonal_naive, 1) + '%', 'good'),
      kpi('Waste-event precision', num(an.event_precision * 100) + '%', '', an.events_detected + ' events flagged'),
      kpi('Waste-event recall', num(an.event_recall * 100) + '%', '', (an.events_true - an.missed.length) + ' of ' + an.events_true + ' injected events found'),
      kpi('Wasted kWh estimate', num(an.estimated_wasted_kwh), 'kWh', 'true injected <b>' + num(an.true_wasted_kwh) + '</b> kWh · full pipeline ' + ev.compute_ms + ' ms')
    ].join('');
    $('#fc-sub').textContent = 'Hold-out ' + fc.holdout + '. MAPE = mean |actual - forecast| / actual. Best per row in green.';
    var rows = '<tr><th>Building</th><th>Regression</th><th>Holt-Winters</th><th>Seasonal naive</th><th>Regr. excl. waste hrs</th></tr>';
    state.buildings.forEach(function (b) {
      var m = fc.by_building[b.id].mape, best = Math.min(m.regression, m.holt_winters, m.seasonal_naive);
      rows += '<tr><td>' + esc(b.name) + '</td>' + ['regression', 'holt_winters', 'seasonal_naive'].map(function (k) {
        return '<td class="' + (m[k] === best ? 'best' : '') + '">' + num(m[k], 1) + '%</td>';
      }).join('') + '<td>' + num(fc.by_building[b.id].mape_excluding_waste_hours, 1) + '%</td></tr>';
    });
    rows += '<tr><td><b>Average</b></td><td class="best"><b>' + num(fc.average_mape.regression, 1) + '%</b></td><td>' + num(fc.average_mape.holt_winters, 1) + '%</td><td>' + num(fc.average_mape.seasonal_naive, 1) + '%</td><td></td></tr>';
    $('#fc-table').innerHTML = rows;
    var t = '<tr><th>Preset</th><th>z &gt;</th><th>min excess</th><th>Flagged</th><th>Precision</th><th>Recall</th></tr>';
    ev.anomaly_threshold_sensitivity.forEach(function (s) {
      t += '<tr class="' + (s.preset === 'default' ? 'default' : '') + '"><td>' + esc(s.preset) + '</td><td>' + s.z + '</td><td>' + s.min_kw + ' kWh / ' + Math.round(s.min_frac * 100) + '%</td><td>' +
        s.events + '</td><td>' + num(s.precision * 100) + '%</td><td>' + num(s.recall * 100) + '%</td></tr>';
    });
    $('#an-table').innerHTML = t;
    $('#missed').innerHTML = an.missed.map(function (m) {
      return '<li><span class="ico miss" aria-label="missed">?</span><span class="reason"><b>' + esc(buildingName(m.building)) + '</b> · +' + m.extra_kw + ' kW for ' + m.hours + ' h from ' +
        fmtTs(parseTs(m.start)) + ' (' + esc(m.kind.replace(/_/g, ' ')) + ') - below the 30%-of-baseline gate</span><span class="cost">' + num(m.extra_kw * m.hours) + '<small>kWh</small></span></li>';
    }).join('') || '<li><span class="reason">None</span></li>';
  }

  // ------------------------------------------------------------------ orchestration
  function renderVisible() {
    if (state.tab === 'overview') { renderLine(); renderTimeline(); renderHeatmap(); }
    if (state.tab === 'solar') { renderSolarChart(); }
    if (state.tab === 'whatif') { renderWhatIf(); }
  }
  function loadAll() {
    return Promise.all([api('/api/overview'), api('/api/buildings'), api('/api/anomalies'), api('/api/leaderboard'), api('/api/evaluation')])
      .then(function (r) {
        state.overview = r[0];
        state.buildings = r[1].buildings;
        state.anomalies = r[2];
        state.board = r[3];
        state.evaluation = r[4];
        renderKpis();
        renderChips();
        renderAlerts();
        renderLeaderboard();
        renderReport();
        return selectBuilding(state.building);
      });
  }
  function runDemo() {
    var btn = $('#run-demo');
    btn.disabled = true;
    toast('Regenerating the deterministic demo campus and re-running every model…', 3000);
    post('/api/demo/reset').then(function () {
      state.building = 'cse_lab';
      state.solar = null;
      state.whatif = null;
      return loadAll();
    }).then(function () {
      showTab('overview');
      var e = state.anomalies.events.filter(function (x) { return x.building === 'cse_lab'; })[0];
      if (e) {
        toast('Demo ready - ' + e.reason.split(' (')[0] + '. That is ' + num(e.wasted_kwh) + ' kWh / ' + inr(e.cost_inr) + ' wasted. Next: Solar planner and What-if tabs.', 9000);
      }
    }).catch(function (err) { toast('Demo failed: ' + err.message); })
      .then(function () { btn.disabled = false; });
  }

  function init() {
    Array.prototype.forEach.call(document.querySelectorAll('.tab'), function (b) {
      b.addEventListener('click', function () { showTab(b.getAttribute('data-tab')); });
    });
    $('#run-demo').addEventListener('click', runDemo);
    solarForm().addEventListener('submit', submitSolar);
    $('#solar-demo').addEventListener('click', function () { $('#solar-building').value = 'campus'; prefillSolar('campus'); });
    var wf = $('#whatif-form');
    wf.addEventListener('input', runWhatIf);
    wf.addEventListener('change', runWhatIf);
    wf.addEventListener('submit', function (e) { e.preventDefault(); });
    var rt = null;
    window.addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(renderVisible, 150); });
    if (window.matchMedia) {
      var mq = window.matchMedia('(prefers-color-scheme: dark)');
      var onScheme = function () { renderVisible(); };
      if (mq.addEventListener) { mq.addEventListener('change', onScheme); } else if (mq.addListener) { mq.addListener(onScheme); }
    }
    loadAll().then(function () {
      var h = (location.hash || '').replace('#', '');
      showTab(h || 'overview');
    }).catch(function (e) { toast('Could not reach the WattWise server: ' + e.message, 10000); });
  }
  init();
})();
