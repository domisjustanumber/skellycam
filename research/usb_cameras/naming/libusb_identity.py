# /// script
# requires-python = ">=3.10"
# dependencies = ["libusb1==3.4.0"]
# ///
"""What identity does libusb expose for each UVC camera? (goal 4, libusb path; any OS)

    uv run --script research/usb_cameras/tools/camlock.py -- \
        uv run --script research/usb_cameras/naming/libusb_identity.py [--no-open] [--compare SNAPSHOT.json] --out-dir DIR

For every device with a Video-class interface: bus number, libusb_get_port_numbers() chain (no open needed),
device address, speed, the string-descriptor INDICES from the cached device descriptor (no open needed), then
(unless --no-open) libusb_open + iManufacturer/iProduct/iSerialNumber text and the open error if it fails.
--compare: a phase-1 Windows naming snapshot (naming/win_identity_dump.py --label ...); each libusb device is
matched by VID:PID + port chain against snapshot `hub_port_chain` (the part after ':') and the result reports which
fields agree. Also derives the camera_identity.py-style key "<vid>:<pid>:sn=<serial>" or
"<vid>:<pid>:port=<bus>/<p1.p2...>" from libusb data alone.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import importlib.metadata as md
import json
import platform
import socket
import sys
from pathlib import Path

import usb1

PLAT = {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}.get(platform.system(), platform.system().lower())
SPEED = {0: "unknown", 1: "low", 2: "full", 3: "high", 4: "super", 5: "super_plus"}


def is_uvc(dev: usb1.USBDevice) -> bool:
    try:
        return any(s.getClass() == 0x0E for s in dev.iterSettings())
    except usb1.USBError:
        return False


def collect(ctx: usb1.USBContext, try_open: bool, exclude: set[str] | None = None) -> list[dict]:
    out = []
    for dev in ctx.getDeviceIterator(skip_on_error=True):
        vp = f"{dev.getVendorID():04x}:{dev.getProductID():04x}"
        if exclude and vp in exclude:
            # never libusb_open / string-read an excluded device; only libusb's own enumeration touched it
            out.append({"vid_pid": vp, "excluded": True, "port_path": f"{dev.getBusNumber()}-"
                        + ".".join(map(str, dev.getPortNumberList() or []))})
            continue
        if not is_uvc(dev):
            continue
        ports = list(dev.getPortNumberList() or [])
        c = {"vid": f"{dev.getVendorID():04x}", "pid": f"{dev.getProductID():04x}", "bcdDevice": f"{dev.getbcdDevice():04x}",
             "bus_number": dev.getBusNumber(), "port_numbers": ports, "port_chain": ".".join(map(str, ports)),
             "port_path": f"{dev.getBusNumber()}-{'.'.join(map(str, ports))}", "device_address": dev.getDeviceAddress(),
             "speed": SPEED.get(dev.getDeviceSpeed(), dev.getDeviceSpeed()),
             "iManufacturer_index": dev.getManufacturerDescriptor(), "iProduct_index": dev.getProductDescriptor(),
             "iSerialNumber_index": dev.getSerialNumberDescriptor()}
        if try_open:
            try:
                h = dev.open()
            except usb1.USBError as e:
                c["open"] = repr(e)
            else:
                try:
                    c["open"] = "OK"
                    for k, idx in (("manufacturer", c["iManufacturer_index"]), ("product", c["iProduct_index"]),
                                   ("serial", c["iSerialNumber_index"])):
                        if not idx:
                            c[k] = None
                            continue
                        try:
                            c[k] = h.getASCIIStringDescriptor(idx)
                        except usb1.USBError as e:
                            c[k] = repr(e)
                    try:  # second concurrent open of the same device (pyuvc/libuvc does this internally)
                        h2 = dev.open()
                        c["second_open_while_open"] = "OK"
                        h2.close()
                    except usb1.USBError as e:
                        c["second_open_while_open"] = repr(e)
                finally:
                    h.close()
        serial = c.get("serial")
        c["key_libusb_only"] = (f"{c['vid']}:{c['pid']}:sn={serial}" if isinstance(serial, str) and serial and not serial.startswith("USBError")
                                else f"{c['vid']}:{c['pid']}:port=bus{c['bus_number']}/{c['port_chain']}")
        out.append(c)
    return out


def compare(cams: list[dict], snap_path: Path) -> list[dict]:
    snap = json.loads(snap_path.read_text())
    rows = [x.get("snapshot", x) for x in snap.get("cameras", snap if isinstance(snap, list) else [])]
    res = []
    for c in cams:
        m = next((r for r in rows if r.get("vid") == c["vid"] and r.get("pid") == c["pid"]
                  and str(r.get("hub_port_chain", "")).rsplit(":", 1)[-1] == c["port_chain"]), None)
        if m is None:
            res.append({"libusb": c["port_path"], "vid_pid": f"{c['vid']}:{c['pid']}", "match": None})
            continue
        res.append({"vid_pid": f"{c['vid']}:{c['pid']}", "libusb_port_path": c["port_path"],
                    "snapshot_hub_port_chain": m.get("hub_port_chain"), "snapshot_location_paths": m.get("location_paths"),
                    "port_chain_equal": True,
                    "libusb_address": c["device_address"], "snapshot_address": m.get("usb_device_address"),
                    "address_equal": c["device_address"] == m.get("usb_device_address"),
                    "libusb_serial": c.get("serial"), "snapshot_serial": m.get("usb_serial"),
                    "serial_equal": c.get("serial") == m.get("usb_serial") if "serial" in c else "not opened",
                    "libusb_product": c.get("product"), "snapshot_product": m.get("usb_product"),
                    "snapshot_camera_key": m.get("camera_key"), "snapshot_composite_instance_id": m.get("composite_instance_id")})
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--compare", type=Path)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--exclude-vidpid", action="append", default=[],
                    help="vvvv:pppp (repeatable): do not open or string-read these devices")
    a = ap.parse_args()
    excl = {x.strip().lower() for v in a.exclude_vidpid for x in v.split(",") if x.strip()}
    a.out_dir.mkdir(parents=True, exist_ok=True)
    res = {"test": "libusb_identity", "platform": PLAT, "hostname": socket.gethostname(),
           "utc_started": _dt.datetime.now(_dt.timezone.utc).isoformat(), "command": " ".join(sys.argv),
           "environment": {"python": sys.version, "os": platform.platform(), "libusb1": md.version("libusb1"),
                           "libusb": ".".join(map(str, tuple(usb1.getVersion())[:4]))}}
    with usb1.USBContext() as ctx:
        found = collect(ctx, not a.no_open, excl)
    res["cameras"] = [c for c in found if not c.get("excluded")]
    if excl:
        res["excluded_vidpid"] = sorted(excl)
        res["excluded_devices_seen"] = [c for c in found if c.get("excluded")]
    if a.compare:
        res["compare_snapshot"] = str(a.compare)
        res["comparison"] = compare(res["cameras"], a.compare)
    (a.out_dir / "result.json").write_text(json.dumps(res, indent=2, default=str))
    print(json.dumps(res, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
