# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26"]
# ///
"""Unit tests for bands.detect_bands (and the strobe-table / identity helpers). No camera, no files.

Run:  uv run --script research/usb_cameras/timing/rig/test_bands.py        (also collectable by pytest)

Profiles are rendered from the exact rolling-shutter overlap (row r integrates [s0 + r*L, s0 + r*L + E], pulse
[t_rise, t_rise + w]), so the true 50 % edges are r_t = (t_c - E - s0)/L and r_b = (t_c - s0)/L, t_c = t_rise + w/2.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bands import detect_bands  # noqa: E402
import rigio  # noqa: E402
import solve  # noqa: E402


def render(H, L, s0, E, pulses, w=50e3, amp=1.0, echo=None):
    a = s0 + np.arange(H) * L
    p = np.zeros(H)
    for t in pulses:
        p += np.clip(np.minimum(a + E, t + w) - np.maximum(a, t), 0, None) / w
    p *= amp
    if echo is not None:
        p += echo
    return p


def truth_edges(L, s0, E, t, w=50e3):
    tc = t + w / 2
    return (tc - E - s0) / L, (tc - s0) / L


def test_single_band_subrow():
    """Sub-row accuracy over many sub-row positions. With w = 50 us the ramp is w/L rows wide: 1.17 rows at
    L = 42.8 us (C922-like) but only 0.78 rows at L = 64.1 us, where the edge is undersampled and the error grows
    to ~0.11 row (~7 us, zero mean). w = 100 us (ramp 1.56 rows) halves it (~3.6 us). Hence the README's
    advice: strobe width >= 2 L."""
    for L, w, lim_us in ((42_800.0, 50e3, 2.5), (64_100.0, 50e3, 8.0), (64_100.0, 100e3, 4.0)):
        errs = []
        for frac in np.linspace(0, 1, 41):
            s0, E = 0.0, 2e6
            t = (300 + frac) * L + E  # top edge near row 300+frac
            p = render(720, L, s0, E, [t], w=w)
            segs = detect_bands(p, 0.35)
            assert len(segs) == 1, segs
            rt, rb = truth_edges(L, s0, E, t, w=w)
            errs.append((segs[0]["r_top"] - rt, segs[0]["r_bot"] - rb))
        e = np.array(errs)
        mean_us = e.mean(axis=0) * L / 1e3
        max_us = np.abs(e).max(axis=0) * L / 1e3
        print(f"  L={L:.0f} ns w={w / 1e3:.0f} us: edge error mean {mean_us.round(3)} us, max {max_us.round(3)} us (top, bottom)")
        assert np.all(max_us < lim_us), max_us
        assert np.all(np.abs(mean_us) < 0.5), mean_us


def test_clipped_top_and_bottom():
    L, E = 42_800.0, 8e6
    # band hanging off the top: rows from <0 to ~100
    s0 = 0.0
    t = 100 * L
    p = render(720, L, s0, E, [t])
    s = detect_bands(p, 0.35)
    assert len(s) == 1 and s[0]["r_top"] is None and s[0]["clipped_top"] and s[0]["r_bot"] is not None
    _, rb = truth_edges(L, s0, E, t)
    assert abs(s[0]["r_bot"] - rb) < 0.1
    # band hanging off the bottom
    t = 700 * L + E
    p = render(720, L, s0, E, [t])
    s = detect_bands(p, 0.35)
    assert len(s) == 1 and s[0]["r_bot"] is None and s[0]["clipped_bot"] and s[0]["r_top"] is not None
    rt, _ = truth_edges(L, s0, E, t)
    assert abs(s[0]["r_top"] - rt) < 0.1
    # edge closer than 2 rows to the image boundary counts as clipped
    t = 1.2 * L
    p = render(720, L, s0, 0.5e6, [t])
    s = detect_bands(p, 0.35)
    assert all(x["r_top"] is None for x in s)


def test_double_band():
    L, E, gap = 42_800.0, 2e6, 10e6
    s0 = 0.0
    t = 150 * L + E
    p = render(720, L, s0, E, [t, t + gap])
    s = detect_bands(p, 0.35)
    assert len(s) == 2, s
    (rt1, rb1), (rt2, rb2) = truth_edges(L, s0, E, t), truth_edges(L, s0, E, t + gap)
    assert abs(s[0]["r_bot"] - rb1) < 0.1 and abs(s[1]["r_bot"] - rb2) < 0.1
    assert abs(s[0]["r_top"] - rt1) < 0.1 and abs(s[1]["r_top"] - rt2) < 0.1
    Lhat = gap / (s[1]["r_bot"] - s[0]["r_bot"])
    assert abs(Lhat - L) / L < 1e-3, Lhat
    # E > gap: the two bands merge into one stepped segment, which must be flagged
    p = render(720, L, s0, 15e6, [100 * L + 15e6, 100 * L + 15e6 + gap])
    s = detect_bands(p, 0.35)
    assert len(s) == 1 and s[0]["stepped"], s


def test_no_band_in_blanking():
    H, L, E = 720, 42_800.0, 1.9e6
    T = 33.333e6
    s0 = 0.0
    t = s0 + (H - 1) * L + 0.3e6 + 0.0  # after the last row's window opened... choose inside the gap
    t = s0 + (H - 1) * L + E + 0.2e6     # (H-1)L + E < t < T: no row integrates it
    assert t < T
    p = render(H, L, s0, E, [t]) + np.random.default_rng(0).normal(0, 0.01, H)
    assert detect_bands(p, 0.35) == []


def test_echo_band_not_detected_and_measurable():
    H, L, E = 720, 42_800.0, 7e6
    prev = render(H, L, 0.0, E, [200 * L + E])          # frame k band rows ~200..364
    cur = render(H, L, 0.0, E, [520 * L + E], echo=0.08 * prev)  # frame k+1 band elsewhere + 8 % echo
    s = detect_bands(cur, 0.35)
    assert len(s) == 1 and s[0]["r_top"] > 500, s     # echo (8 %) is below threshold, real band found
    from bands import mean_level
    lvl = mean_level(cur, 210, 350)
    assert abs(lvl - 0.08) < 0.005, lvl


def test_noise_robustness():
    rng = np.random.default_rng(1)
    L, E = 42_800.0, 4e6
    errs = []
    for i in range(200):
        t = (100 + 500 * rng.random()) * L + E
        p = render(720, L, 0.0, E, [t], amp=0.3) + rng.normal(0, 0.003, 720)
        s = detect_bands(p, 0.35 * 0.3)
        assert len(s) == 1
        rt, rb = truth_edges(L, 0.0, E, t)
        errs.append((s[0]["r_top"] - rt) * L)
        errs.append((s[0]["r_bot"] - rb) * L)
    e = np.abs(np.array(errs))
    print(f"  noisy edges: median {np.median(e) / 1e3:.2f} us, max {e.max() / 1e3:.2f} us")
    assert e.max() < 20e3


def test_strobe_table_double_labels():
    rises = []
    for j in range(5):
        rises += [1_000_000_000 + j * 33_366_000, 1_000_000_000 + j * 33_366_000 + 10_000_000]
    ev = [{"k": k, "t_rise_ns": r, "t_fall_ns": r + 50_000} for k, r in enumerate(rises) if k != 3]  # one lost event
    st = rigio.strobe_table(ev, 10_000_000)
    assert list(st["pulse"]) == [1, 2, 1, 1, 2, 1, 2, 1, 2], st["pulse"]
    assert st["t_c"][0] == 1_000_025_000


def test_longest_empty_wraps():
    tot = np.array([1, 1, 0, 1, 1, 1, 1, 1])
    hit = np.array([0, 0, 0, 1, 1, 1, 1, 0])  # empty run 7,0,1,(2 bridged) -> trimmed at 2? no: 2 is inside [7..2]
    best, start = solve._longest_empty(tot, hit)
    assert (best, start) == (3, 7), (best, start)  # bins 7,0,1 (bin 2 had no strobe and is trimmed from the end)


def main() -> int:
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"[PASS] {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"[FAIL] {t.__name__}: {e!r}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
