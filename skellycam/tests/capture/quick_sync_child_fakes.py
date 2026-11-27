"""Fake checks for the Quick Sync check child (specs/windows-capture.md 22.7). A `spawn` child imports its target by
name, so each fake is a function of this module. Each one stands for the encode of the test frame: it gives True for
a JPEG and False for no JPEG."""

import os
import sys
import threading
import time

ACCESS_VIOLATION = 0xC0000005  # the exit code of a Windows process that ended with an access violation


def gives_true():
    return True


def gives_false():
    return False


def hangs():
    time.sleep(60)
    return True


def exits_3():
    os._exit(3)


def exits_access_violation():
    """A stand-in for a crash in the driver: the process ends with the code of an access violation, with no dialog of
    Windows Error Reporting (a real access violation can open one)."""
    os._exit(ACCESS_VIOLATION - 2**32 if sys.platform == "win32" else 139)


def raises():
    raise RuntimeError("a fake encode error")


def answers_then_hangs_at_exit():
    """A good encode whose teardown hangs: a thread that is not a daemon holds the exit of the child for 60 s, so the
    child gives its answer and then does not end."""
    threading.Thread(target=time.sleep, args=(60,), daemon=False).start()
    return True
