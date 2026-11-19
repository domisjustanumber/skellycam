"""A fake disk and a file-action spy for the recorder tests (specs/recorder.md, sections 5.3, 5.4, 5.6, 6.8).

`FakeDisk.install(monkeypatch)` replaces `builtins.open` and `io.open`. Each file that is opened
under `root` comes back wrapped in a `FakeFile`, which passes each call to the real file. A rule
makes the writes of one file kind stall, block until released, raise an `OSError` (for example
ENOSPC, EFBIG or EIO), or end the process (`os._exit`) at a chosen write. The spy also records
the file actions of the take: opens, writes, fsync, replace, truncate, lock and unlock, each with
the name of the thread. The product needs no seam for this, only plain calls of `open`,
`os.fsync`, `os.replace` and the module functions of the lock (ADR-QEQ8).
"""

import builtins
import errno
import io
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

_REAL_OPEN = io.open


@dataclass
class Rule:
    """One fault. `kind` is the file kind: `.mkv`, `.csv` or `.json`/`.tmp`.

    `after` is the number of writes of that kind that pass before the rule acts. `action` is one of
    `stall` (sleep `seconds` one time), `hold` (block until `release` is set), `fail` (raise
    `OSError(errno_code)` on this and each later write), `exit` (write the bytes, or with `partial`
    the first half of them, then `os._exit(exit_code)`) and `exit_before` (exit before the bytes are
    written). `row_only` counts only CSV data rows (lines that start with a digit).
    """

    kind: str
    after: int = 0
    action: str = "fail"
    seconds: float = 0.0
    errno_code: int = errno.ENOSPC
    exit_code: int = 9
    partial: bool = False
    row_only: bool = False
    match: str = ""  # the rule applies only to a file whose name holds this text
    release: threading.Event = field(default_factory=threading.Event)
    holding: threading.Event = field(default_factory=threading.Event)
    seen: int = 0
    fired: bool = False


def kind_of(path):
    name = str(path)
    for suffix in (".mkv", ".csv", ".tmp", ".json", ".lock"):
        if name.endswith(suffix):
            return suffix
    return Path(name).suffix


class FakeFile:
    """A wrapper of a real file object. Each call goes to the real file, after the rules of the disk."""

    def __init__(self, disk, real, path, mode):
        self._disk, self._real, self.path, self.mode = disk, real, Path(path), mode
        self.kind = kind_of(path)

    # The calls that PyAV and the product use. Each one passes to the real file.
    def write(self, data):
        return self._disk._write(self, data)

    def read(self, *args):
        self._disk._event("read", self.path)
        return self._real.read(*args)

    def readinto(self, buffer):
        self._disk._event("read", self.path)
        return self._real.readinto(buffer)

    def readline(self, *args):
        self._disk._event("read", self.path)
        return self._real.readline(*args)

    def readlines(self, *args):
        self._disk._event("read", self.path)
        return self._real.readlines(*args)

    def __iter__(self):
        self._disk._event("read", self.path)
        return iter(self._real)

    def seek(self, *args):
        return self._real.seek(*args)

    def tell(self):
        return self._real.tell()

    def flush(self):
        self._disk._event("flush", self.path)
        return self._real.flush()

    def truncate(self, *args):
        self._disk._event("truncate", self.path)
        return self._real.truncate(*args)

    def fileno(self):
        return self._real.fileno()

    def close(self):
        self._disk._event("close", self.path)
        return self._real.close()

    def readable(self):
        return self._real.readable()

    def writable(self):
        return self._real.writable()

    def seekable(self):
        return self._real.seekable()

    def isatty(self):
        return False

    @property
    def closed(self):
        return self._real.closed

    @property
    def name(self):
        return self._real.name

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def __getattr__(self, name):
        return getattr(self._real, name)


class FakeDisk:
    """The fake disk and the spy. `root` is the folder whose files it wraps (the take folder or tmp_path)."""

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.rules = []
        self.events = []  # (time_ns, thread name, event, path relative to root, extra)
        self.fd_paths = {}
        self.writes = {}  # path -> number of write calls
        self.lock = threading.Lock()
        self.after_write = None  # a test hook: after_write(handle, data), after each real write
        self.write_ns = []  # (file kind, duration of the real write in ns): the benchmarks read it

    # --- rules ---

    def add(self, kind, action, **kwargs):
        rule = Rule(kind=kind, action=action, **kwargs)
        with self.lock:
            self.rules.append(rule)
        return rule

    def fail(self, kind, *, after=0, errno_code=errno.ENOSPC, row_only=False, match=""):
        return self.add(kind, "fail", after=after, errno_code=errno_code, row_only=row_only, match=match)

    def stall(self, kind, seconds, *, after=0, row_only=False, match=""):
        return self.add(kind, "stall", after=after, seconds=seconds, row_only=row_only, match=match)

    def hold(self, kind, *, after=0, row_only=False, match=""):
        """Block the writes of `kind` from write `after` on, until `rule.release.set()`."""
        return self.add(kind, "hold", after=after, row_only=row_only, match=match)

    def exit(self, kind, *, after=0, partial=False, before=False, row_only=False, exit_code=9):
        action = "exit_before" if before else "exit"
        return self.add(kind, action, after=after, partial=partial, row_only=row_only, exit_code=exit_code)

    # --- install ---

    def install(self, monkeypatch=None):
        """Replace `builtins.open`, `io.open`, `os.fsync`, `os.replace`, `os.truncate` and the lock calls."""
        real_fsync, real_replace, real_truncate = os.fsync, os.replace, os.truncate

        def fake_open(file, mode="r", *args, **kwargs):
            real = _REAL_OPEN(file, mode, *args, **kwargs)
            if isinstance(file, int) or not self._under_root(file):
                return real
            path = Path(file).resolve()
            try:
                self.fd_paths[real.fileno()] = path
            except (OSError, ValueError, AttributeError):
                pass
            self._event("open", path, mode)
            return FakeFile(self, real, path, mode)

        def fake_fsync(fd):
            fd_number = fd if isinstance(fd, int) else fd.fileno()
            path = self.fd_paths.get(fd_number)
            if path is not None:
                self._event("fsync", path)
            return real_fsync(fd)

        def fake_replace(src, dst, *args, **kwargs):
            if self._under_root(dst):
                self._event("replace", Path(dst).resolve(), str(self._rel(Path(src).resolve())))
            return real_replace(src, dst, *args, **kwargs)

        def fake_truncate(path, length):
            if not isinstance(path, int) and self._under_root(path):
                self._event("truncate", Path(path).resolve(), length)
            elif isinstance(path, int) and path in self.fd_paths:
                self._event("truncate", self.fd_paths[path], length)
            return real_truncate(path, length)

        patches = [(builtins, "open", fake_open), (io, "open", fake_open), (os, "fsync", fake_fsync),
                   (os, "replace", fake_replace), (os, "truncate", fake_truncate)]
        if sys.platform == "win32":
            import msvcrt

            real_locking = msvcrt.locking

            def fake_locking(fd, mode, nbytes):
                result = real_locking(fd, mode, nbytes)
                path = self.fd_paths.get(fd)
                if path is not None:
                    self._event("unlock" if mode == msvcrt.LK_UNLCK else "lock", path, mode)
                return result

            patches.append((msvcrt, "locking", fake_locking))
        else:
            import fcntl

            real_flock = fcntl.flock

            def fake_flock(fd, operation):
                result = real_flock(fd, operation)
                fd_number = fd if isinstance(fd, int) else fd.fileno()
                path = self.fd_paths.get(fd_number)
                if path is not None:
                    self._event("unlock" if operation & fcntl.LOCK_UN else "lock", path, operation)
                return result

            patches.append((fcntl, "flock", fake_flock))
        for module, name, value in patches:
            if monkeypatch is not None:
                monkeypatch.setattr(module, name, value)
            else:
                setattr(module, name, value)
        return self

    # --- queries ---

    def trace(self, *names):
        """The events as (event, relative path) pairs, only of the given event names when named."""
        with self.lock:
            return [(e[2], e[3]) for e in self.events if not names or e[2] in names]

    def events_of(self, event, suffix=None):
        with self.lock:
            return [e for e in self.events if e[2] == event and (suffix is None or e[3].endswith(suffix))]

    def wait_holding(self, rule, timeout=10.0):
        """Wait until the writer thread is blocked in the rule `rule`."""
        return rule.holding.wait(timeout)

    # --- internals ---

    def _under_root(self, file):
        try:
            return Path(os.fspath(file)).resolve().is_relative_to(self.root)
        except (TypeError, ValueError, OSError):
            return False

    def _rel(self, path):
        try:
            return Path(path).relative_to(self.root).as_posix()
        except ValueError:
            return Path(path).as_posix()

    def _event(self, event, path, extra=None):
        with self.lock:
            self.events.append((time.perf_counter_ns(), threading.current_thread().name, event, self._rel(path), extra))

    def _write(self, handle, data):
        data = bytes(data)
        with self.lock:
            self.writes[handle.path] = self.writes.get(handle.path, 0) + 1
            active = None
            is_row = handle.kind == ".csv" and data[:1].isdigit()
            for rule in self.rules:
                if rule.kind != handle.kind or (rule.row_only and not is_row) or rule.match not in handle.path.name:
                    continue
                if rule.action == "fail" and rule.fired:
                    active = rule
                    break
                if rule.fired:
                    continue
                if rule.seen >= rule.after:
                    active = rule
                    rule.fired = rule.action != "hold"
                    break
                rule.seen += 1
        self._event("write", handle.path, len(data))
        if active is not None:
            if active.action == "stall":
                time.sleep(active.seconds)
            elif active.action == "hold":
                active.holding.set()
                active.release.wait()
            elif active.action == "fail":
                raise OSError(active.errno_code, os.strerror(active.errno_code))
            elif active.action == "exit_before":
                os._exit(active.exit_code)
            elif active.action == "exit":
                handle._real.write(data[: max(1, len(data) // 2)] if active.partial else data)
                handle._real.flush()
                os._exit(active.exit_code)
        started = time.perf_counter_ns()
        written = handle._real.write(data)
        self.write_ns.append((handle.kind, time.perf_counter_ns() - started))
        if self.after_write is not None:
            self.after_write(handle, data)
        return written
