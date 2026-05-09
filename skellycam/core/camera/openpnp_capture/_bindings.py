"""Low-level ctypes bindings for openpnp-capture (see upstream openpnp-capture.h)."""

from __future__ import annotations

import ctypes
from ctypes import POINTER, c_char_p, c_int, c_int32, c_uint32, c_void_p
from functools import lru_cache
from typing import NamedTuple

from skellycam.core.camera.openpnp_capture._lib_loader import load_openpnp_capture_library

CapContext = c_void_p
CapStream = c_int32


class CapFormatInfo(ctypes.Structure):
    _fields_ = [
        ("width", c_uint32),
        ("height", c_uint32),
        ("fourcc", c_uint32),
        ("fps", c_uint32),
        ("bpp", c_uint32),
    ]


CAPRESULT_OK = 0
CAPRESULT_ERR = 1
CAPRESULT_DEVICENOTFOUND = 2
CAPRESULT_FORMATNOTSUPPORTED = 3
CAPRESULT_PROPERTYNOTSUPPORTED = 4

CapCustomLogFunc = ctypes.CFUNCTYPE(None, c_uint32, c_char_p)


class CapFunctions(NamedTuple):
    # Use ``object`` (not ``ctypes._FuncPointer`` / ``typing.Any``): beartype cannot import
    # private ctypes pointer types, and rejects ``Any`` for runtime isinstance checks.
    Cap_createContext: object
    Cap_releaseContext: object
    Cap_getDeviceCount: object
    Cap_getDeviceName: object
    Cap_getDeviceUniqueID: object
    Cap_getNumFormats: object
    Cap_getFormatInfo: object
    Cap_openStream: object
    Cap_closeStream: object
    Cap_isOpenStream: object
    Cap_captureFrame: object
    Cap_hasNewFrame: object
    Cap_getStreamFrameCount: object
    Cap_getPropertyLimits: object
    Cap_setProperty: object
    Cap_setAutoProperty: object
    Cap_getProperty: object
    Cap_getAutoProperty: object
    Cap_setLogLevel: object
    Cap_installCustomLogFunction: object
    Cap_getLibraryVersion: object


def _configure(lib: ctypes.CDLL) -> CapFunctions:
    lib.Cap_createContext.argtypes = []
    lib.Cap_createContext.restype = CapContext

    lib.Cap_releaseContext.argtypes = [CapContext]
    lib.Cap_releaseContext.restype = c_uint32

    lib.Cap_getDeviceCount.argtypes = [CapContext]
    lib.Cap_getDeviceCount.restype = c_uint32

    lib.Cap_getDeviceName.argtypes = [CapContext, c_uint32]
    lib.Cap_getDeviceName.restype = c_char_p

    lib.Cap_getDeviceUniqueID.argtypes = [CapContext, c_uint32]
    lib.Cap_getDeviceUniqueID.restype = c_char_p

    lib.Cap_getNumFormats.argtypes = [CapContext, c_uint32]
    lib.Cap_getNumFormats.restype = c_int32

    lib.Cap_getFormatInfo.argtypes = [CapContext, c_uint32, c_uint32, POINTER(CapFormatInfo)]
    lib.Cap_getFormatInfo.restype = c_uint32

    lib.Cap_openStream.argtypes = [CapContext, c_uint32, c_uint32]
    lib.Cap_openStream.restype = CapStream

    lib.Cap_closeStream.argtypes = [CapContext, CapStream]
    lib.Cap_closeStream.restype = c_uint32

    lib.Cap_isOpenStream.argtypes = [CapContext, CapStream]
    lib.Cap_isOpenStream.restype = c_uint32

    lib.Cap_captureFrame.argtypes = [CapContext, CapStream, c_void_p, c_uint32]
    lib.Cap_captureFrame.restype = c_uint32

    lib.Cap_hasNewFrame.argtypes = [CapContext, CapStream]
    lib.Cap_hasNewFrame.restype = c_uint32

    lib.Cap_getStreamFrameCount.argtypes = [CapContext, CapStream]
    lib.Cap_getStreamFrameCount.restype = c_uint32

    lib.Cap_getPropertyLimits.argtypes = [
        CapContext,
        CapStream,
        c_uint32,
        POINTER(c_int32),
        POINTER(c_int32),
        POINTER(c_int),
    ]
    lib.Cap_getPropertyLimits.restype = c_uint32

    lib.Cap_setProperty.argtypes = [CapContext, CapStream, c_uint32, c_int32]
    lib.Cap_setProperty.restype = c_uint32

    lib.Cap_setAutoProperty.argtypes = [CapContext, CapStream, c_uint32, c_uint32]
    lib.Cap_setAutoProperty.restype = c_uint32

    lib.Cap_getProperty.argtypes = [CapContext, CapStream, c_uint32, POINTER(c_int32)]
    lib.Cap_getProperty.restype = c_uint32

    lib.Cap_getAutoProperty.argtypes = [CapContext, CapStream, c_uint32, POINTER(c_uint32)]
    lib.Cap_getAutoProperty.restype = c_uint32

    lib.Cap_setLogLevel.argtypes = [c_uint32]
    lib.Cap_setLogLevel.restype = None

    lib.Cap_installCustomLogFunction.argtypes = [CapCustomLogFunc]
    lib.Cap_installCustomLogFunction.restype = None

    lib.Cap_getLibraryVersion.argtypes = []
    lib.Cap_getLibraryVersion.restype = c_char_p

    return CapFunctions(
        Cap_createContext=lib.Cap_createContext,
        Cap_releaseContext=lib.Cap_releaseContext,
        Cap_getDeviceCount=lib.Cap_getDeviceCount,
        Cap_getDeviceName=lib.Cap_getDeviceName,
        Cap_getDeviceUniqueID=lib.Cap_getDeviceUniqueID,
        Cap_getNumFormats=lib.Cap_getNumFormats,
        Cap_getFormatInfo=lib.Cap_getFormatInfo,
        Cap_openStream=lib.Cap_openStream,
        Cap_closeStream=lib.Cap_closeStream,
        Cap_isOpenStream=lib.Cap_isOpenStream,
        Cap_captureFrame=lib.Cap_captureFrame,
        Cap_hasNewFrame=lib.Cap_hasNewFrame,
        Cap_getStreamFrameCount=lib.Cap_getStreamFrameCount,
        Cap_getPropertyLimits=lib.Cap_getPropertyLimits,
        Cap_setProperty=lib.Cap_setProperty,
        Cap_setAutoProperty=lib.Cap_setAutoProperty,
        Cap_getProperty=lib.Cap_getProperty,
        Cap_getAutoProperty=lib.Cap_getAutoProperty,
        Cap_setLogLevel=lib.Cap_setLogLevel,
        Cap_installCustomLogFunction=lib.Cap_installCustomLogFunction,
        Cap_getLibraryVersion=lib.Cap_getLibraryVersion,
    )


@lru_cache(maxsize=1)
def get_cap_functions() -> CapFunctions:
    lib = load_openpnp_capture_library()
    return _configure(lib)


def fourcc_uint_to_str(fourcc: int) -> str:
    """Decode a uint32_t FOURCC into a 4-character string (e.g. MJPG, YUY2)."""
    chars = [(fourcc >> (8 * i)) & 0xFF for i in range(4)]
    return "".join(chr(c) if 32 <= c < 127 else "?" for c in chars).strip("\x00 ?")
