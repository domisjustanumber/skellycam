"""common/modescope.py: the streaming-test mode scope (exactly 720 lines at >= 30 fps unless --all-modes)."""
from __future__ import annotations

import argparse
from types import SimpleNamespace

from common import modescope as ms

# Gerald's C922 MJPEG list (subset): (w, h, fps)
C922 = [(1920, 1080, 30.0), (1920, 1080, 24.0), (1920, 1080, 5.0), (1600, 896, 30.0), (1280, 720, 60.0),
        (1280, 720, 30.0), (1280, 720, 15.0), (960, 720, 30.0), (800, 600, 30.0), (640, 480, 30.0), (640, 480, 5.0)]
C922_IN_SCOPE = [(1280, 720, 60.0), (1280, 720, 30.0), (960, 720, 30.0)]


def test_in_scope_thresholds_and_tolerance():
    assert ms.in_scope(1280, 720, 30)
    assert ms.in_scope(960, 720, 30)                 # 720 lines counts, whatever the width
    assert ms.in_scope(1280, 720, 60)
    assert not ms.in_scope(1920, 1080, 60)           # Dom 2026-11-08: exactly 720 lines by default
    assert not ms.in_scope(1600, 896, 30)
    assert not ms.in_scope(640, 480, 30)
    assert not ms.in_scope(1280, 720, 24)
    assert ms.in_scope(1280, 720, 29.97)             # NTSC rate: within the 0.5 % tolerance
    assert ms.in_scope(1280, 720, 1e7 / 333334)      # interval rounding
    assert not ms.in_scope(1280, 720, 29.8)
    assert not ms.in_scope(1280, 720, None)
    assert not ms.in_scope(None, None, 30)
    # the 2026-11-06 rule (>= 720 lines) through max_height 0
    assert ms.in_scope(1920, 1080, 30, max_height=0)
    assert not ms.in_scope(1920, 1080, 25, max_height=0)
    # an explicit window below the default bound
    assert ms.in_scope(640, 480, 15, min_fps=15, min_height=480)
    assert not ms.in_scope(1280, 720, 30, min_fps=15, min_height=480, max_height=480)
    # a bound below min_height is raised to it: --min-height 1080 alone = exactly 1080 lines
    assert ms.in_scope(1920, 1080, 30, min_height=1080)
    assert not ms.in_scope(1280, 720, 30, min_height=1080)


def test_shim_style_calls_get_the_720_bound():
    """The Linux and macOS shims call in_scope(w, h, fps, min_fps=..., min_height=...) without max_height."""
    assert ms.in_scope(1280, 720, 30.0, min_fps=30.0, min_height=720)
    assert not ms.in_scope(1920, 1080, 30.0, min_fps=30.0, min_height=720)


def test_split_and_record_on_tuples_dicts_and_objects():
    kept, excl = ms.split(C922)
    assert kept == C922_IN_SCOPE
    assert len(excl) == len(C922) - 3
    dicts = [{"width": w, "height": h, "fps": f} for w, h, f in C922]
    assert len(ms.filter_modes(dicts)) == 3
    objs = [SimpleNamespace(w=w, h=h, fps=f, text=f"MJPG {w}x{h}@{f:g}") for w, h, f in C922]
    k2 = ms.filter_modes(objs)
    rec = ms.record(ms.DEFAULT, objs, k2)
    assert rec["advertised"] == 11 and rec["in_scope"] == 3 and rec["excluded"] == 8
    sc = rec["scope"]
    assert sc["min_fps"] == 30 and sc["min_height"] == 720 and sc["max_height"] == 720 and sc["all_modes"] is False
    assert sc["text"] == "exactly 720 lines at >= 30 fps"
    assert "no exception" in sc["raw_formats"]
    assert "MJPG 640x480@30" in rec["excluded_modes"] and "MJPG 1920x1080@30" in rec["excluded_modes"]
    assert "MJPG 1280x720@30" in rec["in_scope_modes"]
    # fourcc tuples and interval dicts
    assert ms.mode_in(("MJPG", 1280, 720, 30.0))
    assert ms.mode_in({"w": 1280, "h": 720, "interval_100ns": 333333})
    assert not ms.mode_in(("YUY2", 1920, 1080, 5.0))


def test_all_modes_and_args():
    assert ms.filter_modes(C922, ms.ALL) == C922
    ap = ms.add_args(argparse.ArgumentParser())
    a = ap.parse_args([])
    sc = ms.from_args(a)
    assert sc == ms.Scope(30.0, 720, False, 720) == ms.Scope(30.0, 720, False) == ms.DEFAULT
    a = ap.parse_args(["--min-fps", "15", "--min-height", "480"])
    assert ms.from_args(a).contains(640, 480, 15) and not ms.from_args(a).contains(640, 360, 30)
    assert ms.from_args(a).contains(1280, 720, 30)           # 480..720 lines
    assert ms.from_args(a).text == ">= 15 fps and 480-720 lines"
    a = ap.parse_args(["--max-height", "0"])
    assert ms.from_args(a).contains(1920, 1080, 30) and ms.from_args(a).text == ">= 30 fps and >= 720 lines"
    assert ms.from_args(a).as_dict()["max_height"] is None
    a = ap.parse_args(["--all-modes"])
    assert ms.from_args(a).contains(160, 90, 5)
    assert ms.from_args(None) == ms.DEFAULT
    assert ms.from_args(SimpleNamespace()) == ms.DEFAULT     # missing attributes -> defaults
    assert ms.from_args(SimpleNamespace(min_fps=30, min_height=720)) == ms.DEFAULT
    assert "all modes" in ms.ALL.text


def test_sort_nearest_partner():
    kept = ms.filter_modes(C922)
    assert ms.sort_modes(kept)[0] == (1280, 720, 60.0)
    assert ms.nearest(kept, 1280, 720, 30) == (1280, 720, 30.0)
    # default 720p30 -> largest other in-scope size at ~30 fps
    assert ms.partner(kept, (1280, 720, 30.0)) == (960, 720, 30.0)
    wide = ms.filter_modes(C922, ms.Scope(max_height=0))
    assert ms.partner(wide, (1280, 720, 30.0)) == (1920, 1080, 30.0)
    # only one size in scope (the Kiyo restricted to 720p): the same size at another rate
    assert ms.partner([(1280, 720, 30.0), (1280, 720, 60.0)], (1280, 720, 30.0)) == (1280, 720, 60.0)
    assert ms.partner([(1280, 720, 30.0)], (1280, 720, 30.0)) is None
    assert ms.partner(kept, None) is None
    assert ms.nearest([], 1280, 720, 30) is None


def test_no_scope_reason_mentions_flags():
    r = ms.no_scope_mode_reason(ms.DEFAULT, 7)
    assert r.startswith("untested (scope)") and "--all-modes" in r and "--max-height 0" in r and "7" in r
    assert "exactly 720 lines" in r
    assert "YUY2" in ms.no_scope_mode_reason(ms.DEFAULT, 3, fmt="YUY2")
