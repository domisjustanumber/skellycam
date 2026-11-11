"""(g) Cheap Chromium check: MJPEG passthrough files in Electron 35.7.5 (pinned by skellycam-ui) and 45.2.3 (newest stable).

Uses the c930e_720p_flash files written by mux_matrix.py (run that first) plus a VP9 WebM control made from the same
JPEGs (proves the harness can play something), and four single JPEGs: camera original, DHT-stripped, generic camera
(extra bytes before EOI), losslessly rotated 90 (4:4:0, jpegtran 3.2.1).

Run (repo root):
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/electron_check.py --jpegtran <scratchpad>/jpeg_passthrough/ljt321/bin/jpegtran.exe
Writes results/jpeg_passthrough/electron_check.json
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import jp_common as C  # noqa: E402

ELECTRONS = {
    "35.7.5": Path("C:/Users/Dom/GitHub/freemocap/skellycam/skellycam-ui/node_modules/electron/dist/electron.exe"),
    "45.2.3": Path("C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/shared/electron-latest/node_modules/electron/dist/electron.exe"),
}
VIDEO_NAMES = ["pyav_vfr_mkv.mkv", "pyav_vfr_mp4.mp4", "pyav_vfr_fmp4_1s.mp4", "pyav_vfr_mov.mov", "pyav_cfr_avi_tb_rate.avi",
               "pyav_vfr_nut.nut", "pyav_vfr_mjpeg_raw_mux.mjpeg"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jpegtran", required=True)
    a = ap.parse_args()
    src = C.MEDIA / "mux_matrix" / "c930e_720p_flash"
    d = C.MEDIA / "electron"
    d.mkdir(parents=True, exist_ok=True)
    videos = [str(src / n) for n in VIDEO_NAMES if (src / n).exists()]
    ctrl = d / "control_vp9.webm"
    if not ctrl.exists():
        frames = C.load_set("c930e_720p_flash", 60)
        subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-y", "-f", "image2pipe", "-framerate", "30", "-i", "pipe:0",
                        "-c:v", "libvpx-vp9", "-b:v", "2M", "-deadline", "realtime", "-cpu-used", "8", str(ctrl)],
                       input=b"".join(frames), capture_output=True, check=True)
    videos.append(str(ctrl))
    f0 = C.load_set("c930e_720p_flash", 1)[0]
    imgs = {"orig_c930e.jpg": f0, "nodht_c930e.jpg": C.strip_dht(f0), "generic_extra_bytes.jpg": C.load_set("generic_1080p", 1)[0]}
    for n, b in imgs.items():
        (d / n).write_bytes(b)
    rot = subprocess.run([a.jpegtran, "-rotate", "90", "-perfect", "-copy", "all"], input=f0, capture_output=True, check=True).stdout
    (d / "rot90_440_c930e.jpg").write_bytes(rot)
    images = [str(d / n) for n in list(imgs) + ["rot90_440_c930e.jpg"]]
    cfg = d / "config.json"
    cfg.write_text(json.dumps({"videos": videos, "images": images}))
    app = Path(__file__).parent / "electron_check" / "main.js"
    res = {"meta": {"date": time.strftime("%Y-%m-%dT%H:%M:%S")}, "runs": {}}
    for ver, exe in ELECTRONS.items():
        out = C.TEMP / f"electron_{ver}.json"
        if out.exists():
            out.unlink()
        env = {k: v for k, v in os.environ.items() if k != "ELECTRON_RUN_AS_NODE"}  # set by VS Code terminals; makes electron.exe act as node
        p = subprocess.run([str(exe), str(app), str(cfg), str(out)], capture_output=True, timeout=600, env=env)
        r = json.loads(out.read_text()) if out.exists() else {"error": "no output", "rc": p.returncode, "stderr": p.stderr.decode("utf8", "replace")[-500:]}
        r["versions"] = {k: r.get("versions", {}).get(k) for k in ("electron", "chrome", "v8")}
        res["runs"][ver] = r
        print(ver, json.dumps(r)[:1500], flush=True)
    C.write_json(C.RESULTS / "electron_check.json", res)
    print("wrote", C.RESULTS / "electron_check.json")


if __name__ == "__main__":
    main()
