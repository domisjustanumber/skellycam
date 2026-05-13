import logging

from skellycam.core.camera.config.camera_config import CameraConfig, DEFAULT_FOCUS
from skellycam.core.camera.config.image_resolution import ImageResolution
from skellycam.core.camera.config.image_rotation_types import RotationTypes
from skellycam.core.camera.openpnp.openpnp_helpers.recommend_camera_exposure_setting import ExposureModes
from openpnp_capture import OpenPnPCamera
from skellycam.core.types.type_overloads import CameraIndexInt

logger = logging.getLogger(__name__)


def extract_config_from_openpnp_camera(
    camera_index: CameraIndexInt,
    camera_id: str,
    camera_name: str,
    camera: OpenPnPCamera,
    exposure_mode: str = ExposureModes.MANUAL.name,
    rotation: RotationTypes = RotationTypes.NO_ROTATION,
    *,
    desired_template: CameraConfig | None = None,
) -> CameraConfig:
    fmt = camera.format
    width, height = int(fmt.width), int(fmt.height)
    settings = camera.get_settings()

    exposure_val = settings.exposure
    if exposure_val is None:
        exposure_val = -7

    derived_mode = exposure_mode
    if settings.exposure_auto is True:
        derived_mode = ExposureModes.AUTO.name
    elif settings.exposure_auto is False:
        derived_mode = ExposureModes.MANUAL.name
    native_fps = float(fmt.fps)

    auto_focus_enabled = settings.focus_auto is True
    focus_val = settings.focus
    focus_int = int(focus_val) if focus_val is not None else DEFAULT_FOCUS

    if width == 0 or height == 0:
        logger.error(
            f"Failed to extract configuration from OpenPnPCamera — width: {width}, height: {height}"
        )
        raise ValueError("Invalid camera configuration detected. Please check the camera settings.")

    try:
        cfg = CameraConfig(
            camera_index=camera_index,
            camera_id=camera_id,
            camera_name=camera_name,
            resolution=ImageResolution(width=width, height=height),
            exposure_mode=derived_mode,
            exposure=int(exposure_val),
            framerate=native_fps,
            auto_focus_enabled=auto_focus_enabled,
            focus=focus_int,
            rotation=rotation,
            capture_fourcc=fmt.fourcc_str.strip(),
        )
        if desired_template is not None:
            cfg.writer_fourcc = desired_template.writer_fourcc
            cfg.pixel_format = desired_template.pixel_format
            cfg.color_channels = desired_template.color_channels
            cfg.use_this_camera = desired_template.use_this_camera

        return cfg
    except Exception as e:
        logger.error(f"Failed to extract configuration from OpenPnPCamera — {type(e).__name__}: {e}")
        raise
