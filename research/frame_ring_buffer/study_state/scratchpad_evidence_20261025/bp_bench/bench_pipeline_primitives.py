"""
Micro-benchmarks of the primitives a 5-camera x 60 fps capture/record pipeline is built from.

Run (from the SkellyCam checkout so its venv is used; nothing is installed):
    cd C:\\Users\\Dom\\GitHub\\freemocap\\skellycam
    .venv\\Scripts\\python.exe -I <scratch>\\bp_bench\\bench_pipeline_primitives.py <section> [<out_dir>]

sections: memcpy | pickle | mpqueue | jpeg | nvenc | disk | all
Each section prints a table and writes <out_dir>/<section>.json
"""
import json
import os
import pickle
import statistics
import sys
import threading
import time
from multiprocessing import shared_memory

import numpy as np

SIZES = {"720p": (720, 1280, 3), "1080p": (1080, 1920, 3)}
OUT_DIR = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(os.path.abspath(__file__))


def synthetic_frame(shape, seed=0):
    """Camera-like content: smooth gradients + texture + mild sensor noise (JPEG is content dependent)."""
    import cv2
    h, w, _ = shape
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    base = np.stack([
        128 + 100 * np.sin(xx / 97.0) * np.cos(yy / 61.0),
        128 + 90 * np.sin((xx + yy) / 151.0),
        128 + 80 * np.cos(xx / 43.0 - yy / 77.0),
    ], axis=-1)
    texture = cv2.GaussianBlur(rng.normal(0, 40, (h, w, 3)).astype(np.float32), (0, 0), 3)
    noise = rng.normal(0, 3, (h, w, 3)).astype(np.float32)
    return np.clip(base + texture + noise, 0, 255).astype(np.uint8)


def timeit(fn, n, warmup=5):
    for _ in range(warmup):
        fn()
    ts = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        ts.append(time.perf_counter() - t0)
    return {"median_ms": statistics.median(ts) * 1e3, "p99_ms": sorted(ts)[int(0.99 * (len(ts) - 1))] * 1e3,
            "min_ms": min(ts) * 1e3, "n": n}


def dump(section, result):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, f"{section}.json"), "w") as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result, indent=2))


# ----------------------------------------------------------------------------- memcpy
def bench_memcpy():
    res = {}
    for name, shape in SIZES.items():
        nbytes = int(np.prod(shape))
        src = synthetic_frame(shape)
        heap_dst = np.empty_like(src)
        shm = shared_memory.SharedMemory(create=True, size=nbytes * 8)
        try:
            ring = [np.ndarray(shape, np.uint8, buffer=shm.buf, offset=i * nbytes) for i in range(8)]
            for r in ring:
                r[:] = 0  # pre-fault pages
            k = [0]

            def into_shm():
                np.copyto(ring[k[0] % 8], src)
                k[0] += 1

            r_heap = timeit(lambda: np.copyto(heap_dst, src), 300)
            r_shm = timeit(into_shm, 300)
            r_alloc = timeit(lambda: src.copy(), 300)  # allocate + copy (what frame.copy() does)
            r_view = timeit(lambda: np.ndarray(shape, np.uint8, buffer=shm.buf, offset=nbytes), 2000)
            for r in (r_heap, r_shm, r_alloc):
                r["GBps"] = nbytes / (r["median_ms"] / 1e3) / 1e9
            res[name] = {"bytes": nbytes, "copyto_heap": r_heap, "copyto_shm_ring": r_shm,
                         "ndarray_copy_alloc": r_alloc, "numpy_view_on_shm_no_copy": r_view,
                         "budget_per_frame_ms_at_300fps": 1000 / 300}
            del ring
        finally:
            shm.close()
            shm.unlink()
    dump("memcpy", res)


# ----------------------------------------------------------------------------- pickle
def bench_pickle():
    res = {}
    for name, shape in SIZES.items():
        src = synthetic_frame(shape)
        p4 = timeit(lambda: pickle.loads(pickle.dumps(src, protocol=4)), 100)
        p5 = timeit(lambda: pickle.loads(pickle.dumps(src, protocol=5)), 100)
        bufs = []

        def oob():
            bufs.clear()
            data = pickle.dumps(src, protocol=5, buffer_callback=bufs.append)
            return pickle.loads(data, buffers=bufs)

        p5oob = timeit(oob, 300)
        res[name] = {"pickle4_dumps_loads": p4, "pickle5_inband_dumps_loads": p5,
                     "pickle5_out_of_band_dumps_loads": p5oob}
    dump("pickle", res)


# ----------------------------------------------------------------------------- mp.Queue
def _queue_consumer(q, n, done):
    for _ in range(n):
        q.get()
    done.put(time.perf_counter())


def bench_mpqueue():
    import multiprocessing as mp
    res = {}
    for name, shape in SIZES.items():
        src = synthetic_frame(shape)
        n = 300
        q = mp.Queue(maxsize=16)
        done = mp.Queue()
        p = mp.Process(target=_queue_consumer, args=(q, n, done))
        p.start()
        q.put(src)  # warm the feeder thread and consumer
        time.sleep(0.5)
        n_send = n - 1
        t0 = time.perf_counter()
        for _ in range(n_send):
            q.put(src)
        t_end = done.get()
        p.join()
        dt = t_end - t0
        res[name] = {"frames": n_send, "seconds": dt, "fps": n_send / dt,
                     "GBps": n_send * src.nbytes / dt / 1e9,
                     "note": "producer->consumer via multiprocessing.Queue (pickle + pipe + unpickle)"}
    dump("mpqueue", res)


# ----------------------------------------------------------------------------- jpeg (preview path)
def bench_jpeg():
    import cv2
    cv2.setNumThreads(1)  # one core per stream; we want per-frame CPU cost
    res = {"cv2_version": cv2.__version__,
           "cv2_jpeg_lib": [l.strip() for l in cv2.getBuildInformation().splitlines() if "JPEG:" in l]}
    for name, shape in SIZES.items():
        src = synthetic_frame(shape)
        r = {}
        for q in (70, 80, 95):
            ok, enc = cv2.imencode(".jpg", src, [cv2.IMWRITE_JPEG_QUALITY, q])
            r[f"imencode_full_q{q}"] = timeit(lambda: cv2.imencode(".jpg", src, [cv2.IMWRITE_JPEG_QUALITY, q]), 100)
            r[f"imencode_full_q{q}"]["bytes"] = int(enc.nbytes)
        ok, enc = cv2.imencode(".jpg", src, [cv2.IMWRITE_JPEG_QUALITY, 80])
        r["imdecode_full_q80"] = timeit(lambda: cv2.imdecode(enc, cv2.IMREAD_COLOR), 100)
        r["imdecode_reduced_2_q80"] = timeit(lambda: cv2.imdecode(enc, cv2.IMREAD_REDUCED_COLOR_2), 100)
        small = np.empty((360, 640, 3), np.uint8)
        r["resize_to_640x360_area"] = timeit(lambda: cv2.resize(src, (640, 360), dst=small, interpolation=cv2.INTER_AREA), 200)
        r["resize_to_640x360_linear"] = timeit(lambda: cv2.resize(src, (640, 360), dst=small, interpolation=cv2.INTER_LINEAR), 200)
        cv2.resize(src, (640, 360), dst=small, interpolation=cv2.INTER_AREA)
        ok, enc_s = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 80])
        r["imencode_640x360_q80"] = timeit(lambda: cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 80]), 300)
        r["imencode_640x360_q80"]["bytes"] = int(enc_s.nbytes)
        res[name] = r
    dump("jpeg", res)


# ----------------------------------------------------------------------------- nvenc / libx264 via PyAV
def _encode_stream(codec_name, shape, n_frames, opts, out, idx, pix_fmt):
    import av
    h, w, _ = shape
    src = synthetic_frame(shape, seed=idx)
    # slight per-frame change so the encoder cannot skip everything
    frames_bgr = [np.roll(src, k * 4, axis=1) for k in range(8)]
    cc = av.CodecContext.create(codec_name, "w")
    cc.width, cc.height = w, h
    cc.pix_fmt = pix_fmt
    from fractions import Fraction
    cc.time_base = Fraction(1, 60)
    cc.framerate = Fraction(60, 1)
    cc.options = opts
    cc.open()
    n_bytes = 0
    t_conv = 0.0
    t0 = time.perf_counter()
    for i in range(n_frames):
        tc = time.perf_counter()
        vf = av.VideoFrame.from_ndarray(frames_bgr[i % 8], format="bgr24").reformat(format=pix_fmt)
        t_conv += time.perf_counter() - tc
        vf.pts = i
        for pkt in cc.encode(vf):
            n_bytes += pkt.size
    for pkt in cc.encode(None):
        n_bytes += pkt.size
    dt = time.perf_counter() - t0
    out[idx] = {"fps": n_frames / dt, "seconds": dt, "bgr_to_yuv_convert_ms_per_frame": t_conv / n_frames * 1e3,
                "bytes_total": n_bytes, "bytes_per_frame": n_bytes / n_frames,
                "MBps_at_60fps": n_bytes / n_frames * 60 / 1e6}


def bench_nvenc():
    res = {}
    configs = [
        ("h264_nvenc", {"preset": "p1", "tune": "ll", "rc": "vbr", "cq": "23"}, "nv12"),
        ("hevc_nvenc", {"preset": "p1", "tune": "ll", "rc": "vbr", "cq": "25"}, "nv12"),
        ("libx264", {"preset": "ultrafast", "crf": "23", "threads": "4"}, "yuv420p"),
        ("mjpeg", {"q:v": "4"}, "yuvj420p"),
    ]
    n_frames = 600
    for name, shape in SIZES.items():
        res[name] = {}
        for codec, opts, pix in configs:
            for n_streams in (1, 5):
                out = {}
                ths = [threading.Thread(target=_encode_stream, args=(codec, shape, n_frames, opts, out, i, pix))
                       for i in range(n_streams)]
                t0 = time.perf_counter()
                try:
                    for t in ths:
                        t.start()
                    for t in ths:
                        t.join()
                    wall = time.perf_counter() - t0
                    res[name][f"{codec}_x{n_streams}"] = {
                        "per_stream": out, "wall_s": wall,
                        "aggregate_fps": n_streams * n_frames / wall if len(out) == n_streams else None}
                except Exception as e:  # noqa
                    res[name][f"{codec}_x{n_streams}"] = {"error": repr(e)}
                print(name, codec, n_streams, res[name][f"{codec}_x{n_streams}"].get("aggregate_fps"), flush=True)
    dump("nvenc", res)


# ----------------------------------------------------------------------------- disk
def bench_disk():
    import ctypes
    from ctypes import wintypes
    target_dir = os.path.join(OUT_DIR, "disk_tmp")
    os.makedirs(target_dir, exist_ok=True)
    shape = SIZES["1080p"]
    frame_bytes = int(np.prod(shape))  # 6,220,800 B, multiple of 4096? -> 6220800/4096 = 1518.75, no
    total_gb = 4
    n_frames = int(total_gb * 1e9 // frame_bytes)
    src = synthetic_frame(shape)
    res = {"frame_bytes": frame_bytes, "n_frames": n_frames, "total_bytes": n_frames * frame_bytes}

    # 1) buffered python writes, one write per frame (raw BGR)
    p = os.path.join(target_dir, "buffered.raw")
    lat = []
    t0 = time.perf_counter()
    with open(p, "wb", buffering=0) as f:
        mv = memoryview(src).cast("B")
        for _ in range(n_frames):
            ts = time.perf_counter()
            f.write(mv)
            lat.append(time.perf_counter() - ts)
        t_write = time.perf_counter() - t0
        ts = time.perf_counter()
        os.fsync(f.fileno())
        t_fsync = time.perf_counter() - ts
    total = time.perf_counter() - t0
    res["buffered_write"] = {"write_phase_GBps": n_frames * frame_bytes / t_write / 1e9,
                             "incl_fsync_GBps": n_frames * frame_bytes / total / 1e9, "fsync_s": t_fsync,
                             "per_write_median_ms": statistics.median(lat) * 1e3,
                             "per_write_p99_ms": sorted(lat)[int(0.99 * (len(lat) - 1))] * 1e3,
                             "per_write_max_ms": max(lat) * 1e3}
    os.remove(p)

    # 2) FILE_FLAG_NO_BUFFERING | FILE_FLAG_WRITE_THROUGH with 4 KiB-aligned VirtualAlloc buffer,
    #    frames packed into 32 MiB aligned chunks (sector-multiple sizes as the docs require)
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    k32.WriteFile.argtypes = [wintypes.HANDLE, wintypes.LPCVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                              wintypes.LPVOID]
    k32.VirtualAlloc.restype = ctypes.c_void_p
    k32.VirtualAlloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD, wintypes.DWORD]
    GENERIC_WRITE, CREATE_ALWAYS = 0x40000000, 2
    FILE_FLAG_NO_BUFFERING, FILE_FLAG_WRITE_THROUGH = 0x20000000, 0x80000000
    chunk = 32 * 1024 * 1024
    for label, flags in (("no_buffering", FILE_FLAG_NO_BUFFERING),
                         ("no_buffering_write_through", FILE_FLAG_NO_BUFFERING | FILE_FLAG_WRITE_THROUGH)):
        p = os.path.join(target_dir, f"{label}.raw")
        h = k32.CreateFileW(p, GENERIC_WRITE, 0, None, CREATE_ALWAYS, flags, None)
        if h in (None, wintypes.HANDLE(-1).value):
            res[label] = {"error": ctypes.get_last_error()}
            continue
        buf = k32.VirtualAlloc(None, chunk, 0x3000, 0x04)
        arr = np.ctypeslib.as_array((ctypes.c_uint8 * chunk).from_address(buf))
        arr[:] = np.resize(src.reshape(-1), chunk)
        n_chunks = (n_frames * frame_bytes) // chunk
        written = wintypes.DWORD(0)
        lat = []
        t0 = time.perf_counter()
        for _ in range(n_chunks):
            ts = time.perf_counter()
            ok = k32.WriteFile(h, ctypes.c_void_p(buf), chunk, ctypes.byref(written), None)
            lat.append(time.perf_counter() - ts)
            if not ok:
                raise OSError(ctypes.get_last_error())
        dt = time.perf_counter() - t0
        k32.CloseHandle(h)
        res[label] = {"GBps": n_chunks * chunk / dt / 1e9, "chunk_bytes": chunk,
                      "per_chunk_median_ms": statistics.median(lat) * 1e3,
                      "per_chunk_max_ms": max(lat) * 1e3}
        os.remove(p)
    dump("disk", res)


if __name__ == "__main__":
    section = sys.argv[1] if len(sys.argv) > 1 else "all"
    table = {"memcpy": bench_memcpy, "pickle": bench_pickle, "mpqueue": bench_mpqueue, "jpeg": bench_jpeg,
             "nvenc": bench_nvenc, "disk": bench_disk}
    for k, fn in table.items():
        if section in (k, "all"):
            print(f"===== {k} =====", flush=True)
            fn()
