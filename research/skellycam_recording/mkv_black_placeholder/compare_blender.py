"""Compare the Blender renders with the full file's renders. Usage: python compare_blender.py MEDIA_DIR

q = 25 % render of every n; x = 100 % render of a few n. Camera rows: max abs difference to the full file's
render of the same n (0 = equal). Placeholder rows: max pixel value. The full file's q renders are identified by
the drawn number (nearest 64x48 reference) and must show row n.
"""

import json
import sys
from pathlib import Path

import cv2
import numpy as np

d = Path(sys.argv[1])
bo = d / "blender_out"
files = json.loads((d / "files.json").read_text())["files"]
bres = json.loads((d / "blender_results.json").read_text())


def load(name, kind, n):
    p = bo / f"{name}__{kind}__{n:03d}.png"
    return cv2.imread(str(p), cv2.IMREAD_COLOR) if p.exists() else None


def ident(img, thumbs):
    g = cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (64, 48), interpolation=cv2.INTER_AREA).astype(np.float32)
    return int(np.argmin(np.abs(thumbs - g).mean(axis=(1, 2))))


summary = {}
for f in files:
    name, cfg, ph = f["file"][:-4], f["cfg"], set(f["ph_rows"])
    full = f"{cfg}__full"
    thumbs = np.load(d / f"{cfg}_thumbs.npy")
    r = {"durations": [bres[name][k] for k in ("movieclip_frame_duration", "image_frame_duration", "strip_duration")],
         "errors": bres[name]["errors"]}
    if f["pattern"] == "full":
        r["drawn_not_n"] = [n for n in range(300) if ident(load(name, "q", n), thumbs) != n]
    bad, ph_max = [], 0
    for n in range(300):
        a = load(name, "q", n)
        if a is None:
            bad.append((n, "missing png"))
        elif n in ph:
            ph_max = max(ph_max, int(a.max()))
        else:
            diff = int(np.abs(a.astype(int) - load(full, "q", n).astype(int)).max())
            if diff:
                bad.append((n, diff, ident(a, thumbs)))
    r["q_camera_rows_differ"] = bad[:12]
    r["q_n_differ"] = len(bad)
    r["q_placeholder_max"] = ph_max
    x = {}
    for p in sorted(bo.glob(f"{name}__x__*.png")):
        n = int(p.stem.split("__")[-1])
        a = cv2.imread(str(p), cv2.IMREAD_COLOR)
        x[n] = f"black max {int(a.max())}" if n in ph else f"maxdiff {int(np.abs(a.astype(int) - load(full, 'x', n).astype(int)).max())}"
    r["x"] = x
    summary[name] = r
    print(name, json.dumps(r))
(d / "blender_compare.json").write_text(json.dumps(summary, indent=1))
