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


def simulate(brightness, rates=None, mode_rate=30.0, lag=0, until_s=60.0, exposure_range=None, slow_first=None):
    """Run one search. Returns (search, the sets in order, the frames of each trial as (sfn, brightness)).
    `slow_first`: {value: rate} for the first 40 frames after the set of that value (then `rates` or the mode rate)."""
    from skellycam.core.camera.capture.exposure_search import ExposureSearch

    rates, slow_first = rates or {}, slow_first or {}
    search = ExposureSearch(mode_rate, T0, exposure_range)
    now, sfn, value, sets, set_at = T0, 0, -7, [], []  # set_at: (sfn of the first frame after the set, value)
    seen, last = [], T0  # last: the arrival of the last frame; a wake of the search does not move the next frame
    while search.result is None and now < T0 + until_s * 1e9:
        pending = search.take_pending()
        if pending is not None:
            value = pending
            sets.append(value)
            set_at.append((sfn, value))
            search.set_done(value, now)
        early = value in slow_first and sfn - set_at[-1][0] < 40
        due = last + round(1e9 / (slow_first[value] if early else rates.get(value, mode_rate)))
        if search.wake_ns < due:
            now = max(now, search.wake_ns)
            search.no_frame(now)
            continue
        now = last = max(now, due)
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


def test_t_req_77_a_borderline_value_is_measured_again_before_it_is_dropped(caplog):
    """T-REQ-77, 1.3 item 2.7 [Q522, NYT6]: -8 reads 28.1 fps in its first window, then 30 fps: it is measured again
    and kept, so the result is -9 (with -8 dropped it is -7). The repeat costs about 1.0 s at 30 fps. A value that
    stays at 28.1 fps is dropped after the second window; a value at 25 fps (more than 10 % below) is not measured
    again. Each value is set one time."""
    import logging

    baseline, _, _ = simulate(MODEL)
    with caplog.at_level(logging.INFO):
        search, sets, _ = simulate(MODEL, slow_first={-8: 28.1})
    assert sets == list(range(-12, -4))
    assert search.result["chosen"] == -9
    trial = {t["value"]: t for t in search.result["trials"]}[-8]
    assert trial["kept_rate"] and trial["measured_fps"] > 29.1 and trial["brightness"] == MODEL[-8]
    assert len([m for m in caplog.messages if "measures -8 again" in m]) == 1
    added_s = (search.ended_ns - baseline.ended_ns) / 1e9
    assert 0.9 <= added_s <= 1.2, added_s

    for rate, windows in ((28.1, 2), (25.0, 1)):
        search, sets, _ = simulate(MODEL, rates={-8: rate})
        assert sets == list(range(-12, -4))
        trial = {t["value"]: t for t in search.result["trials"]}[-8]
        assert not trial["kept_rate"] and search.result["chosen"] == -7
        added_s = (search.ended_ns - baseline.ended_ns) / 1e9
        assert (added_s > 0.9) == (windows == 2), (rate, added_s)


@pytest.mark.parametrize(("error", "readback", "reason", "detail"), [
    ("the camera refused the value", None, "set-failed", "the camera refused exposure -12 (the camera refused the value)"),
    (None, -11, "readback-differs", "exposure -12 read back as -11")])
def test_t_req_17_a_failed_set_ends_the_search(error, readback, reason, detail):
    """T-REQ-17 (pure part), 1.3 item 6, 1.5: a set that returns an error, and a read-back that differs, on a camera
    that gives its range (with no range the value is skipped [GEH0])."""
    from skellycam.core.camera.capture.exposure_search import ExposureSearch

    search = ExposureSearch(30.0, T0, (-13, 0, 1))
    search.set_done(search.take_pending(), T0, error=error, readback=readback)
    assert (search.result["state"], search.result["reason"], search.detail) == ("failed", reason, detail)
    assert search.pending is None


MODEL_WIDE = {**MODEL, -4: 250, -3: 252, -2: 254}


@pytest.mark.parametrize(("exposure_range", "tried", "chosen"), [((-11, -2, 1), list(range(-11, -4)), -9),
                                                                 ((-7, 3, 1), [-7, -6, -5], -7)])
def test_the_search_tries_only_the_values_in_the_range_of_the_camera(exposure_range, tried, chosen):
    """camera-requests.md 1.3 item 1 [GEH0]: the lab cameras have -11 to -2, the generic camera -7 to 3. The search
    tries the values of -12 to -5 in that range, in the same order, and finds a value (-7 to 3: -7 is nearest to
    127.5; its darker step -8 was not tried, so -7 stays)."""
    search, sets, _ = simulate(MODEL_WIDE, exposure_range=exposure_range)
    assert sets == tried
    assert (search.result["state"], search.result["chosen"]) == ("done", chosen)


def test_a_range_with_no_value_of_the_search_fails_at_once():
    """camera-requests.md 1.3 item 6, 1.5 [GEH0]: no value of -12 to -5 in the range: the reason `no-value-in-range`,
    no set, and the text of 1.5."""
    from skellycam.core.camera.capture.exposure_search import ExposureSearch, failed_text

    search = ExposureSearch(30.0, None, (-4, 3, 1))
    assert (search.result["state"], search.result["reason"], search.take_pending()) == ("failed", "no-value-in-range",
                                                                                       None)
    assert failed_text("a1b2", search.detail, -4) == (
        "Camera a1b2: the exposure search failed: no exposure from -12 to -5 is in the range of the camera (-4 to 3). "
        "The exposure is -4 again.")


def test_the_limit_of_20_s_starts_at_the_first_set():
    """camera-requests.md 1.3 item 6 [A2]: the limit counts from the first set, not from the start of the search."""
    from skellycam.core.camera.capture.exposure_search import ExposureSearch

    search = ExposureSearch(30.0)
    assert search.wake_ns is None
    search.tick(T0 + 100 * 10**9)
    assert search.result is None
    assert search.take_pending(T0) == -12
    search.tick(T0 + 19_900_000_000)
    assert search.result is None
    search.tick(T0 + 20_000_000_000)
    assert search.result["reason"] == "timed-out"


def test_a_measuring_frame_that_does_not_decode_passes_to_the_next_frame():
    """camera-requests.md 1.3 item 2.3 [GEH0]: the 10th frame after the set has error flags (the brightness call gives
    None): the 11th frame measures, and the rate window starts there. No brightness 0."""
    from skellycam.core.camera.capture.exposure_search import ExposureSearch

    search = ExposureSearch(30.0, T0)
    search.set_done(search.take_pending(), T0)
    period = round(1e9 / 30)
    for sfn in range(60):
        search.frame(sfn, T0 + (sfn + 1) * period, lambda sfn=sfn: None if sfn == 9 else 100.0 + sfn)
        if search.trials:
            break
    assert search.trials[0]["brightness"] == 110.0 and search.trials[0]["kept_rate"]
    assert sfn == 10 + 30, "the window starts at the 11th frame"



@pytest.mark.parametrize("fault", ["refuse", "clamp"])
def test_with_no_range_a_value_that_cannot_be_set_is_skipped(fault):
    """camera-requests.md 1.3 item 6 [GEH0, supervisor]: a source with no range (OpenCV); the camera refuses -12 (an
    error) or clamps it to -11 (a different read-back). The search skips -12 as not supported, lists it, tries -11
    to -5 and finds a value."""
    from skellycam.core.camera.capture.exposure_search import ExposureSearch

    search = ExposureSearch(30.0, T0)
    value = search.take_pending()
    assert value == -12
    search.set_done(-12, T0, error="refused" if fault == "refuse" else None, readback=-11 if fault == "clamp" else None)
    assert search.result is None and search.pending == -11 and search.skipped == [-12]
    period, now, sfn = round(1e9 / 30), T0, 0
    while search.result is None:
        pending = search.take_pending()
        if pending is not None:
            search.set_done(pending, now)
        now += period
        gray = dict(MODEL)[search._value] if search._value is not None else 0
        search.frame(sfn, now, lambda gray=gray: gray)
        sfn += 1
    assert (search.result["state"], search.result["chosen"], search.result["skipped"]) == ("done", -9, [-12])
    assert [t["value"] for t in search.result["trials"]] == list(range(-11, -4))


def test_with_no_range_and_no_value_that_can_be_set_the_search_fails():
    """[GEH0, supervisor]: no value could be set: the reason `no-value-in-range`."""
    from skellycam.core.camera.capture.exposure_search import ExposureSearch

    search = ExposureSearch(30.0, T0)
    while search.result is None:
        search.set_done(search.take_pending(), T0, error="refused")
    assert (search.result["reason"], search.result["skipped"]) == ("no-value-in-range", list(range(-12, -4)))
    assert search.detail == "no exposure from -12 to -5 could be set on the camera"


def test_with_a_range_a_refused_value_inside_it_still_fails_and_the_step_grid_is_kept():
    """[GEH0]: with a range, a refused set inside it fails the search as before. A value off the step grid of
    GetRange is left out: the range -11 to -2 with the step 2 gives -11, -9, -7, -5."""
    from skellycam.core.camera.capture.exposure_search import ExposureSearch

    search = ExposureSearch(30.0, T0, (-11, -2, 1))
    search.set_done(search.take_pending(), T0, error="refused")
    assert search.result["reason"] == "set-failed"
    assert ExposureSearch(30.0, T0, (-11, -2, 2)).values == (-11, -9, -7, -5)
