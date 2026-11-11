"""Offline: per segment of W-CTRL-EFFECT exposure/gain runs, JPEG bytes/frame, luma mean, temporal noise.
No camera access. Reads suite JSON + raw frames from skellycam-raw."""
import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

SUITE = Path(r"C:\Users\Dom\GitHub\freemocap\skellycam\research\usb_cameras\results\windows\Gerald\suite_20261111T040003Z")
RAW = Path(r"C:\Users\Dom\Documents\skellycam-raw\results\windows\Gerald\suite_20261111T040003Z\W-CTRL-EFFECT")
DIRS = {"1532": "usbvideodevice_1532-0e05_4", "046d:0843": "logitechwebcam_046d-0843_8",
        "4c4a": "usbcamera_4c4a-4a55_2", "046d:085c": "c922prostreamw_046d-085c_C922SN01"}
W, H = 1280, 720


def load_rows(d):
    return [json.loads(l) for l in open(d / "frames.jsonl") if l.strip()]


def y_of(blob, raw):
    if raw:
        a = np.frombuffer(blob, np.uint8)
        if a.size == W * H * 2:
            return a.reshape(H, W, 2)[:, :, 0].astype(np.float32)
        if a.size == W * H * 3 // 2:
            return a[: W * H].reshape(H, W).astype(np.float32)
        return None
    return np.asarray(Image.open(io.BytesIO(blob)).convert("L"), dtype=np.float32)


def roi(y):
    h, w = y.shape
    return y[int(0.1 * h): int(0.9 * h), int(0.1 * w): int(0.9 * w)]


def seg_stats(d, rows, a, b):
    mid = a + (b - a) / 2
    sel = [r for r in rows if mid <= r["qpc_ns"] < b]
    by = [r["bytes"] for r in sel]
    raw = bool(sel) and not sel[0].get("soi", True)
    saved = [r for r in sel if "mjpeg_offset" in r]
    ys = []
    with open(d / "frames.mjpeg", "rb") as f:
        for r in saved:
            f.seek(r["mjpeg_offset"])
            y = y_of(f.read(r["mjpeg_len"]), raw)
            if y is not None:
                ys.append(roi(y))
    out = {"n_frames": len(sel), "bytes_mean": float(np.mean(by)) if by else None, "raw": raw,
           "n_saved": len(ys)}
    if ys:
        out["luma"] = float(np.mean([y.mean() for y in ys]))
    if len(ys) >= 2:
        import cv2
        m = np.mean(ys, axis=0)
        gx = cv2.Sobel(m, cv2.CV_32F, 1, 0, ksize=3); gy = cv2.Sobel(m, cv2.CV_32F, 0, 1, ksize=3)
        gm = cv2.blur(np.hypot(gx, gy), (9, 9))
        flat = gm < 6.0                       # flat areas: no edges, so focus/vibration cannot change them
        unclipped = (m > 8) & (m < 247)
        msk = flat & unclipped
        out["flat_frac"] = float(msk.mean())
        diffs = [y1 - y0 for y0, y1 in zip(ys, ys[1:])]
        out["noise_all"] = float(np.mean([dd.std() for dd in diffs]) / np.sqrt(2))
        if msk.sum() > 1000:
            out["noise_flat"] = float(np.mean([dd[msk].std() for dd in diffs]) / np.sqrt(2))
            out["luma_flat"] = float(m[msk].mean())
            bins = {}
            for lo, hi in ((20, 60), (60, 100), (100, 140), (140, 180), (180, 230)):
                bm = msk & (m >= lo) & (m < hi)
                if bm.sum() > 2000:
                    bins[f"{lo}-{hi}"] = round(float(np.mean([dd[bm].std() for dd in diffs]) / np.sqrt(2)), 3)
            out["noise_bins"] = bins
        out["grad"] = float(np.abs(np.diff(m, axis=1)).mean())
    return out


def bounds_ds(run, rows):
    sets = run["sets"]
    t_first, t_last = rows[0]["qpc_ns"], rows[-1]["qpc_ns"]
    s0 = t_first
    if run.get("fix0") and isinstance(run["fix0"].get("t_end_ns"), (int, float)):
        s0 = max(t_first, run["fix0"]["t_end_ns"] + 150e6)
    starts = [s0] + [x["t_end_ns"] + 150e6 for x in sets[1:]]
    ends = [x["t_start_ns"] for x in sets[1:]] + [t_last + 1]
    return list(zip(starts, ends))


def bounds_mf(d, name, nvals, rows):
    s = json.load(open(d / "summary.json"))
    ev = [e for e in s.get("schedule") or [] if str(e.get("control", "")).endswith(name) and (e.get("at_ms") or 0) > 0]
    cuts = [e.get("applied_qpc_ns") for e in ev]
    edges = [rows[0]["qpc_ns"]] + cuts + [rows[-1]["qpc_ns"] + 1]
    return list(zip(edges[:-1], edges[1:]))


def main():
    eff = json.load(open(SUITE / "W-CTRL-EFFECT.json"))
    res = []
    for key, cam in eff["measurements"]["cameras"].items():
        sub = {"1532:0e05": DIRS["1532"], "046d:0843": DIRS["046d:0843"], "4c4a:4a55": DIRS["4c4a"], "046d:085c": DIRS["046d:085c"]}[":".join(key.split(":")[:2])]
        for path, pd in cam["paths"].items():
            for name in ("exposure", "gain"):
                g = pd.get("controls", {}).get(name)
                if not g:
                    continue
                for i, run in enumerate(g["runs"]):
                    d = RAW / sub / f"{path}_{name}_r{i}"
                    if not (d / "frames.jsonl").exists():
                        continue
                    rows = load_rows(d)
                    if not rows:
                        continue
                    b = bounds_ds(run, rows) if path == "ds" else bounds_mf(d, name, len(run["values"]), rows)
                    for j, (a, z) in enumerate(b):
                        st = seg_stats(d, rows, a, z)
                        st.update(cam=cam["name"], path=path, control=name, run=i, seg=j,
                                  value=run["values"][j], fixed=run.get("fixed"),
                                  state_gain=(run.get("state_at_start") or {}).get("gain"),
                                  suite_metric=(run.get("metric_values") or [None] * 3)[j])
                        res.append(st)
                        print(json.dumps({k2: (round(v2, 2) if isinstance(v2, float) else v2) for k2, v2 in st.items()}),
                              flush=True)
    json.dump(res, open(Path(sys.argv[1]), "w"), indent=1)


if __name__ == "__main__":
    main()
