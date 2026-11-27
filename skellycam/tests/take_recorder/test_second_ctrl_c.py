"""A second Ctrl-C ends every process and releases each hold (specs/recorder.md 9.1 item 9, Q934).

Q934 of the user: a second Ctrl-C means "abort now, something has gone wrong": every process must stop and release
each hold and lock; a clean take is not expected. The real server of `__main__` with two fake camera processes
(`server_take_child.py`) records. The first Ctrl-C comes during a slow take stop (a stop request waits for its
cameras) or during a take (the lifespan end then stops it, slowly); the second Ctrl-C comes after the server took
the first. On Windows the keyboard Ctrl-C goes to the hidden console of the server (`GenerateConsoleCtrlEvent`), or
Ctrl-Break to its process group; elsewhere SIGINT goes to its process group, as a terminal sends it.

After the second Ctrl-C: the server and each process that it started end; no frame ring can be attached; the port
binds again at once; the take folder can be renamed and its lock taken. The manifest may stay `recording`. A split
test (Q619): the blocking half checks that it all happens within `HANG_S`, the `pace` half checks `END_S`.
"""

import json
import os
import signal
import socket
import subprocess
import sys
import time

import psutil
import pytest

from skellycam.tests.pace import bound, one_run
from skellycam.tests.take_recorder.test_take_end_cancel import (
    SERVER_CHILD, _http, _take_end_times, _wait_for_the_take_end_start)

SLOW_S = 12.0  # the wait of a take stop for its cameras: much longer than END_S
HANG_S = 60.0  # the blocking half: a process that lives longer hangs
END_S = 8.0  # the pace half: each process ends within this time of the second Ctrl-C (9.1 item 9)
WINDOWS = sys.platform == "win32"
SIGNALS = ["ctrl-c", "ctrl-break"] if WINDOWS else ["sigint"]
CTRL_C_HELPER = r"""
import ctypes, sys
kernel = ctypes.windll.kernel32
kernel.FreeConsole()
if not kernel.AttachConsole(int(sys.argv[1])):
    sys.exit(2)
kernel.SetConsoleCtrlHandler(None, True)
sys.exit(0 if kernel.GenerateConsoleCtrlEvent(0, 0) else 3)
"""


def _start_server(tmp_path, port, kind):
    if kind == "ctrl-c":  # its own hidden console, as a terminal window that gets the keyboard Ctrl-C
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = 0
        flags = dict(creationflags=subprocess.CREATE_NEW_CONSOLE, startupinfo=info)
    elif kind == "ctrl-break":
        flags = dict(creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    else:
        flags = dict(start_new_session=True)
    log = tmp_path / "server.out"
    with open(log, "w") as out:
        server = subprocess.Popen([sys.executable, str(SERVER_CHILD), str(port), str(tmp_path / "base"),
                                   str(tmp_path / "server.log"), str(SLOW_S), str(tmp_path / "times.jsonl")],
                                  stdout=out, stderr=subprocess.STDOUT, **flags)
    return server, log


def _send(server, kind):
    if kind == "ctrl-c":
        sent = subprocess.run([sys.executable, "-c", CTRL_C_HELPER, str(server.pid)],
                              creationflags=subprocess.DETACHED_PROCESS).returncode
        assert sent == 0, f"the Ctrl-C helper failed with {sent}"
    elif kind == "ctrl-break":
        os.kill(server.pid, signal.CTRL_BREAK_EVENT)
    else:
        os.killpg(os.getpgid(server.pid), signal.SIGINT)


def _wait_for_signals(times_file, count, server, limit_s=30.0):
    deadline = time.monotonic() + limit_s
    while len(_take_end_times(times_file).get("signal", [])) < count:
        assert server.poll() is None or count == 1, "the server ended before it took the second Ctrl-C"
        assert time.monotonic() < deadline, f"the server did not take Ctrl-C number {count}"
        time.sleep(0.02)


def _ring_names(times_file):
    for line in times_file.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        if item["event"] == "rings":
            return item["names"]
    return []


def _held(port, names, folder):
    """The holds that are still there: rings a reader can attach, a port that does not bind, a take folder that
    does not rename, a take lock that cannot be taken."""
    from skellycam.core.ipc.frame_ring import FrameRingReader
    from skellycam.core.take_recorder import folder_files

    held = []
    for name in names:
        try:
            reader = FrameRingReader.attach(name)
        except Exception:
            continue
        held.append(f"ring {name}")
        reader.close()
    with socket.socket() as again:
        try:
            again.bind(("localhost", port))
        except OSError as error:
            held.append(f"port {error!r}")
    try:
        with folder_files.take_lock(folder / folder_files.LOCK_NAME, 0.5):
            pass
    except OSError as error:
        held.append(f"take lock {error!r}")
    try:
        folder.rename(folder.with_name("renamed"))
    except OSError as error:
        held.append(f"take folder {error!r}")
    return held


def _run(tmp_path, kind, phase):
    from skellycam.core.camera.config.camera_config import CameraConfig
    from skellycam.core.camera.config.image_resolution import ImageResolution
    from skellycam.tests.capture.fake_source import FakeScript, FakeSourceFactory

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
    times_file, recordings = tmp_path / "times.jsonl", tmp_path / "recordings"
    server, log = _start_server(tmp_path, port, kind)
    tree = []
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
        tree = psutil.Process(server.pid).children(recursive=True)
        assert len(tree) >= 2, f"the camera processes did not start: {tree}"
        if phase == "stop":
            import threading

            threading.Thread(target=lambda: _http(port, "POST", "/skellycam/camera/group/all/record/stop",
                                                  timeout=60.0), daemon=True).start()
            _wait_for_the_take_end_start(times_file, server, log)
        _send(server, kind)
        _wait_for_signals(times_file, 1, server)
        if phase == "take":
            _wait_for_the_take_end_start(times_file, server, log)  # the lifespan end stops the take, slowly
        _send(server, kind)
        _wait_for_signals(times_file, 2, server)
        second = time.monotonic()
        alive = {process.pid: process for process in [psutil.Process(server.pid), *tree]}
        ends = {}
        while alive and time.monotonic() - second < HANG_S:
            for pid, process in list(alive.items()):
                try:
                    gone = not process.is_running() or process.status() == psutil.STATUS_ZOMBIE
                except psutil.NoSuchProcess:
                    gone = True
                if gone:
                    ends[pid] = time.monotonic() - second
                    del alive[pid]
            time.sleep(0.05)
        return {"left": sorted(alive), "end_s": max(ends.values(), default=None),
                "held": _held(port, _ring_names(times_file), recordings / "take")}
    finally:
        for process in [*tree]:
            try:
                if process.is_running():
                    process.kill()  # a process that the server of this test started (its tree)
            except psutil.Error:
                pass
        if server.poll() is None:
            server.kill()
            server.wait()


@pytest.mark.parametrize("phase", ["stop", "take"])
@pytest.mark.parametrize("kind", SIGNALS)
def test_a_second_ctrl_c_ends_every_process_and_releases_each_hold(tmp_path, kind, phase):
    result = one_run(("second ctrl-c", kind, phase), lambda: _run(tmp_path, kind, phase))
    assert (result["left"], result["held"]) == ([], []), result


@pytest.mark.pace
@pytest.mark.parametrize("phase", ["stop", "take"])
@pytest.mark.parametrize("kind", SIGNALS)
def test_a_second_ctrl_c_ends_every_process_within_its_bound(tmp_path, kind, phase):
    result = one_run(("second ctrl-c", kind, phase), lambda: _run(tmp_path, kind, phase))
    assert result["left"] == [] and result["end_s"] <= bound(END_S - 3.0, END_S), result
