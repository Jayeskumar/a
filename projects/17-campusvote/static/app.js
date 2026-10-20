/* CampusVote UI - vanilla JS, no libraries. Crypto lives in crypto.js (window.CV). */
(() => {
  'use strict';
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
  const esc = (s) => String(s === undefined || s === null ? '' : s).replace(/[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const short = (h, n = 12) => (h ? String(h).slice(0, n) + '…' : '-');
  const fmtTime = (t) => new Date(t * 1000).toLocaleString([], { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  const clock = (t) => new Date(t * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  const store = {
    get(k) { try { return JSON.parse(localStorage.getItem(k)); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
    del(k) { try { localStorage.removeItem(k); } catch (e) { /* ignore */ } },
  };
  const VIEWS = ['vote', 'dashboard', 'board', 'results', 'attacks', 'admin'];
  const PHASE_LABEL = { setup: 'Setup', registration: 'Registration open', voting: 'Voting open', tally: 'Counting complete' };
  const S = { info: null, el: null, stats: null, board: null, boardAll: false, audit: null, view: '',
    wallet: null, choices: {}, session: null, pending: null, highlight: null, lastBallots: -1 };

  async function api(path, opts = {}) {
    const o = { method: 'GET', headers: {}, credentials: 'omit', cache: 'no-store' };
    if (opts.body !== undefined) {
      o.method = 'POST';
      o.headers['Content-Type'] = 'application/json';
      o.body = JSON.stringify(opts.body);
    }
    if (opts.admin) o.headers['X-Admin-Key'] = S.adminKey || '';
    const r = await fetch(path, o);
    let data = null;
    try { data = await r.json(); } catch (e) { data = null; }
    if (!r.ok) {
      const err = new Error((data && data.error) || ('HTTP ' + r.status));
      err.status = r.status;
      throw err;
    }
    return data;
  }
  function msg(id, text, kind) {
    const el = $(id);
    el.textContent = text || '';
    el.className = 'msg' + (kind ? ' ' + kind : '');
  }
  let toastT = 0;
  function toast(text) {
    const t = $('#toast');
    t.textContent = text;
    t.classList.remove('hidden');
    clearTimeout(toastT);
    toastT = setTimeout(() => t.classList.add('hidden'), 3500);
  }
  function busy(btn, on, label) {
    if (!btn) return;
    if (on) {
      btn.dataset.label = btn.textContent; btn.dataset.busy = '1';
      btn.textContent = label || 'Working…'; btn.disabled = true;
    } else {
      btn.textContent = btn.dataset.label || btn.textContent; btn.disabled = false; delete btn.dataset.busy;
    }
  }

  // ------------------------------------------------------------------ routing
  function route() {
    let v = location.hash.slice(1);
    if (!VIEWS.includes(v)) v = window.innerWidth < 760 ? 'vote' : 'dashboard';
    S.view = v;
    $$('.view').forEach((el) => el.classList.toggle('active', el.id === 'view-' + v));
    $$('.tabs a').forEach((a) => a.classList.toggle('active', a.dataset.view === v));
    if (v === 'board') loadBoard();
    if (v === 'results') loadResults();
    if (v === 'attacks') renderAttacks();
    if (v === 'dashboard') renderDashboard();
  }

  // ------------------------------------------------------------------ data refresh
  async function loadElection() {
    S.el = await api('/api/election');
    S.wallet = S.el.election ? store.get('cv.wallet.' + S.el.election.eid) : null;
    initVote();
  }
  async function refreshStats() {
    try {
      S.stats = await api('/api/stats');
    } catch (e) { return; }
    const st = S.stats;
    if (S.el && st.election.eid !== (S.el.election && S.el.election.eid)) await loadElection();
    else if (S.el && S.el.phase !== st.phase) { S.el.phase = st.phase; S.el.window_state = st.window_state; initVote(); }
    $('#phasePill').textContent = (PHASE_LABEL[st.phase] || st.phase) + (st.phase === 'voting' && st.window_state !== 'open' ? ' (window ' + st.window_state + ')' : '');
    const hb = $('#halted');
    if (st.halted) {
      hb.innerHTML = 'Integrity halt: ' + esc(st.halted) + ' <button class="btn" id="btnRestoreTop">Restore board</button>';
      hb.classList.remove('hidden');
      $('#btnRestoreTop').onclick = restoreBoard;
      setIntegrity(false);
    } else {
      hb.classList.add('hidden');
      if (S.integrity === false) checkIntegrity();
    }
    if (S.view === 'dashboard') renderDashboard();
    if (st.ballots !== S.lastBallots) {
      if (S.lastBallots >= 0 && S.view === 'board') loadBoard();
      if (S.vstep === 'receipt' && S.wallet && S.wallet.status !== 'counted') checkReceipt(true);
      S.lastBallots = st.ballots;
    }
  }
  function setIntegrity(ok) {
    S.integrity = ok;
    const p = $('#integrityPill');
    p.textContent = ok ? 'Board verified ✓' : 'Board integrity FAILED';
    p.className = 'pill subtle ' + (ok ? 'ok' : 'bad');
  }
  async function checkIntegrity() {
    try {
      const r = await api('/api/board/verify');
      setIntegrity(r.verdict === 'VERIFIED' && !r.halted);
      return r;
    } catch (e) { return null; }
  }

  // ------------------------------------------------------------------ VOTE
  const ORDER = ['login', 'token', 'choose', 'review', 'receipt'];
  function voteStep(step) {
    S.vstep = step;
    $$('.vstep').forEach((el) => el.classList.toggle('hidden', el.id !== 'step-' + step));
    const idx = ORDER.indexOf(step);
    $$('#voteStepper li').forEach((li, i) => { li.className = i < idx ? 'done' : (i === idx ? 'now' : ''); });
  }
  function saveWallet() { if (S.el && S.el.election) store.set('cv.wallet.' + S.el.election.eid, S.wallet); }
  function initVote() {
    const el = S.el;
    if (!el || !el.election) {
      $('#voteTitle').textContent = 'No election yet';
      voteStep('login');
      return;
    }
    const m = el.election;
    $('#voteEid').textContent = m.eid;
    $('#voteTitle').textContent = m.title;
    $('#voteWindow').textContent = (PHASE_LABEL[el.phase] || el.phase) + ' · voting window ' +
      fmtTime(m.window.opens) + ' → ' + fmtTime(m.window.closes);
    const w = S.wallet;
    if (w && w.cast) { voteStep('receipt'); renderReceipt(); return; }
    if (w && w.sig) {
      if (el.phase === 'voting') {
        if (S.vstep !== 'review') { voteStep('choose'); renderBallot(); }
      } else {
        voteStep('token');
        showTokenDone();
      }
      return;
    }
    if (S.vstep !== 'token') voteStep('login');
  }
  async function doLogin() {
    const reg = $('#regNo').value.trim(), code = $('#otp').value.trim();
    if (!reg || !code) return msg('#loginMsg', 'Enter your register number and one-time code', 'bad');
    const btn = $('#btnLogin');
    busy(btn, true, 'Checking…');
    try {
      const r = await api('/api/login', { body: { reg_no: reg, code } });
      S.session = r.session;
      $('#hello').textContent = 'Hello, ' + r.voter.name + ' (' + r.voter.dept + ')';
      $$('#tokenSteps li').forEach((li) => li.classList.remove('on'));
      ['#tToken', '#tBlinded', '#tBlindSig', '#tSig'].forEach((id) => { $(id).textContent = '-'; });
      $('#btnGetToken').classList.remove('hidden');
      $('#btnToBallot').classList.add('hidden');
      msg('#tokenMsg', r.already_issued ? 'You already received a token. One token per voter: a new one cannot be issued.' : '',
        r.already_issued ? 'bad' : '');
      msg('#loginMsg', '');
      $('#otp').value = '';
      voteStep('token');
    } catch (e) {
      msg('#loginMsg', e.message, 'bad');
    } finally { busy(btn, false); }
  }
  async function demoVoter() {
    try {
      const d = await api('/api/demo/voter');
      $('#regNo').value = d.reg_no;
      $('#otp').value = d.code;
      msg('#loginMsg', 'Demo voter ' + d.name + ' (' + d.dept + ') - ' + d.remaining + ' demo voters left', 'ok');
      await doLogin();
    } catch (e) { msg('#loginMsg', e.message, 'bad'); }
  }
  function on(k, text) {
    const li = $('#tokenSteps li[data-k="' + k + '"]');
    li.classList.add('on');
    li.querySelector('code').textContent = text;
  }
  async function getToken() {
    const btn = $('#btnGetToken');
    busy(btn, true, 'Blind signing…');
    msg('#tokenMsg', '');
    try {
      const pub = CV.pubKey(S.el.keys.issuer), eid = S.el.election.eid;
      const token = CV.newSecretHex();
      on('gen', 't = ' + short(token, 24));
      await sleep(350);
      const b = CV.blind(pub, CV.tokenMessage(eid, token));
      on('blind', "m' = " + short(b.blinded.toString(16), 24));
      await sleep(350);
      const r = await api('/api/issue', { body: { session: S.session, blinded: b.blinded.toString(16) } });
      on('sign', "s' = " + short(r.blind_sig, 24));
      await sleep(350);
      const sig = CV.unblind(pub, CV.big(r.blind_sig), b.r);
      if (!CV.verifyToken(pub, eid, token, sig)) throw new Error('authority returned an invalid signature');
      on('unblind', 's = ' + short(sig.toString(16), 24) + '  ✓ verified on this phone');
      S.wallet = { eid, token, sig: sig.toString(16) };
      S.session = null; // forget the login: from here on we are anonymous
      saveWallet();
      btn.classList.add('hidden');
      showTokenDone();
    } catch (e) {
      msg('#tokenMsg', e.message, 'bad');
    } finally { busy(btn, false); }
  }
  function showTokenDone() {
    $('#btnGetToken').classList.add('hidden');
    if (S.el.phase === 'voting') {
      msg('#tokenMsg', 'Token ready. You are now anonymous: nothing you send next carries your register number.', 'ok');
      $('#btnToBallot').classList.remove('hidden');
    } else {
      msg('#tokenMsg', 'Token saved on this device. Voting has not opened yet - come back when it does.', 'ok');
      $('#btnToBallot').classList.add('hidden');
    }
  }
  const initials = (n) => n.split(/\s+/).map((x) => x[0]).join('').slice(0, 2).toUpperCase();
  function renderBallot() {
    const posts = S.el.election.posts;
    $('#ballotPosts').innerHTML = posts.map((p, i) => '<div class="post" role="radiogroup" aria-label="' + esc(p.title) + '">' +
      '<h3>' + esc(p.title) + ' <small>' + (i + 1) + ' of ' + posts.length + ' · choose one</small></h3>' +
      p.candidates.map((c) => '<button type="button" class="cand' + (c.id === 'NOTA' ? ' nota' : '') + '" role="radio" aria-checked="' +
        (S.choices[p.id] === c.id) + '" data-post="' + esc(p.id) + '" data-cand="' + esc(c.id) + '">' +
        '<span class="av">' + (c.id === 'NOTA' ? '–' : esc(initials(c.name))) + '</span><span><span class="nm">' + esc(c.name) +
        '</span><span class="sl">' + esc([c.dept, c.slogan].filter(Boolean).join(' · ')) + '</span></span><span class="tick"></span></button>').join('') +
      '</div>').join('');
    $('#btnReview').disabled = !posts.every((p) => S.choices[p.id]);
  }
  function review() {
    const posts = S.el.election.posts;
    $('#reviewList').innerHTML = posts.map((p) => {
      const c = p.candidates.find((x) => x.id === S.choices[p.id]);
      return '<li><span>' + esc(p.title) + '</span><b>' + esc(c ? c.name : '-') + '</b></li>';
    }).join('');
    const nonce = CV.newSecretHex();
    const commitment = CV.commitBallot(S.el.election.eid, S.wallet.token, S.choices, nonce);
    S.pending = { nonce, commitment };
    $('#rvCommit').textContent = short(commitment, 20);
    msg('#castMsg', '');
    voteStep('review');
  }
  async function cast() {
    const btn = $('#btnCast');
    busy(btn, true, 'Sealing and sending…');
    try {
      const w = S.wallet, eid = S.el.election.eid, choices = Object.assign({}, S.choices), nonce = S.pending.nonce;
      const commitment = CV.commitBallot(eid, w.token, choices, nonce);
      const sealed = CV.seal(CV.pubKey(S.el.keys.trustee), CV.utf8(CV.canonical({ choices, nonce })), w.token);
      const r = await api('/api/ballot', { body: { token: w.token, sig: w.sig, commitment, sealed } });
      Object.assign(w, { cast: true, choices, nonce, commitment, tokenHash: r.token_hash, status: r.status, pool: r.pool_size });
      saveWallet();
      voteStep('receipt');
      renderReceipt();
      checkReceipt(true);
    } catch (e) {
      msg('#castMsg', e.message, 'bad');
    } finally { busy(btn, false); }
  }
  function renderReceipt(found) {
    const w = S.wallet;
    if (!w) return;
    const code = (w.tokenHash || '').slice(0, 16).toUpperCase().replace(/(.{4})/g, '$1 ').trim();
    $('#receiptCode').textContent = code;
    const f = found || S.found || {};
    const posts = S.el.election.posts;
    const opened = f.opening;
    const match = opened && opened.status === 'ok' && posts.every((p) => opened.choices[p.id] === w.choices[p.id]);
    const items = [
      ['done', 'Accepted into the anonymity mix (signature checked, token unused)'],
      f.seq !== undefined ? ['done', 'Posted on the bulletin board as entry #' + f.seq + ' (batch ' + f.batch + ', commitment ' + (f.commitOk ? 'matches ✓' : 'MISMATCH') + ')']
        : ['wait', 'Waiting in the mix for a shuffled batch… (' + Math.max((S.stats && S.stats.pool) || 0, w.pool || 0) + ' ballots waiting)'],
      f.checkpoint !== undefined && f.checkpoint !== null ? ['done', 'Sealed by signed checkpoint #' + f.checkpoint]
        : ['', 'Sealed by the next signed checkpoint'],
      opened ? [match ? 'done' : 'fail', match ? 'Opened by the trustee and COUNTED exactly as you chose ✓'
        : 'Opened, but does not match your choices - contest it with this receipt!']
        : ['', 'Opened and counted after voting closes'],
    ];
    $('#receiptTimeline').innerHTML = items.map((x) => '<li class="' + x[0] + '">' + esc(x[1]) + '</li>').join('');
    $('#receiptHead').textContent = opened ? (match ? 'Your vote was counted' : 'Problem with your ballot') : 'Ballot cast';
  }
  async function checkReceipt(quiet) {
    const w = S.wallet;
    if (!w || !w.cast) return;
    try {
      const b = await api('/api/board');
      const entries = b.entries;
      const e = entries.find((x) => x.type === 'ballot' && x.data.token === w.token);
      if (!e) {
        S.found = {};
        renderReceipt();
        if (!quiet) msg('#receiptMsg', 'Not on the board yet - it is waiting in the mix with other ballots.', '');
        return;
      }
      const cp = entries.find((x) => x.type === 'checkpoint' && x.data.upto >= e.seq);
      const op = entries.find((x) => x.type === 'opening' && x.data.token === w.token);
      S.found = { seq: e.seq, batch: e.data.batch, commitOk: e.data.commitment === w.commitment,
        checkpoint: cp ? cp.seq : null, opening: op ? op.data : null, hash: e.hash };
      w.status = op ? (op.data.status === 'ok' ? 'counted' : 'spoiled') : 'posted';
      w.entryHash = w.entryHash || e.hash;
      saveWallet();
      renderReceipt();
      if (!quiet) {
        const a = CV.audit(entries);
        const same = w.entryHash === e.hash;
        msg('#receiptMsg', 'Found entry #' + e.seq + (same ? ', hash unchanged' : ', HASH CHANGED since you first saw it!') +
          '. Whole board re-verified on this phone in ' + a.ms + ' ms: ' + a.verdict + '.', a.verdict === 'VERIFIED' && same ? 'ok' : 'bad');
      }
    } catch (e) { if (!quiet) msg('#receiptMsg', e.message, 'bad'); }
  }

  // ------------------------------------------------------------------ DASHBOARD
  function hbars(rows, labelW, width) {
    const W = width || 560, rowH = 34, lw = labelW || 120, bw = W - lw - 74;
    const h = rows.length * rowH + 6;
    let s = '<svg viewBox="0 0 ' + W + ' ' + h + '" role="img">';
    rows.forEach((r, i) => {
      const y = i * rowH + 6, frac = r.max ? r.value / r.max : 0;
      s += '<text class="lbl" x="0" y="' + (y + 16) + '">' + esc(r.label) + '</text>' +
        '<rect class="track" x="' + lw + '" y="' + (y + 3) + '" width="' + bw + '" height="18" rx="5"></rect>' +
        '<rect class="fill ' + (r.cls || '') + '" x="' + lw + '" y="' + (y + 3) + '" width="' + Math.max(2, bw * frac).toFixed(1) + '" height="18" rx="5"></rect>' +
        '<text class="val" x="' + (lw + bw + 8) + '" y="' + (y + 16) + '">' + esc(r.right) + '</text>';
    });
    return s + '</svg>';
  }
  function lineChart(pts, total) {
    const W = 560, H = 220, L = 40, B = 26, T = 24, R = 14;
    if (!pts.length) return '<p class="muted">No ballots yet.</p>';
    const t0 = pts[0].t - 60, t1 = Math.max(pts[pts.length - 1].t, t0 + 120);
    const ymax = Math.max(total || 0, pts[pts.length - 1].n, 1);
    const x = (t) => L + (W - L - R) * (t - t0) / (t1 - t0), y = (n) => H - B - (H - B - T) * n / ymax;
    let d = 'M' + x(t0).toFixed(1) + ',' + y(0).toFixed(1);
    pts.forEach((p) => { d += ' H' + x(p.t).toFixed(1) + ' V' + y(p.n).toFixed(1); });
    const area = d + ' H' + x(t1).toFixed(1) + ' V' + y(0).toFixed(1) + ' Z';
    let s = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img">';
    for (let k = 0; k <= 4; k++) {
      const n = Math.round(ymax * k / 4);
      s += '<line class="grid" x1="' + L + '" x2="' + (W - R) + '" y1="' + y(n) + '" y2="' + y(n) + '"></line><text x="' + (L - 6) + '" y="' + (y(n) + 4) + '" text-anchor="end">' + n + '</text>';
    }
    for (let k = 0; k <= 3; k++) {
      const t = t0 + (t1 - t0) * k / 3;
      s += '<text x="' + x(t) + '" y="' + (H - 8) + '" text-anchor="' + (k === 0 ? 'start' : k === 3 ? 'end' : 'middle') + '">' + clock(t) + '</text>';
    }
    if (total) s += '<line class="grid" stroke-dasharray="4 4" x1="' + L + '" x2="' + (W - R) + '" y1="' + y(total) + '" y2="' + y(total) + '"></line><text x="' + (W - R) + '" y="' + (y(total) - 5) + '" text-anchor="end">tokens issued: ' + total + '</text>';
    return s + '<path class="area" d="' + area + '"></path><path class="line" d="' + d + '"></path></svg>';
  }
  function renderDashboard() {
    const st = S.stats;
    if (!st || !st.election.eid) return;
    $('#dEid').textContent = st.election.eid + ' · ' + st.election.posts + ' posts';
    $('#dTitle').textContent = st.election.title;
    const w = st.election.window;
    $('#dWindow').textContent = 'Voting window ' + fmtTime(w.opens) + ' → ' + fmtTime(w.closes) + ' (' + st.window_state + ')';
    const ph = ['setup', 'registration', 'voting', 'tally'], pi = ph.indexOf(st.phase);
    $$('#phaseBar li').forEach((li, i) => { li.className = i < pi ? 'done' : (i === pi ? 'now' : ''); });
    const adv = $('#btnAdvance');
    const next = { setup: 'Open registration', registration: 'Open voting', voting: 'Close voting & tally', tally: 'Counting complete' };
    if (!adv.dataset.busy) {
      adv.textContent = next[st.phase];
      adv.disabled = st.phase === 'tally';
    }
    const kp = [
      { v: st.eligible, l: 'Eligible voters', s: 'on the roster' },
      { v: st.tokens_issued, l: 'Tokens issued', s: st.token_pct + '% of roster', bar: st.token_pct, cls: 'accent' },
      { v: st.ballots, l: 'Ballots on board', s: 'turnout ' + st.turnout_pct + '%', bar: st.turnout_pct, cls: 'accent' },
      { v: st.pool, l: 'Waiting in mix', s: 'posted in shuffled batches of ' + ((S.el && S.el.params.mix_batch) || 4), cls: 'gold' },
      { v: st.board.entries, l: 'Board entries', s: st.board.checkpoints + ' signed checkpoints · head ' + short(st.board.head, 8) },
    ];
    $('#kpis').innerHTML = kp.map((k) => '<div class="kpi ' + (k.cls || '') + '"><div class="l">' + esc(k.l) + '</div><div class="v">' + esc(k.v) +
      '</div><div class="s">' + esc(k.s) + '</div>' + (k.bar !== undefined ? '<div class="bar"><i style="width:' + Math.min(100, k.bar) + '%"></i></div>' : '') + '</div>').join('');
    const lc = st.board.last_checkpoint;
    $('#dLive').innerHTML = [
      ['Board head', '<code>' + esc(short(st.board.head, 20)) + '</code>'],
      ['Last signed checkpoint', lc ? '#' + lc.seq + ' covering #0-#' + lc.upto + ' at ' + clock(lc.time) : '-'],
      ['Mix batches posted', esc(st.board.batches) + ' (batch of ' + ((S.el && S.el.params.mix_batch) || 4) + ' or ' + ((S.el && S.el.params.mix_max_wait_s) || 12) + ' s)'],
      ['Accounts locked (OTP guessing)', esc(st.locked)],
    ].map((r) => '<li><span>' + r[0] + '</span><b>' + r[1] + '</b></li>').join('');
    $('#chartDept').innerHTML = hbars(st.by_dept.map((d) => ({ label: d.dept, value: d.issued, max: d.eligible,
      right: d.issued + ' / ' + d.eligible })), 70);
    $('#chartTime').innerHTML = lineChart(st.timeline, st.tokens_issued);
  }
  async function advance() {
    const st = S.stats;
    const map = { setup: 'registration', registration: 'voting', voting: 'tally' };
    const target = map[st.phase];
    if (!target) return;
    const btn = $('#btnAdvance');
    busy(btn, true, target === 'tally' ? 'Trustee opening ballots…' : 'Working…');
    try {
      await api('/api/admin/phase', { body: { phase: target }, admin: true });
      toast(target === 'tally' ? 'Voting closed. Every ballot opened, counted and verified.' : 'Phase: ' + target);
      await refreshStats();
      if (target === 'tally') location.hash = '#results';
    } catch (e) { msg('#dashMsg', e.message, 'bad'); } finally { busy(btn, false); renderDashboard(); }
  }
  async function demoReset(btn) {
    busy(btn, true, 'Building demo election…');
    try {
      const r = await api('/api/demo/reset', { body: {}, admin: true });
      S.choices = {};
      S.found = null;
      S.vstep = null;
      await loadElection();
      await refreshStats();
      checkIntegrity();
      toast('Demo loaded: ' + r.students + ' students, ' + r.tokens + ' tokens, ' + r.ballots + ' ballots');
      if (S.view === 'board') loadBoard();
      if (S.view === 'results') loadResults();
    } catch (e) { toast(e.message); } finally { busy(btn, false); }
  }
  async function simulate(n, btn) {
    busy(btn, true, 'Simulating…');
    try {
      const r = await api('/api/admin/simulate', { body: { count: n }, admin: true });
      toast(r.tokens + ' voters ran the full protocol: ' + r.cast + ' ballots cast, ' + r.pool + ' waiting in the mix');
      await refreshStats();
    } catch (e) { toast(e.message); } finally { busy(btn, false); }
  }

  // ------------------------------------------------------------------ BOARD
  function summary(e, names) {
    const d = e.data || {};
    switch (e.type) {
      case 'genesis': return 'Election "' + (d.election ? d.election.title : '?') + '" · ' + (d.roster ? d.roster.eligible : '?') + ' eligible · issuer key ' + (d.keys ? d.keys.issuer.fp : '');
      case 'phase': return d.phase === 'voting' ? 'Voting opened' : 'Voting closed: ' + d.tokens_issued + ' tokens issued, ' + d.ballots + ' ballots';
      case 'issuance': return 'Token issued to voter ' + d.voter_ref + " · blinded m' " + short(d.blinded, 14);
      case 'ballot': return 'Ballot · receipt ' + CV.sha256hex(d.token || '').slice(0, 8).toUpperCase() + ' · commitment ' + short(d.commitment, 14) + ' · batch ' + d.batch;
      case 'checkpoint': return 'Signed checkpoint: head ' + short(d.head, 14) + ' covers #0-#' + d.upto + ' (' + d.ballots + ' ballots)';
      case 'opening': return d.status === 'ok' ? 'Opened ' + CV.sha256hex(d.token || '').slice(0, 8).toUpperCase() + ': ' + Object.keys(d.choices || {}).map((p) => names[p + '/' + d.choices[p]] || d.choices[p]).join(', ') : 'Spoiled: ' + d.reason;
      case 'result': return 'Signed result: ' + d.counted + ' counted, ' + d.spoiled + ' spoiled';
      default: return JSON.stringify(d).slice(0, 80);
    }
  }
  async function loadBoard() {
    try {
      S.board = await api('/api/board');
      renderBoard();
    } catch (e) { $('#boardList').innerHTML = '<p class="msg bad">' + esc(e.message) + '</p>'; }
  }
  function renderBoard() {
    const entries = S.board ? S.board.entries : [];
    const g = entries[0] && entries[0].type === 'genesis' ? entries[0].data.election : null;
    const names = {};
    if (g) g.posts.forEach((p) => p.candidates.forEach((c) => { names[p.id + '/' + c.id] = c.name.split(' ')[0]; }));
    const broken = new Set();
    let prev = '0'.repeat(64);
    entries.forEach((e, i) => {
      if (e.seq !== i || e.prev !== prev || CV.entryHash(e) !== e.hash) broken.add(i);
      prev = e.hash;
    });
    const f = $('#boardFilter').value;
    let rows = entries.map((e, i) => [e, i]).filter(([e, i]) => !f || e.type === f || broken.has(i));
    const total = rows.length;
    if (!S.boardAll && rows.length > 60) {
      const keep = new Set(rows.slice(-60).map((r) => r[1]));
      if (S.highlight !== null) keep.add(S.highlight);
      broken.forEach((b) => keep.add(b));
      rows = rows.filter((r) => keep.has(r[1]) || r[1] === 0);
    }
    $('#btnMoreBoard').classList.toggle('hidden', S.boardAll || total <= 60);
    $('#boardHead').textContent = 'Bulletin board · ' + entries.length + ' entries' + (broken.size ? ' · ' + broken.size + ' broken' : '');
    const mine = S.wallet && S.wallet.token;
    $('#boardList').innerHTML = rows.map(([e, i]) => '<div class="entry' + (broken.has(i) ? ' broken' : '') +
      ((mine && e.data && e.data.token === mine && e.type === 'ballot') || S.highlight === i ? ' mine' : '') + '" id="entry-' + i + '">' +
      '<span class="sq">#' + esc(e.seq) + '</span><span class="chip ' + esc(e.type) + '">' + esc(e.type) + '</span>' +
      '<span class="sm" title="' + esc(summary(e, names)) + '">' + esc(summary(e, names)) + '</span>' +
      '<span class="hs">hash <b>' + esc(String(e.hash).slice(0, 16)) + '</b><br>prev ' + esc(String(e.prev).slice(0, 16)) + '</span></div>').join('') +
      (rows.length < entries.length && !f ? '<p class="hint">Showing the genesis entry and the latest entries. Verification always covers all ' + entries.length + '.</p>' : '');
  }
  function renderChecks(rep, where) {
    const ok = rep.verdict === 'VERIFIED';
    return '<div class="verify"><div class="verdict ' + (ok ? 'ok' : 'bad') + '">' + (ok ? '✓ VERIFIED' : '✗ FAILED') +
      ' <span>' + esc(where) + '</span><small>' + esc(rep.ms) + ' ms</small></div><ul class="checks">' +
      rep.steps.map((s) => '<li><span class="ic ' + (s.ok ? 'ok' : 'bad') + '">' + (s.ok ? '✓' : '✗') + '</span><b>' + esc(s.title) +
        '</b><span class="d">' + esc(s.detail) + '</span>' + (s.why ? '<span class="w">Why it matters: ' + esc(s.why) + '</span>' : '') + '</li>').join('') + '</ul></div>';
  }
  async function verifyBrowser(btn) {
    busy(btn, true, 'Verifying…');
    try {
      await loadBoard();
      await sleep(30);
      const rep = CV.audit(S.board.entries);
      S.audit = rep;
      $('#verifyOut').innerHTML = renderChecks(rep, 'recomputed in your browser from board.json - no trust in the server needed');
      if (rep.firstBreak !== null && rep.firstBreak !== undefined) scrollToEntry(rep.firstBreak);
    } catch (e) { $('#verifyOut').innerHTML = '<p class="msg bad">' + esc(e.message) + '</p>'; } finally { busy(btn, false); }
  }
  async function verifyServer(btn) {
    busy(btn, true, 'Verifying…');
    try {
      const rep = await api('/api/board/verify');
      setIntegrity(rep.verdict === 'VERIFIED' && !rep.halted);
      $('#verifyOut').innerHTML = renderChecks(rep, 'server audit of data/board.json on disk');
      if (rep.first_break !== null && rep.first_break !== undefined) { await loadBoard(); scrollToEntry(rep.first_break); }
    } catch (e) { $('#verifyOut').innerHTML = '<p class="msg bad">' + esc(e.message) + '</p>'; } finally { busy(btn, false); }
  }
  function scrollToEntry(i) {
    S.highlight = i;
    renderBoard();
    const el = $('#entry-' + i);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
  async function lookup() {
    const code = $('#receiptLookup').value.replace(/\s+/g, '').toLowerCase();
    if (!/^[0-9a-f]{8,64}$/.test(code)) return toast('Enter at least 8 hex characters of a receipt code');
    if (!S.board) await loadBoard();
    const e = S.board.entries.find((x) => x.type === 'ballot' && CV.sha256hex(x.data.token).startsWith(code));
    if (!e) return toast('No ballot with that receipt code on the board');
    const op = S.board.entries.find((x) => x.type === 'opening' && x.data.token === e.data.token);
    toast('Found ballot #' + e.seq + (op ? (op.data.status === 'ok' ? ' - opened and counted' : ' - spoiled') : ' - sealed until the count') + ' (searched locally)');
    scrollToEntry(e.seq);
  }

  // ------------------------------------------------------------------ RESULTS
  const LOCK = '<svg class="lock" viewBox="0 0 64 64" aria-hidden="true"><rect x="10" y="28" width="44" height="30" rx="7" fill="#9333EA"/><path d="M20 28v-8a12 12 0 0 1 24 0v8" fill="none" stroke="#F5B301" stroke-width="6"/><circle cx="32" cy="42" r="5" fill="#F5B301"/></svg>';
  async function loadResults() {
    const out = $('#resultsOut');
    if (!S.stats) await refreshStats();
    const st = S.stats;
    if (!st || st.phase !== 'tally') {
      out.innerHTML = '<div class="card sealed">' + LOCK + '<h2>Results are sealed</h2><p class="muted">' + (st ? st.ballots : 0) +
        ' ballots are on the board only as SHA-256 commitments. Nobody - not even the election admin - can compute a running total.</p>' +
        '<p class="muted">When voting closes the trustee opens every sealed ballot, publishes each opening next to its commitment, and anyone can recount.</p>' +
        '<button class="btn primary" id="btnTallyNow">Close voting &amp; tally now (admin)</button><p class="msg" id="tallyMsg"></p></div>';
      $('#btnTallyNow').onclick = async (ev) => {
        busy(ev.target, true, 'Trustee opening ballots…');
        try {
          await api('/api/admin/phase', { body: { phase: 'tally' }, admin: true });
          await refreshStats();
          loadResults();
        } catch (e) { msg('#tallyMsg', e.message, 'bad'); busy(ev.target, false); }
      };
      return;
    }
    try {
      const r = await api('/api/results');
      const t = r.tally, man = r.manifest;
      const cards = man.posts.map((p) => {
        const counts = t.counts[p.id], tot = Object.values(counts).reduce((a, b) => a + b, 0) || 1;
        const win = t.winners[p.id] || [];
        const rows = p.candidates.map((c) => ({ label: c.id === 'NOTA' ? 'NOTA' : c.name, value: counts[c.id], max: Math.max(...Object.values(counts), 1),
          right: counts[c.id] + ' (' + Math.round(100 * counts[c.id] / tot) + '%)', cls: c.id === 'NOTA' ? 'nota' : (win.includes(c.id) ? 'win' : '') }));
        const wn = p.candidates.filter((c) => win.includes(c.id)).map((c) => c.name).join(' & ');
        return '<div class="card"><div class="eyebrow">' + esc(p.title) + '</div><div class="winner">★ ' + esc(wn || 'no winner') + (win.length > 1 ? ' (tie)' : '') + '</div>' +
          '<div class="chart">' + hbars(rows, 112, 370) + '</div></div>';
      }).join('');
      const turnout = r.eligible ? Math.round(1000 * t.counted / r.eligible) / 10 : 0;
      out.innerHTML = '<div class="kpis"><div class="kpi accent"><div class="l">Ballots counted</div><div class="v">' + t.counted + '</div><div class="s">turnout ' + turnout + '% of ' + r.eligible + '</div></div>' +
        '<div class="kpi"><div class="l">Spoiled</div><div class="v">' + t.spoiled + '</div><div class="s">listed by token so voters can contest</div></div>' +
        '<div class="kpi"><div class="l">Tokens issued</div><div class="v">' + r.tokens_issued + '</div><div class="s">ballots never exceed tokens</div></div>' +
        '<div class="kpi gold"><div class="l">Audit</div><div class="v">' + esc(r.report.verdict) + '</div><div class="s">' + r.report.steps.filter((s) => s.ok).length + ' / ' + r.report.steps.length + ' checks passed</div></div>' +
        '<div class="kpi"><div class="l">Recount time</div><div class="v">' + esc(r.report.ms) + ' ms</div><div class="s">full re-verification from board.json</div></div></div>' +
        '<div class="res-grid">' + cards + '</div>' +
        '<div class="card"><div class="toolbar"><h3>Step-by-step verification report</h3><span class="spacer"></span><button class="btn primary" id="btnReverify">Re-verify in my browser</button></div>' +
        renderChecks(r.report, 'server audit') + '<div id="reverifyOut"></div></div>';
      $('#btnReverify').onclick = async (ev) => {
        busy(ev.target, true, 'Recounting…');
        try {
          const b = await api('/api/board');
          const rep = CV.audit(b.entries);
          const same = rep.tally && CV.canonical(rep.tally.counts) === CV.canonical(t.counts);
          $('#reverifyOut').innerHTML = renderChecks(rep, 'your browser recounted ' + (rep.tally ? rep.tally.counted : 0) + ' ballots: ' + (same ? 'identical to the published result' : 'DIFFERENT from the published result'));
        } finally { busy(ev.target, false); }
      };
    } catch (e) { out.innerHTML = '<div class="card"><p class="msg bad">' + esc(e.message) + '</p></div>'; }
  }

  // ------------------------------------------------------------------ ATTACKS
  const ATTACKS = [
    ['double_token', 'Get a second ballot token', 'Student', 'A student who already has a token asks the authority for another one.'],
    ['double_cast', 'Vote twice with one token', 'Student', 'Re-use an already-cast token with a different choice.'],
    ['replay', 'Replay a captured ballot', 'Network attacker', 'Copy a ballot off the public board and submit it again unchanged.'],
    ['forge_random', 'Forge a token', 'Anyone', 'Invent a token and a random number as its "signature".'],
    ['forge_multiply', 'Multiply two real signatures', 'Cryptographer', 'Textbook RSA is malleable: s1*s2 signs m1*m2. Try to mint a token from two real ones.'],
    ['cross_election', "Reuse last year's token", 'Anyone', 'Replay a genuinely signed ballot from a different election.'],
    ['otp_bruteforce', "Guess a classmate's code", 'Classmate', 'Try random 6-digit one-time codes against one register number.'],
    ['link_attempt', 'Authority de-anonymises a voter', 'Election authority', "Take one student's issuance record and search all ballots for theirs."],
    ['tamper_edit', 'Edit a stored ballot', 'Insider / DB admin', 'Change a ballot (or flip an opened vote) directly in data/board.json.'],
    ['tamper_rehash', 'Edit + re-hash the whole chain', 'Smart insider', 'Change a vote, then recompute every later hash so the chain looks fine.'],
    ['tamper_delete', 'Silently delete a ballot', 'Insider / DB admin', 'Remove one ballot entry from data/board.json.'],
    ['stuffing', 'Stuff ballots with the signing key', 'Corrupt authority', 'Sign extra tokens without issuance records and add ballots (dry run on a copy).'],
  ];
  let attacksRendered = false;
  async function renderAttacks() {
    if (attacksRendered) return;
    attacksRendered = true;
    $('#attackGrid').innerHTML = ATTACKS.map(([id, title, who, desc]) => '<div class="attack" id="atk-' + id + '"><span class="who">' + esc(who) + '</span><h3>' + esc(title) + '</h3><p>' + esc(desc) +
      '</p><button class="btn primary" data-attack="' + id + '">Run attack</button><div class="out hidden"></div></div>').join('') +
      '<div class="attack info"><span class="who">Honest limitation</span><h3>Coercion &amp; vote buying</h3><p>Receipts let you verify your vote was counted - which also lets you <b>prove</b> it to a buyer: ' +
      'after the count, your token\'s opening is public. CampusVote is <b>not receipt-free</b>. For student elections we accept this and recommend supervised voting booths (phones handed in, kiosk voting) when coercion is a real risk.</p></div>';
    try {
      const sec = await api('/api/security');
      const cls = (s) => (/^NOT/.test(s) ? 'n' : /Prevented/.test(s) ? 'p' : /Detected/.test(s) ? 'd' : 'm');
      $('#threatTable').innerHTML = '<thead><tr><th>Threat</th><th>Attacker</th><th>Defence</th><th>Status</th></tr></thead><tbody>' +
        sec.threats.map((t) => '<tr><td>' + esc(t.threat) + '</td><td>' + esc(t.attacker) + '</td><td>' + esc(t.defence) + '</td><td class="st ' + cls(t.status) + '">' + esc(t.status) + '</td></tr>').join('') + '</tbody>';
      $('#limitsList').innerHTML = sec.limits.map((l) => '<li>' + esc(l) + '</li>').join('');
    } catch (e) { /* table optional */ }
  }
  async function runAttack(id, btn) {
    const box = $('#atk-' + id + ' .out');
    busy(btn, true, 'Attacking…');
    try {
      const r = await api('/api/attack/' + id, { body: {}, admin: true });
      let html = '<span class="tag' + (r.blocked ? '' : ' bad') + '">' + esc(r.outcome) + '</span><div>' + esc(r.message) + '</div><div class="why">' + esc(r.why) + '</div>';
      if (id.startsWith('tamper')) {
        const d = r.detail, fb = d.first_break, tgt = d.target_seq;
        const lo = Math.max(0, tgt - 12);
        let mc = '';
        for (let i = lo; i < lo + 22; i++) mc += '<i class="' + (fb !== null && i === fb ? 'b' : (fb !== null && i > fb ? 'after' : '')) + '" title="#' + i + '"></i>';
        html += '<div class="minichain" aria-label="chain around the edited entry">' + mc + '</div><div class="why">Failed checks: ' + esc(d.failed_steps.join(', ')) +
          (fb !== null ? ' · chain breaks at #' + fb : ' · chain hashes look consistent - caught by signatures') + '</div>' +
          '<div class="actions"><button class="btn gold" data-restore="1">Restore board</button><a class="btn" href="#board" data-see="' + (fb !== null ? fb : tgt) + '">See it on the board</a></div>';
        checkIntegrity();
        refreshStats();
      }
      if (id === 'link_attempt' && r.detail.sample) {
        html += '<div class="why">' + r.detail.sample.map((s) => 'ballot #' + s.ballot_seq + ': r = ' + short(s.r, 10) + ' ' + (s.consistent ? '✓ consistent' : '✗')).join('<br>') + '</div>';
      }
      box.innerHTML = html;
      box.classList.remove('hidden');
    } catch (e) {
      box.innerHTML = '<span class="tag bad">ERROR</span> ' + esc(e.message);
      box.classList.remove('hidden');
    } finally { busy(btn, false); }
  }
  async function restoreBoard() {
    try {
      const r = await api('/api/attack/restore', { body: {}, admin: true });
      toast(r.message + (r.verdict ? ' - ' + r.verdict : ''));
      await refreshStats();
      checkIntegrity();
      if (S.view === 'board') { S.highlight = null; loadBoard(); }
    } catch (e) { toast(e.message); }
  }

  // ------------------------------------------------------------------ ADMIN
  function parsePosts(text) {
    return text.split('\n').map((l) => l.trim()).filter(Boolean).map((line) => {
      const i = line.indexOf(':');
      if (i < 1) throw new Error('each line needs "Post: Name (DEPT) | Name (DEPT)"');
      return { title: line.slice(0, i).trim(), candidates: line.slice(i + 1).split('|').map((c) => c.trim()).filter(Boolean).map((c) => {
        const m = c.match(/^(.*?)\s*\(([^)]{1,20})\)\s*$/);
        return m ? { name: m[1], dept: m[2] } : { name: c };
      }) };
    });
  }
  const toLocalInput = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  async function createElection(btn) {
    busy(btn, true);
    try {
      const posts = parsePosts($('#elPosts').value);
      const opens = Math.floor(new Date($('#elOpens').value).getTime() / 1000);
      const closes = Math.floor(new Date($('#elCloses').value).getTime() / 1000);
      const r = await api('/api/admin/election', { body: { title: $('#elTitle').value, posts, opens, closes }, admin: true });
      msg('#adminMsg', 'Created ' + r.eid + ' (setup phase). Now upload a roster.', 'ok');
      await loadElection();
      await refreshStats();
    } catch (e) { msg('#adminMsg', e.message, 'bad'); } finally { busy(btn, false); }
  }
  async function uploadRoster(btn) {
    busy(btn, true);
    try {
      const r = await api('/api/admin/roster', { body: { csv: $('#rosterCsv').value }, admin: true });
      const csv = 'reg_no,name,dept,one_time_code\n' + r.slips.map((s) => [s.reg_no, s.name, s.dept, s.code].join(',')).join('\n') + '\n';
      const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
      $('#rosterOut').innerHTML = '<p class="msg ok">' + r.count + ' students loaded. ' + esc(r.note) + '</p><a class="btn gold" download="code-slips.csv" href="' + url + '">Download one-time code slips (CSV)</a>' +
        '<div class="slips">' + r.slips.slice(0, 12).map((s) => esc(s.reg_no + '  ' + s.code + '  ' + s.name)).join('<br>') + (r.slips.length > 12 ? '<br>…' : '') + '</div>';
      await refreshStats();
    } catch (e) { $('#rosterOut').innerHTML = '<p class="msg bad">' + esc(e.message) + '</p>'; } finally { busy(btn, false); }
  }

  // ------------------------------------------------------------------ wiring
  function wire() {
    window.addEventListener('hashchange', route);
    $('#btnLogin').onclick = doLogin;
    $('#otp').addEventListener('keydown', (e) => { if (e.key === 'Enter') doLogin(); });
    $('#btnDemoVoter').onclick = demoVoter;
    $('#btnGetToken').onclick = getToken;
    $('#btnToBallot').onclick = () => { voteStep('choose'); renderBallot(); };
    $('#ballotPosts').addEventListener('click', (e) => {
      const b = e.target.closest('.cand');
      if (!b) return;
      S.choices[b.dataset.post] = b.dataset.cand;
      renderBallot();
      const next = b.closest('.post').nextElementSibling;
      if (next && !S.choices[next.querySelector('.cand').dataset.post]) next.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    $('#btnReview').onclick = review;
    $('#btnBackChoose').onclick = () => { voteStep('choose'); renderBallot(); };
    $('#btnCast').onclick = cast;
    $('#btnCheckReceipt').onclick = () => checkReceipt(false);
    $('#btnNewVoter').onclick = () => {
      if (S.wallet && !window.confirm('Forget this ballot token and receipt on this device?')) return;
      if (S.el && S.el.election) store.del('cv.wallet.' + S.el.election.eid);
      S.wallet = null; S.choices = {}; S.found = null; S.session = null;
      msg('#receiptMsg', '');
      voteStep('login');
    };
    $('#btnDemoReset').onclick = (e) => demoReset(e.target);
    $('#btnSim').onclick = (e) => simulate(10, e.target);
    $('#btnSim2').onclick = (e) => simulate(parseInt($('#simCount').value, 10) || 10, e.target);
    $('#btnFlush').onclick = async () => {
      try { const r = await api('/api/admin/flush', { body: {}, admin: true }); toast(r.posted + ' ballots posted from the mix'); refreshStats(); } catch (e) { toast(e.message); }
    };
    $('#btnAdvance').onclick = advance;
    $('#btnVerifyBrowser').onclick = (e) => verifyBrowser(e.target);
    $('#btnVerifyServer').onclick = (e) => verifyServer(e.target);
    $('#boardFilter').onchange = renderBoard;
    $('#btnMoreBoard').onclick = () => { S.boardAll = true; renderBoard(); };
    $('#btnLookup').onclick = lookup;
    $('#receiptLookup').addEventListener('keydown', (e) => { if (e.key === 'Enter') lookup(); });
    $('#attackGrid').addEventListener('click', (e) => {
      const b = e.target.closest('[data-attack]');
      if (b) return runAttack(b.dataset.attack, b);
      if (e.target.closest('[data-restore]')) return restoreBoard();
      const see = e.target.closest('[data-see]');
      if (see) { S.highlight = parseInt(see.dataset.see, 10); S.boardAll = false; }
      return undefined;
    });
    $$('[data-phase]').forEach((b) => {
      b.onclick = async () => {
        busy(b, true);
        try {
          await api('/api/admin/phase', { body: { phase: b.dataset.phase }, admin: true });
          msg('#adminMsg', 'Phase is now ' + b.dataset.phase, 'ok');
          await refreshStats();
        } catch (e) { msg('#adminMsg', e.message, 'bad'); } finally { busy(b, false); }
      };
    });
    $('#btnUnlock').onclick = async () => {
      try { await api('/api/admin/unlock', { body: { reg_no: $('#unlockReg').value }, admin: true }); msg('#adminMsg', 'Unlocked', 'ok'); } catch (e) { msg('#adminMsg', e.message, 'bad'); }
    };
    $('#btnCreate').onclick = (e) => createElection(e.target);
    $('#btnRoster').onclick = (e) => uploadRoster(e.target);
    $('#btnSampleRoster').onclick = async () => {
      try {
        const r = await fetch('/api/sample/roster.csv', { cache: 'no-store' });
        $('#rosterCsv').value = (await r.text()).split('\n').slice(0, 41).join('\n');
      } catch (e) { toast(e.message); }
    };
    $('#rosterFile').onchange = (e) => {
      const f = e.target.files[0];
      if (!f) return;
      const rd = new FileReader();
      rd.onload = () => { $('#rosterCsv').value = rd.result; };
      rd.readAsText(f);
    };
    $('#adminKey').addEventListener('input', (e) => { S.adminKey = e.target.value; store.set('cv.admin', S.adminKey); });
    const now = new Date();
    $('#elOpens').value = toLocalInput(now);
    $('#elCloses').value = toLocalInput(new Date(now.getTime() + 8 * 3600 * 1000));
  }

  async function boot() {
    wire();
    try {
      S.info = await api('/api/info');
    } catch (e) { S.info = {}; }
    await loadElection();
    S.adminKey = store.get('cv.admin') || S.info.demo_admin_key || '';
    $('#adminKey').value = S.adminKey;
    if (S.info.demo_admin_key) $('#adminKeyHint').textContent = 'Demo admin key pre-filled (' + S.info.demo_admin_key + '). Admin can run phases but can never see or change votes.';
    $('#voteUrl').textContent = S.info.vote_url || '-';
    if (S.el && S.el.keys) {
      $('#keyFps').innerHTML = [['issuer', 'Token issuer (blind signatures)'], ['board', 'Bulletin board (checkpoints, result)'], ['trustee', 'Trustee (sealed openings)']]
        .map(([k, l]) => '<li><span>' + esc(l) + '</span><code>' + esc(S.el.keys[k].fp) + '</code></li>').join('');
    }
    if (!S.info.lan) $('#voteUrlHint').textContent = 'Start the server with  python app.py --host 0.0.0.0  and phones on the same Wi-Fi can open this page to vote.';
    await refreshStats();
    route();
    checkIntegrity();
    setInterval(() => { if (!document.hidden) refreshStats(); }, 3000);
  }
  boot();
})();
