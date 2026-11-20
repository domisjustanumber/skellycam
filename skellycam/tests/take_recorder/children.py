"""The parent side of `child_writer.py`: start a child, send commands, wait for events, kill it.

`Child.kill()` is `Popen.kill()`: `TerminateProcess` on Windows and `SIGKILL` on Linux and macOS
(section 12.1). A kill at a chosen point: wait for the event of that point (`expect`), then kill;
or give the child a fake disk rule that ends it with `os._exit` inside a chosen write.
"""

import json
import pickle
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


class ChildError(AssertionError):
    pass


class Child:
    def __init__(self, config, workdir):
        workdir = Path(workdir)
        workdir.mkdir(parents=True, exist_ok=True)
        self.config_path = workdir / f"child_{id(self)}.pickle"
        with open(self.config_path, "wb") as handle:
            pickle.dump(config, handle)
        self.process = subprocess.Popen(  # noqa: S603 - the test interpreter and a test module
            [sys.executable, "-m", "skellycam.tests.take_recorder.child_writer", str(self.config_path)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=REPO_ROOT,
        )
        self.events, self.history, self.stderr = queue.Queue(), [], []
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._read_err, daemon=True).start()

    def _read(self):
        for line in self.process.stdout:
            try:
                self.events.put(json.loads(line))
            except json.JSONDecodeError:
                self.events.put({"event": "text", "text": line.decode(errors="replace")})
        self.events.put({"event": "eof"})

    def _read_err(self):
        for line in self.process.stderr:
            self.stderr.append(line.decode(errors="replace"))

    def send(self, cmd, **fields):
        self.process.stdin.write((json.dumps({"cmd": cmd, **fields}) + "\n").encode())
        self.process.stdin.flush()

    def next_event(self, timeout=30.0):
        try:
            event = self.events.get(timeout=timeout)
        except queue.Empty:
            raise ChildError(f"no event from the child in {timeout} s; stderr: {''.join(self.stderr)[-2000:]}") from None
        self.history.append(event)
        return event

    def expect(self, *names, timeout=30.0):
        """Wait for the next event whose name is in `names`. Fail on `eof`."""
        deadline = time.monotonic() + timeout
        while True:
            event = self.next_event(max(0.01, deadline - time.monotonic()))
            if event["event"] in names:
                return event
            if event["event"] == "eof":
                raise ChildError(f"the child ended before {names}; stderr: {''.join(self.stderr)[-2000:]}")

    def kill(self):
        """TerminateProcess on Windows, SIGKILL elsewhere. Then join."""
        if self.process.poll() is None:
            self.process.kill()
        return self.process.wait(30)

    def terminate_and_join(self, timeout=30.0):
        if self.process.poll() is None:
            self.process.terminate()
        return self.process.wait(timeout)

    def wait(self, timeout=30.0):
        return self.process.wait(timeout)

    def close(self):
        try:
            self.kill()
        except Exception:
            pass
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            try:
                stream.close()
            except Exception:
                pass
