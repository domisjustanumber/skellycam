"""UVC 1.0/1.1 class-specific control requests on endpoint 0 (pure Python; any transport).

A *transport* is any object with:
    ctrl_in(bmRequestType, bRequest, wValue, wIndex, length, timeout_ms) -> (rc: int, data: bytes)
    ctrl_out(bmRequestType, bRequest, wValue, wIndex, data, timeout_ms) -> rc: int
    name: str
where rc == 0 means success and any other value is the backend's raw code (IOReturn on IOKit, libusb error code
on libusb), recorded as is. Nothing here claims an interface, sets an alt or touches a driver: only GET_* and
SET_CUR to the VideoControl interface, GET_INTERFACE and VS_COMMIT GET_CUR (read-only) to VideoStreaming.

Selector tables: UVC 1.1 specification tables A-12 (camera terminal) and A-13 (processing unit). The bmControls
bit -> selector maps follow sections 3.7.2.3 (CT) and 3.7.2.5 (PU).
"""
from __future__ import annotations

import struct
import time
from typing import Any

SET_CUR, GET_CUR, GET_MIN, GET_MAX, GET_RES, GET_LEN, GET_INFO, GET_DEF = 0x01, 0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87
REQ_NAMES = {GET_CUR: "GET_CUR", GET_MIN: "GET_MIN", GET_MAX: "GET_MAX", GET_RES: "GET_RES", GET_LEN: "GET_LEN",
             GET_INFO: "GET_INFO", GET_DEF: "GET_DEF", SET_CUR: "SET_CUR"}
RT_GET_IF, RT_SET_IF = 0xA1, 0x21          # class request, interface recipient
RT_STD_GET_IF = 0x81                       # standard GET_INTERFACE
RT_STD_GET_DEV = 0x80                      # standard GET_DESCRIPTOR
STD_GET_INTERFACE, STD_GET_DESCRIPTOR = 0x0A, 0x06
VS_PROBE_CONTROL, VS_COMMIT_CONTROL = 0x01, 0x02

# name, selector, size, signed, kind ('range' | 'bool' | 'menu' | 'bitmap' | 'multi')
CT_CONTROLS: dict[str, tuple[int, int, bool, str]] = {
    "scanning_mode": (0x01, 1, False, "bool"),
    "auto_exposure_mode": (0x02, 1, False, "bitmap"),
    "auto_exposure_priority": (0x03, 1, False, "bool"),
    "exposure_time_absolute": (0x04, 4, False, "range"),
    "exposure_time_relative": (0x05, 1, True, "range"),
    "focus_absolute": (0x06, 2, False, "range"),
    "focus_relative": (0x07, 2, False, "multi"),
    "focus_auto": (0x08, 1, False, "bool"),
    "iris_absolute": (0x09, 2, False, "range"),
    "iris_relative": (0x0A, 1, False, "range"),
    "zoom_absolute": (0x0B, 2, False, "range"),
    "zoom_relative": (0x0C, 3, False, "multi"),
    "pantilt_absolute": (0x0D, 8, False, "multi"),
    "pantilt_relative": (0x0E, 4, False, "multi"),
    "roll_absolute": (0x0F, 2, True, "range"),
    "roll_relative": (0x10, 2, False, "multi"),
    "privacy": (0x11, 1, False, "bool"),
}
PU_CONTROLS: dict[str, tuple[int, int, bool, str]] = {
    "backlight_compensation": (0x01, 2, False, "range"),
    "brightness": (0x02, 2, True, "range"),
    "contrast": (0x03, 2, False, "range"),
    "gain": (0x04, 2, False, "range"),
    "power_line_frequency": (0x05, 1, False, "menu"),
    "hue": (0x06, 2, True, "range"),
    "saturation": (0x07, 2, False, "range"),
    "sharpness": (0x08, 2, False, "range"),
    "gamma": (0x09, 2, False, "range"),
    "white_balance_temperature": (0x0A, 2, False, "range"),
    "white_balance_temperature_auto": (0x0B, 1, False, "bool"),
    "white_balance_component": (0x0C, 4, False, "multi"),
    "white_balance_component_auto": (0x0D, 1, False, "bool"),
    "digital_multiplier": (0x0E, 2, False, "range"),
    "digital_multiplier_limit": (0x0F, 2, False, "range"),
    "hue_auto": (0x10, 1, False, "bool"),
    "analog_video_standard": (0x11, 1, False, "menu"),
    "analog_video_lock_status": (0x12, 1, False, "menu"),
    "contrast_auto": (0x13, 1, False, "bool"),
}
# bmControls bit index -> control name (same bit lists as usbdesc.CAMERA_CONTROL_BITS / PROCESSING_CONTROL_BITS)
CT_BITS = ["scanning_mode", "auto_exposure_mode", "auto_exposure_priority", "exposure_time_absolute",
           "exposure_time_relative", "focus_absolute", "focus_relative", "iris_absolute", "iris_relative",
           "zoom_absolute", "zoom_relative", "pantilt_absolute", "pantilt_relative", "roll_absolute", "roll_relative",
           None, None, "focus_auto", "privacy", None, None, None]
PU_BITS = ["brightness", "contrast", "hue", "saturation", "sharpness", "gamma", "white_balance_temperature",
           "white_balance_component", "backlight_compensation", "gain", "power_line_frequency", "hue_auto",
           "white_balance_temperature_auto", "white_balance_component_auto", "digital_multiplier",
           "digital_multiplier_limit", "analog_video_standard", "analog_video_lock_status", "contrast_auto"]
AE_MODE_BITS = {1: "manual", 2: "auto", 4: "shutter_priority", 8: "aperture_priority"}

#: IOReturn names that matter for ep0 (IOReturn.h + IOUSBHostFamily); signed or unsigned input accepted
IORETURN = {0: "kIOReturnSuccess", 0xE00002BC: "kIOReturnError", 0xE00002BE: "kIOReturnNoResources",
            0xE00002C0: "kIOReturnNoDevice", 0xE00002C1: "kIOReturnNotPrivileged", 0xE00002C2: "kIOReturnBadArgument",
            0xE00002C5: "kIOReturnExclusiveAccess", 0xE00002C7: "kIOReturnUnsupported", 0xE00002CA: "kIOReturnIOError",
            0xE00002CD: "kIOReturnNotOpen", 0xE00002D5: "kIOReturnBusy", 0xE00002D6: "kIOReturnTimeout",
            0xE00002D8: "kIOReturnNotReady", 0xE00002D9: "kIOReturnNotAttached", 0xE00002E2: "kIOReturnNotPermitted",
            0xE00002E9: "kIOReturnDeviceError", 0xE00002EB: "kIOReturnAborted", 0xE00002EC: "kIOReturnNoBandwidth",
            0xE00002ED: "kIOReturnNotResponding", 0xE00002F0: "kIOReturnNotFound", 0xE00002E8: "kIOReturnOverrun",
            0xE000404F: "kIOUSBPipeStalled", 0xE0004050: "kIOUSBTransactionReturned",
            0xE0004051: "kIOUSBTransactionTimeout", 0xE0004057: "kIOUSBEndpointNotFound",
            0xE0004061: "kIOUSBUnknownPipeErr", 0xE0005000: "kIOUSBHostReturnPipeStalled"}
LIBUSB_ERRORS = {0: "LIBUSB_SUCCESS", -1: "LIBUSB_ERROR_IO", -2: "LIBUSB_ERROR_INVALID_PARAM", -3: "LIBUSB_ERROR_ACCESS",
                 -4: "LIBUSB_ERROR_NO_DEVICE", -5: "LIBUSB_ERROR_NOT_FOUND", -6: "LIBUSB_ERROR_BUSY",
                 -7: "LIBUSB_ERROR_TIMEOUT", -8: "LIBUSB_ERROR_OVERFLOW", -9: "LIBUSB_ERROR_PIPE",
                 -10: "LIBUSB_ERROR_INTERRUPTED", -11: "LIBUSB_ERROR_NO_MEM", -12: "LIBUSB_ERROR_NOT_SUPPORTED",
                 -99: "LIBUSB_ERROR_OTHER"}


def rc_name(rc: Any) -> str | None:
    if rc is None:
        return None
    if isinstance(rc, str):
        return rc
    if -99 <= rc <= 0 and rc in LIBUSB_ERRORS:
        return LIBUSB_ERRORS[rc]
    u = rc & 0xFFFFFFFF
    return IORETURN.get(u, f"0x{u:08X}")


def rc_hex(rc: Any) -> str | None:
    if rc is None or isinstance(rc, str):
        return None
    return f"0x{rc & 0xFFFFFFFF:08X}"


def decode(data: bytes, size: int, signed: bool) -> int | None:
    if not data:
        return None
    n = min(len(data), size if size in (1, 2, 4, 8) else len(data))
    return int.from_bytes(data[:n], "little", signed=signed)


def encode(value: int, size: int, signed: bool) -> bytes:
    return int(value).to_bytes(size, "little", signed=signed)


def decode_info(b: int | None) -> dict | None:
    """GET_INFO bitmap (UVC 4.1.2): D0 GET supported, D1 SET supported, D2 disabled by auto mode,
    D3 autoupdate, D4 asynchronous."""
    if b is None:
        return None
    return {"get": bool(b & 1), "set": bool(b & 2), "disabled_by_auto": bool(b & 4), "autoupdate": bool(b & 8),
            "async": bool(b & 16), "raw": b}


def controls_from_bitmap(mask_hex: str | int | None, bits: list) -> list[str]:
    if mask_hex is None:
        return []
    mask = int(mask_hex, 16) if isinstance(mask_hex, str) else int(mask_hex)
    return [n for i, n in enumerate(bits) if n and mask >> i & 1]


def entities_from_uvc_summary(uvc: dict | None) -> dict:
    """From usbdesc.summarize_uvc(): {"vc_interface", "camera_terminal": {"id", "controls"}, "processing_unit":
    {"id","controls"}, "extension_units": [...], "bcdUVC"}. Missing parts are None."""
    out: dict[str, Any] = {"vc_interface": None, "camera_terminal": None, "processing_unit": None,
                           "extension_units": [], "bcdUVC": None}
    if not uvc:
        return out
    out["vc_interface"] = uvc.get("vc_interface")
    out["bcdUVC"] = uvc.get("bcdUVC")
    for u in uvc.get("units") or []:
        st = u.get("subtype")
        if st == "VC_INPUT_TERMINAL" and u.get("wTerminalType") == "ITT_CAMERA":
            out["camera_terminal"] = {"id": u.get("bTerminalID"), "bmControls": u.get("bmControls"),
                                      "controls": controls_from_bitmap(u.get("bmControls"), CT_BITS)}
        elif st == "VC_PROCESSING_UNIT":
            out["processing_unit"] = {"id": u.get("bUnitID"), "bmControls": u.get("bmControls"),
                                      "controls": controls_from_bitmap(u.get("bmControls"), PU_BITS)}
        elif st == "VC_EXTENSION_UNIT":
            out["extension_units"].append({"id": u.get("bUnitID"), "guid": u.get("guidExtensionCode"),
                                           "known_as": u.get("known_as"), "bNumControls": u.get("bNumControls"),
                                           "bmControls": u.get("bmControls")})
    return out


def control_spec(name: str) -> tuple[str, int, int, bool, str] | None:
    """('ct'|'pu', selector, size, signed, kind) for a control name."""
    if name in CT_CONTROLS:
        return ("ct",) + CT_CONTROLS[name]
    if name in PU_CONTROLS:
        return ("pu",) + PU_CONTROLS[name]
    return None


class UVCControls:
    """Requests against one camera's VideoControl interface through a transport."""

    def __init__(self, transport: Any, entities: dict, timeout_ms: int = 500, log: list | None = None):
        self.t = transport
        self.ent = entities
        self.timeout_ms = int(timeout_ms)
        self.log = log if log is not None else []

    # --- addressing
    def _addr(self, name: str) -> tuple[int, int, int, bool, str] | None:
        spec = control_spec(name)
        if spec is None:
            return None
        unit, sel, size, signed, kind = spec
        e = self.ent.get("camera_terminal" if unit == "ct" else "processing_unit")
        if not e or e.get("id") is None or self.ent.get("vc_interface") is None:
            return None
        return sel, (int(e["id"]) << 8) | int(self.ent["vc_interface"]), size, signed, kind

    def _get(self, req: int, sel: int, windex: int, length: int) -> dict:
        t0 = time.perf_counter()
        try:
            rc, data = self.t.ctrl_in(RT_GET_IF, req, sel << 8, windex, length, self.timeout_ms)
        except Exception as e:  # transport bug or crash-adjacent failure: record, never raise
            rc, data = f"exception: {e!r}", b""
        ms = round((time.perf_counter() - t0) * 1000, 3)
        rec = {"req": REQ_NAMES.get(req, hex(req)), "rc": rc if not isinstance(rc, str) else None,
               "rc_name": rc_name(rc), "rc_hex": rc_hex(rc), "ms": ms, "data": (data or b"").hex()}
        self.log.append({"op": "get", "sel": sel, "wIndex": windex, **rec})
        return {**rec, "_bytes": data or b"", "_ok": rc == 0}

    def read(self, name: str, requests: tuple[int, ...] = (GET_INFO, GET_MIN, GET_MAX, GET_RES, GET_DEF, GET_CUR)) -> dict:
        """All GET_* for one control. Returns {name, supported_by_addr, info, min, max, res, def, cur, calls}."""
        a = self._addr(name)
        out: dict[str, Any] = {"name": name, "addressable": a is not None, "calls": []}
        if a is None:
            out["error"] = "no entity id / VC interface for this control"
            return out
        sel, windex, size, signed, kind = a
        out.update(selector=sel, wIndex=windex, size=size, signed=signed, kind=kind)
        keymap = {GET_INFO: "info", GET_MIN: "min", GET_MAX: "max", GET_RES: "res", GET_DEF: "def", GET_CUR: "cur"}
        for req in requests:
            length = 1 if req == GET_INFO else size
            r = self._get(req, sel, windex, length)
            out["calls"].append({k: v for k, v in r.items() if not k.startswith("_")})
            if r["_ok"]:
                if req == GET_INFO:
                    out["info"] = decode_info(r["_bytes"][0] if r["_bytes"] else None)
                else:
                    out[keymap[req]] = decode(r["_bytes"], size, signed) if kind != "multi" else r["_bytes"].hex()
            else:
                out[keymap[req]] = None
                if req == GET_INFO and r.get("rc_name") in ("kIOReturnNotResponding", "kIOUSBTransactionTimeout",
                                                            "LIBUSB_ERROR_TIMEOUT", "LIBUSB_ERROR_NO_DEVICE",
                                                            "kIOReturnNoDevice", "kIOReturnTimeout"):
                    out["aborted"] = f"GET_INFO failed with {r['rc_name']}; remaining requests skipped"
                    break
        out["ok"] = all(c["rc"] == 0 for c in out["calls"]) and bool(out["calls"])
        if kind == "bitmap" and out.get("res") is not None:
            out["modes_supported"] = [v for k, v in AE_MODE_BITS.items() if out["res"] & k]
        return out

    def get_cur(self, name: str) -> dict:
        a = self._addr(name)
        if a is None:
            return {"name": name, "ok": False, "error": "not addressable"}
        sel, windex, size, signed, kind = a
        r = self._get(GET_CUR, sel, windex, size)
        return {"name": name, "ok": r["_ok"], "value": decode(r["_bytes"], size, signed) if r["_ok"] else None,
                **{k: v for k, v in r.items() if not k.startswith("_")}}

    def set_cur(self, name: str, value: int, readback: bool = True) -> dict:
        a = self._addr(name)
        if a is None:
            return {"name": name, "ok": False, "error": "not addressable"}
        sel, windex, size, signed, kind = a
        t0 = time.perf_counter()
        try:
            rc = self.t.ctrl_out(RT_SET_IF, SET_CUR, sel << 8, windex, encode(value, size, signed), self.timeout_ms)
        except Exception as e:
            rc = f"exception: {e!r}"
        ms = round((time.perf_counter() - t0) * 1000, 3)
        self.log.append({"op": "set", "sel": sel, "wIndex": windex, "value": value, "rc": rc, "rc_name": rc_name(rc), "ms": ms})
        out = {"name": name, "value": value, "rc": rc if not isinstance(rc, str) else None, "rc_name": rc_name(rc),
               "rc_hex": rc_hex(rc), "ms": ms, "ok": rc == 0}
        if readback:
            rb = self.get_cur(name)
            out["readback"] = rb.get("value")
            out["readback_rc_name"] = rb.get("rc_name")
            out["readback_matches"] = (rb.get("value") == value) if rb.get("ok") else None
        return out

    # --- streaming-interface reads (read-only)
    def get_interface(self, vs_interface: int) -> dict:
        t0 = time.perf_counter()
        try:
            rc, data = self.t.ctrl_in(RT_STD_GET_IF, STD_GET_INTERFACE, 0, int(vs_interface), 1, self.timeout_ms)
        except Exception as e:
            rc, data = f"exception: {e!r}", b""
        return {"interface": vs_interface, "rc": rc if not isinstance(rc, str) else None, "rc_name": rc_name(rc),
                "alt": data[0] if rc == 0 and data else None, "ms": round((time.perf_counter() - t0) * 1000, 3)}

    def get_commit(self, vs_interface: int, bcd_uvc: str | None = None) -> dict:
        """VS_COMMIT_CONTROL GET_CUR: what the streaming interface committed (format/frame index, interval,
        dwMaxPayloadTransferSize) - proves the wire format (macos.md MX1)."""
        length = 26 if (bcd_uvc or "1.00") in ("1.00", "1.0") else (48 if (bcd_uvc or "").startswith("1.5") else 34)
        t0 = time.perf_counter()
        try:
            rc, data = self.t.ctrl_in(RT_GET_IF, GET_CUR, VS_COMMIT_CONTROL << 8, int(vs_interface), length, self.timeout_ms)
        except Exception as e:
            rc, data = f"exception: {e!r}", b""
        out = {"interface": vs_interface, "rc": rc if not isinstance(rc, str) else None, "rc_name": rc_name(rc),
               "ms": round((time.perf_counter() - t0) * 1000, 3), "raw": (data or b"").hex()}
        if rc == 0 and data and len(data) >= 26:
            out.update(parse_probe_commit(data))
        return out


def parse_probe_commit(d: bytes) -> dict:
    bmHint, fmt, frame, interval, keyrate, pframe, cq, wdsz, delay, maxframe, maxpayload = \
        struct.unpack_from("<HBBIHHHHHII", d, 0)
    return {"bmHint": bmHint, "bFormatIndex": fmt, "bFrameIndex": frame, "dwFrameInterval": interval,
            "fps": round(1e7 / interval, 3) if interval else None, "dwMaxVideoFrameSize": maxframe,
            "dwMaxPayloadTransferSize": maxpayload}


def pick_values(info: dict, n: int = 3) -> list[int]:
    """n in-range values spread over [min, max], snapped to res, for an effect test."""
    lo, hi, res = info.get("min"), info.get("max"), info.get("res") or 1
    if lo is None or hi is None or hi <= lo:
        return []
    res = max(1, int(res))
    vals = []
    for i in range(n):
        v = lo + (hi - lo) * (i + 0.5) / n if n > 1 else (lo + hi) / 2
        v = lo + round((v - lo) / res) * res
        vals.append(int(min(hi, max(lo, v))))
    out = []
    for v in vals:
        if v not in out:
            out.append(v)
    return out


def exposure_values(info: dict) -> list[int]:
    """Exposure values (100 us units) for the luma test: geometric spread between min and min(max, 1/fps limit)."""
    lo, hi = info.get("min"), info.get("max")
    if lo is None or hi is None or hi <= lo:
        return []
    lo = max(1, int(lo))
    top = min(int(hi), 333)  # stay at or below 33 ms so the frame rate is not forced down at 30 fps
    if top <= lo:
        top = int(hi)
    vals = sorted({lo, int(round((lo * top) ** 0.5)), top})
    return vals
