# StudyPilot – your offline AI study companion

**Domain:** Artificial Intelligence & Machine Learning · **Port:** 8001 · Built for QUANTIX 2K26 · KSRCE

Paste (or upload) your lecture notes and StudyPilot turns them into an exam plan:
a TextRank summary, weighted key concepts, an auto-generated quiz, SM-2 spaced-repetition
flashcards, "Ask your notes" question answering (BM25) and an exam-readiness score.
All NLP is written from scratch in pure Python: no internet, no API keys, no pip install.

![StudyPilot screenshot](docs/screenshot.png)

## Quick start

```bash
cd projects/01-studypilot
python app.py                 # http://127.0.0.1:8001/
python app.py --host 0.0.0.0  # let phones on the same Wi-Fi open it
```

Click **Load demo notes** (or one of *Deadlocks · Basics · TCP/IP*), then explore the tabs.

```bash
python -m unittest discover -s tests   # 34 unit + API tests
python -m studypilot.evaluation        # ROUGE-1, QA hit rate, latency report
```

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | liveness + version |
| GET | `/api/samples` · `/api/samples/{id}` | bundled demo note sets |
| GET / POST | `/api/docs` | list docs / analyse new notes `{title, text, sample?}` |
| GET / DELETE | `/api/docs/{id}` | doc text, stats, suggested questions / delete |
| GET | `/api/docs/{id}/summary?n=6` | TextRank summary + per-sentence scores, neighbours, graph edges |
| GET | `/api/docs/{id}/concepts?k=30` | RAKE key concepts with weights and evidence |
| GET | `/api/docs/{id}/quiz?n=8&seed=0` | cloze + MCQ questions (answers withheld) |
| POST | `/api/docs/{id}/quiz/grade` | `{n, seed, answers:{qid: answer}}` → grades, explanations, mastery |
| GET | `/api/docs/{id}/flashcards` | cards, SM-2 state, due queue, button previews |
| POST | `/api/docs/{id}/flashcards/review` | `{card_id, rating: again\|hard\|good\|easy}` |
| POST | `/api/docs/{id}/flashcards/reset` | clear the schedule |
| GET / POST | `/api/docs/{id}/ask` | `{question, k}` (or `?q=`) → passages, highlights, BM25 contributions, confidence |
| GET | `/api/docs/{id}/mastery` | readiness %, per-concept mastery, study-next list |

State (docs, flashcard schedules, quiz history) is stored in `data/state.json`, created on first run.
Sample notes are also written to `data/samples/*.md` for the upload demo.

## Layout

```
app.py              HTTP server (stdlib ThreadingHTTPServer)
studypilot/         text.py (tokenizer, sentence splitter, stop words, stemmer)
                    textrank.py · keyphrases.py (RAKE) · bm25.py · quiz.py · flashcards.py
                    srs.py (SM-2) · mastery.py · analysis.py · store.py · samples.py · evaluation.py
static/             index.html · style.css · app.js (vanilla, no CDN)
tests/              test_core.py · test_api.py
```

See [REPORT.md](REPORT.md) for the full write-up.
