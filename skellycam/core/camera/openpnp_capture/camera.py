"""High-level OpenPnP Capture camera API (ctypes-backed)."""

from __future__ import annotations

import atexit
import threading
from ctypes import byref, cast, c_int, c_int32, c_uint32, c_void_p

import numpy as np

from skellycam.core.camera.openpnp_capture._bindings import (
    CAPRESULT_OK,
    CAPRESULT_PROPERTYNOTSUPPORTED,
    CapFormatInfo,
    fourcc_uint_to_str,
    get_cap_functions,
)
from skellycam.core.camera.openpnp_capture.types import (
    OpenPnPCameraSettings,
    OpenPnPCaptureAPIError,
    OpenPnPDeviceInfo,
    OpenPnPFormatInfo,
    OpenPnPProperty,
    OpenPnPPropertyLimits,
)

_cap_lock = threading.Lock()
_cap_ctx: object | None = None


def _decode_c_str(raw: bytes | str | None) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return str(raw)


def _get_shared_context():
    """Single CapContext per process (required for streams)."""
    global _cap_ctx
    with _cap_lock:
        if _cap_ctx is None:
            cap = get_cap_functions()
            ctx = cap.Cap_createContext()
            if not ctx:
                raise OpenPnPCaptureAPIError("Cap_createContext returned NULL")
            _cap_ctx = ctx
        return _cap_ctx


def _release_shared_context() -> None:
    global _cap_ctx
    with _cap_lock:
        if _cap_ctx is not None:
            get_cap_functions().Cap_releaseContext(_cap_ctx)
            _cap_ctx = None


atexit.register(_release_shared_context)


class OpenPnPCamera:
    """One camera stream via openpnp-capture.

    Frames from ``capture_frame_into`` are converted **RGB → BGR** in place so the rest of
    skellycam (OpenCV recording / UI) continues to see BGR888, matching former cv2 behaviour.
    """

    def __init__(
        self,
        device_index: int,
        format_id: int,
        *,
        format_info: OpenPnPFormatInfo,
        device_formats: list[OpenPnPFormatInfo] | None = None,
    ) -> None:
        self._device_index = int(device_index)
        self._format_id = int(format_id)
        self._format_info = format_info
        self._device_formats: list[OpenPnPFormatInfo] = list(device_formats or [])
        self._stream: int | None = None

    @classmethod
    def library_version(cls) -> str | None:
        cap = get_cap_functions()
        raw = cap.Cap_getLibraryVersion()
        return _decode_c_str(raw) if raw else None

    @classmethod
    def list_devices(cls) -> list[OpenPnPDeviceInfo]:
        ctx = _get_shared_context()
        cap = get_cap_functions()
        n = cap.Cap_getDeviceCount(ctx)
        devices: list[OpenPnPDeviceInfo] = []
        for idx in range(n):
            name_b = cap.Cap_getDeviceName(ctx, idx)
            uid_b = cap.Cap_getDeviceUniqueID(ctx, idx)
            name = _decode_c_str(name_b) if name_b else f"Camera {idx}"
            uid = _decode_c_str(uid_b) if uid_b else None
            num_f = cap.Cap_getNumFormats(ctx, idx)
            formats: list[OpenPnPFormatInfo] = []
            if num_f > 0:
                finfo = CapFormatInfo()
                for fid in range(num_f):
                    res = cap.Cap_getFormatInfo(ctx, idx, fid, byref(finfo))
                    if res != CAPRESULT_OK:
                        continue
                    formats.append(
                        OpenPnPFormatInfo(
                            format_id=fid,
                            width=int(finfo.width),
                            height=int(finfo.height),
                            fps=float(finfo.fps),
                            fourcc_str=fourcc_uint_to_str(int(finfo.fourcc)),
                            bpp=int(finfo.bpp),
                        )
                    )
            devices.append(
                OpenPnPDeviceInfo(index=idx, name=name or f"Camera {idx}", unique_id=uid, formats=formats)
            )
        return devices

    @property
    def format(self) -> OpenPnPFormatInfo:
        return self._format_info

    @property
    def fourcc(self) -> str:
        return self._format_info.fourcc_str

    def open(self) -> None:
        if self._stream is not None:
            return
        ctx = _get_shared_context()
        cap = get_cap_functions()
        stream = cap.Cap_openStream(ctx, self._device_index, self._format_id)
        if stream < 0:
            raise OpenPnPCaptureAPIError(
                f"Cap_openStream failed for device={self._device_index} format={self._format_id}",
                result_code=int(stream),
            )
        self._stream = int(stream)

    def close(self) -> None:
        if self._stream is None:
            return
        ctx = _get_shared_context()
        cap = get_cap_functions()
        cap.Cap_closeStream(ctx, self._stream)
        self._stream = None

    def reopen_stream(self, format_id: int, format_info: OpenPnPFormatInfo) -> None:
        """Close the current stream and open another format on the same device index."""
        self.close()
        self._format_id = int(format_id)
        self._format_info = format_info
        self.open()

    @property
    def device_formats(self) -> list[OpenPnPFormatInfo]:
        return list(self._device_formats)

    @property
    def device_index(self) -> int:
        return self._device_index

    def is_open(self) -> bool:
        if self._stream is None:
            return False
        ctx = _get_shared_context()
        cap = get_cap_functions()
        return bool(cap.Cap_isOpenStream(ctx, self._stream))

    def has_new_frame(self) -> bool:
        self._require_stream()
        ctx = _get_shared_context()
        cap = get_cap_functions()
        return bool(cap.Cap_hasNewFrame(ctx, self._stream))

    def stream_frame_count(self) -> int:
        self._require_stream()
        ctx = _get_shared_context()
        cap = get_cap_functions()
        return int(cap.Cap_getStreamFrameCount(ctx, self._stream))

    def capture_frame_into(self, buffer: np.ndarray) -> bool:
        """Copy the latest decoded frame into ``buffer`` (H×W×3 uint8 BGR).

        Returns True if a frame was copied, False if no new frame (matches ``Cap_hasNewFrame`` semantics).
        """
        self._require_stream()
        if buffer.dtype != np.uint8 or buffer.ndim != 3 or buffer.shape[2] != 3:
            raise ValueError("buffer must be H×W×3 uint8")
        h, w = buffer.shape[0], buffer.shape[1]
        need = h * w * 3
        if (h, w) != (self._format_info.height, self._format_info.width):
            raise ValueError(
                f"buffer shape {(h, w)} does not match stream format "
                f"{self._format_info.height}x{self._format_info.width}"
            )
        ctx = _get_shared_context()
        cap = get_cap_functions()
        if not cap.Cap_hasNewFrame(ctx, self._stream):
            return False
        buf_ptr = cast(buffer.ctypes.data, c_void_p)
        err = cap.Cap_captureFrame(ctx, self._stream, buf_ptr, need)
        if err != CAPRESULT_OK:
            return False
        # Library delivers 24-bit RGB; skellycam pipeline expects BGR (former cv2 default).
        ch0 = buffer[:, :, 0].copy()
        buffer[:, :, 0] = buffer[:, :, 2]
        buffer[:, :, 2] = ch0
        return True

    def _require_stream(self) -> None:
        if self._stream is None:
            raise OpenPnPCaptureAPIError("Stream is not open; call open() first")

    def supports_property(self, prop: OpenPnPProperty) -> bool:
        if self._stream is None:
            return False
        ctx = _get_shared_context()
        cap = get_cap_functions()
        vmin, vmax, dv = c_int32(), c_int32(), c_int()
        res = cap.Cap_getPropertyLimits(ctx, self._stream, int(prop), byref(vmin), byref(vmax), byref(dv))
        return res == CAPRESULT_OK

    def get_property_limits(self, prop: OpenPnPProperty) -> OpenPnPPropertyLimits:
        self._require_stream()
        ctx = _get_shared_context()
        cap = get_cap_functions()
        vmin, vmax, dv = c_int32(), c_int32(), c_int()
        res = cap.Cap_getPropertyLimits(ctx, self._stream, int(prop), byref(vmin), byref(vmax), byref(dv))
        if res == CAPRESULT_PROPERTYNOTSUPPORTED:
            raise OpenPnPCaptureAPIError(f"Property {prop.name} not supported", result_code=res)
        if res != CAPRESULT_OK:
            raise OpenPnPCaptureAPIError(f"Cap_getPropertyLimits failed ({res})", result_code=res)
        return OpenPnPPropertyLimits(int(vmin.value), int(vmax.value), int(dv.value))

    def set_exposure(self, value: int) -> None:
        self._set_prop(OpenPnPProperty.EXPOSURE, value)

    def set_auto_exposure(self, enabled: bool) -> None:
        self._set_auto(OpenPnPProperty.EXPOSURE, enabled)

    def set_focus(self, value: int) -> None:
        self._set_prop(OpenPnPProperty.FOCUS, value)

    def set_auto_focus(self, enabled: bool) -> None:
        self._set_auto(OpenPnPProperty.FOCUS, enabled)

    def set_zoom(self, value: int) -> None:
        self._set_prop(OpenPnPProperty.ZOOM, value)

    def _set_prop(self, prop: OpenPnPProperty, value: int) -> None:
        self._require_stream()
        ctx = _get_shared_context()
        cap = get_cap_functions()
        res = cap.Cap_setProperty(ctx, self._stream, int(prop), int(value))
        if res != CAPRESULT_OK:
            raise OpenPnPCaptureAPIError(f"Cap_setProperty({prop.name}) failed", result_code=res)

    def _set_auto(self, prop: OpenPnPProperty, enabled: bool) -> None:
        self._require_stream()
        ctx = _get_shared_context()
        cap = get_cap_functions()
        res = cap.Cap_setAutoProperty(ctx, self._stream, int(prop), 1 if enabled else 0)
        if res != CAPRESULT_OK:
            raise OpenPnPCaptureAPIError(f"Cap_setAutoProperty({prop.name}) failed", result_code=res)

    def _try_get_prop(self, prop: OpenPnPProperty) -> int | None:
        if self._stream is None:
            return None
        ctx = _get_shared_context()
        cap = get_cap_functions()
        out = c_int32()
        res = cap.Cap_getProperty(ctx, self._stream, int(prop), byref(out))
        if res != CAPRESULT_OK:
            return None
        return int(out.value)

    def _try_get_auto(self, prop: OpenPnPProperty) -> bool | None:
        if self._stream is None:
            return None
        ctx = _get_shared_context()
        cap = get_cap_functions()
        out = c_uint32()
        res = cap.Cap_getAutoProperty(ctx, self._stream, int(prop), byref(out))
        if res != CAPRESULT_OK:
            return None
        return bool(out.value)

    def get_settings(self) -> OpenPnPCameraSettings:
        """Best-effort snapshot; unsupported controls are ``None``."""

        def gp(p: OpenPnPProperty) -> int | None:
            return self._try_get_prop(p)

        def ga(p: OpenPnPProperty) -> bool | None:
            return self._try_get_auto(p)

        return OpenPnPCameraSettings(
            exposure=gp(OpenPnPProperty.EXPOSURE),
            exposure_auto=ga(OpenPnPProperty.EXPOSURE),
            focus=gp(OpenPnPProperty.FOCUS),
            focus_auto=ga(OpenPnPProperty.FOCUS),
            zoom=gp(OpenPnPProperty.ZOOM),
            zoom_auto=ga(OpenPnPProperty.ZOOM),
            white_balance=gp(OpenPnPProperty.WHITEBALANCE),
            gain=gp(OpenPnPProperty.GAIN),
            brightness=gp(OpenPnPProperty.BRIGHTNESS),
            contrast=gp(OpenPnPProperty.CONTRAST),
            saturation=gp(OpenPnPProperty.SATURATION),
            gamma=gp(OpenPnPProperty.GAMMA),
            hue=gp(OpenPnPProperty.HUE),
            sharpness=gp(OpenPnPProperty.SHARPNESS),
            backlight_comp=gp(OpenPnPProperty.BACKLIGHTCOMP),
            powerline_freq=gp(OpenPnPProperty.POWERLINEFREQ),
        )
