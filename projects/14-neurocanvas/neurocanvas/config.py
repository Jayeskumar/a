"""Every tunable number in one place, with the reasoning behind it.

Change a value here and re-run `python -m neurocanvas.dataset` (data) or
`python -m neurocanvas.train` (weights) to regenerate the committed files.
"""

# ---- input representation -------------------------------------------------
GRID = 16            # network input is GRID x GRID = 256 pixels. 16 (not MNIST's 28)
                     # keeps pure-Python training fast enough to watch live.
FIT = 12             # longest side of the digit is scaled to FIT pixels, like MNIST's
                     # 20-in-28 box (ratio ~0.71; 12/16 = 0.75), leaving a margin.
INK_THRESHOLD = 0.08  # intensity above which a pixel counts as ink for the bounding box

# ---- synthetic dataset ----------------------------------------------------
DATA_SEED = 2026     # fixed seed: the dataset is byte-for-byte reproducible
PER_CLASS = 600      # 600 x 10 digits = 6,000 images ("a few thousand")
TEST_PER_CLASS = 100  # last 100 of each class are held out -> 5,000 train / 1,000 test
RENDER_SIZE = 40     # strokes are rasterised on a 40x40 canvas, then preprocessed
DIGIT_PX = 28        # nominal digit height on that canvas before random affine

# Augmentation ranges (chosen by eye so samples look like plausible handwriting;
# they are assumptions, not measurements of real handwriting). v1 used milder
# ranges (14 deg, 0.28 shear, no trimming): it scored 99.9% on its own test set and
# 97.6% from just 100 training images, i.e. too easy to teach overfitting with.
# These wider ranges give 99.4% and make the playground's lessons visible.
ROTATE_DEG = 18.0          # +/- rotation
SHEAR = 0.36               # +/- horizontal shear (italic slant)
SCALE_X = (0.62, 1.3)     # independent x/y scale changes the aspect ratio
SCALE_Y = (0.85, 1.15)
STROKE_WIDTH = (0.06, 0.2)  # pen width as a fraction of digit height
ELASTIC_AMP = 0.075        # amplitude of the smooth "elastic" warp (fraction of height)
TREMOR = 0.008             # per-point hand tremor (fraction of height)
STROKE_TRIM = 0.1          # up to this share of a stroke may be cut off at either end (sloppy pen)
NOISE_PROB = 0.35          # share of samples that get mild pixel noise
NOISE_SIGMA = 0.05         # std-dev of that noise (intensity units, 0..1)

# ---- the network ----------------------------------------------------------
SIZES = [GRID * GRID, 64, 32, 10]   # 256 -> 64 -> 32 -> 10 (18.8k weights)
ACTIVATION = "relu"
TRAIN_SEED = 7
EPOCHS = 14
BATCH = 32
LR = 0.06
LR_DECAY = 0.85      # learning rate multiplied by this after every epoch
MOMENTUM = 0.9
L2 = 1e-4

# ---- live training playground defaults (small so an epoch takes ~1 s) -----
LIVE_DEFAULTS = {
    "lr": 0.05, "hidden": 32, "hidden2": 0, "epochs": 8, "batch": 32,
    "momentum": 0.9, "l2": 1e-4, "activation": "relu", "train_size": 2000,
}
LIVE_LIMITS = {
    "lr": (0.0005, 2.0), "hidden": (2, 128), "hidden2": (0, 64), "epochs": (1, 40),
    "batch": (1, 256), "momentum": (0.0, 0.99), "l2": (0.0, 0.1),
    "train_size": (100, 5000),
}
LIVE_WEIGHT_TILES = 16   # first-layer weight images streamed to the UI

# ---- teach-it mode ----------------------------------------------------------
TEACH_MAX = 200          # cap on stored user examples
FINETUNE_STEPS = 30      # default SGD steps per "Teach it" click
FINETUNE_LR = 0.03
FINETUNE_REPLAY = 48     # original training images mixed into each step (limits forgetting)
