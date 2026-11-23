"""The skip guard of the workflows (specs/unix-capture.md 4.11) [ADR-HQE5].

`SKELLYCAM_NO_SKIP` holds test paths, separated by commas. A test under one of these paths that is skipped makes
the run fail. Reason: a module skip of `test_connection.py` made the recorder workflow green on Linux, and the
first run of these tests on Linux came three days after the code.
"""

import os

NO_SKIP_SETTING = "SKELLYCAM_NO_SKIP"


def guarded_paths(value: str | None = None) -> list[str]:
    value = os.environ.get(NO_SKIP_SETTING, "") if value is None else value
    return [path.strip().replace("\\", "/") for path in value.split(",") if path.strip()]


def is_guarded_skip(report, paths: list[str]) -> bool:
    """A skip of a test under `paths` (an expected failure, `xfail`, is not a skip here)."""
    if not paths or not report.skipped or hasattr(report, "wasxfail"):
        return False
    nodeid = report.nodeid.replace("\\", "/")
    return any(nodeid == path or nodeid.startswith(path.rstrip("/") + ("/" if not path.endswith(".py") else "::"))
               for path in paths)
