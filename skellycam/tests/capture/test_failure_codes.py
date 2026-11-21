"""T-UNX-64 and T-UNX-77: the failure code of each camera failure (specs/unix-capture.md 4.2 item 1, 4.6.3;
specs/windows-capture.md 6.7, 12).

The loop sites run fake cameras through the HTTP endpoints (`capture_session`). Each test that compares
a whole failure object of an older test also checks its code. The main-process sites run on a group with
no camera process (`bare_group` of `test_group_watch.py`). T-UNX-77 maps HRESULTs with no COM; the
package `media_foundation/` is Windows only (U18), so it is skipped on other systems.
"""

import pickle
import sys
from types import SimpleNamespace

import pytest

from skellycam.tests.capture.capture_session import capture_app, one_camera, product
from skellycam.tests.capture.fake_source import FakeScript
from skellycam.tests.capture.test_group_watch import bare_group, status_in

SOURCE_MODULE = "skellycam.core.camera.capture.source"
CODES_MODULE = "skellycam.core.camera.capture.failure_codes"
SPEC_CODES = ("not-found", "no-access", "no-permission", "camera-in-use", "usb-bandwidth", "no-mode", "below-floor",
              "open-failed", "first-frame-timeout", "no-native-jpeg", "not-ready", "rate-low", "rate-high",
              "control-failed", "device-removed", "stalled", "hung", "disk-stall", "previous-process-alive",
              "stream-error", "format-changed", "process-ended")
BEFORE_STREAMING = ("open", "set mode", "set controls", "first frame", "warm-up", "rate check", "detection")
AFTER_STREAMING = ("streaming", "recording", "close")


def test_t_unx_64_the_code_list_and_the_default_by_stage():
    """T-UNX-64: each code of 4.6.3; a failure with no code at each stage gets `open-failed` before streaming
    and `stream-error` after; a hung failure with no code gets `hung` (the hung rows of 4.6.3)."""
    codes, source = product(CODES_MODULE), product(SOURCE_MODULE)
    assert tuple(codes.CODES) == SPEC_CODES
    for stage in BEFORE_STREAMING:
        assert source.CaptureFailure(stage, "x").code == "open-failed", stage
    for stage in AFTER_STREAMING:
        assert source.CaptureFailure(stage, "x").code == "stream-error", stage
    assert source.CaptureFailure("close", "Flush did not return in 5 s", hung=True).code == "hung"
    assert source.CaptureFailure("open", "x", code="camera-in-use").code == "camera-in-use"


def test_t_unx_64_the_code_survives_a_process_boundary():
    """T-UNX-64: `code`, `stage`, `reason` and `hung` survive pickling (the pipe of a camera process)."""
    source = product(SOURCE_MODULE)
    for failure in (source.CaptureFailure("open", "in use by another program", code="camera-in-use"),
                    source.CaptureFailure("close", "no return", hung=True),
                    source.CaptureFailure("streaming", "end of stream")):
        copy = pickle.loads(pickle.dumps(failure))
        assert (copy.stage, copy.reason, copy.hung, copy.code) == (failure.stage, failure.reason, failure.hung,
                                                                   failure.code)


def test_t_unx_64_the_mode_choice_codes():
    """T-UNX-64, rows `modes.py:84`, `:88`, `:95` (`below-floor`) and `:91` (`no-mode`)."""
    modes, source = product("skellycam.core.camera.capture.modes"), product(SOURCE_MODULE)

    def code(native, width=640, height=480, framerate=30.0, fourcc="MJPG"):
        request = source.CaptureRequest(camera_id="aaaa", width=width, height=height, framerate=framerate,
                                        capture_fourcc=fourcc)
        with pytest.raises(source.CaptureFailure) as error:
            modes.choose_mode([modes.NativeMode(*m) for m in native], request)
        return error.value.stage, error.value.code

    assert code(((640, 480, 15, 1, "MJPG"),), framerate=-1.0) == ("set mode", "below-floor")  # :84, auto
    assert code(((640, 480, 15, 1, "MJPG"),)) == ("set mode", "below-floor")  # :88, no mode at the floor
    assert code(((640, 480, 30, 1, "MJPG"),), fourcc="YUY2") == ("set mode", "no-mode")  # :91
    assert code(((640, 480, 30, 1, "MJPG"), (640, 480, 15, 1, "MJPG")), framerate=15.0) == ("set mode", "below-floor")


def test_t_unx_64_a_stall_gives_stalled(monkeypatch):
    """T-UNX-64, row `camera_loop.py:204`: no frame for 2 s while `ready`: `dead`, code `stalled`."""
    with one_camera(monkeypatch, FakeScript()) as (app, camera_id, _):
        app.factory.sources[camera_id].stop_now()
        app.wait_state(camera_id, "dead")
        assert app.status(camera_id)["failure"] == {"camera_id": camera_id, "stage": "streaming",
                                                    "reason": "no frame for 2 s", "code": "stalled"}


def test_t_unx_64_a_fast_camera_gives_rate_high(monkeypatch):
    """T-UNX-64, row `camera_loop.py:265`: a camera that delivers 10 % above its mode rate: `rate-high`
    (T-CAP-18 checks `rate-low` for a slow camera)."""
    with one_camera(monkeypatch, FakeScript(rate=33.0)) as (app, camera_id, _):
        failure = app.status(camera_id)["failure"]
        assert (failure["stage"], failure["code"]) == ("rate check", "rate-high"), failure


def test_t_unx_64_any_other_loop_error_gets_the_default(monkeypatch):
    """T-UNX-64, row `camera_loop.py:154`: an exception of the loop after the start-up: `<type>: <text>`,
    stage `streaming`, code `stream-error` (the default after streaming)."""
    def on_read(source, now_ns):
        if len(source.log.taken) > 150:
            raise RuntimeError("test: the read breaks")

    with capture_app(monkeypatch, [FakeScript()], on_read=on_read) as app:
        app.detect()
        camera_id = app.factory.camera_ids[0]
        assert app.apply([app.config(camera_id)]).status_code == 200
        app.wait_state(camera_id, "dead")
        assert app.status(camera_id)["failure"] == {"camera_id": camera_id, "stage": "streaming",
                                                    "reason": "RuntimeError: test: the read breaks",
                                                    "code": "stream-error"}


def test_t_unx_64_the_main_process_sites():
    """T-UNX-64, the table of the main-process sites: `_give_up` (`open-failed` at `open`, `not-ready` at
    `warm-up`), `_mark_ended` (`process-ended`), and the stuck writer (`disk-stall`)."""
    statuses = {"aaaa": status_in("starting"), "bbbb": status_in("waiting"),
                "cccc": status_in("ready"), "dddd": status_in("recording")}
    ended = SimpleNamespace(worker=SimpleNamespace(exitcode=3))
    stuck = SimpleNamespace(worker=SimpleNamespace(terminate=lambda: None, kill=lambda: None, exitcode=None),
                            join=lambda timeout=None: None, is_alive=lambda: False)
    group = bare_group({"cccc": ended, "dddd": stuck}, statuses)
    group._give_up(["aaaa"], "open")
    group._give_up(["bbbb"], "warm-up")
    group._mark_ended("cccc", ended)
    group._end_stuck_camera("dddd")
    codes = {camera_id: (status.info_dict()["failure"]["stage"], status.info_dict()["failure"]["code"])
             for camera_id, status in statuses.items()}
    assert codes == {"aaaa": ("open", "open-failed"), "bbbb": ("warm-up", "not-ready"),
                     "cccc": ("streaming", "process-ended"), "dddd": ("recording", "disk-stall")}


@pytest.mark.parametrize("case", ["open fails", "no control"])
def test_t_unx_64_the_opencv_source_sites(monkeypatch, case):
    """T-UNX-64, rows `opencv_source.py:57` (`open-failed`) and `:94` (`control-failed`)."""
    from skellycam.core.camera.capture.source import ControlSetting
    from skellycam.core.camera.config.camera_config import CameraConfig
    from skellycam.tests.capture.capture_session import OpenCVFakeFactory

    factory = OpenCVFakeFactory(monkeypatch, fail_open=(0,) if case == "open fails" else ())
    camera_id = factory.camera_ids[0]
    source = factory(CameraConfig(camera_id=camera_id, camera_index=0))
    request = product(SOURCE_MODULE).CaptureRequest(camera_id=camera_id, width=640, height=480, framerate=30.0)
    failure_type = product(SOURCE_MODULE).CaptureFailure
    if case == "open fails":
        with pytest.raises(failure_type) as error:
            source.open(request)
        assert (error.value.stage, error.value.code) == ("open", "open-failed")
        return
    source.open(request)
    try:
        with pytest.raises(failure_type) as error:
            source.set_controls({"white_balance": ControlSetting(auto=False, value=4000)})
        assert (error.value.stage, error.value.code) == ("set controls", "control-failed")
    finally:
        source.close()


def test_t_unx_64_the_failure_object_has_a_code(monkeypatch):
    """T-UNX-64: the failure object of the apply response and of the status has `code` beside `stage` and
    `reason` (W 12); the codes of the other cameras stay empty."""
    with capture_app(monkeypatch, [FakeScript(), FakeScript(fail_opens=(1,))]) as app:
        app.detect()
        good, failed = app.factory.camera_ids
        response = app.apply([app.config(good), app.config(failed)])
        assert response.status_code == 200, response.text
        app.wait_state(good, "ready")
        assert response.json()["camera_failures"][failed]["code"] == "open-failed"
        assert app.status(good)["failure"] is None


WINDOWS_ONLY = pytest.mark.skipif(sys.platform != "win32", reason="the media_foundation package is Windows only (U18)")


@WINDOWS_ONLY
def test_t_unx_77_hresults_to_codes():
    """T-UNX-77: in-use HRESULTs give `camera-in-use`; removal HRESULTs give `device-removed`; `0x800718CF`
    gives `usb-bandwidth`; `0x80004005` gives `open-failed` at open and `stream-error` in streaming. The
    reason text of 6.7 stays."""
    errors, source = product("skellycam.core.camera.capture.media_foundation.errors"), product(SOURCE_MODULE)

    def raised(hresult, stage):
        with pytest.raises(source.CaptureFailure) as error:
            errors.check(hresult, stage)
        return error.value

    for hresult in (0xC00D3704, 0xC00D3EA3, 0x80070964, 0x800700AA):
        failure = raised(hresult, "open")
        assert (failure.code, failure.reason) == ("camera-in-use", "in use by another program"), hex(hresult)
    for hresult in (0xC00D3EA2, 0x80070651, 0x8007048F, 0x800701B1):
        failure = raised(hresult, "streaming")
        assert (failure.code, failure.reason) == ("device-removed", "device removed"), hex(hresult)
    failure = raised(0x800718CF, "start stream")
    assert (failure.code, failure.reason) == ("usb-bandwidth", "USB_INSUFFICIENT_BANDWIDTH")
    assert raised(0x80004005, "open").code == "open-failed"
    assert raised(0x80004005, "streaming").code == "stream-error"
    assert errors.hresult_code(0x800718CF, "streaming") == "usb-bandwidth"
    assert errors.hresult_code(-0x7FFFBFFB, "set mode") == "open-failed"  # a signed E_FAIL, as ctypes gives it
