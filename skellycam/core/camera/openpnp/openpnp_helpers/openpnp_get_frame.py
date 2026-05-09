"""Grab frames from openpnp-capture into the shared-memory bound recarray.

TODO(openpnp-capture-fork): ``Cap_captureFrame`` returns **decoded RGB** copied on our thread; decode
happens inside openpnp's worker. We intentionally mirror ``pre_frame_grab_ns`` /
``post_frame_grab_ns`` into ``pre_frame_retrieve_ns`` / ``post_frame_retrieve_ns`` so downstream
dtypes stay compatible — see plan note *NOTE-FOR-FUTURE-FORK* if you need true grab/retrieve split.
"""

import logging
import time

import cv2
import numpy as np

from skellycam.core.camera.openpnp_capture import OpenPnPCamera

logger = logging.getLogger(__name__)


def openpnp_get_frame(camera: OpenPnPCamera, frame_rec_array: np.recarray) -> tuple[bool, np.recarray]:
    """
    Copy the latest camera frame into ``frame_rec_array.image[0]``.

    Timestamp semantics: one blocking ``capture_frame_into`` brackets both grab and retrieve fields
    (RGB→BGR swap happens inside ``OpenPnPCamera.capture_frame_into``).
    """
    frame_rec_array.frame_metadata.timestamps.pre_frame_grab_ns[0] = time.perf_counter_ns()
    frame_rec_array.frame_metadata.timestamps.pre_frame_retrieve_ns[0] = (
        frame_rec_array.frame_metadata.timestamps.pre_frame_grab_ns[0]
    )

    ok = camera.capture_frame_into(frame_rec_array.image[0])

    frame_rec_array.frame_metadata.timestamps.post_frame_grab_ns[0] = time.perf_counter_ns()
    frame_rec_array.frame_metadata.timestamps.post_frame_retrieve_ns[0] = (
        frame_rec_array.frame_metadata.timestamps.post_frame_grab_ns[0]
    )

    if not ok:
        logger.debug(
            "Cap_captureFrame did not succeed for camera %s",
            frame_rec_array.frame_metadata.camera_info.camera_id[0],
        )
        return False, frame_rec_array

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

    return True, frame_rec_array


def draw_doubled_text(image, text, x, y, font_scale=0.8, color=(255, 210, 210), thickness=2):
    cv2.putText(image, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 0), thickness * 4)
    cv2.putText(image, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness)
