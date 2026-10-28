# /// script
# requires-python = ">=3.10"
# ///
"""LINUX DRAFT (unverified until run by the user): dump every identity-relevant fact about each UVC camera.

WHAT TO RUN (from the repo root, no sudo needed; user must be able to open /dev/video* - normally the
'video' group or a logind seat ACL):
    uv run --script research/usb_cameras/naming/linux_identity.py --label baseline
  then (a) reboot, (b) unplug+replug every camera into the SAME port, (c) move cameras to DIFFERENT ports,
  running after each step:
    uv run --script research/usb_cameras/naming/linux_identity.py --label after_reboot
    uv run --script research/usb_cameras/naming/linux_identity.py --label after_replug_same_port
    uv run --script research/usb_cameras/naming/linux_identity.py --label after_move_port
  and finally:
    uv run --script research/usb_cameras/naming/identity_diff.py \
        research/usb_cameras/results/linux/$(hostname)/naming/snapshots/{baseline,after_reboot,after_replug_same_port,after_move_port}.json
  (or use naming/linux_stability_workflow.sh which wraps the same steps).

HARDWARE: any UVC cameras. Ideally include two cameras of the same model (with and without serial numbers).
DEPENDENCIES: python3 >= 3.10 via uv; `udevadm` (systemd-udev) for udev properties (optional, recorded if present).
Nothing is streamed: /dev/videoN is opened read-only only for VIDIOC_QUERYCAP.

WRITES results/linux/<hostname>/naming/
    identity_dump.json   all sysfs attributes, udev properties, V4L2 caps, /dev/v4l symlinks, parsed descriptors
    descriptors.json     same structure as the Windows descriptors.json (see naming/README.md)
    snapshots/<label>.json  flat identifiers per camera (input to identity_diff.py)
"""
from __future__ import annotations

import argparse
import datetime as _dt
import fcntl
import glob
import json
import os
import platform
import re
import socket
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import usbdesc  # noqa: E402

# Test hook only: point at a fake tree (naming/test_linux_fake_sysfs.py). Real runs use / .
ROOT = os.environ.get("LINUX_IDENTITY_TEST_ROOT", "")
VIDIOC_QUERYCAP = 0x80685600  # _IOR('V', 0, struct v4l2_capability) (104 bytes)
V4L2_CAP_VIDEO_CAPTURE, V4L2_CAP_META_CAPTURE, V4L2_CAP_STREAMING = 0x1, 0x00800000, 0x04000000
SPEED_MAP = {"1.5": "low", "12": "full", "480": "high", "5000": "super", "10000": "super_plus", "20000": "super_plus"}


def _read(p: Path) -> str | None:
    try:
        return p.read_text(errors="replace").strip()
    except OSError:
        return None


def querycap(node: str) -> dict:
    try:
        fd = os.open(node, os.O_RDONLY | os.O_NONBLOCK)
    except OSError as e:
        return {"error": f"open: {e}"}
    try:
        buf = bytearray(104)
        fcntl.ioctl(fd, VIDIOC_QUERYCAP, buf)
        driver, card, bus_info = (bytes(buf[o:o + n]).split(b"\0")[0].decode(errors="replace")
                                  for o, n in ((0, 16), (16, 32), (48, 32)))
        version, caps, dcaps = struct.unpack_from("<III", buf, 80)
        return dict(driver=driver, card=card, bus_info=bus_info, version=f"{version >> 16}.{version >> 8 & 0xff}.{version & 0xff}",
                    capabilities=f"0x{caps:08x}", device_caps=f"0x{dcaps:08x}",
                    is_video_capture=bool(dcaps & V4L2_CAP_VIDEO_CAPTURE), is_metadata=bool(dcaps & V4L2_CAP_META_CAPTURE))
    except OSError as e:
        return {"error": f"ioctl: {e}"}
    finally:
        os.close(fd)


def udev_props(node: str) -> dict:
    try:
        r = subprocess.run(["udevadm", "info", "--query=property", f"--name={node}"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"error": repr(e)}
    return dict(l.split("=", 1) for l in r.stdout.splitlines() if "=" in l)


def symlink_map(d: str) -> dict:
    out = {}
    for p in glob.glob(os.path.join(d, "*")):
        out.setdefault(os.path.realpath(p), []).append(p)
    return out


def usb_device_dir(video_sysfs: Path) -> Path | None:
    p = (video_sysfs / "device").resolve()   # .../3-1.4/3-1.4:1.0 (interface)
    for cand in (p, *p.parents):
        if (cand / "idVendor").exists():
            return cand
    return None


def pci_controller(usb_dir: Path) -> str | None:
    """Host controller sysfs name: the path element just above the 'usbN' root hub, e.g. '0000:00:14.0' (PCI xHCI)
    or 'fe9c0000.xhci' / 'xhci-hcd.0.auto' (platform controllers on ARM boards)."""
    parts = usb_dir.parts
    for i, part in enumerate(parts):
        if re.fullmatch(r"usb\d+", part) and i > 0:
            return parts[i - 1]
    return None


def collect() -> list[dict]:
    by_id, by_path = symlink_map(ROOT + "/dev/v4l/by-id"), symlink_map(ROOT + "/dev/v4l/by-path")
    devs: dict[str, dict] = {}
    for v in sorted(glob.glob(ROOT + "/sys/class/video4linux/video*"), key=lambda s: int(s.rsplit("video", 1)[1])):
        vs = Path(v)
        ud = usb_device_dir(vs)
        if ud is None:
            continue
        node = f"{ROOT}/dev/{vs.name}"
        entry = dict(node=node, name=_read(vs / "name"), index=_read(vs / "index"),
                     sysfs=str(vs.resolve()), interface=str((vs / "device").resolve().name),
                     querycap=querycap(node), udev=udev_props(node),
                     by_id=by_id.get(os.path.realpath(node), []), by_path=by_path.get(os.path.realpath(node), []))
        d = devs.setdefault(str(ud), dict(usb_dir=str(ud), video_nodes=[]))
        d["video_nodes"].append(entry)
    cams = []
    for ud_s, d in devs.items():
        ud = Path(ud_s)
        attrs = {k: _read(ud / k) for k in ("idVendor", "idProduct", "bcdDevice", "manufacturer", "product", "serial",
                                             "busnum", "devnum", "devpath", "speed", "version", "bMaxPower",
                                             "removable", "port/connect_type", "port/location", "maxchild", "quirks",
                                             "avoid_reset_quirk", "ltm_capable", "tx_lanes", "rx_lanes")}
        d["sysfs_attrs"] = attrs
        d["sysfs_usb_name"] = ud.name
        d["pci_controller"] = pci_controller(ud)
        speed = SPEED_MAP.get(attrs.get("speed") or "", None)
        d["speed"] = speed
        try:
            d["descriptors"] = usbdesc.parse_sysfs_descriptors((ud / "descriptors").read_bytes(), speed)
            d["descriptors_raw_hex"] = (ud / "descriptors").read_bytes().hex()
        except (OSError, ValueError) as e:
            d["descriptors_error"] = repr(e)
        d["udev_usb_device"] = udev_props(f"/dev/bus/usb/{int(attrs['busnum']):03d}/{int(attrs['devnum']):03d}") \
            if attrs.get("busnum") and attrs.get("devnum") else None
        cams.append(d)
    return cams


def flat(d: dict) -> dict:
    a = d["sysfs_attrs"]
    cap = next((n for n in d["video_nodes"] if n["querycap"].get("is_video_capture")), d["video_nodes"][0])
    u = cap["udev"]
    return dict(vid=a.get("idVendor"), pid=a.get("idProduct"), bcdDevice=a.get("bcdDevice"), usb_serial=a.get("serial"),
                usb_manufacturer=a.get("manufacturer"), usb_product=a.get("product"),
                sysfs_usb_name=d["sysfs_usb_name"], pci_controller=d["pci_controller"], devpath=a.get("devpath"),
                busnum=a.get("busnum"), devnum=a.get("devnum"), speed=d.get("speed"),
                video_node=cap["node"], all_video_nodes=[n["node"] for n in d["video_nodes"]],
                by_id=cap["by_id"], by_path=cap["by_path"],
                id_serial=u.get("ID_SERIAL"), id_serial_short=u.get("ID_SERIAL_SHORT"), id_path=u.get("ID_PATH"),
                id_path_tag=u.get("ID_PATH_TAG"), id_path_with_usb_revision=u.get("ID_PATH_WITH_USB_REVISION"),
                udev_devpath=u.get("DEVPATH"), v4l2_card=cap["querycap"].get("card"),
                v4l2_bus_info=cap["querycap"].get("bus_info"), port_connect_type=a.get("port/connect_type"))


def collect_flat() -> list[dict]:
    return [flat(d) for d in collect()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default=None)
    ap.add_argument("--out-dir", type=Path, default=None)
    a = ap.parse_args()
    if not sys.platform.startswith("linux"):
        print("this script is for Linux", file=sys.stderr)
        return 2
    out_dir = a.out_dir or HERE.parent / "results" / "linux" / socket.gethostname() / "naming"
    out_dir.mkdir(parents=True, exist_ok=True)
    started = _dt.datetime.now(_dt.timezone.utc).isoformat()
    cams = collect()
    if not cams:
        print("no USB video4linux devices found (is uvcvideo loaded? are cameras plugged in?)", file=sys.stderr)
    flats = [flat(c) for c in cams]
    try:
        import camera_identity
        for f in flats:
            f["port_path"] = camera_identity.port_path_from_linux(f["pci_controller"], f["sysfs_usb_name"])
        for f in flats:
            f["camera_key"] = camera_identity.derive(f, flats)[0]
    except ImportError:
        pass
    base = dict(platform="linux", hostname=socket.gethostname(), utc_started=started, command=" ".join(sys.argv),
                environment=dict(os=platform.platform(), kernel=platform.release(), python=sys.version.split()[0],
                                 uvcvideo_quirks=_read(Path("/sys/module/uvcvideo/parameters/quirks")),
                                 udevadm=subprocess.run(["sh", "-c", "udevadm --version"], capture_output=True, text=True).stdout.strip()))
    (out_dir / "identity_dump.json").write_text(json.dumps(dict(test="naming.linux_identity_dump", **base, cameras=cams), indent=1))
    desc = []
    for c, f in zip(cams, flats):
        dd = c.get("descriptors") or {}
        cfg = (dd.get("configurations") or [None])[0]
        desc.append(dict(camera=dict(vid=f["vid"], pid=f["pid"], product=f["usb_product"], serial=f["usb_serial"],
                                     sysfs_usb_name=f["sysfs_usb_name"]), speed=c.get("speed"), device=dd.get("device"),
                         configuration_summary={k: v for k, v in cfg.items() if k not in ("interfaces", "uvc")} if cfg else None,
                         uvc=cfg.get("uvc") if cfg else None, interfaces=cfg.get("interfaces") if cfg else None,
                         raw_hex=dict(sysfs_descriptors=c.get("descriptors_raw_hex")), error=c.get("descriptors_error")))
    (out_dir / "descriptors.json").write_text(json.dumps(dict(test="naming.descriptors", **base, cameras=desc), indent=1))
    if a.label:
        (out_dir / "snapshots").mkdir(exist_ok=True)
        (out_dir / "snapshots" / f"{a.label}.json").write_text(
            json.dumps(dict(test="naming.snapshot", label=a.label, **base, cameras=flats), indent=1))
    for f in flats:
        print(f"{f['vid']}:{f['pid']} {f['usb_product']!r} serial={f['usb_serial']!r} node={f['video_node']} "
              f"by_id={f['by_id']} by_path={f['by_path']} key={f.get('camera_key')}")
    print("wrote", out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
