# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pyobjc-framework-AVFoundation>=10.3; sys_platform == 'darwin'",
# ]
# ///
"""macOS DRAFT (unverified until run by the user): camera identity from AVFoundation + IOKit.

WHAT TO RUN (repo root, normal user, no sudo):
    uv run --script research/usb_cameras/naming/macos_identity.py --label baseline
  then after (a) reboot, (b) replug into the SAME ports, (c) move cameras to DIFFERENT ports:
    uv run --script research/usb_cameras/naming/macos_identity.py --label after_reboot      # etc.
    uv run --script research/usb_cameras/naming/identity_diff.py research/usb_cameras/results/macos/$(hostname -s)/naming/snapshots/*.json
  (naming/macos_stability_workflow.sh wraps these steps.)

HARDWARE: UVC webcams (ideally two of the same model). PERMISSIONS: listing AVCaptureDevices is expected not to
need the Camera (TCC) permission because no session is started; if the list comes back empty, grant Terminal
camera access in System Settings > Privacy & Security > Camera and rerun - the JSON records `avf_error`.

WHAT IT RECORDS (results/macos/<hostname>/naming/):
  * AVFoundation (pyobjc): uniqueID, modelID, localizedName, manufacturer, transportType, deviceType
  * IOKit via `ioreg -a -r -c IOUSBHostDevice -l -w0` (plist): idVendor, idProduct, bcdDevice, USB Serial Number,
    kUSBSerialNumberString, USB Product Name, USB Vendor Name, locationID, USB Address, Device Speed, sessionID
  * the TEST of the reported uniqueID format: does int(uniqueID, 16) == locationID << 32 | idVendor << 16 | idProduct ?
    (reported in https://developer.apple.com/forums/thread/803759 , not documented by Apple)
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import platform
import plistlib
import socket
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def ioreg_usb_devices() -> list[dict]:
    out = subprocess.run(["ioreg", "-a", "-r", "-c", "IOUSBHostDevice", "-l", "-w0"], capture_output=True, timeout=30)
    if out.returncode != 0 or not out.stdout.strip():
        return []
    roots = plistlib.loads(out.stdout)
    devs, seen = [], set()

    def walk(n):
        # `ioreg -r -c` may list a device both as its own root and nested under its hub: dedupe
        if isinstance(n, dict):
            if "idVendor" in n and "idProduct" in n and n.get("IOObjectClass", n.get("IOClass", "")) != "IOUSBHostInterface":
                k = (n.get("locationID"), n.get("sessionID"), n.get("idVendor"), n.get("idProduct"))
                if k not in seen:
                    seen.add(k)
                    devs.append(n)
            for c in n.get("IORegistryEntryChildren", []) or []:
                walk(c)
    for r in roots if isinstance(roots, list) else [roots]:
        walk(r)
    return devs


def _has_video_interface(n: dict) -> bool:
    stack = [n]
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            if x.get("bInterfaceClass") == 14:
                return True
            # do not descend into downstream devices (a hub would otherwise "have" its camera's interfaces)
            stack.extend(ch for ch in (x.get("IORegistryEntryChildren", []) or [])
                         if not (isinstance(ch, dict) and "bDeviceClass" in ch or
                                 isinstance(ch, dict) and ch.get("IOObjectClass") == "IOUSBHostDevice"))
    return False


def _clean(n: dict) -> dict:
    keep = {}
    for k, v in n.items():
        if k == "IORegistryEntryChildren":
            continue
        if isinstance(v, (str, int, float, bool)):
            keep[k] = v
        elif isinstance(v, bytes):
            keep[k] = v.hex()
    return keep


def avfoundation_devices() -> tuple[list[dict], str | None]:
    try:
        import AVFoundation as AVF
    except ImportError as e:
        return [], f"pyobjc AVFoundation not importable: {e}"
    try:
        types = [t for t in (getattr(AVF, "AVCaptureDeviceTypeExternal", None),
                             getattr(AVF, "AVCaptureDeviceTypeExternalUnknown", None),
                             getattr(AVF, "AVCaptureDeviceTypeBuiltInWideAngleCamera", None),
                             getattr(AVF, "AVCaptureDeviceTypeContinuityCamera", None)) if t]
        sess = AVF.AVCaptureDeviceDiscoverySession.discoverySessionWithDeviceTypes_mediaType_position_(
            types, AVF.AVMediaTypeVideo, AVF.AVCaptureDevicePositionUnspecified)
        devs = list(sess.devices())
    except Exception as e:  # noqa: BLE001
        try:
            devs = list(AVF.AVCaptureDevice.devicesWithMediaType_(AVF.AVMediaTypeVideo))
        except Exception as e2:  # noqa: BLE001
            return [], f"{e!r} / {e2!r}"
    out = []
    for i, d in enumerate(devs):
        tt = int(d.transportType()) if hasattr(d, "transportType") else None
        out.append(dict(order=i, uniqueID=str(d.uniqueID()), modelID=str(d.modelID()), localizedName=str(d.localizedName()),
                        manufacturer=str(d.manufacturer()) if d.manufacturer() else None,
                        transportType=tt, transportType_fourcc=tt.to_bytes(4, "big").decode("latin1") if tt else None,
                        deviceType=str(d.deviceType()) if hasattr(d, "deviceType") else None))
    return out, None


def _uid_int(u: str) -> int | None:
    try:
        return int(u, 16) if u.lower().startswith("0x") else None
    except ValueError:
        return None


def collect() -> dict:
    usb = [dict(_clean(n), has_video_interface=_has_video_interface(n)) for n in ioreg_usb_devices()]
    avf, err = avfoundation_devices()
    for a in avf:
        a["matches"] = []
        for u in usb:
            loc, vid, pid = u.get("locationID"), u.get("idVendor"), u.get("idProduct")
            if None in (loc, vid, pid):
                continue
            # forum examples ("0x2000000fd9009b") show locationID printed WITHOUT zero padding, so compare numerically
            if _uid_int(a["uniqueID"]) == (loc << 32) | (vid << 16) | pid:
                a["matches"].append(dict(rule="int(uniqueID,16) == locationID<<32 | vid<<16 | pid", locationID=f"0x{loc:08x}"))
        a["uniqueID_format_confirmed"] = bool(a["matches"])
    return dict(usb_devices=usb, avfoundation=avf, avf_error=err)


def collect_flat() -> list[dict]:
    c = collect()
    flats = []
    for u in c["usb_devices"]:
        if not u.get("has_video_interface"):
            continue
        loc, vid, pid = u.get("locationID"), u.get("idVendor"), u.get("idProduct")
        uid = (loc << 32) | (vid << 16) | pid if None not in (loc, vid, pid) else None
        a = next((x for x in c["avfoundation"] if uid is not None and _uid_int(x["uniqueID"]) == uid), {})
        flats.append(dict(vid=f"{vid:04x}", pid=f"{pid:04x}", bcdDevice=f"{u.get('bcdDevice', 0):04x}",
                          usb_serial=u.get("USB Serial Number") or u.get("kUSBSerialNumberString"),
                          usb_product=u.get("USB Product Name") or u.get("kUSBProductString"),
                          usb_manufacturer=u.get("USB Vendor Name") or u.get("kUSBVendorString"),
                          location_id=loc, location_id_hex=f"0x{loc:08x}" if loc is not None else None,
                          usb_address=u.get("USB Address"), session_id=u.get("sessionID"), speed=u.get("Device Speed"),
                          avf_unique_id=a.get("uniqueID"), avf_model_id=a.get("modelID"),
                          avf_localized_name=a.get("localizedName"), avf_order=a.get("order"),
                          avf_unique_id_matches_location=bool(a)))
    return flats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default=None)
    ap.add_argument("--out-dir", type=Path, default=None)
    a = ap.parse_args()
    if sys.platform != "darwin":
        print("this script is for macOS", file=sys.stderr)
        return 2
    host = socket.gethostname().split(".")[0]
    out_dir = a.out_dir or HERE.parent / "results" / "macos" / host / "naming"
    out_dir.mkdir(parents=True, exist_ok=True)
    started = _dt.datetime.now(_dt.timezone.utc).isoformat()
    full = collect()
    flats = collect_flat()
    try:
        import camera_identity
        for f in flats:
            f["port_path"] = camera_identity.port_path_from_mac_location_id(f["location_id"])
        for f in flats:
            f["camera_key"] = camera_identity.derive(f, flats)[0]
    except ImportError:
        pass
    base = dict(platform="macos", hostname=host, utc_started=started, command=" ".join(sys.argv),
                environment=dict(os=platform.platform(), mac_ver=platform.mac_ver()[0], python=sys.version.split()[0]))
    (out_dir / "identity_dump.json").write_text(json.dumps(dict(test="naming.macos_identity_dump", **base, **full), indent=1, default=str))
    if a.label:
        (out_dir / "snapshots").mkdir(exist_ok=True)
        (out_dir / "snapshots" / f"{a.label}.json").write_text(
            json.dumps(dict(test="naming.snapshot", label=a.label, **base, cameras=flats), indent=1, default=str))
    for f in flats:
        print(json.dumps(f, default=str))
    if full["avf_error"]:
        print("AVFoundation error:", full["avf_error"], file=sys.stderr)
    print("wrote", out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
