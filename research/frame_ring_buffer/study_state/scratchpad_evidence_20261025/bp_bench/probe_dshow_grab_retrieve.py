"""
Probe how OpenCV's DSHOW and MSMF backends split work between grab() and retrieve() on a real camera.
Reports: whether set(CAP_PROP_BUFFERSIZE, 1) is accepted, and per-call grab()/retrieve() durations.

Run (camera index 0, 1280x720 MJPG @ 60 requested):
    cd C:\\Users\\Dom\\GitHub\\freemocap\\skellycam
    .venv\\Scripts\\python.exe -I <scratch>\\bp_bench\\probe_dshow_grab_retrieve.py <out_dir> [camera_index] [fourcc_before_size_only]
"""
import json
import os
import statistics
import sys
import time

import cv2
import numpy as np

out_dir = sys.argv[1] if len(sys.argv) > 1 else "."
idx = int(sys.argv[2]) if len(sys.argv) > 2 else 0
fourcc_before_size_only = len(sys.argv) > 3 and sys.argv[3] == "fourcc_before_size_only"
res = {}
for name, api in (("DSHOW", cv2.CAP_DSHOW), ("MSMF", cv2.CAP_MSMF)):
    cap = cv2.VideoCapture(idx, api)
    if not cap.isOpened():
        res[name] = {"error": "could not open"}
        continue
    # DSHOW applies FOURCC only if it is set after the frame size (order matters); set it both before and after
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_FPS, 60)
    if not fourcc_before_size_only:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*"MJPG"))
    buf_set = cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    ok, img = cap.read()
    if not ok:
        res[name] = {"error": "read failed"}
        cap.release()
        continue
    pre = np.empty_like(img)
    for _ in range(30):
        cap.read()
    g, r, loop = [], [], []
    same_buffer = True
    t_last = time.perf_counter()
    for _ in range(300):
        t0 = time.perf_counter(); cap.grab(); t1 = time.perf_counter()
        ok, out = cap.retrieve(image=pre); t2 = time.perf_counter()
        same_buffer &= out.__array_interface__["data"][0] == pre.__array_interface__["data"][0]
        g.append(t1 - t0); r.append(t2 - t1); loop.append(t2 - t_last); t_last = t2
    res[name] = {
        "set_CAP_PROP_BUFFERSIZE_1_returned": bool(buf_set),
        "get_CAP_PROP_BUFFERSIZE": cap.get(cv2.CAP_PROP_BUFFERSIZE),
        "actual_w_h_fps_fourcc": [cap.get(cv2.CAP_PROP_FRAME_WIDTH), cap.get(cv2.CAP_PROP_FRAME_HEIGHT),
                                  cap.get(cv2.CAP_PROP_FPS),
                                  int(cap.get(cv2.CAP_PROP_FOURCC)).to_bytes(4, "little").decode(errors="replace")],
        "grab_ms_median": statistics.median(g) * 1e3, "grab_ms_max": max(g) * 1e3,
        "retrieve_ms_median": statistics.median(r) * 1e3, "retrieve_ms_max": max(r) * 1e3,
        "loop_fps": 1 / statistics.median(loop),
        "retrieve_wrote_into_preallocated_array": bool(same_buffer),
    }
    cap.release()
print(json.dumps(res, indent=2))
with open(os.path.join(out_dir, "probe_dshow_grab_retrieve" + ("_fourcc_before_size_only" if fourcc_before_size_only else "") + ".json"), "w") as f:
    json.dump(res, f, indent=2)
