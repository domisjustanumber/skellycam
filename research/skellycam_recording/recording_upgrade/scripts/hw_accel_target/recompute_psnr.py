# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6"]
# ///
"""Recompute decode-back PSNR (method v2: raw sample values, no range conversion, reference = the converted frames
actually fed to the encoder) for every OK record in results/hw_accel_target/functional_pyav19.json, from the media
files on disk. Keeps the v1 result as decode_back_v1. Also records fed_frame0 (format, range tag, plane-0 min/max).
  uv run --script research/skellycam_recording/recording_upgrade/scripts/hw_accel_target/recompute_psnr.py
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import pyav19_functional as pf  # noqa: E402
from av.video.frame import PictureType  # noqa: E402,F401

src = pf.load_inputs()
P = pf.RESULTS / "functional_pyav19.json"
d = json.loads(P.read_text(encoding="utf-8"))
cache = {}
n_done = 0
for r in d["encode"]:
    if not r.get("ok") or "decode_back" not in r:
        continue
    inp = r.get("input", "yuy2_1080p")
    key = (inp, r["pix_fmt_in"])
    if key not in cache:
        cache[key] = pf.conv(src[inp], r["pix_fmt_in"])
    frames = cache[key]
    fed = [frames[i % len(frames)] for i in range(r["frames_requested"])]
    f0 = frames[0]
    y0 = np.frombuffer(f0.planes[0], np.uint8).reshape(f0.height, f0.planes[0].line_size)[:, :f0.planes[0].width]
    r["fed_frame0"] = {"format": f0.format.name, "color_range_tag": int(f0.color_range or 0),
                       "plane0_min": int(y0.min()), "plane0_max": int(y0.max())}
    path = pf.OUT / f"{r['encoder']}__{r['tag']}.{r['container']}"
    r.setdefault("decode_back_v1", r["decode_back"])
    r["decode_back"] = pf.decode_back_check(path, fed)
    r["decode_back"]["psnr_method"] = "v2 raw sample values, reference = converted frames fed"
    n_done += 1
    print(r["encoder"], r["tag"], r["decode_back"].get("psnr_y_mean"), r["decode_back"].get("psnr_all_mean"),
          r["decode_back"].get("error", ""))
d["psnr_recomputed_v2"] = n_done
P.write_text(json.dumps(d, indent=1, default=str), encoding="utf-8")
pf.write_md(d)
