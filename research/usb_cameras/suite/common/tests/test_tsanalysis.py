"""Timestamp analysis on synthetic data (deterministic pseudo-random jitter)."""
import math
import random

import pytest

from common import tsanalysis as ts

P = 1e9 / 30


def _arrivals(n=600, jitter_ms=0.3, drop_every=None, latency_ms=20.0, seed=1):
    rnd = random.Random(seed)
    cap, arr = [], []
    for i in range(n):
        if drop_every and i % drop_every == drop_every - 1:
            continue
        c = 5e9 + i * P
        cap.append(c)
        arr.append(c + latency_ms * 1e6 + abs(rnd.gauss(0, jitter_ms * 1e6)))
    return cap, arr


def test_grid_detects_16ms_quantisation():
    _, arr = _arrivals()
    q = [math.floor(a / 16e6) * 16e6 for a in arr]          # host-time grid of 16 ms
    g = ts.grid_analysis(q)
    assert g["quantized"] and g["step_ms"] == pytest.approx(16.0) and g["known_step"] == "16ms"
    q2 = [math.floor(a / 15.625e6) * 15.625e6 for a in arr]  # 64 Hz Windows timer
    g2 = ts.grid_analysis(q2)
    assert g2["quantized"] and g2["step_ms"] == pytest.approx(15.625)


def test_grid_clean_stream_not_quantized():
    _, arr = _arrivals(jitter_ms=0.2)
    g = ts.grid_analysis(arr)
    assert not g["quantized"]
    assert g["interval_ms"]["median"] == pytest.approx(33.33, abs=0.5)
    _, arr_d = _arrivals(jitter_ms=0.05, drop_every=10)
    g2 = ts.grid_analysis(arr_d, nominal_period_ns=P)
    assert not g2["quantized"] and g2.get("period_multiples")


def test_frame_index_fit_whole_run_and_causal():
    cap, arr = _arrivals(drop_every=25)
    f = ts.fit_frame_index(arr, causal=False)
    assert f["period_ns"] == pytest.approx(P, rel=1e-4)
    assert f["slots_skipped"] == 600 // 25 - 1      # the last frame (599) is dropped: not a gap
    err = ts.score_against_truth(f["fitted_ns"], cap)
    assert err["error_ms"]["std"] < 0.1             # the fit removes the arrival jitter
    fc = ts.fit_frame_index(arr, causal=True, min_points=30)
    assert fc["n_estimated"] == len(arr) - 29
    errc = ts.score_against_truth(fc["fitted_ns"], cap)
    assert errc["error_ms"]["std"] < 0.5
    # quantised arrivals (16 ms grid) are still fitted
    q = [math.floor(a / 16e6) * 16e6 for a in arr]
    fq = ts.fit_frame_index(q, causal=False)
    assert fq["period_ns"] == pytest.approx(P, rel=1e-3)


def test_device_clock_with_wrap():
    hz = 30e6
    n = 400
    start = (1 << 32) - 2_000_000                   # wraps a few frames in
    pts = [int(start + i * hz / 30 * (1 + 50e-6)) % (1 << 32) for i in range(n)]   # +50 ppm device clock
    host = [1e9 + i * P + 10e6 + (i % 7) * 1e4 for i in range(n)]
    c = ts.fit_device_clock(pts, host, hz, causal=False)
    assert c["monotonic"]
    assert c["ppm_vs_nominal"] == pytest.approx(50, abs=2)
    assert c["residual_stats_ms"]["std"] < 0.05
    cc = ts.fit_device_clock(pts, host, hz, causal=True)
    assert sum(1 for m in cc["mapped_ns"] if m is not None) == n - 29
    z = ts.fit_device_clock([0] * 50, host[:50], hz)
    assert "error" in z


def test_detect_drops():
    seq = [0, 1, 2, 5, 6, 6, 7, 10]
    d = ts.detect_drops(seq)
    assert d["drops"] == 2 + 2 and d["duplicates"] == 1 and d["max_gap"] == 2
    t = [i * P for i in (0, 1, 2, 4, 5, 9)]
    d2 = ts.detect_drops(t, P)
    assert d2["drops"] == 1 + 3
    w = [(1 << 32) - 2, (1 << 32) - 1, 0, 2]
    d3 = ts.detect_drops(w, None, bits=32)
    assert d3["drops"] == 1 and d3["backwards"] == 0


def test_stats_and_unwrap():
    s = ts.stats([1, 2, 3, 4])
    assert s["mean"] == 2.5 and s["median"] == 2.5 and s["n"] == 4
    assert ts.unwrap([2040, 2047, 3, 10], bits=11) == [2040, 2047, 2051, 2058]


# ------------------------------------------------------------------ fixes from analysis ts.md (2026-11-06 run)
def _gridded(period_ns, n, grid_ns=16e6, latency_ns=3e6, start=1e9, drop=()):
    """Arrivals of a camera at ``period_ns`` quantised on a host grid (rounded up to the next 16 ms tick)."""
    out = []
    for i in range(n):
        if i in drop:
            continue
        c = start + i * period_ns + latency_ns
        out.append(math.ceil(c / grid_ns) * grid_ns)
    return out


def test_frame_index_real_rate_differs_from_nominal():
    # generic camera: 25.7 fps in a "30 fps" mode, arrivals on a 16 ms grid (the fit used to lock to 30.7 fps)
    arr = _gridded(1e9 / 25.7, 772)
    f = ts.fit_frame_index(arr, causal=False, nominal_period_ns=P)
    assert f["fps"] == pytest.approx(25.7, rel=2e-4)
    assert f["slots_skipped"] == 0 and f["duplicate_slots"] == 0 and not f["fit_unreliable"]
    assert f["slotting"] == "sequence" and f["residual_stats_ms"]["std"] < 5.5
    assert f["rate_vs_nominal_ppm"] == pytest.approx(-143_000, rel=0.01)
    fc = ts.fit_frame_index(arr, causal=True, nominal_period_ns=P)
    assert fc["fps"] == pytest.approx(25.7, rel=2e-3)


def test_frame_index_plus_730ppm_sawtooth():
    # C930e: 900 frames at +730 ppm on the 32/48 ms sawtooth (the fit used to lock to 33.43 ms, 31/35 bad slots)
    arr = _gridded(P / 1.00073, 900)
    f = ts.fit_frame_index(arr, causal=False, nominal_period_ns=P)
    assert f["fps"] == pytest.approx(30 * 1.00073, rel=1e-4)
    assert f["slots_skipped"] == 0 and f["duplicate_slots"] == 0 and not f["fit_unreliable"]


def test_frame_index_drop_found_with_measured_period():
    arr = _gridded(1e9 / 25.7, 600, drop=(100, 101, 400))   # a 2-frame and a 1-frame drop at 25.7 fps
    f = ts.fit_frame_index(arr, causal=False, nominal_period_ns=P)
    assert f["slotting"] == "incremental"
    assert f["slots_skipped"] == 3 and f["fps"] == pytest.approx(25.7, rel=2e-4)
    assert f["drops_detectable"] is True


def test_frame_index_60fps_on_16ms_grid_uses_whole_span():
    # 60 fps on a 16 ms grid: 16/32 ms intervals; 32 ms is not a drop, and drops are not detectable
    arr = _gridded(1e9 / 60, 600)
    f = ts.fit_frame_index(arr, causal=False, nominal_period_ns=1e9 / 60)
    assert f["drops_detectable"] is False and f["slotting"] == "sequence"
    assert f["slots_skipped"] == 0 and f["fps"] == pytest.approx(60, rel=1e-3)


def test_slot_frames_rejects_phantom_gaps():
    # a late frame (1.6 periods) then an early one: incremental slotting would add a permanent phantom slot
    t = [i * P for i in range(300)]
    t[150] += 0.6 * P
    t[151] += 0.55 * P
    s = ts.slot_frames(t, grid_ms=0.0)
    assert s["slots"][-1] == 299 and s["slotting"].startswith("sequence")


def test_synthesized_check():
    rnd = random.Random(3)
    arr = [1e9 + i * P + rnd.choice((0, 16e6)) for i in range(900)]
    pts = [i * 33_333_300.0 for i in range(900)]                       # one constant step: synthesized
    assert ts.synthesized_check(pts, arr)["synthesized"] is True
    # two distinct steps, 67 % modal (like the C930e DS pts: 333333 / 333283 x 100 ns): still synthesized
    pts2 = [0.0]
    for i in range(1, 900):
        pts2.append(pts2[-1] + (33_328_300 if i % 3 == 0 else 33_333_300))
    c2 = ts.synthesized_check(pts2, arr)
    assert c2["synthesized"] is True and c2["distinct_intervals"] == 2 and c2["modal_share"] < 0.9
    # nominal-rate counter while the camera runs at 25.7 fps: drift +143 ms/s
    arr3 = [1e9 + i * 1e9 / 25.7 for i in range(700)]
    pts3 = [i * 33_338_300.0 + (i % 5) * 1e5 for i in range(700)]     # uneven, but drifting: still not a clock
    c3 = ts.synthesized_check(pts3, arr3)
    assert c3["synthesized"] is True and c3["drift_ms_per_s"] == pytest.approx(143, abs=2)
    # a real jittery clock that tracks arrival is not synthesized
    real = [a - 5e6 + rnd.gauss(0, 3e5) for a in arr]
    assert ts.synthesized_check(real, arr)["synthesized"] is False
    assert ts.synthesized_check(pts, None)["synthesized"] is None


def test_modes_report_bimodal_no_median():
    vals = [0.3 + 0.01 * (i % 7) for i in range(526)] + [16.3 + 0.01 * (i % 5) for i in range(376)]
    m = ts.modes_report(vals)
    assert m["n_modes"] == 2 and m["multimodal"]
    assert [round(x["share"], 3) for x in m["modes"]] == [0.583, 0.417]
    assert "median" not in m


def test_grid_fallback_ambiguity_uses_nominal():
    # 125 us microframe grid at 30 fps (fallback branch: one interval cluster). The median interval of gridded
    # times is a whole number of steps (ratio integer -> "ambiguous"); against the nominal 33.33 ms it is not.
    rnd = random.Random(7)
    t = [math.floor((1e9 + i * P + rnd.gauss(0, 0.03e6)) / 0.125e6) * 0.125e6 for i in range(300)]
    g = ts.grid_analysis(t, nominal_period_ns=P)
    assert g["known_step"] == "0.125ms_usb_microframe" and g["on_grid_fraction"] is None
    assert g["ambiguous_with_period"] is False
    g0 = ts.grid_analysis(t)
    assert g0["ambiguous_with_period"] is True


def test_uvc_scr_and_units_helpers_removed():
    # tier 0 only (Dom 2026-11-09): no UVC SCR / SOF / device-counter units analysis is left in common
    for name in ("analyse_uvc_scr", "sof_rate", "clock_units_check", "regularity"):
        assert not hasattr(ts, name), name
