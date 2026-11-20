"""A failed camera start says what was requested, what happened, why, and what to try (port from sfn26).

The failure objects are those of specs/windows-capture.md section 12. The manager gives the explanation as one
`start_failure` warning item of the apply response.
"""
import asyncio
import multiprocessing
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera_group import camera_group_manager as manager_module
from skellycam.core.camera_group import camera_start_failure as start_failure
from skellycam.core.camera_group.camera_group import CameraGroup
from skellycam.core.camera_group.camera_start_failure import explain_start_failure
from skellycam.core.ipc.process_management.worker_registry import WorkerRegistry


def configs(*camera_ids, fps=90.0):
    return {camera_id: CameraConfig(camera_id=camera_id, camera_index=index, resolution={"width": 1280, "height": 720},
                                    framerate=fps, capture_fourcc="MJPG")
            for index, camera_id in enumerate(camera_ids)}


def failure(camera_id, stage, reason):
    return {camera_id: dict(camera_id=camera_id, stage=stage, reason=reason)}


def detected(**connections):
    return [SimpleNamespace(camera_id=camera_id, usb_link=version) for camera_id, version in connections.items()]


def test_usb_reset_is_explained_with_connections_and_advice():
    text = explain_start_failure(failure("a272", "first frame", "no frame for 2 s"), configs("1b2b", "891e", "a272"),
                                 detected(**{"1b2b": "USB 3", "891e": "USB 2"}), usb_disconnects=11)
    assert "Could not start 1 of 3 camera(s) with these settings." in text
    assert "1b2b (USB 3): MJPG 1280×720 at 90 fps" in text and "891e (USB 2)" in text
    assert "a272 (USB link unknown)" in text
    assert "Camera a272 failed during first frame: no frame for 2 s." in text
    assert "Windows reported 11 USB device disconnection(s) during the start." in text
    assert "Not detected after the failure: a272." in text
    assert "USB controller reset" in text and "Lower the frame rate or resolution" in text


def test_a_camera_without_frames_is_explained_without_claiming_a_reset():
    text = explain_start_failure(failure("9412", "warm-up", "not ready in 15 s"), configs("1b2b", "9412", fps=30.0),
                                 detected(**{"1b2b": "USB 3", "9412": "USB 3"}), usb_disconnects=0)
    assert "in use by another program" in text and "Close other programs" in text
    assert "reset" not in text


def test_a_camera_that_cannot_open_is_explained():
    text = explain_start_failure(failure("1b2b", "open", "in use by another program"), configs("1b2b"),
                                 detected(**{"1b2b": "USB 3"}), usb_disconnects=None)
    assert "could not be opened" in text and "check its cable" in text


def test_a_reason_that_already_says_what_to_do_gets_no_explanation():
    reason = "declared 30.00 fps, measured 25.76 fps. Add light or shorten the exposure."
    assert explain_start_failure(failure("1b2b", "rate check", reason), configs("1b2b"),
                                 detected(**{"1b2b": "USB 3"}), usb_disconnects=0) is None


def test_ids_that_are_not_detection_ids_do_not_read_as_missing_cameras():
    text = explain_start_failure(failure("cam0", "open", "camera not found"), configs("cam0", "cam1"),
                                 detected(**{"1b2b": "USB 3"}), usb_disconnects=0)
    assert "Not detected after the failure" not in text


def test_default_frame_rate_is_named_as_such():
    text = explain_start_failure(failure("1b2b", "open", "camera not found"), configs("1b2b", fps=-1.0),
                                 detected(**{"1b2b": "USB 3"}), 0)
    assert "at the camera's default frame rate" in text


def test_a_failed_detection_still_gives_the_explanation(monkeypatch):
    def detection_fails():
        raise RuntimeError("no detection")

    monkeypatch.setattr(start_failure, "usb_disconnects_since", lambda started: None)
    text = start_failure.describe_start_failure(failure("1b2b", "open", "camera not found"), configs("1b2b"),
                                                start_failure.datetime.now(start_failure.timezone.utc),
                                                detection_fails)
    assert "1b2b (USB link unknown)" in text and "could not be opened" in text


def test_the_manager_adds_one_start_failure_warning(monkeypatch):
    registry = MagicMock(spec=WorkerRegistry)
    registry.heartbeat_timestamp = multiprocessing.Value("d", 0.0)
    manager = manager_module.CameraGroupManager(global_kill_flag=multiprocessing.Value("b", False),
                                                worker_registry=registry)
    requested = configs("1b2b", "891e")
    manager.detected_cameras = {camera.camera_id: camera for camera in detected(**{"1b2b": "USB 3", "891e": "USB 2"})}
    failures = failure("891e", "first frame", "no frame for 2 s")
    group = Mock(spec=CameraGroup, configs=requested)
    monkeypatch.setattr(manager, "_check_request", lambda camera_configs, camera_group: ([], True))
    monkeypatch.setattr(manager, "_create_and_start", AsyncMock(return_value=(group, failures)))
    requests = []

    def device_list(**kwargs):
        requests.append(kwargs)
        return detected(**{"1b2b": "unknown", "891e": "unknown"})  # a device list has no link; the stored detection has it

    monkeypatch.setattr(manager_module, "detect_available_cameras", device_list)
    monkeypatch.setattr(start_failure, "usb_disconnects_since", lambda started: None)

    _, returned_failures, warnings = asyncio.run(manager.create_or_update_camera_group(requested))
    assert returned_failures is failures  # the failure objects of section 12 do not change
    [item] = warnings
    assert item["kind"] == "start_failure" and item["camera_ids"] == ["891e"]
    assert "891e (USB 2): MJPG 1280×720 at 90 fps" in item["text"] and "sends no frames" in item["text"]
    assert requests == [dict(modes=False)]  # review item 4: the device list only; no camera is activated
