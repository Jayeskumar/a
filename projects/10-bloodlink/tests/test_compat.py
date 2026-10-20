import unittest

import _helpers  # noqa: F401
from bloodlink import compat
from bloodlink.config import BLOOD_GROUPS

# Independent, hand-written truth tables (NOT derived from the implementation).
RED_CELL_DONORS = {
    "O-": {"O-"},
    "O+": {"O-", "O+"},
    "A-": {"O-", "A-"},
    "A+": {"O-", "O+", "A-", "A+"},
    "B-": {"O-", "B-"},
    "B+": {"O-", "O+", "B-", "B+"},
    "AB-": {"O-", "A-", "B-", "AB-"},
    "AB+": {"O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"},
}
PLASMA_DONORS_ABO = {"O": {"O", "A", "B", "AB"}, "A": {"A", "AB"}, "B": {"B", "AB"}, "AB": {"AB"}}


class RedCellMatrix(unittest.TestCase):
    def test_all_64_pairs(self):
        checked = 0
        for recipient in BLOOD_GROUPS:
            for donor in BLOOD_GROUPS:
                with self.subTest(donor=donor, recipient=recipient):
                    self.assertEqual(compat.red_cell_compatible(donor, recipient),
                                     donor in RED_CELL_DONORS[recipient])
                checked += 1
        self.assertEqual(checked, 64)

    def test_compatible_pair_count_is_27(self):
        n = sum(compat.red_cell_compatible(d, r) for d in BLOOD_GROUPS for r in BLOOD_GROUPS)
        self.assertEqual(n, 27)

    def test_universal_donor_and_recipient(self):
        self.assertEqual(compat.red_cell_recipients_of("O-"), BLOOD_GROUPS)
        self.assertEqual(set(compat.red_cell_donors_for("AB+")), set(BLOOD_GROUPS))
        self.assertEqual(compat.red_cell_donors_for("O-"), ["O-"])

    def test_matrix_shape(self):
        m = compat.matrix("red")
        self.assertEqual(sorted(m), sorted(BLOOD_GROUPS))
        for r in BLOOD_GROUPS:
            self.assertEqual({d for d, ok in m[r].items() if ok}, RED_CELL_DONORS[r])

    def test_exact_match_listed_first(self):
        for g in BLOOD_GROUPS:
            self.assertEqual(compat.red_cell_donors_for(g)[0], g)
        # A+ patient: substitutes come after the exact group, O- (scarcest) last
        self.assertEqual(compat.red_cell_donors_for("A+")[-1], "O-")

    def test_compat_score(self):
        self.assertEqual(compat.compat_score("A+", "A+"), 1.0)
        self.assertEqual(compat.compat_score("A-", "A+"), 0.75)
        self.assertEqual(compat.compat_score("O+", "A+"), 0.75)
        self.assertEqual(compat.compat_score("O-", "AB+"), 0.5)
        self.assertEqual(compat.compat_score("B+", "A+"), 0.0)
        self.assertEqual(compat.compat_score("A+", "A-"), 0.0)

    def test_reasons(self):
        self.assertIn("Exact", compat.compat_reason("B+", "B+"))
        self.assertIn("anti-A", compat.compat_reason("A+", "B+"))
        self.assertIn("anti-D", compat.compat_reason("O+", "O-"))
        self.assertIn("scarcer", compat.compat_reason("O-", "A+"))


class PlasmaMatrix(unittest.TestCase):
    def test_all_64_pairs(self):
        for recipient in BLOOD_GROUPS:
            for donor in BLOOD_GROUPS:
                with self.subTest(donor=donor, recipient=recipient):
                    expected = donor.rstrip("+-") in PLASMA_DONORS_ABO[recipient.rstrip("+-")]
                    self.assertEqual(compat.plasma_compatible(donor, recipient), expected)

    def test_ab_plasma_universal(self):
        for r in BLOOD_GROUPS:
            self.assertTrue(compat.plasma_compatible("AB-", r))
            self.assertTrue(compat.plasma_compatible("AB+", r))

    def test_plasma_differs_from_red_cells(self):
        self.assertTrue(compat.red_cell_compatible("O-", "A+"))
        self.assertFalse(compat.plasma_compatible("O-", "A+"))


class Parsing(unittest.TestCase):
    def test_spellings(self):
        self.assertEqual(compat.normalize("ab pos"), "AB+")
        self.assertEqual(compat.normalize("O neg"), "O-")
        self.assertEqual(compat.normalize(" b+ve "), "B+")
        self.assertEqual(compat.normalize("A−"), "A-")

    def test_invalid(self):
        for bad in ["C+", "A", "", "ABO+", None, 5]:
            with self.subTest(bad=bad):
                with self.assertRaises(compat.GroupError):
                    compat.normalize(bad)


if __name__ == "__main__":
    unittest.main()
