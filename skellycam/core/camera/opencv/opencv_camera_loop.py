import logging
import time
from collections import deque

import cv2
import numpy as np

from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.opencv.opencv_helpers.camera_loop_update_checks import camera_loop_update_checks
from skellycam.core.camera.opencv.opencv_helpers.create_cv2_video_capture import create_cv2_video_capture
from skellycam.core.camera.opencv.opencv_helpers.handle_recording_updates import finish_recording
from skellycam.core.camera.opencv.opencv_helpers.handle_video_recording_loop import handle_video_recording
from skellycam.core.camera.opencv.opencv_helpers.opencv_get_frame import opencv_get_frame
from skellycam.core.camera.opencv.opencv_helpers.setup_opencv_camera_loop import await_ring_writer
from skellycam.core.camera_group.camera_group_ipc import CameraGroupIPC
from skellycam.core.camera_group.camera_orchestrator import CameraOrchestrator
from skellycam.core.camera_group.camera_status import CameraStatus
from skellycam.core.ipc.frame_ring import (
    NO_SAMPLE_NS,
    DecodeInput,
    DecodeStage,
    FrameRingWriter,
    check_jpeg,
    rotation_to_cw_deg,
)
from skellycam.core.types.type_overloads import TopicSubscriptionQueue
from skellycam.utilities.wait_functions import wait_1ms, wait_10us
from skellycam.core.recorders.videos.video_recorder import VideoRecorder  # noqa: TC001 — beartype checks annotations at runtime

logger = logging.getLogger(__name__) 

MAX_FAIL_COUNT = 30
JPEG_ENCODE_PARAMETERS = [int(cv2.IMWRITE_JPEG_QUALITY), 90]  # spec 2.3 [A3]; OpenCV default chroma 4:2:0

def run_opencv_camera_loop(ring_writer: FrameRingWriter,
                           config: CameraConfig,
                           cv2_video_capture: cv2.VideoCapture,
                           frame_rec_array: np.recarray,
                           ipc: CameraGroupIPC,
                           orchestrator: CameraOrchestrator,
                           self_status: CameraStatus,
                           update_camera_settings_subscription: TopicSubscriptionQueue,
                           recording_info_subscription: TopicSubscriptionQueue,
                           shm_subscription: TopicSubscriptionQueue | None = None,
                           bgr_ring_writer: FrameRingWriter | None = None):
    video_recorder: VideoRecorder | None = None
    decode_stage = _start_decode_stage(bgr_ring_writer)
    previous_tik = time.perf_counter_ns()

    number_of_frames_outside_acceptable_range = 0
    fail_count = 0
    frame_durations_seconds= deque(maxlen=1000)
    framerate: float | None = None #median framerate of the past 1000
    ring_frame_offset = 0  # frame numbers start at 0 in each new ring (spec 7.5) [A17]
    try:
        while ipc.should_continue:
            ring_mode = (config.resolution, config.framerate, config.bgr_ring)
            (config,
             frame_rec_array,
             video_recorder,
             self_status,
             ) = camera_loop_update_checks(config=config,
                                           cv2_video_capture=cv2_video_capture,
                                           frame_rec_array=frame_rec_array,
                                           ipc=ipc,
                                           orchestrator=orchestrator,
                                           recording_info_subscription=recording_info_subscription,
                                           self_status=self_status,
                                           update_camera_settings_subscription=update_camera_settings_subscription,
                                           video_recorder=video_recorder,
                                           framerate=framerate
                                           )
            if (config.resolution, config.framerate, config.bgr_ring) != ring_mode:
                # The main process recreates the rings of this camera under new names (spec 7.5).
                if shm_subscription is None:
                    raise RuntimeError(f"Camera {config.camera_id} changed its mode, but has no shm subscription")
                old_ring_name = ring_writer.name
                ring_writer.close()
                if decode_stage is not None:
                    decode_stage.stop()
                    bgr_ring_writer.close()
                    decode_stage = None
                ring_writer, bgr_ring_writer = await_ring_writer(config=config, ipc=ipc, self_status=self_status,
                                                                 shm_subscription=shm_subscription,
                                                                 old_ring_name=old_ring_name)
                decode_stage = _start_decode_stage(bgr_ring_writer)
                ring_frame_offset = int(frame_rec_array.frame_metadata.frame_number[0]) + 1

            if self_status.should_close.value:
                logger.info(f"Camera {config.camera_id} received shutdown signal.")
                break
            if self_status.is_paused.value:
                wait_1ms()
                continue

            if not orchestrator.should_grab_by_id(camera_id=config.camera_id):
                wait_10us()
                continue
            self_status.grabbing_frame.value = True
            frame_success = False
            while not frame_success and ipc.should_continue and fail_count < MAX_FAIL_COUNT:
                fail_count += 1
                frame_success, frame_rec_array = opencv_get_frame(cap=cv2_video_capture,
                                                                  frame_rec_array=frame_rec_array, )
                if not frame_success:
                    logger.error(f"Failed to grab frame from camera {config.camera_id}. Retrying...")
                    if not cv2_video_capture.isOpened():
                        raise RuntimeError(f"Camera {config.camera_id} shutdown unexpectedly - exiting camera loop.")
                current_tik = time.perf_counter_ns()
                frame_durations_seconds.append((current_tik - previous_tik) / 1e9)
                previous_tik = current_tik
                if len(frame_durations_seconds) >= 30:
                    framerate = 1.0 / np.median(np.array(frame_durations_seconds))

            if not ipc.should_continue:
                break
            if not frame_success:
                raise RuntimeError(
                    f"Camera {config.camera_id} failed to capture a frame "
                    f"after {MAX_FAIL_COUNT} attempts."
                )
            fail_count = 0
            # NOTE - Get `should_record` flags BEFORE unsetting 'grabbing_frame' to avoid
            # potential race-condition-generating flag setting gaps between cameras
            (should_record_frame,
             should_finish_recording) = orchestrator.should_record_frame_number(
                frame_number=frame_rec_array.frame_metadata.frame_number[0], )

            self_status.grabbing_frame.value = False

            # The "copy to camera shm" times now span the JPEG encode and the capture check (spec 2.3).
            frame_rec_array.frame_metadata.timestamps.pre_copy_to_camera_shm_ns[0] = time.perf_counter_ns()
            payload = cv2.imencode(".jpg", frame_rec_array.image[0], JPEG_ENCODE_PARAMETERS)[1].tobytes()
            payload, flags = check_jpeg(payload, delivered_len=len(payload), driver_error=False)
            frame_rec_array.frame_metadata.timestamps.post_copy_to_camera_shm_ns[0] = time.perf_counter_ns()

            # Recorder first, then the ring write (spec 5.3) [A6].
            video_recorder = handle_video_recording(config=config,
                                                    frame_rec_array=frame_rec_array,
                                                    ipc=ipc,
                                                    self_status=self_status,
                                                    should_finish_recording=should_finish_recording,
                                                    should_record_frame=should_record_frame,
                                                    video_recorder=video_recorder)
            try:
                frame = dict(frame_number=int(frame_rec_array.frame_metadata.frame_number[0]) - ring_frame_offset,
                             arrival_ns=int(frame_rec_array.frame_metadata.timestamps.post_frame_grab_ns[0]),
                             sample_ns=NO_SAMPLE_NS,
                             source_frame_number=-1,
                             flags=flags,
                             rotation_cw_deg=rotation_to_cw_deg(config.rotation))
                ring_writer.write(payload, **frame)
                if decode_stage is not None:
                    # Spec 8.8: OpenCV gives BGR, so the waiting place gets a new copy of it, not the JPEG.
                    decode_stage.waiting_place.put(DecodeInput(payload=frame_rec_array.image[0].copy(),
                                                               source="BGR", **frame))
            except Exception as e:  # a failing ring write must not stop capture or recording
                logger.exception(f"Frame ring write failed for camera {config.camera_id}: {e}")
            (config,
             cv2_video_capture,
             number_of_frames_outside_acceptable_range) = check_framerate_reset(config=config,
                                                                                cv2_video_capture=cv2_video_capture,
                                                                                frame_rec_array=frame_rec_array,
                                                                                number_of_frames_outside_acceptable_range=number_of_frames_outside_acceptable_range,
                                                                                previous_tik=previous_tik)
            frame_rec_array = initialize_frame_recarray(frame_rec_array=frame_rec_array)

            # Last camera to increment their frame count status triggers the next frame_grab
            self_status.frame_count.value = frame_rec_array.frame_metadata.frame_number[0]
            previous_tik = time.perf_counter_ns()

    except Exception as e:
        self_status.signal_error()
        logger.exception(f"Exception occurred in camera loop for Camera: {config.camera_id} - {e}")
        ipc.should_continue = False
        raise
    finally:
        self_status.grabbing_frame.value = False
        try:
            if video_recorder:
                finish_recording(ipc=ipc, video_recorder=video_recorder)
                logger.warning(f"Camera {config.camera_id} closed mid-recording!"   )
        finally:
            self_status.connected.value = False
            self_status.closed.value = True
            ring_writer.close()
            if decode_stage is not None:
                decode_stage.stop()
                bgr_ring_writer.close()
        logger.debug(f"Camera {config.camera_id} loop ended.")


def _start_decode_stage(bgr_ring_writer: FrameRingWriter | None) -> DecodeStage | None:
    """The decode stage of the BGR ring (spec 8.2), or `None` when the camera has no BGR ring."""
    if bgr_ring_writer is None:
        return None
    decode_stage = DecodeStage(bgr_ring_writer)
    decode_stage.start()
    return decode_stage


def initialize_frame_recarray(frame_rec_array: np.recarray) -> np.recarray:
    """Initialize timestamps for a new frame"""
    # Reset all timestamps to 0
    frame_rec_array.frame_metadata.timestamps.pre_frame_grab_ns[0] = 0
    frame_rec_array.frame_metadata.timestamps.post_frame_grab_ns[0] = 0
    frame_rec_array.frame_metadata.timestamps.pre_frame_retrieve_ns[0] = 0
    frame_rec_array.frame_metadata.timestamps.post_frame_retrieve_ns[0] = 0
    frame_rec_array.frame_metadata.timestamps.pre_frame_record_ns[0] = 0
    frame_rec_array.frame_metadata.timestamps.post_frame_record_ns[0] = 0
    frame_rec_array.frame_metadata.timestamps.pre_copy_to_camera_shm_ns[0] = 0
    frame_rec_array.frame_metadata.timestamps.post_copy_to_camera_shm_ns[0] = 0

    frame_rec_array.frame_metadata.timestamps.initialized_ns[0] = time.perf_counter_ns()

    return frame_rec_array


def check_framerate_reset(config: CameraConfig,
                          cv2_video_capture: cv2.VideoCapture,
                          frame_rec_array: np.recarray,
                          number_of_frames_outside_acceptable_range: int,
                          previous_tik: int) -> tuple[CameraConfig, cv2.VideoCapture, int]:
    #TODO - FIGURE OUT A BETTER WAY TO GET TARGET FPS
    target_frame_duration_ms = (30 ** -1) * 1e3  # Convert framerate to nanoseconds per frame
    max_acceptable_frame_duration_ms = target_frame_duration_ms * 2
    if frame_rec_array.frame_metadata.frame_number[0] > 100:
        frame_duration_ms = (time.perf_counter_ns() - previous_tik) / 1e6  # Convert to milliseconds
        if frame_duration_ms > max_acceptable_frame_duration_ms:
            number_of_frames_outside_acceptable_range += 1
        else:
            number_of_frames_outside_acceptable_range = 0
        if number_of_frames_outside_acceptable_range > 30:
            logger.warning(
                f"Camera {config.camera_id} has had {number_of_frames_outside_acceptable_range} consecutive frames that were longer than acceptable duration ({max_acceptable_frame_duration_ms:.2f}ms) - I'm not sure why this happens, but resetting camera will help, so let's do that. ")
            cv2_video_capture.release()
            cv2_video_capture, config = create_cv2_video_capture(config)
            number_of_frames_outside_acceptable_range = 0
    return config, cv2_video_capture, number_of_frames_outside_acceptable_range
