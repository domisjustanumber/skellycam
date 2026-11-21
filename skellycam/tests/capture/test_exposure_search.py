"""T-REQ-01 to T-REQ-09, the pure part: the exposure search of specs/camera-requests.md 1.3 as a function over
measurements, with no camera (`skellycam/core/camera/capture/exposure_search.py`).

`simulate` plays one camera on a time line in ns: each set returns at once, each frame has the interval of the
rate of the value that the camera has, and its image has the brightness of the value set `lag` frames before.
It wakes the search at `wake_ns` when no frame comes before it, as the loop does with its read limit. The
search with the loop and the fake source is in `test_camera_requests.py`.
"""

import pytest

T0 = 1_000_000_000_000

MODEL = {-12: 10, -11: 20, -10: 40, -9: 70, -8: 110, -7: 150, -6: 190, -5: 230}  # T-REQ-01


def simulate(brightness, rates=None, mode_rate=30.0, lag=0, until_s=60.0):
    """Run one search. Returns (search, the sets in order, the frames of each trial as (sfn, brightness))."""
    from skellycam.core.camera.capture.exposure_search import ExposureSearch

    rates = rates or {}
    search = ExposureSearch(mode_rate, T0)
    now, sfn, value, sets, set_at = T0, 0, -7, [], []  # set_at: (sfn of the first frame after the set, value)
    seen = []
    while search.result is None and now < T0 + until_s * 1e9:
        pending = search.take_pending()
        if pending is not None:
            value = pending
            sets.append(value)
            set_at.append((sfn, value))
            search.set_done(value, now)
        interval = round(1e9 / rates.get(value, mode_rate))
        if search.wake_ns < now + interval:
            now = max(now, search.wake_ns)
            search.no_frame(now)
            continue
        now += interval
        shown = next((v for s, v in reversed(set_at) if s <= sfn - lag), -7)
        gray = brightness[shown]
        seen.append((sfn, gray))
        search.frame(sfn, now, lambda gray=gray: gray)
        search.tick(now)
        sfn += 1
    search.ended_ns = now
    return search, sets, seen


def test_t_req_01_the_choice_is_one_step_darker_than_the_nearest():
    """T-REQ-01 (pure part), 1.3 [E6, Q5]: rate 30 at each value; the sets -12 to -5 in order; -8 is nearest to
    127.5, so the result is -9; no `add_light`."""
    search, sets, _ = simulate(MODEL)
    assert sets == list(range(-12, -4))
    assert search.result["state"] == "done" and search.result["chosen"] == -9 and not search.result["add_light"]
    assert [t["value"] for t in search.result["trials"]] == list(range(-12, -4))
    assert all(t["kept_rate"] and abs(t["measured_fps"] - 30.0) < 0.01 for t in search.result["trials"])


def test_t_req_02_a_value_that_loses_the_rate_is_never_kept():
    """T-REQ-02 (pure part), 1.3 item 2.5 [E7]: -6 and -5 at 15 fps: their trials have `kept_rate` false; the
    result is -9."""
    search, _, _ = simulate(MODEL, rates={-6: 15.0, -5: 15.0})
    trials = {t["value"]: t for t in search.result["trials"]}
    assert not trials[-6]["kept_rate"] and not trials[-5]["kept_rate"]
    assert search.result["chosen"] == -9


def test_t_req_03_the_c922_pattern_keeps_the_only_value_that_holds_60():
    """T-REQ-03 (pure part), 1.3 items 3 and 4 [E8, Q5]: mode 60 fps; 60 at -7 only, 29.7 at each other value;
    the brightness is nearest to 127.5 at -6. The result is -7 (-6 and -8 did not keep the rate). A rate is
    measured at each of the 8 values."""
    brightness = {-12: 5, -11: 10, -10: 20, -9: 40, -8: 70, -7: 100, -6: 128, -5: 200}
    rates = {value: 29.7 for value in range(-12, -4) if value != -7}
    search, _, _ = simulate(brightness, rates=rates, mode_rate=60.0)
    assert search.result["chosen"] == -7
    assert [t["value"] for t in search.result["trials"]] == list(range(-12, -4))
    assert all(t["measured_fps"] > 0 for t in search.result["trials"])


def test_t_req_04_too_little_light_holds_the_result_with_add_light():
    """T-REQ-04 (pure part), 1.3 item 5 [Q6]: brightness 50 at -5, darker below; rate 30 at each value. The
    result is -6 (nearest -5, then one darker) with `add_light`; the text of 1.5."""
    from skellycam.core.camera.capture.exposure_search import add_light_text

    brightness = {value: 50 - 5 * (-5 - value) for value in range(-12, -4)}
    search, _, _ = simulate(brightness)
    assert search.result["state"] == "done" and search.result["chosen"] == -6 and search.result["add_light"]
    assert add_light_text("a1b2", 30.0, search.result["trials"]) == (
        "Camera a1b2: add light. At 30 fps the brightest exposure that keeps the rate is -5, and the image is too "
        "dark (mean 50 of 255).")


def test_t_req_05_no_value_keeps_the_rate():
    """T-REQ-05 (pure part), 1.3 item 6 [E6]: the generic camera, 25.76 fps at each value: the search fails with
    `no-value-kept-rate` and the text of 1.5."""
    from skellycam.core.camera.capture.exposure_search import failed_text

    search, _, _ = simulate(MODEL, rates={value: 25.76 for value in range(-12, -4)})
    assert (search.result["state"], search.result["reason"], search.result["chosen"]) == (
        "failed", "no-value-kept-rate", None)
    assert failed_text("a1b2", search.detail, -7) == (
        "Camera a1b2: the exposure search failed: no exposure from -12 to -5 keeps 30 fps. The exposure is -7 again.")


def test_t_req_06_no_offset_out_of_the_range_or_to_a_slow_value():
    """T-REQ-06 (the choice part), 1.3 item 4 [Q5]: the nearest value -12 keeps -12; a darker value that lost
    the rate is not taken."""
    from skellycam.core.camera.capture.exposure_search import choose

    def trial(value, brightness, kept=True):
        return dict(value=value, brightness=brightness, measured_fps=30.0, kept_rate=kept)

    assert choose([trial(-12, 130), trial(-11, 200)]) == (-12, False, None)
    assert choose([trial(-9, 40, kept=False), trial(-8, 128), trial(-7, 200)]) == (-8, False, None)
    assert choose([trial(-8, 20), trial(-7, 30)]) == (-8, True, None)


def test_t_req_07_the_brightness_is_the_10th_frame_after_the_set_returned():
    """T-REQ-07 (pure part), 1.3 item 2.3 [Q4]: the image follows a new exposure only from the 3rd frame after
    the set. The brightness of each trial is the value of the 10th frame that arrived after the set returned, and
    the result is as in T-REQ-01."""
    search, _, seen = simulate(MODEL, lag=2)
    assert search.result["chosen"] == -9
    assert [t["brightness"] for t in search.result["trials"]] == [MODEL[v] for v in range(-12, -4)]


def test_t_req_08_the_early_decision_leaves_a_slow_value():
    """T-REQ-08 (pure part), 1.3 item 2.6 [A1]: one value at 10 fps, the others at 30. The search leaves the slow
    value at t_a + 30 / (0.97 x 30) s, within 25 ms; that trial has `kept_rate` false."""
    from skellycam.core.camera.capture.exposure_search import ExposureSearch

    search = ExposureSearch(30.0, T0)
    assert search.take_pending() == -12
    search.set_done(-12, T0)
    period = round(1e9 / 10)
    t, sfn = T0, 0
    while search.result is None and not search.trials:
        if search.wake_ns < t + period:
            decided = search.wake_ns
            search.no_frame(decided)
            break
        t += period
        search.frame(sfn, t, lambda: 100.0)
        sfn += 1
    t_a = T0 + 10 * period  # the 10th frame after the set
    assert abs((decided - t_a) / 1e9 - 30 / (0.97 * 30)) <= 0.025
    assert search.trials[0]["kept_rate"] is False and search.pending == -11


def test_t_req_09_the_search_fails_at_20_s():
    """T-REQ-09 (pure part), 1.3 item 6 [A2]: each value at 5 fps. The search fails at 20 s (within 0.25 s)
    from its first set, with the reason `timed-out` and the text of 1.5."""
    search, _, seen = simulate(MODEL, rates={value: 5.0 for value in range(-12, -4)})
    assert (search.result["state"], search.result["reason"]) == ("failed", "timed-out")
    assert search.detail == "it took more than 20 s"
    assert abs((search.ended_ns - T0) / 1e9 - 20.0) <= 0.25


@pytest.mark.parametrize(("error", "readback", "reason", "detail"), [
    ("the camera refused the value", None, "set-failed", "the camera refused exposure -12 (the camera refused the value)"),
    (None, -11, "readback-differs", "exposure -12 read back as -11")])
def test_t_req_17_a_failed_set_ends_the_search(error, readback, reason, detail):
    """T-REQ-17 (pure part), 1.3 item 6, 1.5: a set that returns an error, and a read-back that differs."""
    from skellycam.core.camera.capture.exposure_search import ExposureSearch

    search = ExposureSearch(30.0, T0)
    search.set_done(search.take_pending(), T0, error=error, readback=readback)
    assert (search.result["state"], search.result["reason"], search.detail) == ("failed", reason, detail)
    assert search.pending is None
