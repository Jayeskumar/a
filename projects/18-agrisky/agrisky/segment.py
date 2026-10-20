"""Raster helpers: spatial smoothing, connected-component labelling, zones, dilation.

Grids are flat lists indexed i = y * width + x.
"""
from collections import deque

from . import config


def neighbours4(i, w, h):
    x, y = i % w, i // w
    if x > 0:
        yield i - 1
    if x < w - 1:
        yield i + 1
    if y > 0:
        yield i - w
    if y < h - 1:
        yield i + w


_N8 = {}


def _table8(w, h):
    t = _N8.get((w, h))
    if t is None:
        t = []
        for i in range(w * h):
            x, y = i % w, i // w
            t.append(tuple((y + dy) * w + x + dx for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                           if (dx or dy) and 0 <= x + dx < w and 0 <= y + dy < h))
        _N8[(w, h)] = t
    return t


def neighbours8(i, w, h):
    return _table8(w, h)[i]


def majority_smooth(labels, w, h, passes=config.SMOOTH_PASSES, protected=(),
                    min_votes=config.SMOOTH_MIN_VOTES):
    """Plurality (mode) filter over the 3x3 window, applied `passes` times.

    Labels in `protected` (e.g. the bare-soil and open-water masks, which hold thin 1-cell
    bunds and a 2-cell channel) are never changed and never spread, so lines survive. Any other
    cell takes the most common non-protected label of its 3x3 window when that label has at
    least `min_votes` votes and beats the cell's own count.
    """
    protected = set(protected)
    cur = list(labels)
    for _ in range(passes):
        nxt = list(cur)
        changed = 0
        for i in range(len(cur)):
            own = cur[i]
            if own in protected:
                continue
            counts = {own: 1}
            for j in neighbours8(i, w, h):
                lj = cur[j]
                if lj in protected:
                    continue
                counts[lj] = counts.get(lj, 0) + 1
            lab, c = max(counts.items(), key=lambda kv: (kv[1], kv[0] == own, -kv[0]))
            if lab != own and c >= min_votes and c > counts[own]:
                nxt[i] = lab
                changed += 1
        cur = nxt
        if not changed:
            break
    return cur


def connected_components(labels, w, h, connectivity=4):
    """Label 4- (or 8-) connected regions of equal value. Returns (component_id grid, count).

    Component ids are assigned in raster-scan order of each region's first cell.
    """
    nb = neighbours4 if connectivity == 4 else neighbours8
    comp = [-1] * len(labels)
    count = 0
    for start in range(len(labels)):
        if comp[start] != -1:
            continue
        val = labels[start]
        comp[start] = count
        q = deque([start])
        while q:
            i = q.popleft()
            for j in nb(i, w, h):
                if comp[j] == -1 and labels[j] == val:
                    comp[j] = count
                    q.append(j)
        count += 1
    return comp, count


def mask_components(mask, w, h, connectivity=8):
    """Connected regions of True cells only. Returns list of cell-index lists."""
    nb = neighbours4 if connectivity == 4 else neighbours8
    seen = [False] * len(mask)
    regions = []
    for start in range(len(mask)):
        if not mask[start] or seen[start]:
            continue
        seen[start] = True
        q = deque([start])
        cells = []
        while q:
            i = q.popleft()
            cells.append(i)
            for j in nb(i, w, h):
                if mask[j] and not seen[j]:
                    seen[j] = True
                    q.append(j)
        regions.append(sorted(cells))
    return regions


def merge_small(comp, n_comp, w, h, min_cells=config.MIN_ZONE_CELLS, group=None):
    """Merge components smaller than min_cells into the neighbour sharing the longest border.

    `group` (optional) maps a component id to a group key; a component only merges into a
    neighbour of the same group (e.g. crop never merges into a bund). Returns (grid, count).
    """
    comp = list(comp)
    same = (lambda a, b: True) if group is None else (lambda a, b: group(a) == group(b))
    for _ in range(4):                       # a few rounds: merges can create new small ones
        sizes = {}
        for c in comp:
            sizes[c] = sizes.get(c, 0) + 1
        small = sorted((c for c, s in sizes.items() if s < min_cells), key=lambda c: sizes[c])
        if not small:
            break
        cells_of = {}
        for i, c in enumerate(comp):
            if sizes[c] < min_cells:
                cells_of.setdefault(c, []).append(i)
        merged = 0
        for c in small:
            if sizes.get(c, 0) == 0 or sizes[c] >= min_cells:
                continue
            border, other = {}, {}
            for i in cells_of.get(c, []):
                if comp[i] != c:
                    continue
                for j in neighbours4(i, w, h):
                    cj = comp[j]
                    if cj != c:
                        bucket = border if same(c, cj) else other
                        bucket[cj] = bucket.get(cj, 0) + 1
            if sizes[c] <= 2 and group is not None and (border or other):
                # a 1-2 cell speck (e.g. a noisy cell on a bund) joins whichever group
                # surrounds it most, so a bund line is not broken by one bright weed
                both = dict(other)
                both.update(border)
                votes = {}
                for cj, cnt in both.items():
                    votes[group(cj)] = votes.get(group(cj), 0) + cnt
                g_best = max(votes.items(), key=lambda kv: kv[1])[0]
                border = {cj: cnt for cj, cnt in both.items() if group(cj) == g_best}
            if not border:
                continue
            target = max(border.items(), key=lambda kv: (kv[1], sizes.get(kv[0], 0)))[0]
            for i in cells_of[c]:
                if comp[i] == c:
                    comp[i] = target
            cells_of.setdefault(target, []).extend(cells_of[c])
            sizes[target] = sizes.get(target, 0) + sizes[c]
            sizes[c] = 0
            merged += 1
        if not merged:
            break
    # renumber in raster order
    remap = {}
    out = [0] * len(comp)
    for i, c in enumerate(comp):
        if c not in remap:
            remap[c] = len(remap)
        out[i] = remap[c]
    return out, len(remap)


def dilate(mask, w, h, radius):
    """Binary dilation with a disc of the given radius (cells)."""
    if radius <= 0:
        return list(mask)
    offs = [(dx, dy) for dy in range(-radius, radius + 1) for dx in range(-radius, radius + 1)
            if dx * dx + dy * dy <= radius * radius]
    out = list(mask)
    for i, v in enumerate(mask):
        if not v:
            continue
        x, y = i % w, i // w
        for dx, dy in offs:
            xx, yy = x + dx, y + dy
            if 0 <= xx < w and 0 <= yy < h:
                out[yy * w + xx] = True
    return out


def zone_boundaries(comp, w, h):
    """Cells on the edge of their zone (for drawing outlines)."""
    out = [False] * len(comp)
    for i, c in enumerate(comp):
        for j in neighbours4(i, w, h):
            if comp[j] != c:
                out[i] = True
                break
    return out


def bbox(cells, w):
    xs = [i % w for i in cells]
    ys = [i // w for i in cells]
    return min(xs), min(ys), max(xs), max(ys)


def merge_by_label(comp, n_comp, zone_label, w, h):
    """Union adjacent components that carry the same label (union-find over zone adjacency).

    Returns (new component grid renumbered in raster order, count, mapping old->new).
    """
    parent = list(range(n_comp))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i, c in enumerate(comp):
        x = i % w
        for j in ((i + 1) if x < w - 1 else None, (i + w) if i + w < w * h else None):
            if j is None:
                continue
            d = comp[j]
            if d != c and zone_label[c] == zone_label[d]:
                ra, rb = find(c), find(d)
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)
    remap = {}
    out = [0] * len(comp)
    for i, c in enumerate(comp):
        r = find(c)
        if r not in remap:
            remap[r] = len(remap)
        out[i] = remap[r]
    mapping = {c: remap[find(c)] for c in range(n_comp)}
    return out, len(remap), mapping
