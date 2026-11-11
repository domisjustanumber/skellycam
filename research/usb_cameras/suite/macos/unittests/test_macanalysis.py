"""Analysis helpers on synthetic rows."""
import macanalysis


def rows_30fps(n=300, jitter_ns=(0, 300_000, 600_000), drop_at=None):
    rows = []
    seq = 0
    for i in range(n):
        if drop_at is not None and i == drop_at:
            seq += 1  # a frame the delegate never saw
        t = 1_000_000_000 + int(i * 1e9 / 30)
        rows.append({"seq": i, "host_ns": t + 5_000_000 + jitter_ns[i % 3], "pts_ns": t, "pts_host_ns": t,
                     "dur_ns": 33_333_333, "cmio_seq": seq})
        seq += 1
    return rows


def test_ts_analysis_clean_pts_and_cmio_drop():
    an = macanalysis.ts_analysis(rows_30fps(drop_at=150), 30.0, {"port_rate_vs_host": 1.00002, "sync_is_host_clock": True})
    assert an["field_presence"]["cmio_seq"] == 1.0
    assert an["pts_monotonic"] and an["pts_self_consistent"]
    assert an["cmio_seq_drops"]["drops"] == 1
    assert abs(an["arrival_minus_pts_ms"]["median"] - 5.3) < 0.5
    assert an["port_clock_ppm_vs_host"] == 20.0
    assert an["drops_detectable"]


def test_ts_analysis_grid_pts():
    rows = rows_30fps()
    for r in rows:  # PTS on a 16 ms host grid (the Windows failure mode)
        r["pts_host_ns"] = (r["pts_host_ns"] // 16_000_000) * 16_000_000
        r.pop("cmio_seq")
    an = macanalysis.ts_analysis(rows, 30.0)
    assert not an["pts_self_consistent"]


def test_eval_cell_and_mode_row():
    jpeg = {"frames": 90, "fps_measured": 29.9, "is_jpeg": True, "sample_kinds": {"block": 90},
            "jpeg": {"strict_valid_fraction": 1.0, "lenient_valid_fraction": 1.0, "sof_match_fraction": 1.0,
                     "header_sha1_set": ["aa"], "n_header_sha1": 1}, "stream": {"active_format_matches": True}}
    pix = {"frames": 90, "fps_measured": 30.0, "is_jpeg": False, "sample_kinds": {"image": 90},
           "cv_pixel_formats": {"420v": 90}, "jpeg": {}, "stream": {"active_format_matches": True}}
    want = {"w": 1280, "h": 720, "fps": 30.0}
    cells = {"nil": macanalysis.eval_cell(pix, want), "dmb1": macanalysis.eval_cell(jpeg, want),
             "empty": macanalysis.eval_cell(jpeg, want)}
    assert cells["nil"]["delivered"] == "pixel_buffer" and cells["dmb1"]["delivered"] == "jpeg_block"
    row = macanalysis.mode_row({"mode_text": "MJPG 1280x720@30", "fps": 30.0, "format_index": 2}, cells)
    assert row["best_variant"] == "dmb1" and row["is_jpeg"] and row["header_sha1_by_api"] == {"dmb1": "aa", "empty": "aa"}
    none = macanalysis.mode_row({"mode_text": "x", "fps": 30.0}, {"nil": cells["nil"]})
    assert none["is_jpeg"] is False


def test_effect_schedule_and_verdicts():
    ranges = {"auto_exposure_mode": {"min": 1, "max": 8, "res": 9, "def": 8, "modes_supported": ["manual", "aperture_priority"]},
              "exposure_time_absolute": {"min": 3, "max": 2047, "res": 1}, "gain": {"min": 0, "max": 255, "res": 1},
              "white_balance_temperature": {"min": 2800, "max": 6500, "res": 10},
              "white_balance_temperature_auto": {"min": 0, "max": 1, "res": 1},
              "focus_absolute": {"min": 0, "max": 250, "res": 5}, "focus_auto": {"min": 0, "max": 1}}
    sched, groups, total = macanalysis.build_effect_schedule(ranges, {"auto_exposure_mode": 8, "focus_auto": 1})
    assert [g for g, _ in groups] == ["exposure", "gain", "white_balance", "focus"]
    assert "ep0:auto_exposure_mode=1" in sched and sched.rstrip().endswith("focus_auto=1")
    assert total > 10000
    # synthetic: luma follows exposure
    events, rows = [], []
    t = 0
    for i, v in enumerate([3, 32, 333]):
        events.append({"kind": "ep0", "name": "exposure_time_absolute", "value": str(v), "host_ns_before": t,
                       "host_ns_after": t + 1, "result": {"readback_matches": True, "ok": True}})
        for k in range(45):
            rows.append({"host_ns": t + int(k * 33e6), "metrics": {"luma": 20 + v * 0.3}})
        t += int(1.5e9)
    steps = macanalysis.step_medians(rows, events, "exposure_time_absolute", "luma")
    assert [s["value"] for s in steps] == [3, 32, 333] and all(s["n"] > 10 for s in steps)
    assert macanalysis.effect_verdict(steps, "exposure")["effect_ok"] is True
    flat = [dict(s, median=50.0) for s in steps]
    assert macanalysis.effect_verdict(flat, "exposure")["effect_ok"] is False
    assert macanalysis.effect_verdict([{"value": 0, "median": 1.0}, {"value": 100, "median": 2.0}], "focus")["effect_ok"]


def test_refusal_signal():
    assert macanalysis.refusal_signal({"frames": 0}, 30)["signal"] == "zero_frames"
    assert macanalysis.refusal_signal({"frames": 100, "fps_measured": 15.0}, 30)["signal"] == "reduced_fps"
    err = {"frames": 3, "runtime_errors": [{"error": {"code": -11819, "iokit_codes": ["0xE00002EC"]}}]}
    s = macanalysis.refusal_signal(err, 30)
    assert s["signal"] == "runtime_error" and s["code"] == "0xE00002EC"
    assert macanalysis.refusal_signal({"frames": 100, "fps_measured": 29.9}, 30)["refused"] is False
    assert macanalysis.refusal_signal({}, 30, timed_out=True)["signal"] == "hang"


def test_capture_summary_block_of_pixels_is_not_jpeg():
    """A CMBlockBuffer carrying uncompressed pixels (soi False on every frame) must not count as JPEG bytes."""
    from types import SimpleNamespace
    import mac_avf
    rows = [{"kind": "block", "host_ns": 1_000_000_000 + i * 33_333_333, "soi": False, "eoi": False, "bytes": 1000,
             "strict_ok": False, "lenient_ok": False} for i in range(10)]
    rec = SimpleNamespace(rows=rows, kinds={"block": 10}, subtypes={"2vuy": 10}, cv_formats={}, dropped=[],
                          t_first_host=None, errors=[], stats={})
    st = SimpleNamespace(info={"requested_format": {"w": 640, "h": 480}}, notes=[])
    s = mac_avf._capture_summary(rec, st, 1.0, 0.0, {})
    assert s["is_jpeg"] is False and s["soi_fraction"] == 0.0
    for r in rows:
        r.update(soi=True, eoi=True, sof0_w=640, sof0_h=480, strict_ok=True, lenient_ok=True)
    s = mac_avf._capture_summary(rec, st, 1.0, 0.0, {})
    assert s["is_jpeg"] is True and s["jpeg"]["sof_match_fraction"] == 1.0


def test_cmio_invalid_sequence_is_none():
    import mac_avf

    class C:
        def CMIOSampleBufferGetSequenceNumber(self, p):
            return mac_avf.CMIO_INVALID_SEQ

        def CMIOSampleBufferGetDiscontinuityFlags(self, p):
            return 0

    saved = dict(mac_avf.FW)
    try:
        mac_avf.FW["cmio_c"] = C()
        mac_avf.FW["objc"] = None
        obj = type("O", (), {"__pointer__": 1234})()
        assert mac_avf.cmio_seq(obj) == (None, 0)
    finally:
        mac_avf.FW.clear()
        mac_avf.FW.update(saved)
