# /// script
# requires-python = ">=3.10"
# ///
"""Timestamp-anchor test orchestrator: rig strobe + Media Foundation capture with an exposure schedule.

  uv run --script research/usb_cameras/timing/rig/run_anchor_test.py --port COM7 \\
      --cam "vid_046d&pid_085c,1280,720,30,-7,4500" --exposure-schedule "-9,-7,-6" --seconds 240 --restarts 3
  ... --double                      (L run: double strobe, gap 10 ms, fixed exposure; use a short exposure)
  ... --dry-run                     (print every command, open nothing)
  ... --simulate-rig --no-camera    (plumbing test: simulated rig firmware, a sleep instead of the camera)

What it does
  1. Starts rig_session.py (strobe configured, --defer-start) writing into the results folder.
  2. For each of --restarts captures: runs timing/build/mf_uvc_timing.exe --save-mjpeg UNDER tools/camlock.py,
     with the timeout INSIDE the lock (lock waiting never eats the capture timeout). Once every camera has written
     its first frame it waits --strobe-start-delay-s and STARTs the strobe (new epoch, k = 0: the analysis uses the
     first band after the epoch to confirm strobe identity), and STOPs the strobe when the capture ends.
  3. Stops the rig session (stop file), copies frames.jsonl / session.json / controls.jsonl next to the rig logs,
     and writes result.json (standard result fields).
  Raw MJPEG stays in %USERPROFILE%/Documents/skellycam-raw/<same relative path> (never in the repo).

Defaults follow docs/test_gap_plan.md §3.3: strobe period = round(1e6/fps) + 33 us (the band walks the frame in
~33 s), width 50 us (use >= 2*L, e.g. 100 us, for cameras with L > 50 us; see README), phase 1000 us, gap 10000 us
with --double. Then analyse with analyze_anchor.py (printed at the end).
Output: results/<platform>/<hostname>/rig_anchor_<UTC>[_<label>]/
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import shlex
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
AREA_ROOT = HERE.parents[1]
REPO_ROOT = AREA_ROOT.parents[1]
CAMLOCK = AREA_ROOT / "tools" / "camlock.py"
RIG_SESSION = HERE / "rig_session.py"
DEFAULT_EXE = AREA_ROOT / "timing" / "build" / "mf_uvc_timing.exe"
BYTES_PER_CAM_HOUR = 10e9  # test plan §4 data handling: ~10 GB per camera-hour of 720p30 MJPEG (estimate)


def platform_name() -> str:
    return {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux" if sys.platform.startswith("linux") else sys.platform)


def raw_root() -> Path:
    env = os.environ.get("SKELLYCAM_RAW_ROOT")
    if env:
        return Path(env)
    return Path.home() / "Documents" / "skellycam-raw" if sys.platform == "win32" else Path.home() / "skellycam-raw"


def exec_with_timeout(argv: list[str]) -> int:
    """Hidden child mode (runs inside camlock): run argv[2:] with a hard timeout of argv[0] seconds."""
    timeout = float(argv[0])
    cmd = argv[2:] if argv[1:2] == ["--"] else argv[1:]
    p = subprocess.Popen(cmd)
    try:
        return p.wait(timeout)
    except subprocess.TimeoutExpired:
        print(f"[run_anchor_test] capture exceeded {timeout:.0f} s, killing", file=sys.stderr, flush=True)
        p.kill()
        p.wait()
        return 124


def sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def q(cmd: list[str]) -> str:
    return " ".join(shlex.quote(c) if " " in c or "&" in c or ";" in c else c for c in cmd)


def frames_started(raw_cap: Path) -> int:
    n = 0
    for f in raw_cap.glob("*.frames.jsonl"):
        try:
            if f.stat().st_size > 0:
                n += 1
        except OSError:
            pass
    return n


def main() -> int:
    if len(sys.argv) > 2 and sys.argv[1] == "--_exec-timeout":
        return exec_with_timeout(sys.argv[2:])
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", help="rig serial port (AtomS3 Lite: the VID 303A COM port; see rig_session.py --list-ports)")
    ap.add_argument("--cam", action="append", default=[], help='mf_uvc_timing --cam spec, e.g. "vid_046d&pid_085c,1280,720,30,-7,4500"; '
                                                               '7th field = per-camera schedule "-5:-4:-3"')
    ap.add_argument("--seconds", type=float, default=240.0, help="capture length per stream start")
    ap.add_argument("--restarts", type=int, default=3, help="number of stream starts (captures) in this rig session")
    ap.add_argument("--exposure-schedule", default=None, help='e.g. "-9,-7,-6" (omit for a fixed exposure)')
    ap.add_argument("--exposure-dwell-s", type=float, default=5.0)
    ap.add_argument("--exposure-first-s", type=float, default=1.0)
    ap.add_argument("--fps", type=float, help="nominal fps for the strobe period (default: from the first --cam)")
    ap.add_argument("--strobe-period-us", type=int)
    ap.add_argument("--width-us", type=int, default=50)
    ap.add_argument("--phase-us", type=int, default=1000)
    ap.add_argument("--gap-us", type=int, default=0)
    ap.add_argument("--double", action="store_true", help="double strobe for the line time (sets --gap-us 10000 unless given)")
    ap.add_argument("--strobe-start-delay-s", type=float, default=2.0, help="START the strobe this long after all cameras stream")
    ap.add_argument("--no-defer-start", action="store_true", help="strobe runs for the whole session (no epoch check)")
    ap.add_argument("--ping-rate", type=float, default=20.0)
    ap.add_argument("--rig-line-state", choices=("deassert", "dtr", "untouched"), default="deassert")
    ap.add_argument("--exe", type=Path, default=DEFAULT_EXE)
    ap.add_argument("--lock-timeout-s", type=float, default=3600.0)
    ap.add_argument("--label", default="")
    ap.add_argument("--out-dir", type=Path, help="override the results folder")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--simulate-rig", action="store_true", help="rig_session --simulate (no ESP32)")
    ap.add_argument("--no-camera", action="store_true", help="replace the capture by a sleep (plumbing test; no camlock)")
    argv = sys.argv[1:]
    for i in range(len(argv) - 1):  # "--exposure-schedule -9,-7,-6": argparse would read the value as an option
        if argv[i] == "--exposure-schedule" and argv[i + 1].startswith("-"):
            argv[i:i + 2] = [f"--exposure-schedule={argv[i + 1]}", ""]
    a = ap.parse_args([x for x in argv if x != ""])

    if not a.cam and not a.no_camera:
        ap.error("at least one --cam is required (or --no-camera)")
    if not a.port and not a.simulate_rig and not a.dry_run:
        ap.error("--port is required (or --simulate-rig / --dry-run)")
    if a.double and not a.gap_us:
        a.gap_us = 10000
    fps = a.fps
    if fps is None and a.cam:
        parts = a.cam[0].split(",")
        fps = float(parts[3]) if len(parts) > 3 else 30.0
    fps = fps or 30.0
    period = a.strobe_period_us or int(round(1e6 / fps)) + 33
    if period > 65535:
        ap.error(f"strobe period {period} us exceeds the firmware limit of 65535 us")
    if (2 if a.gap_us else 1) * a.width_us * 100 > period:
        ap.error("duty over 1 % (firmware limit)")
    utc = dt.datetime.now(dt.timezone.utc)
    stamp = utc.strftime("%Y%m%dT%H%M%SZ")
    name = f"rig_anchor_{stamp}" + (f"_{a.label}" if a.label else "")
    res_dir = a.out_dir or (AREA_ROOT / "results" / platform_name() / socket.gethostname() / name)
    try:
        raw_dir = raw_root() / res_dir.resolve().relative_to(AREA_ROOT)
    except ValueError:
        raw_dir = raw_root() / "rig_anchor_external" / res_dir.name
    exe = a.exe.resolve()
    defer = not a.no_defer_start

    rig_cmd = ["uv", "run", "--script", str(RIG_SESSION), "--out-dir", str(res_dir), "--period-us", str(period),
               "--width-us", str(a.width_us), "--phase-us", str(a.phase_us), "--ping-rate", str(a.ping_rate),
               "--stop-file", str(res_dir / "rig_stop.flag"), "--line-state", a.rig_line_state,
               "--duration", str(a.restarts * (a.seconds + 120) + a.lock_timeout_s + 600)]
    if a.gap_us:
        rig_cmd += ["--gap-us", str(a.gap_us)]
    if defer:
        rig_cmd += ["--defer-start"]
    rig_cmd += ["--simulate"] if a.simulate_rig else ["--port", str(a.port)]

    def capture_cmd(raw_cap: Path) -> list[str]:
        if a.no_camera:
            return [sys.executable, "-c", f"import time; time.sleep({a.seconds})"]
        cmd = [str(exe), "--out", str(raw_cap), "--seconds", str(a.seconds), "--save-mjpeg"]
        for c in a.cam:
            cmd += ["--cam", c]
        if a.exposure_schedule:
            cmd += ["--exposure-schedule", a.exposure_schedule, "--exposure-dwell-s", str(a.exposure_dwell_s),
                    "--exposure-first-s", str(a.exposure_first_s)]
        inner = [sys.executable, str(Path(__file__).resolve()), "--_exec-timeout", str(a.seconds + 60), "--"] + cmd
        return ["uv", "run", "--script", str(CAMLOCK), "--timeout-s", str(a.lock_timeout_s), "--"] + inner

    if a.dry_run:
        print("# results:", res_dir)
        print("# raw MJPEG:", raw_dir)
        print("# 1. rig session (background):\n" + q(rig_cmd))
        for r in range(a.restarts):
            rc = raw_dir / f"capture_r{r + 1:02d}"
            print(f"# 2.{r + 1} capture {r + 1}/{a.restarts}" + (f" (strobe START {a.strobe_start_delay_s} s after first frames, STOP at end, via {res_dir}/rig_cmd_*.txt)" if defer else "") + ":")
            print(q(capture_cmd(rc)))
        print(f"# 3. stop: create {res_dir / 'rig_stop.flag'}; copy *.frames.jsonl, *.session.json, *.controls.jsonl to {res_dir}/capture_rNN/")
        print("# 4. analyse:\nuv run --script " + str(HERE / "analyze_anchor.py") + " " + str(res_dir))
        if not exe.exists() and not a.no_camera:
            print(f"# WARNING: {exe} does not exist; build it with timing\\build_mf.bat")
        return 0

    if not a.no_camera and not exe.exists():
        print(f"{exe} not found; build it with research/usb_cameras/timing/build_mf.bat", file=sys.stderr)
        return 2
    res_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    need = 2 * BYTES_PER_CAM_HOUR * max(1, len(a.cam)) * a.restarts * a.seconds / 3600
    free = shutil.disk_usage(raw_dir).free
    if free < need:
        print(f"not enough free disk under {raw_dir}: {free / 1e9:.1f} GB free, {need / 1e9:.1f} GB wanted (2x estimate)", file=sys.stderr)
        return 3
    (res_dir / "rig_stop.flag").unlink(missing_ok=True)
    rig_log = (res_dir / "rig_session.log").open("w")
    rig = subprocess.Popen(rig_cmd, stdin=subprocess.PIPE, stdout=rig_log, stderr=subprocess.STDOUT, text=True)
    t0 = time.monotonic()
    while not (res_dir / "rig_ready.json").exists():
        if rig.poll() is not None:
            print(f"rig_session exited early (rc {rig.returncode}); see {res_dir / 'rig_session.log'}", file=sys.stderr)
            return 4
        if time.monotonic() - t0 > 60:
            print("rig_session not ready after 60 s", file=sys.stderr)
            rig.kill()
            return 4
        time.sleep(0.2)
    print(f"[run_anchor_test] rig ready; results {res_dir}", flush=True)
    cmd_seq = [0]

    def rig_cmd_file(word: str):
        cmd_seq[0] += 1
        p = res_dir / f"rig_cmd_{cmd_seq[0]:04d}.tmp"
        p.write_text(word)
        p.rename(p.with_suffix(".txt"))

    captures = []
    try:
        for r in range(a.restarts):
            cap = f"capture_r{r + 1:02d}"
            raw_cap = raw_dir / cap
            raw_cap.mkdir(parents=True, exist_ok=True)
            cmd = capture_cmd(raw_cap)
            log = (res_dir / f"{cap}.log").open("w")
            t_start = time.monotonic()
            p = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
            started_strobe = False
            first_frames_t = None
            n_need = max(1, len(a.cam))
            while p.poll() is None:
                if defer and not started_strobe:
                    if a.no_camera:
                        first_frames_t = first_frames_t or time.monotonic()
                    elif first_frames_t is None and frames_started(raw_cap) >= n_need:
                        first_frames_t = time.monotonic()
                    if first_frames_t and time.monotonic() - first_frames_t >= a.strobe_start_delay_s:
                        rig_cmd_file("START")
                        started_strobe = True
                        print(f"[run_anchor_test] {cap}: strobe START", flush=True)
                time.sleep(0.05)
            if defer and started_strobe:
                rig_cmd_file("STOP")
            log.close()
            captures.append({"capture": cap, "rc": p.returncode, "timed_out": p.returncode == 124,
                             "elapsed_s": round(time.monotonic() - t_start, 3), "strobe_started": started_strobe or not defer,
                             "command": q(cmd), "log": f"{cap}.log"})
            print(f"[run_anchor_test] {cap}: rc {p.returncode}, {captures[-1]['elapsed_s']} s", flush=True)
            if defer and not started_strobe:
                print(f"[run_anchor_test] WARNING {cap}: the strobe never started (cameras did not all write frames)", flush=True)
            # copy the small per-camera files next to the rig logs
            dst = res_dir / cap
            dst.mkdir(exist_ok=True)
            for pat in ("*.frames.jsonl", "*.session.json", "*.controls.jsonl"):
                for f in raw_cap.glob(pat):
                    shutil.copy2(f, dst / f.name)
            time.sleep(1.0)
    finally:
        (res_dir / "rig_stop.flag").write_text("stop")
        try:
            rig.wait(30)
        except subprocess.TimeoutExpired:
            try:
                rig.stdin.write("stop\n")
                rig.stdin.flush()
                rig.wait(10)
            except Exception:  # noqa: BLE001
                rig.kill()
        rig_log.close()

    rig_ses = {}
    if (res_dir / "rig_session.json").exists():
        rig_ses = json.loads((res_dir / "rig_session.json").read_text())
    cams = []
    for cap in captures:
        for f in sorted((res_dir / cap["capture"]).glob("*.session.json")):
            s = json.loads(f.read_text())
            cap.setdefault("cameras", []).append({k: s.get(k) for k in ("camera_key", "frames", "errors", "wall_s", "exposure_schedule")})
            if not any(c["camera_key"] == s.get("camera_key") for c in cams):
                cams.append({k: s.get(k) for k in ("camera_key", "friendly_name", "symbolic_link", "requested", "controls")})
    fit = (rig_ses.get("measurements", {}).get("clock") or {}).get("fit", {})
    result = {
        "test": "rig_anchor", "platform": platform_name(), "hostname": socket.gethostname(), "utc_started": utc.isoformat(),
        "utc_finished": dt.datetime.now(dt.timezone.utc).isoformat(), "command": " ".join(sys.argv),
        "environment": {"os": platform.platform(), "os_version": platform.version(), "python": sys.version},
        "cameras": cams,
        "device": rig_ses.get("device", {}),
        "parameters": {"strobe": {"period_us": period, "width_us": a.width_us, "phase_us": a.phase_us, "gap_us": a.gap_us},
                       "fps_nominal": fps, "seconds": a.seconds, "restarts": a.restarts, "deferred_strobe_start": defer,
                       "strobe_start_delay_s": a.strobe_start_delay_s, "exposure_schedule": a.exposure_schedule,
                       "exposure_dwell_s": a.exposure_dwell_s, "exposure_first_s": a.exposure_first_s, "cam_specs": a.cam,
                       "exe": str(exe), "exe_sha256": None if a.no_camera else sha256(exe),
                       "simulated_rig": a.simulate_rig, "no_camera": a.no_camera},
        "measurements": {"captures": captures,
                         "rig": {k: rig_ses.get("measurements", {}).get(k) for k in ("lines", "line_counts", "ev_e", "boot_lines", "epochs",
                                                                                     "pings_answered", "stop_reason", "rx_src_counts")},
                         "clock_fit": {k: fit.get(k) for k in ("drift_ppm_esp_vs_host", "residual_std_us", "asymmetry_bound_us",
                                                               "offset_ns_at_ref", "offset_ns_at_ref_if_reply_seen_after_last_byte")}},
        "raw_dir": str(raw_dir),
        "notes": ["Analyse with timing/rig/analyze_anchor.py; real data is scored only after selftest_anchor.py passes (test plan V3).",
                  "Absolute K needs the ping fit and is estimated (both ping offsets); alpha and relative K do not need it."],
    }
    (res_dir / "result.json").write_text(json.dumps(result, indent=1))
    print(f"[run_anchor_test] wrote {res_dir / 'result.json'}")
    print("analyse: uv run --script " + str((HERE / "analyze_anchor.py").relative_to(REPO_ROOT)) + " " + str(res_dir))
    return 0 if all(c["rc"] == 0 for c in captures) else 1


if __name__ == "__main__":
    sys.exit(main())
