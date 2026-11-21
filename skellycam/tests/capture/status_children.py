"""Child processes of `test_status_locks.py` (spawn imports this module, not the test module)."""
import json
import time


def hold_then_write(status, go, stop, hold_s, locked):
    """Hold the lock of `info` for `hold_s` (a live holder that is only slow), then write `info` until `stop`: with
    its lock, or with no lock (torn reads in the main process). The sizes alternate, as the writes of the loop do."""
    lock = status.info.get_lock()
    lock.acquire()
    go.set()
    time.sleep(hold_s)
    lock.release()
    count = 0
    while not stop.is_set():
        count += 1
        fields = dict(controls={"x": "a" * (50 + (count % 7) * 900)}, measured_fps=count)
        if locked:
            status.update_info(**fields)
        else:
            status.info.get_obj().value = json.dumps(fields).encode()


def write_info(status, done):
    """A new camera process: one write of `info` with its lock."""
    status.update_info(mode={"width": 320})
    done.set()
