"""Minimal QR Code (ISO/IEC 18004) encoder, pure Python, no libraries.

Scope: byte mode, error-correction level M, versions 1-10 (up to 213
bytes - plenty for a verification URL). Output is a module matrix or an
SVG string. Structure follows the well-known reference algorithm:
data bits -> pad -> split into blocks -> Reed-Solomon ECC over GF(256)
-> interleave -> zig-zag placement -> best of 8 masks by penalty score.
"""

# Error-correction level M only (format bits value for M is 0b00).
_ECL_FORMAT_BITS = 0
# Index = version (1..10); index 0 unused.
_ECC_PER_BLOCK_M = [None, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26]
_NUM_BLOCKS_M = [None, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5]
_ALIGN_POS = [None, [], [6, 18], [6, 22], [6, 26], [6, 30], [6, 34],
              [6, 22, 38], [6, 24, 42], [6, 26, 46], [6, 28, 50]]
MAX_VERSION = 10


def _raw_data_modules(ver):
    result = (16 * ver + 128) * ver + 64
    if ver >= 2:
        numalign = ver // 7 + 2
        result -= (25 * numalign - 10) * numalign - 55
        if ver >= 7:
            result -= 36
    return result


def _num_data_codewords(ver):
    return _raw_data_modules(ver) // 8 - _ECC_PER_BLOCK_M[ver] * _NUM_BLOCKS_M[ver]


# --- GF(256) Reed-Solomon --------------------------------------------------

def _gf_mul(x, y):
    z = 0
    for i in reversed(range(8)):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_divisor(degree):
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            result[j] = _gf_mul(result[j], root)
            if j + 1 < degree:
                result[j] ^= result[j + 1]
        root = _gf_mul(root, 0x02)
    return result


def _rs_remainder(data, divisor):
    result = [0] * len(divisor)
    for b in data:
        factor = b ^ result.pop(0)
        result.append(0)
        for i, coef in enumerate(divisor):
            result[i] ^= _gf_mul(coef, factor)
    return result


# --- Encoder --------------------------------------------------------------

def _choose_version(nbytes):
    for ver in range(1, MAX_VERSION + 1):
        ccbits = 8 if ver <= 9 else 16
        if 4 + ccbits + 8 * nbytes <= _num_data_codewords(ver) * 8:
            return ver
    raise ValueError("data too long for QR versions 1-%d" % MAX_VERSION)


def _data_codewords(data, ver):
    bits = []

    def put(val, n):
        for i in reversed(range(n)):
            bits.append((val >> i) & 1)

    put(0b0100, 4)                                   # byte mode
    put(len(data), 8 if ver <= 9 else 16)            # character count
    for b in data:
        put(b, 8)
    cap = _num_data_codewords(ver) * 8
    put(0, min(4, cap - len(bits)))                  # terminator
    put(0, (8 - len(bits) % 8) % 8)                  # byte align
    pad = 0xEC
    while len(bits) < cap:
        put(pad, 8)
        pad ^= 0xEC ^ 0x11
    return [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]


def _add_ecc_and_interleave(data, ver):
    numblocks = _NUM_BLOCKS_M[ver]
    blockecclen = _ECC_PER_BLOCK_M[ver]
    rawcodewords = _raw_data_modules(ver) // 8
    numshort = numblocks - rawcodewords % numblocks
    shortlen = rawcodewords // numblocks
    divisor = _rs_divisor(blockecclen)
    blocks = []
    k = 0
    for i in range(numblocks):
        n = shortlen - blockecclen + (0 if i < numshort else 1)
        dat = data[k:k + n]
        k += n
        ecc = _rs_remainder(dat, divisor)
        if i < numshort:
            dat = dat + [0]
        blocks.append(dat + ecc)
    result = []
    for i in range(len(blocks[0])):
        for j, blk in enumerate(blocks):
            if i != shortlen - blockecclen or j >= numshort:
                result.append(blk[i])
    return result


class _Matrix(object):
    def __init__(self, ver):
        self.ver = ver
        self.size = ver * 4 + 17
        self.mod = [[False] * self.size for _ in range(self.size)]
        self.fn = [[False] * self.size for _ in range(self.size)]

    def setf(self, x, y, dark):
        self.mod[y][x] = dark
        self.fn[y][x] = True

    def draw_function_patterns(self):
        s = self.size
        for i in range(s):
            self.setf(6, i, i % 2 == 0)
            self.setf(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (s - 4, 3), (3, s - 4)):
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < s and 0 <= y < s:
                        dist = max(abs(dx), abs(dy))
                        self.setf(x, y, dist not in (2, 4))
        pos = _ALIGN_POS[self.ver]
        n = len(pos)
        for i in range(n):
            for j in range(n):
                if (i == 0 and j == 0) or (i == 0 and j == n - 1) or (i == n - 1 and j == 0):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self.setf(pos[i] + dx, pos[j] + dy, max(abs(dx), abs(dy)) != 1)
        self.draw_format_bits(0)
        self.draw_version()

    def draw_format_bits(self, mask):
        data = _ECL_FORMAT_BITS << 3 | mask
        rem = data
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = (data << 10 | rem) ^ 0x5412
        bit = lambda i: ((bits >> i) & 1) != 0
        s = self.size
        for i in range(0, 6):
            self.setf(8, i, bit(i))
        self.setf(8, 7, bit(6))
        self.setf(8, 8, bit(7))
        self.setf(7, 8, bit(8))
        for i in range(9, 15):
            self.setf(14 - i, 8, bit(i))
        for i in range(0, 8):
            self.setf(s - 1 - i, 8, bit(i))
        for i in range(8, 15):
            self.setf(8, s - 15 + i, bit(i))
        self.setf(8, s - 8, True)                     # the "dark module"

    def draw_version(self):
        if self.ver < 7:
            return
        rem = self.ver
        for _ in range(12):
            rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
        bits = self.ver << 12 | rem
        for i in range(18):
            dark = ((bits >> i) & 1) != 0
            a = self.size - 11 + i % 3
            b = i // 3
            self.setf(a, b, dark)
            self.setf(b, a, dark)

    def draw_codewords(self, codewords):
        s = self.size
        i = 0
        total = len(codewords) * 8
        right = s - 1
        while right >= 1:
            if right == 6:
                right = 5
            for vert in range(s):
                for j in range(2):
                    x = right - j
                    upward = ((right + 1) & 2) == 0
                    y = (s - 1 - vert) if upward else vert
                    if not self.fn[y][x] and i < total:
                        self.mod[y][x] = ((codewords[i >> 3] >> (7 - (i & 7))) & 1) != 0
                        i += 1
            right -= 2

    def apply_mask(self, mask):
        f = _MASKS[mask]
        for y in range(self.size):
            for x in range(self.size):
                if not self.fn[y][x] and f(x, y):
                    self.mod[y][x] = not self.mod[y][x]


_MASKS = [
    lambda x, y: (x + y) % 2 == 0,
    lambda x, y: y % 2 == 0,
    lambda x, y: x % 3 == 0,
    lambda x, y: (x + y) % 3 == 0,
    lambda x, y: (x // 3 + y // 2) % 2 == 0,
    lambda x, y: x * y % 2 + x * y % 3 == 0,
    lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
    lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0,
]

_FINDER_A = [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0]
_FINDER_B = list(reversed(_FINDER_A))


def _penalty(m):
    s = len(m)
    score = 0
    lines = [row[:] for row in m] + [[m[y][x] for y in range(s)] for x in range(s)]
    for line in lines:
        run, prev = 0, None
        for v in line:
            if v == prev:
                run += 1
            else:
                if run >= 5:
                    score += 3 + run - 5
                run, prev = 1, v
        if run >= 5:
            score += 3 + run - 5
        padded = [0] * 4 + [1 if v else 0 for v in line] + [0] * 4
        for i in range(len(padded) - 10):
            w = padded[i:i + 11]
            if w == _FINDER_A or w == _FINDER_B:
                score += 40
    for y in range(s - 1):
        for x in range(s - 1):
            c = m[y][x]
            if c == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                score += 3
    dark = sum(1 for row in m for v in row if v)
    total = s * s
    k = (abs(dark * 20 - total * 10) + total - 1) // total - 1
    score += max(0, k) * 10
    return score


def encode(text, mask=None):
    """Return the QR module matrix (list of rows of bools) for text."""
    data = text.encode("utf-8") if isinstance(text, str) else bytes(text)
    ver = _choose_version(len(data))
    codewords = _add_ecc_and_interleave(_data_codewords(data, ver), ver)
    best = None
    masks = range(8) if mask is None else [mask]
    for mk in masks:
        mx = _Matrix(ver)
        mx.draw_function_patterns()
        mx.draw_codewords(codewords)
        mx.apply_mask(mk)
        mx.draw_format_bits(mk)
        pen = _penalty(mx.mod)
        if best is None or pen < best[0]:
            best = (pen, mx)
    return best[1].mod


def to_svg(text, module_px=4, border=4, dark="#0f172a", light="#ffffff"):
    """Render text as a standalone SVG QR code."""
    m = encode(text)
    n = len(m) + 2 * border
    parts = []
    for y, row in enumerate(m):
        for x, v in enumerate(row):
            if v:
                parts.append("M%d,%dh1v1h-1z" % (x + border, y + border))
    px = n * module_px
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" '
            'shape-rendering="crispEdges" role="img" aria-label="QR code">'
            '<rect width="100%%" height="100%%" fill="%s"/>'
            '<path d="%s" fill="%s"/></svg>') % (n, n, px, px, light, "".join(parts), dark)
