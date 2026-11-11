"""Shared rating contract of 2026-11-06 (analyses of suite_20261106T181941Z and their verifier notes)."""
from common import cycstats, rating


# ------------------------------------------------------------------------------------------------ G-MJPEG
def _mode(**kw):
    m = {"mode": "MJPG 1280x720@25", "negotiated": True, "frames": 75, "strict_valid_fraction": 1.0,
         "lenient_valid_fraction": 1.0, "sof_matches": True, "fps_measured": 25.70,
         "header_sha1_by_api": {"mf": "a", "ds": "a"}, "is_jpeg": True}
    m.update(kw)
    return m


def test_mjpeg_device_fault_is_untested():
    rows = [_mode(negotiated=False, frames=0, is_jpeg=None) for _ in range(3)]
    r = rating.rate_mjpeg(rows, device_fault=True, fault_code="0x8007001F", first_fault_utc="2026-11-06T18:43:49Z")
    assert r["rating"] == "untested"
    assert r["evidence"]["device_fault"] is True and r["evidence"]["fault_code"] == "0x8007001F"
    assert "device fault, replug needed" in r["criteria"][0]["detail"]


def test_mjpeg_zero_jpeg_frames_without_fault_is_no():
    rows = [_mode(negotiated=False, frames=0, is_jpeg=None), _mode(frames=10, is_jpeg=False)]
    assert rating.rate_mjpeg(rows)["rating"] == "no"
    # one JPEG frame anywhere -> not 'no'
    assert rating.rate_mjpeg(rows + [_mode()])["rating"] == "partial"
    # legacy rows without 'frames' / 'is_jpeg' are not treated as empty
    legacy = {k: v for k, v in _mode(fps_expected=25.7).items() if k not in ("frames", "is_jpeg")}
    assert rating.rate_mjpeg([legacy])["rating"] == "yes"


def test_mjpeg_symmetric_fps_reference_and_rate_honoured():
    # generic camera: 25.7 fps at nominal 25 through both APIs -> fps ok (agreed real rate), rate not honoured
    fast = _mode(fps_other_api=25.69, fps_nominal=25)
    r = rating.rate_mjpeg([fast])
    assert r["rating"] == "yes"
    row = r["evidence"]["modes"][0]
    assert row["fps_reference_source"] == "both_apis_agree" and row["rate_honoured"] is False
    assert r["evidence"]["rate_honoured"]["not_honoured_modes"] == ["MJPG 1280x720@25"]
    # slow side works the same way (symmetric): C922 at nominal 5 delivering 30 on both APIs
    slow = _mode(mode="MJPG 1280x720@5", fps_measured=29.98, fps_other_api=30.02)
    assert rating.rate_mjpeg([slow])["rating"] == "yes"
    # APIs disagree -> nominal reference -> fps fails
    dis = _mode(mode="MJPG 1280x720@20", fps_measured=22.9, fps_other_api=20.1)
    rr = rating.rate_mjpeg([dis])
    assert rr["rating"] == "partial" and rr["evidence"]["modes"][0]["fps_reference_source"] == "nominal"
    # tier 0 only (Dom 2026-11-09): a device-PTS rate is ignored, the APIs disagree -> nominal
    pts = _mode(fps_measured=25.71, fps_uvc_pts=25.70, fps_pts=25.70, fps_other_api=20.0)
    assert rating.rate_mjpeg([pts])["evidence"]["modes"][0]["fps_reference_source"] == "nominal"
    # rate honoured
    ok = _mode(mode="MJPG 640x480@30", fps_measured=29.9, fps_other_api=29.95)
    assert rating.rate_mjpeg([ok])["evidence"]["modes"][0]["rate_honoured"] is True


def test_fps_reference_legacy_expected():
    assert rating.fps_reference({"fps_measured": 29.9, "fps_expected": 30.0}) == (30.0, "caller")
    assert rating.fps_reference({"mode": "MJPG 640x480@7.5"}) == (7.5, "nominal")
    assert rating.fps_reference({}) == (None, None)


# ------------------------------------------------------------------------------------------------ reliability
def _rows(pattern, ff=400):
    out = []
    for i, ch in enumerate(pattern):
        ok = ch in ".s"
        r = {"i": i, "ok": ok, "first_frame_ms": (3000 if ch == "s" else ff) if ok else None,
             "open_to_first_frame_ms": (3000 if ch == "s" else ff) if ok else None, "close_ms": 20}
        if not ok:
            r.update(stage_failed="first_frame", hr="0x8007001F")
        out.append(r)
    return out


def test_reliability_pre_existing_fault_is_untested():
    s = cycstats.summarize_cycles(_rows("x" * 15))
    fault = {"first_fault_utc": "2026-11-06T18:43:49Z", "test": "W-MJPEG", "code": "0x8007001F"}
    r = rating.rate_reliability(s, replug_needed=True, pre_existing_fault=True, fault=fault)
    assert r["rating"] == "untested" and r["summary_label"] == "untested (pre-existing fault)"
    assert r["evidence"]["fault"] == fault


def test_reliability_evidence_fields():
    s = cycstats.summarize_cycles(_rows("." * 50))
    r = rating.rate_reliability(s, replug_needed=False)
    ev = r["evidence"]
    for k in ("n", "n_ok", "success_rate", "wilson95", "p50_open_to_first_frame_ms", "format_mismatch_count",
              "fps_mismatch_count", "size_mismatch_count"):
        assert k in ev
    assert ev["n"] == 50 and ev["n_ok"] == 50 and ev["success_rate"] == 1.0 and ev["p50_open_to_first_frame_ms"] == 400
    assert r["rating"] == "yes"


def test_reliability_mismatch_caps_at_partial():
    s = cycstats.summarize_cycles(_rows("." * 100))
    r = rating.rate_reliability(s, replug_needed=False, format_mismatch_count=12, fps_mismatch_count=0,
                                size_mismatch_count=0)
    assert r["rating"] == "partial"
    c = next(c for c in r["criteria"] if c["criterion"] == "negotiated the requested format")
    assert c["met"] is False
    # fps mismatch alone is recorded but does not cap
    r2 = rating.rate_reliability(s, replug_needed=False, fps_mismatch_count=5, format_mismatch_count=0,
                                 size_mismatch_count=0)
    assert r2["rating"] == "yes" and r2["evidence"]["fps_mismatch_count"] == 5
    # counts read from the summary when not passed
    r3 = rating.rate_reliability(dict(s, size_mismatch_count=1), replug_needed=False)
    assert r3["rating"] == "partial"


def test_reliability_no_latency_vs_failures():
    lat = rating.rate_reliability(cycstats.summarize_cycles(_rows("s" * 15)), replug_needed=False)
    assert lat["rating"] == "no" and lat["summary_label"] == "no (latency)"
    fail = rating.rate_reliability(cycstats.summarize_cycles(_rows("x" * 15)), replug_needed=False)
    assert fail["rating"] == "no" and fail["summary_label"] == "no (failures)"
    rep = rating.rate_reliability(cycstats.summarize_cycles(_rows("." * 10 + "x" * 5)), replug_needed=True)
    assert rep["summary_label"] == "no (replug needed)"


# ------------------------------------------------------------------------------------------------ G-TS
def test_ts_self_consistency_and_monotonic():
    r = rating.rate_ts(None, True, False, tier=1, device_ts_self_consistent=False)
    assert r["rating"] == "untested" and r["note"] == "device timestamps not self-consistent"
    assert rating.rate_ts(None, True, False, device_ts_self_consistent=False, device_ts_monotonic=False)["rating"] \
        == "no"
    assert rating.rate_ts(None, True, False, device_ts_self_consistent=True, device_ts_monotonic=True)["rating"] \
        == "partial"
    # synthesized still 'no' first
    assert rating.rate_ts(None, None, False, synthesized=True, device_ts_self_consistent=False)["rating"] == "no"


# ------------------------------------------------------------------------------------------------ G-BW
def _ev(**kw):
    e = {"label": "x", "predicted_verdict": "over", "observed_refused": True, "classified_class": "bandwidth_certain",
         "message_ports_other_domains": True, "retry_ok": True}
    e.update(kw)
    return e


def test_bw_device_not_ready_excluded():
    evs = [_ev(), _ev(label="#38", predicted_verdict="fits", classified_class="device_not_ready")]
    r = rating.rate_bw(evs)
    assert r["rating"] == "yes"
    assert r["evidence"]["device_not_ready"]["count"] == 1 and r["evidence"]["device_not_ready"]["events"] == ["#38"]
    evs2 = [_ev(), _ev(label="#38", predicted_verdict="fits", classified_class="other", device_not_ready=True)]
    assert rating.rate_bw(evs2)["rating"] == "yes"
    # without the flag the same event is a false fit
    assert rating.rate_bw([_ev(), _ev(predicted_verdict="fits", classified_class="other")])["rating"] == "no"


def test_bw_retry_final_try():
    ok_on_second = _ev(retry_ok=None, retry_tries=[False, True])
    r = rating.rate_bw([ok_on_second])
    assert r["rating"] == "yes" and r["evidence"]["retry"]["first_try_failed_final_ok"] == 1
    bad = _ev(retry_ok=None, retry_tries=[{"ok": True}, {"ok": False}])
    assert rating.rate_bw([bad])["rating"] == "partial"


def test_bw_false_over():
    evs = [_ev(), _ev(label="over-but-fine", observed_refused=False, classified_class=None)]
    r = rating.rate_bw(evs)
    assert r["rating"] == "partial"
    c = next(c for c in r["criteria"] if "false 'over'" in c["criterion"])
    assert c["met"] is False and r["evidence"]["false_over"] == ["over-but-fine"]


def test_bw_label_rule():
    assert rating.label_is_raw("PCIROOT(0)#PCI(1400)#USBROOT(0)#USB(7)") is True
    assert rating.label_is_raw("HS07") is True
    assert rating.label_is_raw("Intel USB 3.20 xHCI, port 7") is False
    assert rating.label_is_raw("port 7 (HS07, Intel USB 3.20 xHCI)") is False   # controller + port number tier
    assert rating.rate_bw([_ev()], labels=["PCIROOT(0)#PCI(1400)#USBROOT(0)#USB(7)"])["rating"] == "partial"
    assert rating.rate_bw([_ev()], labels=["Intel USB 3.20 xHCI, port 7"])["rating"] == "yes"
    # an explicit labels_raw wins
    assert rating.rate_bw([_ev()], labels_raw=False, labels=["HS07"])["rating"] == "yes"


# ------------------------------------------------------------------------------------------------ G-CTRL
_C = {"name": "exposure", "listed": True, "range_matches_descriptor": True, "set_readback_ok": True,
      "effect_ok": True, "before_start_ok": True, "after_start_ok": True, "runs_ok": 3, "runs_total": 3}


def test_ctrl_device_not_answering_is_no():
    r = rating.rate_ctrl([], device_not_answering=True, not_answering_hr="0x8007001F")
    assert r["rating"] == "no" and r["evidence"]["not_answering_hr"] == "0x8007001F"
    assert r["criteria"][0]["criterion"] == "can set a control" and r["criteria"][0]["met"] is False


def test_ctrl_criterion1_fed_not_hard_coded():
    assert rating.rate_ctrl([_C])["rating"] == "yes"
    r = rating.rate_ctrl([dict(_C, range_matches_descriptor=None)])
    assert r["rating"] == "partial" and r["criteria"][0]["met"] is None
    assert rating.rate_ctrl([dict(_C, listed=False)])["rating"] == "partial"
    assert rating.rate_ctrl([dict(_C, range_matches_descriptor=False)])["criteria"][0]["met"] is False


# ------------------------------------------------------------------------------------------------ misc
def test_device_fault_untested_helper():
    r = rating.device_fault_untested({"first_fault_utc": "2026-11-06T18:43:49Z", "test": "W-MJPEG",
                                      "mode": "MJPG 640x360@5", "code": "0x8007001F"})
    assert r["rating"] == "untested" and r["evidence"]["device_fault"] is True
    assert r["note"].startswith("device fault since 2026-11-06T18:43:49Z")
    assert rating.worst([r, "partial"]) == "partial"


def test_id_provisional_flag():
    keys = ["a", "b"]
    r = rating.rate_id({"mf": [keys] * 20}, keys, {"reboot": None, "same_port_replug": None, "port_move_serial": True})
    assert r["rating"] == "partial" and r["provisional"] is True
    r2 = rating.rate_id({"mf": [keys] * 20}, keys, {"reboot": False})
    assert r2["rating"] == "partial" and r2["provisional"] is False
