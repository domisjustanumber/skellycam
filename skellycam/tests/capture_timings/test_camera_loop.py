"""The steps of the camera loop: T-TIM-05, T-TIM-06, T-TIM-08 (loop part), T-TIM-09, T-TIM-10, T-TIM-14 to T-TIM-17
and T-TIM-23 (specs/capture-timings.md 2, 3.1, 4, 5.1 to 5.4, 6.2).

The loop runs on the test thread with a virtual clock (`loop_harness`). A fake moves the clock by a known time in
each call, so each sample has an exact value. No camera and no real wait.
"""

import pickle
import threading
from types import SimpleNamespace

import cv2

from skellycam.tests.capture_timings.loop_harness import (
    CAMERA_ID, GROUP_ID, MS, ScriptSource, VClock, count_reads, end_take, frames, loop_module, make_loop,
    opencv_source, slow, start_take, summary, switch_on, timings)
from skellycam.tests.capture_timings.test_statistics import assert_known_ids

FRAME_LOG = [[k, k, 1_000_000 + k, 2_000_000 + k, 50_000 + k] for k in range(64)]  # the dict of T-UNX-70


def entry(summary_, step_id):
    return summary_["steps"][step_id]


def values(summary_, step_id, group="steps"):
    item = summary_[group][step_id]
    return item["n"], item["p50_ms"], item["max_ms"]


def mf_loop(monkeypatch, clock, **kwargs):
    """A loop on the Media Foundation fake: 30 ms reads, a 0.05 ms callback copy, 0.2 ms checks, 0.3 ms hashes,
    0.4 ms ring writes and 0.6 ms of `source.diagnostics()`."""
    module = timings()
    source = ScriptSource(clock, read_ns=30 * MS, copy_ns=50_000, timing_steps=module.MEDIA_FOUNDATION_STEPS)
    source.diagnostics_ns = 600_000
    loop = make_loop(monkeypatch, clock, source, ring_ns=400_000, **kwargs)
    monkeypatch.setattr(loop_module(), "check_jpeg", slow(clock, loop_module().check_jpeg, 200_000))
    monkeypatch.setattr(loop, "_hash", slow(clock, loop._hash, 300_000))
    return loop


def test_t_tim_05_off_costs_no_clock_read(monkeypatch, tmp_path):
    """T-TIM-05: with the switch off, the loop (also a hash, a take, the OpenCV source and an encode) calls
    `TimingControl.clock()` zero times, and each `DiagnosticsMessage.timings` is None."""
    clock = VClock()
    reads = count_reads(monkeypatch)
    loop = make_loop(monkeypatch, clock, opencv_source(monkeypatch, clock))
    loop._arm_hashes("ready")
    frames(loop, 5)
    start_take(loop, tmp_path)
    frames(loop, 5)
    end_take(loop)
    loop._publish_diagnostics()
    clock.advance(2_000_000_000)
    frames(loop, 2)  # a pass publishes after the interval
    assert reads == []
    assert len(loop.diagnostics) == 2 and all(message.timings is None for message in loop.diagnostics)


def test_t_tim_06_a_summary_with_each_step_that_applies(monkeypatch):
    """T-TIM-06: a fake source whose steps take scripted virtual times gives a summary with each step of 5.4 that
    applies, the expected n and values, and the kind, cadence and where of table 3.1."""
    module = timings()
    clock = VClock()
    loop = mf_loop(monkeypatch, clock)
    loop._arm_hashes("ready")
    switch_on(loop)
    frames(loop, 5)
    first = summary(loop)
    frames(loop, 3)
    second = summary(loop)
    assert set(first["steps"]) == set(module.CAMERA_STEPS) | set(module.MEDIA_FOUNDATION_STEPS)
    assert set(first["delays"]) == {"arrival_to_published"}
    assert (first["source"], first["camera_group_id"], first["camera_id"], first["clock"]) == (
        "camera", GROUP_ID, CAMERA_ID, "perf_counter_ns")
    assert (first["seq"], second["seq"]) == (0, 1)
    assert first["window_s"] == 0.155 and first["window_end_ns"] < second["window_end_ns"]
    assert values(first, "camera_wait") == (5, 30.05, 30.05)  # the fake copy runs inside its read
    assert values(first, "gate_wait") == (5, 0.0, 0.0)
    assert values(first, "camera_sample_copy") == (5, 0.05, 0.05)
    assert values(first, "capture_check") == (5, 0.2, 0.2)
    assert values(first, "frame_hash") == (5, 0.3, 0.3)
    assert values(first, "ring_write") == (5, 0.4, 0.4)
    assert values(first, "arrival_to_published", "delays") == (5, 0.9, 0.9)
    for step_id in ("recorder_give", "exposure_search_brightness", "take_start", "take_end", "mkv_mux", "csv_row",
                    "fsync", "mkv_close", "diagnostics_publish"):
        assert values(first, step_id) == (0, None, None), step_id
    assert values(second, "diagnostics_publish") == (1, 0.6, 0.6)  # the publish that ended the first window
    assert values(second, "camera_wait")[0] == 3
    assert_known_ids(first)


def test_t_tim_09_the_steps_of_each_source(monkeypatch):
    """T-TIM-09: the Media Foundation fake has `camera_sample_copy` and no `jpeg_encode` or `opencv_retrieve`; the
    OpenCV source is the reverse; with no BGR ring there is no `bgr_*` step, and with one there are both; each has
    `exposure_search_brightness`."""
    clock = VClock()
    loop = mf_loop(monkeypatch, clock)
    switch_on(loop)
    frames(loop, 2)
    mf = summary(loop)
    loop = make_loop(monkeypatch, clock, opencv_source(monkeypatch, clock), bgr_ring=True)
    switch_on(loop)
    frames(loop, 2)
    opencv = summary(loop)
    assert "camera_sample_copy" in mf["steps"] and not {"jpeg_encode", "opencv_retrieve"} & set(mf["steps"])
    assert {"jpeg_encode", "opencv_retrieve"} <= set(opencv["steps"]) and "camera_sample_copy" not in opencv["steps"]
    assert not {"bgr_decode", "bgr_ring_write"} & set(mf["steps"])
    assert {"bgr_decode", "bgr_ring_write"} <= set(opencv["steps"])
    assert "exposure_search_brightness" in mf["steps"] and "exposure_search_brightness" in opencv["steps"]
    assert values(opencv, "opencv_retrieve") == (2, 5.0, 5.0)


def test_t_tim_10_the_brackets_of_the_waits(monkeypatch):
    """T-TIM-10: `camera_wait` plus `opencv_retrieve` is the time of the `_read` calls of a frame; reads with no
    frame add to the next frame; `gate_wait` holds no time of `_check_updates` or `_publish_diagnostics`; a frame with
    no refused pass gives 0."""
    clock = VClock()
    loop = make_loop(monkeypatch, clock, opencv_source(monkeypatch, clock, grab_ns=20 * MS, retrieve_ns=5 * MS))
    switch_on(loop)
    frames(loop, 3)
    opencv = summary(loop)
    assert values(opencv, "camera_wait") == (3, 20.0, 20.0)
    assert values(opencv, "opencv_retrieve") == (3, 5.0, 5.0)

    source = ScriptSource(clock, read_ns=10 * MS, empty=(1,))
    loop = make_loop(monkeypatch, clock, source)
    monkeypatch.setattr(loop, "_check_updates", slow(clock, loop._check_updates, 7 * MS))
    source.diagnostics_ns = 9 * MS
    switch_on(loop)
    frames(loop, 1)  # read 0: a frame, no refused pass
    loop.gate.script = [(False, 2 * MS), (False, 2 * MS)]  # frame 1: two refused passes
    loop.next_diagnostics_ns = clock.now()  # and a publish in its first pass, outside the gate
    frames(loop, 1)  # reads 1 (no frame) and 2
    window = summary(loop)
    assert values(window, "camera_wait") == (1, 20.0, 20.0)  # the read with no frame adds to frame 1
    assert values(window, "gate_wait") == (1, 4.0, 4.0)
    first_window = loop.diagnostics[-2].timings
    assert values(first_window, "gate_wait") == (1, 0.0, 0.0)
    assert values(first_window, "camera_wait") == (1, 10.0, 10.0)


def test_t_tim_14_the_delay_from_the_arrival_to_the_ring(monkeypatch):
    """T-TIM-14: `arrival_to_published` is the end of the `ring_write` bracket minus `arrival_ns`."""
    clock = VClock()
    loop = make_loop(monkeypatch, clock, ScriptSource(clock), ring_ns=1_500_000)
    monkeypatch.setattr(loop_module(), "check_jpeg", slow(clock, loop_module().check_jpeg, 250_000))
    switch_on(loop)
    frames(loop, 4)
    window = summary(loop)
    assert values(window, "arrival_to_published", "delays") == (4, 1.75, 1.75)
    assert values(window, "ring_write") == (4, 1.5, 1.5)


def test_t_tim_15_one_reader(monkeypatch):
    """T-TIM-15: a publish of another thread (the control thread calls `_fail` at a hang) sends the last summary again
    with the same `seq` and reads no buffer; with no earlier summary it sends None. The next loop publish has
    `seq` + 1 and each sample one time."""
    from skellycam.core.camera.capture.source import CaptureFailure

    clock = VClock()
    loop = make_loop(monkeypatch, clock, ScriptSource(clock))
    switch_on(loop)
    other = threading.Thread(target=loop._publish_diagnostics)
    other.start()
    other.join(10)
    assert loop.diagnostics[-1].timings is None  # no summary yet
    frames(loop, 3)
    first = summary(loop)
    frames(loop, 2)
    failing = threading.Thread(target=loop._fail, args=(CaptureFailure("streaming", "a hang"),))
    failing.start()
    failing.join(10)
    assert loop.diagnostics[-1].timings == first and loop.diagnostics[-1].timings["seq"] == 0
    second = summary(loop)
    assert second["seq"] == 1 and values(second, "camera_wait")[0] == 2


def test_t_tim_16_the_publishes_of_the_open_a_failure_and_the_close(monkeypatch):
    """T-TIM-16 (loop part): with the switch on from the start, the publishes at the end of the open, at a failure on
    the loop thread and at the close carry `timings`; `seq` increases by 1 at each; `window_end_ns` increases. The
    warm-up reads are not measured; the callback copies of the warm-up are."""
    from skellycam.core.camera.capture.source import CaptureFailure

    module = timings()
    clock = VClock()
    source = ScriptSource(clock, read_ns=33_333_333, copy_ns=50_000, timing_steps=module.MEDIA_FOUNDATION_STEPS)
    loop = make_loop(monkeypatch, clock, source, state="starting", on=True)
    try:
        loop._start_up()
        opened = loop.diagnostics[-1].timings
        assert opened is not None and values(opened, "camera_wait")[0] == 0
        assert values(opened, "camera_sample_copy")[0] >= 90
        loop.status.set_state("ready")
        frames(loop, 3)
        loop._fail(CaptureFailure("streaming", "a test failure"))
        failed = loop.diagnostics[-1].timings
        clock.advance(1 * MS)
        loop._end(False)
        closed = loop.diagnostics[-1].timings
    finally:
        loop._stop_control()
    assert [opened["seq"], failed["seq"], closed["seq"]] == [0, 1, 2]
    assert opened["window_end_ns"] < failed["window_end_ns"] < closed["window_end_ns"]
    assert values(failed, "camera_wait")[0] == 3


def test_t_tim_08_a_change_during_the_start_up_and_during_a_take_end(monkeypatch, tmp_path):
    """T-TIM-08 (loop part): a change during the start-up applies at the publish at the end of the open; a change
    during the `take_end` wait applies at the first publish after it."""
    module = timings()
    clock = VClock()

    def switch_on_at_read_10(source_, call):
        if call == 10:
            loop.status.log_capture_times.value = True

    source = ScriptSource(clock, read_ns=33_333_333, copy_ns=50_000, timing_steps=module.MEDIA_FOUNDATION_STEPS,
                          on_read=switch_on_at_read_10)
    loop = make_loop(monkeypatch, clock, source, state="starting")
    try:
        loop._start_up()
        assert loop.timing.on and loop.diagnostics[-1].timings is None  # the first window starts here
        loop.status.set_state("ready")
        frames(loop, 3)
        window = summary(loop)
        assert values(window, "camera_sample_copy")[0] == 3 and values(window, "camera_wait")[0] == 3

        start_take(loop, tmp_path)
        frames(loop, 2)
        writer = loop.take_writer
        end = writer.end

        def end_with_a_change(frame_count):
            loop.status.log_capture_times.value = False
            return end(frame_count)

        monkeypatch.setattr(writer, "end", end_with_a_change)
        end_take(loop)
        assert loop.timing.on  # not yet: the loop applies the change at its next publish
        loop._publish_diagnostics()
        assert not loop.timing.on and loop.diagnostics[-1].timings is None
    finally:
        loop._stop_control()


def test_t_tim_17_the_size_of_the_message(monkeypatch):
    """T-TIM-17: the diagnostics message with all camera steps, the largest dict of T-UNX-70 (64 `frame_log` rows and
    30 hashes) and the summary stays under 32 KiB; the summary is under 4 KiB pickled, also with 512 samples of each
    step."""
    module = timings()
    clock = VClock()
    source = ScriptSource(clock, copy_ns=10_000, diagnostics={"frame_log": FRAME_LOG},
                          timing_steps=module.MEDIA_FOUNDATION_STEPS + module.OPENCV_STEPS)
    loop = make_loop(monkeypatch, clock, source, bgr_ring=True)
    loop._arm_hashes("ready")
    switch_on(loop)
    frames(loop, 40)
    window = summary(loop)
    message = loop.diagnostics[-1]
    assert message.diagnostics["sha256_29"] is not None and len(message.diagnostics["frame_log"]) == 64
    ids = set(module.CAMERA_STEPS) | set(module.MEDIA_FOUNDATION_STEPS) | set(module.OPENCV_STEPS) | set(module.BGR_STEPS)
    assert set(window["steps"]) == ids
    assert len(pickle.dumps(message)) < 32 * 1024
    assert len(pickle.dumps(window)) < 4 * 1024
    full = module.build_summary(source="camera", camera_group_id=GROUP_ID, camera_id=CAMERA_ID,
                                clock="perf_counter_ns", seq=10**9, window_end_ns=2**62, window_ns=10**9,
                                step_ids=sorted(ids | {"arrival_to_published"}),
                                windows={i: (100_000, list(range(10**6, 10**6 + 512))) for i in ids})
    assert len(pickle.dumps(full)) < 4 * 1024


def test_t_tim_23_the_clock_reads_of_each_frame(monkeypatch, tmp_path):
    """T-TIM-23: with the switch on, the loop thread calls `TimingControl.clock()` at most 10 times for each frame plus
    one time for each refused pass: the OpenCV source with an encode, the hashes and a take. Then with the brightness
    of an exposure search on each frame: a step of cadence `event` adds its own 2 reads (ADR entry of the build)."""
    clock = VClock()
    loop = make_loop(monkeypatch, clock, opencv_source(monkeypatch, clock))
    monkeypatch.setattr(cv2, "imencode", slow(clock, cv2.imencode, 1 * MS))
    switch_on(loop)
    start_take(loop, tmp_path)
    loop._arm_hashes("recording")
    reads = count_reads(monkeypatch)
    me = threading.get_ident()
    loop.gate.script = [(False, 1 * MS), (True, 0), (False, 1 * MS), (False, 1 * MS)]  # 3 refused passes
    frames(loop, 10)
    in_loop = sum(ident == me for ident in reads)
    assert 0 < in_loop <= 10 * 10 + 3, in_loop
    end_take(loop)

    loop.search = SimpleNamespace(wake_ns=None, frame=lambda sfn, arrival, brightness: brightness(),
                                  no_frame=lambda now: None)
    monkeypatch.setattr(loop, "_search_step", lambda: None)
    loop._arm_hashes("ready")
    reads.clear()
    frames(loop, 10)
    in_loop = sum(ident == me for ident in reads)
    assert 0 < in_loop <= 10 * 10 + 2 * 10, in_loop
    loop.search = None
    window = summary(loop)
    assert window["steps"]["exposure_search_brightness"]["n"] == 10
