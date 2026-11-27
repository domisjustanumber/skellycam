"""The end of a server process whose start fails (specs/recorder.md 9.1, Q907 [ADR-75CF], [ADR-06PW]).

The real server of `skellycam/__main__.py` runs in a child process (`server_exit_child.py`), with no camera group.
"""

import socket
import subprocess
import sys
from pathlib import Path

HANG_S = 30.0  # a process that has not ended by then hangs
CHILD = Path(__file__).with_name("server_exit_child.py")


def test_the_server_ends_when_its_port_is_in_use(tmp_path):
    """recorder.md 9.1 item 1: uvicorn ends a server whose port is in use with `sys.exit`. The exit then runs the
    exit handlers, and the join of the feeder thread of the log queue, which nobody read, must not hold it."""
    with socket.socket() as holder:
        holder.bind(("localhost", 0))
        holder.listen()
        log = tmp_path / "server.out"
        with open(log, "w") as out:
            server = subprocess.Popen([sys.executable, str(CHILD), str(holder.getsockname()[1]), str(tmp_path),
                                       str(tmp_path / "server.log")], stdout=out, stderr=subprocess.STDOUT)
        try:
            code = server.wait(timeout=HANG_S)
        except subprocess.TimeoutExpired:
            code = None
        finally:
            if server.poll() is None:
                server.kill()
                server.wait()
    assert code is not None, f"the server process did not end within {HANG_S:g} s: {log.read_text(errors='replace')[-2000:]}"
    assert code != 0
