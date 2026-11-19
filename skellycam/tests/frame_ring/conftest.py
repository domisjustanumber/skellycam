"""Fixtures of the frame ring tests (specs/frame-ring.md, section 12).

The fixtures do not import the ring package. Each test imports it, so that a missing package
makes each test fail, not error at setup.
"""

import multiprocessing

import pytest

from skellycam.tests.frame_ring.ring_spec import open_raw


class Cleanup:
    """Closes and unlinks each ring of a test, also when the test fails."""

    def __init__(self):
        self.owners = []  # objects with close_and_unlink()
        self.handles = []  # objects with close()
        self.names = []  # ring names to unlink by name

    def own(self, owner):
        self.owners.append(owner)
        return owner

    def handle(self, handle):
        self.handles.append(handle)
        return handle

    def name(self, name):
        self.names.append(name)
        return name

    def run(self):
        for handle in reversed(self.handles):
            try:
                handle.close()
            except Exception:
                pass
        for owner in reversed(self.owners):
            try:
                owner.close_and_unlink()
            except Exception:
                pass
        for name in self.names:
            try:
                shm = open_raw(name)
            except FileNotFoundError:
                continue
            shm.close()
            try:
                shm.unlink()
            except FileNotFoundError:
                pass


@pytest.fixture()
def cleanup():
    registry = Cleanup()
    yield registry
    registry.run()


@pytest.fixture()
def spawn():
    """The spawn start method, explicitly, on each OS (rule of the 2a tests)."""
    return multiprocessing.get_context("spawn")


@pytest.fixture()
def stages():
    """Each decode stage that a test starts (ring_spec.start_stage). Teardown stops each one."""
    started = []
    yield started
    for stage in started:
        try:
            stage.stop()
        except Exception:
            pass


@pytest.fixture()
def procs():
    """Each process that a test starts. Teardown kills each live process."""
    started = []
    yield started
    for process in started:
        if process.is_alive():
            process.kill()
        process.join(timeout=10)
