"""The tests of the second review of the certify code (specs/certify.md 8.3, 9.3, 9.5; C 1.6.0 2.4). Fake sources
only; no test opens a camera. A session-child test is used where a kill matters."""

import threading
import time

import psutil
import pytest

from skellycam.tests.capture.capture_session import capture_app
from skellycam.tests.capture.fake_source import FakeSourceFactory
from skellycam.tests.certify.report_rules import assert_valid
from skellycam.tests.certify.test_certify import CATALOG, RUN, by_name, good, labels, paths, product, run_with
from skellycam.tests.certify.test_certify_review import assert_no_new_process, descendants, record


def last_camera_check(label, base=(640, 480, 30.0)):
    catalog = product(CATALOG)
    names = catalog.camera_names(label, base, "quick", catalog.system_backend() != "media-foundation")
    return (names["clock"] or names["take"])[-1]


@pytest.mark.capture_timing
def test_review2_n1_the_live_change_never_reopens_a_wedged_camera(monkeypatch, tmp_path):
    """2.3: a camera whose process ended after `ready` is wedged; the live change of 4.3 does not apply to it, so it
    is opened one time only."""
    with capture_app(monkeypatch, [good(exit_at="frame:110"), good()], workers="process") as app:
        ended, fine = labels(app.factory.device_infos())
        report = run_with(app, tmp_path)
        opens = app.factory.logs[app.factory.camera_ids[0]].opens.value
    assert_valid(report)
    checks = by_name(report)
    assert opens == 1
    # the crash gives one `fail` row (B1): on a check of the ready step, or on the read-back when the settings step
    # finds it; no check of the settings step has a progress message, so no `not-run` row of it stays (3.6.1)
    fails = [c for c in report["checks"] if c["name"].startswith(ended + ":") and c["result"] == "fail"]
    assert [(c["reason"]) for c in fails] == ["crashed"], fails
    assert fails[0]["name"].split(":", 1)[1] in ("native-jpeg:format", "native-jpeg:not-reencoded",
                                                 "native-jpeg:source-equals-ring", "settings-stick:readback"), fails
    assert not [c for c in report["checks"] if c["name"].startswith(ended + ":settings-stick")
                and c["result"] == "not-run"]
    assert checks[f"{ended}:not-reached"]["reason"] == "prior-failure"
    assert {"code": "camera-wedged", "values": {"camera": "Fake camera 0"}} in report["notices"]
    assert checks[f"{fine}:settings-stick:readback"]["result"] == "pass"


def test_the_live_change_does_not_reopen_a_camera_that_died_after_the_scan(monkeypatch, tmp_path):
    """4.3, windows-capture.md 8.3 [Z7F3]: a camera is `ready` at the scan of the live change and dies before its apply
    (the race of N1, made certain: the apply waits until the camera is `dead`). The apply names no retry list, so the
    product does not open the dead camera again: it is opened one time only."""
    import asyncio

    with capture_app(monkeypatch, [good(), good()]) as app:
        dying = app.factory.camera_ids[0]
        apply = app.manager.create_or_update_camera_group

        async def dies_first(configs, *args, **kwargs):
            if any(config.exposure == -8 for config in configs.values()):  # the live change of 4.3
                app.factory.sources[dying].stop_now()
                deadline = time.monotonic() + 30
                while app.state(dying) != "dead":
                    assert time.monotonic() < deadline, "the camera did not die"
                    await asyncio.sleep(0.01)
            return await apply(configs, *args, **kwargs)
        monkeypatch.setattr(app.manager, "create_or_update_camera_group", dies_first)
        report = run_with(app, tmp_path)
        opens = app.factory.logs[dying].opens.value
    assert_valid(report)
    assert opens == 1


def test_review2_n2_a_camera_with_a_running_step_at_a_cancel_is_not_reopened(tmp_path):
    """8.3: a cancel 1.5 s after a control call hung (the product needs 5 s to declare it): the camera had a step
    running, so it is never opened again, and it gets `camera-not-restored`."""
    factory = FakeSourceFactory([good(hang_at="set_controls")])
    (label,) = labels(factory.device_infos())
    log = factory.logs[factory.camera_ids[0]]
    cancel = threading.Event()

    def progress(message):
        if (message.get("step") or {}).get("name") == f"{label}:settings-stick:readback":
            log.arm_hang()
            threading.Timer(1.5, cancel.set).start()
    before = descendants()
    report = product(RUN).run("quick", progress, cancel, devices=factory.device_infos(), source_factory=factory,
                              **paths(tmp_path))
    assert_valid(report)
    assert log.opens.value == 1
    assert [c["reason"] for c in report["cleanup"]] == ["camera-not-restored"]
    assert_no_new_process(before)


def test_review2_n3_a_cancel_during_the_close_does_not_kill_the_restore(tmp_path):
    """8.3, 9.3: a cancel that comes while the session closes its group (each close restores a camera) waits for the
    close: the source is closed one time, no camera is opened again, and no row of phase G comes."""
    # 2 s: within the join of 3 s of the product. A close that the product must end is a hang (live-at-close `hung`
    # and `camera-wedged`, ADR-0Z6Q item 15), which is not the case of this test.
    factory = FakeSourceFactory([good(close_delay_s=2.0)])
    (label,) = labels(factory.device_infos())
    log = factory.logs[factory.camera_ids[0]]
    cancel = threading.Event()

    def progress(message):
        if (message.get("step") or {}).get("name") == last_camera_check(label):
            threading.Timer(1.0, cancel.set).start()
    before = descendants()
    report = product(RUN).run("quick", progress, cancel, devices=factory.device_infos(), source_factory=factory,
                              **paths(tmp_path))
    assert_valid(report)
    assert (log.opens.value, log.closes.value) == (1, 1)
    assert report["cleanup"] == []
    assert "cancelled" in report["evidence"]["reasons"]
    assert_no_new_process(before)


def test_review2_n4_a_crash_of_the_session_child_during_the_open(tmp_path):
    """8.3: the session child dies while the camera opens: no check blames the camera, the camera is not opened
    again, it gets `camera-not-restored`, and no record row is written."""
    factory = FakeSourceFactory([good(open_delay_s=4.0)])
    (label,) = labels(factory.device_infos())
    started = time.time()

    def kill_session_child():
        for child in psutil.Process().children():
            if child.create_time() >= started - 0.5:
                child.kill()  # the main process of the session child only: a crash

    def progress(message):
        if (message.get("step") or {}).get("name", "").startswith(f"{label}:modes:granted"):
            threading.Timer(1.5, kill_session_child).start()
    before = descendants()
    report = product(RUN).run("quick", progress, devices=factory.device_infos(), source_factory=factory,
                              **paths(tmp_path))
    assert_valid(report)
    assert by_name(report)[f"{label}:opens"] == {**by_name(report)[f"{label}:opens"], "result": "not-run"}
    assert not [c for c in report["checks"] if c["result"] == "fail"]
    assert factory.logs[factory.camera_ids[0]].opens.value == 1
    assert [c["reason"] for c in report["cleanup"]] == ["camera-not-restored"]
    assert record(tmp_path) == []
    assert_no_new_process(before)


def test_review2_n5_an_abandon_that_comes_late_stores_no_row(monkeypatch, tmp_path):
    """C 1.6.0 2.4: an abandon set after the session ended (at the computed check `<model>:units`) still stops each
    store of a result: no record row."""
    abandon = threading.Event()

    def progress(message):
        if (message.get("step") or {}).get("name", "").endswith(":units"):
            abandon.set()
    with capture_app(monkeypatch, [good()]) as app:
        report = run_with(app, tmp_path, progress=progress, abandon=abandon)
    assert_valid(report)
    assert record(tmp_path) == []
    assert "cancelled" in report["evidence"]["reasons"]


def test_review2_n6_the_camera_processes_log_inside_the_work_folder(monkeypatch, tmp_path):
    """9.5: a certify run writes no log file outside its work folder: the camera processes log into `logs` of it."""
    monkeypatch.delenv("SKELLYLOGS_LOG_DIR", raising=False)
    factory = FakeSourceFactory([good()])
    seen = []

    def progress(message):
        if (message.get("step") or {}).get("name") == "group:take:finished":
            seen.extend(str(p) for p in (tmp_path / "recordings").glob("skellycam-certify-*/logs/**/*.log"))
    product(RUN).run("quick", progress, devices=factory.device_infos(), source_factory=factory, **paths(tmp_path))
    assert seen, "no camera process log in the work folder"


def test_review2_n9_a_lock_error_that_is_not_a_held_lock(tmp_path):
    """9.5: only a held lock gives `cameras-busy`; another error of the lock file gives its class name."""
    (tmp_path / product(RUN).LOCK_FILE).mkdir()  # a folder where the lock file must be: the open fails
    factory = FakeSourceFactory([good()])
    report = product(RUN).run("quick", devices=factory.device_infos(), source_factory=factory, **paths(tmp_path))
    assert_valid(report)
    reasons = {c["reason"] for c in report["checks"]}
    assert len(reasons) == 1 and reasons != {"cameras-busy"} and next(iter(reasons)).endswith("Error")


def test_review2_n9_a_failed_record_write_leaves_no_temporary_file(tmp_path):
    """2.5: a record write that fails removes its `.tmp` file."""
    catalog = product(CATALOG)
    target = tmp_path / "camera_checks.json"
    target.mkdir()
    with pytest.raises(OSError):
        catalog.write_record(target, [catalog.record_row("feed:0000", "media-foundation", "11 26H2", "lp64", "quick",
                                                         "pass", "2.0.0", "2026-11-21", None, {})])
    assert not (tmp_path / "camera_checks.json.tmp").exists()


def test_review2_n11_the_next_run_deletes_a_left_work_folder(monkeypatch, tmp_path):
    """9.5: a work folder that a dead caller left in the recording folder (marked) goes at the next run; a folder of
    the person stays."""
    left = tmp_path / "recordings" / "skellycam-certify-left"
    left.mkdir(parents=True)
    (left / ".skellycam-certify").write_text("", encoding="utf-8")
    mine = tmp_path / "recordings" / "skellycam-certify-mine"
    mine.mkdir()
    with capture_app(monkeypatch, [good()]) as app:
        run_with(app, tmp_path)
    assert not left.exists() and mine.exists()
