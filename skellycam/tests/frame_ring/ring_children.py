"""Process targets of the frame ring tests. Each runs in a `spawn` child process.

Each target imports the ring package itself. Each loop has a stop event or a time limit.
"""

import random
import time
import zlib

from skellycam.tests.frame_ring.ring_spec import (
    arrival_for,
    as_bytes,
    lap_payload,
    open_raw,
    paced_payload,
    parse_ring_header,
    raw_head,
    ring,
    ring_payload,
    write_kwargs,
)

# `shape` in a target below: the ring is a BGR ring of that shape (T-RING-36), and the payload is
# the synthetic payload as an array. Without it, the target writes and reads JPEG payloads.


def lap_writer(name, base_size, stop, ready, shape=None):
    """T-RING-08: an unthrottled writer."""
    writer = ring().FrameRingWriter.attach(name)
    ready.set()
    k = 0
    try:
        while not stop.is_set():
            writer.write(ring_payload(lap_payload, k, base_size, shape), **write_kwargs(k))
            k += 1
    finally:
        writer.close()


def lap_reader(name, mode, base_size, stop, ready, results, shape=None):
    """T-RING-08: a reader at the oldest frame, the newest frame or by number."""
    fr = ring()
    reader = fr.FrameRingReader.attach(name)
    raw = open_raw(name)
    slot_count = parse_ring_header(raw.buf)["slot_count"]
    counts = {}
    wrong = []
    ready.set()
    try:
        while not stop.is_set():
            head = raw_head(raw)
            if head < 0:
                time.sleep(0.001)
                continue
            if mode == "newest":
                k = None
                read = reader.read_newest()
            else:
                k = max(0, head - slot_count + 1) if mode == "oldest" else random.randint(
                    max(0, head - slot_count + 1), head)
                read = reader.read(k)
            counts[read.result.name] = counts.get(read.result.name, 0) + 1
            if read.result == fr.ReadResult.OK:
                n = read.frame_number
                expected = as_bytes(ring_payload(lap_payload, n, base_size, shape))
                if (k is not None and n != k) or as_bytes(read.payload) != expected \
                        or read.arrival_ns != arrival_for(n):
                    wrong.append(n)
        results.put(dict(mode=mode, counts=counts, wrong=wrong, failed_checks=reader.failed_checks))
    finally:
        raw.close()
        reader.close()


def kill_target_writer(name, payload_size, ready, shape=None):
    """T-RING-11: writes large frames without a pause until the parent kills it."""
    writer = ring().FrameRingWriter.attach(name)
    ready.set()
    k = 0
    while True:
        writer.write(ring_payload(lap_payload, k, payload_size, shape), **write_kwargs(k))
        k += 1


def timed_writer(name, payload_size, phase, stop, ready, results, shape=None):
    """T-RING-12: writes about 500 frames/s and times each write by phase."""
    writer = ring().FrameRingWriter.attach(name)
    durations = {0: [], 1: []}
    ready.set()
    k = 0
    try:
        while not stop.is_set():
            payload = ring_payload(lap_payload, k, payload_size, shape)
            kwargs = write_kwargs(k)
            current = phase.value
            t0 = time.perf_counter_ns()
            writer.write(payload, **kwargs)
            durations[current].append(time.perf_counter_ns() - t0)
            k += 1
            time.sleep(0.002)
        results.put(durations)
    finally:
        writer.close()


def busy_reader(name, payload_size, phase, stop, results, shape=None):
    """T-RING-12: a reader that copies large frames in a loop. The parent kills one of them."""
    fr = ring()
    reader = fr.FrameRingReader.attach(name)
    raw = open_raw(name)
    ok_after_kill = 0
    wrong = 0
    errors = []
    try:
        while not stop.is_set():
            head = raw_head(raw)
            if head < 0:
                time.sleep(0.001)
                continue
            try:
                read = reader.read(head)
            except Exception as error:  # an exception counts as "affected"
                errors.append(repr(error))
                continue
            if read.result == fr.ReadResult.OK:
                if as_bytes(read.payload) != as_bytes(
                        ring_payload(lap_payload, read.frame_number, payload_size, shape)):
                    wrong += 1
                elif phase.value == 1:
                    ok_after_kill += 1
        results.put(dict(ok_after_kill=ok_after_kill, wrong=wrong, errors=errors))
    finally:
        raw.close()
        reader.close()


def paced_writer(name, payload_size, fps, stop, ready, shape=None):
    """T-RING-14: a writer at a fixed frame rate."""
    writer = ring().FrameRingWriter.attach(name)
    ready.set()
    period = 1.0 / fps
    start = time.perf_counter()
    k = 0
    try:
        while not stop.is_set():
            writer.write(ring_payload(paced_payload, k, payload_size, shape), **write_kwargs(k))
            k += 1
            delay = start + k * period - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
    finally:
        writer.close()


def hold_lock_forever(value, held):
    """Take the lock of a shared Value and keep it until the process is killed (the cause of the hang of
    2026-11-21: a reader killed inside `phase.value` keeps the lock, and each later write waits for ever)."""
    value.get_lock().acquire()
    held.set()
    while True:
        time.sleep(1)


def hammer_reader(name, stop):
    """T-RING-23: a reader that reads the newest frame as fast as it can."""
    reader = ring().FrameRingReader.attach(name)
    try:
        while not stop.is_set():
            reader.read_newest()
    finally:
        reader.close()


def attach_and_exit(name, results):
    """T-RING-30: a reader attaches, reads one frame and exits."""
    reader = ring().FrameRingReader.attach(name)
    read = reader.read_newest()
    results.put((read.result.name, zlib.crc32(read.payload or b"")))
    reader.close()


def crash_creator_main():
    """T-RING-28: a stand-in for the main skellycam process. It creates a ring, prints its name
    and waits to be killed.

    The test starts it with `subprocess`, not `multiprocessing`: a `spawn` child shares the
    resource tracker of its parent, but the main skellycam process has its own tracker.
    """
    fr = ring()
    creator = fr.FrameRingCreator.create(
        camera_id="crash", camera_index=7, pixel_format=fr.PixelFormat.JPEG, width=640,
        height=480, fps_num=30, fps_den=1)
    print(creator.name, flush=True)
    time.sleep(600)


LIBJPEG_EXTRA_BYTES = (601, 100)  # T-RING-46: two different warning lines


def libjpeg_flood_main():
    """T-RING-46: a stand-in camera process. The test starts it with `subprocess`, so that its
    descriptor 2 is a pipe that the test reads.

    1. One decode before the product call: libjpeg writes its warning to descriptor 2 one time.
       This proves that the warning exists on this machine.
    2. `limit_libjpeg_warnings()` (ADR-5MYA), the call of the camera process at start (8.9).
    3. 1,000 decodes with `decode_jpeg` (8.4), 500 of each JPEG of LIBJPEG_EXTRA_BYTES.
    4. Print one JSON line on descriptor 1: the log messages and the elapsed time.
    """
    import json
    import logging

    import cv2
    import numpy as np

    from skellycam.tests.frame_ring.ring_spec import junk_before_eoi, synthetic_jpeg

    messages = []

    class Keep(logging.Handler):
        def emit(self, record):
            messages.append(record.getMessage())

    fr = ring()
    root = logging.getLogger()
    root.handlers[:] = [Keep()]  # no log line goes to descriptor 2
    root.setLevel(logging.DEBUG)
    jpegs = [junk_before_eoi(synthetic_jpeg(), count) for count in LIBJPEG_EXTRA_BYTES]
    first = cv2.imdecode(np.frombuffer(jpegs[0], np.uint8), cv2.IMREAD_COLOR)  # step 1
    assert first is not None and first.shape == (480, 640, 3)
    start = time.monotonic()
    fr.limit_libjpeg_warnings()  # step 2
    for i in range(1000):  # step 3
        bgr = fr.decode_jpeg(jpegs[i % 2])
        assert bgr is not None and bgr.shape == (480, 640, 3)
    time.sleep(1.0)  # a forwarding thread reads the pipe
    elapsed = time.monotonic() - start
    print(json.dumps(dict(messages=messages, elapsed_s=elapsed)), flush=True)


def opencv_threads_in_session_main():
    """T-RING-45: a camera session with fake cameras and a BGR ring request, in its own main
    process. Print `cv2.getNumThreads()` after the first frame, as one JSON line on descriptor 1.

    The test starts it with `subprocess`: `CameraGroup` refuses to start in a `multiprocessing`
    child. The workers run in this process (`WorkerMode.THREAD`), so this process is the camera
    process. It sets 4 OpenCV threads first. Thus the result does not depend on the core count.
    """
    import asyncio
    import json

    import cv2
    import pytest

    from skellycam.tests.frame_ring.ring_session import fake_configs, fake_session, wait_until

    async def main():
        with pytest.MonkeyPatch.context() as monkeypatch:
            async with fake_session(monkeypatch, fake_configs(1, bgr_ids=("0",))) as group:
                reader = ring().FrameRingReader.attach(group.ring_infos["0"].jpeg_ring_name)
                try:
                    await wait_until(lambda: reader.read_newest().result.name == "OK", "first frame")
                finally:
                    reader.close()
                return cv2.getNumThreads()

    cv2.setNumThreads(4)
    threads = asyncio.run(main())
    print(json.dumps(dict(threads=threads)), flush=True)
