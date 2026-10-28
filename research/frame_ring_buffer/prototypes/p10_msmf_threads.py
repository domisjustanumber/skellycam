"""P10 - does OpenCV's worker-thread count change the CPU cost of SkellyCam's real recorder (cv2 'X264' -> MSMF)?

Why: in this stage the same cv2.VideoWriter('X264') -> MSMF writer used 283% summed recorder CPU at 5x1080p60 in
p5_nvenc.py (recorder process calls cv2.setNumThreads(2)) but 939% in p4_mjpeg_passthrough.py and 1207% in the baseline
bench_c_record.py (both leave OpenCV's default, 28 threads on this machine). SkellyCam never calls cv2.setNumThreads
(grep of skellycam/ at 23ccbf20: no match).

Same harness as baseline/bench_c_record.py (REAL SkellyCam VideoRecorder.create + record_frame, video_recorder.py L87-109;
5 spawned processes; synthetic frames copied into the private frame_rec_array, untimed; absolute 60 fps schedule),
plus ONE line per process before the recorder is created: cv2.setNumThreads(N) (N = 'default' means no call).
Rows: 1080p paced 20 s for N in default,1,2,4,8; 720p paced for default,1,2; 1080p unthrottled 10 s for default,2
(encode throughput = frames / (loop + release)). Each recording is decoded and its frames counted, then deleted.

REVISION stage (2026-10-28) additions, env-gated (defaults unchanged): P10_PLAN=revision runs 1080p unthrottled for
threads default,1,2 and 1080p paced60_load for threads default,1,2, where paced60_load = paced60 while 5 extra spawned
processes each cv2.imdecode a 1080p q90 JPEG at 60 fps (the camera-side decode load of a 5x1080p60 capture);
P10_OUT names the output files (default p10_msmf_threads).

Run (from C:\\Users\\Dom\\GitHub\\freemocap\\skellycam): .venv\\Scripts\\python.exe research\\frame_ring_buffer\\prototypes\\p10_msmf_threads.py
"""
from __future__ import annotations

import multiprocessing as mp
import multiprocessing.queues  # noqa: F401  (skellycam type_overloads.py L23 workaround)
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402

N_CAMS = 5


def recorder_proc(cam, h, w, threads, mode, duration_s, rec_dir, ready_q, start_evt, result_q):
    import cv2
    import psutil
    import proto_common as pcm
    import bench_common as bc
    if threads != "default":
        cv2.setNumThreads(int(threads))
    from skellycam.core.recorders.videos.recording_info import RecordingInfo
    from skellycam.core.recorders.videos.video_recorder import VideoRecorder
    cfg = bc.make_config(cam, h, w, framerate=60.0)
    fr = bc.make_frame_recarray(cfg)
    frames = pcm.synthetic_frames(h, w, n=60, seed=cam)
    info = RecordingInfo(recording_name=f"p10_{h}_{threads}_{mode}", recording_directory=str(rec_dir))
    rec = VideoRecorder.create(recording_info=info, config=cfg, framerate=60.0)
    backend = rec.video_writer.getBackendName() if isinstance(rec.video_writer, cv2.VideoWriter) else type(rec.video_writer).__name__
    ready_q.put(cam)
    start_evt.wait()
    proc = psutil.Process()
    c0 = proc.cpu_times()
    pc = time.perf_counter_ns
    period = int(1e9 / 60)
    t_start = pc()
    end = t_start + int(duration_s * 1e9)
    lat, late = [], []
    k = 0
    while True:
        sched = t_start + k * period
        if mode == "paced60":
            if sched >= end:
                break
            pcm.sleep_until(sched)
        elif pc() >= end:
            break
        np.copyto(fr.image[0], frames[k % 60])
        fr.frame_metadata.frame_number[0] += 1
        a = pc()
        rec.record_frame(frame=fr)
        b = pc()
        lat.append(b - a)
        late.append(b - sched)
        k += 1
    loop_s = (pc() - t_start) / 1e9
    r0 = time.perf_counter()
    rec.finish_and_close()
    rel_s = time.perf_counter() - r0
    c1 = proc.cpu_times()
    cpu_s = (c1.user - c0.user) + (c1.system - c0.system)
    path = rec.video_file_path
    result_q.put(dict(cam=cam, backend=backend, threads_requested=threads, cv2_get_num_threads=cv2.getNumThreads(), frames=k,
                      loop_s=loop_s, release_s=rel_s, fps_written=k / loop_s, encode_fps=k / (loop_s + rel_s),
                      cpu_pct=100 * cpu_s / (loop_s + rel_s), cpu_ms_per_frame=1000 * cpu_s / k,
                      record_frame=pcm.stats_ms(lat), late_over_16_7ms=int(sum(1 for x in late if x > period)),
                      video_path=str(path)))


def decode_load_proc(cam, h, w, stop_evt, ready_q, out_q):
    import cv2
    import proto_common as pcm
    f = pcm.synthetic_frames(h, w, n=1, seed=cam)[0]
    jpg = cv2.imencode(".jpg", f, [int(cv2.IMWRITE_JPEG_QUALITY), 90])[1]
    ready_q.put(cam)
    period = int(1e9 / 60)
    t0 = time.perf_counter_ns()
    k = 0
    late = 0
    while not stop_evt.is_set():
        pcm.sleep_until(t0 + k * period)
        cv2.imdecode(jpg, cv2.IMREAD_COLOR)
        if time.perf_counter_ns() - (t0 + k * period) > period:
            late += 1
        k += 1
    out_q.put(dict(cam=cam, decoded=k, late=late))


def run(size_name, threads, mode, duration_s):
    import proto_common as pcm
    h, w = pcm.SIZES[size_name]
    rec_dir = pcm.SCRATCH_TMP / f"p10_{size_name}_{threads}_{mode}"
    rec_dir.mkdir(parents=True, exist_ok=True)
    ctx = mp.get_context("spawn")
    rq, resq, ev = ctx.Queue(), ctx.Queue(), ctx.Event()
    rec_mode = "paced60" if mode == "paced60_load" else mode
    ps = [ctx.Process(target=recorder_proc, args=(i, h, w, threads, rec_mode, duration_s, rec_dir, rq, ev, resq)) for i in range(N_CAMS)]
    lstop, lq = ctx.Event(), ctx.Queue()
    lps = [ctx.Process(target=decode_load_proc, args=(i, h, w, lstop, rq, lq)) for i in range(N_CAMS)] if mode == "paced60_load" else []
    for p in ps + lps:
        p.start()
    for _ in ps + lps:
        rq.get(timeout=300)
    ev.set()
    res = sorted([resq.get(timeout=duration_s + 300) for _ in ps], key=lambda r: r["cam"])
    lstop.set()
    load_res = [lq.get(timeout=60) for _ in lps]
    for p in ps + lps:
        p.join(30)
    for r in res:
        vp = Path(r["video_path"])
        r["file_bytes"] = vp.stat().st_size if vp.exists() else None
        r["file_frames"] = pcm.count_video_frames(vp) if vp.exists() else None
    shutil.rmtree(rec_dir, ignore_errors=True)
    return dict(size=size_name, threads=threads, mode=mode, duration_s=duration_s, per_camera=res, decode_load=load_res,
                cpu_pct_sum=sum(r["cpu_pct"] for r in res), cpu_ms_per_frame_median=float(np.median([r["cpu_ms_per_frame"] for r in res])),
                min_fps_written=min(r["fps_written"] for r in res), encode_fps_slowest=min(r["encode_fps"] for r in res),
                record_frame_median_ms=float(np.median([r["record_frame"]["median_ms"] for r in res])),
                record_frame_worst_p99_ms=max(r["record_frame"]["p99_ms"] for r in res),
                late_over_16_7ms_total=sum(r["late_over_16_7ms"] for r in res),
                files_equal_frames=all(r["file_frames"] == r["frames"] for r in res),
                release_s_max=max(r["release_s"] for r in res), mbit_per_s_per_cam=float(np.median(
                    [r["file_bytes"] * 8 / (r["frames"] / 60) / 1e6 for r in res if r["file_bytes"]])))


def main():
    import cv2
    import proto_common as pcm
    pf = [ln.strip() for ln in cv2.getBuildInformation().splitlines() if "Parallel framework" in ln]
    out = dict(env=pcm.env_summary(), cv2_parallel_framework=pf, cv2_default_threads=cv2.getNumThreads(), rows=[])
    plan = [("1080p", t, "paced60", 20.0) for t in ("default", "1", "2", "4", "8")] + \
           [("720p", t, "paced60", 20.0) for t in ("default", "1", "2")] + \
           [("1080p", t, "unthrottled", 10.0) for t in ("default", "2")]
    if os.environ.get("P10_PLAN") == "revision":
        plan = [("1080p", t, "unthrottled", 10.0) for t in ("default", "1", "2")] +                [("1080p", t, "paced60_load", 20.0) for t in ("default", "1", "2")]
    OUT = os.environ.get("P10_OUT", "p10_msmf_threads")
    for size_name, t, mode, d in plan:
        r = run(size_name, t, mode, d)
        out["rows"].append(r)
        pcm.write_json(f"{OUT}.json", out)
        print(f"{size_name} threads={t} {mode}: cpu sum {r['cpu_pct_sum']:.0f}% ({r['cpu_ms_per_frame_median']:.2f} ms/f), min fps {r['min_fps_written']:.1f}, "
              f"encode fps slowest {r['encode_fps_slowest']:.1f}, record_frame {r['record_frame_median_ms']:.2f}/{r['record_frame_worst_p99_ms']:.2f} ms, "
              f"late {r['late_over_16_7ms_total']}, files ok {r['files_equal_frames']}, {r['mbit_per_s_per_cam']:.1f} Mbit/s", flush=True)
    L = ["# P10 - cv2.setNumThreads vs CPU of SkellyCam's real VideoRecorder (cv2 'X264' -> MSMF), 5 spawned processes", "",
         f"OpenCV parallel framework: {pf}; default cv2.getNumThreads() = {out['cv2_default_threads']}. CPU % = process CPU time / (loop + release), "
         "summed over 5 processes, 100 = one logical CPU. encode fps = frames / (loop + release) (slowest camera).", "",
         "| size | cv2 threads | mode | CPU % sum (5 cams) | CPU ms/frame | min fps written | encode fps (slowest) | record_frame median / worst p99 ms | writes late > 16.7 ms | files decode == written | Mbit/s per cam | release s (max) |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in out["rows"]:
        L.append(f"| {r['size']} | {r['threads']} | {r['mode']} | {r['cpu_pct_sum']:.0f} | {r['cpu_ms_per_frame_median']:.2f} | {r['min_fps_written']:.1f} | "
                 f"{r['encode_fps_slowest']:.1f} | {r['record_frame_median_ms']:.2f} / {r['record_frame_worst_p99_ms']:.2f} | {r['late_over_16_7ms_total']} | "
                 f"{r['files_equal_frames']} | {r['mbit_per_s_per_cam']:.1f} | {r['release_s_max']:.2f} |")
    L += ["", "Baseline (baseline/results/c_record.md, same harness without setNumThreads): 5x1080p paced 1207% CPU, 5x720p 476%."]
    pcm.write_text(f"{OUT}.md", "\n".join(L) + "\n")
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
