"""A cancelled request does not cut a take start or a take stop (specs/recorder.md 9.1 item 3, Q928 [ADR-9V4Y]).

At its shutdown limit uvicorn cancels each request task that still runs, then the lifespan end closes the groups
(9.1). These tests cancel the task of a take stop, a take start and a close of all groups on the event loop of the
app, as uvicorn does, and then close the groups as the lifespan end does. The manifest must be `finished`, and each
camera must have the frame count of the take. Before the shield, the cancel ended `_end_take` in its wait for the
cameras: `take.finish` never ran and the manifest stayed `recording`; and a camera that had not reached the last
frame ended later with a frame count from frame 0 (`camera_loop._end_take` with no first frame), not the take's.

THREAD workers on the virtual clock, fake sources, synthetic JPEGs in tmp folders (as `test_connection.py`).
"""

import asyncio
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from skellycam.tests.capture.capture_session import Spies, capture_app, ready_app_steps, take_manifest, take_rows
from skellycam.tests.capture.fake_source import FakeScript
from skellycam.tests.take_recorder.test_connection import WriterHold, group_module, record_until, wait_blocked_in_give


async def _cancel_when(make, ready, limit_s=30.0):
    """Run `make()` as a task, cancel it when `ready()` is true, and say how it ended."""
    task = asyncio.ensure_future(make())
    deadline = time.monotonic() + limit_s
    while not ready():
        assert time.monotonic() < deadline, "the request never reached its wait"
        assert not task.done(), f"the request ended before the cancel: {task}"
        await asyncio.sleep(0.01)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        return "cancelled"
    return "done"


def _finish_spy(monkeypatch):
    """The frame counts that `Take.finish` gets."""
    from skellycam.core.take_recorder import Take

    finish, counts = Take.finish, []

    def spied(take, *args, **kwargs):
        counts.append(kwargs.get("frame_count"))
        return finish(take, *args, **kwargs)

    monkeypatch.setattr(Take, "finish", spied)
    return counts


def _rows(tmp_path, camera_ids):
    counts = {}
    for camera_id in camera_ids:
        try:
            counts[camera_id] = len(take_rows(tmp_path, camera_id))
        except Exception as error:  # an unfinished file
            counts[camera_id] = repr(error)
    return counts


def _close_as_the_lifespan(app):
    app.client.portal.call(app.manager.close_all_camera_groups)


def _held_stop_case(monkeypatch, tmp_path, request):
    """One camera holds its writer, so the stop waits for it in `_collect_results`; `request` is cancelled there."""
    module = group_module()
    monkeypatch.setattr(module, "TAKE_QUEUE_SECONDS", 0.2)
    monkeypatch.setattr(module, "TAKE_STALL_LIMIT_S", 60.0)  # the hold is no stall
    collecting, expected = threading.Event(), []
    collect = module.CameraGroup._collect_results

    def watched_collect(group):
        expected.append(group.cameras.orchestrator.take_frame_count())  # the frame count that the stop set
        collecting.set()
        return collect(group)

    monkeypatch.setattr(module.CameraGroup, "_collect_results", watched_collect)
    finished = _finish_spy(monkeypatch)
    with capture_app(monkeypatch, [FakeScript(), FakeScript()]) as app:
        spies = Spies(monkeypatch, app)
        hold = WriterHold(monkeypatch, app.factory.camera_ids[0])
        ready_app_steps(app)
        assert app.record_start(tmp_path).status_code == 200
        record_until(app, spies, 30)
        hold.start()
        wait_blocked_in_give(app, spies, hold)
        make = {"stop": app.group.stop_recording, "close all": app.manager.close_all_camera_groups}[request]
        ended = app.client.portal.call(_cancel_when, make, collecting.is_set)
        hold.stop()
        _close_as_the_lifespan(app)
        camera_ids = list(app.factory.camera_ids)
    return ended, finished, camera_ids, expected


@pytest.mark.parametrize("request_kind", ["stop", "close all"])
def test_a_cancelled_take_stop_still_finishes_the_take(monkeypatch, tmp_path, request_kind):
    """A cancel of `/record/stop` (or of `DELETE /group/close/all`, whose close stops the take) while the stop waits
    for a camera: the take ends anyway, then the close of the lifespan finds no take (409, handled). The manifest is
    `finished`; each camera has the frame count of the take."""
    ended, finished, camera_ids, expected = _held_stop_case(monkeypatch, tmp_path, request_kind)
    assert ended == "cancelled"
    state, rows = take_manifest(tmp_path)["state"], _rows(tmp_path, camera_ids)
    assert all(count == expected[0] for count in rows.values()) and expected[0] > 0, (state, expected, rows)
    assert (state, finished) == ("finished", expected[:1]), (state, finished, rows)


def test_a_cancelled_take_start_still_finishes_the_take(monkeypatch, tmp_path):
    """A cancel of `/record/start` while `start_take` runs in its thread: the start completes, and the close of the
    lifespan stops the take. The manifest is `finished`; each camera has the frame count of the take. Before the
    shield, the thread made the take folder and its `recording` manifest, and nobody finished it."""
    from skellycam.core.recorders.videos.recording_info import RecordingInfo

    module = group_module()
    finished = _finish_spy(monkeypatch)
    starting = threading.Event()
    with capture_app(monkeypatch, [FakeScript(), FakeScript()]) as app:
        start_take = module.start_take

        def slow_start_take(*args, **kwargs):
            starting.set()
            time.sleep(0.5)  # the cancel comes while the take folder is made
            return start_take(*args, **kwargs)

        monkeypatch.setattr(module, "start_take", slow_start_take)
        spies = Spies(monkeypatch, app)
        ready_app_steps(app)
        info = RecordingInfo(recording_name="take", recording_directory=str(tmp_path))
        ended = app.client.portal.call(_cancel_when, lambda: app.manager.start_recording_all_groups(info),
                                       starting.is_set)
        app.wait(lambda: app.group.take is not None, "the shielded start ends", timeout=10)
        record_until(app, spies, 10)
        _close_as_the_lifespan(app)
        camera_ids = list(app.factory.camera_ids)
    assert ended == "cancelled"
    state, rows = take_manifest(tmp_path)["state"], _rows(tmp_path, camera_ids)
    assert (state, len(finished)) == ("finished", 1), (state, finished, rows)
    assert all(count == finished[0] for count in rows.values()) and finished[0] > 0, (finished, rows)


# ----- the real server and a real signal -----

SERVER_CHILD = Path(__file__).with_name("server_take_child.py")
SLOW_STOP_S = 8.0  # longer than the shutdown limit of 9.1 item 5: the signal comes while the stop waits


def _http(port, method, path, body=None, timeout=10.0):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(f"http://localhost:{port}{path}", data=data, method=method,
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def _signal_the_server(server):
    """Ctrl-Break to the process group of the server on Windows (uvicorn takes SIGBREAK), SIGINT elsewhere."""
    if sys.platform == "win32":
        os.kill(server.pid, signal.CTRL_BREAK_EVENT)
    else:
        os.kill(server.pid, signal.SIGINT)


def test_a_signal_during_a_slow_take_stop_ends_with_the_take_finished(tmp_path):
    """Q928: the real server of `__main__` with two fake cameras records; a take stop waits for its cameras for
    `SLOW_STOP_S`; then the server gets a real Ctrl-Break (Windows) or SIGINT. The process ends with exit code 0,
    the manifest is `finished` with no `camera_dead`, and each camera has the same rows, more than zero, with a
    finished file (recorder.md 9.1 items 3 and 4)."""
    from skellycam.core.camera.config.camera_config import CameraConfig
    from skellycam.core.camera.config.image_resolution import ImageResolution
    from skellycam.tests.capture.fake_source import FakeSourceFactory

    factory = FakeSourceFactory([FakeScript(), FakeScript()])
    configs = {}
    for index, camera_id in enumerate(factory.camera_ids):
        width, height, fps_num, fps_den, _ = factory.scripts[index].modes[0]
        configs[camera_id] = CameraConfig(camera_id=camera_id, camera_index=index,
                                          resolution=ImageResolution(width=width, height=height),
                                          framerate=round(fps_num / fps_den, 2), exposure_mode="MANUAL",
                                          exposure=-7).model_dump(mode="json")
    with socket.socket() as probe:
        probe.bind(("localhost", 0))
        port = probe.getsockname()[1]
    group = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if sys.platform == "win32" else {
        "start_new_session": True}
    log = tmp_path / "server.out"
    recordings = tmp_path / "recordings"
    with open(log, "w") as out:
        server = subprocess.Popen([sys.executable, str(SERVER_CHILD), str(port), str(tmp_path / "base"),
                                   str(tmp_path / "server.log"), str(SLOW_STOP_S)],
                                  stdout=out, stderr=subprocess.STDOUT, **group)
    stops = []
    try:
        deadline = time.monotonic() + 60
        while True:
            try:
                if _http(port, "GET", "/health", timeout=1.0)[0] == 200:
                    break
            except OSError:
                pass
            assert server.poll() is None and time.monotonic() < deadline, log.read_text(errors="replace")[-3000:]
            time.sleep(0.2)
        assert _http(port, "POST", "/skellycam/camera/detect")[0] == 200
        status, text = _http(port, "POST", "/skellycam/camera/group/apply",
                             {"camera_configs": configs, "retry_camera_ids": []}, timeout=60.0)
        assert status == 200, text
        body = {"recording_name": "take", "recording_directory": str(recordings)}
        while (started := _http(port, "POST", "/skellycam/camera/group/all/record/start", body))[0] != 200:
            assert started[0] == 409 and time.monotonic() < deadline, started  # the cameras are not ready yet
            time.sleep(0.2)
        time.sleep(1.5)
        stopper = threading.Thread(target=lambda: stops.append(
            _http(port, "POST", "/skellycam/camera/group/all/record/stop", timeout=60.0)), daemon=True)
        stopper.start()
        time.sleep(1.0)  # the stop waits in `_collect_results`
        _signal_the_server(server)
        code = server.wait(timeout=60)
    finally:
        if server.poll() is None:
            server.kill()
            server.wait()
    manifest = take_manifest(recordings)
    state, dead = manifest["state"], [w for w in manifest["warnings"] if w["code"] == "camera_dead"]
    assert (code, dead) == (0, []), (code, dead, log.read_text(errors="replace")[-3000:])
    rows = _rows(recordings, factory.camera_ids)
    assert state == "finished", (state, rows, log.read_text(errors="replace")[-3000:])
    counts = list(rows.values())
    assert all(isinstance(count, int) for count in counts) and counts[0] == counts[1] > 0, rows
