"""Run rules of the capture tests (specs/windows-capture.md, section 16.1).

- `camera_hardware`: skipped unless `SKELLYCAM_HARDWARE=1`. The user gives the word.
- `capture_local`: the Windows development machine only; the CI jobs leave it out (section 15).

The markers are registered in `pyproject.toml`.
"""

import os

import pytest

HARDWARE = os.environ.get("SKELLYCAM_HARDWARE", "") == "1"


def pytest_collection_modifyitems(config, items):
    if HARDWARE:
        return
    skip = pytest.mark.skip(reason="hardware test: runs only with SKELLYCAM_HARDWARE=1 (spec 16.1)")
    for item in items:
        if "camera_hardware" in item.keywords:
            item.add_marker(skip)
