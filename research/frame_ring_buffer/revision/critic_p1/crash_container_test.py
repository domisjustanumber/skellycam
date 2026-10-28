"""Critic P1 test: is a recording readable after its writer process is killed without release()?

NOT SkellyCam code. Mimics the HEAD default writer (cv2.VideoWriter fourcc 'X264' -> MSMF H.264 .mp4,
camera_config.py L29 + fourcc_codec_helpers.py L58 @23ccbf20) and the P8 passthrough recorder (PyAV mjpeg packets
into .mkv, prototypes/p8_e2e_proto.py L205-239). Each writer runs in a spawned child, writes N frames of 1280x720 BGR,
signals the parent, then sleeps. The parent either lets it release normally ("clean") or calls Process.terminate()
(TerminateProcess on Windows: no finally / release), which is what WorkerRegistry.shutdown_all step 2 does
(worker_registry.py L185-195) and what a hard crash looks like. Then the file is probed with cv2 and PyAV.

Run: C:\\Users\\Dom\\GitHub\\freemocap\\skellycam\\.venv\\Scripts\\python.exe crash_container_test.py <out_dir>
"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import sys
import time
from fractions import Fraction
from pathlib import Path

N = 300  # 5 s at 60 fps
W, H = 1280, 720


def _frames():
    import numpy as np
    rng = np.random.default_rng(0)
    base = rng.integers(0, 255, (H, W, 3), dtype=np.uint8)
    return [np.roll(base, i * 8, axis=1) for i in range(30)]


def child(kind: str, path: str, ready, clean: bool):
    import cv2
    import av
    fr = _frames()
    if kind == "msmf_mp4":
        vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"X264"), 60, (W, H))
        for i in range(N):
            vw.write(fr[i % 30])
        if clean:
            vw.release()
    else:
        c = av.open(path, "w")
        st = c.add_stream("mjpeg", rate=60)
        st.width, st.height, st.pix_fmt = W, H, "yuvj420p"
        for i in range(N):
            ok, jpg = cv2.imencode(".jpg", fr[i % 30], [cv2.IMWRITE_JPEG_QUALITY, 90])
            pk = av.Packet(jpg.tobytes())
            pk.stream = st
            pk.time_base = Fraction(1, 60)
            pk.pts = pk.dts = i
            c.mux(pk)
        if clean:
            c.close()
    ready.set()
    time.sleep(60)


def probe(path: str) -> dict:
    import cv2
    import av
    out = {"exists": os.path.exists(path), "bytes": os.path.getsize(path) if os.path.exists(path) else 0}
    cap = cv2.VideoCapture(path)
    out["cv2_opened"] = bool(cap.isOpened())
    n = 0
    if cap.isOpened():
        out["cv2_prop_frame_count"] = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        while True:
            ok, _ = cap.read()
            if not ok:
                break
            n += 1
    cap.release()
    out["cv2_frames_decoded"] = n
    try:
        with av.open(path) as c:
            out["pyav_frames_decoded"] = sum(1 for _ in c.decode(video=0))
    except Exception as e:  # noqa: BLE001
        out["pyav_error"] = f"{type(e).__name__}: {e}"
    return out


def load_snapshot() -> dict:
    import psutil
    cpu = psutil.cpu_percent(interval=3.0)
    procs = []
    for p in psutil.process_iter(["name"]):
        try:
            procs.append((p.info["name"], p.cpu_percent(None)))
        except Exception:  # noqa: BLE001
            pass
    time.sleep(1.0)
    procs = []
    for p in psutil.process_iter(["name"]):
        try:
            procs.append((p.info["name"], round(p.cpu_percent(None) / psutil.cpu_count(), 2)))
        except Exception:  # noqa: BLE001
            pass
    procs = sorted([x for x in procs if x[0] != "System Idle Process"], key=lambda x: -x[1])[:8]
    return {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "cpu_pct": cpu,
            "mem_pct": psutil.virtual_memory().percent, "top_procs_pct_of_machine": procs}


def main():
    out_dir = Path(sys.argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    res = {"load_before": load_snapshot(), "frames_written": N, "size": f"{W}x{H} BGR", "runs": []}
    ctx = mp.get_context("spawn")
    for kind, ext in (("msmf_mp4", "mp4"), ("mjpeg_mkv", "mkv")):
        for clean in (True, False):
            path = str(out_dir / f"{kind}_{'clean' if clean else 'killed'}.{ext}")
            if os.path.exists(path):
                os.remove(path)
            ready = ctx.Event()
            p = ctx.Process(target=child, args=(kind, path, ready, clean))
            p.start()
            ready.wait(120)
            time.sleep(0.5)
            p.terminate()
            p.join(10)
            r = {"kind": kind, "released": clean, "exitcode": p.exitcode}
            r.update(probe(path))
            res["runs"].append(r)
            print(json.dumps(r))
    res["load_after"] = load_snapshot()
    (out_dir / "crash_container_test.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res[k] for k in ("load_before", "load_after")}))


if __name__ == "__main__":
    main()
