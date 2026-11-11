"""Which frame does cv2 (OpenCV 4.12.0, CAP_FFMPEG) return after CAP_PROP_POS_FRAMES = 74 on unfinalized vs repaired files?
Compares the image returned after the seek with every frame read sequentially (exact pixel equality)."""
import json, sys
import cv2, numpy as np
M = "C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/crash_resilience/pyav19_check/"
files = ["mjpeg__mkv_fp__drained150.mkv", "mjpeg__avi_fp__drained150.avi", "mjpeg__fmp4_every_fp__drained150.mp4",
         "mjpeg__nut_fp__drained150.nut", "repaired/mjpeg__mkv_fp__drained150.repaired.mkv",
         "h264nv__mkv_cl0_fp__drained150.mkv", "repaired/h264nv__mkv_cl0_fp__drained150.repaired.mkv"]
T = 74
out = {"opencv": cv2.__version__, "target": T, "results": {}}
for f in files:
    cap = cv2.VideoCapture(M + f, cv2.CAP_FFMPEG)
    seq = []
    while True:
        ok, im = cap.read()
        if not ok: break
        seq.append(im)
    cap.release()
    cap = cv2.VideoCapture(M + f, cv2.CAP_FFMPEG)
    set_ok = cap.set(cv2.CAP_PROP_POS_FRAMES, T)
    ok, im = cap.read()
    pos = cap.get(cv2.CAP_PROP_POS_FRAMES)
    cap.release()
    match = [i for i, s in enumerate(seq) if ok and s.shape == im.shape and np.array_equal(s, im)]
    out["results"][f] = {"frames_sequential": len(seq), "set_ok": bool(set_ok), "read_ok": bool(ok),
                         "pos_after": pos, "returned_frame_equals_sequential_index": match}
    print(f, out["results"][f])
open(sys.argv[1], "w").write(json.dumps(out, indent=1))
