"""
Cost of recording MJPEG *without* decode/re-encode: mux already-compressed JPEG frames (stand-ins for the bytes a
UVC camera sends) into a Matroska (.mkv) file with PyAV, one file per camera, 5 cameras in 5 threads.
Then re-open each file and count decodable frames to prove nothing was dropped.

Run:
    cd C:\\Users\\Dom\\GitHub\\freemocap\\skellycam
    .venv\\Scripts\\python.exe -I <scratch>\\bp_bench\\bench_mjpeg_passthrough_mux.py <out_dir>
"""
import json
import os
import sys
import threading
import time
from fractions import Fraction

import av
import cv2
import numpy as np

OUT = sys.argv[1] if len(sys.argv) > 1 else "."
TMP = os.path.join(OUT, "mux_tmp")
os.makedirs(TMP, exist_ok=True)
N = 1800  # 30 s at 60 fps per camera


def jpeg_frames(h, w, seed):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    base = np.stack([128 + 100 * np.sin(xx / 97.0) * np.cos(yy / 61.0),
                     128 + 90 * np.sin((xx + yy) / 151.0),
                     128 + 80 * np.cos(xx / 43.0 - yy / 77.0)], axis=-1)
    out = []
    for k in range(8):
        tex = cv2.GaussianBlur(rng.normal(0, 40, (h, w, 3)).astype(np.float32), (0, 0), 3)
        img = np.clip(np.roll(base, 8 * k, axis=1) + tex, 0, 255).astype(np.uint8)
        out.append(cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes())
    return out


def record(path, frames, w, h, out, i):
    c = av.open(path, "w", format="matroska")
    s = c.add_stream("mjpeg", rate=60)
    s.width, s.height = w, h
    s.pix_fmt = "yuvj420p"
    s.time_base = Fraction(1, 60)
    nbytes = 0
    t0 = time.perf_counter()
    for k in range(N):
        data = frames[k % len(frames)]
        pkt = av.Packet(data)
        pkt.stream = s
        pkt.pts = pkt.dts = k
        pkt.time_base = s.time_base
        pkt.is_keyframe = True
        c.mux(pkt)
        nbytes += len(data)
    c.close()
    dt = time.perf_counter() - t0
    out[i] = {"seconds": dt, "fps": N / dt, "bytes": nbytes, "MBps_needed_at_60fps": nbytes / N * 60 / 1e6}


def count_frames(path):
    with av.open(path) as c:
        return sum(1 for _ in c.decode(video=0))


res = {}
for name, (h, w) in {"720p": (720, 1280), "1080p": (1080, 1920)}.items():
    frames = [jpeg_frames(h, w, s) for s in range(5)]
    out = {}
    paths = [os.path.join(TMP, f"{name}_cam{i}.mkv") for i in range(5)]
    cpu0 = time.process_time(); t0 = time.perf_counter()
    ths = [threading.Thread(target=record, args=(paths[i], frames[i], w, h, out, i)) for i in range(5)]
    for t in ths: t.start()
    for t in ths: t.join()
    wall = time.perf_counter() - t0; cpu = time.process_time() - cpu0
    decoded = [count_frames(p) for p in paths]
    res[name] = {"cameras": 5, "frames_per_camera": N, "wall_s": wall, "aggregate_fps": 5 * N / wall,
                 "process_cpu_s": cpu, "cpu_ms_per_frame": cpu / (5 * N) * 1e3,
                 "decoded_frames_per_file": decoded, "per_camera": out}
    for p in paths:
        os.remove(p)
    print(name, json.dumps(res[name]["aggregate_fps"]), res[name]["cpu_ms_per_frame"], decoded, flush=True)
with open(os.path.join(OUT, "mjpeg_passthrough_mux.json"), "w") as f:
    json.dump(res, f, indent=2)
