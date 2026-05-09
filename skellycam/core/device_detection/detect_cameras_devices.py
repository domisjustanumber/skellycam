import hashlib
import logging
import platform

from pydantic import BaseModel, ConfigDict, computed_field, field_serializer

from skellycam.core.camera.openpnp_capture import OpenPnPCamera, OpenPnPFormatInfo
from skellycam.core.device_detection.probe_openpnp_stream import probe_openpnp_stream_available
from skellycam.core.types.type_overloads import CameraIdString, CameraIndexInt, CameraNameString

logger = logging.getLogger(__name__)


class CameraDeviceInfo(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    index: CameraIndexInt
    name: CameraNameString
    unique_id: str | None = None
    available_formats: list[OpenPnPFormatInfo]
    stream_available: bool = True
    stream_unavailable_reason: str | None = None

    @field_serializer("available_formats")
    def _serialize_formats(self, fmts: list[OpenPnPFormatInfo]) -> list[dict]:
        return [
            {
                "format_id": f.format_id,
                "width": f.width,
                "height": f.height,
                "fps": f.fps,
                "fourcc_str": f.fourcc_str,
                "bpp": f.bpp,
            }
            for f in fmts
        ]

    @computed_field
    @property
    def camera_id(self) -> CameraIdString:
        if self.unique_id:
            raw = self.unique_id
        else:
            raw = f"idx_{self.index}"
        digest = hashlib.sha256(raw.encode()).digest()
        return format(int.from_bytes(digest[:2], "big"), "04x")


def detect_available_cameras(
    *,
    filter_virtual: bool = True,
    probe_streams: bool = True,
    skip_probe_indices: set[int] | frozenset[int] | None = None,
) -> list[CameraDeviceInfo]:
    """Enumerate cameras via openpnp-capture.

    When ``probe_streams`` is True (default), each device is opened briefly with a candidate format.
    If every attempt fails, ``stream_available`` is False so the UI can treat the device as busy or unusable.
    Probing runs sequentially to avoid USB bandwidth contention during detection.

    ``skip_probe_indices``: device indices already streaming inside Skellycam (workers hold the device); the main
    process cannot open them for probe without falsely marking them busy.
    """
    skip_set: set[int] = set(skip_probe_indices or ())
    cameras: list[CameraDeviceInfo] = []
    for device in OpenPnPCamera.list_devices():
        if filter_virtual and "virtual" in device.name.lower():
            continue
        if "darwin" not in platform.system().lower():
            if not device.unique_id:
                continue
        formats = list(device.formats)
        if probe_streams and device.index not in skip_set:
            ok, reason = probe_openpnp_stream_available(device.index, formats)
        else:
            ok, reason = True, None
        cameras.append(
            CameraDeviceInfo(
                index=device.index,
                name=device.name,
                unique_id=device.unique_id,
                available_formats=formats,
                stream_available=ok,
                stream_unavailable_reason=reason,
            )
        )
    logger.debug(
        "Detected %s cameras: %s",
        len(cameras),
        [
            (c.index, c.name, c.unique_id, len(c.available_formats), c.stream_available)
            for c in cameras
        ],
    )
    return cameras


if __name__ == "__main__":
    print(f"Platform: {platform.system()}")
    print(f"openpnp-capture library: {OpenPnPCamera.library_version()}")
    _cameras = detect_available_cameras()
    if not _cameras:
        print("No cameras detected.")
    else:
        for cam in _cameras:
            print(
                f"Camera Index: {cam.index}, Name: {cam.name}, Unique ID: {cam.unique_id}, "
                f"Formats: {len(cam.available_formats)}"
            )
