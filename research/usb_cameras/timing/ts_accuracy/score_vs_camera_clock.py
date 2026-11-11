# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26"]
# ///
"""Score tier-0 host timestamps against the camera's own clock (UVC PTS or SCR STC) on existing captures.

No camera is opened. The camera clock is used ONLY as a measuring reference here: reading it needs the tier-1
registry value MetadataBufferSizeInKB0, so nothing scored as "tier 0" uses it.

What this measures and what it cannot:
- The reference is the camera clock mapped to QPC by ONE line for the whole run: slope and offset from the robust
  lower-envelope fit of camera ticks vs MF arrival (the same mapping as analyze_frames' uvc_pts_mapped_direct).
  Every error is reported after removing its own mean, so this gives the RANDOM error component only; the constant
  bias of each source (stamp minus exposure) is unmeasured here (see score_vs_flash_gt.py for that).
- Because the reference slope comes from the arrival envelope, the robust whole-run lattice fitted to ARRIVAL has
  the same slope by construction and scores ~0 by construction ("degenerate", flagged in the output). Its slope was
  checked against the flash ground truth in timing/VERIFY_method.md section 5: 4-7 ppm.
- The C922 PTS alternates +-0.27 ms between frames (REPORT; windows_results_20261106 section 4); scoring against
  it adds that pattern to every error. The C922 STC (first payload on the bus) is 2.2 us regular and is used as the
  second reference. The C930e PTS is a synthetic counter (regular) and its STC jitters with bus scheduling; PTS is
  used. The Kiyo PTS counts at 1 kHz, so its reference carries 1 ms quantisation (0.29 ms rms).

Per entry (one frames.jsonl): camera clock rate vs QPC (ppm vs nominal, whole run and 10 s chunks), cadence
regularity of the camera clock itself, tier-0 slot/drop detection vs camera-clock slots, and error stats of
raw MF sample time, raw MF arrival, DS stamps (if present) and every tier-0 lattice variant (tslib.tier0_variants),
on all frames and on frames >= --late-s after the first frame (start-up excluded).
Entries with ref "none" (no camera clock) get only slot/drop detection and the lattice-fit residual (regularity).

Usage:
  uv run --script research/usb_cameras/timing/ts_accuracy/score_vs_camera_clock.py \
     --manifest research/usb_cameras/timing/ts_accuracy/manifest_camera_clock.json \
     --out research/usb_cameras/results/windows/Gerald/ts_accuracy_20261109/existing_reanalysis/camera_clock_scores.json
Relative paths in the manifest are resolved against the skellycam repo root.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import socket
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(HERE))
import tslib  # noqa: E402


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def chunk_ppm(ticks, arr, nominal, chunk_s=10.0):
    out = []
    t0 = arr[0]
    for c in np.arange(0, (arr[-1] - t0) / 1e9 - chunk_s * 0.6, chunk_s):
        m = ((arr - t0) / 1e9 >= c) & ((arr - t0) / 1e9 < c + chunk_s)
        if m.sum() > 50:
            _, b = tslib.lower_envelope_fit(ticks[m], arr[m])
            out.append({"t_s": float(c), "ppm": float((1e9 / b / nominal - 1) * 1e6)})
    return out


def prep_clock(ticks: np.ndarray, arr: np.ndarray):
    """Camera-clock slots, with de-stepping: where the camera clock skips a slot but MF arrival shows a
    normal interval, the jump is a clock artefact (C930e PTS mode steps, first-frame jumps): keep the host slot count
    and shift the later ticks by whole periods."""
    ticks = ticks.astype(float).copy()
    step = float(np.median(np.diff(ticks)))
    for _ in range(2):  # refine the period so that rounding does not accumulate
        inc_c = np.maximum(0, np.round(np.diff(ticks) / step))
        step = float((ticks[-1] - ticks[0]) / max(1.0, inc_c.sum()))
    inc_c = np.round(np.diff(ticks) / step)
    inc_h = np.diff(tslib.assign_slots(arr)["k"])
    # only a camera-clock jump without a host gap is corrected; when the host shows a gap the camera clock does not,
    # the camera clock is kept (host-side late delivery)
    bad = np.flatnonzero(inc_c > inc_h)
    for i in bad:
        ticks[i + 1:] += (inc_h[i] - inc_c[i]) * step
    kc = np.concatenate([[0.0], np.cumsum(np.round(np.diff(ticks) / step))])
    return ticks, kc, inc_c, inc_h, bad, step


def entry_ppm(e: dict) -> float | None:
    """Pass 1: the run's own camera-clock rate vs QPC (robust envelope vs arrival), for the per-camera median."""
    if e.get("ref", "none") not in ("pts", "stc"):
        return None
    p = Path(e["path"])
    d = tslib.load_frames(p if p.is_absolute() else REPO / p)
    ticks = d.get("uvc_pts_ticks" if e["ref"] == "pts" else "uvc_stc_ticks")
    if d["n"] < 60 or ticks is None:
        return None
    ticks = prep_clock(ticks, d["arrival"])[0]
    b = tslib.lower_envelope_fit(ticks, d["arrival"])[1]
    return float((1e9 / b / float(e["nominal_hz"]) - 1) * 1e6)


def score_entry(e: dict, late_s: float, fixed_ppm: float | None = None) -> dict:
    p = Path(e["path"])
    if not p.is_absolute():
        p = REPO / p
    d = tslib.load_frames(p)
    out = {"label": e["label"], "camera": e["camera"], "path": e["path"], "ref": e.get("ref", "none"),
           "note": e.get("note"), "frames": d["n"]}
    if d["n"] < 60:
        out["error"] = f"only {d['n']} frames"
        return out
    arr = d["arrival"]
    t_rel = (arr - arr[0]) / 1e9
    late = t_rel >= late_s
    out["duration_s"] = float(t_rel[-1])
    series = {}
    if "sample_time" in d:
        series["mf_sample_time"] = d["sample_time"]
    series["arrival"] = arr
    if "ds_pts" in d:
        series["ds_pts"] = d["ds_pts"]
    if "sample_time" in d:
        df = (arr - d["sample_time"]) / 1e6
        out["arrival_minus_sample_time_ms"] = {"median": float(np.median(df)), "p05": float(np.percentile(df, 5)),
                                               "p95": float(np.percentile(df, 95))}
    ref = e.get("ref", "none")
    ref_ns = None
    ref_fixed = None
    kc = None
    if ref in ("pts", "stc"):
        ticks = d.get("uvc_pts_ticks" if ref == "pts" else "uvc_stc_ticks")
        if ticks is None:
            out["error"] = f"no {ref} in file"
            return out
        nominal = float(e["nominal_hz"])
        ticks, kc, inc_c, inc_h, bad, step = prep_clock(ticks, arr)
        a, b = tslib.lower_envelope_fit(ticks, arr)
        ref_ns = a + b * ticks
        # alternative slope estimators, to show how well the reference slope itself is determined
        ppm = lambda bb: float((1e9 / bb / nominal - 1) * 1e6)  # noqa: E731
        alt = {"env_arrival": ppm(b)}
        if "sample_time" in d:
            alt["env_sample_time"] = ppm(tslib.lower_envelope_fit(ticks, d["sample_time"])[1])
        alt["lsq_arrival_after_late_s"] = ppm(tslib.linfit(ticks[late], arr[late])[1])
        spread = max(alt.values()) - min(alt.values())
        aa, bb = tslib.linfit(kc, ref_ns)
        cad = ref_ns - (aa + bb * kc)
        out["camera_clock"] = {
            "nominal_hz": nominal, "rate_vs_qpc_hz": float(1e9 / b), "ppm_vs_nominal_whole_run": ppm(b),
            "ppm_by_estimator": alt, "ppm_spread": spread,
            "max_ref_error_from_slope_spread_us": float(spread * 1e-6 * out["duration_s"] / 2 * 1e6),
            "ppm_chunks_10s": chunk_ppm(ticks, arr, nominal), "step_ticks": step,
            "frame_period_ms": float(bb / 1e6), "slots_missing_camera_clock": int(kc[-1] - (len(kc) - 1)),
            "steps_corrected_by_host_slots": [{"i": int(i), "camera_inc": float(inc_c[i]), "host_inc": float(inc_h[i])} for i in bad],
            "cadence_residual_us": tslib.err_stats(cad),
            "slope_from": "robust lower envelope of camera ticks vs MF arrival, whole run"}
        inc_cam = np.diff(kc)
        ref_fixed = None
        if fixed_ppm is not None:
            # slope fixed at the per-camera median rate over all runs (host-independent within this run)
            ref_fixed = ticks * (1e9 / (nominal * (1 + fixed_ppm * 1e-6)))
            out["camera_clock"]["fixed_slope_ppm"] = fixed_ppm
    out["sources"] = {}
    for sname, T in series.items():
        sl = tslib.assign_slots(T)
        k = sl["k"]
        s_out = {"slots": {"P_ms": sl["P_ns"] / 1e6, "drops_detected": sl["drops"], "late_deliveries": sl["late_deliveries"],
                           "short_intervals": sl["short_intervals"]}}
        if kc is not None:
            s_out["slots"]["slot_step_disagreements_vs_camera_clock"] = int(np.sum(np.diff(k) != inc_cam))
        variants = tslib.tier0_variants(T, k)
        if ref_ns is not None:
            s_out["raw_all"] = tslib.err_stats(T - ref_ns)
            s_out["raw_late"] = tslib.err_stats((T - ref_ns)[late])
            s_out["fits_all"] = {vn: tslib.err_stats(V - ref_ns) for vn, V in variants.items()}
            s_out["fits_late"] = {vn: tslib.err_stats((V - ref_ns)[late]) for vn, V in variants.items()}
            if ref_fixed is not None:
                s_out["raw_late_fixedslope"] = tslib.err_stats((T - ref_fixed)[late])
                s_out["fits_late_fixedslope"] = {vn: tslib.err_stats((V - ref_fixed)[late]) for vn, V in variants.items()}
                s_out["fits_all_fixedslope"] = {vn: tslib.err_stats(V - ref_fixed) for vn, V in variants.items()}
            if sname == "arrival":
                s_out["degenerate"] = ["rob_envq0_whole", "rob_envq0.02_whole", "rob_envq0.05_whole", "rob_envq0.1_whole"]
        else:
            # regularity only: residual of each fit to the stamps it was fitted to (NOT accuracy)
            s_out["regularity_fit_minus_stamp"] = {vn: tslib.err_stats(V - T) for vn, V in variants.items()
                                                   if vn in ("lsq_whole", "rob_envq0.02_whole", "fixP_envq0.02_win10s_centred",
                                                             "fixP_envq0.02_win10s_causal")}
        out["sources"][sname] = s_out
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--late-s", type=float, default=3.0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    man = json.loads(Path(a.manifest).read_text())
    res = {"test": "ts_accuracy.score_vs_camera_clock", "hostname": socket.gethostname(),
           "utc_started": dt.datetime.now(dt.timezone.utc).isoformat(), "command": " ".join(sys.argv),
           "late_s": a.late_s, "sign": "e = stamp - camera-clock reference; every stat after removing its own mean",
           "code_sha256": {p.name: sha(p) for p in (Path(__file__), HERE / "tslib.py", Path(a.manifest))},
           "entries": []}
    # pass 1: per-camera median camera-clock rate (runs whose rate differs by > 500 ppm from the camera's median
    # are a different clock mode, C930e PTS; they keep their own rate)
    own = {i: entry_ppm(e) for i, e in enumerate(man["entries"])}
    groups: dict = {}
    for i, e in enumerate(man["entries"]):
        if own[i] is not None:
            groups.setdefault((e["camera"], e["ref"]), []).append(own[i])
    med = {}
    for kk, v in groups.items():
        m0 = float(np.median(v))
        med[kk] = float(np.median([x for x in v if abs(x - m0) < 500]))
    res["fixed_slope_ppm_per_camera"] = {f"{c}|{r}": {"median_ppm": m, "runs": groups[(c, r)]} for (c, r), m in med.items()}
    for i, e in enumerate(man["entries"]):
        fp = None
        if own[i] is not None:
            m = med[(e["camera"], e["ref"])]
            fp = m if abs(own[i] - m) < 500 else own[i]
        r = score_entry(e, a.late_s, fp)
        res["entries"].append(r)
        line = f"{r['label']:44s} {r['camera']:6s} ref={r['ref']:4s} n={r['frames']}"
        if "camera_clock" in r:
            cc = r["camera_clock"]
            line += f" ppm={cc['ppm_vs_nominal_whole_run']:7.1f} fixed={cc.get('fixed_slope_ppm', float('nan')):7.1f} spread={cc['ppm_spread']:5.1f} fix={len(cc['steps_corrected_by_host_slots'])} cad={cc['cadence_residual_us'].get('std_us', float('nan')):6.0f}us"
            for sn, so in r["sources"].items():
                fl = so.get("fits_late_fixedslope", so["fits_late"])
                rl = so.get("raw_late_fixedslope", so["raw_late"])
                line += (f" | {sn}[fixed slope]: raw {rl['std_us']:5.0f} lsq {fl['lsq_whole']['std_us']:5.0f}"
                         f" rob {fl['rob_envq0.02_whole']['std_us']:5.0f} fixP10c {fl['fixP_envq0.02_win10s_centred']['std_us']:5.0f}"
                         f" fixP10causal {fl['fixP_envq0.02_win10s_causal']['std_us']:5.0f} slotdis {so['slots'].get('slot_step_disagreements_vs_camera_clock')}")
        elif "sources" in r:
            for sn, so in r["sources"].items():
                rg = so["regularity_fit_minus_stamp"]
                line += f" | {sn}: drops {so['slots']['drops_detected']} short {so['slots']['short_intervals']} resid(lsq) {rg['lsq_whole']['std_us']:5.0f}us"
        else:
            line += " " + r.get("error", "")
        print(line)
    Path(a.out).write_text(json.dumps(res, indent=1, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main())
