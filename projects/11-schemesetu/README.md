# SchemeSetu

**Every rural family, matched to the welfare schemes they deserve.**
QUANTIX 2K26 · Smart Agriculture & Rural Development (AgriTech)

SchemeSetu is an offline, bilingual (English / தமிழ்) assistant that tells a rural family which of
22 central and Tamil Nadu welfare schemes they qualify for. It explains the answer condition by
condition, asks only the questions that matter, estimates the benefit value, builds one
deduplicated document checklist and tracks applications. Field workers (village volunteers, CSC
operators) also get a village dashboard showing benefits that eligible families have not yet claimed.

> Scheme rules are **simplified for this prototype**. Every scheme card says so. Verify on the official portal.

![SchemeSetu screenshot](docs/screenshot.png)

## Quick start

```bash
python app.py                  # http://127.0.0.1:8011/
python app.py --host 0.0.0.0   # open from a phone on the same Wi-Fi
python -m unittest discover -s tests
python -m schemesetu.evaluate  # regenerate data/evaluation.json (numbers in REPORT.md)
python -m schemesetu.synth     # rewrite the deterministic demo data files in data/
```

Python 3.9+ standard library only. No pip, no internet, no CDN.
In the UI, click a **Load demo family** card. In **Field worker** mode, use **Load demo village**.

## What is inside

| Module | What it does |
|---|---|
| `schemesetu/rules.py` | JSON rule language (all / any / not, comparisons, ranges, membership, named params) with 3-valued logic and a full trace |
| `schemesetu/questionnaire.py` | Picks the next question by greedy expected information gain; screening "gate" questions plus inferences |
| `schemesetu/search.py` | Tamil-aware tokeniser, light stemmers, bilingual concept map, TF-IDF cosine ranking |
| `schemesetu/benefits.py` | Adds fixed amounts only; "one pension per person" groups; conditional amounts kept separate |
| `schemesetu/checklist.py` | Union of required documents with alias-based deduplication |
| `schemesetu/store.py` / `village.py` | Households + application tracker in `data/state.json`; unclaimed-benefit dashboard |
| `data/schemes.json`, `questions.json`, `keywords.json` | Catalogue (22 schemes), question bank (22 facts + 4 screening questions), bilingual keyword map |

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | status, counts, engine start-up time |
| GET | `/api/meta` | categories, documents, named params, statuses |
| GET | `/api/schemes[?category=]`, `/api/schemes/<id>` | catalogue |
| GET | `/api/questions` | question bank, inferences, learnt answer priors |
| POST | `/api/evaluate` `{profile}` | status + explanation trace for every scheme, benefit estimate |
| POST | `/api/next` `{profile, skipped[], strategy?}` | next best question (with "why") + evaluation |
| POST | `/api/simulate` `{demo}` or `{profile}` | run the adaptive questionnaire against a full profile |
| GET | `/api/search?q=&k=` | bilingual TF-IDF search |
| POST | `/api/checklist` `{scheme_ids[], extra?}` | deduplicated document checklist |
| GET | `/api/demo` | the 4 demo families |
| GET / POST | `/api/households[?village=]` | list / register households |
| GET / PUT / POST / DELETE | `/api/households/<id>` | view (with evaluation) / update / delete |
| POST | `/api/households/<id>/applications` `{scheme_id, status}` | tracker: not_applied / applied / pending / received |
| GET | `/api/village[?village=]` | village dashboard of unclaimed benefits |
| POST | `/api/demo/village`, `/api/demo/reset` | seed the demo village / clear all households |
| GET | `/api/evaluation` | measured results (from `data/evaluation.json`) |
