import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pulseguard import config, news2, simulator  # noqa: E402
from pulseguard.handover import last_change  # noqa: E402
from pulseguard.ward import Ward  # noqa: E402


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class TestSimulator(unittest.TestCase):
    def test_deterministic(self):
        a = simulator.generate_ward(seed=7)
        b = simulator.generate_ward(seed=7)
        c = simulator.generate_ward(seed=8)
        self.assertEqual(a, b)
        self.assertNotEqual(a[0]["readings"], c[0]["readings"])

    def test_shape(self):
        ward = simulator.generate_ward()
        self.assertEqual(len(ward), 12)
        for w in ward:
            self.assertEqual(len(w["readings"]), config.SCENARIO_STEPS + 1)
        kinds = [w["profile"]["kind"] for w in ward]
        self.assertEqual(kinds.count("deteriorating"), 3)
        self.assertEqual([w["profile"]["scale"] for w in ward].count(2), 1)

    def test_readings_valid_and_scoreable(self):
        for w in simulator.generate_ward(seed=3, jitter=True):
            for r in w["readings"]:
                obs, errors = news2.validate(r)
                self.assertEqual(errors, {}, r)
                news2.calculate(obs)

    def test_deteriorating_end_high_stable_never_medium(self):
        for w in simulator.generate_ward():
            scores = [news2.calculate(r)["total"] for r in w["readings"]]
            if w["profile"]["kind"] == "deteriorating":
                self.assertGreaterEqual(scores[-1], config.NEWS2_HIGH_THRESHOLD,
                                        w["profile"]["name"])
                onset_step = int(w["profile"]["onset_h"] * config.STEPS_PER_HOUR)
                self.assertLess(max(scores[:onset_step + 1]), config.NEWS2_MEDIUM_THRESHOLD)
            elif w["profile"]["kind"] == "stable":
                self.assertLess(max(scores), config.NEWS2_MEDIUM_THRESHOLD,
                                w["profile"]["name"])

    def test_copd_patient_scale2_low(self):
        copd = [w for w in simulator.generate_ward() if w["profile"]["scale"] == 2][0]
        spo2 = [r["spo2"] for r in copd["readings"]]
        self.assertTrue(85 <= sum(spo2) / len(spo2) <= 92)

    def test_clock_label(self):
        self.assertEqual(simulator.clock_label(0), "06:00")
        self.assertEqual(simulator.clock_label(2.25), "08:15")
        self.assertEqual(simulator.clock_label(18), "00:00 (+1d)")


class TestWard(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.ward = Ward(clock=self.clock)

    def test_reset_state(self):
        s = self.ward.summary()
        self.assertEqual(s["clock"]["step"], config.RESET_STEP)
        self.assertFalse(s["clock"]["playing"])
        self.assertEqual(len(s["patients"]), 12)
        # pre-roll alerts are auto-acknowledged
        self.assertTrue(all(a["acknowledged"] for a in s["alerts"]))

    def test_sorted_by_acuity(self):
        self.ward.control("skip", hours=12)
        tiles = self.ward.summary()["patients"]
        keys = [(-t["band_rank"], -int(t["trend"]["early_warning"]), -t["score"], t["bed"])
                for t in tiles]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(tiles[0]["band"], "high")

    def test_play_uses_server_clock_and_speed(self):
        self.ward.control("speed", speed=4)
        self.ward.control("play")
        self.clock.now += 2.0  # 2 s at 4x = 8 steps
        s = self.ward.summary()
        self.assertEqual(s["clock"]["step"], config.RESET_STEP + 8)
        self.ward.control("pause")
        self.clock.now += 10
        self.assertEqual(self.ward.summary()["clock"]["step"], config.RESET_STEP + 8)

    def test_auto_pause_at_end(self):
        self.ward.control("speed", speed=8)
        self.ward.control("play")
        self.clock.now += 1000
        c = self.ward.summary()["clock"]
        self.assertEqual(c["step"], config.SCENARIO_STEPS)
        self.assertFalse(c["playing"])
        self.assertTrue(c["finished"])
        with self.assertRaises(ValueError):
            self.ward.control("play")

    def test_bad_controls(self):
        for action, kw in [("speed", {"speed": 3}), ("speed", {"speed": "x"}),
                           ("skip", {"hours": -1}), ("skip", {"hours": "abc"}),
                           ("nope", {})]:
            with self.subTest(action=action, kw=kw):
                with self.assertRaises(ValueError):
                    self.ward.control(action, **kw)

    def test_step_and_demo(self):
        self.ward.control("step")
        self.assertEqual(self.ward.step, config.RESET_STEP + 1)
        c = self.ward.control("demo")
        self.assertTrue(c["playing"])
        self.assertEqual(c["speed"], 1)
        self.assertEqual(c["step"], config.RESET_STEP)

    def test_alerts_and_ack(self):
        self.ward.control("skip", hours=10)
        unacked = self.ward.alert_list(unacked_only=True)
        self.assertTrue(unacked)
        types = {a["type"] for a in unacked}
        self.assertIn("trend", types)
        self.assertIn("threshold", types)
        a = self.ward.acknowledge(unacked[0]["id"], by="Sr. Meena")
        self.assertTrue(a["acknowledged"])
        self.assertEqual(a["ack_by"], "Sr. Meena")
        self.assertIsNone(self.ward.acknowledge(99999))

    def test_trend_alert_precedes_threshold_for_sepsis_patient(self):
        self.ward.control("skip", hours=12)
        alerts = [a for a in self.ward.alerts if a["patient_id"] == "P01"]
        trend_t = min(a["t"] for a in alerts if a["type"] == "trend")
        thr_t = min(a["t"] for a in alerts if a["type"] == "threshold"
                    and a["band"] in ("medium", "high"))
        self.assertLess(trend_t, thr_t)

    def test_manual_observation(self):
        res = self.ward.add_observation("P06", {"rr": 26, "spo2": 93, "sbp": 95, "hr": 118,
                                                "temp": 39.2, "o2": False, "acvpu": "A",
                                                "scale": 1})
        self.assertEqual(res["reading"]["source"], "manual")
        self.assertEqual(res["reading"]["band"], "high")
        self.assertEqual(res["alerts"][0]["band"], "high")
        tile = [t for t in self.ward.summary()["patients"] if t["id"] == "P06"][0]
        self.assertEqual(tile["source"], "manual")
        self.assertIsNone(self.ward.add_observation("NOPE", {}))

    def test_patient_detail(self):
        d = self.ward.patient_detail("P04")
        self.assertEqual(d["patient"]["scale"], 2)
        self.assertIsNotNone(d["scale1_comparison"])
        self.assertGreater(d["scale1_comparison"]["total"], d["breakdown"]["total"])
        self.assertEqual(len(d["history"]), config.RESET_STEP + 1)
        self.assertIn("Bed 4", d["handover"])
        self.assertIsNone(self.ward.patient_detail("NOPE"))

    def test_handover(self):
        self.ward.control("skip", hours=10)
        h = self.ward.handover()
        self.assertEqual(len(h["patients"]), 12)
        for bed in range(1, 13):
            self.assertIn("Bed %d -" % bed, h["text"])
        self.assertIn("not a medical device", h["text"])
        self.assertIn("Last change", h["text"])

    def test_last_change(self):
        hist = [{"t": 0, "score": 1, "points": {"rr": 0, "hr": 1}},
                {"t": 0.25, "score": 3, "points": {"rr": 2, "hr": 1}},
                {"t": 0.5, "score": 3, "points": {"rr": 2, "hr": 1}}]
        ch = last_change(hist)
        self.assertEqual((ch["from"], ch["to"], ch["t"], ch["params"]), (1, 3, 0.25, ["rr"]))
        self.assertIsNone(last_change(hist[:1]))


if __name__ == "__main__":
    unittest.main()
