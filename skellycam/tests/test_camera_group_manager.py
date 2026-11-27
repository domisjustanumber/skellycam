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
        assert manager.closing == 0  # the count of the closes that run (recorder.md 9.1 item 7)

    def test_get_nonexistent_group_raises(self, manager):
        """Requesting a nonexistent group raises ValueError."""
        with pytest.raises(ValueError, match="does not exist"):
            manager.get_camera_group("nonexistent-id")

    @pytest.mark.asyncio
    async def test_close_empty_groups(self, manager):
        """Closing with no groups should not raise."""
        await manager.close_all_camera_groups()
        assert manager.camera_groups == {}
        assert manager.closing == 0  # sfn26: a close with no group must not stop the payloads

    def test_to_state_dict_empty(self, manager):
        """State dict with no groups returns expected structure."""
        state = manager.to_state_dict()
        assert isinstance(state, dict)


class TestExposureClamp:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(("mode", "requested", "sent"), [("MANUAL", -4, -5), ("MANUAL", -1, -5), ("MANUAL", -5, -5),
                                                             ("MANUAL", -9, -9), ("AUTO", -4, -4)])
    async def test_a_manual_exposure_above_minus_5_is_clamped(self, manager, monkeypatch, mode, requested, sent):
        """sfn26 43e2b968a: a MANUAL exposure above -5 becomes -5 (-4 gives about 16 fps on the Logitech
        cameras, so the rate check fails). A stored UI setting of -4 still opens the camera."""
        from unittest.mock import AsyncMock, Mock

        from skellycam.core.camera.config.camera_config import CameraConfig
        from skellycam.core.camera_group.camera_group import CameraGroup

        config = CameraConfig(camera_id="c1", camera_index=0, exposure_mode=mode, exposure=requested)
        manager.detected_cameras = {"c1": Mock(virtual=False)}
        monkeypatch.setattr(manager, "_check_request", lambda camera_configs, camera_group: ([], True))
        start = AsyncMock(return_value=(Mock(spec=CameraGroup, configs={"c1": config}), {}))
        monkeypatch.setattr(manager, "_create_and_start", start)
        await manager.create_or_update_camera_group({"c1": config})
        assert start.await_args.args[0]["c1"].exposure == sent


class TestCloseAll:
    @pytest.mark.asyncio
    async def test_a_close_that_raises_keeps_the_payloads_on_and_the_failed_group_listed(self, manager):
        """sfn26 43e2b968a: each group and its subscription go after their own close; `closing` goes back to
        False also after an error; the group whose close raised stays listed, so that a retry closes it."""
        from unittest.mock import AsyncMock, Mock

        from skellycam.core.camera_group.camera_group import CameraGroup

        good = Mock(spec=CameraGroup, id="g1", camera_ids=[], close=AsyncMock())
        bad = Mock(spec=CameraGroup, id="g2", camera_ids=[],
                   close=AsyncMock(side_effect=RuntimeError("1 camera process(es) could not be killed")))
        manager.camera_groups.update(g1=good, g2=bad)
        manager.camera_group_framerate_subscriptions.update(g1=Mock(), g2=Mock())
        with pytest.raises(RuntimeError, match="could not be killed"):
            await manager.close_all_camera_groups()
        assert manager.closing == 0  # the count of the closes that run (recorder.md 9.1 item 7)
        assert list(manager.camera_groups) == ["g2"]
        assert list(manager.camera_group_framerate_subscriptions) == ["g2"]

    @pytest.mark.asyncio
    async def test_a_good_close_removes_each_group_and_subscription(self, manager):
        from unittest.mock import AsyncMock, Mock

        from skellycam.core.camera_group.camera_group import CameraGroup

        manager.camera_groups.update(g1=Mock(spec=CameraGroup, id="g1", camera_ids=[], close=AsyncMock()))
        manager.camera_group_framerate_subscriptions.update(g1=Mock())
        await manager.close_all_camera_groups()
        assert manager.camera_groups == {} and manager.camera_group_framerate_subscriptions == {}
        assert manager.closing == 0  # the count of the closes that run (recorder.md 9.1 item 7)


    @pytest.mark.asyncio
    async def test_a_group_removed_during_the_close_raises_no_key_error(self, manager):
        """Fix lane A: the teardown of a failed start (or a second close) removes the group first."""
        from unittest.mock import AsyncMock, Mock

        from skellycam.core.camera_group.camera_group import CameraGroup

        async def removed_meanwhile():
            manager.camera_groups.pop("g1")
            manager.camera_groups.pop("g2")

        second = Mock(spec=CameraGroup, id="g2", camera_ids=[], close=AsyncMock())
        manager.camera_groups.update(g1=Mock(spec=CameraGroup, id="g1", camera_ids=[],
                                             close=AsyncMock(side_effect=removed_meanwhile)), g2=second)
        await manager.close_all_camera_groups()
        assert manager.camera_groups == {}
        second.close.assert_not_awaited()


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
