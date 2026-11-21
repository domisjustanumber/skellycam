"""Helpers of the hardware tests of phase 3 (specs/windows-capture.md, sections 16.1 to 16.4).

The hardware tests run only with `SKELLYCAM_HARDWARE=1` (conftest). They use the real
`CameraGroupManager` with the source of section 14.2 (`source_factory=None`), chosen with
`SKELLYCAM_WINDOWS_CAPTURE`. One camera process opens each camera, except where a test must spy on
the frame path in the process; it then uses a THREAD worker and says so.

Kiyo Pro rule (16.1, D23): on a fault of the Kiyo Pro, the test records the diagnostics, marks the
camera dead and does not use it again in that run.

Results: each test appends JSON lines to `SKELLYCAM_HARDWARE_RESULTS` (default: a file in the temp
folder of the OS). The file is not in the repository.
"""

import contextlib
import json
import os
import re
import tempfile
import time
from pathlib import Path

import pytest

from skellycam.tests.capture.capture_session import CaptureApp, product, quiet_logging

LABELS = ("C922", "C930e", "Kiyo Pro", "generic")
GOOD = ("C922", "C930e", "Kiyo Pro")
DEAD = set()  # labels of cameras that this run must not use again (Kiyo Pro rule)
RESULTS = Path(os.environ.get("SKELLYCAM_HARDWARE_RESULTS",
                              Path(tempfile.gettempdir()) / "skellycam_capture_hardware.jsonl"))
SLOW_REASON = re.compile(r"^declared (\d+\.\d\d) fps, measured (\d+\.\d\d) fps\. Camera is slow\. Try adding more light$")


def record_result(test_id, **data):
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS.open("a", encoding="utf-8") as file:
        file.write(json.dumps(dict(test=test_id, utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **data),
                              default=str) + "\n")
    print(f"{test_id}: result written to {RESULTS}")


# Media Foundation names the Kiyo Pro "USB Video Device" (first hardware run, 2026-11-20): match by USB IDs first.
USB_IDS = {(0x046D, 0x085C): "C922", (0x046D, 0x0843): "C930e", (0x1532, 0x0E05): "Kiyo Pro"}


def label_of(camera):
    """The test label of a detected camera; None for a camera that is not a test camera (a virtual or
    software camera, for example NDI, which has no USB vendor ID)."""
    found = USB_IDS.get((camera.get("vendor_id"), camera.get("product_id")))
    if found:
        return found
    for label in GOOD:
        if label.lower() in camera["name"].lower():
            return label
    return "generic" if camera.get("vendor_id") is not None and not camera.get("virtual") else None


class HardwareApp(CaptureApp):
    """`CaptureApp` with the real source of section 14.2 and the real detection."""

    def __init__(self, monkeypatch, *, workers="process", source="media_foundation"):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        import skellycam.api.http.cameras.camera_router as camera_router
        from skellycam.core.camera_group.camera_group_manager import CameraGroupManager
        from skellycam.core.ipc.process_management.managed_worker import WorkerMode
        from skellycam.core.ipc.process_management.worker_registry import WorkerRegistry

        import multiprocessing

        product("skellycam.core.camera.capture.camera_loop")
        monkeypatch.setenv("SKELLYCAM_WINDOWS_CAPTURE", source)
        quiet_logging(monkeypatch)
        self.factory, self.clock, self.tracker = None, None, None
        self.kill = multiprocessing.Value("b", False)
        mode = WorkerMode.THREAD if workers == "thread" else WorkerMode.PROCESS
        self.registry = WorkerRegistry(global_kill_flag=self.kill, worker_mode=mode)
        self.manager = CameraGroupManager(global_kill_flag=self.kill, worker_registry=self.registry, source_factory=None)
        monkeypatch.setattr(camera_router, "get_or_create_camera_group_manager", lambda app: self.manager)
        app = FastAPI()
        app.include_router(camera_router.camera_router, prefix="/skellycam")
        self.client = TestClient(app, raise_server_exceptions=False)
        self.client.__enter__()
        self.devices = {}

    def detect(self):
        cameras = super().detect()["cameras"]
        self.devices = {label_of(c): c for c in cameras if label_of(c)}
        return cameras

    def camera_id(self, label):
        if label in DEAD:
            pytest.skip(f"the {label} is marked dead in this run (Kiyo Pro rule)")
        if label not in self.devices:
            pytest.skip(f"the {label} is not connected")
        return self.devices[label]["camera_id"]

    def config(self, camera_id, width=1280, height=720, framerate=30.0, exposure_mode="MANUAL", exposure=-7, **changes):
        from skellycam.core.camera.config.camera_config import CameraConfig
        from skellycam.core.camera.config.image_resolution import ImageResolution

        device = next(d for d in self.devices.values() if d["camera_id"] == camera_id)
        return CameraConfig(camera_id=camera_id, camera_index=device["index"], camera_name=device["name"],
                            resolution=ImageResolution(width=width, height=height), framerate=framerate,
                            exposure_mode=exposure_mode, exposure=exposure, **changes)


@contextlib.contextmanager
def hardware_app(monkeypatch, **args):
    app = HardwareApp(monkeypatch, **args)
    try:
        app.detect()
        yield app
    finally:
        app.close()


@contextlib.contextmanager
def kiyo_pro_rule(app, label, test_id):
    """Record the diagnostics of a Kiyo Pro fault and mark the camera dead for this run."""
    try:
        yield
    except BaseException as error:
        if label == "Kiyo Pro":
            _mark_dead(app, label, test_id, repr(error))
        raise
    if label == "Kiyo Pro":
        with contextlib.suppress(Exception):
            status = app.status(app.devices[label]["camera_id"])
            if status.get("state") in ("failed", "dead") and test_id not in ("T-CAP-54", "T-CAP-55", "T-CAP-57"):
                _mark_dead(app, label, test_id, json.dumps(status, default=str))


def _mark_dead(app, label, test_id, diagnostics):
    status = None
    with contextlib.suppress(Exception):
        status = app.status(app.devices[label]["camera_id"])
    record_result(test_id, camera=label, kiyo_pro_fault=diagnostics, status=status)
    DEAD.add(label)


def mode_list_follows_7_3(modes):
    """The structural rules of 7.3 that a mode list shows without its native types."""
    sizes = [(m["width"], m["height"]) for m in modes]
    assert sizes == sorted(sizes, key=lambda s: (-s[0] * s[1], -s[0])) and len(set(sizes)) == len(sizes)
    for mode in modes:
        rates = mode["framerates"]
        assert rates and rates == sorted(set(rates)), mode
        assert all(round(r, 2) == r and r >= 29.97 for r in rates), mode
