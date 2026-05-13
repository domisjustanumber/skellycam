"""Tests for skipping openpnp format enumeration on listed virtual webcams."""

from unittest.mock import MagicMock, patch

from openpnp_capture import OpenPnPCamera
from openpnp_capture.types import OpenPnPFormatInfo
from skellycam.core.device_detection.detect_cameras_devices import detect_available_cameras
from skellycam.core.device_detection.probe_openpnp_stream import ProbeStreamOutcome


class _VirtualWordStub:
    name = "Brand Virtual Webcam"
    index = 43
    unique_id = "usb-virtual-word-stub-id"

    @property
    def formats(self):
        raise AssertionError(
            ".formats must not be read when skip_listed_virtual_resolution_interrogation is True",
        )


class _ListedVirtualStub:
    name = "OBS-Camera Stub"
    index = 42
    unique_id = "usb-virtual-stub-id"

    @property
    def formats(self):
        raise AssertionError(
            ".formats must not be read when skip_listed_virtual_resolution_interrogation is True",
        )


def test_skip_virtual_word_in_name_never_reads_formats():
    """Names containing the word *virtual* follow the same skip path as listed prefixes."""

    with patch.object(
        OpenPnPCamera,
        "list_devices",
        return_value=[_VirtualWordStub()],
    ), patch(
        "skellycam.core.device_detection.detect_cameras_devices.probe_openpnp_stream",
    ) as mock_probe:
        out = detect_available_cameras(
            filter_virtual=False,
            skip_listed_virtual_resolution_interrogation=True,
        )

    assert len(out) == 1
    assert out[0].matches_listed_virtual_name is True
    assert out[0].available_formats == []
    assert out[0].stream_available is True
    mock_probe.assert_not_called()


def test_skip_listed_virtual_never_reads_formats():
    """When skipping interrogation, do not touch device.formats (no enumeration / probe)."""

    with patch.object(
        OpenPnPCamera,
        "list_devices",
        return_value=[_ListedVirtualStub()],
    ), patch(
        "skellycam.core.device_detection.detect_cameras_devices.probe_openpnp_stream",
    ) as mock_probe:
        out = detect_available_cameras(
            filter_virtual=False,
            skip_listed_virtual_resolution_interrogation=True,
        )

    assert len(out) == 1
    assert out[0].matches_listed_virtual_name is True
    assert out[0].available_formats == []
    assert out[0].stream_available is True
    mock_probe.assert_not_called()


def test_filter_virtual_excludes_listed_prefix_case_sensitive_only():
    """``OBS-Camera`` is filtered; lowercase ``obs-`` is not."""

    lower = MagicMock()
    lower.name = "obs-camera Not Listed Prefix"
    lower.index = 0
    lower.unique_id = "usb-lower-obs"
    lower_fmt = OpenPnPFormatInfo(format_id=0, width=640, height=480, fps=30.0, fourcc_str="MJPG", bpp=24)
    lower.formats = [lower_fmt]
    probe_out = ProbeStreamOutcome(stream_available=True)

    with (
        patch.object(OpenPnPCamera, "list_devices", return_value=[_ListedVirtualStub(), lower]),
        patch(
            "skellycam.core.device_detection.detect_cameras_devices.probe_openpnp_stream",
            return_value=probe_out,
        ) as mock_probe,
    ):
        out = detect_available_cameras(filter_virtual=True, skip_listed_virtual_resolution_interrogation=False)

    assert len(out) == 1
    assert out[0].name == lower.name
    mock_probe.assert_called_once()


def test_listed_virtual_still_interrogated_when_skip_false():
    obs = MagicMock()
    obs.name = "OBS-Camera Other"
    obs.index = 1
    obs.unique_id = "usb-real-id"
    fmt = OpenPnPFormatInfo(format_id=0, width=640, height=480, fps=30.0, fourcc_str="MJPG", bpp=24)
    obs.formats = [fmt]
    probe_out = ProbeStreamOutcome(stream_available=True)

    with (
        patch.object(OpenPnPCamera, "list_devices", return_value=[obs]),
        patch(
            "skellycam.core.device_detection.detect_cameras_devices.probe_openpnp_stream",
            return_value=probe_out,
        ) as mock_probe,
    ):
        out = detect_available_cameras(
            filter_virtual=False,
            skip_listed_virtual_resolution_interrogation=False,
        )

    assert len(out) == 1
    assert len(out[0].available_formats) == 1
    mock_probe.assert_called_once()


def test_physical_camera_always_interrogated_even_when_skip_true():
    real = MagicMock()
    real.name = "Integrated Webcam XYZ"
    real.index = 0
    real.unique_id = "usb-physical-id"
    fmt = OpenPnPFormatInfo(format_id=1, width=1280, height=720, fps=30.0, fourcc_str="MJPG", bpp=24)
    real.formats = [fmt]
    probe_out = ProbeStreamOutcome(stream_available=True)

    with (
        patch.object(OpenPnPCamera, "list_devices", return_value=[real]),
        patch(
            "skellycam.core.device_detection.detect_cameras_devices.probe_openpnp_stream",
            return_value=probe_out,
        ) as mock_probe,
    ):
        out = detect_available_cameras(skip_listed_virtual_resolution_interrogation=True)

    assert len(out) == 1
    assert out[0].matches_listed_virtual_name is False
    assert len(out[0].available_formats) == 1
    mock_probe.assert_called_once()

