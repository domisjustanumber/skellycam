"""Frame ring races, kills and lookups: T-RING-08, 09, 11, 12, 13, 14
(specs/frame-ring.md, sections 5.4, 6, 10 and 12).

Each child process uses the `spawn` start method. The `procs` fixture kills each live child.
Each wait has a timeout.
"""

import random
import threading
import time

import numpy as np
import pytest

from skellycam.tests.frame_ring import ring_children
from skellycam.tests.pace import margin
from skellycam.tests.frame_ring.ring_spec import (
    KILL_TRIALS,
    LAP_SECONDS,
    TIMING_SECONDS,
    WAIT_TIMEOUT_S,
    RawRing,
    lap_payload,
    new_ring,
    open_raw,
    paced_payload,
    parse_slot_header,
    raw_head,
    ring,
    synthetic_payload,
    write_kwargs,
)


def _start(spawn, procs, target, *args):
    process = spawn.Process(target=target, args=args, daemon=True)
    procs.append(process)
    process.start()
    return process


def _wait(event, what):
    assert event.wait(WAIT_TIMEOUT_S), f"timed out: {what}"


def _wait_for_head(shm, minimum):
    deadline = time.monotonic() + WAIT_TIMEOUT_S
    while raw_head(shm) < minimum:
        assert time.monotonic() < deadline, f"head did not reach {minimum}"
        time.sleep(0.001)


@pytest.mark.ring_portable
@pytest.mark.ring_slow
@pytest.mark.parametrize("slot_count", [2, 8, 60])
def test_t_ring_08_adversarial_lap(cleanup, spawn, procs, slot_count):
    """T-RING-08, sections 6.2, 6.4 and 10: an unthrottled writer process; slot counts 2, 8 and
    60; readers at the oldest frame, the newest frame and by number. Pass: zero wrong bytes
    accepted AND at least one torn copy detected (`failed_checks`, a failed R5/R10/R12 check).

    The default run is LAP_SECONDS (2 s) per slot count. SKELLYCAM_RING_FULL=1 gives the 60 s of
    the spec. The short run checks the same rule on fewer laps.
    """
    fr = ring()
    base_size = 100_000
    creator = cleanup.own(fr.FrameRingCreator.create(
        camera_id="lap", camera_index=0, pixel_format=fr.PixelFormat.JPEG, width=640,
        height=480, fps_num=slot_count, fps_den=1, history_s=1.0))
    stop, results = spawn.Event(), spawn.Queue()
    ready = [spawn.Event() for _ in range(4)]
    _start(spawn, procs, ring_children.lap_writer, creator.name, base_size, stop, ready[0])
    for mode, event in zip(("oldest", "newest", "number"), ready[1:]):
        _start(spawn, procs, ring_children.lap_reader, creator.name, mode, base_size, stop, event, results)
    for event in ready:
        _wait(event, "child ready")
    time.sleep(LAP_SECONDS)
    stop.set()
    reports = [results.get(timeout=WAIT_TIMEOUT_S) for _ in range(3)]
    for process in procs:
        process.join(timeout=WAIT_TIMEOUT_S)
        assert process.exitcode == 0
    wrong = {report["mode"]: report["wrong"][:10] for report in reports if report["wrong"]}
    assert not wrong, f"wrong bytes accepted: {wrong}"
    assert sum(report["failed_checks"] for report in reports) >= 1, (
        f"no torn copy detected, the race did not run: {reports}")
    assert all(report["counts"].get("OK", 0) > 0 for report in reports), reports


def _accepts_wrong_bytes(fr, read, expected):
    return read.result == fr.ReadResult.OK and read.payload != expected.get(read.frame_number)


@pytest.mark.ring_portable
def test_t_ring_09_reordering_injection_deterministic(cleanup):
    """T-RING-09, sections 5.4, 6.2 and 10: a test writer (from the spec tables, not the
    implementation) publishes the header and `head` before the payload, and writes the payload
    in halves. A read after each step never returns `OK` with wrong bytes."""
    fr = ring()
    raw = cleanup.own(RawRing(slot_count=4, slot_capacity=311_296))
    reader = cleanup.handle(fr.FrameRingReader.attach(raw.name))
    size = 50_000
    expected = {k: synthetic_payload(k, size) for k in range(12)}

    def check_all():
        for k in range(0, 13):
            read = reader.read(k)
            assert not _accepts_wrong_bytes(fr, read, expected), (k, read.result)
        read = reader.read_newest()
        assert not _accepts_wrong_bytes(fr, read, expected)

    for k in range(4):
        raw.commit(k, expected[k])
    check_all()
    for k in range(4, 8):  # header and head first, payload after, no W2
        raw.write_header(k, raw.header_for(k, expected[k]))
        check_all()
        raw.set_head(k)
        check_all()
        raw.write_payload(k, expected[k], 0, size // 2)
        check_all()
        raw.write_payload(k, expected[k], size // 2)
        check_all()
        assert reader.read(k).payload == expected[k]
    for k in range(8, 12):  # payload in halves over a valid older header, no W2
        raw.write_payload(k, expected[k], 0, size // 2)
        check_all()
        raw.write_payload(k, expected[k], size // 2)
        check_all()
        raw.write_header(k, raw.header_for(k, expected[k]))
        raw.set_head(k)
        check_all()


@pytest.mark.ring_portable
def test_t_ring_09_reordering_injection_threaded(cleanup):
    """T-RING-09, sections 5.4 and 6.2: the same misbehaving writer in a thread, with a sleep
    between the payload halves, while a reader thread reads each frame. No `OK` with wrong
    bytes."""
    fr = ring()
    raw = cleanup.own(RawRing(slot_count=4, slot_capacity=311_296))
    reader = cleanup.handle(fr.FrameRingReader.attach(raw.name))
    size = 200_000
    frames = 200
    expected = {k: synthetic_payload(k, size) for k in range(frames)}
    stop = threading.Event()
    bad = []

    def hammer():
        while not stop.is_set():
            head = raw_head(raw.shm)
            for k in range(max(0, head - 4), head + 2):
                read = reader.read(k)
                if _accepts_wrong_bytes(fr, read, expected):
                    bad.append(k)

    thread = threading.Thread(target=hammer, daemon=True)
    thread.start()
    try:
        for k in range(frames):
            if k % 2:
                raw.write_header(k, raw.header_for(k, expected[k]))
                raw.set_head(k)
            raw.write_payload(k, expected[k], 0, size // 2)
            time.sleep(0.001)
            raw.write_payload(k, expected[k], size // 2)
            if not k % 2:
                raw.write_header(k, raw.header_for(k, expected[k]))
                raw.set_head(k)
    finally:
        stop.set()
        thread.join(timeout=WAIT_TIMEOUT_S)
    assert not thread.is_alive()
    assert not bad, f"OK with wrong bytes for frames {bad[:10]}"


@pytest.mark.ring_portable
@pytest.mark.ring_slow
def test_t_ring_11_writer_killed(cleanup, spawn, procs):
    """T-RING-11, sections 5.4, 6.2 and 10: kill the writer process in the middle of a payload
    copy. That frame never reads `OK`; the earlier frames still read `OK`; no reader hangs.

    The kill time is random. A trial hit the copy when the next slot has `frame_number = -1`
    (after W2, before W5). The test repeats up to KILL_TRIALS (100) trials, checks each one, and
    needs one hit. A hit is rare (about 1 trial in 10 on one Windows test machine), so 20 trials
    often gave no hit.
    """
    fr = ring()
    size = 8_000_000  # 3840x2160 slot: the copy is a large part of each write
    hits = 0
    for trial in range(KILL_TRIALS):
        creator = cleanup.own(fr.FrameRingCreator.create(
            camera_id="kill", camera_index=trial, pixel_format=fr.PixelFormat.JPEG, width=3840,
            height=2160, fps_num=4, fps_den=1, history_s=1.0))
        reader = cleanup.handle(fr.FrameRingReader.attach(creator.name))
        shm = cleanup.handle(open_raw(creator.name))
        ready = spawn.Event()
        writer = _start(spawn, procs, ring_children.kill_target_writer, creator.name, size, ready)
        _wait(ready, "writer ready")
        _wait_for_head(shm, 6)
        time.sleep(random.uniform(0, 0.02))
        writer.kill()
        writer.join(timeout=WAIT_TIMEOUT_S)
        assert not writer.is_alive()
        head = raw_head(shm)
        hits += parse_slot_header(shm.buf, (head + 1) % 4)["frame_number"] == -1
        outcome = {}

        def read_all():
            outcome["next"] = reader.read(head + 1)
            outcome["oldest"] = reader.read(head - 3)
            outcome["earlier"] = [reader.read(k) for k in range(head - 2, head + 1)]

        thread = threading.Thread(target=read_all, daemon=True)
        thread.start()
        thread.join(timeout=WAIT_TIMEOUT_S)
        assert not thread.is_alive(), "a reader hangs after the writer was killed"
        assert outcome["next"].result != fr.ReadResult.OK
        oldest = outcome["oldest"]
        assert oldest.result != fr.ReadResult.OK or oldest.payload == lap_payload(head - 3, size)
        for k, read in zip(range(head - 2, head + 1), outcome["earlier"]):
            assert read.result == fr.ReadResult.OK, (trial, k, read.result)
            assert read.payload == lap_payload(k, size)
        outcome.clear()
        reader.close()
        shm.close()
        creator.close_and_unlink()  # the cleanup fixture calls these again and ignores errors
        if hits and trial >= 2:
            break
    assert hits >= 1, f"no kill hit the payload copy in {trial + 1} trials"


def _reader_killed_run(cleanup, spawn, procs):
    """The run of T-RING-12: kill a reader in the middle of a copy. Gives the writer p99 before and after the kill
    and the results of the other reader.

    The writer writes about 500 frames/s of 600 kB (1920x1080 slot). Each phase lasts
    TIMING_SECONDS (2 s; 10 s with SKELLYCAM_RING_FULL=1). The kill time is random; the victim
    spends most of its time in copies of 600 kB.
    """
    fr = ring()
    size = 600_000
    creator = cleanup.own(fr.FrameRingCreator.create(
        camera_id="timing", camera_index=0, pixel_format=fr.PixelFormat.JPEG, width=1920,
        height=1080, fps_num=60, fps_den=1, history_s=1.0))
    # No lock: the victim can die inside a read of `phase`, and a lock that it held stays taken (see the test below)
    phase, stop, ready = spawn.Value("i", 0, lock=False), spawn.Event(), spawn.Event()
    timings, survivor_results, victim_results = spawn.Queue(), spawn.Queue(), spawn.Queue()
    _start(spawn, procs, ring_children.timed_writer, creator.name, size, phase, stop, ready, timings)
    _start(spawn, procs, ring_children.busy_reader, creator.name, size, phase, stop, survivor_results)
    victim_stop = spawn.Event()  # its own Event: a victim killed inside `is_set` keeps the lock of the Event
    victim = _start(spawn, procs, ring_children.busy_reader, creator.name, size, phase, victim_stop, victim_results)
    _wait(ready, "writer ready")
    time.sleep(TIMING_SECONDS)
    victim.kill()
    victim.join(timeout=WAIT_TIMEOUT_S)
    phase.value = 1
    time.sleep(TIMING_SECONDS)
    stop.set()
    durations = timings.get(timeout=WAIT_TIMEOUT_S)
    survivor = survivor_results.get(timeout=WAIT_TIMEOUT_S)
    return np.percentile(durations[0], 99), np.percentile(durations[1], 99), survivor


@pytest.mark.ring_portable
@pytest.mark.ring_slow
def test_t_ring_12_reader_killed(cleanup, spawn, procs):
    """T-RING-12, sections 6.1 and 10: kill a reader in the middle of a copy. The other readers are unaffected: no
    wrong frame, no error, frames after the kill. The writer p99 is in
    `test_t_ring_12_the_writer_timing_is_unchanged_after_a_reader_kill` (16.1)."""
    _, _, survivor = _reader_killed_run(cleanup, spawn, procs)
    assert survivor["wrong"] == 0
    assert not survivor["errors"], survivor["errors"][:3]
    assert survivor["ok_after_kill"] > 0


@pytest.mark.pace  # Q619: two p99 values of real time; the tolerance of 10 % grows by the margin
@pytest.mark.ring_portable
@pytest.mark.ring_slow
def test_t_ring_12_the_writer_timing_is_unchanged_after_a_reader_kill(cleanup, spawn, procs):
    """T-RING-12, the bound of time: the writer p99 after the kill is within 10 % (times the margin) of before."""
    before, after, _ = _reader_killed_run(cleanup, spawn, procs)
    assert after <= (1.0 + 0.10 * margin()) * before, f"writer p99 {before / 1e3:.1f} us before, {after / 1e3:.1f} us after"


@pytest.mark.ring_portable
@pytest.mark.parametrize(("fps", "period"), [(30, 33_333_334), (60, 16_666_666)])
def test_t_ring_13_nearest_to_t(cleanup, fps, period):
    """T-RING-13, section 6.5 [A28]: rings at 30 and 60 frames/s with known arrival times;
    1,000 random t. The expected frame every time; a tie goes to the lower frame number.

    The frame rate is in the arrival times; the frames are written first, then read. Both
    periods are even, so `arrival + period / 2` is an exact tie.
    """
    fr, _, writer, reader = new_ring(cleanup, fps_num=fps)  # N = fps
    t0 = 5_000_000_000
    head = 2 * fps + 4
    arrival = {k: t0 + k * period for k in range(head + 1)}
    for k in range(head + 1):
        kwargs = write_kwargs(k)
        kwargs["arrival_ns"] = arrival[k]
        writer.write(synthetic_payload(k, 2000), **kwargs)
    window = range(head - fps + 1, head + 1)
    rng = np.random.default_rng(13)
    times = [int(t) for t in rng.integers(arrival[window[0]] - 2 * period, arrival[head] + 2 * period, 950)]
    times += [arrival[k] + period // 2 for k in rng.choice(list(window[:-1]), 50)]  # exact ties
    for t in times:
        expected = min(window, key=lambda k: (abs(arrival[k] - t), k))
        read = reader.read_nearest(t)
        assert read.result == fr.ReadResult.OK, t
        assert read.frame_number == expected, (t, read.frame_number, expected)
        assert read.arrival_ns == arrival[expected]


@pytest.mark.ring_portable
def test_t_ring_14_newest_under_load(cleanup, spawn, procs):
    """T-RING-14, section 6.5: a writer at 60 frames/s; the reader asks for the newest frame
    10,000 times. Always `OK` (the lookup's own one retry included); the frame number never goes
    back."""
    fr = ring()
    size = 100_000
    creator = cleanup.own(fr.FrameRingCreator.create(
        camera_id="newest", camera_index=0, pixel_format=fr.PixelFormat.JPEG, width=640,
        height=480, fps_num=60, fps_den=1, history_s=1.0))
    reader = cleanup.handle(fr.FrameRingReader.attach(creator.name))
    shm = cleanup.handle(open_raw(creator.name))
    stop, ready = spawn.Event(), spawn.Event()
    _start(spawn, procs, ring_children.paced_writer, creator.name, size, 60, stop, ready)
    _wait(ready, "writer ready")
    _wait_for_head(shm, 0)
    expected = {}
    last = -1
    try:
        for _ in range(10_000):
            read = reader.read_newest()
            assert read.result == fr.ReadResult.OK, read.result
            assert read.frame_number >= last
            last = read.frame_number
            if last not in expected:
                expected[last] = paced_payload(last, size)
            assert read.payload == expected[last]
    finally:
        stop.set()
    assert last > 0


def test_a_killed_process_keeps_the_lock_of_a_shared_value(spawn, procs):
    """The hang of the suite run of 2026-11-21 (T-RING-12 waited for ever at `phase.value = 1`): a process that is
    killed while it holds the lock of a `multiprocessing.Value` leaves the lock taken, so each later locked access
    waits for ever. The waits here are bounded. T-RING-12 and T-RING-36 therefore share `phase` with no lock."""
    import inspect

    from skellycam.tests.frame_ring import test_bgr_ring

    value, held = spawn.Value("i", 0), spawn.Event()
    holder = _start(spawn, procs, ring_children.hold_lock_forever, value, held)
    _wait(held, "the child holds the lock")
    holder.kill()
    holder.join(timeout=WAIT_TIMEOUT_S)
    lock = value.get_lock()
    assert not lock.acquire(timeout=1.0), "the lock of the killed process was released"
    event, held = spawn.Event(), spawn.Event()
    holder = _start(spawn, procs, ring_children.hold_event_lock_forever, event, held)
    _wait(held, "the child holds the lock of the Event")
    holder.kill()
    holder.join(timeout=WAIT_TIMEOUT_S)
    import threading

    blocked = threading.Thread(target=event.is_set, daemon=True)  # stays blocked: a daemon thread, no hang of the run
    blocked.start()
    blocked.join(1.0)
    assert blocked.is_alive(), "is_set returned after the holder of the lock was killed"
    for test in (_reader_killed_run, test_bgr_ring.test_t_ring_36_reader_killed):  # the run of T-RING-12 (16.1)
        source = inspect.getsource(test)
        assert 'spawn.Value("i", 0, lock=False)' in source, test.__name__
        assert "phase, victim_stop, victim_results" in source, f"{test.__name__}: the victim shares `stop`"
