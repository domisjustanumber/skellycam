"""T-REC-14 to T-REC-18, T-REC-26 and T-REC-27: the manifest, the capture info, the lock, the clocks,
the order of the end of a take and the stop statistics.

specs/recorder.md, sections 4.2, 6.5 to 6.8, 8.1 and 8.2.
"""

import datetime
import errno
import hashlib
import json
import logging
import statistics
import time

import pytest

from skellycam.tests.take_recorder import sidecar_check
from skellycam.tests.take_recorder.rec_api import (
    MEDIA, T0, UTC0, WRITER, Run, camera_key, camera_label, fixed_clock, rec, rec_module, simple_take,
    take_camera, warnings_of)

MANIFEST_MEMBERS = ["skellyfileformat", "format_version", "format_prerelease", "writer", "take_uuid", "recording_name",
                    "purpose", "state", "cameras", "audio", "calibration", "files", "warnings", "privacy", "summary"]
SUMMARY_MEMBERS = ["take_start_utc", "duration_s", "cameras", "audio", "calibration", "processing_runs", "warnings"]
SUMMARY_CAMERA_MEMBERS = ["camera_label", "user_name", "model", "stored_px", "display_rotation", "nominal_fps", "gaps",
                          "filled", "missing", "exposure_us"]
INFO_MEMBERS = ["skellyfileformat", "format_version", "format_prerelease", "writer", "take_uuid", "camera_configs", "audio"]
CONFIG_MEMBERS = ["camera_label", "user_name", "key_origin", "device", "requested", "controls", "exposure_step"]
DEVICE_MEMBERS = ["model", "os_name", "vendor_id", "product_id", "serial", "port_path", "os_device_id", "backend", "os_index"]
REQUESTED_MEMBERS = ["width", "height", "framerate", "capture_format", "exposure_mode"]


def json_form_faults(path):
    """SFF-700 and SFF-702: UTF-8 with no BOM and LF; an integer value with no fraction or exponent;
    each other number in the shortest form that reads back as the same float64."""
    raw = path.read_bytes()
    faults = []
    if raw.startswith(b"\xef\xbb\xbf"):
        faults.append("byte order mark")
    if b"\r" in raw:
        faults.append("CR")

    def check_float(text):
        value = float(text)
        if value.is_integer():
            faults.append(f"integer value with a fraction or exponent: {text}")
        elif repr(value) != text:
            faults.append(f"number not in the shortest form: {text}")
        return value

    json.loads(raw.decode("utf-8"), parse_float=check_float)
    return faults


def expected_privacy(run, keys):
    fields = [{"file": f"{run.name}_info.json", "field": f"/camera_configs/{key}/device/os_name", "kind": "device_name"}
              for key in keys]
    fields += [{"file": f"{MEDIA}/{run.name}.{key[:6]}.csv", "field": "utc_offset_min", "kind": "time_zone"} for key in keys]
    fields.append({"file": "recording_manifest.json", "field": "/recording_name", "kind": "user_entered_name"})
    fields.sort(key=lambda f: (f["file"].encode("utf-8"), f["field"].encode("utf-8")))
    return {"fields": fields, "media_shows_people": True}


def duration_s(run, camera_ids):
    """SFF-728 with F-1: ns is the largest `arrival_ns` of the last row that holds one, of each sidecar."""
    last = []
    for camera_id in camera_ids:
        rows = [r for r in sidecar_check.read(run.csv(camera_id)).rows if r.arrival_ns is not None]
        last.append(rows[-1].arrival_ns)
    return ((max(last) + 500_000) // 10**6) / 1000


def test_t_rec_14_manifest_at_start_during_and_after(tmp_path, runs):
    """T-REC-14 [SFF-702, SFF-723, SFF-724, SFF-727, SFF-728, SFF-881, SFF-882]: the members of
    SFF-723 in order; `state` `recording`, then `finished`; `files` with the SHA-256 of the capture
    info; the summary nulls at the start and the values at the end; `camera_gap` for the camera with
    a gap, with the detail of its first gap (decision F of the user, 2026-11-20, recorder.md 6.6); the
    `privacy` of 6.6; the JSON form of SFF-702."""
    ids = ("0a1b", "ff00")
    run = simple_take(tmp_path / "take", runs, frames=0, finish=False)
    keys = [camera_key(c) for c in ids]
    for moment in ("start", "during"):
        if moment == "during":
            for k in range(10):
                run.give("0a1b", k, sfn=1000 + k + (3 if k >= 5 else 0))  # one gap at row 5
                run.give("ff00", k)
        manifest = run.manifest()
        assert list(manifest) == MANIFEST_MEMBERS
        assert manifest["skellyfileformat"] == "recording_manifest" and manifest["state"] == "recording"
        assert (manifest["format_version"], manifest["format_prerelease"], manifest["writer"]) == ("2.0", 1, WRITER)
        assert manifest["recording_name"] == "take" and manifest["purpose"] == "motion_capture"
        assert manifest["audio"] is None and manifest["calibration"] is None and manifest["warnings"] == []
        info_sha = hashlib.sha256((run.folder / "take_info.json").read_bytes()).hexdigest()
        assert manifest["files"] == [{"path": "take_info.json", "role": "capture_info", "owner": "skellycam", "sha256": info_sha}]
        assert manifest["privacy"] == expected_privacy(run, keys)
        summary = manifest["summary"]
        assert list(summary) == SUMMARY_MEMBERS and summary["duration_s"] is None
        for camera in summary["cameras"]:
            assert list(camera) == SUMMARY_CAMERA_MEMBERS
            assert [camera[m] for m in ("stored_px", "gaps", "filled", "missing")] == [None] * 4
        assert json_form_faults(run.folder / "recording_manifest.json") == []
    run.summary = run.finish(10)
    manifest = run.manifest()
    assert list(manifest) == MANIFEST_MEMBERS and manifest["state"] == "finished"
    info_sha = hashlib.sha256((run.folder / "take_info.json").read_bytes()).hexdigest()
    assert manifest["files"][0]["sha256"] == info_sha
    gap = warnings_of(manifest, "camera_gap")
    assert [(w["source"], w["camera_key"], w["detail"]) for w in gap] == [("skellycam", keys[0], "row=5 from=1004 to=1008")]
    assert manifest["privacy"] == expected_privacy(run, keys)
    summary = manifest["summary"]
    assert summary["take_start_utc"] == datetime.datetime.fromtimestamp(UTC0 // 10**9, datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert summary["duration_s"] == duration_s(run, ids)
    assert summary["audio"] is None and summary["calibration"] is None and summary["processing_runs"] == []
    assert summary["warnings"] == sorted({w["code"] for w in manifest["warnings"]})
    for position, camera in enumerate(summary["cameras"]):
        assert camera == {"camera_label": camera_label(ids[position]), "user_name": None, "model": None,
                          "stored_px": "640x480", "display_rotation": 0, "nominal_fps": 30,
                          "gaps": 1 if position == 0 else 0, "filled": 0, "missing": 0, "exposure_us": 31250}
    assert json_form_faults(run.folder / "recording_manifest.json") == []


def lock_faults(trace, lock_path=".processing.lock"):
    """Each whole-file write is `.tmp`, fsync, one replace, inside lock and unlock; each read of the
    manifest or of the capture info comes inside the lock (SFF-724, SFF-786, SFF-789)."""
    faults, locked, synced = [], 0, set()
    for event, path, extra in trace:
        if path == lock_path and event in ("lock", "unlock", "close"):
            if event == "lock":
                locked += 1
            elif locked:
                locked -= 1  # an explicit unlock, or the close of the lock file, releases the lock
            continue
        whole = path.endswith(("recording_manifest.json", "_info.json"))
        if event == "fsync" and path.endswith(".tmp"):
            synced.add(path)
        elif event == "replace" and whole:
            if not locked:
                faults.append(f"replace of {path} outside the lock")
            if not str(extra).endswith(".tmp") or extra not in synced:
                faults.append(f"replace of {path} from {extra} with no fsync of the .tmp file before it")
            synced.discard(extra)
        elif whole and event in ("read", "write", "truncate"):
            if event == "read" and not locked:
                faults.append(f"read of {path} outside the lock")
            if event != "read":
                faults.append(f"{event} of {path} in place")
    if locked:
        faults.append("the lock is held at the end")
    return faults


def full_trace(disk):
    with disk.lock:
        return [(e[2], e[3], e[4]) for e in disk.events]


def test_t_rec_15_whole_file_writes_under_the_lock(tmp_path, runs, disk):
    """T-REC-15 [SFF-724, SFF-726, SFF-786, SFF-789, SFF-801]: each whole-file write of `start_take`
    and `finish` is `.tmp`, fsync, one rename, inside lock and unlock; each read comes after the
    lock. An unknown member and a freemocap `files` item put in the manifest during the take stay."""
    run = simple_take(tmp_path / "take", runs, frames=5, finish=False)
    start_trace = full_trace(disk)
    replaced = [p for e, p, _ in start_trace if e == "replace"]
    assert replaced == ["take/take_info.json", "take/recording_manifest.json"]
    assert lock_faults(start_trace, "take/.processing.lock") == []
    manifest = run.manifest()
    manifest["x_unknown_member"] = {"kept": True}
    freemocap_item = {"path": "take_recording_info.json", "role": "processing_info", "owner": "freemocap", "sha256": None}
    manifest["files"].append(freemocap_item)
    (run.folder / "recording_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    mark = len(full_trace(disk))
    run.finish(5)
    finish_trace = full_trace(disk)[mark:]
    replaced = [p for e, p, _ in finish_trace if e == "replace"]
    assert replaced == ["take/take_info.json", "take/recording_manifest.json"]
    assert lock_faults(finish_trace, "take/.processing.lock") == []
    reads = [i for i, (e, p, _) in enumerate(finish_trace) if e == "read" and p.endswith("recording_manifest.json")]
    assert reads, "finish reads the manifest before it changes it (SFF-724)"
    final = run.manifest()
    assert final["x_unknown_member"] == {"kept": True}
    assert freemocap_item in final["files"]
    assert final["state"] == "finished"


@pytest.mark.recorder_slow
@pytest.mark.parametrize("case", ["released_after_2_s", "held_15_s"])
def test_t_rec_16_finish_waits_for_the_lock(tmp_path, runs, children, caplog, case):
    """T-REC-16 [SFF-789, F-7, review S7]: a second process holds `.processing.lock` with the lock of
    6.8 at the end of a take. Case 1: it releases after 2 s, and `finish` waits, then writes. Case 2:
    it holds 15 s; the manifest stays `recording`, an error is logged, and the stop response is given."""
    run = simple_take(tmp_path / "take", runs, frames=10, finish=False)
    run.end(10)
    hold = 2.0 if case == "released_after_2_s" else 15.0
    child = children({"mode": "lock", "path": str(run.folder / ".processing.lock"), "hold_s": hold})
    child.expect("locked")
    started = time.monotonic()
    with caplog.at_level(logging.ERROR):
        summary = run.finish(10)
    took = time.monotonic() - started
    if case == "released_after_2_s":
        assert took >= 1.5
        assert run.manifest()["state"] == "finished"
    else:
        assert 9.0 <= took < 15.0
        assert run.manifest()["state"] == "recording"
        assert [r for r in caplog.records if r.name.startswith("skellycam.core.take_recorder") and r.levelno >= logging.ERROR]
        response = summary.stop_response
        assert response["number_of_frames"] == 10 and response["number_of_cameras"] == 2
        assert response["recording_name"] == "take"


def test_t_rec_17_capture_info(tmp_path, runs):
    """T-REC-17 [SFF-800, SFF-801, SFF-802, F-6]: the members of section 13 of the format in order and
    no other; keys in order of `group_position`; the values of 6.7; null for the 5d fields; no
    `rotation`; written at the start and at the end with the same content."""
    first = take_camera("0a1b", rotation=90, controls={"exposure": (-5.0, False), "gain": (12.5, True), "focus": (None, None)})
    second = take_camera("ff00", os_index=3, os_name="Second Camera", vendor_id=None, product_id=None, backend="v4l2",
                         capture_format="YUYV", requested={"width": 640, "height": 480, "framerate": -1,
                                                           "capture_format": "YUYV", "exposure_mode": "auto"},
                         controls={"exposure": (-7.0, True), "gain": (None, None), "focus": (30.0, False)})
    run = Run(tmp_path / "take", [first, second])
    runs.append(run)
    at_start = (run.folder / "take_info.json").read_bytes()
    for k in range(3):
        run.give("0a1b", k)
        run.give("ff00", k)
    run.finish(3)
    at_end = (run.folder / "take_info.json").read_bytes()
    assert at_start == at_end
    info = run.info()
    assert list(info) == INFO_MEMBERS
    assert info["skellyfileformat"] == "capture_info" and info["audio"] is None
    assert (info["format_version"], info["format_prerelease"], info["writer"]) == ("2.0", 1, WRITER)
    assert info["take_uuid"] == run.manifest()["take_uuid"]
    keys = [camera_key("0a1b"), camera_key("ff00")]
    assert list(info["camera_configs"]) == keys
    one, two = (info["camera_configs"][k] for k in keys)
    for config, camera_id in ((one, "0a1b"), (two, "ff00")):
        assert list(config) == CONFIG_MEMBERS
        assert list(config["device"]) == DEVICE_MEMBERS and list(config["requested"]) == REQUESTED_MEMBERS
        assert (config["camera_label"], config["user_name"], config["key_origin"]) == (camera_label(camera_id), None, "provisional")
        assert config["exposure_step"] is None
        assert [config["device"][m] for m in ("model", "serial", "port_path", "os_device_id")] == [None] * 4
        assert list(config["controls"]) == ["exposure_us", "gain", "focus"]
        assert "rotation" not in config
    assert one["device"] == {"model": None, "os_name": "Synthetic Camera", "vendor_id": "046d", "product_id": "0825",
                             "serial": None, "port_path": None, "os_device_id": None, "backend": "media_foundation",
                             "os_index": 0}
    assert two["device"]["vendor_id"] is None and two["device"]["backend"] == "v4l2" and two["device"]["os_index"] == 3
    assert one["requested"] == {"width": 640, "height": 480, "framerate": 30, "capture_format": "MJPG", "exposure_mode": "manual"}
    assert two["requested"]["framerate"] == "camera_default" and two["requested"]["exposure_mode"] == "auto"
    assert one["controls"] == {"exposure_us": {"value": 31250, "auto": False}, "gain": {"value": 12.5, "auto": True},
                               "focus": {"value": None, "auto": None}}
    assert two["controls"]["exposure_us"] == {"value": 2**-7 * 10**6, "auto": True}
    assert two["controls"]["focus"] == {"value": 30, "auto": False}
    assert json_form_faults(run.folder / "take_info.json") == []


def test_t_rec_18_take_start_clocks(tmp_path, runs):
    """T-REC-18 [SFF-774]: the host clock is read first and the UTC clock at once after it, both in
    `start_take`, before the first frame; `utc_offset_min` is the local offset."""
    calls = []
    run = Run(tmp_path / "take", [take_camera("0a1b"), take_camera("ff00", os_index=1)],
              clock=fixed_clock(T0 + 7, UTC0 + 9, calls))
    runs.append(run)
    assert calls[:2] == ["host", "utc"] and calls.count("utc") == 1
    for camera_id in ("0a1b", "ff00"):
        run.give(camera_id, 0, arrival_ns=T0 + 1_000_007)
    run.finish(1)
    header = sidecar_check.read(run.csv("0a1b")).header
    offset = int(datetime.datetime.now().astimezone().utcoffset().total_seconds() // 60)
    assert (header["take_start_host_ns"], header["take_start_utc_ns"]) == (str(T0 + 7), str(UTC0 + 9))
    assert header["utc_offset_min"] == str(offset)
    assert sidecar_check.read(run.csv("0a1b")).rows[0].arrival_ns == 1_000_000


def test_t_rec_26_order_of_the_end_of_a_take(tmp_path, runs, disk):
    """T-REC-26 [SFF-724]: the order of 8.1: each camera's `end`, then the completion of the short
    file, the strict reads of the CSVs, the capture info, and the manifest last. Camera A has a write
    error (a short pair, 5.4); camera B is normal."""
    module = rec()
    run = simple_take(tmp_path / "take", runs, frames=10, finish=False)
    disk.fail(".mkv", errno_code=errno.ENOSPC, match=camera_label("0a1b"))
    k = 10
    with pytest.raises(module.RecorderWriteError):
        while k < 200:
            run.give("0a1b", k)  # raises at frame k: frame k of A is not written, and B does not get it
            run.give("ff00", k)
            k += 1
            time.sleep(0.005)
    run.end(k)
    ended = len(full_trace(disk))
    run.take.finish([run.results["0a1b"], run.results["ff00"]], frame_count=k)
    trace = full_trace(disk)[ended:]
    a_csv, a_mkv = (f"take/{MEDIA}/take.{camera_label('0a1b')}.{ext}" for ext in ("csv", "mkv"))
    b_csv = f"take/{MEDIA}/take.{camera_label('ff00')}.csv"
    completion = [i for i, (e, p, _) in enumerate(trace) if p in (a_csv, a_mkv) and e in ("write", "truncate")]
    assert completion, "the completion of the short pair writes"
    last_completion = completion[-1]
    replaces = [(i, p) for i, (e, p, _) in enumerate(trace) if e == "replace"]
    assert [p for _, p in replaces] == ["take/take_info.json", "take/recording_manifest.json"]
    info_at, manifest_at = replaces[0][0], replaces[1][0]
    for csv in (a_csv, b_csv):
        reads = [i for i, (e, p, _) in enumerate(trace) if p == csv and e == "read" and last_completion < i < info_at]
        assert reads, f"the strict read of {csv} comes after the completion and before the capture info"
    assert last_completion < info_at < manifest_at
    later = [(e, p) for e, p, _ in trace[manifest_at + 1:] if e in ("write", "truncate", "replace")]
    assert later == [], "the manifest is written last"


def write_sidecar(path, position, rows):
    """A finished sidecar written by the test from the text of 6.5."""
    header = {"skellyfileformat": "video_timing", "format_version": "2.0", "format_prerelease": "1", "writer": WRITER,
              "take_uuid": "0" * 31 + "1", "take_start_host_ns": str(T0), "take_start_utc_ns": str(UTC0),
              "utc_offset_min": "0", "clock": "windows_qpc", "clock_hz": "", "group_size": "3", "audio_count": "0",
              "group_position": str(position), "camera_key": f"{position:x}" * 16, "camera_label": f"{position:x}" * 6,
              "nominal_rate": "30/1", "display_rotation": "0"}
    lines = [f"# {key}={value}\n".encode() for key, value in header.items()]
    lines.append((",".join(sidecar_check.COLUMNS) + "\n").encode())
    previous = None
    for k, (arrival, missing) in enumerate(rows):
        sfn = None if arrival is None else 1000 + k
        flags = sidecar_check.expected_flags(previous, sfn, missing)
        lines.append(sidecar_check.make_row(k, sfn, arrival, None, flags, 100 + k, 10))
        previous = sfn
    missing_count = sum(1 for _, m in rows if m)
    lines.append(f"# end rows={len(rows)} gaps=0 filled=0 missing={missing_count} encode_skips=0\n".encode())
    path.write_bytes(b"".join(lines))


# Arrival times (ns, relative) of 3 cameras over 7 group frames; (time, missing).
ARRIVALS_27 = [
    [(1_000_000, False), (34_000_000, False), (66_500_000, False), (101_000_000, False), (133_000_000, False),
     (167_200_000, False), (200_100_000, False)],
    [(1_500_000, False), (33_900_000, False), (67_800_000, False), (99_000_000, False), (134_400_000, False),
     (166_000_000, False), (201_000_000, False)],
    [(2_000_000, False), (35_000_000, False), (68_000_000, True), (100_500_000, False), (None, True), (None, True),
     (None, True)],
]


def hand_stats(values):
    return {"median": statistics.median(values), "mean": statistics.fmean(values), "std": statistics.pstdev(values),
            "min": min(values), "max": max(values)}


def test_t_rec_27_stop_statistics_from_the_csvs(tmp_path):
    """T-REC-27 [R5]: CSVs with known arrival times, also `missing` rows (a damaged row with times and
    dead rows with none), through `stop_stats`. Each field of 8.2 equals the value computed by hand to
    1e-9. A `missing` row is left out of each statistic."""
    folder = tmp_path / "take"
    (folder / MEDIA).mkdir(parents=True)
    paths = []
    for position, rows in enumerate(ARRIVALS_27):
        path = folder / MEDIA / f"take.{f'{position:x}' * 6}.csv"
        write_sidecar(path, position, rows)
        paths.append(path)
    frames = len(ARRIVALS_27[0])
    rates, durations, ranges = [], [], []
    for k in range(frames):
        live = [rows[k][0] for rows in ARRIVALS_27 if not rows[k][1]]
        ranges.append((max(live) - min(live)) / 1e6)
        if k == 0:
            continue
        pairs = [(rows[k - 1][0], rows[k][0]) for rows in ARRIVALS_27 if not rows[k][1] and not rows[k - 1][1]]
        rates.append(statistics.fmean([1e9 / (b - a) for a, b in pairs]))
        durations.append(statistics.fmean([(b - a) / 1e6 for a, b in pairs]))
    last = max([r[0] for r in rows if r[0] is not None][-1] for rows in ARRIVALS_27)
    expected = {
        "recording_name": "take", "recording_path": str(folder), "number_of_cameras": 3, "number_of_frames": frames,
        "total_duration_sec": ((last + 500_000) // 10**6) / 1000,
        "mean_framerate": round(statistics.fmean(rates), 2),
        "mean_inter_camera_sync_ms": round(statistics.fmean(ranges), 2),
        "framerate_stats": hand_stats(rates), "frame_duration_stats": hand_stats(durations),
        "inter_camera_grab_range_ms_stats": hand_stats(ranges),
    }
    stop_stats = rec_module("stop_stats")
    got = stop_stats.stop_response_fields(paths, recording_name="take", recording_path=folder, frame_count=frames)
    assert set(got) == set(expected)
    for key, value in expected.items():
        if isinstance(value, dict):
            assert set(got[key]) == set(value), key
            for stat, number in value.items():
                assert got[key][stat] == pytest.approx(number, abs=1e-9), f"{key}.{stat}"
        elif isinstance(value, float):
            assert got[key] == pytest.approx(value, abs=1e-9), key
        elif key == "recording_path":
            assert str(got[key]) == value
        else:
            assert got[key] == value, key

