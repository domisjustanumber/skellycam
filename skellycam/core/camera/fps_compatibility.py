"""Shared FPS equivalence and integer-ratio (frame-drop) rules for capture vs logical output."""

from __future__ import annotations

FPS_VALUE_TOLERANCE = 0.51
"""Treat two advertised FPS values as equal (mirrors UI `FPS_VALUE_TOLERANCE`)."""

LOGICAL_RATIO_MAX_STRIDE = 24
"""Max integer k where native_fps ≈ k * logical_fps (safeguards pathological enums)."""


def fps_values_equivalent(a: float, b: float) -> bool:
    return abs(float(a) - float(b)) < FPS_VALUE_TOLERANCE


def fps_integer_stride(native_fps: float, logical_fps: float) -> int:
    """
    Return k ≥ 1 if ``native_fps`` ≈ k * ``logical_fps`` within tolerance.

    ``k`` is the stride: keep every k-th captured frame to approximate ``logical_fps`` by dropping frames.
    Return 0 when no integer k satisfies the relation (e.g. 60 fps native vs 24 fps logical).
    """
    if logical_fps <= 0:
        return 0
    nf = float(native_fps)
    lf = float(logical_fps)
    for k in range(1, LOGICAL_RATIO_MAX_STRIDE + 1):
        if fps_values_equivalent(nf, k * lf):
            return k
    return 0


def native_supports_logical_output_fps(native_fps: float, logical_fps: float) -> bool:
    """True when the device can approximate ``logical_fps`` by capturing at ``native_fps`` and dropping."""
    if logical_fps <= 0:
        return True
    return fps_integer_stride(native_fps, logical_fps) > 0


def logical_capture_stride_from_camera_config(
    *,
    logical_output_fps: float,
    capture_native_fps: float | None,
) -> int:
    """
    Captured frames per emitted logical frame: keep captures 1, 1+k, 1+2k, …

    Returns 1 when capture rate matches logical rate or native intent is missing.
    """
    if logical_output_fps <= 0:
        return 1
    if capture_native_fps is None or capture_native_fps <= 0:
        return 1
    k = fps_integer_stride(float(capture_native_fps), float(logical_output_fps))
    return k if k >= 2 else 1

