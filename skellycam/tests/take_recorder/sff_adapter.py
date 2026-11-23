"""The skellyfileformat test adapter of step 5a (specs/recorder.md, section 12.3, agent 28).

`SKELLYFILEFORMAT_ADAPTER=skellycam.tests.take_recorder.sff_adapter` names this module for the
conformance tests of skellyfileformat (`spec/conformance.md`, "The test adapter";
`tests/conformance/INTERFACE_NOTES_capture.md`). It exposes only `TakeWriter`, on top of
`start_take`, `CameraTakeWriter` and `Take.finish`, in one process. It has no `write_audio` (5b), no
`repair_take` (5c), no reader (phase 6) and no `release_check` (5b).

- The `camera_id` of a camera dict is `device.os_index` as 4 lowercase hexadecimal characters. A
  given `camera_key` is not used: 5a makes the key from `camera_id` [C3].
- The take start is the value that the host clock of `start_take` returned (the `clock` seam of 4.2).
- `trace(event, path)` comes from the file-action spy of `fake_disk.py` on the take folder: `lock`,
  `unlock` (also the close of the lock file while it is locked), `read`, `replace`, `write`, `flush`
  and `fsync`, with paths relative to the take folder.
- `write_frame` passes each JPEG through the capture check of the program (`check_jpeg`), which
  inserts the standard DHT [F-3, ring 5.2]. `data` None gives a frame with `CAPTURE_ERROR`: a
  `missing` row with its times (7.2). `camera_stopped(index, reason)` marks a dead camera (7.3).
- `close()` ends each camera writer with the frame count of the take (the largest number of frames
  of a camera), then calls `finish` with the dead cameras.
- The reader functions of the format (also `camera_lost_at` and `short_file_counts`) are not here:
  the reader of skellycam is the player (TypeScript), and T-REC-37 runs no test that uses `reader`.
- Audio, a conversion run, a camera with `capture_format` `YUYV` and `add_warning` raise
  `NotImplementedError`. At exit, the adapter ends the writers of each take that a failed test did
  not close, so that no writer thread keeps the test process alive.
"""

import importlib
import math
import threading
import time
from pathlib import Path

from skellycam.tests.take_recorder.fake_disk import FakeDisk

FORWARDED = {"lock", "unlock", "read", "replace", "write", "flush", "fsync"}
_OPEN = set()  # the TakeWriters that are not closed: the exit hook ends their writer threads


def _end_open_writers():
    for take_writer in list(_OPEN):
        try:
            take_writer.close()
        except Exception:  # noqa: BLE001 - a test that failed left the take; end its threads only
            pass


# The interpreter joins each non-daemon thread before the `atexit` hooks run. This hook of the
# threading module runs before that join (as in concurrent.futures).
threading._register_atexit(_end_open_writers)


class _TraceDisk(FakeDisk):
    def __init__(self, root, trace):
        super().__init__(root)
        self._trace, self._locked = trace, False

    def _event(self, event, path, extra=None):
        super()._event(event, path, extra)
        rel = self._rel(path)
        if rel == ".processing.lock":
            if event == "lock":
                self._locked = True
            elif event in ("unlock", "close") and self._locked:
                self._locked = False
                self._trace("unlock", rel)
                return
            if event != "lock":
                return
        if event in FORWARDED:
            self._trace(event, rel)


def _module():
    return importlib.import_module("skellycam.core.take_recorder")


def _controls(controls):
    """SFF-802 names to the skellycam names of TakeCamera (ADR-QEQ8): exposure in log2 seconds."""
    out = {}
    exposure = (controls or {}).get("exposure_us")
    if exposure is not None:
        value = exposure.get("value")
        out["exposure"] = (None if value is None else math.log2(value / 1e6), exposure.get("auto"))
    for name in ("gain", "focus"):
        if name in (controls or {}):
            out[name] = (controls[name].get("value"), controls[name].get("auto"))
    return out


class TakeWriter:
    def __init__(self, folder, rec, cameras, audio, *, writer, trace=None, mode="capture"):
        if audio is not None:
            raise NotImplementedError("audio recording returns in step 5b")
        if mode != "capture":
            raise NotImplementedError("the conversion writer of skellycam is phase 6")
        for camera in cameras:
            if (camera.get("requested") or {}).get("capture_format") == "YUYV":
                raise NotImplementedError("raw YUYV input: the recorder takes JPEG only (3b encodes in the loop)")
        module = _module()
        self._module, self.folder = module, Path(folder)
        self._patch = None
        if trace is not None:
            import pytest

            self._patch = pytest.MonkeyPatch()
            _TraceDisk(self.folder, trace).install(self._patch)
        takes = []
        for position, camera in enumerate(cameras):
            device, requested = camera.get("device") or {}, camera.get("requested") or {}
            num, den = (int(x) for x in str(camera["nominal_rate"]).split("/"))
            takes.append(module.TakeCamera(
                camera_id=f"{int(device.get('os_index') or position):04x}", nominal_rate=(num, den),
                width=requested.get("width"), height=requested.get("height"),
                rotation_cw_deg=camera.get("display_rotation", 0), capture_format=requested.get("capture_format"),
                layout=None, os_name=device.get("os_name"), vendor_id=device.get("vendor_id"),
                product_id=device.get("product_id"), backend=device.get("backend"), os_index=device.get("os_index"),
                requested=requested, controls=_controls(camera.get("controls")),
            ))
        self._formats = [t.capture_format for t in takes]
        started = {}

        def host():
            started["host"] = time.perf_counter_ns()
            return started["host"]

        try:
            self._take = module.start_take(self.folder, rec, takes, writer=writer, clock=(host, time.time_ns))
        except BaseException:
            self._undo()
            raise
        self.take_start_host_ns = started["host"]
        self._ids = [t.camera_id for t in takes]
        self._writers = [module.CameraTakeWriter.start(self._take.camera_spec(c)) for c in self._ids]
        self._rows = [0] * len(takes)
        self._stopped = {}  # group_position: the reason of camera_stopped
        _OPEN.add(self)

    def write_frame(self, index, data, host_ns, *, source_frame_number, sample_ns=None):
        if self._formats[index] != "MJPG":
            raise NotImplementedError("raw YUYV input: the recorder takes JPEG only (3b encodes in the loop)")
        from skellycam.core.ipc.frame_ring import NO_SAMPLE_NS

        from skellycam.core.ipc.frame_ring.capture_check import check_jpeg
        from skellycam.core.ipc.frame_ring.layout import FrameFlag

        if index in self._stopped:
            raise RuntimeError(f"camera {index} stopped; the test writes no frame of it after camera_stopped")
        # The capture check of the program runs before the recorder [ring 5.2]: it inserts the standard
        # DHT (F-3). `data` None is a frame with a capture error: a `missing` row with its times (7.2).
        if data is None:
            data, flags = b"", FrameFlag.CAPTURE_ERROR
        else:
            data, flags = check_jpeg(data, delivered_len=len(data), driver_error=False)
        k = self._rows[index]
        frame = self._module.RecorderFrame(
            payload=data, frame_number=k, arrival_ns=host_ns, sample_ns=NO_SAMPLE_NS if sample_ns is None else sample_ns,
            source_frame_number=k if source_frame_number is None else source_frame_number, flags=int(flags),
            delivered_len=len(data), rotation_cw_deg=0)
        self._writers[index].give(frame)
        self._rows[index] += 1

    def camera_stopped(self, index, reason):
        """The camera died during the take (7.3): `end` pads its rows, and `finish` adds `camera_dead`."""
        self._stopped[index] = reason

    def write_audio(self, *args, **kwargs):
        raise NotImplementedError("audio recording returns in step 5b")

    def add_warning(self, code, *, camera_key, detail):
        raise NotImplementedError("Take.finish adds the warnings of 5a; it has no call for other warnings")

    def close(self):
        _OPEN.discard(self)
        try:
            frame_count = max(self._rows, default=0)
            results = [w.end(frame_count) for w in self._writers]
            dead = {self._ids[index]: reason for index, reason in self._stopped.items()}
            self._take.finish(results, frame_count=frame_count, dead_cameras=dead)
        finally:
            self._undo()

    def _undo(self):
        if self._patch is not None:
            self._patch.undo()
            self._patch = None
