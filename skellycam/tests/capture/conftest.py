"""Run rules of the capture tests (specs/windows-capture.md, section 16.1).

- `camera_hardware`: skipped unless `SKELLYCAM_HARDWARE=1`. The user gives the word.
- `capture_local`: the Windows development machine only; the CI jobs leave it out (section 15).

The markers are registered in `pyproject.toml`.
"""

import os

import pytest

HARDWARE = os.environ.get("SKELLYCAM_HARDWARE", "") == "1"


@pytest.fixture
def no_camera_auto_exposure(monkeypatch):
    """T-REQ-15 (specs/camera-requests.md 1.1, 1.3 item 7): a spy on `set_controls` of each fake. No exposure set
    has `auto=True`, except the restore at the close (unix-capture.md 4.7) [K4]."""
    import threading

    from skellycam.tests.capture.fake_source import FakeSource

    seen, in_close = [], threading.local()
    set_controls, close = FakeSource.set_controls, FakeSource.close

    def spy_set(source, changes):
        setting = changes.get("exposure")
        if setting is not None and setting.auto and not getattr(in_close, "on", False):
            seen.append((source.camera_id, setting))
        return set_controls(source, changes)

    def spy_close(source, restore=True):
        in_close.on = True
        try:
            return close(source, restore)
        finally:
            in_close.on = False

    monkeypatch.setattr(FakeSource, "set_controls", spy_set)
    monkeypatch.setattr(FakeSource, "close", spy_close)
    yield seen
    assert not seen, f"an exposure set with auto=True outside the close restore: {seen}"


def pytest_collection_modifyitems(config, items):
    if HARDWARE:
        return
    skip = pytest.mark.skip(reason="hardware test: runs only with SKELLYCAM_HARDWARE=1 (spec 16.1)")
    for item in items:
        if "camera_hardware" in item.keywords:
            item.add_marker(skip)
