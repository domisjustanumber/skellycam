"""(a) Ring-buffer WRITE benchmark using the real SkellyCam shared-memory classes.

Topology (mirrors SkellyCam): the parent creates CameraGroupSharedMemory.create(..., read_only=True)
(as CameraGroup.start does), and each camera gets its own *spawned* writer process that attaches with
CameraSharedMemoryRingBuffer.recreate(dto, read_only=False) and calls put_frame(frame_rec_array,
overwrite=True) exactly like opencv_camera_loop.py L96.

Per config: every writer first does one full lap of the ring (first-touch page faults, timed
separately), then all writers start together and write UNTHROTTLED for DURATION_S seconds, timing
every put_frame call. That gives max sustained put_frame rate per camera with N cameras in parallel.

mode "production": camera_shm.put_frame(...)                  (copy.copy + slot assignment)
mode "single_copy_reference": np.copyto(buffer[i:i+1], frame) + last_written_index.value = i
     (NOT SkellyCam code - a reference for what one copy into the same shm slot costs)

Run:  cd C:\\Users\\Dom\\GitHub\\freemocap\\skellycam && .venv\\Scripts\\python.exe benchmarks\\frame_pipeline\\baseline\\bench_a_write.py
"""
from __future__ import annotations

import multiprocessing as mp
import multiprocessing.queues  # noqa: F401  workaround: skellycam type_overloads.py L23 needs it before spawn-child unpickles a DTO (see README)
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402

DURATION_S = 10.0


def writer_proc(cam_idx, h, w, dto, mode, ready_q, start_evt, result_q):
    import bench_common as bc
    from skellycam.core.ipc.shared_memory.camera_shared_memory_ring_buffer import CameraSharedMemoryRingBuffer
    ring = CameraSharedMemoryRingBuffer.recreate(dto=dto, read_only=False)
    cfg = bc.make_config(cam_idx, h, w)
    fr = bc.make_frame_recarray(cfg)
    L = ring.ring_buffer_length
    pc = time.perf_counter_ns

    def put_prod():
        ring.put_frame(frame_rec_array=fr, overwrite=True)

    buf = ring.ring_shm.buffer

    def put_ref():
        i = ring.last_written_index.value + 1
        np.copyto(buf[i % L: i % L + 1], fr)
        ring.last_written_index.value = i

    put = put_prod if mode == "production" else put_ref
    first_lap = []
    for _ in range(L):
        fr.frame_metadata.frame_number[0] += 1
        t0 = pc(); put(); first_lap.append(pc() - t0)
    ready_q.put(cam_idx)
    start_evt.wait()
    lat = []
    t_start = pc()
    deadline = t_start + int(DURATION_S * 1e9)
    n = 0
    while True:
        fr.frame_metadata.frame_number[0] += 1
        t0 = pc(); put(); t1 = pc()
        lat.append(t1 - t0)
        n += 1
        if t1 >= deadline:
            break
    elapsed = (pc() - t_start) / 1e9
    # verify last slot content landed in shm
    last = ring.last_written_index.value
    ok = int(buf[last % L].frame_metadata.frame_number) == int(fr.frame_metadata.frame_number[0])
    result_q.put(dict(cam=cam_idx, n=n, elapsed_s=elapsed, fps=n / elapsed, ring_len=L,
                      itemsize=int(fr.dtype.itemsize), first_lap=bc.stats_ms(first_lap),
                      steady=bc.stats_ms(lat), last_slot_verified=ok))
    ring.close()


def run_config(size_name, n_cams, mode):
    import bench_common as bc
    from skellycam.core.ipc.shared_memory.camera_group_shared_memory import CameraGroupSharedMemory
    from skellycam.core.timestamps.timebase_mapping import TimebaseMapping
    h, w = bc.SIZES[size_name]
    configs = {str(i): bc.make_config(i, h, w) for i in range(n_cams)}
    shm = CameraGroupSharedMemory.create(camera_configs=configs, timebase_mapping=TimebaseMapping(), read_only=True)
    dtos = shm.camera_shm_dtos
    ctx = mp.get_context("spawn")
    ready_q, result_q, start_evt = ctx.Queue(), ctx.Queue(), ctx.Event()
    procs = [ctx.Process(target=writer_proc, args=(i, h, w, dtos[str(i)], mode, ready_q, start_evt, result_q))
             for i in range(n_cams)]
    for p in procs:
        p.start()
    for _ in procs:
        ready_q.get(timeout=120)
    start_evt.set()
    res = sorted([result_q.get(timeout=120) for _ in procs], key=lambda r: r["cam"])
    for p in procs:
        p.join(30)
    shm.unlink_and_close()
    itemsize = res[0]["itemsize"]
    agg_fps = sum(r["fps"] for r in res)
    return dict(size=size_name, n_cams=n_cams, mode=mode, per_camera=res,
                min_cam_fps=min(r["fps"] for r in res), aggregate_fps=agg_fps,
                aggregate_GBps=agg_fps * itemsize / 1e9,
                median_of_cam_median_ms=float(np.median([r["steady"]["median_ms"] for r in res])),
                max_cam_p99_ms=max(r["steady"]["p99_ms"] for r in res),
                first_lap_median_ms=float(np.median([r["first_lap"]["median_ms"] for r in res])))


def main():
    import bench_common as bc
    out = {"env": bc.env_summary(), "duration_s_per_config": DURATION_S, "rows": []}
    lines = ["# (a) ring-buffer write: put_frame unthrottled, N spawned writer processes",
             f"steady state {DURATION_S}s per config after one full first lap; times are per put_frame call",
             "", "| size | N cams | mode | per-cam fps (min) | aggregate fps | aggregate GB/s | median ms | worst-cam p99 ms | first-lap median ms | 60fps budget used by put_frame (median) |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for size_name in ("720p", "1080p"):
        for mode in ("production", "single_copy_reference"):
            for n in range(1, 6):
                r = run_config(size_name, n, mode)
                out["rows"].append(r)
                bc.write_json("a_write.json", out)
                row = (f"| {size_name} | {n} | {mode} | {r['min_cam_fps']:.0f} | {r['aggregate_fps']:.0f} | "
                       f"{r['aggregate_GBps']:.2f} | {r['median_of_cam_median_ms']:.3f} | {r['max_cam_p99_ms']:.3f} | "
                       f"{r['first_lap_median_ms']:.3f} | {100 * r['median_of_cam_median_ms'] / 16.667:.1f}% |")
                lines.append(row)
                print(row, flush=True)
    bc.write_text("a_write.md", "\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
