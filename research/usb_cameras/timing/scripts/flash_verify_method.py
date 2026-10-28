# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26", "opencv-python-headless==4.10.0.84"]
# ///
"""Method / circularity checks for flash_analyze.py results (no camera needed; re-analyses an existing capture).

Usage:
    uv run --script research/usb_cameras/timing/scripts/flash_verify_method.py
        --display DISPLAY_DIR --capture CAPTURE_DIR [--mjpeg-dir DIR] --out verify.json

What it checks (see research/usb_cameras/timing/VERIFY_method.md):
  A. Reproduces flash_analyze's numbers with the same code path (import, not a copy).
  B. Ground-truth (GT) sensitivity: GT exposure-start times w_k are rebuilt with
       - the frame selection of each candidate reference source (flash_analyze uses the best-scoring source),
       - a FIXED tone-curve gamma (flash_analyze tunes gamma to minimise the reference source's own error std),
       - a reference that uses no device timestamp at all (frame index + host-arrival lower envelope),
       - exposure E = 6.5 / 7.8125 / 9.5 ms.
  C. Extra timestamp sources that test what the "uvc_pts" score actually means:
       seq_periodic_env      host arrival lower-envelope fit vs frame index (assumes a perfectly periodic sensor; uses
                             no device timestamp). If this scores like PTS, the PTS result only shows "sensor is periodic".
       pts_nominal_clock     PTS / nominal Hz, offset only (no fitted slope) -> exposes device-clock drift vs QPC
       pts_env_first_half    PTS->host lower-envelope fit on the FIRST half only, evaluated on the second half (holdout)
       pts_env_causal        PTS->host lower-envelope fit on frames [0..i] only (online, causal), first 150 frames skipped
       pts_gt_fit            PTS->host fitted to the GT itself (explicitly circular; upper bound on PTS quality)
  D. Error-vs-time slope of every source vs GT (ppm) and std after removing that slope.
  E. Cross-camera offset difference with bootstrap 95% CI, and ROI dependence of the offset (per-block offsets),
     i.e. how much of a per-camera "offset" is scene geometry (display scan-out position, rolling-shutter row).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import socket
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[2] / "tools"))
sys.path.insert(0, str(HERE.parent))
import analyze_frames as af  # noqa: E402
import flash_analyze as fa  # noqa: E402

RNG = np.random.default_rng(12345)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def gt_build(X: np.ndarray, y: np.ndarray, disp: dict, E: float, gamma: float | None, d0: float | None = None):
    """Same selection/linearisation as fa.fit_source, but gamma may be fixed. Returns (k, w, info)."""
    if d0 is None:
        r = fa.fit_source(X, y, disp, E)
        d0 = r["offset_ms"] * 1e6
        if gamma is None:
            if not r.get("per_frame"):
                return None
            gamma = r["per_frame"]["gamma"]
    ok = np.isfinite(y) & np.isfinite(X)
    lo, hi = np.nanpercentile(y, 2), np.nanpercentile(y, 98)
    yn = np.clip((y - lo) / (hi - lo), 0, 1)
    t, s, _ = fa.cumulative(disp)
    trans_t = t[1:][np.diff(s) != 0]; trans_dir = np.diff(s)[np.diff(s) != 0]
    Xs = np.where(ok, X, 0.0)
    w0 = Xs + d0
    i0 = np.searchsorted(trans_t, w0); i1 = np.searchsorted(trans_t, w0 + E)
    k = np.flatnonzero((i1 - i0 == 1) & ok)
    Tk = trans_t[i0[k]]; up = trans_dir[i0[k]] > 0
    f = yn[k] ** gamma
    sel = (f > 0.08) & (f < 0.92)
    w = np.where(up, Tk - E * (1 - f), Tk - E * f)
    return k[sel], w[sel], {"gamma": float(gamma), "d0_ms": d0 / 1e6, "n": int(sel.sum()), "up": up[sel], "f": f[sel]}


def evaluate(X: np.ndarray, gt, t0: float, subset: np.ndarray | None = None) -> dict | None:
    k, w = gt[0], gt[1]
    e = w - X[k]
    tt = (X[k] - t0) / 1e9
    m = np.isfinite(e)
    if subset is not None:
        m &= subset[k]
    e, tt = e[m], tt[m]
    if e.size < 8:
        return None
    med = np.median(e)
    # error-vs-time slope (ppm) and std after removing it
    b, a = np.polyfit(tt, e, 1)
    r = e - (a + b * tt)
    return {"n": int(e.size), "offset_ms": float(med / 1e6), "err_std_us": float(np.std(e - med) / 1e3),
            "err_mad_sigma_us": float(1.4826 * np.median(np.abs(e - med)) / 1e3),
            "err_min_max_us": [float((e - med).min() / 1e3), float((e - med).max() / 1e3)],
            "slope_ppm": float(b / 1e9 * 1e6), "err_std_after_slope_us": float(np.std(r) / 1e3)}


def boot_median(e: np.ndarray, n: int = 4000) -> tuple[float, float]:
    idx = RNG.integers(0, e.size, (n, e.size))
    meds = np.median(e[idx], axis=1)
    return float(np.percentile(meds, 2.5)), float(np.percentile(meds, 97.5))


def extra_sources(rows, srcs: dict, ana: dict) -> tuple[dict, dict]:
    host = np.array([r["host_arrival_ns"] for r in rows], dtype=np.float64)
    pts = af.unwrap(np.array([r["uvc_pts"] for r in rows], dtype=np.int64), 32).astype(np.float64)
    dp = np.diff(pts); med = np.median(dp)
    slot = np.concatenate([[0], np.cumsum(np.round(dp / med))])  # frame slot index from PTS gaps (drops -> gaps)
    seq = np.array([r["seq"] for r in rows], float); seq -= seq[0]
    info = {"pts_slot_equals_seq": bool(np.all(slot == seq)), "pts_slot_gaps": int(np.sum(np.diff(slot) != 1))}
    out = {}
    a, b = af.lower_envelope_fit(seq, host)
    out["seq_periodic_env"] = a + b * seq
    nom = ana["device_clock"]["nominal_hz"]
    x = pts / nom * 1e9
    out["pts_nominal_clock"] = x - x[0] + host[0]  # offset is irrelevant (median removed)
    n = len(pts); h = n // 2
    a, b = af.lower_envelope_fit(pts[:h], host[:h])
    out["pts_env_first_half"] = a + b * pts
    c = np.full(n, np.nan)
    for i in range(150, n):
        a, b = af.lower_envelope_fit(pts[: i + 1], host[: i + 1])
        c[i] = a + b * pts[i]
    out["pts_env_causal"] = c
    # robust alternative to lower_envelope_fit: line through per-1 s minima of (arrival - PTS/nominal)
    xp = pts / nom * 1e9
    lat = host - xp
    tsec = (host - host[0]) / 1e9
    cid = np.floor(tsec).astype(int)
    cm_t = np.array([tsec[cid == j][np.argmin(lat[cid == j])] for j in np.unique(cid)])
    cm_v = np.array([lat[cid == j].min() for j in np.unique(cid)])
    cm_end = np.array([tsec[cid == j].max() for j in np.unique(cid)])
    tr = cm_end <= tsec[h - 1]
    bb, aa = np.polyfit(cm_t[tr], cm_v[tr], 1)
    out["pts_chunkmin_first_half"] = xp + aa + bb * tsec
    c2 = np.full(n, np.nan)
    for i in range(n):
        m = cm_end < tsec[i]
        if m.sum() >= 5:
            bb, aa = np.polyfit(cm_t[m], cm_v[m], 1)
            c2[i] = xp[i] + aa + bb * tsec[i]
    out["pts_chunkmin_causal"] = c2

    def robust_fit(m):  # reject chunks whose minimum latency is > 3 ms above the median chunk minimum (start-up regime)
        mm = m & (cm_v <= np.median(cm_v[m]) + 3e6)
        bb, aa = np.polyfit(cm_t[mm], cm_v[mm], 1)
        return aa, bb
    aa, bb = robust_fit(tr)
    out["pts_chunkmin_robust_first_half"] = xp + aa + bb * tsec
    c3 = np.full(n, np.nan)
    for i in range(n):
        m = cm_end < tsec[i]
        if m.sum() >= 5:
            aa, bb = robust_fit(m)
            c3[i] = xp[i] + aa + bb * tsec[i]
    out["pts_chunkmin_robust_causal"] = c3
    info["chunk_min_latency_ms"] = [float(v / 1e6 - cm_v.min() / 1e6) for v in cm_v]
    info["nominal_hz"] = nom
    info["first_half_frames"] = h
    return out, {"info": info, "pts": pts, "host": host, "half": h}


def block_offsets(rows, mjpeg: Path, X: np.ndarray, disp: dict, E: float, nb_r: int = 6, nb_c: int = 8) -> list[dict]:
    """Offset (median GT - X) of one source for a grid of image blocks that see the flicker."""
    data = mjpeg.read_bytes()
    imgs = []
    for r in rows:
        im = cv2.imdecode(np.frombuffer(data, np.uint8, r["payload_bytes"], r["mjpeg_offset"]), cv2.IMREAD_REDUCED_GRAYSCALE_8)
        imgs.append(im.astype(np.float32) if im is not None else None)
    shape = next(i.shape for i in imgs if i is not None)
    st = np.stack([i if i is not None else np.full(shape, np.nan, np.float32) for i in imgs])
    sd = np.nanstd(st, axis=0)
    H, W = sd.shape
    res = []
    for bi in range(nb_r):
        for bj in range(nb_c):
            r0, r1 = bi * H // nb_r, (bi + 1) * H // nb_r
            c0, c1 = bj * W // nb_c, (bj + 1) * W // nb_c
            sub = sd[r0:r1, c0:c1]
            if sub.max() < 30:
                continue
            m = sub >= 0.7 * sub.max()
            y = np.array([np.nanmean(f[r0:r1, c0:c1][m]) for f in st])
            r = fa.fit_source(X, y, disp, E)
            gt = r.pop("_gt", None)
            if gt is None or r["corr"] < 0.8:
                continue
            ev = evaluate(X, gt, np.nanmin(X))
            res.append({"block": [bi, bj], "row_center_frac": (r0 + r1) / 2 / H, "col_center_frac": (c0 + c1) / 2 / W,
                        "pixels": int(m.sum()), "corr": r["corr"], "gamma": r["per_frame"]["gamma"] if r.get("per_frame") else None,
                        **({k: ev[k] for k in ("n", "offset_ms", "err_std_us")} if ev else {}), "_gt": gt})
    # GT self-consistency: the same frame measured through two different blocks. Timestamp X cancels, so
    # std(w_A - w_B - median) / sqrt(2) estimates the per-block GT noise (the part that is independent between blocks).
    pair = []
    for i in range(len(res)):
        for j in range(i + 1, len(res)):
            ka, wa = res[i]["_gt"]; kb, wb = res[j]["_gt"]
            common, ia, ib = np.intersect1d(ka, kb, return_indices=True)
            if common.size < 20:
                continue
            d = wa[ia] - wb[ib]
            pair.append(float(np.std(d - np.median(d)) / np.sqrt(2) / 1e3))
    for r in res:
        r.pop("_gt")
    geo = None
    if len(res) >= 4:
        A = np.array([[1.0, r["row_center_frac"], r["col_center_frac"]] for r in res if "offset_ms" in r])
        o = np.array([r["offset_ms"] for r in res if "offset_ms" in r])
        coef, *_ = np.linalg.lstsq(A, o, rcond=None)
        geo = {"model": "offset_ms = a + b*row_frac + c*col_frac", "a_ms": float(coef[0]), "b_ms_per_frame_height": float(coef[1]),
               "c_ms_per_frame_width": float(coef[2]), "residual_std_ms": float(np.std(o - A @ coef)),
               "offset_range_ms": [float(o.min()), float(o.max())]}
    return {"blocks": res, "gt_noise_between_blocks_us": {"pairs": len(pair), "median": float(np.median(pair)) if pair else None,
            "p10": float(np.percentile(pair, 10)) if pair else None, "p90": float(np.percentile(pair, 90)) if pair else None},
            "geometry_fit": geo}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--display", required=True)
    ap.add_argument("--capture", required=True)
    ap.add_argument("--mjpeg-dir")
    ap.add_argument("--skip-first", type=int, default=5)
    ap.add_argument("--no-blocks", action="store_true")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    disp = fa.load_display(Path(a.display))
    mjdir = Path(a.mjpeg_dir or a.capture)
    res = {"test": "flash_verify_method", "hostname": socket.gethostname(), "utc_started": dt.datetime.now(dt.timezone.utc).isoformat(),
           "command": " ".join(sys.argv), "code_sha256": {p.name: sha(p) for p in (HERE, Path(af.__file__), Path(fa.__file__))},
           "display": {k: v for k, v in disp.items() if k not in ("t_on", "level")}, "cameras": []}
    per_cam_err = {}
    for fj in sorted(Path(a.capture).glob("*.frames.jsonl")):
        key = fj.name[: -len(".frames.jsonl")]
        mj = mjdir / (key + ".mjpeg")
        rows = af.load(fj)[a.skip_first:]
        if len(rows) < 20 or not mj.exists():
            res["cameras"].append({"camera_key": key, "skipped": f"{len(rows)} frames, mjpeg exists={mj.exists()}"}); continue
        ses = json.loads(fj.with_name(key + ".session.json").read_text())
        E0 = 2.0 ** ses["controls"]["exposure_log2"]["value"] * 1e9
        ana = af.analyze(rows, None, 0, 32)
        arrays = ana.pop("_arrays")
        srcs = {}
        for name, X in arrays["sources"].items():
            Xf = X.astype(float); m = arrays["masks"].get(name)
            if m is not None:
                Xf[~m] = np.nan
            srcs[name] = Xf
        extra, ex = extra_sources(rows, srcs, ana)
        y, roi = fa.roi_signal(rows, mj)
        t0 = float(np.nanmin(srcs["host_arrival"]))
        cam = {"camera_key": key, "friendly_name": ses.get("friendly_name"), "E_ms": E0 / 1e6, "roi": roi, "extra_info": ex["info"],
               "device_clock": {k: v for k, v in ana["device_clock"].items() if not isinstance(v, dict)}}
        # ---- A. reproduce flash_analyze ------------------------------------------------------------------------
        fits = {n: fa.fit_source(X, y, disp, E0) for n, X in srcs.items()}
        gts = {n: f.pop("_gt", None) for n, f in fits.items()}
        ok = [n for n in fits if fits[n].get("per_frame") and gts[n] is not None]
        ref = min(ok, key=lambda n: fits[n]["per_frame"]["err_std_us"])
        cam["A_reproduce"] = {"reference_source": ref, "gamma_ref": fits[ref]["per_frame"]["gamma"],
                              "coarse_offset_ms": {n: f["offset_ms"] for n, f in fits.items()},
                              "self_selected_per_frame_std_us": {n: (f.get("per_frame") or {}).get("err_std_us") for n, f in fits.items()},
                              "vs_gt": {n: fa.vs_ground_truth(X, gts[ref]) for n, X in srcs.items()}}
        allsrc = dict(srcs); allsrc.update(extra)
        # ---- B. GT variants ----------------------------------------------------------------------------------------
        variants = {}
        for rn in ("uvc_pts_via_scr_lsq_envelope", "uvc_pts_mapped_direct", "host_arrival", "seq_periodic_env"):
            Xr = allsrc[rn]
            for g in (None, 1.0, 2.2, 3.0):
                gt = gt_build(Xr, y, disp, E0, g)
                if gt is None:
                    continue
                variants[f"ref={rn}|gamma={'tuned' if g is None else g}|E=7.8125"] = gt
        for Em in (6.5, 9.5):
            gt = gt_build(allsrc["seq_periodic_env"], y, disp, Em * 1e6, 2.2)
            if gt is not None:
                variants[f"ref=seq_periodic_env|gamma=2.2|E={Em}"] = gt
        second = np.zeros(len(rows), bool); second[ex["half"]:] = True
        tab = {}
        for vn, gt in variants.items():
            row = {"gt_n": gt[2]["n"], "gt_gamma": gt[2]["gamma"]}
            for sn, X in allsrc.items():
                sub = second if sn.endswith("_first_half") else None
                row[sn] = evaluate(X, gt, t0, sub)
            tab[vn] = row
        cam["B_gt_variants"] = tab
        # explicitly circular upper bound: PTS mapped by a line fitted to the GT itself, plus the GT-implied clock rate
        main_gt = variants["ref=seq_periodic_env|gamma=2.2|E=7.8125"]
        k, w = main_gt[0], main_gt[1]
        pts = ex["pts"]
        # where in the run the GT frames are (camera-vs-display beat: only some phases put a transition in the window)
        tk = (ex["host"][k] - ex["host"][0]) / 1e9
        # GT model check: does the error of the PTS source depend on the linearised fraction f or on edge direction?
        # (a perfect brightness model gives no dependence; a wrong tone curve / LCD response shows up as a trend in f)
        e_md = w - srcs["uvc_pts_mapped_direct"][k]; e_md = e_md - np.median(e_md)
        fq = main_gt[2]["f"]; upq = main_gt[2]["up"]
        edges = np.quantile(fq, [0, 0.2, 0.4, 0.6, 0.8, 1.0])
        bins = []
        for lo_, hi_ in zip(edges[:-1], edges[1:]):
            for dname, dm in (("rising", upq), ("falling", ~upq)):
                mm = (fq >= lo_) & (fq <= hi_) & dm
                if mm.sum() >= 3:
                    bins.append({"f_range": [float(lo_), float(hi_)], "edge": dname, "n": int(mm.sum()), "mean_err_us": float(e_md[mm].mean() / 1e3)})
        cam["gt_model_check_uvc_pts_mapped_direct"] = {"corr_err_vs_f_rising": float(np.corrcoef(fq[upq], e_md[upq])[0, 1]),
                                                        "corr_err_vs_f_falling": float(np.corrcoef(fq[~upq], e_md[~upq])[0, 1]),
                                                        "rising_mean_us": float(e_md[upq].mean() / 1e3), "falling_mean_us": float(e_md[~upq].mean() / 1e3),
                                                        "bins": bins}
        cam["gt_frames_per_3s_bin"] = np.histogram(tk, bins=np.arange(0, 33, 3))[0].tolist()
        xm = srcs["uvc_pts_mapped_direct"]; fr = (len(xm) - 1) * 1e9 / (xm[-1] - xm[0])
        cam["beat_period_s"] = float(1.0 / abs(2 * fr - 1e9 / disp["period_ns"])) if abs(2 * fr - 1e9 / disp["period_ns"]) > 1e-6 else None
        b, a0 = np.polyfit(pts[k] - pts[0], w, 1)
        # cross-validated version: fit on even-indexed GT frames, evaluate on odd
        ev_, od_ = np.arange(len(k)) % 2 == 0, np.arange(len(k)) % 2 == 1
        b2, a2 = np.polyfit(pts[k][ev_] - pts[0], w[ev_], 1)
        r_od = w[od_] - (a2 + b2 * (pts[k][od_] - pts[0]))
        env_a, env_b = af.lower_envelope_fit(pts, ex["host"])
        cam["C_clock_rate"] = {
            "pts_hz_from_gt_fit": float(1e9 / b), "pts_hz_from_arrival_envelope": float(1e9 / env_b),
            "pts_hz_nominal": ex["info"]["nominal_hz"],
            "gt_vs_envelope_rate_ppm": float((env_b - b) / b * 1e6),
            "gt_fit_residual_std_us_CIRCULAR": float(np.std(w - (a0 + b * (pts[k] - pts[0]))) / 1e3),
            "gt_fit_even_eval_odd_std_us": float(np.std(r_od - np.median(r_od)) / 1e3)}
        # ---- E. cross-camera material -----------------------------------------------------------------------------
        per_cam_err[key] = {sn: (main_gt[1] - X[main_gt[0]]) for sn, X in allsrc.items()}
        per_cam_err[key + "|ref"] = {sn: (gts[ref][1] - X[gts[ref][0]]) for sn, X in srcs.items()}
        if not a.no_blocks:
            cam["E_block_offsets_uvc_pts_mapped_direct"] = block_offsets(rows, mj, srcs["uvc_pts_mapped_direct"], disp, E0)
        res["cameras"].append(cam)
        print(f"== {key} ref={ref} roi={roi['roi_rows']},{roi['roi_cols']}", flush=True)
        for vn in ("ref=uvc_pts_via_scr_lsq_envelope|gamma=tuned|E=7.8125", "ref=seq_periodic_env|gamma=2.2|E=7.8125",
                   "ref=host_arrival|gamma=2.2|E=7.8125", "ref=seq_periodic_env|gamma=1.0|E=7.8125"):
            if vn not in tab:
                continue
            print(f"  [{vn}] n={tab[vn]['gt_n']}")
            for sn in allsrc:
                v = tab[vn].get(sn)
                if v:
                    print(f"     {sn:30s} std={v['err_std_us']:8.1f} mad={v['err_mad_sigma_us']:8.1f} off={v['offset_ms']:9.3f} "
                          f"slope={v['slope_ppm']:8.1f}ppm std_after_slope={v['err_std_after_slope_us']:8.1f} n={v['n']}")
        print("  clock:", cam["C_clock_rate"])
        bo = cam.get("E_block_offsets_uvc_pts_mapped_direct")
        if bo:
            for b_ in bo["blocks"]:
                print(f"   block {b_['block']} row={b_['row_center_frac']:.2f} col={b_['col_center_frac']:.2f} off={b_.get('offset_ms', float('nan')):8.3f} ms std={b_.get('err_std_us', float('nan')):6.0f} us n={b_.get('n')}")
            print("   gt noise between blocks:", bo["gt_noise_between_blocks_us"])
            print("   geometry:", bo["geometry_fit"])
    # cross-camera offset differences with bootstrap CI
    keys = [k for k in per_cam_err if "|" not in k]
    cross = {}
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            for tag, ki, kj in (("gt=seq_periodic_env,gamma2.2", keys[i], keys[j]), ("gt=flash_analyze_ref", keys[i] + "|ref", keys[j] + "|ref")):
                for sn in per_cam_err[ki]:
                    if sn not in per_cam_err[kj]:
                        continue
                    ei = per_cam_err[ki][sn]; ej = per_cam_err[kj][sn]
                    ei = ei[np.isfinite(ei)]; ej = ej[np.isfinite(ej)]
                    if ei.size < 8 or ej.size < 8:
                        continue
                    d = float(np.median(ei) - np.median(ej)) / 1e6
                    ci_i = boot_median(ei); ci_j = boot_median(ej)
                    bi = RNG.integers(0, ei.size, (4000, ei.size)); bj = RNG.integers(0, ej.size, (4000, ej.size))
                    dd = (np.median(ei[bi], axis=1) - np.median(ej[bj], axis=1)) / 1e6
                    cross[f"{tag}|{sn}"] = {"offset_diff_ms": d, "ci95_ms": [float(np.percentile(dd, 2.5)), float(np.percentile(dd, 97.5))]}
    res["E_cross_camera"] = cross
    for k_, v in cross.items():
        print(f"  cross {k_:60s} {v['offset_diff_ms']:8.3f} ms  CI95 [{v['ci95_ms'][0]:.3f}, {v['ci95_ms'][1]:.3f}]")
    Path(a.out).write_text(json.dumps(res, indent=2, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main())
