# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26", "opencv-python-headless==4.10.0.84"]
# ///
"""Step response of a camera ROI: for display transitions preceded AND followed by >= HOLD ms of constant level,
the normalised ROI brightness of every frame whose (seq_env + nominal offset) lies within -50..+250 ms of the
transition, binned by (frame time - transition time). A box exposure of E gives a ramp of width E; temporal frame
blending gives a multi-frame tail. Usage: flash_step_response.py RUN_DIR COL ROW [--cam c922] [--hold-ms 60] [--out json]"""
import sys, json, argparse
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import flash_libuvc_scr as m  # noqa: E402
ap = argparse.ArgumentParser(); ap.add_argument("run"); ap.add_argument("col", type=float); ap.add_argument("row", type=float)
ap.add_argument("--cam", default="c930e"); ap.add_argument("--hold-ms", type=float, default=60); ap.add_argument("--out")
ap.add_argument("--mf-glob", help="use the MF capture (RUN/capture/<glob>.frames.jsonl + .mjpeg) of any camera, e.g. '*0843*'; --cam is then only the label")
a = ap.parse_args()
run = Path(a.run); disp = m.load_display_robust(run / "display_m0")
if a.cam == "c922" or a.mf_glob:
    cj = sorted((run / "capture").glob((a.mf_glob or "*085c*") + ".frames.jsonl"))[0]
    rows = m.af.load(cj)[15:]; stack = m.decode_mjpeg(rows, cj.with_name(cj.name.replace(".frames.jsonl", ".mjpeg")))
    srcs, _ = m.c922_sources(rows)
else:
    ud = run / "c930e_libuvc"; rows = m.load_jsonl(ud / "frames.jsonl")[15:]
    stack = m.decode_dir([ud / f"frame_{r['seq']:05d}.jpg" for r in rows])
    srcs, _ = m.c930e_sources(rows, m.frame_clock(ud / "usb_frame_qpc.jsonl"))
y, _ = m.roi_series(stack, a.row, a.col)
yn = (y - np.percentile(y, 2)) / (np.percentile(y, 98) - np.percentile(y, 2))
X = srcs["seq_env"]
t, s = disp["t_on"], disp["level"]
ch = np.flatnonzero(np.diff(s) != 0) + 1
H = a.hold_ms * 1e6
good = [i for j, i in enumerate(ch) if j > 0 and j + 1 < len(ch) and t[i] - t[ch[j - 1]] >= H and t[ch[j + 1]] - t[i] >= H]
bad = disp.get("bad_intervals", [])
good = [i for i in good if not any((t[i] - H - 2e6 < b1) and (t[i] + H + 2e6 > b0) for b0, b1 in bad)]
bins = np.arange(-48e6, 252e6, 4e6)
acc = {int(b / 1e6): [] for b in bins}
for i in good:
    up = s[i] > s[i - 1]
    rel = X - t[i]
    for k in np.flatnonzero((rel > -50e6) & (rel < 250e6)):
        b = int(np.floor(rel[k] / 4e6) * 4)
        if b in acc:
            acc[b].append(yn[k] if up else 1 - yn[k])
prof = {b: (float(np.mean(v)), len(v)) for b, v in acc.items() if v}
res = {"cam": a.cam, "transitions_used": len(good), "display_unreliable_presents": disp.get("unreliable_presents"), "hold_ms": a.hold_ms,
       "profile_rel_ms_mean_n": {str(b): [round(v[0], 3), v[1]] for b, v in sorted(prof.items())}}
pb = np.array(sorted(prof)); pv = np.array([prof[b][0] for b in pb])
lo = pb[np.argmax(pv > 0.1)]; hi = pb[np.argmax(pv > 0.9)]
res["rise_10_90_ms_frame_time_minus_transition"] = [int(lo), int(hi)]
print(json.dumps(res))
if a.out:
    p = Path(a.out); d = json.loads(p.read_text()) if p.exists() else {}
    d[f"{a.cam}_row{a.row}_col{a.col}"] = res; p.write_text(json.dumps(d, indent=1))
