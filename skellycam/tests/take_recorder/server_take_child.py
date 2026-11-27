"""The real server of `skellycam/__main__.py` with two fake cameras, for `test_take_end_cancel.py`.

argv: port, base folder, log file, slow seconds, times file. No telemetry, no bytecode pass, the base folder (also of
the restore files) and the log file in a temporary folder. Detection gives the fake cameras, and the camera processes
open fake sources. The wait of a take stop for the cameras (`_collect_results`) first waits the slow seconds, or until a camera
process ends. The
times file gets one JSON line when a take end (`_end_take`) starts and one when it ends, with the wall-clock time,
one line with the names of the frame rings when a group has started, and one line for each signal that
uvicorn takes.
"""

import json
import sys
import time

import uvicorn

import skellycam.__main__ as skellycam_main
import skellycam.api.http.cameras.camera_router as camera_router
import skellycam.api.server_constants as server_constants
import skellycam.app as app_module
import skellycam.core.camera_group.camera_group as group_module
import skellycam.core.camera_group.camera_group_manager as manager_module
import skellycam.system.default_paths as default_paths
from skellycam.tests.capture.fake_source import FakeScript, FakeSourceFactory

port, base_folder, log_file, slow_s, times_file = sys.argv[1:6]
if sys.platform == "win32":  # a keyboard console: Ctrl-C is on, also when the test runner started with it off
    import ctypes

    ctypes.windll.kernel32.SetConsoleCtrlHandler(None, False)
server_constants.PORT = int(port)
app_module.initialize_telemetry = lambda: None
app_module.shutdown_telemetry = lambda: None
app_module.ensure_bytecode_compiled = lambda: None
app_module.get_default_skellycam_base_folder_path = lambda: base_folder
default_paths.get_default_skellycam_base_folder_path = lambda: base_folder
default_paths.get_log_file_path = lambda: log_file

FACTORY = FakeSourceFactory([FakeScript(), FakeScript()])
camera_router.detect_available_cameras = lambda *args, **kwargs: FACTORY.device_infos()
manager_module.detect_available_cameras = lambda *args, **kwargs: FACTORY.device_infos()
_get_manager = manager_module.get_or_create_camera_group_manager


def _manager_with_fakes(app):
    manager = _get_manager(app)
    manager.source_factory = FACTORY
    return manager


camera_router.get_or_create_camera_group_manager = _manager_with_fakes
_collect = group_module.CameraGroup._collect_results


def _slow_collect(group):
    """A slow disk: the wait for the cameras takes the slow seconds, but it ends early when a camera process ends, as
    the wait of the product gives up on a camera that ended (`GIVE_UP_AFTER_EXIT_S`)."""
    deadline = time.monotonic() + float(slow_s)
    workers = list(group.cameras.camera_workers.values())
    while time.monotonic() < deadline and not any(worker.worker.exitcode is not None for worker in workers):
        time.sleep(0.05)
    return _collect(group)


group_module.CameraGroup._collect_results = _slow_collect
_end_take = group_module.CameraGroup._end_take


def _write_time(event, **values):
    with open(times_file, "a", encoding="utf-8") as out:
        print(json.dumps({"event": event, "time": time.time(), **values}), file=out, flush=True)


_start_group = group_module.CameraGroup.start


async def _start_and_name_the_rings(group):
    result = await _start_group(group)
    _write_time("rings", names=[name for info in group.ring_infos.values()
                                for name in (info.jpeg_ring_name, info.bgr_ring_name) if name])
    return result


group_module.CameraGroup.start = _start_and_name_the_rings
_handle_exit = uvicorn.Server.handle_exit


def _noted_handle_exit(server, sig, frame):
    _write_time("signal", number=int(sig))  # the test sends a second Ctrl-C only after the server took the first
    return _handle_exit(server, sig, frame)


uvicorn.Server.handle_exit = _noted_handle_exit


async def _timed_end_take(group):
    _write_time("start")  # the test sends its signal only after this line
    try:
        return await _end_take(group)
    finally:
        _write_time("end")


group_module.CameraGroup._end_take = _timed_end_take

if __name__ == "__main__":
    skellycam_main.entry_point()
