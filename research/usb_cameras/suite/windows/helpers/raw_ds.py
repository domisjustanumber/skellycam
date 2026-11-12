# /// script
# requires-python = "==3.12.13"
# dependencies = ["av==19.0.2", "opencv-contrib-python==5.0.0.93", "numpy==2.5.4"]
# ///
"""Raw (uncompressed) capture through DirectShow and OpenCV for W-RAW (plan capture_stack_options_plan.md 4.1 row 9a).

    uv run --script raw_ds.py pyav   --device <DS DevicePath> --width W --height H --fps F --pixel-format yuyv422
        --seconds S --timeout-ms T --out-dir D [--save-frames K]
    uv run --script raw_ds.py ffmpeg --device <DS DevicePath> ... (same options)
    uv run --script raw_ds.py opencv --backend dshow|msmf --index N --expect-path <DS path | MF symlink>
        --width W --height H --fps F --fourcc YUY2 --seconds S --timeout-ms T [--open-timeout-ms T2]
        --out-dir D [--save-frames K]

Run it under tools/camlock.py like every camera command (ctx.camcmd does). Exit codes follow wincam: 0 ok, 2 usage,
4 camera failure or not the requested format (details in the JSON), 5 a call did not return (the process exits
without waiting for the stuck call).

What each route asks for:
- ``pyav``: ``av.open("video=@device_pnp_<path>", format="dshow", options={video_size, framerate, pixel_format,
  rtbufsize})``. ``pixel_format`` is a real dshow AVOption (unlike ``vcodec``, which PyAV cannot pass: see
  pyav_ds.py), so this checks whether PyAV can request a raw format explicitly. Packets are demuxed, never decoded;
  a raw dshow packet is one whole frame.
- ``ffmpeg``: the ffmpeg CLI with input ``-pixel_format``, packets copied (``-c copy``) to a framecrc list (size and
  arrival time per frame) and the first frames to a rawvideo file.
- ``opencv``: ``VideoCapture(index, CAP_DSHOW | CAP_MSMF)``, then FOURCC, width, height, fps, (MSMF:
  ``CAP_PROP_FORMAT = -1``) and ``CAP_PROP_CONVERT_RGB = 0``, in that order (the order of mjpeg/opencv/
  opencv_capture.py; DSHOW's result depends on property order, REPORT finding 3). Every OpenCV call runs on one
  worker thread with a bound. OpenCV opens by index only; ``--expect-path`` records which device the caller meant
  and lets the suite's camera lock / fault scan find the camera in argv.

Every route records what was DELIVERED (codec / pixel format / FOURCC readback / frame shape) and each frame's byte
length; W-RAW compares that with the expected length of the requested format. Saved frames (``--save-frames``,
default 3, one per second after the first 3 frames) go to ``<out-dir>/frames.raw`` with ``raw_offset`` /
``raw_len`` in frames.jsonl. Pass an out-dir outside the repo (the suite's raw_dir).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shutil
import socket
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pyav_ds  # noqa: E402  (Session, LOGS, device_url, _run_with_cpu, parse_ffmpeg_stream; no camera at import)

TOOL_VERSION = "raw_ds 1.0 (2026-11-08)"
EXIT_OK, EXIT_USAGE, EXIT_CAMERA, EXIT_TIMEOUT = 0, 2, 4, 5
SAVE_SKIP = 3          # frames skipped before the first saved one (start-up frames are often dark)


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def save_plan(fps: float, k: int) -> set[int]:
    """Frame numbers to save: ``k`` frames, one per second of nominal rate, after the first SAVE_SKIP."""
    gap = max(1, int(round(fps)))
    return {SAVE_SKIP + i * gap for i in range(max(0, k))}


def header(sub: str, a: argparse.Namespace) -> dict[str, Any]:
    return {"tool": "raw_ds", "version": TOOL_VERSION, "subcommand": sub, "api": a.api or sub,
            "utc_started": utc_now(), "pid": os.getpid(), "argv": sys.argv, "hostname": socket.gethostname(),
            "timeout_ms": a.timeout_ms, "error": None}


def finish(doc: dict, rc: int, out: Path, hung: bool) -> None:
    doc["utc_finished"] = utc_now()
    doc["exit_code"] = rc
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    sys.stdout.write(json.dumps(doc, default=str) + "\n")
    sys.stdout.flush()
    pyav_ds.LOGS.stop()
    if hung:
        os._exit(rc)  # a stuck call holds the graph / device; do not wait for it at interpreter exit
    sys.exit(rc)


def length_stats(rows: list[dict]) -> dict[str, Any]:
    lens: dict[str, int] = {}
    for r in rows:
        k = str(r.get("bytes"))
        lens[k] = lens.get(k, 0) + 1
    vals = [r["bytes"] for r in rows if isinstance(r.get("bytes"), int)]
    return {"total": len(rows), "bytes_min": min(vals) if vals else None, "bytes_max": max(vals) if vals else None,
            "len_counts": dict(list(lens.items())[:16]), "distinct_lengths": len(lens)}


def fps_of(rows: list[dict], key: str) -> tuple[float | None, float | None]:
    ts = [r[key] for r in rows if isinstance(r.get(key), (int, float))]
    if len(ts) < 2 or ts[-1] <= ts[0]:
        return None, None
    dur = (ts[-1] - ts[0]) / 1e9
    return (len(ts) - 1) / dur, dur


# ============================================================================================================ PyAV
def cmd_pyav(a: argparse.Namespace, av_mod) -> None:
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    doc = header("pyav", a)
    doc["backend"] = "pyav-dshow"
    url = pyav_ds.device_url(a.device)
    opts = {"video_size": f"{a.width}x{a.height}", "framerate": str(a.fps), "pixel_format": a.pixel_format,
            "rtbufsize": a.rtbufsize}
    doc["requested"] = {"pixel_format": a.pixel_format, "width": a.width, "height": a.height, "fps": a.fps,
                        "seconds": a.seconds, "options": opts, "url": url}
    saves = save_plan(pyav_ds.fps_value(a.fps), a.save_frames)
    timeout_s = a.timeout_ms / 1000.0
    sess = pyav_ds.Session(av_mod, url, opts, timeout_s, None, a.seconds)
    log_off = pyav_ds.LOGS.offset()
    rows: list[dict] = []
    t0 = time.perf_counter_ns()
    sess.start()
    hung = timed_out = False
    err = None
    stage = None
    delivered = None
    open_ms = first_ms = close_ms = None
    fj = (out / "frames.jsonl").open("w", encoding="utf-8", newline="\n")
    fr = (out / "frames.raw").open("wb") if saves else None
    m = sess.get(timeout_s + 1.0)
    if m is None:
        hung = timed_out = True
        stage = "open"
        err = {"stage": "open", "class": "timeout", "reason": "av.open did not return within the timeout"}
    elif m[0] == "open_error":
        open_ms = (m[2] - t0) / 1e6
        logs = pyav_ds.LOGS.since(log_off)
        err = pyav_ds.classify_exc(m[1], logs)
        err.update(stage="open", open_duration_ms=open_ms, ffmpeg_log=logs[-30:])
        stage = "open"
    else:
        open_ms = (m[2] - t0) / 1e6
        delivered = m[1]
        while True:
            m = sess.get(timeout_s)
            if m is None:
                timed_out = True
                stage = "first_frame" if not rows else "streaming"
                err = {"stage": stage, "class": "timeout", "reason": f"no packet for {timeout_s:.1f} s"}
                sess.stop.set()
                break
            if m[0] == "pkt":
                _, t, b, pts, tb, _dts = m
                seq = len(rows)
                if first_ms is None:
                    first_ms = (t - t0) / 1e6
                row = {"seq": seq, "qpc_ns": t, "pts": pts,
                       "pts_ns": int(pts * tb[0] * 1_000_000_000 // tb[1]) if (pts is not None and tb) else None,
                       "bytes": len(b)}
                if fr is not None and seq in saves:
                    row["raw_offset"] = fr.tell()
                    row["raw_len"] = len(b)
                    fr.write(b)
                rows.append(row)
                fj.write(json.dumps(row) + "\n")
            elif m[0] == "read_error":
                logs = pyav_ds.LOGS.since(log_off)
                err = pyav_ds.classify_exc(m[1], logs)
                stage = "streaming" if rows else "first_frame"
                err.update(stage=stage, ffmpeg_log=logs[-30:])
            elif m[0] == "stopping":
                break
        # close (the worker closes the container after the loop)
        tc = time.perf_counter_ns()
        while True:
            m = sess.get(timeout_s + 1.0)
            if m is None or m[0] == "closed":
                break
        if m is None:
            hung = True
            close_ms = (time.perf_counter_ns() - tc) / 1e6
            err = err or {"stage": "close", "class": "timeout", "reason": "container.close() did not return"}
            stage = stage or "close"
        else:
            close_ms = m[1]
    fj.close()
    if fr is not None:
        fr.close()
    fps, dur = fps_of(rows, "qpc_ns")
    doc.update({"delivered": delivered, "codec": (delivered or {}).get("codec"),
                "pix_fmt": (delivered or {}).get("pix_fmt"),
                "timings": {"open_ms": open_ms, "first_frame_ms": first_ms, "open_to_first_frame_ms": first_ms,
                            "close_ms": close_ms},
                "frames": length_stats(rows), "fps_measured": fps, "duration_s": dur, "fps_basis": "qpc arrival",
                "stage_failed": stage, "timed_out": timed_out, "hung": hung, "unreleasable": hung,
                "ok": err is None and bool(rows), "error": err,
                "files": {"frames_jsonl": str(out / "frames.jsonl"),
                          "frames_raw": str(out / "frames.raw") if saves else None}})
    rc = EXIT_TIMEOUT if (hung or timed_out) else (EXIT_OK if doc["ok"] else EXIT_CAMERA)
    finish(doc, rc, out, hung)


# ============================================================================================================ ffmpeg CLI
def parse_framecrc(text: str) -> tuple[tuple[int, int] | None, list[tuple[int, int]]]:
    """(time base, [(pts, size)]) from an FFmpeg framecrc file."""
    tb, out = None, []
    for line in text.splitlines():
        if line.startswith("#tb"):
            mm = re.search(r"(\d+)/(\d+)", line)
            if mm:
                tb = (int(mm.group(1)), int(mm.group(2)))
            continue
        if line.startswith("#") or not line.strip():
            continue
        parts = [x.strip() for x in line.split(",")]
        if len(parts) >= 5:
            try:
                out.append((int(parts[2]), int(parts[4])))
            except ValueError:
                continue
    return tb, out


def cmd_ffmpeg(a: argparse.Namespace) -> None:
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    doc = header("ffmpeg", a)
    doc["backend"] = "ffmpeg-cli-dshow"
    exe = shutil.which("ffmpeg")
    doc["requested"] = {"pixel_format": a.pixel_format, "width": a.width, "height": a.height, "fps": a.fps,
                        "seconds": a.seconds}
    if not exe:
        doc.update(ok=False, stage_failed="spawn", untested=True,
                   error={"stage": "spawn", "class": "other", "reason": "ffmpeg CLI not on PATH"})
        finish(doc, EXIT_CAMERA, out, False)
    crc = out / "framecrc.txt"
    rawf = out / "frames.raw"
    argv = [exe, "-hide_banner", "-nostats", "-y", "-f", "dshow", "-use_wallclock_as_timestamps", "1",
            "-rtbufsize", a.rtbufsize, "-pixel_format", a.pixel_format, "-video_size", f"{a.width}x{a.height}",
            "-framerate", str(a.fps), "-i", pyav_ds.device_url(a.device),
            "-map", "0:v", "-t", str(a.seconds), "-c", "copy", "-f", "framecrc", str(crc)]
    nsave = max(0, a.save_frames)
    if nsave:
        argv += ["-map", "0:v", "-frames:v", str(nsave), "-c", "copy", "-f", "rawvideo", str(rawf)]
    doc["ffmpeg_argv"] = argv
    pr = pyav_ds._run_with_cpu(argv, timeout_s=a.seconds + 3 * a.timeout_ms / 1000.0 + 10)
    se = pr.get("stderr") or ""
    codec, pix = pyav_ds.parse_ffmpeg_stream(se)
    try:
        tb, frames = parse_framecrc(crc.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        tb, frames = None, []
    rows = []
    off = 0
    for i, (pts, size) in enumerate(frames):
        row = {"seq": i, "qpc_ns": None, "pts": pts,
               "pts_ns": int(pts * tb[0] * 1_000_000_000 // tb[1]) if tb else None, "bytes": size}
        if i < nsave and rawf.exists():
            row["raw_offset"] = off
            row["raw_len"] = size
            off += size
        rows.append(row)
    with (out / "frames.jsonl").open("w", encoding="utf-8", newline="\n") as fj:
        for r in rows:
            fj.write(json.dumps(r) + "\n")
    fps, dur = fps_of(rows, "pts_ns")
    timed_out = bool(pr.get("timed_out"))
    hung = pr.get("rc") is None and not pr.get("spawn_error")
    ok = pr.get("rc") == 0 and not timed_out and bool(rows)
    err = None
    if not ok:
        tail = [ln for ln in se.splitlines() if ln.strip()][-12:]
        err = {"stage": "open" if not rows else "streaming", "class": "timeout" if timed_out else "other",
               "errno": 5 if ("I/O error" in se or "Input/output error" in se) else None,
               "reason": "ffmpeg timed out" if timed_out else f"ffmpeg rc={pr.get('rc')}",
               "ffmpeg_log": [{"msg": x[:300]} for x in tail]}
    doc.update({"delivered": {"codec": codec, "pix_fmt": pix, "width": a.width, "height": a.height},
                "codec": codec, "pix_fmt": pix, "frames": length_stats(rows), "fps_measured": fps, "duration_s": dur,
                "fps_basis": "packet pts = wall clock at demux (use_wallclock_as_timestamps)",
                "timings": {"process_ms": pr.get("elapsed_ms")},
                "cpu": {"process_cpu_s": pr.get("cpu_s"), "lifetime_s": pr.get("lifetime_s")},
                "stage_failed": (err or {}).get("stage"), "timed_out": timed_out, "hung": hung, "unreleasable": hung,
                "ok": ok, "error": err,
                "files": {"frames_jsonl": str(out / "frames.jsonl"), "framecrc": str(crc),
                          "frames_raw": str(rawf) if nsave and rawf.exists() else None}})
    rc = EXIT_TIMEOUT if timed_out else (EXIT_OK if ok else EXIT_CAMERA)
    finish(doc, rc, out, False)


# ============================================================================================================ OpenCV
def cmd_opencv(a: argparse.Namespace) -> None:
    import opencv_ds  # noqa: PLC0415  (bounded() worker thread, fourcc_str; no camera at import)
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    doc = header("opencv", a)
    try:
        import cv2  # noqa: PLC0415
    except Exception as e:  # noqa: BLE001
        doc.update(ok=False, stage_failed="import", untested=True,     # a harness failure, not a route result
                   error={"stage": "import", "class": "other", "reason": f"harness: cv2 import failed: {e!r}"})
        finish(doc, EXIT_CAMERA, out, False)
    backend = cv2.CAP_DSHOW if a.backend == "dshow" else cv2.CAP_MSMF
    doc.update({"backend": f"opencv-{a.backend}", "opencv": cv2.__version__, "index": a.index,
                "expect_path": a.expect_path,
                "env": {"OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS": os.environ.get(
                    "OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS")}})
    doc["requested"] = {"fourcc": a.fourcc, "width": a.width, "height": a.height, "fps": a.fps, "seconds": a.seconds,
                        "set_order": "fourcc, width, height, fps, " + ("format=-1, " if a.backend == "msmf" else "")
                                     + "convert_rgb=0"}
    T = a.timeout_ms / 1000.0
    rows: list[dict] = []
    err = None
    stage = None
    hung = False
    t0 = time.perf_counter_ns()
    done, cap, exc, ms = opencv_ds.bounded(lambda: cv2.VideoCapture(a.index, backend), a.open_timeout_ms / 1000.0)
    timings: dict[str, Any] = {"open_ms": ms}
    if not done:
        hung = True
        stage = "open"
        err = {"stage": "open", "class": "timeout", "reason": "VideoCapture() did not return"}
    elif exc is not None or cap is None or not cap.isOpened():
        stage = "open"
        err = {"stage": "open", "class": "other",
               "reason": repr(exc) if exc else "isOpened() is False (OpenCV hides the HRESULT in its log)"}
        if cap is not None:
            opencv_ds.bounded(cap.release, T)
    else:
        def do_sets() -> dict:
            s: dict[str, Any] = {"fourcc": cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*a.fourcc[:4])),
                                 "w": cap.set(cv2.CAP_PROP_FRAME_WIDTH, a.width),
                                 "h": cap.set(cv2.CAP_PROP_FRAME_HEIGHT, a.height),
                                 "fps": cap.set(cv2.CAP_PROP_FPS, float(pyav_ds.fps_value(a.fps)))}
            if a.backend == "msmf":
                s["format_-1"] = cap.set(cv2.CAP_PROP_FORMAT, -1)
            s["convert_rgb_0"] = cap.set(cv2.CAP_PROP_CONVERT_RGB, 0)
            s.update(got_fourcc=opencv_ds.fourcc_str(cap.get(cv2.CAP_PROP_FOURCC)),
                     got_w=cap.get(cv2.CAP_PROP_FRAME_WIDTH), got_h=cap.get(cv2.CAP_PROP_FRAME_HEIGHT),
                     got_fps=cap.get(cv2.CAP_PROP_FPS), got_convert_rgb=cap.get(cv2.CAP_PROP_CONVERT_RGB),
                     got_format=cap.get(cv2.CAP_PROP_FORMAT), backend_name=cap.getBackendName())
            return s

        done, sets, exc, ms = opencv_ds.bounded(do_sets, max(T, a.open_timeout_ms / 1000.0))
        timings["set_ms"] = ms
        if not done:
            hung = True
            stage = "set_format"
            err = {"stage": "set_format", "class": "timeout", "reason": "cap.set() did not return"}
        else:
            doc["sets"] = sets if exc is None else {"error": repr(exc)}
            saves = save_plan(pyav_ds.fps_value(a.fps), a.save_frames)
            fr = (out / "frames.raw").open("wb") if saves else None
            t_first = None
            while True:
                done, res, exc, ms = opencv_ds.bounded(cap.read, T)
                t = time.perf_counter_ns()
                if not done:
                    hung = True
                    stage = "first_frame" if not rows else "streaming"
                    err = {"stage": stage, "class": "timeout", "reason": "cap.read() did not return"}
                    break
                if not (res and res[0]):
                    stage = "first_frame" if not rows else "streaming"
                    err = {"stage": stage, "class": "other", "reason": repr(exc) if exc else "read() returned False"}
                    break
                frame = res[1]
                seq = len(rows)
                if t_first is None:
                    t_first = t
                    timings["first_frame_ms"] = timings["open_to_first_frame_ms"] = (t - t0) / 1e6
                row = {"seq": seq, "qpc_ns": t, "bytes": int(frame.nbytes), "shape": list(frame.shape),
                       "dtype": str(frame.dtype)}
                if fr is not None and seq in saves:
                    b = frame.tobytes()
                    row["raw_offset"] = fr.tell()
                    row["raw_len"] = len(b)
                    fr.write(b)
                rows.append(row)
                if (t - t_first) / 1e9 >= a.seconds:
                    break
            if fr is not None:
                fr.close()
        if not hung:
            done, _, exc, ms = opencv_ds.bounded(cap.release, T)
            timings["close_ms"] = ms
            if not done:
                hung = True
                err = err or {"stage": "close", "class": "timeout", "reason": "release() did not return"}
                stage = stage or "close"
    with (out / "frames.jsonl").open("w", encoding="utf-8", newline="\n") as fj:
        for r in rows:
            fj.write(json.dumps(r) + "\n")
    fps, dur = fps_of(rows, "qpc_ns")
    shapes = sorted({json.dumps(r["shape"]) for r in rows})
    doc.update({"delivered": {"fourcc_readback": (doc.get("sets") or {}).get("got_fourcc"),
                              "shapes": [json.loads(s) for s in shapes][:4],
                              "dtype": rows[0]["dtype"] if rows else None},
                "timings": timings, "frames": length_stats(rows), "fps_measured": fps, "duration_s": dur,
                "fps_basis": "qpc after read() returned", "stage_failed": stage, "timed_out": hung, "hung": hung,
                "unreleasable": hung, "ok": err is None and bool(rows), "error": err,
                "files": {"frames_jsonl": str(out / "frames.jsonl"),
                          "frames_raw": str(out / "frames.raw") if (out / "frames.raw").exists() else None}})
    rc = EXIT_TIMEOUT if hung else (EXIT_OK if doc["ok"] else EXIT_CAMERA)
    finish(doc, rc, out, hung)


# ============================================================================================================ main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("pyav", "ffmpeg", "opencv"):
        p = sub.add_parser(name)
        p.add_argument("--api", default=None, help="label recorded in the JSON (and seen by the suite's fault scan)")
        p.add_argument("--width", type=int, required=True)
        p.add_argument("--height", type=int, required=True)
        p.add_argument("--fps", required=True, help="30, 7.5, 15/2 or 10000000/333333")
        p.add_argument("--seconds", type=float, default=3.0)
        p.add_argument("--timeout-ms", type=int, default=5000)
        p.add_argument("--out-dir", required=True)
        p.add_argument("--save-frames", type=int, default=3)
        if name == "opencv":
            p.add_argument("--backend", choices=["dshow", "msmf"], required=True)
            p.add_argument("--index", type=int, required=True)
            p.add_argument("--expect-path", default=None)
            p.add_argument("--fourcc", required=True, help="YUY2, NV12, ...")
            p.add_argument("--open-timeout-ms", type=int, default=60000,
                           help="bound for VideoCapture() and the property sets (MSMF opens took 39-41 s on Gerald)")
        else:
            p.add_argument("--device", required=True, help="DirectShow DevicePath (\\\\?\\usb#...) or friendly name")
            p.add_argument("--pixel-format", required=True, help="FFmpeg pixel format: yuyv422, nv12, ...")
            p.add_argument("--rtbufsize", default="256M")
    try:
        a = ap.parse_args()
    except SystemExit as e:
        sys.exit(EXIT_USAGE if e.code not in (0, None) else 0)
    if a.cmd == "opencv":
        cmd_opencv(a)
    elif a.cmd == "ffmpeg":
        cmd_ffmpeg(a)
    else:
        try:
            import av as av_mod  # noqa: PLC0415
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"tool": "raw_ds", "ok": False, "untested": True,   # harness failure, not a result
                              "error": {"stage": "import", "message": repr(e), "class": "other",
                                        "reason": f"harness: PyAV import failed: {e!r}"}}))
            sys.exit(EXIT_CAMERA)
        pyav_ds._setup_logging(av_mod)
        cmd_pyav(a, av_mod)


if __name__ == "__main__":
    main()
