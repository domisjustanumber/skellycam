"""P7 - process/thread topology: do 5 per-camera workers need 5 processes, or do 5 threads in one process scale?

Workloads (each worker = one "camera"; in-memory synthetic frames, unthrottled, 1920x1080):
  imdecode     : cv2.imdecode of the q90 JPEG (cv2.setNumThreads(1))                         300 frames/worker
  simplejpeg   : simplejpeg.decode_jpeg(buffer=preallocated) (bench venv only)               300
  msmf_write   : cv2.VideoWriter('X264') -> MSMF H.264, write()+release()                    300
  h264_nvenc   : cvtColor BGR->I420 (dst prealloc) + PyAV from_ndarray + h264_nvenc encode   300
  mjpeg_mux    : PyAV av.Packet(jpeg) + mux into .mkv                                         3000
  py_overhead  : the per-frame pure-Python control-plane work of a camera loop, approximated by 40 numpy scalar
                 reads/writes on an int64 view + 9 nested recarray timestamp writes (verified code map W27/CP10)  20000
Topologies: 1 worker alone; 5 threads in one process; 5 spawned processes. Reported: aggregate fps, slowest worker fps,
scaling vs 1 worker (5.0 = perfect), process CPU% (psutil, sum over the measuring processes).

Run: .venv\\Scripts\\python.exe benchmarks\\frame_pipeline\\prototypes\\p7_topology.py
     benchmarks\\frame_pipeline\\.venv-bench\\Scripts\\python.exe benchmarks\\frame_pipeline\\prototypes\\p7_topology.py simplejpeg
"""
from __future__ import annotations

import multiprocessing as mp
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402

N = 5
REPS = int(os.environ.get("P7_REPS", "5"))  # each topology measured REPS times; medians reported, range in JSON
FRAMES = {"imdecode": 300, "simplejpeg": 300, "msmf_write": 300, "h264_nvenc": 300, "mjpeg_mux": 3000, "py_overhead": 20000}


def prepare(work, h, w, seed):
    import cv2
    import proto_common as pcm
    cv2.setNumThreads(1)
    frames = pcm.synthetic_frames(h, w, n=30, seed=seed, noise=8)
    jpegs = [cv2.imencode(".jpg", f, [int(cv2.IMWRITE_JPEG_QUALITY), 90])[1] for f in frames]
    return frames, jpegs


def do_work(work, h, w, frames, jpegs, wid, tag):
    import cv2
    import proto_common as pcm
    n = FRAMES[work]
    path = pcm.SCRATCH_TMP / f"p7_{tag}_{work}_{wid}_{os.getpid()}"
    nbytes = 0
    t0 = time.perf_counter()
    if work == "imdecode":
        for i in range(n):
            cv2.imdecode(jpegs[i % 30], cv2.IMREAD_COLOR)
    elif work == "simplejpeg":
        import simplejpeg
        dst = np.empty((h, w, 3), np.uint8)
        jb = [j.tobytes() for j in jpegs]
        for i in range(n):
            simplejpeg.decode_jpeg(jb[i % 30], colorspace="BGR", buffer=dst)
    elif work == "msmf_write":
        p = str(path) + ".mp4"
        vw = cv2.VideoWriter(p, cv2.VideoWriter_fourcc(*"X264"), 60, (w, h))
        for i in range(n):
            vw.write(frames[i % 30])
        vw.release()
        nbytes = os.path.getsize(p)
        os.remove(p)
    elif work == "h264_nvenc":
        import av
        p = str(path) + ".mp4"
        c = av.open(p, "w")
        st = c.add_stream("h264_nvenc", rate=60)
        st.width, st.height, st.pix_fmt = w, h, "yuv420p"
        st.options = {"preset": "p4", "tune": "ll", "rc": "vbr", "cq": "23"}
        i420 = np.empty((h * 3 // 2, w), np.uint8)
        for i in range(n):
            cv2.cvtColor(frames[i % 30], cv2.COLOR_BGR2YUV_I420, dst=i420)
            f = av.VideoFrame.from_ndarray(i420, format="yuv420p"); f.pts = i
            for pk in st.encode(f):
                c.mux(pk)
        for pk in st.encode():
            c.mux(pk)
        c.close()
        nbytes = os.path.getsize(p)
        os.remove(p)
    elif work == "mjpeg_mux":
        import av
        from fractions import Fraction
        p = str(path) + ".mkv"
        c = av.open(p, "w")
        st = c.add_stream("mjpeg", rate=60)
        st.width, st.height, st.pix_fmt = w, h, "yuvj420p"
        for i in range(n):
            pk = av.Packet(jpegs[i % 30]); pk.stream = st; pk.time_base = Fraction(1, 60); pk.pts = pk.dts = i
            c.mux(pk)
        c.close()
        nbytes = os.path.getsize(p)
        os.remove(p)
    elif work == "py_overhead":
        idx = np.zeros(16, np.int64)
        rec = np.recarray(1, dtype=[("ts", [(f"t{j}", np.int64) for j in range(9)])])
        for i in range(n):
            for j in range(20):
                idx[j % 16] = i
                _ = int(idx[(j + 1) % 16])
            for j in range(9):
                setattr(rec.ts, f"t{j}", i)
    return n / (time.perf_counter() - t0), nbytes


def proc_target(work, h, w, wid, start_evt, q):
    frames, jpegs = prepare(work, h, w, wid)
    q.put(("ready", wid))
    start_evt.wait()
    c0 = time.process_time()
    t0 = time.perf_counter()
    fps, nb = do_work(work, h, w, frames, jpegs, wid, "proc")
    q.put(("done", wid, fps, time.process_time() - c0, time.perf_counter() - t0, nb))


def run_threads(work, h, w, n):
    data = [prepare(work, h, w, i) for i in range(n)]
    res = [None] * n
    nbs = [0] * n
    bar = threading.Barrier(n)

    def t(i):
        bar.wait()
        res[i], nbs[i] = do_work(work, h, w, data[i][0], data[i][1], i, f"thr{n}")
    ths = [threading.Thread(target=t, args=(i,)) for i in range(n)]
    c0 = time.process_time()
    t0 = time.perf_counter()
    for x in ths:
        x.start()
    for x in ths:
        x.join()
    el = time.perf_counter() - t0
    return res, 100 * (time.process_time() - c0) / el, sum(nbs)


def run_procs(work, h, w, n):
    ctx = mp.get_context("spawn")
    q, ev = ctx.Queue(), ctx.Event()
    ps = [ctx.Process(target=proc_target, args=(work, h, w, i, ev, q)) for i in range(n)]
    for p in ps:
        p.start()
    for _ in ps:
        q.get(timeout=300)
    ev.set()
    out = [q.get(timeout=600) for _ in ps]
    for p in ps:
        p.join(30)
    cpu = sum(o[3] for o in out) / max(o[4] for o in out) * 100
    return [o[2] for o in out], cpu, sum(o[5] for o in out)


def main():
    import proto_common as pcm
    h, w = pcm.SIZES["1080p"]
    sel = [a for a in sys.argv[1:]]
    works = sel or ["imdecode", "msmf_write", "h264_nvenc", "mjpeg_mux", "py_overhead"]
    tag = "benchvenv" if "simplejpeg" in works else "skellycamvenv"
    out = dict(env=pcm.env_summary(), rows=[])
    for work in works:
        reps = []
        tmp_bytes = 0
        for rep in range(REPS):
            one, cpu1, b1 = run_threads(work, h, w, 1)
            thr, cput, b2 = run_threads(work, h, w, N)
            prc, cpup, b3 = run_procs(work, h, w, N)
            tmp_bytes += b1 + b2 + b3
            reps.append(dict(single_fps=one[0], single_cpu_pct=cpu1, threads_fps=thr, threads_cpu_pct=cput, procs_fps=prc, procs_cpu_pct=cpup))
        med = lambda xs: float(np.median(xs))
        rng = lambda xs: [float(min(xs)), float(max(xs))]
        single = [r["single_fps"] for r in reps]
        tagg = [sum(r["threads_fps"]) for r in reps]
        pagg = [sum(r["procs_fps"]) for r in reps]
        row = dict(work=work, frames_per_worker=FRAMES[work], reps=REPS, rep_detail=reps, temp_file_bytes_written_then_deleted=tmp_bytes,
                   single_fps=med(single), single_fps_range=rng(single), single_cpu_pct=med([r["single_cpu_pct"] for r in reps]),
                   threads_aggregate_fps=med(tagg), threads_aggregate_range=rng(tagg),
                   threads_slowest_fps=med([min(r["threads_fps"]) for r in reps]), threads_scaling=med(tagg) / med(single),
                   threads_cpu_pct=med([r["threads_cpu_pct"] for r in reps]),
                   procs_aggregate_fps=med(pagg), procs_aggregate_range=rng(pagg),
                   procs_slowest_fps=med([min(r["procs_fps"]) for r in reps]), procs_scaling=med(pagg) / med(single),
                   procs_cpu_pct=med([r["procs_cpu_pct"] for r in reps]))
        out["rows"].append(row)
        pcm.write_json(f"p7_topology_{tag}.json", out)
        print(f"{work}: single {row['single_fps']:.0f} fps | 5 threads agg {row['threads_aggregate_fps']:.0f} slowest {row['threads_slowest_fps']:.0f} "
              f"x{row['threads_scaling']:.2f} cpu {row['threads_cpu_pct']:.0f}% | 5 procs agg {row['procs_aggregate_fps']:.0f} slowest "
              f"{row['procs_slowest_fps']:.0f} x{row['procs_scaling']:.2f} cpu {row['procs_cpu_pct']:.0f}%", flush=True)
    # merge md
    import json
    rows = []
    for t in ("skellycamvenv", "benchvenv"):
        p = pcm.RESULTS / f"p7_topology_{t}.json"
        if p.exists():
            rows += json.loads(p.read_text())["rows"]
    L = ["# P7 - topology: 5 workers as threads in one process vs 5 spawned processes (1920x1080, unthrottled)", "",
         f"Median of {REPS} repetitions per cell (ranges in the JSON). scaling = aggregate fps / single-worker fps (5.0 = perfect). "
         "CPU % = process CPU time / wall (100 = 1 logical CPU).", "",
         "| workload | frames/worker | 1 worker fps | 5 threads: aggregate / slowest fps (scaling) | 5 threads CPU % | 5 processes: aggregate / slowest fps (scaling) | 5 processes CPU % |",
         "|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['work']} | {r['frames_per_worker']} | {r['single_fps']:.0f} | {r['threads_aggregate_fps']:.0f} / {r['threads_slowest_fps']:.0f} (x{r['threads_scaling']:.2f}) | "
                 f"{r['threads_cpu_pct']:.0f} | {r['procs_aggregate_fps']:.0f} / {r['procs_slowest_fps']:.0f} (x{r['procs_scaling']:.2f}) | {r['procs_cpu_pct']:.0f} |")
    pcm.write_text("p7_topology.md", "\n".join(L) + "\n")
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
