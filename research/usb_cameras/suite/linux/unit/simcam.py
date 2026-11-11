"""A simulated camera for unit tests: stands in for ctx.camcmd / ctx.run_child and writes the same files the real
children write (frames.jsonl, meta.jsonl, cycles.jsonl, frames.mjpeg, summary JSON), so the analysis paths of every
test module run end to end without hardware. Needs Pillow (+ numpy for imgmetrics) to make JPEGs.

Behaviour:
- JPEG frames of the requested size whose brightness follows exposure x gain, colour follows WB temperature,
  sharpness follows |focus - 125| (blur), so L-CTRL-EFFECT sees effects;
- metadata blocks on a 300 MHz device clock with a per-URB (4 ms) host grid, so L-TS gets a PTS fit;
- L-MULTI pairs: 'B_over_*' second-camera starts (B1 and the retry) fail with ENOSPC at STREAMON, the alone start
  after A works, 'B_fits_*' works; phase A works.
- L-FMT-NOGRAB: 'formats --hold-signal F' creates F; captures under an 'l_fmt_nograb' folder stamp their frames
  on the real CLOCK_MONOTONIC from the call onwards (the condition streams run "concurrently" with the listings),
  and the PyAV helper does the same there.
"""
from __future__ import annotations

import io
import json
import random
import time
from pathlib import Path
from typing import Any

import sysfs

CTRL = {  # id: (name, type, min, max, step, default)
    0x009A0901: ("Auto Exposure", "menu", 0, 3, 1, 3), 0x009A0902: ("Exposure Time, Absolute", "integer", 3, 2047, 1,
                                                                     250),
    0x009A0903: ("Exposure, Dynamic Framerate", "boolean", 0, 1, 1, 0), 0x00980913: ("Gain", "integer", 0, 255, 1, 0),
    0x0098090C: ("White Balance, Automatic", "boolean", 0, 1, 1, 1),
    0x0098091A: ("White Balance Temperature", "integer", 2000, 6500, 1, 4000),
    0x009A090C: ("Focus, Automatic Continuous", "boolean", 0, 1, 1, 1),
    0x009A090A: ("Focus, Absolute", "integer", 0, 250, 5, 0), 0x00980900: ("Brightness", "integer", 0, 255, 1, 128),
    0x00980901: ("Contrast", "integer", 0, 255, 1, 128), 0x00980902: ("Saturation", "integer", 0, 255, 1, 128),
    0x0098091B: ("Sharpness", "integer", 0, 255, 1, 128), 0x00980918: ("Power Line Frequency", "menu", 0, 2, 1, 2),
    0x0098091C: ("Backlight Compensation", "integer", 0, 1, 1, 0),
    0x009A090D: ("Zoom, Absolute", "integer", 100, 500, 1, 100), 0x009A0908: ("Pan, Absolute", "integer", -36000,
                                                                               36000, 3600, 0),
    0x009A0909: ("Tilt, Absolute", "integer", -36000, 36000, 3600, 0)}


def _arg(argv: list[str], name: str, default=None):
    if name in argv:
        i = argv.index(name)
        return argv[i + 1] if i + 1 < len(argv) else default
    return default


def _sets(text: str | None) -> list[tuple[int, int]]:
    out = []
    for part in (text or "").split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            out.append((int(k, 0), int(v, 0)))
    return out


_JPEG_CACHE: dict[tuple, bytes] = {}


def _jpeg(w: int, h: int, exposure: int, gain: int, wb: int, focus: int, rng: random.Random) -> bytes:
    """Deterministic in its parameters (rng unused), so frames are cached: keeps the 720p captures fast."""
    k = (w, h, exposure, gain, wb, focus)
    if k not in _JPEG_CACHE:
        _JPEG_CACHE[k] = _make_jpeg(w, h, exposure, gain, wb, focus)
    return _JPEG_CACHE[k]


def _make_jpeg(w: int, h: int, exposure: int, gain: int, wb: int, focus: int) -> bytes:
    from PIL import Image, ImageFilter
    sw, sh = max(16, w // 8), max(16, h // 8)
    lum = max(5, min(250, int(exposure * (1 + gain / 64.0) / 4)))
    r = max(0, min(255, int(lum * (0.6 + (wb - 2000) / 6000))))
    b = max(0, min(255, int(lum * (1.4 - (wb - 2000) / 6000))))
    img = Image.new("RGB", (sw, sh), (r, lum, b))
    px = img.load()
    for y in range(0, sh, 2):
        for x in range(0, sw, 2):
            if (x // 2 + y // 2) % 2:
                px[x, y] = (min(255, r + 60), min(255, lum + 60), min(255, b + 60))
    blur = abs(focus - 125) / 25.0
    if blur > 0.2:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    img = img.resize((w, h))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=70)
    return buf.getvalue()


class SimCam:
    def __init__(self, frames_per_capture: int = 12):
        self.state: dict[str, dict[int, int]] = {}
        self.n = frames_per_capture
        self.rng = random.Random(1)
        self.calls: list[list[str]] = []

    def cams(self) -> dict[str, dict[str, Any]]:
        return {c["node"]: c for c in sysfs.discover_cameras()}

    def ctl(self, node: str) -> dict[int, int]:
        return self.state.setdefault(node, {k: v[5] for k, v in CTRL.items()})

    def __call__(self, argv: list[str], timeout_s: float, env=None) -> dict[str, Any]:
        argv = [str(a) for a in argv]
        self.calls.append(argv)
        if any(a.endswith("camworker.py") for a in argv):
            cmd = argv[argv.index(next(a for a in argv if a.endswith("camworker.py"))) + 1]
            j = self.worker(cmd, argv)
        elif any(a.endswith(("pyav_v4l2.py", "opencv_v4l2.py")) for a in argv):
            j = self.helper(argv)
        else:
            return {"argv": argv, "rc": 127, "stdout": "", "stderr": "sim: not available", "elapsed_s": 0.0,
                    "timed_out": False, "killed": False, "spawn_error": None, "json": None}
        rc = j.pop("_rc", 0)
        return {"argv": argv, "rc": rc, "stdout": json.dumps(j), "stderr": "", "elapsed_s": 0.05, "timed_out": False,
                "killed": False, "spawn_error": None, "json": j}

    # ------------------------------------------------------------------ worker
    def worker(self, cmd: str, argv: list[str]) -> dict[str, Any]:
        node = _arg(argv, "--device")
        cams = self.cams()
        if cmd == "enum":
            runs = []
            for r in range(int(_arg(argv, "--repeat", 1))):
                ents = []
                for c in cams.values():
                    bus = f"usb-{c['pci_controller']}-{c['devpath']}"
                    ents.append({"node": c["node"], "driver": "uvcvideo", "bus_info": bus, "is_capture": True})
                    ents.append({"node": c["meta_node"], "driver": "uvcvideo", "bus_info": bus, "is_capture": False,
                                 "is_meta": True})
                runs.append({"run": r, "elapsed_ms": 1.0, "entries": ents})
            return {"cmd": "enum", "runs": runs}
        cam = cams.get(node)
        if cam is None:
            return {"error": {"stage": "open", "errno": 2, "errno_name": "ENOENT"}, "_rc": 3}
        if cmd == "formats":
            fm: dict[str, dict] = {}
            for stream in cam["descriptors"]["streams"]:
                for m in stream["modes"]:
                    fm.setdefault(m["fourcc"], {})[(m["w"], m["h"])] = m.get("fps") or []
            fmts = []
            for fcc, sizes in fm.items():
                fmts.append({"fourcc": fcc, "description": fcc, "compressed": fcc in ("MJPG", "H264"), "sizes": [
                    {"type": "discrete", "w": w, "h": h,
                     "intervals": [{"type": "discrete", "num": 1, "den": f, "fps": f} for f in fps]}
                    for (w, h), fps in sizes.items()]})
            out = {"formats": fmts, "meta_formats": [{"fourcc": "UVCH"}], "elapsed_ms": 2.0, "list_ms": 1.5}
            hold = float(_arg(argv, "--hold-ms", 0) or 0)
            if hold:
                sig = _arg(argv, "--hold-signal")
                t = time.monotonic_ns()
                if sig:
                    Path(sig).write_text(str(t))
                out["hold"] = {"ms": hold, "t_start_ns": t, "t_end_ns": t, "alts_seen": [0], "samples": 1}
            return out
        if cmd in ("info", "desk_probe"):
            return {"querycap": {"driver": "uvcvideo"}, "reqbufs_errno": None, "open_errno": None}
        if cmd == "controls":
            st = self.ctl(node)
            sets = []
            for cid, v in _sets(_arg(argv, "--set")):
                err = None
                if cid == 0x009A0902 and st.get(0x009A0901) != 1:
                    err = "EACCES"
                else:
                    st[cid] = v
                sets.append({"id": cid, "id_hex": f"0x{cid:08x}", "value": v, "errno": err, "readback": st.get(cid),
                             "readback_errno": None})
            out: dict[str, Any] = {"sets": sets}
            if "--no-walk" not in argv:
                ids = {int(x, 0) for x in (_arg(argv, "--ids") or "").split(",") if x}
                walk = []
                for cid, (name, typ, lo, hi, step, d) in CTRL.items():
                    if ids and cid not in ids:
                        continue
                    if cam["pid"] == "4a55" and cid not in (0x009A0901, 0x009A0902, 0x00980900, 0x00980901,
                                                           0x00980902, 0x0098091B, 0x00980913, 0x0098091A,
                                                           0x0098090C, 0x00980918):
                        continue
                    c = {"id": cid, "id_hex": f"0x{cid:08x}", "name": name, "type": typ, "min": lo, "max": hi,
                         "step": step, "default": d, "flags": [], "value": st.get(cid, d), "get_errno": None,
                         "get_ms": 1.0}
                    if typ == "menu":
                        c["menu"] = [{"index": 1, "name": "Manual Mode"}, {"index": 3, "name": "Aperture Priority"}]
                    walk.append(c)
                out["controls"] = walk
                out["walk_ms"] = 5.0
            return out
        if cmd == "capture":
            return self.capture(cam, argv)
        if cmd == "cycle":
            od = Path(_arg(argv, "--out-dir"))
            od.mkdir(parents=True, exist_ok=True)
            n = int(_arg(argv, "--cycles"))
            with (od / "cycles.jsonl").open("w") as f:
                for i in range(n):
                    f.write(json.dumps({"i": i, "ok": True, "frames": int(_arg(argv, "--frames", 30)),
                                        "open_ms": 1.0, "first_frame_ms": 120.0, "close_ms": 2.0,
                                        "granted_alt": 4, "devnum_before": "5", "devnum_after": "5"}) + "\n")
            return {"cmd": "cycle", "rows": n, "n_ok": n}
        return {"error": {"stage": "sim", "message": f"unknown {cmd}"}, "_rc": 2}

    def capture(self, cam: dict[str, Any], argv: list[str]) -> dict[str, Any]:
        od = Path(_arg(argv, "--out-dir"))
        od.mkdir(parents=True, exist_ok=True)
        rd = Path(_arg(argv, "--raw-dir") or od)
        w, h, fps = int(_arg(argv, "--width")), int(_arg(argv, "--height")), float(_arg(argv, "--fps"))
        save = _arg(argv, "--save", "none")
        label = od.parts[-1] if od.parts else ""
        if label in ("B1", "B2_retry_while_A") and "B_over_" in str(od):
            (od / "frames.jsonl").write_text("")
            return {"error": {"stage": "streamon", "errno": 28, "errno_name": "ENOSPC", "message": "sim ENOSPC"},
                    "granted_after_failure": [{"interface": "x", "alt": 0}], "_rc": 4}
        st = self.ctl(cam["node"])
        controls_before = []
        for cid, v in _sets(_arg(argv, "--controls-before")):
            st[cid] = v
            controls_before.append({"id": f"0x{cid:08x}", "value": v, "errno": None, "readback": v,
                                    "readback_errno": None})
        sched = []
        for chunk in (_arg(argv, "--schedule") or "").split(";"):
            if ":" in chunk:
                t, s = chunk.split(":", 1)
                sched.append((float(t), _sets(s)))
        period = 1e9 / fps
        secs = float(_arg(argv, "--seconds") or 0) or int(_arg(argv, "--frames") or self.n) / fps
        n = max(self.n, int(secs * fps)) if sched else self.n
        t0 = 10_000_000_000
        if "l_fmt_nograb" in str(od) and "--seconds" in argv:
            t0, n = time.monotonic_ns(), max(self.n, int(secs * fps))   # a "running" stream on the real clock
        events, step = [], 0
        raw = (rd / "frames.mjpeg").open("wb") if save != "none" else None
        if raw:
            rd.mkdir(parents=True, exist_ok=True)
        off = 0
        meta_on = _arg(argv, "--meta", "off") != "off" and cam.get("meta_node")
        mf = (od / "meta.jsonl").open("w") if meta_on else None
        clock = 300e6
        with (od / "frames.jsonl").open("w") as f:
            for i in range(n):
                t = t0 + int(i * period)
                while sched and (t - t0) / 1e6 >= sched[0][0]:
                    _, s = sched.pop(0)
                    step += 1
                    applied = []
                    for cid, v in s:
                        st[cid] = v
                        applied.append({"id": f"0x{cid:08x}", "value": v, "errno": None, "readback": v,
                                        "readback_errno": None})
                    events.append({"step": step, "sets": applied})
                data = _jpeg(w, h, st[0x009A0902], st[0x00980913], st[0x0098091A],
                             st[0x009A090A], self.rng) if (raw or i == 0) else b""
                soe = t - (t % 4_000_000)  # per-URB host grid
                row = {"seq": i, "v4l2_seq": i, "host_ns": t + 3_000_000, "ts_ns": soe, "ts_type": "MONOTONIC",
                       "ts_src": "SOE", "error": False, "bytes": len(data) or 50000, "soi": True, "eoi": True,
                       "sof0_w": w, "sof0_h": h, "hdr_sha1": "a" * 40, "step": step}
                if raw and data:
                    raw.write(data)
                    row.update(raw_off=off, raw_len=len(data))
                    off += len(data)
                f.write(json.dumps(row) + "\n")
                if mf:
                    pts = int((t - t0 - 5e6) * clock / 1e9) & 0xFFFFFFFF
                    pairs = []
                    for k in range(4):
                        hn = t + k * 4_000_000
                        stc = int((hn - t0) * clock / 1e9 + self.rng.uniform(-3e5, 3e5)) & 0xFFFFFFFF
                        pairs.append([stc, 5, 7, hn])
                    mf.write(json.dumps({"meta_seq": i, "meta_ts_ns": soe, "meta_bytes": 900, "meta_error": False,
                                         "blocks": 40, "uvc_pts": pts, "uvc_scr_stc": pairs[0][0], "uvc_scr_sof": 5,
                                         "uvc_host_sof": 7, "uvc_host_sof_ns": pairs[0][3], "scr_pairs": pairs})
                             + "\n")
        if raw:
            raw.close()
        if mf:
            mf.close()
        alt = {640: 4, 1280: 9}.get(w, 11)
        summ = {"cmd": "capture", "error": None, "controls_before": controls_before,
                "timings": {"open_ms": 1.0, "sfmt_ms": 30.0, "reqbufs_ms": 2.0, "streamon_ms": 50.0,
                            "first_frame_ms": 150.0, "close_ms": 5.0},
                "info": {"format": {"size_ok": True, "fourcc_ok": True}, "meta": {"enabled": bool(meta_on)}},
                "stream": {"fps_host": fps, "counts": {"frames": n, "error_flag": 0, "seq_missing": 0},
                           "granted": {"alts": [{"interface": "x:1.1", "alt": alt}]}, "schedule_events": events}}
        (od / "summary.json").write_text(json.dumps(summ))
        return summ

    # ------------------------------------------------------------------ helpers (pyav / opencv)
    def helper(self, argv: list[str]) -> dict[str, Any]:
        cmd = next(a for a in argv if a in ("version", "capture", "cycle"))
        if cmd == "version":
            return {"av": "19.0.2"}
        od = Path(_arg(argv, "--out-dir"))
        od.mkdir(parents=True, exist_ok=True)
        if cmd == "cycle":
            n = int(_arg(argv, "--cycles"))
            with (od / "cycles.jsonl").open("w") as f:
                for i in range(n):
                    f.write(json.dumps({"i": i, "ok": True, "frames": 10, "first_frame_ms": 300.0}) + "\n")
            return {"rows": n, "n_ok": n}
        w, h = int(_arg(argv, "--width")), int(_arg(argv, "--height"))
        rd = Path(_arg(argv, "--raw-dir") or od)
        rd.mkdir(parents=True, exist_ok=True)
        data = _jpeg(w, h, 250, 0, 4000, 0, self.rng)
        n, t0 = self.n, 0
        if "l_fmt_nograb" in str(od) and _arg(argv, "--seconds"):
            n, t0 = max(self.n, int(float(_arg(argv, "--seconds")) * 30)), time.monotonic_ns()
        with (od / "frames.jsonl").open("w") as f, (rd / "frames.mjpeg").open("wb") as r:
            for i in range(n):
                row = {"seq": i, "host_ns": t0 + i * 33_333_333, "bytes": len(data), "soi": True, "eoi": True,
                       "sof0_w": w, "sof0_h": h, "hdr_sha1": "a" * 40}
                if i < self.n:   # long (L-FMT-NOGRAB) streams keep only the first frames' bytes
                    r.write(data)
                    row.update(raw_off=i * len(data), raw_len=len(data))
                f.write(json.dumps(row) + "\n")
        return {"ok": True, "frames": n, "fps_host": 30.0, "first_frame_ms": 200.0}


def apply(ctx, sim: SimCam) -> None:
    ctx.camcmd = sim
    ctx.run_child = sim

