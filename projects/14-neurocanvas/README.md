# NeuroCanvas

**Draw a digit, watch a neural network think.**
Domain: Artificial Intelligence & Machine Learning · QUANTIX 2K26 · KSRCE

Students usually meet neural networks as `model.fit()`: a black box that needs a GPU and the
internet. NeuroCanvas is a neural network you can see inside. Draw a digit and you see the 10
class probabilities update live as you draw, every hidden neuron light up, which pixels argue
for or against the answer (saliency), and a plain-English walk through the forward pass and
backpropagation using the real numbers for *your* drawing. You can train a fresh network live
and watch the loss fall and the first-layer weights form, and you can teach it your own
handwriting.

Everything is written from scratch in **pure Python** (standard library only): the synthetic
digit generator, MNIST-style preprocessing, the multi-layer perceptron, hand-derived
backpropagation, SGD with momentum, saliency, the confusion matrix. There is no numpy, no
framework, no CDN and no network access; it runs on any laptop with Wi-Fi off.

![NeuroCanvas](docs/screenshot.png)

## Quick start

```bash
cd projects/14-neurocanvas
python app.py                 # http://127.0.0.1:8014/   (ready in ~0.1 s)
python app.py --host 0.0.0.0  # open it from a phone on the same Wi-Fi
```

It opens with a demo digit being drawn. **Run demo** (header) or **Demo digit** draws another,
and the **Load demo lesson** button on the Teach it tab sets up the fine-tuning demo.

```bash
python -m unittest discover -s tests       # 50 tests: gradient check, softmax, XOR, renderer, API
python -m neurocanvas.dataset              # rebuild data/digits.bin.gz (deterministic, ~13 s)
python -m neurocanvas.train                # retrain data/weights.json (~100 s, pure Python)
# optional, needs Node + Playwright: draw digits with the mouse in a real browser
NODE_PATH="$(npm root -g)" node tests/handdraw_check.js http://127.0.0.1:8014/ 3
```

## What's inside

| Tab | What you see |
|---|---|
| Draw & inspect | drawing pad, live probability bars, the 16×16 input, saliency overlaid on your strokes, every neuron's activation with the strongest connections, top voting neurons, first-layer weight images |
| Explain | 11 numbered steps from pixels to softmax to loss to backprop to one SGD step, with the actual numbers; pick a different "true" label to see how hard backprop pushes |
| Live training | train a fresh net in a background thread (learning rate, neurons, layers, epochs, data size, activation, batch, momentum); live loss/accuracy curves and evolving weight images; one-click experiments (LR too high, tiny net, overfitting...) |
| Evaluation | confusion matrix (click a cell), per-class recall/precision, most-confident mistakes, training curve, gallery of training digits |
| Teach it | draw and label your own examples, fine-tune with replay, see before → after for your examples, for unseen LCD-style digits and for the original test set (forgetting) |

## API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | status, model, startup time |
| GET | `/api/model` | architecture, parameter count, pretrained training history |
| GET | `/api/weights` | first-layer weights as 16×16 images (normalised) |
| GET | `/api/evaluation` | test accuracy, confusion matrix, per-class scores, mistakes, latency |
| GET | `/api/samples?digit=&n=&split=&offset=` | training/test images |
| GET | `/api/demo?digit=&seed=&style=hand\|lcd` | pen strokes for an animated demo digit |
| POST | `/api/predict` | `{"pixels":[256 floats]}` or `{"raw":{"width","height","data"}}` → probabilities, activations, contributions, edges, saliency, latency |
| POST | `/api/explain` | `{"pixels", "label"?, "lr"?}` → step-by-step forward + backprop explanation |
| POST | `/api/train/start` | `{"lr","hidden","hidden2","epochs","batch","momentum","l2","activation","train_size"}` |
| GET | `/api/train/status` | live run state, per-epoch history, batch losses, weight tiles |
| POST | `/api/train/stop` · `/api/train/adopt` | stop the run · use the trained net for drawing |
| GET | `/api/teach` | teaching set with current predictions + accuracy on unseen LCD digits |
| POST | `/api/teach/add` · `/delete` · `/clear` · `/demo` | manage the teaching set (`data/teach.json`) |
| POST | `/api/teach/finetune` | `{"steps","lr","replay"}` → before/after report, swaps in the fine-tuned net |
| POST | `/api/model/reset` | back to the pretrained network |

Errors are JSON `{"error": ..., "status": ...}` with 400 / 404 / 405 / 409 / 413 codes.

## Layout

```
app.py                  stdlib ThreadingHTTPServer, routes -> Service
neurocanvas/
  config.py             every tunable number, with reasons
  templates.py          stroke templates for 0-9 (several styles each) + LCD style
  render.py             elastic warp, affine, anti-aliased rasteriser, demo strokes
  preprocess.py         crop -> fit 12 px -> centre of mass in 16x16 (mirrored in app.js)
  dataset.py            deterministic 6,000-image dataset, cached as data/digits.bin.gz
  mlp.py                MLP, softmax/cross-entropy, backprop, SGD + momentum
  train.py              training loop + CLI that writes data/weights.json
  explain.py            saliency, contributions, plain-English explanation
  live.py               background training playground
  teach.py              user examples + fine-tuning with replay
  metrics.py            accuracy, confusion matrix, per-class scores
  service.py            application state used by app.py
static/                 index.html, app.js (incl. JS preprocessing), style.css
data/                   digits.bin.gz (dataset), weights.json (trained net)
tests/                  unittest suites + handdraw_check.js (Playwright)
```

Built for QUANTIX 2K26 · KSRCE.
