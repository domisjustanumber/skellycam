"""Unit tests for integer-ratio FPS helpers used by capture and UI parity."""

from skellycam.core.camera.fps_compatibility import (
    fps_integer_stride,
    logical_capture_stride_from_camera_config,
    native_supports_logical_output_fps,
)


def test_stride_60_to_30() -> None:
    assert fps_integer_stride(60.0, 30.0) == 2
    assert native_supports_logical_output_fps(60.0, 30.0) is True


def test_stride_120_to_30() -> None:
    assert fps_integer_stride(120.0, 30.0) == 4


def test_stride_60_to_24_rejected() -> None:
    assert fps_integer_stride(60.0, 24.0) == 0
    assert native_supports_logical_output_fps(60.0, 24.0) is False


def test_logical_capture_stride_returns_1_when_no_drop() -> None:
    assert logical_capture_stride_from_camera_config(logical_output_fps=30.0, capture_native_fps=30.0) == 1
    assert logical_capture_stride_from_camera_config(logical_output_fps=-1.0, capture_native_fps=60.0) == 1
    assert logical_capture_stride_from_camera_config(logical_output_fps=30.0, capture_native_fps=None) == 1


def test_logical_capture_stride_when_multiplier() -> None:
    assert logical_capture_stride_from_camera_config(logical_output_fps=30.0, capture_native_fps=60.0) == 2
