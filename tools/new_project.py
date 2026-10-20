"""Scaffold a new project that follows docs/BUILD_SPEC.md, ready to adapt to an on-the-spot problem.

    python tools/new_project.py "FloodWatch" --domain sustain --color "#0EA5E9" \\
        --tagline "Village flood alerts from river-level sensors"
    python tools/new_project.py --selftest      # generate into a temp dir, run its tests and server

Creates projects/NN-slug/ (next free number, port 8000+NN) with:
  app.py              stdlib ThreadingHTTPServer: static UI + JSON API (/api/health, /api/demo,
                      /api/analyze, /api/score), input validation, JSON errors
  <pkg>/core.py       an explainable example model (weighted z-scores -> logistic score, with
                      per-feature contributions) and a seeded demo-data generator: replace both
  static/             dashboard UI: Run demo, KPI tiles, SVG chart, ranked table with "why",
                      a try-it form and a how-it-works tab; light/dark; phone-friendly
  tests/              unit tests for the model and the API
  pitch.json, README.md, REPORT.md   with TODO placeholders for the deck and report
Everything else in tools/ (decks, report, videos, smoke test, CI) picks the new folder up as-is.
The template is generic boilerplate, like a framework's starter app; check the event rules on
using it (docs/STRATEGY.md, section 2).
"""
import argparse
import json
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DOMAINS = {
    "ai": "Artificial Intelligence & Machine Learning",
    "sustain": "Sustainability, CleanTech & Green Energy",
    "health": "HealthTech & Biomedical Innovation",
    "cyber": "Cybersecurity & Blockchain Technology",
    "agri": "Smart Agriculture & Rural Development (AgriTech)",
    "data": "Data Science & Analytics",
}
RESERVED = {"test", "tests", "json", "http", "html", "email", "random", "math", "core", "app", "static", "data", "docs"}

# ---------------------------------------------------------------- templates
# Placeholders: __NAME__, __TAGLINE__, __DOMAIN__, __COLOR__, __PKG__, __PORT__, __DIR__, __UPPER__

APP_PY = r'''"""__NAME__ - __TAGLINE__

Run:  python app.py [--host 127.0.0.1] [--port __PORT__]
Standard library only; works offline.
"""
import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from __PKG__ import core  # noqa: E402

STATIC = os.path.join(HERE, "static")
MAX_BODY = 256 * 1024
# Explicit types: the Windows registry can map .js to text/plain, which breaks module loading.
TYPES = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png",
         ".json": "application/json; charset=utf-8", ".ico": "image/x-icon"}


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


class Handler(BaseHTTPRequestHandler):
    server_version = "__NAME__/0.1"

    def log_message(self, fmt, *args):  # quieter console; set __UPPER___LOG=1 to see requests
        if os.environ.get("__UPPER___LOG"):
            super().log_message(fmt, *args)

    def _send(self, status, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json_body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ApiError(400, "bad Content-Length")
        if length > MAX_BODY:
            raise ApiError(413, "request body too large")
        try:
            return json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError(400, "body must be JSON")

    def _static(self, path):
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        full = os.path.realpath(os.path.join(STATIC, rel))
        if not full.startswith(os.path.realpath(STATIC) + os.sep) or not os.path.isfile(full):
            raise ApiError(404, "not found")
        with open(full, "rb") as fh:
            self._send(200, fh.read(), TYPES.get(os.path.splitext(full)[1], "application/octet-stream"))

    def _route(self, method):
        path = urlparse(self.path).path
        if method == "GET" and path == "/api/health":
            return self._send(200, {"ok": True, "name": "__NAME__"})
        if method == "GET" and path == "/api/demo":
            return self._send(200, core.analyze(core.demo_records()))
        if method == "POST" and path == "/api/analyze":
            body = self._json_body()
            if not isinstance(body, dict):
                raise ApiError(400, "body must be a JSON object")
            return self._send(200, core.analyze(body.get("records")))
        if method == "POST" and path == "/api/score":
            body = self._json_body()
            if not isinstance(body, dict):
                raise ApiError(400, "body must be a JSON object")
            return self._send(200, core.score_one(body.get("record")))
        if path.startswith("/api/"):
            raise ApiError(404, "unknown endpoint")
        if method in ("GET", "HEAD"):
            return self._static(path)
        raise ApiError(405, "method not allowed")

    def _handle(self, method):
        try:
            self._route(method)
        except ApiError as e:
            self._send(e.status, {"error": e.message})
        except ValueError as e:  # validation errors from core
            self._send(400, {"error": str(e)})
        except Exception as e:  # never crash the server
            self._send(500, {"error": "internal error: %s" % e})

    def do_GET(self):
        self._handle("GET")

    def do_HEAD(self):
        self._handle("HEAD")

    def do_POST(self):
        self._handle("POST")


def main(argv=None):
    ap = argparse.ArgumentParser(description="__NAME__ server")
    ap.add_argument("--host", default="127.0.0.1", help="0.0.0.0 lets phones on the same Wi-Fi connect")
    ap.add_argument("--port", type=int, default=__PORT__)
    args = ap.parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print("__NAME__ running at http://%s:%d/  (Ctrl+C to stop)" % (
        "127.0.0.1" if args.host == "0.0.0.0" else args.host, args.port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
'''

CORE_PY = r'''"""__NAME__ core logic. REPLACE this example with the model for your problem statement.

The example is a transparent scorer, chosen because judges reward explainability:
  1. fit():   mean and standard deviation of every feature over the population
  2. score(): z_i = (x_i - mean_i) / sd_i ; logit = sum(w_i * z_i) ; score = 100 * sigmoid(logit)
  3. every result lists each feature's contribution w_i * z_i, so the UI can show *why*.
Keep the shapes of analyze() and score_one() and the UI keeps working while you swap the maths.
"""
import math
import random

# key, label, unit, weight (positive pushes the score up) and the demo distribution (mean, sd)
FEATURES = [
    {"key": "signal_a", "label": "Signal A", "unit": "", "weight": 0.9, "demo": (50.0, 15.0)},
    {"key": "signal_b", "label": "Signal B", "unit": "%", "weight": 0.6, "demo": (40.0, 12.0)},
    {"key": "signal_c", "label": "Signal C", "unit": "", "weight": -0.5, "demo": (70.0, 10.0)},
]
LEVELS = [(70.0, "high"), (40.0, "medium"), (0.0, "low")]


def demo_records(n=40, seed=2026):
    """Seeded synthetic records, so every demo run shows the same numbers."""
    rng = random.Random(seed)
    out = []
    for i in range(n):
        rec = {"id": "R%03d" % (i + 1), "name": "Record %d" % (i + 1)}
        for f in FEATURES:
            mu, sd = f["demo"]
            rec[f["key"]] = round(rng.gauss(mu, sd), 1)
        out.append(rec)
    return out


def _number(record, f):
    v = record.get(f["key"])
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ValueError("%s must be a number" % f["label"])
    return float(v)


def validate(records):
    if not isinstance(records, list) or not records:
        raise ValueError("records must be a non-empty list")
    if len(records) > 5000:
        raise ValueError("at most 5000 records")
    for i, r in enumerate(records):
        if not isinstance(r, dict):
            raise ValueError("record %d must be an object" % (i + 1))
        for f in FEATURES:
            _number(r, f)


def fit(records):
    stats = {}
    for f in FEATURES:
        xs = [_number(r, f) for r in records]
        mu = sum(xs) / len(xs)
        sd = math.sqrt(sum((x - mu) ** 2 for x in xs) / len(xs)) or 1.0
        stats[f["key"]] = (mu, sd)
    return stats


def level_of(score):
    for threshold, name in LEVELS:
        if score >= threshold:
            return name
    return LEVELS[-1][1]


def score(record, stats):
    logit = 0.0
    contributions = []
    for f in FEATURES:
        mu, sd = stats[f["key"]]
        x = _number(record, f)
        z = (x - mu) / sd
        c = f["weight"] * z
        logit += c
        contributions.append({"key": f["key"], "label": f["label"], "unit": f["unit"], "value": x,
                              "z": round(z, 2), "contribution": round(c, 3)})
    s = 100.0 / (1.0 + math.exp(-logit))
    contributions.sort(key=lambda c: -abs(c["contribution"]))
    return {"score": round(s, 1), "level": level_of(s), "logit": round(logit, 3), "contributions": contributions}


def analyze(records):
    validate(records)
    stats = fit(records)
    results = []
    for i, r in enumerate(records):
        res = score(r, stats)
        res["id"] = str(r.get("id", "R%03d" % (i + 1)))
        res["name"] = str(r.get("name", res["id"]))
        results.append(res)
    results.sort(key=lambda r: -r["score"])
    counts = {name: sum(1 for r in results if r["level"] == name) for _, name in LEVELS}
    summary = {"count": len(results), "mean_score": round(sum(r["score"] for r in results) / len(results), 1)}
    summary.update(counts)
    features = [{k: f[k] for k in ("key", "label", "unit", "weight")} for f in FEATURES]
    return {"summary": summary, "results": results, "features": features}


def score_one(record):
    """Score one record against the demo population (the try-it form)."""
    if not isinstance(record, dict):
        raise ValueError("record must be an object")
    return score(record, fit(demo_records()))
'''

INDEX_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__NAME__ · __TAGLINE__</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<header class="topbar">
  <div class="brand">
    <span class="logo" aria-hidden="true"></span>
    <div><h1>__NAME__</h1><p class="tagline">__TAGLINE__</p></div>
  </div>
  <button id="btn-demo" class="btn btn-primary" type="button">Run demo</button>
</header>

<nav class="tabs" role="tablist">
  <button class="tab is-active" type="button" role="tab" data-tab="dashboard">Dashboard</button>
  <button class="tab" type="button" role="tab" data-tab="try">Try it</button>
  <button class="tab" type="button" role="tab" data-tab="how">How it works</button>
</nav>

<main>
  <section id="tab-dashboard" class="panel is-active">
    <div class="kpis" id="kpis"></div>
    <div class="grid">
      <div class="card">
        <div class="card-h"><h2>Score distribution</h2><span class="badge">live</span></div>
        <div id="chart" class="chart"></div>
      </div>
      <div class="card">
        <div class="card-h"><h2>Why this result?</h2><span class="badge" id="why-who">pick a row</span></div>
        <div id="why" class="why"><p class="muted">Click a row in the table to see which inputs pushed its score up or down.</p></div>
      </div>
    </div>
    <div class="card">
      <div class="card-h"><h2>Ranked results</h2><span class="muted small" id="table-note"></span></div>
      <div class="table-wrap"><table id="table"></table></div>
    </div>
  </section>

  <section id="tab-try" class="panel">
    <div class="grid">
      <form class="card" id="try-form">
        <div class="card-h"><h2>Score a new record</h2></div>
        <div id="fields" class="fields"></div>
        <button class="btn btn-primary" type="submit">Score it</button>
        <p class="error" id="try-error" role="alert"></p>
      </form>
      <div class="card">
        <div class="card-h"><h2>Result</h2><span class="badge" id="try-level">–</span></div>
        <div class="big" id="try-score">–</div>
        <div id="try-why" class="why"></div>
      </div>
    </div>
  </section>

  <section id="tab-how" class="panel">
    <div class="card prose">
      <h2>How __NAME__ decides</h2>
      <ol>
        <li>Every input is standardised against the population: <code>z = (x − mean) / sd</code>.</li>
        <li>Each input has a weight; the weighted sum is squashed to a 0–100 score with a sigmoid.</li>
        <li>The contribution of each input (<code>weight × z</code>) is shown, so every score is explainable.</li>
      </ol>
      <p class="muted">Replace this with the method for your problem statement, and keep it this short.</p>
      <div class="table-wrap"><table id="features"></table></div>
    </div>
  </section>
</main>

<footer>Built for QUANTIX 2K26 · KSRCE · runs fully offline</footer>
<script src="app.js"></script>
</body>
</html>
'''

STYLE_CSS = r'''/* __NAME__ - generated by tools/new_project.py. Brand colour: --accent. */
:root {
  color-scheme: light;
  --accent: __COLOR__;
  --bg: #f4f5fb; --surface: #ffffff; --surface-2: #f0f2f8; --border: #e2e4f0;
  --text: #11162e; --muted: #5b6180;
  --high: #d33f49; --medium: #d98a00; --low: #2e9d5b;
  --radius: 14px; --shadow: 0 4px 18px rgba(20, 30, 70, .07);
  --sans: system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans Tamil", sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root {
    color-scheme: dark;
    --bg: #0b1026; --surface: #141a37; --surface-2: #1b2246; --border: #2a3260;
    --text: #eceffa; --muted: #a5abc9;
    --high: #ff6b74; --medium: #ffb432; --low: #4fd18a;
    --shadow: 0 4px 18px rgba(0, 0, 0, .35);
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.5 var(--sans); }
h1, h2 { margin: 0; line-height: 1.2; }
code { background: var(--surface-2); padding: 1px 6px; border-radius: 6px; font-size: .92em; }
.muted { color: var(--muted); }
.small { font-size: 13px; }

.topbar { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap;
  padding: 16px 24px; background: var(--surface); border-bottom: 1px solid var(--border); }
.brand { display: flex; align-items: center; gap: 12px; min-width: 0; }
.logo { width: 38px; height: 38px; border-radius: 11px; flex: none; background: var(--accent);
  background: linear-gradient(135deg, var(--accent), color-mix(in srgb, var(--accent) 55%, #000)); }
.brand h1 { font-size: 21px; }
.tagline { margin: 2px 0 0; color: var(--muted); font-size: 14px; }

.btn { font: inherit; font-weight: 600; border-radius: 10px; padding: 9px 18px; cursor: pointer;
  border: 1px solid var(--border); background: var(--surface); color: var(--text); }
.btn:hover { border-color: var(--accent); }
.btn:focus-visible, .tab:focus-visible, tr:focus-visible, input:focus-visible { outline: 3px solid var(--accent);
  outline: 3px solid color-mix(in srgb, var(--accent) 45%, transparent); outline-offset: 2px; }
.btn-primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.btn-primary:hover { filter: brightness(1.08); }

.tabs { display: flex; gap: 4px; padding: 0 24px; background: var(--surface); border-bottom: 1px solid var(--border);
  overflow-x: auto; scrollbar-width: none; }
.tab { font: inherit; font-weight: 600; color: var(--muted); background: none; border: 0; cursor: pointer;
  padding: 12px 14px; border-bottom: 3px solid transparent; white-space: nowrap; }
.tab:hover { color: var(--text); }
.tab.is-active { color: var(--text); border-bottom-color: var(--accent); }

main { max-width: 1240px; margin: 0 auto; padding: 22px 24px 8px; }
.panel { display: none; }
.panel.is-active { display: block; }
.grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; margin-bottom: 18px; }
.grid > * { min-width: 0; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
  box-shadow: var(--shadow); padding: 18px 20px; margin-bottom: 18px; min-width: 0; }
.grid > .card { margin-bottom: 0; }
.card-h { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; margin-bottom: 12px; }
.card-h h2 { font-size: 17px; }
.badge { font-size: 12px; font-weight: 700; padding: 3px 10px; border-radius: 999px;
  background: var(--surface-2); background: color-mix(in srgb, var(--accent) 14%, transparent); color: var(--accent); }

.kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-bottom: 18px; }
.kpi { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
  box-shadow: var(--shadow); padding: 14px 18px; border-top: 4px solid var(--c, var(--accent)); }
.kpi b { display: block; font-size: 30px; line-height: 1.15; }
.kpi span { color: var(--muted); font-size: 13px; }

.chart svg { display: block; width: 100%; height: auto; }
.chart text { fill: var(--muted); font: 12px var(--sans); }
.chart .val { fill: var(--text); font-weight: 700; }
.chart line { stroke: var(--border); }

.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th { text-align: left; color: var(--muted); font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }
th, td { padding: 9px 10px; border-bottom: 1px solid var(--border); white-space: nowrap; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
tbody tr { cursor: pointer; }
tbody tr:hover, tbody tr.is-selected { background: var(--surface-2); }
.pill { display: inline-block; min-width: 64px; text-align: center; font-size: 12px; font-weight: 700;
  padding: 2px 10px; border-radius: 999px; color: #fff; text-transform: capitalize; }
.pill.high { background: var(--high); } .pill.medium { background: var(--medium); } .pill.low { background: var(--low); }

.why { display: grid; gap: 10px; }
.bar-row { display: grid; grid-template-columns: minmax(0, 9em) minmax(0, 1fr) 4.5em; gap: 10px; align-items: center; font-size: 14px; }
.bar-track { position: relative; height: 12px; background: var(--surface-2); border-radius: 6px; }
.bar-track::before { content: ""; position: absolute; left: 50%; top: -3px; bottom: -3px; width: 1px; background: var(--muted); opacity: .5; }
.bar { position: absolute; top: 0; bottom: 0; border-radius: 6px; }
.bar.up { left: 50%; background: var(--high); } .bar.down { right: 50%; background: var(--low); }
.bar-row .v { text-align: right; font-variant-numeric: tabular-nums; color: var(--muted); }

.fields { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 180px), 1fr)); gap: 12px; margin-bottom: 14px; }
.fields label { display: grid; gap: 4px; font-size: 13px; color: var(--muted); font-weight: 600; }
.fields input { font: inherit; color: var(--text); background: var(--surface-2); border: 1px solid var(--border);
  border-radius: 9px; padding: 8px 10px; width: 100%; }
.big { font-size: 56px; font-weight: 800; line-height: 1; margin: 6px 0 16px; }
.error { color: var(--high); min-height: 1.4em; margin: 8px 0 0; }
.prose { max-width: 860px; }
.prose ol { padding-left: 20px; }
.prose li { margin: 6px 0; }

footer { text-align: center; color: var(--muted); font-size: 13px; padding: 18px; }

@media (max-width: 860px) {
  .grid { grid-template-columns: minmax(0, 1fr); }
  .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  main, .topbar { padding-left: 16px; padding-right: 16px; }
  .tabs { padding: 0 8px; }
}
'''

APP_JS = r'''// __NAME__ UI: fetches the JSON API and draws everything with plain DOM + inline SVG.
"use strict";
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmt = (x, d = 1) => Number(x).toLocaleString("en-IN", { maximumFractionDigits: d });
const signed = (x) => (Math.abs(x) < 0.005 ? "0.00" : (x > 0 ? "+" : "−") + Math.abs(x).toFixed(2));
let state = { data: null, selected: null };

async function api(path, body) {
  const res = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json.error || res.statusText);
  return json;
}

function showTab(name) {
  document.querySelectorAll(".tab").forEach((t) => {
    const on = t.dataset.tab === name;
    t.classList.toggle("is-active", on);
    t.setAttribute("aria-selected", on);
  });
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("is-active", p.id === "tab-" + name));
}

function kpis(s) {
  const tiles = [
    [fmt(s.count, 0), "records analysed", "var(--accent)"],
    [fmt(s.high || 0, 0), "high", "var(--high)"],
    [fmt(s.medium || 0, 0), "medium", "var(--medium)"],
    [fmt(s.mean_score), "average score (0–100)", "var(--low)"],
  ];
  $("#kpis").innerHTML = tiles.map(([v, l, c]) => `<div class="kpi" style="--c:${c}"><b>${v}</b><span>${esc(l)}</span></div>`).join("");
}

// Histogram of scores in 10-point bins, coloured by level.
function chart(results) {
  const bins = Array.from({ length: 10 }, () => 0);
  results.forEach((r) => { bins[Math.min(9, Math.floor(r.score / 10))]++; });
  const W = 560, H = 230, pad = { l: 34, r: 8, t: 14, b: 38 };
  const max = Math.max(1, ...bins);
  const bw = (W - pad.l - pad.r) / bins.length;
  const y = (v) => pad.t + (H - pad.t - pad.b) * (1 - v / max);
  const color = (i) => (i >= 7 ? "var(--high)" : i >= 4 ? "var(--medium)" : "var(--low)");
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Histogram of scores">`;
  for (let k = 0; k <= max; k += Math.max(1, Math.ceil(max / 4))) {
    svg += `<line x1="${pad.l}" x2="${W - pad.r}" y1="${y(k)}" y2="${y(k)}"/><text x="${pad.l - 6}" y="${y(k) + 4}" text-anchor="end">${k}</text>`;
  }
  bins.forEach((v, i) => {
    const x = pad.l + i * bw + 3;
    svg += `<rect x="${x}" y="${y(v)}" width="${bw - 6}" height="${y(0) - y(v)}" rx="4" fill="${color(i)}"><title>${i * 10}–${i * 10 + 10}: ${v}</title></rect>`;
    if (v) svg += `<text class="val" x="${x + (bw - 6) / 2}" y="${y(v) - 4}" text-anchor="middle">${v}</text>`;
    svg += `<text x="${x + (bw - 6) / 2}" y="${H - pad.b + 16}" text-anchor="middle">${i * 10}</text>`;
  });
  svg += `<text x="${(W + pad.l) / 2}" y="${H - 4}" text-anchor="middle">score (0–100) → number of records</text></svg>`;
  $("#chart").innerHTML = svg;
}

function whyBars(contribs) {
  // scale to at least one logit unit, so near-zero contributions stay near zero
  const max = Math.max(1, ...contribs.map((c) => Math.abs(c.contribution)));
  return contribs.map((c) => {
    const w = (Math.abs(c.contribution) / max) * 50;
    const dir = c.contribution >= 0 ? "up" : "down";
    return `<div class="bar-row"><span title="${esc(c.label)}">${esc(c.label)} <span class="muted">${fmt(c.value)}${esc(c.unit)}</span></span>
      <div class="bar-track"><div class="bar ${dir}" style="width:${w}%"></div></div>
      <span class="v">${signed(c.contribution)}</span></div>`;
  }).join("") + `<p class="muted small">Bars right of the centre line push the score up; bars to the left pull it down.</p>`;
}

function select(id) {
  const r = state.data.results.find((x) => x.id === id);
  if (!r) return;
  state.selected = id;
  document.querySelectorAll("#table tbody tr").forEach((tr) => tr.classList.toggle("is-selected", tr.dataset.id === id));
  $("#why-who").textContent = `${r.name} · ${fmt(r.score)}`;
  $("#why").innerHTML = whyBars(r.contributions);
}

function table(data) {
  const feats = data.features;
  const head = `<thead><tr><th>#</th><th>Name</th><th class="num">Score</th><th>Level</th>${feats.map((f) => `<th class="num">${esc(f.label)}</th>`).join("")}</tr></thead>`;
  const rows = data.results.slice(0, 15).map((r, i) => {
    const vals = feats.map((f) => (r.contributions.find((c) => c.key === f.key) || {}).value);
    return `<tr data-id="${esc(r.id)}" tabindex="0"><td>${i + 1}</td><td>${esc(r.name)}</td><td class="num"><b>${fmt(r.score)}</b></td>
      <td><span class="pill ${r.level}">${r.level}</span></td>${vals.map((v) => `<td class="num">${fmt(v)}</td>`).join("")}</tr>`;
  }).join("");
  $("#table").innerHTML = head + "<tbody>" + rows + "</tbody>";
  $("#table-note").textContent = `top ${Math.min(15, data.results.length)} of ${data.results.length}, highest score first`;
  $("#table").querySelectorAll("tbody tr").forEach((tr) => {
    tr.addEventListener("click", () => select(tr.dataset.id));
    tr.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(tr.dataset.id); } });
  });
}

function features(data) {
  $("#features").innerHTML = `<thead><tr><th>Input</th><th class="num">Weight</th><th>Effect</th></tr></thead><tbody>` +
    data.features.map((f) => `<tr><td>${esc(f.label)}</td><td class="num">${fmt(f.weight, 2)}</td><td>${f.weight >= 0 ? "higher value → higher score" : "higher value → lower score"}</td></tr>`).join("") + "</tbody>";
  $("#fields").innerHTML = data.features.map((f) => {
    const vals = data.results.map((r) => (r.contributions.find((c) => c.key === f.key) || {}).value);
    const mean = vals.reduce((a, b) => a + b, 0) / Math.max(1, vals.length);
    return `<label>${esc(f.label)}${f.unit ? " (" + esc(f.unit) + ")" : ""}<input name="${esc(f.key)}" type="number" step="any" required value="${fmt(mean).replace(/,/g, "")}"></label>`;
  }).join("");
}

async function runDemo() {
  const btn = $("#btn-demo");
  btn.disabled = true;
  try {
    state.data = await api("/api/demo");
    kpis(state.data.summary);
    chart(state.data.results);
    table(state.data);
    features(state.data);
    select(state.data.results[0].id);
  } catch (e) {
    $("#why").innerHTML = `<p class="error">Could not load the demo: ${esc(e.message)}</p>`;
  } finally {
    btn.disabled = false;
  }
}

$("#try-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const record = {};
  new FormData(e.target).forEach((v, k) => { record[k] = Number(v); });
  $("#try-error").textContent = "";
  try {
    const r = await api("/api/score", { record });
    $("#try-score").textContent = fmt(r.score);
    $("#try-level").textContent = r.level;
    $("#try-why").innerHTML = whyBars(r.contributions);
  } catch (err) {
    $("#try-error").textContent = err.message;
  }
});
document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => showTab(t.dataset.tab)));
$("#btn-demo").addEventListener("click", runDemo);
runDemo(); // judges should see the product working within seconds
'''

TEST_CORE = r'''import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from __PKG__ import core  # noqa: E402


class CoreTest(unittest.TestCase):
    def test_demo_is_deterministic(self):
        self.assertEqual(core.demo_records(), core.demo_records())
        self.assertEqual(len(core.demo_records(25)), 25)

    def test_analyze_ranks_and_counts(self):
        out = core.analyze(core.demo_records())
        scores = [r["score"] for r in out["results"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        s = out["summary"]
        self.assertEqual(s["high"] + s["medium"] + s["low"], s["count"])
        self.assertTrue(all(0 <= x <= 100 for x in scores))

    def test_contributions_explain_the_score(self):
        r = core.analyze(core.demo_records())["results"][0]
        self.assertAlmostEqual(sum(c["contribution"] for c in r["contributions"]), r["logit"], places=2)

    def test_average_record_scores_fifty(self):
        stats = {f["key"]: (10.0, 2.0) for f in core.FEATURES}
        rec = {f["key"]: 10.0 for f in core.FEATURES}
        self.assertEqual(core.score(rec, stats)["score"], 50.0)

    def test_validation(self):
        with self.assertRaises(ValueError):
            core.analyze([])
        with self.assertRaises(ValueError):
            core.analyze([{"id": "x"}])
        with self.assertRaises(ValueError):
            core.score_one({core.FEATURES[0]["key"]: "abc"})


if __name__ == "__main__":
    unittest.main()
'''

TEST_API = r'''import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app  # noqa: E402
from __PKG__ import core  # noqa: E402


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.base = "http://127.0.0.1:%d" % cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def call(self, path, body=None):
        data = None if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
        req = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_health_and_page(self):
        self.assertEqual(json.loads(self.call("/api/health")[1])["ok"], True)
        status, body = self.call("/")
        self.assertEqual(status, 200)
        self.assertIn(b"<html", body)

    def test_demo_and_analyze(self):
        status, body = self.call("/api/demo")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["summary"]["count"], 40)
        status, body = self.call("/api/analyze", {"records": core.demo_records(5)})
        self.assertEqual((status, json.loads(body)["summary"]["count"]), (200, 5))

    def test_errors_are_json(self):
        self.assertEqual(self.call("/api/analyze", b"not json")[0], 400)
        self.assertEqual(self.call("/api/analyze", {"records": []})[0], 400)
        self.assertEqual(self.call("/api/nope")[0], 404)
        self.assertEqual(self.call("/../app.py")[0], 404)

    def test_score_one(self):
        rec = {f["key"]: f["demo"][0] for f in core.FEATURES}
        status, body = self.call("/api/score", {"record": rec})
        self.assertEqual(status, 200)
        self.assertIn(json.loads(body)["level"], ("low", "medium", "high"))


if __name__ == "__main__":
    unittest.main()
'''

README_MD = r'''# __NAME__

**__TAGLINE__** Domain: __DOMAIN__ · QUANTIX 2K26

TODO: two or three sentences on who has the problem, what __NAME__ does about it, and the one
number that proves it works.

![__NAME__ dashboard](docs/screenshot.png)

## Quick start

```bash
cd __DIR__
python app.py                 # http://127.0.0.1:__PORT__/
python app.py --host 0.0.0.0  # let phones on the same Wi-Fi open it
python -m unittest discover -s tests
```

## API

| Method | Path | What it does |
|---|---|---|
| GET | `/api/health` | liveness check |
| GET | `/api/demo` | analyses the seeded demo data |
| POST | `/api/analyze` | `{"records": [...]}` → ranked, explained results |
| POST | `/api/score` | `{"record": {...}}` → one explained score |

Generated with `tools/new_project.py`; the example model in `__PKG__/core.py` is a placeholder.
'''

REPORT_MD = r'''# __NAME__

## 1. Title, tagline, domain

**__NAME__**: __TAGLINE__. Domain: __DOMAIN__.

## 2. Problem statement

TODO: who suffers, how much (2–3 honest statistics, marked approx. where rounded), why existing
solutions fail.

## 3. Our solution

TODO: one paragraph, then the key features as bullets.

## 4. Innovation / what makes it different

TODO

## 5. System architecture

```mermaid
flowchart LR
  UI[Browser UI: static/] -->|JSON| API[app.py: ThreadingHTTPServer]
  API --> Core[__PKG__/core.py: model + explanations]
  Core --> Data[(seeded demo data)]
```

| Component | Role |
|---|---|
| `static/` | dashboard, try-it form, how-it-works |
| `app.py` | static files + JSON API, input validation |
| `__PKG__/core.py` | the model and its per-input explanations |

## 6. Algorithms & models

TODO: each algorithm with its formula or pseudocode, why it was chosen, and its limits.

## 7. Tech stack

Python 3.9+ standard library, vanilla HTML/CSS/JS with inline SVG charts. Runs offline: no
installs, no cloud, no API keys.

## 8. Results / evaluation

TODO: numbers you measured (accuracy on a held-out split, latency, ...) and how.

## 9. Screenshots

![__NAME__](docs/screenshot.png)

## 10. 3-minute live demo script

1. TODO

## 11. Impact

TODO

## 12. Feasibility, scalability & business model

TODO

## 13. Future scope

TODO

## 14. Judges' Q&A prep

| Question | Answer |
|---|---|
| TODO | TODO |

## 15. How to run

```bash
cd __DIR__
python app.py
python -m unittest discover -s tests
```
'''


def pitch_json(name, tagline, domain, color, port, rel_dir):
    return {
        "name": name,
        "tagline": tagline,
        "domain": domain,
        "color": color,
        "problem": ["TODO: who suffers, in one line", "TODO: how much it costs them", "TODO: why today's options fail"],
        "stats": [{"value": "TODO", "label": "a real statistic (source or approx.)"},
                  {"value": "TODO", "label": "a second statistic"}],
        "solution": ["TODO: what %s does" % name, "TODO: the explainable part", "TODO: runs offline on a laptop"],
        "features": [{"title": "Live dashboard", "desc": "KPIs, score distribution and a ranked table"},
                     {"title": "Explainable scores", "desc": "Every result shows which inputs pushed it up or down"},
                     {"title": "Try it", "desc": "Score a new case instantly from a form"},
                     {"title": "Offline-first", "desc": "Python standard library only; no cloud, no installs"}],
        "architecture": ["Browser UI -> dashboard, try-it form, how-it-works",
                         "app.py -> stdlib HTTP server and JSON API with validation",
                         "core.py -> model and per-input explanations",
                         "Seeded demo data -> the same numbers on every run"],
        "algorithms": ["TODO: main algorithm – what it decides", "TODO: second algorithm – purpose"],
        "tech": ["Python 3 stdlib", "http.server", "Vanilla HTML/CSS/JS", "Inline SVG charts", "unittest"],
        "innovation": ["TODO: differentiator 1", "TODO: differentiator 2", "TODO: differentiator 3"],
        "results": [{"value": "TODO", "label": "a number you measured"}, {"value": "TODO", "label": "another measured number"}],
        "demo_flow": ["Click Run demo: TODO what judges see", "TODO: open the top result and its why-bars",
                      "TODO: Try it tab, change one input", "TODO: How it works tab"],
        "impact": ["TODO: impact 1", "TODO: impact 2", "TODO: impact 3"],
        "business": ["TODO: who pays", "TODO: pricing", "TODO: first customer"],
        "future": ["TODO: next step 1", "TODO: next step 2", "TODO: next step 3"],
        "compare": {"columns": ["TODO status quo", "TODO existing tools", name],
                    "rows": [["Works offline", "TODO", "TODO", "Yes"],
                             ["Explains each decision", "TODO", "TODO", "Yes"],
                             ["Cost to start", "TODO", "TODO", "₹0 / open"]]},
        "port": port,
        "dir": rel_dir,
    }


# ---------------------------------------------------------------- generator
def slugify(name):
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def next_number(projects_dir):
    nums = [int(m.group(1)) for d in projects_dir.iterdir() if (m := re.match(r"(\d+)-", d.name))] if projects_dir.exists() else []
    return max(nums, default=0) + 1


def used_ports(projects_dir):
    ports = set()
    for f in projects_dir.glob("*/pitch.json"):
        try:
            ports.add(int(json.loads(f.read_text(encoding="utf-8")).get("port")))
        except (ValueError, TypeError, OSError):
            pass
    return ports


def write(path, text):
    # LF endings on every OS (Path.write_text has no newline= before Python 3.10)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def create(name, tagline, domain, color, root=ROOT, number=None, slug=None):
    projects_dir = root / "projects"
    slug = slug or slugify(name)
    if not re.fullmatch(r"[a-z][a-z0-9]*", slug or ""):
        raise SystemExit("name must start with a letter, e.g. \"FloodWatch\" (or pass --slug)")
    if slug in RESERVED:
        raise SystemExit("'%s' clashes with a Python module or folder name; pass --slug" % slug)
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
        raise SystemExit("--color must look like #0EA5E9")
    domain = DOMAINS.get(domain, domain)
    number = number or next_number(projects_dir)
    port = 8000 + number
    if port in used_ports(projects_dir):
        raise SystemExit("port %d is already used by another project; pass --number" % port)
    rel_dir = "projects/%02d-%s" % (number, slug)
    target = root / rel_dir
    if target.exists():
        raise SystemExit("%s already exists" % rel_dir)

    subs = {"__NAME__": name, "__TAGLINE__": tagline, "__DOMAIN__": domain, "__COLOR__": color.upper(),
            "__PKG__": slug, "__PORT__": str(port), "__DIR__": rel_dir, "__UPPER__": slug.upper()}

    def render(text):
        for k, v in subs.items():
            text = text.replace(k, v)
        return text

    files = {
        "app.py": APP_PY, "%s/__init__.py" % slug: '"""%s core package."""\n' % name, "%s/core.py" % slug: CORE_PY,
        "static/index.html": INDEX_HTML, "static/style.css": STYLE_CSS, "static/app.js": APP_JS,
        "tests/__init__.py": "", "tests/test_core.py": TEST_CORE, "tests/test_api.py": TEST_API,
        "README.md": README_MD, "REPORT.md": REPORT_MD, "data/.gitkeep": "", "docs/.gitkeep": "",
    }
    for rel, text in files.items():
        p = target / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        write(p, render(text))
    write(target / "pitch.json", json.dumps(pitch_json(name, tagline, domain, color.upper(), port, rel_dir),
                                             ensure_ascii=False, indent=2) + "\n")
    return target, port


def selftest():
    """Generate a project in a temp dir, run its tests, start its server and fetch the page and API."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "projects").mkdir()
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            free = s.getsockname()[1]
        target, _ = create("Selftest Demo", "Checks the scaffold works", "data", "#6C4CF1", root=root, number=1)
        r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=target)
        if r.returncode:
            return 1
        proc = subprocess.Popen([sys.executable, "app.py", "--port", str(free)], cwd=target,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                try:
                    with urllib.request.urlopen("http://127.0.0.1:%d/api/demo" % free, timeout=2) as resp:
                        assert json.loads(resp.read())["summary"]["count"] == 40
                    with urllib.request.urlopen("http://127.0.0.1:%d/" % free, timeout=2) as resp:
                        assert b"Selftest Demo" in resp.read()
                    break
                except OSError:
                    time.sleep(0.2)
            else:
                print("selftest: server did not answer")
                return 1
        finally:
            proc.terminate()
            proc.wait(timeout=10)
        print("selftest: scaffold generated, its tests pass and its server answers")
        return 0


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="domains: " + ", ".join("%s = %s" % kv for kv in DOMAINS.items()))
    ap.add_argument("name", nargs="?", help='product name, e.g. "FloodWatch"')
    ap.add_argument("--tagline", default="TODO: one line, under 70 characters")
    ap.add_argument("--domain", default="ai", help="ai | sustain | health | cyber | agri | data, or the full name")
    ap.add_argument("--color", default="#6C4CF1", help="brand colour, e.g. #0EA5E9")
    ap.add_argument("--number", type=int, help="folder number (default: next free)")
    ap.add_argument("--slug", help="folder/package name (default: from the name)")
    ap.add_argument("--selftest", action="store_true", help="generate into a temp dir and check it works")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.name:
        ap.error("give a product name, or --selftest")
    target, port = create(args.name, args.tagline, args.domain, args.color, number=args.number, slug=args.slug)
    rel = target.relative_to(ROOT).as_posix()
    print("Created %s (port %d). Next:\n"
          "  cd %s && python app.py          # open http://127.0.0.1:%d/\n"
          "  python -m unittest discover -s tests\n"
          "Then replace the example model in %s/core.py, fill the TODOs in pitch.json and REPORT.md,\n"
          "and rebuild the deck: cd tools && node build_decks.js ../%s/pitch.json"
          % (rel, port, rel, port, target.name.split("-", 1)[1], rel))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
