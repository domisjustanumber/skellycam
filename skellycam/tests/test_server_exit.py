"""The connection limit of the shutdown (specs/recorder.md 9, Q907 of the user [ADR-75CF]).

The real server of `skellycam/__main__.py` runs in a child process (`server_exit_child.py`), with no camera group. Its
first connection never leaves its asyncio server, as a reset connection whose loss never reaches the server. After
`/shutdown`, the server process must still end: at most `LIMIT_S` after the start of the shutdown of uvicorn. A split
test (Q669): the blocking half checks that the process ends, the `pace` half checks the time. A server whose port is in
use must end too (item 4).
"""

import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from skellycam.tests.pace import bound, one_run

LIMIT_S = 5.0  # recorder.md 9: the shutdown of uvicorn waits at most this long for open connections
HANG_S = 30.0  # the blocking half: a process that has not ended by then hangs
CHILD = Path(__file__).with_name("server_exit_child.py")


def _get(port: int, path: str, timeout: float) -> dict:
    with urllib.request.urlopen(f"http://localhost:{port}{path}", timeout=timeout) as response:
        return json.loads(response.read())


def _start(tmp_path: Path, port: int) -> tuple[subprocess.Popen, Path]:
    log = tmp_path / "server.out"
    with open(log, "w") as out:
        server = subprocess.Popen([sys.executable, str(CHILD), str(port), str(tmp_path), str(tmp_path / "server.log")],
                                  stdout=out, stderr=subprocess.STDOUT)
    return server, log


def _run(tmp_path: Path) -> dict:
    with socket.socket() as probe:
        probe.bind(("localhost", 0))
        port = probe.getsockname()[1]
    server, log = _start(tmp_path, port)
    try:
        started = time.monotonic()
        while True:  # the first answered request is the connection that the server loses
            try:
                _get(port, "/health", timeout=1)
                break
            except OSError:
                assert server.poll() is None and time.monotonic() - started < 60, log.read_text(errors="replace")
                time.sleep(0.2)
        assert _get(port, "/shutdown", timeout=5)["status"] == "shutdown_initiated"
        answered = time.monotonic()
        try:
            code = server.wait(timeout=HANG_S)
        except subprocess.TimeoutExpired:
            return {"ended": False, "code": None, "exit_s": None}
        return {"ended": True, "code": code, "exit_s": time.monotonic() - answered}
    finally:
        if server.poll() is None:
            server.kill()
            server.wait()


def test_the_server_ends_after_shutdown_with_a_lost_connection(tmp_path):
    result = one_run("server_exit", lambda: _run(tmp_path))
    assert result["ended"], f"the server process did not end within {HANG_S:g} s of /shutdown"
    assert result["code"] == 0, result


@pytest.mark.pace
def test_the_server_ends_within_the_connection_limit(tmp_path):
    result = one_run("server_exit", lambda: _run(tmp_path))
    assert result["ended"], f"the server process did not end within {HANG_S:g} s of /shutdown"
    # the limit starts at the signal of the worker monitor (up to 1 s after the answer) and holds the end until then
    assert LIMIT_S <= result["exit_s"] <= bound(LIMIT_S + 1.0, LIMIT_S + 2.5), result


def test_the_server_ends_when_its_port_is_in_use(tmp_path):
    """recorder.md 9.1 item 4: uvicorn ends a server whose port is in use with `sys.exit`. The exit then runs the
    exit handlers, and the join of the feeder thread of the log queue, which nobody read, must not hold it."""
    with socket.socket() as holder:
        holder.bind(("localhost", 0))
        holder.listen()
        server, log = _start(tmp_path, holder.getsockname()[1])
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
