"""Tests for the shutdown endpoint."""
from unittest.mock import patch
import logging


class TestShutdownEndpoint:
    def test_shutdown_returns_json(self, client, mock_global_kill_flag, monkeypatch):
        """GET /shutdown triggers shutdown and returns JSON response."""
        monkeypatch.setattr(logging.Logger, "api", logging.Logger.info, raising=False)
        with patch("os.kill") as mock_kill:
            response = client.get("/shutdown")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "shutdown_initiated"
        assert "message" in data
        assert mock_global_kill_flag.value
        # The worker monitor owns final termination after saves complete.
        mock_kill.assert_not_called()


async def test_the_lifespan_end_waits_for_the_close_of_the_shutdown_endpoint(monkeypatch, tmp_path):
    """Fix lane B: the lifespan end (also Ctrl-C) starts no close while the background close of `/shutdown`
    runs; it waits for that close first."""
    import asyncio
    import multiprocessing
    from unittest.mock import Mock

    from fastapi import FastAPI

    import skellycam.app as app_module

    events = []

    async def endpoint_close():
        await asyncio.sleep(0.2)
        events.append("endpoint close ends")

    async def lifespan_close():
        events.append("lifespan close")

    for name in ("ensure_bytecode_compiled", "initialize_telemetry", "shutdown_telemetry"):
        monkeypatch.setattr(app_module, name, lambda: None)
    monkeypatch.setattr(app_module, "get_default_skellycam_base_folder_path", lambda: tmp_path)
    monkeypatch.setattr(app_module, "close_camera_groups_before_exit", lifespan_close)
    monkeypatch.setattr(app_module, "logger", Mock())
    app = FastAPI()
    app.state.global_kill_flag = multiprocessing.Value("b", False)
    async with app_module.app_lifespan(app):
        app.state.shutdown_task = asyncio.create_task(endpoint_close())
    assert events == ["endpoint close ends", "lifespan close"]
    assert app.state.global_kill_flag.value
