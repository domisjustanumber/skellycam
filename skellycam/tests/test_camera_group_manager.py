"""Tests for CameraGroupManager logic (without real cameras)."""
import multiprocessing
from unittest.mock import patch

import pytest

from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera_group.camera_group_manager import (
    CameraGroupManager,
    _matched_camera_ids_from_partials,
    get_or_create_camera_group_manager,
)


def _cfg(camera_id: str, camera_index: int) -> CameraConfig:
    return CameraConfig(camera_id=camera_id, camera_index=camera_index, camera_name=f"cam-{camera_id}")
from skellycam.core.ipc.process_management.managed_worker import WorkerMode
from skellycam.core.ipc.process_management.worker_registry import WorkerRegistry


@pytest.fixture()
def kill_flag():
    return multiprocessing.Value("b", False)


@pytest.fixture()
def worker_registry(kill_flag):
    return WorkerRegistry(global_kill_flag=kill_flag, worker_mode=WorkerMode.THREAD)


@pytest.fixture()
def manager(kill_flag, worker_registry):
    return CameraGroupManager(
        global_kill_flag=kill_flag,
        worker_registry=worker_registry,
    )


class TestCameraGroupManagerInit:
    def test_starts_empty(self, manager):
        """New manager has no camera groups."""
        assert manager.camera_groups == {}
        assert manager.closing is False

    def test_get_nonexistent_group_raises(self, manager):
        """Requesting a nonexistent group raises ValueError."""
        with pytest.raises(ValueError, match="does not exist"):
            manager.get_camera_group("nonexistent-id")

    @pytest.mark.asyncio
    async def test_close_empty_groups(self, manager):
        """Closing with no groups should not raise."""
        await manager.close_all_camera_groups()
        assert manager.camera_groups == {}

    def test_to_state_dict_empty(self, manager):
        """State dict with no groups returns expected structure."""
        state = manager.to_state_dict()
        assert isinstance(state, dict)


class TestMatchedCameraIdsFromPartials:
    """Guards apply routing: expanding selection must not match as a mere settings update."""

    def test_unions_keys_across_groups(self):
        partial = {
            "g1": {"cam_a": _cfg("cam_a", 0)},
            "g2": {"cam_b": _cfg("cam_b", 1)},
        }
        assert _matched_camera_ids_from_partials(partial) == frozenset({"cam_a", "cam_b"})

    def test_expanding_second_camera_not_in_group_yields_strict_subset(self):
        """Simulates one live group with cam_a only; user applies cam_a + cam_b."""
        partial = {"g1": {"cam_a": _cfg("cam_a", 0)}}
        requested = frozenset({"cam_a", "cam_b"})
        assert _matched_camera_ids_from_partials(partial) != requested


class TestSingletonFactory:
    def test_returns_same_instance(self, kill_flag, worker_registry):
        """get_or_create_camera_group_manager returns the same instance on repeated calls."""
        # We need to reset the module-level singleton before testing
        with patch(
            "skellycam.core.camera_group.camera_group_manager._CAMERA_GROUP_MANAGER",
            None,
        ):
            from fastapi import FastAPI
            app = FastAPI()
            app.state.global_kill_flag = kill_flag
            app.state.worker_registry = worker_registry

            first = get_or_create_camera_group_manager(app)
            second = get_or_create_camera_group_manager(app)
            assert first is second
