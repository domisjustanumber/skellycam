"""Cycle statistics and plan section 3 ratings."""
import pytest

from common import cycstats, rating


def _rows(pattern):
    out = []
    for i, ch in enumerate(pattern):
        ok = ch == "."
        r = {"i": i, "ok": ok, "activate_ms": 30 + i % 5, "first_frame_ms": 400 if ok else None, "close_ms": 20}
        if not ok:
            r.update(stage_failed="first_frame", hr="0x8007001F", hr_name="ERROR_GEN_FAILURE")
        if ch == "T":
            r.update(stage_failed="timeout", timed_out=True, hr=None, hr_name=None)
        out.append(r)
    return out


def test_wilson():
    lo, hi = cycstats.wilson_interval(99, 100)
    assert lo == pytest.approx(0.9455, abs=1e-3) and hi == pytest.approx(0.9982, abs=1e-3)
    assert cycstats.wilson_interval(0, 0) == (0.0, 1.0)


def test_summarize_cycles():
    s = cycstats.summarize_cycles(_rows("....x..xx..T...."))
    assert s["n"] == 16 and s["n_ok"] == 12
    assert s["longest_failure_run"] == 2 and s["hangs"] == 1
    assert s["recovery_after_failure"] == {"failures_followed": 4, "recovered": 3, "rate": 0.75}
    assert s["timings_ms"]["first_frame_ms"]["p50"] == 400
    top = s["failure_classes"][0]
    assert top["count"] == 3 and top["stage"] == "first_frame"
    assert s["trailing_failures"] == 0


def test_rate_reliability():
    assert rating.rate_reliability(cycstats.summarize_cycles(_rows("." * 100)), replug_needed=False)["rating"] == "yes"
    assert rating.rate_reliability(cycstats.summarize_cycles(_rows("." * 97 + "x" * 3)))["rating"] == "partial"
    assert rating.rate_reliability(cycstats.summarize_cycles(_rows("." * 90 + "x" * 10)))["rating"] == "no"
    assert rating.rate_reliability(cycstats.summarize_cycles(_rows("." * 99 + "T")))["rating"] == "partial"
    assert rating.rate_reliability(cycstats.summarize_cycles([]))["rating"] == "untested"
    r = rating.rate_reliability(cycstats.summarize_cycles(_rows("." * 100)), replug_needed=True)
    assert r["rating"] == "no" and r["criteria"]


def test_rate_bw():
    good = [{"predicted_verdict": "over", "observed_refused": True, "classified_class": "bandwidth_certain",
             "message_ports_other_domains": True, "retry_ok": True},
            {"predicted_verdict": "fits", "observed_refused": False}]
    assert rating.rate_bw(good)["rating"] == "yes"
    assert rating.rate_bw(good, labels_raw=True)["rating"] == "partial"
    assert rating.rate_bw([dict(good[0], predicted_verdict="fits")])["rating"] == "no"
    assert rating.rate_bw([dict(good[0], classified_class="in_use")])["rating"] == "no"
    assert rating.rate_bw([good[1]])["rating"] == "untested"


def test_rate_ts():
    assert rating.rate_ts(0.4, True, True)["rating"] == "yes"
    assert rating.rate_ts(0.4, True, True, tier=1)["rating"] == "partial"
    assert rating.rate_ts(1.5, True, True)["rating"] == "partial"
    assert rating.rate_ts(3.0, True, True)["rating"] == "no"
    assert rating.rate_ts(None, True, False, host_grid_ms=16.0)["rating"] == "no"
    assert rating.rate_ts(None, True, False, synthesized=True)["rating"] == "no"
    assert rating.rate_ts(None, True, False, device_ts_self_consistent=True)["rating"] == "partial"
    assert rating.rate_ts(None, None, False)["rating"] == "untested"


def test_rate_mjpeg():
    m = {"mode": "MJPG 1280x720@30", "negotiated": True, "strict_valid_fraction": 1.0, "lenient_valid_fraction": 1.0,
         "sof_matches": True, "fps_measured": 29.9, "fps_expected": 30.0,
         "header_sha1_by_api": {"mf": "a", "pyav_ds": "a"}}
    assert rating.rate_mjpeg([m])["rating"] == "yes"
    quirk = dict(m, strict_valid_fraction=0.0, known_quirk="generic 1080p extraneous bytes before EOI")
    assert rating.rate_mjpeg([quirk])["rating"] == "yes"
    assert rating.rate_mjpeg([dict(m, strict_valid_fraction=0.0)])["rating"] == "partial"
    assert rating.rate_mjpeg([m, dict(m, negotiated=False)])["rating"] == "partial"
    assert rating.rate_mjpeg([dict(m, header_sha1_by_api={"mf": "a", "ds": "b"})])["rating"] == "partial"
    assert rating.rate_mjpeg([m], jpeg_bytes=False)["rating"] == "no"


def test_rate_ctrl_and_id():
    c = {"name": "exposure", "listed": True, "range_matches_descriptor": True, "set_readback_ok": True,
         "effect_ok": True, "before_start_ok": True, "after_start_ok": True, "runs_ok": 3, "runs_total": 3}
    assert rating.rate_ctrl([c])["rating"] == "yes"
    assert rating.rate_ctrl([dict(c, workaround="re-apply after start")])["rating"] == "partial"
    assert rating.rate_ctrl([dict(c, set_readback_ok=False)], can_set_any=False)["rating"] == "no"
    keys = ["a", "b"]
    runs = {"mf": [keys] * 20, "ds": [keys] * 20}
    r = rating.rate_id(runs, keys)
    assert r["rating"] == "partial" and "provisional" in r["note"]
    full = rating.rate_id(runs, keys, {"reboot": True, "same_port_replug": True, "port_move_serial": True})
    assert full["rating"] == "yes"
    assert rating.rate_id({"opencv": [[None, None]] * 20}, keys)["rating"] == "no"
    assert rating.worst([full, r, rating.untested("x")]) == "partial"
