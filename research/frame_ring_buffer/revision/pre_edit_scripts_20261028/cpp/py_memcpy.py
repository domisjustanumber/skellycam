"""Python twin of build/memcpybench.exe: the same copy scenarios, sizes, thread counts and timing rules with numpy.

  .venv\\Scripts\\python.exe benchmarks\\frame_pipeline\\cpp\\py_memcpy.py <out.json> [rep_s=2] [reps=5]

Sizes: 64x64x3, 1280x720x3, 1920x1080x3 image bytes (uint8, flat views).
Scenarios (single thread): hot_hot, hot_to_ring (dst cycles through a 512 MiB multiprocessing.shared_memory block,
prefaulted, 4 KiB-strided slots), cold_to_ring (src also cycles through a 512 MiB private array). Variant np.copyto.
Extra variant slot_assign_record (hot_to_ring only): `ring[i] = rec` with the REAL SkellyCam frame dtype
(create_frame_dtype), i.e. the structured-record slot assignment put_data does at ring_buffer_shared_memory.py L132
(bytes counted = full record incl. 632 B metadata).
Threads: hot_to_ring np.copyto with T = 1, 2, 4, 5, 8 Python threads (np.copyto releases the GIL), each thread with its
own src and its own 512 MiB block; aggregate GB/s.
Pixel ops (hypothesis C2): numpy BGR->RGB swap + vertical flip (np.copyto(dst, src[::-1, :, ::-1])) and flip only.
Timing: 0.5 s warm-up; `reps` throughput reps of `rep_s` s with the deadline checked every 64 copies (no per-copy timer);
then a 1 s latency pass timing every copy (perf_counter_ns), at most 2M samples.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from multiprocessing import shared_memory
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "baseline"))
REGION = 512 << 20
pc = time.perf_counter_ns


def round4k(n):
    return (n + 4095) // 4096 * 4096


def stats_ms(a):
    a = np.asarray(a, np.float64) / 1e6
    return {"n": int(a.size), "median_ms": float(np.median(a)), "mean_ms": float(a.mean()), "p99_ms": float(np.percentile(a, 99)),
            "min_ms": float(a.min()), "max_ms": float(a.max())}


rows = []


def add(r):
    rows.append(r)
    print(json.dumps(r), flush=True)


def new_shm():
    shm = shared_memory.SharedMemory(create=True, size=REGION)
    arr = np.ndarray((REGION,), np.uint8, shm.buf)
    arr[:] = 1  # prefault
    return shm, arr


def run_single(size_name, h, w, scen, variant, rep_s, reps):
    n = h * w * 3
    stride = round4k(n)
    nslots = REGION // stride
    src_hot = np.full(n, 3, np.uint8)
    dst_hot = np.zeros(n, np.uint8)
    shm, ring = new_shm()
    slots = np.ndarray((nslots, stride), np.uint8, shm.buf)[:, :n]
    src_ring = None
    if scen == "cold_to_ring":
        src_ring = np.full((nslots, stride), 2, np.uint8)[:, :n]
    if variant == "slot_assign_record":
        sys.path.insert(0, str(HERE.parent / "baseline"))
        import bench_common as bc
        from skellycam.core.types.frame_dtype_factories import create_frame_dtype
        dt = create_frame_dtype(bc.make_config(0, h, w))
        rec = bc.make_frame_recarray(bc.make_config(0, h, w))
        nrec = REGION // dt.itemsize
        recring = np.ndarray((nrec,), dt, shm.buf)
        n = dt.itemsize
        i = [0]

        def one():
            recring[i[0] % nrec] = rec[0]
            i[0] += 1
    else:
        i = [0]
        if scen == "hot_hot":
            def one():
                np.copyto(dst_hot, src_hot)
        elif scen == "hot_to_ring":
            def one():
                np.copyto(slots[i[0] % nslots], src_hot)
                i[0] += 1
        else:
            def one():
                k = i[0] % nslots
                np.copyto(slots[k], src_ring[k])
                i[0] += 1
    t_end = pc() + 500_000_000
    while pc() < t_end:
        one()
    gb = []
    for _ in range(reps):
        t0 = pc()
        dl = t0 + int(rep_s * 1e9)
        cnt = 0
        t = t0
        while t < dl:
            for _j in range(64):
                one()
            cnt += 64
            t = pc()
        gb.append(cnt * n / ((t - t0) / 1e9) / 1e9)
    lat = []
    dl = pc() + 1_000_000_000
    while pc() < dl and len(lat) < 2_000_000:
        a = pc(); one(); lat.append(pc() - a)
    gb.sort()
    add(dict(lang="python", size=size_name, bytes=n, scenario=scen, variant=variant, threads=1, gbps_median=gb[len(gb) // 2],
             gbps_min=gb[0], gbps_max=gb[-1], lat=stats_ms(lat)))
    del slots, ring
    if variant == "slot_assign_record":
        del recring
    shm.close(); shm.unlink()


def run_threads(size_name, h, w, T, rep_s, reps):
    n = h * w * 3
    stride = round4k(n)
    nslots = REGION // stride
    shms, slotss, srcs = [], [], []
    for _ in range(T):
        shm, _arr = new_shm()
        shms.append(shm)
        slotss.append(np.ndarray((nslots, stride), np.uint8, shm.buf)[:, :n])
        srcs.append(np.full(n, 3, np.uint8))
    gb = []
    for r in range(-1, reps):
        dur = 0.5 if r < 0 else rep_s
        counts = [0] * T
        barrier = threading.Barrier(T + 1)
        start = [0]

        def worker(t):
            slots, src = slotss[t], srcs[t]
            barrier.wait()
            dl = start[0] + int(dur * 1e9)
            c = 0
            i = 0
            while pc() < dl:
                np.copyto(slots[i % nslots], src)
                i += 1
                c += 1
            counts[t] = c
        th = [threading.Thread(target=worker, args=(t,)) for t in range(T)]
        for x in th:
            x.start()
        start[0] = pc()
        t0 = start[0]
        barrier.wait()
        for x in th:
            x.join()
        wall = (pc() - t0) / 1e9
        if r >= 0:
            gb.append(sum(counts) * n / wall / 1e9)
    gb.sort()
    add(dict(lang="python", size=size_name, bytes=n, scenario="hot_to_ring_threads", variant="np.copyto", threads=T,
             gbps_median=gb[len(gb) // 2], gbps_min=gb[0], gbps_max=gb[-1]))
    slotss.clear()
    for s in shms:
        s.close(); s.unlink()


def run_pixel(size_name, h, w, op, rep_s, reps):
    src = (np.arange(h * w * 3, dtype=np.uint64) * 7 % 256).astype(np.uint8).reshape(h, w, 3)
    dst = np.zeros_like(src)
    if op == "swap_bgr_rgb_and_flip":
        def one():
            np.copyto(dst, src[::-1, :, ::-1])
    else:
        def one():
            np.copyto(dst, src[::-1])
    t_end = pc() + 500_000_000
    while pc() < t_end:
        one()
    lat = []
    for _ in range(reps):
        dl = pc() + int(rep_s * 1e9)
        while pc() < dl:
            a = pc(); one(); lat.append(pc() - a)
    ok = int(dst[0, 0, 0] == (src[h - 1, 0, 2] if op.startswith("swap") else src[h - 1, 0, 0]))
    add(dict(lang="python", size=size_name, bytes=h * w * 3, scenario="pixel_op", variant=op, threads=1, check=ok, lat=stats_ms(lat)))


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "-"
    rep_s = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0
    reps = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    sizes = [("64x64", 64, 64), ("720p", 720, 1280), ("1080p", 1080, 1920)]
    for name, h, w in sizes:
        run_single(name, h, w, "hot_hot", "np.copyto", rep_s, reps)
        run_single(name, h, w, "hot_to_ring", "np.copyto", rep_s, reps)
        run_single(name, h, w, "hot_to_ring", "slot_assign_record", rep_s, reps)
        run_single(name, h, w, "cold_to_ring", "np.copyto", rep_s, reps)
    for name, h, w in sizes[1:]:
        for T in (1, 2, 4, 5, 8):
            run_threads(name, h, w, T, rep_s, reps)
        run_pixel(name, h, w, "swap_bgr_rgb_and_flip", rep_s, reps)
        run_pixel(name, h, w, "flip_rows", rep_s, reps)
    res = dict(tool="py_memcpy", python=sys.version.split()[0], numpy=np.__version__, rep_s=rep_s, reps=reps, rows=rows)
    if out != "-":
        Path(out).write_text(json.dumps(res))


if __name__ == "__main__":
    main()
