"""Behaviour outside the ring package that step 2a changes: T-RING-23, 31, 32, 33
(specs/frame-ring.md, sections 2, 5.3, 8.10 and 12).

These tests use the production OpenCV loop and `CameraGroup` with fake cameras
(ring_session.py). No camera and no camera frame is used.
"""

import importlib.util
import multiprocessing
import re
import threading
import time
from pathlib import Path

import numpy as np
import psutil
import pytest

from skellycam.tests.frame_ring import ring_children
from skellycam.tests.frame_ring.ring_session import (
    FakeCapture,
    decode,
    fake_configs,
    fake_session,
    patch_fakes,
    wait_until,
)
from skellycam.tests.frame_ring.ring_spec import (
    IDLE_SECONDS,
    TIMING_SECONDS,
    WAIT_TIMEOUT_S,
    ring,
    synthetic_payload,
    write_kwargs,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _run_loop_in_thread(monkeypatch, fr, writer, frames_wanted, fail_at=None):
    """Run the production `run_opencv_camera_loop` with a fake capture source. Record the order
    of the inline recorder call and the ring write for each frame."""
    import skellycam.core.camera.opencv.opencv_camera_loop as loop_module
    from skellycam.core.camera.opencv.opencv_helpers.create_initial_frame_recarray import (
        create_initial_frame_rec_array,
    )
    from skellycam.core.camera_group.camera_group_ipc import CameraGroupIPC
    from skellycam.core.camera_group.camera_orchestrator import CameraOrchestrator
    from skellycam.core.camera_group.camera_status import CameraStatus
    from skellycam.core.ipc.pubsub.pubsub_manager import PubSubTopicManager

    patch_fakes(monkeypatch)
    events = []
    config = fake_configs(1)["0"]
    status = CameraStatus()
    status.connected.value = True
    orchestrator = CameraOrchestrator.from_statuses({config.camera_id: status})
    updates, recording = multiprocessing.Queue(), multiprocessing.Queue()
    ipc = CameraGroupIPC(
        group_id="ring-order", pubsub=PubSubTopicManager(topics={}),
        extracted_config_subscription=updates, recording_finished_subscription=recording,
        global_kill_flag=multiprocessing.Value("b", False),
        heartbeat_timestamp=multiprocessing.Value("d", time.perf_counter()))

    def recorder(**kwargs):
        events.append(("record", int(kwargs["frame_rec_array"].frame_metadata.frame_number[0])))
        return kwargs["video_recorder"]

    real_write = fr.FrameRingWriter.write

    def spy_write(self, payload, **kwargs):
        events.append(("write", kwargs["frame_number"], payload))
        if sum(event[0] == "write" for event in events) >= frames_wanted:
            status.should_close.value = True
        if kwargs["frame_number"] == fail_at:
            raise RuntimeError("injected ring write failure")
        return real_write(self, payload, **kwargs)

    monkeypatch.setattr(loop_module, "handle_video_recording", recorder)
    monkeypatch.setattr(fr.FrameRingWriter, "write", spy_write)
    errors = []

    def run():
        try:
            loop_module.run_opencv_camera_loop(
                ring_writer=writer, config=config, cv2_video_capture=FakeCapture(640, 480, 60.0),
                frame_rec_array=create_initial_frame_rec_array(config=config, ipc=ipc), ipc=ipc,
                orchestrator=orchestrator, self_status=status,
                update_camera_settings_subscription=updates, recording_info_subscription=recording)
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout=WAIT_TIMEOUT_S)
    status.should_close.value = True
    ipc.should_continue = False
    thread.join(timeout=WAIT_TIMEOUT_S)
    assert not thread.is_alive(), "the camera loop did not stop"
    return events, errors


def test_t_ring_23_recorder_first_in_the_opencv_loop(monkeypatch, cleanup):
    """T-RING-23, sections 2.3 and 5.3 [A3, A6]: with an instrumented recorder and ring, the
    recorder call precedes every ring write. The loop encodes each frame with `cv2.imencode` and
    writes the JPEG."""
    fr = ring()
    creator = cleanup.own(fr.FrameRingCreator.create(
        camera_id="0", camera_index=0, pixel_format=fr.PixelFormat.JPEG, width=640, height=480,
        fps_num=60, fps_den=1))
    writer = cleanup.handle(fr.FrameRingWriter.attach(creator.name))
    events, errors = _run_loop_in_thread(monkeypatch, fr, writer, frames_wanted=10)
    assert not errors, errors
    kinds = [event[0] for event in events]
    assert kinds.count("write") >= 10
    assert kinds[: 2 * kinds.count("write")] == ["record", "write"] * kinds.count("write")
    writes = [event for event in events if event[0] == "write"]
    assert [event[1] for event in writes] == list(range(len(writes)))  # A17: from 0, +1
    for _, _, payload in writes:
        assert type(payload) is bytes and payload[:2] == b"\xff\xd8"
        assert decode(payload).shape == (480, 640, 3)


def test_t_ring_23_failing_ring_write_leaves_the_recorder_unaffected(monkeypatch, cleanup):
    """T-RING-23, section 5.3: a failing ring write leaves the recorder path unaffected: the
    recorder already has the frame whose ring write fails."""
    fr = ring()
    creator = cleanup.own(fr.FrameRingCreator.create(
        camera_id="0", camera_index=0, pixel_format=fr.PixelFormat.JPEG, width=640, height=480,
        fps_num=60, fps_den=1))
    writer = cleanup.handle(fr.FrameRingWriter.attach(creator.name))
    events, _ = _run_loop_in_thread(monkeypatch, fr, writer, frames_wanted=10, fail_at=3)
    kinds = [event[0] for event in events]
    failing = next(i for i, event in enumerate(events) if event[0] == "write" and event[1] == 3)
    assert kinds[failing - 1] == "record"
    assert kinds.count("record") >= 4


@pytest.mark.ring_slow
def test_t_ring_23_write_p99_with_four_readers(cleanup, spawn, procs):
    """T-RING-23, sections 5.3 and 11.3 [A48]: 4 reader processes read the newest frame without a
    pause. The JPEG write p99 stays within the provisional M2 target (0.5 ms at 1080p).

    The writer writes 1080p-size payloads (607,032 bytes, the largest measured frame) at about
    200 frames/s for TIMING_SECONDS (2 s; 10 s with SKELLYCAM_RING_FULL=1).
    """
    fr = ring()
    creator = cleanup.own(fr.FrameRingCreator.create(
        camera_id="p99", camera_index=0, pixel_format=fr.PixelFormat.JPEG, width=1920,
        height=1080, fps_num=60, fps_den=1))
    writer = cleanup.handle(fr.FrameRingWriter.attach(creator.name))
    payloads = [synthetic_payload(k, 607_032) for k in range(8)]
    writer.write(payloads[0], **write_kwargs(0))
    stop = spawn.Event()
    for _ in range(4):
        process = spawn.Process(target=ring_children.hammer_reader, args=(creator.name, stop), daemon=True)
        procs.append(process)
        process.start()
    time.sleep(3)  # let the readers attach and start
    durations = []
    k = 1
    end = time.monotonic() + TIMING_SECONDS
    try:
        while time.monotonic() < end:
            kwargs = write_kwargs(k)
            t0 = time.perf_counter_ns()
            writer.write(payloads[k % 8], **kwargs)
            durations.append(time.perf_counter_ns() - t0)
            k += 1
            time.sleep(0.005)
    finally:
        stop.set()
    assert all(process.is_alive() for process in procs), "a reader died"
    p99_ms = np.percentile(durations, 99) / 1e6
    assert p99_ms <= 0.5, f"JPEG write p99 {p99_ms:.3f} ms > 0.5 ms (M2 target)"


@pytest.mark.ring_slow
def test_t_ring_31_no_spinning_thread_when_idle(cleanup, spawn, procs):
    """T-RING-31, section 8.10 [A45]: a camera process with a fake capture source, paused for
    5 s. The process CPU is under 2 % of one core.

    The default pause is IDLE_SECONDS (2 s; 5 s with SKELLYCAM_RING_FULL=1). A helper thread in
    the child wakes every 50 ms to copy the flags; that cost is part of the measured CPU.
    """
    fr = ring()
    creator = cleanup.own(fr.FrameRingCreator.create(
        camera_id="0", camera_index=0, pixel_format=fr.PixelFormat.JPEG, width=640, height=480,
        fps_num=30, fps_den=1))
    pause, paused, close = spawn.Value("b", 0), spawn.Value("b", 0), spawn.Value("b", 0)
    frames = spawn.Value("q", 0)
    process = spawn.Process(target=ring_children.idle_camera_process,
                            args=(creator.name, pause, paused, close, frames), daemon=True)
    procs.append(process)
    process.start()
    try:
        _poll(lambda: frames.value > 10, "frames from the fake camera")
        pause.value = 1
        _poll(lambda: paused.value, "camera paused")
        time.sleep(0.5)
        cpu = psutil.Process(process.pid)
        before, t0 = cpu.cpu_times(), time.perf_counter()
        time.sleep(IDLE_SECONDS)
        after, t1 = cpu.cpu_times(), time.perf_counter()
    finally:
        close.value = 1
    used = (after.user - before.user + after.system - before.system) / (t1 - t0)
    process.join(timeout=WAIT_TIMEOUT_S)
    assert used < 0.02, f"paused camera process used {used:.1%} of one core"


def _poll(predicate, what):
    deadline = time.monotonic() + WAIT_TIMEOUT_S
    while not predicate():
        assert time.monotonic() < deadline, f"timed out: {what}"
        time.sleep(0.01)


DELETED_MODULES = [
    "skellycam.core.ipc.shared_memory.shared_memory_element",
    "skellycam.core.ipc.shared_memory.shared_memory_number",
    "skellycam.core.ipc.shared_memory.ring_buffer_shared_memory",
    "skellycam.core.ipc.shared_memory.camera_shared_memory_ring_buffer",
    "skellycam.core.ipc.shared_memory.camera_group_shared_memory",
    "skellycam.system.diagnostics.check_shm_speed",
]
DELETED_NAMES = [
    "SharedMemoryElement", "SharedMemoryElementDTO", "SharedMemoryNumber", "SharedMemoryRingBuffer",
    "SharedMemoryRingBufferDTO", "CameraSharedMemoryRingBuffer", "CameraGroupSharedMemory",
    "CameraGroupSharedMemoryDTO", "camera_group_shm_dto", "get_shm_dto_by_camera_id",
    "create_frontend_payload", "encode_image_payload", "ImagePayloadFrame", "ImagePayloadRequest",
    "JPEG_ENCODING_PARAMETERS", "get_latest_frames", "get_latest_frontend_payload",
    "get_frontend_payload_by_frame_number", "check_shm_speed",
]


def _module_exists(name):
    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError:
        return False


def test_t_ring_32_old_code_gone():
    """T-RING-32, section 2.1 [A1]: the deleted modules do not import, and the deleted names are
    not in the package or in `architecture.mdx`. `find_spec` finds a module without running it.

    The frame ring tests themselves are not searched. The decision log and `specs/` are history
    documents and are not searched.
    """
    left_modules = [name for name in DELETED_MODULES if _module_exists(name)]
    pattern = re.compile(r"\b(" + "|".join(DELETED_NAMES) + r")\b")
    own_folder = Path(__file__).resolve().parent
    files = [path for path in (REPO_ROOT / "skellycam").rglob("*.py") if own_folder not in path.parents]
    files.append(REPO_ROOT / "skellycam-docs" / "docs" / "technical" / "architecture.mdx")
    hits = []
    for path in files:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = pattern.search(line)
            if match:
                hits.append(f"{path.relative_to(REPO_ROOT).as_posix()}:{number}: {match.group(1)}")
    assert not left_modules, f"deleted modules still import: {left_modules}"
    assert not hits, f"{len(hits)} deleted names left, for example: {hits[:10]}"


async def test_t_ring_33_interim_relay_sends_the_ring_jpeg(monkeypatch, cleanup):
    """T-RING-33, section 2.3 [A4]: fake cameras; capture one websocket message. The JPEG bytes
    in the message equal the bytes of the ring, at one frame number for all cameras.

    The message is the payload that `CameraGroupManager.get_latest_frontend_payloads` gives the
    websocket relay; its wire format is the format of today (`FRONTEND_*_DTYPE`).
    """
    fr = ring()
    from skellycam.core.camera_group.camera_group_manager import CameraGroupManager
    from skellycam.core.ipc.process_management.managed_worker import WorkerMode
    from skellycam.core.ipc.process_management.worker_registry import WorkerRegistry
    from skellycam.core.types.frontend_payload_bytearray import (
        FRONTEND_FRAME_HEADER_DTYPE,
        FRONTEND_PAYLOAD_HEADER_FOOTER_DTYPE,
    )

    async with fake_session(monkeypatch, fake_configs(2)) as group:
        kill = multiprocessing.Value("b", False)
        manager = CameraGroupManager(
            global_kill_flag=kill, camera_groups={group.id: group},
            worker_registry=WorkerRegistry(global_kill_flag=kill, worker_mode=WorkerMode.THREAD))
        readers = {}
        for camera_id, info in group.ring_infos.items():
            readers[info.camera_index] = cleanup.handle(fr.FrameRingReader.attach(info.jpeg_ring_name))
        messages = {}

        def message_ready():
            messages.update(manager.get_latest_frontend_payloads(if_newer_than={}))
            return group.id in messages

        await wait_until(message_ready, "a websocket message")
        frame_number, _, payload = messages[group.id]
        data = bytes(payload)
        offset = FRONTEND_PAYLOAD_HEADER_FOOTER_DTYPE.itemsize
        seen = set()
        for _ in range(2):
            header = np.frombuffer(data, dtype=FRONTEND_FRAME_HEADER_DTYPE, count=1, offset=offset)[0]
            offset += FRONTEND_FRAME_HEADER_DTYPE.itemsize
            length = int(header["jpeg_string_length"])
            jpeg = data[offset:offset + length]
            offset += length
            assert int(header["frame_number"]) == frame_number
            read = readers[int(header["camera_index"])].read(frame_number)
            assert read.result == fr.ReadResult.OK
            assert jpeg == read.payload, "the relay changed the ring JPEG"
            seen.add(int(header["camera_index"]))
        assert seen == {0, 1}
        for reader in readers.values():
            reader.close()
