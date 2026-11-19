"""Rules of the sender with fake sends: T-PRV-18 to T-PRV-21 and T-PRV-23 (specs/preview.md, sections
4 and 5).

Fake tests. `PreviewRelay.run` runs as a task of the test's event loop, with a fake manager and the
fake sends of `FakeConnection`. A change that the test makes with no `await` is atomic for the sender,
so a time stamp before or after it splits the messages cleanly.
"""

import asyncio
import json
import logging
import time

import pytest

from skellycam.tests.frame_ring.ring_spec import open_raw, parse_ring_header, ring, slot_payload_offset
from skellycam.tests.preview.preview_helpers import (
    CAMERA_INDEX_BASE, FakeConnection, FakeGroup, FakeManager, FakeRing, PacedWriter, SpyReader, StubReader,
    frame_read, manager_with, ready_text, running_relay, tag_of, wait_for)

A, B, C, D = "a1b2", "c3d4", "e5f6", "a7b8"


def warnings_or_above(caplog):
    return [f"{r.levelname} {r.name}: {r.getMessage()}" for r in caplog.records if r.levelno >= logging.WARNING]


async def test_t_prv_18_closed_ring_then_a_new_ring(cleanup, writers):
    """T-PRV-18, sections 4.4 and 5.3: set A's ring `closed` while its reader stays in the fake manager;
    later replace the reader with a new ring. No camera message for A while it is closed, and no
    exception; A's frames come again from the new ring."""
    a = FakeRing(cleanup, A, CAMERA_INDEX_BASE, tag=1)
    b = FakeRing(cleanup, B, CAMERA_INDEX_BASE + 1, tag=2)
    new_a = FakeRing(cleanup, A, CAMERA_INDEX_BASE, tag=3)
    manager = manager_with({A: a.reader(), B: b.reader()})
    connection = FakeConnection(answer=True)
    async with running_relay(manager, connection):
        writers.extend(PacedWriter(r).start_task() for r in (a, b))
        await wait_for(lambda: len(connection.camera(A)) >= 3, "3 camera messages for A")
        a.set_closed()
        t_closed = time.monotonic()
        await asyncio.sleep(0.5)
        assert connection.camera(A, since=t_closed) == [], "a camera message for A while its ring is closed"
        assert len(connection.camera(B, since=t_closed)) >= 5, "B stopped"
        new_a.write_range(0, 2)
        manager.replace_reader(A, new_a.reader())
        t_new = time.monotonic()
        writers.append(PacedWriter(new_a).start_task())
        await wait_for(lambda: len(connection.camera(A, since=t_new)) >= 3, "camera messages from the new ring")
    assert {tag_of(m) for m in connection.camera(A, since=t_new)} == {new_a.tag}


def flip_payload_bit(cleanup, fake_ring, k):
    shm = cleanup.handle(open_raw(fake_ring.name))
    header = parse_ring_header(shm.buf)
    offset = slot_payload_offset(header, k % header["slot_count"]) + 20
    shm.buf[offset] = shm.buf[offset] ^ 0x01


@pytest.mark.parametrize("case", ["corrupt", "lapped"])
async def test_t_prv_19_failed_reads(cleanup, caplog, case):
    """T-PRV-19, sections 4.3 and 5.3 [agent 7, agent 18]. (1) Flip one payload bit of A's newest frame
    after commit (`CORRUPT`); run 20 passes; then write the next frame. A spy counts the reads of the
    passes by frame number; it does not count the tick reads. (2) A stub reader whose `read` gives
    `NOT_YET_WRITTEN` for the check and `LAPPED` for the probe two times, then `OK`.

    (1) No message for the bad frame; the passes read it in one pass only; the next frame goes out.
    (2) No message for the two `LAPPED` passes; the `OK` frame goes out. No log record at WARNING or
    above in either case.

    The passes run in `run`, not one by one: the spec names no call for one pass. The tick reads
    through `read_newest`; the spy counts only the calls of `read`, and the stub gives the tick no
    frame. In (1), "20 passes" is 20 checks `read(7)` after the bad frame."""
    caplog.set_level(logging.WARNING)
    fr = ring()
    connection = FakeConnection(answer=True)
    if case == "corrupt":
        a = FakeRing(cleanup, A)
        spy = SpyReader(a.reader())
        async with running_relay(manager_with({A: spy}), connection):
            a.write_range(0, 4)
            await wait_for(lambda: 4 in [m.frame_number for m in connection.camera(A)], "frame 4")
            await asyncio.sleep(0.05)  # the ready answer of frame 4
            a.write(5)
            flip_payload_bit(cleanup, a, 5)
            t_bad = time.monotonic()
            assert a.reader().read(5).result is fr.ReadResult.CORRUPT
            await wait_for(lambda: len(spy.reads_of(7, since=t_bad)) >= 20, "20 passes after the bad frame")
            a.write(6)
            await wait_for(lambda: 6 in [m.frame_number for m in connection.camera(A)], "frame 6")
        assert 5 not in [m.frame_number for m in connection.camera(A)], "a camera message for the CORRUPT frame"
        assert len(spy.reads_of(5, since=t_bad)) == 1, f"the passes read frame 5 {len(spy.reads_of(5, since=t_bad))} times"
    else:
        lapped = frame_read(fr.ReadResult.LAPPED, 0)
        ok = frame_read(fr.ReadResult.OK, 0, arrival_ns=7_000_000_000, source_frame_number=0,
                        payload=b"\xff\xd8stub\xff\xd9")
        stub = StubReader({0: [lapped, lapped, ok]})
        async with running_relay(manager_with({A: stub}), connection):
            await wait_for(lambda: connection.camera(A), "the OK frame")
            await asyncio.sleep(0.1)
        messages = connection.camera(A)
        assert [(m.frame_number, m.jpeg) for m in messages] == [(0, ok.payload)]
        assert stub.calls.count(("read", 0)) == 3, stub.calls[:12]
    assert warnings_or_above(caplog) == []


def four_cameras(cleanup):
    rings = {cid: FakeRing(cleanup, cid, CAMERA_INDEX_BASE + i, tag=i + 1) for i, cid in enumerate((A, B, C, D))}
    for fake_ring in rings.values():
        fake_ring.write_range(0, 2)
    spies = {cid: SpyReader(r.reader()) for cid, r in rings.items()}
    manager = FakeManager(FakeGroup("g1", {cid: spies[cid] for cid in (A, B, C)}), FakeGroup("g2", {D: spies[D]}))
    return rings, spies, manager


@pytest.mark.parametrize("case", ["send_bytes", "send_json"])
async def test_t_prv_20_changes_while_a_send_waits(cleanup, case):
    """T-PRV-20, sections 4.4 and 5.1 [agent 14, agent 16]. (1) Slow send. Cameras A, B, C in group 1;
    camera D in group 2. While the send of A waits: remove and close B's reader; replace C's reader
    with a new ring; remove group 2; call `handle_text` with a ready message for A. Then release the
    send. (2) A slow `send_json`: while the first `framerate_update` of a tick waits, remove and close
    B's reader and remove group 2. Then release it.

    No exception, and `run` continues; no read through a closed reader (the closed reader raises if it
    is read); no message for B or D; C's next message is from the new ring; A is `ready` after the send
    (the ready message is not lost). (2) The same, for the tick: no read after its first `send_json`.

    "A is ready": a new frame of A goes out within 0.3 s, long before the safety net. In (2), "no
    message for B or D" is no camera message after the removal."""
    rings, spies, manager = four_cameras(cleanup)
    if case == "send_bytes":
        new_c = FakeRing(cleanup, C, CAMERA_INDEX_BASE + 2, tag=9)
        new_c.write_range(0, 1)
        connection = FakeConnection()
        connection.bytes_gate.arm()
        async with running_relay(manager, connection) as (relay, task):
            await asyncio.wait_for(connection.bytes_gate.entered.wait(), 5)
            manager.remove_reader(B)
            manager.replace_reader(C, SpyReader(new_c.reader()))
            manager.remove_group("g2")
            assert relay.handle_text(ready_text(A)) is True
            connection.bytes_gate.release.set()
            await wait_for(lambda: connection.camera(C), "the next message of C")
            await wait_for(lambda: connection.camera(A), "the message of A")
            await asyncio.sleep(0.05)
            rings[A].write(3)
            await wait_for(lambda: 3 in [m.frame_number for m in connection.camera(A)],
                           "a new frame of A: A is not ready after the send", timeout=0.3)
            assert not task.done()
        assert connection.camera()[0].camera_id == A, "the first camera message is not the one of A"
        assert {tag_of(m) for m in connection.camera(C)} == {new_c.tag}
        assert connection.camera(B) == [] and connection.camera(D) == []
    else:
        connection = FakeConnection(answer=True)
        connection.json_gate.arm()
        async with running_relay(manager, connection) as (_, task):
            await asyncio.wait_for(connection.json_gate.entered.wait(), 5)
            manager.remove_reader(B)
            manager.remove_group("g2")
            t_removed = time.monotonic()
            connection.json_gate.release.set()
            await asyncio.sleep(0.6)
            assert not task.done()
        assert connection.camera(B, since=t_removed) == [] and connection.camera(D, since=t_removed) == []
    for cid, spy in spies.items():
        assert spy.after_close == [], f"reads through the closed reader of {cid}: {spy.after_close}"


INVALID_TEXTS = {
    "camera_id missing": ('{"message_type": "camera_ready"}', True, "warning"),
    "camera_id 7": ('{"message_type": "camera_ready", "camera_id": 7}', True, "warning"),
    "unknown camera id": (ready_text("zzzz"), True, "none"),
    "not JSON": ("not json {", False, "any"),
    "frameNumber": (json.dumps({"frameNumber": 3}), False, "any"),
    "ping": ("ping", False, "any"),
}


@pytest.mark.parametrize("case", ["valid", *INVALID_TEXTS])
async def test_t_prv_21_handle_text(cleanup, caplog, case):
    """T-PRV-21, section 4.1 [agent 9, agent 21]: `handle_text` with: a valid ready message; `camera_id`
    missing; `camera_id` 7; an unknown camera id; text that is not JSON; `{"frameNumber": 3}`; `ping`.

    Valid: `True`, camera `ready`. Missing and 7: `True`, one WARNING record each, nothing changes.
    Unknown id: `True`, no record. Not JSON, `frameNumber` and `ping`: `False`. No exception.

    The spec gives no read of the `ready` field, so the test reads the behaviour: camera A has sent
    frame 0 and is not ready. Then a new frame of A goes out within 0.3 s only if the text made A
    ready. The safety net comes 1 s after frame 0. The call is synchronous, so each record during the
    call comes from it."""
    caplog.set_level(logging.DEBUG)
    a = FakeRing(cleanup, A)
    a.write(0)
    connection = FakeConnection()
    async with running_relay(manager_with({A: a.reader()}), connection) as (relay, _):
        await wait_for(lambda: connection.camera(A), "frame 0")
        t0 = connection.camera_times(A)[0]
        text, expected, records = (ready_text(A), True, "none") if case == "valid" else INVALID_TEXTS[case]
        before = len(caplog.records)
        assert relay.handle_text(text) is expected
        new = caplog.records[before:]
        a.write(1)
        if case == "valid":
            await wait_for(lambda: len(connection.camera(A)) >= 2, "frame 1 after the ready message", timeout=0.3)
            assert connection.camera_times(A)[1] < t0 + 0.9
        else:
            await asyncio.sleep(max(0.0, t0 + 0.8 - time.monotonic()))
            assert [m.frame_number for m in connection.camera(A)] == [0], "the text changed the state of A"
    if records == "warning":
        assert [r.levelno for r in new if r.levelno >= logging.WARNING] == [logging.WARNING], [r.getMessage() for r in new]
    elif records == "none":
        assert new == [], [r.getMessage() for r in new]


async def test_t_prv_23_no_reads_while_the_manager_closes(cleanup, writers):
    """T-PRV-23, section 4.4 [agent 26]: set `closing = True` on the fake manager for 0.5 s, then
    `False`. No read and no message while it is `True`; messages again after.

    "No read" counts each call to the readers, also `oversize_count` and `skipped_count`."""
    a = FakeRing(cleanup, A, CAMERA_INDEX_BASE, tag=1)
    b = FakeRing(cleanup, B, CAMERA_INDEX_BASE + 1, tag=2)
    spies = {A: SpyReader(a.reader()), B: SpyReader(b.reader())}
    manager = manager_with(spies)
    connection = FakeConnection(answer=True)
    async with running_relay(manager, connection):
        writers.extend(PacedWriter(r).start_task() for r in (a, b))
        await wait_for(lambda: len(connection.camera(A)) >= 3 and connection.json("framerate_update"),
                       "camera messages and a framerate_update")
        manager.closing = True
        reads, events = sum(len(s.calls) for s in spies.values()), len(connection.events)
        await asyncio.sleep(0.5)
        assert sum(len(s.calls) for s in spies.values()) == reads, "a read while the manager closes"
        assert len(connection.events) == events, "a message while the manager closes"
        manager.closing = False
        t_open = time.monotonic()
        await wait_for(lambda: connection.camera(A, since=t_open) and connection.camera(B, since=t_open)
                       and connection.json("framerate_update", since=t_open), "messages after the close ends",
                       timeout=2.0)
