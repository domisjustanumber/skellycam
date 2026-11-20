"""The sender through a websocket: T-PRV-02 and T-PRV-04 to T-PRV-17 (specs/preview.md, sections 3
to 5).

ws tests. A Starlette test client connects to the test route of `preview_helpers`, which wires
`PreviewRelay` to the websocket as 4b will. Paced writer threads write fake rings at 30 fps. Changes
to the fake manager run on the event-loop thread of the server (`client.portal.call`), as
`CameraGroup` makes them. The pass thresholds are those of section 9.2 [agent 23].
"""

import contextlib
import logging
import time

import pytest
from fastapi.testclient import TestClient

from skellycam.tests.frame_ring.ring_spec import ring
from skellycam.tests.preview.preview_helpers import (
    CAMERA_INDEX_BASE, HEADER_SIZE, ROUTE, FakeRing, PacedWriter, WsClient, manager_with, preview_app, pump,
    run_errors, tag_of)

A, B, C, D = "a1b2", "c3d4", "e5f6", "a7b8"


@contextlib.contextmanager
def server(manager):
    """The test route on a running test server. At the end, no `run` or `handle_text` raised."""
    app = preview_app(manager)
    with TestClient(app) as client:
        yield app, client
    assert run_errors(app) == []


def fake_rings(cleanup, camera_ids, **kwargs):
    return {cid: FakeRing(cleanup, cid, CAMERA_INDEX_BASE + i, tag=i + 1, **kwargs) for i, cid in enumerate(camera_ids)}


def start_writers(writers, rings, **kwargs):
    for fake_ring in rings:
        writers.append(PacedWriter(fake_ring, **kwargs).start_thread())


def received_in_window(ws, camera_id, t0, t1):
    return set(ws.frames(camera_id, t0, t1))


def assert_share(ws, fake_ring, t0, t1, share=0.8):
    written = fake_ring.written_between(t0, t1)
    got = received_in_window(ws, fake_ring.camera_id, t0, t1) & set(written)
    assert len(got) >= share * len(written), (
        f"camera {fake_ring.camera_id}: {len(got)} of {len(written)} frames written in {t1 - t0:.1f} s")


def warnings_or_above(caplog):
    return [f"{r.levelname} {r.name}: {r.getMessage()}" for r in caplog.records if r.levelno >= logging.WARNING]


# ---------------------------------------------------------------------------
# Content of the camera messages
# ---------------------------------------------------------------------------

def test_t_prv_02_message_fields_equal_the_slot(cleanup, writers):
    """T-PRV-02, sections 3.2 and 3.3: three fake rings at 30 fps for 5 s; the client answers at once. A
    second reader per ring reads each received `frame_number`. Each field that the independent parser
    reads equals the slot field of that frame; the JPEG bytes equal the ring payload (the rule of
    T-RING-33).

    The frames vary their rotation and the flag 0x20, so each field has more than one value."""
    fr = ring()
    rings = fake_rings(cleanup, (A, B, C), history_s=2.0)
    slot_readers = {cid: r.reader() for cid, r in rings.items()}
    manager = manager_with({cid: r.reader() for cid, r in rings.items()})
    with server(manager) as (_, client), client.websocket_connect(ROUTE) as session:
        ws = WsClient(session, answer=True)
        start_writers(writers, rings.values(), script=lambda k: {"rotation": (k // 15 % 4) * 90,
                                                                 "flags": 0x20 if k % 3 == 0 else 0})
        problems, end = [], time.monotonic() + 5.0
        while time.monotonic() < end:
            message = ws.poll()
            if message is None or isinstance(message, dict):
                continue
            slot = slot_readers[message.camera_id].read(message.frame_number)
            if slot.result is not fr.ReadResult.OK:
                problems.append(f"{message.camera_id} {message.frame_number}: slot read {slot.result}")
                continue
            expected = dict(version=1, reserved=b"\0\0\0", flags=slot.flags, arrival_ns=slot.arrival_ns,
                            rotation_cw_deg=slot.rotation_cw_deg, jpeg_len=slot.payload_len,
                            camera_id_raw=message.camera_id.encode("ascii").ljust(16, b"\0"), jpeg=slot.payload,
                            length=HEADER_SIZE + slot.payload_len)
            for name, value in expected.items():
                if getattr(message, name) != value:
                    problems.append(f"{message.camera_id} {message.frame_number}: {name}")
    assert not problems, problems[:10]
    for cid in rings:
        assert len(ws.camera[cid]) >= 30, f"camera {cid}: {len(ws.camera[cid])} camera messages in 5 s"
        assert {m.rotation_cw_deg for _, m in ws.camera[cid]} >= {0, 90}


def test_t_prv_04_rotation_of_each_frame(cleanup):
    """T-PRV-04, section 3.3: one ring; rotation 0, then 90, 180, 270, 0 on consecutive frames; the
    client answers at once. Each camera message has the rotation of its own frame."""
    rotations = [0, 90, 180, 270, 0]
    a = FakeRing(cleanup, A)
    with server(manager_with({A: a.reader()})) as (_, client), client.websocket_connect(ROUTE) as session:
        ws = WsClient(session, answer=True)
        for k, rotation in enumerate(rotations):
            a.write(k, rotation=rotation)
            pump(ws, until=lambda k=k: k in ws.frames(A), timeout=2.0, what=f"the camera message of frame {k}")
    assert ws.frames(A) == [0, 1, 2, 3, 4]
    assert [m.rotation_cw_deg for _, m in ws.camera[A]] == rotations


def test_t_prv_05_camera_ids_that_do_not_fit(cleanup, writers, caplog):
    """T-PRV-05, section 3.3 [agent 4]: camera ids `a1b2`, `abcdefghijklmnop` (16),
    `abcdefghijklmnopq` (17) and `cámara`. The first two are sent, NUL-padded to 16 bytes; the last
    two get no camera message and one ERROR record each for the connection; the first two are not
    affected.

    The ring tag in each JPEG tells which ring a message comes from (a cut id of 17 bytes would read
    as the id of 16 bytes). "Not affected": at least 80 % of their frames in 1.5 s."""
    ids = ["a1b2", "abcdefghijklmnop", "abcdefghijklmnopq", "cámara"]
    rings = fake_rings(cleanup, ids)
    with server(manager_with({cid: r.reader() for cid, r in rings.items()})) as (_, client), \
            client.websocket_connect(ROUTE) as session:
        ws = WsClient(session, answer=True)
        t0 = time.monotonic()
        start_writers(writers, rings.values())
        pump(ws, duration=1.5)
        t1 = time.monotonic()
    by_tag = {}
    for messages in ws.camera.values():
        for _, message in messages:
            by_tag.setdefault(tag_of(message), []).append(message)
    good, bad = [rings[cid] for cid in ids[:2]], [rings[cid] for cid in ids[2:]]
    for fake_ring in bad:
        assert fake_ring.tag not in by_tag, f"camera {fake_ring.camera_id!r} got a camera message"
    for fake_ring in good:
        assert {m.camera_id_raw for m in by_tag.get(fake_ring.tag, [])} == {fake_ring.camera_id.encode().ljust(16, b"\0")}
        assert_share(ws, fake_ring, t0, t1)
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 2, errors
    for fake_ring in bad:
        assert len([e for e in errors if fake_ring.camera_id in e]) == 1, (fake_ring.camera_id, errors)


# ---------------------------------------------------------------------------
# Flow control: ready messages and the safety net (section 4)
# ---------------------------------------------------------------------------

def first_messages(ws, cameras, timeout):
    pump(ws, until=lambda: all(ws.first(cid) for cid in cameras), timeout=timeout,
         what="the first camera message of each camera")
    return {cid: ws.first(cid)[0] for cid in cameras}


def test_t_prv_06_first_frame_with_no_ready_message(cleanup, writers):
    """T-PRV-06, sections 4.2 and 4.4 [agent 10]: two rings with frames 0 to 9; connect; send no ready
    message; the writers continue. Exactly one camera message per camera, frame 9 or newer, within 1 s
    of the connect; no other camera message until 0.8 s after it."""
    rings = fake_rings(cleanup, (A, B))
    for fake_ring in rings.values():
        fake_ring.write_range(0, 9)
    with server(manager_with({cid: r.reader() for cid, r in rings.items()})) as (_, client):
        t_connect = time.monotonic()
        with client.websocket_connect(ROUTE) as session:
            start_writers(writers, rings.values())
            ws = WsClient(session)
            first = first_messages(ws, (A, B), timeout=2.0)
            pump(ws, duration=max(first.values()) + 0.8 - time.monotonic())
    for cid in (A, B):
        assert first[cid] - t_connect <= 1.0, f"camera {cid}: first message {first[cid] - t_connect:.2f} s after the connect"
        assert ws.frames(cid)[0] >= 9, f"camera {cid}: frame {ws.frames(cid)[0]}"
        assert len(ws.frames(cid, until=first[cid] + 0.8)) == 1, f"camera {cid}: {ws.frames(cid)}"


def test_t_prv_07_ready_message_sends_the_newest_frame(cleanup, writers):
    """T-PRV-07, sections 4.1 and 4.3: as T-PRV-06; within its 0.8 s, pause the writers at frame 20 and
    send a ready message for one camera. One camera message for that camera, frame 20; none for the
    other camera until its safety net.

    The answer comes before the safety net of camera A (1 s after its first message), so the second
    message of A is the answer to the ready message."""
    rings = fake_rings(cleanup, (A, B))
    for fake_ring in rings.values():
        fake_ring.write_range(0, 9)
    with server(manager_with({cid: r.reader() for cid, r in rings.items()})) as (_, client), \
            client.websocket_connect(ROUTE) as session:
        start_writers(writers, rings.values(), stop_after=20)
        ws = WsClient(session)
        first = first_messages(ws, (A, B), timeout=2.0)
        pump(ws, until=lambda: rings[A].last == 20 and rings[B].last == 20, timeout=2.0, what="frame 20")
        t_ready = time.monotonic()
        assert t_ready < first[A] + 0.7, "the writers were too slow for the 0.8 s of T-PRV-06"
        ws.send_ready(A)
        pump(ws, until=lambda: len(ws.camera[A]) >= 2, timeout=first[A] + 0.9 - time.monotonic(),
             what="the answer to the ready message of camera A, before its safety net")
        pump(ws, duration=max(0.0, first[B] + 0.9 - time.monotonic()))
    assert ws.frames(A) == [ws.frames(A)[0], 20]
    assert len(ws.frames(B, until=first[B] + 0.9)) == 1, f"camera {B}: {ws.frames(B)}"


def test_t_prv_08_ready_message_with_no_new_frame(cleanup):
    """T-PRV-08, sections 4.3 and 4.4: a ready message while the newest frame is the last sent frame;
    then write one frame. No camera message before the write; one camera message with the new frame
    within 0.5 s after the write."""
    a = FakeRing(cleanup, A)
    a.write_range(0, 4)
    with server(manager_with({A: a.reader()})) as (_, client), client.websocket_connect(ROUTE) as session:
        ws = WsClient(session)
        first_messages(ws, (A,), timeout=2.0)
        ws.send_ready(A)
        pump(ws, duration=0.3)
        assert ws.frames(A) == [4], "a camera message with no new frame"
        a.write(5)
        t_write = time.monotonic()
        pump(ws, until=lambda: len(ws.camera[A]) >= 2, timeout=0.5, what="the new frame within 0.5 s")
    assert ws.frames(A) == [4, 5]
    assert ws.times(A)[1] - t_write <= 0.5


def test_t_prv_09_a_camera_with_no_answer_does_not_hold_back_the_others(cleanup, writers):
    """T-PRV-09, sections 4.3 and 4.4 [P2, A6]: three rings at 30 fps for 5 s; the client answers at once
    for cameras A and B; it never answers for camera C. A and B each get at least 80 % of the frames
    written in that time; C gets 4 to 7 camera messages (the safety net)."""
    rings = fake_rings(cleanup, (A, B, C))
    with server(manager_with({cid: r.reader() for cid, r in rings.items()})) as (_, client), \
            client.websocket_connect(ROUTE) as session:
        ws = WsClient(session, answer={A, B})
        t0 = time.monotonic()
        start_writers(writers, rings.values())
        pump(ws, duration=5.0)
        t1 = time.monotonic()
    assert_share(ws, rings[A], t0, t1)
    assert_share(ws, rings[B], t0, t1)
    assert 4 <= len(ws.camera[C]) <= 7, f"camera {C}: {len(ws.camera[C])} camera messages"


def test_t_prv_10_four_cameras_that_keep_up(cleanup, writers):
    """T-PRV-10, sections 4.3 and 8.4: four rings at 30 fps for 10 s; the client answers at once. Each
    camera gets at least 80 % of its frames; `frame_number` increases in the camera messages of each
    camera."""
    rings = fake_rings(cleanup, (A, B, C, D))
    with server(manager_with({cid: r.reader() for cid, r in rings.items()})) as (_, client), \
            client.websocket_connect(ROUTE) as session:
        ws = WsClient(session, answer=True)
        t0 = time.monotonic()
        start_writers(writers, rings.values())
        pump(ws, duration=10.0)
        t1 = time.monotonic()
    for cid, fake_ring in rings.items():
        assert_share(ws, fake_ring, t0, t1)
        frames = ws.frames(cid)
        assert all(b > a for a, b in zip(frames, frames[1:])), f"camera {cid}: frame numbers do not increase"


def test_t_prv_11_safety_net_only(cleanup, writers):
    """T-PRV-11, section 4.4 [A6, agent 11]: two rings at 30 fps; the client never answers; 5.5 s. Each
    camera gets 4 to 7 camera messages; each holds a frame that was written after the previous camera
    message of that camera; the intervals are 0.9 to 1.6 s."""
    rings = fake_rings(cleanup, (A, B))
    with server(manager_with({cid: r.reader() for cid, r in rings.items()})) as (_, client), \
            client.websocket_connect(ROUTE) as session:
        ws = WsClient(session)
        start_writers(writers, rings.values())
        pump(ws, duration=5.5)
    for cid, fake_ring in rings.items():
        received = ws.camera[cid]
        assert 4 <= len(received) <= 7, f"camera {cid}: {len(received)} camera messages"
        for (t_prev, _), (t, message) in zip(received, received[1:]):
            assert fake_ring.written[message.frame_number] > t_prev, f"camera {cid}: frame {message.frame_number} is old"
            assert 0.9 <= t - t_prev <= 1.6, f"camera {cid}: interval {t - t_prev:.2f} s"


def test_t_prv_12_reconnect(cleanup, writers):
    """T-PRV-12, section 4.4 [agent 22]: connect, receive, close; connect again with a new client; send
    no ready message. The `run` task of the first connection has ended within 1 s of the close; the new
    client gets the newest frame of each camera.

    "The newest frame": a frame not older than the newest frame at the second connect."""
    rings = fake_rings(cleanup, (A, B))
    with server(manager_with({cid: r.reader() for cid, r in rings.items()})) as (app, client):
        start_writers(writers, rings.values())
        with client.websocket_connect(ROUTE) as session:
            ws1 = WsClient(session, answer=True)
            first_messages(ws1, (A, B), timeout=2.0)
        t_close = time.monotonic()
        while not app.state.run_tasks[0].done() and time.monotonic() < t_close + 1.0:
            time.sleep(0.01)
        assert app.state.run_tasks[0].done(), "the run task of the first connection did not end within 1 s"
        newest = {cid: r.last for cid, r in rings.items()}
        with client.websocket_connect(ROUTE) as session:
            ws2 = WsClient(session)
            first_messages(ws2, (A, B), timeout=2.0)
        assert len(app.state.run_tasks) == 2
    for cid in (A, B):
        assert ws2.frames(cid)[0] >= newest[cid], f"camera {cid}: frame {ws2.frames(cid)[0]} < {newest[cid]}"


def test_t_prv_13_two_clients(cleanup, writers):
    """T-PRV-13, section 4.4 [agent 17]: two clients on two rings at 30 fps for 5 s. Client 1 answers at
    once; client 2 never. Client 1 gets at least 80 % of the frames; client 2 gets only safety-net
    camera messages (4 to 7 per camera)."""
    rings = fake_rings(cleanup, (A, B))
    with server(manager_with({cid: r.reader() for cid, r in rings.items()})) as (_, client), \
            client.websocket_connect(ROUTE) as session1, client.websocket_connect(ROUTE) as session2:
        ws1, ws2 = WsClient(session1, answer=True), WsClient(session2)
        t0 = time.monotonic()
        start_writers(writers, rings.values())
        pump([ws1, ws2], duration=5.0)
        t1 = time.monotonic()
    for cid, fake_ring in rings.items():
        assert_share(ws1, fake_ring, t0, t1)
        assert 4 <= len(ws2.camera[cid]) <= 7, f"client 2, camera {cid}: {len(ws2.camera[cid])} camera messages"


# ---------------------------------------------------------------------------
# Cameras and rings that come and go (sections 4.4 and 5.1)
# ---------------------------------------------------------------------------

def test_t_prv_14_a_new_camera(cleanup, writers):
    """T-PRV-14, section 4.4: two rings; after 1 s, add a third reader to the fake manager and write
    frames to it. The newest frame of the third camera arrives with no ready message, within 0.5 s
    after its first commit."""
    rings = fake_rings(cleanup, (A, B, C))
    manager = manager_with({A: rings[A].reader(), B: rings[B].reader()})
    with server(manager) as (_, client), client.websocket_connect(ROUTE) as session:
        ws = WsClient(session, answer={A, B})
        start_writers(writers, (rings[A], rings[B]))
        pump(ws, duration=1.0)
        client.portal.call(manager.add_reader, C, rings[C].reader())
        start_writers(writers, (rings[C],))
        pump(ws, until=lambda: ws.first(C), timeout=2.0, what="a camera message of the new camera")
    first_commit = rings[C].written[0]
    assert ws.first(C)[0] - first_commit <= 0.5, f"{ws.first(C)[0] - first_commit:.2f} s after the first commit"


@pytest.mark.parametrize("answered", [True, False], ids=["answered", "not answered"])
def test_t_prv_15_ring_recreated(cleanup, writers, answered):
    """T-PRV-15, sections 4.2 and 4.4 [agent 12]: ring A at frame 500, sent. (1) The client has answered;
    replace A's reader with a new ring at frames 0 to 3. (2) The client has not answered; replace it
    in the same way, then answer within 0.5 s of the last camera message for A (before the safety net).

    (1) The next camera message for A has frame 3 of the new ring. (2) No camera message for A before
    the answer; then frame 3 or newer of the new ring. B continues in both cases (the rule of
    T-CAP-86): at least 8 camera messages in the 0.5 s after the new frame of A."""
    rings = fake_rings(cleanup, (A, B))
    rings[A].write_range(0, 500)
    new_a = FakeRing(cleanup, A, CAMERA_INDEX_BASE, tag=9)
    new_a.write_range(0, 3)
    manager = manager_with({cid: r.reader() for cid, r in rings.items()})
    with server(manager) as (_, client), client.websocket_connect(ROUTE) as session:
        ws = WsClient(session, answer={B})
        start_writers(writers, (rings[B],))
        t_first = first_messages(ws, (A,), timeout=2.0)[A]
        assert ws.frames(A) == [500]
        if answered:
            ws.send_ready(A)
            pump(ws, duration=0.05)
        client.portal.call(manager.replace_reader, A, new_a.reader())
        if not answered:
            pump(ws, duration=t_first + 0.3 - time.monotonic())
            assert ws.frames(A) == [500], "a camera message for A before the answer"
            ws.send_ready(A)
        pump(ws, until=lambda: len(ws.camera[A]) >= 2, timeout=t_first + 0.9 - time.monotonic(),
             what="the next camera message for A, before its safety net")
        t_new = ws.times(A)[1]
        pump(ws, duration=0.5)
    message = ws.camera[A][1][1]
    assert tag_of(message) == new_a.tag and message.arrival_ns == new_a.arrival(message.frame_number)
    if answered:
        assert message.frame_number == 3
    else:
        assert message.frame_number >= 3
    assert len(ws.frames(B, since=t_new)) >= 8, f"camera {B}: {len(ws.frames(B, since=t_new))} camera messages"


def test_t_prv_16_a_camera_stops(cleanup, writers):
    """T-PRV-16, section 4.4: two rings at 30 fps; A's writer stops (a failed or dead camera); the client
    answers at once. After A's last frame, no camera message for A in 2 s; B gets at least 30 camera
    messages in those 2 s."""
    rings = fake_rings(cleanup, (A, B))
    last_a = 30
    with server(manager_with({cid: r.reader() for cid, r in rings.items()})) as (_, client), \
            client.websocket_connect(ROUTE) as session:
        ws = WsClient(session, answer=True)
        writers.append(PacedWriter(rings[A], stop_after=last_a).start_thread())
        start_writers(writers, (rings[B],))
        pump(ws, until=lambda: last_a in ws.frames(A), timeout=3.0, what="the last frame of A")
        t_last = ws.camera[A][-1][0]
        pump(ws, duration=t_last + 2.0 - time.monotonic())
    assert ws.frames(A, since=t_last + 1e-6) == [], "a camera message for A after its last frame"
    assert len(ws.frames(B, t_last, t_last + 2.0)) >= 30


def test_t_prv_17_reader_removed_then_closed(cleanup, writers, caplog):
    """T-PRV-17, sections 4.1, 4.4 and 5.1 [agent 21]: remove A's reader from the fake manager, then
    close it, as `_close_rings` does; then send a ready message for A. No exception; no camera message
    for A; no log record at WARNING or above; B continues.

    "No camera message for A": no message of a frame of A written after the removal. "B continues":
    at least 15 camera messages of B in the next 1 s."""
    rings = fake_rings(cleanup, (A, B))
    manager = manager_with({cid: r.reader() for cid, r in rings.items()})
    with server(manager) as (app, client), client.websocket_connect(ROUTE) as session:
        ws = WsClient(session, answer=True)
        start_writers(writers, rings.values())
        pump(ws, until=lambda: len(ws.camera[A]) >= 3 and len(ws.camera[B]) >= 3, timeout=3.0, what="3 messages each")
        client.portal.call(manager.remove_reader, A)
        t_removed = time.monotonic()
        ws.send_ready(A)
        pump(ws, duration=1.0)
        assert not app.state.run_tasks[0].done(), "PreviewRelay.run ended"
    late = [k for k in ws.frames(A) if rings[A].written.get(k, 0) > t_removed]
    assert late == [], f"camera messages for A after the removal: {late}"
    assert warnings_or_above(caplog) == []
    assert len([k for k in ws.frames(B) if rings[B].written[k] > t_removed]) >= 15
