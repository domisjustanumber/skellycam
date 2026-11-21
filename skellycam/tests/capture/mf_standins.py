"""Stand-in interfaces for `MediaFoundationSource` (T-UNX-76, T-UNX-78). No device and no camera frame.

Run in a fresh process: `python -m skellycam.tests.capture.mf_standins <case>`. comtypes joins the MTA at
import, and the main thread of a test process can already be in a single-threaded apartment (see
`test_media_foundation_com.py`). The last line of the output is a JSON object with the result.

The stand-ins replace the functions of `com` that the source calls, and `_set_mode`. The reader issues one
sample each 33 ms on its own thread, as the work queue of Media Foundation does. `IAMCameraControl` and
`IAMVideoProcAmp` keep a value and flags for each property and record each `Set`.

Cases: `diagnostics`; `restore` (the restore at the close, on by default); `restore-off`
(`SKELLYCAM_RESTORE_CONTROLS=0`); `restore-fails` (the restore `Set` of gain fails); `after-error` (a removal
HRESULT in `OnReadSample` before the close); `after-hang` (the `Set` of gain does not return); `restore-hangs`
(the restore `Set` of gain does not return); `loop-failed` (the close of a camera whose loop failed).
"""

import ctypes
import json
import sys
import threading
import time

PAYLOAD = b"\xff\xd8\xff\xfe\x00\x06fake\xff\xd9"  # a stand-in payload, not an image
E_FAIL = 0x80004005


class Calls(list):
    def add(self, *item):
        self.append(list(item))


class Control:
    """IAMCameraControl or IAMVideoProcAmp: {property: [value, flags]}."""

    def __init__(self, calls, kind, values, fail_sets=(), hang_sets=(), ranges=None):
        self.calls, self.kind, self.values, self.fail_sets, self.sets = calls, kind, values, fail_sets, 0
        self.hang_sets, self.ranges = hang_sets, ranges or {}

    def GetRange(self, prop, low, high, step, default, caps):  # noqa: N802
        if prop not in self.ranges:
            return E_FAIL
        for ref, value in zip((low, high, step, default, caps), self.ranges[prop]):
            ref._obj.value = value
        return 0

    def Get(self, prop, value, flags):  # noqa: N802 - COM name
        if prop not in self.values:
            return E_FAIL
        value._obj.value, flags._obj.value = self.values[prop]
        return 0

    def Set(self, prop, value, flags):  # noqa: N802
        self.sets += 1
        self.calls.add("set", self.kind, prop, value, flags)
        if (prop, self.sets) in self.fail_sets:
            return E_FAIL
        if (prop, self.sets) in self.hang_sets:
            threading.Event().wait()  # a driver call that does not return
        self.values[prop] = [value, flags]
        return 0


class Buffer:
    def __init__(self):
        self.data = ctypes.create_string_buffer(PAYLOAD, len(PAYLOAD))

    def Lock(self, data, max_length, length):  # noqa: N802
        data._obj.value, max_length._obj.value, length._obj.value = ctypes.addressof(self.data), len(PAYLOAD), len(PAYLOAD)
        return 0

    def Unlock(self):  # noqa: N802
        return 0


class Sample:
    def __init__(self, arrival_ns):
        self.time = (arrival_ns - 4_000_000) // 100

    def ConvertToContiguousBuffer(self, raw):  # noqa: N802
        return 0

    def GetSampleTime(self, value):  # noqa: N802
        value._obj.value = self.time
        return 0


class Reader:
    def __init__(self, calls, callback):
        self.calls, self.callback, self.stopped, self.fail = calls, callback, False, False

    def ReadSample(self, *args):  # noqa: N802
        def deliver():
            time.sleep(0.033)
            if self.fail:
                self.callback.OnReadSample(None, 0xC00D3EA2, 0, 0, 0, None)  # the device went away
            elif not self.stopped:
                self.callback.OnReadSample(None, 0, 0, 0, 0, Sample(time.perf_counter_ns()))
        threading.Thread(target=deliver, daemon=True).start()
        return 0

    def Flush(self, streams):  # noqa: N802
        self.stopped = True
        self.calls.add("flush")
        self.callback.OnFlush(None, 0)
        return 0


class Shuts:
    def __init__(self, calls, name):
        self.calls, self.name = calls, name

    def Shutdown(self):  # noqa: N802
        self.calls.add(self.name)

    ShutdownObject = Shutdown


def install(case):
    from skellycam.core.camera.capture.media_foundation import com, detect
    from skellycam.core.camera.capture.media_foundation import source as mf
    from skellycam.core.camera.capture.modes import NativeMode
    from skellycam.tests.capture.fake_source import fake_link

    calls = Calls()
    link = fake_link(0)
    # exposure (IAMCameraControl 4) in auto at -6, focus (6) absent, gain (IAMVideoProcAmp 9) manual at 10
    camera = Control(calls, "camera", {4: [-6, 1]}, ranges={4: (-13, -1, 1, -6, 3)})
    hang = {"after-hang": ((9, 1),), "restore-hangs": ((9, 2),)}.get(case, ())
    procamp = Control(calls, "procamp", {9: [10, 2]}, fail_sets=((9, 2),) if case == "restore-fails" else (),
                      hang_sets=hang)
    reader = {}

    def create_reader(media_source, callback, stage):
        reader["reader"] = Reader(calls, callback)
        return reader["reader"]

    names = dict(enumerate_devices=lambda stage: [("Fake camera 0", link, Shuts(calls, "shutdown-object"))],
                 activate_source=lambda activate, stage: Shuts(calls, "shutdown"),
                 query=lambda media_source, kind: {com.IAMCameraControl: camera, com.IAMVideoProcAmp: procamp}.get(kind),
                 create_reader=create_reader, ref=lambda pointer, kind: pointer, release=lambda pointer: None,
                 own=lambda raw, kind: Buffer(), borrow=lambda raw, kind: raw, get_uint32=lambda attributes, key: 0)
    for name, value in names.items():
        setattr(com, name, value)
    mf._set_mode = lambda reader_, request: NativeMode(640, 480, 30, 1, "MJPG")
    return mf, detect.camera_id_of(link), calls, reader


def run(case):
    import os

    from skellycam.core.camera.capture.source import CaptureFailure, CaptureRequest, ControlSetting

    if case == "restore-off":
        os.environ["SKELLYCAM_RESTORE_CONTROLS"] = "0"
    mf, camera_id, calls, reader = install(case)
    if case.startswith("auto-open"):
        return auto_open(mf, camera_id, calls, int(case.split(":")[1]))
    source = mf.MediaFoundationSource()
    source.open(CaptureRequest(camera_id=camera_id, width=640, height=480, framerate=30.0))
    frames = [source.read_frame(1.0) for _ in range(10)]
    source.set_controls({"exposure": ControlSetting(auto=False, value=-7)})
    result = {"exposure_range": source.exposure_range()}  # camera-requests.md 1.3 item 1: GetRange at the first read
    try:
        source.set_controls({"gain": ControlSetting(auto=False, value=20)})
    except CaptureFailure as failure:
        result["set_failure"] = [failure.stage, failure.code]
    if case == "after-error":
        reader["reader"].fail = True
        deadline = time.monotonic() + 2.0
        while source._error is None and time.monotonic() < deadline:
            time.sleep(0.01)
    calls.add("close")
    t0 = time.monotonic()
    try:
        source.close(restore=case != "loop-failed")
    except CaptureFailure as failure:
        result["close_failure"] = [failure.stage, failure.code, failure.hung]
    result["close_s"] = time.monotonic() - t0
    return dict(frames=sum(frame is not None for frame in frames), diagnostics=source.diagnostics(), calls=calls,
                **result)


def auto_open(mf, camera_id, calls, held):
    """The steps 5 and 6 of an open of the shared loop (`CameraLoop._set_start_controls`) in AUTO, on the real Media
    Foundation source over the stand-ins: the held value is set inside the range of GetRange (camera-requests.md
    1.3a). The loop is bare: no rings, no threads (the loop tests do the rest with the fake)."""
    from skellycam.core.camera.capture.camera_loop import CameraLoop
    from skellycam.core.camera.capture.source import CaptureRequest
    from skellycam.core.camera.config.camera_config import CameraConfig
    from skellycam.core.camera_group.camera_status import CameraStatus

    source = mf.MediaFoundationSource()
    source.open(CaptureRequest(camera_id=camera_id, width=640, height=480, framerate=30.0))
    loop = CameraLoop.__new__(CameraLoop)
    loop.source, loop.status, loop.camera_id = source, CameraStatus(), camera_id
    loop.config = CameraConfig(camera_id=camera_id, exposure_mode="AUTO", exposure=held)
    error = None
    try:
        CameraLoop._set_start_controls(loop, 0)
    except Exception as failure:  # the result names it; the test fails on it
        error = f"{type(failure).__name__}: {failure}"
    source.close()
    return dict(error=error, exposure=loop.config.exposure, exposure_range=source.exposure_range(),
                sets=[call[1:] for call in calls if call[0] == "set"])


if __name__ == "__main__":
    print(json.dumps(run(sys.argv[1])))
