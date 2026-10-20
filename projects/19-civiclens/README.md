# CivicLens

**AI triage and analytics for citizen complaints.** Domain: Data Science & Analytics.

Municipalities and college administrations get thousands of complaints about potholes, garbage,
streetlights, water leaks, drainage, stray animals and hostel problems. They arrive in English, Tamil and
Tanglish through apps, calls and social media. CivicLens routes each complaint to the right department,
sets a P1–P4 priority with a stated reason, merges duplicates into one incident, flags hotspots and wards
that are suddenly getting worse, and predicts which open complaints will breach their SLA. Every model is
written from scratch in pure Python: Naive Bayes, logistic regression, MinHash/LSH, DBSCAN, the Poisson
test, Kaplan-Meier and k-means. It needs no pip installs and no CDNs, and it runs fully offline.

![CivicLens triage screen](docs/screenshot.png)

## Quick start

```bash
cd projects/19-civiclens
python app.py                    # http://127.0.0.1:8019/
python app.py --host 0.0.0.0     # let phones on the same Wi-Fi open it
python -m unittest discover -s tests     # 70 tests, about 12 s
python bench.py                  # offline benchmark behind REPORT.md (about 1 min, writes data/bench.json)
python -m civiclens.datagen      # regenerate data/complaints.csv + data/ground_truth.json
```

On start-up the server generates the deterministic stream (3,017 complaints over 13 weeks, seed 2026) and
trains every model. This takes about 9 s. **Run demo** files 8 scripted complaints that exercise every stage:
a live wire reported in Tanglish, a Tamil duplicate of an open complaint, sewage in drinking water,
garbage in a ward with an emerging hotspot, a typo-ridden accident report, a noise complaint, a hostel
complaint and a second report of the live wire. **Reset** removes them again.

## What each tab shows

| Tab | Content |
|---|---|
| Triage | KPI tiles, live queue (routed department, priority, duplicate-of link, SLA clock), a "file a complaint" form with a click-to-place map, and a step-by-step pipeline explanation (word-level contributions, rules that fired, duplicate match evidence, hotspot, breach risk, latency) |
| Map & hotspots | Canvas map of the 20 wards with one dot per de-duplicated incident, DBSCAN hotspots with live eps/minPts sliders, the planted ground-truth overlay, a weekly ward heat grid and the Poisson emerging-hotspot list |
| SLA & risk | Kaplan-Meier "% still open after N days" curves, resolution-time box plots, department scorecards, the at-risk queue with reasons, breach-model weights and a ward ranking |
| Models | NB vs LR accuracy, macro-F1 and per-language results, confusion matrix, top words per department, failure cases, the urgency comparison (rules vs model vs both), duplicate-detection metrics with the LSH S-curve and threshold tuning |
| Topics | k-means topics for "General / Other" complaints, with a silhouette chart, top terms, purity against the planted sub-topics, and examples |

## API

| Method | Path | Returns |
|---|---|---|
| GET | `/api/health` | liveness, complaint count, build time |
| GET | `/api/summary` | KPIs, weekly volumes, department and language mix, emerging hotspots this week, headline metrics |
| GET | `/api/town` | wards (bounds, Tamil names), landmarks, departments with SLA days, channels, DBSCAN defaults |
| GET | `/api/queue?limit=&dept=&priority=&status=open&q=` | triage queue, newest first |
| GET | `/api/complaint/<id>` | one complaint with sibling reports, breach risk and its synthetic ground truth |
| POST | `/api/analyze` | `{"text", "lat", "lon" or "ward", "channel"}`: full pipeline result without filing it |
| POST | `/api/complaints` | same body; files the complaint into the live queue (201) and saves it to `data/filed_complaints.json` |
| POST | `/api/demo/reset` | removes the complaints filed live |
| GET | `/api/demo/samples` | the 8 scripted demo complaints |
| GET | `/api/map?dept=&weeks=` | one point per de-duplicated incident |
| GET | `/api/hotspots?dept=&eps=&min_pts=&weeks=` | DBSCAN clusters matched against the planted hotspots, plus the evaluation |
| GET | `/api/heatgrid?dept=` | ward x week incident counts with emerging flags |
| GET | `/api/emerging?week=5..13` | Poisson z-test flags for one week, plus the evaluation |
| GET | `/api/sla` | Kaplan-Meier curves, resolution statistics and scorecards per department, breach-model evaluation |
| GET | `/api/at-risk?limit=` | open complaints inside their SLA ranked by breach probability, plus the overdue list |
| GET | `/api/wards` | ward ranking by breach rate |
| GET | `/api/models` | every evaluation: routing, urgency, duplicates, hotspots, emerging, breach, timings |
| GET | `/api/topics?k=3..8` | k-means topics of "Other" complaints with silhouette and purity |
| GET | `/api/complaints.csv` | the whole triaged stream as CSV |

Errors come back as JSON `{"error", "status"}` with codes 400, 404, 405 or 413. Bad input never stops the server.

## Layout

```
app.py                 ThreadingHTTPServer: static files + JSON API + input validation
bench.py               offline benchmark (unseen phrasings, ablation, MinHash error, seeds, latency)
civiclens/config.py    every tunable assumption, each with the reason for its value
civiclens/datagen.py   deterministic town + complaint generator (templates in English, Tamil and Tanglish)
civiclens/lexicon.py   bilingual concept lexicon (Tamil and Tanglish -> language-neutral concepts)
civiclens/text.py      Unicode tokenizer that keeps Tamil marks, graphemes, n-grams, concepts, typo tolerance
civiclens/features.py  TF-IDF over word, grapheme and concept blocks
civiclens/models.py    Multinomial NB, logistic regression (SGD + L2), one-vs-rest
civiclens/urgency.py   safety rules and the rules + model policy
civiclens/dedup.py     MinHash, geo-tagged LSH banding, haversine, union-find, learned pair scorer
civiclens/hotspot.py   DBSCAN with a grid index, Poisson z-test and tail probability
civiclens/sla.py       Kaplan-Meier, resolution statistics, breach-model features
civiclens/topics.py    spherical k-means++, silhouette, purity
civiclens/metrics.py   accuracy, F1, confusion, AUC, Brier, ECE, pairwise clustering P/R/F1
civiclens/engine.py    builds, trains and evaluates everything; serves the views and the live pipeline
static/                index.html, app.js (hand-drawn SVG and canvas charts), style.css
data/                  complaints.csv, ground_truth.json, bench.json (filed_complaints.json is created at run time)
tests/                 70 unittest tests
```

See [REPORT.md](REPORT.md) for the full write-up and measured results.
