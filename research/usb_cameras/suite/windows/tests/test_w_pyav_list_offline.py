"""W-PYAV-LIST offline tests (no camera, no PyAV/FFmpeg call): the listing parsers, the per-call disturbance and
pipe analysis, the rating text, and an end-to-end run with the session helper replaced by synthetic timelines
(healthy cameras; a wedged Kiyo whose list_devices call hangs; a listing that stalls the streaming process).

    uv run --isolated --python 3.12 --no-project --with pytest pytest suite/windows/tests/test_w_pyav_list_offline.py \
        -c suite/common/tests/pytest.ini
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
WIN = HERE.parent
for p in (str(WIN.parent), str(WIN), str(WIN / "helpers"), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import capkit as ck  # noqa: E402
import pyav_list as pl  # noqa: E402
import w_pyav_list as wp  # noqa: E402

LIST_DEVICES_TXT = """[in#0 @ 000] "c922 Pro Stream Webcam" (video)
[in#0 @ 000]   Alternative name "@device_pnp_\\\\?\\usb#vid_046d&pid_085c&mi_00#7&1#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\\global"
[in#0 @ 000] "USB Video Device" (video)
[in#0 @ 000]   Alternative name "@device_pnp_\\\\?\\usb#vid_1532&pid_0e05&mi_00#8&2#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\\global"
[in#0 @ 000] "Microphone (c922)" (audio)
[in#0 @ 000]   Alternative name "@device_cm_{33D9A762}\\wave_{1}"
"""
OPTIONS_TXT = """[in#0 @ 000] DirectShow video device options (from video devices)
[in#0 @ 000]  Pin "Capture" (alternative pin name "0")
[in#0 @ 000]   vcodec=mjpeg  min s=1280x720 fps=5 max s=1280x720 fps=30
[in#0 @ 000]   pixel_format=yuyv422  min s=640x480 fps=5 max s=640x480 fps=30
"""


def test_parsers():
    s = pl.summarise("pyav_list_devices", LIST_DEVICES_TXT)
    assert s["n_devices"] == 2 and s["devices"][1]["name"] == "USB Video Device"
    assert pl.summarise("ffmpeg_list_options", OPTIONS_TXT)["option_lines"] == 2
    assert pl.summarise("ffmpeg_list_options", "Could not enumerate video devices")["could_not"]


def _frames(t0, n, gap_at=None, gap_ms=0.0):
    rows, t = [], t0
    for i in range(n):
        if gap_at is not None and i == gap_at:
            t += int(gap_ms * 1e6)
        rows.append({"seq": i, "qpc_ns": t, "soi": True, "eoi": True})
        t += 33_333_333
    return rows


def test_call_disturbance_and_pipes():
    t0 = 10_000_000_000
    frames = _frames(t0, 300, gap_at=150, gap_ms=400)          # 400 ms stall at ~5 s
    t_gap = frames[150]["qpc_ns"]
    calls = [{"i": 0, "t_start_ns": t0 + 3_000_000_000, "t_end_ns": t0 + 3_200_000_000},
             {"i": 1, "t_start_ns": t_gap - 300_000_000, "t_end_ns": t_gap + 50_000_000}]
    d = wp.call_disturbance(calls, frames, 30.0)
    assert d[0]["disturbed"] is False and d[1]["disturbed"] is True and "gap" in d[1]["why"]
    samples = [{"t_ns": 100, "t_end_ns": 200, "cameras": {"a": {"active": False}, "b": {"active": True}}},
               {"t_ns": 300, "t_end_ns": 400, "cameras": {"a": {"active": True, "current_alt": 1},
                                                          "b": {"active": True}}}]
    base = [{"cameras": {"a": {"active": False}, "b": {"active": True}}}]
    p = wp.pipes_opened(samples, 250, 350, base, skip_key=None)
    assert p["opened"] == {"a": 1} and p["baseline_active"] == ["b"]
    assert wp.pipes_opened(samples, 250, 350, base, skip_key="a")["opened"] == {}


def _cond(cond, **kw):
    return {"condition": cond, "tested": True, "hung": False, "disturbed": None if cond == "idle" else False,
            "stream_started_on_idle_camera": False, "pipes": {"opened": {}}, "faulted_cameras_present": [], **kw}


def test_rate_list_texts():
    ok = wp.rate_list([_cond("idle"), _cond("streaming:a")], "pyav_list_devices")
    assert ok["rating"] == "partial" and ok["summary_label"] == "partial (touches but harmless)"
    dist = wp.rate_list([_cond("idle"), _cond("streaming:a", disturbed=True)], "pyav_list_devices")
    assert dist["summary_label"] == "no (disturbs)"
    pipe = wp.rate_list([_cond("idle", stream_started_on_idle_camera=True, pipes={"opened": {"a": 2}})], "x")
    assert pipe["summary_label"] == "no (disturbs)"
    hang = wp.rate_list([_cond("idle_kiyo_wedged", hung=True, faulted_cameras_present=["kiyo"])], "x")
    assert hang["summary_label"] == "no (hangs on a faulted camera)"
    hang2 = wp.rate_list([_cond("idle", hung=True)], "x")
    assert hang2["summary_label"] == "no (hangs)"
    # list_options binds only the named device: a hang on the healthy C922 is not blamed on the faulted Kiyo
    opt = wp.rate_list([_cond("streaming:c922", hung=True, camera_key="c922", faulted_cameras_present=["kiyo"])],
                       "pyav_list_options")
    assert opt["summary_label"] == "no (hangs)"
    opt_k = wp.rate_list([_cond("idle", hung=True, camera_key="kiyo", faulted_cameras_present=["kiyo"])],
                         "pyav_list_options")
    assert opt_k["summary_label"] == "no (hangs on a faulted camera)"
    un = wp.rate_list([{"condition": "idle", "tested": False, "untested_reason": "ffmpeg CLI not on PATH"}], "x")
    assert un["rating"] == "untested"


# ------------------------------------------------------------------------------------------------ end to end
CAMS = [{"key": "046d:085c:sn=X", "name": "c922", "vid": "046d", "pid": "085c", "serial": "X", "instance_id": "USB\\A",
         "mf_symlink": "\\\\?\\usb#vid_046d&pid_085c#a#{mf}", "ds_path": "\\\\?\\usb#vid_046d&pid_085c#a#{ds}",
         "is_kiyo": False},
        {"key": "1532:0e05:port=P/4.4", "name": "USB Video Device", "vid": "1532", "pid": "0e05", "serial": None,
         "instance_id": "USB\\K", "mf_symlink": "\\\\?\\usb#vid_1532&pid_0e05#k#{mf}",
         "ds_path": "\\\\?\\usb#vid_1532&pid_0e05#k#{ds}", "is_kiyo": True}]


class ListCtx:
    def __init__(self, tmp: Path, kiyo_wedged=False, stall_on_list=False, streamer_summary=None):
        self.out_dir, self.raw_dir = tmp / "out", tmp / "raw"
        self.out_dir.mkdir()
        self.args = SimpleNamespace(quick=True, list_repeats=None, min_fps=30.0, min_height=720, max_height=720,
                                    all_modes=False)
        self.cameras = [dict(c) for c in CAMS]
        self.wincam = Path("wincam.exe")
        self.kiyo_wedged, self.stall = kiyo_wedged, stall_on_list
        self.streamer_summary = streamer_summary or {}       # {camera key: the streamer's summary at stop}
        self.marked = []
        self.sessions = []
        self.clock = 20_000_000_000

    def log(self, m):
        pass

    def test_dir(self, name):
        d = self.out_dir / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def camera_faulted(self, cam):
        return None

    def camera_gated(self, cam):
        return None

    def mark_fault(self, cam, **kw):
        self.marked.append((cam["key"], kw))

    def plug_in_age_s(self, cam):
        return 600.0, "2026-11-08T12:00:00Z"

    def arrivals(self):
        raise RuntimeError("offline")

    def camcmd(self, argv, timeout_s, **k):
        a = [str(x) for x in argv]
        assert a[1].endswith("pyav_list_session.py"), a          # W-PYAV-LIST's only camcmd (reads are patched)
        spec = json.loads(Path(a[2]).read_text(encoding="utf-8"))
        self.sessions.append(spec)
        return {"rc": 0, "stdout": json.dumps(self.fake_session(spec)), "stderr": "", "elapsed_s": 5}

    def fake_session(self, spec):
        od = Path(spec["out_dir"])
        od.mkdir(parents=True, exist_ok=True)
        t = self.clock
        doc = {"condition": spec["condition"], "stream_key": spec["stream_key"], "methods": [], "streamer_runs": [],
               "baseline_topology": [{"cameras": {c["key"]: {"active": c["key"] == spec["stream_key"]}
                                                  for c in spec["cameras"]}}]}
        frames_path = od / "frames.jsonl"
        stalls = []
        t += 2_000_000_000
        for m in spec["methods"]:
            n = 1
            calls = []
            hung = False
            for i in range(n):
                dur = 150_000_000
                if self.kiyo_wedged and spec["condition"].startswith("idle") and m["id"] == "pyav_list_devices":
                    dur, hung = 20_000_000_000, True
                calls.append({"i": i, "t_start_ns": t, "t_end_ns": t + dur, "elapsed_ms": dur / 1e6, "hung": hung,
                              "n_devices": 2 if m["id"].endswith("devices") else None,
                              "option_lines": 4 if m["id"].endswith("options") else None})
                if self.stall and spec["stream_key"] and m["id"] == "ffmpeg_list_options":
                    stalls.append((t + 50_000_000, 500.0))
                t += dur + 1_500_000_000
            so = od / f"{m['id']}_{m.get('camera_slug') or 'all'}.out"
            so.write_text(json.dumps({"method": m["id"], "calls": calls, "hung": hung}), encoding="utf-8")
            doc["methods"].append({"id": m["id"], "camera_key": m.get("camera_key"), "stdout_file": str(so),
                                   "process": {"rc": 5 if hung else 0, "timed_out": False,
                                               "t_start_ns": calls[0]["t_start_ns"] - 500_000_000,
                                               "t_end_ns": calls[-1]["t_end_ns"] + 10_000_000},
                                   "topology_samples": [{"t_ns": calls[0]["t_start_ns"], "t_end_ns": calls[0]["t_end_ns"],
                                                         "cameras": {c["key"]: {"active": c["key"] == spec["stream_key"]}
                                                                     for c in spec["cameras"]}}],
                                   "streamer_alive_after": True if spec["stream_key"] else None})
            t += 1_000_000_000
        if spec["stream_key"]:
            rows, tt, i = [], self.clock, 0
            while tt < t + 1_000_000_000:
                for ts, ms in stalls:
                    if tt <= ts < tt + 33_333_333:
                        tt += int(ms * 1e6)
                rows.append({"seq": i, "qpc_ns": tt, "soi": True, "eoi": True})
                tt += 33_333_333
                i += 1
            frames_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
            doc["streamer_runs"] = [{"index": 1, "started_ok": True, "frames_jsonl": str(frames_path),
                                     "summary": self.streamer_summary.get(spec["stream_key"], {}),
                                     "process": {"rc": 0, "timed_out": False}}]
        self.clock = t + 5_000_000_000
        return doc


def _install(monkeypatch, wedged=False):
    monkeypatch.setattr(ck, "get_formats", lambda ctx, c, cache=None: (
        {"reader_streams": [{"types": [{"subtype": "MJPG", "width": 1280, "height": 720, "fps_num": 30,
                                        "fps_den": 1}]}]}, {}))
    dna = {"device_not_answering": True, "error": {"hr": "0x8007001F", "stage": "control_get"}, "controls": []}
    monkeypatch.setattr(ck, "get_controls", lambda ctx, c, api="mf", **k: (
        (dna, {"rc": 4}) if (wedged and c.get("is_kiyo")) else
        ({"controls": [{"name": "exposure", "supported": True, "get_ok": True, "value": -5}]}, {"rc": 0})))
    monkeypatch.setattr(wp.shutil, "which", lambda name: "C:/ffmpeg/bin/ffmpeg.exe")


def test_end_to_end_healthy(tmp_path, monkeypatch):
    _install(monkeypatch)
    ctx = ListCtx(tmp_path)
    res = wp.run(ctx)
    v = res["verdicts"]
    assert {k.split("|", 1)[1] for k in v} == {"all|pyav_list_devices", "all|ffmpeg_list_devices"} | \
        {f"{c['key']}|{m}" for c in CAMS for m in wp.OPTION_METHODS}
    assert {x["summary_label"] for x in v.values()} == {"partial (touches but harmless)"}
    assert [s["condition"] for s in ctx.sessions] == ["idle"] + [f"streaming:{c['key']}" for c in CAMS]
    conds = {c["condition"] for c in v["list_touch|all|pyav_list_devices"]["evidence"]["conditions"]}
    assert conds == {"idle"} | {f"streaming:{c['key']}" for c in CAMS}
    (tmp_path / "out" / "W-PYAV-LIST.json").write_text(json.dumps(res), encoding="utf-8")
    assert wp.reanalyze(tmp_path / "out")["changes"] == []


def test_end_to_end_wedged_kiyo_hang(tmp_path, monkeypatch):
    _install(monkeypatch, wedged=True)
    ctx = ListCtx(tmp_path, kiyo_wedged=True)
    res = wp.run(ctx)
    v = res["verdicts"]
    assert res["measurements"]["kiyo_as_found"][CAMS[1]["key"]]["wedged"] is True
    assert v["list_touch|all|pyav_list_devices"]["summary_label"] == "no (hangs on a faulted camera)"
    assert v["list_touch|all|ffmpeg_list_devices"]["summary_label"] == "partial (touches but harmless)"
    # the wedged Kiyo's own streaming condition is skipped, the C922's still runs
    assert [s["condition"] for s in ctx.sessions] == ["idle_kiyo_wedged", f"streaming:{CAMS[0]['key']}"]
    kiyo_opt = v[f"list_touch|{CAMS[1]['key']}|pyav_list_options"]["evidence"]["conditions"]
    assert any(str(c.get("untested_reason")).startswith("camera wedged") for c in kiyo_opt)


def test_streamer_fault_after_first_frame_is_marked(tmp_path, monkeypatch):
    """A streamer that started fine but failed later (0x8007001F at stop) must reach the fault gate: the session's
    argv names no device, so camcmd's own scan cannot see it."""
    _install(monkeypatch)
    kiyo = CAMS[1]["key"]
    ctx = ListCtx(tmp_path, streamer_summary={kiyo: {"ok": False, "error": {"hr": "0x8007001F", "stage": "read_sample",
                                                                         "class": "device_error"}}})
    res = wp.run(ctx)
    assert [k for k, _ in ctx.marked] == [kiyo]
    assert ctx.marked[0][1]["code"] == "0x8007001F" and ctx.marked[0][1]["detail"]["started_ok"] is True
    assert res["measurements"]["sessions"][f"streaming_{ck.cam_slug(CAMS[1])}"]["streamer_fault"]["class"] == "device_error"
    # a streamer killed at its stop timeout (hang at reader release) is a fault too; a clean run is not
    assert wp.streamer_fault({"streamer_runs": [{"index": 1, "started_ok": True, "summary": None,
                                                 "process": {"timed_out": True}}]})["class"] == "hung_process"
    assert wp.streamer_fault({"streamer_runs": [{"index": 1, "started_ok": True, "summary": {"ok": True},
                                                 "process": {"timed_out": False}}]}) is None


def test_end_to_end_listing_stalls_stream(tmp_path, monkeypatch):
    _install(monkeypatch)
    res = wp.run(ListCtx(tmp_path, stall_on_list=True))
    v = res["verdicts"]
    assert v[f"list_touch|{CAMS[0]['key']}|ffmpeg_list_options"]["summary_label"] == "no (disturbs)"
    assert v[f"list_touch|{CAMS[0]['key']}|pyav_list_options"]["summary_label"] == "partial (touches but harmless)"


# ------------------------------------------------------------------------------------------------ session helper
FAKE_STREAMER = r'''
import json, sys, time
from pathlib import Path
out, stop = Path(sys.argv[1]), Path(sys.argv[2])
i = 0
with open(out / "frames.jsonl", "w") as f:
    t_end = time.monotonic() + 30
    while not stop.exists() and time.monotonic() < t_end:
        f.write(json.dumps({"seq": i, "qpc_ns": time.perf_counter_ns(), "soi": True, "eoi": True}) + "\n")
        f.flush()
        i += 1
        time.sleep(0.033)
print(json.dumps({"ok": True, "frames": {"total": i}, "stopped_by_stop_file": stop.exists()}))
'''
FAKE_LISTER = r'''
import json, sys, time
calls = []
for i in range(2):
    t0 = time.perf_counter_ns(); time.sleep(0.05); t1 = time.perf_counter_ns()
    calls.append({"i": i, "t_start_ns": t0, "t_end_ns": t1, "elapsed_ms": (t1 - t0) / 1e6, "hung": False,
                  "n_devices": 2})
    time.sleep(0.2)
print(json.dumps({"method": sys.argv[1], "calls": calls, "hung": False}))
'''


def test_session_helper_in_process(tmp_path, monkeypatch, capsys):
    import types
    import pyav_list_session as S
    fake_wt = types.SimpleNamespace(
        collect=lambda descriptor_file=None: {},
        observed_alts=lambda snap: {CAMS[0]["key"]: {"device_id": "USB\\A", "iso_pipes": [{"ep": 1}], "current_alt": 9},
                                    CAMS[1]["key"]: {"device_id": "USB\\K", "iso_pipes": [], "current_alt": 0}})
    monkeypatch.setitem(sys.modules, "win_topology", fake_wt)
    (tmp_path / "streamer.py").write_text(FAKE_STREAMER, encoding="utf-8")
    (tmp_path / "lister.py").write_text(FAKE_LISTER, encoding="utf-8")
    spec = {"label": "streaming_c922", "condition": "streaming", "stream_key": CAMS[0]["key"],
            "cameras": [{k: c[k] for k in ("key", "name", "instance_id")} for c in CAMS],
            "out_dir": str(tmp_path / "sess"),
            "streamer": {"argv": [sys.executable, str(tmp_path / "streamer.py"), "{out_dir}", "{stop_file}"],
                         "first_frame_timeout_s": 10, "stop_timeout_s": 10},
            "baseline_s": 0.8, "settle_s": 0.3, "descriptor_file": None, "sample": {"interval_s": 0.05},
            "methods": [{"id": "pyav_list_devices", "camera_key": None, "camera_slug": None,
                         "argv": [sys.executable, str(tmp_path / "lister.py"), "pyav_list_devices"], "timeout_s": 20}]}
    sp = tmp_path / "spec.json"
    sp.write_text(json.dumps(spec), encoding="utf-8")
    assert S.main(str(sp)) == 0
    doc = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert doc["streamer_runs"][0]["started_ok"] and doc["methods"][0]["streamer_alive_after"] is True
    assert doc["baseline_topology"][0]["cameras"][CAMS[0]["key"]]["active"] is True
    rows = wp.analyse_session(doc, "streaming:" + CAMS[0]["key"], 30.0, [])
    r = rows[0]
    assert r["tested"] and not r["hung"] and r["calls"] == 2
    assert r["disturbed"] is False and r["stream_started_on_idle_camera"] is False      # streamed camera skipped
    assert r["pipes"]["samples_in_window"] >= 1


def test_condition_criterion_classifies_by_prefix():
    """Review round 3: the idle session is 'idle_kiyo_wedged' when the Kiyo is wedged; an idle row alone is not a
    streaming condition."""
    def met(conds):
        r = wp.rate_list(conds, "x")
        return next(c for c in r["criteria"] if c["criterion"] == "idle and streaming conditions measured")["met"]
    assert met([_cond("idle_kiyo_wedged"), _cond("streaming:a")]) is True
    assert met([_cond("idle"), _cond("streaming:a")]) is True
    assert met([_cond("idle_kiyo_wedged")]) is False
    assert met([_cond("streaming:a")]) is False
