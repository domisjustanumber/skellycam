# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SDL3 camera API probe (C library, zlib license; MF / V4L2 / CoreMedia / Android backends) via ctypes.

Get SDL3 (3.4.18 used here, 2026-10-02):
  Windows: gh release download release-3.4.18 -R libsdl-org/SDL -p 'SDL3-3.4.18-win32-x64.zip'  (SDL3.dll inside)
           sha256(SDL3.dll) = 2b4b128d8d510cc2d442693cf848c050d700d43dc667afe9e5fd82b0570d667e
  Linux:   distro libSDL3.so.0 (>=3.4 for SDL_PIXELFORMAT_MJPG) or build from the tarball
  macOS:   SDL3-3.4.18.dmg (SDL3.framework/SDL3).  NOTE: the CoreMedia backend has no MJPG mapping.

RUN (shared Windows machine):
  uv run --script research/usb_cameras/tools/camlock.py -- uv run --script research/usb_cameras/prior_art/sdl3_camera_probe.py --lib <path-to-SDL3.dll>

Checks: what identity the public API exposes (SDL_GetCameraName + opened-camera properties), whether
MJPG formats are listed, whether an MJPG-spec camera hands back JPEG bytes (surface->pixels, pitch = byte
length), and the timestamp series (SDL rebases the backend timestamp: ts = backend_ts - first_backend_ts +
SDL_GetTicksNS() at the first frame, see src/camera/SDL_camera.c).
OUTPUT results/<platform>/<hostname>/prior_art_sdl3_camera/result.json + frames_<n>.jsonl
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
MJPG = 0x47504A4D
SDL_INIT_CAMERA = 0x00010000


class Spec(C.Structure):
    _fields_ = [("format", C.c_uint32), ("colorspace", C.c_uint32), ("width", C.c_int), ("height", C.c_int),
                ("fps_num", C.c_int), ("fps_den", C.c_int)]


class Surface(C.Structure):
    _fields_ = [("flags", C.c_uint32), ("format", C.c_uint32), ("w", C.c_int), ("h", C.c_int),
                ("pitch", C.c_int), ("pixels", C.c_void_p), ("refcount", C.c_int), ("reserved", C.c_void_p)]


def fcc(v: int) -> str:
    s = "".join(chr((v >> (8 * i)) & 0xFF) for i in range(4))
    return s if s.isprintable() else hex(v)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", required=True)
    ap.add_argument("--seconds", type=float, default=6)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--only", action="append", default=[],
                    help="open only cameras whose name equals this (repeatable). SDL_Init still enumerates "
                         "every camera (the MF backend activates each source to list formats)")
    a = ap.parse_args()
    sdl = C.CDLL(a.lib)
    sdl.SDL_Init.restype = C.c_bool
    sdl.SDL_GetError.restype = C.c_char_p
    sdl.SDL_GetCurrentCameraDriver.restype = C.c_char_p
    sdl.SDL_GetCameras.restype = C.POINTER(C.c_uint32)
    sdl.SDL_GetCameras.argtypes = [C.POINTER(C.c_int)]
    sdl.SDL_GetCameraName.restype = C.c_char_p
    sdl.SDL_GetCameraName.argtypes = [C.c_uint32]
    sdl.SDL_GetCameraSupportedFormats.restype = C.POINTER(C.POINTER(Spec))
    sdl.SDL_GetCameraSupportedFormats.argtypes = [C.c_uint32, C.POINTER(C.c_int)]
    sdl.SDL_OpenCamera.restype = C.c_void_p
    sdl.SDL_OpenCamera.argtypes = [C.c_uint32, C.POINTER(Spec)]
    sdl.SDL_GetCameraPermissionState.argtypes = [C.c_void_p]
    sdl.SDL_GetCameraFormat.argtypes = [C.c_void_p, C.POINTER(Spec)]
    sdl.SDL_GetCameraFormat.restype = C.c_bool
    sdl.SDL_AcquireCameraFrame.restype = C.POINTER(Surface)
    sdl.SDL_AcquireCameraFrame.argtypes = [C.c_void_p, C.POINTER(C.c_uint64)]
    sdl.SDL_ReleaseCameraFrame.argtypes = [C.c_void_p, C.POINTER(Surface)]
    sdl.SDL_CloseCamera.argtypes = [C.c_void_p]
    sdl.SDL_GetCameraProperties.argtypes = [C.c_void_p]
    sdl.SDL_GetCameraProperties.restype = C.c_uint32
    ENUMCB = C.CFUNCTYPE(None, C.c_void_p, C.c_uint32, C.c_char_p)
    sdl.SDL_EnumerateProperties.argtypes = [C.c_uint32, ENUMCB, C.c_void_p]
    sdl.SDL_GetTicksNS.restype = C.c_uint64
    sdl.SDL_free.argtypes = [C.c_void_p]
    sdl.SDL_GetVersion.restype = C.c_int

    if not sdl.SDL_Init(SDL_INIT_CAMERA):
        print("SDL_Init failed:", sdl.SDL_GetError())
        return 1
    v = sdl.SDL_GetVersion()
    res = {"test": "prior_art_sdl3_camera_probe", "platform": PLAT, "hostname": socket.gethostname(),
           "utc_started": dt.datetime.now(dt.timezone.utc).isoformat(), "command": "uv run --script " + " ".join(sys.argv),
           "environment": {"os": platform.platform(), "python": sys.version,
                           "sdl_version": f"{v // 1000000}.{v // 1000 % 1000}.{v % 1000}",
                           "camera_driver": (sdl.SDL_GetCurrentCameraDriver() or b"").decode()},
           "settings": {"width": a.width, "height": a.height, "fps": a.fps, "exposure": "not controlled"},
           "cameras": []}
    n = C.c_int()
    ids = sdl.SDL_GetCameras(C.byref(n))
    cam_ids = [ids[i] for i in range(n.value)]
    out = (Path(os.environ["USBCAM_RESULTS_DIR"]) if os.environ.get("USBCAM_RESULTS_DIR") else ROOT / "results" / PLAT / socket.gethostname()) / "prior_art_sdl3_camera"
    out.mkdir(parents=True, exist_ok=True)
    for cid in cam_ids:
        name = (sdl.SDL_GetCameraName(cid) or b"").decode(errors="replace")
        nf = C.c_int()
        specs = sdl.SDL_GetCameraSupportedFormats(cid, C.byref(nf))
        fmts = [specs[i].contents for i in range(nf.value)] if specs else []
        fl = [{"fmt": fcc(s.format), "w": s.width, "h": s.height, "fps": f"{s.fps_num}/{s.fps_den}"} for s in fmts]
        if specs:
            sdl.SDL_free(specs)
        entry = {"id": cid, "name": name, "n_formats": len(fl), "formats_fourcc": sorted({f["fmt"] for f in fl})}
        want = [f for f in fl if f["fmt"] == "MJPG" and f["w"] == a.width and f["h"] == a.height]
        if a.only and name not in a.only:
            entry["skipped_open"] = "not in --only allowlist"
        if not want or any(s in name for s in ("NDI", "OBS", "Spout", "NVIDIA")) or (a.only and name not in a.only):
            res["cameras"].append(entry)
            continue
        spec = Spec(MJPG, 0, a.width, a.height, a.fps, 1)
        cam = sdl.SDL_OpenCamera(cid, C.byref(spec))
        if not cam:
            entry["error"] = f"SDL_OpenCamera: {sdl.SDL_GetError().decode()}"
            res["cameras"].append(entry)
            continue
        props = []
        cb = ENUMCB(lambda ud, pid, pname: props.append(pname.decode()))
        sdl.SDL_EnumerateProperties(sdl.SDL_GetCameraProperties(cam), cb, None)
        entry["opened_camera_properties"] = props
        frames = []
        t_end = time.monotonic() + a.seconds
        perm = None
        sample_saved = False
        while time.monotonic() < t_end:
            sdl.SDL_PumpEvents()
            perm = sdl.SDL_GetCameraPermissionState(C.c_void_p(cam))
            ts = C.c_uint64()
            fr = sdl.SDL_AcquireCameraFrame(C.c_void_p(cam), C.byref(ts))
            if not fr:
                time.sleep(0.001)
                continue
            host = time.perf_counter_ns()
            ticks = sdl.SDL_GetTicksNS()
            s = fr.contents
            nbytes = s.pitch if s.format == MJPG else s.pitch * s.h
            data = C.string_at(s.pixels, nbytes) if s.pixels else b""
            ok = data[:2] == b"\xff\xd8" and data.rstrip(b"\x00")[-2:] == b"\xff\xd9"
            if ok and not sample_saved and len(frames) > 10:
                (out / f"sample_{cid}.jpg").write_bytes(data)
                sample_saved = True
            frames.append({"camera_key": name, "backend": f"sdl3-{res['environment']['camera_driver']}",
                           "seq": len(frames), "host_arrival_ns": host,
                           "os_timestamp_ns": host - (ticks - ts.value),
                           "os_timestamp_source": "SDL_AcquireCameraFrame timestampNS (rebased backend ts) mapped via SDL_GetTicksNS",
                           "uvc_pts": None, "uvc_scr_stc": None, "uvc_scr_sof": None, "device_clock_hz": None,
                           "payload_bytes": len(data), "is_valid_jpeg": ok, "surface_format": fcc(s.format),
                           "sdl_ts_ns": ts.value})
            sdl.SDL_ReleaseCameraFrame(C.c_void_p(cam), fr)
        got = Spec()
        sdl.SDL_GetCameraFormat(C.c_void_p(cam), C.byref(got))
        sdl.SDL_CloseCamera(C.c_void_p(cam))
        with open(out / f"frames_{cid}.jsonl", "w") as f:
            for x in frames:
                f.write(json.dumps(x) + "\n")
        st = {}
        fr2 = frames[5:]
        if len(fr2) > 3:
            q = lambda v: [round(v[0], 3), round(v[len(v) // 2], 3), round(v[-1], 3)]  # noqa: E731
            arr = [x["host_arrival_ns"] for x in fr2]
            tsv = [x["sdl_ts_ns"] for x in fr2]
            st = {"fps_by_arrival": (len(arr) - 1) / ((arr[-1] - arr[0]) / 1e9),
                  "arrival_interval_ms": q(sorted((b - a_) / 1e6 for a_, b in zip(arr, arr[1:]))),
                  "ts_interval_ms": q(sorted((b - a_) / 1e6 for a_, b in zip(tsv, tsv[1:]))),
                  "arrival_minus_ts_ms": q(sorted((x["host_arrival_ns"] - x["os_timestamp_ns"]) / 1e6 for x in fr2))}
        entry.update({"permission_state": perm, "negotiated": {"fmt": fcc(got.format), "w": got.width, "h": got.height,
                      "fps": f"{got.fps_num}/{got.fps_den}"}, "n_frames": len(frames),
                      "n_valid_jpeg": sum(x["is_valid_jpeg"] for x in frames), "stats": st,
                      "frames_file": f"frames_{cid}.jsonl"})
        res["cameras"].append(entry)
    sdl.SDL_Quit()
    (out / "result.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
