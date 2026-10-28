# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26", "opencv-python-headless==4.10.0.84"]
# ///
"""Exposure scan for the libuvc C930e flash data: GT correlation (seq_env reference, fixed ROI) vs assumed exposure E.
The camera's real integration time is not observable from the control readback; the E that maximises the window-model
correlation is the data's estimate. Usage: flash_libuvc_escan.py RUN_DIR COL ROW E_MIN_MS E_MAX_MS STEP_MS [--cam c922]"""
import sys, json
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import flash_libuvc_scr as m  # noqa: E402
run = Path(sys.argv[1]); col, row = float(sys.argv[2]), float(sys.argv[3]); e0, e1, de = map(float, sys.argv[4:7])
c922 = "--cam" in sys.argv
disp = m.load_display_robust(run / "display_m0")
if c922:
    cj = sorted((run / "capture").glob("*085c*.frames.jsonl"))[0]
    rows = m.af.load(cj)[15:]; stack = m.decode_mjpeg(rows, cj.with_name(cj.name.replace(".frames.jsonl", ".mjpeg")))
    srcs, _ = m.c922_sources(rows)
else:
    ud = run / "c930e_libuvc"
    rows = m.load_jsonl(ud / "frames.jsonl")[15:]
    stack = m.decode_dir([ud / f"frame_{r['seq']:05d}.jpg" for r in rows])
    srcs, _ = m.c930e_sources(rows, m.frame_clock(ud / "usb_frame_qpc.jsonl"))
y, box = m.roi_series(stack, row, col)
out = []
for E in np.arange(e0, e1 + 1e-9, de):
    gt = m.gt_fixed(srcs["seq_env"], y, disp, E * 1e6, 2.2)
    s = m.score(srcs["seq_env"], gt)
    out.append({"E_ms": float(E), "corr": gt["corr"], "n": s.get("n"), "std_us": s.get("err_std_us")})
    print(f"E={E:6.2f} corr={gt['corr']:.4f} n={s.get('n')} seq_env std={s.get('err_std_us')}")
print(json.dumps({"best_E_ms": max(out, key=lambda o: o["corr"])["E_ms"]}))
