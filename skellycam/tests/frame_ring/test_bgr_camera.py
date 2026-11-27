"""The BGR ring in the camera process and the session: T-RING-37, 38, 39, 40, 45 and 47
(specs/frame-ring.md, sections 5.3, 7.1 to 7.3, 7.8, 8 and 9).

These tests run the shared camera loop of phase 3: `CameraGroup` with the OpenCV source and a fake
capture (ring_session.fake_session), or the capture app with the fake source of
specs/windows-capture.md, section 16.1 (capture_session.capture_app). No camera and no camera frame
is used. The BGR ring of a camera on OpenCV capture gets the BGR frame of OpenCV through the waiting
place, not a decode of the re-encoded JPEG (8.8 [A42]).
"""

import json
import logging
import os
import re
import subprocess
import sys
import time

import cv2
import numpy as np
import pytest

from skellycam.tests.capture.capture_session import (
    capture_app, hold_clock_from_the_ring_open, hold_clock_while_behind)
from skellycam.tests.capture.fake_source import FakeScript
from skellycam.tests.frame_ring.ring_session import (
    fake_configs,
    fake_session,
    wait_until,
)
from skellycam.tests.frame_ring.ring_spec import (
    CAPTURE_ERROR,
    ERROR_MASK,
    NO_SOI_EOI,
    PIXEL_FORMAT_BGR24,
    WAIT_TIMEOUT_S,
    bgr_size,
    committed_frame_numbers,
    open_raw,
    parse_ring_header,
    raw_head,
    ring,
    ring_exists,
)
from skellycam.tests.frame_ring.test_lifecycle import _bytes_pattern, _wait_gone

FRAMES_T_RING_40 = 10_000


def _ready_fake_camera(cleanup, app, until=("ready",), hold=True):
    """Apply the one fake camera of `app` with a BGR ring and wait until it is in a state of `until`. Give its
    ID, and the names and raw views (open after the close of the session) of its JPEG and BGR rings. A camera
    that ends soon after `ready` must also accept `dead`: on the virtual clock its time in `ready` can be
    shorter than one poll of `wait_state` (as `capture_session.one_camera`). The views open just after the apply,
    before the wait: the group watch closes the rings of a camera whose loop ended [ADR-2HW5]."""
    camera_id = app.factory.camera_ids[0]
    if hold:  # a reader of the test holds the clock from the open of the JPEG ring; it must call
        # `hold_clock_while_behind` next and leave the clock before the close (`hold_clock_from_the_ring_open`)
        hold_clock_from_the_ring_open(app, camera_id)
    try:
        app.detect()
        response = app.apply([app.config(camera_id, bgr_ring=True)])
        assert response.status_code == 200, response.text
        info = app.group.ring_infos[camera_id]  # the apply returns after the open of the rings (CameraGroup.start)
        names = (info.jpeg_ring_name, info.bgr_ring_name)
        views = [cleanup.handle(open_raw(name)) for name in names]
        app.wait_state(camera_id, *until)
    except BaseException:
        if hold:
            app.clock.leave()
        raise
    return camera_id, names, views


def _count_imdecode(monkeypatch):
    """Count the calls of `cv2.imdecode` in this process."""
    calls = []
    real = cv2.imdecode

    def counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(cv2, "imdecode", counting)
    return calls


async def test_t_ring_37_bgr_ring_only_when_asked(monkeypatch, caplog, cleanup):
    """T-RING-37, sections 3.6, 3.8, 7.1 to 7.3, 7.8, 8.1 and 9 [A39, A46, D N:51]: a session
    with one camera config with `bgr_ring=True` and one without. The BGR ring and its name exist
    only for the camera that asks; its size is logged; it has the layout of section 3 with
    `pixel_format = 2`; it is gone after the session."""
    fr = ring()
    configs = fake_configs(2, 640, 480, 30.0, bgr_ids=("0",))
    assert configs["0"].bgr_ring is True, "8.1: `bgr_ring` is a field of CameraConfig"
    assert configs["1"].bgr_ring is False, "8.1: `bgr_ring` is off by default"
    jpeg_ring = 8192 + 30 * 311_296  # tables 3.6 and 3.8: 640x480, N = 30
    bgr_ring = 8192 + 30 * bgr_size()
    total = 2 * jpeg_ring + bgr_ring
    pid = os.getpid()
    with caplog.at_level(logging.DEBUG):
        async with fake_session(monkeypatch, configs) as group:
            assert group.ring_infos["1"].bgr_ring_name is None
            name = group.ring_infos["0"].bgr_ring_name
            assert name is not None, "no BGR ring for the camera that asked for it"
            assert re.fullmatch(rf"skc{pid:x}_0_B\d+", name) and len(name) <= 30
            raw = open_raw(name)
            try:
                header = parse_ring_header(raw.buf)
            finally:
                raw.close()
            assert header["pixel_format"] == PIXEL_FORMAT_BGR24
            assert (header["width"], header["height"]) == (640, 480)
            assert header["slot_capacity"] == bgr_size()
            assert header["slot_count"] == 30 and header["history_ms"] == 1000
            assert header["total_size"] == bgr_ring
            assert header["camera_index"] == 0
            reader = cleanup.handle(fr.FrameRingReader.attach(name))
            try:
                await wait_until(lambda: reader.read_newest().result == fr.ReadResult.OK, "first BGR frame")
                read = reader.read_newest()
            finally:
                reader.close()
            assert type(read.payload) is np.ndarray and read.payload.shape == (480, 640, 3)
            for generation in range(64):
                assert not ring_exists(f"skc{pid:x}_1_B{generation}"), "a BGR ring that nobody asked for"
    log = " ".join(record.getMessage() for record in caplog.records)
    assert re.search(_bytes_pattern(bgr_ring), log), "BGR ring size not logged"
    assert re.search(_bytes_pattern(total), log), "session total with the BGR ring not logged in bytes"
    assert f"{total / 2 ** 20:.1f} MiB" in log, "session total with the BGR ring not logged in MiB"
    assert _wait_gone(name, timeout=5), f"BGR ring {name} left after the session"


async def test_t_ring_37_bgr_ring_recreated_on_a_mode_change(monkeypatch, cleanup):
    """T-RING-37 with T-RING-26, sections 7.2, 7.4, 7.5 and 8.1 [A17, A33, A35, A39] (user,
    2026-11-19): change the resolution of a fake camera with `bgr_ring=True`. Its BGR ring is
    recreated as its JPEG ring is: a new name (generation + 1); the old ring has `closed = 1`; old
    readers get `CLOSED`; the old segment is gone; the new ring has the new shape."""
    fr = ring()
    async with fake_session(monkeypatch, fake_configs(2, 640, 480, 30.0, bgr_ids=("0",))) as group:
        old = group.ring_infos["0"].bgr_ring_name
        old_reader = cleanup.handle(fr.FrameRingReader.attach(old))
        old_raw = cleanup.handle(open_raw(old))
        await wait_until(lambda: old_reader.read_newest().result == fr.ReadResult.OK, "first BGR frame")
        await group.update_camera_settings(fake_configs(2, 1280, 720, 30.0, bgr_ids=("0",)))
        new = group.ring_infos["0"].bgr_ring_name
        assert new is not None and new != old
        assert int(new.rsplit("B", 1)[1]) == int(old.rsplit("B", 1)[1]) + 1
        assert group.ring_infos["1"].bgr_ring_name is None
        assert parse_ring_header(old_raw.buf)["closed"] == 1
        assert old_reader.read_newest().result == fr.ReadResult.CLOSED
        old_reader.close()
        old_raw.close()
        assert _wait_gone(old), f"old BGR ring {old} still opens by name"
        raw = open_raw(new)
        try:
            header = parse_ring_header(raw.buf)
        finally:
            raw.close()
        assert header["pixel_format"] == PIXEL_FORMAT_BGR24
        assert (header["width"], header["height"]) == (1280, 720)
        assert header["slot_capacity"] == bgr_size(1280, 720)
        new_reader = cleanup.handle(fr.FrameRingReader.attach(new))
        await wait_until(lambda: new_reader.read_newest().result == fr.ReadResult.OK, "first new BGR frame")
        read = new_reader.read_newest()
        assert read.frame_number >= 0
        assert type(read.payload) is np.ndarray and read.payload.shape == (720, 1280, 3)
        new_reader.close()


def test_t_ring_38_slow_bgr_stage_in_the_camera_loop(monkeypatch, cleanup):
    """T-RING-38, sections 5.3, 8.3 and 8.8 [D N:60, N:78, A42]: the shared loop with a fake source
    at 60 frames/s and a slow BGR stage (each BGR write sleeps 100 ms). The JPEG ring gets every
    frame; the BGR skips are counted; the BGR frames are a subset of the JPEG frames.

    The fake delivers no frame after source frame 200. The loop then ends (`dead` after the stall of
    2 s of the virtual clock) and stops its decode stage, and the test reads the counters after that
    end. A close of the group would close the rings first, and a slow BGR write would then be lost.

    The timed rule of T-RING-38 (capture interval p99 within 10 %) is in test_decode_stage.py.
    """
    fr = ring()
    real_write = fr.FrameRingWriter.write

    def slow_bgr_write(writer, payload, **kwargs):
        if payload is None or isinstance(payload, np.ndarray):  # a BGR frame
            time.sleep(0.1)
        return real_write(writer, payload, **kwargs)

    monkeypatch.setattr(fr.FrameRingWriter, "write", slow_bgr_write)
    with capture_app(monkeypatch, [FakeScript(modes=((640, 480, 60, 1, "MJPG"),), stop_after_frame=200)]) as app:
        camera_id, _, (jpeg_shm, bgr_shm) = _ready_fake_camera(cleanup, app, until=("ready", "dead"), hold=False)
        app.wait(lambda: app.status(camera_id)["closed"], "the end of the loop after the last frame")
    jpeg = parse_ring_header(jpeg_shm.buf)
    frames = jpeg["head"] + 1
    assert frames >= 60, frames
    assert jpeg["frames_committed"] == frames and jpeg["skipped_count"] == 0
    bgr = parse_ring_header(bgr_shm.buf)
    assert bgr["skipped_count"] >= 1, ("no BGR skip counted", bgr["frames_committed"], frames)
    assert bgr["frames_committed"] >= 1
    # The loop can stop between the JPEG write and the hand-over, and one frame can wait.
    assert frames - 2 <= bgr["frames_committed"] + bgr["skipped_count"] <= frames, (bgr, frames)
    assert set(committed_frame_numbers(bgr_shm)) <= set(range(frames))


async def test_t_ring_39_flagged_frame_in_the_camera_loop(monkeypatch, cleanup):
    """T-RING-39, sections 4, 5.3, 8.5 and 8.8 [D N:62, A15, A42]: in the shared loop with the
    OpenCV source, the capture check flags ring frame 5 `NO_SOI_EOI` and ring frame 6
    `CAPTURE_ERROR` (a wrapper of `check_jpeg`, which the loop calls once for each ring frame).
    Their BGR slots are flagged and have no pixels; the frames around them have pixels;
    `cv2.imdecode` is never called."""
    import skellycam.core.camera.capture.camera_loop as loop_module

    fr = ring()
    real_check = loop_module.check_jpeg
    calls = []

    def flagging_check(payload, **kwargs):
        payload, flags = real_check(payload, **kwargs)
        index = len(calls)
        calls.append(index)
        return payload, flags | {5: NO_SOI_EOI, 6: CAPTURE_ERROR}.get(index, 0)

    monkeypatch.setattr(loop_module, "check_jpeg", flagging_check)
    decodes = _count_imdecode(monkeypatch)
    async with fake_session(monkeypatch, fake_configs(1, bgr_ids=("0",))) as group:
        bgr_name = group.ring_infos["0"].bgr_ring_name
        reader = cleanup.handle(fr.FrameRingReader.attach(bgr_name))
        bgr_shm = cleanup.handle(open_raw(bgr_name))
        await wait_until(lambda: reader.read(8).result != fr.ReadResult.NOT_YET_WRITTEN, "BGR frame 8")
        reads = {k: reader.read(k) for k in (4, 5, 6, 7)}
        header = parse_ring_header(bgr_shm.buf)
    assert decodes == [], "the BGR stage decoded a JPEG"
    for k, flag in ((5, NO_SOI_EOI), (6, CAPTURE_ERROR)):
        read = reads[k]
        assert read.result == fr.ReadResult.FLAGGED, (k, read.result)
        assert read.payload is None
        assert read.flags & ERROR_MASK == flag
    for k in (4, 7):
        read = reads[k]
        assert read.result == fr.ReadResult.OK, (k, read.result)
        assert read.payload.shape == (480, 640, 3)
    assert header["cut_off_count"] == 1 and header["capture_error_count"] == 1


@pytest.mark.ring_slow
def test_t_ring_40_both_rings_match(monkeypatch, cleanup):
    """T-RING-40, sections 3.4, 8.6 and 8.8 [D N:61, N:79, A15]: 10,000 frames of the shared loop
    with a fake source; the test reads every number from both rings. For each number that both
    rings give: equal `frame_number`, `arrival_ns`, `sample_ns`, `source_frame_number` and
    `rotation_cw_deg`; the BGR `published_ns` is not earlier than that of the JPEG. Each number
    that the BGR ring does not give is a counted BGR skip.

    The fake source gives 640x360 MJPG frames (the smallest size of the floor, windows-capture.md 22.2, Q888)
    at 100 frames/s of a virtual clock, and each ring has 100 slots (about 89 MiB for the two rings, near the
    82 MB of the 160x120 frames at 1,000 slots before the floor). The test thread holds the clock from the open of
    the JPEG ring until its first read, and while it is half of the slots (50 frames) behind the ring, so that the
    reader keeps up also on a slow machine (`hold_clock_from_the_ring_open`, `hold_clock_while_behind`) [ADR-2HW5].
    """
    fr = ring()
    both = not_in_bgr = 0
    k = 0
    with capture_app(monkeypatch, [FakeScript(modes=((640, 360, 100, 1, "MJPG"),))]) as app:
        camera_id, names, (jpeg_shm, bgr_shm) = _ready_fake_camera(cleanup, app)
        jpeg_reader, bgr_reader = (cleanup.handle(fr.FrameRingReader.attach(name)) for name in names)
        deadline = time.monotonic() + max(WAIT_TIMEOUT_S, 180.0)
        try:
            while k < FRAMES_T_RING_40:
                assert app.state(camera_id) == "ready", app.status(camera_id)
                assert time.monotonic() < deadline, f"timed out at frame {k}"
                upto = min(raw_head(jpeg_shm), raw_head(bgr_shm), FRAMES_T_RING_40 - 1)
                while k <= upto:
                    jpeg = jpeg_reader.read(k)
                    hold_clock_while_behind(app.clock, jpeg_reader, k)
                    bgr = bgr_reader.read(k)
                    assert jpeg.result == fr.ReadResult.OK, (k, jpeg.result)
                    if bgr.result == fr.ReadResult.OK:
                        both += 1
                        assert (bgr.frame_number, bgr.arrival_ns, bgr.sample_ns) == (
                            jpeg.frame_number, jpeg.arrival_ns, jpeg.sample_ns), k
                        assert (bgr.source_frame_number, bgr.rotation_cw_deg) == (
                            jpeg.source_frame_number, jpeg.rotation_cw_deg), k
                        assert bgr.published_ns >= jpeg.published_ns, k
                    else:
                        assert bgr.result in (fr.ReadResult.MISSING, fr.ReadResult.LAPPED), (k, bgr.result)
                        not_in_bgr += 1
                    k += 1
                hold_clock_while_behind(app.clock, jpeg_reader, k)
                time.sleep(0.001)
        finally:
            app.clock.leave()  # before the close: the gate reads the ring
        skipped = parse_ring_header(bgr_shm.buf)["skipped_count"]
    assert both >= 1
    assert not_in_bgr <= skipped, f"{not_in_bgr} numbers not in the BGR ring, {skipped} BGR skips counted"


def test_t_ring_45_one_opencv_thread():
    """T-RING-45, section 8.2 [D N:60]: in a camera process with a BGR ring request,
    `cv2.getNumThreads() == 1`.

    A separate main process runs a session with one fake camera
    (ring_children.opencv_threads_in_session_main). It sets 4 OpenCV threads before the session.
    """
    process = subprocess.run(
        [sys.executable, "-c", "from skellycam.tests.frame_ring.ring_children import"
                               " opencv_threads_in_session_main; opencv_threads_in_session_main()"],
        capture_output=True, text=True, timeout=4 * WAIT_TIMEOUT_S)
    assert process.returncode == 0, process.stderr[-3000:]
    threads = json.loads(process.stdout.strip().splitlines()[-1])["threads"]
    assert threads == 1, f"cv2.getNumThreads() is {threads} in the camera process"


async def test_t_ring_47_opencv_source_hands_a_copy_to_the_decode_thread(monkeypatch, cleanup):
    """T-RING-47 and accepted item 42, sections 8.7 (`cv2.imencode` case) and 8.8 [A42, A43]:
    while a camera is on OpenCV capture (the shared loop with the OpenCV source), the waiting place
    gets the BGR frame of OpenCV as a new array (source "BGR"), one array for each frame; the BGR
    ring holds that array; it is not a decode of the re-encoded JPEG (no `cv2.imdecode` call, and the
    pixels differ from a decode of the ring JPEG but are near them). The recorder path has no image
    buffer since step 5a: the take recorder takes the JPEG (recorder.md section 10 item 6)."""
    fr = ring()
    handed = {}
    real_put = fr.WaitingPlace.put

    def spy_put(self, item):
        handed[item.frame_number] = item
        return real_put(self, item)

    monkeypatch.setattr(fr.WaitingPlace, "put", spy_put)
    decodes = _count_imdecode(monkeypatch)
    async with fake_session(monkeypatch, fake_configs(1, bgr_ids=("0",))) as group:
        info = group.ring_infos["0"]
        bgr_shm = cleanup.handle(open_raw(info.bgr_ring_name))
        await wait_until(lambda: parse_ring_header(bgr_shm.buf)["frames_committed"] >= 10, "10 BGR frames")
        jpeg_reader = cleanup.handle(fr.FrameRingReader.attach(info.jpeg_ring_name))
        bgr_reader = cleanup.handle(fr.FrameRingReader.attach(info.bgr_ring_name))
        reads = {k: (bgr_reader.read(k), jpeg_reader.read(k)) for k in committed_frame_numbers(bgr_shm)}
    assert decodes == [], "the BGR ring got a decode of the re-encoded JPEG"
    assert len(handed) >= 10
    for item in handed.values():
        assert item.source == "BGR"
        assert type(item.payload) is np.ndarray and item.payload.shape == (480, 640, 3)
        assert item.payload.dtype == np.uint8 and item.payload.flags.c_contiguous
    assert len({id(item.payload) for item in handed.values()}) == len(handed), "one array for two frames"
    checked = 0
    for k, (bgr, jpeg) in reads.items():
        if bgr.result != fr.ReadResult.OK or jpeg.result != fr.ReadResult.OK:
            continue
        assert np.array_equal(bgr.payload, handed[k].payload), k
        decoded = cv2.imdecode(np.frombuffer(jpeg.payload, np.uint8), cv2.IMREAD_COLOR)
        assert not np.array_equal(bgr.payload, decoded), "the BGR frame equals a decode of the JPEG"
        assert np.abs(bgr.payload.astype(np.int16) - decoded).mean() < 4, "BGR and JPEG are not one frame"
        checked += 1
    assert checked >= 5
