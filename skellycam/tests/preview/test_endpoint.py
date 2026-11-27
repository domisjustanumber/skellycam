"""The product endpoint sends camera messages: T-PRV-26 to T-PRV-28 (specs/preview-4b.md 4.1, 4.2, 7.4).

ws tests. The Starlette test client connects to the product route `/skellycam/websocket/connect` of the `app`
fixture of `skellycam/tests/conftest.py`. Real: the route, `WebsocketServer`, `PreviewRelay` and the ring package.
Fake: the manager of `preview_helpers.py` (also a `CameraGroupManager`, for the beartype check of
`WebsocketServer`), patched in as the `app` fixture patches its manager, and paced writers.

A share of frames is a `pace` test (Q669, Q670 [ADR-F4N7]): T-PRV-26 is split on one run, as the 4a ws tests are.
"""

import logging
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from skellycam.tests.pace import one_run
from skellycam.tests.preview.preview_helpers import (
    PERIOD_NS, FakeGroup, FakeManager, FakeRing, PacedWriter, WsClient, pump, ready_text)
from skellycam.tests.preview.test_ws_flow import assert_more_than_the_safety_net, assert_share, fake_rings

ENDPOINT = "/skellycam/websocket/connect"
A, B, C, D = "a1b2", "c3d4", "e5f6", "a7b8"
KIYO_PRO_1080P_JPEG = 607_032  # bytes: the largest real 1080p JPEG of the Kiyo Pro [4a 8.1]


def endpoint_manager():
    """The fake manager of `preview_helpers.py`, also a `CameraGroupManager`, with a constant `to_state_dict`."""
    from skellycam.core.camera_group.camera_group_manager import CameraGroupManager

    class EndpointManager(FakeManager, CameraGroupManager):
        def __init__(self):
            FakeManager.__init__(self, FakeGroup("g1"))

        def __repr__(self):
            return f"EndpointManager({list(self.group().ring_readers)})"

        def to_state_dict(self):
            return {"camera_groups": {"g1": {"id": "g1", "configs": {}, "alive": True, "recording_in_progress": False,
                                             "cameras": {cid: {"alive": True, "status": {"state": "ready",
                                                                                         "replaced_count": 0}}
                                                         for cid in self.group().ring_readers}}}}

    return EndpointManager()


@pytest.fixture()
def mock_camera_group_manager():
    """Replaces the MagicMock manager of the `app` fixture with the fake manager of the preview tests."""
    return endpoint_manager()


@pytest.fixture()
def servers(monkeypatch):
    """Each `WebsocketServer` that the endpoint makes."""
    from skellycam.api.websocket.websocket_server import WebsocketServer

    made, init = [], WebsocketServer.__init__

    def recording_init(self, *args, **kwargs):
        init(self, *args, **kwargs)
        made.append(self)

    monkeypatch.setattr(WebsocketServer, "__init__", recording_init)
    return made


def errors_of(caplog):
    return [f"{r.name}: {r.getMessage()}" for r in caplog.records if r.levelno >= logging.ERROR]


def framerate_updates(ws):
    return [m for _, m in ws.json if m.get("message_type") == "framerate_update"]


# ---------------------------------------------------------------------------
# T-PRV-26
# ---------------------------------------------------------------------------

def _t_prv_26_run(app, manager, cleanup, writers):
    rings = fake_rings(cleanup, (A, B))
    for cid, fake_ring in rings.items():
        manager.add_reader(cid, fake_ring.reader())
    with TestClient(app) as client, client.websocket_connect(ENDPOINT) as session:
        ws = WsClient(session, answer=True)
        t0 = time.monotonic()
        for fake_ring in rings.values():
            writers.append(PacedWriter(fake_ring, fps=30).start_thread())
        pump(ws, duration=1.0)
        session.send_text("ping")
        pump(ws, duration=2.0)
        t1 = time.monotonic()
    payload_problems = [f"{cid} {m.frame_number}" for cid, messages in ws.camera.items() for _, m in messages
                        if cid in rings and m.jpeg != rings[cid].payload(m.frame_number)]
    return SimpleNamespace(rings=rings, ws=ws, t0=t0, t1=t1, payload_problems=payload_problems)


def test_t_prv_26_the_product_endpoint_sends_camera_messages(app, mock_camera_group_manager, cleanup, writers):
    """T-PRV-26 (4.1): connect to the product route; answer each camera message at once; `ping` after 1 s; run 3 s.
    Each JPEG equals the ring payload; one `app_state` message arrives; each `framerate_update` has `cameras` with
    both ids and no `backend_framerate` key; `pong` arrives. Blocking half: each camera gets more camera messages
    than the safety net gives; the share of 80 % is `test_t_prv_26_each_camera_gets_its_share` (9.1)."""
    run = one_run("T-PRV-26", lambda: _t_prv_26_run(app, mock_camera_group_manager, cleanup, writers))
    for cid in run.rings:
        assert_more_than_the_safety_net(run.ws, cid, run.t1 - run.t0)
    assert run.payload_problems == []
    app_states = [m for _, m in run.ws.json if m.get("message_type") == "app_state"]
    assert len(app_states) == 1, f"{len(app_states)} app_state messages"
    updates = framerate_updates(run.ws)
    assert updates, "no framerate_update"
    for update in updates:
        assert "backend_framerate" not in update and "frontend_framerate" not in update, update
        assert set(update.get("cameras", {})) == {A, B}, update
    assert [text for _, text in run.ws.texts] == ["pong"]


@pytest.mark.pace  # Q670: a share of frames depends on the pace; 80 % on a real machine, 40 % on CI
def test_t_prv_26_each_camera_gets_its_share(app, mock_camera_group_manager, cleanup, writers):
    """T-PRV-26, the share: each camera gets at least 80 % of its frames (9.1)."""
    run = one_run("T-PRV-26", lambda: _t_prv_26_run(app, mock_camera_group_manager, cleanup, writers))
    for fake_ring in run.rings.values():
        assert_share(run.ws, fake_ring, run.t0, run.t1)


# ---------------------------------------------------------------------------
# T-PRV-27
# ---------------------------------------------------------------------------

def test_t_prv_27_old_and_bad_client_texts(app, mock_camera_group_manager, cleanup, writers, caplog):
    """T-PRV-27 (4.1 items 3, 4): with one ring at 30 fps, send `{"frameNumber": 3, "displayImageSizes": null}`,
    `{not json`, a ready message with a camera id that is not a string, then `ping`. `pong` arrives; the connection
    stays open; camera messages continue; the global kill flag stays False; no record at ERROR."""
    a = FakeRing(cleanup, A)
    mock_camera_group_manager.add_reader(A, a.reader())
    with TestClient(app) as client, client.websocket_connect(ENDPOINT) as session:
        ws = WsClient(session, answer=True)
        writers.append(PacedWriter(a, fps=30).start_thread())
        pump(ws, until=lambda: len(ws.camera[A]) >= 1, timeout=5.0, what="the first camera message")
        for text in ('{"frameNumber": 3, "displayImageSizes": null}', "{not json",
                     '{"message_type": "camera_ready", "camera_id": 7}', "ping"):
            session.send_text(text)
        sent_at = time.monotonic()
        pump(ws, until=lambda: any(text == "pong" for _, text in ws.texts), timeout=5.0, what="pong")
        pump(ws, until=lambda: len(ws.frames(A, since=sent_at)) >= 5, timeout=5.0,
             what="camera messages after the texts")
        session.send_text(ready_text(A))  # the connection still takes texts
        pump(ws, duration=0.2)
    assert not app.state.global_kill_flag.value, "the global kill flag is set"
    assert errors_of(caplog) == []


# ---------------------------------------------------------------------------
# T-PRV-28
# ---------------------------------------------------------------------------

def big_payload(fake_ring, k):
    return fake_ring.payload(k)[:16].ljust(KIYO_PRO_1080P_JPEG, bytes([k % 251]))


def test_t_prv_28_the_tasks_end_after_a_close(app, mock_camera_group_manager, cleanup, writers, servers, caplog):
    """T-PRV-28 (4.2): four rings at 60 fps with payloads of 607,032 bytes; the client answers at once; close the
    client after 2 s. Each task of `WebsocketServer` has ended within 1 s of the close; the global kill flag stays
    False; no record at ERROR."""
    rings = {cid: FakeRing(cleanup, cid, 60 + i, fps=60, tag=i + 1, width=1920, height=1080,
                           period_ns=PERIOD_NS // 2) for i, cid in enumerate((A, B, C, D))}
    for cid, fake_ring in rings.items():
        mock_camera_group_manager.add_reader(cid, fake_ring.reader())
    with TestClient(app) as client:
        with client.websocket_connect(ENDPOINT) as session:
            ws = WsClient(session, answer=True)
            for fake_ring in rings.values():
                writers.append(PacedWriter(fake_ring, fps=60,
                                           script=lambda k, r=fake_ring: {"payload": big_payload(r, k)}).start_thread())
            pump(ws, duration=2.0)
            assert len(servers) == 1, f"{len(servers)} websocket servers"
            tasks = servers[0].ws_tasks
            assert len(tasks) == 4, [t.get_name() for t in tasks]
            # the close of the client only: the exit of the TestClient context would cancel each task itself
            session.close(1000)
            closed_at = time.monotonic()
            while time.monotonic() < closed_at + 1.0 and not all(t.done() for t in tasks):
                time.sleep(0.01)
            still_running = [t.get_name() for t in tasks if not t.done()]
        assert still_running == [], "tasks still running 1 s after the close"
    assert any(ws.camera[cid] for cid in rings), "no camera message in 2 s"
    assert not app.state.global_kill_flag.value, "the global kill flag is set"
    assert errors_of(caplog) == []
