#!/usr/bin/env python3
"""SchemeSetu server - python app.py [--host 127.0.0.1] [--port 8011]

Standard library only. Serves the UI from static/ and a JSON API under /api/.
State (registered households + application tracker) lives in data/state.json.
"""
import argparse
import json
import mimetypes
import os
import re
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from schemesetu import __version__, config, synth  # noqa: E402
from schemesetu.catalogue import ProfileError  # noqa: E402
from schemesetu.engine import Engine  # noqa: E402
from schemesetu.store import NotFound, Store, StoreError  # noqa: E402

STATIC_DIR = os.path.join(HERE, "static")
DATA_DIR = os.path.join(HERE, "data")
STATE_PATH = os.path.join(DATA_DIR, "state.json")
MAX_BODY = 64 * 1024
ENGINE = None
STORE = None


class ApiError(Exception):
    def __init__(self, status, message):
        Exception.__init__(self, message)
        self.status = status
        self.message = message


# ------------------------------------------------------------------ helpers
def _profile(body, key="profile"):
    raw = body.get(key, {}) if isinstance(body, dict) else None
    if raw is None:
        raw = {}
    try:
        return ENGINE.normalise(raw)
    except ProfileError as e:
        raise ApiError(400, str(e))


def _str_list(body, key, limit=64):
    v = body.get(key, [])
    if v is None:
        return []
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v) or len(v) > limit:
        raise ApiError(400, "'%s' must be a list of strings (max %d)" % (key, limit))
    return v


def _strategy(body):
    s = body.get("strategy") if isinstance(body, dict) else None
    if s is None:
        return None
    if s not in ("ig", "resolve", "static"):
        raise ApiError(400, "strategy must be ig, resolve or static")
    return s


def _q(q, name, default=None):
    v = q.get(name)
    return v[0] if v else default


def _household(hid):
    try:
        return STORE.get(hid)
    except NotFound:
        raise ApiError(404, "household '%s' not found" % hid)


def _household_view(h):
    ev = ENGINE.evaluate(h["profile"])
    for r in ev["results"]:
        r["application"] = (h["applications"].get(r["id"]) or {}).get("status", "not_applied")
    return {"household": h, "evaluation": ev}


# ------------------------------------------------------------------ GET routes
def api_health(q):
    return {"status": "ok", "version": __version__, "households": len(STORE.list()), **ENGINE.stats()}


def api_meta(q):
    cat = ENGINE.cat
    return {"version": cat.version, "categories": cat.categories, "documents": cat.documents,
            "params": cat.params, "verify_note": cat.verify_note,
            "application_statuses": list(config.APPLICATION_STATUSES),
            "demo_village": config.DEMO_VILLAGE, **ENGINE.stats()}


def api_schemes(q):
    cat = ENGINE.cat
    cats = _q(q, "category")
    out = [cat.public_scheme(s) for s in cat.schemes if not cats or s["category"] == cats]
    return {"count": len(out), "schemes": out}


def api_questions(q):
    return {"questions": ENGINE.cat.questions, "inferences": ENGINE.cat.inferences,
            "full_form": len(ENGINE.cat.atomic), "priors": dict(
                (k, [[v, round(p, 4)] for v, p in dist]) for k, dist in ENGINE.priors.items())}


def api_search(q):
    text = (_q(q, "q") or "").strip()
    if not text:
        raise ApiError(400, "query parameter 'q' is required")
    if len(text) > 200:
        raise ApiError(400, "query too long (max 200 characters)")
    try:
        k = int(_q(q, "k", "5"))
    except ValueError:
        raise ApiError(400, "'k' must be an integer")
    if not 1 <= k <= 22:
        raise ApiError(400, "'k' must be between 1 and 22")
    t0 = time.perf_counter()
    res = ENGINE.search(text, k)
    res["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    return res


def api_demo(q):
    return {"households": synth.DEMO_HOUSEHOLDS}


def api_households(q):
    village = _q(q, "village")
    hs = STORE.list(village)
    out = []
    for h in hs:
        st = ENGINE.statuses(h["profile"])
        out.append({"id": h["id"], "name": h["name"], "village": h["village"], "source": h.get("source"),
                    "eligible": sum(1 for v in st.values() if v == "eligible"),
                    "applications": len(h["applications"]), "updated": h["updated"]})
    return {"count": len(out), "households": out, "villages": STORE.villages()}


def api_village(q):
    village = _q(q, "village")
    t0 = time.perf_counter()
    d = ENGINE.village_dashboard(STORE.list(), village)
    d["villages"] = STORE.villages()
    d["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    return d


def api_evaluation(q):
    path = os.path.join(DATA_DIR, "evaluation.json")
    if not os.path.exists(path):
        return {"available": False, "hint": "run: python -m schemesetu.evaluate"}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


GET_ROUTES = {
    "/api/health": api_health,
    "/api/meta": api_meta,
    "/api/schemes": api_schemes,
    "/api/questions": api_questions,
    "/api/search": api_search,
    "/api/demo": api_demo,
    "/api/households": api_households,
    "/api/village": api_village,
    "/api/evaluation": api_evaluation,
}


# ------------------------------------------------------------------ POST routes
def api_evaluate(body):
    t0 = time.perf_counter()
    ev = ENGINE.evaluate(_profile(body))
    ev["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    return ev


def api_next(body):
    t0 = time.perf_counter()
    prof = _profile(body)
    skipped = _str_list(body, "skipped")
    nq = ENGINE.next_question(prof, skipped, _strategy(body))
    ev = ENGINE.evaluate(prof)
    return {"done": nq is None, "next": nq, "evaluation": ev,
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2)}


def api_simulate(body):
    demo_id = body.get("demo")
    if demo_id is not None:
        match = [d for d in synth.DEMO_HOUSEHOLDS if d["id"] == demo_id]
        if not match:
            raise ApiError(404, "unknown demo household '%s'" % demo_id)
        truth = match[0]["profile"]
    else:
        truth = _profile(body)
        if not truth:
            raise ApiError(400, "give 'demo' or a non-empty 'profile'")
    sim = ENGINE.simulate(truth, _strategy(body))
    sim["evaluation"] = ENGINE.evaluate(sim["profile"])
    return sim


def api_checklist(body):
    ids = _str_list(body, "scheme_ids")
    extra = body.get("extra")
    if extra is not None and not isinstance(extra, dict):
        raise ApiError(400, "'extra' must be an object {scheme_id: [names]}")
    return ENGINE.checklist(ids, extra)


def api_create_household(body):
    prof = _profile(body)
    try:
        h = STORE.create(body.get("name"), body.get("village"), prof)
    except StoreError as e:
        raise ApiError(400, str(e))
    return _household_view(h)


def api_demo_village(body):
    n = STORE.replace_source("demo", ENGINE.demo_village_households())
    return {"status": "ok", "households": n, "village": config.DEMO_VILLAGE}


def api_demo_reset(body):
    STORE.reset()
    return {"status": "ok", "message": "All registered households cleared"}


POST_ROUTES = {
    "/api/evaluate": api_evaluate,
    "/api/next": api_next,
    "/api/simulate": api_simulate,
    "/api/checklist": api_checklist,
    "/api/households": api_create_household,
    "/api/demo/village": api_demo_village,
    "/api/demo/reset": api_demo_reset,
}

RE_SCHEME = re.compile(r"^/api/schemes/([a-z0-9_]{1,40})$")
RE_HH = re.compile(r"^/api/households/([A-Za-z0-9_-]{1,40})$")
RE_HH_APP = re.compile(r"^/api/households/([A-Za-z0-9_-]{1,40})/applications$")


class Handler(BaseHTTPRequestHandler):
    server_version = "SchemeSetu/" + __version__

    def log_message(self, fmt, *args):
        if os.environ.get("SCHEMESETU_LOG"):
            BaseHTTPRequestHandler.log_message(self, fmt, *args)

    # -------------------------------------------------------------- plumbing
    def _send(self, status, body, ctype):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status, obj):
        self._send(status, json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _error(self, status, msg):
        self._json(status, {"error": msg, "status": status})

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ApiError(400, "bad Content-Length")
        if n > MAX_BODY:
            raise ApiError(413, "body too large (max %d bytes)" % MAX_BODY)
        raw = self.rfile.read(n) if n > 0 else b""
        if not raw.strip():
            return {}
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ApiError(400, "body must be valid JSON")
        if not isinstance(body, dict):
            raise ApiError(400, "body must be a JSON object")
        return body

    def _run(self, fn, *args):
        try:
            self._json(200, fn(*args))
        except ApiError as e:
            self._error(e.status, e.message)
        except Exception:  # never crash the server on bad input
            traceback.print_exc()
            self._error(500, "internal error")

    # -------------------------------------------------------------- verbs
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        url = urlparse(self.path)
        path = url.path
        if path.startswith("/api/"):
            q = parse_qs(url.query)
            if path in GET_ROUTES:
                return self._run(GET_ROUTES[path], q)
            m = RE_SCHEME.match(path)
            if m:
                return self._run(self._get_scheme, m.group(1))
            m = RE_HH.match(path)
            if m:
                return self._run(lambda hid: _household_view(_household(hid)), m.group(1))
            if path in POST_ROUTES or RE_HH_APP.match(path):
                return self._error(405, "use POST for %s" % path)
            return self._error(404, "no such endpoint: %s" % path)
        return self._static(path)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            body = self._body()
        except ApiError as e:
            return self._error(e.status, e.message)
        if path in POST_ROUTES:
            return self._run(POST_ROUTES[path], body)
        m = RE_HH_APP.match(path)
        if m:
            return self._run(self._set_application, m.group(1), body)
        m = RE_HH.match(path)
        if m:  # POST to a household = update (handy for clients without PUT)
            return self._run(self._update_household, m.group(1), body)
        if path in GET_ROUTES:
            return self._error(405, "use GET for %s" % path)
        return self._error(404, "no such endpoint: %s" % path)

    def do_PUT(self):
        path = urlparse(self.path).path
        try:
            body = self._body()
        except ApiError as e:
            return self._error(e.status, e.message)
        m = RE_HH.match(path)
        if m:
            return self._run(self._update_household, m.group(1), body)
        return self._error(404 if not path.startswith("/api/households") else 405, "PUT not supported here")

    def do_DELETE(self):
        path = urlparse(self.path).path
        m = RE_HH.match(path)
        if not m:
            return self._error(404, "DELETE not supported here")
        return self._run(self._delete_household, m.group(1))

    # -------------------------------------------------------------- handlers
    @staticmethod
    def _get_scheme(sid):
        s = ENGINE.cat.by_id.get(sid)
        if not s:
            raise ApiError(404, "scheme '%s' not found" % sid)
        return ENGINE.cat.public_scheme(s)

    @staticmethod
    def _update_household(hid, body):
        _household(hid)
        prof = _profile(body) if "profile" in body else None
        try:
            h = STORE.update(hid, body.get("name"), body.get("village"), prof)
        except StoreError as e:
            raise ApiError(400, str(e))
        return _household_view(h)

    @staticmethod
    def _delete_household(hid):
        _household(hid)
        STORE.delete(hid)
        return {"status": "ok", "deleted": hid}

    @staticmethod
    def _set_application(hid, body):
        _household(hid)
        sid = body.get("scheme_id")
        if not isinstance(sid, str) or sid not in ENGINE.cat.by_id:
            raise ApiError(400, "'scheme_id' must be a known scheme id")
        try:
            h = STORE.set_application(hid, sid, body.get("status"))
        except StoreError as e:
            raise ApiError(400, str(e))
        return _household_view(h)

    def _static(self, path):
        if path in ("", "/"):
            path = "/index.html"
        rel = unquote(path).lstrip("/")
        full = os.path.realpath(os.path.join(STATIC_DIR, rel))
        root = os.path.realpath(STATIC_DIR)
        if not (full == root or full.startswith(root + os.sep)) or not os.path.isfile(full):
            return self._error(404, "not found")
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        with open(full, "rb") as f:
            self._send(200, f.read(), ctype)


def main(argv=None):
    global ENGINE, STORE
    ap = argparse.ArgumentParser(description="SchemeSetu - welfare scheme matcher")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8011)
    args = ap.parse_args(argv)
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("image/svg+xml", ".svg")
    ENGINE = Engine(DATA_DIR)
    STORE = Store(STATE_PATH)
    if not STORE.list():  # first run: seed the demo village so the dashboard is never empty
        STORE.replace_source("demo", ENGINE.demo_village_households())
    try:
        srv = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as e:
        print("\n  Could not start on %s:%d (%s)." % (args.host, args.port, e.strerror or e))
        print("  Is SchemeSetu already running? Try another port:  python app.py --port %d\n" % (args.port + 100))
        return 1
    shown = "127.0.0.1" if args.host in ("0.0.0.0", "") else args.host
    print("")
    print("  SchemeSetu %s - every rural family, matched to the schemes they deserve" % __version__)
    print("  %d schemes, %d questions, engine ready in %.0f ms" % (
        len(ENGINE.cat.schemes), len(ENGINE.cat.atomic), ENGINE.startup_ms))
    print("  Open  http://%s:%d/" % (shown, args.port))
    if args.host == "0.0.0.0":
        print("  (listening on all interfaces - use this laptop's LAN IP from a phone)")
    print("  Ctrl+C to stop.\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    sys.exit(main())
