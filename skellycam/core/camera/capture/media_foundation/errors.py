"""HRESULT to the reason of a failure (specs/windows-capture.md, sections 6.7 and 12). No COM."""

from skellycam.core.camera.capture.failure_codes import default_code
from skellycam.core.camera.capture.source import CaptureFailure

IN_USE = frozenset({0xC00D3704, 0xC00D3EA3, 0x80070964, 0x800700AA})
REMOVED = frozenset({0xC00D3EA2, 0x80070651, 0x8007048F, 0x800701B1})
E_FAIL = 0x80004005
USB_INSUFFICIENT_BANDWIDTH = 0x800718CF

# Values from winerror.h and mferror.h, as the prototype `parse.py` lists them.
NAMES = {
    0x80004001: "E_NOTIMPL", 0x80004002: "E_NOINTERFACE", 0x80004003: "E_POINTER", 0x80004004: "E_ABORT",
    E_FAIL: "E_FAIL", 0x8000FFFF: "E_UNEXPECTED", 0x80070005: "E_ACCESSDENIED", 0x8007000E: "E_OUTOFMEMORY",
    0x80070057: "E_INVALIDARG", 0x80070015: "ERROR_NOT_READY", 0x8007001F: "ERROR_GEN_FAILURE",
    0x8007045D: "ERROR_IO_DEVICE", 0x80070490: "E_PROP_ID_UNSUPPORTED", 0x80070492: "E_PROP_SET_UNSUPPORTED",
    0x800705B4: "ERROR_TIMEOUT", USB_INSUFFICIENT_BANDWIDTH: "USB_INSUFFICIENT_BANDWIDTH",
    0xC00D36B0: "MF_E_PLATFORM_NOT_INITIALIZED", 0xC00D36B2: "MF_E_INVALIDREQUEST",
    0xC00D36B3: "MF_E_INVALIDSTREAMNUMBER", 0xC00D36B4: "MF_E_INVALIDMEDIATYPE", 0xC00D36B5: "MF_E_NOTACCEPTING",
    0xC00D36B9: "MF_E_NO_MORE_TYPES", 0xC00D36BB: "MF_E_UNEXPECTED", 0xC00D36D5: "MF_E_NOT_FOUND",
    0xC00D36E6: "MF_E_ATTRIBUTENOTFOUND", 0xC00D3E82: "MF_E_INVALID_STATE_TRANSITION",
    0xC00D3E84: "MF_E_END_OF_STREAM", 0xC00D3E85: "MF_E_SHUTDOWN", 0xC00D3E9B: "MF_E_MEDIA_SOURCE_WRONGSTATE",
    0xC00D4E24: "MF_E_VIDEO_DEVICE_LOCKED", 0xC00D7167: "MF_E_REBOOT_REQUIRED",
    0xC00DA7FD: "MF_E_HW_STREAM_NOT_CONNECTED",
}


def hresult_reason(hresult: int) -> str:
    """The reason text of 6.7 for an HRESULT: the D13 text, "device removed", or the name of the code."""
    hresult &= 0xFFFFFFFF
    if hresult in IN_USE:
        return "in use by another program"
    if hresult in REMOVED:
        return "device removed"
    return NAMES.get(hresult, f"0x{hresult:08X}")


def hresult_code(hresult: int, stage: str) -> str:
    """The failure code of unix-capture.md 4.6.3 for an HRESULT (windows-capture.md 6.7)."""
    hresult &= 0xFFFFFFFF
    if hresult in IN_USE:
        return "camera-in-use"
    if hresult in REMOVED:
        return "device-removed"
    if hresult == USB_INSUFFICIENT_BANDWIDTH:
        return "usb-bandwidth"
    return default_code(stage)


def failure(hresult: int, stage: str) -> CaptureFailure:
    return CaptureFailure(stage, hresult_reason(hresult), code=hresult_code(hresult, stage))


def check(hresult: int, stage: str) -> None:
    """Raise `CaptureFailure` with `stage` for a failed HRESULT."""
    if hresult & 0x80000000:
        raise failure(hresult, stage)
