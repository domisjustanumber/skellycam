"""The caller part of a certify run of skellycam (specs/certify.md 2.1, 2.5, 4.1, 8.3, 9; contract `report-format.md`
of `skellycertify`, format 1.7.0): the plan, the progress, the cancel, the time limits, phase G, the local record and
the module report.

The caller imports no `comtypes` and opens no camera. The camera steps (`session.py`) run in a spawn session child
with the product `CameraGroupManager` and its camera processes. A test can give `manager` (the session then runs in
a thread of the test process) or a picklable `source_factory` (fake sources in the session child).
"""

import asyncio
import contextlib
import dataclasses
import datetime
import getpass
import json
import logging
import multiprocessing
import os
import platform
import queue
import re
import shutil
import socket
import tempfile
import threading
import time
import uuid
from pathlib import Path

import psutil

from skellycam.core.camera.capture import camera_checks
from skellycam.core.camera.capture.source import CaptureRequest, ControlSetting
from skellycam.core.certify import catalog
from skellycam.core.certify.session import Stopped, Unit, run_session

logger = logging.getLogger(__name__)

SCHEMA = "skellycertify.report/1.7.0"  # 3.6.1
LEVELS = ("quick", "full")
QUICK_BUDGET_S = 30.0  # 4.1
FULL_SESSION_LIMIT_S = 240.0  # 9.3: the limit of a camera block, for the session of this step
DETECT_LIMIT_S = 20.0  # 9.3
RECHECK_LIMIT_S = 5.0  # 8.3: after a cancel, at most 5 s for each touched camera
RECHECK_CRASH_LIMIT_S = 20.0  # 8.3: after a crash or a time-out, at most 20 s for each camera
GRACE_S = 12.0  # 9.3: after a time-out, the camera processes get this long to finish and restore
EXIT_LIMIT_S = 5.0
ACK_POLL_S = 1.0  # the session child looks for a dead caller at least this often
CALLER_GONE_CLOSE_S = 15.0  # the session child closes its group within this time after its caller died
LOCK_FILE = "certify.lock"  # 9.5: one run at a time, beside the record in the base folder
# 9.3: the product closes the camera processes one after the other: a join of 3 s, a terminate and 3 s, a kill and 2 s
CLOSE_BASE_S, CLOSE_PER_CAMERA_S = 5.0, 8.0
PROGRESS_GAP_S = 0.1  # 9.6: at most 10 messages each second
MARKER = ".skellycam-certify"  # 9.5
STOPS = {"cancelled": "cancelled", "abandoned": "cancelled", "over-budget": "over-budget"}  # stop: reason
QUESTIONS = [{"section": None, "id": "lit-as-usual", "text": "Was the room lit as it is when you record?"},
             {"section": None, "id": "all-cameras", "text": "Were all the cameras that you record with attached?"}]
QUESTION_FULL = {"section": None, "id": "camera-ok-after",
                 "text": "Do all the cameras still work in other programs after the run?"}
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
COMMIT = re.compile(r"[0-9a-f]{40}")
BUILD_INFO = Path(__file__).resolve().parents[2] / "build_info.json"  # 3.5.2: `skellycam/build_info.json` (P7)


# ---------------------------------------------------------------------------
# The public functions (C 2.1, C 2.6, C 2.8; certify.md 1, 9.1)
# ---------------------------------------------------------------------------

def certify(level: str, progress=None, cancel=None, *, cameras=None, recording_folder=None,
            test_media_dir=None, abandon=None) -> dict:
    """Run the certify checks of skellycam and return one module report. skellycam reads and writes nothing in
    `test_media_dir` (2.4). `abandon` (C 1.6.0 2.4) stops the run as a cancel does, and the run stores no result."""
    return run(level, progress, cancel, cameras=cameras, recording_folder=recording_folder, abandon=abandon)


def certify_plan(level: str, *, cameras=None, recording_folder=None, test_media_dir=None) -> dict:
    """The plan of a run (9.1). It opens no camera and activates no device."""
    return plan(level, cameras=cameras)


def _check_level(level):
    if level not in LEVELS:
        raise ValueError(f"level must be 'quick' or 'full', not {level!r}")


def _version() -> str:
    import skellycam
    return skellycam.__version__.lstrip("v")


def _private_terms() -> tuple:
    terms = []
    for get in (getpass.getuser, socket.gethostname):
        with contextlib.suppress(Exception):
            terms.append(get())
    return tuple(terms)


def _enumerate(backend: str) -> list:
    """The device list with no activation (cap 6.2 step 1); Linux and macOS: the native detection is not built."""
    if backend != "media-foundation":
        return []
    from skellycam.core.camera.capture.media_foundation.detect import detect_media_foundation_cameras
    try:
        return detect_media_foundation_cameras(modes=False)
    except Exception as error:
        logger.warning(f"certify plan: the device list failed: {error!r}")
        return []


class _Context:
    """The cameras of a run or a plan: labels, cleaned names, models, the record and the evidence file."""

    def __init__(self, level, devices, cameras, backend, checks_path, evidence_path, os_key, abi, private_terms):
        self.level, self.backend = level, backend
        self.os_key, self.abi = os_key or camera_checks.current_os_key(), abi or camera_checks.current_abi()
        terms = _private_terms() if private_terms is None else private_terms
        rows, evidence = camera_checks.read_rows(checks_path), camera_checks.read_evidence(evidence_path)
        self.cameras, self.models = [], {}
        for unit_label, device in catalog.camera_labels(devices, backend):
            key = catalog.device_key(device)
            name = catalog.clean_name(device.name, key, terms)
            record_key = key or f"nousb:{name}"
            model = unit_label.rsplit(".", 1)[0]
            info = dict(label=unit_label, name=name, device=key, record_key=record_key, model=model, raw=device,
                        evidence=camera_checks.evidence_state(evidence, key, backend, self.os_key, self.abi)
                        if key else "unknown",
                        checked=camera_checks.checked(rows, record_key, backend, self.os_key, self.abi),
                        base=catalog.base_mode(device))
            self.cameras.append(info)
            self.models.setdefault(model, dict(module=name, device=key, record_key=record_key, units=[]))
            self.models[model]["units"].append(info)
        self.virtual = sum(1 for d in devices if d.virtual)
        selected = set(cameras) if cameras is not None else None
        self.reviewed = [] if selected is not None or level == "full" else [
            model for model, m in self.models.items() if m["units"][0]["evidence"] == "verified"]
        self.units = [c for c in self.cameras if (selected is None and c["model"] not in self.reviewed)
                      or (selected is not None and c["label"] in selected)]
        for c in self.units:
            c["module"], c["selected"] = self.models[c["model"]]["module"], True
        self.checked_models = list(dict.fromkeys(c["model"] for c in self.units))

    def unit_specs(self):
        return [(c["label"], c["base"], c["module"]) for c in self.units]


def plan(level, *, cameras=None, devices=None, checks_path=None, evidence_path=camera_checks.EVIDENCE_PATH,
         os_key=None, abi=None, private_terms=None) -> dict:
    _check_level(level)
    backend = catalog.system_backend()
    if devices is None:
        devices = _enumerate(backend)
    context = _Context(level, devices, cameras, backend, checks_path, evidence_path, os_key, abi, private_terms)
    checks = [name for name, _ in catalog.planned_checks(level, context.unit_specs(), backend)]
    unchecked = [dict(label=m["units"][0]["label"], name=m["module"], device=m["device"])
                 for model, m in context.models.items()
                 if not m["units"][0]["checked"] and m["units"][0]["evidence"] != "verified"]
    risks = [] if level == "quick" else [catalog.RISK] + ([catalog.RISK_MACOS] if backend == "avfoundation" else [])
    systems = camera_checks._read(evidence_path, "systems", lambda data: data.get("schema") == 1)
    system = next((r for r in reversed(systems) if (r.get("os_key"), r.get("backend")) == (context.os_key, backend)
                   and r.get("state") in ("verified", "known-bad")), None)
    return {
        "package": "skellycam",
        "kind": level,
        "seconds_estimate": catalog.seconds_estimate(level, len(context.units), len(context.checked_models)),
        # 3.6.1: with `session:exit`, when a session child runs
        "total": len(checks) + 1 if context.units else len(checks) if level == "full" else 0,
        "risks": risks,
        "downloads": [],
        "system_changes": [],
        "questions": QUESTIONS + ([QUESTION_FULL] if level == "full" else []),
        "details": {
            "cameras": [dict(label=c["label"], name=c["name"], device=c["device"], evidence=c["evidence"],
                             checked=c["checked"]) for c in context.cameras],
            "unchecked": unchecked,
            "system_evidence": system["state"] if system else "unknown",
            "virtual": context.virtual,
            "checks": checks,
        },
    }


# ---------------------------------------------------------------------------
# Progress (C 2.3, 9.6)
# ---------------------------------------------------------------------------

class _Progress:
    def __init__(self, callback, level, total=None):
        self.callback, self.level, self.total = callback, level, total
        self.last = 0.0
        self.broken = False
        self.session = False  # 3.6.1: the plan counts the end of the session child (`session:exit`) as one check
        self.ended = False
        self.named: set[str] = set()  # each check that a progress message named (3.6.1 `not-reached`)

    def done(self, rows) -> int:
        """3.6.1: the ended checks; a `<label>:not-reached` row counts as the checks that it stands for, and the end
        of the session child counts as one, with or without a `session:exit` row, so `done` equals `total` at the
        end."""
        return sum((r.get("numbers") or {}).get("checks", 1) if name.endswith(":not-reached") else 1
                   for name, r in rows.items() if r is not None and name != "session:exit") + (
            1 if self.session and self.ended else 0)

    def send(self, state, rows, step=None):
        if step is not None:
            self.named.add(step)
        if self.callback is None or self.broken:
            return
        wait = self.last + PROGRESS_GAP_S - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        checks = [dict(section=None, name=name, result=None) if r is None else dict(r, section=None)
                  for name, r in rows.items()]
        message = {"package": "skellycam", "kind": self.level, "state": state,
                   "step": None if step is None else {"section": None, "name": step}, "checks": checks,
                   "done": self.done(rows), "total": self.total, "seconds_left": None}
        self.last = time.monotonic()
        try:
            self.callback(message)
        except Exception as error:  # C 2.3: stop calling it and go on
            logger.warning(f"certify: the progress callable raised {type(error).__name__}; no more progress")
            self.broken = True
        except BaseException:  # for example KeyboardInterrupt: it goes to the caller, and the run stops its session
            self.broken = True
            raise


# ---------------------------------------------------------------------------
# The session in a spawn child, or in a thread (2.1)
# ---------------------------------------------------------------------------

def kill_tree(pid: int) -> None:
    """Kill a process and each of its children (C 2.4, C 2.5)."""
    try:
        parent = psutil.Process(pid)
        processes = parent.children(recursive=True) + [parent]
    except psutil.NoSuchProcess:
        return
    _kill(processes)


def _kill(processes) -> None:
    for process in processes:
        with contextlib.suppress(psutil.NoSuchProcess):
            process.kill()
    psutil.wait_procs(processes, timeout=5)


def _watch_caller(parent, kill, manager, loop_box) -> None:
    """2.1: the session child must not outlive its caller. On the death of the caller: set the kill flag (each camera
    loop ends and its close restores the camera), close the group within a limit, and end the child."""
    from multiprocessing.connection import wait

    wait([parent.sentinel])
    logger.warning("certify: the caller of the session ended; the session closes its cameras and ends")
    kill.value = True
    loop = loop_box.get("loop")
    if loop is not None and loop.is_running():
        with contextlib.suppress(Exception):
            asyncio.run_coroutine_threadsafe(manager.close_all_camera_groups(), loop).result(CALLER_GONE_CLOSE_S)
    os._exit(3)


def _session_child(events, acks, units, work, level, unix, source_factory) -> None:
    """The session child: one `CameraGroupManager` with real camera processes and the native source (2.1)."""
    from skellycam.core.camera_group.camera_group_manager import CameraGroupManager
    from skellycam.core.ipc.process_management.managed_worker import WorkerMode
    from skellycam.core.ipc.process_management.worker_registry import WorkerRegistry

    if source_factory is None:  # 2.1: certify always uses the native source
        os.environ["SKELLYCAM_WINDOWS_CAPTURE"] = "media_foundation"
    # 9.5: the log file of each camera process goes into the work folder (a log folder that the caller set stays)
    os.environ.setdefault("SKELLYLOGS_LOG_DIR", str(Path(work) / "logs"))
    # The product makes a camera group only in a main process (`parent_process() is None`, the pubsub guards). The
    # session child is the main process of its camera processes (2.1), so it clears its own parent mark. It keeps the
    # handle of its caller first: `_watch_caller` ends the child when the caller dies.
    parent = multiprocessing.parent_process()
    multiprocessing.process._parent_process = None
    from skellylogs import configure_logging
    from skellylogs.handlers.websocket_log_queue_handler import create_websocket_log_queue

    from skellycam import LOG_LEVEL
    # as a camera process does (managed_worker.py): the custom levels, and the log queue of the logs topic
    configure_logging(LOG_LEVEL, ws_queue=create_websocket_log_queue(), use_file_handler=False)
    error = None
    registry = None
    try:
        kill = multiprocessing.Value("b", False)
        registry = WorkerRegistry(global_kill_flag=kill, worker_mode=WorkerMode.PROCESS)
        registry.start_heartbeat()
        manager = CameraGroupManager(global_kill_flag=kill, worker_registry=registry, source_factory=source_factory)
        manager.detected_cameras = {unit.camera_id: unit.device for unit in units}
        loop_box = {}
        if parent is not None:
            threading.Thread(target=_watch_caller, args=(parent, kill, manager, loop_box), name="certify caller watch",
                             daemon=True).start()

        def begin(name):
            events.put(("begin", name))
            while True:  # a bounded wait: a caller that died gives no answer
                try:
                    ok = acks.get(timeout=ACK_POLL_S)
                    break
                except queue.Empty:
                    if parent is not None and not parent.is_alive():
                        raise Stopped() from None
            if not ok:
                raise Stopped()

        async def main():
            loop_box["loop"] = asyncio.get_running_loop()
            await run_session(manager, units, work, level, unix, begin, lambda r: events.put(("done", r)),
                              lambda kind, value: events.put(("fact", (kind, value))), time.sleep)

        asyncio.run(main())
    except Stopped:
        pass
    except BaseException as caught:  # a fault of the session: its class name is the reason (15)
        logger.exception("certify: the session failed")
        error = type(caught).__name__
    finally:
        if registry is not None:
            with contextlib.suppress(Exception):
                registry.shutdown_all()
        events.put(("end", error))


class _ChildSession:
    def __init__(self, units, work, level, unix, source_factory):
        context = multiprocessing.get_context("spawn")
        self.events, self.acks = context.Queue(), context.Queue()
        self.process = context.Process(target=_session_child, name="skellycam certify session",
                                       args=(self.events, self.acks, units, work, level, unix, source_factory))
        self.process.start()
        self.tree: dict[int, psutil.Process] = {}  # each process of the tree that the caller has seen
        self.closed = False

    def alive(self):
        return self.process.is_alive()

    def remember(self):
        """Keep the camera processes of the child: after the child ends, its children have no parent to find."""
        with contextlib.suppress(psutil.Error):
            for process in psutil.Process(self.process.pid).children(recursive=True):
                self.tree.setdefault(process.pid, process)

    def ack(self, ok):
        self.acks.put(ok)

    def _left(self):
        return [p for p in self.tree.values() if p.is_running()]

    def stop(self, mode="kill"):
        """`kill`: the tree at once (a cancel, the end of the budget, C 2.4). `grace`: 9.3, the main process of the
        child first; each camera process sees the dead server, finishes its files and restores its camera; after
        GRACE_S the rest of the tree is killed. Nothing is left after a stop."""
        self.remember()
        if self.process.is_alive():
            if mode == "kill":
                kill_tree(self.process.pid)
            else:
                self.process.kill()
        if mode == "grace":
            with contextlib.suppress(psutil.Error):
                psutil.wait_procs(self._left(), timeout=GRACE_S)
        _kill(self._left())

    def exit_code(self):
        return self.process.exitcode

    def finish(self) -> bool:
        """True when the child gave its result and did not end (C 2.5 `exit`)."""
        self.process.join(EXIT_LIMIT_S)
        hung = self.process.is_alive()
        if hung:
            self.stop("kill")
        self.process.join(EXIT_LIMIT_S)
        if not self.closed:
            self.closed = True
            for channel in (self.events, self.acks):
                channel.close()
                channel.cancel_join_thread()
        return hung


class _ThreadSession:
    """The session in a thread of this process, for the tests (no kill: a stop takes effect at the next `begin`)."""

    def __init__(self, manager, units, work, level, unix, sleep):
        self.events, self.acks, self.stopped = queue.Queue(), queue.Queue(), threading.Event()

        def begin(name):
            if self.stopped.is_set():
                raise Stopped()
            self.events.put(("begin", name))
            if not self.acks.get():
                raise Stopped()

        def target():
            error = None
            try:
                asyncio.run(run_session(manager, units, work, level, unix, begin,
                                        lambda r: self.events.put(("done", r)),
                                        lambda kind, value: self.events.put(("fact", (kind, value))), sleep))
            except Stopped:
                pass
            except BaseException as caught:
                logger.exception("certify: the session failed")
                error = type(caught).__name__
            self.events.put(("end", error))

        self.thread = threading.Thread(target=target, name="certify session", daemon=True)
        self.thread.start()

    def alive(self):
        return self.thread.is_alive()

    def remember(self):
        pass

    def ack(self, ok):
        self.acks.put(ok)

    def stop(self, mode="kill"):
        self.stopped.set()
        self.acks.put(False)

    def exit_code(self):
        return None

    def finish(self) -> bool:
        self.thread.join(120)
        return False


class _Stops:
    """The stop of the caller: `abandoned` (C 1.6.0 2.4: it wins over a cancel), `cancelled`, or None."""

    def __init__(self, cancel, abandon):
        self.cancel, self.abandon = cancel, abandon

    def cause(self):
        if self.abandon is not None and _is_set(self.abandon):
            return "abandoned"
        if self.cancel is not None and _is_set(self.cancel):
            return "cancelled"
        return None


@dataclasses.dataclass
class _Driven:
    current: str | None
    stop: str | None
    error: str | None
    facts: dict
    pending: list  # each check that started and has no result, in order
    closing: bool = False  # the session started the close of its group
    clean: bool = False  # the session closed its group itself and ended: the close restored each camera


def _drive(session, rows, reporter, stops, deadline, over, close_limit_s=CLOSE_BASE_S) -> _Driven:
    """Serve the session until its end, a stop of the caller or the end of the time (9.3)."""
    out = _Driven(None, None, None, dict(touched=[], before={}, release={}, prior={}), [])
    stopped = False

    def handle(kind, value, *, before_stop):
        if kind == "begin":
            if out.stop is not None:
                session.ack(False)
                return
            out.current = value
            reporter.send("running", rows, step=value)
            cause = stops.cause()
            if cause is not None:  # a stop during the progress call: the check does not start
                out.stop = cause
                return
            out.pending.append(value)
            session.ack(True)
        elif kind == "done" and (out.stop is None or before_stop):  # C 2.4: a check that had ended keeps its result
            rows[value["name"]] = value
            if value["name"] in out.pending:
                out.pending.remove(value["name"])
        elif kind == "fact":
            name, item = value
            if name == "closing":
                out.closing = True
                closing_at[0] = time.monotonic()
            elif name == "touched":
                out.facts["touched"] += item
            elif name in ("before", "release", "prior"):
                out.facts[name].setdefault(item[0], item[1])

    last_seen = 0.0
    closing_at = [None]
    deferred = None
    while True:
        if out.stop is None:
            cause = stops.cause() or (over if time.monotonic() > deadline else None)
            if cause is not None and closing_at[0] is not None and time.monotonic() < closing_at[0] + close_limit_s:
                deferred = cause  # N3: never kill a camera in the middle of its restore; wait for the close
            elif cause is not None:
                out.stop = cause
        if out.stop is not None and not stopped:
            stopped = True
            while True:  # the events that came before the stop
                try:
                    kind, value = session.events.get_nowait()
                except (queue.Empty, EOFError, OSError):
                    break
                if kind == "end":
                    break
                handle(kind, value, before_stop=True)
            session.stop("grace" if out.stop == "timed-out" else "kill")
        if time.monotonic() - last_seen > 1.0:
            session.remember()
            last_seen = time.monotonic()
        try:
            kind, value = session.events.get(timeout=0.2)
        except queue.Empty:
            if not session.alive():
                out.stop = out.stop or "crashed"
                break
            continue
        except (EOFError, OSError):
            out.stop = out.stop or "crashed"
            break
        if kind == "end":
            if value is not None and out.stop is None:
                out.stop, out.error = "crashed", value
            out.clean = out.closing and value is None  # the close of the group ran to its end
            if out.stop is None:
                out.stop = stops.cause() or deferred
            break
        handle(kind, value, before_stop=False)
    return out


def _is_set(flag) -> bool:
    try:
        return bool(flag.is_set())
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Phase G after a stop, a time-out or a crash (8.3)
# ---------------------------------------------------------------------------

def recheck(source, request, before) -> str:
    """A plain open; a control that differs from its first "before" value is set back. Returns `healthy`,
    `restored` or `not-restored`; an open that fails raises."""
    source.open(request)
    try:
        now = source.set_controls({})
        changes = {name: ControlSetting(auto=b["auto"], value=b["value"]) for name, b in before.items()
                   if name in now and now[name].present and (now[name].auto != b["auto"]
                                                             or (not b["auto"] and now[name].value != b["value"]))}
        if not changes:
            return "healthy"
        got = source.set_controls(changes)
        ok = all(got[name].auto == s.auto and (s.auto or got[name].value == s.value) for name, s in changes.items())
        return "restored" if ok else "not-restored"
    finally:
        source.close(restore=False)


def _recheck_child(source_factory, config, request, before, sender) -> None:
    from skellycam.core.camera.camera_worker import media_foundation_process

    try:
        with media_foundation_process(source_factory is None):
            if source_factory is None:
                from skellycam.core.camera.capture.media_foundation.source import MediaFoundationSource
                source = MediaFoundationSource()
            else:
                source = source_factory(config)
            sender.send(recheck(source, request, before))
    except BaseException:
        sender.send("replug")


def _recheck(unit: Unit, before: dict, source_factory, manager, limit_s: float) -> str:
    """One camera, at most `limit_s` from the start of its child: in a spawn child (its process tree is killed at the
    limit), or in a thread with the source factory of the test manager."""
    from skellycam.core.camera.config.camera_config import CameraConfig
    from skellycam.core.camera.config.image_resolution import ImageResolution

    width, height, rate = unit.base
    config = CameraConfig(camera_id=unit.camera_id, camera_index=unit.index,
                          resolution=ImageResolution(width=width, height=height), framerate=rate)
    request = CaptureRequest(camera_id=unit.camera_id, width=width, height=height, framerate=rate)
    if manager is not None:
        box = []

        def target():
            try:
                box.append(recheck(manager.source_factory(config), request, before))
            except BaseException:
                box.append("replug")
        thread = threading.Thread(target=target, name="certify recheck", daemon=True)
        thread.start()
        thread.join(limit_s)
        return box[0] if box else "replug"
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    child = context.Process(target=_recheck_child, args=(source_factory, config, request, before, sender),
                            name="skellycam certify recheck")
    child.start()
    sender.close()
    try:
        return receiver.recv() if receiver.poll(limit_s) else "replug"
    except EOFError:
        return "replug"
    finally:
        receiver.close()
        child.join(1.0)
        if child.is_alive():
            kill_tree(child.pid)


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------

def _work_folder(recording_folder) -> Path:
    """9.5: a new marked work folder; earlier marked folders of certify go first (the run lock makes them old)."""
    root = Path(recording_folder) if recording_folder is not None else Path(tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    for old in root.glob("skellycam-certify-*"):
        if (old / MARKER).exists():
            shutil.rmtree(old, ignore_errors=True)
    work = root / f"skellycam-certify-{uuid.uuid4()}"
    work.mkdir()
    (work / MARKER).write_text("", encoding="utf-8")
    return work


def _run_lock(checks_path: Path, stack: contextlib.ExitStack) -> str | None:
    """9.5: one run at a time. The lock file is beside the record in the base folder; the OS frees it when the
    process ends. None when the run holds the lock; `cameras-busy` when another run holds it; else the class name
    of the error of the lock file."""
    from skellycam.core.take_recorder import folder_files

    path = checks_path.with_name(LOCK_FILE)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
        stack.enter_context(folder_files.take_lock(path, 0.0))
        return None
    except TimeoutError:
        return "cameras-busy"
    except OSError as error:
        return type(error).__name__


def _group_open() -> bool:
    """9.7: a camera group of skellycam is open in the calling process."""
    module = __import__("sys").modules.get("skellycam.core.camera_group.camera_group_manager")
    manager = getattr(module, "_CAMERA_GROUP_MANAGER", None) if module is not None else None
    return bool(manager is not None and manager.camera_groups)


def _detect(backend, stops, deadline, over, modes=True):
    """(the `detect` row or None, the devices). Windows: the product detection, which has its own child (cap 7.1). It
    ends at its limit of 20 s, at the end of the budget or at a stop of the caller."""
    if backend != "media-foundation":
        return dict(name="detect", result="not-run", reason="not-built"), []
    from skellycam.core.camera.capture.media_foundation import detect

    box = {}

    def target():
        try:
            box["devices"] = detect.detect_media_foundation_cameras(modes=modes)
        except BaseException as error:
            box["error"] = error
    t0 = time.monotonic()
    limit = min(DETECT_LIMIT_S, max(0.0, deadline - t0))
    thread = threading.Thread(target=target, name="certify detection", daemon=True)
    thread.start()
    while thread.is_alive() and time.monotonic() - t0 < limit and stops.cause() is None:
        thread.join(0.05)
    if "devices" in box:
        return None, box["devices"]
    error = box.get("error")
    if error is not None:
        return dict(name="detect", result="fail", reason="timed-out" if getattr(error, "code", None) == "hung"
                    else "crashed"), []
    if stops.cause() is not None:
        return dict(name="detect", result="not-run", reason="cancelled"), []
    if limit < DETECT_LIMIT_S:
        return dict(name="detect", result="not-run", reason=over), []
    return dict(name="detect", result="fail", reason="timed-out"), []


def _detect_row(devices, seconds):
    return dict(name="detect", result="pass", reason=None,
                numbers=dict(seconds=round(seconds, 2), cameras=sum(1 for d in devices if not d.virtual),
                             virtual=sum(1 for d in devices if d.virtual),
                             modes_read=all(d.modes_read for d in devices if not d.virtual)))


def _host() -> dict:
    system = platform.system()
    name = {"Windows": "Windows", "Linux": "Linux", "Darwin": "macOS"}.get(system)
    machine = platform.machine().lower()
    arch = {"amd64": "x86_64", "x86_64": "x86_64", "aarch64": "arm64", "arm64": "arm64"}.get(machine, machine or None)
    os_info = dict(name=name, release=platform.release() or None, version=platform.version() or None, build=None,
                   label=None, arch=arch)
    cpu = platform.processor() or None
    if system == "Windows":
        with contextlib.suppress(Exception):
            os_info["build"] = int(platform.version().split(".")[-1])
            os_info["label"] = f"Windows {camera_checks.current_os_key()}"
        with contextlib.suppress(Exception):
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                cpu = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
    elif system == "Darwin":
        os_info["label"] = f"macOS {platform.mac_ver()[0]}"
    elif system == "Linux":
        with contextlib.suppress(Exception):
            os_info["label"] = platform.freedesktop_os_release().get("PRETTY_NAME")
        with contextlib.suppress(Exception):
            cpu = next(line.split(":", 1)[1].strip() for line in Path("/proc/cpuinfo").read_text().splitlines()
                       if line.startswith("model name"))
    memory = None
    with contextlib.suppress(Exception):
        memory = int(psutil.virtual_memory().total)
    return dict(os=os_info, cpu=dict(name=cpu), memory_bytes=memory)


def run(level, progress=None, cancel=None, *, cameras=None, recording_folder=None, abandon=None, devices=None,
        manager=None, source_factory=None, sleep=time.sleep, checks_path=None,
        evidence_path=camera_checks.EVIDENCE_PATH, os_key=None, abi=None, budget_s=None, private_terms=None) -> dict:
    """`certify()` with the seams of the tests: `devices` (the detection result), `manager` (a session in a thread
    of this process), `source_factory` (the fakes of a session child), the paths of the record and the evidence
    file, the OS key and the ABI, and `budget_s` (the budget of quick, or the session limit of full)."""
    _check_level(level)
    start = time.monotonic()
    created = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    backend = catalog.system_backend()
    if checks_path is None:
        from skellycam.system.default_paths import get_default_skellycam_base_folder_path
        checks_path = Path(get_default_skellycam_base_folder_path()) / camera_checks.CHECKS_FILE
    checks_path = Path(checks_path)
    reporter = _Progress(progress, level)
    reporter.send("starting", {})
    stops = _Stops(cancel, abandon)
    limit = budget_s if budget_s is not None else QUICK_BUDGET_S if level == "quick" else FULL_SESSION_LIMIT_S
    out = dict(rows={"detect": None}, reasons=[], cleanup=[], notices=[], summary=[], context=None, stop=None)
    work = None
    with contextlib.ExitStack() as stack:
        refused = _run_lock(checks_path, stack)
        try:
            if refused is None:
                work = _work_folder(recording_folder)
            _run(out, level, reporter, stops, cameras, devices, manager, source_factory, sleep, checks_path,
                 evidence_path, os_key, abi, private_terms, backend, work, refused, start + limit,
                 "over-budget" if level == "quick" else "timed-out")
        finally:
            reporter.ended = True
            reporter.send("cleaning-up", out["rows"])
            if work is not None:
                shutil.rmtree(work, ignore_errors=True)
                if work.exists():
                    out["cleanup"].append(_row("delete-work-folder", "fail", "not-deleted"))
    report = _report(level, created, out, backend)
    reporter.send("done", out["rows"])
    return report


def _unit_of(name, units):
    return next((unit.label for unit in units if name.startswith(unit.label + ":")), None)


def _run(out, level, reporter, stops, cameras, devices, manager, source_factory, sleep, checks_path, evidence_path,
         os_key, abi, private_terms, backend, work, refused, deadline, over):
    unix = backend != "media-foundation"
    refused = refused or ("cameras-busy" if _group_open() else None)
    busy = refused is not None
    reporter.send("running", out["rows"], step="detect")
    t0 = time.monotonic()
    detect_row = None
    if devices is None:
        detect_row, devices = _detect(backend, stops, deadline, over, modes=not busy)
    context = out["context"] = _Context(level, devices, cameras, backend, checks_path, evidence_path, os_key, abi,
                                        private_terms)
    planned = catalog.planned_checks(level, context.unit_specs(), backend)
    modules = dict(planned)
    rows = out["rows"] = {name: None for name, _ in planned}
    reporter.session = bool(context.units)
    reporter.total = len(rows) + (1 if context.units else 0)
    if busy:  # 9.5, 9.7: the run is refused; it opens no camera. No summary item, so no `module` (C 3.4)
        out["rows"] = {name: _row(name, "not-run", refused) for name in rows}
        out["reasons"].append(refused)
        return
    rows["detect"] = detect_row or _detect_row(devices, time.monotonic() - t0)
    stop = stops.cause() if rows["detect"]["reason"] == "cancelled" else None
    if rows["detect"]["reason"] == over:
        stop = over
    if rows["detect"]["result"] == "pass" and not any(not d.virtual for d in devices):
        out["reasons"].append("no-camera")
    units = [Unit(label=c["label"], camera_id=c["raw"].camera_id, index=c["raw"].index, base=c["base"],
                  module=c["module"], device=c["raw"]) for c in context.units]
    facts = dict(touched=[], before={}, release={}, prior={})
    if units and stop is None:
        session = (_ThreadSession(manager, units, work, level, unix, sleep) if manager is not None else
                   _ChildSession(units, work, level, unix, source_factory))
        try:
            driven = _drive(session, rows, reporter, stops, deadline, over,
                            CLOSE_BASE_S + CLOSE_PER_CAMERA_S * len(units))
            if session.finish() and driven.stop is None:
                rows["session:exit"] = _row("session:exit", "record-only", "hung-at-exit")
        finally:  # never leave the session behind (2.1): after an end it is a no-op
            session.stop("grace")
        stop, facts = driven.stop, driven.facts
    else:
        driven = None
    # N4: before `_blame`, so that a camera in the middle of its open does not count as judged
    judged = {unit.label for unit in units if rows.get(f"{unit.label}:opens") is not None}
    if driven is not None and stop in ("crashed", "timed-out"):
        _blame(rows, modules, driven, units, session.exit_code())
    # N2: a camera with a step running at the stop can be in a hang that the product has not yet declared
    running = set() if driven is None or driven.clean else {
        label for name in driven.pending for label in ([_unit_of(name, units)] if _unit_of(name, units) else
                                                        [unit.label for unit in units])}
    computed = {name for name in rows if name.endswith(":units") or ":gate" in name}
    filled = _fill(rows, modules, context, level, stop, facts["prior"], skip=computed)
    _not_reached(rows, context, reporter.named, filled)
    if stop not in STOPS:
        _computed_rows(rows, context, level, reporter)
    _fill(rows, modules, context, level, stop, facts["prior"], skip=set())
    out["summary"] = _summary(rows, context, level, unix)
    clean = driven is not None and driven.clean
    _phase_g(context, units, facts, stop, judged - running, clean, source_factory, manager, out["cleanup"],
             out["notices"])
    if stops.cause() == "abandoned":  # N5: an abandon that came late still stops each store of a result
        stop = "abandoned"
    out["stop"] = stop
    if stop in ("cancelled", "abandoned") and "cancelled" not in out["reasons"]:
        out["reasons"].append("cancelled")
    if stop in ("crashed", "timed-out", "abandoned"):  # C 1.6.0 2.4; a fault of the run blames no model
        return
    try:
        _write_record(rows, context, level, out["summary"], checks_path)
    except Exception as error:  # C 2.5: a failed cleanup step is a row, and the report still returns
        logger.exception("certify: the record of checked models could not be written")
        out["cleanup"].append(_row("write-record", "fail", type(error).__name__))


def _blame(rows, modules, driven, units, exit_code):
    """A crash or a time-out in the session. A crash is a fault of the session, never of a camera: each running check
    is `not-run` `crashed`. At a time-out the running check is `fail` only when the checks that ran belong to one
    camera (or to the group) and are not the open (the one apply for all cameras); else none is blamed."""
    pending = [name for name in driven.pending if rows.get(name) is None]
    if not pending and driven.current is not None and rows.get(driven.current) is None:
        pending = [driven.current]
    cause = driven.error or driven.stop
    open_names = {name for unit in units if unit.base is not None
                  for name in catalog.camera_names(unit.label, unit.base, "quick", False)["open"]}
    opening = any(name in open_names for name in pending)
    if driven.stop == "timed-out" and not opening and len({_unit_of(name, units) for name in pending}) == 1:
        numbers = {"exit_code": exit_code} if exit_code is not None and driven.error is None else {}
        rows[pending[0]] = _row(pending[0], "fail", cause, modules.get(pending[0]), **numbers)
    for name in pending:
        if rows.get(name) is None:
            rows[name] = _row(name, "not-run", cause, modules.get(name))


def _row(name, result, reason=None, module=None, **numbers) -> dict:
    out = dict(name=name, result=result, reason=reason)
    if module is not None:
        out["module"] = module
    if numbers:
        out["numbers"] = numbers
    return out


def _fill(rows, modules, context, level, stop, prior, skip):
    """Each planned check with no result: the stop cause (C 2.4, 4.1), or the reason that the session gave for its
    camera (`prior-failure`, `camera-in-use`, ...). A check with no code is not planned (3.6.1). Returns the names
    that it filled."""
    filled = set()
    for name in rows:
        if rows[name] is not None or name in skip:
            continue
        unit_label = next((c["label"] for c in context.units if name.startswith(c["label"] + ":")), None)
        if stop in STOPS:
            reason = STOPS[stop]
        elif unit_label in prior:
            reason = prior[unit_label]
        elif name.startswith("group:") and "group" in prior:
            reason = prior["group"]
        else:
            reason = "prior-check-failed"
        rows[name] = _row(name, "not-run", reason, modules.get(name))
        filled.add(name)
    return filled


NOT_REACHED = ("prior-check-failed", "prior-failure", "camera-in-use", "no-mjpg-mode", "cancelled", "over-budget",
               "interrupted")  # 3.6.1: the reasons of a camera that cannot go on


def _not_reached(rows, context, named, filled) -> None:
    """3.6.1: the filled rows of a camera (`_fill` wrote them; no step gave a result) with a reason of a camera that
    could not go on (NOT_REACHED) and that no progress message named give one row `<label>:not-reached` in their
    place, wherever they stand [ADR-0Z6Q item 11]: `not-run`, the reason of the first of them, the `module` of the
    camera and `numbers.checks`. The row stands at the place of the first of them. A check that a progress message
    named, and a row that the session gave, keep their own rows. A check counts as named when the run announced it,
    also with no progress callable [ADR-0Z6Q item 13]."""
    tails = {}
    for camera in context.units:
        tail = [name for name in rows if name.startswith(camera["label"] + ":") and name in filled
                and name not in named and rows[name]["result"] == "not-run" and rows[name]["reason"] in NOT_REACHED]
        if tail:
            tails[tail[0]] = (camera["label"], tail)
    if not tails:
        return
    merged = {}
    gone = {name for _, tail in tails.values() for name in tail}
    for name, r in rows.items():
        if name in tails:
            label, tail = tails[name]
            merged[f"{label}:not-reached"] = _row(f"{label}:not-reached", "not-run", r["reason"], r.get("module"),
                                                  checks=len(tail))
        if name not in gone:
            merged[name] = r
    rows.clear()
    rows.update(merged)


def _unit_rows(rows, unit_label):
    return {name: r for name, r in rows.items() if name.startswith(unit_label + ":") and r is not None}


def _selected(context, model):
    return [c for c in context.models[model]["units"] if c.get("selected")]


def _computed_rows(rows, context, level, reporter):
    """`<model>:units` (3.4) and, in full, the gate of 11.3: computed checks, each with its progress message (9.6)."""
    for model, m in context.models.items():
        name = f"{model}:units"
        if name not in rows:
            continue
        units = _selected(context, model)
        reporter.send("running", rows, step=name)
        opens = [rows.get(f"{c['label']}:opens") or {} for c in units]
        rows[name] = _row(name, "record-only", None, m["module"], units=len(m["units"]),
                          units_tested=sum(1 for r in opens if r.get("result") in ("pass", "fail")),
                          units_busy=sum(1 for r in opens if r.get("reason") == "camera-in-use"))
        if level != "full":
            continue
        for gate_row in catalog.gate_rows(model, [_unit_rows(rows, c["label"]) for c in units], m["module"]):
            reporter.send("running", rows, step=gate_row["name"])
            rows[gate_row["name"]] = gate_row


def _summary(rows, context, level, unix) -> list:
    """One `camera` item for each model (3.4), with the private key `_model` that the record uses."""
    items = []
    for model, m in context.models.items():
        item = dict(group="camera", name=m["module"], device=m["device"], _model=model)
        if model in context.reviewed:
            items.append(dict(item, result="skipped", reason="reviewed"))
            continue
        units = _selected(context, model)
        if not units:
            continue
        item["result"] = catalog.item_result([_unit_rows(rows, c["label"]) for c in units], unix=unix)
        if item["result"] == "skipped":
            item["reason"] = "busy"
        if level == "full":
            item["gate"] = f"{model}:gate"
        items.append(item)
    return items


def _phase_g(context, units, facts, stop, judged, clean, source_factory, manager, cleanup, notices):
    """8.3: a cleanup row and a notice for each camera that is not healthy after the run.

    When the session closed its group itself (`clean`), the close facts decide, as in quick with no stop. Else,
    after a stop, a time-out or a crash, each touched camera that is not wedged is judged again:
    - a camera whose `opens` has no result was in the middle of its open, and a camera with a step running at the
      stop can be in a hang that is not yet declared: it is never opened again, and it is `camera-not-restored`;
    - a camera in use by another program, or one with no known "before" values (no control was set), needs nothing;
    - else a plain open of at most 5 s (20 s after a crash or a time-out) sets each control back.
    """
    states = {label: "replug" if code == "camera-wedged" else "not-restored"
              for label, code in facts["release"].items()}
    if stop is not None and not clean:
        limit = RECHECK_CRASH_LIMIT_S if stop in ("crashed", "timed-out") else RECHECK_LIMIT_S
        for unit in units:
            if unit.label not in facts["touched"] or unit.label in states or unit.base is None:
                continue
            before = facts["before"].get(unit.label)
            if unit.label not in judged:
                states[unit.label] = "not-restored"
            elif before:
                state = _recheck(unit, before, source_factory, manager, limit)
                if state in ("replug", "not-restored"):
                    states[unit.label] = state
    names = {c["label"]: c["name"] for c in context.cameras}
    for unit in units:
        state = states.get(unit.label)
        if state is None:
            continue
        code = "camera-wedged" if state == "replug" else "camera-not-restored"
        cleanup.append(_row(f"release:{unit.label}", "fail", code, unit.module))
        notices.append({"code": code, "values": {"camera": names[unit.label]}})


def _write_record(rows, context, level, summary, checks_path):
    """2.5: one row for each model by the rule of `catalog.writes_row`, from the summary item of that model."""
    by_model = {item["_model"]: item for item in summary if item.get("reason") != "reviewed"}
    out = []
    date = datetime.date.today().isoformat()
    for model, m in context.models.items():
        units = _selected(context, model)
        item = by_model.get(model)
        if not units or item is None:
            continue
        opens = [(rows.get(f"{c['label']}:opens") or {}).get("result") for c in units]
        if not catalog.writes_row(item["result"], opens):
            continue
        gate = {step: rows[f"{model}:gate:{step}"]["result"] for step in catalog.GATE_STEPS} if level == "full" else None
        first = units[0]["label"]
        # 3.6.1: a settings check in the `not-reached` row is `not-run` with the reason of that row
        missing = rows.get(f"{first}:not-reached") or dict(result="not-run", reason="not-built")
        settings = [rows.get(f"{first}:settings-stick:{c}") or missing for c in ("readback", "holds", "image-effect")]
        path = (settings[0].get("numbers") or {}).get("control_path")
        result = catalog.control_result(settings[0].get("result"), settings[1].get("result"),
                                        {"result": settings[2].get("result"), "reason": settings[2].get("reason")})
        controls = {"exposure": {path: result}} if path not in (None, "none") and result else {}
        out.append(catalog.record_row(m["record_key"], context.backend, context.os_key, context.abi, level,
                                      item["result"], _version(), date, gate, controls))
    if out:
        catalog.write_record(checks_path, out)


def read_build_info(path) -> tuple:
    """3.5.2: (commit, tree_modified) from the build file that the wheel build writes (P7); (None, None) with no
    file, a file that does not parse or a file of another form. A run never reads git."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, None
    commit = data.get("commit") if isinstance(data, dict) else None
    modified = data.get("tree_modified") if isinstance(data, dict) else None
    if isinstance(commit, str) and COMMIT.fullmatch(commit) and isinstance(modified, bool):
        return commit, modified
    return None, None


def build_values(path) -> tuple:
    """3.5.2: (commit, tree_modified) of the build file at `path`. A source checkout (a `.git` folder, or the `.git`
    file of a worktree, beside the package folder) ignores the file and gives (None, None): an editable run has no
    build, and a file that `tools/build_info.py` wrote there can be stale [ADR-0Z6Q item 17]."""
    if (Path(path).parents[1] / ".git").exists():
        return None, None
    return read_build_info(path)


def evidence_reasons(version, commit, tree_modified, reasons) -> list:
    """C 7.1: `no-version`, `no-commit` and `modified-tree` only when they apply (3.5.2), then the reasons of the
    run, each one time."""
    common = (["no-version"] if not SEMVER.match(version) else []) + (
        ["no-commit"] if not (isinstance(commit, str) and COMMIT.fullmatch(commit)) else []) + (
        ["modified-tree"] if tree_modified is not False else [])
    return list(dict.fromkeys(common + list(reasons)))


def _report(level, created, out, backend) -> dict:
    version = _version()
    context = out["context"]
    commit, tree_modified = build_values(BUILD_INFO)
    evidence = evidence_reasons(version, commit, tree_modified, out["reasons"])
    report = {
        "schema": SCHEMA,
        "package": {"name": "skellycam", "version": version, "commit": commit, "tree_modified": tree_modified},
        "kind": level,
        "created_utc": created,
        "host": _host(),
        "checks": [r for r in out["rows"].values() if r is not None],
        "cleanup": out["cleanup"],
        "details": {"backend": backend, "os_key": context.os_key if context else None,
                    "abi": context.abi if context else None,
                    "not_built": catalog.not_built(level, context.unit_specs() if context else [], backend)},
        "evidence": {"valid": not evidence, "reasons": evidence},
    }
    summary = [{k: v for k, v in item.items() if not k.startswith("_")} for item in out["summary"]]
    if summary:
        report["summary"] = summary
    if out["notices"]:
        report["notices"] = out["notices"]
    return report
