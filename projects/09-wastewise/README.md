# WasteWise

**Smart bins and optimised collection routes for cleaner cities.** Domain: Sustainability, CleanTech & Green Energy.

WasteWise simulates a small Tamil Nadu-style grid town with 40 smart bins (wet / dry / recyclable), a transfer station and 3 trucks. Every morning it forecasts each bin's fill level and picks the bins that need a pickup today. It then builds capacitated truck routes with **Clarke-Wright savings + 2-opt** and compares them, on exactly the same waste, with the municipal **fixed beat**. In a simulated month it drives **43% fewer truck-km**, burns **43% less diesel** and has **12 → 1 overflowing bin-days**. A bilingual (English/Tamil) waste-item classifier and a ward leaderboard with green points push source segregation. Every algorithm is written from scratch in the Python standard library and runs offline.

![screenshot](docs/screenshot.png)

## Quick start

```bash
python app.py                    # http://127.0.0.1:8009/
python app.py --host 0.0.0.0     # let judges open it from a phone on the same LAN
python -m unittest discover -s tests
python -m wastewise.evaluate     # reproduce every number in REPORT.md (~2 s)
```

You need Python 3.9+ and nothing else: no pip installs, CDNs, fonts or network. On first run the app writes the deterministic town (`data/town.json`), 6 weeks of sensor history (`data/sensor_history.csv`) and demo segregation reports (`data/reports.json`). Click **Run demo** at any time to reset to day 0 and replay today's routes.

## What is inside

| Module | What it does |
|---|---|
| `wastewise/town.py` | Seeded town: 6 wards, 40 bins, depot, 3 trucks. Fill model with weekday + weekly market-day effects |
| `wastewise/forecast.py` | Seasonal exponential smoothing (Holt-Winters, weekday season) with grid-searched α/γ. Also naive, SES and OLS + weekday regression for backtests, and time-to-full |
| `wastewise/planner.py` | Rule A (≥75% at pickup) / rule B (overflow guard with +1σ margin). Runs Clarke-Wright → 2-opt → truck packing, and defers the least urgent bins if the window is full |
| `wastewise/routing.py` | Clarke-Wright savings (capacity + duration), 2-opt, fixed-order baseline, LPT trip assignment |
| `wastewise/simulator.py` | Two worlds (fixed beat and WasteWise) given the same waste. Tracks truck timing, loads, unloads and overflow |
| `wastewise/classifier.py` | Multinomial Naive Bayes over words + character 3-grams (English / தமிழ் / Tanglish), with explanations |
| `wastewise/segregation.py` | Citizen reports, green points, compliance-weighted ward leaderboard (persisted to `data/reports.json`) |
| `wastewise/impact.py` | Annual fuel / ₹ / CO₂ projection from the simulated month. All constants live in `wastewise/config.py` |

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | liveness, current day |
| GET | `/api/town` | wards, bins, depot, trucks (with fixed beats), constants |
| GET | `/api/state` | current day, bin levels in both worlds, running totals, daily KPIs, overflow log |
| GET | `/api/plan` | today's decisions per bin, smart routes + fixed beat (timed events for playback), KPIs, savings, algorithm trace |
| GET | `/api/forecast?bin=B07` | history, one-step fit, 7-day forecast ±σ, weekday indices, backtest MAE, time-to-full, decision |
| GET | `/api/simulate?days=30` | fresh month simulation from day 0: daily KPIs, totals, savings %, routing-only gain, solver ms |
| GET | `/api/evaluation` | forecast backtest (all bins), classifier hold-out, month savings, solver timing |
| GET | `/api/impact?diesel=90&bins=400&kmpl=4` | annual projection with overridable assumptions |
| GET / POST | `/api/classify?item=` / `{item}` | which bin? label, confidence, evidence, Tamil bin name, tip |
| GET | `/api/leaderboard` | ward ranking, compliance, top households, recent reports |
| POST | `/api/report` | `{ward, household?, item, bin_used}` → verdict + green points |
| POST | `/api/sim/advance` | `{days: 1..60}` run the collection and move on |
| POST | `/api/sim/reset` | back to day 0 |
| POST | `/api/demo` | reset simulation and regenerate the demo reports |

Bad input gets a JSON error with the matching status code (400 / 404 / 405 / 413), and the server stays up.

All data is synthetic and generated deterministically (seed 2026). The constants marked "approx." in `wastewise/config.py` are planning assumptions, not measurements.
