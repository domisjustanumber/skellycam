# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy"]
# ///
"""Re-run a subset of run_resumable_demo.py scenarios with PyAV 19.0.2 (child writers use this interpreter).
usage: uv run --script resumable_pyav19.py <out_json>"""
import json, sys
from pathlib import Path
D = "C:/Users/Dom/GitHub/freemocap/skellycam/research/skellycam_recording/recording_upgrade/scripts/crash_resilience"
sys.path.insert(0, D)
import common_cr as cc
import run_resumable_demo as rd
import av
cc.VENV_PY = Path(sys.executable)
base = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/crash_resilience/pyav19_check/resumable")
cc.rm(base); base.mkdir(parents=True)
out = {"env": {"pyav": av.__version__, "libavformat": ".".join(map(str, av.library_versions["libavformat"])),
               "child_interpreter": sys.executable}, "scenarios": []}
def scen(name, payload, steps, plseed=None):
    sd = base / name
    log = []
    for i, (n, kill_at) in enumerate(steps):
        log.append(rd.run_child(sd, payload, n, kill_at))
        if plseed is not None and i == 0:
            log.append({"powerloss": rd.powerloss(sd, plseed)})
    v = rd.verify(sd, payload)
    out["scenarios"].append({"name": name, "payload": payload, "steps": log, "verify": v})
    print(name, json.dumps({k: v[k] for k in v if k != "joined"}), flush=True)
    Path(sys.argv[1]).write_text(json.dumps(out, indent=1, default=str))
scen("kill_mid_segment", "mjpeg", [(600, 170), (90, None)])
scen("double_crash", "mjpeg", [(600, 100), (600, 75), (60, None)])
scen("powerloss_0", "mjpeg", [(600, 170), (60, None)], plseed=0)
scen("powerloss_1", "mjpeg", [(600, 170), (60, None)], plseed=1)
scen("ffv1_kill_mid", "ffv1", [(600, 170), (90, None)])
