"""(g) Reference: cost of the synthetic camera stand-ins used by bench_e_e2e.FakeCapture.retrieve.

NOT SkellyCam code - this measures the substitute for cv2.VideoCapture.retrieve() so the e2e numbers can be
interpreted: cv2.imdecode of the same JPEG q90 synthetic frames (+ np.copyto into a recarray image view, as
FakeCapture does) vs a plain np.copyto, in 1 process and in 5 parallel spawned processes, 10 s each.

Run:  cd C:\\Users\\Dom\\GitHub\\freemocap\\skellycam && .venv\\Scripts\\python.exe research\\frame_ring_buffer\\baseline\\bench_g_decode_ref.py
"""
from __future__ import annotations

import multiprocessing as mp
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cv2  # noqa: E402
import numpy as np  # noqa: E402

DUR = 10.0


def worker(h, w, mode, seed, start_evt, q):
    import bench_common as bc
    frames = bc.synthetic_frames(h, w, n=30, seed=seed, noise=8)
    jpegs = [cv2.imencode(".jpg", f, [int(cv2.IMWRITE_JPEG_QUALITY), 90])[1] for f in frames]
    dst = np.zeros((h, w, 3), np.uint8)
    start_evt.wait()
    lat = []
    t_end = time.perf_counter_ns() + int(DUR * 1e9)
    k = 0
    while time.perf_counter_ns() < t_end:
        a = time.perf_counter_ns()
        if mode == "mjpeg":
            np.copyto(dst, cv2.imdecode(jpegs[k % 30], cv2.IMREAD_COLOR))
        else:
            np.copyto(dst, frames[k % 30])
        lat.append(time.perf_counter_ns() - a)
        k += 1
    q.put(dict(seed=seed, n=k, fps=k / DUR, jpeg_bytes_mean=float(np.mean([j.nbytes for j in jpegs])), lat=bc.stats_ms(lat)))


def main():
    import bench_common as bc
    out = {"env": bc.env_summary(), "duration_s": DUR, "rows": []}
    lines = ["# (g) reference cost of FakeCapture.retrieve stand-ins (not SkellyCam code)", "",
             "| size | mode | parallel procs | median ms | p99 ms | per-proc fps | mean JPEG KB |", "|---|---|---|---|---|---|---|"]
    ctx = mp.get_context("spawn")
    for size_name in ("720p", "1080p"):
        h, w = bc.SIZES[size_name]
        for mode in ("mjpeg", "memcpy"):
            for n in (1, 5):
                q, ev = ctx.Queue(), ctx.Event()
                ps = [ctx.Process(target=worker, args=(h, w, mode, i, ev, q)) for i in range(n)]
                for p in ps:
                    p.start()
                time.sleep(8.0 if size_name == "1080p" else 5.0)  # let workers build frames
                ev.set()
                res = [q.get(timeout=120) for _ in ps]
                for p in ps:
                    p.join(30)
                row = dict(size=size_name, mode=mode, n=n, per_proc=res)
                out["rows"].append(row)
                bc.write_json("g_decode_ref.json", out)
                line = (f"| {size_name} | {mode} | {n} | {np.median([r['lat']['median_ms'] for r in res]):.2f} | "
                        f"{max(r['lat']['p99_ms'] for r in res):.2f} | {min(r['fps'] for r in res):.0f} | {res[0]['jpeg_bytes_mean'] / 1e3:.0f} |")
                lines.append(line)
                print(line, flush=True)
    bc.write_text("g_decode_ref.md", "\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
