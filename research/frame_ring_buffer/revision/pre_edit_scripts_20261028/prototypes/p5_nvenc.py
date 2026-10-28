"""P5 - hardware encode (NVENC via PyAV 18 / FFmpeg) fed from shared memory vs the current software-path writer.

Part S - NVENC session limit: one process opens N concurrent PyAV encoders (h264_nvenc, then hevc_nvenc) at 1280x720,
each encoding one frame and staying open, N = 1..MAX_SESSIONS, until opening/encoding fails. nvidia-smi
encoder.stats.sessionCount is sampled while all are open.

Part E - 5 spawned camera processes (FakeSensor 60 fps; pixels = np.copyto(synthetic frame) into a BGR SeqRing slot,
i.e. the decode-free memcpy stand-in so only the encoder differs) + 5 spawned recorder processes (gated cursor,
block policy). Recorder encoders:
  msmf        : cv2.VideoWriter('X264') -> MSMF H.264 (SkellyCam's default on this machine), write(slot view)
  h264_nvenc  : cv2.cvtColor(slot view, BGR2YUV_I420, dst=preallocated) -> av.VideoFrame.from_ndarray(yuv420p)
                -> h264_nvenc (preset p4, tune ll, rc vbr, cq 23) -> mp4
  hevc_nvenc  : same, hevc_nvenc cq 25
  pyav_libx264: SkellyCam's REAL PyavVideoWriter (writer_fourcc 'X264_PYAV'; libx264 crf 18 preset fast, CPU), write(slot view)
                (added 2026-10-28)
Paced: 60 fps, RUN_S s, 1080p and 720p. Unthrottled: 900 frames per camera as fast as the gated chain allows.
Full-frame-equivalent copies on the NVENC path: BGR->I420 conversion (writes 1.5 B/px), from_ndarray copy of the I420
buffer (1.5 B/px), then the host->GPU upload inside NVENC (not measurable here).

Run (from C:\\Users\\Dom\\GitHub\\freemocap\\skellycam): .venv\\Scripts\\python.exe benchmarks\\frame_pipeline\\prototypes\\p5_nvenc.py
"""
from __future__ import annotations

import multiprocessing as mp
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402

N_CAMS = 5
FPS = 60.0
RUN_S = float(os.environ.get("P5_RUN_S", "20"))
UNTHROTTLED_FRAMES = 900
MAX_SESSIONS = 20
NVENC_OPTS = {"h264_nvenc": {"preset": "p4", "tune": "ll", "rc": "vbr", "cq": "23"},
              "hevc_nvenc": {"preset": "p4", "tune": "ll", "rc": "vbr", "cq": "25"}}


def nvsmi_sessions():
    try:
        o = subprocess.check_output(["nvidia-smi", "--query-gpu=encoder.stats.sessionCount", "--format=csv,noheader"], text=True)
        return int(o.strip().splitlines()[0])
    except Exception as e:
        return repr(e)


def session_probe(codec):
    import av
    h, w = 720, 1280
    img = np.zeros((h * 3 // 2, w), np.uint8)
    open_ = []
    err = None
    for n in range(1, MAX_SESSIONS + 1):
        try:
            cc = av.CodecContext.create(codec, "w")
            cc.width, cc.height, cc.pix_fmt = w, h, "yuv420p"
            from fractions import Fraction
            cc.time_base = Fraction(1, 60)
            cc.options = NVENC_OPTS[codec]
            cc.open()
            f = av.VideoFrame.from_ndarray(img, format="yuv420p"); f.pts = 0
            cc.encode(f)
            open_.append(cc)
        except Exception as e:
            err = f"session {n}: {e!r}"
            break
    smi = nvsmi_sessions()
    ok = len(open_)
    for cc in open_:
        try:
            cc.encode(None)
        except Exception:
            pass
        try:
            cc.close()
        except Exception:
            pass
    del open_
    return dict(codec=codec, max_concurrent_opened=ok, first_error=err, nvidia_smi_session_count_while_open=smi,
                probe_limit=MAX_SESSIONS)


def camera(spec, cam, h, w, paced, run_s, ready_q, go, out_q):
    import proto_common as pcm
    ring = pcm.SeqRing.attach(spec)
    frames = pcm.synthetic_frames(h, w, n=30, seed=cam, noise=8)
    ready_q.put(cam)
    go.wait()
    sensor = pcm.FakeSensor(FPS, seed=cam)
    k = 0
    t_end = time.perf_counter_ns() + int(run_s * 1e9)
    t_start = time.perf_counter()
    blocked = 0.0
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
        s = ring.begin(k)
        np.copyto(ring.image_view(s, (h, w, 3)), frames[tick % 30])
        ring.commit(k, s, frame_number=k, tick_ns=t_tick, aux0=tick)
        k += 1
    el = time.perf_counter() - t_start
    out_q.put(dict(cam=cam, produced=k, fps=k / el, sensor_skipped=sensor.skipped if paced else None, blocked_s=blocked))
    ring.close()


def recorder(spec, cam, h, w, enc, path, ready_q, go, stop, out_q):
    import cv2
    import av
    import proto_common as pcm
    cv2.setNumThreads(2)
    ring = pcm.SeqRing.attach(spec)
    vw = c = st = None
    if enc == "pyav_libx264":
        # SkellyCam's own PyAV writer (pyav_video_writer.py L3-39 @23ccbf20: libx264 crf 18 preset fast, bgr24 from_ndarray),
        # used when writer_fourcc == 'X264_PYAV'. Same write()/release() interface as cv2.VideoWriter.
        from skellycam.core.recorders.videos.pyav_video_writer import PyavVideoWriter
        vw = PyavVideoWriter(str(path), FPS, w, h)
        backend = "skellycam PyavVideoWriter (libx264)"
    elif enc == "msmf":
        vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"X264"), FPS, (w, h))
        backend = vw.getBackendName()
    else:
        c = av.open(str(path), "w")
        st = c.add_stream(enc, rate=60)
        st.width, st.height, st.pix_fmt = w, h, "yuv420p"
        st.options = NVENC_OPTS[enc]
        backend = enc
        i420 = np.empty((h * 3 // 2, w), np.uint8)
    ready_q.put(cam)
    go.wait()
    nxt = 0
    fns, lat, wlat, conv = [], [], [], []
    cpu0 = time.process_time()
    t_start = time.perf_counter()
    while True:
        if nxt > ring.head:
            if stop.is_set() and ring.head < nxt:
                break
            time.sleep(0.0003)
            continue
        sl = nxt % ring.L
        view = ring.image_view(sl, (h, w, 3))
        t0 = time.perf_counter_ns()
        if vw is not None:
            vw.write(view)
            t_c = t0
        else:
            cv2.cvtColor(view, cv2.COLOR_BGR2YUV_I420, dst=i420)
            t_c = time.perf_counter_ns()
            f = av.VideoFrame.from_ndarray(i420, format="yuv420p")
            f.pts = nxt
            for pk in st.encode(f):
                c.mux(pk)
        t1 = time.perf_counter_ns()
        fns.append(int(ring.meta[sl, pcm.F_FN]))
        lat.append(t1 - int(ring.meta[sl, pcm.F_TICK]))
        wlat.append(t1 - t0)
        conv.append(t_c - t0)
        ring.set_cursor(0, nxt)  # slot released only after the encoder call has consumed it
        nxt += 1
    loop_s = time.perf_counter() - t_start
    r0 = time.perf_counter()
    if vw is not None:
        vw.release()
    else:
        for pk in st.encode():
            c.mux(pk)
        c.close()
    rel = time.perf_counter() - r0
    cpu = time.process_time() - cpu0
    out_q.put(dict(cam=cam, backend=backend, recorded=len(fns), consecutive=bool(len(fns) < 2 or np.all(np.diff(fns) == 1)),
                   tick_to_written=pcm.stats_ms(lat), write=pcm.stats_ms(wlat), convert=pcm.stats_ms(conv),
                   loop_s=loop_s, release_s=rel, cpu_ms_per_frame=1000 * cpu / max(1, len(fns))))
    ring.close()


def run(size_name, enc, paced, run_s):
    import proto_common as pcm
    h, w = pcm.SIZES[size_name]
    ctx = mp.get_context("spawn")
    L = (1024 ** 3) // (632 + h * w * 3)
    rings = [pcm.SeqRing.create(L, h * w * 3, prefault=True) for _ in range(N_CAMS)]
    paths = [pcm.SCRATCH_TMP / f"p5_{size_name}_{enc}_{'paced' if paced else 'unthr'}_cam{i}.mp4" for i in range(N_CAMS)]
    ready_q, oc, orr = ctx.Queue(), ctx.Queue(), ctx.Queue()
    go, stop = ctx.Event(), ctx.Event()
    cams = [ctx.Process(target=camera, args=(rings[i].spec(), i, h, w, paced, run_s, ready_q, go, oc)) for i in range(N_CAMS)]
    recs = [ctx.Process(target=recorder, args=(rings[i].spec(), i, h, w, enc, paths[i], ready_q, go, stop, orr)) for i in range(N_CAMS)]
    for p in cams + recs:
        p.start()
    for _ in cams + recs:
        ready_q.get(timeout=300)
    samples = []
    cs = threading.Event()
    th = threading.Thread(target=pcm.cpu_sampler, args=([p.pid for p in cams + recs], cs, samples), daemon=True)
    th.start()
    smi = []

    def smi_poll():
        while not cs.wait(2.0):
            smi.append(nvsmi_sessions())
    th2 = threading.Thread(target=smi_poll, daemon=True)
    th2.start()
    go.set()
    cres = sorted([oc.get(timeout=run_s + 300) for _ in cams], key=lambda r: r["cam"])
    stop.set()
    rres = sorted([orr.get(timeout=300) for _ in recs], key=lambda r: r["cam"])
    cs.set()
    for p in cams + recs:
        p.join(30)
    for r in rings:
        r.close()
    cpu = pcm.summarize_cpu(samples)
    rec_pids = {str(p.pid) for p in recs}
    cam_pids = {str(p.pid) for p in cams}
    cpu_split = dict(cameras=sum(v for k, v in cpu.items() if k in cam_pids), recorders=sum(v for k, v in cpu.items() if k in rec_pids),
                     system=cpu["system"]) if cpu else None
    files = []
    for i, p in enumerate(paths):
        files.append(dict(file=p.name, bytes=p.stat().st_size, decoded_frames=pcm.count_video_frames(p), produced=cres[i]["produced"]))
        p.unlink()
    dur = max(c["produced"] for c in cres) / FPS
    return dict(size=size_name, encoder=enc, paced=paced, run_s=run_s, cameras=cres, recorders=rres, files=files,
                cpu_psutil_mean=cpu, cpu_split=cpu_split, nvidia_smi_sessions_samples=smi,
                min_cam_fps=min(c["fps"] for c in cres), sensor_skipped_total=sum((c["sensor_skipped"] or 0) for c in cres),
                files_equal_produced=all(f["decoded_frames"] == f["produced"] for f in files),
                mbit_per_s_per_cam=float(np.median([f["bytes"] * 8 / dur / 1e6 for f in files])),
                rec_cpu_ms_per_frame=float(np.median([r["cpu_ms_per_frame"] for r in rres])),
                recorder_fps_sum=sum(r["recorded"] / (r["loop_s"] + r["release_s"]) for r in rres),
                slowest_recorder_fps=min(r["recorded"] / (r["loop_s"] + r["release_s"]) for r in rres))


def main():
    import proto_common as pcm
    out = dict(env=pcm.env_summary(), nvidia_smi_idle_sessions=nvsmi_sessions(), sessions=[], rows=[])
    for codec in ("h264_nvenc", "hevc_nvenc"):
        r = session_probe(codec)
        out["sessions"].append(r)
        print("SESSIONS", r, flush=True)
    pcm.write_json("p5_nvenc.json", out)
    for size_name in ("1080p", "720p"):
        for enc in ("msmf", "h264_nvenc", "hevc_nvenc", "pyav_libx264"):
            for paced in (True, False):
                r = run(size_name, enc, paced, RUN_S if paced else 60.0)
                out["rows"].append(r)
                pcm.write_json("p5_nvenc.json", out)
                print(f"{size_name} {enc} paced={paced}: min fps {r['min_cam_fps']:.1f} skipped {r['sensor_skipped_total']} "
                      f"files==produced {r['files_equal_produced']} {r['mbit_per_s_per_cam']:.1f} Mbit/s cpu {r['cpu_split']} "
                      f"rec {r['rec_cpu_ms_per_frame']:.2f} ms/f recfps sum {r['recorder_fps_sum']:.0f} slowest {r['slowest_recorder_fps']:.0f} smi {r['nvidia_smi_sessions_samples'][:3]}",
                      flush=True)
    L = ["# P5 - NVENC (PyAV h264_nvenc / hevc_nvenc) vs cv2 'X264' (MSMF) as the decoupled recorder, fed from shm", "",
         "## Session limit (one process, concurrent open encoders, 1280x720)", "",
         "| codec | max concurrent sessions opened (probe limit) | first error | nvidia-smi sessionCount while open |", "|---|---|---|---|"]
    for s in out["sessions"]:
        L.append(f"| {s['codec']} | {s['max_concurrent_opened']} ({s['probe_limit']}) | {s['first_error']} | {s['nvidia_smi_session_count_while_open']} |")
    L += ["", f"## 5 cameras x 60 fps (paced, {RUN_S}s) and unthrottled ({UNTHROTTLED_FRAMES} frames/camera); memcpy-into-slot cameras", "",
          "CPU % = psutil mean per process (100 = 1 logical CPU). Recorder fps = recorded / (loop + release).", "",
          "| size | encoder | paced | per-cam fps (min) | sensor frames never grabbed | files decode == produced | Mbit/s per cam | CPU % cameras / recorders | recorder CPU ms/frame | encode call median / p99 ms (worst cam) | BGR->I420 median ms | tick->written median / p99 ms | recorder fps sum / slowest | release s (max) |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in out["rows"]:
        wr = max(r["recorders"], key=lambda x: x["write"]["p99_ms"])
        tw = max(r["recorders"], key=lambda x: x["tick_to_written"]["p99_ms"])["tick_to_written"]
        cs = r["cpu_split"] or {}
        L.append(f"| {r['size']} | {r['encoder']} | {r['paced']} | {r['min_cam_fps']:.1f} | {r['sensor_skipped_total']} | {r['files_equal_produced']} | "
                 f"{r['mbit_per_s_per_cam']:.1f} | {cs.get('cameras', float('nan')):.0f} / {cs.get('recorders', float('nan')):.0f} | {r['rec_cpu_ms_per_frame']:.2f} | "
                 f"{wr['write']['median_ms']:.2f} / {wr['write']['p99_ms']:.2f} | {float(np.median([x['convert']['median_ms'] for x in r['recorders']])):.2f} | "
                 f"{tw['median_ms']:.1f} / {tw['p99_ms']:.1f} | {r['recorder_fps_sum']:.0f} / {r['slowest_recorder_fps']:.0f} | {max(x['release_s'] for x in r['recorders']):.2f} |")
    L += ["", "Baseline (baseline/results/c_record.md, idle 20261027 re-run): VideoRecorder (MSMF), 5x1080p paced 60: 1207% summed CPU, "
          "record_frame median / p99 2.17 / 4.05 ms; 5x720p 476%; derived unthrottled encode throughput about 117 fps/camera at 1080p, 237 at 720p."]
    pcm.write_text("p5_nvenc.md", "\n".join(L) + "\n")
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
