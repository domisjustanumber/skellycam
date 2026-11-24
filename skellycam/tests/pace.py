"""The margin of the tests with the marker `pace` (specs/windows-capture.md 16.1; Q619 of the user, 2026-11-23).

A workflow runs the `pace` tests in a step of its own with `SKELLYCAM_PACE_MARGIN` (3 on the hosted runners). A
test multiplies the tolerance of each bound by `margin()`: the part of the bound past its nominal value. The nominal
value does not move. On a real machine the setting is not there, and the margin is 1 (strict).

A split test (Q669 of the user, 2026-11-24 [ADR-F4N7]) is a blocking test and a `pace` test on one run: `one_run`.
"""

import os

MARGIN_SETTING = "SKELLYCAM_PACE_MARGIN"
_RUNS = {}


def margin() -> float:
    """The margin of this run: the value of the setting, at least 1; 1 when it is not set or not a number."""
    try:
        return max(float(os.environ.get(MARGIN_SETTING) or 1.0), 1.0)
    except ValueError:
        return 1.0


def bound(nominal: float, strict: float) -> float:
    """The bound of a `pace` test: the nominal value plus the strict tolerance (`strict - nominal`) times the margin.
    A lower bound has `strict` below `nominal`, so it goes down with the margin."""
    return nominal + (strict - nominal) * margin()


def one_run(key, run):
    """The result of `run()` for `key`, made one time in a test session: the blocking test and the `pace` test of a
    split test check the same run [ADR-B7YV]. The test that comes first makes the run with its own fixtures, so
    `run()` must give only data, not objects that its fixtures end. A run that raises is not kept: the next test
    makes it again. A CI step with `-m "not pace"` or `-m pace` runs only one test of the two, so it makes its own
    run."""
    if key not in _RUNS:
        _RUNS[key] = run()
    return _RUNS[key]
