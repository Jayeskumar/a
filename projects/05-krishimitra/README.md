# KrishiMitra · கிருஷிமித்ரா

**A smart farming advisor in the farmer's own language.** Domain: Smart Agriculture & Rural Development (AgriTech).

KrishiMitra turns a soil test and local weather into four decisions a smallholder farmer actually makes:
*what to grow, how much fertiliser to buy, when to irrigate, and when to sell*. Everything is shown in
**English or Tamil**, can be **read aloud**, and runs **fully offline** on a cheap laptop. All the ML and
agronomy maths is written from scratch in Python's standard library.

![KrishiMitra screenshot](docs/screenshot.png)

## Quick start

```bash
cd projects/05-krishimitra
python app.py                 # http://127.0.0.1:8005/
python app.py --host 0.0.0.0  # open it from a phone on the same Wi-Fi
python -m unittest discover -s tests        # 56 tests
python -m krishimitra.evaluate              # accuracy + latency -> data/metrics.json
```

No `pip install`, no internet. Python 3.9+.

## What it does

| Module | Method (from scratch) |
|---|---|
| Crop recommendation (14 Tamil Nadu crops) | Gaussian Naive Bayes + Random Forest (CART, bootstrap, feature bagging), blended top-3 |
| Explanation | NB per-input log-likelihood vs runner-up crop; RF Saabas path contributions |
| Fertiliser advisor | dose − soil credit → deficit → Urea / DAP / MOP per acre + bags + organic options |
| Irrigation scheduler | FAO-56 Ra + Hargreaves ET0 × Kc(stage) − effective rain → 7-day bucket plan in mm and litres |
| Market timing | Synthetic seasonal mandi series → MA4/MA12, ratio-to-moving-average seasonal index, trend → sell/hold |
| Crop calendar | Stage timeline (land prep → nursery → stages → harvest) with key operations |

All agronomic ranges, doses and prices are **approximate / illustrative** and prices are **synthetic**;
every assumption is a named constant in `krishimitra/config.py`.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | liveness |
| GET | `/api/meta` | crops (EN/TA), feature limits, soils, methods, presets, model metrics |
| GET | `/api/presets` | demo farms |
| GET | `/api/model` | hold-out accuracy, training time, RF feature importance |
| POST | `/api/recommend` | `{N,P,K,ph,temperature,humidity,rainfall}` → top-3 (blend, GNB, RF) + explanation |
| POST | `/api/fertiliser` | `{crop,N,P,K,ph?,area_acres?}` → Urea/DAP/MOP per acre, schedule, organic |
| POST | `/api/irrigation` | `{crop,lat,sowing_date,start_date?,soil,method,area_acres?,forecast?}` → 7-day plan |
| GET | `/api/market?crop=&date=` | price history, MAs, seasonal index, forecast band, sell/hold |
| GET | `/api/calendar?crop=&sowing_date=` | stage timeline + operations |
| GET | `/api/et0?lat=&doy=&tmin=&tmax=` | Ra and Hargreaves ET0 calculator |
| GET | `/api/forecast?lat=&date=` | deterministic synthetic 7-day weather |
| POST | `/api/advise` | everything above in one call + bilingual spoken summary |

Bad input returns JSON `{"error": ...}` with status 400/404/405/413; the server never crashes on it.

## Layout

```
app.py              HTTP server (ThreadingHTTPServer), static files + JSON API
krishimitra/        config, dataset, gnb, forest, recommender, fertiliser, irrigation,
                    weather, market, cropcal, i18n, advisor, evaluate
static/             index.html, app.js, i18n.js (EN/TA labels), style.css
data/               crop_dataset.csv (deterministic, seed 42), metrics.json
tests/              unittest suite
```
