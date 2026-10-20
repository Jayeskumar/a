"""Live ward state: simulated clock, per-patient monitors, alert feed, handover.

The clock is lazy and server-side: while playing, the current step is derived from the
real time elapsed since the last play/speed change, and readings are revealed (and scored)
step by step whenever any API call syncs the ward. No background thread is needed.
"""

import threading
import time

from . import config, handover, news2, simulator, trend
from .alerts import PatientMonitor

BAND_ORDER = ("high", "medium", "low_medium", "low")


def _history_row(r):
    row = {k: r[k] for k in ("t", "rr", "spo2", "sbp", "hr", "temp", "o2", "acvpu", "score",
                             "band", "points")}
    row["clock"] = simulator.clock_label(r["t"])
    row["source"] = r.get("source", "monitor")
    return row


class Ward:
    def __init__(self, seed=config.DEFAULT_SEED, clock=time.monotonic):
        self.seed = seed
        self._clock = clock
        self.lock = threading.RLock()
        self.reset()

    # ----------------------------------------------------------------- clock
    def reset(self):
        with self.lock:
            self.patients = []
            for w in simulator.generate_ward(seed=self.seed):
                self.patients.append({"profile": w["profile"], "stream": w["readings"],
                                      "monitor": PatientMonitor()})
            self.alerts = []
            self._next_alert = 1
            self.step = -1
            self.playing = False
            self.speed = 1
            self._anchor_real = self._clock()
            self._anchor_step = 0
            self._advance_to(config.RESET_STEP, preroll=True)
            self._reanchor()

    def _reanchor(self):
        self._anchor_real = self._clock()
        self._anchor_step = self.step

    def _advance_to(self, target, preroll=False):
        target = min(target, config.SCENARIO_STEPS)
        while self.step < target:
            self.step += 1
            for p in self.patients:
                reading = p["stream"][self.step]
                _, events = p["monitor"].ingest(reading)
                for ev in events:
                    self._add_alert(p, ev, preroll)
        if self.step >= config.SCENARIO_STEPS:
            self.playing = False

    def _add_alert(self, patient, ev, preroll=False):
        prof = patient["profile"]
        alert = dict(ev)
        alert.update(id=self._next_alert, patient_id=prof["id"], bed=prof["bed"],
                     patient=prof["name"], clock=simulator.clock_label(ev["t"]),
                     acknowledged=preroll, ack_by="Night shift" if preroll else None,
                     ack_clock=simulator.clock_label(ev["t"]) if preroll else None)
        self._next_alert += 1
        self.alerts.append(alert)

    def sync(self):
        with self.lock:
            if self.playing:
                elapsed = self._clock() - self._anchor_real
                target = self._anchor_step + int(elapsed * self.speed /
                                                 config.REAL_SECONDS_PER_STEP)
                self._advance_to(target)

    def control(self, action, speed=None, hours=None):
        """play | pause | reset | speed | skip | step | demo. Raises ValueError."""
        with self.lock:
            self.sync()
            if action == "play":
                if self.step >= config.SCENARIO_STEPS:
                    raise ValueError("scenario finished - reset to replay")
                self.playing = True
                self._reanchor()
            elif action == "pause":
                self.playing = False
            elif action == "reset":
                self.reset()
            elif action == "speed":
                try:
                    speed = int(speed)
                except (TypeError, ValueError):
                    speed = None
                if speed not in config.ALLOWED_SPEEDS:
                    raise ValueError("speed must be one of %s" % (config.ALLOWED_SPEEDS,))
                self.speed = speed
                self._reanchor()
            elif action in ("skip", "step"):
                if action == "step":
                    hours = 1.0 / config.STEPS_PER_HOUR
                try:
                    hours = float(hours)
                except (TypeError, ValueError):
                    raise ValueError("hours must be a number")
                if not 0 < hours <= config.SCENARIO_HOURS:
                    raise ValueError("hours must be between 0 and %d" % config.SCENARIO_HOURS)
                self._advance_to(self.step + int(round(hours * config.STEPS_PER_HOUR)))
                self._reanchor()
            elif action == "demo":
                self.reset()
                self.speed = 1          # 15 simulated minutes per second
                self.playing = True
                self._reanchor()
            else:
                raise ValueError("unknown action")
            return self.clock_state()

    def clock_state(self):
        t = self.step / config.STEPS_PER_HOUR
        return {"step": self.step, "t": t, "clock": simulator.clock_label(t),
                "playing": self.playing, "speed": self.speed,
                "speeds": list(config.ALLOWED_SPEEDS), "end_step": config.SCENARIO_STEPS,
                "finished": self.step >= config.SCENARIO_STEPS,
                "minutes_per_step": config.READING_INTERVAL_MIN,
                "real_seconds_per_step": config.REAL_SECONDS_PER_STEP}

    # --------------------------------------------------------------- queries
    def _find(self, pid):
        for p in self.patients:
            if p["profile"]["id"] == pid:
                return p
        return None

    def _tile(self, p):
        prof = p["profile"]
        hist = p["monitor"].history
        last = hist[-1]
        tr = p["monitor"].last_trend or {}
        full = news2.calculate(last)
        unacked = [a for a in self.alerts if a["patient_id"] == prof["id"]
                   and not a["acknowledged"]]
        change = handover.last_change(hist)
        return {
            "id": prof["id"], "bed": prof["bed"], "name": prof["name"], "age": prof["age"],
            "sex": prof["sex"], "diagnosis": prof["diagnosis"], "scale": prof["scale"],
            "score": last["score"], "band": last["band"], "band_rank": last["band_rank"],
            "band_label": full["band_label"], "red_params": last["red_params"],
            "frequency": full["frequency"],
            "vitals": {k: last[k] for k in ("rr", "spo2", "sbp", "hr", "temp", "o2",
                                             "acvpu")},
            "points": last["points"],
            "spark": [r["score"] for r in hist[-24:]],
            "trend": {"direction": trend.direction(tr) if tr else "stable",
                      "early_warning": bool(p["monitor"].trend_streak >=
                                            config.TREND_CONFIRM_READINGS),
                      "reason": tr.get("reason", ""), "projected": tr.get("projected_score"),
                      "score_slope": tr.get("score_slope", 0.0)},
            "unacked_alerts": len(unacked),
            "last_change": change and dict(change, clock=simulator.clock_label(change["t"])),
            "last_clock": simulator.clock_label(last["t"]),
            "source": last.get("source", "monitor"),
        }

    @staticmethod
    def _acuity_key(tile):
        return (-tile["band_rank"], -int(tile["trend"]["early_warning"]), -tile["score"],
                tile["bed"])

    def summary(self):
        with self.lock:
            self.sync()
            tiles = sorted((self._tile(p) for p in self.patients), key=self._acuity_key)
            counts = {b: 0 for b in BAND_ORDER}
            for t in tiles:
                counts[t["band"]] += 1
            return {"clock": self.clock_state(), "patients": tiles, "band_counts": counts,
                    "early_warnings": sum(1 for t in tiles if t["trend"]["early_warning"]),
                    "unacked_alerts": sum(1 for a in self.alerts if not a["acknowledged"]),
                    "alerts": self.alert_list(limit=40)}

    def alert_list(self, limit=None, unacked_only=False):
        with self.lock:
            items = [a for a in reversed(self.alerts)
                     if not (unacked_only and a["acknowledged"])]
            return items[:limit] if limit else items

    def patient_detail(self, pid):
        with self.lock:
            self.sync()
            p = self._find(pid)
            if p is None:
                return None
            hist = p["monitor"].history
            tr = p["monitor"].last_trend or {}
            last = hist[-1]
            full = news2.calculate(last)
            tile = self._tile(p)
            scale1 = None
            if p["profile"]["scale"] == 2:
                alt = news2.calculate(dict(last, scale=1))
                scale1 = {"total": alt["total"], "band": alt["band"],
                          "band_label": alt["band_label"]}
            _, text = handover.patient_summary(p["profile"], hist, tr)
            return {
                "patient": tile,
                "breakdown": full,
                "scale1_comparison": scale1,
                "trend": tr,
                "history": [_history_row(r) for r in hist],
                "alerts": [a for a in reversed(self.alerts) if a["patient_id"] == pid],
                "handover": text,
            }

    def acknowledge(self, alert_id, by="Nurse"):
        with self.lock:
            self.sync()
            for a in self.alerts:
                if a["id"] == alert_id:
                    if not a["acknowledged"]:
                        a["acknowledged"] = True
                        a["ack_by"] = (str(by)[:40] or "Nurse")
                        a["ack_clock"] = self.clock_state()["clock"]
                    return a
            return None

    def add_observation(self, pid, obs):
        """Add a manually entered (validated) observation at the current simulated time."""
        with self.lock:
            self.sync()
            p = self._find(pid)
            if p is None:
                return None
            reading = dict(obs)
            reading.update(step=self.step, t=self.step / config.STEPS_PER_HOUR,
                           source="manual")
            scored, events = p["monitor"].ingest(reading)
            for ev in events:
                self._add_alert(p, ev)
            return {"reading": scored, "alerts": events}

    def handover(self):
        with self.lock:
            self.sync()
            items = []
            for p in sorted(self.patients, key=lambda p: self._acuity_key(self._tile(p))):
                data, text = handover.patient_summary(p["profile"], p["monitor"].history,
                                                      p["monitor"].last_trend or {})
                data["text"] = text
                items.append(data)
            clock = self.clock_state()["clock"]
            header = ("PulseGuard shift handover - General Ward A - generated %s (simulated)\n"
                      "Decision-support prototype, not a medical device. Verify at bedside.\n"
                      % clock)
            return {"clock": clock, "patients": items,
                    "text": header + "\n" + "\n\n".join(i["text"] for i in items) + "\n"}
