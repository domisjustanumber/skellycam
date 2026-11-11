"""Pure-Python pieces of pymf: no COM, no ctypes calls, importable on any OS (the offline tests use this module).

Everything here mirrors a function of ``suite/windows/native/wincam.cpp`` so the two probes give the same answer
for the same bytes. The wincam function each one copies is named in its docstring.
"""
from __future__ import annotations

import math
import struct
from typing import Any, Iterable, Sequence

# ============================================================================================================ HRESULTs
E_FAIL = 0x80004005
E_NOINTERFACE = 0x80004002
E_NOTIMPL = 0x80004001
E_PROP_ID_UNSUPPORTED = 0x80070490
HR_DEVICE_NOT_CONNECTED = 0x8007048F
MF_E_INVALIDMEDIATYPE = 0xC00D36B4
MF_E_INVALIDSTREAMNUMBER = 0xC00D36B3
MF_E_NO_MORE_TYPES = 0xC00D36B9
MF_E_END_OF_STREAM = 0xC00D3E84
MF_E_SHUTDOWN = 0xC00D3E85
MF_E_INVALIDREQUEST = 0xC00D36B2
MF_E_HW_MFT_FAILED_START_STREAMING = 0xC00D3704
MF_E_VIDEO_RECORDING_DEVICE_INVALIDATED = 0xC00D3EA2
MF_E_VIDEO_RECORDING_DEVICE_PREEMPTED = 0xC00D3EA3
MF_E_REBOOT_REQUIRED = 0xC00D7167

#: names for HRESULTs, the same table as wincam's kHrNames (values from winerror.h / Mferror.h, SDK 10.0.22621)
HR_NAMES: dict[int, str] = {
    0x00000000: "S_OK", 0x00000001: "S_FALSE", E_FAIL: "E_FAIL", 0x80070057: "E_INVALIDARG",
    E_NOINTERFACE: "E_NOINTERFACE", E_NOTIMPL: "E_NOTIMPL", 0x80004003: "E_POINTER", 0x8007000E: "E_OUTOFMEMORY",
    0x8000FFFF: "E_UNEXPECTED", 0x80004004: "E_ABORT", 0x8000000A: "E_PENDING",
    0x80070005: "E_ACCESSDENIED",
    0x800718CF: "HRESULT_FROM_WIN32(6351) USB_INSUFFICIENT_BANDWIDTH",
    0x8007001F: "HRESULT_FROM_WIN32(ERROR_GEN_FAILURE)",
    0x80070015: "HRESULT_FROM_WIN32(ERROR_NOT_READY)",
    0x8007048F: "HRESULT_FROM_WIN32(ERROR_DEVICE_NOT_CONNECTED)",
    0x80070651: "HRESULT_FROM_WIN32(ERROR_DEVICE_REMOVED)",
    0x800701B1: "HRESULT_FROM_WIN32(ERROR_NO_SUCH_DEVICE)",
    0x8007045D: "HRESULT_FROM_WIN32(ERROR_IO_DEVICE)",
    0x800700AA: "HRESULT_FROM_WIN32(ERROR_BUSY)",
    0x80070964: "HRESULT_FROM_WIN32(ERROR_DEVICE_IN_USE)",
    0x80070079: "HRESULT_FROM_WIN32(ERROR_SEM_TIMEOUT)",
    0x800705B4: "HRESULT_FROM_WIN32(ERROR_TIMEOUT)",
    0x800705AA: "HRESULT_FROM_WIN32(ERROR_NO_SYSTEM_RESOURCES)",
    0x80070490: "HRESULT_FROM_WIN32(ERROR_NOT_FOUND) E_PROP_ID_UNSUPPORTED",
    0x80070492: "HRESULT_FROM_WIN32(ERROR_SET_NOT_FOUND) E_PROP_SET_UNSUPPORTED",
    0x80070002: "HRESULT_FROM_WIN32(ERROR_FILE_NOT_FOUND)",
    0x8007007A: "HRESULT_FROM_WIN32(ERROR_INSUFFICIENT_BUFFER)",
    0x800700EA: "HRESULT_FROM_WIN32(ERROR_MORE_DATA)",
    0x80070032: "HRESULT_FROM_WIN32(ERROR_NOT_SUPPORTED)",
    0xA00F4271: "CAMERA_APP_0xA00F4271_MEDIA_CAPTURE_FAILED",
    0xA00F4244: "CAMERA_APP_0xA00F4244_NO_CAMERA",
    0xA00F4243: "CAMERA_APP_0xA00F4243_CAMERA_IN_USE",
    MF_E_HW_MFT_FAILED_START_STREAMING: "MF_E_HW_MFT_FAILED_START_STREAMING",
    MF_E_VIDEO_RECORDING_DEVICE_INVALIDATED: "MF_E_VIDEO_RECORDING_DEVICE_INVALIDATED",
    MF_E_VIDEO_RECORDING_DEVICE_PREEMPTED: "MF_E_VIDEO_RECORDING_DEVICE_PREEMPTED",
    MF_E_REBOOT_REQUIRED: "MF_E_REBOOT_REQUIRED", MF_E_INVALIDMEDIATYPE: "MF_E_INVALIDMEDIATYPE",
    MF_E_INVALIDREQUEST: "MF_E_INVALIDREQUEST", MF_E_SHUTDOWN: "MF_E_SHUTDOWN", MF_E_NO_MORE_TYPES: "MF_E_NO_MORE_TYPES",
    MF_E_INVALIDSTREAMNUMBER: "MF_E_INVALIDSTREAMNUMBER", 0xC00D36B5: "MF_E_NOTACCEPTING", 0xC00D36BB: "MF_E_UNEXPECTED",
    0xC00D36E6: "MF_E_ATTRIBUTENOTFOUND", 0xC00D36D5: "MF_E_NOT_FOUND", 0xC00D36D6: "MF_E_NOT_AVAILABLE",
    0xC00D3E82: "MF_E_INVALID_STATE_TRANSITION", 0xC00DA7FD: "MF_E_HW_STREAM_NOT_CONNECTED",
    0xC00D4E24: "MF_E_VIDEO_DEVICE_LOCKED", 0xC00DABE4: "MF_E_CAPTURE_ENGINE_INVALID_OP",
    0xC00D5212: "MF_E_TOPO_CODEC_NOT_FOUND", 0xC00D6D60: "MF_E_TRANSFORM_TYPE_NOT_SET",
    0xC00D4A3E: "MF_E_SAMPLEALLOCATOR_EMPTY", 0xC00D3E9B: "MF_E_MEDIA_SOURCE_WRONGSTATE",
    0xC00D36C8: "MF_E_NO_SAMPLE_TIMESTAMP", 0xC00D36B6: "MF_E_NOT_INITIALIZED", 0xC00D36BD: "MF_E_INVALIDTYPE",
    0xC00DABE7: "MF_E_CAPTURE_SOURCE_NO_VIDEO_STREAM_PRESENT", 0xC00DABED: "MF_E_UNSUPPORTED_CAPTURE_DEVICE_PRESENT",
    0xC00D36DA: "MF_E_MULTIPLE_SUBSCRIBERS", 0xC00D3706: "MF_E_HARDWARE_DRM_UNSUPPORTED",
    0xC00D36B0: "MF_E_PLATFORM_NOT_INITIALIZED", 0xC00D36B1: "MF_E_BUFFERTOOSMALL", MF_E_END_OF_STREAM: "MF_E_END_OF_STREAM",
    # wincam's VFW_E_* entries are DirectShow-only; pymf has no DirectShow path, so they are left out
}


def u32(hr: int) -> int:
    return int(hr) & 0xFFFFFFFF


def failed(hr: int) -> bool:
    return bool(u32(hr) & 0x80000000)


def hr_hex(hr: int) -> str:
    return f"0x{u32(hr):08X}"


def hr_name(hr: int) -> str:
    return HR_NAMES.get(u32(hr), hr_hex(hr))


def error_class(hr: int | None, timed_out: bool) -> tuple[str, str]:
    """(class, reason) from the code alone; the same rules as wincam's error_class()."""
    h = None if hr is None else u32(hr)
    if timed_out:
        return "timeout", "call did not return within --timeout-ms"
    if h == 0x800718CF:
        return "bandwidth_certain", "usbvideo refused the isochronous bandwidth (Win32 6351)"
    if h == MF_E_HW_MFT_FAILED_START_STREAMING:
        return "in_use", "MF could not start streaming; usually another app holds the camera"
    if h == MF_E_VIDEO_RECORDING_DEVICE_PREEMPTED:
        return "in_use", "preempted by another application"
    if h in (0x80070964, 0x800700AA):
        return "in_use", "device busy / in use"
    if h == 0x80070005:
        return "permission", "access denied (privacy setting, or for DirectShow possibly bandwidth)"
    if h == 0x8007001F:
        return "device_error", "ERROR_GEN_FAILURE: device stopped answering (Kiyo signature)"
    if h == MF_E_REBOOT_REQUIRED:
        return "device_error", "devnode needs restart (DN_NEED_RESTART); ask for a replug"
    if h in (MF_E_VIDEO_RECORDING_DEVICE_INVALIDATED, 0x8007048F, 0x80070651, 0x800701B1):
        return "device_error", "device disappeared or re-enumerated"
    if h in (0x8007045D, 0x80070015):
        return "device_error", "I/O error / device not ready"
    if h == MF_E_SHUTDOWN:
        return "other", "object used after Shutdown (stale IMFActivate?)"
    if h == MF_E_INVALIDREQUEST:
        return "other", "MF_E_INVALIDREQUEST (Chromium treats as transient and retries)"
    return "other", ""


# ============================================================================================================ links
def norm_link(s: str | None) -> str:
    """wincam norm_link(): lower case, no ``\\\\?\\`` prefix, no ``#{interface class guid}`` segment (the reference
    string after it, e.g. ``\\global``, is kept). The MF symlink and the DS DevicePath of one interface agree."""
    t = str(s or "").lower()
    if t.startswith("\\\\?\\"):
        t = t[4:]
    p = t.find("#{")
    if p >= 0:
        e = t.find("}", p)
        t = t[:p] + ("" if e < 0 else t[e + 1:])
    return t


def parse_usb_ids(link: str | None) -> dict:
    """wincam parse_usb_ids(): vid, pid, mi (lower-case hex text) and the instance part of ``usb#vid..#<inst>#{guid}``."""
    low = str(link or "").lower()

    def grab(key: str, n: int) -> str | None:
        p = low.find(key)
        if p < 0 or p + len(key) + n > len(low):
            return None
        return low[p + len(key):p + len(key) + n]

    out = {"vid": grab("vid_", 4), "pid": grab("pid_", 4), "mi": grab("mi_", 2)}
    a = low.find("#")
    b = low.find("#", a + 1) if a >= 0 else -1
    c = low.find("#", b + 1) if b >= 0 else -1
    out["instance"] = low[b + 1:c] if (b >= 0 and c >= 0) else None
    return out


def match_device(want: str, cands: Sequence[tuple[str, str]]) -> tuple[int, list[dict]]:
    """wincam match_device(): ``cands`` = [(link, friendly name)]. Exact link (case-insensitive), else a substring of
    the link or of its normalized form, else a substring of the friendly name. Returns (index, []) on one match,
    (-1, []) for none, (-2, [matches]) when ambiguous."""
    w, wn = want.lower(), norm_link(want)
    for i, (link, _name) in enumerate(cands):
        if link.lower() == w:
            return i, []
    hits = [i for i, (link, _name) in enumerate(cands)
            if link and (w in link.lower() or (wn and wn in norm_link(link)))]
    if not hits:
        hits = [i for i, (_link, name) in enumerate(cands) if w in str(name or "").lower()]
    if len(hits) == 1:
        return hits[0], []
    if not hits:
        return -1, []
    return -2, [{"name": cands[i][1], "link": cands[i][0]} for i in hits]


# ============================================================================================================ GUIDs
FOURCC_BASE_SUFFIX = "-0000-0010-8000-00AA00389B71"

#: attribute / type GUID names: the same entries as wincam's kAttrNames (values from the SDK 10.0.22621 headers,
#: see sdk_10.0.22621_reference.json "guids"; the DirectShow ones from uuids.h / ksmedia.h)
GUID_NAMES: dict[str, str] = {
    "2939E7B8-A62E-4579-B674-D4073DFABBBA": "MF_DEVICESTREAM_STREAM_CATEGORY",
    "11BD5120-D124-446B-88E6-17060257FFF9": "MF_DEVICESTREAM_STREAM_ID",
    "1CB378E9-B279-41D4-AF97-34A243E68320": "MF_DEVICESTREAM_FRAMESERVER_SHARED",
    "17145FD1-1B2B-423C-8001-2B6833ED3588": "MF_DEVICESTREAM_ATTRIBUTE_FRAMESOURCE_TYPES",
    "048E6558-60C4-4173-BD5B-6A3CA2896AEE": "MF_DEVICESTREAM_EXTENSION_PLUGIN_CLSID",
    "1684CEBE-3175-4985-882C-0EFD3E8AC11E": "MF_DEVICESTREAM_MAX_FRAME_BUFFERS",
    "A7FFB865-E7B2-43B0-9F6F-9AF2A0E50FC0": "MF_DEVICESTREAM_IMAGE_STREAM",
    "03EEEC7E-D605-4576-8B29-6580B490D7D3": "MF_DEVICESTREAM_INDEPENDENT_IMAGE_STREAM",
    "1D180E34-538C-4FBB-A75A-859AF7D261A6": "MF_DEVICESTREAM_TAKEPHOTO_TRIGGER",
    "6D8B957E-7CF6-43F4-AF56-9C0E1E4FCBE1": "MF_DEVICESTREAM_REQUIRED_CAPABILITIES",
    "331AE85D-C0D3-49BA-83BA-82A12D63CDD6": "MF_DEVICESTREAM_REQUIRED_SDDL",
    "4F1B099D-D314-41E5-A781-7FEFAA4C501F": "MF_SD_STREAM_NAME",
    "00AF2180-BDC2-423C-ABCA-F503593BC121": "MF_SD_LANGUAGE",
    "48EBA18E-F8C9-4687-BF11-0A74C9F96A8F": "MF_MT_MAJOR_TYPE",
    "F7E34C9A-42E8-4714-B74B-CB29D72C35E5": "MF_MT_SUBTYPE",
    "1652C33D-D6B2-4012-B834-72030849A37D": "MF_MT_FRAME_SIZE",
    "C459A2E8-3D2C-4E44-B132-FEE5156C7BB0": "MF_MT_FRAME_RATE",
    "D2E7558C-DC1F-403F-9A72-D28BB1EB3B5E": "MF_MT_FRAME_RATE_RANGE_MIN",
    "E3371D41-B4CF-4A05-BD4E-20B88BB2C4D6": "MF_MT_FRAME_RATE_RANGE_MAX",
    "C6376A1E-8D0A-4027-BE45-6D9A0AD39BB6": "MF_MT_PIXEL_ASPECT_RATIO",
    "E2724BB8-E676-4806-B4B2-A8D6EFB44CCD": "MF_MT_INTERLACE_MODE",
    "C9173739-5E56-461C-B713-46FB995CB95F": "MF_MT_ALL_SAMPLES_INDEPENDENT",
    "DAD3AB78-1990-408B-BCE2-EBA673DACC10": "MF_MT_SAMPLE_SIZE",
    "B8EBEFAF-B718-4E04-B0A9-116775E3321B": "MF_MT_FIXED_SIZE_SAMPLES",
    "644B4E48-1E02-4516-B0EB-C01CA9D49AC6": "MF_MT_DEFAULT_STRIDE",
    "20332624-FB0D-4D9E-BD0D-CBF6786C102E": "MF_MT_AVG_BITRATE",
    "3AFD0CEE-18F2-4BA5-A110-8BEA502E1F92": "MF_MT_COMPRESSED",
    "3E23D450-2C75-4D25-A00E-B91670D12327": "MF_MT_YUV_MATRIX",
    "C21B8EE5-B956-4071-8DAF-325EDF5CAB11": "MF_MT_VIDEO_NOMINAL_RANGE",
    "DBFBE4D7-0740-4EE0-8192-850AB0E21935": "MF_MT_VIDEO_PRIMARIES",
    "5FB0FCE9-BE5C-4935-A811-EC838F8EED93": "MF_MT_TRANSFER_FUNCTION",
    "65DF2370-C773-4C33-AA64-843E068EFB0C": "MF_MT_VIDEO_CHROMA_SITING",
    "73D1072D-1870-4174-A063-29FF4FF6C11E": "MF_MT_AM_FORMAT_TYPE",
    "C380465D-2271-428C-9B83-ECEA3B4A85C1": "MF_MT_VIDEO_ROTATION",
    "47504A4D" + FOURCC_BASE_SUFFIX: "MFVideoFormat_MJPG",
    "3231564E" + FOURCC_BASE_SUFFIX: "MFVideoFormat_NV12",
    "32595559" + FOURCC_BASE_SUFFIX: "MFVideoFormat_YUY2",
    "34363248" + FOURCC_BASE_SUFFIX: "MFVideoFormat_H264",
    "3F40F4F0-5622-4FF8-B6D8-A17A584BEE5E": "MFVideoFormat_H264_ES",
    "43564548" + FOURCC_BASE_SUFFIX: "MFVideoFormat_HEVC",
    "73646976" + FOURCC_BASE_SUFFIX: "MFMediaType_Video",
    "05589F80-C356-11CE-BF01-00AA0055595A": "FORMAT_VideoInfo",
    "F72A76A0-EB0A-11D0-ACE4-0000C0CC16BA": "FORMAT_VideoInfo2",
    "FB6C4281-0353-11D1-905F-0000C0CC16BA": "PIN_CATEGORY_CAPTURE (PINNAME_VIDEO_CAPTURE)",
    "FB6C4282-0353-11D1-905F-0000C0CC16BA": "PIN_CATEGORY_PREVIEW (PINNAME_VIDEO_PREVIEW)",
    "FB6C428A-0353-11D1-905F-0000C0CC16BA": "PIN_CATEGORY_STILL (PINNAME_VIDEO_STILL)",
    "E436EB83-524F-11CE-9F53-0020AF0BA770": "MEDIATYPE_Stream",
    "2EBE23A8-FAF5-444A-A6A2-EB810880AB5D": "MFSampleExtension_CaptureMetadata",
    "9252077B-2680-49B9-AE02-B19075973B70": "MF_CAPTURE_METADATA_FRAME_RAWSTREAM",
    "8F3E35E7-2DCD-4887-8622-2A58BAA652B0": "MFSampleExtension_DeviceTimestamp",
}
MJPG_GUID = "47504A4D" + FOURCC_BASE_SUFFIX
NV12_GUID = "3231564E" + FOURCC_BASE_SUFFIX


def guid_name(g: str) -> str:
    """wincam guid_name(): the known name, else the GUID text."""
    return GUID_NAMES.get(g.upper(), g.upper())


def fourcc_of(d: int) -> str:
    """wincam fourcc_of(): four printable characters, else ``D3DFMT_<n>``."""
    cs = [(d >> (8 * i)) & 0xFF for i in range(4)]
    if any(c < 32 or c > 126 for c in cs):
        return f"D3DFMT_{d}"
    return "".join(chr(c) for c in cs)


def subtype_text(g: str) -> str:
    """wincam subtype_fourcc(): FOURCC-based subtypes print as the FOURCC, others by name or GUID."""
    gu = g.upper()
    if gu.endswith(FOURCC_BASE_SUFFIX):
        return fourcc_of(int(gu[:8], 16))
    return guid_name(gu)


def subtype_guid_text(s: str) -> str | None:
    """wincam subtype_guid(): MJPG / YUY2 / NV12 / H264 or any 4-character FOURCC -> the GUID text."""
    u = s.upper()
    if len(u) != 4:
        return None
    d = ord(u[0]) | (ord(u[1]) << 8) | (ord(u[2]) << 16) | (ord(u[3]) << 24)
    return f"{d:08X}" + FOURCC_BASE_SUFFIX


# ============================================================================================================ types
def fps_of(fn: int, fd: int) -> float:
    return fn / fd if fd else 0.0


def flag_types(types: list[dict]) -> list[dict]:
    """wincam formats_mf(): flag the NV12 type MF (Frame Server) inserts right before each MJPG type of the same size
    and rate. ``types`` are dicts with subtype_guid, width, height, fps_num, fps_den; adds ``flags``."""
    for k, x in enumerate(types):
        flags = []
        nxt = types[k + 1] if k + 1 < len(types) else None
        if (x.get("subtype_guid", "").upper() == NV12_GUID and nxt is not None
                and nxt.get("subtype_guid", "").upper() == MJPG_GUID
                and (nxt.get("width"), nxt.get("height"), nxt.get("fps_num"), nxt.get("fps_den"))
                == (x.get("width"), x.get("height"), x.get("fps_num"), x.get("fps_den"))):
            flags.append("nv12_immediately_before_same_mode_mjpg:likely_mf_synthesized_decode")
        x["flags"] = flags
    return types


def subtype_counts(types: Iterable[dict]) -> dict:
    out: dict[str, int] = {}
    for x in types:
        out[x["subtype"]] = out.get(x["subtype"], 0) + 1
    return dict(sorted(out.items()))


def mjpg_sizes(types: Iterable[dict]) -> list[dict]:
    """wincam: de-duplicated MJPG sizes in first-seen order, each with its list of rates."""
    modes: list[dict] = []
    for x in types:
        if x.get("subtype_guid", "").upper() != MJPG_GUID:
            continue
        hit = next((m for m in modes if (m["width"], m["height"]) == (x["width"], x["height"])), None)
        f = fps_of(x["fps_num"], x["fps_den"])
        if hit is None:
            modes.append({"width": x["width"], "height": x["height"], "fps": [f]})
        else:
            hit["fps"].append(f)
    return modes


def select_native_type(types: Sequence[dict], subtype_guid: str, w: int, h: int, fps: float
                       ) -> tuple[int | None, list[str]]:
    """wincam open_session() type choice: exact subtype, exact size, the rate nearest ``fps`` within 0.5 fps (the first
    of equally near rates wins). Never the first match: MF lists a synthesized NV12 right before each MJPG type.
    ``types`` are dicts with type_index, subtype_guid, width, height, fps_num, fps_den. Returns (type_index or None,
    candidate rates at this size as "num/den")."""
    best, best_err, cands = None, 1e9, []
    for t in types:
        if t.get("subtype_guid", "").upper() != subtype_guid.upper():
            continue
        f = fps_of(t["fps_num"], t["fps_den"])
        same = t["width"] == w and t["height"] == h
        if same:
            cands.append(f"{t['fps_num']}/{t['fps_den']}")
        e = abs(f - fps)
        if same and e < 0.5 and e < best_err:
            best, best_err = t["type_index"], e
    return best, cands


def mode_str(subtype: str, w: int, h: int, fps: float) -> str:
    """wincam mode_str(): ``MJPG 1280x720@30``."""
    return f"{subtype} {w}x{h}@{fps:g}"


# ============================================================================================================ JPEG
def jpeg_info(p: bytes) -> dict:
    """wincam jpeg_info(): SOI, EOI (last two bytes FFD9), eoi_trailing (0 = at the end, > 0 = bytes after the last
    FFD9 in the last 4 KB, -1 = none), SOFn width/height/marker from a marker walk that stops at SOS / EOI."""
    n = len(p)
    out = {"soi": n >= 2 and p[0] == 0xFF and p[1] == 0xD8, "eoi": False, "eoi_trailing": -1,
           "sof_w": -1, "sof_h": -1, "sof_marker": -1}
    if n >= 2 and p[n - 2] == 0xFF and p[n - 1] == 0xD9:
        out["eoi"], out["eoi_trailing"] = True, 0
    elif n > 2:
        lim = n - 4096 if n > 4096 else 0
        i = p.rfind(b"\xff\xd9", lim + 1, n)
        if i >= 0:
            out["eoi_trailing"] = n - (i + 2)
    if not out["soi"]:
        return out
    i = 2
    while i + 4 <= n:
        if p[i] != 0xFF:
            i += 1
            continue
        m = p[i + 1]
        if m == 0xFF:
            i += 1
            continue
        if m == 0xD8 or m == 0x01 or 0xD0 <= m <= 0xD7:
            i += 2
            continue
        ln = (p[i + 2] << 8) | p[i + 3]
        if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
            if i + 9 <= n:
                out["sof_h"] = (p[i + 5] << 8) | p[i + 6]
                out["sof_w"] = (p[i + 7] << 8) | p[i + 8]
                out["sof_marker"] = m
            break
        if m in (0xDA, 0xD9):
            break
        i += 2 + ln
    return out


# ============================================================================================================ UVC metadata
METADATA_ID_USB_VIDEO_HEADER = 2      # MetadataId_UsbVideoHeader (ksmedia.h 6306)
ITEMHEADER_SIZE = 8                   # KSCAMERA_METADATA_ITEMHEADER {ULONG MetadataId; ULONG Size} (ksmedia.h 6317)
UVC_TS_SIZE = 16                      # KSSTREAM_UVC_METADATATYPE_TIMESTAMP (ks.h ~2097): PTS, SCR, SCRToken, 2+4 rsvd
UVC_METADATA_SIZE = 2 * UVC_TS_SIZE   # KSSTREAM_UVC_METADATA {StartOfFrame, EndOfFrame} (ks.h 2115)


def parse_uvc_meta(p: bytes) -> dict:
    """wincam parse_uvc_meta() / timing/src/mf_uvc_timing.cpp: walk KSCAMERA_METADATA_ITEMHEADER items; the
    MetadataId_UsbVideoHeader item carries KSSTREAM_UVC_METADATA (first and last payload header of the frame):
    PTS, SCR STC and the 11-bit SOF counter of SCRToken. ``present`` False is normal without the tier-1 setting."""
    n = len(p)
    u = {"present": False, "pts": 0, "stc": 0, "sof": 0, "eof_pts": 0, "eof_stc": 0, "eof_sof": 0, "raw_len": n,
         "items": 0}
    off = 0
    while off + ITEMHEADER_SIZE <= n:
        mid, size = struct.unpack_from("<II", p, off)
        if size < ITEMHEADER_SIZE or off + size > n:
            break
        u["items"] += 1
        if mid == METADATA_ID_USB_VIDEO_HEADER and size >= ITEMHEADER_SIZE + UVC_METADATA_SIZE:
            b = off + ITEMHEADER_SIZE
            pts, stc, tok = struct.unpack_from("<IIH", p, b)
            epts, estc, etok = struct.unpack_from("<IIH", p, b + UVC_TS_SIZE)
            u.update(present=True, pts=pts, stc=stc, sof=tok & 0x7FF, eof_pts=epts, eof_stc=estc, eof_sof=etok & 0x7FF)
        off += size
    return u


def build_uvc_item(pts: int, stc: int, sof: int, eof_pts: int | None = None, eof_stc: int | None = None,
                   eof_sof: int | None = None, metadata_id: int = METADATA_ID_USB_VIDEO_HEADER,
                   extra: int = 0) -> bytes:
    """One KSCAMERA_METADATA_ITEMHEADER + KSSTREAM_UVC_METADATA item (for fixtures and the COM self-test)."""
    def ts(a, b, c):
        return struct.pack("<IIHHI", a & 0xFFFFFFFF, b & 0xFFFFFFFF, c & 0xFFFF, 0, 0)
    body = ts(pts, stc, sof) + ts(pts if eof_pts is None else eof_pts, stc if eof_stc is None else eof_stc,
                                  sof if eof_sof is None else eof_sof) + b"\0" * extra
    return struct.pack("<II", metadata_id, ITEMHEADER_SIZE + len(body)) + body


# ============================================================================================================ controls
#: wincam kCtls: (set, id, name); set 0 = PROPSETID_VIDCAP_CAMERACONTROL, 1 = PROPSETID_VIDCAP_VIDEOPROCAMP
CTLS: list[tuple[int, int, str]] = [
    (0, 0, "pan"), (0, 1, "tilt"), (0, 2, "roll"), (0, 3, "zoom"), (0, 4, "exposure"), (0, 5, "iris"), (0, 6, "focus"),
    (0, 7, "scanmode"), (0, 8, "privacy"), (0, 9, "pantilt"), (0, 10, "pan_relative"), (0, 11, "tilt_relative"),
    (0, 12, "roll_relative"), (0, 13, "zoom_relative"), (0, 14, "exposure_relative"), (0, 15, "iris_relative"),
    (0, 16, "focus_relative"), (0, 17, "pantilt_relative"), (0, 18, "focal_length"), (0, 19, "auto_exposure_priority"),
    (0, 20, "cc_id20"), (0, 21, "cc_id21"), (0, 22, "cc_id22"), (0, 23, "cc_id23"),
    (1, 0, "brightness"), (1, 1, "contrast"), (1, 2, "hue"), (1, 3, "saturation"), (1, 4, "sharpness"), (1, 5, "gamma"),
    (1, 6, "color_enable"), (1, 7, "white_balance"), (1, 8, "backlight_compensation"), (1, 9, "gain"),
    (1, 10, "digital_multiplier"), (1, 11, "digital_multiplier_limit"), (1, 12, "white_balance_component"),
    (1, 13, "powerline_frequency"), (1, 14, "pa_id14"), (1, 15, "pa_id15"),
]
CC_PANTILT, CC_PANTILT_RELATIVE, CC_FOCAL_LENGTH = 9, 17, 18
PA_WHITEBALANCE_COMPONENT = 12


def ctl_key(d: tuple[int, int, str]) -> str:
    return ("cc." if d[0] == 0 else "pa.") + d[2]


def find_ctl(s0: str) -> tuple[int, int, str] | None:
    """wincam find_ctl(): names, ``cc.<name>`` / ``pa.<name>``, ``cc<N>`` / ``pa<N>``, aliases wb / ae_priority."""
    s = s0.lower()
    st, rest = -1, s
    if s.startswith(("cc.", "pa.")):
        st, rest = (0 if s[0] == "c" else 1), s[3:]
    elif s.startswith(("cc", "pa")) and len(s) > 2 and s[2].isdigit():
        st, rest = (0 if s[0] == "c" else 1), s[2:]
    numeric = rest.isdigit()
    for c in CTLS:
        if st >= 0 and c[0] != st:
            continue
        if (st >= 0 and c[1] == int(rest)) if numeric else rest == c[2]:
            return c
    if not numeric and st < 0:
        if s in ("wb", "white_balance_temperature"):
            return find_ctl("pa.white_balance")
        if s == "ae_priority":
            return find_ctl("cc.auto_exposure_priority")
    return None


def flags_names(f: int) -> list[str]:
    out = []
    if f & 0x1:
        out.append("auto")
    if f & 0x2:
        out.append("manual")
    if f & 0x4:
        out.append("asynchronous")
    if f & 0x10:
        out.append("relative")
    return out


def parse_sets(spec: str, default_flags: int = 2) -> list[dict]:
    """wincam parse_sets(): ``id=value,id=value``; value = integer | auto | manual. Raises ValueError."""
    out = []
    for item in spec.split(","):
        if not item:
            continue
        if "=" not in item:
            raise ValueError(f"bad set item (need id=value): {item}")
        k, v = item.split("=", 1)
        d = find_ctl(k)
        if d is None:
            raise ValueError(f"unknown control id: {k}")
        v = v.lower()
        r = {"def": d, "raw_value": v, "is_auto": False, "is_manual_keep": False, "value": 0, "flags": default_flags}
        if v == "auto":
            r.update(is_auto=True, flags=1)
        elif v == "manual":
            r.update(is_manual_keep=True, flags=2)
        else:
            try:
                r["value"] = int(v, 10)
            except ValueError:
                raise ValueError(f"bad value: {item}") from None
        out.append(r)
    return out


#: KSPROPERTY_DESCRIPTION {AccessFlags, DescriptionSize, KSIDENTIFIER PropTypeSet (24), MembersListCount, Reserved}
KSDESC_SIZE = 40
#: KSPROPERTY_MEMBERSHEADER {MembersFlags, MembersSize, MembersCount, Flags}
KSMEMBERSHEADER_SIZE = 16
KSPROPERTY_MEMBER_RANGES, KSPROPERTY_MEMBER_STEPPEDRANGES, KSPROPERTY_MEMBER_VALUES = 1, 2, 3
KSPROPERTY_MEMBER_FLAG_DEFAULT = 1
KSSTEPPING_LONG_SIZE = 16   # {ULONG SteppingDelta; ULONG Reserved; {LONG SignedMinimum; LONG SignedMaximum}}


def ks_parse_members(buf: bytes, defaults: bool) -> dict:
    """wincam ks_parse_members(): the ranges (min/max/step) and the default value in a BASICSUPPORT / DEFAULTVALUES
    reply. Returns {ranges, has_range, min, max, step, has_default, default}."""
    r = {"ranges": [], "has_range": False, "min": 0, "max": 0, "step": 0, "has_default": False, "default": 0}
    if len(buf) < KSDESC_SIZE:
        return r
    _acc, dsize = struct.unpack_from("<II", buf, 0)
    lists = struct.unpack_from("<I", buf, 32)[0]
    p = KSDESC_SIZE
    end = min(len(buf), dsize if dsize else len(buf))
    for _k in range(lists):
        if p + KSMEMBERSHEADER_SIZE > end:
            break
        mflags, msize, mcount, hflags = struct.unpack_from("<IIII", buf, p)
        p += KSMEMBERSHEADER_SIZE
        body = msize * mcount
        if p + body > end:
            break
        if mflags in (KSPROPERTY_MEMBER_RANGES, KSPROPERTY_MEMBER_STEPPEDRANGES) and msize >= KSSTEPPING_LONG_SIZE \
                and mcount:
            step, _rsv, mn, mx = struct.unpack_from("<IIii", buf, p)
            r["ranges"].append({"min": mn, "max": mx, "step": step})
            if not r["has_range"] and not defaults:
                r.update(has_range=True, min=mn, max=mx, step=step)
        elif mflags == KSPROPERTY_MEMBER_VALUES and msize >= 4 and mcount:
            if (hflags & KSPROPERTY_MEMBER_FLAG_DEFAULT) and not r["has_default"]:
                r.update(has_default=True, default=struct.unpack_from("<i", buf, p)[0])
        p += body
    return r


def hrj(hr: int | None) -> str | None:
    """Per-call HRESULT for JSON: None when the call was not made (wincam's HR_NOT_CALLED)."""
    return None if hr is None else hr_hex(hr)


def hrnj(hr: int | None) -> str | None:
    return None if hr is None else hr_name(hr)


def new_ctl_read() -> dict:
    return {"supported": False, "via": "", "has_range": False, "has_default": False, "has_value": False,
            "has_value2": False, "mn": 0, "mx": 0, "step": 0, "def": 0, "caps": 0, "val": 0, "flags": 0, "val2": 0,
            "hr_iam_range": None, "hr_iam_get": None, "hr_ks_basic": None, "hr_ks_default": None, "hr_ks_get": None,
            "ks_ranges": [], "ks_has_range": False, "ks_has_default": False, "iam_range_degenerate": False,
            "ks_mn": 0, "ks_mx": 0, "ks_step": 0, "ks_def": 0, "ks_basic_hex": "", "ks_basic_len": 0,
            "ks_members_lists": 0}


def ctl_json(d: tuple[int, int, str], r: dict, ms: float) -> dict:
    """wincam ctl_json(): one control's JSON (same keys)."""
    e: dict[str, Any] = {"set": "camera_control" if d[0] == 0 else "video_proc_amp", "id": d[1], "name": d[2],
                         "key": ctl_key(d), "supported": r["supported"], "via": r["via"] or None}
    e["min"] = r["mn"] if r["has_range"] else None
    e["max"] = r["mx"] if r["has_range"] else None
    e["step"] = r["step"] if r["has_range"] else None
    e["default"] = r["def"] if r["has_default"] else None
    e["caps_flags"] = r["caps"] if r["supported"] else None
    e["caps_flags_names"] = flags_names(r["caps"]) if r["supported"] else None
    e["value"] = r["val"] if r["has_value"] else None
    e["flags"] = r["flags"] if r["has_value"] else None
    e["flags_names"] = flags_names(r["flags"]) if r["has_value"] else None
    if r["has_value2"]:
        e["value2"] = r["val2"]
    if r["ks_ranges"]:
        e["ks_ranges"] = r["ks_ranges"]
    kx: dict[str, Any] = {"hr": hrj(r["hr_ks_basic"]),
                          "min": r["ks_mn"] if r["ks_has_range"] else None,
                          "max": r["ks_mx"] if r["ks_has_range"] else None,
                          "step": r["ks_step"] if r["ks_has_range"] else None,
                          "default": r["ks_def"] if r["ks_has_default"] else None}
    if r["hr_ks_basic"] is not None and not failed(r["hr_ks_basic"]):
        kx["bytes"] = r["ks_basic_len"]
        kx["members_lists"] = r["ks_members_lists"]
    if r["ks_basic_hex"]:
        kx["raw_hex_head"] = r["ks_basic_hex"]
    e["ks_basicsupport"] = kx
    if r["via"] != "IKsControl" and r["supported"]:
        e["iam_ks_range_agree"] = (r["iam_range_degenerate"] or (r["ks_mn"], r["ks_mx"], r["ks_step"]) ==
                                   (r["mn"], r["mx"], r["step"])) if r["ks_has_range"] else None
    if r["iam_range_degenerate"]:
        e["note"] = ("IAM GetRange returned 0..0 step 0; range and default taken from "
                     "KSPROPERTY_TYPE_BASICSUPPORT/DEFAULTVALUES")
    names = ("iam_get_range", "iam_get", "ks_basicsupport", "ks_defaultvalues", "ks_get")
    keys = ("hr_iam_range", "hr_iam_get", "hr_ks_basic", "hr_ks_default", "hr_ks_get")
    e["hr"] = {n: hrj(r[k]) for n, k in zip(names, keys)}
    e["hr_names"] = {n: hrnj(r[k]) for n, k in zip(names, keys)}
    e["call_ms"] = ms
    if r["supported"]:
        e["get_ok"] = r["has_value"]
        gh = r["hr_ks_get"] if r["via"] == "IKsControl" else (r["hr_iam_get"] if r["hr_iam_get"] is not None
                                                                else r["hr_iam_range"])
        e["get_hr"] = hrj(gh)
        e["get_hr_name"] = hrnj(gh)
    return e


def get_health(controls: list[dict]) -> dict:
    """wincam run_controls() device-backed GET health: focal_length excluded (the driver answers it from the
    descriptors). Returns get_ok_count, get_failed_count, get_failed_controls, device_not_answering, first_fail_hr."""
    ok, failed_n, keys, first = 0, 0, [], None
    for e in controls:
        if not e.get("supported") or e.get("name") == "focal_length":
            continue
        if e.get("get_ok") is True:
            ok += 1
            continue
        failed_n += 1
        keys.append(e.get("key"))
        if first is None:
            gh = e.get("get_hr")
            first = int(gh, 16) if isinstance(gh, str) else E_FAIL
    return {"get_ok_count": ok, "get_failed_count": failed_n, "get_failed_controls": keys,
            "device_not_answering": failed_n > 0 and ok == 0, "first_fail_hr": first}


# ============================================================================================================ stats
def pct(values: Sequence[float], p: float) -> float:
    """wincam pct(): linear interpolation between order statistics; NaN for no values."""
    v = sorted(values)
    if not v:
        return math.nan
    idx = p / 100.0 * (len(v) - 1)
    lo, hi = math.floor(idx), math.ceil(idx)
    return v[lo] + (v[hi] - v[lo]) * (idx - lo)
