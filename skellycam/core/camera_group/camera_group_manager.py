import asyncio
import logging
import multiprocessing
from multiprocessing.sharedctypes import Synchronized
from dataclasses import dataclass, field
from datetime import datetime, timezone
from collections.abc import Callable

import numpy as np
from fastapi import FastAPI

from skellycam.api.websocket.performance_data import extract_performance_data_from_frames
from skellycam.core.camera.capture.modes import (
    FLOOR_FPS,
    NO_FLOOR_MODE,
    choose_mode,
    group_rate_problem,
    mixed_rate_text,
    native_from_supported,
    rates_equal,
)
from skellycam.core.camera.capture.source import CaptureFailure, CaptureRequest
from skellycam.core.camera.config.camera_config import CameraConfigs
from skellycam.core.camera_group.camera_group import CameraGroup, RequestRefused, same_config
from skellycam.core.camera_group.camera_start_failure import describe_start_failure
from skellycam.core.device_detection.detect_cameras_devices import CameraDeviceInfo, detect_available_cameras
from skellycam.core.ipc.pubsub.pubsub_manager import TopicTypes
from skellycam.core.ipc.pubsub.pubsub_topics import FramerateMessage
from skellycam.core.ipc.process_management.worker_registry import WorkerRegistry
from skellycam.core.recorders.framerate_tracker import CurrentFramerate
from skellycam.core.recorders.videos.recording_info import RecordingInfo
from skellycam.core.types.type_overloads import (
    CameraGroupIdString,
    CameraIdString,
    FrameNumberInt,
    MultiframeTimestampFloat,
    TopicSubscriptionQueue,
)
from skellycam.core.take_recorder import TakeSummary  # noqa: TC001 — beartype checks annotations at runtime

logger = logging.getLogger(__name__)


@dataclass
class CameraGroupManager:
    global_kill_flag: Synchronized
    worker_registry: WorkerRegistry
    source_factory: Callable | None = None  # ADR-HP7D item 10; None: the source of 14.2
    detected_cameras: dict[CameraIdString, CameraDeviceInfo] = field(default_factory=dict)  # U17 (c)
    closing: bool = False
    camera_groups: dict[CameraGroupIdString, CameraGroup] = field(default_factory=dict)
    camera_group_framerate_subscriptions: dict[CameraGroupIdString, TopicSubscriptionQueue] = field(
        default_factory=dict
    )

    async def create_and_start_camera_group(self, camera_configs: CameraConfigs) -> CameraGroup:
        """Create a camera group with the provided configuration settings."""
        camera_group, _ = await self._create_and_start(camera_configs)
        return camera_group

    async def _create_and_start(self, camera_configs: CameraConfigs) -> tuple:
        camera_group = CameraGroup.create(
            camera_configs=camera_configs,
            heartbeat_timestamp=self.worker_registry.heartbeat_timestamp,
            global_kill_flag=self.global_kill_flag,
            worker_registry=self.worker_registry,
            source_factory=self.source_factory,
        )
        self.camera_group_framerate_subscriptions[camera_group.id] = (
            camera_group.ipc.pubsub.get_subscription(TopicTypes.FRAMERATE)
        )
        self.camera_groups[camera_group.id] = camera_group
        try:
            failures = await self.camera_groups[camera_group.id].start()
        except Exception:
            # Startup failed (e.g. the group stopped) — tear the half-started group down so a
            # retry creates a fresh group.
            logger.error(f"Camera group {camera_group.id} failed to start, tearing it down")
            try:
                await camera_group.close()
            except Exception as close_err:
                logger.error(f"Error closing failed camera group {camera_group.id}: {close_err}")
            del self.camera_groups[camera_group.id]
            del self.camera_group_framerate_subscriptions[camera_group.id]
            raise

        logger.info(
            f"Creating camera group with ID: {camera_group.id} "
            f"and cameras: {camera_group.camera_ids}"
        )
        return camera_group, failures

    async def create_or_update_camera_group(self, camera_configs: CameraConfigs) -> tuple[CameraGroup, dict, list]:
        """Check the request as a whole (8.3), then apply it to each camera on its own (U10).

        Return the group, the failure object of each camera that failed (8.4) and the warnings (11.3).
        Raise `RequestRefused` (422 or 409) before any change.
        """
        camera_groups = self._get_configs_by_group(camera_configs)
        if len(camera_groups) > 1:
            raise NotImplementedError("Cannot update multiple camera groups at once (yet).")
        camera_group = self.get_camera_group(next(iter(camera_groups))) if camera_groups else None
        if any(camera_id not in self.detected_cameras for camera_id, config in camera_configs.items()
               if config.use_this_camera):
            # 7.1, U17: the check needs the detection data, also to refuse a virtual camera (ADR-PDD3 W5)
            self.detected_cameras = {camera.camera_id: camera
                                     for camera in await asyncio.to_thread(detect_available_cameras)}
        warnings, rates_known = self._check_request(camera_configs, camera_group)
        started = datetime.now(timezone.utc)
        if camera_group is None:
            selected = {camera_id: config for camera_id, config in camera_configs.items() if config.use_this_camera}
            camera_group, failures = await self._create_and_start(selected)
        else:
            failures, change_warnings = await camera_group.apply(camera_configs)
            warnings += change_warnings
        if failures:
            # One explanation of the failed start, where it adds a cause to the reasons (port from sfn26)
            text = await asyncio.to_thread(describe_start_failure, failures, camera_configs, started,
                                           detect_available_cameras)
            if text:
                warnings.append(dict(kind="start_failure", camera_ids=sorted(failures), text=text))
                logger.warning(text)
        if not rates_known:
            # agent 56, ADR-PDD3 W3: different real rates after the open give a warning item and a log record
            rates = {camera_id: config.framerate for camera_id, config in camera_group.configs.items()
                     if config.framerate > 0 and camera_id not in failures}
            text = mixed_rate_text(rates) if rates else None
            if text:
                warnings.append(dict(kind="mixed_rate", camera_ids=sorted(rates), text=text))
                logger.warning(text)
        return camera_group, failures, warnings

    def _check_request(self, camera_configs: CameraConfigs, camera_group: CameraGroup | None) -> tuple[list, bool]:
        """The whole-request check of 8.3: 422 by content (7.5, U11), then 409 by the camera states.

        A camera of the group that the request does not name counts with its current config.
        Return the warnings and whether the mode rates came from the detection data.
        """
        effective = dict(camera_group.configs) if camera_group is not None else {}
        effective.update(camera_configs)
        selected = {camera_id: config for camera_id, config in effective.items() if config.use_this_camera}
        if camera_group is None and not selected:
            raise RequestRefused(422, "The request selects no camera")
        problems = [f"camera {camera_id}: {NO_FLOOR_MODE}" for camera_id, config in selected.items()
                    if config.framerate not in (-1, 0) and config.framerate < FLOOR_FPS - 0.5]  # agent 55
        infos = {camera_id: self.detected_cameras.get(camera_id) for camera_id in selected}
        problems += [f"camera {camera_id} is a virtual camera; virtual cameras cannot be selected"
                     for camera_id, info in infos.items() if info is not None and info.virtual]  # ADR-PDD3 W5
        # 7.5: the modes were read and none is at the floor (an unread list is also [])
        problems += [f"camera {camera_id}: {NO_FLOOR_MODE}" for camera_id, info in infos.items()
                     if info is not None and info.modes_read and not info.supported_modes]
        rates_known = bool(selected) and all(info is not None and info.supported_modes for info in infos.values())
        warnings = []
        if rates_known:  # ADR-HP7D item 2: the mode rates that 7.5 gives from the detection data
            rates = {}
            for camera_id, config in selected.items():
                request = CaptureRequest(camera_id=camera_id, width=config.resolution.width,
                                         height=config.resolution.height, framerate=config.framerate,
                                         capture_fourcc=config.capture_fourcc)
                try:
                    rates[camera_id] = choose_mode(native_from_supported(infos[camera_id].supported_modes),
                                                   request).fps
                except CaptureFailure as failure:
                    problems.append(f"camera {camera_id}: {failure.reason}")
            if not problems and rates:
                problem = group_rate_problem(rates)
                if problem:
                    problems.append(problem)
                elif text := mixed_rate_text(rates):  # U15: 29.97 with 30 is allowed, with a warning
                    warnings.append(dict(kind="mixed_rate", camera_ids=sorted(rates), text=text))
        else:  # agent 56: the requested rates must be all equal or all auto
            requested = [config.framerate for config in selected.values()]
            autos = [rate in (-1, 0) for rate in requested]
            if not all(autos) and (any(autos) or not all(rates_equal(rate, requested[0]) for rate in requested)):
                problems.append("all cameras of a group must request one frame rate, or each 'auto': "
                                + ", ".join(f"camera {camera_id} {config.framerate:g}"
                                            for camera_id, config in selected.items()))
        if problems:
            raise RequestRefused(422, "; ".join(problems))
        if camera_group is not None:
            statuses = camera_group.cameras.orchestrator.camera_statuses
            recording = [camera_id for camera_id, status in list(statuses.items())
                         if status.recording_in_progress.value]
            if recording:  # D36
                raise RequestRefused(409, "A recording runs: no change is possible; recording cameras: "
                                          + ", ".join(recording))
            blocked = [f"camera {camera_id} is {statuses[camera_id].state}"
                       for camera_id, config in camera_configs.items()
                       if camera_id in camera_group.configs and statuses[camera_id].state in ("starting", "waiting")
                       and config.use_this_camera and not same_config(config, camera_group.configs[camera_id])]
            if blocked:  # agent 45
                raise RequestRefused(409, "A camera that starts cannot take a changed config: " + "; ".join(blocked))
        for item in warnings:
            logger.warning(item["text"])
        return warnings, rates_known

    def get_camera_group(self, camera_group_id: CameraGroupIdString) -> CameraGroup:
        """Retrieve a camera group by its ID."""
        if camera_group_id not in self.camera_groups:
            raise ValueError(f"Camera group with ID {camera_group_id} does not exist.")
        return self.camera_groups[camera_group_id]

    def _get_configs_by_group(
        self, camera_configs: CameraConfigs
    ) -> dict[CameraGroupIdString, CameraConfigs]:
        configs_by_group: dict[CameraGroupIdString, CameraConfigs] = {}
        for camera_group in self.camera_groups.values():
            configs_by_group[camera_group.id] = {}
            for camera_id, camera_config in camera_configs.items():
                if camera_id in camera_group.camera_ids:
                    configs_by_group[camera_group.id][camera_id] = camera_config
        return configs_by_group

    async def close_all_camera_groups(self) -> None:
        """Close all camera groups."""
        self.closing = True
        if not self.camera_groups:
            logger.warning("No camera groups to close.")
            return

        for camera_group_id in list(self.camera_groups.keys()):
            await self.camera_groups[camera_group_id].close()
        logger.success(
            f"Successfully closed all camera groups ids - {list(self.camera_groups.keys())}"
        )
        self.camera_groups.clear()
        self.closing = False

    async def start_recording_all_groups(self, recording_info: RecordingInfo) -> list:
        """Start recording for all camera groups. Return the warnings of 11.3."""
        warnings = []
        for camera_group in self.camera_groups.values():
            warnings += await camera_group.start_recording(recording_info=recording_info,
                                                           devices=self.detected_cameras)
            logger.info(f"Started recording for camera group ID: {camera_group.id}")
        return warnings

    async def stop_recording_all_groups(self) -> list[TakeSummary]:
        """Stop recording for all camera groups."""
        results: list[TakeSummary] = []
        for camera_group in self.camera_groups.values():
            results.append(await camera_group.stop_recording())
            logger.info(f"Stopped recording for camera group ID: {camera_group.id}")
        return results

    def get_latest_frontend_payloads(
        self,
        if_newer_than: dict[CameraGroupIdString, int],
    ) -> dict[CameraGroupIdString, tuple[FrameNumberInt, MultiframeTimestampFloat, memoryview]]:
        if self.closing:
            return {}
        fe_payloads: dict[
            CameraGroupIdString, tuple[FrameNumberInt, MultiframeTimestampFloat, memoryview]
        ] = {}
        for camera_group in self.camera_groups.values():
            fe_return = camera_group.get_latest_ring_payload()
            if fe_return is None:
                continue
            frame_number, multiframe_timestamp, fe_payload = fe_return
            if fe_payload is None:
                continue
            fe_payloads[camera_group.id] = (frame_number, multiframe_timestamp, fe_payload)
        return fe_payloads

    def get_backend_framerate_updates(self) -> dict[CameraGroupIdString, CurrentFramerate]:
        """Get the latest framerate updates for all camera groups."""
        framerate_updates: dict[CameraGroupIdString, CurrentFramerate] = {}
        for camera_group_id, subscription in self.camera_group_framerate_subscriptions.items():
            if not subscription.empty():
                framerate_update = subscription.get()
                if isinstance(framerate_update, FramerateMessage):
                    framerate_updates[camera_group_id] = framerate_update.current_framerate
                else:
                    raise TypeError(
                        f"Received unexpected data type from framerate subscription: "
                        f"{type(framerate_update)}"
                    )
        return framerate_updates

    def get_latest_performance_data(
        self,
        session_start_perf_ns: int,
    ) -> dict[CameraGroupIdString, dict]:
        """
        Get per-camera frame lifecycle performance data for all camera groups.
        Returns a dict mapping camera_group_id to performance data dicts
        suitable for streaming to the frontend Perspective tables.
        """
        if self.closing:
            return {}
        result: dict[CameraGroupIdString, dict] = {}
        for camera_group in self.camera_groups.values():
            latest_frames = camera_group.read_latest_ring_frames()
            if latest_frames is None:
                continue
            try:
                perf_data = extract_performance_data_from_frames(
                    latest_frames=latest_frames,
                    session_start_perf_ns=session_start_perf_ns,
                )
                result[camera_group.id] = perf_data
            except Exception as e:
                logger.debug(f"Error extracting performance data for group {camera_group.id}: {e}")
        return result

    async def set_paused_all_groups(self, *, paused: bool, await_state_change: bool = True) -> None:
        """Set the pause state of all camera groups (PUT /group/all/pause)."""
        for camera_group in self.camera_groups.values():
            await camera_group.set_paused(paused=paused, await_state_change=await_state_change)
            logger.info(f"{'Paused' if paused else 'Unpaused'} camera group ID: {camera_group.id}")

    def find_camera_group_by_camera_ids(
        self, camera_ids: list[CameraIdString]
    ) -> CameraGroup | None:
        """Find a camera group that contains all the specified camera IDs."""
        for camera_group in self.camera_groups.values():
            if all(camera_id in camera_group.camera_ids for camera_id in camera_ids):
                return camera_group
        return None

    def to_state_dict(self) -> dict[CameraGroupIdString, dict]:
        """Convert the CameraGroupManager to a serializable state dictionary."""
        return {
            "camera_groups": {
                cg_id: cg.to_state().model_dump() for cg_id, cg in self.camera_groups.items()
            }
        }


_CAMERA_GROUP_MANAGER: CameraGroupManager | None = None


async def close_camera_groups() -> None:
    """Close every camera group, so that an open take finishes before the worker monitor exits."""
    if _CAMERA_GROUP_MANAGER is not None and _CAMERA_GROUP_MANAGER.camera_groups:
        await _CAMERA_GROUP_MANAGER.close_all_camera_groups()


def get_or_create_camera_group_manager(app: FastAPI) -> CameraGroupManager:
    """Create the singleton CameraGroupManager instance."""
    global _CAMERA_GROUP_MANAGER

    if _CAMERA_GROUP_MANAGER is not None:
        return _CAMERA_GROUP_MANAGER

    _CAMERA_GROUP_MANAGER = CameraGroupManager(
        global_kill_flag=app.state.global_kill_flag,
        worker_registry=app.state.worker_registry,
    )
    return _CAMERA_GROUP_MANAGER
