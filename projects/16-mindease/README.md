# MindEase

**A private, early-support companion for student mental wellbeing.** Domain: HealthTech & Biomedical Innovation · QUANTIX 2K26

MindEase helps college students notice when exam stress, worry or low mood is building, and
makes reaching out easier. Students get a private mood journal, the standard PHQ-9 and GAD-7
check-ins, and a self-help toolkit. Counsellors get an opt-in, pseudonymous early signal.
Everything runs offline on the Python standard library, and every result explains *why*.

> **Supportive screening and self-help only. Not a diagnosis or treatment.** Every screen
> shows Tele-MANAS **14416** / **1-800-891-4416** (free, 24×7) and **112** for emergencies.
> All data in the demo is synthetic.

![MindEase Today view](docs/screenshot.png)

## Quick start

```bash
cd projects/16-mindease
python app.py                  # http://127.0.0.1:8016/
python app.py --host 0.0.0.0   # let phones on the same Wi-Fi open it
python -m unittest discover -s tests   # 100 tests, about 2 s
python -m mindease.evaluation  # re-measure REPORT.md numbers -> data/evaluation.json
python -m mindease.demo_data   # re-export the seeded demo -> data/demo_seed.json
```

Click **Load demo data** to reset to the demo: Ananya's 3-week journal plus a 60-student cohort over
8 weeks. The **Counsellor** tab uses the demo PIN **2468**.

## Features

- **Check-ins:** PHQ-9 and GAD-7 with the standard wording, 0–3 scoring and the published bands.
  If PHQ-9 item 9 is answered above 0, a gentle support screen opens immediately, whatever the
  total.
- **Mood journal:** mood (1–5), sleep hours and a short text entry. A from-scratch lexicon
  analyser reads it: negation ("not happy", Tamil "nalla illa"), intensifiers ("romba", "very"),
  "but" contrast, emoji and some Tanglish. The result is shown as "what the app noticed", with
  each word's score.
- **Safety net:** 41 phrase rules plus a co-occurrence layer flag self-harm and hopelessness
  language and open the same support screen. Hyperbole such as "this exam is killing me" does not
  trigger it.
- **Trend engine:** 7-day rolling means, one-sided CUSUM, a dip-run counter and an OLS slope
  t-test, all against the student's *own* baseline. The output is a kind insight, such as "Your
  mood has dipped for 5 days in a row", with the evidence behind it.
- **Toolkit:** a CSS/JS box-breathing animation, 5-4-3-2-1 grounding, an exam-stress Pomodoro
  planner and timer, and sleep tips. All of it works offline.
- **Talk & support:** a "prepare to talk to someone" script generator, peer-support guidance on
  helping a friend, and signs that it's time to get help.
- **Counsellor dashboard** (demo login): weekly counts by severity band with exam weeks marked, a
  by-year table with small-cell suppression, a list of students who asked to be contacted, and an
  item-9 alert queue with an acknowledge → followed-up workflow. The privacy principles are
  explained on screen.
- **How it works:** the measured accuracy, the ethics and the limitations, shown inside the app.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | liveness + server date |
| GET | `/api/questionnaires` | PHQ-9 / GAD-7 items, options, bands |
| POST | `/api/screening` | `{"instrument":"phq9","answers":[0..3 ×9],"share":true}` → score, band, explanation, support |
| GET | `/api/student` | profile, consent, journal, check-ins, trend analysis |
| POST | `/api/consent` | `{"share_aggregate":bool,"contact":bool}` |
| POST | `/api/journal` | `{"mood":1-5,"sleep":h,"text":"..."}` → entry, analysis, safety, support, insights |
| DELETE | `/api/journal/<id>` | delete an entry |
| POST | `/api/analyze` | `{"text":"..."}` → sentiment + concerning-phrase check (nothing stored) |
| GET | `/api/trends` | series with rolling means, detectors, insights |
| POST | `/api/planner` | `{"exams":[{"subject","date","confidence"}],"hours_per_day","start_time"}` → Pomodoro plan |
| POST | `/api/script` · GET `/api/script/options` | "prepare to talk" script generator |
| GET | `/api/resources` · `/api/support?reason=&level=` | helplines, peer support, sleep tips, support-screen content |
| POST | `/api/support/contact` | `{"reason","preferred"}` → pseudonymous "please reach out" request |
| POST | `/api/demo/reset` · `/api/student/erase` | load demo data · delete all my data |
| POST | `/api/counsellor/login` · `/logout` | `{"pin":"2468"}` → bearer token |
| GET | `/api/counsellor/dashboard` | aggregates, alerts, contacts, privacy (Bearer token) |
| POST | `/api/counsellor/alerts/<id>/ack` · `/followup` | `{"note":"..."}` alert workflow |
| POST | `/api/counsellor/contacts/<id>/done` | mark a contact request handled |
| GET | `/api/evaluation` | the metrics in REPORT.md |

Bad input gets a JSON error with status 400, 401, 404, 405, 409 or 413. The server keeps running.

## Layout

The pure logic lives in `mindease/`:

- `questionnaires.py`, `sentiment.py` + `lexicon.py`, `safety.py`, `trends.py`
- `planner.py`, `talk_script.py`, `resources.py`
- `counsellor.py`, `store.py`, `demo_data.py`
- `evaluation.py` + `eval_sets.py` (the hand-labelled sets)
- `config.py` (every tunable assumption, with its source)

The rest of the project:

- `app.py`: the HTTP server.
- `static/`: the front end.
- `tests/`: the unit tests.
- `data/`: `demo_seed.json` and `evaluation.json`. `state.json` is created on first run.
