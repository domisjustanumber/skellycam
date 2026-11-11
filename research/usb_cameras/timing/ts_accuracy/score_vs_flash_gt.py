# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26", "opencv-python-headless==4.10.0.84"]
# ///
"""Score tier-0 timestamp options per frame against the screen-flash ground truth (GT), on an existing flash run
whose raw MJPEG still exists (only flash_run1_repositioned, 2026-10-25, C930e + C922 via mf_uvc_timing.exe).

No camera is opened. The GT code is reused unchanged by import:
  timing/scripts/flash_analyze.py      roi_signal (auto ROI = the 1/24 x 1/24 block that flickers most), cumulative
  timing/scripts/flash_libuvc_scr.py   load_display_robust, gt_fixed (exposure start of the ROI per frame, gamma fixed)
  tools/analyze_frames.py              load, analyze (tier-1 PTS/SCR mappings, reference only)
OpenCV is needed only to decode the MJPEG for the ROI brightness.

GT per frame (see timing/VERIFY_method.md): frames whose exposure window holds exactly one display transition give
w = exposure start of the ROI rows. A reference series only SELECTS frames (which transition); two references are run:
  ref=seq_env  frame index + lower envelope of MF arrival (no device timestamp; the same estimator as the tier-0 fit,
               so frame selection is mildly favourable to tier-0 arrival fits)
  ref=pts      uvc_pts_mapped_direct (tier 1, used ONLY to select frames; makes the selection independent of tier 0)
Gamma is fixed at 2.2 and E at the nominal 2^-7 s (no tuning on any judged source).

Sign convention here: e = stamp - GT (positive = stamp later than exposure start of the ROI rows).
Scored per camera: raw MF sample time, raw MF QPC arrival, every tier-0 lattice variant (tslib.tier0_variants) on
each of them, and tier-1 PTS/SCR mappings (reference only: the registry value MetadataBufferSizeInKB0 was set).

Usage:
  uv run --script research/usb_cameras/timing/ts_accuracy/score_vs_flash_gt.py \
     --run research/usb_cameras/results/windows/Gerald/timing/flash_run1_repositioned \
     --mjpeg-dir C:/Users/Dom/Documents/skellycam-raw/research/usb_cameras/results/windows/Gerald/timing/flash_run1_repositioned/capture \
     --out research/usb_cameras/results/windows/Gerald/ts_accuracy_20261109/existing_reanalysis/flash_gt_perframe.json
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
UC = HERE.parents[1]  # research/usb_cameras
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(UC / "timing" / "scripts"))
sys.path.insert(0, str(UC / "tools"))
import tslib  # noqa: E402
import analyze_frames as af  # noqa: E402
import flash_analyze as fa  # noqa: E402
import flash_libuvc_scr as fl  # noqa: E402

# measured rolling-shutter readout per frame height (REPORT finding 12; flash_rows readout_ms_full_height, rerun)
READOUT_MS = {"085c": 31.0, "0843": 30.0}
NAMES = {"085c": "C922", "0843": "C930e"}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--mjpeg-dir", required=True)
    ap.add_argument("--skip-first", type=int, default=5)
    ap.add_argument("--gamma", type=float, default=2.2)
    ap.add_argument("--e-ms", type=float, default=7.8125)
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    run = Path(a.run)
    disp = fl.load_display_robust(run / "display_m0")
    res = {"test": "ts_accuracy.score_vs_flash_gt", "hostname": socket.gethostname(),
           "utc_started": dt.datetime.now(dt.timezone.utc).isoformat(), "command": " ".join(sys.argv),
           "run": str(run), "mjpeg_dir": a.mjpeg_dir, "gamma": a.gamma, "E_ms": a.e_ms, "skip_first": a.skip_first,
           "sign": "e = stamp - GT exposure start of ROI rows (ns -> reported ms/us)",
           "code_sha256": {p.name: sha(p) for p in [Path(__file__), HERE / "tslib.py", UC / "timing/scripts/flash_analyze.py",
                                                       UC / "timing/scripts/flash_libuvc_scr.py", UC / "tools/analyze_frames.py"]},
           "display": {k: v for k, v in disp.items() if k not in ("t_on", "level", "bad_intervals")},
           "cameras": {}}
    E = a.e_ms * 1e6
    keep_e = {}
    for fj in sorted((run / "capture").glob("*.frames.jsonl")):
        key = fj.name[: -len(".frames.jsonl")]
        mj = Path(a.mjpeg_dir) / (key + ".mjpeg")
        pid = next((p for p in NAMES if f"pid_{p}" in key), None)
        if pid is None or not mj.exists():
            continue
        rows = af.load(fj)[a.skip_first:]
        if len(rows) < 100:
            continue
        name = NAMES[pid]
        y, roi = fa.roi_signal(rows, mj)
        ana = af.analyze(rows, None, 0, 32)
        arr = ana.pop("_arrays")
        t1 = {}
        for k, X in arr["sources"].items():
            if k.startswith("uvc_"):
                Xf = X.astype(float); m = arr["masks"].get(k)
                if m is not None:
                    Xf[~m] = np.nan
                t1[k] = Xf
        seq = np.array([r["seq"] for r in rows], float)
        host = np.array([r["host_arrival_ns"] for r in rows], float)
        samp = np.array([r["os_timestamp_ns"] for r in rows], float)
        srcs: dict[str, np.ndarray] = {"raw:mf_sample_time": samp, "raw:mf_arrival": host}
        slot_info = {}
        for sname, T in (("mf_sample_time", samp), ("mf_arrival", host)):
            sl = tslib.assign_slots(T)
            slot_info[sname] = {"P_ms": sl["P_ns"] / 1e6, "drops_detected": sl["drops"], "short_intervals": sl["short_intervals"],
                                "slots_equal_seq": bool(np.all(sl["k"] == seq - seq[0]))}
            for vn, V in tslib.tier0_variants(T, sl["k"]).items():
                srcs[f"t0:{sname}:{vn}"] = V
        for k, V in t1.items():
            srcs[f"t1ref:{k}"] = V
        a2, b2 = af.lower_envelope_fit(seq, host)
        refs = {"seq_env": a2 + b2 * seq, "pts": t1.get("uvc_pts_mapped_direct")}
        cam = {"camera_key": key, "frames_scored_from": a.skip_first, "frames": len(rows), "roi": roi,
               "readout_ms_assumed": READOUT_MS[pid], "slots": slot_info,
               "device_clock": ana.get("device_clock"), "gt": {}}
        for rname, Xref in refs.items():
            if Xref is None:
                continue
            gt = fl.gt_fixed(Xref, y, disp, E, a.gamma)
            k = gt["k"]; w = gt["w"]
            tsec = (host[k] - host[0]) / 1e9
            g = {"ref": rname, "corr": gt["corr"], "n": int(len(k)), "gt_time_span_s": [float(tsec.min()), float(tsec.max())],
                 "n_rising": int(gt["up"].sum()), "n_before_3s": int(np.sum(tsec < 3.0)),
                 "gt_frame_times_s": [round(float(x), 3) for x in tsec], "sources": {}, "sources_t_ge_3s": {}}
            late = tsec >= 3.0
            for sn, X in srcs.items():
                e = X[k] - w
                st = tslib.err_stats(e)
                # bias referred to the exposure start of the frame's middle row (rolling shutter only; scan-out NOT removed)
                if "mean_offset_ms" in st:
                    st["mean_offset_mid_row_ms"] = st["mean_offset_ms"] - (0.5 - roi["roi_row_center_frac"]) * READOUT_MS[pid]
                g["sources"][sn] = st
                g["sources_t_ge_3s"][sn] = tslib.err_stats(e[late])
                keep_e[(name, rname, sn)] = e
            cam["gt"][rname] = g
        res["cameras"][name] = cam
        print(f"== {name} roi row {roi['roi_row_center_frac']:.2f} col {roi['roi_col_center_frac']:.2f}")
        for rname, g in cam["gt"].items():
            print(f"  GT ref={rname} n={g['n']} (before 3 s: {g['n_before_3s']}) corr={g['corr']:.3f}")
            for sn in ("raw:mf_sample_time", "raw:mf_arrival", "t0:mf_sample_time:lsq_whole", "t0:mf_arrival:lsqP_envq0.02_whole",
                       "t0:mf_sample_time:rob_envq0.02_whole", "t0:mf_arrival:rob_envq0.02_whole",
                       "t0:mf_sample_time:rob_envq0.02_win10s_centred", "t0:mf_arrival:rob_envq0.02_win10s_centred",
                       "t0:mf_sample_time:rob_envq0.02_win10s_causal", "t0:mf_arrival:rob_envq0.02_win10s_causal",
                       "t0:mf_sample_time:fixP_envq0.02_win10s_centred", "t0:mf_arrival:fixP_envq0.02_win10s_centred",
                       "t0:mf_sample_time:fixP_envq0.02_win10s_causal", "t0:mf_arrival:fixP_envq0.02_win10s_causal",
                       "t1ref:uvc_pts_mapped_direct", "t1ref:uvc_pts_via_scr_lsq_envelope"):
                s = g["sources"].get(sn)
                if s and "std_us" in s:
                    print(f"    {sn:45s} off {s['mean_offset_ms']:8.2f} ms  std {s['std_us']:7.0f}  p95 {s['p95_abs_us']:7.0f}  max {s['max_abs_us']:7.0f} us")
    # inter-camera: difference of mean offsets (C930e - C922), bootstrap over GT frames of each camera independently
    rng = np.random.default_rng(1)
    inter = {}
    if {"C922", "C930e"} <= set(res["cameras"]):
        for rname in ("seq_env", "pts"):
            for sn in res["cameras"]["C922"]["gt"].get(rname, {}).get("sources", {}):
                e1 = keep_e.get(("C930e", rname, sn)); e2 = keep_e.get(("C922", rname, sn))
                if e1 is None or e2 is None:
                    continue
                e1 = e1[np.isfinite(e1)]; e2 = e2[np.isfinite(e2)]
                if e1.size < 8 or e2.size < 8:
                    continue
                d = e1.mean() - e2.mean()
                bs = [rng.choice(e1, e1.size).mean() - rng.choice(e2, e2.size).mean() for _ in range(a.boot)]
                r1 = res["cameras"]["C930e"]["roi"]["roi_row_center_frac"]; r2 = res["cameras"]["C922"]["roi"]["roi_row_center_frac"]
                dmid = d / 1e6 - (0.5 - r1) * READOUT_MS["0843"] + (0.5 - r2) * READOUT_MS["085c"]
                inter[f"{rname}|{sn}"] = {"c930e_minus_c922_ms": d / 1e6,
                                          "ci95_ms": [float(np.percentile(bs, 2.5) / 1e6), float(np.percentile(bs, 97.5) / 1e6)],
                                          "mid_row_corrected_ms": dmid}
    res["inter_camera"] = inter
    res["inter_camera_caveat"] = ("ROIs sit at different image rows/cols and different screen positions. Rolling shutter is "
                                  "corrected to the middle row with the assumed readout; display scan-out position is NOT "
                                  "corrected (up to one refresh, 16.7 ms, across the screen). C930e exposure is assumed (-7), "
                                  "not confirmed (REPORT finding 11).")
    Path(a.out).write_text(json.dumps(res, indent=1, default=float))
    for kk in ("seq_env|raw:mf_sample_time", "seq_env|raw:mf_arrival", "seq_env|t0:mf_arrival:rob_envq0.02_whole",
               "seq_env|t0:mf_sample_time:rob_envq0.02_whole", "seq_env|t1ref:uvc_pts_mapped_direct"):
        if kk in inter:
            v = inter[kk]
            print(f"inter {kk:45s} {v['c930e_minus_c922_ms']:7.2f} ms CI {v['ci95_ms'][0]:.2f}..{v['ci95_ms'][1]:.2f}  mid-row {v['mid_row_corrected_ms']:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
