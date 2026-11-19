"""A worker process with a piped console logs a line with the box-drawing prefix of skellylogs
(user decision of 2026-11-19, step 3a). A piped stream on Windows is cp1252 unless the process sets
UTF-8, and each log line then fails with "--- Logging error ---"."""

import os
import subprocess
import sys

CHILD = """
import logging
import multiprocessing

from skellycam.core.ipc.process_management.managed_worker import _process_entry_point


def target():
    logging.getLogger("skellycam.tests.utf8").warning("\\u2514 utf8 console line")


if __name__ == "__main__":
    _process_entry_point(target_fn=target, name="utf8-console", shutdown_flag=multiprocessing.Value("b", False),
                         log_queue=multiprocessing.Queue(), worker_kwargs={})
"""


def test_worker_with_a_piped_console_logs_utf8_lines():
    env = {name: value for name, value in os.environ.items() if name not in ("PYTHONIOENCODING", "PYTHONUTF8")}
    process = subprocess.run([sys.executable, "-c", CHILD], capture_output=True, timeout=120, env=env)
    output = (process.stdout + process.stderr).decode("utf-8", errors="replace")
    assert process.returncode == 0, output[-2000:]
    assert "utf8 console line" in output
    assert "--- Logging error ---" not in output
