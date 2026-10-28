# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow>=10", "numpy"]
# ///
"""Recompute comparable per-camera statistics from prior-art frame logs (old and new runs alike).

For every frames_*.jsonl under each given result dir:
  n, n_valid_jpeg, fps (frames[5:] by host arrival), arrival-interval histogram in 4 ms bins,
  fraction of frames whose arrival phase mod 16.000 ms falls in the modal 1-ms bin,
  distinct os_timestamp deltas (100 ns units; top 3), median arrival-minus-os_timestamp,
  linear drift of (arrival - os_timestamp) in ms/s (least squares over frames[5:]), payload median.
For every sample*.jpg: mean luma (Pillow 'L'), so low light can be checked against fps. With
--move-samples DIR the sample JPEGs are moved out of the repo after measuring (privacy).

RUN:
  uv run --script research/usb_cameras/verify_prior_art/rerun_compare.py --out <summary.json> <result_dir> [<result_dir> ...]
"""
from __future__ import annotations

import argparse
import collections
import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image


def frame_stats(p: Path) -> dict:
    fr = [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]
    out = {"file": p.name, "n": len(fr), "n_valid_jpeg": sum(bool(x.get("is_valid_jpeg")) for x in fr)}
    if len(fr) < 8:
        return out
    f5 = fr[5:]
    arr = np.array([x["host_arrival_ns"] for x in f5], dtype=np.int64)
    out["fps_frames5on"] = round((len(arr) - 1) / ((arr[-1] - arr[0]) / 1e9), 3)
    d = np.diff(np.array([x["host_arrival_ns"] for x in fr], dtype=np.int64)) / 1e6
    hist = collections.Counter(int(round(v / 4.0)) * 4 for v in d)
    out["arrival_interval_hist_4ms"] = {str(k): v for k, v in sorted(hist.items())}
    ph = (arr % 16_000_000) // 1_000_000
    out["phase16_modal_bin_fraction"] = round(collections.Counter(ph.tolist()).most_common(1)[0][1] / len(ph), 3)
    os_ts = [x.get("os_timestamp_ns") for x in f5]
    if all(v is not None for v in os_ts):
        os_a = np.array(os_ts, dtype=np.int64)
        dd = np.diff(os_a)
        out["os_ts_delta_top3_100ns"] = [[int(k) // 100, c] for k, c in collections.Counter(dd.tolist()).most_common(3)]
        off = (arr - os_a) / 1e6
        t = (arr - arr[0]) / 1e9
        slope, icpt = np.polyfit(t, off, 1)
        out["arrival_minus_os_ms_median"] = round(float(np.median(off)), 3)
        out["arrival_minus_os_drift_ms_per_s"] = round(float(slope), 3)
        out["arrival_minus_os_resid_sd_ms"] = round(float(np.std(off - (slope * t + icpt))), 3)
        osd = np.diff(os_a) / 1e6
        out["os_ts_interval_ms_min_med_max"] = [round(float(osd.min()), 3), round(float(np.median(osd)), 3), round(float(osd.max()), 3)]
    out["payload_bytes_median"] = int(np.median([x["payload_bytes"] for x in fr]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--move-samples", default=None)
    a = ap.parse_args()
    res = {}
    for d in a.dirs:
        dp = Path(d)
        ent = {"frames": [frame_stats(p) for p in sorted(dp.glob("frames_*.jsonl"))], "samples": []}
        for s in sorted(dp.glob("sample*.jpg")):
            try:
                im = Image.open(s).convert("L")
                ent["samples"].append({"file": s.name, "mean_luma": round(float(np.asarray(im).mean()), 1),
                                       "w_h": list(im.size)})
            except Exception as e:  # noqa: BLE001
                ent["samples"].append({"file": s.name, "error": repr(e)})
            if a.move_samples:
                dst = Path(a.move_samples) / dp.name
                dst.mkdir(parents=True, exist_ok=True)
                shutil.move(str(s), dst / s.name)
                ent["samples"][-1]["moved_to"] = str(dst / s.name)
        res[str(dp)] = ent
    Path(a.out).write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
