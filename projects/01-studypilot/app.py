#!/usr/bin/env python3
"""StudyPilot - your offline AI study companion.

    python app.py [--host 127.0.0.1] [--port 8001]

Pure Python standard library: no pip install, no internet, no API keys.
"""
import argparse
import hashlib
import json
import mimetypes
import os
import re
import sys
import threading
import time
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from studypilot import __version__, mastery, quiz, srs
from studypilot.analysis import Analysis
from studypilot.samples import BY_ID as SAMPLE_BY_ID, SAMPLES, write_sample_files
from studypilot.store import Store

ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(ROOT, "static")
DATA = os.path.join(ROOT, "data")
DEFAULT_PORT = 8001
MAX_TEXT_CHARS = 300_000    # ~ a 150-page set of notes; keeps TextRank (O(n^2)) snappy
MIN_WORDS = 20
MAX_BODY = 2_000_000
CACHE_SIZE = 16

STORE = None
_CACHE = OrderedDict()
_CACHE_LOCK = threading.Lock()


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


def doc_id_for(text):
    return hashlib.sha1(text.strip().encode("utf-8")).hexdigest()[:12]


def get_analysis(doc_id):
    doc = STORE.get_doc(doc_id)
    if not doc:
        raise ApiError(404, "Unknown document id: %s" % doc_id)
    with _CACHE_LOCK:
        an = _CACHE.get(doc_id)
        if an is not None:
            _CACHE.move_to_end(doc_id)
            return doc, an
    an = Analysis(doc["text"], doc["title"])
    with _CACHE_LOCK:
        _CACHE[doc_id] = an
        while len(_CACHE) > CACHE_SIZE:
            _CACHE.popitem(last=False)
    return doc, an


def _int(params, name, default, lo, hi):
    raw = params.get(name, [None])[0] if isinstance(params.get(name), list) else params.get(name)
    if raw is None or raw == "":
        return default
    try:
        val = int(raw)
    except (TypeError, ValueError):
        raise ApiError(400, "%s must be an integer" % name)
    return max(lo, min(hi, val))


# --------------------------------------------------------------------- handlers
def h_health(_m, _q, _b):
    return {"ok": True, "name": "StudyPilot", "version": __version__, "offline": True,
            "docs": len(STORE.data["docs"])}


def h_samples(_m, _q, _b):
    return {"samples": [{"id": s["id"], "title": s["title"], "subject": s["subject"],
                         "words": len(s["text"].split())} for s in SAMPLES]}


def h_sample(_m, _q, _b, sample_id):
    s = SAMPLE_BY_ID.get(sample_id)
    if not s:
        raise ApiError(404, "Unknown sample: %s" % sample_id)
    return dict(s)


def h_docs(method, _q, body):
    if method == "GET":
        return {"docs": STORE.list_docs(), "last_doc": STORE.data.get("last_doc")}
    text = body.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ApiError(400, "Field 'text' (your notes) is required")
    if len(text) > MAX_TEXT_CHARS:
        raise ApiError(413, "Notes too long (%d chars, max %d)" % (len(text), MAX_TEXT_CHARS))
    title = body.get("title") or ""
    if not isinstance(title, str):
        raise ApiError(400, "Field 'title' must be a string")
    title = title.strip()[:120] or _guess_title(text)
    sample = body.get("sample") if body.get("sample") in SAMPLE_BY_ID else None
    words = len(re.findall(r"\w+", text))
    if words < MIN_WORDS:
        raise ApiError(400, "Please paste at least %d words of notes (got %d)" % (MIN_WORDS, words))
    did = doc_id_for(text)
    STORE.put_doc(did, title, text, sample)
    _, an = get_analysis(did)
    return {"doc": {"id": did, "title": title, "sample": sample}, "stats": an.stats()}


def _guess_title(text):
    for line in text.splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return line[:80]
    return "Untitled notes"


def h_doc(method, _q, _b, did):
    if method == "DELETE":
        if not STORE.delete_doc(did):
            raise ApiError(404, "Unknown document id: %s" % did)
        with _CACHE_LOCK:
            _CACHE.pop(did, None)
        return {"deleted": did}
    doc, an = get_analysis(did)
    STORE.data["last_doc"] = did
    return {"id": did, "title": doc["title"], "text": doc["text"], "sample": doc.get("sample"),
            "stats": an.stats(), "suggested_questions": an.suggested_questions()}


def h_summary(_m, q, _b, did):
    _, an = get_analysis(did)
    total = len(an.sentences)
    n = _int(q, "n", max(1, round(total * 0.2)), 1, max(1, total))
    return an.summary(n=n)


def h_concepts(_m, q, _b, did):
    _, an = get_analysis(did)
    return {"concepts": an.concept_list(_int(q, "k", 30, 1, 30))}


def h_quiz(_m, q, _b, did):
    _, an = get_analysis(did)
    n = _int(q, "n", 8, 1, 20)
    seed = _int(q, "seed", 0, 0, 10 ** 6)
    qs = an.quiz(n=n, seed=seed)
    return {"quiz_id": "%d-%d" % (n, seed), "n": n, "seed": seed,
            "questions": [quiz.public(x) for x in qs]}


def h_grade(_m, _q, body, did):
    _, an = get_analysis(did)
    n = _int(body, "n", 8, 1, 20)
    seed = _int(body, "seed", 0, 0, 10 ** 6)
    answers = body.get("answers")
    if not isinstance(answers, dict):
        raise ApiError(400, "Field 'answers' must be an object {question_id: answer}")
    qs = an.quiz(n=n, seed=seed)
    results, records, now = [], [], time.time()
    for qq in qs:
        ans = answers.get(qq["id"], "")
        if not isinstance(ans, str):
            ans = str(ans)
        r = quiz.grade(qq, ans[:200])
        r["kind"] = qq["kind"]
        r["prompt"] = qq["prompt"]
        results.append(r)
        if ans.strip():
            records.append({"concept": qq["concept"], "correct": r["correct"],
                            "kind": qq["kind"], "ts": now})
    if records:
        STORE.add_quiz_results(did, records)
    correct = sum(1 for r in results if r["correct"])
    return {"score": correct, "total": len(results), "results": results,
            "recorded": len(records),
            "mastery": _mastery(did, an)}


def _cards_view(did, an):
    now = time.time()
    states = STORE.card_states(did)
    cards, counts = [], {"new": 0, "due": 0, "learning": 0, "learned": 0}
    for c in an.cards:
        st = states.get(c["id"])
        if not st or not st.get("reviews"):
            status = "new"
        elif srs.is_due(st, now):
            status = "due"
        elif st.get("reps", 0) == 0:
            status = "learning"   # lapsed ("Again"): back in RELEARN_MINUTES
        else:
            status = "learned"
        counts[status] += 1
        cards.append(dict(c, state=st or srs.new_state(), status=status,
                          preview=srs.preview(st, now)))
    queue = [c["id"] for c in sorted(
        (c for c in cards if c["status"] in ("due", "new")),
        key=lambda c: (0 if c["status"] == "due" else 1, c["state"].get("due") or 0))]
    return {"cards": cards, "counts": counts, "queue": queue}


def h_cards(_m, _q, _b, did):
    _, an = get_analysis(did)
    return _cards_view(did, an)


def h_review(_m, _q, body, did):
    _, an = get_analysis(did)
    card_id = body.get("card_id")
    rating = body.get("rating")
    card = next((c for c in an.cards if c["id"] == card_id), None)
    if not card:
        raise ApiError(404, "Unknown card_id")
    if rating not in srs.QUALITY:
        raise ApiError(400, "rating must be one of %s" % ", ".join(srs.QUALITY))
    now = time.time()
    before = STORE.card_states(did).get(card_id)
    after = srs.review(before, rating, now)
    STORE.set_card_state(did, card_id, after)
    view = _cards_view(did, an)
    return {"card_id": card_id, "rating": rating, "quality": srs.QUALITY[rating],
            "before": before or srs.new_state(), "after": after,
            "next_in": srs.humanize(after["due"] - now),
            "explain": "SM-2: q=%d, EF %.2f -> %.2f, interval %s -> %s day(s)" % (
                srs.QUALITY[rating], (before or srs.new_state())["ef"], after["ef"],
                (before or srs.new_state())["interval"], after["interval"]),
            "deck": view, "mastery": _mastery(did, an)}


def h_reset(_m, _q, _b, did):
    _, an = get_analysis(did)
    STORE.reset_cards(did)
    return _cards_view(did, an)


def h_ask(method, q, body, did):
    _, an = get_analysis(did)
    question = body.get("question") if method == "POST" else (q.get("q") or [""])[0]
    if not isinstance(question, str) or not question.strip():
        raise ApiError(400, "Field 'question' is required")
    if len(question) > 500:
        raise ApiError(400, "Question too long (max 500 chars)")
    k = _int(body if method == "POST" else q, "k", 3, 1, 10)
    t0 = time.perf_counter()
    res = an.ask(question.strip(), k=k)
    res["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    return res


def _mastery(did, an):
    return mastery.compute(an.concepts, an.cards, STORE.card_states(did), STORE.quiz_log(did))


def h_mastery(_m, _q, _b, did):
    _, an = get_analysis(did)
    return _mastery(did, an)


ROUTES = [
    (r"/api/health", ("GET",), h_health),
    (r"/api/samples", ("GET",), h_samples),
    (r"/api/samples/([\w-]+)", ("GET",), h_sample),
    (r"/api/docs", ("GET", "POST"), h_docs),
    (r"/api/docs/(\w+)", ("GET", "DELETE"), h_doc),
    (r"/api/docs/(\w+)/summary", ("GET",), h_summary),
    (r"/api/docs/(\w+)/concepts", ("GET",), h_concepts),
    (r"/api/docs/(\w+)/quiz", ("GET",), h_quiz),
    (r"/api/docs/(\w+)/quiz/grade", ("POST",), h_grade),
    (r"/api/docs/(\w+)/flashcards", ("GET",), h_cards),
    (r"/api/docs/(\w+)/flashcards/review", ("POST",), h_review),
    (r"/api/docs/(\w+)/flashcards/reset", ("POST",), h_reset),
    (r"/api/docs/(\w+)/ask", ("GET", "POST"), h_ask),
    (r"/api/docs/(\w+)/mastery", ("GET",), h_mastery),
]
ROUTES = [(re.compile("^" + p + "/?$"), m, h) for p, m, h in ROUTES]


class Handler(BaseHTTPRequestHandler):
    server_version = "StudyPilot/" + __version__

    def log_message(self, fmt, *args):  # quieter console
        if os.environ.get("STUDYPILOT_LOG"):
            super().log_message(fmt, *args)

    def _send(self, status, payload, ctype="application/json; charset=utf-8"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ApiError(400, "Bad Content-Length")
        if length > MAX_BODY:
            raise ApiError(413, "Request body too large")
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ApiError(400, "Body must be valid JSON")
        if not isinstance(data, dict):
            raise ApiError(400, "JSON body must be an object")
        return data

    def _api(self, method):
        url = urlparse(self.path)
        try:
            for rx, methods, handler in ROUTES:
                m = rx.match(url.path)
                if not m:
                    continue
                if method not in methods:
                    raise ApiError(405, "Method %s not allowed here" % method)
                body = self._body() if method == "POST" else {}
                result = handler(method, parse_qs(url.query), body, *m.groups())
                return self._send(200, result)
            raise ApiError(404, "No such endpoint: %s" % url.path)
        except ApiError as e:
            self._send(e.status, {"error": e.message, "status": e.status})
        except Exception as e:  # never crash the server on bad input
            sys.stderr.write("Internal error on %s %s: %r\n" % (method, self.path, e))
            self._send(500, {"error": "Internal error: %s" % type(e).__name__, "status": 500})

    def _static(self):
        path = urlparse(self.path).path
        if path == "/":
            path = "/index.html"
        full = os.path.realpath(os.path.join(STATIC, path.lstrip("/")))
        if not full.startswith(os.path.realpath(STATIC) + os.sep) or not os.path.isfile(full):
            return self._send(404, {"error": "Not found", "status": 404})
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        with open(full, "rb") as f:
            self._send(200, f.read(), ctype)

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._api("GET")
        return self._static()

    def do_HEAD(self):
        return self.do_GET()

    def do_POST(self):
        if self.path.startswith("/api/"):
            return self._api("POST")
        self._send(405, {"error": "Method not allowed", "status": 405})

    def do_DELETE(self):
        if self.path.startswith("/api/"):
            return self._api("DELETE")
        self._send(405, {"error": "Method not allowed", "status": 405})


def main(argv=None):
    global STORE
    ap = argparse.ArgumentParser(description="StudyPilot - offline AI study companion")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--data", default=os.path.join(DATA, "state.json"),
                    help="path of the JSON state file")
    args = ap.parse_args(argv)
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("image/svg+xml", ".svg")
    write_sample_files(os.path.join(DATA, "samples"))
    STORE = Store(args.data)
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    shown = "localhost" if args.host in ("127.0.0.1", "0.0.0.0") else args.host
    print("=" * 58)
    print("  StudyPilot %s - your offline AI study companion" % __version__)
    print("  Open  http://%s:%d/   (Ctrl+C to stop)" % (shown, args.port))
    if args.host == "0.0.0.0":
        print("  LAN mode: phones on this Wi-Fi can use http://<this-PC-IP>:%d/" % args.port)
    print("  No internet, no API keys - everything runs on this laptop.")
    print("=" * 58)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nBye - happy studying!")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
