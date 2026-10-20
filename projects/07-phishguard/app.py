#!/usr/bin/env python3
"""PhishGuard server - python app.py [--host 127.0.0.1] [--port 8007]

Pure standard library. Serves the UI from static/ and a JSON API under /api/.
Everything runs locally; no request ever leaves this machine.
"""
import argparse
import json
import mimetypes
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from phishguard import config, corpus, rules as rules_mod, samples  # noqa: E402
from phishguard.scorer import PhishGuard  # noqa: E402

STATIC = os.path.join(HERE, "static")
DATA = os.path.join(HERE, "data")
ENGINE = None


def load_engine():
    """Load the committed corpus (or generate it on first run), train, write metrics."""
    msg_path = os.path.join(DATA, "messages.json")
    url_path = os.path.join(DATA, "urls.json")
    if os.path.exists(msg_path) and os.path.exists(url_path):
        with open(msg_path, encoding="utf-8") as f:
            messages = json.load(f)
        with open(url_path, encoding="utf-8") as f:
            urls = json.load(f)
    else:
        messages, urls = corpus.write_data(DATA)
    engine = PhishGuard(messages, urls)
    stats = engine.stats()
    try:
        with open(os.path.join(DATA, "metrics.json"), "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=1)
    except OSError:
        pass
    return engine


class Handler(BaseHTTPRequestHandler):
    server_version = "PhishGuard/1.0"

    def log_message(self, fmt, *args):  # quieter console
        sys.stderr.write("  %s %s\n" % (self.command, self.path))

    # ------------------------------------------------------------ helpers
    def _send(self, status, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _json(self, obj, status=200):
        self._send(status, json.dumps(obj, ensure_ascii=False))

    def _error(self, status, message):
        self._json({"error": message, "status": status}, status)

    def _body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ValueError("invalid Content-Length")
        if length > config.MAX_BODY_BYTES:
            raise OverflowError("request body too large")
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        try:
            obj = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("body must be valid UTF-8 JSON")
        if not isinstance(obj, dict):
            raise ValueError("body must be a JSON object")
        return obj

    # ------------------------------------------------------------ routes
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = urlsplit(self.path).path
        try:
            if path == "/api/health":
                return self._json({"ok": True, "service": "PhishGuard", "offline": True,
                                   "trained_seconds": ENGINE.stats()["train_seconds"]})
            if path == "/api/samples":
                return self._json({"samples": samples.DEMO_SAMPLES, "bulk": samples.BULK_DEMO})
            if path == "/api/quiz":
                return self._json({"questions": samples.QUIZ})
            if path == "/api/stats":
                return self._json(ENGINE.stats())
            if path == "/api/rules":
                return self._json({"rules": [{"id": r.id, "title": r.title, "category": r.category,
                                              "weight": r.weight, "advice": r.advice} for r in rules_mod.RULES]})
            if path.startswith("/api/"):
                return self._error(404, "unknown endpoint")
            return self._static(path)
        except Exception as exc:  # never crash the server
            return self._error(500, "internal error: %s" % exc.__class__.__name__)

    def do_POST(self):
        path = urlsplit(self.path).path
        try:
            body = self._body()
        except OverflowError as exc:
            return self._error(413, str(exc))
        except ValueError as exc:
            return self._error(400, str(exc))
        try:
            if path == "/api/analyze":
                text = body.get("text")
                kind = body.get("kind", "auto")
                if not isinstance(text, str) or not text.strip():
                    return self._error(400, "'text' must be a non-empty string")
                if kind not in ("auto", "message", "url"):
                    return self._error(400, "'kind' must be auto, message or url")
                if len(text) > config.MAX_INPUT_CHARS:
                    return self._error(413, "text longer than %d characters" % config.MAX_INPUT_CHARS)
                return self._json(ENGINE.analyse(text, kind))
            if path == "/api/url":
                url = body.get("url")
                if not isinstance(url, str) or not url.strip() or len(url) > 2048:
                    return self._error(400, "'url' must be a non-empty string (max 2048 chars)")
                return self._json(ENGINE.analyse(url.strip(), "url"))
            if path == "/api/bulk":
                lines = body.get("lines")
                if lines is None and isinstance(body.get("text"), str):
                    lines = body["text"].splitlines()
                if not isinstance(lines, list) or not all(isinstance(x, str) for x in lines):
                    return self._error(400, "send 'text' (string) or 'lines' (list of strings)")
                lines = [x[: config.MAX_INPUT_CHARS] for x in lines if x.strip()]
                if not lines:
                    return self._error(400, "no non-empty lines to scan")
                if len(lines) > config.MAX_BULK_LINES:
                    return self._error(413, "at most %d lines per scan" % config.MAX_BULK_LINES)
                t0 = time.perf_counter()
                out = ENGINE.bulk(lines)
                out["total_ms"] = round((time.perf_counter() - t0) * 1000, 2)
                return self._json(out)
            return self._error(404, "unknown endpoint")
        except Exception as exc:
            return self._error(500, "internal error: %s" % exc.__class__.__name__)

    def _static(self, path):
        if path in ("", "/"):
            path = "/index.html"
        full = os.path.normpath(os.path.join(STATIC, path.lstrip("/")))
        if not full.startswith(STATIC + os.sep) or not os.path.isfile(full):
            return self._error(404, "not found")
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
            ctype += "; charset=utf-8"
        with open(full, "rb") as f:
            self._send(200, f.read(), ctype)


def main(argv=None):
    ap = argparse.ArgumentParser(description="PhishGuard - offline scam & phishing detector")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8007)
    args = ap.parse_args(argv)
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("text/css", ".css")
    global ENGINE
    t0 = time.perf_counter()
    ENGINE = load_engine()
    s = ENGINE.stats()
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    shown = "127.0.0.1" if args.host in ("0.0.0.0", "") else args.host
    print("")
    print("  PhishGuard - explainable scam & phishing detector")
    print("  Models trained in %.2fs (NB vocab %d, %d URL features, %d rules)"
          % (time.perf_counter() - t0, s["dataset"]["nb_vocabulary"], s["dataset"]["url_features"], s["dataset"]["rules"]))
    print("  Open  http://%s:%d/" % (shown, args.port))
    if args.host == "0.0.0.0":
        print("  (listening on all interfaces - use this laptop's LAN IP from a phone)")
    print("  100% offline: nothing leaves this device. Ctrl+C to stop.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  bye")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
