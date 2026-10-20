"""Thread-safe app state persisted to data/state.json (created on first run).

Data flow and consent:
* Journal entries (text, mood, sleep) stay in the student's own record and are never
  copied into the cohort / counsellor data.
* A check-in is copied to the cohort (pseudonymous ID, totals and bands only) only if the
  student's "share anonymously" consent is on.
* PHQ-9 item 9 > 0 on a shared check-in creates a pseudonymous alert.
* "Ask a counsellor to reach out" creates a contact request; only then is the student
  reachable.
"""

import copy
import datetime as _dt
import json
import os
import secrets
import threading

from . import (config, counsellor, demo_data, questionnaires, resources, safety, sentiment,
               trends)

MAX_TEXT = 1000


class Store:
    def __init__(self, path, today_fn=None, now_fn=None):
        self.path = path
        self.today = today_fn or _dt.date.today
        self.now = now_fn or (lambda: _dt.datetime.now().isoformat(timespec="minutes"))
        self.lock = threading.RLock()
        self.sessions = {}
        self.state = None
        self._load()

    # ------------------------------------------------------------ persistence
    def _load(self):
        with self.lock:
            if os.path.isfile(self.path):
                try:
                    with open(self.path, encoding="utf-8") as f:
                        st = json.load(f)
                    if isinstance(st, dict) and st.get("version") == 1 and "student" in st:
                        self.state = st
                        return
                except (OSError, ValueError):
                    pass
            self.reset_demo()

    def _save(self):
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False)
        os.replace(tmp, self.path)

    def reset_demo(self):
        with self.lock:
            today = self.today()
            self.state = demo_data.build_state(end_date=today - _dt.timedelta(days=1),
                                               today=today)
            self._save()
            return {"ok": True, "generated_for": self.state["generated_for"]}

    def _next(self, key, prefix):
        c = self.state.setdefault("counter", {})
        c[key] = c.get(key, 0) + 1
        return "%s%03d" % (prefix, c[key])

    def _current_week(self):
        return self.state["cohort"]["weeks"][-1]["week"]

    # ------------------------------------------------------------ student side
    def student(self):
        with self.lock:
            st = self.state["student"]
            journal = st["journal"]
            return {
                "name": st["name"], "pid": st["pid"], "year": st["year"],
                "consent": st["consent"], "today": self.today().isoformat(),
                "journal": list(reversed(journal)),
                "screenings": list(reversed(st["screenings"])),
                "trends": trends.analyse(journal),
                "demo_entry": demo_data.DEMO_LIVE_ENTRY,
            }

    def set_consent(self, body):
        with self.lock:
            c = self.state["student"]["consent"]
            for k in ("share_aggregate", "contact"):
                if k in body:
                    if not isinstance(body[k], bool):
                        raise ValueError({k: "must be true or false"})
                    c[k] = body[k]
            self._save()
            return c

    def add_journal(self, body):
        errors = {}
        mood = body.get("mood")
        if isinstance(mood, bool) or not isinstance(mood, (int, float)) or \
                mood != int(mood) or not 1 <= mood <= 5:
            errors["mood"] = "choose 1 (very low) to 5 (very good)"
        sleep = body.get("sleep")
        if sleep is not None and (isinstance(sleep, bool) or
                                  not isinstance(sleep, (int, float)) or
                                  not 0 <= sleep <= 16):
            errors["sleep"] = "hours between 0 and 16"
        text = body.get("text") or ""
        if not isinstance(text, str):
            errors["text"] = "must be text"
            text = ""
        elif len(text) > MAX_TEXT:
            errors["text"] = "up to %d characters" % MAX_TEXT
        today = self.today()
        date = body.get("date") or today.isoformat()
        try:
            d = _dt.date.fromisoformat(str(date))
            if d > today or (today - d).days > 60:
                errors["date"] = "within the last 60 days"
        except ValueError:
            errors["date"] = "use YYYY-MM-DD"
        if errors:
            raise ValueError(errors)
        text = text.strip()
        analysis = sentiment.analyse(text) if text else None
        flags = safety.detect(text)
        with self.lock:
            entry = {
                "id": self._next("journal", "j"), "date": str(date), "mood": int(mood),
                "sleep": round(float(sleep), 1) if sleep is not None else None,
                "text": text,
                "sentiment": analysis["compound"] if analysis else None,
                "label": analysis["label"] if analysis else None,
                "emotions": [e["emotion"] for e in analysis["emotions"][:2]] if analysis
                else [],
                "flagged": flags["flagged"],
            }
            self.state["student"]["journal"].append(entry)
            self.state["student"]["journal"].sort(key=lambda e: (e["date"], e["id"]))
            self._save()
            t = trends.analyse(self.state["student"]["journal"])
        reason = "someone_else" if flags.get("category") == "someone_else" else "journal"
        return {
            "entry": entry, "analysis": analysis, "safety": flags,
            "support": resources.support_screen(reason, flags["level"])
            if flags["flagged"] else None,
            "insights": t["insights"],
        }

    def delete_journal(self, entry_id):
        with self.lock:
            j = self.state["student"]["journal"]
            for i, e in enumerate(j):
                if e["id"] == entry_id:
                    del j[i]
                    self._save()
                    return True
            return False

    def add_screening(self, body):
        inst = body.get("instrument")
        answers = body.get("answers")
        clean, errors = questionnaires.validate(inst, answers)
        if errors:
            raise ValueError(errors)
        result = questionnaires.score(inst, clean, difficulty=body.get("difficulty"))
        with self.lock:
            st = self.state["student"]
            share = st["consent"].get("share_aggregate", False)
            if "share" in body:
                if not isinstance(body["share"], bool):
                    raise ValueError({"share": "must be true or false"})
                share = body["share"]
            today = self.today().isoformat()
            rec = {"id": self._next("screening", "s"), "date": today, "instrument": inst,
                   "answers": clean, "total": result["total"], "band": result["band"],
                   "shared": share}
            st["screenings"].append(rec)
            alert = None
            if share:
                week = self._current_week()
                self.state["cohort"]["screenings"].append({
                    "pid": st["pid"], "week": week, "date": today, "instrument": inst,
                    "total": result["total"], "band": result["band"],
                    "item9": clean[questionnaires.ITEM9_INDEX] if inst == "phq9" else None,
                })
                self._ensure_student_in_cohort()
                if result["support"]["show"]:
                    alert = self._raise_alert(clean, result, week, today)
            self._save()
        result["record"] = rec
        result["shared"] = share
        result["alert_created"] = bool(alert)
        if result["support"]["show"]:
            result["support"].update(resources.support_screen("item9", "urgent"))
        return result

    def _ensure_student_in_cohort(self):
        st = self.state["student"]
        students = self.state["cohort"]["students"]
        if not any(s["pid"] == st["pid"] for s in students):
            students.append({"pid": st["pid"], "year": st["year"],
                             "contact_opt_in": st["consent"].get("contact", False),
                             "preferred": "college email"})

    def _raise_alert(self, answers, result, week, today):
        st = self.state["student"]
        alerts = self.state["cohort"]["alerts"]
        for a in alerts:  # one open alert per student is enough
            if a["pid"] == st["pid"] and a["status"] != "followed_up":
                a.update({"item9": answers[questionnaires.ITEM9_INDEX],
                          "phq9_total": result["total"], "band": result["band"],
                          "raised": today})
                return a
        item9 = answers[questionnaires.ITEM9_INDEX]
        alert = {
            "id": self._next("alert", "A"), "pid": st["pid"], "week": week, "raised": today,
            "source": "PHQ-9 item 9", "item9": item9,
            "item9_label": questionnaires.OPTIONS[item9]["label"],
            "phq9_total": result["total"], "band": result["band"],
            "contact_ok": bool(st["consent"].get("contact")),
            "preferred": "college email" if st["consent"].get("contact") else None,
            "status": "new", "history": [],
        }
        alerts.append(alert)
        return alert

    def request_contact(self, body):
        reason = body.get("reason", "general")
        if reason not in ("item9", "journal", "script", "general", "someone_else"):
            raise ValueError({"reason": "unknown reason"})
        preferred = body.get("preferred", "college email")
        if preferred not in ("in person", "phone call", "college email"):
            raise ValueError({"preferred": "in person, phone call or college email"})
        with self.lock:
            st = self.state["student"]
            co = self.state["cohort"]
            st["consent"]["contact"] = True
            self._ensure_student_in_cohort()
            for s in co["students"]:
                if s["pid"] == st["pid"]:
                    s["contact_opt_in"], s["preferred"] = True, preferred
            latest = next((s for s in reversed(st["screenings"]) if s["instrument"] ==
                           "phq9" and s.get("shared")), None)
            today = self.today().isoformat()
            contact = next((c for c in co["contacts"] if c["pid"] == st["pid"] and
                            c["status"] == "pending"), None)
            label = {"item9": "From support screen (check-in)",
                     "journal": "From support screen (journal)",
                     "script": "From 'talk to someone' screen",
                     "someone_else": "Worried about a friend",
                     "general": "Asked for a chat"}[reason]
            if contact is None:
                contact = {"id": self._next("contact", "C"), "pid": st["pid"],
                           "week": self._current_week(), "requested": today,
                           "reason": label, "preferred": preferred,
                           "latest_band": latest["band"] if latest else None,
                           "status": "pending",
                           "priority": "today" if reason != "general" else "this week"}
                co["contacts"].append(contact)
            else:
                contact.update({"reason": label, "preferred": preferred, "requested": today})
                if reason != "general":
                    contact["priority"] = "today"
            for a in co["alerts"]:
                if a["pid"] == st["pid"] and a["status"] != "followed_up":
                    a["contact_ok"], a["preferred"] = True, preferred
            self._save()
        return {
            "contact": contact,
            "message": "Thank you. The counselling cell will reach out to you (%s) during "
                       "working hours. If you need to talk right now, Tele-MANAS (14416) "
                       "is free and open 24x7. In an emergency, call 112." % preferred,
        }

    def erase_student(self):
        """'Delete my data': removes journal, check-ins and all cohort traces."""
        with self.lock:
            st = self.state["student"]
            pid = st["pid"]
            st["journal"], st["screenings"] = [], []
            st["consent"] = {"share_aggregate": False, "contact": False}
            co = self.state["cohort"]
            co["screenings"] = [s for s in co["screenings"] if s["pid"] != pid]
            co["alerts"] = [a for a in co["alerts"] if a["pid"] != pid]
            co["contacts"] = [c for c in co["contacts"] if c["pid"] != pid]
            co["students"] = [s for s in co["students"] if s["pid"] != pid]
            self._save()
            return {"ok": True}

    # ------------------------------------------------------------ counsellor side
    def login(self, body):
        pin = body.get("pin")
        if not isinstance(pin, str) or not secrets.compare_digest(
                pin.encode(), config.DEMO_COUNSELLOR_PIN.encode()):
            raise PermissionError("incorrect PIN")
        name = body.get("name") or "Ms. Kavya (demo)"
        if not isinstance(name, str):
            name = "Counsellor"
        token = secrets.token_urlsafe(18)
        with self.lock:
            if len(self.sessions) > 50:
                self.sessions.clear()
            self.sessions[token] = {"name": " ".join(name.split())[:60] or "Counsellor",
                                    "role": "counsellor", "since": self.now()}
        return {"token": token, "name": self.sessions[token]["name"], "role": "counsellor"}

    def session(self, token):
        with self.lock:
            return self.sessions.get(token or "")

    def logout(self, token):
        with self.lock:
            self.sessions.pop(token or "", None)

    def dashboard(self):
        with self.lock:
            snap = copy.deepcopy(self.state)
        return counsellor.dashboard(snap, self.today().isoformat())

    def acknowledge(self, alert_id, by, note):
        with self.lock:
            a = counsellor.acknowledge(self.state, alert_id, by, note, self.now())
            self._save()
            return copy.deepcopy(a)

    def follow_up(self, alert_id, by, note):
        with self.lock:
            a = counsellor.follow_up(self.state, alert_id, by, note, self.now())
            self._save()
            return copy.deepcopy(a)

    def mark_contacted(self, contact_id, by):
        with self.lock:
            c = counsellor.mark_contacted(self.state, contact_id, by, self.now())
            self._save()
            return copy.deepcopy(c)
