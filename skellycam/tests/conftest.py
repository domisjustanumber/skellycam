"""
Shared test fixtures for the skellycam test suite.

Builds a lightweight FastAPI app with the same routes as the real app
but WITHOUT the heavy lifespan (bytecode compilation, logging setup, etc).
"""
import multiprocessing
import logging
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import skellycam
from skellycam.api.http.app.health import health_router
from skellycam.api.http.app.shutdown import shutdown_router
from skellycam.api.routers import SKELLYCAM_ROUTERS


# ---------------------------------------------------------------------------
# Core mocks
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_global_kill_flag():
    """A real multiprocessing.Value used as the global kill flag."""
    return multiprocessing.Value("b", False)


@pytest.fixture()
def mock_worker_registry(mock_global_kill_flag):
    """A MagicMock standing in for WorkerRegistry (no real threads/processes)."""
    registry = MagicMock()
    registry.heartbeat_timestamp = multiprocessing.Value("d", 0.0)
    return registry


@pytest.fixture()
def mock_camera_group_manager():
    """
    A MagicMock standing in for CameraGroupManager.

    All async methods are AsyncMock so they can be awaited without error.
    Sync methods return sensible defaults.
    """
    mgr = MagicMock()
    # Async methods
    mgr.create_or_update_camera_group = AsyncMock()
    mgr.create_and_start_camera_group = AsyncMock()
    mgr.start_recording_all_groups = AsyncMock()
    def _stats(mean=30.0):
        return {"median": mean, "mean": mean, "std": 1.0, "min": mean - 2.0, "max": mean + 2.0}

    from skellycam.core.take_recorder import TakeSummary

    stop_response = {"recording_name": "test_recording", "recording_path": "/tmp/test_recording",
                     "number_of_cameras": 1, "number_of_frames": 100, "total_duration_sec": 10.0,
                     "mean_framerate": 30.0, "mean_inter_camera_sync_ms": 2.0, "framerate_stats": _stats(30.0),
                     "frame_duration_stats": _stats(33.3), "inter_camera_grab_range_ms_stats": _stats(2.0)}
    mgr.stop_recording_all_groups = AsyncMock(
        return_value=[TakeSummary(stop_response=stop_response, results=[], warnings=[])])
    mgr.close_all_camera_groups = AsyncMock()
    mgr.set_paused_all_groups = AsyncMock()
    mgr.pause_unpause_all_groups = AsyncMock()
    mgr.pause_all_groups = AsyncMock()
    mgr.unpause_all_groups = AsyncMock()

    # Sync methods
    mgr.get_latest_frontend_payloads = MagicMock(return_value={})
    mgr.get_backend_framerate_updates = MagicMock(return_value={})
    mgr.to_state_dict = MagicMock(return_value={"camera_groups": {}})
    mgr.camera_groups = {}
    return mgr


# ---------------------------------------------------------------------------
# FastAPI app + TestClient (lightweight — no lifespan)
# ---------------------------------------------------------------------------

@pytest.fixture()
def app(mock_global_kill_flag, mock_worker_registry, mock_camera_group_manager, logging_runtime):
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


@pytest.fixture
def logging_runtime(monkeypatch):
    """Supply the normal logging prerequisites without files or global handlers."""
    from skellylogs.configure_logging import _register_custom_levels
    from skellylogs.handlers import websocket_log_queue_handler
    for name in ('loop', 'trace', 'success', 'api'):
        monkeypatch.setattr(logging.Logger, name, getattr(logging.Logger, name, None), raising=False)
    _register_custom_levels()
    queue = multiprocessing.Queue()
    monkeypatch.setattr(websocket_log_queue_handler, 'WEBSOCKET_LOG_QUEUE', queue)
    yield
    queue.close()
    queue.join_thread()
