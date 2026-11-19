"""The decode stage and its waiting place: T-RING-38, 39, 41, 44, 46 and 47
(specs/frame-ring.md, sections 4, 5.5, 5.6, 8.2 to 8.10 and 12).

These tests use the decode stage of ADR-5MYA directly on a BGR ring, with synthetic JPEGs made
by `cv2.imencode` (4:2:0 and 4:2:2) and synthetic YUY2 and NV12 buffers made with numpy. No
camera and no camera frame is used. The tests with the OpenCV camera loop and a session are in
test_bgr_camera.py.

A test that needs "capture" uses a capture stub: a thread that does, for each frame, the steps of
the camera process in the order of 5.3 (capture check, JPEG ring write, waiting place). It waits
by a sleep (rule of 8.10).
"""

import json
import re
import subprocess
import sys
import threading
import time

import cv2
import numpy as np
import pytest

from skellycam.tests.frame_ring.ring_children import LIBJPEG_EXTRA_BYTES
from skellycam.tests.frame_ring.ring_spec import (
    CAPTURE_ERROR,
    DECODE_ERROR,
    DISCONTINUITY,
    ERROR_MASK,
    NO_SOI_EOI,
    TIMING_SECONDS,
    WAIT_TIMEOUT_S,
    arrival_for,
    attach_slow_writer,
    bgr_size,
    committed_frame_numbers,
    decode_input,
    jpeg_segments,
    junk_before_eoi,
    new_ring,
    open_raw,
    parse_ring_header,
    parse_slot_header,
    ring,
    slot_payload_offset,
    start_stage,
    synthetic_jpeg,
    wait_committed,
    write_kwargs,
)

JPEG_ENCODE_PARAMETERS = [int(cv2.IMWRITE_JPEG_QUALITY), 90]  # the decided setting (2.3) [D N:83]


def _bgr_ring(cleanup, width=640, height=480, fps_num=60, camera_index=0):
    """A BGR ring with a writer, a reader and a raw view of the block."""
    fr, creator, writer, reader = new_ring(cleanup, bgr=True, width=width, height=height, fps_num=fps_num,
                                           camera_index=camera_index)
    return fr, writer, reader, cleanup.handle(open_raw(creator.name))


def _imdecode(jpeg):
    return cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)


def _assert_no_pixels(fr, read, shm, k, width=640, height=480):
    """A flagged BGR slot has no pixels (5.6, 8.5): no payload, `payload_crc32 = 0`, `payload_len`
    stays `w x h x 3`, and the slot bytes are untouched (zero in a new ring)."""
    assert read.result == fr.ReadResult.FLAGGED, read.result
    assert read.payload is None
    slot = parse_slot_header(shm.buf, k % parse_ring_header(shm.buf)["slot_count"])
    assert slot["frame_number"] == k
    assert slot["payload_crc32"] == 0
    assert slot["payload_len"] == bgr_size(width, height)
    start = slot_payload_offset(parse_ring_header(shm.buf), k % parse_ring_header(shm.buf)["slot_count"])
    assert not any(shm.buf[start:start + bgr_size(width, height)]), "a flagged slot got pixels"


class CountingDecoder:
    """A decoder stub (ADR-5MYA: `decode(payload) -> ndarray | None`). It counts its calls and
    their threads. It decodes with `cv2.imdecode`, after an optional sleep."""

    def __init__(self, sleep_s=0.0):
        self.sleep_s = sleep_s
        self.calls = 0
        self.threads = set()

    def __call__(self, payload):
        self.calls += 1
        self.threads.add(threading.get_ident())
        if self.sleep_s:
            time.sleep(self.sleep_s)
        return _imdecode(payload)


# ---------------------------------------------------------------------------
# T-RING-38: the waiting place and a slow decode
# ---------------------------------------------------------------------------

def test_t_ring_38_waiting_place_newest_wins():
    """T-RING-38, section 8.3 [A40]: the waiting place holds one frame. A new frame replaces a
    frame that waits, and the replaced frame counts as skipped. A decode thread that waits wakes
    on a put."""
    fr = ring()
    place = fr.WaitingPlace()
    frames = [decode_input(b"\xff\xd8", "JPEG", k) for k in range(4)]
    assert place.take(0.01) is None
    place.put(frames[0])
    place.put(frames[1])
    assert place.skipped == 1
    assert place.take(0.1) is frames[1]
    assert place.take(0.01) is None
    place.put(frames[2])
    assert place.take(0.1) is frames[2]
    assert place.skipped == 1
    taken = []
    thread = threading.Thread(target=lambda: taken.append(place.take(WAIT_TIMEOUT_S)), daemon=True)
    thread.start()
    time.sleep(0.2)
    t0 = time.monotonic()
    place.put(frames[3])
    thread.join(timeout=WAIT_TIMEOUT_S)
    assert not thread.is_alive()
    assert taken == [frames[3]]
    assert time.monotonic() - t0 < 1.0, "the waiting decode thread did not wake on the put"


def _capture_stub(jpeg_writer, jpeg, frames, period_s, put=None):
    """Synthetic capture at 1 / period_s frames/s: capture check, JPEG ring write, then the
    waiting place (5.3). Return the start time of each frame (ns)."""
    fr = ring()
    starts = []
    start = time.perf_counter()
    for k in range(frames):
        starts.append(time.perf_counter_ns())
        payload, flags = fr.check_jpeg(jpeg, delivered_len=len(jpeg), driver_error=False)
        jpeg_writer.write(payload, **write_kwargs(k, flags))
        if put is not None:
            put(decode_input(payload, "JPEG", k, flags))
        delay = start + (k + 1) * period_s - time.perf_counter()
        if delay > 0:
            time.sleep(delay)
    return starts


@pytest.mark.ring_slow
def test_t_ring_38_slow_decode_skips(cleanup, stages):
    """T-RING-38, sections 5.3, 8.2 and 8.3 [D N:88]: a decoder stub that sleeps 100 ms;
    synthetic capture at 60 frames/s. The JPEG ring gets every frame; the capture interval p99 is
    unchanged within 10 %; the BGR skips are counted; the BGR frames are a subset.

    Phase 1 runs the capture stub with no decode stage, phase 2 with the decode stage. Each phase
    lasts TIMING_SECONDS (2 s; 10 s with SKELLYCAM_RING_FULL=1). The spec gives no duration.
    """
    fr = ring()
    frames = int(60 * TIMING_SECONDS)
    jpeg = synthetic_jpeg()
    intervals = {}
    for index, phase in enumerate(("alone", "with decode stage")):
        _, jpeg_creator, jpeg_writer, jpeg_reader = new_ring(cleanup, fps_num=60, camera_index=index)
        put = None
        if phase != "alone":
            _, bgr_writer, _, bgr_shm = _bgr_ring(cleanup)
            decoder = CountingDecoder(sleep_s=0.1)
            stage = start_stage(stages, bgr_writer, decode=decoder)
            put = stage.waiting_place.put
        starts = _capture_stub(jpeg_writer, jpeg, frames, 1 / 60, put)
        intervals[phase] = np.diff(starts)
        jpeg_header = parse_ring_header(cleanup.handle(open_raw(jpeg_creator.name)).buf)
        assert jpeg_header["frames_committed"] == frames, "the JPEG ring did not get every frame"
        assert jpeg_header["skipped_count"] == 0
        assert jpeg_reader.read(frames - 1).result == fr.ReadResult.OK
    stage.stop()
    p99 = {phase: np.percentile(values, 99) for phase, values in intervals.items()}
    assert p99["with decode stage"] <= 1.10 * p99["alone"], (
        f"capture interval p99 {p99['alone'] / 1e6:.2f} ms alone, "
        f"{p99['with decode stage'] / 1e6:.2f} ms with the slow decode stage")
    header = parse_ring_header(bgr_shm.buf)
    committed, skipped = header["frames_committed"], header["skipped_count"]
    assert skipped >= 1, "no BGR skip counted"
    assert skipped == stage.waiting_place.skipped
    assert committed + skipped in (frames, frames - 1), (committed, skipped, frames)  # one can wait
    assert committed == decoder.calls
    assert set(committed_frame_numbers(bgr_shm)) <= set(range(frames))


# ---------------------------------------------------------------------------
# T-RING-39 and T-RING-41: flagged frames and decode failures
# ---------------------------------------------------------------------------

def test_t_ring_39_flagged_jpeg_frame_is_never_decoded(cleanup, stages):
    """T-RING-39, sections 4, 5.6, 8.4 (step 2), 8.5 and 8.6 [D N:62, A15]: frames with
    `NO_SOI_EOI` and with `CAPTURE_ERROR`. Each BGR slot is flagged with the flags of the JPEG
    frame and has no pixels; the decoder call count is 0. An unflagged frame that follows is
    decoded one time, and a `DISCONTINUITY` flag is copied."""
    fr, writer, reader, shm = _bgr_ring(cleanup)
    decoder = CountingDecoder()
    stage = start_stage(stages, writer, decode=decoder)
    jpeg = synthetic_jpeg()
    cut = jpeg[:len(jpeg) // 2]
    _, cut_flags = fr.check_jpeg(cut, delivered_len=len(cut), driver_error=False)
    _, error_flags = fr.check_jpeg(jpeg, delivered_len=len(jpeg), driver_error=True)
    assert cut_flags & NO_SOI_EOI and error_flags & CAPTURE_ERROR
    for k, (payload, flags) in enumerate([(cut, cut_flags), (jpeg, error_flags)]):
        stage.waiting_place.put(decode_input(payload, "JPEG", k, flags, rotation=90))
        wait_committed(shm, k + 1)
    assert decoder.calls == 0, "the decoder got a flagged frame"
    for k, flags in enumerate([cut_flags, error_flags]):
        read = reader.read(k)
        _assert_no_pixels(fr, read, shm, k)
        assert read.flags & ERROR_MASK == flags & ERROR_MASK
        assert (read.arrival_ns, read.sample_ns, read.source_frame_number) == (
            arrival_for(k), arrival_for(k) - 1000, k)
        assert read.rotation_cw_deg == 90
    header = parse_ring_header(shm.buf)
    assert (header["cut_off_count"], header["capture_error_count"], header["decode_error_count"]) == (1, 1, 0)
    stage.waiting_place.put(decode_input(jpeg, "JPEG", 2, DISCONTINUITY, rotation=90))
    wait_committed(shm, 3)
    assert decoder.calls == 1
    read = reader.read(2)
    assert read.result == fr.ReadResult.OK
    assert read.flags & DISCONTINUITY
    assert np.array_equal(read.payload, _imdecode(jpeg))


def _jpeg_that_imdecode_rejects():
    """A synthetic JPEG with valid SOI and EOI that passes the capture check, but whose SOF0
    segment has 0 components (byte 9 of the segment). `cv2.imdecode` returns None for it. The
    SOF0 length stays the same, so the header walk of 5.2 still reaches SOS."""
    jpeg = bytearray(synthetic_jpeg())
    sof = next(start for marker, start, _ in jpeg_segments(bytes(jpeg)) if marker == 0xC0)
    jpeg[sof + 9] = 0
    return bytes(jpeg)


def test_t_ring_41_decode_failure(cleanup, stages):
    """T-RING-41, sections 5.6, 8.4 (step 4) and 8.5 [D N:62, A41]: a JPEG with valid SOI and EOI
    that `cv2.imdecode` rejects, and one that decodes to a size other than the ring's. Both give
    `DECODE_ERROR`, the counter goes up, and the slots have no pixels.

    The first is a synthetic JPEG with 0 components in SOF0. The second is a valid 320x240
    synthetic JPEG on a 640x480 BGR ring. The set-up checks that both pass `check_jpeg`.
    """
    fr, writer, reader, shm = _bgr_ring(cleanup)
    rejected = _jpeg_that_imdecode_rejects()
    small = synthetic_jpeg(width=320, height=240)
    for jpeg in (rejected, small):
        assert fr.check_jpeg(jpeg, delivered_len=len(jpeg), driver_error=False) == (jpeg, 0)
    assert _imdecode(rejected) is None
    assert _imdecode(small).shape == (240, 320, 3)
    stage = start_stage(stages, writer)  # the decode call of 8.4 (decode_jpeg)
    for k, jpeg in enumerate((rejected, small)):
        stage.waiting_place.put(decode_input(jpeg, "JPEG", k))
        wait_committed(shm, k + 1)
    for k in (0, 1):
        read = reader.read(k)
        _assert_no_pixels(fr, read, shm, k)
        assert read.flags & ERROR_MASK == DECODE_ERROR
    header = parse_ring_header(shm.buf)
    assert header["decode_error_count"] == 2
    assert header["frames_committed"] == 2


@pytest.mark.parametrize("sampling", ["420", "422"])
def test_t_ring_41_valid_jpeg_decodes_to_imdecode_pixels(cleanup, stages, sampling):
    """T-RING-41 control, sections 5.5 and 8.4 (steps 3 and 5) [A41]: a valid synthetic JPEG
    (4:2:0 and 4:2:2) gives an `OK` BGR frame with the pixels of
    `cv2.imdecode(..., cv2.IMREAD_COLOR)`, and no `DECODE_ERROR`."""
    fr, writer, reader, shm = _bgr_ring(cleanup)
    jpeg = synthetic_jpeg(sampling)
    stage = start_stage(stages, writer)
    stage.waiting_place.put(decode_input(jpeg, "JPEG", 0, rotation=180))
    wait_committed(shm, 1)
    read = reader.read(0)
    assert read.result == fr.ReadResult.OK
    assert np.array_equal(read.payload, _imdecode(jpeg))
    assert read.rotation_cw_deg == 180
    assert parse_ring_header(shm.buf)["decode_error_count"] == 0


# ---------------------------------------------------------------------------
# T-RING-44: no spinning thread, under load
# ---------------------------------------------------------------------------

class TimedDecoder(CountingDecoder):
    """The reference decode (`decode_jpeg` of ADR-5MYA), timed in the thread that calls it."""

    def __init__(self):
        super().__init__()
        self.durations_ns = []

    def __call__(self, payload):
        self.threads.add(threading.get_ident())
        t0 = time.perf_counter_ns()
        bgr = ring().decode_jpeg(payload)
        self.durations_ns.append(time.perf_counter_ns() - t0)
        self.calls += 1
        return bgr


@pytest.mark.ring_slow
def test_t_ring_44_decode_speed_with_the_capture_stub(cleanup, stages):
    """T-RING-44, sections 8.4 and 8.10 [D N:88, A45]: time a reference decode (a 1920x1080
    synthetic JPEG, `decode_jpeg`) in the decode thread while the capture stub runs, against the
    same decode alone. The median with the capture stub is at most 1.3 times the median alone.

    Alone: the test puts one frame, then waits for its commit (a poll with a 1 ms sleep). With
    the capture stub: capture check, JPEG ring write and waiting place at 60 frames/s. Each case
    lasts TIMING_SECONDS (2 s; 10 s with SKELLYCAM_RING_FULL=1). The spec gives no duration.
    """
    jpeg = synthetic_jpeg(width=1920, height=1080)
    frames = int(60 * TIMING_SECONDS)
    medians = {}
    for index, case in enumerate(("alone", "with capture stub")):
        _, writer, _, shm = _bgr_ring(cleanup, width=1920, height=1080, camera_index=index)
        decoder = TimedDecoder()
        stage = start_stage(stages, writer, decode=decoder)
        if case == "alone":
            for k in range(frames):
                stage.waiting_place.put(decode_input(jpeg, "JPEG", k))
                wait_committed(shm, k + 1)
        else:
            _, _, jpeg_writer, _ = new_ring(cleanup, width=1920, height=1080, fps_num=60, camera_index=index)
            _capture_stub(jpeg_writer, jpeg, frames, 1 / 60, stage.waiting_place.put)
        stage.stop()
        assert threading.get_ident() not in decoder.threads, "the decode ran in the test thread"
        assert len(decoder.threads) == 1, "the decode ran in more than one thread"
        assert decoder.calls >= frames // 2, (case, decoder.calls)
        medians[case] = float(np.median(decoder.durations_ns))
    ratio = medians["with capture stub"] / medians["alone"]
    assert ratio <= 1.3, (f"decode median {medians['alone'] / 1e6:.2f} ms alone, "
                          f"{medians['with capture stub'] / 1e6:.2f} ms with the capture stub ({ratio:.2f} x)")


# ---------------------------------------------------------------------------
# T-RING-46: libjpeg warnings must not flood the log
# ---------------------------------------------------------------------------

LIBJPEG_WARNING = re.compile(r"Corrupt JPEG data: \d+ extraneous bytes before marker 0xd9")


def test_t_ring_46_libjpeg_warnings_do_not_flood_the_log():
    """T-RING-46, section 8.9 [A44]: decode 1,000 JPEGs with extra bytes before EOI (two
    different counts, thus two different warning lines). At most one log line per distinct
    message per minute, with a count, and no flood on descriptor 2.

    The stand-in camera process (ring_children.libjpeg_flood_main) runs with `subprocess`, so the
    test reads its descriptor 2. Its one decode before `limit_libjpeg_warnings()` proves that the
    warning exists: exactly that one warning line is on descriptor 2. A forwarded log line has the
    form `<line> (count <n>)` (ADR-5MYA). If the OpenCV log level silences the lines, no line is
    forwarded, and that also passes.
    """
    for count in LIBJPEG_EXTRA_BYTES:
        jpeg = junk_before_eoi(synthetic_jpeg(), count)
        assert ring().check_jpeg(jpeg, delivered_len=len(jpeg), driver_error=False)[1] == 0
        assert _imdecode(jpeg).shape == (480, 640, 3), "cv2.imdecode must still decode the frame"
    process = subprocess.run(
        [sys.executable, "-c", "from skellycam.tests.frame_ring.ring_children import libjpeg_flood_main;"
                               " libjpeg_flood_main()"],
        capture_output=True, text=True, timeout=120)
    assert process.returncode == 0, process.stderr[-2000:]
    stderr_warnings = LIBJPEG_WARNING.findall(process.stderr)
    assert len(stderr_warnings) == 1, (
        f"{len(stderr_warnings)} libjpeg warning lines on descriptor 2 (1 expected, from the set-up decode)")
    report = json.loads(process.stdout.strip().splitlines()[-1])
    allowed = 1 + int(report["elapsed_s"] // 60)
    forwarded = {}
    for message in report["messages"]:
        if LIBJPEG_WARNING.search(message):
            match = re.fullmatch(r"(?s)(.*) \(count (\d+)\)", message.strip())
            assert match, f"a forwarded line has no count: {message!r}"
            assert int(match.group(2)) >= 1
            forwarded.setdefault(LIBJPEG_WARNING.search(match.group(1)).group(0), []).append(message)
    for line, messages in forwarded.items():
        assert len(messages) <= allowed, f"{len(messages)} log lines for {line!r} in {report['elapsed_s']:.0f} s"


# ---------------------------------------------------------------------------
# T-RING-47: the uncompressed path (8.7)
# ---------------------------------------------------------------------------

def _raw_frame(source, k, width=640, height=480):
    """A synthetic YUY2 frame `(h, w, 2)` or NV12 frame `(h x 3 / 2, w)`, uint8, made with numpy:
    a new object for each frame (8.7, Quick Sync case)."""
    rng = np.random.default_rng(470 + k)
    shape = (height, width, 2) if source == "YUY2" else (height * 3 // 2, width)
    return rng.integers(16, 236, shape, dtype=np.uint8)


def _reference_bgr(raw, source):
    """The reference conversion: OpenCV's YUY2 and NV12 conversions (ADR-5MYA, until phase 3
    fixes the range rule of [D N:85])."""
    return cv2.cvtColor(raw, cv2.COLOR_YUV2BGR_YUY2 if source == "YUY2" else cv2.COLOR_YUV2BGR_NV12)


@pytest.mark.parametrize("source", ["YUY2", "NV12"])
def test_t_ring_47_quick_sync_case_converts_on_the_decode_thread(cleanup, stages, source):
    """T-RING-47, sections 8.7 (Quick Sync case) and 5.5 [A43]: the raw YUY2 or NV12 frame (a new
    object) goes to the waiting place, and the decode thread converts it. The BGR frame matches
    the reference conversion; the ring array does not share memory with the raw buffer; the JPEG
    decoder is not called."""
    fr, writer, reader, shm = _bgr_ring(cleanup)
    decoder = CountingDecoder()
    stage = start_stage(stages, writer, decode=decoder)
    for k in range(3):
        raw = _raw_frame(source, k)
        stage.waiting_place.put(decode_input(raw, source, k))
        wait_committed(shm, k + 1)
        read = reader.read(k)
        assert read.result == fr.ReadResult.OK, read.result
        assert type(read.payload) is np.ndarray and read.payload.shape == (480, 640, 3)
        assert np.array_equal(read.payload, _reference_bgr(raw, source))
        assert not np.shares_memory(read.payload, raw)
    assert decoder.calls == 0


@pytest.mark.parametrize("source", ["YUY2", "NV12"])
def test_t_ring_47_imencode_case_hands_over_a_copy(cleanup, stages, source):
    """T-RING-47, sections 8.7 (`cv2.imencode` case) and 5.3 [A43]: the recorder path converts
    each raw frame into its own BGR buffer and encodes it; it copies the buffer into a new array
    for the waiting place. The BGR frames match the reference conversion of their own frame; the
    ring array never shares memory with the recorder buffer; BGR skips (a slow BGR writer) leave
    the encoder path untouched.

    Needs a seam: the recorder path of phase 3 does not exist. The test plays it: it converts
    into one reused buffer, encodes it at quality 90 and hands over a copy (8.7). The decode stage
    is the product code under test.
    """
    fr = ring()
    _, creator, _, reader = new_ring(cleanup, bgr=True, fps_num=60)
    slow = cleanup.handle(attach_slow_writer(creator.name))
    shm = cleanup.handle(open_raw(creator.name))
    stage = start_stage(stages, slow)
    frames = 30
    recorder_buffer = np.empty((480, 640, 3), np.uint8)
    raws = [_raw_frame(source, k) for k in range(frames)]
    references = [_reference_bgr(raw, source) for raw in raws]
    encoded = []
    for k, raw in enumerate(raws):
        recorder_buffer[...] = _reference_bgr(raw, source)  # the conversion of the recorder path
        encoded.append(cv2.imencode(".jpg", recorder_buffer, JPEG_ENCODE_PARAMETERS)[1].tobytes())
        handed = recorder_buffer.copy()
        assert not np.shares_memory(handed, recorder_buffer)
        stage.waiting_place.put(decode_input(handed, "BGR", k))
        time.sleep(1 / 60)
    recorder_buffer[...] = 0  # a later frame of the recorder path must not reach the ring
    stage.stop()
    expected_jpegs = [cv2.imencode(".jpg", reference, JPEG_ENCODE_PARAMETERS)[1].tobytes()
                      for reference in references]
    assert encoded == expected_jpegs, "the BGR stage changed the encoder path"
    header = parse_ring_header(shm.buf)
    assert header["skipped_count"] >= 1, "the slow BGR writer caused no skip"
    # ADR-467Z item 2: stop() drops a frame that waits and counts it as skipped.
    assert header["frames_committed"] + header["skipped_count"] == frames, header
    numbers = committed_frame_numbers(shm)
    assert numbers, "no BGR frame was written"
    for k in numbers:
        read = reader.read(k)
        assert read.result == fr.ReadResult.OK, (k, read.result)
        assert np.array_equal(read.payload, references[k]), f"BGR frame {k} has the pixels of another frame"
