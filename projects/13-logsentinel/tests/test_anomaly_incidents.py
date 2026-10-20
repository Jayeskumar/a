import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logsentinel.events import Event
from logsentinel import anomaly
from logsentinel import incidents
from logsentinel.alerts import Alert, reset_ids

BASE = datetime(2026, 10, 15, 10, 0, 0)


def web(ip, offset, path="/", ua="Mozilla/5.0", status=200):
    f = {"method": "GET", "path": path, "proto": "HTTP/1.1", "status": status,
         "size": 10, "ua": ua, "ref": "-"}
    return Event("web", BASE + timedelta(seconds=offset), ip, f, "web %s" % ip)


class TestRateAnomaly(unittest.TestCase):
    def test_spike_detected(self):
        evs = []
        # quiet IP: ~2/min for 8 minutes
        for m in range(8):
            for k in range(2):
                evs.append(web("203.0.113.5", m * 60 + k))
        # then a sudden 80-request minute
        for k in range(80):
            evs.append(web("203.0.113.5", 8 * 60 + k % 60))
        alerts = anomaly.rate_anomalies(evs)
        self.assertTrue(any(a.rule == "ANOM-RATE" and a.src == "203.0.113.5" for a in alerts))

    def test_steady_traffic_quiet(self):
        evs = []
        for m in range(20):
            for k in range(5):
                evs.append(web("203.0.113.6", m * 60 + k))
        alerts = anomaly.rate_anomalies(evs)
        self.assertFalse(any(a.src == "203.0.113.6" for a in alerts))

    def test_known_bot_not_flagged(self):
        evs = []
        for m in range(8):
            evs.append(web("203.0.113.250", m * 60, ua="Googlebot/2.1"))
        for k in range(80):
            evs.append(web("203.0.113.250", 8 * 60 + k % 60, ua="Googlebot/2.1"))
        alerts = anomaly.rate_anomalies(evs)
        self.assertFalse(any(a.src == "203.0.113.250" for a in alerts))


class TestGlobalRpm(unittest.TestCase):
    def test_series_has_points_and_baseline(self):
        evs = [web("1.2.3.4", i) for i in range(0, 600, 3)]
        r = anomaly.global_rpm(evs)
        self.assertGreater(len(r["points"]), 5)
        self.assertIn("baseline", r["points"][0])
        self.assertIn("anomaly", r["points"][0])


class TestNovelty(unittest.TestCase):
    def test_novel_ua_after_warmup(self):
        evs = []
        # warmup: lots of browser traffic (exceed warmup threshold)
        for i in range(anomaly.C.NOVELTY_WARMUP_EVENTS + 10):
            evs.append(web("203.0.113.%d" % (i % 50 + 10), i, ua="Mozilla/5.0 Chrome"))
        # a brand-new UA used heavily by one IP
        for i in range(20):
            evs.append(web("198.51.100.77", anomaly.C.NOVELTY_WARMUP_EVENTS + 20 + i,
                           ua="evil-bot/6.6"))
        alerts = anomaly.novelty(evs)
        self.assertTrue(any(a.rule == "ANOM-UA" and a.src == "198.51.100.77" for a in alerts))


class TestIncidentGrouping(unittest.TestCase):
    def setUp(self):
        reset_ids()

    def _alert(self, rule, sev, src, t0, t1):
        return Alert(rule, rule, sev, src, rule + " title", "detail",
                     ["T1110"], "ssh-brute", ["evi"],
                     BASE + timedelta(seconds=t0), BASE + timedelta(seconds=t1))

    def test_same_ip_grouped(self):
        a1 = self._alert("FW-PORTSCAN", "medium", "203.0.113.200", 0, 60)
        a2 = self._alert("SSH-BRUTE", "high", "203.0.113.200", 120, 300)
        incs = incidents.group([a1, a2])
        self.assertEqual(len(incs), 1)
        self.assertEqual(incs[0]["alert_count"], 2)
        self.assertEqual(incs[0]["severity"], "high")
        # kill-chain ordering: recon before credential access
        phases = incs[0]["phases"]
        self.assertEqual(phases[0], "Reconnaissance")

    def test_distant_times_split(self):
        a1 = self._alert("SSH-BRUTE", "high", "203.0.113.200", 0, 60)
        a2 = self._alert("SSH-BRUTE", "high", "203.0.113.200", 100000, 100060)
        incs = incidents.group([a1, a2])
        self.assertEqual(len(incs), 2)

    def test_different_ips_separate(self):
        a1 = self._alert("SSH-BRUTE", "high", "203.0.113.1", 0, 60)
        a2 = self._alert("SSH-BRUTE", "high", "203.0.113.2", 10, 70)
        incs = incidents.group([a1, a2])
        self.assertEqual(len(incs), 2)

    def test_timeline_sorted(self):
        a1 = self._alert("SSH-COMPROMISE", "critical", "192.0.2.77", 300, 360)
        a2 = self._alert("FW-PORTSCAN", "medium", "192.0.2.77", 0, 60)
        incs = incidents.group([a1, a2])
        ts = [t["ts"] for t in incs[0]["timeline"]]
        self.assertEqual(ts, sorted(ts))


if __name__ == "__main__":
    unittest.main()
