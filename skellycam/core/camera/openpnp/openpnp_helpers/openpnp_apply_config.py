import logging

from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.openpnp.openpnp_helpers.format_selection import select_best_format
from skellycam.core.camera.openpnp.openpnp_helpers.openpnp_extract_config import extract_config_from_openpnp_camera
from skellycam.core.camera.openpnp.openpnp_helpers.recommend_camera_exposure_setting import (
    ExposureModes,
    get_recommended_openpnp_exposure,
)
from skellycam.core.camera.openpnp_capture import OpenPnPCamera
from skellycam.core.camera.openpnp_capture.types import OpenPnPCaptureAPIError, OpenPnPProperty

logger = logging.getLogger(__name__)


class FailedToApplyCameraConfigurationError(Exception):
    pass


def _apply_focus(camera: OpenPnPCamera, config: CameraConfig, *, initial_config: bool) -> None:
    if not camera.supports_property(OpenPnPProperty.FOCUS):
        config.auto_focus_enabled = False
        return
    if initial_config:
        try:
            camera.set_auto_focus(False)
        except OpenPnPCaptureAPIError:
            logger.debug("Could not disable autofocus on camera open for device %s", camera.device_index)
    try:
        if config.auto_focus_enabled:
            camera.set_auto_focus(True)
            return
        camera.set_auto_focus(False)
        limits = camera.get_property_limits(OpenPnPProperty.FOCUS)
        if config.focus < 0:
            focus_val = limits.default_value
        else:
            focus_val = int(max(limits.min_value, min(config.focus, limits.max_value)))
        camera.set_focus(focus_val)
        config.focus = focus_val
    except OpenPnPCaptureAPIError as e:
        logger.warning("Focus controls not applied for camera %s: %s", config.camera_index, e)


def _apply_exposure(camera: OpenPnPCamera, config: CameraConfig) -> None:
    if config.exposure_mode == ExposureModes.RECOMMEND.name:
        optimized = get_recommended_openpnp_exposure(camera)
        camera.set_auto_exposure(False)
        camera.set_exposure(int(optimized))
        config.exposure = optimized
        config.exposure_mode = ExposureModes.MANUAL.name
    elif config.exposure_mode == ExposureModes.AUTO.name:
        camera.set_auto_exposure(True)
    elif config.exposure_mode == ExposureModes.MANUAL.name:
        camera.set_auto_exposure(False)
        camera.set_exposure(int(config.exposure))


def apply_camera_configuration(
    camera: OpenPnPCamera,
    prior_config: CameraConfig | None,
    config: CameraConfig,
) -> CameraConfig:
    initial_config = prior_config is None

    if initial_config:
        logger.info(f"Applying initial configuration to Camera {config.camera_index}:\n{config}")
    else:
        logger.info(f"Applying configuration to Camera {config.camera_index}:\n{config}")

    should_apply_exposure = (
        initial_config or prior_config.exposure_mode != config.exposure_mode or prior_config.exposure != config.exposure
    )
    should_apply_focus = initial_config or (
        prior_config.auto_focus_enabled != config.auto_focus_enabled or prior_config.focus != config.focus
    )
    should_apply_resolution = initial_config or prior_config.resolution != config.resolution
    should_apply_framerate = False
    should_apply_capture_fourcc = initial_config or prior_config.capture_fourcc != config.capture_fourcc

    try:
        if not camera.is_open():
            raise FailedToApplyCameraConfigurationError(
                f"Failed to apply configuration to Camera {config.camera_index} — stream is not open"
            )

        if should_apply_resolution or should_apply_capture_fourcc:
            chosen = select_best_format(camera.device_formats, config)
            if chosen.format_id != camera.format.format_id:
                logger.info(
                    f"Camera {config.camera_index}: reopening stream for format "
                    f"{chosen.width}x{chosen.height} {chosen.fourcc_str} @ {chosen.fps}fps"
                )
                camera.reopen_stream(chosen.format_id, chosen)

        if should_apply_exposure:
            _apply_exposure(camera, config)

        if should_apply_focus:
            _apply_focus(camera, config, initial_config=initial_config)

        if should_apply_framerate:
            if config.framerate > 0:
                logger.trace("Framerate application is disabled for openpnp-capture paths")

        extracted_config = extract_config_from_openpnp_camera(
            camera_index=config.camera_index,
            camera_id=config.camera_id,
            camera_name=config.camera_name,
            camera=camera,
            exposure_mode=config.exposure_mode,
            rotation=config.rotation,
        )
        if not camera.is_open():
            raise FailedToApplyCameraConfigurationError(
                f"Failed to apply configuration to Camera {config.camera_index} — stream closed unexpectedly"
            )
        logger.trace(f"Camera {config.camera_index} configuration applied, extracted config: {extracted_config}")
        return extracted_config
    except Exception as e:
        logger.exception(f"Problem applying configuration for camera: {config},\n\nReceived error: {e}")
        raise FailedToApplyCameraConfigurationError(
            f"Failed to apply configuration to Camera {config.camera_index} — {type(e).__name__} — {e}"
        )
