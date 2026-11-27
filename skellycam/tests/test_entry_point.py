"""The standalone entry point must configure logging before it starts the server: the app calls logger.api /
logger.success, which exist only after skellylogs.configure_logging has run. Then it cancels the join of the feeder
thread of the websocket log queue (recorder.md 9.1 item 4 [ADR-06PW])."""
from unittest.mock import Mock

import skellylogs

import skellycam.__main__ as skellycam_main
import skellycam.system.default_paths as default_paths


def test_entry_point_configures_logging_before_the_server_starts(monkeypatch):
    calls = []

    def fake_run(coroutine):
        coroutine.close()
        calls.append("server")

    # fakes: the real configure_logging starts a queue thread that outlives the test session
    monkeypatch.setattr(skellylogs, "configure_logging", lambda **kwargs: calls.append(("logging", kwargs)))
    log_queue = Mock(cancel_join_thread=lambda: calls.append("no join of the log queue"))
    monkeypatch.setattr(skellylogs, "get_websocket_log_queue", lambda: log_queue)
    monkeypatch.setattr(default_paths, "get_log_file_path", lambda: "fake.log")
    monkeypatch.setattr(skellycam_main.asyncio, "run", fake_run)
    monkeypatch.setattr(skellycam_main.os, "_exit", lambda code: None)

    skellycam_main.entry_point()

    assert calls == [("logging", {"level": skellycam_main_log_level(), "log_file_path": "fake.log"}),
                     "no join of the log queue", "server"]


def skellycam_main_log_level():
    import skellycam

    return skellycam.LOG_LEVEL
