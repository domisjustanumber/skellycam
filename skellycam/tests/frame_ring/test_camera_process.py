"""Behaviour outside the ring package that step 2a changes: T-RING-23, 32, 33
(specs/frame-ring.md, sections 2, 5.3 and 12). T-RING-31 is retired; T-CAP-49 checks its rule on
the shared loop (ADR-PDD3 W8). The two parts of T-RING-23 in the camera loop are retired with the
phase 2 loop; T-CAP-08 checks them on the shared loop.

T-RING-33 uses `CameraGroup` with fake cameras (ring_session.py). No camera and no camera frame is
used.
"""

import importlib.util
import multiprocessing
import re
import time
from pathlib import Path

import numpy as np
import pytest

from skellycam.tests.frame_ring import ring_children
from skellycam.tests.frame_ring.ring_session import (
    fake_configs,
    fake_session,
    wait_until,
)
from skellycam.tests.frame_ring.ring_spec import (
    TIMING_SECONDS,
    ring,
    synthetic_payload,
    write_kwargs,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.ring_slow
def test_t_ring_23_write_p99_with_four_readers(cleanup, spawn, procs):
    """T-RING-23, sections 5.3 and 11.3 [A48]: 4 reader processes read the newest frame without a
    pause. The JPEG write p99 stays within the target of 1.0 ms at 1080p for a writer that is paced
    at 60 frames/s by a sleep [A66].

    The writer writes 1080p-size payloads (607,032 bytes, the largest measured frame) at 60
    frames/s for TIMING_SECONDS (2 s; 10 s with SKELLYCAM_RING_FULL=1).
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
            time.sleep(1 / 60)
    finally:
        stop.set()
    assert all(process.is_alive() for process in procs), "a reader died"
    p99_ms = np.percentile(durations, 99) / 1e6
    assert p99_ms <= 1.0, f"JPEG write p99 {p99_ms:.3f} ms > 1.0 ms (target with four readers, paced at 60 frames/s)"


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
            """A payload that holds both cameras at one frame number: the relay sends each camera that has a frame
            to show, also before the second camera has one."""
            got = manager.get_latest_frontend_payloads(if_newer_than={}).get(group.id)
            data = b"" if got is None else bytes(got[2])
            head = FRONTEND_PAYLOAD_HEADER_FOOTER_DTYPE.itemsize
            if not data or int(np.frombuffer(data, FRONTEND_PAYLOAD_HEADER_FOOTER_DTYPE, 1)[0]["number_of_cameras"]) != 2:
                return False
            first = np.frombuffer(data, FRONTEND_FRAME_HEADER_DTYPE, 1, head)[0]
            second_at = head + FRONTEND_FRAME_HEADER_DTYPE.itemsize + int(first["jpeg_string_length"])
            second = np.frombuffer(data, FRONTEND_FRAME_HEADER_DTYPE, 1, second_at)[0]
            if first["frame_number"] != got[0] or second["frame_number"] != got[0]:
                return False
            messages[group.id] = got
            return True

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
