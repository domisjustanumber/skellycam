# /// script
# requires-python = ">=3.10"
# dependencies = ["opencv-contrib-python==4.12.*", "numpy", "psutil>=5.9", "pillow>=10", "simplejpeg>=1.7"]
# ///
"""OpenCV baseline (same opencv-contrib-python 4.12 series as skellycam) for MJPEG capture.

  uv run --script research/usb_cameras/tools/camlock.py -- uv run --script research/usb_cameras/mjpeg/opencv/opencv_capture.py \
      --api dshow|msmf --index N [--index M ...] --size 1280x720 --fps 30 --seconds 10 --mode decode|raw --run-dir <scratch>

--mode decode : FOURCC=MJPG, default CONVERT_RGB -> read() gives decoded BGR (the skellycam path today).
--mode raw    : dshow: CAP_PROP_CONVERT_RGB=0 ; msmf: CAP_PROP_FORMAT=-1 (and CONVERT_RGB=0).
                The script records what comes back (shape/dtype, whether bytes begin with FF D8) and, if
                it is a JPEG bitstream, stores the bytes for validation.
Index -> device mapping on the test machine is given by the caller (DirectShow order for dshow, MF order
for msmf); the script records the opened size/fps/fourcc so a wrong mapping is visible.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import mjpeg_common as mc  # noqa: E402
import cv2  # noqa: E402
import numpy as np  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--api", choices=["dshow", "msmf", "v4l2", "avfoundation", "any"], required=True)
ap.add_argument("--index", type=int, action="append", required=True)
ap.add_argument("--name", action="append", default=[], help="label per index (same order)")
ap.add_argument("--size", default="1280x720")
ap.add_argument("--fps", type=float, default=30)
ap.add_argument("--seconds", type=float, default=10)
ap.add_argument("--warmup", type=float, default=2)
ap.add_argument("--open-wait", type=float, default=90, help="max seconds to wait for each VideoCapture open before the warm-up starts (OpenCV MSMF opens took ~40 s on Gerald; 30 s, the old fixed value, let the window start mid-open)")
ap.add_argument("--mode", choices=["decode", "raw"], default="decode")
ap.add_argument("--run-dir", required=True)
ap.add_argument("--set-order", choices=["fourcc-first", "size-first", "skellycam"], default="size-first",
                help="fourcc-first: FOURCC,W,H,FPS (= skellycam create_cv2_video_capture). size-first: W,H,FPS,FOURCC. "
                     "skellycam: FOURCC,W,H,FPS then W,H,FOURCC again (create_cv2_video_capture followed by apply_camera_configuration)")
a = ap.parse_args()
W, H = map(int, a.size.lower().split("x"))
API = {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF, "v4l2": cv2.CAP_V4L2, "avfoundation": cv2.CAP_AVFOUNDATION, "any": cv2.CAP_ANY}[a.api]
writer = mc.RunWriter(Path(a.run_dir))
stop = threading.Event()
cams_meta: list[dict] = []
errors: list[str] = []
lock = threading.Lock()


def fourcc_str(v: float) -> str:
    v = int(v)
    return "".join(chr((v >> (8 * i)) & 0xFF) for i in range(4))


def reader(idx: int, cam_index: int, ready: threading.Event):
    name = a.name[idx] if idx < len(a.name) else f"{a.api}:{cam_index}"
    t_open = time.perf_counter_ns()
    params = []
    if a.api == "msmf" and a.mode == "raw":
        pass
    cap = cv2.VideoCapture(cam_index, API, params)
    if not cap.isOpened():
        errors.append(f"index {cam_index}: open failed")
        ready.set()
        return
    sets = {"order": a.set_order}
    mjpg = cv2.VideoWriter_fourcc(*"MJPG")
    if a.set_order in ("fourcc-first", "skellycam"):
        sets["fourcc"] = cap.set(cv2.CAP_PROP_FOURCC, mjpg)
    sets["w"] = cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
    sets["h"] = cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
    sets["fps"] = cap.set(cv2.CAP_PROP_FPS, a.fps)
    if a.set_order == "skellycam":
        sets["fourcc_after_create"] = fourcc_str(cap.get(cv2.CAP_PROP_FOURCC))
        sets["w2"] = cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
        sets["h2"] = cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
    if a.set_order in ("size-first", "skellycam"):
        sets["fourcc_last"] = cap.set(cv2.CAP_PROP_FOURCC, mjpg)
    if a.mode == "raw":
        if a.api == "msmf":
            sets["format_-1"] = cap.set(cv2.CAP_PROP_FORMAT, -1)
        sets["convert_rgb_0"] = cap.set(cv2.CAP_PROP_CONVERT_RGB, 0)
    info = {"idx": idx, "name": name, "cv_index": cam_index, "api": a.api, "backend_name": cap.getBackendName(), "set_results": sets,
            "got_fourcc": fourcc_str(cap.get(cv2.CAP_PROP_FOURCC)), "got_w": cap.get(cv2.CAP_PROP_FRAME_WIDTH), "got_h": cap.get(cv2.CAP_PROP_FRAME_HEIGHT),
            "got_fps": cap.get(cv2.CAP_PROP_FPS), "got_convert_rgb": cap.get(cv2.CAP_PROP_CONVERT_RGB), "got_format": cap.get(cv2.CAP_PROP_FORMAT),
            "open_ms": (time.perf_counter_ns() - t_open) / 1e6}
    with lock:
        cams_meta.append(info)
    ready.set()
    seq = 0
    shapes = {}
    jpeg_like = 0
    state_crc = [None]
    dups = 0
    try:
        while not stop.is_set():
            ok = cap.grab()
            t = time.perf_counter_ns()
            if not ok:
                errors.append(f"{name}: grab failed at seq {seq}")
                break
            ok, fr = cap.retrieve()
            if not ok or fr is None:
                errors.append(f"{name}: retrieve failed at seq {seq}")
                break
            pos_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
            key = f"{fr.shape}/{fr.dtype}"
            shapes[key] = shapes.get(key, 0) + 1
            raw = fr.reshape(-1).view(np.uint8)
            is_jpeg = raw.size >= 2 and raw[0] == 0xFF and raw[1] == 0xD8
            payload = b""
            luma = None
            if is_jpeg:
                jpeg_like += 1
                payload = raw.tobytes()
            elif seq % 30 == 0 and fr.ndim == 3 and fr.shape[0] > 8:  # night runs: record how dark the scene is
                sub = fr[::8, ::8].astype(np.float32)
                luma = round(float((sub[..., 0] * 0.114 + sub[..., 1] * 0.587 + sub[..., 2] * 0.299).mean()), 2) if fr.shape[2] == 3 else round(float(sub[..., 0].mean()), 2)
            # CRC of a 1/4-subsampled frame: identical consecutive CRCs = a repeated (duplicated) frame, since sensor noise
            # makes real consecutive frames differ. Used to check whether a pipeline pads the rate with repeats.
            crc = zlib.crc32(np.ascontiguousarray(fr[::4, ::4]).tobytes()) if not is_jpeg else None
            dup = crc is not None and crc == state_crc[0]
            state_crc[0] = crc
            dups += dup
            writer.add(idx, {"camera_key": name, "backend": f"opencv-{a.api}-{a.mode}", "seq": seq, "host_arrival_ns": t, "frame_crc": crc, "repeat_of_previous": dup,
                             "os_timestamp_ns": None, "os_timestamp_source": "none (CAP_PROP_POS_MSEC logged as pos_msec)",
                             "pos_msec": pos_ms, "uvc_pts": None, "uvc_scr_stc": None, "uvc_scr_sof": None, "device_clock_hz": None,
                             "payload_bytes": int(raw.size), "is_valid_jpeg": None, "frame_shape": list(fr.shape), "starts_ffd8": bool(is_jpeg),
                             **({"mean_luma": luma} if luma is not None else {})}, payload)
            seq += 1
    finally:
        info["frames"] = seq
        info["frame_shapes"] = shapes
        info["frames_starting_ffd8"] = jpeg_like
        info["frames_identical_to_previous"] = dups
        cap.release()


started = mc.utc_now()
threads = []
for i, ci in enumerate(a.index):
    ev = threading.Event()
    th = threading.Thread(target=reader, args=(i, ci, ev), daemon=True)
    th.start()
    if not ev.wait(a.open_wait):
        errors.append(f"index {ci}: open still running after {a.open_wait:g} s (window may include open-time work)")
    threads.append(th)
time.sleep(a.warmup)
cpu = mc.CpuWindow({"frameserver": mc.frameserver_pid()})
cpu.start()
w0 = time.perf_counter_ns()
time.sleep(a.seconds)
w1 = time.perf_counter_ns()
cpu_res = cpu.stop()
stop.set()
for th in threads:
    th.join(10)
cams_meta.sort(key=lambda m: m["idx"])
all_jpeg = all(m.get("frames_starting_ffd8", 0) == m.get("frames", -1) and m.get("frames", 0) > 0 for m in cams_meta)
meta = {"backend": f"opencv-{a.api}-{a.mode}", "utc_started": started, "command": sys.argv, "environment": mc.environment(),
        "cv2_version": cv2.__version__, "open_wait_s": a.open_wait,
        "requested": {"subtype": "MJPG", "width": W, "height": H, "fps": a.fps},
        "decoded_by_pipeline": not all_jpeg,
        "delivered_codecs": [m.get("got_fourcc") for m in cams_meta],
        "silent_format_fallback": any(m.get("got_fourcc") != "MJPG" for m in cams_meta),
        "decode_evidence": "frames returned as JPEG bitstream (start FF D8)" if all_jpeg else "frames returned as pixel arrays (see frame_shapes)",
        "cpu": cpu_res, "cameras": cams_meta, "errors": errors}
writer.flush(meta, w0, w1)
print(json.dumps({"cameras": cams_meta, "cpu": cpu_res, "errors": errors, "jpeg": all_jpeg}, default=str)[:3000])
