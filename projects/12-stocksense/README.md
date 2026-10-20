# StockSense

**Demand forecasting and smart reordering for neighbourhood stores** · Data Science & Analytics · QUANTIX 2K26

Kirana stores, pharmacies and college canteens reorder by gut feel: fast movers run out, perishables
expire, and nobody has analytics. StockSense reads plain daily sales and gives the shopkeeper a
morning reorder list. Each line comes with its quantity, its stock-out risk, the rupees at stake and
the arithmetic behind it. Every algorithm is written from scratch in the Python standard library and
runs offline on a basic laptop.

![StockSense dashboard](docs/screenshot.png)

## Quick start

```bash
cd projects/12-stocksense
python app.py                 # http://127.0.0.1:8012/
python app.py --host 0.0.0.0  # let judges open it from a phone on the same Wi-Fi
python -m unittest discover -s tests
python -m stocksense.synth    # regenerate the deterministic demo data in data/
```

You need Python 3.9 or newer. There is nothing to install and no network access is needed. On
start-up the server analyses 40 SKUs × 400 days (4 models, rolling backtests, a 90-day simulation)
in about 1.5 s.

## What it does

- **4 forecasting models per SKU:** seasonal naive, moving average, additive Holt-Winters (weekly
  season, damped trend) and a regression on day-of-week, festival and promotion features.
- **Automatic rolling-origin backtesting.** The model with the lowest sMAPE wins for each SKU, and
  you can see the full leaderboard.
- **Festival-aware forecasts.** Last year's Diwali and Pongal spikes are measured per SKU, shrunk
  when the signal is weak, and re-applied to upcoming festivals.
- **Stock-out cleaning.** Censored days are flagged or detected, then imputed before fitting.
- **Inventory optimisation:** safety stock = z·σ (z from a hand-written inverse-normal), reorder
  point, EOQ, shelf-life cap for perishables, and case-pack rounding.
- **Today's reorder list** with run-out risk (if you skip vs if you order), sales at risk and a
  plain-English reason. A what-if slider shows how service level trades off against cost.
- **ABC–XYZ matrix** (revenue Pareto × weekly demand CV) with a strategy for each cell.
- **Apriori market-basket rules** (support, confidence, lift), turned into shelf and bundle
  suggestions.
- **Policy simulation.** The last 90 days are replayed under gut-feel ordering and under StockSense
  to compare stock-outs, lost sales, waste, holding cost and total cost.
- **CSV upload** (`date, sku, qty` plus optional columns) with validation and readable errors.

## Results on the demo store

| Measure | Seasonal naive / gut feel | StockSense |
|---|---|---|
| Daily forecast WAPE, unseen last 14 days | 47.9% | **28.4%** |
| 14-day total demand error per SKU | 28.8% | **11.7%** |
| Stock-out SKU-days, 90-day replay | 309 | **17** |
| Lost sales, 90 days | ₹2,06,333 | **₹9,930** |
| Expired units, 90 days | 98 | **81** |
| Total inventory cost, 90 days | ₹69,155 | **₹34,903** |

StockSense holds more stock on average (₹1.71 L vs ₹0.95 L), because EOQ favours fewer, larger
orders. See [REPORT.md](REPORT.md) for the full evaluation and its caveats.

## API

| Method | Path | Returns |
|---|---|---|
| GET | `/api/health` | liveness, dataset info, endpoint list |
| GET | `/api/summary?service=0.95` | KPI tiles, hold-out accuracy, simulation headline, festival alert |
| GET | `/api/trend` | store revenue history + 28-day forecast with 80% band |
| GET | `/api/skus` | SKUs with class, chosen model, status |
| GET | `/api/sku/<SKU>?service=0.95` | drill-down: history, all model forecasts, leaderboard, policy maths, drivers, basket, simulation |
| GET | `/api/leaderboard` | backtest metrics per model and per SKU, hold-out comparison |
| GET | `/api/reorder?service=0.95` | today's reorder list with risk, rupee impact and reasons |
| GET | `/api/whatif?service=0.95` | service level vs holding / stock-out cost curve, optimum |
| GET | `/api/abcxyz` | 3×3 matrix, Pareto curve, per-cell strategy |
| GET | `/api/basket?min_support=0.02&min_confidence=0.3` | Apriori itemsets, rules, shelf suggestions |
| GET | `/api/simulation?service=0.95` | gut feel vs StockSense over the last 90 days (totals, per SKU, daily trajectories) |
| GET | `/api/festivals` | upcoming festival demand plan |
| GET | `/api/sample.csv` | sample upload file |
| POST | `/api/upload` | upload a sales CSV (`text/csv` body or JSON `{"csv": "..."}`) |
| POST | `/api/demo` | reload the demo dataset |
| POST | `/api/stock` | `{"sku", "on_hand", "on_order"}`: update stock and recompute |

## Layout

```
app.py                  HTTP server (ThreadingHTTPServer), static files + JSON API
stocksense/config.py    every tunable assumption, with its reasoning
stocksense/synth.py     deterministic demo data (sales, POS bills, stock on hand)
stocksense/dataset.py   CSV validation, stock-out detection and cleaning
stocksense/forecast.py  festival layer, seasonal naive, moving average, Holt-Winters, regression
stocksense/backtest.py  rolling-origin splits, metrics, model selection
stocksense/inventory.py safety stock, ROP, EOQ, perishable cap, reorder list, trade-off curve
stocksense/abcxyz.py    ABC-XYZ classification
stocksense/apriori.py   Apriori + association rules + shelf suggestions
stocksense/simulate.py  90-day policy replay
stocksense/engine.py    orchestration and API payloads
static/                 index.html, app.js, style.css (hand-drawn SVG charts, light/dark)
tests/                  44 unittest tests
```
