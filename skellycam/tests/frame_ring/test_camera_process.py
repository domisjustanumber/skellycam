"""Behaviour outside the ring package that step 2a changes: T-RING-23, 32
(specs/frame-ring.md, sections 2, 5.3 and 12). T-RING-31 is retired; T-CAP-49 checks its rule on
the shared loop (ADR-PDD3 W8). The two parts of T-RING-23 in the camera loop are retired with the
phase 2 loop; T-CAP-08 checks them on the shared loop. T-RING-33 is deleted with the old group message in
step 4b; T-PRV-02 and T-PRV-26 keep its rule (specs/preview-4b.md 3.2).
"""

import importlib.util
import re
import time
from pathlib import Path

import numpy as np
import pytest

from skellycam.tests.frame_ring import ring_children
from skellycam.tests.pace import margin
from skellycam.tests.frame_ring.ring_spec import (
    TIMING_SECONDS,
    ring,
    synthetic_payload,
    write_kwargs,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _four_readers_run(cleanup, spawn, procs):
    """The run of T-RING-23: 4 reader processes read the newest frame without a pause, while the writer writes
    1080p-size payloads (607,032 bytes, the largest measured frame) at 60 frames/s for TIMING_SECONDS (2 s; 10 s with
    SKELLYCAM_RING_FULL=1). Gives whether each reader still runs and the JPEG write p99 in ms."""
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
    alive = all(process.is_alive() for process in procs)
    return alive, np.percentile(durations, 99) / 1e6


@pytest.mark.ring_slow
def test_t_ring_23_write_with_four_readers(cleanup, spawn, procs):
    """T-RING-23, sections 5.3 and 11.3 [A48]: 4 reader processes read the newest frame without a pause while the
    writer writes at 60 frames/s; no reader dies. The p99 target is in `test_t_ring_23_write_p99_with_four_readers`."""
    alive, _ = _four_readers_run(cleanup, spawn, procs)
    assert alive, "a reader died"


@pytest.mark.pace  # Q619: a p99 of real time; a percentile target is all tolerance, so the margin multiplies it (16.1)
@pytest.mark.ring_slow
def test_t_ring_23_write_p99_with_four_readers(cleanup, spawn, procs):
    """T-RING-23, the bound of time [A66]: the JPEG write p99 stays within the target of 1.0 ms (times the margin) at
    1080p with four readers, for a writer that is paced at 60 frames/s by a sleep."""
    _, p99_ms = _four_readers_run(cleanup, spawn, procs)
    assert p99_ms <= 1.0 * margin(), f"JPEG write p99 {p99_ms:.3f} ms > {margin():g} ms (target with four readers)"


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
