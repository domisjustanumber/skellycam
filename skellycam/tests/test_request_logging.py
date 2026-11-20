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
    assert any(r.levelno == logging.WARNING and "No recording runs" in r.getMessage() for r in records)


def test_a_server_error_stays_an_error_with_its_traceback(client, caplog):
    with caplog.at_level(logging.DEBUG):
        assert client.get("/broken").status_code == 500
    assert any(r.levelno == logging.ERROR and r.exc_info for r in records_of(caplog))
