"""The request log of the app (`skellycam/api/middleware/add_middleware.py`). Third review of the connection
fixes, S12: an expected refusal (4xx, for example 409 "No recording runs") is one WARNING line with no
traceback; a server error (5xx) stays ERROR with its traceback."""

import logging

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from skellycam.api.middleware.add_middleware import add_middleware


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(logging.Logger, "api", logging.Logger.info, raising=False)  # a level of the app logger
    app = FastAPI()
    add_middleware(app)

    @app.get("/refused")
    async def refused():
        raise HTTPException(status_code=409, detail="No recording runs")

    @app.get("/broken")
    async def broken():
        raise HTTPException(status_code=500, detail="test: it broke")

    return TestClient(app)


def records_of(caplog):
    return [r for r in caplog.records if r.name == "skellycam.api.middleware.add_middleware"]


def test_a_refusal_is_one_warning_line_with_no_traceback(client, caplog):
    with caplog.at_level(logging.DEBUG):
        assert client.get("/refused").status_code == 409
    records = records_of(caplog)
    assert [r for r in records if r.levelno >= logging.ERROR] == []
    assert all(r.exc_info is None and "\n" not in r.getMessage() for r in records if r.levelno >= logging.WARNING)
    warnings = [r for r in records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and "No recording runs" in warnings[0].getMessage(), [r.getMessage() for r in warnings]


def test_a_server_error_stays_an_error_with_its_traceback(client, caplog):
    with caplog.at_level(logging.DEBUG):
        assert client.get("/broken").status_code == 500
    assert any(r.levelno == logging.ERROR and r.exc_info for r in records_of(caplog))


def test_a_requested_shutdown_is_logged_at_info(caplog):
    """Round 4, item 5: the child monitor logs a requested shutdown (the global kill flag, no worker death) at
    INFO, not ERROR."""
    import multiprocessing
    import time
    from unittest.mock import patch

    from skellycam.core.ipc.process_management.managed_worker import WorkerMode
    from skellycam.core.ipc.process_management.worker_registry import WorkerRegistry

    registry = WorkerRegistry(global_kill_flag=multiprocessing.Value("b", True), worker_mode=WorkerMode.THREAD)
    kill = "skellycam.core.ipc.process_management.worker_registry.signal.raise_signal"  # sfn26: not os.kill
    with caplog.at_level(logging.DEBUG), patch(kill) as terminate_server:
        registry.start_heartbeat()
        try:
            deadline = time.monotonic() + 5
            while not terminate_server.called and time.monotonic() < deadline:
                time.sleep(0.01)
        finally:
            registry.shutdown_all()
    assert terminate_server.called
    lines = [r for r in caplog.records if "Application shutdown requested" in r.getMessage()]
    assert lines and all(r.levelno == logging.INFO for r in lines), [(r.levelname, r.getMessage()) for r in lines]
