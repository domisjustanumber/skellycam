"""Tests for CameraGroupManager logic (without real cameras)."""
import multiprocessing
from unittest.mock import MagicMock, patch

import pytest

from skellycam.core.ipc.process_management.worker_registry import WorkerRegistry

from skellycam.core.camera_group.camera_group_manager import (
    CameraGroupManager,
    get_or_create_camera_group_manager,
)


@pytest.fixture()
def kill_flag():
    return multiprocessing.Value("b", False)


@pytest.fixture()
def worker_registry():
    reg = MagicMock(spec=WorkerRegistry)
    reg.heartbeat_timestamp = multiprocessing.Value("d", 0.0)
    return reg


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
        assert manager.closing is False  # sfn26: a close with no group must not stop the payloads

    def test_to_state_dict_empty(self, manager):
        """State dict with no groups returns expected structure."""
        state = manager.to_state_dict()
        assert isinstance(state, dict)


class TestCloseAll:
    @pytest.mark.asyncio
    async def test_a_close_that_raises_keeps_the_payloads_on_and_the_failed_group_listed(self, manager):
        """sfn26 43e2b968a: each group and its subscription go after their own close; `closing` goes back to
        False also after an error; the group whose close raised stays listed, so that a retry closes it."""
        from unittest.mock import AsyncMock, Mock

        from skellycam.core.camera_group.camera_group import CameraGroup

        good = Mock(spec=CameraGroup, id="g1", close=AsyncMock())
        bad = Mock(spec=CameraGroup, id="g2",
                   close=AsyncMock(side_effect=RuntimeError("1 camera process(es) could not be killed")))
        manager.camera_groups.update(g1=good, g2=bad)
        manager.camera_group_framerate_subscriptions.update(g1=Mock(), g2=Mock())
        with pytest.raises(RuntimeError, match="could not be killed"):
            await manager.close_all_camera_groups()
        assert manager.closing is False
        assert list(manager.camera_groups) == ["g2"]
        assert list(manager.camera_group_framerate_subscriptions) == ["g2"]

    @pytest.mark.asyncio
    async def test_a_good_close_removes_each_group_and_subscription(self, manager):
        from unittest.mock import AsyncMock, Mock

        from skellycam.core.camera_group.camera_group import CameraGroup

        manager.camera_groups.update(g1=Mock(spec=CameraGroup, id="g1", close=AsyncMock()))
        manager.camera_group_framerate_subscriptions.update(g1=Mock())
        await manager.close_all_camera_groups()
        assert manager.camera_groups == {} and manager.camera_group_framerate_subscriptions == {}
        assert manager.closing is False


class TestSetPaused:
    """PUT /group/all/pause with {paused} sets one state; it does not toggle (port from sfn26)."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("paused", [True, False])
    async def test_each_group_gets_the_state(self, manager, paused):
        from unittest.mock import AsyncMock, Mock

        from skellycam.core.camera_group.camera_group import CameraGroup

        groups = [Mock(spec=CameraGroup, id=name, set_paused=AsyncMock()) for name in ("g1", "g2")]
        manager.camera_groups.update({group.id: group for group in groups})
        await manager.set_paused_all_groups(paused=paused)
        for group in groups:
            group.set_paused.assert_awaited_once_with(paused=paused, await_state_change=True)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("paused", [True, False])
    async def test_the_group_sets_the_state_twice_without_a_toggle(self, paused):
        from unittest.mock import AsyncMock, Mock

        from skellycam.core.camera_group.camera_group import CameraGroup

        group = CameraGroup.__new__(CameraGroup)
        group.cameras = Mock(pause=AsyncMock(), unpause=AsyncMock())
        await group.set_paused(paused=paused)
        await group.set_paused(paused=paused)
        wanted, other = (group.cameras.pause, group.cameras.unpause) if paused else (group.cameras.unpause,
                                                                                       group.cameras.pause)
        assert wanted.await_count == 2
        other.assert_not_awaited()


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
