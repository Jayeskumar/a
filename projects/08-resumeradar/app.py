#!/usr/bin/env python3
"""ResumeRadar - fair, explainable AI resume screening and career coaching.

    python app.py [--host 127.0.0.1] [--port 8008]

Pure Python standard library: no pip install, no internet, no API keys.
"""
import argparse
import json
import mimetypes
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from resumeradar import __version__, blind, config, interview, ontology, screening
from resumeradar.ats import check as ats_check
from resumeradar.demo import get_demo, write_demo
from resumeradar.extract import parse_resume, public_profile
from resumeradar.gaps import learning_path
from resumeradar.jd import parse_jd, public_jd

ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(ROOT, "static")
DATA = os.path.join(ROOT, "data")
DEFAULT_PORT = 8008

_EVAL = {}
_EVAL_LOCK = threading.Lock()


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


# --------------------------------------------------------------------- validation
def _text(body, key, required=True, min_len=20):
    val = body.get(key)
    if val is None or (isinstance(val, str) and not val.strip()):
        if required:
            raise ApiError(400, "'%s' is required" % key)
        return None
    if not isinstance(val, str):
        raise ApiError(400, "'%s' must be a string" % key)
    if len(val) > config.MAX_TEXT_CHARS:
        raise ApiError(413, "'%s' is too long (max %d characters)" % (key, config.MAX_TEXT_CHARS))
    if len(val.strip()) < min_len:
        raise ApiError(400, "'%s' is too short to analyse (min %d characters)" % (key, min_len))
    return val


def _bool(body, key, default=True):
    val = body.get(key, default)
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    if isinstance(val, str):
        return val.strip().lower() in ("1", "true", "yes", "on")
    raise ApiError(400, "'%s' must be a boolean" % key)


def _resumes(body):
    items = body.get("resumes")
    if not isinstance(items, list) or not items:
        raise ApiError(400, "'resumes' must be a non-empty list of {id, name, text}")
    if len(items) > config.MAX_RESUMES:
        raise ApiError(413, "too many resumes (max %d)" % config.MAX_RESUMES)
    out = []
    seen = set()
    for i, it in enumerate(items):
        if isinstance(it, str):
            it = {"text": it}
        if not isinstance(it, dict):
            raise ApiError(400, "resumes[%d] must be an object" % i)
        text = _text(it, "text", min_len=20)
        rid = str(it.get("id") or "C%03d" % (i + 1))[:40]
        if rid in seen:
            rid = "%s-%d" % (rid, i + 1)
        seen.add(rid)
        name = it.get("name")
        out.append({"id": rid, "name": str(name)[:80] if name else rid, "text": text})
    return out


def _skill_names(body, key):
    vals = body.get(key) or []
    if not isinstance(vals, list):
        raise ApiError(400, "'%s' must be a list of skill names" % key)
    ids = []
    unknown = []
    lookup = {s.name.lower(): s.id for s in ontology.SKILLS.values()}
    lookup.update({s.id: s.id for s in ontology.SKILLS.values()})
    for v in vals:
        sid = lookup.get(str(v).strip().lower())
        if sid:
            ids.append(sid)
        else:
            unknown.append(str(v))
    return ids, unknown


# --------------------------------------------------------------------- handlers
def h_health(_q, _b):
    return {"ok": True, "name": "ResumeRadar", "version": __version__, "offline": True,
            "skills": len(ontology.SKILLS), "time": int(time.time())}


def h_demo(_q, _b):
    d = get_demo()
    return {"jds": d["jds"],
            "resumes": [{"id": r["id"], "name": r["name"], "archetype": r["archetype"], "text": r["text"]}
                        for r in d["resumes"]],
            "note": d["note"]}


def h_ontology(q, _b):
    term = (q.get("q", [""])[0] or "").strip().lower()
    skills = [s.to_dict() for s in ontology.SKILLS.values()]
    if term:
        skills = [s for s in skills if term in s["name"].lower() or any(term in a.lower() for a in s["aliases"])]
    return {"stats": ontology.stats(), "skills": skills[:400], "questions": interview.bank_stats()}


def h_config(_q, _b):
    return {"weights": dict(config.WEIGHTS), "labels": config.COMPONENT_LABELS,
            "implied_credit_direct": config.IMPLIED_CREDIT_DIRECT,
            "implied_credit_indirect": config.IMPLIED_CREDIT_INDIRECT,
            "related_credit": config.RELATED_CREDIT, "title_skill_weight": config.TITLE_SKILL_WEIGHT,
            "strong_cue_weight": config.STRONG_CUE_WEIGHT, "semantic_cos_full": config.SEMANTIC_COS_FULL,
            "internship_weight": config.INTERNSHIP_WEIGHT, "shortlist_at": config.SHORTLIST_AT,
            "review_at": config.REVIEW_AT, "hours_per_week": config.HOURS_PER_WEEK,
            "as_of": "%04d-%02d" % (config.AS_OF_YEAR, config.AS_OF_MONTH)}


def h_parse_resume(_q, b):
    text = _text(b, "text")
    use_blind = _bool(b, "blind", False)
    masked = blind.mask(text) if use_blind else None
    prof = parse_resume(masked["text"] if masked else text)
    return {"profile": public_profile(prof), "blind": use_blind}


def h_parse_jd(_q, b):
    text = _text(b, "text")
    return public_jd(parse_jd(text))


def h_mask(_q, b):
    text = _text(b, "text", min_len=1)
    return blind.mask(text)


def h_match(_q, b):
    resume = _text(b, "resume")
    jd = _text(b, "jd")
    return screening.analyze(resume, jd, blind_mode=_bool(b, "blind", True))


def h_screen(_q, b):
    jd = _text(b, "jd")
    resumes = _resumes(b)
    return screening.screen(jd, resumes, blind_mode=_bool(b, "blind", True), details=_bool(b, "details", True))


def h_bias(_q, b):
    jd = _text(b, "jd")
    resumes = _resumes(b)
    if len(resumes) > 200:
        raise ApiError(413, "bias check supports up to 200 resumes per request")
    return screening.bias_check(jd, resumes)


def h_ats(_q, b):
    text = _text(b, "text")
    jd_text = _text(b, "jd", required=False)
    prof = parse_resume(text)
    if jd_text:
        res = screening.analyze(text, jd_text, blind_mode=False)
        return res["ats"]
    return ats_check(prof)


def h_learning_path(_q, b):
    targets, unknown_t = _skill_names(b, "targets")
    known, unknown_k = _skill_names(b, "known")
    if not targets:
        raise ApiError(400, "'targets' must list at least one known skill name (see /api/ontology)")
    out = learning_path(targets, set(known), must_ids=targets)
    out["unknown"] = unknown_t + unknown_k
    return out


def h_interview(_q, b):
    resume = _text(b, "resume")
    jd = _text(b, "jd")
    res = screening.analyze(resume, jd, blind_mode=_bool(b, "blind", True))
    return {"questions": res["interview"], "score": res["score"]}


def h_eval(q, _b):
    fresh = q.get("refresh", ["0"])[0] == "1"
    with _EVAL_LOCK:
        if fresh or "r" not in _EVAL:
            from resumeradar import evaluate
            res = evaluate.run(include_latency=True)
            res["extraction"]["errors"] = res["extraction"]["errors"][:6]
            _EVAL["r"] = res
        return _EVAL["r"]


ROUTES = {
    ("GET", "/api/health"): h_health,
    ("GET", "/api/demo"): h_demo,
    ("GET", "/api/ontology"): h_ontology,
    ("GET", "/api/config"): h_config,
    ("GET", "/api/eval"): h_eval,
    ("POST", "/api/parse-resume"): h_parse_resume,
    ("POST", "/api/parse-jd"): h_parse_jd,
    ("POST", "/api/mask"): h_mask,
    ("POST", "/api/match"): h_match,
    ("POST", "/api/screen"): h_screen,
    ("POST", "/api/bias-check"): h_bias,
    ("POST", "/api/ats"): h_ats,
    ("POST", "/api/learning-path"): h_learning_path,
    ("POST", "/api/interview"): h_interview,
}


class Handler(BaseHTTPRequestHandler):
    server_version = "ResumeRadar/" + __version__
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if os.environ.get("RR_QUIET"):
            return
        sys.stderr.write("  %s %s\n" % (self.command, fmt % args))

    def _send(self, status, body, ctype="application/json; charset=utf-8", extra=None):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store" if ctype.startswith("application/json") else "no-cache")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _api(self, method):
        url = urlparse(self.path)
        handler = ROUTES.get((method, url.path))
        if handler is None:
            if any(p == url.path for (_m, p) in ROUTES):
                return self._send(405, {"error": "method not allowed"}, extra={"Allow": "GET, POST"})
            return self._send(404, {"error": "unknown endpoint %s" % url.path})
        body = {}
        if method == "POST":
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return self._send(400, {"error": "bad Content-Length"})
            if length > config.MAX_BODY_BYTES:
                return self._send(413, {"error": "request body too large"})
            raw = self.rfile.read(length) if length else b""
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
            except (ValueError, UnicodeDecodeError):
                return self._send(400, {"error": "body must be valid UTF-8 JSON"})
            if not isinstance(body, dict):
                return self._send(400, {"error": "body must be a JSON object"})
        try:
            result = handler(parse_qs(url.query), body)
        except ApiError as e:
            return self._send(e.status, {"error": e.message})
        except Exception as e:  # never crash the server on bad input
            sys.stderr.write("  ERROR %s: %r\n" % (url.path, e))
            return self._send(500, {"error": "internal error: %s" % type(e).__name__})
        return self._send(200, result)

    def _static(self):
        url = urlparse(self.path)
        rel = url.path.lstrip("/") or "index.html"
        full = os.path.normpath(os.path.join(STATIC, rel))
        if not full.startswith(STATIC + os.sep) and full != STATIC:
            return self._send(403, {"error": "forbidden"})
        if os.path.isdir(full):
            full = os.path.join(full, "index.html")
        if not os.path.isfile(full):
            return self._send(404, {"error": "not found"})
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        with open(full, "rb") as f:
            return self._send(200, f.read(), ctype)

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._api("GET")
        return self._static()

    def do_HEAD(self):
        return self.do_GET()

    def do_POST(self):
        if self.path.startswith("/api/"):
            return self._api("POST")
        return self._send(405, {"error": "method not allowed"})


def main(argv=None):
    ap = argparse.ArgumentParser(description="ResumeRadar - fair, explainable resume screening")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = ap.parse_args(argv)
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("image/svg+xml", ".svg")
    if not os.path.exists(os.path.join(DATA, "demo.json")):
        write_demo(os.path.join(DATA, "demo.json"))
    screening.background_model()  # warm up the IDF background once
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    shown = "127.0.0.1" if args.host in ("0.0.0.0", "") else args.host
    print("\n  ResumeRadar %s - fair, explainable AI resume screening" % __version__)
    print("  -------------------------------------------------------")
    print("  Open   http://%s:%d/" % (shown, args.port))
    if args.host == "0.0.0.0":
        print("  LAN    listening on all interfaces (use this laptop's IP from a phone)")
    print("  %d skills, %d aliases, 100%% offline. Ctrl+C to stop.\n" % (len(ontology.SKILLS),
                                                                         ontology.stats()["aliases"]))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  bye")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
