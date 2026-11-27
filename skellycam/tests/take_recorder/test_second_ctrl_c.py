"""A second Ctrl-C ends every process and releases each hold (specs/recorder.md 9.1 item 9, Q934, Q977 [ADR-F7BK]).

Q934, the words of the user: a second manual Ctrl-C is "abort now, something has gone wrong"; the goal is that all
processes stop and release any holds and locks; cleaning up the recording would be nice, but is not expected. The
real server of `__main__` with two fake camera processes (`server_take_child.py`) records. The first Ctrl-C comes
during a slow take stop (a stop request waits for its cameras) or during a take (the lifespan end then stops it,
slowly); the second Ctrl-C comes 1 s or more after the server took the first (`SECOND_CTRL_C_AFTER_S`). On Windows
the keyboard Ctrl-C goes to the hidden console of the server (`GenerateConsoleCtrlEvent`), or Ctrl-Break to its
process group; elsewhere SIGINT goes to its process group, as a terminal sends it.

After the second Ctrl-C: the server and each process that it started end; no frame ring can be attached; the port
binds again at once; the take folder can be renamed and its lock taken. The manifest may stay `recording`. The
handler made the abort with the kill flag, and no camera process was ended with `terminate` or `kill` (each one ended
at the kill flag). With a take stop that hangs, the forced exit ends the server (exit code 1). A press that gives two signals
less than 1 s apart is one ordinary quit. Split tests (Q619): the blocking halves check what happens within `HANG_S`,
the `pace` halves check the times.
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
HANG = -1.0  # the wait of a take stop hangs for ever
HANG_S = 60.0  # the blocking half: a process that lives longer hangs
END_S = 8.0  # the pace half: each process ends within this time of the second Ctrl-C (9.1 item 9)
FORCED_S = 5.0  # 9.1 item 9: the forced exit comes this long after the abort
REPEAT_GAP_S = 0.1  # two signals of one press
WINDOWS = sys.platform == "win32"
SIGNALS = ["ctrl-c", "ctrl-break"] if WINDOWS else ["sigint"]
CTRL_C_HELPER = r"""
import ctypes, sys, time
kernel = ctypes.windll.kernel32
kernel.FreeConsole()
if not kernel.AttachConsole(int(sys.argv[1])):
    sys.exit(2)
kernel.SetConsoleCtrlHandler(None, True)
for index in range(int(sys.argv[2])):
    if index:
        time.sleep(float(sys.argv[3]))
    if not kernel.GenerateConsoleCtrlEvent(0, 0):
        sys.exit(3)
"""


def _start_server(tmp_path, port, kind, slow_s):
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
                                   str(tmp_path / "server.log"), str(slow_s), str(tmp_path / "times.jsonl")],
                                  stdout=out, stderr=subprocess.STDOUT, **flags)
    return server, log


def _send(server, kind, count=1):
    """`count` signals, `REPEAT_GAP_S` apart, as one press that gives more than one signal."""
    if kind == "ctrl-c":
        sent = subprocess.run([sys.executable, "-c", CTRL_C_HELPER, str(server.pid), str(count), str(REPEAT_GAP_S)],
                              creationflags=subprocess.DETACHED_PROCESS).returncode
        assert sent == 0, f"the Ctrl-C helper failed with {sent}"
        return
    for index in range(count):
        if index:
            time.sleep(REPEAT_GAP_S)
        if kind == "ctrl-break":
            os.kill(server.pid, signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(os.getpgid(server.pid), signal.SIGINT)


def _events(times_file, event):
    if not times_file.exists():
        return []
    items = [json.loads(line) for line in times_file.read_text(encoding="utf-8").splitlines()]
    return [item for item in items if item["event"] == event]


def _wait_for(times_file, event, count, server, limit_s=30.0):
    deadline = time.monotonic() + limit_s
    while len(_events(times_file, event)) < count:
        assert server.poll() is None, f"the server ended before it got {event} number {count}"
        assert time.monotonic() < deadline, f"the server did not get {event} number {count}"
        time.sleep(0.02)
    return _events(times_file, event)


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


def _run(tmp_path, kind, phase, slow_s=SLOW_S, press="two"):
    """`press`: "two" (a second Ctrl-C 1 s or more after the first) or "repeat" (one press, two signals)."""
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
    server, log = _start_server(tmp_path, port, kind, slow_s)
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
                                                  timeout=120.0), daemon=True).start()
            _wait_for_the_take_end_start(times_file, server, log)
        if press == "repeat":
            _send(server, kind, count=2)
            gaps = [item["time"] for item in _wait_for(times_file, "ctrl", 2, server)]
            second = time.monotonic()
        else:
            _send(server, kind)
            first = _wait_for(times_file, "signal", 1, server)[0]["time"]  # uvicorn took the first
            if phase == "take":
                _wait_for_the_take_end_start(times_file, server, log)  # the lifespan end stops the take, slowly
            time.sleep(max(0.0, first + 1.2 - time.time()))  # 9.1 item 9: 1 s or more after the first
            _send(server, kind)
            gaps = [item["time"] for item in _wait_for(times_file, "signal", 2, server)]
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
        code = server.wait(timeout=5) if not alive else None
        names = next((item["names"] for item in _events(times_file, "rings")), [])
        try:
            manifest = json.loads((recordings / "take" / "recording_manifest.json").read_text(encoding="utf-8"))["state"]
        except (OSError, ValueError) as error:
            manifest = repr(error)
        return {"left": sorted(alive), "end_s": max(ends.values(), default=None), "code": code,
                "gap_s": gaps[1] - gaps[0], "aborts": len(_events(times_file, "abort")), "manifest": manifest,
                "kill_flag": [item["kill_flag"] for item in _events(times_file, "abort")],
                "collect_ended_by_a_camera": [item["camera_ended"] for item in _events(times_file, "collect")],
                "terminated": [item["name"] for event in ("terminate", "kill") for item in _events(times_file, event)],
                "held": _held(port, names, recordings / "take")}
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
    assert (result["left"], result["held"], result["code"]) == ([], [], 0), result
    # the handler set the kill flag, and each camera process ended at it: none was ended by terminate or kill
    assert (result["aborts"], result["kill_flag"], result["terminated"]) == (1, [True], []), result
    # the slow wait of the take stop ended because a camera process ended (at the kill flag), not at its time
    assert result["collect_ended_by_a_camera"] == [True], result


@pytest.mark.pace
@pytest.mark.parametrize("phase", ["stop", "take"])
@pytest.mark.parametrize("kind", SIGNALS)
def test_a_second_ctrl_c_ends_every_process_within_its_bound(tmp_path, kind, phase):
    result = one_run(("second ctrl-c", kind, phase), lambda: _run(tmp_path, kind, phase))
    assert result["left"] == [] and result["end_s"] <= bound(END_S - 3.0, END_S), result


@pytest.mark.parametrize("phase", ["stop", "take"])
@pytest.mark.parametrize("kind", SIGNALS)
def test_a_hung_take_stop_ends_with_the_forced_exit(tmp_path, kind, phase):
    """Q977: the take stop hangs (a disk call that never returns). After the second Ctrl-C, the camera processes end
    at the kill flag, and the forced exit ends the server with exit code 1; the port is free and no ring is held."""
    result = one_run(("forced exit", kind, phase), lambda: _run(tmp_path, kind, phase, slow_s=HANG))
    assert (result["left"], result["held"], result["code"], result["aborts"]) == ([], [], 1, 1), result


@pytest.mark.pace
@pytest.mark.parametrize("phase", ["stop", "take"])
@pytest.mark.parametrize("kind", SIGNALS)
def test_the_forced_exit_comes_5_s_after_the_abort(tmp_path, kind, phase):
    result = one_run(("forced exit", kind, phase), lambda: _run(tmp_path, kind, phase, slow_s=HANG))
    assert result["left"] == [] and FORCED_S - 0.5 <= result["end_s"] <= bound(FORCED_S + 1.0, FORCED_S + 3.0), result


@pytest.mark.pace
@pytest.mark.parametrize("kind", SIGNALS)
def test_one_press_with_two_signals_is_an_ordinary_quit(tmp_path, kind):
    """The review of e9eef6e1c: two signals `REPEAT_GAP_S` apart (a launcher that forwards SIGINT while the terminal
    signals the process group, or key repeat) are one press: no abort, and the take ends `finished`. A `pace` test:
    it needs the two signals to come less than 1 s apart; the unit test of the handler checks the drop with no
    timing."""
    result = one_run(("repeat", kind), lambda: _run(tmp_path, kind, "stop", slow_s=4.0, press="repeat"))
    assert result["gap_s"] < 1.0, f"the two signals came {result['gap_s']:.2f} s apart, not as one press"
    assert (result["aborts"], result["manifest"], result["left"], result["code"]) == (0, "finished", [], 0), result
