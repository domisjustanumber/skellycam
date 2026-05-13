import logging

import numpy as np

from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.openpnp.openpnp_helpers.openpnp_apply_config import apply_camera_configuration
from openpnp_capture import OpenPnPCamera
from skellycam.core.camera_group.camera_group_ipc import CameraGroupIPC
from skellycam.core.camera_group.camera_status import CameraStatus
from skellycam.core.ipc.pubsub.pubsub_manager import TopicTypes
from skellycam.core.ipc.pubsub.pubsub_topics import DeviceExtractedConfigMessage, UpdateCamerasSettingsMessage

logger = logging.getLogger(__name__)


def check_for_new_config(
    current_config: CameraConfig,
    frame_rec_array: np.recarray,
    camera: OpenPnPCamera,
    ipc: CameraGroupIPC,
    self_status: CameraStatus,
    update_camera_settings_subscription,
) -> tuple[np.recarray, CameraConfig]:
    if not update_camera_settings_subscription.empty():
        logger.debug(f"Camera {current_config.camera_id} received update_camera_settings_subscription message")
        update_message = update_camera_settings_subscription.get()
        if not isinstance(update_message, UpdateCamerasSettingsMessage):
            raise RuntimeError(
                f"Expected UpdateCamerasSettingsMessage for camera {current_config.camera_id}, "
                f"but received {type(update_message)}"
            )
        if current_config.camera_id in update_message.requested_configs:
            self_status.updating.value = True
            new_config = update_message.requested_configs[current_config.camera_id]
            extracted_config = apply_camera_configuration(camera=camera, prior_config=current_config, config=new_config)
            frame_rec_array.frame_metadata.camera_info[0] = extracted_config.to_frame_camera_info()
            ipc.pubsub.topics[TopicTypes.EXTRACTED_CONFIG].publish(
                DeviceExtractedConfigMessage(extracted_config=extracted_config)
            )
            self_status.updating.value = False
            current_config = extracted_config

    return frame_rec_array, current_config
