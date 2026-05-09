"""
Shared test fixtures for the skellycam test suite.

Builds a lightweight FastAPI app with the same routes as the real app
but WITHOUT the heavy lifespan (bytecode compilation, logging setup, etc).

Time-consuming tests are marked ``@pytest.mark.slow`` (see ``pyproject.toml``);
run ``pytest -m "not slow"`` for a faster local loop.
"""
import multiprocessing
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import skellycam
from skellycam.api.http.app.health import health_router
from skellycam.api.http.app.shutdown import shutdown_router
from skellycam.api.routers import SKELLYCAM_ROUTERS
from skellycam.core.camera_group.camera_group_manager import CameraGroupManager
from skellycam.core.ipc.process_management.managed_worker import WorkerMode
from skellycam.core.ipc.process_management.worker_registry import WorkerRegistry


# ---------------------------------------------------------------------------
# Core mocks
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_global_kill_flag():
    """A real multiprocessing.Value used as the global kill flag."""
    return multiprocessing.Value("b", False)


@pytest.fixture()
def mock_worker_registry(mock_global_kill_flag):
    """Real WorkerRegistry (THREAD mode, heartbeat not started) for type-checked APIs/tests."""
    return WorkerRegistry(
        global_kill_flag=mock_global_kill_flag,
        worker_mode=WorkerMode.THREAD,
    )


@pytest.fixture()
def mock_camera_group_manager(mock_global_kill_flag, mock_worker_registry):
    """
    Real CameraGroupManager with recording/group methods stubbed as AsyncMocks.

    Must be a true ``CameraGroupManager`` instance so beartype-validated code
    (e.g. ``WebsocketServer``) accepts ``get_or_create_camera_group_manager`` results.
    """
    mgr = CameraGroupManager(
        global_kill_flag=mock_global_kill_flag,
        worker_registry=mock_worker_registry,
    )
    mgr.create_or_update_camera_group = AsyncMock()
    mgr.create_and_start_camera_group = AsyncMock()
    mgr.start_recording_all_groups = AsyncMock()

    _stats_dtype = np.dtype(
        [
            ("median_value", np.float64),
            ("mean_value", np.float64),
            ("standard_deviation_value", np.float64),
            ("min_value", np.float64),
            ("max_value", np.float64),
        ]
    )

    def _mock_stats_recarray(mean: float = 30.0) -> np.recarray:
        """Structured scalar as recarray so ``stop_recording._stats_summary`` beartype checks pass."""
        return np.array((mean, mean, 1.0, mean - 2.0, mean + 2.0), dtype=_stats_dtype).view(np.recarray)

    mock_recording_info = MagicMock()
    mock_recording_info.recording_name = "test_recording"
    mock_recording_info.full_recording_path = "/tmp/test_recording"

    mock_timestamp_stats = MagicMock()
    mock_timestamp_stats.number_of_cameras = 1
    mock_timestamp_stats.number_of_frames = 100
    mock_timestamp_stats.total_duration_sec = 10.0
    mock_timestamp_stats.framerate_stats = _mock_stats_recarray(30.0)
    mock_timestamp_stats.frame_duration_stats = _mock_stats_recarray(33.3)
    mock_timestamp_stats.inter_camera_grab_range_ms = _mock_stats_recarray(2.0)

    mgr.stop_recording_all_groups = AsyncMock(return_value=[(mock_recording_info, mock_timestamp_stats)])
    mgr.close_all_camera_groups = AsyncMock()
    mgr.pause_unpause_all_groups = AsyncMock()
    mgr.pause_all_groups = AsyncMock()
    mgr.unpause_all_groups = AsyncMock()

    return mgr


# ---------------------------------------------------------------------------
# FastAPI app + TestClient (lightweight — no lifespan)
# ---------------------------------------------------------------------------

@pytest.fixture()
def app(mock_global_kill_flag, mock_worker_registry, mock_camera_group_manager):
    """
    A lightweight FastAPI app with the same routes but no heavy lifespan.

    Patches `get_or_create_camera_group_manager` at every import site
    so all endpoints use the mock.
    """
    with patch(
        "skellycam.api.http.cameras.camera_router.get_or_create_camera_group_manager",
        return_value=mock_camera_group_manager,
    ), patch(
        "skellycam.api.websocket.websocket_server.get_or_create_camera_group_manager",
        return_value=mock_camera_group_manager,
    ), patch(
        "skellycam.api.websocket.websocket_server.WebsocketServer._logs_relay",
        new_callable=AsyncMock,
    ):
        test_app = FastAPI()
        test_app.state.global_kill_flag = mock_global_kill_flag
        test_app.state.worker_registry = mock_worker_registry

        # Register the same routes as the real app
        for router in [health_router, shutdown_router]:
            test_app.include_router(router)

        prefix = f"/{skellycam.__package_name__}"
        for router in SKELLYCAM_ROUTERS:
            test_app.include_router(router, prefix=prefix)

        yield test_app


@pytest.fixture()
def client(app):
    """Synchronous TestClient for HTTP endpoint tests."""
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
