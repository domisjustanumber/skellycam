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
from skellycam.core.camera.opencv.opencv_helpers.create_initial_frame_recarray import create_initial_frame_rec_array
from skellycam.core.camera.opencv.opencv_helpers.handle_recording_updates import (
    check_for_new_recording_info,
    finish_recording,
)
from skellycam.core.camera.opencv.opencv_helpers.handle_video_recording_loop import handle_video_recording
from skellycam.core.camera.opencv.opencv_helpers.recommend_camera_exposure_setting import (
    MAX_EXPOSURE,
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
from skellycam.core.ipc.pubsub.pubsub_topics import DeviceExtractedConfigMessage
from skellycam.core.types.type_overloads import TopicSubscriptionQueue

logger = logging.getLogger(__name__)

perf_counter_ns = time.perf_counter_ns

STALL_NS = 2_000_000_000  # 9.5, D38
READY_LIMIT_NS = 15_000_000_000  # 9.3, D21
HANG_FINISH_S = 5.0  # interim (U12): removed in phase 5
CONTROL_READ_INTERVAL_S = 1.0  # 11.4, U16
JPEG_Q90 = [int(cv2.IMWRITE_JPEG_QUALITY), 90]  # ring 2.3, 8.8


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
        self.frame_rec_array = create_initial_frame_rec_array(config=config, ipc=ipc)
        self.ring_writer: FrameRingWriter | None = None
        self.bgr_ring_writer: FrameRingWriter | None = None
        self.decode_stage: DecodeStage | None = None
        self.old_ring_name: str | None = None
        self.ring_count = 0
        self.reference_rate = 0.0
        self.last_arrival = 0
        self.last_number = -1
        self.stage = "open"
        self.started = False
        self.recorder = None
        self.flagged = 0
        self.check: dict | None = None  # the check after a live change (10.2)
        self.block: tuple[int, int] | None = None  # the block of a recording (10.3)
        self.slow = False
        self.replaced_base: int | None = None
        self.replaced_total = 0
        self.control: _ControlThread | None = None
        self.signals = queue.Queue()
        self.hung = threading.Event()
        self.files_done = threading.Event()
        self._failure_lock = threading.Lock()
        self._hard_end_lock = threading.Lock()
        self.failed = False
        self.end_state: str | None = None  # the state that the end sets after the close
        self.initialized_ns = perf_counter_ns()

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
            self._end(hung)

    def _pass(self) -> None:
        if self.hung.is_set():
            raise _Hung()
        self._check_updates()
        if self.status.state == "waiting":
            self._wait_pass()
            return
        if self.status.should_pause.value:
            self.status.is_paused.value = True
            time.sleep(0.05)  # T-CAP-49: a paused camera process uses under 2 % of one core
            return
        self.status.is_paused.value = False
        if not self.orchestrator.should_grab_by_id(camera_id=self.camera_id):
            time.sleep(0.001)  # no spin at the gate (4.3)
            return
        frame = self._read()
        if frame is not None:
            self._process(frame)

    def _read(self, deadline_ns: int | None = None) -> CapturedFrame | None:
        """`read_frame` with the stall watch (9.5): it waits at most until 2 s after the last arrival."""
        wake = self.last_arrival + STALL_NS
        for limit in (deadline_ns, self.check and self.check["deadline"]):
            if limit:
                wake = min(wake, limit)
        frame = self.source.read_frame(max(wake - perf_counter_ns(), 0) / 1e9)
        if frame is None:
            if perf_counter_ns() - self.last_arrival >= STALL_NS:
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
        number = int(self.frame_rec_array.frame_metadata.frame_number[0])
        self.frame_rec_array = create_initial_frame_rec_array(config=self.config, ipc=self.ipc)
        self.frame_rec_array.frame_metadata.frame_number[0] = number  # the gate count continues (5.3)
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
        """RECOMMEND (11.1): -12 to -4, 10 frames to settle, the mean of the image nearest to 127.5."""
        best = None
        for value in range(MIN_EXPOSURE, MAX_EXPOSURE + 1):
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
        return best[1]

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
        self.frame_rec_array.frame_metadata.frame_number[0] = count
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
        rec = self.frame_rec_array
        meta, stamps = rec.frame_metadata, rec.frame_metadata.timestamps
        if self.replaced_base is None:
            self.replaced_base = self.source.replaced_count  # the first frame in the gate (5.2, agent 49)
        meta.frame_number[0] += 1
        number = int(meta.frame_number[0])
        should_record, should_finish = self.orchestrator.should_record_frame_number(frame_number=number)
        stamps.initialized_ns[0] = self.initialized_ns
        stamps.pre_frame_grab_ns[0] = stamps.post_frame_grab_ns[0] = frame.arrival_ns  # 5.4, agent 7
        stamps.pre_frame_retrieve_ns[0], stamps.post_frame_retrieve_ns[0] = (
            getattr(self.source, "retrieve_ns", None) or (0, 0))  # only OpenCV stamps the retrieve (5.4)
        stamps.pre_copy_to_camera_shm_ns[0] = perf_counter_ns()
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
        stamps.post_copy_to_camera_shm_ns[0] = perf_counter_ns()
        if image is None and not flags & ERROR_FLAGS and (should_record or self.decode_stage is not None):
            image = decode_jpeg(payload)  # interim decode for the old recorder (5.5, D9): one decode
        good = image is not None and image.shape == rec.image[0].shape
        if good:
            rec.image[0] = image
        elif should_record:
            self.flagged += 1  # interim (U5): removed in phase 5; the recorder gets the last good image again
        recorder = self.recorder
        self.recorder = handle_video_recording(config=self.config, frame_rec_array=rec, ipc=self.ipc,
                                               self_status=self.status, should_finish_recording=should_finish,
                                               should_record_frame=should_record, video_recorder=self.recorder)
        if recorder is not None and self.recorder is None:
            self._log_flagged()
        fields = dict(frame_number=self.ring_count, arrival_ns=frame.arrival_ns, sample_ns=frame.sample_ns,
                      source_frame_number=frame.source_frame_number, flags=int(flags),
                      rotation_cw_deg=rotation_to_cw_deg(self.config.rotation))
        self.ring_count += 1
        try:
            self.ring_writer.write(payload, **fields)
            if self.decode_stage is not None:
                item = (DecodeInput(payload=image, source="BGR", **fields) if good
                        else DecodeInput(payload=payload, source="JPEG", **fields))
                self.decode_stage.waiting_place.put(item)
        except Exception as error:  # a failing ring write does not stop capture or recording (ring 5.3)
            logger.exception(f"Frame ring write failed for camera {self.camera_id}: {error}")
        self.status.frame_count.value = number
        self.status.replaced_count.value = self.replaced_total + self.source.replaced_count - self.replaced_base
        self._feed_check(frame)
        self._feed_block(frame)
        self.initialized_ns = perf_counter_ns()

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
        if self.recorder is None:
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
        recorder = self.recorder
        self.recorder = check_for_new_recording_info(
            config=self.config, ipc=self.ipc, orchestrator=self.orchestrator,
            recording_info_subscription=self.recording_sub, self_status=self.status, video_recorder=self.recorder,
            framerate=self.reference_rate)  # agent 9: the mode rate, not the median of the intervals
        if self.recorder is not recorder:
            self.flagged = 0
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

    def _log_flagged(self) -> None:
        logger.info(f"Camera {self.camera_id}: {self.flagged} flagged frames gave the last good image to the "
                    f"recorder")  # interim (U5): removed in phase 5

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

    def _finish_files(self) -> None:
        """Finish the files of a recording: a dead camera (D38), or a hang for at most 5 s (U12)."""
        try:
            if self.recorder is not None:
                if self.recorder.any_data_saved:
                    finish_recording(ipc=self.ipc, video_recorder=self.recorder)
                    self._log_flagged()
                else:
                    self.recorder.close()
                self.recorder = None
            self.status.recording_in_progress.value = False
        finally:
            self.files_done.set()

    def hard_end(self) -> None:
        """6.6: after a hang, end the camera process with no clean-up. THREAD workers only end the thread."""
        if parent_process() is None:
            return
        # One thread only: a second `join_thread` returns at once, and its os._exit would cut the first one short.
        self._hard_end_lock.acquire()
        deadline = time.monotonic() + HANG_FINISH_S  # interim (U12): removed in phase 5
        self.files_done.wait(HANG_FINISH_S)
        # The feeder thread of the queue writes the files message; os._exit would drop it (U12).
        for queue_ in self.ipc.pubsub.topics[TopicTypes.RECORDING_FINISHED].subscriptions:
            queue_.close()
            flush = threading.Thread(target=queue_.join_thread, daemon=True)
            flush.start()
            flush.join(max(deadline - time.monotonic(), 0))
        os._exit(1)

    def _end(self, hung: bool) -> None:
        try:
            self._finish_files()  # D38: the files first (8.2); after a hang, at most 5 s (U12)
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
