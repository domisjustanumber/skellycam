import hashlib
import logging
import platform

from pydantic import BaseModel, ConfigDict, computed_field, field_serializer

from skellycam.core.camera.openpnp_capture import OpenPnPCamera, OpenPnPFormatInfo
from skellycam.core.device_detection.virtual_camera_names import (
    matches_listed_virtual_camera_prefix,
    name_contains_virtual_word,
)
from skellycam.core.device_detection.probe_openpnp_stream import probe_openpnp_stream
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
    matches_listed_virtual_name: bool = False
    supports_focus_manual: bool = False
    focus_auto_supported: bool = False
    focus_min: int | None = None
    focus_max: int | None = None
    focus_default: int | None = None

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
    skip_listed_virtual_resolution_interrogation: bool = False,
) -> list[CameraDeviceInfo]:
    """Enumerate cameras via openpnp-capture.

    When ``probe_streams`` is True (default), each device is opened briefly with a candidate format.
    If every attempt fails, ``stream_available`` is False so the UI can treat the device as busy or unusable.
    Probing runs sequentially to avoid USB bandwidth contention during detection.

    ``skip_probe_indices``: device indices already streaming inside Skellycam (workers hold the device); the main
    process cannot open them for probe without falsely marking them busy.

    When ``skip_listed_virtual_resolution_interrogation`` is True, devices matching
    ``matches_listed_virtual_camera_prefix`` (known virtual prefixes or the word *virtual* in the name)
    are not queried for formats and are not stream-probed
    (avoids expensive interrogation while the UI is hiding them).
    """
    skip_set: set[int] = set(skip_probe_indices or ())
    cameras: list[CameraDeviceInfo] = []
    for device in OpenPnPCamera.list_devices():
        if filter_virtual and name_contains_virtual_word(device.name):
            continue
        if "darwin" not in platform.system().lower():
            if not device.unique_id:
                continue

        matches_listed_virtual = matches_listed_virtual_camera_prefix(device.name)
        if skip_listed_virtual_resolution_interrogation and matches_listed_virtual:
            cameras.append(
                CameraDeviceInfo(
                    index=device.index,
                    name=device.name,
                    unique_id=device.unique_id,
                    available_formats=[],
                    stream_available=True,
                    stream_unavailable_reason=None,
                    matches_listed_virtual_name=True,
                    supports_focus_manual=False,
                    focus_auto_supported=False,
                    focus_min=None,
                    focus_max=None,
                    focus_default=None,
                )
            )
            continue

        formats = list(device.formats)
        if probe_streams and device.index not in skip_set:
            outcome = probe_openpnp_stream(device.index, formats)
            cameras.append(
                CameraDeviceInfo(
                    index=device.index,
                    name=device.name,
                    unique_id=device.unique_id,
                    available_formats=formats,
                    stream_available=outcome.stream_available,
                    stream_unavailable_reason=outcome.stream_unavailable_reason,
                    matches_listed_virtual_name=matches_listed_virtual,
                    supports_focus_manual=outcome.supports_focus_manual,
                    focus_auto_supported=outcome.focus_auto_supported,
                    focus_min=outcome.focus_min,
                    focus_max=outcome.focus_max,
                    focus_default=outcome.focus_default,
                )
            )
        else:
            cameras.append(
                CameraDeviceInfo(
                    index=device.index,
                    name=device.name,
                    unique_id=device.unique_id,
                    available_formats=formats,
                    stream_available=True,
                    stream_unavailable_reason=None,
                    matches_listed_virtual_name=matches_listed_virtual,
                    supports_focus_manual=False,
                    focus_auto_supported=False,
                    focus_min=None,
                    focus_max=None,
                    focus_default=None,
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
