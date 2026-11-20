"""Fixtures of the step 4a preview tests (specs/preview.md, section 9).

The fixtures do not import the preview module. Each test imports it, so that a missing module makes
each test fail, not error at setup.
"""

import pytest

from skellycam.tests.frame_ring.conftest import Cleanup


@pytest.fixture()
def cleanup():
    registry = Cleanup()
    yield registry
    registry.run()


@pytest.fixture()
def writers(cleanup):
    """Each paced writer that a test starts. Teardown stops each one before the rings close."""
    started = []
    yield started
    for writer in started:
        writer.stop()
