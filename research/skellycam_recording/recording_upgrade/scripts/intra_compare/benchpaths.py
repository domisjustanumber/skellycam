"""Shared code for the 23:00 matched-quality intra benches (bench_matched_stream.py, bench_matched_concurrent.py).

Implementation under test: PyAV 19.0.2 (FFmpeg 9.0.2), simplejpeg 1.9.0 (libjpeg-turbo 3.1.2),
nvidia-nvimgcodec-cu12 0.10.0.9 (nvJPEG). Encoder settings come from results/intra_compare/matched_settings.json
(target A = camera-equivalent SSIM-Y 0.9961; target B = PSNR-Y 45 dB, key 'psnr45').

Sources (what a camera loop receives; everything before the timed loop is prepared untimed):
  nv12       NV12 array made from the real YUY2 frames (4:2:0 chroma = rounded vertical average, iclib.down420).
             Only 4:2:0 paths.
  yuy2       packed YUY2 bytes (the real 1080p frames; 720p = swscale-scaled, as in iclib/benchlib).
             4:2:2 paths that take yuyv422 (mjpeg_qsv_422, hevc_qsv_422) get the packed frame directly ("native").
  mjpeg_cpu  unmodified camera JPEG bytes -> PyAV 'mjpeg' software decode in the timed loop.
  mjpeg_qsv  unmodified camera JPEG bytes -> 'mjpeg_qsv' decode (Intel iGPU) in the timed loop. Only 4:2:0 paths.
  rgb        nvJPEG only: exact float BT.601 RGB prepared untimed (the input the matched sweep used), so the timed
             loop is the nvJPEG encode call alone (host RGB -> JPEG bytes).
Range: JPEG paths are fed full range, H.264/HEVC limited range (matched_settings _meta.apply). For the nv12/yuy2
sources the range change is done untimed in numpy (iclib.map_range); for decoded MJPEG it is done by swscale in the
loop (dst_color_range=1), as a recorder would. Every reformat passes src_color_range/dst_color_range explicitly
(PyAV keeps or guesses the range otherwise: results/hw_accel_target/NOTES_functional.md section 6).
Decoded MJPEG frames carry pict_type=I; it is reset to NONE (harmless for intra, kept identical to the hw benches).

A quality check (untimed, separate from the timed reps) encodes the first K source frames with the same pipeline,
decodes them in PyAV software and reports PSNR-Y / SSIM-Y against the source Y (source domain, as in iclib.metrics),
so each bench row shows the quality it actually ran at.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
from av.video.frame import PictureType

sys.path.insert(0, str(Path(__file__).parent))
import iclib  # noqa: E402

MATCHED = iclib.RESULTS / "matched_settings.json"
BENCH = iclib.RESULTS / "bench"
DIMS = {"720p": (1280, 720), "1080p": (1920, 1080)}
RANGE_CODE = {"lim": 1, "full": 2}  # AVColorRange: 1 = MPEG (limited), 2 = JPEG (full)

ALL_PATHS = ["jpeg_turbo_422", "jpeg_turbo_420", "ff_mjpeg_422", "ff_mjpeg_420", "mjpeg_qsv_422", "mjpeg_qsv_420",
             "nvjpeg_422", "nvjpeg_420", "h264_nvenc_420", "hevc_nvenc_420", "h264_qsv_420", "hevc_qsv_420",
             "hevc_qsv_422", "libx264_ultrafast_420", "libx264_veryfast_420", "libx265_ultrafast_420"]
ALL_SOURCES = ["nv12", "yuy2", "mjpeg_cpu", "mjpeg_qsv", "rgb"]


def load_matched() -> dict:
    return json.loads(MATCHED.read_text(encoding="utf-8"))


def entry(matched: dict, path: str, input_class: str, target: str) -> dict:
    e = matched[path][input_class]
    return e["psnr45"] if target == "B" else e


def input_class(source: str, size: str) -> str:
    return ("mjpeg_" if source.startswith("mjpeg") else "yuy2_") + size


def compatible(path: str, source: str) -> tuple[bool, str]:
    p = iclib.PATHS[path]
    if source == "rgb":
        return (p["enc"] == "nvjpeg", "rgb source is nvJPEG-only")
    if source in ("nv12", "mjpeg_qsv") and p["chroma"] == "4:2:2":
        return False, "4:2:0 source; a 4:2:2 path would only upsample"
    return True, ""


def is_qsv(path: str, source: str) -> bool:
    return "qsv" in path or source == "mjpeg_qsv"


def is_nvidia(path: str) -> bool:
    return "nvenc" in path or "nvjpeg" in path


# ------------------------------------------------------------------ prepared source data (untimed)
class Prepared:
    """Per (path, source, size): the per-frame inputs in the form the source delivers, already in the path's range."""

    def __init__(self, path: str, source: str, size: str, srcs: list | None = None):
        self.path, self.source, self.size = path, source, size
        self.p = iclib.PATHS[path]
        self.w, self.h = DIMS[size]
        self.rng = "full" if self.p["family"] == "jpeg" else "lim"
        self.srcs = srcs if srcs is not None else iclib.load_input(input_class(source, size))
        if source == "nv12":
            self.data = [iclib.nv12_array(*iclib.map_range([s.y, s.u420, s.v420], s.rng, self.rng)) for s in self.srcs]
        elif source == "yuy2":
            self.data = [iclib.yuyv_pack(*iclib.map_range([s.y, s.u, s.v], s.rng, self.rng)).tobytes() for s in self.srcs]
        elif source == "rgb":
            self.data = [iclib.rgb_from_src(s) for s in self.srcs]
        else:
            self.data = [s.jpeg for s in self.srcs]


def frame_from_packed(buf: bytes, w: int, h: int, rng: str) -> av.VideoFrame:
    f = av.VideoFrame(w, h, "yuyv422")
    p = f.planes[0]
    row = w * 2
    if p.line_size == row:
        p.update(buf)
    else:
        np.frombuffer(p, np.uint8).reshape(h, p.line_size)[:, :row] = np.frombuffer(buf, np.uint8).reshape(h, row)
    f.color_range = RANGE_CODE[rng]
    return f


def planes_of(f: av.VideoFrame, chroma_h_div: int) -> list[np.ndarray]:
    w, h = f.width, f.height
    return [iclib.plane_array(f, 0, w, h), iclib.plane_array(f, 1, w // 2, h // chroma_h_div),
            iclib.plane_array(f, 2, w // 2, h // chroma_h_div)]


# ------------------------------------------------------------------ encoders
class Encoder:
    """One encode path at a fixed matched setting. encode(x) -> list of output bytes objects (may be empty)."""

    def __init__(self, path: str, w: int, h: int, e: dict):
        self.path, self.e = path, e
        self.p = iclib.PATHS[path]
        self.kind = self.p["enc"]
        self.opts = dict(e["options"])
        self.cc = None
        if self.kind == "simplejpeg":
            import simplejpeg  # noqa: PLC0415
            self.sj = simplejpeg
            self.q = int(self.opts["quality"])
        elif self.kind == "nvjpeg":
            from nvidia import nvimgcodec as nv  # noqa: PLC0415
            self.nvenc = nv.Encoder(encoder_ids=["nvjpeg_cuda_encoder"])
            css = nv.ChromaSubsampling.CSS_422 if self.opts["chroma_subsampling"] == "CSS_422" else nv.ChromaSubsampling.CSS_420
            self.params = nv.EncodeParams(quality_type=nv.QualityType.QUALITY,
                                          quality_value=int(self.opts["quality_value"]), chroma_subsampling=css)
        else:
            cc = av.CodecContext.create(self.kind, "w")
            cc.width, cc.height, cc.pix_fmt = w, h, e["pix_fmt_fed"]
            cc.time_base, cc.framerate = Fraction(1, 30), Fraction(30, 1)
            cc.gop_size = int(e.get("gop_size", 1))
            if self.p["family"] != "jpeg":
                cc.max_b_frames = 0
            cc.options = {k: str(v) for k, v in self.opts.items()}
            cc.open()
            self.cc = cc
        self.n = 0

    def encode(self, x) -> list:
        if self.kind == "simplejpeg":
            return [self.sj.encode_jpeg_yuv_planes(*x, quality=self.q, fastdct=False)]
        if self.kind == "nvjpeg":
            cs = self.nvenc.encode(x, "jpeg", params=self.params)
            if cs is None:
                raise RuntimeError("nvimgcodec encode returned None")
            return [bytes(cs)]
        x.pts = self.n
        self.n += 1
        return [bytes(pk) for pk in self.cc.encode(x)]

    def flush(self) -> list:
        if self.cc is None:
            return []
        return [bytes(pk) for pk in self.cc.encode(None)]


# ------------------------------------------------------------------ per-frame feed (timed work before encode)
class Feed:
    """Turns the next prepared input into exactly what the encoder takes, doing the per-frame work in the loop."""

    def __init__(self, prep: Prepared):
        self.prep, self.i = prep, 0
        self.p, self.rng, self.w, self.h = prep.p, prep.rng, prep.w, prep.h
        self.kind = self.p["enc"]
        self.fmt = self.p.get("fmt")
        self.dec = None
        if prep.source in ("mjpeg_cpu", "mjpeg_qsv"):
            self.dec = av.CodecContext.create("mjpeg" if prep.source == "mjpeg_cpu" else "mjpeg_qsv", "r")
            self.pending: list = []

    def _decoded(self) -> av.VideoFrame:
        data = self.prep.data
        while not self.pending:
            self.pending += list(self.dec.decode(av.Packet(data[self.i % len(data)])))
            self.i += 1
        return self.pending.pop(0)

    def _reformat(self, f: av.VideoFrame, fmt: str, src_rng: str) -> av.VideoFrame:
        g = f.reformat(format=fmt, src_color_range=RANGE_CODE[src_rng], dst_color_range=RANGE_CODE[self.rng])
        g.pict_type = PictureType.NONE
        return g

    def next(self):
        src = self.prep.source
        if src == "rgb":
            x = self.prep.data[self.i % len(self.prep.data)]
            self.i += 1
            return x
        if src == "nv12":
            arr = self.prep.data[self.i % len(self.prep.data)]
            self.i += 1
            if self.kind == "simplejpeg":  # 4:2:0 planes from NV12: de-interleave the UV plane
                h = self.h
                uv = arr[h:]
                return [arr[:h], np.ascontiguousarray(uv[:, 0::2]), np.ascontiguousarray(uv[:, 1::2])]
            f = av.VideoFrame.from_ndarray(arr, format="nv12")
            f.color_range = RANGE_CODE[self.rng]
            if self.kind == "nvjpeg":
                return self._reformat(f, "rgb24", self.rng).to_ndarray()
            return f if self.fmt == "nv12" else self._reformat(f, self.fmt, self.rng)
        if src == "yuy2":
            buf = self.prep.data[self.i % len(self.prep.data)]
            self.i += 1
            if self.kind == "simplejpeg" and self.p["chroma"] == "4:2:2":  # numpy unpack of YUYV
                a = np.frombuffer(buf, np.uint8).reshape(self.h, self.w * 2)
                return [np.ascontiguousarray(a[:, 0::2]), np.ascontiguousarray(a[:, 1::4]),
                        np.ascontiguousarray(a[:, 3::4])]
            f = frame_from_packed(buf, self.w, self.h, self.rng)
            if self.kind == "simplejpeg":  # 4:2:0: swscale to yuvj420p, then planes
                return planes_of(self._reformat(f, "yuvj420p", self.rng), 2)
            if self.kind == "nvjpeg":
                return self._reformat(f, "rgb24", self.rng).to_ndarray()
            return f if self.fmt == "yuyv422" else self._reformat(f, self.fmt, self.rng)
        # mjpeg_cpu / mjpeg_qsv: decoded camera frame (full range; yuvj422p from mjpeg, nv12 from mjpeg_qsv)
        f = self._decoded()
        if self.kind == "simplejpeg":
            if f.format.name == "nv12":
                g = self._reformat(f, "yuvj420p", "full")
                return planes_of(g, 2)
            if self.p["chroma"] == "4:2:2" and f.format.name == "yuvj422p":
                return planes_of(f, 1)
            return planes_of(self._reformat(f, "yuvj420p", "full"), 2)
        if self.kind == "nvjpeg":
            return self._reformat(f, "rgb24", "full").to_ndarray()
        if f.format.name == self.fmt and self.rng == "full":
            f.pict_type = PictureType.NONE
            return f
        return self._reformat(f, self.fmt, "full")


# ------------------------------------------------------------------ quality check (untimed)
def decode_y(datas: list[bytes], path: str) -> tuple[list[np.ndarray], str]:
    fam = iclib.PATHS[path]["family"]
    out = []
    if fam == "jpeg":
        dec = av.CodecContext.create("mjpeg", "r")
        for d in datas:
            for fr in dec.decode(av.Packet(d)):
                out.append(iclib.plane_array(fr, 0, fr.width, fr.height))
        return out, "full"
    dec = av.CodecContext.create(fam, "r")
    for d in datas:
        for fr in dec.decode(av.Packet(d)):
            out.append(iclib.plane_array(fr, 0, fr.width, fr.height))
    for fr in dec.decode(None):
        out.append(iclib.plane_array(fr, 0, fr.width, fr.height))
    return out, "lim"


def quality_check(prep: Prepared, e: dict, k: int = 4) -> dict:
    try:
        enc = Encoder(prep.path, prep.w, prep.h, e)
        feed = Feed(prep)
        datas = []
        for _ in range(k):
            datas += enc.encode(feed.next())
        datas += enc.flush()
        ys, out_rng = decode_y(datas, prep.path)
        ps, ss = [], []
        for j, y in enumerate(ys[:k]):
            s = prep.srcs[j % len(prep.srcs)]
            yf = y.astype(np.float32)
            if out_rng != s.rng:
                yf = iclib.lim2full_f(yf) if (out_rng, s.rng) == ("lim", "full") else iclib.full2lim_f(yf)
            ref = s.y.astype(np.float32)
            ps.append(iclib.psnr_mse(float(np.mean((yf - ref) ** 2))))
            ss.append(iclib.ssim(ref, yf))
        return {"frames": len(ys[:k]), "psnr_y": round(float(np.mean(ps)), 3) if ps else None,
                "ssim_y": round(float(np.mean(ss)), 5) if ss else None,
                "bytes_per_frame": round(sum(map(len, datas)) / max(len(datas), 1)),
                "matched_psnr_y": e.get("psnr_y"), "matched_ssim_y": e.get("ssim_y"),
                "matched_bytes_per_frame": e.get("bytes_per_frame")}
    except Exception as ex:  # noqa: BLE001
        return {"error": f"{type(ex).__name__}: {ex}"[:300]}


# ------------------------------------------------------------------ GPU utilisation samplers
QUERY = "encoder.stats.sessionCount,utilization.gpu,utilization.encoder,utilization.decoder"


def nvidia_smi_now() -> str:
    try:
        return subprocess.run(["nvidia-smi", f"--query-gpu={QUERY}", "--format=csv,noheader"], capture_output=True,
                              text=True, timeout=20).stdout.strip()
    except Exception as ex:  # noqa: BLE001
        return f"nvidia-smi failed: {ex!r}"


def dxgi_adapters() -> dict:
    """LUID string ('0x%08X_0x%08X' high_low as in GPU Engine instance names) -> adapter description, via DXGI."""
    import ctypes  # noqa: PLC0415
    from ctypes import wintypes  # noqa: PLC0415

    class GUID(ctypes.Structure):
        _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16), ("c", ctypes.c_uint16), ("d", ctypes.c_ubyte * 8)]

    class DESC1(ctypes.Structure):
        _fields_ = [("Description", ctypes.c_wchar * 128), ("VendorId", wintypes.UINT), ("DeviceId", wintypes.UINT),
                    ("SubSysId", wintypes.UINT), ("Revision", wintypes.UINT), ("DedicatedVideoMemory", ctypes.c_size_t),
                    ("DedicatedSystemMemory", ctypes.c_size_t), ("SharedSystemMemory", ctypes.c_size_t),
                    ("LuidLow", wintypes.DWORD), ("LuidHigh", wintypes.LONG), ("Flags", wintypes.UINT)]

    iid = GUID(0x770AAE78, 0xF26F, 0x4DBA, (ctypes.c_ubyte * 8)(0xA8, 0x29, 0x25, 0x3C, 0x83, 0xD1, 0xB3, 0x87))
    fac = ctypes.c_void_p()
    if ctypes.windll.dxgi.CreateDXGIFactory1(ctypes.byref(iid), ctypes.byref(fac)) != 0:
        return {}

    def vcall(obj, idx, restype, *argtypes):
        vt = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vt[idx])

    out = {}
    i = 0
    while True:
        ad = ctypes.c_void_p()
        hr = vcall(fac, 12, ctypes.c_long, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p))(fac, i, ctypes.byref(ad))
        if hr != 0:
            break
        d = DESC1()
        vcall(ad, 10, ctypes.c_long, ctypes.POINTER(DESC1))(ad, ctypes.byref(d))
        out[f"0x{d.LuidHigh & 0xFFFFFFFF:08X}_0x{d.LuidLow:08X}"] = f"{d.Description} (vendor 0x{d.VendorId:04X})"
        vcall(ad, 2, ctypes.c_ulong)(ad)
        i += 1
    vcall(fac, 2, ctypes.c_ulong)(fac)
    return out


class GpuSampler:
    """nvidia-smi -lms 500 (NVIDIA) plus typeperf GPU Engine utilisation of THIS process's engines on every adapter
    (Intel iGPU included), started after warm-up so the process's engine instances exist."""

    def __init__(self, pids: list[int] | None = None, period_ms: int = 500):
        self.pids = pids or [os.getpid()]
        self.period_ms = period_ms
        self.nv_rows: list[str] = []
        self.tp_lines: list[str] = []
        self.times: dict[int, list[float]] = {}  # id(rows list) -> arrival perf_counter per row
        self._nv = self._tp = None

    def __enter__(self):
        try:
            self._nv = subprocess.Popen(["nvidia-smi", f"--query-gpu={QUERY}", "--format=csv,noheader,nounits",
                                         f"-lms={self.period_ms}"], stdout=subprocess.PIPE, text=True)
            threading.Thread(target=self._rd, args=(self._nv, self.nv_rows), daemon=True).start()
        except Exception:  # noqa: BLE001
            self._nv = None
        try:
            ctrs = [rf"\GPU Engine(pid_{p}_*)\Utilization Percentage" for p in self.pids]
            self._tp = subprocess.Popen(["typeperf", *ctrs, "-si", "1"], stdout=subprocess.PIPE, text=True,
                                        errors="replace")
            threading.Thread(target=self._rd, args=(self._tp, self.tp_lines), daemon=True).start()
            t_end = time.perf_counter() + 4.0  # wait for the CSV header (wildcard resolved) before timing starts
            while time.perf_counter() < t_end and not any(ln.startswith('"(PDH') for ln in self.tp_lines):
                time.sleep(0.05)
        except Exception:  # noqa: BLE001
            self._tp = None
        return self

    def _rd(self, p, rows):
        ts = self.times.setdefault(id(rows), [])
        for ln in p.stdout:
            ts.append(time.perf_counter())
            rows.append(ln.strip())

    def _window(self, rows: list[str], t0: float | None, t1: float | None) -> list[str]:
        """Rows whose arrival falls in [t0 + 0.5, t1 + 0.5] s (a sample arriving at T covers about [T - 1, T])."""
        if t0 is None or t1 is None:
            return list(rows)
        ts = self.times.get(id(rows), [])
        return [r for r, t in zip(rows, ts) if t0 + 0.5 <= t <= t1 + 0.5]

    def __exit__(self, *a):
        for p in (self._nv, self._tp):
            if p:
                p.terminate()
                try:
                    p.wait(timeout=5)
                except Exception:  # noqa: BLE001
                    p.kill()

    def summary(self, adapters: dict | None = None, t0: float | None = None, t1: float | None = None) -> dict:
        """Summary over the whole sampler life, or over the time window [t0, t1] (perf_counter) if given."""
        out: dict = {}
        cols = QUERY.split(",")
        vals: dict[str, list[float]] = {c: [] for c in cols}
        nv_rows = self._window(self.nv_rows, t0, t1)
        for r in nv_rows:
            parts = [x.strip() for x in r.split(",")]
            if len(parts) == len(cols):
                for c, v in zip(cols, parts):
                    try:
                        vals[c].append(float(v))
                    except ValueError:
                        pass
        out["nvidia_smi"] = {c: {"mean": round(sum(v) / len(v), 1), "max": max(v)} for c, v in vals.items() if v}
        out["nvidia_smi"]["samples"] = len(nv_rows)
        # typeperf CSV: header row with instance names, then one row per second (first row may be blank values)
        hdr_rows = [ln for ln in self.tp_lines if ln.startswith('"(PDH')]
        rows = hdr_rows[:1] + [ln for ln in self._window(self.tp_lines, t0, t1)
                               if ln.startswith('"') and not ln.startswith('"(PDH')]
        if len(rows) >= 2:
            hdr = [h.strip('"') for h in rows[0].split('","')]
            agg: dict[str, list[float]] = {}
            for ln in rows[1:]:
                parts = [x.strip('"') for x in ln.split('","')]
                per: dict[str, float] = {}
                for name, v in zip(hdr[1:], parts[1:]):
                    try:
                        fv = float(v)
                    except ValueError:
                        continue
                    try:
                        inst = name.split("GPU Engine(")[1].split(")")[0]
                        luid = inst.split("_luid_")[1].split("_phys_")[0]
                        eng = inst.split("engtype_")[1]
                    except IndexError:
                        continue
                    key = f"{(adapters or {}).get(luid, luid)} | {eng}"
                    per[key] = per.get(key, 0.0) + fv
                for kk, v in per.items():
                    agg.setdefault(kk, []).append(v)
            out["gpu_engine_util_pct"] = {kk: {"mean": round(sum(v) / len(v), 1), "max": round(max(v), 1),
                                               "samples": len(v)} for kk, v in agg.items() if max(v) > 0}
        else:
            out["gpu_engine_util_pct"] = None
            out["gpu_engine_note"] = "no typeperf rows (run shorter than the 1 s sample period, or counter missing)"
        return out


def snapshot() -> dict:
    import platform  # noqa: PLC0415
    s = {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "machine": platform.node(),
         "cpu_count": os.cpu_count(), "python": platform.python_version(), "pyav": av.__version__,
         "libavcodec": ".".join(map(str, av.library_versions["libavcodec"])), "nvidia_smi": nvidia_smi_now()}
    try:
        import psutil  # noqa: PLC0415
        s["process_cpu_affinity"] = psutil.Process().cpu_affinity()
    except Exception:  # noqa: BLE001
        pass
    for mod in ("simplejpeg",):
        try:
            s[mod] = __import__(mod).__version__
        except Exception:  # noqa: BLE001
            pass
    try:
        from nvidia import nvimgcodec as nv  # noqa: PLC0415
        s["nvimgcodec"] = nv.__version__
    except Exception as ex:  # noqa: BLE001
        s["nvimgcodec"] = f"unavailable: {ex!r}"[:200]
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "Get-PnpDevice -Class Display | ForEach-Object { \"$($_.Status)|$($_.Present)|$($_.FriendlyName)\" }"],
                           capture_output=True, text=True, timeout=30)
        s["display_devices"] = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    except Exception:  # noqa: BLE001
        pass
    return s


def write(outdir: Path, name: str, data: dict) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    p = outdir / f"{name}_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json"
    p.write_text(json.dumps(data, indent=1, default=str), encoding="utf-8")
    print("wrote", p, flush=True)
    return p
