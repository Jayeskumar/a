# PhishGuard

**Explainable scam & phishing detector for SMS, email and links** - QUANTIX 2K26, domain *Cybersecurity & Blockchain Technology*.

Paste a suspicious SMS, WhatsApp forward, e-mail or link and PhishGuard returns a 0-100 risk score, a
Safe / Suspicious / Dangerous verdict and the reasons behind it: highlighted words, the India-specific scam
rules that fired (KYC, EB disconnection, UPI collect, job fee, OTP requests, digital arrest...), a score for every
embedded link, phone number and UPI ID, and what to do next (helpline **1930**, cybercrime.gov.in).
Everything - Naive Bayes, logistic regression, URL features, rules - is written from scratch in the Python standard
library and runs offline. Nothing you paste leaves the device.

![PhishGuard screenshot](docs/screenshot.png)

## Quick start

```bash
cd projects/07-phishguard
python app.py                    # http://127.0.0.1:8007/
python app.py --host 0.0.0.0     # let phones on the same Wi-Fi open it
python -m unittest discover -s tests
python -m phishguard.corpus      # regenerate data/messages.json and data/urls.json
```

Python 3.9+ only, no `pip install`. Models train in about 1 s at start-up; metrics are written to `data/metrics.json`.

## API

| Method | Path | Body / result |
|---|---|---|
| GET | `/api/health` | status, training time |
| POST | `/api/analyze` | `{"text": "...", "kind": "auto" \| "message" \| "url"}` -> risk, verdict, components, rules, NB tokens, entities, highlighted segments, advice, latency |
| POST | `/api/url` | `{"url": "..."}` -> URL-model verdict with feature contributions |
| POST | `/api/bulk` | `{"text": "line1\nline2"}` or `{"lines": [...]}` (max 200) -> table of verdicts + summary |
| GET | `/api/stats` | hold-out metrics, confusion matrices, unseen-template check, latency, LR weights, top tokens |
| GET | `/api/samples` | demo messages and bulk-scan demo lines |
| GET | `/api/quiz` | 10 "Spot the scam" questions with answers and explanations |
| GET | `/api/rules` | the rule layer (id, title, weight, advice) |

Errors are JSON (`{"error": ..., "status": ...}`) with 400 / 404 / 413 / 500 codes.

## Layout

```
app.py                  HTTP server (ThreadingHTTPServer), static files + JSON API
phishguard/config.py    every tunable constant, with reasoning
phishguard/corpus.py    deterministic synthetic corpus (760 messages, 440 URLs) + splits
phishguard/text.py      normalisation, word / bigram / char n-gram features
phishguard/naive_bayes.py   Multinomial NB with Laplace smoothing
phishguard/urlfeatures.py   28 lexical URL features
phishguard/logreg.py    logistic regression (batch gradient descent + L2)
phishguard/rules.py     17 India-specific scam rules with negation handling
phishguard/extract.py   URL / phone / UPI / e-mail / amount extraction with offsets
phishguard/entities.py  phone & UPI heuristic scores
phishguard/scorer.py    combined noisy-OR score, explanations, bulk, stats
phishguard/samples.py   hand-written demo messages and quiz (not in the training data)
static/                 index.html, app.js, style.css (no CDN, hand-drawn SVG charts)
tests/                  55 unittest tests
```

See [REPORT.md](REPORT.md) for the full write-up and [pitch.json](pitch.json) for slide content.
