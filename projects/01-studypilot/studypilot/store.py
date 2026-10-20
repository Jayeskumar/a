"""Tiny JSON-file persistence for docs, flashcard SM-2 state and quiz history."""
import json
import os
import threading
import time

EMPTY = {"version": 1, "docs": {}, "cards": {}, "quiz_log": {}, "last_doc": None}
MAX_LOG = 2000   # quiz attempts kept per doc


class Store:
    def __init__(self, path):
        self.path = path
        self.lock = threading.RLock()
        self.data = json.loads(json.dumps(EMPTY))
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    self.data.update(loaded)
            except (OSError, ValueError):
                pass  # corrupt file: start fresh rather than crash the demo
        else:
            self.save()

    def save(self):
        with self.lock:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=1)
            os.replace(tmp, self.path)

    # docs
    def put_doc(self, doc_id, title, text, sample=None):
        with self.lock:
            existing = self.data["docs"].get(doc_id)
            self.data["docs"][doc_id] = {
                "id": doc_id, "title": title, "text": text, "sample": sample,
                "created": existing["created"] if existing else time.time(),
                "opened": time.time()}
            self.data["last_doc"] = doc_id
            self.save()
            return self.data["docs"][doc_id]

    def get_doc(self, doc_id):
        return self.data["docs"].get(doc_id)

    def list_docs(self):
        docs = sorted(self.data["docs"].values(), key=lambda d: -d.get("opened", 0))
        return [{"id": d["id"], "title": d["title"], "sample": d.get("sample"),
                 "words": len(d["text"].split())} for d in docs]

    def delete_doc(self, doc_id):
        with self.lock:
            found = self.data["docs"].pop(doc_id, None) is not None
            self.data["cards"].pop(doc_id, None)
            self.data["quiz_log"].pop(doc_id, None)
            if self.data.get("last_doc") == doc_id:
                self.data["last_doc"] = None
            self.save()
            return found

    # cards
    def card_states(self, doc_id):
        return self.data["cards"].get(doc_id, {})

    def set_card_state(self, doc_id, card_id, state):
        with self.lock:
            self.data["cards"].setdefault(doc_id, {})[card_id] = state
            self.save()

    def reset_cards(self, doc_id):
        with self.lock:
            self.data["cards"].pop(doc_id, None)
            self.save()

    # quiz history
    def quiz_log(self, doc_id):
        return self.data["quiz_log"].get(doc_id, [])

    def add_quiz_results(self, doc_id, records):
        with self.lock:
            log = self.data["quiz_log"].setdefault(doc_id, [])
            log.extend(records)
            del log[:-MAX_LOG]
            self.save()
