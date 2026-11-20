import logging
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel, Field, StrictBool

from skellycam.core.camera.config.camera_config import CameraConfig, DEFAULT_CAMERA_ID, CameraConfigs
from skellycam.core.camera_group.camera_group import RequestRefused
from skellycam.core.camera_group.camera_group_manager import get_or_create_camera_group_manager
from skellycam.core.device_detection.detect_cameras_devices import CameraDeviceInfo, detect_available_cameras
from skellycam.core.device_detection.detect_microphone_devices import get_available_microphones
from skellycam.core.recorders.videos.recording_info import RecordingInfo
from skellycam.core.types.type_overloads import CameraIdString, CameraGroupIdString, CameraBackendInt
from skellycam.system.default_paths import default_recording_name, get_default_recording_folder_path

logger = logging.getLogger(__name__)

camera_router = APIRouter(prefix="/camera", tags=["Cameras"])


class CameraGroupCreateRequest(BaseModel):
    camera_configs: dict[CameraIdString, CameraConfig]

    @classmethod
    def example(cls) -> "CameraGroupCreateRequest":
        return cls(camera_configs={DEFAULT_CAMERA_ID: CameraConfig()})


class CameraUpdateRequest(BaseModel):
    camera_configs: CameraConfigs

    @classmethod
    def example(cls) -> "CameraUpdateRequest":
        return cls(camera_configs={DEFAULT_CAMERA_ID: CameraConfig(exposure=-8)})


class StartRecordingRequest(BaseModel):
    recording_name: str = Field(
        default_factory=default_recording_name,
        description="Name of the recording"
    )
    recording_directory: str = Field(
        default_factory=get_default_recording_folder_path,
        description="Path to save the recording"
    )
    mic_device_index: int = Field(
        default=-1,
        description="Index of the microphone device"
    )

    def recording_full_path(self) -> str:
        return str(Path(self.recording_directory) / self.recording_name)


class CreateCameraGroupResponse(BaseModel):
    group_id: CameraGroupIdString
    camera_configs: CameraConfigs
    camera_failures: dict[CameraIdString, dict] = Field(default_factory=dict)  # spec 8.4, section 12
    warnings: list[dict] = Field(default_factory=list)  # spec 11.3


class StartRecordingResponse(BaseModel):
    started: bool
    warnings: list[dict]  # spec 11.3


class DetectedCamerasResponse(BaseModel):
    cameras: list[CameraDeviceInfo]


class DetectedMicrophonesResponse(BaseModel):
    microphones: dict[int, str]


class StatsSummary(BaseModel):
    median: float
    mean: float
    std: float
    min: float
    max: float


class StopRecordingResponse(BaseModel):
    recording_name: str
    recording_path: str
    number_of_cameras: int
    number_of_frames: int
    total_duration_sec: float
    mean_framerate: float
    mean_inter_camera_sync_ms: float
    framerate_stats: StatsSummary
    frame_duration_stats: StatsSummary
    inter_camera_grab_range_ms_stats: StatsSummary


@camera_router.post("/detect", summary="Detect available camera devices")
def cameras_detect_endpoint(
        request: Request,
        filter_virtual: bool = True,
        backend_id: CameraBackendInt | None = None
) -> DetectedCamerasResponse:
    try:
        cameras = detect_available_cameras(backend_id=backend_id, filter_virtual=filter_virtual)
        # The last detection result, for the whole-request check of the apply request (7.1, U17)
        get_or_create_camera_group_manager(app=request.app).detected_cameras = {
            camera.camera_id: camera for camera in cameras}
        return DetectedCamerasResponse(cameras=cameras)
    except Exception as e:
        logger.error(f"Error in {request.url}: {type(e).__name__} - {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@camera_router.get("/microphone/detect", summary="Detect available microphone devices")
def microphone_detect_endpoint(request: Request) -> DetectedMicrophonesResponse:
    try:
        microphones = get_available_microphones()
        return DetectedMicrophonesResponse(microphones=microphones)
    except Exception as e:
        logger.error(f"Error in {request.url}: {type(e).__name__} - {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@camera_router.post("/group/apply", summary="Create/update camera group")
async def camera_group_apply_post_endpoint(
        request: Request,
        request_body: CameraGroupCreateRequest = Body(..., examples=[CameraGroupCreateRequest.example()])
) -> CreateCameraGroupResponse:
    try:
        raw_body = await request.body()
        logger.info(f"Request to {request.url}: {raw_body.decode('utf-8')}")

        configs = request_body.camera_configs
        camera_group, failures, warnings = await get_or_create_camera_group_manager(
            app=request.app).create_or_update_camera_group(camera_configs=configs)

        return CreateCameraGroupResponse(
            group_id=camera_group.id,
            camera_configs=camera_group.configs,
            camera_failures=failures,
            warnings=warnings,
        )
    except RequestRefused as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except Exception as e:
        logger.error(f"Error in {request.url}: {type(e).__name__} - {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@camera_router.post("/group/all/record/start", summary="Start recording")
async def start_recording(
        request: Request,
        request_body: StartRecordingRequest = Body(..., examples=[StartRecordingRequest()])
) -> StartRecordingResponse:
    try:
        if request_body.recording_directory.startswith("~"):
            request_body.recording_directory = str(
                Path(request_body.recording_directory.replace("~", str(Path.home()), 1))
            )

        Path(request_body.recording_directory).mkdir(parents=True, exist_ok=True)
        warnings = await get_or_create_camera_group_manager(app=request.app).start_recording_all_groups(
            RecordingInfo(**request_body.model_dump()))

        return StartRecordingResponse(started=True, warnings=warnings)
    except RequestRefused as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except Exception as e:
        logger.error(f"Error in {request.url}: {type(e).__name__} - {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@camera_router.post("/group/all/record/stop", summary="Stop recording")
async def stop_recording(request: Request) -> list[StopRecordingResponse]:
    try:
        summaries = await get_or_create_camera_group_manager(app=request.app).stop_recording_all_groups()
        # Each field comes from the timing sidecars of the take (recorder.md 8.2) [R5].
        return [StopRecordingResponse(**summary.stop_response) for summary in summaries]
    except RequestRefused as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except Exception as e:
        logger.error(f"Error in {request.url}: {type(e).__name__} - {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@camera_router.delete("/group/close/all", summary="Close all camera groups")
async def close_all_camera_groups(request: Request) -> bool:
    try:
        await get_or_create_camera_group_manager(app=request.app).close_all_camera_groups()
        return True
    except Exception as e:
        logger.error(f"Error in {request.url}: {type(e).__name__} - {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class CameraPauseState(BaseModel):
    paused: StrictBool


@camera_router.put("/group/all/pause", summary="Set camera pause state")
async def pause_camera_groups(request: Request, desired: CameraPauseState) -> CameraPauseState:
    try:
        await get_or_create_camera_group_manager(app=request.app).set_paused_all_groups(paused=desired.paused)
        return desired
    except Exception as e:
        logger.error(f"Error in {request.url}: {type(e).__name__} - {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
