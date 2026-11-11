# /// script
# requires-python = ">=3.10"
# ///
"""Serialize access to the physical cameras across concurrently running test agents.

Usage:
    uv run --script research/usb_cameras/tools/camlock.py [--timeout-s 1800] [--no-queue] -- <command> [args...]

Acquires an exclusive OS-level lock on research/usb_cameras/.camlock, runs the command,
releases the lock, and exits with the command's exit code (75 when the lock wait timed out).
The lock is released by the OS if this process dies, so a crashed run cannot wedge the others.

Waiters are served first come, first served (a ticket lock): each waiter takes the next ticket
under a short dispenser lock, creates waiting/<ticket>.<pid> and holds an OS lock on that file
while it waits (queue files in %TEMP%/camlock_<hash of the lock path>/, outside the repo). A waiter only tries the camera lock once no live lower
ticket exists; a ticket file whose OS lock can be taken belongs to a dead waiter and is removed.
Without the queue, a waiter polling every 0.5 s could lose the race again and again (the W-KIYO
poller waited up to 456 s behind back-to-back test commands on 2026-11-06). A process that takes
the camera lock without a ticket (an old copy of this tool, --no-queue) can still jump the queue.
"""
import argparse
import hashlib
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

LOCK_PATH = Path(__file__).resolve().parent.parent / ".camlock"
#: the queue lives in the temp folder (one per lock file), so only the gitignored .camlock is in the repo
QUEUE_ROOT = Path(tempfile.gettempdir()) / f"camlock_{hashlib.sha1(str(LOCK_PATH).lower().encode()).hexdigest()[:12]}"
QUEUE_LOCK_PATH = QUEUE_ROOT / "dispenser.lock"
COUNTER_PATH = QUEUE_ROOT / "ticket"
QUEUE_DIR = QUEUE_ROOT / "waiting"
POLL_S = 0.25


def _try_lock(fd: int) -> bool:
    if os.name == "nt":
        import msvcrt
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    import fcntl
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock(fd: int) -> None:
    try:
        if os.name == "nt":
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass


def _lock_blocking(fd: int, timeout_s: float) -> bool:
    t0 = time.monotonic()
    while not _try_lock(fd):
        if time.monotonic() - t0 > timeout_s:
            return False
        time.sleep(0.02)
    return True


def _ticket_number(name: str) -> int | None:
    try:
        return int(name.split(".", 1)[0])
    except ValueError:
        return None


class Ticket:
    """This waiter's place in the queue: a ticket file held under an OS lock for as long as the waiter lives."""

    def __init__(self, queue_dir: Path = QUEUE_DIR, counter: Path = COUNTER_PATH,
                 dispenser: Path = QUEUE_LOCK_PATH) -> None:
        self.queue_dir, self.counter, self.dispenser = queue_dir, counter, dispenser
        self.number: int | None = None
        self.path: Path | None = None
        self.fd: int | None = None

    def take(self, timeout_s: float = 30.0) -> bool:
        """Draw the next number under the dispenser lock and create the held ticket file. False on failure (the
        caller then waits without a queue place)."""
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        self.dispenser.parent.mkdir(parents=True, exist_ok=True)
        dfd = os.open(self.dispenser, os.O_RDWR | os.O_CREAT)
        try:
            if not _lock_blocking(dfd, timeout_s):
                return False
            try:
                try:
                    n = int(self.counter.read_text(encoding="ascii").strip() or "0") + 1
                except (OSError, ValueError):
                    n = 1
                self.counter.write_text(str(n), encoding="ascii")
                self.number = n
                self.path = self.queue_dir / f"{n:012d}.{os.getpid()}"
                self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT)
                if not _try_lock(self.fd):
                    self.release()
                    return False
                return True
            finally:
                _unlock(dfd)
        finally:
            os.close(dfd)

    def ahead(self) -> list[Path]:
        """Live tickets with a lower number than ours; dead waiters' ticket files are removed on the way."""
        out = []
        try:
            entries = list(self.queue_dir.iterdir())
        except OSError:
            return out
        for p in entries:
            n = _ticket_number(p.name)
            if n is None or self.number is None or n >= self.number:
                continue
            if _is_dead(p):
                try:
                    p.unlink()
                except OSError:
                    pass
                continue
            out.append(p)
        return out

    def release(self) -> None:
        if self.fd is not None:
            _unlock(self.fd)
            os.close(self.fd)
            self.fd = None
        if self.path is not None:
            try:
                self.path.unlink()
            except OSError:
                pass
            self.path = None


def _is_dead(p: Path) -> bool:
    """A ticket file nobody holds (its OS lock can be taken) belongs to a waiter that died."""
    try:
        fd = os.open(p, os.O_RDWR)
    except OSError:
        return False          # already gone, or held open in a way we cannot open: treat as live
    try:
        if _try_lock(fd):
            _unlock(fd)
            return True
        return False
    finally:
        os.close(fd)


def acquire(timeout_s: float, queue: bool = True, lock_path: Path = LOCK_PATH,
            ticket: Ticket | None = None) -> tuple[int | None, Ticket | None]:
    """(camera-lock fd or None on timeout, ticket). FIFO among ticket holders when ``queue``."""
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT)
    t = None
    if queue:
        t = ticket or Ticket()
        if t.number is None and not t.take():
            t = None
    started = time.monotonic()
    try:
        while True:
            if (t is None or not t.ahead()) and _try_lock(fd):
                return fd, t
            if time.monotonic() - started > timeout_s:
                os.close(fd)
                return None, t
            time.sleep(POLL_S)
    finally:
        if t is not None:
            t.release()        # holding the camera lock (or giving up): our place in the queue is no longer needed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-s", type=float, default=1800.0)
    parser.add_argument("--no-queue", action="store_true", help="poll the lock without taking a FIFO ticket")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("no command given")

    started = time.monotonic()
    fd, ticket = acquire(args.timeout_s, queue=not args.no_queue)
    if fd is None:
        print(f"[camlock] timed out after {args.timeout_s:.0f}s waiting for camera lock", file=sys.stderr)
        return 75
    print(f"[camlock] acquired after {time.monotonic() - started:.1f}s"
          f"{f' (ticket {ticket.number})' if ticket and ticket.number else ''}: {' '.join(command)}",
          file=sys.stderr, flush=True)
    try:
        return subprocess.call(command)
    finally:
        _unlock(fd)
        os.close(fd)
        print("[camlock] released", file=sys.stderr, flush=True)


if __name__ == "__main__":
    sys.exit(main())
