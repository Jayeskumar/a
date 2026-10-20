# QUANTIX 2K26: winning strategy and playbook

This is the team's playbook for QUANTIX 2K26. The per-project reports live in each
`projects/<NN-name>/REPORT.md`, the auto-generated portfolio summary is in
[`PORTFOLIO.md`](PORTFOLIO.md), and the pitch decks are in `decks/`.

## 1. Event facts (from the official poster)

| | |
|---|---|
| Event | QUANTIX 2K26, 24-hour hackathon. "Real ideas. Real code. Real impact." |
| Organisers | KSRCE AI Innovation Hub & Quantix Association, Depts. of AI&DS, CSE, CSD, K.S.R. College of Engineering. Sponsor: Praskla Technology |
| Dates / venue | 23–24 October 2026, Emerald Hall, KSRCE |
| Team size / fee | 1–4 members, ₹500 per head |
| Registration | Online closes **22 Oct, 12 pm**; on-spot registration is also available |
| Problem statements | **Released on the spot** (open innovation also allowed) |
| Evaluation | **PPT presentation, then a working product demo** |
| Submit before evaluation | **PPT, GitHub link and demo link** |
| Bring | College ID card, registration details, **one junction box (extension board) per team** |
| Prizes | Rewards for winners plus **pre-placement opportunities** |

Domains: (1) AI & ML, (2) Sustainability, CleanTech & Green Energy, (3) HealthTech & Biomedical,
(4) Cybersecurity & Blockchain, (5) Smart Agriculture & Rural Development, (6) Data Science & Analytics.

## 2. Read this first: the "pre-built code" question

Problem statements are announced on the spot and the event is a 24-hour build. Many hackathons
expect the code to be written during the event. **Before relying on anything in this repository, ask
the faculty coordinator** (Mr. Gopinath V, AI&DS) or a student coordinator listed on the poster:

> "Can we bring prior work or our own libraries, or must all code be written during the 24 hours?"

- **If prior work is allowed:** pitch the closest project, adapt it to the announced problem statement,
  and say openly in the PPT which parts were built before the event and which during it.
- **If it is not allowed:** treat this repository as **practice and preparation**. Each project's
  `REPORT.md` and source show the architecture, algorithms and pitch for a strong solution. Rebuild the
  core during the event, which goes much faster when you have already done it once, and use these as
  reference designs. Don't submit code written before the event as if it were written there.

Being upfront about this protects the team. Judges respect honesty, and a disqualification costs far
more than any head start gains.

## 3. The portfolio: 19 prototypes, every domain covered

| Domain | Lead project | Backup projects | Why the lead wins |
|---|---|---|---|
| AI & ML | **StudyPilot** (01): offline study companion | **ResumeRadar** (08) fair resume screening · **NeuroCanvas** (14) neural-net explainer | Every student judge "gets" it instantly; the AI runs with no API keys |
| Sustainability | **WattWise** (02): campus energy & carbon copilot | **WasteWise** (09) smart bins + routing · **AirSense** (15) hyperlocal AQI | Uses the judges' own campus as the story; ₹ and CO₂ savings on screen |
| HealthTech | **PulseGuard** (03): NEWS2 early-warning ward | **BloodLink** (10) donor matching · **MindEase** (16) student wellbeing | A real clinical standard (RCP NEWS2), a live simulation and a lead-time metric |
| Cyber & Blockchain | **CertChain** (04): tamper-proof certificates | **PhishGuard** (07) scam detector · **LogSentinel** (13) log SOC · **CampusVote** (17) verifiable e-voting | The tamper demo is theatrical; crypto from scratch is checked against the RFC 8032 vectors |
| AgriTech & Rural | **KrishiMitra** (05): Tamil/English farm advisor | **SchemeSetu** (11) welfare schemes · **AgriSky** (18) drone crop health | Local relevance (Tiruchengode farms, Tamil voice); four decisions in one plan |
| Data Science | **PlaceIQ** (06): placement analytics | **StockSense** (12) retail forecasting · **CivicLens** (19) complaint triage | Matches the sponsor's pre-placement theme; tells each student what to fix next |

**If only one project can be pitched as open innovation, pick PulseGuard or CertChain.** They have the
strongest "wow" moment (a patient tile turning red before the threshold; a chain breaking live), are
hard to fake, and their numbers come from recognised standards. KrishiMitra is the best choice if the
judges value local or social impact most.

### Mapping a surprise problem statement to a project

| If the announced problem mentions… | Start from |
|---|---|
| students, learning, exams, e-learning, chatbot | StudyPilot (01) |
| hiring, resumes, careers, skill gaps | ResumeRadar (08), PlaceIQ (06) |
| energy, electricity, solar, carbon, smart campus/building | WattWise (02) |
| waste, garbage, smart city, routing, logistics | WasteWise (09) |
| patients, hospitals, vitals, IoT health monitoring, ICU | PulseGuard (03) |
| blood, donors, emergency response, organ/donor matching | BloodLink (10) |
| certificates, documents, verification, land records, supply-chain provenance | CertChain (04) |
| fraud, phishing, scams, spam, cyber awareness | PhishGuard (07) |
| intrusion detection, logs, SOC, network security | LogSentinel (13) |
| farmers, crops, irrigation, soil, mandi prices | KrishiMitra (05) |
| rural citizens, government schemes, e-governance, accessibility | SchemeSetu (11) |
| analytics dashboards, prediction, education data | PlaceIQ (06) |
| retail, inventory, sales forecasting, MSMEs | StockSense (12) |
| neural networks, computer vision, AI education | NeuroCanvas (14) |
| air pollution, AQI, IoT sensors, smart city environment | AirSense (15) |
| mental health, student wellbeing, counselling | MindEase (16) |
| e-voting, elections, transparency, anonymity | CampusVote (17) |
| drones, remote sensing, precision agriculture, pesticides | AgriSky (18) |
| grievances, e-governance, citizen services, municipal analytics | CivicLens (19) |

Most of the code generalises. For example, CertChain's ledger works for land records or drug
batches, and StockSense's forecaster works for hospital consumables.

## 4. How judges usually score, and how to hit each criterion

| Typical criterion | What earns marks | How our projects show it |
|---|---|---|
| Problem understanding | Specific users, honest numbers, why current tools fail | Slide 2 of every deck; Section 2 of every REPORT.md |
| Innovation | Something they haven't seen ten times today | Explainability panels, offline-first design, trend-based alerts, blind screening |
| Technical depth | Real algorithms, not a CRUD form | All ML and crypto written from scratch, with unit tests and measured metrics |
| Working demo | It runs, live, without excuses | `python app.py`, no installs or internet, "Run demo" buttons |
| Impact & feasibility | Who pays, how it scales, costs | Section 12 of each report; business slide |
| Presentation | Clear story, on time, confident Q&A | 12-slide decks with speaker notes; Q&A prep in Section 14 of each report |

Judges often ask "is this ChatGPT?". The honest answer is the selling point: these are classical,
explainable algorithms (TextRank, BM25, Naive Bayes, Random Forest, logistic regression, Ed25519,
Clarke-Wright, Holt-Winters…) written in plain Python. You can open the file and walk them through the formula.

## 5. 24-hour game plan (team of 4)

| Time | Everyone | Builder 1 (backend/ML) | Builder 2 (frontend) | Presenter / PM |
|---|---|---|---|---|
| H0–H1 | Read problem statements; pick one in 20 min using the mapping table above | Run the closest project, list the gaps | Sketch the screens judges will see | Confirm rules (Section 2); register the GitHub repo |
| H1–H8 | | Adapt the core logic and data to the problem | Adapt the UI, add the "Run demo" path | Write the problem slides; collect 2–3 honest statistics |
| H8–H9 | **Checkpoint:** demo the end-to-end flow to each other | | | |
| H9–H16 | | Measure results (accuracy, latency) for the deck | Polish, responsive, dark mode | Draft the full deck: `node tools/build_decks.js` |
| H16–H18 | Sleep in shifts; never all four at once | | | |
| H18–H21 | | Freeze features; fix bugs only | Screenshots, `--lan` phone test | Rehearse the 3-minute demo twice, timed |
| H21–H23 | Final rehearsal with Q&A drill (Section 14 of the report) | Tag a release on GitHub | Record a 2-minute backup demo video | Submit PPT + GitHub + demo link **early** |
| H23–H24 | Buffer. Do not start new features. | | | |

**If no project fits the announced problem**, don't start from an empty folder. Run
`python tools/new_project.py "Name" --domain <ai|sustain|health|cyber|agri|data> --color "#RRGGBB" --tagline "..."`
in the first hour. It creates a working app in the house style: a stdlib server with a JSON API and
validation, a dashboard with a Run demo button, KPI tiles, a chart, a ranked table with "why" bars, a
try-it form, light/dark and phone layouts, 9 passing tests, and pitch.json/REPORT.md with TODOs.
Builder 1 then replaces the example model in `<pkg>/core.py`, Builder 2 renames the inputs and tabs,
and the presenter fills the TODOs in pitch.json. The deck (`node tools/build_decks.js`), PDF report,
videos and CI all pick the new folder up with no extra wiring. The scaffold is generic boilerplate,
like a framework's starter app, but check it against the rules in Section 2 like everything else.

## 6. Demo-day checklist

- [ ] Python 3.9+ installed on **two** laptops (in case one dies); repo cloned on both
- [ ] `python run_all.py` starts every demo; `python run_all.py --lan` lets judges use their phones
- [ ] Test each demo with **Wi-Fi off**
- [ ] Browser zoom at 110–125% so the projector is readable; close other tabs and notifications
- [ ] Junction box, chargers, an HDMI adapter (USB-C → HDMI), and a phone hotspot as backup
- [ ] Backup demo video downloaded locally (not only a link)
- [ ] `team.json` filled in (team name, members, GitHub, branch), then `cd tools && npm install && node build_decks.js`
- [ ] PPT exported to PDF as a fallback
- [ ] Every member can answer the top 3 questions in the chosen project's Section 14

## 7. Presentation structure (about 5–7 minutes plus demo)

The decks in `decks/` follow this order. Each slide has speaker notes.

1. Title: product, tagline, team
2. The problem: 3–4 bullets plus 2–3 honest statistics
3. Our solution, with a screenshot of the product
4. Key features (6 cards)
5. System architecture plus tech stack
6. Algorithms built from scratch
7. What makes it different
8. How we compare: the status quo and existing tools against ours, criterion by criterion
9. Measured results plus impact
10. Live demo flow, with a screenshot of a second view, then **switch to the browser**
11. Business model and roadmap
12. Thank you, code link, QR code, run command, questions

Rules of thumb: one message per slide, never read the slide aloud, demo before minute 4, and end on impact.

## 8. Submission checklist

- [ ] **PPT:** `decks/<project>.pptx`, customised and saved as PDF too
- [ ] **Report:** `docs/QUANTIX2K26_Report.pdf` (rebuild with `python tools/build_report.py` after editing `team.json`) as a leave-behind for judges
- [ ] **GitHub link:** a public repo with the README screenshot on top and a green CI badge (`.github/workflows/tests.yml` runs every project's tests on Linux and Windows)
- [ ] **Demo link:** an unlisted YouTube or Drive video of the 3-minute demo; the apps are offline by design, so a video is the most reliable "link". `node tools/record_demos.js` produces a ready-made ~45 s captioned MP4 per project as a fallback; record your own voice-over on top if time allows
- [ ] **Dry run:** `python tools/smoke_test.py` and `node tools/qa_sweep.js` both clean on the laptop you will present from, and the closing-slide QR code scans to your repo
- [ ] REPORT.md of the pitched project reviewed: every statistic double-checked and anything unsure marked approx.

## 9. Generic tough questions and crisp answers

| Question | Answer |
|---|---|
| Is your data real? | It's synthetic, generated by code we can show you, with a fixed seed. That lets us measure accuracy honestly. The pipeline accepts real CSVs as-is, and the next step is a pilot with real data. |
| Why didn't you use TensorFlow or scikit-learn? | We wanted it to run anywhere, offline, on a cheap laptop, and every decision to be explainable. With this data size, classical models are accurate enough and far more transparent. |
| How is this different from existing apps? | It works offline, explains its decisions, and is built for Indian and Tamil Nadu users. See slide 7. |
| How will you make money? | See the business slide: free for end users, paid for institutions or B2B. |
| What would you do with 3 more months? | A pilot with one real partner (a college, PHC, FPO or shop), real data, then a field-validated accuracy number. |
| What was the hardest part? | Pick the honest one for your project. Usually it's making the explanation exact, not just plausible. |
