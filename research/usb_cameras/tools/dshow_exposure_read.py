# /// script
# requires-python = ">=3.10"
# dependencies = ["comtypes"]
# ///
"""Read (never set) exposure/gain state of selected cameras through DirectShow, for night-run context.

Binds ONLY the capture filters whose DevicePath contains one of the --vidpid substrings (other devices
are enumerated by property bag only and never bound). No streaming. Reads:
  IAMCameraControl  Exposure (property 4): value (log2 seconds), flags (1=auto, 2=manual), range
  IAMVideoProcAmp   Brightness (0), Gain (9), BacklightCompensation (8): value, flags
UVC note: in auto mode some cameras report the last AE-chosen exposure, some the default; treat the
value as indicative only.

RUN (shared Windows machine):
  uv run --script research/usb_cameras/tools/camlock.py -- uv run --script research/usb_cameras/tools/dshow_exposure_read.py \
      --vidpid vid_046d&pid_085c --vidpid vid_046d&pid_0843 --vidpid vid_4c4a&pid_4a55 --out <file.json>
"""
from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import json
import socket
import sys
from ctypes import HRESULT, POINTER, byref, c_long
from pathlib import Path

import comtypes
import comtypes.client
from comtypes import COMMETHOD, GUID, IUnknown
from comtypes.persist import IPropertyBag

CLSID_SystemDeviceEnum = GUID("{62BE5D10-60EB-11d0-BD3B-00A0C911CE86}")
CLSID_VideoInputDeviceCategory = GUID("{860BB310-5D01-11d0-BD3B-00A0C911CE86}")


class IEnumMoniker(IUnknown):
    _iid_ = GUID("{00000102-0000-0000-C000-000000000046}")


class IMoniker(IUnknown):
    _iid_ = GUID("{0000000f-0000-0000-C000-000000000046}")


IEnumMoniker._methods_ = [
    COMMETHOD([], HRESULT, "Next", (["in"], ctypes.c_ulong, "celt"),
              (["out"], POINTER(POINTER(IMoniker)), "rgelt"), (["out"], POINTER(ctypes.c_ulong), "pceltFetched")),
]
# IMoniker vtable: IPersist(GetClassID) IPersistStream(IsDirty, Load, Save, GetSizeMax) then BindToObject, BindToStorage
IMoniker._methods_ = [
    COMMETHOD([], HRESULT, "GetClassID", (["out"], POINTER(GUID), "pClassID")),
    COMMETHOD([], HRESULT, "IsDirty"),
    COMMETHOD([], HRESULT, "Load", (["in"], ctypes.c_void_p, "pStm")),
    COMMETHOD([], HRESULT, "Save", (["in"], ctypes.c_void_p, "pStm"), (["in"], ctypes.c_int, "fClearDirty")),
    COMMETHOD([], HRESULT, "GetSizeMax", (["out"], POINTER(ctypes.c_ulonglong), "pcbSize")),
    COMMETHOD([], HRESULT, "BindToObject", (["in"], ctypes.c_void_p, "pbc"), (["in"], ctypes.c_void_p, "pmkToLeft"),
              (["in"], POINTER(GUID), "riid"), (["out"], POINTER(POINTER(IUnknown)), "ppv")),
    COMMETHOD([], HRESULT, "BindToStorage", (["in"], ctypes.c_void_p, "pbc"), (["in"], ctypes.c_void_p, "pmkToLeft"),
              (["in"], POINTER(GUID), "riid"), (["out"], POINTER(POINTER(IUnknown)), "ppv")),
]


class ICreateDevEnum(IUnknown):
    _iid_ = GUID("{29840822-5B84-11D0-BD3B-00A0C911CE86}")
    _methods_ = [
        COMMETHOD([], HRESULT, "CreateClassEnumerator", (["in"], POINTER(GUID), "clsidDeviceClass"),
                  (["out"], POINTER(POINTER(IEnumMoniker)), "ppEnumMoniker"), (["in"], ctypes.c_ulong, "dwFlags")),
    ]


class IBaseFilter(IUnknown):
    _iid_ = GUID("{56a86895-0ad4-11ce-b03a-0020af0ba770}")


def _amctl(iid):
    class _I(IUnknown):
        _iid_ = GUID(iid)
        _methods_ = [
            COMMETHOD([], HRESULT, "GetRange", (["in"], c_long, "Property"), (["out"], POINTER(c_long), "pMin"),
                      (["out"], POINTER(c_long), "pMax"), (["out"], POINTER(c_long), "pSteppingDelta"),
                      (["out"], POINTER(c_long), "pDefault"), (["out"], POINTER(c_long), "pCapsFlags")),
            COMMETHOD([], HRESULT, "Set", (["in"], c_long, "Property"), (["in"], c_long, "lValue"), (["in"], c_long, "Flags")),
            COMMETHOD([], HRESULT, "Get", (["in"], c_long, "Property"), (["out"], POINTER(c_long), "lValue"),
                      (["out"], POINTER(c_long), "Flags")),
        ]
    return _I


IAMVideoProcAmp = _amctl("{C6E13360-30AC-11d0-A18C-00A0C9118956}")
IAMCameraControl = _amctl("{C6E13370-30AC-11d0-A18C-00A0C9118956}")
FLAGS = {1: "auto", 2: "manual"}


def read_prop(iface, prop):
    out = {}
    try:
        v, f = iface.Get(prop)
        out.update(value=v, flags=f, mode=FLAGS.get(f & 3, f))
    except Exception as e:  # noqa: BLE001
        out["get_error"] = repr(e)
    try:
        mn, mx, st, de, caps = iface.GetRange(prop)
        out["range"] = {"min": mn, "max": mx, "step": st, "default": de, "caps_flags": caps}
    except Exception as e:  # noqa: BLE001
        out["range_error"] = repr(e)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vidpid", action="append", required=True, help="DevicePath substring, e.g. vid_046d&pid_085c")
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", default="")
    a = ap.parse_args()
    comtypes.CoInitialize()
    dev_enum = comtypes.client.CreateObject(CLSID_SystemDeviceEnum, interface=ICreateDevEnum)
    em = dev_enum.CreateClassEnumerator(byref(CLSID_VideoInputDeviceCategory), 0)
    res = {"test": "dshow_exposure_read", "hostname": socket.gethostname(), "label": a.label,
           "utc": dt.datetime.now(dt.timezone.utc).isoformat(), "command": " ".join(["uv run --script"] + sys.argv),
           "allowlist": a.vidpid, "cameras": []}
    while True:
        try:
            mk, n = em.Next(1)
        except Exception:  # noqa: BLE001
            break
        if not n:
            break
        bag = mk.BindToStorage(None, None, byref(IPropertyBag._iid_)).QueryInterface(IPropertyBag)
        try:
            name = bag.Read("FriendlyName", pErrorLog=None)
        except Exception:  # noqa: BLE001
            name = None
        try:
            path = bag.Read("DevicePath", pErrorLog=None)
        except Exception:  # noqa: BLE001
            path = ""
        if not any(v.lower() in (path or "").lower() for v in a.vidpid):
            continue  # never bound
        cam = {"name": name, "device_path": path}
        try:
            flt = mk.BindToObject(None, None, byref(IBaseFilter._iid_))
            cc = flt.QueryInterface(IAMCameraControl)
            cam["exposure"] = read_prop(cc, 4)
            pa = flt.QueryInterface(IAMVideoProcAmp)
            cam["brightness"] = read_prop(pa, 0)
            cam["gain"] = read_prop(pa, 9)
            cam["backlight_compensation"] = read_prop(pa, 8)
            del cc, pa, flt
        except Exception as e:  # noqa: BLE001
            cam["error"] = repr(e)
        res["cameras"].append(cam)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
