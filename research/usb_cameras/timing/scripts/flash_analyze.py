# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26", "opencv-python-headless==4.10.0.84"]
# ///
"""Screen-flash ground truth: per-frame error of every camera timestamp source vs. the light actually on the screen.

Usage:
    uv run --script research/usb_cameras/timing/scripts/flash_analyze.py
        --display DISPLAY_DIR [--display DISPLAY_DIR2 ...]   (flash_timecode output dirs: display.jsonl/.session.json)
        --capture CAPTURE_DIR                                 (mf_uvc_timing --save-mjpeg output, or any backend that
                                                               writes <key>.frames.jsonl + <key>.mjpeg with
                                                               mjpeg_offset/payload_bytes per frame)
        [--exposure-ms KEY=MS ...] [--out result.json]

Method
  Display: each Present shows level 0/1 over the whole monitor; DXGI frame statistics give the vblank QPC time at which
  present_count N reached the screen, so the light signal s(t) is known (piecewise constant between vblanks; the
  scan-out position of the rows the camera sees adds a constant <= one refresh, absorbed into the fitted offset).
  Camera: per frame, mean brightness y_k of the pixels that flicker most (auto ROI, a narrow band of image rows, so the
  rolling-shutter row time is ~constant). Model: frame k integrates s(t) over [X_k + d, X_k + d + E] where X_k is the
  timestamp under test, E the exposure time and d a per-source constant. d is fit by maximising corr(y, predicted);
  then, for every frame whose exposure window contains exactly one transition (at vblank time T), the measured
  fraction gives the exposure start exactly: rising w0 = T - E*(1 - f), falling w0 = T - E*f, with f the linearised
  brightness (camera tone curve modelled as f = y_norm**gamma, gamma fitted). e_k = (w0_k - X_k) - median is the
  per-frame error of that timestamp source. std(e_k) is directly comparable between sources and cameras.
  When several displays are given (one flash_timecode per monitor, different seeds) the display whose sequence
  correlates best with the camera is used, which also identifies which monitor each camera sees.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import platform
import socket
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import analyze_frames as af  # noqa: E402


def load_display(d: Path) -> dict:
    recs = [json.loads(l) for l in (d / "display.jsonl").open()]
    ses = json.loads((d / "display.session.json").read_text())
    pres = [r for r in recs if r["type"] == "present"]
    st = [r for r in recs if r["type"] == "stats"]
    if len(st) < 10:
        # flash_timecode_py.py: no vblank statistics -> fit a periodic clock to flip-return times
        tr = np.array([r["present_return_ns"] for r in pres], float)
        pf = af.periodic_fit(tr.astype(np.int64))
        P = pf["period_ms"] * 1e6
        n = np.round((tr - tr[0]) / P)
        a0, P2, resid = af.linfit(n, tr)
        lev = np.array([r["level"] for r in pres], float)
        return {"dir": str(d), "session": ses, "t_on": a0 + P2 * n, "level": lev, "period_ns": P2,
                "vblank_fit_resid_us": af.stats(resid, 1e-3), "refresh_glitches": int(np.sum(np.diff(n) != 1)),
                "presents": len(pres), "stats_samples": 0, "timing": "flip-return periodic fit"}
    # refresh index of each stats sample, and linear vblank clock
    src = np.array([r["sync_refresh_count"] for r in st], float)
    sq = np.array([r["sync_qpc_ns"] for r in st], float)
    a, P, resid = af.linfit(src, sq)
    # present_count -> refresh index at which it was first shown
    pc = np.array([r["present_count"] for r in st]); prc = np.array([r["present_refresh_count"] for r in st])
    off = prc - pc  # constant if no glitches
    glitches = int(np.sum(np.diff(off) != 0))
    pcs = np.array([r["present_count"] for r in pres]); lev = np.array([r["level"] for r in pres])
    # interpolate offset for presents without their own stats sample (nearest earlier stats sample)
    idx = np.clip(np.searchsorted(pc, pcs, side="right") - 1, 0, len(pc) - 1)
    refresh = pcs + off[idx]
    t_on = a + P * refresh
    order = np.argsort(t_on)
    return {"dir": str(d), "session": ses, "t_on": t_on[order], "level": lev[order].astype(float), "period_ns": P,
            "vblank_fit_resid_us": af.stats(resid, 1e-3), "refresh_glitches": glitches, "presents": len(pres),
            "stats_samples": len(st)}


def cumulative(disp: dict):
    t = disp["t_on"]; s = disp["level"]
    # S(t) = integral of s from t[0]; piecewise linear with knots at t
    seg = np.diff(t) * s[:-1]
    S = np.concatenate([[0.0], np.cumsum(seg)])
    return t, s, S


def window_mean(disp_c, w0: np.ndarray, E: float) -> np.ndarray:
    t, s, S = disp_c

    def Sint(x):
        i = np.clip(np.searchsorted(t, x, side="right") - 1, 0, len(t) - 1)
        return S[i] + (x - t[i]) * s[i]
    return (Sint(w0 + E) - Sint(w0)) / E


def roi_signal(frames: list[dict], mjpeg: Path) -> tuple[np.ndarray, dict]:
    data = mjpeg.read_bytes()
    imgs = []
    for r in frames:
        o, n = r["mjpeg_offset"], r["payload_bytes"]
        im = cv2.imdecode(np.frombuffer(data, np.uint8, n, o), cv2.IMREAD_REDUCED_GRAYSCALE_8)
        imgs.append(im.astype(np.float32) if im is not None else None)
    shape = next(i.shape for i in imgs if i is not None)
    stack = np.stack([i if i is not None else np.full(shape, np.nan, np.float32) for i in imgs])
    sd = np.nanstd(stack, axis=0)
    H, W = sd.shape
    # compact block (not a full row band): a portrait monitor scans out horizontally, so a block keeps both the
    # camera rolling-shutter row time and the display scan-out time ~constant across the ROI
    bh, bw = max(2, H // 24), max(2, W // 24)
    c = np.pad(np.cumsum(np.cumsum(sd, 0), 1), ((1, 0), (1, 0)))
    box = (c[bh:, bw:] - c[:-bh, bw:] - c[bh:, :-bw] + c[:-bh, :-bw]) / (bh * bw)
    r0, c0 = np.unravel_index(int(np.argmax(box)), box.shape)
    sub = sd[r0:r0 + bh, c0:c0 + bw]
    m = np.zeros_like(sd, bool)
    m[r0:r0 + bh, c0:c0 + bw] = sub >= 0.5 * sub.max()
    y = np.array([np.nanmean(f[m]) for f in stack])
    info = {"decoded_shape": list(sd.shape), "roi_rows": [int(r0), int(r0 + bh)], "roi_cols": [int(c0), int(c0 + bw)],
            "roi_row_center_frac": float((r0 + bh / 2) / H), "roi_col_center_frac": float((c0 + bw / 2) / W),
            "roi_pixels": int(m.sum()), "roi_temporal_std": float(sd[m].mean()), "median_pixel_std": float(np.median(sd))}
    return y, info


def fit_source(X: np.ndarray, y: np.ndarray, disp: dict, E: float) -> dict:
    dc = cumulative(disp)
    ok = np.isfinite(y) & np.isfinite(X)
    X = np.where(np.isfinite(X), X, np.nanmedian(np.diff(X)) * np.arange(len(X)) + np.nanmin(X))  # placeholder, excluded by ok
    # coarse search of d (offset timestamp -> exposure start) in [-400, +100] ms
    best = (-2.0, 0.0)
    for d in np.arange(-400e6, 100e6, 0.5e6):
        p = window_mean(dc, X + d, E)
        c = np.corrcoef(p[ok], y[ok])[0, 1] if np.std(p[ok]) > 0 else -1
        if c > best[0]:
            best = (c, d)
    for d in np.arange(best[1] - 1e6, best[1] + 1e6, 0.02e6):
        p = window_mean(dc, X + d, E)
        c = np.corrcoef(p[ok], y[ok])[0, 1]
        if c > best[0]:
            best = (c, d)
    corr, d0 = best
    lo, hi = np.nanpercentile(y, 2), np.nanpercentile(y, 98)
    yn = np.clip((y - lo) / (hi - lo), 0, 1)
    t, s, _ = dc
    trans_t = t[1:][np.diff(s) != 0]; trans_dir = np.diff(s)[np.diff(s) != 0]
    w0 = X + d0
    out = {"corr": float(corr), "offset_ms": d0 / 1e6, "E_ms": E / 1e6}
    # frames with exactly one transition inside the window (margin 10% of E so the fraction is informative)
    i0 = np.searchsorted(trans_t, w0); i1 = np.searchsorted(trans_t, w0 + E)
    single = (i1 - i0 == 1) & ok
    k = np.flatnonzero(single)
    Tk = trans_t[i0[k]]; up = trans_dir[i0[k]] > 0
    best_g = None
    for g in np.arange(0.4, 3.01, 0.05):
        f = yn[k] ** g
        sel = (f > 0.08) & (f < 0.92)
        w = np.where(up, Tk - E * (1 - f), Tk - E * f)
        e = (w - X[k])[sel]
        if e.size < 8:
            continue
        sig = np.std(e - np.median(e))
        if best_g is None or sig < best_g[0]:
            best_g = (sig, g)
    if best_g is None:
        out["per_frame"] = None
        return out
    g = best_g[1]
    f = yn[k] ** g
    sel = (f > 0.08) & (f < 0.92)
    w = np.where(up, Tk - E * (1 - f), Tk - E * f)
    e = (w - X[k])[sel]
    med = np.median(e)
    eu = e[up[sel]] - med; ed = e[~up[sel]] - med
    mad = 1.4826 * np.median(np.abs(e - med))
    out["per_frame"] = {"gamma": float(g), "n": int(e.size), "frames_total": int(len(X)),
                        "offset_median_ms": med / 1e6, "err_std_us": float(np.std(e - med) / 1e3),
                        "err_mad_sigma_us": float(mad / 1e3), "err_p05_p95_us": [float(np.percentile(e - med, 5) / 1e3), float(np.percentile(e - med, 95) / 1e3)],
                        "rising_mean_us": float(eu.mean() / 1e3) if eu.size else None, "falling_mean_us": float(ed.mean() / 1e3) if ed.size else None,
                        "n_rising": int(eu.size), "n_falling": int(ed.size)}
    out["_gt"] = (k[sel], w[sel])  # frame indices + measured exposure-start times (host ns), popped before output
    return out


def vs_ground_truth(X: np.ndarray, gt) -> dict:
    """Evaluate a timestamp source against exposure-start times measured with the best source's frame selection."""
    k, w = gt
    e = w - X[k]
    e = e[np.isfinite(e)]
    med = np.median(e)
    return {"n": int(e.size), "offset_ms": med / 1e6, "err_std_us": float(np.std(e - med) / 1e3),
            "err_mad_sigma_us": float(1.4826 * np.median(np.abs(e - med)) / 1e3),
            "err_min_max_us": [float((e - med).min() / 1e3), float((e - med).max() / 1e3)]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--display", action="append", required=True)
    ap.add_argument("--capture", required=True)
    ap.add_argument("--exposure-ms", action="append", default=[], help="KEYSUBSTR=ms (overrides the session exposure)")
    ap.add_argument("--skip-first", type=int, default=5)
    ap.add_argument("--out")
    a = ap.parse_args()
    disps = [load_display(Path(d)) for d in a.display]
    res = {"test": "flash_analyze", "platform": sys.platform, "hostname": socket.gethostname(),
           "utc_started": dt.datetime.now(dt.timezone.utc).isoformat(), "command": " ".join(sys.argv),
           "environment": {"python": platform.python_version(), "numpy": np.__version__, "opencv": cv2.__version__},
           "displays": [{k: v for k, v in d.items() if k not in ("t_on", "level")} for d in disps], "cameras": []}
    for fj in sorted(Path(a.capture).glob("*.frames.jsonl")):
        key = fj.name[: -len(".frames.jsonl")]
        mj = fj.with_name(key + ".mjpeg")
        if not mj.exists():
            continue
        ses = json.loads(fj.with_name(key + ".session.json").read_text()) if fj.with_name(key + ".session.json").exists() else {}
        rows = af.load(fj)[a.skip_first:]
        if len(rows) < 20:
            res["cameras"].append({"camera_key": key, "error": f"only {len(rows)} frames captured"}); continue
        ana = af.analyze(rows, None, 0, 32)
        arrays = ana.pop("_arrays", None)
        E = None
        for kv in a.exposure_ms:
            ks, v = kv.split("=")
            if ks.lower() in key.lower():
                E = float(v) * 1e6
        exp = ses.get("controls", {}).get("exposure_log2", {})
        if E is None and exp.get("manual"):
            E = 2.0 ** exp["value"] * 1e9
        cam = {"camera_key": key, "friendly_name": ses.get("friendly_name"), "exposure_control": exp, "E_ms_used": E / 1e6 if E else None}
        y, info = roi_signal(rows, mj)
        cam["roi"] = info
        if E is None:
            cam["error"] = "exposure unknown (pass --exposure-ms)"; res["cameras"].append(cam); continue
        srcs = {}
        for name, X in arrays["sources"].items():  # frames without a valid mapping (start of SCR window) -> NaN
            m = arrays["masks"].get(name)
            Xf = X.astype(float)
            if m is not None:
                Xf[~m] = np.nan
            srcs[name] = Xf
        # choose the display that matches best using host_arrival
        scores = []
        for i, d in enumerate(disps):
            scores.append(fit_source(srcs["host_arrival"], y, d, E)["corr"])
        di = int(np.argmax(scores))
        cam["display_corr"] = scores; cam["display_used"] = disps[di]["session"].get("output")
        cam["screen_visible"] = bool(scores[di] > 0.5)
        cam["sources"] = {}
        gts = {}
        for name, X in srcs.items():
            cam["sources"][name] = fit_source(X, y, disps[di], E)
            gts[name] = cam["sources"][name].pop("_gt", None)
        ok_src = [n for n in srcs if cam["sources"][n].get("per_frame") and gts[n] is not None]
        if ok_src:
            ref = min(ok_src, key=lambda n: cam["sources"][n]["per_frame"]["err_std_us"])
            cam["ground_truth_reference_source"] = ref
            for name, X in srcs.items():
                cam["sources"][name]["vs_ground_truth"] = vs_ground_truth(X, gts[ref])
        res["cameras"].append(cam)
        print(f"== {key} display={cam['display_used']} corr={scores} roi={info['roi_rows']} E={E/1e6:.2f}ms")
        for name, r in cam["sources"].items():
            pf = r.get("per_frame") or {}
            print(f"   {name:30s} corr={r['corr']:.3f} offset={r['offset_ms']:9.3f} ms  per-frame err std={pf.get('err_std_us', float('nan')):9.1f} us"
                  f" mad={pf.get('err_mad_sigma_us', float('nan')):8.1f} us n={pf.get('n')} gamma={pf.get('gamma')}"
                  f" | vs GT std={r.get('vs_ground_truth', {}).get('err_std_us', float('nan')):9.1f} us")
    # cross-camera offsets per source (same display only)
    cams = [c for c in res["cameras"] if c.get("sources") and c.get("screen_visible")]
    cross = {}
    for i in range(len(cams)):
        for j in range(i + 1, len(cams)):
            for name in set(cams[i]["sources"]) & set(cams[j]["sources"]):
                pi, pj = cams[i]["sources"][name].get("vs_ground_truth"), cams[j]["sources"][name].get("vs_ground_truth")
                if pi and pj:
                    cross[f"{cams[i]['camera_key']}|{cams[j]['camera_key']}|{name}"] = {
                        "offset_diff_ms": pi["offset_ms"] - pj["offset_ms"],
                        "combined_err_std_us": float(np.hypot(pi["err_std_us"], pj["err_std_us"]))}
    res["cross_camera"] = cross
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=2, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main())
