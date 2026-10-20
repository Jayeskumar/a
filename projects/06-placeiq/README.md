# PlaceIQ

**Placement analytics that tells every student what to fix next.** Domain: Data Science & Analytics.

PlaceIQ replaces the placement cell's spreadsheet with a dashboard that predicts each student's
placement probability, explains the prediction, and gives the student a minimum-effort plan
("clear 1 backlog, solve 80 more coding problems") that lifts them above 70%. Logistic regression,
linear regression, k-means++, the counterfactual planner and every metric are written from scratch
in pure Python. No pip installs, no CDNs, and it runs fully offline.

![PlaceIQ student coach](docs/screenshot.png)

## Quick start

```bash
cd projects/06-placeiq
python app.py                 # http://127.0.0.1:8006/
python app.py --host 0.0.0.0  # let phones on the same Wi-Fi open it
python -m unittest discover -s tests
```

Start-up generates the deterministic 600-student demo cohort and trains every model in about 3 s.
Click **Load demo data** at any time to reset. On the *Data / upload* tab, **Try a file with errors**
shows CSV validation at work.

## API

| Method | Path | What it returns |
|---|---|---|
| GET | `/api/health` | liveness check |
| GET | `/api/dataset?limit=` | source, row counts, departments, batches, last upload report, sample rows |
| POST | `/api/demo` | reload the synthetic cohort and retrain |
| POST | `/api/upload?filename=` | CSV body (`text/csv`, or JSON `{"csv": "..."}`); validates, reports bad rows, retrains (422 if unusable) |
| GET | `/api/sample.csv` | the demo cohort as CSV (column template) |
| GET | `/api/eda` | per-column stats and histograms, placement by department, Pearson matrix, top drivers |
| GET | `/api/model` | hold-out metrics, ROC points, confusion matrix, coefficients, scaler, loss curve, package regression, fairness |
| GET | `/api/fairness?threshold=` | per-department accuracy, FPR, FNR and calibration gap (5-fold out-of-fold) |
| GET | `/api/dashboard?dept=&batch=` | KPI tiles, department rates, probability bands, personas, common gaps |
| GET | `/api/students?dept=&batch=&q=&limit=` | students with predicted probability, lowest first |
| GET | `/api/student/<id>?target=` | probability, contributions, counterfactual plan, top gap, persona, expected package |
| POST | `/api/predict` | `{"features": {...12 columns...}, "target": 0.7}` gives the same explanation for any what-if profile |
| GET | `/api/at-risk?threshold=&dept=&batch=&include_placed=` | at-risk list with top gap and plan effort |
| GET | `/api/at-risk.csv?...` | the same list as a CSV download |
| GET | `/api/clusters?k=2..6` | k-means++ personas with profiles and department mix |

## Layout

```
app.py              HTTP server (ThreadingHTTPServer), static files + JSON API
placeiq/config.py   every tunable assumption (effort costs, step sizes, hyper-parameters)
placeiq/data.py     documented latent-variable generator + CSV validation
placeiq/models.py   scaler, logistic regression (GD + L2), ridge regression, splits
placeiq/metrics.py  accuracy/precision/recall/F1, ROC-AUC (rank method), ROC curve, R², MAE
placeiq/stats.py    summary stats, histograms, Pearson correlation
placeiq/cluster.py  k-means with k-means++ init, persona naming
placeiq/explain.py  contributions + exact minimum-effort counterfactual (dynamic programming)
placeiq/engine.py   ties it together: training, evaluation, fairness, dashboards
static/             index.html, app.js (hand-drawn SVG charts), style.css, samples/
data/               students_demo.csv + make_samples.py
tests/              46 unittest tests
```

See [REPORT.md](REPORT.md) for the full write-up and measured results.
