"""`MediaFoundationSource` (specs/windows-capture.md, section 6; ported from the prototype `pymf/mf.py`).

A push source: an async `IMFSourceReader` gives each sample to `_ReaderCallback` on a work-queue
thread of Media Foundation, and the callback puts the frame in the waiting place (4.3).

The process set-up of 6.1 (`com.startup()`) is the job of the camera process, before `open`.
"""

import logging
import threading
import time
from ctypes import byref, c_long, c_ulong, c_void_p, sizeof, string_at

from comtypes import COMObject

from skellycam.core.camera.capture.media_foundation import bounded, com, detect
from skellycam.core.camera.capture.media_foundation.errors import E_FAIL, check, hresult_reason
from skellycam.core.camera.capture.modes import choose_mode
from skellycam.core.camera.capture.source import (
    BOUNDED_CALL_LIMIT_S, FIRST_FRAME_TIMEOUT_S, CapturedFrame, CaptureFailure, CaptureRequest, CaptureWaitingPlace,
    ControlSetting, ControlState, ControlValue, OpenedMode)
from skellycam.core.ipc.frame_ring import NO_SAMPLE_NS

logger = logging.getLogger(__name__)
FIRST = com.MF_SOURCE_READER_FIRST_VIDEO_STREAM
FLAGS_AUTO, FLAGS_MANUAL = 1, 2  # CameraControl_Flags_Auto, CameraControl_Flags_Manual
SAMPLE_TIME_LIMIT_NS = 200_000_000  # 4.2: a sample time more than 200 ms before its arrival is not used

# The controls of step 3a (11.4): name: (index into the control interfaces (0 IAMCameraControl,
# 1 IAMVideoProcAmp), property ID). White balance and power line frequency come in step 3c.
CONTROLS = {"exposure": (0, 4), "focus": (0, 6), "gain": (1, 9)}
ABSENT = ControlValue(present=False, auto=False, value=None)


class _ReaderCallback(COMObject):
    """IMFSourceReaderCallback. Media Foundation calls it on its work-queue threads (MTA)."""
    _com_interfaces_ = [com.IMFSourceReaderCallback]

    def __init__(self, source):
        super().__init__()
        self._source = source

    def OnReadSample(self, this, hr, stream_index, flags, timestamp, sample):  # noqa: N802 - COM name
        arrival_ns = time.perf_counter_ns()  # 6.5 step 1: first
        if self._source._callback is not self:
            return 0  # a late call of the reader of an earlier open
        try:
            self._source._on_sample(arrival_ns, hr, flags, sample)
        except CaptureFailure as failure:
            self._source._fail(failure)
        except BaseException as error:  # noqa: BLE001 - never raise into Media Foundation (4.3)
            self._source._fail(CaptureFailure("streaming", f"{type(error).__name__}: {error}"))
        return 0

    def OnFlush(self, this, stream_index):  # noqa: N802
        if self._source._callback is self:
            self._source._flushed.set()
        return 0

    def OnEvent(self, this, stream_index, event):  # noqa: N802
        return 0


class MediaFoundationSource:
    """The capture interface of 4.1 on Media Foundation. Opens the device whose `camera_id` equals
    the `camera_id` of the request (6.2, agent 12)."""

    def __init__(self):
        self._lock = threading.Lock()  # guards _closing, _issuing and the reader of the callback
        self._place = CaptureWaitingPlace()
        self._first = threading.Event()
        self._flushed = threading.Event()
        self._activate = self._media_source = self._reader = self._callback = None
        self._interfaces = (None, None, None)  # IAMCameraControl, IAMVideoProcAmp, IKsControl
        self._closing = False
        self._issuing = 0
        self._hung = False
        self._error = None
        self._count = 0
        self._sample_time_ok = True
        self._format = "MJPG"

    @property
    def replaced_count(self) -> int:
        return self._place.replaced

    # ----- the capture interface (4.1) -----

    def open(self, request: CaptureRequest) -> OpenedMode:
        try:
            return self._open(request)
        except BaseException as error:
            if not getattr(error, "hung", False):
                try:
                    self.close()  # 6.4 step 2: the bounded close steps; the process does not end hard
                except CaptureFailure as close_failure:
                    raise CaptureFailure(getattr(error, "stage", "open"), getattr(error, "reason", str(error)),
                                         hung=True) from close_failure
            raise

    def read_frame(self, timeout_s: float) -> CapturedFrame | None:
        return self._place.take(timeout_s)

    def set_controls(self, changes: dict[str, ControlSetting]) -> ControlState:
        """Set each change, then read every control back (D20), in one bounded call (6.8)."""
        if self._hung:  # 6.8: after a hang, the source does not touch the interfaces again
            raise CaptureFailure("set controls", "an earlier call did not return", hung=True)
        with self._lock:  # the close swaps the interfaces out under this lock, then releases them
            if self._closing:
                return {name: ABSENT for name in CONTROLS}
            interfaces = [com.ref(pointer, kind) for pointer, kind in
                          zip(self._interfaces, (com.IAMCameraControl, com.IAMVideoProcAmp, com.IKsControl))]

        def run():
            try:
                for name, setting in changes.items():
                    _set_control(interfaces, name, setting)
                return {name: _read_control(interfaces, name)[0] for name in CONTROLS}
            finally:
                for pointer in interfaces:
                    com.release(pointer)
        return self._call("set controls", "a control call", run)

    def close(self) -> None:
        """Close in the order of 6.9. Each step is bounded; a hung step stops the close there."""
        if self._hung:
            return  # a hung call can still use these objects; the camera process ends hard (6.6)
        with self._lock:
            self._closing = True
            interfaces, self._interfaces = self._interfaces, (None, None, None)
        deadline = time.perf_counter() + BOUNDED_CALL_LIMIT_S
        while self._issuing:  # 6.9 step 1
            if time.perf_counter() > deadline:
                self._hung = True
                raise CaptureFailure("close", f"a ReadSample issue did not return in {BOUNDED_CALL_LIMIT_S:g} s",
                                     hung=True)
            time.sleep(0.001)
        if self._reader is not None:
            self._flushed.clear()
            reader = com.ref(self._reader, com.IMFSourceReader)
            hresult = self._call("close", "Flush", lambda: _flush(reader))
            if hresult & 0x80000000:
                logger.warning(f"close: Flush failed: {hresult_reason(hresult)}")
            elif not self._flushed.wait(BOUNDED_CALL_LIMIT_S):
                logger.warning(f"close: no OnFlush in {BOUNDED_CALL_LIMIT_S:g} s")  # as the prototype: the close goes on
            reader, self._reader = self._reader, None
            self._call("close", "the reader release", lambda: com.release(reader))
        self._call("close", "the control interface release", lambda: [com.release(p) for p in interfaces])
        media_source, self._media_source = self._media_source, None
        if media_source is not None:
            self._call("close", "IMFMediaSource::Shutdown", lambda: _end(media_source, media_source.Shutdown))
        activate, self._activate = self._activate, None
        if activate is not None:
            self._call("close", "IMFActivate::ShutdownObject", lambda: _end(activate, activate.ShutdownObject))
        self._callback = None

    # ----- open (6.2 to 6.4) -----

    def _open(self, request):
        self._place = CaptureWaitingPlace()
        self._first.clear()
        self._closing, self._error, self._count, self._sample_time_ok = False, None, 0, True
        self._format = request.capture_fourcc

        def find():
            found = com.enumerate_devices("open")
            keep = [(link, activate) for _, link, activate in found if detect.camera_id_of(link) == request.camera_id]
            for _, _, activate in found:
                if len(keep) != 1 or activate is not keep[0][1]:
                    com.release(activate)
            if not keep:
                raise CaptureFailure("open", "camera not found")
            if len(keep) > 1:  # D13, agent 12
                raise CaptureFailure("open", f"{len(keep)} devices have the camera_id {request.camera_id}: "
                                             + ", ".join(link for link, _ in keep))
            return keep[0]
        link, self._activate = self._call("open", "the device list", find, on_late=lambda kept: com.release(kept[1]))

        activate = com.ref(self._activate, com.IMFActivate)

        def activate_source():
            try:
                return com.activate_source(activate, "open")
            finally:
                com.release(activate)
        self._media_source = self._call("open", "ActivateObject", activate_source,
                                        on_late=lambda late: _end(late, late.Shutdown))  # 6.2 step 3

        self._callback = _ReaderCallback(self)
        media_source = com.ref(self._media_source, com.IMFMediaSource)

        def create_reader():
            try:
                interfaces = tuple(com.query(media_source, kind)
                                   for kind in (com.IAMCameraControl, com.IAMVideoProcAmp, com.IKsControl))
                return interfaces, com.create_reader(media_source, self._callback, "open")
            finally:
                com.release(media_source)
        self._interfaces, self._reader = self._call("open", "the reader creation", create_reader)

        reader = com.ref(self._reader, com.IMFSourceReader)

        def set_mode():
            try:
                return _set_mode(reader, request)
            finally:
                com.release(reader)
        mode = self._call("set mode", "the mode set", set_mode)

        reader = com.ref(self._reader, com.IMFSourceReader)

        def start():
            try:
                check(reader.ReadSample(FIRST, 0, None, None, None, None), "start stream")
            finally:
                com.release(reader)
        self._call("start stream", "the first ReadSample", start)

        if not self._first.wait(FIRST_FRAME_TIMEOUT_S):  # a wait, not a hung call (6.4)
            raise CaptureFailure("first frame", f"no frame in {FIRST_FRAME_TIMEOUT_S:g} s")
        if self._count == 0:
            raise CaptureFailure("first frame", self._error.reason)
        return OpenedMode(width=mode.width, height=mode.height, fps_num=mode.fps_num, fps_den=mode.fps_den,
                          format=mode.format, device_path=link)

    def _call(self, stage, what, function, on_late=None):
        try:
            return bounded.call(stage, what, function, on_late)
        except CaptureFailure as failure:
            self._hung = self._hung or failure.hung
            raise

    # ----- the callback (6.5) -----

    def _on_sample(self, arrival_ns, hr, flags, sample):
        if hr & 0x80000000:
            return self._fail(CaptureFailure("streaming", hresult_reason(hr)))
        if flags & com.MF_SOURCE_READERF_ERROR:
            return self._fail(CaptureFailure("streaming", hresult_reason(E_FAIL)))
        if flags & com.MF_SOURCE_READERF_ENDOFSTREAM:
            return self._fail(CaptureFailure("streaming", "end of stream"))
        if sample:  # a null sample is a stream tick, not a frame
            self._place.put(self._frame(arrival_ns, com.borrow(sample, com.IMFSample)))
            self._first.set()
        self._read_next()

    def _frame(self, arrival_ns, sample):
        """Copy the sample into one `bytes` object (4.2). The callbacks of one stream never overlap."""
        try:
            raw = c_void_p()
            check(sample.ConvertToContiguousBuffer(byref(raw)), "streaming")
            buffer = com.own(raw, com.IMFMediaBuffer)
            try:
                payload = _copy(buffer)
            finally:
                com.release(buffer)
            sample_time = com.LONGLONG()
            has_time = not sample.GetSampleTime(byref(sample_time)) & 0x80000000
            discontinuity = com.get_uint32(sample, com.MFSampleExtension_Discontinuity) != 0
        finally:
            com.release(sample)
        sample_ns = 100 * sample_time.value  # agent 10
        if not has_time or not arrival_ns - SAMPLE_TIME_LIMIT_NS <= sample_ns <= arrival_ns:
            self._sample_time_ok = False  # the rule of 4.2: for the rest of the open
        number, self._count = self._count, self._count + 1
        return CapturedFrame(payload=payload, format=self._format, arrival_ns=arrival_ns,
                             sample_ns=sample_ns if self._sample_time_ok else NO_SAMPLE_NS,
                             delivered_len=len(payload), driver_error=False, source_frame_number=number,
                             discontinuity=discontinuity)

    def _read_next(self):
        with self._lock:
            if self._closing or self._reader is None:
                return
            reader = com.ref(self._reader, com.IMFSourceReader)  # the close can release the reader
            self._issuing += 1
        try:
            hresult = reader.ReadSample(FIRST, 0, None, None, None, None)
        finally:
            com.release(reader)
            with self._lock:
                self._issuing -= 1
        if hresult & 0x80000000:
            self._fail(CaptureFailure("streaming", hresult_reason(hresult)))

    def _fail(self, failure):
        """Keep the first error; the marker wakes the loop (4.3), and no new read is issued."""
        if self._error is None:
            self._error = failure
            self._place.put_error(failure)
        self._first.set()


def _set_mode(reader, request):
    """6.3: choose by 7.5, set the type, read it back."""
    native = com.native_types(reader)
    chosen = choose_mode(native, request)
    raw = c_void_p()
    check(reader.GetNativeMediaType(FIRST, native.index(chosen), byref(raw)), "set mode")
    media_type = com.own(raw, com.IMFMediaType)
    try:
        check(reader.SetStreamSelection(com.MF_SOURCE_READER_ALL_STREAMS, 0), "set mode")
        check(reader.SetStreamSelection(FIRST, 1), "set mode")
        check(reader.SetCurrentMediaType(FIRST, None, media_type), "set mode")
    finally:
        com.release(media_type)
    raw = c_void_p()
    check(reader.GetCurrentMediaType(FIRST, byref(raw)), "set mode")
    current = com.own(raw, com.IMFMediaType)
    try:
        got = com.mode_of(current)
    finally:
        com.release(current)
    if got != chosen:
        raise CaptureFailure("set mode", f"the camera set {got} instead of {chosen}")
    return chosen


def _copy(buffer):
    """Lock the buffer, copy its current length into one `bytes` object, unlock (6.5 step 3)."""
    data, max_length, length = c_void_p(), com.DWORD(), com.DWORD()
    check(buffer.Lock(byref(data), byref(max_length), byref(length)), "streaming")
    try:
        return string_at(data.value, length.value) if length.value else b""
    finally:
        buffer.Unlock()


def _flush(reader):
    try:
        return reader.Flush(com.MF_SOURCE_READER_ALL_STREAMS)
    finally:
        com.release(reader)


def _end(pointer, shutdown):
    """Shutdown or ShutdownObject, then release, on the worker of the bounded call."""
    try:
        shutdown()
    finally:
        com.release(pointer)


def _read_control(interfaces, name):
    """(ControlValue, the interface that answered): IAM `Get` first, else IKsControl (6.8)."""
    kind, prop = CONTROLS[name]
    iam, ks = interfaces[kind], interfaces[2]
    value, flags = c_long(), c_long()
    if iam is not None:
        if not iam.Get(prop, byref(value), byref(flags)) & 0x80000000:
            return ControlValue(present=True, auto=bool(flags.value & FLAGS_AUTO), value=value.value), iam
    if ks is not None:
        request = _ks_property(kind, prop, com.KSPROPERTY_TYPE_GET)
        if not ks.KsProperty(byref(request), sizeof(request), byref(request), sizeof(request),
                             byref(c_ulong())) & 0x80000000:
            return ControlValue(present=True, auto=bool(request.Flags & FLAGS_AUTO), value=request.Value), ks
    return ABSENT, None


def _set_control(interfaces, name, setting):
    """Set one control through the interface that read it. The read-back follows in `set_controls`."""
    if name not in CONTROLS:
        raise CaptureFailure("set controls", f"no {name} control")
    before, via = _read_control(interfaces, name)
    if not before.present:
        raise CaptureFailure("set controls", f"no {name} control")
    value = before.value if setting.value is None else setting.value
    flags = FLAGS_AUTO if setting.auto else FLAGS_MANUAL
    kind, prop = CONTROLS[name]
    if via is interfaces[2]:
        request = _ks_property(kind, prop, com.KSPROPERTY_TYPE_SET)
        request.Value, request.Flags = value, flags
        hresult = via.KsProperty(byref(request), sizeof(request), byref(request), sizeof(request), byref(c_ulong()))
    else:
        hresult = via.Set(prop, value, flags)
    check(hresult, "set controls")


def _ks_property(kind, prop, operation):
    request = com.KSPROPERTY_CAMERACONTROL_S()
    request.Property.s.Set = com.PROPSETID_VIDCAP_CAMERACONTROL if kind == 0 else com.PROPSETID_VIDCAP_VIDEOPROCAMP
    request.Property.s.Id, request.Property.s.Flags = prop, operation
    return request
