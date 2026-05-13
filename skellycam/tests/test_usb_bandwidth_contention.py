"""Tests for USB isochronous bandwidth detection during multi-camera open."""

import logging
import multiprocessing
import time
from queue import Queue

import pytest

from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.openpnp.openpnp_helpers.create_openpnp_camera import (
    FailedToReadFrameFromCameraException,
    create_openpnp_camera,
)
from openpnp_capture.camera import OpenPnPCamera
from openpnp_capture.types import OpenPnPDeviceInfo, OpenPnPFormatInfo
from skellycam.core.camera_group.camera_group import await_extracted_configs
from skellycam.core.camera_group.camera_group_ipc import CameraGroupIPC
from skellycam.core.camera_group.camera_status import CameraStatus
from skellycam.core.camera_group.usb_bandwidth import USB_BANDWIDTH_USER_GUIDANCE, UsbBandwidthContentionError
from skellycam.core.ipc.pubsub.pubsub_topics import DeviceExtractedConfigMessage

_LOG = logging.getLogger("skellycam.core.camera.openpnp.openpnp_helpers.create_openpnp_camera")

# Shared fake device used by all tests that stub OpenPnPCamera.
_FMT = OpenPnPFormatInfo(format_id=0, width=320, height=240, fps=30.0, fourcc_str="MJPG", bpp=24)
_DEVICE = OpenPnPDeviceInfo(index=0, name="FakeCam", unique_id="x", formats=[_FMT])


class _FakeOpenPnPCamera(OpenPnPCamera):
    """No native code: open succeeds, first frame never arrives."""

    def __init__(self, device_index, format_id, *, format_info, device_formats=None):
        self._device_index = int(device_index)
        self._format_id = int(format_id)
        self._format_info = format_info
        self._device_formats = list(device_formats or [])
        self._stream = None

    def open(self) -> None:
        self._stream = 0

    def close(self) -> None:
        self._stream = None

    def is_open(self) -> bool:
        return self._stream is not None

    def capture_frame_into(self, buf) -> bool:
        return False


def _patch_fake_no_frame_camera(monkeypatch) -> None:
    """Monkeypatch ``create_openpnp_camera``'s OpenPnPCamera to `_FakeOpenPnPCamera`."""
    monkeypatch.setattr(
        _FakeOpenPnPCamera,
        "list_devices",
        classmethod(lambda cls: [_DEVICE]),
    )
    monkeypatch.setattr(
        "skellycam.core.camera.openpnp.openpnp_helpers.create_openpnp_camera.OpenPnPCamera",
        _FakeOpenPnPCamera,
    )


def _minimal_cfg() -> CameraConfig:
    return CameraConfig(
        camera_id="c1",
        camera_index=0,
        camera_name="FakeCam",
        resolution={"width": 320, "height": 240},
        framerate=30.0,
        capture_fourcc="MJPG",
    )


def test_create_openpnp_camera_raises_usb_bandwidth_when_peers_and_no_first_frame(monkeypatch):
    _patch_fake_no_frame_camera(monkeypatch)
    with pytest.raises(UsbBandwidthContentionError, match="never delivered a first frame"):
        create_openpnp_camera(
            _minimal_cfg(),
            retry_count=1,
            parallel_peer_count=1,
            first_frame_deadline_seconds=0.05,
            pre_open_sync=None,
        )


def test_create_openpnp_camera_single_camera_uses_generic_frame_failure(monkeypatch):
    _patch_fake_no_frame_camera(monkeypatch)
    with pytest.raises(FailedToReadFrameFromCameraException):
        create_openpnp_camera(
            _minimal_cfg(),
            retry_count=1,
            parallel_peer_count=0,
            first_frame_deadline_seconds=0.05,
            pre_open_sync=None,
        )


@pytest.mark.asyncio
async def test_await_extracted_configs_raises_usb_when_worker_flag_set(
    monkeypatch, mock_global_kill_flag
):
    cfg_a = CameraConfig(camera_id="a", camera_index=0, camera_name="A")
    cfg_b = CameraConfig(camera_id="b", camera_index=1, camera_name="B")

    heartbeat = multiprocessing.Value("d", 0.0)
    ipc = CameraGroupIPC.create(
        global_kill_flag=mock_global_kill_flag, heartbeat_timestamp=heartbeat
    )
    ipc.extracted_config_subscription = Queue()
    ipc.extracted_config_subscription.put(DeviceExtractedConfigMessage(extracted_config=cfg_a))

    async def fake_await_100ms() -> None:
        mock_global_kill_flag.value = True

    monkeypatch.setattr(
        "skellycam.core.camera_group.camera_group.await_100ms", fake_await_100ms
    )
    monkeypatch.setattr(
        "skellycam.core.camera_group.camera_group_ipc.check_main_process_heartbeat",
        lambda **_: True,
    )

    st_a = CameraStatus()
    st_b = CameraStatus()
    st_b.likely_usb_bandwidth_contention.value = True

    with pytest.raises(UsbBandwidthContentionError) as excinfo:
        await await_extracted_configs(
            ipc=ipc,
            requested_configs={"a": cfg_a, "b": cfg_b},
            camera_statuses={"a": st_a, "b": st_b},
        )

    msg = str(excinfo.value)
    assert "b" in msg
    assert USB_BANDWIDTH_USER_GUIDANCE in msg


def test_create_openpnp_camera_fails_fast_with_peers(monkeypatch):
    """With ``parallel_peer_count >= 1`` we must not retry the first-frame wait.

    USB isochronous bandwidth contention is structural — re-trying takes ~10s/attempt
    and never recovers. The function should raise after a single deadline window so
    the user sees the "use a different USB port" guidance promptly.
    """
    _patch_fake_no_frame_camera(monkeypatch)

    deadline_s = 0.1
    started = time.perf_counter()
    with pytest.raises(UsbBandwidthContentionError):
        create_openpnp_camera(
            _minimal_cfg(),
            retry_count=2,  # would be 3 attempts without peer fail-fast
            parallel_peer_count=1,
            first_frame_deadline_seconds=deadline_s,
            pre_open_sync=None,
        )
    elapsed = time.perf_counter() - started
    assert elapsed < deadline_s * 2 + 0.3, (
        f"Expected fail-fast (~{deadline_s}s) but took {elapsed:.2f}s — likely re-tried."
    )


def test_create_openpnp_camera_single_camera_still_retries(monkeypatch):
    """Single-camera case keeps the retry budget — failures *can* be transient there."""
    _patch_fake_no_frame_camera(monkeypatch)

    retry_log_messages: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            retry_log_messages.append(record.getMessage())

    handler = _Capture(level=logging.WARNING)
    _LOG.addHandler(handler)
    try:
        with pytest.raises(FailedToReadFrameFromCameraException):
            create_openpnp_camera(
                _minimal_cfg(),
                retry_count=2,
                parallel_peer_count=0,
                first_frame_deadline_seconds=0.05,
                pre_open_sync=None,
            )
    finally:
        _LOG.removeHandler(handler)

    retries = [m for m in retry_log_messages if "Retrying" in m and "first frame" in m]
    assert len(retries) >= 1, "Single-camera case should still retry on frame failure."
