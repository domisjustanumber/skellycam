# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""openpnp-capture (C library, MIT; DirectShow / V4L2 / AVFoundation backends) probe via ctypes.

Get the prebuilt library from the GitHub release (v0.0.30, 2025-06-13):
  gh release download v0.0.30 -R openpnp/openpnp-capture -p 'libopenpnp-capture-windows-latest-x86_64.dll'
  (Linux: libopenpnp-capture-ubuntu-22.04-x86_64.so, macOS: libopenpnp-capture-macos-latest-arm64.dylib)
sha256 of the Windows DLL used here: 3280266977f6ee70687d997455cd7463507ed5077d5de1235c4ef5d8f8e77b21

RUN (shared Windows machine):
  uv run --script research/usb_cameras/tools/camlock.py -- uv run --script research/usb_cameras/prior_art/openpnp_capture_probe.py --lib <path-to-dll>

Checks: Cap_getDeviceName / Cap_getDeviceUniqueID strings, format list (fourcc), whether the only frame
API (Cap_captureFrame) returns RGB (w*h*3) -- i.e. no compressed passthrough -- and the frame counter rate.
OUTPUT results/<platform>/<hostname>/prior_art_openpnp_capture/result.json
"""
from __future__ import annotations

import argparse
import ctypes as C
import datetime as dt
import json
import os
import platform
import socket
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAT = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")


class CapFormatInfo(C.Structure):
    _fields_ = [("width", C.c_uint32), ("height", C.c_uint32), ("fourcc", C.c_uint32),
                ("fps", C.c_uint32), ("bpp", C.c_uint32)]


def fourcc(v: int) -> str:
    return "".join(chr((v >> (8 * i)) & 0xFF) for i in range(4))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", required=True)
    ap.add_argument("--seconds", type=float, default=4)
    ap.add_argument("--only", action="append", default=[],
                    help="open streams only on devices whose unique ID contains this substring (repeatable). "
                         "Cap_createContext still enumerates (binds) every DirectShow device to list formats")
    a = ap.parse_args()
    lib = C.CDLL(a.lib)
    lib.Cap_createContext.restype = C.c_void_p
    lib.Cap_getDeviceCount.argtypes = [C.c_void_p]
    lib.Cap_getDeviceName.restype = C.c_char_p
    lib.Cap_getDeviceName.argtypes = [C.c_void_p, C.c_uint32]
    lib.Cap_getDeviceUniqueID.restype = C.c_char_p
    lib.Cap_getDeviceUniqueID.argtypes = [C.c_void_p, C.c_uint32]
    lib.Cap_getNumFormats.argtypes = [C.c_void_p, C.c_uint32]
    lib.Cap_getFormatInfo.argtypes = [C.c_void_p, C.c_uint32, C.c_uint32, C.POINTER(CapFormatInfo)]
    lib.Cap_openStream.restype = C.c_int32
    lib.Cap_openStream.argtypes = [C.c_void_p, C.c_uint32, C.c_uint32]
    lib.Cap_closeStream.argtypes = [C.c_void_p, C.c_int32]
    lib.Cap_captureFrame.argtypes = [C.c_void_p, C.c_int32, C.c_void_p, C.c_uint32]
    lib.Cap_hasNewFrame.argtypes = [C.c_void_p, C.c_int32]
    lib.Cap_getStreamFrameCount.argtypes = [C.c_void_p, C.c_int32]
    lib.Cap_getLibraryVersion.restype = C.c_char_p
    lib.Cap_setLogLevel(3)

    ctx = lib.Cap_createContext()
    res = {"test": "prior_art_openpnp_capture_probe", "platform": PLAT, "hostname": socket.gethostname(),
           "utc_started": dt.datetime.now(dt.timezone.utc).isoformat(),
           "command": "uv run --script " + " ".join(sys.argv),
           "environment": {"os": platform.platform(), "python": sys.version,
                           "openpnp_capture": lib.Cap_getLibraryVersion().decode()},
           "devices": []}
    n = lib.Cap_getDeviceCount(ctx)
    for i in range(n):
        name = lib.Cap_getDeviceName(ctx, i).decode(errors="replace")
        uid = lib.Cap_getDeviceUniqueID(ctx, i).decode(errors="replace")
        fmts = []
        for f in range(lib.Cap_getNumFormats(ctx, i)):
            fi = CapFormatInfo()
            lib.Cap_getFormatInfo(ctx, i, f, C.byref(fi))
            fmts.append({"id": f, "w": fi.width, "h": fi.height, "fourcc": fourcc(fi.fourcc), "fps": fi.fps, "bpp": fi.bpp})
        d = {"index": i, "name": name, "unique_id": uid, "n_formats": len(fmts),
             "fourccs": sorted({x["fourcc"] for x in fmts})}
        mj = [x for x in fmts if x["fourcc"] == "MJPG" and x["w"] == 1280 and x["h"] == 720]
        allowed = not a.only or any(o.lower() in uid.lower() for o in a.only)
        if not allowed:
            d["skipped_stream"] = "not in --only allowlist"
        if allowed and mj and any(s in uid.lower() for s in ("vid_", "usb", "0x")):
            f = mj[0]
            d["opened_format"] = f
            s = lib.Cap_openStream(ctx, i, f["id"])
            if s >= 0:
                nbytes = f["w"] * f["h"] * 3
                buf = (C.c_uint8 * nbytes)()
                t0 = time.perf_counter()
                c0 = None
                grabbed = 0
                while time.perf_counter() - t0 < a.seconds:
                    if lib.Cap_hasNewFrame(ctx, s):
                        r = lib.Cap_captureFrame(ctx, s, buf, nbytes)
                        grabbed += (r == 0)
                        if c0 is None:
                            c0 = (lib.Cap_getStreamFrameCount(ctx, s), time.perf_counter())
                    time.sleep(0.002)
                c1 = (lib.Cap_getStreamFrameCount(ctx, s), time.perf_counter())
                d["capture"] = {"buffer_bytes_required_by_api": nbytes, "frames_copied_ok": grabbed,
                                "driver_frame_counter_rate_fps": (c1[0] - c0[0]) / (c1[1] - c0[1]) if c0 else None,
                                "first_bytes_hex": bytes(buf[:4]).hex(),
                                "api_has_raw_or_timestamp_function": False}
                lib.Cap_closeStream(ctx, s)
            else:
                d["capture"] = {"error": f"Cap_openStream returned {s}"}
        res["devices"].append(d)
    lib.Cap_releaseContext(C.c_void_p(ctx))
    out = (Path(os.environ["USBCAM_RESULTS_DIR"]) if os.environ.get("USBCAM_RESULTS_DIR") else ROOT / "results" / PLAT / socket.gethostname()) / "prior_art_openpnp_capture"
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
