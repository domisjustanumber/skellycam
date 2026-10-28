# /// script
# requires-python = ">=3.10"
# dependencies = ["pupil-labs-uvc==1.0.8", "numpy"]
# ///
"""pyuvc (pupil-labs-uvc) probe: install check, enumeration, accessibility, optional MJPEG streaming.

Run (any OS, from the repo root; wrap in camlock on the shared Windows box):
    uv run --script research/usb_cameras/tools/camlock.py -- \
        uv run --script research/usb_cameras/libusb/pyuvc/pyuvc_probe.py [--stream] [options]

Default (no --stream): imports uvc, lists devices, calls uvc.is_accessible() for each, tries
uvc.Capture() on each and records the exception. Nothing streams.
--stream: for each accessible device (filter with --vid/--pid), streams MJPEG for --seconds at
each --bandwidth-factors value and writes frames_<vid>_<pid>_bf<F>.jsonl in the README per-frame
schema (backend "pyuvc"). Records whether pyuvc's frame.timestamp (PTS-derived, host clock) is
sane vs. the arrival time.

Needs:
  Windows: the camera on libusbK/WinUSB (pyuvc docs say libusbK on the *composite parent*;
           research/usb_cameras/libusb/winusb/ installs WinUSB on the C930e parent).
  Linux:   udev rule giving the user rw on /dev/bus/usb/* (see ../linux/).
  macOS:   root (sudo) on macOS 12+ (libusb must detach the kernel UVC driver).
Writes: research/usb_cameras/results/<platform>/<hostname>/pyuvc_probe[_stream]/result.json
"""
from __future__ import annotations

import argparse
import datetime as _dt
import importlib.metadata as md
import json
import platform
import socket
import sys
import time
import traceback
from pathlib import Path

PLAT = {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}.get(platform.system(), platform.system().lower())
REPO_RESULTS = Path(__file__).resolve().parents[2] / "results"


def jpeg_ok(buf: bytes) -> bool:
    return len(buf) > 4 and buf[:2] == b"\xff\xd8" and b"\xff\xd9" in buf[-64:]


def bundled_libusb_version() -> dict:
    """Find the libusb shared library shipped in the wheel (delvewheel/auditwheel/delocate dirs)
    and ask it for its version via libusb_get_version()."""
    import ctypes

    class _V(ctypes.Structure):
        _fields_ = [("major", ctypes.c_uint16), ("minor", ctypes.c_uint16), ("micro", ctypes.c_uint16),
                    ("nano", ctypes.c_uint16), ("rc", ctypes.c_char_p), ("describe", ctypes.c_char_p)]

    found = []
    try:
        dist = md.distribution("pupil-labs-uvc")
        for f in dist.files or []:
            n = str(f).lower()
            if "libusb" in n and n.endswith((".dll", ".so", ".dylib")) or (".so." in n and "libusb" in n):
                p = Path(dist.locate_file(f))
                entry = {"file": str(p)}
                try:
                    lib = ctypes.CDLL(str(p))
                    lib.libusb_get_version.restype = ctypes.POINTER(_V)
                    v = lib.libusb_get_version().contents
                    entry["version"] = f"{v.major}.{v.minor}.{v.micro}.{v.nano}"
                except Exception as e:  # noqa: BLE001
                    entry["error"] = repr(e)
                found.append(entry)
            elif "pthread" in n and n.endswith(".dll"):
                found.append({"file": str(Path(dist.locate_file(f))), "note": "pthreads-win32 runtime bundled"})
    except Exception as e:  # noqa: BLE001
        return {"error": repr(e)}
    return {"libs": found}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stream", action="store_true")
    ap.add_argument("--vid", type=lambda s: int(s, 16))
    ap.add_argument("--pid", type=lambda s: int(s, 16))
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--bandwidth-factors", default="2.0", help="comma list, pyuvc default is 2.0; 0 = use camera's dwMaxPayloadTransferSize")
    ap.add_argument("--manual-exposure", type=int, help="'Absolute Exposure Time' value (100us units); sets AE mode manual")
    ap.add_argument("--out-dir", type=Path)
    a = ap.parse_args()

    host = socket.gethostname()
    out = a.out_dir or (REPO_RESULTS / PLAT / host / ("pyuvc_probe_stream" if a.stream else "pyuvc_probe"))
    out.mkdir(parents=True, exist_ok=True)
    res: dict = {
        "test": "pyuvc_probe",
        "platform": PLAT,
        "hostname": host,
        "utc_started": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "command": " ".join(sys.argv),
        "environment": {"python": sys.version, "os": platform.platform()},
        "cameras": [],
    }
    try:
        res["environment"]["pupil-labs-uvc"] = md.version("pupil-labs-uvc")
        import uvc  # noqa: PLC0415

        res["import_ok"] = True
        res["uvc_module_file"] = getattr(uvc, "__file__", None)
    except Exception as e:  # noqa: BLE001
        res["import_ok"] = False
        res["import_error"] = repr(e)
        res["import_traceback"] = traceback.format_exc()
        (out / "result.json").write_text(json.dumps(res, indent=2))
        print(json.dumps(res, indent=2))
        return 2

    res["bundled_libusb"] = bundled_libusb_version()

    # clock check: pyuvc's get_time_monotonic() vs time.perf_counter_ns()
    t0 = time.perf_counter_ns()
    g = uvc.get_time_monotonic()
    t1 = time.perf_counter_ns()
    res["clock_check"] = {
        "uvc_get_time_monotonic_s": g,
        "perf_counter_s": (t0 + t1) / 2e9,
        "difference_s": g - (t0 + t1) / 2e9,
        "note": "on Windows both should be QPC-based seconds; difference ~0 means same clock",
    }

    try:
        devs = uvc.device_list() or []
    except Exception as e:  # noqa: BLE001
        res["device_list_error"] = repr(e)
        devs = []
    for d in devs:
        cam = {k: d.get(k) for k in ("name", "manufacturer", "serialNumber", "idVendor", "idProduct", "bus_number", "device_address", "uid")}
        cam["vid"] = f"{d['idVendor']:04x}"
        cam["pid"] = f"{d['idProduct']:04x}"
        try:
            cam["is_accessible"] = bool(uvc.is_accessible(d["uid"]))
        except Exception as e:  # noqa: BLE001
            cam["is_accessible"] = None
            cam["is_accessible_error"] = repr(e)
        try:
            cap = uvc.Capture(d["uid"])
            cam["capture_open"] = "OK"
            cam["available_modes"] = [str(m) for m in cap.available_modes][:64]
            cap.close()
        except Exception as e:  # noqa: BLE001
            cam["capture_open"] = repr(e)
        res["cameras"].append(cam)

    if a.stream:
        res["streams"] = []
        for d in devs:
            if a.vid is not None and d["idVendor"] != a.vid:
                continue
            if a.pid is not None and d["idProduct"] != a.pid:
                continue
            for bf in [float(x) for x in a.bandwidth_factors.split(",")]:
                res["streams"].append(stream_one(uvc, d, bf, a, out))

    (out / "result.json").write_text(json.dumps(res, indent=2))
    print(json.dumps({k: v for k, v in res.items() if k != "import_traceback"}, indent=2))
    print(f"wrote {out / 'result.json'}", file=sys.stderr)
    if not any(c.get("capture_open") == "OK" for c in res["cameras"]):
        print("no accessible device (pyuvc could not open any camera)", file=sys.stderr)
        return 3
    return 0


def stream_one(uvc, d, bf: float, a, out: Path) -> dict:
    key = f"usb:{d['idVendor']:04x}:{d['idProduct']:04x}:" + (f"sn:{d['serialNumber']}" if d.get("serialNumber") not in (None, "unknown") else f"busaddr:{d['uid']}")
    s: dict = {"camera_key": key, "bandwidth_factor": bf, "requested": [a.width, a.height, a.fps]}
    jl = out / f"frames_{d['idVendor']:04x}_{d['idProduct']:04x}_bf{bf:g}.jsonl"
    try:
        cap = uvc.Capture(d["uid"])
        mode = next((m for m in cap.available_modes if m.width == a.width and m.height == a.height and m.fps == a.fps and "MJPG" in str(m.format_name).upper()), None)
        if mode is None:
            mode = next(m for m in cap.available_modes if m.width == a.width and m.height == a.height and m.fps == a.fps)
        s["mode"] = str(mode)
        cap.frame_mode = mode
        cap.bandwidth_factor = bf
        controls = {c.display_name: c for c in cap.controls}
        if a.manual_exposure is not None:
            if "Auto Exposure Mode" in controls:
                controls["Auto Exposure Mode"].value = 1
            if "Absolute Exposure Time" in controls:
                controls["Absolute Exposure Time"].value = a.manual_exposure
        s["controls"] = {n: getattr(c, "value", None) for n, c in controls.items()}
        n = ok = 0
        deltas = []
        t_end = time.perf_counter() + a.seconds
        with jl.open("w") as f:
            while time.perf_counter() < t_end:
                fr = cap.get_frame(timeout=1.0)
                arr = time.perf_counter_ns()
                buf = bytes(fr.jpeg_buffer) if hasattr(fr, "jpeg_buffer") else b""
                v = jpeg_ok(buf) if buf else None
                n += 1
                ok += bool(v)
                ts_ns = int(fr.timestamp * 1e9)
                deltas.append((arr - ts_ns) / 1e6)
                f.write(json.dumps({
                    "camera_key": key, "backend": "pyuvc", "seq": int(fr.index), "host_arrival_ns": arr,
                    "os_timestamp_ns": ts_ns,
                    "os_timestamp_source": "pyuvc frame.timestamp: pupil-labs libuvc PTS mapped to host clock (dev_clk_start_host_us + PTS/clock_freq, drift-corrected)",
                    "uvc_pts": None, "uvc_scr_stc": None, "uvc_scr_sof": None, "device_clock_hz": None,
                    "payload_bytes": len(buf), "is_valid_jpeg": v, "jpeg_check": "soi_eoi_only",
                }) + "\n")
        cap.close()
        deltas.sort()
        s.update({
            "frames": n, "jpeg_ok": ok, "fps": n / a.seconds, "frames_jsonl": str(jl),
            "arrival_minus_timestamp_ms": {"min": deltas[0], "median": deltas[len(deltas) // 2], "max": deltas[-1]} if deltas else None,
        })
    except Exception as e:  # noqa: BLE001
        s["error"] = repr(e)
        s["traceback"] = traceback.format_exc()
    return s


if __name__ == "__main__":
    sys.exit(main())
