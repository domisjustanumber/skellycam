"""Run rules of the capture tests (specs/windows-capture.md, section 16.1).

- `camera_hardware`: skipped unless `SKELLYCAM_HARDWARE=1`. The user gives the word.
- `capture_local`: the Windows development machine only; the CI jobs leave it out (section 15).
- A failed test with a `VirtualClock` shows the notes of the clock (ADR-FTC3). `SKELLYCAM_CLOCK_TRACE=1`
  adds a trace of each state change and step, and a line for each test.

The markers are registered in `pyproject.toml`.
"""

import os

import pytest

HARDWARE = os.environ.get("SKELLYCAM_HARDWARE", "") == "1"
CLOCK_TRACE = os.environ.get("SKELLYCAM_CLOCK_TRACE", "") == "1"


def pytest_runtest_setup(item):
    from skellycam.tests.capture.fake_source import VirtualClock

    VirtualClock.instances.clear()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """A failed test with a virtual clock gets the notes of the clock (ADR-FTC3). With
    `SKELLYCAM_CLOCK_TRACE=1`, each test also writes the stopped far steps of its clocks to the terminal."""
    outcome = yield
    report = outcome.get_result()
    if call.when != "call":
        return
    from skellycam.tests.capture.fake_source import VirtualClock

    clocks = list(VirtualClock.instances)
    if report.failed and clocks:
        report.sections.append(("virtual clock", "\n\n".join(clock.report() for clock in clocks)))
    if CLOCK_TRACE and clocks:
        writer = item.config.pluginmanager.get_plugin("terminalreporter")
        if writer is not None:
            for clock in clocks:
                first = clock.notes[0][0] if clock.notes else 0
                states = "; ".join(f"{(real - first) / 1e6:.0f} ms {text}" for real, text in clock.notes
                                   if " sets " in text and "Worker" in text)
                writer.write_line(f"[clock] {item.nodeid}: stopped steps {clock.stopped}; real times: {states}")


def pytest_collection_modifyitems(config, items):
    if HARDWARE:
        return
    skip = pytest.mark.skip(reason="hardware test: runs only with SKELLYCAM_HARDWARE=1 (spec 16.1)")
    for item in items:
        if "camera_hardware" in item.keywords:
            item.add_marker(skip)
