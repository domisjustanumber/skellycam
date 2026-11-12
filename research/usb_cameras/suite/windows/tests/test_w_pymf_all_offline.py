"""Offline tests for W-PYMF-ALL and ``pymf multi``. NO camera is opened, enumerated or queried.

    uv run --isolated --python 3.12 --no-project --with pytest --with comtypes==1.5.0 --with pillow --with numpy \\
        --with simplejpeg pytest research/usb_cameras/suite/windows/tests/test_w_pymf_all_offline.py

Layers:
1. pure (any OS): the frames.bin record format, fault kinds, control value rule, watchdog formula;
2. analysis (any OS): gap / drop / jitter math on synthetic 16 ms-grid streams (30 and 60 fps), frames until the
   ROI luma changes, refusal vs device fault, the in-use analysis, the ratings;
3. run() with a fake ctx whose camcmd writes what pymf multi writes: dead / gated cameras left out of every spec, a
   Kiyo Pro first-sample timeout reported and marked (and the Kiyo Pro out of the later parts), a bandwidth refusal
   recorded as a result, one camcmd per part, the in-use part never on the Kiyo Pro, plan mode, estimates;
4. the real CLI end to end on generated MJPEG AVI files (Windows + comtypes + pillow; ``url`` sources in the spec):
   two "cameras" in one process, frames.bin parsed by the analysis, unsupported controls, an intruder command.
"""
from __future__ import annotations

import io
import json
import math
import subprocess
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

import w_pymf_all as W  # noqa: E402
from common import results  # noqa: E402
from pymf import framerec as FR  # noqa: E402

IS_WIN = sys.platform == "win32"
KIYO = {"key": "1532:0e05:port=P1", "name": "Razer Kiyo Pro", "vid": "1532", "pid": "0e05", "serial": None,
        "hub_port": "P1", "is_kiyo": True, "mf_symlink": r"\\?\usb#vid_1532&pid_0e05&mi_00#kiyo#{e5323777}\global",
        "parent_instance_id": "USB\\ROOT_HUB30\\SS"}
C922 = {"key": "046d:085c:sn=C922A", "name": "C922 Pro Stream Webcam", "vid": "046d", "pid": "085c", "serial": "C922A",
        "is_kiyo": False, "mf_symlink": r"\\?\usb#vid_046d&pid_085c&mi_00#c922#{e5323777}\global",
        "parent_instance_id": "USB\\VID_05E3&PID_0610\\HS13"}
GENERIC = {"key": "4c4a:4a55:port=P3", "name": "USB Camera", "vid": "4c4a", "pid": "4a55", "serial": None,
           "hub_port": "P3", "is_kiyo": False, "mf_symlink": r"\\?\usb#vid_4c4a&pid_4a55&mi_00#gen#{e5323777}\global",
           "parent_instance_id": "USB\\VID_05E3&PID_0610\\HS13"}
C930E = {"key": "046d:0843:sn=C930B", "name": "Logitech Webcam C930e", "vid": "046d", "pid": "0843",
         "serial": "C930B", "is_kiyo": False, "mf_symlink": r"\\?\usb#vid_046d&pid_0843&mi_00#c930e#{e5323777}\global",
         "parent_instance_id": "USB\\ROOT_HUB30\\X"}
ALL = [KIYO, C922, GENERIC, C930E]


# ============================================================================================================ helpers
def grid(t_ns: float, g: float = 16e6) -> int:
    return int(math.ceil(t_ns / g) * g)


def stream_rows(n: int = 900, fps: float = 30.0, drop_at: tuple = (), late_at: tuple = (), start: float = 1e12,
                bits: int = FR.BIT_SOI | FR.BIT_EOI | FR.BIT_SIZE) -> list[dict]:
    """Delivered frames of a camera at ``fps``: capture index k (``drop_at`` capture indices never arrive), MF sample
    time and arrival both on the 16 ms host grid, arrival 3 ms after capture (``late_at`` seqs +40 ms)."""
    per = 1e9 / fps
    rows, seq = [], 0
    for k in range(n):
        if k in drop_at:
            continue
        cap = start + k * per
        rows.append({"seq": seq, "qpc_ns": grid(cap + 3e6 + (40e6 if seq in late_at else 0)),
                     "sample_time_100ns": grid(cap) // 100, "sample_duration_100ns": int(1e7 / fps),
                     "bytes": 90000 + (k % 7), "reader_flags": 0, "bits": bits, "sof_w": 1280, "sof_h": 720})
        seq += 1
    return rows


def gray_jpeg(v: int, w: int = 64, h: int = 36) -> bytes:
    Image = pytest.importorskip("PIL.Image")
    b = io.BytesIO()
    Image.new("RGB", (w, h), (v, v, v)).save(b, "JPEG", quality=90)
    return b.getvalue()


# ============================================================================================================ 1. pure
def test_record_roundtrip_and_size(tmp_path):
    assert FR.REC.size == 41
    rows = stream_rows(20)
    rows[3]["sample_time_100ns"] = None
    FR.write_file(tmp_path / "frames.bin", rows)
    back = FR.read_file(tmp_path / "frames.bin")
    assert back == rows
    blob = (tmp_path / "frames.bin").read_bytes()
    assert len(FR.unpack_all(blob + b"\x01\x02")) == 20                 # torn tail ignored
    assert FR.read_file(tmp_path / "missing.bin") == []


def test_fault_kinds():
    fk = FR.fault_kind
    assert fk(None) is None
    assert fk({"stage": "first_sample", "class": "timeout", "hr_name": "timeout"}) == "first_sample_timeout"
    assert fk({"stage": "streaming", "hr": "0x8007001F", "class": "device_error"}) == "device_error"
    assert fk({"stage": "activate", "hr": "0x8007001F"}) == "device_error"
    assert fk({"stage": "streaming", "class": "timeout"}) == "stream_stall"
    assert fk({"stage": "activate", "class": "timeout"}) == "open_timeout"
    assert fk({"stage": "flush", "class": "timeout"}) == "unreleasable"
    assert fk({"stage": "first_sample", "hr": "0x800718CF", "class": "bandwidth_certain"}) == "error"
    assert fk(None, unreleasable=True) == "unreleasable"
    for k in ("device_error", "first_sample_timeout", "stream_stall", "unreleasable", "open_timeout"):
        assert FR.is_kiyo_fault(k)
    assert not FR.is_kiyo_fault("error") and "first_sample_timeout" not in FR.DEVICE_FAULT_KINDS


def test_choose_control_value():
    before = {"mn": -11, "mx": -2, "step": 1, "val": -5, "def": -6, "has_range": True}
    assert FR.choose_control_value({"delta": -2}, before, None)[0] == -7
    v, why = FR.choose_control_value({"delta": -2}, {**before, "val": -10}, None)
    assert v == -8 and "other direction" in why                         # -12 is out of range
    assert FR.choose_control_value({"value": "start"}, before, ("IAMCameraControl", -4, 1))[0] == -4
    assert FR.choose_control_value({"value": "start"}, before, None)[0] is None
    assert FR.choose_control_value({"value": "default"}, before, None)[0] == -6
    assert FR.choose_control_value({"value": 99}, before, None) == (-2, "explicit (clamped)")
    assert FR.choose_control_value({}, before, None)[0] is None


def test_watchdog_formula():
    spec = {"seconds": 600, "cameras": [{"controls": [{}, {}]}, {}], "intruders": []}
    assert FR.watchdog_ms(spec, 5000) == 600_000 + 5000 * (16 + 4) + 60_000
    spec["intruders"] = [{"timeout_s": 25}, {"timeout_s": 40}]
    assert FR.watchdog_ms(spec, 5000) == 600_000 + 65_000 + 5000 * 20 + 60_000


# ============================================================================================================ 2. analysis
def test_stream_metrics_clean_30fps():
    m = W.stream_metrics(stream_rows(900), 30.0)
    assert m["frames"] == 900 and m["integrity"]["valid"] == 1.0
    assert abs(m["fps_fit"] - 30.0) < 0.05
    assert m["sample_time"]["drops_detectable"] is True and m["sample_time"]["drops"] == 0
    assert m["arrival_gaps"]["count"] == 0 and m["arrival_gaps"]["grid_limited"] is False
    assert m["sample_time"]["frames_short_of_nominal"] == 0
    assert m["arrival_minus_sample_ms"]["offset_p99_ms"] < 1.0
    # 16 ms grid: intervals 32 / 48 ms, never above the 50 ms gap threshold
    assert m["arrival_interval_ms"]["max"] <= 48.0 and m["arrival_gaps"]["threshold_ms"] == 50.0


def test_stream_metrics_drops_and_gaps_30fps():
    rows = stream_rows(900, drop_at=(200, 400, 401, 700), late_at=(500,))
    m = W.stream_metrics(rows, 30.0)
    assert m["sample_time"]["drops"] == 4                                # 4 capture slots never arrived
    assert m["sample_time"]["frames_short_of_nominal"] == 4
    assert m["sample_time_gaps"]["count"] == 3                           # 3 gaps (one is two frames long)
    g = m["arrival_gaps"]
    assert g["count"] >= 4 and g["largest"][0]["gap_ms"] >= 80          # the two-frame hole + the late frame
    assert all(x["t_s"] is not None for x in g["largest"])
    r = W.rate_stream({"ran": True, "ok": True, "closed_by": "stop", "stop_to_released_ms": 300.0, "metrics": m,
                       "samples": {"n": 4, "strict_ok": True}})
    crit = {c["criterion"][:20]: c["met"] for c in r["criteria"]}
    assert r["rating"] == "partial" and crit["frames lost in the M"] is False


def test_stream_metrics_60fps_grid_limited():
    m = W.stream_metrics(stream_rows(600, fps=60.0), 60.0)
    assert m["sample_time"]["drops_detectable"] is False and m["sample_time"]["drops"] is None
    assert m["arrival_gaps"]["grid_limited"] is True                     # 32 ms intervals are normal here
    r = W.rate_stream({"ran": True, "ok": True, "closed_by": "stop", "stop_to_released_ms": 300.0, "metrics": m,
                       "samples": {"n": 4, "strict_ok": True}})
    assert r["rating"] == "yes"
    met = {c["criterion"][:12]: c["met"] for c in r["criteria"]}
    assert met["frames lost "] is None and met["arrival gaps"] is None


def test_camera_limited_rate_not_counted_as_loss():
    """The Kiyo Pro's 720p60 delivers ~30 fps evenly (WR2 2026-11-10): not a pymf loss, the fps criterion is None."""
    m = W.stream_metrics(stream_rows(300, fps=30.0), 60.0)
    r = W.rate_stream({"ran": True, "ok": True, "closed_by": "stop", "stop_to_released_ms": 200.0, "metrics": m,
                       "samples": {"n": 4, "strict_ok": True}})
    fps_c = next(c for c in r["criteria"] if c["criterion"].startswith("delivered fps"))
    assert fps_c["met"] is None and r["rating"] == "yes"


def test_rate_stream_release_and_faults():
    m = W.stream_metrics(stream_rows(300), 30.0)
    base = {"ran": True, "ok": True, "closed_by": "stop", "metrics": m, "samples": {"n": 2, "strict_ok": True}}
    assert W.rate_stream({**base, "stop_to_released_ms": 9000.0})["rating"] == "no"
    assert W.rate_stream({**base, "stop_to_released_ms": 100.0, "unreleasable": True})["rating"] == "no"
    r = W.rate_stream({**base, "kiyo_pro_fault": True, "failure": {"fault_kind": "first_sample_timeout"}})
    assert r["rating"] == "untested" and r["summary_label"] == "untested (device fault)"
    r = W.rate_stream({**base, "failure": {"refusal": True, "class": "bandwidth_certain"}})
    assert r["summary_label"] == "untested (refused)"
    assert W.rate_stream({"excluded": "dead", "scope": False})["summary_label"] == "untested (excluded)"
    assert W.rate_stream({"excluded": "no MJPG", "scope": True})["summary_label"] == "untested (scope)"


def test_control_effect_frames_until_change():
    lum = {s: 150.0 + (0.4 if s % 2 else -0.4) for s in range(95, 100)}
    lum.update({s: (150.0 if s < 103 else 60.0) for s in range(100, 160)})
    rec = {"seq_at_set_start": 100, "seq_at_set_return": 101, "qpc_set_start_ns": 1_000_000_000,
           "before": {"value": -5}, "set_value": -7}
    q = {s: 1_000_000_000 + (s - 100) * 33_333_333 for s in lum}
    e = W.control_effect(rec, lum, q)
    assert e["measured"] and e["changed"] and e["frames_to_change"] == 3 and e["frames_after_set_returned"] == 2
    assert e["expected_direction"] == "darker" and e["direction_ok"] is True
    assert abs(e["ms_to_change"] - 100.0) < 0.1
    flat = {s: 150.0 for s in range(95, 160)}
    e2 = W.control_effect(rec, flat, q)
    assert e2["measured"] and e2["changed"] is False and "frames_to_change" not in e2
    assert W.control_effect(rec, {})["measured"] is False


def test_rate_control():
    good = {"control": "exposure", "supported": True, "timed_out": False, "matches": True, "set_value": -7,
            "after": {"value": -7}, "effect": {"measured": True, "changed": True, "direction_ok": True,
                                               "frames_to_change": 3}}
    rest = [{"control": "cc.exposure", "ok": True}]
    assert W.rate_control("k", [good, good], rest, None)["rating"] == "yes"
    assert W.rate_control("k", [good, {**good, "timed_out": True}], rest, None)["rating"] == "no"
    assert W.rate_control("k", [{"control": "exposure", "supported": False, "reason": "x"}], [], None)[
        "summary_label"] == "untested (unsupported)"
    r = W.rate_control("k", [good], [], "camera failed")
    assert r["rating"] == "partial"


def test_classify_refusal_vs_fault():
    cr = {"error": {"stage": "first_sample", "hr": "0x800718CF", "class": "bandwidth_certain"}, "fault_kind": "error",
          "frames": {"total": 0}}
    f = W.classify_camera_failure(cr, True)
    assert f["failed"] and f["refusal"] and f["class"].startswith("bandwidth")
    kiyo = {"error": {"stage": "first_sample", "class": "timeout"}, "fault_kind": "first_sample_timeout",
            "kiyo_pro_fault": True, "frames": {"total": 0}}
    assert W.classify_camera_failure(kiyo, False)["refusal"] is False
    dev = {"error": {"stage": "streaming", "hr": "0x8007001F", "class": "device_error"}, "fault_kind": "device_error",
           "frames": {"total": 10}}
    assert W.classify_camera_failure(dev, True)["refusal"] is False
    assert W.classify_camera_failure({"error": None, "fault_kind": None}, False) == {"failed": False}


def test_session_suspects():
    sess = {"doc": None, "spec": {"cameras": [{"label": "a"}, {"label": "b"}]}}
    assert W.session_suspects(sess, ["a", "b"])[0] == ["a", "b"]
    sess["doc"] = {"watchdog_fired": True, "partial": {"cameras": {
        "a": {"stage": "streaming", "progress_age_ms": 40000.0}, "b": {"stage": "streaming", "progress_age_ms": 30.0}}}}
    assert W.session_suspects(sess, ["a", "b"]) == (["a"], "watchdog partial progress")
    sess["doc"] = {"cameras": [{"label": "a"}]}
    assert W.session_suspects(sess, ["a"])[0] == []


def _in_use_doc(rows, outcome="refused", pid=4242, disturb=False):
    t_all = rows[0]["qpc_ns"] - 1_000_000_000
    q = lambda s: t_all + int(s * 1e9)  # noqa: E731
    err = {"stage": "first_sample", "hr": "0xC00D3704", "hr_name": "MF_E_HW_MFT_FAILED_START_STREAMING",
           "class": "in_use"}
    opener = {"ok": False, "error": err, "frames": {"total": 0}} if outcome == "refused" else \
        {"ok": True, "error": None, "frames": {"total": 1}}
    return {"pid": pid, "session": {"t_all_qpc_ns": t_all},
            "cameras": [{"label": "c922", "ok": True, "closed_by": "stop", "fault_kind": None, "unreleasable": False,
                         "error": None}],
            "intruders": [
                {"label": "wincam_activity", "qpc_start_ns": q(6), "qpc_end_ns": q(7.6), "start_after_t_all_s": 6,
                 "timed_out": False, "rc": 0, "stdout_json": {"subcommand": "activity", "devices": [
                     {"symlink": C922["mf_symlink"], "in_use": True, "streaming": True,
                      "processes": [{"pid": pid, "name": "python.exe", "streaming": True}]}]}},
                {"label": "wincam_capture", "qpc_start_ns": q(14), "qpc_end_ns": q(15.2), "start_after_t_all_s": 14,
                 "timed_out": False, "rc": 4, "stdout_json": opener},
                {"label": "pymf_capture", "qpc_start_ns": q(26), "qpc_end_ns": q(29.0), "start_after_t_all_s": 26,
                 "timed_out": disturb is None, "rc": 4, "stdout_json": opener}]}


def test_analyse_in_use_refused_undisturbed():
    rows = stream_rows(30 * 40)
    iu = W.analyse_in_use(_in_use_doc(rows), rows, "c922", 30.0, C922["mf_symlink"])
    ops = {o["label"]: o for o in iu["openers"]}
    assert ops["wincam_activity"]["sees_pymf"] is True and ops["wincam_activity"]["in_use"] is True
    assert ops["wincam_capture"]["outcome"] == "refused (in_use)"
    assert ops["wincam_capture"]["opener_error"]["hr"] == "0xC00D3704"
    assert iu["first_stream_disturbed"] is False
    assert W.rate_in_use(iu)["rating"] == "yes"


def test_analyse_in_use_disturbed_and_hung():
    rows = stream_rows(30 * 40)
    hole = [r for r in rows if not (15.0e9 < r["qpc_ns"] - rows[0]["qpc_ns"] < 15.6e9)]   # 600 ms hole at 14 s
    iu = W.analyse_in_use(_in_use_doc(hole), hole, "c922", 30.0, C922["mf_symlink"])
    assert iu["first_stream_disturbed"] is True and W.rate_in_use(iu)["rating"] == "partial"
    iu2 = W.analyse_in_use(_in_use_doc(rows, disturb=None), rows, "c922", 30.0, C922["mf_symlink"])
    assert any(o["outcome"].startswith("hung") for o in iu2["openers"])
    assert W.rate_in_use(iu2)["rating"] == "no"
    # no error field of an opener lands under a key named 'error' (the suite's result scan would read it as a fault)
    assert "error" not in json.dumps([{k: v for k, v in o.items() if k == "error"} for o in iu["openers"]])


# ============================================================================================================ 3. run()
def formats_doc(has60: bool) -> dict:
    types = [{"subtype": "MJPG", "width": 1280, "height": 720, "fps_num": 30, "fps_den": 1},
             {"subtype": "MJPG", "width": 640, "height": 480, "fps_num": 30, "fps_den": 1}]
    if has60:
        types.append({"subtype": "MJPG", "width": 1280, "height": 720, "fps_num": 60, "fps_den": 1})
    return {"reader_streams": [{"stream_index": 0, "types": types}]}


class FakeCtx:
    """SuiteCtx stand-in. camcmd answers ``pymf multi --spec`` with what pymf multi writes (frames.bin, samples,
    control windows, summary JSON); nothing runs. Behaviour: ``kiyo_fault`` (first-sample timeout of the Kiyo Pro
    in part 1), ``refuse_generic`` (0x800718CF on the generic camera while the C922 streams), ``dead`` / ``gated``
    key sets, ``hang`` (part 1 killed at its timeout: no JSON; ``hang_partial`` = the watchdog's progress record)."""

    def __init__(self, tmp: Path, cameras=None, quick=True, kiyo_fault=False, refuse_generic=False, dead=(),
                 gated=(), dry_run=False, hang=False, hang_partial=None):
        self.out_dir, self.raw_dir = tmp / "out", tmp / "raw"
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.args = SimpleNamespace(quick=quick)
        self.cameras = [dict(c) for c in (cameras or ALL)]
        self.wincam = WIN / "native" / "build" / "wincam.exe"
        self.python = "3.12"
        self.kiyo_fault, self.refuse_generic = kiyo_fault, refuse_generic
        self.dead_keys, self.gated_keys = set(dead), set(gated)
        self.dry_run = dry_run
        self.hang, self.hang_partial = hang, hang_partial
        self.calls: list[list[str]] = []
        self.specs: list[dict] = []
        self.faults: dict = {}
        self.marks: list[dict] = []
        self.logs: list[str] = []

    # ---- ctx API used by the module
    def log(self, msg):
        self.logs.append(msg)

    def test_dir(self, name):
        d = self.out_dir / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def raw_test_dir(self, name):
        d = self.raw_dir / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def run(self, argv, timeout_s):
        assert "--version" in argv                                   # the only uncamlocked command: env warm-up
        return {"rc": 0, "stdout": "pymf 0.3 (2026-11-11)\n", "stderr": "", "elapsed_s": 0.1, "timed_out": False}

    def camera_gated(self, cam):
        k = cam["key"] if isinstance(cam, dict) else cam
        return {"since_utc": "2026-11-11T20:00:00Z", "code": "0x8007001F"} if k in self.gated_keys else None

    def camera_dead(self, cam):
        k = cam["key"] if isinstance(cam, dict) else cam
        return {"dead": True, "since_utc": "2026-11-11T21:00:00Z"} if k in self.dead_keys else None

    def camera_faulted(self, k):
        return self.faults.get(k)

    def mark_fault(self, key, **kw):
        self.marks.append({"key": key, **kw})
        self.faults[key] = {"faulted": True, **kw}
        cam = next((c for c in self.cameras if c["key"] == key), {})
        if cam.get("is_kiyo"):
            self.dead_keys.add(key)                                  # the suite's dead rule
        return self.faults[key]

    def clear_fault(self, *a, **k):
        return None

    def arrivals(self):
        return {"cameras": {}}

    # ---- the camera command
    def camcmd(self, argv, timeout_s, **kw):
        argv = [str(a) for a in argv]
        self.calls.append(argv)
        assert argv[:3] == ["uv", "run", "--python"] and argv[argv.index("--script") + 2] == "multi"
        assert timeout_s > float(argv[argv.index("--watchdog-ms") + 1]) / 1000.0
        if self.dry_run:
            return {"argv": argv, "rc": None, "stdout": "", "stderr": "plan mode", "timed_out": False, "dry_run": True}
        spec = json.loads(Path(argv[argv.index("--spec") + 1]).read_text(encoding="utf-8"))
        od = Path(argv[argv.index("--out-dir") + 1])
        self.specs.append(spec)
        part = od.name
        if self.hang and part == "all_720p30":
            od.mkdir(parents=True, exist_ok=True)
            if self.hang_partial is None:
                return {"argv": argv, "rc": 1, "stdout": "", "stderr": "killed", "timed_out": True, "killed": True}
            wd = {"tool": "pymf", "subcommand": "multi", "watchdog_fired": True, "exit_code": 5,
                  "error": {"class": "timeout", "stage": "multi_streaming"},
                  "partial": {"cameras": {c["label"]: self.hang_partial.get(c["is_kiyo"], {"stage": "streaming",
                                                                                         "progress_age_ms": 20.0})
                                          for c in spec["cameras"]}}}
            return {"argv": argv, "rc": 5, "stdout": json.dumps(wd), "stderr": "", "timed_out": False}
        recs, streaming = [], []
        for c in spec["cameras"]:
            cam = next(x for x in self.cameras if x["mf_symlink"] == c["device"])
            if cam.get("is_kiyo") and self.kiyo_fault and part == "all_720p30":
                recs.append(self._failed(c, od, {"stage": "first_sample", "hr": None, "hr_name": "timeout",
                                                 "class": "timeout"}, "first_sample_timeout", True))
                continue
            if cam is not None and cam["key"] == GENERIC["key"] and self.refuse_generic:
                recs.append(self._failed(c, od, {"stage": "first_sample", "hr": "0x800718CF",
                                                 "hr_name": "0x800718CF", "class": "bandwidth_certain"}, "error",
                                         False))
                continue
            recs.append(self._ok(c, od, spec["seconds"]))
            streaming.append(c["label"])
        intr = []
        for it in spec.get("intruders") or []:
            t_all = 5_000_000_000
            intr.append({"label": it["label"], "target": it["target"], "argv": it["argv"],
                         "qpc_start_ns": t_all + int(it["at_s"] * 1e9), "qpc_end_ns": t_all + int((it["at_s"] + 1) * 1e9),
                         "start_after_t_all_s": it["at_s"], "end_after_t_all_s": it["at_s"] + 1, "rc": 4,
                         "timed_out": False, "stdout_json": (
                             {"subcommand": "activity", "devices": []} if "activity" in it["label"] else
                             {"ok": False, "frames": {"total": 0},
                              "error": {"stage": "first_sample", "hr": "0xC00D3704", "class": "in_use"}})})
        kf = next((r for r in recs if r["kiyo_pro_fault"]), None)
        failed = [r["label"] for r in recs if not r["ok"]]
        doc = {"tool": "pymf", "subcommand": "multi", "pid": 4242, "exit_code": 4 if failed else 0,
               "session": {"t_all_qpc_ns": 5_000_000_000, "t_stop_qpc_ns": 5_000_000_000 + int(spec["seconds"] * 1e9)},
               "cpu": {"pct_of_one_core": 9.5, "window_s": spec["seconds"]}, "cameras": recs, "intruders": intr,
               "release": {"all_released": True, "hung_camera_threads": []},
               "writer": {"dropped": 0}, "failed_cameras": failed, "abandoned_threads": 0,
               "kiyo_pro_fault": {"label": kf["label"], "kind": kf["fault_kind"]} if kf else None,
               "error": None if not failed else {"class": "camera_failure", "reason": str(failed)}}
        (od / "summary.json").write_text(json.dumps(doc), encoding="utf-8")
        return {"argv": argv, "rc": doc["exit_code"], "stdout": json.dumps(doc), "stderr": "", "timed_out": False,
                "elapsed_s": spec["seconds"]}

    def _base(self, c, od):
        d = od / c["label"]
        (d / "samples").mkdir(parents=True, exist_ok=True)
        return d, {"label": c["label"], "device": c["device"], "is_kiyo": c["is_kiyo"],
                   "mode": f"MJPG {c['width']}x{c['height']}@{c['fps']:g}", "requested": {"fps": c["fps"]},
                   "steps": [{"step": "enumerate", "hr": "0x00000000"}], "negotiated": {"readback_ok": True},
                   "files": {"frames_bin": str(d / "frames.bin"), "samples_dir": str(d / "samples")},
                   "callback_s": 0.4, "restore": [], "restore_skipped": None}

    def _failed(self, c, od, err, kind, kiyo):
        d, r = self._base(c, od)
        FR.write_file(d / "frames.bin", [])
        r.update(open_ok=False, ok=False, closed_by="failure", error=err, fault_kind=kind, kiyo_pro_fault=kiyo,
                 unreleasable=False, frames={"total": 0}, controls=[],
                 timings={"first_frame_ms": -1.0, "stop_to_released_ms": None, "close_ms": 210.0})
        return r

    def _ok(self, c, od, seconds):
        d, r = self._base(c, od)
        fps = c["fps"]
        rows = stream_rows(int(seconds * fps), fps=fps)
        FR.write_file(d / "frames.bin", rows)
        for s in (0, len(rows) // 2):
            (d / "samples" / f"f{s:07d}.jpg").write_bytes(gray_jpeg(120))
        ctl = []
        for i, item in enumerate(c.get("controls") or []):
            s0 = int(item["at_s"] * fps)
            wdir = d / f"ctl{i}_exposure"
            wdir.mkdir()
            darker = "delta" in item
            for s in range(s0 - 5, s0 + 60):
                lv = (150 if s < s0 + 3 else 60) if darker else (60 if s < s0 + 4 else 150)
                (wdir / f"f{s:07d}.jpg").write_bytes(gray_jpeg(lv))
            ctl.append({"i": i, "at_s": item["at_s"], "control": "exposure", "key": "cc.exposure", "supported": True,
                        "before": {"value": -5 if darker else -7, "flags": 2}, "set_value": -7 if darker else -5,
                        "set_flags": 2, "hr_set_name": "S_OK", "matches": True, "after": {"value": -7 if darker else -5},
                        "timed_out": False, "call_ms": 12.0, "seq_at_set_start": s0, "seq_at_set_return": s0 + 1,
                        "qpc_set_start_ns": rows[s0]["qpc_ns"], "window": {"dir": str(wdir)}})
        r.update(open_ok=True, ok=True, closed_by="stop", error=None, fault_kind=None, kiyo_pro_fault=False,
                 unreleasable=False, frames={"total": len(rows), "ok": len(rows)}, controls=ctl,
                 restore=[{"control": "cc.exposure", "restore_value": -5, "restore_flags": 1, "readback_value": -5,
                           "readback_flags": 1, "ok": True}] if ctl else [],
                 timings={"first_frame_ms": 450.0, "open_to_first_frame_ms": 900.0, "stop_to_released_ms": 320.0,
                          "close_ms": 310.0, "first_sample_after_session_start_ms": 905.0})
        return r


@pytest.fixture
def fake_formats(monkeypatch):
    def gf(ctx, cam, cache=None):
        return formats_doc((cam["vid"], cam["pid"]) in W.KNOWN_720P60), {"cached": True}
    monkeypatch.setattr(W.ck, "get_formats", gf)


def _spec_devices(spec):
    return {c["device"] for c in spec["cameras"]}


def test_run_all_good(tmp_path, fake_formats):
    ctx = FakeCtx(tmp_path)
    res = W.run(ctx)
    assert not res.get("errors"), res.get("errors")
    assert len(ctx.calls) == 3                                   # one camcmd per part
    parts = [Path(c[c.index("--out-dir") + 1]).name for c in ctx.calls]
    assert parts == ["all_720p30", "all_720p60", "in_use"]
    assert _spec_devices(ctx.specs[0]) == {c["mf_symlink"] for c in ALL}
    assert _spec_devices(ctx.specs[1]) == {KIYO["mf_symlink"], C922["mf_symlink"]}
    assert _spec_devices(ctx.specs[2]) == {C922["mf_symlink"]} and KIYO["mf_symlink"] not in json.dumps(ctx.specs[2])
    assert all(i["argv"][-1] != "" for i in ctx.specs[2]["intruders"])
    v = res["verdicts"]
    for c in ALL:
        assert v[f"pymf_multi|{c['key']}|720p30"]["rating"] == "yes", v[f"pymf_multi|{c['key']}|720p30"]
        assert v[f"pymf_streaming_set|{c['key']}|exposure"]["rating"] == "yes"
    assert v[f"pymf_multi|{KIYO['key']}|720p60"]["rating"] == "yes"
    assert v[f"pymf_multi|{C930E['key']}|720p60"]["summary_label"] == "untested (scope)"
    assert v[f"pymf_in_use|{C922['key']}"]["rating"] == "yes"
    assert v["pymf_multi"]["rating"] == "yes"
    m = res["measurements"]
    eff = m["cameras"][C922["key"]]["controls"][0]["effect"]
    assert eff["changed"] and eff["direction_ok"] and eff["frames_to_change"] == 3
    assert m["cameras"][C922["key"]]["controls"][1]["effect"]["frames_to_change"] == 4
    assert m["cameras"][C922["key"]]["all_720p30"]["samples"]["n"] == 2
    assert m["kiyo_pro_fault"] is None and m["refusals"] == [] and not ctx.marks
    assert m["parts"]["all_720p30"]["cpu"]["pct_of_one_core"] == 9.5
    assert m["control_plan"]["times_s"] == [20.0, 40.0]
    results.write_json(tmp_path / "W-PYMF-ALL.json", res)        # strict JSON (no NaN, no sets)


def test_run_kiyo_fault_refusal_and_exclusions(tmp_path, fake_formats):
    ctx = FakeCtx(tmp_path, kiyo_fault=True, refuse_generic=True)
    res = W.run(ctx)
    assert not res.get("errors"), res.get("errors")
    m, v = res["measurements"], res["verdicts"]
    # Kiyo Pro fault: reported, marked through ctx.mark_fault, and never used again in this test
    kf = m["kiyo_pro_fault"]
    assert kf and kf["key"] == KIYO["key"] and kf["kind"] == "first_sample_timeout" and kf["marked"] is True
    assert [x["key"] for x in ctx.marks] == [KIYO["key"]] and ctx.marks[0]["test"] == W.TEST
    assert KIYO["mf_symlink"] not in json.dumps(ctx.specs[1:])
    assert m["cameras"][KIYO["key"]]["all_720p60"]["excluded"].startswith("dead")
    assert v[f"pymf_multi|{KIYO['key']}|720p30"]["summary_label"] == "untested (device fault)"
    # refusal of the generic camera on the shared HS13 hub: a recorded result, no crash, no fault
    assert [r["camera"] for r in m["refusals"]] == [GENERIC["key"]] and m["refusals"][0]["refusal"] is True
    assert v[f"pymf_multi|{GENERIC['key']}|720p30"]["summary_label"] == "untested (refused)"
    assert GENERIC["key"] not in ctx.faults
    assert v[f"pymf_multi|{C922['key']}|720p30"]["rating"] == "yes"
    assert v["pymf_multi"]["rating"] == "partial" and "Kiyo Pro faulted" in v["pymf_multi"]["summary_label"]
    # the in-use target is a camera that streamed in part 1 (C922 first in order), never the Kiyo Pro
    assert m["parts"]["in_use"]["target"] == C922["key"]
    # the result scan would agree: the Kiyo Pro fault record is a first-sample timeout (not re-marked as device_error)
    import suitectx
    found = suitectx.scan_result_for_faults(W.TEST, res, ctx.cameras)
    assert GENERIC["key"] not in found and C922["key"] not in found


def test_dead_and_gated_cameras_never_in_a_spec(tmp_path, fake_formats):
    ctx = FakeCtx(tmp_path, dead={KIYO["key"]}, gated={C930E["key"]})
    res = W.run(ctx)
    text = json.dumps(ctx.specs)
    assert KIYO["mf_symlink"] not in text and C930E["mf_symlink"] not in text
    sel = res["measurements"]["selection"]
    assert sel[KIYO["key"]]["excluded_at_start"].startswith("dead")
    assert sel[C930E["key"]]["excluded_at_start"].startswith("gated")
    assert _spec_devices(ctx.specs[1]) == {C922["mf_symlink"]}       # 720p60: the C922 alone
    assert res["verdicts"][f"pymf_multi|{KIYO['key']}|720p30"]["summary_label"] == "untested (excluded)"


def test_no_in_use_part_with_only_the_kiyo(tmp_path, fake_formats):
    ctx = FakeCtx(tmp_path, cameras=[KIYO])
    res = W.run(ctx)
    assert [Path(c[c.index("--out-dir") + 1]).name for c in ctx.calls] == ["all_720p30", "all_720p60"]
    assert "Kiyo Pro" in res["measurements"]["parts"]["in_use"]["reason"]


def test_plan_mode_and_estimates(tmp_path, fake_formats):
    ctx = FakeCtx(tmp_path, dry_run=True)
    res = W.run(ctx)
    assert not res.get("errors"), res.get("errors")
    assert len(ctx.calls) == 3 and not ctx.marks
    assert res["verdicts"]["pymf_multi"]["rating"] == "untested"
    full = W.estimate_s(FakeCtx(tmp_path / "f", quick=False))
    quick = W.estimate_s(FakeCtx(tmp_path / "q", quick=True))
    assert 16 * 60 <= full <= 22 * 60 and quick <= 6 * 60
    assert W.estimate_s(FakeCtx(tmp_path / "d", quick=False, dead={KIYO["key"]})) < full
    assert W.ctrl_times(FakeCtx(tmp_path / "c", quick=False), 600.0) == [120.0, 300.0]


# ============================================================================================================ 4. CLI
def _comtypes():
    if not IS_WIN:
        pytest.skip("Windows only")
    return pytest.importorskip("comtypes")


def test_cli_multi_on_two_files(tmp_path):
    _comtypes()
    import test_pymf_offline as T
    T._avi(tmp_path / "a.avi", n=45)
    T._avi(tmp_path / "b.avi", n=30)
    py = sys.executable
    spec = {"seconds": 3, "cameras": [
        {"label": "fa", "url": str(tmp_path / "a.avi"), "width": 320, "height": 240, "fps": 30, "samples": 2,
         "controls": [{"at_s": 0.0, "control": "exposure", "delta": -2, "flags": "manual"}]},
        {"label": "fb", "url": str(tmp_path / "b.avi"), "width": 320, "height": 240, "fps": 30}],
        "intruders": [{"label": "opener", "at_s": 0, "timeout_s": 30, "target": "fa",
                       "argv": [py, "-c", "import json;print(json.dumps({'ok': False, 'error': "
                                          "{'hr': '0xC00D3704', 'class': 'in_use'}}))"]}]}
    (tmp_path / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
    out = tmp_path / "out"
    r = subprocess.run([py, str(WIN / "pymf" / "cli.py"), "multi", "--spec", str(tmp_path / "spec.json"),
                        "--timeout-ms", "4000", "--out-dir", str(out)], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    j = json.loads(r.stdout)
    assert j["subcommand"] == "multi" and j["ok"] and j["release"]["all_released"] and j["abandoned_threads"] == 0
    assert json.loads((out / "summary.json").read_text(encoding="utf-8"))["exit_code"] == 0
    cams = {c["label"]: c for c in j["cameras"]}
    assert cams["fa"]["frames"]["total"] == 45 and cams["fb"]["frames"]["total"] == 30
    assert cams["fa"]["closed_by"] == "end_of_file" and cams["fa"]["fault_kind"] is None
    rows = FR.read_file(cams["fa"]["files"]["frames_bin"])
    assert [x["seq"] for x in rows] == list(range(45)) and all(x["sof_w"] == 320 for x in rows)
    assert all(x["bits"] & FR.BIT_SOI and x["bits"] & FR.BIT_EOI and x["bits"] & FR.BIT_SIZE for x in rows)
    assert (out / "fa" / "samples" / "f0000000.jpg").exists()
    ctl = cams["fa"]["controls"]
    assert len(ctl) == 1 and ctl[0]["supported"] is False                 # a file source has no camera control
    assert j["intruders"][0]["stdout_json"]["error"]["class"] == "in_use" and j["intruders"][0]["rc"] == 0
    assert j["frames_format"]["size"] == FR.REC.size
    # the analysis reads the real CLI output
    fake = {"fa": {"key": "fa", "name": "file a"}, "fb": {"key": "fb", "name": "file b"}}
    a = W.analyse_part({"doc": j}, fake, {"fa": 30.0, "fb": 30.0})
    assert a["fa"]["metrics"]["frames"] == 45 and a["fa"]["metrics"]["integrity"]["valid"] == 1.0
    assert a["fa"]["samples"]["n"] >= 1 and a["fa"]["failure"] is None


def test_cli_multi_usage_and_watchdog_formula():
    _comtypes()
    r = subprocess.run([sys.executable, str(WIN / "pymf" / "cli.py"), "multi", "--timeout-ms", "4000"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 2 and json.loads(r.stdout)["error"]["reason"] == "--spec FILE required"
    from pymf import multi
    assert multi.watchdog_ms is FR.watchdog_ms


def test_hung_session_without_progress_marks_the_kiyo_pro_dead(tmp_path, fake_formats):
    """Part 1 killed at its timeout with no JSON at all: nobody can tell which camera hung. The Kiyo Pro is left out
    of the later parts (never re-opened) and, since integration on 2026-11-11, MARKED dead as a suspected fault (the
    dead rule is conservative); the other cameras are not marked."""
    ctx = FakeCtx(tmp_path, hang=True)
    res = W.run(ctx)
    assert not res.get("errors"), res.get("errors")
    m = res["measurements"]
    assert [mk["key"] for mk in ctx.marks] == [KIYO["key"]]
    assert m["kiyo_pro_fault"]["marked"] is True and m["kiyo_pro_fault"]["suspected"] is True
    assert KIYO["mf_symlink"] not in json.dumps(ctx.specs[1:])
    assert m["session_hangs"][0]["suspects"] and m["session_hangs"][0]["part"] == "all_720p30"
    assert m["cameras"][C922["key"]]["all_720p30"]["ran"] is False
    assert res["verdicts"][f"pymf_multi|{C922['key']}|720p30"]["rating"] == "untested"


def test_hung_session_with_watchdog_progress_marks_the_kiyo(tmp_path, fake_formats):
    ctx = FakeCtx(tmp_path, hang=True, hang_partial={True: {"stage": "streaming", "progress_age_ms": 60000.0}})
    res = W.run(ctx)
    m = res["measurements"]
    assert [x["key"] for x in ctx.marks] == [KIYO["key"]] and ctx.marks[0]["cls"] == "hung_process"
    assert m["kiyo_pro_fault"]["marked"] is True and m["session_hangs"][0]["suspects"] == [W.ck.cam_slug(KIYO)]
    assert KIYO["mf_symlink"] not in json.dumps(ctx.specs[1:])
