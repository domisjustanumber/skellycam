"""Make a real recording by starting the skellycam (or FreeMoCap) server and driving its HTTP API, as a UI would.

Run under camlock. Steps: start server -> /health -> detect cameras -> /group/apply (chosen cameras, default
config except resolution) -> warm up -> start recording -> sleep -> stop -> close groups -> /shutdown.

--server skellycam : `python -m skellycam` from the skellycam venv; start = POST /skellycam/camera/group/all/record/start
--server freemocap : `python -m freemocap` from the freemocap venv; start = POST /freemocap/calibration/recording/start
                     (the FreeMoCap UI's calibration-recording request: calibrationRecordingDirectory =
                     <root>/<timestamp>_calibration, default calibrationTaskConfig). Stop goes through
                     GET /skellycam/camera/group/all/record/stop, NOT /freemocap/calibration/recording/stop,
                     because the latter launches a posthoc calibration solve (out of scope). Both call
                     CameraGroupManager.stop_recording_all_groups().

Writes <out_json> with every request/response and timings.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

BASE = "http://localhost:53117"
PY = {
    "skellycam": r"C:\Users\Dom\GitHub\freemocap\skellycam\.venv\Scripts\python.exe",
    "freemocap": r"C:\Users\Dom\GitHub\freemocap\freemocap\.venv\Scripts\python.exe",
}
CWD = {
    "skellycam": r"C:\Users\Dom\GitHub\freemocap\skellycam",
    "freemocap": r"C:\Users\Dom\GitHub\freemocap\freemocap",
}

log: list[dict] = []


def call(client, method, path, **kw):
    t = time.perf_counter()
    r = client.request(method, BASE + path, **kw)
    dt = time.perf_counter() - t
    try:
        body = r.json()
    except Exception:
        body = r.text[:2000]
    entry = dict(t=datetime.now().isoformat(timespec="milliseconds"), method=method, path=path,
                 request=kw.get("json"), status=r.status_code, seconds=round(dt, 3), response=body)
    log.append(entry)
    print(f"[drive] {method} {path} -> {r.status_code} in {dt:.2f}s", flush=True)
    return r, body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", choices=["skellycam", "freemocap"], default="skellycam")
    ap.add_argument("--cameras", nargs="+", default=["046D:0843", "1532:0E05", "046D:085C"], help="VID:PID hex")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--warmup-s", type=float, default=15)
    ap.add_argument("--duration-s", type=float, default=60)
    ap.add_argument("--mic", type=int, default=-1)
    ap.add_argument("--root", required=True, help="recording_directory")
    ap.add_argument("--name", default=None, help="recording_name (skellycam server only)")
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--server-log", required=True)
    ap.add_argument("--hw-transforms-off", action="store_true", help="OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS=0")
    ap.add_argument("--module-probe", action="store_true", help="list encoder DLLs loaded in python.exe processes 5 s into the recording")
    a = ap.parse_args()

    env = dict(os.environ)
    if a.hw_transforms_off:
        env["OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS"] = "0"
    srv_log = open(a.server_log, "w", encoding="utf-8", errors="replace")
    t_launch = time.perf_counter()
    proc = subprocess.Popen([PY[a.server], "-m", a.server], cwd=CWD[a.server], env=env,
                            stdout=srv_log, stderr=subprocess.STDOUT)
    summary = dict(server=a.server, args=vars(a), server_pid=proc.pid)
    rc = 1
    try:
        with httpx.Client(timeout=600) as c:
            for _ in range(240):
                try:
                    if c.get(BASE + "/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                if proc.poll() is not None:
                    raise RuntimeError(f"server exited early rc={proc.returncode}")
                time.sleep(0.5)
            summary["server_ready_s"] = round(time.perf_counter() - t_launch, 1)
            _, cams = call(c, "POST", "/skellycam/camera/detect")
            if a.server == "skellycam" or True:
                call(c, "GET", "/skellycam/camera/microphone/detect")
            by_vp = {f"{d['vendor_id']:04X}:{d['product_id']:04X}": d for d in cams["cameras"]}
            configs = {}
            for vp in a.cameras:
                d = by_vp.get(vp.upper())
                if d is None:
                    raise RuntimeError(f"camera {vp} not detected; detected: {list(by_vp)}")
                configs[d["camera_id"]] = dict(camera_id=d["camera_id"], camera_index=d["index"],
                                               camera_name=d["name"],
                                               resolution=dict(width=a.width, height=a.height))
            r, body = call(c, "POST", "/skellycam/camera/group/apply", json={"camera_configs": configs})
            if r.status_code != 200:
                raise RuntimeError(f"apply failed: {body}")
            time.sleep(a.warmup_s)
            ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            if a.server == "skellycam":
                name = a.name or f"{ts}_skellycam"
                r, body = call(c, "POST", "/skellycam/camera/group/all/record/start",
                               json=dict(recording_name=name, recording_directory=a.root, mic_device_index=a.mic))
            else:
                calib_dir = f"{a.root.rstrip('/\\')}/{ts}_calibration"
                r, body = call(c, "POST", "/freemocap/calibration/recording/start",
                               json=dict(calibrationRecordingDirectory=calib_dir))
            if r.status_code != 200:
                raise RuntimeError(f"start failed: {body}")
            summary["record_start_wall"] = datetime.now().isoformat(timespec="milliseconds")
            if a.module_probe:
                # which H.264 encoder DLL do the server's processes have loaded while recording?
                time.sleep(5)
                ps = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | ForEach-Object { $p=$_; "
                      "try { (Get-Process -Id $p.ProcessId).Modules | Where-Object { $_.ModuleName -match "
                      "'nvEnc|mfh264enc|msmpeg2enc|mfplat|mfreadwrite|nvcuda|igd|libmfx|intel|amf|d3d11' } | ForEach-Object { "
                      "'{0} parent={1} {2} {3}' -f $p.ProcessId, $p.ParentProcessId, $_.ModuleName, $_.FileName } } catch { "
                      "'{0} ERR {1}' -f $p.ProcessId, $_ } }")
                pr = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=120)
                summary["module_probe"] = pr.stdout.splitlines() + pr.stderr.splitlines()
                time.sleep(max(0.0, a.duration_s - 5 - 0))
            else:
                time.sleep(a.duration_s)
            r, body = call(c, "GET", "/skellycam/camera/group/all/record/stop")
            summary["stop_status"] = r.status_code
            summary["stop_response"] = body
            call(c, "DELETE", "/skellycam/camera/group/close/all")
            rc = 0 if r.status_code == 200 else 2
            try:
                call(c, "GET", "/shutdown")
            except httpx.HTTPError as e:
                log.append(dict(path="/shutdown", error=repr(e)))
    except Exception as e:
        summary["error"] = repr(e)
        print(f"[drive] ERROR {e!r}", flush=True)
    finally:
        try:
            summary["server_exit_rc"] = proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            summary["server_exit_rc"] = "timeout: killed"
            proc.kill()
            proc.wait()
        srv_log.close()
        summary["log"] = log
        Path(a.out_json).write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    return rc


if __name__ == "__main__":
    sys.exit(main())
