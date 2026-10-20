import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pulseguard import config, news2, trend  # noqa: E402
from pulseguard.alerts import PatientMonitor  # noqa: E402


def make_series(n, start, slope_per_h, noise=None, seed=0, scale=1, o2=False):
    """Synthetic readings every 15 min; start/slope are dicts per vital."""
    rng = random.Random(seed)
    out = []
    for i in range(n):
        t = i * 0.25
        r = {"t": t, "step": i, "o2": o2, "acvpu": "A", "scale": scale}
        for k in trend.VITALS:
            v = start[k] + slope_per_h.get(k, 0.0) * t
            if noise:
                v += rng.gauss(0, noise.get(k, 0.0))
            r[k] = round(v, 1) if k == "temp" else int(round(v))
        r["score"] = news2.calculate(r)["total"]
        out.append(r)
    return out


STABLE = {"rr": 16, "spo2": 97, "sbp": 125, "hr": 78, "temp": 37.0}


class TestOLS(unittest.TestCase):
    def test_exact_line(self):
        slope, intercept, r2 = trend.ols([0, 1, 2, 3], [2, 5, 8, 11])
        self.assertAlmostEqual(slope, 3.0)
        self.assertAlmostEqual(intercept, 2.0)
        self.assertAlmostEqual(r2, 1.0)

    def test_hand_computed_noisy(self):
        slope, intercept, r2 = trend.ols([0, 1, 2, 3], [1, 3, 2, 4])
        self.assertAlmostEqual(slope, 0.8)
        self.assertAlmostEqual(intercept, 1.3)
        self.assertAlmostEqual(r2, 0.64)

    def test_negative_slope(self):
        slope, _, r2 = trend.ols([0, 0.5, 1.0], [120, 110, 100])
        self.assertAlmostEqual(slope, -20.0)
        self.assertAlmostEqual(r2, 1.0)

    def test_constant_y(self):
        slope, intercept, r2 = trend.ols([0, 1, 2], [5, 5, 5])
        self.assertEqual((slope, intercept, r2), (0.0, 5.0, 0.0))

    def test_degenerate_x(self):
        slope, intercept, r2 = trend.ols([1, 1, 1], [1, 2, 3])
        self.assertEqual(slope, 0.0)
        self.assertEqual(r2, 0.0)

    def test_needs_two_points(self):
        with self.assertRaises(ValueError):
            trend.ols([1], [1])
        with self.assertRaises(ValueError):
            trend.ols([1, 2], [1])


class TestAnalyse(unittest.TestCase):
    def test_not_enough_data(self):
        r = trend.analyse(make_series(config.TREND_MIN_READINGS - 1, STABLE, {}))
        self.assertFalse(r["enough_data"])
        self.assertFalse(r["early_warning"])
        self.assertIn("Collecting", r["reason"])

    def test_empty(self):
        r = trend.analyse([])
        self.assertFalse(r["early_warning"])

    def test_flat_patient_is_stable(self):
        r = trend.analyse(make_series(16, STABLE, {}))
        self.assertTrue(r["enough_data"])
        self.assertFalse(r["early_warning"])
        self.assertEqual(r["reason"], "Stable")
        self.assertEqual(trend.direction(r), "stable")
        self.assertEqual(r["worsening"], [])

    def test_sepsis_like_trend_warns_before_threshold(self):
        start = {"rr": 17, "spo2": 97, "sbp": 122, "hr": 84, "temp": 37.3}
        slopes = {"rr": 1.2, "hr": 5.0, "sbp": -4.0, "temp": 0.2}
        series = make_series(12, start, slopes)
        self.assertLess(series[-1]["score"], config.NEWS2_MEDIUM_THRESHOLD)
        r = trend.analyse(series)
        self.assertTrue(r["early_warning"], r)
        self.assertGreaterEqual(r["projected_score"], config.NEWS2_MEDIUM_THRESHOLD)
        self.assertIn("hr", r["worsening"])
        self.assertIn("rr", r["worsening"])
        self.assertEqual(trend.direction(r), "rising")
        hr = [v for v in r["vitals"] if v["key"] == "hr"][0]
        self.assertAlmostEqual(hr["slope_per_h"], 5.0, delta=0.3)
        self.assertGreater(hr["r2"], 0.9)

    def test_improving_patient_does_not_warn(self):
        start = {"rr": 23, "spo2": 94, "sbp": 118, "hr": 108, "temp": 37.9}
        slopes = {"rr": -1.5, "hr": -6.0, "spo2": 0.8, "temp": -0.2}
        r = trend.analyse(make_series(12, start, slopes))
        self.assertFalse(r["early_warning"])
        self.assertEqual(r["worsening"], [])
        self.assertEqual(trend.direction(r), "falling")

    def test_no_early_warning_once_medium(self):
        start = {"rr": 22, "spo2": 94, "sbp": 105, "hr": 100, "temp": 38.2}
        slopes = {"rr": 1.0, "hr": 4.0, "sbp": -3.0}
        series = make_series(12, start, slopes)
        self.assertGreaterEqual(series[-1]["score"], config.NEWS2_MEDIUM_THRESHOLD)
        self.assertFalse(trend.analyse(series)["early_warning"])

    def test_noise_without_trend_rarely_significant(self):
        noise = {"rr": 0.8, "spo2": 0.6, "sbp": 4.0, "hr": 2.5, "temp": 0.06}
        warnings = 0
        for seed in range(40):
            r = trend.analyse(make_series(12, STABLE, {}, noise=noise, seed=seed))
            warnings += r["early_warning"]
        self.assertEqual(warnings, 0)

    def test_scale2_spo2_projection_uses_scale2(self):
        start = {"rr": 18, "spo2": 90, "sbp": 135, "hr": 85, "temp": 36.9}
        r = trend.analyse(make_series(12, start, {}, scale=2))
        spo2 = [v for v in r["vitals"] if v["key"] == "spo2"][0]
        self.assertEqual(spo2["points_now"], 0)  # would be 3 on Scale 1

    def test_only_one_worsening_vital_is_not_enough(self):
        start = dict(STABLE, hr=86)
        r = trend.analyse(make_series(12, start, {"hr": 8.0}))
        # Pulse alone climbing fast: projected may hit 2-3 points but not >=5.
        self.assertFalse(r["early_warning"])


class TestPatientMonitor(unittest.TestCase):
    def reading(self, i, **kw):
        r = {"t": i * 0.25, "step": i, "rr": 16, "spo2": 97, "sbp": 125, "hr": 78,
             "temp": 37.0, "o2": False, "acvpu": "A", "scale": 1}
        r.update(kw)
        return r

    def test_threshold_alert_once_with_hysteresis(self):
        m = PatientMonitor()
        events = []
        # 4 normal, then flicker 5,4,5,4 (medium/low) -> only one medium alert.
        seq = [{}] * 4 + [{"rr": 22, "sbp": 95, "hr": 95}, {"rr": 22, "sbp": 95}] * 2
        for i, kw in enumerate(seq):
            _, ev = m.ingest(self.reading(i, **kw))
            events += [e for e in ev if e["type"] == "threshold"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["band"], "medium")
        self.assertIn("Minimum 1-hourly", events[0]["frequency"])
        self.assertTrue(events[0]["contributors"])

    def test_escalation_to_higher_band_alerts_again(self):
        m = PatientMonitor()
        _, e1 = m.ingest(self.reading(0, rr=22, sbp=95, hr=95))
        _, e2 = m.ingest(self.reading(1, rr=22, sbp=95, hr=115, temp=38.5))
        self.assertEqual([e["band"] for e in e1], ["medium"])
        self.assertEqual([e["band"] for e in e2], ["high"])

    def test_rearm_after_sustained_recovery(self):
        m = PatientMonitor()
        bands = []
        seq = [{"rr": 26}] + [{}] * config.THRESHOLD_REARM_READINGS + [{"rr": 26}]
        for i, kw in enumerate(seq):
            _, ev = m.ingest(self.reading(i, **kw))
            bands += [e["band"] for e in ev]
        self.assertEqual(bands, ["low_medium", "low_medium"])

    def test_trend_alert_needs_confirmation_and_cooldown(self):
        m = PatientMonitor()
        start = {"rr": 17, "spo2": 97, "sbp": 122, "hr": 84, "temp": 37.3}
        series = make_series(14, start, {"rr": 1.2, "hr": 5.0, "sbp": -4.0, "temp": 0.2})
        first_ew, trend_events = None, []
        for r in series:
            _, ev = m.ingest({k: v for k, v in r.items() if k != "score"})
            if m.last_trend["early_warning"] and first_ew is None:
                first_ew = r["step"]
            trend_events += [e for e in ev if e["type"] == "trend"]
        self.assertIsNotNone(first_ew)
        self.assertEqual(len(trend_events), 1)  # cooldown prevents repeats
        self.assertEqual(trend_events[0]["step"],
                         first_ew + config.TREND_CONFIRM_READINGS - 1)
        self.assertIn("Early warning", trend_events[0]["message"])


if __name__ == "__main__":
    unittest.main()
