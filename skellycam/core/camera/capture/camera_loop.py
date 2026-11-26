"""The shared camera loop (specs/windows-capture.md, sections 5, 8 to 12).

One loop in each camera process serves each source (D6). The loop reads the time only through the
module name `perf_counter_ns`, so that a test can give it a virtual clock (ADR-HP7D item 12).
"""
import hashlib
import logging
import os
import pickle
import queue
import threading
import time
from collections import deque
from collections.abc import Callable
from multiprocessing import parent_process

import cv2
import numpy as np

from skellycam.core import capture_timings
from skellycam.core.camera.capture import rate_check
from skellycam.core.camera.capture.failure_codes import WEDGE_CODES
from skellycam.core.camera.capture.exposure_search import ExposureSearch, add_light_text, failed_text, search_values
from skellycam.core.camera.capture.modes import NO_FLOOR_MODE, at_floor, rates_equal
from skellycam.core.camera.capture.source import (
    BOUNDED_CALL_LIMIT_S,
    HASH_COUNT,
    CapturedFrame,
    CaptureFailure,
    CaptureRequest,
    ControlSetting,
    ControlState,
    empty_diagnostics,
)
from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.config.image_resolution import ImageResolution
from skellycam.core.camera_group.camera_orchestrator import FRAME_LOCK_WAIT_S
from skellycam.core.camera_group.camera_group_ipc import CameraGroupIPC
from skellycam.core.camera_group.camera_orchestrator import CameraOrchestrator
from skellycam.core.camera_group.camera_setup_failure import CameraSetupFailure
from skellycam.core.ipc.frame_ring import (
    ERROR_FLAGS,
    DecodeInput,
    DecodeStage,
    FrameFlag,
    FrameRingWriter,
    check_jpeg,
    decode_jpeg,
    rotation_to_cw_deg,
)
from skellycam.core.ipc.pubsub.pubsub_manager import TopicTypes
from skellycam.core.ipc.pubsub.pubsub_topics import (
    DeviceExtractedConfigMessage,
    DiagnosticsMessage,
    RecordingFinishedMessage,
)
from skellycam.core.take_recorder import (
    CameraTakeWriter,
    RecorderFrame,
    RecorderStalled,
    RecorderWriteError,
    parse_sof,
)
from skellycam.core.types.type_overloads import TopicSubscriptionQueue

logger = logging.getLogger(__name__)

perf_counter_ns = time.perf_counter_ns

STALL_NS = 2_000_000_000  # 9.5, D38
READY_LIMIT_NS = 15_000_000_000  # 9.3, D21
CONTROL_READ_INTERVAL_S = 1.0  # 11.4, U16
RECENT_FRAMES = 1024  # 10.2 [ADR-0R76]: the taken frames that a check gets: a set of 5 s (the bounded call) at 200 fps
JPEG_Q90 = [int(cv2.IMWRITE_JPEG_QUALITY), 90]  # ring 2.3, 8.8
DIAGNOSTICS_INTERVAL_NS = 1_000_000_000  # unix-capture.md 4.2 item 2: one dict each second
DIAGNOSTICS_LIMIT_BYTES = 32 * 1024  # the pickled message; a larger dict is not sent
DIAGNOSTICS_FLUSH_S = 1.0  # the longest wait of a camera process for its close dict to reach the pipe
SEARCH_WARNINGS = ("add_light", "exposure_search_failed")  # camera-requests.md 1.5: they clear at the next search
HELD_FIELDS = ("exposure_mode", "exposure", "exposure_found_at_fps")  # the held value of 1.3a
# [GEH0]: the reply of the last set of a search comes within the limit of a bounded call (6.6) and a margin
FINAL_SET_LIMIT_NS = round((BOUNDED_CALL_LIMIT_S + 1.0) * 1e9)


class _Stop(Exception):
    """The group closes this camera."""


class _Hung(Exception):
    """A bounded call of the control thread did not return (6.6)."""


def camera_loop(source_factory: Callable, config: CameraConfig, ipc: CameraGroupIPC, orchestrator: CameraOrchestrator,
                update_camera_settings_subscription: TopicSubscriptionQueue,
                shm_subscription: TopicSubscriptionQueue,
                recording_info_subscription: TopicSubscriptionQueue) -> None:
    """Run one camera until the group closes it, or until it fails or dies. Never raises for a camera failure.

    `source_factory(config)` gives a new source for each open (ADR-HP7D item 10).
    """
    CameraLoop(source_factory, config, ipc, orchestrator, update_camera_settings_subscription, shm_subscription,
               recording_info_subscription).run()


def start_take_writer(camera_id, spec, progress=None, alive=None, timing=None) -> CameraTakeWriter:
    """Start the camera writer of a take (recorder.md 10 item 5). A spec of another camera is refused (D41)."""
    if spec.camera_id != camera_id:
        raise ValueError(f"the take spec of camera {spec.camera_id} came to camera {camera_id}")
    return CameraTakeWriter.start(spec, progress=progress, alive=alive, timing=timing)


def needs_reopen(requested: CameraConfig, current: CameraConfig) -> bool:
    """A change of resolution or rate reopens the camera (D31). Each other change is live (11.2)."""
    return ((requested.resolution, requested.capture_fourcc, requested.bgr_ring)
            != (current.resolution, current.capture_fourcc, current.bgr_ring)
            or (requested.framerate > 0 and not rates_equal(requested.framerate, current.framerate)))


class CameraLoop:
    def __init__(self, source_factory, config, ipc, orchestrator, update_sub, shm_sub, recording_sub):
        self.source_factory, self.config, self.ipc, self.orchestrator = source_factory, config, ipc, orchestrator
        self.source = None
        self.camera_id = config.camera_id
        self.status = orchestrator.camera_statuses[config.camera_id]
        self.update_sub, self.shm_sub, self.recording_sub = update_sub, shm_sub, recording_sub
        self.gate_count = -1  # the frame number of the gate (5.3); it continues across a reopen
        self.ring_writer: FrameRingWriter | None = None
        self.bgr_ring_writer: FrameRingWriter | None = None
        self.decode_stage: DecodeStage | None = None
        self.old_ring_name: str | None = None
        self.ring_count = 0
        self.reference_rate = 0.0
        self.last_arrival = 0
        self.last_number = -1
        self.recent_frames: deque[tuple[int, int]] = deque(maxlen=RECENT_FRAMES)  # (sfn, arrival) of taken frames
        self.last_wait_end = 0  # the end of the last wait of the loop at the gate or in `give` (recorder.md 5.2)
        self.stage = "open"
        self.started = False
        self.take_writer: CameraTakeWriter | None = None
        self.take_failed = False  # after a stall or a write error the loop calls only `end` (recorder.md 4.3)
        self.last_good_payload: bytes | None = None  # its SOF gives the placeholder layout (recorder.md 6.4)
        self.check: dict | None = None  # the check after a live change (10.2)
        self.block: tuple[int, int] | None = None  # the block of a recording (10.3)
        self.slow = False
        self.replaced_base: int | None = None
        self.replaced_total = 0
        self.control: _ControlThread | None = None
        # The exposure search (camera-requests.md 1.3): the search, the config fields before it, the value of its
        # last set (None while it tries the values) and the results of its sets from the control thread.
        self.search: ExposureSearch | None = None
        self.search_before: dict | None = None
        self.search_final: int | None = None
        self.search_final_ns = 0  # when the last set of the search went to the control thread
        self.search_replies = queue.Queue()
        self.no_exposure = False  # the camera has no working exposure control (camera-requests.md 1.9) [K3]
        self.exposure_range: tuple | None = None  # (min, max, step) of the camera at this open (1.3 item 1) [GEH0]
        self.signals = queue.Queue()
        self.hung = threading.Event()
        self._failure_lock = threading.Lock()
        self.failed = False
        self.lost_heartbeat = False  # not a camera fault: the close restores the controls (unix-capture.md 4.7)
        self.end_state: str | None = None  # the state that the end sets after the close
        # The diagnostics of the loop (unix-capture.md 4.2 item 3, 4.6.2 D-10, D-11)
        self.next_diagnostics_ns = 0
        self.diagnostics_logged = False  # one log line for a dict over the limit or a failed dict
        self.failure_code = self.failure_stage = None
        self.encoded = self.decoded_closed = self.dht_inserted = 0
        self.hash_trigger: str | None = None
        self.hashes: list[tuple[int, str]] = []  # (source_frame_number, SHA-256) of the bytes of the ring and recorder
        self.dqt_hashes: list[str] = []
        self.dht_present: bool | None = None
        # The capture timings (capture-timings.md 5.1): one control for each process, the set of this thread, the
        # set of each other writer instance by role ("source", "decode", "writer"), and the one reader.
        self.loop_thread = threading.current_thread()
        self.timing = capture_timings.TimingControl(lambda: perf_counter_ns())  # the module name: a test clock
        self.timing.on = bool(self.status.log_capture_times.value)  # a group made after a change to on starts on
        self.loop_steps = capture_timings.StepSet(self.timing, capture_timings.LOOP_STEPS)
        self.timing_sets: dict = {}
        self.timing_reader = capture_timings.WindowReader()
        self.timing_seq = 0
        self.timing_last: dict | None = None  # the last summary: a publish of another thread sends it again
        self.timing_start_ns = self.timing.clock() if self.timing.on else 0
        self.wait_ns = self.gate_ns = 0  # the waits of the passes since the last frame (3.1)
        self.timings_logged = False  # one log line for a fault of the timings
        for subscription in getattr(self.ipc.pubsub.topics.get(TopicTypes.DIAGNOSTICS), "subscriptions", ()):
            # The main process stops reading at the group close: an exit must not wait to flush a full pipe of
            # diagnostics (multiprocessing joins the feeder thread of each queue at the exit). A lost dict is no loss.
            subscription.cancel_join_thread()

    # ----- the run -----

    def run(self) -> None:
        hung = lost = False
        try:
            self._start_up()
            while self.ipc.should_continue and not self.status.should_close.value:
                self._pass()
            # The loop left with no stop flag and the group running: the heartbeat was lost. Read here, not in the
            # `finally`: no second read of the clock (a heartbeat that came back would hide the reason), and a
            # re-select clears the stop flag after the end; another BaseException is no lost heartbeat.
            lost = not self.status.should_close.value and self.ipc.running
        except _Stop:
            lost = not self.status.should_close.value and self.ipc.running
        except _Hung:
            hung = True
        except CaptureFailure as failure:
            hung = failure.hung
            self._fail(failure, at_end=not hung)
        except Exception as error:
            logger.exception(f"Camera {self.camera_id} loop error: {error}")
            self._fail(CaptureFailure(self.stage, f"{type(error).__name__}: {error}"), at_end=True)
        finally:
            if lost and not self.failed:
                self._lost_heartbeat()
            self._end(hung)

    def _lost_heartbeat(self) -> None:
        """Decision L: no heartbeat of the server for 10 s. This camera ends; its take files are finished and its
        camera released by `_end`. A live main process gets the reason in the status and ends the take with it."""
        text = "lost the server's heartbeat"
        self.lost_heartbeat = True
        if self.take_writer is not None:
            self.ipc.pubsub.topics[TopicTypes.RECORDING_FINISHED].publish(
                RecordingFinishedMessage(camera_id=self.camera_id, error=f"camera {self.camera_id} {text}"))
        self._fail(CaptureFailure(self.stage, text), at_end=not self.started)  # not started: `failed` after its close

    def _pass(self) -> None:
        self.status.alive_count.value += 1  # the main-process stall watch (unix-capture.md 4.10)
        if self.hung.is_set():
            raise _Hung()
        now = perf_counter_ns()
        if now >= self.next_diagnostics_ns:
            self.next_diagnostics_ns = now + DIAGNOSTICS_INTERVAL_NS
            self._publish_diagnostics()
        self._check_updates()
        if self.search is not None:
            self._search_step()
        if self.status.state == "waiting":
            self._wait_pass()
            return
        if self.status.should_pause.value:
            if not self.status.is_paused.value:
                self._publish_layout()  # a take starts paused: the take level reads the layout then
                self.status.is_paused.value = True
            time.sleep(0.05)  # T-CAP-49: a paused camera process uses under 2 % of one core
            return
        self.status.is_paused.value = False
        timing = self.timing
        on = timing.on
        if on:
            t0 = timing.clock()
        if not self.orchestrator.should_grab_by_id(camera_id=self.camera_id):
            time.sleep(0.001)  # no spin at the gate (4.3)
            self.last_wait_end = perf_counter_ns()
            if on:
                self.gate_ns += self.last_wait_end - t0  # 3.1: the read that exists ends a refused pass
            return
        if on:
            t1 = timing.clock()
            self.gate_ns += t1 - t0
        frame = self._read()
        if on:
            retrieve = getattr(self.source, "retrieve_ns", None) if frame is not None and frame.format == "BGR" else None
            if retrieve is not None:  # 3.1: the OpenCV wait ends at the read before its retrieve (no read of its own)
                self.wait_ns += retrieve[0] - t1
            else:
                self.wait_ns += timing.clock() - t1
        if frame is not None:
            if on:
                steps = self.loop_steps
                steps.add("camera_wait", self.wait_ns)
                steps.add("gate_wait", self.gate_ns)
            self.wait_ns = self.gate_ns = 0
            self._process(frame, on)

    def _read(self, deadline_ns: int | None = None) -> CapturedFrame | None:
        """`read_frame` with the stall watch (9.5): it waits at most until 2 s after the last arrival, or after
        the end of the last wait of the loop at the gate or in `give` (recorder.md 5.2, agent 32)."""
        since = max(self.last_arrival, self.last_wait_end)
        wake = since + STALL_NS
        for limit in (deadline_ns, self.check and self.check["deadline"], self.search and self.search.wake_ns):
            if limit:
                wake = min(wake, limit)
        frame = self.source.read_frame(max(wake - perf_counter_ns(), 0) / 1e9)
        if frame is None:
            if perf_counter_ns() - since >= STALL_NS:
                raise CaptureFailure(self.stage, "no frame for 2 s", code="stalled")
            check = self.check
            now = perf_counter_ns()
            if check is not None and check["deadline"] is not None and now >= check["deadline"]:
                # 10.2: no frame came by the deadline, so frame s_a + 59 cannot be in time
                self._too_slow(rate_check.measured_rate(*check["start"], self.last_number, now))
            if self.search is not None:
                self.search.no_frame(now)
            return None
        self.last_arrival, self.last_number = frame.arrival_ns, frame.source_frame_number
        return frame

    # ----- start-up (9) -----

    def _start_up(self) -> None:
        self.started = False
        self.encoded = self.decoded_closed = self.dht_inserted = 0  # the counters of D-10 and D-11 count each open
        self._arm_hashes(None)  # the hashes of an earlier open go; the first `ready` arms a new set
        self.wait_ns = self.gate_ns = 0  # capture-timings.md 3.1: the start-up reads are not measured
        self.stage = "open"
        self.status.set_state("starting")
        self.status.update_info(failure=None, measured_fps=None)
        deadline = perf_counter_ns() + READY_LIMIT_NS
        config = self.config
        self.source = self._new_source(config)
        # `searches`: false for the OpenCV source of Linux and macOS (camera-requests.md 1.7); the endpoint reads it
        self.status.update_info(source=getattr(self.source, "name", "fake"),
                                searches=getattr(self.source, "searches", True))
        opened = self.source.open(CaptureRequest(camera_id=self.camera_id, width=config.resolution.width,
                                                 height=config.resolution.height, framerate=config.framerate,
                                                 capture_fourcc=config.capture_fourcc))
        self.last_arrival, self.last_number = perf_counter_ns(), -1
        self.recent_frames.clear()  # the source frame numbers start again at each open
        rate = opened.fps_num / opened.fps_den if opened.fps_num > 0 else 0.0
        if rate and not at_floor(rate):
            raise CaptureFailure("set mode", NO_FLOOR_MODE, code="below-floor")  # 14.1: OpenCV reports a rate under the floor
        # D22; with no reported rate (OpenCV), the requested rate and 30 for "auto" (ADR-PDD3 W2)
        self.reference_rate = rate or (config.framerate if config.framerate > 0 else rate_check.AUTO_REFERENCE_FPS)
        self.status.update_info(mode=dict(width=opened.width, height=opened.height, fps_num=opened.fps_num,
                                          fps_den=opened.fps_den, format=opened.format))
        self._check_deadline_of_start(deadline)
        self.stage = "set controls"
        self._set_start_controls(deadline)
        self._check_deadline_of_start(deadline)
        first = self.source.read_frame(0.0)  # a frame that waits since the read-back; later frames are warm-up frames
        if first is not None:
            self.last_arrival, self.last_number = first.arrival_ns, first.source_frame_number
        s0 = self.last_number + 1
        self.config = self.config.model_copy(update=dict(
            resolution=ImageResolution(width=opened.width, height=opened.height),
            framerate=rate or config.framerate))  # D17: the config stores the mode rate
        self.last_good_payload = None
        self._publish_config()
        self.stage = "warm-up"
        window_start = None
        while True:  # 9.2: 90 delivered frames, counted by `source_frame_number`
            frame = self._read_in_start(deadline)
            if frame is None:
                continue
            warm_up_frame = frame.source_frame_number - s0 + 1
            if window_start is None and warm_up_frame >= rate_check.WINDOW_FIRST:
                window_start = (frame.source_frame_number, frame.arrival_ns)
            # an empty window (the first frame seen is frame 90 or later) waits for one more frame
            if warm_up_frame >= rate_check.WARM_UP_FRAMES and frame.source_frame_number > window_start[0]:
                break
        if not self._searches():  # camera-requests.md 1.3b: a camera in AUTO has no start-up rate check
            self.stage = "rate check"
            measured = rate_check.measured_rate(*window_start, frame.source_frame_number, frame.arrival_ns)
            self.status.update_info(measured_fps=measured)
            if not rate_check.within_limit(measured, self.reference_rate):
                raise CaptureFailure("rate check", rate_check.slow_reason(self.reference_rate, measured),
                                     code="rate-low" if rate_check.is_slow(measured, self.reference_rate) else "rate-high")
        self.started = True
        self.stage = "streaming"
        self.status.set_state("waiting")
        self.control = _ControlThread(self)
        self._publish_diagnostics()  # at the end of the open
        self.next_diagnostics_ns = perf_counter_ns() + DIAGNOSTICS_INTERVAL_NS

    def _new_source(self, config: CameraConfig):
        """A new source of the factory. A source with steps of its own (`timing_steps`) gets its own StepSet
        (capture-timings.md 5.1, 5.4)."""
        source = self.source_factory(config)
        steps = getattr(source, "timing_steps", None)
        if steps is not None:
            source.timing_set = self.timing_sets["source"] = capture_timings.StepSet(self.timing, steps)
        return source

    def _retire(self, role: str) -> None:
        """5.1: the set of a closed source, a stopped decode stage or an ended writer goes into the next summary."""
        self.timing_reader.retire(self.timing_sets.pop(role, None))

    def _check_deadline_of_start(self, deadline: int) -> None:
        if not self.ipc.should_continue or self.status.should_close.value:
            raise _Stop()
        if perf_counter_ns() >= deadline:
            raise CaptureFailure("warm-up", "not ready in 15 s", code="not-ready")

    def _read_in_start(self, deadline: int) -> CapturedFrame | None:
        """A start-up read: the 15 s limit is checked between the steps and on each warm-up frame (9.3)."""
        self._check_deadline_of_start(deadline)
        return self._read(deadline)

    def _set_start_controls(self, deadline: int) -> None:
        """9.1 steps 5 and 6. The config stores the read-back values (agent 44). `AUTO` sets its held value as a
        manual value (camera-requests.md 1.3a); no call of an open has `auto=True` (1.3 item 7)."""
        value = self.config.exposure
        readback = self.source.set_controls({})  # a read: a camera with no exposure control gets no set (1.9)
        exposure = readback.get("exposure")
        self.no_exposure = exposure is not None and not exposure.present
        text = f"Camera {self.camera_id} has no manual exposure. SkellyCam does not set its exposure."
        self.status.replace_warning_items("camera_warnings", ("no_manual_exposure",), [
            dict(kind="no_manual_exposure", camera_ids=[self.camera_id], control="exposure", text=text)
        ] if self.no_exposure else [])  # it comes again at each open (1.5)
        self.exposure_range = None if self.no_exposure else getattr(self.source, "exposure_range", lambda: None)()
        if self.no_exposure:
            logger.warning(text)
        else:
            if self.config.exposure_mode == "AUTO" and self.exposure_range is not None:
                # 1.3a: the held value is set at the nearest search value (with none, inside the range of the
                # camera), and the config stores the read-back
                low, high, _ = self.exposure_range  # (min, max, step), the one shape of each source
                values = search_values(self.exposure_range)
                opened_at = min(values, key=lambda v: abs(v - value)) if values else min(max(value, low), high)
                if opened_at != value:
                    logger.info(f"Camera {self.camera_id}: the held exposure {value} is not a search value in the "
                                f"range {low} to {high} of the camera; it opens at {opened_at}")
                    value = opened_at
            readback = self.source.set_controls({"exposure": ControlSetting(auto=False, value=value)})
        self._publish_controls(readback)
        exposure = readback.get("exposure")
        if exposure is not None and exposure.present and exposure.value is not None:
            value = exposure.value
        self.config = self.config.model_copy(update=dict(exposure=value))

    def _wait_pass(self) -> None:
        """`waiting` (9.4): keep the stream, take no frame to the rings, join the gate with the others."""
        if self.ring_writer is None:
            self._attach_rings()
            if self.ring_writer is None:
                time.sleep(0.001)  # the main process makes the rings now; no read, so no stall in this short wait
                return
            self.last_arrival = perf_counter_ns()
        self._read()
        if any(status.state == "starting" for status in list(self.orchestrator.camera_statuses.values())):
            return
        count = max(int(self.status.frame_count.value), self.orchestrator.largest_gate_count())
        self.gate_count = count
        self.status.frame_count.value = count
        self.ring_count = 0
        self.status.connected.value = True
        self._arm_hashes("ready")  # the first move to `ready` of this open (D-11); a live change does not arm
        if self._searches():
            self._start_search()  # camera-requests.md 1.3b: `waiting` to `adjusting`
        else:
            self.status.set_state("ready")

    # ----- the exposure search (camera-requests.md 1.3, 1.3b) -----

    def _searches(self) -> bool:
        """A camera in `AUTO` searches, except on a source that cannot (the OpenCV source of Linux and macOS, 1.7)."""
        return self.config.exposure_mode == "AUTO" and getattr(self.source, "searches", True) and not self.no_exposure

    def _start_search(self) -> None:
        """The one-shot search on the open stream, in the state `adjusting`. A check that runs stops (1.5)."""
        self.check = None
        self.status.search_count.value += 1
        self.status.replace_warning_items("camera_warnings", SEARCH_WARNINGS, [])
        self.search_before = {name: getattr(self.config, name) for name in HELD_FIELDS}
        while not self.search_replies.empty():  # a late reply of an earlier search
            self.search_replies.get_nowait()
        self.search, self.search_final = ExposureSearch(self.reference_rate, None, self.exposure_range), None
        self.status.update_info(exposure_search=dict(state="running", chosen=None, add_light=False, reason=None,
                                                     trials=[], skipped=[]))
        self.status.set_state("adjusting")

    def _search_step(self) -> None:
        """One pass: take the results of the sets, send the next set to the control thread, and at the end set the
        result (or the held value after a failure) one more time (1.3 items 6 and 8)."""
        search = self.search
        while not self.search_replies.empty():
            value, returned_ns, error, readback = self.search_replies.get_nowait()
            if self.search_final is None:
                search.set_done(value, returned_ns, error, readback)
                continue
            if value != self.search_final:  # a reply of a value tried before the result
                continue
            if error is None and (readback is None or readback == value):
                self._end_search(self.search_final_ns)
                return
            text = f"the camera refused exposure {value} ({error})" if error else f"exposure {value} read back as {readback}"
            if search.result["state"] == "done":
                search.fail("set-failed" if error else "readback-differs", text)
            held = self.search_before["exposure"]
            if value == held:  # the held value failed too: the camera keeps what it has
                self._end_search(self.search_final_ns)
                return
            self.search_final, self.search_final_ns = held, perf_counter_ns()
            self.control.requests.put(("search", held))
        now = perf_counter_ns()
        if self.search_final is not None and now - self.search_final_ns > FINAL_SET_LIMIT_NS:
            if search.result["state"] == "done":  # [GEH0]: no camera stays `adjusting` for ever
                search.fail("set-failed", f"the set of exposure {self.search_final} gave no answer in "
                                          f"{FINAL_SET_LIMIT_NS / 1e9:g} s")
            self._end_search(now)  # 10.2 [ADR-0R76]: no answer: the check counts no frame from before the time-out
            return
        search.tick(now)
        if search.result is None:
            value = search.take_pending(perf_counter_ns())  # the first set starts the limit of 20 s
            if value is not None:
                self.control.requests.put(("search", value))
        elif self.search_final is None:
            done = search.result["state"] == "done"
            self.search_final = search.result["chosen"] if done else self.search_before["exposure"]
            self.search_final_ns = perf_counter_ns()
            self.control.requests.put(("search", self.search_final))

    def _end_search(self, after_ns: int) -> None:
        """The config holds the result, or its fields of before the search after a failure; then the check of 10.2
        from `after_ns`: the time read just before the last set went to the control thread when that set answered
        [ADR-JWZ1], or the time-out when it gave no answer [ADR-0R76]."""
        search, before = self.search, self.search_before
        self.search = None
        result = search.result
        if result["state"] == "done":
            self.config = self.config.model_copy(update=dict(exposure_mode="AUTO", exposure=result["chosen"],
                                                             exposure_found_at_fps=self.reference_rate))
            texts = [("add_light", add_light_text(self.camera_id, self.reference_rate, result["trials"]))
                     ] if result["add_light"] else []
        else:  # [GEH0]: AUTO stays the stored mode; the camera keeps its held value
            self.config = self.config.model_copy(update=dict(exposure_mode="AUTO", exposure=before["exposure"],
                                                             exposure_found_at_fps=before["exposure_found_at_fps"]))
            texts = [("exposure_search_failed", failed_text(self.camera_id, search.detail, before["exposure"]))]
        for _, text in texts:
            logger.warning(text)
        self.status.replace_warning_items("camera_warnings", SEARCH_WARNINGS, [
            dict(kind=kind, camera_ids=[self.camera_id], control="exposure", text=text) for kind, text in texts])
        # `held`: the main process copies the held value into its config once for each search (camera_group.py)
        self.status.update_info(exposure_search=result, held=dict(
            count=self.status.search_count.value, **{name: getattr(self.config, name) for name in HELD_FIELDS}))
        self._start_check(after_ns)  # `self.search` is None: the frames taken since then count once

    def _start_check(self, after_ns: int) -> None:
        """A new check of 10.2 from `after_ns` (see the callers). Each frame that the loop took after `after_ns`,
        before this call, counts, so the skip of 15 is exact [ADR-53VB, ADR-JWZ1, ADR-0R76]."""
        self.check = dict(after=after_ns, first=None, start=None, deadline=None)
        self.status.set_state("checking")
        for sfn, arrival_ns in [frame for frame in self.recent_frames if frame[1] > after_ns]:
            self._feed_check(sfn, arrival_ns)

    def _brightness(self, payload: bytes, image, flags: int) -> float | None:
        """1.3 item 2.3: the mean of all pixels of the decoded image (`np.mean`, all channels), as sfn26. The bytes
        that passed the JPEG check; None for a frame with error flags or that does not decode [GEH0]."""
        if flags & ERROR_FLAGS:
            return None
        if image is None:
            image = decode_jpeg(payload)
        return float(np.mean(image)) if image is not None else None

    def _measured_brightness(self, payload: bytes, image, flags: int) -> float | None:
        """`_brightness` in the bracket of `exposure_search_brightness` (capture-timings.md 3.1)."""
        timing = self.timing
        if not timing.on:
            return self._brightness(payload, image, flags)
        t0 = timing.clock()
        value = self._brightness(payload, image, flags)
        self.loop_steps.add("exposure_search_brightness", timing.clock() - t0)
        return value

    def _attach_rings(self) -> None:
        while not self.shm_sub.empty():
            info = self.shm_sub.get().ring_infos.get(self.camera_id)
            # A message that names the old ring is stale: it came for a change of another camera (ring 7.2).
            if info is not None and info.jpeg_ring_name != self.old_ring_name:
                self.ring_writer = FrameRingWriter.attach(info.jpeg_ring_name)
                if info.bgr_ring_name:
                    self._start_decode(FrameRingWriter.attach(info.bgr_ring_name))
                return

    def _start_decode(self, writer: FrameRingWriter) -> None:
        self.bgr_ring_writer = writer
        self.decode_stage = DecodeStage(writer, timing=self.timing)
        self.timing_sets["decode"] = self.decode_stage.timing_set
        self.decode_stage.start()

    # ----- each frame (5.1) -----

    def _process(self, frame: CapturedFrame, on: bool = False) -> None:
        """`on`: the capture timings measure this frame. Brackets that follow one another share one clock read (`t`),
        so the loop reads the clock at most 10 times for each frame (capture-timings.md 5.3)."""
        if self.replaced_base is None:
            self.replaced_base = self.source.replaced_count  # the first frame in the gate (5.2, agent 49)
        self.gate_count += 1
        number = self.gate_count
        should_record, should_finish = self.orchestrator.should_record_frame_number(frame_number=number)
        timing, steps = self.timing, self.loop_steps
        if on:
            t = timing.clock()
        image = None
        if frame.format == "BGR":
            image = frame.payload
            payload = cv2.imencode(".jpg", image, JPEG_Q90)[1].tobytes()
            if on:
                t, t0 = timing.clock(), t
                steps.add("jpeg_encode", t - t0)
            delivered_len = len(payload)
            self.encoded += 1
        else:
            payload, delivered_len = frame.payload, frame.delivered_len
        payload, flags = check_jpeg(payload, delivered_len=delivered_len, driver_error=frame.driver_error)
        if on:
            t, t0 = timing.clock(), t
            steps.add("capture_check", t - t0)
        if frame.discontinuity:
            flags |= FrameFlag.DISCONTINUITY  # D34
        if not flags & ERROR_FLAGS:
            self.last_good_payload = payload
        if flags & FrameFlag.DHT_INSERTED:
            self.dht_inserted += 1
        if len(self.hashes) < HASH_COUNT and (self.hash_trigger == "ready" or (self.hash_trigger and should_record)):
            self._hash(payload, frame.source_frame_number, flags)
            if on:
                t, t0 = timing.clock(), t
                steps.add("frame_hash", t - t0)
        fields = dict(frame_number=self.ring_count, arrival_ns=frame.arrival_ns, sample_ns=frame.sample_ns,
                      source_frame_number=frame.source_frame_number, flags=int(flags),
                      rotation_cw_deg=rotation_to_cw_deg(self.config.rotation))
        if should_record:  # the recorder first, then the ring, with the same bytes (ring 5.3, 5.7)
            self._give(RecorderFrame(payload=payload, frame_number=number, arrival_ns=frame.arrival_ns,
                                     sample_ns=frame.sample_ns, source_frame_number=frame.source_frame_number,
                                     flags=int(flags), delivered_len=delivered_len,
                                     rotation_cw_deg=fields["rotation_cw_deg"]))
            if on:
                t, t0 = timing.clock(), t
                steps.add("recorder_give", t - t0)
        elif should_finish and self.take_writer is not None:
            self._end_take()
            if on:
                t = timing.clock()  # take_end has its own bracket
        self.ring_count += 1
        try:
            self.ring_writer.write(payload, **fields)
            if on:
                t, t0 = timing.clock(), t
                steps.add("ring_write", t - t0)
                steps.add("arrival_to_published", t - frame.arrival_ns)
            if self.decode_stage is not None:
                # The one decode is in the decode stage; the recorder needs none (recorder.md 10 item 6, D9).
                item = (DecodeInput(payload=image, source="BGR", **fields) if image is not None
                        else DecodeInput(payload=payload, source="JPEG", **fields))
                self.decode_stage.waiting_place.put(item)
        except Exception as error:  # a failing ring write does not stop capture or recording (ring 5.3)
            logger.exception(f"Frame ring write failed for camera {self.camera_id}: {error}")
        self.status.frame_count.value = number
        self.status.replaced_count.value = self.replaced_total + self.source.replaced_count - self.replaced_base
        self.recent_frames.append((frame.source_frame_number, frame.arrival_ns))
        self._feed_check(frame.source_frame_number, frame.arrival_ns)
        if self.search is not None:
            self.search.frame(frame.source_frame_number, frame.arrival_ns,
                              lambda: self._measured_brightness(payload, image, flags))
        self._feed_block(frame)

    def _feed_check(self, sfn: int, arrival_ns: int) -> None:
        """The check after a live change (10.2): skip 15 delivered frames, then measure over 60. Skipped frame 1
        is the first frame that arrived after `after` (the start of the set) [ADR-53VB]."""
        check = self.check
        if check is None or self.search is not None or arrival_ns <= check["after"]:
            return
        if check["first"] is None:
            check["first"] = sfn
        if check["start"] is None:
            if sfn >= check["first"] + rate_check.CHECK_SKIP:
                check["start"] = (sfn, arrival_ns)
                check["deadline"] = rate_check.early_deadline_ns(arrival_ns, self.reference_rate)
            return
        if sfn < check["start"][0] + rate_check.CHECK_FRAMES - 1:
            if arrival_ns > check["deadline"]:
                # 10.2: a later frame came after the deadline, so frame s_a + 59 did not come in time
                self._too_slow(rate_check.measured_rate(*check["start"], sfn, arrival_ns))
            return
        measured = rate_check.measured_rate(*check["start"], sfn, arrival_ns)
        self.check = None
        self.status.update_info(measured_fps=measured)
        if self.signals.empty():  # a newer change starts a new check (agent 27)
            self.status.set_state("ready" if rate_check.within_limit(measured, self.reference_rate)
                                  else "too_slow")

    def _too_slow(self, measured: float) -> None:
        """The early decision of 10.2. Only a frame that did not come decides it: a frame that came in time
        but waits (paused, or at the gate) gives no decision.

        `measured` is the rate of the window up to the decision: the frames delivered since frame s_a, over
        the time since t_a. It is below the limit by the rule of the deadline. The status shows it (8.4)."""
        self.check = None
        if self.search is not None:
            return
        self.status.update_info(measured_fps=measured)
        if self.signals.empty():
            self.status.set_state("too_slow")

    def _feed_block(self, frame: CapturedFrame) -> None:
        """10.3: one warning for each slow period of a recording; blocks of 60 delivered frames."""
        if self.take_writer is None:
            self.block, self.slow = None, False
            return
        if self.block is None:
            self.block = (frame.source_frame_number, frame.arrival_ns)
            return
        if frame.source_frame_number < self.block[0] + rate_check.BLOCK_FRAMES:
            return
        measured = rate_check.measured_rate(*self.block, frame.source_frame_number, frame.arrival_ns)
        slow = rate_check.is_slow(measured, self.reference_rate)
        if slow and not self.slow:
            logger.warning(f"Camera {self.camera_id} is slow during the recording: {measured:.2f} fps")
        self.slow = slow
        self.block = (frame.source_frame_number, frame.arrival_ns)

    # ----- changes (8.3, 11.2) and recordings -----

    def _check_updates(self) -> None:
        if not self.update_sub.empty():
            requested = self.update_sub.get().requested_configs.get(self.camera_id)
            if requested is not None:
                self._apply_change(requested)
        while not self.recording_sub.empty():
            spec = self.recording_sub.get().take_specs.get(self.camera_id)
            if spec is not None:
                self._start_take(spec)
        while not self.signals.empty():  # first: a queued live change lands before a search starts
            _, after_ns, config = self.signals.get_nowait()
            if self.search is not None:  # [GEH0]: its other fields (rotation) land; the search keeps its held fields
                self.config = config.model_copy(update={name: getattr(self.config, name) for name in HELD_FIELDS})
                continue
            self.config = config
            self._start_check(after_ns)  # 10.2: the frames taken after the change and before this read count
        if self.status.search_requested.value:
            self._requested_search()

    def _requested_search(self) -> None:
        """The button or "Search again" (camera-requests.md 1.2 (c)): the camera goes to `AUTO` and searches. Never
        during a take, and only on a stream that runs (1.5); the main process checks the states first."""
        if (self.search is None and self.take_writer is None and not self.status.should_pause.value
                and not self.no_exposure and self.status.state in ("ready", "too_slow", "checking")):
            self._start_search()
            self.config = self.config.model_copy(update=dict(exposure_mode="AUTO"))
        self.status.search_requested.value = False  # last: the main process then sees the new count and state

    def _apply_change(self, requested: CameraConfig) -> None:
        current = self.config
        if needs_reopen(requested, current):
            self._reopen(requested)
            return
        if requested.exposure_mode == "AUTO" and current.exposure_mode != "AUTO" and self.search is None \
                and getattr(self.source, "searches", True) and not self.no_exposure \
                and not self.status.should_pause.value and self.take_writer is None:  # 1.1 [G4]: never in a take
            # camera-requests.md 1.2 (c): a switch to AUTO searches on the open stream; the response sees `adjusting`
            self._start_search()  # it keeps the MANUAL setting of before, for a failed search (1.3 item 6)
            self.config = requested.model_copy(update=dict(
                framerate=current.framerate, resolution=current.resolution, exposure=current.exposure,
                exposure_found_at_fps=current.exposure_found_at_fps))
            self._publish_config()
            return
        adopted = requested.model_copy(update=dict(framerate=current.framerate, resolution=current.resolution))
        if requested.exposure_mode == "MANUAL":
            adopted = adopted.model_copy(update=dict(exposure_found_at_fps=None))  # camera-requests.md 1.3a
        changes = {}
        if self.no_exposure:  # 1.9 [K3]: an exposure in a request is ignored, not refused; the warning stays
            pass
        elif requested.exposure_mode == "MANUAL" and (current.exposure_mode, current.exposure) != ("MANUAL", requested.exposure):
            changes["exposure"] = ControlSetting(auto=False, value=requested.exposure)
        if changes:
            self.status.replace_warning_items("camera_warnings", SEARCH_WARNINGS, [])  # 1.5: an exposure change
            # A failed change publishes self.config: it must hold the request's number and name (camera-requests.md 8.1)
            self.config = current.model_copy(update=dict(camera_index=requested.camera_index,
                                                         camera_name=requested.camera_name))
            self.control.requests.put((adopted, changes))  # live, on the control thread (U16)
            return
        if requested.exposure_mode == "AUTO":
            adopted = adopted.model_copy(update=dict(exposure=current.exposure,
                                                     exposure_found_at_fps=current.exposure_found_at_fps))
        self.config = adopted
        self._publish_config()

    def _reopen(self, requested: CameraConfig) -> None:
        """A change of resolution or rate reopens only this camera and recreates its rings (D31, ring 7.5)."""
        self.status.set_state("starting")  # the stall watch is off during the close (unix-capture.md 4.10)
        self._stop_control()
        self.status.set_state("starting")  # again: a live change of the control thread can set `checking` (F3)
        self._close_rings()
        self._add_replaced()
        self.source.close()
        self._retire("source")
        if self.search is not None:  # [GEH0]: as `_end`, the search ends as `camera-closed` in the status
            self.search.cancel()
            self.status.update_info(exposure_search=self.search.result)
            self.search = None
        if requested.exposure_mode == "AUTO":  # camera-requests.md 1.3a [A8]: the held value, not the request's
            requested = requested.model_copy(update=dict(exposure=self.config.exposure,
                                                         exposure_found_at_fps=self.config.exposure_found_at_fps))
        self.config = requested
        self._start_up()

    # ----- the take (recorder.md section 10) -----

    def _start_take(self, spec) -> None:
        if self.take_writer is not None:
            self._end_take()
        orchestrator = self.orchestrator
        if orchestrator.first_recording_frame_number.value == -1 or orchestrator.last_frame != -1:
            # The take ended (or its start failed) before this spec came: no writer (ADR-P5VE).
            text = f"camera {self.camera_id}: the take ended before its writer started"
            logger.warning(text)
            self.status.update_info(writer_failure=text)
            return
        timing = self.timing
        on = timing.on
        try:
            self.status.alive_count.value += 1  # the file open can take long; the watch is off in the pause too
            if on:
                t0 = timing.clock()
            self.take_writer = start_take_writer(self.camera_id, spec, self.status.writer_progress_at,
                                                 self.status.alive_count, timing=timing)
            if on:
                self.loop_steps.add("take_start", timing.clock() - t0)
            self.timing_sets["writer"] = self.take_writer.timing_set
            self.status.alive_count.value += 1
        except Exception as error:  # the camera runs on; the record start fails with this text (ADR-P5VE)
            text = f"camera {self.camera_id}: the take writer did not start: {error}"
            logger.error(text)
            self.status.update_info(writer_failure=text)
            return
        self.take_failed = False
        self._arm_hashes("recording")  # D-11: the recorded frames of each record start
        self.status.recording_in_progress.value = True  # the main process unpauses when each camera has it

    def _give(self, frame: RecorderFrame | None) -> None:
        """Give a frame, or a `missing` row for None. After a stall or a write error, nothing (4.3)."""
        if self.take_writer is None or self.take_failed:
            return
        try:
            if frame is None:
                self.take_writer.give_missing()
            else:
                self.take_writer.give(frame)
        except (RecorderStalled, RecorderWriteError) as error:
            self.take_failed = True
            text = f"disk stall on camera {self.camera_id}" if isinstance(error, RecorderStalled) else str(error)
            logger.error(f"Camera {self.camera_id}: the take ends: {text}")
            # The main process ends the take for every camera (recorder.md 5.3, 5.4) [C5].
            self.ipc.pubsub.topics[TopicTypes.RECORDING_FINISHED].publish(
                RecordingFinishedMessage(camera_id=self.camera_id, error=text))
        finally:
            self.last_wait_end = perf_counter_ns()

    def _end_take(self) -> None:
        """End the camera writer with the frame count of the take (7.6) and send its result at once.

        With no last frame, the take did not end, and the frame count of the take is not known. When the take
        goes on (this camera ends alone), `abandon` writes the queued frames and the take level completes the
        pair after the join (7.4). When no take level follows (the group stops, the main process is gone),
        the first camera that ends sets the last frame of the take after the latest group frame, so that each
        camera finishes its pair with the same rows (placeholders to that frame, 7.3) and its `# end` line."""
        writer, self.take_writer = self.take_writer, None
        timing = self.timing
        on = timing.on
        try:
            if self.orchestrator.last_frame == -1:
                lock = self.orchestrator.last_recording_frame_number.get_lock()
                # A bounded wait (unix-capture.md 4.10): a camera killed while it held the lock keeps it for ever.
                locked = not self.ipc.should_continue and lock.acquire(timeout=FRAME_LOCK_WAIT_S)
                if not locked:
                    if on:
                        t0 = timing.clock()
                    error = writer.abandon()
                    if on:
                        self.loop_steps.add("take_end", timing.clock() - t0)
                    if not self.ipc.should_continue:  # with no lock: this camera ends its part of the take alone
                        error = error or (f"camera {self.camera_id}: no lock of the last frame of the take in "
                                          f"{FRAME_LOCK_WAIT_S:g} s")
                        logger.error(error)
                    if error is not None:  # the take level ends the take with this error (recorder.md 5.4)
                        self.ipc.pubsub.topics[TopicTypes.RECORDING_FINISHED].publish(
                            RecordingFinishedMessage(camera_id=self.camera_id, error=error))
                    return
                try:
                    if self.orchestrator.last_frame == -1:
                        # The gate lets another camera be one frame ahead, in hand but not yet counted: + 2.
                        latest = max(self.orchestrator.largest_gate_count(), self.gate_count)
                        self.orchestrator.last_frame = max(latest + 2, self.orchestrator.first_recording_frame_number.value)
                finally:
                    lock.release()
            frame_count = self.orchestrator.take_frame_count()
            if on:
                t0 = timing.clock()
            result = writer.end(frame_count)
            if on:
                self.loop_steps.add("take_end", timing.clock() - t0)
            self.ipc.pubsub.topics[TopicTypes.RECORDING_FINISHED].publish(
                RecordingFinishedMessage(camera_id=self.camera_id, result=result))
        finally:
            self._retire("writer")
            self.status.recording_in_progress.value = False

    def _missing_until_end(self) -> None:
        """A camera that died during a take: one placeholder row for each new group frame, up to the last
        frame of the take (recorder.md 7.3, section 10 item 7) [M1]. Blocking sleeps of 1 ms (4.3)."""
        number = self.gate_count
        orchestrator = self.orchestrator
        while self.ipc.should_continue and not self.status.should_close.value:
            last = orchestrator.last_frame
            # With no camera left in the gate, the last group frame of the stop is the one to reach.
            group = max(orchestrator.largest_gate_count(), last - 1 if last != -1 else -1)
            while number < group:
                number += 1
                self.status.frame_count.value = number
                if orchestrator.should_record_frame_number(frame_number=number)[0]:
                    self._give(None)
            if orchestrator.should_record_frame_number(frame_number=number + 1)[1]:
                return
            time.sleep(0.001)

    def _publish_layout(self) -> None:
        layout = None
        if self.last_good_payload is not None:
            try:
                sof = parse_sof(self.last_good_payload)
                layout = dict(width=sof.width, height=sof.height, factors=sof.factors)
            except ValueError:
                pass
        self.status.update_info(layout=layout)

    # ----- failures and the end -----

    def _fail(self, failure: CaptureFailure, at_end: bool = False) -> None:
        """Report the first failure (section 12): the failure object, then the state (8.2).

        A started camera is `dead` at once, so that it leaves the gate before its files and its close (6.7).
        A camera that fails at start is `failed` after its close (8.2), when `at_end`."""
        with self._failure_lock:
            if self.failed:
                return
            self.failed = True
        stage = failure.stage
        if self.started:  # ADR-HP7D item 7: after the start-up, a failure is a `streaming` failure
            stage = "close" if stage == "close" else "streaming"
        report = CameraSetupFailure(camera_id=self.camera_id, stage=stage, reason=failure.reason)
        self.ipc.report_setup_failure(report)
        self.status.update_info(failure=dict(camera_id=report.camera_id, stage=report.stage,
                                             reason=report.reason[:2048], code=failure.code))
        self.failure_code, self.failure_stage = failure.code, report.stage
        if at_end and not self.started:
            self.end_state = "failed"
        else:
            self.status.set_state("dead" if self.started else "failed")
        logger.warning(str(report))
        self._publish_diagnostics()

    def _finish_take(self) -> None:
        if self.take_writer is None:
            return
        if self.failed and self.started:  # dead while its process runs: placeholders to the end (M1)
            self._missing_until_end()
        if self.take_writer is not None:
            self._end_take()

    def hard_end(self) -> None:
        """6.6: after a hang, end the camera process at once with no clean-up. The main process completes the
        files of a take after the process ended (recorder.md 7.4) [R4]. THREAD workers only end the thread."""
        if parent_process() is None:
            return
        self.status.update_info(hung=True)  # the take level gives the reason "hang" (recorder.md 7.4)
        os._exit(1)

    def _end(self, hung: bool) -> None:
        self.status.closing.value = True  # the stall watch is off in each close, also from the group flags (F9)
        if self.search is not None:  # camera-requests.md 1.3 item 6: the search sets nothing; the close restores
            self.search.cancel((self.failure_code or "camera-closed") if self.failed else "camera-closed")
            self.status.update_info(exposure_search=self.search.result)
            self.search = None
        if hung:
            self.hard_end()
        try:
            self._finish_take()  # before the close: a slow close does not delay the end of the take (D38)
        finally:
            if not hung:
                self._stop_control()
                self._add_replaced()
                if self.source is not None:
                    try:
                        # 4.7 [Z7F3]: no call into a wedged camera; each other failure (and a lost heartbeat) restores
                        self.source.close(restore=self.failure_code not in WEDGE_CODES)
                    except CaptureFailure as failure:
                        self._fail(failure)
                        hung = failure.hung
                    self._retire("source")
                    if not hung:
                        self._publish_diagnostics()  # at the close
                        self._flush_diagnostics()
            if self.end_state:
                self.status.set_state(self.end_state)
            self._close_rings()
            self._add_replaced()
            self.status.replaced_count.value = self.replaced_total
            logger.info(f"Camera {self.camera_id} stop: replaced {self.replaced_total} frames since its first "
                        f"frame in the gate")
            if hung:
                self.hard_end()
            self.status.connected.value = False
            self.status.closed.value = True
            logger.debug(f"Camera {self.camera_id} loop ended")

    def _close_rings(self) -> None:
        if self.decode_stage is not None:
            self.decode_stage.stop()
            self.decoded_closed += self.decode_stage.decoded
            self.decode_stage = None
            self._retire("decode")
        if self.bgr_ring_writer is not None:
            self.bgr_ring_writer.close()
            self.bgr_ring_writer = None
        if self.ring_writer is not None:
            self.old_ring_name = self.ring_writer.name
            self.ring_writer.close()
            self.ring_writer = None

    def _add_replaced(self) -> None:
        if self.replaced_base is not None:
            self.replaced_total += self.source.replaced_count - self.replaced_base
            self.replaced_base = None

    def _stop_control(self) -> None:
        control, self.control = self.control, None
        if control is not None:
            control.stop.set()
            control.requests.put(None)
            if threading.current_thread() is not control.thread:
                control.thread.join(BOUNDED_CALL_LIMIT_S + 1.0)

    # ----- diagnostics (unix-capture.md 4.2 items 2 and 3) -----

    def _arm_hashes(self, trigger: str | None) -> None:
        """D-11: a new set of 30 hashes replaces the old set."""
        self.hashes, self.dqt_hashes, self.dht_present, self.hash_trigger = [], [], None, trigger

    def _hash(self, payload: bytes, source_frame_number: int, flags: int) -> None:
        self.hashes.append((source_frame_number, hashlib.sha256(payload).hexdigest()))
        self.dqt_hashes.append(hashlib.sha256(dqt_segments(payload)).hexdigest())
        if not flags & ERROR_FLAGS:
            self.dht_present = bool(self.dht_present) or not flags & FrameFlag.DHT_INSERTED

    def _loop_diagnostics(self) -> dict:
        stage, hashes, dqt = self.decode_stage, list(self.hashes), list(self.dqt_hashes)
        data = dict(decoded_by_skellycam=self.decoded_closed + (stage.decoded if stage is not None else 0),
                    encoded_by_skellycam=self.encoded, dht_inserted=self.dht_inserted,
                    sha256_trigger=self.hash_trigger, dqt_sha256=dqt[0] if dqt else None,
                    dqt_distinct=len(set(dqt)) if dqt else None, dht_present=self.dht_present)
        for i in range(HASH_COUNT):
            data[f"sha256_frame_{i:02d}"], data[f"sha256_{i:02d}"] = hashes[i] if i < len(hashes) else (None, None)
        return data

    def _flush_diagnostics(self) -> None:
        """A camera process waits at most 1 s until its close dict is in the pipe; then it exits anyway, so a full
        pipe never blocks the exit (the main process reads during the group close). THREAD workers share the
        queue object with the main process: nothing to flush."""
        if parent_process() is None:
            return
        deadline = time.monotonic() + DIAGNOSTICS_FLUSH_S
        for subscription in getattr(self.ipc.pubsub.topics.get(TopicTypes.DIAGNOSTICS), "subscriptions", ()):
            subscription.close()  # the feeder thread writes what waits, then ends
            feeder = getattr(subscription, "_thread", None)  # shortcut: a private name of multiprocessing.Queue
            if feeder is not None:
                feeder.join(max(0.0, deadline - time.monotonic()))

    def _publish_diagnostics(self) -> None:
        """The full dict to the main process. A dict over 32 KiB (pickled) is not sent, and is logged one time.
        It carries the capture timings of the window that ends (capture-timings.md 6.2)."""
        timing = self.timing
        on_loop = threading.current_thread() is self.loop_thread
        measured = on_loop and timing.on
        if measured:
            t0 = timing.clock()
        try:
            data = self.source.diagnostics() if self.source is not None else empty_diagnostics()
            data.update(self._loop_diagnostics())
            if data.get("fail_code") is None and self.failure_code is not None:
                data.update(fail_code=self.failure_code, fail_stage=self.failure_stage)
            message = DiagnosticsMessage(camera_id=self.camera_id, diagnostics=data, timings=self._timings(on_loop))
            size = len(pickle.dumps(message))
            if size > DIAGNOSTICS_LIMIT_BYTES:
                raise ValueError(f"the diagnostics have {size} bytes, over the limit of {DIAGNOSTICS_LIMIT_BYTES}")
            self.ipc.pubsub.topics[TopicTypes.DIAGNOSTICS].publish(message, print_log=False)
        except Exception as error:  # the diagnostics never stop a camera
            if not self.diagnostics_logged:
                self.diagnostics_logged = True
                logger.warning(f"Camera {self.camera_id}: diagnostics not sent: {type(error).__name__}: {error}")
        if measured:  # 3.1: its sample goes into the next window
            self.loop_steps.add("diagnostics_publish", timing.clock() - t0)

    def _timings(self, on_loop: bool) -> dict | None:
        """5.1: only the loop thread reads the buffers; another thread sends the last summary again. A fault of the
        timings sends None and is logged one time: the diagnostics dict still goes."""
        if not on_loop:
            return self.timing_last
        try:
            return self._take_timings()
        except Exception as error:
            self.timing_last = None
            if not self.timings_logged:
                self.timings_logged = True
                logger.warning(f"Camera {self.camera_id}: capture timings not sent: {type(error).__name__}: {error}")
            return None

    def _take_timings(self) -> dict | None:
        """Close the window on the loop thread (5.1, 5.2). The switch applies here (2 item 4): the window that ends
        gives a summary only when the switch was on for it and still is, else None. The next window starts here."""
        timing = self.timing
        was_on = timing.on
        timing.on = on = bool(self.status.log_capture_times.value)
        if on != was_on:
            self.wait_ns = self.gate_ns = 0  # no wait of a pass that was not measured goes into a sample
        windows = self.timing_reader.read([self.loop_steps, *self.timing_sets.values()])
        summary = None
        if on:
            now = timing.clock()
            if was_on:
                summary = capture_timings.build_summary(
                    source="camera", camera_group_id=getattr(self.ipc, "group_id", None), camera_id=self.camera_id,
                    clock="perf_counter_ns", seq=self.timing_seq, window_end_ns=now,
                    window_ns=now - self.timing_start_ns, step_ids=self._timing_steps(), windows=windows)
                self.timing_seq += 1
            self.timing_start_ns = now
        self.timing_last = summary
        return summary

    def _timing_steps(self) -> tuple:
        """5.4: the steps that apply to this camera."""
        steps = capture_timings.CAMERA_STEPS + tuple(getattr(self.source, "timing_steps", ()))
        return steps + capture_timings.BGR_STEPS if self.config.bgr_ring else steps

    # ----- publishing -----

    def _publish_config(self, failed_change: str | None = None) -> None:
        self.ipc.pubsub.topics[TopicTypes.EXTRACTED_CONFIG].publish(
            DeviceExtractedConfigMessage(extracted_config=self.config, control_change_failed=failed_change))

    def _publish_controls(self, readback: ControlState) -> None:
        self.status.update_info(controls={name: dict(present=value.present, auto=value.auto, value=value.value)
                                          for name, value in readback.items()})


def dqt_segments(payload: bytes) -> bytes:
    """The DQT segments of a JPEG before its first SOS (D-11 `dqt_sha256`)."""
    found, i, n = [], 2, len(payload)
    while i + 4 <= n and payload[i] == 0xFF and payload[i + 1] != 0xDA:
        if payload[i + 1] == 0xFF:  # a fill byte before a marker
            i += 1
            continue
        end = i + 2 + int.from_bytes(payload[i + 2:i + 4], "big")
        if payload[i + 1] == 0xDB:
            found.append(payload[i:end])
        i = end
    return b"".join(found)


class _ControlThread:
    """One thread for each camera process (4.3, U16): it reads the controls one time per second and
    applies each live control change. A hung call blocks only this thread."""

    def __init__(self, loop: CameraLoop):
        self.loop = loop
        self.requests = queue.Queue()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, name=f"controls {loop.camera_id}", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        loop = self.loop
        failing = False
        while not self.stop.is_set():
            try:
                request = self.requests.get(timeout=CONTROL_READ_INTERVAL_S)
            except queue.Empty:
                request = ()
            if self.stop.is_set() or request is None:
                return
            try:
                if request and isinstance(request[0], str):
                    self._search_set(request[1])
                elif request:
                    self._live_change(*request)
                elif loop.search is None:  # camera-requests.md 1.3 [A4]: no read while the search runs
                    loop._publish_controls(loop.source.set_controls({}))
            except CaptureFailure as failure:
                if failure.hung:
                    loop._fail(failure)
                    loop.hung.set()
                    loop.hard_end()
                    return
                # one warning for each run of failed reads, not one each second
                (logger.debug if failing else logger.warning)(
                    f"Camera {loop.camera_id}: control read failed: {failure.reason}")
                failing = True
                continue
            except Exception as error:
                logger.exception(f"Camera {loop.camera_id} control thread error: {error}")
            failing = False

    def _search_set(self, value: int) -> None:
        """One set of the exposure search (camera-requests.md 1.3). The loop gets (value, return time, error text,
        read-back value). A hang raises, as each control call (6.6)."""
        loop = self.loop
        try:
            readback = loop.source.set_controls({"exposure": ControlSetting(auto=False, value=value)})
        except CaptureFailure as failure:
            if failure.hung:
                raise
            loop.search_replies.put((value, perf_counter_ns(), failure.reason, None))
            return
        except Exception as error:  # [GEH0]: each failed set gives a reply, so the search never waits for ever
            logger.exception(f"Camera {loop.camera_id}: the exposure set of {value} raised: {error}")
            loop.search_replies.put((value, perf_counter_ns(), f"{type(error).__name__}: {error}", None))
            return
        returned = perf_counter_ns()
        loop._publish_controls(readback)
        got = readback.get("exposure")
        loop.search_replies.put((value, returned, None, got.value if got is not None and got.present else None))

    def _live_change(self, config: CameraConfig, changes: dict[str, ControlSetting]) -> None:
        """11.2, U14: a change that fails without a hang leaves the camera in its earlier state."""
        loop = self.loop
        after_ns = perf_counter_ns()
        wanted = changes["exposure"]
        try:
            readback = loop.source.set_controls(changes)
        except CaptureFailure as failure:
            if failure.hung:
                raise
            self._failed(f"Camera {loop.camera_id}: the exposure change failed: {failure.reason}")
            return
        loop._publish_controls(readback)
        got = readback.get("exposure")
        if not wanted.auto and got is not None and not got.auto and got.value != wanted.value:
            self._failed(f"Camera {loop.camera_id}: the exposure change to {wanted.value} failed; the camera "
                         f"read back {got.value}")
            return
        if got is not None and got.value is not None:
            config = config.model_copy(update=dict(exposure=got.value))
        if loop.search is None:  # a search that runs keeps `adjusting` (1.4)
            loop.status.set_state("checking")  # before the response, so that a record start sees it (D33)
        loop.signals.put(("check", after_ns, config))
        loop.ipc.pubsub.topics[TopicTypes.EXTRACTED_CONFIG].publish(DeviceExtractedConfigMessage(extracted_config=config))

    def _failed(self, text: str) -> None:
        logger.warning(text)
        self.loop._publish_config(failed_change=text)
