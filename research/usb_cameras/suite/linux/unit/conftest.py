"""Linux suite unit tests: put suite/, suite/linux and suite/linux/linuxlib on sys.path (as the runner does) and
provide a fake sysfs tree (fakesysfs.py). No camera, no root; Linux or WSL/Docker (sysfs layout needs symlinks)."""
import os
import sys
from pathlib import Path

import pytest

UNIT = Path(__file__).resolve().parent
LINUX = UNIT.parent
SUITE = LINUX.parent
for p in (str(SUITE), str(LINUX), str(LINUX / "linuxlib"), str(UNIT), str(SUITE / "common" / "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

import fakesysfs  # noqa: E402


@pytest.fixture
def fake_root(tmp_path, monkeypatch):
    """Gerald-like fake tree, idle cameras."""
    fakesysfs.build(tmp_path)
    monkeypatch.setenv("SKELLYCAM_LINUX_ROOT", str(tmp_path))
    return tmp_path


@pytest.fixture
def fake_root_streaming(tmp_path, monkeypatch):
    """Same tree with the C922 streaming at alt 9 (its VS interface bAlternateSetting = 9)."""
    fakesysfs.build(tmp_path, streaming={"c922": 9})
    monkeypatch.setenv("SKELLYCAM_LINUX_ROOT", str(tmp_path))
    return tmp_path


def pytest_collection_modifyitems(config, items):
    if not sys.platform.startswith("linux"):
        skip = pytest.mark.skip(reason="fake sysfs needs Linux symlink semantics (run in WSL or Docker)")
        for it in items:
            if "linux_only" in it.keywords:
                it.add_marker(skip)


def pytest_configure(config):
    config.addinivalue_line("markers", "linux_only: needs Linux (symlinks, fcntl)")
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
