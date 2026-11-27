"""Detection through Media Foundation (specs/windows-capture.md, sections 6.2, 6.3 and 7.1 to 7.3).

`detect_media_foundation_cameras` runs the calls in a short-lived child process. Each call there is
bounded. After a hang, the child reports the failure and ends itself hard, so that a hung camera
cannot block the main process (agent 17). The main process does not import comtypes: only the
child and the camera process load it.
"""

import multiprocessing
import os
import re

from pydantic import computed_field

from skellycam.core.camera.capture.modes import NativeMode, capture_modes, supported_modes
from skellycam.core.camera.capture.source import BOUNDED_CALL_LIMIT_S, CaptureFailure
from skellycam.core.device_detection.detect_cameras_devices import CameraDeviceInfo

STEP_LIMIT_S = BOUNDED_CALL_LIMIT_S + 2.0  # the main process waits this long for each message of the child


def camera_id_of(link: str) -> str:
    """The `camera_id` of 7.2: the hash of today, of the lower-case symbolic link."""
    return CameraDeviceInfo(index=0, name="", path=link.lower()).camera_id


class MediaFoundationDeviceInfo(CameraDeviceInfo):
    """`path` is the symbolic link as Media Foundation gives it; `camera_id` hashes it in lower case (7.2).
    `virtual` marks a virtual camera: detection shows it, but a request cannot select it yet."""
    virtual: bool = False
    backend: str | None = "media-foundation"
    id_source: str | None = "mf-link"

    @computed_field
    @property
    def camera_id(self) -> str:
        return camera_id_of(self.path)


class MediaFoundationBackend:
    """The real backend of `detect_media_foundation_cameras` (ADR-HP7D item 9)."""

    def devices(self) -> list[tuple[str, str]]:
        from skellycam.core.camera.capture.media_foundation import com  # comtypes: child process only

        found = com.enumerate_devices("detection")
        for _, _, activate in found:
            com.release(activate)
        return [(name, link) for name, link, _ in found]

    def native_modes(self, link: str) -> list[NativeMode]:
        """Activate the device, list its native types, then close in the order of 6.9 (no reads ran)."""
        from skellycam.core.camera.capture.media_foundation import com  # comtypes: child process only

        found = com.enumerate_devices("detection")
        match = next((activate for _, other, activate in found if other.lower() == link.lower()), None)
        for _, _, activate in found:
            if activate is not match:
                com.release(activate)
        if match is None:
            raise CaptureFailure("detection", "camera not found", code="not-found")
        media_source = reader = None
        try:
            media_source = com.activate_source(match, "detection")
            reader = com.create_reader(media_source, None, "detection")
            return com.native_types(reader)
        finally:
            com.release(reader)
            if media_source:
                media_source.Shutdown()
            com.release(media_source)
            match.ShutdownObject()
            com.release(match)


def is_virtual(name: str, link: str) -> bool:
    """A virtual camera (ADR-PDD3 W5): the name holds "virtual", or the link is under a software-device root:
    `root#` (a root-enumerated device with no hardware bus, for example the NDI cameras) or
    `swd#vcamdevapi#` (the virtual camera API of Windows 11). A real camera has the link of its bus
    (`usb#`, `pci#`, `acpi#`, `display#`, ...). Other `swd#` links stay real, because a sensor group of
    the frame server can join real cameras under that root (not verified on a device)."""
    tail = link.lower().removeprefix("\\\\?\\")
    return "virtual" in name.lower() or tail.startswith(("root#", "swd#vcamdevapi#"))


def _usb_id(link: str, key: str) -> int | None:
    found = re.search(key + r"_([0-9a-f]{4})", link.lower())
    return int(found.group(1), 16) if found else None


def _detect_in_child(backend, sender, modes: bool = True) -> None:
    """The detection child: each call bounded, one message after each step; after a hang, report and end hard.
    With `modes` False it lists the devices only and activates none."""
    from skellycam.core.camera.capture.media_foundation import bounded, com

    try:
        if backend is None:
            com.startup()
            backend = MediaFoundationBackend()
        sender.send(("alive", None))
        found = []
        for name, link in bounded.call("detection", "the device list", backend.devices):
            sender.send(("alive", None))
            if not modes:
                found.append((name, link, None))
                continue
            try:
                native = bounded.call("detection", f"the mode list of {link}", lambda: backend.native_modes(link))
            except Exception as error:
                if getattr(error, "hung", False):
                    raise
                native = None  # 7.3: a mode list that cannot be read gives []
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


def _child_result(receiver, child):
    """The last message of the child. Each message must come within `STEP_LIMIT_S`."""
    while True:
        if not receiver.poll(STEP_LIMIT_S):
            child.kill()
            raise CaptureFailure("detection", f"the detection process did not answer in {STEP_LIMIT_S:g} s",
                                 code="hung")
        try:
            kind, result = receiver.recv()
        except EOFError:
            raise CaptureFailure("detection", f"the detection process ended with code {child.exitcode}",
                                 code="process-ended") from None
        if kind != "alive":
            return kind, result


def detect_media_foundation_cameras(*, backend=None, modes: bool = True) -> list[CameraDeviceInfo]:
    """7.1: the Media Foundation cameras. A virtual camera is listed with `virtual=True`. With `modes` False,
    the device list only: no camera is activated, and no mode list is read (`modes_read` False).
    Raises `CaptureFailure` (stage `detection`) after a hang, and `ValueError` when two devices have
    one `camera_id`."""
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    child = context.Process(target=_detect_in_child, args=(backend, sender, modes), name="skellycam detection", daemon=True)
    child.start()
    sender.close()
    try:
        kind, result = _child_result(receiver, child)
    finally:
        receiver.close()
        child.join(BOUNDED_CALL_LIMIT_S)
        if child.is_alive():
            child.kill()
    if kind == "failed":
        raise result
    cameras, links = [], {}
    for index, (name, link, native) in enumerate(result):
        camera = MediaFoundationDeviceInfo(index=index, name=name, path=link, vendor_id=_usb_id(link, "vid"),
                                           product_id=_usb_id(link, "pid"), supported_modes=supported_modes(native or []),
                                           capture_modes=capture_modes(native or []),
                                           modes_read=native is not None,
                                           virtual=is_virtual(name, link))
        if camera.camera_id in links:
            raise ValueError(f"Detected devices have colliding camera IDs: {camera.camera_id}. "
                             f"Device paths: {links[camera.camera_id]} and {link}")
        links[camera.camera_id] = link
        cameras.append(camera)
    return cameras
