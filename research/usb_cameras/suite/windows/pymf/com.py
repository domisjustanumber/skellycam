"""COM declarations for pymf: comtypes interfaces, GUIDs, PROPVARIANT and the MF / ole32 / kernel32 entry points.

Every interface is declared by hand. Its ``_methods_`` list IS the vtable after IUnknown's QueryInterface / AddRef /
Release, so the order must match the C++ header exactly. Each order below was checked against the Windows SDK
10.0.22621.0 headers (the SDK that built wincam.exe; this machine no longer has an SDK installed, so the headers came
from Microsoft's ``Microsoft.Windows.SDK.CPP`` 10.0.22621.3233 NuGet package). ``sdk_10.0.22621_reference.json`` next to
this file holds the method order and line numbers extracted from those headers, and ``tests/test_pymf_offline.py``
compares every ``_methods_`` list with it.

| Interface | Header (c/Include/10.0.22621.0/...) | Line | Base | Methods after the base (vtable order) |
| --- | --- | --- | --- | --- |
| IMFAttributes | um/mfobjects.h | 303 | IUnknown | GetItem, GetItemType, CompareItem, Compare, GetUINT32, GetUINT64, GetDouble, GetGUID, GetStringLength, GetString, GetAllocatedString, GetBlobSize, GetBlob, GetAllocatedBlob, GetUnknown, SetItem, DeleteItem, DeleteAllItems, SetUINT32, SetUINT64, SetDouble, SetGUID, SetString, SetBlob, SetUnknown, LockStore, UnlockStore, GetCount, GetItemByIndex, CopyAllItems |
| IMFMediaBuffer | um/mfobjects.h | 791 | IUnknown | Lock, Unlock, GetCurrentLength, SetCurrentLength, GetMaxLength |
| IMFSample | um/mfobjects.h | 931 | IMFAttributes | GetSampleFlags, SetSampleFlags, GetSampleTime, SetSampleTime, GetSampleDuration, SetSampleDuration, GetBufferCount, GetBufferByIndex, ConvertToContiguousBuffer, AddBuffer, RemoveBufferByIndex, RemoveAllBuffers, GetTotalLength, CopyToBuffer |
| IMFMediaType | um/mfobjects.h | 1959 | IMFAttributes | GetMajorType, IsCompressedFormat, IsEqual, GetRepresentation, FreeRepresentation |
| IMFMediaEventGenerator | um/mfobjects.h | 4437 | IUnknown | GetEvent, BeginGetEvent, EndGetEvent, QueueEvent |
| IMFActivate | um/mfobjects.h | 5624 | IMFAttributes | ActivateObject, ShutdownObject, DetachObject |
| IMFSourceResolver | um/mfidl.h | 1405 | IUnknown | CreateObjectFromURL, CreateObjectFromByteStream, BeginCreateObjectFromURL, EndCreateObjectFromURL, BeginCreateObjectFromByteStream, EndCreateObjectFromByteStream, CancelObjectCreation |
| IMFMediaSource | um/mfidl.h | 1764 | IMFMediaEventGenerator | GetCharacteristics, CreatePresentationDescriptor, Start, Stop, Pause, Shutdown |
| IMFPresentationDescriptor | um/mfidl.h | 6208 | IMFAttributes | GetStreamDescriptorCount, GetStreamDescriptorByIndex, SelectStream, DeselectStream, Clone |
| IMFStreamDescriptor | um/mfidl.h | 6653 | IMFAttributes | GetStreamIdentifier, GetMediaTypeHandler |
| IMFMediaTypeHandler | um/mfidl.h | 7036 | IUnknown | IsMediaTypeSupported, GetMediaTypeCount, GetMediaTypeByIndex, SetCurrentMediaType, GetCurrentMediaType, GetMajorType |
| IMFSourceReader | um/mfreadwrite.h | 355 | IUnknown | GetStreamSelection, SetStreamSelection, GetNativeMediaType, GetCurrentMediaType, SetCurrentMediaType, SetCurrentPosition, ReadSample, Flush, GetServiceForStream, GetPresentationAttribute |
| IMFSourceReaderCallback | um/mfreadwrite.h | 932 | IUnknown | OnReadSample, OnFlush, OnEvent |
| IAMVideoProcAmp | um/strmif.h | 10959 | IUnknown | GetRange, Set, Get |
| IAMCameraControl | um/strmif.h | 11124 | IUnknown | GetRange, Set, Get |
| IKsControl | shared/ks.h | 3921 (IID 3995) | IUnknown | KsProperty, KsMethod, KsEvent |

Note the IAM order: GetRange comes FIRST (then Set, then Get). Declaring Get / Set / GetRange, as the method names
might suggest, would call the wrong function with the wrong arguments.

Conventions:
- Every method returns the raw HRESULT as a Python int (restype ``c_long``, never comtypes' raising HRESULT type),
  so each step records its real code, like wincam does.
- Pointer arguments are declared ``c_void_p`` / ``POINTER(c_void_p)``; a returned interface pointer is wrapped with
  ``own()`` (takes the reference the callee gave us, no AddRef) and given back with ``release()`` (Release now, then
  NULL the Python object so its ``__del__`` does nothing). Release order is therefore explicit, never left to the
  garbage collector.
- The apartment is the MTA (``sys.coinit_flags = 0`` before comtypes is imported), as in wincam. Worker threads join
  the MTA with ``coinit_mta()``.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import POINTER, Structure, Union, byref, c_double, c_int, c_long, c_longlong, c_ubyte, c_uint, c_ulong, \
    c_ulonglong, c_ushort, c_void_p, c_wchar_p, wintypes

if "comtypes" not in sys.modules:
    sys.coinit_flags = 0          # COINIT_MULTITHREADED for comtypes' own CoInitializeEx on import
import comtypes  # noqa: E402
from comtypes import GUID, IUnknown, STDMETHOD  # noqa: E402

HR = c_long            # raw HRESULT (no exception on failure)
REFGUID = POINTER(GUID)
DWORD = c_ulong
UINT32 = c_uint
UINT64 = c_ulonglong
LONGLONG = c_longlong
BOOL = c_int

COINIT_MULTITHREADED = 0x0
MF_VERSION = (0x0002 << 16) | 0x0070          # mfapi.h 37/45/46
MFSTARTUP_FULL = 0
MF_SOURCE_READER_FIRST_VIDEO_STREAM = 0xFFFFFFFC   # mfreadwrite.h 329
MF_SOURCE_READER_ALL_STREAMS = 0xFFFFFFFE          # mfreadwrite.h 326
MF_SOURCE_READERF_ERROR = 0x1                      # mfreadwrite.h 305-311
MF_SOURCE_READERF_ENDOFSTREAM = 0x2
MF_SOURCE_READERF_NEWSTREAM = 0x4
MF_SOURCE_READERF_NATIVEMEDIATYPECHANGED = 0x10
MF_SOURCE_READERF_CURRENTMEDIATYPECHANGED = 0x20
MF_SOURCE_READERF_STREAMTICK = 0x100
MF_SOURCE_READERF_ALLEFFECTSREMOVED = 0x200
MF_RESOLUTION_MEDIASOURCE = 0x1                    # mfidl.h 1349
MF_RESOLUTION_READ = 0x10000                       # mfidl.h 1358
KSPROPERTY_TYPE_GET = 0x1                          # ks.h 143
KSPROPERTY_TYPE_SET = 0x2                          # ks.h 145
KSPROPERTY_TYPE_BASICSUPPORT = 0x200               # ks.h 148
KSPROPERTY_TYPE_DEFAULTVALUES = 0x10000            # ks.h 155

VT_I8, VT_UI4, VT_UI8, VT_R8, VT_LPWSTR, VT_CLSID, VT_UNKNOWN, VT_VECTOR, VT_UI1 = 20, 19, 21, 5, 31, 72, 13, 0x1000, 17


def G(s: str) -> GUID:
    return GUID("{" + s + "}")


# ============================================================================================================ GUIDs
# values: sdk_10.0.22621_reference.json "guids" (header + line per GUID)
MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE = G("C60AC5FE-252A-478F-A0EF-BC8FA5F7CAD3")
MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID = G("8AC3587A-4AE7-42D8-99E0-0A6013EEF90F")
MF_DEVSOURCE_ATTRIBUTE_FRIENDLY_NAME = G("60D0E559-52F8-4FA2-BBCE-ACDB34A8EC01")
MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_SYMBOLIC_LINK = G("58F0AAD8-22BF-4F8A-BB3D-D2C4978C6E2F")
MF_READWRITE_DISABLE_CONVERTERS = G("98D5B065-1374-4847-8D5D-31520FEE7156")
MF_SOURCE_READER_DISCONNECT_MEDIASOURCE_ON_SHUTDOWN = G("56B67165-219E-456D-A22E-2D3004C7FE56")
MF_SOURCE_READER_ASYNC_CALLBACK = G("1E3DBEAC-BB43-4C35-B507-CD644464C965")
MF_MT_MAJOR_TYPE = G("48EBA18E-F8C9-4687-BF11-0A74C9F96A8F")
MF_MT_SUBTYPE = G("F7E34C9A-42E8-4714-B74B-CB29D72C35E5")
MF_MT_FRAME_SIZE = G("1652C33D-D6B2-4012-B834-72030849A37D")
MF_MT_FRAME_RATE = G("C459A2E8-3D2C-4E44-B132-FEE5156C7BB0")
MF_MT_FRAME_RATE_RANGE_MIN = G("D2E7558C-DC1F-403F-9A72-D28BB1EB3B5E")
MF_MT_FRAME_RATE_RANGE_MAX = G("E3371D41-B4CF-4A05-BD4E-20B88BB2C4D6")
MF_MT_PIXEL_ASPECT_RATIO = G("C6376A1E-8D0A-4027-BE45-6D9A0AD39BB6")
MF_MT_SAMPLE_SIZE = G("DAD3AB78-1990-408B-BCE2-EBA673DACC10")
MFSampleExtension_CaptureMetadata = G("2EBE23A8-FAF5-444A-A6A2-EB810880AB5D")
MF_CAPTURE_METADATA_FRAME_RAWSTREAM = G("9252077B-2680-49B9-AE02-B19075973B70")
MFSampleExtension_Discontinuity = G("9CDF01D9-A0F0-43BA-B077-EAA06CBD728A")
MFSampleExtension_DeviceTimestamp = G("8F3E35E7-2DCD-4887-8622-2A58BAA652B0")
MFMediaType_Video = G("73646976-0000-0010-8000-00AA00389B71")
PROPSETID_VIDCAP_CAMERACONTROL = G("C6E13370-30AC-11D0-A18C-00A0C9118956")   # ksmedia.h 5695
PROPSETID_VIDCAP_VIDEOPROCAMP = G("C6E13360-30AC-11D0-A18C-00A0C9118956")    # ksmedia.h 5240
#: attributes whose UINT64 value is a (hi, lo) pair (wincam attrs_json)
PAIR_ATTRS = {str(g).upper().strip("{}") for g in (MF_MT_FRAME_SIZE, MF_MT_FRAME_RATE, MF_MT_FRAME_RATE_RANGE_MIN,
                                                     MF_MT_FRAME_RATE_RANGE_MAX, MF_MT_PIXEL_ASPECT_RATIO)}


def gtext(g: GUID) -> str:
    """GUID as upper-case text without braces (the form parse.GUID_NAMES uses)."""
    return str(g).upper().strip("{}")


# ============================================================================================================ PROPVARIANT
class _CAUB(Structure):
    _fields_ = [("cElems", c_ulong), ("pElems", POINTER(c_ubyte))]


class _PVUnion(Union):
    _fields_ = [("ulVal", c_ulong), ("uhVal", c_ulonglong), ("hVal", c_longlong), ("dblVal", c_double),
                ("puuid", POINTER(GUID)), ("pwszVal", c_void_p), ("caub", _CAUB), ("punkVal", c_void_p),
                ("_pad", c_ubyte * 16)]


class PROPVARIANT(Structure):
    """propidlbase.h tagPROPVARIANT: VARTYPE vt; WORD wReserved1..3; union (16 bytes on x64). sizeof = 24."""
    _fields_ = [("vt", c_ushort), ("wReserved1", c_ushort), ("wReserved2", c_ushort), ("wReserved3", c_ushort),
                ("u", _PVUnion)]


# ============================================================================================================ KS structs
class _KSIDENTIFIER_S(Structure):
    _fields_ = [("Set", GUID), ("Id", c_ulong), ("Flags", c_ulong)]


class KSIDENTIFIER(Union):
    """ks.h KSIDENTIFIER (= KSPROPERTY): union { struct {GUID Set; ULONG Id; ULONG Flags;}; LONGLONG Alignment; }.
    24 bytes, 8-byte aligned (the LONGLONG member), which is what makes the _S structs below 40 bytes."""
    _fields_ = [("s", _KSIDENTIFIER_S), ("Alignment", c_longlong)]


class KSPROPERTY_CAMERACONTROL_S(Structure):
    """ksmedia.h 5745 (KSPROPERTY_VIDEOPROCAMP_S at 5273 has the same layout): KSPROPERTY Property; LONG Value;
    ULONG Flags; ULONG Capabilities. sizeof = 40 (36 rounded up to the 8-byte alignment of KSPROPERTY)."""
    _fields_ = [("Property", KSIDENTIFIER), ("Value", c_long), ("Flags", c_ulong), ("Capabilities", c_ulong)]


class KSPROPERTY_CAMERACONTROL_S2(Structure):
    """ksmedia.h: KSPROPERTY Property; LONG Value1; ULONG Flags; ULONG Capabilities; LONG Value2. sizeof = 40.
    KSPROPERTY_VIDEOPROCAMP_S2 has the same layout."""
    _fields_ = [("Property", KSIDENTIFIER), ("Value1", c_long), ("Flags", c_ulong), ("Capabilities", c_ulong),
                ("Value2", c_long)]


class KSPROPERTY_CAMERACONTROL_FOCAL_LENGTH_S(Structure):
    """ksmedia.h: KSPROPERTY Property; LONG lOcularFocalLength; LONG lObjectiveFocalLengthMin;
    LONG lObjectiveFocalLengthMax. sizeof = 40."""
    _fields_ = [("Property", KSIDENTIFIER), ("lOcularFocalLength", c_long), ("lObjectiveFocalLengthMin", c_long),
                ("lObjectiveFocalLengthMax", c_long)]


# ============================================================================================================ interfaces
def _m(name: str, *argtypes) -> object:
    return STDMETHOD(HR, name, list(argtypes))


class IMFAttributes(IUnknown):
    _iid_ = G("2CD2D921-C447-44A7-A13C-4ADABFC247E3")
    _methods_ = [
        _m("GetItem", REFGUID, POINTER(PROPVARIANT)),
        _m("GetItemType", REFGUID, POINTER(c_int)),
        _m("CompareItem", REFGUID, POINTER(PROPVARIANT), POINTER(BOOL)),
        _m("Compare", c_void_p, c_int, POINTER(BOOL)),
        _m("GetUINT32", REFGUID, POINTER(UINT32)),
        _m("GetUINT64", REFGUID, POINTER(UINT64)),
        _m("GetDouble", REFGUID, POINTER(c_double)),
        _m("GetGUID", REFGUID, POINTER(GUID)),
        _m("GetStringLength", REFGUID, POINTER(UINT32)),
        _m("GetString", REFGUID, c_wchar_p, UINT32, POINTER(UINT32)),
        _m("GetAllocatedString", REFGUID, POINTER(c_void_p), POINTER(UINT32)),
        _m("GetBlobSize", REFGUID, POINTER(UINT32)),
        _m("GetBlob", REFGUID, c_void_p, UINT32, POINTER(UINT32)),
        _m("GetAllocatedBlob", REFGUID, POINTER(c_void_p), POINTER(UINT32)),
        _m("GetUnknown", REFGUID, REFGUID, POINTER(c_void_p)),
        _m("SetItem", REFGUID, POINTER(PROPVARIANT)),
        _m("DeleteItem", REFGUID),
        _m("DeleteAllItems"),
        _m("SetUINT32", REFGUID, UINT32),
        _m("SetUINT64", REFGUID, UINT64),
        _m("SetDouble", REFGUID, c_double),
        _m("SetGUID", REFGUID, REFGUID),
        _m("SetString", REFGUID, c_wchar_p),
        _m("SetBlob", REFGUID, c_void_p, UINT32),
        _m("SetUnknown", REFGUID, c_void_p),
        _m("LockStore"),
        _m("UnlockStore"),
        _m("GetCount", POINTER(UINT32)),
        _m("GetItemByIndex", UINT32, POINTER(GUID), POINTER(PROPVARIANT)),
        _m("CopyAllItems", c_void_p),
    ]


class IMFMediaBuffer(IUnknown):
    _iid_ = G("045FA593-8799-42B8-BC8D-8968C6453507")
    _methods_ = [
        _m("Lock", POINTER(c_void_p), POINTER(DWORD), POINTER(DWORD)),
        _m("Unlock"),
        _m("GetCurrentLength", POINTER(DWORD)),
        _m("SetCurrentLength", DWORD),
        _m("GetMaxLength", POINTER(DWORD)),
    ]


class IMFSample(IMFAttributes):
    _iid_ = G("C40A00F2-B93A-4D80-AE8C-5A1C634F58E4")
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
    _iid_ = G("44AE0FA8-EA31-4109-8D2E-4CAE4997C555")
    _methods_ = [
        _m("GetMajorType", POINTER(GUID)),
        _m("IsCompressedFormat", POINTER(BOOL)),
        _m("IsEqual", c_void_p, POINTER(DWORD)),
        _m("GetRepresentation", GUID, POINTER(c_void_p)),
        _m("FreeRepresentation", GUID, c_void_p),
    ]


class IMFMediaEventGenerator(IUnknown):
    _iid_ = G("2CD0BD52-BCD5-4B89-B62C-EADC0C031E7D")
    _methods_ = [
        _m("GetEvent", DWORD, POINTER(c_void_p)),
        _m("BeginGetEvent", c_void_p, c_void_p),
        _m("EndGetEvent", c_void_p, POINTER(c_void_p)),
        _m("QueueEvent", DWORD, REFGUID, HR, POINTER(PROPVARIANT)),
    ]


class IMFActivate(IMFAttributes):
    _iid_ = G("7FEE9E9A-4A89-47A6-899C-B6A53A70FB67")
    _methods_ = [
        _m("ActivateObject", REFGUID, POINTER(c_void_p)),
        _m("ShutdownObject"),
        _m("DetachObject"),
    ]


class IMFSourceResolver(IUnknown):
    _iid_ = G("FBE5A32D-A497-4B61-BB85-97B1A848A6E3")
    _methods_ = [
        _m("CreateObjectFromURL", c_wchar_p, DWORD, c_void_p, POINTER(c_int), POINTER(c_void_p)),
        _m("CreateObjectFromByteStream", c_void_p, c_wchar_p, DWORD, c_void_p, POINTER(c_int), POINTER(c_void_p)),
        _m("BeginCreateObjectFromURL", c_wchar_p, DWORD, c_void_p, POINTER(c_void_p), c_void_p, c_void_p),
        _m("EndCreateObjectFromURL", c_void_p, POINTER(c_int), POINTER(c_void_p)),
        _m("BeginCreateObjectFromByteStream", c_void_p, c_wchar_p, DWORD, c_void_p, POINTER(c_void_p), c_void_p,
           c_void_p),
        _m("EndCreateObjectFromByteStream", c_void_p, POINTER(c_int), POINTER(c_void_p)),
        _m("CancelObjectCreation", c_void_p),
    ]


class IMFMediaSource(IMFMediaEventGenerator):
    _iid_ = G("279A808D-AEC7-40C8-9C6B-A6B492C78A66")
    _methods_ = [
        _m("GetCharacteristics", POINTER(DWORD)),
        _m("CreatePresentationDescriptor", POINTER(c_void_p)),
        _m("Start", c_void_p, REFGUID, POINTER(PROPVARIANT)),
        _m("Stop"),
        _m("Pause"),
        _m("Shutdown"),
    ]


class IMFPresentationDescriptor(IMFAttributes):
    _iid_ = G("03CB2711-24D7-4DB6-A17F-F3A7A479A536")
    _methods_ = [
        _m("GetStreamDescriptorCount", POINTER(DWORD)),
        _m("GetStreamDescriptorByIndex", DWORD, POINTER(BOOL), POINTER(c_void_p)),
        _m("SelectStream", DWORD),
        _m("DeselectStream", DWORD),
        _m("Clone", POINTER(c_void_p)),
    ]


class IMFStreamDescriptor(IMFAttributes):
    _iid_ = G("56C03D9C-9DBB-45F5-AB4B-D80F47C05938")
    _methods_ = [
        _m("GetStreamIdentifier", POINTER(DWORD)),
        _m("GetMediaTypeHandler", POINTER(c_void_p)),
    ]


class IMFMediaTypeHandler(IUnknown):
    _iid_ = G("E93DCF6C-4B07-4E1E-8123-AA16ED6EADF5")
    _methods_ = [
        _m("IsMediaTypeSupported", c_void_p, POINTER(c_void_p)),
        _m("GetMediaTypeCount", POINTER(DWORD)),
        _m("GetMediaTypeByIndex", DWORD, POINTER(c_void_p)),
        _m("SetCurrentMediaType", c_void_p),
        _m("GetCurrentMediaType", POINTER(c_void_p)),
        _m("GetMajorType", POINTER(GUID)),
    ]


class IMFSourceReader(IUnknown):
    _iid_ = G("70AE66F2-C809-4E4F-8915-BDCB406B7993")
    _methods_ = [
        _m("GetStreamSelection", DWORD, POINTER(BOOL)),
        _m("SetStreamSelection", DWORD, BOOL),
        _m("GetNativeMediaType", DWORD, DWORD, POINTER(c_void_p)),
        _m("GetCurrentMediaType", DWORD, POINTER(c_void_p)),
        _m("SetCurrentMediaType", DWORD, POINTER(DWORD), c_void_p),
        _m("SetCurrentPosition", REFGUID, POINTER(PROPVARIANT)),
        _m("ReadSample", DWORD, DWORD, POINTER(DWORD), POINTER(DWORD), POINTER(LONGLONG), POINTER(c_void_p)),
        _m("Flush", DWORD),
        _m("GetServiceForStream", DWORD, REFGUID, REFGUID, POINTER(c_void_p)),
        _m("GetPresentationAttribute", DWORD, REFGUID, POINTER(PROPVARIANT)),
    ]


class IMFSourceReaderCallback(IUnknown):
    """Implemented in Python (mf.ReaderCallback). Pointer arguments are c_void_p so comtypes never wraps (and later
    Releases) a pointer it did not AddRef; the implementation AddRefs explicitly when it keeps one."""
    _iid_ = G("DEEC8D99-FA1D-4D82-84C2-2C8969944867")
    _methods_ = [
        _m("OnReadSample", HR, DWORD, DWORD, LONGLONG, c_void_p),
        _m("OnFlush", DWORD),
        _m("OnEvent", DWORD, c_void_p),
    ]


class IAMVideoProcAmp(IUnknown):
    _iid_ = G("C6E13360-30AC-11D0-A18C-00A0C9118956")
    _methods_ = [
        _m("GetRange", c_long, POINTER(c_long), POINTER(c_long), POINTER(c_long), POINTER(c_long), POINTER(c_long)),
        _m("Set", c_long, c_long, c_long),
        _m("Get", c_long, POINTER(c_long), POINTER(c_long)),
    ]


class IAMCameraControl(IUnknown):
    _iid_ = G("C6E13370-30AC-11D0-A18C-00A0C9118956")
    _methods_ = [
        _m("GetRange", c_long, POINTER(c_long), POINTER(c_long), POINTER(c_long), POINTER(c_long), POINTER(c_long)),
        _m("Set", c_long, c_long, c_long),
        _m("Get", c_long, POINTER(c_long), POINTER(c_long)),
    ]


class IKsControl(IUnknown):
    _iid_ = G("28F54685-06FD-11D2-B27A-00A0C9223196")
    _methods_ = [
        _m("KsProperty", c_void_p, c_ulong, c_void_p, c_ulong, POINTER(c_ulong)),
        _m("KsMethod", c_void_p, c_ulong, c_void_p, c_ulong, POINTER(c_ulong)),
        _m("KsEvent", c_void_p, c_ulong, c_void_p, c_ulong, POINTER(c_ulong)),
    ]


#: every hand-declared interface (the offline test checks each against sdk_10.0.22621_reference.json)
INTERFACES = (IMFAttributes, IMFMediaBuffer, IMFSample, IMFMediaType, IMFMediaEventGenerator, IMFActivate,
              IMFSourceResolver, IMFMediaSource, IMFPresentationDescriptor, IMFStreamDescriptor, IMFMediaTypeHandler,
              IMFSourceReader, IMFSourceReaderCallback, IAMVideoProcAmp, IAMCameraControl, IKsControl)


# ============================================================================================================ pointers
def own(raw, iface):
    """Wrap a raw interface pointer we already hold a reference to (an out parameter) without AddRef. None for NULL."""
    v = raw.value if isinstance(raw, c_void_p) else raw
    if not v:
        return None
    p = POINTER(iface)()
    c_void_p.from_address(ctypes.addressof(p)).value = v
    return p


def borrow(raw, iface):
    """Wrap a raw pointer we do NOT own (a callback argument): AddRef, so the wrapper's reference is balanced."""
    p = own(raw, iface)
    if p is not None:
        p.AddRef()
    return p


def release(p) -> int | None:
    """Release ``p`` now and NULL it, so comtypes' __del__ does not Release it again. Returns the new refcount."""
    if p is None or not p:
        return None
    n = p.Release()
    c_void_p.from_address(ctypes.addressof(p)).value = None
    return n


_QI_PROTO = ctypes.WINFUNCTYPE(HR, c_void_p, POINTER(GUID), POINTER(c_void_p))


def query(p, iface):
    """IUnknown::QueryInterface through vtable slot 0, without exceptions: (hr, owned pointer or None). comtypes' own
    QueryInterface raises on E_NOINTERFACE; this keeps the HRESULT like every other call here."""
    if p is None or not p:
        return 0x80004003, None
    out = c_void_p()
    vtbl = ctypes.cast(p, POINTER(POINTER(c_void_p))).contents
    hr = _QI_PROTO(vtbl[0])(ctypes.cast(p, c_void_p), byref(iface._iid_), byref(out)) & 0xFFFFFFFF
    return hr, own(out, iface)


# ============================================================================================================ DLLs
_mfplat = ctypes.WinDLL("mfplat.dll")
_mf = ctypes.WinDLL("mf.dll")
_mfreadwrite = ctypes.WinDLL("mfreadwrite.dll")
_ole32 = ctypes.WinDLL("ole32.dll")
_kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)

MFStartup = _mfplat.MFStartup
MFStartup.argtypes, MFStartup.restype = [c_ulong, DWORD], HR
MFShutdown = _mfplat.MFShutdown
MFShutdown.argtypes, MFShutdown.restype = [], HR
MFCreateAttributes = _mfplat.MFCreateAttributes
MFCreateAttributes.argtypes, MFCreateAttributes.restype = [POINTER(c_void_p), UINT32], HR
MFCreateMediaType = _mfplat.MFCreateMediaType
MFCreateMediaType.argtypes, MFCreateMediaType.restype = [POINTER(c_void_p)], HR
MFCreateSample = _mfplat.MFCreateSample
MFCreateSample.argtypes, MFCreateSample.restype = [POINTER(c_void_p)], HR
MFCreateMemoryBuffer = _mfplat.MFCreateMemoryBuffer
MFCreateMemoryBuffer.argtypes, MFCreateMemoryBuffer.restype = [DWORD, POINTER(c_void_p)], HR
MFCreateSourceResolver = _mfplat.MFCreateSourceResolver
MFCreateSourceResolver.argtypes, MFCreateSourceResolver.restype = [POINTER(c_void_p)], HR
MFEnumDeviceSources = _mf.MFEnumDeviceSources
MFEnumDeviceSources.argtypes, MFEnumDeviceSources.restype = [c_void_p, POINTER(POINTER(c_void_p)),
                                                             POINTER(UINT32)], HR
MFCreateSourceReaderFromMediaSource = _mfreadwrite.MFCreateSourceReaderFromMediaSource
MFCreateSourceReaderFromMediaSource.argtypes = [c_void_p, c_void_p, POINTER(c_void_p)]
MFCreateSourceReaderFromMediaSource.restype = HR
CoInitializeEx = _ole32.CoInitializeEx
CoInitializeEx.argtypes, CoInitializeEx.restype = [c_void_p, DWORD], HR
CoUninitialize = _ole32.CoUninitialize
CoUninitialize.argtypes, CoUninitialize.restype = [], None
CoTaskMemFree = _ole32.CoTaskMemFree
CoTaskMemFree.argtypes, CoTaskMemFree.restype = [c_void_p], None
PropVariantClear = _ole32.PropVariantClear
PropVariantClear.argtypes, PropVariantClear.restype = [POINTER(PROPVARIANT)], HR


class FILETIME(Structure):
    _fields_ = [("lo", wintypes.DWORD), ("hi", wintypes.DWORD)]


GetProcessTimes = _kernel32.GetProcessTimes
GetProcessTimes.argtypes = [wintypes.HANDLE, POINTER(FILETIME), POINTER(FILETIME), POINTER(FILETIME),
                            POINTER(FILETIME)]
GetProcessTimes.restype = wintypes.BOOL
GetCurrentProcess = _kernel32.GetCurrentProcess
GetCurrentProcess.argtypes, GetCurrentProcess.restype = [], wintypes.HANDLE
FormatMessageW = _kernel32.FormatMessageW
FormatMessageW.argtypes = [DWORD, c_void_p, DWORD, DWORD, c_void_p, DWORD, c_void_p]
FormatMessageW.restype = DWORD
LoadLibraryExW = _kernel32.LoadLibraryExW
LoadLibraryExW.argtypes, LoadLibraryExW.restype = [c_wchar_p, c_void_p, DWORD], c_void_p
LocalFree = _kernel32.LocalFree
LocalFree.argtypes, LocalFree.restype = [c_void_p], c_void_p


def coinit_mta() -> int:
    """Join the MTA on this thread (returns the HRESULT; S_FALSE when already initialised)."""
    return CoInitializeEx(None, COINIT_MULTITHREADED) & 0xFFFFFFFF


def proc_cpu_s() -> tuple[float, float]:
    """(user_s, kernel_s) of this process from GetProcessTimes (wincam proc_cpu_s)."""
    c, e, k, u = FILETIME(), FILETIME(), FILETIME(), FILETIME()
    if not GetProcessTimes(GetCurrentProcess(), byref(c), byref(e), byref(k), byref(u)):
        return 0.0, 0.0
    f = (lambda ft: ((ft.hi << 32) | ft.lo) / 1e7)
    return f(u), f(k)


_mferror_mod = None


def hr_message(hr: int) -> str:
    """FormatMessage text: system first, then mferror.dll (wincam hr_message)."""
    global _mferror_mod
    flags = 0x00000100 | 0x00001000 | 0x00000200   # ALLOCATE_BUFFER | FROM_SYSTEM | IGNORE_INSERTS
    buf = c_void_p()
    FormatMessageW(flags, None, hr & 0xFFFFFFFF, 0, byref(buf), 0, None)
    if not buf.value:
        if _mferror_mod is None:
            _mferror_mod = LoadLibraryExW("mferror.dll", None, 0x00000002) or 0   # LOAD_LIBRARY_AS_DATAFILE
        if _mferror_mod:
            FormatMessageW(0x00000100 | 0x00000800 | 0x00000200, c_void_p(_mferror_mod), hr & 0xFFFFFFFF, 0,
                           byref(buf), 0, None)
    if not buf.value:
        return ""
    s = ctypes.wstring_at(buf.value)
    LocalFree(buf)
    return s.rstrip("\r\n ")


# ============================================================================================================ helpers
def get_uint32(a, key: GUID) -> tuple[int, int]:
    v = UINT32()
    hr = a.GetUINT32(byref(key), byref(v)) & 0xFFFFFFFF
    return hr, v.value


def get_uint64(a, key: GUID) -> tuple[int, int]:
    v = UINT64()
    hr = a.GetUINT64(byref(key), byref(v)) & 0xFFFFFFFF
    return hr, v.value


def get_guid(a, key: GUID) -> tuple[int, str | None]:
    v = GUID()
    hr = a.GetGUID(byref(key), byref(v)) & 0xFFFFFFFF
    return hr, (gtext(v) if hr == 0 else None)


def get_string(a, key: GUID) -> str | None:
    """GetAllocatedString -> str (CoTaskMemFree'd), None when absent."""
    p, n = c_void_p(), UINT32()
    if a.GetAllocatedString(byref(key), byref(p), byref(n)) & 0x80000000 or not p.value:
        return None
    s = ctypes.wstring_at(p.value, n.value)
    CoTaskMemFree(p)
    return s


def get_pair(a, key: GUID, default: tuple[int, int] = (0, 0)) -> tuple[bool, int, int]:
    """MFGetAttributeSize / MFGetAttributeRatio: (present, hi, lo) of a packed UINT64."""
    hr, v = get_uint64(a, key)
    if hr:
        return False, default[0], default[1]
    return True, (v >> 32) & 0xFFFFFFFF, v & 0xFFFFFFFF


def new_attributes(n: int):
    raw = c_void_p()
    hr = MFCreateAttributes(byref(raw), n) & 0xFFFFFFFF
    return hr, own(raw, IMFAttributes)


def lock_bytes(buf) -> tuple[int, bytes]:
    """Copy an IMFMediaBuffer's current bytes (Lock / string_at / Unlock)."""
    p, mx, ln = c_void_p(), DWORD(), DWORD()
    hr = buf.Lock(byref(p), byref(mx), byref(ln)) & 0xFFFFFFFF
    if hr:
        return hr, b""
    try:
        data = ctypes.string_at(p.value, ln.value) if ln.value else b""
    finally:
        buf.Unlock()
    return 0, data


__all__ = [n for n in dir() if not n.startswith("_")] + ["comtypes"]
