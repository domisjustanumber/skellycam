"""(d) UI path benchmark: the real SkellyCam frame->UI serialisation for 5 cameras.

Topology: 5 spawned writer processes publish frames with the real put_frame(overwrite=True) at 60 fps into a
CameraGroupSharedMemory created by the parent (read_only=True) - same as CameraGroup.start. The parent
runs an asyncio loop that mimics WebsocketServer._frontend_image_relay (websocket_server.py L189-212):
  await await_10ms(); frames = shm.get_latest_multiframe(); create_frontend_payload(frames, None)
with an instant client ack (no browser), i.e. the most UI work the server can be asked to do.
Also measured: the FreeMoCap UI path get_images_by_frame_number(n) + create_frontend_payload
(realtime_pipeline.py L479-482 -> camera_group.py L148-166), and a no-sleep hot loop (max build rate).

Content: bench_common.synthetic_frames(noise=8) cycled per camera (30 distinct frames).

Run:  cd C:\\Users\\Dom\\GitHub\\freemocap\\skellycam && .venv\\Scripts\\python.exe benchmarks\\frame_pipeline\\baseline\\bench_d_ui.py
"""
from __future__ import annotations

import asyncio
import multiprocessing as mp
import multiprocessing.queues  # noqa: F401  workaround for skellycam type_overloads.py L23 (see README)
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402

N_CAMS = 5
FPS = 60.0
RUN_S = 15.0


def content_writer(cam_idx, h, w, dto, ready_q, stop_evt):
    import bench_common as bc
    from skellycam.core.ipc.shared_memory.camera_shared_memory_ring_buffer import CameraSharedMemoryRingBuffer
    ring = CameraSharedMemoryRingBuffer.recreate(dto=dto, read_only=False)
    fr = bc.make_frame_recarray(bc.make_config(cam_idx, h, w))
    frames = bc.synthetic_frames(h, w, n=30, seed=cam_idx, noise=8)
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
        fr.image[0] = frames[k % 30]
        tnow = time.perf_counter_ns()
        fr.frame_metadata.timestamps.pre_frame_grab_ns[0] = tnow
        fr.frame_metadata.timestamps.post_frame_grab_ns[0] = tnow
        fr.frame_metadata.frame_number[0] += 1
        ring.put_frame(frame_rec_array=fr, overwrite=True)
        k += 1
    ring.close()


async def relay_like(shm, create_frontend_payload, await_10ms, seconds, path, sleep=True):
    pc = time.perf_counter_ns
    copy_ns, build_ns, total_ns, sizes, latency_ns, fns = [], [], [], [], [], []
    t_end = pc() + int(seconds * 1e9)
    t_first = None
    while pc() < t_end:
        if sleep:
            await await_10ms()
        a = pc()
        if path == "skellycam_ui":
            frames = shm.get_latest_multiframe()
        else:
            frames = shm.get_images_by_frame_number(frame_number=shm.latest_multiframe_number)
        b = pc()
        fn, mf_ts, payload = create_frontend_payload(latest_frames=frames, display_image_sizes=None)
        c = pc()
        t_first = t_first or a
        copy_ns.append(b - a); build_ns.append(c - b); total_ns.append(c - a)
        sizes.append(len(payload)); latency_ns.append(c - mf_ts); fns.append(int(fn))
    elapsed = (pc() - t_first) / 1e9
    import bench_common as bc
    uniq = len(set(fns))
    return dict(path=path, sleep_10ms=sleep, payloads=len(total_ns), elapsed_s=elapsed, payload_fps=len(total_ns) / elapsed,
                distinct_frame_numbers=uniq, distinct_fps=uniq / elapsed, duplicate_payloads=len(fns) - uniq,
                shm_copy=bc.stats_ms(copy_ns), resize_jpeg_pack=bc.stats_ms(build_ns), total=bc.stats_ms(total_ns),
                age_of_frame_when_payload_ready=bc.stats_ms(latency_ns),
                payload_bytes_median=float(np.median(sizes)), payload_MBps_out=float(np.median(sizes)) * len(sizes) / elapsed / 1e6)


def main():
    import psutil
    import bench_common as bc
    from skellycam.core.ipc.shared_memory.camera_group_shared_memory import CameraGroupSharedMemory
    from skellycam.core.timestamps.timebase_mapping import TimebaseMapping
    from skellycam.core.types.frontend_payload_bytearray import create_frontend_payload
    from skellycam.utilities.wait_functions import await_10ms
    out = {"env": bc.env_summary(), "n_cams": N_CAMS, "writer_fps": FPS, "seconds_per_row": RUN_S, "rows": []}
    lines = ["# (d) UI path: shm read + create_frontend_payload (resize 0.5, JPEG q60, pack) for 5 cameras", "",
             "| size | path | 10ms relay sleep | payloads/s | distinct frames/s | dup payloads | shm copy median ms | resize+jpeg+pack median ms | p99 ms | total median ms | payload KB | main-proc CPU% |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    me = psutil.Process()
    for size_name in ("720p", "1080p"):
        h, w = bc.SIZES[size_name]
        configs = {str(i): bc.make_config(i, h, w) for i in range(N_CAMS)}
        shm = CameraGroupSharedMemory.create(camera_configs=configs, timebase_mapping=TimebaseMapping(), read_only=True)
        dtos = shm.camera_shm_dtos
        ctx = mp.get_context("spawn")
        ready_q, stop_evt = ctx.Queue(), ctx.Event()
        procs = [ctx.Process(target=content_writer, args=(i, h, w, dtos[str(i)], ready_q, stop_evt)) for i in range(N_CAMS)]
        for p in procs:
            p.start()
        for _ in procs:
            ready_q.get(timeout=120)
        time.sleep(1.0)
        for path, sleep in (("skellycam_ui", True), ("freemocap_ui_by_number", True), ("skellycam_ui", False)):
            c0 = me.cpu_times()
            t0 = time.perf_counter()
            r = asyncio.run(relay_like(shm, create_frontend_payload, await_10ms, RUN_S, path, sleep))
            c1 = me.cpu_times()
            r["main_process_cpu_pct"] = 100 * ((c1.user - c0.user) + (c1.system - c0.system)) / (time.perf_counter() - t0)
            r["size"] = size_name
            out["rows"].append(r)
            bc.write_json("d_ui.json", out)
            line = (f"| {size_name} | {path} | {sleep} | {r['payload_fps']:.1f} | {r['distinct_fps']:.1f} | {r['duplicate_payloads']} | "
                    f"{r['shm_copy']['median_ms']:.2f} | {r['resize_jpeg_pack']['median_ms']:.2f} | {r['total']['p99_ms']:.2f} | "
                    f"{r['total']['median_ms']:.2f} | {r['payload_bytes_median'] / 1e3:.0f} | {r['main_process_cpu_pct']:.0f} |")
            lines.append(line)
            print(line, flush=True)
        stop_evt.set()
        for p in procs:
            p.join(30)
        shm.unlink_and_close()
    lines += ["", "No browser attached: ack is instant, so these are upper bounds on server-side UI work/rate.",
              "dup payloads = payloads whose frame_number was already sent (if_newer_than is ignored, camera_group.py L133-146)."]
    bc.write_text("d_ui.md", "\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
