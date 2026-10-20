import unittest

import _path  # noqa: F401
from agrisky import segment
from agrisky.report import rectangles


def grid(rows):
    return [int(c) for r in rows for c in r], len(rows[0]), len(rows)


class TestComponents(unittest.TestCase):
    def test_four_vs_eight_connectivity(self):
        g, w, h = grid(["100",
                        "010",
                        "001"])
        comp4, n4 = segment.connected_components(g, w, h, connectivity=4)
        # 3 diagonal ones are separate in 4-connectivity; the zeros split into 2 regions
        ones4 = {comp4[i] for i, v in enumerate(g) if v == 1}
        self.assertEqual(len(ones4), 3)
        self.assertEqual(n4, 5)
        regions8 = segment.mask_components([v == 1 for v in g], w, h, connectivity=8)
        self.assertEqual(len(regions8), 1)
        self.assertEqual(regions8[0], [0, 4, 8])

    def test_hand_labelled(self):
        g, w, h = grid(["1100",
                        "1102",
                        "0002"])
        comp, n = segment.connected_components(g, w, h)
        self.assertEqual(n, 3)
        self.assertEqual(comp[0], comp[1])
        self.assertEqual(comp[0], comp[5])
        self.assertEqual(comp[7], comp[11])
        self.assertNotEqual(comp[0], comp[7])
        self.assertEqual(comp[0], 0)               # raster-order ids

    def test_smooth_removes_speck_keeps_protected_line(self):
        g, w, h = grid(["00000",
                        "00100",
                        "00000",
                        "99999",
                        "00000"])
        out = segment.majority_smooth(g, w, h, passes=2, protected=(9,), min_votes=5)
        self.assertEqual(out[7], 0)                 # isolated 1 removed
        self.assertEqual(out[15:20], [9] * 5)       # protected bund line survives
        self.assertEqual(out.count(9), 5)           # and never spreads

    def test_merge_small(self):
        g, w, h = grid(["000000",
                        "001000",
                        "000000"])
        comp, n = segment.connected_components(g, w, h)
        self.assertEqual(n, 2)
        merged, m = segment.merge_small(comp, n, w, h, min_cells=2)
        self.assertEqual(m, 1)
        self.assertEqual(set(merged), {0})

    def test_merge_small_respects_groups(self):
        g, w, h = grid(["0000",
                        "0120",
                        "0000"])
        comp, n = segment.connected_components(g, w, h)
        first = {comp[i]: g[i] for i in range(len(g))}
        merged, m = segment.merge_small(comp, n, w, h, min_cells=3,
                                        group=lambda c: "crop" if first[c] != 2 else "soil")
        # the two specks are surrounded by crop -> both become crop zone 0
        self.assertEqual(m, 1)

    def test_merge_by_label(self):
        g, w, h = grid(["0011",
                        "0011",
                        "2222"])
        comp, n = segment.connected_components(g, w, h)
        labels = {comp[0]: "healthy", comp[2]: "healthy", comp[8]: "soil"}
        out, m, mapping = segment.merge_by_label(comp, n, [labels[c] for c in range(n)], w, h)
        self.assertEqual(m, 2)
        self.assertEqual(out[0], out[3])

    def test_dilate(self):
        w, h = 5, 5
        mask = [False] * 25
        mask[12] = True
        d1 = segment.dilate(mask, w, h, 1)
        self.assertEqual(sum(d1), 5)                # disc radius 1 = plus shape
        d2 = segment.dilate(mask, w, h, 2)
        self.assertEqual(sum(d2), 13)

    def test_rectangles_cover_exactly(self):
        cells = [0, 1, 2, 5, 6, 7, 11, 12, 20]
        w = 5
        rects = rectangles(cells, w)
        covered = set()
        for x0, x1, y0, y1 in rects:
            for y in range(y0, y1):
                for x in range(x0, x1):
                    i = y * w + x
                    self.assertNotIn(i, covered)
                    covered.add(i)
        self.assertEqual(covered, set(cells))


if __name__ == "__main__":
    unittest.main()
