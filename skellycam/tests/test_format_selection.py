"""Tests for OpenPnP format selection heuristics."""

from openpnp_capture.types import OpenPnPFormatInfo

from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.config.image_resolution import ImageResolution
from skellycam.core.camera.openpnp.openpnp_helpers.format_selection import select_best_format


def test_select_best_format_falls_back_to_nearest_fps_when_no_exact_match() -> None:
    """Saved config may request 5 fps while the driver only enumerates e.g. 60 fps modes."""
    formats = [
        OpenPnPFormatInfo(format_id=0, width=1280, height=720, fps=60.0, fourcc_str="MJPG", bpp=24),
    ]
    config = CameraConfig(
        camera_index=0,
        camera_id="x",
        camera_name="test",
        resolution=ImageResolution(width=1280, height=720),
        framerate=5.0,
        capture_fourcc="MJPG",
    )
    chosen = select_best_format(formats, config)
    assert chosen.fps == 60.0
    assert chosen.format_id == 0


def test_select_best_format_prefers_exact_fps_match_when_present() -> None:
    formats = [
        OpenPnPFormatInfo(format_id=0, width=1280, height=720, fps=60.0, fourcc_str="MJPG", bpp=24),
        OpenPnPFormatInfo(format_id=1, width=1280, height=720, fps=30.0, fourcc_str="MJPG", bpp=24),
    ]
    config = CameraConfig(
        camera_index=0,
        camera_id="x",
        camera_name="test",
        resolution=ImageResolution(width=1280, height=720),
        framerate=30.0,
        capture_fourcc="MJPG",
    )
    chosen = select_best_format(formats, config)
    assert chosen.fps == 30.0
    assert chosen.format_id == 1


def test_select_best_format_nearest_fps_picks_closer_mode() -> None:
    formats = [
        OpenPnPFormatInfo(format_id=0, width=1280, height=720, fps=60.0, fourcc_str="MJPG", bpp=24),
        OpenPnPFormatInfo(format_id=1, width=1280, height=720, fps=15.0, fourcc_str="MJPG", bpp=24),
    ]
    config = CameraConfig(
        camera_index=0,
        camera_id="x",
        camera_name="test",
        resolution=ImageResolution(width=1280, height=720),
        framerate=5.0,
        capture_fourcc="MJPG",
    )
    chosen = select_best_format(formats, config)
    assert chosen.fps == 15.0
    assert chosen.format_id == 1


def test_select_best_format_skips_non_mjpeg_when_mjpeg_policy_enabled() -> None:
    """MJPEG-only policy must ignore YUV/H264 enumeration entries."""
    formats = [
        OpenPnPFormatInfo(format_id=2, width=1280, height=720, fps=30.0, fourcc_str="YUY2", bpp=16),
        OpenPnPFormatInfo(format_id=1, width=1280, height=720, fps=60.0, fourcc_str="MJPG", bpp=24),
        OpenPnPFormatInfo(format_id=0, width=1280, height=720, fps=30.0, fourcc_str="MJPG", bpp=24),
    ]
    config = CameraConfig(
        camera_index=0,
        camera_id="x",
        camera_name="test",
        resolution=ImageResolution(width=1280, height=720),
        framerate=30.0,
        capture_fourcc="YUYV",
    )
    chosen = select_best_format(formats, config)
    assert chosen.fourcc_str == "MJPG"
    assert chosen.format_id == 0
