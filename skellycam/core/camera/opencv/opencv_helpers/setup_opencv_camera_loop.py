import logging

from skellycam.core.camera_group.camera_setup_failure import CameraSetupFailure, CameraSetupFailedException

import cv2
import numpy as np

from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.opencv.opencv_helpers.create_cv2_video_capture import create_cv2_video_capture
from skellycam.core.camera.opencv.opencv_helpers.create_initial_frame_recarray import create_initial_frame_rec_array
from skellycam.core.camera_group.camera_group_ipc import CameraGroupIPC
from skellycam.core.camera_group.camera_orchestrator import CameraOrchestrator
from skellycam.core.camera_group.camera_status import CameraStatus
from skellycam.core.ipc.pubsub.pubsub_manager import TopicTypes
from skellycam.core.ipc.frame_ring import FrameRingWriter
from skellycam.core.ipc.pubsub.pubsub_topics import DeviceExtractedConfigMessage, SetShmMessage
from skellycam.core.types.type_overloads import TopicSubscriptionQueue
from skellycam.utilities.wait_functions import wait_10ms

logger = logging.getLogger(__name__)


def await_ring_writer(config: CameraConfig,
                      ipc: CameraGroupIPC,
                      self_status: CameraStatus,
                      shm_subscription: TopicSubscriptionQueue,
                      old_ring_name: str | None = None) -> tuple[FrameRingWriter, FrameRingWriter | None]:
    """Wait for the rings of this camera in a `SetShmMessage` and attach as their writer.

    Return the JPEG ring writer, and the BGR ring writer or `None` (spec 7.3 and 8.1).

    A message that still names `old_ring_name` for this camera is stale: the main process sent it
    for a change of another camera. Ring names are never used again (spec 7.2).
    """
    logger.debug(f"Camera {config.camera_id} awaiting its frame ring...")
    while ipc.should_continue and not self_status.should_close.value:
        wait_10ms()
        if not shm_subscription.empty():
            shm_message: SetShmMessage = shm_subscription.get()
            if not isinstance(shm_message, SetShmMessage):
                raise RuntimeError(
                    f"Expected SetShmMessage for camera {config.camera_id}, but received {type(shm_message)}"
                )
            info = shm_message.ring_infos[config.camera_id]
            if info.jpeg_ring_name != old_ring_name:
                logger.debug(f"Camera {config.camera_id} attaching to frame ring {info.jpeg_ring_name}...")
                bgr_writer = FrameRingWriter.attach(info.bgr_ring_name) if info.bgr_ring_name else None
                return FrameRingWriter.attach(info.jpeg_ring_name), bgr_writer
    raise RuntimeError(f"Camera {config.camera_id} closed before it received its frame ring")


def setup_opencv_camera_loop(config: CameraConfig,
                             ipc: CameraGroupIPC,
                             orchestrator: CameraOrchestrator,
                             self_status: CameraStatus,
                             shm_subscription: TopicSubscriptionQueue) -> tuple[
    FrameRingWriter, CameraConfig, cv2.VideoCapture, np.recarray, FrameRingWriter | None]:
    # Create cv2.VideoCapture object
    phase = "opening camera and reading first frame"
    cv2_video_capture = None
    ring_writer = bgr_ring_writer = None
    try:
        cv2_video_capture, config = create_cv2_video_capture(config)

        phase = "joining camera group shared memory"
        ipc.pubsub.topics[TopicTypes.EXTRACTED_CONFIG].publish(DeviceExtractedConfigMessage(extracted_config=config))
        ring_writer, bgr_ring_writer = await_ring_writer(config=config, ipc=ipc, self_status=self_status,
                                                         shm_subscription=shm_subscription)
        if not cv2_video_capture.isOpened():
            raise RuntimeError(f"cv2.VideoCapture for camera {config.camera_id} is not opened")
        self_status.connected.value = True
        logger.success(f"Camera {config.camera_id} ready!")
        while not orchestrator.all_ready and ipc.should_continue and not self_status.should_close.value:
            _, _ = cv2_video_capture.read()  # Clear the buffer
            wait_10ms()
        frame_rec_array = create_initial_frame_rec_array(config=config,
                                                         ipc=ipc)

    except Exception as e:
        logger.exception(f"Failed to create cv2.VideoCapture for camera {config.camera_id}: {e}")
        self_status.signal_error()
        # Stop only this camera group's siblings, not the whole backend.
        failure = CameraSetupFailure(camera_id=config.camera_id, stage=phase, reason=f"{type(e).__name__}: {e}")
        ipc.report_setup_failure(failure)
        # This function owns the capture until it returns successfully.
        if cv2_video_capture is not None:
            cv2_video_capture.release()
        if ring_writer is not None:
            ring_writer.close()
        if bgr_ring_writer is not None:
            bgr_ring_writer.close()
        raise CameraSetupFailedException(str(failure)) from e
    return ring_writer, config, cv2_video_capture, frame_rec_array, bgr_ring_writer
