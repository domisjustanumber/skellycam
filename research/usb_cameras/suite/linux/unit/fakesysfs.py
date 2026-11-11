"""Build a FAKE Linux sysfs/devfs tree that mimics Gerald's USB layout (no cameras, no root needed).

Modelled on research/usb_cameras/naming/test_linux_fake_sysfs.py, extended to the topology the suite maps:

    0000:00:14.0  Intel 8086:7A60 xHCI   usb1 (480, 16 ports)  usb2 (10000, 9 ports; peers usb1-port1..9)
        usb1-port7   C930e 046d:0843 (no serial)
        usb1-port10  internal hub 05e3:0608 (hardwired), 4 empty ports
        usb1-port13  Genesys 05e3:0610 (USB 2.0 half of the GL3523 dock, location shared with usb4-port2)
            1-13.1   inner Genesys 05e3:0610
                1-13.1.2  generic USB Camera 4c4a:4a55 (no serial)
                1-13.1.4  C922 046d:085c serial C922SN01
        usb1-port9 / usb2-port9: USB-C (connector symlinks)
        usb1-port1: physical_location back/lower/left (trusted);  usb1-port2: all-zero _PLD (must be ignored)
    0000:3a:00.0  Intel 8086:1138 Thunderbolt xHCI behind PCIe bridges   usb3 (480, 2)  usb4 (10000, 2)
        usb4-port1 (USB-C, location = usb1-port12), usb4-port2 (USB-C, location = usb1-port13)
        4-2   Genesys 05e3:0625 SuperSpeed half of the dock -> 4-2.4 Razer Kiyo Pro 1532:0e05 at 5000 (quirks 0x400)

Descriptor bytes are the real ones from Windows (unit/fixtures/gerald_descriptors.json). ``streaming`` sets a
camera's VS interface bAlternateSetting (as uvcvideo would while it streams). /dev nodes are plain files, so any
ioctl on them fails (that path is exercised too).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LINUX_DIR = HERE.parent
sys.path.insert(0, str(LINUX_DIR / "linuxlib"))
import usbdesc  # noqa: E402

DESC = json.loads((HERE / "fixtures" / "gerald_descriptors.json").read_text(encoding="utf-8"))["cameras"]
PCH = "sys/devices/pci0000:00/0000:00:14.0"
TB = "sys/devices/pci0000:00/0000:00:1c.4/0000:03:00.0/0000:04:02.0/0000:3a:00.0"


def _w(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text + "\n")


def _ln(target: Path, link: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(os.path.relpath(target, link.parent), link)


def _controller(root: Path, rel: str, vid: str, did: str) -> Path:
    c = root / rel
    _w(c / "vendor", f"0x{vid}")
    _w(c / "device", f"0x{did}")
    _w(c / "class", "0x0c0330")
    drv = root / "sys/bus/pci/drivers/xhci_hcd"
    drv.mkdir(parents=True, exist_ok=True)
    _ln(drv, c / "driver")
    return c


def _roothub(root: Path, cdir: Path, bus: int, speed: str, maxchild: int, version: str) -> Path:
    rh = cdir / f"usb{bus}"
    for k, v in dict(busnum=str(bus), devnum="1", speed=speed, maxchild=str(maxchild), version=f" {version}",
                     product="xHCI Host Controller", idVendor="1d6b",
                     idProduct="0002" if speed == "480" else "0003").items():
        _w(rh / k, v)
    _ln(rh, root / f"sys/bus/usb/devices/usb{bus}")
    return rh


def _port(hub_if: Path, name: str, connect_type: str = "hotplug", location: str | None = None,
          acpi: str | None = None, pld: dict | None = None, typec: bool = False) -> Path:
    p = hub_if / name
    _w(p / "connect_type", connect_type)
    _w(p / "over_current_count", "0")
    _w(p / "quirks", "0x0")
    if location:
        _w(p / "location", location)
    if acpi:
        _w(p / "firmware_node" / "path", acpi)
    if pld:
        for k, v in pld.items():
            _w(p / "physical_location" / k, v)
    if typec:
        cdir = hub_if.parents[3] / "typec_fake" / name
        cdir.mkdir(parents=True, exist_ok=True)
        _ln(cdir, p / "connector")
    return p


def _device(root: Path, parent_dir: Path, port_dir: Path, name: str, attrs: dict, desc_key: str | None = None,
            alt: dict | None = None, maxchild: int = 0) -> Path:
    d = parent_dir / name
    base = dict(busnum=name.split("-")[0], devpath=name.split("-", 1)[1], maxchild=str(maxchild),
                bDeviceClass="09" if maxchild else "ef", version=" 2.10", removable="removable")
    base.update(attrs)
    for k, v in base.items():
        if v is not None:
            _w(d / k, v)
    _w(d / "power" / "control", "auto")
    _w(d / "power" / "runtime_status", "active")
    _w(d / "power" / "autosuspend_delay_ms", "2000")
    _w(d / "power" / "connected_duration", "123456")
    _ln(d, port_dir / "device")
    _ln(port_dir, d / "port")
    _ln(d, root / f"sys/bus/usb/devices/{name}")
    if desc_key:
        ent = DESC[desc_key]
        raw = bytes.fromhex(ent["device_hex"]) + bytes.fromhex(ent["configuration_hex"])
        (d / "descriptors").write_bytes(raw)
        speed = {"480": "high", "5000": "super"}.get(base.get("speed", "480"), "high")
        cfg = usbdesc.parse_sysfs_descriptors(raw, speed)["configurations"][0]
        nums = sorted({i["bInterfaceNumber"] for i in cfg["interfaces"]})
        for n in nums:
            i0 = next(i for i in cfg["interfaces"] if i["bInterfaceNumber"] == n and i["bAlternateSetting"] == 0)
            itf = d / f"{name}:1.{n}"
            a = (alt or {}).get(n, 0)
            for k, v in dict(bInterfaceNumber=f"{n:02x}", bAlternateSetting=f"{a:2d}",
                             bInterfaceClass=f"{i0['bInterfaceClass']:02x}",
                             bInterfaceSubClass=f"{i0['bInterfaceSubClass']:02x}",
                             bNumEndpoints=f"{i0['bNumEndpoints']:02x}").items():
                _w(itf / k, v)
    elif maxchild:
        itf = d / f"{name}:1.0"
        for k, v in dict(bInterfaceNumber="00", bAlternateSetting=" 0", bInterfaceClass="09",
                         bInterfaceSubClass="00").items():
            _w(itf / k, v)
    return d


def _video(root: Path, dev: Path, name: str, first_node: int, product: str, by_id: str, by_path: str) -> None:
    itf = dev / f"{name}:1.0"
    drv = root / "sys/bus/usb/drivers/uvcvideo"
    drv.mkdir(parents=True, exist_ok=True)
    if not os.path.lexists(itf / "driver"):
        _ln(drv, itf / "driver")
    for idx in (0, 1):
        n = first_node + idx
        v = itf / "video4linux" / f"video{n}"
        _w(v / "name", product)
        _w(v / "index", str(idx))
        _w(v / "dev", f"81:{n}")
        _ln(itf, v / "device")
        _ln(v, root / f"sys/class/video4linux/video{n}")
        node = root / f"dev/video{n}"
        _w(node, "")
        _ln(node, root / f"dev/v4l/by-path/{by_path}-video-index{idx}")
        _ln(node, root / f"dev/v4l/by-id/{by_id}-video-index{idx}")


def build(root: Path, streaming: dict[str, int] | None = None, kiyo_quirks: str = "0x400") -> dict:
    """Create the tree under ``root``. ``streaming`` = {'c922'|'generic'|'c930e'|'kiyo': alt} sets that camera's
    VS interface (interface 1) alt setting. Returns a dict of handy paths."""
    st = streaming or {}
    root = Path(root)
    for d in ("sys/class/video4linux", "dev/v4l/by-id", "dev/v4l/by-path", "sys/bus/usb/devices"):
        (root / d).mkdir(parents=True, exist_ok=True)
    for k, v in dict(quirks="-1", nodrop="Y", hwtimestamps="0", clock="CLOCK_MONOTONIC", timeout="5000",
                     trace="0").items():
        _w(root / "sys/module/uvcvideo/parameters" / k, v)
    _w(root / "sys/module/usbcore/parameters/quirks", "")
    _w(root / "sys/module/usbcore/parameters/autosuspend", "2")

    pch = _controller(root, PCH, "8086", "7a60")
    tb = _controller(root, TB, "8086", "1138")
    u1 = _roothub(root, pch, 1, "480", 16, "2.00")
    u2 = _roothub(root, pch, 2, "10000", 9, "3.20")
    u3 = _roothub(root, tb, 3, "480", 2, "2.00")
    u4 = _roothub(root, tb, 4, "10000", 2, "3.10")
    u1if, u2if, u3if, u4if = (u1 / "1-0:1.0", u2 / "2-0:1.0", u3 / "3-0:1.0", u4 / "4-0:1.0")
    ports = {}
    for k in range(1, 17):
        ct = "hardwired" if k in (10, 11, 14) else "hotplug"
        loc = {12: "0x80000112", 13: "0x80000113"}.get(k)
        pld = None
        if k == 1:
            pld = dict(panel="back", vertical_position="lower", horizontal_position="left", dock="no", lid="no")
        elif k == 2:
            pld = dict(panel="top", vertical_position="upper", horizontal_position="left", dock="no", lid="no")
        ports[f"usb1-port{k}"] = _port(u1if, f"usb1-port{k}", ct, loc, f"\\_SB_.PC00.XHCI.RHUB.HS{k:02d}", pld,
                                       typec=k == 9)
    for k in range(1, 10):
        ports[f"usb2-port{k}"] = _port(u2if, f"usb2-port{k}", "hotplug", None, f"\\_SB_.PC00.XHCI.RHUB.SS{k:02d}",
                                       typec=k == 9)
        _ln(ports[f"usb2-port{k}"], ports[f"usb1-port{k}"] / "peer")
        _ln(ports[f"usb1-port{k}"], ports[f"usb2-port{k}"] / "peer")
    for k in (1, 2):
        ports[f"usb3-port{k}"] = _port(u3if, f"usb3-port{k}", "not used")
        ports[f"usb4-port{k}"] = _port(u4if, f"usb4-port{k}", "hotplug", {1: "0x80000112", 2: "0x80000113"}[k],
                                       f"\\_SB_.PC00.TXHC.RHUB.SS0{k + 2}", typec=True)
        _ln(ports[f"usb4-port{k}"], ports[f"usb3-port{k}"] / "peer")
        _ln(ports[f"usb3-port{k}"], ports[f"usb4-port{k}"] / "peer")

    hs = dict(speed="480")
    # C930e on root port 7
    c930e = _device(root, u1, ports["usb1-port7"], "1-7",
                    dict(idVendor="046d", idProduct="0843", bcdDevice="0013", product="Logitech Webcam C930e",
                         devnum="5", **hs), "046d:0843", {1: st.get("c930e", 0)})
    _video(root, c930e, "1-7", 4, "Logitech Webcam C930e", "usb-046d_Logitech_Webcam_C930e",
           "pci-0000:00:14.0-usb-0:7:1.0")
    # internal hub on root port 10 with four empty ports
    h10 = _device(root, u1, ports["usb1-port10"], "1-10",
                  dict(idVendor="05e3", idProduct="0608", bcdDevice="6060", product="USB2.0 Hub", devnum="3",
                       bDeviceProtocol="01", **hs), maxchild=4)
    for k in range(1, 5):
        _port(h10 / "1-10:1.0", f"1-10-port{k}", "unknown")
    # dock: outer Genesys hub on root port 13 -> inner hub -> generic + C922
    h13 = _device(root, u1, ports["usb1-port13"], "1-13",
                  dict(idVendor="05e3", idProduct="0610", bcdDevice="6070", product="USB2.1 Hub", devnum="7",
                       bDeviceProtocol="02", **hs), maxchild=4)
    p13 = {k: _port(h13 / "1-13:1.0", f"1-13-port{k}", "unknown") for k in range(1, 5)}
    h131 = _device(root, h13, p13[1], "1-13.1",
                   dict(idVendor="05e3", idProduct="0610", bcdDevice="6070", product="USB2.1 Hub", devnum="8",
                        bDeviceProtocol="02", **hs), maxchild=4)
    p131 = {k: _port(h131 / "1-13.1:1.0", f"1-13.1-port{k}", "unknown") for k in range(1, 5)}
    gen = _device(root, h131, p131[2], "1-13.1.2",
                  dict(idVendor="4c4a", idProduct="4a55", bcdDevice="0100", product="USB Camera",
                       manufacturer="Jieli Technology", devnum="9", **hs), "4c4a:4a55", {1: st.get("generic", 0)})
    _video(root, gen, "1-13.1.2", 2, "USB Camera", "usb-Jieli_Technology_USB_Camera",
           "pci-0000:00:14.0-usb-0:13.1.2:1.0")
    c922 = _device(root, h131, p131[4], "1-13.1.4",
                   dict(idVendor="046d", idProduct="085c", bcdDevice="0016", product="C922 Pro Stream Webcam",
                        serial="C922SN01", devnum="10", **hs), "046d:085c", {1: st.get("c922", 0)})
    _video(root, c922, "1-13.1.4", 0, "C922 Pro Stream Webcam", "usb-046d_C922_Pro_Stream_Webcam_C922SN01",
           "pci-0000:00:14.0-usb-0:13.1.4:1.0")
    # SuperSpeed half of the dock on the Thunderbolt controller, Kiyo Pro behind it
    h42 = _device(root, u4, ports["usb4-port2"], "4-2",
                  dict(idVendor="05e3", idProduct="0625", bcdDevice="0606", product="USB3.2 Hub", devnum="2",
                       speed="5000", version=" 3.20", bDeviceProtocol="03"), maxchild=4)
    p42 = {k: _port(h42 / "4-2:1.0", f"4-2-port{k}", "unknown") for k in range(1, 5)}
    kiyo = _device(root, h42, p42[4], "4-2.4",
                   dict(idVendor="1532", idProduct="0e05", bcdDevice="0819", product="Razer Kiyo Pro", devnum="3",
                        speed="5000", version=" 3.20", quirks=kiyo_quirks), "1532:0e05",
                   {1: st.get("kiyo", 0)})
    _w(kiyo / "power" / "usb3_hardware_lpm_u1", "disabled")
    _w(kiyo / "power" / "usb3_hardware_lpm_u2", "disabled")
    _video(root, kiyo, "4-2.4", 6, "Razer Kiyo Pro", "usb-Razer_Inc_Razer_Kiyo_Pro",
           "pci-0000:3a:00.0-usb-0:2.4:1.0")
    return {"root": root, "c922": c922, "generic": gen, "c930e": c930e, "kiyo": kiyo}


if __name__ == "__main__":  # manual: build a tree to inspect
    import tempfile
    t = Path(sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="fakesysfs_"))
    build(t)
    print(t)
