import random
import unittest

import helpers  # noqa: F401  (sets sys.path)
from campusvote.numtheory import egcd, gen_prime, is_mr_witness, is_probable_prime, modinv, small_primes


def trial_is_prime(n):
    if n < 2:
        return False
    i = 2
    while i * i <= n:
        if n % i == 0:
            return False
        i += 1
    return True


class TestEuclid(unittest.TestCase):
    def test_egcd_identity(self):
        rng = random.Random(1)
        for _ in range(500):
            a, b = rng.getrandbits(256), rng.getrandbits(200) + 1
            g, x, y = egcd(a, b)
            self.assertEqual(a * x + b * y, g)
            self.assertEqual(a % g, 0)
            self.assertEqual(b % g, 0)

    def test_modinv_matches_definition(self):
        rng = random.Random(2)
        m = (1 << 521) - 1  # Mersenne prime: every non-zero residue is invertible
        for _ in range(200):
            a = rng.randrange(1, m)
            inv = modinv(a, m)
            self.assertEqual(a * inv % m, 1)
            self.assertEqual(inv, pow(a, -1, m))  # cross-check with Python's built-in

    def test_modinv_rejects_non_units(self):
        with self.assertRaises(ValueError):
            modinv(6, 9)
        with self.assertRaises(ValueError):
            modinv(5, 1)


class TestMillerRabin(unittest.TestCase):
    def test_sieve(self):
        self.assertEqual(small_primes(50), [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47])

    def test_agrees_with_trial_division_below_20000(self):
        rng = random.Random(3)
        for n in range(-5, 20000):
            self.assertEqual(is_probable_prime(n, rng=rng), trial_is_prime(n), n)

    def test_random_odd_numbers_above_trial_bound(self):
        rng = random.Random(4)
        for _ in range(300):
            n = rng.randrange(4_000_000, 60_000_000) | 1
            self.assertEqual(is_probable_prime(n, rng=rng), trial_is_prime(n), n)

    def test_carmichael_numbers_are_composite(self):
        # Fermat liars for every coprime base - Miller-Rabin still catches them.
        for n in (561, 1105, 1729, 2465, 2821, 6601, 8911, 41041, 825265, 321197185, 5394826801,
                  232250619601, 9746347772161, 1436697831295441, 60977817398996785):
            self.assertFalse(is_probable_prime(n), n)

    def test_strong_pseudoprimes_need_more_than_one_base(self):
        for n in (2047, 3277, 4033, 4681, 8321, 3215031751):
            self.assertFalse(is_mr_witness(2, n), "%d is a strong pseudoprime to base 2" % n)
            self.assertFalse(is_probable_prime(n), n)
        # 3215031751 fools bases 2, 3, 5 and 7 at once
        for a in (2, 3, 5, 7):
            self.assertFalse(is_mr_witness(a, 3215031751))
        self.assertTrue(is_mr_witness(11, 3215031751))

    def test_large_known_primes_and_composites(self):
        for e in (89, 107, 127, 521, 607, 1279):
            self.assertTrue(is_probable_prime((1 << e) - 1), "M%d" % e)
        self.assertFalse(is_probable_prime((1 << 128) + 1))           # F7 = 59649589127497217 * ...
        self.assertFalse(is_probable_prime((1 << 67) - 1))            # Cole: 193707721 * 761838257287
        p, q = (1 << 127) - 1, (1 << 89) - 1
        self.assertFalse(is_probable_prime(p * q))

    def test_gen_prime(self):
        rng = random.Random(5)
        stats = {}
        for bits in (64, 256, 512):
            p = gen_prime(bits, rng, e=65537, stats=stats)
            self.assertEqual(p.bit_length(), bits)
            self.assertEqual(p >> (bits - 2), 3)       # top two bits set
            self.assertTrue(is_probable_prime(p))
            self.assertNotEqual((p - 1) % 65537, 0)
        self.assertGreater(stats["candidates"], 3)


if __name__ == "__main__":
    unittest.main()
