"""Start every project's server on a spare port and check it serves its page and API.

    python tools/smoke_test.py            # all projects
    python tools/smoke_test.py 03 17      # only folders starting with 03 or 17

Runs each app.py as a subprocess (ports 9101+, so it does not clash with running demos),
waits for GET / to return 200 HTML, then GET /api/health (accepting 200, or 404 for apps
without that route), and stops it. The project folders are copied to a temporary
directory first, so the demos' own data files in the repo are left untouched.
"""
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
START_TIMEOUT = 120  # some apps train models at start-up


def free(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def get(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read(2048)
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), b""


def check(project, port):
    # stderr goes to a file, not a pipe: http.server logs every request there and a full
    # pipe buffer (small on Windows) would block the server
    log = open(project / "smoke-stderr.log", "w+b")
    proc = subprocess.Popen([sys.executable, "app.py", "--host", "127.0.0.1", "--port", str(port)],
                            cwd=project, stdout=subprocess.DEVNULL, stderr=log)
    t0 = time.time()
    try:
        while True:
            if proc.poll() is not None:
                log.seek(0)
                err = log.read().decode("utf-8", "replace").strip().splitlines()[-3:]
                return False, "exited with %s: %s" % (proc.returncode, " | ".join(err))
            try:
                status, ctype, body = get("http://127.0.0.1:%d/" % port)
                break
            except OSError:
                if time.time() - t0 > START_TIMEOUT:
                    return False, "no response within %ds" % START_TIMEOUT
                time.sleep(0.5)
        if status != 200 or "html" not in ctype.lower():
            return False, "GET / returned %s %s" % (status, ctype)
        h_status, _, _ = get("http://127.0.0.1:%d/api/health" % port)
        if h_status not in (200, 404):
            return False, "GET /api/health returned %s" % h_status
        return True, "up in %.1fs, / 200, /api/health %s" % (time.time() - t0, h_status)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        log.close()


def main(wanted):
    dirs = sorted(d for d in (ROOT / "projects").iterdir() if (d / "app.py").exists())
    dirs = [d for d in dirs if not wanted or any(d.name.startswith(w) for w in wanted)]
    failed = []
    port = 9101
    with tempfile.TemporaryDirectory() as tmp:
        for d in dirs:
            copy = Path(tmp) / d.name
            shutil.copytree(d, copy, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            while not free(port):
                port += 1
            ok, msg = check(copy, port)
            print("%-18s %s  %s" % (d.name, "ok  " if ok else "FAIL", msg), flush=True)
            if not ok:
                failed.append(d.name)
            port += 1
    print("\nFAILED: " + ", ".join(failed) if failed else "\nAll %d servers started and responded." % len(dirs))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
