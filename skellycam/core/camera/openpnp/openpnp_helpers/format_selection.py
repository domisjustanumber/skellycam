"""Pick the closest CapFormatInfo for a :class:`CameraConfig`."""

from __future__ import annotations

from typing import Final

from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.fps_compatibility import fps_values_equivalent
from openpnp_capture.types import OpenPnPFormatInfo

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

# Packed / line-based YUV — usually what users mean by “YUYV” in the UI and what DirectShow USB cams open reliably.
_YUY_PACKED = frozenset({"YUY2", "YUYV", "UYVY", "YUV2", "UYV2"})
_YUY_SEMI_PLANAR = frozenset({"NV12", "NV21"})
_YUY_PLANAR = frozenset({"IYUV", "I420", "YV12", "YU12"})


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


# Temporary policy: capture pipeline lists and opens MJPEG modes only (UI + probing match).
MJPEG_CAPTURE_FORMATS_ONLY: Final[bool] = True


def filter_openpnp_formats_mjpeg_capture_policy(formats: list[OpenPnPFormatInfo]) -> list[OpenPnPFormatInfo]:
    """Enumerate / probe subsets when :data:`MJPEG_CAPTURE_FORMATS_ONLY` is enabled."""
    if not MJPEG_CAPTURE_FORMATS_ONLY:
        return list(formats)
    return [f for f in formats if _canonical_capture_fourcc(f.fourcc_str) == "MJPG"]


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


def _yuy_intra_family_rank(requested_canonical: str, fmt_fourcc: str) -> int:
    """When config requests the YUYV *family*, prefer packed modes before NV12/I420 (often fails to open on Windows)."""
    if requested_canonical != "YUYV":
        return 0
    raw = _normalize_fourcc(fmt_fourcc)
    if raw in _YUY_PACKED:
        return 0
    if raw in _YUY_SEMI_PLANAR:
        return 1
    if raw in _YUY_PLANAR:
        return 2
    if raw in _YUY_FAMILY:
        return 3
    return 4


def select_best_format(formats: list[OpenPnPFormatInfo], config: CameraConfig) -> OpenPnPFormatInfo:
    """Prefer matching resolution + capture_fourcc, then native FPS when ``config.framerate > 0``.

    If no enumerated mode matches the requested FPS (within ``fps_values_equivalent``), pick the
    closest advertised frame rate so the device can still open.
    """
    if not formats:
        raise ValueError("No formats reported for this device — cannot open stream")

    formats = filter_openpnp_formats_mjpeg_capture_policy(formats)
    if not formats:
        raise ValueError(
            "No MJPEG capture modes reported for this device (MJPEG_CAPTURE_FORMATS_ONLY) — cannot open stream",
        )

    w, h = config.resolution.width, config.resolution.height
    want_cc = (
        "MJPG"
        if MJPEG_CAPTURE_FORMATS_ONLY
        else _canonical_capture_fourcc(config.capture_fourcc)
    )

    def _format_tiebreak(fmt: OpenPnPFormatInfo) -> tuple[int, int, int, int]:
        """Codec / resolution / stable id — lower tuple is better."""
        return (
            _yuy_intra_family_rank(want_cc, fmt.fourcc_str),
            _fourcc_preference_rank(fmt.fourcc_str),
            -(fmt.width * fmt.height),
            -fmt.format_id,
        )

    exact_res = [f for f in formats if f.width == w and f.height == h]
    pool = exact_res if exact_res else list(formats)

    cc_match = [f for f in pool if _canonical_capture_fourcc(f.fourcc_str) == want_cc]
    pool2 = cc_match if cc_match else pool

    if config.framerate > 0:
        target = float(config.framerate)

        feasible = [f for f in pool2 if fps_values_equivalent(f.fps, target)]
        if feasible:
            pool2 = sorted(feasible, key=_format_tiebreak)
        else:
            # No advertised mode matches requested FPS (e.g. profile still has 5 fps but
            # the device only lists 60 fps). Prefer the closest native rate so the stream
            # can open; ``extract_config_from_openpnp_camera`` records the actual ``fmt.fps``.
            pool2 = sorted(
                pool2,
                key=lambda f: (abs(float(f.fps) - target), *_format_tiebreak(f)),
            )

    else:
        pool2 = sorted(
            pool2,
            key=lambda f: (
                _yuy_intra_family_rank(want_cc, f.fourcc_str),
                _fourcc_preference_rank(f.fourcc_str),
                -(f.width * f.height),
                -f.fps,
            ),
        )

    return pool2[0]


def format_matches_config(fmt: OpenPnPFormatInfo, config: CameraConfig) -> bool:
    if MJPEG_CAPTURE_FORMATS_ONLY and _canonical_capture_fourcc(fmt.fourcc_str) != "MJPG":
        return False
    return (
        fmt.width == config.resolution.width
        and fmt.height == config.resolution.height
        and _canonical_capture_fourcc(fmt.fourcc_str) == _canonical_capture_fourcc(config.capture_fourcc)
    )
