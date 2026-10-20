/* CertChain front-end - vanilla JS, no external libraries. */
(function () {
  "use strict";

  var $ = function (id) { return document.getElementById(id); };
  var state = { institutions: [], certTypes: [] };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function short(h, n) { h = String(h || ""); n = n || 10; return h.length > n + 2 ? h.slice(0, n) + "…" : h; }
  function hashHtml(h, n) {
    h = String(h || "");
    var m = h.match(/^0*/)[0];
    var rest = h.slice(m.length);
    var shown = n ? rest.slice(0, n) + (rest.length > n ? "…" : "") : rest;
    return '<span class="zeros">' + m + "</span>" + esc(shown);
  }
  function toast(msg) {
    var t = $("toast");
    t.textContent = msg;
    t.classList.add("show");
    clearTimeout(toast._t);
    toast._t = setTimeout(function () { t.classList.remove("show"); }, 2600);
  }

  function api(path, body) {
    var opts = body === undefined ? {} : {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
    };
    return fetch(path, opts).then(function (r) {
      return r.json().then(function (data) {
        if (!r.ok) { var e = new Error(data.error || ("HTTP " + r.status)); e.status = r.status; throw e; }
        return data;
      });
    });
  }

  function busy(btn, p) {
    if (btn) btn.disabled = true;
    return p.then(function (v) { if (btn) btn.disabled = false; return v; },
      function (e) { if (btn) btn.disabled = false; throw e; });
  }

  /* ---------- tabs & routing ---------- */
  function showTab(name) {
    document.querySelectorAll(".tab").forEach(function (t) { t.classList.toggle("active", t.dataset.tab === name); });
    document.querySelectorAll(".panel").forEach(function (p) { p.classList.toggle("active", p.id === "panel-" + name); });
    if (name === "security") loadSecurity();
    if (name === "issue") loadCerts();
  }
  document.querySelectorAll(".tab").forEach(function (t) {
    t.addEventListener("click", function () { showTab(t.dataset.tab); });
  });

  /* ---------- stats + strip + explorer ---------- */
  function refresh() {
    return Promise.all([loadStats(), loadChain()]);
  }
  function loadStats() {
    return api("/api/stats").then(function (s) {
      $("s-blocks").textContent = s.blocks;
      $("s-certs").textContent = s.certificates;
      $("s-revoked").textContent = s.revocations;
      $("s-inst").textContent = s.institutions;
      $("s-diff").textContent = s.difficulty + " hex 0s";
      $("s-val").textContent = s.validation_ms.toFixed(0) + " ms";
      $("s-tip").innerHTML = hashHtml(s.tip_hash, 14);
      $("s-tip").title = s.tip_hash;
      var pill = $("integrity");
      pill.className = "pill " + (s.chain_valid ? "ok" : "bad");
      pill.lastElementChild.textContent = s.chain_valid ? "Chain valid" : "Chain BROKEN at block " + s.broken_blocks.join(", ");
    });
  }

  function loadChain() {
    return api("/api/chain").then(function (c) {
      renderStrip(c.blocks);
      renderExplorer(c);
    });
  }

  function renderStrip(blocks) {
    var html = "";
    blocks.forEach(function (b, i) {
      if (i > 0) html += '<div class="link ' + (b.link_ok ? "" : "bad") + '" title="prev_hash link"></div>';
      var certs = b.records.filter(function (r) { return r.type === "certificate"; }).length;
      var label = i === 0 ? "genesis" : certs + " cert" + (certs === 1 ? "" : "s");
      if (b.records.some(function (r) { return r.type === "revocation"; })) label += " +rev";
      html += '<div class="chip ' + (b.ok ? "" : "bad") + '" data-block="' + i + '" title="' + esc(b.issuer_name) + '"><b>#' + i + " " + esc(label) +
        "</b><span>" + esc(short(b.hash, 10)) + "</span></div>";
    });
    $("strip").innerHTML = html;
  }
  $("strip").addEventListener("click", function (e) {
    var chip = e.target.closest(".chip");
    if (!chip) return;
    showTab("explorer");
    var el = $("block-" + chip.dataset.block);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
  });

  var CHECK_LABEL = { index: "index", prev_link: "link", block_hash: "hash", pow: "PoW",
    merkle_root: "Merkle", signature: "signature", records: "records", timestamp: "time", structure: "structure" };

  function renderExplorer(c) {
    var v = c.validation;
    $("x-validation").innerHTML = v.valid
      ? '<div class="notice ok">All ' + c.blocks.length + " blocks validated in " + v.validation_ms.toFixed(1) + " ms: hash links, PoW, Merkle roots and signatures intact.</div>"
      : '<div class="notice bad"><b>Chain broken.</b><br>' + v.errors.map(esc).join("<br>") + "</div>";
    var html = "";
    c.blocks.forEach(function (b, i) {
      var recs = b.records.map(function (r) {
        if (r.type === "certificate") return '<span class="rec" data-cert="' + esc(r.cert_id) + '" title="' + esc(r.student_name + " - " + r.cert_type + " - CGPA " + r.cgpa) + '">' + esc(r.cert_id) + "</span>";
        if (r.type === "revocation") return '<span class="rec rev" data-cert="' + esc(r.cert_id) + '" title="' + esc(r.reason) + '">revoke ' + esc(r.cert_id) + "</span>";
        return '<span class="rec auth" title="registered issuer">authority: ' + esc(r.inst_id) + "</span>";
      }).join("");
      var checks = b.checks.map(function (k) {
        return '<span class="' + (k.ok ? "ok" : "bad") + '" title="' + esc(k.detail) + '">' + (k.ok ? "✓ " : "✗ ") + esc(CHECK_LABEL[k.name] || k.name) + "</span>";
      }).join("");
      var next = c.blocks[i + 1];
      html += '<article class="block ' + (b.ok ? "" : "bad") + '" id="block-' + i + '">' +
        '<div class="bh"><b>Block #' + i + "</b><span class=\"meta\">" + esc((b.timestamp || "").replace("T", " ").replace("Z", " UTC")) + "</span></div>" +
        '<div class="meta">signed by <b>' + esc(b.issuer_name) + "</b></div>" +
        "<dl><dt>hash</dt><dd>" + hashHtml(b.hash, 30) + "</dd>" +
        "<dt>prev</dt><dd>" + hashHtml(b.prev_hash, 30) + "</dd>" +
        "<dt>merkle</dt><dd>" + esc(short(b.merkle_root, 30)) + "</dd>" +
        "<dt>nonce</dt><dd>" + esc(b.nonce) + " (difficulty " + esc(b.difficulty) + ")</dd>" +
        "<dt>signature</dt><dd>" + esc(short(b.signature, 30)) + "</dd></dl>" +
        '<div class="recs">' + recs + "</div>" +
        '<div class="checks">' + checks + "</div>" +
        (next ? '<span class="arrow ' + (next.link_ok ? "" : "bad") + '" title="next block stores this hash">' + (next.link_ok ? "→" : "✕") + "</span>" : "") +
        "</article>";
    });
    $("x-blocks").innerHTML = html;
  }
  $("x-blocks").addEventListener("click", function (e) {
    var r = e.target.closest(".rec[data-cert]");
    if (!r) return;
    showTab("verify");
    $("v-id").value = r.dataset.cert;
    verifyId(r.dataset.cert);
  });

  /* ---------- verify ---------- */
  function verdictClass(res) {
    if (res.valid) return "ok";
    if (res.verdict === "REVOKED") return "warn";
    return "bad";
  }

  function renderResult(res, el, opts) {
    opts = opts || {};
    var cls = verdictClass(res);
    var icon = cls === "ok" ? "✓" : (cls === "warn" ? "!" : "✗");
    var r = res.record;
    var html = '<div class="verdict ' + cls + '"><div class="icon">' + icon + '</div><div><div class="big">' + esc(res.verdict) +
      '</div><div class="txt">' + esc(res.summary) + "</div></div>" +
      (res.verify_ms != null ? '<div class="ms">verified in<br><b>' + res.verify_ms.toFixed(1) + " ms</b></div>" : "") + "</div>";
    if (r) {
      html += '<div class="kv">' +
        kv("Certificate ID", r.cert_id) + kv("Student", r.student_name) + kv("Register no.", r.register_no) +
        kv("Programme", r.programme) + kv("CGPA", r.cgpa) + kv("Type", r.cert_type) +
        kv("Issued by", res.issuer && res.issuer.name ? res.issuer.name : r.issuer_id) + kv("Issue date", r.issue_date) +
        kv("Block", "#" + res.block_index) + "</div>";
    }
    html += '<ul class="steps">' + res.steps.map(function (s) {
      return '<li class="' + (s.ok ? "ok" : "bad") + '"><span class="mark">' + (s.ok ? "✓" : "✗") + "</span><div>" +
        '<div class="t">' + esc(s.title) + '</div><div class="d">' + esc(s.detail) + '</div><div class="w">' + esc(s.why) + "</div></div></li>";
    }).join("") + "</ul>";
    if (r && !opts.noLinks && res.verdict !== "INVALID") {
      html += '<div class="actions"><a class="btn small" href="certificate.html?id=' + encodeURIComponent(r.cert_id) + '" target="_blank" rel="noopener">Printable certificate + QR</a>' +
        '<button class="small" data-dl="' + esc(r.cert_id) + '">Download certificate JSON</button></div>';
    }
    el.innerHTML = html;
  }
  function kv(k, v) { return '<div><div class="k">' + esc(k) + '</div><div class="val">' + esc(v) + "</div></div>"; }

  function verifyId(id, code) {
    id = (id || "").trim();
    if (!id) { toast("Enter a certificate ID"); return Promise.resolve(); }
    return busy($("btn-verify"), api("/api/verify", { cert_id: id, code: code || null }))
      .then(function (res) {
        renderResult(res, $("v-result"));
        if (window.innerWidth < 1100) $("v-result").scrollIntoView({ behavior: "smooth", block: "start" });
      })
      .catch(function (e) { $("v-result").innerHTML = '<div class="notice bad">' + esc(e.message) + "</div>"; });
  }
  function verifyBundleText(text) {
    var obj;
    try { obj = JSON.parse(text); } catch (e) { toast("That is not valid JSON"); return; }
    var bundle = obj && obj.bundle ? obj.bundle : obj;
    busy($("btn-verify-json"), api("/api/verify", { bundle: bundle }))
      .then(function (res) { renderResult(res, $("v-result")); })
      .catch(function (e) { $("v-result").innerHTML = '<div class="notice bad">' + esc(e.message) + "</div>"; });
  }

  $("btn-verify").addEventListener("click", function () { verifyId($("v-id").value, $("v-code").value); });
  $("v-id").addEventListener("keydown", function (e) { if (e.key === "Enter") verifyId($("v-id").value, $("v-code").value); });
  $("v-samples").addEventListener("click", function (e) {
    var b = e.target.closest("button[data-id]");
    if (!b) return;
    $("v-id").value = b.dataset.id;
    $("v-code").value = "";
    verifyId(b.dataset.id);
  });
  $("btn-verify-json").addEventListener("click", function () { verifyBundleText($("v-json").value); });
  $("v-file").addEventListener("change", function () {
    var f = this.files[0];
    if (!f) return;
    var rd = new FileReader();
    rd.onload = function () { $("v-json").value = rd.result; verifyBundleText(rd.result); };
    rd.readAsText(f);
    this.value = "";
  });
  $("btn-forge").addEventListener("click", function () {
    api("/api/certificate/KSRCE-26-00001").then(function (c) {
      var b = c.bundle;
      var old = b.record.cgpa;
      b.record.cgpa = "9.99";
      delete b.record_hash;
      $("v-json").value = JSON.stringify(b, null, 1);
      toast("Downloaded a genuine certificate and changed CGPA " + old + " → 9.99");
      verifyBundleText($("v-json").value);
    });
  });

  function download(name, text, type) {
    var a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type: type || "application/json" }));
    a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 500);
  }
  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-dl]");
    if (!b) return;
    api("/api/certificate/" + encodeURIComponent(b.dataset.dl)).then(function (c) {
      download(b.dataset.dl + ".certchain.json", JSON.stringify(c.bundle, null, 2));
    }).catch(function (err) { toast(err.message); });
  });

  /* ---------- issue ---------- */
  function loadInstitutions() {
    return api("/api/institutions").then(function (d) {
      state.institutions = d.institutions;
      state.certTypes = d.cert_types;
      document.querySelectorAll(".issuer-select").forEach(function (sel) {
        var cur = sel.value;
        sel.innerHTML = d.institutions.map(function (i) { return '<option value="' + esc(i.id) + '">' + esc(i.name) + "</option>"; }).join("");
        if (cur) sel.value = cur;
      });
      $("i-type").innerHTML = d.cert_types.map(function (t) { return "<option>" + esc(t) + "</option>"; }).join("");
    });
  }
  function today() { return new Date().toISOString().slice(0, 10); }
  $("i-date").value = today();

  var SAMPLES = [
    ["Lakshmi R.", "KSR22CS141", "B.E. Computer Science and Engineering", "8.91"],
    ["Mohan Kumar S.", "KSR22EC077", "B.E. Electronics and Communication Engineering", "7.48"],
    ["Revathi P.", "KSR22IT032", "B.Tech Information Technology", "9.12"]
  ];
  $("btn-fill").addEventListener("click", function () {
    var s = SAMPLES[Math.floor(Math.random() * SAMPLES.length)];
    $("i-name").value = s[0]; $("i-reg").value = s[1]; $("i-prog").value = s[2]; $("i-cgpa").value = s[3];
    $("i-date").value = today(); $("i-type").value = "Degree Certificate";
  });
  $("btn-issue").addEventListener("click", function () {
    var body = {
      issuer_id: $("i-issuer").value, student_name: $("i-name").value, register_no: $("i-reg").value,
      programme: $("i-prog").value, cgpa: $("i-cgpa").value, issue_date: $("i-date").value, cert_type: $("i-type").value
    };
    busy(this, api("/api/issue", body)).then(function (r) {
      $("i-result").innerHTML = '<div class="notice ok"><b>Issued ' + esc(r.cert_id) + "</b> in block #" + r.block_index +
        " - mined in " + r.mining.mining_ms.toFixed(0) + " ms (" + r.mining.attempts.toLocaleString() + " hashes), signed in " +
        r.mining.signing_ms.toFixed(1) + " ms.<br>Verification code <b>" + esc(r.bundle.verification_code) + "</b> &middot; hash " +
        hashHtml(r.block_hash, 14) + '</div><div class="actions"><a class="btn small primary" href="certificate.html?id=' +
        encodeURIComponent(r.cert_id) + '" target="_blank" rel="noopener">Open printable certificate</a><button class="small" data-dl="' +
        esc(r.cert_id) + '">Download JSON</button></div>';
      refresh(); loadCerts();
    }).catch(function (e) { $("i-result").innerHTML = '<div class="notice bad">' + esc(e.message) + "</div>"; });
  });

  $("btn-sample-csv").addEventListener("click", function () {
    fetch("/api/sample.csv").then(function (r) { return r.text(); }).then(function (t) { $("b-csv").value = t; });
  });
  $("b-file").addEventListener("change", function () {
    var f = this.files[0];
    if (!f) return;
    var rd = new FileReader();
    rd.onload = function () { $("b-csv").value = rd.result; };
    rd.readAsText(f);
    this.value = "";
  });
  $("btn-bulk").addEventListener("click", function () {
    busy(this, api("/api/issue/bulk", { issuer_id: $("b-issuer").value, csv: $("b-csv").value })).then(function (r) {
      $("b-result").innerHTML = '<div class="notice ok"><b>' + r.issued + " certificates</b> sealed in block #" + r.block_index +
        " (Merkle root " + esc(short(r.merkle_root, 12)) + ", mined in " + r.mining.mining_ms.toFixed(0) + " ms).<br>" +
        r.cert_ids.map(function (id) { return '<a href="certificate.html?id=' + encodeURIComponent(id) + '" target="_blank" rel="noopener">' + esc(id) + "</a>"; }).join(", ") + "</div>";
      refresh(); loadCerts();
    }).catch(function (e) { $("b-result").innerHTML = '<div class="notice bad">' + esc(e.message) + "</div>"; });
  });

  $("btn-revoke").addEventListener("click", function () {
    busy(this, api("/api/revoke", { issuer_id: $("r-issuer").value, cert_id: $("r-id").value, reason: $("r-reason").value }))
      .then(function (r) {
        $("r-result").innerHTML = '<div class="notice ok">Revocation of <b>' + esc(r.cert_id) + "</b> signed (" + esc(short(r.signature, 16)) +
          ") and recorded in block #" + r.block_index + ".</div>";
        refresh(); loadCerts();
      }).catch(function (e) { $("r-result").innerHTML = '<div class="notice bad">' + esc(e.message) + "</div>"; });
  });

  var searchT;
  $("c-search").addEventListener("input", function () { clearTimeout(searchT); searchT = setTimeout(loadCerts, 200); });
  function loadCerts() {
    return api("/api/certificates?q=" + encodeURIComponent($("c-search").value)).then(function (d) {
      $("c-table").innerHTML = d.certificates.slice().reverse().map(function (c) {
        return "<tr><td class=\"mono\">" + esc(c.cert_id) + "</td><td>" + esc(c.student_name) + "<br><span class=\"mono\" style=\"color:var(--muted)\">" + esc(c.register_no) +
          "</span></td><td>" + esc(c.cert_type) + "</td><td>" + esc(c.cgpa) + "</td><td>" +
          (c.revoked ? '<span class="tag bad">revoked</span>' : '<span class="tag ok">active</span>') +
          '</td><td><a class="btn small" href="certificate.html?id=' + encodeURIComponent(c.cert_id) + '" target="_blank" rel="noopener">Print</a></td></tr>';
      }).join("") || '<tr><td colspan="6" class="c">No matches</td></tr>';
    });
  }

  /* ---------- tamper ---------- */
  var CHECK_COLS = ["index", "prev_link", "block_hash", "pow", "merkle_root", "signature", "records", "timestamp"];
  function renderMatrix(rep) {
    var html = '<div class="notice ' + (rep.valid ? "ok" : "bad") + '">' + (rep.valid
      ? "<b>Chain VALID</b> - " + rep.block_count + " blocks checked in " + rep.validation_ms.toFixed(1) + " ms."
      : "<b>Chain BROKEN</b> at block(s) " + rep.broken_blocks.join(", ") + "<br>" + rep.errors.map(esc).join("<br>")) + "</div>";
    html += '<div class="tablewrap" style="margin-top:12px"><table class="matrix"><thead><tr><th>Block</th>' +
      CHECK_COLS.map(function (c) { return "<th>" + esc(CHECK_LABEL[c]) + "</th>"; }).join("") + "</tr></thead><tbody>";
    rep.blocks.forEach(function (b) {
      var map = {};
      b.checks.forEach(function (c) { map[c.name] = c; });
      html += '<tr class="' + (b.ok ? "" : "bad") + '"><td><b>#' + b.index + '</b> <span class="mono">' + esc(short(b.hash, 8)) + "</span></td>" +
        CHECK_COLS.map(function (c) {
          var k = map[c];
          if (!k) return "<td>-</td>";
          return '<td title="' + esc(k.detail) + '"><span class="' + (k.ok ? "yes" : "no") + '">' + (k.ok ? "✓" : "✗") + "</span></td>";
        }).join("") + "</tr>";
    });
    html += "</tbody></table></div>";
    $("t-matrix").innerHTML = html;
  }
  function doTamper(mode, btn) {
    var id = $("t-id").value.trim();
    busy(btn, api("/api/tamper", { mode: mode, cert_id: id || null })).then(function (r) {
      var log = r.attacker_steps.map(function (s) { return "$ " + esc(s); }).join("\n");
      log += '\n\n<span class="r">&gt; validator: ' + esc(r.validation.errors.join("\n> validator: ")) + "</span>";
      log += '\n<span class="r">&gt; verdict for ' + esc(r.cert_id) + ": " + esc(r.verification.verdict) + "</span>";
      $("t-log").innerHTML = log;
      renderMatrix(r.validation);
      renderResult(r.verification, $("t-verify"), { noLinks: true });
      refresh();
    }).catch(function (e) { toast(e.message); });
  }
  $("btn-tamper-edit").addEventListener("click", function () { doTamper("edit", this); });
  $("btn-tamper-rehash").addEventListener("click", function () { doTamper("rehash", this); });
  $("btn-restore").addEventListener("click", function () {
    var id = $("t-id").value.trim() || "KSRCE-26-00003";
    busy(this, api("/api/restore", {})).then(function (r) {
      $("t-log").innerHTML = '<span class="g">$ ' + esc(r.message) + "\n&gt; validator: chain " + (r.validation.valid ? "VALID" : "still BROKEN") + "</span>";
      renderMatrix(r.validation);
      refresh();
      return api("/api/verify", { cert_id: id }).then(function (v) { renderResult(v, $("t-verify"), { noLinks: true }); });
    }).catch(function (e) { toast(e.message); });
  });
  $("btn-validate").addEventListener("click", function () {
    busy(this, api("/api/validate")).then(function (r) { renderMatrix(r); refresh(); }).catch(function (e) { toast(e.message); });
  });

  /* ---------- security ---------- */
  var secLoaded = false;
  function loadSecurity() {
    if (secLoaded) return;
    secLoaded = true;
    api("/api/security").then(function (d) {
      $("sec-threats").innerHTML = d.threats.map(function (t) {
        return '<div class="threat"><h4>' + esc(t.threat) + "</h4><p><b>Attack:</b> " + esc(t.attack) + "</p><p><b>Defence:</b> " +
          esc(t.defence) + '</p><div class="m"><span class="tag brand">' + esc(t.mechanism) + "</span></div></div>";
      }).join("");
      $("sec-limits").innerHTML = d.limits.map(function (l) { return "<li>" + esc(l) + "</li>"; }).join("");
    });
    api("/api/institutions").then(function (d) {
      $("sec-inst").innerHTML = d.institutions.map(function (i) {
        return "<tr><td class=\"mono\">" + esc(i.id) + "</td><td>" + esc(i.name) + "</td><td>" + esc(i.city) + '</td><td class="mono">' +
          esc(short(i.public_key, 24)) + '</td><td class="c">' + i.certificates + "</td></tr>";
      }).join("");
    });
  }

  /* ---------- demo ---------- */
  $("btn-demo").addEventListener("click", function () {
    busy(this, api("/api/demo/reset", {})).then(function () {
      $("t-log").textContent = "$ waiting for an attack...";
      $("t-matrix").innerHTML = "";
      return Promise.all([refresh(), loadInstitutions()]);
    }).then(function () {
      showTab("verify");
      $("v-id").value = "KSRCE-26-00001";
      $("v-code").value = "";
      return verifyId("KSRCE-26-00001");
    }).then(function () { toast("Demo ledger loaded: 6 blocks, 20 certificates"); })
      .catch(function (e) { toast(e.message); });
  });

  function route() {
    var h = decodeURIComponent(location.hash || "");
    var m = h.match(/^#verify=([A-Za-z0-9\-]+)/);
    if (m) {
      showTab("verify");
      $("v-id").value = m[1];
      verifyId(m[1]);
      return;
    }
    m = h.match(/^#tab=(\w+)/);
    if (m && $("panel-" + m[1])) showTab(m[1]);
  }
  window.addEventListener("hashchange", route);

  Promise.all([refresh(), loadInstitutions()]).then(function () {
    api("/api/validate").then(renderMatrix);
    route();
  }).catch(function (e) { toast("Could not reach the server: " + e.message); });
})();
