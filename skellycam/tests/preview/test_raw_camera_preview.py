"""A guard of the step 4b code lane, with no T-ID (specs/preview-4b.md 7.4): the JPEGs of a raw camera reach the
preview like any other.

capture-fake. A YUY2 or an NV12 fake camera (step 3b, `windows-capture.md` 22) opens its raw mode; the capture loop
encodes each frame to JPEG and writes it to the ring. Real: `CameraGroupManager`, `CameraGroup`, the ring and
`PreviewRelay`, with fake send functions that answer each camera message at once. Each camera message holds a JPEG
that decodes at the size of the camera.
"""

import threading
import time

import cv2
import numpy as np
import pytest

from skellycam.tests.capture.capture_session import capture_app, ready_app_steps
from skellycam.tests.capture.test_uncompressed import H, W, raw_camera
from skellycam.tests.capture.uncompressed import RAW_FORMATS, QuickSyncFake
from skellycam.tests.preview.preview_helpers import parse_camera_message, preview, ready_text


@pytest.mark.parametrize("fmt", RAW_FORMATS)
def test_the_jpegs_of_a_raw_camera_reach_the_preview(monkeypatch, fmt):
    with capture_app(monkeypatch, [raw_camera(fmt)], full_modes=True) as app:
        QuickSyncFake(monkeypatch, available=False)
        camera_id = app.factory.camera_ids[0]
        ready_app_steps(app, [app.config(camera_id, capture_fourcc=fmt)])
        assert app.status(camera_id)["mode"]["format"] == fmt
        portal = app.client.portal
        messages = []
        relay = None
        done = threading.Event()

        async def send_bytes(data):
            messages.append(parse_camera_message(data))
            relay.handle_text(ready_text(camera_id))
            if len(messages) >= 10:
                done.set()

        async def send_json(data):
            pass

        relay = preview().PreviewRelay(app.manager, send_bytes, send_json)
        run = portal.start_task_soon(relay.run)
        try:
            assert done.wait(30), f"{len(messages)} camera messages of the {fmt} camera in 30 s"
        finally:
            run.cancel()
            time.sleep(0.05)
    assert {m.camera_id for m in messages} == {camera_id}
    for m in messages[:10]:
        assert m.jpeg[:2] == b"\xff\xd8", "the camera message holds no JPEG"
        image = cv2.imdecode(np.frombuffer(m.jpeg, np.uint8), cv2.IMREAD_COLOR)
        assert image is not None and image.shape == (H, W, 3)
