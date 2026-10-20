import os
import random
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from neurocanvas import config as C  # noqa: E402
from neurocanvas.dataset import generate, load, quantise, save  # noqa: E402
from neurocanvas.preprocess import bounding_box, centre_of_mass, preprocess, resample_area  # noqa: E402
from neurocanvas.render import demo_strokes, rasterise, render_digit, sample_rng  # noqa: E402
from neurocanvas.templates import strokes_for  # noqa: E402

DATA = os.path.join(os.path.dirname(__file__), "..", "data", "digits.bin.gz")


def blob(w, h, x0, y0, bw, bh):
    img = [0.0] * (w * h)
    for y in range(y0, y0 + bh):
        for x in range(x0, x0 + bw):
            img[y * w + x] = 1.0
    return img


class Preprocessing(unittest.TestCase):
    def test_off_centre_blob_is_centred_by_mass(self):
        img = blob(64, 64, 2, 40, 10, 20)        # bottom-left corner
        out = preprocess(img, 64, 64)
        cx, cy = centre_of_mass(out, C.GRID, C.GRID)
        self.assertAlmostEqual(cx, C.GRID / 2, places=6)     # sub-pixel exact
        self.assertAlmostEqual(cy, C.GRID / 2, places=6)

    def test_lopsided_shape_centred_by_mass_not_box(self):
        img = blob(60, 60, 10, 10, 30, 6)        # a bar along the top ...
        for y in range(10, 50):                  # ... plus a thin stem on the left
            img[y * 60 + 10] = 1.0
        out = preprocess(img, 60, 60)
        cx, cy = centre_of_mass(out, C.GRID, C.GRID)
        self.assertLess(abs(cx - 8) + abs(cy - 8), 1.0)        # the long stem is clipped at the border
        box = bounding_box(out, C.GRID, C.GRID)
        self.assertNotEqual((box[1] + box[3]) / 2.0, 7.5)   # box centre is not the grid centre

    def test_longest_side_fits_and_aspect_kept(self):
        out, info = preprocess(blob(80, 80, 30, 10, 10, 40), 80, 80, info=True)
        self.assertEqual(info["size"], [3, 12])            # 10x40 -> 3x12
        x0, y0, x1, y1 = bounding_box(out, C.GRID, C.GRID)
        self.assertIn(y1 - y0 + 1, (12, 13))                # a fractional shift may straddle one more row
        self.assertIn(x1 - x0 + 1, (3, 4))

    def test_translation_invariant(self):
        a = preprocess(blob(50, 50, 3, 4, 12, 20), 50, 50)
        b = preprocess(blob(50, 50, 30, 25, 12, 20), 50, 50)
        for u, v in zip(a, b):
            self.assertAlmostEqual(u, v, places=9)

    def test_scale_roughly_invariant(self):
        r = random.Random(1)
        strokes = strokes_for(2, r)
        small = rasterise([[(10 + x * 25, 5 + y * 25) for x, y in s] for s in strokes], 3.0, 40)
        big = rasterise([[(20 + x * 50, 10 + y * 50) for x, y in s] for s in strokes], 6.0, 80)
        a, b = preprocess(small, 40, 40), preprocess(big, 80, 80)
        self.assertLess(sum(abs(u - v) for u, v in zip(a, b)) / len(a), 0.05)

    def test_fractional_shift_moves_mass_exactly(self):
        from neurocanvas.preprocess import shift_splat
        patch = [0.0, 1.0, 0.5, 0.25]                     # 2x2
        out = shift_splat(patch, 2, 2, 3.3, 4.7, 10)
        self.assertAlmostEqual(sum(out), sum(patch))
        cx0, cy0 = centre_of_mass(patch, 2, 2)
        cx1, cy1 = centre_of_mass(out, 10, 10)
        self.assertAlmostEqual(cx1 - cx0, 3.3)
        self.assertAlmostEqual(cy1 - cy0, 4.7)

    def test_peak_is_one_and_empty_is_zero(self):
        out = preprocess(blob(30, 30, 5, 5, 4, 9), 30, 30)
        self.assertAlmostEqual(max(out), 1.0)
        self.assertEqual(preprocess([0.0] * 900, 30, 30), [0.0] * 256)
        self.assertEqual(preprocess([0.05] * 900, 30, 30), [0.0] * 256)   # below the ink threshold

    def test_area_resample_conserves_mass(self):
        r = random.Random(2)
        img = [r.random() for _ in range(37 * 23)]
        box = (3, 2, 33, 20)
        out = resample_area(img, 37, 23, box, 12, 7)
        src = sum(img[y * 37 + x] for y in range(2, 21) for x in range(3, 34))
        cell_area = (31 / 12) * (19 / 7)
        self.assertAlmostEqual(sum(out) * cell_area, src, places=6)

    def test_bad_size_raises(self):
        with self.assertRaises(ValueError):
            preprocess([0.0] * 10, 4, 4)


class Rendering(unittest.TestCase):
    def test_same_seed_same_image(self):
        for d in range(10):
            a = render_digit(d, sample_rng(99, d))
            b = render_digit(d, sample_rng(99, d))
            self.assertEqual(a, b)

    def test_different_seed_different_image(self):
        a = render_digit(4, sample_rng(1, 0))
        b = render_digit(4, sample_rng(2, 0))
        self.assertNotEqual(a, b)

    def test_every_digit_and_style_renders_ink(self):
        r = random.Random(0)
        for style in ("hand", "lcd"):
            for d in range(10):
                img = render_digit(d, r, style)
                self.assertEqual(len(img), C.GRID * C.GRID)
                self.assertTrue(all(0.0 <= v <= 1.0 for v in img))
                self.assertGreater(sum(1 for v in img if v > 0.5), 8, (style, d))

    def test_bad_digit(self):
        with self.assertRaises(ValueError):
            strokes_for(10, random.Random(0))

    def test_demo_strokes_fit_the_pad(self):
        for d in range(10):
            pts = [p for s in demo_strokes(d, seed=3) for p in s]
            self.assertTrue(all(0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 for x, y in pts))
        self.assertEqual(demo_strokes(5, 8), demo_strokes(5, 8))

    def test_dataset_generation_is_byte_identical(self):
        a = generate(per_class=3, test_per_class=1, seed=7)
        b = generate(per_class=3, test_per_class=1, seed=7)
        self.assertEqual(a.train_b, b.train_b)
        self.assertEqual(len(a.train_y), 20)
        self.assertEqual(a.test_y, list(range(10)))
        with tempfile.TemporaryDirectory() as t:
            p1, p2 = os.path.join(t, "a.gz"), os.path.join(t, "b.gz")
            save(a, p1)
            save(b, p2)
            with open(p1, "rb") as f1, open(p2, "rb") as f2:
                self.assertEqual(f1.read(), f2.read())
            c = load(p1)
            self.assertEqual(c.train_b, a.train_b)
            self.assertEqual(c.test_y, a.test_y)

    def test_committed_dataset_matches_generator(self):
        ds = load(DATA)
        self.assertEqual(len(ds.train_y), (C.PER_CLASS - C.TEST_PER_CLASS) * 10)
        self.assertEqual(len(ds.test_y), C.TEST_PER_CLASS * 10)
        for idx in range(20):                    # first two images of every digit
            fresh = quantise(render_digit(idx % 10, sample_rng(C.DATA_SEED, idx)))
            self.assertEqual(ds.train_y[idx], idx % 10)
            # allow 1/255 of float drift across platforms' libm
            self.assertLessEqual(max(abs(a - b) for a, b in zip(fresh, ds.train_b[idx])), 1)


if __name__ == "__main__":
    unittest.main()
