import unittest

import _path  # noqa: F401
from agrisky import indices


class TestIndices(unittest.TestCase):
    # hand-computed cell: green 0.10, red 0.05, red-edge 0.25, NIR 0.50
    G, R, E, N = 0.10, 0.05, 0.25, 0.50

    def test_ndvi_hand(self):
        # (0.50 - 0.05) / (0.50 + 0.05) = 0.45 / 0.55
        self.assertAlmostEqual(indices.ndvi(self.N, self.R), 0.45 / 0.55, places=12)
        self.assertAlmostEqual(indices.ndvi(self.N, self.R), 0.818182, places=6)

    def test_gndvi_hand(self):
        self.assertAlmostEqual(indices.gndvi(self.N, self.G), 0.40 / 0.60, places=12)

    def test_ndre_hand(self):
        self.assertAlmostEqual(indices.ndre(self.N, self.E), 0.25 / 0.75, places=12)

    def test_savi_hand(self):
        # 1.5 * 0.45 / (0.55 + 0.5) = 0.675 / 1.05
        self.assertAlmostEqual(indices.savi(self.N, self.R), 0.675 / 1.05, places=12)
        self.assertAlmostEqual(indices.savi(self.N, self.R, L=0.0), indices.ndvi(self.N, self.R))

    def test_ndwi_hand_and_sign(self):
        self.assertAlmostEqual(indices.ndwi(self.G, self.N), -0.40 / 0.60, places=12)
        # open water: more green than NIR -> positive
        self.assertGreater(indices.ndwi(0.07, 0.025), 0)

    def test_zero_signal(self):
        self.assertEqual(indices.ndvi(0.0, 0.0), 0.0)
        self.assertEqual(indices.normalized_difference(0, 0), 0.0)
        self.assertEqual(indices.savi(0.0, 0.0, L=0.0), 0.0)

    def test_soil_vs_vegetation(self):
        self.assertLess(indices.ndvi(0.24, 0.15), 0.35)      # bare soil
        self.assertGreater(indices.ndvi(0.52, 0.04), 0.8)    # dense leaf

    def test_compute_all_matches_cell(self):
        bands = {"green": [self.G, 0.07, 0.0], "red": [self.R, 0.05, 0.0],
                 "rededge": [self.E, 0.035, 0.0], "nir": [self.N, 0.025, 0.0]}
        out = indices.compute_all(bands)
        for i in range(3):
            cell = indices.cell_indices(bands["green"][i], bands["red"][i],
                                        bands["rededge"][i], bands["nir"][i])
            for k in indices.INDEX_NAMES:
                self.assertAlmostEqual(out[k][i], cell[k], places=12)
        self.assertEqual(out["ndvi"][2], 0.0)

    def test_bounded(self):
        for n in (0.01, 0.2, 0.6):
            for r in (0.01, 0.1, 0.3):
                self.assertTrue(-1 <= indices.ndvi(n, r) <= 1)
                self.assertTrue(-1.5 <= indices.savi(n, r) <= 1.5)


if __name__ == "__main__":
    unittest.main()
