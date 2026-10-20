"""Print a QR code (SVG) for the given text, using CertChain's from-scratch encoder.

    python tools/qr_svg.py "https://github.com/..."   # used by build_decks.js
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "projects" / "04-certchain"))
from certchain import qr  # noqa: E402

if __name__ == "__main__":
    sys.stdout.write(qr.to_svg(sys.argv[1], module_px=10, border=2, dark="#0b1026", light="#ffffff"))
