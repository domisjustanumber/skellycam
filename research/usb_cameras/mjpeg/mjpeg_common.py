"""Shared helpers for the goal-1 (native MJPEG extraction) harnesses.

Not a PEP 723 script itself: the capture scripts in this directory put this directory on
sys.path and import it, and declare its dependencies (pillow, simplejpeg, psutil) themselves.

Run-directory contract (every backend writes the same files into a scratch run dir):
  meta.json        backend, requested mode, capture window (host monotonic ns), cpu, cameras[]
  frames.jsonl     one JSON object per delivered frame, README per-frame schema + extras,
                   plus "cam_idx" and "in_window" (arrival inside the measured window)
  frames_<i>.bin   payload records for camera i: u32 cam, u64 seq, u32 len, <len bytes>

summarize_run() validates every payload (SOI/EOI + full decode with Pillow and with
simplejpeg/libjpeg-turbo), fills is_valid_jpeg, and writes summary.json + frames.jsonl
(+ optional sample JPEG) into the results directory. The .bin files stay in scratch.
"""
from __future__ import annotations

import io
import json
import os
import platform
import socket
import statistics
import struct
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
USB_ROOT = HERE.parent
HOST = socket.gethostname()


def plat() -> str:
    return {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux" if sys.platform.startswith("linux") else sys.platform)


def results_dir(test: str, *parts: str, root: Path | str | None = None) -> Path:
    """results/<platform>/<host>/<test>/<parts...>, or <root>/<test>/<parts...> when root is given."""
    p = (Path(root) / test) if root else (USB_ROOT / "results" / plat() / HOST / test)
    for x in parts:
        p = p / x
    p.mkdir(parents=True, exist_ok=True)
    return p


def scratch_root() -> Path:
    env = os.environ.get("MJPEG_SCRATCH")
    if env:
        p = Path(env)
    else:
        import tempfile
        p = Path(tempfile.gettempdir()) / "usb_cameras_mjpeg_scratch"
    p.mkdir(parents=True, exist_ok=True)
    return p


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_stamp() -> str:
    """Compact UTC stamp for new result directories, e.g. 20261027T031500Z."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def machine_cpu(interval: float = 1.0) -> dict:
    """Whole-machine CPU% over `interval` seconds (psutil), for labelling runs taken while other agents load the box."""
    try:
        import psutil
        per = psutil.cpu_percent(interval=interval, percpu=True)
        return {"utc": utc_now(), "interval_s": interval, "machine_cpu_pct": round(sum(per) / len(per), 1), "n_logical": len(per),
                "busiest_core_pct": max(per)}
    except Exception as e:  # never fail a run because of this
        return {"error": repr(e)}


def jpeg_luma(b: bytes) -> float | None:
    """Mean luma (0..255) of a JPEG, decoded at 1/8 scale in GRAY (libjpeg-turbo via simplejpeg). Used to show how dark the
    scene was (night runs: auto-exposure priority can lower fps in low light)."""
    try:
        import simplejpeg
        a = simplejpeg.decode_jpeg(b, colorspace="GRAY", fastdct=True, min_factor=8, strict=False)
        return round(float(a.mean()), 2)
    except Exception:
        return None


def environment(extra_packages: tuple[str, ...] = ()) -> dict:
    from importlib import metadata
    pk = {}
    for name in ("av", "opencv-python", "opencv-python-headless", "numpy", "pillow", "simplejpeg", "psutil", "winrt-runtime", "comtypes", "pyobjc-core", "linuxpy", *extra_packages):
        try:
            pk[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            pass
    env = {"os": platform.platform(), "machine": platform.machine(), "python": sys.version.split()[0], "packages": pk, "cpu_count": os.cpu_count()}
    if sys.platform == "win32":
        env["windows_build"] = platform.version()
    return env


# ---------------------------------------------------------------- cameras on this test machine
# Keys are short human names; the authoritative identity is the USB VID/PID + MF symbolic link.
# dshow_name is informational only: the Kiyo Pro's DirectShow FriendlyName is the generic "USB Video Device", so
# DirectShow/FFmpeg devices are always addressed by device path (dshow_alt_name) instead.
# max_mjpeg = largest MJPG frame size, then highest rate at that size, from the DirectShow/MF format lists
# (results/windows/Gerald/mjpeg_formats/).
WINDOWS_CAMERAS = {
    "c922": {"vidpid": "vid_046d&pid_085c", "dshow_name": "c922 Pro Stream Webcam", "max_mjpeg": (1920, 1080, 30)},
    "kiyo": {"vidpid": "vid_1532&pid_0e05", "dshow_name": "USB Video Device", "max_mjpeg": (1920, 1080, 60)},
    "c930e": {"vidpid": "vid_046d&pid_0843", "dshow_name": "Logitech Webcam C930e", "max_mjpeg": (1920, 1080, 30)},
    "usbcam": {"vidpid": "vid_4c4a&pid_4a55", "dshow_name": "USB Camera", "max_mjpeg": (1920, 1080, 30)},
}
COMMON_MODE = (1280, 720, 30)
# Cameras a run uses when none are named. The Razer Kiyo Pro is left out on purpose: the user excluded it as known
# flaky (it stops answering EP0 a few minutes after each plug-in, then every API fails with 0x8007001F), so harnesses
# never open it unless it is named explicitly with --cams.
DEFAULT_CAMS = ("c922", "c930e", "usbcam")
EXCLUDED_CAMS = {"kiyo": "excluded by the user as known flaky (2026-10-27 rerun); never opened unless named explicitly"}
MF_TOOL = HERE / "build" / "mf_mjpeg_capture.exe"


def cam_from_vidpid(text: str) -> str | None:
    t = (text or "").lower()
    for k, v in WINDOWS_CAMERAS.items():
        if v["vidpid"] in t or v["vidpid"].replace("&", "_") in t:
            return k
    return None


def dshow_devices() -> list[dict]:
    """DirectShow video-input enumeration (index order == OpenCV CAP_DSHOW index). Does not open any camera."""
    p = subprocess.run([str(MF_TOOL), "--list-dshow"], capture_output=True, text=True, timeout=60)
    return json.loads(p.stdout)["dshow_video_input_devices"]


def mf_devices_enum_only() -> list[dict]:
    """MFEnumDeviceSources order (== OpenCV CAP_MSMF index) without activating any source."""
    p = subprocess.run([str(MF_TOOL), "--list-enum"], capture_output=True, text=True, timeout=60)
    return json.loads(p.stdout)["devices"]


def dshow_alt_name(cam: str) -> str:
    """FFmpeg dshow 'alternative name' (@device_pnp_<device path>): unique even when FriendlyNames collide."""
    for d in dshow_devices():
        if WINDOWS_CAMERAS[cam]["vidpid"] in d["device_path"].lower():
            return "@device_pnp_" + d["device_path"]
    raise SystemExit(f"{cam} not found in DirectShow list")


def dshow_index(cam: str) -> int:
    for d in dshow_devices():
        if WINDOWS_CAMERAS[cam]["vidpid"] in d["device_path"].lower():
            return d["index"]
    raise SystemExit(f"{cam} not found in DirectShow list")


def msmf_index(cam: str) -> int:
    for i, d in enumerate(mf_devices_enum_only()):
        if WINDOWS_CAMERAS[cam]["vidpid"] in d["symbolic_link"].lower():
            return i
    raise SystemExit(f"{cam} not found in MF list")


def mf_controls(cams: list[str], set_manual: bool = True, exposure: int = -7, wb: int = 4500) -> dict:
    """Apply (and/or read back) exposure/white-balance/AE-priority with the MF tool. Settings persist
    in the device after the tool exits (verified: see results .../mjpeg_controls/)."""
    if not MF_TOOL.exists():
        return {"error": f"{MF_TOOL} not built"}
    cmd = [str(MF_TOOL)]
    for c in cams:
        cmd += ["--dev", WINDOWS_CAMERAS[c]["vidpid"]]
    cmd += ["--controls-only", "--via-dshow"]  # KS property path via the DirectShow filter; works even when MF activation fails
    if set_manual:
        cmd += ["--exposure", str(exposure), "--wb", str(wb), "--ae-priority", "0"]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    out = {}
    cur = None
    for line in p.stdout.splitlines():
        if ": before=" in line:
            cur, rest = line.split(": before=", 1)
            out[cur] = {"before": json.loads(rest)}
        elif line.startswith(" after=") and cur:
            out[cur]["after_set"] = json.loads(line[len(" after="):])
        elif line.startswith(" end=") and cur:
            out[cur]["end"] = json.loads(line[len(" end="):])
    return {"command": cmd, "returncode": p.returncode, "stderr": p.stderr[-2000:], "per_camera": out}


def frameserver_pid() -> int | None:
    """PID of the svchost hosting the Windows Camera Frame Server service (None if not running).
    FrameServer is demand-started, so call this while a camera is streaming."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes
    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    adv.OpenSCManagerW.restype = wintypes.HANDLE
    adv.OpenServiceW.restype = wintypes.HANDLE
    adv.OpenServiceW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, wintypes.DWORD]
    adv.QueryServiceStatusEx.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    adv.CloseServiceHandle.argtypes = [wintypes.HANDLE]
    scm = adv.OpenSCManagerW(None, None, 0x0001)
    if not scm:
        return None
    try:
        svc = adv.OpenServiceW(scm, "FrameServer", 0x0004)
        if not svc:
            return None
        buf = (wintypes.DWORD * 9)()
        need = wintypes.DWORD()
        ok = adv.QueryServiceStatusEx(svc, 0, buf, ctypes.sizeof(buf), ctypes.byref(need))
        adv.CloseServiceHandle(svc)
        return int(buf[7]) if ok and buf[7] else None
    finally:
        adv.CloseServiceHandle(scm)


_TSC_HZ: float | None = None


def _cycles_win(pid: int | None = None) -> int | None:
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.restype = wintypes.HANDLE
    k.GetCurrentProcess.restype = wintypes.HANDLE
    k.QueryProcessCycleTime.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_ulonglong)]
    h = k.GetCurrentProcess() if pid is None else k.OpenProcess(0x1000, False, pid)
    if not h:
        return None
    c = ctypes.c_ulonglong()
    ok = k.QueryProcessCycleTime(h, ctypes.byref(c))
    if pid is not None:
        k.CloseHandle(wintypes.HANDLE(h))
    return c.value if ok else None


def tsc_hz() -> float | None:
    """Cycle-counter rate, calibrated by spinning one thread for 0.3 s (QueryThreadCycleTime / wall)."""
    global _TSC_HZ
    if sys.platform != "win32":
        return None
    if _TSC_HZ is None:
        import ctypes
        from ctypes import wintypes
        k = ctypes.WinDLL("kernel32")
        k.GetCurrentThread.restype = wintypes.HANDLE
        k.QueryThreadCycleTime.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_ulonglong)]
        h = k.GetCurrentThread()
        c0, c1 = ctypes.c_ulonglong(), ctypes.c_ulonglong()
        best = 0.0
        for _ in range(3):
            k.QueryThreadCycleTime(h, ctypes.byref(c0)); t0 = time.perf_counter()
            while time.perf_counter() - t0 < 0.1:
                pass
            k.QueryThreadCycleTime(h, ctypes.byref(c1)); t1 = time.perf_counter()
            best = max(best, (c1.value - c0.value) / (t1 - t0))
        _TSC_HZ = best
    return _TSC_HZ


class CpuWindow:
    """CPU used by this process (and optional aux PIDs) between start() and stop().
    psutil cpu_times are tick-sampled (15.6 ms on Windows); on Windows the precise figure is
    QueryProcessCycleTime / calibrated cycle rate ("process_cpu_pct_of_one_core")."""

    def __init__(self, aux_pids: dict[str, int | None] | None = None):
        import psutil
        self.psutil = psutil
        self.proc = psutil.Process()
        self.aux = {k: v for k, v in (aux_pids or {}).items() if v}
        self.hz = tsc_hz()

    def _times(self, p):
        t = p.cpu_times()
        return t.user + t.system

    def start(self):
        self.a0 = {}
        for k, pid in self.aux.items():
            try:
                self.a0[k] = (self._times(self.psutil.Process(pid)), _cycles_win(pid) if self.hz else None)
            except Exception as e:  # access denied etc.
                self.a0[k] = repr(e)
        self.y0 = _cycles_win() if self.hz else None
        self.c0 = self._times(self.proc)
        self.t0 = time.perf_counter_ns()

    def stop(self) -> dict:
        t1 = time.perf_counter_ns()
        c1 = self._times(self.proc)
        y1 = _cycles_win() if self.hz else None
        wall = (t1 - self.t0) / 1e9
        res = {"method": "psutil cpu_times (tick-sampled) + QueryProcessCycleTime/calibrated cycle rate (Windows, precise)",
               "wall_s": wall, "process_cpu_s_ticks": c1 - self.c0,
               "process_cpu_pct_of_one_core_ticks": 100.0 * (c1 - self.c0) / wall if wall else None, "tsc_hz": self.hz}
        if self.hz and self.y0 is not None and y1 is not None:
            res["process_cycles"] = y1 - self.y0
            res["process_cpu_pct_of_one_core"] = 100.0 * (y1 - self.y0) / self.hz / wall
        else:
            res["process_cpu_pct_of_one_core"] = res["process_cpu_pct_of_one_core_ticks"]
        for k, pid in self.aux.items():
            res[f"{k}_pid"] = pid
            try:
                a0 = self.a0[k]
                if isinstance(a0, str):
                    res[f"{k}_error"] = a0
                    continue
                a1 = (self._times(self.psutil.Process(pid)), _cycles_win(pid) if self.hz else None)
                res[f"{k}_cpu_pct_of_one_core_ticks"] = 100.0 * (a1[0] - a0[0]) / wall
                res[f"{k}_cpu_pct_of_one_core"] = (100.0 * (a1[1] - a0[1]) / self.hz / wall) if (a0[1] is not None and a1[1] is not None) else None
            except Exception as e:
                res[f"{k}_error"] = repr(e)
        return res


class RunWriter:
    """Collects frames in memory during capture; flush() writes the run-dir contract files."""

    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.rows: list[dict] = []
        self.payloads: dict[int, list[tuple[int, bytes]]] = {}

    def add(self, cam_idx: int, row: dict, payload: bytes):
        row["cam_idx"] = cam_idx
        self.rows.append(row)
        self.payloads.setdefault(cam_idx, []).append((row["seq"], payload))

    def flush(self, meta: dict, window_start_ns: int, window_end_ns: int):
        for r in self.rows:
            r["in_window"] = window_start_ns <= r["host_arrival_ns"] <= window_end_ns
        meta.setdefault("window", {})
        meta["window"].update({"start_ns": window_start_ns, "end_ns": window_end_ns, "wall_s": (window_end_ns - window_start_ns) / 1e9})
        (self.run_dir / "meta.json").write_text(json.dumps(meta, indent=1))
        with open(self.run_dir / "frames.jsonl", "w") as f:
            for r in self.rows:
                f.write(json.dumps(r) + "\n")
        for cam, items in self.payloads.items():
            with open(self.run_dir / f"frames_{cam}.bin", "wb") as f:
                for seq, b in items:
                    f.write(struct.pack("<IQI", cam, seq, len(b)))
                    f.write(b)


# ---------------------------------------------------------------- validation + summary
def read_bin(path: Path):
    data = path.read_bytes()
    off = 0
    while off + 16 <= len(data):
        cam, seq, n = struct.unpack_from("<IQI", data, off)
        off += 16
        yield cam, seq, data[off:off + n]
        off += n


def jpeg_header(b: bytes) -> dict:
    """Walk JPEG marker segments up to SOS. Returns the marker sequence, APPn ids, the DQT/SOF/DHT segment bytes'
    SHA-1s and a 'fingerprint' over DQT+SOF+DHT. A camera's own encoder uses fixed (or few) quantisation tables and
    usually omits DHT (UVC MJPEG relies on the standard Huffman tables); a host-side decode + re-encode would emit
    a different DQT (Windows/libjpeg quality-scaled Annex K tables) and an explicit DHT. So equal fingerprints across
    APIs for the same camera+mode == the bytes came from the same (camera) encoder."""
    import hashlib
    out = {"markers": [], "app": [], "dqt_sha1": None, "sof_sha1": None, "dht_sha1": None, "fingerprint": None,
           "sof": None, "header_bytes": None, "header_sha1": None, "dri": None, "com": None, "bytes_before_soi": 0, "bytes_after_eoi": None}
    i = b.find(b"\xff\xd8")
    if i < 0:
        return out
    out["bytes_before_soi"] = i
    j = b.rfind(b"\xff\xd9")
    out["bytes_after_eoi"] = (len(b) - j - 2) if j >= 0 else None
    pos = i + 2
    dqt, sof, dht = [], [], []
    while pos + 4 <= len(b):
        if b[pos] != 0xFF:
            out["markers"].append(f"junk@{pos}")
            break
        m = b[pos + 1]
        if m == 0xFF:  # fill byte
            pos += 1
            continue
        ln = (b[pos + 2] << 8) | b[pos + 3]
        seg = b[pos + 4:pos + 2 + ln]
        name = {0xC0: "SOF0", 0xC1: "SOF1", 0xC2: "SOF2", 0xC4: "DHT", 0xDB: "DQT", 0xDD: "DRI", 0xDA: "SOS", 0xFE: "COM"}.get(m, f"APP{m - 0xE0}" if 0xE0 <= m <= 0xEF else f"FF{m:02X}")
        out["markers"].append(name)
        if name == "DQT":
            dqt.append(seg)
        elif name.startswith("SOF"):
            sof.append(seg)
            if len(seg) >= 6:
                nc = seg[5]
                comps = [{"id": seg[6 + 3 * k], "hv": f"{seg[7 + 3 * k] >> 4}x{seg[7 + 3 * k] & 15}", "tq": seg[8 + 3 * k]} for k in range(nc) if 8 + 3 * k < len(seg)]
                out["sof"] = {"type": name, "precision": seg[0], "h": (seg[1] << 8) | seg[2], "w": (seg[3] << 8) | seg[4], "components": comps}
        elif name == "DHT":
            dht.append(seg)
        elif name == "DRI" and len(seg) >= 2:
            out["dri"] = (seg[0] << 8) | seg[1]
        elif name == "COM":
            out["com"] = seg[:64].decode("latin-1")
        elif name.startswith("APP"):
            out["app"].append({"marker": name, "len": ln, "id": seg[:5].split(b"\x00")[0].decode("latin-1", "replace")})
        if name == "SOS":
            out["header_bytes"] = pos + 2 + ln - i
            out["header_sha1"] = hashlib.sha1(b[i:pos + 2 + ln]).hexdigest()[:12]
            break
        pos += 2 + ln
    h = lambda parts: hashlib.sha1(b"".join(parts)).hexdigest()[:12] if parts else None
    out["dqt_sha1"], out["sof_sha1"], out["dht_sha1"] = h(dqt), h(sof), h(dht)
    out["fingerprint"] = hashlib.sha1(b"|".join([b"".join(dqt), b"".join(sof), b"".join(dht)])).hexdigest()[:12]
    out["dqt_q0_first8"] = list(dqt[0][1:9]) if dqt and len(dqt[0]) > 9 else None  # first 8 luma quant values (zigzag order)
    return out


def validate_jpeg(b: bytes, want_wh: tuple[int, int] | None = None) -> dict:
    from PIL import Image
    import simplejpeg
    soi = len(b) >= 2 and b[:2] == b"\xff\xd8"
    eoi_end = len(b) >= 2 and b[-2:] == b"\xff\xd9"
    # some cameras pad after EOI; record whether EOI exists anywhere in the last 1 KiB
    eoi_tail = b.rfind(b"\xff\xd9", max(0, len(b) - 1024)) >= 0
    has_dht = b.find(b"\xff\xc4", 0, 4096) >= 0
    pil_ok, pil_err, wh = False, None, None
    try:
        im = Image.open(io.BytesIO(b))
        im.load()
        pil_ok, wh = True, im.size
    except Exception as e:
        pil_err = repr(e)[:200]
    sj_ok, sj_err = False, None
    try:
        arr = simplejpeg.decode_jpeg(b, fastdct=True)
        sj_ok = True
        wh = wh or (arr.shape[1], arr.shape[0])
    except Exception as e:
        sj_err = repr(e)[:200]
    # libjpeg-turbo *warnings* (e.g. "Corrupt JPEG data: N extraneous bytes before marker 0xd9") are fatal in
    # simplejpeg's default strict mode; a lenient decode tells warning-level defects (image intact) from real errors.
    sj_lenient_ok = sj_ok
    if not sj_ok:
        try:
            arr = simplejpeg.decode_jpeg(b, fastdct=True, strict=False)
            sj_lenient_ok = True
            wh = wh or (arr.shape[1], arr.shape[0])
        except Exception:
            pass
    size_ok = (wh == tuple(want_wh)) if (want_wh and wh) else None
    return {"soi": soi, "eoi_at_end": eoi_end, "eoi_in_tail": eoi_tail, "has_dht": has_dht, "pillow_ok": pil_ok, "simplejpeg_ok": sj_ok,
            "simplejpeg_lenient_ok": sj_lenient_ok, "libjpeg_warning": sj_err if (sj_lenient_ok and not sj_ok) else None,
            "pillow_err": pil_err, "simplejpeg_err": sj_err, "wh": wh, "size_ok": size_ok,
            "valid": bool(soi and eoi_tail and pil_ok and sj_lenient_ok and size_ok is not False),
            "valid_strict": bool(soi and eoi_tail and pil_ok and sj_ok and size_ok is not False)}


TIMESTAMP_FIELDS = ("os_timestamp_ns", "pkt_pts", "pos_msec", "readsample_ts_hns", "sample_time_hns", "device_timestamp", "device_reference_system_time",
                    "mfsampleextension_timestamp", "first_scanline_qpc", "last_scanline_qpc", "uvc_payloadheader_bytes", "duration_ns", "sample_duration_hns",
                    "uvc_pts", "uvc_scr_stc", "v4l2_sequence", "pts_host_ns", "winrt_props_ts")


def _stats(xs):
    if not xs:
        return None
    xs = sorted(xs)
    return {"n": len(xs), "min": xs[0], "p50": xs[len(xs) // 2], "mean": statistics.fmean(xs), "p95": xs[int(0.95 * (len(xs) - 1))], "max": xs[-1]}


def summarize_run(run_dir: Path, out_dir: Path, *, test: str, command: list[str] | str, extra: dict | None = None,
                  keep_samples: int = 0, payload_is_jpeg: bool | None = None) -> dict:
    run_dir, out_dir = Path(run_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = json.loads((run_dir / "meta.json").read_text())
    if str(meta.get("backend", "")).startswith("msmf") and "decoded_by_pipeline" not in meta:  # C++ tool: derive from the reader state
        outs = [c.get("reader_output_subtype") for c in meta.get("cameras", [])]
        meta["decoded_by_pipeline"] = bool(meta.get("decode_to")) or any(o != "MJPG" for o in outs)
        meta["decode_evidence"] = (f"MF_READWRITE_DISABLE_CONVERTERS={meta.get('disable_converters')}; native MJPG media type set on the source; "
                                   f"IMFSourceReader::GetCurrentMediaType subtype per camera = {outs} (MJPG => no decoder MFT in the reader)")
        meta["delivered_codecs"] = outs
        meta["silent_format_fallback"] = (not meta.get("decode_to")) and any(o != "MJPG" for o in outs)
    if payload_is_jpeg is None:  # backend says whether its payload bytes are JPEG (e.g. WinRT handing over NV12)
        payload_is_jpeg = bool(meta.get("payload_is_jpeg", True))
    rows = [json.loads(l) for l in (run_dir / "frames.jsonl").read_text().splitlines() if l.strip()]
    req = meta.get("requested", {})
    want_wh = (req.get("width"), req.get("height")) if req.get("width") else None
    # per-camera requested mode (all-cameras-at-own-max runs) overrides the run-level one
    cam_req = {c["idx"]: c["requested_mode"] for c in meta.get("cameras", []) if isinstance(c.get("requested_mode"), dict)}
    by_key = {(r["cam_idx"], r["seq"]): r for r in rows}
    val_by_cam: dict[int, list[dict]] = {}
    hdr_by_cam: dict[int, list[dict]] = {}
    samples_written: list[str] = []
    for binf in sorted(run_dir.glob("frames_*.bin")):
        kept = 0
        for cam, seq, b in read_bin(binf):
            r = by_key.get((cam, seq))
            if r is None:
                continue
            if payload_is_jpeg and len(b) > 0:
                cr = cam_req.get(cam)
                v = validate_jpeg(b, (cr["width"], cr["height"]) if cr else want_wh)
                r["is_valid_jpeg"] = v["valid"]
                r["jpeg_check"] = {k: v[k] for k in ("soi", "eoi_at_end", "eoi_in_tail", "has_dht", "pillow_ok", "simplejpeg_ok", "simplejpeg_lenient_ok", "size_ok")}
                if v["libjpeg_warning"]:
                    r["jpeg_check"]["libjpeg_warning"] = v["libjpeg_warning"]
                if not v["valid"]:
                    r["jpeg_check"]["errors"] = [v["pillow_err"], v["simplejpeg_err"], v["wh"]]
                val_by_cam.setdefault(cam, []).append(v)
                if v["valid"] and r.get("in_window") and seq % 30 == 0:
                    r["mean_luma"] = jpeg_luma(b)
                hd = jpeg_header(b)
                r["jpeg_fingerprint"] = hd["fingerprint"]
                hdr_by_cam.setdefault(cam, []).append(hd)
                if keep_samples and kept < keep_samples and v["valid"] and r.get("in_window") and seq >= 30:
                    # privacy: frames show the user's room -> keep only the JPEG header (SOI..SOS segment: tables,
                    # markers, no entropy-coded image data). Enough for byte-identical header comparison across APIs.
                    name = f"sample_cam{cam}_seq{seq}.jpghdr"
                    (out_dir / name).write_bytes(b[:hd["header_bytes"] + hd["bytes_before_soi"]] if hd.get("header_bytes") else b[:600])
                    samples_written.append(name)
                    kept += 1
            else:
                r["is_valid_jpeg"] = None
    with open(out_dir / "frames.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    cams_out = []
    wall = meta.get("window", {}).get("wall_s") or 0
    for cam_meta in meta.get("cameras", []):
        ci = cam_meta["idx"]
        cr = [r for r in rows if r["cam_idx"] == ci]
        win = [r for r in cr if r.get("in_window")]
        arr = [r["host_arrival_ns"] for r in win]
        d = [(b - a) / 1e6 for a, b in zip(arr, arr[1:])]
        fps_span = (len(arr) - 1) / ((arr[-1] - arr[0]) / 1e9) if len(arr) > 2 else None
        fps_req = (cam_req.get(ci) or {}).get("fps") or req.get("fps")
        period = 1000.0 / fps_req if fps_req else None
        late = sum(1 for x in d if period and x > 1.5 * period)
        osd = []
        ost = [r.get("os_timestamp_ns") for r in win]
        if all(isinstance(x, int) for x in ost) and len(ost) > 2:
            osd = [(b - a) / 1e6 for a, b in zip(ost, ost[1:])]
        vals = val_by_cam.get(ci, [])
        vwin = [r for r in win if r.get("is_valid_jpeg") is not None]
        hdrs = hdr_by_cam.get(ci, [])
        fp_counts: dict[str, int] = {}
        hs_counts: dict[str, int] = {}
        for hd in hdrs:
            fp_counts[hd["fingerprint"]] = fp_counts.get(hd["fingerprint"], 0) + 1
            hs_counts[str(hd["header_sha1"])] = hs_counts.get(str(hd["header_sha1"]), 0) + 1
        hdr_first = hdrs[len(hdrs) // 2] if hdrs else None
        # which timestamp-like fields this API attached (non-null count among in-window frames)
        ts_fields = {}
        for k in TIMESTAMP_FIELDS:
            n_present = sum(1 for r in win if r.get(k) is not None)
            if n_present:
                ts_fields[k] = n_present
        lumas = [r["mean_luma"] for r in win if isinstance(r.get("mean_luma"), (int, float))]
        lat = [(r["host_arrival_ns"] - r["os_timestamp_ns"]) / 1e6 for r in win if isinstance(r.get("os_timestamp_ns"), int)]
        lat_med = sorted(lat)[len(lat) // 2] if lat else None
        lat_jit = _stats([abs(x - lat_med) for x in lat]) if lat else None
        cams_out.append({
            **{k: cam_meta.get(k) for k in cam_meta if k not in ("sample_attribute_dumps", "native_types")},
            "frames_delivered_total": len(cr),
            "frames_in_window": len(win),
            "fps_requested": fps_req,
            "fps_achieved_count_over_wall": len(win) / wall if wall else None,
            "fps_achieved_span": fps_span,
            "inter_arrival_ms": _stats(d),
            "gaps_over_1p5_period": late,
            "os_timestamp_delta_ms": _stats(osd),
            "payload_bytes": _stats([r["payload_bytes"] for r in win]),
            "mean_luma": ({**_stats(lumas), "method": "mean of 8-bit luma, every 30th in-window frame (JPEG: simplejpeg GRAY 1/8 scale; pixels: capture script)"} if lumas else None),
            "pct_valid_jpeg_in_window": (100.0 * sum(1 for r in vwin if r["is_valid_jpeg"]) / len(vwin)) if vwin else None,
            "pct_valid_jpeg_all": (100.0 * sum(1 for v in vals if v["valid"]) / len(vals)) if vals else None,
            "pct_valid_jpeg_strict_all": (100.0 * sum(1 for v in vals if v["valid_strict"]) / len(vals)) if vals else None,
            "libjpeg_warnings_sample": sorted({(v["libjpeg_warning"] or "")[:90] for v in vals if v["libjpeg_warning"]})[:3],
            "jpeg_checks_all": {k: sum(1 for v in vals if v[k]) for k in ("soi", "eoi_at_end", "eoi_in_tail", "has_dht", "pillow_ok", "simplejpeg_ok", "simplejpeg_lenient_ok")} if vals else None,
            "n_validated": len(vals),
            "cam": cam_meta.get("cam") or (cam_meta.get("name") if cam_meta.get("name") in WINDOWS_CAMERAS else None) or cam_from_vidpid(json.dumps(cam_meta)),
            "jpeg_header": ({"fingerprints": fp_counts, "header_sha1s": hs_counts, "markers": hdr_first["markers"], "app": hdr_first["app"], "sof": hdr_first["sof"],
                             "dqt_sha1": hdr_first["dqt_sha1"], "dht_sha1": hdr_first["dht_sha1"], "dqt_q0_first8": hdr_first.get("dqt_q0_first8"),
                             "has_dht": hdr_first["dht_sha1"] is not None, "header_bytes": hdr_first["header_bytes"], "com": hdr_first["com"],
                             "bytes_after_eoi_max": max((hd["bytes_after_eoi"] or 0) for hd in hdrs)} if hdrs else None),
            "os_timestamp_source": next((r.get("os_timestamp_source") for r in win if r.get("os_timestamp_source")), None),
            "timestamp_fields_present": ts_fields,
            "arrival_minus_os_timestamp_ms": ({"median": lat_med, "abs_dev_from_median": lat_jit,
                                               "note": "host_arrival_ns - os_timestamp_ns; a latency only when os_timestamp_ns is on the host QPC clock (true for MF llTimestamp and WinRT SystemRelativeTime by documentation; FFmpeg dshow pts = DirectShow stream time + FFmpeg start offset, which lands in the QPC domain on this machine: see the median)"} if lat else None),
        })
    n = max(1, len(cams_out))
    cpu = meta.get("cpu", {})
    pc = cpu.get("process_cpu_pct_of_one_core")
    summary = {
        "test": test, "platform": plat(), "hostname": HOST, "utc_started": meta.get("utc_started"), "utc_summarized": utc_now(),
        "command": command, "environment": meta.get("environment") or environment(),
        "backend": meta.get("backend"), "requested": req, "decoded_by_pipeline": meta.get("decoded_by_pipeline"),
        "decode_evidence": meta.get("decode_evidence"), "window": meta.get("window"),
        "delivered_codecs": meta.get("delivered_codecs"), "silent_format_fallback": meta.get("silent_format_fallback"),
        "cpu": {**cpu, "process_cpu_pct_per_camera": (pc / n) if pc is not None else None},
        "cameras": cams_out, "samples": samples_written, **(extra or {}),
    }
    if (run_dir / "controls.json").exists():
        cj = json.loads((run_dir / "controls.json").read_text())
        def _short(block):
            out = {}
            for cam, d in (block or {}).get("per_camera", {}).items():
                st = d.get("end") or d.get("after_set") or d.get("before") or {}
                out[cam] = {k: (st.get(k) or {}).get("value") for k in ("exposure_log2s", "white_balance_k", "auto_exposure_priority", "gain")}
                out[cam].update({k + "_mode": (st.get(k) or {}).get("flags_meaning") for k in ("exposure_log2s", "white_balance_k")})
            return out
        def _dn(block):
            return {f"{d.get('cam')}:{d.get('id', '').split(chr(92))[1] if chr(92) in d.get('id', '') else d.get('id')}": d.get("devnode_hex")
                    for d in (block or {}).get("devices", [])} if block else None
        summary["devnode_status"] = {"before": _dn(cj.get("devnode_status_before")), "after": _dn(cj.get("devnode_status_after"))}
        summary["machine_cpu"] = {"before": cj.get("machine_cpu_before"), "after": cj.get("machine_cpu_after"),
                                  "note": "whole-machine CPU% (psutil, 1 s) right before and after the capture; other agents run concurrently"}
        summary["controls"] = {"requested": cj.get("requested"), "after_apply": _short(cj.get("apply")), "readback_after_capture": _short(cj.get("readback_after_capture")),
                               "apply_rc": (cj.get("apply") or {}).get("returncode"), "readback_rc": (cj.get("readback_after_capture") or {}).get("returncode")}
        (out_dir / "controls.json").write_text(json.dumps(cj, indent=1))
    for k in ("controls", "notes", "backend_details", "errors", "delivered_codecs", "silent_format_fallback", "cv2_version", "open_wait_s"):
        if k in meta:
            summary[k] = meta[k]
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    # keep the raw MF attribute dumps (timing agent wants them) alongside
    if any("sample_attribute_dumps" in c for c in meta.get("cameras", [])):
        (out_dir / "sample_attribute_dumps.json").write_text(json.dumps({c["idx"]: c.get("sample_attribute_dumps") for c in meta["cameras"]}, indent=1))
    return summary


def brief(summary: dict) -> str:
    lines = [f"{summary['backend']} {summary['requested']} decoded={summary.get('decoded_by_pipeline')} cpu={summary['cpu'].get('process_cpu_pct_of_one_core')}"]
    for c in summary["cameras"]:
        lines.append(f"  cam{c.get('idx')} {c.get('name') or c.get('camera_key')}: fps={c['fps_achieved_span'] and round(c['fps_achieved_span'], 2)} "
                     f"n={c['frames_in_window']} valid%={c['pct_valid_jpeg_in_window']} bytes_p50={c['payload_bytes'] and c['payload_bytes']['p50']} gaps={c['gaps_over_1p5_period']}")
    return "\n".join(lines)


def devnode_status() -> dict:
    """PnP DevNodeStatus of every test camera's interface + composite parent (Windows; no elevation, opens no camera).
    DN_NEED_RESTART = 0x100, DN_HAS_PROBLEM = 0x400. Used to tag each capture with the device state at that moment."""
    if sys.platform != "win32":
        return {}
    ps = ("$o=@(); Get-PnpDevice -PresentOnly | ? { $_.InstanceId -match '^USB.VID_(046D&PID_085C|046D&PID_0843|1532&PID_0E05|4C4A&PID_4A55)' } | % { "
          "$s=(Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName DEVPKEY_Device_DevNodeStatus).Data; "
          "$p=(Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName DEVPKEY_Device_ProblemCode).Data; "
          "$o += [pscustomobject]@{id=$_.InstanceId; name=$_.FriendlyName; status=$_.Status; devnode=[int64]$s; problem=$p} }; $o | ConvertTo-Json -Compress")
    try:
        p = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=60)
        items = json.loads(p.stdout) if p.stdout.strip() else []
    except Exception as e:  # never fail a capture because of this
        return {"error": repr(e)}
    if isinstance(items, dict):
        items = [items]
    out = {"utc": utc_now(), "devices": []}
    for it in items:
        dn = it.get("devnode") or 0
        it.update({"devnode_hex": f"0x{dn:08X}", "need_restart": bool(dn & 0x100), "has_problem": bool(dn & 0x400), "cam": cam_from_vidpid(it.get("id", ""))})
        out["devices"].append(it)
    return out
