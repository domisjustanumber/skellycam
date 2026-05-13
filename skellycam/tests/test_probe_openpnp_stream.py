"""Tests for openpnp stream availability probing."""
from unittest.mock import MagicMock, patch

import pytest

from openpnp_capture.types import OpenPnPCaptureAPIError, OpenPnPFormatInfo
from skellycam.core.device_detection.probe_openpnp_stream import probe_openpnp_stream_available


@pytest.fixture
def sample_formats() -> list[OpenPnPFormatInfo]:
    return [
        OpenPnPFormatInfo(
            format_id=0,
            width=640,
            height=480,
            fps=30.0,
            fourcc_str="MJPG",
            bpp=24,
        ),
        OpenPnPFormatInfo(
            format_id=6,
            width=1280,
            height=720,
            fps=30.0,
            fourcc_str="MJPG",
            bpp=24,
        ),
    ]


def test_probe_empty_formats() -> None:
    ok, reason = probe_openpnp_stream_available(0, [])
    assert ok is False
    assert reason is not None
    assert "No video formats" in reason


def test_probe_success_first_format(sample_formats: list[OpenPnPFormatInfo]) -> None:
    with patch("skellycam.core.device_detection.probe_openpnp_stream.OpenPnPCamera") as mock_cls:
        instance = MagicMock()
        mock_cls.return_value = instance
        instance.open.side_effect = [None]
        instance.capture_frame_into.return_value = True
        ok, reason = probe_openpnp_stream_available(2, sample_formats)
        assert ok is True
        assert reason is None
        instance.open.assert_called_once()
        instance.close.assert_called_once()


def test_probe_open_ok_without_frame_tries_next_format(
    sample_formats: list[OpenPnPFormatInfo],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "skellycam.core.device_detection.probe_openpnp_stream._PROBE_FIRST_FRAME_DEADLINE_S",
        0.02,
    )
    with patch("skellycam.core.device_detection.probe_openpnp_stream.OpenPnPCamera") as mock_cls:
        instances = [MagicMock(), MagicMock()]
        mock_cls.side_effect = instances
        instances[0].open.return_value = None
        instances[0].capture_frame_into.return_value = False
        instances[1].open.return_value = None
        instances[1].capture_frame_into.return_value = True
        ok, reason = probe_openpnp_stream_available(2, sample_formats)
        assert ok is True
        assert reason is None


def test_probe_all_formats_no_frames(
    sample_formats: list[OpenPnPFormatInfo],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "skellycam.core.device_detection.probe_openpnp_stream._PROBE_FIRST_FRAME_DEADLINE_S",
        0.02,
    )
    with patch("skellycam.core.device_detection.probe_openpnp_stream.OpenPnPCamera") as mock_cls:
        instance = MagicMock()
        mock_cls.return_value = instance
        instance.open.return_value = None
        instance.capture_frame_into.return_value = False
        ok, reason = probe_openpnp_stream_available(2, sample_formats)
        assert ok is False
        assert reason is not None
        assert "frame" in reason.lower() or "in use" in reason.lower() or "graph" in reason.lower()


def test_probe_tries_next_format_after_failure(sample_formats: list[OpenPnPFormatInfo]) -> None:
    with patch("skellycam.core.device_detection.probe_openpnp_stream.OpenPnPCamera") as mock_cls:
        instances = []
        for _ in range(2):
            inst = MagicMock()
            instances.append(inst)
        mock_cls.side_effect = instances
        instances[0].open.side_effect = OpenPnPCaptureAPIError("fail first")
        instances[1].open.side_effect = None
        instances[1].capture_frame_into.return_value = True
        ok, reason = probe_openpnp_stream_available(2, sample_formats)
        assert ok is True
        assert reason is None
        assert instances[0].close.called
        assert instances[1].close.called


def test_probe_all_formats_fail(sample_formats: list[OpenPnPFormatInfo]) -> None:
    with patch("skellycam.core.device_detection.probe_openpnp_stream.OpenPnPCamera") as mock_cls:
        instance = MagicMock()
        mock_cls.return_value = instance
        instance.open.side_effect = OpenPnPCaptureAPIError("Cap_openStream failed")
        ok, reason = probe_openpnp_stream_available(2, sample_formats)
        assert ok is False
        assert reason is not None
        assert "in use" in reason.lower() or "Cap_openStream" in reason
