"""The real server of `skellycam/__main__.py` with two fake cameras, for `test_take_end_cancel.py`.

argv: port, base folder, log file, slow seconds, times file. No telemetry, no bytecode pass, the base folder (also of
the restore files) and the log file in a temporary folder. Detection gives the fake cameras, and the camera processes
open fake sources. The wait of a take stop for the cameras (`_collect_results`) first sleeps the slow seconds. The
times file gets the wall-clock start and end of each take end (`_end_take`), one JSON line each.
"""

import json
import sys
import time

import skellycam.__main__ as skellycam_main
import skellycam.api.http.cameras.camera_router as camera_router
import skellycam.api.server_constants as server_constants
import skellycam.app as app_module
import skellycam.core.camera_group.camera_group as group_module
import skellycam.core.camera_group.camera_group_manager as manager_module
import skellycam.system.default_paths as default_paths
from skellycam.tests.capture.fake_source import FakeScript, FakeSourceFactory

port, base_folder, log_file, slow_s, times_file = sys.argv[1:6]
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
    time.sleep(float(slow_s))
    return _collect(group)


group_module.CameraGroup._collect_results = _slow_collect
_end_take = group_module.CameraGroup._end_take


async def _timed_end_take(group):
    started = time.time()
    try:
        return await _end_take(group)
    finally:
        with open(times_file, "a", encoding="utf-8") as out:
            print(json.dumps({"start": started, "end": time.time()}), file=out)


group_module.CameraGroup._end_take = _timed_end_take

if __name__ == "__main__":
    skellycam_main.entry_point()
