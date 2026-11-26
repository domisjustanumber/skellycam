"""T-CAP-22 to T-CAP-28, T-CAP-48 and T-CAP-106: HRESULT reasons, detection, `camera_id`, `supported_modes`
and the mode choice (specs/windows-capture.md, sections 6.7, 7 and 12).

Detection uses a fake Media Foundation enumeration (`FakeDetectionBackend`). The mode choice runs
through `FakeSource.open`, which calls `modes.choose_mode` of the product.

The package `media_foundation/` is Windows only [U18]. Thus T-CAP-22, T-CAP-23, T-CAP-24 and T-CAP-48
run on the Windows development machine and on the Windows CI job, and are skipped on other systems
(16.1). The tests of `modes.py` run on each system.
"""

import json
import sys
import time

import psutil
import pytest

from skellycam.tests.capture.capture_session import SOURCE_MODULE, capture_app, product
from skellycam.tests.capture.fake_source import (
    FakeDetectionBackend, FakeScript, FakeSource, VirtualClock, fake_link, spec_camera_id)

ERRORS_MODULE = "skellycam.core.camera.capture.media_foundation.errors"
DETECT_MODULE = "skellycam.core.camera.capture.media_foundation.detect"
MODES_MODULE = "skellycam.core.camera.capture.modes"
WINDOWS_ONLY = pytest.mark.skipif(sys.platform != "win32", reason="the media_foundation package is Windows only (U18, 16.1)")


# ---------------------------------------------------------------------------
# T-CAP-22: HRESULT to reason (6.7)
# ---------------------------------------------------------------------------

IN_USE = (0xC00D3704, 0xC00D3EA3, 0x80070964, 0x800700AA)
REMOVED = (0xC00D3EA2, 0x80070651, 0x8007048F, 0x800701B1)
OTHER = {0x80004005: "E_FAIL", 0xC00D3E85: "MF_E_SHUTDOWN"}


@WINDOWS_ONLY
def test_t_cap_22_hresult_reasons():
    """T-CAP-22, sections 6.7 and 12 [D13, agent 15]: map each HRESULT of 6.7 (pure function, no COM).
    In-use codes give "in use by another program"; device-removed codes give "device removed"; other
    codes give their name."""
    errors = product(ERRORS_MODULE)
    for code in IN_USE:
        assert errors.hresult_reason(code) == "in use by another program", hex(code)
    for code in REMOVED:
        assert errors.hresult_reason(code) == "device removed", hex(code)
    for code, name in OTHER.items():
        assert errors.hresult_reason(code) == name


# ---------------------------------------------------------------------------
# T-CAP-23, T-CAP-24: detection and camera_id (7.1, 7.2)
# ---------------------------------------------------------------------------

def _colliding_links():
    """Two different Media Foundation links whose `camera_id` (7.2) is the same."""
    seen = {}
    for k in range(200_000):
        link = fake_link(0).replace("fake0000", f"c{k:07x}")
        camera_id = spec_camera_id(link)
        if camera_id in seen:
            return seen[camera_id], link
        seen[camera_id] = link
    raise AssertionError("no collision found")


MODES_720 = ((1280, 720, 30, 1, "MJPG"),)


@pytest.mark.capture_timing  # a spawned detection child must answer within the 5 s limit; slow under load
@WINDOWS_ONLY
def test_t_cap_23_detection_refuses_two_links_with_one_camera_id():
    """T-CAP-23, section 7.1 [D13]: a detection result with two links that give the same `camera_id`.
    Refused with an error that names both links."""
    detect = product(DETECT_MODULE)
    first, second = _colliding_links()
    backend = FakeDetectionBackend((("Camera A", first, MODES_720), ("Camera B", second, MODES_720)))
    with pytest.raises(ValueError) as error:
        detect.detect_media_foundation_cameras(backend=backend)
    assert first in str(error.value) and second in str(error.value)


@pytest.mark.capture_timing  # a spawned detection child must answer within the 5 s limit; slow under load
@WINDOWS_ONLY
def test_t_cap_24_camera_id_hashes_the_lower_case_link():
    """T-CAP-24, section 7.2 [D11, agent 13]: hash known Media Foundation links in mixed case.
    `camera_id` equals the SHA-256 rule of today on the lower-case link."""
    detect = product(DETECT_MODULE)
    links = [r"\\?\USB#VID_046D&PID_085C&MI_00#7&1A2B3C4D&0&0000#{E5323777-F976-4F5B-9B55-B94699C46E44}\GLOBAL",
             r"\\?\usb#vid_1532&pid_0E05&mi_00#8&3F00AB12&0&0000#{e5323777-f976-4f5b-9b55-b94699c46e44}\global",
             r"\\?\Usb#Vid_046d&Pid_0843&Mi_00#6&2C4D8E1F&1&0000#{E5323777-f976-4F5B-9b55-B94699C46E44}\Global"]
    backend = FakeDetectionBackend(tuple((f"Camera {k}", link, MODES_720) for k, link in enumerate(links)))
    infos = detect.detect_media_foundation_cameras(backend=backend)
    assert len(infos) == 3
    for info, link in zip(infos, links):
        assert info.camera_id == spec_camera_id(link.lower())
        assert info.index == links.index(link)


@pytest.mark.capture_timing  # a spawned detection child must answer within the 5 s limit; slow under load
@WINDOWS_ONLY
def test_t_cap_48_a_hung_device_does_not_block_detection():
    """T-CAP-48, sections 6.6 and 7.1 [D10, agent 17]: detection with a fake enumeration that hangs for
    one device. The detection child ends; the call returns within the limit plus 2 s with an error;
    the main process keeps running. Real time: up to the limit of 5 s plus 2 s."""
    detect = product(DETECT_MODULE)
    source_module = product(SOURCE_MODULE)
    links = [fake_link(0), fake_link(1)]
    backend = FakeDetectionBackend((("Camera 0", links[0], MODES_720), ("Camera 1", links[1], MODES_720)),
                                   hang_link=links[1])
    me = psutil.Process()
    before = {child.pid for child in me.children(recursive=True)}
    t0 = time.perf_counter()
    with pytest.raises(source_module.CaptureFailure) as failure:
        detect.detect_media_foundation_cameras(backend=backend)
    elapsed = time.perf_counter() - t0
    assert failure.value.stage == "detection"
    assert elapsed <= source_module.BOUNDED_CALL_LIMIT_S + 2.0, f"detection returned after {elapsed:.2f} s"
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        new = [c for c in me.children(recursive=True) if c.pid not in before and c.is_running()
               and c.status() != psutil.STATUS_ZOMBIE]
        if not new:
            break
        time.sleep(0.05)
    assert not new, f"the detection child is still alive: {[c.pid for c in new]}"
    assert product(MODES_MODULE).rates_equal(30.0, 30.0), "the main process keeps running"


@pytest.mark.capture_timing  # a spawned detection child must answer within the 5 s limit; slow under load
@WINDOWS_ONLY
def test_detection_marks_a_camera_under_a_software_device_root_virtual():
    """Section 7.1 [ADR-PDD3 W5], first hardware run of 3a: a software camera with no "virtual" in its
    name (for example an NDI camera) has its link under `root#`. Detection marks it virtual, and also a
    camera of the virtual camera API of Windows 11 (`swd#vcamdevapi#`) and a camera with "virtual" in its
    name. A camera on a hardware bus (USB, PCI, a built-in camera under `display#`) and another `swd#`
    device stay real. Each link is made up."""
    detect = product(DETECT_MODULE)
    guid = "{e5323777-f976-4f5b-9b55-b94699c46e44}"
    devices = (
        ("Fake USB camera", fake_link(0), False),
        ("Fake built-in camera", rf"\\?\DISPLAY#FAKE0001#4&1a2b3c4d&0&UID1#{guid}\{{00000000-0000-0000-0000-000000000001}}", False),
        ("Fake PCI camera", rf"\\?\pci#ven_feed&dev_0001&subsys_00000000&rev_01#3&1a2b3c4d&0&a0#{guid}\global", False),
        ("Fake software camera 1", rf"\\?\ROOT#MEDIA#0001#{guid}\global", True),
        ("Fake virtual camera", fake_link(5), True),
        ("Fake camera API camera", rf"\\?\swd#vcamdevapi#{{00000000-0000-0000-0000-00000000feed}}#{guid}\global", True),
        ("Fake sensor group", rf"\\?\SWD#SGDEVAPI#FAKE0007#{guid}\global", False),
    )
    backend = FakeDetectionBackend(tuple((name, link, MODES_720) for name, link, _ in devices))
    infos = detect.detect_media_foundation_cameras(backend=backend)
    assert [(info.name, info.virtual) for info in infos] == [(name, virtual) for name, _, virtual in devices]


# ---------------------------------------------------------------------------
# T-CAP-25: supported_modes (7.3)
# ---------------------------------------------------------------------------

NATIVE_25 = (
    (1280, 720, 30, 1, "NV12"),  # synthesized: immediately before the MJPG type
    (1280, 720, 30, 1, "MJPG"),
    (1280, 720, 60, 1, "NV12"),
    (1280, 720, 60, 1, "MJPG"),
    (1280, 720, 30, 1, "MJPG"),  # a duplicate
    (1280, 720, 10, 1, "YUY2"),
    (1920, 1080, 10000000, 333333, "MJPG"),  # 30.00003
    (1920, 1080, 24, 1, "MJPG"),
    (1920, 1080, 30, 1, "H264"),
    (640, 480, 30000, 1001, "MJPG"),  # 29.97
    (640, 480, 30, 1, "MJPG"),
    (640, 480, 15, 2, "MJPG"),  # 7.5
    (640, 480, 30, 1, "YUY2"),
    (480, 640, 30, 1, "MJPG"),  # the same area as 640x480, smaller width
    (320, 240, 15, 2, "MJPG"),  # only low rates: the size is left out
    (320, 240, 24, 1, "MJPG"),
    (800, 600, 30, 1, "YUY2"),  # no MJPG type: left out
    (960, 540, 30, 1, "H264"),  # only H.264: left out
)
EXPECTED_25 = [
    {"width": 1920, "height": 1080, "framerates": [30.0]},
    {"width": 1280, "height": 720, "framerates": [30.0, 60.0]},
    {"width": 640, "height": 480, "framerates": [29.97, 30.0]},
    {"width": 480, "height": 640, "framerates": [30.0]},
]


def test_t_cap_25_supported_modes_json():
    """T-CAP-25, section 7.3 [D14, U11, agent 18]: build `supported_modes` from native types with MJPG,
    YUY2, a synthesized NV12, H.264, duplicates, 30000/1001, 10000000/333333, 60/1, 24/1 and 15/2.
    The exact JSON of the 7.3 rules: MJPG only, order, 29.97, 30.0 and 60.0; no 24 and no 7.5; no
    duplicates; a size with only low rates is left out."""
    modes = product(MODES_MODULE)
    result = modes.supported_modes([modes.NativeMode(*m) for m in NATIVE_25])
    dumped = [mode.model_dump() for mode in result]
    assert dumped == EXPECTED_25
    assert json.dumps(dumped) == json.dumps(EXPECTED_25)


# ---------------------------------------------------------------------------
# T-CAP-26 to T-CAP-28: mode choice, auto rate, stored rate (7.5)
# ---------------------------------------------------------------------------

def _open(native, width, height, framerate):
    """Open a fake with `native` types through the product mode choice. Returns (opened, fake)."""
    source_module = product(SOURCE_MODULE)
    fake = FakeSource(FakeScript(modes=native), clock=VirtualClock())
    request = source_module.CaptureRequest(camera_id="0", width=width, height=height, framerate=framerate,
                                           capture_fourcc="MJPG")
    return fake.open(request), fake


def _refused(native, width, height, framerate):
    source_module = product(SOURCE_MODULE)
    with pytest.raises(source_module.CaptureFailure) as failure:
        _open(native, width, height, framerate)
    return failure.value


# The NV12 type is at 15 fps (Q876): below the floor, so the raw-mode open of 22.2 (Q807) does not take it, and
# 1920x1080 has no mode that an MJPG request opens, as in the spec row.
NATIVE_26 = ((1280, 720, 30000, 1001, "MJPG"), (1280, 720, 30, 1, "MJPG"), (640, 480, 30, 1, "MJPG"),
             (1920, 1080, 30, 1, "H264"), (1920, 1080, 15, 1, "NV12"))


def test_t_cap_26_mode_choice():
    """T-CAP-26, section 7.5 [D15, D4]: request 30 when the camera has 29.97 and 30; request 60 at a size
    that has only 30; a size it lacks; a size that only H.264 has. 30; no mode for the other three,
    and each failure lists the modes; H.264 is never chosen or opened.

    "Lists the modes": the reason holds the modes as the JSON of 7.3 (ADR-HP7D)."""
    modes = product(MODES_MODULE)
    opened, _ = _open(NATIVE_26, 1280, 720, 30.0)
    assert (opened.fps_num, opened.fps_den, opened.format) == (30, 1, "MJPG")
    listed = json.dumps([m.model_dump() for m in modes.supported_modes([modes.NativeMode(*m) for m in NATIVE_26])])
    for width, height, framerate in ((640, 480, 60.0), (800, 600, 30.0), (1920, 1080, 30.0)):
        failure = _refused(NATIVE_26, width, height, framerate)
        assert failure.stage == "set mode"
        assert listed in failure.reason, f"the failure for {width}x{height}@{framerate} does not list the modes"
    fake = FakeSource(FakeScript(modes=NATIVE_26), clock=VirtualClock())
    with pytest.raises(product(SOURCE_MODULE).CaptureFailure):
        fake.open(product(SOURCE_MODULE).CaptureRequest(camera_id="0", width=1920, height=1080, framerate=30.0,
                                                        capture_fourcc="MJPG"))
    assert "read_sample" not in fake.log.names(), "no stream was started for an H.264-only size"


def test_t_cap_27_auto_rate():
    """T-CAP-27, section 7.5 [D16, U11]: requests of -1 and 0: with 30 at the size; with 60 but no 30;
    with only 15 and 24. 30; 60; failed with "no mode at 30 fps or more"."""
    with_30 = ((640, 480, 60, 1, "MJPG"), (640, 480, 30, 1, "MJPG"), (640, 480, 24, 1, "MJPG"))
    with_60 = ((640, 480, 24, 1, "MJPG"), (640, 480, 60, 1, "MJPG"), (1280, 720, 30, 1, "MJPG"))
    low = ((640, 480, 15, 1, "MJPG"), (640, 480, 24, 1, "MJPG"), (1280, 720, 30, 1, "MJPG"))
    for auto in (-1.0, 0.0):
        assert _open(with_30, 640, 480, auto)[0].fps_num == 30
        assert _open(with_60, 640, 480, auto)[0].fps_num == 60
        failure = _refused(low, 640, 480, auto)
        assert (failure.stage, failure.reason) == ("set mode", "no mode at 30 fps or more")


def test_t_cap_28_stored_rate_and_tolerance(monkeypatch):
    """T-CAP-28, section 7.5 [D17]: open with -1; compare 30.0 and 30.00003, 30 and 29.97. The config
    stores the mode rate; the first pair is equal, the second is not."""
    modes = product(MODES_MODULE)
    assert modes.rates_equal(30.0, 30.00003)
    assert not modes.rates_equal(30.0, 29.97)
    script = FakeScript(modes=((640, 480, 10000000, 333333, "MJPG"),))
    with capture_app(monkeypatch, [script]) as app:
        app.detect()
        camera_id = app.factory.camera_ids[0]
        response = app.apply([app.config(camera_id, framerate=-1.0)])
        assert response.status_code == 200, response.text
        stored = response.json()["camera_configs"][camera_id]["framerate"]
        assert stored == pytest.approx(10000000 / 333333, rel=1e-9, abs=0)


@pytest.mark.parametrize("kind", ["CameraDeviceInfo", "MediaFoundationDeviceInfo"])
def test_t_cap_106_one_camera_id_for_a_mixed_case_link(kind):
    """T-CAP-106, section 7.2 [D11, agent 13, ADR-PDD3 W6]: a Media Foundation link in mixed case, in both
    device-info classes. `camera_id` is the hash of the lower-case link, so the mixed-case and the
    lower-case link give one `camera_id`; `path` stays as the OS gives it. The class of the Windows-only
    package runs on Windows only (U18)."""
    if kind == "MediaFoundationDeviceInfo":
        if sys.platform != "win32":
            pytest.skip("the media_foundation package is Windows only (U18, 16.1)")
        info_class = product(DETECT_MODULE).MediaFoundationDeviceInfo
    else:
        info_class = product("skellycam.core.device_detection.detect_cameras_devices").CameraDeviceInfo
    link = r"\\?\USB#VID_046D&PID_085C&MI_00#7&1A2B3C4D&0&0000#{E5323777-F976-4F5B-9B55-B94699C46E44}\GLOBAL"
    mixed = info_class(index=0, name="Camera", path=link)
    lower = info_class(index=0, name="Camera", path=link.lower())
    assert mixed.camera_id == lower.camera_id == spec_camera_id(link)
    assert mixed.path == link


@WINDOWS_ONLY
@pytest.mark.capture_timing
def test_the_device_list_activates_no_camera():
    """Review item 4: the check after a failed start lists the devices only. It activates no camera (a camera
    that streams in the group must not be opened again), so the mode list of a device is never read: the fake
    hangs on that call."""
    detect = product(DETECT_MODULE)
    links = [fake_link(0), fake_link(1)]
    backend = FakeDetectionBackend((("Camera 0", links[0], MODES_720), ("Camera 1", links[1], MODES_720)),
                                   hang_link=links[1])
    infos = detect.detect_media_foundation_cameras(backend=backend, modes=False)
    assert [info.path for info in infos] == links
    assert all(not info.modes_read and info.supported_modes == [] for info in infos)


@WINDOWS_ONLY
def test_the_device_list_looks_up_no_usb_link(monkeypatch):
    """Fix lane I: `detect_available_cameras(modes=False)` (the check after a failed start, which uses the links of the
    detection before) looks up no USB link; the full detection does."""
    from skellycam.core.camera.capture import camera_checks
    from skellycam.core.device_detection import detect_cameras_devices

    detect = product(DETECT_MODULE)
    looked_up = []
    monkeypatch.setattr(detect, "detect_media_foundation_cameras", lambda modes: [
        detect_cameras_devices.CameraDeviceInfo(index=0, name="Camera 0", path=fake_link(0))])
    monkeypatch.setattr(camera_checks, "mark_devices", lambda cameras: cameras)
    monkeypatch.setattr(detect_cameras_devices, "usb_link", lambda path: looked_up.append(path) or "USB 2")
    assert detect_cameras_devices.detect_available_cameras(modes=False)[0].usb_link != "USB 2"
    assert looked_up == []
    assert detect_cameras_devices.detect_available_cameras()[0].usb_link == "USB 2"
