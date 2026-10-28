# /// script
# requires-python = ">=3.10"
# ///
"""Linux: which VideoStreaming alt setting does uvcvideo pick, and how many cameras stream at once,
with default quirks vs quirks=128 (UVC_QUIRK_FIX_BANDWIDTH).  Goal 3 harness -- DRAFT, unverified until run.

WHAT TO RUN
  # 1. no root: list cameras, VS alt settings (bytes per service interval), topology
  uv run --script research/usb_cameras/bandwidth/linux/uvc_bw_probe.py list

  # 2. no root: concurrency ramp with the current kernel settings (1..N cameras, same mode)
  uv run --script research/usb_cameras/bandwidth/linux/uvc_bw_probe.py ramp --mode MJPG:1280x720@30 --seconds 8

  # 3. ROOT (comparison baseline): same ramp with default quirks and with quirks=128, per mode.
  #    Writes /sys/module/uvcvideo/parameters/{quirks,trace}, rebinds each camera's uvcvideo interface,
  #    reads dmesg for the driver's "Device requested N B/frame bandwidth" / "Selecting alternate setting" lines,
  #    then RESTORES the original quirks/trace values and rebinds again.
  sudo env "PATH=$PATH" uv run --script research/usb_cameras/bandwidth/linux/uvc_bw_probe.py compare \
       --mode MJPG:1280x720@30 --mode YUYV:640x480@30 --seconds 8

HARDWARE: >=2 UVC cameras; to actually stress one bus, plug them all into ONE USB 2.0 hub (or one root
port through a hub), because xHCI budgets bandwidth per root-hub port (see report).
REQUIREMENTS: 64-bit Linux (struct layouts below are LP64), python>=3.10 (uv), the uvcvideo driver.
Read access to /dev/videoN (user in group 'video' or a seat session). 'compare' needs root.

OUTPUT: results/linux/<hostname>/bw_probe/<subcommand>_<utc>.json  (path printed at the end)
Per attempt: camera identity, requested mode, STREAMON errno, the VS interface's bAlternateSetting and the
endpoint bytes/interval read from sysfs while streaming, frames, fps, payload bytes/s, invalid-JPEG count,
V4L2_BUF_FLAG_ERROR count, and (compare only) the uvcvideo trace lines.
"""
from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import errno
try:
    import fcntl
except ImportError:  # allows --selftest on non-Linux
    fcntl = None
import glob
import json
import mmap
import os
import platform
import re
import select
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path


# ------------------------------------------------------------------ V4L2 ioctls (linux/videodev2.h, LP64)
_IOC_WRITE, _IOC_READ = 1, 2


def _IOC(d, t, nr, size):
    return (d << 30) | (size << 16) | (ord(t) << 8) | nr


V4L2_FMT_SIZE, V4L2_PARM_SIZE, V4L2_REQBUF_SIZE, V4L2_BUF_SIZE = 208, 204, 20, 88
VIDIOC_QUERYCAP = _IOC(_IOC_READ, "V", 0, 104)
VIDIOC_S_FMT = _IOC(_IOC_READ | _IOC_WRITE, "V", 5, V4L2_FMT_SIZE)
VIDIOC_REQBUFS = _IOC(_IOC_READ | _IOC_WRITE, "V", 8, V4L2_REQBUF_SIZE)
VIDIOC_QUERYBUF = _IOC(_IOC_READ | _IOC_WRITE, "V", 9, V4L2_BUF_SIZE)
VIDIOC_QBUF = _IOC(_IOC_READ | _IOC_WRITE, "V", 15, V4L2_BUF_SIZE)
VIDIOC_DQBUF = _IOC(_IOC_READ | _IOC_WRITE, "V", 17, V4L2_BUF_SIZE)
VIDIOC_STREAMON = _IOC(_IOC_WRITE, "V", 18, 4)
VIDIOC_STREAMOFF = _IOC(_IOC_WRITE, "V", 19, 4)
VIDIOC_S_PARM = _IOC(_IOC_READ | _IOC_WRITE, "V", 22, V4L2_PARM_SIZE)
BUF_TYPE_CAPTURE, MEMORY_MMAP, V4L2_BUF_FLAG_ERROR = 1, 1, 0x40
V4L2_CAP_VIDEO_CAPTURE, V4L2_CAP_DEVICE_CAPS = 0x1, 0x80000000
FOURCC = {"MJPG": b"MJPG", "YUYV": b"YUYV", "H264": b"H264", "NV12": b"NV12"}


def _fourcc(s: str) -> int:
    return struct.unpack("<I", FOURCC.get(s, s.encode()[:4].ljust(4)))[0]


# ------------------------------------------------------------------ sysfs helpers
def _rd(p: Path, default=None):
    try:
        return p.read_text().strip()
    except OSError:
        return default


def parse_vs_alts(raw: bytes) -> dict:
    """VS interfaces -> alt settings -> isoc bytes per service interval (from sysfs 'descriptors')."""
    out, i, cur_if, cls, sub, ep = {}, 18, None, None, None, None  # skip 18-byte device descriptor
    speed_hint = None
    while i + 2 <= len(raw):
        ln, typ = raw[i], raw[i + 1]
        if ln < 2:
            break
        d = raw[i:i + ln]
        if typ == 4 and ln >= 9:
            cur_if, alt, cls, sub = d[2], d[3], d[5], d[6]
            ep = None
            if cls == 0x0E and sub == 2:
                out.setdefault(cur_if, []).append({"alt": alt, "endpoints": []})
        elif typ == 5 and ln >= 7 and cls == 0x0E and sub == 2 and cur_if in out:
            wmps = struct.unpack_from("<H", d, 4)[0]
            ep = {"address": f"0x{d[2]:02x}", "type": ["control", "isoc", "bulk", "intr"][d[3] & 3], "wMaxPacketSize": f"0x{wmps:04x}",
                  "bInterval": d[6], "bytes_per_interval_hs": (wmps & 0x7FF) * (((wmps >> 11) & 3) + 1)}
            out[cur_if][-1]["endpoints"].append(ep)
        elif typ == 0x30 and ln >= 6 and ep is not None:
            ep["ss_wBytesPerInterval"] = struct.unpack_from("<H", d, 4)[0]
        i += ln
    return out


def cameras() -> list[dict]:
    cams = []
    for node in sorted(glob.glob("/sys/class/video4linux/video*"), key=lambda p: int(re.sub(r"\D", "", p) or 0)):
        n = Path(node)
        if _rd(n / "index", "0") != "0":
            continue  # metadata node
        intf = (n / "device").resolve()           # .../1-2:1.0  (VideoControl interface)
        if not (intf / "bInterfaceClass").exists():
            continue
        usbdev = intf.parent
        dev = "/dev/" + n.name
        try:
            fd = os.open(dev, os.O_RDWR | os.O_NONBLOCK)
            cap = bytearray(104)
            fcntl.ioctl(fd, VIDIOC_QUERYCAP, cap)
            os.close(fd)
            caps, dcaps = struct.unpack_from("<II", cap, 84)
            if not ((dcaps if caps & V4L2_CAP_DEVICE_CAPS else caps) & V4L2_CAP_VIDEO_CAPTURE):
                continue
        except OSError as e:
            cams.append({"dev": dev, "error": f"open/querycap: {e}"})
            continue
        speed = _rd(usbdev / "speed")
        try:
            raw = (usbdev / "descriptors").read_bytes()
        except OSError:
            raw = b""
        alts = parse_vs_alts(raw)
        vs_ifaces = []
        for k in sorted(alts):
            vs_ifaces.append({"bInterfaceNumber": k, "sysfs": str(usbdev / f"{usbdev.name}:{_rd(usbdev / 'bConfigurationValue', '1')}.{k}"),
                              "alts": [{"alt": a["alt"], "bytes_per_interval": next(
                                  (e.get("ss_wBytesPerInterval", e["bytes_per_interval_hs"]) if speed in ("5000", "10000", "20000")
                                   else e["bytes_per_interval_hs"] for e in a["endpoints"] if e["type"] == "isoc"), 0)}
                                       for a in alts[k]]})
        cams.append({"dev": dev, "name": _rd(n / "name"), "vc_interface": intf.name, "usb_path": usbdev.name,
                     "vid": _rd(usbdev / "idVendor"), "pid": _rd(usbdev / "idProduct"), "serial": _rd(usbdev / "serial"),
                     "product": _rd(usbdev / "product"), "busnum": _rd(usbdev / "busnum"), "devnum": _rd(usbdev / "devnum"),
                     "speed_mbps": speed, "root_port": usbdev.name.split("-")[1].split(".")[0] if "-" in usbdev.name else None,
                     "controller_path": str(usbdev.resolve()).split("/usb")[0], "vs_interfaces": vs_ifaces})
    return cams


def current_alt(cam: dict) -> list[dict]:
    res = []
    for vs in cam.get("vs_interfaces", []):
        p = Path(vs["sysfs"])
        alt = _rd(p / "bAlternateSetting")
        eps = []
        for e in sorted(p.glob("ep_*")):
            eps.append({"ep": e.name, "type": _rd(e / "type"), "wMaxPacketSize": _rd(e / "wMaxPacketSize"), "bInterval": _rd(e / "bInterval")})
        alt_i = int(alt) if alt and alt.strip().isdigit() else None
        bpi = next((a["bytes_per_interval"] for a in vs["alts"] if a["alt"] == alt_i), None)
        res.append({"interface": vs["bInterfaceNumber"], "bAlternateSetting": alt_i, "bytes_per_interval": bpi, "endpoints": eps})
    return res


# ------------------------------------------------------------------ capture
class Stream:
    def __init__(self, cam: dict, fmt: str, w: int, h: int, fps: float, nbufs: int = 4):
        self.cam, self.fmt, self.w, self.h, self.fps = cam, fmt, w, h, fps
        self.r = {"dev": cam["dev"], "vid": cam["vid"], "pid": cam["pid"], "serial": cam.get("serial"), "mode": f"{fmt}:{w}x{h}@{fps}",
                  "streamon_errno": None, "error": None, "frames": 0, "bytes": 0, "error_flag_frames": 0, "invalid_jpeg": 0,
                  "seq_gaps": 0}
        self.fd = os.open(cam["dev"], os.O_RDWR | os.O_NONBLOCK)
        f = bytearray(V4L2_FMT_SIZE)
        struct.pack_into("<I", f, 0, BUF_TYPE_CAPTURE)
        struct.pack_into("<IIII", f, 8, w, h, _fourcc(fmt), 1)  # field NONE
        fcntl.ioctl(self.fd, VIDIOC_S_FMT, f)
        gw, gh, gfcc = struct.unpack_from("<III", f, 8)
        self.r["got_format"] = f"{struct.pack('<I', gfcc).decode(errors='replace')}:{gw}x{gh}"
        p = bytearray(V4L2_PARM_SIZE)
        struct.pack_into("<I", p, 0, BUF_TYPE_CAPTURE)
        struct.pack_into("<II", p, 4 + 8, 1000, int(round(fps * 1000)))  # timeperframe num/den
        fcntl.ioctl(self.fd, VIDIOC_S_PARM, p)
        num, den = struct.unpack_from("<II", p, 12)
        self.r["got_fps"] = den / num if num else None
        rq = bytearray(V4L2_REQBUF_SIZE)
        struct.pack_into("<III", rq, 0, nbufs, BUF_TYPE_CAPTURE, MEMORY_MMAP)
        fcntl.ioctl(self.fd, VIDIOC_REQBUFS, rq)
        self.maps = []
        for i in range(struct.unpack_from("<I", rq, 0)[0]):
            b = self._buf(i)
            fcntl.ioctl(self.fd, VIDIOC_QUERYBUF, b)
            off, length = struct.unpack_from("<I", b, 64)[0], struct.unpack_from("<I", b, 72)[0]
            self.maps.append(mmap.mmap(self.fd, length, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=off))
            fcntl.ioctl(self.fd, VIDIOC_QBUF, b)
        self.last_seq = None
        self.t_first = None
        self.t_last = None

    @staticmethod
    def _buf(i: int) -> bytearray:
        b = bytearray(V4L2_BUF_SIZE)
        struct.pack_into("<II", b, 0, i, BUF_TYPE_CAPTURE)
        struct.pack_into("<I", b, 60, MEMORY_MMAP)
        return b

    def start(self) -> bool:
        try:
            fcntl.ioctl(self.fd, VIDIOC_STREAMON, struct.pack("<I", BUF_TYPE_CAPTURE))
            return True
        except OSError as e:
            self.r["streamon_errno"] = errno.errorcode.get(e.errno, e.errno)
            self.r["error"] = str(e)
            return False

    def service(self, warm_until: float):
        b = self._buf(0)
        try:
            fcntl.ioctl(self.fd, VIDIOC_DQBUF, b)
        except OSError as e:
            if e.errno == errno.EAGAIN:
                return
            self.r["error"] = f"DQBUF: {e}"
            raise
        idx, _, used, flags = struct.unpack_from("<IIII", b, 0)
        seq = struct.unpack_from("<I", b, 56)[0]
        now = time.monotonic()
        if now >= warm_until:
            if self.t_first is None:
                self.t_first = now
            else:
                self.r["frames"] += 1
                self.r["bytes"] += used
            self.t_last = now
            if flags & V4L2_BUF_FLAG_ERROR:
                self.r["error_flag_frames"] += 1
            if self.fmt == "MJPG":
                m = self.maps[idx]
                if used < 4 or m[0:2] != b"\xff\xd8" or b"\xff\xd9" not in m[max(0, used - 64):used]:
                    self.r["invalid_jpeg"] += 1
            if self.last_seq is not None and seq != self.last_seq + 1:
                self.r["seq_gaps"] += 1
        self.last_seq = seq
        fcntl.ioctl(self.fd, VIDIOC_QBUF, b)

    def close(self):
        try:
            fcntl.ioctl(self.fd, VIDIOC_STREAMOFF, struct.pack("<I", BUF_TYPE_CAPTURE))
        except OSError:
            pass
        for m in self.maps:
            m.close()
        os.close(self.fd)
        if self.t_first and self.t_last and self.t_last > self.t_first:
            dtv = self.t_last - self.t_first
            self.r["fps"] = round(self.r["frames"] / dtv, 3)
            self.r["bytes_per_s"] = round(self.r["bytes"] / dtv)
            self.r["mean_frame_bytes"] = round(self.r["bytes"] / max(1, self.r["frames"]))


def xhci_port_bw() -> dict:
    """Root only: xHCI 'Get Port Bandwidth' per root port (available %, per speed), Linux >= 6.16
    (drivers/usb/host/xhci-debugfs.c, commit 59d50e53e070). Empty dict if unavailable."""
    out = {}
    for f in glob.glob("/sys/kernel/debug/usb/xhci/*/port_bandwidth/*_BW"):
        try:
            out[f] = Path(f).read_text().strip().splitlines()
        except OSError as e:
            out[f] = f"error: {e}"
    return out


def run_attempt(cams: list[dict], mode: str, seconds: float) -> dict:
    fmt, rest = mode.split(":")
    wh, fps = rest.split("@")
    w, h = (int(x) for x in wh.split("x"))
    streams, att = [], {"mode": mode, "n_cameras": len(cams), "cameras": []}
    for c in cams:
        try:
            streams.append(Stream(c, fmt, w, h, float(fps)))
        except OSError as e:
            att["cameras"].append({"dev": c["dev"], "error": f"setup: {e}"})
    started = [s for s in streams if s.start()]
    time.sleep(1.5)
    for s in streams:
        s.r["alt_while_streaming"] = current_alt(s.cam)
    att["xhci_port_bw_while_streaming"] = xhci_port_bw() if os.geteuid() == 0 else "needs root"
    warm_until = time.monotonic() + 1.0
    t_end = time.monotonic() + seconds
    while time.monotonic() < t_end and started:
        rl, _, _ = select.select([s.fd for s in started], [], [], 0.5)
        for s in started:
            if s.fd in rl:
                try:
                    s.service(warm_until)
                except OSError:
                    started = [x for x in started if x is not s]
    for s in streams:
        s.close()
        att["cameras"].append(s.r)
    att["all_streamed"] = all(c.get("frames", 0) > 0 for c in att["cameras"])
    return att


def ramp(cams: list[dict], modes: list[str], seconds: float) -> list[dict]:
    out = []
    for mode in modes:
        for k in range(1, len(cams) + 1):
            a = run_attempt(cams[:k], mode, seconds)
            out.append(a)
            print(f"  {mode} x{k}: " + ", ".join(
                f"{c.get('dev')} {'ERR ' + str(c.get('streamon_errno') or c.get('error')) if not c.get('frames') else str(c.get('fps')) + 'fps'}"
                f" alt={[x['bAlternateSetting'] for x in c.get('alt_while_streaming', [])]}" for c in a["cameras"]), flush=True)
            time.sleep(0.5)
    return out


# ------------------------------------------------------------------ root-only: quirks + rebind
PARAM = Path("/sys/module/uvcvideo/parameters")
DRV = Path("/sys/bus/usb/drivers/uvcvideo")


def _w(p: Path, v: str):
    p.write_text(v)


def rebind(cams: list[dict]):
    for c in cams:
        try:
            _w(DRV / "unbind", c["vc_interface"])
        except OSError as e:
            print(f"unbind {c['vc_interface']}: {e}", file=sys.stderr)
    time.sleep(0.5)
    for c in cams:
        try:
            _w(DRV / "bind", c["vc_interface"])
        except OSError as e:
            print(f"bind {c['vc_interface']}: {e}", file=sys.stderr)
    time.sleep(2.0)


def dmesg_since(mark: str) -> list[str]:
    try:
        txt = subprocess.run(["dmesg"], capture_output=True, text=True, timeout=10).stdout
    except Exception as e:  # noqa: BLE001
        return [f"dmesg failed: {e}"]
    lines = txt.splitlines()
    for i in range(len(lines) - 1, -1, -1):
        if mark in lines[i]:
            lines = lines[i + 1:]
            break
    keep = re.compile(r"uvcvideo|Device requested|Selecting alternate|Forcing device quirks|bandwidth|non compliance", re.I)
    return [ln for ln in lines if keep.search(ln)]


def kmsg_mark(tag: str):
    try:
        Path("/dev/kmsg").write_text(f"skellycam-bw-mark {tag}\n")
    except OSError:
        pass


def compare(cams: list[dict], modes: list[str], seconds: float) -> dict:
    if os.geteuid() != 0:
        sys.exit("'compare' needs root (writes /sys/module/uvcvideo/parameters and rebinds the driver)")
    orig = {"quirks": _rd(PARAM / "quirks"), "trace": _rd(PARAM / "trace")}
    res = {"original_params": orig, "runs": []}
    try:
        for q in ("4294967295", "128"):  # -1 (= use per-device table) and FIX_BANDWIDTH
            _w(PARAM / "quirks", q)
            _w(PARAM / "trace", str(0x400))  # UVC_DBG_VIDEO: "Device requested ..." / "Selecting alternate setting ..."
            tag = f"quirks={q}-{time.time():.0f}"
            kmsg_mark(tag)
            rebind(cams)
            fresh = [c for c in cameras() if "error" not in c]
            fresh = [c for c in fresh if any(c["usb_path"] == o["usb_path"] for o in cams)]
            print(f"quirks={q}: {len(fresh)} cameras after rebind", flush=True)
            r = {"quirks_param": q, "probe_log": dmesg_since(tag), "attempts": []}
            for mode in modes:
                for k in range(1, len(fresh) + 1):
                    mark = f"{tag}-{mode}-{k}"
                    kmsg_mark(mark)
                    a = run_attempt(fresh[:k], mode, seconds)
                    a["uvc_trace"] = dmesg_since(mark)
                    r["attempts"].append(a)
                    print(f"  {mode} x{k}: all_streamed={a['all_streamed']} alts=" + str(
                        [[x['bAlternateSetting'] for x in c.get('alt_while_streaming', [])] for c in a['cameras']]), flush=True)
            res["runs"].append(r)
    finally:
        _w(PARAM / "quirks", orig["quirks"] or "4294967295")
        _w(PARAM / "trace", orig["trace"] or "0")
        rebind(cams)
        res["restored"] = {"quirks": _rd(PARAM / "quirks"), "trace": _rd(PARAM / "trace")}
    return res


def selftest(topology: Path) -> int:
    """Parse the raw config descriptors captured on Windows (prefixed with a dummy 18-byte device descriptor,
    as in sysfs 'descriptors') and check the alt-setting byte counts match the Windows parser's."""
    doc = json.loads(topology.read_text())
    bad = 0
    for c in doc["cameras"]:
        alts = parse_vs_alts(bytes(18) + bytes.fromhex(c["config_descriptor_hex"]))
        ss = c["speed"].startswith("super")
        for ifn, vs in c["uvc"]["vs_interfaces"].items():
            mine = [next((e.get("ss_wBytesPerInterval", e["bytes_per_interval_hs"]) if ss else e["bytes_per_interval_hs"]
                          for e in a["endpoints"] if e["type"] == "isoc"), 0) for a in alts[int(ifn)]]
            theirs = [a["endpoints"][0]["bytes_per_interval"] if a["endpoints"] else 0 for a in vs["alt_settings"]]
            ok = mine == theirs
            bad += not ok
            print(f"{c['idVendor']}:{c['idProduct']} if{ifn} {'OK' if ok else 'MISMATCH'} {mine}")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["list", "ramp", "compare", "selftest"])
    ap.add_argument("--mode", action="append", help="FOURCC:WxH@fps, e.g. MJPG:1280x720@30 (repeatable)")
    ap.add_argument("--seconds", type=float, default=8)
    ap.add_argument("--dev", action="append", help="limit to these /dev/videoN (default: all UVC capture nodes)")
    ap.add_argument("--topology-json", help="selftest: Windows bw_topology/topology.json with config_descriptor_hex")
    a = ap.parse_args()
    if a.cmd == "selftest":
        return selftest(Path(a.topology_json))
    if not sys.platform.startswith("linux"):
        sys.exit("uvc_bw_probe.py is Linux-only")
    if struct.calcsize("P") != 8:
        sys.exit("uvc_bw_probe.py assumes a 64-bit (LP64) kernel ABI for v4l2 structs")
    cams = [c for c in cameras() if "error" not in c and (not a.dev or c["dev"] in a.dev)]
    host = socket.gethostname()
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    doc = {"test": "bw_probe", "subcommand": a.cmd, "platform": "linux", "hostname": host, "utc_started": stamp,
           "command": " ".join(sys.argv), "environment": {"kernel": platform.release(), "os": platform.platform(),
                                                          "python": platform.python_version(),
                                                          "uvcvideo_quirks": _rd(PARAM / "quirks"),
                                                          "usbfs_memory_mb": _rd(Path("/sys/module/usbcore/parameters/usbfs_memory_mb"))},
           "cameras": cams}
    for c in cams:
        print(f"{c['dev']} {c['vid']}:{c['pid']} {c.get('product')!r} speed={c['speed_mbps']} usb={c['usb_path']} "
              f"VS alts={[ (x['alt'], x['bytes_per_interval']) for v in c['vs_interfaces'] for x in v['alts']]}")
    modes = a.mode or ["MJPG:1280x720@30"]
    if a.cmd == "ramp":
        doc["attempts"] = ramp(cams, modes, a.seconds)
    elif a.cmd == "compare":
        doc["compare"] = compare(cams, modes, a.seconds)
    out = Path(__file__).resolve().parents[2] / "results" / "linux" / host / "bw_probe" / f"{a.cmd}_{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
