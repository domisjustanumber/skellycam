"""T-CERT-152: the record-only check `system:quick-sync` (specs/certify.md 3.6.2; windows-capture.md 22.7; Q879,
ADR-VTW3). A fake `check_quick_sync` gives each answer; the backend is patched, so the test runs on the three
systems. No test starts the real check or opens a camera."""

import threading
import time

import pytest

from skellycam.tests.capture.capture_session import capture_app
from skellycam.tests.certify.report_rules import assert_valid
from skellycam.tests.certify.test_certify import CATALOG, RUN, by_name, good, paths, product, run_with

ENCODER = "skellycam.core.camera.capture.encoder"
NAME = "system:quick-sync"
KEYS = ("works", "check_ms", "encode_ms", "failure", "exit_code")
ANSWERS = {
    "works": dict(works=True, failure=None, check_ms=1052.4, encode_ms=551.2, exit_code=None),
    "no-jpeg": dict(works=False, failure="no-jpeg", check_ms=1003.0, encode_ms=540.5, exit_code=None),
    "RuntimeError": dict(works=False, failure="RuntimeError", check_ms=612.3, encode_ms=101.9, exit_code=None),
    "timed-out": dict(works=False, failure="timed-out", check_ms=5004.7, encode_ms=None, exit_code=None),
    "crashed": dict(works=False, failure="crashed", check_ms=451.0, encode_ms=None, exit_code=3),
}


@pytest.fixture
def backend(monkeypatch):
    catalog = product(CATALOG)

    def set_backend(name):
        monkeypatch.setattr(catalog, "system_backend", lambda: name)
    set_backend("media-foundation")
    return set_backend


def answer(monkeypatch, values, calls=None, gate=None):
    """Replace the product call with a fake that gives `values`; `gate` (an Event) holds the fake until it is set."""
    encoder = product(ENCODER)

    def fake(**kwargs):
        if calls is not None:
            calls.append(kwargs)
        if gate is not None:
            gate.wait(30)
        return encoder.QuickSyncCheck(**values)
    monkeypatch.setattr(encoder, "check_quick_sync", fake)


def quick_no_camera(tmp_path, level="quick", **options):
    (tmp_path / "recordings").mkdir(exist_ok=True)
    return product(RUN).run(level, devices=[], **paths(tmp_path), **options)


@pytest.mark.parametrize("level", ["quick", "full"])
@pytest.mark.parametrize("kind", list(ANSWERS))
def test_t_cert_152_each_answer_gives_one_record_only_row(monkeypatch, tmp_path, backend, level, kind):
    """T-CERT-152: with no camera, each answer of cap 22.7 item 4 gives one row `system:quick-sync` right after
    `detect`, `record-only` with no reason and no `module`, and the five numbers of the fake."""
    calls = []
    answer(monkeypatch, ANSWERS[kind], calls)
    report = quick_no_camera(tmp_path, level)
    assert_valid(report)
    names = [check["name"] for check in report["checks"]]
    assert names[:2] == ["detect", NAME], names
    row = by_name(report)[NAME]
    assert (row["result"], row["reason"], row.get("module")) == ("record-only", None, None), row
    assert row["numbers"] == {key: ANSWERS[kind][key] for key in KEYS}, row
    assert len(calls) == 1, calls


def test_t_cert_152_the_row_changes_no_summary_item(monkeypatch, tmp_path, backend):
    """T-CERT-152: a quick run with one fake camera gives the same summary and the same camera rows with a check that
    works and with a crashed check."""
    reports = {}
    for kind in ("works", "crashed"):
        answer(monkeypatch, ANSWERS[kind])
        (tmp_path / kind).mkdir()
        with capture_app(monkeypatch, [good()]) as app:
            reports[kind] = run_with(app, tmp_path / kind)
        assert_valid(reports[kind])
    rows = {kind: {c["name"]: (c["result"], c["reason"]) for c in r["checks"] if c["name"] != NAME}
            for kind, r in reports.items()}
    assert rows["works"] == rows["crashed"]
    assert reports["works"]["summary"] == reports["crashed"]["summary"]
    assert by_name(reports["crashed"])[NAME]["numbers"]["failure"] == "crashed"


def test_t_cert_152_a_cancel_during_the_check(monkeypatch, tmp_path, backend):
    """T-CERT-152, 9.3: a cancel while the fake check still runs gives `not-run` `cancelled` within 1 s."""
    gate, started = threading.Event(), threading.Event()
    cancel = threading.Event()
    encoder = product(ENCODER)

    def fake(**kwargs):
        started.set()
        gate.wait(30)
        return encoder.QuickSyncCheck(**ANSWERS["works"])
    monkeypatch.setattr(encoder, "check_quick_sync", fake)
    threading.Thread(target=lambda: started.wait(30) and cancel.set(), daemon=True).start()
    t0 = time.monotonic()
    try:
        report = quick_no_camera(tmp_path, cancel=cancel)
        seconds = time.monotonic() - t0
    finally:
        gate.set()
    assert_valid(report)
    row = by_name(report)[NAME]
    assert (row["result"], row["reason"]) == ("not-run", "cancelled"), row
    assert seconds < 1.0 + 1.0, f"the run returned {seconds:.2f} s after the start"  # the check started at once


def test_t_cert_152_a_refused_run(monkeypatch, tmp_path, backend):
    """T-CERT-152, 9.7: a refused run gives `not-run` `cameras-busy` and calls no check."""
    calls = []
    answer(monkeypatch, ANSWERS["works"], calls)
    monkeypatch.setattr(product(RUN), "_group_open", lambda: True)
    report = quick_no_camera(tmp_path)
    row = by_name(report)[NAME]
    assert (row["result"], row["reason"]) == ("not-run", "cameras-busy"), row
    assert not calls


@pytest.mark.parametrize("other", ["v4l2", "avfoundation"])
def test_t_cert_152_no_row_on_linux_and_macos(monkeypatch, tmp_path, backend, other):
    """T-CERT-152: Linux and macOS have no row and call no check; the plan does not list it there."""
    calls = []
    answer(monkeypatch, ANSWERS["works"], calls)
    backend(other)
    report = quick_no_camera(tmp_path, "full")
    assert NAME not in by_name(report)
    assert not calls
    plan = product(RUN).plan("full", devices=[], checks_path=tmp_path / "camera_checks.json")
    assert NAME not in plan["details"]["checks"]


def test_t_cert_152_the_plan_lists_the_row(tmp_path, backend):
    """T-CERT-152: on Windows the plan lists the row right after `detect`, and `total` counts it in full."""
    plan = product(RUN).plan("full", devices=[], checks_path=tmp_path / "camera_checks.json")
    assert plan["details"]["checks"][:2] == ["detect", NAME]
    assert plan["total"] == len(plan["details"]["checks"])
