"""Offline tests for W-TBUMP and helpers/skellycam_record.py (no camera is opened, no skellycam is started).

    uv run --isolated --python 3.12 --no-project --with pytest pytest suite/windows/tests/test_w_tbump_offline.py

Covers: camera identity resolution (DS DevicePath, MF symlink by device instance, VID:PID, index, id, ambiguity),
the group/apply body, timestamps-CSV analysis (columns, monotonic, fps), recording verification (lockstep frame
counts, missing files), server-log scan and fault attribution (the Kiyo Pro's first-frame failure, a sibling abort,
a connect timeout, 0x8007001F); the driver end to end against a FAKE skellycam HTTP server (API call sequence,
unresolved camera, a Kiyo Pro start failure, a connect timeout, clean shutdown); and W-TBUMP with a fake ctx
(dead / gated exclusion, two recordings, a Kiyo Pro fault reported and never retried, regression / change ratings,
missing checkout). The last test verifies a real MJPEG AVI through the driver's own PEP 723 environment (uv) and is
skipped when uv cannot build that environment.
"""
from __future__ import annotations

import json
import os
import shutil
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

import skellycam_record as sr  # noqa: E402
import w_tbump  # noqa: E402

DS_GUID = "{65e8773d-8f56-11d0-a3b9-00a0c9223196}"
MF_GUID = "{e5323777-f976-4f5b-9b55-b94699c46e44}"


def ds(inst: str) -> str:
    return f"\\\\?\\usb#{inst}#{DS_GUID}\\global"


def mf(inst: str) -> str:
    return f"\\\\?\\usb#{inst}#{MF_GUID}\\global"


I_C922A, I_C922B = "vid_046d&pid_085c&mi_00#7&1111&0&0000", "vid_046d&pid_085c&mi_00#7&2222&0&0000"
I_KIYO, I_GEN = "vid_1532&pid_0e05&mi_00#7&3333&0&0000", "vid_0c45&pid_6366&mi_00#7&4444&0&0000"
DETECTED = [
    {"index": 0, "name": "C922 Pro Stream Webcam", "vendor_id": 0x046D, "product_id": 0x085C, "path": ds(I_C922A),
     "backend_id": 700, "backend_name": "DSHOW", "camera_id": "a1b2"},
    {"index": 1, "name": "C922 Pro Stream Webcam", "vendor_id": 0x046D, "product_id": 0x085C, "path": ds(I_C922B),
     "backend_id": 700, "backend_name": "DSHOW", "camera_id": "c3d4"},
    {"index": 2, "name": "Razer Kiyo Pro", "vendor_id": 0x1532, "product_id": 0x0E05, "path": ds(I_KIYO),
     "backend_id": 700, "backend_name": "DSHOW", "camera_id": "e5f6"},
    {"index": 3, "name": "USB Camera", "vendor_id": 0x0C45, "product_id": 0x6366, "path": ds(I_GEN),
     "backend_id": 700, "backend_name": "DSHOW", "camera_id": "0718"},
]
CAMERA_COLUMNS = ["recording_frame_number", "connection_frame_number", "timestamp.from_recording_start.sec",
                  "timestamp.utc.seconds", "timestamp.local.iso8601", "timestamp.perf_counter_ns.ns",
                  "from_previous.frame_duration.ms", "from_previous.framerate.hz", "frame.initialized.ns",
                  "frame.pre_frame_grab.ns", "frame.post_frame_grab.ns", "frame.pre_frame_retrieve.ns",
                  "frame.post_frame_retrieve.ns", "frame.pre_copy_to_camera_shm.ns", "frame.post_copy_to_camera_shm.ns",
                  "frame.pre_frame_record.ns", "frame.post_frame_record.ns", "duration.idle_before_frame_grab.ns",
                  "duration.during_frame_grab.ns", "duration.idle_before_retrieve.ns",
                  "duration.during_frame_retrieve.ns", "duration.idle_before_copy_to_camera_shm.ns",
                  "duration.during_copy_to_camera_shm.ns", "duration.idle_before_frame_record.ns",
                  "duration.during_frame_record.ns", "total.frame_processing_time.ns", "total.camera_idle_time.ns"]


# ============================================================================================================ fake recording
def write_camera_csv(path: Path, n: int, step_ns: int = 33_333_333, t0: int = 10 ** 12, backstep_at: int | None = None,
                     drop_columns: tuple = ()) -> None:
    cols = [c for c in CAMERA_COLUMNS if c not in drop_columns]
    lines = [",".join(cols)]
    for i in range(n):
        t = t0 + i * step_ns - (step_ns * 2 if backstep_at is not None and i == backstep_at else 0)
        row = {c: "0" for c in cols}
        row.update({"recording_frame_number": str(i), "connection_frame_number": str(100 + i),
                    "timestamp.from_recording_start.sec": f"{(t - t0) / 1e9 + 0.01:.6f}",
                    "timestamp.utc.seconds": f"{1.7e9 + (t - t0) / 1e9:.6f}",
                    "timestamp.local.iso8601": "2026-11-11T22:00:00.000000-05:00",
                    "timestamp.perf_counter_ns.ns": str(t),
                    "from_previous.frame_duration.ms": "nan" if i == 0 else f"{step_ns / 1e6:.4f}",
                    "from_previous.framerate.hz": "nan" if i == 0 else f"{1e9 / step_ns:.4f}"})
        lines.append(",".join(row[c] for c in cols))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_recording(root: Path, name: str, cams: list[tuple[str, int]], frames: dict[str, int] | int = 60,
                    video_bytes: bytes = b"\0" * 4096, skip_video: str | None = None) -> Path:
    rd = root / name
    vd = rd / "synchronized_videos"
    td = vd / "timestamps"
    (td / "camera_timestamps").mkdir(parents=True, exist_ok=True)
    (rd / f"{name}_info.json").write_text(json.dumps({"recording_name": name, "camera_configs": {
        cid: {"camera_index": idx, "camera_name": f"cam{idx}"} for cid, idx in cams}}), encoding="utf-8")
    for cid, idx in cams:
        n = frames if isinstance(frames, int) else frames[cid]
        if cid != skip_video:
            (vd / f"{name}.id-{cid}.idx-{idx}.mp4").write_bytes(video_bytes)
        write_camera_csv(td / "camera_timestamps" / f"{name}.camera{cid}.timestamps.csv", n)
    n0 = frames if isinstance(frames, int) else min(frames.values())
    mf_lines = ["multiframe_number,timestamp.from_recording_start.sec,timestamp.perf_counter_ns.ns,"
                "inter_camera.frame_grab_range.ms"]
    for i in range(n0):
        mf_lines.append(f"{i},{i / 30:.6f},{10 ** 12 + i * 33_333_333}.0,{0.5 + (i % 3) * 0.1:.3f}")
    (td / f"{name}_timestamps.csv").write_text("\n".join(mf_lines) + "\n", encoding="utf-8")
    (td / f"{name}_stats.json").write_text(json.dumps({"number_of_frames": n0}), encoding="utf-8")
    return rd


# ============================================================================================================ identity
def test_instance_key_joins_mf_symlink_and_ds_devicepath():
    assert sr.instance_key(ds(I_KIYO)) == sr.instance_key(mf(I_KIYO)) == "usb#" + I_KIYO
    assert sr.instance_key(ds(I_C922A)) != sr.instance_key(ds(I_C922B))
    assert sr.instance_key(None) is None


def test_resolve_specs_all_kinds_and_errors():
    res, errs = sr.resolve_specs([f"ds:{ds(I_C922A)}", f"mf:{mf(I_KIYO)}", "index:3", "id:c3d4"], DETECTED)
    assert not errs
    assert [r["camera_index"] for r in res] == [0, 2, 3, 1]
    assert res[0]["how"] == "device_path_exact" and res[1]["how"] == "device_instance"
    assert res[1]["is_kiyo_pro"] and not res[0]["is_kiyo_pro"]
    assert res[1]["camera_id"] == "e5f6"
    res, errs = sr.resolve_specs(["vidpid:1532:0e05"], DETECTED)
    assert res[0]["camera_index"] == 2 and not errs
    res, errs = sr.resolve_specs(["vidpid:046d:085c", "index:9", f"ds:{ds('vid_dead&pid_beef#x')}"], DETECTED)
    assert not res and len(errs) == 3
    assert "ambiguous" in errs[0]["error"] and "no detected camera" in errs[1]["error"]
    res, errs = sr.resolve_specs(["index:2", f"mf:{mf(I_KIYO)}"], DETECTED)
    assert len(errs) == 1 and "same camera" in errs[0]["error"]
    with pytest.raises(ValueError):
        sr.parse_spec("bogus")
    assert sr.parse_spec("2") == ("index", "2")
    assert sr.parse_spec(ds(I_GEN))[0] == "path"


def test_group_apply_body_has_exactly_the_resolved_cameras():
    res, _ = sr.resolve_specs(["index:0", "index:2"], DETECTED)
    body = sr.camera_configs_body(res, 1280, 720, 30, "MJPG", "MANUAL", -7, None)
    cfg = body["camera_configs"]
    assert sorted(cfg) == ["a1b2", "e5f6"]
    assert cfg["e5f6"]["camera_index"] == 2 and cfg["e5f6"]["capture_fourcc"] == "MJPG"
    assert cfg["a1b2"]["resolution"] == {"width": 1280, "height": 720} and cfg["a1b2"]["framerate"] == 30.0
    assert "writer_fourcc" not in cfg["a1b2"]
    assert sr.camera_configs_body(res, 1280, 720, 30, "MJPG", "AUTO", -7, "MJPG")["camera_configs"]["a1b2"][
        "writer_fourcc"] == "MJPG"


# ============================================================================================================ verify
def test_camera_csv_analysis_good(tmp_path):
    p = tmp_path / "c.csv"
    write_camera_csv(p, 90)
    a = sr.analyse_camera_csv(p)
    assert a["rows"] == 90 and a["columns_missing"] == [] and a["monotonic"] and a["frame_numbers_contiguous"]
    assert abs(a["fps_from_timestamps"] - 30.0) < 0.01
    assert a["connection_frame_gaps"] == 0 and a["problems"] == []
    assert a["timestamps"]["long_intervals_gt_1p5x_median"] == 0


def test_camera_csv_analysis_flags_backstep_and_missing_columns(tmp_path):
    p = tmp_path / "c.csv"
    write_camera_csv(p, 30, backstep_at=10, drop_columns=("timestamp.utc.seconds",))
    a = sr.analyse_camera_csv(p)
    assert not a["monotonic"] and a["timestamps"]["non_increasing_steps"] >= 1
    assert a["columns_missing"] == ["timestamp.utc.seconds"]
    assert any("not strictly increasing" in x for x in a["problems"])
    assert sr.analyse_camera_csv(tmp_path / "missing.csv")["problems"] == ["timestamps CSV missing"]


def test_verify_recording_lockstep_and_missing_files(tmp_path):
    cams = [("a1b2", 0), ("e5f6", 2)]
    rd = write_recording(tmp_path, "rec", cams, 60)
    v = sr.verify_recording(rd, "rec", media="none")
    assert v["ok"], v["problems"]
    assert v["frame_counts"] == {"a1b2": 60, "e5f6": 60} and v["frame_counts_equal"] and v["frames"] == 60
    assert v["multiframe_csv"]["rows"] == 60 and v["camera_source"] == "recording files"
    rd2 = write_recording(tmp_path, "rec2", cams, {"a1b2": 60, "e5f6": 59}, skip_video="e5f6")
    v2 = sr.verify_recording(rd2, "rec2", cameras=[{"camera_id": c, "camera_index": i, "name": None} for c, i in cams],
                             media="none")
    assert not v2["ok"] and not v2["frame_counts_equal"]
    assert any("lockstep" in p for p in v2["problems"])
    assert any("e5f6: video file missing" in p for p in v2["problems"])
    assert not sr.verify_recording(tmp_path / "nope", "nope", media="none")["ok"]


def test_server_log_scan():
    txt = "\n".join([
        "\x1b[32m└>> SkellyCam API started |  SUCCESS |  1ms | a.b():1 | t |\x1b[0m",
        "\x1b[31m└>> Failed to grab frame from camera a1b2. Retrying... |  ERROR |  2ms | x.y():77 | t |\x1b[0m",
        "└>> Failed to grab frame from camera c3d4. Retrying... |  ERROR |  2ms | x.y():77 | t |",
        "Traceback (most recent call last):",
        "--- Logging error ---",
        "[ WARN:0@1.0] global cap_dshow.cpp:1 hr=0x8007001F",
        "└>> Requested video codec 'X264' is not available on this system. Probing |  WARNING |",
        "└>> Using fallback video codec: X264_PYAV |  INFO |",
    ])
    s = sr.scan_server_log(txt)
    assert s["error_lines"] == 2 and s["tracebacks"] == 1 and s["logging_errors"] == 1
    assert len(s["error_kinds"]) == 1          # both grab failures are one error kind
    assert len(s["hr_0x8007001F_lines"]) == 1
    assert "Using fallback video codec: X264_PYAV" in s["writer_codec_lines"]


def test_fault_hints_attribute_the_kiyo_pro_not_its_siblings():
    res, _ = sr.resolve_specs([f"ds:{ds(I_C922A)}", f"ds:{ds(I_KIYO)}", f"ds:{ds(I_GEN)}"], DETECTED)
    log_ = "\n".join([
        "└>> Camera a1b2 connected, awaiting shm message... |  DEBUG |",
        "└>> Failed to read frame from camera 2. Retrying... (1/5) |  WARNING |",
        "└>> Failed to create cv2.VideoCapture for camera 0718: Failed to initialize camera_group_shm |  ERROR |",
        "└>> Failed to create cv2.VideoCapture for camera e5f6:  |  ERROR |",
    ])
    h = sr.fault_hints(log_, res, {"ok": False, "status": 500, "timed_out": False})
    assert len(h) == 1 and h[0]["camera_id"] == "e5f6" and h[0]["is_kiyo_pro"]
    assert h[0]["code"] == "first_frame_failed" and h[0]["spec"] == f"ds:{ds(I_KIYO)}"
    # a connect timeout with nothing in the log: the cameras that never logged 'connected' are the suspects
    h2 = sr.fault_hints("└>> Camera a1b2 connected, awaiting shm message... |  DEBUG |", res,
                        {"ok": False, "timed_out": True, "error": "timeout"})
    assert sorted(x["camera_id"] for x in h2) == ["0718", "e5f6"]
    assert all(x["code"] == "connect_timeout" for x in h2)
    # 0x8007001F on a line naming one camera upgrades its code; on no camera it is unattributed
    h3 = sr.fault_hints("└>> Failed to grab frame from camera e5f6 hr=0x8007001F |  ERROR |\nhr=0x8007001F", res, None)
    assert h3[0]["camera_id"] == "e5f6" and h3[0]["code"] == sr.DEVICE_ERROR_HR
    assert h3[1]["camera_id"] is None and h3[1]["code"] == sr.DEVICE_ERROR_HR


# ============================================================================================================ fake server
FAKE_SERVER = r'''
import json, os, sys, threading, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
port = int(sys.argv[1])
MODE = os.environ.get("FAKE_MODE", "ok")
CAMS = json.loads(os.environ["FAKE_CAMERAS"])
COLS = json.loads(os.environ["FAKE_COLUMNS"])
N = int(os.environ.get("FAKE_FRAMES", "45"))
state = {"configs": {}, "rec": None}

def log(msg, level="INFO"):
    print(f"\x1b[36m└>> {msg} |  {level} |  0.1ms | fake.mod():1 | 2026-11-11T22:00:00 |  PID:1:MainProcess\x1b[0m", flush=True)

def write_recording():
    rec = state["rec"]
    name = rec["recording_name"]
    rd = Path(rec["recording_directory"]) / name
    vd = rd / "synchronized_videos"; td = vd / "timestamps"; (td / "camera_timestamps").mkdir(parents=True, exist_ok=True)
    (rd / f"{name}_info.json").write_text(json.dumps({"recording_name": name, "camera_configs": state["configs"]}))
    for cid, c in state["configs"].items():
        (vd / f"{name}.id-{cid}.idx-{c['camera_index']}.mp4").write_bytes(b"\0" * 5000)
        lines = [",".join(COLS)]
        for i in range(N):
            t = 10 ** 12 + i * 33_333_333
            row = {k: "0" for k in COLS}
            row.update({"recording_frame_number": str(i), "connection_frame_number": str(7 + i),
                        "timestamp.from_recording_start.sec": f"{i / 30 + 0.01:.6f}",
                        "timestamp.utc.seconds": f"{1.7e9 + i / 30:.6f}", "timestamp.perf_counter_ns.ns": str(t),
                        "from_previous.frame_duration.ms": "nan" if i == 0 else "33.3333",
                        "from_previous.framerate.hz": "nan" if i == 0 else "30.0"})
            lines.append(",".join(row[k] for k in COLS))
        (td / "camera_timestamps" / f"{name}.camera{cid}.timestamps.csv").write_text("\n".join(lines) + "\n")
    m = ["multiframe_number,timestamp.from_recording_start.sec,timestamp.perf_counter_ns.ns,inter_camera.frame_grab_range.ms"]
    m += [f"{i},{i / 30:.6f},{10 ** 12 + i * 33_333_333}.0,0.6" for i in range(N)]
    (td / f"{name}_timestamps.csv").write_text("\n".join(m) + "\n")
    (td / f"{name}_stats.json").write_text(json.dumps({"number_of_frames": N}))
    stats = {"median": 33.3, "mean": 33.3, "std": 0.1, "min": 33.0, "max": 34.0}
    return [{"recording_name": name, "recording_path": str(rd), "number_of_cameras": len(state["configs"]),
             "number_of_frames": N, "total_duration_sec": N / 30, "mean_framerate": 30.0,
             "mean_inter_camera_sync_ms": 0.6, "framerate_stats": stats, "frame_duration_stats": stats,
             "inter_camera_grab_range_ms_stats": stats}]

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass
    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"null")
    def do_GET(self):
        p = self.path.split("?")[0]
        log(f"GET {p}", "API")
        if p == "/health":
            return self._send(200, {"alive": True, "pid": os.getpid()})
        if p == "/shutdown":
            self._send(200, {"status": "shutdown_initiated", "message": "bye"})
            threading.Timer(0.2, lambda: os._exit(0)).start()
            return
        if p == "/skellycam/camera/group/all/record/stop":
            return self._send(200, write_recording())
        self._send(404, {"detail": "not found"})
    def do_POST(self):
        p = self.path.split("?")[0]
        log(f"POST {self.path}", "API")
        body = self._body()
        if p == "/skellycam/camera/detect":
            return self._send(200, {"cameras": CAMS})
        if p == "/skellycam/camera/group/apply":
            cfgs = body["camera_configs"]
            if MODE == "hang_connect":
                time.sleep(30)
                return self._send(500, {"detail": "late"})
            for cid in cfgs:
                if MODE == "kiyo_fail" and cfgs[cid]["camera_index"] == 2:
                    continue
                log(f"Camera {cid} connected, awaiting shm message...", "DEBUG")
            if MODE == "kiyo_fail":
                log("Failed to read frame from camera 2. Retrying... (1/5)", "WARNING")
                for cid in cfgs:
                    msg = "" if cfgs[cid]["camera_index"] == 2 else "Failed to initialize camera_group_shm"
                    log(f"Failed to create cv2.VideoCapture for camera {cid}: {msg}", "ERROR")
                return self._send(500, {"detail": "Camera config for e5f6 must be an instance of CameraConfig"})
            state["configs"] = cfgs
            out = {cid: dict(c, framerate=30.0) for cid, c in cfgs.items()}
            return self._send(200, {"group_id": "g1", "camera_configs": out})
        if p == "/skellycam/camera/group/all/record/start":
            state["rec"] = body
            return self._send(200, True)
        self._send(404, {"detail": "not found"})
    def do_DELETE(self):
        log(f"DELETE {self.path}", "API")
        if self.path == "/skellycam/camera/group/close/all":
            return self._send(200, True)
        self._send(404, {"detail": "not found"})

ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
'''


@pytest.fixture
def fake_server(tmp_path, monkeypatch):
    p = tmp_path / "fake_skellycam_server.py"
    p.write_text(FAKE_SERVER, encoding="utf-8")
    monkeypatch.setenv("FAKE_CAMERAS", json.dumps(DETECTED))
    monkeypatch.setenv("FAKE_COLUMNS", json.dumps(CAMERA_COLUMNS))
    checkout = tmp_path / "checkout"
    checkout.mkdir()

    def run(specs: list[str], mode: str = "ok", extra: list[str] | None = None, capsys=None) -> tuple[int, dict]:
        monkeypatch.setenv("FAKE_MODE", mode)
        argv = ["--checkout", str(checkout), "--out-dir", str(tmp_path / f"out_{mode}"), "--seconds", "1",
                "--warmup-s", "0", "--media-check", "none", "--recording-name", "rec",
                "--server-cmd-json", json.dumps([sys.executable, str(p), "{port}"]), "--deadline-s", "60"]
        for s in specs:
            argv += ["--camera", s]
        rc = sr.main(argv + (extra or []))
        out = capsys.readouterr().out.strip()
        assert out.count("\n") == 0, "the driver prints exactly one JSON line"
        return rc, json.loads(out)
    return run


def test_driver_end_to_end_against_fake_server(fake_server, capsys):
    rc, s = fake_server([f"ds:{ds(I_C922A)}", f"mf:{mf(I_KIYO)}"], capsys=capsys)
    assert rc == 0 and s["ok"], s.get("error")
    calls = [(c["method"], c["path"]) for c in s["api_calls"]]
    assert calls == [("GET", "/health"), ("POST", "/skellycam/camera/detect?filter_virtual=false"),
                     ("POST", "/skellycam/camera/group/apply"), ("POST", "/skellycam/camera/group/all/record/start"),
                     ("GET", "/skellycam/camera/group/all/record/stop"), ("DELETE", "/skellycam/camera/group/close/all"),
                     ("GET", "/shutdown")]
    assert sorted(s["group_request"]["camera_configs"]) == ["a1b2", "e5f6"]     # exactly the given cameras
    assert [r["camera_index"] for r in s["resolution"]] == [0, 2]
    v = s["verify"]
    assert v["ok"] and v["frame_counts"] == {"a1b2": 45, "e5f6": 45} and v["camera_source"] == "request"
    assert s["server"]["clean"] and not s["server"]["killed"] and s["server"]["leftover_processes"] in (0, None)
    assert s["fault_hints"] == [] and s["exit_code"] == 0
    assert Path(s["out_dir"], "summary.json").is_file() and Path(s["server"]["stdout_log"]).is_file()


def test_driver_unresolved_camera_opens_nothing(fake_server, capsys):
    rc, s = fake_server([f"ds:{ds(I_C922A)}", "vidpid:046d:085c"], capsys=capsys)
    assert rc == sr.EXIT_UNRESOLVED and s["stage_failed"] == "resolve"
    paths = [c["path"] for c in s["api_calls"]]
    assert "/skellycam/camera/group/apply" not in paths and "/skellycam/camera/group/close/all" not in paths
    assert paths[-1] == "/shutdown" and s["server"]["clean"]


def test_driver_reports_kiyo_pro_start_failure(fake_server, capsys):
    rc, s = fake_server([f"ds:{ds(I_C922A)}", f"ds:{ds(I_KIYO)}"], mode="kiyo_fail", capsys=capsys)
    assert rc == sr.EXIT_FAIL and s["stage_failed"] == "connect" and not s["ok"]
    assert [h["camera_id"] for h in s["fault_hints"]] == ["e5f6"]
    assert s["fault_hints"][0]["is_kiyo_pro"] and s["fault_hints"][0]["code"] == "first_frame_failed"
    paths = [c["path"] for c in s["api_calls"]]
    assert "/skellycam/camera/group/all/record/start" not in paths
    assert paths[-2:] == ["/skellycam/camera/group/close/all", "/shutdown"]
    assert s["server_log"]["error_lines"] == 2


def test_driver_connect_timeout_is_bounded(fake_server, capsys):
    rc, s = fake_server([f"ds:{ds(I_C922A)}", f"ds:{ds(I_KIYO)}"], mode="hang_connect",
                        extra=["--connect-timeout-s", "2"], capsys=capsys)
    assert rc == sr.EXIT_TIMEOUT and s["stage_failed"] == "connect" and s["error"]["class"] == "timeout"
    assert sorted(h["camera_id"] for h in s["fault_hints"]) == ["a1b2", "e5f6"]
    assert all(h["code"] == "connect_timeout" for h in s["fault_hints"])
    assert s["elapsed_s"] < 40


# ============================================================================================================ W-TBUMP
CAMS = [
    {"key": "046d:085c:sn=A", "name": "C922 A", "vid": "046d", "pid": "085c", "is_kiyo": False,
     "ds_path": ds(I_C922A), "mf_symlink": mf(I_C922A), "ds_index": 0},
    {"key": "046d:085c:sn=B", "name": "C922 B", "vid": "046d", "pid": "085c", "is_kiyo": False,
     "ds_path": ds(I_C922B), "mf_symlink": mf(I_C922B), "ds_index": 1},
    {"key": "1532:0e05:port=P", "name": "Razer Kiyo Pro", "vid": "1532", "pid": "0e05", "is_kiyo": True,
     "ds_path": ds(I_KIYO), "mf_symlink": mf(I_KIYO), "ds_index": 2},
    {"key": "0c45:6366:port=Q", "name": "USB Camera", "vid": "0c45", "pid": "6366", "is_kiyo": False,
     "ds_path": ds(I_GEN), "mf_symlink": None, "ds_index": 3},
]
ID_BY_PATH = {d["path"]: (d["camera_id"], d["index"]) for d in DETECTED}


def make_summary(specs: list[str], ok: bool = True, fps: float = 30.0, frames: int = 1800, codec: str = "h264",
                 stage_failed: str | None = None, hints: list | None = None, error_kinds: dict | None = None,
                 connect_s: float = 8.0, versions: dict | None = None, verify_ok: bool = True) -> dict:
    res = []
    for s in specs:
        cid, idx = ID_BY_PATH[s.split(":", 1)[1]]
        res.append({"spec": s, "camera_id": cid, "camera_index": idx, "name": f"cam{idx}"})
    cams = {r["camera_id"]: {"camera_index": r["camera_index"], "ok": verify_ok, "problems": [] if verify_ok else ["x"],
                             "frames": {"count": frames}, "fps_from_timestamps": fps,
                             "csv": {"header_sha1": "abc", "columns": 27, "first_frame_from_recording_start_s": 0.02,
                                     "timestamps": {"interval_ms": {"median": 33.3}}},
                             "video": {"ext": "mp4", "size_bytes": frames * 20000},
                             "pyav": {"codec": codec, "container": "mov,mp4", "pix_fmt": "yuv420p", "width": 1280,
                                      "height": 720},
                             "opencv": {"fourcc": "avc1", "decoded_frames": frames}} for r in res}
    good = ok and stage_failed is None
    return {"tool": "skellycam_record", "ok": good, "stage_failed": stage_failed,
            "error": None if good else {"stage": stage_failed, "class": "api_error", "message": "boom"},
            "resolution": res, "fault_hints": hints or [], "phases_s": {"connect": connect_s, "start_to_health": 12.0},
            "checkout": {"commit": "c0ffee", "versions": versions or {"opencv": "x"}},
            "group": {"extracted_configs": {r["camera_id"]: {"framerate": 30.0} for r in res}},
            "verify": None if stage_failed in ("connect", "resolve") else {
                "ok": verify_ok, "frames": frames, "frame_counts_equal": True, "cameras": cams, "problems": [],
                "multiframe_csv": {"fps_from_timestamps": fps, "header_sha1": "def"}},
            "server_log": {"error_lines": len(error_kinds or {}), "error_kinds": error_kinds or {}, "tracebacks": 0,
                           "logging_errors": 0, "writer_codec_lines": []},
            "server": {"clean": True, "leftover_processes": 0}}


class FakeCtx:
    def __init__(self, tmp: Path, scenario, cameras=CAMS, dead=(), gated=(), quick=False):
        self.base = tmp / "base"
        self.head = tmp / "head"
        for d in (self.base, self.head):
            (d / ".venv").mkdir(parents=True, exist_ok=True)
            (d / "pyproject.toml").write_text("[project]\nname='skellycam'\n", encoding="utf-8")
        self.args = SimpleNamespace(quick=quick, tbump_baseline_dir=str(self.base), tbump_head_dir=str(self.head))
        self.cameras = list(cameras)
        self.raw = tmp / "raw"
        self.dead = {k: {"dead": True, "since_utc": "t0"} for k in dead}
        self.gated = {k: {"since_utc": "t1", "code": "0x8007001F"} for k in gated}
        self.scenario = scenario
        self.calls: list[dict] = []
        self.marked: list = []
        self.logs: list[str] = []

    def log(self, msg):
        self.logs.append(msg)

    def raw_test_dir(self, name):
        d = self.raw / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def helper_cmd(self, script, *args):
        return ["uv", "run", "--python", "3.12", "--script", str(script), *map(str, args)]

    def run(self, argv, timeout_s):
        return {"rc": 0, "stdout": w_tbump.BASELINE_COMMIT + "\n" if "rev-parse" in argv and "HEAD" == argv[-1]
                and argv[2] == str(self.base) else "deadbeef\n"}

    def camera_dead(self, cam):
        return self.dead.get(cam["key"] if isinstance(cam, dict) else cam)

    def camera_gated(self, cam):
        k = cam["key"] if isinstance(cam, dict) else cam
        return self.dead.get(k) or self.gated.get(k)

    def camera_summaries(self):
        return [{"key": c["key"]} for c in self.cameras]

    def camera(self, key):
        return next((c for c in self.cameras if c["key"] == key), None)

    def mark_fault(self, *a, **k):
        self.marked.append((a, k))

    def camcmd(self, argv, timeout_s):
        label = "baseline" if str(self.base) in argv else "head"
        specs = [argv[i + 1] for i, a in enumerate(argv) if a == "--camera"]
        n = sum(1 for c in self.calls if c["label"] == label)
        self.calls.append({"label": label, "specs": specs, "timeout_s": timeout_s, "argv": argv})
        out = self.scenario(label, specs, n)
        return {"rc": 0 if out.get("ok") else 4, "stdout": json.dumps(out), "stderr": "", "timed_out": False,
                "elapsed_s": 100.0}


def test_exclusion_dead_gated_and_estimate(tmp_path):
    no_ids = dict(CAMS[3], key="x:y:z", ds_path=None, mf_symlink=None)
    ctx = FakeCtx(tmp_path, None, cameras=CAMS + [no_ids], dead=[CAMS[2]["key"]], gated=[CAMS[1]["key"]])
    keep, out = w_tbump.eligible(ctx)
    assert [c["key"] for c in keep] == [CAMS[0]["key"], CAMS[3]["key"]]
    assert out[CAMS[2]["key"]].startswith("dead") and out[CAMS[1]["key"]].startswith("device-fault gate")
    assert "no DirectShow" in out["x:y:z"]
    assert w_tbump.spec_for(CAMS[3]) == f"ds:{ds(I_GEN)}"
    full = w_tbump.estimate_s(FakeCtx(tmp_path, None))
    assert 330 <= full <= 400                       # ~6 min with 4 cameras
    assert w_tbump.estimate_s(FakeCtx(tmp_path, None, quick=True)) == full - 2 * 50
    assert w_tbump.seconds(FakeCtx(tmp_path, None, quick=True)) == 10.0


def test_two_recordings_compared_dead_kiyo_never_reached(tmp_path):
    ctx = FakeCtx(tmp_path, lambda label, specs, n: make_summary(specs), dead=[CAMS[2]["key"]])
    res = w_tbump.run(ctx)
    assert [c["label"] for c in ctx.calls] == ["baseline", "head"]
    for c in ctx.calls:
        assert f"ds:{ds(I_KIYO)}" not in c["specs"] and len(c["specs"]) == 3
        assert "--seconds" in c["argv"] and c["argv"][c["argv"].index("--seconds") + 1] == "60"
        assert str(ctx.raw / "W-TBUMP") in c["argv"][c["argv"].index("--out-dir") + 1]
        assert c["timeout_s"] == 60 + w_tbump.DEADLINE_EXTRA_S + w_tbump.CAMCMD_SLACK_S
    assert ctx.calls[0]["argv"][ctx.calls[0]["argv"].index("--checkout") + 1] == str(ctx.base)
    v = res["verdicts"]
    assert v["T-BUMP|recording"]["rating"] == "yes", v["T-BUMP|recording"].get("note")
    assert v[f"T-BUMP|{CAMS[0]['key']}"]["rating"] == "yes"
    assert res["measurements"]["excluded"][CAMS[2]["key"]].startswith("dead")
    assert res["kiyo_pro_fault"] is None and res["fault_reports"] == []
    assert "measurements" in res and "cameras" not in res["measurements"]   # no backstop-scanned per-camera block


def test_kiyo_pro_fault_reported_never_retried(tmp_path):
    kiyo_spec = f"ds:{ds(I_KIYO)}"

    def scenario(label, specs, n):
        if kiyo_spec in specs:
            return make_summary(specs, stage_failed="connect", hints=[
                {"spec": kiyo_spec, "camera_id": "e5f6", "camera_index": 2, "code": "first_frame_failed",
                 "stage": "first_frame", "evidence": "Failed to read frame from camera 2"}])
        return make_summary(specs)

    ctx = FakeCtx(tmp_path, scenario)
    res = w_tbump.run(ctx)
    assert [c["label"] for c in ctx.calls] == ["baseline", "baseline", "head"]
    assert sum(kiyo_spec in c["specs"] for c in ctx.calls) == 1        # the Kiyo Pro was streamed once only
    assert len(ctx.calls[1]["specs"]) == 3 and len(ctx.calls[2]["specs"]) == 3
    f = res["kiyo_pro_fault"]
    assert f["key"] == CAMS[2]["key"] and f["code"] == "first_frame_failed" and not f["suspected"]
    # MARK_FAULTS = True (integrated 2026-11-11): the module marks the Kiyo Pro fault itself, once
    assert len(ctx.marked) == 1 and ctx.marked[0][0][0] == CAMS[2]["key"]
    assert "baseline_with_kiyo_pro" in res["measurements"]["runs"]
    assert res["measurements"]["runs"]["baseline"]["rerun_without_kiyo_pro"]
    assert res["verdicts"]["T-BUMP|recording"]["rating"] == "yes"
    assert any("Kiyo Pro" in m and "fault" in m for m in ctx.logs)


def test_kiyo_pro_hang_without_json_is_a_suspected_fault(tmp_path):
    run = {"label": "head", "ok": False, "driver": None, "camcmd": {"timed_out": True},
           "spec_to_key": {w_tbump.spec_for(c): c["key"] for c in CAMS}}
    rep = w_tbump.fault_reports(run, CAMS)
    assert [r["key"] for r in rep] == [CAMS[2]["key"]] and rep[0]["suspected"] and rep[0]["code"] == "timeout"
    run["camcmd"] = {"timed_out": False, "lock_timed_out": True}
    assert w_tbump.fault_reports(run, CAMS) == []


def test_head_regression_rates_no_and_change_rates_partial(tmp_path):
    ctx = FakeCtx(tmp_path, lambda label, specs, n: make_summary(specs) if label == "baseline" else
                  make_summary(specs, verify_ok=False, ok=True, stage_failed="verify"), dead=[CAMS[2]["key"]])
    res = w_tbump.run(ctx)
    assert res["verdicts"]["T-BUMP|recording"]["rating"] == "no"
    assert "regression" in res["verdicts"]["T-BUMP|recording"]["note"]

    ctx2 = FakeCtx(tmp_path / "b", lambda label, specs, n: make_summary(specs) if label == "baseline" else
                   make_summary(specs, fps=27.0, codec="mpeg4", error_kinds={"Failed to grab frame #": 3}),
                   dead=[CAMS[2]["key"]])
    res2 = w_tbump.run(ctx2)
    v = res2["verdicts"]["T-BUMP|recording"]
    assert v["rating"] == "partial"
    assert "group fps within 2 %" in v["note"] and "no new server-log error kinds" in v["note"]
    cam_v = res2["verdicts"][f"T-BUMP|{CAMS[0]['key']}"]
    assert cam_v["rating"] == "partial"
    unmet = {c["criterion"] for c in cam_v["criteria"] if c["met"] is False}
    assert {"fps within 2 %", "same codec, container and frame size"} <= unmet


def test_baseline_failure_is_untested_and_missing_checkout_runs_nothing(tmp_path):
    ctx = FakeCtx(tmp_path, lambda label, specs, n: make_summary(specs, stage_failed="stop") if label == "baseline"
                  else make_summary(specs), dead=[CAMS[2]["key"]])
    assert w_tbump.run(ctx)["verdicts"]["T-BUMP|recording"]["rating"] == "untested"
    ctx2 = FakeCtx(tmp_path / "m", lambda *a: pytest.fail("no recording without both checkouts"))
    shutil.rmtree(ctx2.base / ".venv")
    res = w_tbump.run(ctx2)
    assert ctx2.calls == [] and res["verdicts"]["T-BUMP|recording"]["rating"] == "untested"
    assert "no .venv" in res["verdicts"]["T-BUMP|recording"]["criteria"][0]["detail"]
    ctx3 = FakeCtx(tmp_path / "w", lambda *a: pytest.fail("baseline at the wrong commit"))
    ctx3.run = lambda argv, timeout_s: {"rc": 0, "stdout": "0123456789\n"}
    assert w_tbump.run(ctx3)["verdicts"]["T-BUMP|recording"]["rating"] == "untested" and ctx3.calls == []


# ============================================================================================================ real media (uv)
GEN = r'''
import sys, cv2, numpy as np
from pathlib import Path
out, n = Path(sys.argv[1]), int(sys.argv[2])
w = cv2.VideoWriter(str(out), cv2.VideoWriter.fourcc(*"MJPG"), 30.0, (320, 240))
assert w.isOpened()
for i in range(n):
    img = np.full((240, 320, 3), i % 255, np.uint8)
    w.write(img)
w.release()
print(out.stat().st_size)
'''


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not on PATH")
def test_verify_only_reads_a_real_video_with_pyav_and_opencv(tmp_path):
    n = 40
    rd = write_recording(tmp_path, "real", [("a1b2", 0)], n, video_bytes=b"")
    vid = next((rd / "synchronized_videos").glob("*.mp4"))
    vid.unlink()
    avi = vid.with_suffix(".avi")
    gen = tmp_path / "gen.py"
    gen.write_text(GEN, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "PYTHONPATH")}
    g = subprocess.run(["uv", "run", "--isolated", "--no-project", "--python", "3.12", "--with",
                        "opencv-contrib-python==5.0.0.93", "--with", "numpy==2.5.4", "python", str(gen), str(avi),
                        str(n)], capture_output=True, text=True, timeout=600, env=env)
    if g.returncode != 0:
        pytest.skip(f"could not build the OpenCV environment offline: {g.stderr[-300:]}")
    r = subprocess.run(["uv", "run", "--python", "3.12", "--script", str(WIN / "helpers" / "skellycam_record.py"),
                        "--verify-only", str(rd)], capture_output=True, text=True, timeout=600, env=env)
    if r.returncode not in (0, 4) or not r.stdout.strip():
        pytest.skip(f"could not build the driver's environment offline: {r.stderr[-300:]}")
    s = json.loads(r.stdout)
    c = s["verify"]["cameras"]["a1b2"]
    assert c["pyav"]["ok"] and c["pyav"]["codec"] == "mjpeg" and c["pyav"]["packets"] == n
    assert c["opencv"]["ok"] and c["opencv"]["decoded_frames"] == n and c["opencv"]["fourcc"] == "MJPG"
    assert c["frames"] == {"csv_rows": n, "pyav_packets": n, "opencv_decoded": n, "count": n}
    assert s["ok"] and r.returncode == 0, s["verify"]["problems"]
