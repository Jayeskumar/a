"""Pure-Python Ed25519 (RFC 8032, section 5.1) built only on hashlib.sha512.

Points are kept in extended homogeneous coordinates (X, Y, Z, T) with
x = X/Z, y = Y/Z, x*y = T/Z, exactly as in RFC 8032 section 5.1.4.

This is a teaching / prototype implementation: it is correct (validated
against the RFC 8032 section 7.1 test vectors in tests/) but it is NOT
constant-time, so it should not be used where an attacker can measure
signing time on a shared machine. See REPORT.md, "limits".
"""

import hashlib
import os

# --- Curve constants (RFC 8032 section 5.1) -------------------------------
P = 2 ** 255 - 19                                   # field prime
L = 2 ** 252 + 27742317777372353535851937790883648493  # group order
D = (-121665 * pow(121666, P - 2, P)) % P           # curve constant d
SQRT_M1 = pow(2, (P - 1) // 4, P)                   # sqrt(-1) mod p

_GY = (4 * pow(5, P - 2, P)) % P


def _sha512(data):
    return hashlib.sha512(data).digest()


def _sha512_modq(data):
    return int.from_bytes(_sha512(data), "little") % L


def _inv(x):
    return pow(x, P - 2, P)


# --- Point arithmetic (extended coordinates) ------------------------------

def point_add(p, q):
    """RFC 8032 5.1.4 addition formula (a = -1)."""
    a = (p[1] - p[0]) * (q[1] - q[0]) % P
    b = (p[1] + p[0]) * (q[1] + q[0]) % P
    c = 2 * p[3] * q[3] * D % P
    d = 2 * p[2] * q[2] % P
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f % P, g * h % P, f * g % P, e * h % P)


def point_double(p):
    """Dedicated doubling (RFC 8032 5.1.4)."""
    a = p[0] * p[0] % P
    b = p[1] * p[1] % P
    c = 2 * p[2] * p[2] % P
    h = a + b
    e = h - (p[0] + p[1]) ** 2
    g = a - b
    f = c + g
    return (e * f % P, g * h % P, f * g % P, e * h % P)


IDENTITY = (0, 1, 1, 0)


def point_mul(s, p):
    """Scalar multiplication by double-and-add."""
    q = IDENTITY
    while s > 0:
        if s & 1:
            q = point_add(q, p)
        p = point_double(p)
        s >>= 1
    return q


def point_equal(p, q):
    # x1/z1 == x2/z2  <=>  x1*z2 == x2*z1
    if (p[0] * q[2] - q[0] * p[2]) % P != 0:
        return False
    if (p[1] * q[2] - q[1] * p[2]) % P != 0:
        return False
    return True


def _recover_x(y, sign):
    """RFC 8032 5.1.3 step 2-4: x from y and the sign bit, or None."""
    if y >= P:
        return None
    x2 = (y * y - 1) * _inv(D * y * y + 1) % P
    if x2 == 0:
        if sign:
            return None
        return 0
    x = pow(x2, (P + 3) // 8, P)
    if (x * x - x2) % P != 0:
        x = x * SQRT_M1 % P
    if (x * x - x2) % P != 0:
        return None
    if (x & 1) != sign:
        x = P - x
    return x


_GX = _recover_x(_GY, 0)
G = (_GX, _GY, 1, _GX * _GY % P)


def point_compress(p):
    zinv = _inv(p[2])
    x = p[0] * zinv % P
    y = p[1] * zinv % P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def point_decompress(s):
    if len(s) != 32:
        raise ValueError("invalid point length")
    y = int.from_bytes(s, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % P)


# --- Keys, signing, verification (RFC 8032 5.1.5 - 5.1.7) ----------------

def _expand_secret(secret):
    if len(secret) != 32:
        raise ValueError("Ed25519 secret key must be 32 bytes")
    h = _sha512(secret)
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8          # clear low 3 bits and bit 255
    a |= 1 << 254                # set bit 254
    return a, h[32:]


def public_key(secret):
    """32-byte public key A = [s]B for a 32-byte secret seed."""
    a, _ = _expand_secret(secret)
    return point_compress(point_mul(a, G))


def generate_secret():
    """Fresh 32-byte secret from the OS CSPRNG."""
    return os.urandom(32)


def sign(secret, msg):
    """Return the 64-byte signature R || S of msg."""
    a, prefix = _expand_secret(secret)
    A = point_compress(point_mul(a, G))
    r = _sha512_modq(prefix + msg)
    R = point_compress(point_mul(r, G))
    h = _sha512_modq(R + A + msg)
    s = (r + h * a) % L
    return R + int.to_bytes(s, 32, "little")


def verify(public, msg, signature):
    """True iff signature is a valid Ed25519 signature of msg under public."""
    if len(public) != 32 or len(signature) != 64:
        return False
    A = point_decompress(public)
    if A is None:
        return False
    Rs = signature[:32]
    R = point_decompress(Rs)
    if R is None:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= L:                       # reject non-canonical S (malleability)
        return False
    h = _sha512_modq(Rs + public + msg)
    sB = point_mul(s, G)
    hA = point_mul(h, A)
    # cofactorless check  [S]B == R + [k]A
    return point_equal(sB, point_add(R, hA))


class KeyPair(object):
    """Convenience wrapper holding a seed and its public key."""

    def __init__(self, secret):
        self.secret = bytes(secret)
        self.public = public_key(self.secret)

    @classmethod
    def from_hex(cls, hexseed):
        return cls(bytes.fromhex(hexseed))

    def sign(self, msg):
        return sign(self.secret, msg)

    def verify(self, msg, signature):
        return verify(self.public, msg, signature)
