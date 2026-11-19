"""BGR ring writer and reader: T-RING-36, 42 and 43 (specs/frame-ring.md, sections 3.5, 3.6,
5.1, 5.5, 5.7, 6.6, 8 and 12).

T-RING-36 runs the cases of T-RING-05 and T-RING-07 to T-RING-14 again with BGR payloads on a BGR
ring (`pixel_format = 2`), at 640x480, with one 1920x1080 case. T-RING-06 does not apply: a BGR
ring has no oversize guard. T-RING-48 runs T-RING-36 again on ARM, so these tests have the
`ring_portable` marker.

The bodies follow the JPEG tests of test_write_read.py and test_concurrency.py. They are not the
same functions: a BGR payload is an array of one fixed size, and a BGR read gives an array. The
child processes (ring_children.py) and the raw ring (ring_spec.RawRing) are shared.
"""

import random
import threading
import time
import tracemalloc

import numpy as np
import pytest

from skellycam.tests.frame_ring import ring_children
from skellycam.tests.frame_ring.ring_spec import (
    KILL_TRIALS,
    LAP_SECONDS,
    PIXEL_FORMAT_BGR24,
    TIMING_SECONDS,
    WAIT_TIMEOUT_S,
    RawRing,
    arrival_for,
    as_bgr,
    as_bytes,
    bgr_payload,
    bgr_size,
    lap_payload,
    new_ring,
    open_raw,
    paced_payload,
    parse_ring_header,
    parse_slot_header,
    raw_head,
    ring,
    slot_payload_offset,
    synthetic_payload,
    write_kwargs,
)
from skellycam.tests.frame_ring.test_concurrency import _start, _wait, _wait_for_head

SHAPE = (480, 640, 3)
SIZE = bgr_size()  # 921,600 (table 3.6)


def _assert_bgr_ok(fr, read, expected):
    """A BGR read is `OK` and gives the frame as a writable array (6.6)."""
    assert read.result == fr.ReadResult.OK, read.result
    assert type(read.payload) is np.ndarray, type(read.payload)
    assert read.payload.shape == expected.shape and read.payload.dtype == np.uint8
    assert np.array_equal(read.payload, expected)
    assert read.payload_len == expected.size  # 5.5: always width x height x 3


def _bgr_ring(cleanup, **kwargs):
    return new_ring(cleanup, bgr=True, **kwargs)


@pytest.mark.ring_portable
@pytest.mark.parametrize(("width", "height"), [(640, 480), (1920, 1080)], ids=["640x480", "1920x1080"])
def test_t_ring_36_round_trip(cleanup, width, height):
    """T-RING-36 (T-RING-05 with BGR payloads), sections 3.5, 3.6, 5.5 and 6.6: synthetic BGR
    frames. Each read is `OK` with identical pixels and `payload_len = width x height x 3`.

    A BGR payload has one size (table 3.6), so the sizes 0, 1 and random of T-RING-05 do not
    apply. The 1920x1080 case is the one 1080p case of T-RING-36.
    """
    fr, creator, writer, reader = _bgr_ring(cleanup, fps_num=4, width=width, height=height)
    header = parse_ring_header(cleanup.handle(open_raw(creator.name)).buf)
    assert header["pixel_format"] == PIXEL_FORMAT_BGR24
    assert header["slot_capacity"] == bgr_size(width, height)
    for k in range(6):  # more frames than slots: the ring wraps
        frame = bgr_payload(k, width, height)
        writer.write(frame, **write_kwargs(k, rotation=180))
        read = reader.read(k)
        _assert_bgr_ok(fr, read, frame)
        assert read.frame_number == k
        assert read.arrival_ns == arrival_for(k)
        assert read.sample_ns == arrival_for(k) - 1000
        assert read.source_frame_number == k
        assert read.flags == 0
        assert read.rotation_cw_deg == 180


@pytest.mark.ring_portable
def test_t_ring_36_read_results(cleanup):
    """T-RING-36 (T-RING-07 with BGR payloads), sections 6.2 and 6.3: empty ring, `k > head`,
    `head - k >= N`, a skipped number and a closed ring give `NOT_YET_WRITTEN`, `NOT_YET_WRITTEN`,
    `LAPPED`, `MISSING` and `CLOSED`."""
    fr, creator, writer, reader = _bgr_ring(cleanup, fps_num=4)  # N = 4
    assert reader.read(0).result == fr.ReadResult.NOT_YET_WRITTEN
    for k in range(6):
        writer.write(bgr_payload(k), **write_kwargs(k))
    assert reader.read(6).result == fr.ReadResult.NOT_YET_WRITTEN
    assert reader.read(1).result == fr.ReadResult.LAPPED
    writer.write(bgr_payload(6), newer_frame_waiting=True, **write_kwargs(6))
    writer.write(bgr_payload(7), **write_kwargs(7))
    read = reader.read(6)  # slot 2 still holds frame 2
    assert read.result == fr.ReadResult.MISSING
    assert read.payload is None
    _assert_bgr_ok(fr, reader.read(7), bgr_payload(7))
    creator.set_closed()
    read = reader.read(7)
    assert read.result == fr.ReadResult.CLOSED
    assert read.payload is None


@pytest.mark.ring_portable
def test_t_ring_36_slot_being_written_is_lapped(cleanup):
    """T-RING-36 (T-RING-07 with BGR payloads), sections 6.2 and 6.4 [A58]: a committed frame
    whose slot header then holds `frame_number = -1` reads as `LAPPED`, not `CORRUPT`."""
    fr, creator, writer, reader = _bgr_ring(cleanup, fps_num=8)
    writer.write(bgr_payload(0), **write_kwargs(0))
    _assert_bgr_ok(fr, reader.read(0), bgr_payload(0))
    shm = cleanup.handle(open_raw(creator.name))
    shm.buf[4096:4104] = (-1).to_bytes(8, "little", signed=True)  # slot 0, frame_number
    read = reader.read(0)
    assert read.result == fr.ReadResult.LAPPED
    assert read.payload is None


@pytest.mark.ring_portable
def test_t_ring_36_closed_ring_stops_the_writer(cleanup):
    """T-RING-36 (T-RING-07 group with BGR payloads), section 7.4 [A35]: after `closed = 1`, the
    BGR writer stops writing."""
    fr, creator, writer, reader = _bgr_ring(cleanup, fps_num=4)
    writer.write(bgr_payload(0), **write_kwargs(0))
    _assert_bgr_ok(fr, reader.read(0), bgr_payload(0))
    creator.set_closed()
    writer.write(bgr_payload(1), **write_kwargs(1))
    header = parse_ring_header(cleanup.handle(open_raw(creator.name)).buf)
    assert header["closed"] == 1
    assert header["head"] == 0
    assert header["frames_committed"] == 1


@pytest.mark.ring_portable
@pytest.mark.parametrize("where", ["payload", "header"])
def test_t_ring_36_bit_flip_after_commit_is_corrupt(cleanup, where):
    """T-RING-36 (T-RING-10 with BGR payloads), sections 6.2 and 6.4: one payload bit flipped
    after the commit, and separately one header bit. Both give `CORRUPT`."""
    fr, creator, writer, reader = _bgr_ring(cleanup, fps_num=8)
    writer.write(bgr_payload(0), **write_kwargs(0))
    _assert_bgr_ok(fr, reader.read(0), bgr_payload(0))
    shm = cleanup.handle(open_raw(creator.name))
    header = parse_ring_header(shm.buf)
    offset = slot_payload_offset(header, 0) + 12_345 if where == "payload" else 4096 + 9
    shm.buf[offset] ^= 0x10
    read = reader.read(0)
    assert read.result == fr.ReadResult.CORRUPT
    assert read.payload is None


@pytest.mark.ring_portable
@pytest.mark.ring_slow
@pytest.mark.parametrize("slot_count", [2, 8, 60])
def test_t_ring_36_adversarial_lap(cleanup, spawn, procs, slot_count):
    """T-RING-36 (T-RING-08 with BGR payloads), sections 6.2, 6.4 and 10: an unthrottled BGR
    writer process; slot counts 2, 8 and 60; readers at the oldest frame, the newest frame and by
    number. Zero wrong bytes accepted, and at least one torn copy detected.

    The default run is LAP_SECONDS (2 s) per slot count; SKELLYCAM_RING_FULL=1 gives the 60 s of
    the spec. Frames k and k + N have different bodies (ring_spec.lap_payload).
    """
    fr = ring()
    creator = cleanup.own(fr.FrameRingCreator.create(
        camera_id="lap", camera_index=0, pixel_format=fr.PixelFormat.BGR24, width=640,
        height=480, fps_num=slot_count, fps_den=1, history_s=1.0))
    stop, results = spawn.Event(), spawn.Queue()
    ready = [spawn.Event() for _ in range(4)]
    _start(spawn, procs, ring_children.lap_writer, creator.name, SIZE, stop, ready[0], SHAPE)
    for mode, event in zip(("oldest", "newest", "number"), ready[1:]):
        _start(spawn, procs, ring_children.lap_reader, creator.name, mode, SIZE, stop, event, results, SHAPE)
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
    return read.result == fr.ReadResult.OK and as_bytes(read.payload) != expected(read.frame_number)


@pytest.mark.ring_portable
def test_t_ring_36_reordering_injection_deterministic(cleanup):
    """T-RING-36 (T-RING-09 with BGR payloads), sections 5.4, 6.2 and 10: a test writer (from
    the spec tables) on a BGR block publishes the header and `head` before the payload, and
    writes the payload in halves. No read returns `OK` with wrong bytes."""
    fr = ring()
    raw = cleanup.own(RawRing(slot_count=4, slot_capacity=SIZE, pixel_format=PIXEL_FORMAT_BGR24))
    reader = cleanup.handle(fr.FrameRingReader.attach(raw.name))
    payloads = {k: synthetic_payload(k, SIZE) for k in range(12)}

    def check_all():
        for k in range(0, 13):
            assert not _accepts_wrong_bytes(fr, reader.read(k), payloads.get), k
        assert not _accepts_wrong_bytes(fr, reader.read_newest(), payloads.get)

    for k in range(4):
        raw.commit(k, payloads[k])
    check_all()
    for k in range(4, 8):  # header and head first, payload after, no W2
        raw.write_header(k, raw.header_for(k, payloads[k]))
        check_all()
        raw.set_head(k)
        check_all()
        raw.write_payload(k, payloads[k], 0, SIZE // 2)
        check_all()
        raw.write_payload(k, payloads[k], SIZE // 2)
        check_all()
        _assert_bgr_ok(fr, reader.read(k), as_bgr(payloads[k], SHAPE))
    for k in range(8, 12):  # payload in halves over a valid older header, no W2
        raw.write_payload(k, payloads[k], 0, SIZE // 2)
        check_all()
        raw.write_payload(k, payloads[k], SIZE // 2)
        check_all()
        raw.write_header(k, raw.header_for(k, payloads[k]))
        raw.set_head(k)
        check_all()
        _assert_bgr_ok(fr, reader.read(k), as_bgr(payloads[k], SHAPE))


@pytest.mark.ring_portable
def test_t_ring_36_reordering_injection_threaded(cleanup):
    """T-RING-36 (T-RING-09 with BGR payloads), sections 5.4 and 6.2: the same misbehaving
    writer in a thread, with a sleep between the payload halves, while a reader thread reads each
    frame. No `OK` with wrong bytes."""
    fr = ring()
    raw = cleanup.own(RawRing(slot_count=4, slot_capacity=SIZE, pixel_format=PIXEL_FORMAT_BGR24))
    reader = cleanup.handle(fr.FrameRingReader.attach(raw.name))
    frames = 200

    def expected(k):
        return paced_payload(k, SIZE) if 0 <= k < frames else None

    stop = threading.Event()
    bad = []

    def hammer():
        while not stop.is_set():
            head = raw_head(raw.shm)
            for k in range(max(0, head - 4), head + 2):
                if _accepts_wrong_bytes(fr, reader.read(k), expected):
                    bad.append(k)

    thread = threading.Thread(target=hammer, daemon=True)
    thread.start()
    try:
        for k in range(frames):
            payload = expected(k)
            if k % 2:
                raw.write_header(k, raw.header_for(k, payload))
                raw.set_head(k)
            raw.write_payload(k, payload, 0, SIZE // 2)
            time.sleep(0.001)
            raw.write_payload(k, payload, SIZE // 2)
            if not k % 2:
                raw.write_header(k, raw.header_for(k, payload))
                raw.set_head(k)
    finally:
        stop.set()
        thread.join(timeout=WAIT_TIMEOUT_S)
    assert not thread.is_alive()
    assert not bad, f"OK with wrong bytes for frames {bad[:10]}"
    _assert_bgr_ok(fr, reader.read(frames - 1), as_bgr(expected(frames - 1), SHAPE))


@pytest.mark.ring_portable
@pytest.mark.ring_slow
def test_t_ring_36_writer_killed(cleanup, spawn, procs):
    """T-RING-36 (T-RING-11 with BGR payloads), sections 5.4, 6.2 and 10: kill the BGR writer
    process in the middle of a payload copy. That frame never reads `OK`; the earlier frames still
    read `OK`; no reader hangs. Up to KILL_TRIALS trials; one hit is necessary (as T-RING-11)."""
    fr = ring()
    hits = 0
    for trial in range(KILL_TRIALS):
        creator = cleanup.own(fr.FrameRingCreator.create(
            camera_id="kill", camera_index=trial, pixel_format=fr.PixelFormat.BGR24, width=640,
            height=480, fps_num=4, fps_den=1, history_s=1.0))
        reader = cleanup.handle(fr.FrameRingReader.attach(creator.name))
        shm = cleanup.handle(open_raw(creator.name))
        ready = spawn.Event()
        writer = _start(spawn, procs, ring_children.kill_target_writer, creator.name, SIZE, ready, SHAPE)
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
        assert oldest.result != fr.ReadResult.OK or as_bytes(oldest.payload) == lap_payload(head - 3, SIZE)[:SIZE]
        for k, read in zip(range(head - 2, head + 1), outcome["earlier"]):
            _assert_bgr_ok(fr, read, as_bgr(lap_payload(k, SIZE), SHAPE))
        outcome.clear()
        reader.close()
        shm.close()
        creator.close_and_unlink()
        if hits and trial >= 2:
            break
    assert hits >= 1, f"no kill hit the payload copy in {trial + 1} trials"


@pytest.mark.ring_portable
@pytest.mark.ring_slow
def test_t_ring_36_reader_killed(cleanup, spawn, procs):
    """T-RING-36 (T-RING-12 with BGR payloads), sections 6.1 and 10: kill a BGR reader in the
    middle of a copy. Writer timing is unchanged (p99 within 10 %); the other readers are
    unaffected. Each phase lasts TIMING_SECONDS (2 s; 10 s with SKELLYCAM_RING_FULL=1)."""
    fr = ring()
    creator = cleanup.own(fr.FrameRingCreator.create(
        camera_id="timing", camera_index=0, pixel_format=fr.PixelFormat.BGR24, width=640,
        height=480, fps_num=60, fps_den=1, history_s=1.0))
    phase, stop, ready = spawn.Value("i", 0), spawn.Event(), spawn.Event()
    timings, survivor_results, victim_results = spawn.Queue(), spawn.Queue(), spawn.Queue()
    _start(spawn, procs, ring_children.timed_writer, creator.name, SIZE, phase, stop, ready, timings, SHAPE)
    _start(spawn, procs, ring_children.busy_reader, creator.name, SIZE, phase, stop, survivor_results, SHAPE)
    victim = _start(spawn, procs, ring_children.busy_reader, creator.name, SIZE, phase, stop,
                    victim_results, SHAPE)
    _wait(ready, "writer ready")
    time.sleep(TIMING_SECONDS)
    victim.kill()
    victim.join(timeout=WAIT_TIMEOUT_S)
    phase.value = 1
    time.sleep(TIMING_SECONDS)
    stop.set()
    durations = timings.get(timeout=WAIT_TIMEOUT_S)
    survivor = survivor_results.get(timeout=WAIT_TIMEOUT_S)
    before = np.percentile(durations[0], 99)
    after = np.percentile(durations[1], 99)
    assert after <= 1.10 * before, f"writer p99 {before / 1e3:.1f} us before, {after / 1e3:.1f} us after"
    assert survivor["wrong"] == 0
    assert not survivor["errors"], survivor["errors"][:3]
    assert survivor["ok_after_kill"] > 0


@pytest.mark.ring_portable
@pytest.mark.parametrize(("fps", "period"), [(30, 33_333_334), (60, 16_666_666)])
def test_t_ring_36_nearest_to_t(cleanup, fps, period):
    """T-RING-36 (T-RING-13 with BGR payloads), section 6.5 [A28]: rings at 30 and 60 frames/s
    with known arrival times; 1,000 random t. The expected frame every time; a tie goes to the
    lower frame number."""
    fr, _, writer, reader = _bgr_ring(cleanup, fps_num=fps)  # N = fps
    t0 = 5_000_000_000
    head = 2 * fps + 4
    arrival = {k: t0 + k * period for k in range(head + 1)}
    frames = [bgr_payload(k % 8) for k in range(8)]
    for k in range(head + 1):
        kwargs = write_kwargs(k)
        kwargs["arrival_ns"] = arrival[k]
        writer.write(frames[k % 8], **kwargs)
    window = range(head - fps + 1, head + 1)
    rng = np.random.default_rng(13)
    times = [int(t) for t in rng.integers(arrival[window[0]] - 2 * period, arrival[head] + 2 * period, 950)]
    times += [arrival[k] + period // 2 for k in rng.choice(list(window[:-1]), 50)]  # exact ties
    for t in times:
        expected = min(window, key=lambda k: (abs(arrival[k] - t), k))
        read = reader.read_nearest(t)
        assert read.frame_number == expected, (t, read.frame_number, expected)
        assert read.arrival_ns == arrival[expected]
        _assert_bgr_ok(fr, read, frames[expected % 8])


@pytest.mark.ring_portable
def test_t_ring_36_newest_under_load(cleanup, spawn, procs):
    """T-RING-36 (T-RING-14 with BGR payloads), section 6.5: a BGR writer at 60 frames/s; the
    reader asks for the newest frame 10,000 times. Always `OK`; the frame number never goes
    back."""
    fr = ring()
    creator = cleanup.own(fr.FrameRingCreator.create(
        camera_id="newest", camera_index=0, pixel_format=fr.PixelFormat.BGR24, width=640,
        height=480, fps_num=60, fps_den=1, history_s=1.0))
    reader = cleanup.handle(fr.FrameRingReader.attach(creator.name))
    shm = cleanup.handle(open_raw(creator.name))
    stop, ready = spawn.Event(), spawn.Event()
    _start(spawn, procs, ring_children.paced_writer, creator.name, SIZE, 60, stop, ready, SHAPE)
    _wait(ready, "writer ready")
    _wait_for_head(shm, 0)
    expected = {}
    last = -1
    try:
        for _ in range(10_000):
            read = reader.read_newest()
            assert read.frame_number >= last
            last = read.frame_number
            if last not in expected:
                expected[last] = as_bgr(paced_payload(last, SIZE), SHAPE)
            _assert_bgr_ok(fr, read, expected[last])
    finally:
        stop.set()
    assert last > 0


def test_t_ring_42_bgr_writer_one_copy(cleanup):
    """T-RING-42, sections 5.5 and 5.7: `tracemalloc` over the BGR write step (the decode is not
    in it): 1,000 writes of preallocated arrays. No allocation of 1 KiB or more.

    As T-RING-15: the peak above the start of each write catches each block of 1 KiB or more,
    and the memory that stays after 1,000 writes catches small blocks that stay.
    """
    fr, _, writer, reader = _bgr_ring(cleanup, fps_num=60)
    frames = [bgr_payload(k) for k in range(8)]
    arguments = [write_kwargs(k) for k in range(1010)]
    for k in range(10):  # warm-up: first-touch pages, caches
        writer.write(frames[k % 8], **arguments[k])
    _assert_bgr_ok(fr, reader.read(9), frames[1])
    worst = 0
    tracemalloc.start()
    try:
        start = tracemalloc.get_traced_memory()[0]
        for k in range(10, 1010):
            frame = frames[k % 8]
            kwargs = arguments[k]
            tracemalloc.reset_peak()
            before = tracemalloc.get_traced_memory()[0]
            writer.write(frame, **kwargs)
            worst = max(worst, tracemalloc.get_traced_memory()[1] - before)
        kept = tracemalloc.get_traced_memory()[0] - start
    finally:
        tracemalloc.stop()
    assert worst < 1024, f"one BGR write allocated {worst} bytes at its peak"
    assert kept < 1000 * 1024, f"{kept} bytes stay after 1,000 BGR writes"


def test_t_ring_43_bgr_read_type(cleanup):
    """T-RING-43, section 6.6 [A29]: a BGR read gives a writable `numpy.ndarray` of shape
    `(h, w, 3)`, uint8, that does not share memory with the block. Each lookup (by number,
    newest, nearest) gives the same type. A change to the array does not change the ring."""
    fr, creator, writer, reader = _bgr_ring(cleanup, fps_num=8)
    frame = bgr_payload(3)
    writer.write(frame, **write_kwargs(0))
    shm = cleanup.handle(open_raw(creator.name))
    block = np.frombuffer(shm.buf, np.uint8)
    try:
        reads = [reader.read(0), reader.read_newest(), reader.read_nearest(arrival_for(0))]
        for read in reads:
            _assert_bgr_ok(fr, read, frame)
            assert read.payload.flags.writeable
            assert read.payload.flags.c_contiguous
            assert not np.shares_memory(read.payload, block)
        reads[0].payload[...] = 0
        _assert_bgr_ok(fr, reader.read(0), frame)
    finally:
        del block  # an open export of `shm.buf` makes `close()` raise BufferError
