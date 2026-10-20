"""Election service: roster, voter login, blind token issuance, anonymous casting via a mix,
phases (setup -> registration -> voting -> tally), trustee opening and the signed result.

Pure logic (no HTTP). Thread-safe through a single re-entrant lock. Persistence:

  data/keys.json        authority (issuer), board and trustee RSA keys  [DEMO keys]
  data/board.json       the public bulletin board (the only thing an auditor needs)
  data/state.json       private server state: roster with hashed codes, issuance log, mix pool
  data/demo_codes.json  plaintext one-time codes for the DEMO roster only
"""

import contextlib
import csv
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import threading

from . import audit, blind, board, commitment, config, rsa, seal
from .util import (Conflict, Forbidden, NotFound, ValidationError, atomic_write_bytes, atomic_write_json,
                   check_hex, dump_json_bytes, now, parse_hex_int, read_json, sha256_hex)

PHASES = ("setup", "registration", "voting", "tally")
REG_RE = re.compile(r"^[A-Z0-9][A-Z0-9/\-]{2,19}$")
NAME_RE = re.compile(r"^[^\x00-\x1f<>]{1,60}$")
BOARD_FORMAT = "campusvote-board-v1"


def slug(text, maxlen=24):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (s or "x")[:maxlen]


def clean_text(value, name, maxlen=60, required=True):
    v = str(value if value is not None else "").strip()
    if not v:
        if required:
            raise ValidationError("%s is required" % name)
        return ""
    if len(v) > maxlen or not NAME_RE.match(v):
        raise ValidationError("%s must be 1-%d printable characters (no < >)" % (name, maxlen))
    return v


def hash_code(salt_hex, reg_no, code, iters):
    return hashlib.pbkdf2_hmac("sha256", ("%s|%s" % (reg_no, code)).encode(), bytes.fromhex(salt_hex), iters).hex()


class ElectionService(object):
    def __init__(self, data_dir=None, admin_key=None, clock=None, rng=None, keys=None,
                 key_bits=None, otp_iters=None):
        self.dir = data_dir
        self.lock = threading.RLock()
        self.clock = clock or now
        self.rng = rng or secrets.SystemRandom()
        self.admin_key = admin_key or config.ADMIN_KEY
        self.key_bits = key_bits or config.RSA_BITS
        self.otp_iters = otp_iters or config.OTP_PBKDF2_ITERS
        self.sessions = {}
        self.halted = None
        self._defer = 0
        self._dirty = False
        self._disk_digest = None
        self._tokens = set()
        self._last_cp = 0
        self.mix_batch = config.MIX_BATCH
        self.mix_wait = config.MIX_MAX_WAIT_S
        self.keys = keys or self._load_or_create_keys()
        self.state = self._blank_state()
        self.entries = []
        self.demo_codes = {}
        if self.dir:
            self._load()

    # ------------------------------------------------------------------ files
    def _path(self, name):
        return os.path.join(self.dir, name)

    def _load_or_create_keys(self):
        if self.dir:
            raw = read_json(self._path("keys.json"))
            if raw:
                try:
                    return {k: rsa.PrivateKey.from_dict(raw[k]) for k in ("issuer", "board", "trustee")}
                except (KeyError, ValueError, TypeError):
                    pass
        keys = {k: rsa.generate_keypair(self.key_bits) for k in ("issuer", "board", "trustee")}
        if self.dir:
            out = {k: v.private_dict() for k, v in keys.items()}
            out["_note"] = "DEMO KEYS - private keys in a repo are for the demo only. Delete this file to generate fresh keys."
            atomic_write_json(self._path("keys.json"), out)
        return keys

    @staticmethod
    def _blank_state():
        return {"version": 1, "election": None, "phase": "setup", "roster": {}, "issued": {},
                "pool": [], "batches": 0, "demo": False}

    def _load(self):
        st = read_json(self._path("state.json"))
        if st:
            self.state = st
        raw = self._read_board_bytes()
        if raw is not None:
            self._disk_digest = hashlib.sha256(raw).hexdigest()
            try:
                self.entries = json.loads(raw.decode("utf-8"))["entries"]
            except (ValueError, KeyError, TypeError):
                self.entries = []
                self.halted = "board.json is unreadable"
        self.demo_codes = read_json(self._path("demo_codes.json"), {}) or {}
        self._rebuild_index()
        if os.path.exists(self._path("board.backup.json")):
            self.halted = "board.json was tampered with (attack demo) - restore it"
        elif self.entries and audit.audit(self.entries, expected_eid=self.eid)["verdict"] != "VERIFIED":
            # Refuse to extend a board that fails verification (e.g. edited while the server was down).
            self.halted = "board.json failed verification at start-up - appends halted"

    def _rebuild_index(self):
        self._tokens = {e["data"].get("token") for e in self.entries
                        if isinstance(e, dict) and e.get("type") == "ballot" and isinstance(e.get("data"), dict)}
        self._last_cp = max((i for i, e in enumerate(self.entries)
                             if isinstance(e, dict) and e.get("type") == "checkpoint"), default=0)

    def _read_board_bytes(self):
        try:
            with open(self._path("board.json"), "rb") as f:
                return f.read()
        except FileNotFoundError:
            return None

    def _check_disk(self):
        """Detect edits made to board.json behind the service's back (e.g. an insider with a text editor)."""
        if not self.dir or self._disk_digest is None:
            return
        raw = self._read_board_bytes()
        digest = hashlib.sha256(raw).hexdigest() if raw is not None else None
        if digest != self._disk_digest:
            self.halted = "board.json was modified outside CampusVote - appends halted until it is restored"

    def board_bytes(self):
        return dump_json_bytes({"format": BOARD_FORMAT, "entries": self.entries})

    def _save(self):
        if self._defer:
            self._dirty = True
            return
        if not self.dir:
            return
        self._check_disk()
        if self.halted:
            raise Conflict(self.halted)
        data = self.board_bytes()
        atomic_write_bytes(self._path("board.json"), data)
        self._disk_digest = hashlib.sha256(data).hexdigest()
        atomic_write_json(self._path("state.json"), self.state)
        self._dirty = False

    @contextlib.contextmanager
    def batch(self):
        """Group many mutations into one disk write (demo build, simulations)."""
        with self.lock:
            self._defer += 1
            try:
                yield
            finally:
                self._defer -= 1
                if not self._defer and self._dirty:
                    self._save()

    # ------------------------------------------------------------- helpers
    @property
    def manifest(self):
        return self.state.get("election")

    @property
    def eid(self):
        return self.manifest["eid"] if self.manifest else None

    @property
    def phase(self):
        return self.state.get("phase", "setup")

    def voter_ref(self, reg_no):
        return sha256_hex("CV1-voter|%s|%s" % (self.eid, reg_no))[:16]

    def check_admin(self, key):
        if not isinstance(key, str) or not hmac.compare_digest(key.encode(), self.admin_key.encode()):
            raise Forbidden("admin key required (header X-Admin-Key)")

    def _require_election(self):
        if not self.manifest:
            raise Conflict("no election has been created yet")

    def _require_phase(self, *phases):
        self._require_election()
        if self.phase not in phases:
            raise Conflict("not allowed in the %s phase (needs: %s)" % (self.phase, " or ".join(phases)))

    def _guard(self):
        """Refuse to mutate anything once the stored board has been touched behind our back."""
        if not self._defer:
            self._check_disk()
        if self.halted:
            raise Conflict(self.halted)

    def _append(self, etype, data):
        if self.halted:
            raise Conflict(self.halted)
        e = board.make_entry(self.entries, etype, data, self.clock())
        self.entries.append(e)
        if etype == "ballot":
            self._tokens.add(data["token"])
        elif etype == "checkpoint":
            self._last_cp = e["seq"]
        return e

    def _maybe_checkpoint(self, force=False):
        since = len(self.entries) - 1 - self._last_cp
        if (force and self.entries[-1]["type"] != "checkpoint") or since >= config.CHECKPOINT_EVERY:
            self._append("checkpoint", board.make_checkpoint_data(self.entries, self.eid, self.keys["board"],
                                                                  ballots=len(self._tokens)))

    def public_keys(self):
        return {k: v.public_dict() for k, v in self.keys.items()}

    def window_state(self):
        if not self.manifest:
            return "none"
        t = self.clock()
        w = self.manifest["window"]
        if t < w["opens"]:
            return "not-yet"
        if t > w["closes"]:
            return "ended"
        return "open"

    def ballot_entries(self):
        return [e for e in self.entries if e.get("type") == "ballot"]

    def _token_used(self, token):
        if any(p["ballot"]["token"] == token for p in self.state["pool"]):
            return "waiting in the mix"
        if token in self._tokens:
            return "already on the bulletin board"
        return None

    # ------------------------------------------------------------- election setup
    def reset(self):
        with self.lock:
            self.state = self._blank_state()
            self.entries = []
            self._tokens = set()
            self._last_cp = 0
            self.sessions = {}
            self.halted = None
            self._disk_digest = None  # the next save re-establishes the on-disk fingerprint
            self.demo_codes = {}
            if self.dir and os.path.exists(self._path("board.backup.json")):
                os.unlink(self._path("board.backup.json"))

    def create_election(self, title, posts, opens=None, closes=None, eid=None, demo=False, nota=True):
        with self.lock:
            if self.manifest and self.phase not in ("setup", "tally") and not demo:
                raise Conflict("an election is in progress - close and tally it first (or Load demo data)")
            title = clean_text(title, "title", 80)
            if not isinstance(posts, list) or not 1 <= len(posts) <= config.MAX_POSTS:
                raise ValidationError("posts must be a list of 1-%d posts" % config.MAX_POSTS)
            out_posts, used = [], set()
            for p in posts:
                if not isinstance(p, dict):
                    raise ValidationError("each post must be an object {title, candidates}")
                ptitle = clean_text(p.get("title"), "post title", 50)
                pid = slug(ptitle, 20)
                while pid in used:
                    pid += "x"
                used.add(pid)
                cands = p.get("candidates")
                if not isinstance(cands, list) or not 1 <= len(cands) <= config.MAX_CANDIDATES:
                    raise ValidationError("post %r needs 1-%d candidates" % (ptitle, config.MAX_CANDIDATES))
                out_c, cids = [], set()
                for i, c in enumerate(cands):
                    if isinstance(c, str):
                        c = {"name": c}
                    if not isinstance(c, dict):
                        raise ValidationError("candidate must be a name or {name, dept, slogan}")
                    cid = "c%d" % (i + 1)
                    name = clean_text(c.get("name"), "candidate name")
                    if name.upper() == "NOTA":
                        continue
                    out_c.append({"id": cid, "name": name,
                                  "dept": clean_text(c.get("dept"), "dept", 20, required=False),
                                  "slogan": clean_text(c.get("slogan"), "slogan", 70, required=False)})
                    cids.add(cid)
                if not out_c:
                    raise ValidationError("post %r needs at least one real candidate" % ptitle)
                if nota:
                    out_c.append({"id": "NOTA", "name": "None of the above", "dept": "", "slogan": "NOTA"})
                out_posts.append({"id": pid, "title": ptitle, "candidates": out_c})
            t = self.clock()
            opens = int(opens) if opens not in (None, "") else t
            closes = int(closes) if closes not in (None, "") else t + 24 * 3600
            if closes <= opens:
                raise ValidationError("voting window must close after it opens")
            if self.manifest and self.dir and self.entries:
                arch = self._path(os.path.join("archive", "%s-board.json" % self.eid))
                os.makedirs(os.path.dirname(arch), exist_ok=True)
                atomic_write_bytes(arch, self.board_bytes())
            self.reset()
            eid = eid or "%s-%s" % (slug(title, 16).upper(), secrets.token_hex(2).upper())
            self.state["election"] = {"eid": eid, "title": title, "posts": out_posts,
                                      "window": {"opens": opens, "closes": closes}, "created": t}
            self.state["demo"] = bool(demo)
            self._save()
            return self.manifest

    def upload_roster(self, csv_text, code_rng=None):
        with self.lock:
            self._require_phase("setup")
            if not isinstance(csv_text, str) or not csv_text.strip():
                raise ValidationError("csv is required (columns: reg_no,name,dept,year)")
            if len(csv_text) > 400000:
                raise ValidationError("roster CSV too large")
            rows = list(csv.reader(io.StringIO(csv_text.strip())))
            header = [h.strip().lower().replace(" ", "_") for h in rows[0]]
            alias = {"register_no": "reg_no", "regno": "reg_no", "register_number": "reg_no", "roll_no": "reg_no",
                     "department": "dept", "student_name": "name"}
            header = [alias.get(h, h) for h in header]
            if "reg_no" not in header or "name" not in header:
                raise ValidationError("CSV header must include reg_no and name (optional: dept, year)")
            idx = {h: i for i, h in enumerate(header)}
            body = rows[1:]
            if not body:
                raise ValidationError("roster has no students")
            if len(body) > config.MAX_ROSTER:
                raise ValidationError("roster limited to %d students" % config.MAX_ROSTER)
            rng = code_rng or self.rng
            roster, slips = {}, []
            for ln, row in enumerate(body, start=2):
                if not any(c.strip() for c in row):
                    continue
                get = lambda k: row[idx[k]].strip() if k in idx and idx[k] < len(row) else ""  # noqa: E731
                reg = get("reg_no").upper()
                if not REG_RE.match(reg):
                    raise ValidationError("line %d: bad register number %r" % (ln, reg[:24]))
                if reg in roster:
                    raise ValidationError("line %d: duplicate register number %s" % (ln, reg))
                name = clean_text(get("name"), "line %d name" % ln)
                dept = clean_text(get("dept") or "-", "line %d dept" % ln, 20).upper()
                year = get("year")
                year = int(year) if year.isdigit() and 1 <= int(year) <= 6 else 0
                code = "%0*d" % (config.OTP_DIGITS, rng.randrange(10 ** config.OTP_DIGITS))
                salt = "%032x" % rng.getrandbits(128)
                roster[reg] = {"name": name, "dept": dept, "year": year, "salt": salt,
                               "code_hash": hash_code(salt, reg, code, self.otp_iters), "failed": 0}
                slips.append({"reg_no": reg, "name": name, "dept": dept, "code": code})
            self.state["roster"] = roster
            self.state["issued"] = {}
            self._save()
            return {"count": len(roster), "slips": slips,
                    "note": "One-time codes are shown ONCE - only salted PBKDF2 hashes are stored."}

    def set_demo_codes(self, codes):
        self.demo_codes = {"eid": self.eid, "codes": codes}
        if self.dir:
            atomic_write_json(self._path("demo_codes.json"), self.demo_codes)

    def open_registration(self):
        with self.lock:
            self._guard()
            self._require_phase("setup")
            if not self.state["roster"]:
                raise Conflict("upload a roster first")
            refs = sorted(self.voter_ref(r) for r in self.state["roster"])
            self._append("genesis", {
                "protocol": config.PROTOCOL,
                "election": self.manifest,
                "keys": self.public_keys(),
                "roster": {"eligible": len(refs), "roster_hash": sha256_hex("\n".join(refs))},
                "params": {"checkpoint_every": config.CHECKPOINT_EVERY, "mix_batch": config.MIX_BATCH,
                           "mix_max_wait_s": config.MIX_MAX_WAIT_S},
            })
            self._maybe_checkpoint(force=True)
            self.state["phase"] = "registration"
            self._save()
            return {"phase": self.phase}

    def open_voting(self):
        with self.lock:
            self._guard()
            if self.phase == "setup":
                self.open_registration()
            self._require_phase("registration")
            self._append("phase", {"phase": "voting"})
            self._maybe_checkpoint(force=True)
            self.state["phase"] = "voting"
            self._save()
            return {"phase": self.phase}

    def close_and_tally(self):
        """Close voting, let the trustee open every sealed ballot, post the signed result."""
        with self.lock:
            self._guard()
            self._require_phase("voting")
            with self.batch():
                self.flush_pool(force=True)
                ballots = self.ballot_entries()
                self._append("phase", {"phase": "closed", "tokens_issued": len(self.state["issued"]),
                                       "ballots": len(ballots)})
                self._maybe_checkpoint(force=True)
                trustee = self.keys["trustee"]
                counts = audit.empty_counts(self.manifest)
                counted = spoiled = 0
                for b in ballots:
                    d = b["data"]
                    out = {"token": d["token"], "ballot_seq": b["seq"]}
                    try:
                        pt = json.loads(seal.open_sealed(trustee, d["sealed"], d["token"]).decode("utf-8"))
                        choices, nonce = pt.get("choices"), pt.get("nonce")
                        out.update({"choices": choices, "nonce": nonce})
                        if not commitment.verify_opening(self.eid, d["token"], choices, nonce, d["commitment"]):
                            out.update({"status": "invalid", "reason": "opening does not match the commitment"})
                        elif not audit.valid_choices(self.manifest, choices):
                            out.update({"status": "invalid", "reason": "names an unknown candidate"})
                        else:
                            out["status"] = "ok"
                    except (seal.SealError, ValueError, UnicodeDecodeError, AttributeError) as exc:
                        out.update({"status": "invalid", "reason": "sealed opening unreadable: %s" % exc})
                    if out["status"] == "ok":
                        counted += 1
                        for post, cand in out["choices"].items():
                            counts[post][cand] += 1
                    else:
                        spoiled += 1
                    self._append("opening", out)
                    self._maybe_checkpoint()
                result = {"counts": counts, "counted": counted, "spoiled": spoiled,
                          "tokens_issued": len(self.state["issued"]), "eligible": len(self.state["roster"]),
                          "winners": audit.winners_of(counts), "head": self.entries[-1]["hash"]}
                result["sig"] = "%x" % rsa.sign_message(self.keys["board"], board.result_message(self.eid, result))
                self._append("result", result)
                self._maybe_checkpoint(force=True)
                self.state["phase"] = "tally"
                self._dirty = True
            return self.results()

    def set_phase(self, target):
        with self.lock:
            if target == "registration":
                return self.open_registration()
            if target == "voting":
                return self.open_voting()
            if target == "tally":
                return {"phase": "tally", "report": self.close_and_tally()["report"]["verdict"]}
            raise ValidationError("phase must be registration, voting or tally")

    # ------------------------------------------------------------- voters
    def login(self, reg_no, code):
        with self.lock:
            self._require_phase("registration", "voting")
            if self.window_state() == "ended":
                raise Conflict("the voting window has closed")
            self._guard()
            reg, student = self._authenticate(reg_no, code)
            t = self.clock()
            self.sessions = {k: v for k, v in self.sessions.items() if v["exp"] > t}
            sid = secrets.token_urlsafe(18)
            self.sessions[sid] = {"reg_no": reg, "exp": t + config.SESSION_TTL_S}
            self._save()
            return {"session": sid, "voter": {"name": student["name"], "dept": student["dept"],
                                              "year": student["year"]},
                    "voter_ref": self.voter_ref(reg), "already_issued": reg in self.state["issued"]}

    def _authenticate(self, reg_no, code):
        """Check a one-time code with lockout. Same error for unknown students and wrong codes."""
        reg = str(reg_no or "").strip().upper()
        code = str(code or "").strip()
        student = self.state["roster"].get(reg)
        if not student or not REG_RE.match(reg):
            raise Forbidden("unknown register number or wrong code")
        if student.get("failed", 0) >= config.OTP_MAX_ATTEMPTS:
            raise Forbidden("account locked after %d wrong codes - see the election officer" % config.OTP_MAX_ATTEMPTS)
        good = len(code) == config.OTP_DIGITS and code.isdigit() and hmac.compare_digest(
            hash_code(student["salt"], reg, code, self.otp_iters), student["code_hash"])
        if not good:
            student["failed"] = student.get("failed", 0) + 1
            self._save()
            left = config.OTP_MAX_ATTEMPTS - student["failed"]
            raise Forbidden("wrong one-time code (%d attempts left)" % left if left > 0 else
                            "wrong code - account now LOCKED after %d attempts" % config.OTP_MAX_ATTEMPTS)
        student["failed"] = 0
        return reg, student

    def issue(self, session, blinded_hex):
        with self.lock:
            s = self.sessions.get(str(session or ""))
            if not s or s["exp"] < self.clock():
                raise Forbidden("session expired - sign in again")
            out = self._issue_for(s["reg_no"], blinded_hex)
            self.sessions.pop(session, None)  # one token request per login
            return out

    def _issue_for(self, reg, blinded_hex, check_phase=True):
        self._guard()
        if check_phase:
            self._require_phase("registration", "voting")
        issuer = self.keys["issuer"]
        blinded = parse_hex_int(blinded_hex, issuer.size, "blinded")
        if not 1 < blinded < issuer.n - 1:
            raise ValidationError("blinded value out of range")
        prior = self.state["issued"].get(reg)
        if prior:
            if prior["blinded"] == "%x" % blinded:
                # Same blinded value re-sent (e.g. network retry): same signature, no new token.
                return {"blind_sig": prior["blind_sig"], "issuance_seq": prior["seq"], "resent": True}
            raise Conflict("%s already received a ballot token - one token per eligible voter "
                           "(double voting blocked at issuance)" % reg)
        blind_sig = blind.sign_blinded(issuer, blinded)
        e = self._append("issuance", {"voter_ref": self.voter_ref(reg), "blinded": "%x" % blinded,
                                      "blind_sig": "%x" % blind_sig})
        self.state["issued"][reg] = {"seq": e["seq"], "blinded": "%x" % blinded, "blind_sig": "%x" % blind_sig,
                                     "time": e["time"]}
        self._maybe_checkpoint()
        self._save()
        return {"blind_sig": "%x" % blind_sig, "issuance_seq": e["seq"], "resent": False}

    def cast(self, ballot):
        """Anonymous channel entry point: no login, no session - only the token speaks."""
        with self.lock:
            self._guard()
            self.flush_if_due()
            self._require_phase("voting")
            ws = self.window_state()
            if ws != "open":
                raise Conflict("voting window is %s" % ("not open yet" if ws == "not-yet" else "over"))
            clean = self.validate_ballot(ballot)
            token, com = clean["token"], clean["commitment"]
            self.state["pool"].append({"ballot": clean, "arrived": self.clock()})
            pool_size = len(self.state["pool"])
            self._save()
            self.flush_if_due()
            posted = self._token_used(token) == "already on the bulletin board"
            return {"accepted": True, "token_hash": sha256_hex(token), "commitment": com,
                    "status": "posted" if posted else "queued", "pool_size": 0 if posted else pool_size,
                    "message": "Ballot accepted into the anonymity mix. It is posted to the board in a shuffled "
                               "batch of %d (or after %ds)." % (config.MIX_BATCH, config.MIX_MAX_WAIT_S)}

    def validate_ballot(self, ballot):
        """Every check a ballot must pass (shape, authority signature, unused token). No side effects."""
        with self.lock:
            self._require_election()
            if not isinstance(ballot, dict):
                raise ValidationError("ballot must be an object")
            issuer = self.keys["issuer"]
            token = check_hex(ballot.get("token"), 64, "token")
            sig = parse_hex_int(ballot.get("sig"), issuer.size, "sig")
            com = check_hex(ballot.get("commitment"), 64, "commitment")
            sealed = seal.validate_sealed(ballot.get("sealed"), self.keys["trustee"])
            if not blind.verify_token(issuer, self.eid, token, sig):
                raise ValidationError("REJECTED: signature does not verify - this token was not issued by the "
                                      "election authority for election %s" % self.eid)
            used = self._token_used(token)
            if used:
                raise Conflict("REJECTED: duplicate token (%s) - each token votes once; "
                               "double vote / replay blocked" % used)
            return {"token": token, "sig": "%x" % sig, "commitment": com, "sealed": sealed}

    def flush_if_due(self):
        with self.lock:
            pool = self.state["pool"]
            if pool and not self._defer:
                self._check_disk()
            if not pool or self.halted:
                return 0
            oldest = min(p["arrived"] for p in pool)
            if len(pool) >= self.mix_batch or self.clock() - oldest >= self.mix_wait:
                return self.flush_pool()
            return 0

    def flush_pool(self, force=False):
        """Post pooled ballots in random order with one shared batch timestamp."""
        with self.lock:
            pool = list(self.state["pool"])
            if not pool:
                return 0
            self.rng.shuffle(pool)
            self.state["batches"] = self.state.get("batches", 0) + 1
            for p in pool:
                d = dict(p["ballot"])
                d["batch"] = self.state["batches"]
                self._append("ballot", d)
                self._maybe_checkpoint()
            self._maybe_checkpoint(force=True)
            self.state["pool"] = []
            self._save()
            return len(pool)

    # ------------------------------------------------------------- read side
    def election_info(self):
        with self.lock:
            m = self.manifest
            return {"election": m, "phase": self.phase, "window_state": self.window_state(),
                    "keys": self.public_keys(), "demo": bool(self.state.get("demo")),
                    "params": {"mix_batch": config.MIX_BATCH, "mix_max_wait_s": config.MIX_MAX_WAIT_S,
                               "checkpoint_every": config.CHECKPOINT_EVERY, "otp_digits": config.OTP_DIGITS}}

    def stats(self):
        with self.lock:
            try:
                self.flush_if_due()
            except Conflict:
                pass
            roster = self.state["roster"]
            issued = self.state["issued"]
            ballots = self.ballot_entries()
            depts = {}
            for reg, s in roster.items():
                d = depts.setdefault(s["dept"], {"dept": s["dept"], "eligible": 0, "issued": 0})
                d["eligible"] += 1
                if reg in issued:
                    d["issued"] += 1
            timeline, cum = [], 0
            for b in ballots:
                cum += 1
                if timeline and timeline[-1]["t"] == b["time"]:
                    timeline[-1]["n"] = cum
                else:
                    timeline.append({"t": b["time"], "n": cum})
            iss_times = sorted(v["time"] for v in issued.values())
            cps = [e for e in self.entries if e["type"] == "checkpoint"]
            n_el = len(roster) or 1
            return {
                "phase": self.phase, "window_state": self.window_state(),
                "election": {"eid": self.eid, "title": self.manifest["title"] if self.manifest else None,
                             "window": self.manifest["window"] if self.manifest else None,
                             "posts": len(self.manifest["posts"]) if self.manifest else 0},
                "eligible": len(roster), "tokens_issued": len(issued), "ballots": len(ballots),
                "pool": len(self.state["pool"]),
                "token_pct": round(100.0 * len(issued) / n_el, 1),
                "turnout_pct": round(100.0 * len(ballots) / n_el, 1),
                "locked": sum(1 for s in roster.values() if s.get("failed", 0) >= config.OTP_MAX_ATTEMPTS),
                "by_dept": sorted(depts.values(), key=lambda d: -d["eligible"]),
                "timeline": timeline,
                "issuance_timeline": [{"t": t, "n": i + 1} for i, t in enumerate(iss_times)],
                "board": {"entries": len(self.entries),
                          "head": self.entries[-1]["hash"] if self.entries else board.GENESIS_PREV,
                          "checkpoints": len(cps),
                          "last_checkpoint": ({"seq": cps[-1]["seq"], "upto": cps[-1]["data"]["upto"],
                                               "time": cps[-1]["time"]} if cps else None),
                          "batches": self.state.get("batches", 0)},
                "halted": self.halted, "demo": bool(self.state.get("demo")), "server_time": self.clock(),
            }

    def stored_board_bytes(self):
        if self.dir:
            raw = self._read_board_bytes()
            if raw is not None:
                return raw
        return self.board_bytes()

    def disk_entries(self):
        """The board as stored on disk (what an auditor downloads), falling back to memory."""
        if self.dir:
            raw = self._read_board_bytes()
            if raw is not None:
                try:
                    return json.loads(raw.decode("utf-8")).get("entries", [])
                except (ValueError, AttributeError):
                    return []
        return self.entries

    def verify(self):
        with self.lock:
            self._check_disk()
            rep = audit.audit(self.disk_entries(), expected_eid=self.eid)
            rep["halted"] = self.halted
            return rep

    def results(self):
        with self.lock:
            self._require_election()
            if self.phase != "tally":
                raise Conflict("results are sealed: %d ballots are on the board as commitments and cannot be "
                               "read until voting closes" % len(self.ballot_entries()))
            rep = self.verify()
            return {"manifest": self.manifest, "report": rep, "tally": rep.get("tally"),
                    "eligible": len(self.state["roster"]), "tokens_issued": len(self.state["issued"])}

    def receipt(self, token_hash):
        with self.lock:
            th = str(token_hash or "").strip().lower()
            if not re.match(r"^[0-9a-f]{16,64}$", th):
                raise ValidationError("receipt code must be 16-64 hex characters")
            for p in self.state["pool"]:
                if sha256_hex(p["ballot"]["token"]).startswith(th):
                    return {"status": "queued", "pool_size": len(self.state["pool"])}
            for e in self.ballot_entries():
                if sha256_hex(e["data"]["token"]).startswith(th):
                    cp = next((c for c in self.entries if c["type"] == "checkpoint" and c["data"]["upto"] >= e["seq"]),
                              None)
                    op = next((o for o in self.entries if o["type"] == "opening" and
                               o["data"]["token"] == e["data"]["token"]), None)
                    return {"status": "counted" if op and op["data"]["status"] == "ok" else
                            ("spoiled" if op else "posted"),
                            "seq": e["seq"], "entry_hash": e["hash"], "commitment": e["data"]["commitment"],
                            "time": e["time"], "batch": e["data"].get("batch"),
                            "checkpoint": cp["seq"] if cp else None,
                            "opening": op["data"] if op else None}
            raise NotFound("no ballot with this receipt code on the board")

    def linkability(self, issuance_seq=None, limit=400):
        """The authority's best linking attempt, using only public data. It always fails."""
        with self.lock:
            issuer = self.keys["issuer"]
            iss = [e for e in self.entries if e["type"] == "issuance"]
            if not iss:
                raise Conflict("no tokens issued yet")
            if issuance_seq is None:
                target = iss[len(iss) // 2]
            else:
                target = next((e for e in iss if e["seq"] == issuance_seq), None)
                if not target:
                    raise NotFound("no issuance entry #%s" % issuance_seq)
            ballots = self.ballot_entries()[:limit]
            m_b = int(target["data"]["blinded"], 16)
            s_b = int(target["data"]["blind_sig"], 16)
            consistent, sample = 0, []
            for b in ballots:
                r, ok = blind.linking_factor(issuer, m_b, s_b, self.eid, b["data"]["token"], int(b["data"]["sig"], 16))
                consistent += ok
                if len(sample) < 4:
                    sample.append({"ballot_seq": b["seq"], "r": "%x" % r, "consistent": ok})
            n = len(ballots)
            return {"issuance_seq": target["seq"], "voter_ref": target["data"]["voter_ref"], "ballots": n,
                    "consistent": consistent, "sample": sample,
                    "guess_probability": ("1/%d" % n) if n else "n/a",
                    "explanation": "For every ballot (t, s) the factor r = s' * s^-1 mod n satisfies "
                                   "FDH(t) * r^e = m' - so each of the %d ballots is an equally valid match for "
                                   "this voter's issuance record. The authority learns nothing." % n}

    # ------------------------------------------------------------- demo helpers
    def demo_voter(self):
        with self.lock:
            codes = (self.demo_codes or {}).get("codes") if (self.demo_codes or {}).get("eid") == self.eid else None
            if not codes:
                raise NotFound("demo credentials only exist for the demo election")
            free = [r for r in sorted(codes) if r not in self.state["issued"]
                    and self.state["roster"].get(r, {}).get("failed", 0) == 0]
            if not free:
                raise NotFound("every demo voter already has a token - Load demo data to start over")
            reg = secrets.choice(free)
            s = self.state["roster"][reg]
            return {"reg_no": reg, "code": codes[reg], "name": s["name"], "dept": s["dept"], "remaining": len(free)}

    def unlock(self, reg_no):
        with self.lock:
            s = self.state["roster"].get(str(reg_no or "").strip().upper())
            if not s:
                raise NotFound("unknown register number")
            s["failed"] = 0
            self._save()
            return {"unlocked": True}

    def simulate(self, count, chooser=None, rng=None):
        """Run the full voter protocol for `count` students who have no token yet."""
        from .client import VoterDevice
        from .demo import choose_for
        with self.lock, self.batch():
            self._require_phase("registration", "voting")
            count = int(count)
            if not 1 <= count <= config.MAX_SIMULATE:
                raise ValidationError("count must be 1-%d" % config.MAX_SIMULATE)
            rng = rng or self.rng
            free = sorted(r for r, s in self.state["roster"].items()
                          if r not in self.state["issued"] and s.get("failed", 0) < config.OTP_MAX_ATTEMPTS)
            rng.shuffle(free)
            chooser = chooser or choose_for
            cast = 0
            for reg in free[:count]:
                dev = VoterDevice(self.eid, self.keys["issuer"].public(), self.keys["trustee"].public(), rng)
                res = self._issue_for(reg, "%x" % dev.prepare_token())
                dev.finish_token(int(res["blind_sig"], 16))
                if self.phase == "voting":
                    self.cast(dev.build_ballot(chooser(self.state["roster"][reg], self.manifest, rng)))
                    cast += 1
            return {"tokens": min(count, len(free)), "cast": cast, "pool": len(self.state["pool"])}

    # ------------------------------------------------------------- tamper demo
    def tamper(self, mode):
        """Play an insider who edits data/board.json directly (bypassing this service)."""
        with self.lock:
            if not self.dir:
                raise Conflict("tamper demo needs on-disk storage")
            if os.path.exists(self._path("board.backup.json")):
                self.restore()
            raw = self._read_board_bytes()
            doc = json.loads(raw.decode("utf-8"))
            entries = doc["entries"]
            openings = [e for e in entries if e["type"] == "opening" and e["data"].get("status") == "ok"]
            ballots = [e for e in entries if e["type"] == "ballot"]
            if not ballots:
                raise Conflict("no ballots on the board yet")
            if mode not in ("edit", "rehash", "delete"):
                raise ValidationError("mode must be edit, rehash or delete")
            if mode == "delete":
                target = ballots[len(ballots) // 2]
                k = target["seq"]
                del entries[k]
                what = "deleted ballot #%d (token %s...) to silently drop a vote" % (k, target["data"]["token"][:10])
            else:
                if openings:
                    target = openings[len(openings) // 2]
                    post = self.manifest["posts"][0]
                    old = target["data"]["choices"][post["id"]]
                    new = next(c["id"] for c in post["candidates"] if c["id"] not in (old, "NOTA"))
                    target["data"]["choices"][post["id"]] = new
                    names = {c["id"]: c["name"] for c in post["candidates"]}
                    what = "flipped the %s vote in opening #%d from %s to %s" % (
                        post["title"], target["seq"], names.get(old, old), names[new])
                else:
                    target = ballots[len(ballots) // 2]
                    target["data"]["commitment"] = sha256_hex("forged-" + target["data"]["commitment"])
                    what = "replaced the commitment of ballot #%d with a forged one" % target["seq"]
                k = target["seq"]
                if mode == "rehash":
                    prev = entries[k - 1]["hash"]
                    for e in entries[k:]:
                        e["prev"] = prev
                        if e["type"] == "checkpoint" and e["data"]["upto"] >= k:
                            e["data"]["head"] = entries[e["data"]["upto"]]["hash"]
                        e["hash"] = board.entry_hash(e)
                        prev = e["hash"]
                    what += ", then recomputed every later hash so the chain looks consistent"
            atomic_write_bytes(self._path("board.backup.json"), raw)
            atomic_write_bytes(self._path("board.json"), dump_json_bytes(doc))
            self._check_disk()
            rep = audit.audit(entries, expected_eid=self.eid)
            return {"mode": mode, "target_seq": k, "what": what, "report": rep, "halted": self.halted}

    def restore(self):
        with self.lock:
            bak = self._path("board.backup.json") if self.dir else None
            if not bak or not os.path.exists(bak):
                return {"restored": False, "message": "nothing to restore"}
            with open(bak, "rb") as f:
                raw = f.read()
            atomic_write_bytes(self._path("board.json"), raw)
            os.unlink(bak)
            self.entries = json.loads(raw.decode("utf-8"))["entries"]
            self._rebuild_index()
            self._disk_digest = hashlib.sha256(raw).hexdigest()
            self.halted = None
            return {"restored": True, "message": "board.json restored from the pre-attack backup",
                    "verdict": audit.audit(self.entries, expected_eid=self.eid)["verdict"]}
