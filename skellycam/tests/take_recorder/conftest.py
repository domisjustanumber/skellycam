"""Run rules and fixtures of the recorder tests (specs/recorder.md, section 12.1).

- `recorder_bench`: the benchmarks of section 11. Skipped unless `SKELLYCAM_BENCH=1`. Each writes a
  JSON summary to the path in `SKELLYCAM_BENCH_OUT`, outside the repository.
- `recorder_slow`: a test that runs longer than 10 s.

The markers are registered in `pyproject.toml`. The fixtures do not import the product package, so
that a missing package makes each test fail, not error at setup.
"""

import pytest

from skellycam.tests.take_recorder.children import Child
from skellycam.tests.take_recorder.fake_disk import FakeDisk
from skellycam.tests.take_recorder.rec_api import BENCH


def pytest_collection_modifyitems(config, items):
    if BENCH:
        return
    skip = pytest.mark.skip(reason="benchmark: runs only with SKELLYCAM_BENCH=1 (spec 12.1)")
    for item in items:
        if "recorder_bench" in item.keywords:
            item.add_marker(skip)


@pytest.fixture()
def disk(tmp_path, monkeypatch, runs):
    """The fake disk and file-action spy on `tmp_path`. Teardown releases each held write.

    It uses `runs`, so its teardown comes first: the held writes are released before the writers end."""
    fake = FakeDisk(tmp_path).install(monkeypatch)
    yield fake
    for rule in fake.rules:
        rule.release.set()


@pytest.fixture()
def runs():
    """Each `rec_api.Run` of a test. Teardown ends each camera writer that is still open."""
    started = []
    yield started
    for run in started:
        run.close()


@pytest.fixture()
def children(tmp_path):
    """A function that starts a `Child`. Teardown kills each child."""
    started = []

    def start(config):
        child = Child(config, tmp_path / "children")
        started.append(child)
        return child

    yield start
    for child in started:
        child.close()
