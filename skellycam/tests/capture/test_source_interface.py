"""T-CAP-01 to T-CAP-04: the capture interface and its waiting place (specs/windows-capture.md, 4.1 to 4.3).

The fake source puts each frame into `CaptureWaitingPlace` of the product (ADR-HP7D). Thus these
tests check the product rules of 4.3, through the calls of 4.1.
"""

import dataclasses
import threading
import time

import numpy as np
import pytest

from skellycam.tests.capture.capture_session import SOURCE_MODULE, product
from skellycam.tests.capture.fake_source import FakeScript, FakeSource, RealClock, VirtualClock


def _request(source_module, width=640, height=480, framerate=30.0):
    return source_module.CaptureRequest(camera_id="0", width=width, height=height, framerate=framerate,
                                        capture_fourcc="MJPG")


FIELDS_4_2 = {"payload": bytes, "format": str, "arrival_ns": int, "sample_ns": int, "delivered_len": int,
              "driver_error": bool, "source_frame_number": int, "discontinuity": bool}


def test_t_cap_01_each_frame_has_the_fields_of_4_2():
    """T-CAP-01, section 4.2: read 100 frames from a fake source. Each `CapturedFrame` has every field
    of 4.2 with its type; `source_frame_number` increases by 1 per delivered frame; `arrival_ns`
    increases."""
    source_module = product(SOURCE_MODULE)
    fake = FakeSource(FakeScript(), clock=VirtualClock())
    fake.open(_request(source_module))
    frames = [fake.read_frame(1.0) for _ in range(100)]
    assert [field.name for field in dataclasses.fields(source_module.CapturedFrame)] == list(FIELDS_4_2)
    for frame in frames:
        assert isinstance(frame, source_module.CapturedFrame)
        for name, kind in FIELDS_4_2.items():
            assert isinstance(getattr(frame, name), kind), f"{name} is {type(getattr(frame, name)).__name__}"
    numbers = [frame.source_frame_number for frame in frames]
    assert numbers == list(range(numbers[0], numbers[0] + 100)), "one step per delivered frame"
    arrivals = [frame.arrival_ns for frame in frames]
    assert all(b > a for a, b in zip(arrivals, arrivals[1:]))


def test_t_cap_02_newest_frame_wins_and_replaced_frames_count():
    """T-CAP-02, section 4.3 [D26]: the fake delivers frames 0 to 4 before the first `read_frame`,
    then frame 5 after it. The read gives frame 4; `replaced_count` is 4; the next read waits and
    gives frame 5."""
    source_module = product(SOURCE_MODULE)
    clock = VirtualClock()
    fake = FakeSource(FakeScript(), clock=clock)
    fake.open(_request(source_module))  # frame 0 comes in the open (6.4)
    frame_4_arrival = fake.log.first_read_sample_ns.value + round(4e9 / 30)
    clock.advance_to(frame_4_arrival)  # frames 1 to 4 arrive; nothing reads
    frame = fake.read_frame(1.0)
    assert frame.source_frame_number == 4
    assert fake.replaced_count == 4
    frame = fake.read_frame(1.0)
    assert frame.source_frame_number == 5
    assert clock.now_ns() == frame.arrival_ns > frame_4_arrival, "the second read waited for frame 5"


def test_t_cap_03_a_put_never_waits_on_the_consumer():
    """T-CAP-03, section 4.3 [D26, ring 8.3]: a consumer holds the waiting place busy; the producer
    puts 1,000 frames. Each put takes at most 1 ms at p99; no put waits on the consumer.

    The consumer takes in a loop and then works 50 ms on each frame, without the place. A put that
    waited on the consumer would take 40 ms or more."""
    source_module = product(SOURCE_MODULE)
    place = source_module.CaptureWaitingPlace()
    stop = threading.Event()

    def consumer():
        while not stop.is_set():
            if place.take(0.001) is not None:
                time.sleep(0.05)

    thread = threading.Thread(target=consumer, daemon=True)
    thread.start()
    durations = []
    try:
        for k in range(1000):
            frame = source_module.CapturedFrame(payload=b"\xff\xd8\xff\xd9", format="MJPG", arrival_ns=k, sample_ns=k,
                                                delivered_len=4, driver_error=False, source_frame_number=k,
                                                discontinuity=False)
            t0 = time.perf_counter_ns()
            place.put(frame)
            durations.append(time.perf_counter_ns() - t0)
            time.sleep(0.0005)
    finally:
        stop.set()
        thread.join(5)
    p99_ms = np.percentile(durations, 99) / 1e6
    assert p99_ms <= 1.0, f"put p99 {p99_ms:.3f} ms"
    assert max(durations) < 40e6, f"a put waited {max(durations) / 1e6:.1f} ms: it waited on the consumer"


@pytest.mark.capture_timing  # real-time bounds (0.1 s, 2 % of one core)
def test_t_cap_04_read_frame_times_out_without_spinning():
    """T-CAP-04, sections 4.1 and 4.3 [ring 8.10]: `read_frame(2.0)` with no frame. It returns `None`
    after 2.0 s (+/-0.1 s); the thread uses under 2 % of one core while it waits. Real time."""
    source_module = product(SOURCE_MODULE)
    fake = FakeSource(FakeScript(stop_after_frame=0), clock=RealClock())
    fake.open(_request(source_module))
    assert fake.read_frame(1.0).source_frame_number == 0
    cpu0, t0 = time.thread_time(), time.perf_counter()
    frame = fake.read_frame(2.0)
    elapsed, cpu = time.perf_counter() - t0, time.thread_time() - cpu0
    fake.close()
    assert frame is None
    assert 1.9 <= elapsed <= 2.1, f"read_frame returned after {elapsed:.3f} s"
    assert cpu / elapsed < 0.02, f"the waiting thread used {cpu / elapsed:.1%} of one core"
