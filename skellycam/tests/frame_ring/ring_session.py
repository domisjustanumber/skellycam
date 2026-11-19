"""A camera session with fake cameras for the frame ring tests (T-RING-23, 25, 26, 27, 31, 33;
step 2b: T-RING-37 to 40, 45 and 47).

It uses the existing facilities of the code base: `MockVideoCapture` (tests/mocks), the
production `CameraGroup`, and `WorkerRegistry` in `WorkerMode.THREAD`, so that a monkeypatch of
`create_cv2_video_capture` reaches the camera workers. No camera and no camera frame is used.
"""

import asyncio
import contextlib
import logging
import multiprocessing
import threading
import time

import cv2

from skellycam.tests.frame_ring.ring_spec import WAIT_TIMEOUT_S
from skellycam.tests.mocks.camera_mock import MockVideoCapture


# OpenCV 5.1.0 crashes the process (access violation) when the garbage collector frees an instance
# of a Python subclass of cv2.VideoCapture. Thus each FakeCapture stays alive until the process ends.
_LIVE_CAPTURES = []


class FakeCapture(cv2.VideoCapture):
    """A `cv2.VideoCapture` (beartype checks the type) that serves the frames of
    `MockVideoCapture`, with the grab/retrieve pair that `opencv_get_frame` calls."""

    def __init__(self, width=640, height=480, fps=30.0):
        super().__init__()  # not opened: no device
        _LIVE_CAPTURES.append(self)
        self._mock = MockVideoCapture()
        self._mock._width, self._mock._height, self._mock._fps = float(width), float(height), float(fps)
        self._pending = None

    def isOpened(self):
        return self._mock.isOpened()

    def release(self):
        self._mock.release()

    def read(self, image=None):
        return self._mock.read()

    def get(self, prop_id):
        return self._mock.get(prop_id)

    def set(self, prop_id, value):
        return self._mock.set(prop_id, float(value))  # beartype: the mock takes a float

    def grab(self):
        ok, self._pending = self._mock.read()
        return ok

    def retrieve(self, image=None):
        if self._pending is None:
            return False, None
        if image is None:
            return True, self._pending
        image[...] = self._pending
        return True, image


def fake_create_cv2_video_capture(config):
    capture = FakeCapture(config.resolution.width, config.resolution.height, config.framerate)
    return capture, config


def patch_fakes(monkeypatch):
    import skellycam.core.camera.opencv.opencv_camera_loop as loop_module
    import skellycam.core.camera.opencv.opencv_helpers.setup_opencv_camera_loop as setup_module

    import skellylogs.handlers.websocket_log_queue_handler as log_queue_module

    # The app creates this queue at start. monkeypatch restores it, so other tests see no change.
    monkeypatch.setattr(log_queue_module, "WEBSOCKET_LOG_QUEUE", multiprocessing.Queue(maxsize=1000))
    monkeypatch.setattr(logging.Logger, "trace", logging.Logger.debug, raising=False)
    monkeypatch.setattr(logging.Logger, "success", logging.Logger.info, raising=False)
    monkeypatch.setattr(setup_module, "create_cv2_video_capture", fake_create_cv2_video_capture)
    monkeypatch.setattr(loop_module, "create_cv2_video_capture", fake_create_cv2_video_capture)


def fake_configs(count=2, width=640, height=480, fps=30.0, bgr_ids=()):
    """`bgr_ids`: the camera ids whose config asks for a BGR ring (`bgr_ring=True`, 8.1 [A39])."""
    from skellycam.core.camera.config.camera_config import CameraConfig
    from skellycam.core.camera.config.image_resolution import ImageResolution

    return {
        str(index): CameraConfig(camera_id=str(index), camera_index=index,
                                 resolution=ImageResolution(width=width, height=height),
                                 framerate=fps, **({"bgr_ring": True} if str(index) in bgr_ids else {}))
        for index in range(count)
    }


@contextlib.asynccontextmanager
async def fake_session(monkeypatch, configs):
    """Start a `CameraGroup` with fake cameras. Close it on exit, also after a failure."""
    from skellycam.core.camera_group.camera_group import CameraGroup
    from skellycam.core.ipc.process_management.managed_worker import WorkerMode
    from skellycam.core.ipc.process_management.worker_registry import WorkerRegistry

    patch_fakes(monkeypatch)
    kill = multiprocessing.Value("b", False)
    registry = WorkerRegistry(global_kill_flag=kill, worker_mode=WorkerMode.THREAD)
    group = CameraGroup.create(camera_configs=configs, heartbeat_timestamp=registry.heartbeat_timestamp,
                               global_kill_flag=kill, worker_registry=registry)
    try:
        await asyncio.wait_for(group.start(), WAIT_TIMEOUT_S)
        yield group
    finally:
        try:
            await asyncio.wait_for(group.close(), WAIT_TIMEOUT_S)
        finally:
            registry.shutdown_all()
            assert not registry.alive_workers, "a camera worker survived the session"


async def wait_until(predicate, what, timeout=WAIT_TIMEOUT_S):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, f"timed out: {what}"
        await asyncio.sleep(0.01)


def decode(jpeg):
    import numpy as np

    return cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)


class LoopRun:
    """The state of one run of `camera_loop_thread`."""

    def __init__(self, status, frame_rec_array, ipc):
        self.status = status
        self.frame_rec_array = frame_rec_array  # the buffer of the recorder path of the OpenCV loop
        self.ipc = ipc
        self.errors = []


@contextlib.contextmanager
def camera_loop_thread(monkeypatch, *, ring_writer, bgr_ring_writer, width=640, height=480, fps=60.0):
    """Run the production `run_opencv_camera_loop` in a thread with a fake capture source, a JPEG
    ring writer and a BGR ring writer (the argument `bgr_ring_writer` of ADR-5MYA). On exit, stop
    the loop and check that its thread ended, also after a failure.

    The set-up of the loop arguments is the set-up of the 2a tests (test_camera_process.py).
    """
    import skellycam.core.camera.opencv.opencv_camera_loop as loop_module
    from skellycam.core.camera.opencv.opencv_helpers.create_initial_frame_recarray import (
        create_initial_frame_rec_array,
    )
    from skellycam.core.camera_group.camera_group_ipc import CameraGroupIPC
    from skellycam.core.camera_group.camera_orchestrator import CameraOrchestrator
    from skellycam.core.camera_group.camera_status import CameraStatus
    from skellycam.core.ipc.pubsub.pubsub_manager import PubSubTopicManager

    patch_fakes(monkeypatch)
    config = fake_configs(1, width, height, fps)["0"]
    status = CameraStatus()
    status.connected.value = True
    orchestrator = CameraOrchestrator.from_statuses({config.camera_id: status})
    updates, recording = multiprocessing.Queue(), multiprocessing.Queue()
    ipc = CameraGroupIPC(
        group_id="ring-bgr", pubsub=PubSubTopicManager(topics={}),
        extracted_config_subscription=updates, recording_finished_subscription=recording,
        global_kill_flag=multiprocessing.Value("b", False),
        heartbeat_timestamp=multiprocessing.Value("d", time.perf_counter()))
    run = LoopRun(status, create_initial_frame_rec_array(config=config, ipc=ipc), ipc)

    def target():
        try:
            loop_module.run_opencv_camera_loop(
                ring_writer=ring_writer, bgr_ring_writer=bgr_ring_writer, config=config,
                cv2_video_capture=FakeCapture(width, height, fps), frame_rec_array=run.frame_rec_array,
                ipc=ipc, orchestrator=orchestrator, self_status=status,
                update_camera_settings_subscription=updates, recording_info_subscription=recording)
        except BaseException as error:
            run.errors.append(error)

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    try:
        yield run
    finally:
        status.should_close.value = True
        ipc.should_continue = False
        thread.join(timeout=WAIT_TIMEOUT_S)
        assert not thread.is_alive(), "the camera loop did not stop"


def poll(predicate, what, run=None, timeout=WAIT_TIMEOUT_S):
    """Wait until `predicate()` is true. Stop at once when the camera loop of `run` failed."""
    deadline = time.monotonic() + timeout
    while not predicate():
        assert run is None or not run.errors, f"the camera loop failed: {run.errors!r}"
        assert time.monotonic() < deadline, f"timed out: {what}"
        time.sleep(0.005)
