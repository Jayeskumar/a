# Build spec shared by every QUANTIX 2K26 project

QUANTIX 2K26 is a 24-hour hackathon at K.S.R. College of Engineering (23–24 Oct 2026).
Evaluation is a PPT presentation followed by a working product demo. Teams submit a PPT,
a GitHub link and a demo link. Each project in `projects/` targets one hackathon domain.

## Hard constraints

- **Python 3.9+ standard library only** for the backend. No `pip install`, no numpy, no Flask.
  Venue laptops may be Windows and Wi-Fi may be down; `python app.py` must just work.
- **No CDNs, no external fonts, no network calls** from the frontend. Vanilla HTML/CSS/JS.
  Charts are hand-drawn with inline SVG or `<canvas>`.
- Every ML/analytics algorithm is implemented from scratch in Python (this is a selling point:
  "explainable, no black box, runs offline on a ₹15k laptop").
- Sample data is generated deterministically (fixed random seed) by code in the project, and
  the generated file may also be committed under `data/`.
- Never fabricate precise real-world statistics. Use only widely known figures you are
  confident of, mark rough numbers as "approx.", and keep tunable assumptions as named
  constants in one place with a comment giving the source or reasoning.

## Layout (inside `projects/<NN-name>/`)

```
app.py            # entry point: python app.py [--host 127.0.0.1] [--port <assigned>]
<package>/        # pure logic modules, no HTTP code (importable and unit-tested)
static/           # index.html, app.js, style.css (and any other assets)
data/             # deterministic sample data (+ generator if not inside the package)
tests/            # unittest tests: run with `python -m unittest discover -s tests` from the project dir
docs/screenshot.png  # 1440x900 screenshot of the UI showing real demo data
README.md         # short: what it is, quick start, API list, screenshot
REPORT.md         # full hackathon report (template below)
pitch.json        # structured pitch content consumed by tools/build_decks.py (schema below)
```

## Server conventions

- `http.server.ThreadingHTTPServer` + a `BaseHTTPRequestHandler` subclass.
- Default host `127.0.0.1`, `--host 0.0.0.0` lets judges open it from a phone on the same LAN.
- Serve `static/` at `/`; JSON API under `/api/...`; return JSON errors with proper status codes;
  validate input; never crash the server on bad input.
- Print a friendly banner with the URL on start-up.
- Persisted state (if any) goes into `data/*.json` and is created on first run.

## UI conventions

- Polished, modern dashboard look; responsive down to phone width; works in light and dark
  (`prefers-color-scheme`). Use the project's brand colour as the accent.
- A clearly visible **"Load demo data" / "Run demo"** control so the live demo never depends on typing.
- Header shows product name + tagline; footer shows "Built for QUANTIX 2K26 · KSRCE".
- Explain *why* a result was produced (feature contributions, rule that fired, etc.) wherever
  the product makes a decision — judges reward explainability.
- No console errors.

## Verification you must do before finishing

1. `python -m unittest discover -s tests` passes (aim for meaningful tests of the core logic).
2. Start the server, exercise every API endpoint with `curl`, then stop it.
3. Take the screenshot with the shared helper (from the repo root):
   `NODE_PATH="$(npm root -g)" node tools/screenshot.js http://127.0.0.1:<port>/ projects/<dir>/docs/screenshot.png [selectors to click first]`
   It exits non-zero on any console error — fix those. Look at the PNG (Read tool) and fix
   anything that looks broken or empty.
4. Do **not** run git commands (no add/commit/push); the coordinator commits.
5. Kill any server you started.

## REPORT.md template (use these headings, in this order)

1. **Title, tagline, domain**
2. **Problem statement** – who suffers, how much, why existing solutions fail
3. **Our solution** – one paragraph + bullet list of key features
4. **Innovation / what makes it different**
5. **System architecture** – a Mermaid diagram (` ```mermaid `) plus a component table
6. **Algorithms & models** – each with formula/pseudocode, why chosen, and its limits
7. **Tech stack** and why it is offline-first
8. **Results / evaluation** – real numbers you measured (accuracy on a hold-out split, latency, etc.)
9. **Screenshots** – reference `docs/screenshot.png`
10. **3-minute live demo script** – numbered steps with what to click and what to say
11. **Impact** – social / economic / environmental, with honest assumptions
12. **Feasibility, scalability & business model**
13. **Future scope**
14. **Judges' Q&A prep** – 8–10 likely tough questions with crisp answers
15. **How to run** – commands

## pitch.json schema

```json
{
  "name": "ProductName",
  "tagline": "One line, under 70 characters",
  "domain": "Exact hackathon domain name",
  "color": "#RRGGBB",
  "problem": ["3-4 short bullets"],
  "stats": [{"value": "e.g. ~60%", "label": "what it measures (source or 'approx.')"}],
  "solution": ["3-4 short bullets"],
  "features": [{"title": "Feature", "desc": "under 90 characters"}],
  "architecture": ["Layer or component -> what it does", "..."],
  "algorithms": ["Algorithm – one-line purpose"],
  "tech": ["Python 3 stdlib", "..."],
  "innovation": ["3-4 bullets"],
  "results": [{"value": "94%", "label": "what was measured"}],
  "demo_flow": ["5-7 steps"],
  "impact": ["3-4 bullets"],
  "business": ["3-4 bullets"],
  "future": ["3-5 bullets"],
  "port": 8001,
  "dir": "projects/NN-name"
}
```

`stats` has 2–3 items, `features` 4–6, `results` 2–4. Keep every string short — they go on slides.

Optional keys:

- `"compare": {"columns": ["Status quo", "Typical existing tool", "ProductName"], "rows": [["Criterion", "No", "Partial", "Yes"], ...]}`
  becomes the "How we compare" slide (up to 6 rows; cells starting with Yes / No / Partial get a ✓ / ✗ / ◐ mark).
  Use generic categories, not named products, and claim only what the app actually does.
- `"deck_views": {"solution": 3, "demo": 2}` picks which capture in `docs/shots/` (1-based, from
  `tools/capture_tabs.js`) appears on the solution and demo slides; the default is views 2 and 3.
