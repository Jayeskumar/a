# AirSense - Hyperlocal air quality: know before you breathe

**Domain:** Sustainability, CleanTech & Green Energy · **QUANTIX 2K26, KSRCE**

One official monitoring station often stands in for a whole town, so people living next to a highway,
an industrial cluster, a construction site or burning fields have no local data. AirSense turns a
network of cheap, noisy PM sensors into trustworthy hyperlocal air quality. It calibrates each sensor
against a reference, catches faulty sensors, computes the India National AQI (CPCB) correctly, draws a
live heat map with uncertainty, forecasts the next 24 hours, points at likely sources from wind
direction and tells asthma patients, parents and outdoor workers when to stay in, and when to go for a run.

Every algorithm is written from scratch in plain Python. It runs offline on any laptop.

![AirSense dashboard](docs/screenshot.png)

## Quick start

```bash
cd projects/15-airsense
python app.py                    # http://127.0.0.1:8015/
python app.py --host 0.0.0.0     # so judges can open it from a phone on the same Wi-Fi
python -m unittest discover -s tests
```

Python 3.9+ only. Nothing to install: no pip, no numpy, no CDNs. Click **Run demo** in the header for a
guided tour (festival night, monsoon rain, source hints, tomorrow's forecast). The demo data is synthetic
and deterministic (seed 2026); `python -m airsense.simulate` rewrites `data/`.

## What's inside

| Feature | How |
|---|---|
| CPCB National AQI | Official breakpoints for PM2.5, PM10, NO2, SO2, CO, O3, NH3 (`airsense/config.py`), linear interpolation, 24-h / 8-h averaging, 16-hour minimum, ">= 3 pollutants incl. PM" rule, prominent pollutant |
| Sensor calibration | Per sensor: kappa-Koehler humidity-growth correction, then multiple linear regression on PM, RH and T, fitted on a co-location week. PM2.5 RMSE 43.6 -> 2.4 ug/m3 on hold-out days |
| Fault detection | Stuck readings (run length), spikes (robust z in time and against the neighbours' median), drift (robust z of the log-ratio to the spatial median). 95% precision, 100% recall on 20 injected faults |
| Heat map | IDW in the browser for smooth playback; ordinary kriging with a fitted exponential variogram on the server, with a 90% interval for any clicked spot |
| 24-hour forecast | Seasonal profile + AR terms + weather features on log PM, iterated 24 h. MAE 6.0 vs 16.1 ug/m3 for persistence; 80% interval covers 79.8% |
| Source hints | Pollution roses per sensor plus upwind concentration-weighted rays (CWT/PSCF-style) - finds the industrial cluster within 0.2 km |
| Health | CPCB health statements, advice for 5 profiles, forecast alerts with the rule that fired, best hour for a run |

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Status, data size, pipeline timings |
| GET | `/api/meta` | Map, sensors, events, AQI categories and breakpoints, profiles, headline metrics |
| GET | `/api/frames` | Every hour x sensor: calibrated PM2.5/PM10, 1-h and 24-h AQI, QA flags, wind, rain |
| GET | `/api/summary[?hour=]` | Town median AQI, worst/best spot, official station AQI |
| GET | `/api/sensor?id=S07` | Raw vs calibrated vs reference, flags with reasons, calibration model, rose, forecast |
| GET | `/api/estimate?x=5&y=4[&hour=]` | Kriging + IDW estimate at any point, AQI with 90% interval, nearest-sensor weights |
| GET | `/api/grid?hour=&method=kriging\|idw&field=pm25\|pm10&nx=&ny=` | Interpolated grid (and kriging std. dev.) |
| GET | `/api/forecast?id=S13` or `?x=&y=` `[&profile=asthma]` | 24-h forecast, interval, alerts, best time for a run |
| GET | `/api/faults` | Detected fault events, evaluation vs injected faults, threshold sweep |
| GET | `/api/sources` | CWT grid, hotspots with likely source, pollution roses |
| GET | `/api/evaluation` | Calibration, faults, forecast, interpolation, variogram, hidden exposure, timings |
| GET | `/api/advice?aqi=150&profile=children` | CPCB statement + profile advice |
| POST | `/api/aqi` | `{"pm25": 84, "pm10": [hourly...], "co": 1.2, ...}` -> sub-indices, AQI, validity, advice |
| POST | `/api/demo/reset` | Regenerate the deterministic demo data and re-run every model |

Errors come back as JSON (`{"error": ..., "status": ...}`) with status 400, 404, 405 or 413.

## Layout

```
app.py              HTTP server (ThreadingHTTPServer)
airsense/           pure logic: config, aqi, calibration, faults, interpolate, forecast,
                    sources, health, simulate (data generator), mathx (stats/linear algebra), engine
static/             index.html, app.js, style.css (canvas map, hand-drawn SVG charts)
data/               synthetic network: field.csv, colocation.csv, reference.csv, weather.csv,
                    ground_truth.csv (evaluation only), meta.json (injected faults, events)
tests/              unittest: AQI boundaries, models, pipeline quality, HTTP API
```

The data is **synthetic**. The town layout is only loosely inspired by Tiruchengode/Namakkal and is not
real geography. The hourly AQI on the map applies CPCB breakpoints to 1-hour values and is labelled
indicative; the official CPCB AQI (24-h / 8-h averages) is shown alongside.
