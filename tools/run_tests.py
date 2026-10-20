"""Run every project's unit tests: python tools/run_tests.py [03 06 ...]"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(wanted):
    failed = []
    dirs = sorted(d for d in (ROOT / "projects").iterdir() if (d / "tests").is_dir())
    for d in dirs:
        if wanted and not any(d.name.startswith(w) for w in wanted):
            continue
        print(f"\n=== {d.name} ===", flush=True)
        r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=d)
        if r.returncode:
            failed.append(d.name)
    print("\nFAILED: " + ", ".join(failed) if failed else "\nAll project tests passed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
