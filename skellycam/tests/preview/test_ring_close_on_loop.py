"""T-PRV-29: each ring-reader close runs on the event loop [Q4] (specs/preview-4b.md 4.3, 7.4).

capture-fake. Real: `CameraGroupManager`, `CameraGroup` with its watch thread, the rings and `PreviewRelay`, with
fake send functions that record the messages. Fake: three fake sources of `skellycam/tests/capture/fake_source.py`,
made as `capture_app` of `capture_session.py` makes them. PROCESS workers: the end of camera B is the end of its
process (`os._exit(3)` at the next frame after `FakeLog.arm()`), which the watch thread sees.

The relay runs on the event loop of the test client, where the group starts, so the group's `_loop` is the loop of
the relay. This guard can pass before the code of 4b: fix F8 is in (4.3).
"""

import threading
import time

from skellycam.tests.capture.capture_session import capture_app
from skellycam.tests.capture.fake_source import FakeScript
from skellycam.tests.preview.preview_helpers import parse_camera_message, preview, ready_text

GAP_LIMIT_S = 2.0  # loose: "A and C get camera messages during the whole test", not a pace check


def test_t_prv_29_each_ring_reader_close_runs_on_the_event_loop(monkeypatch):
    """T-PRV-29: run the sender; when B has sent 3 frames (Q866), end the process of camera B, so that the watch
    thread acts; wait until the camera status of B changes; restart B; run 2 s more. Each `close` of a ring reader runs on the thread of the event
    loop; A and C get camera messages during the whole test; B's camera messages come from the new ring after the
    restart."""
    from skellycam.core.ipc.frame_ring.reader import FrameRingReader

    closes = []  # (thread ident, time)
    original_close = FrameRingReader.close

    def spy_close(self):
        closes.append((threading.get_ident(), time.monotonic()))
        return original_close(self)

    monkeypatch.setattr(FrameRingReader, "close", spy_close)
    scripts = [FakeScript(), FakeScript(on_arm="exit"), FakeScript()]
    with capture_app(monkeypatch, scripts, workers="process") as app:
        app.detect()
        a, b, c = app.factory.camera_ids
        assert app.apply([app.config(cid) for cid in (a, b, c)]).status_code == 200
        for cid in (a, b, c):
            app.wait_state(cid, "ready")

        portal = app.client.portal
        loop_thread = portal.call(threading.get_ident)
        received = {a: [], b: [], c: []}  # camera id -> [(time, frame number)]
        relay = None

        async def send_bytes(data):
            message = parse_camera_message(data)
            received.setdefault(message.camera_id, []).append((time.monotonic(), message.frame_number))
            relay.handle_text(ready_text(message.camera_id))

        async def send_json(data):
            pass

        relay = preview().PreviewRelay(app.manager, send_bytes, send_json)
        run = portal.start_task_soon(relay.run)
        try:
            app.wait(lambda: all(received[cid] for cid in (a, b, c)), "a camera message of each camera", 20)
            # Q866: B sends at least 3 frames first, so that a frame of the new ring is lower than the last old one
            app.wait(lambda: len(received[b]) >= 3, "three camera messages of B", 20)
            old_ring = app.ring_name(b)
            app.factory.logs[b].arm()
            app.wait_state(b, "dead", "failed", timeout=20)
            app.wait(lambda: closes, "a ring reader close after the end of B", 10)
            last_old = received[b][-1][1]
            restarted_at = time.monotonic()
            response = app.apply([app.config(cid) for cid in (a, b, c)], retry=[b])
            assert response.status_code == 200, response.text
            app.wait_state(b, "ready", timeout=20)
            assert app.ring_name(b) != old_ring, "B has no new ring after the restart"
            app.wait(lambda: any(t > restarted_at for t, _ in received[b]), "a camera message of B after the restart",
                     20)
            end = time.monotonic() + 2.0
            while time.monotonic() < end:
                time.sleep(0.05)
        finally:
            run.cancel()

    assert closes, "no ring reader closed"
    wrong = [ident for ident, _ in closes if ident != loop_thread]
    assert wrong == [], f"{len(wrong)} of {len(closes)} ring reader closes ran on a thread that is not the event loop"
    for cid in (a, c):
        times = [t for t, _ in received[cid]]
        gaps = [later - earlier for earlier, later in zip(times, times[1:])]
        assert max(gaps, default=0.0) <= GAP_LIMIT_S, f"camera {cid}: a gap of {max(gaps):.1f} s in its messages"
        assert times[-1] > end - GAP_LIMIT_S, f"camera {cid}: no camera message at the end"
    after = [k for t, k in received[b] if t > restarted_at]
    assert after and after[0] < last_old, f"B after the restart: frames {after[:5]}, last old frame {last_old}"
