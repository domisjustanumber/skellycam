"""Python twin of build/codecbench.exe: decode / encode / record with cv2, same inputs, frame counts and topology.

  python py_codec.py buildinfo <out.txt>
  python py_codec.py decode <720p|1080p> <nprocs> <run_s> <inputs_dir> <out.json>
  python py_codec.py imencode <720p|1080p> <run_s> <inputs_dir> <out.json>
  python py_codec.py videowriter <720p|1080p> <nprocs> <paced_fps|0> <nframes> <threads|-1> <inputs_dir> <tmp_dir> <out.json>

Run with the SkellyCam venv (cv2 4.12.0) and with the throw-away venv holding opencv-python 4.8.0.76 (the same OpenCV
version as the C++ SDK) to separate a language effect from a library-version effect.
decode: spawned processes, cv2.setNumThreads(1), 30 q90 JPEGs per camera (make_inputs.py), 2 s warm-up, run_s unthrottled;
        img = cv2.imdecode(buf, IMREAD_COLOR) then np.copyto into a slot of a private 1 GiB shared_memory ring (4 KiB
        slots, prefaulted) = prototypes P1 row p_imdecode_copyslot. (cv2 4.12 Python imdecode has no dst argument.)
imencode: 1 process, setNumThreads(1): full-frame q90; and resize 0.5 INTER_LINEAR + imencode q60 (the SkellyCam UI step,
        frontend_payload_bytearray.py L136-147, quality from L34).
videowriter: cv2.VideoWriter(path.mp4, cv2.VideoWriter.fourcc(*"X264"), 60.0, (w, h)) - the exact call of
        video_recorder.py L125-130 - per process; threads >= 0 calls cv2.setNumThreads(threads) first; 60 distinct raw
        frames per camera; paced (proto sleep_until) or unthrottled; times write() and release(); counts file frames.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import sys
import time
from multiprocessing import shared_memory
from pathlib import Path

import numpy as np

pc = time.perf_counter_ns
META = 632


def round4k(n):
    return (n + 4095) // 4096 * 4096


def size_of(s):
    return (720, 1280) if s == "720p" else (1080, 1920)


def stats_ms(a):
    a = np.asarray(a, np.float64) / 1e6
    return {"n": int(a.size), "median_ms": float(np.median(a)), "mean_ms": float(a.mean()), "p99_ms": float(np.percentile(a, 99)),
            "min_ms": float(a.min()), "max_ms": float(a.max())}


def sleep_until(t_ns):
    while True:
        rem = t_ns - pc()
        if rem <= 0:
            return
        if rem > 2_000_000:
            time.sleep((rem - 1_500_000) / 1e9)


def decode_child(cam, size, run_s, d, ready_q, start_evt, res_q):
    import cv2
    cv2.setNumThreads(1)
    h, w = size_of(size)
    jpegs = [np.fromfile(os.path.join(d, f"{size}_seed{cam}_{i}.jpg"), np.uint8) for i in range(30)]
    n = h * w * 3
    stride = round4k(n + META)
    L = (1 << 30) // stride
    shm = shared_memory.SharedMemory(create=True, size=L * stride)
    ring = np.ndarray((L, stride), np.uint8, shm.buf)
    ring[:] = 0
    imgs = ring[:, META:META + n]
    k = [0]

    def one():
        kk = k[0]
        img = cv2.imdecode(jpegs[kk % 30], cv2.IMREAD_COLOR)
        np.copyto(imgs[kk % L], img.reshape(-1))
        k[0] = kk + 1
    t_end = pc() + 2_000_000_000
    while pc() < t_end:
        one()
    ready_q.put(cam)
    start_evt.wait()
    lat = []
    cpu0 = time.process_time()
    t0 = pc()
    dl = t0 + int(run_s * 1e9)
    cnt = 0
    while pc() < dl:
        a = pc(); one(); lat.append(pc() - a); cnt += 1
    el = (pc() - t0) / 1e9
    cpu = time.process_time() - cpu0
    last = k[0] - 1
    ref = cv2.imdecode(jpegs[last % 30], cv2.IMREAD_COLOR).reshape(-1)
    content_ok = int(np.array_equal(ref, imgs[last % L]))
    res_q.put(dict(cam=cam, n=cnt, elapsed_s=el, fps=cnt / el, cpu_ms_per_frame=1e3 * cpu / cnt, inplace_ok=0, content_ok=content_ok,
                   mean_jpeg_kb=float(np.mean([j.size for j in jpegs]) / 1024), lat=stats_ms(lat)))
    del imgs, ring
    shm.close(); shm.unlink()


def vw_child(cam, size, paced, nframes, threads, d, tmp, ready_q, start_evt, start_ns, res_q):
    import cv2
    if threads >= 0:
        cv2.setNumThreads(threads)
    h, w = size_of(size)
    raw = np.fromfile(os.path.join(d, f"{size}_seed{cam}.raw"), np.uint8).reshape(-1, h, w, 3)
    nf = raw.shape[0]
    path = os.path.join(tmp, f"py_vw_{size}_cam{cam}_{os.getpid()}.mp4")
    c0 = pc()
    vw = cv2.VideoWriter(path, cv2.VideoWriter.fourcc(*"X264"), 60.0, (w, h))
    create_s = (pc() - c0) / 1e9
    backend = vw.getBackendName() if vw.isOpened() else "NOT_OPENED"
    ready_q.put(cam)
    start_evt.wait()
    t_start = start_ns.value
    period = int(1e9 / paced) if paced > 0 else 0
    lat = []
    late = 0
    cpu0 = time.process_time()
    t0 = pc()
    for i in range(nframes):
        if period:
            sleep_until(t_start + (i + 1) * period)
        f = raw[i % nf]
        a = pc(); vw.write(f); dd = pc() - a
        lat.append(dd)
        if dd > 16_667_000:
            late += 1
    loop_end = pc()
    vw.release()
    rel_end = pc()
    cpu = time.process_time() - cpu0
    loop_s, release_s = (loop_end - t0) / 1e9, (rel_end - loop_end) / 1e9
    cap = cv2.VideoCapture(path)
    counted = 0
    while cap.grab():
        counted += 1
    cap.release()
    res_q.put(dict(cam=cam, backend=backend, create_s=create_s, n=nframes, loop_s=loop_s, release_s=release_s,
                   write_return_fps=nframes / loop_s, encode_fps_incl_release=nframes / (loop_s + release_s), cpu_s=cpu,
                   cpu_pct=100 * cpu / (loop_s + release_s), late_writes=late, frames_in_file=counted, file_bytes=os.path.getsize(path),
                   path=path.replace("\\", "/"), lat=stats_ms(lat)))


def imencode_main(size, run_s, d, out):
    import cv2
    cv2.setNumThreads(1)
    h, w = size_of(size)
    raw = np.fromfile(os.path.join(d, f"{size}_seed0.raw"), np.uint8).reshape(-1, h, w, 3)[:30]
    rows = []
    for variant in ("imencode_q90_full", "ui_resize05_linear_imencode_q60"):
        k = [0]
        nbytes = [0]

        def one():
            f = raw[k[0] % 30]
            if variant == "imencode_q90_full":
                _, enc = cv2.imencode(".jpg", f, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
            else:
                small = cv2.resize(src=f, dsize=(w // 2, h // 2), interpolation=cv2.INTER_LINEAR)
                _, enc = cv2.imencode(ext=".jpg", img=small, params=[int(cv2.IMWRITE_JPEG_QUALITY), 60])
            nbytes[0] += enc.size
            k[0] += 1
        te = pc() + 2_000_000_000
        while pc() < te:
            one()
        k0 = k[0]
        nbytes[0] = 0
        lat = []
        cpu0 = time.process_time()
        t0 = pc()
        dl = t0 + int(run_s * 1e9)
        while pc() < dl:
            a = pc(); one(); lat.append(pc() - a)
        el = (pc() - t0) / 1e9
        cpu = time.process_time() - cpu0
        cnt = k[0] - k0
        rows.append(dict(variant=variant, n=cnt, fps=cnt / el, cpu_ms_per_frame=1e3 * cpu / cnt, mean_kb=nbytes[0] / cnt / 1024, lat=stats_ms(lat)))
    res = dict(tool="py_codec", mode="imencode", lang="python", opencv=cv2.__version__, numpy=np.__version__, size=size, rows=rows)
    Path(out).write_text(json.dumps(res))
    print(json.dumps(res))


def multi(target, args_fn, nprocs, header, out):
    ctx = mp.get_context("spawn")
    ready_q, res_q, start_evt = ctx.Queue(), ctx.Queue(), ctx.Event()
    start_ns = ctx.Value("q", 0, lock=False)
    ps = [ctx.Process(target=target, args=args_fn(c, ready_q, start_evt, start_ns, res_q)) for c in range(nprocs)]
    for p in ps:
        p.start()
    for _ in ps:
        ready_q.get(timeout=600)
    start_ns.value = pc() + 1_000_000
    start_evt.set()
    procs = sorted([res_q.get(timeout=900) for _ in ps], key=lambda r: r["cam"])
    for p in ps:
        p.join(60)
        if p.is_alive():
            p.kill()
    res = dict(header, procs=procs)
    Path(out).write_text(json.dumps(res))
    print(json.dumps(res))


def main():
    mode = sys.argv[1]
    import cv2
    if mode == "buildinfo":
        Path(sys.argv[2]).write_text(cv2.getBuildInformation())
        return
    if mode == "imencode":
        imencode_main(sys.argv[2], float(sys.argv[3]), sys.argv[4], sys.argv[5])
        return
    hdr = dict(tool="py_codec", lang="python", opencv=cv2.__version__, numpy=np.__version__, python=sys.version.split()[0],
               executable=sys.executable)
    if mode == "decode":
        size, np_, run_s, d, out = sys.argv[2], int(sys.argv[3]), float(sys.argv[4]), sys.argv[5], sys.argv[6]
        hdr.update(mode="decode", size=size, nprocs=np_, run_s=run_s, inplace=0)
        multi(decode_child, lambda c, rq, se, sn, q: (c, size, run_s, d, rq, se, q), np_, hdr, out)
    elif mode == "videowriter":
        size, np_, paced, nfr, th, d, tmp, out = (sys.argv[2], int(sys.argv[3]), float(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6]),
                                                  sys.argv[7], sys.argv[8], sys.argv[9])
        hdr.update(mode="videowriter", size=size, nprocs=np_, paced_fps=paced, nframes=nfr, threads=th)
        multi(vw_child, lambda c, rq, se, sn, q: (c, size, paced, nfr, th, d, tmp, rq, se, sn, q), np_, hdr, out)


if __name__ == "__main__":
    main()
    sys.stdout.flush()
    os._exit(0)
