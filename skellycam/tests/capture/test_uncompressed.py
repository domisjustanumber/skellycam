"""Step 3b: JPEG encode at capture for uncompressed modes (specs/windows-capture.md, sections 13 and
22; specs/frame-ring.md, section 8.7).

T-CAP-61 to T-CAP-67, T-CAP-70, T-CAP-71, T-CAP-89 and T-CAP-150 to T-CAP-153 (section 22.3). They run
on Windows, Linux and macOS, except T-CAP-151, which runs on Linux and macOS only. The tests come from
`dom/3bc-tests` (ADR-3WCA), ported to `dom/integration` with the choices of ADR-0Z2F.

The fake source gives synthetic YUY2 and NV12 frames (`uncompressed.synthetic_raw`). The session
tests run THREAD workers with a virtual clock (`capture_session`), and the detection result holds
the full mode list (`full_modes=True`, V1). `QuickSyncFake` replaces the Quick Sync check and
encoder of the product module `capture.encoder` (ADR-3WCA items 6 and 7): `available=False` gives the
`cv2.imencode` path, `available=True` a fake encoder that holds one frame, as Quick Sync at depth 2.
Thus no test needs an Intel GPU. No test measures time.
"""

import json
import logging
import re
import sys

import cv2
import numpy as np
import pytest

from skellycam.tests.capture.capture_session import (
    SOURCE_MODULE, CaptureApp, OpenCVFakeFactory, Spies, block_payloads, capture_app, capture_logs, product,
    ready_app_steps)
from skellycam.tests.capture.fake_source import FakeScript, FakeSource, VirtualClock
from skellycam.tests.capture.test_detection_and_modes import NATIVE_25
from skellycam.tests.capture.uncompressed import (
    Q90_TABLES, RAW_FORMATS, BgrImages, QuickSyncFake, full_range_to_bgr, is_quick_sync_jpeg, jpeg_chroma,
    jpeg_quant_tables, mean_difference, raw_shape, stop_line_count, synthetic_raw, to_bgr)

W, H = 320, 240
CLOSE = "/skellycam/camera/group/close/all"
MODES_MODULE = "skellycam.core.camera.capture.modes"
CHROMA = {"YUY2": "4:2:2", "NV12": "4:2:0"}


def ring_flags():
    from skellycam.core.ipc.frame_ring import FrameFlag

    return FrameFlag


def raw_camera(fmt="YUY2", **script):
    """A fake with an MJPG and a raw type of one size and rate (the MJPG type first, so that the
    raw type is native)."""
    return FakeScript(modes=((W, H, 30, 1, "MJPG"), (W, H, 30, 1, fmt)), **script)


def detail(response):
    return json.dumps(response.json().get("detail"))


def opens(app, camera_id):
    return app.factory.logs[camera_id].opens.value


def jpeg_encoder(app, camera_id):
    """The status field `jpeg_encoder` of V3 (8.4): "quick_sync", "cv2" or None."""
    status = app.status(camera_id)
    assert "jpeg_encoder" in status, "the status has no field jpeg_encoder (V3, 8.4)"
    return status["jpeg_encoder"]


def decode(jpeg):
    image = cv2.imdecode(np.frombuffer(bytes(jpeg), np.uint8), cv2.IMREAD_COLOR)
    assert image is not None, "the payload is not a JPEG"
    return image


def record_frames(app, spies, directory, name, camera_id, frames):
    """Record until the camera writer of the take got `frames` more frames of the camera, then stop."""
    before = len(spies.of("record", camera_id))
    response = app.record_start(directory, name)
    assert response.status_code == 200, response.text
    app.wait(lambda: len(spies.of("record", camera_id)) >= before + frames, f"{frames} recorded frames")
    response = app.record_stop()
    assert response.status_code == 200, response.text


RANGE_LINE = re.compile(r"input range\W+(limited|full)\b", re.IGNORECASE)


def range_values(logs, camera_id):
    """The range decisions that the log lines of a camera give (13.3; recorder.md 6.7: the log only):
    "input range", then "limited" or "full" (ADR-0Z2F item 4)."""
    return [match.group(1).lower() for m in logs.messages()
            if camera_id in m and (match := RANGE_LINE.search(m))]


# ---------------------------------------------------------------------------
# T-CAP-61: the choice of a raw type (13.1, V2)
# ---------------------------------------------------------------------------

NATIVE_61 = (
    (1280, 720, 30, 1, "NV12"),  # synthesized: immediately before the MJPG type of the same size and rate
    (1280, 720, 30, 1, "MJPG"),
    (1280, 720, 30, 1, "YUY2"),
    (640, 480, 30, 1, "MJPG"),
    (640, 480, 30, 1, "NV12"),  # native: it comes after the MJPG type
    (1920, 1080, 30, 1, "NV12"),  # native: the MJPG type after it has another rate
    (1920, 1080, 60, 1, "MJPG"),
    # for the auto rate of V2: each size also has MJPG at 30
    (960, 540, 30, 1, "MJPG"), (960, 540, 60, 1, "YUY2"), (960, 540, 30, 1, "YUY2"),
    (800, 600, 30, 1, "MJPG"), (800, 600, 60, 1, "YUY2"), (800, 600, 30000, 1001, "YUY2"),
    (1024, 768, 30, 1, "MJPG"), (1024, 768, 24, 1, "YUY2"), (1024, 768, 60, 1, "YUY2"),
    (320, 240, 30, 1, "MJPG"), (320, 240, 10, 1, "YUY2"),
)


def _open_format(fmt, width, height, framerate=30.0):
    source_module = product(SOURCE_MODULE)
    fake = FakeSource(FakeScript(modes=NATIVE_61), clock=VirtualClock())
    request = source_module.CaptureRequest(camera_id="0", width=width, height=height, framerate=framerate,
                                           capture_fourcc=fmt)
    return fake, request


def test_t_cap_61_native_raw_types_are_chosen():
    """T-CAP-61, sections 13.1, 7.4 and 7.5 [D19, agent 19, V2]: request YUY2 and NV12 where the fake
    lists native and synthesized types. Native types are chosen; a synthesized NV12 is never chosen; a
    missing format fails at `set mode`. An auto rate (-1 and 0) looks at the modes of the requested
    format: 30 if it has 30, else 29.97, else its highest rate at the floor or above; with none,
    `set mode` with "no mode at 30 fps or more"."""
    source_module = product(SOURCE_MODULE)
    for fmt, width, height in (("YUY2", 1280, 720), ("NV12", 640, 480), ("NV12", 1920, 1080)):
        fake, request = _open_format(fmt, width, height)
        opened = fake.open(request)
        assert (opened.width, opened.height, opened.fps_num, opened.fps_den, opened.format) == (width, height, 30, 1, fmt)
    for fmt, width, height in (("NV12", 1280, 720), ("YUY2", 1920, 1080), ("YUY2", 640, 480)):
        fake, request = _open_format(fmt, width, height)
        with pytest.raises(source_module.CaptureFailure) as failure:
            fake.open(request)
        assert failure.value.stage == "set mode", f"{fmt} {width}x{height}"
        assert "read_sample" not in fake.log.names(), f"a stream was started for {fmt} {width}x{height}"
    for auto in (-1.0, 0.0):
        for width, height, rate in ((960, 540, (30, 1)), (800, 600, (30000, 1001)), (1024, 768, (60, 1))):
            fake, request = _open_format("YUY2", width, height, auto)
            opened = fake.open(request)
            assert (opened.format, (opened.fps_num, opened.fps_den)) == ("YUY2", rate), f"auto at {width}x{height}"
        fake, request = _open_format("YUY2", 320, 240, auto)
        with pytest.raises(source_module.CaptureFailure) as failure:
            fake.open(request)
        assert (failure.value.stage, failure.value.reason) == ("set mode", "no mode at 30 fps or more")


# ---------------------------------------------------------------------------
# T-CAP-62: cv2.imencode, quality 90, the chroma of the source (13.2)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fmt", RAW_FORMATS)
def test_t_cap_62_cv2_jpeg_has_quality_90_and_the_chroma_of_the_source(monkeypatch, fmt):
    """T-CAP-62, section 13.2 [D2, notes: Encoder settings]: YUY2 and NV12 fakes with `cv2.imencode`. The
    ring gets a q90 JPEG with the chroma of the source (4:2:2 from YUY2, 4:2:0 from NV12).

    "q90": the quantization tables equal those of a `cv2.imencode` JPEG at quality 90."""
    with capture_app(monkeypatch, [raw_camera(fmt)], full_modes=True) as app:
        QuickSyncFake(monkeypatch, available=False)
        spies = Spies(monkeypatch, app, keep_payloads=True)
        camera_id = app.factory.camera_ids[0]
        ready_app_steps(app, [app.config(camera_id, capture_fourcc=fmt)])
        assert app.status(camera_id)["mode"]["format"] == fmt
        app.wait(lambda: len(spies.of("jpeg", camera_id)) >= 30, "30 ring frames")
        app.client.delete(CLOSE)
    for event in spies.of("jpeg", camera_id)[:30]:
        jpeg = event["payload"]
        assert isinstance(jpeg, bytes) and jpeg[:2] == b"\xff\xd8", "the ring frame is not a JPEG"
        assert jpeg_chroma(jpeg) == CHROMA[fmt]
        assert jpeg_quant_tables(jpeg) == Q90_TABLES, "not a quality 90 JPEG"
        assert decode(jpeg).shape == (H, W, 3)


# ---------------------------------------------------------------------------
# T-CAP-63: one Quick Sync check per app run (13.2)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("available", [True, False], ids=["Quick Sync", "no Quick Sync"])
def test_t_cap_63_one_quick_sync_check_per_app_run(monkeypatch, available):
    """T-CAP-63, section 13.2 [D2, V3, notes: Encoder check]: sessions with and without an uncompressed
    camera; count the Quick Sync checks. One check per app run, only with an uncompressed camera; each
    camera process gets the result.

    One `CaptureApp` is one app run (ADR-3WCA item 6). Three sessions: MJPG only; one YUY2 camera; two
    YUY2 cameras. "Gets the result": the status `jpeg_encoder` of each uncompressed camera is
    "quick_sync" or "cv2", as the check gave, and a Quick Sync encoder opens only after a check that
    gave true."""
    expected = "quick_sync" if available else "cv2"
    with capture_app(monkeypatch, [raw_camera(), raw_camera()], full_modes=True) as app:
        quick_sync = QuickSyncFake(monkeypatch, available=available)
        a, b = app.factory.camera_ids
        ready_app_steps(app, [app.config(a), app.config(b)])
        assert quick_sync.checks == 0, "a check ran for a session with MJPG cameras only"
        assert jpeg_encoder(app, a) is None and jpeg_encoder(app, b) is None
        app.client.delete(CLOSE)
        ready_app_steps(app, [app.config(a, capture_fourcc="YUY2"), app.config(b)])
        assert (jpeg_encoder(app, a), jpeg_encoder(app, b)) == (expected, None)
        assert quick_sync.checks == 1
        app.client.delete(CLOSE)
        ready_app_steps(app, [app.config(a, capture_fourcc="YUY2"), app.config(b, capture_fourcc="YUY2")])
        assert (jpeg_encoder(app, a), jpeg_encoder(app, b)) == (expected, expected)
        assert quick_sync.checks == 1, "a second check ran in the same app run"
        assert len(quick_sync.encoders) == (3 if available else 0)


# ---------------------------------------------------------------------------
# T-CAP-64: the encoder fails during a take (13.2)
# ---------------------------------------------------------------------------

def test_t_cap_64_encoder_failure_during_a_take(monkeypatch, tmp_path):
    """T-CAP-64, section 13.2 [D2, V3, ring 4, notes: Encoder check]: the encoder fails at frame 200 of a
    take. Later frames use `cv2.imencode`; held frames are encoded from the raw frames; no frame is
    lost; the first frame after the event has `DISCONTINUITY`; the event is counted and logged.

    "At frame 200": the first encode call after the camera writer of the take got 200 frames. "Held
    frames": the frame that the fake encoder held when it failed. "No frame is lost": each frame that
    the loop took from the first to the last ring frame has one ring frame, and the recorded frame
    numbers have no gap. "First frame after the event": the first ring frame after the event, which is
    the first `cv2.imencode` JPEG (ADR-3WCA item 7). "Counted and logged" [V3]: a WARNING with the
    camera ID and `cv2.imencode`, the stop line with `encoder fallbacks` and the count, and, while the
    take runs, one `encoder_fallback` item for the camera in the `warnings` of the status (ADR-3WCA
    item 3)."""
    flag = ring_flags()
    with capture_logs() as logs, capture_app(monkeypatch, [raw_camera()], full_modes=True) as app:
        quick_sync = QuickSyncFake(monkeypatch, available=True)
        spies = Spies(monkeypatch, app, keep_payloads=True)
        camera_id = app.factory.camera_ids[0]
        ready_app_steps(app, [app.config(camera_id, capture_fourcc="YUY2")])
        assert jpeg_encoder(app, camera_id) == "quick_sync"
        quick_sync.fail_when = lambda: len(spies.of("record", camera_id)) >= 200
        started = app.record_start(tmp_path)
        assert started.status_code == 200, started.text
        app.wait(lambda: quick_sync.failures == 1 and len(spies.of("record", camera_id)) >= 300,
                 "the failure and 100 more recorded frames")
        items = [w for w in app.status(camera_id)["warnings"] if w["kind"] == "encoder_fallback"]
        assert len(items) == 1 and items[0]["camera_ids"] == [camera_id] and items[0]["text"], items
        assert app.record_stop().status_code == 200
        assert jpeg_encoder(app, camera_id) == "cv2"
        app.client.delete(CLOSE)
    assert len(quick_sync.encoders) == 1, "a Quick Sync encoder opened again after the failure"
    encoder = quick_sync.encoders[0]
    writes = spies.of("jpeg", camera_id)
    marked = [is_quick_sync_jpeg(event["payload"]) for event in writes]
    assert False in marked, "no ring frame came from cv2.imencode"
    first = marked.index(False)
    assert all(marked[:first]) and not any(marked[first:]), "a frame after the event used the Quick Sync encoder"
    assert encoder.accepted == encoder.outputs + 1, "the fake did not hold one frame at the failure"
    taken = app.factory.logs[camera_id].taken
    sfns = [event["sfn"] for event in writes]
    assert sfns == [k for k in taken if sfns[0] <= k <= sfns[-1]], "a taken frame has no ring frame"
    assert [event["frame_number"] for event in writes] == list(range(len(writes)))
    with_discontinuity = [k for k, event in enumerate(writes) if event["flags"] & flag.DISCONTINUITY]
    assert with_discontinuity == [first], f"DISCONTINUITY on ring frames {with_discontinuity}, expected [{first}]"
    recorded = [event["frame_number"] for event in spies.of("record", camera_id)]
    assert recorded == list(range(recorded[0], recorded[0] + len(recorded))), "a recorded frame is missing"
    assert any(camera_id in message and "cv2.imencode" in message for message in logs.messages(logging.WARNING))
    assert stop_line_count(logs.messages(), camera_id, "encoder fallbacks") == 1


# ---------------------------------------------------------------------------
# T-CAP-65: the range rule (13.3)
# ---------------------------------------------------------------------------

CHANGE_AT = 400  # the source frame from which the share outside 16 to 235 changes


@pytest.mark.parametrize(("share", "later", "expected"), [(0.005, 0.02, "limited"), (0.02, 0.0, "full")],
                         ids=["0.5 %", "2 %"])
def test_t_cap_65_range_rule(monkeypatch, tmp_path, share, later, expected):
    """T-CAP-65, section 13.3 [D21, notes: Input range]: warm-up frames with 0.5 % and 2 % of Y values
    outside 16 to 235, with the OS flag "limited". 0.5 %: limited; 2 %: full; the decision does not
    change later in the session; the log holds it (note of 2026-11-20, recorder.md 6.7).

    "Later": from source frame 400 the share changes (0.5 % to 2 %, 2 % to 0 %). The second take
    starts after that frame. "The log holds it" (ADR-0Z2F item 4): at least one line of the camera
    gives a range decision, and each one gives the expected value."""
    script = raw_camera(os_range="limited", y_outside=((0, share), (CHANGE_AT, later)))
    with capture_logs() as logs, capture_app(monkeypatch, [script], full_modes=True) as app:
        QuickSyncFake(monkeypatch, available=False)
        spies = Spies(monkeypatch, app)
        camera_id = app.factory.camera_ids[0]
        ready_app_steps(app, [app.config(camera_id, capture_fourcc="YUY2")])
        record_frames(app, spies, tmp_path, "take1", camera_id, 30)
        app.wait(lambda: app.factory.logs[camera_id].taken[-1] > CHANGE_AT + 30, "the change of the share")
        record_frames(app, spies, tmp_path, "take2", camera_id, 30)
    values = range_values(logs, camera_id)
    assert values, f"no log line with the input range of camera {camera_id}"
    assert all(value == expected for value in values), values


# ---------------------------------------------------------------------------
# T-CAP-66: a raw frame of the wrong length (13.2)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("available", [False, True], ids=["cv2.imencode", "Quick Sync"])
def test_t_cap_66_short_raw_frame_is_flagged_not_encoded(monkeypatch, available):
    """T-CAP-66, section 13.2 [agent 36]: a YUY2 frame that is 100 bytes short. Not encoded; slot flagged
    `CAPTURE_ERROR`. The frames after it are encoded and not flagged.

    "Not encoded" is checked on the fake Quick Sync encoder: it gets no frame of the wrong shape."""
    flag = ring_flags()
    with capture_app(monkeypatch, [raw_camera()], full_modes=True) as app:
        quick_sync = QuickSyncFake(monkeypatch, available=available)
        spies = Spies(monkeypatch, app, keep_payloads=True)
        camera_id = app.factory.camera_ids[0]
        ready_app_steps(app, [app.config(camera_id, capture_fourcc="YUY2")])
        app.wait(lambda: len(spies.of("jpeg", camera_id)) >= 10, "10 ring frames")
        source = app.factory.sources[camera_id]
        source.short_next()
        app.wait(lambda: source.short, "the short frame")
        short = source.short[0]
        app.wait(lambda: any(e["sfn"] > short + 10 for e in spies.of("jpeg", camera_id)), "10 frames after it")
        app.client.delete(CLOSE)
    writes = [e for e in spies.of("jpeg", camera_id) if e["sfn"] == short]
    assert len(writes) == 1 and writes[0]["flags"] & flag.CAPTURE_ERROR, writes
    after = [e for e in spies.of("jpeg", camera_id) if e["sfn"] > short]
    assert after and not any(e["flags"] & flag.CAPTURE_ERROR for e in after)
    assert all(decode(e["payload"]).shape == (H, W, 3) for e in after), "a frame after the short one is no JPEG"
    if available:
        shapes = {shape for encoder in quick_sync.encoders for shape in encoder.shapes}
        assert shapes == {raw_shape("YUY2", W, H)}, f"the encoder got frames of shapes {shapes}"


# ---------------------------------------------------------------------------
# T-CAP-67: the recorder gets the encoded JPEG (13.2)
# ---------------------------------------------------------------------------

def test_t_cap_67_recorder_gets_the_encoded_jpeg(monkeypatch, tmp_path):
    """T-CAP-67, section 13.2 [V3, ring 5.3, note of 2026-11-20]: record in YUY2 with Quick Sync on and
    the BGR ring off. The recorder gets the encoded JPEG.

    "The encoded JPEG" (ADR-0Z2F item 5): each frame that the camera writer of the take gets is the
    Quick Sync JPEG, with the same bytes as the ring frame of the same source frame (ring 5.3); the
    recorded frame numbers have no gap; and each block of the camera file of the take is one of these
    JPEGs: the take is JPEG-MKV (Q689)."""
    with capture_app(monkeypatch, [raw_camera()], full_modes=True) as app:
        quick_sync = QuickSyncFake(monkeypatch, available=True)
        spies = Spies(monkeypatch, app, keep_payloads=True)
        camera_id = app.factory.camera_ids[0]
        ready_app_steps(app, [app.config(camera_id, capture_fourcc="YUY2", bgr_ring=False)])
        assert jpeg_encoder(app, camera_id) == "quick_sync"
        record_frames(app, spies, tmp_path, "take", camera_id, 60)
        app.client.delete(CLOSE)
    assert quick_sync.encoders and quick_sync.encoders[0].accepted > 0, "the Quick Sync encoder was not used"
    records = spies.of("record", camera_id)
    numbers = [event["frame_number"] for event in records]
    assert len(records) >= 60 and numbers == list(range(numbers[0], numbers[0] + len(numbers)))
    assert all(is_quick_sync_jpeg(event["payload"]) for event in records), "a recorded frame is not the Quick Sync JPEG"
    ring = {event["sfn"]: event["hash"] for event in spies.of("jpeg", camera_id)}
    assert all(ring.get(event["sfn"]) == event["hash"] for event in records), "the recorder and the ring differ"
    blocks = block_payloads(tmp_path, camera_id)
    assert len(blocks) == len(records)
    assert all(is_quick_sync_jpeg(block) and jpeg_chroma(block) == "4:2:2" for block in blocks), \
        "a block of the take file is not the encoded JPEG"
    assert not spies.of("bgr", camera_id), "a BGR ring was written with the BGR ring off"


# ---------------------------------------------------------------------------
# T-CAP-70, T-CAP-89: the group rules with a raw format (7.5, 13.1)
# ---------------------------------------------------------------------------

def test_t_cap_70_one_rate_rule_with_a_raw_format(monkeypatch):
    """T-CAP-70, sections 7.5 and 13.1 [D18, D19, U7]: a group with one fake in YUY2 at a mode rate of 30
    and one in MJPG at 60. The apply fails and opens no camera.

    "Fails" for the reason of the one-rate rule (`group_rate_problem` of 7.5), not because the YUY2
    request is refused (ADR-0Z2F item 6)."""
    scripts = [FakeScript(modes=((W, H, 30, 1, "MJPG"), (W, H, 30, 1, "YUY2"))),
               FakeScript(modes=((W, H, 30, 1, "MJPG"), (W, H, 60, 1, "MJPG")))]
    with capture_app(monkeypatch, scripts, full_modes=True) as app:
        QuickSyncFake(monkeypatch, available=False)
        app.detect()
        raw, mjpg = app.factory.camera_ids
        response = app.apply([app.config(raw, capture_fourcc="YUY2", framerate=30.0),
                              app.config(mjpg, framerate=60.0)])
        assert response.status_code == 422, response.text
        assert "must have one frame rate" in detail(response) and "no YUY2 mode" not in detail(response), \
            detail(response)
        assert opens(app, raw) == opens(app, mjpg) == 0 and not app.manager.camera_groups


def test_t_cap_89_floor_of_30_fps_for_a_raw_format(monkeypatch):
    """T-CAP-89, sections 7.5 and 13.1 [U11, agent 58, V1]: a YUY2 request at 1280x720 for a fake with
    YUY2 only at 10 fps there; then at 640x480 where it has 30. The first gets 422 with "no mode at 30
    fps or more"; the second opens.

    The fake has MJPG at 30 fps at 1280x720, so the check must use the YUY2 types of `capture_modes`."""
    script = FakeScript(modes=((1280, 720, 30, 1, "MJPG"), (1280, 720, 10, 1, "YUY2"),
                               (640, 480, 30, 1, "MJPG"), (640, 480, 30, 1, "YUY2")))
    with capture_app(monkeypatch, [script], full_modes=True) as app:
        QuickSyncFake(monkeypatch, available=False)
        app.detect()
        camera_id = app.factory.camera_ids[0]
        refused = app.apply([app.config(camera_id, capture_fourcc="YUY2", framerate=30.0)])
        assert refused.status_code == 422, refused.text
        assert "no mode at 30 fps or more" in detail(refused)
        assert opens(app, camera_id) == 0 and not app.manager.camera_groups
        response = app.apply([app.config(camera_id, capture_fourcc="YUY2", framerate=30.0, width=640, height=480)])
        assert response.status_code == 200, response.text
        app.wait_state(camera_id, "ready")
        mode = app.status(camera_id)["mode"]
        assert (mode["width"], mode["height"], mode["format"], mode["fps_num"]) == (640, 480, "YUY2", 30)


# ---------------------------------------------------------------------------
# T-CAP-71: capture_modes (7.4, V1)
# ---------------------------------------------------------------------------

# The native types of T-CAP-25, and two more: the criterion names RAW, and 7.4 lists native NV12.
NATIVE_71 = NATIVE_25 + ((800, 600, 30, 1, "NV12"), (640, 480, 30, 1, "RAW"))


def _mode(width, height, fps_num, fps_den, fmt, framerate, reason=None):
    uncompressed = fmt in ("YUY2", "NV12", "RAW")
    return {"width": width, "height": height, "fps_num": fps_num, "fps_den": fps_den, "framerate": framerate,
            "format": fmt, "uncompressed": uncompressed, "selectable": reason is None, "reason": reason}


LOW, NEVER = "below 30 fps", "never opened"
EXPECTED_71 = [
    _mode(1920, 1080, 24, 1, "MJPG", 24.0, LOW),
    _mode(1920, 1080, 10000000, 333333, "MJPG", 30.0),
    _mode(1920, 1080, 30, 1, "H264", 30.0, NEVER),
    _mode(1280, 720, 10, 1, "YUY2", 10.0, LOW),
    _mode(1280, 720, 30, 1, "MJPG", 30.0),
    _mode(1280, 720, 60, 1, "MJPG", 60.0),
    _mode(960, 540, 30, 1, "H264", 30.0, NEVER),
    _mode(800, 600, 30, 1, "YUY2", 30.0),
    _mode(800, 600, 30, 1, "NV12", 30.0),
    _mode(640, 480, 15, 2, "MJPG", 7.5, LOW),
    _mode(640, 480, 30000, 1001, "MJPG", 29.97),
    _mode(640, 480, 30, 1, "MJPG", 30.0),
    _mode(640, 480, 30, 1, "YUY2", 30.0),
    _mode(640, 480, 30, 1, "RAW", 30.0, NEVER),
    _mode(480, 640, 30, 1, "MJPG", 30.0),
    _mode(320, 240, 15, 2, "MJPG", 7.5, LOW),
    _mode(320, 240, 24, 1, "MJPG", 24.0, LOW),
]


def test_t_cap_71_capture_modes_json():
    """T-CAP-71, section 7.4, step 3b [V1, D4, D14, U8, U11, agent 19, agent 53]: build `capture_modes`
    from the native types of T-CAP-25. The JSON of 7.4: MJPG and YUY2 both listed, MJPG first; H.264
    and RAW `selectable: false` with "never opened"; modes below 29.97 fps `selectable: false` with
    "below 30 fps"; synthesized NV12 left out.

    Two types are added to those of T-CAP-25: a RAW type (the criterion names RAW) and a native NV12
    type. Where 7.4 does not fix the list, it follows ADR-3WCA item 2: an exact duplicate is listed one
    time; for one size, the rounded rates ascend; for one size and rounded rate, MJPG comes first, then
    the other formats in the order of the native list."""
    modes = product(MODES_MODULE)
    assert hasattr(modes, "capture_modes"), "no modes.capture_modes (V1, ADR-3WCA item 10)"
    result = modes.capture_modes([modes.NativeMode(*m) for m in NATIVE_71])
    dumped = [mode.model_dump() for mode in result]
    assert dumped == EXPECTED_71
    assert json.dumps(dumped) == json.dumps(EXPECTED_71)


# ---------------------------------------------------------------------------
# T-CAP-150, T-CAP-151: a raw request and the detection with the OpenCV source (14.1, V4, V5)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fmt", RAW_FORMATS)
def test_t_cap_150_opencv_source_with_a_raw_request(monkeypatch, tmp_path, fmt):
    """T-CAP-150 (T-CAP-105 of `dom/3bc-tests`), sections 14.1 and 13 [V4]: the OpenCV fake with
    `capture_fourcc` YUY2 and NV12; record. No Quick Sync check runs; `jpeg_encoder` is "cv2"; each ring
    JPEG is the q90 `cv2.imencode` JPEG of an OpenCV image; no input range (ADR-0Z2F item 4: no range
    line in the log).

    "The q90 JPEG of an OpenCV image": byte-equal to `cv2.imencode` at quality 90 of an image that the
    fake gave, as T-CAP-44. The OpenCV fake runs on the virtual clock of `OpenCVFakeFactory`."""
    factory = OpenCVFakeFactory(monkeypatch)
    app = CaptureApp(monkeypatch, factory)
    try:
        with capture_logs() as logs:
            quick_sync = QuickSyncFake(monkeypatch, available=True) if _has_encoder_module() else None
            spies = Spies(monkeypatch, app)
            camera_id = factory.camera_ids[0]
            ready_app_steps(app, [app.config(camera_id, capture_fourcc=fmt)])
            assert jpeg_encoder(app, camera_id) == "cv2"
            record_frames(app, spies, tmp_path, "take", camera_id, 30)
        capture = factory.captures[camera_id]
        writes = spies.of("jpeg", camera_id)
        assert writes and all(e["hash"] in capture.jpeg_hashes for e in writes), \
            "a ring JPEG is not the q90 JPEG of an OpenCV image"
        if quick_sync is not None:
            assert quick_sync.checks == 0 and not quick_sync.encoders, "a Quick Sync check ran for the OpenCV source"
        assert not range_values(logs, camera_id), "an input range for a camera of the OpenCV source"
    finally:
        app.close()


def _has_encoder_module():
    """T-CAP-150 checks that no Quick Sync check runs: without the module, none can run."""
    import importlib.util

    from skellycam.tests.capture.uncompressed import ENCODER_MODULE

    return importlib.util.find_spec(ENCODER_MODULE) is not None


@pytest.mark.skipif(sys.platform == "win32", reason="detection on Windows is Media Foundation (7.1, D11)")
def test_t_cap_151_opencv_detection_has_no_mode_list(monkeypatch):
    """T-CAP-151 (T-CAP-106 of `dom/3bc-tests`), sections 7.3, 7.4 and 14.1 [V5, agent 78]: OpenCV
    detection with a fake `cv2_enumerate_cameras`. `capture_modes` is `[]` and `supported_modes` is `[]`
    for each camera."""
    from cv2_enumerate_cameras.camera_info import CameraInfo

    import skellycam.core.device_detection.detect_cameras_devices as detection

    found = [CameraInfo(index=k, name=f"Fake camera {k}", path=f"/dev/video{2 * k}", vid=0xFEED, pid=k,
                        backend=cv2.CAP_ANY) for k in range(2)]
    monkeypatch.setattr(detection, "enumerate_cameras", lambda *args, **kwargs: list(found))
    cameras = detection.detect_available_cameras()
    assert len(cameras) == 2
    for camera in cameras:
        dumped = camera.model_dump()
        assert "capture_modes" in dumped, "the detection result has no capture_modes (V1)"
        assert dumped["capture_modes"] == [] and dumped["supported_modes"] == [], dumped


# ---------------------------------------------------------------------------
# T-CAP-152, T-CAP-153: the range of the JPEG and of the BGR ring (13.3, ring 8.7, V6)
# ---------------------------------------------------------------------------

RANGE_CASES = {"limited": (0.0, dict(os_range="limited")),
               "full": (0.02, dict(os_range="limited", y_outside=((0, 0.02),)))}
LIMIT_LEVELS = 3.0  # the largest mean absolute difference, in levels (ADR-3WCA item 12)
RANGE_PARAMS = [(fmt, available, case) for fmt in RAW_FORMATS for available in (False, True) for case in RANGE_CASES]
RANGE_IDS = [f"{fmt}-{'Quick Sync' if available else 'cv2'}-{case}" for fmt, available, case in RANGE_PARAMS]


def _range_session(monkeypatch, fmt, available, case, bgr_ring):
    """One camera in `fmt` with the input of `case`; returns (spies, BGR images, camera_id, the
    full-range BGR of the source frame). A limited-range frame has its full-range BGR from the default
    conversion."""
    share, script = RANGE_CASES[case]
    with capture_app(monkeypatch, [raw_camera(fmt, **script)], full_modes=True) as app:
        QuickSyncFake(monkeypatch, available=available)
        spies = Spies(monkeypatch, app, keep_payloads=True)
        images = BgrImages(monkeypatch)
        camera_id = app.factory.camera_ids[0]
        ready_app_steps(app, [app.config(camera_id, capture_fourcc=fmt, bgr_ring=bgr_ring)])
        app.wait(lambda: len(spies.of("jpeg", camera_id)) >= 10 and (not bgr_ring or len(images.images) >= 10),
                 "10 ring frames")
        app.client.delete(CLOSE)
    raw = synthetic_raw(fmt, W, H, share)
    reference = to_bgr(raw, fmt) if case == "limited" else full_range_to_bgr(raw, fmt)
    return spies, images, camera_id, reference


@pytest.mark.parametrize(("fmt", "available", "case"), RANGE_PARAMS, ids=RANGE_IDS)
def test_t_cap_152_the_jpeg_is_full_range(monkeypatch, fmt, available, case):
    """T-CAP-152 (T-CAP-109 of `dom/3bc-tests`), sections 13.2 and 13.3 [V6, notes: Input range]: YUY2
    and NV12 fakes with the fake Quick Sync encoder and with `cv2.imencode`: (1) limited-range frames;
    (2) full-range frames (2 % of Y outside 16 to 235). The decoded ring JPEG equals the full-range BGR
    of the source within a mean absolute difference of 3 levels: (1) the limited-range conversion (the
    OpenCV default); (2) the full-range conversion.

    The fake Quick Sync encoder takes its input as full range, as Quick Sync does: a limited-range
    frame must get the range-expanding table first."""
    spies, _, camera_id, reference = _range_session(monkeypatch, fmt, available, case, bgr_ring=False)
    for event in spies.of("jpeg", camera_id)[:10]:
        difference = mean_difference(decode(event["payload"]), reference)
        assert difference <= LIMIT_LEVELS, f"frame {event['sfn']}: {difference:.2f} levels from the full-range BGR"


@pytest.mark.parametrize(("fmt", "available", "case"), RANGE_PARAMS, ids=RANGE_IDS)
def test_t_cap_153_bgr_ring_matches_the_jpeg(monkeypatch, fmt, available, case):
    """T-CAP-153 (T-CAP-110 of `dom/3bc-tests`), ring 8.7 and section 13.3 [V6]: as T-CAP-152, with the
    BGR ring on. The BGR ring image of each frame equals the decoded ring JPEG of the same frame within
    a mean absolute difference of 3 levels.

    With T-CAP-152, this test decides the conversion of the BGR ring: the decided range (ring 8.7) or
    the default conversion (ADR-467Z item 4); see section 22.4 of the spec."""
    spies, images, camera_id, _ = _range_session(monkeypatch, fmt, available, case, bgr_ring=True)
    jpegs = {event["sfn"]: event["payload"] for event in spies.of("jpeg", camera_id)}
    pairs = [(sfn, image) for sfn, image in images.images.items() if sfn in jpegs][:10]
    assert len(pairs) == 10, "fewer than 10 BGR ring frames with their JPEG"
    for sfn, image in pairs:
        assert image.shape == (H, W, 3)
        difference = mean_difference(image, decode(jpegs[sfn]))
        assert difference <= LIMIT_LEVELS, f"frame {sfn}: {difference:.2f} levels from its JPEG"
