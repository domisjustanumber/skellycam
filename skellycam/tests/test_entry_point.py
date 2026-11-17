"""The standalone entry point must configure logging before it starts the server: the app calls logger.api /
logger.success, which exist only after skellylogs.configure_logging has run."""
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
    monkeypatch.setattr(default_paths, "get_log_file_path", lambda: "fake.log")
    monkeypatch.setattr(skellycam_main.asyncio, "run", fake_run)
    monkeypatch.setattr(skellycam_main.os, "_exit", lambda code: None)

    skellycam_main.entry_point()

    assert calls == [("logging", {"level": skellycam_main_log_level(), "log_file_path": "fake.log"}), "server"]


def skellycam_main_log_level():
    import skellycam

    return skellycam.LOG_LEVEL
