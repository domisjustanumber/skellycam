# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy", "msgspec==0.21.1"]
# ///
"""Verifier check (functional, sizes only): how much the JSONL/.skov/MessagePack size ratio depends on the
synthetic data being pre-rounded to 0.01 px. Variant: same frames, coordinates replaced by float32 values with
sub-pixel noise (what a tracker's float32 output becomes when json.dumps'd without rounding)."""
import json, sys, tempfile, copy
from pathlib import Path
import numpy as np
sys.path.insert(0, r"C:/Users/Dom/GitHub/freemocap/skellycam/research/skellycam_recording/recording_upgrade/scripts/overlays")
import overlay_model as M
n, W, H = 300, 1280, 720
base = M.make_frames(n, W, H, "all")
rng = np.random.default_rng(0)
def f32(a):
    return (a + rng.uniform(-0.005, 0.005, a.shape)).astype(np.float32).astype(np.float64)
raw = []
for fd in base:
    g = copy.deepcopy(fd)
    if g.skel is not None: g.skel = f32(g.skel)
    if g.ch_xy is not None: g.ch_xy = f32(g.ch_xy)
    if g.aruco: g.aruco = [(m, f32(c)) for m, c in g.aruco]
    raw.append(g)
hdr = M.header(W, H, 30.0, "all")
tmp = Path(tempfile.mkdtemp()); out = {}
for label, frames in (("rounded_0.01px (as in study)", base), ("float32_unrounded", raw)):
    out[label] = {}
    for fmt, (Wr, R) in M.DATA_FORMATS.items():
        p = tmp / f"{fmt}{Wr.ext}"; w = Wr(p, hdr)
        for fd in frames: w.write(fd)
        w.close(); out[label][fmt] = round(p.stat().st_size / n, 1)
    out[label]["jsonl_over_bin"] = round(out[label]["jsonl"] / out[label]["bin"], 2)
print(json.dumps(out, indent=1))
