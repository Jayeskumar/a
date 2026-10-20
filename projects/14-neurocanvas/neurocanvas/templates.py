"""Stroke templates for the digits 0-9, written the way people draw them.

A template is a function ``f(rng) -> strokes``. ``strokes`` is a list of pen
strokes and each stroke is a list of (x, y) points in a unit box: y runs from 0
(top) to 1 (bottom) and x from about 0 to 0.75. The rng picks a style (a 1 with
or without a flag, an open or closed 4, a 7 with a crossbar...) and wiggles
every control point, so no two calls give the same digit.

Angles for arcs are in degrees with y pointing down, so 0 = right, 90 = bottom,
180 = left and 270 (or -90) = top. Increasing angle runs clockwise on screen.

``seven_segment(d, rng)`` draws LCD-style digits. They are *not* in the training
set; the "Teach it" demo uses them to show a style the network has never seen.
"""

import math

CENTRE = (0.35, 0.5)   # rough centre of every template; affine transforms pivot here


def arc(cx, cy, rx, ry, a0, a1, step=12.0):
    """Points along an elliptical arc from angle a0 to a1 (degrees, either direction)."""
    n = max(2, int(abs(a1 - a0) / step) + 1)
    pts = []
    for i in range(n + 1):
        a = math.radians(a0 + (a1 - a0) * i / n)
        pts.append((cx + rx * math.cos(a), cy + ry * math.sin(a)))
    return pts


def bezier(p0, p1, p2, p3, n=12):
    """Points along a cubic Bezier curve."""
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1.0 - t
        a, b, c, d = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
        pts.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
                    a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return pts


def _u(r, lo, hi):
    return r.uniform(lo, hi)


def zero(r):
    rx, ry = _u(r, 0.22, 0.34), _u(r, 0.44, 0.5)
    start = _u(r, -125, -55)                       # pen starts near the top
    turn = -1 if r.random() < 0.7 else 1           # most people go anticlockwise
    end = start + turn * (360 + _u(r, -8, 28))     # small gap or overlap at the join
    return [arc(0.35, 0.5, rx, ry, start, end)]


def one(r):
    x, top, bot = 0.35, _u(r, 0.0, 0.03), _u(r, 0.97, 1.0)
    tilt = _u(r, -0.05, 0.05)
    stem = [(x + tilt, top), (x - tilt, bot)]
    style = r.random()
    if style < 0.4:
        return [stem]                              # plain stick
    flag = (x + tilt - _u(r, 0.12, 0.26), top + _u(r, 0.1, 0.26))
    strokes = [[flag] + stem]                      # flag + stem in one stroke
    if style > 0.86:                               # serif base
        w = _u(r, 0.16, 0.26)
        strokes.append([(x - tilt - w, bot), (x - tilt + w, bot)])
    return strokes


def two(r):
    cy, rx, ry = _u(r, 0.26, 0.32), _u(r, 0.24, 0.32), _u(r, 0.22, 0.28)
    hook = arc(0.35, cy, rx, ry, _u(r, 168, 208), _u(r, 375, 412))
    end = hook[-1]
    bl = (_u(r, 0.0, 0.08), _u(r, 0.95, 1.0))
    br = (_u(r, 0.62, 0.78), _u(r, 0.94, 1.02))
    k = _u(r, 0.0, 0.25)                           # 0 = straight neck, larger = S-shaped
    neck = bezier(end, (end[0] - 0.03, end[1] + 0.12 + k), (bl[0] + 0.12 + k, bl[1] - 0.18), bl, 10)
    return [hook + neck[1:] + [br]]


def three(r):
    if r.random() < 0.8:                           # round-topped 3: two bowls
        mid = _u(r, 0.44, 0.53)
        upper = arc(0.33, mid / 2, _u(r, 0.2, 0.28), mid / 2, _u(r, 185, 222), 450 + _u(r, 0, 25))
    else:                                          # flat-topped 3
        mid = _u(r, 0.4, 0.48)
        upper = [(_u(r, 0.04, 0.12), 0.0), (_u(r, 0.6, 0.7), 0.0), (_u(r, 0.25, 0.35), mid)]
    ry = (1.0 - mid) / 2
    lower = arc(0.33, mid + ry, _u(r, 0.26, 0.34), ry, _u(r, 240, 268), _u(r, 500, 545))
    return [upper + lower]


def four(r):
    xv, yb = _u(r, 0.5, 0.6), _u(r, 0.58, 0.7)
    tip = (xv + _u(r, -0.05, 0.02), 0.0)
    if r.random() < 0.55:                          # closed (triangle) 4
        s1 = [tip, (_u(r, 0.0, 0.06), yb), (_u(r, 0.7, 0.8), yb + _u(r, -0.03, 0.03))]
        s2 = [(tip[0], _u(r, 0.0, 0.08)), (xv + _u(r, -0.03, 0.03), 1.0)]
    else:                                          # open 4
        s1 = [(_u(r, 0.06, 0.2), 0.0), (_u(r, 0.02, 0.1), yb), (_u(r, 0.7, 0.8), yb + _u(r, -0.03, 0.03))]
        s2 = [(xv, _u(r, 0.12, 0.35)), (xv + _u(r, -0.03, 0.03), 1.0)]
    return [s1, s2]


def five(r):
    xl, yb = _u(r, 0.06, 0.16), _u(r, 0.36, 0.48)
    ry = (1.0 - yb) / 2 + 0.02
    belly = arc(0.33, 1.0 - ry, _u(r, 0.26, 0.33), ry, _u(r, 205, 228), _u(r, 478, 515))
    stem = [(xl + _u(r, 0.0, 0.04), 0.0)] + belly
    bar = [(xl + _u(r, 0.0, 0.03), 0.0), (_u(r, 0.58, 0.72), _u(r, -0.03, 0.03))]
    return [stem, bar]


def six(r):
    cy = _u(r, 0.64, 0.72)
    rx, ry = _u(r, 0.24, 0.31), 1.0 - cy
    left = (0.36 - rx, cy)
    start = (_u(r, 0.48, 0.66), _u(r, 0.0, 0.04))
    stem = bezier(start, (start[0] - _u(r, 0.18, 0.3), start[1] + 0.04),
                  (left[0] - _u(r, 0.0, 0.05), cy - _u(r, 0.25, 0.4)), left, 10)
    loop = arc(0.36, cy, rx, ry, 180, 180 - _u(r, 320, 372))
    return [stem + loop[1:]]


def seven(r):
    tl = (_u(r, 0.0, 0.08), _u(r, 0.0, 0.06))
    tr = (_u(r, 0.62, 0.76), _u(r, -0.02, 0.02))
    bot = (_u(r, 0.18, 0.42), 1.0)
    if r.random() < 0.3:                           # curved stem
        stem = bezier(tr, (tr[0] - 0.08, 0.35), (bot[0] + 0.05, 0.7), bot, 10)
    else:
        stem = [tr, bot]
    strokes = [[tl] + stem]
    if r.random() < 0.22:                          # continental crossbar
        y = _u(r, 0.45, 0.55)
        x = tr[0] + (bot[0] - tr[0]) * y
        strokes.append([(x - _u(r, 0.14, 0.22), y), (x + _u(r, 0.12, 0.2), y)])
    return strokes


def eight(r):
    if r.random() < 0.6:                           # one-stroke figure of eight
        cy, h = _u(r, 0.48, 0.52), 0.5
        au, al = _u(r, 0.2, 0.27), _u(r, 0.25, 0.33)
        pts = []
        n = 40
        t0, sweep = _u(r, -0.3, 0.3), 2 * math.pi + _u(r, -0.1, 0.3)
        for i in range(n + 1):
            t = t0 + sweep * i / n
            a = au if math.cos(t) > 0 else al      # upper lobe narrower than the lower
            pts.append((0.35 + a * math.sin(2 * t), cy - h * math.cos(t)))
        return [pts]
    mid = _u(r, 0.42, 0.5)                         # two stacked loops ("snowman")
    up = arc(0.35, mid / 2, _u(r, 0.18, 0.25), mid / 2, -90, 270)
    lo = arc(0.35, mid + (1 - mid) / 2, _u(r, 0.24, 0.32), (1 - mid) / 2, -90, 270)
    return [up, lo]


def nine(r):
    cy = _u(r, 0.24, 0.32)
    rx, ry = _u(r, 0.23, 0.3), cy
    a0 = _u(r, -15, 15)
    loop = arc(0.35, cy, rx, ry, a0, a0 - _u(r, 340, 372))   # anticlockwise from the right
    right = (0.35 + rx, cy)
    if r.random() < 0.6:
        stem = [right, (right[0] - _u(r, -0.02, 0.1), 1.0)]
    else:
        stem = bezier(right, (right[0] + 0.02, 0.65), (right[0] - 0.08, 0.95),
                      (0.35 - _u(r, 0.05, 0.2), 1.0), 10)
    return [loop + stem]


DIGITS = [zero, one, two, three, four, five, six, seven, eight, nine]

# --- seven-segment ("LCD") digits: an unseen style for the Teach-it demo ------
_SEG_LIT = {
    0: "abcdef", 1: "bc", 2: "abged", 3: "abgcd", 4: "fgbc",
    5: "afgcd", 6: "afgedc", 7: "abc", 8: "abcdefg", 9: "abcdfg",
}
_SEG_ENDS = {
    "a": ((0.05, 0.0), (0.62, 0.0)), "b": ((0.62, 0.0), (0.62, 0.5)),
    "c": ((0.62, 0.5), (0.62, 1.0)), "d": ((0.62, 1.0), (0.05, 1.0)),
    "e": ((0.05, 1.0), (0.05, 0.5)), "f": ((0.05, 0.5), (0.05, 0.0)),
    "g": ((0.05, 0.5), (0.62, 0.5)),
}


def seven_segment(d, r):
    """An LCD-style digit: straight segments with square corners."""
    strokes = []
    for s in _SEG_LIT[d]:
        (x0, y0), (x1, y1) = _SEG_ENDS[s]
        j = lambda: _u(r, -0.015, 0.015)   # noqa: E731 - tiny tremor per endpoint
        strokes.append([(x0 + j(), y0 + j()), (x1 + j(), y1 + j())])
    return strokes


def strokes_for(digit, rng, style="hand"):
    if not 0 <= digit <= 9:
        raise ValueError("digit must be 0-9")
    if style == "lcd":
        return seven_segment(digit, rng)
    return DIGITS[digit](rng)
