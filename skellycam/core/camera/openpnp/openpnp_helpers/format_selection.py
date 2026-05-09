"""Pick the closest CapFormatInfo for a :class:`CameraConfig`."""

from __future__ import annotations

from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.openpnp_capture.types import OpenPnPFormatInfo


def _normalize_fourcc(s: str) -> str:
    return "".join(c for c in s.strip().upper() if c.isalnum())


def select_best_format(formats: list[OpenPnPFormatInfo], config: CameraConfig) -> OpenPnPFormatInfo:
    """Prefer matching resolution + capture_fourcc; fall back sensibly if the camera cannot satisfy both."""
    if not formats:
        raise ValueError("No formats reported for this device — cannot open stream")

    w, h = config.resolution.width, config.resolution.height
    want_cc = _normalize_fourcc(config.capture_fourcc)

    exact_res = [f for f in formats if f.width == w and f.height == h]
    pool = exact_res if exact_res else list(formats)

    cc_match = [f for f in pool if _normalize_fourcc(f.fourcc_str) == want_cc]
    pool2 = cc_match if cc_match else pool

    if config.framerate > 0:
        pool2 = sorted(pool2, key=lambda f: abs(f.fps - config.framerate))
    else:
        pool2 = sorted(pool2, key=lambda f: -f.fps)

    return pool2[0]


def format_matches_config(fmt: OpenPnPFormatInfo, config: CameraConfig) -> bool:
    return (
        fmt.width == config.resolution.width
        and fmt.height == config.resolution.height
        and _normalize_fourcc(fmt.fourcc_str) == _normalize_fourcc(config.capture_fourcc)
    )
