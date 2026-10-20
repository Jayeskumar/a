"""Per-patient alert state machine shared by the live ward and the offline evaluation.

Two alert types:
  * threshold - NEWS2 band escalates (low-medium / medium / high). Hysteresis: once alerted
    at a band, the same band does not re-alert until the patient has stayed in a lower band
    for THRESHOLD_REARM_READINGS consecutive readings (stops 4<->5 flicker spam).
  * trend     - the early-warning rule in trend.py fires while the patient is still below
    the medium band and has not already been escalated; rate-limited by a cooldown.
"""

from . import config, news2, trend


def score_reading(reading):
    res = news2.calculate(reading)
    out = dict(reading)
    out.update(score=res["total"], band=res["band"], band_rank=res["band_rank"],
               red_params=res["red_params"],
               points={p["key"]: p["points"] for p in res["parameters"]})
    return out, res


class PatientMonitor:
    def __init__(self):
        self.history = []
        self.alerted_rank = 0
        self.lower_count = 0
        self.last_trend_t = None
        self.last_trend = None
        self.trend_streak = 0

    def ingest(self, reading):
        """Score a new reading, update trend analysis, return list of alert events."""
        scored, full = score_reading(reading)
        self.history.append(scored)
        tr = trend.analyse(self.history)
        self.last_trend = tr
        events = []
        rank = scored["band_rank"]
        if rank > self.alerted_rank:
            self.alerted_rank = rank
            self.lower_count = 0
            top = sorted(full["parameters"], key=lambda p: -p["points"])
            contrib = ["%s %s%s (%d)" % (p["label"], p["value"], p["unit"] and " " + p["unit"],
                                         p["points"]) for p in top if p["points"] > 0][:4]
            msg = "NEWS2 %d – %s risk" % (scored["score"], full["band_label"].lower())
            if full["red_params"] and scored["band"] == "low_medium":
                msg += " (single parameter scored 3: %s)" % ", ".join(
                    news2.PARAM_META[k][0] for k in full["red_params"])
            events.append({"type": "threshold", "t": scored["t"], "step": scored.get("step"),
                           "band": scored["band"], "score": scored["score"],
                           "message": msg, "contributors": contrib,
                           "frequency": full["frequency"], "response": full["response"]})
        elif rank < self.alerted_rank:
            self.lower_count += 1
            if self.lower_count >= config.THRESHOLD_REARM_READINGS:
                self.alerted_rank = rank
                self.lower_count = 0
        else:
            self.lower_count = 0

        self.trend_streak = self.trend_streak + 1 if tr["early_warning"] else 0
        confirmed = self.trend_streak >= config.TREND_CONFIRM_READINGS
        if confirmed and self.alerted_rank < 2:
            cooled = (self.last_trend_t is None or
                      scored["t"] - self.last_trend_t >= config.TREND_ALERT_COOLDOWN_H)
            if cooled:
                self.last_trend_t = scored["t"]
                contrib = ["%s %+.1f %s/h → %s" % (v["label"], v["slope_per_h"], v["unit"],
                                                  v["projected"])
                           for v in tr["vitals"] if v["worsening"]]
                events.append({
                    "type": "trend", "t": scored["t"], "step": scored.get("step"),
                    "band": scored["band"], "score": scored["score"],
                    "projected_score": tr["projected_score"],
                    "message": "Early warning – " + tr["reason"],
                    "contributors": contrib,
                    "frequency": "Increase observations to at least 1-hourly",
                    "response": ("Score is still below the urgent-response threshold but "
                                 "vitals are trending towards it. Registered nurse to "
                                 "re-assess the patient now and inform the medical team "
                                 "if the trend is confirmed."),
                })
        return scored, events
