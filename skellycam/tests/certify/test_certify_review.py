"""The tests of the review fixes of the certify code and of format 1.6.0 (specs/certify.md 2.1, 2.3, 2.5, 8.3, 9.3,
9.5; contract `report-format.md` 1.6.0 2.4). Fake sources only; no test opens a camera.

The session-child tests use the real kill: a thread session cannot be killed, so it hides what a kill leaves.
"""

import json
import multiprocessing
import queue
import threading
import time
from pathlib import Path

import psutil
import pytest

from skellycam.tests.capture.capture_session import capture_app
from skellycam.tests.capture.fake_source import FakeSourceFactory
from skellycam.tests.certify.report_rules import assert_valid, problems
from skellycam.tests.certify.test_certify import (
    CATALOG, RUN, SOURCE_FACTS, by_name, good, group_checks, labels, paths, product, run_with, unit)


def descendants():
    return {p.pid for p in psutil.Process().children(recursive=True)}


def assert_no_new_process(before, wait_s=3.0):
    deadline = time.monotonic() + wait_s
    while (left := descendants() - before) and time.monotonic() < deadline:
        time.sleep(0.2)
    assert not left, left


def record(tmp_path):
    path = tmp_path / "camera_checks.json"
    return json.loads(path.read_text(encoding="utf-8"))["rows"] if path.exists() else []


# ---------------------------------------------------------------------------
# Finding 4: the record is keyed by model
# ---------------------------------------------------------------------------

def test_review_4_two_models_with_one_name_write_their_own_rows(monkeypatch, tmp_path):
    """2.5: each model gets the row of its own summary item, also when two models have one cleaned name."""
    scripts = [good(name="USB Video Device", rate=25.0), good(name="USB Video Device")]
    with capture_app(monkeypatch, scripts) as app:
        report = run_with(app, tmp_path)
    assert [(i["device"], i["result"]) for i in report["summary"]] == [("feed:0000", "fail"), ("feed:0001", "pass")]
    assert sorted((r["device"], r["item"]) for r in record(tmp_path)) == [("feed:0000", "fail"), ("feed:0001", "pass")]


# ---------------------------------------------------------------------------
# Finding 1: a wedge after the open
# ---------------------------------------------------------------------------

@pytest.mark.capture_timing
def test_review_1_a_hang_after_the_open_gives_camera_wedged(monkeypatch, tmp_path):
    """2.3, 8.3: a camera that hangs at the live change: the running check `fail` `hung`, the later checks
    `not-run` `prior-failure`, `gate:no-hang` `fail`, the cleanup row and the notice `camera-wedged`."""
    with capture_app(monkeypatch, [good(hang_at="set_controls"), good()], workers="process") as app:
        hung, fine = labels(app.factory.device_infos())
        log = app.factory.logs[app.factory.camera_ids[0]]

        def progress(message):
            if (message.get("step") or {}).get("name") == f"{hung}:settings-stick:readback":
                log.arm_hang()
        report = run_with(app, tmp_path, level="full", progress=progress)
        opens = log.opens.value
    assert_valid(report)
    checks = by_name(report)
    assert (checks[f"{hung}:settings-stick:readback"]["result"], checks[f"{hung}:settings-stick:readback"]["reason"]) \
        == ("fail", "hung")
    for name in ("settings-stick:holds", "settings-stick:image-effect", "records:rows-complete"):
        assert checks[f"{hung}:{name}"]["reason"] == "prior-failure", checks[f"{hung}:{name}"]
    assert checks[f"{hung.rsplit('.', 1)[0]}:gate:no-hang"]["result"] == "fail"
    assert {"name": f"release:{hung}", "result": "fail", "reason": "camera-wedged", "module": "Fake camera 0"} \
        in report["cleanup"]
    assert {"code": "camera-wedged", "values": {"camera": "Fake camera 0"}} in report["notices"]
    assert opens == 1
    assert checks[f"{fine}:records:rows-complete"]["result"] == "pass"


# ---------------------------------------------------------------------------
# Findings 2 and 5: a stop during the open
# ---------------------------------------------------------------------------

def test_review_2_and_5_a_cancel_during_the_open_in_a_session_child(tmp_path):
    """8.3: a cancel while the camera is in the middle of its open: the camera is never opened again, and it gets
    `camera-not-restored` with its notice, never `healthy`."""
    cancel = threading.Event()
    factory = FakeSourceFactory([good(open_delay_s=1.0)])
    (label,) = labels(factory.device_infos())

    def progress(message):
        if (message.get("step") or {}).get("name", "").startswith(f"{label}:modes:granted"):
            threading.Timer(2.0, cancel.set).start()
    before = descendants()
    report = product(RUN).run("quick", progress, cancel, devices=factory.device_infos(), source_factory=factory,
                              **paths(tmp_path))
    assert_valid(report)
    assert by_name(report)[f"{label}:opens"]["reason"] == "cancelled"
    assert factory.logs[factory.camera_ids[0]].opens.value == 1
    assert report["cleanup"] == [{"name": f"release:{label}", "result": "fail", "reason": "camera-not-restored",
                                  "module": "Fake camera 0"}]
    assert report["notices"] == [{"code": "camera-not-restored", "values": {"camera": "Fake camera 0"}}]
    assert_no_new_process(before)


def test_review_5_and_6_the_end_of_the_budget_during_the_open(tmp_path):
    """4.1, 8.3, 9.3: the budget ends while the camera opens: `over-budget`, no second open, `camera-not-restored`,
    and the call returns within its bound (budget, phase G with no open, the exit wait)."""
    factory = FakeSourceFactory([good(open_delay_s=30.0)])
    (label,) = labels(factory.device_infos())
    before = descendants()
    t0 = time.monotonic()
    report = product(RUN).run("quick", devices=factory.device_infos(), source_factory=factory, budget_s=8.0,
                              **paths(tmp_path))
    elapsed = time.monotonic() - t0
    assert_valid(report)
    assert by_name(report)[f"{label}:opens"]["reason"] == "over-budget"
    assert factory.logs[factory.camera_ids[0]].opens.value == 1
    assert [c["reason"] for c in report["cleanup"]] == ["camera-not-restored"]
    assert elapsed < 8.0 + product(RUN).EXIT_LIMIT_S + 3.0, elapsed
    assert_no_new_process(before)


@pytest.mark.parametrize("script, flagged", [
    (dict(rate=25.0), False), (dict(stop_after_frame=100), True),
    # finding 9 [Z7F3]: a later dict of the camera holds another `fail_code`; the status code `stalled` decides
    (dict(stop_after_frame=100, diagnostics={**SOURCE_FACTS, "fail_code": "stream-error"}), True)])
def test_review_2_a_failed_camera_that_was_set_is_flagged_only_when_the_product_does_not_restore_it(
        monkeypatch, tmp_path, script, flagged):
    """8.3, unix-capture.md 4.7 [Z7F3]: the product restores a camera whose loop failed for a reason that is not a
    wedge (a failed rate check, `rate-low`), so that camera gets no cleanup row. It does not restore a camera that
    stalled (`stalled`, no frame for 2 s) after its controls were set: that camera gets `camera-not-restored`."""
    with capture_app(monkeypatch, [good(**script), good()]) as app:
        failed, _ = labels(app.factory.device_infos())
        report = run_with(app, tmp_path)
    assert_valid(report)
    assert report["cleanup"] == ([{"name": f"release:{failed}", "result": "fail", "reason": "camera-not-restored",
                                   "module": "Fake camera 0"}] if flagged else [])


# ---------------------------------------------------------------------------
# Finding 3: the session child does not outlive its caller
# ---------------------------------------------------------------------------

def _caller_that_dies(factory, folder, pids_path):
    """A caller process that dies (os._exit) in the middle of a run."""
    import os
    from skellycam.core.certify import run
    (label,) = [lab for lab, _ in product(CATALOG).camera_labels(factory.device_infos(),
                                                                  product(CATALOG).system_backend())]

    def progress(message):
        if (message.get("step") or {}).get("name") == f"{label}:native-jpeg:format":
            kids = [dict(pid=p.pid, created=p.create_time()) for p in psutil.Process().children(recursive=True)]
            Path(pids_path).write_text(json.dumps(kids), encoding="utf-8")
            os._exit(1)
    folder = Path(folder)
    run.run("quick", progress, devices=factory.device_infos(), source_factory=factory,
            recording_folder=folder / "recordings", checks_path=folder / "camera_checks.json",
            evidence_path=folder / "camera_evidence.json", os_key="11 26H2", abi="lp64")


def test_review_3_the_session_child_ends_when_its_caller_dies(tmp_path):
    """2.1: when the caller dies, the session child closes the camera group (the close restores each camera) and
    ends, with its camera processes, within the limit."""
    factory = FakeSourceFactory([good()])
    pids_path = tmp_path / "pids.json"
    caller = multiprocessing.get_context("spawn").Process(target=_caller_that_dies,
                                                          args=(factory, str(tmp_path), str(pids_path)))
    caller.start()
    caller.join(120)
    kids = json.loads(pids_path.read_text(encoding="utf-8"))
    assert kids, "the caller recorded no child"
    left = []
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            left = [k for k in kids if psutil.pid_exists(k["pid"]) and _same(k)]
            if not left:
                break
            time.sleep(0.5)
        assert not left, f"the session tree outlived its caller: {left}"
        assert factory.logs[factory.camera_ids[0]].closes.value >= 1
    finally:
        for k in left:  # only the processes of this run (same pid and create time)
            try:
                psutil.Process(k["pid"]).kill()
            except psutil.NoSuchProcess:
                pass


def _same(kid):
    try:
        return abs(psutil.Process(kid["pid"]).create_time() - kid["created"]) < 0.01
    except psutil.NoSuchProcess:
        return False


# ---------------------------------------------------------------------------
# Finding 9: a time-out ends the main process of the session child, and the cameras restore
# ---------------------------------------------------------------------------

def test_review_9_a_time_out_lets_the_camera_processes_restore(tmp_path):
    """9.3: at a time-out, the caller ends the main process of the session child only; each camera process sees
    the dead server, closes its source (with the restore) and ends; then the rest of the tree is killed."""
    factory = FakeSourceFactory([good()])
    (label,) = labels(factory.device_infos())
    before = descendants()
    report = product(RUN).run("full", devices=factory.device_infos(), source_factory=factory, budget_s=10.0,
                              **paths(tmp_path))
    assert_valid(report)
    timed_out = [c for c in report["checks"] if c["reason"] == "timed-out" and c["result"] == "fail"]
    assert len(timed_out) <= 1
    assert by_name(report)[f"{label}:opens"]["result"] == "pass"
    assert factory.logs[factory.camera_ids[0]].closes.value >= 1, "the camera process did not close its source"
    assert record(tmp_path) == []
    assert_no_new_process(before)


# ---------------------------------------------------------------------------
# Finding 7: a cancel keeps each check that had ended
# ---------------------------------------------------------------------------

class FakeSession:
    def __init__(self, events):
        self.events, self.acked, self.stopped = queue.Queue(), [], None
        for event in events:
            self.events.put(event)

    def ack(self, ok):
        self.acked.append(ok)

    def stop(self, mode="kill"):
        self.stopped = mode

    def alive(self):
        return self.stopped is None

    def remember(self):
        pass


def test_review_7_a_cancel_keeps_the_checks_that_had_ended():
    """C 2.4: a `done` that was in the queue when the cancel came keeps its result; a check that starts later
    does not start."""
    run = product(RUN)
    rows = {"a": None, "b": None}
    session = FakeSession([("begin", "a"), ("done", {"name": "a", "result": "pass", "reason": None}),
                           ("begin", "b")])

    class Cancel:
        def is_set(self):
            return bool(session.acked)  # set right after the caller let `a` start
    stops = run._Stops(Cancel(), None)
    result = run._drive(session, rows, run._Progress(None, "quick"), stops, time.monotonic() + 60, "over-budget")
    assert result.stop == "cancelled"
    assert rows["a"] == {"name": "a", "result": "pass", "reason": None}
    assert rows["b"] is None and session.acked == [True, False]  # `b` is refused: it never starts


# ---------------------------------------------------------------------------
# Finding 8: a crash or a refused apply during the one group open
# ---------------------------------------------------------------------------

def test_review_8_a_crash_in_the_group_open_blames_no_camera(monkeypatch, tmp_path):
    """A crash of the session in the one apply: each open check is `not-run` with the cause; no `fail`; no record."""
    with capture_app(monkeypatch, [good(), good()]) as app:
        async def crash(configs):
            raise KeyboardInterrupt  # a fault that the session does not catch
        monkeypatch.setattr(app.manager, "create_or_update_camera_group", crash)
        report = run_with(app, tmp_path)
    assert_valid(report)
    assert not [c for c in report["checks"] if c["result"] == "fail"]
    first, _ = labels(app.factory.device_infos())
    assert by_name(report)[f"{first}:opens"]["reason"] == "KeyboardInterrupt"
    assert record(tmp_path) == []


def test_review_8_a_refused_apply_blames_no_camera(monkeypatch, tmp_path):
    """A refused apply: each `opens` is `not-run` with the class name of the refusal; no `fail`; no record row."""
    from skellycam.core.camera_group.camera_group import RequestRefused
    with capture_app(monkeypatch, [good(), good()]) as app:
        async def refuse(configs):
            raise RequestRefused(422, "test")
        monkeypatch.setattr(app.manager, "create_or_update_camera_group", refuse)
        report = run_with(app, tmp_path)
    assert_valid(report)
    assert not [c for c in report["checks"] if c["result"] == "fail"]
    first, _ = labels(app.factory.device_infos())
    assert by_name(report)[f"{first}:opens"]["reason"] == "RequestRefused"
    assert record(tmp_path) == []


# ---------------------------------------------------------------------------
# Finding 10: one run at a time; a failed record write
# ---------------------------------------------------------------------------

def test_review_10_a_second_run_is_refused(tmp_path):
    """9.5: a run holds a lock in the base folder; a second run is refused with `cameras-busy` and makes no work
    folder."""
    from skellycam.core.take_recorder import folder_files
    lock = tmp_path / product(RUN).LOCK_FILE
    lock.touch()
    factory = FakeSourceFactory([good()])
    (tmp_path / "recordings").mkdir()
    with folder_files.take_lock(lock, 1.0):
        report = product(RUN).run("quick", devices=factory.device_infos(), source_factory=factory,
                                  **paths(tmp_path))
    assert_valid(report)
    assert all(c["reason"] == "cameras-busy" for c in report["checks"])
    assert "cameras-busy" in report["evidence"]["reasons"]
    assert not list((tmp_path / "recordings").iterdir())
    assert not factory.sources


def test_review_10_a_failed_record_write_gives_a_cleanup_row(monkeypatch, tmp_path):
    """C 2.2, C 2.5: a record file that cannot be written gives the cleanup row `write-record`; the report returns."""
    target = tmp_path / "camera_checks.json"
    target.mkdir()  # a folder where the file must go: the replace fails
    with capture_app(monkeypatch, [good()]) as app:
        report = run_with(app, tmp_path)
    assert_valid(report)
    rows = [c for c in report["cleanup"] if c["name"] == "write-record"]
    assert len(rows) == 1 and rows[0]["result"] == "fail" and rows[0]["reason"].endswith("Error")


# ---------------------------------------------------------------------------
# Finding 6: the detection is inside the budget
# ---------------------------------------------------------------------------

def test_review_6_the_detection_is_inside_the_budget(monkeypatch):
    """4.1: a detection that does not end before the end of the budget is `not-run` `over-budget` at that time."""
    run = product(RUN)
    detect_module = product("skellycam.core.camera.capture.media_foundation.detect")
    monkeypatch.setattr(detect_module, "detect_media_foundation_cameras", lambda **kwargs: time.sleep(5) or [])
    t0 = time.monotonic()
    detect_row, devices = run._detect("media-foundation", run._Stops(None, None), t0 + 0.5, "over-budget")
    assert time.monotonic() - t0 < 1.5
    assert (detect_row["result"], detect_row["reason"]) == ("not-run", "over-budget") and devices == []


# ---------------------------------------------------------------------------
# Findings 12 and 13
# ---------------------------------------------------------------------------

def test_review_12_gaps_are_explained_by_the_replaced_frames_of_the_wide_window():
    """4.5: each gap needs a replaced frame; the window of the replaced count is wider than the rows of the take."""
    explained = product(CATALOG).gaps_explained
    assert explained(0, 0) and explained(2, 3) and explained(3, 3)
    assert not explained(3, 2)


def test_review_13_only_the_base_mode_counts_for_the_item_and_the_gate():
    """3.4, 11.3: a mode check above `<base>` changes neither the item nor `gate:mode`."""
    catalog = product(CATALOG)
    label = "cam.x.0001-0002.0"
    rows = unit(label)
    rows[f"{label}:modes:granted:1280x720@60"] = {"name": f"{label}:modes:granted:1280x720@60", "result": "fail",
                                                  "reason": "mode-not-granted"}
    assert catalog.item_result([rows]) == "pass"
    gate = {r["name"]: r for r in catalog.gate_rows("cam.x.0001-0002", [rows], "Fake")}
    assert gate["cam.x.0001-0002:gate:mode"]["result"] == "pass"


# ---------------------------------------------------------------------------
# Format 1.6.0: abandon, the schema, and the validator
# ---------------------------------------------------------------------------

def test_format_1_6_0_abandon(monkeypatch, tmp_path):
    """C 1.6.0 2.4: `abandon` stops the run as a cancel does, the record gets no row, and a report still returns;
    with `cancel` also set, the abandon rules apply; `certify_plan` does not take `abandon`."""
    import inspect

    import skellycam
    assert inspect.signature(skellycam.certify).parameters["abandon"].kind is inspect.Parameter.KEYWORD_ONLY
    assert "abandon" not in inspect.signature(skellycam.certify_plan).parameters
    abandon, cancel = threading.Event(), threading.Event()

    def progress(message):
        if (message.get("step") or {}).get("name") == "group:take:finished":
            abandon.set()
            cancel.set()
    with capture_app(monkeypatch, [good()]) as app:
        report = run_with(app, tmp_path, progress=progress, cancel=cancel, abandon=abandon)
    assert_valid(report)
    assert report["schema"] == "skellycertify.report/1.7.0"
    assert by_name(report)["group:take:finished"]["reason"] == "cancelled"
    assert "cancelled" in report["evidence"]["reasons"]
    assert record(tmp_path) == []


def base_report():
    return {"schema": "skellycertify.report/1.7.0",
            "package": {"name": "skellycam", "version": "2.0.0", "commit": None, "tree_modified": None},
            "kind": "quick", "created_utc": "2026-11-21T00:00:00Z", "host": {"os": None, "cpu": None},
            "checks": [{"name": "detect", "result": "pass", "reason": None}],
            "evidence": {"valid": False, "reasons": ["no-commit", "modified-tree"]}}


def test_the_validator_rules_of_the_review_and_of_1_6_0():
    """The validator refuses each form that the review and formats 1.6.0 and 1.7.0 name (3.6.1: the schema
    `skellycertify.report/1.7.0`; the name of a test media file is exempt from rule 7 only there)."""
    assert problems(base_report()) == []
    cases = {
        "no-commit missing": dict(evidence={"valid": False, "reasons": ["modified-tree"]}),
        "a cleanup row that passes": dict(cleanup=[{"name": "x", "result": "pass", "reason": None}]),
        "a camera device of another form": dict(summary=[{"group": "camera", "name": "C", "device": "feed",
                                                          "result": "pass"}]),
        "a gate that is not a roll-up": dict(
            checks=[{"name": "detect", "result": "fail", "reason": "timed-out"}],
            summary=[{"group": "camera", "name": "C", "device": "feed:0000", "result": "pass", "gate": "detect"}]),
        "not-installed on a camera": dict(summary=[{"group": "camera", "name": "C", "device": "feed:0000",
                                                    "result": "skipped", "reason": "not-installed"}]),
        "a bad test_media item": dict(test_media=[{"name": "x", "sha256": "abc", "bytes": -1, "source": "web"}]),
        "a bad shared_memory_bytes": dict(host={"gpus": [{"name": "G", "id": "10de:2484",
                                                          "shared_memory_bytes": -5}]}),
        "the schema of format 1.6.0": dict(schema="skellycertify.report/1.6.0"),
        "a media name outside test_media": dict(
            test_media=[{"name": "quick_frames.mp4", "sha256": "a" * 64, "bytes": 10, "source": "bundled"}],
            checks=[{"name": "detect", "result": "pass", "reason": None, "numbers": {"file": "quick_frames.mp4"}}]),
    }
    for what, change in cases.items():
        assert problems({**base_report(), **change}), what
    good_cases = [dict(summary=[{"group": "component", "name": "Blender", "device": None, "result": "skipped",
                                 "reason": "not-installed"}]),
                  dict(test_media=[{"name": "quick_frames.zip", "sha256": "a" * 64, "bytes": 10,
                                    "source": "bundled"}]),
                  dict(test_media=[{"name": "quick_frames.mp4", "sha256": "a" * 64, "bytes": 10,
                                    "source": "bundled"}])]
    for change in good_cases:
        assert problems({**base_report(), **change}) == [], change
    assert group_checks  # the helper of the first test file stays importable
