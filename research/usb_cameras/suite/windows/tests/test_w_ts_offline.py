"""Offline unit tests for W-TS (no camera is opened: capture functions are replaced by fakes).

    uv run --isolated --python 3.12 --no-project --with pytest pytest suite/windows/tests/test_w_ts_offline.py

Covers the fixes from results/windows/Gerald/suite_20261106T181941Z/analysis/ts.md on the tier-0 routes: 0 frames,
synthesized DS pts (C930e two-step pts) rated 'no' with no drop count, measured-period drop detection on the MF
sample time, the best-route aggregate (untested outranks no, by design), the device-fault gate (a wedged camera is
opened once, then skipped) and --reanalyse. Tier 0 only (Dom 2026-11-09): UVC PTS/SCR fields in the frames (present
when the registry value is set) are ignored, never rated, and leave no cell behind.
"""
from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
WIN = HERE.parent
SUITE = WIN.parent
for p in (str(SUITE), str(WIN), str(WIN / "helpers"), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import w_ts  # noqa: E402

P = 1e9 / 30
MODE = SimpleNamespace(w=1280, h=720, fps=30.0, text="MJPG 1280x720@30", fps_arg=30, ds_fps=30, subtype="MJPG")
C922 = {"key": "046d:085c:sn=X", "name": "c922", "vid": "046d", "pid": "085c", "serial": "X", "metadata_tier1": True,
        "mf_symlink": "mf-link", "ds_path": "ds-link", "is_kiyo": False}
KIYO = {"key": "1532:0e05:port=P", "name": "USB Video Device", "vid": "1532", "pid": "0e05", "serial": None,
        "metadata_tier1": True, "mf_symlink": "kiyo-mf", "ds_path": "kiyo-ds", "is_kiyo": True}
C930E = {"key": "046d:0843:port=Q", "name": "c930e", "vid": "046d", "pid": "0843", "metadata_tier1": False,
         "mf_symlink": "c930e-mf", "ds_path": "c930e-ds", "is_kiyo": False}


def _grid(t, g=16e6):
    return math.ceil(t / g) * g


def mf_rows(n=300, hz=3e8, pts=True, fps=30.0, pts_hz=None, late=0.0):
    """MF rows: arrivals on a 16 ms grid; ``late``: share of frames delayed by one extra grid tick at random.
    ``pts``: also write the UVC metadata fields wincam emits when the registry value is set (W-TS must ignore
    them)."""
    rnd = random.Random(1)
    rows = []
    per = 1e9 / fps
    for i in range(n):
        cap = 1e12 + i * per
        r = {"seq": i, "qpc_ns": _grid(cap + 3e6 + (16e6 if rnd.random() < late else 0.0)), "sample_time_100ns": _grid(cap) / 100,
             "discontinuity": i == 0}
        if pts:
            ph = pts_hz or hz
            stc = int(i * hz / fps) % (1 << 32)
            r.update(uvc_pts=int((i * ph / fps) - 0.033 * ph) % (1 << 32), uvc_scr_stc=stc,
                     uvc_scr_sof=int(i * 29.47) % 2048, uvc_eof_scr_stc=(stc + int(0.007 * hz)) % (1 << 32),
                     uvc_eof_scr_sof=(int(i * 29.47) + 6) % 2048, has_metadata=True)
        rows.append(r)
    return rows


def ds_rows(n=300, steps=(333333, 333283)):
    rnd = random.Random(2)
    rows, pts = [], 0
    for i in range(n):
        if i:
            pts += steps[1] if (len(steps) > 1 and i % 3 == 0) else steps[0]
        rows.append({"seq": i, "qpc_ns": _grid(1e12 + i * P * 0.99927 + rnd.choice((0, 16e6))), "pts_ns": pts * 100})
    return rows


def test_zero_frames_mf_analysis():
    a = w_ts.analyse_mf([], MODE)
    assert a["frames"] == 0 and a["fields"] == {"qpc_ns": 0, "sample_time_100ns": 0}
    v, cells = w_ts.verdicts_for(KIYO, "mf", a, 0)
    assert v["rating"] == "untested" and cells == {}


def test_ds_two_step_pts_synthesized_and_no_drop_count():
    a = w_ts.analyse_ds(ds_rows(), MODE)
    assert a["pts_synthesized"]["synthesized"] is True and a["drops_pts"] is None
    s = w_ts.rate_sources("ds", a, C930E)
    assert s["pyav_pts"]["rating"] == "no"
    assert s["pyav_pts"]["evidence"]["drops_detectable"] is False
    # the API aggregate stays the best route including untested ones (by design, analysis ts.md V3.1)
    v, cells = w_ts.verdicts_for(C930E, "ds", a, 300)
    assert v["rating"] == "untested" and cells["ds:pyav_pts"]["rating"] == "no"
    assert "untested" in v["aggregate_note"]


def test_mf_c922_like_sources():
    rows = mf_rows()
    a = w_ts.analyse_mf(rows, MODE)
    assert a["drops_sample_time"]["drops_detectable"] is True and a["drops_sample_time"]["drops"] == 0
    assert a["arrival_minus_sample_time_ms"]["n_modes"] >= 1 and "median" not in a["arrival_minus_sample_time_ms"]
    s = w_ts.rate_sources("mf", a, C922)
    assert set(s) == {"mf_sample_time", "frame_index_fit"}
    assert s["mf_sample_time"]["rating"] == "no"
    assert s["frame_index_fit"]["rating"] == "untested"
    assert s["frame_index_fit"]["detail"]["fit_unreliable"] is False
    # random one-tick delays on half the frames make 64 ms intervals that are not drops: flagged, not mis-slotted
    harsh = w_ts.analyse_mf(mf_rows(late=0.5), MODE)["frame_index_fit_arrival"]["whole_run"]
    assert harsh["fit_unreliable"] is True and harsh["slots_skipped"] == 0


def test_jittery_wallclock_pts_count_no_false_drops():
    """Smoke 2026-11-09: the ffmpeg CLI wall-clock packet time jitters (std ~9 ms at 30 fps), so per-interval
    rounding counted a long/short pair as a drop (14-22 false drops per 8 s). With jitter > period/4 the
    per-interval count is withheld and the whole-series count (drops_cumulative) stands."""
    rnd = random.Random(7)
    t, pts = 1e12, []
    for i in range(240):
        pts.append(t + rnd.choice((-1, 1)) * rnd.uniform(0, 15e6) if 0 < i < 239 else t)
        t += P
    pts = sorted(pts)
    rows = [{"seq": i, "pts_ns": v} for i, v in enumerate(pts)]
    a = w_ts.analyse_ds(rows, MODE, wallclock_pts=True)
    d = a["drops_pts"]
    assert d["interval_std_ms"] > P / 4 / 1e6
    assert d["drops_detectable"] is False and d["drops"] is None and d["drops_cumulative"] == 0
    assert "interval std" in d["note"]
    s = w_ts.rate_sources("ds_ffmpeg", a, C930E)["ffmpeg_pts"]
    assert s["detail"]["drops"] is None and s["detail"]["drops_cumulative"] == 0
    # a steady series with one real drop is still counted per interval
    steady = [{"seq": i, "pts_ns": 1e12 + (i + (1 if i >= 100 else 0)) * P} for i in range(240)]
    d2 = w_ts.analyse_ds(steady, MODE, wallclock_pts=True)["drops_pts"]
    assert d2["drops_detectable"] is True and d2["drops"] == 1 and d2["drops_method"] == "cumulative (slot_frames)"
    # C930e-like: interval std below period/4, but every 12th frame 20 ms late (a 53 ms / 13 ms pair): per-interval
    # rounding would count 19 drops; the whole-series count is 0
    late = [{"seq": i, "pts_ns": 1e12 + i * P + (20e6 if i % 12 == 5 else 0)} for i in range(240)]
    d3 = w_ts.analyse_ds(late, MODE, wallclock_pts=True)["drops_pts"]
    assert d3["interval_std_ms"] < P / 4 / 1e6 and d3["drops_detectable"] is True and d3["drops"] == 0
    from common import tsanalysis as tsa
    assert tsa.detect_drops([r["pts_ns"] for r in late], period=P)["drops"] > 10      # the old count


def test_uvc_metadata_in_rows_is_ignored():
    # tier 0 only (Dom 2026-11-09): the Kiyo's 1 kHz PTS and the C922's SCR are not analysed, rated or reported
    for cam, rows_md, rows_plain in ((KIYO, mf_rows(pts_hz=1000.0, hz=3e7), mf_rows(pts=False)),
                                     (C922, mf_rows(), mf_rows(pts=False))):
        a, b = w_ts.analyse_mf(rows_md, MODE), w_ts.analyse_mf(rows_plain, MODE)
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
        assert "uvc" not in json.dumps(a).lower()
        v, cells = w_ts.verdicts_for(cam, "mf", a, len(rows_md))
        assert set(cells) == {"mf:mf_sample_time", "mf:frame_index_fit"}
        assert v["tier"] == 0 and all(c["tier"] == 0 for c in cells.values())
    for gone in ("TIER1_SOURCES", "_flag_defects", "_pts_consistency", "_clock_hz_from", "_tier_fields"):
        assert not hasattr(w_ts, gone), gone


def test_rate_ts_tier0_has_no_device_criterion():
    # host-time sources carry no device-timestamp criterion (tier 0 only, Dom 2026-11-09): a host-time grid is
    # 'no'; a fine-grid host stamp without ground truth is 'untested' for lack of ground truth
    assert not hasattr(w_ts, "_rate_ts")
    a = {"drops_sample_time": {"drops_detectable": True}}
    for grid, want in ((16.0, "no"), (1.0, "untested")):
        a["grid_sample_time"] = {"quantized": True, "step_ms": grid}
        v = w_ts.rate_sources("mf", a, {})["mf_sample_time"]
        assert v["rating"] == want, (grid, v)
        assert not any("device timestamps monotonic" in c["criterion"] for c in v.get("criteria") or []), v
        assert "not self-consistent" not in json.dumps(v)


def test_fault_classification():
    s = {"error": {"stage": "first_sample", "hr": "0x8007001F", "class": "device_error"}}
    f = w_ts._fault_of(s, {"rc": 4}, "mf MJPG 1280x720@30")
    assert f["device_fault"] and f["fault_code"] == "0x8007001F"
    assert w_ts._fault_of({"error": {"errno": 5, "class": "other", "stage": "open"}}, {"rc": 4}, "ds") is None
    assert w_ts._fault_of(None, {"timed_out": True}, "mf")["fault_code"] == "timeout"
    v = w_ts._fault_verdict(f)
    assert v["rating"] == "untested" and v["evidence"]["device_fault"] is True
    assert "replug" in json.dumps(v)


class FakeCtx:
    def __init__(self, tmp: Path, cameras, faults=None):
        self.cameras = cameras
        self.out_dir = tmp / "out"
        self.raw_dir = tmp / "raw"
        self.args = SimpleNamespace(ts_seconds=2.0, quick=True)
        self.logs = []
        if faults is not None:
            self.faults = faults

    def log(self, msg):
        self.logs.append(msg)


@pytest.fixture
def fake_ck(monkeypatch, tmp_path):
    calls = []
    frames: dict = {}

    def capture(api):
        def _cap(ctx, cam, mode, od, seconds=None, save="none", **kw):
            calls.append((api, cam["key"]))
            od = Path(od)
            od.mkdir(parents=True, exist_ok=True)
            rows, summ = frames[(api, cam["key"])]
            with (od / "frames.jsonl").open("w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r) + "\n")
            return summ, {"rc": 0 if summ.get("ok") else 4}
        return _cap

    ck = w_ts.ck
    monkeypatch.setattr(ck, "new_result", lambda ctx, test, cams=None: {"test": test, "cameras": ctx.cameras})
    monkeypatch.setattr(ck, "arrivals_before", lambda ctx: {})
    monkeypatch.setattr(ck, "arrivals_after", lambda ctx, a0: {"changes": []})
    monkeypatch.setattr(ck, "quick", lambda ctx: True)
    monkeypatch.setattr(ck, "arg", lambda ctx, name, full, q: q)
    monkeypatch.setattr(ck, "get_formats", lambda ctx, cam, cache=None: ({}, {}))
    monkeypatch.setattr(ck, "mjpeg_modes", lambda fm: [MODE])
    monkeypatch.setattr(ck, "default_mode", lambda modes: MODE)
    monkeypatch.setattr(ck, "wincam_capture", capture("mf"))
    monkeypatch.setattr(ck, "pyav_capture", capture("ds"))
    return SimpleNamespace(calls=calls, frames=frames)


def test_wedged_camera_opened_once_then_skipped(fake_ck, tmp_path):
    err = {"stage": "first_sample", "hr": "0x8007001F", "class": "device_error",
           "reason": "ERROR_GEN_FAILURE: device stopped answering (Kiyo signature)"}
    fake_ck.frames[("mf", KIYO["key"])] = ([], {"ok": False, "error": err})
    fake_ck.frames[("mf", C922["key"])] = (mf_rows(120), {"ok": True})
    fake_ck.frames[("ds", C922["key"])] = (ds_rows(120, steps=(333333,)), {"ok": True})
    ctx = FakeCtx(tmp_path, [KIYO, C922])
    res = w_ts.run(ctx)
    assert ("ds", KIYO["key"]) not in fake_ck.calls          # the wedged Kiyo is not opened a second time
    assert ("mf", KIYO["key"]) in fake_ck.calls and ("ds", C922["key"]) in fake_ck.calls
    v = res["verdicts"]
    for api in ("mf", "ds"):
        assert v[f"G-TS|{KIYO['key']}|{api}"]["rating"] == "untested"
        assert v[f"G-TS|{KIYO['key']}|{api}"]["evidence"]["device_fault"] is True
    assert res["measurements"]["device_faults"][KIYO["key"]]["fault_code"] == "0x8007001F"
    # tier 0 only: the MF aggregate is the frame-index model (untested until the rig), the 16 ms sample time is 'no'
    assert v[f"G-TS|{C922['key']}|mf"]["rating"] == "untested"
    assert v[f"G-TS|{C922['key']}|mf:mf_sample_time"]["rating"] == "no"
    assert not any("uvc" in k for k in v)


def test_runner_fault_skips_camera(fake_ck, tmp_path):
    rec = {"first_fault_utc": "2026-11-06T13:44:00Z", "test": "W-MJPEG", "mode": "mf_640x360_5",
           "fault_code": "0x8007001F"}
    ctx = FakeCtx(tmp_path, [KIYO], faults={KIYO["key"]: rec})
    res = w_ts.run(ctx)
    assert fake_ck.calls == []
    v = res["verdicts"][f"G-TS|{KIYO['key']}|mf"]
    assert v["rating"] == "untested" and "2026-11-06T13:44:00Z" in json.dumps(v)


def test_reanalyse_writes_separate_file(tmp_path):
    run_dir = tmp_path / "run"
    raw = tmp_path / "raw"
    od_mf = raw / "W-TS" / "c922" / "mf"
    od_ds = raw / "W-TS" / "c930e" / "ds"
    for od, rows in ((od_mf, mf_rows(150)), (od_ds, ds_rows(150))):
        od.mkdir(parents=True)
        (od / "frames.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    kiyo_err = {"stage": "first_sample", "hr": "0x8007001F", "class": "device_error"}
    orig = {"test": "W-TS", "utc_started": "2026-11-06T19:45:05Z", "cameras": [C922, C930E, KIYO],
            "measurements": {"cameras": {
                C922["key"]: {"name": "c922", "mode": "MJPG 1280x720@30", "apis": {
                    "mf": {"frames_jsonl": str(od_mf / "frames.jsonl"), "clock_hz_nominal": 3e8, "capture_ok": True}}},
                C930E["key"]: {"name": "c930e", "mode": "MJPG 1280x720@30", "apis": {
                    "ds": {"frames_jsonl": str(od_ds / "frames.jsonl"), "capture_ok": True}}},
                KIYO["key"]: {"name": "kiyo", "mode": "MJPG 1280x720@30", "apis": {
                    "mf": {"frames_jsonl": str(raw / "nope" / "frames.jsonl"), "capture_error": kiyo_err,
                           "capture_ok": False},
                    "ds": {"frames_jsonl": str(raw / "nope2" / "frames.jsonl"),
                           "capture_error": {"errno": 5, "class": "other"}, "capture_ok": False}}}}},
            "verdicts": {f"G-TS|{C930E['key']}|ds:pyav_pts": {"rating": "untested"},
                         f"G-TS|{C922['key']}|mf:uvc_scr_stc": {"rating": "partial"},
                         "OTHER|x": {"rating": "yes"}}}
    run_dir.mkdir()
    (run_dir / "W-TS.json").write_text(json.dumps(orig), encoding="utf-8")
    # Kiyo: an empty frames.jsonl as in the real run
    for sub in ("nope", "nope2"):
        (raw / sub).mkdir()
        (raw / sub / "frames.jsonl").write_text("", encoding="utf-8")
    before = (run_dir / "W-TS.json").read_bytes()
    out = w_ts.reanalyse(run_dir, raw)
    assert (run_dir / "W-TS.json").read_bytes() == before
    written = json.loads((run_dir / "reanalysis" / "W-TS.json").read_text(encoding="utf-8"))
    v = written["verdicts"]
    assert v[f"G-TS|{C930E['key']}|ds:pyav_pts"]["rating"] == "no"
    # tier 0 only: the old UVC SCR cell is gone (listed as a change to None), the MF sample time is rated
    assert f"G-TS|{C922['key']}|mf:uvc_scr_stc" not in v and not any("uvc" in k for k in v)
    assert v[f"G-TS|{C922['key']}|mf:mf_sample_time"]["rating"] == "no"
    assert {"key": f"G-TS|{C922['key']}|mf:uvc_scr_stc", "before": "partial", "after": None} in \
        out["reanalysis"]["rating_changes"]
    assert v[f"G-TS|{KIYO['key']}|mf"]["evidence"]["device_fault"] is True
    assert v[f"G-TS|{KIYO['key']}|ds"]["evidence"]["device_fault"] is True
    assert v["OTHER|x"] == {"rating": "yes"}
    assert {"key": f"G-TS|{C930E['key']}|ds:pyav_pts", "before": "untested", "after": "no"} in \
        out["reanalysis"]["rating_changes"]


def test_format_read_failure_is_recorded_not_dropped(fake_ck, tmp_path, monkeypatch):
    """Review round 3: a camera whose MF format read fails (the Kiyo hanging at activation) gets a verdict for every
    API: 'untested (format read failed)', or 'untested (device fault)' when the health probe finds it faulted."""
    ck = w_ts.ck
    monkeypatch.setattr(ck, "mjpeg_modes", lambda fm: [])
    monkeypatch.setattr(ck, "get_formats", lambda ctx, cam, cache=None: (
        {"error": {"stage": "activate", "class": "timeout"}}, {"rc": 5}))
    ctx = FakeCtx(tmp_path / "a", [KIYO])
    res = w_ts.run(ctx)
    for api in w_ts.APIS:
        v = res["verdicts"][f"G-TS|{KIYO['key']}|{api}"]
        assert v["rating"] == "untested" and v["summary_label"] == "untested (format read failed)"
        assert "activate" in v["note"] and "scope" not in v["summary_label"]
    assert fake_ck.calls == []
    probes = []
    ctx2 = FakeCtx(tmp_path / "b", [KIYO])

    def health_probe(cam, test=None, mode=None, reason=""):
        probes.append((cam["key"], test))
        ctx2.device_faults = {cam["key"]: {"active": True, "utc": "2026-11-09T10:00:00Z", "code": "timeout",
                                           "kind": "hung_process"}}
        return {"ok": False, "fault_like": True}
    ctx2.health_probe = health_probe
    res2 = w_ts.run(ctx2)
    assert probes == [(KIYO["key"], "W-TS")] and fake_ck.calls == []
    for api in w_ts.APIS:
        v = res2["verdicts"][f"G-TS|{KIYO['key']}|{api}"]
        assert v["rating"] == "untested" and v["evidence"]["device_fault"] is True
    assert KIYO["key"] in res2["measurements"]["device_faults"]
