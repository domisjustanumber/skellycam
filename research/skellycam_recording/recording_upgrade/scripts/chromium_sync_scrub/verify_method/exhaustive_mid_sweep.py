"""Exhaustive frame-exactness sweep (functional, no timing): every frame k of every vfr720p and c720p30 video clip,
<video> 'mid' target and WebCodecs+index, in Electron 35 or 45. Closes the sampling gap in FINDINGS F10/F15
(seed-1 random seeks covered only 169/600 and 185/891 distinct frames and never frames 80-82).
Usage: <skellycam venv python> exhaustive_mid_sweep.py --electron 35|45 [--dry]"""
import argparse, importlib.util, json, sys
from pathlib import Path
RS = Path("C:/Users/Dom/GitHub/freemocap/skellycam/research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/run_suite.py")
spec = importlib.util.spec_from_file_location("run_suite", RS); rs = importlib.util.module_from_spec(spec); spec.loader.exec_module(rs)
ap = argparse.ArgumentParser(); ap.add_argument("--electron", required=True, choices=["35", "45"]); ap.add_argument("--dry", action="store_true"); a = ap.parse_args()
c = rs.clips()
out = rs.RESULTS / "functional" / f"e{a.electron}" / "exhaustive"
todo = []
for k, v in c.items():
    if v.get("kind") != "video" or v.get("content") not in ("vfr720p", "c720p30"): continue
    ks = ",".join(str(i) for i in range(int(v["frames"])))
    todo.append((f"{k.replace('/', '_')}_video_mid.json", [{"test": "seek", "clip": k, "path": "video", "mode": "mid", "ks": ks}]))
    todo.append((f"{k.replace('/', '_')}_webcodecs.json", [{"test": "seek", "clip": k, "path": "webcodecs", "ks": ks}]))
print(len(todo), "configs ->", out)
if a.dry: sys.exit(0)
for name, cfg in todo:
    d = rs.run_electron(a.electron, "batch", out / name, configs=cfg, timeout_s=3000)
    for r in d.get("result", []):
        s = r["result"]["summary"] if "summary" in r["result"] else r["result"]
        print(name, s.get("exact"), "/", s.get("n"), "unreadable", s.get("unreadable"), "off_by", s.get("off_by_hist"), flush=True)
