"""Python twin of build/microbench.exe: per-operation fixed costs (SkellyCam venv; uses the REAL SkellyCam classes).

  .venv\\Scripts\\python.exe research\\frame_ring_buffer\\cpp\\py_micro.py <out.json>

1. control-plane ops, ns/op as throughput (N ops x 5 reps after a warm-up rep), same method as microbench.exe:
   numpy int64 view store / load on a shared_memory block (what the prototype SeqRing uses);
   SkellyCam SharedMemoryNumber.value write / read (shared_memory_number.py L23-33; used 3-5x per put_data / get_*);
   the nested recarray timestamp write the camera loop does ~31x per frame
   (`frame_rec_array.frame_metadata.timestamps.pre_frame_grab_ns[0] = ...`, opencv_camera_loop.py L133-147);
   time.perf_counter_ns().
2. cross-process ping-pong latency (spawned process, pure spin), 200,000 round trips after 10,000 warm-up:
   numpy int64 views, and SkellyCam SharedMemoryNumber (.value on both sides; 20,000 + 2,000 warm-up because each op is ~us).
3. sleep granularity: time.sleep(0), (1e-5), (1e-4), (1e-3); 500 samples each after 20 warm-up.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import multiprocessing.queues  # noqa: F401
import os
import sys
import time
from multiprocessing import shared_memory
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "baseline"))
pc = time.perf_counter_ns
rows = []


def add(r):
    rows.append(r)
    print(json.dumps(r), flush=True)


def stats_ms(a):
    a = np.asarray(a, np.float64) / 1e6
    return {"n": int(a.size), "median_ms": float(np.median(a)), "mean_ms": float(a.mean()), "p99_ms": float(np.percentile(a, 99)),
            "min_ms": float(a.min()), "max_ms": float(a.max())}


def bench_op(name, fn, n):
    vals = []
    for r in range(6):
        t0 = pc()
        for i in range(n):
            fn(i)
        v = (pc() - t0) / n
        if r:
            vals.append(v)
    vals.sort()
    add(dict(lang="python", group="control_op", op=name, ns_per_op_median=vals[len(vals) // 2], ns_min=vals[0], ns_max=vals[-1], n_per_rep=n))


def pong_np(name, n):
    shm = shared_memory.SharedMemory(name=name)
    a = np.ndarray((1,), np.int64, shm.buf, 0)
    b = np.ndarray((1,), np.int64, shm.buf, 64)
    for i in range(1, n + 1):
        while a[0] != i:
            pass
        b[0] = i
    del a, b
    shm.close()


def pong_smn(dto_a, dto_b, n):
    from skellycam.core.ipc.shared_memory.shared_memory_number import SharedMemoryNumber
    a = SharedMemoryNumber.recreate(dto=dto_a, read_only=False)
    b = SharedMemoryNumber.recreate(dto=dto_b, read_only=False)
    for i in range(1, n + 1):
        while a.value != i:
            pass
        b.value = i
    a.close(); b.close()


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "-"
    import bench_common as bc
    from skellycam.core.ipc.shared_memory.shared_memory_number import SharedMemoryNumber
    # ---- 1. control-plane ops
    shm = shared_memory.SharedMemory(create=True, size=4096)
    x = np.ndarray((1,), np.int64, shm.buf, 0)

    def st(i):
        x[0] = i
    sink = [0]

    def ld(i):
        sink[0] = x[0]
    bench_op("numpy_int64_view_store_shm", st, 1_000_000)
    bench_op("numpy_int64_view_load_shm", ld, 1_000_000)
    smn = SharedMemoryNumber.create(read_only=False, initial_value=-1)

    def smn_w(i):
        smn.value = i

    def smn_r(i):
        sink[0] = smn.value
    bench_op("skellycam_SharedMemoryNumber_value_write", smn_w, 100_000)
    bench_op("skellycam_SharedMemoryNumber_value_read", smn_r, 100_000)
    fr = bc.make_frame_recarray(bc.make_config(0, 1080, 1920))

    def nested(i):
        fr.frame_metadata.timestamps.pre_frame_grab_ns[0] = i
    bench_op("skellycam_nested_recarray_timestamp_write", nested, 100_000)
    ts_view = fr.frame_metadata.timestamps.pre_frame_grab_ns  # cached field view (the Python fix)

    def cached(i):
        ts_view[0] = i
    bench_op("cached_field_view_timestamp_write", cached, 1_000_000)

    def tmr(i):
        sink[0] = pc()
    bench_op("perf_counter_ns", tmr, 1_000_000)
    del x
    # ---- 2. ping-pong
    ctx = mp.get_context("spawn")
    N, WARM = 210_000, 10_000
    a = np.ndarray((1,), np.int64, shm.buf, 0)
    b = np.ndarray((1,), np.int64, shm.buf, 64)
    a[0] = 0; b[0] = 0
    p = ctx.Process(target=pong_np, args=(shm.name, N))
    p.start()
    time.sleep(2.0)  # child import + attach
    lat = []
    for i in range(1, N + 1):
        t0 = pc()
        a[0] = i
        while b[0] != i:
            pass
        if i > WARM:
            lat.append(pc() - t0)
    p.join(30)
    add(dict(lang="python", group="pingpong", op="numpy_int64_spin_cross_process_round_trip", lat=stats_ms(lat)))
    del a, b
    shm.close(); shm.unlink()
    N2, WARM2 = 22_000, 2_000
    sa = SharedMemoryNumber.create(read_only=False, initial_value=0)
    sb = SharedMemoryNumber.create(read_only=False, initial_value=0)
    p = ctx.Process(target=pong_smn, args=(sa.to_dto(), sb.to_dto(), N2))
    p.start()
    time.sleep(4.0)
    lat = []
    for i in range(1, N2 + 1):
        t0 = pc()
        sa.value = i
        while sb.value != i:
            pass
        if i > WARM2:
            lat.append(pc() - t0)
    p.join(30)
    add(dict(lang="python", group="pingpong", op="skellycam_SharedMemoryNumber_spin_cross_process_round_trip", lat=stats_ms(lat)))
    # ---- 3. sleep
    for arg in (0, 1e-5, 1e-4, 1e-3):
        lat = []
        for i in range(520):
            t0 = pc(); time.sleep(arg)
            if i >= 20:
                lat.append(pc() - t0)
        add(dict(lang="python", group="sleep", op=f"time.sleep({arg:g})", lat=stats_ms(lat)))
    res = dict(tool="py_micro", python=sys.version.split()[0], numpy=np.__version__, rows=rows)
    if out != "-":
        Path(out).write_text(json.dumps(res))
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
