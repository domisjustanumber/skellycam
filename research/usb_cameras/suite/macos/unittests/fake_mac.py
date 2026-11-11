"""Synthetic macOS data for the unit tests (any OS; no device access).

Trees are modelled on the excerpts quoted in topology_macos.md (M1 Pro gist: usb-drd1-port-hs@01100000 class
AppleUSB20XHCITypeCPort, "port" = <01000000>; IOUSBHostDevice "USBSpeed" 3 / "Device Speed" 2 for an HS camera;
a USB 3 hub appearing twice; restorekit's AppleHPM port-location labels; the macOS 26 "usb-port-number" key) and
on naming/test_macos_fake_ioreg.py. They show plumbing only, not real macOS behaviour.
"""
from __future__ import annotations

import json
import plistlib
import struct
from pathlib import Path

_ID = [1000]


def _rid() -> int:
    _ID[0] += 1
    return _ID[0]


def le32(n: int) -> bytes:
    return struct.pack("<I", n)


def iface(num: int, cls: int, sub: int, loc: int, vid: int, pid: int, alt: int = 0) -> dict:
    return {"IOObjectClass": "IOUSBHostInterface", "IORegistryEntryName": f"IOUSBHostInterface@{num}",
            "IORegistryEntryID": _rid(), "bInterfaceNumber": num, "bInterfaceClass": cls, "bInterfaceSubClass": sub,
            "bAlternateSetting": alt, "locationID": loc, "idVendor": vid, "idProduct": pid,
            "IORegistryEntryChildren": [{"IOObjectClass": "AppleUSBHostFrameworkInterfaceClient",
                                         "IORegistryEntryName": "UVCAssistant"}] if cls == 14 else []}


def camera(vid: int, pid: int, loc: int, name: str, serial: str | None = None, speed: int = 3, bcd: int = 0x16,
           vs_alt: int = 0) -> dict:
    d = {"IOObjectClass": "IOUSBHostDevice", "IORegistryEntryName": name, "IORegistryEntryID": _rid(),
         "idVendor": vid, "idProduct": pid, "bcdDevice": bcd, "locationID": loc, "USBSpeed": speed,
         "Device Speed": {3: 2, 4: 3, 1: 1, 2: 0}[speed], "bDeviceClass": 239, "bDeviceProtocol": 1,
         "USB Product Name": name, "sessionID": 123456789 + loc, "USB Address": loc & 0xFF or 3,
         "IORegistryEntryChildren": [
             {"IOObjectClass": "AppleUSBHostCompositeDevice", "IORegistryEntryName": "AppleUSBHostCompositeDevice"},
             iface(0, 14, 1, loc, vid, pid), iface(1, 14, 2, loc, vid, pid, vs_alt), iface(2, 1, 1, loc, vid, pid)]}
    if serial:
        d["USB Serial Number"] = serial
        d["kUSBSerialNumberString"] = serial
    return d


def hub(vid: int, pid: int, loc: int, name: str, speed: int, ports: dict[int, dict | None], usb3: bool,
        container: bytes | None = None, port_key: str = "port") -> dict:
    hub_driver = {"IOObjectClass": "AppleUSB30Hub" if usb3 else "AppleUSB20Hub",
                  "IORegistryEntryName": "AppleUSB30Hub" if usb3 else "AppleUSB20Hub", "IORegistryEntryChildren": []}
    for n, occ in ports.items():
        p = {"IOObjectClass": "AppleUSB30HubPort" if usb3 else "AppleUSB20HubPort",
             "IORegistryEntryName": f"port{n}", "IORegistryEntryID": _rid(), port_key: le32(n),
             "port-status": 0 if occ is None else (0x1400 if usb3 else 0x0300),
             "IORegistryEntryChildren": [occ] if occ else []}
        hub_driver["IORegistryEntryChildren"].append(p)
    d = {"IOObjectClass": "IOUSBHostDevice", "IORegistryEntryName": name, "IORegistryEntryID": _rid(),
         "idVendor": vid, "idProduct": pid, "bcdDevice": 0x9364, "locationID": loc, "USBSpeed": speed,
         "bDeviceClass": 9, "bDeviceProtocol": 3 if usb3 else 2, "USB Product Name": name,
         "IORegistryEntryChildren": [iface(0, 9, 0, loc, vid, pid), hub_driver]}
    if container:
        d["kUSBContainerID"] = container
    return d


def root_port(cls: str, name: str, num: int, occ: dict | None = None, **extra) -> dict:
    p = {"IOObjectClass": cls, "IORegistryEntryName": name, "IORegistryEntryID": _rid(), "port": le32(num),
         "port-status": 0 if occ is None else 0x0300, "IORegistryEntryChildren": [occ] if occ else []}
    p.update(extra)
    return p


def controller(cls: str, name: str, bus: int, ports: list[dict], port_number: int | None = None,
               rid: int | None = None) -> dict:
    c = {"IOObjectClass": cls, "IORegistryEntryName": name, "IORegistryEntryID": rid or _rid(),
         "locationID": bus << 24, "IORegistryEntryChildren": ports}
    if port_number is not None:
        c["port-number"] = le32(port_number)
    return c


# ---------------------------------------------------------------------------------------------- trees
C922 = (0x046D, 0x085C)
GENERIC = (0x4C4A, 0x4A55)
KIYO = (0x1532, 0x0E05)
C930E = (0x046D, 0x0843)
FL1100_RID = 777001


def apple_silicon_plists(macos26_keys: bool = False) -> dict[str, list[dict]]:
    """Mac Studio-like: two Apple DRD USB-C controllers + a Fresco FL1100 PCIe xHCI for USB-A.
    drd0 (left-back): empty. drd1 (right-back): Genesys USB 3 hub, HS half (05E3:0610) holding the generic
    camera (p2) and the C922 (p4, serial); SS half (05E3:0625) holding the Kiyo Pro at SuperSpeed (p4).
    FL1100: C930e on HS port 1; HS port 2 empty; SS ports 3/4 companions of 1/2."""
    _ID[0] = 1000
    pk = "usb-port-number" if macos26_keys else "port"
    cid = bytes(range(16))
    hs_hub = hub(0x05E3, 0x0610, 0x01100000, "USB2.0 Hub", 3, {
        1: None, 2: camera(*GENERIC, 0x01120000, "USB Camera", bcd=0x0100),
        3: None, 4: camera(*C922, 0x01140000, "C922 Pro Stream Webcam", serial="C922SN01", bcd=0x0016)},
        usb3=False, container=cid, port_key=pk)
    ss_hub = hub(0x05E3, 0x0625, 0x01200000, "USB3.1 Hub", 4, {
        1: None, 2: None, 3: None, 4: camera(*KIYO, 0x01240000, "Razer Kiyo Pro", speed=4, bcd=0x0108)},
        usb3=True, container=cid, port_key=pk)

    def drd_ports(n, hs_occ=None, ss_occ=None):
        hs = root_port("AppleUSB20XHCITypeCPort", f"usb-drd{n}-port-hs", 1, hs_occ)
        ss = root_port("AppleT8103USB40XHCITypeCPort", f"usb-drd{n}-port-ss", 2, ss_occ)
        if macos26_keys:
            for p in (hs, ss):
                p["usb-port-number"] = p.pop("port")
                p["port-status"] = 5  # the libusb #1661 beta excerpt: out of the SDK 11.3 layout
                p["UsbCPortNumber"] = le32(n + 1)
        return [hs, ss]

    ctrls = [
        controller("AppleT6000USBXHCI", "usb-drd0", 0x00, drd_ports(0), port_number=1),
        controller("AppleT6000USBXHCI", "usb-drd1", 0x01, drd_ports(1, hs_hub, ss_hub), port_number=2),
        controller("AppleUSBXHCIFL1100", "xhci", 0x02, [
            root_port("AppleUSB20XHCIPort", "port1@02100000", 1, camera(*C930E, 0x02100000, "Logitech Webcam C930e",
                                                                        bcd=0x0013), UsbCompanionPortNumber=le32(3),
                      UsbConnector=3, UsbConnectable=1),
            root_port("AppleUSB20XHCIPort", "port2@02200000", 2, None, UsbCompanionPortNumber=le32(4), UsbConnector=3,
                      UsbConnectable=1),
            root_port("AppleUSB30XHCIPort", "port3@02300000", 3, None, UsbCompanionPortNumber=le32(1), UsbConnector=3,
                      UsbConnectable=1),
            root_port("AppleUSB30XHCIPort", "port4@02400000", 4, None, UsbCompanionPortNumber=le32(2), UsbConnector=3,
                      UsbConnectable=1)], rid=FL1100_RID),
    ]
    hpm = [{"IOObjectClass": "AppleHPMARM", "IORegistryEntryName": "hpm0", "port-number": le32(1),
            "port-location": b"left-back\x00", "RID": 0},
           {"IOObjectClass": "AppleHPMARM", "IORegistryEntryName": "hpm1", "port-number": le32(2),
            "port-location": b"right-back\x00", "RID": 1}]
    pci = [{"IOObjectClass": "IOPCIDevice", "IORegistryEntryName": "pci1b73,1100", "vendor-id": le32(0x1B73),
            "device-id": le32(0x1100),
            "IORegistryEntryChildren": [{"IOObjectClass": "AppleUSBXHCIFL1100", "IORegistryEntryName": "xhci",
                                         "IORegistryEntryID": FL1100_RID}]}]
    interfaces = []
    for r in ctrls:
        stack = [r]
        while stack:
            n = stack.pop()
            if n.get("IOObjectClass") == "IOUSBHostInterface":
                interfaces.append({k: v for k, v in n.items() if k != "IORegistryEntryChildren"})
            stack.extend(n.get("IORegistryEntryChildren", []) or [])
    return {"controllers": ctrls, "hpm": hpm, "pci": pci, "interfaces": interfaces}


def intel_plists() -> dict[str, list[dict]]:
    """2018 Mac mini-like: Cannon Lake PCH xHCI (HS01-HS04, SS01-SS02 with companions), C930e on HS02, plus the
    T2 virtual bus with the built-in FaceTime camera (excluded from suggestions)."""
    _ID[0] = 5000
    pch_rid = 888001
    ports = [root_port("AppleUSB20XHCIPort", f"HS{n:02d}", n,
                       camera(*C930E, 0x14200000, "Logitech Webcam C930e", bcd=0x0013) if n == 2 else None,
                       UsbCompanionPortNumber=le32(4 + n) if n <= 2 else None, UsbConnector=3 if n <= 2 else 0,
                       UsbConnectable=1)
             for n in range(1, 5)]
    for p in ports:
        if p.get("UsbCompanionPortNumber") is None:
            p.pop("UsbCompanionPortNumber")
    ports += [root_port("AppleUSB30XHCIPort", f"SS{n:02d}", 4 + n, None, UsbCompanionPortNumber=le32(n),
                        UsbConnector=3, UsbConnectable=1) for n in (1, 2)]
    ctrls = [controller("AppleIntelCNLUSBXHCI", "XHC1", 0x14, ports, rid=pch_rid),
             controller("AppleUSBVHCIBCE", "VHC128", 0x80, [
                 root_port("AppleUSB20HubPort", "port2", 2,
                           camera(0x05AC, 0x8514, 0x80200000, "FaceTime HD Camera (Built-in)"))])]
    pci = [{"IOObjectClass": "IOPCIDevice", "IORegistryEntryName": "XHC1@14", "vendor-id": le32(0x8086),
            "device-id": le32(0xA36D), "IORegistryEntryChildren": [
                {"IOObjectClass": "AppleIntelCNLUSBXHCI", "IORegistryEntryName": "XHC1", "IORegistryEntryID": pch_rid}]}]
    return {"controllers": ctrls, "pci": pci, "hpm": []}


def write_fake_dir(d: Path, plists: dict[str, list[dict]]) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    for k, v in plists.items():
        (d / f"ioreg_{k}.plist").write_bytes(plistlib.dumps(v))
    return d


# ---------------------------------------------------------------------------------------------- AVFoundation fakes
def avf_format(index: int, sub: str, w: int, h: int, rates: list[float]) -> dict:
    return {"index": index, "subtype": sub, "w": w, "h": h, "discrete": True,
            "ranges": [{"min_fps": r, "max_fps": r, "min_frame_duration": {"value": 1000000, "timescale": int(r * 1e6),
                                                                           "flags": 1, "epoch": 0},
                        "max_frame_duration": {"value": 1000000, "timescale": int(r * 1e6), "flags": 1, "epoch": 0}}
                       for r in rates]}


def avf_device(order: int, loc: int, vid: int, pid: int, name: str, formats: list[dict]) -> dict:
    uid = f"0x{(loc << 32) | (vid << 16) | pid:x}"
    return {"order": order, "unique_id": uid, "model_id": f"UVC Camera VendorID_{vid} ProductID_{pid}", "name": name,
            "transport": "usb", "is_usb": True, "uid_parsed": {"location_id": loc, "location_hex": f"0x{loc:08x}",
                                                                "vid": f"{vid:04x}", "pid": f"{pid:04x}"},
            "model_parsed": {"vid": f"{vid:04x}", "pid": f"{pid:04x}"}, "formats": formats}


STD_FORMATS = [avf_format(0, "420v", 640, 480, [30.0]), avf_format(1, "dmb1", 640, 480, [30.0, 15.0]),
               avf_format(2, "dmb1", 1280, 720, [30.0]), avf_format(3, "dmb1", 1920, 1080, [30.0])]


def apple_silicon_avf() -> dict:
    return {"authorization": "authorized", "devices": [
        avf_device(0, 0x01140000, *C922, "C922 Pro Stream Webcam", STD_FORMATS),
        avf_device(1, 0x01120000, *GENERIC, "USB Camera", STD_FORMATS),
        avf_device(2, 0x01240000, *KIYO, "Razer Kiyo Pro", STD_FORMATS),
        avf_device(3, 0x02100000, *C930E, "Logitech Webcam C930e", STD_FORMATS),
        {"order": 4, "unique_id": "47B4B64B70674B9CAD2BAE273A71F4B5", "name": "FaceTime HD Camera", "transport": "0x00000000",
         "is_usb": False, "uid_parsed": None, "model_id": "FaceTimeHD", "formats": []}]}


def write_fake_avf(path: Path) -> Path:
    path.write_text(json.dumps(apple_silicon_avf()), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------------------------- UVC descriptor
def uvc_config(alts: dict[int, tuple[int, int]], mjpeg_frames: list[tuple[int, int, list[float]]],
               ct_controls: int = 0x0A0E, pu_controls: int = 0x165B) -> bytes:
    """A UVC 1.0 configuration: VC (header, camera IT id 1 with ct_controls, PU id 2 with pu_controls, OT 3) and
    one VS interface with an MJPEG format, the given frames, and iso alts {alt: (max_packet, mult)}."""
    vc_hdr = bytes([13, 0x24, 1]) + struct.pack("<HHIB", 0x0100, 0, 30_000_000, 1) + bytes([1])
    it = bytes([18, 0x24, 2, 1]) + struct.pack("<HBB", 0x0201, 0, 0) + struct.pack("<HHHB", 0, 0, 0, 3) + ct_controls.to_bytes(3, "little")
    pu = bytes([11, 0x24, 5, 2, 1]) + struct.pack("<HB", 0, 2) + pu_controls.to_bytes(2, "little") + bytes([0])
    ot = bytes([9, 0x24, 3, 3]) + struct.pack("<HBBB", 0x0101, 0, 2, 0)
    vc_if = bytes([9, 4, 0, 0, 0, 0x0E, 1, 0, 0])
    vs_hdr = bytes([14, 0x24, 1, 1]) + struct.pack("<HBBBBBBB", 0, 0x81, 0, 3, 0, 0, 0, 1) + bytes([0])
    fmt = bytes([11, 0x24, 6, 1, len(mjpeg_frames), 1, 1, 0, 0, 0, 0])
    frames = b""
    for i, (w, h, rates) in enumerate(mjpeg_frames, start=1):
        ivals = [int(round(1e7 / r)) for r in rates]
        body = struct.pack("<BBHHIIII", i, 0, w, h, 1, 2, w * h * 2, ivals[0]) + bytes([len(ivals)]) + \
            b"".join(struct.pack("<I", v) for v in ivals)
        frames += bytes([3 + len(body), 0x24, 7]) + body
    vs = bytes([9, 4, 1, 0, 0, 0x0E, 2, 0, 0]) + vs_hdr + fmt + frames
    for alt, (mp, mult) in sorted(alts.items()):
        vs += bytes([9, 4, 1, alt, 1, 0x0E, 2, 0, 0]) + bytes([7, 5, 0x81, 0x05]) + struct.pack("<HB", ((mult - 1) << 11) | mp, 1)
    iad = bytes([8, 0x0B, 0, 2, 0x0E, 3, 0, 0])
    body = iad + vc_if + vc_hdr + it + pu + ot + vs
    return bytes([9, 2]) + struct.pack("<HBBBBB", 9 + len(body), 2, 1, 0, 0x80, 250) + body


C922_ALTS = {1: (192, 1), 2: (384, 1), 3: (512, 1), 4: (640, 1), 5: (800, 1), 6: (944, 1), 7: (640, 2), 8: (800, 2),
             9: (992, 2), 10: (896, 3), 11: (1020, 3)}
GENERIC_ALTS = {1: (1023, 3)}


class FakeUVCTransport:
    """A camera answering UVC GET_*/SET_CUR on the VC interface (entity 1 = CT, 2 = PU, interface 0)."""
    name = "fake"

    def __init__(self, dead_after: int | None = None):
        self.vals = {(1, 0x02): {"cur": 8, "min": 1, "max": 8, "res": 9, "def": 8, "len": 1, "info": 3},
                     (1, 0x04): {"cur": 156, "min": 3, "max": 2047, "res": 1, "def": 250, "len": 4, "info": 15},
                     (2, 0x04): {"cur": 0, "min": 0, "max": 255, "res": 1, "def": 0, "len": 2, "info": 3},
                     (2, 0x02): {"cur": -10, "min": -64, "max": 64, "res": 1, "def": 0, "len": 2, "info": 3, "signed": True},
                     (2, 0x0A): {"cur": 4600, "min": 2800, "max": 6500, "res": 10, "def": 4600, "len": 2, "info": 15},
                     (2, 0x0B): {"cur": 1, "min": 0, "max": 1, "res": 1, "def": 1, "len": 1, "info": 3}}
        self.calls = 0
        self.dead_after = dead_after

    def _dead(self) -> bool:
        self.calls += 1
        return self.dead_after is not None and self.calls > self.dead_after

    def ctrl_in(self, bm, req, wv, wi, length, timeout_ms):
        if self._dead():
            return 0xE00002ED, b""  # kIOReturnNotResponding
        if bm == 0x81 and req == 0x0A:
            return 0, bytes([4])
        ent, sel = wi >> 8, wv >> 8
        v = self.vals.get((ent, sel))
        if v is None:
            return 0xE000404F, b""  # stall
        key = {0x81: "cur", 0x82: "min", 0x83: "max", 0x84: "res", 0x87: "def", 0x86: "info", 0x85: "len"}[req]
        n = 1 if req == 0x86 else v["len"]
        return 0, int(v[key]).to_bytes(n, "little", signed=bool(v.get("signed")) and req != 0x86)

    def ctrl_out(self, bm, req, wv, wi, data, timeout_ms):
        if self._dead():
            return 0xE00002ED
        v = self.vals.get((wi >> 8, wv >> 8))
        if v is None:
            return 0xE000404F
        v["cur"] = int.from_bytes(data, "little", signed=bool(v.get("signed")))
        return 0
