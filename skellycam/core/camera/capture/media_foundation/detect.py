"""Detection through Media Foundation (specs/windows-capture.md, sections 6.2, 6.3 and 7.1 to 7.3).

`detect_media_foundation_cameras` runs the calls in a short-lived child process. Each call there is
bounded. After a hang, the child reports the failure and ends itself hard, so that a hung camera
cannot block the main process (agent 17).
"""

import multiprocessing
import os
import re
from ctypes import POINTER, byref, c_void_p

from comtypes import GUID, IUnknown

from skellycam.core.camera.capture.media_foundation import bounded, com
from skellycam.core.camera.capture.media_foundation.errors import check
from skellycam.core.camera.capture.modes import NativeMode, supported_modes
from skellycam.core.camera.capture.source import BOUNDED_CALL_LIMIT_S, CaptureFailure
from skellycam.core.device_detection.detect_cameras_devices import CameraDeviceInfo


def camera_id_of(link: str) -> str:
    """The `camera_id` of 7.2: the hash of today, of the lower-case symbolic link."""
    return CameraDeviceInfo(index=0, name="", path=link.lower()).camera_id


def enumerate_devices(stage: str) -> list:
    """6.2 step 1: [(friendly name, symbolic link, IMFActivate)]. The caller releases each IMFActivate."""
    raw = c_void_p()
    check(com.MFCreateAttributes(byref(raw), 1), stage)
    attributes = com.own(raw, com.IMFAttributes)
    array, count = POINTER(c_void_p)(), com.UINT32()
    try:
        check(attributes.SetGUID(byref(com.MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE),
                                 byref(com.MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID)), stage)
        check(com.MFEnumDeviceSources(attributes, byref(array), byref(count)), stage)
    finally:
        com.release(attributes)
    try:
        devices = []
        for k in range(count.value):
            activate = com.own(array[k], com.IMFActivate)
            devices.append((com.get_string(activate, com.MF_DEVSOURCE_ATTRIBUTE_FRIENDLY_NAME),
                            com.get_string(activate, com.MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_SYMBOLIC_LINK),
                            activate))
        return devices
    finally:
        com.CoTaskMemFree(array)


def activate_source(activate, stage: str):
    """6.2 step 3: IMFActivate::ActivateObject(IID_IMFMediaSource)."""
    raw = c_void_p()
    check(activate.ActivateObject(byref(com.IMFMediaSource._iid_), byref(raw)), stage)
    return com.own(raw, com.IMFMediaSource)


def create_reader(media_source, callback, stage: str):
    """6.2 step 5: a source reader with no converters. With `callback`, the reader is async."""
    raw = c_void_p()
    check(com.MFCreateAttributes(byref(raw), 3), stage)
    attributes = com.own(raw, com.IMFAttributes)
    try:
        attributes.SetUINT32(byref(com.MF_READWRITE_DISABLE_CONVERTERS), 1)
        attributes.SetUINT32(byref(com.MF_SOURCE_READER_DISCONNECT_MEDIASOURCE_ON_SHUTDOWN), 1)
        if callback is not None:
            unknown = callback.QueryInterface(IUnknown)
            attributes.SetUnknown(byref(com.MF_SOURCE_READER_ASYNC_CALLBACK), unknown)
            com.release(unknown)
        raw = c_void_p()
        check(com.MFCreateSourceReaderFromMediaSource(media_source, attributes, byref(raw)), stage)
        return com.own(raw, com.IMFSourceReader)
    finally:
        com.release(attributes)


def mode_of(media_type) -> NativeMode:
    """Subtype, size and rate of an IMFMediaType. A missing rate gives 0/1."""
    subtype = GUID()
    media_type.GetGUID(byref(com.MF_MT_SUBTYPE), byref(subtype))
    width, height = com.get_pair(media_type, com.MF_MT_FRAME_SIZE) or (0, 0)
    fps_num, fps_den = com.get_pair(media_type, com.MF_MT_FRAME_RATE) or (0, 1)
    return NativeMode(width, height, fps_num, fps_den or 1, com.fourcc(subtype))


def native_types(reader) -> list[NativeMode]:
    """6.3 step 1: the native types of the first video stream, in list order (index k is type k)."""
    modes = []
    while True:
        raw = c_void_p()
        if reader.GetNativeMediaType(com.MF_SOURCE_READER_FIRST_VIDEO_STREAM, len(modes), byref(raw)) & 0x80000000:
            return modes
        media_type = com.own(raw, com.IMFMediaType)
        try:
            modes.append(mode_of(media_type))
        finally:
            com.release(media_type)


class MediaFoundationBackend:
    """The real backend of `detect_media_foundation_cameras` (ADR-HP7D item 9)."""

    def devices(self) -> list[tuple[str, str]]:
        found = enumerate_devices("detection")
        for _, _, activate in found:
            com.release(activate)
        return [(name, link) for name, link, _ in found]

    def native_modes(self, link: str) -> list[NativeMode]:
        """Activate the device, list its native types, then close in the order of 6.9 (no reads ran)."""
        found = enumerate_devices("detection")
        match = next((activate for _, other, activate in found if other.lower() == link.lower()), None)
        for _, _, activate in found:
            if activate is not match:
                com.release(activate)
        if match is None:
            raise CaptureFailure("detection", "camera not found")
        media_source = reader = None
        try:
            media_source = activate_source(match, "detection")
            reader = create_reader(media_source, None, "detection")
            return native_types(reader)
        finally:
            com.release(reader)
            if media_source:
                media_source.Shutdown()
            com.release(media_source)
            match.ShutdownObject()
            com.release(match)


def _usb_id(link: str, key: str) -> int | None:
    found = re.search(key + r"_([0-9a-f]{4})", link.lower())
    return int(found.group(1), 16) if found else None


def _detect_in_child(backend, sender) -> None:
    """The detection child: each call bounded; after a hang, report and end hard (6.6)."""
    try:
        if backend is None:
            com.startup()
            backend = MediaFoundationBackend()
        found = []
        for name, link in bounded.call("detection", "the device list", backend.devices):
            try:
                native = bounded.call("detection", f"the mode list of {link}", lambda: backend.native_modes(link))
            except Exception as error:
                if getattr(error, "hung", False):
                    raise
                native = []  # 7.3: a mode list that cannot be read gives []
            found.append((name, link, native))
        sender.send(("ok", found))
    except CaptureFailure as failure:
        sender.send(("failed", failure))
        if failure.hung:
            os._exit(1)  # no MFShutdown and no interpreter finalisation after a hang (6.6)
    except Exception as error:
        sender.send(("failed", CaptureFailure("detection", f"{type(error).__name__}: {error}")))
    if isinstance(backend, MediaFoundationBackend):
        com.shutdown()


def detect_media_foundation_cameras(*, backend=None) -> list[CameraDeviceInfo]:
    """7.1: the Media Foundation cameras. Raises `CaptureFailure` (stage `detection`) after a hang,
    and `ValueError` when two devices have one `camera_id`."""
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    child = context.Process(target=_detect_in_child, args=(backend, sender), name="skellycam detection", daemon=True)
    child.start()
    sender.close()
    try:
        kind, result = receiver.recv()
    except EOFError:
        raise CaptureFailure("detection", f"the detection process ended with code {child.exitcode}") from None
    finally:
        receiver.close()
        child.join(BOUNDED_CALL_LIMIT_S)
        if child.is_alive():
            child.kill()
    if kind == "failed":
        raise result
    cameras, links = [], {}
    for index, (name, link, native) in enumerate(result):
        camera = CameraDeviceInfo(index=index, name=name, path=link.lower(), vendor_id=_usb_id(link, "vid"),
                                  product_id=_usb_id(link, "pid"), supported_modes=supported_modes(native))
        if camera.camera_id in links:
            raise ValueError(f"Detected devices have colliding camera IDs: {camera.camera_id}. "
                             f"Device paths: {links[camera.camera_id]} and {link}")
        links[camera.camera_id] = link
        cameras.append(camera)
    return cameras
