"""P12 - does the physical disk keep up with a long 5-camera recording? (REVISION stage, 2026-10-28)

Answers the evidence critic: no earlier benchmark touched the physical disk (no fsync / FlushFileBuffers / unbuffered
I/O; files fit in the 64 GB page cache and were deleted after counting). NOT SkellyCam code; no camera, no encoder:
this measures only the storage path under the recording rates the study measured.

Target volume: the benchmark scratch folder (proto_common.SCRATCH_TMP, drive C:, the same volume SkellyCam's default
recording folder is on). Free-space guard: refuses to start below 140 GB free and stops a phase below 100 GB free.
Every file is deleted at the end of its phase.

Phases (Win32 CreateFileW + WriteFile through ctypes; WriteFile releases the GIL):
  A  max-rate sequential write, FILE_FLAG_NO_BUFFERING | FILE_FLAG_WRITE_THROUGH, 4 MiB writes, 32 GiB (more than any
     SLC cache this drive may have left at 94% full is not guaranteed; the per-GiB rate shows whether it falls off a cliff)
  B  5 paced streams (one thread per "camera"), 60 writes/s each, write-through + unbuffered, frame-sized writes
     (rounded up to 4 KiB): B1 = 162 MB/s total for 300 s (P8/P4 MJPEG passthrough rate, 5x1080p), B2 = 69 MB/s total for
     600 s (HEAD MSMF H.264 rate: baseline e2e 1080p 2,081,764,275 B / 30 s). Per write: latency; per stream: how far it
     fell behind its 60 Hz schedule (lag) = the buffering a recorder would need to ride it out (ring budget: 2.87 s at
     1080p BGR with the 1 GiB default).
  C  5 paced streams at 162 MB/s for 60 s with ordinary BUFFERED writes (what cv2/PyAV writers do), then
     FlushFileBuffers on every file at stop: the flush time = how long until the recording is actually on the disk.

Run (from C:\\Users\\Dom\\GitHub\\freemocap\\skellycam):
  .venv\\Scripts\\python.exe research\\frame_ring_buffer\\prototypes\\p12_disk_sustained.py
  (env P12_PHASES=A,B1,B2,C to choose phases; P12_B2_S, P12_B1_S, P12_A_GIB to shorten)
Output: prototypes/results/p12_disk_sustained.json and .md
"""
from __future__ import annotations

import ctypes
import mmap
import os
import shutil
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402

K32 = ctypes.WinDLL("kernel32", use_last_error=True)
K32.CreateFileW.restype = wintypes.HANDLE
K32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
K32.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
K32.FlushFileBuffers.argtypes = [wintypes.HANDLE]
K32.CloseHandle.argtypes = [wintypes.HANDLE]
GENERIC_WRITE = 0x40000000
CREATE_ALWAYS = 2
FILE_ATTRIBUTE_NORMAL = 0x80
FILE_FLAG_NO_BUFFERING = 0x20000000
FILE_FLAG_WRITE_THROUGH = 0x80000000
INVALID = ctypes.c_void_p(-1).value
GB = 1e9
MIN_FREE_START = 140e9
MIN_FREE_RUN = 100e9


def free_bytes(p):
    return shutil.disk_usage(p).free


def open_file(path, unbuffered):
    flags = (FILE_FLAG_NO_BUFFERING | FILE_FLAG_WRITE_THROUGH) if unbuffered else FILE_ATTRIBUTE_NORMAL
    h = K32.CreateFileW(str(path), GENERIC_WRITE, 0, None, CREATE_ALWAYS, flags, None)
    if h == INVALID or h is None:
        raise OSError(ctypes.get_last_error(), f"CreateFileW {path}")
    return h


def write(h, addr, n):
    w = wintypes.DWORD(0)
    if not K32.WriteFile(h, ctypes.c_void_p(addr), n, ctypes.byref(w), None):
        raise OSError(ctypes.get_last_error(), "WriteFile")
    return w.value


def aligned_buffer(n):
    mm = mmap.mmap(-1, n)  # page-aligned (4 KiB), satisfies NO_BUFFERING alignment
    mm.write(np.random.default_rng(0).integers(0, 256, n, dtype=np.uint8).tobytes())
    addr = ctypes.addressof(ctypes.c_char.from_buffer(mm))
    return mm, addr


def stats_ms(ns):
    a = np.asarray(ns, np.float64) / 1e6
    if not len(a):
        return None
    return dict(n=int(len(a)), median_ms=float(np.median(a)), p99_ms=float(np.percentile(a, 99)), p999_ms=float(np.percentile(a, 99.9)),
                max_ms=float(a.max()), over_16_7ms=int((a > 16.7).sum()), over_100ms=int((a > 100).sum()), over_1s=int((a > 1000).sum()))


def phase_a(d, gib):
    chunk = 4 << 20
    mm, addr = aligned_buffer(chunk)
    path = d / "p12_A.bin"
    h = open_file(path, True)
    per_gib, lat = [], []
    t0 = time.perf_counter()
    tg = t0
    written = 0
    stopped = None
    try:
        for g in range(gib):
            for _ in range((1 << 30) // chunk):
                a = time.perf_counter_ns()
                written += write(h, addr, chunk)
                lat.append(time.perf_counter_ns() - a)
            now = time.perf_counter()
            per_gib.append(round((1 << 30) / (now - tg) / 1e6, 1))
            tg = now
            if free_bytes(d) < MIN_FREE_RUN:
                stopped = "free-space guard"
                break
    finally:
        K32.CloseHandle(h)
        el = time.perf_counter() - t0
        os.remove(path)
        mm.close()
    return dict(phase="A", mode="unbuffered+write-through, 4 MiB sequential", bytes=written, seconds=el, mb_per_s=written / el / 1e6,
                mb_per_s_per_gib=per_gib, min_gib_mb_per_s=min(per_gib), write_call=stats_ms(lat), stopped=stopped)


def paced_streams(d, name, total_mb_s, seconds, unbuffered, flush_at_end):
    n_streams, fps = 5, 60
    per_write = int(total_mb_s * 1e6 / (n_streams * fps))
    per_write = (per_write + 4095) // 4096 * 4096
    mm, addr = aligned_buffer(per_write)
    period = 1e9 / fps
    res = [None] * n_streams
    stop_flag = {"guard": None}

    def stream(i):
        path = d / f"p12_{name}_{i}.bin"
        h = open_file(path, unbuffered)
        lat, lags = [], []
        t0 = time.perf_counter_ns() + 50_000_000
        k = 0
        end = t0 + int(seconds * 1e9)
        written = 0
        while True:
            sched = t0 + int(k * period)
            if sched >= end or stop_flag["guard"]:
                break
            now = time.perf_counter_ns()
            if sched > now:
                rem = sched - now
                if rem > 2_000_000:
                    time.sleep((rem - 1_500_000) / 1e9)
                while time.perf_counter_ns() < sched:
                    pass
            a = time.perf_counter_ns()
            written += write(h, addr, per_write)
            b = time.perf_counter_ns()
            lat.append(b - a)
            lags.append(b - sched)  # how far behind the 60 Hz schedule this write finished
            k += 1
        f0 = time.perf_counter()
        if flush_at_end:
            K32.FlushFileBuffers(h)
        flush_s = time.perf_counter() - f0
        K32.CloseHandle(h)
        res[i] = dict(stream=i, writes=k, bytes=written, write_call=stats_ms(lat), lag_behind_schedule=stats_ms(lags),
                      flush_s=flush_s if flush_at_end else None, path=str(path))

    def guard():
        while any(r is None for r in res):
            if free_bytes(d) < MIN_FREE_RUN:
                stop_flag["guard"] = "free-space guard"
                return
            time.sleep(2)

    ths = [threading.Thread(target=stream, args=(i,)) for i in range(n_streams)]
    gt = threading.Thread(target=guard, daemon=True)
    t0 = time.perf_counter()
    for t in ths:
        t.start()
    gt.start()
    for t in ths:
        t.join()
    el = time.perf_counter() - t0
    for r in res:
        os.remove(r.pop("path"))
    mm.close()
    tot = sum(r["bytes"] for r in res)
    worst_lag = max(r["lag_behind_schedule"]["max_ms"] for r in res)
    return dict(phase=name, mode=("unbuffered+write-through" if unbuffered else "buffered (OS cache)") + (", FlushFileBuffers at stop" if flush_at_end else ""),
                target_mb_per_s=total_mb_s, bytes_per_write=per_write, seconds=seconds, wall_s=el, achieved_mb_per_s=tot / el / 1e6, bytes=tot,
                streams=res, worst_write_call=max((r["write_call"] for r in res), key=lambda x: x["max_ms"]),
                worst_lag_behind_schedule_ms=worst_lag, writes_finishing_over_16_7ms_late=sum(r["lag_behind_schedule"]["over_16_7ms"] for r in res),
                max_flush_s=max((r["flush_s"] or 0) for r in res) if flush_at_end else None, stopped=stop_flag["guard"])


def main():
    import proto_common as pcm
    d = pcm.SCRATCH_TMP / "p12_disk"
    d.mkdir(parents=True, exist_ok=True)
    phases = os.environ.get("P12_PHASES", "A,B1,B2,C").split(",")
    du0 = shutil.disk_usage(d)
    out = dict(env=pcm.env_summary(), target_dir=str(d), volume_total_bytes=du0.total, free_bytes_at_start=du0.free,
               used_pct_at_start=round(100 * du0.used / du0.total, 2), rows=[],
               time_to_full_at_rate_min={str(r): round(du0.free / (r * 1e6) / 60, 1) for r in (69, 162)})
    print(f"free {du0.free / GB:.1f} GB of {du0.total / GB:.1f} GB", flush=True)
    if du0.free < MIN_FREE_START:
        out["refused"] = "less than 140 GB free"
        pcm.write_json("p12_disk_sustained.json", out)
        print("refused: low free space")
        os._exit(0)
    plan = {"A": lambda: phase_a(d, int(os.environ.get("P12_A_GIB", "32"))),
            "B1": lambda: paced_streams(d, "B1", 162, float(os.environ.get("P12_B1_S", "300")), True, False),
            "B2": lambda: paced_streams(d, "B2", 69, float(os.environ.get("P12_B2_S", "600")), True, False),
            "C": lambda: paced_streams(d, "C", 162, 60, False, True)}
    for ph in phases:
        r = plan[ph]()
        r["free_bytes_after"] = free_bytes(d)
        out["rows"].append(r)
        pcm.write_json("p12_disk_sustained.json", out)
        print(ph, {k: v for k, v in r.items() if k not in ("streams",)}, flush=True)
        time.sleep(10)
    L = ["# P12 - sustained writes to the physical disk (C:, the recording volume)", "",
         f"Volume {du0.total / GB:.0f} GB, {du0.free / GB:.1f} GB free at start ({out['used_pct_at_start']}% used). "
         f"Time to fill the free space: {out['time_to_full_at_rate_min']['69']} min at 69 MB/s (HEAD MSMF, 5x1080p), "
         f"{out['time_to_full_at_rate_min']['162']} min at 162 MB/s (MJPEG passthrough, 5x1080p).", "",
         "| phase | mode | target MB/s | achieved MB/s | GB written | write() median / p99 / p99.9 / max ms (worst stream) | writes > 100 ms / > 1 s | worst lag behind 60 Hz schedule ms | writes finishing > 16.7 ms late | flush at stop s | min per-GiB MB/s (A) |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in out["rows"]:
        if r["phase"] == "A":
            w = r["write_call"]
            L.append(f"| A | {r['mode']} | max | {r['mb_per_s']:.0f} | {r['bytes'] / GB:.1f} | {w['median_ms']:.2f} / {w['p99_ms']:.2f} / {w['p999_ms']:.2f} / {w['max_ms']:.1f} | "
                     f"{w['over_100ms']} / {w['over_1s']} | - | - | - | {r['min_gib_mb_per_s']:.0f} |")
        else:
            w = r["worst_write_call"]
            L.append(f"| {r['phase']} | {r['mode']} | {r['target_mb_per_s']} | {r['achieved_mb_per_s']:.0f} | {r['bytes'] / GB:.1f} | "
                     f"{w['median_ms']:.2f} / {w['p99_ms']:.2f} / {w['p999_ms']:.2f} / {w['max_ms']:.1f} | "
                     f"{sum(s['write_call']['over_100ms'] for s in r['streams'])} / {sum(s['write_call']['over_1s'] for s in r['streams'])} | "
                     f"{r['worst_lag_behind_schedule_ms']:.1f} | {r['writes_finishing_over_16_7ms_late']} | {r['max_flush_s'] if r['max_flush_s'] is not None else '-'} | - |")
    pcm.write_text("p12_disk_sustained.md", "\n".join(L) + "\n")
    print("\n".join(L))
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
