# WattWise - AI energy & carbon copilot for smart campuses

**Domain:** Sustainability, CleanTech & Green Energy · **QUANTIX 2K26, KSRCE**

WattWise reads hourly smart-meter data for every building on a campus and tells you
what next week will cost, where electricity is being wasted right now (and why), how
much CO₂ that is, whether rooftop solar pays off, and which building is the greenest.
Every model is written from scratch in plain Python. It runs offline on any laptop.

![WattWise dashboard](docs/screenshot.png)

## Quick start

```bash
cd projects/02-wattwise
python app.py                    # http://127.0.0.1:8002/
python app.py --host 0.0.0.0     # so judges can open it from a phone on the same Wi-Fi
python -m unittest discover -s tests
```

Python 3.9+ only. Nothing to install: no pip, no numpy, no CDNs. Click **Run demo** in the header to
regenerate the demo campus (it is deterministic) and start the guided story.

## What's inside

| Feature | How |
|---|---|
| 7-day hourly forecast per building | Robust, recency-weighted multiple linear regression (day-type × hour + temperature), solved by Gaussian elimination. Compared against Holt-Winters and seasonal-naive. |
| Waste detection with reasons | Median + MAD modified z-score per hour-of-week, merged into events, with a rule-based cause in plain language |
| Carbon & cost | Named constants: 0.71 kg CO₂/kWh (approx., CEA), ₹8/kWh, 21 kg CO₂/tree/yr (approx.) |
| Rooftop solar planner | kWp limited by roof or demand, 1,450 kWh/kWp/yr (approx., TN), payback, 25-year cash flow, CO₂ avoided |
| What-if simulator | AC setpoint, auto-off after 9/10/11 PM, LED and BLDC retrofit, applied in sequence so nothing is counted twice |
| Leaderboard | Weather-normalised % saving against each building's own baseline, plus badges |

All assumptions are in `wattwise/config.py`.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Status, data size, compute time |
| GET | `/api/overview` | Campus KPIs, latest alerts, assumptions |
| GET | `/api/buildings` | Building list with metadata |
| GET | `/api/series?building=cse_lab&days=14` | Actual, back-test and 7-day forecast, plus the "why" |
| GET | `/api/forecast?building=admin` | Back-test and forecast only |
| GET | `/api/heatmap?building=library` | 56 days × 24 hours, with flagged hours |
| GET | `/api/anomalies[?building=]` | Waste events with kWh, ₹, CO₂ and the reason |
| GET | `/api/leaderboard` | Rankings, badges and points |
| GET | `/api/evaluation` | MAPE per model, anomaly precision/recall, threshold sweep |
| POST | `/api/solar` | `{roof_area_m2, monthly_kwh \| monthly_bill_inr, tariff?, cost_per_kwp?}` or `{building}` |
| POST | `/api/whatif` | `{ac_setpoint_delta, auto_off, auto_off_hour, led_pct, bldc_pct}` |
| POST | `/api/demo/reset` | Regenerate the deterministic demo data and re-run every model |

Errors come back as JSON (`{"error": ..., "status": ...}`) with status 400, 404, 405 or 413.

## Layout

```
app.py              HTTP server (ThreadingHTTPServer)
wattwise/           pure logic: dataset, forecast, anomaly, carbon, solar, whatif, leaderboard, engine
static/             index.html, app.js, style.css (hand-drawn SVG charts)
data/               meter_data.csv + meta.json (synthetic, seed 2026, ground-truth waste events)
tests/              unittest: core models + HTTP API
```

The data is **synthetic**. It is shaped like a typical Indian engineering campus but was not measured anywhere.
