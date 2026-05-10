import logging
import time
from collections import deque

import numpy as np

from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.fps_compatibility import logical_capture_stride_from_camera_config
from skellycam.core.camera.openpnp.openpnp_helpers.camera_loop_update_checks import camera_loop_update_checks
from skellycam.core.camera.openpnp.openpnp_helpers.create_openpnp_camera import create_openpnp_camera
from skellycam.core.camera.openpnp.openpnp_helpers.handle_recording_updates import finish_recording
from skellycam.core.camera.openpnp.openpnp_helpers.handle_video_recording_loop import handle_video_recording
from skellycam.core.camera.openpnp.openpnp_helpers.openpnp_get_frame import draw_doubled_text, openpnp_get_frame
from skellycam.core.camera.openpnp_capture import OpenPnPCamera
from skellycam.core.camera_group.camera_group_ipc import CameraGroupIPC
from skellycam.core.camera_group.camera_orchestrator import CameraOrchestrator
from skellycam.core.camera_group.camera_status import CameraStatus
from skellycam.core.ipc.shared_memory.camera_shared_memory_ring_buffer import CameraSharedMemoryRingBuffer
from skellycam.core.recorders.videos.video_recorder import VideoRecorder
from skellycam.core.types.type_overloads import TopicSubscriptionQueue
from skellycam.utilities.wait_functions import wait_1ms, wait_10us

logger = logging.getLogger(__name__)

MAX_FAIL_COUNT = 30


def run_openpnp_camera_loop(
    camera_shm: CameraSharedMemoryRingBuffer,
    config: CameraConfig,
    camera: OpenPnPCamera,
    frame_rec_array: np.recarray,
    ipc: CameraGroupIPC,
    orchestrator: CameraOrchestrator,
    self_status: CameraStatus,
    update_camera_settings_subscription: TopicSubscriptionQueue,
    recording_info_subscription: TopicSubscriptionQueue,
):
    video_recorder: VideoRecorder | None = None
    previous_tik = time.perf_counter_ns()

    number_of_frames_outside_acceptable_range = 0
    fail_count = 0
    frame_durations_seconds = deque(maxlen=1000)
    framerate: float | None = None

    # Diagnostics: detect "stream open but no frames" stalls (e.g. USB / Media Foundation contention)
    # without spamming logs every iteration.
    stall_log_interval_ns = 5 * 1_000_000_000
    last_stall_log_ns = 0
    last_frame_log_ns = 0
    last_stride_key: tuple[float, float, int] | None = None
    captures_seen_under_stride_key = 0

    try:
        while ipc.should_continue:
            (
                config,
                frame_rec_array,
                video_recorder,
                self_status,
            ) = camera_loop_update_checks(
                config=config,
                camera=camera,
                frame_rec_array=frame_rec_array,
                ipc=ipc,
                orchestrator=orchestrator,
                recording_info_subscription=recording_info_subscription,
                self_status=self_status,
                update_camera_settings_subscription=update_camera_settings_subscription,
                video_recorder=video_recorder,
                framerate=framerate,
            )

            stream_native = getattr(config, "stream_framerate", None)
            native_for_stride = float(stream_native) if stream_native is not None and float(stream_native) > 0 else float(
                camera.format.fps
            )
            logical_for_stride = float(config.framerate) if config.framerate and float(config.framerate) > 0 else -1.0
            stride_now = logical_capture_stride_from_camera_config(
                logical_output_fps=logical_for_stride,
                capture_native_fps=native_for_stride,
            )

            stride_key = (logical_for_stride, native_for_stride, stride_now)
            if last_stride_key != stride_key:
                last_stride_key = stride_key
                captures_seen_under_stride_key = 0

            if self_status.should_close.value:
                logger.info(f"Camera {config.camera_id} received shutdown signal.")
                break
            if self_status.is_paused.value:
                wait_1ms()
                continue

            if not orchestrator.should_grab_by_id(camera_id=config.camera_id):
                now_ns = time.perf_counter_ns()
                if now_ns - last_stall_log_ns >= stall_log_interval_ns:
                    last_stall_log_ns = now_ns
                    logger.debug(
                        "Camera %s waiting on orchestrator gate (all_ready=%s, frame_counts=%s)",
                        config.camera_id,
                        orchestrator.all_ready,
                        orchestrator.camera_frame_counts,
                    )
                wait_10us()
                continue
            self_status.grabbing_frame.value = True
            frame_success = False
            wait_started_ns = time.perf_counter_ns()
            while not frame_success and ipc.should_continue and fail_count < MAX_FAIL_COUNT:
                # OpenPnP signals "no frame yet" via Cap_hasNewFrame; polling faster than FPS is normal.
                if not camera.has_new_frame():
                    elapsed_ns = time.perf_counter_ns() - wait_started_ns
                    if elapsed_ns > stall_log_interval_ns and (
                        time.perf_counter_ns() - last_stall_log_ns >= stall_log_interval_ns
                    ):
                        last_stall_log_ns = time.perf_counter_ns()
                        logger.warning(
                            "Camera %s: no new frame from device for %.1fs (stream is_open=%s, "
                            "fail_count=%s, frame_count=%s). Camera may be stalled — possible USB "
                            "bandwidth contention or driver issue.",
                            config.camera_id,
                            elapsed_ns / 1e9,
                            camera.is_open(),
                            fail_count,
                            self_status.frame_count.value,
                        )
                    wait_1ms()
                    continue
                frame_success, frame_rec_array = openpnp_get_frame(
                    camera=camera,
                    frame_rec_array=frame_rec_array,
                    advance_logical_delivery=False,
                )
                if not frame_success:
                    fail_count += 1
                    if not camera.is_open():
                        raise RuntimeError(
                            f"Camera {config.camera_id} shutdown unexpectedly - exiting camera loop."
                        )
                    logger.warning(
                        "Capture retry %s/%s for camera %s",
                        fail_count,
                        MAX_FAIL_COUNT,
                        config.camera_id,
                    )

            if not frame_success:
                raise RuntimeError(
                    f"Could not capture a frame from camera {config.camera_id} after {MAX_FAIL_COUNT} failed attempts."
                )

            captures_seen_under_stride_key += 1
            logical_deliver = (captures_seen_under_stride_key - 1) % stride_now == 0

            if not logical_deliver:
                self_status.grabbing_frame.value = False
                frame_rec_array = initialize_frame_recarray(frame_rec_array=frame_rec_array)
                continue

            frame_rec_array.frame_metadata.frame_number[0] += 1
            frame_stamp = (
                f"camera.id{frame_rec_array.frame_metadata.camera_info.camera_id[0]}."
                f"idx{frame_rec_array.frame_metadata.camera_info.camera_index[0]}."
                f"fr{frame_rec_array.frame_metadata.frame_number[0]}"
            )
            draw_doubled_text(
                image=frame_rec_array.image[0],
                text=frame_stamp,
                x=10,
                y=40,
            )

            current_tik = time.perf_counter_ns()
            frame_durations_seconds.append((current_tik - previous_tik) / 1e9)
            previous_tik = current_tik
            if len(frame_durations_seconds) >= 30:
                framerate = 1.0 / np.median(np.array(frame_durations_seconds))

            now_ns = time.perf_counter_ns()
            current_frame_number = int(frame_rec_array.frame_metadata.frame_number[0])
            if current_frame_number == 1 or (
                now_ns - last_frame_log_ns >= stall_log_interval_ns
            ):
                last_frame_log_ns = now_ns
                logger.debug(
                    "Camera %s captured frame %s (running framerate=%.1f fps)",
                    config.camera_id,
                    current_frame_number,
                    framerate or 0.0,
                )

            fail_count = 0
            (
                should_record_frame,
                should_finish_recording,
            ) = orchestrator.should_record_frame_number(frame_number=frame_rec_array.frame_metadata.frame_number[0])

            self_status.grabbing_frame.value = False

            frame_rec_array.frame_metadata.timestamps.pre_copy_to_camera_shm_ns[0] = time.perf_counter_ns()
            camera_shm.put_frame(frame_rec_array=frame_rec_array, overwrite=True)
            frame_rec_array.frame_metadata.timestamps.post_copy_to_camera_shm_ns[0] = time.perf_counter_ns()

            video_recorder = handle_video_recording(
                config=config,
                frame_rec_array=frame_rec_array,
                ipc=ipc,
                self_status=self_status,
                should_finish_recording=should_finish_recording,
                should_record_frame=should_record_frame,
                video_recorder=video_recorder,
            )
            (
                config,
                camera,
                number_of_frames_outside_acceptable_range,
            ) = check_framerate_reset(
                config=config,
                camera=camera,
                frame_rec_array=frame_rec_array,
                number_of_frames_outside_acceptable_range=number_of_frames_outside_acceptable_range,
                previous_tik=previous_tik,
            )
            frame_rec_array = initialize_frame_recarray(frame_rec_array=frame_rec_array)

            self_status.frame_count.value = frame_rec_array.frame_metadata.frame_number[0]
            previous_tik = time.perf_counter_ns()

    except Exception as e:
        self_status.signal_error()
        logger.exception(f"Exception occurred in camera loop for Camera: {config.camera_id} - {e}")
        ipc.kill_everything()
        raise
    finally:
        if video_recorder:
            finish_recording(ipc=ipc, video_recorder=video_recorder)
            logger.warning(f"Camera {config.camera_id} closed mid-recording!")
        self_status.connected.value = False
        self_status.closed.value = True
        logger.debug(f"Camera {config.camera_id} loop ended.")


def initialize_frame_recarray(frame_rec_array: np.recarray) -> np.recarray:
    """Initialize timestamps for a new frame"""
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


def check_framerate_reset(
    config: CameraConfig,
    camera: OpenPnPCamera,
    frame_rec_array: np.recarray,
    number_of_frames_outside_acceptable_range: int,
    previous_tik: int,
) -> tuple[CameraConfig, OpenPnPCamera, int]:
    lf = float(config.framerate) if config.framerate and float(config.framerate) > 0 else 30.0
    target_frame_duration_ms = (lf**-1) * 1e3
    max_acceptable_frame_duration_ms = target_frame_duration_ms * 2
    if frame_rec_array.frame_metadata.frame_number[0] > 100:
        frame_duration_ms = (time.perf_counter_ns() - previous_tik) / 1e6
        if frame_duration_ms > max_acceptable_frame_duration_ms:
            number_of_frames_outside_acceptable_range += 1
        else:
            number_of_frames_outside_acceptable_range = 0
        if number_of_frames_outside_acceptable_range > 30:
            logger.warning(
                f"Camera {config.camera_id} has had {number_of_frames_outside_acceptable_range} consecutive frames "
                f"that were longer than acceptable duration ({max_acceptable_frame_duration_ms:.2f}ms) — resetting camera."
            )
            camera.close()
            camera, config = create_openpnp_camera(config)
            number_of_frames_outside_acceptable_range = 0
    return config, camera, number_of_frames_outside_acceptable_range
