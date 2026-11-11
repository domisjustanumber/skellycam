"""cv2 (skellycam venv, OpenCV 4.12.0, read-only use) on the PyAV 19.0.2 kill images: CAP_PROP_FRAME_COUNT vs frames read."""
import json, sys
sys.path.insert(0, "C:/Users/Dom/GitHub/freemocap/skellycam/research/skellycam_recording/recording_upgrade/scripts/crash_resilience")
import common_cr as cc, cv2
M = "C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/crash_resilience/pyav19_check/"
files = ["mjpeg__mkv_fp__drained150.mkv", "mjpeg__avi_fp__drained150.avi", "mjpeg__nut_fp__drained150.nut",
         "mjpeg__fmp4_every_fp__drained150.mp4", "h264nv__mkv_cl0_fp__drained150.mkv", "av1__mkv_cl0_fp__drained150.mkv",
         "repaired/mjpeg__mkv_fp__drained150.repaired.mkv", "repaired/mjpeg__avi_fp__drained150.repaired.mkv"]
out = {"opencv": cv2.__version__, "writer": "PyAV 19.0.2 (pyav19_recheck.json)", "results": {}}
for f in files:
    r = cc.cv2_read(M + f)
    out["results"][f] = {k: r.get(k) for k in ("opened", "prop_frame_count", "frames", "seek")}
    print(f, out["results"][f])
open(sys.argv[1], "w").write(json.dumps(out, indent=1))
