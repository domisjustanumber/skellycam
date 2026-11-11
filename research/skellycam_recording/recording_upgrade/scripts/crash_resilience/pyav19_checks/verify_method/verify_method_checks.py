# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy"]
# ///
"""VERIFY_method functional re-checks (PyAV 19.0.2, no timing):
A. segment muxer with vs without flush_packets (drained:150 kill, MJPEG)  -> does P19 show 'ignores fp'?
B. rt-mode kill (fed at 30 fps, TerminateProcess on the inner PID once 75 frames FED, i.e. mid-recording, not quiescent)
   for MJPEG mkv+fp, NVENC mkv_cl0+fp, AV1 mkv_cl0+fp.
usage: uv run --script verify_method_checks.py <out_json>"""
import json, os, signal, subprocess, sys
from pathlib import Path
SCR = Path("C:/Users/Dom/GitHub/freemocap/skellycam/research/skellycam_recording/recording_upgrade/scripts/crash_resilience")
sys.path.insert(0, str(SCR)); sys.path.insert(0, str(SCR / "pyav19_checks"))
import common_cr as cc
import pyav19_check as pc
import av
MEDIA = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/crash_resilience/verify_method")
MEDIA.mkdir(parents=True, exist_ok=True)
pc.MEDIA = MEDIA
res = {"env": {"pyav": av.__version__, "libavformat": ".".join(map(str, av.library_versions["libavformat"])), "python": sys.executable},
       "segment": [], "rt": []}
for c in ("seg_mkv", "seg_mkv+fp"):
    r = pc.kill_run("mjpeg", c); res["segment"].append(r); print(r, flush=True)

def rt_kill(p, c, kill_fed=75):
    out = cc.out_path(MEDIA, p, c, "rt75"); cc.rm(out)
    pr = subprocess.Popen([sys.executable, str(SCR / "writer_child.py"), p, c, str(out), "150", "rt"],
                          stdout=subprocess.PIPE, stdin=subprocess.PIPE, text=True)
    inner = None; last = None
    for line in pr.stdout:
        line = line.strip()
        if line.startswith("PID "): inner = int(line.split()[1])
        elif line.startswith("M "):
            last = line
            if int(line.split()[2]) >= kill_fed:
                os.kill(inner, signal.SIGTERM); break
        elif line.startswith(("OPENFAIL", "STREAMFAIL", "MUXFAIL")):
            last = line; break
    try: pr.kill()
    except Exception: pass
    pr.wait(timeout=30)
    r = {"payload": p, "container": c, "last_mux_line_seen": last, "bytes": out.stat().st_size if out.exists() else None}
    fp = cc.ffprobe_count(str(out)); r["ffprobe_frames"] = fp.get("frames")
    ref = [cc.sha(b) for b in cc.load_jpegs(cc.DEFAULT_SET, 150)] if p == "mjpeg" else None
    pr2 = cc.pyav_read(str(out), ref_shas=ref)
    r["pyav"] = {k: pr2.get(k) for k in ("frames", "packets", "byte_exact", "error", "seek")}
    return r
for p, c in (("mjpeg", "mkv+fp"), ("h264nv", "mkv_cl0+fp"), ("av1", "mkv_cl0+fp")):
    try: r = rt_kill(p, c)
    except Exception as e: r = {"payload": p, "container": c, "error": repr(e)}
    res["rt"].append(r); print(r, flush=True)
Path(sys.argv[1]).write_text(json.dumps(res, indent=1))
