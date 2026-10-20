"""Look inside the network: activations, contributions, saliency, explanations.

Contributions use gradient x activation. For a ReLU network this is *exact*:
inside the current on/off pattern of the ReLUs the logit is a linear function
of any hidden layer, so  z_c = sum_j a_j * dz_c/da_j  +  (terms from later
biases). For tanh it is the first-order (Taylor) approximation.
"""

import math

from .config import GRID
from .mlp import log_softmax, softmax


def _r(v, d=4):
    return round(v, d)


def _argmax(v):
    return max(range(len(v)), key=v.__getitem__)


def _top(values, k, key=abs):
    return sorted(range(len(values)), key=lambda i: -key(values[i]))[:k]


def _pix(i, grid=GRID):
    return "row %d, col %d" % (i // grid + 1, i % grid + 1)


def analyse(model, x, cls=None):
    """Forward + backward from the class logit. ``cls`` defaults to the prediction."""
    zs, acts = model.forward(x)
    logits = zs[-1]
    probs = softmax(logits)
    pred = _argmax(probs)
    c = pred if cls is None else cls
    onehot = [0.0] * len(logits)
    onehot[c] = 1.0
    deltas, dx = model.backward(zs, acts, onehot, to_input=True)
    # dz_c/da_h for every hidden layer h (acts[h], h >= 1)
    grads = [None] + [model._wt_dot(h, deltas[h]) for h in range(1, len(acts))]
    return {"zs": zs, "acts": acts, "logits": logits, "probs": probs, "pred": pred, "cls": c,
            "deltas": deltas, "saliency": dx, "grads": grads}


def inspect(model, x, top_units=10):
    """Everything the 'Inside the network' panel draws, rounded for JSON."""
    a = analyse(model, x)
    acts, grads, c = a["acts"], a["grads"], a["cls"]
    order = sorted(range(len(a["probs"])), key=lambda k: -a["probs"][k])
    runner = order[1]
    layers, shown = [], []
    for h in range(1, len(acts)):
        contrib = [ai * gi for ai, gi in zip(acts[h], grads[h])]
        idx = _top(contrib, top_units)
        shown.append(idx)
        layers.append({
            "size": len(acts[h]),
            "act": [_r(v, 3) for v in acts[h]],
            "active": sum(1 for v in acts[h] if v > 1e-9) if model.activation == "relu"
            else sum(1 for v in acts[h] if abs(v) > 0.5),
            "top": [{"unit": j, "act": _r(acts[h][j], 3), "contrib": _r(contrib[j], 3)} for j in idx],
        })
    # edges between consecutive displayed layers: signal j sends into k = W[k][j] * a_j
    edges = []
    for h in range(1, len(acts) - 1):
        W = model.W[h]
        for j in shown[h - 1]:
            for k in shown[h]:
                s = W[k][j] * acts[h][j]
                if abs(s) > 1e-6:
                    edges.append({"from": [h, j], "to": [h + 1, k], "w": _r(s, 3)})
    last = len(acts) - 1
    Wout = model.W[-1]
    for k in shown[-1]:
        for cls in (c, runner):
            s = Wout[cls][k] * acts[last][k]
            edges.append({"from": [last, k], "to": ["out", cls], "w": _r(s, 3)})
    sal = a["saliency"]
    gxi = [s * v for s, v in zip(sal, x)]
    return {
        "probs": [_r(v) for v in a["probs"]], "logits": [_r(v, 3) for v in a["logits"]],
        "pred": a["pred"], "runner_up": runner, "confidence": _r(a["probs"][a["pred"]]),
        "layers": layers, "edges": edges,
        "saliency": [_r(v, 4) for v in sal], "grad_x_input": [_r(v, 4) for v in gxi],
        "evidence": {"pixels": _r(sum(gxi), 3), "bias": _r(a["logits"][c] - sum(gxi), 3)},
    }


# ---- plain-English step-by-step explanation with the real numbers ------------

def _f(v, d=2):
    return ("%+." + str(d) + "f") % v


def _pct(p):
    """Probability as a readable percentage, keeping tiny values visible."""
    if p >= 0.001:
        return "%.1f%%" % (100 * p)
    if p > 0:
        return "%.1g%%" % (100 * p)
    return "0%"


def explain(model, x, label=None, lr=0.05):
    a = analyse(model, x)
    zs, acts, probs, pred = a["zs"], a["acts"], a["probs"], a["pred"]
    y = pred if label is None else int(label)
    if not 0 <= y < len(probs):
        raise ValueError("label must be 0-9")
    L = len(model.W)
    steps = []

    ink = [i for i, v in enumerate(x) if v > 0.2]
    steps.append({
        "title": "Your drawing becomes %d numbers" % len(x),
        "text": ("The pad was cropped to the ink, scaled so the longest side is 12 px, and shifted so its "
                 "centre of mass sits in the middle of a 16x16 grid (the recipe used for MNIST). "
                 "%d of %d pixels carry ink (> 0.2); total ink = %.1f. Each pixel is one input x_i in [0, 1]."
                 % (len(ink), len(x), sum(x))),
    })

    for h in range(1, L):
        z, act = zs[h - 1], acts[h]
        Wl, bl, inp = model.W[h - 1], model.b[h - 1], acts[h - 1]
        alive = [j for j, v in enumerate(act) if (v > 1e-9 if model.activation == "relu" else abs(v) > 0.5)]
        best = _top(act, 3, key=lambda v: v)
        rows = []
        for j in best:
            parts = [Wl[j][i] * inp[i] for i in range(len(inp))]
            top_in = _top(parts, 2, key=lambda v: v)
            src = ", ".join(("%s" % _pix(i) if h == 1 else "L%d #%d" % (h - 1, i)) + " %s" % _f(parts[i])
                            for i in top_in)
            rows.append(["#%d" % j, "%.2f" % (z[j] - bl[j]), "%.2f" % bl[j], "%.2f" % z[j], "%.2f" % act[j], src])
        what = "pattern detectors" if h == 1 else "combinations of layer-%d patterns" % (h - 1)
        fname = "ReLU(z) = max(0, z)" if model.activation == "relu" else "tanh(z)"
        steps.append({
            "title": "Hidden layer %d: %d neurons, %s" % (h, len(act), what),
            "text": ("Each neuron j adds up its weighted inputs, z_j = w_j . a + b_j, then applies %s. "
                     "%d of %d neurons %s. The three strongest are below, with the inputs that pushed them most."
                     % (fname, len(alive), len(act),
                        "fired (z > 0); the rest output exactly 0" if model.activation == "relu" else "are strongly on (|a| > 0.5)")),
            "math": "z_j = sum_i W[j][i] * a_i + b_j ;  a_j = f(z_j)",
            "table": {"cols": ["neuron", "w.a", "bias", "z", "a", "biggest inputs"], "rows": rows},
        })

    # output layer
    hid = acts[-1]
    Wout, bout = model.W[-1], model.b[-1]
    logits = zs[-1]
    order = sorted(range(len(probs)), key=lambda k: -probs[k])
    runner = order[1]

    def breakdown(c):
        parts = [Wout[c][k] * hid[k] for k in range(len(hid))]
        tops = _top(parts, 3)
        return ("z_%d = %.2f = bias %.2f %s" % (c, logits[c], bout[c],
                " ".join("%s (#%d)" % (_f(parts[k]), k) for k in tops)) + " ...")
    steps.append({
        "title": "Output layer: one score (logit) per digit",
        "text": ("Each digit c gets z_c = W_out[c] . a + b_c from the last hidden layer. The winner is %d; "
                 "the runner-up is %d. Biggest contributions: %s; %s"
                 % (pred, runner, breakdown(pred), breakdown(runner))),
        "math": "z_c = sum_k W_out[c][k] * a_k + b_c",
    })

    m = max(logits)
    ex = [math.exp(v - m) for v in logits]
    s = sum(ex)
    steps.append({
        "title": "Softmax turns scores into probabilities",
        "text": ("p_c = e^(z_c) / sum e^(z). We subtract the largest score first (%.2f) so e^z can never overflow; "
                 "the answer is unchanged. The exponentials sum to %.3f, so p(%d) = %.3f / %.3f = %.1f%%."
                 % (m, s, pred, ex[pred], s, 100 * probs[pred])),
        "math": "p_c = exp(z_c - max z) / sum_k exp(z_k - max z)",
        "table": {"cols": ["digit", "z", "z - max", "e^(z-max)", "p"],
                  "rows": [[str(k), "%.2f" % logits[k], "%.2f" % (logits[k] - m), "%.3f" % ex[k],
                            _pct(probs[k])] for k in order]},
    })

    lp = log_softmax(logits)
    loss = -lp[y]
    verdict = ("This matches the prediction, so the loss is small." if y == pred else
               "The network gave your label only %s, so the loss is large and backprop will push hard."
               % _pct(probs[y]))
    steps.append({
        "title": "Loss: how wrong is it, if the true digit is %d?" % y,
        "text": "Cross-entropy L = -ln p_%d = -ln %s = %.3f. %s" % (y, ("%.4f" % probs[y]) if probs[y] >= 1e-3 else ("%.2e" % probs[y]), loss, verdict),
        "math": "L = -ln p_y",
    })

    # backprop with respect to the loss for label y
    d_out = [p for p in probs]
    d_out[y] -= 1.0
    deltas, dx = model.backward(zs, acts, d_out, to_input=True)
    steps.append({
        "title": "Backprop 1: the output error is just p - onehot(y)",
        "text": ("Softmax and cross-entropy differentiate to dL/dz_c = p_c - [c = %d]. A negative value means "
                 "'raise this score', positive means 'lower it'. Here dL/dz_%d = %.3f and the strongest push-down "
                 "is on digit %d (%+.3f)."
                 % (y, y, d_out[y], max((k for k in range(len(d_out)) if k != y), key=lambda k: d_out[k]),
                    max(d_out[k] for k in range(len(d_out)) if k != y))),
        "math": "delta_out = p - onehot(y)",
        "table": {"cols": ["digit"] + [str(k) for k in range(len(d_out))],
                  "rows": [["dL/dz"] + ["%+.3f" % v for v in d_out]]},
    })

    g_last = [[d_out[c] * hid[k] for k in range(len(hid))] for c in range(len(d_out))]
    flat = [(abs(g_last[c][k]), c, k) for c in range(len(d_out)) for k in range(len(hid))]
    flat.sort(reverse=True)
    rows = []
    for _, c, k in flat[:3]:
        g = g_last[c][k]
        w = Wout[c][k]
        rows.append(["W_out[%d][#%d]" % (c, k), "%+.3f x %.3f" % (d_out[c], hid[k]), "%+.4f" % g,
                     "%.4f -> %.4f" % (w, w - lr * g)])
    da_last = model._wt_dot(L - 1, d_out)
    passing = sum(1 for k in range(len(hid)) if deltas[L - 2][k] != 0.0)
    steps.append({
        "title": "Backprop 2: blame flows into the last hidden layer",
        "text": ("A weight's gradient is (error at its output) x (activation at its input). The three largest are "
                 "below, with the change one SGD step (learning rate %.2f) would make. The error is then sent back "
                 "through the weights, dL/da = W_out^T delta, and multiplied by f'(z): %d of %d neurons pass "
                 "gradient back (inactive ReLUs block it). Largest |dL/da| = %.3f at neuron #%d."
                 % (lr, passing, len(hid), max(abs(v) for v in da_last), _top(da_last, 1)[0])),
        "math": "dL/dW_out = delta_out (outer) a ;  delta_h = (W_out^T delta_out) * f'(z_h)",
        "table": {"cols": ["weight", "delta x a", "gradient", "after one step"], "rows": rows},
    })

    nz_pix = sum(1 for v in x if v > 0)
    alive1 = sum(1 for v in deltas[0] if v != 0.0)
    steps.append({
        "title": "Backprop 3: down to the first layer",
        "text": ("The same rule repeats layer by layer. For the first layer dL/dW1[j][i] = delta_j x x_i, so only "
                 "%d active-and-blamed neurons x %d inked pixels = %d of %d first-layer weights get a non-zero "
                 "gradient. Pixels with no ink teach nothing: the network learns only from where you drew."
                 % (alive1, nz_pix, alive1 * nz_pix, len(model.W[0]) * len(model.W[0][0]))),
        "math": "dL/dW_1 = delta_1 (outer) x",
    })

    sal = a["saliency"]          # d z_pred / dx
    pos = [i for i in _top(sal, 40, key=lambda v: v) if sal[i] > 0][:3]
    neg = [i for i in _top(sal, 40, key=lambda v: -v) if sal[i] < 0][:3]
    steps.append({
        "title": "Saliency: which pixels argue for a %d?" % pred,
        "text": ("Backprop all the way to the input gives dz_%d/dx: how much each pixel would raise the score for %d "
                 "if it were darker. Strongest 'for' pixels: %s. Strongest 'against' (ink there would argue for "
                 "another digit): %s. This is the cyan (for) / rose (against) overlay on your drawing."
                 % (pred, pred, "; ".join("%s (%+.2f)" % (_pix(i), sal[i]) for i in pos) or "none",
                    "; ".join("%s (%+.2f)" % (_pix(i), sal[i]) for i in neg) or "none")),
        "math": "saliency_i = d z_pred / d x_i",
    })

    # actually take one plain SGD step on this drawing and measure the effect
    probe = model.copy()
    gW, gb = probe.gradients([x], [y])
    for l in range(len(probe.W)):
        for j in range(len(probe.W[l])):
            probe.W[l][j] = [w - lr * g for w, g in zip(probe.W[l][j], gW[l][j])]
        probe.b[l] = [b - lr * g for b, g in zip(probe.b[l], gb[l])]
    p2 = probe.predict_proba(x)
    gnorm = math.sqrt(sum(g * g for m_ in gW for r in m_ for g in r))
    caveat = ""
    if p2[y] - probs[y] > 0.5:
        caveat = (" One big step on a single drawing overshoots like this and would damage what the network "
                  "knows about other digits, which is why real training uses small steps averaged over mini-batches.")
    steps.append({
        "title": "One gradient-descent step on this drawing",
        "text": ("We copy the network and apply W <- W - %.2f x dL/dW once (gradient norm %.3f). p(%d) goes "
                 "from %s to %s and the loss from %.3f to %.3f. Training is just this, repeated "
                 "thousands of times over many drawings (with momentum and mini-batches).%s"
                 % (lr, gnorm, y, _pct(probs[y]), _pct(p2[y]), loss, -math.log(max(p2[y], 1e-300)), caveat)),
        "math": "W <- W - lr * dL/dW",
    })

    return {"pred": pred, "label": y, "loss": _r(loss), "probs": [_r(v) for v in probs],
            "p_after_step": _r(p2[y]), "steps": steps}
