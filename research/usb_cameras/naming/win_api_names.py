# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "opencv-contrib-python==4.12.0.88",
#   "cv2-enumerate-cameras==1.4.0",
#   "imageio-ffmpeg==0.5.1",
# ]
# ///
"""Windows: record the device names/paths each capture API exposes and map them back to USB identity.

Run (from repo root; enumeration only, no stream is opened, but hold the lock anyway):
    uv run --script research/usb_cameras/tools/camlock.py -- uv run --script research/usb_cameras/naming/win_api_names.py

Writes results/windows/<hostname>/naming/api_names.json with, per API:
  * Media Foundation   MFEnumDeviceSources(VIDCAP): friendly name + MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_SYMBOLIC_LINK
                       (enumeration order == OpenCV CAP_MSMF index)
  * DirectShow         ICreateDevEnum(CLSID_VideoInputDeviceCategory): FriendlyName, DevicePath, moniker display name
                       (enumeration order == OpenCV CAP_DSHOW index; display name with ':'->'_' == FFmpeg "Alternative name")
  * FFmpeg dshow       `ffmpeg -list_devices true -f dshow -i dummy` (imageio-ffmpeg build) raw lines + parsed names
  * OpenCV             cv2_enumerate_cameras.enumerate_cameras(CAP_MSMF / CAP_DSHOW): index, name, path, vid, pid
and, for every entry, the USB device it resolves to (composite instance id, serial, LocationPaths) by parsing the
symbolic link into a device instance id and matching it against win_identity_dump.collect().
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import datetime as _dt
import json
import platform
import re
import socket
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import win_identity_dump as wid  # noqa: E402

ole32 = ctypes.WinDLL("ole32")
oleaut32 = ctypes.WinDLL("oleaut32")
mfplat = ctypes.WinDLL("mfplat")
mf = ctypes.WinDLL("mf")
GUID = wid.GUID
HRESULT = ctypes.c_long


def _vcall(obj: ctypes.c_void_p, index: int, restype, *args_types):
    """Return a callable for COM vtable slot `index` of interface pointer obj."""
    vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    proto = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *args_types)
    fn = proto(vtbl[index])
    return lambda *a: fn(obj, *a)


def _release(obj):
    if obj:
        _vcall(obj, 2, wt.ULONG)()


def _check(hr: int, what: str):
    if hr < 0:
        raise OSError(f"{what} failed hr=0x{hr & 0xFFFFFFFF:08x}")


# ---------------------------------------------------------------- Media Foundation
MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE = GUID.from_str("c60ac5fe-252a-478f-a0ef-bc8fa5f7cad3")
MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID = GUID.from_str("8ac3587a-4ae7-42d8-99e0-0a6013eef90f")
MF_DEVSOURCE_ATTRIBUTE_FRIENDLY_NAME = GUID.from_str("60d0e559-52f8-4fa2-bbce-acdb34a8ec01")
MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_SYMBOLIC_LINK = GUID.from_str("58f0aad8-22bf-4f8a-bb3d-d2c4978c6e2f")


def _mf_string(act, key: GUID) -> str | None:
    p = ctypes.c_wchar_p()
    n = wt.UINT()
    hr = _vcall(act, 13, HRESULT, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_wchar_p), ctypes.POINTER(wt.UINT))(
        ctypes.byref(key), ctypes.byref(p), ctypes.byref(n))
    if hr < 0:
        return None
    s = p.value
    ole32.CoTaskMemFree(p)
    return s


def enumerate_mf() -> list[dict]:
    _check(mfplat.MFStartup(0x00020070, 0), "MFStartup")
    attrs = ctypes.c_void_p()
    _check(mfplat.MFCreateAttributes(ctypes.byref(attrs), 1), "MFCreateAttributes")
    _check(_vcall(attrs, 24, HRESULT, ctypes.POINTER(GUID), ctypes.POINTER(GUID))(
        ctypes.byref(MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE), ctypes.byref(MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID)),
        "IMFAttributes::SetGUID")
    arr = ctypes.POINTER(ctypes.c_void_p)()
    count = wt.UINT()
    _check(mf.MFEnumDeviceSources(attrs, ctypes.byref(arr), ctypes.byref(count)), "MFEnumDeviceSources")
    out = []
    for i in range(count.value):
        act = ctypes.c_void_p(arr[i])
        out.append(dict(index=i, friendly_name=_mf_string(act, MF_DEVSOURCE_ATTRIBUTE_FRIENDLY_NAME),
                        symbolic_link=_mf_string(act, MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_SYMBOLIC_LINK)))
        _release(act)
    ole32.CoTaskMemFree(arr)
    _release(attrs)
    mfplat.MFShutdown()
    return out


# ---------------------------------------------------------------- DirectShow
CLSID_SystemDeviceEnum = GUID.from_str("62be5d10-60eb-11d0-bd3b-00a0c911ce86")
IID_ICreateDevEnum = GUID.from_str("29840822-5b84-11d0-bd3b-00a0c911ce86")
CLSID_VideoInputDeviceCategory = GUID.from_str("860bb310-5d01-11d0-bd3b-00a0c911ce86")
IID_IPropertyBag = GUID.from_str("55272a00-42cb-11ce-8135-00aa004bb851")


class VARIANT(ctypes.Structure):
    _fields_ = [("vt", wt.USHORT), ("r1", wt.WORD), ("r2", wt.WORD), ("r3", wt.WORD),
                ("val", ctypes.c_void_p), ("pad", ctypes.c_void_p)]


def _bag_read(bag, name: str) -> str | None:
    v = VARIANT()
    hr = _vcall(bag, 3, HRESULT, wt.LPCWSTR, ctypes.POINTER(VARIANT), ctypes.c_void_p)(name, ctypes.byref(v), None)
    if hr < 0:
        return None
    s = ctypes.wstring_at(v.val) if v.vt == 8 and v.val else None  # VT_BSTR
    oleaut32.VariantClear(ctypes.byref(v))
    return s


def enumerate_dshow() -> list[dict]:
    dev_enum = ctypes.c_void_p()
    _check(ole32.CoCreateInstance(ctypes.byref(CLSID_SystemDeviceEnum), None, 1, ctypes.byref(IID_ICreateDevEnum),
                                  ctypes.byref(dev_enum)), "CoCreateInstance(SystemDeviceEnum)")
    en = ctypes.c_void_p()
    hr = _vcall(dev_enum, 3, HRESULT, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p), wt.DWORD)(
        ctypes.byref(CLSID_VideoInputDeviceCategory), ctypes.byref(en), 0)
    out = []
    if hr == 0 and en:
        i = 0
        while True:
            mon = ctypes.c_void_p()
            fetched = wt.ULONG()
            if _vcall(en, 3, HRESULT, wt.ULONG, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wt.ULONG))(
                    1, ctypes.byref(mon), ctypes.byref(fetched)) != 0 or not fetched.value:
                break
            ctx = ctypes.c_void_p()
            ole32.CreateBindCtx(0, ctypes.byref(ctx))
            disp = ctypes.c_wchar_p()
            _vcall(mon, 20, HRESULT, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_wchar_p))(
                ctx, None, ctypes.byref(disp))
            display = disp.value
            ole32.CoTaskMemFree(disp)
            bag = ctypes.c_void_p()
            _vcall(mon, 9, HRESULT, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))(
                ctx, None, ctypes.byref(IID_IPropertyBag), ctypes.byref(bag))
            entry = dict(index=i, moniker_display_name=display,
                         ffmpeg_alternative_name=display.replace(":", "_") if display else None)
            if bag:
                entry.update(friendly_name=_bag_read(bag, "FriendlyName"), device_path=_bag_read(bag, "DevicePath"),
                             clsid=_bag_read(bag, "CLSID"))
                _release(bag)
            out.append(entry)
            _release(ctx)
            _release(mon)
            i += 1
        _release(en)
    _release(dev_enum)
    return out


# ---------------------------------------------------------------- FFmpeg dshow
def enumerate_ffmpeg() -> dict:
    import imageio_ffmpeg
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    r = subprocess.run([exe, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                       capture_output=True, text=True, errors="replace", timeout=60)
    lines = [l for l in r.stderr.splitlines() if "dshow" in l]
    devices, cur, section = [], None, None
    for l in lines:
        if "DirectShow video devices" in l:
            section = "video"
            continue
        if "DirectShow audio devices" in l:
            section = "audio"
            continue
        # FFmpeg >= 5 prints '"name" (video)'; 4.x prints '"name"' under a section header
        m = re.search(r'\]\s+"(.+)"(?:\s+\((video|audio|none)\))?\s*$', l)
        if m and "Alternative name" not in l:
            cur = dict(name=m.group(1), kind=m.group(2) or section, alternative_name=None)
            devices.append(cur)
            continue
        m = re.search(r'Alternative name\s+"(.+)"', l)
        if m and cur is not None:
            cur["alternative_name"] = m.group(1)
    ver = subprocess.run([exe, "-version"], capture_output=True, text=True).stdout.splitlines()[0]
    return dict(ffmpeg_exe=exe, ffmpeg_version=ver, raw_lines=lines, devices=devices)


# ---------------------------------------------------------------- OpenCV
def enumerate_opencv() -> dict:
    import cv2
    from cv2_enumerate_cameras import enumerate_cameras
    out = dict(cv2_version=cv2.__version__)
    for name, api in (("CAP_MSMF", cv2.CAP_MSMF), ("CAP_DSHOW", cv2.CAP_DSHOW)):
        out[name] = [dict(index=c.index, name=c.name, path=c.path, vid=c.vid, pid=c.pid, backend=c.backend)
                     for c in enumerate_cameras(api)]
    return out


# ---------------------------------------------------------------- mapping
def link_to_instance_id(link: str | None) -> str | None:
    if not link:
        return None
    s = link
    s = re.sub(r"^@device[:_]pnp[:_]", "", s, flags=re.I)
    s = re.sub(r"^\\\\\?\\", "", s)
    s = s.split("#{")[0]
    return s.replace("#", "\\").upper()


def api_identity_fields(cams: list[dict]) -> dict[str, dict]:
    """Per composite instance id: the MF / DirectShow index, name and path (stdlib-only, used in snapshots)."""
    ole32.CoInitializeEx(None, 0)
    try:
        mfl = enumerate_mf()
    except Exception as e:  # noqa: BLE001
        mfl = [dict(index=-1, error=repr(e))]
    try:
        dsl = enumerate_dshow()
    except Exception as e:  # noqa: BLE001
        dsl = [dict(index=-1, error=repr(e))]
    out = {}
    for cam in cams:
        vf = ((cam.get("video_function") or {}).get("instance_id") or "").upper()
        m = next((e for e in mfl if link_to_instance_id(e.get("symbolic_link")) == vf), {})
        d = next((e for e in dsl if link_to_instance_id(e.get("device_path") or e.get("moniker_display_name")) == vf), {})
        out[cam["usb_device"]["instance_id"]] = dict(
            mf_index=m.get("index"), mf_friendly_name=m.get("friendly_name"), mf_symbolic_link=m.get("symbolic_link"),
            dshow_index=d.get("index"), dshow_friendly_name=d.get("friendly_name"),
            ffmpeg_dshow_alternative_name=d.get("ffmpeg_alternative_name"),
            mf_device_count=len(mfl), dshow_device_count=len(dsl))
    return out


def main() -> int:
    import argparse
    import os
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="default results/windows/<hostname>/naming (overwrites api_names.json there)")
    ap.add_argument("--exclude-vidpid", action="append", default=[],
                    help="vvvv:pppp: no hub IOCTL / descriptor read for these devices (they still appear in the "
                         "MF/DShow/FFmpeg/OpenCV enumerations, which open no stream)")
    a = ap.parse_args()
    excl = wid.excluded_vidpids(a.exclude_vidpid)
    if excl:
        os.environ[wid.EXCLUDE_ENV] = ",".join(sorted(excl))
    started = _dt.datetime.now(_dt.timezone.utc).isoformat()
    ole32.CoInitializeEx(None, 0)  # COINIT_MULTITHREADED
    cams = wid.collect(read_descriptors=True, exclude=excl)
    func_map = {}
    for cam in cams:
        fi = wid.flat_identity(cam)
        usb = dict(composite_instance_id=fi["composite_instance_id"], usb_serial=fi["usb_serial"], vid=fi["vid"],
                   pid=fi["pid"], product=fi["usb_product"], location_paths=fi["location_paths"])
        for f in cam["functions"]:
            func_map[f["instance_id"].upper()] = dict(usb, function_instance_id=f["instance_id"])

    def resolve(link):
        iid = link_to_instance_id(link)
        return dict(parsed_instance_id=iid, usb=func_map.get(iid) if iid else None)

    res: dict = {}
    for name, fn in (("media_foundation", enumerate_mf), ("directshow", enumerate_dshow)):
        try:
            entries = fn()
            for e in entries:
                e["resolves_to"] = resolve(e.get("symbolic_link") or e.get("device_path") or e.get("moniker_display_name"))
            res[name] = entries
        except Exception as e:  # noqa: BLE001
            res[name] = {"error": repr(e)}
    try:
        ff = enumerate_ffmpeg()
        for d in ff["devices"]:
            d["resolves_to"] = resolve(d.get("alternative_name"))
        res["ffmpeg_dshow"] = ff
    except Exception as e:  # noqa: BLE001
        res["ffmpeg_dshow"] = {"error": repr(e)}
    try:
        cv = enumerate_opencv()
        for k in ("CAP_MSMF", "CAP_DSHOW"):
            for c in cv[k]:
                c["resolves_to"] = resolve(c["path"])
        res["opencv"] = cv
    except Exception as e:  # noqa: BLE001
        res["opencv"] = {"error": repr(e)}
    # cross check: does every API's ordering/name agree?
    summary = []
    for cam in cams:
        fi = wid.flat_identity(cam)
        vf = (fi["video_function_instance_id"] or "").upper()
        row = dict(product=fi["usb_product"], composite_instance_id=fi["composite_instance_id"], usb_serial=fi["usb_serial"])
        mfe = [e for e in res.get("media_foundation", []) if isinstance(e, dict) and (e["resolves_to"]["parsed_instance_id"] or "") == vf]
        row["mf_index"] = [e["index"] for e in mfe]
        row["mf_symbolic_link"] = [e["symbolic_link"] for e in mfe]
        dse = [e for e in res.get("directshow", []) if isinstance(e, dict) and (e["resolves_to"]["parsed_instance_id"] or "") == vf]
        row["dshow_index"] = [e["index"] for e in dse]
        row["dshow_friendly_name"] = [e.get("friendly_name") for e in dse]
        row["ffmpeg_alternative_name"] = [d["alternative_name"] for d in res.get("ffmpeg_dshow", {}).get("devices", [])
                                          if (d["resolves_to"]["parsed_instance_id"] or "") == vf]
        for k in ("CAP_MSMF", "CAP_DSHOW"):
            row[f"opencv_{k}"] = [dict(index=c["index"], name=c["name"], path=c["path"])
                                  for c in res.get("opencv", {}).get(k, []) if (c["resolves_to"]["parsed_instance_id"] or "") == vf]
        summary.append(row)
    out = dict(test="naming.win_api_names", platform="windows", hostname=socket.gethostname(), utc_started=started,
               command=" ".join([Path(sys.executable).name] + sys.argv),
               environment=dict(os=platform.platform(), python=sys.version.split()[0]),
               cameras=[wid.flat_identity(c) for c in cams], apis=res, mapping=summary)
    if excl:
        out["excluded_vidpid"] = sorted(excl)
        out["excluded_instance_ids"] = list(wid.EXCLUDED)
    od = a.out_dir or wid.default_out_dir()
    od.mkdir(parents=True, exist_ok=True)
    (od / "api_names.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    (od / "api_names_history").mkdir(exist_ok=True)  # keep every run: enumeration order changes are evidence
    (od / "api_names_history" / f"api_names_{started[:19].replace(':', '')}Z.json").write_text(
        json.dumps(out, indent=1, default=str), encoding="utf-8")
    for r in summary:
        print(json.dumps(r, indent=1))
    print("wrote", od / "api_names.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
