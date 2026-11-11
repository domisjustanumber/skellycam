"""W-MULTI under the mode scope, offline (no camera): in-scope pair modes, the per-pair predicted verdicts and the
"fits-side not testable under mode scope" note; a camera without an in-scope mode is rated untested (scope).

    uv run --isolated --python 3.12 --no-project --with pytest pytest suite/windows/tests/test_multi_scope_offline.py \
        -c suite/common/tests/pytest.ini
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
WIN = HERE.parent
for p in (str(WIN.parent), str(WIN), str(WIN / "helpers"), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import capkit as ck  # noqa: E402
import w_multi  # noqa: E402

M = ck.Mode
C922 = [M(1920, 1080, 30, 1), M(1920, 1080, 5, 1), M(1600, 896, 30, 1), M(1280, 720, 60, 1), M(1280, 720, 30, 1),
        M(960, 720, 30, 1), M(640, 480, 30, 1), M(640, 480, 5, 1)]
GENERIC = [M(1920, 1080, 30, 1), M(1280, 720, 30, 1), M(640, 480, 30, 1)]
SMALL = [M(640, 480, 30, 1), M(320, 240, 30, 1)]          # nothing in scope
CAMS = [{"key": "c922", "name": "C922", "vid": "046d", "pid": "085c"},
        {"key": "generic", "name": "USB Camera", "vid": "4c4a", "pid": "4a55"},
        {"key": "tiny", "name": "Tiny", "vid": "1234", "pid": "0001"}]
MODES = {"c922": C922, "generic": GENERIC, "tiny": SMALL}


class FakeCtx:
    def __init__(self, tmp_path, all_modes=False, max_height=720):
        self.cameras = CAMS
        self.out_dir = tmp_path / "out"
        self.raw_dir = tmp_path / "raw"
        self.out_dir.mkdir(parents=True)
        self.args = types.SimpleNamespace(quick=True, multi_reps=1, min_fps=30, min_height=720, all_modes=all_modes,
                                          max_height=max_height)
        self.wincam = Path("wincam.exe")
        self.logs = []

    def log(self, m):
        self.logs.append(m)

    def arrivals(self):
        return {"cameras": {c["key"]: {"present": True, "last_arrival": None} for c in self.cameras}}


class FakeMulti:
    """Every camera in one high-speed domain; any pair with the C922 is predicted 'over' unless A runs 640x480."""

    def __init__(self, ctx, snap, desc, cache, work, raw, raw_modes):
        self.domain_of = {c["key"]: "hs|ctrl|HS13" for c in CAMS}
        self.skey = {c["key"]: c["key"] for c in CAMS}
        self.learned, self.sets = [], []
        self.runs, self.events, self.messages, self.timeline, self.failures = [], {}, [], [], []
        self.retry_used, self.reenum, self.settle_waits, self.faults, self.fault_log = {}, set(), [], {}, []

    def learn(self, plan, secs):
        self.learned += [(c["key"], m.text) for c, m in plan]
        return {}

    def predict(self, plan, api="mf"):
        a = plan[0][1]
        verdict = "fits" if (a.w, a.h) == (640, 480) else "over"
        return {"domains": [{"key": "hs|ctrl|HS13", "verdict": verdict}], "conflicts": []}

    def run_set(self, api, plan, secs, stagger, label, kind):
        self.sets.append((api, kind, label, [(c["key"], m.text) for c, m in plan]))

    def reprobe_faults(self, dflt, api):
        return None

    def poll_arrivals(self, tag):
        return []


@pytest.fixture
def patched(monkeypatch):
    monkeypatch.setattr(ck, "get_formats", lambda ctx, cam, cache=None: ({"key": cam["key"]}, {}))
    monkeypatch.setattr(ck, "mjpeg_modes", lambda fm: list(MODES[fm["key"]]))
    monkeypatch.setattr(w_multi, "native_raw_modes", lambda fm: set())
    monkeypatch.setattr(w_multi, "_find_descriptors", lambda ctx: None)
    monkeypatch.setattr(w_multi, "_snapshot", lambda desc: {"devices": [], "cameras": []})
    monkeypatch.setattr(w_multi.tm, "compute_domains", lambda snap: [])
    monkeypatch.setattr(w_multi, "Multi", FakeMulti)
    return monkeypatch


def test_pairs_use_in_scope_modes_and_fits_side_note(tmp_path, patched):
    res = w_multi.run(FakeCtx(tmp_path))
    m = res["measurements"]
    pairs = m["pairs"]
    assert len(pairs) == 1                                        # tiny has no in-scope mode: never paired
    p = pairs[0]
    assert p["A"] == "c922" and p["B"] == "generic"
    # default, switch partner (largest other size at ~30), fastest, smallest in-scope size (exactly 720 lines,
    # Dom 2026-11-08: the switch partner and the smallest size are both 960x720@30)
    assert p["a_modes"] == ["MJPG 1280x720@30", "MJPG 960x720@30", "MJPG 1280x720@60"]
    assert all(v == "over" for v in p["predicted"].values())
    assert p["fits_side"] == "fits-side not testable under mode scope"
    assert m["pairs_note"].startswith("fits-side not testable under mode scope")
    sc = m["mode_scope"]["cameras"]
    assert sc["c922"]["excluded"] == 5 and sc["c922"]["default_mode"] == "MJPG 1280x720@30"
    assert sc["c922"]["scope"]["text"] == "exactly 720 lines at >= 30 fps"
    assert sc["tiny"]["untested_reason"].startswith("untested (scope)")
    v = res["verdicts"]["G-BW|tiny|all"]
    assert v["rating"] == "untested" and v["summary_label"] == "untested (scope)"


def test_max_height_0_restores_the_2026_11_06_scope(tmp_path, patched):
    p = w_multi.run(FakeCtx(tmp_path, max_height=0))["measurements"]["pairs"][0]
    assert p["a_modes"] == ["MJPG 1280x720@30", "MJPG 1920x1080@30", "MJPG 1280x720@60", "MJPG 960x720@30"]


def test_all_modes_restores_the_fits_side(tmp_path, patched):
    res = w_multi.run(FakeCtx(tmp_path, all_modes=True))
    p = res["measurements"]["pairs"]
    # with --all-modes the tiny camera joins the domain; the C922 pair gets a 640x480 candidate that fits
    c922_generic = next(x for x in p if {x["A"], x["B"]} == {"c922", "generic"})
    assert "fits" in c922_generic["predicted"].values() and c922_generic["fits_side"] == "testable"
    # the plan section 5 candidates are back: 640x480@30 and the largest size's lowest rate
    assert "MJPG 640x480@30" in c922_generic["a_modes"] and "MJPG 1920x1080@5" in c922_generic["a_modes"]
    assert "fits-side" not in (res["measurements"].get("pairs_note") or "")
