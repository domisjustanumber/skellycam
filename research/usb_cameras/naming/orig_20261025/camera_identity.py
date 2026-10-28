# /// script
# requires-python = ">=3.10"
# ///
"""Stable, cross-platform USB camera identity keys.

    uv run --script research/usb_cameras/naming/camera_identity.py            # print cameras + keys as JSON
    uv run --script research/usb_cameras/naming/camera_identity.py --selftest # scheme unit tests (any OS)

Status: Windows implementation tested on the investigation machine; Linux / macOS paths are DRAFTS
(they call naming/linux_identity.py / naming/macos_identity.py, which have not been run yet).

Scheme (see naming/README.md for the evidence behind each rule):
  1. key = "<vid>:<pid>:sn=<serial>"   when the USB iSerialNumber string is *usable*:
        - present and non-empty,
        - every char in 0x21..0x7f and no ',' (the rule Windows applies before using a serial in the instance id;
          udev's usb_id builtin applies nearly the same rule - otherwise the OS ignores the serial too),
        - not a known placeholder (all-zero, '0123456789', ...; see PLACEHOLDER_SERIALS) and not one repeated char,
        - unique among the currently connected cameras with the same VID:PID.
     This key survives reboots, replugging and moving the camera to another port/hub/computer.
  2. otherwise key = "<vid>:<pid>:port=<controller>/<p1.p2...>"  -- the physical port path:
        windows: DEVPKEY_Device_LocationPaths[0] split at USBROOT(n): "PCIROOT(0)#PCI(1400)#USBROOT(0)" + "13.1.4"
        linux:   PCI address of the host controller + kernel port chain (sysfs name "3-13.1.4" -> "13.1.4");
                 the bus number "3" is dropped because it is not stable across boots (systemd path_id does the same)
        macos:   IOKit locationID: bus byte + port nibbles, e.g. 0x14130000 -> "bus14/1.3"
     This key survives reboots and replugging into the SAME port; it changes when the camera moves port or the
     hub chain changes. Two identical serial-less cameras can only be told apart this way.
  The key never uses: OS instance ids with generated parts, MF/DirectShow/OpenCV indices, friendly names,
  USB device addresses, Linux /dev/videoN numbers, ContainerIds of serial-less devices - all measured or
  documented to change.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

PLACEHOLDER_SERIALS = {
    "0", "00", "000", "0000", "00000000", "000000000000", "0000000000000000", "1", "01", "0001",
    "0123456789", "123456789", "1234567890", "12345678", "123456", "0123456789abcdef", "0123456789ABCDEF",
    "sn0001", "sn12345678", "none", "null", "default", "serial", "unknown", "n/a", "na", "123", "200901010001",
}


def serial_is_valid_for_os(serial: str | None) -> bool:
    if not serial:
        return False
    # Windows rejects a serial containing chars <= 0x20, > 0x7F or ',' (Microsoft windows-music-dev blog,
    # 2023-06-06); udev usb_id rejects < 0x20, > 0x7f, ','. We apply the stricter (Windows) rule everywhere so a
    # camera gets the same key kind on every OS.
    return all(0x20 < ord(c) <= 0x7F and c != "," for c in serial)


def serial_is_usable(serial: str | None) -> tuple[bool, str]:
    if not serial or not serial.strip():
        return False, "no serial"
    if not serial_is_valid_for_os(serial):
        return False, "invalid characters (OS ignores it)"
    s = serial.strip()
    if s.lower() in PLACEHOLDER_SERIALS:
        return False, "placeholder serial"
    if len(set(s)) == 1:
        return False, "single repeated character"
    return True, "ok"


@dataclass
class CameraIdentity:
    key: str
    key_kind: str                 # "serial" | "port"
    vid: str
    pid: str
    serial: str | None
    serial_usable: bool
    serial_reason: str
    product: str | None
    port_path: str | None         # "<controller>/<ports>" (see module docstring)
    native: dict = field(default_factory=dict)   # platform handles: how to open this camera with each API


def port_path_from_windows_location_paths(loc: str | None) -> str | None:
    """'PCIROOT(0)#PCI(1400)#USBROOT(0)#USB(13)#USB(1)#USB(4)' -> 'PCIROOT(0)#PCI(1400)#USBROOT(0)/13.1.4'."""
    if not loc:
        return None
    m = re.match(r"^(.*?#USBROOT\(\d+\))((?:#USB\(\d+\))+)", loc)
    if not m:
        return loc
    ports = re.findall(r"#USB\((\d+)\)", m.group(2))
    return f"{m.group(1)}/{'.'.join(ports)}"


def port_path_from_linux(pci_controller: str | None, kernel_name: str | None) -> str | None:
    """('0000:00:14.0', '3-13.1.4') -> 'pci-0000:00:14.0/13.1.4'."""
    if not kernel_name or "-" not in kernel_name:
        return None
    return f"pci-{pci_controller or '?'}/{kernel_name.split('-', 1)[1]}"


def port_path_from_mac_location_id(location_id: int | None) -> str | None:
    """IOKit locationID 0xBBPPPPPP: top byte = bus, then one nibble per hub tier (port number), 0 terminates."""
    if location_id is None:
        return None
    bus = (location_id >> 24) & 0xFF
    ports = []
    for shift in range(20, -1, -4):
        n = (location_id >> shift) & 0xF
        if n == 0:
            break
        ports.append(str(n))
    return f"bus{bus:02x}/{'.'.join(ports)}"


def derive(flat: dict, peers: list[dict] | None) -> tuple[str, str, bool, str]:
    """flat needs vid, pid, usb_serial, port_path. peers = all cameras currently connected (incl. this one)."""
    vid, pid, serial = (flat.get("vid") or "????").lower(), (flat.get("pid") or "????").lower(), flat.get("usb_serial")
    ok, reason = serial_is_usable(serial)
    if ok and peers:
        same = [p for p in peers if (p.get("vid") or "").lower() == vid and (p.get("pid") or "").lower() == pid
                and (p.get("usb_serial") or "") == serial]
        if len(same) > 1:
            ok, reason = False, f"serial shared by {len(same)} connected cameras"
    if ok:
        return f"{vid}:{pid}:sn={serial}", "serial", True, reason
    return f"{vid}:{pid}:port={flat.get('port_path')}", "port", False, reason


# ---------------------------------------------------------------- windows (tested)
def windows_key_for_flat(flat: dict, flats: list[dict] | None) -> str:
    """Used by win_identity_dump.py / win_restart_test.py snapshots."""
    f = dict(flat, port_path=port_path_from_windows_location_paths(flat.get("location_paths")))
    peers = [dict(p, port_path=None) for p in flats] if flats else None
    return derive(f, peers)[0]


def _list_windows() -> list[CameraIdentity]:
    import win_identity_dump as wid
    cams = wid.collect(read_descriptors=True)
    flats = [wid.flat_identity(c) for c in cams]
    for f in flats:
        f["port_path"] = port_path_from_windows_location_paths(f.get("location_paths"))
    out = []
    for c, f in zip(cams, flats):
        key, kind, usable, reason = derive(f, flats)
        out.append(CameraIdentity(
            key=key, key_kind=kind, vid=f["vid"], pid=f["pid"], serial=f["usb_serial"], serial_usable=usable,
            serial_reason=reason, product=f["usb_product"], port_path=f["port_path"],
            native=dict(composite_instance_id=f["composite_instance_id"],
                        video_function_instance_id=f["video_function_instance_id"],
                        # == MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_SYMBOLIC_LINK and cv2_enumerate_cameras(CAP_MSMF).path
                        msmf_symbolic_link=f["ks_video_camera_symlink"],
                        # == DirectShow DevicePath and cv2_enumerate_cameras(CAP_DSHOW).path
                        dshow_device_path=f["ks_capture_symlink"],
                        ffmpeg_dshow_alternative_name=("@device_pnp_" + f["ks_capture_symlink"]) if f["ks_capture_symlink"] else None,
                        container_id=f["container_id"], friendly_name=f["friendly_name"])))
    return out


# ---------------------------------------------------------------- linux / macos (drafts)
def _list_linux() -> list[CameraIdentity]:
    import linux_identity
    flats = linux_identity.collect_flat()
    out = []
    for f in flats:
        f["port_path"] = port_path_from_linux(f.get("pci_controller"), f.get("sysfs_usb_name"))
    for f in flats:
        key, kind, usable, reason = derive(f, flats)
        out.append(CameraIdentity(key=key, key_kind=kind, vid=f["vid"], pid=f["pid"], serial=f.get("usb_serial"),
                                  serial_usable=usable, serial_reason=reason, product=f.get("usb_product"),
                                  port_path=f["port_path"],
                                  native={k: f.get(k) for k in ("video_node", "by_id", "by_path", "id_path", "v4l2_bus_info")}))
    return out


def _list_macos() -> list[CameraIdentity]:
    import macos_identity
    flats = macos_identity.collect_flat()
    for f in flats:
        f["port_path"] = port_path_from_mac_location_id(f.get("location_id"))
    out = []
    for f in flats:
        key, kind, usable, reason = derive(f, flats)
        out.append(CameraIdentity(key=key, key_kind=kind, vid=f["vid"], pid=f["pid"], serial=f.get("usb_serial"),
                                  serial_usable=usable, serial_reason=reason, product=f.get("usb_product"),
                                  port_path=f["port_path"],
                                  native={k: f.get(k) for k in ("avf_unique_id", "avf_model_id", "avf_localized_name",
                                                                "location_id_hex")}))
    return out


def list_cameras() -> list[CameraIdentity]:
    if sys.platform == "win32":
        return _list_windows()
    if sys.platform.startswith("linux"):
        return _list_linux()
    if sys.platform == "darwin":
        return _list_macos()
    raise NotImplementedError(sys.platform)


# ---------------------------------------------------------------- self test
def _selftest() -> int:
    assert port_path_from_windows_location_paths("PCIROOT(0)#PCI(1400)#USBROOT(0)#USB(13)#USB(1)#USB(4)") == \
        "PCIROOT(0)#PCI(1400)#USBROOT(0)/13.1.4"
    assert port_path_from_windows_location_paths(
        "PCIROOT(0)#PCI(1C04)#PCI(0000)#PCI(0200)#PCI(0000)#USBROOT(0)#USB(4)#USB(4)") == \
        "PCIROOT(0)#PCI(1C04)#PCI(0000)#PCI(0200)#PCI(0000)#USBROOT(0)/4.4"
    assert port_path_from_linux("0000:00:14.0", "3-13.1.4") == "pci-0000:00:14.0/13.1.4"
    assert port_path_from_mac_location_id(0x14130000) == "bus14/1.3"
    assert port_path_from_mac_location_id(0x00100000) == "bus00/1"
    a = dict(vid="046d", pid="085c", usb_serial="B76395EF", port_path="x/1")
    b = dict(vid="046d", pid="085c", usb_serial="B76395EF", port_path="x/2")
    assert derive(a, [a])[1] == "serial"
    assert derive(a, [a, b])[1] == "port"                       # duplicate serial -> port
    assert derive(dict(a, usb_serial="0123456789"), None)[1] == "port"
    assert derive(dict(a, usb_serial="AB,CD"), None)[1] == "port"
    assert derive(dict(a, usb_serial="AB CD"), None)[1] == "port"
    assert derive(dict(a, usb_serial=None), None)[0] == "046d:085c:port=x/1"
    print("camera_identity selftest OK")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    print(json.dumps([asdict(c) for c in list_cameras()], indent=1))
