"""(b) Ring-buffer READ benchmark: every reader style the SkellyCam/FreeMoCap code uses.

Topology: parent creates CameraGroupSharedMemory (read_only=True) like CameraGroup.start. Five spawned
writer processes call the real put_frame(overwrite=True) paced at 60 fps (one per camera). The reader
runs in the parent process (as the SkellyCam UI relay does) and, for each style, waits for a NEW frame
to be published, then times one read (cache-cold source: the slot was just written by another core),
then immediately times a second read of the same slot (cache-warm).

Styles (production call sites in brackets):
  latest_reused        CameraSharedMemoryRingBuffer.get_latest_data(rec_array=reused)  [retrieve_latest_frame; not called in prod]
  latest_alloc         get_latest_data(rec_array=None)                                  [allocating variant]
  by_index_reused      get_data_by_index(i, rec_array=reused)                            [FreeMoCap camera_node.py L256, skeleton node L403]
  next_consuming       get_next_data(reused) on a read_only=False handle                 [only tests/demo; not called in prod]
  view_no_copy         ring_shm.buffer[i % L] view, np.asarray(image)                   [REFERENCE ONLY - no SkellyCam code does this]
  multiframe_latest    CameraGroupSharedMemory.get_latest_multiframe()  (5 cams)         [SkellyCam UI relay via CameraGroup.get_latest_frames]
  multiframe_by_number get_images_by_frame_number(n) (5 cams, allocates: cache never filled) [FreeMoCap UI: realtime_pipeline.py L479-482]
  multiframe_views     5 x buffer[i % L] views                                           [REFERENCE ONLY]

Run:  cd C:\\Users\\Dom\\GitHub\\freemocap\\skellycam && .venv\\Scripts\\python.exe benchmarks\\frame_pipeline\\baseline\\bench_b_read.py
"""
from __future__ import annotations

import multiprocessing as mp
import multiprocessing.queues  # noqa: F401  workaround: skellycam type_overloads.py L23 needs it before spawn-child unpickles a DTO (see README)
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402

N_CAMS = 5
FPS = 60.0
STYLE_S = 10.0  # total per style, split over ROUNDS interleaved rounds
ROUNDS = 5


def paced_writer(cam_idx, h, w, dto, ready_q, stop_evt):
    import bench_common as bc
    from skellycam.core.ipc.shared_memory.camera_shared_memory_ring_buffer import CameraSharedMemoryRingBuffer
    ring = CameraSharedMemoryRingBuffer.recreate(dto=dto, read_only=False)
    fr = bc.make_frame_recarray(bc.make_config(cam_idx, h, w))
    frames = bc.synthetic_frames(h, w, n=8, seed=cam_idx, noise=0)
    # first lap so every page is faulted in
    for _ in range(ring.ring_buffer_length):
        fr.frame_metadata.frame_number[0] += 1
        ring.put_frame(frame_rec_array=fr, overwrite=True)
    ready_q.put(cam_idx)
    period = int(1e9 / FPS)
    nxt = time.perf_counter_ns()
    k = 0
    while not stop_evt.is_set():
        nxt += period
        while True:
            rem = nxt - time.perf_counter_ns()
            if rem <= 0:
                break
            if rem > 2_000_000:
                time.sleep((rem - 1_500_000) / 1e9)
        fr.image[0] = frames[k % 8]  # change pixels like retrieve() would
        fr.frame_metadata.frame_number[0] += 1
        ring.put_frame(frame_rec_array=fr, overwrite=True)
        k += 1
    ring.close()


def wait_new(get_idx, last):
    while True:
        i = get_idx()
        if i != last:
            return i


def main():
    import bench_common as bc
    from skellycam.core.ipc.shared_memory.camera_group_shared_memory import CameraGroupSharedMemory
    from skellycam.core.ipc.shared_memory.camera_shared_memory_ring_buffer import CameraSharedMemoryRingBuffer
    from skellycam.core.timestamps.timebase_mapping import TimebaseMapping
    pc = time.perf_counter_ns
    out = {"env": bc.env_summary(), "n_cams": N_CAMS, "writer_fps": FPS, "seconds_per_style": STYLE_S, "rows": []}
    lines = ["# (b) ring-buffer read styles (5 cameras written at 60 fps by 5 spawned writer processes)",
             "cold = first read after the writer published the slot; warm = immediate re-read of the same slot", "",
             "| size | style | cams per read | n | cold median ms | range of 5 round medians ms | cold p99 ms | warm median ms | per-camera cold median ms | cold GB/s | frame_number mismatches |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for size_name in ("720p", "1080p"):
        h, w = bc.SIZES[size_name]
        configs = {str(i): bc.make_config(i, h, w) for i in range(N_CAMS)}
        shm = CameraGroupSharedMemory.create(camera_configs=configs, timebase_mapping=TimebaseMapping(), read_only=True)
        dtos = shm.camera_shm_dtos
        ctx = mp.get_context("spawn")
        ready_q, stop_evt = ctx.Queue(), ctx.Event()
        procs = [ctx.Process(target=paced_writer, args=(i, h, w, dtos[str(i)], ready_q, stop_evt)) for i in range(N_CAMS)]
        for p in procs:
            p.start()
        for _ in procs:
            ready_q.get(timeout=120)
        time.sleep(1.0)
        ring0 = shm.camera_shms["0"]
        L = ring0.ring_buffer_length
        itemsize = ring0.dtype.itemsize
        reused = np.recarray(1, dtype=ring0.dtype)
        consumer = CameraSharedMemoryRingBuffer.recreate(dto=dtos["0"], read_only=False)

        def s_latest_reused(i):
            return ring0.get_latest_data(rec_array=reused).frame_metadata.frame_number[0], 1

        def s_latest_alloc(i):
            return ring0.get_latest_data(rec_array=None).frame_metadata.frame_number[0], 1

        def s_by_index(i):
            return ring0.get_data_by_index(index=i, rec_array=reused).frame_metadata.frame_number[0], 1

        def s_next(i):
            return consumer.get_next_data(reused).frame_metadata.frame_number[0], 1

        def s_view(i):
            v = ring0.ring_shm.buffer[i % L]
            img = np.asarray(v.image)
            return int(v.frame_metadata.frame_number), 1 if img.shape[0] == h else 0

        def s_mf_latest(i):
            mf = shm.get_latest_multiframe()
            return int(next(iter(mf.values())).frame_metadata.frame_number[0]), N_CAMS

        def s_mf_by_number(i):
            n = shm.latest_multiframe_number
            mf = shm.get_images_by_frame_number(frame_number=n)
            return int(next(iter(mf.values())).frame_metadata.frame_number[0]), N_CAMS

        def s_mf_views(i):
            n = shm.latest_multiframe_number
            vs = [r.ring_shm.buffer[n % L] for r in shm.camera_shms.values()]
            return int(vs[0].frame_metadata.frame_number), N_CAMS

        styles = [("latest_reused", s_latest_reused, lambda: ring0.latest_frame_number),
                  ("latest_alloc", s_latest_alloc, lambda: ring0.latest_frame_number),
                  ("by_index_reused", s_by_index, lambda: ring0.latest_frame_number),
                  ("next_consuming", s_next, lambda: ring0.latest_frame_number),
                  ("view_no_copy(REFERENCE)", s_view, lambda: ring0.latest_frame_number),
                  ("multiframe_latest", s_mf_latest, lambda: shm.latest_multiframe_number),
                  ("multiframe_by_number", s_mf_by_number, lambda: shm.latest_multiframe_number),
                  ("multiframe_views(REFERENCE)", s_mf_views, lambda: shm.latest_multiframe_number)]
        acc = {name: dict(cold=[], warm=[], mism=0, ncams=1, round_medians=[]) for name, _, _ in styles}
        for rnd in range(ROUNDS):
            for name, fn, get_idx in styles:
                a = acc[name]
                if name == "next_consuming":
                    consumer.last_read_index.value = consumer.last_written_index.value  # start at the head
                last = get_idx()
                t_end = pc() + int(STYLE_S / ROUNDS * 1e9)
                rc = []
                while pc() < t_end:
                    i = wait_new(get_idx, last)
                    last = i
                    if name == "next_consuming":
                        i = consumer.last_read_index.value + 1
                    t0 = pc(); fnum, ncams = fn(i); t1 = pc()
                    a["ncams"] = ncams
                    if name == "next_consuming":
                        t2 = t3 = 0
                    else:
                        t2 = pc(); fn(i); t3 = pc()
                    a["cold"].append(t1 - t0); a["warm"].append(t3 - t2); rc.append(t1 - t0)
                    if name in ("latest_reused", "latest_alloc", "by_index_reused", "next_consuming") and fnum != i:
                        a["mism"] += 1
                a["round_medians"].append(float(np.median(rc)) / 1e6)
        for name, _, _ in styles:
            a = acc[name]
            ncams, mism = a["ncams"], a["mism"]
            sc, sw = bc.stats_ms(a["cold"]), bc.stats_ms(a["warm"])
            row = dict(size=size_name, style=name, cams_per_read=ncams, cold=sc, warm=sw, frame_number_mismatches=mism,
                       cold_round_medians_ms=a["round_medians"], record_itemsize=int(itemsize), ring_len=L,
                       cold_GBps=(ncams * itemsize / (sc["median_ms"] / 1e3) / 1e9) if sc["median_ms"] > 0 else None)
            out["rows"].append(row)
            bc.write_json("b_read.json", out)
            rm = a["round_medians"]
            line = (f"| {size_name} | {name} | {ncams} | {sc['n']} | {sc['median_ms']:.4f} | {min(rm):.3f}-{max(rm):.3f} | {sc['p99_ms']:.4f} | "
                    f"{sw.get('median_ms', 0):.4f} | {sc['median_ms'] / ncams:.4f} | "
                    f"{row['cold_GBps'] if row['cold_GBps'] is None else round(row['cold_GBps'], 2)} | {mism} |")
            lines.append(line)
            print(line, flush=True)
        stop_evt.set()
        for p in procs:
            p.join(30)
        consumer.close()
        shm.unlink_and_close()
    lines += ["", "Notes: 'view' rows only build numpy views (no bytes moved) - the GB/s figure is not a copy rate.",
              "multiframe_* rows read 5 cameras per call; per-camera column divides by 5."]
    bc.write_text("b_read.md", "\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
