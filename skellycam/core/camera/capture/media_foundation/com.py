"""COM declarations of the Media Foundation source (specs/windows-capture.md, sections 6.2, 6.5, 6.8).

Ported from the research prototype `pymf/com.py`. Each `_methods_` list is the vtable after the
three methods of IUnknown, in the order of the Windows SDK 10.0.22621 headers; the prototype checks
each order against those headers. Each method returns the raw HRESULT as an int. A pointer argument
that this package does not use is declared `c_void_p`.

Pointer rules: `own` wraps a pointer that a call gave us (no AddRef); `release` releases it now
and sets it to NULL, so that the garbage collector does not release it again. Thus the release
order is explicit.

The DLLs load at the first call, not at import (section 15).
"""

import ctypes
import sys
from ctypes import POINTER, Structure, Union, byref, c_int, c_long, c_longlong, c_uint, c_ulong, c_ulonglong, c_void_p

if "comtypes" not in sys.modules:
    sys.coinit_flags = 0  # comtypes joins the multithreaded apartment (MTA) at import (agent 43)
from comtypes import GUID, IUnknown, STDMETHOD  # noqa: E402

HR = c_long
REFGUID = POINTER(GUID)
DWORD = c_ulong
UINT32 = c_uint
UINT64 = c_ulonglong
LONGLONG = c_longlong
BOOL = c_int

COINIT_MULTITHREADED = 0x0
MF_VERSION = (0x0002 << 16) | 0x0070
MFSTARTUP_FULL = 0
MF_SOURCE_READER_FIRST_VIDEO_STREAM = 0xFFFFFFFC
MF_SOURCE_READER_ALL_STREAMS = 0xFFFFFFFE
MF_SOURCE_READERF_ERROR = 0x1
MF_SOURCE_READERF_ENDOFSTREAM = 0x2
KSPROPERTY_TYPE_GET = 0x1
KSPROPERTY_TYPE_SET = 0x2
FOURCC_SUFFIX = "-0000-0010-8000-00AA00389B71}"


def _guid(text: str) -> GUID:
    return GUID("{" + text + "}")


MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE = _guid("C60AC5FE-252A-478F-A0EF-BC8FA5F7CAD3")
MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID = _guid("8AC3587A-4AE7-42D8-99E0-0A6013EEF90F")
MF_DEVSOURCE_ATTRIBUTE_FRIENDLY_NAME = _guid("60D0E559-52F8-4FA2-BBCE-ACDB34A8EC01")
MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_SYMBOLIC_LINK = _guid("58F0AAD8-22BF-4F8A-BB3D-D2C4978C6E2F")
MF_READWRITE_DISABLE_CONVERTERS = _guid("98D5B065-1374-4847-8D5D-31520FEE7156")
MF_SOURCE_READER_DISCONNECT_MEDIASOURCE_ON_SHUTDOWN = _guid("56B67165-219E-456D-A22E-2D3004C7FE56")
MF_SOURCE_READER_ASYNC_CALLBACK = _guid("1E3DBEAC-BB43-4C35-B507-CD644464C965")
MF_MT_SUBTYPE = _guid("F7E34C9A-42E8-4714-B74B-CB29D72C35E5")
MF_MT_FRAME_SIZE = _guid("1652C33D-D6B2-4012-B834-72030849A37D")
MF_MT_FRAME_RATE = _guid("C459A2E8-3D2C-4E44-B132-FEE5156C7BB0")
MFSampleExtension_Discontinuity = _guid("9CDF01D9-A0F0-43BA-B077-EAA06CBD728A")
PROPSETID_VIDCAP_CAMERACONTROL = _guid("C6E13370-30AC-11D0-A18C-00A0C9118956")
PROPSETID_VIDCAP_VIDEOPROCAMP = _guid("C6E13360-30AC-11D0-A18C-00A0C9118956")


class _KSIDENTIFIER_S(Structure):
    _fields_ = [("Set", GUID), ("Id", c_ulong), ("Flags", c_ulong)]


class KSIDENTIFIER(Union):
    """ks.h KSPROPERTY: 24 bytes, 8-byte aligned by its LONGLONG member."""
    _fields_ = [("s", _KSIDENTIFIER_S), ("Alignment", c_longlong)]


class KSPROPERTY_CAMERACONTROL_S(Structure):
    """ksmedia.h; KSPROPERTY_VIDEOPROCAMP_S has the same layout. 40 bytes."""
    _fields_ = [("Property", KSIDENTIFIER), ("Value", c_long), ("Flags", c_ulong), ("Capabilities", c_ulong)]


def _m(name, *argtypes):
    return STDMETHOD(HR, name, list(argtypes))


class IMFAttributes(IUnknown):
    _iid_ = _guid("2CD2D921-C447-44A7-A13C-4ADABFC247E3")
    _methods_ = [
        _m("GetItem", REFGUID, c_void_p),
        _m("GetItemType", REFGUID, POINTER(c_int)),
        _m("CompareItem", REFGUID, c_void_p, POINTER(BOOL)),
        _m("Compare", c_void_p, c_int, POINTER(BOOL)),
        _m("GetUINT32", REFGUID, POINTER(UINT32)),
        _m("GetUINT64", REFGUID, POINTER(UINT64)),
        _m("GetDouble", REFGUID, c_void_p),
        _m("GetGUID", REFGUID, POINTER(GUID)),
        _m("GetStringLength", REFGUID, POINTER(UINT32)),
        _m("GetString", REFGUID, c_void_p, UINT32, POINTER(UINT32)),
        _m("GetAllocatedString", REFGUID, POINTER(c_void_p), POINTER(UINT32)),
        _m("GetBlobSize", REFGUID, POINTER(UINT32)),
        _m("GetBlob", REFGUID, c_void_p, UINT32, POINTER(UINT32)),
        _m("GetAllocatedBlob", REFGUID, POINTER(c_void_p), POINTER(UINT32)),
        _m("GetUnknown", REFGUID, REFGUID, POINTER(c_void_p)),
        _m("SetItem", REFGUID, c_void_p),
        _m("DeleteItem", REFGUID),
        _m("DeleteAllItems"),
        _m("SetUINT32", REFGUID, UINT32),
        _m("SetUINT64", REFGUID, UINT64),
        _m("SetDouble", REFGUID, ctypes.c_double),
        _m("SetGUID", REFGUID, REFGUID),
        _m("SetString", REFGUID, ctypes.c_wchar_p),
        _m("SetBlob", REFGUID, c_void_p, UINT32),
        _m("SetUnknown", REFGUID, c_void_p),
        _m("LockStore"),
        _m("UnlockStore"),
        _m("GetCount", POINTER(UINT32)),
        _m("GetItemByIndex", UINT32, POINTER(GUID), c_void_p),
        _m("CopyAllItems", c_void_p),
    ]


class IMFMediaBuffer(IUnknown):
    _iid_ = _guid("045FA593-8799-42B8-BC8D-8968C6453507")
    _methods_ = [
        _m("Lock", POINTER(c_void_p), POINTER(DWORD), POINTER(DWORD)),
        _m("Unlock"),
        _m("GetCurrentLength", POINTER(DWORD)),
        _m("SetCurrentLength", DWORD),
        _m("GetMaxLength", POINTER(DWORD)),
    ]


class IMFSample(IMFAttributes):
    _iid_ = _guid("C40A00F2-B93A-4D80-AE8C-5A1C634F58E4")
    _methods_ = [
        _m("GetSampleFlags", POINTER(DWORD)),
        _m("SetSampleFlags", DWORD),
        _m("GetSampleTime", POINTER(LONGLONG)),
        _m("SetSampleTime", LONGLONG),
        _m("GetSampleDuration", POINTER(LONGLONG)),
        _m("SetSampleDuration", LONGLONG),
        _m("GetBufferCount", POINTER(DWORD)),
        _m("GetBufferByIndex", DWORD, POINTER(c_void_p)),
        _m("ConvertToContiguousBuffer", POINTER(c_void_p)),
        _m("AddBuffer", c_void_p),
        _m("RemoveBufferByIndex", DWORD),
        _m("RemoveAllBuffers"),
        _m("GetTotalLength", POINTER(DWORD)),
        _m("CopyToBuffer", c_void_p),
    ]


class IMFMediaType(IMFAttributes):
    _iid_ = _guid("44AE0FA8-EA31-4109-8D2E-4CAE4997C555")
    _methods_ = [
        _m("GetMajorType", POINTER(GUID)),
        _m("IsCompressedFormat", POINTER(BOOL)),
        _m("IsEqual", c_void_p, POINTER(DWORD)),
        _m("GetRepresentation", GUID, POINTER(c_void_p)),
        _m("FreeRepresentation", GUID, c_void_p),
    ]


class IMFMediaEventGenerator(IUnknown):
    _iid_ = _guid("2CD0BD52-BCD5-4B89-B62C-EADC0C031E7D")
    _methods_ = [
        _m("GetEvent", DWORD, POINTER(c_void_p)),
        _m("BeginGetEvent", c_void_p, c_void_p),
        _m("EndGetEvent", c_void_p, POINTER(c_void_p)),
        _m("QueueEvent", DWORD, REFGUID, HR, c_void_p),
    ]


class IMFActivate(IMFAttributes):
    _iid_ = _guid("7FEE9E9A-4A89-47A6-899C-B6A53A70FB67")
    _methods_ = [
        _m("ActivateObject", REFGUID, POINTER(c_void_p)),
        _m("ShutdownObject"),
        _m("DetachObject"),
    ]


class IMFMediaSource(IMFMediaEventGenerator):
    _iid_ = _guid("279A808D-AEC7-40C8-9C6B-A6B492C78A66")
    _methods_ = [
        _m("GetCharacteristics", POINTER(DWORD)),
        _m("CreatePresentationDescriptor", POINTER(c_void_p)),
        _m("Start", c_void_p, REFGUID, c_void_p),
        _m("Stop"),
        _m("Pause"),
        _m("Shutdown"),
    ]


class IMFSourceReader(IUnknown):
    _iid_ = _guid("70AE66F2-C809-4E4F-8915-BDCB406B7993")
    _methods_ = [
        _m("GetStreamSelection", DWORD, POINTER(BOOL)),
        _m("SetStreamSelection", DWORD, BOOL),
        _m("GetNativeMediaType", DWORD, DWORD, POINTER(c_void_p)),
        _m("GetCurrentMediaType", DWORD, POINTER(c_void_p)),
        _m("SetCurrentMediaType", DWORD, POINTER(DWORD), c_void_p),
        _m("SetCurrentPosition", REFGUID, c_void_p),
        _m("ReadSample", DWORD, DWORD, POINTER(DWORD), POINTER(DWORD), POINTER(LONGLONG), POINTER(c_void_p)),
        _m("Flush", DWORD),
        _m("GetServiceForStream", DWORD, REFGUID, REFGUID, POINTER(c_void_p)),
        _m("GetPresentationAttribute", DWORD, REFGUID, c_void_p),
    ]


class IMFSourceReaderCallback(IUnknown):
    """Implemented in Python. A pointer argument is `c_void_p`, so comtypes never releases a pointer
    that it did not AddRef."""
    _iid_ = _guid("DEEC8D99-FA1D-4D82-84C2-2C8969944867")
    _methods_ = [
        _m("OnReadSample", HR, DWORD, DWORD, LONGLONG, c_void_p),
        _m("OnFlush", DWORD),
        _m("OnEvent", DWORD, c_void_p),
    ]


class IAMVideoProcAmp(IUnknown):
    """GetRange comes first, then Set, then Get (strmif.h)."""
    _iid_ = _guid("C6E13360-30AC-11D0-A18C-00A0C9118956")
    _methods_ = [
        _m("GetRange", c_long, POINTER(c_long), POINTER(c_long), POINTER(c_long), POINTER(c_long), POINTER(c_long)),
        _m("Set", c_long, c_long, c_long),
        _m("Get", c_long, POINTER(c_long), POINTER(c_long)),
    ]


class IAMCameraControl(IUnknown):
    """GetRange comes first, then Set, then Get (strmif.h)."""
    _iid_ = _guid("C6E13370-30AC-11D0-A18C-00A0C9118956")
    _methods_ = [
        _m("GetRange", c_long, POINTER(c_long), POINTER(c_long), POINTER(c_long), POINTER(c_long), POINTER(c_long)),
        _m("Set", c_long, c_long, c_long),
        _m("Get", c_long, POINTER(c_long), POINTER(c_long)),
    ]


class IKsControl(IUnknown):
    _iid_ = _guid("28F54685-06FD-11D2-B27A-00A0C9223196")
    _methods_ = [
        _m("KsProperty", c_void_p, c_ulong, c_void_p, c_ulong, POINTER(c_ulong)),
        _m("KsMethod", c_void_p, c_ulong, c_void_p, c_ulong, POINTER(c_ulong)),
        _m("KsEvent", c_void_p, c_ulong, c_void_p, c_ulong, POINTER(c_ulong)),
    ]


def _entry(dll, name, argtypes, restype=HR):
    """A DLL function that loads its DLL at the first call."""
    function = None

    def call(*args):
        nonlocal function
        if function is None:
            function = getattr(ctypes.WinDLL(dll), name)
            function.argtypes, function.restype = argtypes, restype
        return function(*args)
    return call


MFStartup = _entry("mfplat.dll", "MFStartup", [c_ulong, DWORD])
MFShutdown = _entry("mfplat.dll", "MFShutdown", [])
MFCreateAttributes = _entry("mfplat.dll", "MFCreateAttributes", [POINTER(c_void_p), UINT32])
MFEnumDeviceSources = _entry("mf.dll", "MFEnumDeviceSources", [c_void_p, POINTER(POINTER(c_void_p)), POINTER(UINT32)])
MFCreateSourceReaderFromMediaSource = _entry("mfreadwrite.dll", "MFCreateSourceReaderFromMediaSource",
                                             [c_void_p, c_void_p, POINTER(c_void_p)])
CoInitializeEx = _entry("ole32.dll", "CoInitializeEx", [c_void_p, DWORD])
CoUninitialize = _entry("ole32.dll", "CoUninitialize", [], None)
CoTaskMemFree = _entry("ole32.dll", "CoTaskMemFree", [c_void_p], None)

_joined_mta = False


def coinit_mta() -> bool:
    """Join the MTA on this thread. True when a CoUninitialize must follow (S_OK or S_FALSE)."""
    return (CoInitializeEx(None, COINIT_MULTITHREADED) & 0xFFFFFFFF) in (0, 1)


def startup() -> None:
    """Process set-up of 6.1: this thread joins the MTA, then MFStartup."""
    global _joined_mta
    _joined_mta = coinit_mta()
    hresult = MFStartup(MF_VERSION, MFSTARTUP_FULL) & 0xFFFFFFFF
    if hresult & 0x80000000:
        raise OSError(f"MFStartup failed: 0x{hresult:08X}")


def shutdown() -> None:
    """The end of 6.1. Call it only when no bounded call was abandoned (`bounded.abandoned()`)."""
    MFShutdown()
    if _joined_mta:
        CoUninitialize()


def own(raw, interface):
    """Wrap a pointer that a call gave us, without AddRef. None for NULL."""
    value = raw.value if isinstance(raw, c_void_p) else raw
    if not value:
        return None
    pointer = POINTER(interface)()
    c_void_p.from_address(ctypes.addressof(pointer)).value = value
    return pointer


def borrow(raw, interface):
    """Wrap a pointer that we do not own (an argument of a callback) and AddRef it."""
    pointer = own(raw, interface)
    if pointer is not None:
        pointer.AddRef()
    return pointer


def ref(pointer, interface):
    """A second reference to `pointer` for a bounded call, so that the call never uses an object
    that its caller released (6.6). None for None."""
    return None if not pointer else borrow(ctypes.cast(pointer, c_void_p).value, interface)


def release(pointer) -> None:
    """Release now and set to NULL, so that comtypes does not release it again."""
    if pointer:
        pointer.Release()
        c_void_p.from_address(ctypes.addressof(pointer)).value = None


def query(pointer, interface):
    """QueryInterface without an exception: the new pointer, or None when the object lacks it."""
    out = c_void_p()
    table = ctypes.cast(pointer, POINTER(POINTER(c_void_p))).contents
    query_interface = ctypes.WINFUNCTYPE(HR, c_void_p, POINTER(GUID), POINTER(c_void_p))(table[0])
    if query_interface(ctypes.cast(pointer, c_void_p), byref(interface._iid_), byref(out)) & 0x80000000:
        return None
    return own(out, interface)


def get_uint32(attributes, key: GUID) -> int:
    """The value, or 0 when the attribute is missing."""
    value = UINT32()
    return 0 if attributes.GetUINT32(byref(key), byref(value)) & 0x80000000 else value.value


def get_pair(attributes, key: GUID) -> tuple[int, int] | None:
    """A packed UINT64 (MFGetAttributeSize, MFGetAttributeRatio) as (high, low), or None when missing."""
    value = UINT64()
    if attributes.GetUINT64(byref(key), byref(value)) & 0x80000000:
        return None
    return (value.value >> 32) & 0xFFFFFFFF, value.value & 0xFFFFFFFF


def get_string(attributes, key: GUID) -> str:
    """The string, or "" when the attribute is missing."""
    text, length = c_void_p(), UINT32()
    if attributes.GetAllocatedString(byref(key), byref(text), byref(length)) & 0x80000000 or not text.value:
        return ""
    try:
        return ctypes.wstring_at(text.value, length.value)
    finally:
        CoTaskMemFree(text)


def fourcc(subtype: GUID) -> str:
    """The FOURCC of a video subtype (MJPG, YUY2, NV12, H264), else the GUID text."""
    text = str(subtype).upper()
    return subtype.Data1.to_bytes(4, "little").decode("latin-1") if text.endswith(FOURCC_SUFFIX) else text
