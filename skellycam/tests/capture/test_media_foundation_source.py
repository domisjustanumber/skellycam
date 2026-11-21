"""T-UNX-76 and T-UNX-78: `MediaFoundationSource` with the stand-in interfaces of `mf_standins.py` (specs/unix-capture.md
4.2 item 2, 4.6.2, 4.7; windows-capture.md 6.9). Windows only (U18). Each case runs in a fresh process (see
`mf_standins.py`)."""

import json
import subprocess
import sys

import pytest

from skellycam.tests.capture.capture_session import product

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="the media_foundation package is Windows only (U18)")


def run_case(case):
    process = subprocess.run([sys.executable, "-m", "skellycam.tests.capture.mf_standins", case],
                             capture_output=True, text=True, timeout=120)
    assert process.returncode == 0, process.stderr[-3000:]
    return json.loads(process.stdout.strip().splitlines()[-1])


def test_t_unx_76_media_foundation_diagnostics():
    """T-UNX-76: every key of 4.6.2; `id_source` `mf-link`; `native_domain` `hresult`; `clock` `unknown`;
    the `t_*_ms` keys of the steps that Media Foundation has are filled (it has no buffer step)."""
    source = product("skellycam.core.camera.capture.source")
    result = run_case("diagnostics")
    data = result["diagnostics"]
    assert result["frames"] == 10
    assert set(data) == set(source.SOURCE_KEYS)
    assert (data["backend"], data["id_source"], data["native_domain"], data["clock"]) == (
        "media-foundation", "mf-link", "hresult", "unknown")
    times = {key: data[key] for key in source.SOURCE_KEYS if key.startswith("t_")}
    assert times.pop("t_buffers_ms") is None
    assert all(isinstance(value, float) and value >= 0 for value in times.values()), times
    assert (data["requested_w"], data["granted_w"], data["granted_fps_num"], data["delivered"]) == (640, 640, 30, "jpeg")
    assert data["frames"] >= 10 and len(data["frame_log"]) == min(64, data["frames"])
    assert data["sample_minus_arrival_p50_ms"] == pytest.approx(-4.0, abs=0.01)
    assert data["later_than_arrival"] == 0 and data["sample_time_kept"] is True
    # the last read-back is that of the restore at the close (4.7): the value of before the open
    assert (data["exposure_present"], data["exposure_value"], data["control_path"]) == (True, -6, "iam")
    assert data["focus_present"] is False and data["fail_code"] is None
    # F10: the range of IAMCameraControl::GetRange; the keys that Media Foundation cannot fill are null (4.6.2)
    assert [data[f"exposure_{k}"] for k in ("min", "max", "step", "default", "auto_supported")] == [-13, -1, 1, -6, True]
    assert (data["long_intervals"], data["format_changes"]) == (0, 0)
    assert all(data[k] is None for k in ("error_flag_frames", "drops_reported", "long_intervals_with_seq_gap"))


def restore_sets(result):
    """The `Set` calls of the close (after the `close` mark), and the index of the flush among the calls."""
    calls = result["calls"]
    start = calls.index(["close"])
    flush = calls.index(["flush"])
    return [call[1:] for call in calls[start:] if call[0] == "set"], flush - start, calls[start:]


def test_t_unx_78_the_restore_at_the_close_is_on_by_default():
    """T-UNX-78, T-REQ-15: exposure was in auto (-6) and gain manual (10) before the open; the source set
    exposure -7 and gain 20. At the close each changed control is set back to its value and flags of before
    (exposure with the auto flag), before the flush, and read back: `restore_ok` true, `restore_failed` 0."""
    result = run_case("restore")
    sets, flush_at, calls = restore_sets(result)
    assert sets == [["camera", 4, -6, 1], ["procamp", 9, 10, 2]], calls  # sorted by name: exposure, gain
    assert all(calls.index(["set", *item]) < flush_at for item in sets), calls
    data = result["diagnostics"]
    assert (data["restore_ok"], data["restore_failed"]) == (True, 0)
    assert (data["exposure_before"], data["exposure_before_auto"], data["gain_before"]) == (-6, True, 10)


def test_t_unx_78_no_restore_with_the_setting_0():
    """T-UNX-78, unix-capture.md 4.7: with `SKELLYCAM_RESTORE_CONTROLS=0` the close sets no control."""
    sets, _, calls = restore_sets(run_case("restore-off"))
    assert sets == [], calls


def test_t_unx_78_a_failed_restore_is_recorded_and_the_close_goes_on():
    """T-UNX-78: the restore `Set` of gain fails: `restore_ok` false, `restore_failed` 1; the close goes on
    (the flush and both shutdowns come)."""
    result = run_case("restore-fails")
    sets, _, calls = restore_sets(result)
    assert sets == [["camera", 4, -6, 1], ["procamp", 9, 10, 2]], calls
    assert ["flush"] in calls and ["shutdown"] in calls and ["shutdown-object"] in calls
    data = result["diagnostics"]
    assert (data["restore_ok"], data["restore_failed"]) == (False, 1)


def test_f7_no_restore_after_a_stream_error():
    """F7 (reviewer list): a removal HRESULT in `OnReadSample` before the close: the close sets no control."""
    sets, _, calls = restore_sets(run_case("after-error"))
    assert sets == [], calls


def test_f7_no_restore_after_a_hang():
    """F7 (reviewer list): a control `Set` that does not return makes the source hung; the close then touches
    no interface: no restore set, and it returns at once."""
    result = run_case("after-hang")
    assert result["set_failure"] == ["set controls", "hung"]
    calls = result["calls"][result["calls"].index(["close"]):]
    assert not [call for call in calls if call[0] == "set"], calls
    assert result["close_s"] < 0.5


def test_f7_no_restore_when_the_loop_failed():
    """F7: the shared loop closes a camera whose loop failed (for example the in-process stall rule, which sets
    no error of the source) with `restore=False`: no set and no read-back at the close."""
    sets, _, calls = restore_sets(run_case("loop-failed"))
    assert sets == [], calls


def test_f7_a_hanging_restore_ends_the_close_as_hung_within_its_bound():
    """F7 (reviewer list): the restore `Set` of gain does not return. The close stops there as hung (stage
    `close`, code `hung`) within the bound of one call (5 s), and goes to no later step (W 6.6, 6.9)."""
    result = run_case("restore-hangs")
    assert result["close_failure"] == ["close", "hung", True]
    assert 5.0 <= result["close_s"] <= 6.0, result["close_s"]
    assert ["flush"] not in result["calls"]


def test_t_req_15_no_auto_set_outside_the_close_and_the_exposure_range():
    """T-REQ-15 (Media Foundation), camera-requests.md 1.1 and 1.3 item 1 [K4, GEH0]: no `Set` with the auto flag
    comes before the close (only the restore of the close sets it); `exposure_range()` gives min, max and step
    of `IAMCameraControl::GetRange`."""
    result = run_case("restore")
    calls = result["calls"]
    close = calls.index(["close"])
    auto = [i for i, call in enumerate(calls) if call[0] == "set" and call[4] & 1]  # flags: 1 auto, 2 manual
    assert auto and all(i > close for i in auto), calls
    assert result["exposure_range"] == [-13, -1, 1]



@pytest.mark.parametrize(("held", "opened"), [(-9, -9), (-15, -13), (0, -1)])
def test_an_auto_open_on_media_foundation_sets_the_held_value_inside_the_range(held, opened):
    """camera-requests.md 1.3a [GEH0] (the fault of the real-camera run of 2026-11-21): the open steps of the shared
    loop in AUTO on `MediaFoundationSource` over the stand-ins (GetRange -13 to -1, step 1): no error; the held value
    inside the range opens at that value, below it at -13, above it at -1; the config stores the read-back."""
    result = run_case(f"auto-open:{held}")
    assert result["error"] is None, result
    assert result["exposure_range"] == [-13, -1, 1]
    assert result["sets"][0] == ["camera", 4, opened, 2], result["sets"]  # flags 2: manual
    assert result["exposure"] == opened
