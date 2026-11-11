# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2"]
# ///
"""PyAV / FFmpeg DirectShow device and option listing with per-call QPC timestamps and a hang bound (W-PYAV-LIST).

    uv run --script pyav_list.py pyav_list_devices   [--repeats N] [--gap-s G] [--timeout-s T]
    uv run --script pyav_list.py pyav_list_options   --device <DS DevicePath> [...]
    uv run --script pyav_list.py ffmpeg_list_devices [--ffmpeg PATH] [...]
    uv run --script pyav_list.py ffmpeg_list_options --device <DS DevicePath> [--ffmpeg PATH] [...]

Prints one JSON object: {"method", "device", "versions", "calls": [{"i", "t_start_ns", "t_end_ns", "elapsed_ms",
"hung", "error", "log_tail", "devices" | "option_lines"}], "hung"}. ``t_*_ns`` are time.perf_counter_ns() (QPC on
Windows: the clock wincam's ``qpc_ns`` uses), so the suite can line each call up with another process's frames.

What the calls touch (FFmpeg 9.0.2, the version PyAV 19.0.2 bundles and the CLI on Gerald): ``list_devices``
enumerates CLSID_VideoInputDeviceCategory and, to print each device's media types, binds every capture filter
(IMoniker::BindToObject) and walks its pins: a KS filter open per camera, no graph, no Run. ``list_options`` binds
the named device's filter and prints its pin caps. Neither starts a stream by design; W-PYAV-LIST measures whether
that holds.

A call runs on a worker thread (PyAV) or as a child process (CLI) with the --timeout-s bound. A PyAV call that does
not return is recorded (``hung``) and the process exits 5 after printing, because the stuck FFmpeg call keeps the
filter; the CLI child is killed. FFmpeg's log goes through its C callback to fd 2, redirected to a temp file
(pyav_ds._StderrCapture: PyAV's Python log callback can deadlock), and the part of it each call wrote is kept.
Exit: 0 every call returned, 4 some call failed to list anything, 5 a call hung.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (str(HERE.parents[1]), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

OPT_LINE = re.compile(r"(vcodec|pixel_format)=\S+\s+min s=")
LOG_TAIL = 6000


def parse_devices(text: str) -> list[dict]:
    """Video devices from a dshow list_devices log (enum_apis' parser: name + alternative name)."""
    import enum_apis  # noqa: PLC0415
    return enum_apis._parse_dshow_lines(text)


def option_lines(text: str) -> int:
    return len(OPT_LINE.findall(text or ""))


def summarise(method: str, text: str) -> dict:
    if method.endswith("list_devices"):
        devs = parse_devices(text)
        return {"devices": devs, "n_devices": len(devs)}
    return {"option_lines": option_lines(text),
            "could_not": [ln.strip()[:200] for ln in (text or "").splitlines() if "Could not" in ln][:5]}


# ------------------------------------------------------------------------------------------------ PyAV
class _Log:
    """FFmpeg log capture through pyav_ds (fd 2 -> temp file); the text each call added."""

    def __init__(self, av_mod) -> None:
        import pyav_ds  # noqa: PLC0415
        self.cap = pyav_ds.LOGS
        pyav_ds._setup_logging(av_mod)

    def offset(self) -> int:
        return self.cap.offset()

    def since(self, off: int) -> str:
        if not self.cap.path:
            return ""
        self.cap.flush()
        try:
            with open(self.cap.path, "rb") as f:
                f.seek(off)
                return f.read(400_000).decode("utf-8", "replace")
        except OSError:
            return ""

    def stop(self) -> None:
        self.cap.stop()


def pyav_call(av_mod, log: _Log, method: str, device: str | None, timeout_s: float) -> dict:
    import pyav_ds  # noqa: PLC0415
    if method == "pyav_list_devices":
        url, opts = "dummy", {"list_devices": "true"}
    else:
        url, opts = pyav_ds.device_url(device or ""), {"list_options": "true"}
    box: dict = {}

    def work() -> None:
        try:
            c = av_mod.open(url, format="dshow", options=opts)
            try:
                c.close()
            except Exception:  # noqa: BLE001
                pass
            box["returned"] = "opened"
        except Exception as e:  # noqa: BLE001 - list_* always ends with an error ("Immediate exit requested")
            box["returned"] = f"{type(e).__name__}: {e}"[:300]

    off = log.offset()
    t0 = time.perf_counter_ns()
    th = threading.Thread(target=work, daemon=True)
    th.start()
    th.join(timeout_s)
    t1 = time.perf_counter_ns()
    hung = th.is_alive()
    text = log.since(off)
    rec = {"t_start_ns": t0, "t_end_ns": t1, "elapsed_ms": round((t1 - t0) / 1e6, 2), "hung": hung,
           "returned": box.get("returned"), "log_tail": text[-LOG_TAIL:]}
    rec.update(summarise(method, text))
    return rec


# ------------------------------------------------------------------------------------------------ CLI
def ffmpeg_call(exe: str, method: str, device: str | None, timeout_s: float) -> dict:
    import pyav_ds  # noqa: PLC0415
    if method == "ffmpeg_list_devices":
        argv = [exe, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"]
    else:
        argv = [exe, "-hide_banner", "-list_options", "true", "-f", "dshow", "-i", pyav_ds.device_url(device or "")]
    t0 = time.perf_counter_ns()
    hung, rc, text = False, None, ""
    try:
        p = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL)
        try:
            _, err = p.communicate(timeout=timeout_s)
            rc = p.returncode
        except subprocess.TimeoutExpired:
            hung = True
            p.kill()
            try:
                _, err = p.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                err = b""
        text = (err or b"").decode("utf-8", "replace")
        error = None
    except OSError as e:
        error = repr(e)
    t1 = time.perf_counter_ns()
    rec = {"t_start_ns": t0, "t_end_ns": t1, "elapsed_ms": round((t1 - t0) / 1e6, 2), "hung": hung, "rc": rc,
           "error": error, "log_tail": text[-LOG_TAIL:], "argv": argv}
    rec.update(summarise(method, text))
    return rec


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("method", choices=["pyav_list_devices", "pyav_list_options", "ffmpeg_list_devices",
                                       "ffmpeg_list_options"])
    ap.add_argument("--device", default=None)
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--gap-s", type=float, default=1.5)
    ap.add_argument("--timeout-s", type=float, default=20.0)
    ap.add_argument("--ffmpeg", default=None)
    a = ap.parse_args(argv)
    if a.method.endswith("list_options") and not a.device:
        print("--device is required for list_options", file=sys.stderr)
        return 2
    doc: dict = {"tool": "pyav_list", "method": a.method, "device": a.device, "pid": os.getpid(), "calls": [],
                 "versions": {}, "timeout_s": a.timeout_s}
    log = None
    av_mod = None
    if a.method.startswith("pyav"):
        import av  # noqa: PLC0415
        av_mod = av
        doc["versions"] = {"av": av.__version__, "libavdevice": str(av.library_versions.get("libavdevice"))}
        log = _Log(av)
    exe = a.ffmpeg or shutil.which("ffmpeg")
    if a.method.startswith("ffmpeg") and not exe:
        doc["error"] = "ffmpeg CLI not on PATH"
        print(json.dumps(doc))
        return 2
    hung = False
    for i in range(max(1, a.repeats)):
        if i:
            time.sleep(a.gap_s)
        rec = pyav_call(av_mod, log, a.method, a.device, a.timeout_s) if av_mod is not None else \
            ffmpeg_call(exe, a.method, a.device, a.timeout_s)
        rec["i"] = i
        doc["calls"].append(rec)
        if rec["hung"]:
            hung = True
            break
    doc["hung"] = hung
    listed = all((c.get("n_devices") or c.get("option_lines") or 0) > 0 for c in doc["calls"])
    rc = 5 if hung else (0 if listed else 4)
    doc["exit_code"] = rc
    sys.stdout.write(json.dumps(doc, default=str) + "\n")
    sys.stdout.flush()
    if hung:
        os._exit(rc)        # the stuck FFmpeg call holds the filter; do not wait for it
    if log is not None:
        log.stop()
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
