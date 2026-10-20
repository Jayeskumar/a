# LogSentinel

**A pocket SOC: detect attacks hiding in your server logs.**
Domain: Cybersecurity & Blockchain Technology · QUANTIX 2K26 · KSRCE

LogSentinel reads the logs nobody ever reads — Apache/Nginx access logs, Linux
`auth.log`, and firewall drops — and surfaces the attacks buried in them: SSH
brute force, password spraying, credential stuffing, likely account compromise,
web injection (SQLi/XSS/traversal), vulnerability scanners, port scans and
off-hours admin logins. Every finding comes with evidence, a MITRE ATT&CK
mapping, and a recommended response. It runs entirely offline on a cheap laptop
— Python standard library only, no pip, no CDN, no cloud.

This is a **defensive** tool. It detects and reports; it never attacks and never
touches your firewall. Exports (blocklists) are plain text for you to review.

## Quick start

```bash
cd projects/13-logsentinel
python app.py                 # http://127.0.0.1:8013/
python app.py --host 0.0.0.0  # open it from a phone on the same LAN
```

It boots with a deterministic demo log already analysed (12k lines, ~16 alerts,
9 incidents). Click **Run demo** to regenerate it, or **Upload log** to paste or
drop your own file.

Run the tests and regenerate the committed sample data:

```bash
python -m unittest discover -s tests
python -m logsentinel.evaluation          # prints precision/recall/throughput
python -c "from logsentinel import generator; generator.write_files('data')"
```

## How it works (three complementary detectors)

1. **Signatures** — URL-decode the request first (twice, to defeat
   double-encoding), then regex for SQLi / XSS / path-traversal / command
   injection payloads and known scanner user-agents.
2. **Correlation** — stateful sliding windows over an IP's history: N failures
   in T seconds (brute force), one IP ↔ many usernames (spraying/stuffing),
   failures-then-success (compromise), many distinct ports (scan), many 404s
   (enumeration), off-hours privileged logins, and sudo escalation.
3. **Anomaly** — per-IP request rate via EWMA mean + variance with a z-score,
   plus user-agent and path-shape novelty after a warm-up baseline.

Alerts from the same source IP and time window are merged into an **incident**
with a kill-chain timeline (Reconnaissance → Credential Access → Exploitation →
Initial Access → Privilege Escalation).

## API

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/health` | status + counts |
| GET | `/api/summary` | KPIs, severity counts, top attackers, categories |
| GET | `/api/alerts?severity=&category=&src=&rule=` | filtered alert list |
| GET | `/api/alert/<id>` | one alert: evidence, MITRE, response |
| GET | `/api/incidents` | incidents with kill-chain phases |
| GET | `/api/incident/<id>` | one incident + its alerts + timeline |
| GET | `/api/rpm` | requests-per-minute series with anomaly markers |
| GET | `/api/stream?offset=&limit=` | tail-replay chunk of parsed events |
| GET | `/api/blocklist` | attacker IPs as iptables/fail2ban text |
| GET | `/api/report/<id>?format=md\|html` | incident report export |
| GET | `/api/evaluation` | precision/recall vs. ground truth + throughput |
| POST | `/api/analyze` | analyse uploaded log text (raw or JSON `{"log": "..."}`) |
| POST | `/api/demo/reset` | regenerate and re-analyse the demo log |

## Layout

```
app.py                 entry point (stdlib http.server)
logsentinel/           pure logic: parsers, signatures, correlation, anomaly,
                       incidents, engine, generator, evaluation, reports
static/                index.html, app.js, style.css (console dashboard)
data/                  deterministic sample.log, benign.log, ground_truth.json
tests/                 unittest suite (67 tests)
docs/screenshot.png    dashboard screenshot
```

## Safety & data

All IPs in the generated data use RFC 5737 documentation ranges
(203.0.113.0/24, 198.51.100.0/24, 192.0.2.0/24) and RFC 1918 private space —
never a real address. The tool performs no outbound network calls and executes
nothing; the blocklist is text you apply yourself after review.

![LogSentinel dashboard](docs/screenshot.png)

Built for QUANTIX 2K26 · KSRCE.
