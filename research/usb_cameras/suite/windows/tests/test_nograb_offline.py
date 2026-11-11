"""W-FMT-NOGRAB analysis and the capture tests' mode-scope choices, offline (no camera).

    uv run --isolated --python 3.12 --no-project --with pytest pytest suite/windows/tests/test_nograb_offline.py \
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
import w_fmt_nograb as N  # noqa: E402
from common import rating  # noqa: E402

FFMPEG_TXT = """[in#0 @ 0000] DirectShow video device options (from video devices)
[in#0 @ 0000]  Pin "Capture" (alternative pin name "0")
[in#0 @ 0000]   pixel_format=yuyv422  min s=640x480 fps=5 max s=640x480 fps=30
[in#0 @ 0000]   pixel_format=yuyv422  min s=640x480 fps=5 max s=640x480 fps=30 (tv, bt470bg/bt709/unknown, topleft)
[in#0 @ 0000]   vcodec=mjpeg  min s=1280x720 fps=5 max s=1280x720 fps=30
[in#0 @ 0000]   vcodec=mjpeg  min s=1280x720 fps=7.5 max s=1280x720 fps=7.5 (pc, bt470bg/bt709/unknown, center)
[in#0 @ 0000]  Pin "Still" (alternative pin name "1")
[in#0 @ 0000]   vcodec=mjpeg  min s=2592x1944 fps=5 max s=2592x1944 fps=5
"""
IV = {30: 333333, 15: 666667, 7.5: 1333333, 5: 2000000}


def test_parse_ffmpeg_list_options_min_max_only_and_still_skipped():
    modes, info = N.parse_ffmpeg_list_options(FFMPEG_TXT)
    assert ("YUY2", 640, 480, IV[30]) in modes and ("YUY2", 640, 480, IV[5]) in modes
    assert ("MJPG", 1280, 720, IV[7.5]) in modes
    assert not any(w == 2592 for _, w, _, _ in modes)          # still pin skipped
    assert info["pins"] == {"Capture": 4, "Still": 0} and info["option_lines"] == 5


def _write(p: Path, text: str) -> str:
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_analyse_session_idle_ffmpeg_and_hub(tmp_path):
    ref = {("MJPG", 1280, 720, IV[30]), ("MJPG", 1280, 720, IV[15]), ("MJPG", 1280, 720, IV[5]),
           ("MJPG", 1280, 720, IV[7.5]), ("YUY2", 640, 480, IV[30]), ("YUY2", 640, 480, IV[5])}
    t0 = 10_000_000_000
    ff_main = {"id": "ffmpeg", "tag": "main", "process": {"rc": 0, "t_start_ns": t0, "t_end_ns": t0 + 400_000_000,
                                                          "elapsed_s": 0.4},
               "stdout_file": _write(tmp_path / "ff.out", ""), "stderr_file": _write(tmp_path / "ff.err", FFMPEG_TXT),
               "hold": None, "topology_samples": [{"t_ns": t0 + 1000, "collect_ms": 45, "active": False,
                                                   "blocker_running": False}]}
    ff_blk = dict(ff_main, tag="blocking", topology_samples=[],
                  blocker={"ok": True, "open_to_first_frame_ms": 330.0, "first_frame_ns": t0 + 500_000_000})
    doc = {"methods": [ff_main, ff_blk], "baseline_topology": [{"active": False}],
           "control_blocker": {"ok": True, "open_to_first_frame_ms": 325.0}}
    out = N.analyse_session(doc, ref, "idle", 30.0)["ffmpeg"]
    # 15 fps is between min and max: ffmpeg cannot list it
    assert out["succeeded"] and not out["complete"]
    assert out["comparison"]["per_class"]["mjpeg"]["missing"] == ["MJPG 1280x720@15"]
    assert out["stream_started"] is False and out["blocked"] is False and out["disturbed"] is None
    conds = {"idle": {k: out.get(k) for k in ("tested", "succeeded", "complete", "disturbed", "stream_started",
                                               "blocked")}}
    assert rating.rate_fmt_nograb(conds)["rating"] == "no"


def test_analyse_session_streaming_disturbance_from_streamer_frames(tmp_path):
    ref = {("MJPG", 1280, 720, IV[30])}
    frames = tmp_path / "frames.jsonl"
    t = 0
    rows = []
    for i in range(300):                 # 10 s at 30 fps with a 400 ms stall at frame 150 (inside the window)
        if i == 150:
            t += 400_000_000
        rows.append(json.dumps({"seq": i, "qpc_ns": t, "soi": True, "eoi": True, "eoi_trailing_bytes": 0}))
        t += 33_333_333
    frames.write_text("\n".join(rows) + "\n", encoding="utf-8")
    hub_out = {"devices": [{"configuration": {"uvc": {"streaming_interfaces": [{"formats": [
        {"format": "MJPEG", "frames": [{"wWidth": 1280, "wHeight": 720, "dwFrameInterval": [IV[30]]}]}]}]}},
        "errors": []}]}
    rec = {"id": "hub_ioctl", "tag": "main", "streamer_index": 1, "streamer_alive_after": True,
           "process": {"rc": 0, "t_start_ns": 4_500_000_000, "t_end_ns": 5_800_000_000, "elapsed_s": 1.3},
           "stdout_file": _write(tmp_path / "hub.out", json.dumps(hub_out)),
           "stderr_file": _write(tmp_path / "hub.err", ""), "hold": None,
           "topology_samples": [{"t_ns": 4_600_000_000, "collect_ms": 45, "active": True, "current_alt": 9}]}
    doc = {"methods": [rec], "baseline_topology": [{"active": True, "current_alt": 9}], "control_blocker": None,
           "streamer_runs": [{"index": 1, "started_ok": True, "frames_jsonl": str(frames)}]}
    out = N.analyse_session(doc, ref, "streaming_native", 30.0)["hub_ioctl"]
    assert out["complete"] and out["disturbed"] is True and "gap" in out["disturbance"]["why"]
    assert out["stream_started"] is None and out["blocked"] is None          # decided in the idle condition only
    assert out["pipe_change"]["changed"] is False


def test_stream_samples_exclude_snapshots_overlapping_the_third_process_open():
    """Live 2026-11-06 (generic camera, ds): a 380 ms snapshot that STARTED while the 1-frame third-process open ran
    saw that open's pipe; its flag was read after the collect (open finished), so it was blamed on the method."""
    ms = 1_000_000
    rec = {"process": {"t_start_ns": 0, "t_end_ns": 2600 * ms}, "hold": {"end_seen_ns": 2550 * ms},
           "blocker": {"t_start_ns": 640 * ms, "t_end_ns": 1050 * ms},
           "topology_samples": [
               {"t_ns": 100 * ms, "collect_ms": 50, "active": False, "blocker_running": False},
               {"t_ns": 860 * ms, "collect_ms": 380, "active": True, "blocker_running": False},   # overlaps the open
               {"t_ns": 1300 * ms, "collect_ms": 300, "active": False, "blocker_running": False},  # within the tail
               {"t_ns": 1800 * ms, "collect_ms": 300, "active": False, "blocker_running": False},
               {"t_ns": 2200 * ms, "t_end_ns": 2500 * ms, "active": False, "blocker_running": True}]}
    got = N.method_stream_samples(rec)
    assert [s["t_ns"] // ms for s in got] == [100, 1800]
    from common import nograb
    assert nograb.stream_started(got) is False


def test_method_blocking_delayed_until_release():
    control = {"ok": True, "open_to_first_frame_ms": 300.0}
    rec = {"hold": {"begin_ns": 1_000, "end_ns": 3_000_000_000, "begin_seen_ns": 1_000, "end_seen_ns": 3_000_000_000},
           "blocker": {"ok": True, "open_to_first_frame_ms": 2400.0, "first_frame_ns": 3_200_000_000,
                       "t_start_ns": 600_000_000}}
    b = N.method_blocking(rec, control)
    assert b["delayed_until_release"] is True and b["blocked"] is True and b["blocker_started_in_hold"] is True
    rec["blocker"].update(open_to_first_frame_ms=320.0, first_frame_ns=1_000_000_000)
    assert N.method_blocking(rec, control)["blocked"] is False
    assert N.method_blocking(rec, {"ok": False})["blocked"] is None


def test_capkit_scope_choices_on_gerald_modes():
    c922 = [ck.Mode(w, h, f, 1) for w, h, f in ((1920, 1080, 30), (1920, 1080, 5), (1600, 896, 30), (1280, 720, 60),
                                                (1280, 720, 30), (960, 720, 30), (640, 480, 30), (640, 480, 5))]
    ctx = SimpleNamespace(args=SimpleNamespace(min_fps=30, min_height=720, all_modes=False))
    kept, rec = ck.scoped(ctx, c922)
    assert rec["in_scope"] == 3 and rec["excluded"] == 5            # exactly 720 lines (Dom 2026-11-08)
    d, rec = ck.scoped_default(ctx, c922)
    assert d == ck.Mode(1280, 720, 30, 1) and rec["default_mode"] == "MJPG 1280x720@30"
    assert ck.switch_mode(kept, d) == ck.Mode(960, 720, 30, 1)
    wide = SimpleNamespace(args=SimpleNamespace(min_fps=30, min_height=720, max_height=0, all_modes=False))
    kept_w, rec_w = ck.scoped(wide, c922)
    assert rec_w["in_scope"] == 5 and ck.switch_mode(kept_w, d) == ck.Mode(1920, 1080, 30, 1)
    kiyo720 = [ck.Mode(1280, 720, 30, 1), ck.Mode(1280, 720, 60, 1), ck.Mode(640, 480, 30, 1)]
    kept, _ = ck.scoped(ctx, kiyo720)
    assert ck.switch_mode(kept, ck.default_mode(kept)) == ck.Mode(1280, 720, 60, 1)
    small = [ck.Mode(640, 480, 30, 1), ck.Mode(1280, 720, 10, 1)]
    d, rec = ck.scoped_default(ctx, small)
    assert d is None and rec["untested_reason"].startswith("untested (scope)")
    v = ck.scope_untested(ctx, rec)
    assert v["rating"] == "untested" and v["summary_label"] == "untested (scope)" and v["evidence"]["scope_excluded"]
    ctx.args.all_modes = True
    d, _ = ck.scoped_default(ctx, small)
    assert d == ck.Mode(1280, 720, 10, 1)


def test_activity_entry_matches_mf_and_ds_links():
    doc = {"ok": True, "devices": [{"match_key": "usb#vid_046d&pid_085c&mi_00#8&268da596&0&0000\\global",
                                    "processes": [{"pid": 1, "name": "LogiTuneAgent.exe", "streaming": False}]}]}
    cam = {"mf_symlink": "\\\\?\\usb#vid_046d&pid_085c&mi_00#8&268da596&0&0000#{e5323777-f976-4f5b-9b55-b94699c46e44}"
                         "\\global"}
    assert ck.activity_entry(doc, cam)["processes"][0]["name"] == "LogiTuneAgent.exe"
    cam = {"ds_path": "\\\\?\\usb#vid_046d&pid_085c&mi_00#8&268da596&0&0000#{65e8773d-8f56-11d0-a3b9-00a0c9223196}"
                      "\\global"}
    assert ck.activity_entry(doc, cam) is not None
    rec = ck.activity_for_camera(None, cam, doc=doc)
    assert rec["other_processes"][0]["pid"] == 1 and rec["streaming_by_other"] is False


def test_no_in_scope_mode_streams_nothing(tmp_path, monkeypatch):
    """Dom 2026-11-08: a camera whose MJPEG modes are all out of scope gets NO streaming condition and NO idle
    blocker (no fallback to the nearest advertised mode); only the idle listing session runs."""
    cam = {"key": "k", "name": "Small cam", "vid": "1111", "pid": "2222", "serial": "S", "instance_id": "USB/X",
           "mf_symlink": "usb#vid_1111&pid_2222#s#global", "ds_path": "@device:pnp:x"}
    small = [ck.Mode(640, 480, 30, 1), ck.Mode(1280, 720, 10, 1)]
    specs: list[dict] = []

    class Ctx:
        cameras = [cam]
        args = SimpleNamespace(min_fps=30, min_height=720, all_modes=False, quick=True)
        out_dir = tmp_path / "out"
        raw_dir = tmp_path / "raw"
        wincam = Path("wincam.exe")

        def test_dir(self, t):
            d = self.out_dir / t
            d.mkdir(parents=True, exist_ok=True)
            return d

        def log(self, m):
            pass

        def camera_gated(self, c):
            return None

        def camera_faulted(self, c):
            return None

        def camcmd(self, argv, timeout_s=0, **kw):
            specs.append(json.loads(Path(argv[-1]).read_text(encoding="utf-8")))
            return {"rc": 1, "stdout": "", "stderr": "fixture"}

    monkeypatch.setattr(N.U, "get_descriptors", lambda ctx: {"devices": []})
    monkeypatch.setattr(N.U, "descriptor_for", lambda d, c: {"fixture": True})
    monkeypatch.setattr(N, "reference_modes", lambda d: {("MJPG", 640, 480, 333333)})
    monkeypatch.setattr(N, "build_methods", lambda ctx, c: ([{"id": "mf", "hold": True}], {}))
    monkeypatch.setattr(N, "idle_hold_session", lambda *a, **k: ({}, None))
    monkeypatch.setattr(ck, "get_formats", lambda ctx, c, cache=None: ({"fixture": True}, {}))
    monkeypatch.setattr(ck, "mjpeg_modes", lambda fm: small)
    monkeypatch.setattr(ck, "wincam_activity", lambda ctx: {"ok": None})
    monkeypatch.setattr(ck, "activity_for_camera", lambda ctx, c, doc=None: {"ok": None})
    monkeypatch.setattr(N.U, "start", lambda ctx, t: {"test": t})
    monkeypatch.setattr(N.U, "finish", lambda ctx, res, m, v, e: {"measurements": m, "verdicts": v, "errors": e})
    res = N.run(Ctx())
    crec = res["measurements"]["cameras"]["k"]
    assert crec["stream_mode"] is None and crec["idle_blocker_untested"].startswith("untested (scope)")
    assert [s["condition"] for s in specs] == ["idle"]                  # only the idle listing session ran
    assert specs[0]["blocker"] is None and specs[0]["streamer"] is None
    for cond in ("streaming_native", "streaming_second_api"):
        assert crec["results"]["mf"][cond]["untested_reason"].startswith("untested (scope)"), cond
