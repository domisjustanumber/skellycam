"""W-MULTI / W-TOPO harness fixes (multi_topo.md bugs per its verifier notes): pure helpers of
windows/tests/w_multi.py and the offline re-analysis of the 2026-11-06 Gerald run. No camera is opened."""
import sys
from pathlib import Path

import pytest

SUITE = Path(__file__).resolve().parents[2]
for _p in (SUITE / "windows", SUITE / "windows" / "helpers", SUITE / "windows" / "tests"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

wm = pytest.importorskip("w_multi")
from common import topology_model as tm  # noqa: E402

RUN = SUITE.parent / "results" / "windows" / "Gerald" / "suite_20261106T181941Z"
GEN, C922 = "gen", "c922"


def test_native_raw_modes_and_pyav_format():
    fm = {"reader_streams": [{"types": [
        {"subtype": "YUY2", "width": 640, "height": 480, "fps_num": 30, "fps_den": 1},
        {"subtype": "YUY2", "width": 1920, "height": 1080, "fps_num": 5, "fps_den": 1},
        {"subtype": "NV12", "width": 1280, "height": 720, "fps_num": 30, "fps_den": 1},   # MF-synthesized
        {"subtype": "MJPG", "width": 1280, "height": 720, "fps_num": 30, "fps_den": 1}]}]}
    raw = wm.native_raw_modes(fm)
    assert ("YUY2", 640, 480, 30.0) in raw and not any(r[0] == "NV12" for r in raw)
    assert wm.pyav_format(raw, 640, 480, 30) == "YUY2"
    assert wm.pyav_format(raw, 1920, 1080, 5) == "YUY2"
    assert wm.pyav_format(raw, 1280, 720, 30) == "MJPG"
    assert wm.mode_fmt_text("MJPG 640x480@30", "YUY2") == "YUY2 640x480@30"


def test_negotiated_format():
    assert wm.negotiated_format("pyav_ds", {"negotiated": {"codec": "mjpeg"}}) == "MJPG"
    assert wm.negotiated_format("pyav_ds", {"negotiated": {"codec": "rawvideo", "pix_fmt": "yuyv422"}}) == "YUY2"
    assert wm.negotiated_format("pyav_ds", {"format_fallback": True}) == "YUY2"
    assert wm.negotiated_format("ds", {}) == "MJPG"


def test_counts_as_refusal_keeps_others_streaming_rule():
    assert wm.counts_as_refusal("bandwidth_probable", False)
    assert wm.counts_as_refusal("other", True)            # unforeseen refusal at a 'fits' prediction still counts
    assert not wm.counts_as_refusal("other", False)
    assert not wm.counts_as_refusal("device_not_ready", True)
    assert not wm.counts_as_refusal("device_error", True)


def _oc(cam, ok, t_start, t_end, code=None, log=None, dom="d1", fmt="MJPG", frames=None, pipe=None, pf="MJPG"):
    return {"camera": cam, "snapshot_key": cam, "ok": ok, "frames": frames if frames is not None else (100 if ok else 0),
            "t_start_s": t_start, "t_end_s": t_end, "code": code, "stage": "open", "timed_out": False,
            "error": {"ffmpeg_log": log} if log else None, "domain": dom, "mode": "MJPG 640x480@30",
            "predicted_format": pf, "predicted_mode": wm.mode_fmt_text("MJPG 640x480@30", pf),
            "observed_format": fmt if ok else None, "observed_pipe": pipe, "predicted_domain_verdict": "over"}


def test_device_gone_and_classification():
    tl = [{"key": GEN, "kind": "arrival", "t": 100.6, "utc": "x"}, {"key": GEN, "kind": "arrival", "t": 210.4,
                                                                      "utc": "y"}]
    assert wm.device_gone(GEN, 100.0, 106.0, tl)["delta_s"] == pytest.approx(0.6)     # slow failure, then arrival
    assert wm.device_gone(GEN, 200.0, 206.0, tl) is None                             # fast refusal: reset at +10.4 s
    oc = _oc(GEN, False, 0.0, 0.6, code="OSError(5)")
    assert wm.classify_camera("ds", oc, True, "over", False)["class"] == "bandwidth_probable"
    slow = _oc(GEN, False, 0.0, 3.87, code="OSError(5)")
    assert wm.classify_camera("ds", slow, True, "fits", False)["class"] == "device_not_ready"
    rs = _oc(GEN, False, 0.0, 0.6, code="OSError(5)", log=[{"msg": "Could not RenderStream to connect pins"}])
    assert wm.classify_camera("pyav_ds", rs, True, "over", False)["class"] == "device_not_ready"
    assert wm.classify_camera("ds", oc, True, "over", True)["class"] == "device_not_ready"
    mf = _oc(C922, False, 0.0, 0.37, code=0x800718CF)
    assert wm.classify_camera("mf", mf, True, "over", True)["class"] == "bandwidth_certain"


def test_arrival_attribution_by_timestamp_not_next_check():
    prev = {"utc": "2026-11-06T19:37:57+00:00", "cameras": {GEN: {"present": True, "last_arrival": "a0"}}}
    now = {"utc": "2026-11-06T19:38:10+00:00",
           "cameras": {GEN: {"present": True, "last_arrival": "2026-11-06T19:38:07.885+00:00"}}}
    evs = wm.arrival_events(prev, now, "run_B")   # seen at the check after run B ...
    assert evs[0]["kind"] == "arrival" and evs[0]["seen_after"] == "run_B"
    t_arr = evs[0]["t"]
    fails = [{"run": "run_A", "api": "ds", "camera": GEN, "where": "run", "t_end": t_arr - 10.4, "utc_end": "a"},
             {"run": "run_B", "api": "ds", "camera": C922, "where": "run", "t_end": t_arr - 3.0, "utc_end": "b"}]
    att = wm.attribute_arrivals(evs, fails)
    assert att[0]["failure"]["run"] == "run_A" and att[0]["delay_s"] == pytest.approx(10.4)   # ... caused by run A
    gone = wm.arrival_events({"utc": "t", "cameras": {GEN: {"present": True, "last_arrival": "a"}}},
                             {"utc": "2026-11-06T19:38:10+00:00", "cameras": {GEN: {"present": False}}}, "x")
    assert [e["kind"] for e in gone] == ["absent"]


def test_build_events_excludes_device_not_ready_and_single_camera_domains():
    a = _oc(C922, True, 0.0, 6.2)
    b = _oc(GEN, False, 0.0, 3.9, code="OSError(5)")
    b["classification"] = wm.classify_camera("ds", b, True, "over", False)
    b["counts_as_refusal"] = wm.counts_as_refusal(b["classification"]["class"], True)
    k = _oc("kiyo", False, 0.0, 0.6, code="OSError(5)", dom="d2", log=[{"msg": "Could not RenderStream"}])
    k["classification"] = wm.classify_camera("ds", k, False, "fits", False)
    k["counts_as_refusal"] = False
    rec = {"api": "ds", "tag": "ds_x_001", "label": "x", "kind": "pair", "stagger_s": 0, "cameras": [a, b, k]}
    pred = {"domains": [{"key": "d1", "verdict": "fits", "members": [C922, GEN], "pct_microframe": 59.7},
                        {"key": "d2", "verdict": "fits", "members": ["kiyo"]}]}
    evs = wm.build_events(rec, pred, None)
    assert len(evs) == 1                                          # the Kiyo alone in its domain is no G-BW event
    ev = evs[0]
    assert not ev["observed_refused"] and ev["device_not_ready"] == [GEN] and ev["excluded_device_not_ready"]
    assert ev["classified_class"] == "device_not_ready" and not ev["all_streamed"]
    from common import rating
    assert rating.rate_bw(evs)["rating"] == "untested"            # no refusal left, so no false 'fits'


def test_effective_requests_on_format_mismatch():
    a = _oc(C922, True, 0.0, 6.2, fmt="YUY2", pipe={"max_packet": 896, "mult": 3})   # predicted MJPG, got YUY2
    b = _oc(GEN, True, 0.0, 6.0)
    reqs, mismatch = wm.effective_requests({"cameras": [a, b]})
    assert mismatch and reqs[0]["mode"] == "YUY2 640x480@30" and reqs[0]["max_packet"] == 896
    a2 = _oc(C922, True, 0.0, 6.2, fmt="YUY2", pf="YUY2")                               # predicted YUY2: no mismatch
    assert not wm.effective_requests({"cameras": [a2, b]})[1]


def test_message_failure_stagger_position():
    a = _oc(C922, True, 0.0, 13.7)
    b = _oc(GEN, False, 5.0, 5.05, code=0x800718CF)
    b["classification"] = tm.classify_failure("windows", 0x800718CF, {"api": "mf"})
    f = wm.message_failure({"stagger_s": 2.5, "cameras": [a, b]}, b)
    # the real start gap between the two colliding cameras (a camera of another domain started between them)
    assert f["stagger_s"] == 5.0 and f["stagger_step_s"] == 2.5
    assert f["loser_position"] == "last" and f["loser"] == GEN
    assert "stagger_s" not in wm.message_failure({"stagger_s": 0.0, "cameras": [a, b]}, b)
    # loser started first: the gap to the next camera of its domain
    a2, b2 = _oc(C922, False, 0.0, 0.4, code=0x800718CF), _oc(GEN, True, 2.5, 9.0)
    a2["classification"] = b["classification"]
    assert wm.message_failure({"stagger_s": 2.5, "cameras": [a2, b2]}, a2)["stagger_s"] == 2.5
    assert wm.start_gap_s({"t_start_s": 7.5}, [{"t_start_s": 0.0}, {"t_start_s": 5.0}]) == 2.5
    assert wm.start_gap_s({"t_start_s": None}, [{"t_start_s": 0.0}]) is None


@pytest.mark.skipif(not (RUN / "W-MULTI.json").exists(), reason="Gerald 2026-11-06 run not present")
def test_reanalyze_gerald_run():
    out = wm.reanalyze(RUN, write=False)
    assert out["original_ratings"] == {"G-BW|all|mf": "yes", "G-BW|all|ds": "no", "G-BW|all|pyav_ds": "no"}
    assert out["ratings"] == {"G-BW|all|mf": "yes", "G-BW|all|ds": "partial", "G-BW|all|pyav_ds": "partial"}
    s = out["summary_by_api"]
    assert (s["mf"]["refusals"], s["ds"]["refusals"], s["pyav_ds"]["refusals"]) == (17, 15, 19)
    assert s["ds"]["device_not_ready_events"] == 3 and s["pyav_ds"]["device_not_ready_events"] == 2
    assert all(s[a]["false_fits"] == 0 for a in s)
    msgs = [m["message"] for m in out["measurements"]["messages"] if m.get("message")]
    assert len(msgs) == 51
    assert not any("access denied" in m or "see details" in m for m in msgs)
    assert all("lower c922 Pro Stream Webcam to 640x480 MJPEG 30 fps" in m for m in msgs
               if "1280x720 MJPEG 30 fps: 40%" in m)
    stag = [m for m in out["measurements"]["messages"] if m.get("kind") == "staggered"]
    # the C922 and the generic camera started 5.0 s apart (the Kiyo started between them; run step 2.5 s)
    assert stag and all("one after another, 5 s apart" in m["message"] for m in stag)
    # timestamp attribution: every fast-refusal reset lands on the run that caused it (~10.4 s later)
    delays = [x["after_failure_s"] for r in out["measurements"]["re_arrivals_by_run"] for x in r["re_arrivals"]
              if x["kind"] == "arrival"]
    assert delays and all(0 <= d <= 11.5 for d in delays)


@pytest.mark.skipif(not (RUN / "W-TOPO" / "snapshot.json").exists(), reason="Gerald 2026-11-06 run not present")
def test_reanalyze_w_topo_gerald_run():
    import w_topo
    out = w_topo.reanalyze(RUN, write=False)
    assert out["original_ratings"]["mapper"] == "partial" and out["ratings"]["mapper"] == "yes"
    hub3 = next(f for f in out["measurements"]["free_ports"] if f["label"].startswith("port 3 of the hub 'USB2.0"))
    assert hub3["socket_evidence_level"] == "header"
    assert all(f["label_tier"] == "controller_port_number" for f in out["measurements"]["free_ports"])
    msg = out["measurements"]["scenarios"]["all_cameras_720p30"]["messages"][0]
    order = [p["label"] for g in msg["suggestions"] for p in g["ports"]]
    assert order[-1].startswith("port 3 of the hub 'USB2.0 Hub'")
    assert not any("user-accessible" in lb for lb in order if "HS05" in lb or "HS15" in lb or "HS09" in lb)
