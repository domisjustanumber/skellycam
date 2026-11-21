"""The exposure search of specs/camera-requests.md 1.3: the values, the frame feed, the choice and the flag
`add_light`. Pure: no camera and no clock. The shared loop gives it each frame and each set result, and it does
each set that `pending` names on the control thread (1.3 "Who does what").
"""
from collections.abc import Callable

from skellycam.core.camera.capture import rate_check

VALUES = tuple(range(-12, -4))  # 1.3 item 1 [E6]: -12 to -5, in that order; -4 gives about 16 fps (ADR-JMS0 H)
SETTLE_FRAMES = 10  # 1.3 item 2.2 [Q4]: the 10th delivered frame after the set returned
RATE_FRAMES = 30  # 1.3 item 2.4 [Q4]: from the 10th to the 40th delivered frame
TARGET_BRIGHTNESS = 127.5  # 1.3 item 4: half of 255
OFFSET = -1  # 1.3 item 4 [E6]: one step darker than the nearest value
ADD_LIGHT_BELOW = 64.0  # 1.3 item 5 [Q6]: a starting value; T-REQ-25 sets it
LIMIT_NS = 20_000_000_000  # 1.3 item 6 [A2]: from the first set


def early_deadline_ns(t_a: int, mode_rate: float) -> int:
    """1.3 item 2.6 [A1]: frame s_a + 30 cannot arrive in time after t_a + 30 / (0.97 x r)."""
    return t_a + round(RATE_FRAMES / ((1 - rate_check.LIMIT) * mode_rate) * 1e9)


def choose(trials: list[dict]) -> tuple[int | None, bool, str | None]:
    """1.3 items 4 to 6: (chosen value, add_light, reason). The nearest kept value to 127.5, then one step darker
    when that value also kept the rate and is in the range [Q5]. No kept value: the reason `no-value-kept-rate`."""
    kept = {trial["value"]: trial for trial in trials if trial["kept_rate"]}
    if not kept:
        return None, False, "no-value-kept-rate"
    nearest = min(kept.values(), key=lambda trial: abs(trial["brightness"] - TARGET_BRIGHTNESS))["value"]
    chosen = nearest + OFFSET if nearest + OFFSET in kept and nearest + OFFSET >= VALUES[0] else nearest
    return chosen, kept[max(kept)]["brightness"] < ADD_LIGHT_BELOW, None


class ExposureSearch:
    """One search on the open stream. `pending` is the value to set next (None while a set runs or after the end);
    `result` is None until the end, then the `exposure_search` object of 1.5 without `count`."""

    def __init__(self, mode_rate: float, start_ns: int):
        self.mode_rate = mode_rate
        self.limit_ns = start_ns + LIMIT_NS
        self.trials: list[dict] = []
        self.pending: int | None = VALUES[0]
        self.result: dict | None = None
        self.detail: str | None = None  # the reason text of a failure (1.5)
        self._value: int | None = None
        self._returned_ns: int | None = None
        self._first: int | None = None
        self._a: tuple[int, int, float] | None = None  # (s_a, t_a, brightness of the 10th frame)
        self._deadline: int | None = None
        self._last: tuple[int, int] | None = None

    @property
    def wake_ns(self) -> int:
        """The latest time for the next decision with no frame: the early deadline, or the limit of 20 s."""
        return min(self._deadline or self.limit_ns, self.limit_ns)

    def set_done(self, value: int, returned_ns: int, error: str | None = None, readback: int | None = None) -> None:
        """The set of `value` returned at `returned_ns`, with an error text, or with its read-back value."""
        if self.result is not None:
            return
        if error is not None:
            self._fail("set-failed", f"the camera refused exposure {value} ({error})")
        elif readback is not None and readback != value:
            self._fail("readback-differs", f"exposure {value} read back as {readback}")
        else:
            self._value, self._returned_ns, self._first, self._a, self._deadline = value, returned_ns, None, None, None

    def frame(self, sfn: int, arrival_ns: int, brightness: Callable[[], float]) -> None:
        """A taken frame: its `source_frame_number`, its arrival and a call that gives the mean of its image."""
        if self.result is not None or self._returned_ns is None or arrival_ns <= self._returned_ns:
            return
        self._last = (sfn, arrival_ns)
        if self._first is None:
            self._first = sfn
        if self._a is None:
            if sfn >= self._first + SETTLE_FRAMES - 1:
                self._a = (sfn, arrival_ns, float(brightness()))
                self._deadline = early_deadline_ns(arrival_ns, self.mode_rate)
            return
        if sfn >= self._a[0] + RATE_FRAMES:
            self._trial(rate_check.measured_rate(self._a[0], self._a[1], sfn, arrival_ns))
        elif arrival_ns > self._deadline:  # a later frame came after the deadline: frame s_a + 30 was not in time
            self._trial(rate_check.measured_rate(self._a[0], self._a[1], sfn, arrival_ns), early=True)

    def no_frame(self, now_ns: int) -> None:
        """No frame came by `now_ns` (the loop waited until `wake_ns`)."""
        if self.result is None and self._a is not None and now_ns >= self._deadline:
            sfn = self._last[0] if self._last is not None else self._a[0]
            self._trial(rate_check.measured_rate(self._a[0], self._a[1], sfn, now_ns), early=True)
        self.tick(now_ns)

    def tick(self, now_ns: int) -> None:
        if self.result is None and now_ns >= self.limit_ns:
            self._fail("timed-out", "it took more than 20 s")

    def cancel(self) -> None:
        """The group closed the camera, or it was unselected: no warning, and the search sets nothing (1.9)."""
        if self.result is None:
            self._fail("camera-closed", None)

    def _trial(self, measured: float, early: bool = False) -> None:
        kept = not early and not rate_check.is_slow(measured, self.mode_rate)
        self.trials.append(dict(value=self._value, brightness=self._a[2], measured_fps=measured, kept_rate=kept))
        index = VALUES.index(self._value) + 1
        self._returned_ns = None
        if index < len(VALUES):
            self.pending = VALUES[index]
            return
        chosen, add_light, reason = choose(self.trials)
        if reason is not None:
            self._fail(reason, f"no exposure from {VALUES[0]} to {VALUES[-1]} keeps {self.mode_rate:g} fps")
        else:
            self.result = dict(state="done", chosen=chosen, add_light=add_light, reason=None, trials=self.trials)

    def _fail(self, reason: str, detail: str | None) -> None:
        self.pending, self.detail = None, detail
        self.result = dict(state="failed", chosen=None, add_light=False, reason=reason, trials=self.trials)

    def take_pending(self) -> int | None:
        value, self.pending = self.pending, None
        return value


def add_light_text(camera_id: str, mode_rate: float, trials: list[dict]) -> str:
    """The text of the warning `add_light` (1.5) [A11]."""
    brightest = max((trial for trial in trials if trial["kept_rate"]), key=lambda trial: trial["value"])
    return (f"Camera {camera_id}: add light. At {mode_rate:g} fps the brightest exposure that keeps the rate is "
            f"{brightest['value']}, and the image is too dark (mean {brightest['brightness']:.0f} of 255).")


def failed_text(camera_id: str, detail: str, held: int) -> str:
    """The text of the warning `exposure_search_failed` (1.5) [A11]."""
    return f"Camera {camera_id}: the exposure search failed: {detail}. The exposure is {held} again."
