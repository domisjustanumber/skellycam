r"""Why does mjpeg_qsv with async_depth=1 take ~15 ms per encode() call? Test the Windows timer-resolution guess:
time 120 single-stream unpaced calls at 720p/1080p, async_depth 1 and 4, before and after timeBeginPeriod(1)
(per-process on Windows 11; undone with timeEndPeriod before exit). Indicative only.

Run: <phase1 venv>\python.exe -I qsv_ad1_timer_probe.py
"""
from __future__ import annotations

import ctypes
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import numpy as np  # noqa: E402

import eplib as E  # noqa: E402


def timed(size: str, ad, n: int = 120) -> dict:
    src = E.FrameSource(size)
    ring = [src.frame(i) for i in range(8)]
    enc = E.QsvEnc(size, async_depth=ad)
    calls = []
    t0 = time.perf_counter()
    for seq in range(n):
        tc = time.perf_counter()
        enc.submit(seq, ring[seq % 8], {"sfn": seq})
        calls.append((time.perf_counter() - tc) * 1000)
    enc.flush()
    wall = time.perf_counter() - t0
    c = np.array(calls[5:])
    return {"size": size, "async_depth": ad or 4, "fps": round(n / wall, 1),
            "call_ms_p50": round(float(np.median(c)), 2), "call_ms_p90": round(float(np.percentile(c, 90)), 2)}


def main():
    winmm = ctypes.windll.winmm
    out = {"default_timer": [], "timeBeginPeriod_1": []}
    for size in ("720p", "1080p"):
        for ad in (1, None):
            out["default_timer"].append(timed(size, ad))
    winmm.timeBeginPeriod(1)
    try:
        for size in ("720p", "1080p"):
            for ad in (1, None):
                out["timeBeginPeriod_1"].append(timed(size, ad))
    finally:
        winmm.timeEndPeriod(1)
    print(json.dumps(out, indent=1))
    (E.RESULTS / "qsv_ad1_timer_probe.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
