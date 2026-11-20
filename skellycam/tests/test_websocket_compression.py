"""The server turns off websocket compression (answer A9 of ADR-G651, evidence ADR-HDC9): a JPEG does not
compress, and permessage-deflate cost 12.7 ms of the event loop for each 1080p frame."""
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import uvicorn

import skellycam.__main__ as skellycam_main
import skellycam.app as skellycam_app
import skellycam.core.ipc.process_management.worker_registry as worker_registry_module
import skellycam.utilities.wait_functions as wait_functions


def test_server_config_turns_off_permessage_deflate(monkeypatch):
    configs = []

    class FakeServer:
        should_exit = False

        def __init__(self, config):
            configs.append(config)

        async def serve(self):
            pass

    async def no_wait():
        pass

    # fakes: no worker processes, no app, no socket; main() only builds the config and returns
    monkeypatch.setattr(worker_registry_module, "WorkerRegistry", lambda **kwargs: MagicMock())
    monkeypatch.setattr(skellycam_app, "create_fastapi_app", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr(uvicorn, "Server", FakeServer)
    monkeypatch.setattr(wait_functions, "await_1s", no_wait)
    monkeypatch.setattr(skellycam_main.signal, "signal", lambda *args: None)
    monkeypatch.setattr(skellycam_main, "logger", MagicMock())

    asyncio.run(skellycam_main.main())

    assert len(configs) == 1
    assert configs[0].ws_per_message_deflate is False
