import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pulseguard import news2  # noqa: E402

NORMAL = {"rr": 16, "spo2": 98, "o2": False, "sbp": 124, "hr": 72, "acvpu": "A",
          "temp": 36.8, "scale": 1}


def obs(**kw):
    o = dict(NORMAL)
    o.update(kw)
    return o


class TestParameterBoundaries(unittest.TestCase):
    def check(self, fn, cases):
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(fn(value), expected)

    def test_respiration_rate(self):
        self.check(news2.score_respiration, [
            (0, 3), (5, 3), (8, 3), (9, 1), (10, 1), (11, 1), (12, 0), (16, 0), (20, 0),
            (21, 2), (22, 2), (24, 2), (25, 3), (40, 3), (80, 3)])

    def test_spo2_scale1(self):
        self.check(news2.score_spo2_scale1, [
            (40, 3), (85, 3), (91, 3), (92, 2), (93, 2), (94, 1), (95, 1), (96, 0), (100, 0)])

    def test_spo2_scale2_on_air(self):
        self.check(lambda v: news2.score_spo2_scale2(v, False), [
            (70, 3), (83, 3), (84, 2), (85, 2), (86, 1), (87, 1), (88, 0), (90, 0), (92, 0),
            (93, 0), (95, 0), (97, 0), (100, 0)])

    def test_spo2_scale2_on_oxygen(self):
        self.check(lambda v: news2.score_spo2_scale2(v, True), [
            (83, 3), (84, 2), (85, 2), (86, 1), (87, 1), (88, 0), (92, 0), (93, 1), (94, 1),
            (95, 2), (96, 2), (97, 3), (100, 3)])

    def test_air_or_oxygen(self):
        self.assertEqual(news2.score_air_oxygen(False), 0)
        self.assertEqual(news2.score_air_oxygen(True), 2)

    def test_systolic_bp(self):
        self.check(news2.score_systolic, [
            (40, 3), (90, 3), (91, 2), (100, 2), (101, 1), (110, 1), (111, 0), (150, 0),
            (219, 0), (220, 3), (300, 3)])

    def test_pulse(self):
        self.check(news2.score_pulse, [
            (20, 3), (40, 3), (41, 1), (50, 1), (51, 0), (90, 0), (91, 1), (110, 1),
            (111, 2), (130, 2), (131, 3), (200, 3)])

    def test_consciousness(self):
        self.assertEqual(news2.score_consciousness("A"), 0)
        for code in ("C", "V", "P", "U", "c", "u"):
            with self.subTest(code=code):
                self.assertEqual(news2.score_consciousness(code), 3)
        with self.assertRaises(ValueError):
            news2.score_consciousness("X")

    def test_temperature(self):
        self.check(news2.score_temperature, [
            (30.0, 3), (35.0, 3), (35.1, 1), (35.5, 1), (36.0, 1), (36.1, 0), (37.0, 0),
            (38.0, 0), (38.1, 1), (38.5, 1), (39.0, 1), (39.1, 2), (41.0, 2)])

    def test_rounding_to_chart_precision(self):
        # Temperature to 1 dp, half-up; integer parameters to whole numbers, half-up.
        self.assertEqual(news2.score_temperature(36.05), 0)   # -> 36.1
        self.assertEqual(news2.score_temperature(36.04), 1)   # -> 36.0
        self.assertEqual(news2.score_temperature(35.04), 3)   # -> 35.0
        self.assertEqual(news2.score_respiration(20.4), 0)    # -> 20
        self.assertEqual(news2.score_respiration(20.5), 2)    # -> 21
        self.assertEqual(news2.score_pulse(90.5), 1)          # -> 91
        self.assertEqual(news2.score_systolic(90.5), 2)       # -> 91
        self.assertEqual(news2.score_spo2_scale1(95.5), 0)    # -> 96


class TestAggregateAndBands(unittest.TestCase):
    def test_all_normal_is_zero_low_12_hourly(self):
        r = news2.calculate(NORMAL)
        self.assertEqual(r["total"], 0)
        self.assertEqual(r["band"], "low")
        self.assertEqual(r["frequency"], "Minimum 12-hourly")
        self.assertEqual(r["red_params"], [])
        self.assertEqual(len(r["parameters"]), 7)

    def test_low_band_1_to_4(self):
        for kw, total in [({"hr": 95}, 1), ({"rr": 22}, 2), ({"rr": 22, "hr": 95}, 3),
                          ({"rr": 22, "sbp": 95}, 4)]:
            with self.subTest(kw=kw):
                r = news2.calculate(obs(**kw))
                self.assertEqual(r["total"], total)
                self.assertEqual(r["band"], "low")
                self.assertEqual(r["frequency"], "Minimum 4–6-hourly")

    def test_single_parameter_3_is_low_medium(self):
        for kw in ({"rr": 26}, {"spo2": 90}, {"sbp": 88}, {"hr": 135}, {"acvpu": "C"},
                   {"temp": 34.8}, {"rr": 7}, {"hr": 38}, {"sbp": 225}):
            with self.subTest(kw=kw):
                r = news2.calculate(obs(**kw))
                self.assertEqual(r["total"], 3)
                self.assertEqual(r["band"], "low_medium")
                self.assertEqual(r["frequency"], "Minimum 1-hourly")
                self.assertEqual(len(r["red_params"]), 1)

    def test_red_plus_one_still_low_medium(self):
        r = news2.calculate(obs(rr=26, hr=95))
        self.assertEqual(r["total"], 4)
        self.assertEqual(r["band"], "low_medium")

    def test_medium_band_5_and_6(self):
        r5 = news2.calculate(obs(rr=22, sbp=95, hr=95))
        self.assertEqual((r5["total"], r5["band"]), (5, "medium"))
        r6 = news2.calculate(obs(rr=22, sbp=95, hr=115))
        self.assertEqual((r6["total"], r6["band"]), (6, "medium"))
        self.assertIn("urgent assessment", r6["response"])

    def test_aggregate_takes_precedence_over_red(self):
        r = news2.calculate(obs(rr=26, hr=115))  # 3 + 2 = 5 with a red parameter
        self.assertEqual(r["total"], 5)
        self.assertEqual(r["band"], "medium")
        self.assertEqual(r["red_params"], ["rr"])

    def test_high_band_7_plus(self):
        r = news2.calculate(obs(rr=22, sbp=95, hr=115, temp=38.5))
        self.assertEqual((r["total"], r["band"]), (7, "high"))
        self.assertEqual(r["frequency"], "Continuous monitoring of vital signs")
        self.assertIn("critical-care", r["response"])

    def test_maximum_score_is_20(self):
        r = news2.calculate(obs(rr=30, spo2=85, o2=True, sbp=80, hr=140, acvpu="U",
                                temp=34.0))
        self.assertEqual(r["total"], 20)
        r = news2.calculate(obs(rr=30, spo2=85, o2=True, sbp=80, hr=140, acvpu="U",
                                temp=40.0))
        self.assertEqual(r["total"], 19)  # fever scores at most 2
        self.assertEqual(r["band"], "high")

    def test_oxygen_adds_two(self):
        self.assertEqual(news2.calculate(obs(o2=True))["total"], 2)

    def test_band_for_direct(self):
        self.assertEqual(news2.band_for(0, False), "low")
        self.assertEqual(news2.band_for(4, False), "low")
        self.assertEqual(news2.band_for(3, True), "low_medium")
        self.assertEqual(news2.band_for(4, True), "low_medium")
        self.assertEqual(news2.band_for(5, False), "medium")
        self.assertEqual(news2.band_for(6, True), "medium")
        self.assertEqual(news2.band_for(7, False), "high")
        self.assertEqual(news2.band_for(20, True), "high")

    def test_breakdown_sums_to_total(self):
        r = news2.calculate(obs(rr=23, spo2=93, sbp=105, hr=112, temp=38.4))
        self.assertEqual(sum(p["points"] for p in r["parameters"]), r["total"])
        pts = {p["key"]: p["points"] for p in r["parameters"]}
        self.assertEqual(pts, {"rr": 2, "spo2": 2, "o2": 0, "sbp": 1, "hr": 2, "acvpu": 0,
                               "temp": 1})


class TestScale2(unittest.TestCase):
    def test_copd_target_range_scores_zero_on_scale2(self):
        copd = obs(spo2=89, scale=2)
        r2 = news2.calculate(copd)
        r1 = news2.calculate(dict(copd, scale=1))
        self.assertEqual(r2["total"], 0)
        self.assertEqual(r1["total"], 3)
        self.assertEqual(r1["band"], "low_medium")

    def test_scale2_over_oxygenation_penalised_only_on_oxygen(self):
        self.assertEqual(news2.calculate(obs(spo2=97, scale=2, o2=True))["total"], 3 + 2)
        self.assertEqual(news2.calculate(obs(spo2=97, scale=2, o2=False))["total"], 0)
        self.assertEqual(news2.calculate(obs(spo2=97, scale=1, o2=True))["total"], 2)

    def test_scale_label_in_breakdown(self):
        r = news2.calculate(obs(spo2=94, scale=2, o2=True))
        spo2 = [p for p in r["parameters"] if p["key"] == "spo2"][0]
        self.assertTrue(spo2["range"].startswith("Scale 2"))
        self.assertEqual(spo2["points"], 1)


class TestValidation(unittest.TestCase):
    def test_valid_and_coerced(self):
        o, errors = news2.validate({"rr": "18", "spo2": 97, "sbp": 120.4, "hr": 80,
                                    "temp": "37.25", "o2": "true", "acvpu": "c",
                                    "scale": "2"})
        self.assertEqual(errors, {})
        self.assertEqual(o["rr"], 18)
        self.assertEqual(o["sbp"], 120)
        self.assertEqual(o["temp"], 37.3)
        self.assertTrue(o["o2"])
        self.assertEqual(o["acvpu"], "C")
        self.assertEqual(o["scale"], 2)

    def test_missing_fields(self):
        o, errors = news2.validate({})
        self.assertIsNone(o)
        self.assertEqual(set(errors), {"rr", "spo2", "sbp", "hr", "temp"})

    def test_out_of_range_and_bad_types(self):
        _, errors = news2.validate({"rr": 120, "spo2": 101, "sbp": "abc", "hr": True,
                                    "temp": float("nan"), "acvpu": "Z", "scale": 3})
        self.assertEqual(set(errors), {"rr", "spo2", "sbp", "hr", "temp", "acvpu", "scale"})
        self.assertIn("between", errors["rr"])

    def test_range_edges_accepted(self):
        o, errors = news2.validate({"rr": 0, "spo2": 40, "sbp": 300, "hr": 250, "temp": 45})
        self.assertEqual(errors, {})
        self.assertEqual(news2.calculate(o)["band"], "high")

    def test_non_dict(self):
        o, errors = news2.validate([1, 2])
        self.assertIsNone(o)
        self.assertIn("_", errors)


class TestReference(unittest.TestCase):
    def test_reference_matches_scoring_functions(self):
        ref = news2.reference()
        self.assertEqual(len(ref["parameters"]), 8)
        self.assertEqual([b["band"] for b in ref["bands"]],
                         ["low", "low_medium", "medium", "high"])
        fns = {"rr": news2.score_respiration, "spo2_1": news2.score_spo2_scale1,
               "sbp": news2.score_systolic, "hr": news2.score_pulse,
               "temp": news2.score_temperature}
        for p in ref["parameters"]:
            if p["key"] not in fns:
                continue
            for row in p["rows"]:
                if row["upper"] is not None:
                    with self.subTest(param=p["key"], upper=row["upper"]):
                        self.assertEqual(fns[p["key"]](row["upper"]), row["points"])


if __name__ == "__main__":
    unittest.main()
