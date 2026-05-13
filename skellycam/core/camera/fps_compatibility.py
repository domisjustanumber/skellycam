"""Shared FPS equivalence helper for capture vs requested rate parity."""

from __future__ import annotations

FPS_VALUE_TOLERANCE = 0.51
"""Treat two advertised FPS values as equal (mirrors UI `FPS_VALUE_TOLERANCE`)."""


def fps_values_equivalent(a: float, b: float) -> bool:
    return abs(float(a) - float(b)) < FPS_VALUE_TOLERANCE
