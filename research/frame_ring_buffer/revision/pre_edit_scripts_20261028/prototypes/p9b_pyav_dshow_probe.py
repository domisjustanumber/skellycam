"""P9b - can the cameras' own MJPEG bytes be read without decoding (needed for MJPEG passthrough recording)?

p9_real_camera.py showed that OpenCV 4.12 does not hand over JPEG bytes (DSHOW CAP_PROP_CONVERT_RGB=0 still returns
decoded BGR; MSMF CAP_PROP_FORMAT=-1 is refused), and that PyAV's FFmpeg dshow input returned I/O errors whenever 60 fps
was requested at a size the camera does not offer at 60 fps. This probe opens each camera through PyAV's dshow input
with vcodec=mjpeg and the framerate the camera offers (no framerate option, then 30, then 60), demuxes packets for 3 s
WITHOUT decoding, and reports fps, bytes/frame and whether packets are JPEG (start with FF D8).

Run (from C:\\Users\\Dom\\GitHub\\freemocap\\skellycam): .venv\\Scripts\\python.exe benchmarks\\frame_pipeline\\prototypes\\p9b_pyav_dshow_probe.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402

NAMES = ["c922 Pro Stream Webcam", "Logitech Webcam C930e", "Razer Kiyo Pro", "USB Camera"]
CONFIGS = [("1280x720", None), ("1280x720", "30"), ("1280x720", "60"), ("1920x1080", "30"), ("1920x1080", "60")]


def probe(name, size, fps, seconds=3.0):
    import av
    opts = {"vcodec": "mjpeg", "video_size": size, "rtbufsize": "64M"}
    if fps:
        opts["framerate"] = fps
    try:
        c = av.open(f"video={name}", format="dshow", options=opts)
    except Exception as e:
        return dict(opened=False, error=repr(e)[:120])
    try:
        st = c.streams.video[0]
        sizes, ffd8 = [], 0
        cpu0 = time.process_time()
        t0 = time.perf_counter()
        for pkt in c.demux(st):
            if pkt.size == 0:
                continue
            mv = memoryview(pkt)
            ffd8 += int(mv[0] == 0xFF and mv[1] == 0xD8)
            sizes.append(pkt.size)
            if time.perf_counter() - t0 >= seconds:
                break
        el = time.perf_counter() - t0
        return dict(opened=True, width=st.width, height=st.height, negotiated_rate=float(st.average_rate or 0), packets=len(sizes),
                    fps=len(sizes) / el, ffd8=ffd8, median_bytes=float(np.median(sizes)) if sizes else None,
                    cpu_ms_per_packet=1000 * (time.process_time() - cpu0) / max(1, len(sizes)))
    finally:
        c.close()


def main():
    import proto_common as pcm
    out = dict(env=pcm.env_summary(), rows=[])
    for name in NAMES:
        for size, fps in CONFIGS:
            r = probe(name, size, fps)
            r.update(device=name, size=size, framerate_option=fps)
            out["rows"].append(r)
            print(r, flush=True)
            time.sleep(1.0)
    pcm.write_json("p9b_pyav_dshow_probe.json", out)
    L = ["# P9b - camera MJPEG bytes through PyAV's FFmpeg dshow input (vcodec=mjpeg, demux only, no decode), 3 s each", "",
         "| device | size | framerate option | opened | negotiated rate | delivered fps | packets starting FF D8 / packets | median bytes/frame | CPU ms/packet |",
         "|---|---|---|---|---|---|---|---|---|"]
    for r in out["rows"]:
        if r["opened"]:
            L.append(f"| {r['device']} | {r['size']} | {r['framerate_option']} | yes | {r['negotiated_rate']:.1f} | {r['fps']:.1f} | {r['ffd8']} / {r['packets']} | "
                     f"{r['median_bytes']} | {r['cpu_ms_per_packet']:.3f} |")
        else:
            L.append(f"| {r['device']} | {r['size']} | {r['framerate_option']} | no: {r['error']} | - | - | - | - | - |")
    pcm.write_text("p9b_pyav_dshow_probe.md", "\n".join(L) + "\n")
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
