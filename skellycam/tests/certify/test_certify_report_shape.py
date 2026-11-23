"""The tests of the report shape of quick and full (specs/certify.md 3.5.2, 3.6; the build order of 3.6.7). Fake
sources only; no test opens a camera. Each test names the T-CERT test of section 17 that it covers, in whole or in
part; a part that a later step of 3.6.7 builds joins at that step.
"""

import json
import subprocess
import threading
import time

from skellycam.tests.capture.capture_session import capture_app
from skellycam.tests.capture.fake_source import FakeSourceFactory
from skellycam.tests.certify.report_rules import assert_valid
from skellycam.tests.certify.test_certify import CATALOG, RUN, by_name, good, labels, paths, product, run_with
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
    whose camera process ends there with `os._exit(3)`, one with a stream error in the take and one removed in the
    take. Each gets one `fail` row on the first check that has no result (`settings-stick:readback` `stalled` and
    `crashed`; `records:rows-complete` `stream-error` and `device-removed`), with the failure facts that have a
    value and `module` = its model; each later check of that camera is `not-run` (one `not-reached` row joins at
    step 4); `<model>:gate:no-hang` is `fail` for the stall and the crash and `pass` for the others. The take in
    place of "before the take": no progress message comes between the settings change and the take."""
    scripts = [good(on_arm="stall"), good(on_arm="exit"), good(on_arm="remove", removed_code="stream-error"),
               good(on_arm="remove")]
    factory = FakeSourceFactory(scripts)
    stall, crash, error, removed = labels(factory.device_infos())
    log = {label: factory.logs[camera_id] for label, camera_id in zip((stall, crash, error, removed),
                                                                      factory.camera_ids)}

    def arm_in_take():
        log[error].arm()
        log[removed].arm()

    def progress(message):
        name = (message.get("step") or {}).get("name")
        if name == f"{crash}:native-jpeg:source-equals-ring":  # the last check of the ready step of these two
            log[stall].arm()
            log[crash].arm()
            time.sleep(3.5)  # the product declares a stall after 2 s with no frame
        elif name == "group:take:finished":
            threading.Timer(2.0, arm_in_take).start()  # in the take of 3 s, after the record start
    before = descendants()
    report = product(RUN).run("full", progress, devices=factory.device_infos(), source_factory=factory,
                              **paths(tmp_path))
    assert_valid(report)
    checks = by_name(report)
    expected = {stall: ("settings-stick:readback", "stalled"), crash: ("settings-stick:readback", "crashed"),
                error: ("records:rows-complete", "stream-error"), removed: ("records:rows-complete", "device-removed")}
    for index, (label, (check, reason)) in enumerate(expected.items()):
        row = checks[f"{label}:{check}"]
        assert (row["result"], row["reason"], row["module"]) == ("fail", reason, f"Fake camera {index}"), row
        numbers = row.get("numbers", {})
        assert numbers.get("stage") == "streaming", row
        assert all(value is not None for key, value in numbers.items() if key != "exit_code"), row
        own = [c for c in report["checks"] if c["name"].startswith(label + ":")]
        assert [c["name"] for c in own if c["result"] == "fail"] == [row["name"]], own
        after = own[own.index(row) + 1:]
        assert after and all(c["result"] == "not-run" for c in after), after
    assert checks[f"{crash}:settings-stick:readback"]["numbers"]["exit_code"] == 3
    for label, result in ((stall, "fail"), (crash, "fail"), (error, "pass"), (removed, "pass")):
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
