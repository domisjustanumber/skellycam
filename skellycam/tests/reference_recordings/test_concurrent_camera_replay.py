"""Three reference videos through the shared camera loop (specs/windows-capture.md, sections 5 and 14.1).

The production `CameraGroup` runs THREAD workers with the OpenCV source. The OpenCV source gets a
file-backed capture of each video that gives one frame on each 1/60 s of real time and reports
60 fps: the loop refuses a mode under 30 fps (14.1), and it checks the rate of the warm-up frames
(9.2). The warm-up and the wait for the other cameras use about the first 90 frames of each video.

A spy on each JPEG ring write reads the frame back from the ring and compares it with the frame of
the video at its `source_frame_number` (mean absolute difference under 8 for the q90 JPEG, over the
whole image: the shared loop stamps no text, U2). Extra work in one camera exercises unequal
progress through the lockstep gate. No camera and no camera frame is used.
"""

import asyncio
import contextlib
import multiprocessing
import threading
import time
from multiprocessing import shared_memory

import cv2
import numpy as np
import pytest

from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.config.image_resolution import ImageResolution
from skellycam.core.ipc.frame_ring import FrameRingReader, FrameRingWriter, ReadResult
from skellycam.core.recorders.videos.fourcc_codec_helpers import PYAV_H264_FOURCC
from skellycam.core.recorders.videos.video_recorder import VideoRecorder
from skellycam.tests.capture.capture_session import quiet_logging
from skellycam.tests.reference_recordings.datasets import TEST, acquire

REPLAY_FPS = 60
LAST_FRAME = TEST.frames - 1


async def wait_until(predicate, problems, description, timeout=30):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert not problems, problems
        assert time.monotonic() < deadline, f"Timed out: {description}"
        await asyncio.sleep(0.005)


class PacedFileCapture:
    """A file-backed capture with the calls of the OpenCV source. Grab k waits until k / 60 s after
    the first grab, on a fixed grid, so that the warm-up rate is 60 fps."""

    def __init__(self, path):
        self.capture = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG)
        self.start_ns = None
        self.grabs = 0

    def isOpened(self):
        return self.capture.isOpened()

    def get(self, prop_id):
        return float(REPLAY_FPS) if prop_id == cv2.CAP_PROP_FPS else self.capture.get(prop_id)

    def set(self, prop_id, value):
        return self.capture.set(prop_id, value)

    def grab(self):
        now = time.perf_counter_ns()
        self.start_ns = now if self.start_ns is None else self.start_ns
        wake = self.start_ns + self.grabs * 1_000_000_000 // REPLAY_FPS
        if wake > now:
            time.sleep((wake - now) / 1e9)
        ok = self.capture.grab()
        self.grabs += ok
        return ok

    def retrieve(self, image=None):
        return self.capture.retrieve()

    def release(self):
        self.capture.release()


class Replay:
    """The three reference videos as three cameras of one group. `received` holds the source frame
    number of each ring frame of each camera; `recorded` holds the (frame number, arrival_ns) of each
    frame that the old recorder got. Each spy puts what is wrong in `problems`, because the loop
    catches an exception of a ring write."""

    def __init__(self, monkeypatch, paths):
        import skellycam.core.camera.capture.camera_loop as loop_module
        import skellycam.core.camera.capture.opencv_source as opencv_source

        quiet_logging(monkeypatch)
        self.paths = {str(index): path for index, path in enumerate(paths)}
        self.configs = {camera_id: CameraConfig(
            camera_id=camera_id, camera_index=int(camera_id), resolution=ImageResolution(width=720, height=1280),
            framerate=float(REPLAY_FPS), exposure_mode="MANUAL", exposure=-7, writer_fourcc=PYAV_H264_FOURCC)
            for camera_id in self.paths}
        self.group = None
        self.captures = {}
        self.received = {camera_id: [] for camera_id in self.paths}
        self.arrivals = {camera_id: {} for camera_id in self.paths}  # arrival_ns -> source frame number
        self.recorded = {camera_id: [] for camera_id in self.paths}
        self.problems = []
        self.ring_names = set()
        self._readers = {}
        self._baselines = {camera_id: [cv2.VideoCapture(str(path), cv2.CAP_FFMPEG), -1, None]
                           for camera_id, path in self.paths.items()}
        self._lock = threading.Lock()
        write, record_frame, handle = FrameRingWriter.write, VideoRecorder.record_frame, loop_module.handle_video_recording
        replay = self

        def spy_write(writer, payload, **kwargs):
            write(writer, payload, **kwargs)
            if payload is not None and not isinstance(payload, np.ndarray):
                replay._check(writer.name, payload, kwargs)

        def spy_handle(**kwargs):
            stamps = kwargs["frame_rec_array"].frame_metadata.timestamps
            if not (0 < stamps.pre_frame_grab_ns[0] <= stamps.post_frame_grab_ns[0] <= stamps.pre_frame_retrieve_ns[0]
                    <= stamps.post_frame_retrieve_ns[0] <= stamps.pre_copy_to_camera_shm_ns[0]):
                replay.problems.append("capture stamps out of order")
            return handle(**kwargs)

        def spy_record_frame(recorder, frame):
            replay.recorded[recorder.camera_id].append((int(frame.frame_metadata.frame_number[0]),
                                                        int(frame.frame_metadata.timestamps.post_frame_grab_ns[0])))
            return record_frame(recorder, frame)

        monkeypatch.setattr(opencv_source, "create_cv2_video_capture", self._open)
        monkeypatch.setattr(FrameRingWriter, "write", spy_write)
        monkeypatch.setattr(loop_module, "handle_video_recording", spy_handle)
        monkeypatch.setattr(VideoRecorder, "record_frame", spy_record_frame)

    def _open(self, config):
        capture = PacedFileCapture(self.paths[config.camera_id])
        self.captures[config.camera_id] = capture
        return capture, config

    def _check(self, name, payload, fields):
        camera_id = next(cid for cid, info in list(self.group.ring_infos.items()) if info.jpeg_ring_name == name)
        sfn = fields["source_frame_number"]
        if name not in self._readers:
            self.ring_names.add(name)
            self._readers[name] = FrameRingReader.attach(name)
        read = self._readers[name].read(fields["frame_number"])
        if read.result is ReadResult.CLOSED:
            return  # the close of the group closes the rings before it stops the loops
        if read.result is not ReadResult.OK or read.payload != payload:
            self.problems.append(f"camera {camera_id}: ring frame {fields['frame_number']} reads {read.result}")
        baseline = self._baselines[camera_id]
        while baseline[1] < sfn:
            ok, baseline[2] = baseline[0].read()
            baseline[1] += 1
            if not ok:
                self.problems.append(f"camera {camera_id}: the video has no frame {baseline[1]}")
                return
        actual = cv2.imdecode(np.frombuffer(payload, np.uint8), cv2.IMREAD_COLOR)
        if actual is None or actual.shape != baseline[2].shape or \
                float(np.abs(actual.astype(np.int16) - baseline[2].astype(np.int16)).mean()) >= 8:
            self.problems.append(f"camera {camera_id}: ring frame of video frame {sfn} differs")
        if camera_id == "2":
            time.sleep(0.003)  # unequal work per camera exercises the gate
        statuses = self.group.cameras.orchestrator.camera_statuses
        with self._lock:
            self.received[camera_id].append(sfn)
            self.arrivals[camera_id][fields["arrival_ns"]] = sfn
            if fields["frame_number"] != len(self.received[camera_id]) - 1:
                self.problems.append(f"camera {camera_id}: ring frame number {fields['frame_number']} is not the next")
            counts = [len(frames) for frames in self.received.values()]
            # a camera at its last frame holds the others at the gate until it is dead (9.5)
            if all(status.state == "ready" for status in list(statuses.values())) and max(counts) - min(counts) > 1:
                self.problems.append(f"ring frame counts {counts} differ by more than 1")

    def fewest(self):
        return min(len(frames) for frames in self.received.values())

    def recorded_sfns(self, camera_id, first=0, last=None):
        """The source frame numbers of the recorded frames with a frame number in [first, last)."""
        return [self.arrivals[camera_id][arrival] for number, arrival in self.recorded[camera_id]
                if number >= first and (last is None or number < last)]

    def positions(self):
        return [(len(self.received[camera_id]), capture.capture.get(cv2.CAP_PROP_POS_FRAMES))
                for camera_id, capture in sorted(self.captures.items())]

    @contextlib.asynccontextmanager
    async def running(self):
        """Start the group; on exit, close it and check the clean-up, also after a failure."""
        from skellycam.core.camera.capture.opencv_source import OpenCVSource
        from skellycam.core.camera_group.camera_group import CameraGroup
        from skellycam.core.ipc.process_management.managed_worker import WorkerMode
        from skellycam.core.ipc.process_management.worker_registry import WorkerRegistry

        kill = multiprocessing.Value("b", False)
        registry = WorkerRegistry(global_kill_flag=kill, worker_mode=WorkerMode.THREAD)
        self.group = CameraGroup.create(camera_configs=self.configs, heartbeat_timestamp=registry.heartbeat_timestamp,
                                        global_kill_flag=kill, worker_registry=registry, source_factory=OpenCVSource)
        try:
            failures = await asyncio.wait_for(self.group.start(), 30)
            assert not failures, failures
            yield self.group
        finally:
            try:
                await asyncio.wait_for(self.group.close(), 60)
            finally:
                registry.shutdown_all()
                for reader in self._readers.values():
                    reader.close()
                for baseline in self._baselines.values():
                    baseline[0].release()
        assert not registry.alive_workers, "a camera worker survived the close"
        assert not kill.value
        assert not self.problems, self.problems
        assert set(self.captures) == set(self.paths)
        assert all(not capture.isOpened() for capture in self.captures.values()), "a capture was not released"
        assert all(status.closed.value for status in self.group.cameras.orchestrator.camera_statuses.values())
        assert len(self.ring_names) == 3
        for name in self.ring_names:
            try:
                leaked = shared_memory.SharedMemory(name=name)
            except FileNotFoundError:
                continue
            leaked.close()
            pytest.fail(f"Shared-memory allocation leaked: {name}")


@pytest.mark.real_data
async def test_concurrent_replay_pause_and_group_shutdown(monkeypatch):
    """Each frame of each video after the warm-up reaches the ring in order and matches the video;
    the ring frame counts stay within one frame; while the group is paused, neither the video cursors
    nor the rings advance; at the close, each capture is released and no ring is left."""
    replay = Replay(monkeypatch, acquire(TEST))
    async with replay.running() as group:
        await wait_until(lambda: replay.fewest() >= 20, replay.problems, "initial frames")
        await asyncio.wait_for(group.cameras.pause(await_paused=True), timeout=5)
        assert group.cameras.orchestrator.all_cameras_paused
        before = replay.positions()
        await asyncio.sleep(0.05)
        assert replay.positions() == before
        await asyncio.wait_for(group.cameras.unpause(await_unpaused=True), timeout=5)
        await wait_until(lambda: replay.fewest() >= 60, replay.problems, "resumed frames")
        await wait_until(lambda: all(frames[-1] == LAST_FRAME for frames in replay.received.values()),
                         replay.problems, "complete replay")
    for frames in replay.received.values():
        assert frames == list(range(frames[0], LAST_FRAME + 1)), "a video frame is missing from the ring"
