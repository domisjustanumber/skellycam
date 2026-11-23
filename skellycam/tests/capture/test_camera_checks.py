"""T-UNX-62 and T-UNX-74, the shared part: the reader of the record of checked models and of the shipped
evidence file (specs/unix-capture.md 4.2 item 8, 4.9; specs/certify.md 2.5, 11.2, 11.3).

Certify owns the writer of `camera_checks.json` and its tests (T-CERT-41). The shipped file
`camera_evidence.json` does not exist yet: the reader treats a missing file as no rows. The source selection
of 4.9 (T-UNX-61) and the native detection of Linux and macOS wait for steps 7a and 7b.
"""

import json
import logging

import pytest

from skellycam.tests.capture.capture_session import product
from skellycam.tests.capture.fake_source import FakeSourceFactory, FakeScript

CHECKS_MODULE = "skellycam.core.camera.capture.camera_checks"
GATE = {"opens": "pass", "mode": "pass", "rate": "pass", "native-jpeg": "pass", "timestamps": "pass",
        "sequence": "pass", "records": "pass", "no-hang": "pass"}
KEY = dict(device="046d:085c", backend="v4l2", os_key="7.0", abi="lp64")


def row(**changes):
    value = {**KEY, "level": "full", "item": "partial", "skellycam": "2.0.0a6", "date": "2026-11-20",
             "gate": dict(GATE), "controls": {"exposure": {"v4l2": "works"}, "gain": {"v4l2": "unproven"},
                                              "focus": {"v4l2": "no"}}}
    value.update(changes)
    return value


def write(path, rows, **extra):
    path.write_text(json.dumps({"format": 1, "rows": rows, **extra}), encoding="utf-8")
    return path


def test_t_unx_62_the_reader_of_the_record(tmp_path):
    """T-UNX-62: the source reads the turn-on checks and the routes of each model from a file of the form of
    cert 2.5; a failed gate check, a `quick` row, another OS key and another ABI give no local pass; an
    unknown field is ignored; the reader never writes the file."""
    checks = product(CHECKS_MODULE)
    rows = [row(), row(device="046d:0892", gate={**GATE, "rate": "fail"}), row(device="1532:0e05", level="quick",
            gate=None, controls=None, colour="an unknown field")]
    path = write(tmp_path / "camera_checks.json", rows, written_by="an unknown field")
    before = path.read_bytes()
    read = checks.read_rows(path)
    assert read == rows
    assert checks.local_pass(read, **KEY)
    assert not checks.local_pass(read, **{**KEY, "device": "046d:0892"})  # a failed turn-on check
    assert not checks.local_pass(read, **{**KEY, "device": "1532:0e05"})  # a quick row
    assert not checks.local_pass(read, **{**KEY, "os_key": "7.1"}) and not checks.local_pass(read, **{**KEY, "abi": "ilp32"})
    assert checks.control_routes(read, **KEY) == {"exposure": {"v4l2": "works"}, "gain": {"v4l2": "unproven"},
                                                  "focus": {"v4l2": "no"}}
    assert checks.control_routes(read, **{**KEY, "device": "1532:0e05"}) == {}
    assert checks.checked(read, **{**KEY, "device": "1532:0e05"}) and not checks.checked(read, **{**KEY, "os_key": "7.1"})
    assert path.read_bytes() == before


def test_t_unx_62_a_newer_row_replaces_an_older_one(tmp_path):
    """cert 2.5: a newer row for the same key replaces the older one (the last row of the file wins)."""
    checks = product(CHECKS_MODULE)
    read = checks.read_rows(write(tmp_path / "camera_checks.json", [row(), row(gate={**GATE, "records": "fail"})]))
    assert not checks.local_pass(read, **KEY)


@pytest.mark.parametrize("content", [None, "{not json", '{"format": 2, "rows": []}', '{"format": 1, "rows": 3}', "[]"],
                         ids=["missing", "broken", "other format", "rows not a list", "not an object"])
def test_t_unx_62_a_file_that_cannot_be_read_is_no_rows(tmp_path, caplog, content):
    """T-UNX-62, cert 2.5: a missing file, a file that cannot be read and a file that does not parse count as
    no rows; the reader logs that one time for the file, and never raises."""
    checks = product(CHECKS_MODULE)
    path = tmp_path / "camera_checks.json"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    with caplog.at_level(logging.DEBUG, logger=CHECKS_MODULE):
        assert checks.read_rows(path) == [] and checks.read_rows(path) == []
    lines = [r.getMessage() for r in caplog.records if r.name == CHECKS_MODULE]
    assert len(lines) == 1 and "camera_checks.json" in lines[0], lines


def test_t_unx_74_detection_fields_with_a_local_record_and_no_evidence_file(tmp_path):
    """T-UNX-74, the shared part: `backend`, `id_source`, `has_serial`, `evidence` and `checked` in
    `CameraDeviceInfo`. The evidence file is missing: each camera is `unknown`. A local row of the model on
    this OS key and ABI marks it `checked`."""
    checks = product(CHECKS_MODULE)
    devices = FakeSourceFactory([FakeScript(), FakeScript()]).device_infos()
    for device in devices:
        device.backend, device.id_source = "media-foundation", "mf-link"
    record = write(tmp_path / "camera_checks.json", [row(device="feed:0001", backend="media-foundation",
                                                         os_key="11 26H2", level="quick")])
    marked = checks.mark_devices(devices, checks_path=record, evidence_path=tmp_path / "camera_evidence.json",
                                 os_key="11 26H2", abi="lp64")
    assert [(d.backend, d.id_source, d.has_serial, d.evidence, d.checked) for d in marked] == [
        ("media-foundation", "mf-link", None, "unknown", False), ("media-foundation", "mf-link", None, "unknown", True)]


def test_t_unx_74_the_evidence_file_gives_verified_and_known_bad(tmp_path):
    """T-UNX-74, cert 11.2 and 11.3: a `verified` and a `known-bad` row of the evidence file for the model,
    backend, OS key and ABI; a key with no row is `unknown`."""
    checks = product(CHECKS_MODULE)
    devices = FakeSourceFactory([FakeScript(), FakeScript(), FakeScript()]).device_infos()
    for device in devices:
        device.backend = "media-foundation"
    evidence = tmp_path / "camera_evidence.json"
    evidence.write_text(json.dumps({"schema": 1, "systems": [], "cameras": [
        {"device": "feed:0000", "backend": "media-foundation", "os_key": "11 26H2", "abi": "lp64", "state": "verified"},
        {"device": "feed:0001", "backend": "media-foundation", "os_key": "11 26H2", "abi": "lp64", "state": "known-bad"},
        {"device": "feed:0002", "backend": "media-foundation", "os_key": "11 25H2", "abi": "lp64", "state": "verified"}]}),
        encoding="utf-8")
    marked = checks.mark_devices(devices, checks_path=tmp_path / "none.json", evidence_path=evidence,
                                 os_key="11 26H2", abi="lp64")
    assert [d.evidence for d in marked] == ["verified", "known-bad", "unknown"]


def test_t_unx_74_the_os_key_and_the_abi():
    """cert 11.2: the OS key of this system has the form of its OS; the ABI is `lp64` on a 64-bit Python."""
    import platform
    import re
    import struct

    checks = product(CHECKS_MODULE)
    key = checks.current_os_key()
    # Windows: the release (`11`, or `2025Server` on Windows Server 2025, CI run 45278395951), a space and the
    # feature version
    pattern = {"Windows": r"^\d+(Server)? \w+$", "Linux": r"^\d+\.\d+$", "Darwin": r"^\d+$"}[platform.system()]
    assert re.match(pattern, key), key
    assert checks.current_abi() == ("lp64" if struct.calcsize("P") == 8 else "ilp32")


def test_t_unx_74_the_windows_os_key_of_a_client_and_a_server(monkeypatch):
    """cert 11.2: the Windows OS key is the release and the feature version. Windows Server keeps the release of
    `platform.release()`: with the same feature version 24H2, the server key differs from the client key."""
    import sys
    from types import SimpleNamespace

    checks = product(CHECKS_MODULE)
    registry = SimpleNamespace(HKEY_LOCAL_MACHINE="HKLM", OpenKey=lambda *args: __import__("contextlib").nullcontext(),
                               QueryValueEx=lambda handle, name: ("24H2", 1) if name == "DisplayVersion" else None)
    monkeypatch.setitem(sys.modules, "winreg", registry)
    keys = []
    for release in ("11", "2025Server"):
        monkeypatch.setattr(checks, "platform", SimpleNamespace(system=lambda: "Windows", release=lambda: release))
        keys.append(checks.current_os_key())
    assert keys == ["11 24H2", "2025Server 24H2"]


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="the media_foundation package is Windows only (U18)")
def test_t_unx_74_windows_detection_gives_the_fields(monkeypatch, tmp_path):
    """T-UNX-74 on Windows: `detect_available_cameras` gives `backend` `media-foundation`, `id_source`
    `mf-link`, and `evidence` and `checked` from the record of the base folder (no evidence file yet)."""
    import skellycam.core.device_detection.detect_cameras_devices as detection
    import skellycam.system.default_paths as default_paths
    from skellycam.core.camera.capture.media_foundation import detect
    from skellycam.tests.capture.fake_source import fake_link

    checks = product(CHECKS_MODULE)
    devices = [detect.MediaFoundationDeviceInfo(index=index, name=f"Fake camera {index}", path=fake_link(index),
                                                vendor_id=0xFEED, product_id=index) for index in range(2)]
    monkeypatch.setattr(detect, "detect_media_foundation_cameras", lambda modes=True: devices)
    monkeypatch.setattr(detection, "_add_usb_links", lambda cameras: cameras)
    monkeypatch.setattr(default_paths, "get_default_skellycam_base_folder_path", lambda: str(tmp_path))
    write(tmp_path / "camera_checks.json", [row(device="feed:0000", backend="media-foundation",
                                                os_key=checks.current_os_key(), level="quick")])
    found = detection.detect_available_cameras()
    assert [(d.backend, d.id_source, d.evidence, d.checked) for d in found] == [
        ("media-foundation", "mf-link", "unknown", True), ("media-foundation", "mf-link", "unknown", False)]
