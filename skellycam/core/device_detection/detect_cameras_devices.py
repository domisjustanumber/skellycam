import hashlib
import logging
import platform

import cv2
from cv2.videoio_registry import getBackendName
from cv2_enumerate_cameras import supported_backends, enumerate_cameras
from cv2_enumerate_cameras.camera_info import CameraInfo
from pydantic import BaseModel, computed_field
from tabulate import tabulate

from skellycam.core.camera.capture.modes import CaptureMode, CaptureModeEntry  # ADR-HP7D item 3, 3WCA 1: also here
from skellycam.core.camera.determine_backend import determine_opencv_camera_backend, OpenCVBackend
from skellycam.core.device_detection.usb_connection import usb_link
from skellycam.core.types.type_overloads import CameraIndexInt, CameraNameString, CameraBackendInt, CameraVendorIdInt, \
    CameraProductIdInt, CameraDevicePathString, CameraBackendNameString, CameraIdString

logger = logging.getLogger(__name__)

# define a function to search for a camera
def find_camera(
        index: CameraIndexInt | None = None,
        vid: CameraVendorIdInt | None = None,
        pid: CameraProductIdInt | None = None,
        path: CameraDevicePathString | None = None,
        api_preference: CameraBackendInt = cv2.CAP_ANY):
    for i in enumerate_cameras(api_preference):
        if index is not None and i.index == index:
            return cv2.VideoCapture(i.index, i.backend)
        if path is not None and i.path == path:
            return cv2.VideoCapture(i.index, i.backend)
        if vid is not None and pid is not None and i.vid == vid and i.pid == pid:
            return cv2.VideoCapture(i.index, i.backend)
    return None


class CameraDeviceInfo(BaseModel):
    index: CameraIndexInt
    name: CameraNameString
    vendor_id: CameraVendorIdInt | None = None
    product_id: CameraProductIdInt | None = None
    path: CameraDevicePathString | None = None
    backend_id: CameraBackendInt | None = None
    backend_name: CameraBackendNameString | None = None
    supported_modes: list[CaptureMode] = []  # spec 7.3; empty when the mode list cannot be read
    capture_modes: list[CaptureModeEntry] = []  # spec 7.4, 22.2 [V1]: every native type; [] with the OpenCV detection
    virtual: bool = False  # ADR-PDD3 W5: detection shows a virtual camera; a request cannot select it
    modes_read: bool = False  # the native mode list was read: [] then means no mode at the floor (7.5)
    usb_link: str = "unknown"  # "USB 3", "USB 2", "USB 1" or "unknown"
    # unix-capture.md 4.2 item 8: the native backend, the identity source, and the result of certify for the model
    backend: str | None = None  # "v4l2", "avfoundation", "media-foundation"; None for the OpenCV detection
    id_source: str | None = None  # "serial", "id-path", "unique-id", "mf-link"
    has_serial: bool | None = None
    evidence: str = "unknown"  # "verified", "known-bad", "unknown" (certify.md 11.2)
    checked: bool = False  # a row of the record of checked models for the model on this OS key (certify.md 2.5)

    @computed_field
    @property
    def camera_id(self) -> CameraIdString:
        if self.path:
            # 7.2: the lower-case Media Foundation link; the path itself stays as the OS gives it (ADR-PDD3 W6)
            raw = self.path.lower() if self.path.startswith(r"\\?" + "\\") else self.path
        elif self.vendor_id is not None and self.product_id is not None:
            raw = f"{self.vendor_id:04x}_{self.product_id:04x}_{self.index}"
        else:
            return format(self.index, '04x')
        digest = hashlib.sha256(raw.encode()).digest()
        return format(int.from_bytes(digest[:2], 'big'), '04x')

    @classmethod
    def from_camera_info(cls, camera_info: CameraInfo) -> 'CameraDeviceInfo':
        return cls(
            index=camera_info.index,
            name=camera_info.name,
            vendor_id=camera_info.vid,
            product_id=camera_info.pid,
            path=camera_info.path,
            backend_id=camera_info.backend,
            backend_name=getBackendName(camera_info.backend)
        )
    def create_cv2_video_capture(self) -> 'cv2.VideoCapture':
        cap = find_camera(
            vid=self.vendor_id,
            pid=self.product_id,
            path=self.path,
            api_preference=self.backend_id if self.backend_id is not None else cv2.CAP_ANY
        )
        if cap is None:
            raise RuntimeError(f"No matching camera found for index={self.index}, Vendor ID={self.vendor_id}, Product ID={self.product_id}")
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open camera {self.index} with Vendor ID: {self.vendor_id} and Product ID: {self.product_id}")
        # Attempt to read a frame to ensure the camera is working
        success, image = cap.read()

        if not success or image is None:
            cap.release()
            raise RuntimeError(f"Failed to read frame from camera {self.index} with Vendor ID: {self.vendor_id} and Product ID: {self.product_id}")
        return cap


def _add_usb_links(cameras: list[CameraDeviceInfo]) -> list[CameraDeviceInfo]:
    """Set the USB link of each camera from its device path. The lookup never fails the detection."""
    for camera in cameras:
        camera.usb_link = usb_link(camera.path)
    return cameras


def detect_available_cameras(backend_id: CameraBackendInt|None=None, filter_virtual:bool=True,
                             modes: bool = True) -> list[CameraDeviceInfo]:
    """
    Detects available cameras using the cv2_enumerate_cameras package.
    Returns a list of CameraInfo objects for each detected camera.

    On Windows, detection uses Media Foundation, also while the OpenCV source is chosen (7.1, D11). With `modes`
    False it lists the devices only and activates none; elsewhere detection activates no camera in any case. With
    `modes` False no USB link is looked up either: the caller (the check after a failed start) uses the links of the
    detection before.
    """
    if platform.system() == "Windows":
        # Windows only, and it can load comtypes (U18): import it only here.
        from skellycam.core.camera.capture.media_foundation.detect import detect_media_foundation_cameras
        from skellycam.core.camera.capture.camera_checks import mark_devices
        cameras = detect_media_foundation_cameras(modes=modes)
        return mark_devices(_add_usb_links(cameras) if modes else cameras)
    if backend_id is None:
        backend = determine_opencv_camera_backend()
    else:
        backend = OpenCVBackend.from_backend_id(backend_id)


    cameras: list[CameraDeviceInfo] =  []
    for camera_info in enumerate_cameras(apiPreference=backend.id):
        device = CameraDeviceInfo.from_camera_info(camera_info)
        # ADR-PDD3 W5: a virtual camera is listed and marked, whatever `filter_virtual` says; the check refuses it
        device.virtual = 'virtual' in camera_info.name.lower()
        if 'darwin' not in platform.system().lower():
            # On Windows/Linux, VID/PID is reliably provided - skip cameras without it.
            # On macOS (AVFoundation), VID/PID are often unavailable even for real USB cameras.
            if camera_info.vid is None or camera_info.pid is None:
                continue
        if any(camera.camera_id == device.camera_id for camera in cameras):
            raise ValueError(f"Detected devices have colliding camera IDs: {device.camera_id}. Device paths: {[camera.path for camera in cameras]} and {device.path}")
        cameras.append(device)
    if modes:
        _add_usb_links(cameras)
    logger.debug(f"Detected {len(cameras)} cameras:\n {tabulate([camera.model_dump() for camera in cameras], headers='keys')}\n)")
    return cameras

if __name__ == "__main__":
    print(f"Platform: {platform.system()}")
    print(f"OpenCV Version: {cv2.__version__}")
    print(f"Supported Backends: {[getBackendName(b) for b in supported_backends]}")
    _cameras = detect_available_cameras()
    if not _cameras:
        print("No _cameras detected.")
    else:
        for cam in _cameras:
            print(f"Camera Index: {cam.index}, Name: {cam.name}, Vendor ID: {cam.vendor_id}, Product ID: {cam.product_id}, Path: {cam.path}, Backend: {cam.backend_name} ({cam.backend_id})")
