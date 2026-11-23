"""T-UNX-96 to T-UNX-101: the restore record on disk (specs/unix-capture.md 4.7.1; a decision of the user of
2026-11-23, Q608).

The server writes the "before" values of each camera to `<folder>/<key>.json` (an HMAC of the stable identity input
with the salt of the folder) when it first sets a control of
that camera, and removes the file after a restore with no failure. A new server reads the file at the group
creation and uses it under the rule of the record in memory (4.7). A "server kill" here is a camera that stalls
(a wedge: its close sets no control, so the record stays), then a new `CameraGroupManager` with an empty memory,
the same folder and the same fake cameras (THREAD workers, the virtual clock). The fake cameras keep their
control values from one open to the next, as real cameras do.
"""

import json
import logging
import sys

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
    """The restore file of a fake camera: `<HMAC of its Media Foundation link with the salt of the folder>.json`
    (4.7.1). The salt is made here when the folder has none, as the server makes it at its first use."""
    store = product(STORE_MODULE)
    device = next(info for info in factory.device_infos() if info.camera_id == camera_id)
    return store.entry_path(folder, store.identity(device, folder)["key"])


def entry_text(path, record, version=1, vendor_id=0xFEED, product_id=0):
    return json.dumps({"version": version, "key": path.stem, "vendor_id": vendor_id, "product_id": product_id,
                       "written_utc": "2026-11-23T00:00:00+00:00", "record": record})


def record_of(before, last, name="exposure"):
    return {"names": [name], "before": {name: before}, "set": {name: last}}


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


DAMAGED = {
    "not json": lambda path: b"\x00{not json",
    "another version": lambda path: json.dumps({"version": 0, "key": path.stem, "record": {}}).encode(),
    # the reviewer's case: the right shape, a string value; before, the open failed with a TypeError
    "a string value": lambda path: entry_text(path, record_of([True, True, -6], [False, "-4"])).encode(),
    "an unknown control": lambda path: entry_text(path, record_of([True, True, -6], [False, -4], "zoom")).encode(),
    "a boolean as a value": lambda path: entry_text(path, record_of([True, True, True], [False, -4])).encode(),
}


@pytest.mark.parametrize("case", list(DAMAGED))
def test_t_unx_97_a_damaged_file_is_dropped_and_never_fails_the_open(monkeypatch, tmp_path, case):
    """T-UNX-97: a damaged file gives one log line and is removed; the open and the close have no error and the
    camera is `ready`; the close restores the values that the camera read at this open (manual -4), not a value of the
    file. A record of the right shape with a wrong type or name is damaged too (4.7.1)."""
    factory = FakeSourceFactory([FakeScript(controls=MANUAL_BEFORE, keeps_controls=True)], clock=VirtualClock())
    camera_id = factory.camera_ids[0]
    path = file_of(tmp_path, factory, camera_id)
    path.write_bytes(DAMAGED[case](path))
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


def test_t_unx_97_a_before_value_outside_the_range_of_the_camera_is_not_set(monkeypatch, tmp_path):
    """T-UNX-97, 4.7.1: a valid entry whose manual "before" value (-40) is outside the exposure range of the camera
    at this open (-13 to 0), while the camera holds the value of this app (-7): the record drops that control, so no
    set gives -40, and the close sets the value that the camera read at this open (-7)."""
    factory = FakeSourceFactory([FakeScript(controls=MANUAL_BEFORE, keeps_controls=True)], clock=VirtualClock())
    camera_id = factory.camera_ids[0]
    path = file_of(tmp_path, factory, camera_id)
    first = server(monkeypatch, factory, tmp_path)
    try:
        open_all(first)
        stall_all(first)
    finally:
        end_server(first)
    path.write_text(entry_text(path, record_of([True, False, -40], [False, -7])), encoding="utf-8")
    second = server(monkeypatch, factory, tmp_path)
    try:
        open_all(second)
        assert second.status(camera_id)["failure"] is None
    finally:
        end_server(second)
    values = [change["exposure"].value for change in factory.logs[camera_id].settings if "exposure" in change]
    assert -40 not in values and exposure(factory, camera_id) == [False, -7]


def test_t_unx_97_a_file_of_a_later_version_stays_and_is_not_used(monkeypatch, tmp_path):
    """T-UNX-97, 4.7.1: a file of version 2 (a later app wrote it) is not used and stays as it is."""
    factory = FakeSourceFactory([FakeScript(controls=MANUAL_BEFORE, keeps_controls=True)], clock=VirtualClock())
    camera_id = factory.camera_ids[0]
    path = file_of(tmp_path, factory, camera_id)
    text = entry_text(path, record_of([True, True, -6], [False, -4]), version=2)
    path.write_text(text, encoding="utf-8")
    app = server(monkeypatch, factory, tmp_path)
    try:
        open_all(app)
        assert app.status(camera_id)["failure"] is None
        app.client.delete("/skellycam/camera/group/close/all")
        log = factory.logs[camera_id]
        app.wait(lambda: log.closes.value == 1, "the close")
    finally:
        end_server(app)
    assert exposure(factory, camera_id) == [False, -4]  # the value of this open, not auto -6 of the file
    assert path.read_text(encoding="utf-8") == text


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


def test_t_unx_98_the_identity_input_is_stable_and_never_a_device_number(tmp_path):
    """T-UNX-98 (4.7.1): a Media Foundation link gives its lower-case form; a Linux `/dev/video<n>` gives the USB
    interface of its sysfs folder (a fake tree), so two numbers of one port give one key; a Linux path with no sysfs
    folder, an OpenCV index and the USB IDs with the index give no input, so no file and no entry."""
    import os

    store = product(STORE_MODULE)
    from skellycam.core.device_detection.detect_cameras_devices import CameraDeviceInfo

    def device(path=None, index=0):
        return CameraDeviceInfo(index=index, name="Same", vendor_id=0x46D, product_id=0x85C, path=path)

    link = r"\\?\USB#VID_046D&PID_085C#ABC#{GUID}\global"
    assert store.identity_input(device(link)) == link.lower()
    assert store.identity_input(device("opencv-index-0")) is None and store.identity_input(device()) is None
    assert store.identity_input(device("/dev/video0"), tmp_path / "no sysfs") is None
    if sys.platform == "win32":
        return  # a sysfs folder name holds ":", which Windows refuses; the Linux job and WSL run the rest
    sys_root = tmp_path / "sys"
    interface = sys_root / "devices" / "pci0000:00" / "usb1" / "1-2" / "1-2.3" / "1-2.3:1.0"
    interface.mkdir(parents=True)
    for number in (0, 4):
        node = sys_root / "class" / "video4linux" / f"video{number}"
        node.mkdir(parents=True)
        os.symlink(interface, node / "device", target_is_directory=True)
    assert store.identity_input(device("/dev/video0"), sys_root) == "v4l2:port:1-2.3:1.0"
    assert store.identity_input(device("/dev/video4"), sys_root) == "v4l2:port:1-2.3:1.0"
    assert store.identity_input(device("/dev/video9"), sys_root) is None
    salt = bytes(32)
    first = store.identity(device("/dev/video0"), salt=salt, sys_root=sys_root)
    assert first == store.identity(device("/dev/video4"), salt=salt, sys_root=sys_root)
    assert store.identity(device("/dev/video9"), salt=salt, sys_root=sys_root) is None
    assert store.identity(device("/dev/video0"), salt=bytes([1]) * 32, sys_root=sys_root)["key"] != first["key"]


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


# ---------------------------------------------------------------------------
# T-UNX-101: the salt, the folder and the camera process
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("salt", ["missing", "damaged"])
def test_t_unx_101_a_missing_or_damaged_salt_uses_no_old_entry(monkeypatch, tmp_path, salt):
    """T-UNX-101: the first server leaves a record (a stall); then the salt is lost or damaged. The new server makes a
    new salt, removes the old entry files and uses none: its close restores what the camera reads (manual -7 of the
    first server), not auto -6."""
    factory = FakeSourceFactory([FakeScript(controls=AUTO_BEFORE, keeps_controls=True)], clock=VirtualClock())
    camera_id = factory.camera_ids[0]
    old = file_of(tmp_path, factory, camera_id)
    first = server(monkeypatch, factory, tmp_path)
    try:
        open_all(first)
        stall_all(first)
    finally:
        end_server(first)
    assert old.exists()
    salt_path = tmp_path / ".salt"
    if salt == "missing":
        salt_path.unlink()
    else:
        salt_path.write_text("not hex", encoding="ascii")
    second = server(monkeypatch, factory, tmp_path)
    try:
        open_all(second)
        assert not old.exists()
    finally:
        end_server(second)
    assert exposure(factory, camera_id) == [False, -7]
    assert len(bytes.fromhex(salt_path.read_text(encoding="ascii"))) == 32


def test_t_unx_101_a_temporary_file_of_an_ended_process_is_removed(tmp_path):
    """T-UNX-101: a kill between the write and the replace leaves `.<key>.<pid>.tmp`; the next read removes it when
    that process does not run, and keeps one of a live process."""
    import os

    import psutil

    store = product(STORE_MODULE)
    dead_pid = max(psutil.pids()) + 100_000
    stale = tmp_path / f".{'a' * 64}.{dead_pid}.tmp"
    live = tmp_path / f".{'b' * 64}.{os.getppid()}.tmp"
    stale.write_text("{", encoding="utf-8")
    live.write_text("{", encoding="utf-8")
    store.read_entries(tmp_path, [], {})
    assert not stale.exists() and live.exists()


def test_t_unx_101_a_folder_that_cannot_be_written_never_fails_an_open(monkeypatch, tmp_path):
    """T-UNX-101: the restore folder is a file. The camera opens `ready` and closes with its restore; one log line."""
    folder = tmp_path / "not a folder"
    folder.write_text("a file", encoding="utf-8")
    factory = FakeSourceFactory([FakeScript(controls=AUTO_BEFORE)], clock=VirtualClock())
    camera_id = factory.camera_ids[0]
    with capture_logs() as logs:
        app = server(monkeypatch, factory, folder)
        try:
            open_all(app)
            assert app.status(camera_id)["failure"] is None
        finally:
            end_server(app)
    lines = [m for m in logs.messages(logging.WARNING) if "restore file" in m or "salt of the restore files" in m]
    assert len(lines) == 1, lines


def test_t_unx_101_the_server_of_the_app_gets_the_folder_of_the_app(monkeypatch, tmp_path):
    """T-UNX-101: `get_or_create_camera_group_manager` gives `default_folder()`, `camera_restore` in the data folder of
    the app; each other manager gets no folder."""
    import skellycam.core.camera_group.camera_group_manager as manager_module
    import skellycam.system.default_paths as default_paths

    monkeypatch.setattr(default_paths, "get_default_skellycam_base_folder_path", lambda: str(tmp_path))
    monkeypatch.setattr(manager_module, "_CAMERA_GROUP_MANAGER", None)
    from fastapi import FastAPI

    import multiprocessing

    from skellycam.core.ipc.process_management.managed_worker import WorkerMode
    from skellycam.core.ipc.process_management.worker_registry import WorkerRegistry

    kill = multiprocessing.Value("b", False, lock=False)
    registry = WorkerRegistry(global_kill_flag=kill, worker_mode=WorkerMode.THREAD)
    app = FastAPI()
    app.state.global_kill_flag, app.state.worker_registry = kill, registry
    try:
        manager = manager_module.get_or_create_camera_group_manager(app)
        assert manager.restore_store == tmp_path / "camera_restore"
        assert manager_module.CameraGroupManager(global_kill_flag=kill, worker_registry=registry).restore_store is None
    finally:
        registry.shutdown_all()


def test_t_unx_101_a_camera_process_writes_its_file_and_a_kill_keeps_it(monkeypatch, tmp_path):
    """T-UNX-101 (the reviewer's case): PROCESS workers. The camera process writes the file with the values of before;
    after a kill of that process the file stays."""
    factory = FakeSourceFactory([FakeScript(controls=AUTO_BEFORE, keeps_controls=True)])
    camera_id = factory.camera_ids[0]
    path = file_of(tmp_path, factory, camera_id)
    app = CaptureApp(monkeypatch, factory, workers="process", restore_store=tmp_path)
    try:
        open_all(app)
        assert path.exists(), list(tmp_path.iterdir())
        assert json.loads(path.read_text(encoding="utf-8"))["record"]["before"]["exposure"] == [True, True, -6]
        worker = app.worker(camera_id).worker
        worker.kill()
        worker.join(timeout=10.0)
        assert path.exists()
    finally:
        app.close()
