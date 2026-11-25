"""The certify tests of Q772, Q773 and Q775 (session Q44, Q45 and Q47 of 2026-11-25; specs/certify.md section 17).

Fake sources only; no test opens a camera, and no test is timed. The session-child tests use a fake factory that
changes the session child when it is unpickled there (`ChildFault`): the real child, the real queue and the real
kill, with no hook in the product.
"""

import json
import multiprocessing
import os
import pickle
import queue
import shutil
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import psutil
import pytest

from skellycam.tests.capture.capture_session import capture_app
from skellycam.tests.capture.fake_source import FakeSourceFactory
from skellycam.tests.certify.report_rules import assert_valid, known_codes, problems
from skellycam.tests.certify.test_certify import (
    CATALOG, RUN, by_name, good, group_checks, labels, paths, product, run_with, virtual_sleep)
from skellycam.tests.certify.test_certify_review import assert_no_new_process, descendants, record

SESSION_CHILD = "skellycam certify session"  # the process name of run._ChildSession


def reason_codes_text() -> str:
    return (Path(product("skellycam").__file__).parent / "REASON_CODES.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Q772 (Q44): the missing tests
# ---------------------------------------------------------------------------

def test_t_cert_30_the_product_codes_and_each_reason_of_a_report_are_in_the_list():
    """T-CERT-30, 15, C 5.4: each failure code of the product (unix-capture.md 4.6.3) is a reason of the list, except
    `process-ended`, which certify gives as `crashed` (10.5); each reason that the code can give is in
    `skellycam/REASON_CODES.md`. The validator refuses a reason, a notice code or an evidence reason that is not in
    the file, and takes the class name of an exception (15 `<ExceptionClass>`) except as a notice code, so each run
    test checks the rule."""
    catalog = product(CATALOG)
    failure_codes = product("skellycam.core.camera.capture.failure_codes")
    codes = known_codes()
    product_codes = [c for c in failure_codes.CODES if c != "process-ended"]
    assert not [c for c in product_codes if c not in catalog.REASON_CODES], "a product code is not in REASON_CODES"
    assert not [c for c in (*catalog.REASON_CODES, *catalog.NOTICE_CODES, "crashed") if c not in codes]
    base = {"schema": "skellycertify.report/1.7.0",
            "package": {"name": "skellycam", "version": "2.0.0", "commit": None, "tree_modified": None},
            "kind": "quick", "created_utc": "2026-11-25T00:00:00Z", "host": {"os": None, "cpu": None},
            "checks": [{"name": "detect", "result": "fail", "reason": "timed-out"},
                       {"name": "x", "result": "not-run", "reason": "KeyboardInterrupt"}],
            "evidence": {"valid": False, "reasons": ["no-commit", "modified-tree"]}}
    assert problems(base) == []
    unknown = [dict(checks=[{"name": "detect", "result": "fail", "reason": "made-up"}]),
               dict(cleanup=[{"name": "release:x", "result": "fail", "reason": "made-up"}]),
               dict(notices=[{"code": "made-up", "values": {"camera": "C"}}]),
               dict(evidence={"valid": False, "reasons": ["no-commit", "modified-tree", "made-up"]}),
               dict(notices=[{"code": "KeyboardInterrupt", "values": {"camera": "C"}}])]
    for change in unknown:
        assert any("REASON_CODES.md" in p for p in problems({**base, **change})), change


@pytest.mark.parametrize("system, backend", [("Windows", "media-foundation"), ("Linux", "v4l2"),
                                             ("Darwin", "avfoundation")])
def test_t_cert_31_the_backend_of_each_os_and_each_check_name(monkeypatch, system, backend):
    """T-CERT-31, 3.1, C 3.4: the backend name of each OS; each check name that the code can give (the planned
    checks, the not-built names with their mode, the cleanup rows, `not-reached`, `session:exit`) with the longest
    backend, `nousb-nousb`, index 9 and rate 29.97 matches the pattern; the longest has 75 characters."""
    catalog = product(CATALOG)
    monkeypatch.setattr(catalog.platform, "system", lambda: system)
    assert catalog.system_backend() == backend
    longest, base = catalog.label(backend, None, None, 9), (1920, 1080, 29.97)
    units = [(longest, base, "Camera (no USB id)"), (catalog.label(backend, 0xFFFF, 0xFFFF, 9), (640, 480, 30.0), "C")]
    names = [f"release:{longest}", "delete-work-folder", "write-record", "session:exit", f"{longest}:not-reached"]
    for level in ("quick", "full"):
        names += [name for name, _ in catalog.planned_checks(level, units, backend)]
        not_built = catalog.not_built(level, units, backend)
        names += not_built["run"] + [f"{longest}:{c}" for c in not_built["camera"]]
        names += [f"{longest}:{c.format(base=catalog.mode_name(*base))}" for c in catalog.FULL_CAMERA_NOT_BUILT]
    bad = [name for name in names if not catalog.NAME.match(name)]
    assert not bad, bad
    assert max(map(len, names)) <= 75
    if backend == "media-foundation":
        assert max(map(len, names)) == 75


def test_t_cert_67_two_wedged_cameras_and_one_not_restored_give_three_notices():
    """T-CERT-67, 8.3, C 3.8: three notices with their codes and `values.camera` the cleaned names; at most 8 keys
    each; no free text; each code is in `skellycam/REASON_CODES.md` with its text for the person."""
    run, session = product(RUN), product("skellycam.core.certify.session")
    units = [session.Unit(label=f"cam.media-foundation.feed-000{i}.0", camera_id=f"c{i}", index=i,
                          base=(640, 480, 30.0), module=f"Webcam {i}", device=None) for i in range(4)]
    context = SimpleNamespace(cameras=[dict(label=u.label, name=u.module) for u in units])
    release = {units[0].label: "camera-wedged", units[1].label: "camera-not-restored", units[2].label: "camera-wedged"}
    facts = dict(touched=[u.label for u in units], before={}, release=release, prior={})
    cleanup, notices = [], []
    run._phase_g(context, units, facts, None, set(), True, None, None, cleanup, notices)
    assert notices == [{"code": "camera-wedged", "values": {"camera": "Webcam 0"}},
                       {"code": "camera-not-restored", "values": {"camera": "Webcam 1"}},
                       {"code": "camera-wedged", "values": {"camera": "Webcam 2"}}]
    assert [c["reason"] for c in cleanup] == ["camera-wedged", "camera-not-restored", "camera-wedged"]
    text = reason_codes_text()
    for notice in notices:
        assert len(notice["values"]) <= 8 and set(notice) == {"code", "values"}
        line = next(line for line in text.splitlines() if line.startswith(f"| `{notice['code']}` |"))
        assert line.rstrip(" |").split("|")[-1].strip().startswith("Camera <name>"), line


def work_folders(tmp_path):
    return sorted((tmp_path / "recordings").glob("skellycam-certify-*"))


@pytest.mark.parametrize("end", ["pass", "crash", "time-out", "cancel"])
def test_t_cert_28_the_work_folder_goes_at_each_end(monkeypatch, tmp_path, end):
    """T-CERT-28, 9.5: after a pass, a crash of the session, a time-out and a cancel, the work folder is gone and no
    `not-deleted` row is in the report."""
    run = product(RUN)
    made = []
    make = run._work_folder
    monkeypatch.setattr(run, "_work_folder", lambda folder: made.append(make(folder)) or made[-1])
    cancel = threading.Event()
    jump = [0.0]  # the time-out: the clock of `run` jumps past the session limit when the take starts
    monkeypatch.setattr(run, "time", SimpleNamespace(monotonic=lambda: time.monotonic() + jump[0], sleep=time.sleep))

    def progress(message):
        if (message.get("step") or {}).get("name") == "group:take:finished":
            if end == "cancel":
                cancel.set()
            elif end == "time-out":
                jump[0] = 1e6
    with capture_app(monkeypatch, [good()]) as app:
        if end == "crash":
            async def crash(*args, **kwargs):
                raise KeyboardInterrupt  # a fault that the session does not catch
            monkeypatch.setattr(app.manager, "start_recording_all_groups", crash)
        report = run_with(app, tmp_path, level="full" if end == "time-out" else "quick", progress=progress,
                          cancel=cancel)
    assert_valid(report)
    reasons = {c["reason"] for c in report["checks"]}
    assert {"pass": None, "crash": "KeyboardInterrupt", "time-out": "timed-out", "cancel": "cancelled"}[end] in reasons
    assert len(made) == 1 and not made[0].exists()
    assert not [c for c in report.get("cleanup", []) if c["reason"] == "not-deleted"]


def test_t_cert_28_a_locked_file_and_the_files_of_the_person(monkeypatch, tmp_path):
    """T-CERT-28, 9.5: a file in the work folder that cannot be deleted gives the cleanup row `delete-work-folder`
    `not-deleted`; a file of the person in `recording_folder` and an old folder with no marker stay; an old folder
    with the marker goes."""
    if sys.platform != "win32" and os.geteuid() == 0:
        pytest.skip("root deletes a file in a folder with no write access, so POSIX has no locked file for root")
    recordings = tmp_path / "recordings"
    recordings.mkdir()
    mine = recordings / "my notes.txt"
    mine.write_text("mine", encoding="utf-8")
    unmarked = recordings / "skellycam-certify-mine"
    unmarked.mkdir()
    marked = recordings / "skellycam-certify-left"
    marked.mkdir()
    (marked / ".skellycam-certify").write_text("", encoding="utf-8")
    held = []

    def progress(message):
        if (message.get("step") or {}).get("name") == "group:take:finished" and not held:
            work = next(p for p in work_folders(tmp_path) if p.name not in (unmarked.name, marked.name))
            locked = work / "locked"
            locked.mkdir()
            handle = open(locked / "held.bin", "wb")  # noqa: SIM115 - Windows: an open file cannot be deleted
            if sys.platform != "win32":
                locked.chmod(0o500)  # POSIX: a file in a folder with no write access cannot be deleted
            held.append((locked, handle))
    try:
        with capture_app(monkeypatch, [good()]) as app:
            report = run_with(app, tmp_path, progress=progress)
    finally:
        for locked, handle in held:
            handle.close()
            locked.chmod(0o700)
    assert_valid(report)
    assert held, "the run did not reach the take"
    assert {"name": "delete-work-folder", "result": "fail", "reason": "not-deleted"} in report["cleanup"]
    assert mine.read_text(encoding="utf-8") == "mine" and unmarked.exists() and not marked.exists()
    shutil.rmtree(held[0][0].parent, ignore_errors=True)


def snapshot(folder: Path) -> list:
    return sorted((str(p.relative_to(folder)), p.stat().st_size, p.stat().st_mtime_ns) for p in folder.rglob("*")) + [
        folder.stat().st_mtime_ns]


def test_t_cert_49_test_media_dir_is_left_untouched(monkeypatch, tmp_path):
    """T-CERT-49, 2.4: `skellycam.certify("quick", test_media_dir=...)` and `certify_plan("full", test_media_dir=...)`
    take the option; the run writes and deletes nothing in that folder; its path is in no report, no plan and no
    progress message. (The public functions run with the fake cameras of the test through the seams of `run`.)"""
    import skellycam
    run = product(RUN)
    media = tmp_path / "shared media"
    media.mkdir()
    (media / "clip.bin").write_bytes(b"\x00" * 64)
    before = snapshot(media)
    real_run, real_plan = run.run, run.plan
    messages = []
    with capture_app(monkeypatch, [good()]) as app:
        devices = app.factory.device_infos()
        given = paths(tmp_path)

        def fake_run(level, progress=None, cancel=None, **options):
            options = {k: v for k, v in options.items() if v is not None}
            return real_run(level, progress, cancel, manager=app.manager, devices=devices,
                            sleep=virtual_sleep(app.factory.clock), **{**given, **options})

        def fake_plan(level, **options):
            return real_plan(level, devices=devices, **{k: v for k, v in given.items() if k != "recording_folder"},
                             **{k: v for k, v in options.items() if v is not None})
        (tmp_path / "recordings").mkdir()
        monkeypatch.setattr(run, "run", fake_run)
        monkeypatch.setattr(run, "plan", fake_plan)
        plan = skellycam.certify_plan("full", test_media_dir=media)
        report = skellycam.certify("quick", messages.append, test_media_dir=media)
    assert_valid(report)
    (label,) = labels(devices)
    assert by_name(report)[f"{label}:opens"]["result"] == "pass", "the run did not use the fake cameras"
    assert snapshot(media) == before
    text = json.dumps([report, plan, messages])
    for form in {str(media), media.as_posix(), json.dumps(str(media))[1:-1], media.name}:
        assert form not in text, form


def _std_caller(out_path: str) -> None:
    """T-CERT-01, 18, 33: a spawn child as the caller, as freemocap runs certify: `sys.stdout` and `sys.stderr`
    `None`, `sys.frozen` true and a stdin that records each read. It writes its findings to `out_path`."""
    import multiprocessing.spawn as spawn
    import traceback

    reads = []

    class Stdin:
        def __getattr__(self, name):
            reads.append(name)
            raise OSError("certify read stdin")

    command_line = spawn.get_command_line

    def plain_command_line(**kwds):
        # shortcut: python.exe is no frozen executable, so it gets the plain spawn command line that a frozen app's
        # `freeze_support()` makes unnecessary; a test with a real frozen build is T-CERT-90 (hardware)
        frozen = sys.__dict__.pop("frozen")
        try:
            return command_line(**kwds)
        finally:
            sys.frozen = frozen

    findings = dict(comtypes=[], listening=[], scanned=0, reports={}, plan_comtypes=None, error=None)
    kind = "inet" if sys.platform == "win32" else "all"  # POSIX: also the Unix sockets
    try:
        spawn.get_command_line = plain_command_line
        sys.stdout = sys.stderr = None
        sys.stdin = Stdin()
        sys.frozen = True
        from skellycam.core.certify import run
        from skellycam.tests.capture.fake_source import FakeSourceFactory
        from skellycam.tests.certify.test_certify import good, paths

        factory = FakeSourceFactory([good()])
        folder = Path(out_path).parent
        options = paths(folder)
        options["recording_folder"].mkdir(exist_ok=True)
        run.plan("quick", devices=factory.device_infos(),
                 **{k: v for k, v in options.items() if k != "recording_folder"})
        findings["plan_comtypes"] = "comtypes" in sys.modules

        def progress(message):
            findings["comtypes"].append("comtypes" in sys.modules)
            tree = [psutil.Process()] + psutil.Process().children(recursive=True)
            for process in tree:
                try:
                    connections = process.net_connections(kind=kind)
                    findings["scanned"] += 1
                    for conn in connections:
                        if conn.status == psutil.CONN_LISTEN or (conn.type == 2 and conn.laddr):  # 2: SOCK_DGRAM
                            findings["listening"].append([process.name(), str(conn.laddr)])
                except psutil.Error:
                    pass
        for level in ("quick", "full"):
            findings["reports"][level] = run.run(level, progress, devices=factory.device_infos(),
                                                 source_factory=factory, **options)
    except BaseException:
        findings["error"] = traceback.format_exc()
    findings["stdin_reads"] = reads
    Path(out_path).write_text(json.dumps(findings), encoding="utf-8")


def test_t_cert_01_18_33_a_caller_with_no_streams_no_comtypes_and_no_socket(tmp_path):
    """T-CERT-01, 18, 33, 2.1, C 2.5: the caller is a spawn child with `sys.stdout` and `sys.stderr` `None` and
    `sys.frozen` true. The plan and quick and full runs with fakes give complete reports; the caller never loads
    comtypes and never reads stdin; no process of the tree listens on a socket. Not proven: the frozen case. The
    product never reads `sys.frozen`, multiprocessing fixes its executable at import, and the test patches the spawn
    command line; a real frozen build is T-CERT-90 (hardware)."""
    out = tmp_path / "findings.json"
    before = descendants()
    caller = multiprocessing.get_context("spawn").Process(target=_std_caller, args=(str(out),),
                                                          name="certify test caller")
    caller.start()
    caller.join(600)
    assert caller.exitcode == 0, caller.exitcode
    findings = json.loads(out.read_text(encoding="utf-8"))
    assert findings["error"] is None, findings["error"]
    assert findings["stdin_reads"] == []
    assert findings["plan_comtypes"] is False and findings["comtypes"] and not any(findings["comtypes"])
    assert findings["listening"] == [] and findings["scanned"] > 0
    for level, report in findings["reports"].items():
        assert_valid(report)
        assert report["kind"] == level
        (label,) = labels(FakeSourceFactory([good()]).device_infos())
        checks = by_name(report)
        for name in group_checks(label):
            if level == "quick" and name.split(":", 1)[1] in ("native-jpeg:not-reencoded", "native-jpeg:size",
                                                               "native-jpeg:ring-equals-mkv",
                                                               "native-jpeg:source-equals-ring",
                                                               "settings-stick:image-effect", "records:gaps-explained"):
                continue
            assert checks[name]["result"] == "pass", checks[name]
    assert_no_new_process(before)


def test_t_cert_121_the_not_built_list_after_q624():
    """T-CERT-121 in part, 3.6.12 (Q624): the plan and `details.not_built` name no check that Q624 dropped
    (`system:backend`, `system:virtual-cameras`, `control:focus:sharpness`, `control:autofocus`,
    `control:white-balance`, `control:power-line`, `timings`); they name `self:scale-3` and `self:scale-12`, and keep
    `self:idle-cpu`, the two ring self-checks, `identity:stable` and `identity:unique`. Not covered: the x86-64
    and the ARM fake systems (the lists do not depend on the CPU today), and `details.cameras`, which is not built."""
    catalog = product(CATALOG)
    units = [("cam.x.0001-0002.0", (640, 480, 30.0), "C")]
    for backend in ("media-foundation", "v4l2", "avfoundation"):
        not_built = catalog.not_built("full", units, backend)
        planned = [name for name, _ in catalog.planned_checks("full", units, backend)]
        names = set(not_built["camera"]) | set(not_built["run"]) | set(planned) | {n.split(":", 1)[-1] for n in planned}
        dropped = {"system:backend", "system:virtual-cameras", "control:focus:sharpness", "control:autofocus",
                   "control:white-balance", "control:power-line", "timings", "self:scale-4", "self:scale-8"}
        assert not names & dropped, names & dropped
        assert {"self:scale-3", "self:scale-12", "self:idle-cpu", "self:ring:torn", "self:ring:lapped"} <= set(
            not_built["run"])
        assert {"identity:stable", "identity:unique"} <= set(not_built["camera"])


# ---------------------------------------------------------------------------
# Q773 (Q45): the dark rule of 4.6
# ---------------------------------------------------------------------------

@pytest.mark.xfail(strict=True, raises=AssertionError, reason="needs the D-3 key `rate_luma_mean` of the product (3.5.15 P5): a camera that "
                                       "fails its start-up rate check writes no ring frame (19.1 item 7), and today "
                                       "certify gets no diagnostics dict of that camera at the judge of the open")
def test_t_cert_09_a_slow_camera_in_the_dark(monkeypatch, tmp_path):
    """T-CERT-09, 4.2, 4.6: the generic-camera pattern (25 fps on a 30 fps mode) with dark frames (mean 10) gives
    `rate` `not-run` `too-dark` and the summary item `partial`; the same camera with bright frames stays `fail`
    `rate-low` (T-CERT-08)."""
    assert_slow_in_the_dark(monkeypatch, tmp_path, [good(rate=25.0, brightness=((-7, 10), (-8, 5))), good(rate=25.0)])


def assert_slow_in_the_dark(monkeypatch, tmp_path, scripts):
    with capture_app(monkeypatch, scripts) as app:
        devices = app.factory.device_infos()
        report = run_with(app, tmp_path)
    assert_valid(report)
    checks = by_name(report)
    dark, bright = labels(devices)
    assert (checks[f"{dark}:rate"]["result"], checks[f"{dark}:rate"]["reason"]) == ("not-run", "too-dark")
    assert checks[f"{dark}:rate"]["numbers"]["luma_mean"] < 24
    assert (checks[f"{bright}:rate"]["result"], checks[f"{bright}:rate"]["reason"]) == ("fail", "rate-low")
    assert [i["result"] for i in report["summary"]] == ["partial", "fail"]


def test_t_cert_13_the_image_check_in_the_dark(monkeypatch, tmp_path):
    """T-CERT-13 dark case, 4.3, 4.6 (full): a dark image that gets darker at -8 passes (a pass in the dark stays
    `pass`); a dark image that does not change is `not-run` `too-dark` (it replaces only a fail); a bright image
    that does not change stays `fail` `no-image-effect`."""
    scripts = [good(brightness=((-7, 20), (-8, 8))), good(brightness=((-7, 12), (-8, 12))), good(brightness=())]
    with capture_app(monkeypatch, scripts) as app:
        devices = app.factory.device_infos()
        report = run_with(app, tmp_path, level="full")
    assert_valid(report)
    checks = by_name(report)
    dark_pass, dark_flat, flat = labels(devices)

    def image(label):
        check = checks[f"{label}:settings-stick:image-effect"]
        return check["result"], check["reason"]
    assert image(dark_pass) == ("pass", None)
    assert image(dark_flat) == ("not-run", "too-dark")
    assert image(flat) == ("fail", "no-image-effect")


def test_t_cert_13_the_image_rule_with_a_missing_frame():
    """4.3, 4.6 [proposed `no-frame`]: no frame at -7 or at -8 gives `not-run` `no-frame`, never `too-dark`; a black
    frame (mean 0) that does not change is `too-dark`; the bright limit is unchanged; the rule of each unit kind."""
    rule = product(CATALOG).image_effect
    assert rule(None, 60.0, "log2-s") == ("not-run", "no-frame")
    assert rule(120.0, None, "log2-s") == ("not-run", "no-frame")
    assert rule(0.0, 0.0, "log2-s") == ("not-run", "too-dark")
    assert rule(240.0, 120.0, "log2-s") == ("not-run", "too-bright")
    assert rule(120.0, 60.0, "log2-s") == ("pass", None)
    assert rule(120.0, 110.0, "log2-s") == ("fail", "no-image-effect")
    assert rule(120.0, 110.0, "ev") == ("pass", None)  # unitless: only the direction counts (ratio < 0.97)
    assert rule(20.0, 8.0, "log2-s") == ("pass", None)
    assert rule(20.0, 20.0, "log2-s") == ("not-run", "too-dark")
    assert rule(100.0, 84.96, "log2-s") == ("fail", "no-image-effect")  # the report shows `luma_ratio` 0.85
    assert "no-frame" in product(CATALOG).REASON_CODES and "no-frame" in known_codes()


def test_t_cert_23_in_part_the_dark_rule_of_a_rate_check():
    """T-CERT-23 in part, 4.6, 5.3: the rule that `auto-exposure:holds-rate:<base>` uses: a check that ends
    `too_slow` (`fail` `rate-low`) in a dark scene is `not-run` `too-dark`; a pass in the dark stays `pass`; with no
    frame there is no brightness, so the fail stays. (The Auto checks of `full` are not built; the run part of the
    test waits for them.)"""
    dark = product(CATALOG).in_the_dark
    assert dark(("fail", "rate-low"), 10.0) == ("not-run", "too-dark")
    assert dark(("pass", None), 10.0) == ("pass", None)
    assert dark(("fail", "rate-low"), 24.0) == ("fail", "rate-low")
    assert dark(("fail", "rate-low"), None) == ("fail", "rate-low")


# ---------------------------------------------------------------------------
# Q775 (Q47): the seams of T-CERT-15 and T-CERT-32
# ---------------------------------------------------------------------------

class ChildFault(FakeSourceFactory):
    """A picklable fake factory that, when it is unpickled in the session child (and only there), plants one fault
    of T-CERT-15: `exit` ends the child with `os._exit(5)` right after the take starts; `no-exit` keeps the child
    alive after its result; `bad-output` sends a value that is not a result right after the take starts."""

    def __init__(self, scripts, fault):
        super().__init__(scripts)
        self.fault = fault

    def __setstate__(self, state):
        self.__dict__.update(state)
        if multiprocessing.current_process().name != SESSION_CHILD:
            return
        if self.fault == "no-exit":
            threading.Thread(target=time.sleep, args=(60,), name="certify test: no exit").start()  # not a daemon
            return
        from skellycam.core.certify import run as child_run
        real, fault = child_run.run_session, self.fault

        async def faulty(manager, units, work, level, unix, begin, done, fact, sleep=time.sleep):
            def begin_then(name):
                begin(name)
                if name == "group:take:finished":
                    if fault == "exit":
                        os._exit(5)
                    done(b"\x00\xff not a result")
            await real(manager, units, work, level, unix, begin_then, done, fact, sleep)
        child_run.run_session = faulty


@pytest.mark.parametrize("fault", ["exit", "no-exit", "bad-output"])
def test_t_cert_15_the_session_child_ends_badly(tmp_path, fault):
    """T-CERT-15, C 2.5, 19.2 items 8 and 13: the session child ends with `os._exit(5)`: the running check is
    `crashed` with `exit_code` 5 (`not-run`: a crash blames no check, 19.2); it gives its result and does not end:
    `session:exit` `record-only` `hung-at-exit`; it gives bytes that are not a result: the running group check is
    `fail` `bad-output`, the run stops and writes no record row. No process is left. (The time-out case with a
    grandchild is test_review_9.)"""
    factory = ChildFault([good()], fault)
    (label,) = labels(factory.device_infos())
    before = descendants()
    report = product(RUN).run("quick", devices=factory.device_infos(), source_factory=factory, **paths(tmp_path))
    assert_valid(report)
    checks = by_name(report)
    assert checks[f"{label}:opens"]["result"] == "pass"
    take = checks["group:take:finished"]
    if fault == "exit":
        assert (take["result"], take["reason"], take.get("numbers")) == ("not-run", "crashed", {"exit_code": 5})
        assert "session:exit" not in checks and record(tmp_path) == []
    elif fault == "no-exit":
        assert take["result"] == "pass"
        assert (checks["session:exit"]["result"], checks["session:exit"]["reason"]) == ("record-only", "hung-at-exit")
    else:
        assert (take["result"], take["reason"]) == ("fail", "bad-output")
        assert "session:exit" not in checks and record(tmp_path) == []
    assert_no_new_process(before, wait_s=20.0)


def test_t_cert_15_drive_refuses_a_value_that_is_not_a_result():
    """C 2.5 `bad-output`: an event of the session child that is not a pair of a known kind and its value stops the
    drive loop with `bad-output` and stops the session; the checks that had ended keep their results."""
    from skellycam.tests.certify.test_certify_review import FakeSession
    run = product(RUN)
    for bad in (b"\x00\xff", ("done", b"\x00\xff"), ("what", 1), ("begin", 3), ("done", {"result": "pass"}),
                ("done", {"name": "zzz", "result": "pass", "reason": None}), ("done", {"name": "b", "result": "maybe"}),
                ("fact", ("before", 5)), ("fact", ("what", ("a", 1))), ("end", 3), "unpickle"):
        rows = {"a": None, "b": None}
        session = FakeSession([("begin", "a"), ("done", {"name": "a", "result": "pass", "reason": None})])
        if bad == "unpickle":  # the queue of a session child raises when the bytes do not unpickle
            session.events = Unpickles(session.events)
        else:
            session.events.put(bad)
        session.events.put(("begin", "b"))
        out = run._drive(session, rows, run._Progress(None, "quick"), run._Stops(None, None), time.monotonic() + 60,
                         "over-budget")
        assert out.stop == "bad-output" and session.stopped is not None, bad
        assert rows == {"a": {"name": "a", "result": "pass", "reason": None}, "b": None}, bad


class Unpickles(queue.Queue):
    """Gives the events of `events`, then raises as `multiprocessing.Queue.get` does for bytes that do not unpickle."""

    def __init__(self, events):
        super().__init__()
        while not events.empty():
            self.put(events.get_nowait())
        self.put(None)  # the place of the broken bytes

    def get(self, *args, **kwargs):
        item = super().get(*args, **kwargs)
        if item is None:
            raise pickle.UnpicklingError("invalid load key")
        return item


def test_the_session_child_sets_the_native_source(monkeypatch, tmp_path):
    """2.1, T-CERT-32: the session child calls `_native_capture` with its source factory before it builds anything;
    `_native_capture` sets the native source with no factory, leaves the setting with a factory, and its callable
    puts the old value back."""
    run = product(RUN)

    class Called(Exception):
        pass

    def stop_here(source_factory):
        raise Called(source_factory)
    with monkeypatch.context() as patch:
        patch.setattr(run, "_native_capture", stop_here)
        with pytest.raises(Called) as called:
            run._session_child(queue.Queue(), queue.Queue(), [], str(tmp_path), "quick", False, None)
    assert called.value.args == (None,)
    monkeypatch.setenv("SKELLYCAM_WINDOWS_CAPTURE", "opencv")
    run._native_capture(FakeSourceFactory([good()]))()
    assert os.environ["SKELLYCAM_WINDOWS_CAPTURE"] == "opencv"
    restore = run._native_capture(None)
    assert os.environ["SKELLYCAM_WINDOWS_CAPTURE"] == "media_foundation"
    restore()
    assert os.environ["SKELLYCAM_WINDOWS_CAPTURE"] == "opencv"
    monkeypatch.delenv("SKELLYCAM_WINDOWS_CAPTURE")
    run._native_capture(None)()
    assert "SKELLYCAM_WINDOWS_CAPTURE" not in os.environ


def test_t_cert_32_certify_uses_the_native_source_of_the_product_factory(monkeypatch, tmp_path):
    """T-CERT-32 in part, 2.1, 2.2: with `SKELLYCAM_WINDOWS_CAPTURE`, `SKELLYCAM_LINUX_CAPTURE` and
    `SKELLYCAM_MACOS_CAPTURE` set to `opencv` and no source factory of the test (the real factory of the product),
    each open creates the native source, and the OpenCV source is never created. The native source is a fake in
    place of `MediaFoundationSource`, so no camera opens."""
    if sys.platform != "win32":
        pytest.skip("Linux and macOS have no native source before phase 7 (Q777, session Q49)")
    for name in ("SKELLYCAM_WINDOWS_CAPTURE", "SKELLYCAM_LINUX_CAPTURE", "SKELLYCAM_MACOS_CAPTURE"):
        monkeypatch.setenv(name, "opencv")
    worker = product("skellycam.core.camera.camera_worker")
    opencv = product("skellycam.core.camera.capture.opencv_source")
    native = SimpleNamespace()  # in place of the module: its import would load comtypes into the test process
    monkeypatch.setitem(sys.modules, "skellycam.core.camera.capture.media_foundation.source", native)
    created, local = [], threading.local()
    with capture_app(monkeypatch, [good(), good()]) as app:
        factory = app.factory
        real = worker.create_capture_source

        def spy(config):  # the product factory itself; the spy keeps the config for the fake native source
            local.config = config
            return real(config)
        monkeypatch.setattr(worker, "create_capture_source", spy)
        monkeypatch.setattr(worker, "media_foundation_process", lambda used: __import__("contextlib").nullcontext())
        native.MediaFoundationSource = lambda: created.append("native") or factory(local.config)
        monkeypatch.setattr(opencv, "OpenCVSource", lambda config: created.append("opencv") or factory(config))
        app.manager.source_factory = None
        report = run_with(app, tmp_path)
    assert_valid(report)
    assert created and set(created) == {"native"}, created
    assert os.environ["SKELLYCAM_WINDOWS_CAPTURE"] == "opencv", "the thread session did not put the setting back"
    first, _ = labels(factory.device_infos())
    assert by_name(report)[f"{first}:opens"]["result"] == "pass"
