/* StudyPilot front-end – vanilla JS, no libraries, no network calls except our own API. */
(function () {
  "use strict";

  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  var S = {
    doc: null, samples: [], summary: null, concepts: [], selectedConcept: null,
    quiz: { n: 8, seed: 0, questions: [], graded: false },
    deck: null, current: null, flipped: false, sessionAgain: [],
    mastery: null, tab: "summary"
  };

  // ------------------------------------------------------------------ utils
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function highlight(text, spans) {
    if (!spans || !spans.length) return esc(text);
    var sorted = spans.slice().sort(function (a, b) { return a[0] - b[0]; });
    var out = "", pos = 0;
    sorted.forEach(function (sp) {
      if (sp[0] < pos) return;
      out += esc(text.slice(pos, sp[0])) + "<mark>" + esc(text.slice(sp[0], sp[1])) + "</mark>";
      pos = sp[1];
    });
    return out + esc(text.slice(pos));
  }
  function blanks(text) { return esc(text).replace(/_____/g, '<span class="blank">?</span>'); }
  function pct(x) { return Math.round((x || 0) * 100) + "%"; }
  function toast(msg, ms) {
    var t = $("#toast");
    t.textContent = msg; t.hidden = false;
    clearTimeout(toast._t);
    toast._t = setTimeout(function () { t.hidden = true; }, ms || 2600);
  }
  function api(path, opts) {
    opts = opts || {};
    var init = { method: opts.method || "GET", headers: {} };
    if (opts.body !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(opts.body);
    }
    return fetch(path, init).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (data) {
        if (!r.ok) throw new Error(data.error || ("HTTP " + r.status));
        return data;
      });
    });
  }
  function fail(e) { toast("⚠ " + (e && e.message ? e.message : e), 4000); }
  function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } }

  // ------------------------------------------------------------------ theme
  function applyTheme(t) {
    if (t) document.documentElement.setAttribute("data-theme", t);
    else document.documentElement.removeAttribute("data-theme");
  }
  applyTheme(store("sp-theme"));
  $("#theme-btn").addEventListener("click", function () {
    var cur = document.documentElement.getAttribute("data-theme") ||
      (window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    var next = cur === "dark" ? "light" : "dark";
    applyTheme(next); store("sp-theme", next);
  });

  // ------------------------------------------------------------------ notes input
  var ta = $("#notes-text");
  function updateWordCount() {
    var n = (ta.value.match(/[A-Za-z0-9]+/g) || []).length;
    $("#word-count").textContent = n + " words";
  }
  ta.addEventListener("input", updateWordCount);

  function setEditor(open) {
    $("#editor").hidden = !open;
    $("#btn-edit").setAttribute("aria-expanded", open ? "true" : "false");
    $("#btn-edit").textContent = open ? "Hide editor" : "Edit notes";
  }
  $("#btn-edit").addEventListener("click", function () { setEditor($("#editor").hidden); });

  function readFile(file) {
    if (!file) return;
    if (!/\.(txt|md|markdown)$/i.test(file.name) && !/^text\//.test(file.type)) {
      toast("Please choose a .txt or .md file"); return;
    }
    if (file.size > 300000) { toast("File too large (max ~300 KB of text)"); return; }
    var fr = new FileReader();
    fr.onload = function () {
      ta.value = String(fr.result || "");
      $("#doc-title").value = file.name.replace(/\.(txt|md|markdown)$/i, "");
      updateWordCount(); setEditor(true); analyze(null);
    };
    fr.readAsText(file);
  }
  $("#file-input").addEventListener("change", function (e) { readFile(e.target.files[0]); e.target.value = ""; });
  ["dragenter", "dragover"].forEach(function (ev) {
    ta.addEventListener(ev, function (e) { e.preventDefault(); ta.classList.add("drag"); });
  });
  ["dragleave", "drop"].forEach(function (ev) {
    ta.addEventListener(ev, function (e) { e.preventDefault(); ta.classList.remove("drag"); });
  });
  ta.addEventListener("drop", function (e) { readFile(e.dataTransfer.files[0]); });

  $("#btn-analyze").addEventListener("click", function () { analyze(null); });
  $("#btn-demo").addEventListener("click", function () {
    var first = S.samples[0];
    if (first) loadSample(first.id);
  });

  function renderSampleChips() {
    $("#sample-chips").innerHTML = S.samples.map(function (s) {
      var short = s.title.split("–").pop().trim();
      return '<button type="button" data-sample="' + esc(s.id) + '" title="' + esc(s.title) + '">' + esc(short) + "</button>";
    }).join("");
    $$("#sample-chips button").forEach(function (b) {
      b.addEventListener("click", function () { loadSample(b.getAttribute("data-sample")); });
    });
    markSample();
  }
  function markSample() {
    $$("#sample-chips button").forEach(function (b) {
      b.classList.toggle("on", !!(S.doc && S.doc.sample === b.getAttribute("data-sample")));
    });
  }

  function loadSample(id) {
    api("/api/samples/" + encodeURIComponent(id)).then(function (s) {
      ta.value = s.text; $("#doc-title").value = s.title; updateWordCount();
      return analyze(s.id);
    }).catch(fail);
  }

  function analyze(sample) {
    var text = ta.value;
    if (!text.trim()) { toast("Paste some notes first – or click “Load demo notes”."); return Promise.resolve(); }
    var btn = $("#btn-analyze");
    btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Analysing…';
    return api("/api/docs", { method: "POST", body: { title: $("#doc-title").value, text: text, sample: sample } })
      .then(function (res) { return openDoc(res.doc.id, true); })
      .catch(fail)
      .then(function () { btn.disabled = false; btn.textContent = "Analyse notes"; });
  }

  // ------------------------------------------------------------------ open doc
  function openDoc(id, fresh) {
    return api("/api/docs/" + id).then(function (doc) {
      S.doc = doc; S.sessionAgain = []; S.selectedConcept = null;
      S.quiz = { n: +$("#quiz-n").value, seed: 0, questions: [], graded: false };
      store("sp-doc", id);
      ta.value = doc.text; $("#doc-title").value = doc.title; updateWordCount();
      setEditor(false); markSample();
      renderStats(doc.stats);
      $("#empty-state").hidden = true;
      var slider = $("#sum-len");
      slider.max = Math.max(1, Math.min(15, doc.stats.sentences));
      slider.value = Math.max(1, Math.min(+slider.max, Math.round(doc.stats.sentences * 0.18) || 1));
      $("#sum-len-val").textContent = slider.value;
      renderSuggest(doc.suggested_questions || []);
      $("#ask-results").innerHTML = "";
      showTab(S.tab);
      if (fresh) toast("Analysed " + doc.stats.sentences + " sentences in " + doc.stats.build_ms + " ms – offline");
      return Promise.all([loadSummary(), loadConcepts(), loadQuiz(), loadDeck(), loadMastery()]);
    }).catch(fail);
  }

  function renderStats(st) {
    var box = $("#stats");
    box.hidden = false;
    box.innerHTML = [
      [st.words.toLocaleString(), "words"],
      [st.sentences, "sentences"],
      [st.concepts, "key concepts"],
      [st.cards, "flashcards"],
      [st.reading_min + " min", "to read in full"]
    ].map(function (x) { return '<div class="stat"><b>' + esc(x[0]) + "</b><span>" + esc(x[1]) + "</span></div>"; }).join("");
  }

  // ------------------------------------------------------------------ tabs
  function showTab(name) {
    S.tab = name;
    $$(".tab").forEach(function (t) {
      var on = t.getAttribute("data-tab") === name;
      t.classList.toggle("active", on); t.setAttribute("aria-selected", on ? "true" : "false");
    });
    $$(".panel").forEach(function (p) { p.hidden = !S.doc || p.id !== "tab-" + name; });
    if (name === "ask" && S.doc) setTimeout(function () { $("#ask-input").focus(); }, 50);
  }
  $$(".tab").forEach(function (t) {
    t.addEventListener("click", function () { showTab(t.getAttribute("data-tab")); });
  });

  // ------------------------------------------------------------------ summary
  $("#sum-len").addEventListener("input", function () { $("#sum-len-val").textContent = this.value; });
  $("#sum-len").addEventListener("change", function () { loadSummary(); });

  function loadSummary() {
    if (!S.doc) return Promise.resolve();
    return api("/api/docs/" + S.doc.id + "/summary?n=" + $("#sum-len").value).then(function (d) {
      S.summary = d; renderSummary();
    }).catch(fail);
  }

  function renderSummary() {
    var d = S.summary, byId = {};
    d.sentences.forEach(function (s) { byId[s.id] = s; });
    var maxScore = Math.max.apply(null, d.sentences.map(function (s) { return s.score; }));
    $("#summary-list").innerHTML = d.summary_ids.map(function (id) {
      var s = byId[id];
      return '<li id="sum-' + id + '"><p class="s-text">' + esc(s.text) + "</p>" +
        '<div class="s-meta"><span>TextRank <b>' + s.score.toFixed(2) + '×</b> avg</span>' +
        '<span class="bar"><i style="width:' + Math.round(100 * s.score / maxScore) + '%"></i></span>' +
        "<span>rank #" + s.rank + " of " + d.stats.total + "</span>" +
        '<button type="button" class="why-btn" data-why="' + id + '">Why?</button></div>' +
        '<div class="why-box" id="why-' + id + '" hidden>' + whyHtml(s, byId) + "</div></li>";
    }).join("");
    $$(".why-btn").forEach(function (b) {
      b.addEventListener("click", function () {
        var box = $("#why-" + b.getAttribute("data-why")); box.hidden = !box.hidden;
      });
    });
    var st = d.stats;
    $("#sum-sub").textContent = "TextRank kept " + st.chosen + " of " + st.total +
      " sentences (" + pct(st.compression) + " of the words) – PageRank converged in " + st.iterations + " iterations.";
    $("#sum-stats").innerHTML =
      "<div><b>" + st.summary_words + "</b>words in summary</div>" +
      "<div><b>" + pct(st.compression) + "</b>of original length</div>" +
      "<div><b>" + st.minutes_saved + " min</b>reading saved</div>" +
      "<div><b>" + d.edges.length + "</b>similarity edges</div>";
    drawGraph(d);
    $("#all-sentences").innerHTML = d.sentences.map(function (s) {
      return '<div class="sent-row' + (s.in_summary ? " in" : "") + '"><span class="rk">#' + s.rank + "</span><span>" +
        esc(s.text) + '</span><span class="bar" title="' + s.score.toFixed(3) + '"><i style="width:' +
        Math.round(100 * s.score / maxScore) + '%"></i></span></div>';
    }).join("");
  }

  function whyHtml(s, byId) {
    var html = "Score <b>" + s.score.toFixed(2) + "</b> = this sentence's PageRank × number of sentences " +
      "(1.00 = average). It shares content words with <b>" + s.degree + "</b> other sentences. Strongest links:<ul>";
    s.neighbors.forEach(function (n) {
      var other = byId[n.id];
      html += "<li>w=" + n.weight.toFixed(2) + " with “" + esc(other.text.slice(0, 70)) + (other.text.length > 70 ? "…" : "") +
        "” via " + n.shared.map(function (t) { return '<span class="tag">' + esc(t) + "</span>"; }).join("") + "</li>";
    });
    return html + "</ul>";
  }

  function drawGraph(d) {
    var svg = $("#graph"), n = d.sentences.length, cx = 160, cy = 160, R = 128;
    if (!n) { svg.innerHTML = ""; return; }
    var pos = d.sentences.map(function (s, i) {
      var a = -Math.PI / 2 + 2 * Math.PI * i / n;
      return [cx + R * Math.cos(a), cy + R * Math.sin(a)];
    });
    var maxW = Math.max.apply(null, d.edges.map(function (e) { return e.w; }).concat([1e-9]));
    var maxS = Math.max.apply(null, d.sentences.map(function (s) { return s.score; }));
    var NS = "http://www.w3.org/2000/svg", html = "";
    d.edges.forEach(function (e) {
      var a = pos[e.a], b = pos[e.b];
      html += '<line x1="' + a[0].toFixed(1) + '" y1="' + a[1].toFixed(1) + '" x2="' + b[0].toFixed(1) + '" y2="' + b[1].toFixed(1) +
        '" stroke-width="' + (0.4 + 1.8 * e.w / maxW).toFixed(2) + '" stroke-opacity="' + (0.08 + 0.4 * e.w / maxW).toFixed(2) + '"/>';
    });
    d.sentences.forEach(function (s, i) {
      var r = 4 + 9 * Math.sqrt(s.score / maxS);
      html += '<circle data-id="' + s.id + '" class="' + (s.in_summary ? "n-in" : "n-out") + '" cx="' + pos[i][0].toFixed(1) + '" cy="' +
        pos[i][1].toFixed(1) + '" r="' + r.toFixed(1) + '"><title>#' + s.rank + " · " + s.score.toFixed(2) + "× – " + esc(s.text) + "</title></circle>";
      if (s.in_summary && r > 7) {
        html += '<text x="' + pos[i][0].toFixed(1) + '" y="' + (pos[i][1] + 3).toFixed(1) + '" text-anchor="middle">' +
          (d.summary_ids.indexOf(s.id) + 1) + "</text>";
      }
    });
    svg.setAttribute("xmlns", NS);
    svg.innerHTML = html;
    $$("circle", svg).forEach(function (c) {
      c.addEventListener("click", function () {
        var el = $("#sum-" + c.getAttribute("data-id"));
        if (el) { el.scrollIntoView({ behavior: "smooth", block: "center" }); el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash"); }
        else toast("Not in the summary – rank #" + d.sentences[+c.getAttribute("data-id")].rank);
      });
    });
  }

  // ------------------------------------------------------------------ concepts
  function loadConcepts() {
    return api("/api/docs/" + S.doc.id + "/concepts").then(function (d) {
      S.concepts = d.concepts; renderConcepts();
    }).catch(fail);
  }
  function renderConcepts() {
    $("#chips").innerHTML = S.concepts.map(function (c, i) {
      var size = (12.5 + 9 * c.weight).toFixed(1);
      var alpha = (0.35 + 0.65 * c.weight).toFixed(2);
      return '<button type="button" class="chip' + (S.selectedConcept === i ? " sel" : "") + '" data-i="' + i + '" style="font-size:' + size +
        'px;opacity:' + alpha + '">' + esc(c.phrase) + "<small>" + c.weight.toFixed(2) + "</small></button>";
    }).join("");
    $$("#chips .chip").forEach(function (b) {
      b.addEventListener("click", function () { S.selectedConcept = +b.getAttribute("data-i"); renderConcepts(); });
    });
    var c = S.concepts[S.selectedConcept == null ? 0 : S.selectedConcept];
    if (!c) { $("#concept-detail").innerHTML = '<p class="muted">No concepts found.</p>'; return; }
    var ws = Object.keys(c.word_scores).map(function (w) {
      return '<span class="tag">' + esc(w) + " " + c.word_scores[w].toFixed(2) + "</span>";
    }).join(" ");
    $("#concept-detail").innerHTML = '<div class="cd-card"><div class="cd-head"><h3>' + esc(c.phrase) + "</h3>" +
      '<div><button type="button" class="btn btn-ghost small" id="cd-ask">Ask about it</button> ' +
      '<button type="button" class="btn btn-ghost small" id="cd-cards">Study cards</button></div></div>' +
      '<div class="kv"><span>importance <b>' + c.weight.toFixed(2) + "</b></span><span>appears <b>" + c.occurrences + "×</b></span>" +
      "<span>RAKE <b>" + c.rake.toFixed(2) + "</b></span><span>type <b>" + esc(c.type.suffix) + (c.type.acronym ? ", acronym" : "") + "</b></span>" +
      (c.subject ? "<span><b>opens a sentence</b> (definition-like) ×2</span>" : "") + "</div>" +
      '<p class="muted small">Why: RAKE word scores (degree ÷ frequency) ' + ws +
      " are averaged, multiplied by a length bonus and by 1 + log₂(occurrences).</p>" +
      c.mentions.map(function (m) { return '<p class="mention">' + highlight(m.text, m.spans) + "</p>"; }).join("") + "</div>";
    $("#cd-ask").addEventListener("click", function () { askQuestion("What is " + c.phrase + "?"); });
    $("#cd-cards").addEventListener("click", function () { showTab("cards"); });
  }

  // ------------------------------------------------------------------ quiz
  $("#quiz-n").addEventListener("change", function () { S.quiz.n = +this.value; loadQuiz(); });
  $("#btn-new-quiz").addEventListener("click", function () { S.quiz.seed += 1; loadQuiz(); });

  function loadQuiz() {
    if (!S.doc) return Promise.resolve();
    S.quiz.n = +$("#quiz-n").value;
    return api("/api/docs/" + S.doc.id + "/quiz?n=" + S.quiz.n + "&seed=" + S.quiz.seed).then(function (d) {
      S.quiz.questions = d.questions; S.quiz.graded = false; renderQuiz();
    }).catch(fail);
  }
  function renderQuiz() {
    var qs = S.quiz.questions;
    $("#quiz-score").textContent = "";
    $("#btn-grade").hidden = false;
    if (!qs.length) { $("#quiz-form").innerHTML = '<p class="notice">Not enough material for a quiz yet – add more notes.</p>'; return; }
    $("#quiz-form").innerHTML = qs.map(function (q, i) {
      var body;
      if (q.kind === "mcq") {
        body = '<div class="opts">' + q.options.map(function (o) {
          return '<label class="opt"><input type="radio" name="' + q.id + '" value="' + esc(o) + '"><span>' + esc(o) + "</span></label>";
        }).join("") + "</div>";
      } else {
        body = '<input class="cloze-in" name="' + q.id + '" autocomplete="off" placeholder="Your answer…" aria-label="Answer"> <span class="muted small">hint: ' + esc(q.hint) + "</span>";
      }
      return '<div class="q" id="q-' + q.id + '"><div class="q-top"><span class="q-kind">' + (q.kind === "mcq" ? "Multiple choice" : "Fill the blank") +
        "</span>Question " + (i + 1) + " of " + qs.length + '</div><p class="q-prompt">' + blanks(q.prompt) + "</p>" + body + "</div>";
    }).join("");
  }
  $("#quiz-form").addEventListener("submit", function (e) {
    e.preventDefault();
    if (!S.doc || !S.quiz.questions.length) return;
    var answers = {};
    S.quiz.questions.forEach(function (q) {
      if (q.kind === "mcq") {
        var r = $('input[name="' + q.id + '"]:checked'); answers[q.id] = r ? r.value : "";
      } else answers[q.id] = ($('input[name="' + q.id + '"]').value || "");
    });
    api("/api/docs/" + S.doc.id + "/quiz/grade", { method: "POST", body: { n: S.quiz.n, seed: S.quiz.seed, answers: answers } })
      .then(function (res) { showGrades(res); renderMastery(res.mastery); })
      .catch(fail);
  });
  function showGrades(res) {
    res.results.forEach(function (r) {
      var box = $("#q-" + r.id); if (!box) return;
      box.classList.remove("ok", "no"); box.classList.add(r.correct ? "ok" : "no");
      $$(".opt", box).forEach(function (o) {
        var v = $("input", o).value;
        o.classList.toggle("right", v.toLowerCase() === r.expected.toLowerCase());
        o.classList.toggle("wrong", !r.correct && v === r.given);
      });
      var old = $(".verdict", box); if (old) old.remove();
      var why = "From sentence ranked #" + r.why.sentence_rank + " by TextRank (" + r.why.sentence_score.toFixed(2) +
        "× avg); concept importance " + r.why.concept_weight.toFixed(2) + ".";
      if (r.distractors && r.distractors.length) {
        why += " Distractors chosen as similar concepts: " + r.distractors.map(function (d) {
          return "<b>" + esc(d.phrase) + "</b> (" + esc(d.why.join(", ")) + ")";
        }).join("; ") + ".";
      }
      var div = document.createElement("div");
      div.className = "verdict " + (r.correct ? "ok" : "no");
      div.innerHTML = (r.correct ? "✔ Correct" : "✘ " + (r.given ? "Not quite" : "Skipped") + " – answer: <b>" + esc(r.expected) + "</b>") +
        (r.kind === "cloze" && r.given ? ' <span class="muted">(' + esc(r.match) + ")</span>" : "") +
        '<div class="src">' + highlight(r.source, [r.answer_span]) + '</div><div class="muted small">' + why + "</div>";
      box.appendChild(div);
    });
    $("#quiz-score").textContent = "Score: " + res.score + " / " + res.total + " · saved to your progress";
    toast("Quiz graded – " + res.score + "/" + res.total + ". Readiness updated.");
  }

  // ------------------------------------------------------------------ flashcards
  function loadDeck() {
    if (!S.doc) return Promise.resolve();
    return api("/api/docs/" + S.doc.id + "/flashcards").then(function (d) { setDeck(d); }).catch(fail);
  }
  function setDeck(d) {
    S.deck = d;
    var queue = d.queue.slice();
    S.sessionAgain.forEach(function (id) { if (queue.indexOf(id) < 0) queue.push(id); });
    S.queue = queue;
    S.current = queue.length ? d.cards.filter(function (c) { return c.id === queue[0]; })[0] : null;
    S.flipped = false;
    renderCard();
  }
  function renderCard() {
    var d = S.deck, c = S.current;
    var cnt = d.counts;
    $("#deck-counts").innerHTML = '<span class="c-new">' + cnt["new"] + ' new</span><span class="c-due">' + (cnt.due + cnt.learning) +
      ' due / learning</span><span class="c-learned">' + cnt.learned + " learned</span>";
    var dueTotal = S.queue.length;
    $("#due-badge").hidden = !dueTotal; $("#due-badge").textContent = dueTotal;
    $("#flashcard").classList.toggle("flipped", false);
    if (!c) {
      $("#fc-kind").textContent = "All caught up";
      $("#fc-front").innerHTML = "🎉 Nothing due right now. SM-2 will bring cards back just before you are likely to forget them.";
      $("#fc-back").textContent = ""; $("#fc-answer").textContent = "";
      $$(".rate").forEach(function (b) { b.disabled = true; $("span", b).textContent = ""; });
    } else {
      $("#fc-kind").textContent = (c.kind === "definition" ? "Definition" : "Fill the blank") + " · " + c.status;
      $("#fc-front").innerHTML = blanks(c.front);
      $("#fc-answer").textContent = c.answer;
      $("#fc-back").innerHTML = highlight(c.back, [c.highlight]);
      $$(".rate").forEach(function (b) {
        b.disabled = true;
        $("span", b).textContent = c.preview[b.getAttribute("data-rating")];
      });
    }
    renderCardTable();
  }
  function flip() {
    if (!S.current) return;
    S.flipped = !S.flipped;
    $("#flashcard").classList.toggle("flipped", S.flipped);
    if (S.flipped) $$(".rate").forEach(function (b) { b.disabled = false; });
  }
  $("#flashcard").addEventListener("click", flip);
  $$(".rate").forEach(function (b) {
    b.addEventListener("click", function () { rate(b.getAttribute("data-rating")); });
  });
  function rate(rating) {
    if (!S.current || !S.flipped) return;
    var id = S.current.id;
    api("/api/docs/" + S.doc.id + "/flashcards/review", { method: "POST", body: { card_id: id, rating: rating } })
      .then(function (res) {
        S.sessionAgain = S.sessionAgain.filter(function (x) { return x !== id; });
        if (rating === "again") S.sessionAgain.push(id);
        $("#fc-explain").textContent = "“" + rating + "” → next review in " + res.next_in + ". " + res.explain + ".";
        setDeck(res.deck);
        renderMastery(res.mastery);
      }).catch(fail);
  }
  document.addEventListener("keydown", function (e) {
    if (S.tab !== "cards" || !S.doc) return;
    var tag = (e.target && e.target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    if (e.key === " " || e.key === "Enter") { e.preventDefault(); flip(); }
    var map = { "1": "again", "2": "hard", "3": "good", "4": "easy" };
    if (map[e.key]) rate(map[e.key]);
  });
  function renderCardTable() {
    var now = Date.now() / 1000;
    $("#card-table").innerHTML = "<tr><th>Card</th><th>Status</th><th>EF</th><th>Reps</th><th>Interval</th><th>Next review</th></tr>" +
      S.deck.cards.map(function (c) {
        var st = c.state, due = st.due ? (st.due <= now ? "now" : humanize(st.due - now)) : "–";
        return "<tr><td>" + esc(c.answer) + '</td><td><span class="st st-' + (c.status === "learning" ? "due" : c.status) + '">' + c.status +
          "</span></td><td>" + st.ef.toFixed(2) + "</td><td>" + st.reps + "</td><td>" + st.interval + " d</td><td>" + due + "</td></tr>";
      }).join("");
  }
  function humanize(s) {
    if (s < 3600) return "in " + Math.max(1, Math.round(s / 60)) + " min";
    if (s < 86400) return "in " + Math.round(s / 3600) + " h";
    return "in " + Math.round(s / 86400) + " d";
  }
  $("#btn-reset-cards").addEventListener("click", function () {
    if (!S.doc || !confirm("Reset all flashcard schedules for these notes?")) return;
    api("/api/docs/" + S.doc.id + "/flashcards/reset", { method: "POST", body: {} })
      .then(function (d) { S.sessionAgain = []; setDeck(d); loadMastery(); toast("Schedule reset"); }).catch(fail);
  });

  // ------------------------------------------------------------------ ask
  function renderSuggest(qs) {
    $("#suggest").innerHTML = qs.map(function (q) { return '<button type="button">' + esc(q) + "</button>"; }).join("");
    $$("#suggest button").forEach(function (b) { b.addEventListener("click", function () { askQuestion(b.textContent); }); });
  }
  function askQuestion(q) {
    showTab("ask");
    $("#ask-input").value = q;
    doAsk();
  }
  $("#ask-form").addEventListener("submit", function (e) { e.preventDefault(); doAsk(); });
  function doAsk() {
    var q = $("#ask-input").value.trim();
    if (!q || !S.doc) return;
    api("/api/docs/" + S.doc.id + "/ask", { method: "POST", body: { question: q, k: 3 } }).then(renderAnswers).catch(fail);
  }
  function renderAnswers(res) {
    var box = $("#ask-results");
    if (!res.results.length) {
      box.innerHTML = '<div class="notice">🤔 ' + esc(res.message || "No match.") + "</div>"; return;
    }
    var maxC = Math.max.apply(null, res.results.map(function (r) {
      return Math.max.apply(null, r.contributions.map(function (c) { return c.score; }));
    }));
    box.innerHTML = '<p class="muted small">Searched for <b>' + res.terms.map(esc).join(", ") + "</b>" +
      (res.missing_terms.length ? " · not in your notes: " + res.missing_terms.map(esc).join(", ") : "") +
      " · " + res.latency_ms + " ms</p>" +
      res.results.map(function (r, i) {
        return '<div class="answer' + (i === 0 ? " best" : "") + '"><div class="a-top"><span>' + (i === 0 ? "<b>Best passage</b>" : "Also relevant") +
          " · BM25 " + r.score.toFixed(2) + (r.section ? " · " + esc(r.section) : "") + '</span><span class="conf">confidence <span class="conf-' + r.label + '">' +
          r.label + " " + pct(r.confidence) + '</span><span class="bar"><i style="width:' + pct(r.confidence) + '"></i></span></span></div>' +
          '<p class="a-text">' + (r.before ? '<span class="a-ctx">' + esc(r.before) + " </span>" : "") + highlight(r.text, r.highlights) +
          (r.after ? '<span class="a-ctx"> ' + esc(r.after) + "</span>" : "") + "</p>" +
          '<details class="contrib"' + (i === 0 ? " open" : "") + '><summary class="muted small">Why this passage? BM25 term contributions · covers ' +
          pct(r.coverage) + " of the question's IDF weight</summary>" +
          r.contributions.map(function (c) {
            return '<div class="contrib-row"><span><mark>' + esc(c.term) + '</mark></span><span class="bar"><i style="width:' + Math.round(100 * c.score / maxC) +
              '%"></i></span><span class="num">' + c.score.toFixed(2) + " · tf " + c.tf + " · idf " + c.idf.toFixed(2) + "</span></div>";
          }).join("") + (r.definition_bonus > 0 ? '<div class="contrib-row"><span><b>definition bonus</b></span><span class="muted small">sentence opens with the asked term – looks like a definition</span><span class="num">+' +
            r.definition_bonus.toFixed(2) + "</span></div>" : "") + "</details></div>";
      }).join("");
  }

  // ------------------------------------------------------------------ mastery
  function loadMastery() {
    if (!S.doc) return Promise.resolve();
    return api("/api/docs/" + S.doc.id + "/mastery").then(renderMastery).catch(fail);
  }
  function renderMastery(m) {
    S.mastery = m;
    var C = 314.16;
    $("#ring-fg").setAttribute("stroke-dashoffset", (C * (1 - m.readiness / 100)).toFixed(1));
    $("#ready-pct").textContent = m.readiness + "%";
    $("#ready-level").textContent = m.level;
    var t = m.totals;
    $("#mini-stats").innerHTML = "<div><b>" + (t.quiz_accuracy == null ? "–" : pct(t.quiz_accuracy)) + "</b>quiz accuracy</div>" +
      "<div><b>" + t.cards_reviewed + "</b>cards reviewed</div>" +
      "<div><b>" + t.concepts_covered + "/" + t.concepts_total + "</b>concepts practised</div>";
    $("#study-next").innerHTML = m.study_next.map(function (s, i) {
      return '<li><span title="' + esc(s.reason) + '">' + esc(s.phrase) + '</span><button type="button" data-i="' + i + '">Ask</button></li>';
    }).join("") || '<li class="muted">Great – nothing urgent.</li>';
    $$("#study-next button").forEach(function (b) {
      b.addEventListener("click", function () { askQuestion("What is " + m.study_next[+b.getAttribute("data-i")].phrase + "?"); });
    });
    $("#mastery-list").innerHTML = m.concepts.slice(0, 8).map(function (c) {
      return '<li title="quiz ' + c.quiz.correct + "/" + c.quiz.attempts + ", card reviews " + c.cards.reviews + '"><div class="m-row"><span>' + esc(c.phrase) +
        "</span><span>" + (c.status === "not started" ? "not started" : pct(c.mastery)) + '</span></div><div class="m-bar"><i class="' +
        c.status + '" style="width:' + Math.max(c.status === "not started" ? 0 : 4, Math.round(100 * c.mastery)) + '%"></i></div></li>';
    }).join("");
  }

  // ------------------------------------------------------------------ boot
  function boot() {
    showTab("summary");
    api("/api/samples").then(function (d) { S.samples = d.samples; renderSampleChips(); }).catch(fail);
    api("/api/docs").then(function (d) {
      var want = store("sp-doc"), ids = d.docs.map(function (x) { return x.id; });
      var id = ids.indexOf(want) >= 0 ? want : (d.last_doc && ids.indexOf(d.last_doc) >= 0 ? d.last_doc : null);
      if (id) openDoc(id, false); else setEditor(true);
    }).catch(fail);
  }
  boot();
})();
