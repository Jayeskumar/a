/* MindEase front end: vanilla JS, inline SVG charts, no external requests. */
(function () {
  "use strict";

  // ------------------------------------------------------------------ utilities
  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function parseDate(iso) { var p = iso.slice(0, 10).split("-"); return new Date(+p[0], +p[1] - 1, +p[2]); }
  function fmtDate(iso) { var d = parseDate(iso); return d.getDate() + " " + MONTHS[d.getMonth()]; }
  function dayDiff(a, b) { return Math.round((parseDate(b) - parseDate(a)) / 86400000); }
  function cssVar(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }

  var toastTimer = null;
  function toast(msg) {
    var t = $("#toast");
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.hidden = true; }, 3200);
  }

  var S = {
    student: null, q: null, resources: null, scriptOpts: null, token: null, dash: null,
    inst: "phq9", answers: {}, mood: null, sleep: 7, dashInst: "phq9", evaluation: null,
    supportReason: "general"
  };
  try { S.token = sessionStorage.getItem("mindease_token"); } catch (e) { S.token = null; }

  function api(path, opts) {
    opts = opts || {};
    var headers = { "Content-Type": "application/json" };
    if (S.token) headers["Authorization"] = "Bearer " + S.token;
    return fetch(path, {
      method: opts.method || "GET", headers: headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (data) {
        if (!r.ok) {
          var err = new Error(data.error || ("HTTP " + r.status));
          err.status = r.status; err.details = data.details;
          throw err;
        }
        return data;
      });
    });
  }
  function failed(err) {
    var msg = err && err.message ? err.message : "Something went wrong";
    if (err && err.details) msg += ": " + Object.keys(err.details).map(function (k) { return k + " " + err.details[k]; }).join("; ");
    toast(msg);
  }

  // ------------------------------------------------------------------ faces
  var MOOD_LABELS = ["Very low", "Low", "Okay", "Good", "Great"];
  function face(m, size) {
    size = size || 34;
    var curve = [-6, -3, 0, 4, 7][m - 1];
    var fill = m <= 2 ? "var(--lav-soft)" : (m === 3 ? "var(--surface-2)" : "var(--brand-soft)");
    var stroke = m <= 2 ? "var(--lav)" : (m === 3 ? "var(--muted)" : "var(--brand)");
    return '<svg width="' + size + '" height="' + size + '" viewBox="0 0 40 40" aria-hidden="true">' +
      '<circle cx="20" cy="20" r="17" fill="' + fill + '" stroke="' + stroke + '" stroke-width="2"/>' +
      '<circle cx="14" cy="16" r="2.2" fill="' + stroke + '"/><circle cx="26" cy="16" r="2.2" fill="' + stroke + '"/>' +
      '<path d="M12 ' + (26 - curve / 2) + ' Q20 ' + (26 + curve) + ' 28 ' + (26 - curve / 2) + '" stroke="' + stroke +
      '" stroke-width="2.4" fill="none" stroke-linecap="round"/></svg>';
  }

  // ------------------------------------------------------------------ navigation
  function show(view) {
    $$(".view").forEach(function (v) { v.classList.toggle("active", v.id === "view-" + view); });
    $$(".tabs button").forEach(function (b) { b.setAttribute("aria-selected", b.dataset.view === view ? "true" : "false"); });
    if (view === "counsellor") loadDashboard();
    if (view === "about") loadAbout();
    if (view === "today") renderCharts();
    try { history.replaceState(null, "", "#" + view); } catch (e) { /* ignore */ }
    window.scrollTo(0, 0);
  }
  document.addEventListener("click", function (e) {
    var tab = e.target.closest(".tabs button");
    if (tab) { show(tab.dataset.view); return; }
    var go = e.target.closest("[data-go]");
    if (go) {
      show(go.dataset.go);
      if (go.dataset.target) {
        var t = document.getElementById(go.dataset.target);
        if (t) t.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }
  });

  // ------------------------------------------------------------------ support screen
  function openSupport(content, noticed) {
    content = content || {};
    S.supportReason = content.reason || "general";
    $("#mTitle").textContent = content.headline || "You don't have to go through this alone.";
    $("#mBody").textContent = content.body || "Help is available right now, any time of day or night.";
    var n = $("#mNoticed");
    if (noticed) { n.hidden = false; n.innerHTML = noticed; } else { n.hidden = true; }
    $("#mLines").innerHTML = helplineHTML(content.helplines || (S.resources && S.resources.helplines) || []);
    $("#mPeer").hidden = !content.peer;
    $("#mConfirm").hidden = true;
    $("#mCounsellor").disabled = false;
    $("#modal").hidden = false;
    setTimeout(function () { $("#mCounsellor").focus(); }, 30);
  }
  function closeSupport() { $("#modal").hidden = true; }
  function helplineHTML(lines) {
    return lines.map(function (h) {
      var nums = h.numbers.map(function (num, i) {
        return '<a class="num" href="tel:' + esc(h.tel[i]) + '">' + esc(num) + "</a>";
      }).join("");
      return '<div class="hl-line"><div><b>' + esc(h.name) + '</b><div class="muted xsmall">' + esc(h.desc) +
        "</div></div><div>" + nums + "</div></div>";
    }).join("");
  }
  $("#mClose").addEventListener("click", closeSupport);
  $("#modal").addEventListener("click", function (e) { if (e.target.id === "modal") closeSupport(); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !$("#modal").hidden) closeSupport(); });
  $("#mCounsellor").addEventListener("click", function () {
    var reason = S.supportReason === "general" ? "general" : S.supportReason;
    api("/api/support/contact", { method: "POST", body: { reason: reason, preferred: "in person" } }).then(function (r) {
      var c = $("#mConfirm");
      c.textContent = r.message;
      c.hidden = false;
      $("#mCounsellor").disabled = true;
      refreshStudent();
    }).catch(failed);
  });
  $("#mBreathe").addEventListener("click", function () {
    closeSupport();
    show("toolkit");
    $("#tool-breathing").scrollIntoView({ behavior: "smooth", block: "center" });
    startBreathing();
  });
  $("#mPeer").addEventListener("click", function () { closeSupport(); show("talk"); $("#peerSteps").scrollIntoView({ block: "center" }); });
  $("#btnHelp").addEventListener("click", function () {
    api("/api/support?reason=general&level=urgent").then(function (c) { openSupport(c); })
      .catch(function () { openSupport({}); });
  });

  // ------------------------------------------------------------------ demo controls
  $("#btnDemo").addEventListener("click", function () {
    api("/api/demo/reset", { method: "POST" }).then(function () {
      S.answers = {}; S.mood = null;
      $("#jText").value = "";
      renderNoticed(null);
      $("#qResult").hidden = true;
      renderQuestionnaire();
      return refreshStudent();
    }).then(function () {
      toast("Demo data loaded: Ananya's 3-week journal and a 60-student cohort.");
      if (S.token) loadDashboard();
    }).catch(failed);
  });
  $("#btnErase").addEventListener("click", function () {
    if (!window.confirm("Delete your journal, check-ins and any shared scores? This cannot be undone. (Load demo data restores the demo.)")) return;
    api("/api/student/erase", { method: "POST" }).then(function () { toast("Your data has been deleted."); return refreshStudent(); }).catch(failed);
  });

  // ------------------------------------------------------------------ today
  function refreshStudent() {
    return api("/api/student").then(function (st) {
      S.student = st;
      renderToday();
      renderEntries();
      renderHistory();
      $("#qShare").checked = !!st.consent.share_aggregate;
      $("#consentShare").checked = !!st.consent.share_aggregate;
    });
  }

  function renderToday() {
    var st = S.student;
    if (!st) return;
    var hour = new Date().getHours();
    var part = hour < 12 ? "Good morning" : (hour < 17 ? "Good afternoon" : "Good evening");
    $("#greeting").textContent = part + ", " + st.name;
    var todayEntry = st.journal.length && st.journal[0].date === st.today;
    $("#heroSub").textContent = todayEntry ? "Thanks for checking in today. Small steps count." : "How are you feeling today? Tap a face to start today's entry.";
    $("#myPid").textContent = st.pid;
    $("#quickMood").innerHTML = [1, 2, 3, 4, 5].map(function (m) {
      return '<button data-mood="' + m + '" title="' + MOOD_LABELS[m - 1] + '">' + face(m, 30) + "<span>" + MOOD_LABELS[m - 1] + "</span></button>";
    }).join("");
    var series = st.trends.series || [];
    var last5 = series.slice(-5).map(function (r) { return r.sleep; }).filter(function (v) { return v != null; });
    var avgSleep = last5.length ? (last5.reduce(function (a, b) { return a + b; }, 0) / last5.length).toFixed(1) : "–";
    var lastCi = st.screenings[0];
    $("#heroMeta").innerHTML =
      "<div><b>" + series.length + "</b><span>days journaled</span></div>" +
      "<div><b>" + avgSleep + " h</b><span>avg sleep, last 5 nights</span></div>" +
      "<div><b>" + (lastCi ? fmtDate(lastCi.date) : "–") + "</b><span>last check-in</span></div>";
    renderInsights(st.trends.insights || []);
    renderCharts();
    renderCheckinSummary();
  }
  $("#quickMood").addEventListener("click", function (e) {
    var b = e.target.closest("button[data-mood]");
    if (!b) return;
    setMood(+b.dataset.mood);
    show("journal");
    $("#jText").focus();
  });

  var ICONS = {
    gentle: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--lav-strong)" stroke-width="2" stroke-linecap="round"><path d="M3 14c3-4 6-4 9 0s6 4 9 0"/><path d="M3 9c3-4 6-4 9 0s6 4 9 0" opacity=".5"/></svg>',
    notice: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--lav-strong)" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="8"/><path d="M12 8v5M12 16h.01"/></svg>',
    positive: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--brand-strong)" stroke-width="2" stroke-linecap="round"><path d="M5 19c0-8 6-13 14-14-1 8-6 14-14 14z"/><path d="M5 19l7-7"/></svg>'
  };
  var ACTIONS = {
    breathing: { label: "Start box breathing", go: "toolkit", target: "tool-breathing" },
    grounding: { label: "Try 5-4-3-2-1 grounding", go: "toolkit", target: "tool-grounding" },
    sleep: { label: "See sleep tips", go: "toolkit", target: "tool-sleep" },
    planner: { label: "Plan study blocks", go: "toolkit", target: "tool-planner" },
    toolkit: { label: "Open toolkit", go: "toolkit", target: "tool-breathing" },
    checkin: { label: "Take a 2-min check-in", go: "checkin" },
    talk: { label: "Prepare to talk", go: "talk" },
    journal: { label: "Write today's entry", go: "journal" }
  };
  function renderInsights(list) {
    $("#insights").innerHTML = list.map(function (ins) {
      var a = ACTIONS[ins.suggestion && ins.suggestion.action] || null;
      var btn = a ? '<button class="btn small" data-go="' + a.go + '"' + (a.target ? ' data-target="' + a.target + '"' : "") + ">" + esc(a.label) + "</button>" : "";
      var ev = (ins.evidence || []).length ? '<details><summary>Why?</summary><ul>' +
        ins.evidence.map(function (e) { return "<li>" + esc(e) + "</li>"; }).join("") + "</ul></details>" : "";
      var wide = ins.kind === "together";
      return '<div class="card insight ' + esc(ins.tone) + (wide ? " wide" : "") + '"><span class="ico">' + (ICONS[ins.tone] || ICONS.gentle) + "</span>" +
        '<div class="ins-body"><h4>' + esc(ins.title) + "</h4><p>" + esc(ins.message) +
        (ins.suggestion ? ' <span class="sugg">' + esc(ins.suggestion.text) + "</span>" : "") + "</p></div>" +
        '<div class="ins-foot">' + btn + ev + "</div></div>";
    }).join("") || '<div class="card muted">Nothing to show yet.</div>';
  }

  function renderCheckinSummary() {
    var st = S.student;
    var rows = ["phq9", "gad7"].map(function (inst) {
      var hist = st.screenings.filter(function (s) { return s.instrument === inst; });
      var name = inst === "phq9" ? "PHQ-9" : "GAD-7";
      if (!hist.length) return '<div class="ci-row"><span class="ci-name">' + name + '</span><span class="muted small">No check-in yet</span></div>';
      var cur = hist[0], prev = hist[1];
      var max = inst === "phq9" ? 27 : 21;
      var trend = prev ? (cur.total > prev.total ? "up from " + prev.total : (cur.total < prev.total ? "down from " + prev.total : "same as last time")) : "first check-in";
      return '<div class="ci-row"><span class="ci-name">' + name + '</span><span class="ci-score">' + cur.total + '<span class="muted small"> / ' + max + "</span></span>" +
        bandChip(cur.band, inst) + '<span class="muted small">' + fmtDate(cur.date) + " · " + trend + "</span></div>";
    }).join("");
    $("#checkinSummary").innerHTML = rows + '<p class="muted xsmall">Scores describe the last two weeks. They are screening signals, not diagnoses.</p>';
  }
  var BAND_LABEL = { minimal: "Minimal", mild: "Mild", moderate: "Moderate", moderately_severe: "Moderately severe", severe: "Severe" };
  var BAND_VAR = { phq9: { minimal: 1, mild: 2, moderate: 3, moderately_severe: 4, severe: 5 }, gad7: { minimal: 1, mild: 2, moderate: 3, severe: 5 } };
  function bandColor(band, inst) { return "var(--band-" + (BAND_VAR[inst || "phq9"][band] || 1) + ")"; }
  function inkFor(varName) {
    // pick white or dark ink from the fill's real luminance (the ramp flips in dark mode)
    var hex = cssVar(varName).replace("#", "");
    if (hex.length !== 6) return "#fff";
    var ch = [0, 2, 4].map(function (i) {
      var c = parseInt(hex.slice(i, i + 2), 16) / 255;
      return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    });
    var lum = 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
    return lum > 0.3 ? "#1B1640" : "#fff";
  }
  function bandChip(band, inst) {
    var idx = BAND_VAR[inst || "phq9"][band] || 1;
    var ink = inkFor("--band-" + idx);
    return '<span class="chip band" style="background:' + bandColor(band, inst) + ";color:" + ink + '">' + esc(BAND_LABEL[band] || band) + "</span>";
  }

  // ------------------------------------------------------------------ charts
  var tip = $("#tooltip");
  function showTip(html, evt) {
    tip.innerHTML = html;
    tip.hidden = false;
    var x = evt.clientX + 14, y = evt.clientY + 14;
    var w = tip.offsetWidth, h = tip.offsetHeight;
    if (x + w > window.innerWidth - 8) x = evt.clientX - w - 14;
    if (y + h > window.innerHeight - 8) y = evt.clientY - h - 14;
    tip.style.left = x + "px"; tip.style.top = y + "px";
  }
  function hideTip() { tip.hidden = true; }

  function seriesChart(host, opts) {
    var rows = opts.rows;
    var W = Math.max(260, host.clientWidth || 360), H = opts.height || 170;
    var m = { l: 30, r: 10, t: 10, b: 22 };
    var iw = W - m.l - m.r, ih = H - m.t - m.b;
    if (!rows.length) { host.innerHTML = '<p class="muted small">No entries yet.</p>'; return; }
    var first = rows[0].date, span = Math.max(1, dayDiff(first, rows[rows.length - 1].date));
    var pad = iw / (span + 1) / 2;
    var x = function (d) { return m.l + pad + (dayDiff(first, d) / span) * (iw - 2 * pad); };
    var y = function (v) { return m.t + ih - (v - opts.min) / (opts.max - opts.min) * ih; };
    var s1 = cssVar("--series-1"), s2 = cssVar("--series-2"), surf = cssVar("--surface");
    var out = ['<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="' + esc(opts.label) + '">'];
    // dip window shading (explainability: which days the detector flagged)
    if (opts.dip && opts.dip.length) {
      var x0 = x(opts.dip[0]) - pad, x1 = x(opts.dip[opts.dip.length - 1]) + pad;
      out.push('<rect x="' + Math.max(m.l, x0) + '" y="' + m.t + '" width="' + (Math.min(m.l + iw, x1) - Math.max(m.l, x0)) + '" height="' + ih +
        '" fill="var(--lav-soft)"/><text x="' + (Math.max(m.l, x0) + 4) + '" y="' + (m.t + 11) + '" font-size="10" fill="var(--lav-strong)" font-weight="600">' + esc(opts.dipLabel || "dip") + "</text>");
    }
    if (opts.band) {
      out.push('<rect x="' + m.l + '" y="' + y(opts.band[1]) + '" width="' + iw + '" height="' + (y(opts.band[0]) - y(opts.band[1])) +
        '" fill="var(--brand-soft)" opacity=".7"/><text x="' + (m.l + iw - 4) + '" y="' + (y(opts.band[1]) + 11) + '" text-anchor="end" font-size="10" fill="var(--muted)">' + esc(opts.bandLabel) + "</text>");
    }
    out.push('<g class="axis">');
    opts.ticks.forEach(function (t) {
      out.push('<line class="gridline" x1="' + m.l + '" x2="' + (m.l + iw) + '" y1="' + y(t) + '" y2="' + y(t) + '"/>' +
        '<text x="' + (m.l - 6) + '" y="' + (y(t) + 3.5) + '" text-anchor="end">' + esc(opts.tickFmt ? opts.tickFmt(t) : t) + "</text>");
    });
    var labelIdx = [0, Math.floor((rows.length - 1) / 2), rows.length - 1];
    labelIdx.forEach(function (i, k) {
      var anchor = k === 0 ? "start" : (k === 2 ? "end" : "middle");
      out.push('<text x="' + x(rows[i].date) + '" y="' + (H - 5) + '" text-anchor="' + anchor + '">' + fmtDate(rows[i].date) + "</text>");
    });
    out.push("</g>");
    var key = opts.key, avgKey = key + "_avg7";
    if (opts.bars) {
      var bw = Math.min(12, Math.max(3, (iw / (span + 1)) * 0.6));
      rows.forEach(function (r) {
        if (r[key] == null) return;
        var top = y(r[key]), base = y(opts.min), hgt = Math.max(1, base - top), cx = x(r.date) - bw / 2, rr = Math.min(4, bw / 2, hgt);
        out.push('<path d="M' + cx + " " + base + "V" + (top + rr) + "Q" + cx + " " + top + " " + (cx + rr) + " " + top + "H" + (cx + bw - rr) +
          "Q" + (cx + bw) + " " + top + " " + (cx + bw) + " " + (top + rr) + "V" + base + 'Z" fill="' + s1 + '"/>');
      });
    }
    if (opts.zero) out.push('<line x1="' + m.l + '" x2="' + (m.l + iw) + '" y1="' + y(0) + '" y2="' + y(0) + '" stroke="var(--muted)" stroke-width="1"/>');
    var pts = rows.filter(function (r) { return r[avgKey] != null; }).map(function (r) { return x(r.date).toFixed(1) + "," + y(r[avgKey]).toFixed(1); });
    if (pts.length > 1) out.push('<polyline points="' + pts.join(" ") + '" fill="none" stroke="' + s2 + '" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>');
    if (!opts.bars) {
      rows.forEach(function (r) {
        if (r[key] == null) return;
        out.push('<circle cx="' + x(r.date) + '" cy="' + y(r[key]) + '" r="4" fill="' + s1 + '" stroke="' + surf + '" stroke-width="2"/>');
      });
    }
    out.push('<line id="xh-' + host.id + '" x1="0" x2="0" y1="' + m.t + '" y2="' + (m.t + ih) + '" stroke="var(--muted)" stroke-width="1" opacity="0"/>');
    var slot = (iw - 2 * pad) / span;
    rows.forEach(function (r, i) {
      out.push('<rect class="hit" data-i="' + i + '" x="' + (x(r.date) - slot / 2) + '" y="' + m.t + '" width="' + slot + '" height="' + ih + '" fill="transparent"/>');
    });
    out.push("</svg>");
    host.innerHTML = out.join("");
    var xh = host.querySelector("#xh-" + host.id);
    $$(".hit", host).forEach(function (h) {
      h.addEventListener("mousemove", function (evt) {
        var r = rows[+h.dataset.i];
        xh.setAttribute("x1", x(r.date)); xh.setAttribute("x2", x(r.date)); xh.setAttribute("opacity", ".5");
        showTip("<b>" + fmtDate(r.date) + "</b><br>" + opts.tip(r), evt);
      });
      h.addEventListener("mouseleave", function () { xh.setAttribute("opacity", "0"); hideTip(); });
    });
  }
  function legend(items) {
    return items.map(function (it) { return '<span><i class="' + (it.cls || "") + '" style="background:' + it.color + '"></i>' + esc(it.label) + "</span>"; }).join("");
  }
  function renderCharts() {
    var st = S.student;
    if (!st || !$("#view-today").classList.contains("active")) return;
    var rows = st.trends.series || [];
    var det = st.trends.detectors || {};
    function dip(metric) {
      var d = det[metric];
      return d && d.dip_run && d.dip_run.length >= 2 ? d.dip_run.dates : null;
    }
    var s1 = cssVar("--series-1"), s2 = cssVar("--series-2");
    $("#lgMood").innerHTML = legend([{ label: "Daily", color: s1, cls: "dot" }, { label: "7-day average", color: s2, cls: "line" }]);
    $("#lgSleep").innerHTML = legend([{ label: "Hours", color: s1 }, { label: "7-day average", color: s2, cls: "line" }]);
    $("#lgTone").innerHTML = legend([{ label: "Entry tone", color: s1, cls: "dot" }, { label: "7-day average", color: s2, cls: "line" }]);
    seriesChart($("#chMood"), {
      rows: rows, key: "mood", min: 1, max: 5, ticks: [1, 2, 3, 4, 5], label: "Mood by day, 1 to 5",
      dip: dip("mood"), dipLabel: "lower than usual",
      tip: function (r) { return "Mood " + r.mood + "/5 (" + MOOD_LABELS[Math.round(r.mood) - 1] + ")" + (r.mood_avg7 != null ? "<br>7-day avg " + r.mood_avg7.toFixed(1) : ""); }
    });
    seriesChart($("#chSleep"), {
      rows: rows, key: "sleep", min: 0, max: 10, ticks: [0, 5, 10], bars: true, label: "Hours of sleep by night",
      band: [7, 9], bandLabel: "7–9 h advised", dip: dip("sleep"), dipLabel: "shorter",
      tickFmt: function (t) { return t + "h"; },
      tip: function (r) { return (r.sleep != null ? r.sleep + " h sleep" : "no sleep logged") + (r.sleep_avg7 != null ? "<br>7-day avg " + r.sleep_avg7.toFixed(1) + " h" : ""); }
    });
    seriesChart($("#chTone"), {
      rows: rows, key: "sentiment", min: -1, max: 1, ticks: [-1, 0, 1], zero: true, label: "Journal tone by day, -1 heavy to +1 bright",
      dip: dip("sentiment"), dipLabel: "heavier",
      tickFmt: function (t) { return t === 0 ? "0" : (t > 0 ? "+1" : "−1"); },
      tip: function (r) { return r.sentiment != null ? "Tone " + (r.sentiment > 0 ? "+" : "") + r.sentiment.toFixed(2) + (r.sentiment_avg7 != null ? "<br>7-day avg " + r.sentiment_avg7.toFixed(2) : "") : "no text"; }
    });
  }
  var resizeTimer = null;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () { renderCharts(); if (S.dash && $("#view-counsellor").classList.contains("active")) renderBands(); }, 150);
  });

  // ------------------------------------------------------------------ check-in
  function renderQuestionnaire() {
    var q = S.q && S.q[S.inst];
    if (!q) return;
    $$(".seg[role=tablist] button").forEach(function (b) { b.classList.toggle("on", b.dataset.inst === S.inst); });
    $("#qStem").textContent = q.stem;
    var ans = S.answers[S.inst] || (S.answers[S.inst] = []);
    $("#qList").innerHTML = q.items.map(function (text, i) {
      var isItem9 = S.inst === "phq9" && i === q.item9_index;
      return '<li class="' + (isItem9 ? "item9" : "") + '"><div class="qtext">' + esc(text) + "</div>" +
        '<div class="opts" role="radiogroup" aria-label="Answer for item ' + (i + 1) + '">' + q.options.map(function (o) {
          return '<button type="button" role="radio" aria-checked="' + (ans[i] === o.value) + '" class="' + (ans[i] === o.value ? "on" : "") +
            '" data-i="' + i + '" data-v="' + o.value + '">' + esc(o.label) + "</button>";
        }).join("") + "</div>" +
        (isItem9 ? '<p class="muted xsmall" style="margin:6px 0 0 32px">If you choose anything other than “Not at all”, MindEase will gently show you support options straight away.</p>' : "") +
        "</li>";
    }).join("");
    $("#qDifficulty").innerHTML = S.inst === "phq9" && q.difficulty ? '<div class="field"><span class="label small">' + esc(q.difficulty.question) +
      ' <span class="muted">(optional, not scored)</span></span><select id="qDiff"><option value="">Choose…</option>' +
      q.difficulty.options.map(function (o, i) { return '<option value="' + i + '">' + esc(o) + "</option>"; }).join("") + "</select></div>" : "";
    $("#qSource").textContent = q.name + ": " + q.source + ". Free to use; no permission required.";
    updateProgress();
  }
  function updateProgress() {
    var q = S.q[S.inst], ans = S.answers[S.inst] || [];
    var n = ans.filter(function (v) { return v !== undefined && v !== null; }).length;
    $("#qProgress").style.width = (100 * n / q.items.length) + "%";
    $("#qProgressText").textContent = n + " of " + q.items.length + " answered";
    $("#btnSubmitQ").disabled = n < q.items.length;
  }
  $$(".seg[role=tablist] button").forEach(function (b) {
    b.addEventListener("click", function () { S.inst = b.dataset.inst; $("#qResult").hidden = true; renderQuestionnaire(); });
  });
  $("#qList").addEventListener("click", function (e) {
    var b = e.target.closest("button[data-i]");
    if (!b) return;
    var i = +b.dataset.i, v = +b.dataset.v;
    S.answers[S.inst][i] = v;
    $$('button[data-i="' + i + '"]', $("#qList")).forEach(function (x) {
      var on = +x.dataset.v === v; x.classList.toggle("on", on); x.setAttribute("aria-checked", on);
    });
    updateProgress();
    if (S.inst === "phq9" && i === S.q.phq9.item9_index && v > 0) {
      // Immediate, gentle support screen - regardless of the total score.
      api("/api/support?reason=item9&level=urgent").then(function (c) {
        openSupport(c, "You answered <b>“" + esc(S.q.phq9.options[v].label) + "”</b> to question 9. Thank you for being honest. You can still finish the check-in afterwards.");
      }).catch(function () { openSupport({ reason: "item9" }); });
    }
  });
  $("#btnExampleQ").addEventListener("click", function () {
    S.answers[S.inst] = S.inst === "phq9" ? [1, 2, 2, 2, 1, 2, 2, 0, 0] : [2, 2, 2, 1, 1, 2, 1];
    renderQuestionnaire();
  });
  $("#btnSubmitQ").addEventListener("click", function () {
    var diff = $("#qDiff");
    var body = { instrument: S.inst, answers: S.answers[S.inst], share: $("#qShare").checked };
    if (diff && diff.value !== "") body.difficulty = +diff.value;
    api("/api/screening", { method: "POST", body: body }).then(function (r) {
      renderResult(r);
      refreshStudent();
      if (r.support && r.support.show) {
        openSupport(r.support, "Your check-in is saved. Because question 9 was answered above “Not at all”, we're showing support options" +
          (r.alert_created ? ", and the counselling cell has a pseudonymous alert so someone can follow up." : "."));
      }
    }).catch(failed);
  });
  function renderResult(r) {
    var q = S.q[r.instrument];
    var box = $("#qResult");
    var gauge = '<div class="gauge"><div class="gauge-bar">' + q.bands.map(function (b) {
      return '<span style="flex:' + (b.max - b.min + 1) + ";background:" + bandColor(b.band, r.instrument) + '" title="' + esc(b.label) + " " + b.min + "–" + b.max + '"></span>';
    }).join("") + '</div><div class="gauge-marker"><b style="left:calc(' + (100 * (r.total + 0.5) / (r.max + 1)) + '% - 1px)"></b></div>' +
      '<div class="gauge-labels">' + q.bands.map(function (b) { return '<span style="flex:' + (b.max - b.min + 1) + '">' + esc(b.label) + "</span>"; }).join("") + "</div></div>";
    var bars = '<div class="bars-mini">' + r.breakdown.map(function (b) {
      return '<div class="bm"><span>' + esc(b.tag) + '</span><span class="track"><i style="width:' + (100 * b.points / 3) + '%"></i></span><span class="mono">' + b.points + "</span></div>";
    }).join("") + "</div>";
    box.innerHTML = '<div class="card-head"><h4>' + esc(r.name) + ' result</h4>' + bandChip(r.band, r.instrument) + "</div>" +
      "<h3>" + r.total + '<span class="muted small"> / ' + r.max + "</span></h3>" + gauge +
      "<p>" + esc(r.message) + "</p>" +
      (r.suggest_counsellor ? '<div class="help-actions"><button class="btn primary" data-go="talk">Prepare to talk to a counsellor</button><a class="btn" href="tel:14416">Tele-MANAS 14416</a></div>' : "") +
      "<h5>Why this result</h5>" + '<ul class="explain">' + r.explain.map(function (e) { return "<li>" + esc(e) + "</li>"; }).join("") + "</ul>" + bars +
      '<div class="note-box">' + esc(r.disclaimer) + " " + (r.shared ? "Shared anonymously as " + esc(S.student ? S.student.pid : "") + "." : "Not shared: only you can see this.") + "</div>";
    box.hidden = false;
    box.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
  function renderHistory() {
    var st = S.student;
    $("#qHistory").innerHTML = st.screenings.length ? st.screenings.slice(0, 8).map(function (s) {
      return '<div class="hist-row"><span>' + fmtDate(s.date) + " · " + (s.instrument === "phq9" ? "PHQ-9" : "GAD-7") + "</span><span><b>" + s.total + "</b> " +
        bandChip(s.band, s.instrument) + ' <span class="muted xsmall">' + (s.shared ? "shared" : "private") + "</span></span></div>";
    }).join("") : '<p class="muted small">No check-ins yet.</p>';
  }
  function setConsent(val) {
    api("/api/consent", { method: "POST", body: { share_aggregate: val } }).then(function (c) {
      $("#qShare").checked = c.consent.share_aggregate; $("#consentShare").checked = c.consent.share_aggregate;
      toast(c.consent.share_aggregate ? "Check-in scores will be shared anonymously." : "Sharing is off. Your check-ins stay private.");
    }).catch(failed);
  }
  $("#consentShare").addEventListener("change", function () { setConsent(this.checked); });

  // ------------------------------------------------------------------ journal
  function setMood(m) {
    S.mood = m;
    $("#moodPick").innerHTML = [1, 2, 3, 4, 5].map(function (v) {
      return '<button type="button" role="radio" aria-checked="' + (v === m) + '" class="' + (v === m ? "on" : "") + '" data-m="' + v + '">' + face(v, 32) + "<span>" + MOOD_LABELS[v - 1] + "</span></button>";
    }).join("");
  }
  $("#moodPick").addEventListener("click", function (e) { var b = e.target.closest("button[data-m]"); if (b) setMood(+b.dataset.m); });
  $("#sleep").addEventListener("input", function () { S.sleep = +this.value; $("#sleepVal").textContent = S.sleep.toFixed(1) + " h"; });
  var analyzeTimer = null, lastText = "";
  $("#jText").addEventListener("input", function () {
    clearTimeout(analyzeTimer);
    var text = this.value;
    analyzeTimer = setTimeout(function () { analyse(text); }, 350);
  });
  function analyse(text) {
    lastText = text;
    if (!text.trim()) { renderNoticed(null); return; }
    api("/api/analyze", { method: "POST", body: { text: text } }).then(function (r) {
      if (text === lastText) renderNoticed(r, text);
    }).catch(failed);
  }
  function highlight(text, tokens, flags) {
    var cps = Array.from(text);
    var mark = new Array(cps.length), tokAt = new Array(cps.length);
    tokens.forEach(function (t, k) { for (var i = t.start; i < t.end && i < cps.length; i++) { mark[i] = t.score > 0 ? "p" : "n"; tokAt[i] = k; } });
    var flagAt = new Array(cps.length);
    (flags || []).forEach(function (f) { for (var i = f.start; i < f.end && i < cps.length; i++) flagAt[i] = true; });
    var html = "", i = 0;
    while (i < cps.length) {
      var j = i, cls = mark[i], tk = tokAt[i], fl = flagAt[i];
      while (j < cps.length && mark[j] === cls && tokAt[j] === tk && flagAt[j] === fl) j++;
      var chunk = esc(cps.slice(i, j).join(""));
      if (cls || fl) {
        var t = tk !== undefined ? tokens[tk] : null;
        var title = t ? t.text + ": " + (t.score > 0 ? "+" : "") + t.score.toFixed(2) + (t.rules.length ? " (" + t.rules.join(", ") + ")" : "") : "noticed phrase";
        html += '<mark class="' + [cls || "", fl ? "flag" : "", t && t.negated ? "neg" : ""].join(" ").trim() + '" title="' + esc(title) + '">' + chunk + "</mark>";
      } else html += chunk;
      i = j;
    }
    return html;
  }
  function renderNoticed(r, text) {
    var box = $("#noticed");
    if (!r) {
      box.innerHTML = '<h4>What the app noticed</h4><p class="muted small">Start typing to see how MindEase reads your words. It is never a diagnosis.</p>';
      return;
    }
    var sv = r.sentiment, sf = r.safety;
    var pct = 50 + 50 * sv.compound;
    var emos = sv.emotions.length ? sv.emotions.slice(0, 4).map(function (e) {
      return '<span class="chip ' + (["joy", "calm"].indexOf(e.emotion) >= 0 ? "pos" : "neg") + '">' + esc(e.label) + " · " + Math.round(100 * e.share) + "%</span>";
    }).join("") : '<span class="muted small">No strong feeling words found.</span>';
    var rows = sv.tokens.map(function (t) {
      return "<tr><td>" + esc(t.text) + '</td><td class="num">' + (t.base > 0 ? "+" : "") + t.base.toFixed(1) + '</td><td class="num">' + (t.score > 0 ? "+" : "") + t.score.toFixed(2) +
        '</td><td class="muted">' + esc(t.rules.join("; ") || "–") + "</td></tr>";
    }).join("");
    box.innerHTML = "<h4>What the app noticed</h4>" +
      '<div class="hl">' + highlight(text, sv.tokens, sf.matches) + "</div>" +
      '<div class="meter" aria-label="Tone meter"><b style="left:' + pct + '%"></b></div><div class="meter-l"><span>heavier</span><span>neutral</span><span>brighter</span></div>' +
      '<p style="margin:8px 0 2px"><b>' + esc(sv.summary) + '</b> <span class="muted small">(tone ' + (sv.compound > 0 ? "+" : "") + sv.compound.toFixed(2) + ", " + esc(sv.label) + ")</span></p>" +
      '<div class="emos">' + emos + "</div>" +
      (sv.rules_fired.length ? '<ul class="rules">' + sv.rules_fired.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul>" : "") +
      (rows ? '<details><summary class="small">Word-by-word scores</summary><table class="contrib"><tr><td class="muted">word</td><td class="num muted">lexicon</td><td class="num muted">after rules</td><td class="muted">rule</td></tr>' + rows + "</table></details>" : "") +
      (sf.flagged ? '<div class="flag-note"><b>Some words sounded heavy</b> (underlined). ' + esc(sf.message) + ' <button class="btn small" id="btnSeeSupport">See support options</button></div>' : "") +
      '<p class="muted xsmall" style="margin-top:8px">A word-list reading, computed in ' + r.compute_ms + " ms on this laptop. It can miss sarcasm and new words.</p>";
    var b = $("#btnSeeSupport");
    if (b) b.addEventListener("click", function () { openSupport(r.support); });
  }
  $("#btnExampleJ").addEventListener("click", function () {
    var d = S.student && S.student.demo_entry;
    if (!d) return;
    setMood(d.mood);
    $("#sleep").value = d.sleep; S.sleep = d.sleep; $("#sleepVal").textContent = d.sleep.toFixed(1) + " h";
    $("#jText").value = d.text;
    analyse(d.text);
  });
  $("#btnSaveJ").addEventListener("click", function () {
    if (!S.mood) { toast("Pick a mood face first (1 = very low, 5 = great)."); return; }
    var text = $("#jText").value;
    api("/api/journal", { method: "POST", body: { mood: S.mood, sleep: S.sleep, text: text } }).then(function (r) {
      toast("Saved. Thank you for checking in.");
      $("#jText").value = "";
      if (r.analysis) renderNoticed({ sentiment: r.analysis, safety: r.safety, support: r.support, compute_ms: "<1" }, text);
      refreshStudent();
      if (r.support) {
        var phrases = r.safety.matches.map(function (m) { return "“" + esc(m.phrase) + "”"; }).join(", ");
        openSupport(r.support, "MindEase noticed " + phrases + " in your entry. Your journal stays private; nothing has been shared.");
      }
    }).catch(failed);
  });
  function renderEntries() {
    var st = S.student;
    $("#jCount").textContent = st.journal.length + " entries";
    $("#entries").innerHTML = st.journal.map(function (e) {
      var lab = e.label ? '<span class="chip ' + (e.label === "positive" ? "pos" : (e.label === "negative" ? "neg" : "")) + '">' + esc(e.label) + "</span>" : "";
      return "<li>" + face(e.mood, 32) + '<div><div class="e-meta"><b>' + fmtDate(e.date) + "</b><span>mood " + e.mood + "/5</span>" +
        (e.sleep != null ? "<span>" + e.sleep + " h sleep</span>" : "") + lab + (e.flagged ? '<span class="chip neg">support shown</span>' : "") + "</div>" +
        '<div class="e-text">' + esc(e.text || "") + '</div></div><button class="del" title="Delete this entry" aria-label="Delete entry" data-del="' + esc(e.id) + '">×</button></li>';
    }).join("") || '<li class="muted">No entries yet.</li>';
  }
  $("#entries").addEventListener("click", function (e) {
    var b = e.target.closest("button[data-del]");
    if (!b) return;
    api("/api/journal/" + b.dataset.del, { method: "DELETE" }).then(function () { toast("Entry deleted."); refreshStudent(); }).catch(failed);
  });

  // ------------------------------------------------------------------ toolkit: breathing
  var breath = { timer: null, t: 0, rounds: 0 };
  var PHASES = ["Breathe in", "Hold", "Breathe out", "Hold"];
  function startBreathing() {
    if (breath.timer) return;
    var box = $("#breathBox");
    breath.t = 0; breath.rounds = 0;
    box.classList.add("running");
    $("#btnBreath").textContent = "Stop";
    tickBreath();
    breath.timer = setInterval(tickBreath, 1000);
  }
  function tickBreath() {
    var box = $("#breathBox");
    var phase = Math.floor(breath.t / 4) % 4, count = 4 - (breath.t % 4);
    box.classList.toggle("in", phase === 0 || phase === 1);
    box.classList.toggle("hold", phase === 1);
    $("#breathLabel").innerHTML = esc(PHASES[phase]) + "<small>" + count + "</small>";
    if (breath.t > 0 && breath.t % 16 === 0) { breath.rounds++; $("#breathCount").textContent = breath.rounds + (breath.rounds === 1 ? " round" : " rounds"); }
    breath.t++;
  }
  function stopBreathing() {
    clearInterval(breath.timer); breath.timer = null;
    var box = $("#breathBox");
    box.classList.remove("running", "in", "hold");
    $("#breathLabel").textContent = breath.rounds ? "Well done" : "Ready";
    $("#btnBreath").textContent = "Start";
  }
  $("#btnBreath").addEventListener("click", function () { if (breath.timer) stopBreathing(); else startBreathing(); });

  // ------------------------------------------------------------------ toolkit: grounding
  var ground = { step: 0, filled: [0, 0, 0, 0, 0] };
  function renderGrounding() {
    var steps = (S.resources && S.resources.grounding) || [];
    var done = ground.step >= steps.length;
    $("#grounding").innerHTML = steps.map(function (s, i) {
      var cls = i < ground.step ? "done" : (i === ground.step ? "on" : "");
      var dots = "";
      for (var k = 0; k < s.count; k++) dots += '<button type="button" aria-label="' + esc(s.sense) + " " + (k + 1) + '" class="' + (k < ground.filled[i] ? "on" : "") + '" data-g="' + i + '"' + (i !== ground.step ? " disabled" : "") + "></button>";
      return '<div class="g-step ' + cls + '"><span class="num">' + s.count + "</span><div><b>" + esc(s.prompt) + '</b><div class="g-dots">' + dots + "</div></div></div>";
    }).join("") + (done ? '<p class="small"><b>Well done.</b> Notice how your body feels now. <button class="btn link small" id="btnGroundReset">Start again</button></p>' : "");
    var r = $("#btnGroundReset");
    if (r) r.addEventListener("click", function () { ground = { step: 0, filled: [0, 0, 0, 0, 0] }; renderGrounding(); });
  }
  $("#grounding").addEventListener("click", function (e) {
    var b = e.target.closest("button[data-g]");
    if (!b || b.disabled) return;
    var i = +b.dataset.g, steps = S.resources.grounding;
    ground.filled[i] = Math.min(steps[i].count, ground.filled[i] + 1);
    if (ground.filled[i] >= steps[i].count) ground.step = i + 1;
    renderGrounding();
  });

  // ------------------------------------------------------------------ toolkit: planner
  var SUBJ_COLORS = ["var(--series-1)", "var(--series-2)", "#2a78d6", "#eb6834", "#eda100", "#e87ba4", "#008300", "#e34948"];
  function isoPlus(days) {
    var base = S.student ? parseDate(S.student.today) : new Date();
    base.setDate(base.getDate() + days);
    return base.getFullYear() + "-" + String(base.getMonth() + 1).padStart(2, "0") + "-" + String(base.getDate()).padStart(2, "0");
  }
  function examRow(e) {
    var conf = [1, 2, 3, 4, 5].map(function (c) {
      return '<option value="' + c + '"' + (c === (e.confidence || 3) ? " selected" : "") + ">" + c + " · " + ["not ready", "shaky", "okay", "good", "very ready"][c - 1] + "</option>";
    }).join("");
    return '<div class="exam-row"><input class="ex-subj" placeholder="Subject" maxlength="40" value="' + esc(e.subject || "") + '" aria-label="Subject">' +
      '<input class="ex-date" type="date" value="' + esc(e.date || "") + '" aria-label="Exam date"><select class="ex-conf" aria-label="How ready do you feel">' + conf + "</select>" +
      '<button type="button" class="rm" title="Remove" aria-label="Remove exam">×</button></div>';
  }
  function setExams(list) {
    $("#examRows").innerHTML = '<div class="exam-head"><span>Subject</span><span>Exam date</span><span>How ready?</span><span></span></div>' + list.map(examRow).join("");
  }
  function exampleExams() {
    return [{ subject: "Engineering Maths", date: isoPlus(4), confidence: 2 }, { subject: "Physics", date: isoPlus(6), confidence: 3 },
      { subject: "Electronics", date: isoPlus(8), confidence: 4 }, { subject: "Programming in C", date: isoPlus(10), confidence: 3 }];
  }
  $("#btnAddExam").addEventListener("click", function () {
    var rows = $$(".exam-row");
    if (rows.length >= 8) { toast("Up to 8 exams."); return; }
    $("#examRows").insertAdjacentHTML("beforeend", examRow({ date: isoPlus(7) }));
  });
  $("#examRows").addEventListener("click", function (e) { var b = e.target.closest(".rm"); if (b) b.parentElement.remove(); });
  $("#btnExamplePlan").addEventListener("click", function () { setExams(exampleExams()); makePlan(); });
  $("#btnPlan").addEventListener("click", makePlan);
  function makePlan() {
    var exams = $$(".exam-row").map(function (r) {
      return { subject: $(".ex-subj", r).value, date: $(".ex-date", r).value, confidence: +$(".ex-conf", r).value };
    }).filter(function (e) { return e.subject.trim() || e.date; });
    api("/api/planner", { method: "POST", body: { exams: exams, hours_per_day: +$("#pHours").value, start_time: $("#pStart").value || "17:30" } })
      .then(renderPlan).catch(failed);
  }
  function renderPlan(p) {
    var color = {};
    p.subjects.forEach(function (s, i) { color[s.subject] = SUBJ_COLORS[i % SUBJ_COLORS.length]; });
    var shares = '<div class="share-bars bars-mini">' + p.subjects.map(function (s) {
      return '<div class="bm"><span><i style="display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:5px;background:' + color[s.subject] + '"></i>' + esc(s.subject) +
        '</span><span class="track"><i style="width:' + (100 * s.share) + "%;background:" + color[s.subject] + '"></i></span><span class="mono" style="width:auto">' + s.hours + "h</span></div>";
    }).join("") + "</div>";
    var days = '<div class="plan-days">' + p.days.map(function (d) {
      var focus = d.blocks.filter(function (b) { return b.type === "focus"; });
      return '<div class="plan-day' + (d.exam_today.length ? " exam" : "") + '"><h5>' + esc(d.weekday) + " " + fmtDate(d.date) + (d.exam_today.length ? ' <span class="pill">' + esc(d.exam_today.join(", ")) + " exam</span>" : "") + "</h5>" +
        focus.map(function (b) { return '<div class="blk" title="' + esc(b.why || "") + '"><span><i class="sw" style="background:' + color[b.subject] + '"></i>' + esc(b.subject) + '</span><span class="muted">' + b.start + "</span></div>"; }).join("") +
        '<div class="muted">' + Math.round(d.focus_min / 60 * 10) / 10 + " h focus</div>" + (d.note ? '<div class="note">' + esc(d.note) + "</div>" : "") + "</div>";
    }).join("") + "</div>";
    $("#planOut").innerHTML = (p.warnings.length ? '<div class="note-box">' + p.warnings.map(esc).join("<br>") + "</div>" : "") + "<h5>Time per subject</h5>" + shares + days +
      '<details><summary class="small">How the plan was made</summary><ul class="explain">' + p.explain.map(function (e) { return "<li>" + esc(e) + "</li>"; }).join("") + "</ul></details>";
  }
  // Pomodoro timer
  var pomo = { timer: null, left: 25 * 60, total: 25 * 60, phase: "focus", count: 0 };
  function drawPomo() {
    var mm = Math.floor(pomo.left / 60), ss = pomo.left % 60;
    $("#pomoTime").textContent = String(mm).padStart(2, "0") + ":" + String(ss).padStart(2, "0");
    $("#pomoPhase").textContent = (pomo.phase === "focus" ? "Focus" : "Break") + (pomo.count ? " · " + pomo.count + " done" : "");
    $("#pomoFill").style.strokeDashoffset = (326.73 * (1 - pomo.left / pomo.total)).toFixed(2);
    $("#pomoFill").style.stroke = pomo.phase === "focus" ? "var(--brand)" : "var(--lav)";
  }
  $("#btnPomo").addEventListener("click", function () {
    if (pomo.timer) { clearInterval(pomo.timer); pomo.timer = null; this.textContent = "Resume"; return; }
    this.textContent = "Pause";
    pomo.timer = setInterval(function () {
      pomo.left--;
      if (pomo.left <= 0) {
        if (pomo.phase === "focus") { pomo.count++; pomo.phase = "break"; pomo.total = pomo.left = (pomo.count % 4 === 0 ? 15 : 5) * 60; toast("Focus block done. Stand up, stretch, drink water."); }
        else { pomo.phase = "focus"; pomo.total = pomo.left = 25 * 60; toast("Break over. Next focus block."); }
      }
      drawPomo();
    }, 1000);
  });
  $("#btnPomoReset").addEventListener("click", function () {
    clearInterval(pomo.timer); pomo = { timer: null, left: 25 * 60, total: 25 * 60, phase: "focus", count: 0 };
    $("#btnPomo").textContent = "Start"; drawPomo();
  });

  // ------------------------------------------------------------------ talk & resources
  var script = { audience: "friend", feelings: [], duration: "two_weeks", causes: [], impacts: [], needs: [] };
  function chipGroup(field, label, opts, multi) {
    return '<div class="chips-q"><span class="label">' + esc(label) + '</span><div class="chips" data-field="' + field + '" data-multi="' + (multi ? 1 : 0) + '">' +
      Object.keys(opts).map(function (k) {
        var on = multi ? script[field].indexOf(k) >= 0 : script[field] === k;
        return '<button type="button" class="' + (on ? "on" : "") + (k === "thoughts_harm" ? " harm" : "") + '" data-k="' + esc(k) + '" aria-pressed="' + on + '">' + esc(opts[k]) + "</button>";
      }).join("") + "</div></div>";
  }
  function renderScriptForm() {
    var o = S.scriptOpts;
    if (!o) return;
    $("#scriptForm").innerHTML = chipGroup("audience", "Who do you want to talk to?", o.audiences, false) +
      chipGroup("feelings", "How have you been feeling?", o.feelings, true) +
      chipGroup("duration", "For how long?", o.durations, false) +
      chipGroup("causes", "What's behind it? (optional)", o.causes, true) +
      chipGroup("impacts", "What is it affecting? (optional)", o.impacts, true) +
      chipGroup("needs", "What would help from them?", o.needs, true) +
      '<div class="row gap wrap"><label class="inline" style="flex:1">Their name (optional) <input id="sName" maxlength="30" placeholder="e.g. Divya" value="' + esc(script.name || "") + '"></label></div>' +
      '<div class="field"><label class="label small" for="sNote">One thing you really want them to know (optional)</label><input id="sNote" maxlength="300" value="' + esc(script.note || "") + '"></div>';
  }
  $("#scriptForm").addEventListener("click", function (e) {
    var b = e.target.closest(".chips button");
    if (!b) return;
    var g = b.parentElement, field = g.dataset.field, k = b.dataset.k;
    script.name = ($("#sName") || {}).value || ""; script.note = ($("#sNote") || {}).value || "";
    if (g.dataset.multi === "1") {
      var i = script[field].indexOf(k);
      if (i >= 0) script[field].splice(i, 1); else script[field].push(k);
    } else script[field] = k;
    renderScriptForm();
  });
  $("#btnScriptExample").addEventListener("click", function () {
    script = { audience: "counsellor", feelings: ["stressed", "anxious", "tired"], duration: "two_weeks", causes: ["exams", "sleep"], impacts: ["sleep", "studies"],
      needs: ["listen", "study_help"], name: "", note: "I'm scared I'll fail maths and let my parents down" };
    renderScriptForm();
    makeScript();
  });
  $("#btnScript").addEventListener("click", makeScript);
  function makeScript() {
    script.name = ($("#sName") || {}).value || ""; script.note = ($("#sNote") || {}).value || "";
    api("/api/script", { method: "POST", body: script }).then(function (r) {
      var paras = r.full_text.split("\n\n").map(function (p) { return "<p>" + esc(p) + "</p>"; }).join("");
      $("#scriptOut").innerHTML = '<div class="script"><div class="card-head"><h4>What you could say to ' + esc(r.audience_label) + '</h4><button class="btn small" id="btnCopy">Copy</button></div>' + paras +
        '<h5>Short message to ask for a time</h5><div class="short">' + esc(r.short_message) + "</div>" +
        '<h5>Tips</h5><ul class="tips">' + r.tips.map(function (t) { return "<li>" + esc(t) + "</li>"; }).join("") + "</ul></div>";
      $("#btnCopy").addEventListener("click", function () {
        var txt = r.full_text + "\n\n" + r.short_message;
        try {
          navigator.clipboard.writeText(txt).then(function () { toast("Copied."); }, function () { toast("Select the text to copy it."); });
        } catch (e) { toast("Select the text to copy it."); }
      });
      if (r.support && r.support.show) api("/api/support?reason=script&level=urgent").then(function (c) { openSupport(c); }).catch(function () { openSupport({ reason: "script" }); });
    }).catch(failed);
  }
  function renderResources() {
    var r = S.resources;
    $("#helplines").innerHTML = helplineHTML(r.helplines);
    $("#counsellingCell").textContent = r.counselling_cell.name + ": " + r.counselling_cell.how;
    $("#peerIntro").textContent = r.peer_support.intro;
    $("#peerSteps").innerHTML = r.peer_support.steps.map(function (s) { return "<li><b>" + esc(s.title) + "</b>" + esc(s.text) + "</li>"; }).join("");
    $("#peerIdeas").innerHTML = r.peer_support.ideas.map(function (s) { return "<li>" + esc(s) + "</li>"; }).join("");
    $("#whenHelp").innerHTML = r.when_to_get_help.map(function (s) { return "<li>" + esc(s) + "</li>"; }).join("");
    $("#sleepTips").innerHTML = r.sleep_tips.map(function (s) { return "<li><b>" + esc(s.title) + "</b>" + esc(s.text) + "</li>"; }).join("");
    $("#breathNote").textContent = r.breathing.note;
    renderGrounding();
  }
  $("#btnTalkCounsellor").addEventListener("click", function () {
    api("/api/support/contact", { method: "POST", body: { reason: "general", preferred: "in person" } }).then(function (r) { toast(r.message); }).catch(failed);
  });

  // ------------------------------------------------------------------ counsellor
  $("#btnLogin").addEventListener("click", login);
  $("#cPin").addEventListener("keydown", function (e) { if (e.key === "Enter") login(); });
  function login() {
    api("/api/counsellor/login", { method: "POST", body: { pin: $("#cPin").value, name: $("#cName").value } }).then(function (r) {
      S.token = r.token;
      try { sessionStorage.setItem("mindease_token", r.token); } catch (e) { /* ignore */ }
      $("#cPin").value = "";
      loadDashboard();
    }).catch(failed);
  }
  $("#btnLogout").addEventListener("click", function () {
    api("/api/counsellor/logout", { method: "POST" }).catch(function () { return null; }).then(function () {
      S.token = null; S.dash = null;
      try { sessionStorage.removeItem("mindease_token"); } catch (e) { /* ignore */ }
      $("#dash").hidden = true; $("#loginCard").hidden = false;
    });
  });
  function loadDashboard() {
    if (!S.token) { $("#dash").hidden = true; $("#loginCard").hidden = false; return; }
    api("/api/counsellor/dashboard").then(function (d) {
      S.dash = d;
      $("#loginCard").hidden = true; $("#dash").hidden = false;
      renderDashboard();
    }).catch(function (err) {
      if (err.status === 401) {
        S.token = null;
        try { sessionStorage.removeItem("mindease_token"); } catch (e) { /* ignore */ }
        $("#dash").hidden = true; $("#loginCard").hidden = false;
      } else failed(err);
    });
  }
  function renderDashboard() {
    var d = S.dash, k = d.kpis;
    $("#viewer").textContent = "Signed in as " + d.viewer.name + " (" + d.viewer.role + ")";
    var wk = d.weeks[d.weeks.length - 1];
    $("#dashSub").textContent = "Week " + k.week + " of term (from " + fmtDate(wk.start) + ")" + (wk.exam ? ", semester exams" : "") + ". " + k.cohort_size + " pseudonymous students, " + k.opted_in_contact + " opted in to be contacted.";
    var delta = k.pct_moderate_plus_prev == null ? "" : (k.pct_moderate_plus - k.pct_moderate_plus_prev >= 0 ? "+" : "") + (k.pct_moderate_plus - k.pct_moderate_plus_prev).toFixed(0) + " pts vs last week";
    $("#kpis").innerHTML = [
      { l: "Check-ins shared this week", v: k.checkins_this_week, d: "of " + k.cohort_size + " students" },
      { l: "PHQ-9 moderate or above", v: k.pct_moderate_plus.toFixed(0) + "%", d: delta },
      { l: "New item-9 alerts", v: k.open_alerts, d: k.awaiting_follow_up + " acknowledged, awaiting follow-up" },
      { l: "Asked to be contacted", v: k.pending_contacts, d: "pending" }
    ].map(function (x) { return '<div class="card kpi"><div class="k-label">' + esc(x.l) + '</div><div class="k-value">' + esc(x.v) + '</div><div class="k-delta">' + esc(x.d) + "</div></div>"; }).join("");
    $$("#dashInst button").forEach(function (b) { b.classList.toggle("on", b.dataset.inst === S.dashInst); });
    renderBands();
    $("#narrative").innerHTML = d.narrative.map(function (n) { return "<li>" + esc(n) + "</li>"; }).join("");
    $("#principles").innerHTML = d.privacy.map(function (p) { return "<li><b>" + esc(p.title) + "</b>" + esc(p.text) + "</li>"; }).join("");
    $("#dashExplain").innerHTML = d.explain.map(function (p) { return "<li>" + esc(p) + "</li>"; }).join("");
    renderAlerts();
    renderContacts();
    var by = d.by_year;
    $("#byYearNote").textContent = "Week " + by.week + ", PHQ-9. Counts under " + by.min_cell + " are hidden so no one can be singled out.";
    $("#byYear").innerHTML = "<tr><th>Year</th><th class=\"num\">Check-ins</th><th class=\"num\">Moderate+</th></tr>" + by.rows.map(function (r) {
      return "<tr><td>Year " + r.year + '</td><td class="num">' + esc(r.n) + '</td><td class="num">' + esc(r.moderate_plus) + (r.suppressed ? ' <span class="muted xsmall">suppressed</span>' : "") + "</td></tr>";
    }).join("");
  }
  $("#dashInst").addEventListener("click", function (e) {
    var b = e.target.closest("button[data-inst]");
    if (!b || !S.dash) return;
    S.dashInst = b.dataset.inst;
    $$("#dashInst button").forEach(function (x) { x.classList.toggle("on", x === b); });
    renderBands();
  });
  function renderBands() {
    var d = S.dash, inst = S.dashInst, rows = d[inst], bands = d.bands[inst];
    var host = $("#chBands");
    $("#lgBands").innerHTML = legend(bands.map(function (b) { return { label: b.label, color: bandColor(b.band, inst) }; }).reverse());
    var W = Math.max(320, host.clientWidth || 700), H = 250, m = { l: 34, r: 10, t: 22, b: 40 };
    var iw = W - m.l - m.r, ih = H - m.t - m.b;
    var maxN = Math.max.apply(null, rows.map(function (r) { return r.n; }).concat([1]));
    var step = maxN <= 40 ? 10 : (maxN <= 80 ? 20 : 50);
    var top = Math.ceil(maxN / step) * step;
    var y = function (v) { return m.t + ih - v / top * ih; };
    var slot = iw / rows.length, bw = Math.min(24, slot * 0.5);
    var out = ['<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Weekly check-ins by severity band">'];
    rows.forEach(function (r, i) {
      if (r.exam) out.push('<rect x="' + (m.l + i * slot) + '" y="' + m.t + '" width="' + slot + '" height="' + ih + '" fill="var(--lav-soft)"/>');
    });
    var firstExam = rows.findIndex(function (r) { return r.exam; });
    if (firstExam >= 0) out.push('<text x="' + (m.l + firstExam * slot + 4) + '" y="' + (m.t - 8) + '" font-size="10.5" fill="var(--lav-strong)" font-weight="600">Semester exams</text>');
    out.push('<g class="axis">');
    for (var t = 0; t <= top; t += step) {
      out.push('<line class="gridline" x1="' + m.l + '" x2="' + (m.l + iw) + '" y1="' + y(t) + '" y2="' + y(t) + '"/><text x="' + (m.l - 6) + '" y="' + (y(t) + 3.5) + '" text-anchor="end">' + t + "</text>");
    }
    rows.forEach(function (r, i) {
      var cx = m.l + i * slot + slot / 2;
      out.push('<text x="' + cx + '" y="' + (H - 22) + '" text-anchor="middle">Wk ' + r.week + '</text><text x="' + cx + '" y="' + (H - 8) + '" text-anchor="middle" font-size="10">' + r.pct_moderate_plus.toFixed(0) + (slot >= 64 ? "% mod+" : "%") + "</text>");
    });
    out.push("</g>");
    rows.forEach(function (r, i) {
      var cx = m.l + i * slot + slot / 2 - bw / 2, acc = 0;
      var segs = bands.filter(function (b) { return r.counts[b.band] > 0; });
      segs.forEach(function (b, si) {
        var v = r.counts[b.band];
        var y0 = y(acc), y1 = y(acc + v);
        var isTop = si === segs.length - 1;
        var h = Math.max(0.5, y0 - y1 - (isTop ? 0 : 2));
        var yy = y1 + (isTop ? 0 : 2);
        if (isTop) {
          var rr = Math.min(4, h, bw / 2);
          out.push('<path d="M' + cx + " " + (yy + h) + "V" + (yy + rr) + "Q" + cx + " " + yy + " " + (cx + rr) + " " + yy + "H" + (cx + bw - rr) + "Q" + (cx + bw) + " " + yy + " " + (cx + bw) + " " + (yy + rr) +
            "V" + (yy + h) + 'Z" fill="' + bandColor(b.band, inst) + '"/>');
        } else {
          out.push('<rect x="' + cx + '" y="' + yy + '" width="' + bw + '" height="' + h + '" fill="' + bandColor(b.band, inst) + '"/>');
        }
        acc += v;
      });
      out.push('<text x="' + (cx + bw / 2) + '" y="' + (y(r.n) - 5) + '" text-anchor="middle" font-size="10.5" fill="var(--text)" font-weight="600">' + r.n + "</text>");
      out.push('<rect class="hit" data-i="' + i + '" x="' + (m.l + i * slot) + '" y="' + m.t + '" width="' + slot + '" height="' + ih + '" fill="transparent"/>');
    });
    out.push("</svg>");
    host.innerHTML = out.join("");
    $$(".hit", host).forEach(function (h) {
      h.addEventListener("mousemove", function (evt) {
        var r = rows[+h.dataset.i];
        showTip("<b>Week " + r.week + (r.exam ? " (exams)" : "") + "</b> · " + r.n + " check-ins<br>" + bands.slice().reverse().map(function (b) { return esc(b.label) + ": " + r.counts[b.band]; }).join("<br>") +
          "<br>Moderate or above: " + r.pct_moderate_plus.toFixed(0) + "%", evt);
      });
      h.addEventListener("mouseleave", hideTip);
    });
  }
  function renderAlerts() {
    var alerts = S.dash.alerts;
    var head = "<tr><th>Alert</th><th>Raised</th><th>Item 9 · PHQ-9</th><th>Contact</th><th>Status</th><th>Action</th></tr>";
    $("#alertsTbl").innerHTML = head + alerts.map(function (a) {
      var contact = a.contact_ok ? "Opted in<div class=\"muted xsmall\">" + esc(a.preferred || "") + "</div>" : '<span class="muted xsmall">No contact consent. Crisis resources were shown.</span>';
      var last = (a.history || [])[a.history.length - 1];
      var hist = last ? '<div class="hist">' + esc(last.by) + " · " + esc(String(last.at).replace("T", " ")) + (last.note ? ": " + esc(last.note) : "") + "</div>" : "";
      var act = a.status === "followed_up" ? '<span class="muted xsmall">Closed</span>' :
        '<div class="alert-actions"><input placeholder="Note (optional)" maxlength="280" data-note="' + a.id + '">' +
        (a.status === "new" ? '<button class="btn small primary" data-ack="' + a.id + '">Acknowledge</button>' : "") +
        '<button class="btn small" data-fu="' + a.id + '">Followed up</button></div>';
      return '<tr><td class="nowrap"><b>' + esc(a.id) + '</b><div class="mono xsmall">' + esc(a.pid) + '</div></td><td class="nowrap">' + fmtDate(a.raised) + '<div class="muted xsmall">week ' + a.week +
        (a.days_open != null ? " · " + (a.days_open === 0 ? "today" : a.days_open + " d ago") : "") + "</div></td><td>" + esc(a.item9_label) + '<div class="nowrap">' + a.phq9_total + " " + bandChip(a.band, "phq9") +
        "</div></td><td>" + contact + '</td><td><span class="status ' + esc(a.status) + '">' + esc(a.status.replace("_", " ")) + "</span>" + hist + "</td><td>" + act + "</td></tr>";
    }).join("");
  }
  $("#alertsTbl").addEventListener("click", function (e) {
    var ack = e.target.closest("button[data-ack]"), fu = e.target.closest("button[data-fu]");
    if (!ack && !fu) return;
    var id = (ack || fu).dataset[ack ? "ack" : "fu"];
    var noteEl = $('input[data-note="' + id + '"]');
    api("/api/counsellor/alerts/" + id + "/" + (ack ? "ack" : "followup"), { method: "POST", body: { note: noteEl ? noteEl.value : "" } })
      .then(function () { toast(ack ? "Alert " + id + " acknowledged." : "Alert " + id + " marked as followed up."); loadDashboard(); }).catch(failed);
  });
  function renderContacts() {
    var cs = S.dash.contacts;
    $("#contactCount").textContent = cs.filter(function (c) { return c.status === "pending"; }).length + " pending";
    $("#contacts").innerHTML = cs.map(function (c) {
      return "<li><div><b class=\"mono\">" + esc(c.pid) + "</b> " + (c.latest_band ? bandChip(c.latest_band, "phq9") : "") + '<div class="muted xsmall">' + esc(c.reason) + " · " + esc(c.preferred) + " · " + fmtDate(c.requested) +
        (c.priority === "today" ? ' · <span class="c-pri">respond today</span>' : "") + "</div></div>" +
        (c.status === "pending" ? '<button class="btn small" data-done="' + esc(c.id) + '">Mark contacted</button>' : '<span class="status contacted">contacted</span>') + "</li>";
    }).join("") || '<li class="muted">No requests.</li>';
  }
  $("#contacts").addEventListener("click", function (e) {
    var b = e.target.closest("button[data-done]");
    if (!b) return;
    api("/api/counsellor/contacts/" + b.dataset.done + "/done", { method: "POST" }).then(function () { toast("Marked as contacted."); loadDashboard(); }).catch(failed);
  });

  // ------------------------------------------------------------------ about / evaluation
  function pct(x) { return x == null ? "–" : Math.round(100 * x) + "%"; }
  function loadAbout() {
    if (S.evaluation) return renderAbout();
    $("#about").innerHTML = '<div class="card span3 muted">Loading the measured numbers…</div>';
    api("/api/evaluation").then(function (e) { S.evaluation = e; renderAbout(); }).catch(failed);
  }
  function renderAbout() {
    var e = S.evaluation, s = e.sentiment, sf = e.safety, tr = e.trends.conditions, la = e.latency;
    function frac(x) { return x.tp + "/" + (x.tp + x.fn); }
    $("#about").innerHTML =
      '<div class="card span3"><h3>Measured, not claimed</h3><p class="muted small">All numbers below are recomputed by <span class="mono">python -m mindease.evaluation</span> on hand-labelled sentences written by the team and on simulated journals. They are small, single-annotator sets: indicative, not clinical validation.</p>' +
      '<div class="metric-tiles">' +
      "<div><b>" + pct(s.heldout.accuracy) + "</b><span>sentiment accuracy, held-out set (n=" + s.heldout.n + ")</span></div>" +
      "<div><b>" + pct(s.fresh.accuracy) + "</b><span>sentiment accuracy, fresh unseen wording (n=" + s.fresh.n + ")</span></div>" +
      "<div><b>" + frac(sf.check3) + "</b><span>concerning phrases caught, newest check set</span></div>" +
      "<div><b>" + pct(tr["dip_1.5"].rule) + "</b><span>simulated mood dips (1.5 points) flagged within 7 days; " + pct(tr.no_dip.rule) + " false alarms per stable week</span></div>" +
      "</div></div>" +
      '<div class="card"><h4>Sentiment &amp; emotion</h4><ul>' +
      "<li>Hand-built list of ~450 entries (319 words, 68 phrases, 58 emoji; 56 Tanglish terms), scored −4…+4.</li>" +
      "<li>Rules: negation (“not happy”, Tamil “nalla illa”), intensifiers (“romba”, “very”), “but” contrast, caps, “!”.</li>" +
      "<li>Untuned sets combined: " + pct(s.untuned_combined.accuracy) + " vs " + pct(s.untuned_combined.baseline_accuracy) + " for plain word counting.</li>" +
      "<li>Negation checks: " + s.negation_checks.passed + "/" + s.negation_checks.total + " pass.</li>" +
      "<li>Most misses are new words read as neutral, not wrong-way flips (" + s.fresh.polarity_flips + " flip on the fresh set).</li></ul></div>" +
      '<div class="card"><h4>Concerning-language safety net</h4><ul>' +
      "<li>Direct phrasing (held-out): " + frac(sf.heldout_direct) + " caught, " + sf.heldout_direct.fp + "/" + (sf.heldout_direct.fp + sf.heldout_direct.tn) + " false alarms.</li>" +
      "<li>Indirect phrasing first caught 0/12. We added a co-occurrence rule (first person + death/absence cue + wish cue); the next unseen set caught " + frac(sf.check3) + ".</li>" +
      "<li>Everyday hyperbole (“exam is killing me”, “dead tired”) does not trigger.</li>" +
      "<li>PHQ-9 item 9 is the validated signal; it always triggers support (" + sf.item9_rule.correct + "/" + sf.item9_rule.combinations + " rule checks).</li></ul></div>" +
      '<div class="card"><h4>Trend detection</h4><ul>' +
      "<li>Personal baseline (mean ± sd of earlier days), never a comparison with other students.</li>" +
      "<li>Rule: one-sided CUSUM (k = 0.5, h = 5) has crossed <i>and</i> the last 2+ days are below your usual. A 7-day OLS slope t-test is shown as evidence only.</li>" +
      "<li>Held-out simulated journals: 1.5-point dips flagged " + pct(tr["dip_1.5"].rule) + " (median " + tr["dip_1.5"].median_delay_days + " days), 1-point dips " + pct(tr["dip_1.0"].rule) + ".</li>" +
      "<li>The first rule flagged 21% of stable weeks; the tuned rule " + pct(tr.no_dip.rule) + ".</li>" +
      "<li>Speed: " + la.sentiment_analyse_us.toFixed(0) + " µs per entry, trends " + la.trends_analyse_21d_ms.toFixed(1) + " ms, PHQ-9 " + la.phq9_score_us.toFixed(0) + " µs.</li></ul></div>" +
      '<div class="card span2"><h4>Ethics &amp; safety by design</h4><ul>' +
      "<li><b>Not a diagnosis.</b> Every result says so; wording is warm, never alarming or labelling.</li>" +
      "<li><b>Help on every screen:</b> Tele-MANAS 14416 / 1-800-891-4416 and 112 are always one tap away.</li>" +
      "<li><b>Safety first:</b> item 9 &gt; 0 or concerning journal words open a gentle support screen immediately, whatever the score.</li>" +
      "<li><b>Private by default:</b> journals never leave the student's record; check-ins are shared only with consent, pseudonymously, and can be deleted.</li>" +
      "<li><b>Counsellors see aggregates</b>, small cells suppressed, plus pseudonymous alerts with an acknowledge-and-follow-up workflow.</li>" +
      "<li><b>Honest limits:</b> keyword detectors miss indirect language. MindEase is a safety net and a nudge to talk, not a replacement for people.</li></ul></div>" +
      '<div class="card"><h4>Limitations</h4><ul>' +
      "<li>Lexicon covers a small slice of Tanglish; sarcasm and new slang are missed.</li>" +
      "<li>All evaluation sets were written by one person; a clinical, multi-rater validation is needed before any real use.</li>" +
      "<li>Cohort data is synthetic (fixed seed).</li></ul></div>";
  }

  // ------------------------------------------------------------------ init
  function init() {
    setMood(null);
    S.mood = null;
    drawPomo();
    Promise.all([api("/api/questionnaires"), api("/api/resources"), api("/api/script/options")]).then(function (res) {
      S.q = res[0]; S.resources = res[1]; S.scriptOpts = res[2];
      S.answers = { phq9: [], gad7: [] };
      renderQuestionnaire();
      renderResources();
      renderScriptForm();
      setExams(exampleExams().slice(0, 2));
      return refreshStudent();
    }).then(function () {
      setExams(exampleExams().slice(0, 2));
      var h = (location.hash || "").replace("#", "");
      if (h && document.getElementById("view-" + h)) show(h);
    }).catch(failed);
  }
  init();
})();
