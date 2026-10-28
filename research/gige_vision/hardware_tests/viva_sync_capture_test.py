#!/usr/bin/env python3
"""
viva_sync_capture_test.py - multi-camera PTP + frame timestamp alignment test through GenICam features.

NEEDS viva-genicam (MIT, pure Rust GigE Vision stack with Python wheels for Windows x64, macOS arm64,
Linux x86_64):  pip install viva-genicam   (tested with 0.10.0). Keep gev_common.py next to this file.

Steps:
  1. open all cameras found (or --ip ...) with viva-genicam (takes control of each camera)
  2. report vendor/model/serial/firmware, bootstrap GigE Vision version (GEV 3.x flagged),
     DeviceTLVersionMajor/Minor, GevStreamingMode (GVSP / GVRSP) if present, pixel format, packet size,
     timestamp tick frequency
  3. PTP via whichever GenICam feature set the camera has:
       enable: PtpEnable (SFNC) | GevIEEE1588 (deprecated name) | PtpMode=Auto (Allied Vision)
       latch:  PtpDataSetLatch | GevIEEE1588DataSetLatch (if present; status/offset are latched values)
       status: PtpStatus | GevIEEE1588StatusLatched | GevIEEE1588Status  (enum read BY NAME)
       offset: PtpOffsetFromMaster | GevIEEE1588OffsetFromMaster
     waits for one Master + Slaves (or all Slave with --external-master) and max |offset| below
     --max-ptp-offset-ns for --stable-s seconds. PTP is enabled BEFORE any stream is opened (some cameras
     change tick frequency when PTP starts, and stacks cache it at stream creation).
  4a. --mode freerun (default): TriggerMode=Off, AcquisitionFrameRate=--fps; streams for --duration;
     pairs frames across cameras by DEVICE timestamp and reports the inter-camera timestamp spread
     (median/p95/max), per-camera phase offset and frame-clock drift, and dropped frames (block-id gaps +
     incomplete frames). Free-running cameras have arbitrary phase unless a vendor sync mode (Basler
     Synchronous Free Run, LUCID PTPSync, ...) aligns them, so the spread is only judged with --expect-aligned.
  4b. --mode scheduled-action: TriggerSelector=FrameStart, TriggerMode=On, TriggerSource=Action1
     (fallback Action0), ActionSelector/ActionDeviceKey/ActionGroupKey/ActionGroupMask; latches camera 0's
     clock, then sends scheduled ACTION_CMDs for T0 + k * (1/--fps) via viva-genicam send_action (fallback:
     the stdlib sender in gev_common) and reports, per triggered frame, the exposure-start (frame timestamp)
     spread across cameras and each camera's lag behind the scheduled time.
  5. writes frames.csv (one row per frame: device timestamp ticks/ns, block id, host receive time kept in
     separate columns) and summary.json into --out; restores every feature it changed (PTP stays enabled
     unless --restore-ptp).

Examples:
  python viva_sync_capture_test.py                                   # free-run, all cameras, 30 fps, 10 s
  python viva_sync_capture_test.py --mode scheduled-action --fps 30 --triggers 300
  python viva_sync_capture_test.py --ip 169.254.1.10 --ip 169.254.1.11 --pixel-format BayerRG8 --duration 30
  python viva_sync_capture_test.py --fake-cameras 1                  # dry run with viva's emulator

Exit code: 0 = no FAIL, 1 = a check failed, 2 = viva-genicam missing / no camera / bad arguments.

DRAFT: verified only against software-emulated cameras (viva-genicam FakeGigeCamera, which has no PTP and
no Action trigger source). See README.md.
"""
from __future__ import annotations

import argparse
import bisect
import contextlib
import csv
import os
import queue
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

try:
    from . import gev_common as gev  # imported as part of a package (e.g. hardware_tests.<script>)
except ImportError:  # run directly: python viva_sync_capture_test.py
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import gev_common as gev  # type: ignore[no-redef]

INSTALL_HINT = ("This test needs viva-genicam:  pip install viva-genicam\n"
                "(wheels: Windows x64, macOS arm64, Linux x86_64; Python >= 3.9; https://github.com/VitalyVorobyev/viva-genicam)")

PTP_ENABLE = ["PtpEnable", "GevIEEE1588", "PtpMode"]
PTP_LATCH = ["PtpDataSetLatch", "GevIEEE1588DataSetLatch"]
PTP_STATUS = ["PtpStatus", "GevIEEE1588StatusLatched", "GevIEEE1588Status"]
PTP_OFFSET = ["PtpOffsetFromMaster", "GevIEEE1588OffsetFromMaster", "GevIEEE1588OffsetFromMasterLatched"]
PTP_SERVO = ["PtpServoStatus", "BslPtpServoStatus"]
TS_LATCH = ["TimestampLatch", "GevTimestampControlLatch", "PtpDataSetLatch"]
TS_VALUE = ["TimestampLatchValue", "GevTimestampValue", "PtpDataSetLatchValue"]
FRAME_RATE = ["AcquisitionFrameRate", "AcquisitionFrameRateAbs"]
CSV_COLUMNS = ["mode", "camera_index", "camera_ip", "camera_serial", "block_id", "frame_status", "missing_packets",
               "device_timestamp_ticks", "tick_hz", "device_timestamp_ns", "host_receive_unix_ns",
               "host_receive_perf_ns", "width", "height", "pixel_format", "group_index", "trigger_index",
               "scheduled_time_ticks"]


def import_viva() -> Any:
    try:
        import viva_genicam as vg  # noqa: PLC0415
    except ImportError:
        print(INSTALL_HINT)
        sys.exit(2)
    return vg


@dataclass
class FrameRec:
    cam: int
    block_id: int
    ts_ticks: Optional[int]
    status: str
    missing: Optional[int]
    host_unix_ns: int
    host_perf_ns: int
    width: int
    height: int
    pixel_format: str
    ts_ns: Optional[int] = None
    group: Optional[int] = None
    trigger: Optional[int] = None


@dataclass
class VCam:
    idx: int
    ip: str
    cam: Any
    model: str = ""
    serial: str = ""
    tick_hz: int = 0
    nodes: set[str] = field(default_factory=set)
    changed: list[tuple[str, Optional[str]]] = field(default_factory=list)
    frames: list[FrameRec] = field(default_factory=list)
    stream: Any = None
    stream_stats: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    @property
    def label(self) -> str:
        return f"cam{self.idx} {self.ip} {self.model}".strip()

    def has(self, name: str) -> bool:
        return name in self.nodes

    def first(self, names: list[str]) -> Optional[str]:
        return next((n for n in names if n in self.nodes), None)

    def kind(self, name: str) -> str:
        try:
            info = self.cam.node_info(name)
            return str(getattr(info, "kind", "") or "") if info is not None else ""
        except Exception:  # noqa: BLE001 - viva raises its own GenicamError family
            return ""

    def get(self, name: str) -> Optional[str]:
        if name not in self.nodes:
            return None
        try:
            return str(self.cam.get(name))
        except Exception:  # noqa: BLE001
            return None

    def set(self, name: str, value: str, remember: bool = True) -> None:
        """Set by node kind; remembers the old value so restore() can undo it."""
        if remember and name not in [n for n, _ in self.changed]:
            self.changed.append((name, self.get(name)))
        kind = self.kind(name).lower()
        if "bool" in kind:
            self.cam.set_bool(name, value.strip().lower() in ("1", "true", "on", "yes"))
        elif "int" in kind:
            self.cam.set_integer(name, int(value, 0))
        elif "float" in kind:
            self.cam.set_float(name, float(value))
        elif "enum" in kind:
            self.cam.set_enum(name, value)
        else:
            self.cam.set(name, value)

    def execute(self, name: str) -> None:
        self.cam.execute(name)

    def read_reg(self, addr: int) -> Optional[int]:
        try:
            return int.from_bytes(self.cam.read_register(addr, 4), "big")
        except Exception:  # noqa: BLE001
            return None

    def restore(self) -> list[str]:
        problems = []
        reclaimed = False
        for name, old in reversed(self.changed):
            if old is None:
                continue
            try:
                self.set(name, old, remember=False)
            except Exception as e:  # noqa: BLE001
                if not reclaimed and "control" in str(e).lower():
                    reclaimed = True  # the camera dropped us (heartbeat timeout): take control back once and retry
                    try:
                        self.cam.reclaim_control()
                        self.set(name, old, remember=False)
                        continue
                    except Exception as e2:  # noqa: BLE001
                        e = e2
                problems.append(f"{name}={old}: {e}")
        self.changed.clear()
        return problems

    def latch_ticks(self) -> tuple[int, int, int]:
        """(host_perf_ns_before, host_perf_ns_after, device_ticks) via GenICam latch or bootstrap registers."""
        cmd, val = self.first(TS_LATCH), self.first(TS_VALUE)
        if cmd and val:
            t0 = time.perf_counter_ns()
            self.execute(cmd)
            t1 = time.perf_counter_ns()
            return t0, t1, int(self.cam.get_integer(val))
        t0 = time.perf_counter_ns()
        self.cam.write_register(gev.REG_TIMESTAMP_CONTROL, gev.TIMESTAMP_CONTROL_LATCH.to_bytes(4, "big"))
        t1 = time.perf_counter_ns()
        hi = self.read_reg(gev.REG_TIMESTAMP_VALUE_HIGH)
        lo = self.read_reg(gev.REG_TIMESTAMP_VALUE_LOW)
        if hi is None or lo is None:
            raise RuntimeError("no timestamp latch feature and bootstrap latch registers unreadable")
        return t0, t1, (hi << 32) | lo


# ============================================================================================ setup
def open_cameras(vg: Any, args: argparse.Namespace, rep: gev.Reporter, fakes: list[Any]) -> list[VCam]:
    if args.fake_cameras:
        from viva_genicam.testing import FakeGigeCamera  # noqa: PLC0415
        infos = []
        for i in range(args.fake_cameras):
            f = FakeGigeCamera(width=640, height=480, fps=max(1, int(args.fps)), bind_ip=f"127.0.0.{i + 1}",
                               pixel_format=args.pixel_format or "BayerRG8")
            f.start()
            fakes.append(f)
            infos.append(f.device_info())
    else:
        infos = vg.discover(timeout_ms=int(args.discovery_timeout * 1000), iface=args.iface or None,
                            all=args.include_loopback or any(i.startswith("127.") for i in args.ip))
        if args.ip:
            by_ip = {d.ip: d for d in infos}
            missing = [ip for ip in args.ip if ip not in by_ip]
            for ip in missing:
                rep.add("discovery", gev.FAIL, "not found by viva-genicam discovery", ip)
            infos = [by_ip[ip] for ip in args.ip if ip in by_ip]
    cams: list[VCam] = []
    for info in infos:
        try:
            cam = vg.connect_gige(info, iface=args.iface or None)
        except Exception as e:  # noqa: BLE001
            rep.add("connect", gev.FAIL, f"{type(e).__name__}: {e} (another application holding control?)", info.ip)
            continue
        vc = VCam(idx=len(cams), ip=info.ip, cam=cam, model=info.model or "")
        try:
            vc.nodes = set(cam.nodes())
        except Exception:  # noqa: BLE001
            vc.nodes = set()
        cams.append(vc)
    return cams


def describe_camera(c: VCam, args: argparse.Namespace, rep: gev.Reporter) -> dict[str, Any]:
    d: dict[str, Any] = {"ip": c.ip}
    for f in ("DeviceVendorName", "DeviceModelName", "DeviceSerialNumber", "DeviceFirmwareVersion", "DeviceVersion",
              "DeviceTLType", "DeviceTLVersionMajor", "DeviceTLVersionMinor", "GevVersionMajor", "GevVersionMinor",
              "GevStreamingMode", "DeviceStreamProtocol", "PixelFormat", "Width", "Height", "GevSCPSPacketSize",
              "GevTimestampTickFrequency", "ExposureTime", "ExposureTimeAbs"):
        v = c.get(f)
        if v is not None:
            d[f] = v
    c.serial = d.get("DeviceSerialNumber", "")
    c.model = d.get("DeviceModelName", c.model)
    ver = c.read_reg(gev.REG_VERSION)
    if ver is not None:
        d["bootstrap_gev_version"] = f"{ver >> 16}.{ver & 0xFFFF}"
    cap = c.read_reg(gev.REG_GVCP_CAPABILITY)
    d["capability"] = gev.bits_set(cap, gev.CAPABILITY_BITS) if cap is not None else None
    for name in ("GevStreamingMode", "DeviceStreamProtocol"):
        if c.has(name):
            try:
                d[f"{name}_entries"] = list(c.cam.enum_entries(name))
            except Exception:  # noqa: BLE001
                pass
    gev3 = (ver is not None and ver >> 16 >= 3) or d.get("DeviceTLVersionMajor") == "3"
    rep.add("camera", gev.INFO, f"{d.get('DeviceVendorName', '')} {d.get('DeviceModelName', '')} serial "
            f"{d.get('DeviceSerialNumber', '?')} fw {d.get('DeviceFirmwareVersion', '?')}; GEV "
            f"{d.get('bootstrap_gev_version', '?')} (DeviceTLVersion {d.get('DeviceTLVersionMajor', '?')}."
            f"{d.get('DeviceTLVersionMinor', '?')}){' = GigE Vision 3' if gev3 else ''}; "
            f"{d.get('PixelFormat', '?')} {d.get('Width', '?')}x{d.get('Height', '?')}, packet size "
            f"{d.get('GevSCPSPacketSize', '?')}", c.label)
    mode = d.get("GevStreamingMode") or d.get("DeviceStreamProtocol")
    if mode is not None:
        if "RSP" in mode.upper() or "RDMA" in mode.upper():
            if args.force_gvsp:
                try:
                    c.set("GevStreamingMode" if c.has("GevStreamingMode") else "DeviceStreamProtocol", "GVSP")
                    rep.add("streaming mode", gev.INFO, f"{mode} -> GVSP (--force-gvsp)", c.label)
                except Exception as e:  # noqa: BLE001
                    rep.add("streaming mode", gev.FAIL, f"cannot switch {mode} to GVSP: {e}", c.label)
            else:
                rep.add("streaming mode", gev.FAIL, f"camera streams with {mode} (GEV 3.0 RDMA); this test needs GVSP "
                        "- rerun with --force-gvsp", c.label)
        else:
            rep.add("streaming mode", gev.INFO, f"{mode} (entries {d.get('GevStreamingMode_entries') or d.get('DeviceStreamProtocol_entries')})", c.label)
    if args.pixel_format and not args.fake_cameras:
        try:
            c.set("PixelFormat", args.pixel_format)
            d["PixelFormat"] = c.get("PixelFormat")
        except Exception as e:  # noqa: BLE001
            rep.add("pixel format", gev.FAIL, f"cannot set {args.pixel_format}: {e}", c.label)
    return d


def read_tick_hz(c: VCam) -> int:
    v = c.get("GevTimestampTickFrequency")
    if v is not None:
        try:
            return int(v)
        except ValueError:
            pass
    hi, lo = c.read_reg(gev.REG_TICK_FREQ_HIGH), c.read_reg(gev.REG_TICK_FREQ_LOW)
    return (hi << 32) | lo if hi is not None and lo is not None else 0


# ============================================================================================ PTP
def ptp_snapshot(c: VCam) -> dict[str, Any]:
    latch = c.first(PTP_LATCH)
    if latch:
        try:
            c.execute(latch)
        except Exception:  # noqa: BLE001
            pass
    snap: dict[str, Any] = {}
    st = c.first(PTP_STATUS)
    snap["status"] = c.get(st) if st else None
    off = c.first(PTP_OFFSET) or next((n for n in sorted(c.nodes) if re.match(r"^(Ptp|GevIEEE1588)OffsetFromMaster", n)), None)
    if off:
        v = c.get(off)
        try:
            snap["offset_ns"] = int(float(v)) if v is not None else None
        except ValueError:
            snap["offset_ns"] = None
    sv = c.first(PTP_SERVO)
    if sv:
        snap["servo"] = c.get(sv)
    return snap


def step_ptp(cams: list[VCam], args: argparse.Namespace, rep: gev.Reporter, out: dict[str, Any]) -> bool:
    """Returns True when every camera is PTP-locked."""
    if args.skip_ptp:
        rep.add("PTP", gev.SKIP, "--skip-ptp")
        return False
    enabled = []
    for c in cams:
        en = c.first(PTP_ENABLE)
        if en is None:
            rep.add("PTP enable feature", gev.SKIP, "none of PtpEnable / GevIEEE1588 / PtpMode in the camera XML", c.label)
            continue
        try:
            cur = c.get(en)
            if en == "PtpMode":
                target = args.ptp_mode
                is_on = cur is not None and cur.lower() != "off"
            else:
                target = "true"
                is_on = (cur or "").lower() in ("true", "1")
            if not is_on:
                c.set(en, target, remember=args.restore_ptp)
            if args.ptp_slave_only and c.idx > 0 and c.has("PtpSlaveOnly"):
                c.set("PtpSlaveOnly", "true")
            rep.add("PTP enable feature", gev.PASS, f"{en}: {cur} -> {c.get(en)}", c.label)
            enabled.append(c)
        except Exception as e:  # noqa: BLE001
            rep.add("PTP enable feature", gev.FAIL, f"{en}: {e}", c.label)
    if not enabled:
        rep.add("PTP lock", gev.SKIP, "PTP could not be enabled on any camera")
        return False
    print(f"  waiting up to {args.ptp_timeout:.0f} s for PTP lock ...")
    t0 = time.monotonic()
    stable_since: Optional[float] = None
    timeline = []
    snaps: dict[str, dict[str, Any]] = {}
    locked = False
    while time.monotonic() - t0 <= args.ptp_timeout:
        now = time.monotonic() - t0
        snaps = {c.label: ptp_snapshot(c) for c in enabled}
        timeline.append({"t_s": round(now, 2), **{k: v for k, v in snaps.items()}})
        print(f"    t={now:5.1f}s " + "  ".join(f"{k.split()[0]}={v.get('status')}/{v.get('offset_ns')}ns"
                                               for k, v in snaps.items()))
        states = [str(v.get("status") or "").lower() for v in snaps.values()]
        masters = states.count("master")
        roles = all(s in ("master", "slave") for s in states) and (masters == 1 or (args.external_master and not masters))
        offs = [abs(v["offset_ns"]) for v in snaps.values() if str(v.get("status") or "").lower() == "slave"
                and v.get("offset_ns") is not None]
        good = roles and (not offs or max(offs) <= args.max_ptp_offset_ns)
        if good:
            stable_since = now if stable_since is None else stable_since
            if now - stable_since >= args.stable_s:
                locked = True
                break
        else:
            stable_since = None
        time.sleep(1.0)
    out["ptp_timeline"] = timeline
    detail = "; ".join(f"{k}: {v.get('status')} offset {v.get('offset_ns')} ns"
                       + (f" servo {v['servo']}" if v.get("servo") else "") for k, v in snaps.items())
    if locked:
        rep.add("PTP lock", gev.PASS, f"after {stable_since:.0f} s: {detail}")
    else:
        rep.add("PTP lock", gev.FAIL, f"not locked within {args.ptp_timeout:.0f} s (limit {args.max_ptp_offset_ns} ns): "
                f"{detail}. Check IGMP snooping (disable), one switch/subnet, power-cycle cameras stuck as Master.")
    return locked and len(enabled) == len(cams)


# ============================================================================================ streams
def start_streams(cams: list[VCam], args: argparse.Namespace, stack: contextlib.ExitStack, stop: threading.Event,
                  rep: gev.Reporter) -> list[threading.Thread]:
    threads = []
    for c in cams:
        try:
            st = c.cam.stream(iface=args.iface or None, packet_size=args.packet_size or None,
                              resend=True, deliver_incomplete=True)
            c.stream = st.__enter__()  # starts acquisition
            stack.callback(close_stream, c, st)
        except Exception as e:  # noqa: BLE001
            rep.add("open stream", gev.FAIL, f"{type(e).__name__}: {e}", c.label)
            continue
        t = threading.Thread(target=reader, args=(c, stop), name=f"reader-{c.ip}", daemon=True)
        t.start()
        threads.append(t)
    return threads


def close_stream(c: VCam, st: Any) -> None:
    """Stop acquisition and close the stream without letting a lost camera abort the report."""
    try:
        st.__exit__(None, None, None)
    except Exception as e:  # noqa: BLE001 - e.g. control lost after a heartbeat timeout
        c.error = c.error or f"closing stream: {type(e).__name__}: {e}"


def reader(c: VCam, stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            fr = c.stream.next_frame(timeout_ms=200)
        except Exception as e:  # noqa: BLE001 - TransportError on timeout
            if "timeout" in str(e).lower():
                continue
            c.error = f"{type(e).__name__}: {e}"
            time.sleep(0.05)
            continue
        if fr is None:
            break
        status = getattr(fr.status, "value", str(fr.status))
        c.frames.append(FrameRec(cam=c.idx, block_id=int(fr.block_id), ts_ticks=fr.ts_dev, status=str(status),
                                 missing=fr.missing_packets, host_unix_ns=time.time_ns(),
                                 host_perf_ns=time.perf_counter_ns(), width=int(fr.width), height=int(fr.height),
                                 pixel_format=str(fr.pixel_format)))


def stop_streams(cams: list[VCam], threads: list[threading.Thread], stop: threading.Event) -> None:
    stop.set()
    for t in threads:
        t.join(3.0)
    for c in cams:
        if c.stream is not None:
            try:
                s = c.stream.stats()
                c.stream_stats = {k: getattr(s, k) for k in ("frames_complete", "frames_incomplete", "frames_missed",
                                                              "frames_lost", "packets_missing", "resend_requested",
                                                              "resend_recovered", "avg_fps", "avg_mbps")}
            except Exception:  # noqa: BLE001
                pass


def block_gaps(ids: list[int]) -> int:
    gaps = 0
    for a, b in zip(ids, ids[1:]):
        d = b - a
        if d <= 0 and a > 0xF000:  # 16-bit block ids wrap 65535 -> 1
            d = b + 0xFFFF - a
        if 1 < d < 100_000:
            gaps += d - 1
    return gaps


def frame_quality(cams: list[VCam], args: argparse.Namespace, rep: gev.Reporter, expected: Optional[int]) -> dict[str, Any]:
    q: dict[str, Any] = {}
    for c in cams:
        fr = sorted(c.frames, key=lambda f: f.host_perf_ns)
        n = len(fr)
        incomplete = sum(1 for f in fr if f.status.lower() != "complete")
        gaps = block_gaps([f.block_id for f in fr])
        lost = incomplete + gaps
        pct = 100.0 * lost / (n + gaps) if n + gaps else 100.0
        ts = [f.ts_ns for f in fr if f.ts_ns is not None]
        fps = None
        if len(ts) > 2:
            med = gev.percentile([b - a for a, b in zip(ts, ts[1:])], 50)
            fps = 1e9 / med if med > 0 else None
        q[c.label] = {"frames": n, "incomplete": incomplete, "block_id_gaps": gaps, "lost_pct": pct,
                      "device_fps": fps, "stream_stats": c.stream_stats, "reader_error": c.error}
        exp = f" of ~{expected} requested" if expected else ""
        ok = n > 0 and pct <= args.max_drop_pct
        rep.add("frames received", gev.PASS if ok else gev.FAIL,
                f"{n}{exp}; incomplete {incomplete}, block-id gaps {gaps} ({pct:.2f} % lost, limit {args.max_drop_pct} %)"
                + (f"; device fps {fps:.2f}" if fps else "") + (f"; reader error {c.error}" if c.error else ""), c.label)
        if ok and expected and n < 0.95 * expected:
            rep.add("frame rate", gev.WARN, f"camera delivered {n} frames, fewer than the {expected} the requested "
                    f"{args.fps} fps implies, without losing any - it cannot run that fast (exposure time, "
                    "bandwidth limit, ROI) or ignores AcquisitionFrameRate", c.label)
    return q


def to_ns(cams: list[VCam]) -> None:
    for c in cams:
        for f in c.frames:
            if f.ts_ticks is not None:
                f.ts_ns = gev.ticks_to_ns(int(f.ts_ticks), c.tick_hz or 1_000_000_000)


# ============================================================================================ freerun
def analyse_freerun(cams: list[VCam], args: argparse.Namespace, rep: gev.Reporter, synced: bool) -> dict[str, Any]:
    res: dict[str, Any] = {}
    if len(cams) < 2:
        rep.add("timestamp pairing", gev.SKIP, "needs two or more cameras")
        return res
    ref = sorted([f for f in cams[0].frames if f.ts_ns is not None], key=lambda f: f.ts_ns or 0)
    if len(ref) < 3:
        rep.add("timestamp pairing", gev.FAIL, "camera 0 delivered fewer than 3 timestamped frames")
        return res
    period = gev.percentile([float((b.ts_ns or 0) - (a.ts_ns or 0)) for a, b in zip(ref, ref[1:])], 50)
    others = {c.idx: sorted([f for f in c.frames if f.ts_ns is not None], key=lambda f: f.ts_ns or 0) for c in cams[1:]}
    keys = {i: [f.ts_ns or 0 for f in fr] for i, fr in others.items()}
    spreads: list[float] = []
    offsets: dict[int, list[tuple[float, float]]] = {i: [] for i in others}
    for gi, f0 in enumerate(ref):
        t0 = f0.ts_ns or 0
        group = [f0]
        for i, ks in keys.items():
            j = bisect.bisect_left(ks, t0)
            best = min((k for k in (j - 1, j) if 0 <= k < len(ks)), key=lambda k: abs(ks[k] - t0), default=None)
            if best is not None and abs(ks[best] - t0) <= period / 2:
                group.append(others[i][best])
                offsets[i].append((t0 / 1e9, float(ks[best] - t0)))
        if len(group) == len(cams):
            for f in group:
                f.group = gi
            tss = [f.ts_ns or 0 for f in group]
            spreads.append(float(max(tss) - min(tss)))
    rate = len(spreads) / len(ref)
    res.update(frame_period_ns=period, groups=len(spreads), ref_frames=len(ref), pairing_rate=rate)
    if not synced:
        rep.add("timestamp pairing", gev.INFO, f"{100 * rate:.1f} % of camera-0 frames paired, but device clocks are "
                "not PTP-synchronised, so device timestamps are not comparable across cameras")
    else:
        rep.add("timestamp pairing", gev.PASS if rate >= 0.95 else gev.FAIL,
                f"{len(spreads)}/{len(ref)} camera-0 frames have a partner within half a frame period in every camera "
                f"({100 * rate:.1f} %)")
    if spreads:
        d = gev.describe([s / 1e3 for s in spreads])
        res["spread_us"] = d
        detail = f"median {d['median']:.1f} us, p95 {d['p95']:.1f} us, max {d['max']:.1f} us over {d['n']} groups"
        if args.expect_aligned and synced:
            rep.add("inter-camera timestamp spread", gev.PASS if d["p95"] <= args.max_spread_us else gev.FAIL,
                    detail + f" (limit p95 {args.max_spread_us} us)")
        else:
            rep.add("inter-camera timestamp spread", gev.INFO, detail + " (free-run phase is arbitrary; judged only "
                    "with --expect-aligned)")
    for i, pts in offsets.items():
        if len(pts) < 3:
            continue
        slope, icpt = gev.linear_fit([p[0] for p in pts], [p[1] for p in pts])
        jitter = gev.percentile([abs(p[1] - (slope * p[0] + icpt)) for p in pts], 95)
        med = gev.percentile([p[1] for p in pts], 50)
        res.setdefault("pairwise", {})[cams[i].label] = {"median_offset_us": med / 1e3, "drift_ppm": slope / 1e3,
                                                         "jitter_p95_us": jitter / 1e3}
        rep.add("frame phase vs cam0", gev.INFO, f"median offset {med / 1e3:+.1f} us, frame-clock drift "
                f"{slope / 1e3:+.3f} ppm, jitter p95 {jitter / 1e3:.1f} us"
                + (" - frame timing not locked across cameras" if abs(slope / 1e3) > 1 and synced else ""), cams[i].label)
    return res


def configure_freerun(c: VCam, args: argparse.Namespace, rep: gev.Reporter) -> None:
    try:
        if c.has("TriggerSelector"):
            c.set("TriggerSelector", "FrameStart")
        if c.has("TriggerMode"):
            c.set("TriggerMode", "Off")
        if c.has("AcquisitionFrameRateEnable"):
            c.set("AcquisitionFrameRateEnable", "true")
        fr = c.first(FRAME_RATE)
        if fr:
            c.set(fr, str(args.fps))
        rep.add("free-run setup", gev.INFO, f"TriggerMode={c.get('TriggerMode')}, {fr}={c.get(fr) if fr else 'n/a'}",
                c.label)
    except Exception as e:  # noqa: BLE001
        rep.add("free-run setup", gev.WARN, f"{type(e).__name__}: {e}", c.label)


# ============================================================================================ scheduled action
def configure_action_trigger(c: VCam, args: argparse.Namespace, rep: gev.Reporter) -> bool:
    if args.skip_trigger_config:
        rep.add("action trigger setup", gev.WARN, "--skip-trigger-config: frames are NOT triggered by the actions "
                "(emulator dry run only)", c.label)
        return True
    try:
        entries: list[str] = []
        if c.has("TriggerSelector"):
            c.set("TriggerSelector", "FrameStart")
        if c.has("TriggerSource"):
            try:
                entries = list(c.cam.available_enum_entries("TriggerSource"))
            except Exception:  # noqa: BLE001
                entries = list(c.cam.enum_entries("TriggerSource"))
        src = next((s for s in args.trigger_source.split(",") if s in entries), None)
        if src is None:
            rep.add("action trigger setup", gev.SKIP, f"TriggerSource has none of {args.trigger_source} "
                    f"(entries: {entries})", c.label)
            return False
        c.set("TriggerSource", src)
        if c.has("TriggerMode"):
            c.set("TriggerMode", "On")
        if c.has("ActionSelector"):
            c.set("ActionSelector", "1" if src.endswith("1") else "0")
        for name, val in (("ActionDeviceKey", args.device_key), ("ActionGroupKey", args.group_key),
                          ("ActionGroupMask", args.group_mask)):
            if c.has(name):
                c.set(name, str(val))
            else:
                rep.add("action trigger setup", gev.WARN, f"no {name} feature", c.label)
        if c.has("AcquisitionFrameRateEnable"):
            c.set("AcquisitionFrameRateEnable", "false")
        exp = c.get("ExposureTime") or c.get("ExposureTimeAbs")
        if exp is not None and float(exp) > 0.8e6 / args.fps:
            rep.add("exposure vs trigger period", gev.WARN, f"exposure {float(exp):.0f} us is close to the "
                    f"{1e6 / args.fps:.0f} us trigger period; triggers may be ignored (overtrigger)", c.label)
        rep.add("action trigger setup", gev.PASS, f"TriggerSource={src}, keys 0x{args.device_key:08X}/"
                f"0x{args.group_key:08X}/0x{args.group_mask:08X}", c.label)
        return True
    except Exception as e:  # noqa: BLE001
        rep.add("action trigger setup", gev.FAIL, f"{type(e).__name__}: {e}", c.label)
        return False


class ActionSender(threading.Thread):
    """Sends queued scheduled actions so the scheduling loop never waits for ACKs."""

    def __init__(self, vg: Any, args: argparse.Namespace, dests: list[str], bind_ip: str) -> None:
        super().__init__(name="action-sender", daemon=True)
        self.vg, self.args, self.dests, self.bind_ip = vg, args, dests, bind_ip
        self.q: queue.Queue[Optional[tuple[int, int]]] = queue.Queue()
        self.log: list[dict[str, Any]] = []
        self.backend = args.action_sender

    def run(self) -> None:
        while True:
            item = self.q.get()
            if item is None:
                return
            k, t = item
            for dest in self.dests:
                rec: dict[str, Any] = {"trigger": k, "time_ticks": t, "dest": dest, "host_perf_ns": time.perf_counter_ns()}
                if self.backend == "viva":
                    try:
                        r = self.vg.send_action(self.args.device_key, self.args.group_key, self.args.group_mask,
                                                scheduled_time=t, destination=dest, timeout_ms=self.args.ack_timeout_ms)
                        rec.update(sender="viva", acks=int(r.acks))
                    except Exception as e:  # noqa: BLE001
                        rec["viva_error"] = f"{type(e).__name__}: {e}"
                        self.backend = "stdlib"
                if self.backend == "stdlib":
                    acks = gev.send_action_cmd(dest, self.args.device_key, self.args.group_key, self.args.group_mask,
                                               t, bind_ip=self.bind_ip, wait_s=self.args.ack_timeout_ms / 1000)
                    rec.update(sender="stdlib", acks=len(acks), statuses={ip: gev.gev_status_name(s) for ip, s in acks.items()})
                self.log.append(rec)


def run_scheduled(vg: Any, cams: list[VCam], args: argparse.Namespace, rep: gev.Reporter, synced: bool,
                  stack: contextlib.ExitStack) -> dict[str, Any]:
    res: dict[str, Any] = {}
    ok = [c for c in cams if configure_action_trigger(c, args, rep)]
    if len(ok) != len(cams):
        rep.add("scheduled-action run", gev.SKIP, "not every camera can be triggered by an action command")
        return res
    for c in cams:
        cap = c.read_reg(gev.REG_GVCP_CAPABILITY)
        q = c.read_reg(gev.REG_SCHED_ACTION_QUEUE_SIZE)
        if cap is not None and not cap & gev.CAP["scheduled_action"]:
            rep.add("scheduled action capability", gev.WARN, "capability bit clear - camera may reject scheduled "
                    "actions (trying anyway)", c.label)
        elif q:
            res.setdefault("queue_size", {})[c.label] = q
    period_ns = int(1e9 / args.fps)
    base = cams[0]
    tick = base.tick_hz or 1_000_000_000
    period_ticks = gev.ns_to_ticks(period_ns, tick)
    try:
        t0, t1, dev0 = base.latch_ticks()
    except Exception as e:  # noqa: BLE001
        rep.add("scheduled-action run", gev.SKIP, f"cannot latch camera 0's clock: {e}")
        return res
    if dev0 == 0:
        rep.add("scheduled-action run", gev.SKIP, "camera 0's timestamp latch returns 0 (not implemented)")
        return res
    host_mid = (t0 + t1) // 2
    res["latch_round_trip_us"] = (t1 - t0) / 1e3

    def dev_to_host_perf_ns(ticks: int) -> int:
        return host_mid + gev.ticks_to_ns(ticks - dev0, tick)

    local_ip = args.iface if re.match(r"^\d+\.\d+\.\d+\.\d+$", args.iface or "") else gev.local_ip_towards(base.ip)
    if args.action_dest == "unicast" or (args.action_dest == "auto" and base.ip.startswith("127.")):
        dests = [c.ip for c in cams]
    elif args.action_dest == "auto":
        dests = [gev.broadcast_for(local_ip, base.ip)]
    else:
        dests = [args.action_dest]
    ack_ms = min(args.ack_timeout_ms, max(1, int(0.8 * 1000 / args.fps / max(1, len(dests)))))
    if ack_ms != args.ack_timeout_ms:
        print(f"  ACK wait reduced to {ack_ms} ms so sends keep up with {args.fps} fps")
        args.ack_timeout_ms = ack_ms
    stop = threading.Event()
    threads = start_streams(cams, args, stack, stop, rep)
    sender = ActionSender(vg, args, dests, local_ip)
    sender.start()
    lead_ns = int(args.lead_ms * 1e6)
    t_start = dev0 + gev.ns_to_ticks(int(args.start_delay_ms * 1e6), tick)
    schedule = [t_start + k * period_ticks for k in range(args.triggers)]
    print(f"  {args.triggers} scheduled actions at {args.fps} fps to {dests}, sent {args.lead_ms} ms ahead ...")
    late_sends = 0
    for k, t in enumerate(schedule):
        send_at = dev_to_host_perf_ns(t) - lead_ns
        while True:
            now = time.perf_counter_ns()
            if now >= send_at:
                break
            time.sleep(min(0.002, (send_at - now) / 1e9))
        if time.perf_counter_ns() > dev_to_host_perf_ns(t):
            late_sends += 1
        sender.q.put((k, t))
    time.sleep(args.lead_ms / 1000 + 3 * period_ns / 1e9 + 0.5)
    sender.q.put(None)
    sender.join(5.0)
    stop_streams(cams, threads, stop)
    res.update(schedule_first_ticks=schedule[0], period_ticks=period_ticks, destinations=dests,
               sender_backend=sender.backend, late_sends=late_sends, actions=sender.log)
    acks = [r.get("acks", 0) for r in sender.log]
    expect = len(cams) if len(dests) == 1 else 1
    full = sum(1 for a in acks if a >= expect)
    rep.add("ACTION_ACKs", gev.PASS if acks and full == len(acks) else gev.WARN,
            f"{full}/{len(acks)} sends acknowledged by every addressed camera (sender {sender.backend}); "
            f"{late_sends} sends left after their scheduled time")
    lates = sum(1 for r in sender.log for s in (r.get("statuses") or {}).values() if s == "ACTION_LATE")
    if lates:
        rep.add("ACTION_LATE", gev.WARN, f"{lates} ACKs reported ACTION_LATE - increase --lead-ms")
    to_ns(cams)
    match_frames_to_triggers(cams, schedule, tick, period_ns, rep, res, args, synced)
    return res


def match_frames_to_triggers(cams: list[VCam], schedule: list[int], tick: int, period_ns: int, rep: gev.Reporter,
                             res: dict[str, Any], args: argparse.Namespace, synced: bool) -> None:
    sched_ns = [gev.ticks_to_ns(t, tick) for t in schedule]
    per_trigger: dict[int, dict[int, int]] = {k: {} for k in range(len(schedule))}
    by_order = []
    for c in cams:
        frames = sorted([f for f in c.frames if f.ts_ns is not None], key=lambda f: f.ts_ns or 0)
        matched = 0
        for f in frames:
            j = bisect.bisect_left(sched_ns, f.ts_ns or 0)
            cand = [k for k in (j - 1, j) if 0 <= k < len(sched_ns)]
            if not cand:
                continue
            k = min(cand, key=lambda x: abs(sched_ns[x] - (f.ts_ns or 0)))
            if abs(sched_ns[k] - (f.ts_ns or 0)) <= period_ns / 2 and c.idx not in per_trigger[k]:
                per_trigger[k][c.idx] = f.ts_ns or 0
                f.trigger = k
                matched += 1
        if frames and matched < 0.5 * len(frames):
            by_order.append(c.label)
            for f in frames:
                f.trigger = None
            for k, f in enumerate(frames[:len(schedule)]):
                f.trigger = k
                per_trigger[k][c.idx] = f.ts_ns or 0
        n = sum(1 for k in per_trigger if c.idx in per_trigger[k])
        ok = n >= 0.95 * len(schedule)
        status = (gev.WARN if c.label in by_order else gev.PASS) if ok else gev.FAIL
        rep.add("triggered frames", status, f"{n}/{len(schedule)} actions produced a frame"
                + (" (matched by ORDER: frame timestamps are not on camera 0's timescale)" if c.label in by_order
                   else " (matched by timestamp)"), c.label)
    spreads = []
    lags: dict[int, list[float]] = {c.idx: [] for c in cams}
    for k, got in per_trigger.items():
        for idx, ts in got.items():
            lags[idx].append((ts - sched_ns[k]) / 1e3)
        if len(got) == len(cams) and len(cams) > 1:
            spreads.append((max(got.values()) - min(got.values())) / 1e3)
            for c in cams:
                for f in c.frames:
                    if f.trigger == k:
                        f.group = k
    res["matched_by_order"] = by_order
    for c in cams:
        if lags[c.idx]:
            d = gev.describe(lags[c.idx])
            res.setdefault("lag_us", {})[c.label] = d
            rep.add("frame timestamp - scheduled time", gev.INFO, f"median {d['median']:+.1f} us, p95 {d['p95']:+.1f} us "
                    "(what the timestamp marks - exposure start, end or readout - is vendor-specific)", c.label)
    if len(cams) < 2:
        rep.add("exposure-start spread", gev.SKIP, "needs two or more cameras")
    elif not spreads:
        rep.add("exposure-start spread", gev.FAIL, "no action produced a frame in every camera")
    else:
        d = gev.describe(spreads)
        res["spread_us"] = d
        comparable = synced and not by_order
        detail = f"median {d['median']:.2f} us, p95 {d['p95']:.2f} us, max {d['max']:.2f} us over {d['n']} triggers"
        if comparable:
            rep.add("exposure-start spread", gev.PASS if d["p95"] <= args.max_spread_us else gev.FAIL,
                    detail + f" (limit p95 {args.max_spread_us} us)")
        else:
            rep.add("exposure-start spread", gev.INFO, detail + " - not judged: clocks not PTP-synchronised")


# ============================================================================================ main
def write_outputs(cams: list[VCam], args: argparse.Namespace, out: dict[str, Any], rep: gev.Reporter) -> None:
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, "frames.csv")
    sched = {}
    for a in out.get("scheduled", {}).get("actions", []):
        sched[a["trigger"]] = a["time_ticks"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(CSV_COLUMNS)
        for c in cams:
            for fr in c.frames:
                w.writerow([args.mode, c.idx, c.ip, c.serial, fr.block_id, fr.status, fr.missing, fr.ts_ticks, c.tick_hz,
                            fr.ts_ns, fr.host_unix_ns, fr.host_perf_ns, fr.width, fr.height, fr.pixel_format,
                            fr.group, fr.trigger, sched.get(fr.trigger) if fr.trigger is not None else None])
    print(f"wrote {path}")
    out["checks"] = rep.as_list()
    gev.write_json(os.path.join(args.out, "summary.json"), out)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ip", action="append", default=[], help="camera IP (repeatable, sets camera order); default all")
    ap.add_argument("--iface", default="", help="host interface (IPv4 address or OS name) facing the cameras")
    ap.add_argument("--include-loopback", action="store_true", help="also discover on loopback (emulators)")
    ap.add_argument("--discovery-timeout", type=float, default=1.0)
    ap.add_argument("--mode", choices=["freerun", "scheduled-action"], default="freerun")
    ap.add_argument("--fps", type=float, default=30.0, help="frame rate / trigger rate (default 30)")
    ap.add_argument("--duration", type=float, default=10.0, help="free-run capture seconds (default 10)")
    ap.add_argument("--triggers", type=int, default=150, help="scheduled-action count (default 150)")
    ap.add_argument("--pixel-format", default="", help="set PixelFormat first, e.g. BayerRG8 or Mono8 (8-bit preferred)")
    ap.add_argument("--packet-size", type=int, default=0, help="GevSCPSPacketSize for the streams (default: camera's)")
    ap.add_argument("--force-gvsp", action="store_true", help="switch GevStreamingMode from GVRSP (RDMA) to GVSP")
    ap.add_argument("--skip-ptp", action="store_true", help="do not touch PTP")
    ap.add_argument("--restore-ptp", action="store_true", help="disable PTP again at exit (default: leave it on)")
    ap.add_argument("--ptp-mode", default="Auto", help="value for PtpMode on cameras that use it (Allied Vision)")
    ap.add_argument("--ptp-slave-only", action="store_true", help="set PtpSlaveOnly on all but camera 0 (LUCID)")
    ap.add_argument("--external-master", action="store_true", help="accept all cameras Slave (external grandmaster)")
    ap.add_argument("--ptp-timeout", type=float, default=90.0)
    ap.add_argument("--stable-s", type=float, default=5.0, help="PTP must stay locked this long (default 5 s)")
    ap.add_argument("--max-ptp-offset-ns", type=int, default=1000, help="max |offset from master| (default 1000 ns)")
    ap.add_argument("--max-spread-us", type=float, default=100.0, help="p95 inter-camera spread limit (default 100 us)")
    ap.add_argument("--expect-aligned", action="store_true",
                    help="free-run: judge the spread (a vendor PTP-synchronous free-run mode is enabled)")
    ap.add_argument("--max-drop-pct", type=float, default=0.5, help="max lost frames per camera in %% (default 0.5)")
    ap.add_argument("--trigger-source", default="Action1,Action0", help="TriggerSource preference list")
    ap.add_argument("--skip-trigger-config", action="store_true", help="emulator dry run: send actions, free-run frames")
    ap.add_argument("--device-key", type=gev.int_arg, default=0x12345678)
    ap.add_argument("--group-key", type=gev.int_arg, default=0x1)
    ap.add_argument("--group-mask", type=gev.int_arg, default=0xFFFFFFFF)
    ap.add_argument("--action-dest", default="auto", help="auto (subnet broadcast), unicast, or an IP address")
    ap.add_argument("--action-sender", choices=["viva", "stdlib"], default="viva")
    ap.add_argument("--ack-timeout-ms", type=int, default=20, help="ACK collection per send (default 20 ms)")
    ap.add_argument("--lead-ms", type=float, default=20.0, help="send each scheduled action this early (default 20 ms)")
    ap.add_argument("--start-delay-ms", type=float, default=1000.0, help="first action this long after the latch")
    ap.add_argument("--fake-cameras", type=int, default=0, help="dry run with N viva FakeGigeCameras (N=1 on most hosts)")
    ap.add_argument("--out", default="", help="output directory (default gige_results/viva_<mode>_<time>)")
    ap.add_argument("--selftest", action="store_true", help="run offline checks and exit (needs no viva-genicam)")
    args = ap.parse_args(argv)
    if args.selftest:
        return gev.selftest_main(selftest_extra, title="viva_sync_capture_test selftest")
    vg = import_viva()
    args.out = args.out or os.path.join("gige_results", f"viva_{args.mode}_{time.strftime('%Y%m%d_%H%M%S')}")
    rep = gev.Reporter("viva_sync_capture_test")
    out: dict[str, Any] = {"tool": "viva_sync_capture_test", "host": gev.host_info(), "args": vars(args),
                           "viva_genicam_version": getattr(vg, "__version__", "?")}
    fakes: list[Any] = []
    cams: list[VCam] = []
    try:
        print("== cameras")
        cams = open_cameras(vg, args, rep, fakes)
        if not cams:
            rep.add("cameras", gev.FAIL, "no camera could be opened (check gev_probe.py first)")
            rep.print_summary()
            return 2
        out["cameras"] = [describe_camera(c, args, rep) for c in cams]
        print("== PTP")
        synced = step_ptp(cams, args, rep, out)
        for c, d in zip(cams, out["cameras"]):
            before = d.get("GevTimestampTickFrequency")
            c.tick_hz = read_tick_hz(c)
            d["tick_hz_after_ptp"] = c.tick_hz
            if before and str(c.tick_hz) != before:
                rep.add("tick frequency", gev.INFO, f"changed from {before} to {c.tick_hz} Hz when PTP was enabled "
                        "(streams are opened after this point, so this is handled)", c.label)
        with contextlib.ExitStack() as stack:
            if args.mode == "freerun":
                print(f"== free-run at {args.fps} fps for {args.duration:.0f} s")
                for c in cams:
                    configure_freerun(c, args, rep)
                stop = threading.Event()
                threads = start_streams(cams, args, stack, stop, rep)
                time.sleep(args.duration)
                stop_streams(cams, threads, stop)
                to_ns(cams)
                out["quality"] = frame_quality(cams, args, rep, int(args.fps * args.duration))
                out["freerun"] = analyse_freerun(cams, args, rep, synced)
            else:
                print("== scheduled actions")
                out["scheduled"] = run_scheduled(vg, cams, args, rep, synced, stack)
                if out["scheduled"]:
                    out["quality"] = frame_quality(cams, args, rep, None)
        for c in cams:
            if "control" in c.error.lower():
                rep.add("camera control", gev.FAIL, f"{c.error} - the camera dropped this application (heartbeat "
                        "timeout: network glitch, another application, or the host was too busy)", c.label)
        if not synced and len(cams) > 1:
            print("  note: without PTP lock, device timestamps of different cameras are not comparable")
        write_outputs(cams, args, out, rep)
    finally:
        for c in cams:
            for p in c.restore():
                rep.add("restore features", gev.WARN, p, c.label)
            try:
                c.cam.close()
            except Exception:  # noqa: BLE001
                pass
        for f in fakes:
            out.setdefault("fake_actions_received", []).append(f.actions())
            f.stop()
    rep.print_summary()
    return rep.exit_code()


def selftest_extra(rep: gev.Reporter) -> None:
    rep.check("block-id gap counting (incl. 16-bit wrap)", block_gaps([1, 2, 4, 5]) == 1
              and block_gaps([65534, 65535, 1, 2]) == 0 and block_gaps([65535, 2]) == 1)
    fr = [FrameRec(0, i, i * 1000, "Complete", 0, 0, 0, 1, 1, "Mono8") for i in range(5)]
    c0 = VCam(idx=0, ip="a", cam=None, tick_hz=1_000_000_000, frames=fr)
    c1 = VCam(idx=1, ip="b", cam=None, tick_hz=1_000_000_000,
              frames=[FrameRec(1, i, i * 1000 + 7, "Complete", 0, 0, 0, 1, 1, "Mono8") for i in range(5)])
    to_ns([c0, c1])
    r = gev.Reporter("x", quiet=True)
    ns = argparse.Namespace(expect_aligned=True, max_spread_us=0.01)
    res = analyse_freerun([c0, c1], ns, r, True)
    rep.check("free-run pairing by device timestamp", res.get("groups") == 5 and abs(res["spread_us"]["max"] - 0.007) < 1e-9,
              str(res.get("spread_us")))
    r2 = gev.Reporter("y", quiet=True)
    res2: dict[str, Any] = {}
    match_frames_to_triggers([c0, c1], [0, 1000, 2000, 3000, 4000], 1_000_000_000, 1000, r2, res2,
                             argparse.Namespace(max_spread_us=0.01), True)
    rep.check("scheduled-action matching + spread", res2["spread_us"]["n"] == 5 and abs(res2["spread_us"]["median"] - 0.007) < 1e-9
              and all(x.status == gev.PASS for x in r2.results if x.name == "triggered frames"))


if __name__ == "__main__":
    sys.exit(main())
