"""Child processes of `test_status_locks.py` (spawn imports this module, not the test module)."""
import json
import time

DEADLINE_S = 60.0  # each child ends by itself after this, also when nobody stops or kills it


def hold_then_write(status, go, stop, hold_s, locked):
    """Hold the lock of `info` for `hold_s` (a live holder that is only slow), then write `info` until `stop`: with
    its lock, or with no lock (torn reads in the main process). The sizes alternate, as the writes of the loop do."""
    lock = status.info.get_lock()
    lock.acquire()
    go.set()
    time.sleep(hold_s)
    lock.release()
    count, deadline = 0, time.monotonic() + DEADLINE_S
    while not stop.is_set() and time.monotonic() < deadline:
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


def read_heartbeat_forever(heartbeat, reading):
    """A camera process: read the heartbeat in a tight loop, as each loop pass does, until it is killed."""
    from skellycam.utilities.check_main_processs_heartbeat import check_main_process_heartbeat

    reading.set()
    deadline = time.monotonic() + DEADLINE_S
    while time.monotonic() < deadline:
        check_main_process_heartbeat(heartbeat_timestamp=heartbeat)
