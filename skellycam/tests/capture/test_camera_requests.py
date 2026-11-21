"""Part 1 of specs/camera-requests.md (exposure): the tests T-REQ of code step 3 with the fake sources.

Each test runs THREAD workers with the virtual clock of `capture_session`, unless it says else. The fixture
`no_camera_auto_exposure` is the spy of T-REQ-15: no exposure set of a test in this file has `auto=True`,
except the restore at the close.
"""

import cv2
import pytest

from skellycam.tests.capture.capture_session import capture_app, ready_app_steps
from skellycam.tests.capture.fake_source import FakeScript

pytestmark = pytest.mark.usefixtures("no_camera_auto_exposure")


def exposure_sets(app, camera_id):
    """(auto, value) of each exposure set of the fake, in order."""
    return [(s["exposure"].auto, s["exposure"].value) for s in app.factory.logs[camera_id].settings if "exposure" in s]


# ---------------------------------------------------------------------------
# 1.1, 1.5: the config and the modes (T-REQ-14, T-REQ-15)
# ---------------------------------------------------------------------------

def test_t_req_14_default_config_and_the_mode_values():
    """T-REQ-14, 1.5 [G1, G6, H7]: the default of `CameraConfig()` is `AUTO`, -7, `exposure_found_at_fps` None;
    `RECOMMEND` is read as `AUTO`; each other mode value is refused."""
    from pydantic import ValidationError

    from skellycam.core.camera.config.camera_config import CameraConfig

    config = CameraConfig()
    assert (config.exposure_mode, config.exposure, config.exposure_found_at_fps) == ("AUTO", -7, None)
    assert CameraConfig(exposure_mode="RECOMMEND").exposure_mode == "AUTO"
    assert CameraConfig(exposure_mode="MANUAL").exposure_mode == "MANUAL"
    with pytest.raises(ValidationError):
        CameraConfig(exposure_mode="CAMERA")


def test_t_req_14_same_config_ignores_the_found_rate_number_and_name():
    """T-REQ-14, 1.5 [H6, AC5B]: `same_config` ignores `exposure_found_at_fps`, `camera_index` and
    `camera_name`; for `AUTO` it ignores `exposure` (the held value of the server)."""
    from skellycam.core.camera.config.camera_config import CameraConfig
    from skellycam.core.camera_group.camera_group import same_config

    current = CameraConfig(camera_id="a1", camera_index=0, camera_name="one", exposure_mode="AUTO", exposure=-9,
                           exposure_found_at_fps=30.0, framerate=30.0)
    request = current.model_copy(update=dict(camera_index=3, camera_name="three", exposure_found_at_fps=None,
                                             exposure=-7))
    assert same_config(request, current)
    assert not same_config(request.model_copy(update=dict(exposure_mode="MANUAL")), current)
    assert not same_config(request.model_copy(update=dict(framerate=60.0)), current)


def test_t_req_14_the_apply_request_reads_recommend_as_auto_and_refuses_other_modes(monkeypatch):
    """T-REQ-14 [G6]: an apply request with `RECOMMEND` stores `AUTO`; `CAMERA` gets 422. A same config with
    another `camera_index` and `camera_name` makes no set call, and the new number and name are stored."""
    with capture_app(monkeypatch, [FakeScript()]) as app:
        camera_id = app.factory.camera_ids[0]
        app.detect()
        bad = app.config(camera_id).model_dump(mode="json")
        bad["exposure_mode"] = "CAMERA"
        refused = app.client.post("/skellycam/camera/group/apply", json={"camera_configs": {camera_id: bad}})
        assert refused.status_code == 422, refused.text
        ready_app_steps(app)
        settings = len(app.factory.logs[camera_id].settings)
        same = app.apply([app.config(camera_id, camera_index=4, camera_name="renamed", exposure_found_at_fps=30.0)])
        assert same.status_code == 200, same.text
        stored = app.group.configs[camera_id]
        assert (stored.camera_index, stored.camera_name) == (4, "renamed")
        assert not [s for s in app.factory.logs[camera_id].settings[settings:] if s]
        body = app.config(camera_id).model_dump(mode="json")
        body["exposure_mode"] = "RECOMMEND"
        response = app.client.post("/skellycam/camera/group/apply", json={"camera_configs": {camera_id: body}})
        assert response.status_code == 200, response.text
        assert response.json()["camera_configs"][camera_id]["exposure_mode"] == "AUTO"


def test_t_req_15_an_auto_open_sets_its_held_value_as_a_manual_value(monkeypatch):
    """T-REQ-15, 1.3a [A7, G1]: a camera in `AUTO` held at -9 sets -9 with `auto=False` at the open (9.1 step 5).
    The camera's own auto exposure is never requested (the spy of this file)."""
    with capture_app(monkeypatch, [FakeScript()]) as app:
        camera_id = app.factory.camera_ids[0]
        app.detect()
        response = app.apply([app.config(camera_id, exposure_mode="AUTO", exposure=-9, exposure_found_at_fps=30.0)])
        assert response.status_code == 200, response.text
        assert exposure_sets(app, camera_id)[0] == (False, -9)
        assert response.json()["camera_configs"][camera_id]["exposure_mode"] == "AUTO"


# ---------------------------------------------------------------------------
# 1.7: the OpenCV exposure on each system
# ---------------------------------------------------------------------------

def _capture():
    """A stand-in `cv2.VideoCapture` (the beartype check of the product wants the type) that keeps each call."""
    from unittest.mock import Mock

    capture = Mock(spec=cv2.VideoCapture)
    capture.get.side_effect = lambda prop: -8.0 if prop == cv2.CAP_PROP_EXPOSURE else -1
    return capture


@pytest.mark.parametrize("platform", ["win32", "linux", "darwin"])
@pytest.mark.parametrize("mode", ["MANUAL", "AUTO"])
def test_t_req_21_opencv_apply_exposure_on_each_system(monkeypatch, platform, mode):
    """T-REQ-21 (1), 1.7 [Q11, K2, AC5B]: on Linux and macOS `_apply_exposure` sets the camera's auto exposure for
    `MANUAL` and `AUTO`. On Windows `AUTO` makes no exposure call (the loop sets the held value, then searches),
    and `MANUAL` sets the manual value."""
    from skellycam.core.camera.config.camera_config import CameraConfig
    from skellycam.core.camera.opencv.opencv_helpers import opencv_apply_config as module

    monkeypatch.setattr(module.sys, "platform", platform)
    capture = _capture()
    module._apply_exposure(capture, CameraConfig(exposure_mode=mode, exposure=-8))
    calls = [c.args for c in capture.set.call_args_list]
    if platform != "win32":
        assert calls == [(cv2.CAP_PROP_AUTO_EXPOSURE, module.AUTO_EXPOSURE_SETTING)]
    elif mode == "AUTO":
        assert calls == []
    else:
        assert calls == [(cv2.CAP_PROP_AUTO_EXPOSURE, module.MANUAL_EXPOSURE_SETTING),
                                 (cv2.CAP_PROP_EXPOSURE, -8.0)]


@pytest.mark.parametrize("platform", ["win32", "linux", "darwin"])
def test_opencv_source_forces_auto_exposure_on_linux_and_macos_only(monkeypatch, platform):
    """1.7 [AC5B]: the OpenCV source sets the camera's auto exposure on Linux and macOS for each set; on Windows a
    manual set stays manual. It searches only on Windows."""
    from skellycam.core.camera.capture import opencv_source
    from skellycam.core.camera.capture.source import ControlSetting
    from skellycam.core.camera.config.camera_config import CameraConfig

    monkeypatch.setattr(opencv_source.sys, "platform", platform)
    source = opencv_source.OpenCVSource(CameraConfig())
    source._capture = _capture()
    readback = source.set_controls({"exposure": ControlSetting(auto=False, value=-8)})
    assert readback["exposure"].auto is (platform != "win32")
    assert source.searches is (platform == "win32")
