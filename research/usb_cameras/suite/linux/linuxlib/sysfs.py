"""sysfs / devfs readers for the Linux suite: camera discovery, descriptor summary, power and holder state.

Stdlib only. Nothing here opens a /dev node: discovery uses /sys/class/video4linux and the USB device's sysfs
attributes, which are world-readable and cause no USB traffic (``descriptors`` is the kernel's cached copy).

Test hook: every path is prefixed with $SKELLYCAM_LINUX_ROOT (default ''), so unit tests can point the code at a
fake tree (suite/linux/unit/fakesysfs.py). Real runs leave it unset.

Logic borrowed from research/usb_cameras/naming/linux_identity.py (usb_device_dir, pci_controller, symlink maps)
and timing/linux/v4l2_uvc_timing.py (capture/metadata node pairing); identity keys come from common.identity
(the naming/camera_identity.py scheme: serial if usable and unique, else 'pci-<controller>/<port chain>').
"""
from __future__ import annotations

import glob
import os
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SUITE_DIR = HERE.parents[1]
if str(SUITE_DIR) not in sys.path:
    sys.path.insert(0, str(SUITE_DIR))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from common import identity  # noqa: E402
import usbdesc  # noqa: E402

ROOT_ENV = "SKELLYCAM_LINUX_ROOT"
KIYO_VIDPID = ("1532", "0e05")
USB_QUIRK_NO_LPM = 0x400  # include/linux/usb/quirks.h BIT(10)
SPEED_NAMES = {"1.5": "LS", "12": "FS", "480": "HS", "5000": "SS", "10000": "SS+", "20000": "SS+"}
SPEED_USBDESC = {"LS": "low", "FS": "full", "HS": "high", "SS": "super", "SS+": "super_plus"}
FOURCC_DESC_TO_V4L2 = {"YUY2": "YUYV", "MJPG": "MJPG", "NV12": "NV12", "H264": "H264", "I420": "YU12",
                       "M420": "M420", "UYVY": "UYVY", "Y800": "GREY", "RGBP": "RGBP"}


def root() -> str:
    return os.environ.get(ROOT_ENV, "").rstrip("/")


def P(path: str) -> Path:
    """Absolute system path ('/sys/...') under the configured root."""
    return Path(root() + path)


def unroot(p: Path | str) -> str:
    s = str(p)
    r = root()
    return s[len(r):] if r and s.startswith(r) else s


def rd(p: Path | str) -> str | None:
    try:
        return Path(p).read_text(errors="replace").strip()
    except OSError:
        return None


def rd_int(p: Path | str, base: int = 10) -> int | None:
    v = rd(p)
    if v is None:
        return None
    try:
        return int(v, base)
    except ValueError:
        return None


def link_name(p: Path) -> str | None:
    try:
        return os.path.basename(os.path.realpath(p)) if os.path.lexists(p) else None
    except OSError:
        return None


def node_number(name: str) -> int:
    m = re.search(r"(\d+)$", name)
    return int(m.group(1)) if m else 1 << 30


def usb_device_dir(p: Path) -> Path | None:
    """Nearest ancestor (or self) holding idVendor: the USB device directory."""
    for cand in (p, *p.parents):
        if (cand / "idVendor").exists():
            return cand
        if cand == cand.parent:
            break
    return None


def pci_controller(usb_dir: Path) -> str | None:
    """Host controller sysfs name: the path element above 'usbN' (e.g. '0000:00:14.0' or 'xhci-hcd.0.auto')."""
    parts = usb_dir.parts
    for i, part in enumerate(parts):
        if re.fullmatch(r"usb\d+", part) and i > 0:
            return parts[i - 1]
    return None


def symlink_map(d: Path) -> dict[str, list[str]]:
    """realpath -> [link names] for /dev/v4l/by-id or by-path."""
    out: dict[str, list[str]] = {}
    for p in sorted(glob.glob(str(d / "*"))):
        out.setdefault(os.path.realpath(p), []).append(os.path.basename(p))
    return out


# ----------------------------------------------------------------------------------------- descriptors
def descriptor_summary(raw: bytes | None, speed: str | None) -> dict[str, Any]:
    """Parse the sysfs 'descriptors' blob (device + every configuration) with usbdesc and flatten what the suite
    needs: UVC version, clock, CT/PU controls (bmControls), extension units, formats/frames per streaming
    interface, alt table per VS interface (max_packet, mult, bytes per interval) and the device descriptor."""
    out: dict[str, Any] = {"ok": False}
    if not raw:
        out["error"] = "no descriptors"
        return out
    try:
        d = usbdesc.parse_sysfs_descriptors(raw, SPEED_USBDESC.get(speed or "", None))
    except Exception as e:  # malformed: record, never raise
        out["error"] = f"{type(e).__name__}: {e}"
        return out
    out["device"] = d.get("device")
    cfg = (d.get("configurations") or [None])[0]
    if not cfg:
        out["error"] = "no configuration"
        return out
    out["ok"] = True
    out["interfaces"] = [{"number": i["bInterfaceNumber"], "alt": i["bAlternateSetting"], "kind": i["kind"],
                          "class": i["bInterfaceClass"], "subclass": i["bInterfaceSubClass"],
                          "endpoints": [_ep_pipe(e, speed) for e in i["endpoints"]]} for i in cfg["interfaces"]]
    u = cfg.get("uvc")
    if not u:
        return out
    out["bcdUVC"] = u.get("bcdUVC")
    out["dwClockFrequency"] = u.get("dwClockFrequency")
    ct, pu, xus = [], [], []
    for unit in u.get("units") or []:
        st = unit.get("subtype")
        if st == "VC_INPUT_TERMINAL" and unit.get("wTerminalType") == "ITT_CAMERA":
            ct = list(unit.get("controls") or [])
            out["ct_bmControls"] = unit.get("bmControls")
        elif st == "VC_PROCESSING_UNIT":
            pu = list(unit.get("controls") or [])
            out["pu_bmControls"] = unit.get("bmControls")
        elif st == "VC_EXTENSION_UNIT":
            xus.append({"unit": unit.get("bUnitID"), "guid": unit.get("guidExtensionCode"),
                        "known_as": unit.get("known_as"), "bNumControls": unit.get("bNumControls"),
                        "bmControls": unit.get("bmControls")})
    out["ct_controls"], out["pu_controls"], out["extension_units"] = ct, pu, xus
    streams = []
    for s in u.get("streaming_interfaces") or []:
        modes = []
        for f in s.get("formats") or []:
            fcc = f.get("fourcc") or f.get("format")
            fcc = "MJPG" if f.get("format") == "MJPEG" else fcc
            v4 = FOURCC_DESC_TO_V4L2.get(fcc or "", fcc)
            for fr in f.get("frames") or []:
                m = {"fourcc_desc": fcc, "fourcc": v4, "w": fr.get("wWidth"), "h": fr.get("wHeight"),
                     "interval_type": fr.get("interval_type"), "default_interval": fr.get("dwDefaultFrameInterval")}
                if fr.get("interval_type") == "discrete":
                    m["fps"] = sorted({round(1e7 / iv, 3) for iv in fr.get("dwFrameInterval") or [] if iv},
                                      reverse=True)
                else:
                    m["fps_min"], m["fps_max"] = fr.get("fps_min"), fr.get("fps_max")
                modes.append(m)
        alts = []
        for a in s.get("alt_settings") or []:
            if a.get("transfer_type") != "isochronous":
                continue
            mp, mult = _maxpacket_mult(a, speed)
            alts.append({"alt": a["bAlternateSetting"], "max_packet": mp, "mult": mult,
                         "bytes_per_interval": a.get("bytes_per_interval"), "bInterval": a.get("bInterval"),
                         "ep": a.get("bEndpointAddress")})
        streams.append({"interface": s.get("bInterfaceNumber"), "transport": s.get("transport"), "modes": modes,
                        "alt_table": alts})
    out["streams"] = streams
    return out


def _maxpacket_mult(a: dict, speed: str | None) -> tuple[int, int]:
    """(base packet, transactions per interval). SuperSpeed: (wMaxPacketSize, bursts x mult) per the snapshot
    convention; high speed: wMaxPacketSize bits 0-10 and 1 + bits 11-12 (NOT the sysfs ep_XX value, which drops
    the multiplier bits: topology_linux verifier note 1)."""
    raw = int(a.get("wMaxPacketSize_raw") or 0)
    comp = a.get("ss_companion")
    if speed in ("SS", "SS+") and comp:
        burst = int(comp.get("bMaxBurst") or 0) + 1
        mult = (int(comp.get("bmAttributes") or 0) & 0x3) + 1
        return raw & 0x7FF, burst * mult
    return raw & 0x7FF, ((raw >> 11) & 0x3) + 1


def _ep_pipe(ep: dict, speed: str | None) -> dict[str, Any]:
    t = ep.get("transfer_type")
    mp, mult = _maxpacket_mult(ep, speed)
    return {"ep": ep.get("bEndpointAddress"), "type": {"isochronous": "iso", "interrupt": "int"}.get(t, t),
            "max_packet": mp, "mult": mult, "interval": ep.get("bInterval"), "direction": ep.get("direction")}


def mjpeg_modes(desc: dict) -> list[tuple[int, int, float]]:
    """(w, h, fps) of every MJPEG mode in the descriptors (continuous ranges give min and max fps)."""
    out = set()
    for s in desc.get("streams") or []:
        for m in s.get("modes") or []:
            if m.get("fourcc") != "MJPG":
                continue
            for f in m.get("fps") or [m.get("fps_max"), m.get("fps_min")]:
                if f:
                    out.add((int(m["w"]), int(m["h"]), float(f)))
    return sorted(out, key=lambda t: (t[0] * t[1], t[2]))


def pick_modes(desc: dict) -> dict[str, Any]:
    """Default and small test modes from the descriptors (no device access).
    default: MJPG 1280x720@30 if offered, else the largest MJPEG size <= 1280x720 at its highest fps, else the
    first MJPEG mode. small: MJPG 640x480@30 if offered, else the smallest MJPEG size >= 320x240 at its highest
    fps. large: the largest MJPEG size at its highest fps."""
    modes = mjpeg_modes(desc)
    if not modes:
        return {"default": None, "small": None, "large": None, "all_mjpeg": []}

    def best_at(pred):
        cands = [m for m in modes if pred(m)]
        if not cands:
            return None
        area = max(c[0] * c[1] for c in cands)
        return max((c for c in cands if c[0] * c[1] == area), key=lambda c: c[2])

    def fmt(m):
        return None if m is None else {"fourcc": "MJPG", "w": m[0], "h": m[1], "fps": m[2]}

    d = next((m for m in modes if m[:2] == (1280, 720) and abs(m[2] - 30) < 0.5), None) \
        or best_at(lambda m: m[0] * m[1] <= 1280 * 720) or modes[0]
    s = next((m for m in modes if m[:2] == (640, 480) and abs(m[2] - 30) < 0.5), None)
    if s is None:
        ge = [m for m in modes if m[0] * m[1] >= 320 * 240]
        if ge:
            area = min(m[0] * m[1] for m in ge)
            s = max((m for m in ge if m[0] * m[1] == area), key=lambda m: m[2])
        else:
            s = modes[0]
    big = best_at(lambda m: True)
    return {"default": fmt(d), "small": fmt(s), "large": fmt(big), "all_mjpeg": [fmt(m) for m in modes]}


# ----------------------------------------------------------------------------------------- devices / cameras
def usb_attrs(usb_dir: Path) -> dict[str, Any]:
    keys = ("idVendor", "idProduct", "bcdDevice", "manufacturer", "product", "serial", "busnum", "devnum",
            "devpath", "speed", "version", "removable", "maxchild", "quirks", "bDeviceClass", "bDeviceProtocol",
            "bNumInterfaces", "configuration", "avoid_reset_quirk", "ltm_capable", "rx_lanes", "tx_lanes",
            "port/connect_type", "port/location", "power/control", "power/autosuspend_delay_ms",
            "power/runtime_status", "power/connected_duration", "power/active_duration",
            "power/usb3_hardware_lpm_u1", "power/usb3_hardware_lpm_u2", "power/usb2_hardware_lpm",
            "power/persist", "power/level")
    return {k: rd(usb_dir / k) for k in keys}


def interface_dirs(usb_dir: Path) -> list[Path]:
    name = usb_dir.name
    return sorted((p for p in usb_dir.glob(f"{name}:*") if p.is_dir()), key=lambda p: p.name)


def vs_interfaces(usb_dir: Path) -> list[dict[str, Any]]:
    """Video streaming interfaces with their CURRENT alt setting (non-zero = streaming isochronous now)."""
    out = []
    for itf in interface_dirs(usb_dir):
        if rd(itf / "bInterfaceClass") == "0e" and rd(itf / "bInterfaceSubClass") == "02":
            out.append({"interface": itf.name, "number": rd_int(itf / "bInterfaceNumber", 16),
                        "alt": rd_int(itf / "bAlternateSetting", 10)})
    return out


def _video_nodes() -> list[dict[str, Any]]:
    nodes = []
    for v in sorted(glob.glob(str(P("/sys/class/video4linux/video*"))), key=lambda s: node_number(s)):
        vp = Path(v)
        try:
            itf = (vp / "device").resolve(strict=True)
        except OSError:
            continue
        ud = usb_device_dir(itf)
        nodes.append({"name": vp.name, "index": rd_int(vp / "index"), "v4l_name": rd(vp / "name"),
                      "interface": itf.name, "interface_dir": itf, "usb_dir": ud,
                      "driver": link_name(itf / "driver"), "dev_major_minor": rd(vp / "dev")})
    return nodes


def discover_cameras() -> list[dict[str, Any]]:
    """All USB video4linux devices, one entry per USB device (Kiyo and everything else included; never filtered).

    Each entry: key, key_kind, name, vid, pid, serial, bcd_device, is_kiyo, node (capture /dev/videoN),
    meta_node, other_nodes, usb_name ('3-13.1.4'), sysfs_dir, busnum, devnum, devpath, speed, version,
    pci_controller, port_path, by_id, by_path, vs_interfaces, descriptors (summary), modes (default/small/large),
    quirks, no_lpm_quirk, power."""
    by_id = symlink_map(P("/dev/v4l/by-id"))
    by_path = symlink_map(P("/dev/v4l/by-path"))
    groups: dict[str, dict[str, Any]] = {}
    for n in _video_nodes():
        if n["usb_dir"] is None:
            continue
        g = groups.setdefault(str(n["usb_dir"]), {"usb_dir": n["usb_dir"], "nodes": []})
        g["nodes"].append(n)
    cams = []
    for g in groups.values():
        ud: Path = g["usb_dir"]
        a = usb_attrs(ud)
        speed = SPEED_NAMES.get(a.get("speed") or "", "unknown")
        nodes = sorted(g["nodes"], key=lambda n: node_number(n["name"]))
        # uvcvideo registers per stream: capture node (even index), then its metadata node (index + 1)
        caps = [n for n in nodes if (n["index"] or 0) % 2 == 0]
        metas = [n for n in nodes if (n["index"] or 0) % 2 == 1]
        cap = caps[0] if caps else nodes[0]
        meta = next((m for m in metas if m["index"] == (cap["index"] or 0) + 1), None)
        raw = None
        try:
            raw = (ud / "descriptors").read_bytes()
        except OSError:
            pass
        desc = descriptor_summary(raw, speed)
        vid, pid = (a.get("idVendor") or "").lower(), (a.get("idProduct") or "").lower()
        ctrl = pci_controller(ud)
        node_path = root() + "/dev/" + cap["name"]
        q = a.get("quirks")
        try:
            qv = int(q, 16) if q else None
        except ValueError:
            qv = None
        cam = {
            "name": a.get("product") or cap.get("v4l_name") or ud.name,
            "vid": vid, "pid": pid, "serial": a.get("serial"), "bcd_device": a.get("bcdDevice"),
            "manufacturer": a.get("manufacturer"),
            "is_kiyo": (vid, pid) == KIYO_VIDPID,
            "node": "/dev/" + cap["name"], "node_fs": node_path,
            "meta_node": ("/dev/" + meta["name"]) if meta else None,
            "other_nodes": ["/dev/" + n["name"] for n in nodes if n is not cap and n is not meta],
            "v4l_names": {("/dev/" + n["name"]): n["v4l_name"] for n in nodes},
            "interface_driver": cap.get("driver"),
            "usb_name": ud.name, "sysfs_dir": unroot(ud),
            "busnum": a.get("busnum"), "devnum": a.get("devnum"), "devpath": a.get("devpath"),
            "speed": speed, "version": (a.get("version") or "").strip(),
            "speed_downgraded": bool(speed == "HS" and (a.get("version") or "").strip().startswith("3")),
            "pci_controller": ctrl, "port_path": identity.port_path_from_linux(ctrl, ud.name),
            "by_id": by_id.get(os.path.realpath(node_path), []),
            "by_path": by_path.get(os.path.realpath(node_path), []),
            "meta_by_id": by_id.get(os.path.realpath(root() + meta_node_dev(meta)), []) if meta else [],
            "vs_interfaces": vs_interfaces(ud),
            "descriptors": desc,
            "modes": pick_modes(desc),
            "quirks": q, "no_lpm_quirk": (bool(qv & USB_QUIRK_NO_LPM) if qv is not None else None),
            "power": {k.split("/", 1)[1]: v for k, v in a.items() if k.startswith("power/")},
            "port_connect_type": a.get("port/connect_type"), "port_location": a.get("port/location"),
        }
        cams.append(cam)
    cams.sort(key=lambda c: node_number(c["node"]))
    identity.assign_keys(cams)
    for c in cams:
        c["metadata_tier0"] = c["meta_node"] is not None
    return cams


def meta_node_dev(meta: dict | None) -> str:
    return ("/dev/" + meta["name"]) if meta else ""


def camera_brief(c: dict[str, Any]) -> dict[str, Any]:
    """The camera fields every result JSON carries (small)."""
    keys = ("key", "key_kind", "name", "vid", "pid", "serial", "bcd_device", "is_kiyo", "node", "meta_node",
            "usb_name", "busnum", "devnum", "speed", "pci_controller", "port_path", "by_id", "by_path",
            "metadata_tier0")
    return {k: c.get(k) for k in keys}


def arrival_state(cams: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """{key: {usb_name, busnum, devnum, node, connected_duration}} for re-arrival detection (plan 6.1)."""
    cams = cams if cams is not None else discover_cameras()
    out = {}
    for c in cams:
        ud = P(c["sysfs_dir"])
        out[c["key"]] = {"usb_name": c["usb_name"], "busnum": rd(ud / "busnum"), "devnum": rd(ud / "devnum"),
                         "node": c["node"], "connected_duration_ms": rd_int(ud / "power/connected_duration")}
    return out


def compare_arrivals(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    """Cameras that disappeared, appeared or re-enumerated (devnum changed or connected_duration went down)."""
    ev = []
    for k, b in before.items():
        a = after.get(k)
        if a is None:
            ev.append({"key": k, "event": "disappeared", "before": b})
            continue
        cd_b, cd_a = b.get("connected_duration_ms"), a.get("connected_duration_ms")
        if (b.get("devnum") != a.get("devnum") or b.get("busnum") != a.get("busnum")
                or (cd_b is not None and cd_a is not None and cd_a < cd_b)):
            ev.append({"key": k, "event": "re-arrived", "before": b, "after": a})
        elif b.get("node") != a.get("node"):
            ev.append({"key": k, "event": "node_changed", "before": b, "after": a})
    for k, a in after.items():
        if k not in before:
            ev.append({"key": k, "event": "appeared", "after": a})
    return ev


# ----------------------------------------------------------------------------------------- holders
def holders(nodes: list[str], exclude_pids: set[int] | None = None) -> dict[str, list[dict[str, Any]]]:
    """Processes holding each /dev node open, from /proc/<pid>/fd (only processes this user may inspect; the
    PipeWire / WirePlumber / browser processes of the desktop user are visible to that user)."""
    want = {}
    for n in nodes:
        try:
            st = os.stat(root() + n)
            want[(st.st_dev, st.st_ino)] = n
            want[os.path.realpath(root() + n)] = n
        except OSError:
            continue
    out: dict[str, list[dict[str, Any]]] = {n: [] for n in nodes}
    ex = exclude_pids or set()
    for pd in glob.glob(str(P("/proc")) + "/[0-9]*"):
        pid = int(os.path.basename(pd))
        if pid in ex:
            continue
        try:
            fds = os.listdir(pd + "/fd")
        except OSError:
            continue
        comm = rd(pd + "/comm")
        seen = set()
        for fd in fds:
            try:
                tgt = os.readlink(f"{pd}/fd/{fd}")
            except OSError:
                continue
            n = want.get(tgt) or want.get(root() + tgt)
            if n and n not in seen:
                seen.add(n)
                out[n].append({"pid": pid, "comm": comm, "fd": int(fd)})
    return out


def ancestors_and_self() -> set[int]:
    """This process, its parents (uv, the runner's shell) and its children are not 'other holders'."""
    pids = {os.getpid()}
    p = os.getppid()
    while p and p not in pids and p > 1:
        pids.add(p)
        st = rd(f"/proc/{p}/stat")
        try:
            p = int(st.rsplit(")", 1)[1].split()[1]) if st else 0
        except (IndexError, ValueError):
            break
    return pids


def kernel_version() -> tuple[int, int]:
    r = rd(P("/proc/sys/kernel/osrelease")) or (os.uname().release if hasattr(os, "uname") else "")
    m = re.match(r"(\d+)\.(\d+)", r or "")
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def uvc_params() -> dict[str, str | None]:
    d = P("/sys/module/uvcvideo/parameters")
    if not d.is_dir():
        return {}
    return {p.name: rd(p) for p in sorted(d.iterdir())}


def usbcore_params() -> dict[str, str | None]:
    d = P("/sys/module/usbcore/parameters")
    if not d.is_dir():
        return {}
    return {p.name: rd(p) for p in sorted(d.iterdir()) if p.name in ("quirks", "autosuspend", "usbfs_memory_mb",
                                                                      "old_scheme_first", "use_both_schemes",
                                                                      "authorized_default", "nousb")}
