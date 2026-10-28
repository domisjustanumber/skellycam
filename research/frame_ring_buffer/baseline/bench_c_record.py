"""(c) Record path benchmark using the real SkellyCam VideoRecorder.

Each camera = one spawned process (as in SkellyCam, where VideoRecorder lives inside the camera
process, opencv_camera_loop.py L99-105). Each process:
  VideoRecorder.create(recording_info, config, framerate=60.0)   -> real codec resolution
       (resolve_writer_fourcc probe, default writer_fourcc 'X264', camera_config.py L29)
  loop: copy next synthetic frame into the private frame_rec_array (stands in for retrieve(); untimed)
        frame_number += 1; time VideoRecorder.record_frame(frame_rec_array)   (video_recorder.py L87-109)
  finish_and_close() (timed)  -> then counts frames actually in the file by decoding it.

Modes:  paced60 = absolute 60 fps schedule for PACED_S seconds (late frames are written immediately,
        lateness = write-finish minus scheduled time);  unthrottled = as fast as possible for 10 s.
CPU% = process (user+system) CPU time / wall time, 100% = one logical CPU (includes encoder threads).

Synthetic content: bench_common.synthetic_frames (moving gradient + moving box + +-8 uniform noise).
Video files go to the scratch bench_tmp folder and are deleted after their sizes are recorded.

Run:  cd C:\\Users\\Dom\\GitHub\\freemocap\\skellycam && .venv\\Scripts\\python.exe research\\frame_ring_buffer\\baseline\\bench_c_record.py
"""
from __future__ import annotations

import multiprocessing as mp
import multiprocessing.queues  # noqa: F401  workaround: skellycam type_overloads.py L23 needs it before spawn-child unpickles a DTO (see README)
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402

PACED_S = 20.0
UNTHROTTLED_S = 10.0


def recorder_proc(cam_idx, h, w, mode, duration_s, rec_name, ready_q, start_evt, result_q):
    import cv2
    import psutil
    import bench_common as bc
    from skellycam.core.recorders.videos.recording_info import RecordingInfo
    from skellycam.core.recorders.videos.video_recorder import VideoRecorder
    cfg = bc.make_config(cam_idx, h, w, framerate=60.0)
    fr = bc.make_frame_recarray(cfg)
    frames = bc.synthetic_frames(h, w, n=60, seed=cam_idx)
    info = RecordingInfo(recording_name=rec_name, recording_directory=str(bc.SCRATCH_TMP))
    t0 = time.perf_counter()
    rec = VideoRecorder.create(recording_info=info, config=cfg, framerate=60.0)
    create_s = time.perf_counter() - t0
    backend = rec.video_writer.getBackendName() if isinstance(rec.video_writer, cv2.VideoWriter) else type(rec.video_writer).__name__
    ready_q.put(cam_idx)
    start_evt.wait()
    proc = psutil.Process()
    c0 = proc.cpu_times()
    pc = time.perf_counter_ns
    period = int(1e9 / 60)
    t_start = pc()
    deadline_end = t_start + int(duration_s * 1e9)
    lat, late = [], []
    k = 0
    while True:
        sched = t_start + k * period
        if mode == "paced60":
            if sched >= deadline_end:
                break
            while True:
                rem = sched - pc()
                if rem <= 0:
                    break
                if rem > 2_000_000:
                    time.sleep((rem - 1_500_000) / 1e9)
        elif pc() >= deadline_end:
            break
        np.copyto(fr.image[0], frames[k % 60])
        fr.frame_metadata.frame_number[0] += 1
        a = pc(); rec.record_frame(frame=fr); b = pc()
        lat.append(b - a)
        late.append(b - sched)
        k += 1
    elapsed = (pc() - t_start) / 1e9
    c1 = proc.cpu_times()
    cpu_pct_loop = 100 * ((c1.user - c0.user) + (c1.system - c0.system)) / elapsed
    a = time.perf_counter()
    rec.finish_and_close()
    release_s = time.perf_counter() - a
    c2 = proc.cpu_times()
    cpu_pct_incl_release = 100 * ((c2.user - c0.user) + (c2.system - c0.system)) / (elapsed + release_s)
    path = rec.video_file_path
    size_bytes = os.path.getsize(path)
    cap = cv2.VideoCapture(path)
    prop_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    decoded = 0
    while cap.grab():
        decoded += 1
    cap.release()
    result_q.put(dict(cam=cam_idx, frames_written=k, elapsed_s=elapsed, fps=k / elapsed,
                      record_frame=bc.stats_ms(lat),
                      lateness_vs_schedule=bc.stats_ms(late) if mode == "paced60" else None,
                      frames_over_16p7ms=int(sum(1 for x in lat if x > 16_666_667)),
                      cpu_pct_loop=cpu_pct_loop, cpu_pct_incl_release=cpu_pct_incl_release,
                      release_s=release_s, create_s=create_s, writer_fourcc=rec.writer_fourcc, writer_backend=backend,
                      file=path, file_bytes=size_bytes, file_frame_count_prop=prop_count, file_frames_decoded=decoded,
                      metadata_entries=len(rec.video_frame_metadata)))


def run(size_name, n, mode, duration_s, tag):
    import psutil
    import bench_common as bc
    h, w = bc.SIZES[size_name]
    ctx = mp.get_context("spawn")
    ready_q, result_q, start_evt = ctx.Queue(), ctx.Queue(), ctx.Event()
    rec_name = f"c_{tag}_{size_name}_{n}cam_{mode}_{int(time.time())}"
    procs = [ctx.Process(target=recorder_proc, args=(i, h, w, mode, duration_s, rec_name, ready_q, start_evt, result_q))
             for i in range(n)]
    for p in procs:
        p.start()
    for _ in procs:
        ready_q.get(timeout=180)
    psutil.cpu_percent(interval=None)
    start_evt.set()
    time.sleep(duration_s)
    sys_cpu = psutil.cpu_percent(interval=None)  # system-wide over the loop window
    res = sorted([result_q.get(timeout=600) for _ in procs], key=lambda r: r["cam"])
    for p in procs:
        p.join(60)
    for r in res:  # record size then delete
        try:
            os.remove(r["file"])
        except OSError as e:
            r["delete_error"] = str(e)
    return dict(size=size_name, n_cams=n, mode=mode, duration_s=duration_s, per_camera=res,
                system_cpu_pct_all_28_logical=sys_cpu,
                min_cam_fps=min(r["fps"] for r in res),
                sum_cpu_pct_loop=sum(r["cpu_pct_loop"] for r in res),
                total_file_bytes=sum(r["file_bytes"] for r in res),
                all_frames_on_disk=all(r["file_frames_decoded"] == r["frames_written"] for r in res))


def main():
    import bench_common as bc
    out = {"env": bc.env_summary(), "rows": []}
    lines = ["# (c) record path: real VideoRecorder.record_frame, one spawned process per camera", "",
             "| size | N | mode | min cam fps | record_frame median ms | worst p99 ms | worst max ms | max lateness ms | frames >16.7ms | sum proc CPU% (100=1 core) | system CPU% | writer | file frames == written | MB on disk |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    plan = []
    for size_name in ("720p", "1080p"):
        plan += [(size_name, 5, "paced60", PACED_S), (size_name, 5, "unthrottled", UNTHROTTLED_S),
                 (size_name, 1, "unthrottled", UNTHROTTLED_S)]
    for size_name, n, mode, dur in plan:
        r = run(size_name, n, mode, dur, "rec")
        out["rows"].append(r)
        bc.write_json("c_record.json", out)
        pcs = r["per_camera"]
        lat_max = max((p["lateness_vs_schedule"]["max_ms"] for p in pcs if p["lateness_vs_schedule"]), default=float("nan"))
        line = (f"| {size_name} | {n} | {mode} | {r['min_cam_fps']:.1f} | "
                f"{np.median([p['record_frame']['median_ms'] for p in pcs]):.2f} | "
                f"{max(p['record_frame']['p99_ms'] for p in pcs):.2f} | {max(p['record_frame']['max_ms'] for p in pcs):.2f} | "
                f"{lat_max:.2f} | {sum(p['frames_over_16p7ms'] for p in pcs)} | {r['sum_cpu_pct_loop']:.0f} | "
                f"{r['system_cpu_pct_all_28_logical']:.0f} | {pcs[0]['writer_fourcc']}/{pcs[0]['writer_backend']} | "
                f"{r['all_frames_on_disk']} | {r['total_file_bytes'] / 1e6:.1f} |")
        lines.append(line)
        print(line, flush=True)
    bc.write_text("c_record.md", "\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
