"""Re-run only the VLC checks (play + seek) on matrix outputs and update compat_raw.json in place.
Run from PowerShell: python -I rerun_vlc.py <scratch dir> <compat_raw.json> [names]"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_compat as K  # noqa: E402
import run_matrix as RM  # noqa: E402

sp, raw = sys.argv[1], sys.argv[2]
only = sys.argv[3].split(",") if len(sys.argv) > 3 else None
srcs = json.load(open(os.path.join(sp, "src", "sources.json")))
res = json.load(open(raw))
for name, src, start, count, ofps, kw in RM.VARIANTS:
    if (only and name not in only) or name not in res:
        continue
    s = srcs[src]
    case = dict(start_frame=start, src_fps=s["fps"], out_fps=ofps or s["fps"], flash_frames=s["flash_frames"],
                channels=1 if kw.get("channels") == "mono" else 2)
    p = os.path.join(sp, "out", name + ".mkv")
    res[name]["checks"]["vlc_seek_7s"] = K.vlc_run(p, case, start_time=7)
    print(name, res[name]["checks"]["vlc_seek_7s"].get("first_slot"), flush=True)
    json.dump(res, open(raw, "w"), indent=1)
