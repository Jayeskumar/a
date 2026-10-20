"""Turn stroke templates into greyscale digit images.

Pipeline for one sample (all randomness comes from one seeded ``random.Random``):

  template strokes (unit box)
    -> densify (so later warps can bend straight lines)
    -> elastic warp: a smooth random displacement field, sum of two sinusoids
    -> hand tremor: tiny independent jitter per point
    -> affine: aspect-ratio scale, italic shear, rotation (about the digit centre)
    -> rasterise on a 40x40 canvas with an anti-aliased round pen
    -> preprocess (crop, fit 12 px, centre of mass in 16x16; see preprocess.py)
    -> optional mild Gaussian pixel noise
"""

import math
import random

from . import config as C
from .preprocess import preprocess
from .templates import CENTRE, strokes_for


def densify(stroke, step=0.035):
    """Insert points so that no segment is longer than ``step``."""
    if len(stroke) < 2:
        return list(stroke)
    out = [stroke[0]]
    for (x0, y0), (x1, y1) in zip(stroke, stroke[1:]):
        n = max(1, int(math.ceil(math.hypot(x1 - x0, y1 - y0) / step)))
        for i in range(1, n + 1):
            t = i / n
            out.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    return out


def random_style(rng):
    """All per-sample random parameters, drawn in a fixed order (determinism)."""
    waves = []
    for _ in range(2):                       # two sinusoids per axis
        waves.append((rng.uniform(1.5, 4.5), rng.uniform(1.5, 4.5), rng.uniform(0, 2 * math.pi),
                      rng.uniform(1.5, 4.5), rng.uniform(1.5, 4.5), rng.uniform(0, 2 * math.pi)))
    return {
        "waves": waves,
        "elastic": rng.uniform(0.3, 1.0) * C.ELASTIC_AMP,
        "rot": math.radians(rng.uniform(-C.ROTATE_DEG, C.ROTATE_DEG)),
        "shear": rng.uniform(-C.SHEAR, C.SHEAR),
        "sx": rng.uniform(*C.SCALE_X),
        "sy": rng.uniform(*C.SCALE_Y),
        "width": rng.uniform(*C.STROKE_WIDTH),
        "dx": rng.uniform(-3, 3),
        "dy": rng.uniform(-3, 3),
    }


def warp_strokes(strokes, style, rng, tremor=C.TREMOR):
    """Apply elastic warp, tremor and affine transform; result in unit-ish coords."""
    amp = style["elastic"]
    waves = style["waves"]
    cr, sr = math.cos(style["rot"]), math.sin(style["rot"])
    sh, sx, sy = style["shear"], style["sx"], style["sy"]
    cx0, cy0 = CENTRE
    out = []
    for stroke in strokes:
        pts = []
        for x, y in densify(stroke):
            ex = ey = 0.0
            for fx, fy, ph, gx, gy, qh in waves:
                ex += math.sin(fx * x + fy * y + ph)
                ey += math.sin(gx * x + gy * y + qh)
            x += amp * ex * 0.5 + rng.gauss(0, tremor)
            y += amp * ey * 0.5 + rng.gauss(0, tremor)
            # affine about the template centre: scale, shear (italic), rotate
            u, v = (x - cx0) * sx, (y - cy0) * sy
            u -= sh * v
            pts.append((u * cr - v * sr, u * sr + v * cr))
        out.append(pts)
    return out


def rasterise(strokes, width, size):
    """Anti-aliased round-pen rasteriser. ``strokes`` are in pixel coordinates.

    Each pixel takes the max coverage over all segments (no double-darkening
    where strokes cross), with a 1-pixel linear ramp at the pen edge.
    """
    img = [0.0] * (size * size)
    hw = width / 2.0
    for stroke in strokes:
        segs = list(zip(stroke, stroke[1:])) or [(stroke[0], stroke[0])]
        for (x0, y0), (x1, y1) in segs:
            dx, dy = x1 - x0, y1 - y0
            l2 = dx * dx + dy * dy
            ax = max(0, int(min(x0, x1) - hw - 1))
            bx = min(size - 1, int(max(x0, x1) + hw + 1))
            ay = max(0, int(min(y0, y1) - hw - 1))
            by = min(size - 1, int(max(y0, y1) + hw + 1))
            for py in range(ay, by + 1):
                cy = py + 0.5
                base = py * size
                for px in range(ax, bx + 1):
                    cx = px + 0.5
                    if l2 > 0:
                        t = ((cx - x0) * dx + (cy - y0) * dy) / l2
                        t = 0.0 if t < 0 else (1.0 if t > 1 else t)
                    else:
                        t = 0.0
                    ddx, ddy = cx - (x0 + t * dx), cy - (y0 + t * dy)
                    c = hw + 0.5 - math.sqrt(ddx * ddx + ddy * ddy)
                    if c > 0:
                        if c > 1:
                            c = 1.0
                        i = base + px
                        if c > img[i]:
                            img[i] = c
    return img


def to_canvas(strokes, size=C.RENDER_SIZE, digit_px=C.DIGIT_PX, dx=0.0, dy=0.0):
    """Map warped unit strokes onto a size x size pixel canvas."""
    k = float(digit_px)
    c = size / 2.0
    return [[(c + dx + x * k, c + dy + y * k) for x, y in s] for s in strokes]


def sloppy(strokes, rng, amount):
    """Sloppy pen: randomly cut short the start or end of strokes (gaps, short tails)."""
    out = []
    for s in strokes:
        pts = densify(s)
        n = len(pts)
        if n > 6:
            a = int(n * rng.uniform(0, amount)) if rng.random() < 0.5 else 0
            b = int(n * rng.uniform(0, amount)) if rng.random() < 0.5 else 0
            pts = pts[a:n - b] if n - a - b >= 4 else pts
        out.append(pts)
    return out


def render_digit(digit, rng, style_name="hand", noise=True):
    """One synthetic sample -> flat GRID*GRID list of floats in [0, 1]."""
    strokes = strokes_for(digit, rng, style_name)
    if C.STROKE_TRIM > 0:
        strokes = sloppy(strokes, rng, C.STROKE_TRIM)
    st = random_style(rng)
    warped = warp_strokes(strokes, st, rng)
    px = to_canvas(warped, dx=st["dx"], dy=st["dy"])
    width = st["width"] * C.DIGIT_PX * st["sy"]
    img = rasterise(px, width, C.RENDER_SIZE)
    grid = preprocess(img, C.RENDER_SIZE, C.RENDER_SIZE)
    if noise and rng.random() < C.NOISE_PROB:
        sigma = C.NOISE_SIGMA * rng.uniform(0.5, 1.0)
        grid = [min(1.0, max(0.0, v + rng.gauss(0, sigma))) for v in grid]
    return grid


def sample_rng(seed, index):
    """Independent, reproducible generator for sample ``index`` of dataset ``seed``."""
    return random.Random(seed * 1000003 + index)


def demo_strokes(digit, seed=0, style_name="hand"):
    """Pen strokes for the UI's animated 'Demo digit' (normalised to a 0..1 canvas).

    Uses the same templates and warps as training, but milder, so the demo
    shows what the network was trained on.
    """
    rng = random.Random(seed * 7919 + digit * 104729 + (1 if style_name == "lcd" else 0))
    strokes = strokes_for(digit, rng, style_name)
    st = random_style(rng)
    st["elastic"] *= 0.5
    st["rot"] *= 0.5
    st["shear"] *= 0.5
    warped = warp_strokes(strokes, st, rng, tremor=C.TREMOR * 0.5)
    xs = [x for s in warped for x, _ in s]
    ys = [y for s in warped for _, y in s]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    span = max(max(xs) - min(xs), max(ys) - min(ys)) or 1.0
    k = 0.64 / span                         # digit fills ~64% of the pad
    return [[(round(0.5 + (x - cx) * k, 4), round(0.5 + (y - cy) * k, 4)) for x, y in s]
            for s in warped]
