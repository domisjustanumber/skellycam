"""The other threads of the camera process: T-TIM-11 to T-TIM-13, and the callback bracket of the real Media Foundation
source (specs/capture-timings.md 3.1, 5.1).

No camera and no real wait: a fake moves the virtual clock, and a full queue is released by the wait itself.
"""

import sys
import threading
import time

import pytest

from skellycam.tests.capture_timings.loop_harness import (
    JPEG, MS, FakeRing, ScriptSource, VClock, end_take, frames, loop_module, make_loop, slow, start_take, summary,
    switch_on, take_spec, timings)
from skellycam.tests.capture_timings.test_statistics import assert_known_ids


def values(summary_, step_id):
    item = summary_["steps"][step_id]
    return item["n"], item["p50_ms"], item["max_ms"]


def wait_until(predicate, what, timeout=10.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, f"timed out: {what}"
        time.sleep(0.001)


def recorder_frame(k, arrival_ns):
    from skellycam.core.take_recorder import RecorderFrame
    return RecorderFrame(payload=JPEG, frame_number=k, arrival_ns=arrival_ns, sample_ns=arrival_ns - 1000,
                         source_frame_number=k, flags=0, delivered_len=len(JPEG), rotation_cw_deg=0)


def test_t_tim_11_retired_sets_go_into_the_next_summary(monkeypatch, tmp_path):
    """T-TIM-11: after a reopen, a new decode stage and a new take, the next summary holds the samples of the old
    instances; an old thread that writes after that writes only into its own set, and the n of the new set is
    exact."""
    module = timings()
    clock = VClock()
    old = ScriptSource(clock, copy_ns=50_000, timing_steps=module.MEDIA_FOUNDATION_STEPS)
    loop = make_loop(monkeypatch, clock, old, bgr_ring=True)
    switch_on(loop)
    frames(loop, 3)

    new = ScriptSource(clock, copy_ns=70_000, timing_steps=module.MEDIA_FOUNDATION_STEPS)
    loop.source_factory = lambda config: new
    monkeypatch.setattr(loop, "_start_up", lambda: setattr(loop, "source", loop._new_source(loop.config)))
    loop._reopen(loop.config)
    assert old.closed and loop.source is new
    loop.ring_writer = FakeRing(clock)
    loop.status.set_state("ready")
    frames(loop, 1)

    bgr = FakeRing(clock, name="bgr")
    loop._start_decode(bgr)
    for k in range(2):
        frames(loop, 1)
        wait_until(lambda: len(bgr.writes) == k + 1, "a BGR ring write")
    loop._close_rings()  # the decode stage stops
    loop.ring_writer = FakeRing(clock)

    start_take(loop, tmp_path)
    frames(loop, 2)
    end_take(loop)

    window = summary(loop)
    assert values(window, "camera_sample_copy") == (3 + 5, 0.07, 0.07)
    assert window["steps"]["camera_sample_copy"]["p95_ms"] == 0.07
    assert values(window, "bgr_decode")[0] == 2 and values(window, "bgr_ring_write")[0] == 2
    assert values(window, "mkv_mux")[0] == 2 and values(window, "csv_row")[0] == 2
    assert [values(window, step)[0] for step in ("take_start", "take_end", "mkv_close")] == [1, 1, 1]

    late = threading.Thread(target=old.read_frame, args=(0.0,))  # a late callback of the old source
    late.start()
    late.join(10)
    frames(loop, 2)
    after = summary(loop)
    assert values(after, "camera_sample_copy") == (2, 0.07, 0.07)
    for step_id in ("bgr_decode", "mkv_mux", "take_end"):
        assert values(after, step_id)[0] == 0
    assert_known_ids(window)


def test_t_tim_12_the_steps_of_the_writer_thread(monkeypatch, tmp_path):
    """T-TIM-12 (writer thread): scripted mux, row write, fsync and close times give `mkv_mux`, `csv_row` and
    `fsync`; `mkv_close` holds no time of the `mkv_mux`, `csv_row` and `fsync` of `_finish`."""
    from skellycam.core.take_recorder import camera_writer, mkv

    module = timings()
    clock = VClock()
    monkeypatch.setattr(mkv.MkvFile, "mux", slow(clock, mkv.MkvFile.mux, 400 * MS))
    monkeypatch.setattr(mkv.MkvFile, "fsync", slow(clock, mkv.MkvFile.fsync, 2 * MS))
    monkeypatch.setattr(mkv.MkvFile, "close_container", slow(clock, mkv.MkvFile.close_container, 5 * MS))
    writer_class = camera_writer.CameraTakeWriter
    monkeypatch.setattr(writer_class, "_write_line", slow(clock, writer_class._write_line, 1 * MS))
    control = module.TimingControl(clock.now)
    control.on = True
    writer = writer_class.start(take_spec(tmp_path), clock=clock.now, timing=control)
    for k in range(3):
        writer.give(recorder_frame(k, clock.now()))
    result = writer.end(3)
    assert result.error is None and result.rows == 3
    windows = module.WindowReader().read([writer.timing_set])
    assert module.stats(*windows["mkv_mux"]) == dict(n=3, p50_ms=400.0, p95_ms=400.0, max_ms=400.0)
    assert module.stats(*windows["csv_row"]) == dict(n=3, p50_ms=1.0, p95_ms=1.0, max_ms=1.0)
    assert module.stats(*windows["fsync"]) == dict(n=2, p50_ms=2.0, p95_ms=2.0, max_ms=2.0)  # 1 s, then the end
    assert module.stats(*windows["mkv_close"]) == dict(n=1, p50_ms=6.0, p95_ms=6.0, max_ms=6.0)  # close + end line
    assert set(windows) <= set(module.RECORDER_STEPS)


def test_t_tim_12_the_take_steps_of_the_loop(monkeypatch, tmp_path):
    """T-TIM-12 (loop thread): a full queue (`queue_size` 1, a mux that waits on an event) gives a `recorder_give`
    sample equal to the virtual wait; a take gives one `take_start`, one `take_end` and one `mkv_close`; no take
    gives n 0 (T-TIM-06)."""
    from skellycam.core.take_recorder import camera_writer, mkv

    clock = VClock()
    loop = make_loop(monkeypatch, clock, ScriptSource(clock))
    release = threading.Event()
    mux = mkv.MkvFile.mux

    def waiting_mux(self, *args):
        release.wait(10)
        return mux(self, *args)

    monkeypatch.setattr(mkv.MkvFile, "mux", waiting_mux)
    wait = camera_writer.CameraTakeWriter._wait_with_progress

    def virtual_wait(self, started, attempt):
        clock.advance(5 * MS)  # the virtual time of each wait for space or for the writer thread
        release.set()
        return wait(self, started, attempt)

    monkeypatch.setattr(camera_writer.CameraTakeWriter, "_wait_with_progress", virtual_wait)
    monkeypatch.setattr(loop_module(), "start_take_writer", slow(clock, loop_module().start_take_writer, 3 * MS))
    switch_on(loop)
    start_take(loop, tmp_path, queue_size=1)
    frames(loop, 3)
    end_take(loop)
    window = summary(loop)
    result = loop.finished[-1].result
    assert result is not None and result.give_wait_count >= 1
    give = window["steps"]["recorder_give"]
    assert give["n"] == 3 and give["max_ms"] == 5.0
    assert values(window, "take_start") == (1, 3.0, 3.0)
    assert [values(window, step)[0] for step in ("take_end", "mkv_close")] == [1, 1]


def test_t_tim_13_the_decode_thread(monkeypatch):
    """T-TIM-13: a fake decode of scripted time gives `bgr_decode`, and a fake BGR ring `bgr_ring_write`; a BGR input
    gives no `bgr_decode` sample."""
    import numpy as np

    from skellycam.core.ipc.frame_ring import DecodeInput, DecodeStage, decode_jpeg

    module = timings()
    clock = VClock()
    control = module.TimingControl(clock.now)
    control.on = True
    ring = FakeRing(clock, write_ns=2 * MS, name="bgr")
    stage = DecodeStage(ring, decode=slow(clock, decode_jpeg, 7 * MS), timing=control)
    stage.start()
    try:
        image = np.zeros((48, 64, 3), np.uint8)
        for k, (payload, kind) in enumerate([(JPEG, "JPEG")] * 3 + [(image, "BGR")] * 2):
            stage.waiting_place.put(DecodeInput(payload=payload, source=kind, frame_number=k, arrival_ns=0,
                                                sample_ns=0, source_frame_number=k, flags=0, rotation_cw_deg=0))
            wait_until(lambda: len(ring.writes) == k + 1, "a BGR ring write")
    finally:
        stage.stop()
    windows = module.WindowReader().read([stage.timing_set])
    assert module.stats(*windows["bgr_decode"]) == dict(n=3, p50_ms=7.0, p95_ms=7.0, max_ms=7.0)
    assert module.stats(*windows["bgr_ring_write"]) == dict(n=5, p50_ms=2.0, p95_ms=2.0, max_ms=2.0)


@pytest.mark.skipif(sys.platform != "win32", reason="the media_foundation package is Windows only (U18)")
def test_t_tim_09_the_callback_bracket_of_media_foundation():
    """T-TIM-09 (the real source): `MediaFoundationSource` over the stand-ins of `mf_standins.py` gives one
    `camera_sample_copy` sample for each sample of the callback, of two reads of its clock."""
    from skellycam.tests.capture.test_media_foundation_source import run_case

    result = run_case("timings")
    assert result["frames"] == 10
    assert len(result["copy_samples"]) >= 10 and set(result["copy_samples"]) == {1000}
