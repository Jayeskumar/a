# ResumeRadar

**Fair, explainable AI resume screening and career coaching.** Domain: Artificial Intelligence & Machine Learning.

ResumeRadar ranks a pile of plain-text resumes against a job description and explains every point of
every score. A 231-skill ontology understands synonyms ("JS" = JavaScript, "k8s" = Kubernetes), so good
candidates are not rejected for their wording. **Blind mode** masks names, gendered words, college names,
age, photo and contact details before scoring. A built-in bias check re-scores everyone with identity
deleted and with identity swapped, and shows that the ranking is identical. Students get the other side:
missing skills, a prerequisite-ordered learning plan, bullet rewrites, an ATS check and interview questions.

Pure Python standard library + vanilla JS. No pip install, no CDN, no internet, no API key.

![ResumeRadar screenshot](docs/screenshot.png)

## Quick start

```bash
cd projects/08-resumeradar
python app.py                 # http://127.0.0.1:8008/
python app.py --host 0.0.0.0  # let judges open it from a phone on the same Wi-Fi
```

Click **Load demo data**. This screens 20 synthetic resumes against a Python backend JD in blind mode.

```bash
python -m unittest discover -s tests   # 77 tests
python -m resumeradar.evaluate         # the numbers in REPORT.md
python -m resumeradar.demo             # regenerate data/demo.json (seeded, deterministic)
```

## API

| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET | `/api/health` | | status, version, skill count |
| GET | `/api/demo` | | 3 JDs + 20 demo resumes |
| GET | `/api/config` | | score weights and every tunable constant |
| GET | `/api/ontology` | `?q=k8s` | skills, aliases, prerequisites, stats |
| GET | `/api/eval` | `?refresh=1` | ranking agreement, extraction P/R, fairness, latency |
| POST | `/api/screen` | `{jd, resumes:[{id,name,text}], blind}` | ranked candidates with full reports |
| POST | `/api/bias-check` | `{jd, resumes}` | scores as submitted / identity deleted / identity swapped, blind vs standard |
| POST | `/api/match` | `{resume, jd, blind}` | one full report: breakdown, gaps, plan, ATS, interview |
| POST | `/api/parse-resume` | `{text, blind?}` | extracted skills, roles, years, education, projects |
| POST | `/api/parse-jd` | `{text}` | must-have / nice-to-have requirements, years, degree, bias lint |
| POST | `/api/mask` | `{text}` | blind-mode text and an audit list of what was hidden |
| POST | `/api/ats` | `{text, jd?}` | ATS-friendliness checks and score |
| POST | `/api/learning-path` | `{targets:[skill], known:[skill]}` | topologically sorted study plan |
| POST | `/api/interview` | `{resume, jd, blind?}` | technical + project + behavioural questions |

Errors come back as JSON `{"error": ...}` with status 400/404/405/413/500. Bad input never crashes the server.

## Layout

```
app.py                  HTTP server (ThreadingHTTPServer), routing, validation
resumeradar/            pure logic, no HTTP
  config.py             all weights and assumptions in one place
  ontology.py           231 skills, 908 aliases, prerequisites, families
  extract.py            resume parser: sections, skills, dated roles, education, projects
  jd.py                 JD parser: must vs nice, either-or groups, bias lint
  tfidf.py              TF-IDF + cosine from scratch
  scoring.py            weighted, explainable match score
  blind.py              identity masking, stripping, counterfactual swaps
  screening.py          bulk ranking, bias check, Spearman
  gaps.py               Kahn topological learning path, bullet analysis and rewrites
  ats.py                ATS-friendliness rules
  interview.py          question bank (115 questions over 66 skills) + generator
  demo.py               seeded demo data and hand labels
  evaluate.py           offline evaluation
static/                 index.html, app.js, style.css (inline SVG charts)
data/demo.json          generated demo set
tests/                  unittest suite
```

All people, companies and contact details in the demo data are fictional.
