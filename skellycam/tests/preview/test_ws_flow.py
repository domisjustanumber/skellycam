"""The sender through a websocket: T-PRV-02, T-PRV-04 to T-PRV-17 and T-PRV-54 (specs/preview.md, sections 3
to 5).

ws tests. A Starlette test client connects to the test route of `preview_helpers`, which wires
`PreviewRelay` to the websocket as 4b will. Paced writer threads write fake rings at 30 fps. Changes
to the fake manager run on the event-loop thread of the server (`client.portal.call`), as
`CameraGroup` makes them. The pass thresholds are those of section 9.2 [agent 23].

A share of frames and a count of camera messages in a window are `pace` tests (9.1; Q669 and Q670 of the user
[ADR-F4N7]): each is split from its blocking test on one run (`one_run`). In place of the share, the blocking test
checks that an answered camera gets more camera messages than the safety net can give; in place of the count, it
waits for the n-th camera message with a loose limit [ADR-B7YV].
"""

import contextlib
import logging
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from skellycam.tests.frame_ring.ring_spec import ring
from skellycam.tests.preview.preview_helpers import (
    CAMERA_INDEX_BASE, HEADER_SIZE, ROUTE, FakeRing, PacedWriter, WsClient, manager_with, preview_app, pump,
    run_errors, tag_of)
from skellycam.tests.pace import bound, one_run

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


SHARE = 0.8  # of the frames written: 9.2; on CI the margin makes it 40 % (Q670) [ADR-F4N7]


def assert_share(ws, fake_ring, t0, t1):
    """The `pace` check of a share of frames (9.1): `SHARE` on a real machine, 1 - (1 - `SHARE`) x the margin on CI."""
    share = bound(1.0, SHARE)
    written = fake_ring.written_between(t0, t1)
    got = received_in_window(ws, fake_ring.camera_id, t0, t1) & set(written)
    assert len(got) >= share * len(written), (
        f"camera {fake_ring.camera_id}: {len(got)} of {len(written)} frames written in {t1 - t0:.1f} s")


def assert_more_than_the_safety_net(ws, camera_id, seconds):
    """The blocking check in place of a share (9.1) [ADR-B7YV]: an answered camera gets more camera messages than the
    safety net can give in `seconds` (the first message, then one each second, plus one)."""
    count = len(ws.camera[camera_id])
    assert count > seconds + 2, f"camera {camera_id}: {count} camera messages in {seconds:.1f} s: only the safety net"


def assert_nth_message_within(ws, camera_id, since, n, strict_s):
    """The `pace` check of a count of camera messages in a window (9.1) [ADR-B7YV]: the n-th camera message after
    `since` comes within `strict_s`. The nominal time is n frame periods; the margin multiplies the rest."""
    times = [t for t in ws.times(camera_id) if t >= since]
    assert len(times) >= n, f"camera {camera_id}: {len(times)} camera messages, not {n}"
    took = times[n - 1] - since
    assert took <= bound(n / 30, strict_s), f"camera {camera_id}: camera message {n} came {took:.2f} s later"


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


def _t_prv_05_run(cleanup, writers, caplog):
    ids = ["a1b2", "abcdefghijklmnop", "abcdefghijklmnopq", "cámara"]
    rings = fake_rings(cleanup, ids)
    with server(manager_with({cid: r.reader() for cid, r in rings.items()})) as (_, client), \
            client.websocket_connect(ROUTE) as session:
        ws = WsClient(session, answer=True)
        t0 = time.monotonic()
        start_writers(writers, rings.values())
        pump(ws, duration=1.5)
        t1 = time.monotonic()
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    return SimpleNamespace(ids=ids, rings=rings, ws=ws, t0=t0, t1=t1, errors=errors)


def test_t_prv_05_camera_ids_that_do_not_fit(cleanup, writers, caplog):
    """T-PRV-05, section 3.3 [agent 4]: camera ids `a1b2`, `abcdefghijklmnop` (16),
    `abcdefghijklmnopq` (17) and `cámara`. The first two are sent, NUL-padded to 16 bytes; the last
    two get no camera message and one ERROR record each for the connection; the first two are not
    affected.

    The ring tag in each JPEG tells which ring a message comes from (a cut id of 17 bytes would read
    as the id of 16 bytes). "Not affected", blocking: more camera messages than the safety net gives; the share
    of 80 % of their frames in 1.5 s is `test_t_prv_05_the_cameras_that_fit_get_their_share` (9.1)."""
    run = one_run("T-PRV-05", lambda: _t_prv_05_run(cleanup, writers, caplog))
    by_tag = {}
    for messages in run.ws.camera.values():
        for _, message in messages:
            by_tag.setdefault(tag_of(message), []).append(message)
    good, bad = [run.rings[cid] for cid in run.ids[:2]], [run.rings[cid] for cid in run.ids[2:]]
    for fake_ring in bad:
        assert fake_ring.tag not in by_tag, f"camera {fake_ring.camera_id!r} got a camera message"
    for fake_ring in good:
        assert {m.camera_id_raw for m in by_tag.get(fake_ring.tag, [])} == {fake_ring.camera_id.encode().ljust(16, b"\0")}
        assert_more_than_the_safety_net(run.ws, fake_ring.camera_id, run.t1 - run.t0)
    assert len(run.errors) == 2, run.errors
    for fake_ring in bad:
        assert len([e for e in run.errors if fake_ring.camera_id in e]) == 1, (fake_ring.camera_id, run.errors)


@pytest.mark.pace  # Q670: a share of frames depends on the pace; 80 % on a real machine, 40 % on CI
def test_t_prv_05_the_cameras_that_fit_get_their_share(cleanup, writers, caplog):
    """T-PRV-05, the share: the two cameras that fit get at least 80 % of their frames in 1.5 s (9.1)."""
    run = one_run("T-PRV-05", lambda: _t_prv_05_run(cleanup, writers, caplog))
    for cid in run.ids[:2]:
        assert_share(run.ws, run.rings[cid], run.t0, run.t1)


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


def _answered_run(cleanup, writers, cameras, answer, seconds):
    """Rings of `cameras` at 30 fps for `seconds`; the client answers at once for `answer` (`True`: each camera)."""
    rings = fake_rings(cleanup, cameras)
    with server(manager_with({cid: r.reader() for cid, r in rings.items()})) as (_, client), \
            client.websocket_connect(ROUTE) as session:
        ws = WsClient(session, answer=answer)
        t0 = time.monotonic()
        start_writers(writers, rings.values())
        pump(ws, duration=seconds)
        t1 = time.monotonic()
    return SimpleNamespace(rings=rings, ws=ws, t0=t0, t1=t1)


def test_t_prv_09_a_camera_with_no_answer_does_not_hold_back_the_others(cleanup, writers):
    """T-PRV-09, sections 4.3 and 4.4 [P2, A6]: three rings at 30 fps for 5 s; the client answers at once
    for cameras A and B; it never answers for camera C. A and B are not held back: blocking, each gets more camera
    messages than the safety net gives (the share of 80 % is
    `test_t_prv_09_the_answered_cameras_get_their_share`, 9.1); C gets 4 to 7 camera messages (the safety net)."""
    run = one_run("T-PRV-09", lambda: _answered_run(cleanup, writers, (A, B, C), {A, B}, 5.0))
    assert_more_than_the_safety_net(run.ws, A, run.t1 - run.t0)
    assert_more_than_the_safety_net(run.ws, B, run.t1 - run.t0)
    assert 4 <= len(run.ws.camera[C]) <= 7, f"camera {C}: {len(run.ws.camera[C])} camera messages"


@pytest.mark.pace  # Q670: a share of frames depends on the pace; 80 % on a real machine, 40 % on CI
def test_t_prv_09_the_answered_cameras_get_their_share(cleanup, writers):
    """T-PRV-09, the share: A and B each get at least 80 % of the frames written in the 5 s (9.1)."""
    run = one_run("T-PRV-09", lambda: _answered_run(cleanup, writers, (A, B, C), {A, B}, 5.0))
    assert_share(run.ws, run.rings[A], run.t0, run.t1)
    assert_share(run.ws, run.rings[B], run.t0, run.t1)


def test_t_prv_10_four_cameras_that_keep_up(cleanup, writers):
    """T-PRV-10, sections 4.3 and 8.4: four rings at 30 fps for 10 s; the client answers at once.
    `frame_number` increases in the camera messages of each camera; each camera gets more camera messages than the
    safety net gives. The share of 80 % is `test_t_prv_10_each_camera_gets_its_share` (9.1)."""
    run = one_run("T-PRV-10", lambda: _answered_run(cleanup, writers, (A, B, C, D), True, 10.0))
    for cid in run.rings:
        frames = run.ws.frames(cid)
        assert all(b > a for a, b in zip(frames, frames[1:])), f"camera {cid}: frame numbers do not increase"
        assert_more_than_the_safety_net(run.ws, cid, run.t1 - run.t0)


@pytest.mark.pace  # Q670: a share of frames depends on the pace; 80 % on a real machine, 40 % on CI
def test_t_prv_10_each_camera_gets_its_share(cleanup, writers):
    """T-PRV-10, the share: each camera gets at least 80 % of its frames in the 10 s (9.1)."""
    run = one_run("T-PRV-10", lambda: _answered_run(cleanup, writers, (A, B, C, D), True, 10.0))
    for fake_ring in run.rings.values():
        assert_share(run.ws, fake_ring, run.t0, run.t1)


AHEAD = 5  # T-PRV-54: the frames that each ring writes after a camera message, before the answer [ADR-B7YV]


def test_t_prv_54_the_next_message_after_an_answer_holds_the_newest_frame(cleanup, writers):
    """T-PRV-54, section 4.3 (Q670 of the user) [ADR-F4N7]: four rings at 30 fps for 5 s; the client answers late.
    After each camera message, the writer of that ring writes `AHEAD` more frames and pauses, as in T-PRV-07; then
    the client answers. While the writer pauses, the newest frame at the send is the pause frame. After each answer,
    the next camera message of that camera holds the newest frame at the send or one older: its `frame_number` is at
    least the pause frame minus 1. A sender that sends the next frame in sequence, or a frame two older than the
    newest, fails [ADR-B7YV]. `frame_number` increases; each camera gets more camera messages than the safety net
    gives. The rule does not depend on the pace: blocking."""
    cameras = (A, B, C, D)
    rings = fake_rings(cleanup, cameras)
    paused_at = {cid: [] for cid in cameras}  # the pause frame of the ring at each answer
    with server(manager_with({cid: r.reader() for cid, r in rings.items()})) as (_, client), \
            client.websocket_connect(ROUTE) as session:
        ws = WsClient(session)
        paced = {cid: PacedWriter(rings[cid], stop_after=0).start_thread() for cid in cameras}
        writers.extend(paced.values())
        first_messages(ws, cameras, timeout=2.0)
        t0 = time.monotonic()
        while time.monotonic() < t0 + 5.0:
            counts = {cid: len(ws.camera[cid]) for cid in cameras}
            for cid in cameras:
                paced[cid].stop_after = ws.frames(cid)[-1] + AHEAD
            pump(ws, until=lambda: all(rings[cid].last == paced[cid].stop_after for cid in cameras), timeout=2.0,
                 what="the pause frame of each ring")
            assert {cid: len(ws.camera[cid]) for cid in cameras} == counts, (
                "a camera message before the answer: the writers were too slow for the safety net")
            for cid in cameras:
                paused_at[cid].append(rings[cid].last)
                ws.send_ready(cid)
            pump(ws, until=lambda: all(len(ws.camera[cid]) > counts[cid] for cid in cameras), timeout=2.0,
                 what="the answer of each camera")
        t1 = time.monotonic()
    for cid in cameras:
        frames = ws.frames(cid)
        assert len(frames) == len(paused_at[cid]) + 1, (cid, len(frames), len(paused_at[cid]))
        old = [(p, f) for p, f in zip(paused_at[cid], frames[1:]) if f < p - 1]
        assert old == [], f"camera {cid}: (the pause frame at the answer, the next camera message): {old[:5]}"
        assert all(b > a for a, b in zip(frames, frames[1:])), f"camera {cid}: frame numbers do not increase"
        assert_more_than_the_safety_net(ws, cid, t1 - t0)


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


def _t_prv_13_run(cleanup, writers):
    rings = fake_rings(cleanup, (A, B))
    with server(manager_with({cid: r.reader() for cid, r in rings.items()})) as (_, client), \
            client.websocket_connect(ROUTE) as session1, client.websocket_connect(ROUTE) as session2:
        ws1, ws2 = WsClient(session1, answer=True), WsClient(session2)
        t0 = time.monotonic()
        start_writers(writers, rings.values())
        pump([ws1, ws2], duration=5.0)
        t1 = time.monotonic()
    return SimpleNamespace(rings=rings, ws1=ws1, ws2=ws2, t0=t0, t1=t1)


def test_t_prv_13_two_clients(cleanup, writers):
    """T-PRV-13, section 4.4 [agent 17]: two clients on two rings at 30 fps for 5 s. Client 1 answers at
    once; client 2 never. Client 2 does not hold back client 1: blocking, client 1 gets more camera messages than
    the safety net gives (the share of 80 % is `test_t_prv_13_client_1_gets_its_share`, 9.1); client 2 gets only
    safety-net camera messages (4 to 7 per camera)."""
    run = one_run("T-PRV-13", lambda: _t_prv_13_run(cleanup, writers))
    for cid in run.rings:
        assert_more_than_the_safety_net(run.ws1, cid, run.t1 - run.t0)
        assert 4 <= len(run.ws2.camera[cid]) <= 7, f"client 2, camera {cid}: {len(run.ws2.camera[cid])} camera messages"


@pytest.mark.pace  # Q670: a share of frames depends on the pace; 80 % on a real machine, 40 % on CI
def test_t_prv_13_client_1_gets_its_share(cleanup, writers):
    """T-PRV-13, the share: client 1 gets at least 80 % of the frames in the 5 s (9.1)."""
    run = one_run("T-PRV-13", lambda: _t_prv_13_run(cleanup, writers))
    for fake_ring in run.rings.values():
        assert_share(run.ws1, fake_ring, run.t0, run.t1)


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


def _t_prv_15_run(cleanup, writers, answered):
    rings = fake_rings(cleanup, (A, B))
    rings[A].write_range(0, 500)
    new_a = FakeRing(cleanup, A, CAMERA_INDEX_BASE, tag=9)
    new_a.write_range(0, 3)
    manager = manager_with({cid: r.reader() for cid, r in rings.items()})
    before_answer = None
    with server(manager) as (_, client), client.websocket_connect(ROUTE) as session:
        ws = WsClient(session, answer={B})
        start_writers(writers, (rings[B],))
        t_first = first_messages(ws, (A,), timeout=2.0)[A]
        first_frames = ws.frames(A)
        if answered:
            ws.send_ready(A)
            pump(ws, duration=0.05)
        client.portal.call(manager.replace_reader, A, new_a.reader())
        if not answered:
            pump(ws, duration=t_first + 0.3 - time.monotonic())
            before_answer = ws.frames(A)
            ws.send_ready(A)
        pump(ws, until=lambda: len(ws.camera[A]) >= 2, timeout=t_first + 0.9 - time.monotonic(),
             what="the next camera message for A, before its safety net")
        t_new = ws.times(A)[1]
        # 8 camera messages of B after the new frame of A: a loose limit (10 times the window of 0.5 s) [ADR-B7YV]
        pump(ws, until=lambda: len(ws.frames(B, since=t_new)) >= 8, timeout=5.0, what="8 camera messages of B")
    message = ws.camera[A][1][1]
    return SimpleNamespace(ws=ws, new_a=new_a, message=message, first_frames=first_frames,
                           before_answer=before_answer, t_new=t_new)


@pytest.mark.parametrize("answered", [True, False], ids=["answered", "not answered"])
def test_t_prv_15_ring_recreated(cleanup, writers, answered):
    """T-PRV-15, sections 4.2 and 4.4 [agent 12]: ring A at frame 500, sent. (1) The client has answered;
    replace A's reader with a new ring at frames 0 to 3. (2) The client has not answered; replace it
    in the same way, then answer within 0.5 s of the last camera message for A (before the safety net).

    (1) The next camera message for A has frame 3 of the new ring. (2) No camera message for A before
    the answer; then frame 3 or newer of the new ring. B continues in both cases (the rule of
    T-CAP-86): blocking, 8 camera messages after the new frame of A, with a loose limit; within 0.5 s is
    `test_t_prv_15_b_gets_8_messages_within_0_5_s` (9.1)."""
    run = one_run(("T-PRV-15", answered), lambda: _t_prv_15_run(cleanup, writers, answered))
    assert run.first_frames == [500]
    if not answered:
        assert run.before_answer == [500], "a camera message for A before the answer"
    assert tag_of(run.message) == run.new_a.tag and run.message.arrival_ns == run.new_a.arrival(run.message.frame_number)
    if answered:
        assert run.message.frame_number == 3
    else:
        assert run.message.frame_number >= 3
    assert len(run.ws.frames(B, since=run.t_new)) >= 8


@pytest.mark.pace  # Q669: a count of camera messages in a window depends on the pace
@pytest.mark.parametrize("answered", [True, False], ids=["answered", "not answered"])
def test_t_prv_15_b_gets_8_messages_within_0_5_s(cleanup, writers, answered):
    """T-PRV-15, the count: B gets 8 camera messages within 0.5 s after the new frame of A (9.1) [ADR-B7YV]. A CI
    run on macOS: 5 in 0.5 s (CI run 45401541234)."""
    run = one_run(("T-PRV-15", answered), lambda: _t_prv_15_run(cleanup, writers, answered))
    assert_nth_message_within(run.ws, B, run.t_new, 8, 0.5)


def _t_prv_16_run(cleanup, writers):
    rings = fake_rings(cleanup, (A, B))
    last_a = 30
    with server(manager_with({cid: r.reader() for cid, r in rings.items()})) as (_, client), \
            client.websocket_connect(ROUTE) as session:
        ws = WsClient(session, answer=True)
        writers.append(PacedWriter(rings[A], stop_after=last_a).start_thread())
        start_writers(writers, (rings[B],))
        pump(ws, until=lambda: last_a in ws.frames(A), timeout=3.0, what="the last frame of A")
        t_last = ws.camera[A][-1][0]
        # 2 s with no message for A, and 30 camera messages of B: a loose limit (10 times the window) [ADR-B7YV]
        pump(ws, until=lambda: time.monotonic() >= t_last + 2.0 and len(ws.frames(B, since=t_last)) >= 30,
             timeout=t_last + 20.0 - time.monotonic(), what="2 s and 30 camera messages of B")
    return SimpleNamespace(ws=ws, t_last=t_last)


def test_t_prv_16_a_camera_stops(cleanup, writers):
    """T-PRV-16, section 4.4: two rings at 30 fps; A's writer stops (a failed or dead camera); the client
    answers at once. After A's last frame, no camera message for A in 2 s; B continues: blocking, 30 camera messages
    with a loose limit; within those 2 s is `test_t_prv_16_b_gets_30_messages_within_2_s` (9.1)."""
    run = one_run("T-PRV-16", lambda: _t_prv_16_run(cleanup, writers))
    assert run.ws.frames(A, since=run.t_last + 1e-6) == [], "a camera message for A after its last frame"
    assert len(run.ws.frames(B, since=run.t_last)) >= 30


@pytest.mark.pace  # Q669: a count of camera messages in a window depends on the pace
def test_t_prv_16_b_gets_30_messages_within_2_s(cleanup, writers):
    """T-PRV-16, the count: B gets 30 camera messages within 2 s after A's last frame (9.1) [ADR-B7YV]. A CI run on
    macOS: 19 in 2 s (CI run 45401541234)."""
    run = one_run("T-PRV-16", lambda: _t_prv_16_run(cleanup, writers))
    assert_nth_message_within(run.ws, B, run.t_last, 30, 2.0)


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
