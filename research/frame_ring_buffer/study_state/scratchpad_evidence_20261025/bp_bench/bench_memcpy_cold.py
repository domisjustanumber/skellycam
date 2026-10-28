"""
memcpy cost with cache-cold source and destination (a camera frame arriving from DMA is not in L3), and
the cost of 5 such copies running concurrently (5 camera processes copying into shared memory at once).

Run:
    cd C:\\Users\\Dom\\GitHub\\freemocap\\skellycam
    .venv\\Scripts\\python.exe -I <scratch>\\bp_bench\\bench_memcpy_cold.py <out_dir>
"""
import json
import multiprocessing as mp
import os
import statistics
import sys
import time

import numpy as np

SIZES = {"720p": (720, 1280, 3), "1080p": (1080, 1920, 3)}
POOL = 32  # 32 x 6.2 MB = 199 MB per side at 1080p, far larger than the 33 MB L3 of an i7-14700K


def worker(shape, n, q):
    src = [np.full(shape, i, np.uint8) for i in range(POOL)]
    dst = [np.zeros(shape, np.uint8) for _ in range(POOL)]
    ts = []
    for i in range(n):
        t0 = time.perf_counter()
        np.copyto(dst[(i * 7) % POOL], src[i % POOL])
        ts.append(time.perf_counter() - t0)
    q.put(ts[20:])


def run(shape, n_procs, n=400):
    q = mp.Queue()
    ps = [mp.Process(target=worker, args=(shape, n, q)) for _ in range(n_procs)]
    for p in ps: p.start()
    all_ts = []
    for _ in ps: all_ts += q.get()
    for p in ps: p.join()
    med = statistics.median(all_ts)
    nbytes = int(np.prod(shape))
    return {"median_ms": med * 1e3, "p99_ms": sorted(all_ts)[int(0.99 * (len(all_ts) - 1))] * 1e3,
            "per_copy_GBps": nbytes / med / 1e9, "processes": n_procs}


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    res = {k: {"1_proc": run(s, 1), "5_procs_concurrent": run(s, 5)} for k, s in SIZES.items()}
    print(json.dumps(res, indent=2))
    with open(os.path.join(out, "memcpy_cold.json"), "w") as f:
        json.dump(res, f, indent=2)
