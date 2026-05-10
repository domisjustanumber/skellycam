"""Pick the closest CapFormatInfo for a :class:`CameraConfig`."""

from __future__ import annotations

from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.openpnp_capture.types import OpenPnPFormatInfo


def _normalize_fourcc(s: str) -> str:
    return "".join(c for c in s.strip().upper() if c.isalnum())


_YUY_FAMILY = frozenset(
    {
        "YUY2",
        "YUYV",
        "UYVY",
        "YUV2",
        "UYV2",
        "NV12",
        "NV21",
        "IYUV",
        "I420",
        "YV12",
        "YU12",
    },
)


def _canonical_capture_fourcc(s: str) -> str:
    """Map vendor fourccs into coarse families so YUY2 matches configured YUYV, etc."""
    n = _normalize_fourcc(str(s))
    if n in _YUY_FAMILY:
        return "YUYV"
    if n.startswith("MJ") or "MJPEG" in n or "JFIF" in n or (n.startswith("JPEG") and len(n) <= 8):
        return "MJPG"
    if "H264" in n or "X264" in n or n in {"AVC1", "HVC1", "M264"}:
        return "H264"
    return n


def _fourcc_preference_rank(fourcc_str: str) -> int:
    """Prefer YUV / uncompressed (0), then H.264 (1), then MJPEG (2). Mirrors the UI heuristic."""
    c = _canonical_capture_fourcc(fourcc_str)
    if c == "YUYV":
        return 0
    if c == "H264":
        return 1
    if c == "MJPG":
        return 2
    return 3


def select_best_format(formats: list[OpenPnPFormatInfo], config: CameraConfig) -> OpenPnPFormatInfo:
    """Prefer matching resolution + capture_fourcc; fall back sensibly if the camera cannot satisfy both."""
    if not formats:
        raise ValueError("No formats reported for this device — cannot open stream")

    w, h = config.resolution.width, config.resolution.height
    want_cc = _canonical_capture_fourcc(config.capture_fourcc)

    exact_res = [f for f in formats if f.width == w and f.height == h]
    pool = exact_res if exact_res else list(formats)

    cc_match = [f for f in pool if _canonical_capture_fourcc(f.fourcc_str) == want_cc]
    pool2 = cc_match if cc_match else pool

    if config.framerate > 0:
        target = float(config.framerate)
        pool2 = sorted(
            pool2,
            key=lambda f: (
                abs(f.fps - target),
                _fourcc_preference_rank(f.fourcc_str),
                -(f.width * f.height),
            ),
        )
    else:
        pool2 = sorted(
            pool2,
            key=lambda f: (
                _fourcc_preference_rank(f.fourcc_str),
                -(f.width * f.height),
                -f.fps,
            ),
        )

    return pool2[0]


def format_matches_config(fmt: OpenPnPFormatInfo, config: CameraConfig) -> bool:
    return (
        fmt.width == config.resolution.width
        and fmt.height == config.resolution.height
        and _canonical_capture_fourcc(fmt.fourcc_str) == _canonical_capture_fourcc(config.capture_fourcc)
    )
