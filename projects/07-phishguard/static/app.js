/* PhishGuard front-end - vanilla JS, no external libraries, no network calls except to this local server. */
(function () {
  "use strict";

  var $ = function (id) { return document.getElementById(id); };
  var state = { samples: [], bulk: [], quiz: [], qi: 0, score: 0, answered: false, stats: null };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function pct(x) { return Math.round(x * 100) + "%"; }
  function fmt(x, d) { return Number(x).toFixed(d == null ? 2 : d); }

  function api(path, body) {
    var opts = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
    return fetch(path, opts).then(function (r) {
      return r.json().then(function (j) {
        if (!r.ok) { throw new Error(j.error || ("HTTP " + r.status)); }
        return j;
      });
    });
  }

  /* ---------------- theme ---------------- */
  function initTheme() {
    var saved = null;
    try { saved = localStorage.getItem("pg-theme"); } catch (e) { saved = null; }
    if (saved === "dark" || saved === "light") { document.documentElement.setAttribute("data-theme", saved); }
    $("themeToggle").addEventListener("click", function () {
      var cur = document.documentElement.getAttribute("data-theme");
      if (!cur) { cur = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"; }
      var next = cur === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      try { localStorage.setItem("pg-theme", next); } catch (e) { /* ignore */ }
    });
  }

  /* ---------------- tabs ---------------- */
  function showTab(name) {
    document.querySelectorAll(".tab-btn").forEach(function (b) { b.classList.toggle("active", b.getAttribute("data-tab") === name); });
    document.querySelectorAll(".tab").forEach(function (t) { t.classList.toggle("active", t.id === "tab-" + name); });
    if (name === "stats" && !state.stats) { loadStats(); }
    if (name === "quiz" && state.quiz.length && !$("qText").getAttribute("data-ready")) { renderQuestion(); }
  }

  /* ---------------- analyse ---------------- */
  function setText(t) { $("msg").value = t; updateCount(); }
  function updateCount() { $("charCount").textContent = $("msg").value.length + " / 5000"; }

  function analyse() {
    var text = $("msg").value;
    if (!text.trim()) { $("verdictMeta").textContent = "Type or paste something first (or click Run demo)."; return; }
    $("analyseBtn").disabled = true;
    api("/api/analyze", { text: text }).then(renderResult).catch(function (e) {
      $("verdictMeta").textContent = "Error: " + e.message;
    }).then(function () { $("analyseBtn").disabled = false; });
  }

  function renderResult(r) {
    var card = $("verdictCard");
    card.className = "card verdict-card v-" + r.verdict;
    $("riskNum").textContent = r.risk;
    $("verdict").textContent = r.verdict;
    var g = $("gaugeVal");
    g.setAttribute("stroke-dasharray", r.risk + " 100");
    g.style.stroke = r.verdict === "Dangerous" ? "var(--danger)" : r.verdict === "Suspicious" ? "var(--warn)" : "var(--safe)";
    $("verdictMeta").innerHTML = (r.mode === "url" ? "Analysed as a <b>link</b>" : "Analysed as a <b>message</b>") +
      " in " + esc(r.latency_ms) + " ms &middot; on this device";

    $("components").innerHTML = r.components.map(function (c) {
      return '<div class="comp" title="raw score ' + fmt(c.raw, 3) + ' x weight ' + c.weight + '"><span class="lab">' + esc(c.label) +
        '</span><div class="bar"><i style="width:' + Math.round(c.value * 100) + '%"></i></div><span class="val">' + pct(c.value) + "</span></div>";
    }).join("");

    // highlighted segments
    var hl = $("highlight");
    hl.classList.remove("empty");
    hl.innerHTML = r.segments.map(function (s) {
      if (!s.kind) { return esc(s.text); }
      return '<span class="hl ' + esc(s.kind) + '" title="' + esc(s.label) + '">' + esc(s.text) + "</span>";
    }).join("");

    // rules
    $("rules").classList.remove("muted");
    $("rules").innerHTML = r.rules.length ? r.rules.map(function (x) {
      return '<div class="rule-item' + (x.weight < 0.3 ? " low" : "") + '"><div class="t"><span>' + esc(x.title) + '</span><span class="w">+' +
        Math.round(x.weight * 100) + '</span></div><div class="m">"' + esc(x.matches.slice(0, 2).join('", "')) + '"</div></div>';
    }).join("") : '<div class="muted small">No scam-pattern rule fired.' + (r.mode === "url" ? " (Link-only input: see the URL model reasons.)" : "") + "</div>";

    // tokens
    var tk = $("tokens");
    tk.classList.remove("muted");
    $("tokensTitle").textContent = r.nb ? "Words pushing toward scam" : "URL feature contributions";
    if (r.nb) {
      var all = r.nb.scam_tokens.concat(r.nb.ham_tokens);
      var max = Math.max.apply(null, all.map(function (t) { return Math.abs(t.contribution); }).concat([0.01]));
      var row = function (t, neg) {
        return '<div class="tok' + (neg ? " neg" : "") + '" title="LLR ' + fmt(t.llr, 3) + " x count " + t.count + '"><span class="k">' + esc(t.display || t.token) +
          '</span><div class="bar"><i style="width:' + Math.round(Math.abs(t.contribution) / max * 100) + '%"></i></div><span class="v">' +
          (t.contribution > 0 ? "+" : "") + fmt(t.contribution, 2) + "</span></div>";
      };
      tk.innerHTML = (r.nb.scam_tokens.length ? r.nb.scam_tokens.slice(0, 7).map(function (t) { return row(t, false); }).join("") : '<div class="muted small">No scam-leaning words.</div>') +
        (r.nb.ham_tokens.length ? '<div class="subhead">Pushing toward safe</div>' + r.nb.ham_tokens.slice(0, 3).map(function (t) { return row(t, true); }).join("") : "") +
        '<div class="nbmeta">NB log-odds ' + fmt(r.nb.log_odds, 1) + " &divide; T=" + r.nb.temperature + ", prior " + r.nb.deploy_prior + " &rarr; p<sub>text</sub> = " + fmt(r.nb.probability, 3) +
        " &middot; char n-grams " + (r.nb.char_ngram_total >= 0 ? "+" : "") + fmt(r.nb.char_ngram_total, 1) + "</div>";
    } else {
      var u = r.entities.urls[0];
      tk.innerHTML = '<div class="muted small">Link-only input, so the text model is skipped. Feature contributions of the URL model (w &middot; x):</div>' +
        u.reasons.map(function (x) {
          return '<div class="tok' + (x.contribution < 0 ? " neg" : "") + '" title="' + esc(x.label) + '"><span class="k">' + esc(x.feature) +
            '</span><div class="bar"><i style="width:' + Math.min(100, Math.round(Math.abs(x.contribution) / 3.5 * 100)) + '%"></i></div><span class="v">' +
            (x.contribution > 0 ? "+" : "") + fmt(x.contribution, 2) + "</span></div>";
        }).join("");
    }

    renderEntities(r.entities);
    $("advice").innerHTML = r.advice.map(function (a) { return "<li>" + esc(a).replace(/1930/g, "<b>1930</b>") + "</li>"; }).join("");
  }

  function renderEntities(e) {
    var parts = [];
    e.urls.forEach(function (u) {
      var reasons = u.reasons.slice(0, 6).map(function (x) {
        return '<span class="reason' + (x.contribution < 0 ? " neg" : "") + '" title="weight ' + x.weight + '">' + esc(x.label) + " " +
          (x.contribution > 0 ? "+" : "") + fmt(x.contribution, 1) + "</span>";
      }).join("");
      parts.push('<div class="ent"><div class="ent-h"><span class="ent-v">' + esc(u.url) + '</span><span class="badge ' + u.verdict + '" title="model probability ' + pct(u.probability) + '">LINK ' +
        u.risk + "/100 " + u.verdict + '</span></div><div class="small muted">domain <b>' + esc(u.info.registered_domain || u.info.host) + "</b> &middot; scheme " +
        esc(u.info.scheme) + (u.info.lookalike_of ? " &middot; imitates <b>" + esc(u.info.lookalike_of) + "</b>" : "") +
        (u.info.brands.length ? " &middot; brand words: " + esc(u.info.brands.join(", ")) : "") + '</div><div class="reasons">' + reasons + "</div></div>");
    });
    e.phones.concat(e.upi).forEach(function (p) {
      var v = p.score >= 0.65 ? "Dangerous" : p.score >= 0.35 ? "Suspicious" : "Safe";
      var kind = e.upi.indexOf(p) >= 0 ? "UPI" : "PHONE";
      parts.push('<div class="ent"><div class="ent-h"><span class="ent-v">' + esc(p.value) + '</span><span class="badge ' + v + '">' + kind + " " +
        Math.round(p.score * 100) + '%</span></div><div class="small muted">' + esc(p.reason) + "</div></div>");
    });
    var box = $("entities");
    box.classList.remove("muted");
    box.innerHTML = parts.length ? parts.join("") : '<div class="muted small">No links, phone numbers or UPI IDs in this message.</div>';
  }

  /* ---------------- bulk ---------------- */
  function bulkScan() {
    var text = $("bulkText").value;
    if (!text.trim()) { $("bulkMeta").textContent = "Paste some lines first (or Load demo lines)."; return; }
    $("bulkBtn").disabled = true;
    api("/api/bulk", { text: text }).then(function (r) {
      $("bulkMeta").textContent = r.count + " lines scanned in " + r.total_ms + " ms";
      $("bulkSummary").innerHTML = ["Dangerous", "Suspicious", "Safe"].map(function (v) {
        return '<span class="badge ' + v + '">' + r.summary[v] + " " + v + "</span>";
      }).join("");
      $("bulkTable").querySelector("tbody").innerHTML = r.rows.map(function (row) {
        var col = row.verdict === "Dangerous" ? "var(--danger)" : row.verdict === "Suspicious" ? "var(--warn)" : "var(--safe)";
        return '<tr class="click" data-text="' + esc(row.text) + '"><td class="num">' + row.line + '</td><td class="msgcell" title="' + esc(row.text) + '">' +
          esc(row.text) + '</td><td><div class="minibar"><div class="bar"><i style="width:' + row.risk + "%;background:" + col + '"></i></div><span class="num">' +
          row.risk + '</span></div></td><td><span class="badge ' + row.verdict + '">' + row.verdict + '</span></td><td class="small">' + esc(row.reason) + "</td></tr>";
      }).join("");
    }).catch(function (e) { $("bulkMeta").textContent = "Error: " + e.message; })
      .then(function () { $("bulkBtn").disabled = false; });
  }

  /* ---------------- quiz ---------------- */
  function renderQuestion() {
    var q = state.quiz[state.qi];
    $("qText").setAttribute("data-ready", "1");
    $("qProgress").textContent = "Question " + (state.qi + 1) + " / " + state.quiz.length;
    $("qScore").textContent = "Score " + state.score;
    $("qBar").style.width = (state.qi / state.quiz.length * 100) + "%";
    $("qText").textContent = q.text;
    $("qButtons").classList.remove("hidden");
    $("qReveal").className = "reveal hidden";
    state.answered = false;
  }

  function answer(ans) {
    if (state.answered) { return; }
    state.answered = true;
    var q = state.quiz[state.qi];
    var ok = ans === q.answer;
    if (ok) { state.score += 1; }
    $("qScore").textContent = "Score " + state.score;
    $("qButtons").classList.add("hidden");
    var rv = $("qReveal");
    rv.className = "reveal " + (ok ? "ok" : "bad");
    var last = state.qi === state.quiz.length - 1;
    rv.innerHTML = "<h3>" + (ok ? "Correct!" : "Not quite.") + " This one is " + (q.answer === "scam" ? "a SCAM" : "SAFE") + ".</h3><div>" + esc(q.why) +
      '</div><div class="model" id="qModel">Asking PhishGuard...</div><div class="row"><button class="btn primary" id="qNext" type="button">' +
      (last ? "See my score" : "Next question") + "</button></div>";
    $("qNext").addEventListener("click", function () {
      if (last) { finishQuiz(); } else { state.qi += 1; renderQuestion(); }
    });
    api("/api/analyze", { text: q.text }).then(function (r) {
      var top = r.rules.length ? r.rules[0].title : (r.nb && r.nb.scam_tokens.length ? "words like '" + r.nb.scam_tokens.slice(0, 3).map(function (t) { return t.token; }).join("', '") + "'" : "no strong signals");
      $("qModel").innerHTML = "PhishGuard says: <b class=\"c-" + r.verdict + "\">" + r.risk + "/100 " + r.verdict + "</b> &middot; main signal: " + esc(top);
    }).catch(function () { $("qModel").textContent = ""; });
  }

  function finishQuiz() {
    var n = state.quiz.length;
    $("qBar").style.width = "100%";
    $("qProgress").textContent = "Finished";
    var msg = state.score === n ? "Perfect! You're a scam-spotting pro." : state.score >= n * 0.7 ? "Great instincts. Share this quiz with your family." :
      "Scammers are clever - review the explanations and try again.";
    $("qText").innerHTML = '<div class="final"><div class="big">' + state.score + " / " + n + "</div><div>" + esc(msg) +
      '</div><div class="small muted" style="margin-top:6px">Remember: never share OTP / UPI PIN. Lost money? Call <b>1930</b>.</div></div>';
    $("qReveal").className = "reveal hidden";
    $("qButtons").classList.add("hidden");
    var rv = $("qReveal");
    rv.className = "row center";
    rv.innerHTML = '<button class="btn primary" id="qRestart" type="button">Play again</button>';
    $("qRestart").addEventListener("click", function () { state.qi = 0; state.score = 0; renderQuestion(); });
  }

  /* ---------------- stats ---------------- */
  function cmSvg(c) {
    var max = Math.max(c.tp, c.fp, c.tn, c.fn, 1);
    var cell = function (x, y, v, good, lab) {
      var a = 0.12 + 0.78 * (v / max);
      var fill = good ? "rgba(16,185,129," + a.toFixed(2) + ")" : (v ? "rgba(239,68,68," + Math.max(a, 0.25).toFixed(2) + ")" : "rgba(148,163,184,.12)");
      return '<rect x="' + x + '" y="' + y + '" width="96" height="70" rx="8" fill="' + fill + '"/>' +
        '<text x="' + (x + 48) + '" y="' + (y + 38) + '" text-anchor="middle" font-size="22" font-weight="800" fill="currentColor">' + v + "</text>" +
        '<text x="' + (x + 48) + '" y="' + (y + 58) + '" text-anchor="middle" font-size="10" fill="currentColor" opacity=".7">' + lab + "</text>";
    };
    return '<svg class="cm-svg" viewBox="0 0 260 200" role="img" aria-label="confusion matrix">' +
      '<text x="160" y="12" text-anchor="middle" font-size="10" fill="currentColor" opacity=".65">PREDICTED</text>' +
      '<text x="112" y="28" text-anchor="middle" font-size="11" fill="currentColor" opacity=".8">Scam</text>' +
      '<text x="210" y="28" text-anchor="middle" font-size="11" fill="currentColor" opacity=".8">Safe</text>' +
      '<text x="12" y="118" text-anchor="middle" font-size="10" fill="currentColor" opacity=".65" transform="rotate(-90 12 118)">ACTUAL</text>' +
      '<text x="46" y="75" text-anchor="end" font-size="11" fill="currentColor" opacity=".8">Scam</text>' +
      '<text x="46" y="149" text-anchor="end" font-size="11" fill="currentColor" opacity=".8">Safe</text>' +
      cell(62, 36, c.tp, true, "true positive") + cell(162, 36, c.fn, false, "missed scam") +
      cell(62, 112, c.fp, false, "false alarm") + cell(162, 112, c.tn, true, "true negative") + "</svg>";
  }

  function cmCard(title, sub, m) {
    return '<div class="card"><div class="card-h"><h2>' + esc(title) + '</h2></div><div class="cm-sub">' + esc(sub) + "</div>" + cmSvg(m.confusion) +
      '<div class="cm-metrics"><div><b>' + pct(m.accuracy) + "</b><span>acc</span></div><div><b>" + pct(m.precision) + "</b><span>prec</span></div><div><b>" +
      pct(m.recall) + "</b><span>recall</span></div><div><b>" + fmt(m.f1, 3) + "</b><span>F1</span></div></div></div>";
  }

  function loadStats() {
    api("/api/stats").then(function (s) {
      state.stats = s;
      var d = s.dataset;
      var kpis = [
        [pct(s.message_combined.accuracy), "Combined accuracy (random hold-out, n=" + s.message_combined.n + ")", true],
        [pct(s.heldout_templates.combined.accuracy), "Combined accuracy on unseen templates (n=" + s.heldout_templates.test + ")", true],
        [pct(s.url_lr.accuracy), "URL model accuracy (n=" + s.url_lr.n + ")", false],
        [fmt(s.latency_ms.message, 2) + " ms", "Avg. latency per message (full pipeline)", false],
        [fmt(s.train_seconds, 2) + " s", "Training time on this machine", false],
        [d.messages + " / " + d.urls, "Synthetic messages / URLs", false],
      ];
      $("kpis").innerHTML = kpis.map(function (k) {
        return '<div class="kpi' + (k[2] ? " accent" : "") + '"><div class="v">' + esc(k[0]) + '</div><div class="l">' + esc(k[1]) + "</div></div>";
      }).join("");
      $("honesty").innerHTML = "<b>Honesty note:</b> " + esc(s.note) + " On the random split the test messages share templates with training, so the text model looks perfect. " +
        "The <b>unseen-template</b> split (whole phrasings held out) is the more realistic number. Real SMS will be messier still.";
      $("cms").innerHTML = cmCard("Text model (Naive Bayes)", "Random 25% hold-out, threshold p = 0.5", s.message_nb) +
        cmCard("Full pipeline", "Random hold-out, flagged if risk >= " + s.config.safe_below, s.message_combined) +
        cmCard("Full pipeline, unseen templates", s.heldout_templates.train + " train / " + s.heldout_templates.test + " test", s.heldout_templates.combined) +
        cmCard("URL model (logistic regression)", "Random 25% hold-out of " + d.urls + " URLs", s.url_lr);

      var rows = [
        ["Naive Bayes only", "random", s.message_nb], ["Rules only (score >= 0.35)", "random", s.message_rules_only],
        ["Full pipeline (risk >= 35)", "random", s.message_combined], ["Full pipeline (risk >= 65)", "random", s.message_combined_dangerous],
        ["Naive Bayes only", "unseen templates", s.heldout_templates.nb], ["Full pipeline (risk >= 35)", "unseen templates", s.heldout_templates.combined],
        ["URL logistic regression", "random", s.url_lr],
      ];
      $("evalTable").innerHTML = "<thead><tr><th>Model</th><th>Split</th><th>n</th><th>Acc</th><th>Prec</th><th>Recall</th><th>F1</th></tr></thead><tbody>" +
        rows.map(function (r) {
          var m = r[2];
          return "<tr><td>" + esc(r[0]) + '</td><td class="small muted">' + esc(r[1]) + '</td><td class="num">' + m.n + '</td><td class="num">' + pct(m.accuracy) +
            '</td><td class="num">' + pct(m.precision) + '</td><td class="num">' + pct(m.recall) + '</td><td class="num">' + fmt(m.f1, 3) + "</td></tr>";
        }).join("") + "</tbody>";

      var wmax = Math.max.apply(null, s.lr_weights.map(function (w) { return Math.abs(w.weight); }));
      $("weights").innerHTML = s.lr_weights.filter(function (w) { return Math.abs(w.weight) >= 0.05; }).map(function (w) {
        var width = Math.abs(w.weight) / wmax * 50;
        return '<div class="wrow"><span class="lab" title="' + esc(w.label) + '">' + esc(w.label) + '</span><div class="wbar"><i class="' + (w.weight >= 0 ? "pos" : "neg") +
          '" style="width:' + width.toFixed(1) + '%"></i></div><span class="num">' + (w.weight > 0 ? "+" : "") + fmt(w.weight, 2) + "</span></div>";
      }).join("") + '<div class="small muted" style="margin-top:6px">Bias ' + fmt(s.lr_bias, 2) + ". Red pushes toward phishing, green toward safe.</div>";

      var toks = function (list, neg) {
        var m = Math.max.apply(null, list.map(function (t) { return Math.abs(t.llr); }).concat([0.01]));
        return list.slice(0, 12).map(function (t) {
          return '<div class="tok' + (neg ? " neg" : "") + '"><span class="k">' + esc(t.token) + '</span><div class="bar"><i style="width:' +
            Math.round(Math.abs(t.llr) / m * 100) + '%"></i></div><span class="v">' + (t.llr > 0 ? "+" : "") + fmt(t.llr, 2) + "</span></div>";
        }).join("");
      };
      $("topScam").innerHTML = toks(s.top_tokens.scam, false) + '<div class="small muted">LLR = log P(token | scam) - log P(token | safe), Laplace smoothed.</div>';
      $("topHam").innerHTML = toks(s.top_tokens.ham, true) + '<div class="small muted">Vocabulary: ' + d.nb_vocabulary + " features (words, phrases, char n-grams).</div>";
    }).catch(function (e) { $("kpis").textContent = "Could not load stats: " + e.message; });
  }

  /* ---------------- boot ---------------- */
  function boot() {
    initTheme();
    document.querySelectorAll(".tab-btn").forEach(function (b) {
      b.addEventListener("click", function () { showTab(b.getAttribute("data-tab")); });
    });
    $("msg").addEventListener("input", updateCount);
    $("msg").addEventListener("keydown", function (e) { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { analyse(); } });
    $("analyseBtn").addEventListener("click", analyse);
    $("clearBtn").addEventListener("click", function () { setText(""); $("msg").focus(); });
    $("demoBtn").addEventListener("click", function () {
      if (!state.samples.length) { return; }
      var cur = $("msg").value;
      var idx = 0;
      for (var i = 0; i < state.samples.length; i++) { if (state.samples[i].text === cur) { idx = (i + 1) % state.samples.length; } }
      setText(state.samples[idx].text);
      analyse();
    });
    $("bulkDemo").addEventListener("click", function () { $("bulkText").value = state.bulk.join("\n"); });
    $("bulkBtn").addEventListener("click", bulkScan);
    $("bulkTable").addEventListener("click", function (e) {
      var tr = e.target.closest("tr.click");
      if (!tr) { return; }
      setText(tr.getAttribute("data-text"));
      showTab("analyse");
      analyse();
    });
    $("qButtons").addEventListener("click", function (e) {
      var b = e.target.closest("button[data-ans]");
      if (b) { answer(b.getAttribute("data-ans")); }
    });

    api("/api/samples").then(function (s) {
      state.samples = s.samples;
      state.bulk = s.bulk;
      $("chips").innerHTML = s.samples.map(function (x, i) {
        var safe = /safe/i.test(x.label);
        return '<button class="chip ' + (safe ? "safe-chip" : "scam-chip") + '" type="button" data-i="' + i + '">' + esc(x.label) + "</button>";
      }).join("");
      $("chips").addEventListener("click", function (e) {
        var c = e.target.closest(".chip");
        if (!c) { return; }
        setText(state.samples[+c.getAttribute("data-i")].text);
        analyse();
      });
    }).catch(function () { /* server offline */ });
    api("/api/quiz").then(function (q) {
      state.quiz = q.questions;
      if (document.getElementById("tab-quiz").classList.contains("active")) { renderQuestion(); }
    }).catch(function () { /* ignore */ });
  }

  if (document.readyState === "loading") { document.addEventListener("DOMContentLoaded", boot); } else { boot(); }
})();
