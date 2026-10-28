# /// script
# requires-python = ">=3.10"
# ///
"""Serialize access to the physical cameras across concurrently running test agents.

Usage:
    uv run --script research/usb_cameras/tools/camlock.py [--timeout-s 1800] -- <command> [args...]

Acquires an exclusive OS-level lock on research/usb_cameras/.camlock, runs the command,
releases the lock, and exits with the command's exit code. The lock is released by the OS
if this process dies, so a crashed run cannot wedge the others.
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

LOCK_PATH = Path(__file__).resolve().parent.parent / ".camlock"


def _try_lock(fd: int) -> bool:
    if os.name == "nt":
        import msvcrt
        try:
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-s", type=float, default=1800.0)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("no command given")

    fd = os.open(LOCK_PATH, os.O_RDWR | os.O_CREAT)
    started = time.monotonic()
    while not _try_lock(fd):
        if time.monotonic() - started > args.timeout_s:
            print(f"[camlock] timed out after {args.timeout_s:.0f}s waiting for camera lock", file=sys.stderr)
            return 75
        time.sleep(0.5)
    print(f"[camlock] acquired after {time.monotonic() - started:.1f}s: {' '.join(command)}", file=sys.stderr, flush=True)
    try:
        return subprocess.call(command)
    finally:
        os.close(fd)
        print("[camlock] released", file=sys.stderr, flush=True)


if __name__ == "__main__":
    sys.exit(main())
