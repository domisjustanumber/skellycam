"""Unit tests for the FPS equivalence helper used by capture and UI parity."""

from skellycam.core.camera.fps_compatibility import (
    FPS_VALUE_TOLERANCE,
    fps_values_equivalent,
)


def test_equal_values_within_tolerance() -> None:
    assert fps_values_equivalent(30.0, 30.0) is True
    assert fps_values_equivalent(30.0, 29.97) is True
    assert fps_values_equivalent(60.0, 59.94) is True


def test_unequal_values_outside_tolerance() -> None:
    assert fps_values_equivalent(60.0, 30.0) is False
    assert fps_values_equivalent(30.0, 25.0) is False
    assert fps_values_equivalent(0.0, 1.0) is False


def test_tolerance_constant_is_subframe() -> None:
    assert 0 < FPS_VALUE_TOLERANCE < 1
