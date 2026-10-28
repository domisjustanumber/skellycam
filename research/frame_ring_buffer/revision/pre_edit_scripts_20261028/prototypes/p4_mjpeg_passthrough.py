"""P4 - MJPEG passthrough recording vs decode + re-encode, with the decoupled gated recorder from P3.

Simulated MJPEG camera: synthetic frames (baseline synthetic_frames, noise=8) pre-encoded with cv2.imencode q90
(30 distinct frames cycled) - the bytes a UVC camera would deliver. 5 spawned camera processes (FakeSensor 60 fps,
latest-frame-wins) + 5 spawned recorder processes, each recorder with its own gated cursor (block policy).

  passthrough : camera copies the JPEG bytes into a byte-slot SeqRing (slot = 1 MiB; 1 compressed copy);
                recorder wraps the slot VIEW in av.Packet (1 compressed copy, inside PyAV) and muxes it into .mkv
                with the sensor tick time as pts (ms). No decode, no encode.
  decode_msmf : camera cv2.imdecode -> np.copyto(BGR slot) (what a camera path must do to get pixels);
                recorder cv2.VideoWriter('X264') -> MSMF H.264 (SkellyCam's default writer on this machine) fed the view.
  passthrough_unthrottled : no sensor pacing; camera publishes as fast as the gated recorder allows (5 s) -> max mux rate.

Metrics: per-camera achieved fps, sensor frames never grabbed, frames recorded, frames decoded back from each file,
disk bytes/s, CPU% (psutil, per process, averaged over the run), CPU ms per frame, tick->written latency.

Run (from C:\\Users\\Dom\\GitHub\\freemocap\\skellycam): .venv\\Scripts\\python.exe benchmarks\\frame_pipeline\\prototypes\\p4_mjpeg_passthrough.py
"""
from __future__ import annotations

import multiprocessing as mp
import os
import sys
import threading
import time
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402

N_CAMS = 5
FPS = 60.0
RUN_S = float(os.environ.get("P4_RUN_S", "20"))
UNTHROTTLED_FRAMES = 1500  # per camera; caps temp disk use (~0.8 GB/camera at 1080p q90)


def camera(spec, cam, h, w, mode, run_s, ready_q, go, out_q):
    import cv2
    import proto_common as pcm
    cv2.setNumThreads(1)
    ring = pcm.SeqRing.attach(spec)
    frames = pcm.synthetic_frames(h, w, n=30, seed=cam, noise=8)
    jpegs = [cv2.imencode(".jpg", f, [int(cv2.IMWRITE_JPEG_QUALITY), 90])[1] for f in frames]
    ready_q.put(cam)
    go.wait()
    paced = not mode.endswith("unthrottled")
    sensor = pcm.FakeSensor(FPS, seed=cam)
    k = 0
    blocked = 0.0
    t_end = time.perf_counter_ns() + int(run_s * 1e9)
    cpu0 = time.process_time()
    t_start = time.perf_counter()
    work = []
    while time.perf_counter_ns() < t_end and (paced or k < UNTHROTTLED_FRAMES):
        if paced:
            tick, t_tick = sensor.grab()
        else:
            tick, t_tick = k, time.perf_counter_ns()
        if not ring.can_write(k, 1):
            b0 = time.perf_counter()
            while not ring.can_write(k, 1):
                time.sleep(0.0002)
            blocked += time.perf_counter() - b0
        t0 = time.perf_counter_ns()
        s = ring.begin(k)
        j = jpegs[tick % 30]
        if mode.startswith("passthrough"):
            n = j.size
            ring.bytes_view(s, n)[:] = j  # the one compressed copy into shm
        else:
            n = h * w * 3
            np.copyto(ring.image_view(s, (h, w, 3)), cv2.imdecode(j, cv2.IMREAD_COLOR))
        ring.commit(k, s, frame_number=k, tick_ns=t_tick, nbytes=n, aux0=tick)
        work.append(time.perf_counter_ns() - t0)
        k += 1
    el = time.perf_counter() - t_start
    cpu = time.process_time() - cpu0
    out_q.put(dict(cam=cam, produced=k, fps=k / el, sensor_skipped=sensor.skipped if paced else None, blocked_s=blocked,
                   work=pcm.stats_ms(work), cpu_ms_per_frame=1000 * cpu / max(k, 1), cpu_pct=100 * cpu / el))
    ring.close()


def recorder(spec, cam, h, w, mode, path, ready_q, go, stop, out_q):
    import cv2
    import av
    import proto_common as pcm
    ring = pcm.SeqRing.attach(spec)
    if mode.startswith("passthrough"):
        c = av.open(str(path), "w")
        st = c.add_stream("mjpeg", rate=60)
        st.width, st.height = w, h
        st.pix_fmt = "yuvj420p"
        tb = Fraction(1, 1000)
        vw = None
    else:
        vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"X264"), FPS, (w, h))
    ready_q.put(cam)
    go.wait()
    nxt = 0
    t_first = None
    fns = []
    lat = []
    wlat = []
    nbytes = 0
    cpu0 = time.process_time()
    t_start = time.perf_counter()
    while True:
        hd = ring.head
        if nxt > hd:
            if stop.is_set() and ring.head < nxt:
                break
            time.sleep(0.0003)
            continue
        sl = nxt % ring.L
        m = ring.meta[sl]
        t_tick = int(m[pcm.F_TICK])
        if t_first is None:
            t_first = t_tick
        t0 = time.perf_counter_ns()
        if vw is None:
            n = int(m[pcm.F_NBYTES])
            pkt = av.Packet(ring.bytes_view(sl, n))
            pkt.stream = st
            pkt.time_base = tb
            pkt.pts = pkt.dts = (t_tick - t_first) // 1_000_000
            c.mux(pkt)
            nbytes += n
        else:
            vw.write(ring.image_view(sl, (h, w, 3)))
        t1 = time.perf_counter_ns()
        fns.append(int(m[pcm.F_FN]))
        lat.append(t1 - t_tick)
        wlat.append(t1 - t0)
        ring.set_cursor(0, nxt)
        nxt += 1
    loop_s = time.perf_counter() - t_start
    r0 = time.perf_counter()
    if vw is None:
        c.close()
    else:
        vw.release()
    rel = time.perf_counter() - r0
    cpu = time.process_time() - cpu0
    out_q.put(dict(cam=cam, recorded=len(fns), consecutive=bool(len(fns) < 2 or np.all(np.diff(fns) == 1)),
                   tick_to_written=pcm.stats_ms(lat), write=pcm.stats_ms(wlat), release_s=rel, loop_s=loop_s,
                   cpu_ms_per_frame=1000 * cpu / max(len(fns), 1), cpu_pct=100 * cpu / (loop_s + rel),
                   compressed_bytes_muxed=nbytes))
    ring.close()


def run(size_name, mode, run_s):
    import proto_common as pcm
    h, w = pcm.SIZES[size_name]
    ctx = mp.get_context("spawn")
    if mode.startswith("passthrough"):
        L, slot = 1024, 1 << 20  # 1 GiB of 1 MiB slots = 17 s at 60 fps
    else:
        L, slot = (1024 ** 3) // (632 + h * w * 3), h * w * 3
    rings = [pcm.SeqRing.create(L, slot, prefault=True) for _ in range(N_CAMS)]
    ext = "mkv" if mode.startswith("passthrough") else "mp4"
    paths = [pcm.SCRATCH_TMP / f"p4_{size_name}_{mode}_cam{i}.{ext}" for i in range(N_CAMS)]
    ready_q, oc, orr = ctx.Queue(), ctx.Queue(), ctx.Queue()
    go, stop = ctx.Event(), ctx.Event()
    cams = [ctx.Process(target=camera, args=(rings[i].spec(), i, h, w, mode, run_s, ready_q, go, oc)) for i in range(N_CAMS)]
    recs = [ctx.Process(target=recorder, args=(rings[i].spec(), i, h, w, mode, paths[i], ready_q, go, stop, orr)) for i in range(N_CAMS)]
    for p in cams + recs:
        p.start()
    for _ in cams + recs:
        ready_q.get(timeout=300)
    samples = []
    cs = threading.Event()
    th = threading.Thread(target=pcm.cpu_sampler, args=([p.pid for p in cams + recs], cs, samples), daemon=True)
    th.start()
    t0 = time.perf_counter()
    go.set()
    cres = sorted([oc.get(timeout=run_s + 120) for _ in cams], key=lambda r: r["cam"])
    stop.set()
    rres = sorted([orr.get(timeout=300) for _ in recs], key=lambda r: r["cam"])
    wall = time.perf_counter() - t0
    cs.set()
    for p in cams + recs:
        p.join(30)
    for r in rings:
        r.close()
    cpu = pcm.summarize_cpu(samples)
    cam_pids = {str(p.pid) for p in cams}
    rec_pids = {str(p.pid) for p in recs}
    cpu_split = None
    if cpu:
        cpu_split = dict(cameras=sum(v for k, v in cpu.items() if k in cam_pids),
                         recorders=sum(v for k, v in cpu.items() if k in rec_pids), system=cpu["system"])
    files = []
    for i, p in enumerate(paths):
        files.append(dict(file=p.name, bytes=p.stat().st_size, decoded_frames=pcm.count_video_frames(p),
                          produced=cres[i]["produced"], recorded=rres[i]["recorded"]))
    for p in paths:
        p.unlink()
    total_bytes = sum(f["bytes"] for f in files)
    rec_s = max(c["produced"] for c in cres) / FPS if not mode.endswith("unthrottled") else max(r["loop_s"] + r["release_s"] for r in rres)
    return dict(size=size_name, mode=mode, run_s=run_s, ring_len=L, ring_slot_bytes=slot, ring_seconds=L / FPS,
                cameras=cres, recorders=rres, files=files, cpu_psutil_mean=cpu, cpu_split=cpu_split, wall_s=wall,
                min_cam_fps=min(c["fps"] for c in cres), sensor_skipped_total=sum((c["sensor_skipped"] or 0) for c in cres),
                files_equal_produced=all(f["decoded_frames"] == f["produced"] for f in files),
                disk_MBps_5cams=total_bytes / rec_s / 1e6, disk_bytes_total=total_bytes,
                cam_cpu_ms_per_frame=float(np.median([c["cpu_ms_per_frame"] for c in cres])),
                rec_cpu_ms_per_frame=float(np.median([r["cpu_ms_per_frame"] for r in rres])),
                recorder_fps_unthrottled=(sum(r["recorded"] / (r["loop_s"] + r["release_s"]) for r in rres)) if mode.endswith("unthrottled") else None)


def main():
    import proto_common as pcm
    out = dict(env=pcm.env_summary(), rows=[])
    for size_name in ("1080p", "720p"):
        for mode in ("passthrough", "decode_msmf", "passthrough_unthrottled"):
            r = run(size_name, mode, 5.0 if mode.endswith("unthrottled") else RUN_S)
            out["rows"].append(r)
            pcm.write_json("p4_mjpeg_passthrough.json", out)
            print(f"{size_name} {mode}: min fps {r['min_cam_fps']:.2f} skipped {r['sensor_skipped_total']} files==produced {r['files_equal_produced']} "
                  f"disk {r['disk_MBps_5cams']:.1f} MB/s cpu {r['cpu_split']} cam {r['cam_cpu_ms_per_frame']:.3f} rec {r['rec_cpu_ms_per_frame']:.3f} ms/f "
                  f"unthr {r['recorder_fps_unthrottled']}", flush=True)
    L = ["# P4 - MJPEG passthrough recording vs decode + MSMF H.264 re-encode (5 cameras, decoupled gated recorders)", "",
         f"Paced rows: 60 fps FakeSensor, {RUN_S}s. Unthrottled rows: 1500 frames per camera (or 5 s), camera publishes as fast as the gated recorder consumes. "
         "CPU %: psutil mean per process over the run, 100 = one logical CPU; ms/frame from process_time.", "",
         "| size | mode | per-cam fps (min) | sensor frames never grabbed | files decode == produced | disk MB/s (5 cams) | CPU % cameras / recorders (sum) | camera CPU ms/frame | recorder CPU ms/frame | tick->written median / p99 ms (worst cam) | recorder release s | full-frame copies | unthrottled recorder fps (sum over cams, recorded/(loop+release)) |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    copies = {"passthrough": "0 (2 compressed copies)", "passthrough_unthrottled": "0 (2 compressed copies)",
              "decode_msmf": "1 after decode (+ encoder-internal, unknown)"}
    for r in out["rows"]:
        tw = max(r["recorders"], key=lambda x: x["tick_to_written"]["p99_ms"])["tick_to_written"]
        cs = r["cpu_split"] or {}
        L.append(f"| {r['size']} | {r['mode']} | {r['min_cam_fps']:.2f} | {r['sensor_skipped_total']} | {r['files_equal_produced']} | "
                 f"{r['disk_MBps_5cams']:.1f} | {cs.get('cameras', float('nan')):.0f} / {cs.get('recorders', float('nan')):.0f} | "
                 f"{r['cam_cpu_ms_per_frame']:.3f} | {r['rec_cpu_ms_per_frame']:.3f} | {tw['median_ms']:.1f} / {tw['p99_ms']:.1f} | "
                 f"{max(x['release_s'] for x in r['recorders']):.2f} | {copies[r['mode']]} | "
                 f"{'' if r['recorder_fps_unthrottled'] is None else f'{r['recorder_fps_unthrottled']:.0f}'} |")
    L += ["", "Baseline (baseline/results/c_record.md, idle 20261027 re-run): real VideoRecorder, 5x1080p paced 60: summed process CPU 1207%; "
          "5x720p: 476%. Unthrottled cv2 X264->MSMF throughput (derived, c_record.json) about 117 fps/camera at 5x1080p."]
    pcm.write_text("p4_mjpeg_passthrough.md", "\n".join(L) + "\n")
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
