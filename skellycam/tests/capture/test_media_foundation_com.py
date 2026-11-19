"""The apartment of the Media Foundation package (specs/windows-capture.md, section 6.1, agent 43). No device."""

import subprocess
import sys

import pytest

CHECK = """
import ctypes
import skellycam.core.camera.capture.media_foundation.source  # imports comtypes before com.py
from skellycam.core.camera.capture.media_foundation import com
com.startup()
kind, qualifier = ctypes.c_int(), ctypes.c_int()
assert ctypes.WinDLL("ole32.dll").CoGetApartmentType(ctypes.byref(kind), ctypes.byref(qualifier)) == 0
com.shutdown()
print("APTTYPE", kind.value)
"""


@pytest.mark.skipif(sys.platform != "win32", reason="the media_foundation package is Windows only (U18)")
def test_main_thread_is_in_the_mta_after_startup():
    """A fresh process imports the source module first, then calls `com.startup()`. The main thread
    is then in the multithreaded apartment (APTTYPE_MTA = 1), and `startup()` does not raise."""
    try:
        import ctypes
        ctypes.WinDLL("mfplat.dll")
    except OSError:
        pytest.skip("mfplat.dll does not load on this runner")
    process = subprocess.run([sys.executable, "-c", CHECK], capture_output=True, text=True, timeout=120)
    assert process.returncode == 0, process.stderr[-2000:]
    assert "APTTYPE 1" in process.stdout, process.stdout
