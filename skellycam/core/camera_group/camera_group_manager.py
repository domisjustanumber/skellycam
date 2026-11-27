import asyncio
import logging
import multiprocessing
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from collections.abc import Callable

import numpy as np
from fastapi import FastAPI

from skellycam.core.camera.capture.modes import (
    FLOOR_FPS,
    NO_FLOOR_MODE,
    NO_USABLE_MODE,
    RAW_FORMATS,
    choose_mode,
    group_rate_problem,
    mixed_rate_text,
    native_from_capture_modes,
    native_from_supported,
    rates_equal,
    size_at_floor,
    small_request_text,
)
from skellycam.core import capture_timings
from skellycam.core.camera.camera_worker import select_capture_source
from skellycam.core.camera.capture import encoder as capture_encoder
from skellycam.core.camera.capture import restore_store as restore_files
from skellycam.core.camera.capture.failure_codes import WEDGE_CODES
from skellycam.core.camera.capture.source import CaptureFailure, CaptureRequest
from skellycam.core.camera.config.camera_config import CameraConfigs, MAX_MANUAL_EXPOSURE
from skellycam.core.camera_group.camera_group import REQUEST_RUNS, CameraGroup, RequestRefused, same_config
from skellycam.core.camera_group.camera_start_failure import describe_start_failure
from skellycam.core.device_detection.detect_cameras_devices import CameraDeviceInfo, detect_available_cameras
from skellycam.core.ipc.pubsub.pubsub_manager import TopicTypes
from skellycam.core.ipc.process_management.worker_registry import WorkerRegistry
from skellycam.core.recorders.videos.recording_info import RecordingInfo
from skellycam.core.types.type_overloads import (
    CameraGroupIdString,
    CameraIdString,
    SharedValue,
    TopicSubscriptionQueue,
)
from skellycam.core.take_recorder import TakeSummary  # noqa: TC001 — beartype checks annotations at runtime

logger = logging.getLogger(__name__)
CLOSED_DURING_REQUEST = "The cameras were closed while the request ran. Send the request again."
CLOSING_REFUSED = "The cameras close: no recording starts"  # recorder.md 9.1 item 7


@dataclass
class CameraGroupManager:
    global_kill_flag: SharedValue
    worker_registry: WorkerRegistry
    source_factory: Callable | None = None  # ADR-HP7D item 10; None: the source of 14.2
    detected_cameras: dict[CameraIdString, CameraDeviceInfo] = field(default_factory=dict)  # U17 (c)
    closing: bool = False
    closed_diagnostics: dict = field(default_factory=dict)  # the last dicts of each camera of a closed group (F4)
    searching: bool = False  # an exposure search of the endpoint runs (camera-requests.md 1.5)
    creating: bool = False  # an apply request makes a group: no second one may (camera-requests.md 2.4a item 7) [Z7F3]
    closes: int = 0  # the count of close requests: a close ends a request that makes a group (2.4a item 7) [Z7F3]
    restore_records: dict = field(default_factory=dict)  # unix-capture.md 4.7 [NYT6]: from a group to the next
    # unix-capture.md 4.7.1 [HQE5]: the folder of the restore files. None (certify, the tests): no file is read or written.
    restore_store: object = None
    camera_groups: dict[CameraGroupIdString, CameraGroup] = field(default_factory=dict)
    camera_group_framerate_subscriptions: dict[CameraGroupIdString, TopicSubscriptionQueue] = field(
        default_factory=dict
    )
    _log_capture_times: bool = False  # capture-timings.md 2: the one switch of the app
    quick_sync: bool | None = None  # windows-capture.md 13.2 [3WCA 6]: the one Quick Sync check of the app run
    _quick_sync_lock: object = field(default_factory=threading.Lock)  # 22.7 item 8: one check at a time
    encoder_failed: set = field(default_factory=set)  # 22.2 [U Q886]: cameras that fell back from Quick Sync
    _last_statuses: dict = field(default_factory=dict)  # camera_id -> its status of the newest group (Q886)

    @property
    def log_capture_times(self) -> bool:
        return self._log_capture_times

    def set_log_capture_times(self, on: bool) -> None:
        """capture-timings.md 2 items 2 to 5: write the switch into each status of each group. The kept summaries go
        at each change; each camera applies the change at its next publish."""
        self._log_capture_times = bool(on)
        for group in list(self.camera_groups.values()):
            self._write_switch(group)
            group.camera_timings = {}

    def _write_switch(self, group) -> None:
        cameras = group.cameras
        statuses = {**cameras.removed_statuses, **cameras.orchestrator.camera_statuses}
        for camera_id, status in statuses.items():
            # 22.2 [U Q886]: a fallback in the status of this group or of the last group (its shared value stays
            # readable after its close) keeps the camera on cv2 for the app run
            if any(known is not None and known.encoder_failed.value
                   for known in (self._last_statuses.get(camera_id), status)):
                self.encoder_failed.add(camera_id)
            self._last_statuses[camera_id] = status
            status.log_capture_times.value = self._log_capture_times
            status.quick_sync.value = bool(self.quick_sync)  # 13.2: each camera process gets the result
            if camera_id in self.encoder_failed:  # only True: a fallback that lands meanwhile is never reset
                status.encoder_failed.value = True

    def capture_timings(self) -> dict:
        """capture-timings.md 6.3: the newest summary of each camera of each open group, at most 3 s old. It reads no
        ring, never raises for a missing camera, and is safe from any thread of the main process."""
        summaries = []
        if self._log_capture_times:
            now = capture_timings.main_clock_ns()
            for group in list(self.camera_groups.values()):
                if group._closing:
                    continue
                summaries.extend(summary for summary, received_ns in group.camera_timings.values()
                                 if now - received_ns <= capture_timings.MAX_AGE_NS)
        return {"version": capture_timings.VERSION, "log_capture_times": self._log_capture_times,
                "summaries": summaries}

    async def create_and_start_camera_group(self, camera_configs: CameraConfigs) -> CameraGroup:
        """Create a camera group with the provided configuration settings."""
        camera_group, _ = await self._create_and_start(camera_configs)
        camera_group.request_runs = False
        return camera_group

    async def _create_and_start(self, camera_configs: CameraConfigs) -> tuple:
        identities = {}
        if self.restore_store is not None:  # 4.7.1: a camera with no record in memory takes the entry of its file
            salt = restore_files.salt_of(self.restore_store)  # the main process only: a camera process gets its key
            identities = {camera_id: restore_files.identity(self.detected_cameras.get(camera_id), salt=salt)
                          for camera_id in camera_configs}
            missing = [camera_id for camera_id in camera_configs if not self.restore_records.get(camera_id)]
            self.restore_records.update(restore_files.read_entries(self.restore_store, missing, self.detected_cameras,
                                                                   identities))
        camera_group = CameraGroup.create(
            camera_configs=camera_configs,
            heartbeat_timestamp=self.worker_registry.heartbeat_timestamp,
            global_kill_flag=self.global_kill_flag,
            worker_registry=self.worker_registry,
            source_factory=self.source_factory,
            restore_records=self.restore_records,
            restore_store=self.restore_store,
            restore_identities=identities,
        )
        self._write_switch(camera_group)  # before the camera processes start (capture-timings.md 2 item 2)
        self.camera_group_framerate_subscriptions[camera_group.id] = (
            camera_group.ipc.pubsub.get_subscription(TopicTypes.FRAMERATE)
        )
        self.camera_groups[camera_group.id] = camera_group
        camera_group.request_runs = True  # camera-requests.md 2.4a item 7: before the first wait; the caller clears it
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
            self.camera_groups.pop(camera_group.id, None)  # a close of all groups can have removed it first
            self.camera_group_framerate_subscriptions.pop(camera_group.id, None)
            raise

        logger.info(
            f"Creating camera group with ID: {camera_group.id} "
            f"and cameras: {camera_group.camera_ids}"
        )
        return camera_group, failures

    async def create_or_update_camera_group(self, camera_configs: CameraConfigs,
                                            retry=()) -> tuple[CameraGroup, dict, list]:
        """One change of the cameras at a time (camera-requests.md 2.4a item 7) [ADR-1T0S]: the request sets
        `request_runs` of its group with no wait after its whole-request check, and this call clears it at the end.
        `retry`: `retry_camera_ids`, the failed or dead cameras that the request opens again (windows-capture.md 8.3)."""
        flagged = []
        try:
            return await self._create_or_update(camera_configs, flagged, retry)
        finally:
            for camera_group in flagged:
                if camera_group is self:
                    self.creating = False
                else:
                    camera_group.request_runs = False

    async def _create_or_update(self, camera_configs: CameraConfigs, flagged: list,
                                retry=()) -> tuple[CameraGroup, dict, list]:
        """Check the request as a whole (8.3), then apply it to each camera on its own (U10).

        Return the group, the failure object of each camera that failed (8.4) and the warnings (11.3).
        Raise `RequestRefused` (422 or 409) before any change.
        """
        clamped = [dict(kind="exposure_clamped", camera_ids=[camera_id], control="exposure",  # 1.1, 1.5 [NYT6]
                        text=f"Camera {camera_id}: manual exposure {config.exposure} is above the limit "
                             f"{MAX_MANUAL_EXPOSURE}. The exposure is {MAX_MANUAL_EXPOSURE}.")
                   for camera_id, config in camera_configs.items() if config.use_this_camera
                   and config.exposure_mode == "MANUAL" and config.exposure > MAX_MANUAL_EXPOSURE]
        camera_configs = {camera_id: config.model_copy(update=dict(exposure=MAX_MANUAL_EXPOSURE))
                          if config.exposure_mode == "MANUAL" and config.exposure > MAX_MANUAL_EXPOSURE else config
                          for camera_id, config in camera_configs.items()}  # sfn26 43e2b968a: the clamp
        camera_groups = self._get_configs_by_group(camera_configs)
        if len(camera_groups) > 1:
            raise NotImplementedError("Cannot update multiple camera groups at once (yet).")
        camera_group = self.get_camera_group(next(iter(camera_groups))) if camera_groups else None
        if camera_group is None:  # 2.4a item 7 [Z7F3]: no group yet, so no group flag; no wait between check and set
            if self.creating:
                raise RequestRefused(409, REQUEST_RUNS)
            self.creating = True
            flagged.append(self)
            closes = self.closes
        if any(camera_id not in self.detected_cameras for camera_id, config in camera_configs.items()
               if config.use_this_camera):
            # 7.1, U17: the check needs the detection data, also to refuse a virtual camera (ADR-PDD3 W5)
            self.detected_cameras = {camera.camera_id: camera
                                     for camera in await asyncio.to_thread(detect_available_cameras)}
        if camera_group is not None:
            camera_group.adopt_search_results()
        warnings, rates_known = self._check_request(camera_configs, camera_group)
        if self.quick_sync is None and self._opens_raw(camera_configs):
            # 13.2: only for a request that the check accepts; the check runs again after the wait, so the check of
            # `request_runs` and its set have no wait between them (camera-requests.md 2.4a item 7) [ZEK6 2]
            if await asyncio.to_thread(self._check_quick_sync_once) and camera_group is not None:
                self._write_switch(camera_group)
            warnings, rates_known = self._check_request(camera_configs, camera_group)
        before, counts = {}, {}  # camera-requests.md 2.4a [ADR-1T0S]: for the fall back to 30 fps
        if camera_group is not None:  # camera-requests.md 1.5 [AC5B]: each apply request of the user clears them
            camera_group.request_runs = True  # 2.4a item 7: no wait since the check
            flagged.append(camera_group)
            camera_group.clear_group_warnings()
            camera_group.fall_back_armed = None
            camera_group.request_count += 1  # 2.4a item 7: a fall back of an earlier request does not run
            before = dict(camera_group.configs)
            counts = {camera_id: status.search_count.value for camera_id, status in {
                **camera_group.cameras.orchestrator.camera_statuses, **camera_group.cameras.removed_statuses}.items()}
        started = datetime.now(timezone.utc)
        if camera_group is None:
            if self.closes != closes:  # a close came during the detection: it ends this change (2.4a item 7)
                raise RequestRefused(409, CLOSED_DURING_REQUEST)
            selected = {camera_id: config for camera_id, config in camera_configs.items() if config.use_this_camera}
            camera_group, failures = await self._create_and_start(selected)
            flagged.append(camera_group)  # `_create_and_start` set `request_runs`
        else:
            failures, change_warnings = await camera_group.apply(camera_configs, retry)
            warnings += change_warnings
        # [Z7F3]: a failed camera that the request left alone is in the answer, but it is no failure of this request
        kept = {camera_id for item in warnings if item["kind"] == "camera_not_retried" for camera_id in item["camera_ids"]}
        for item in clamped:  # the main process owns it (camera-requests.md 1.5)
            logger.warning(item["text"])
            warnings.append(item)
            camera_group.add_group_warning(item)
        if any(config.use_this_camera and abs(config.framerate - 60) <= 0.5 for config in camera_configs.values()):
            # 2.4: a request at 60 fps falls the group back to the configs from before the request, at 30 fps, one time
            fallback = {camera_id: (before.get(camera_id) or camera_configs.get(camera_id) or config).model_copy(
                update=dict(framerate=30.0)) for camera_id, config in camera_group.configs.items()}
            statuses = camera_group.cameras.orchestrator.camera_statuses
            slow = {camera_id: (statuses[camera_id].info_dict().get("measured_fps"), camera_group.configs[camera_id].exposure,
                                camera_group.mode_rate(camera_id) or camera_group.configs[camera_id].framerate)
                    if failure.get("stage") == "rate check" else (None, None, None)  # 2.4a item 4: `set mode`
                    for camera_id, failure in failures.items() if camera_id not in kept
                    and failure.get("stage") in ("set mode", "rate check") and failure.get("code") not in WEDGE_CODES}
            if slow:
                failures, fallback_warnings = await camera_group.fall_back(fallback, slow)
                warnings += [item for item in fallback_warnings if not (  # one item for a camera left alone
                    item["kind"] == "camera_not_retried" and set(item["camera_ids"]) <= kept)]
            else:  # a search at 60 fps can still start it: the watch of the group (2.4a item 5)
                camera_group.fall_back_armed = (fallback, counts, camera_group.request_count)
        new = {camera_id: failure for camera_id, failure in failures.items() if camera_id not in kept}
        if new:
            # One explanation of the failed start, where it adds a cause to the reasons (port from sfn26)
            # Review item 4: the device list only (no camera is activated); the links of the detection before
            links = {camera_id: getattr(device, "usb_link", "unknown") for camera_id, device in self.detected_cameras.items()}
            text = await asyncio.to_thread(describe_start_failure, new, camera_configs, started,
                                           lambda: detect_available_cameras(modes=False), links)
            if text:
                item = dict(kind="start_failure", camera_ids=sorted(new), text=text)
                warnings.append(item)
                logger.warning(text)
                camera_group.add_group_warning(item)  # the main process owns it (camera-requests.md 1.5)
        if not rates_known:
            # agent 56, ADR-PDD3 W3: different real rates after the open give a warning item and a log record
            rates = {camera_id: config.framerate for camera_id, config in camera_group.configs.items()
                     if config.framerate > 0 and camera_id not in failures}
            text = mixed_rate_text(rates) if rates else None
            if text:
                warnings.append(dict(kind="mixed_rate", camera_ids=sorted(rates), text=text))
                logger.warning(text)
        return camera_group, failures, warnings

    def _check_quick_sync_once(self) -> bool:
        """22.7 item 8 [VTW3 17]: one check child for each app run. A second request waits here for the answer of the
        first. Returns whether this call ran the check (then its request writes the switch)."""
        with self._quick_sync_lock:  # a thread lock: the worker thread holds it, so it binds to no event loop
            if self.quick_sync is not None:
                return False
            self.quick_sync = capture_encoder.quick_sync_works()
            return True

    def _opens_raw(self, camera_configs: CameraConfigs) -> bool:
        """13.2 [3WCA 6]: a request with a camera of the Media Foundation source that opens YUY2 or NV12 (also by
        22.2 [Q807]). The detection of the OpenCV source has no `capture_modes` (22.2 [V5])."""
        if self.source_factory is None and select_capture_source() == "opencv":
            return False
        for camera_id, config in camera_configs.items():
            info = self.detected_cameras.get(camera_id)
            if not config.use_this_camera or info is None or not info.capture_modes:
                continue
            try:
                mode = choose_mode(native_from_capture_modes(info.capture_modes), _request(camera_id, config))
            except CaptureFailure:
                continue
            if mode.format in RAW_FORMATS:
                return True
        return False

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
        refused = {camera_id for camera_id, config in selected.items()  # 22.2 [YQN1 9]: the size floor
                   if not size_at_floor(config.resolution.width, config.resolution.height)}
        problems += [f"camera {camera_id}: {small_request_text(selected[camera_id].resolution.width, selected[camera_id].resolution.height)}"
                     for camera_id in refused]
        by_number = {}  # camera-requests.md 8.1: camera_index stays unique in a group
        for camera_id, config in selected.items():
            by_number.setdefault(config.camera_index, []).append(camera_id)
        problems += [" and ".join(f"camera {camera_id}" for camera_id in ids) + f" have the same camera number {number}"
                     for number, ids in by_number.items() if len(ids) > 1]
        infos = {camera_id: self.detected_cameras.get(camera_id) for camera_id in selected}
        problems += [f"camera {camera_id} is a virtual camera; virtual cameras cannot be selected"
                     for camera_id, info in infos.items() if info is not None and info.virtual]  # ADR-PDD3 W5
        # 7.5: the modes were read and none is at the floor (an unread list is also []); 22.2 [Q807]: a raw mode counts
        unusable = {camera_id: info for camera_id, info in infos.items()
                    if info is not None and info.modes_read and not info.supported_modes
                    and not any(mode.selectable for mode in info.capture_modes)}
        for camera_id, info in unusable.items():  # 22.2 [YQN1 9]: a camera with a mode below the size floor names it
            small = any(not size_at_floor(mode.width, mode.height) for mode in info.capture_modes)
            problems.append(f"camera {camera_id} {NO_USABLE_MODE}" if small else f"camera {camera_id}: {NO_FLOOR_MODE}")
        refused |= set(unusable)
        rates_known = bool(selected) and all(info is not None and (info.capture_modes or info.supported_modes)
                                             for info in infos.values())
        warnings = []
        if rates_known:  # ADR-HP7D item 2: the mode rates that 7.5 gives from the detection data
            rates = {}
            for camera_id, config in selected.items():
                if camera_id in refused:  # its reason is in the problems already
                    continue
                info = infos[camera_id]
                # 7.5 [agent 20], 22.2 [V1, N72V 3]: the full native list where detection has it
                native = (native_from_capture_modes(info.capture_modes) if info.capture_modes
                          else native_from_supported(info.supported_modes))
                try:
                    rates[camera_id] = choose_mode(native, _request(camera_id, config)).fps
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
        if problems:  # one text once: the size floor and the mode choice can give the same reason [YQN1 3]
            raise RequestRefused(422, "; ".join(dict.fromkeys(problems)))
        if camera_group is not None:
            if camera_group.request_runs:  # camera-requests.md 2.4a item 7 [ADR-1T0S]
                raise RequestRefused(409, REQUEST_RUNS)
            statuses = camera_group.cameras.orchestrator.camera_statuses
            recording = [camera_id for camera_id, status in list(statuses.items())
                         if status.recording_in_progress.value]
            if recording:  # D36
                raise RequestRefused(409, "A recording runs: no change is possible; recording cameras: "
                                          + ", ".join(recording))
            if camera_group.take is not None or camera_group.take_busy:  # D36, 1.1 [G4]: also in a record start [GEH0]
                raise RequestRefused(409, "A recording runs or starts: no change is possible")
            blocked = [f"camera {camera_id} is {statuses[camera_id].state}"
                       for camera_id, config in camera_configs.items()
                       if camera_id in camera_group.configs
                       and (statuses[camera_id].state in ("starting", "waiting", "adjusting")
                            or statuses[camera_id].search_requested.value)  # [GEH0]: a search is asked for
                       and config.use_this_camera and not same_config(config, camera_group.configs[camera_id])]
            if blocked:  # agent 45
                raise RequestRefused(409, "A camera cannot take a changed config while it starts or sets its exposure: "
                                     + "; ".join(blocked))
        for item in warnings:
            logger.warning(item["text"])
        return warnings, rates_known

    async def search_exposure(self, camera_ids: list | None = None) -> dict:
        """`POST /camera/group/exposure/auto` (camera-requests.md 1.5) [B18]: with no IDs each selected camera that
        streams, else the named cameras. 409 and 422 by the rules of 1.5; a camera that does not stream is named in
        `not_streaming`."""
        if not self.camera_groups:
            raise RequestRefused(409, "No camera group runs")
        group = next(iter(self.camera_groups.values()))
        statuses = group.cameras.orchestrator.camera_statuses
        unknown = [camera_id for camera_id in camera_ids or () if camera_id not in group.configs]
        if unknown:
            raise RequestRefused(422, "These cameras are not selected: " + ", ".join(unknown))
        if group.take is not None or group.take_busy or any(
                status.recording_in_progress.value for status in list(statuses.values())):
            raise RequestRefused(409, "A recording runs: the exposure cannot change")  # D36, 1.1 [G4]
        blocked = [f"camera {camera_id} is {status.state}" for camera_id, status in list(statuses.items())
                   if status.state in ("starting", "waiting", "adjusting")]
        if self.searching or blocked or group.request_runs:  # 1.5; 2.4a item 7 [ADR-1T0S]: a change of the cameras runs
            raise RequestRefused(409, "An exposure search cannot start now: " + "; ".join(
                blocked + ([REQUEST_RUNS] if group.request_runs else []) or ["a search runs"]))
        named = list(camera_ids or group.configs)
        opencv = [camera_id for camera_id in named if statuses[camera_id].info_dict().get("searches") is False]
        if opencv and (camera_ids or len(opencv) == len(named)):  # 1.7 [K2]: the button skips them when others can
            raise RequestRefused(422, "the exposure search does not run on the OpenCV source of this system: "
                                 + ", ".join(opencv))
        lacking = {camera_id: item for camera_id in named for item in statuses[camera_id].warning_items(
            "camera_warnings") if item["kind"] == "no_manual_exposure"}  # 1.9 [K3]: skipped
        streaming = [camera_id for camera_id in named if camera_id not in opencv and camera_id not in lacking
                     and statuses[camera_id].state in ("ready", "too_slow", "checking")]
        self.searching = True
        group.fall_back_armed = None  # 2.4a item 5 [ADR-1T0S]: a search on request is not a request at 60 fps
        try:
            response = await group.search_exposure(streaming)
        finally:
            self.searching = False
        response["not_streaming"] = [camera_id for camera_id in named if camera_id not in opencv
                                     and camera_id not in lacking and camera_id not in streaming]
        response["warnings"] += list(lacking.values())
        return response

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
        self.closes += 1
        if not self.camera_groups:
            logger.warning("No camera groups to close.")
            return  # `closing` stays False: else the payloads stay empty after a close with no group (sfn26)
        self.closing = True
        try:
            # sfn26 43e2b968a: a group whose close raises stays listed, so that a retry closes it
            for camera_group_id in list(self.camera_groups):
                group = self.camera_groups.get(camera_group_id)
                if group is None:  # a second close, or the teardown of a failed start, removed it first
                    continue
                await group.await_take_end()  # recorder.md 9.1 item 3: a shielded start or stop ends first
                await group.close()
                self.closed_diagnostics.update({camera_id: group.diagnostics(camera_id) for camera_id in group.camera_ids})
                self.camera_groups.pop(camera_group_id, None)
                self.camera_group_framerate_subscriptions.pop(camera_group_id, None)
                logger.info(f"Closed camera group ID: {camera_group_id}")
        finally:
            self.closing = False

    async def start_recording_all_groups(self, recording_info: RecordingInfo) -> list:
        """Start recording for all camera groups. Return the warnings of 11.3."""
        if self.closing:  # recorder.md 9.1 item 7: the close of the groups runs (also the background close of /shutdown)
            raise RequestRefused(409, CLOSING_REFUSED)
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

    def find_camera_group_by_camera_ids(
        self, camera_ids: list[CameraIdString]
    ) -> CameraGroup | None:
        """Find a camera group that contains all the specified camera IDs."""
        for camera_group in self.camera_groups.values():
            if all(camera_id in camera_group.camera_ids for camera_id in camera_ids):
                return camera_group
        return None

    def diagnostics(self) -> dict:
        """`{camera_id: dict}` of each camera of each group, the full newest dict (unix-capture.md 4.2 item 2). A
        closed group keeps its last dicts here until a later group has the camera: certify reads the restore
        keys of the close (F4)."""
        live = {camera_id: group.diagnostics(camera_id) for group in list(self.camera_groups.values())
                for camera_id in group.camera_ids}
        return {**self.closed_diagnostics, **live}

    def to_state_dict(self) -> dict[CameraGroupIdString, dict]:
        """Convert the CameraGroupManager to a serializable state dictionary."""
        return {
            "camera_groups": {
                cg_id: cg.to_state().model_dump() for cg_id, cg in self.camera_groups.items()
            }
        }


_CAMERA_GROUP_MANAGER: CameraGroupManager | None = None


def _request(camera_id: CameraIdString, config) -> CaptureRequest:
    return CaptureRequest(camera_id=camera_id, width=config.resolution.width, height=config.resolution.height,
                          framerate=config.framerate, capture_fourcc=config.capture_fourcc)


async def close_camera_groups_before_exit() -> None:
    """An exit of the app (the shutdown endpoint, the lifespan end, Ctrl-C) stops a running take through the
    take level (recorder.md 8.1) and closes the camera groups before the kill flag ends the camera
    processes: else the manifest stays `recording` (third review S4, ADR-P5VE). Each wait of the stop and
    of the close has its own limit, so the exit cannot hang."""
    if _CAMERA_GROUP_MANAGER is None or not _CAMERA_GROUP_MANAGER.camera_groups:
        return
    try:
        await _CAMERA_GROUP_MANAGER.close_all_camera_groups()
    except Exception as error:
        logger.exception(f"The camera groups could not close before the exit: {error!r}")


def get_or_create_camera_group_manager(app: FastAPI) -> CameraGroupManager:
    """Create the singleton CameraGroupManager instance."""
    global _CAMERA_GROUP_MANAGER

    if _CAMERA_GROUP_MANAGER is not None:
        return _CAMERA_GROUP_MANAGER

    _CAMERA_GROUP_MANAGER = CameraGroupManager(
        global_kill_flag=app.state.global_kill_flag,
        worker_registry=app.state.worker_registry,
        restore_store=restore_files.default_folder(),  # 4.7.1: only the server of the app keeps restore files
    )
    return _CAMERA_GROUP_MANAGER
