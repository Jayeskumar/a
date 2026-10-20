"""MNIST-style preprocessing: crop, scale to fit, centre by centre of mass.

The same steps run in three places and must agree exactly:
  * here, on synthetic digits while building the dataset,
  * in the browser (static/app.js, ``preprocess``) on what the user draws,
  * here again when the API receives a raw bitmap instead of a 16x16 grid.

Steps (LeCun et al. normalised MNIST the same way, with a 20x20 box in 28x28):
  1. bounding box of pixels brighter than INK_THRESHOLD;
  2. scale the box so its longest side is FIT pixels, keeping the aspect ratio,
     with an exact area-averaging (box) filter so thin strokes are not lost;
  3. paste it into a GRID x GRID image so its centre of mass lands exactly on
     the centre of the grid (a fractional, area-preserving shift);
  4. divide by the brightest pixel so every drawing uses the full 0..1 range.

Images are flat row-major lists of floats in [0, 1], ink = high.
"""

import math

from .config import FIT, GRID, INK_THRESHOLD


def _round(v):
    """Round half up (matches JavaScript Math.round; Python's round() is banker's)."""
    return int(math.floor(v + 0.5))


def bounding_box(img, w, h, threshold=INK_THRESHOLD):
    """(x0, y0, x1, y1) inclusive box of ink pixels, or None for a blank image."""
    x0, y0, x1, y1 = w, h, -1, -1
    for y in range(h):
        row = img[y * w:(y + 1) * w]
        xs = [x for x, v in enumerate(row) if v > threshold]
        if xs:
            if y < y0:
                y0 = y
            y1 = y
            if xs[0] < x0:
                x0 = xs[0]
            if xs[-1] > x1:
                x1 = xs[-1]
    if x1 < 0:
        return None
    return x0, y0, x1, y1


def _weights(start, size, n_out, n_src):
    """For each output cell, the list of (source index, overlap length)."""
    step = size / n_out
    out = []
    for o in range(n_out):
        a = start + o * step
        b = a + step
        cells = []
        i = int(math.floor(a))
        while i < b and i < n_src:
            lo = max(a, i)
            hi = min(b, i + 1)
            if hi > lo and i >= 0:
                cells.append((i, hi - lo))
            i += 1
        out.append(cells)
    return out


def resample_area(img, w, h, box, ow, oh):
    """Area-average the source box (x0, y0, x1, y1 inclusive) down/up to ow x oh."""
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0 + 1, y1 - y0 + 1
    cols = _weights(x0, bw, ow, w)
    rows = _weights(y0, bh, oh, h)
    norm = (ow / bw) * (oh / bh)          # 1 / (area of one output cell in source px)
    out = [0.0] * (ow * oh)
    for oy, rws in enumerate(rows):
        for ox, cws in enumerate(cols):
            acc = 0.0
            for iy, wy in rws:
                base = iy * w
                for ix, wx in cws:
                    acc += img[base + ix] * wy * wx
            out[oy * ow + ox] = acc * norm
    return out


def centre_of_mass(img, w, h):
    total = sx = sy = 0.0
    for y in range(h):
        for x in range(w):
            v = img[y * w + x]
            if v:
                total += v
                sx += v * (x + 0.5)
                sy += v * (y + 0.5)
    if total <= 0:
        return w / 2.0, h / 2.0
    return sx / total, sy / total


def shift_splat(patch, pw, ph, offx, offy, grid):
    """Paste ``patch`` into a grid x grid image shifted by a *fractional* offset.

    Each patch pixel is a unit square; its value is split over the (up to) four
    grid cells the shifted square overlaps, in proportion to the overlap area.
    Mass is preserved and the centre of mass moves by exactly (offx, offy), so
    the result is centred to sub-pixel accuracy and does not jump by a whole
    pixel when the drawing changes slightly (an integer shift does).
    """
    ix, iy = int(math.floor(offx)), int(math.floor(offy))
    fx, fy = offx - ix, offy - iy
    wts = ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy))
    out = [0.0] * (grid * grid)
    for py in range(ph):
        for px in range(pw):
            v = patch[py * pw + px]
            if not v:
                continue
            for dx, dy, wt in wts:
                gx, gy = px + ix + dx, py + iy + dy
                if wt and 0 <= gx < grid and 0 <= gy < grid:
                    out[gy * grid + gx] += v * wt
    return out


def preprocess(img, w, h, grid=GRID, fit=FIT, info=False):
    """Turn any w x h ink image into the network's grid x grid input.

    With ``info=True`` also returns the mapping (box, scale, offset) so a caller
    can project grid cells back onto the original drawing (saliency overlay).
    """
    if len(img) != w * h:
        raise ValueError("image has %d values, expected %d" % (len(img), w * h))
    box = bounding_box(img, w, h)
    if box is None:
        out = [0.0] * (grid * grid)
        return (out, None) if info else out
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0 + 1, y1 - y0 + 1
    scale = fit / max(bw, bh)
    ow = max(1, _round(bw * scale))
    oh = max(1, _round(bh * scale))
    patch = resample_area(img, w, h, box, ow, oh)
    cx, cy = centre_of_mass(patch, ow, oh)
    offx = grid / 2.0 - cx
    offy = grid / 2.0 - cy
    out = shift_splat(patch, ow, oh, offx, offy, grid)
    peak = max(out)
    if peak > 0:
        inv = 1.0 / peak
        out = [v * inv for v in out]
    if info:
        return out, {"box": [x0, y0, x1, y1], "size": [ow, oh],
                     "scale_x": ow / bw, "scale_y": oh / bh, "offset": [round(offx, 4), round(offy, 4)]}
    return out
