"""Run rules of the capture tests (specs/windows-capture.md, section 16.1).

- `camera_hardware`: skipped unless `SKELLYCAM_HARDWARE=1`. The user gives the word.
- `capture_local`: the Windows development machine only; the CI jobs leave it out (section 15).
- `gate_amendment`: the failing tests of the proposed gate rule (specs/windows-capture-gate-amendment.md).
  They are deselected unless `SKELLYCAM_GATE_AMENDMENT=1`, also when the command line gives its own `-m`.

The markers are registered in `pyproject.toml`.
"""

import os

import pytest

HARDWARE = os.environ.get("SKELLYCAM_HARDWARE", "") == "1"
GATE_AMENDMENT = os.environ.get("SKELLYCAM_GATE_AMENDMENT", "") == "1"


def pytest_collection_modifyitems(config, items):
    if not GATE_AMENDMENT:
        proposed = [item for item in items if "gate_amendment" in item.keywords]
        if proposed:
            config.hook.pytest_deselected(items=proposed)
            items[:] = [item for item in items if "gate_amendment" not in item.keywords]
    if HARDWARE:
        return
    skip = pytest.mark.skip(reason="hardware test: runs only with SKELLYCAM_HARDWARE=1 (spec 16.1)")
    for item in items:
        if "camera_hardware" in item.keywords:
            item.add_marker(skip)
