# /// script
# requires-python = ">=3.10"
# dependencies = ["pupil-labs-uvc==1.0.8", "numpy", "pillow>=10"]
# ///
"""pyuvc (pupil-labs-uvc 1.0.8) on a WinUSB-bound UVC camera: open, MJPEG stream, bandwidth_factor -> alt
setting (verified by a live hub-IOCTL pipe snapshot), timestamps, exposure control.

Run (repo root; the snapshot tool does not open the camera, the whole run is inside one camlock hold):
  uv run --script research/usb_cameras/tools/camlock.py -- \
      uv run --script research/usb_cameras/libusb/pyuvc/pyuvc_winusb_stream.py \
      --vid 046d --pid 0843 --width 1280 --height 720 --fps 30 --seconds 20 \
      --bandwidth-factors 2.0,1.0,0 [--manual-exposure 100] --out-dir <dir> [--raw-dump-dir <scratch dir>]

Per bandwidth factor: opens uvc.Capture, selects the MJPEG mode, sets bandwidth_factor, streams --seconds with
get_frame(), starts `bandwidth/win_usb_topology.py --pipes-only` (Windows) asynchronously --snapshot-at-s seconds in,
then closes. After streaming every retained jpeg_buffer is fully decoded with Pillow. Writes result.json and one
frames_bf<F>.jsonl (README per-frame schema) per factor. Host clock: time.perf_counter_ns() (QPC on Windows).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import importlib.metadata as md
import json
import platform
import socket
import statistics
import subprocess
import sys
import time
import traceback
from io import BytesIO
from pathlib import Path

PLAT = {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}.get(platform.system(), platform.system().lower())
HERE = Path(__file__).resolve().parent
TOPO = HERE.parents[1] / "bandwidth" / "win_usb_topology.py"


def pyuvc_expected_bytes(w: int, h: int, interval_100ns: int, bf: float) -> int:
    """libuvc-source/src/stream.c (pupil-labs fork) bandwidth_factor estimate, integer math as in C (size_t)."""
    b = int(w * h / 8 * bf)
    b *= 10000000 // interval_100ns + 1
    b //= 1000
    b //= 8
    return b + 12


def stats(xs: list[float]) -> dict | None:
    if not xs:
        return None
    s = sorted(xs)
    return {"n": len(s), "mean": statistics.fmean(s), "std": statistics.pstdev(s) if len(s) > 1 else 0.0,
            "min": s[0], "p50": s[len(s) // 2], "max": s[-1]}


def stream_one(uvc, d: dict, bf: float, a, out: Path) -> dict:
    from PIL import Image

    s: dict = {"bandwidth_factor": bf, "requested": [a.width, a.height, a.fps]}
    key = f"usb:{d['idVendor']:04x}:{d['idProduct']:04x}:pyuvc-uid:{d['uid']}"
    jl = out / f"frames_bf{bf:g}.jsonl"
    cap = None
    snap_proc = None
    try:
        cap = uvc.Capture(d["uid"])
        modes = list(cap.available_modes)
        s["available_modes_count"] = len(modes)
        mode = next((m for m in modes if m.width == a.width and m.height == a.height and m.fps == a.fps
                     and "MJPG" in str(m.format_name).upper()), None)
        if mode is None:
            s["error"] = f"no MJPEG mode {a.width}x{a.height}@{a.fps}; modes={[str(m) for m in modes][:40]}"
            return s
        s["mode"] = str(mode)
        cap.frame_mode = mode
        cap.bandwidth_factor = bf
        s["bandwidth_factor_readback"] = cap.bandwidth_factor
        s["pyuvc_expected_bytes_per_packet"] = pyuvc_expected_bytes(a.width, a.height, int(round(1e7 / a.fps)), bf) if bf > 0 else "dwMaxPayloadTransferSize"
        controls = {c.display_name: c for c in cap.controls}
        s["controls_before"] = {n: {"value": getattr(c, "value", None), "min": getattr(c, "min_val", None),
                                    "max": getattr(c, "max_val", None), "def": getattr(c, "def_val", None)}
                                for n, c in controls.items()}
        if a.manual_exposure is not None:
            ctl = {}
            try:
                controls["Auto Exposure Mode"].value = 1
                ctl["ae_mode_readback"] = controls["Auto Exposure Mode"].value
                controls["Absolute Exposure Time"].value = a.manual_exposure
                ctl["exposure_readback"] = controls["Absolute Exposure Time"].value
            except Exception as e:  # noqa: BLE001
                ctl["error"] = repr(e)
            s["exposure_set"] = ctl
        rows, bufs, errs = [], [], []
        cpu0, t_start = time.process_time(), time.perf_counter()
        t_end = t_start + a.seconds
        snapped = False
        while time.perf_counter() < t_end:
            if not snapped and PLAT == "windows" and time.perf_counter() - t_start >= a.snapshot_at_s:
                snap_proc = subprocess.Popen(["uv", "run", "--script", str(TOPO), "--pipes-only"],
                                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                s["snapshot_started_s"] = time.perf_counter() - t_start
                snapped = True
            try:
                fr = cap.get_frame(timeout=1.0)
            except Exception as e:  # noqa: BLE001  (TimeoutError / StreamError("JPEG header corrupt.") ...)
                errs.append((round(time.perf_counter() - t_start, 3), repr(e)[:100]))
                continue
            arr = time.perf_counter_ns()
            buf = bytes(fr.jpeg_buffer)
            bufs.append(buf)
            rows.append({"camera_key": key, "backend": "pyuvc", "seq": int(fr.index), "host_arrival_ns": arr,
                         "os_timestamp_ns": int(round(fr.timestamp * 1e9)),
                         "os_timestamp_source": "pyuvc frame.timestamp (libuvc capture_time: dev_clk_start_host_us + PTS/clock, "
                                                "seconds of QPC)",
                         "uvc_pts": None, "uvc_scr_stc": None, "uvc_scr_sof": None, "device_clock_hz": None,
                         "payload_bytes": len(buf), "is_valid_jpeg": None, "jpeg_check": "pillow_full_decode",
                         "data_fully_received": bool(fr.data_fully_received)})
        cpu = time.process_time() - cpu0
        if cap is not None:
            cap.stop_stream()
        if snap_proc is not None:
            so, se = snap_proc.communicate(timeout=60)
            try:
                snap = json.loads(so)
                s["pipes_snapshot"] = [c for c in snap if c["idVendor"].lower().endswith(f"{d['idVendor']:04x}")
                                       and c["idProduct"].lower().endswith(f"{d['idProduct']:04x}")] or snap
            except Exception as e:  # noqa: BLE001
                s["pipes_snapshot_error"] = repr(e)
                s["pipes_snapshot_raw"] = (so or "")[-2000:] + (se or "")[-2000:]
        ok = 0
        for r, b in zip(rows, bufs):
            try:
                with Image.open(BytesIO(b)) as im:
                    im.load()
                    r["is_valid_jpeg"] = im.size == (a.width, a.height)
            except Exception:  # noqa: BLE001
                r["is_valid_jpeg"] = False
            ok += r["is_valid_jpeg"]
        if a.raw_dump_dir is not None:  # every retained frame, u32 LE length + bytes (same as uvc_libusb1_stream.py --raw-dump)
            a.raw_dump_dir.mkdir(parents=True, exist_ok=True)
            rp = a.raw_dump_dir / f"pyuvc_bf{bf:g}.u32.bin"
            with rp.open("wb") as f:
                for b in bufs:
                    f.write(len(b).to_bytes(4, "little"))
                    f.write(b)
            s["raw_dump"] = str(rp)
        with jl.open("w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        idx = [r["seq"] for r in rows]
        idx_gaps = sum(1 for p, q in zip(idx, idx[1:]) if q - p != 1)
        arr_ms = [(q["host_arrival_ns"] - p["host_arrival_ns"]) / 1e6 for p, q in zip(rows, rows[1:])]
        ts_ms = [(q["os_timestamp_ns"] - p["os_timestamp_ns"]) / 1e6 for p, q in zip(rows, rows[1:])]
        lat_ms = [(r["host_arrival_ns"] - r["os_timestamp_ns"]) / 1e6 for r in rows]
        dur = (rows[-1]["host_arrival_ns"] - rows[0]["host_arrival_ns"]) / 1e9 if len(rows) > 1 else 0
        s.update({
            "frames": len(rows), "pillow_full_decode_ok": ok, "get_frame_errors": len(errs), "get_frame_errors_first10": errs[:10],
            "fps_from_arrivals": (len(rows) - 1) / dur if dur else 0, "frame_index_gaps": idx_gaps,
            "frame_index_first_last": [idx[0], idx[-1]] if idx else None,
            "mean_frame_bytes": statistics.fmean(len(b) for b in bufs) if bufs else 0,
            "data_fully_received_false": sum(1 for r in rows if not r["data_fully_received"]),
            "process_cpu_s": cpu, "cpu_fraction_of_one_core": cpu / a.seconds,
            "arrival_interval_ms": stats(arr_ms), "timestamp_interval_ms": stats(ts_ms),
            "arrival_minus_timestamp_ms": stats(lat_ms), "frames_jsonl": str(jl),
        })
    except Exception as e:  # noqa: BLE001
        s["error"] = repr(e)
        s["traceback"] = traceback.format_exc()
    finally:
        if cap is not None:
            try:
                cap.close()
            except Exception:  # noqa: BLE001
                pass
        if snap_proc is not None and snap_proc.poll() is None:
            snap_proc.kill()
    return s


def controls_test(uvc, d: dict, a) -> dict:
    out: dict = {}
    cap = uvc.Capture(d["uid"])
    try:
        out["modes"] = [str(m) for m in cap.available_modes]
        ctl = {c.display_name: c for c in cap.controls}
        out["controls"] = {n: {"value": c.value, "min": c.min_val, "max": c.max_val, "def": c.def_val, "step": c.step}
                           for n, c in ctl.items()}
        exp = a.manual_exposure if a.manual_exposure is not None else 100
        steps = []
        for name, val in (("Auto Exposure Mode", 1), ("Absolute Exposure Time", exp), ("Absolute Exposure Time", exp * 2),
                          ("Auto Exposure Mode", 8)):
            c = ctl.get(name)
            if c is None:
                steps.append({"control": name, "error": "absent"})
                continue
            try:
                c.value = val
                c.refresh()
                steps.append({"control": name, "set": val, "readback": c.value})
            except Exception as e:  # noqa: BLE001
                steps.append({"control": name, "set": val, "error": repr(e)})
        out["set_readback"] = steps
    finally:
        cap.close()
    return out


def double_open_test(vid: int, pid: int) -> dict:
    """ctypes against the libusb DLL bundled in the pyuvc wheel (the one uvc_bindings links): open the target twice
    and read iProduct through each handle. pupil-labs libuvc's uvc_stream_start() calls uvc_get_device_descriptor(),
    which libusb_open()s the already-open device to read iProduct and then strlen()s the result without a NULL check."""
    import ctypes
    import glob

    out: dict = {}
    dlls = glob.glob(str(Path(md.distribution("pupil-labs-uvc").locate_file("")) / "**" / "libusb*.dll"), recursive=True)
    out["dlls"] = dlls
    if not dlls:
        return out
    lib = ctypes.CDLL(dlls[0])

    class Ver(ctypes.Structure):
        _fields_ = [("major", ctypes.c_uint16), ("minor", ctypes.c_uint16), ("micro", ctypes.c_uint16),
                    ("nano", ctypes.c_uint16), ("rc", ctypes.c_char_p), ("describe", ctypes.c_char_p)]

    class DevDesc(ctypes.Structure):
        _fields_ = [("bLength", ctypes.c_uint8), ("bDescriptorType", ctypes.c_uint8), ("bcdUSB", ctypes.c_uint16),
                    ("bDeviceClass", ctypes.c_uint8), ("bDeviceSubClass", ctypes.c_uint8), ("bDeviceProtocol", ctypes.c_uint8),
                    ("bMaxPacketSize0", ctypes.c_uint8), ("idVendor", ctypes.c_uint16), ("idProduct", ctypes.c_uint16),
                    ("bcdDevice", ctypes.c_uint16), ("iManufacturer", ctypes.c_uint8), ("iProduct", ctypes.c_uint8),
                    ("iSerialNumber", ctypes.c_uint8), ("bNumConfigurations", ctypes.c_uint8)]

    lib.libusb_get_version.restype = ctypes.POINTER(Ver)
    v = lib.libusb_get_version().contents
    out["libusb_version"] = f"{v.major}.{v.minor}.{v.micro}.{v.nano}"
    ctx = ctypes.c_void_p()
    out["init"] = lib.libusb_init(ctypes.byref(ctx))
    lst = ctypes.POINTER(ctypes.c_void_p)()
    lib.libusb_get_device_list.restype = ctypes.c_ssize_t
    n = lib.libusb_get_device_list(ctx, ctypes.byref(lst))
    target = None
    for i in range(n):
        d = DevDesc()
        lib.libusb_get_device_descriptor(ctypes.c_void_p(lst[i]), ctypes.byref(d))
        if d.idVendor == vid and d.idProduct == pid:
            target, desc = ctypes.c_void_p(lst[i]), d
            break
    if target is None:
        out["error"] = "target not found"
        return out
    out["iProduct_index"] = desc.iProduct
    out["iSerialNumber_index"] = desc.iSerialNumber
    h1, h2 = ctypes.c_void_p(), ctypes.c_void_p()
    out["open1_rc"] = lib.libusb_open(target, ctypes.byref(h1))
    buf = ctypes.create_string_buffer(128)
    if out["open1_rc"] == 0:
        r = lib.libusb_get_string_descriptor_ascii(h1, desc.iProduct, buf, 128)
        out["open1_iProduct"] = buf.value.decode(errors="replace") if r > 0 else r
        out["open2_rc_while_open1"] = lib.libusb_open(target, ctypes.byref(h2))
        if out["open2_rc_while_open1"] == 0:
            r = lib.libusb_get_string_descriptor_ascii(h2, desc.iProduct, buf, 128)
            out["open2_iProduct"] = buf.value.decode(errors="replace") if r > 0 else r
            lib.libusb_close(h2)
        out["claim_if0_rc"] = lib.libusb_claim_interface(h1, 0)
        out["open3_rc_while_open1_claimed"] = lib.libusb_open(target, ctypes.byref(h2))
        if out["open3_rc_while_open1_claimed"] == 0:
            r = lib.libusb_get_string_descriptor_ascii(h2, desc.iProduct, buf, 128)
            out["open3_iProduct"] = buf.value.decode(errors="replace") if r > 0 else r
            lib.libusb_close(h2)
        lib.libusb_release_interface(h1, 0)
        lib.libusb_close(h1)
    lib.libusb_free_device_list(lst, 1)
    lib.libusb_exit(ctx)
    out["note"] = "libusb error codes: -3 ACCESS, -4 NO_DEVICE, -5 NOT_FOUND, -6 BUSY, -12 NOT_SUPPORTED"
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vid", type=lambda x: int(x, 16), default=0x046D)
    ap.add_argument("--pid", type=lambda x: int(x, 16), default=0x0843)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--seconds", type=float, default=20.0)
    ap.add_argument("--bandwidth-factors", default="2.0")
    ap.add_argument("--manual-exposure", type=int)
    ap.add_argument("--snapshot-at-s", type=float, default=5.0)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--raw-dump-dir", type=Path, help="write every frame of each factor to DIR/pyuvc_bf<F>.u32.bin (keep it outside the repo)")
    ap.add_argument("--no-stream", action="store_true", help="device list + bundled-libusb double-open test only")
    ap.add_argument("--controls-only", action="store_true", help="open Capture, list modes+controls, set/read back exposure; no stream")
    a = ap.parse_args()
    a.out_dir.mkdir(parents=True, exist_ok=True)
    res: dict = {"test": "pyuvc_winusb_stream", "platform": PLAT, "hostname": socket.gethostname(),
                 "utc_started": _dt.datetime.now(_dt.timezone.utc).isoformat(), "command": " ".join(sys.argv),
                 "environment": {"python": sys.version, "os": platform.platform(), "pupil-labs-uvc": md.version("pupil-labs-uvc")},
                 "host_clock": "time.perf_counter_ns", "cameras": []}
    import uvc  # noqa: PLC0415

    t0 = time.perf_counter_ns()
    g = uvc.get_time_monotonic()
    t1 = time.perf_counter_ns()
    res["clock_check"] = {"uvc_get_time_monotonic_s": g, "perf_counter_s": (t0 + t1) / 2e9, "difference_s": g - (t0 + t1) / 2e9}
    devs = uvc.device_list() or []
    res["device_list"] = [{k: v for k, v in dd.items()} for dd in devs]
    for dd in devs:
        try:
            dd_acc = bool(uvc.is_accessible(dd["uid"]))
        except Exception as e:  # noqa: BLE001
            dd_acc = repr(e)
        res["cameras"].append({"vid": f"{dd['idVendor']:04x}", "pid": f"{dd['idProduct']:04x}", "uid": dd["uid"], "is_accessible": dd_acc})
    target = next((dd for dd in devs if dd["idVendor"] == a.vid and dd["idProduct"] == a.pid), None)
    res["bundled_libusb_double_open"] = double_open_test(a.vid, a.pid)
    (a.out_dir / "result.json").write_text(json.dumps(res, indent=2, default=str))  # early write: survives a native crash
    if a.controls_only and target is not None:
        res["controls_only"] = controls_test(uvc, target, a)
        (a.out_dir / "result.json").write_text(json.dumps(res, indent=2, default=str))
    if a.no_stream or a.controls_only:
        print(json.dumps(res, indent=1, default=str))
        return 0
    rc = 0
    if target is None:
        res["error"] = "target camera not in uvc.device_list()"
        rc = 3
    else:
        res["streams"] = [stream_one(uvc, target, float(x), a, a.out_dir) for x in a.bandwidth_factors.split(",")]
        if not any(s.get("frames") for s in res["streams"]):
            rc = 4
    res["exit_code"] = rc
    (a.out_dir / "result.json").write_text(json.dumps(res, indent=2, default=str))
    summ = [{k: s.get(k) for k in ("bandwidth_factor", "mode", "frames", "pillow_full_decode_ok", "get_frame_errors", "fps_from_arrivals",
                                   "frame_index_gaps", "cpu_fraction_of_one_core", "error")} for s in res.get("streams", [])]
    print(json.dumps({"cameras": res["cameras"], "streams": summ}, indent=1))
    print(f"wrote {a.out_dir / 'result.json'} (exit {rc})", file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main())
