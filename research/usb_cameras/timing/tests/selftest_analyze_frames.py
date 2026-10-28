# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26"]
# ///
"""Synthetic self-test of tools/analyze_frames.py: simulates a UVC camera (device clock 30 MHz nominal, +40 ppm vs
host; USB SOF clock -15 ppm vs host; capture period 33.3333 ms; PTS = capture start; STC sampled ~8 ms later when
the first byte goes on the bus, SOF counter at that instant; host arrival = end of transfer + 16 ms-quantised
completion like Windows usbvideo; Linux-style host SOF + ns samples) and checks the analyser's estimates against truth.
Run: uv run --script research/usb_cameras/timing/tests/selftest_analyze_frames.py [--out result.json]"""
import json, sys, tempfile
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import analyze_frames as af

rng = np.random.default_rng(1)
N = 1800
f_nom = 30e6; dev_ppm = 40.0; usb_ppm = -15.0
t_cap = 5e9 + np.arange(N) * 33.3333e6 + rng.normal(0, 20e3, N)  # true capture start, host ns (20 us sensor jitter)
pts = np.round((t_cap * 1e-9) * f_nom * (1 + dev_ppm * 1e-6) + 123456).astype(np.int64) % (1 << 32)
t_bus = t_cap + 8e6 + rng.uniform(0, 0.2e6, N)  # first byte on the bus
stc = np.round((t_bus * 1e-9) * f_nom * (1 + dev_ppm * 1e-6) + 123456).astype(np.int64) % (1 << 32)
sof_ms = t_bus * 1e-6 * (1 + usb_ppm * 1e-6) + 777.3
dev_sof = np.floor(sof_ms).astype(np.int64) % 2048
t_done = t_bus + 20e6  # transfer complete
host_arr = (np.ceil((t_done - 1e9) / 16e6) * 16e6 + 1e9 + rng.uniform(0.1e6, 0.4e6, N)).astype(np.int64)  # 16 ms URB quantisation
host_sof_ns = (t_bus + rng.uniform(20e3, 120e3, N)).astype(np.int64)  # kernel samples when header arrives
host_sof = np.floor(host_sof_ns * 1e-6 * (1 + usb_ppm * 1e-6) + 777.3).astype(np.int64) % 2048
out = {}
with tempfile.TemporaryDirectory() as td:
    for mode in ("windows_like", "linux_like"):
        p = Path(td) / f"{mode}.jsonl"
        with p.open("w") as f:
            for i in range(N):
                r = {"camera_key": mode, "backend": "synthetic", "seq": i, "host_arrival_ns": int(host_arr[i]), "os_timestamp_ns": int(host_arr[i] - 300000),
                     "uvc_pts": int(pts[i]), "uvc_scr_stc": int(stc[i]), "uvc_scr_sof": int(dev_sof[i]), "payload_bytes": 100000, "is_valid_jpeg": True}
                if mode == "linux_like":
                    r.update(uvc_host_sof=int(host_sof[i]), uvc_host_sof_ns=int(host_sof_ns[i]))
                f.write(json.dumps(r) + "\n")
        res = af.analyze(af.load(p), None, 0, 32)
        arr = res.pop("_arrays")
        o = {"device_clock": res["device_clock"], "jitter_ranking_rms_us": res["jitter_ranking_rms_us"],
             "truth": {"pts_freq_hz": f_nom * (1 + dev_ppm * 1e-6), "device_vs_host_ppm": dev_ppm,
                       "device_vs_usb_ppm": (1 + dev_ppm * 1e-6) / (1 + usb_ppm * 1e-6) * 1e6 - 1e6, "usb_vs_host_ppm": usb_ppm,
                       "stc_minus_pts_ms_mean": float(np.mean(t_bus - t_cap) / 1e6)}}
        for name, t in arr["sources"].items():
            m = arr["masks"].get(name)
            e = (t.astype(float) - t_cap)[m if m is not None else slice(None)]
            o.setdefault("error_vs_true_capture_us", {})[name] = {"mean": float(e.mean() / 1e3), "std": float(e.std() / 1e3)}
        out[mode] = o
        print(mode, json.dumps({k: v for k, v in o.items() if k != "device_clock"}, indent=1))
        print(" device_clock:", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in res["device_clock"].items() if not isinstance(v, dict)})
if len(sys.argv) > 2 and sys.argv[1] == "--out":
    Path(sys.argv[2]).write_text(json.dumps({"test": "selftest_analyze_frames", "results": out}, indent=2, default=float))
