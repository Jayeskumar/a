# BloodLink

**Find the right blood donor in minutes, not hours.** HealthTech & Biomedical Innovation, QUANTIX 2K26.

When a patient needs blood, families forward WhatsApp messages to everyone they know: half the
people who reply donated last month, the right group is never filtered, and the same few
donors get spammed. Meanwhile one blood bank throws away expired units that another needed.
BloodLink ranks *eligible, compatible* donors with a transparent score, alerts them in waves
until the units are collected, and balances stock across blood banks before it expires.

![BloodLink screenshot](docs/screenshot.png)

> Prototype with synthetic data. Actual transfusion decisions follow ABO/Rh grouping and
> cross-matching by qualified blood bank staff.

## Quick start

```bash
python app.py                 # http://127.0.0.1:8010/
python app.py --host 0.0.0.0  # open from a phone on the same Wi-Fi
python -m unittest discover -s tests      # 91 tests
python -m bloodlink.evaluate              # reproduce the numbers in REPORT.md
python -m bloodlink.dataset               # regenerate data/*.json (deterministic)
```

Python 3.9+ standard library only. No pip, no internet, no CDNs. Press **Run demo**.

## What it does

- **ABO/Rh compatibility** derived from antigens (red cells, plus plasma), tested on all 64 pairs.
- **Eligibility gates** as named constants: 90/120-day interval (men/women), age 18-65, weight >= 45 kg,
  deferrals - ineligible donors are excluded with the reason and the date they become eligible.
- **Explainable ranking**: compatibility (exact match preferred) + haversine travel time + Beta-smoothed
  response history + last-contacted fairness. Every rank shows its points and why it beat the next one.
- **Wave broadcast simulator** with a live timeline, compared with "forward to everyone" and a
  "first-come phone list" on the same donors and the same random draws.
- **Blood bank network**: 5 banks, FEFO issue, 7-day moving-average forecast, FEFO expiry-risk
  projection, greedy inter-bank transfer suggestions, and a month simulation with vs without transfers.
- **Donor app**: eligibility self-check, next eligible date, badges, availability toggle.
- SVG map (no tiles), light/dark mode, works on a phone.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | liveness |
| GET | `/api/meta` | groups, hospitals, banks, towns, constants, compatibility matrices |
| GET | `/api/compatibility` | red-cell and plasma 8x8 matrices |
| GET | `/api/map` | all donor points with eligibility flag |
| GET | `/api/donors?q=&group=&limit=` | donor list with eligibility |
| GET | `/api/donors/<id>` | donor card: eligibility rules, badges, history |
| POST | `/api/donors/<id>/availability` | `{"available": false}` pause alerts |
| POST | `/api/match` | `{"hospital_id":"H1","group":"A+","units":3,"urgency":"critical"}` (or `lat`/`lon`) -> ranked + excluded donors |
| POST | `/api/simulate` | same body + `seed` -> 3 strategies, timelines, curves |
| POST | `/api/broadcast` | run the wave plan and commit it (last-contacted, response history, donation date) |
| GET | `/api/evaluate?n=300&seed=11&factor=` | Monte Carlo comparison of strategies |
| POST | `/api/eligibility` | self-check `{"age","sex","weight_kg","last_donation","hb","unwell","today"}` |
| GET | `/api/inventory` | stock per bank x group, forecasts, at-risk units, transfer suggestions |
| POST | `/api/inventory/issue` | FEFO issue `{"bank_id","group","units","allow_substitutes"}` |
| POST | `/api/inventory/transfers/apply` | apply the current suggestions (demo) |
| GET | `/api/inventory/month?seeds=20` | 30-day simulation with vs without transfers |
| GET | `/api/activity` | committed wave plans |
| POST | `/api/demo/reset` | restore the original demo state |

## Layout

```
app.py              HTTP server (ThreadingHTTPServer), static files + JSON API
bloodlink/          pure logic: compat, eligibility, geo, ranking, simulation, inventory,
                    dataset (seeded generator), service (demo state), evaluate, config
static/             index.html, app.js, style.css (vanilla, hand-drawn SVG charts and maps)
data/               donors.json, network.json (generated deterministically, seed 2026)
tests/              unittest suite
```
