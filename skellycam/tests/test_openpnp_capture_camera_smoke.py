"""Optional integration smoke test (requires camera + native library)."""

import os

import numpy as np
import pytest

from skellycam.core.camera.openpnp_capture.types import OpenPnPCaptureLibraryNotFoundError


@pytest.mark.skipif(not os.environ.get("SKELLYCAM_HAS_REAL_CAMERA"), reason="Set SKELLYCAM_HAS_REAL_CAMERA=1 to run")
def test_real_camera_grab_smoke() -> None:
    from skellycam.core.camera.openpnp_capture import OpenPnPCamera, OpenPnPProperty

    try:
        devices = OpenPnPCamera.list_devices()
    except OpenPnPCaptureLibraryNotFoundError:
        pytest.skip("openpnp-capture native library missing")

    assert devices, "No cameras detected"
    dev = devices[0]
    assert dev.formats, "No formats for first device"
    fmt = sorted(dev.formats, key=lambda f: -f.fps)[0]
    cam = OpenPnPCamera(dev.index, fmt.format_id, format_info=fmt, device_formats=dev.formats)
    cam.open()
    try:
        buf = np.zeros((fmt.height, fmt.width, 3), dtype=np.uint8)
        grabbed = 0
        for _ in range(60):
            if cam.capture_frame_into(buf):
                grabbed += 1
            if grabbed >= 30:
                break
        assert grabbed >= 30
        if cam.supports_property(OpenPnPProperty.EXPOSURE):
            lim = cam.get_property_limits(OpenPnPProperty.EXPOSURE)
            mid = (lim.min_value + lim.max_value) // 2
            cam.set_auto_exposure(False)
            cam.set_exposure(mid)
    finally:
        cam.close()
