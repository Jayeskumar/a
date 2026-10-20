"""Start every QUANTIX 2K26 demo at once.

    python run_all.py              # all projects on 127.0.0.1
    python run_all.py --lan        # bind 0.0.0.0 so judges can open them from a phone
    python run_all.py 03 06        # only projects whose folder starts with 03 or 06

Each project keeps running in its own process; Ctrl+C stops them all.
"""
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECTS = ROOT / "projects"


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # no packet is sent; just picks the outbound interface
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def main(argv):
    lan = "--lan" in argv
    wanted = [a for a in argv if not a.startswith("--")]
    host = "0.0.0.0" if lan else "127.0.0.1"
    shown = lan_ip() if lan else "127.0.0.1"

    procs = []
    for d in sorted(p for p in PROJECTS.iterdir() if (p / "app.py").exists()):
        if wanted and not any(d.name.startswith(w) for w in wanted):
            continue
        pitch = json.loads((d / "pitch.json").read_text(encoding="utf-8")) if (d / "pitch.json").exists() else {}
        port = str(pitch.get("port", ""))
        cmd = [sys.executable, "app.py", "--host", host] + (["--port", port] if port else [])
        procs.append((pitch.get("name", d.name), port, subprocess.Popen(cmd, cwd=d, stdout=subprocess.DEVNULL)))

    time.sleep(1.5)
    print("\nQUANTIX 2K26 demos\n" + "-" * 48)
    for name, port, p in procs:
        state = "running" if p.poll() is None else f"exited ({p.returncode})"
        print(f"  {name:<14} http://{shown}:{port}/   {state}")
    print("-" * 48 + "\nCtrl+C to stop all.\n")
    try:
        while any(p.poll() is None for _, _, p in procs):
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for _, _, p in procs:
            if p.poll() is None:
                p.terminate()


if __name__ == "__main__":
    main(sys.argv[1:])
