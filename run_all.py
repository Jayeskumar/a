"""Start every QUANTIX 2K26 demo at once, plus a showcase hub on port 8000.

    python run_all.py              # all projects on 127.0.0.1, hub at http://127.0.0.1:8000
    python run_all.py --lan        # bind 0.0.0.0 so judges can open them from a phone
    python run_all.py 03 06        # only projects whose folder starts with 03 or 06
    python run_all.py --no-hub     # skip the hub page

Each project keeps running in its own process; Ctrl+C stops them all.
"""
import json
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECTS = ROOT / "projects"
HUB_PORT = 8000
MERMAID_JS = ROOT / "tools" / "node_modules" / "mermaid" / "dist" / "mermaid.min.js"  # optional, for report diagrams
ASSET_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".svg": "image/svg+xml"}

sys.path.insert(0, str(ROOT / "hub"))
from report_view import report_page  # noqa: E402


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # no packet is sent; just picks the outbound interface
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def is_listening(port):
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=0.2):
            return True
    except (OSError, TypeError, ValueError):
        return False


def project_dirs():
    return sorted(p for p in PROJECTS.iterdir() if (p / "app.py").exists())


def read_pitch(d):
    f = d / "pitch.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"name": d.name}


class HubHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            return self._send(200, (ROOT / "hub" / "index.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/api/projects":
            items = []
            for d in project_dirs():
                if not (d / "pitch.json").exists():
                    continue  # still being built
                p = read_pitch(d)
                items.append({
                    "num": d.name.split("-")[0], "dir_name": d.name, "name": p.get("name", d.name),
                    "tagline": p.get("tagline", ""), "domain": p.get("domain", ""),
                    "color": p.get("color", "#7c5cff"), "port": p.get("port"),
                    "results": p.get("results", []), "live": is_listening(p.get("port")),
                    "shot": (d / "docs" / "screenshot.png").exists(),
                })
            return self._send(200, json.dumps({"projects": items}).encode(), "application/json")
        # /shots/<dir>.png and /report/<dir> only resolve to known project folders
        known = {d.name: d for d in project_dirs()}
        if path.startswith("/shots/") and path.endswith(".png"):
            d = known.get(path[len("/shots/"):-4])
            shot = d / "docs" / "screenshot.png" if d else None
            if shot and shot.exists():
                return self._send(200, shot.read_bytes(), "image/png")
        if path.startswith("/report/"):
            # /report/<dir> renders REPORT.md; /report/<dir>/<file> serves images or renders other .md files
            name, _, rel = path[len("/report/"):].partition("/")
            d = known.get(name)
            target = (d / (rel or "REPORT.md")).resolve() if d else None
            if target and target.is_file() and d.resolve() in target.parents:
                if target.suffix.lower() == ".md":
                    return self._report(d, target)
                if target.suffix.lower() in ASSET_TYPES:
                    return self._send(200, target.read_bytes(), ASSET_TYPES[target.suffix.lower()])
        if path == "/vendor/mermaid.min.js" and MERMAID_JS.exists():
            return self._send(200, MERMAID_JS.read_bytes(), "application/javascript; charset=utf-8")
        self._send(404, b'{"error": "not found"}', "application/json")

    def _report(self, d, md_file):
        pitch = read_pitch(d)
        base = md_file.parent.relative_to(d).as_posix()
        prefix = "/report/%s/%s" % (d.name, base + "/" if base != "." else "")
        host = (self.headers.get("Host") or "127.0.0.1").rsplit(":", 1)[0]
        demo = "http://%s:%s/" % (host, pitch["port"]) if pitch.get("port") else None
        page = report_page(pitch, md_file.read_text(encoding="utf-8"), lambda p: prefix + p, demo, MERMAID_JS.exists())
        self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")


def main(argv):
    lan = "--lan" in argv
    wanted = [a for a in argv if not a.startswith("--")]
    host = "0.0.0.0" if lan else "127.0.0.1"
    shown = lan_ip() if lan else "127.0.0.1"

    procs = []
    for d in project_dirs():
        if wanted and not any(d.name.startswith(w) for w in wanted):
            continue
        pitch = read_pitch(d)
        port = str(pitch.get("port", ""))
        cmd = [sys.executable, "app.py", "--host", host] + (["--port", port] if port else [])
        procs.append((pitch.get("name", d.name), port, subprocess.Popen(cmd, cwd=d, stdout=subprocess.DEVNULL)))

    hub = None
    if "--no-hub" not in argv:
        hub = ThreadingHTTPServer((host, HUB_PORT), HubHandler)
        threading.Thread(target=hub.serve_forever, daemon=True).start()

    time.sleep(2)
    print("\nQUANTIX 2K26 demos\n" + "-" * 52)
    if hub:
        print(f"  {'Showcase hub':<14} http://{shown}:{HUB_PORT}/")
    for name, port, p in procs:
        state = "running" if p.poll() is None else f"exited ({p.returncode})"
        print(f"  {name:<14} http://{shown}:{port}/   {state}")
    print("-" * 52 + "\nSome demos train models at start-up and take a few seconds to come up.\nCtrl+C to stop all.\n")
    try:
        while any(p.poll() is None for _, _, p in procs):
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for _, _, p in procs:
            if p.poll() is None:
                p.terminate()
        if hub:
            hub.shutdown()


if __name__ == "__main__":
    main(sys.argv[1:])
