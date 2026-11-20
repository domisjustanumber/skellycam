"""The libjpeg warnings of a camera process on Windows (specs/windows-capture.md, section 5.6; D42, U17).

The OpenCV wheel has its own C runtime. That runtime takes its descriptor 2 from the standard error
handle of the process when OpenCV loads, and a later redirect does not reach it (ADR-E817 item 7).
`multiprocessing` gives no handle to a child on Windows. Thus the main process makes a named pipe and
puts its name in the environment of the child. The child sets the pipe as its standard error handle
before OpenCV loads (`attach_stderr_pipe`, called by `skellycam/__init__.py`). One thread of the main
process for each camera process reads the pipe and logs each different line one time per minute at
most, with a count (ring 8.9).
"""
import contextlib
import itertools
import os
import sys
import threading

ENV_NAME = "SKELLYCAM_STDERR_PIPE"
STD_ERROR_HANDLE = -12
ERROR_PIPE_CONNECTED = 535
_names = itertools.count()


@contextlib.contextmanager
def child_stderr_pipe(label: str):
    """Main process, Windows: the processes started in this block get a pipe as their standard error."""
    import _winapi

    name = rf"\\.\pipe\skellycam-stderr-{os.getpid()}-{next(_names)}"
    handle = _winapi.CreateNamedPipe(name, _winapi.PIPE_ACCESS_INBOUND, _winapi.PIPE_WAIT, 1, 0, 65536, 0,
                                     _winapi.NULL)
    os.environ[ENV_NAME] = name
    try:
        yield
    except BaseException:
        _winapi.CloseHandle(handle)
        raise
    finally:
        os.environ.pop(ENV_NAME, None)
    threading.Thread(target=_relay, args=(handle,), name=f"libjpeg warnings {label}", daemon=True).start()


def _relay(handle: int) -> None:
    import _winapi
    import msvcrt

    from skellycam.core.ipc.frame_ring.decode import _forward_lines

    try:
        _winapi.ConnectNamedPipe(handle, False)
    except OSError as error:
        if error.winerror != ERROR_PIPE_CONNECTED:  # the child connected first: that is normal
            _winapi.CloseHandle(handle)
            return
    _forward_lines(msvcrt.open_osfhandle(handle, os.O_RDONLY))  # the rule of ring 8.9


def attach_stderr_pipe() -> None:
    """Child process, Windows: before OpenCV loads, make the pipe of the main process the standard error."""
    name = os.environ.pop(ENV_NAME, None)
    if not name or sys.platform != "win32":
        return
    import _winapi
    import ctypes

    try:
        handle = _winapi.CreateFile(name, _winapi.GENERIC_WRITE, 0, _winapi.NULL, _winapi.OPEN_EXISTING, 0,
                                    _winapi.NULL)
    except OSError:
        return
    ctypes.windll.kernel32.SetStdHandle(STD_ERROR_HANDLE, handle)
