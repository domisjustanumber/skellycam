"""Process targets of the frame ring tests. Each runs in a `spawn` child process.

Each target imports the ring package itself. Each loop has a stop event or a time limit.
"""

import random
import time
import zlib

from skellycam.tests.frame_ring.ring_spec import (
    arrival_for,
    lap_payload,
    open_raw,
    paced_payload,
    parse_ring_header,
    raw_head,
    ring,
    write_kwargs,
)


def lap_writer(name, base_size, stop, ready):
    """T-RING-08: an unthrottled writer."""
    writer = ring().FrameRingWriter.attach(name)
    ready.set()
    k = 0
    try:
        while not stop.is_set():
            writer.write(lap_payload(k, base_size), **write_kwargs(k))
            k += 1
    finally:
        writer.close()


def lap_reader(name, mode, base_size, stop, ready, results):
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
                if (k is not None and n != k) or read.payload != lap_payload(n, base_size) \
                        or read.arrival_ns != arrival_for(n):
                    wrong.append(n)
        results.put(dict(mode=mode, counts=counts, wrong=wrong, failed_checks=reader.failed_checks))
    finally:
        raw.close()
        reader.close()


def kill_target_writer(name, payload_size, ready):
    """T-RING-11: writes large frames without a pause until the parent kills it."""
    writer = ring().FrameRingWriter.attach(name)
    ready.set()
    k = 0
    while True:
        writer.write(lap_payload(k, payload_size), **write_kwargs(k))
        k += 1


def timed_writer(name, payload_size, phase, stop, ready, results):
    """T-RING-12: writes about 500 frames/s and times each write by phase."""
    writer = ring().FrameRingWriter.attach(name)
    durations = {0: [], 1: []}
    ready.set()
    k = 0
    try:
        while not stop.is_set():
            payload = lap_payload(k, payload_size)
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


def busy_reader(name, payload_size, phase, stop, results):
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
                if read.payload != lap_payload(read.frame_number, payload_size):
                    wrong += 1
                elif phase.value == 1:
                    ok_after_kill += 1
        results.put(dict(ok_after_kill=ok_after_kill, wrong=wrong, errors=errors))
    finally:
        raw.close()
        reader.close()


def paced_writer(name, payload_size, fps, stop, ready):
    """T-RING-14: a writer at a fixed frame rate."""
    writer = ring().FrameRingWriter.attach(name)
    ready.set()
    period = 1.0 / fps
    start = time.perf_counter()
    k = 0
    try:
        while not stop.is_set():
            writer.write(paced_payload(k, payload_size), **write_kwargs(k))
            k += 1
            delay = start + k * period - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
    finally:
        writer.close()


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


def idle_camera_process(name, pause, paused, close, frames):
    """T-RING-31: the production OpenCV loop with a fake capture source and a ring writer.

    A helper thread copies the flags of the parent to the camera status every 50 ms.
    """
    import logging
    import multiprocessing
    import threading

    import skellycam.core.camera.opencv.opencv_camera_loop as loop_module
    from skellycam.core.camera_group.camera_group_ipc import CameraGroupIPC
    from skellycam.core.camera_group.camera_orchestrator import CameraOrchestrator
    from skellycam.core.camera_group.camera_status import CameraStatus
    from skellycam.core.camera.opencv.opencv_helpers.create_initial_frame_recarray import (
        create_initial_frame_rec_array,
    )
    from skellycam.core.ipc.pubsub.pubsub_manager import PubSubTopicManager
    from skellycam.tests.frame_ring.ring_session import FakeCapture, fake_configs

    logging.Logger.trace = logging.Logger.debug
    logging.Logger.success = logging.Logger.info
    writer = ring().FrameRingWriter.attach(name)
    config = fake_configs(1)["0"]
    status = CameraStatus()
    status.connected.value = True
    orchestrator = CameraOrchestrator.from_statuses({config.camera_id: status})
    updates, recording = multiprocessing.Queue(), multiprocessing.Queue()
    ipc = CameraGroupIPC(
        group_id="ring-idle", pubsub=PubSubTopicManager(topics={}),
        extracted_config_subscription=updates, recording_finished_subscription=recording,
        global_kill_flag=multiprocessing.Value("b", False),
        heartbeat_timestamp=multiprocessing.Value("d", time.perf_counter()))

    def mirror():
        while not close.value:
            status.should_pause.value = bool(pause.value)
            paused.value = bool(status.is_paused.value)
            frames.value = int(status.frame_count.value)
            time.sleep(0.05)
        status.should_close.value = True

    threading.Thread(target=mirror, daemon=True).start()
    try:
        loop_module.run_opencv_camera_loop(
            ring_writer=writer, config=config, cv2_video_capture=FakeCapture(640, 480, 30.0),
            frame_rec_array=create_initial_frame_rec_array(config=config, ipc=ipc), ipc=ipc,
            orchestrator=orchestrator, self_status=status,
            update_camera_settings_subscription=updates, recording_info_subscription=recording)
    finally:
        writer.close()
