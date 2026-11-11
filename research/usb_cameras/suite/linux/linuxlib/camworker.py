#!/usr/bin/env python3
"""camworker: the Linux suite's child process for every camera operation (raw V4L2 via ctypes ioctls).

The runner (suite/linux/run_suite.py) never touches a camera itself: it starts this script with a timeout and
kills the whole process group on a hang (common/procutil.py). This script adds its own watchdog thread: when a
stage overruns, it writes what it has (partial JSON / JSONL) and exits 5. A process blocked inside an ioctl in
uninterruptible sleep can only exit once the kernel returns (uvcvideo control timeout ~5 s), which is recorded.

Stdlib only (+ suite/common for JPEG header parsing). Run with the runner's interpreter:

    python3 camworker.py selftest
    python3 camworker.py info      --device /dev/video0 [--meta-node /dev/video1]
    python3 camworker.py enum      --repeat 20
    python3 camworker.py formats   --device /dev/video0 [--meta-node /dev/video1] [--hold-ms 2000 [--hold-signal F]]
    python3 camworker.py controls  --device /dev/video0 [--set id=value,...] [--ids id,...] [--no-menus]
    python3 camworker.py capture   --device /dev/video0 --width 1280 --height 720 --fps 30 (--frames N | --seconds S)
                                   --out-dir D [--raw-dir R] [--save none|all|every:K|first:K] [--meta auto|on|off]
                                   [--meta-node /dev/video1] [--meta-buffersize B] [--controls-before id=v,...]
                                   [--schedule "ms:id=v[,id=v];ms:..."] [--timeout-ms T] [--buffers 4]
    python3 camworker.py cycle     --device /dev/video0 --width W --height H --fps F --cycles K --frames N
                                   --out-dir D [--alt-width W2 --alt-height H2 --alt-fps F2] [--gap-ms G]
    python3 camworker.py desk_probe --device /dev/video0

Output: ONE JSON object on stdout (logs on stderr). Exit codes: 0 ok, 2 usage, 3 device not found,
4 camera failure (details in the JSON), 5 timeout (watchdog). Control ids may be hex (0x009a0902), decimal or a
short name from linuxlib/v4l2.py CID (e.g. exposure_time_absolute).

Rules honoured: no S_FMT/TRY_FMT except in capture/cycle (which the runner only calls after checking nobody else
streams the camera); desk_probe uses REQBUFS only (no PROBE is sent); nothing here writes module parameters,
unbinds, or touches another device.
"""
from __future__ import annotations

import argparse
import errno as _errno
import glob
import hashlib
import json
import os
import select
import sys
import threading
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SUITE_DIR = HERE.parents[1]
for p in (str(SUITE_DIR), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import v4l2  # noqa: E402
from v4l2 import V4L2Error, errno_name, mono_ns  # noqa: E402

try:
    import resource  # POSIX only; the module still imports elsewhere for its unit tests
except ImportError:  # pragma: no cover
    resource = None

try:
    from common import jpegcheck  # stdlib only (parse_sof0 / header_span)
except Exception:  # pragma: no cover
    jpegcheck = None

EXIT_OK, EXIT_USAGE, EXIT_NODEV, EXIT_CAMERA, EXIT_TIMEOUT = 0, 2, 3, 4, 5
_OUT_LOCK = threading.Lock()
_EMITTED = False


def log(msg: str) -> None:
    print(f"[camworker {time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def emit(obj: dict[str, Any], rc: int) -> int:
    """Print the single JSON result (once) and return rc."""
    global _EMITTED
    with _OUT_LOCK:
        if not _EMITTED:
            obj.setdefault("exit_code", rc)
            sys.stdout.write(json.dumps(obj, default=str) + "\n")
            sys.stdout.flush()
            _EMITTED = True
    return rc


def ms_since(t0: int) -> float:
    return round((mono_ns() - t0) / 1e6, 3)


class Watchdog:
    """Stage timer: if the current stage overruns, call on_timeout(stage) (which must write partial results) and
    os._exit(5). ``stage(None)`` disarms."""

    def __init__(self, on_timeout):
        self.on_timeout = on_timeout
        self.name: str | None = None
        self.deadline = 0.0
        self.lock = threading.Lock()
        t = threading.Thread(target=self._run, daemon=True, name="watchdog")
        t.start()

    def stage(self, name: str | None, timeout_s: float = 15.0) -> None:
        with self.lock:
            self.name = name
            self.deadline = time.monotonic() + timeout_s if name else 0.0

    def _run(self) -> None:
        while True:
            time.sleep(0.1)
            with self.lock:
                name, dl = self.name, self.deadline
            if name and dl and time.monotonic() > dl:
                try:
                    self.on_timeout(name)
                finally:
                    sys.stdout.flush()
                    sys.stderr.flush()
                    os._exit(EXIT_TIMEOUT)


def parse_id(s: str) -> int:
    s = s.strip()
    if s in v4l2.CID:
        return v4l2.CID[s]
    return int(s, 0)


def parse_sets(text: str | None) -> list[tuple[int, int]]:
    """'id=v,id=v' -> [(id, v)] (order kept: auto modes must be switched before their slaves)."""
    out = []
    for part in (text or "").replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        k, v = part.split("=", 1)
        out.append((parse_id(k), int(v, 0)))
    return out


def parse_schedule(text: str | None) -> list[tuple[float, list[tuple[int, int]]]]:
    """'1000:id=v,id=v;2500:id=v' -> [(1000.0, [(id, v), ...]), ...] sorted by time (ms after the first frame)."""
    ev = []
    for chunk in (text or "").split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        t, sets = chunk.split(":", 1)
        ev.append((float(t), parse_sets(sets)))
    return sorted(ev, key=lambda e: e[0])


def parse_save(text: str) -> tuple[str, int]:
    if text in ("none", "all"):
        return text, 0
    kind, n = text.split(":", 1)
    if kind not in ("every", "first"):
        raise ValueError(text)
    return kind, int(n)


def frame_quick_check(data: bytes) -> dict[str, Any]:
    n = len(data)
    soi = n >= 2 and data[0] == 0xFF and data[1] == 0xD8
    eoi = n >= 2 and data.rfind(b"\xff\xd9", max(0, n - 64)) >= 0
    out: dict[str, Any] = {"soi": soi, "eoi": eoi, "sof0_w": None, "sof0_h": None, "hdr_sha1": None}
    if soi and jpegcheck is not None:
        try:
            sof = jpegcheck.parse_sof0(data[:65536])
            if sof:
                out["sof0_w"], out["sof0_h"] = sof["w"], sof["h"]
            span = jpegcheck.header_span(data[:65536])
            if span:
                out["hdr_sha1"] = hashlib.sha1(data[span[0]:span[1]]).hexdigest()
        except Exception:
            pass
    return out


# ----------------------------------------------------------------------------------------- sysfs readback
def usb_dir_for_node(node: str) -> Path | None:
    root = os.environ.get("SKELLYCAM_LINUX_ROOT", "")
    base = Path(f"{root}/sys/class/video4linux/{Path(node).name}")
    try:
        p = (base / "device").resolve(strict=True)
    except OSError:
        return None
    for cand in (p, *p.parents):
        if (cand / "idVendor").exists():
            return cand
        if cand == cand.parent:
            break
    return None


def _rd(p: Path) -> str | None:
    try:
        return p.read_text().strip()
    except OSError:
        return None


def usb_state(ud: Path | None) -> dict[str, Any]:
    if ud is None:
        return {}
    return {"usb_name": ud.name, "busnum": _rd(ud / "busnum"), "devnum": _rd(ud / "devnum"),
            "runtime_status": _rd(ud / "power/runtime_status"),
            "connected_duration_ms": _rd(ud / "power/connected_duration")}


def granted_alts(ud: Path | None) -> list[dict[str, Any]]:
    """Current alt setting of every video-streaming interface (world-readable; non-zero while streaming)."""
    if ud is None:
        return []
    out = []
    for itf in sorted(ud.glob(f"{ud.name}:*")):
        if _rd(itf / "bInterfaceClass") == "0e" and _rd(itf / "bInterfaceSubClass") == "02":
            try:
                alt = int(_rd(itf / "bAlternateSetting") or "")
            except ValueError:
                alt = None
            out.append({"interface": itf.name, "alt": alt})
    return out


# ----------------------------------------------------------------------------------------- subcommands
def cmd_selftest(a) -> int:
    st = v4l2.selftest()
    blocks, an = v4l2.parse_uvc_meta(b"")
    return emit({"cmd": "selftest", **st, "meta_parser_ok": blocks == [] and an.get("truncated") == 0},
                EXIT_OK if st["ok"] else EXIT_CAMERA)


def _open(path: str, readonly: bool = False) -> v4l2.Device:
    return v4l2.Device(path, readonly=readonly)


def _err_rc(e: V4L2Error) -> int:
    return EXIT_NODEV if (e.stage == "open" and e.errno in (_errno.ENOENT, _errno.ENODEV, _errno.ENXIO)) \
        else EXIT_CAMERA


def cmd_info(a) -> int:
    res: dict[str, Any] = {"cmd": "info", "device": a.device}
    t0 = mono_ns()
    try:
        with _open(a.device, readonly=True) as d:
            res["querycap"] = d.querycap()
            res["formats"] = d.enum_formats()
        if a.meta_node:
            with _open(a.meta_node, readonly=True) as m:
                res["meta_querycap"] = m.querycap()
                res["meta_formats"] = m.enum_formats(v4l2.BUF_TYPE_META_CAPTURE)
    except V4L2Error as e:
        res["error"] = e.as_dict()
        res["elapsed_ms"] = ms_since(t0)
        return emit(res, _err_rc(e))
    res["elapsed_ms"] = ms_since(t0)
    return emit(res, EXIT_OK)


def cmd_enum(a) -> int:
    root = os.environ.get("SKELLYCAM_LINUX_ROOT", "")
    runs = []
    for r in range(a.repeat):
        t0 = mono_ns()
        nodes = sorted(glob.glob(f"{root}/dev/video*"), key=lambda s: int("".join(ch for ch in s[-4:] if ch.isdigit())
                                                                           or 0))
        entries = []
        for n in nodes:
            e: dict[str, Any] = {"node": n[len(root):]}
            t1 = mono_ns()
            try:
                with _open(n, readonly=True) as d:
                    e.update(d.querycap())
            except V4L2Error as err:
                e["error"] = err.as_dict()
            e["ms"] = ms_since(t1)
            entries.append(e)
        runs.append({"run": r, "elapsed_ms": ms_since(t0), "entries": entries})
        if a.gap_ms:
            time.sleep(a.gap_ms / 1000)
    return emit({"cmd": "enum", "repeat": a.repeat, "runs": runs}, EXIT_OK)


def cmd_formats(a) -> int:
    """ENUM_FMT / FRAMESIZES / FRAMEINTERVALS on a read-only fd: no S_FMT, no REQBUFS, no STREAMON.
    --hold-ms: keep the fd open that long after listing (L-FMT-NOGRAB samples the VS interface alt and tries a
    third-process capture meanwhile); --hold-signal FILE is created when the hold starts. The VS alt is also
    sampled here during the hold (world-readable sysfs)."""
    res: dict[str, Any] = {"cmd": "formats", "device": a.device}
    t0 = mono_ns()
    try:
        with _open(a.device, readonly=True) as d:
            res["querycap"] = d.querycap()
            res["formats"] = d.list_modes()
            res["list_ms"] = ms_since(t0)
            if a.hold_ms and a.hold_ms > 0:
                ud = usb_dir_for_node(a.device)
                h: dict[str, Any] = {"ms": a.hold_ms, "t_start_ns": mono_ns(), "alts_seen": [], "samples": 0}
                res["hold"] = h
                if a.hold_signal:
                    try:
                        Path(a.hold_signal).write_text(str(h["t_start_ns"]))
                    except OSError as e:
                        h["signal_error"] = repr(e)
                end = h["t_start_ns"] + int(a.hold_ms * 1e6)
                seen: set = set()
                while mono_ns() < end:
                    for g in granted_alts(ud):
                        seen.add(g.get("alt"))
                    h["samples"] += 1
                    time.sleep(0.05)
                h["alts_seen"] = sorted(x for x in seen if x is not None)
                h["t_end_ns"] = mono_ns()
        if a.meta_node:
            with _open(a.meta_node, readonly=True) as m:
                res["meta_formats"] = m.enum_formats(v4l2.BUF_TYPE_META_CAPTURE)
    except V4L2Error as e:
        res["error"] = e.as_dict()
        return emit(res, _err_rc(e))
    finally:
        res["elapsed_ms"] = ms_since(t0)
    return emit(res, EXIT_OK)


def _ctrl_readable(c: dict[str, Any]) -> bool:
    return c.get("id") is not None and c["type"] not in ("ctrl_class", "button", "string") \
        and "write_only" not in c["flags"] and "disabled" not in c["flags"]


def cmd_controls(a) -> int:
    res: dict[str, Any] = {"cmd": "controls", "device": a.device, "sets": []}
    # --total-timeout-s: the worker always exits by itself (with the partial JSON) before the runner's outer
    # timeout would kill it without any output; every stage limit is clipped to what is left of it.
    total_dl = (time.monotonic() + a.total_timeout_s) if a.total_timeout_s else None

    def lim(x: float) -> float:
        return max(0.5, min(x, total_dl - time.monotonic())) if total_dl else x

    def on_timeout(stage: str) -> None:
        res["error"] = {"stage": stage, "errno": None, "errno_name": "timeout",
                        "message": f"watchdog: stage {stage} exceeded its limit (op {a.op_timeout_s}s, "
                                   f"walk {a.walk_timeout_s}s, total {a.total_timeout_s}s)"}
        emit(res, EXIT_TIMEOUT)

    wd = Watchdog(on_timeout)
    t0 = mono_ns()
    try:
        wd.stage("open", lim(a.op_timeout_s))
        d = _open(a.device)
    except V4L2Error as e:
        res["error"] = e.as_dict()
        return emit(res, _err_rc(e))
    try:
        want = {parse_id(x) for x in a.ids.split(",")} if a.ids else None
        if not a.no_walk:
            t1 = mono_ns()
            walk_dl = time.monotonic() + a.walk_timeout_s
            walk: list[dict[str, Any]] = []
            res["controls"] = walk          # partial list survives a watchdog exit
            res["walk_partial"] = True

            def progress(n: int) -> None:
                # per-query limit (a Kiyo in its bad state takes ~5 s per GET request), never past the walk limit
                wd.stage(f"query_ext_ctrl #{n}", lim(max(1.0, min(a.op_timeout_s, walk_dl - time.monotonic()))))

            d.query_ext_ctrls(menus=not a.no_menus, out=walk, progress=progress)
            res["walk_partial"] = False
            res["walk_ms"] = ms_since(t1)
            if want is not None:
                walk = [c for c in walk if c.get("id") in want or c.get("id") is None]  # keep walk errors
            res["controls"] = walk
            for c in walk:
                if not _ctrl_readable(c) or a.no_values:
                    continue
                wd.stage(f"get {c['id_hex']}", lim(a.op_timeout_s))
                t2 = mono_ns()
                try:
                    c["value"] = d.get_ctrl(c["id"], int64=c["type"] == "integer64")
                    c["get_errno"] = None
                except V4L2Error as e:
                    c["value"], c["get_errno"] = None, e.errno_name
                c["get_ms"] = ms_since(t2)
        for cid, val in parse_sets(a.set):
            ent: dict[str, Any] = {"id": cid, "id_hex": f"0x{cid:08x}", "short": v4l2.CID_NAME.get(cid),
                                   "value": val}
            res["sets"].append(ent)         # recorded before the call: a hung set still shows up
            wd.stage(f"set 0x{cid:08x}", lim(a.op_timeout_s))
            t3 = mono_ns()
            try:
                d.set_ctrl(cid, val)
                ent["errno"] = None
            except V4L2Error as e:
                ent["errno"] = e.errno_name
            ent["set_ms"] = ms_since(t3)
            wd.stage(f"readback 0x{cid:08x}", lim(a.op_timeout_s))
            try:
                ent["readback"] = d.get_ctrl(cid)
                ent["readback_errno"] = None
            except V4L2Error as e:
                ent["readback"], ent["readback_errno"] = None, e.errno_name
            ent["matches"] = ent.get("readback") == val if ent["errno"] is None else None
            if a.settle_ms:
                time.sleep(a.settle_ms / 1000)
    finally:
        wd.stage(None)
        d.close()
        res["elapsed_ms"] = ms_since(t0)
    errs = [s for s in res["sets"] if s.get("errno")]
    res["n_set_errors"] = len(errs)
    return emit(res, EXIT_OK)


def cmd_desk_probe(a) -> int:
    """open + REQBUFS(1) + REQBUFS(0): tells whether another file handle owns the queue (EBUSY) WITHOUT sending a
    PROBE to the camera (S_FMT/TRY_FMT would)."""
    res: dict[str, Any] = {"cmd": "desk_probe", "device": a.device}
    t0 = mono_ns()
    try:
        d = _open(a.device)
    except V4L2Error as e:
        res["open_errno"] = e.errno_name
        res["error"] = e.as_dict()
        return emit(res, _err_rc(e))
    try:
        res["open_errno"] = None
        rb = v4l2.v4l2_requestbuffers(count=1, type=v4l2.BUF_TYPE_VIDEO_CAPTURE, memory=v4l2.MEMORY_MMAP)
        try:
            v4l2.xioctl(d.fd, v4l2.VIDIOC_REQBUFS, rb, "reqbufs")
            res["reqbufs_errno"] = None
            res["granted"] = rb.count
            v4l2.xioctl(d.fd, v4l2.VIDIOC_REQBUFS, v4l2.v4l2_requestbuffers(
                count=0, type=v4l2.BUF_TYPE_VIDEO_CAPTURE, memory=v4l2.MEMORY_MMAP), "reqbufs0")
        except V4L2Error as e:
            res["reqbufs_errno"] = e.errno_name
    finally:
        d.close()
        res["elapsed_ms"] = ms_since(t0)
    return emit(res, EXIT_OK)


# ----------------------------------------------------------------------------------------- capture
class Capture:
    """One capture session: open -> S_FMT -> S_PARM -> controls -> (meta) -> REQBUFS -> STREAMON -> frames -> close.
    Used by both ``capture`` and ``cycle``. Errors raise V4L2Error with the stage."""

    def __init__(self, a, wd: Watchdog, mode: tuple[str, int, int, float], rows_cb=None, meta: str = "off",
                 save=None, raw_file=None):
        self.a, self.wd, self.mode = a, wd, mode
        self.rows_cb, self.meta_mode, self.save, self.raw_file = rows_cb, meta, save, raw_file
        self.dev: v4l2.Device | None = None
        self.mdev: v4l2.Device | None = None
        self.vq: v4l2.MmapQueue | None = None
        self.mq: v4l2.MmapQueue | None = None
        self.t: dict[str, Any] = {}
        self.info: dict[str, Any] = {}
        self.streaming = False

    def _stage(self, name: str, timeout: float | None = None) -> int:
        self.wd.stage(name, timeout or self.a.op_timeout_s)
        return mono_ns()

    def open_and_configure(self) -> None:
        fcc, w, h, fps = self.mode
        t = self._stage("open")
        self.t_open = t
        self.dev = _open(self.a.device)
        self.t["open_ms"] = ms_since(t)
        t = self._stage("querycap")
        cap = self.dev.querycap()
        self.info["querycap"] = {k: cap[k] for k in ("driver", "card", "bus_info", "device_caps")}
        if not cap["is_capture"]:
            raise V4L2Error("querycap", _errno.ENOTTY, "not a video capture node")
        t = self._stage("s_fmt")
        got = self.dev.s_fmt(fcc, w, h)
        self.t["sfmt_ms"] = ms_since(t)
        self.info["format"] = {"requested": {"fourcc": fcc, "width": w, "height": h}, "returned": got,
                               "fourcc_ok": got["fourcc"] == fcc, "size_ok": (got["width"], got["height"]) == (w, h)}
        if got["fourcc"] != fcc and not getattr(self.a, "allow_substitute", False):
            raise V4L2Error("s_fmt", _errno.EINVAL, f"driver substituted {got['fourcc']} for {fcc}")
        t = self._stage("s_parm")
        try:
            self.info["parm"] = self.dev.s_parm(fps)
        except V4L2Error as e:
            self.info["parm"] = {"error": e.as_dict()}
        self.t["sparm_ms"] = ms_since(t)

    def apply_sets(self, sets: list[tuple[int, int]], label: str) -> list[dict[str, Any]]:
        out = []
        for cid, val in sets:
            ent: dict[str, Any] = {"id": f"0x{cid:08x}", "short": v4l2.CID_NAME.get(cid), "value": val}
            t = self._stage(f"{label} set 0x{cid:08x}")
            try:
                self.dev.set_ctrl(cid, val)
                ent["errno"] = None
            except V4L2Error as e:
                ent["errno"] = e.errno_name
            ent["set_ms"] = ms_since(t)
            self._stage(f"{label} readback 0x{cid:08x}")
            try:
                ent["readback"] = self.dev.get_ctrl(cid)
                ent["readback_errno"] = None
            except V4L2Error as e:
                ent["readback"], ent["readback_errno"] = None, e.errno_name
            out.append(ent)
        return out

    def setup_meta(self) -> None:
        node = getattr(self.a, "meta_node", None)
        if self.meta_mode == "off" or not node:
            self.info["meta"] = {"enabled": False, "reason": "off" if self.meta_mode == "off" else "no meta node"}
            return
        t = self._stage("meta_setup")
        try:
            self.mdev = _open(node)
            fmt = self.mdev.s_meta_fmt(v4l2.META_FMT_UVC, getattr(self.a, "meta_buffersize", None) or None)
            self.mq = v4l2.MmapQueue(self.mdev.fd, v4l2.BUF_TYPE_META_CAPTURE, max(4, self.a.buffers),
                                     "meta_reqbufs")
            self.info["meta"] = {"enabled": True, "node": node, "format": fmt, "buffers": self.mq.granted,
                                 "buffer_length": self.mq.lengths[0] if self.mq.lengths else None,
                                 "setup_ms": ms_since(t)}
        except V4L2Error as e:
            self.info["meta"] = {"enabled": False, "error": e.as_dict()}
            if self.mdev:
                self.mdev.close()
                self.mdev = None
            self.mq = None
            if self.meta_mode == "on":
                raise

    def start(self) -> None:
        t = self._stage("reqbufs")
        self.vq = v4l2.MmapQueue(self.dev.fd, v4l2.BUF_TYPE_VIDEO_CAPTURE, self.a.buffers)
        self.t["reqbufs_ms"] = ms_since(t)
        self.info["buffers"] = {"granted": self.vq.granted, "length": self.vq.lengths[0] if self.vq.lengths else None}
        if self.mq is not None:
            self._stage("meta_streamon")
            try:
                self.mq.streamon("meta_streamon")
            except V4L2Error as e:
                self.info.setdefault("meta", {})["streamon_error"] = e.as_dict()
        t = self._stage("streamon")
        self.t_streamon = mono_ns()
        self.vq.streamon()
        self.streaming = True
        self.t["streamon_ms"] = ms_since(t)

    def close(self) -> dict[str, Any]:
        t = mono_ns()
        self.wd.stage("close", self.a.op_timeout_s)
        errs: dict[str, Any] = {}
        if self.vq is not None:
            errs.update({f"video_{k}": v for k, v in self.vq.close(streamoff=self.streaming).items()})
        if self.mq is not None:
            errs.update({f"meta_{k}": v for k, v in self.mq.close().items()})
        for d in (self.dev, self.mdev):
            if d is not None:
                try:
                    d.close()
                except OSError as e:
                    errs["close"] = errno_name(e.errno)
        self.vq = self.mq = self.dev = self.mdev = None
        self.streaming = False
        self.t["close_ms"] = ms_since(t)
        return errs


def _new_counts() -> dict[str, Any]:
    return {"frames": 0, "error_flag": 0, "bad_markers": 0, "seq_gaps": 0, "seq_missing": 0, "bytes_total": 0,
            "ts_kinds": {}, "hdr_sha1": {}, "sof_sizes": {}, "meta_buffers": 0, "meta_error_flag": 0,
            "meta_empty": 0, "meta_blocks": 0, "meta_seq_gaps": 0, "meta_truncated": 0, "meta_length_ne_std": 0,
            "zero_bytes": 0, "saved": 0}


def stream_frames(cap: Capture, n_frames: int | None, seconds: float | None, timeout_ms: float,
                  first_timeout_ms: float, frames_fh=None, meta_fh=None, schedule=None, raw_file=None,
                  save=("none", 0), counts=None) -> dict[str, Any]:
    """Dequeue frames until n_frames or seconds; returns timing info. Writes JSONL rows if file handles given."""
    c = counts if counts is not None else _new_counts()
    a = cap.a
    poller = select.poll()
    poller.register(cap.dev.fd, select.POLLIN | select.POLLPRI)
    if cap.mq is not None:
        poller.register(cap.mdev.fd, select.POLLIN)
    t_first = None
    t_last = None
    last_seq = None
    last_meta_seq = None
    ts_first_last = [None, None]
    sched = list(schedule or [])
    events: list[dict[str, Any]] = []
    step = 0
    granted = None
    raw_off = raw_file.tell() if raw_file else 0
    cpu0 = resource.getrusage(resource.RUSAGE_SELF) if resource else None
    deadline_ns = None
    wait_since = mono_ns()
    meta_err_polls = 0
    stop_reason = None
    while True:
        now = mono_ns()
        if t_first is not None:
            if n_frames and c["frames"] >= n_frames:
                stop_reason = "frames"
                break
            if deadline_ns and now >= deadline_ns:
                stop_reason = "seconds"
                break
        limit = first_timeout_ms if t_first is None else timeout_ms
        if (now - wait_since) / 1e6 > limit:
            stop_reason = "first_frame_timeout" if t_first is None else "frame_timeout"
            break
        cap.wd.stage("dqbuf", max(limit / 1000 + 5, a.op_timeout_s))
        evs = poller.poll(100)
        for fd, ev in evs:
            if cap.mdev is not None and fd == cap.mdev.fd:
                if ev & select.POLLERR and not ev & select.POLLIN:
                    meta_err_polls += 1
                    if meta_err_polls > 200:
                        poller.unregister(cap.mdev.fd)
                    continue
                while (b := cap.mq.dqbuf()) is not None:
                    used = b.bytesused
                    data = cap.mq.maps[b.index][:used] if used else b""
                    cap.mq.qbuf(b.index)
                    c["meta_buffers"] += 1
                    if not used:
                        c["meta_empty"] += 1
                    if b.flags & v4l2.BUF_FLAG_ERROR:
                        c["meta_error_flag"] += 1
                    if last_meta_seq is not None and b.sequence > last_meta_seq + 1:
                        c["meta_seq_gaps"] += 1
                    last_meta_seq = b.sequence
                    blocks, an = v4l2.parse_uvc_meta(data)
                    c["meta_blocks"] += len(blocks)
                    c["meta_truncated"] += an.get("truncated", 0)
                    c["meta_length_ne_std"] += an.get("length_ne_std", 0)
                    if meta_fh is not None:
                        row: dict[str, Any] = {"meta_seq": b.sequence, "meta_ts_ns": b.timestamp.tv_sec * 10**9
                                               + b.timestamp.tv_usec * 1000, "meta_bytes": used,
                                               "meta_error": bool(b.flags & v4l2.BUF_FLAG_ERROR),
                                               "blocks": len(blocks), "dq_host_ns": mono_ns()}
                        if blocks:
                            f0, fl = blocks[0], blocks[-1]
                            row.update({"uvc_pts": next((x["pts"] for x in blocks if x["pts"] is not None), None),
                                        "uvc_scr_stc": f0["stc"], "uvc_scr_sof": f0["dev_sof"],
                                        "uvc_host_sof": f0["host_sof"], "uvc_host_sof_ns": f0["ns"],
                                        "uvc_eof_pts": fl["pts"], "uvc_eof_scr_stc": fl["stc"],
                                        "uvc_eof_scr_sof": fl["dev_sof"], "uvc_eof_host_sof": fl["host_sof"],
                                        "uvc_eof_host_sof_ns": fl["ns"],
                                        "scr_pairs": [[x["stc"], x["dev_sof"], x["host_sof"], x["ns"]]
                                                      for x in blocks if x["stc"] is not None][:64],
                                        "eof_bit": any(x["flags"] & v4l2.UVC_STREAM_EOF for x in blocks),
                                        "err_bit": any(x["flags"] & v4l2.UVC_STREAM_ERR for x in blocks)})
                        meta_fh.write(json.dumps(row, separators=(",", ":")) + "\n")
                continue
            while (b := cap.vq.dqbuf()) is not None:
                host = mono_ns()
                used = b.bytesused
                data = cap.vq.maps[b.index][:used]
                cap.vq.qbuf(b.index)
                wait_since = host
                if t_first is None:
                    t_first = host
                    if seconds:
                        deadline_ns = host + int(seconds * 1e9)
                    cap.t["first_frame_ms"] = round((host - cap.t_streamon) / 1e6, 3)   # after STREAMON (= W)
                    if getattr(cap, "t_open", None):
                        cap.t["open_to_first_frame_ms"] = round((host - cap.t_open) / 1e6, 3)
                    cap.wd.stage("granted_alt", a.op_timeout_s)
                    granted = {"alts": granted_alts(usb_dir_for_node(a.device)),
                               "read_at_ms_after_first_frame": 0.0}
                t_last = host
                fl = v4l2.decode_buf_flags(b.flags)
                k = f"{fl['ts_type']}/{fl['ts_src']}"
                c["ts_kinds"][k] = c["ts_kinds"].get(k, 0) + 1
                qc = frame_quick_check(data)
                if fl["error"]:
                    c["error_flag"] += 1
                if used == 0:
                    c["zero_bytes"] += 1
                if not (qc["soi"] and qc["eoi"]):
                    c["bad_markers"] += 1
                if qc["hdr_sha1"]:
                    c["hdr_sha1"][qc["hdr_sha1"]] = c["hdr_sha1"].get(qc["hdr_sha1"], 0) + 1
                sz = f"{qc['sof0_w']}x{qc['sof0_h']}"
                c["sof_sizes"][sz] = c["sof_sizes"].get(sz, 0) + 1
                if last_seq is not None and b.sequence > last_seq + 1:
                    c["seq_gaps"] += 1
                    c["seq_missing"] += b.sequence - last_seq - 1
                last_seq = b.sequence
                ts_ns = b.timestamp.tv_sec * 10**9 + b.timestamp.tv_usec * 1000
                if ts_first_last[0] is None:
                    ts_first_last[0] = ts_ns
                ts_first_last[1] = ts_ns
                c["bytes_total"] += used
                saved = None
                kind, kk = save
                if raw_file is not None and (kind == "all" or (kind == "every" and kk and c["frames"] % kk == 0)
                                             or (kind == "first" and c["frames"] < kk)):
                    raw_file.write(data)
                    saved = (raw_off, used)
                    raw_off += used
                    c["saved"] += 1
                if frames_fh is not None:
                    row = {"seq": c["frames"], "v4l2_seq": b.sequence, "host_ns": host, "ts_ns": ts_ns,
                           "ts_type": fl["ts_type"], "ts_src": fl["ts_src"], "flags": b.flags,
                           "error": fl["error"], "bytes": used, "soi": qc["soi"], "eoi": qc["eoi"],
                           "sof0_w": qc["sof0_w"], "sof0_h": qc["sof0_h"], "hdr_sha1": qc["hdr_sha1"],
                           "step": step}
                    if saved:
                        row["raw_off"], row["raw_len"] = saved
                    frames_fh.write(json.dumps(row, separators=(",", ":")) + "\n")
                c["frames"] += 1
                # control schedule (ms after the first frame), applied on the streaming fd
                while sched and (host - t_first) / 1e6 >= sched[0][0]:
                    t_ms, sets = sched.pop(0)
                    step += 1
                    applied = cap.apply_sets(sets, f"schedule{step}")
                    events.append({"step": step, "t_ms": t_ms, "applied_at_ms": round((mono_ns() - t_first) / 1e6, 3),
                                   "frame_seq": c["frames"], "sets": applied})
                if n_frames and c["frames"] >= n_frames:
                    break
    cpu1 = resource.getrusage(resource.RUSAGE_SELF) if resource else None
    out = {"stop_reason": stop_reason, "granted": granted, "schedule_events": events}
    if t_first is not None and t_last is not None and c["frames"] > 1 and t_last > t_first:
        out["fps_host"] = round((c["frames"] - 1) / ((t_last - t_first) / 1e9), 3)
        out["stream_seconds"] = round((t_last - t_first) / 1e9, 3)
    if ts_first_last[0] is not None and ts_first_last[1] != ts_first_last[0] and c["frames"] > 1:
        out["fps_buffer_ts"] = round((c["frames"] - 1) / ((ts_first_last[1] - ts_first_last[0]) / 1e9), 3)
    out["cpu_s"] = round((cpu1.ru_utime - cpu0.ru_utime) + (cpu1.ru_stime - cpu0.ru_stime), 4) if cpu0 else None
    if out.get("stream_seconds") and out["cpu_s"] is not None:
        out["cpu_pct_one_core"] = round(100 * out["cpu_s"] / out["stream_seconds"], 2)
    out["counts"] = c
    return out


def _mode_from(a, alt: bool = False) -> tuple[str, int, int, float]:
    if alt:
        return (a.fourcc, a.alt_width, a.alt_height, a.alt_fps or a.fps)
    return (a.fourcc, a.width, a.height, a.fps)


def mode_text(m: tuple[str, int, int, float]) -> str:
    return f"{m[0]} {m[1]}x{m[2]}@{m[3]:g}"


def cmd_capture(a) -> int:
    out_dir = Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = Path(a.raw_dir) if a.raw_dir else out_dir
    save = parse_save(a.save)
    summary: dict[str, Any] = {"cmd": "capture", "device": a.device, "meta_node": a.meta_node,
                               "mode": mode_text(_mode_from(a)), "argv": sys.argv, "error": None,
                               "utc_started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    ud = usb_dir_for_node(a.device)
    summary["usb_before"] = usb_state(ud)
    frames_fh = (out_dir / "frames.jsonl").open("w", buffering=1)
    meta_fh = (out_dir / "meta.jsonl").open("w", buffering=1) if a.meta != "off" and a.meta_node else None
    raw_file = None
    if save[0] != "none":
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_file = (raw_dir / "frames.mjpeg").open("wb")
        summary["raw_file"] = str(raw_dir / "frames.mjpeg")
    cap: Capture | None = None

    def finish(rc: int) -> int:
        for fh in (frames_fh, meta_fh, raw_file):
            try:
                if fh:
                    fh.flush()
                    fh.close()
            except Exception:
                pass
        summary["usb_after"] = usb_state(ud)
        summary["timings"] = cap.t if cap else {}
        summary["info"] = cap.info if cap else {}
        summary["utc_finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        summary["exit_code"] = rc
        try:
            (out_dir / "summary.json").write_text(json.dumps(summary, default=str, indent=1))
        except OSError:
            pass
        return emit(summary, rc)

    def on_timeout(stage: str) -> None:
        summary["error"] = {"stage": stage, "errno": None, "errno_name": "timeout",
                            "message": f"watchdog: stage {stage} overran"}
        summary["timed_out"] = True
        finish(EXIT_TIMEOUT)

    wd = Watchdog(on_timeout)
    cap = Capture(a, wd, _mode_from(a), meta=a.meta)
    rc = EXIT_OK
    try:
        cap.open_and_configure()
        if a.controls_before:
            summary["controls_before"] = cap.apply_sets(parse_sets(a.controls_before), "before")
        cap.setup_meta()
        cap.start()
        res = stream_frames(cap, a.frames, a.seconds, a.timeout_ms, max(a.timeout_ms, a.first_frame_timeout_ms),
                            frames_fh, meta_fh, parse_schedule(a.schedule), raw_file, save)
        summary["stream"] = res
        if res["counts"]["frames"] == 0:
            summary["error"] = {"stage": "first_frame", "errno": None, "errno_name": None,
                                "message": f"no frame within {max(a.timeout_ms, a.first_frame_timeout_ms)} ms"}
            rc = EXIT_CAMERA
    except V4L2Error as e:
        summary["error"] = e.as_dict()
        if e.stage == "streamon":
            summary["granted_after_failure"] = granted_alts(ud)
        rc = _err_rc(e)
    except Exception as e:  # never crash without a JSON
        summary["error"] = {"stage": "internal", "errno": None, "errno_name": None,
                            "message": f"{type(e).__name__}: {e}"}
        rc = EXIT_CAMERA
    finally:
        try:
            summary["close_errors"] = cap.close()
        except Exception as e:
            summary["close_errors"] = {"exception": repr(e)}
        wd.stage(None)
    return finish(rc)


def cmd_cycle(a) -> int:
    out_dir = Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fh = (out_dir / "cycles.jsonl").open("w", buffering=1)
    ud = usb_dir_for_node(a.device)
    res: dict[str, Any] = {"cmd": "cycle", "device": a.device, "argv": sys.argv, "cycles_requested": a.cycles,
                           "usb_before": usb_state(ud), "rows": 0}
    cur: dict[str, Any] = {}

    def on_timeout(stage: str) -> None:
        row = dict(cur)
        row.update(ok=False, stage_failed="timeout", hung_stage=stage, timed_out=True, unreleasable=True,
                   errno=None, errno_name="timeout")
        try:
            fh.write(json.dumps(row) + "\n")
            fh.flush()
        except Exception:
            pass
        res["unreleasable"] = {"cycle": cur.get("i"), "stage": stage}
        res["usb_after"] = usb_state(ud)
        emit(res, EXIT_TIMEOUT)

    wd = Watchdog(on_timeout)
    alt = bool(a.alt_width and a.alt_height)
    n_ok = 0
    for i in range(a.cycles):
        mode = _mode_from(a, alt=alt and i % 2 == 1)
        st = usb_state(ud)
        cur.clear()
        cur.update({"i": i, "mode": mode_text(mode), "ok": False, "stage_failed": None, "errno": None,
                    "errno_name": None, "devnum_before": st.get("devnum")})
        cap = Capture(a, wd, mode)
        t_cycle = mono_ns()
        try:
            cap.open_and_configure()
            cur["size_ok"] = cap.info["format"]["size_ok"]
            cap.start()
            r = stream_frames(cap, a.frames, None, a.timeout_ms, max(a.timeout_ms, a.first_frame_timeout_ms))
            cnt = r["counts"]
            cur["frames"] = cnt["frames"]
            cur["error_flags"] = cnt["error_flag"]
            cur["bad_markers"] = cnt["bad_markers"]
            cur["granted_alt"] = ((r.get("granted") or {}).get("alts") or [{}])[0].get("alt")
            cur["fps_host"] = r.get("fps_host")
            if cnt["frames"] == 0:
                cur["stage_failed"] = "first_frame"
                cur["timed_out_waiting"] = True
            elif a.frames and cnt["frames"] < a.frames:
                cur["stage_failed"] = "frames"
            else:
                cur["ok"] = True
        except V4L2Error as e:
            cur["stage_failed"], cur["errno"], cur["errno_name"] = e.stage, e.errno, e.errno_name
            cur["message"] = str(e)
        except Exception as e:
            cur["stage_failed"], cur["message"] = "internal", f"{type(e).__name__}: {e}"
        finally:
            ce = cap.close()
            if ce:
                cur["close_errors"] = ce
            wd.stage(None)
        cur.update({k: v for k, v in cap.t.items()})
        cur["cycle_ms"] = ms_since(t_cycle)
        cur["devnum_after"] = usb_state(ud).get("devnum")
        n_ok += bool(cur["ok"])
        fh.write(json.dumps(cur, default=str) + "\n")
        fh.flush()
        res["rows"] += 1
        if a.gap_ms:
            time.sleep(a.gap_ms / 1000)
    fh.close()
    res["n_ok"] = n_ok
    res["usb_after"] = usb_state(ud)
    return emit(res, EXIT_OK)


# ----------------------------------------------------------------------------------------- CLI
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="camworker", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def dev(p, meta=False):
        p.add_argument("--device", required=True)
        if meta:
            p.add_argument("--meta-node", default=None)
        p.add_argument("--op-timeout-s", type=float, default=15.0, help="watchdog limit per ioctl stage")

    sub.add_parser("selftest")
    p = sub.add_parser("info")
    dev(p, meta=True)
    p = sub.add_parser("enum")
    p.add_argument("--repeat", type=int, default=1)
    p.add_argument("--gap-ms", type=float, default=0)
    p = sub.add_parser("formats")
    dev(p, meta=True)
    p.add_argument("--hold-ms", type=float, default=0.0, help="keep the fd open this long after listing")
    p.add_argument("--hold-signal", default=None, help="file created when the hold starts")
    p = sub.add_parser("controls")
    dev(p)
    p.add_argument("--set", default=None)
    p.add_argument("--ids", default=None)
    p.add_argument("--no-menus", action="store_true")
    p.add_argument("--no-values", action="store_true")
    p.add_argument("--no-walk", action="store_true", help="only apply --set (with readback)")
    p.add_argument("--read-only", action="store_true", help="(default when --set is absent)")
    p.add_argument("--settle-ms", type=float, default=0)
    p.add_argument("--walk-timeout-s", type=float, default=120.0)
    p.add_argument("--total-timeout-s", type=float, default=None,
                   help="overall limit: the worker exits 5 with the partial JSON before this (set it below the "
                        "runner's child timeout)")
    p = sub.add_parser("desk_probe")
    dev(p)
    for name in ("capture", "cycle"):
        p = sub.add_parser(name)
        dev(p, meta=True)
        p.add_argument("--fourcc", default="MJPG")
        p.add_argument("--width", type=int, required=True)
        p.add_argument("--height", type=int, required=True)
        p.add_argument("--fps", type=float, required=True)
        p.add_argument("--frames", type=int, default=None)
        p.add_argument("--timeout-ms", type=float, default=2000)
        p.add_argument("--first-frame-timeout-ms", type=float, default=4000)
        p.add_argument("--buffers", type=int, default=4)
        p.add_argument("--out-dir", required=True)
        p.add_argument("--allow-substitute", action="store_true")
        if name == "capture":
            p.add_argument("--seconds", type=float, default=None)
            p.add_argument("--raw-dir", default=None)
            p.add_argument("--save", default="none")
            p.add_argument("--meta", choices=("auto", "on", "off"), default="off")
            p.add_argument("--meta-buffersize", type=int, default=None)
            p.add_argument("--controls-before", default=None)
            p.add_argument("--schedule", default=None)
        else:
            p.add_argument("--cycles", type=int, required=True)
            p.add_argument("--alt-width", type=int, default=None)
            p.add_argument("--alt-height", type=int, default=None)
            p.add_argument("--alt-fps", type=float, default=None)
            p.add_argument("--gap-ms", type=float, default=0)
            p.set_defaults(meta="off", frames_default=30)
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return EXIT_USAGE if e.code else EXIT_OK
    if a.cmd == "cycle" and not a.frames:
        a.frames = 30
    if a.cmd == "capture" and not a.frames and not a.seconds:
        a.seconds = 3.0
    if a.cmd != "selftest":
        try:
            v4l2.require_linux64()
        except RuntimeError as e:
            return emit({"cmd": a.cmd, "error": {"stage": "platform", "message": str(e)}}, EXIT_USAGE)
        if hasattr(a, "device") and not os.path.exists(os.environ.get("SKELLYCAM_LINUX_ROOT", "") + a.device) \
                and os.environ.get("SKELLYCAM_LINUX_ROOT") is None:
            return emit({"cmd": a.cmd, "device": a.device,
                         "error": {"stage": "open", "errno": _errno.ENOENT, "errno_name": "ENOENT",
                                   "message": "device node does not exist"}}, EXIT_NODEV)
    fn = {"selftest": cmd_selftest, "info": cmd_info, "enum": cmd_enum, "formats": cmd_formats,
          "controls": cmd_controls, "capture": cmd_capture, "cycle": cmd_cycle, "desk_probe": cmd_desk_probe}[a.cmd]
    try:
        return fn(a)
    except V4L2Error as e:
        return emit({"cmd": a.cmd, "error": e.as_dict()}, _err_rc(e))
    except Exception as e:  # last resort: a JSON, never a bare traceback
        import traceback
        return emit({"cmd": a.cmd, "error": {"stage": "internal", "message": f"{type(e).__name__}: {e}",
                                             "traceback": traceback.format_exc()[-2000:]}}, EXIT_CAMERA)


if __name__ == "__main__":
    sys.exit(main())
