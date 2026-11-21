"""The caller part of a certify run of skellycam (specs/certify.md 2.1, 2.5, 4.1, 8.3, 9; contract `report-format.md`
of `skellycertify`, format 1.4.0): the plan, the progress, the cancel, the time limits, phase G, the local record and
the module report.

The caller imports no `comtypes` and opens no camera. The camera steps (`session.py`) run in a spawn session child
with the product `CameraGroupManager` and its camera processes. A test can give `manager` (the session then runs in
a thread of the test process) or a picklable `source_factory` (fake sources in the session child).
"""

import asyncio
import contextlib
import datetime
import getpass
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

SCHEMA = "skellycertify.report/1.4.0"
LEVELS = ("quick", "full")
QUICK_BUDGET_S = 30.0  # 4.1
FULL_SESSION_LIMIT_S = 240.0  # 9.3: the limit of a camera block, for the session of this step
DETECT_LIMIT_S = 20.0  # 9.3
RECHECK_LIMIT_S = 5.0  # 8.3: after a cancel, at most 5 s for each touched camera
EXIT_LIMIT_S = 5.0
PROGRESS_GAP_S = 0.1  # 9.6: at most 10 messages each second
MARKER = ".skellycam-certify"  # 9.5
STOPS = ("cancelled", "over-budget")
QUESTIONS = [{"section": None, "id": "lit-as-usual", "text": "Was the room lit as it is when you record?"},
             {"section": None, "id": "all-cameras", "text": "Were all the cameras that you record with attached?"}]
QUESTION_FULL = {"section": None, "id": "camera-ok-after",
                 "text": "Do all the cameras still work in other programs after the run?"}
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")


# ---------------------------------------------------------------------------
# The public functions (C 2.1, C 2.6, C 2.8; certify.md 1, 9.1)
# ---------------------------------------------------------------------------

def certify(level: str, progress=None, cancel=None, *, cameras=None, recording_folder=None,
            test_media_dir=None) -> dict:
    """Run the certify checks of skellycam and return one module report. skellycam reads and writes nothing in
    `test_media_dir` (2.4)."""
    return run(level, progress, cancel, cameras=cameras, recording_folder=recording_folder)


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
        "total": len(checks) if level == "full" or context.units else 0,
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

    def send(self, state, rows, step=None):
        if self.callback is None or self.broken:
            return
        wait = self.last + PROGRESS_GAP_S - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        checks = [dict(section=None, name=name, result=None) if r is None else dict(r, section=None)
                  for name, r in rows.items()]
        message = {"package": "skellycam", "kind": self.level, "state": state,
                   "step": None if step is None else {"section": None, "name": step}, "checks": checks,
                   "done": sum(1 for r in rows.values() if r is not None), "total": self.total, "seconds_left": None}
        self.last = time.monotonic()
        try:
            self.callback(message)
        except Exception as error:  # C 2.3: stop calling it and go on
            logger.warning(f"certify: the progress callable raised {type(error).__name__}; no more progress")
            self.broken = True


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
    for process in processes:
        with contextlib.suppress(psutil.NoSuchProcess):
            process.kill()
    psutil.wait_procs(processes, timeout=5)


def _session_child(events, acks, units, work, level, unix, source_factory) -> None:
    """The session child: one `CameraGroupManager` with real camera processes and the native source (2.1)."""
    from skellycam.core.camera_group.camera_group_manager import CameraGroupManager
    from skellycam.core.ipc.process_management.managed_worker import WorkerMode
    from skellycam.core.ipc.process_management.worker_registry import WorkerRegistry

    if source_factory is None:  # 2.1: certify always uses the native source
        os.environ["SKELLYCAM_WINDOWS_CAPTURE"] = "media_foundation"
    # The product makes a camera group only in a main process (`parent_process() is None`, the pubsub guards). The
    # session child is the main process of its camera processes (2.1), so it clears its own parent mark.
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

        def begin(name):
            events.put(("begin", name))
            if not acks.get():
                raise Stopped()

        asyncio.run(run_session(manager, units, work, level, unix, begin, lambda r: events.put(("done", r)),
                                lambda kind, value: events.put(("fact", (kind, value))), time.sleep))
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

    def alive(self):
        return self.process.is_alive()

    def ack(self, ok):
        self.acks.put(ok)

    def stop(self):
        kill_tree(self.process.pid)

    def exit_code(self):
        return self.process.exitcode

    def finish(self) -> bool:
        """True when the child gave its result and did not end (C 2.5 `exit`)."""
        self.process.join(EXIT_LIMIT_S)
        hung = self.process.is_alive()
        if hung:
            kill_tree(self.process.pid)
        self.process.join(EXIT_LIMIT_S)
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

    def ack(self, ok):
        self.acks.put(ok)

    def stop(self):
        self.stopped.set()
        self.acks.put(False)

    def exit_code(self):
        return None

    def finish(self) -> bool:
        self.thread.join(120)
        return False


def _drive(session, rows, reporter, cancel, deadline, over):
    """Serve the session until its end, a cancel or the end of the time (9.3). Returns (running check, stop cause,
    error class name, facts)."""
    current, stop, error = None, None, None
    facts = dict(touched=[], before={}, release={}, prior={})
    while True:
        if stop is None and ((cancel is not None and _is_set(cancel)) or time.monotonic() > deadline):
            stop = "cancelled" if cancel is not None and _is_set(cancel) else over
            session.stop()
        try:
            kind, value = session.events.get(timeout=0.2)
        except queue.Empty:
            if not session.alive():
                if stop is None:
                    stop = "crashed"
                break
            continue
        except (EOFError, OSError):
            stop = stop or "crashed"
            break
        if kind == "begin":
            if stop is not None:
                session.ack(False)
                continue
            current = value
            reporter.send("running", rows, step=value)
            if cancel is not None and _is_set(cancel):  # a cancel during the progress call: the check does not start
                stop = "cancelled"
                session.stop()
                continue
            session.ack(True)
        elif kind == "done" and stop is None:
            rows[value["name"]] = value
        elif kind == "fact":
            name, item = value
            if name == "touched":
                facts["touched"] += item
            elif name in ("before", "release", "prior"):
                facts[name].setdefault(item[0], item[1])
        elif kind == "end":
            if value is not None and stop is None:
                stop, error = "crashed", value
            break
    return current, stop, error, facts


def _is_set(cancel) -> bool:
    try:
        return bool(cancel.is_set())
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Phase G after a cancel, a time-out or a crash (8.3)
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


def _recheck(unit: Unit, before: dict, source_factory, manager) -> str:
    """One camera, at most RECHECK_LIMIT_S: in a spawn child (its process tree is killed at the limit), or in a
    thread with the source factory of the test manager."""
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
        thread.join(RECHECK_LIMIT_S)
        return box[0] if box else "replug"
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    child = context.Process(target=_recheck_child, args=(source_factory, config, request, before, sender),
                            name="skellycam certify recheck")
    child.start()
    sender.close()
    try:
        return receiver.recv() if receiver.poll(RECHECK_LIMIT_S) else "replug"
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
    """9.5: a new marked work folder; earlier marked folders of certify go first."""
    root = Path(recording_folder) if recording_folder is not None else Path(tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    for old in root.glob("skellycam-certify-*"):
        if (old / MARKER).exists():
            shutil.rmtree(old, ignore_errors=True)
    work = root / f"skellycam-certify-{uuid.uuid4()}"
    work.mkdir()
    (work / MARKER).write_text("", encoding="utf-8")
    return work


def _group_open() -> bool:
    """9.7: a camera group of skellycam is open in the calling process."""
    module = __import__("sys").modules.get("skellycam.core.camera_group.camera_group_manager")
    manager = getattr(module, "_CAMERA_GROUP_MANAGER", None) if module is not None else None
    return bool(manager is not None and manager.camera_groups)


def _detect(backend, cancel):
    """(the `detect` row, the devices). Windows: the product detection, which has its own child (cap 7.1)."""
    if backend != "media-foundation":
        return dict(name="detect", result="not-run", reason="not-built"), []
    from skellycam.core.camera.capture.media_foundation.detect import detect_media_foundation_cameras

    box = {}

    def target():
        try:
            box["devices"] = detect_media_foundation_cameras()
        except BaseException as error:
            box["error"] = error
    t0 = time.monotonic()
    thread = threading.Thread(target=target, name="certify detection", daemon=True)
    thread.start()
    while thread.is_alive() and time.monotonic() - t0 < DETECT_LIMIT_S and not (cancel is not None and _is_set(cancel)):
        thread.join(0.25)
    if "devices" not in box:
        error = box.get("error")
        code = getattr(error, "code", None)
        reason = ("cancelled" if cancel is not None and _is_set(cancel) and error is None else
                  "timed-out" if error is None or code == "hung" else "crashed")
        return dict(name="detect", result="not-run" if reason == "cancelled" else "fail", reason=reason), []
    return None, box["devices"]


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


def run(level, progress=None, cancel=None, *, cameras=None, recording_folder=None, devices=None, manager=None,
        source_factory=None, sleep=time.sleep, checks_path=None, evidence_path=camera_checks.EVIDENCE_PATH,
        os_key=None, abi=None, budget_s=None, private_terms=None) -> dict:
    """`certify()` with the seams of the tests: `devices` (the detection result), `manager` (a session in a thread
    of this process), `source_factory` (the fakes of a session child), the paths of the record and the evidence
    file, the OS key and the ABI, and the budget of quick."""
    _check_level(level)
    created = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    backend = catalog.system_backend()
    reporter = _Progress(progress, level)
    reporter.send("starting", {})
    work = _work_folder(recording_folder)
    out = dict(rows={"detect": None}, reasons=[], cleanup=[], notices=[], summary=[], context=None)
    try:
        _run(out, level, reporter, cancel, cameras, devices, manager, source_factory, sleep, checks_path,
             evidence_path, os_key, abi, budget_s, private_terms, backend, work)
    finally:
        reporter.send("cleaning-up", out["rows"])
        shutil.rmtree(work, ignore_errors=True)
        if work.exists():
            out["cleanup"].append(_row("delete-work-folder", "fail", "not-deleted"))
    report = _report(level, created, out, backend)
    reporter.send("done", out["rows"])
    return report


def _run(out, level, reporter, cancel, cameras, devices, manager, source_factory, sleep, checks_path, evidence_path,
         os_key, abi, budget_s, private_terms, backend, work):
    unix = backend != "media-foundation"
    busy = _group_open()
    reporter.send("running", out["rows"], step="detect")
    t0 = time.monotonic()
    detect_row = None
    if devices is None:
        detect_row, devices = (None, _enumerate(backend)) if busy else _detect(backend, cancel)
    context = out["context"] = _Context(level, devices, cameras, backend, checks_path, evidence_path, os_key, abi,
                                        private_terms)
    planned = catalog.planned_checks(level, context.unit_specs(), backend)
    modules = dict(planned)
    rows = out["rows"] = {name: None for name, _ in planned}
    reporter.total = len(rows)
    if busy:  # 9.7: the run is refused; it opens no camera. No summary item, so no `module` (C 3.4)
        out["rows"] = {name: _row(name, "not-run", "cameras-busy") for name in rows}
        out["reasons"].append("cameras-busy")
        return
    rows["detect"] = detect_row or _detect_row(devices, time.monotonic() - t0)
    stop = "cancelled" if rows["detect"]["reason"] == "cancelled" else None
    if rows["detect"]["result"] == "pass" and not any(not d.virtual for d in devices):
        out["reasons"].append("no-camera")
    units = [Unit(label=c["label"], camera_id=c["raw"].camera_id, index=c["raw"].index, base=c["base"],
                  module=c["module"], device=c["raw"]) for c in context.units]
    facts = dict(touched=[], before={}, release={}, prior={})
    if units and stop is None:
        limit = (QUICK_BUDGET_S if budget_s is None else budget_s) if level == "quick" else FULL_SESSION_LIMIT_S
        session = (_ThreadSession(manager, units, work, level, unix, sleep) if manager is not None else
                   _ChildSession(units, work, level, unix, source_factory))
        current, stop, error, facts = _drive(session, rows, reporter, cancel, time.monotonic() + limit,
                                             "over-budget" if level == "quick" else "timed-out")
        if session.finish() and stop is None:
            rows["session:exit"] = _row("session:exit", "record-only", "hung-at-exit")
        exit_code = session.exit_code()
        if stop in ("crashed", "timed-out") and current is not None and rows.get(current) is None:
            numbers = {"exit_code": exit_code} if exit_code is not None and error is None else {}
            rows[current] = _row(current, "fail", error or stop, modules.get(current), **numbers)
    computed = {name for name in rows if name.endswith(":units") or ":gate" in name}
    _fill(rows, modules, context, level, stop, facts["prior"], skip=computed)
    if stop not in STOPS:
        _computed_rows(rows, context, level, reporter)
    _fill(rows, modules, context, level, stop, facts["prior"], skip=set())
    out["summary"] = _summary(rows, context, level, unix)
    _phase_g(rows, context, units, facts, stop, source_factory, manager, out["cleanup"], out["notices"])
    if stop == "cancelled":
        out["reasons"].append("cancelled")
    _write_record(rows, context, level, out["summary"], checks_path)


def _row(name, result, reason=None, module=None, **numbers) -> dict:
    out = dict(name=name, result=result, reason=reason)
    if module is not None:
        out["module"] = module
    if numbers:
        out["numbers"] = numbers
    return out


def _fill(rows, modules, context, level, stop, prior, skip):
    """Each check with no result: `not-built` or `same-model` (5.1), the stop cause (C 2.4, 4.1), or the reason that
    the session gave for its camera (`prior-failure`, `camera-in-use`, ...)."""
    unix = context.backend != "media-foundation"
    first = {m["units"][0]["label"] for m in context.models.values()}
    block = {name: c["label"] for c in context.units
             for name in catalog.camera_names(c["label"], c["base"], level, unix)["full"]}
    static = set(catalog.QUICK_NOT_BUILT + catalog.SELF_QUICK + catalog.FULL_NOT_BUILT).union(
        *catalog.SYSTEM_NOT_BUILT.values())
    for name in rows:
        if rows[name] is not None or name in skip:
            continue
        unit_label = next((c["label"] for c in context.units if name.startswith(c["label"] + ":")), None)
        if name in static:
            reason = "not-built"
        elif name in block:
            reason = "not-built" if block[name] in first else "same-model"
        elif stop in STOPS:
            reason = stop
        elif unit_label in prior:
            reason = prior[unit_label]
        elif name.startswith("group:") and "group" in prior:
            reason = prior["group"]
        else:
            reason = "prior-check-failed"
        rows[name] = _row(name, "not-run", reason, modules.get(name))


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
    items = []
    for model, m in context.models.items():
        item = dict(group="camera", name=m["module"], device=m["device"])
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


def _phase_g(rows, context, units, facts, stop, source_factory, manager, cleanup, notices):
    """8.3: a cleanup row and a notice for each camera that is not healthy after the run. After a cancel, the end of
    the budget, a time-out or a crash, each touched camera that did not fail is opened again, at most 5 s each."""
    states = {label: "replug" if code == "camera-wedged" else "not-restored"
              for label, code in facts["release"].items()}
    if stop is not None:
        for unit in units:
            opens = rows.get(f"{unit.label}:opens") or {}
            if (unit.label not in facts["touched"] or unit.label in states or unit.base is None
                    or opens.get("result") == "fail" or opens.get("reason") == "camera-in-use"):
                continue
            state = _recheck(unit, facts["before"].get(unit.label, {}), source_factory, manager)
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
    """2.5: one row for each model by the rule of `catalog.writes_row`."""
    by_name = {item["name"]: item for item in summary if item.get("reason") != "reviewed"}
    out = []
    date = datetime.date.today().isoformat()
    for model, m in context.models.items():
        units = _selected(context, model)
        item = by_name.get(m["module"])
        if not units or item is None:
            continue
        opens = [(rows.get(f"{c['label']}:opens") or {}).get("result") for c in units]
        if not catalog.writes_row(item["result"], opens):
            continue
        gate = {step: rows[f"{model}:gate:{step}"]["result"] for step in catalog.GATE_STEPS} if level == "full" else None
        first = units[0]["label"]
        settings = [rows.get(f"{first}:settings-stick:{c}") or {} for c in ("readback", "holds", "image-effect")]
        path = (settings[0].get("numbers") or {}).get("control_path")
        result = catalog.control_result(settings[0].get("result"), settings[1].get("result"),
                                        {"result": settings[2].get("result"), "reason": settings[2].get("reason")})
        controls = {"exposure": {path: result}} if path not in (None, "none") and result else {}
        out.append(catalog.record_row(m["record_key"], context.backend, context.os_key, context.abi, level,
                                      item["result"], _version(), date, gate, controls))
    if out:
        if checks_path is None:
            from skellycam.system.default_paths import get_default_skellycam_base_folder_path
            checks_path = Path(get_default_skellycam_base_folder_path()) / camera_checks.CHECKS_FILE
        catalog.write_record(checks_path, out)


def _report(level, created, out, backend) -> dict:
    version = _version()
    context = out["context"]
    evidence = (["no-version"] if not SEMVER.match(version) else []) + ["no-commit", "modified-tree"] + out["reasons"]
    report = {
        "schema": SCHEMA,
        "package": {"name": "skellycam", "version": version, "commit": None, "tree_modified": None},
        "kind": level,
        "created_utc": created,
        "host": _host(),
        "checks": [r for r in out["rows"].values() if r is not None],
        "cleanup": out["cleanup"],
        "details": {"backend": backend, "os_key": context.os_key if context else None,
                    "abi": context.abi if context else None},
        "evidence": {"valid": not evidence, "reasons": list(dict.fromkeys(evidence))},
    }
    if out["summary"]:
        report["summary"] = out["summary"]
    if out["notices"]:
        report["notices"] = out["notices"]
    return report
