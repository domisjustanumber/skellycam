# /// script
# requires-python = ">=3.10"
# dependencies = ["opencv-python-headless==4.12.0.88", "numpy"]
# ///
"""OpenCV CAP_V4L2 with FOURCC MJPG and CAP_PROP_CONVERT_RGB = 0: the raw MJPEG buffer as a 1xN uint8 Mat.
Linux suite helper (status-quo baseline; skellycam uses OpenCV today).

    uv run --script opencv_v4l2.py version
    uv run --script opencv_v4l2.py capture --device /dev/video0 --width W --height H --fps F (--frames N|--seconds S)
                                   --out-dir D [--raw-dir R] [--save none|all|first:K]
    uv run --script opencv_v4l2.py cycle   --device /dev/video0 --width W --height H --fps F --cycles K --frames N
                                   --out-dir D [--alt-width ... --alt-height ... --alt-fps ...] [--gap-ms G]

Opens by device PATH (not index). Same frames.jsonl / cycles.jsonl schema as the other helpers; ONE JSON on stdout.
OpenCV does not check V4L2_BUF_FLAG_ERROR (corrupt frames pass unflagged on 6.14+) and reports the STREAMON errno
only in its DEBUG log: the runner sets OPENCV_LOG_LEVEL=DEBUG and parses 'errno=' from stderr
(topology_linux verifier 'Missed' 4). Timestamps: CAP_PROP_POS_MSEC = the V4L2 buffer timestamp.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

SUITE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SUITE_DIR))
from common import jpegcheck  # noqa: E402


def mono_ns() -> int:
    return time.clock_gettime_ns(time.CLOCK_MONOTONIC)


def emit(obj: dict, rc: int) -> int:
    obj.setdefault("exit_code", rc)
    print(json.dumps(obj, default=str), flush=True)
    return rc


def quick(data: bytes) -> dict:
    out = {"soi": data[:2] == b"\xff\xd8", "eoi": data.rfind(b"\xff\xd9", max(0, len(data) - 64)) >= 0,
           "sof0_w": None, "sof0_h": None, "hdr_sha1": None}
    if out["soi"]:
        sof = jpegcheck.parse_sof0(data[:65536])
        if sof:
            out["sof0_w"], out["sof0_h"] = sof["w"], sof["h"]
        span = jpegcheck.header_span(data[:65536])
        if span:
            out["hdr_sha1"] = hashlib.sha1(data[span[0]:span[1]]).hexdigest()
    return out


def session(a, w, h, fps, n_frames, seconds, fh=None, raw=None, save=("none", 0)):
    import cv2
    t0 = mono_ns()
    r = {"mode": f"MJPG {w}x{h}@{fps:g}", "ok": False, "stage_failed": None, "frames": 0, "not_raw": 0,
         "bad_markers": 0, "hdr_sha1": {}, "sof_sizes": {}}
    cap = cv2.VideoCapture(a.device, cv2.CAP_V4L2)
    try:
        if not cap.isOpened():
            r["stage_failed"] = "open"
            return r
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        cap.set(cv2.CAP_PROP_FPS, fps)
        cap.set(cv2.CAP_PROP_CONVERT_RGB, 0)
        r["open_ms"] = round((mono_ns() - t0) / 1e6, 3)
        fcc = int(cap.get(cv2.CAP_PROP_FOURCC))
        r["negotiated"] = {"fourcc": "".join(chr((fcc >> 8 * i) & 0xFF) for i in range(4)),
                           "width": cap.get(cv2.CAP_PROP_FRAME_WIDTH), "height": cap.get(cv2.CAP_PROP_FRAME_HEIGHT),
                           "fps": cap.get(cv2.CAP_PROP_FPS), "convert_rgb": cap.get(cv2.CAP_PROP_CONVERT_RGB)}
        t_first = t_last = deadline = None
        raw_off = raw.tell() if raw else 0
        fails = 0
        while True:
            ok, frame = cap.read()
            host = mono_ns()
            if not ok or frame is None:
                fails += 1
                if t_first is None or fails >= 3:
                    r["stage_failed"] = "first_frame" if t_first is None else "read"
                    break
                continue
            if t_first is None:
                t_first = host
                r["first_frame_ms"] = round((host - t0) / 1e6, 3)
                if seconds:
                    deadline = host + int(seconds * 1e9)
            t_last = host
            is_raw = frame.ndim == 2 and frame.shape[0] == 1
            data = frame.tobytes() if is_raw else b""
            if not is_raw:
                r["not_raw"] += 1
            q = quick(data) if data else {"soi": False, "eoi": False, "sof0_w": None, "sof0_h": None,
                                          "hdr_sha1": None}
            if not (q["soi"] and q["eoi"]):
                r["bad_markers"] += 1
            if q["hdr_sha1"]:
                r["hdr_sha1"][q["hdr_sha1"]] = r["hdr_sha1"].get(q["hdr_sha1"], 0) + 1
            sz = f"{q['sof0_w']}x{q['sof0_h']}"
            r["sof_sizes"][sz] = r["sof_sizes"].get(sz, 0) + 1
            if fh is not None:
                row = {"seq": r["frames"], "host_ns": host, "pos_msec": cap.get(cv2.CAP_PROP_POS_MSEC),
                       "bytes": len(data), "shape": list(frame.shape), **q}
                kind, k = save
                if raw is not None and data and (kind == "all" or (kind == "first" and r["frames"] < k)):
                    raw.write(data)
                    row["raw_off"], row["raw_len"] = raw_off, len(data)
                    raw_off += len(data)
                fh.write(json.dumps(row, separators=(",", ":")) + "\n")
            r["frames"] += 1
            if (n_frames and r["frames"] >= n_frames) or (deadline and host >= deadline):
                break
        if t_first and t_last and r["frames"] > 1 and t_last > t_first:
            r["fps_host"] = round((r["frames"] - 1) / ((t_last - t_first) / 1e9), 3)
        r["ok"] = r["frames"] > 0 and r["stage_failed"] is None
    except Exception as e:
        r["stage_failed"] = r["stage_failed"] or "internal"
        r["error"] = {"type": type(e).__name__, "message": str(e)[:500]}
    finally:
        t1 = mono_ns()
        cap.release()
        r["close_ms"] = round((mono_ns() - t1) / 1e6, 3)
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("version")
    for name in ("capture", "cycle"):
        p = sub.add_parser(name)
        p.add_argument("--device", required=True)
        p.add_argument("--width", type=int, required=True)
        p.add_argument("--height", type=int, required=True)
        p.add_argument("--fps", type=float, required=True)
        p.add_argument("--frames", type=int, default=None)
        p.add_argument("--out-dir", required=True)
        if name == "capture":
            p.add_argument("--seconds", type=float, default=None)
            p.add_argument("--raw-dir", default=None)
            p.add_argument("--save", default="none")
        else:
            p.add_argument("--cycles", type=int, required=True)
            p.add_argument("--alt-width", type=int, default=None)
            p.add_argument("--alt-height", type=int, default=None)
            p.add_argument("--alt-fps", type=float, default=None)
            p.add_argument("--gap-ms", type=float, default=0)
    a = ap.parse_args()
    try:
        import cv2
    except Exception as e:
        return emit({"cmd": a.cmd, "error": {"type": type(e).__name__, "message": str(e)}}, 4)
    if a.cmd == "version":
        return emit({"cmd": "version", "opencv": cv2.__version__}, 0)
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if a.cmd == "capture":
        save = ("none", 0) if a.save == "none" else (("all", 0) if a.save == "all"
                                                    else (a.save.split(":")[0], int(a.save.split(":")[1])))
        raw = None
        if save[0] != "none":
            rd = Path(a.raw_dir or a.out_dir)
            rd.mkdir(parents=True, exist_ok=True)
            raw = (rd / "frames.mjpeg").open("wb")
        with (out / "frames.jsonl").open("w", buffering=1) as fh:
            r = session(a, a.width, a.height, a.fps, a.frames, a.seconds if not a.frames else None, fh, raw, save)
        if raw:
            raw.close()
            r["raw_file"] = raw.name
        r.update({"cmd": "capture", "api": "opencv_v4l2", "opencv": cv2.__version__, "device": a.device})
        (out / "summary.json").write_text(json.dumps(r, default=str, indent=1))
        return emit(r, 0 if r["ok"] else 4)
    rows = []
    with (out / "cycles.jsonl").open("w", buffering=1) as fh:
        for i in range(a.cycles):
            alt = bool(a.alt_width and a.alt_height) and i % 2 == 1
            w, h, f = (a.alt_width, a.alt_height, a.alt_fps or a.fps) if alt else (a.width, a.height, a.fps)
            r = session(a, w, h, f, a.frames or 30, None)
            r = {"i": i, **{k: v for k, v in r.items() if k not in ("hdr_sha1", "sof_sizes")}}
            fh.write(json.dumps(r, default=str) + "\n")
            rows.append(r)
            if a.gap_ms:
                time.sleep(a.gap_ms / 1000)
    return emit({"cmd": "cycle", "api": "opencv_v4l2", "opencv": cv2.__version__, "device": a.device,
                 "rows": len(rows), "n_ok": sum(1 for r in rows if r["ok"])}, 0)


if __name__ == "__main__":
    sys.exit(main())
