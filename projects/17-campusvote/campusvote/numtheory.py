"""Number theory from scratch: extended Euclid, modular inverse, Miller-Rabin, prime generation.

Only Python's built-in arbitrary-precision ``int`` and three-argument ``pow`` are used.
"""

import secrets

from . import config

_SYSRAND = secrets.SystemRandom()


def egcd(a, b):
    """Iterative extended Euclid. Returns (g, x, y) with a*x + b*y == g == gcd(a, b)."""
    old_r, r = a, b
    old_x, x = 1, 0
    old_y, y = 0, 1
    while r:
        q = old_r // r
        old_r, r = r, old_r - q * r
        old_x, x = x, old_x - q * x
        old_y, y = y, old_y - q * y
    if old_r < 0:
        old_r, old_x, old_y = -old_r, -old_x, -old_y
    return old_r, old_x, old_y


def gcd(a, b):
    while b:
        a, b = b, a % b
    return abs(a)


def modinv(a, m):
    """Inverse of a modulo m (m > 1). Raises ValueError if gcd(a, m) != 1."""
    if m <= 1:
        raise ValueError("modulus must be > 1")
    g, x, _ = egcd(a % m, m)
    if g != 1:
        raise ValueError("%d has no inverse modulo m (gcd=%d)" % (a % m, g))
    return x % m


def small_primes(bound):
    """Sieve of Eratosthenes: all primes < bound."""
    sieve = bytearray([1]) * bound
    sieve[0:2] = b"\x00\x00"
    for i in range(2, int(bound ** 0.5) + 1):
        if sieve[i]:
            sieve[i * i::i] = bytearray(len(sieve[i * i::i]))
    return [i for i, v in enumerate(sieve) if v]


SMALL_PRIMES = small_primes(config.TRIAL_DIVISION_BOUND)


def _decompose(n):
    """n - 1 = d * 2^s with d odd."""
    d, s = n - 1, 0
    while d % 2 == 0:
        d //= 2
        s += 1
    return d, s


def is_mr_witness(a, n):
    """True if base a proves the odd number n > 3 composite (a strong-probable-prime test)."""
    d, s = _decompose(n)
    x = pow(a, d, n)
    if x == 1 or x == n - 1:
        return False
    for _ in range(s - 1):
        x = x * x % n
        if x == n - 1:
            return False
    return True


def is_probable_prime(n, rounds=None, rng=None):
    """Miller-Rabin with random bases after trial division.

    A composite survives one random base with probability <= 1/4, so ``rounds`` rounds
    give error <= 4^-rounds (Rabin 1980), even for adversarial n such as Carmichael numbers.
    """
    if n < 2:
        return False
    for p in SMALL_PRIMES:
        if n == p:
            return True
        if n % p == 0:
            return False
    if n < SMALL_PRIMES[-1] ** 2:
        return True  # no prime factor below sqrt(n)
    rng = rng or _SYSRAND
    rounds = config.MR_ROUNDS if rounds is None else rounds
    for _ in range(rounds):
        a = 2 + rng.randrange(n - 3)  # uniform in [2, n-2]
        if is_mr_witness(a, n):
            return False
    return True


def gen_prime(bits, rng=None, e=None, stats=None):
    """Random prime of exactly ``bits`` bits with the top two bits set (so p*q has 2*bits bits).

    If ``e`` is given, also require gcd(e, p-1) == 1 so e is invertible mod phi.
    ``stats`` (a dict) counts candidates tried, for the report.
    """
    if bits < 16:
        raise ValueError("bits too small")
    rng = rng or _SYSRAND
    while True:
        c = rng.getrandbits(bits) | (3 << (bits - 2)) | 1
        if stats is not None:
            stats["candidates"] = stats.get("candidates", 0) + 1
        if e is not None and gcd(e, c - 1) != 1:
            continue
        if is_probable_prime(c, rng=rng):
            return c
