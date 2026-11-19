"""Self-tests of the preview test helpers (specs/preview.md, section 9.1).

These tests pass before the product code of step 4a exists. Thus a failure of a T-PRV test comes
from the product, not from a helper.
"""

import asyncio
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from skellycam.core.recorders.framerate_tracker import CurrentFramerate

from skellycam.tests.frame_ring.ring_spec import ring
from skellycam.tests.preview.preview_helpers import (
    HEADER_SIZE, OVERSIZE_PAYLOAD_SIZE, ROUTE, SPEC_EXAMPLE, FakeConnection, FakeGroup, FakeManager, FakeRing,
    PacedWriter, ReadThroughClosedReader, SpyReader, StubReader, WsClient, frame_read, pack_message_for_test,
    parse_camera_message, preview_app, pump, ready_text, wait_for)


def test_parser_reads_the_example_of_the_spec():
    """The independent parser gives the values of the example of section 3.2."""
    message = parse_camera_message(SPEC_EXAMPLE)
    assert message.version == 1
    assert message.reserved == b"\0\0\0"
    assert message.flags == 0x30
    assert message.frame_number == 258
    assert message.arrival_ns == 1_000_000_007
    assert message.rotation_cw_deg == 90
    assert message.jpeg_len == 4
    assert message.camera_id == "a1b2"
    assert message.camera_id_raw == b"a1b2" + b"\0" * 12
    assert message.jpeg == b"\xff\xd8\xff\xd9"
    assert message.length == HEADER_SIZE + 4


def test_parser_round_trip_at_the_table_offsets():
    data = pack_message_for_test(version=1, flags=0xDEADBEEF, frame_number=-5, arrival_ns=2 ** 62 + 3,
                                 rotation_cw_deg=270, camera_id=b"abcdefghijklmnop", jpeg=b"xyz")
    message = parse_camera_message(data)
    assert (message.flags, message.frame_number, message.arrival_ns, message.rotation_cw_deg) == (
        0xDEADBEEF, -5, 2 ** 62 + 3, 270)
    assert message.jpeg_len == 3 and message.jpeg == b"xyz" and message.camera_id == "abcdefghijklmnop"
    assert pack_message_for_test(flags=0x30, frame_number=258, arrival_ns=1_000_000_007, rotation_cw_deg=90,
                                 camera_id=b"a1b2", jpeg=b"\xff\xd8\xff\xd9") == SPEC_EXAMPLE


def test_fake_ring_writes_frames_that_the_reader_reads(cleanup):
    fr = ring()
    a = FakeRing(cleanup, "a1b2", tag=1)
    b = FakeRing(cleanup, "b1b2", tag=2)
    reader = a.reader()
    a.write_range(0, 4, rotation=90, flags=0x20)
    a.write(5, payload=b"\0" * OVERSIZE_PAYLOAD_SIZE)
    a.write(6, newer_frame_waiting=True)
    read = reader.read(4)
    assert read.result is fr.ReadResult.OK and read.payload == a.payload(4) != b.payload(4)
    assert (read.arrival_ns, read.rotation_cw_deg, read.flags, read.source_frame_number) == (a.arrival(4), 90, 0x20, 4)
    assert reader.read(5).result is fr.ReadResult.OVERSIZE
    assert a.last == 5 and list(a.skipped) == [6] and sorted(a.written) == [0, 1, 2, 3, 4, 5]
    assert a.arrival(0) != b.arrival(0) and a.name != b.name


def test_paced_writer_thread_rate_stop_after_and_skip(cleanup):
    a = FakeRing(cleanup, "a1b2")
    writer = PacedWriter(a, fps=100, stop_after=9, script=lambda k: {"newer_frame_waiting": k == 4}).start_thread()
    try:
        deadline = time.monotonic() + 5
        while a.last < 9 and time.monotonic() < deadline:
            time.sleep(0.01)
        time.sleep(0.05)
    finally:
        writer.stop()
    assert a.last == 9 and list(a.skipped) == [4]
    assert sorted(a.written) == [0, 1, 2, 3, 5, 6, 7, 8, 9]
    assert a.written[5] - a.skipped[4] < 0.005, "the frame after a skip is not written in the same step"
    elapsed = a.written[9] - a.written[0]
    assert 0.05 <= elapsed <= 1.0, elapsed


async def test_paced_writer_task_runs_on_the_event_loop(cleanup):
    a = FakeRing(cleanup, "a1b2")
    writer = PacedWriter(a, fps=50).start_task()
    try:
        await wait_for(lambda: a.last >= 5, "6 frames")
    finally:
        writer.stop()
    assert sorted(a.written)[:6] == [0, 1, 2, 3, 4, 5]


def test_fake_manager_add_replace_remove_close(cleanup):
    a, b, c = (FakeRing(cleanup, cid) for cid in ("a", "b", "c"))
    spies = {cid: SpyReader(r.reader()) for cid, r in (("a", a), ("b", b))}
    manager = FakeManager(FakeGroup("g1", spies), FakeGroup("g2"))
    assert manager.closing is False and list(manager.camera_groups) == ["g1", "g2"]
    assert manager.group("g1").id == "g1"
    new_c = SpyReader(c.reader())
    manager.add_reader("c", new_c)
    manager.replace_reader("a", SpyReader(a.reader()))
    assert spies["a"].closed and manager.group().ring_readers["a"] is not spies["a"]
    manager.remove_reader("b")
    assert spies["b"].closed and list(manager.group().ring_readers) == ["c", "a"]
    manager.add_reader("x", SpyReader(c.reader()), group_id="g2")
    manager.remove_group("g2")
    assert list(manager.camera_groups) == ["g1"]


def test_spy_reader_records_and_raises_after_close(cleanup):
    fr = ring()
    a = FakeRing(cleanup, "a")
    a.write_range(0, 2)
    spy = SpyReader(a.reader())
    assert spy.read(1).result is fr.ReadResult.OK
    assert spy.read_newest().frame_number == 2
    assert len(spy.reads_of(1)) == 1 and len(spy.read_calls()) == 2
    spy.close()
    with pytest.raises(ReadThroughClosedReader):
        spy.read(2)
    with pytest.raises(ReadThroughClosedReader):
        spy.read_newest()
    assert spy.after_close == [("read", 2), ("read_newest", None)]


def test_stub_reader_follows_its_script():
    fr = ring()
    ok = frame_read(fr.ReadResult.OK, 0, payload=b"abc", arrival_ns=5)
    stub = StubReader({0: [frame_read(fr.ReadResult.LAPPED, 0), frame_read(fr.ReadResult.LAPPED, 0), ok]},
                      oversize_count=2, skipped_count=1)
    assert stub.read(1).result is fr.ReadResult.NOT_YET_WRITTEN
    assert [stub.read(0).result for _ in range(4)] == [fr.ReadResult.LAPPED, fr.ReadResult.LAPPED,
                                                       fr.ReadResult.OK, fr.ReadResult.OK]
    assert stub.read_newest().result is fr.ReadResult.NOT_YET_WRITTEN
    assert (stub.oversize_count, stub.skipped_count) == (2, 1)
    assert ok.payload_len == 3 and ok.payload == b"abc"
    assert frame_read(fr.ReadResult.OVERSIZE, 3, payload_len=9000).payload_len == 9000


async def test_slow_send_waits_while_other_coroutines_run():
    connection = FakeConnection()
    connection.bytes_gate.arm()
    ticks = []

    async def other():
        while True:
            ticks.append(time.monotonic())
            await asyncio.sleep(0.005)

    other_task = asyncio.create_task(other())
    send = asyncio.create_task(connection.send_bytes(pack_message_for_test(camera_id=b"a1b2")))
    await asyncio.wait_for(connection.bytes_gate.entered.wait(), 2)
    count = len(ticks)
    await asyncio.sleep(0.05)
    assert not send.done() and len(ticks) > count, "the slow send does not let other coroutines run"
    assert connection.events == []
    connection.bytes_gate.release.set()
    await asyncio.wait_for(send, 2)
    other_task.cancel()
    assert [m.camera_id for m in connection.camera()] == ["a1b2"]
    await connection.send_bytes(pack_message_for_test(camera_id=b"a1b2"))  # the gate holds one send only
    assert len(connection.camera("a1b2")) == 2


async def test_fake_connection_answers_after_the_send_and_encodes_json():
    answered = []

    class Relay:
        def handle_text(self, text):
            answered.append(text)

    connection = FakeConnection(answer={"a1b2"})
    connection.relay = Relay()
    await connection.send_bytes(pack_message_for_test(camera_id=b"a1b2"))
    await connection.send_bytes(pack_message_for_test(camera_id=b"c3d4"))
    assert answered == [], "the fake client answered before the send returned"
    await asyncio.sleep(0)
    assert answered == [ready_text("a1b2")]
    framerate = CurrentFramerate.from_durations_ms(durations_ms=np.array([10.0, 10.0]), framerate_source="x")
    await connection.send_json({"message_type": "framerate_update", "f": framerate})
    assert connection.json("framerate_update")[0]["f"]["mean_frames_per_second"] == 100.0


class _DummyRelay:
    """A stand-in for `PreviewRelay` for the self-test of the test route."""

    instances = []

    def __init__(self, manager, send_bytes, send_json):
        self.send_bytes, self.send_json, self.texts = send_bytes, send_json, []
        _DummyRelay.instances.append(self)

    async def run(self):
        k = 0
        while True:
            await self.send_bytes(pack_message_for_test(frame_number=k, camera_id=b"a1b2"))
            await self.send_json({"message_type": "framerate_update", "k": k})
            k += 1
            await asyncio.sleep(0.05)

    def handle_text(self, text):
        self.texts.append(text)
        return True


def test_test_route_runs_relays_and_ends_them_at_disconnect():
    _DummyRelay.instances.clear()
    app = preview_app(FakeManager(), relay_class=_DummyRelay)
    with TestClient(app) as client:
        with client.websocket_connect(ROUTE) as session:
            ws = WsClient(session, answer=True)
            pump(ws, until=lambda: len(ws.camera["a1b2"]) >= 3 and ws.json, what="3 messages")
            assert ws.frames("a1b2")[:3] == [0, 1, 2]
            assert ws.json[0][1] == {"message_type": "framerate_update", "k": 0}
            session.send_text("ping")
        closed = time.monotonic()
        deadline = closed + 1.0
        while not app.state.run_tasks[0].done() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert app.state.run_tasks[0].done(), "the test route did not end the run task within 1 s"
        relay = _DummyRelay.instances[0]
        assert ready_text("a1b2") in relay.texts and "ping" in relay.texts
    assert app.state.errors == []


def test_ws_client_receive_times_out():
    class Quiet(_DummyRelay):
        async def run(self):
            await asyncio.sleep(3600)

    app = preview_app(FakeManager(), relay_class=Quiet)
    with TestClient(app) as client, client.websocket_connect(ROUTE) as session:
        ws = WsClient(session)
        start = time.monotonic()
        assert ws.receive(0.2) is None
        assert 0.15 <= time.monotonic() - start <= 2.0
