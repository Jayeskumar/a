# AgriSky · அக்ரிஸ்கை

**Drone-based crop health maps and precision spraying.** Domain: Smart Agriculture & Rural Development (AgriTech).

AgriSky turns multispectral drone flights over a field into a **crop-health map, management zones,
a diagnosis per zone (water stress / nitrogen deficiency / pest), an early warning when a pest patch
is spreading, a variable-rate prescription, and a drone spray mission that covers only the cells that
need treatment**. It also prints a farmer report in English and Tamil. All the image analytics and
planning are written from scratch in the Python standard library, and the app runs fully offline.

![AgriSky screenshot](docs/screenshot.png)

## Quick start

```bash
cd projects/18-agrisky
python app.py                  # http://127.0.0.1:8018/
python app.py --host 0.0.0.0   # open it from a phone on the same Wi-Fi
python -m unittest discover -s tests       # 79 tests
python -m agrisky.evaluate                 # accuracy / savings / path metrics -> data/metrics.json
python bench.py                            # HTTP latency -> data/metrics.json ("http")
```

Python 3.9+, no `pip install`, no internet. Click **Run demo** to load the demo field and fly the
spray mission. **Weeks** plays the five weekly flights so you can watch the pest patch grow.

## What it does

| Stage | Method (from scratch) |
|---|---|
| Synthetic field | 120 × 80 grid of 1 m cells. Green / Red / Red-edge / NIR reflectance from a linear canopy–soil–water mixing model. Scenarios: healthy maize, a missed-fertiliser N strip, a waterlogged patch, a pest outbreak spreading from a corner, bunds, an irrigation channel. Five weekly flights, seeded noise |
| Vegetation indices | NDVI, GNDVI, NDRE, SAVI, NDWI per cell, drawn as canvas heat maps with legends |
| Zoning | Soil and water masks → z-scored k-means++ over crop cells → 3×3 mode filter → connected components → merge specks → merge touching zones that share a label |
| Diagnosis | Ordered rule list against a same-flight reference canopy (top-quartile NDVI). The full rule trace is shown for every zone |
| Change detection | Relative ΔNDVI map, decline hotspots, front advance (p90 distance of new cells), OLS on √area vs day, projection and early-warning level |
| Prescription | Pesticide spot spray (pest zone + 2 m ring, full label rate, 3 m no-spray buffer next to water) and urea scaled by the NDRE deficit (held on waterlogged zones). Compared with uniform application in % and ₹ |
| Mission planner | Boustrophedon passes one swath wide over target blocks only. Picks E–W or N–S lanes and the start corner with the lowest estimated time (fewest turns). Checks tank and battery (with reserve) before every metre and returns home to refill when needed. Animated on the map |
| Export | Prescription CSV and GeoJSON (zone polygons in WGS84 from an illustrative origin), plus a printable report with English and Tamil lines |

## Measured results (`data/metrics.json`)

| Metric | Value |
|---|---|
| Zone-classification accuracy vs ground truth, 20 unseen fields × 5 flights | **98.6 %** mean (min 97.1 %), macro-F1 0.942 |
| Pest recall / precision (hold-out, pooled) | 96.2 % / 99.2 % |
| Waterlogging recall (weakest class: fringe cells) | 68.4 % (precision 99.6 %) |
| Early warning | red alert at the first flight after the outbreak on 20 / 20 fields (patch ≈ 1.2 % of crop); 0 red alerts on 50 pest-free control flights |
| Pest front-speed estimate vs generator truth | 6.9 % mean error |
| Pesticide / urea saved vs uniform application | 89.3 % / 85.6 % (hold-out mean); demo field ₹766 saved per round |
| Coverage path | 100 % of target cells sprayed **exactly once** on every hold-out field; VRA 1 sortie vs 2 for whole field, flight time −80 % |
| Turn minimisation on the N strip | 3.2 turns (auto) vs 19.1 with fixed E–W lanes, −32 % flight time |
| Latency | 0.36 s to analyse a flight; `/api/scene` 56 ms median (warm); planner 8 ms |

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | liveness |
| GET | `/api/meta` | classes (EN/TA), index formulas, rules, drone defaults, assumptions |
| GET | `/api/flights?seed=&k=` | per-flight summary (day, pest area, accuracy) |
| GET | `/api/scene?seed=&flight=&k=[&swath&tank&endurance&speed&orient]` | everything the dashboard needs for one flight |
| GET | `/api/field?seed=&flight=` | raw bands + indices (×1000) + ground truth |
| GET | `/api/zones?seed=&flight=&k=` | k-means info, zones with rule trace, accuracy, zone grid |
| GET | `/api/change?seed=&flight=&base=` | ΔNDVI map, hotspots, spread trend, projection, alert |
| GET | `/api/prescription?seed=&flight=&product=pesticide\|urea&buffer=` | per-cell rates, rows, VRA vs uniform savings |
| GET/POST | `/api/mission` | `{seed, flight, product, plan: vra\|uniform, swath, tank, endurance, speed, orient}` → sorties + coverage check |
| GET | `/api/report?seed=&flight=` | farmer report lines (English + Tamil) and totals |
| GET | `/api/export/prescription.csv` · `/api/export/prescription.geojson` | prescription export (`&download=1` sets an attachment header) |
| POST | `/api/indices` | `{green, red, rededge, nir}` → all indices (hand-check calculator) |
| GET | `/api/metrics` | contents of `data/metrics.json` |

`flight` is 1–5 and defaults to 5. Bad input returns JSON `{"error": ...}` with status 400, 404, 405
or 413, and the server never crashes on it.

## Layout

```
app.py              HTTP server (ThreadingHTTPServer): static files + JSON API, input validation
bench.py            HTTP latency benchmark
agrisky/config.py   every tunable assumption (marked approx. / illustrative)
agrisky/field.py    deterministic multispectral field + flight generator with ground truth
agrisky/indices.py  NDVI, GNDVI, NDRE, SAVI, NDWI
agrisky/kmeans.py   k-means++ / Lloyd / restarts
agrisky/segment.py  mode filter, connected components, small-zone merge, dilation
agrisky/analysis.py per-flight pipeline (masks → k-means → zones → rules)
agrisky/classify.py explainable stress rules, reference canopy, confusion matrix
agrisky/change.py   ΔNDVI, hotspots, front advance, √area OLS, early warning
agrisky/prescription.py variable-rate pesticide / urea vs uniform
agrisky/planner.py  boustrophedon coverage, turn minimisation, tank/battery sorties
agrisky/report.py   farmer report (EN + Tamil), CSV and GeoJSON export
agrisky/pipeline.py orchestration + cache;  agrisky/evaluate.py offline evaluation
static/             index.html, app.js, style.css, report.html, report.js, favicon.svg
data/               sample_flights.json (demo field, created on first run), metrics.json
tests/              79 unittest tests
```

All field data is **synthetic**. Doses, prices and drone specifications are approximate or
illustrative and live as named constants in `agrisky/config.py`.
