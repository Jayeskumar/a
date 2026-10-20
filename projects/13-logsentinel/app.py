#!/usr/bin/env python3
"""LogSentinel server - python app.py [--host 127.0.0.1] [--port 8013]

A pocket SOC: detect attacks hiding in your server logs. Standard library only.
Serves the dashboard from static/ and a JSON API under /api/.
"""

import argparse
import json
import mimetypes
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from logsentinel import __version__                 # noqa: E402
from logsentinel.service import Service              # noqa: E402

STATIC_DIR = os.path.join(HERE, "static")
MAX_BODY = 8 * 1024 * 1024        # uploaded logs can be a few MB
SVC = None


class ApiError(Exception):
    def __init__(self, status, message):
        Exception.__init__(self, message)
        self.status = status
        self.message = message


def _one(q, name, default=None):
    vals = q.get(name)
    return vals[0] if vals else default


def _int(q, name, default):
    v = _one(q, name)
    if v is None:
        return default
    try:
        return int(v)
    except ValueError:
        raise ApiError(400, "'%s' must be an integer" % name)


def get_routes(q):
    s = SVC
    return {
        "/api/health": lambda: s.health(),
        "/api/summary": lambda: s.summary(),
        "/api/alerts": lambda: s.alerts(_one(q, "severity"), _one(q, "category"),
                                        _one(q, "src"), _one(q, "rule")),
        "/api/incidents": lambda: s.incidents(),
        "/api/rpm": lambda: s.rpm(),
        "/api/stream": lambda: s.stream(_int(q, "offset", 0), _int(q, "limit", 400)),
        "/api/blocklist": lambda: s.blocklist(),
        "/api/evaluation": lambda: s.evaluation(),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "LogSentinel/" + __version__

    def log_message(self, fmt, *args):
        if os.environ.get("LOGSENTINEL_LOG"):
            BaseHTTPRequestHandler.log_message(self, fmt, *args)

    # ---- low level ----
    def _send(self, status, body, ctype):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status, obj):
        self._send(status, json.dumps(obj, separators=(",", ":")), "application/json; charset=utf-8")

    def _error(self, status, msg):
        self._json(status, {"error": msg, "status": status})

    def _run(self, fn):
        try:
            self._json(200, fn())
        except ApiError as e:
            self._error(e.status, e.message)
        except KeyError as e:
            self._error(404, "not found: %s" % e.args[0])
        except ValueError as e:
            self._error(400, str(e))
        except Exception:
            traceback.print_exc()
            self._error(500, "internal error")

    # ---- verbs ----
    def do_GET(self):
        url = urlparse(self.path)
        path = url.path
        q = parse_qs(url.query)

        if path.startswith("/api/"):
            # parametric GETs
            if path.startswith("/api/alert/"):
                aid = path[len("/api/alert/"):]
                return self._run(lambda: SVC.alert(aid))
            if path.startswith("/api/incident/"):
                iid = path[len("/api/incident/"):]
                return self._run(lambda: SVC.incident(iid))
            if path.startswith("/api/report/"):
                iid = path[len("/api/report/"):]
                fmt = _one(q, "format", "md")
                return self._report(iid, fmt)
            routes = get_routes(q)
            stripped = path.rstrip("/") or "/"
            key = path if path in routes else stripped
            if key in routes:
                return self._run(routes[key])
            if path in ("/api/analyze", "/api/demo/reset"):
                return self._error(405, "use POST for %s" % path)
            return self._error(404, "no such endpoint: %s" % path)
        return self._static(path)

    do_HEAD = do_GET

    def _report(self, iid, fmt):
        try:
            text = SVC.report(iid, "html" if fmt == "html" else "md")
        except KeyError:
            return self._error(404, "no such incident: %s" % iid)
        if fmt == "html":
            return self._send(200, text, "text/html; charset=utf-8")
        return self._send(200, text, "text/markdown; charset=utf-8")

    def do_POST(self):
        url = urlparse(self.path)
        path = url.path.rstrip("/")
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._error(400, "bad Content-Length")
        if length > MAX_BODY:
            return self._error(413, "request body too large (max %d bytes)" % MAX_BODY)
        raw = self.rfile.read(length) if length else b""

        if path == "/api/demo/reset":
            return self._run(lambda: (SVC.load_demo(), SVC.summary())[1])

        if path == "/api/analyze":
            ctype = self.headers.get("Content-Type", "")
            text = None
            fmt = None
            if "application/json" in ctype:
                try:
                    body = json.loads(raw.decode("utf-8")) if raw.strip() else {}
                except (ValueError, UnicodeDecodeError):
                    return self._error(400, "body must be valid JSON")
                if not isinstance(body, dict):
                    return self._error(400, "body must be a JSON object")
                text = body.get("log") or body.get("text") or ""
                fmt = body.get("format")
            else:
                text = raw.decode("utf-8", "replace")
            if not text.strip():
                return self._error(400, "no log text provided")
            return self._run(lambda: SVC.analyze_text(text, fmt))

        if path in get_routes({}):
            return self._error(405, "use GET for %s" % path)
        return self._error(404, "no such endpoint: %s" % path)

    def _static(self, path):
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        full = os.path.realpath(os.path.join(STATIC_DIR, rel))
        if not full.startswith(os.path.realpath(STATIC_DIR) + os.sep) or not os.path.isfile(full):
            return self._send(404, "Not found", "text/plain; charset=utf-8")
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        with open(full, "rb") as f:
            self._send(200, f.read(), ctype)


def main(argv=None):
    global SVC
    ap = argparse.ArgumentParser(description="LogSentinel - a pocket SOC for your logs")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8013)
    args = ap.parse_args(argv)
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("text/css", ".css")

    SVC = Service()
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    shown = "127.0.0.1" if args.host in ("0.0.0.0", "") else args.host
    an = SVC.an
    print("")
    print("  LogSentinel %s - a pocket SOC: attacks hiding in your logs" % __version__)
    print("  Analysed %d log lines -> %d alerts across %d incidents."
          % (len(an.events), len(an.alerts), len(an.incidents)))
    print("  Open  http://%s:%d/" % (shown, args.port))
    if args.host == "0.0.0.0":
        print("  (listening on all interfaces - use this laptop's LAN IP from a phone)")
    print("  Ctrl+C to stop.")
    print("")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
