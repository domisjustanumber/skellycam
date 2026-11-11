# /// script
# requires-python = ">=3.12"
# dependencies = ["opencv-contrib-python==4.12.*", "numpy"]
# ///
"""OpenCV 4.12 CAP_MSMF: open time, CAP_PROP_POS_MSEC (MF sample time), queue/drop behaviour, CONVERT_RGB=0 output.

    uv run --script tools/camlock.py -- uv run --script msmf_timing.py --index 0 --out D [--hw-transforms 0|1]
        [--seconds 8] [--timeout-ms 5000]

--hw-transforms sets OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS before cv2 is imported (cap_msmf.cpp:956 reads it into
MF_READWRITE_ENABLE_HARDWARE_TRANSFORMS). --index is the MF device index (wincam list -> mf[].index; OpenCV MSMF
enumerates MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID in the same order). Phases on one open:
  decode_work0 : default CONVERT_RGB=1, loop grab/retrieve for --seconds;
  raw_work0    : set CONVERT_RGB=0 (re-negotiates output), loop;
  raw_work50   : same, plus a 50 ms busy wait per iteration (slower than the 33 ms frame period).
Per frame: t_pre_grab, t_post_grab, t_post_retrieve (perf_counter_ns = QPC), pos_msec, frame shape, first two bytes.
Changes no camera control. All OpenCV calls run on one worker thread; a watchdog exits 5 if it stalls
(open is allowed 90 s because the Logitech open took 39-41 s in mjpeg/RESULTS.md finding 6).
"""
from __future__ import annotations

import argparse
import json
import os
import statistics as st
import sys
import threading
import time
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--index", type=int, required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--hw-transforms", choices=["0", "1", "unset"], default="unset")
ap.add_argument("--seconds", type=float, default=8.0)
ap.add_argument("--timeout-ms", type=int, default=5000)
ap.add_argument("--width", type=int, default=1280)
ap.add_argument("--height", type=int, default=720)
ap.add_argument("--fps", type=float, default=30.0)
ap.add_argument("--raw-before-read", action="store_true", help="set CONVERT_RGB=0 before the first read and skip the decode phase")
a = ap.parse_args()
if a.hw_transforms != "unset":
    os.environ["OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS"] = a.hw_transforms
import cv2  # noqa: E402
import numpy as np  # noqa: E402

out = Path(a.out)
out.mkdir(parents=True, exist_ok=True)
state = {"phase": "start", "beat": time.perf_counter(), "limit_s": 90.0}
summary: dict = {"tool": "msmf_timing 1.1 (2026-11-09)", "cv2_version": cv2.__version__, "argv": sys.argv,
                 "env_OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS": os.environ.get("OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS"),
                 "utc_started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def beat(phase=None, limit_s=None):
    state["beat"] = time.perf_counter()
    if phase:
        state["phase"] = phase
    if limit_s:
        state["limit_s"] = limit_s


def write_summary():
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str))


def fourcc_str(v):
    v = int(v)
    return "".join(chr((v >> (8 * i)) & 0xFF) for i in range(4)) if v > 0 else str(v)


def q(xs):
    if len(xs) < 20:
        return None
    qs = st.quantiles(xs, n=20)
    return {"p5": round(qs[0], 3), "p50": round(st.median(xs), 3), "p95": round(qs[-1], 3), "min": round(min(xs), 3), "max": round(max(xs), 3)}


def analyse(rows, nominal_ms):
    pos = [r["pos_msec"] for r in rows]
    tg = [r["t_post_grab"] / 1e6 for r in rows]
    grab_ms = [(r["t_post_grab"] - r["t_pre_grab"]) / 1e6 for r in rows]
    ret_ms = [(r["t_post_retrieve"] - r["t_post_grab"]) / 1e6 for r in rows]
    age = [g - p for g, p in zip(tg, pos)]  # host post-grab minus MF sample time, both QPC-based ms
    dpos = [b - x for x, b in zip(pos, pos[1:])]
    dur = (tg[-1] - tg[0]) / 1e3 if len(tg) > 1 else 0
    span = (pos[-1] - pos[0]) if len(pos) > 1 else 0
    return {"frames": len(rows), "delivered_fps": round((len(rows) - 1) / dur, 3) if dur else None,
            "grab_ms": q(grab_ms), "grab_immediate_lt0p5ms_frac": round(sum(1 for x in grab_ms if x < 0.5) / len(rows), 3),
            "retrieve_ms": q(ret_ms), "post_grab_minus_pos_msec_ms": q(age),
            "pos_step_ms": q(dpos), "pos_step_distinct_rounded_0p1": sorted({round(x, 1) for x in dpos})[:12],
            "pos_steps_exactly_nominal_frac": round(sum(1 for x in dpos if abs(x - nominal_ms) < 0.01) / max(1, len(dpos)), 3),
            "pos_steps_near_16ms_multiple_frac": round(sum(1 for x in dpos if abs(x - 16.0 * round(x / 16.0)) < 1.5) / max(1, len(dpos)), 3),
            "pos_gaps_gt_1p5P": sum(1 for x in dpos if x > 1.5 * nominal_ms),
            "frames_missing_by_pos_span": round(span / nominal_ms) + 1 - len(rows) if span else None,
            "shapes": {k: sum(1 for r in rows if r["shape"] == k) for k in {r["shape"] for r in rows}},
            "starts_ffd8_frac": round(sum(1 for r in rows if r["ffd8"]) / len(rows), 3)}


def loop(cap, name, seconds, work_ms):
    beat(name, a.timeout_ms / 1e3 + 10.0)  # first grab of a phase may need the reader restart after a reconfigure
    rows = []
    t_end = time.perf_counter() + seconds
    while time.perf_counter() < t_end:
        t0 = time.perf_counter_ns()
        g = cap.grab()
        t1 = time.perf_counter_ns()
        r, fr = cap.retrieve()
        t2 = time.perf_counter_ns()
        beat(None, a.timeout_ms / 1e3)
        if not (g and r and fr is not None):
            summary.setdefault("errors", []).append(f"{name}: grab {g} retrieve {r} at {len(rows)}")
            break
        pm = cap.get(cv2.CAP_PROP_POS_MSEC)
        flat = fr.reshape(-1)
        rows.append({"t_pre_grab": t0, "t_post_grab": t1, "t_post_retrieve": t2, "pos_msec": pm,
                     "shape": "x".join(map(str, fr.shape)), "ffd8": bool(flat.size > 1 and flat[0] == 0xFF and flat[1] == 0xD8)})
        if work_ms > 0:
            tw = t2 + int(work_ms * 1e6)
            while time.perf_counter_ns() < tw:
                pass
    with open(out / f"frames_{name}.jsonl", "w") as f:
        for i, r_ in enumerate(rows):
            f.write(json.dumps({"seq": i, **r_}) + "\n")
    if len(rows) > 20:
        summary["phases"][name] = analyse(rows, 1000.0 / a.fps)
    summary["phases"].setdefault(name, {})["frames"] = len(rows)
    write_summary()


def run():
    beat("open", 90.0)
    t_open = time.perf_counter_ns()
    cap = cv2.VideoCapture(a.index, cv2.CAP_MSMF)
    summary["construct_ms"] = round((time.perf_counter_ns() - t_open) / 1e6, 1)
    summary["open_ok"] = bool(cap.isOpened())
    if not cap.isOpened():
        return
    beat("configure", 90.0)
    sets = {"w": cap.set(cv2.CAP_PROP_FRAME_WIDTH, a.width), "h": cap.set(cv2.CAP_PROP_FRAME_HEIGHT, a.height),
            "fps": cap.set(cv2.CAP_PROP_FPS, a.fps), "fourcc_mjpg": cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG")),
            "buffersize_1": cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)}
    if a.raw_before_read:
        sets["convert_rgb_0_before_read"] = cap.set(cv2.CAP_PROP_CONVERT_RGB, 0)
    summary["set_results"] = sets
    summary["configure_done_ms"] = round((time.perf_counter_ns() - t_open) / 1e6, 1)
    summary["get_decode"] = {"fourcc": fourcc_str(cap.get(cv2.CAP_PROP_FOURCC)), "w": cap.get(cv2.CAP_PROP_FRAME_WIDTH),
                             "h": cap.get(cv2.CAP_PROP_FRAME_HEIGHT), "fps": cap.get(cv2.CAP_PROP_FPS),
                             "buffersize": cap.get(cv2.CAP_PROP_BUFFERSIZE), "hw_accel": cap.get(cv2.CAP_PROP_HW_ACCELERATION)}
    beat("first_read", 90.0)
    ok, fr = cap.read()
    summary["open_to_first_frame_ms"] = round((time.perf_counter_ns() - t_open) / 1e6, 1)
    summary["first_frame"] = None if fr is None else list(fr.shape)
    summary["pos_msec_first"] = cap.get(cv2.CAP_PROP_POS_MSEC)
    summary["perf_counter_ms_at_first"] = time.perf_counter_ns() / 1e6
    if not ok:
        cap.release()
        return
    summary["phases"] = {}
    if not a.raw_before_read:
        loop(cap, "decode_work0", a.seconds, 0)
        beat("set_convert_rgb_0", 30.0)
        t = time.perf_counter_ns()
        summary["set_convert_rgb_0"] = cap.set(cv2.CAP_PROP_CONVERT_RGB, 0)
        summary["set_convert_rgb_0_ms"] = round((time.perf_counter_ns() - t) / 1e6, 1)
    summary["get_raw"] = {"fourcc": fourcc_str(cap.get(cv2.CAP_PROP_FOURCC)), "w": cap.get(cv2.CAP_PROP_FRAME_WIDTH),
                          "h": cap.get(cv2.CAP_PROP_FRAME_HEIGHT), "fps": cap.get(cv2.CAP_PROP_FPS),
                          "convert_rgb": cap.get(cv2.CAP_PROP_CONVERT_RGB)}
    loop(cap, "raw_work0", a.seconds, 0)
    loop(cap, "raw_work50", a.seconds, 50)
    beat("release", 30.0)
    t = time.perf_counter_ns()
    cap.release()
    summary["release_ms"] = round((time.perf_counter_ns() - t) / 1e6, 1)
    summary["released"] = True


def watchdog():
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
