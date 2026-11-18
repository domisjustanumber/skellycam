"""Frame ring lifecycle: T-RING-25 to T-RING-30 (specs/frame-ring.md, sections 7, 9 and 12).

T-RING-25 to 27 start a `CameraGroup` with fake cameras (ring_session.fake_session).
"""

import logging
import os
import re
import signal
import subprocess
import sys
import time
import warnings
import zlib

import pytest

from skellycam.tests.frame_ring import ring_children
from skellycam.tests.frame_ring.ring_session import decode, fake_configs, fake_session, wait_until
from skellycam.tests.frame_ring.ring_spec import (
    WAIT_TIMEOUT_S,
    new_ring,
    open_raw,
    parse_ring_header,
    ring,
    ring_exists,
    synthetic_payload,
    write_kwargs,
)

LINUX = sys.platform.startswith("linux")
MACOS = sys.platform == "darwin"


def _bytes_pattern(n):
    """The number of bytes, with or without thousands separators."""
    return rf"\b({n}|{n:,})\b"


def _wait_gone(name, timeout=WAIT_TIMEOUT_S):
    deadline = time.monotonic() + timeout
    while ring_exists(name):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.05)
    return True


async def _wait_ok(fr, reader):
    await wait_until(lambda: reader.read_newest().result == fr.ReadResult.OK, "first frame in the ring")
    return reader.read_newest()


async def test_t_ring_25_creation_and_names(monkeypatch, caplog, cleanup):
    """T-RING-25, sections 3.3, 7.1 to 7.3, 7.8 and 9 [A32 to A34, A38, A46, A47]: start a
    session with fake cameras. The total and per-ring sizes are logged; the names are in
    `CameraRingInfo`; a reader attaches by name alone; the header matches the config."""
    fr = ring()
    configs = fake_configs(2, 640, 480, 30.0)
    per_ring = 8192 + 30 * 311_296  # table 3.6 and section 3.8: 640x480, N = 30
    total = 2 * per_ring
    with caplog.at_level(logging.DEBUG):
        async with fake_session(monkeypatch, configs) as group:
            infos = group.ring_infos
            assert set(infos) == set(configs)
            for camera_id, info in infos.items():
                config = configs[camera_id]
                assert info.camera_id == camera_id and info.camera_index == config.camera_index
                assert info.bgr_ring_name is None
                assert re.fullmatch(rf"skc{os.getpid():x}_{config.camera_index}_J\d+", info.jpeg_ring_name)
                assert len(info.jpeg_ring_name) <= 30
                assert info.rotation_cw_deg == 0
                mode = info.mode
                assert (mode.width, mode.height) == (640, 480)
                assert mode.fps_num / mode.fps_den == pytest.approx(30.0)
                assert mode.format == config.capture_fourcc
                assert mode.uncompressed is False and mode.selectable is True
                reader = cleanup.handle(fr.FrameRingReader.attach(info.jpeg_ring_name))
                read = await _wait_ok(fr, reader)
                assert decode(read.payload).shape == (480, 640, 3)
                reader.close()
                header = parse_ring_header(cleanup.handle(open_raw(info.jpeg_ring_name)).buf)
                assert (header["width"], header["height"]) == (640, 480)
                assert header["fps_num"] / header["fps_den"] == pytest.approx(30.0)
                assert header["pixel_format"] == 1
                assert header["camera_index"] == config.camera_index
                assert header["camera_key"].rstrip(b"\0") == camera_id.encode()
                assert header["creator_pid"] == os.getpid()
                assert header["slot_count"] == 30 and header["history_ms"] == 1000
                assert header["total_size"] == per_ring
    log = " ".join(record.getMessage() for record in caplog.records)
    assert re.search(_bytes_pattern(total), log), "total shared memory not logged in bytes"
    assert f"{total / 2 ** 20:.1f} MiB" in log, "total shared memory not logged in MiB"
    assert re.search(_bytes_pattern(per_ring), log), "per-ring size not logged"


async def test_t_ring_26_recreation(monkeypatch, cleanup):
    """T-RING-26, sections 7.2, 7.4 and 7.5 [A17, A33, A35]: change the resolution of a fake
    camera. The ring gets a new name; the old ring has `closed = 1`; old readers get `CLOSED`;
    the old segment is gone after the unlink (Linux: no `/dev/shm` entry; Windows: an open by
    name fails)."""
    fr = ring()
    async with fake_session(monkeypatch, fake_configs(2, 640, 480, 30.0)) as group:
        old = group.ring_infos["0"].jpeg_ring_name
        old_reader = cleanup.handle(fr.FrameRingReader.attach(old))
        old_raw = cleanup.handle(open_raw(old))
        await _wait_ok(fr, old_reader)
        await group.update_camera_settings(fake_configs(2, 320, 240, 30.0))
        new = group.ring_infos["0"].jpeg_ring_name
        assert new != old
        assert int(new.rsplit("J", 1)[1]) == int(old.rsplit("J", 1)[1]) + 1
        assert parse_ring_header(old_raw.buf)["closed"] == 1
        assert old_reader.read_newest().result == fr.ReadResult.CLOSED
        old_reader.close()
        old_raw.close()
        assert _wait_gone(old), f"old ring {old} still opens by name"
        if LINUX:
            assert not os.path.exists(f"/dev/shm/{old}")
        new_reader = cleanup.handle(fr.FrameRingReader.attach(new))
        read = await _wait_ok(fr, new_reader)
        assert read.frame_number >= 0
        assert decode(read.payload).shape == (240, 320, 3)
        new_reader.close()


async def test_t_ring_27_normal_cleanup(monkeypatch):
    """T-RING-27, sections 7.4 and 7.6: session start and stop, on each OS. No ring name is
    left."""
    fr = ring()
    async with fake_session(monkeypatch, fake_configs(2)) as group:
        names = [info.jpeg_ring_name for info in group.ring_infos.values()]
        reader = fr.FrameRingReader.attach(names[0])
        try:
            await _wait_ok(fr, reader)
        finally:
            reader.close()
    for name in names:
        assert _wait_gone(name, timeout=5), f"ring {name} left after the session"
    if LINUX:
        assert not [entry for entry in os.listdir("/dev/shm") if entry.startswith(f"skc{os.getpid():x}_")]


@pytest.mark.ring_portable
@pytest.mark.ring_slow
@pytest.mark.parametrize("kill", ["main", "group"])
def test_t_ring_28_crash_cleanup(cleanup, kill, record_property):
    """T-RING-28, section 7.7 [A37]: kill the main process (Linux, Windows, macOS); on Linux also
    kill the tracker (a group kill), then start again. Windows: gone when the processes exit.
    Linux: the tracker unlinks; after a group kill, the sweep removes it. macOS: the result is
    recorded [NV], not asserted."""
    fr = ring()
    if kill == "group" and not LINUX:
        pytest.skip("spec 7.7 and T-RING-28: the tracker kill and the sweep are Linux only")
    process = subprocess.Popen(
        [sys.executable, "-c", "from skellycam.tests.frame_ring.ring_children import crash_creator_main;"
                               " crash_creator_main()"],
        stdout=subprocess.PIPE, text=True, start_new_session=(kill == "group"))
    try:
        name = process.stdout.readline().strip()
        assert name, "the stand-in main process printed no ring name"
        cleanup.name(name)
        if kill == "main":
            process.kill()
        else:
            os.killpg(process.pid, signal.SIGKILL)  # the process and its resource tracker
        process.wait(timeout=WAIT_TIMEOUT_S)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=WAIT_TIMEOUT_S)
        process.stdout.close()
    if kill == "main":
        gone = _wait_gone(name, timeout=10)
        if MACOS:
            record_property("macos_ring_gone_after_main_kill", gone)
            warnings.warn(f"T-RING-28 macOS result [NV]: ring gone after main kill = {gone}")
        else:
            assert gone, f"ring {name} left after the main process was killed"
    else:
        time.sleep(1)
        assert os.path.exists(f"/dev/shm/{name}"), "the group kill left no segment to sweep"
        removed = fr.sweep_stale_rings()
        assert name in removed
        assert not os.path.exists(f"/dev/shm/{name}")


def test_t_ring_29_too_large_request():
    """T-RING-29, section 7.8 [A36, A38]: ask for a history that cannot fit. The session does
    not start; the message has the total in bytes and MiB; no ring is left.

    The spec's small tmpfs on Linux needs root to mount. This test asks for about 45 TiB per
    ring instead, which fails on Windows at creation and on Linux at the free-space check.
    """
    fr = ring()
    if MACOS:
        pytest.skip("spec 7.8: the failure of a too-large allocation on macOS is not known [NV]")
    configs = fake_configs(2, 3840, 2160, 60.0)
    history_s = 100_000.0
    slots = 6_000_000  # ceil(100,000 s x 60 fps)
    total = 2 * fr.ring_total_size(slots, 8_298_496)
    with pytest.raises(MemoryError) as raised:
        fr.create_session_rings(configs, history_s=history_s)
    message = str(raised.value)
    assert re.search(_bytes_pattern(total), message), message
    assert f"{total / 2 ** 20:.1f} MiB" in message, message
    for index in (0, 1):
        for generation in range(64):
            assert not ring_exists(f"skc{os.getpid():x}_{index}_J{generation}")


@pytest.mark.ring_portable
def test_t_ring_30_reader_exit(cleanup, spawn, procs):
    """T-RING-30, sections 6.1 and 7.6 [A30]: a reader process attaches and exits. The ring is
    still readable by another process (Linux and macOS: `track=False`; on Windows the test also
    runs and must pass)."""
    _, creator, writer, reader = new_ring(cleanup, fps_num=4)
    payload = synthetic_payload(0, 10_000)
    writer.write(payload, **write_kwargs(0))
    for _ in range(2):  # the second process proves that the first exit did not remove the ring
        results = spawn.Queue()
        process = spawn.Process(target=ring_children.attach_and_exit, args=(creator.name, results))
        procs.append(process)
        process.start()
        assert results.get(timeout=WAIT_TIMEOUT_S) == ("OK", zlib.crc32(payload))
        process.join(timeout=WAIT_TIMEOUT_S)
        assert process.exitcode == 0
    assert reader.read(0).payload == payload
