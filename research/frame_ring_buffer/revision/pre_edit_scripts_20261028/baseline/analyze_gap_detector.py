"""Offline analysis of the per-frame dumps written by bench_e2e_variants.py (REVISION stage, 2026-10-28). NOT SkellyCam code.

1. Rank-4 drop detector validation. Ground truth = sensor frames never grabbed during the recording (FakeCapture tick log:
   last tick - first tick + 1 - recorded frames). Candidate detectors, all computed from the host timestamps SkellyCam
   already stores per frame (frame_metadata.timestamps) and the configured 60 fps:
     per_interval_round : sum over consecutive frames of max(0, round(dt / T) - 1)        (the formula proposed in rank 4)
     accumulated_clock  : round((t_last - t_first) / T) + 1 - n_frames                     (the critic's proposed fix)
     fractional_sum     : floor(sum over intervals of max(0, dt / T - 1))
   each on pre_frame_grab_ns and on post_frame_retrieve_ns.
2. Recording start/stop pause gap: sensor ticks skipped between consecutive RECORDED frames, for the first and last 10
   recorded frames and for the rest (stop_recording pauses every camera while recording is active, camera_group.py L215-232).
3. Cross-camera spread per frame number of pre_frame_grab_ns vs of the true sensor tick time (shows whether the grab stamps
   describe capture time; relevant to the dshowlike variant).

Run (from C:\\Users\\Dom\\GitHub\\freemocap\\skellycam):
  .venv\\Scripts\\python.exe benchmarks\\frame_pipeline\\baseline\\analyze_gap_detector.py
Output: baseline/results/e2ev_gap_detector.md and .json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent / "results"
T = 1e9 / 60.0


def detectors(t, n):
    dt = np.diff(t.astype(np.float64))
    return dict(per_interval_round=int(np.maximum(0, np.round(dt / T) - 1).sum()),
                accumulated_clock=int(round((t[-1] - t[0]) / T) + 1 - n),
                fractional_sum=int(np.floor(np.maximum(0.0, dt / T - 1).sum())))


def main():
    out = {}
    lines = ["# e2e per-frame analysis: rank-4 drop detector validation, start/stop pause gap, grab-stamp vs capture-time spread", "",
             "Source: bench_e2e_variants.py dumps (`*_perframe.npz`), real SkellyCam stack at 23ccbf20, 5 synthetic cameras, 30 s recording. "
             "Detector values are sums over 5 cameras. T = 16.667 ms (configured 60 fps).", "",
             "| run | true never grabbed | per_interval_round (grab / retrieve) | accumulated_clock (grab / retrieve) | fractional_sum (grab / retrieve) | "
             "skipped ticks in first 10 recorded frames (sum 5 cams) | skipped ticks in last 10 recorded frames | largest single gap in last 10 (ticks) | "
             "skipped ticks elsewhere | grab-stamp spread p99 ms | sensor-tick spread median / p99 / max ms |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for f in sorted(R.glob("e2ev_*_perframe.npz")):
        z = np.load(f)
        cams = sorted({k.split("_")[0][3:] for k in z.files if k.startswith("cam")})
        tot = dict(true=0)
        det = {}
        first10 = last10 = mid = 0
        big_last = 0
        G, TK = [], []
        for c in cams:
            fn = z[f"cam{c}_fn"]
            n = len(fn)
            tick = z[f"cam{c}_tick"]
            true = int(tick[-1] - tick[0] + 1 - n)
            tot["true"] += true
            for src in ("pre_frame_grab_ns", "post_frame_retrieve_ns"):
                for k, v in detectors(z[f"cam{c}_{src}"], n).items():
                    det[(k, src)] = det.get((k, src), 0) + v
            sk = np.diff(tick) - 1
            first10 += int(sk[:10].sum())
            last10 += int(sk[-10:].sum())
            big_last = max(big_last, int(sk[-10:].max()))
            mid += int(sk[10:-10].sum())
            G.append(z[f"cam{c}_pre_frame_grab_ns"])
            TK.append(z[f"cam{c}_tick_ns"])
        m = min(len(g) for g in G)
        Ga = np.array([g[:m] for g in G], np.int64)
        Ta = np.array([t[:m] for t in TK], np.int64)
        gs = (Ga.max(0) - Ga.min(0)) / 1e6
        ts = (Ta.max(0) - Ta.min(0)) / 1e6
        row = dict(true_never_grabbed=tot["true"], detectors={f"{k}|{s}": v for (k, s), v in det.items()},
                   skipped_first10=first10, skipped_last10=last10, largest_gap_last10_ticks=big_last, skipped_elsewhere=mid,
                   grab_spread_p99_ms=float(np.percentile(gs, 99)),
                   tick_spread=dict(median_ms=float(np.median(ts)), p99_ms=float(np.percentile(ts, 99)), max_ms=float(ts.max())))
        name = f.name.replace("_perframe.npz", "")
        out[name] = row

        def g(k):
            return f"{det[(k, 'pre_frame_grab_ns')]} / {det[(k, 'post_frame_retrieve_ns')]}"
        lines.append(f"| {name} | {tot['true']} | {g('per_interval_round')} | {g('accumulated_clock')} | {g('fractional_sum')} | {first10} | {last10} | "
                     f"{big_last} | {mid} | {row['grab_spread_p99_ms']:.2f} | {row['tick_spread']['median_ms']:.2f} / {row['tick_spread']['p99_ms']:.2f} / {row['tick_spread']['max_ms']:.2f} |")
    (R / "e2ev_gap_detector.json").write_text(json.dumps(out, indent=1))
    (R / "e2ev_gap_detector.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
