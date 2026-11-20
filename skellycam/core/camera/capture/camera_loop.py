"""The shared camera loop (specs/windows-capture.md, sections 5, 8 to 12).

One loop in each camera process serves each source (D6). The loop reads the time only through the
module name `perf_counter_ns`, so that a test can give it a virtual clock (ADR-HP7D item 12).
"""
import logging
import os
import queue
import threading
import time
from collections.abc import Callable
from multiprocessing import parent_process

import cv2
import numpy as np

from skellycam.core.camera.capture import rate_check
from skellycam.core.camera.capture.modes import NO_FLOOR_MODE, at_floor, rates_equal
from skellycam.core.camera.capture.source import (
    BOUNDED_CALL_LIMIT_S,
    CapturedFrame,
    CaptureFailure,
    CaptureRequest,
    ControlSetting,
    ControlState,
)
from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.config.image_resolution import ImageResolution
from skellycam.core.camera.opencv.opencv_helpers.recommend_camera_exposure_setting import (
    MIN_EXPOSURE,
    NUMBER_OF_FRAMES_TO_SETTLE,
    TARGET_BRIGHTNESS,
)
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
from skellycam.core.ipc.pubsub.pubsub_topics import DeviceExtractedConfigMessage, RecordingFinishedMessage
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
JPEG_Q90 = [int(cv2.IMWRITE_JPEG_QUALITY), 90]  # ring 2.3, 8.8
RECOMMEND_MAX_EXPOSURE = -5  # 11.1, decision H (ADR-JMS0): -4 gives about 16 fps on the Logitech cameras
RECOMMEND_OFFSET = -1  # 11.1, decision H: one step darker than the nearest value, as the old helper


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


def start_take_writer(camera_id, spec, progress=None) -> CameraTakeWriter:
    """Start the camera writer of a take (recorder.md 10 item 5). A spec of another camera is refused (D41)."""
    if spec.camera_id != camera_id:
        raise ValueError(f"the take spec of camera {spec.camera_id} came to camera {camera_id}")
    return CameraTakeWriter.start(spec, progress=progress)


def needs_reopen(requested: CameraConfig, current: CameraConfig) -> bool:
    """A change of resolution or rate reopens the camera (D31). Each other change is live (11.2)."""
    return ((requested.resolution, requested.capture_fourcc, requested.bgr_ring)
            != (current.resolution, current.capture_fourcc, current.bgr_ring)
            or (requested.framerate > 0 and not rates_equal(requested.framerate, current.framerate))
            or requested.exposure_mode == "RECOMMEND")  # RECOMMEND runs at the open (11.1)


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
        self.signals = queue.Queue()
        self.hung = threading.Event()
        self._failure_lock = threading.Lock()
        self.failed = False
        self.end_state: str | None = None  # the state that the end sets after the close

    # ----- the run -----

    def run(self) -> None:
        hung = False
        try:
            self._start_up()
            while self.ipc.should_continue and not self.status.should_close.value:
                self._pass()
        except _Stop:
            pass
        except _Hung:
            hung = True
        except CaptureFailure as failure:
            hung = failure.hung
            self._fail(failure, at_end=not hung)
        except Exception as error:
            logger.exception(f"Camera {self.camera_id} loop error: {error}")
            self._fail(CaptureFailure(self.stage, f"{type(error).__name__}: {error}"), at_end=True)
        finally:
            if not hung and self.ipc.heartbeat_lost:
                self._lost_heartbeat()
            self._end(hung)

    def _lost_heartbeat(self) -> None:
        """Decision L: no heartbeat of the server for 10 s. This camera ends; its take files are finished and its
        camera released by `_end`. A live main process gets the reason in the status and ends the take with it."""
        text = "lost the server's heartbeat"
        if self.take_writer is not None:
            self.ipc.pubsub.topics[TopicTypes.RECORDING_FINISHED].publish(
                RecordingFinishedMessage(camera_id=self.camera_id, error=f"camera {self.camera_id} {text}"))
        self._fail(CaptureFailure(self.stage, text))

    def _pass(self) -> None:
        if self.hung.is_set():
            raise _Hung()
        self._check_updates()
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
        if not self.orchestrator.should_grab_by_id(camera_id=self.camera_id):
            time.sleep(0.001)  # no spin at the gate (4.3)
            self.last_wait_end = perf_counter_ns()
            return
        frame = self._read()
        if frame is not None:
            self._process(frame)

    def _read(self, deadline_ns: int | None = None) -> CapturedFrame | None:
        """`read_frame` with the stall watch (9.5): it waits at most until 2 s after the last arrival, or after
        the end of the last wait of the loop at the gate or in `give` (recorder.md 5.2, agent 32)."""
        since = max(self.last_arrival, self.last_wait_end)
        wake = since + STALL_NS
        for limit in (deadline_ns, self.check and self.check["deadline"]):
            if limit:
                wake = min(wake, limit)
        frame = self.source.read_frame(max(wake - perf_counter_ns(), 0) / 1e9)
        if frame is None:
            if perf_counter_ns() - since >= STALL_NS:
                raise CaptureFailure(self.stage, "no frame for 2 s")
            check = self.check
            now = perf_counter_ns()
            if check is not None and check["deadline"] is not None and now >= check["deadline"]:
                # 10.2: no frame came by the deadline, so frame s_a + 59 cannot be in time
                self._too_slow(rate_check.measured_rate(*check["start"], self.last_number, now))
            return None
        self.last_arrival, self.last_number = frame.arrival_ns, frame.source_frame_number
        return frame

    # ----- start-up (9) -----

    def _start_up(self) -> None:
        self.started = False
        self.stage = "open"
        self.status.set_state("starting")
        self.status.update_info(failure=None, measured_fps=None)
        deadline = perf_counter_ns() + READY_LIMIT_NS
        config = self.config
        self.source = self.source_factory(config)
        self.status.update_info(source=getattr(self.source, "name", "fake"))
        opened = self.source.open(CaptureRequest(camera_id=self.camera_id, width=config.resolution.width,
                                                 height=config.resolution.height, framerate=config.framerate,
                                                 capture_fourcc=config.capture_fourcc))
        self.last_arrival, self.last_number = perf_counter_ns(), -1
        rate = opened.fps_num / opened.fps_den if opened.fps_num > 0 else 0.0
        if rate and not at_floor(rate):
            raise CaptureFailure("set mode", NO_FLOOR_MODE)  # 14.1: OpenCV reports a rate under the floor
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
        self.stage = "rate check"
        measured = rate_check.measured_rate(*window_start, frame.source_frame_number, frame.arrival_ns)
        self.status.update_info(measured_fps=measured)
        if not rate_check.within_limit(measured, self.reference_rate):
            raise CaptureFailure("rate check", rate_check.slow_reason(self.reference_rate, measured))
        self.started = True
        self.stage = "streaming"
        self.status.set_state("waiting")
        self.control = _ControlThread(self)

    def _check_deadline_of_start(self, deadline: int) -> None:
        if not self.ipc.should_continue or self.status.should_close.value:
            raise _Stop()
        if perf_counter_ns() >= deadline:
            raise CaptureFailure("warm-up", "not ready in 15 s")

    def _read_in_start(self, deadline: int) -> CapturedFrame | None:
        """A start-up read: the 15 s limit is checked between the steps and on each warm-up frame (9.3)."""
        self._check_deadline_of_start(deadline)
        return self._read(deadline)

    def _set_start_controls(self, deadline: int) -> None:
        """9.1 steps 5 and 6. The config stores the read-back values (agent 44)."""
        mode, value = self.config.exposure_mode, self.config.exposure
        if mode == "RECOMMEND":
            mode, value = "MANUAL", self._recommend(deadline)
        setting = ControlSetting(auto=True, value=None) if mode == "AUTO" else ControlSetting(auto=False, value=value)
        readback = self.source.set_controls({"exposure": setting})
        self._publish_controls(readback)
        exposure = readback.get("exposure")
        if exposure is not None and exposure.present and exposure.value is not None:
            value = exposure.value
        self.config = self.config.model_copy(update=dict(exposure_mode=mode, exposure=value))

    def _recommend(self, deadline: int) -> int:
        """RECOMMEND (11.1): -12 to -5, 10 frames to settle, the mean of the image nearest to 127.5, then one
        step darker, in the range."""
        best = None
        for value in range(MIN_EXPOSURE, RECOMMEND_MAX_EXPOSURE + 1):
            set_ns = perf_counter_ns()
            self.source.set_controls({"exposure": ControlSetting(auto=False, value=value)})
            seen, frame = 0, None
            while seen < NUMBER_OF_FRAMES_TO_SETTLE:
                read = self._read_in_start(deadline)
                if read is not None and read.arrival_ns > set_ns:
                    seen, frame = seen + 1, read
            image = frame.payload if frame.format == "BGR" else decode_jpeg(frame.payload)
            error = abs(float(np.mean(image)) - TARGET_BRIGHTNESS) if image is not None else float("inf")
            if best is None or error < best[0]:
                best = (error, value)
        return max(MIN_EXPOSURE, best[1] + RECOMMEND_OFFSET)

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
        self.status.set_state("ready")

    def _attach_rings(self) -> None:
        while not self.shm_sub.empty():
            info = self.shm_sub.get().ring_infos.get(self.camera_id)
            # A message that names the old ring is stale: it came for a change of another camera (ring 7.2).
            if info is not None and info.jpeg_ring_name != self.old_ring_name:
                self.ring_writer = FrameRingWriter.attach(info.jpeg_ring_name)
                if info.bgr_ring_name:
                    self.bgr_ring_writer = FrameRingWriter.attach(info.bgr_ring_name)
                    self.decode_stage = DecodeStage(self.bgr_ring_writer)
                    self.decode_stage.start()
                return

    # ----- each frame (5.1) -----

    def _process(self, frame: CapturedFrame) -> None:
        if self.replaced_base is None:
            self.replaced_base = self.source.replaced_count  # the first frame in the gate (5.2, agent 49)
        self.gate_count += 1
        number = self.gate_count
        should_record, should_finish = self.orchestrator.should_record_frame_number(frame_number=number)
        image = None
        if frame.format == "BGR":
            image = frame.payload
            payload = cv2.imencode(".jpg", image, JPEG_Q90)[1].tobytes()
            delivered_len = len(payload)
        else:
            payload, delivered_len = frame.payload, frame.delivered_len
        payload, flags = check_jpeg(payload, delivered_len=delivered_len, driver_error=frame.driver_error)
        if frame.discontinuity:
            flags |= FrameFlag.DISCONTINUITY  # D34
        if not flags & ERROR_FLAGS:
            self.last_good_payload = payload
        fields = dict(frame_number=self.ring_count, arrival_ns=frame.arrival_ns, sample_ns=frame.sample_ns,
                      source_frame_number=frame.source_frame_number, flags=int(flags),
                      rotation_cw_deg=rotation_to_cw_deg(self.config.rotation))
        if should_record:  # the recorder first, then the ring, with the same bytes (ring 5.3, 5.7)
            self._give(RecorderFrame(payload=payload, frame_number=number, arrival_ns=frame.arrival_ns,
                                     sample_ns=frame.sample_ns, source_frame_number=frame.source_frame_number,
                                     flags=int(flags), delivered_len=delivered_len,
                                     rotation_cw_deg=fields["rotation_cw_deg"]))
        elif should_finish and self.take_writer is not None:
            self._end_take()
        self.ring_count += 1
        try:
            self.ring_writer.write(payload, **fields)
            if self.decode_stage is not None:
                # The one decode is in the decode stage; the recorder needs none (recorder.md 10 item 6, D9).
                item = (DecodeInput(payload=image, source="BGR", **fields) if image is not None
                        else DecodeInput(payload=payload, source="JPEG", **fields))
                self.decode_stage.waiting_place.put(item)
        except Exception as error:  # a failing ring write does not stop capture or recording (ring 5.3)
            logger.exception(f"Frame ring write failed for camera {self.camera_id}: {error}")
        self.status.frame_count.value = number
        self.status.replaced_count.value = self.replaced_total + self.source.replaced_count - self.replaced_base
        self._feed_check(frame)
        self._feed_block(frame)

    def _feed_check(self, frame: CapturedFrame) -> None:
        """The check after a live change (10.2): skip 15 delivered frames, then measure over 60."""
        check = self.check
        if check is None or frame.arrival_ns <= check["after"]:
            return
        if check["first"] is None:
            check["first"] = frame.source_frame_number
        if check["start"] is None:
            if frame.source_frame_number >= check["first"] + rate_check.CHECK_SKIP:
                check["start"] = (frame.source_frame_number, frame.arrival_ns)
                check["deadline"] = rate_check.early_deadline_ns(frame.arrival_ns, self.reference_rate)
            return
        if frame.source_frame_number < check["start"][0] + rate_check.CHECK_FRAMES - 1:
            if frame.arrival_ns > check["deadline"]:
                # 10.2: a later frame came after the deadline, so frame s_a + 59 did not come in time
                self._too_slow(rate_check.measured_rate(*check["start"], frame.source_frame_number, frame.arrival_ns))
            return
        measured = rate_check.measured_rate(*check["start"], frame.source_frame_number, frame.arrival_ns)
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
        while not self.signals.empty():
            _, after_ns, config = self.signals.get_nowait()
            self.config = config
            self.check = dict(after=after_ns, first=None, start=None, deadline=None)
            self.status.set_state("checking")

    def _apply_change(self, requested: CameraConfig) -> None:
        current = self.config
        if needs_reopen(requested, current):
            self._reopen(requested)
            return
        adopted = requested.model_copy(update=dict(framerate=current.framerate, resolution=current.resolution))
        changes = {}
        if requested.exposure_mode == "AUTO" and current.exposure_mode != "AUTO":
            changes["exposure"] = ControlSetting(auto=True, value=None)
        elif requested.exposure_mode == "MANUAL" and (current.exposure_mode, current.exposure) != ("MANUAL", requested.exposure):
            changes["exposure"] = ControlSetting(auto=False, value=requested.exposure)
        if changes:
            self.control.requests.put((adopted, changes))  # live, on the control thread (U16)
            return
        if requested.exposure_mode == "AUTO":
            adopted = adopted.model_copy(update=dict(exposure=current.exposure))
        self.config = adopted
        self._publish_config()

    def _reopen(self, requested: CameraConfig) -> None:
        """A change of resolution or rate reopens only this camera and recreates its rings (D31, ring 7.5)."""
        self._stop_control()
        self._close_rings()
        self._add_replaced()
        self.source.close()
        self.config = requested
        self._start_up()

    # ----- the take (recorder.md section 10) -----

    def _start_take(self, spec) -> None:
        if self.take_writer is not None:
            self._end_take()
        orchestrator = self.orchestrator
        if orchestrator.first_recording_frame_number.value == -1 or orchestrator.last_recording_frame_number.value != -1:
            # The take ended (or its start failed) before this spec came: no writer (ADR-P5VE).
            text = f"camera {self.camera_id}: the take ended before its writer started"
            logger.warning(text)
            self.status.update_info(writer_failure=text)
            return
        try:
            self.take_writer = start_take_writer(self.camera_id, spec, self.status.writer_progress_at)
        except Exception as error:  # the camera runs on; the record start fails with this text (ADR-P5VE)
            text = f"camera {self.camera_id}: the take writer did not start: {error}"
            logger.error(text)
            self.status.update_info(writer_failure=text)
            return
        self.take_failed = False
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
        try:
            if self.orchestrator.last_recording_frame_number.value == -1:
                if self.ipc.should_continue:
                    error = writer.abandon()
                    if error is not None:  # the take level ends the take with this error (recorder.md 5.4)
                        self.ipc.pubsub.topics[TopicTypes.RECORDING_FINISHED].publish(
                            RecordingFinishedMessage(camera_id=self.camera_id, error=error))
                    return
                last = self.orchestrator.last_recording_frame_number
                with last.get_lock():
                    if last.value == -1:
                        # The gate lets another camera be one frame ahead, in hand but not yet counted: + 2.
                        latest = max(self.orchestrator.largest_gate_count(), self.gate_count)
                        last.value = max(latest + 2, self.orchestrator.first_recording_frame_number.value)
            result = writer.end(self.orchestrator.take_frame_count())
            self.ipc.pubsub.topics[TopicTypes.RECORDING_FINISHED].publish(
                RecordingFinishedMessage(camera_id=self.camera_id, result=result))
        finally:
            self.status.recording_in_progress.value = False

    def _missing_until_end(self) -> None:
        """A camera that died during a take: one placeholder row for each new group frame, up to the last
        frame of the take (recorder.md 7.3, section 10 item 7) [M1]. Blocking sleeps of 1 ms (4.3)."""
        number = self.gate_count
        orchestrator = self.orchestrator
        while self.ipc.should_continue and not self.status.should_close.value:
            last = orchestrator.last_recording_frame_number.value
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
                                             reason=report.reason[:2048]))
        if at_end and not self.started:
            self.end_state = "failed"
        else:
            self.status.set_state("dead" if self.started else "failed")
        logger.warning(str(report))

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
                        self.source.close()
                    except CaptureFailure as failure:
                        self._fail(failure)
                        hung = failure.hung
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
            self.decode_stage = None
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

    # ----- publishing -----

    def _publish_config(self, failed_change: str | None = None) -> None:
        self.ipc.pubsub.topics[TopicTypes.EXTRACTED_CONFIG].publish(
            DeviceExtractedConfigMessage(extracted_config=self.config, control_change_failed=failed_change))

    def _publish_controls(self, readback: ControlState) -> None:
        self.status.update_info(controls={name: dict(present=value.present, auto=value.auto, value=value.value)
                                          for name, value in readback.items()})


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
                if request:
                    self._live_change(*request)
                else:
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
        loop.status.set_state("checking")  # before the response, so that a record start sees it (D33)
        loop.signals.put(("check", after_ns, config))
        loop.ipc.pubsub.topics[TopicTypes.EXTRACTED_CONFIG].publish(DeviceExtractedConfigMessage(extracted_config=config))

    def _failed(self, text: str) -> None:
        logger.warning(text)
        self.loop._publish_config(failed_change=text)
