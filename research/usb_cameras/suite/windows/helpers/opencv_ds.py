# /// script
# requires-python = ">=3.10"
# dependencies = ["opencv-contrib-python==4.12.*", "numpy"]
# ///
"""OpenCV CAP_DSHOW open/close cycle baseline for W-CYC (skellycam's capture path today).

    uv run --script opencv_ds.py cycle --index N --width 1280 --height 720 --fps 30 --cycles K --frames N
        --timeout-ms 5000 --out D [--alt-width W2 --alt-height H2 --alt-fps F2] [--gap-ms G]
        [--expect-path <DS DevicePath>] [--set-order skellycam|size-first|skellycam-full]
        [--skellycam-framerate F] [--skellycam-exposure -7|none]

OpenCV opens DirectShow devices by INDEX only. The caller resolves the index from the DirectShow device order
(``wincam list`` -> ds[].index, which enumerates CLSID_VideoInputDeviceCategory like OpenCV's videoInput does)
immediately before the run and passes ``--expect-path`` so the result records which device the index was meant
to be. OpenCV gives no way to read the device path back, so the opened size/fps/fourcc are recorded and a wrong
mapping shows up as a mismatch. Indices changed between runs on Gerald (REPORT finding 23).

Each cycle: VideoCapture(index, CAP_DSHOW) -> set FOURCC MJPG, width, height, fps (skellycam order:
create_cv2_video_capture sets FOURCC first) -> read() first frame -> N more reads -> release(). OpenCV decodes the
MJPEG to BGR (no JPEG bytes; REPORT finding 3); this is a reliability baseline only.

``--set-order skellycam-full`` models skellycam's REAL open (skellycam/core/camera/opencv/opencv_helpers/
create_cv2_video_capture.py + opencv_apply_config.py, read 2026-11-06; analysis cyc_kiyo V2.4 / N5):
  create step: set FOURCC MJPG, W, H, FPS (only when the config framerate > 0: ``--skellycam-framerate``, default
  the requested fps; skellycam's DEFAULT_FRAMERATE is -1, which skips it), CAP_PROP_BUFFERSIZE = 1, read();
  apply step (apply_camera_configuration, prior_config=None): exposure (MANUAL: CAP_PROP_AUTO_EXPOSURE = 1 then
  CAP_PROP_EXPOSURE = -7, skellycam's DEFAULT_EXPOSURE; ``--skellycam-exposure none`` skips it), W, H, FPS SKIPPED
  (should_apply_framerate = False), FOURCC MJPG last; then read() the first frame of the configured stream and N
  more. ``open_to_first_frame_ms`` is then the time from VideoCapture() to the first frame AFTER the apply step
  (what a skellycam user waits for); the create-step frame is ``create_first_frame_ms``. The exposure set changes
  the camera's exposure control: the caller (W-CYC) reads it before and restores it after the run.

Row checks (analysis cyc_kiyo B3 / V2.5): ``streamed_ok`` = opened, first frame, closed (the old ``ok``);
``size_mismatch`` (frame shape != requested), ``format_mismatch`` (CAP_PROP_FOURCC read back after the last set is
not MJPG), ``fps_mismatch`` (measured rate < 0.9 x requested; None when not measurable); ``ok`` = streamed_ok and
none of the mismatches (the camera delivered what was asked).

Every OpenCV call runs on one worker thread (OpenCV DSHOW crashes when calls hop threads) with the --timeout-ms bound; a call that does not return is recorded
(timed_out) and the process exits 5 after writing, because the stuck call keeps the DirectShow graph.
Exit codes: 0 all cycles ok (as requested), 2 usage, 4 some cycle failed or was not as requested, 5 a call hung.
Output: D/cycles.jsonl (one row per cycle, same field names as wincam / pyav_ds) and D/summary.json (also stdout).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

TOOL_VERSION = "opencv_ds 1.1 (2026-11-06)"
FPS_TOL = 0.9   # fps_mismatch when measured < FPS_TOL x requested


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


class Worker:
    """One thread that runs every OpenCV call in order. OpenCV's DirectShow backend crashed the process
    (exit -1, no output) when VideoCapture was created on one thread and read on another, so all calls of
    the run go through this single thread; the main thread only waits on it with the timeout."""

    def __init__(self) -> None:
        import queue
        self.q: "queue.Queue" = queue.Queue()
        self.th = threading.Thread(target=self._loop, daemon=True)
        self.th.start()

    def _loop(self) -> None:
        while True:
            fn, box, ev = self.q.get()
            try:
                box["v"] = fn()
            except BaseException as e:  # noqa: BLE001
                box["e"] = e
            ev.set()

    def call(self, fn: Callable[[], Any], timeout_s: float) -> tuple[bool, Any, BaseException | None, float]:
        """Returns (finished, value, exception, elapsed_ms)."""
        box: dict[str, Any] = {}
        ev = threading.Event()
        t0 = time.perf_counter()
        self.q.put((fn, box, ev))
        done = ev.wait(timeout_s)
        return done, box.get("v"), box.get("e"), (time.perf_counter() - t0) * 1000.0


WORKER: Worker | None = None


def bounded(fn: Callable[[], Any], timeout_s: float) -> tuple[bool, Any, BaseException | None, float]:
    global WORKER
    if WORKER is None:
        WORKER = Worker()
    return WORKER.call(fn, timeout_s)


def fourcc_str(v: float) -> str:
    v = int(v)
    return "".join(chr((v >> (8 * i)) & 0xFF) for i in range(4))


def one_cycle(cv2, a: argparse.Namespace, i: int, w: int, h: int, fps: float) -> dict[str, Any]:
    """One cycle; every exit path goes through evaluate_row (idempotent)."""
    return evaluate_row(_one_cycle(cv2, a, i, w, h, fps), w, h, fps)


def _one_cycle(cv2, a: argparse.Namespace, i: int, w: int, h: int, fps: float) -> dict[str, Any]:
    T = a.timeout_ms / 1000.0
    row: dict[str, Any] = {"i": i, "mode": f"MJPG {w}x{h}@{fps:g}", "ok": False, "stage_failed": None,
                           "error": None, "error_class": None, "timed_out": False, "open_ms": None,
                           "set_ms": None, "first_frame_ms": None, "open_to_first_frame_ms": None, "frames": 0,
                           "close_ms": None, "unreleasable": False, "in_use_by_other": None, "utc": utc_now(),
                           "hung": False}
    t_start = time.perf_counter()
    done, cap, exc, ms = bounded(lambda: cv2.VideoCapture(a.index, cv2.CAP_DSHOW), T)
    row["open_ms"] = ms
    if not done:
        row.update(stage_failed="open", timed_out=True, hung=True, unreleasable=True, error_class="timeout",
                   error="VideoCapture() did not return")
        return row
    if exc is not None or cap is None or not cap.isOpened():
        row.update(stage_failed="open", error_class="other",
                   error=repr(exc) if exc else "isOpened() is False (OpenCV hides the HRESULT in its log)")
        if cap is not None:
            bounded(cap.release, T)
        return row

    full = a.set_order == "skellycam-full"
    sk_fps = fps if getattr(a, "skellycam_framerate", None) is None else a.skellycam_framerate

    def readback(s: dict) -> dict:
        s["got_fourcc"] = fourcc_str(cap.get(cv2.CAP_PROP_FOURCC))
        s["got_w"] = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        s["got_h"] = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        s["got_fps"] = cap.get(cv2.CAP_PROP_FPS)
        return s

    def do_sets() -> dict:
        mj = cv2.VideoWriter_fourcc(*"MJPG")
        s: dict[str, Any] = {"order": a.set_order}
        if a.set_order in ("skellycam", "skellycam-full"):
            s["fourcc"] = cap.set(cv2.CAP_PROP_FOURCC, mj)
        s["w"] = cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        s["h"] = cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        if not full:
            s["fps"] = cap.set(cv2.CAP_PROP_FPS, fps)
        elif sk_fps and sk_fps > 0:
            s["fps"] = cap.set(cv2.CAP_PROP_FPS, sk_fps)
        else:
            s["fps"] = "skipped (config framerate <= 0)"
        if a.set_order == "size-first":
            s["fourcc"] = cap.set(cv2.CAP_PROP_FOURCC, mj)
        if full:
            s["buffersize"] = cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            s["got_buffersize"] = cap.get(cv2.CAP_PROP_BUFFERSIZE)
        return readback(s)

    def do_apply() -> dict:
        """skellycam apply_camera_configuration(prior_config=None): exposure, W, H, (FPS skipped), FOURCC last."""
        mj = cv2.VideoWriter_fourcc(*"MJPG")
        s: dict[str, Any] = {"step": "apply_camera_configuration"}
        if a.skellycam_exposure != "none":
            s["exposure_before"] = cap.get(cv2.CAP_PROP_EXPOSURE)
            s["auto_exposure"] = cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)   # skellycam MANUAL_EXPOSURE_SETTING
            s["exposure"] = cap.set(cv2.CAP_PROP_EXPOSURE, float(a.skellycam_exposure))
        s["w"] = cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        s["h"] = cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        s["fps"] = "skipped (should_apply_framerate = False)"
        s["fourcc"] = cap.set(cv2.CAP_PROP_FOURCC, mj)
        s["got_exposure"] = cap.get(cv2.CAP_PROP_EXPOSURE)
        return readback(s)

    done, sets, exc, ms = bounded(do_sets, T)
    row["set_ms"] = ms
    if not done:
        row.update(stage_failed="set_format", timed_out=True, hung=True, unreleasable=True, error_class="timeout",
                   error="cap.set() did not return")
        return row
    row["sets"] = sets if exc is None else {"error": repr(exc)}
    if full:
        # create step: the read() skellycam does before apply_camera_configuration
        done, res, exc, ms = bounded(cap.read, T)
        if not done:
            row.update(stage_failed="create_read", timed_out=True, hung=True, unreleasable=True,
                       error_class="timeout", error="cap.read() (create step) did not return")
            return row
        row["create_read_ms"] = ms
        if not (res and res[0]):
            row.update(stage_failed="create_read", error_class="other",
                       error=repr(exc) if exc else "read() (create step) returned False")
        else:
            row["create_first_frame_ms"] = (time.perf_counter() - t_start) * 1000.0
            row["create_frame_shape"] = list(res[1].shape) if res[1] is not None else None
            done, aps, exc, ms = bounded(do_apply, T)
            row["apply_ms"] = ms
            if not done:
                row.update(stage_failed="apply_config", timed_out=True, hung=True, unreleasable=True,
                           error_class="timeout", error="apply step cap.set() did not return")
                return row
            row["apply"] = aps if exc is None else {"error": repr(exc)}
        if row["stage_failed"] is not None:
            done, _, exc, ms = bounded(cap.release, T)
            row["close_ms"] = ms
            if not done:
                row.update(timed_out=True, hung=True, unreleasable=True)
            return row
    shape = None
    for k in range(a.frames + 1):
        done, res, exc, ms = bounded(cap.read, T)
        if not done:
            row.update(stage_failed="first_frame" if k == 0 else "streaming", timed_out=True, hung=True,
                       unreleasable=True, error_class="timeout", error="cap.read() did not return")
            return row
        ok = bool(res and res[0])
        if not ok:
            row.update(stage_failed="first_frame" if k == 0 else "streaming", error_class="other",
                       error=repr(exc) if exc else "read() returned False")
            break
        if k == 0:
            row["first_frame_ms"] = (time.perf_counter() - t_start) * 1000.0
            row["open_to_first_frame_ms"] = row["first_frame_ms"]
            row["t_first"] = time.perf_counter()
            fr = res[1]
            shape = list(fr.shape) if fr is not None else None
        row["frames"] = k + 1
    t_first = row.pop("t_first", None)
    if t_first is not None and row["frames"] > 1:
        dur = time.perf_counter() - t_first
        row["fps_measured"] = (row["frames"] - 1) / dur if dur > 0 else None
    row["frame_shape"] = shape
    done, _, exc, ms = bounded(cap.release, T)
    row["close_ms"] = ms
    if not done:
        row.update(timed_out=True, hung=True, unreleasable=True, error_class=row["error_class"] or "timeout",
                   stage_failed=row["stage_failed"] or "close", error=row["error"] or "release() did not return")
        return row
    return evaluate_row(row, w, h, fps)


def evaluate_row(row: dict[str, Any], w: int, h: int, fps: float) -> dict[str, Any]:
    """streamed_ok / size_mismatch / format_mismatch / fps_mismatch / ok for one cycle row (pure; tested offline).
    The format read back after the LAST set step counts (the apply step for skellycam-full)."""
    row["streamed_ok"] = row.get("stage_failed") is None and (row.get("frames") or 0) >= 1
    shape = row.get("frame_shape")
    row["size_mismatch"] = bool(shape) and list(shape)[:2] != [h, w]
    last = row.get("apply") if isinstance(row.get("apply"), dict) and "got_fourcc" in row["apply"] else \
        (row.get("sets") or {})
    got = last.get("got_fourcc")
    row["final_fourcc"] = got
    row["final_size"] = [shape[1], shape[0]] if shape and len(shape) >= 2 else None
    row["format_mismatch"] = None if not row["streamed_ok"] or got is None else str(got).strip("\x00 ") != "MJPG"
    fm = row.get("fps_measured")
    row["fps_requested"] = fps
    row["fps_mismatch"] = None if (fm is None or not fps or fps <= 0) else fm < FPS_TOL * fps
    row["ok"] = bool(row["streamed_ok"] and not row["size_mismatch"] and row["format_mismatch"] is not True
                     and row["fps_mismatch"] is not True)
    return row


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("cycle")
    p.add_argument("--index", type=int, required=True)
    p.add_argument("--expect-path", default=None)
    p.add_argument("--width", type=int, required=True)
    p.add_argument("--height", type=int, required=True)
    p.add_argument("--fps", type=float, required=True)
    p.add_argument("--cycles", type=int, required=True)
    p.add_argument("--frames", type=int, default=30)
    p.add_argument("--timeout-ms", type=int, default=5000)
    p.add_argument("--out", required=True)
    p.add_argument("--alt-width", type=int)
    p.add_argument("--alt-height", type=int)
    p.add_argument("--alt-fps", type=float)
    p.add_argument("--gap-ms", type=int, default=0)
    p.add_argument("--set-order", choices=["skellycam", "size-first", "skellycam-full"], default="skellycam")
    p.add_argument("--skellycam-framerate", dest="skellycam_framerate", type=float, default=None,
                   help="skellycam-full: the config framerate (default: --fps; <= 0 skips the create-step FPS set)")
    p.add_argument("--skellycam-exposure", dest="skellycam_exposure", default="-7",
                   help="skellycam-full: manual exposure value of the apply step (skellycam default -7) or 'none'")
    try:
        a = ap.parse_args()
    except SystemExit as e:
        sys.exit(2 if e.code not in (0, None) else 0)
    import cv2  # noqa: PLC0415
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    modes = [(a.width, a.height, a.fps)]
    if a.alt_width and a.alt_height:
        modes.append((a.alt_width, a.alt_height, a.alt_fps or a.fps))
    doc: dict[str, Any] = {"tool": "opencv_ds", "version": TOOL_VERSION, "subcommand": "cycle",
                           "utc_started": utc_now(), "pid": os.getpid(), "argv": sys.argv,
                           "hostname": socket.gethostname(), "api": "opencv_ds", "opencv": cv2.__version__,
                           "index": a.index, "expect_path": a.expect_path, "timeout_ms": a.timeout_ms,
                           "requested": {"modes": [f"MJPG {m[0]}x{m[1]}@{m[2]:g}" for m in modes],
                                         "cycles": a.cycles, "frames_per_cycle": a.frames, "gap_ms": a.gap_ms,
                                         "set_order": a.set_order,
                                         "skellycam_framerate": a.skellycam_framerate,
                                         "skellycam_exposure": a.skellycam_exposure}}
    rows = []
    hung = False
    with (out / "cycles.jsonl").open("w", encoding="utf-8", newline="\n") as cj:
        for i in range(a.cycles):
            w, h, f = modes[i % len(modes)]
            r = one_cycle(cv2, a, i, w, h, f)
            rows.append(r)
            cj.write(json.dumps(r, default=str) + "\n")
            cj.flush()
            if r["hung"]:
                hung = True
                break
            if a.gap_ms and i + 1 < a.cycles:
                time.sleep(a.gap_ms / 1000.0)
    ok = sum(1 for r in rows if r["ok"])
    streamed = sum(1 for r in rows if r.get("streamed_ok"))
    ff = sorted(r["open_to_first_frame_ms"] for r in rows
                if r.get("streamed_ok") and r["open_to_first_frame_ms"] is not None)
    fps_m = sorted(r["fps_measured"] for r in rows if r.get("fps_measured") is not None)
    doc["summary"] = {"cycles_requested": a.cycles, "cycles_run": len(rows), "ok": ok, "failed": len(rows) - ok,
                      "streamed_ok": streamed,
                      "format_mismatches": sum(1 for r in rows if r.get("format_mismatch") is True),
                      "fps_mismatches": sum(1 for r in rows if r.get("fps_mismatch") is True),
                      "final_fourccs": sorted({str(r.get("final_fourcc")) for r in rows if r.get("streamed_ok")}),
                      "final_sizes": sorted({str(r.get("final_size")) for r in rows if r.get("streamed_ok")}),
                      "fps_measured_p50": fps_m[len(fps_m) // 2] if fps_m else None,
                      "timeouts": sum(1 for r in rows if r["timed_out"]),
                      "success_rate": ok / len(rows) if rows else None,
                      "open_to_first_frame_ms_p50": ff[len(ff) // 2] if ff else None,
                      "first_frame_within_2s": sum(1 for x in ff if x <= 2000.0),
                      "size_mismatches": sum(1 for r in rows if r.get("size_mismatch")),
                      "unreleasable": hung, "stopped_early": len(rows) < a.cycles}
    doc["files"] = {"cycles_jsonl": str(out / "cycles.jsonl")}
    rc = 5 if hung else (0 if ok == len(rows) else 4)
    doc["utc_finished"] = utc_now()
    doc["exit_code"] = rc
    (out / "summary.json").write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    sys.stdout.write(json.dumps(doc, default=str) + "\n")
    sys.stdout.flush()
    if hung:
        os._exit(rc)
    sys.exit(rc)


if __name__ == "__main__":
    main()
