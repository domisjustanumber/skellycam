"""A pytest plugin for T-REC-37 (specs/recorder.md, section 12.3): in the conformance tests of
skellyfileformat, keep only the test functions that use the fixture `writer` and not `reader`.

T-REC-37 loads it with `-p skellycam.tests.take_recorder.sff_select`. It runs before the hook of the
conformance `conftest.py` (`tryfirst`), so that hook sees only the kept tests.
"""

import pytest


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    kept, dropped = [], []
    for item in items:
        names = getattr(item, "fixturenames", ())
        (kept if "writer" in names and "reader" not in names else dropped).append(item)
    if dropped:
        config.hook.pytest_deselected(items=dropped)
    items[:] = kept
