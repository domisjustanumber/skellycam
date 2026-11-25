"""The tests of the report shape of quick and full (specs/certify.md 3.5.2, 3.6; the build order of 3.6.7). Fake
sources only; no test opens a camera. Each test names the T-CERT test of section 17 that it covers, in whole or in
part; a part that a later step of 3.6.7 builds joins at that step.
"""

import json
import subprocess
import threading
import time

import pytest

from skellycam.tests.capture.capture_session import capture_app
from skellycam.tests.capture.fake_source import FakeSourceFactory
from skellycam.tests.certify.report_rules import assert_valid
from skellycam.tests.certify.test_certify import (
    CATALOG, RUN, SOURCE_FACTS, InUseFactory, by_name, good, labels, paths, product, run_with, same_model)
from skellycam.tests.certify.test_certify_review import assert_no_new_process, descendants

COMMIT = "0123456789abcdef0123456789abcdef01234567"


# ---------------------------------------------------------------------------
# Step 1: B1 (3.6.1) and the commit and the tree state (3.5.2)
# ---------------------------------------------------------------------------

def test_t_cert_93_the_gate_no_hang_reads_each_fail_row():
    """T-CERT-93 in part, 3.6.1 B1: `<model>:gate:no-hang` fails with `hung`, `crashed` and `stalled` on any row of
    the model; a `device-removed` row and a `stream-error` row do not fail it."""
    gate = product(CATALOG).gate_rows
    model, label = "cam.x.0001-0002", "cam.x.0001-0002.0"
    for reason, expected in (("stalled", ("fail", "stalled")), ("crashed", ("fail", "crashed")),
                             ("hung", ("fail", "hung")), ("device-removed", ("pass", None)),
                             ("stream-error", ("pass", None))):
        rows = {f"{label}:opens": {"name": f"{label}:opens", "result": "pass", "reason": None},
                f"{label}:settings-stick:readback": {"name": f"{label}:settings-stick:readback", "result": "fail",
                                                     "reason": reason}}
        no_hang = next(r for r in gate(model, [rows], "Fake") if r["name"] == f"{model}:gate:no-hang")
        assert (no_hang["result"], no_hang["reason"]) == expected, reason


def test_t_cert_93_b1_a_camera_that_leaves_the_run_between_two_steps(tmp_path):
    """T-CERT-93, 3.6.1 B1, session child: a camera that stalls after `ready` and before the settings change, one
    whose camera process ends there with `os._exit(3)`, one with a stream error in the take, one removed in the take
    and one with a stream error in the ready step (a code that is not a wedge code). Each gets one `fail` row on the
    first check that has no result, with the failure facts that have a value and `module` = its model. Each other
    check that no progress message named is in its one `not-reached` row, wherever it stands (ADR-0Z6Q item 11).
    `<model>:gate:no-hang` is `fail` for the stall and the crash and `pass` for the others."""
    scripts = [good(on_arm="stall"), good(on_arm="exit"), good(on_arm="remove", removed_code="stream-error"),
               good(on_arm="remove"), good(on_arm="remove", removed_code="stream-error")]
    factory = FakeSourceFactory(scripts)
    stall, crash, error, removed, ready_error = labels(factory.device_infos())
    log = {label: factory.logs[camera_id] for label, camera_id in zip(labels(factory.device_infos()),
                                                                      factory.camera_ids)}
    named = set()

    def arm_in_take():
        log[error].arm()
        log[removed].arm()

    def progress(message):
        name = (message.get("step") or {}).get("name")
        named.add(name)
        if name == f"{crash}:native-jpeg:source-equals-ring":  # the last check of the ready step of these two
            log[stall].arm()
            log[crash].arm()
            time.sleep(3.5)  # the product declares a stall after 2 s with no frame
        elif name == f"{ready_error}:native-jpeg:format":  # the ready step scans this camera after this message
            log[ready_error].arm()
            time.sleep(2.0)
        elif name == "group:take:finished":
            threading.Timer(2.0, arm_in_take).start()  # in the take of 3 s, after the record start
    before = descendants()
    report = product(RUN).run("full", progress, devices=factory.device_infos(), source_factory=factory,
                              **paths(tmp_path))
    assert_valid(report)
    checks = by_name(report)
    expected = {stall: ("settings-stick:readback", "stalled"), crash: ("settings-stick:readback", "crashed"),
                error: ("records:rows-complete", "stream-error"), removed: ("records:rows-complete", "device-removed"),
                ready_error: ("native-jpeg:format", "stream-error")}
    for index, (label, (check, reason)) in enumerate(expected.items()):
        row = checks[f"{label}:{check}"]
        assert (row["result"], row["reason"], row["module"]) == ("fail", reason, f"Fake camera {index}"), row
        numbers = row.get("numbers", {})
        assert numbers.get("stage") == "streaming", row
        assert all(value is not None for key, value in numbers.items() if key != "exit_code"), row
        own = [c for c in report["checks"] if c["name"].startswith(label + ":")]
        assert [c["name"] for c in own if c["result"] == "fail"] == [row["name"]], own
        reached = [c for c in own if c["name"] == f"{label}:not-reached"]
        assert len(reached) == 1 and reached[0]["module"] == row["module"], own
        assert own.index(reached[0]) > own.index(row), own  # the row stands after the fail row (ADR-0Z6Q item 11)
        # M1 of the review: no filled row outside the `not-reached` row, also before the fail row
        assert not [c["name"] for c in own if c["result"] == "not-run" and c is not reached[0]
                    and c["name"] not in named], own
    assert checks[f"{crash}:settings-stick:readback"]["numbers"]["exit_code"] == 3
    for label, result in ((stall, "fail"), (crash, "fail"), (error, "pass"), (removed, "pass"),
                          (ready_error, "pass")):
        assert checks[f"{label.rsplit('.', 1)[0]}:gate:no-hang"]["result"] == result, label
    assert_no_new_process(before)


def write_build_file(path, **content):
    path.write_text(json.dumps(content), encoding="utf-8")
    return path


def test_t_cert_77_the_build_file(monkeypatch, tmp_path):
    """T-CERT-77, 3.5.2: a valid build file gives the commit, `false`, and neither `no-commit` nor `modified-tree`;
    no file, a file that does not parse, a commit of 39 hex digits and a `tree_modified` that is a string each give
    `null`, `null` and both reasons; no run reads git."""
    run = product(RUN)
    good_file = write_build_file(tmp_path / "good.json", commit=COMMIT, tree_modified=False)
    assert run.read_build_info(good_file) == (COMMIT, False)
    bad = [tmp_path / "missing.json", tmp_path / "broken.json",
           write_build_file(tmp_path / "short.json", commit=COMMIT[:39], tree_modified=False),
           write_build_file(tmp_path / "text.json", commit=COMMIT, tree_modified="false")]
    bad[1].write_text("{not json", encoding="utf-8")
    for path in bad:
        assert run.read_build_info(path) == (None, None), path
        reasons = run.evidence_reasons("2.0.0-alpha.6", *run.read_build_info(path), [])
        assert {"no-commit", "modified-tree"} <= set(reasons), path
    assert run.evidence_reasons("2.0.0-alpha.6", COMMIT, False, []) == []
    real_popen = subprocess.Popen

    class NoGit(real_popen):
        def __init__(self, args, *rest, **options):
            assert "git" not in str(args).lower(), args
            super().__init__(args, *rest, **options)
    monkeypatch.setattr(subprocess, "Popen", NoGit)
    monkeypatch.setattr(run, "BUILD_INFO", good_file)
    with capture_app(monkeypatch, [good()]) as app:
        report = run_with(app, tmp_path)
    assert_valid(report)
    assert report["package"]["commit"] == COMMIT and report["package"]["tree_modified"] is False
    assert not {"no-commit", "modified-tree"} & set(report["evidence"]["reasons"])


def test_a_build_file_in_a_source_checkout_is_ignored(tmp_path):
    """P2-M2 of the review, 3.5.2, ADR-0Z6Q item 17: a run from a source checkout (a `.git` folder, or the `.git` file
    of a worktree, beside the package folder) ignores the build file and gives `null` and `null`; else it reads it."""
    run = product(RUN)
    package = tmp_path / "skellycam"
    package.mkdir()
    build = write_build_file(package / "build_info.json", commit=COMMIT, tree_modified=False)
    assert run.build_values(build) == (COMMIT, False)
    (tmp_path / ".git").mkdir()
    assert run.build_values(build) == (None, None)
    (tmp_path / ".git").rmdir()
    (tmp_path / ".git").write_text("gitdir: elsewhere", encoding="utf-8")
    assert run.build_values(build) == (None, None)


def test_t_cert_27_versions_the_tree_and_a_part_of_the_cameras(monkeypatch, tmp_path):
    """T-CERT-27, 3.5.2, 2.4: the version `2.0.0a6` gives `no-version` and `2.0.0-a6` does not; a valid commit with
    `tree_modified` true gives `modified-tree` and no `no-commit`; a run with the option `cameras` of one of four
    labels gives no `partial-run`."""
    import skellycam
    run = product(RUN)
    assert "no-version" in run.evidence_reasons("2.0.0a6", COMMIT, False, [])
    assert run.evidence_reasons("2.0.0-a6", COMMIT, False, []) == []
    monkeypatch.setattr(skellycam, "__version__", "v2.0.0a6")
    monkeypatch.setattr(run, "BUILD_INFO", write_build_file(tmp_path / "build_info.json", commit=COMMIT,
                                                            tree_modified=True))
    with capture_app(monkeypatch, [good(), good(), good(), good()]) as app:
        first, *others = labels(app.factory.device_infos())
        report = run_with(app, tmp_path, cameras=[first])
    assert_valid(report)
    assert report["package"] == {"name": "skellycam", "version": "2.0.0a6", "commit": COMMIT, "tree_modified": True}
    reasons = report["evidence"]["reasons"]
    assert "no-version" in reasons and "modified-tree" in reasons
    assert "no-commit" not in reasons and "partial-run" not in reasons
    assert by_name(report)[f"{first}:opens"]["result"] == "pass"
    assert not [c for c in report["checks"] if any(c["name"].startswith(label + ":") for label in others)]


# ---------------------------------------------------------------------------
# Step 3: `details.not_built`, no `same-model` row, the plan total with `session:exit` (3.6.1, 3.6.3)
# ---------------------------------------------------------------------------

def plan_options(tmp_path):
    return {key: value for key, value in paths(tmp_path).items() if key != "recording_folder"}


@pytest.mark.parametrize("level", ["quick", "full"])
def test_t_cert_91_a_check_with_no_code_has_no_row(monkeypatch, tmp_path, level):
    """T-CERT-91, 3.6.1, 3.6.3: 4 fakes of 3 models, two of one model. No row has `not-built` for a check with no
    code, and no row has `same-model`; `details.not_built.camera` and `.run` hold each such name one time, sorted,
    with `base` for the mode of `<base>`; the plan `total` and `details.checks` count no such check; a check with code
    whose diagnostics key is `null` keeps `not-run` `not-built` and counts in `total`."""
    catalog = product(CATALOG)
    unfilled = good(diagnostics={**SOURCE_FACTS, "long_intervals": None})
    with capture_app(monkeypatch, [good(), good(), good(), unfilled]) as app:
        devices = same_model(app.factory.device_infos(), 0, 1)
        plan = product(RUN).plan(level, devices=devices, **plan_options(tmp_path))
        report = run_with(app, tmp_path, level=level, devices=devices)
    assert_valid(report)
    not_built = report["details"]["not_built"]
    assert set(not_built) == {"camera", "run"}
    for names in not_built.values():
        assert names == sorted(set(names)), names
    no_code = set(not_built["run"]) | {f"{label}:{name}" for label in labels(devices) for name in not_built["camera"]}
    no_code |= {f"{label}:{name.replace('base', catalog.mode_name(640, 480, 30.0))}" for label in labels(devices)
                for name in not_built["camera"]}
    assert not [c for c in report["checks"] if c["name"] in no_code]
    assert not [c for c in report["checks"] if c["reason"] == "same-model"]
    assert not [name for name in plan["details"]["checks"] if name in no_code]
    assert plan["total"] == len(plan["details"]["checks"]) + 1 == len(report["checks"]) + 1  # with `session:exit`
    if level == "quick":
        assert not_built == {"camera": [], "run": ["group:open", "self:hang-100ms:gap", "self:hang-100ms:hard-end"]}
    else:
        assert {"cycles", "exposure:base", "auto-exposure:searched:base"} <= set(not_built["camera"])  # Q624: no `timings`
        assert {"group:contention", "group:take-30:finished", "self:idle-cpu"} <= set(not_built["run"])
        last = labels(devices)[-1]
        assert (by_name(report)[f"{last}:time-gaps"]["result"], by_name(report)[f"{last}:time-gaps"]["reason"]) \
            == ("not-run", "not-built")
        assert f"{last}:time-gaps" in plan["details"]["checks"]


@pytest.mark.parametrize("hang", [False, True])
def test_t_cert_103_the_plan_total_counts_session_exit(monkeypatch, tmp_path, hang):
    """T-CERT-103, 3.6.1: the plan counts `session:exit`; with a clean exit there is no `session:exit` row and the
    last `done` equals `total`; with a hang at the exit the row is `record-only` `hung-at-exit` and `done` equals
    `total`; no message has `done` above `total`."""
    run = product(RUN)
    if hang:
        finish = run._ThreadSession.finish
        monkeypatch.setattr(run._ThreadSession, "finish", lambda self: finish(self) or True)
    messages = []
    with capture_app(monkeypatch, [good()]) as app:
        plan = run.plan("quick", devices=app.factory.device_infos(), **plan_options(tmp_path))
        report = run_with(app, tmp_path, progress=messages.append)
    assert_valid(report)
    assert plan["total"] == len(plan["details"]["checks"]) + 1
    exit_row = by_name(report).get("session:exit")
    if hang:
        assert (exit_row["result"], exit_row["reason"]) == ("record-only", "hung-at-exit")
    else:
        assert exit_row is None
    assert messages[-1]["state"] == "done" and messages[-1]["done"] == messages[-1]["total"] == plan["total"]
    assert all(m["done"] <= m["total"] for m in messages if m["total"] is not None)


# ---------------------------------------------------------------------------
# Step 4: `<label>:not-reached` and the `done` count (3.6.1)
# ---------------------------------------------------------------------------

def assert_not_reached(report, plan, messages, expected, all_labels):
    """Each camera of `expected` ({label: reason}) has one `not-reached` row with `not-run`, the reason of the first
    check that it stands for, `module` = the name of its item and `checks` = the count of the checks that it
    stands for; each camera check that a progress message named keeps its own row; `done` ends at `total`."""
    checks = by_name(report)
    named = {(m.get("step") or {}).get("name") for m in messages}
    items = {i["name"] for i in report.get("summary", [])}
    for label, reason in expected.items():
        row = checks[f"{label}:not-reached"]
        own = [c for c in report["checks"] if c["name"].startswith(label + ":") and c is not row]
        planned = [n for n in plan["details"]["checks"] if n.startswith(label + ":")]
        assert (row["result"], row["reason"]) == ("not-run", reason), row
        assert row["module"] in items, row
        assert row["numbers"] == {"checks": len(planned) - len(own)} and row["numbers"]["checks"] > 0, (row, own)
        assert not [n for n in planned if n in named and n not in checks], label
    for label in set(all_labels) - set(expected):
        assert f"{label}:not-reached" not in checks, label
    totals = [m for m in messages if m["total"] is not None]
    assert totals[-1]["state"] == "done" and totals[-1]["done"] == totals[-1]["total"] == plan["total"]
    assert all(m["done"] <= m["total"] for m in totals)


def test_t_cert_92_17_one_not_reached_row_for_a_camera_that_cannot_go_on(monkeypatch, tmp_path):
    """T-CERT-92, T-CERT-17, 3.6.1: a camera in use, one with no MJPG mode and one with a rate failure, beside a
    good camera: each of the first three has one `not-reached` row (`camera-in-use`, `no-mjpg-mode`,
    `prior-check-failed`); the good camera has none; `done` counts a `not-reached` row as its checks."""
    yuy2 = good(modes=((640, 480, 30, 1, "YUY2"),))
    messages = []
    with capture_app(monkeypatch, [good(), yuy2, good(rate=25.0), good()]) as app:
        factory = InUseFactory(app.factory.scripts, clock=app.factory.clock)  # the first camera is in use
        app.manager.source_factory = app.factory = factory
        devices = factory.device_infos()
        plan = product(RUN).plan("quick", devices=devices, **plan_options(tmp_path))
        report = run_with(app, tmp_path, progress=messages.append)
    assert_valid(report)
    busy, no_mjpg, slow, fine = labels(devices)
    assert_not_reached(report, plan, messages, {busy: "camera-in-use", no_mjpg: "no-mjpg-mode",
                                                slow: "prior-check-failed"}, labels(devices))
    checks = by_name(report)
    assert checks[f"{busy}:opens"]["reason"] == "camera-in-use"  # named by its progress message: its own row
    # ADR-0Z6Q item 11: a camera with no MJPG mode has no row of its own after the detection
    assert [c["name"] for c in report["checks"] if c["name"].startswith(no_mjpg + ":")] == [
        f"{no_mjpg}:detect", f"{no_mjpg}:detect:mjpg-mode", f"{no_mjpg}:not-reached"]
    assert checks[f"{slow}:rate"]["reason"] == "rate-low"
    assert [i["result"] for i in report["summary"]] == ["skipped", "partial", "fail", "pass"]


@pytest.mark.capture_timing
def test_t_cert_92_a_hang_at_the_open(monkeypatch, tmp_path):
    """T-CERT-92, 3.6.1: a camera that hangs at the open has one `not-reached` row with `prior-failure`."""
    messages = []
    with capture_app(monkeypatch, [good(hang_at="open", hang_armed=True), good()], workers="process") as app:
        devices = app.factory.device_infos()
        plan = product(RUN).plan("quick", devices=devices, **plan_options(tmp_path))
        report = run_with(app, tmp_path, progress=messages.append)
    assert_valid(report)
    hung, _ = labels(devices)
    assert by_name(report)[f"{hung}:opens"]["reason"] == "hung"
    assert_not_reached(report, plan, messages, {hung: "prior-failure"}, labels(devices))


def test_t_cert_92_a_cancel_in_the_take_and_the_end_of_the_budget(monkeypatch, tmp_path):
    """T-CERT-92, 3.6.1: a cancel when the take starts gives each camera one `not-reached` row with `cancelled` for
    its checks after the take, and `group:take:finished` keeps its own row; a budget that ends before the take gives
    each camera one `not-reached` row with `over-budget`."""
    cancel = threading.Event()
    messages = []

    def progress(message):
        messages.append(message)
        if (message.get("step") or {}).get("name") == "group:take:finished":
            cancel.set()
    with capture_app(monkeypatch, [good(), good()]) as app:
        devices = app.factory.device_infos()
        plan = product(RUN).plan("quick", devices=devices, **plan_options(tmp_path))
        report = run_with(app, tmp_path, progress=progress, cancel=cancel)
    assert_valid(report)
    assert by_name(report)["group:take:finished"]["reason"] == "cancelled"
    assert_not_reached(report, plan, messages, {label: "cancelled" for label in labels(devices)}, labels(devices))
    messages = []
    with capture_app(monkeypatch, [good()]) as app:
        devices = app.factory.device_infos()
        plan = product(RUN).plan("quick", devices=devices, **plan_options(tmp_path))
        report = run_with(app, tmp_path, progress=messages.append, budget_s=0.0)
    assert_valid(report)
    (label,) = labels(devices)
    assert_not_reached(report, plan, messages, {label: "over-budget"}, [label])


# ---------------------------------------------------------------------------
# The fix round of the review of 2026-11-23
# ---------------------------------------------------------------------------

def test_a_gate_step_whose_check_is_in_the_not_reached_row_is_not_run():
    """ADR-0Z6Q item 12: a gate step whose required check stands in the `not-reached` row is `not-run`
    `gate-check-not-run`; a step whose checks all have their own `pass` rows passes; the item is `partial`."""
    catalog = product(CATALOG)
    model, label = "cam.x.0001-0002", "cam.x.0001-0002.0"
    names = ["detect", "detect:mjpg-mode", "opens", "rate", "modes:granted:640x480@30", "native-jpeg:format",
             "native-jpeg:not-reencoded", "native-jpeg:source-equals-ring", "settings-stick:readback",
             "settings-stick:holds", "settings-stick:image-effect", "native-jpeg:valid", "native-jpeg:size",
             "native-jpeg:ring-equals-mkv"]
    rows = {f"{label}:{n}": {"name": f"{label}:{n}", "result": "pass", "reason": None} for n in names}
    rows[f"{label}:not-reached"] = {"name": f"{label}:not-reached", "result": "not-run", "reason": "cancelled",
                                    "numbers": {"checks": 4}}
    gate = {r["name"]: r for r in catalog.gate_rows(model, [rows], "Fake")}
    assert (gate[f"{model}:gate:records"]["result"], gate[f"{model}:gate:records"]["reason"]) == (
        "not-run", "gate-check-not-run")
    assert gate[f"{model}:gate:native-jpeg"]["result"] == "pass"
    assert gate[f"{model}:gate"]["result"] == "not-run"
    assert catalog.item_result([rows]) == "partial"


def test_the_failure_facts_of_a_b1_row():
    """3.5.3, ADR-0Z6Q item 5: each failure fact only with a value; `native_domain` only beside `native_code`;
    `first_fail_code` only when it differs from the code; `exit_code` on each `crashed` row (also `null`) and on a
    `hung` row that has it; the failure text is not copied."""
    facts = product("skellycam.core.certify.session").failure_facts
    data = {"call": "reader-release", "native_code": 2147942405, "native_domain": "hresult",
            "first_fail_code": "first-frame-timeout"}
    assert facts({"stage": "first frame", "reason": "camera process ended (exit code 1)"}, data, "hung", "hung") == {
        "stage": "first-frame", "call": "reader-release", "native_code": 2147942405, "native_domain": "hresult",
        "first_fail_code": "first-frame-timeout", "exit_code": 1}
    assert facts({"stage": "streaming", "reason": "no frame"}, {"native_domain": "hresult"}, "stalled", "stalled") == {
        "stage": "streaming"}
    assert facts({}, {"first_fail_code": "process-ended"}, "process-ended", "crashed") == {"exit_code": None}


def test_done_equals_total_after_a_refused_run(monkeypatch, tmp_path):
    """3.6.1, ADR-0Z6Q item 10: a run that an open camera group refuses ends with `done` equal to `total`."""
    manager_module = product("skellycam.core.camera_group.camera_group_manager")
    monkeypatch.setattr(manager_module, "_CAMERA_GROUP_MANAGER", type("M", (), {"camera_groups": {"g": 1}})())
    factory = FakeSourceFactory([good()])
    messages = []
    report = product(RUN).run("quick", messages.append, devices=factory.device_infos(), source_factory=factory,
                              **paths(tmp_path))
    assert_valid(report)
    assert "cameras-busy" in report["evidence"]["reasons"]
    last = messages[-1]
    assert last["state"] == "done" and last["done"] == last["total"] == len(report["checks"]) + 1


def test_the_default_build_file_path():
    """3.5.2: the run reads `skellycam/build_info.json` beside the package code."""
    import skellycam
    from pathlib import Path
    assert product(RUN).BUILD_INFO == Path(skellycam.__file__).resolve().parent / "build_info.json"


# ---------------------------------------------------------------------------
# Q646 (ADR-056Z): a camera that leaves after its take checks and at the close
# ---------------------------------------------------------------------------

def test_t_cert_133_a_camera_that_leaves_after_its_take_checks_or_at_the_close(tmp_path):
    """T-CERT-133, 3.6.1, 3.6.2 [U Q646], ADR-0Z6Q item 15, session child, full: a camera process that ends after the
    take checks, a camera that stalls there, a camera that hangs at the close and a camera process that ends at the
    close, beside a good camera. Each of the four gets `<label>:live-at-close` `fail` with the product code and the
    failure facts that have a value; each check that had a result keeps it; its item, `<model>:gate:no-hang` and
    `<model>:gate` are not `pass`; the stalled camera gets the cleanup row and the notice `camera-not-restored`
    (ADR-0Z6Q item 14); the good camera has `live-at-close` `pass`."""
    scripts = [good(on_arm="exit"), good(on_arm="stall"), good(hang_at="close"), good(exit_at="close"), good()]
    factory = FakeSourceFactory(scripts)
    exits, stalls, hangs, ends, fine = labels(factory.device_infos())
    log = {label: factory.logs[camera_id] for label, camera_id in zip(labels(factory.device_infos()),
                                                                      factory.camera_ids)}
    results = {}

    def progress(message):
        name = (message.get("step") or {}).get("name")
        for check in message["checks"]:
            if check["result"] is not None and check["name"] not in results:
                results[check["name"]] = check["result"]
        if name == f"{exits}:time-gaps":  # the last check of its take rows
            log[exits].arm()
            time.sleep(3.0)
        elif name == f"{stalls}:time-gaps":
            log[stalls].arm()
            time.sleep(3.5)  # the product declares a stall after 2 s with no frame
        elif name == f"{hangs}:time-gaps":
            log[hangs].arm_hang()
    before = descendants()
    report = product(RUN).run("full", progress, devices=factory.device_infos(), source_factory=factory,
                              **paths(tmp_path))
    assert_valid(report)
    checks = by_name(report)
    expected = {exits: {"crashed"}, stalls: {"stalled"}, hangs: {"hung"}, ends: {"crashed"}}
    for index, (label, reasons) in enumerate(expected.items()):
        row = checks[f"{label}:live-at-close"]
        assert row["result"] == "fail" and row["reason"] in reasons and row["module"] == f"Fake camera {index}", row
        if row["reason"] == "crashed":
            assert "exit_code" in row["numbers"], row
        assert all(value is not None for key, value in row.get("numbers", {}).items() if key != "exit_code"), row
        assert checks[f"{label}:records:rows-complete"]["result"] == "pass"  # a written result does not change
        model = label.rsplit(".", 1)[0]
        assert checks[f"{model}:gate:no-hang"]["result"] == "fail", label
        assert checks[f"{model}:gate"]["result"] != "pass", label
        item = next(i for i in report["summary"] if i["name"] == f"Fake camera {index}")
        assert item["result"] != "pass", item
    assert checks[f"{exits}:live-at-close"]["numbers"]["exit_code"] == 3
    assert checks[f"{fine}:live-at-close"]["result"] == "pass"
    # P2-S2 of the review: a camera that hangs at the close is wedged (2.3): the cleanup row and the replug notice
    assert {"name": f"release:{hangs}", "result": "fail", "reason": "camera-wedged", "module": "Fake camera 2"}         in report["cleanup"]
    assert {"code": "camera-wedged", "values": {"camera": "Fake camera 2"}} in report["notices"]
    assert {"name": f"release:{stalls}", "result": "fail", "reason": "camera-not-restored",
            "module": "Fake camera 1"} in report["cleanup"]
    assert {"code": "camera-not-restored", "values": {"camera": "Fake camera 1"}} in report["notices"]
    # each result that a progress message showed is the result of the report
    assert all(checks[name]["result"] == result for name, result in results.items() if name in checks), results
    assert_no_new_process(before)


class _Status:
    def __init__(self, info):
        self.info = info

    def info_dict(self):
        return self.info


def test_late_codes_reads_the_hang_flag_and_the_exit_code():
    """P2-S1 of the review, ADR-0Z6Q item 15: after the close, the status flag `hung` gives `hung`; else a new product
    code of the status or of the last dict; else an end by -SIGTERM or -SIGKILL (the product ended the process)
    gives `hung`, and each other exit code that is not 0 gives `process-ended` (`crashed`). A code that the camera
    had already at the record start is not new and counts as no code."""
    from types import SimpleNamespace
    session_module = product("skellycam.core.certify.session")
    cases = {"a": ({}, 3, "process-ended"), "b": ({}, -11, "process-ended"), "c": ({}, -15, "hung"),
             "d": ({}, -9, "hung"), "e": ({}, 3221225477, "process-ended"), "f": ({}, 0, None),
             "g": ({"hung": True, "failure": {"code": "process-ended", "stage": "close"}}, 1, "hung"),
             "h": ({"failure": {"code": "stalled", "stage": "streaming"}}, 0, None),
             "i": ({"failure": {"code": "stream-error", "stage": "close"}}, 0, "stream-error")}
    session = object.__new__(session_module.Session)
    session.closing = [SimpleNamespace(label=label, camera_id=label) for label in cases]
    session.wedged, session.left = {}, {}
    session.code_at_take = {"h": "stalled"}
    group = SimpleNamespace(cameras=SimpleNamespace(orchestrator=SimpleNamespace(
        camera_statuses={label: _Status(info) for label, (info, _, _) in cases.items()})), camera_diagnostics={})
    workers = {label: SimpleNamespace(worker=SimpleNamespace(exitcode=code)) for label, (_, code, _) in cases.items()}
    late = session.late_codes(group, workers)
    assert {label: late[label][0] for label in late} == {
        label: want for label, (_, _, want) in cases.items() if want is not None}
    assert late["a"][1].get("reason") == "exit code 3" and "reason" not in late["c"][1]
