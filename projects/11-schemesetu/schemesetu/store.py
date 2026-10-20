"""Tiny JSON-file store for registered households and their application tracker.

Thread-safe (one lock), atomic writes (temp file + os.replace), created on
first use. Shape:
  {"version": 1, "households": {id: {id, name, village, profile, source,
                                     applications: {scheme_id: {status, updated}},
                                     created, updated}}}
"""
import json
import os
import secrets
import threading
import time

from . import config

MAX_NAME = 80
MAX_VILLAGE = 60


class StoreError(ValueError):
    pass


class NotFound(KeyError):
    pass


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class Store(object):
    def __init__(self, path):
        self.path = path
        self.lock = threading.RLock()
        self.data = {"version": 1, "households": {}}
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict) and isinstance(loaded.get("households"), dict):
                    self.data = loaded
            except (OSError, ValueError):
                pass  # corrupt file: start fresh, it is overwritten on next save
        else:
            self._save()

    def _save(self):
        d = os.path.dirname(self.path)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=1, sort_keys=True)
        os.replace(tmp, self.path)

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _clean_name(name):
        if isinstance(name, dict):
            en = str(name.get("en", "")).strip()[:MAX_NAME]
            ta = str(name.get("ta", en)).strip()[:MAX_NAME]
            if not en:
                raise StoreError("name is required")
            return {"en": en, "ta": ta or en}
        name = str(name or "").strip()
        if not name:
            raise StoreError("name is required")
        if len(name) > MAX_NAME:
            raise StoreError("name too long (max %d)" % MAX_NAME)
        return name

    @staticmethod
    def _clean_village(v):
        v = str(v or "").strip()
        if len(v) > MAX_VILLAGE:
            raise StoreError("village too long (max %d)" % MAX_VILLAGE)
        return v or "Unassigned"

    # ------------------------------------------------------------ queries
    def list(self, village=None):
        with self.lock:
            hs = list(self.data["households"].values())
        if village:
            hs = [h for h in hs if h["village"] == village]
        return sorted(hs, key=lambda h: (h["village"], h["created"], h["id"]))

    def villages(self):
        with self.lock:
            return sorted(set(h["village"] for h in self.data["households"].values()))

    def get(self, hid):
        with self.lock:
            h = self.data["households"].get(hid)
            if h is None:
                raise NotFound(hid)
            return h

    # ------------------------------------------------------------ writes
    def create(self, name, village, profile, source="manual", hid=None, applications=None):
        with self.lock:
            hid = hid or ("h" + secrets.token_hex(4))
            while hid in self.data["households"]:
                hid = "h" + secrets.token_hex(4)
            now = _now()
            h = {"id": hid, "name": self._clean_name(name), "village": self._clean_village(village),
                 "profile": dict(profile or {}), "source": source,
                 "applications": dict(applications or {}), "created": now, "updated": now}
            self.data["households"][hid] = h
            self._save()
            return h

    def update(self, hid, name=None, village=None, profile=None):
        with self.lock:
            h = self.get(hid)
            if name is not None:
                h["name"] = self._clean_name(name)
            if village is not None:
                h["village"] = self._clean_village(village)
            if profile is not None:
                h["profile"] = dict(profile)
            h["updated"] = _now()
            self._save()
            return h

    def delete(self, hid):
        with self.lock:
            if hid not in self.data["households"]:
                raise NotFound(hid)
            del self.data["households"][hid]
            self._save()

    def set_application(self, hid, scheme_id, status):
        if status not in config.APPLICATION_STATUSES:
            raise StoreError("status must be one of %s" % ", ".join(config.APPLICATION_STATUSES))
        with self.lock:
            h = self.get(hid)
            if status == "not_applied":
                h["applications"].pop(scheme_id, None)
            else:
                h["applications"][scheme_id] = {"status": status, "updated": _now()}
            h["updated"] = _now()
            self._save()
            return h

    def replace_source(self, source, households):
        """Drop all households of `source` and insert the given ones (demo seeding)."""
        with self.lock:
            hs = self.data["households"]
            for hid in [k for k, v in hs.items() if v.get("source") == source]:
                del hs[hid]
            now = _now()
            for h in households:
                rec = dict(h)
                rec.setdefault("applications", {})
                rec["source"] = source
                rec["created"] = rec.get("created") or now
                rec["updated"] = now
                hs[rec["id"]] = rec
            self._save()
            return len(households)

    def reset(self):
        with self.lock:
            self.data = {"version": 1, "households": {}}
            self._save()
