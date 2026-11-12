r"""T-S6 part 5: short mjpeg_qsv throughput sanity check at 1080p30 for several camera counts (one thread and one
encoder per camera, paced). Confirms the packet delay in calls stays fixed under load; records encode-call time
and submit-to-packet time. Indicative only (two other agents were running Electron tests).

Run: <phase1 venv>\python.exe -I throughput_qsv.py
"""
from __future__ import annotations

import json
import sys
import threading
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import av  # noqa: E402
import numpy as np  # noqa: E402

import eplib as E  # noqa: E402

SIZE = "1080p"
FRAMES = 300


def cam(idx: int, ring: list, async_depth, out: dict, barrier: threading.Barrier):
    w, h = E.DIMS[SIZE]
    enc = E.QsvEnc(SIZE, async_depth=async_depth)
    lates, call_ms, s2p, fifo_ok = Counter(), [], [], 0
    expect = 0
    barrier.wait()
    t0 = time.perf_counter()
    t_next = t0
    late_frames = 0
    for seq in range(FRAMES):
        now = time.perf_counter()
        if t_next > now:
            time.sleep(t_next - now)
        elif now - t_next > 1 / E.FPS:
            late_frames += 1
        t_next += 1 / E.FPS
        a = ring[seq % len(ring)]
        tc = time.perf_counter()
        res = enc.submit(seq, a, {"sfn": seq})
        call_ms.append((time.perf_counter() - tc) * 1000)
        for o in res:
            lates[o.late_calls] += 1
            s2p.append((o.t_out - o.t_submit) * 1000)
            fifo_ok += o.seq == expect
            expect += 1
    for o in enc.flush():
        fifo_ok += o.seq == expect
        expect += 1
    wall = time.perf_counter() - t0
    out[idx] = {"late_calls_hist": dict(lates), "frames_out": expect, "fifo_in_order": fifo_ok,
                "fifo_violations": enc.fifo_violations, "fps": FRAMES / wall, "late_frames": late_frames,
                "call_ms": call_ms, "s2p_ms": s2p}


def cpu_times():
    import ctypes
    from ctypes import wintypes
    k = ctypes.windll.kernel32
    c, e, kt, ut = (wintypes.FILETIME() for _ in range(4))
    k.GetProcessTimes(k.GetCurrentProcess(), ctypes.byref(c), ctypes.byref(e), ctypes.byref(kt), ctypes.byref(ut))
    f = lambda t: (t.dwHighDateTime << 32 | t.dwLowDateTime) / 1e7  # noqa: E731
    return f(kt) + f(ut)


def run(n: int, async_depth) -> dict:
    src = E.FrameSource(SIZE)
    ring = [src.frame(i) for i in range(30)]
    out: dict = {}
    barrier = threading.Barrier(n)
    ths = [threading.Thread(target=cam, args=(i, ring, async_depth, out, barrier)) for i in range(n)]
    c0, t0 = cpu_times(), time.perf_counter()
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    cpu = (cpu_times() - c0) / (time.perf_counter() - t0)
    calls = np.concatenate([np.array(v["call_ms"]) for v in out.values()])
    s2p = np.concatenate([np.array(v["s2p_ms"]) for v in out.values()])
    lates = Counter()
    for v in out.values():
        lates.update(v["late_calls_hist"])
    fps = [v["fps"] for v in out.values()]
    return {"cameras": n, "async_depth": async_depth or 4, "late_calls_hist": dict(lates),
            "frames_out_total": sum(v["frames_out"] for v in out.values()), "frames_in_total": n * FRAMES,
            "fifo_violations": sum(v["fifo_violations"] for v in out.values()),
            "fifo_in_order_total": sum(v["fifo_in_order"] for v in out.values()),
            "keep_up": sum(f >= 0.98 * E.FPS for f in fps), "fps_min": round(min(fps), 2),
            "late_paced_frames": sum(v["late_frames"] for v in out.values()),
            "encode_call_ms_p50": round(float(np.percentile(calls, 50)), 2),
            "encode_call_ms_p99": round(float(np.percentile(calls, 99)), 2),
            "submit_to_packet_ms_p50": round(float(np.percentile(s2p, 50)), 2),
            "submit_to_packet_ms_p99": round(float(np.percentile(s2p, 99)), 2),
            "process_cores": round(cpu, 2)}


def main():
    res = {"versions": {"python": sys.version.split()[0], "av": av.__version__, "numpy": np.__version__},
           "size": SIZE, "frames_per_camera": FRAMES, "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "note": "machine not quiet (two other agents running Electron tests); timing indicative only"}
    runs = []
    for ad in (None, 1):
        for n in (1, 4, 8, 16):
            runs.append(run(n, ad))
            print(json.dumps(runs[-1]), flush=True)
    res["runs"] = runs
    res["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    (E.RESULTS / "qsv_throughput.json").write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
