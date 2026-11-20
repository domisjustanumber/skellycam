"""The child process of the recorder kill, stall and lock tests (specs/recorder.md, sections 3, 11, 12.2).

Run as `python -m skellycam.tests.take_recorder.child_writer <config.pickle>`. The child reads one
JSON command per line on standard input and writes one JSON event per line on standard output.
`children.Child` is the parent side.

Modes (the `mode` of the config):

- `selftest`: no product code. It writes lines to a file through the fake disk. The self-tests of
  the helpers use it.
- `lock`: no product code. It takes the lock of 6.8 on `.processing.lock` (`msvcrt.locking` with
  `LK_NBLCK` on byte 0 on Windows, `fcntl.flock` with `LOCK_EX | LOCK_NB` elsewhere), holds it for
  `hold_s` seconds or until the command `release`, then releases it.
- `writer`: the camera level of the product (`CameraTakeWriter`) with the fake disk rules of the
  config. Frame k is `jpeg_tools.synthetic_jpeg(k, ...)`, so the parent can make the same bytes.
- `paced`: the benchmarks of section 11: a synthetic source thread on an absolute schedule puts
  frames in a waiting place; the loop thread takes the newest frame and gives it to the writer.
"""

import json
import os
import pickle
import sys
import threading
import time

from skellycam.tests.take_recorder import jpeg_tools
from skellycam.tests.take_recorder.fake_disk import FakeDisk

_OUT_LOCK = threading.Lock()


def emit(event, **fields):
    with _OUT_LOCK:
        sys.stdout.write(json.dumps({"event": event, **fields}) + "\n")
        sys.stdout.flush()


def commands():
    for line in sys.stdin:
        line = line.strip()
        if line:
            yield json.loads(line)


def install_rules(config):
    """The fake disk of the config: `root` and a list of rules (dicts of FakeDisk.add arguments)."""
    if not config.get("root"):
        return None
    disk = FakeDisk(config["root"]).install()
    for rule in config.get("rules", ()):
        add_rule(disk, rule)
    return disk


def add_rule(disk, rule):
    """A rule dict of the parent: FakeDisk.add arguments; `before: true` with `exit` is `exit_before`."""
    rule = dict(rule)
    kind, action = rule.pop("kind"), rule.pop("action")
    if rule.pop("before", False) and action == "exit":
        action = "exit_before"
    disk.add(kind, action, **rule)


def result_fields(result):
    names = ("camera_id", "rows", "blocks", "missing_rows", "last_real_row", "queue_high_water",
             "give_wait_count", "give_wait_ms_max", "files_closed", "error")
    return {name: getattr(result, name) for name in names}


def frame_payload(config, k):
    return jpeg_tools.synthetic_jpeg(k, config["width"], config["height"], config.get("layout", "422"),
                                     config.get("quality", 90))


def run_selftest(config):
    install_rules(config)
    emit("started", pid=os.getpid())
    handle = None
    for command in commands():
        if command["cmd"] == "open":
            handle = open(command["path"], "xb", buffering=0)
            emit("opened")
        elif command["cmd"] == "write":
            for i in range(command["lines"]):
                handle.write(f"{i},line\n".encode())
                emit("wrote", n=i)
        elif command["cmd"] == "exit":
            os._exit(0)


def run_lock(config):
    path = config["path"]
    handle = open(path, "r+b")
    if sys.platform == "win32":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    emit("locked", t_ns=time.perf_counter_ns())
    released = threading.Event()

    def wait_command():
        for command in commands():
            if command["cmd"] == "release":
                released.set()
                return

    threading.Thread(target=wait_command, daemon=True).start()
    released.wait(config.get("hold_s", 3600.0))
    if sys.platform == "win32":
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    handle.close()
    emit("released", t_ns=time.perf_counter_ns())


def run_writer(config):
    import importlib

    module = importlib.import_module("skellycam.core.take_recorder")
    disk = install_rules(config)
    writer = module.CameraTakeWriter.start(config["spec"])
    emit("started", pid=os.getpid())
    for command in commands():
        cmd = command["cmd"]
        if cmd == "arm":  # add a fake disk rule now, for example after frame k was given
            add_rule(disk, command["rule"])
            emit("armed")
        elif cmd == "give":
            every = command.get("missing_every", 0)  # T-REC-KILL: every second item a placeholder
            for k in range(command["k_from"], command["k_to"]):
                if every and k % every == every - 1:
                    try:
                        writer.give_missing()
                    except (module.RecorderStalled, module.RecorderWriteError) as error:
                        emit("stalled" if isinstance(error, module.RecorderStalled) else "write_error", k=k)
                        break
                    emit("gave", k=k, missing=True)
                    continue
                payload = frame_payload(config, k)
                arrival = time.perf_counter_ns()
                frame = module.RecorderFrame(payload=payload, frame_number=k, arrival_ns=arrival,
                                             sample_ns=arrival - 500_000, source_frame_number=1000 + k,
                                             flags=0, delivered_len=len(payload), rotation_cw_deg=0)
                started = time.monotonic()
                try:
                    writer.give(frame)
                except module.RecorderStalled:
                    emit("stalled", k=k, waited_s=time.monotonic() - started)
                    break
                except module.RecorderWriteError as error:
                    emit("write_error", k=k, text=str(error))
                    break
                emit("gave", k=k)
        elif cmd == "give_missing":
            for _ in range(command["n"]):
                writer.give_missing()
            emit("gave_missing", n=command["n"])
        elif cmd == "end":
            started = time.monotonic()
            result = writer.end(command["frame_count"])
            emit("result", end_s=time.monotonic() - started, **result_fields(result))
        elif cmd == "exit":
            os._exit(0)


def percentiles(values):
    if not values:
        return {"p50": None, "p99": None, "p999": None, "max": None}
    ordered = sorted(values)

    def at(q):
        return ordered[min(len(ordered) - 1, int(q * (len(ordered) - 1) + 0.5))]

    return {"p50": at(0.5), "p99": at(0.99), "p999": at(0.999), "max": ordered[-1]}


def run_paced(config):
    """Section 11: source thread, loop thread and (with `writer_on`) the writer of the product.

    One thread reads standard input: `stop` ends the run early (the parent ends the take, 5.3), and
    `end` gives the frame count of the take after the event `done`."""
    import importlib
    import queue

    import psutil

    module = importlib.import_module("skellycam.core.take_recorder") if config["writer_on"] else None
    disk = install_rules(config) if config.get("root") else None
    real_fsync, fsync_ns = os.fsync, []

    def timed_fsync(fd):
        started = time.perf_counter_ns()
        if config.get("fsync_on", True):
            real_fsync(fd)  # T-REC-FSYNC "off": the writer's fsync does nothing
        fsync_ns.append(time.perf_counter_ns() - started)

    os.fsync = timed_fsync
    num, den = config["rate"]
    period_ns = 10**9 * den // num
    pool = [frame_payload(config, k) for k in range(config.get("pool", 30))]
    writer = module.CameraTakeWriter.start(config["spec"]) if module else None
    place = {"frame": None, "replaced": 0}
    condition = threading.Condition()
    schedule, arrivals, steps = [], [], []
    stop, inbox, state = threading.Event(), queue.Queue(), {"given": 0, "stalled_at": None}

    def read_commands():
        for command in commands():
            if command["cmd"] == "stop":
                stop.set()
            inbox.put(command)

    def source():
        t0 = time.perf_counter_ns() + 50_000_000
        i = 0
        while not stop.is_set():
            due = t0 + i * period_ns
            delay = (due - time.perf_counter_ns()) / 1e9
            if delay > 0:
                time.sleep(delay)
            arrival = time.perf_counter_ns()
            with condition:
                if place["frame"] is not None:
                    place["replaced"] += 1
                place["frame"] = (i, due, arrival, pool[i % len(pool)])
                condition.notify()
            i += 1

    def loop():
        while not stop.is_set():
            with condition:
                while place["frame"] is None and not stop.is_set():
                    condition.wait(0.5)
                if stop.is_set():
                    return
                i, due, arrival, payload = place["frame"]
                place["frame"] = None
            taken = time.perf_counter_ns()
            schedule.append(due)
            arrivals.append(arrival)
            if writer is not None:
                given = state["given"]
                frame = module.RecorderFrame(payload=payload, frame_number=given, arrival_ns=arrival,
                                             sample_ns=arrival, source_frame_number=i, flags=0,
                                             delivered_len=len(payload), rotation_cw_deg=0)
                stall = config.get("stall")
                if stall and disk is not None and given == stall["at_frame"]:
                    disk.stall(".mkv", stall["seconds"])
                try:
                    writer.give(frame)
                except module.RecorderStalled:
                    state["stalled_at"] = given
                    emit("stalled", k=given)
                    stop.set()
                    return
                except module.RecorderWriteError as error:
                    emit("write_error", k=given, text=str(error))
                    stop.set()
                    return
            steps.append(time.perf_counter_ns() - taken)
            state["given"] += 1

    threading.Thread(target=read_commands, daemon=True).start()
    threads = [threading.Thread(target=source, name="source"), threading.Thread(target=loop, name="loop")]
    for thread in threads:
        thread.start()
    emit("started", pid=os.getpid())
    stop.wait(config["seconds"])
    stop.set()
    for thread in threads:
        thread.join(30.0)
    emit("done", given=state["given"], stalled_at=state["stalled_at"])
    result = None
    if writer is not None:
        while True:
            command = inbox.get()
            if command["cmd"] == "end":
                result = writer.end(command["frame_count"])
                break
    lateness = [a - d for a, d in zip(arrivals, schedule)]
    intervals = [b - a for a, b in zip(arrivals, arrivals[1:])]
    writes = disk.write_ns if disk is not None else []
    cpu = psutil.Process().cpu_times()
    emit("summary", given=state["given"], replaced=place["replaced"], lateness_ns=percentiles(lateness),
         interval_jitter_ns=percentiles([abs(x - period_ns) for x in intervals]), loop_step_ns=percentiles(steps),
         write_ns=percentiles([d for kind, d in writes if kind == ".mkv"]),
         row_write_ns=percentiles([d for kind, d in writes if kind == ".csv"]), fsync_ns=percentiles(fsync_ns),
         cpu_s=cpu.user + cpu.system, result=result_fields(result) if result is not None else None)
    sys.stdout.flush()
    os._exit(0)


def main():
    with open(sys.argv[1], "rb") as handle:
        config = pickle.load(handle)
    {"selftest": run_selftest, "lock": run_lock, "writer": run_writer, "paced": run_paced}[config["mode"]](config)


if __name__ == "__main__":
    main()
