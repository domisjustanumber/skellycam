"""The set-up of each certify test: no certify test starts the real Quick Sync check (specs/certify.md 3.6.2, ADR-VTW3
item 15). The row `system:quick-sync` then has the values of a check that works; T-CERT-152 replaces the fake."""

import importlib
from types import SimpleNamespace

import pytest

WORKS = dict(works=True, failure=None, check_ms=1050.0, encode_ms=550.0, exit_code=None)


@pytest.fixture(autouse=True)
def fake_quick_sync_check(monkeypatch):
    encoder = importlib.import_module("skellycam.core.camera.capture.encoder")
    calls = []

    def check(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(**WORKS)

    monkeypatch.setattr(encoder, "check_quick_sync", check)  # a renamed or removed product call fails each test
    return calls
