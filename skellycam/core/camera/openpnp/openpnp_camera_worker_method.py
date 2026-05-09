import logging

from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.openpnp.openpnp_camera_loop import run_openpnp_camera_loop
from skellycam.core.camera.openpnp.openpnp_helpers.setup_openpnp_camera_loop import setup_openpnp_camera_loop
from skellycam.core.camera_group.camera_group_ipc import CameraGroupIPC
from skellycam.core.camera_group.camera_orchestrator import CameraOrchestrator
from skellycam.core.camera_group.camera_status import CameraStatus
from skellycam.core.camera_group.usb_bandwidth import CameraStartupAborted, UsbBandwidthContentionError
from skellycam.core.ipc.shared_memory.camera_shared_memory_ring_buffer import CameraSharedMemoryRingBuffer
from skellycam.core.types.type_overloads import CameraIdString, TopicSubscriptionQueue

logger = logging.getLogger(__name__)


def openpnp_camera_worker_method(
    camera_id: CameraIdString,
    config: CameraConfig,
    ipc: CameraGroupIPC,
    orchestrator: CameraOrchestrator,
    update_camera_settings_subscription: TopicSubscriptionQueue,
    shm_subscription: TopicSubscriptionQueue,
    recording_info_subscription: TopicSubscriptionQueue,
) -> None:

    logger.trace(f"Camera {camera_id} worker started")
    self_status: CameraStatus = orchestrator.camera_statuses[camera_id]
    camera_shm: CameraSharedMemoryRingBuffer | None = None
    camera = None
    frame_rec_array = None

    # Expected startup-failure paths (USB bandwidth contention on this device, or peer
    # worker failed and signaled coordinated shutdown) are swallowed here so the worker
    # exits with code 0. The main process already learns about the failure via shared
    # ``CameraStatus`` / ``global_kill_flag``; surfacing a tracebacks via
    # ``_process_entry_point``'s "Unhandled exception" path adds no diagnostic value
    # and floods the log + UI with stack dumps for a known-good error path.
    try:
        (camera_shm, config, camera, frame_rec_array) = setup_openpnp_camera_loop(
            camera_shm=camera_shm,
            config=config,
            ipc=ipc,
            orchestrator=orchestrator,
            self_status=self_status,
            shm_subscription=shm_subscription,
        )
    except UsbBandwidthContentionError:
        logger.warning(f"Camera {camera_id} worker exiting cleanly after USB bandwidth contention.")
        self_status.signal_closing()
        self_status.closed.value = True
        return
    except CameraStartupAborted:
        logger.info(f"Camera {camera_id} worker exiting cleanly after coordinated startup abort.")
        self_status.signal_closing()
        self_status.closed.value = True
        return

    try:
        logger.debug(f"Camera {config.camera_id} frame grab loop starting...")
        run_openpnp_camera_loop(
            camera_shm=camera_shm,
            config=config,
            camera=camera,
            frame_rec_array=frame_rec_array,
            ipc=ipc,
            orchestrator=orchestrator,
            self_status=self_status,
            update_camera_settings_subscription=update_camera_settings_subscription,
            recording_info_subscription=recording_info_subscription,
        )

    except Exception as e:
        self_status.signal_error()
        logger.exception(f"Exception occurred when running Camera Process for Camera: {camera_id} - {e}")
        ipc.kill_everything()
        raise
    finally:
        logger.debug(f"Closing OpenPnPCamera for {camera_id} and shutting down CameraProcess")
        self_status.signal_closing()
        ipc.should_continue = False
        if camera:
            camera.close()
        if camera_shm:
            logger.trace(f"Closing camera {config.camera_index} shared memory")
            camera_shm.close()
        self_status.closed.value = True
        logger.debug(f"Camera {config.camera_index} process completed")
