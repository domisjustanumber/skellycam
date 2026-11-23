"""T-UNX-96 to T-UNX-100: the restore record on disk (specs/unix-capture.md 4.7.1; a decision of the user of
2026-11-23, Q608).

The server writes the "before" values of each camera to `<folder>/<camera_id>.json` when it first sets a control of
that camera, and removes the file after a restore with no failure. A new server reads the file at the group
creation and uses it under the rule of the record in memory (4.7). A "server kill" here is a camera that stalls
(a wedge: its close sets no control, so the record stays), then a new `CameraGroupManager` with an empty memory,
the same folder and the same fake cameras (THREAD workers, the virtual clock). The fake cameras keep their
control values from one open to the next, as real cameras do.
"""

import json
import logging

import pytest

from skellycam.tests.capture.capture_session import CaptureApp, capture_logs, product
from skellycam.tests.capture.fake_source import FakeScript, FakeSourceFactory, VirtualClock

AUTO_BEFORE = (("exposure", True, True, -6), ("gain", True, False, 0), ("focus", True, True, 30))
MANUAL_BEFORE = (("exposure", True, False, -4), ("gain", True, False, 0), ("focus", True, True, 30))
STORE_MODULE = "skellycam.core.camera.capture.restore_store"


def server(monkeypatch, factory, folder):
    """A new server: a new manager (no record in memory) with the restore folder, over the same fake cameras."""
    return CaptureApp(monkeypatch, factory, restore_store=folder)


def open_all(app):
    app.detect()
    response = app.apply([app.config(camera_id) for camera_id in app.factory.camera_ids])
    assert response.status_code == 200, response.text
    for camera_id in app.factory.camera_ids:
        app.wait_state(camera_id, "ready")


def stall_all(app):
    """A wedge: the close of a stalled camera sets no control, so the record stays (as after a kill)."""
    for camera_id in app.factory.camera_ids:
        app.factory.sources[camera_id].stop_now()
    for camera_id in app.factory.camera_ids:
        app.wait_state(camera_id, "dead")
        log = app.factory.logs[camera_id]
        app.wait(lambda: log.closes.value >= 1, "the close of the dead camera")


def end_server(app):
    app.close()


def file_of(folder, factory, camera_id):
    """The restore file of a fake camera: `<SHA-256 of the input of its camera_id>.json` (4.7.1)."""
    store = product(STORE_MODULE)
    device = next(info for info in factory.device_infos() if info.camera_id == camera_id)
    return store.entry_path(folder, store.identity(device)["key"])


def exposure(factory, camera_id):
    return factory.logs[camera_id].device_controls["exposure"][1:]


def test_t_unx_96_a_new_server_restores_a_camera_that_a_killed_server_left_in_manual(monkeypatch, tmp_path):
    """T-UNX-96: the first set writes the file (version 1, the USB IDs, no path); the record survives the server;
    the new server's close restores auto -6, and the file is gone."""
    factory = FakeSourceFactory([FakeScript(controls=AUTO_BEFORE, keeps_controls=True)], clock=VirtualClock())
    camera_id = factory.camera_ids[0]
    path = file_of(tmp_path, factory, camera_id)
    first = server(monkeypatch, factory, tmp_path)
    try:
        open_all(first)
        entry = json.loads(path.read_text(encoding="utf-8"))
        assert (entry["version"], entry["vendor_id"], entry["product_id"]) == (1, 0xFEED, 0)
        assert entry["key"] == path.stem and len(entry["key"]) == 64 and "camera_id" not in entry
        assert entry["record"]["names"] == ["exposure"] and entry["record"]["before"]["exposure"] == [True, True, -6]
        text = path.read_text(encoding="utf-8").lower()
        assert "usb#" not in text and "\\" not in text and "fake" not in text  # no link, no name (the key is a SHA-256)
        stall_all(first)
    finally:
        end_server(first)
    assert exposure(factory, camera_id) == [False, -7] and path.exists()  # no restore: the app's value stays
    second = server(monkeypatch, factory, tmp_path)
    try:
        open_all(second)
    finally:
        end_server(second)
    assert exposure(factory, camera_id) == [True, -6]
    assert not path.exists()


@pytest.mark.parametrize("content", [b"\x00{not json", json.dumps({"version": 2, "key": "x", "record": {}}).encode()],
                         ids=["not json", "another version"])
def test_t_unx_97_a_damaged_file_is_dropped_and_never_fails_the_open(monkeypatch, tmp_path, content):
    """T-UNX-97: a damaged file gives one log line and is removed; the open and the close have no error; the close
    restores the values that the camera read at this open (manual -4), not a value of the file."""
    factory = FakeSourceFactory([FakeScript(controls=MANUAL_BEFORE, keeps_controls=True)], clock=VirtualClock())
    camera_id = factory.camera_ids[0]
    path = file_of(tmp_path, factory, camera_id)
    path.write_bytes(content)
    with capture_logs() as logs:
        app = server(monkeypatch, factory, tmp_path)
        try:
            open_all(app)
            assert app.status(camera_id)["failure"] is None
        finally:
            end_server(app)
    assert exposure(factory, camera_id) == [False, -4]
    assert not path.exists()
    lines = [m for m in logs.messages(logging.WARNING) if "restore file" in m and camera_id in m]
    assert len(lines) == 1, lines


@pytest.mark.parametrize("case", ["same model", "other usb ids"])
def test_t_unx_98_two_cameras_of_one_model_keep_their_own_entries(monkeypatch, tmp_path, case):
    """T-UNX-98: two cameras with the same USB IDs (Media Foundation links: the port tells them apart), one in auto -6
    and one in manual -4 before the first server. Each restores its own values at the close of the new server.
    "other usb ids": the entry of camera 1 names other USB IDs than the camera with its `camera_id`: it is dropped,
    and camera 1 is not set back to manual -4 (it keeps manual -7, its value at the open of the new server)."""
    scripts = [FakeScript(controls=AUTO_BEFORE, keeps_controls=True, product_id=7),
               FakeScript(controls=MANUAL_BEFORE, keeps_controls=True, product_id=7)]
    factory = FakeSourceFactory(scripts, clock=VirtualClock())
    first_id, second_id = factory.camera_ids
    first = server(monkeypatch, factory, tmp_path)
    try:
        open_all(first)
        stall_all(first)
    finally:
        end_server(first)
    if case == "other usb ids":
        path = file_of(tmp_path, factory, second_id)
        entry = json.loads(path.read_text(encoding="utf-8"))
        entry["product_id"] = 99
        path.write_text(json.dumps(entry), encoding="utf-8")
    second = server(monkeypatch, factory, tmp_path)
    try:
        open_all(second)
    finally:
        end_server(second)
    assert exposure(factory, first_id) == [True, -6]
    assert exposure(factory, second_id) == ([False, -4] if case == "same model" else [False, -7])
    assert not list(tmp_path.glob("*.json"))


def test_t_unx_98_two_cameras_of_one_model_with_no_stable_identity_drop_their_entries(tmp_path):
    """T-UNX-98 (the rule of 4.7.1): two attached cameras with the USB IDs of an entry and no stable identity (no
    serial number, an OpenCV path that is not a Media Foundation link) cannot be told apart across a restart: the
    entry is dropped. With a serial number, or with one camera of that model, the entry is used."""
    store = product(STORE_MODULE)
    from skellycam.core.device_detection.detect_cameras_devices import CameraDeviceInfo

    record = {"before": {"exposure": [True, True, -6]}, "names": ["exposure"], "set": {"exposure": [False, -7]}}

    def devices(paths, serial=None):
        infos = [CameraDeviceInfo(index=i, name="Same", vendor_id=0x46D, product_id=0x85C, path=p, has_serial=serial)
                 for i, p in enumerate(paths)]
        return {info.camera_id: info for info in infos}

    for found, expected in [(devices(["opencv-index-0", "opencv-index-2"]), False),
                            (devices(["opencv-index-0", "opencv-index-2"], serial=True), True),
                            (devices(["opencv-index-0"]), True)]:
        camera_id, device = next(iter(found.items()))
        ident = store.identity(device)
        store.write_entry(tmp_path, ident, record)
        got = store.read_entries(tmp_path, [camera_id], found)
        assert (camera_id in got) is expected, (found, got)
        assert store.entry_path(tmp_path, ident["key"]).exists() is expected
        store.remove_entry(tmp_path, ident["key"])


def test_t_unx_99_the_entry_is_removed_after_a_restore(monkeypatch, tmp_path):
    """T-UNX-99: an open of a camera writes its file; a close whose restore has no failure removes it. A camera that
    the app never set has no file."""
    factory = FakeSourceFactory([FakeScript(controls=AUTO_BEFORE)], clock=VirtualClock())
    camera_id = factory.camera_ids[0]
    path = file_of(tmp_path, factory, camera_id)
    assert not path.exists()
    app = server(monkeypatch, factory, tmp_path)
    try:
        open_all(app)
        assert path.exists()
        app.client.delete("/skellycam/camera/group/close/all")
        log = app.factory.logs[camera_id]
        app.wait(lambda: log.closes.value == 1, "the close")
        assert app.factory.sources[camera_id].diagnostics()["restore_ok"] is True
    finally:
        end_server(app)
    assert not path.exists()


def test_t_unx_100_a_camera_whose_value_moved_more_than_one_step_drops_the_entry(monkeypatch, tmp_path):
    """T-UNX-100: after the killed server, another program set the camera to manual -9 (two steps from -7). The new
    server drops the entry at its first read: the file of its open holds manual -9 as the value of before, and its
    close sets manual -9, not auto -6."""
    factory = FakeSourceFactory([FakeScript(controls=AUTO_BEFORE, keeps_controls=True)], clock=VirtualClock())
    camera_id = factory.camera_ids[0]
    path = file_of(tmp_path, factory, camera_id)
    first = server(monkeypatch, factory, tmp_path)
    try:
        open_all(first)
        stall_all(first)
    finally:
        end_server(first)
    factory.logs[camera_id].device_controls["exposure"][1:] = [False, -9]
    second = server(monkeypatch, factory, tmp_path)
    try:
        open_all(second)
        assert json.loads(path.read_text(encoding="utf-8"))["record"]["before"]["exposure"] == [True, False, -9]
    finally:
        end_server(second)
    assert exposure(factory, camera_id) == [False, -9]
    assert not path.exists()
