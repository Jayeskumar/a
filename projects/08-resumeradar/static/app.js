/* ResumeRadar front-end: vanilla JS, no dependencies, no network calls beyond this server. */
'use strict';
(function () {
  var $ = function (s, el) { return (el || document).querySelector(s); };
  var $$ = function (s, el) { return Array.prototype.slice.call((el || document).querySelectorAll(s)); };
  var ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return ESC[c]; }); }
  function fmt(n, d) { if (n == null || isNaN(n)) return '-'; return Number(n).toFixed(d == null ? 1 : d); }

  var COMP_COLORS = {
    must_have: 'var(--c-must)', nice_to_have: 'var(--c-nice)', semantic: 'var(--c-semantic)',
    experience: 'var(--c-experience)', education: 'var(--c-education)', evidence: 'var(--c-evidence)'
  };
  var COMP_SHORT = { must_have: 'Must-have', nice_to_have: 'Nice-to-have', semantic: 'Context (TF-IDF)',
    experience: 'Experience', education: 'Education', evidence: 'Proven in work' };
  var KIND_ICON = { direct: '✓', alias: '≈', implied: '~', related: '↔', missing: '✕' };
  var REC_SHORT = { strong: 'Shortlist', review: 'Review', low: 'Low match' };

  var S = {
    demo: null, config: null, onto: null, jd: null, jdText: '', jdKey: '', resumes: [], blind: true,
    result: null, sel: null, bias: null, biasToken: 0, detailTab: 'score', coachTab: 'score', coach: null,
    evalLoaded: false, uploadSeq: 0
  };

  // ------------------------------------------------------------------ helpers
  function api(path, body) {
    var opt = body === undefined ? {} : {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
    };
    return fetch(path, opt).then(function (res) {
      return res.json().catch(function () { return null; }).then(function (data) {
        if (!res.ok) throw new Error((data && data.error) || ('HTTP ' + res.status));
        return data;
      });
    });
  }
  var toastTimer = null;
  function toast(msg, err) {
    var t = $('#toast');
    t.textContent = msg;
    t.className = 'show' + (err ? ' err' : '');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.className = ''; }, 2800);
  }
  function busy(btn, on, label) {
    if (!btn) return;
    if (on) { btn.dataset.label = btn.innerHTML; btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> ' + (label || 'Working'); }
    else { btn.disabled = false; if (btn.dataset.label) btn.innerHTML = btn.dataset.label; }
  }
  function readFiles(files) {
    return Promise.all(Array.prototype.map.call(files, function (f) {
      return new Promise(function (resolve) {
        var r = new FileReader();
        r.onload = function () { resolve({ name: f.name.replace(/\.txt$/i, ''), text: String(r.result || '') }); };
        r.onerror = function () { resolve({ name: f.name, text: '' }); };
        r.readAsText(f);
      });
    }));
  }
  function donut(score, size, label) {
    var r = 40, c = 2 * Math.PI * r, v = Math.max(0, Math.min(100, score || 0));
    var col = v >= (S.config ? S.config.shortlist_at : 75) ? 'var(--good)' : (v >= (S.config ? S.config.review_at : 55) ? 'var(--warn)' : 'var(--bad)');
    return '<svg class="donut" viewBox="0 0 100 100" style="width:' + size + 'px;height:' + size + 'px" role="img" aria-label="' + esc(label || 'score') + ' ' + fmt(v) + '">' +
      '<circle cx="50" cy="50" r="' + r + '" fill="none" stroke="var(--border)" stroke-width="10"/>' +
      '<circle cx="50" cy="50" r="' + r + '" fill="none" stroke="' + col + '" stroke-width="10" stroke-linecap="round" ' +
      'stroke-dasharray="' + (c * v / 100).toFixed(1) + ' ' + c.toFixed(1) + '" transform="rotate(-90 50 50)"/>' +
      '<text x="50" y="55" text-anchor="middle" font-size="22">' + fmt(v) + '</text>' +
      (label ? '<text x="50" y="72" text-anchor="middle" font-size="13" style="fill:var(--muted);font-weight:600">' + esc(label) + '</text>' : '') +
      '</svg>';
  }
  function mathSym(t) { return esc(t).replace(/&gt;=/g, '≥').replace(/&lt;=/g, '≤'); }
  function chips(items, cls) {
    return items.map(function (t) { return '<span class="chip ' + (cls || '') + '">' + esc(t) + '</span>'; }).join('');
  }

  // ------------------------------------------------------------------ tabs
  function showView(name) {
    $$('.tab').forEach(function (t) { t.classList.toggle('active', t.dataset.view === name); });
    $$('.view').forEach(function (v) { v.classList.toggle('active', v.id === 'view-' + name); });
    if (name === 'how') drawOnto();
    // first visit to the coach: show a worked example instead of an empty report
    if (name === 'coach' && !S.coach && S.demo && !$('#coach-text').value.trim()) loadSample('R03');
    if (name === 'how' && !S.evalLoaded) runEval();
  }

  // ------------------------------------------------------------------ JD
  function fillJdSelects() {
    var opts = S.demo.jds.map(function (j) { return '<option value="' + esc(j.id) + '">' + esc(j.title) + '</option>'; }).join('');
    $('#jd-select').innerHTML = opts + '<option value="custom">Custom JD...</option>';
    $('#coach-jd').innerHTML = opts + '<option value="current">Same as recruiter screen</option>';
    $('#coach-sample').innerHTML = '<option value="">Choose a sample resume...</option>' + S.demo.resumes.map(function (r) {
      return '<option value="' + esc(r.id) + '">' + esc(r.id + ' - ' + r.archetype) + '</option>';
    }).join('');
  }
  function jdById(id) { return S.demo.jds.filter(function (j) { return j.id === id; })[0]; }

  function setJd(key, text, rescreen) {
    S.jdKey = key;
    S.jdText = text != null ? text : jdById(key).text;
    if ($('#jd-select').value !== key) $('#jd-select').value = key;
    return api('/api/parse-jd', { text: S.jdText }).then(function (jd) {
      S.jd = jd;
      renderJdSummary();
      if (rescreen && S.resumes.length) return runScreen();
    }).catch(function (e) { toast(e.message, true); });
  }

  function renderJdSummary() {
    var jd = S.jd;
    if (!jd) { $('#jd-summary').innerHTML = ''; return; }
    var req = function (id) { return jd.requirements.filter(function (r) { return r.id === id; })[0]; };
    var must = jd.must.map(req).sort(function (a, b) { return b.weight - a.weight; });
    var nice = jd.nice.map(req);
    var edu = jd.education || {};
    var eduTxt = edu.level ? edu.label + (edu.fields && edu.fields.length && !edu.any_field ? ' · ' + edu.fields.join(', ') : '') +
      (edu.any_field ? ' · any field' : (edu.related_ok ? ' (or related)' : '')) : (edu.equivalent_ok ? 'Degree or equivalent experience' : 'Not required');
    var h = '<div class="jd-top"><h2>' + esc(jd.title) + '</h2><div class="jd-meta">' +
      '<span>Experience <b>' + (jd.min_years ? fmt(jd.min_years, 0) + '+ yrs' : 'no minimum') + '</b></span>' +
      '<span>Degree <b>' + esc(eduTxt) + '</b></span>' +
      '<span>Parsed <b>' + jd.must.length + ' must-have · ' + jd.nice.length + ' nice-to-have</b></span></div></div>';
    h += '<div class="jd-rows"><div class="chips"><span class="lbl">Must-have</span>' + must.map(function (r) {
      return '<span class="chip must' + (r.core ? ' core' : '') + '" title="' + esc('weight x' + r.weight + ' · from: ' + r.line) + '">' + esc(r.label) + (r.weight > 1 && !r.core ? ' x' + r.weight : '') + '</span>';
    }).join('') + '</div>';
    if (nice.length) h += '<div class="chips"><span class="lbl">Nice-to-have</span>' + nice.map(function (r) {
      return '<span class="chip nice" title="' + esc('from: ' + r.line) + '">' + esc(r.label) + '</span>'; }).join('') + '</div>';
    if (jd.soft_names && jd.soft_names.length) h += '<div class="chips"><span class="lbl">Soft skills</span>' + chips(jd.soft_names, 'soft') +
      '<span class="muted">&nbsp;judged in interview, never scored from keywords</span></div>';
    h += '</div>';
    if (jd.bias_flags && jd.bias_flags.length) {
      h += '<div class="bias-lint"><span class="chip flag">⚠ JD bias lint</span><div class="lint-list">' + jd.bias_flags.map(function (f) {
        return '<div><b>' + esc(f.category) + '</b>: "' + esc(f.match) + '" - ' + esc(f.suggestion) + '</div>';
      }).join('') + '</div></div>';
    }
    $('#jd-summary').innerHTML = h;
  }

  // ------------------------------------------------------------------ screening
  function loadDemo() {
    var btn = $('#btn-demo');
    busy(btn, true, 'Loading');
    S.resumes = S.demo.resumes.map(function (r) { return { id: r.id, name: r.name, text: r.text, archetype: r.archetype }; });
    S.sel = null;
    S.blind = true;
    $('#blind-toggle').checked = true;
    return setJd(S.demo.jds[0].id, null, false).then(runScreen).then(function () {
      busy(btn, false);
    }, function () { busy(btn, false); });
  }

  function runScreen() {
    if (!S.resumes.length) { toast('Load demo data or add resumes first'); renderAll(); return Promise.resolve(); }
    var btn = $('#btn-screen');
    busy(btn, true, 'Screening');
    var body = { jd: S.jdText, blind: S.blind, resumes: S.resumes.map(function (r) { return { id: r.id, name: r.name, text: r.text }; }) };
    return api('/api/screen', body).then(function (res) {
      S.result = res;
      if (!S.sel || !res.ranking.some(function (r) { return r.id === S.sel; })) S.sel = res.ranking[0].id;
      busy(btn, false);
      renderAll();
      runBias();
    }).catch(function (e) { busy(btn, false); toast(e.message, true); });
  }

  function runBias() {
    var token = ++S.biasToken;
    S.bias = null;
    renderBias(true);
    var body = { jd: S.jdText, resumes: S.resumes.map(function (r) { return { id: r.id, name: r.name, text: r.text }; }) };
    return api('/api/bias-check', body).then(function (b) {
      if (token !== S.biasToken) return;
      S.bias = b;
      renderBias(false);
      renderKpis();
    }).catch(function (e) { if (token === S.biasToken) { renderBias(false, e.message); } });
  }

  function renderAll() {
    renderKpis();
    renderTable();
    renderDetail($('#detail'), selected(), 'screen');
    renderResumeList();
    if (!S.result) renderBias(false);
  }
  function selected() {
    if (!S.result) return null;
    return S.result.ranking.filter(function (r) { return r.id === S.sel; })[0] || null;
  }
  function displayName(id) {
    if (!S.result) return id;
    var r = S.result.ranking.filter(function (x) { return x.id === id; })[0];
    return r ? r.display_name : id;
  }

  function renderKpis() {
    var el = $('#kpis');
    var res = S.result;
    if (!res) {
      el.innerHTML = kpi('0', 'Candidates') + kpi('-', 'Shortlist (≥' + (S.config ? S.config.shortlist_at : 75) + ')') +
        kpi('-', 'Human review') + kpi('-', 'Average score') + kpi('-', 'Screening time') + kpi('-', 'Bias check');
      return;
    }
    var rk = res.ranking;
    var shortl = rk.filter(function (r) { return r.summary.recommendation.level === 'strong'; }).length;
    var review = rk.filter(function (r) { return r.summary.recommendation.level === 'review'; }).length;
    var avg = rk.reduce(function (a, r) { return a + r.score; }, 0) / rk.length;
    var biasTxt = '<span class="spinner"></span>', biasCls = '';
    if (S.bias) {
      var mode = S.blind ? S.bias.blind : S.bias.standard;
      biasTxt = mode.invariant ? 'Identical' : ('Δ ' + fmt(Math.max(mode.vs_swapped.max_abs_delta, mode.vs_stripped.max_abs_delta), 1));
      biasCls = mode.invariant ? 'good' : '';
    }
    el.innerHTML = kpi(rk.length, 'Candidates screened') + kpi(shortl, 'Shortlist (≥' + S.config.shortlist_at + ')', 'good') +
      kpi(review, 'Human review') + kpi(fmt(avg), 'Average match score') +
      kpi(fmt(res.elapsed_ms, 0) + ' ms', 'Screening time (' + (res.blind ? 'blind' : 'standard') + ')', 'accent') +
      kpi(biasTxt, S.blind ? 'Bias check: identity swap' : 'Bias check (standard mode)', biasCls);
  }
  function kpi(v, l, cls) { return '<div class="kpi ' + (cls || '') + '"><div class="v">' + v + '</div><div class="l">' + esc(l) + '</div></div>'; }

  function scoreBar(rep) {
    return '<div class="scorebar" aria-hidden="true">' + rep.match.breakdown.map(function (b) {
      return '<span style="width:' + Math.max(0, b.points).toFixed(2) + '%;background:' + COMP_COLORS[b.key] + '" title="' + esc(b.label + ': ' + fmt(b.points) + ' pts') + '"></span>';
    }).join('') + '</div>';
  }

  function renderTable() {
    var el = $('#ranking');
    var res = S.result;
    if (!res) {
      el.innerHTML = '<div class="empty"><b>No candidates yet.</b><br>Screen 20 synthetic resumes against a real-looking JD in one click.<br>' +
        '<button class="btn primary" type="button" id="btn-demo-empty">&#9654; Load demo data</button></div>';
      $('#rank-meta').textContent = '';
      $('#legend').innerHTML = '';
      var b = $('#btn-demo-empty');
      if (b) b.addEventListener('click', loadDemo);
      return;
    }
    $('#rank-meta').textContent = res.count + ' resumes · ' + (res.blind ? 'blind mode: identity masked before scoring' : 'standard mode: identity visible');
    var h = '<table><thead><tr><th>#</th><th>Candidate</th><th>Match score</th><th>Must-have</th><th class="hide-sm">Exp.</th><th class="hide-sm">ATS</th><th class="hide-sm">Signals</th></tr></thead><tbody>';
    res.ranking.forEach(function (r) {
      var s = r.summary, rec = s.recommendation.level;
      var flags = s.flags.map(function (f) {
        var t = { alias: '≈ synonyms', stuffing: '⚠ stuffing', dates: 'no dates', jd: 'thin JD' }[f] || f;
        return '<span class="flagicon ' + esc(f) + '">' + esc(t) + '</span>';
      }).join('');
      h += '<tr data-id="' + esc(r.id) + '" tabindex="0"' + (r.id === S.sel ? ' class="sel"' : '') + '>' +
        '<td class="rank">' + r.rank + '</td>' +
        '<td class="cand">' + esc(r.display_name) + '<small><span class="pill ' + rec + '">' + REC_SHORT[rec] + '</span></small></td>' +
        '<td class="scorecell"><span class="num">' + fmt(r.score) + '</span>' + scoreBar(r) + '</td>' +
        '<td class="mustcell"><span class="nw"><span class="num">' + s.must_met + '</span>/' + s.must_total + (s.must_partial ? ' <span class="muted">+' + s.must_partial + ' partial</span>' : '') + '</span>' +
        (s.top_missing.length ? '<span class="muted miss-line">' + esc('missing ' + s.top_missing.slice(0, 2).join(', ')) + '</span>' : '') + '</td>' +
        '<td class="hide-sm">' + fmt(s.years) + 'y</td>' +
        '<td class="hide-sm">' + fmt(s.ats, 0) + '</td>' +
        '<td class="hide-sm">' + (flags || '<span class="muted">-</span>') + '</td></tr>';
    });
    el.innerHTML = h + '</tbody></table>';
    $$('tbody tr', el).forEach(function (tr) {
      var pick = function () {
        S.sel = tr.dataset.id; $$('tbody tr', el).forEach(function (x) { x.classList.toggle('sel', x === tr); }); renderDetail($('#detail'), selected(), 'screen');
        // single-column layout: the explanation sits below the table, so bring it into view
        if (window.innerWidth <= 1180) $('#detail').scrollIntoView({ behavior: 'smooth', block: 'start' });
      };
      tr.addEventListener('click', pick);
      tr.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(); } });
    });
    var lg = '';
    Object.keys(COMP_COLORS).forEach(function (k) {
      if (S.config && S.config.weights[k] != null) lg += '<span><i style="background:' + COMP_COLORS[k] + '"></i>' + esc(COMP_SHORT[k]) + ' ' + Math.round(S.config.weights[k] * 100) + '%</span>';
    });
    $('#legend').innerHTML = lg + '<span>≈ matched via synonym a keyword ATS would miss</span>';
  }

  // ------------------------------------------------------------------ detail panel
  function renderDetail(el, rep, where) {
    if (!rep) {
      el.innerHTML = where === 'coach'
        ? '<div class="empty"><b>Your personal report appears here.</b><br>Match score with reasons, missing skills, a learning plan, bullet rewrites, ATS check and interview questions.<br><button class="btn primary" type="button" id="btn-coach-sample">Try a sample resume</button></div>'
        : '<div class="empty"><b>Select a candidate</b><br>to see why they scored what they did.</div>';
      var b = $('#btn-coach-sample', el);
      if (b) b.addEventListener('click', function () { loadSample('R03'); });
      return;
    }
    var tabKey = where === 'coach' ? 'coachTab' : 'detailTab';
    var tabs = [['score', 'Why this score'], ['gaps', 'Gaps & plan'], ['tips', 'Bullets'], ['ats', 'ATS'], ['interview', 'Interview']];
    if (rep.blind) tabs.push(['blind', 'Blind view']);
    if (!tabs.some(function (t) { return t[0] === S[tabKey]; })) S[tabKey] = 'score';
    var m = rep.match, rec = m.recommendation;
    var name = where === 'coach' ? 'Your resume' : rep.display_name;
    var h = '<div class="d-head">' + donut(rep.score, 92, 'match') + '<div><h2>' + esc(name) + '</h2>' +
      '<div style="margin:4px 0"><span class="pill ' + rec.level + '">' + esc(rec.label) + '</span> <span class="muted">rule: ' + mathSym(rec.rule) + '</span></div>' +
      '<div class="muted">' + esc(oneLiner(rep)) + '</div></div></div>';
    h += '<div class="subtabs" role="tablist">' + tabs.map(function (t) {
      return '<button class="subtab' + (S[tabKey] === t[0] ? ' active' : '') + '" data-t="' + t[0] + '" type="button">' + esc(t[1]) + '</button>';
    }).join('') + '</div><div class="d-body">' + body(rep, S[tabKey]) + '</div>';
    el.innerHTML = h;
    $$('.subtab', el).forEach(function (b) {
      b.addEventListener('click', function () { S[tabKey] = b.dataset.t; renderDetail(el, rep, where); });
    });
  }

  function oneLiner(rep) {
    var m = rep.match;
    var met = m.must.filter(function (r) { return r.credit >= 1; }).length;
    var parts = [met + '/' + m.must.length + ' must-haves'];
    parts.push(fmt(m.experience.relevant_years) + ' relevant yrs');
    parts.push('ATS ' + fmt(rep.ats.score, 0));
    if (rep.profile.education.degree) parts.push(rep.profile.education.degree);
    return parts.join(' · ');
  }

  function body(rep, tab) {
    if (tab === 'gaps') return gapsBody(rep);
    if (tab === 'tips') return tipsBody(rep);
    if (tab === 'ats') return atsBody(rep);
    if (tab === 'interview') return interviewBody(rep);
    if (tab === 'blind') return blindBody(rep);
    return scoreBody(rep);
  }

  function reqRows(list) {
    return list.map(function (r) {
      var how = { direct: 'exact match', alias: 'synonym "' + (r.via || '') + '"', implied: 'implied by ' + r.via,
        related: 'related: ' + r.via, missing: 'not found' }[r.kind];
      if ((r.kind === 'direct' || r.kind === 'alias') && !r.evidence) how += ' · listed only';
      return '<tr><td><span class="st ' + r.kind + '" title="' + esc(r.kind) + '">' + KIND_ICON[r.kind] + '</span></td>' +
        '<td><b>' + esc(r.label) + '</b>' + (r.weight > 1 ? ' <span class="muted">x' + r.weight + '</span>' : '') + '</td>' +
        '<td class="muted">' + esc(how) + '</td><td class="num">' + fmt(r.credit, 1) + '</td></tr>';
    }).join('');
  }

  function scoreBody(rep) {
    var m = rep.match;
    var h = '<div class="bd">';
    m.breakdown.forEach(function (b) {
      h += '<div class="bd-row"><span class="bd-label">' + esc(b.label) + '</span>' +
        '<div class="bd-track"><div class="bd-fill" style="width:' + (b.score * 100).toFixed(1) + '%;background:' + COMP_COLORS[b.key] + '"></div></div>' +
        '<span class="bd-pts">' + fmt(b.points) + '/' + fmt(b.max_points, 0) + '</span>' +
        '<span class="bd-detail">' + esc(b.detail) + '</span></div>';
    });
    (m.not_scored || []).forEach(function (n) { h += '<div class="bd-off">' + esc(n.label) + ': not scored - ' + esc(n.reason) + '</div>'; });
    h += '</div><div class="callout">Score = Σ weight × component × 100, weights renormalised over the components that apply. ' +
      'Total <b>' + fmt(rep.score) + '</b>. Nobody is auto-rejected; a human decides.</div>';
    m.flags.forEach(function (f) {
      h += '<div class="callout ' + (f.type === 'stuffing' ? 'bad' : (f.type === 'alias' ? 'accent' : 'warn')) + '">' + esc(f.text) + '</div>';
    });
    h += '<h3>Must-have requirements</h3><table class="reqs"><tbody>' + reqRows(m.must) + '</tbody></table>';
    if (m.nice.length) h += '<h3>Nice-to-have</h3><table class="reqs"><tbody>' + reqRows(m.nice) + '</tbody></table>';
    if (m.semantic.shared_terms.length) h += '<h3>Top shared TF-IDF terms (cosine ' + fmt(m.semantic.cosine, 3) + ')</h3><div class="chips">' +
      m.semantic.shared_terms.map(function (t) { return '<span class="chip" title="contribution ' + t[1] + '">' + esc(t[0]) + '</span>'; }).join('') + '</div>';
    if (m.extra_skills.length) h += '<h3>Other skills found</h3><div class="chips">' + chips(m.extra_skills.map(function (s) { return s.name; })) + '</div>';
    return h;
  }

  function gapsBody(rep) {
    var g = rep.gaps;
    var h = '';
    if (!g.missing_must.length && !g.partial_must.length) h += '<div class="callout good">Every must-have requirement is met.</div>';
    if (g.missing_must.length) h += '<h3>Missing must-haves</h3><div class="chips">' + chips(g.missing_must, 'miss') + '</div>';
    if (g.partial_must.length) h += '<h3>Partly covered</h3><div class="chips">' + g.partial_must.map(function (p) {
      return '<span class="chip part" title="credit ' + p.credit + '">' + esc(p.label + ' (' + p.kind + ': ' + p.via + ')') + '</span>'; }).join('') + '</div>';
    if (g.missing_nice.length) h += '<h3>Missing nice-to-haves</h3><div class="chips">' + chips(g.missing_nice, '') + '</div>';
    if (g.advice.length) h += '<h3>Quick wins</h3><ul class="clean">' + g.advice.map(function (a) { return '<li>• ' + esc(a) + '</li>'; }).join('') + '</ul>';
    var p = g.learning_path;
    if (p.steps.length) {
      h += '<h3>Learning path - ' + fmt(p.total_hours, 0) + ' h ≈ ' + p.weeks + ' weeks at ' + p.hours_per_week + ' h/week (approx.)</h3>' +
        '<div class="muted" style="margin-bottom:8px">' + esc(p.method) + '</div><div class="path">';
      p.steps.forEach(function (s) {
        h += '<div class="step' + (s.is_target ? '' : ' pre') + '" data-n="' + s.step + '"><b>' + esc(s.name) + '</b> ' +
          '<span class="meta">' + esc(s.category) + ' · ~' + fmt(s.hours, 0) + ' h · by week ' + s.week + ' · ' + esc(s.why) +
          (s.requires.length ? ' · after ' + esc(s.requires.join(', ')) : '') + '</span>' +
          '<div class="practice">' + esc(s.practice) + '</div></div>';
      });
      h += '</div>';
    } else {
      h += '<div class="callout good">No study plan needed for this job.</div>';
    }
    return h;
  }

  function tipsBody(rep) {
    var b = rep.gaps.bullets;
    if (!b.count) return '<div class="callout warn">No achievement bullets found. Add 3-5 bullets per role or project: action verb + what + measurable result.</div>';
    var h = '<div class="chips" style="margin-bottom:8px"><span class="chip">' + b.count + ' bullets</span><span class="chip">avg quality ' + fmt(b.avg_score, 0) + '/100</span>' +
      '<span class="chip">' + fmt(b.action_pct, 0) + '% start with a verb</span><span class="chip">' + fmt(b.quantified_pct, 0) + '% quantified</span></div>';
    if (!b.weakest.length) h += '<div class="callout good">Every bullet has an action verb and a number. Nice.</div>';
    b.weakest.forEach(function (x) {
      h += '<div class="bullet"><span class="bscore" style="color:' + (x.score >= 75 ? 'var(--good)' : x.score >= 45 ? 'var(--warn)' : 'var(--bad)') + '">' + x.score + '/100</span>' +
        '<div class="orig">' + esc(x.text) + '</div><div class="issues">' + chips(x.issues, 'part') + '</div>' +
        (x.rewrite ? '<div class="rw">' + esc(x.rewrite) + '</div>' : '') + '</div>';
    });
    if (b.strongest) h += '<h3>Your strongest bullet</h3><div class="callout good">' + esc(b.strongest.text) + '</div>';
    return h;
  }

  function atsBody(rep) {
    var a = rep.ats;
    var h = '<div class="d-head">' + donut(a.score, 88, 'ATS') + '<div><b>' + esc(a.grade) + '</b><div class="muted">' + fmt(a.points, a.points % 1 ? 1 : 0) + ' of ' + a.max_points +
      ' points from ' + a.checks.length + ' rule checks. Scored on the resume as submitted.</div></div></div><div class="checks">';
    a.checks.forEach(function (c) {
      var ic = { pass: '✓', warn: '!', fail: '✕' }[c.status];
      h += '<div class="check"><span class="ic ' + c.status + '">' + ic + '</span><div><b>' + esc(c.label) + '</b> - ' + esc(c.message) +
        (c.fix ? '<div class="fix">Fix: ' + esc(c.fix) + '</div>' : '') + '</div><span class="pts">' + fmt(c.points, c.points % 1 ? 1 : 0) + '/' + c.max + '</span></div>';
    });
    return h + '</div>';
  }

  function interviewBody(rep) {
    var qs = rep.interview;
    if (!qs.length) return '<p class="muted">No questions generated.</p>';
    var label = { 'deep-dive': 'Deep-dive on skills you claim', gap: 'Gaps - prepare these fundamentals', 'nice-to-have': 'Stand-out topics',
      project: 'About your projects', behavioural: 'Behavioural' };
    var h = '', last = '';
    qs.forEach(function (q) {
      if (q.type !== last) { h += '<h3>' + esc(label[q.type] || q.type) + '</h3>'; last = q.type; }
      h += '<div class="q"><div class="qt">' + esc(q.question) + '</div><div class="qm"><span class="diff ' + esc(q.difficulty) + '">' + esc(q.difficulty) + '</span>' +
        (q.skill ? esc(q.skill) + ' · ' : '') + esc(q.why) + '</div></div>';
    });
    return h;
  }

  function blindBody(rep) {
    var r = rep.redactions;
    if (!r) return '<p class="muted">Blind mode is off.</p>';
    var counts = Object.keys(r.counts).map(function (k) {
      var item = r.items.filter(function (i) { return i.kind === k; })[0];
      return '<span class="chip">' + esc((item ? item.label : k) + ' ×' + r.counts[k]) + '</span>';
    }).join('');
    var txt = esc(rep.masked_text || '').replace(/\[(CANDIDATE|CONTACT|GENDER|AGE|PHOTO REMOVED|INSTITUTION|LOCATION|REDACTED|YEAR)\]/g, '<mark class="red">[$1]</mark>');
    return '<div class="callout accent">' + r.total + ' identity fields hidden before scoring. The model never saw them, so they cannot change the score.</div>' +
      '<div class="chips" style="margin-bottom:8px">' + counts + '</div><pre class="masked">' + txt + '</pre>';
  }

  // ------------------------------------------------------------------ bias card
  function biasChart(rows, key, good) {
    var w = 340, h = 104, mid = h / 2, n = rows.length, L = 40;
    var maxAbs = 1.5;
    rows.forEach(function (r) { maxAbs = Math.max(maxAbs, Math.abs(r[key] - r.score)); });
    var bw = Math.max(3, (w - L - 2) / Math.max(1, n) - 3);
    var s = '<svg class="bias-chart" viewBox="0 0 ' + w + ' ' + h + '" role="img" aria-label="score change per candidate after identity swap">';
    s += '<line x1="' + (L - 4) + '" x2="' + w + '" y1="' + mid + '" y2="' + mid + '" stroke="var(--border)" stroke-width="1"/>';
    s += '<text x="' + (L - 6) + '" y="13" text-anchor="end">+' + fmt(maxAbs, 1) + '</text><text x="' + (L - 6) + '" y="' + (mid + 4) + '" text-anchor="end">0</text><text x="' + (L - 6) + '" y="' + (h - 3) + '" text-anchor="end">-' + fmt(maxAbs, 1) + '</text>' +
      '<text x="' + w + '" y="13" text-anchor="end">Δ score (pts)</text>';
    rows.forEach(function (r, i) {
      var d = r[key] - r.score;
      var x = L + i * (bw + 3);
      var bh = Math.abs(d) / maxAbs * (mid - 6);
      if (Math.abs(d) < 1e-9) {
        s += '<rect x="' + x.toFixed(1) + '" y="' + (mid - 1.5) + '" width="' + bw.toFixed(1) + '" height="3" rx="1.5" fill="var(--good)"><title>' + esc(displayName(r.id)) + ': 0.00</title></rect>';
      } else {
        s += '<rect x="' + x.toFixed(1) + '" y="' + (d > 0 ? mid - bh : mid).toFixed(1) + '" width="' + bw.toFixed(1) + '" height="' + Math.max(1.5, bh).toFixed(1) +
          '" rx="1.5" fill="' + (good ? 'var(--good)' : 'var(--warn)') + '"><title>' + esc(displayName(r.id) + ': ' + (d > 0 ? '+' : '') + d.toFixed(2)) + '</title></rect>';
      }
    });
    return s + '</svg>';
  }

  function biasBox(mode, data, isBlind) {
    var sw = data.vs_swapped, st = data.vs_stripped;
    var maxd = Math.max(sw.max_abs_delta, st.max_abs_delta);
    var changes = Math.max(sw.rank_changes, st.rank_changes);
    return '<div class="bias-box' + (isBlind ? ' blind' : '') + '"><h4>' + esc(mode) + (data.invariant ? '<span class="pill strong">identical ranking</span>' : '<span class="pill review">ranking shifts</span>') + '</h4>' +
      '<div class="big ' + (data.invariant ? 'good' : 'warn') + '">max Δ ' + fmt(maxd, 2) + ' pts</div>' +
      '<div class="sub">Spearman ρ ' + fmt(Math.min(sw.spearman, st.spearman), 3) + ' · ' + changes + ' rank change' + (changes === 1 ? '' : 's') +
      ' · top-5 ' + (sw.top_k_identical && st.top_k_identical ? 'identical' : 'changed') + '</div>' +
      biasChart(data.rows, 'swapped', isBlind) + '<div class="sub">Bars: score change per candidate after swapping gender, name, college tier, age and city.</div></div>';
  }

  function renderBias(loading, err) {
    var el = $('#bias-card');
    var head = '<div class="card-head"><h2>Bias check</h2><span class="muted">each resume scored as submitted, with identity deleted, and with identity swapped</span></div>';
    if (!S.result) { el.innerHTML = head + '<p class="muted">Runs automatically after screening.</p>'; return; }
    if (loading) { el.innerHTML = head + '<p class="muted"><span class="spinner"></span> Re-scoring every resume three ways in both modes...</p>'; return; }
    if (err || !S.bias) { el.innerHTML = head + '<p class="muted">Bias check unavailable' + (err ? ': ' + esc(err) : '') + '</p>'; return; }
    var b = S.bias;
    el.innerHTML = head + '<div class="bias-grid">' + biasBox('Blind mode (ResumeRadar default)', b.blind, true) +
      biasBox('Standard mode (identity visible)', b.standard, false) + '</div>' +
      '<p class="muted" style="margin:8px 0 0">' + esc(b.explanation) + ' Checked in ' + fmt(b.elapsed_ms, 0) + ' ms.</p>';
  }

  // ------------------------------------------------------------------ resume list
  function renderResumeList() {
    var el = $('#resume-list-card');
    var h = '<div class="card-head"><h2>Resumes in this batch (' + S.resumes.length + ')</h2>' +
      (S.resumes.length ? '<button class="btn ghost small" id="btn-clear" type="button">Clear all</button>' : '') + '</div>';
    if (!S.resumes.length) { el.innerHTML = h + '<p class="muted">Load the demo set, upload .txt files or paste resumes.</p>'; return; }
    h += '<div class="rlist">' + S.resumes.map(function (r) {
      var label = S.blind ? displayName(r.id) : r.name;
      return '<div class="ritem" title="' + esc(r.archetype || r.name) + '"><span><b>' + esc(r.id) + '</b> ' + esc(r.archetype || label) + '</span>' +
        '<button type="button" data-rm="' + esc(r.id) + '" aria-label="Remove ' + esc(r.id) + '">×</button></div>';
    }).join('') + '</div><p class="muted" style="margin:8px 0 0">Archetype labels are shown here for the demo only; the scorer never sees them.</p>';
    el.innerHTML = h;
    $$('[data-rm]', el).forEach(function (b) {
      b.addEventListener('click', function () {
        S.resumes = S.resumes.filter(function (r) { return r.id !== b.dataset.rm; });
        if (!S.resumes.length) { S.result = null; S.bias = null; renderAll(); return; }
        runScreen();
      });
    });
    var c = $('#btn-clear', el);
    if (c) c.addEventListener('click', function () { S.resumes = []; S.result = null; S.bias = null; S.sel = null; renderAll(); });
  }

  function addResumes(list) {
    var added = 0;
    list.forEach(function (r) {
      if (!r.text || r.text.trim().length < 20) return;
      S.uploadSeq += 1;
      S.resumes.push({ id: 'U' + String(S.uploadSeq).padStart(2, '0'), name: r.name || ('Upload ' + S.uploadSeq), text: r.text, archetype: r.name || 'uploaded' });
      added += 1;
    });
    if (!added) { toast('No usable text found (min 20 characters)', true); return Promise.resolve(); }
    toast('Added ' + added + ' resume' + (added > 1 ? 's' : ''));
    return runScreen();
  }

  // ------------------------------------------------------------------ coach
  function loadSample(id) {
    var r = S.demo.resumes.filter(function (x) { return x.id === id; })[0];
    if (!r) return;
    $('#coach-text').value = r.text;
    $('#coach-sample').value = id;
    var jdIdx = { R01: 0, R02: 0, R03: 0, R04: 0, R05: 0, R06: 0, R07: 0, R08: 1, R09: 1, R10: 1, R11: 1, R12: 1, R13: 1 }[id];
    $('#coach-jd').value = S.demo.jds[jdIdx == null ? 2 : jdIdx].id;
    runCoach();
  }
  function runCoach() {
    var text = $('#coach-text').value;
    if (text.trim().length < 20) { toast('Paste your resume (at least a few lines) or pick a sample', true); return; }
    var key = $('#coach-jd').value;
    var jdText = key === 'current' ? S.jdText : jdById(key).text;
    var btn = $('#btn-coach');
    busy(btn, true, 'Analysing');
    api('/api/match', { resume: text, jd: jdText, blind: $('#coach-blind').checked }).then(function (rep) {
      busy(btn, false);
      S.coach = rep;
      renderDetail($('#coach-detail'), rep, 'coach');
    }).catch(function (e) { busy(btn, false); toast(e.message, true); });
  }

  // ------------------------------------------------------------------ how it works
  function renderHowStatic() {
    var steps = [
      ['1. Blind mask', 'Name, pronouns, college, age, photo, city, contact replaced by placeholders'],
      ['2. Parse', 'Sections, dated roles, degree, projects, certifications, bullets'],
      ['3. Skill ontology', S.onto.stats.skills + ' skills, ' + S.onto.stats.aliases + ' aliases, longest-match + case rules'],
      ['4. Match', 'Must/nice credit (exact, synonym, implied, related) + TF-IDF cosine + experience'],
      ['5. Explain', 'Weighted breakdown, evidence, flags, recommendation band'],
      ['6. Coach', 'Topological learning path, bullet rewrites, ATS checks, interview questions']
    ];
    $('#pipeline').innerHTML = steps.map(function (s) { return '<div class="pstep"><b>' + esc(s[0]) + '</b><span>' + esc(s[1]) + '</span></div>'; }).join('');
    var c = S.config;
    var rows = Object.keys(c.weights).map(function (k) {
      return '<tr><td><i style="display:inline-block;width:10px;height:10px;border-radius:3px;background:' + COMP_COLORS[k] + ';margin-right:6px"></i>' + esc(c.labels[k]) + '</td><td class="num">' + Math.round(c.weights[k] * 100) + '%</td></tr>';
    }).join('');
    $('#weights').innerHTML = '<table class="wtable"><thead><tr><th>Component</th><th>Weight</th></tr></thead><tbody>' + rows + '</tbody></table>' +
      '<ul class="clean" style="margin-top:10px">' +
      '<li>≈ synonym (JS = JavaScript): full credit 1.0</li>' +
      '<li>~ implied by a skill that requires it (Django ⇒ Python): ' + c.implied_credit_direct + ' direct, ' + c.implied_credit_indirect + ' further away</li>' +
      '<li>↔ related skill in the same family (Flask ↔ Django): ' + c.related_credit + '</li>' +
      '<li>Skill in the job title counts x' + c.title_skill_weight + '; "strong/expert" lines x' + c.strong_cue_weight + '</li>' +
      '<li>TF-IDF cosine reaches full credit at ' + c.semantic_cos_full + '; internships count x' + c.internship_weight + '</li>' +
      '<li>Bands: shortlist ≥ ' + c.shortlist_at + ', human review ≥ ' + c.review_at + '. Soft skills are never scored.</li></ul>';
    drawOnto();
    $('#onto-meta').textContent = S.onto.stats.skills + ' skills · ' + S.onto.stats.prerequisite_edges + ' prerequisite edges · ' +
      S.onto.questions.questions + ' interview questions';
    searchOnto('');
  }
  function drawOnto() {
    if (!S.onto) return;
    var cats = S.onto.stats.by_category;
    var keys = Object.keys(cats).sort(function (a, b) { return cats[b] - cats[a]; });
    var max = Math.max.apply(null, keys.map(function (k) { return cats[k]; }));
    var cw = $('#onto-chart').clientWidth;
    var bh = 20, w = cw > 200 ? cw : 520, lw = 130;
    var svg = '<svg viewBox="0 0 ' + w + ' ' + (keys.length * bh + 4) + '" role="img" aria-label="skills per category">';
    keys.forEach(function (k, i) {
      var bw = (w - lw - 40) * cats[k] / max;
      svg += '<text x="' + (lw - 6) + '" y="' + (i * bh + 14) + '" text-anchor="end" font-size="12.5" fill="var(--muted)">' + esc(k) + '</text>' +
        '<rect x="' + lw + '" y="' + (i * bh + 4) + '" width="' + bw.toFixed(1) + '" height="' + (bh - 7) + '" rx="3" fill="var(--accent)" opacity="' + (0.45 + 0.55 * cats[k] / max).toFixed(2) + '"/>' +
        '<text x="' + (lw + bw + 5).toFixed(1) + '" y="' + (i * bh + 14) + '" font-size="12.5" font-weight="600" fill="var(--text)">' + cats[k] + '</text>';
    });
    $('#onto-chart').innerHTML = svg + '</svg>';
    $('#onto-chart').className = 'onto-chart';
  }
  function searchOnto(q) {
    q = (q || '').trim().toLowerCase();
    var list = S.onto.skills.filter(function (s) {
      return !q || s.name.toLowerCase().indexOf(q) >= 0 || s.aliases.some(function (a) { return a.toLowerCase().indexOf(q) >= 0; });
    }).slice(0, q ? 60 : 40);
    $('#onto-results').innerHTML = list.map(function (s) {
      var tip = s.category + (s.aliases.length ? ' · aliases: ' + s.aliases.join(', ') : '') + (s.prereqs.length ? ' · requires: ' + s.prereqs.join(', ') : '');
      return '<span class="chip" title="' + esc(tip) + '">' + esc(s.name) + (q && s.aliases.length ? ' <span class="muted">(' + esc(s.aliases.slice(0, 3).join(', ')) + ')</span>' : '') + '</span>';
    }).join('') || '<span class="muted">No match</span>';
  }

  function runEval() {
    var btn = $('#btn-eval');
    busy(btn, true, 'Evaluating');
    $('#eval').innerHTML = '<p class="muted"><span class="spinner"></span> Scoring 20 resumes x 3 JDs, 3 systems, bias checks and a 100-resume latency run...</p>';
    api('/api/eval').then(function (r) {
      S.evalLoaded = true;
      busy(btn, false);
      renderEval(r);
    }).catch(function (e) { busy(btn, false); $('#eval').innerHTML = '<p class="muted">Evaluation failed: ' + esc(e.message) + '</p>'; });
  }

  function renderEval(r) {
    var m = r.mean, ex = r.extraction, lat = r.latency;
    var h = '<div class="eval-grid">' +
      kpi(fmt(m.resumeradar.spearman, 2), 'Spearman vs hand labels (keyword ATS ' + fmt(m.keyword_ats.spearman, 2) + ')', 'accent') +
      kpi(fmt(m.resumeradar['ndcg@5'], 2), 'NDCG@5 (keyword ATS ' + fmt(m.keyword_ats['ndcg@5'], 2) + ')', 'accent') +
      kpi(fmt(ex.resumeradar.f1, 2), 'Skill-extraction F1 (keyword ' + fmt(ex.keyword_baseline.f1, 2) + ')', 'good') +
      kpi(lat ? fmt(lat.full_reports_ms, 0) + ' ms' : '-', lat ? 'Full reports for ' + lat.resumes + ' resumes' : 'Latency', '') + '</div>';
    h += '<h3>Ranking agreement per job (20 resumes, hand-labelled 0-3)</h3><div class="table-wrap"><table class="metrics"><thead><tr><th>Job</th><th>System</th><th>Spearman <span class="nocase">ρ</span></th><th>NDCG@5</th><th>Top-5 overlap</th></tr></thead><tbody>';
    Object.keys(r.rankings).forEach(function (jid) {
      var row = r.rankings[jid];
      var sys = [['resumeradar', 'ResumeRadar'], ['keyword_ats', 'Keyword ATS (literal)'], ['plain_tfidf', 'Plain TF-IDF']];
      var best = {};
      ['spearman', 'ndcg@5', 'top5_overlap'].forEach(function (k) { best[k] = Math.max.apply(null, sys.map(function (s) { return row[s[0]][k]; })); });
      sys.forEach(function (s, i) {
        var v = row[s[0]];
        h += '<tr>' + (i === 0 ? '<td rowspan="3"><b>' + esc(row.title) + '</b></td>' : '') + '<td>' + esc(s[1]) + '</td>' +
          ['spearman', 'ndcg@5', 'top5_overlap'].map(function (k) { return '<td class="num' + (v[k] === best[k] ? ' best' : '') + '">' + fmt(v[k], 3) + '</td>'; }).join('') + '</tr>';
      });
    });
    h += '</tbody></table></div>';
    h += '<h3>Where wording matters</h3><div class="table-wrap"><table class="metrics"><thead><tr><th>Resume</th><th>Hand label</th><th>ResumeRadar rank</th><th>Keyword ATS rank</th><th>Plain TF-IDF rank</th></tr></thead><tbody>' +
      r.case_studies.map(function (c) {
        return '<tr><td>' + esc(c.resume + ' - ' + c.what) + '</td><td class="num">' + c.hand_label + '/3</td><td class="num">#' + c.resumeradar.rank + '</td><td class="num">#' + c.keyword_ats.rank + '</td><td class="num">#' + c.plain_tfidf.rank + '</td></tr>';
      }).join('') + '</tbody></table></div>';
    h += '<h3>Fairness: max score change when identity is deleted or swapped</h3><div class="table-wrap"><table class="metrics"><thead><tr><th>Job</th><th>Blind mode</th><th>Standard mode</th></tr></thead><tbody>' +
      Object.keys(r.fairness).map(function (jid) {
        var f = r.fairness[jid];
        var cell = function (x) { return fmt(Math.max(x.max_delta_stripped, x.max_delta_swapped), 2) + ' pts · ' + Math.max(x.rank_changes_swapped, x.rank_changes_stripped) + ' rank changes'; };
        return '<tr><td>' + esc(r.rankings[jid].title) + '</td><td class="best">' + cell(f.blind) + '</td><td>' + cell(f.standard) + '</td></tr>';
      }).join('') + '</tbody></table></div>';
    h += '<h3>Skill extraction on ' + ex.snippets + ' tricky snippets (' + ex.expected_skills + ' labelled skills)</h3>' +
      '<p class="muted">ResumeRadar P ' + fmt(ex.resumeradar.precision, 3) + ' / R ' + fmt(ex.resumeradar.recall, 3) + ' vs keyword baseline P ' + fmt(ex.keyword_baseline.precision, 3) + ' / R ' + fmt(ex.keyword_baseline.recall, 3) + '. Known misses:</p>' +
      '<ul class="clean">' + ex.errors.map(function (e) {
        return '<li>• "' + esc(e.text) + '"' + (e.missed.length ? ' - missed ' + esc(e.missed.join(', ')) : '') + (e.extra.length ? ' - false positive ' + esc(e.extra.join(', ')) : '') + '</li>';
      }).join('') + '</ul>';
    if (lat) h += '<p class="muted">Latency: score + rank ' + lat.resumes + ' resumes in ' + fmt(lat.score_and_rank_ms, 0) + ' ms; full reports (gaps, ATS, interview) in ' + fmt(lat.full_reports_ms, 0) + ' ms (' + fmt(lat.per_resume_full_ms, 2) + ' ms per resume, median of ' + lat.repeats + ' runs, this laptop).</p>';
    $('#eval').innerHTML = h;
  }

  // ------------------------------------------------------------------ bindings
  function bind() {
    $$('.tab').forEach(function (t) { t.addEventListener('click', function () { showView(t.dataset.view); }); });
    $('#jd-select').addEventListener('change', function (e) {
      var v = e.target.value;
      if (v === 'custom') { $('#jd-editor').classList.remove('hidden'); $('#jd-text').value = S.jdText; $('#jd-text').focus(); return; }
      setJd(v, null, true);
    });
    $('#btn-edit-jd').addEventListener('click', function () {
      $('#jd-editor').classList.toggle('hidden');
      $('#jd-text').value = S.jdText;
    });
    $('#btn-jd-cancel').addEventListener('click', function () {
      $('#jd-editor').classList.add('hidden');
      if ($('#jd-select').value === 'custom' && S.jdKey !== 'custom') $('#jd-select').value = S.jdKey;
    });
    $('#btn-jd-apply').addEventListener('click', function () {
      var t = $('#jd-text').value;
      if (t.trim().length < 20) { toast('The JD is too short', true); return; }
      $('#jd-editor').classList.add('hidden');
      $('#jd-select').value = 'custom';
      setJd('custom', t, true);
    });
    $('#btn-demo').addEventListener('click', loadDemo);
    $('#file-resumes').addEventListener('change', function (e) {
      var files = e.target.files;
      if (!files || !files.length) return;
      readFiles(files).then(addResumes).then(function () { e.target.value = ''; });
    });
    $('#btn-paste').addEventListener('click', function () { $('#paste-panel').classList.toggle('hidden'); $('#paste-text').focus(); });
    $('#btn-paste-cancel').addEventListener('click', function () { $('#paste-panel').classList.add('hidden'); });
    $('#btn-paste-add').addEventListener('click', function () {
      var t = $('#paste-text').value;
      addResumes([{ name: $('#paste-name').value.trim() || null, text: t }]).then(function () {
        $('#paste-text').value = ''; $('#paste-name').value = '';
      });
    });
    $('#blind-toggle').addEventListener('change', function (e) {
      S.blind = e.target.checked;
      toast(S.blind ? 'Blind mode on: identity masked before scoring' : 'Blind mode off: identity visible to the scorer');
      if (S.resumes.length) runScreen();
    });
    $('#btn-screen').addEventListener('click', runScreen);
    $('#btn-coach').addEventListener('click', runCoach);
    $('#coach-sample').addEventListener('change', function (e) { if (e.target.value) loadSample(e.target.value); });
    $('#coach-file').addEventListener('change', function (e) {
      if (!e.target.files || !e.target.files.length) return;
      readFiles([e.target.files[0]]).then(function (list) { $('#coach-text').value = list[0].text; e.target.value = ''; runCoach(); });
    });
    $('#btn-eval').addEventListener('click', runEval);
    $('#onto-search').addEventListener('input', function (e) { searchOnto(e.target.value); });
  }

  function init() {
    bind();
    var rz = null;
    window.addEventListener('resize', function () { clearTimeout(rz); rz = setTimeout(function () { if ($('#view-how').classList.contains('active')) drawOnto(); }, 200); });
    renderAll();
    renderDetail($('#coach-detail'), null, 'coach');
    Promise.all([api('/api/demo'), api('/api/config'), api('/api/ontology')]).then(function (r) {
      S.demo = r[0]; S.config = r[1]; S.onto = r[2];
      $('#skill-count').textContent = S.onto.stats.skills + ' skills · ' + S.onto.stats.aliases + ' aliases';
      fillJdSelects();
      renderHowStatic();
      renderKpis();
      return loadDemo();
    }).catch(function (e) { toast('Could not reach the ResumeRadar server: ' + e.message, true); });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
