# /// script
# requires-python = ">=3.10"
# ///
"""Print the VERIFY_method.md section-3 table (independent GT: ref=seq_periodic_env, gamma 2.2, E 7.8125) from
verify_method.json files. Usage: verify_method_table.py FILE [FILE ...] [--out json]"""
import json, sys
from pathlib import Path
args = sys.argv[1:]; out = None
if "--out" in args:
    i = args.index("--out"); out = args[i + 1]; del args[i:i + 2]
SRC = ["uvc_pts_mapped_direct", "uvc_pts_via_scr_lsq_envelope", "seq_periodic_env", "pts_nominal_clock", "pts_chunkmin_robust_causal",
       "pts_env_causal", "pts_env_first_half", "host_arrival", "os_timestamp"]
res = {}
for f in args:
    d = json.loads(Path(f).read_text()); res[f] = {}
    for c in d["cameras"]:
        bv = c.get("B_gt_variants", {})
        key = next((k for k in bv if k.startswith("ref=seq_periodic_env|gamma=2.2|E=")), None)
        if key is None:
            continue
        v = bv[key]; row = {"variant": key, "gt_n": v.get("gt_n")}
        for s in SRC:
            if s in v and isinstance(v[s], dict):
                row[s] = [round(v[s]["err_std_us"]), round(v[s]["err_mad_sigma_us"]), v[s]["n"]]
        res[f][c["camera_key"]] = row
        print(Path(f).parent.name[-40:], c["camera_key"][:17], "gt_n", row["gt_n"], " ".join(f"{s}={row[s][0]}/{row[s][1]}" for s in SRC if s in row))
if out:
    Path(out).write_text(json.dumps(res, indent=1))
