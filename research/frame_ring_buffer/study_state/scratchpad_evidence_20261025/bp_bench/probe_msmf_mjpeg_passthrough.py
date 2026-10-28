"""
Can OpenCV's MSMF backend hand us the camera's compressed MJPEG bytes (no decode)?  Opens camera <idx> with
CAP_MSMF, asks for MJPG 1280x720@60, sets CAP_PROP_CONVERT_RGB=0, and checks that each returned buffer is a
JPEG (starts with FF D8, ends with FF D9). Reports sizes (bytes/frame -> MB/s at 60 fps) and read() timing,
then decodes a few with cv2.imdecode to confirm they are valid images.

Run:
    cd C:\\Users\\Dom\\GitHub\\freemocap\\skellycam
    .venv\\Scripts\\python.exe -I <scratch>\\bp_bench\\probe_msmf_mjpeg_passthrough.py <out_dir> [camera_index]
"""
import json
import os
import statistics
import sys
import time

os.environ.setdefault("OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS", "0")
import cv2  # noqa: E402

out_dir = sys.argv[1] if len(sys.argv) > 1 else "."
idx = int(sys.argv[2]) if len(sys.argv) > 2 else 0
res = {}
cap = cv2.VideoCapture(idx, cv2.CAP_MSMF)
res["opened"] = cap.isOpened()
if cap.isOpened():
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_FPS, 60)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*"MJPG"))
    res["set_convert_rgb_0"] = bool(cap.set(cv2.CAP_PROP_CONVERT_RGB, 0))
    sizes, ts, is_jpeg, shapes = [], [], [], []
    for i in range(330):
        t0 = time.perf_counter()
        ok, buf = cap.read()
        ts.append(time.perf_counter() - t0)
        if not ok or buf is None:
            res.setdefault("read_failures", 0)
            res["read_failures"] += 1
            continue
        b = buf.reshape(-1)
        shapes.append(list(buf.shape))
        sizes.append(int(b.size))
        is_jpeg.append(bool(b.size > 4 and b[0] == 0xFF and b[1] == 0xD8))
    ts = ts[30:]
    if sizes:
        sample = cap.read()[1]
        dec = cv2.imdecode(sample.reshape(-1), cv2.IMREAD_COLOR) if sample is not None else None
        res.update({
            "first_shape": shapes[0], "all_buffers_start_with_FFD8": all(is_jpeg), "n": len(sizes),
            "bytes_per_frame_median": statistics.median(sizes), "bytes_per_frame_max": max(sizes),
            "MBps_at_60fps_median": statistics.median(sizes) * 60 / 1e6,
            "read_ms_median": statistics.median(ts) * 1e3, "loop_fps": 1 / statistics.median(ts),
            "decoded_shape": None if dec is None else list(dec.shape),
            "fourcc_reported": int(cap.get(cv2.CAP_PROP_FOURCC)).to_bytes(4, "little").decode(errors="replace"),
        })
    cap.release()
print(json.dumps(res, indent=2))
with open(os.path.join(out_dir, "probe_msmf_mjpeg_passthrough.json"), "w") as f:
    json.dump(res, f, indent=2)
