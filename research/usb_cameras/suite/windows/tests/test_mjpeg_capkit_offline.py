"""Offline unit tests for W-MJPEG, capkit and pyav_ds fixes (no camera opened).

    uv run --isolated --python 3.12 --no-project --with pytest --with simplejpeg --with pillow \
        pytest suite/windows/tests/test_mjpeg_capkit_offline.py

Covers (analysis/mjpeg_fmt.md H1-H10 + verifier M1/M3, multi_topo.md B9 + open duration, cyc_kiyo.md B6):
symmetric fps reference and rate_honoured, 0 frames = no JPEG, device fault -> untested, decode sample spread over
the capture, sweep order (default first, low-rate last), tier-0-only fps reference (no device-PTS rate, Dom
2026-11-09), device-fault detection and the suite-wide registry, control state, pyav_ds open duration / format_fallback with a
fake PyAV, ffmpeg banner parsing, the FFmpeg log capture self-test, and the offline re-rate of the 20261106 run.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
import time
import types
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
WIN = HERE.parent
SUITE = WIN.parent
for p in (str(SUITE), str(WIN), str(WIN / "helpers"), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows suite")

import capkit as ck  # noqa: E402
import pyav_ds  # noqa: E402
import w_mjpeg  # noqa: E402

RUN = SUITE.parent / "results" / "windows" / "Gerald" / "suite_20261106T181941Z"


# ============================================================================================================ capkit
def test_spread_pick_covers_whole_list():
    items = list(range(46))
    pick = ck.spread_pick(items, 8)
    assert pick[0] == 0 and pick[-1] == 45 and len(pick) == 8
    assert ck.spread_pick(items[:5], 8) == items[:5]
    assert ck.spread_pick(items, 1) == [0]


def test_saved_frame_bytes_spread(tmp_path):
    rows, off = [], 0
    with (tmp_path / "frames.mjpeg").open("wb") as f:
        for i in range(30):
            b = bytes([i]) * 10
            rows.append({"seq": i, "mjpeg_offset": off, "mjpeg_len": len(b)})
            f.write(b)
            off += len(b)
    first = ck.saved_frame_bytes(tmp_path, rows, 4)
    spread = ck.saved_frame_bytes(tmp_path, rows, 4, spread=True)
    assert [r["seq"] for r, _ in first] == [0, 1, 2, 3]
    assert [r["seq"] for r, _ in spread] == [0, 10, 19, 29]
    assert spread[-1][1] == bytes([29]) * 10


def test_sweep_order_default_first_low_rate_last():
    M = ck.Mode
    modes = [M(640, 360, 5, 1), M(640, 360, 30, 1), M(1280, 720, 5, 1), M(1280, 720, 30, 1), M(1920, 1080, 60, 1),
             M(640, 360, 15, 2)]
    order = ck.sweep_order(modes)
    assert order[0] == M(1280, 720, 30, 1)
    assert [m.fps for m in order[-3:]] == [5.0, 7.5, 5.0]          # low-rate modes last, by size
    assert all(m.fps >= ck.LOW_FPS for m in order[1:3])
    assert sorted(order, key=str) == sorted(modes, key=str)


def test_fps_reference_symmetric_above_nominal():
    # generic camera at @25 runs 25.7 on both APIs: the old rule (below nominal only) failed it
    ref, basis, note = ck.fps_reference({"mf": 25.70, "ds": 25.69}, 25.0)
    assert basis == "apis_agree" and abs(ref - 25.695) < 1e-6 and note
    ref, basis, _ = ck.fps_reference({"mf": 15.0, "ds": 15.02}, 5.0)     # below nominal still accepted
    assert basis == "apis_agree" and abs(ref - 15.01) < 1e-6
    # tier 0 only (Dom 2026-11-09): there is no device-PTS reference any more
    with pytest.raises(TypeError):
        ck.fps_reference({"mf": 22.9, "ds": 20.0}, 20.0, pts_fps=21.0)
    assert ck.fps_reference({"mf": 30.5, "ds": 30.6}, 60.0)[:2] == (30.55, "apis_agree")
    # APIs disagree (C930e drift): nominal
    assert ck.fps_reference({"mf": 22.9, "ds": 20.0}, 20.0)[:2] == (20.0, "nominal")
    assert ck.fps_reference({"mf": 22.9, "ds": None}, 20.0)[:2] == (20.0, "nominal")


def test_rate_honoured_is_separate_camera_finding():
    assert ck.rate_honoured({"mf": 30.0, "ds": 29.9}, 5.0)["honoured"] is False
    assert ck.rate_honoured({"mf": 30.0, "ds": 29.9}, 30.0)["honoured"] is True
    assert ck.rate_honoured({"mf": 30.0, "ds": 20.0}, 20.0)["honoured"] is None
    assert ck.rate_honoured({"mf": None, "ds": None}, 20.0)["honoured"] is None


def test_no_device_clock_helpers_left():
    # tier 0 only (Dom 2026-11-09): UVC PTS rate, PTS peak rate, SCR/SOF bus time and the dwClockFrequency reader
    # were removed from capkit; W-MJPEG rates on tier-0 timing only
    for name in ("uvc_pts_fps", "pts_peak_fps", "bus_stats", "device_clock_hz"):
        assert not hasattr(ck, name), name


def test_fps_tail_uses_last_seconds():
    # 20 fps for 2 s then 30 fps for 1.5 s (C930e mf_800x448_20 pattern)
    rows, t = [], 0
    for i in range(40):
        rows.append({"seq": i, "qpc_ns": t})
        t += int(1e9 / 20)
    for i in range(40, 86):
        rows.append({"seq": i, "qpc_ns": t})
        t += int(1e9 / 30)
    assert abs(ck.fps_tail(rows) - 30.0) < 0.5
    assert ck.fps_from_rows(rows) < 29.0


def test_fault_from_result_rules():
    dev = {"error": {"stage": "first_sample", "hr": "0x8007001F", "class": "device_error"}}
    assert ck.fault_from_result("mf", dev, {})["kind"] == "device_error"
    rel = {"error": {"stage": "reader_release", "hr": None, "class": "timeout"}, "abandoned_threads": 1}
    assert ck.fault_from_result("mf", rel, {})["kind"] == "unreleasable"
    hung = {"error": {"stage": "open", "class": "timeout"}, "unreleasable": True}
    assert ck.fault_from_result("ds", hung, {})["kind"] == "unreleasable"
    assert ck.fault_from_result("ds", {"error": {"stage": "open", "errno": 5}}, {"timed_out": True})["kind"] == \
        "hung_process"
    # not faults: a first-frame timeout, a bandwidth refusal, a raw-format fallback
    assert ck.fault_from_result("ds", {"error": {"stage": "first_frame", "class": "timeout"}}, {}) is None
    assert ck.fault_from_result("mf", {"error": {"stage": "first_sample", "hr": "0x800718CF"}}, {},
                                {"class": "bandwidth_probable"}) is None
    assert ck.fault_from_result("ds", {"format_fallback": True, "error": {"stage": "format"}}, {}) is None


class _Ctx:
    def __init__(self):
        self.lines = []

    def log(self, m):
        self.lines.append(m)


def test_fault_registry_mark_clear_first_failure():
    ctx, cam = _Ctx(), {"key": "k1", "name": "Kiyo", "vid": "1532", "pid": "0e05"}
    assert ck.device_fault(ctx, cam) is None
    rec = ck.mark_device_fault(ctx, cam, "W-MJPEG", "MJPG 1280x720@30", "mf",
                               {"kind": "device_error", "code": "0x8007001F", "stage": "first_sample", "reason": "x"})
    assert ck.device_fault(ctx, cam)["utc"] == rec["utc"] and ctx.device_faults["k1"]["test"] == "W-MJPEG"
    assert ctx.first_failures["k1"]["code"] == "0x8007001F"
    # a second fault keeps the first timestamp and test
    ck.mark_device_fault(ctx, cam, "W-TS", "m", "ds", {"kind": "unreleasable", "code": "timeout"})
    assert ctx.device_faults["k1"]["test"] == "W-MJPEG" and len(ctx.device_faults["k1"]["history"]) == 2
    ck.clear_device_fault(ctx, cam, "W-TS", {"ok": True})
    assert ck.device_fault(ctx, cam) is None
    assert ctx.device_faults["k1"]["history"][-1]["event"] == "recovered"


def test_fault_adapters_use_suitectx_gate(tmp_path):
    """With suitectx's SuiteCtx, capkit's fault helpers go through ctx.mark_fault / camera_faulted / clear_fault /
    record_failure (one registry for the runner's dead-device gate). No discovery, no camera opened."""
    import suitectx
    # a non-Kiyo Pro camera: faults can clear (a Kiyo Pro fault is permanent under the dead rule, checked below)
    cam = {"key": "046d:085c:test", "name": "c922", "vid": "046d", "pid": "085c", "is_kiyo": False}
    ctx = suitectx.build_ctx(suitectx.default_args(), out_dir=tmp_path / "o", raw_dir=tmp_path / "r", cameras=[cam])
    if not ck._has_gate(ctx):
        pytest.skip("this suitectx has no device-fault gate")
    ck.mark_device_fault(ctx, cam, "W-MJPEG", "MJPG 1280x720@30", "mf",
                         {"kind": "device_error", "code": "0x8007001F", "stage": "first_sample", "reason": "r"})
    f = ck.device_fault(ctx, cam)
    assert f["code"] == "0x8007001F" and f["test"] == "W-MJPEG" and f["utc"]
    assert ctx.camera_faulted(cam["key"])["class"] == "device_error"
    assert ck.first_failure(ctx, cam)["test"] == "W-MJPEG"
    ck.clear_device_fault(ctx, cam, "W-MJPEG", {"ok": True})
    assert ck.device_fault(ctx, cam) is None and ctx.camera_faulted(cam["key"]) is None
    kp = {"key": "1532:0e05:test", "name": "Kiyo Pro", "vid": "1532", "pid": "0e05", "is_kiyo": True}
    ctx2 = suitectx.build_ctx(suitectx.default_args(), out_dir=tmp_path / "o2", raw_dir=tmp_path / "r2", cameras=[kp])
    ck.mark_device_fault(ctx2, kp, "W-MJPEG", "MJPG 1280x720@30", "mf",
                         {"kind": "device_error", "code": "0x8007001F", "stage": "first_sample", "reason": "r"})
    ck.clear_device_fault(ctx2, kp, "W-MJPEG", {"ok": True})
    assert ctx2.camera_faulted(kp["key"]) and ctx2.camera_dead(kp["key"])


def test_gate_skipped_result_is_a_fault():
    s = {"ok": False, "gate_skipped": True, "device_fault": True, "fault_code": "0x8007001F",
         "error": {"stage": "gate", "class": "device_fault", "reason": "untested: device fault since t"}}
    assert ck.fault_from_result("mf", s, {})["kind"] == "gated"


def test_control_state_read_only_summary():
    ok = {"controls": [{"name": "auto_exposure_priority", "supported": True, "value": 1, "flags_names": []},
                       {"name": "exposure", "supported": True, "value": -4, "flags_names": ["auto"]},
                       {"name": "roll", "supported": False, "value": None}]}
    st = ck.control_state(ok)
    assert st["answering"] is True
    assert st["controls"]["auto_exposure_priority"]["value"] == 1
    assert st["controls"]["exposure"]["mode"] == "auto"
    dead = {"controls": [{"name": "exposure", "supported": True, "value": None, "flags_names": None}]}
    assert ck.control_state(dead)["answering"] is False
    assert ck.control_state(None)["answering"] is None


# ============================================================================================================ w_mjpeg
def _api(fps, frames=90, soi=1.0, neg=True, hdr="h", fallback=None):
    return {"ok": True, "negotiated": neg, "frames": frames, "fps_steady": fps, "soi_fraction": soi,
            "eoi_fraction": soi, "sof_match_fraction": 1.0 if soi else 0.0, "strict_ok_fraction": 1.0 if soi else None,
            "lenient_ok_fraction": 1.0 if soi else None, "header_sha1": hdr if soi else None,
            "format_fallback": fallback, "pix_fmt": "yuyv422" if fallback else None}


def _row(m, mf, pyav, ffm=None):
    row = {"mode": m.text, "mode_detail": m.as_dict(), "apis": {"mf": mf, "pyav_ds": pyav}}
    if ffm:
        row["apis"]["ffmpeg_ds"] = ffm
    return w_mjpeg.finish_mode_row(row, m)


INFO = {"selected": 2, "advertised": 2}


def test_generic_25p7_at_25_rates_yes_and_rate_not_honoured():
    m25, m30 = ck.Mode(1280, 720, 25, 1), ck.Mode(1280, 720, 30, 1)
    rows = [_row(m25, _api(25.70), _api(25.69)), _row(m30, _api(25.70), _api(25.71))]
    v = w_mjpeg.rate_camera("gen", rows, INFO, None)
    assert v["G-MJPEG|gen|mf"]["rating"] == "yes" and v["G-MJPEG|gen|ds"]["rating"] == "yes"
    ev = v["G-MJPEG|gen|mf"]["evidence"]
    assert ev["device_fault"] is False and ev["rating_failed_modes"] == []
    assert ev["rate_honoured_camera"]["not_honoured"] == [m25.text, m30.text]


def test_zero_frames_everywhere_without_fault_rates_no():
    m = ck.Mode(640, 480, 30, 1)
    dead = {"ok": False, "negotiated": False, "frames": 0}
    rows = [_row(m, dict(dead), dict(dead))]
    v = w_mjpeg.rate_camera("c", rows, {"selected": 1, "advertised": 1}, None)
    assert v["G-MJPEG|c|ds"]["rating"] == "no"


def test_device_fault_rates_untested_with_evidence():
    m = ck.Mode(640, 360, 5, 1)
    rows = [_row(m, {"ok": False, "frames": 1, "soi_fraction": 1.0}, {"ok": False, "frames": 0}),
            {"mode": "MJPG 640x360@10", "mode_detail": {}, "apis": {}, "skipped": "untested: device fault since t"}]
    fault = {"utc": "2026-11-06T18:43:49Z", "test": "W-MJPEG", "mode": m.text, "api": "mf", "kind": "unreleasable",
             "code": "timeout", "stage": "reader_release", "reason": "MF reader_release did not return"}
    v = w_mjpeg.rate_camera("kiyo", rows, INFO, fault)
    for api in ("mf", "ds", "pyav_ds"):
        c = v[f"G-MJPEG|kiyo|{api}"]
        assert c["rating"] == "untested"
        assert c["criteria"][0]["detail"] == "device fault, replug needed"
        assert c["evidence"]["device_fault"] is True and c["evidence"]["first_fault_utc"] == fault["utc"]
        assert c["evidence"]["fault_code"] == "timeout"


def test_ds_route_and_raw_fallback_control_rate():
    m = ck.Mode(640, 480, 5, 1)
    row = _row(m, _api(30.0), _api(6.0, soi=0.0, neg=False, fallback=True), _api(30.0))
    assert row["apis"]["ds"]["route"] == "ffmpeg_ds"
    assert row["header_sha1_equal"] is True
    assert row["raw_fallback_rate"]["honoured"] is False and row["raw_fallback_rate"]["pix_fmt"] == "yuyv422"
    assert row["rate_honoured"]["honoured"] is False and row["fps_misses"] == []
    v = w_mjpeg.rate_camera("c922", [row], {"selected": 1, "advertised": 1}, None)
    assert v["G-MJPEG|c922|ds"]["rating"] == "yes"            # the camera ignoring 5 fps is not an API failure
    assert v["G-MJPEG|c922|pyav_ds"]["rating"] in ("partial", "no")
    assert v["G-MJPEG|c922|pyav_ds"]["evidence"]["rating_failed_modes"] == [m.text]


def test_fps_misses_flag_recapture_candidates():
    m = ck.Mode(800, 448, 20, 1)
    row = _row(m, _api(22.9), _api(20.0))
    assert set(row["fps_misses"]) == {"mf"} and row["fps_reference_basis"] == "nominal"


def test_stored_uvc_pts_rate_is_ignored():
    # a W-MJPEG row from an older run still carries uvc_pts_fps: it plays no part in the reference or the rating
    m = ck.Mode(800, 448, 20, 1)
    mf = dict(_api(22.9), uvc_pts_fps=22.9)
    row = _row(m, mf, _api(20.0))
    assert row["fps_reference_basis"] == "nominal" and set(row["fps_misses"]) == {"mf"}
    rm = w_mjpeg._rate_rows([row], "mf")
    assert "fps_uvc_pts" not in rm[0]
    v = w_mjpeg.rate_camera("c930e", [row], {"selected": 1, "advertised": 1}, None)
    assert v["G-MJPEG|c930e|mf"]["evidence"]["modes"][0]["fps_reference_source"] != "uvc_pts"


def test_save_every_targets_nominal():
    assert w_mjpeg.save_every(ck.Mode(640, 480, 5, 1), 3.0) == 1          # 15 frames: save all
    assert w_mjpeg.save_every(ck.Mode(640, 480, 30, 1), 3.0) == 5
    assert w_mjpeg.save_every(ck.Mode(640, 480, 30, 1), 10.0) == 17


def test_call_rate_mjpeg_respects_contract_when_rating_fn_ignores_fault(monkeypatch):
    def fake(modes):
        return {"rating": "partial", "criteria": [], "evidence": {"modes": []}}
    monkeypatch.setattr(w_mjpeg.rating, "rate_mjpeg", fake)
    v = w_mjpeg._call_rate_mjpeg([], {"device_fault": True, "fault_code": "0x8007001F", "first_fault_utc": "t"})
    assert v["rating"] == "untested" and v["superseded_rating"] == "partial"
    assert v["evidence"]["device_fault"] is True


# ============================================================================================================ pyav_ds
class _FakeCC:
    def __init__(self, name):
        self.name, self.pix_fmt, self.width, self.height = name, "yuyv422" if name != "mjpeg" else "yuvj422p", 64, 48


class _FakePkt:
    def __init__(self, b, i):
        self._b, self.size, self.pts, self.dts = b, len(b), i * 333333, i * 333333
        self.time_base = types.SimpleNamespace(numerator=1, denominator=10_000_000)

    def __bytes__(self):
        return self._b


class _FakeContainer:
    def __init__(self, codec, n):
        st = types.SimpleNamespace(codec_context=_FakeCC(codec), time_base="1/10000000", average_rate="30")
        self.streams = types.SimpleNamespace(video=[st])
        self.n = n

    def demux(self, s):
        for i in range(self.n):
            time.sleep(0.005)
            yield _FakePkt(b"\xff\xd8" + b"\x00" * 50 + b"\xff\xd9", i)

    def close(self):
        pass


def _fake_av(mode, codec="mjpeg", n=10):
    def open_(url, format=None, options=None, timeout=None):  # noqa: A002
        if mode == "error":
            time.sleep(0.05)
            e = OSError(5, "Input/output error")
            raise e
        if mode == "hang":
            threading.Event().wait(30)
        return _FakeContainer(codec, n)
    return types.SimpleNamespace(open=open_)


def test_run_session_open_error_has_duration():
    r = pyav_ds.run_session(_fake_av("error"), "video=x", 64, 48, "30", 1.0, 5, None, False, "1M")
    assert r["stage_failed"] == "open" and r["error"]["errno"] == 5
    assert r["open_duration_ms"] >= 40 and r["error"]["open_duration_ms"] == r["open_duration_ms"]
    assert r["format_fallback"] is None and r["mjpeg_ok"] is False


def test_run_session_open_hang_has_duration():
    r = pyav_ds.run_session(_fake_av("hang"), "video=x", 64, 48, "30", 0.2, 5, None, False, "1M")
    assert r["hung"] and r["unreleasable"] and r["open_duration_ms"] >= 1000.0
    assert r["error"]["open_duration_ms"] == r["open_duration_ms"]


def test_run_session_format_fallback_per_session():
    raw = pyav_ds.run_session(_fake_av("ok", codec="rawvideo"), "video=x", 64, 48, "30", 1.0, 5, None, False, "1M")
    assert raw["ok"] is True and raw["format_fallback"] is True and raw["mjpeg_ok"] is False
    assert raw["pix_fmt"] == "yuyv422"
    mj = pyav_ds.run_session(_fake_av("ok"), "video=x", 64, 48, "30", 1.0, 5, None, False, "1M")
    assert mj["format_fallback"] is False and mj["mjpeg_ok"] is True and mj["open_duration_ms"] is not None


FFMPEG_BANNER = """Input #0, dshow, from 'video=@device_pnp_\\\\?\\usb#vid_046d':
  Duration: N/A, start: 1762457000.123456, bitrate: N/A
  Stream #0:0: Video: mjpeg (Baseline) (MJPG / 0x47504A4D), yuvj422p(pc, bt470bg/unknown/unknown), 1280x720, 30 fps
"""


def test_parse_ffmpeg_banner():
    assert pyav_ds.parse_ffmpeg_stream(FFMPEG_BANNER) == ("mjpeg", "yuvj422p")
    assert pyav_ds.parse_ffmpeg_start(FFMPEG_BANNER) == pytest.approx(1762457000.123456)
    raw = "Stream #0:0: Video: rawvideo (YUY2 / 0x32595559), yuyv422, 640x480, 30 fps"
    assert pyav_ds.parse_ffmpeg_stream(raw) == ("rawvideo", "yuyv422")
    assert pyav_ds.parse_ffmpeg_stream("nothing") == (None, None)


def test_process_times_of_child():
    # the base interpreter: a uv venv's python.exe is a trampoline whose CPU is spent in a grandchild
    exe = getattr(sys, "_base_executable", None) or sys.executable
    p = subprocess.Popen([exe, "-c", "s=0\nfor i in range(3_000_000): s+=i"])
    p.wait()
    cpu, life = pyav_ds._process_times(p)
    assert cpu is not None and cpu > 0 and life is not None and life >= cpu * 0.5


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not on PATH")
def test_pyav_ds_selftest_log_captures_ffmpeg_lines():
    """B9: in-process FFmpeg log lines must reach the JSON (msvcrt stderr is buffered; the capture flushes it)."""
    r = subprocess.run(["uv", "run", "-q", "--script", str(WIN / "helpers" / "pyav_ds.py"), "selftest-log"],
                       capture_output=True, text=True, timeout=300)
    doc = json.loads(r.stdout.strip().splitlines()[-1])
    assert r.returncode == 0 and doc["ok"] is True, doc
    assert any("moov atom not found" in x["msg"] for x in doc["captured"])


# ============================================================================================================ offline
@pytest.mark.skipif(not (RUN / "W-MJPEG.json").exists(), reason="20261106 run not present")
def test_reanalyse_20261106_run(tmp_path):
    raw = Path(json.loads((RUN / "W-MJPEG.json").read_text(encoding="utf-8"))["measurements"]["raw_dir"])
    if not raw.exists():
        pytest.skip("raw folder not present")
    doc = w_mjpeg.reanalyse(RUN, out=tmp_path / "W-MJPEG.json")
    got = {k.split("|")[1][:9] + "|" + k.split("|")[2]: v["rating"] for k, v in doc["verdicts"].items()}
    assert got["4c4a:4a55|mf"] == got["4c4a:4a55|ds"] == got["4c4a:4a55|pyav_ds"] == "yes"
    assert got["1532:0e05|mf"] == got["1532:0e05|ds"] == got["1532:0e05|pyav_ds"] == "untested"
    assert got["046d:085c|mf"] == "partial" and got["046d:0843|mf"] == "partial"
    c922 = [v for k, v in doc["verdicts"].items() if k.endswith("085c:sn=C922SN01|mf")][0]
    assert c922["evidence"]["rating_failed_modes"] == ["MJPG 1280x720@5", "MJPG 1600x896@5"]
    kiyo = [v for k, v in doc["verdicts"].items() if "1532" in k][0]["evidence"]
    assert kiyo["device_fault"] is True and kiyo["fault_stage"] == "reader_release"
