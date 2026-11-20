"""The rate formula, the limits and the early decision (specs/windows-capture.md, section 10). Pure functions."""

LIMIT = 0.03  # D22: 3 % below or above the mode rate
WARM_UP_FRAMES = 90  # D21
WINDOW_FIRST = 6  # D22: warm-up frames 6 to 90
CHECK_SKIP = 15  # D32: after a live change, skip 15 frames
CHECK_FRAMES = 60  # D32: then measure over 60 frames
BLOCK_FRAMES = 60  # 10.3: one block during a recording
AUTO_REFERENCE_FPS = 30.0  # ADR-PDD3 W2: "auto" with no reported rate is checked against 30


def measured_rate(s_a: int, t_a: int, s_b: int, t_b: int) -> float:
    """(s_b - s_a) / (t_b - t_a): `s` counts each delivered frame, so missed frames do not change it (10.1)."""
    return (s_b - s_a) * 1e9 / (t_b - t_a)


def within_limit(measured: float, mode_rate: float) -> bool:
    return (1 - LIMIT) * mode_rate <= measured <= (1 + LIMIT) * mode_rate


def is_slow(measured: float, mode_rate: float) -> bool:
    return measured < (1 - LIMIT) * mode_rate


def slow_reason(declared: float, measured: float) -> str:
    """The reason of a slow camera (10.4)."""
    return (f"declared {declared:.2f} fps, measured {measured:.2f} fps. Add light or shorten the exposure, "
            f"or choose a rate that the camera reaches.")


def early_deadline_ns(t_a: int, mode_rate: float) -> int:
    """10.2: too slow when frame s_a + 59 has not arrived by t_a + 59 / (0.97 x r)."""
    return t_a + round((CHECK_FRAMES - 1) / ((1 - LIMIT) * mode_rate) * 1e9)
