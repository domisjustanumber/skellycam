"""Unit tests for virtual webcam name classification."""

from skellycam.core.device_detection.virtual_camera_names import (
    matches_listed_virtual_camera_prefix,
    name_contains_virtual_word,
)


def test_name_contains_virtual_word_whole_word_only():
    assert name_contains_virtual_word("My Virtual Camera")
    assert name_contains_virtual_word("  x-VIRTUAL-y ")
    assert not name_contains_virtual_word("Virtually Clear HD")
    assert not name_contains_virtual_word("Revirtualized Sensor")


def test_matches_listed_virtual_includes_prefixes_and_virtual_word():
    assert matches_listed_virtual_camera_prefix("OBS-Camera HD")
    assert matches_listed_virtual_camera_prefix("Brand Virtual Webcam")
    assert not matches_listed_virtual_camera_prefix("Integrated Webcam")
