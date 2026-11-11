# /// script
# requires-python = ">=3.10"
# ///
"""Read USB descriptors (device, configuration, BOS, a few strings) of USB devices through their parent hub.

    python win_descriptors.py --instance "USB\\VID_046D&PID_085C\\C922SN01" [--instance ...] [--out FILE]

This SENDS STANDARD GET_DESCRIPTOR REQUESTS on EP0 (IOCTL_USB_GET_DESCRIPTOR_FROM_NODE_CONNECTION), the same as
usbview, naming/win_identity_dump.py and bandwidth/win_usb_topology.py. It opens no stream, claims nothing and
changes no state, but it does reach the device, so the suite runs it one camera per child process, under camlock,
with a timeout (the Razer Kiyo Pro can stop answering control requests). Instance IDs are the USB DEVICE
(composite parent) instance IDs from suitectx discovery: never hard-coded.

Output (stdout, one JSON object): {"devices": [{instance_id, vid, pid, hub_instance_id, port, speed, device,
configuration (naming/usbdesc.py parse_configuration), bos, strings, manufacturer, product, serial_number,
raw {device, configuration, bos}, requests, errors, elapsed_ms}], "utc", "command"}.
Parsing: naming/usbdesc.py (imported from the study folder, unmodified).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import struct
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESEARCH_ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(RESEARCH_ROOT / "naming"))
import usbdesc  # noqa: E402
import winpnp as wp  # noqa: E402


def read_one(usb_iid: str, strings: bool = True) -> dict:
    t0 = time.perf_counter()
    out: dict = {"instance_id": usb_iid, "errors": [], "requests": 0}
    vid, pid, _ = wp.parse_usb_ids(usb_iid)
    out.update(vid=vid, pid=pid)
    dn = wp.locate(usb_iid)
    if dn is None:
        out["errors"].append("device not present")
        return out
    port = wp.devnode_prop(dn, "Address")
    hdn = wp.parent(dn)
    hub_iid = wp.instance_id(hdn) if hdn else None
    out.update(hub_instance_id=hub_iid, port=port)
    path = wp.hub_interface_for_instance(hub_iid) if hub_iid else None
    if not path or port is None:
        out["errors"].append("no hub interface / port")
        return out
    h, err = wp.open_path(path)
    if h is None:
        out["errors"].append(f"open hub failed winerror {err}")
        return out
    try:
        ci = wp.connection_info(h, int(port))
        v2 = ci.get("v2_flags") or {}
        speed = "super_plus" if v2.get("op_ssp") else "super" if v2.get("op_ss") else ci.get("legacy_speed")
        out["speed"] = speed
        out["cached_connection"] = {k: v for k, v in ci.items() if k != "driver_key"}

        def gd(dtype, index=0, lang=0, length=4096):
            out["requests"] += 1
            return wp.get_descriptor(h, int(port), dtype, index, lang, length)

        raw: dict = {}
        try:
            dev_raw = gd(usbdesc.DT_DEVICE, length=18)
            raw["device"] = dev_raw.hex()
            dev = usbdesc.parse_device_descriptor(dev_raw)
            out["device"] = dev
        except (OSError, ValueError) as e:
            out["errors"].append(f"device descriptor: {e}")
            out["raw"] = raw
            return out
        try:
            head = gd(usbdesc.DT_CONFIG, 0, length=9)
            total = struct.unpack_from("<H", head, 2)[0]
            cfg_raw = gd(usbdesc.DT_CONFIG, 0, length=total)
            raw["configuration"] = cfg_raw.hex()
            out["configuration"] = usbdesc.parse_configuration(cfg_raw, speed)
        except (OSError, ValueError, struct.error) as e:
            out["errors"].append(f"configuration descriptor: {e}")
        if dev.get("bcdUSB_raw", 0) >= 0x0201:
            try:
                bh = gd(usbdesc.DT_BOS, 0, length=5)
                btotal = struct.unpack_from("<H", bh, 2)[0]
                braw = gd(usbdesc.DT_BOS, 0, length=btotal)
                raw["bos"] = braw.hex()
                out["bos"] = usbdesc.parse_bos(braw)
            except (OSError, ValueError, struct.error) as e:
                out["errors"].append(f"bos: {e}")
        out["raw"] = raw
        if strings:
            st: dict = {}
            lang = 0x0409
            try:
                l0 = gd(usbdesc.DT_STRING, 0, 0, 255)
                langs = [struct.unpack_from("<H", l0, 2 + 2 * i)[0] for i in range((l0[0] - 2) // 2)] if l0 else []
                if langs and 0x0409 not in langs:
                    lang = langs[0]
                out["string_languages"] = [f"0x{x:04x}" for x in langs]
            except (OSError, ValueError, IndexError) as e:
                out["errors"].append(f"langid: {e}")
            for name in ("iManufacturer", "iProduct", "iSerialNumber"):
                i = dev.get(name)
                if not i:
                    continue
                try:
                    st[name] = usbdesc.decode_string_descriptor(gd(usbdesc.DT_STRING, i, lang, 255))
                except (OSError, ValueError) as e:
                    st[name] = {"error": str(e)}
            out["strings"] = st
            out["manufacturer"] = st.get("iManufacturer") if isinstance(st.get("iManufacturer"), str) else None
            out["product"] = st.get("iProduct") if isinstance(st.get("iProduct"), str) else None
            out["serial_number"] = st.get("iSerialNumber") if isinstance(st.get("iSerialNumber"), str) else None
    finally:
        wp.close(h)
        out["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    return out


def alt_table_from_configuration(cfg: dict | None, speed: str | None) -> list[dict] | None:
    """Isochronous VS alt settings -> [{"alt", "max_packet", "mult", "interface", "ep", "wMaxPacketSize_raw",
    "bInterval", "bytes_per_interval"}] in topology_model's alt_table form. For SuperSpeed, mult = bursts x mult
    from the SS endpoint companion (topology_model convention). None if no isochronous VS interface."""
    uvc = (cfg or {}).get("uvc") or {}
    out = []
    for s in uvc.get("streaming_interfaces") or []:
        for a in s.get("alt_settings") or []:
            if a.get("transfer_type") != "isochronous":
                continue
            raw = a.get("wMaxPacketSize_raw") or 0
            mp, mult = raw & 0x7FF, ((raw >> 11) & 3) + 1
            comp = a.get("ss_companion")
            if speed in ("super", "super_plus") and comp:
                mult = (int(comp.get("bMaxBurst", 0)) + 1) * ((int(comp.get("bmAttributes", 0)) & 3) + 1)
            out.append({"alt": a.get("bAlternateSetting"), "max_packet": mp, "mult": mult,
                        "interface": s.get("bInterfaceNumber"), "ep": a.get("bEndpointAddress"),
                        "wMaxPacketSize_raw": raw, "bInterval": a.get("bInterval"),
                        "bytes_per_interval": a.get("bytes_per_interval")})
    return out or None


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="read USB descriptors through the parent hub (EP0 GET_DESCRIPTOR)")
    ap.add_argument("--instance", action="append", default=[], help="USB device instance ID (repeatable)")
    ap.add_argument("--no-strings", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    if not a.instance:
        ap.error("--instance is required (instance IDs come from suitectx discovery; nothing is hard-coded)")
    t_utc = _dt.datetime.now(_dt.timezone.utc).isoformat()
    devs = []
    for iid in a.instance:
        try:
            d = read_one(iid, strings=not a.no_strings)
        except Exception as e:  # noqa: BLE001 - record, never crash
            d = {"instance_id": iid, "errors": [f"{type(e).__name__}: {e}"]}
        d["alt_table"] = alt_table_from_configuration(d.get("configuration"), d.get("speed"))
        devs.append(d)
    doc = {"tool": "win_descriptors", "utc": t_utc, "command": sys.argv, "devices": devs,
           "note": "sends standard GET_DESCRIPTOR requests on EP0; no stream, no claim, no state change"}
    text = json.dumps(doc, indent=1, default=str)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(text, encoding="utf-8")
    print(text)
    return 0 if all(not d.get("errors") for d in devs) else 4


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
