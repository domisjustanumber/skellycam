# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "opencv-contrib-python==5.0.0.93", "numpy==2.5.4"]
# ///
"""Record with the REAL skellycam app (a given checkout) through its public HTTP API, then verify the recording.

    uv run --python 3.12 --script skellycam_record.py --checkout <skellycam checkout> \
        --camera ds:<DirectShow DevicePath> [--camera mf:<MF symlink> | vidpid:1532:0e05 | name:<n> | index:N | id:XXXX]
        --width 1280 --height 720 --fps 30 --seconds 60 --out-dir <dir outside the repo> [--deadline-s S]
    uv run --python 3.12 --script skellycam_record.py --verify-only <recording dir> [--server-log <file>]

Prints ONE JSON object on stdout (also written to <out-dir>/summary.json). Run it under tools/camlock.py
(ctx.camcmd) like every camera command. Exit codes: 0 recorded and verified, 2 usage, 3 a camera could not be
resolved (nothing opened), 4 recording or verification failed, 5 a stage timed out / the server had to be killed.

What it does (skellycam read 2026-11-11 at 2992e64f9 and 7d06ba2e1; the API is the same at both):
1. ``uv run --no-sync python -c <launcher> <port>`` inside the checkout. The launcher sets
   skellycam.api.server_constants HOSTNAME/PORT/APP_URL to 127.0.0.1:<free port> and calls
   skellycam.__main__.entry_point() (the console-script entry point): the app's own lifecycle, logging, worker
   registry and signal handling. No app file is changed. (PORT is a constant, 53117, and main() calls
   kill_process_on_port(PORT) first: the free port keeps a running skellycam safe.) The server runs in a Job
   Object (common/procutil.Background), so the whole tree dies with the driver.
2. GET /health until {"alive": true}.
3. POST /skellycam/camera/detect?filter_virtual=false: cv2_enumerate_cameras.enumerate_cameras(CAP_DSHOW)
   (detect_cameras_devices.py:98; the backend is DSHOW on Windows, determine_backend.py:42). On Windows this
   reads DirectShow property bags only: CreateClassEnumerator + IMoniker::BindToStorage + Read FriendlyName /
   DevicePath (cv2_enumerate_cameras 1.4.0 _windows_backend.cpp:80-140), never BindToObject, so NO camera is
   opened. The index is the DirectShow enumeration order, which is what skellycam opens:
   cv2.VideoCapture(camera_index, CAP_DSHOW) (create_cv2_video_capture.py:37). Each --camera spec is resolved
   against that list (DevicePath exact, else the device-instance part shared by the MF symlink and the DS
   DevicePath) and ONLY the resolved cameras are put in the group, with skellycam's own camera_id.
4. POST /skellycam/camera/group/apply with exactly those cameras (MJPG capture fourcc, WxH, fps; exposure mode
   and value as given, default skellycam's MANUAL -7; writer fourcc left at skellycam's default unless given).
   The call returns when every camera opened and read its first frame (await_extracted_configs).
5. POST /skellycam/camera/group/all/record/start, wait --seconds (GET /health every 5 s), then
   GET /skellycam/camera/group/all/record/stop, which returns after finalisation (timestamps CSVs, skellycam's own
   validate_recording).
6. DELETE /skellycam/camera/group/close/all, GET /shutdown (on Windows the app TerminateProcess-es itself,
   shutdown.py:40), wait for the exit; kill the tree on timeout. Leftover processes in the job are counted.
7. Verify on disk: one video per camera (PyAV: codec, size, packet count, decode; OpenCV CAP_FFMPEG: opened,
   every frame decoded), per-camera timestamps CSVs (columns, rows = video frames, monotonic perf-counter
   timestamps, fps from the timestamps, frame-interval stats, connection-frame gaps), the multi-frame CSV, equal
   frame counts across cameras (skellycam records in lockstep), and the server log (ERROR / CRITICAL lines,
   tracebacks, camera failure lines, 0x8007001F).
8. ``fault_hints``: camera failures attributed to a camera from the log (skellycam logs "Failed to open camera
   <index>", "Failed to read frame from camera <index>", "Failed to create cv2.VideoCapture for camera <id>",
   "Failed to grab frame from camera <id>"), 0x8007001F, and a connect timeout (cameras that never logged
   "Camera <id> connected"). The driver never retries a camera; skellycam itself retries an open 5 times
   (create_cv2_video_capture.py:31).

Every HTTP call has a timeout and the whole run has a deadline (--deadline-s, default seconds + 600): each stage is
bounded so that closing the cameras and stopping the server always has time left.
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import hashlib
import json
import math
import os
import re
import shutil
import socket
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent            # suite/windows/helpers
SUITE_DIR = HERE.parents[1]                       # suite
if str(SUITE_DIR) not in sys.path:
    sys.path.insert(0, str(SUITE_DIR))
from common import procutil  # noqa: E402

TOOL = "skellycam_record"
API = "/skellycam"
KIYO_PRO_VIDPID = (0x1532, 0x0E05)
DSHOW_BACKEND_ID = 700
EXIT_OK, EXIT_USAGE, EXIT_UNRESOLVED, EXIT_FAIL, EXIT_TIMEOUT = 0, 2, 3, 4, 5
DEVICE_ERROR_HR = "0x8007001F"
CLEANUP_RESERVE_S = 90.0        # close groups (60) + /shutdown (10) + exit wait (20)
VERIFY_RESERVE_S = 60.0

LAUNCHER = ("import sys; port = int(sys.argv[1]); import skellycam.api.server_constants as sc; "
            "sc.HOSTNAME = '127.0.0.1'; sc.PORT = port; sc.APP_URL = 'http://127.0.0.1:%d' % port; "
            "from skellycam.__main__ import entry_point; entry_point()")
VERSION_PROBE = ("import json, platform, importlib.metadata as m, cv2, numpy; "
                 "d = {(x.metadata['Name'] or '').lower().replace('_', '-'): x.version for x in m.distributions()}; "
                 "out = {'python': platform.python_version(), 'opencv': cv2.__version__, 'numpy': numpy.__version__}; "
                 "out.update({k: d.get(k) for k in ('av', 'skellycam', 'opencv-contrib-python', 'fastapi', 'uvicorn', "
                 "'pydantic', 'polars', 'cv2-enumerate-cameras')}); print(json.dumps(out))")

#: per-camera timestamps CSV columns the verification needs (skellycam CAMERA_TIMESTAMPS_CSV_ROW_DTYPE)
REQUIRED_CAMERA_COLUMNS = ("recording_frame_number", "connection_frame_number", "timestamp.from_recording_start.sec",
                           "timestamp.utc.seconds", "timestamp.perf_counter_ns.ns", "from_previous.frame_duration.ms",
                           "from_previous.framerate.hz", "frame.pre_frame_grab.ns", "frame.post_frame_grab.ns")
#: multi-frame timestamps CSV columns (MULTI_FRAME_TIMESTAMP_CSV_ROW)
REQUIRED_MULTIFRAME_COLUMNS = ("multiframe_number", "timestamp.from_recording_start.sec", "timestamp.perf_counter_ns.ns",
                               "inter_camera.frame_grab_range.ms")
VIDEO_EXTS = (".mp4", ".avi", ".mkv", ".mov", ".webm")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
LEVEL_RE = re.compile(r"\|\s+(ERROR|CRITICAL)\s+\|")
HR_RE = re.compile(r"0x8007001f|-2147024865|8007001f", re.IGNORECASE)


# ============================================================================================================ utils
def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def log(msg: str) -> None:
    print(f"[{TOOL}] {_dt.datetime.now().strftime('%H:%M:%S')} {msg}", file=sys.stderr, flush=True)


class Deadline:
    def __init__(self, total_s: float) -> None:
        self.total_s = float(total_s)
        self.t_end = time.monotonic() + self.total_s

    def left(self) -> float:
        return self.t_end - time.monotonic()

    def bound(self, want_s: float, reserve_s: float = 0.0, floor_s: float = 1.0) -> float:
        """min(want, time left minus a reserve), never below floor (a call always gets a short timeout)."""
        return max(floor_s, min(float(want_s), self.left() - reserve_s))

    def expired(self, reserve_s: float = 0.0) -> bool:
        return self.left() <= reserve_s


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _pct(vals: list[float], q: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    k = (len(s) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] if lo == hi else s[lo] + (s[hi] - s[lo]) * (k - lo)


def _r(x: Any, n: int = 4) -> Any:
    return round(x, n) if isinstance(x, float) and math.isfinite(x) else (None if isinstance(x, float) else x)


def bounded_run(argv: list[str], timeout_s: float, cwd: str | os.PathLike | None = None,
                env: dict | None = None) -> dict:
    """A short non-camera command (git, version probe) with the whole-tree kill of procutil."""
    return procutil.run(argv, timeout_s=timeout_s, cwd=cwd, env=env)


def child_env() -> dict:
    env = dict(os.environ)
    for k in ("VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME", "UV_PROJECT_ENVIRONMENT", "PYTHONSTARTUP"):
        env.pop(k, None)
    env.update(PYTHONUNBUFFERED="1", PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    return env


# ============================================================================================================ HTTP
class Api:
    """Bounded JSON HTTP client; every call is recorded in ``calls``."""

    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        self.calls: list[dict] = []

    def call(self, method: str, path: str, body: Any = None, timeout_s: float = 10.0,
             quiet: bool = False) -> dict:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"} if data is not None else {})
        t0 = time.monotonic()
        rec: dict[str, Any] = {"method": method, "path": path, "status": None, "error": None,
                               "timeout_s": round(float(timeout_s), 1), "utc": utc_now()}
        raw = b""
        try:
            with urllib.request.urlopen(req, timeout=float(timeout_s)) as resp:
                rec["status"] = resp.status
                raw = resp.read()
        except urllib.error.HTTPError as e:
            rec["status"] = e.code
            rec["error"] = f"HTTP {e.code}"
            try:
                raw = e.read()
            except Exception:  # noqa: BLE001
                raw = b""
        except urllib.error.URLError as e:
            reason = e.reason
            rec["error"] = "timeout" if isinstance(reason, (TimeoutError, socket.timeout)) else f"URLError: {reason}"
        except (TimeoutError, socket.timeout):
            rec["error"] = "timeout"
        except (ConnectionError, OSError) as e:
            rec["error"] = f"{type(e).__name__}: {e}"
        rec["elapsed_s"] = round(time.monotonic() - t0, 3)
        payload: Any = None
        if raw:
            try:
                payload = json.loads(raw.decode("utf-8", errors="replace"))
            except ValueError:
                payload = raw.decode("utf-8", errors="replace")[:2000]
        if rec["error"] and isinstance(payload, dict) and payload.get("detail") is not None:
            rec["detail"] = str(payload.get("detail"))[:2000]
        self.calls.append(rec)
        if not quiet:
            log(f"{method} {path} -> {rec['status'] or rec['error']} in {rec['elapsed_s']}s")
        return {"ok": rec["error"] is None and rec["status"] is not None and 200 <= rec["status"] < 300,
                "status": rec["status"], "error": rec["error"], "json": payload, "elapsed_s": rec["elapsed_s"],
                "timed_out": rec["error"] == "timeout", "detail": rec.get("detail")}


# ============================================================================================================ identity
def instance_key(path: str | None) -> str | None:
    """The device-instance part of a Windows device interface path, shared by the MF symbolic link
    (KSCATEGORY_VIDEO_CAMERA) and the DirectShow DevicePath (KSCATEGORY_CAPTURE) of one video function:
    '\\\\?\\usb#vid_046d&pid_085c&mi_00#7&1a2b&0&0000#{65e8773d-...}\\global' -> 'usb#vid_046d&pid_085c&mi_00#7&1a2b&0&0000'."""
    if not path:
        return None
    s = str(path).strip().lower().replace("/", "\\")
    for pre in ("\\\\?\\", "\\??\\", "\\\\.\\"):
        if s.startswith(pre):
            s = s[len(pre):]
            break
    i = s.find("#{")
    if i >= 0:
        s = s[:i]
    return s.rstrip("\\#") or None


def parse_spec(spec: str) -> tuple[str, str]:
    """('ds'|'mf'|'path'|'vidpid'|'name'|'index'|'id', value). A bare integer is an index; a bare device path
    (starts with \\\\?\\ or contains '#vid_') is a path."""
    s = str(spec).strip()
    m = re.match(r"^(ds|mf|path|vidpid|name|index|id)[:=](.*)$", s, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1).lower(), m.group(2).strip()
    if re.fullmatch(r"\d+", s):
        return "index", s
    if s.startswith("\\\\") or "#vid_" in s.lower():
        return "path", s
    raise ValueError(f"camera spec {spec!r}: use ds:<DevicePath>, mf:<symlink>, vidpid:VVVV:PPPP, name:<name>, "
                     "index:N or id:XXXX")


def _is_kiyo_pro(det: dict) -> bool:
    return (det.get("vendor_id"), det.get("product_id")) == KIYO_PRO_VIDPID


def resolve_specs(specs: list[str], detected: list[dict]) -> tuple[list[dict], list[dict]]:
    """Map each --camera spec to one detected camera. Returns (resolved, errors). Pure: nothing is opened.
    resolved: {spec, kind, how, camera_id, camera_index, name, path, vendor_id, product_id, backend_id,
    backend_name, is_kiyo_pro}."""
    resolved: list[dict] = []
    errors: list[dict] = []
    for spec in specs:
        try:
            kind, val = parse_spec(spec)
        except ValueError as e:
            errors.append({"spec": spec, "error": str(e)})
            continue
        hits: list[dict] = []
        how = kind
        if kind in ("ds", "mf", "path"):
            exact = [d for d in detected if d.get("path") and str(d["path"]).lower() == val.lower()]
            if exact:
                hits, how = exact, "device_path_exact"
            else:
                ik = instance_key(val)
                hits = [d for d in detected if ik and instance_key(d.get("path")) == ik]
                how = "device_instance"
        elif kind == "vidpid":
            m = re.fullmatch(r"([0-9a-fA-F]{4})[:_ ]([0-9a-fA-F]{4})", val)
            if not m:
                errors.append({"spec": spec, "error": "vidpid must be VVVV:PPPP (hex)"})
                continue
            v, p = int(m.group(1), 16), int(m.group(2), 16)
            hits = [d for d in detected if d.get("vendor_id") == v and d.get("product_id") == p]
        elif kind == "name":
            hits = [d for d in detected if str(d.get("name") or "").lower() == val.lower()]
        elif kind == "index":
            try:
                n = int(val)
            except ValueError:
                errors.append({"spec": spec, "error": "index must be an integer"})
                continue
            hits = [d for d in detected if d.get("index") == n]
        elif kind == "id":
            hits = [d for d in detected if str(d.get("camera_id") or "").lower() == val.lower()]
        if not hits:
            errors.append({"spec": spec, "error": f"no detected camera matches ({kind})",
                           "detected": [{k: d.get(k) for k in ("index", "camera_id", "name", "path")} for d in detected]})
            continue
        if len(hits) > 1:
            errors.append({"spec": spec, "error": f"ambiguous: {len(hits)} detected cameras match ({kind})",
                           "matches": [{k: d.get(k) for k in ("index", "camera_id", "name")} for d in hits]})
            continue
        d = hits[0]
        resolved.append({"spec": spec, "kind": kind, "how": how, "camera_id": d.get("camera_id"),
                         "camera_index": d.get("index"), "name": d.get("name"), "path": d.get("path"),
                         "vendor_id": d.get("vendor_id"), "product_id": d.get("product_id"),
                         "backend_id": d.get("backend_id"), "backend_name": d.get("backend_name"),
                         "is_kiyo_pro": _is_kiyo_pro(d)})
    seen_idx: dict[Any, str] = {}
    seen_id: dict[Any, str] = {}
    for r in resolved:
        if r["camera_index"] in seen_idx:
            errors.append({"spec": r["spec"], "error": f"same camera as spec {seen_idx[r['camera_index']]!r} "
                                                       f"(index {r['camera_index']})"})
        elif r["camera_id"] in seen_id:
            errors.append({"spec": r["spec"], "error": f"skellycam camera_id {r['camera_id']} collides with spec "
                                                       f"{seen_id[r['camera_id']]!r}"})
        seen_idx.setdefault(r["camera_index"], r["spec"])
        seen_id.setdefault(r["camera_id"], r["spec"])
    return resolved, errors


def camera_configs_body(resolved: list[dict], width: int, height: int, fps: float, capture_fourcc: str,
                        exposure_mode: str, exposure: int, writer_fourcc: str | None) -> dict:
    """The /camera/group/apply body: {"camera_configs": {camera_id: CameraConfig fields}}."""
    cfgs = {}
    for r in resolved:
        c = {"camera_id": r["camera_id"], "camera_index": int(r["camera_index"]), "camera_name": r["name"] or
             f"Camera-{r['camera_id']}", "use_this_camera": True, "resolution": {"width": int(width),
                                                                                 "height": int(height)},
             "framerate": float(fps), "capture_fourcc": capture_fourcc, "exposure_mode": exposure_mode,
             "exposure": int(exposure), "rotation": -1}
        if writer_fourcc:
            c["writer_fourcc"] = writer_fourcc
        cfgs[r["camera_id"]] = c
    return {"camera_configs": cfgs}


# ============================================================================================================ CSVs
def _read_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        rd = csv.reader(f)
        header = [h.strip() for h in (next(rd, None) or [])]
        rows = [r for r in rd if r and any(x.strip() for x in r)]
    return header, rows


def _num(s: str, as_int: bool = False) -> float | int | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return int(s) if as_int else float(s)
    except ValueError:
        try:
            f = float(s)
            return int(f) if as_int and math.isfinite(f) else f
        except ValueError:
            return None


def _col(header: list[str], rows: list[list[str]], name: str, as_int: bool = False) -> tuple[list, int]:
    """(values, unparseable count) for one column; None entries for blanks / unparseable."""
    if name not in header:
        return [], 0
    i = header.index(name)
    vals, bad = [], 0
    for r in rows:
        v = _num(r[i], as_int) if i < len(r) else None
        if v is None or (isinstance(v, float) and not math.isfinite(v) and name != "from_previous.framerate.hz"
                         and name != "from_previous.frame_duration.ms"):
            bad += 1
        vals.append(v)
    return vals, bad


def interval_stats(ts_ns: list[int]) -> dict:
    """Frame-interval statistics from perf-counter timestamps (ns)."""
    out: dict[str, Any] = {"n": len(ts_ns)}
    if len(ts_ns) < 2:
        out.update(fps=None, duration_s=None)
        return out
    d = [(b - a) / 1e6 for a, b in zip(ts_ns, ts_ns[1:])]
    span_s = (ts_ns[-1] - ts_ns[0]) / 1e9
    pos = [x for x in d if x > 0]
    med = statistics.median(pos) if pos else None
    out.update(
        duration_s=_r(span_s, 4),
        fps=_r((len(ts_ns) - 1) / span_s, 4) if span_s > 0 else None,
        non_increasing_steps=sum(1 for x in d if x <= 0),
        interval_ms={"median": _r(med, 4), "mean": _r(statistics.fmean(d), 4), "p95": _r(_pct(d, 0.95), 4),
                     "p99": _r(_pct(d, 0.99), 4), "min": _r(min(d), 4), "max": _r(max(d), 4),
                     "std": _r(statistics.pstdev(d), 4)},
        long_intervals_gt_1p5x_median=sum(1 for x in d if med and x > 1.5 * med),
        short_intervals_lt_0p5x_median=sum(1 for x in d if med and 0 < x < 0.5 * med),
    )
    return out


def analyse_camera_csv(path: Path) -> dict:
    """One camera's timestamps CSV: columns, rows, frame numbering, monotonic timestamps, fps from timestamps."""
    out: dict[str, Any] = {"path": str(path), "exists": path.is_file(), "problems": []}
    if not out["exists"]:
        out["problems"].append("timestamps CSV missing")
        return out
    try:
        header, rows = _read_csv(path)
    except Exception as e:  # noqa: BLE001
        out["problems"].append(f"unreadable: {type(e).__name__}: {e}")
        return out
    out["columns"] = len(header)
    out["header_sha1"] = hashlib.sha1(",".join(header).encode()).hexdigest()[:12]
    out["columns_missing"] = [c for c in REQUIRED_CAMERA_COLUMNS if c not in header]
    out["rows"] = len(rows)
    if out["columns_missing"]:
        out["problems"].append(f"columns missing: {out['columns_missing']}")
    short = sum(1 for r in rows if len(r) != len(header))
    if short:
        out["ragged_rows"] = short
        out["problems"].append(f"{short} rows with a column count != header")
    fn, bad_fn = _col(header, rows, "recording_frame_number", as_int=True)
    if fn:
        out["frame_numbers_contiguous"] = all(isinstance(v, int) for v in fn) and fn == list(range(fn[0], fn[0] + len(fn)))
        out["first_recording_frame_number"] = fn[0]
        if not out["frame_numbers_contiguous"]:
            out["problems"].append("recording_frame_number not contiguous")
    conn, _ = _col(header, rows, "connection_frame_number", as_int=True)
    if conn and all(isinstance(v, int) for v in conn):
        steps = [b - a for a, b in zip(conn, conn[1:])]
        out["connection_frame_gaps"] = sum(1 for s in steps if s != 1)
        out["connection_frames_skipped"] = sum(s - 1 for s in steps if s > 1)
    perf, bad_perf = _col(header, rows, "timestamp.perf_counter_ns.ns", as_int=True)
    if perf:
        good = [int(v) for v in perf if isinstance(v, (int, float))]
        if bad_perf:
            out["problems"].append(f"{bad_perf} unparseable perf_counter timestamps")
        st = interval_stats(good)
        out["timestamps"] = st
        out["monotonic"] = bad_perf == 0 and st.get("non_increasing_steps", 0) == 0
        out["fps_from_timestamps"] = st.get("fps")
        if not out["monotonic"]:
            out["problems"].append(f"perf_counter timestamps not strictly increasing "
                                   f"({st.get('non_increasing_steps')} steps, {bad_perf} unparseable)")
    utc, bad_utc = _col(header, rows, "timestamp.utc.seconds")
    if utc:
        u = [v for v in utc if isinstance(v, float) and math.isfinite(v)]
        out["utc_decreasing_steps"] = sum(1 for a, b in zip(u, u[1:]) if b < a)
        out["utc_first"] = _r(u[0], 3) if u else None
        if out["utc_decreasing_steps"] or bad_utc:
            out["problems"].append(f"utc timestamps: {out['utc_decreasing_steps']} decreasing steps, {bad_utc} bad")
    rs, _ = _col(header, rows, "timestamp.from_recording_start.sec")
    if rs and isinstance(rs[0], float):
        out["first_frame_from_recording_start_s"] = _r(rs[0], 4)
    return out


def analyse_multiframe_csv(path: Path) -> dict:
    out: dict[str, Any] = {"path": str(path), "exists": path.is_file(), "problems": []}
    if not out["exists"]:
        out["problems"].append("multi-frame timestamps CSV missing")
        return out
    try:
        header, rows = _read_csv(path)
    except Exception as e:  # noqa: BLE001
        out["problems"].append(f"unreadable: {type(e).__name__}: {e}")
        return out
    out["columns"] = len(header)
    out["header_sha1"] = hashlib.sha1(",".join(header).encode()).hexdigest()[:12]
    out["columns_missing"] = [c for c in REQUIRED_MULTIFRAME_COLUMNS if c not in header]
    out["rows"] = len(rows)
    if out["columns_missing"]:
        out["problems"].append(f"columns missing: {out['columns_missing']}")
    mf, _ = _col(header, rows, "multiframe_number", as_int=True)
    if mf:
        out["multiframe_numbers_contiguous"] = all(isinstance(v, int) for v in mf) and mf == list(range(mf[0], mf[0] + len(mf)))
        if not out["multiframe_numbers_contiguous"]:
            out["problems"].append("multiframe_number not contiguous")
    perf, bad = _col(header, rows, "timestamp.perf_counter_ns.ns")
    if perf:
        good = [int(v) for v in perf if isinstance(v, float) and math.isfinite(v)]
        st = interval_stats(good)
        out["timestamps"] = st
        out["fps_from_timestamps"] = st.get("fps")
        out["monotonic"] = bad == 0 and st.get("non_increasing_steps", 0) == 0
        if not out["monotonic"]:
            out["problems"].append("multi-frame timestamps not strictly increasing")
    rng, _ = _col(header, rows, "inter_camera.frame_grab_range.ms")
    r = [v for v in rng if isinstance(v, float) and math.isfinite(v)]
    if r:
        out["inter_camera_grab_range_ms"] = {"median": _r(statistics.median(r), 4), "p95": _r(_pct(r, 0.95), 4),
                                             "max": _r(max(r), 4), "mean": _r(statistics.fmean(r), 4)}
    return out


# ============================================================================================================ media
def probe_pyav(path: Path, dl: Deadline | None = None) -> dict:
    """PyAV: container/codec facts, packet count (demux, every packet), first and last frame decoded."""
    out: dict[str, Any] = {"ok": False}
    try:
        import av  # noqa: PLC0415 - lazy: the offline tests run without PyAV
    except Exception as e:  # noqa: BLE001
        return {"ok": None, "unavailable": f"PyAV not importable: {e!r}"}
    out["pyav_version"] = getattr(av, "__version__", None)
    try:
        with av.open(str(path)) as c:
            out["container"] = c.format.name
            vs = c.streams.video
            if not vs:
                out["error"] = "no video stream"
                return out
            s = vs[0]
            cc = s.codec_context
            out.update(codec=cc.name, pix_fmt=getattr(cc, "pix_fmt", None), width=cc.width, height=cc.height,
                       average_rate=_r(float(s.average_rate), 4) if s.average_rate else None,
                       header_frames=int(s.frames or 0),
                       duration_s=_r(float(s.duration * s.time_base), 4) if s.duration and s.time_base else None,
                       bit_rate=c.bit_rate)
            n = 0
            keyframes = 0
            first = None
            truncated = False
            for pkt in c.demux(s):
                if pkt.size == 0:
                    continue
                n += 1
                if pkt.is_keyframe:
                    keyframes += 1
                if first is None:
                    try:
                        frames = pkt.decode()
                        if frames:
                            f0 = frames[0]
                            first = {"width": f0.width, "height": f0.height, "format": f0.format.name}
                    except Exception as e:  # noqa: BLE001
                        first = {"error": f"{type(e).__name__}: {e}"}
                if dl is not None and n % 500 == 0 and dl.expired():
                    truncated = True
                    break
            out.update(packets=n, keyframes=keyframes, first_frame=first, truncated_by_deadline=truncated)
            out["ok"] = n > 0 and isinstance(first, dict) and "error" not in first
    except Exception as e:  # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def probe_opencv(path: Path, decode_all: bool = True, dl: Deadline | None = None) -> dict:
    """OpenCV through CAP_FFMPEG (a file backend only: no camera API is involved): open, props, decode every frame."""
    out: dict[str, Any] = {"ok": False}
    try:
        import cv2  # noqa: PLC0415 - lazy
    except Exception as e:  # noqa: BLE001
        return {"ok": None, "unavailable": f"OpenCV not importable: {e!r}"}
    out["opencv_version"] = cv2.__version__
    cap = None
    try:
        cap = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG)
        out["opened"] = bool(cap.isOpened())
        if not out["opened"]:
            out["error"] = "VideoCapture did not open the file"
            return out
        fcc = int(cap.get(cv2.CAP_PROP_FOURCC))
        out.update(fourcc="".join(chr((fcc >> 8 * i) & 0xFF) for i in range(4)).strip("\x00"),
                   frame_count_prop=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), fps_prop=_r(cap.get(cv2.CAP_PROP_FPS), 4),
                   width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        n = 0
        shape = None
        truncated = False
        while True:
            ok, img = cap.read()
            if not ok or img is None:
                break
            n += 1
            if shape is None:
                shape = list(img.shape)
            if not decode_all:
                break
            if dl is not None and n % 300 == 0 and dl.expired():
                truncated = True
                break
        out.update(decoded_frames=n if decode_all else None, first_frame_shape=shape, truncated_by_deadline=truncated)
        out["ok"] = shape is not None
    except Exception as e:  # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {e}"
    finally:
        if cap is not None:
            try:
                cap.release()
            except Exception:  # noqa: BLE001
                pass
    return out


# ============================================================================================================ verify
VIDEO_NAME_RE = re.compile(r"^(?P<rec>.+)\.id-(?P<cid>[^.]+)\.idx-(?P<idx>\d+)$")


def cameras_from_recording(rec_dir: Path, rec_name: str) -> list[dict]:
    """The recorded cameras: <name>_info.json camera_configs, else the video file names."""
    info = rec_dir / f"{rec_name}_info.json"
    if info.is_file():
        try:
            d = json.loads(info.read_text(encoding="utf-8"))
            cams = [{"camera_id": str(k), "camera_index": v.get("camera_index"), "name": v.get("camera_name")}
                    for k, v in (d.get("camera_configs") or {}).items()]
            if cams:
                return cams
        except (OSError, ValueError):
            pass
    out = []
    vd = rec_dir / "synchronized_videos"
    for p in sorted(vd.glob("*")) if vd.is_dir() else []:
        m = VIDEO_NAME_RE.match(p.stem)
        if p.suffix.lower() in VIDEO_EXTS and m:
            out.append({"camera_id": m.group("cid"), "camera_index": int(m.group("idx")), "name": None})
    return out


def find_video(rec_dir: Path, rec_name: str, cam: dict) -> tuple[Path | None, list[str]]:
    vd = rec_dir / "synchronized_videos"
    stem = f"{rec_name}.id-{cam['camera_id']}.idx-{cam['camera_index']}"
    hits = sorted(p for p in vd.glob(f"{glob_escape(stem)}.*") if p.suffix.lower() in VIDEO_EXTS) if vd.is_dir() else []
    return (hits[0] if hits else None), [str(h) for h in hits]


def glob_escape(s: str) -> str:
    return re.sub(r"([\[\]*?])", r"[\1]", s)


def verify_recording(rec_dir: Path, rec_name: str, cameras: list[dict] | None = None, media: str = "full",
                     dl: Deadline | None = None) -> dict:
    """Check the recording on disk. media: 'full' (PyAV packets + OpenCV decode of every frame), 'ends' (PyAV
    packets + OpenCV first frame), 'none' (files and CSVs only)."""
    rec_dir = Path(rec_dir)
    out: dict[str, Any] = {"recording_dir": str(rec_dir), "recording_name": rec_name, "media_check": media,
                           "cameras": {}, "problems": []}
    if not rec_dir.is_dir():
        out["problems"].append("recording directory missing")
        out["ok"] = False
        return out
    cams = cameras if cameras else cameras_from_recording(rec_dir, rec_name)
    out["camera_source"] = "request" if cameras else "recording files"
    if not cams:
        out["problems"].append("no cameras found in the recording")
    info = rec_dir / f"{rec_name}_info.json"
    out["recording_info_json"] = info.is_file()
    if not info.is_file():
        out["problems"].append("recording info JSON missing")
    ts_dir = rec_dir / "synchronized_videos" / "timestamps"
    stats = ts_dir / f"{rec_name}_stats.json"
    out["stats_json"] = stats.is_file()
    if stats.is_file():
        try:
            out["stats"] = json.loads(stats.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            out["problems"].append(f"stats JSON unreadable: {e}")
    frames: dict[str, int | None] = {}
    for cam in cams:
        cid = str(cam["camera_id"])
        c: dict[str, Any] = {"camera_index": cam.get("camera_index"), "name": cam.get("name"), "problems": []}
        vp, all_hits = find_video(rec_dir, rec_name, cam)
        if len(all_hits) > 1:
            c["problems"].append(f"{len(all_hits)} video files for this camera")
        if vp is None:
            c["problems"].append("video file missing")
            c["video"] = None
        else:
            c["video"] = {"path": str(vp), "ext": vp.suffix.lower().lstrip("."), "size_bytes": vp.stat().st_size}
            if c["video"]["size_bytes"] == 0:
                c["problems"].append("video file is empty")
            if media != "none":
                c["pyav"] = probe_pyav(vp, dl)
                c["opencv"] = probe_opencv(vp, decode_all=(media == "full"), dl=dl)
                for lib in ("pyav", "opencv"):
                    r = c[lib]
                    if r.get("ok") is None:
                        c["problems"].append(f"{lib} unavailable: {r.get('unavailable')}")
                    elif not r.get("ok"):
                        c["problems"].append(f"{lib} could not read the video: {r.get('error') or 'no frame'}")
        csvp = ts_dir / "camera_timestamps" / f"{rec_name}.camera{cid}.timestamps.csv"
        c["csv"] = analyse_camera_csv(csvp)
        c["problems"] += [f"csv: {p}" for p in c["csv"]["problems"]]
        n_csv = c["csv"].get("rows")
        n_pkt = (c.get("pyav") or {}).get("packets")
        n_dec = (c.get("opencv") or {}).get("decoded_frames")
        n = n_pkt if isinstance(n_pkt, int) else n_csv
        c["frames"] = {"csv_rows": n_csv, "pyav_packets": n_pkt, "opencv_decoded": n_dec, "count": n}
        if isinstance(n_pkt, int) and isinstance(n_csv, int) and n_pkt != n_csv:
            c["problems"].append(f"video has {n_pkt} packets but the CSV {n_csv} rows")
        if isinstance(n_dec, int) and isinstance(n_csv, int) and n_dec != n_csv \
                and not (c.get("opencv") or {}).get("truncated_by_deadline"):
            c["problems"].append(f"OpenCV decoded {n_dec} frames but the CSV has {n_csv} rows")
        if n == 0:
            c["problems"].append("0 frames")
        c["fps_from_timestamps"] = c["csv"].get("fps_from_timestamps")
        c["ok"] = not c["problems"]
        frames[cid] = n
        out["cameras"][cid] = c
    counts = [v for v in frames.values() if isinstance(v, int)]
    out["frame_counts"] = frames
    out["frame_counts_equal"] = bool(counts) and len(set(counts)) == 1 and len(counts) == len(frames)
    if frames and not out["frame_counts_equal"]:
        out["problems"].append(f"frame counts differ across cameras (lockstep expects equal): {frames}")
    mf = analyse_multiframe_csv(ts_dir / f"{rec_name}_timestamps.csv")
    out["multiframe_csv"] = mf
    out["problems"] += [f"multi-frame csv: {p}" for p in mf["problems"]]
    if counts and isinstance(mf.get("rows"), int) and out["frame_counts_equal"] and mf["rows"] != counts[0]:
        out["problems"].append(f"multi-frame CSV has {mf['rows']} rows, cameras {counts[0]} frames")
    for cid, c in out["cameras"].items():
        out["problems"] += [f"camera {cid}: {p}" for p in c["problems"]]
    out["frames"] = counts[0] if out["frame_counts_equal"] else None
    out["ok"] = not out["problems"]
    return out


# ============================================================================================================ server log
def _norm_msg(line: str) -> str:
    """A log message with numbers / ids / paths blanked, for comparing error kinds across runs."""
    msg = line.split(" | ")[0].replace("└>>", "").strip()
    msg = re.sub(r"0x[0-9a-fA-F]+", "0x#", msg)
    msg = re.sub(r"\b[0-9a-f]{4}\b", "#", msg)
    msg = re.sub(r"\d+(\.\d+)?", "#", msg)
    msg = re.sub(r"[A-Za-z]:\\[^ ]*|/[^ ]+/[^ ]*", "<path>", msg)
    return msg[:200]


def scan_server_log(text: str, max_lines: int = 40) -> dict:
    """ERROR / CRITICAL lines, tracebacks, logging failures and 0x8007001F in the server's console output."""
    lines = [ANSI_RE.sub("", ln).rstrip() for ln in (text or "").splitlines()]
    errors, kinds = [], {}
    tracebacks = 0
    logging_errors = 0
    hr_lines: list[dict] = []
    codec_lines: list[str] = []
    for i, ln in enumerate(lines):
        if LEVEL_RE.search(ln):
            errors.append({"line": i + 1, "text": ln[:400]})
            k = _norm_msg(ln)
            kinds[k] = kinds.get(k, 0) + 1
        if ln.startswith("Traceback (most recent call last)"):
            tracebacks += 1
        if ln.startswith("--- Logging error ---"):
            logging_errors += 1
        if HR_RE.search(ln):
            hr_lines.append({"line": i + 1, "text": ln[:400]})
        m = CODEC_RE.search(ln)
        if m:
            codec_lines.append(m.group(0)[:200])
    return {"lines": len(lines), "error_lines": len(errors), "errors": errors[:max_lines], "error_kinds": kinds,
            "tracebacks": tracebacks, "logging_errors": logging_errors, "hr_0x8007001F_lines": hr_lines[:max_lines],
            "writer_codec_lines": sorted(set(codec_lines))[:max_lines]}


#: skellycam's writer-codec resolution (fourcc_codec_helpers.resolve_writer_fourcc) messages
CODEC_RE = re.compile(r"(Requested video codec '[^']+' is not available[^|]*|Using fallback video codec: \S+|"
                      r"No web-compatible codec available[^|]*)")


#: (regex, key kind 'index'|'id', code, stage) in priority order: the first hint per camera wins
FAULT_PATTERNS = (
    (re.compile(r"Failed to open camera (\d+)\b"), "index", "open_failed", "open"),
    (re.compile(r"Failed to read frame from camera (\d+)\b"), "index", "first_frame_failed", "first_frame"),
    (re.compile(r"Failed to create cv2\.VideoCapture for camera (\w+):\s*(.*)"), "id", "setup_failed", "setup"),
    (re.compile(r"Camera (\w+) shutdown unexpectedly"), "id", "camera_closed", "stream"),
    (re.compile(r"Camera (\w+) closed mid-recording"), "id", "camera_closed", "stream"),
    (re.compile(r"Failed to grab frame from camera ?(\w+)"), "id", "grab_failed", "grab"),
    (re.compile(r"Failed to retrieve frame from camera ?(\w+)"), "id", "retrieve_failed", "retrieve"),
)
CONNECTED_RE = re.compile(r"Camera (\w+) (?:connected|ready!)")


def fault_hints(log_text: str, resolved: list[dict], connect: dict | None = None) -> list[dict]:
    """Camera failures attributed to the resolved cameras (first hint per camera), from the server log and the
    connect call. A sibling aborting because another camera failed ('Failed to initialize camera_group_shm') is not
    a hint. 0x8007001F on a line naming the camera upgrades its code; on no camera it is an unattributed hint."""
    by_idx = {r.get("camera_index"): r for r in resolved}
    by_id = {str(r.get("camera_id")): r for r in resolved}
    lines = [ANSI_RE.sub("", ln) for ln in (log_text or "").splitlines()]
    hints: dict[str, dict] = {}
    unattributed: list[dict] = []

    def add(r: dict, code: str, stage: str, line_no: int, text: str) -> None:
        k = str(r["camera_id"])
        h = hints.get(k)
        if h is None:
            hints[k] = {"camera_id": r["camera_id"], "camera_index": r.get("camera_index"), "spec": r.get("spec"),
                        "name": r.get("name"), "is_kiyo_pro": r.get("is_kiyo_pro"), "code": code, "stage": stage,
                        "line": line_no, "evidence": text.strip()[:400]}
        elif code == DEVICE_ERROR_HR and h["code"] != DEVICE_ERROR_HR:
            h.update(code=code, hr_line=line_no)

    for i, ln in enumerate(lines):
        for rx, kind, code, stage in FAULT_PATTERNS:
            m = rx.search(ln)
            if not m:
                continue
            if code == "setup_failed" and "camera_group_shm" in (m.group(2) or ""):
                continue
            key = m.group(1)
            r = by_idx.get(int(key)) if kind == "index" and key.isdigit() else by_id.get(key)
            if r is not None:
                add(r, code, stage, i + 1, ln)
            break
        if HR_RE.search(ln):
            named = [r for r in resolved if re.search(rf"camera\s*{re.escape(str(r['camera_id']))}\b", ln, re.I)
                     or re.search(rf"camera\s*{r.get('camera_index')}\b", ln, re.I)]
            if len(named) == 1:
                add(named[0], DEVICE_ERROR_HR, "stream", i + 1, ln)
            else:
                unattributed.append({"code": DEVICE_ERROR_HR, "line": i + 1, "evidence": ln.strip()[:400]})
    connect = connect or {}
    if connect and not connect.get("ok") and not hints:
        # no camera named in the log: the cameras that never logged 'connected' are the suspects
        seen = {m.group(1) for ln in lines for m in [CONNECTED_RE.search(ln)] if m}
        silent = [r for r in resolved if str(r["camera_id"]) not in seen]
        code = "connect_timeout" if connect.get("timed_out") else "start_failed"
        if len(silent) < len(resolved) or connect.get("timed_out"):
            for r in silent:
                if str(r["camera_id"]) not in hints:
                    add(r, code, "first_frame_timeout" if connect.get("timed_out") else "connect", 0,
                        f"group/apply {connect.get('error') or connect.get('status')}: camera never logged "
                        f"'Camera {r['camera_id']} connected'")
    out = list(hints.values())
    for u in unattributed[:5]:
        out.append({"camera_id": None, "camera_index": None, "spec": None, "is_kiyo_pro": None, "stage": "unknown",
                    **u})
    return out


# ============================================================================================================ server
def _job_counts(job: Any) -> dict | None:
    """{active, total} processes in the server's Job Object (Windows), else None."""
    if job is None or not getattr(job, "ok", False) or not getattr(job, "handle", None):
        return None
    try:
        import ctypes  # noqa: PLC0415
        from ctypes import wintypes  # noqa: PLC0415

        class _Acct(ctypes.Structure):
            _fields_ = [("TotalUserTime", ctypes.c_longlong), ("TotalKernelTime", ctypes.c_longlong),
                        ("ThisPeriodTotalUserTime", ctypes.c_longlong),
                        ("ThisPeriodTotalKernelTime", ctypes.c_longlong), ("TotalPageFaultCount", wintypes.DWORD),
                        ("TotalProcesses", wintypes.DWORD), ("ActiveProcesses", wintypes.DWORD),
                        ("TotalTerminatedProcesses", wintypes.DWORD)]

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                                                  ctypes.c_void_p]
        a = _Acct()
        if not k32.QueryInformationJobObject(job.handle, 1, ctypes.byref(a), ctypes.sizeof(a), None):
            return None
        return {"active": int(a.ActiveProcesses), "total": int(a.TotalProcesses)}
    except Exception:  # noqa: BLE001
        return None


def server_argv(checkout: Path, port: int, override: list[str] | None, sync: bool) -> list[str]:
    if override:
        return [a.replace("{port}", str(port)) for a in override]
    uv = shutil.which("uv") or "uv"
    return [uv, "run", "--frozen" if sync else "--no-sync", "python", "-c", LAUNCHER, str(port)]


def checkout_info(checkout: Path, probe_versions: bool, sync: bool, timeout_s: float) -> dict:
    out: dict[str, Any] = {"path": str(checkout)}
    g = bounded_run(["git", "-C", str(checkout), "rev-parse", "HEAD"], timeout_s=20)
    out["commit"] = (g.get("stdout") or "").strip() or None
    g = bounded_run(["git", "-C", str(checkout), "status", "--porcelain", "--untracked-files=no"], timeout_s=20)
    out["dirty"] = bool((g.get("stdout") or "").strip()) if g.get("rc") == 0 else None
    pv = checkout / ".python-version"
    out["python_version_file"] = pv.read_text(encoding="utf-8").strip() if pv.is_file() else None
    if probe_versions:
        uv = shutil.which("uv") or "uv"
        r = bounded_run([uv, "run", "--frozen" if sync else "--no-sync", "python", "-c", VERSION_PROBE],
                        timeout_s=timeout_s, cwd=checkout, env=child_env())
        try:
            out["versions"] = json.loads((r.get("stdout") or "").strip().splitlines()[-1])
        except (ValueError, IndexError):
            out["versions"] = None
            out["versions_error"] = {"rc": r.get("rc"), "timed_out": r.get("timed_out"),
                                     "stderr": (r.get("stderr") or "")[-800:]}
    return out


# ============================================================================================================ record
def record(args: argparse.Namespace) -> tuple[dict, int]:
    t0 = time.monotonic()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    rec_root = out_dir / "recording"
    rec_root.mkdir(parents=True, exist_ok=True)
    rec_name = args.recording_name or f"skellycam_record_{_dt.datetime.now().strftime('%Y%m%dT%H%M%S')}"
    dl = Deadline(args.deadline_s if args.deadline_s else args.seconds + 600.0)
    checkout = Path(args.checkout).resolve()
    summ: dict[str, Any] = {
        "tool": TOOL, "ok": False, "utc_started": utc_now(), "out_dir": str(out_dir),
        "request": {"checkout": str(checkout), "cameras": list(args.camera), "width": args.width,
                    "height": args.height, "fps": args.fps, "seconds": args.seconds, "warmup_s": args.warmup_s,
                    "capture_fourcc": args.capture_fourcc, "exposure_mode": args.exposure_mode,
                    "exposure": args.exposure, "writer_fourcc": args.writer_fourcc or "(skellycam default)",
                    "deadline_s": dl.total_s, "media_check": args.media_check},
        "stage_failed": None, "error": None, "phases_s": {}, "resolution": [], "fault_hints": [],
    }
    override = json.loads(args.server_cmd_json) if args.server_cmd_json else None
    if not checkout.is_dir() or (not override and not (checkout / "pyproject.toml").is_file()):
        summ["stage_failed"] = "preflight"
        summ["error"] = {"stage": "preflight", "class": "usage", "message": f"not a skellycam checkout: {checkout}"}
        return finish(summ, t0, out_dir), EXIT_USAGE
    if not override and not args.sync and not (checkout / ".venv").is_dir():
        summ["stage_failed"] = "preflight"
        summ["error"] = {"stage": "preflight", "class": "usage",
                         "message": f"{checkout} has no .venv: run `uv sync` there first (or pass --sync)"}
        return finish(summ, t0, out_dir), EXIT_USAGE
    summ["checkout"] = checkout_info(checkout, probe_versions=not override and not args.no_version_probe,
                                     sync=args.sync, timeout_s=dl.bound(90, CLEANUP_RESERVE_S + VERIFY_RESERVE_S))

    port = free_port()
    base = f"http://127.0.0.1:{port}"
    api = Api(base)
    argv = server_argv(checkout, port, override, args.sync)
    stdout_log, stderr_log = out_dir / "server_stdout.log", out_dir / "server_stderr.log"
    summ["server"] = {"port": port, "argv": argv, "cwd": str(checkout), "stdout_log": str(stdout_log),
                      "stderr_log": str(stderr_log)}
    log(f"starting skellycam server in {checkout} on {base}")
    bg = procutil.Background(argv, stdout_path=stdout_log, stderr_path=stderr_log, cwd=checkout,
                             env=child_env()).start()
    summ["server"]["pid"] = bg.pid
    rc = EXIT_FAIL
    group_maybe = False
    resolved: list[dict] = []
    connect: dict | None = None
    timed_out_stage = None
    reserve = CLEANUP_RESERVE_S + VERIFY_RESERVE_S

    def fail(stage: str, cls: str, message: str, timed_out: bool = False) -> None:
        nonlocal timed_out_stage
        if summ["stage_failed"] is None:
            summ["stage_failed"] = stage
            summ["error"] = {"stage": stage, "class": cls, "message": message[:2000]}
        if timed_out and timed_out_stage is None:
            timed_out_stage = stage

    try:
        if bg.spawn_error:
            fail("server_start", "spawn_error", bg.spawn_error)
            raise _Stop()
        # ---- health
        t = time.monotonic()
        want = time.monotonic() + dl.bound(args.start_timeout_s, reserve)
        healthy = False
        while time.monotonic() < want:
            if bg.poll() is not None:
                fail("server_start", "server_exited", f"server exited with rc {bg.poll()} before /health answered")
                raise _Stop()
            h = api.call("GET", "/health", timeout_s=2.0, quiet=True)
            if h["ok"] and isinstance(h["json"], dict) and h["json"].get("alive"):
                healthy = True
                summ["server"]["app_pid"] = h["json"].get("pid")
                break
            time.sleep(0.5)
        summ["phases_s"]["start_to_health"] = round(time.monotonic() - t, 3)
        api.calls = [c for c in api.calls if c["path"] != "/health"] + \
            ([{"method": "GET", "path": "/health", "status": 200, "error": None, "polls": True,
               "elapsed_s": summ["phases_s"]["start_to_health"]}] if healthy else [])
        if not healthy:
            fail("server_start", "timeout", f"/health did not answer within {args.start_timeout_s}s", True)
            raise _Stop()
        log(f"server healthy after {summ['phases_s']['start_to_health']}s")
        # ---- detect (enumeration only: DirectShow property bags, no camera opened)
        d = api.call("POST", f"{API}/camera/detect?filter_virtual=false",
                     timeout_s=dl.bound(args.detect_timeout_s, reserve))
        summ["phases_s"]["detect"] = d["elapsed_s"]
        if not d["ok"]:
            fail("detect", "timeout" if d["timed_out"] else "api_error",
                 f"camera detect failed: {d['error']} {d.get('detail') or ''}", d["timed_out"])
            raise _Stop()
        detected = list((d["json"] or {}).get("cameras") or [])
        summ["detected"] = detected
        resolved, errs = resolve_specs(list(args.camera), detected)
        summ["resolution"] = resolved
        backends = {r.get("backend_id") for r in resolved}
        if sys.platform == "win32" and resolved and backends != {DSHOW_BACKEND_ID}:
            summ.setdefault("warnings", []).append(f"detected backend ids {sorted(map(str, backends))}, expected "
                                                   f"DSHOW ({DSHOW_BACKEND_ID})")
        if errs or not resolved:
            summ["resolution_errors"] = errs
            fail("resolve", "unresolved", f"{len(errs)} camera spec(s) not resolved: "
                                          + "; ".join(f"{e['spec']}: {e['error']}" for e in errs[:4]))
            rc = EXIT_UNRESOLVED
            raise _Stop()
        log("resolved: " + ", ".join(f"{r['spec'][:40]} -> index {r['camera_index']} id {r['camera_id']}"
                                     for r in resolved))
        # ---- connect exactly these cameras
        body = camera_configs_body(resolved, args.width, args.height, args.fps, args.capture_fourcc,
                                   args.exposure_mode, args.exposure, args.writer_fourcc)
        summ["group_request"] = body
        group_maybe = True
        connect = api.call("POST", f"{API}/camera/group/apply", body=body,
                           timeout_s=dl.bound(args.connect_timeout_s, reserve))
        summ["phases_s"]["connect"] = connect["elapsed_s"]
        if not connect["ok"]:
            fail("connect", "timeout" if connect["timed_out"] else "api_error",
                 f"group/apply failed: {connect['error']} {connect.get('detail') or ''}", connect["timed_out"])
            raise _Stop()
        g = connect["json"] or {}
        summ["group"] = {"group_id": g.get("group_id"), "extracted_configs": g.get("camera_configs")}
        # ---- warm-up, record
        if args.warmup_s > 0:
            time.sleep(min(args.warmup_s, max(0.0, dl.left() - reserve - args.seconds)))
        rec_body = {"recording_name": rec_name, "recording_directory": str(rec_root), "mic_device_index": -1}
        s = api.call("POST", f"{API}/camera/group/all/record/start", body=rec_body,
                     timeout_s=dl.bound(args.record_start_timeout_s, reserve))
        summ["phases_s"]["record_start_call"] = s["elapsed_s"]
        if not s["ok"]:
            fail("record_start", "timeout" if s["timed_out"] else "api_error",
                 f"record/start failed: {s['error']} {s.get('detail') or ''}", s["timed_out"])
            raise _Stop()
        t_rec = time.monotonic()
        rec_end = t_rec + min(float(args.seconds), max(1.0, dl.left() - reserve - args.stop_timeout_s * 0.5))
        health_fail = 0
        while time.monotonic() < rec_end:
            time.sleep(min(5.0, max(0.05, rec_end - time.monotonic())))
            if bg.poll() is not None:
                fail("recording", "server_exited", f"server exited with rc {bg.poll()} during the recording")
                raise _Stop()
            if time.monotonic() < rec_end - 1.0:
                h = api.call("GET", "/health", timeout_s=5.0, quiet=True)
                health_fail = 0 if h["ok"] else health_fail + 1
                if health_fail >= 3:
                    fail("recording", "server_unresponsive", "/health failed 3 times in a row during the recording")
                    raise _Stop()
        summ["phases_s"]["recorded_wall"] = round(time.monotonic() - t_rec, 3)
        api.calls = [c for c in api.calls if c["path"] != "/health" or c.get("polls") or c.get("error")]
        # ---- stop (returns after finalisation)
        st = api.call("GET", f"{API}/camera/group/all/record/stop",
                      timeout_s=dl.bound(args.stop_timeout_s, CLEANUP_RESERVE_S + 15))
        summ["phases_s"]["stop_and_finalise"] = st["elapsed_s"]
        summ["stop_response"] = st["json"]
        if not st["ok"]:
            fail("stop", "timeout" if st["timed_out"] else "api_error",
                 f"record/stop failed: {st['error']} {st.get('detail') or ''}", st["timed_out"])
            raise _Stop()
    except _Stop:
        pass
    except KeyboardInterrupt:
        fail("interrupted", "interrupted", "Ctrl-C")
    except Exception as e:  # noqa: BLE001 - the server must still be stopped
        fail("driver", "exception", f"{type(e).__name__}: {e}")
    finally:
        summ["server"].update(stop_server(bg, api, group_maybe, dl))
        summ["api_calls"] = api.calls

    # ---- verify on disk (also after a failure: whatever was written is evidence)
    rec_dir = rec_root / rec_name
    expected = [{"camera_id": r["camera_id"], "camera_index": r["camera_index"], "name": r["name"]}
                for r in resolved] if connect and connect.get("ok") else None
    if rec_dir.is_dir():
        t = time.monotonic()
        summ["verify"] = verify_recording(rec_dir, rec_name, cameras=expected, media=args.media_check, dl=dl)
        summ["phases_s"]["verify"] = round(time.monotonic() - t, 3)
        if summ["stage_failed"] is None and not summ["verify"]["ok"]:
            fail("verify", "verify_failed", "; ".join(summ["verify"]["problems"][:6]))
    elif summ["stage_failed"] is None:
        fail("verify", "verify_failed", f"recording directory missing: {rec_dir}")
    summ["recording_dir"] = str(rec_dir) if rec_dir.is_dir() else None

    log_text = ""
    for p in (stdout_log, stderr_log):
        try:
            log_text += Path(p).read_text(encoding="utf-8", errors="replace") + "\n"
        except OSError:
            pass
    summ["server_log"] = scan_server_log(log_text)
    summ["fault_hints"] = fault_hints(log_text, resolved, connect)
    if any(h.get("code") == DEVICE_ERROR_HR for h in summ["fault_hints"]) and summ["error"]:
        summ["error"].update({"hr": DEVICE_ERROR_HR, "class": "device_error"})
    summ["ok"] = summ["stage_failed"] is None
    if summ["ok"]:
        rc = EXIT_OK
    elif timed_out_stage or summ["server"].get("killed"):
        rc = EXIT_TIMEOUT
    elif rc != EXIT_UNRESOLVED:
        rc = EXIT_FAIL
    summ["exit_code"] = rc
    return finish(summ, t0, out_dir), rc


class _Stop(Exception):
    pass


def stop_server(bg: procutil.Background, api: Api, group_maybe: bool, dl: Deadline) -> dict:
    """Close the camera group(s), ask the app to shut down, wait; kill the tree on timeout. Never raises."""
    out: dict[str, Any] = {"close_groups": None, "shutdown_call": None, "exit": None, "killed": False}
    t0 = time.monotonic()
    alive = bg.p is not None and bg.poll() is None
    if alive and group_maybe:
        c = api.call("DELETE", f"{API}/camera/group/close/all", timeout_s=dl.bound(60.0, 30.0, floor_s=10.0))
        out["close_groups"] = {k: c[k] for k in ("ok", "status", "error", "elapsed_s")}
    if bg.p is not None and bg.poll() is None:
        s = api.call("GET", "/shutdown", timeout_s=dl.bound(10.0, 20.0, floor_s=5.0))
        # on Windows the app TerminateProcess-es itself: a reset connection is the normal answer
        out["shutdown_call"] = {k: s[k] for k in ("ok", "status", "error", "elapsed_s")}
        if s["error"] and ("10054" in s["error"] or "ConnectionReset" in s["error"]):
            out["shutdown_call"]["note"] = "expected: the app TerminateProcess-es itself on Windows (exit code 15)"
    rc = bg.wait(dl.bound(20.0, 0.0, floor_s=8.0)) if bg.p is not None else None
    out["exit"] = "exited" if rc is not None else "timeout"
    jc = _job_counts(bg.job)
    if rc is not None and jc and jc["active"] > 0:
        # camera worker processes notice the missing heartbeat and exit on their own: give them a moment
        t = time.monotonic() + min(10.0, max(2.0, dl.left()))
        while time.monotonic() < t and jc and jc["active"] > 0:
            time.sleep(0.5)
            jc = _job_counts(bg.job)
    out["job_processes_after_exit"] = jc
    out["leftover_processes"] = jc["active"] if jc else None
    res = bg.stop(0.5 if rc is not None else 2.0)
    out.update(rc=res.get("rc"), killed=bool(res.get("killed")), kill_method=res.get("kill_method"),
               clean=rc is not None and not res.get("killed") and not (jc and jc["active"] > 0),
               stop_elapsed_s=round(time.monotonic() - t0, 3))
    if out["killed"] or (jc and jc["active"] > 0):
        log(f"server tree killed ({res.get('kill_method')}); leftover processes {out['leftover_processes']}")
    else:
        log(f"server exited rc={res.get('rc')} in {out['stop_elapsed_s']}s")
    return out


def finish(summ: dict, t0: float, out_dir: Path | None) -> dict:
    summ["utc_finished"] = utc_now()
    summ["elapsed_s"] = round(time.monotonic() - t0, 3)
    if out_dir is not None:
        try:
            (out_dir / "summary.json").write_text(json.dumps(summ, indent=1, default=str), encoding="utf-8")
        except OSError:
            pass
    return summ


# ============================================================================================================ main
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--checkout", help="skellycam checkout (git worktree) with a synced .venv")
    ap.add_argument("--camera", action="append", default=[],
                    help="camera spec (repeat): ds:<DevicePath> | mf:<symlink> | vidpid:VVVV:PPPP | name:<n> | "
                         "index:N | id:XXXX")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--seconds", type=float, default=60.0, help="recording length")
    ap.add_argument("--out-dir", dest="out_dir", help="output folder (OUTSIDE the repo: videos show the room)")
    ap.add_argument("--recording-name", dest="recording_name", default=None)
    ap.add_argument("--deadline-s", dest="deadline_s", type=float, default=None,
                    help="whole-run deadline (default seconds + 600)")
    ap.add_argument("--warmup-s", dest="warmup_s", type=float, default=3.0, help="streaming before record/start")
    ap.add_argument("--capture-fourcc", dest="capture_fourcc", default="MJPG")
    ap.add_argument("--exposure-mode", dest="exposure_mode", default="MANUAL", choices=("MANUAL", "AUTO", "RECOMMEND"))
    ap.add_argument("--exposure", type=int, default=-7, help="skellycam DEFAULT_EXPOSURE")
    ap.add_argument("--writer-fourcc", dest="writer_fourcc", default=None,
                    help="skellycam writer fourcc (default: skellycam's own default)")
    ap.add_argument("--media-check", dest="media_check", default="full", choices=("full", "ends", "none"))
    ap.add_argument("--start-timeout-s", dest="start_timeout_s", type=float, default=150.0)
    ap.add_argument("--detect-timeout-s", dest="detect_timeout_s", type=float, default=45.0)
    ap.add_argument("--connect-timeout-s", dest="connect_timeout_s", type=float, default=150.0)
    ap.add_argument("--record-start-timeout-s", dest="record_start_timeout_s", type=float, default=30.0)
    ap.add_argument("--stop-timeout-s", dest="stop_timeout_s", type=float, default=240.0)
    ap.add_argument("--sync", action="store_true", help="uv run --frozen (may install) instead of --no-sync")
    ap.add_argument("--no-version-probe", dest="no_version_probe", action="store_true")
    ap.add_argument("--verify-only", dest="verify_only", default=None, help="verify an existing recording folder")
    ap.add_argument("--server-log", dest="server_log", action="append", default=[], help="with --verify-only")
    ap.add_argument("--server-cmd-json", dest="server_cmd_json", default=None, help=argparse.SUPPRESS)  # tests
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    if args.verify_only:
        t0 = time.monotonic()
        rd = Path(args.verify_only).resolve()
        name = args.recording_name or rd.name
        dl = Deadline(args.deadline_s or 900.0)
        summ: dict[str, Any] = {"tool": TOOL, "mode": "verify_only", "utc_started": utc_now()}
        summ["verify"] = verify_recording(rd, name, media=args.media_check, dl=dl)
        if args.server_log:
            txt = "\n".join(Path(p).read_text(encoding="utf-8", errors="replace") for p in args.server_log
                            if Path(p).is_file())
            summ["server_log"] = scan_server_log(txt)
        summ["ok"] = bool(summ["verify"]["ok"])
        finish(summ, t0, None)
        print(json.dumps(summ, default=str))
        return EXIT_OK if summ["ok"] else EXIT_FAIL
    if not args.checkout or not args.out_dir or not args.camera:
        print(json.dumps({"tool": TOOL, "ok": False, "error": {"stage": "usage", "class": "usage",
                                                               "message": "--checkout, --out-dir and at least one "
                                                                          "--camera are required"}}))
        return EXIT_USAGE
    for spec in args.camera:
        try:
            parse_spec(spec)
        except ValueError as e:
            print(json.dumps({"tool": TOOL, "ok": False, "error": {"stage": "usage", "class": "usage",
                                                                   "message": str(e)}}))
            return EXIT_USAGE
    summ, rc = record(args)
    print(json.dumps(summ, default=str))
    return rc


if __name__ == "__main__":
    sys.exit(main())
