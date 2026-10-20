import os
import re
import unittest

import _path  # noqa: F401
from krishimitra import config, i18n

TAMIL = re.compile(u"[஀-௿]")


class TestI18n(unittest.TestCase):
    def test_every_backend_string_has_tamil(self):
        for key, (en, ta) in i18n.TEXT.items():
            self.assertTrue(en.strip(), key)
            self.assertTrue(TAMIL.search(ta), key)
            # same placeholders in both languages
            self.assertEqual(sorted(re.findall(r"{(\w+)}", en)), sorted(re.findall(r"{(\w+)}", ta)), key)

    def test_crop_soil_method_names(self):
        for c in config.CROPS:
            self.assertTrue(TAMIL.search(config.CROP_NAMES[c]["ta"]), c)
        for d in list(config.SOIL_TYPES.values()) + list(config.IRRIGATION_METHODS.values()):
            self.assertTrue(TAMIL.search(d["ta"]))
        for p in config.PRESETS:
            self.assertTrue(TAMIL.search(p["name"]["ta"]))

    def test_render(self):
        out = i18n.t("irr_summary", n=2, date="2026-10-20", mm=12.5, litres=5000, week_litres=9000)
        self.assertIn("20 Oct", out["en"])
        self.assertIn("அக்டோபர் 20", out["ta"])
        out = i18n.t("advice_intro", crop="rice")
        self.assertIn("நெல்", out["ta"])
        self.assertIn("Rice", out["en"])

    def test_indian_grouping(self):
        self.assertEqual(i18n.indian_int(352829), "3,52,829")
        self.assertEqual(i18n.indian_int(12345678), "1,23,45,678")
        self.assertEqual(i18n.indian_int(999), "999")
        self.assertEqual(i18n.indian_int(1000), "1,000")

    def test_frontend_dictionaries_have_same_keys(self):
        path = os.path.join(_path.ROOT, "static", "i18n.js")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        en_block = src[src.index("en: {"):src.index("ta: {")]
        ta_block = src[src.index("ta: {"):]
        key_re = re.compile(r"(?:^|[\s,{])([A-Za-z_][A-Za-z0-9_]*):\s*[\"\[]", re.M)
        en_keys = set(key_re.findall(en_block)) - {"en"}
        ta_keys = set(key_re.findall(ta_block)) - {"ta"}
        self.assertEqual(en_keys, ta_keys)
        self.assertGreater(len(en_keys), 60)
        # every data-i18n key used in the HTML exists
        with open(os.path.join(_path.ROOT, "static", "index.html"), encoding="utf-8") as fh:
            html = fh.read()
        for k in re.findall(r'data-i18n="(\w+)"', html):
            self.assertIn(k, en_keys)


if __name__ == "__main__":
    unittest.main()
