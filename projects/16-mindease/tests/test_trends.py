import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mindease import config, demo_data, trends as T  # noqa: E402


def journal(moods, sleeps=None, start=dt.date(2026, 10, 1), texts=None):
    out = []
    for i, m in enumerate(moods):
        out.append({"date": (start + dt.timedelta(days=i)).isoformat(), "mood": m,
                    "sleep": sleeps[i] if sleeps else 7.5,
                    "sentiment": 0.3, "text": texts[i] if texts else ""})
    return out


class TestStatistics(unittest.TestCase):
    def test_rolling_mean(self):
        self.assertEqual(T.rolling_mean([1, 2, 3, 4], window=2, min_periods=2),
                         [None, 1.5, 2.5, 3.5])
        self.assertEqual(T.rolling_mean([1, None, 3], window=3, min_periods=2),
                         [None, None, 2.0])

    def test_ols_slope_exact_line(self):
        r = T.ols_slope([0, 1, 2, 3], [5, 4, 3, 2])
        self.assertAlmostEqual(r["slope"], -1.0)
        self.assertTrue(r["significant_down"])
        self.assertEqual(r["t"], -99.0)  # perfect fit: capped t
        self.assertIsNone(T.ols_slope([0, 1], [1, 2]))
        self.assertIsNone(T.ols_slope([1, 1, 1], [1, 2, 3]))

    def test_ols_slope_t_statistic(self):
        r = T.ols_slope([0, 1, 2, 3, 4], [1, 3, 2, 5, 4])
        self.assertAlmostEqual(r["slope"], 0.8)   # Sxy = 8, Sxx = 10
        # SSE = 3.6, se = sqrt(SSE/(n-2)) / sqrt(Sxx), t = 2.309 < t_crit(3) = 2.353
        self.assertAlmostEqual(r["t"], 0.8 / ((3.6 / 3) ** 0.5 / 10 ** 0.5), places=2)
        self.assertEqual(r["df"], 3)
        self.assertFalse(r["significant_up"])
        r2 = T.ols_slope([0, 1, 2, 3, 4, 5, 6], [1, 2, 2, 3, 4, 4, 5])
        self.assertTrue(r2["significant_up"])

    def test_cusum(self):
        s, alarm, start = T.cusum_lower([4, 4, 2, 2, 2], mu=4, sigma=1, k=0.5, h=4)
        self.assertEqual(s, [0.0, 0.0, 1.5, 3.0, 4.5])
        self.assertEqual((alarm, start), (4, 2))
        s, alarm, _ = T.cusum_lower([4, 5, 3, 4, 4], mu=4, sigma=1, k=0.5, h=4)
        self.assertIsNone(alarm)
        self.assertEqual(s[2], 0.5)


class TestDetectors(unittest.TestCase):
    def test_not_enough_data(self):
        r = T.analyse(journal([4, 4, 3]))
        self.assertEqual(r["status"], "not_enough_data")
        self.assertEqual(r["insights"][0]["id"], "warming_up")

    def test_stable_journal_has_no_dip(self):
        r = T.analyse(journal([4, 4, 3, 4, 5, 4, 4, 3, 4, 4, 5, 4, 4, 4, 3, 4, 4, 4, 4, 5, 4]))
        kinds = [i["kind"] for i in r["insights"]]
        self.assertNotIn("dip", kinds)
        self.assertNotIn("together", kinds)
        self.assertFalse(T.dip_decision(r["detectors"]["mood"]))

    def test_dip_detected_with_evidence(self):
        moods = [4] * 14 + [4, 4, 2, 2, 3, 2, 2]
        r = T.analyse(journal(moods))
        d = r["detectors"]["mood"]
        self.assertTrue(T.dip_decision(d))
        self.assertEqual(d["dip_run"]["length"], 5)
        self.assertIsNotNone(d["cusum"]["alarm_date"])
        dip = next(i for i in r["insights"] if i["id"] == "mood_dip")
        self.assertEqual(dip["title"], "Your mood has dipped for 5 days in a row")
        self.assertTrue(any("CUSUM" in e for e in dip["evidence"]))

    def test_one_bad_day_is_not_a_dip(self):
        moods = [4] * 20 + [1]
        r = T.analyse(journal(moods))
        self.assertFalse(T.dip_decision(r["detectors"]["mood"]))

    def test_recovered_dip_is_quiet(self):
        moods = [4] * 14 + [2, 2, 2, 2, 4, 4, 5]
        r = T.analyse(journal(moods))
        self.assertNotIn("mood_dip", [i["id"] for i in r["insights"]])

    def test_sleep_low(self):
        sleeps = [7.5] * 16 + [5, 5.5, 5, 4.5, 5]
        r = T.analyse(journal([4] * 21, sleeps))
        ins = next(i for i in r["insights"] if i["id"] == "sleep_low")
        self.assertIn("5.0 h", ins["message"])

    def test_lift(self):
        moods = [3] * 14 + [3, 4, 4, 5, 5, 5, 5]
        r = T.analyse(journal(moods))
        self.assertIn("lift", [i["kind"] for i in r["insights"]])

    def test_gaps_and_same_day_entries(self):
        e = journal([4, 4, 4, 4, 4, 4, 4, 4, 2, 2, 2])
        e.append(dict(e[-1], mood=4))  # second entry same day -> averaged to 3
        del e[5]                        # a missing day
        series = T.daily_series(e)
        self.assertEqual(len(series), 10)
        self.assertEqual(series[-1]["mood"], 3.0)
        r = T.analyse(e)
        self.assertEqual(r["status"], "ok")

    def test_bad_rows_ignored(self):
        self.assertEqual(T.daily_series([{"date": "nope", "mood": 3}, {"mood": 2}]), [])

    def test_helped_before(self):
        texts = ["went for a walk", "called Amma", "walk with friends"] + [""] * 4
        h = T.helped_before([{"mood": 4, "text": t} for t in texts] +
                            [{"mood": 2, "text": "walk"}])
        self.assertEqual(h[0], {"activity": "going for a walk", "days": 2})


class TestDemoStudent(unittest.TestCase):
    def test_ananya_shows_kind_combined_dip(self):
        st = demo_data.build_state(end_date=demo_data.FIXED_END_DATE)
        r = T.analyse(st["student"]["journal"])
        ids = [i["id"] for i in r["insights"]]
        self.assertEqual(ids[0], "together")
        for needed in ("mood_dip", "sleep_low", "tone_dip", "helped"):
            self.assertIn(needed, ids)
        dip = next(i for i in r["insights"] if i["id"] == "mood_dip")
        self.assertIn("5 days", dip["title"])
        for i in r["insights"]:
            text = (i["title"] + i["message"]).lower()
            for word in ("depress", "disorder", "diagnos", "abnormal"):
                self.assertNotIn(word, text)

    def test_settings_exposed(self):
        r = T.analyse(journal([4] * 10))
        self.assertEqual(r["settings"]["cusum_h"], config.CUSUM_H)


if __name__ == "__main__":
    unittest.main()
