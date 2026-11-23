"""The tests of the certify code of skellycam, Windows first (specs/certify.md section 17).

Each test uses fake sources (`skellycam/tests/capture/fake_source.py`); no test opens a camera. A run in a
test gives the detection result (`devices`) and runs the session in a thread of the test process with the
`CameraGroupManager` of `capture_app` (THREAD workers on a virtual clock, or PROCESS workers on the real clock
for a hang), or in a spawn session child with a picklable fake factory (`test_session_child_*`). The tests name
the T-CERT test of the spec that they cover, in whole or in part.
"""

import importlib
import json
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import psutil
import pytest

from skellycam.tests.capture.capture_session import capture_app
from skellycam.tests.capture.fake_source import FakeScript, FakeSourceFactory
from skellycam.tests.certify.report_rules import assert_valid, markdown_problems

RUN = "skellycam.core.certify.run"
CATALOG = "skellycam.core.certify.catalog"
OS_KEY, ABI = "11 26H2", "lp64"
MODE = ((640, 480, 30, 1, "MJPG"),)
# The diagnostics keys that a native source fills and the fake leaves null (unix-capture.md 4.6.2).
SOURCE_FACTS = {"delivered": "jpeg", "clock": "monotonic", "later_than_arrival": 0, "sample_minus_arrival_p95_ms": -4.0,
                "sequence_available": False, "long_intervals": 0, "control_path": "iam", "exposure_unit": "log2-s"}


def product(name):
    return importlib.import_module(name)


def good(**changes):
    """A fake that passes each check of quick: its image follows the exposure."""
    values = dict(modes=MODE, brightness=((-7, 120), (-8, 60)), diagnostics=dict(SOURCE_FACTS))
    values.update(changes)
    return FakeScript(**values)


def virtual_sleep(clock):
    def sleep(seconds):
        target = clock.now_ns() + round(seconds * 1e9)
        deadline = time.monotonic() + 60
        while clock.now_ns() < target:
            assert time.monotonic() < deadline, "the virtual clock did not move"
            time.sleep(0.002)
    return sleep


def same_model(devices, *indexes):
    """The fake devices with one product id for the cameras of `indexes` (one model, two units)."""
    return [d.model_copy(update=dict(product_id=0)) if d.index in indexes else d for d in devices]


def paths(tmp_path):
    return dict(recording_folder=tmp_path / "recordings", checks_path=tmp_path / "camera_checks.json",
                evidence_path=tmp_path / "camera_evidence.json", os_key=OS_KEY, abi=ABI)


def run_with(app, tmp_path, level="quick", devices=None, **options):
    (tmp_path / "recordings").mkdir(exist_ok=True)
    clock = app.factory.clock
    return product(RUN).run(level, manager=app.manager, devices=devices or app.factory.device_infos(),
                            sleep=virtual_sleep(clock) if clock is not None else time.sleep,
                            **{**paths(tmp_path), **options})


def by_name(report):
    return {check["name"]: check for check in report["checks"]}


def labels(devices):
    return [label for label, _ in product(CATALOG).camera_labels(devices, product(CATALOG).system_backend())]


def group_checks(label):
    return [f"{label}:opens", f"{label}:rate", f"{label}:modes:granted:640x480@30",
            f"{label}:settings-stick:readback", f"{label}:settings-stick:holds", f"{label}:settings-stick:image-effect",
            *(f"{label}:native-jpeg:{c}" for c in ("format", "not-reencoded", "valid", "size", "ring-equals-mkv",
                                                    "source-equals-ring")),
            *(f"{label}:records:{c}" for c in ("rows-complete", "blocks-decode", "gaps-explained"))]


def write_evidence(path, device, backend):
    path.write_text(json.dumps({"schema": 1, "systems": [], "cameras": [
        {"device": device, "model": "Fake", "backend": backend, "os": "Windows", "os_key": OS_KEY, "abi": ABI,
         "state": "verified", "source": "maintainer", "reports": []}]}), encoding="utf-8")


def write_record(path, device, backend, level="quick"):
    path.write_text(json.dumps({"format": 1, "rows": [
        {"device": device, "backend": backend, "os_key": OS_KEY, "abi": ABI, "level": level, "item": "pass",
         "skellycam": "2.0.0", "date": "2026-11-21"}]}), encoding="utf-8")


# ---------------------------------------------------------------------------
# Pure parts: names, the summary item rule, the gate, the record
# ---------------------------------------------------------------------------

def test_t_cert_02_a_wrong_level_raises():
    """T-CERT-02, C 2.2: `ValueError` for a level that is not `quick` or `full`."""
    import skellycam
    with pytest.raises(ValueError):
        skellycam.certify("slow")
    with pytest.raises(ValueError):
        skellycam.certify_plan("")


def test_t_cert_05_and_70_camera_names():
    """T-CERT-05, T-CERT-70, 9.4: the name cleaning, and no character of rules 17 and 20 in a cleaned name."""
    clean = product(CATALOG).clean_name
    terms = ("dom-pc", "alex")
    assert clean("Alex's iPhone Camera", "05ac:1234", ()) == "iPhone Camera"
    assert clean("Kamera’s Webcam", "046d:085c", ()) == "Webcam"
    assert clean("DOM-PC Webcam", "046d:085c", terms) == "Camera 046d:085c"
    assert clean("DOM-PC Webcam", None, terms) == "Camera"
    assert clean("HD Webcam (SN 12AB34CD56)", "1234:5678", ()) == "HD Webcam"
    assert clean("USB Video Device", "1532:0e05", ()) == "USB Video Device"
    assert clean("Intel(R) RealSense(TM)  Camera", None, ()) == "Intel RealSense Camera"
    for name in ("Cam <x>", "See https://x", "www.cam.example", "Cam 192.0.2.7", "a](b", "a]:b"):
        cleaned = clean(name, None, ())
        assert cleaned and not markdown_problems(cleaned), cleaned
    assert len(clean("x" * 200, None, ())) <= 64


def test_t_cert_31_the_longest_names():
    """T-CERT-31, 3.1: the longest names match the pattern of C 3.4; the longest has 75 characters."""
    catalog = product(CATALOG)
    label = catalog.label("media-foundation", None, None, 9)
    assert label == "cam.media-foundation.nousb-nousb.9"
    name = f"{label}:auto-exposure:holds-rate:{catalog.mode_name(1920, 1080, 29.97)}"
    assert len(name) == 75 and catalog.NAME.match(name)
    assert catalog.mode_name(1280, 720, 30.0) == "1280x720@30"


def row(name, result="pass", reason=None):
    return {"name": name, "result": result, "reason": reason}


def unit(label, overrides=(), groups=None):
    names = groups or group_checks(label)
    rows = {name: row(name) for name in names}
    for name, result, reason in overrides:
        rows[f"{label}:{name}"] = row(f"{label}:{name}", result, reason)
    return rows


def test_t_cert_44_the_summary_item_rule():
    """T-CERT-44, 3.4: the first rule of four that applies; time-gaps in place of sequence; no `record-only`."""
    item = product(CATALOG).item_result
    a, b = "cam.x.0001-0002.0", "cam.x.0001-0002.1"
    assert item([unit(a)]) == "pass"
    assert item([unit(a), unit(b)]) == "pass"
    busy = [("opens", "not-run", "camera-in-use")]
    assert item([unit(a, busy)]) == "skipped"
    assert item([unit(a, busy), unit(b, busy)]) == "skipped"
    assert item([unit(a, busy), unit(b)]) == "partial"
    assert item([unit(a, [("rate", "fail", "rate-low")])]) == "fail"
    assert item([unit(a, [("records:rows-complete", "fail", "missing-rows")])]) == "fail"
    assert item([unit(a, [("native-jpeg:valid", "fail", "jpeg-damaged")])]) == "partial"
    assert item([unit(a, [("settings-stick:image-effect", "not-run", "too-dark")])]) == "partial"
    assert item([unit(a, busy), unit(b, [("opens", "fail", "hung")])]) == "fail"
    unix = group_checks(a) + [f"{a}:clock:base", f"{a}:clock:before-arrival", f"{a}:clock:near-arrival",
                              f"{a}:sequence", f"{a}:time-gaps"]
    no_sequence = unit(a, [("sequence", "not-run", "no-sequence")], groups=unix)
    assert item([no_sequence], unix=True) == "pass"
    gaps = unit(a, [("sequence", "not-run", "no-sequence"), ("time-gaps", "fail", "frame-gaps")], groups=unix)
    assert item([gaps], unix=True) == "partial"
    with_sequence = unit(a, [("time-gaps", "not-run", "has-sequence")], groups=unix)
    assert item([with_sequence], unix=True) == "pass"
    extra = unit(a)
    extra[f"{a}:control:focus"] = row(f"{a}:control:focus", "fail", "readback-differs")
    assert item([extra]) == "pass"


def gate_unit(label, overrides=()):
    names = group_checks(label) + [f"{label}:clock:base", f"{label}:clock:before-arrival",
                                   f"{label}:clock:near-arrival", f"{label}:sequence", f"{label}:time-gaps",
                                   f"{label}:cycles"]
    rows = unit(label, groups=names)
    rows[f"{label}:sequence"] = row(f"{label}:sequence", "not-run", "no-sequence")
    for name, result, reason in overrides:
        rows[f"{label}:{name}"] = row(f"{label}:{name}", result, reason)
    return rows


def test_t_cert_65_and_68_the_gate_roll_ups():
    """T-CERT-65, T-CERT-68, 3.3, 11.3: each roll-up requires exactly the checks of 11.3; `pass` only when each
    is `pass`, else `fail` `gate-check-failed` or `not-run` `gate-check-not-run`; `no-hang` is an ordinary check;
    with no sequence number, `time-gaps` judges the gaps."""
    gate = product(CATALOG).gate_rows
    model, label = "cam.x.0001-0002", "cam.x.0001-0002.0"
    rows = {r["name"]: r for r in gate(model, [gate_unit(label)], "Fake")}
    assert [name.removeprefix(model) for name in rows] == [
        ":gate:opens", ":gate:mode", ":gate:rate", ":gate:native-jpeg", ":gate:timestamps", ":gate:sequence",
        ":gate:records", ":gate:no-hang", ":gate"]
    assert all(r["result"] == "pass" and r["module"] == "Fake" for r in rows.values())
    rows = {r["name"]: r for r in gate(model, [gate_unit(label, [("time-gaps", "fail", "frame-gaps")])], "Fake")}
    assert rows[f"{model}:gate:sequence"]["reason"] == "gate-check-failed"
    assert rows[f"{model}:gate"]["result"] == "fail" and rows[f"{model}:gate"]["reason"] == "gate-check-failed"
    seq = gate_unit(label, [("sequence", "fail", "sequence-unreliable"), ("time-gaps", "not-run", "has-sequence")])
    rows = {r["name"]: r for r in gate(model, [seq], "Fake")}
    assert rows[f"{model}:gate:sequence"]["result"] == "fail"
    rows = {r["name"]: r for r in gate(model, [gate_unit(label, [("clock:base", "not-run", "not-built")])], "Fake")}
    assert rows[f"{model}:gate:timestamps"] == {**rows[f"{model}:gate:timestamps"], "result": "not-run",
                                                "reason": "gate-check-not-run"}
    rows = {r["name"]: r for r in gate(model, [gate_unit(label, [("cycles", "fail", "hung")])], "Fake")}
    assert rows[f"{model}:gate:no-hang"]["result"] == "fail" and rows[f"{model}:gate:no-hang"]["reason"] == "hung"
    assert rows[f"{model}:gate"]["result"] == "fail"
    rows = {r["name"]: r for r in gate(model, [gate_unit(label, [("rate", "fail", "crashed")])], "Fake")}
    assert rows[f"{model}:gate:no-hang"]["reason"] == "crashed"


def test_the_timestamps_gate_of_a_source_that_cannot_tell_its_clock():
    """11.3 (Q585 of the user, 2026-11-23) [Z7F3]: with `clock:base` `not-run` `clock-unknown`, `gate:timestamps`
    requires only `clock:before-arrival` and `clock:near-arrival`; a declared clock keeps all three."""
    gate = product(CATALOG).gate_rows
    model, label = "cam.x.0001-0002", "cam.x.0001-0002.0"

    def timestamps(*overrides):
        rows = {r["name"]: r for r in gate(model, [gate_unit(label, [("clock:base", "not-run", "clock-unknown"),
                                                                      *overrides])], "Fake")}
        return rows[f"{model}:gate:timestamps"]["result"]
    assert timestamps() == "pass"  # (a)
    assert timestamps(("clock:near-arrival", "fail", "sample-too-early")) == "fail"  # (b)
    assert timestamps(("clock:before-arrival", "not-run", "not-built")) != "pass"  # (c)
    rows = {r["name"]: r for r in gate(model, [gate_unit(label, [("clock:base", "fail", "clock-base-differs")])],
                                       "Fake")}
    assert rows[f"{model}:gate:timestamps"]["result"] == "fail"  # (d) a declared `realtime` clock


def test_t_cert_41_the_record_rule_and_a_damaged_file(tmp_path):
    """T-CERT-41, 2.5: one row for each model whose item is `pass`, `fail`, or `partial` with a judged `opens`; no
    row for `skipped` or for `partial` with no judged `opens`; a damaged file counts as no row, and the writer
    writes a new file; a later row of a key replaces the earlier one; no serial, path or `camera_id`."""
    catalog = product(CATALOG)
    checks = product("skellycam.core.camera.capture.camera_checks")
    path = tmp_path / "camera_checks.json"
    path.write_text("{not json", encoding="utf-8")
    models = [
        dict(device="feed:0001", item="pass", opens=["pass"]),
        dict(device="feed:0002", item="partial", opens=["pass"]),
        dict(device="feed:0003", item="fail", opens=["fail"]),
        dict(device="feed:0004", item="skipped", opens=["not-run"]),
        dict(device="feed:0005", item="partial", opens=["not-run"]),
    ]
    rows = [catalog.record_row(m["device"], "media-foundation", OS_KEY, ABI, "quick", m["item"], "2.0.0", "2026-11-21",
                               None, {}) for m in models if catalog.writes_row(m["item"], m["opens"])]
    assert [r["device"] for r in rows] == ["feed:0001", "feed:0002", "feed:0003"]
    catalog.write_record(path, rows)
    catalog.write_record(path, [catalog.record_row("feed:0001", "media-foundation", OS_KEY, ABI, "quick", "fail",
                                                   "2.0.0", "2026-11-22", None, {})])
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["format"] == 1 and len(data["rows"]) == 3
    assert [r["item"] for r in data["rows"] if r["device"] == "feed:0001"] == ["fail"]
    assert checks.checked(checks.read_rows(path), "feed:0002", "media-foundation", OS_KEY, ABI)
    assert not checks.checked(checks.read_rows(path), "feed:0002", "media-foundation", "11 27H2", ABI)
    text = path.read_text(encoding="utf-8")
    assert "camera_id" not in text and "serial" not in text and "\\" not in text


def test_t_cert_30_each_code_is_in_the_reason_codes_file():
    """T-CERT-30, C 5.4: each reason code and each notice code that the code can give is in
    `skellycam/REASON_CODES.md` with one sentence; each notice code has its text for the person."""
    catalog = product(CATALOG)
    text = (Path(product("skellycam").__file__).parent / "REASON_CODES.md").read_text(encoding="utf-8")
    missing = [code for code in catalog.REASON_CODES if f"| `{code}` |" not in text]
    assert not missing, missing
    for code in catalog.NOTICE_CODES:
        line = next(line for line in text.splitlines() if line.startswith(f"| `{code}` |"))
        assert "Camera <name>" in line, line


# ---------------------------------------------------------------------------
# The plan
# ---------------------------------------------------------------------------

def test_t_cert_01_the_plan(tmp_path):
    """T-CERT-01, 2.5, 4.7, 8.4, 9.1: the fields of C 2.6; `risks` only for `full`; `total` is the count of the
    planned checks; the estimate; `evidence` and `checked`; `details.unchecked` holds neither the checked nor
    the reviewed model; with each model reviewed, quick has `total` 0; no camera is opened."""
    run = product(RUN)
    catalog = product(CATALOG)
    backend = catalog.system_backend()
    scripts = [good(), good(), good(), good(), good(name="Virtual camera")]
    factory = FakeSourceFactory(scripts)
    devices = factory.device_infos()
    write_evidence(tmp_path / "camera_evidence.json", "feed:0001", backend)
    write_record(tmp_path / "camera_checks.json", "feed:0002", backend)
    options = {key: value for key, value in paths(tmp_path).items() if key != "recording_folder"}
    for count in (0, 1, 4):
        quick = run.plan("quick", devices=devices[:count] + devices[4:], **options)
        full = run.plan("full", devices=devices[:count] + devices[4:], **options)
        for plan in (quick, full):
            assert {"package", "kind", "seconds_estimate", "total", "risks", "downloads", "system_changes",
                    "questions", "details"} <= set(plan)
            assert plan["package"] == "skellycam" and plan["downloads"] == [] and plan["system_changes"] == []
            assert plan["details"]["virtual"] == 1
            json.dumps(plan)
        assert quick["risks"] == [] and full["risks"][0].startswith("The full run opens each camera many times")
        assert [q["id"] for q in quick["questions"]] == ["lit-as-usual", "all-cameras"]
        assert [q["id"] for q in full["questions"]] == ["lit-as-usual", "all-cameras", "camera-ok-after"]
        cameras = quick["details"]["cameras"]
        assert len(cameras) == count
        to_check = [c for c in cameras if c["evidence"] != "verified"]
        # 3.6.1: `total` counts `session:exit` when a session child runs, and no check with no code
        assert quick["total"] == (len(quick["details"]["checks"]) + 1 if to_check else 0)
        assert quick["seconds_estimate"] == (min(30, -(-(20 * 4 + len(to_check)) // 4) + 10) if to_check else 0)
        assert full["total"] == len(full["details"]["checks"]) + (1 if count else 0)
        assert not [n for n in quick["details"]["checks"] + full["details"]["checks"]
                    if n.startswith(("self:", "group:open", "group:take-30", "system:")) or n.endswith(":cycles")]
        if count == 4:
            by_device = {c["device"]: c for c in cameras}
            assert by_device["feed:0001"]["evidence"] == "verified" and by_device["feed:0002"]["checked"] is True
            assert by_device["feed:0000"]["checked"] is False and by_device["feed:0000"]["evidence"] == "unknown"
            assert [u["device"] for u in quick["details"]["unchecked"]] == ["feed:0000", "feed:0003"]
            assert not any(n.startswith(cameras[1]["label"]) for n in quick["details"]["checks"])
    only_reviewed = run.plan("quick", devices=devices[1:2], **options)
    assert only_reviewed["total"] == 0 and only_reviewed["seconds_estimate"] == 0
    assert sum(1 for f in factory.logs.values() if f.opens.value) == 0


# ---------------------------------------------------------------------------
# Runs with fake cameras
# ---------------------------------------------------------------------------

def test_t_cert_03_07_17_26_a_quick_run_with_good_fakes(monkeypatch, tmp_path):
    """T-CERT-03, T-CERT-07, T-CERT-17, T-CERT-26: three good fakes, two of one model. The report obeys the
    rules of the contract (schema `skellycertify.report/1.7.0`, 3.6.1); each check of the five groups passes; one summary item for each model, `pass`, in the
    detection order, with `<model>:units`; no row would be in the table of the checks that did not pass, except
    the checks that are not built; the work folder is gone; no cleanup row and no notice; one record row for each
    model; the progress names each check before its result; at most 10 messages each second."""
    messages = []
    with capture_app(monkeypatch, [good(), good(), good()]) as app:
        devices = same_model(app.factory.device_infos(), 0, 1)
        report = run_with(app, tmp_path, devices=devices,
                          progress=lambda m: messages.append((time.monotonic(), json.loads(json.dumps(m)))))
    assert_valid(report)
    assert report["schema"] == "skellycertify.report/1.7.0"
    checks = by_name(report)
    a0, a1, b0 = labels(devices)
    assert a0.endswith(".0") and a1.endswith(".1") and b0.endswith(".0")
    for label in (a0, a1, b0):
        for name in group_checks(label):
            assert checks[name]["result"] == "pass", checks[name]
    for name in ("group:take:finished", "group:take:csv-rows", "group:take:no-missing", "group:take:frame-count",
                 "group:take:rate"):
        assert checks[name]["result"] == "pass", checks[name]
    assert checks["detect"]["result"] == "pass" and checks["detect"]["numbers"]["cameras"] == 3
    model_a = a0.rsplit(".", 1)[0]
    assert checks[f"{model_a}:units"]["result"] == "record-only" and checks[f"{model_a}:units"]["numbers"]["units"] == 2
    assert [(i["device"], i["result"]) for i in report["summary"]] == [("feed:0000", "pass"), ("feed:0002", "pass")]
    assert all("gate" not in i for i in report["summary"])
    # `no-sequence`: Linux and macOS quick have `sequence`; the fake gives no sequence number (10.2)
    assert {c["reason"] for c in report["checks"] if c["result"] in ("fail", "not-run")} <= {"not-built", "no-sequence"}
    assert not report.get("cleanup") and not report.get("notices")
    assert report["kind"] == "quick" and "no-commit" in report["evidence"]["reasons"]
    assert not list((tmp_path / "recordings").iterdir()), "the work folder stays"
    record = json.loads((tmp_path / "camera_checks.json").read_text(encoding="utf-8"))["rows"]
    assert sorted(r["device"] for r in record) == ["feed:0000", "feed:0002"]
    assert all(r["level"] == "quick" and r["os_key"] == OS_KEY and r["abi"] == ABI for r in record)
    plan = product(RUN).plan("quick", devices=devices, **{k: v for k, v in paths(tmp_path).items()
                                                         if k != "recording_folder"})
    assert plan["details"]["unchecked"] == []
    assert plan["total"] == len(report["checks"]) + 1  # `session:exit` (3.6.1): no row with a clean exit
    # progress (C 2.3, 9.6)
    states = [m["state"] for _, m in messages]
    assert states[0] == "starting" and states[-1] == "done"
    for name, check in checks.items():
        if check["result"] == "not-run":  # a check that does not run does not start
            continue
        started = next(i for i, (_, m) in enumerate(messages) if m["step"] == {"section": None, "name": name})
        ended = next(i for i, (_, m) in enumerate(messages)
                     if any(c["name"] == name and c["result"] is not None for c in m["checks"]))
        assert started < ended, name
        assert all(c["result"] is None for c in messages[started][1]["checks"] if c["name"] == name)
    assert all(c["section"] is None for _, m in messages for c in m["checks"])
    gaps = [b - a for (a, _), (b, _) in zip(messages, messages[1:])]
    assert min(gaps) >= 0.095, min(gaps)
    last = messages[-1][1]
    assert last["done"] == plan["total"] and all("reason" in c for c in last["checks"])


def test_t_cert_08_and_17_a_slow_camera_and_a_progress_that_raises(monkeypatch, tmp_path):
    """T-CERT-08, T-CERT-17: the generic-camera pattern (25 fps on a 30 fps mode) gives `rate` `fail` `rate-low`
    and the item `fail`; the camera that passed still records. A progress callable that raises is called once,
    and the run completes."""
    calls = []

    def progress(message):
        calls.append(message)
        raise RuntimeError("the app failed")

    with capture_app(monkeypatch, [good(rate=25.0), good()]) as app:
        devices = app.factory.device_infos()
        report = run_with(app, tmp_path, progress=progress)
    assert_valid(report)
    assert len(calls) == 1
    checks = by_name(report)
    slow, fine = labels(devices)
    assert checks[f"{slow}:rate"]["result"] == "fail" and checks[f"{slow}:rate"]["reason"] == "rate-low"
    assert checks[f"{slow}:opens"]["result"] == "pass"
    assert f"{slow}:records:rows-complete" not in checks  # 3.6.1: in the one `not-reached` row
    assert checks[f"{slow}:not-reached"] == {**checks[f"{slow}:not-reached"], "result": "not-run",
                                             "reason": "prior-check-failed"}
    assert [i["result"] for i in report["summary"]] == ["fail", "pass"], [
        c for c in report["checks"] if c["name"].startswith(fine) and c["result"] != "pass"]
    assert checks[f"{fine}:records:rows-complete"]["result"] == "pass"
    assert checks["group:take:finished"]["result"] == "pass"


class InUseFactory(FakeSourceFactory):
    """The first camera is held by another program: its open fails with the product code `camera-in-use`."""

    def __call__(self, config):
        source = super().__call__(config)
        if config.camera_id == self.camera_ids[0]:
            failure = source.types.CaptureFailure

            def open_in_use(request):
                source.log.opens.value += 1
                raise failure("open", "in use by another program", code="camera-in-use")
            source.open = open_in_use
        return source


def test_t_cert_10_a_camera_in_use(monkeypatch, tmp_path):
    """T-CERT-10, 3.4, 9.7: `opens` `not-run` `camera-in-use`, each other check of that camera `not-run`
    `camera-in-use` (its own row when a progress message named it, else in the one `not-reached` row, 3.6.1), the
    item `skipped` `busy`, the run is not refused, no retry, no record row of that model."""
    with capture_app(monkeypatch, [good(), good()]) as app:
        factory = InUseFactory(app.factory.scripts, clock=app.factory.clock)
        app.manager.source_factory = factory
        app.factory = factory
        devices = factory.device_infos()
        report = run_with(app, tmp_path)
    assert_valid(report)
    checks = by_name(report)
    busy, fine = labels(devices)
    for name in group_checks(busy):
        check = checks.get(name) or checks[f"{busy}:not-reached"]
        assert check["result"] == "not-run" and check["reason"] == "camera-in-use", check
    assert checks[f"{busy}:opens"]["reason"] == "camera-in-use"
    assert report["summary"][0] == {"group": "camera", "name": "Fake camera 0", "device": "feed:0000",
                                    "result": "skipped", "reason": "busy"}
    assert report["summary"][1]["result"] == "pass"
    assert "cameras-busy" not in report["evidence"]["reasons"]
    assert factory.logs[factory.camera_ids[0]].opens.value == 1
    record = json.loads((tmp_path / "camera_checks.json").read_text(encoding="utf-8"))["rows"]
    assert [r["device"] for r in record] == ["feed:0001"]


def test_t_cert_13_settings_stick(monkeypatch, tmp_path):
    """T-CERT-13, 4.3: a read-back that differs after the change, an image that does not change, a mean of 240,
    and a camera with no manual exposure; each item `partial`; no `fail` for the camera with no manual exposure."""
    scripts = [good(live_set_faults=("readback:-5",)), good(brightness=()), good(brightness=((-7, 240), (-8, 235))),
               good(controls=(("exposure", False, False, 0), ("gain", True, False, 0), ("focus", True, True, 30)))]
    with capture_app(monkeypatch, scripts) as app:
        devices = app.factory.device_infos()
        report = run_with(app, tmp_path)
    assert_valid(report)
    checks = by_name(report)
    differs, flat, bright, none = labels(devices)

    def result(label, name):
        check = checks[f"{label}:settings-stick:{name}"]
        return check["result"], check["reason"]
    assert result(differs, "readback") == ("fail", "readback-differs")
    assert result(differs, "holds") == ("not-run", "prior-check-failed")
    assert result(flat, "image-effect") == ("fail", "no-image-effect")
    assert result(bright, "image-effect") == ("not-run", "too-bright")
    for name in ("readback", "holds", "image-effect"):
        assert result(none, name) == ("not-run", "no-manual-exposure")
    assert [i["result"] for i in report["summary"]] == ["partial"] * 4


def test_t_cert_14_native_jpeg(monkeypatch, tmp_path):
    """T-CERT-14, 4.4: a fake with cut JPEGs gives `native-jpeg:valid` `fail` `jpeg-damaged`, and its other JPEG
    checks keep their own results; a fake with no DHT passes each JPEG check with `dht_inserted` > 0."""
    scripts = [good(cut_off_frames=tuple(range(0, 3000, 9))), good(no_dht=True)]
    with capture_app(monkeypatch, scripts) as app:
        devices = app.factory.device_infos()
        report = run_with(app, tmp_path)
    assert_valid(report)
    checks = by_name(report)
    cut, no_dht = labels(devices)
    assert checks[f"{cut}:native-jpeg:valid"]["result"] == "fail"
    assert checks[f"{cut}:native-jpeg:valid"]["reason"] == "jpeg-damaged"
    assert checks[f"{cut}:native-jpeg:format"]["result"] == "pass"
    assert checks[f"{cut}:native-jpeg:not-reencoded"]["result"] == "pass"
    for name in ("format", "not-reencoded", "valid", "size", "ring-equals-mkv", "source-equals-ring"):
        assert checks[f"{no_dht}:native-jpeg:{name}"]["result"] == "pass", checks[f"{no_dht}:native-jpeg:{name}"]
    assert checks[f"{no_dht}:native-jpeg:format"]["numbers"]["dht_inserted"] > 0


def test_t_cert_16_a_cancel_during_the_take(monkeypatch, tmp_path):
    """T-CERT-16, 8.3, 9.3: the cancel comes when the take starts. The checks that ended keep their results; the
    running and later checks are `not-run` `cancelled`; a thread session closes its group itself (the close
    restores each camera), so phase G takes the result of that close and opens no camera again (ADR-X8XE); no
    cleanup row for a healthy camera; `cancelled` is in `evidence.reasons`; the work folder is gone; the record gets
    rows by the rule of 2.5."""
    cancel = threading.Event()

    def progress(message):
        if (message.get("step") or {}).get("name") == "group:take:finished":
            cancel.set()

    with capture_app(monkeypatch, [good(), good()]) as app:
        devices = app.factory.device_infos()
        report = run_with(app, tmp_path, progress=progress, cancel=cancel)
        opens = [app.factory.logs[camera_id].opens.value for camera_id in app.factory.camera_ids]
    assert_valid(report)
    checks = by_name(report)
    first, _ = labels(devices)
    assert checks[f"{first}:opens"]["result"] == "pass"
    assert checks["group:take:finished"]["result"] == "not-run" and checks["group:take:finished"]["reason"] == "cancelled"
    assert checks[f"{first}:not-reached"]["reason"] == "cancelled"  # 3.6.1: the checks after the take
    assert "cancelled" in report["evidence"]["reasons"]
    assert opens == [1, 1], opens
    assert not report.get("cleanup")
    assert not list((tmp_path / "recordings").iterdir())
    record = json.loads((tmp_path / "camera_checks.json").read_text(encoding="utf-8"))["rows"]
    assert len(record) == 2


def test_t_cert_24_over_budget(monkeypatch, tmp_path):
    """T-CERT-24, 4.1: with a budget that is used up before the camera steps, each check of the cameras is
    `not-run` `over-budget` (one `not-reached` row, 3.6.1), never `fail`. (A thread session cannot be killed; the
    kill is the same as a cancel.)"""
    with capture_app(monkeypatch, [good()]) as app:
        devices = app.factory.device_infos()
        report = run_with(app, tmp_path, budget_s=0.0)
    assert_valid(report)
    checks = by_name(report)
    (label,) = labels(devices)
    assert f"{label}:opens" not in checks and checks[f"{label}:not-reached"]["reason"] == "over-budget"
    assert checks["group:take:finished"]["reason"] == "over-budget"
    assert not [c for c in report["checks"] if c["result"] == "fail"]


def test_t_cert_43_an_open_camera_group_refuses_the_run(monkeypatch, tmp_path):
    """T-CERT-43, 9.7: an open camera group in the calling process: each check `not-run` `cameras-busy`,
    `cameras-busy` in `evidence.reasons`, no source created."""
    manager_module = product("skellycam.core.camera_group.camera_group_manager")
    monkeypatch.setattr(manager_module, "_CAMERA_GROUP_MANAGER", SimpleNamespace(camera_groups={"group": object()}))
    factory = FakeSourceFactory([good()])
    report = product(RUN).run("quick", devices=factory.device_infos(), source_factory=factory, **paths(tmp_path))
    assert_valid(report)
    assert report["checks"] and all(c["result"] == "not-run" and c["reason"] == "cameras-busy" for c in report["checks"])
    assert "cameras-busy" in report["evidence"]["reasons"]
    assert not factory.sources


def test_t_cert_06_no_camera(tmp_path):
    """T-CERT-06, 2.5: `detect` `pass` with `cameras` 0; no `fail`; no `camera` summary item; `no-camera` in
    `evidence.reasons`; no record row."""
    factory = FakeSourceFactory([good(name="Virtual camera")])
    report = product(RUN).run("quick", devices=factory.device_infos(), source_factory=factory, **paths(tmp_path))
    assert_valid(report)
    checks = by_name(report)
    assert checks["detect"]["result"] == "pass" and checks["detect"]["numbers"]["cameras"] == 0
    assert checks["detect"]["numbers"]["virtual"] == 1
    assert not [c for c in report["checks"] if c["result"] == "fail"]
    assert not [i for i in report.get("summary", []) if i["group"] == "camera"]
    assert "no-camera" in report["evidence"]["reasons"]
    assert not (tmp_path / "camera_checks.json").exists()


def test_t_cert_42_the_pop_up_flow(monkeypatch, tmp_path):
    """T-CERT-42, 2.5: the record holds one model; `details.unchecked` names the first camera of the other model;
    a run with that label checks only that camera, with no `partial-run`; then nothing is unchecked."""
    options = {k: v for k, v in paths(tmp_path).items() if k != "recording_folder"}
    with capture_app(monkeypatch, [good(), good()]) as app:
        devices = app.factory.device_infos()
        write_record(tmp_path / "camera_checks.json", "feed:0001", product(CATALOG).system_backend())
        plan = product(RUN).plan("quick", devices=devices, **options)
        assert [u["device"] for u in plan["details"]["unchecked"]] == ["feed:0000"]
        report = run_with(app, tmp_path, cameras=[plan["details"]["unchecked"][0]["label"]])
    assert_valid(report)
    first, second = labels(devices)
    assert by_name(report)[f"{first}:opens"]["result"] == "pass"
    assert not any(c["name"].startswith(second) for c in report["checks"])
    assert "partial-run" not in report["evidence"]["reasons"]
    assert product(RUN).plan("quick", devices=devices, **options)["details"]["unchecked"] == []


def test_t_cert_47_a_full_run_and_the_local_pass(monkeypatch, tmp_path):
    """T-CERT-47, T-CERT-44, 11.3: a full run with a fake whose gate checks pass gives `<model>:gate` `pass`, the
    summary item `gate`, and a `full` row that is a local pass; a fake whose sample time comes after its arrival
    fails `clock:before-arrival`, so its gate fails and its row is no local pass. The checks that are not built
    are not in `checks`: `details.not_built` names them (3.6.1)."""
    late = good(diagnostics={**SOURCE_FACTS, "later_than_arrival": 3})
    with capture_app(monkeypatch, [good(), late]) as app:
        devices = app.factory.device_infos()
        report = run_with(app, tmp_path, level="full")
    assert_valid(report)
    checks = by_name(report)
    fine, bad = labels(devices)
    model_fine, model_bad = fine.rsplit(".", 1)[0], bad.rsplit(".", 1)[0]
    assert checks[f"{model_fine}:gate"]["result"] == "pass", [c for c in report["checks"] if
                                                             c["name"].startswith(model_fine + ":gate")]
    assert checks[f"{bad}:clock:before-arrival"]["reason"] == "sample-after-arrival"
    assert checks[f"{model_bad}:gate"]["result"] == "fail"
    assert [i["gate"] for i in report["summary"]] == [f"{model_fine}:gate", f"{model_bad}:gate"]
    assert f"{fine}:cycles" not in checks and "cycles" in report["details"]["not_built"]["camera"]
    checks_module = product("skellycam.core.camera.capture.camera_checks")
    rows = checks_module.read_rows(tmp_path / "camera_checks.json")
    backend = product(CATALOG).system_backend()
    assert checks_module.local_pass(rows, "feed:0000", backend, OS_KEY, ABI)
    assert not checks_module.local_pass(rows, "feed:0001", backend, OS_KEY, ABI)
    assert next(r for r in rows if r["device"] == "feed:0000")["controls"] == {"exposure": {"iam": "works"}}


def test_clock_base_of_a_source_that_cannot_tell_its_clock(monkeypatch, tmp_path):
    """10.2, unix-capture.md 4.6.2 D-2 [Z7F3]: a source whose `clock` is `unknown` (Media Foundation: it reads only
    `IMFSample::GetSampleTime`, and no attribute names the base) gives `clock:base` `not-run` `clock-unknown`; a source
    that does not fill the key (null) gives `not-built`. `time-gaps` judges the gaps from `long_intervals`."""
    unknown = good(diagnostics={**SOURCE_FACTS, "clock": "unknown"})
    unfilled = good(diagnostics={**SOURCE_FACTS, "clock": None})
    with capture_app(monkeypatch, [unknown, unfilled]) as app:
        devices = app.factory.device_infos()
        report = run_with(app, tmp_path, level="full")
    assert_valid(report)
    checks = by_name(report)
    cannot_tell, not_built = labels(devices)
    assert (checks[f"{cannot_tell}:clock:base"]["result"], checks[f"{cannot_tell}:clock:base"]["reason"]) == (
        "not-run", "clock-unknown")
    assert checks[f"{cannot_tell}:clock:base"]["numbers"]["clock"] == "unknown"
    assert checks[f"{not_built}:clock:base"]["reason"] == "not-built"
    assert checks[f"{cannot_tell}:time-gaps"]["result"] == "pass"


@pytest.mark.capture_timing
def test_t_cert_12_a_camera_that_hangs_at_the_open(monkeypatch, tmp_path):
    """T-CERT-12, 2.3, 8.3: `opens` `fail` `hung`; the later checks one `not-reached` row `prior-failure` (3.6.1);
    never opened again;
    the cleanup row `release:<label>` `camera-wedged` and one notice `camera-wedged` with the cleaned name;
    `<model>:gate:no-hang` `fail` in `full`; the other camera completes."""
    scripts = [good(hang_at="open", hang_armed=True), good()]
    with capture_app(monkeypatch, scripts, workers="process") as app:
        devices = app.factory.device_infos()
        report = run_with(app, tmp_path, level="full")
        opens = app.factory.logs[app.factory.camera_ids[0]].opens.value
    assert_valid(report)
    checks = by_name(report)
    hung, fine = labels(devices)
    assert checks[f"{hung}:opens"]["result"] == "fail" and checks[f"{hung}:opens"]["reason"] == "hung"
    assert checks[f"{hung}:not-reached"]["reason"] == "prior-failure"
    assert opens == 1
    assert report["cleanup"] == [{"name": f"release:{hung}", "result": "fail", "reason": "camera-wedged",
                                  "module": "Fake camera 0"}]
    assert report["notices"] == [{"code": "camera-wedged", "values": {"camera": "Fake camera 0"}}]
    assert checks[f"{hung.rsplit('.', 1)[0]}:gate:no-hang"]["result"] == "fail"
    assert checks[f"{fine}:records:rows-complete"]["result"] == "pass"


def test_session_child_runs_the_product_path(tmp_path, monkeypatch):
    """T-CERT-32 in part, 2.1, 2.2: the session runs in a spawn child with real camera processes; the setting
    `SKELLYCAM_WINDOWS_CAPTURE=opencv` does not change the source (the factory gives the fakes); each check of
    the five groups passes; no process of the run is left."""
    monkeypatch.setenv("SKELLYCAM_WINDOWS_CAPTURE", "opencv")
    factory = FakeSourceFactory([good()])
    before = {p.pid for p in psutil.Process().children(recursive=True)}
    report = product(RUN).run("quick", devices=factory.device_infos(), source_factory=factory, **paths(tmp_path))
    assert_valid(report)
    (label,) = labels(factory.device_infos())
    checks = by_name(report)
    for name in group_checks(label):
        assert checks[name]["result"] == "pass", checks[name]
    time.sleep(0.5)
    left = {p.pid for p in psutil.Process().children(recursive=True)} - before
    assert not left, left


def test_session_child_a_cancel_kills_the_session_tree(tmp_path):
    """T-CERT-16 in part, 9.3: a cancel when the take starts kills the session child with its camera processes;
    the checks that did not end are `not-run` `cancelled`; phase G opens the touched camera again in a recheck
    child; no process of the run is left."""
    cancel = threading.Event()
    factory = FakeSourceFactory([good()])

    def progress(message):
        if (message.get("step") or {}).get("name") == "group:take:finished":
            cancel.set()

    before = {p.pid for p in psutil.Process().children(recursive=True)}
    report = product(RUN).run("quick", progress, cancel, devices=factory.device_infos(), source_factory=factory,
                              **paths(tmp_path))
    assert_valid(report)
    checks = by_name(report)
    (label,) = labels(factory.device_infos())
    assert checks[f"{label}:opens"]["result"] == "pass"
    assert checks["group:take:finished"]["reason"] == "cancelled"
    assert "cancelled" in report["evidence"]["reasons"]
    assert factory.logs[factory.camera_ids[0]].opens.value == 2
    time.sleep(0.5)
    left = {p.pid for p in psutil.Process().children(recursive=True)} - before
    assert not left, left


def test_the_package_names_the_two_functions():
    """C 2.1, 1: `skellycam.certify` and `skellycam.certify_plan` exist, and the caller does not load comtypes."""
    import skellycam
    assert callable(skellycam.certify) and callable(skellycam.certify_plan)
    loaded = "comtypes" in sys.modules
    product(RUN)
    assert loaded or "comtypes" not in sys.modules
