# /// script
# requires-python = ">=3.10"
# dependencies = ["psutil>=5.9"]
# ///
"""Run ONE capture command with camera controls applied before and read back after (Windows).

  uv run --script research/usb_cameras/tools/camlock.py -- uv run --script research/usb_cameras/mjpeg/run_one.py \
      --cams c922,kiyo --run-dir <scratch run dir> [--no-set] -- <capture command ...>

Controls (exposure 2^-7 s manual, white balance 4500 K manual, UVC auto-exposure-priority 0) are set through
the Media Foundation tool (build/mf_mjpeg_capture.exe --controls-only). They persist in the device after
the tool exits, so they also govern DirectShow/OpenCV/WinRT captures. Result: <run-dir>/controls.json, which also
records every test camera's PnP DevNodeStatus before and after the capture (device-state evidence per cell).
"""
import argparse, json, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import mjpeg_common as mc

ap = argparse.ArgumentParser()
ap.add_argument("--cams", required=True)
ap.add_argument("--run-dir", required=True)
ap.add_argument("--no-set", action="store_true")
ap.add_argument("--exposure", type=int, default=-7)
ap.add_argument("--wb", type=int, default=4500)
ap.add_argument("--timeout-s", type=float, default=120, help="kill the capture (process tree) after this many seconds")
ap.add_argument("cmd", nargs=argparse.REMAINDER)
a = ap.parse_args()
cmd = a.cmd[1:] if a.cmd[:1] == ["--"] else a.cmd
cams = a.cams.split(",")
rd = Path(a.run_dir); rd.mkdir(parents=True, exist_ok=True)
dn_before = mc.devnode_status()
mcpu_before = mc.machine_cpu()
before = mc.mf_controls(cams, set_manual=not a.no_set, exposure=a.exposure, wb=a.wb)
t0 = time.time()
p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace")
timed_out = False
try:
    out_s, err_s = p.communicate(timeout=a.timeout_s)
except subprocess.TimeoutExpired:  # keep camera holds short: kill the whole tree (uv -> python / exe)
    timed_out = True
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
    else:
        p.kill()
    out_s, err_s = p.communicate()
    err_s += f"\n[run_one] capture killed after {a.timeout_s:.0f} s timeout"
rc = 124 if timed_out else p.returncode
log = "\n".join(l for l in (out_s + "\n" + err_s).splitlines() if "VCAMDS" not in l)  # drop NVIDIA Broadcast virtual-cam DLL chatter
print(log[-4000:])
(rd / "capture_log.txt").write_text(log)
mcpu_after = mc.machine_cpu()
after = mc.mf_controls(cams, set_manual=False)
dn_after = mc.devnode_status()
(rd / "controls.json").write_text(json.dumps({"requested": None if a.no_set else {"exposure_log2s": a.exposure, "white_balance_k": a.wb, "auto_exposure_priority": 0},
                                              "apply": before, "readback_after_capture": after, "capture_cmd": cmd, "capture_rc": rc, "capture_timed_out": timed_out, "capture_s": time.time() - t0,
                                              "devnode_status_before": dn_before, "devnode_status_after": dn_after,
                                              "machine_cpu_before": mcpu_before, "machine_cpu_after": mcpu_after}, indent=1))
sys.exit(rc)
