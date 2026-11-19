"""T-REC-06, 19, 20, 29, 32, 35, 36: the queue, the writer thread, the fsync and the layout wait.

specs/recorder.md, sections 4.3, 5.1, 5.2, 5.5, 5.6 and 6.4. A writer thread is "held" with the fake
disk: its next MKV write blocks until the test releases it.
"""

import logging
import shutil
import time
import tracemalloc
from pathlib import Path

import psutil
import pytest

from skellycam.tests.take_recorder import jpeg_tools, sidecar_check
from skellycam.tests.take_recorder.rec_api import (
    DAMAGED_BYTES, T0, Frames, Run, queue_size, rec, recorder_frame, ring_flags, run_in_thread, take_camera)


def wait_rows(path, count, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists() and len(sidecar_check.read(path).rows) >= count:
            return True
        time.sleep(0.005)
    return False


def recorder_log_records(caplog, level):
    return [r for r in caplog.records if r.name.startswith("skellycam.core.take_recorder") and r.levelno == level]


def test_t_rec_06_the_queue_holds_the_frames_given_with_no_copy(tmp_path, runs, disk):
    """T-REC-06 [ring 5.7, R10]: 1,000 frames to a writer whose thread is held, then released. Each
    queue item holds the same object as the frame given (`is`); `give` makes no allocation of the
    payload size (`tracemalloc`)."""
    frames = Frames(640, 480)
    run = Run(tmp_path / "take", [take_camera("0a1b"), take_camera("ff00", os_index=1)], queue_seconds=40.0,
              frames=lambda k: frames(k % 20))
    runs.append(run)
    writer = run.writers["0a1b"]
    rule = disk.hold(".mkv")
    smallest = min(len(frames(k)) for k in range(20))  # also fills the cache before the snapshot
    tracemalloc.start(30)
    try:
        before = tracemalloc.take_snapshot()
        given = [run.give("0a1b", k) for k in range(1000)]
        after = tracemalloc.take_snapshot()
    finally:
        tracemalloc.stop()
    assert disk.wait_holding(rule, 10.0), "the writer thread must be held in a write"
    items = list(writer.queue.queue)
    assert len(items) >= 990
    for item, frame in zip(items, given[-len(items):]):
        assert item is frame or getattr(item, "payload", None) is frame.payload
    package = str(Path(rec().__file__).parent)

    def in_give(traceback):
        """An allocation of the recorder on the calling thread: the stack holds `Run.give` and the package.
        The writer thread (the mux copies the packet for PyAV) is not `give`."""
        return any(f.filename.startswith(package) for f in traceback) and any(f.filename.endswith("rec_api.py") for f in traceback)

    grown = [s for s in after.compare_to(before, "traceback") if in_give(s.traceback)]
    large = [t for t in after.traces if t.size >= smallest and in_give(t.traceback)]
    assert large == [], "an allocation of the payload size in give"
    assert sum(s.size_diff for s in grown) < 1000 * smallest // 10
    rule.release.set()
    for k in range(1000):
        run.give("ff00", k)
    run.finish(1000)
    assert len(sidecar_check.read(run.csv("0a1b")).rows) == 1000


def test_t_rec_19_full_queue_give_waits_with_no_spin(tmp_path, runs, disk):
    """T-REC-19 [P §6, ring 8.10]: the writer thread is held; frames fill the queue; one more `give`
    from a second thread waits; while it waits, the process uses under 2 % of one core; it returns
    when space comes; each frame is in the CSV; the counts of 5.2 are right."""
    run = Run(tmp_path / "take", [take_camera("0a1b"), take_camera("ff00", os_index=1)])
    runs.append(run)
    writer = run.writers["0a1b"]
    size = run.take.camera_spec("0a1b").queue_size
    rule = disk.hold(".mkv")
    k = 0
    while not writer.queue.full():
        assert k < size + 10, "the queue does not fill"
        run.give("0a1b", k)
        k += 1
        if k == 3:
            assert disk.wait_holding(rule, 10.0)
    wait_started = time.monotonic()
    thread, box = run_in_thread(run.give, "0a1b", k)
    time.sleep(0.2)
    process = psutil.Process()
    cpu_before, wall_before = process.cpu_times(), time.monotonic()
    time.sleep(1.0)
    cpu_after, wall_after = process.cpu_times(), time.monotonic()
    assert thread.is_alive(), "the extra give must wait while the queue is full"
    used = (cpu_after.user + cpu_after.system - cpu_before.user - cpu_before.system) / (wall_after - wall_before)
    assert used < 0.02, f"the process used {used:.1%} of one core while give waited"
    released = time.monotonic()
    rule.release.set()
    thread.join(10.0)
    assert not thread.is_alive() and "error" not in box
    total = k + 1
    for j in range(total):
        run.give("ff00", j)
    run.finish(total)
    result = run.results["0a1b"]
    assert len(sidecar_check.read(run.csv("0a1b")).rows) == total
    assert result.give_wait_count == 1
    assert 1000.0 <= result.give_wait_ms_max <= (released - wait_started + 0.5) * 1000
    assert result.queue_high_water == size


@pytest.mark.parametrize(("rate", "size"), [((30, 1), 90), ((30000, 1001), 90), ((60, 1), 180)],
                         ids=["30_1", "30000_1001", "60_1"])
def test_t_rec_20_queue_size(tmp_path, runs, rate, size):
    """T-REC-20 [agent 4]: the queue size is ⌈3.0 × num / den⌉ items: 90, 90 and 180."""
    assert queue_size(*rate) == size
    run = Run(tmp_path / "take", [take_camera("0a1b", rate=rate), take_camera("ff00", rate=rate, os_index=1)])
    runs.append(run)
    assert run.take.camera_spec("0a1b").queue_size == size
    assert run.writers["0a1b"].queue.maxsize == size
    run.give("0a1b", 0)
    run.give("ff00", 0)
    run.finish(1)


class VirtualClock:
    """The clock of the writer thread (ADR-QEQ8): ns, set by the test."""

    def __init__(self):
        self.ns = 0

    def __call__(self):
        return self.ns


def test_t_rec_29_fsync_once_a_second_on_the_writer_thread(tmp_path, runs, disk):
    """T-REC-29 [SFF-788, agent 9]: with an injected clock of the writer thread, one fsync of the MKV
    and one of the CSV for each second with a row, MKV first, on the writer thread only; one fsync of
    each at `end`."""
    clock = VirtualClock()
    run = Run(tmp_path / "take", [take_camera("0a1b"), take_camera("ff00", os_index=1)], writer_clock=clock)
    runs.append(run)
    for k in range(50):
        clock.ns = k * 100_000_000  # 10 rows for each virtual second
        run.give("0a1b", k)
        run.give("ff00", k)
        assert wait_rows(run.csv("0a1b"), k) and wait_rows(run.csv("ff00"), k)
    live = disk.events_of("fsync")
    run.finish(50)
    final = disk.events_of("fsync")
    for camera_id in ("0a1b", "ff00"):
        mkv = run.mkv(camera_id).resolve().relative_to(disk.root).as_posix()
        csv = run.csv(camera_id).resolve().relative_to(disk.root).as_posix()
        mine = [e for e in live if e[3] in (mkv, csv)]
        assert all(e[1] == f"take-writer-{camera_id}" for e in mine), "fsync only on the writer thread"
        assert len(mine) % 2 == 0 and len(mine) // 2 in (4, 5), [e[3] for e in mine]
        assert [e[3] for e in mine] == [mkv, csv] * (len(mine) // 2), "the MKV, then the CSV"
        at_end = [e for e in final[len(live):] if e[3] in (mkv, csv)]
        assert [e[3] for e in at_end] == [mkv, csv]
        assert all(e[1] == f"take-writer-{camera_id}" for e in at_end)


def test_t_rec_32_calls_out_of_order_raise(tmp_path, runs):
    """T-REC-32 (4.3): `give` and `give_missing` before `start` and after `end`, and a second `end`,
    each raise `RuntimeError`. A writer that is constructed but not started is the "before start"
    case (ADR-QEQ8)."""
    module = rec()
    run = Run(tmp_path / "take", [take_camera("0a1b"), take_camera("ff00", os_index=1)], start_writers=False)
    runs.append(run)
    unstarted = module.CameraTakeWriter(run.take.camera_spec("0a1b"))
    frame = run.frames(0)
    with pytest.raises(RuntimeError):
        unstarted.give(recorder_frame(frame, 0, arrival_ns=T0 + 1))
    with pytest.raises(RuntimeError):
        unstarted.give_missing()
    run.start_writer("0a1b")
    run.start_writer("ff00")
    run.give("0a1b", 0)
    run.give("ff00", 0)
    run.end(1)
    writer = run.writers["0a1b"]
    with pytest.raises(RuntimeError):
        writer.give(recorder_frame(frame, 1, arrival_ns=T0 + 2))
    with pytest.raises(RuntimeError):
        writer.give_missing()
    with pytest.raises(RuntimeError):
        writer.end(1)
    run.take.finish([run.results["0a1b"], run.results["ff00"]], frame_count=1)


def test_t_rec_35_layout_from_the_spec_rows_written_live(tmp_path, runs):
    """T-REC-35 case 1 [M2, M7, agent 22]: the spec has a layout; frames 0 to 2 are damaged. The rows
    are written live with the spec's placeholder, before frame 3 is given.

    The spec text says "rows 0 to 2". By 6.3 the muxer gives block k to the file only when block k+1
    comes, so row 2 waits for frame 3. The test checks rows 0 and 1 (see the report of ADR-QEQ8)."""
    frame_flag, _ = ring_flags()
    run = Run(tmp_path / "take", [take_camera("0a1b", layout="420"), take_camera("ff00", layout="420", os_index=1)],
              frames=Frames(640, 480, "420"))
    runs.append(run)
    for k in range(3):
        run.give("0a1b", k, payload=DAMAGED_BYTES, flags=frame_flag.CAPTURE_ERROR)
        run.give("ff00", k)
    assert wait_rows(run.csv("0a1b"), 2, timeout=5.0), "rows 0 and 1 are on disk before frame 3"
    sidecar = sidecar_check.read(run.csv("0a1b"))
    data = run.mkv("0a1b").read_bytes()
    for row in sidecar.rows[:2]:
        assert row.missing
        sof = jpeg_tools.parse_sof(data[row.byte_offset:row.byte_offset + row.byte_size])
        assert sof.factors == jpeg_tools.LAYOUTS["420"] and (sof.width, sof.height) == (640, 480)
    for k in range(3, 6):
        run.give("0a1b", k)
        run.give("ff00", k)
    run.finish(6)


def test_t_rec_35_no_layout_rows_wait_for_the_first_good_frame(tmp_path, runs):
    """T-REC-35 case 2 [M2, M7, agent 22]: `layout` `None`, damaged frames 0 to 2, then good frames
    (4:2:0). Rows 0 to 2 wait; then their placeholders get the layout of frame 3."""
    frame_flag, _ = ring_flags()
    run = Run(tmp_path / "take", [take_camera("0a1b", layout=None), take_camera("ff00", layout="420", os_index=1)],
              frames=Frames(640, 480, "420"))
    runs.append(run)
    for k in range(3):
        run.give("0a1b", k, payload=DAMAGED_BYTES, flags=frame_flag.CAPTURE_ERROR)
        run.give("ff00", k)
    time.sleep(0.5)
    assert len(sidecar_check.read(run.csv("0a1b")).rows) == 0, "rows 0 to 2 wait for the first good frame"
    for k in range(3, 8):
        run.give("0a1b", k)
        run.give("ff00", k)
    run.finish(8)
    sidecar = sidecar_check.read(run.csv("0a1b"))
    data = run.mkv("0a1b").read_bytes()
    assert len(sidecar.rows) == 8
    for row in sidecar.rows[:3]:
        assert row.missing
        sof = jpeg_tools.parse_sof(data[row.byte_offset:row.byte_offset + row.byte_size])
        assert sof.factors == jpeg_tools.LAYOUTS["420"] and (sof.width, sof.height) == (640, 480)
    assert [data[r.byte_offset:r.byte_offset + r.byte_size] for r in sidecar.rows[3:]] == [run.frames(k) for k in range(3, 8)]


def test_t_rec_35_no_good_frame_in_the_queue_time_gives_a_4_2_2_placeholder(tmp_path, runs, caplog):
    """T-REC-35 case 3 [M2, agent 22]: `layout` `None` and only damaged frames for longer than the
    queue size. After the queue size of rows, the held rows are written with a 4:2:2 placeholder of
    the mode size, and one warning is logged."""
    frame_flag, _ = ring_flags()
    width, height = 320, 240
    cameras = [take_camera("0a1b", width=width, height=height, layout=None),
               take_camera("ff00", width=width, height=height, os_index=1)]
    run = Run(tmp_path / "take", cameras, queue_seconds=1.0, frames=Frames(width, height))
    runs.append(run)
    size = run.take.camera_spec("0a1b").queue_size
    assert size == 30
    with caplog.at_level(logging.WARNING):
        for k in range(size + 10):
            run.give("0a1b", k, payload=DAMAGED_BYTES, flags=frame_flag.CAPTURE_ERROR)
            run.give("ff00", k)
        assert wait_rows(run.csv("0a1b"), size - 1, timeout=10.0), "the held rows are written after the queue size"
        run.finish(size + 10)
    sidecar = sidecar_check.read(run.csv("0a1b"))
    data = run.mkv("0a1b").read_bytes()
    assert len(sidecar.rows) == size + 10 and all(r.missing for r in sidecar.rows)
    sof = jpeg_tools.parse_sof(data[sidecar.rows[0].byte_offset:sidecar.rows[0].byte_offset + sidecar.rows[0].byte_size])
    assert sof.factors == jpeg_tools.LAYOUTS["422"] and (sof.width, sof.height) == (width, height)
    assert len(recorder_log_records(caplog, logging.WARNING)) == 1


@pytest.mark.recorder_slow
def test_t_rec_36_1080p60_frames_of_600_kb_for_30_s(tmp_path, runs):
    """T-REC-36 (a sanity check, not a measurement): 1080p, frames of 600 kB at 60/1 for 30 s, in one
    process. No `give` wait on a free disk; every frame is in the CSV. The frames are synthetic JPEGs
    padded after EOI to 600 kB (SFF-738). The test deletes its 2 GB of media at the end."""
    base = Frames(1920, 1080)
    payloads = [jpeg_tools.padded(base(k), 600_000) for k in range(30)]
    cameras = [take_camera("0a1b", rate=(60, 1), width=1920, height=1080),
               take_camera("ff00", rate=(60, 1), width=1920, height=1080, os_index=1)]
    run = Run(tmp_path / "take", cameras, frames=lambda k: payloads[k % 30])
    runs.append(run)
    count = 60 * 30
    start = time.perf_counter()
    try:
        for k in range(count):
            delay = start + k / 60 - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            run.give("0a1b", k)
            run.give("ff00", k)
        run.finish(count)
        for camera_id in ("0a1b", "ff00"):
            assert run.results[camera_id].give_wait_count == 0
            assert len(sidecar_check.read(run.csv(camera_id)).rows) == count
    finally:
        shutil.rmtree(run.folder, ignore_errors=True)
