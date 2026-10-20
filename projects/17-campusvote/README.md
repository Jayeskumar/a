# CampusVote

**Verifiable, anonymous e-voting for student elections.** Domain: Cybersecurity & Blockchain Technology.

College and club elections run on paper (slow counts, disputed recounts) or Google Forms (the admin can see who voted
what, edit rows, and anyone with the link can vote twice). CampusVote lets students vote from their phones over campus
Wi-Fi. Every vote stays secret and every result can be checked. All of the crypto is written from scratch on Python big
integers plus `hashlib`, `hmac` and `secrets`:

- **Chaum RSA blind signatures:** the authority signs a ballot token it never sees. It issues one per register number,
  and the token can never be linked back to the voter.
- **Hash commitments plus sealed openings:** choices stay hidden until voting closes. After that, the trustee opens
  every ballot and anyone can check each opening against its commitment.
- **Public bulletin board:** a hash-chained, append-only log with RSA-signed checkpoints. Download it, verify it and
  recount it, on the server, in the browser or with `verify.py`.
- **Receipts:** each voter checks on their own phone that their ballot was counted as cast.
- **Attack lab:** 12 live attacks (double voting, forgery, replay, tampering, stuffing, de-anonymisation), each one
  rejected or detected, with the reason.

![screenshot](docs/screenshot.png)

## Quick start

```bash
python app.py                    # http://127.0.0.1:8017/
python app.py --host 0.0.0.0     # phones on the same Wi-Fi vote at http://<laptop-ip>:8017/#vote
python -m unittest discover -s tests
python verify.py                 # independent audit + recount of data/board.json
python bench.py                  # keygen / sign / verify / tally timings -> docs/bench.json
python -m campusvote.demo        # regenerate the deterministic demo election in data/
```

You need Python 3.9 or newer and nothing else. On first run the demo election is built: 200 synthetic students, 3 posts,
168 tokens issued and 152 ballots, with voting still open. The demo admin key is `ksrce-admin-2026` and the UI fills it in.
Set `CAMPUSVOTE_ADMIN_KEY` to change it.

**Live demo:** on a phone, open **Vote**, then tap **Use a demo voter**, **Get token**, pick candidates, **Cast**, and you
get a receipt. Then try the **Attack lab**, press **Close voting & tally**, check **Results**, and re-check the receipt
(it now shows *counted as cast*).

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | liveness + phase |
| GET | `/api/info` | product info, phone vote URL, demo admin key (demo only) |
| GET | `/api/election` | manifest (posts, candidates, window), phase, public keys |
| GET | `/api/stats` | live turnout dashboard: tokens, ballots, mix pool, by department, timeline |
| GET | `/api/board` | the full public bulletin board as stored on disk (`?download=1` to save) |
| GET | `/api/board/verify` | 10-step audit of the stored board |
| GET | `/api/results` | tally + audit (only in the tally phase; 409 while sealed) |
| GET | `/api/receipt/<code>` | ballot status by receipt code (the UI checks locally instead, for privacy) |
| GET | `/api/link?seq=` | the authority's linking attempt for one issuance record (always 1/N) |
| GET | `/api/security` | threat model + honest limits |
| GET | `/api/demo/voter` | an unused demo credential (demo election only) |
| GET | `/api/sample/roster.csv` | sample roster CSV |
| POST | `/api/login` | `{reg_no, code}` → single-use session |
| POST | `/api/issue` | `{session, blinded}` → blind signature (one per voter; same blinded value = same answer) |
| POST | `/api/ballot` | `{token, sig, commitment, sealed}` anonymous cast, no login (202, queued in the mix) |
| POST | `/api/admin/election` | `{title, posts, opens, closes}` create an election (setup phase) |
| POST | `/api/admin/roster` | `{csv}` upload a roster and get one-time code slips (shown once) |
| POST | `/api/admin/phase` | `{phase: registration, voting or tally}` |
| POST | `/api/admin/simulate` | `{count}` run the full voter protocol for N students |
| POST | `/api/admin/flush` | post the mix pool now |
| POST | `/api/admin/unlock` | `{reg_no}` clear an OTP lockout |
| POST | `/api/demo/reset` | rebuild the deterministic demo election |
| POST | `/api/attack/<name>` | run an attack: `double_token`, `double_cast`, `replay`, `forge_random`, `forge_multiply`, `cross_election`, `otp_bruteforce`, `link_attempt`, `stuffing`, `tamper_edit`, `tamper_rehash`, `tamper_delete` |
| POST | `/api/attack/restore` | restore `board.json` after a tamper demo |

Admin, demo and attack endpoints need the `X-Admin-Key` header.

## Layout

- `campusvote/`: pure logic.
  - `numtheory` (Miller–Rabin, extended Euclid)
  - `rsa` (keygen, CRT, FDH)
  - `blind` (Chaum)
  - `commitment`
  - `seal` (RSA-KEM)
  - `board` (hash chain)
  - `audit` (universal verification)
  - `election` (service)
  - `client` (voter device)
  - `attacks`
  - `demo`
  - `security`
  - `config`
- `static/`: the single-page UI. `crypto.js` mirrors the Python crypto byte for byte, including a full board audit
  in the browser.
- `data/`
  - `keys.json`: **DEMO** keys, deterministic, never for real use
  - `board.json`: the public board
  - `state.json`: private server state, with OTP codes stored as salted PBKDF2 hashes
  - `demo_codes.json`
  - `sample_roster.csv`
- `tests/`: 65 unit and integration tests.
- `verify.py`: offline auditor.
- `bench.py`: measurements.

See `REPORT.md` for the full hackathon report: threat model, measurements, demo script and Q&A.
