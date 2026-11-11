"""common/nograb.py (FMT-NOGRAB completeness / disturbance / blocking) and rating.rate_fmt_nograb."""
from __future__ import annotations

from common import nograb as ng
from common import rating

IV30, IV15, IV5 = 333333, 666667, 2000000
REF = {("MJPG", 1280, 720, IV30), ("MJPG", 1280, 720, IV15), ("MJPG", 1920, 1080, IV30),
       ("YUY2", 640, 480, IV30), ("YUY2", 640, 480, IV5), ("H264", 1280, 720, IV30)}


def test_fourcc_classes_and_aliases():
    assert ng.fmt_class("mjpeg") == "mjpeg" and ng.fmt_class("MJPG") == "mjpeg"
    assert ng.fmt_class("yuyv422") == "raw" and ng.norm_fourcc("yuyv422") == "YUY2"
    assert ng.fmt_class("NV12") == "raw" and ng.fmt_class("H264") == "other"
    assert ng.fmt_class("MFVideoFormat_H264") == "other"
    assert ng.interval_from_fps(30) == IV30 and ng.interval_from_fps(7.5) == 1333333


def test_compare_complete_exact_and_missing_rates():
    c = ng.compare(REF, set(REF))
    assert c["complete"] and c["exact"] and c["required_classes"] == ["mjpeg", "raw"]
    # H.264 missing: "other" is not required
    c = ng.compare(REF, {m for m in REF if m[0] != "H264"})
    assert c["complete"] and c["per_class"]["other"]["n_missing"] == 1
    # a raw rate missing (sizes all present): incomplete, rates_only_missing
    c = ng.compare(REF, REF - {("YUY2", 640, 480, IV5)})
    assert not c["complete"] and c["per_class"]["raw"]["missing"] == ["YUY2 640x480@5"]
    assert c["per_class"]["raw"]["rates_only_missing"] is True and c["per_class"]["mjpeg"]["complete"]
    # extra mode: complete but not exact
    c = ng.compare(REF, set(REF) | {("MJPG", 640, 480, IV30)})
    assert c["complete"] and not c["exact"] and c["per_class"]["mjpeg"]["n_extra"] == 1
    # nothing returned
    c = ng.compare(REF, None)
    assert not c["complete"] and c["listed_none"]
    # empty reference never counts as complete
    assert not ng.compare(set(), set(REF))["complete"]


def test_compare_tolerances():
    listed = {("MJPG", 1280, 720, IV30 + 2), ("MJPG", 1280, 720, IV15), ("MJPG", 1920, 1080, IV30),
              ("yuyv422", 640, 480, IV30), ("YUY2", 640, 480, IV5)}
    assert ng.compare(REF, listed)["complete"]            # 2 x 100 ns within TOL_100NS, alias normalised
    off = {("MJPG", 1280, 720, 1333333)}
    ref = {("MJPG", 1280, 720, 1333333 + 1000)}           # 7.5 fps printed with few digits (ffmpeg)
    assert not ng.compare(ref, off)["complete"]
    assert ng.compare(ref, off, rel_tol=ng.REL_TOL)["complete"]


def _ts(start_ms: float, n: int, period_ms: float = 33.333, gap_at: int | None = None, gap_ms: float = 0.0):
    out, t = [], start_ms
    for i in range(n):
        if gap_at is not None and i == gap_at:
            t += gap_ms
        out.append(int(t * 1e6))
        t += period_ms
    return out


def test_disturbance_clean_gap_stop_and_bad_frames():
    ts = _ts(0, 300)                                       # 10 s at 30 fps
    w = (int(4000e6), int(6500e6))
    d = ng.disturbance(ts, w)
    assert d["disturbed"] is False and d["frames_in_window"] > 60 and d["baseline_frames"] > 50
    # a 300 ms stall inside the window
    d = ng.disturbance(_ts(0, 300, gap_at=150, gap_ms=300), w)
    assert d["disturbed"] is True and "gap" in d["why"] and d["window_max_interval_ms"] > 300
    # the stream ends inside the window (no frame after it)
    d = ng.disturbance([t for t in ts if t < 5_000_000_000], w)
    assert d["disturbed"] is True and "stream_stopped" in d["why"]
    # one bad frame in the window
    d = ng.disturbance(ts, w, bad_frame_ts_ns=[5_000_000_000])
    assert d["disturbed"] is True and d["bad_frames_in_window"] == 1
    # nothing to measure
    assert ng.disturbance([], w)["disturbed"] is None


def test_blocked_and_stream_started():
    assert ng.blocked(True, True) is False
    assert ng.blocked(True, False) is True
    assert ng.blocked(True, True, first_frame_after_release=True) is True
    assert ng.blocked(False, False) is None                # control failed too: not testable
    assert ng.blocked(True, None) is None
    assert ng.stream_started([{"active": False}, {"active": False}]) is False
    assert ng.stream_started([{"active": False}, {"active": True}]) is True
    assert ng.stream_started([{"error": "x"}]) is None
    assert ng.stream_started([{"active": True}], baseline_active=True) is None


# ---------------------------------------------------------------------------------------------------- rating
def _c(**kw):
    base = {"tested": True, "succeeded": True, "complete": True, "disturbed": None, "stream_started": None,
            "blocked": None, "elapsed_s": 0.1}
    base.update(kw)
    return base


def _all_good():
    return {"idle": _c(stream_started=False, blocked=False),
            "streaming_native": _c(disturbed=False), "streaming_second_api": _c(disturbed=False)}


def test_rate_yes():
    r = rating.rate_fmt_nograb(_all_good(), method="mf")
    assert r["rating"] == "yes" and all(c["met"] for c in r["criteria"])


def test_rate_partial_idle_only_disturbs_blocks():
    c = _all_good()
    c["streaming_second_api"] = _c(succeeded=False, complete=False, disturbed=False)
    r = rating.rate_fmt_nograb(c)
    assert r["rating"] == "partial" and r["summary_label"] == "partial (idle only)"
    c = _all_good()
    c["streaming_native"]["disturbed"] = True
    r = rating.rate_fmt_nograb(c)
    assert r["rating"] == "partial" and r["summary_label"] == "partial (disturbs)"
    c = _all_good()
    c["idle"]["blocked"] = True
    r = rating.rate_fmt_nograb(c)
    assert r["rating"] == "partial" and r["summary_label"] == "partial (blocks)"


def test_rate_no_incomplete_or_needs_stream():
    c = _all_good()
    c["idle"]["complete"] = False
    r = rating.rate_fmt_nograb(c)
    assert r["rating"] == "no" and r["summary_label"] == "no (incomplete)"
    c = _all_good()
    c["idle"]["stream_started"] = True
    r = rating.rate_fmt_nograb(c)
    assert r["rating"] == "no" and r["summary_label"] == "no (needs a stream)"
    r = rating.rate_fmt_nograb({}, no_reason="cannot list without opening capture", method="opencv")
    assert r["rating"] == "no" and r["no_reason"].startswith("cannot list") and r["summary_label"].startswith("no")
    c = _all_good()
    c["idle"]["succeeded"] = False
    c["idle"]["complete"] = False
    assert rating.rate_fmt_nograb(c)["summary_label"] == "no (failed)"


def test_rate_provisional_and_untested():
    c = _all_good()
    c["streaming_second_api"] = {"tested": False, "untested_reason": "streamer did not start"}
    r = rating.rate_fmt_nograb(c)
    assert r["rating"] == "partial" and r.get("provisional") and "streamer did not start" in r["note"]
    c = _all_good()
    c["idle"]["stream_started"] = None           # pipes not sampled
    r = rating.rate_fmt_nograb(c)
    assert r["rating"] == "partial" and "stream / bandwidth not measured" in r["note"]
    r = rating.rate_fmt_nograb({"idle": {"tested": False, "untested_reason": "untested: device fault since t"}})
    assert r["rating"] == "untested"
    # a condition missing entirely counts as not run
    c = _all_good()
    del c["streaming_native"]
    assert rating.rate_fmt_nograb(c)["rating"] == "partial"
