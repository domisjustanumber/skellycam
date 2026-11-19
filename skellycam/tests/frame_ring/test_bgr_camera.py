"""The BGR ring in the camera process and the session: T-RING-37, 38, 39, 40, 45 and 47
(specs/frame-ring.md, sections 5.3, 7.1 to 7.3, 7.8, 8 and 9).

These tests use the production OpenCV camera loop (ring_session.camera_loop_thread) and
`CameraGroup` (ring_session.fake_session) with fake cameras. No camera and no camera frame is
used. Until phase 3, the BGR ring of a camera on OpenCV capture gets a copy of the BGR frame of
OpenCV through the waiting place, not a decode of the re-encoded JPEG (8.8 [A42]).
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

from skellycam.tests.frame_ring.ring_session import (
    camera_loop_thread,
    fake_configs,
    fake_session,
    poll,
    wait_until,
)
from skellycam.tests.frame_ring.ring_spec import (
    CAPTURE_ERROR,
    ERROR_MASK,
    NO_SOI_EOI,
    PIXEL_FORMAT_BGR24,
    WAIT_TIMEOUT_S,
    attach_slow_writer,
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


def _rings(cleanup, width=640, height=480, fps_num=60, bgr_writer=None):
    """A JPEG ring and a BGR ring of camera 0, their writers and a raw view of each block.
    `bgr_writer(name)` attaches the BGR writer (default: `FrameRingWriter.attach`)."""
    fr = ring()
    rings = {}
    for letter, pixel_format in (("J", fr.PixelFormat.JPEG), ("B", fr.PixelFormat.BGR24)):
        creator = cleanup.own(fr.FrameRingCreator.create(
            camera_id="0", camera_index=0, pixel_format=pixel_format, width=width, height=height,
            fps_num=fps_num, fps_den=1))
        attach = bgr_writer if letter == "B" and bgr_writer else fr.FrameRingWriter.attach
        rings[letter] = (creator.name, cleanup.handle(attach(creator.name)), cleanup.handle(open_raw(creator.name)))
    return fr, rings["J"], rings["B"]


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


def test_t_ring_38_slow_bgr_stage_in_the_camera_loop(monkeypatch, cleanup):
    """T-RING-38, sections 5.3, 8.3 and 8.8 [D N:60, N:78, A42]: the OpenCV loop with a fake camera
    at 60 frames/s and a slow BGR stage (each BGR write sleeps 100 ms). The JPEG ring gets every
    frame; the BGR skips are counted; the BGR frames are a subset of the JPEG frames.

    The timed rule of T-RING-38 (capture interval p99 within 10 %) is in test_decode_stage.py.
    """
    fr, (_, jpeg_writer, jpeg_shm), (_, bgr_writer, bgr_shm) = _rings(cleanup, bgr_writer=attach_slow_writer)
    with camera_loop_thread(monkeypatch, ring_writer=jpeg_writer, bgr_ring_writer=bgr_writer) as run:
        poll(lambda: raw_head(jpeg_shm) >= 60, "60 JPEG frames", run)
    assert not run.errors, run.errors
    jpeg = parse_ring_header(jpeg_shm.buf)
    frames = jpeg["head"] + 1
    assert jpeg["frames_committed"] == frames and jpeg["skipped_count"] == 0
    bgr = parse_ring_header(bgr_shm.buf)
    assert bgr["skipped_count"] >= 1, "no BGR skip counted"
    assert bgr["frames_committed"] >= 1
    # The loop can stop between the JPEG write and the hand-over, and one frame can wait.
    assert frames - 2 <= bgr["frames_committed"] + bgr["skipped_count"] <= frames, (bgr, frames)
    assert set(committed_frame_numbers(bgr_shm)) <= set(range(frames))


def test_t_ring_39_flagged_frame_in_the_camera_loop(monkeypatch, cleanup):
    """T-RING-39, sections 4, 5.3, 8.5 and 8.8 [D N:62, A15, A42]: in the OpenCV loop, the
    capture check flags frame 5 `NO_SOI_EOI` and frame 6 `CAPTURE_ERROR` (a wrapper of
    `check_jpeg`). Their BGR slots are flagged and have no pixels; the frames around them have
    pixels; `cv2.imdecode` is never called."""
    import skellycam.core.camera.opencv.opencv_camera_loop as loop_module

    fr, (_, jpeg_writer, _), (bgr_name, bgr_writer, bgr_shm) = _rings(cleanup)
    real_check = loop_module.check_jpeg
    calls = []

    def flagging_check(payload, **kwargs):
        payload, flags = real_check(payload, **kwargs)
        index = len(calls)
        calls.append(index)
        return payload, flags | {5: NO_SOI_EOI, 6: CAPTURE_ERROR}.get(index, 0)

    monkeypatch.setattr(loop_module, "check_jpeg", flagging_check)
    decodes = _count_imdecode(monkeypatch)
    reader = cleanup.handle(fr.FrameRingReader.attach(bgr_name))
    with camera_loop_thread(monkeypatch, ring_writer=jpeg_writer, bgr_ring_writer=bgr_writer, fps=30.0) as run:
        poll(lambda: reader.read(8).result != fr.ReadResult.NOT_YET_WRITTEN, "BGR frame 8", run)
    assert not run.errors, run.errors
    assert decodes == [], "the BGR stage decoded a JPEG"
    for k, flag in ((5, NO_SOI_EOI), (6, CAPTURE_ERROR)):
        read = reader.read(k)
        assert read.result == fr.ReadResult.FLAGGED, (k, read.result)
        assert read.payload is None
        assert read.flags & ERROR_MASK == flag
    for k in (4, 7):
        read = reader.read(k)
        assert read.result == fr.ReadResult.OK, (k, read.result)
        assert read.payload.shape == (480, 640, 3)
    header = parse_ring_header(bgr_shm.buf)
    assert header["cut_off_count"] == 1 and header["capture_error_count"] == 1


@pytest.mark.ring_slow
def test_t_ring_40_both_rings_match(monkeypatch, cleanup):
    """T-RING-40, sections 3.4, 8.6 and 8.8 [D N:61, N:79, A15]: 10,000 frames of the OpenCV loop
    with a fake camera; the test reads every number from both rings. For each number that both
    rings give: equal `frame_number`, `arrival_ns`, `sample_ns`, `source_frame_number` and
    `rotation_cw_deg`; the BGR `published_ns` is not earlier than that of the JPEG. Each number
    that the BGR ring does not give is a counted BGR skip.

    The fake camera gives 160x120 frames at up to 1,000 frames/s, and each ring has 1,000 slots,
    so that the reader keeps up. The run lasts about 10 to 30 s.
    """
    fr, (jpeg_name, jpeg_writer, jpeg_shm), (bgr_name, bgr_writer, bgr_shm) = _rings(
        cleanup, width=160, height=120, fps_num=1000)
    jpeg_reader = cleanup.handle(fr.FrameRingReader.attach(jpeg_name))
    bgr_reader = cleanup.handle(fr.FrameRingReader.attach(bgr_name))
    both = not_in_bgr = 0
    k = 0
    with camera_loop_thread(monkeypatch, ring_writer=jpeg_writer, bgr_ring_writer=bgr_writer,
                            width=160, height=120, fps=1000.0) as run:
        deadline = time.monotonic() + max(WAIT_TIMEOUT_S, 180.0)
        while k < FRAMES_T_RING_40:
            assert not run.errors, run.errors
            assert time.monotonic() < deadline, f"timed out at frame {k}"
            upto = min(raw_head(jpeg_shm), raw_head(bgr_shm), FRAMES_T_RING_40 - 1)
            while k <= upto:
                jpeg = jpeg_reader.read(k)
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
            time.sleep(0.001)
    assert both >= 1
    skipped = parse_ring_header(bgr_shm.buf)["skipped_count"]
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


def test_t_ring_47_opencv_source_hands_a_copy_to_the_decode_thread(monkeypatch, cleanup):
    """T-RING-47 and accepted item 42, sections 8.7 (`cv2.imencode` case) and 8.8 [A42, A43]:
    while a camera is on OpenCV capture, the waiting place gets the BGR frame of OpenCV as a new
    array (source "BGR"). That array never shares memory with the buffer of the recorder path
    (the frame record of the loop); the BGR ring holds that array; it is not a decode of the
    re-encoded JPEG (no `cv2.imdecode` call, and the pixels differ from a decode of the ring JPEG
    but are near them)."""
    fr, (jpeg_name, jpeg_writer, _), (bgr_name, bgr_writer, bgr_shm) = _rings(cleanup)
    handed = {}
    real_put = fr.WaitingPlace.put

    def spy_put(self, item):
        handed[item.frame_number] = item
        return real_put(self, item)

    monkeypatch.setattr(fr.WaitingPlace, "put", spy_put)
    decodes = _count_imdecode(monkeypatch)
    with camera_loop_thread(monkeypatch, ring_writer=jpeg_writer, bgr_ring_writer=bgr_writer, fps=30.0) as run:
        poll(lambda: parse_ring_header(bgr_shm.buf)["frames_committed"] >= 10, "10 BGR frames", run)
    assert not run.errors, run.errors
    assert decodes == [], "the BGR ring got a decode of the re-encoded JPEG"
    assert len(handed) >= 10
    recorder_buffer = run.frame_rec_array.image
    for item in handed.values():
        assert item.source == "BGR"
        assert type(item.payload) is np.ndarray and item.payload.shape == (480, 640, 3)
        assert item.payload.dtype == np.uint8 and item.payload.flags.c_contiguous
        assert not np.shares_memory(item.payload, recorder_buffer), "the hand-over is not a copy"
    assert len({id(item.payload) for item in handed.values()}) == len(handed), "one array for two frames"
    jpeg_reader = cleanup.handle(fr.FrameRingReader.attach(jpeg_name))
    bgr_reader = cleanup.handle(fr.FrameRingReader.attach(bgr_name))
    checked = 0
    for k in committed_frame_numbers(bgr_shm):
        bgr, jpeg = bgr_reader.read(k), jpeg_reader.read(k)
        if bgr.result != fr.ReadResult.OK or jpeg.result != fr.ReadResult.OK:
            continue
        assert np.array_equal(bgr.payload, handed[k].payload), k
        decoded = cv2.imdecode(np.frombuffer(jpeg.payload, np.uint8), cv2.IMREAD_COLOR)
        assert not np.array_equal(bgr.payload, decoded), "the BGR frame equals a decode of the JPEG"
        assert np.abs(bgr.payload.astype(np.int16) - decoded).mean() < 4, "BGR and JPEG are not one frame"
        checked += 1
    assert checked >= 5
