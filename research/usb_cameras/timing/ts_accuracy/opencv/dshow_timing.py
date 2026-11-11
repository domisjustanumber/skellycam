# /// script
# requires-python = ">=3.12"
# dependencies = ["opencv-contrib-python==4.12.*", "numpy"]
# ///
"""What a Python loop can see of frame timing through OpenCV 4.12 CAP_DSHOW (skellycam's Windows path).

    uv run --script tools/camlock.py -- uv run --script dshow_timing.py --index 3 --expect-name "Logitech Webcam C930e" \
        --out D [--seconds 10] [--work-ms 0,20,50] [--timeout-ms 5000]

Opens one camera by DirectShow index (resolve it with `wincam list` -> ds[].index just before), size-first property order
(W, H, FPS, FOURCC MJPG; the order that negotiates MJPG@30 here, mjpeg/RESULTS.md finding 6). Records what the
backend returns for CAP_PROP_BUFFERSIZE / POS_MSEC / POS_FRAMES / FPS. Then for each --work-ms value runs a loop for
--seconds: t0 = perf_counter_ns; grab(); t1; retrieve(into a preallocated array); t2; then busy-waits work_ms
(simulates skellycam's per-iteration work + lockstep wait). Writes D/frames_<work>.jsonl and D/summary.json.
Changes no camera control. Every OpenCV call runs on one worker thread; a watchdog ends the process (exit 5) if the
worker makes no progress for --timeout-ms (open gets 20 s). Read-only on the system otherwise.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics as st
import sys
import threading
import time
import zlib
from pathlib import Path

import cv2
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--index", type=int, required=True)
ap.add_argument("--expect-name", default="")
ap.add_argument("--out", required=True)
ap.add_argument("--seconds", type=float, default=10.0)
ap.add_argument("--work-ms", default="0,20,50")
ap.add_argument("--timeout-ms", type=int, default=5000)
ap.add_argument("--width", type=int, default=1280)
ap.add_argument("--height", type=int, default=720)
ap.add_argument("--fps", type=float, default=30.0)
a = ap.parse_args()
out = Path(a.out)
out.mkdir(parents=True, exist_ok=True)

state = {"phase": "start", "beat": time.perf_counter(), "limit_s": 20.0}
summary: dict = {"tool": "dshow_timing 1.0 (2026-11-09)", "cv2_version": cv2.__version__, "argv": sys.argv,
                 "index": a.index, "expect_name": a.expect_name, "utc_started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def beat(phase: str | None = None, limit_s: float | None = None) -> None:
    state["beat"] = time.perf_counter()
    if phase:
        state["phase"] = phase
    if limit_s:
        state["limit_s"] = limit_s


def write_summary() -> None:
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str))


def fourcc_str(v: float) -> str:
    v = int(v)
    return "".join(chr((v >> (8 * i)) & 0xFF) for i in range(4)) if v > 0 else str(v)


def analyse(rows: list[dict], nominal_ms: float) -> dict:
    t2 = [r["t2"] / 1e6 for r in rows]
    ret = [(r["t2"] - r["t1"]) / 1e6 for r in rows]
    grab = [(r["t1"] - r["t0"]) / 1e6 for r in rows]
    steps = [b - x for x, b in zip(t2, t2[1:])]
    blocked = [d > 2.0 for d in ret]
    q = lambda xs: {"p5": round(st.quantiles(xs, n=20)[0], 3), "p50": round(st.median(xs), 3),
                    "p95": round(st.quantiles(xs, n=20)[-1], 3), "max": round(max(xs), 3)} if len(xs) >= 20 else None
    # how many steps of the post-retrieve stamp sit near a multiple of 16 ms vs near a multiple of the nominal period
    def near(xs, grid, tol=2.0):
        return round(sum(1 for x in xs if abs(x - grid * round(x / grid)) <= tol and round(x / grid) > 0) / max(1, len(xs)), 3)
    # steps between consecutive frames that both blocked: these stamps are tied to delivery
    bsteps = [b - x for (x, bx), (b, bb) in zip(zip(t2, blocked), zip(t2[1:], blocked[1:])) if bx and bb]
    slots = [round(s / nominal_ms) for s in bsteps]
    dur = (t2[-1] - t2[0]) / 1e3 if len(t2) > 1 else 0
    dups = sum(1 for x, b in zip(rows, rows[1:]) if x["crc"] == b["crc"])
    return {"frames": len(rows), "duration_s": round(dur, 3), "delivered_fps": round((len(rows) - 1) / dur, 3) if dur else None,
            "grab_ms": q(grab), "retrieve_ms": q(ret), "retrieve_blocked_gt2ms_frac": round(sum(blocked) / len(rows), 3),
            "retrieve_immediate_lt0p5ms_frac": round(sum(1 for d in ret if d < 0.5) / len(rows), 3),
            "post_retrieve_step_ms": q(steps), "post_retrieve_step_sd_ms": round(st.pstdev(steps), 3) if steps else None,
            "steps_near_16ms_multiple_frac": near(steps, 16.0), "steps_near_nominal_multiple_frac": near(steps, nominal_ms),
            "blocked_pair_steps": len(bsteps), "blocked_pair_step_ms": q(bsteps),
            "blocked_pair_slots_histogram": {str(k): slots.count(k) for k in sorted(set(slots))},
            "implied_missing_frames_from_blocked_pairs": sum(max(0, s - 1) for s in slots),
            "identical_consecutive_frames": dups}


def run() -> None:
    beat("open", 20.0)
    t_open = time.perf_counter_ns()
    cap = cv2.VideoCapture(a.index, cv2.CAP_DSHOW)
    summary["open_ok"] = bool(cap.isOpened())
    if not cap.isOpened():
        return
    sets = {}
    sets["w"] = cap.set(cv2.CAP_PROP_FRAME_WIDTH, a.width); beat()
    sets["h"] = cap.set(cv2.CAP_PROP_FRAME_HEIGHT, a.height); beat()
    sets["fps"] = cap.set(cv2.CAP_PROP_FPS, a.fps); beat()
    sets["fourcc"] = cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG")); beat()
    sets["buffersize_1"] = cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    summary["set_results"] = sets
    summary["get"] = {"fourcc": fourcc_str(cap.get(cv2.CAP_PROP_FOURCC)), "w": cap.get(cv2.CAP_PROP_FRAME_WIDTH),
                      "h": cap.get(cv2.CAP_PROP_FRAME_HEIGHT), "fps": cap.get(cv2.CAP_PROP_FPS),
                      "buffersize": cap.get(cv2.CAP_PROP_BUFFERSIZE), "pos_msec": cap.get(cv2.CAP_PROP_POS_MSEC),
                      "pos_frames": cap.get(cv2.CAP_PROP_POS_FRAMES), "convert_rgb": cap.get(cv2.CAP_PROP_CONVERT_RGB)}
    beat("first_read", a.timeout_ms / 1e3)
    ok, fr = cap.read()
    summary["open_to_first_frame_ms"] = round((time.perf_counter_ns() - t_open) / 1e6, 1)
    summary["first_frame"] = None if fr is None else list(fr.shape)
    if not ok:
        cap.release()
        return
    img = np.empty_like(fr)
    t_end = time.perf_counter() + 2.0
    while time.perf_counter() < t_end:  # warm-up
        cap.grab(); cap.retrieve(image=img); beat()
    summary["pos_msec_after_warmup"] = cap.get(cv2.CAP_PROP_POS_MSEC)
    summary["phases"] = {}
    for w in [float(x) for x in a.work_ms.split(",")]:
        beat(f"loop_work{w:g}")
        rows = []
        t_end = time.perf_counter() + a.seconds
        while time.perf_counter() < t_end:
            t0 = time.perf_counter_ns()
            g = cap.grab()
            t1 = time.perf_counter_ns()
            r, _ = cap.retrieve(image=img)
            t2 = time.perf_counter_ns()
            beat()
            if not (g and r):
                summary.setdefault("errors", []).append(f"work {w:g}: grab {g} retrieve {r} at {len(rows)}")
                break
            rows.append({"t0": t0, "t1": t1, "t2": t2, "crc": zlib.crc32(img[::8, ::8].tobytes())})
            if w > 0:
                tw = t2 + int(w * 1e6)
                while time.perf_counter_ns() < tw:
                    pass
        with open(out / f"frames_work{w:g}.jsonl", "w") as f:
            for i, r_ in enumerate(rows):
                f.write(json.dumps({"seq": i, **r_}) + "\n")
        summary["phases"][f"work_{w:g}ms"] = analyse(rows, 1000.0 / a.fps)
        write_summary()
    beat("release", a.timeout_ms / 1e3)
    cap.release()
    summary["released"] = True


def watchdog() -> None:
    while True:
        time.sleep(0.2)
        if time.perf_counter() - state["beat"] > state["limit_s"]:
            summary["timed_out_in"] = state["phase"]
            write_summary()
            print(json.dumps(summary, default=str)[:4000])
            os._exit(5)


threading.Thread(target=watchdog, daemon=True).start()
th = threading.Thread(target=run, daemon=True)
th.start()
th.join()
summary["utc_finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
write_summary()
print(json.dumps(summary, indent=1, default=str))
sys.exit(0 if summary.get("released") else 4)
