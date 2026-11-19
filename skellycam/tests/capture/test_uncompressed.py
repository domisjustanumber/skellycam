"""Step 3b: uncompressed modes (specs/windows-capture.md, section 13; specs/frame-ring.md, section 8.7).

T-CAP-61 to T-CAP-67, T-CAP-70, T-CAP-89, T-CAP-105, T-CAP-106, T-CAP-109 and T-CAP-110. They run on
Windows, Linux and macOS (16.7), except T-CAP-106, which runs on Linux and macOS only. T-CAP-105 uses
the product `OpenCVSource` with the OpenCV fake, in real time (V4).

The fake source gives synthetic YUY2 and NV12 frames (`uncompressed.synthetic_raw`). The session
tests run THREAD workers with a virtual clock (`capture_session`), and the detection result holds
the full mode list (`full_modes=True`, ADR-3WCA). `QuickSyncFake` replaces the Quick Sync check and
encoder of the product module `capture.encoder` (ADR-3WCA): `available=False` gives the
`cv2.imencode` path, `available=True` a fake encoder that holds one frame, as Quick Sync at depth 2.
Thus no test needs an Intel GPU.
"""

import json
import logging
import sys

import pytest

from skellycam.tests.capture.capture_session import (
    SOURCE_MODULE, CaptureApp, OpenCVFakeFactory, Spies, capture_app, capture_logs, product, ready_app_steps,
    recording_info_json, stop_line_count)
from skellycam.tests.capture.fake_source import FakeScript, FakeSource, VirtualClock
from skellycam.tests.capture.uncompressed import (
    Q90_TABLES, RAW_FORMATS, QuickSyncFake, full_range_to_bgr, is_quick_sync_jpeg, jpeg_chroma, jpeg_quant_tables,
    mean_difference, raw_shape, synthetic_raw, to_bgr)

W, H = 320, 240
CLOSE = "/skellycam/camera/group/close/all"


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


def record_frames(app, spies, directory, name, camera_id, frames):
    """Record until the old recorder got `frames` more frames of the camera, then stop."""
    before = len(spies.of("record", camera_id))
    response = app.record_start(directory, name)
    assert response.status_code == 200, response.text
    app.wait(lambda: len(spies.of("record", camera_id)) >= before + frames, f"{frames} recorded frames")
    response = app.record_stop()
    assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# T-CAP-61: the choice of a raw type (13.1)
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

@pytest.mark.parametrize(("fmt", "chroma"), [("YUY2", "4:2:2"), ("NV12", "4:2:0")])
def test_t_cap_62_cv2_jpeg_has_quality_90_and_the_chroma_of_the_source(monkeypatch, fmt, chroma):
    """T-CAP-62, section 13.2 [D2, notes: Encoder settings]: YUY2 and NV12 fakes with `cv2.imencode`. The
    ring gets a q90 JPEG with the chroma of the source (4:2:2 from YUY2, 4:2:0 from NV12).

    "q90": the quantization tables equal those of a `cv2.imencode` JPEG at quality 90."""
    import cv2
    import numpy as np

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
        assert jpeg_chroma(jpeg) == chroma
        assert jpeg_quant_tables(jpeg) == Q90_TABLES, "not a quality 90 JPEG"
        assert cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR).shape == (H, W, 3)


# ---------------------------------------------------------------------------
# T-CAP-63: one Quick Sync check per app run (13.2)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("available", [True, False], ids=["Quick Sync", "no Quick Sync"])
def test_t_cap_63_one_quick_sync_check_per_app_run(monkeypatch, available):
    """T-CAP-63, section 13.2 [D2, notes: Encoder check]: sessions with and without an uncompressed
    camera; count the Quick Sync checks. One check per app run, only with an uncompressed camera; each
    camera process gets the result.

    One `CaptureApp` is one app run. Three sessions: MJPG only; one YUY2 camera; two YUY2 cameras.
    "Gets the result": the status `jpeg_encoder` (ADR-3WCA) of each uncompressed camera is
    "quick_sync" or "cv2", as the check gave, and a Quick Sync encoder opens only after a check that
    gave true."""
    expected = "quick_sync" if available else "cv2"
    with capture_app(monkeypatch, [raw_camera(), raw_camera()], full_modes=True) as app:
        quick_sync = QuickSyncFake(monkeypatch, available=available)
        a, b = app.factory.camera_ids
        ready_app_steps(app, [app.config(a), app.config(b)])
        assert quick_sync.checks == 0, "a check ran for a session with MJPG cameras only"
        assert app.status(a)["jpeg_encoder"] is None and app.status(b)["jpeg_encoder"] is None
        app.client.delete(CLOSE)
        ready_app_steps(app, [app.config(a, capture_fourcc="YUY2"), app.config(b)])
        assert quick_sync.checks == 1
        assert (app.status(a)["jpeg_encoder"], app.status(b)["jpeg_encoder"]) == (expected, None)
        app.client.delete(CLOSE)
        ready_app_steps(app, [app.config(a, capture_fourcc="YUY2"), app.config(b, capture_fourcc="YUY2")])
        assert quick_sync.checks == 1, "a second check ran in the same app run"
        assert (app.status(a)["jpeg_encoder"], app.status(b)["jpeg_encoder"]) == (expected, expected)
        assert len(quick_sync.encoders) == (3 if available else 0)


# ---------------------------------------------------------------------------
# T-CAP-64: the encoder fails during a take (13.2)
# ---------------------------------------------------------------------------

def test_t_cap_64_encoder_failure_during_a_take(monkeypatch, tmp_path):
    """T-CAP-64, section 13.2 [D2, ring 4, notes: Encoder check]: the encoder fails at frame 200 of a
    take. Later frames use `cv2.imencode`; held frames are encoded from the raw frames; no frame is
    lost; the first frame after the event has `DISCONTINUITY`; the event is counted and logged.

    "At frame 200": the first encode call after the old recorder got 200 frames of the take.
    "Held frames": the frame that the fake encoder held when it failed. "No frame is lost": each frame
    that the loop took from the first to the last ring frame has one ring frame, and the recorded
    frame numbers have no gap. "First frame after the event": the first ring frame after the event,
    which is the first `cv2.imencode` JPEG. "Counted and logged" [V3]: a WARNING with the camera ID
    and `cv2.imencode`, the stop line with `encoder fallbacks` and the count (ADR-3WCA), and, while
    the take runs, one `encoder_fallback` item for the camera in the `warnings` of the status (11.3,
    ADR-3WCA)."""
    flag = ring_flags()
    with capture_logs() as logs, capture_app(monkeypatch, [raw_camera()], full_modes=True) as app:
        quick_sync = QuickSyncFake(monkeypatch, available=True)
        spies = Spies(monkeypatch, app, keep_payloads=True)
        camera_id = app.factory.camera_ids[0]
        ready_app_steps(app, [app.config(camera_id, capture_fourcc="YUY2")])
        assert app.status(camera_id)["jpeg_encoder"] == "quick_sync"
        quick_sync.fail_when = lambda: len(spies.of("record", camera_id)) >= 200
        started = app.record_start(tmp_path)
        assert started.status_code == 200, started.text
        app.wait(lambda: quick_sync.failures == 1 and len(spies.of("record", camera_id)) >= 300,
                 "the failure and 100 more recorded frames")
        items = [w for w in app.status(camera_id)["warnings"] if w["kind"] == "encoder_fallback"]
        assert len(items) == 1 and items[0]["camera_ids"] == [camera_id] and items[0]["text"], items
        assert app.record_stop().status_code == 200
        assert app.status(camera_id)["jpeg_encoder"] == "cv2"
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
    assert stop_line_count(logs.messages(), camera_id, word="encoder fallbacks") == 1


# ---------------------------------------------------------------------------
# T-CAP-65: the range rule (13.3)
# ---------------------------------------------------------------------------

CHANGE_AT = 400  # the source frame from which the share outside 16 to 235 changes


@pytest.mark.parametrize(("share", "later", "expected"), [(0.005, 0.02, "limited"), (0.02, 0.0, "full")],
                         ids=["0.5 %", "2 %"])
def test_t_cap_65_range_rule(monkeypatch, tmp_path, share, later, expected):
    """T-CAP-65, section 13.3 [D21, notes: Input range]: warm-up frames with 0.5 % and 2 % of Y values
    outside 16 to 235, with the OS flag "limited". 0.5 %: limited; 2 %: full; the decision does not
    change later in the session; the recording info holds it.

    "Later": from source frame 400 the share changes (0.5 % to 2 %, 2 % to 0 %). The second take
    starts after that frame; both takes hold the decision of the warm-up."""
    script = raw_camera(os_range="limited", y_outside=((0, share), (CHANGE_AT, later)))
    with capture_app(monkeypatch, [script], full_modes=True) as app:
        QuickSyncFake(monkeypatch, available=False)
        spies = Spies(monkeypatch, app)
        camera_id = app.factory.camera_ids[0]
        ready_app_steps(app, [app.config(camera_id, capture_fourcc="YUY2")])
        record_frames(app, spies, tmp_path, "take1", camera_id, 30)
        app.wait(lambda: app.factory.logs[camera_id].taken[-1] > CHANGE_AT + 30, "the change of the share")
        record_frames(app, spies, tmp_path, "take2", camera_id, 30)
    for name in ("take1", "take2"):
        assert recording_info_json(tmp_path, name)["capture"][camera_id]["input_range"] == expected, name


# ---------------------------------------------------------------------------
# T-CAP-66: a raw frame of the wrong length (13.2)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("available", [False, True], ids=["cv2.imencode", "Quick Sync"])
def test_t_cap_66_short_raw_frame_is_flagged_not_encoded(monkeypatch, available):
    """T-CAP-66, section 13.2 [agent 36]: a YUY2 frame that is 100 bytes short. Not encoded; slot flagged
    `CAPTURE_ERROR`.

    "Not encoded" is checked on the fake Quick Sync encoder: it gets no frame of the wrong shape."""
    flag = ring_flags()
    with capture_app(monkeypatch, [raw_camera()], full_modes=True) as app:
        quick_sync = QuickSyncFake(monkeypatch, available=available)
        spies = Spies(monkeypatch, app)
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
    if available:
        shapes = {shape for encoder in quick_sync.encoders for shape in encoder.shapes}
        assert shapes == {raw_shape("YUY2", W, H)}, f"the encoder got frames of shapes {shapes}"


# ---------------------------------------------------------------------------
# T-CAP-67: the old recorder gets BGR (13.2)
# ---------------------------------------------------------------------------

def test_t_cap_67_old_recorder_gets_bgr_with_quick_sync(monkeypatch, tmp_path):
    """T-CAP-67, section 13.2 [D9, agent 36]: record in YUY2 with Quick Sync on and the BGR ring off. The
    old recorder gets a BGR image for each recorded frame.

    "Each recorded frame": the recorded frame numbers have no gap, and each frame of the old
    recorder is a `(height, width, 3)` uint8 image."""
    with capture_app(monkeypatch, [raw_camera()], full_modes=True) as app:
        quick_sync = QuickSyncFake(monkeypatch, available=True)
        spies = Spies(monkeypatch, app)
        camera_id = app.factory.camera_ids[0]
        ready_app_steps(app, [app.config(camera_id, capture_fourcc="YUY2", bgr_ring=False)])
        assert app.status(camera_id)["jpeg_encoder"] == "quick_sync"
        record_frames(app, spies, tmp_path, "take", camera_id, 60)
        app.client.delete(CLOSE)
    assert quick_sync.encoders and quick_sync.encoders[0].accepted > 0, "the Quick Sync encoder was not used"
    records = spies.of("record", camera_id)
    numbers = [event["frame_number"] for event in records]
    assert len(records) >= 60 and numbers == list(range(numbers[0], numbers[0] + len(numbers)))
    assert all(event["shape"] == (H, W, 3) and event["dtype"] == "uint8" for event in records), \
        {(event["shape"], event["dtype"]) for event in records}
    assert not spies.of("bgr", camera_id), "a BGR ring was written with the BGR ring off"


# ---------------------------------------------------------------------------
# T-CAP-70, T-CAP-89: the group rules with a raw format (7.5, 13.1)
# ---------------------------------------------------------------------------

def test_t_cap_70_one_rate_rule_with_a_raw_format(monkeypatch):
    """T-CAP-70, sections 7.5 and 13.1 [D18, D19, U7]: a group with one fake in YUY2 at a mode rate of 30
    and one in MJPG at 60. The apply fails and opens no camera."""
    scripts = [FakeScript(modes=((W, H, 30, 1, "MJPG"), (W, H, 30, 1, "YUY2"))),
               FakeScript(modes=((W, H, 30, 1, "MJPG"), (W, H, 60, 1, "MJPG")))]
    with capture_app(monkeypatch, scripts, full_modes=True) as app:
        QuickSyncFake(monkeypatch, available=False)
        app.detect()
        raw, mjpg = app.factory.camera_ids
        response = app.apply([app.config(raw, capture_fourcc="YUY2", framerate=30.0),
                              app.config(mjpg, framerate=60.0)])
        assert response.status_code == 422, response.text
        assert opens(app, raw) == opens(app, mjpg) == 0 and not app.manager.camera_groups


def test_t_cap_89_floor_of_30_fps_for_a_raw_format(monkeypatch):
    """T-CAP-89, sections 7.5 and 13.1 [U11, agent 58]: a YUY2 request at 1280x720 for a fake with YUY2
    only at 10 fps there; then at 640x480 where it has 30. The first gets 422 with "no mode at 30 fps
    or more"; the second opens.

    The fake has MJPG at 30 fps at 1280x720, so the check must use the YUY2 types."""
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
# T-CAP-105, T-CAP-106: a raw request and the detection with the OpenCV source (14.1, V4, V5)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fmt", RAW_FORMATS)
def test_t_cap_105_opencv_source_with_a_raw_request(monkeypatch, tmp_path, fmt):
    """T-CAP-105, sections 14.1 and 13 [V4]: the OpenCV fake with `capture_fourcc` YUY2 and NV12; record.
    No Quick Sync check runs; `jpeg_encoder` is "cv2"; each ring JPEG is the q90 `cv2.imencode` JPEG of
    the OpenCV image; `input_range` is null in the recording info.

    "The q90 JPEG of the OpenCV image": byte-equal to `cv2.imencode` at quality 90 of an image that the
    fake gave, as T-CAP-44. Real time: about 5 s."""
    factory = OpenCVFakeFactory(monkeypatch)
    app = CaptureApp(monkeypatch, factory)
    try:
        quick_sync = QuickSyncFake(monkeypatch, available=True)
        spies = Spies(monkeypatch, app)
        camera_id = factory.camera_ids[0]
        ready_app_steps(app, [app.config(camera_id, capture_fourcc=fmt)])
        assert app.status(camera_id)["jpeg_encoder"] == "cv2"
        record_frames(app, spies, tmp_path, "take", camera_id, 30)
        capture = factory.captures[camera_id]
        writes = spies.of("jpeg", camera_id)
        assert writes and all(e["hash"] in capture.jpeg_hashes for e in writes), \
            "a ring JPEG is not the q90 JPEG of an OpenCV image"
        assert quick_sync.checks == 0 and not quick_sync.encoders, "a Quick Sync check ran for the OpenCV source"
        assert recording_info_json(tmp_path)["capture"][camera_id]["input_range"] is None
    finally:
        app.close()


@pytest.mark.skipif(sys.platform == "win32", reason="detection on Windows is Media Foundation (7.1, D11)")
def test_t_cap_106_opencv_detection_has_no_mode_list(monkeypatch):
    """T-CAP-106, sections 7.3, 7.4 and 14.1 [V5, agent 78]: OpenCV detection with a fake
    `cv2_enumerate_cameras`. `capture_modes` is `[]` and `supported_modes` is `[]` for each camera."""
    import cv2
    from cv2_enumerate_cameras.camera_info import CameraInfo

    import skellycam.core.device_detection.detect_cameras_devices as detection

    found = [CameraInfo(index=k, name=f"Fake camera {k}", path=f"/dev/video{2 * k}", vid=0xFEED, pid=k,
                        backend=cv2.CAP_ANY) for k in range(2)]
    monkeypatch.setattr(detection, "enumerate_cameras", lambda *args, **kwargs: list(found))
    cameras = detection.detect_available_cameras()
    assert len(cameras) == 2
    for camera in cameras:
        dumped = camera.model_dump()
        assert dumped["capture_modes"] == [] and dumped["supported_modes"] == [], dumped


# ---------------------------------------------------------------------------
# T-CAP-109, T-CAP-110: the range of the JPEG and of the BGR ring (13.3, ring 8.7, V6)
# ---------------------------------------------------------------------------

RANGE_CASES = {"limited": (0.0, dict(os_range="limited")),
               "full": (0.02, dict(os_range="limited", y_outside=((0, 0.02),)))}
LIMIT_LEVELS = 3.0  # the largest mean absolute difference, in levels
RANGE_PARAMS = [(fmt, available, case) for fmt in RAW_FORMATS for available in (False, True) for case in RANGE_CASES]
RANGE_IDS = [f"{fmt}-{'Quick Sync' if available else 'cv2'}-{case}" for fmt, available, case in RANGE_PARAMS]


def _range_session(monkeypatch, fmt, available, case, bgr_ring):
    """One camera in `fmt` with the input of `case`; returns (spies, camera_id, the full-range BGR of
    the source frame). A limited-range frame has its full-range BGR from the default conversion."""
    share, script = RANGE_CASES[case]
    with capture_app(monkeypatch, [raw_camera(fmt, **script)], full_modes=True) as app:
        QuickSyncFake(monkeypatch, available=available)
        spies = Spies(monkeypatch, app, keep_payloads=True)
        camera_id = app.factory.camera_ids[0]
        ready_app_steps(app, [app.config(camera_id, capture_fourcc=fmt, bgr_ring=bgr_ring)])
        app.wait(lambda: len(spies.of("jpeg", camera_id)) >= 10 and (not bgr_ring or len(spies.of("bgr", camera_id)) >= 10),
                 "10 ring frames")
        app.client.delete(CLOSE)
    raw = synthetic_raw(fmt, W, H, share)
    reference = to_bgr(raw, fmt) if case == "limited" else full_range_to_bgr(raw, fmt)
    return spies, camera_id, reference


def _decode(jpeg):
    import cv2
    import numpy as np

    return cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)


@pytest.mark.parametrize(("fmt", "available", "case"), RANGE_PARAMS, ids=RANGE_IDS)
def test_t_cap_109_the_jpeg_is_full_range(monkeypatch, fmt, available, case):
    """T-CAP-109, sections 13.2 and 13.3 [V6, notes: Input range]: YUY2 and NV12 fakes with the fake
    Quick Sync encoder and with `cv2.imencode`: (1) limited-range frames; (2) full-range frames (2 % of
    Y outside 16 to 235). The decoded ring JPEG equals the full-range BGR of the source within a mean
    absolute difference of 3 levels: (1) the limited-range conversion (the OpenCV default); (2) the
    full-range conversion.

    The fake Quick Sync encoder takes its input as full range, as Quick Sync does: a limited-range
    frame must get the range-expanding table first."""
    spies, camera_id, reference = _range_session(monkeypatch, fmt, available, case, bgr_ring=False)
    for event in spies.of("jpeg", camera_id)[:10]:
        difference = mean_difference(_decode(event["payload"]), reference)
        assert difference <= LIMIT_LEVELS, f"frame {event['sfn']}: {difference:.2f} levels from the full-range BGR"


@pytest.mark.parametrize(("fmt", "available", "case"), RANGE_PARAMS, ids=RANGE_IDS)
def test_t_cap_110_bgr_ring_matches_the_jpeg(monkeypatch, fmt, available, case):
    """T-CAP-110, ring 8.7 and section 13.3 [V6]: as T-CAP-109, with the BGR ring on. The BGR ring image
    of each frame equals the decoded ring JPEG of the same frame within a mean absolute difference of
    3 levels.

    With T-CAP-109, this test decides the conversion of the BGR ring: the decided range (ring 8.7) or
    the default conversion (ADR-467Z item 4); see section 17.2 of the spec."""
    spies, camera_id, _ = _range_session(monkeypatch, fmt, available, case, bgr_ring=True)
    jpegs = {event["sfn"]: event["payload"] for event in spies.of("jpeg", camera_id)}
    bgrs = [event for event in spies.of("bgr", camera_id) if event["sfn"] in jpegs][:10]
    assert len(bgrs) == 10, "fewer than 10 BGR ring frames with their JPEG"
    for event in bgrs:
        assert event["payload"].shape == (H, W, 3)
        difference = mean_difference(event["payload"], _decode(jpegs[event["sfn"]]))
        assert difference <= LIMIT_LEVELS, f"frame {event['sfn']}: {difference:.2f} levels from its JPEG"
