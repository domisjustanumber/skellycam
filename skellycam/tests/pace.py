"""The margin of the tests with the marker `pace` (specs/windows-capture.md 16.1; Q619 of the user, 2026-11-23).

A workflow runs the `pace` tests in a step of its own with `SKELLYCAM_PACE_MARGIN` (3 on the hosted runners). A
test multiplies the tolerance of each bound by `margin()`: the part of the bound past its nominal value. The nominal
value does not move. On a real machine the setting is not there, and the margin is 1 (strict).
"""

import os

MARGIN_SETTING = "SKELLYCAM_PACE_MARGIN"


def margin() -> float:
    """The margin of this run: the value of the setting, at least 1; 1 when it is not set or not a number."""
    try:
        return max(float(os.environ.get(MARGIN_SETTING) or 1.0), 1.0)
    except ValueError:
        return 1.0
