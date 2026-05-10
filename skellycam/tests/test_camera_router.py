"""Tests for the camera router endpoints."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from skellycam.core.camera.config.camera_config import CameraConfig, DEFAULT_CAMERA_ID
from skellycam.core.camera.openpnp_capture import OpenPnPFormatInfo
from skellycam.core.camera_group.usb_bandwidth import (
    USB_BANDWIDTH_ERROR_CODE,
    USB_BANDWIDTH_USER_GUIDANCE,
    UsbBandwidthContentionError,
)
from skellycam.core.device_detection.detect_cameras_devices import CameraDeviceInfo


class TestDetectCameras:
    def test_detect_cameras_returns_list(self, client):
        """POST /skellycam/camera/detect returns detected cameras."""
        mock_camera = CameraDeviceInfo(
            index=0,
            name="Test Camera",
            unique_id="usb-test-000",
            available_formats=[
                OpenPnPFormatInfo(
                    format_id=0,
                    width=640,
                    height=480,
                    fps=30.0,
                    fourcc_str="MJPG",
                    bpp=24,
                )
            ],
        )

        with patch(
            "skellycam.api.http.cameras.camera_router.detect_available_cameras",
            return_value=[mock_camera],
        ):
            response = client.post("/skellycam/camera/detect")
        assert response.status_code == 200
        data = response.json()
        assert "cameras" in data
        assert len(data["cameras"]) == 1

    def test_detect_cameras_empty(self, client):
        """POST /skellycam/camera/detect returns empty list when no cameras."""
        with patch(
            "skellycam.api.http.cameras.camera_router.detect_available_cameras",
            return_value=[],
        ):
            response = client.post("/skellycam/camera/detect")
        assert response.status_code == 200
        data = response.json()
        assert data["cameras"] == []

    def test_detect_request_body_maps_skip_listed_virtual_flag(self, client):
        """CamelCase JSON skipListedVirtualResolutionInterrogation reaches detect_available_cameras."""
        with patch(
            "skellycam.api.http.cameras.camera_router.detect_available_cameras",
            return_value=[],
        ) as mock_detect:
            response = client.post(
                "/skellycam/camera/detect",
                json={"skipListedVirtualResolutionInterrogation": True},
            )
        assert response.status_code == 200
        mock_detect.assert_called_once()
        assert (
            mock_detect.call_args.kwargs["skip_listed_virtual_resolution_interrogation"]
            is True
        )

    def test_detect_cameras_error(self, client):
        """POST /skellycam/camera/detect returns 500 on detection error."""
        with patch(
            "skellycam.api.http.cameras.camera_router.detect_available_cameras",
            side_effect=RuntimeError("Camera detection failed"),
        ):
            response = client.post("/skellycam/camera/detect")
        assert response.status_code == 500


class TestCameraGroupApply:
    def test_apply_creates_group(self, client, mock_camera_group_manager):
        """POST /skellycam/camera/group/apply creates a camera group."""
        mock_group = MagicMock()
        mock_group.id = "group-0"
        mock_group.configs = {DEFAULT_CAMERA_ID: CameraConfig()}
        mock_camera_group_manager.create_or_update_camera_group = AsyncMock(
            return_value=mock_group
        )

        response = client.post(
            "/skellycam/camera/group/apply",
            json={"camera_configs": {DEFAULT_CAMERA_ID: CameraConfig().model_dump()}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["group_id"] == "group-0"
        assert DEFAULT_CAMERA_ID in data["camera_configs"]

    def test_apply_error(self, client, mock_camera_group_manager):
        """POST /skellycam/camera/group/apply returns 500 on error."""
        mock_camera_group_manager.create_or_update_camera_group = AsyncMock(
            side_effect=RuntimeError("Something went wrong")
        )
        response = client.post(
            "/skellycam/camera/group/apply",
            json={"camera_configs": {DEFAULT_CAMERA_ID: CameraConfig().model_dump()}},
        )
        assert response.status_code == 500

    def test_apply_returns_409_with_structured_detail_on_usb_contention(
        self, client, mock_camera_group_manager
    ):
        """A USB bandwidth failure must return HTTP 409 with a structured ``detail``.

        freemocap (and the UI) rely on a stable ``error_code`` and a human-readable
        ``message`` / ``user_guidance`` so they can react without parsing the message.
        """
        mock_camera_group_manager.create_or_update_camera_group = AsyncMock(
            side_effect=UsbBandwidthContentionError(
                "Camera xyz never delivered a first frame while 1 other camera(s) were also starting."
            )
        )
        response = client.post(
            "/skellycam/camera/group/apply",
            json={"camera_configs": {DEFAULT_CAMERA_ID: CameraConfig().model_dump()}},
        )
        assert response.status_code == 409
        body = response.json()
        assert isinstance(body["detail"], dict)
        assert body["detail"]["error_code"] == USB_BANDWIDTH_ERROR_CODE
        assert "first frame" in body["detail"]["message"]
        assert body["detail"]["user_guidance"] == USB_BANDWIDTH_USER_GUIDANCE


class TestRecording:
    def test_start_recording(self, client, mock_camera_group_manager):
        """POST /skellycam/camera/group/all/record/start returns true."""
        response = client.post(
            "/skellycam/camera/group/all/record/start",
            json={},
        )
        assert response.status_code == 200
        assert response.json() is True

    def test_stop_recording(self, client, mock_camera_group_manager):
        """GET /skellycam/camera/group/all/record/stop returns list of StopRecordingResponse."""
        response = client.get("/skellycam/camera/group/all/record/stop")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["recording_name"] == "test_recording"
        assert data[0]["number_of_cameras"] == 1
        assert data[0]["number_of_frames"] == 100


class TestCameraGroupManagement:
    def test_close_all(self, client, mock_camera_group_manager):
        """DELETE /skellycam/camera/group/close/all returns true."""
        response = client.request("DELETE", "/skellycam/camera/group/close/all")
        assert response.status_code == 200
        assert response.json() is True

    def test_pause_unpause(self, client, mock_camera_group_manager):
        """GET /skellycam/camera/group/all/pause_unpause returns true."""
        response = client.get("/skellycam/camera/group/all/pause_unpause")
        assert response.status_code == 200
        assert response.json() is True
