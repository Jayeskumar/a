"""Live training playground: train a fresh network in a background thread.

The UI polls ``status()``; every epoch records loss/accuracy and a snapshot of
first-layer weight images, so students watch the filters form from noise.
"""

import threading
import time

from . import config as C
from .metrics import accuracy
from .mlp import MLP
from .train import fit


def _num(params, key, cast):
    lo, hi = C.LIVE_LIMITS[key]
    raw = params.get(key, C.LIVE_DEFAULTS[key])
    if isinstance(raw, bool):
        raise ValueError("'%s' must be a number" % key)
    try:
        v = cast(raw)
    except (TypeError, ValueError):
        raise ValueError("'%s' must be a number" % key)
    if v != v or not lo <= v <= hi:
        raise ValueError("'%s' must be between %s and %s" % (key, lo, hi))
    return v


def parse_params(params):
    params = params or {}
    if not isinstance(params, dict):
        raise ValueError("expected a JSON object")
    act = params.get("activation", C.LIVE_DEFAULTS["activation"])
    if act not in ("relu", "tanh"):
        raise ValueError("activation must be 'relu' or 'tanh'")
    return {
        "lr": _num(params, "lr", float), "hidden": _num(params, "hidden", int),
        "hidden2": _num(params, "hidden2", int), "epochs": _num(params, "epochs", int),
        "batch": _num(params, "batch", int), "momentum": _num(params, "momentum", float),
        "l2": _num(params, "l2", float), "train_size": _num(params, "train_size", int),
        "activation": act,
    }


def weight_tiles(model, n=C.LIVE_WEIGHT_TILES):
    """First n rows of W1 scaled to [-1, 1] per tile (so the pattern, not the scale, shows)."""
    tiles = []
    for row in model.W[0][:n]:
        m = max(abs(v) for v in row) or 1.0
        tiles.append([round(v / m, 2) for v in row])
    return tiles


class LiveTrainer:
    def __init__(self, dataset):
        self.ds = dataset
        self.lock = threading.Lock()
        self.thread = None
        self.stop_flag = threading.Event()
        self.model = None
        self.run_id = 0
        self._state = {"state": "idle", "run": 0}

    def start(self, params):
        p = parse_params(params)
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise RuntimeError("a training run is already in progress - stop it first")
            self.run_id += 1
            sizes = [C.GRID * C.GRID, p["hidden"]] + ([p["hidden2"]] if p["hidden2"] else []) + [10]
            model = MLP(sizes, p["activation"], seed=self.run_id)
            self.model = model
            self.stop_flag.clear()
            self._state = {"state": "running", "run": self.run_id, "params": p, "sizes": sizes,
                           "n_params": model.n_params, "epoch": 0, "batch": 0, "n_batches": 0,
                           "history": [], "batch_loss": [], "tiles": weight_tiles(model),
                           "started": time.time(), "elapsed": 0.0, "error": None}
            run = self.run_id
            self.thread = threading.Thread(target=self._run, args=(run, model, p), daemon=True)
            self.thread.start()
        return self.status()

    def _run(self, run, model, p):
        try:
            X, Y = self.ds.arrays("train", p["train_size"])
            Xte, Yte = self.ds.arrays("test", 500)              # 500 test images keep epochs snappy
            with self.lock:
                self._state["test_acc0"] = round(accuracy(model, Xte, Yte), 4)
            every = max(1, (len(X) // p["batch"]) // 40)       # ~40 loss points per epoch

            def on_batch(i, n, loss):
                if i % every == 0 or i == n:
                    with self.lock:
                        if self._state["run"] == run:
                            st = self._state
                            st["batch"], st["n_batches"] = i, n
                            st["batch_loss"].append([round(st["epoch"] + i / n, 3),
                                                     round(loss, 4) if loss is not None else None])
                time.sleep(0)                                   # let HTTP threads in

            def on_epoch(row):
                with self.lock:
                    if self._state["run"] == run:
                        if row.get("diverged"):
                            self._state["diverged"] = True
                        self._state["history"].append(row)
                        self._state["epoch"] = row["epoch"]
                        self._state["tiles"] = weight_tiles(model)

            fit(model, X, Y, Xte, Yte, epochs=p["epochs"], batch=p["batch"], lr=p["lr"],
                momentum=p["momentum"], l2=p["l2"], seed=run, on_epoch=on_epoch, on_batch=on_batch,
                should_stop=self.stop_flag.is_set)
            with self.lock:
                if self._state["run"] == run:
                    self._state["state"] = "stopped" if self.stop_flag.is_set() else "done"
        except Exception as e:                                   # never kill the server
            with self.lock:
                self._state["state"] = "error"
                self._state["error"] = str(e)

    def stop(self):
        self.stop_flag.set()
        t = self.thread
        if t:
            t.join(timeout=5)
        return self.status()

    def status(self):
        with self.lock:
            st = dict(self._state)
            if "history" in st:
                st["history"] = list(st["history"])
                st["batch_loss"] = list(st["batch_loss"])
            if st.get("started") and st["state"] == "running":
                st["elapsed"] = round(time.time() - st["started"], 1)
                self._state["elapsed"] = st["elapsed"]
            return st

    def trained_model(self):
        with self.lock:
            if self.model is None or self._state.get("state") == "running" or self._state.get("diverged"):
                return None
            return self.model.copy()
