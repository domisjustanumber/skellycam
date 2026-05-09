import logging

import numpy as np

from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.openpnp.openpnp_helpers.create_initial_frame_recarray import create_initial_frame_rec_array
from skellycam.core.camera.openpnp.openpnp_helpers.create_openpnp_camera import create_openpnp_camera
from skellycam.core.camera_group.usb_bandwidth import CameraStartupAborted, UsbBandwidthContentionError
from skellycam.core.camera.openpnp_capture import OpenPnPCamera
from skellycam.core.camera_group.camera_group_ipc import CameraGroupIPC
from skellycam.core.camera_group.camera_orchestrator import CameraOrchestrator
from skellycam.core.camera_group.camera_status import CameraStatus
from skellycam.core.ipc.pubsub.pubsub_manager import TopicTypes
from skellycam.core.ipc.pubsub.pubsub_topics import DeviceExtractedConfigMessage, SetShmMessage
from skellycam.core.ipc.shared_memory.camera_shared_memory_ring_buffer import CameraSharedMemoryRingBuffer
from skellycam.core.types.type_overloads import TopicSubscriptionQueue
from skellycam.utilities.wait_functions import wait_10ms

logger = logging.getLogger(__name__)


# How long any single worker is allowed to wait at the device-open barrier before giving up
# and opening on its own. ``CameraManager.start`` staggers spawn by ~1s/camera on Windows for
# the import phase, so 60s is generous (covers ~50 cameras of stagger + slow imports).
_BARRIER_WAIT_TIMEOUT_SECONDS = 60.0


def setup_openpnp_camera_loop(
    camera_shm: CameraSharedMemoryRingBuffer | None,
    config: CameraConfig,
    ipc: CameraGroupIPC,
    orchestrator: CameraOrchestrator,
    self_status: CameraStatus,
    shm_subscription: TopicSubscriptionQueue,
) -> tuple[CameraSharedMemoryRingBuffer, CameraConfig, OpenPnPCamera, np.recarray]:
    peer_count = max(0, len(orchestrator.camera_statuses) - 1)

    def _pre_open_sync() -> None:
        """Rendezvous with peer workers immediately before ``Cap_openStream``.

        Sequential opens fail on some Logitech UVC stacks: while one camera is already
        streaming, a second ``Cap_openStream`` succeeds but never delivers frames; and
        ``close()+open()`` to make room for a peer wedges the camera that reopened. Opening
        every device in the same wall-clock moment leaves no "incumbent" stream, so MF / the
        USB stack negotiates bandwidth across all of them at once.
        """
        barrier = ipc.device_open_barrier
        if barrier is None:
            return
        try:
            logger.debug(
                f"Camera {config.camera_id} waiting at device-open barrier "
                f"(peers={peer_count})..."
            )
            barrier.wait(timeout=_BARRIER_WAIT_TIMEOUT_SECONDS)
            logger.debug(f"Camera {config.camera_id} cleared device-open barrier; opening stream.")
        except Exception as barrier_err:
            # ``BrokenBarrierError`` (timeout / abort) or any other failure: log and proceed
            # with the open. A peer crashing earlier will already have set kill flags; if not,
            # opening on our own is the most useful fallback for the user.
            logger.warning(
                f"Camera {config.camera_id}: device-open barrier failed "
                f"({type(barrier_err).__name__}: {barrier_err}); opening stream without sync."
            )

    try:
        camera, config = create_openpnp_camera(
            config,
            parallel_peer_count=peer_count,
            pre_open_sync=_pre_open_sync,
        )
    except UsbBandwidthContentionError as e:
        self_status.likely_usb_bandwidth_contention.value = True
        # Avoid logger.exception() here — a multi-line traceback for an *expected*
        # structural failure pollutes the log. The user-facing guidance is delivered
        # via the HTTP 409 response (see ``camera_router.py``).
        logger.warning(f"[{config.camera_id}] USB bandwidth contention suspected: {e}")
        self_status.signal_error()
        ipc.kill_everything()
        raise
    except Exception as e:
        logger.exception(f"Failed to open camera {config.camera_id}: {e}")
        self_status.signal_error()
        ipc.kill_everything()
        raise RuntimeError(f"Could not create OpenPnPCamera for camera {config.camera_id}") from e

    drain_buffer = np.zeros((config.resolution.height, config.resolution.width, 3), dtype=np.uint8)

    try:
        ipc.pubsub.topics[TopicTypes.EXTRACTED_CONFIG].publish(DeviceExtractedConfigMessage(extracted_config=config))

        # The capture stream stays open from create_openpnp_camera through the SHM wait and into
        # the frame loop. Closing and reopening within the same worker process wedges the
        # Logitech UVC drivers seen on Windows (camera reports ``is_open=True`` but never
        # delivers frames again), so we never close the stream during setup.
        #
        # Do NOT actively drain frames during the SHM wait. ``capture_frame_into`` on an early
        # camera holds enough USB / Media Foundation bandwidth that a peer whose
        # ``Cap_openStream`` is still in flight (DirectShow's ``IMediaControl::Run`` serializes
        # bandwidth allocation, so a later peer's open can block for many seconds) never gets a
        # first frame. The driver continues to push frames into MF's internal buffer regardless;
        # we simply don't read until the worker enters the orchestrator-gated drain loop after
        # SHM arrives, by which point every peer is also open.
        logger.debug(f"Camera {config.camera_id} connected, awaiting shm message...")
        while camera_shm is None and ipc.should_continue and not self_status.should_close.value:
            wait_10ms()
            if not shm_subscription.empty():
                shm_message: SetShmMessage = shm_subscription.get()
                if not isinstance(shm_message, SetShmMessage):
                    raise RuntimeError(
                        f"Expected SetShmMessage for camera {config.camera_id}, but received {type(shm_message)}"
                    )
                camera_shm_dto = shm_message.camera_group_shm_dto.camera_shm_dtos[config.camera_id]
                logger.debug(f"Creating camera shared memory for camera {config.camera_id}...")
                camera_shm = CameraSharedMemoryRingBuffer.recreate(dto=camera_shm_dto, read_only=False)
        if camera_shm is None or not camera_shm.valid:
            # If shutdown was triggered cooperatively (peer worker failed and called
            # ``kill_everything``, or the user closed the group mid-startup), this is
            # a known-good abort path — surface a typed sentinel so the worker entry
            # point can return cleanly without the multiprocessing "unhandled exception"
            # traceback dump. The peer's specific error (e.g. ``UsbBandwidthContentionError``)
            # is already recorded on its ``CameraStatus`` and surfaced by the main process
            # via ``await_extracted_configs``.
            shutdown_triggered = (
                ipc.global_kill_flag.value
                or ipc.shutdown_camera_group_flag.value
                or self_status.should_close.value
            )
            if shutdown_triggered:
                raise CameraStartupAborted(
                    f"Camera {config.camera_id}: startup aborted before shared memory arrived "
                    f"(shutdown_camera_group_flag={ipc.shutdown_camera_group_flag.value}, "
                    f"global_kill_flag={ipc.global_kill_flag.value}, "
                    f"should_close={self_status.should_close.value}). "
                    "Likely a peer camera failed during startup."
                )
            raise RuntimeError(
                f"Camera {config.camera_id}: shared memory was not initialized before startup stopped. "
                "The main process only sends shared-memory handles after every camera has published its "
                "extracted configuration; another worker may have failed, or IPC shutdown was triggered. "
                f"Diagnostics: shutdown_camera_group_flag={ipc.shutdown_camera_group_flag.value}, "
                f"global_kill_flag={ipc.global_kill_flag.value}, should_close={self_status.should_close.value}. "
                "See other cameras in this group or earlier errors."
            )

        if not camera.is_open():
            raise RuntimeError(f"OpenPnPCamera for camera {config.camera_id} is not open")
        self_status.connected.value = True
        logger.success(f"Camera {config.camera_id} ready!")
        while not orchestrator.all_ready and ipc.should_continue and not self_status.should_close.value:
            _ = camera.capture_frame_into(drain_buffer)
            wait_10ms()
        frame_rec_array = create_initial_frame_rec_array(config=config, ipc=ipc)

    except CameraStartupAborted as e:
        logger.info(f"[{config.camera_id}] startup aborted cooperatively: {e}")
        self_status.signal_error()
        ipc.kill_everything()
        if camera is not None:
            try:
                camera.close()
            except Exception:
                pass
        raise
    except Exception as e:
        logger.exception(f"Camera worker failed for {config.camera_id} after device open: {e}")
        self_status.signal_error()
        ipc.kill_everything()
        raise
    return camera_shm, config, camera, frame_rec_array
