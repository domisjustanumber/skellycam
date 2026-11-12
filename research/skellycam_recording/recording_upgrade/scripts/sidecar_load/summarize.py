"""Summarise T-S4 raw run JSONs: median and range per (electron, fps, arm).
Usage: python -I summarize.py <runs_dir> <summary.json> [runs.jsonl]"""
import glob, json, os, re, statistics, sys

runs_dir, out = sys.argv[1], sys.argv[2]
raw_out = sys.argv[3] if len(sys.argv) > 3 else None
log = {}
lp = os.path.join(runs_dir, "runlog.jsonl")
if os.path.exists(lp):
    for line in open(lp, encoding="utf-8-sig"):
        if line.strip():
            d = json.loads(line); log[d["tag"]] = d
groups, raws = {}, []
for p in sorted(glob.glob(os.path.join(runs_dir, "r*_*.json"))):
    if p.endswith(".cfg.json"): continue
    tag = os.path.basename(p)[:-5]
    m = re.match(r"r(\d+)_(e\d+)_fps(\d+)_(.+)", tag)
    d = json.load(open(p, encoding="utf-8"))
    for k in ("mem_base", "mem_after", "mem_end"):
        if k in d: d[k].pop("procs", None)
    d["tag"] = tag; d["runlog"] = log.get(tag)
    raws.append(d)
    if "exception" in d: print("EXC", tag, d["exception"][:200]); continue
    flat = {}
    L = d["load"]
    for k in ("fetch_ms", "parse_ms", "views_ms", "conv_ms", "ttff_ms", "load_ms", "parse_bigint_ms", "parse_u32view_ms",
              "conv_bigint_ms", "crc_verify_ms", "reads", "read_bytes", "frames"):
        if L.get(k) is not None: flat[k] = L[k]
    flat["renderer_private_mb_after"] = (d["mem_after"]["renderer"]["private_kb"] - d["mem_base"]["renderer"]["private_kb"]) / 1024
    flat["renderer_private_mb_peak"] = (d["mem_peak"]["renderer_private_kb"] - d["mem_base"]["renderer"]["private_kb"]) / 1024
    flat["all_private_mb_after"] = (d["mem_after"]["total_private_kb"] - d["mem_base"]["total_private_kb"]) / 1024
    flat["all_private_mb_peak"] = (d["mem_peak"]["total_private_kb"] - d["mem_base"]["total_private_kb"]) / 1024
    flat["js_heap_mb_after"] = (d["page_after"]["used_js_heap"] - d["page_base"]["used_js_heap"]) / 2**20
    for kind, o in d["lookups"].items():
        for k, v in o.items():
            if isinstance(v, (int, float)) and "checksum" not in k: flat[f"{kind}.{k}"] = v
            if "checksum" in k: flat[f"{kind}.{k}"] = v
    if d.get("runlog"): flat["cpu_load_pct_before"] = d["runlog"]["cpu_load_pct_before"]; flat["other_procs"] = d["runlog"]["other_procs"]
    key = (m.group(2), int(m.group(3)), m.group(4))
    groups.setdefault(key, []).append(flat)
summary = []
for (ev, fps, arm), rows in sorted(groups.items()):
    keys = sorted({k for r in rows for k in r})
    s = {"electron": ev, "fps": fps, "arm": arm, "n_runs": len(rows)}
    for k in keys:
        vals = [r[k] for r in rows if k in r]
        if "checksum" in k:
            s[k] = vals[0] if len(set(vals)) == 1 else "MISMATCH " + str(sorted(set(vals)))
            continue
        s[k] = {"median": round(statistics.median(vals), 3), "min": round(min(vals), 3), "max": round(max(vals), 3)}
    summary.append(s)
json.dump(summary, open(out, "w"), indent=1)
if raw_out:
    with open(raw_out, "w") as f:
        for d in raws: f.write(json.dumps(d) + "\n")
# compact console table
cols = ["ttff_ms", "load_ms", "fetch_ms", "parse_ms", "read_bytes", "renderer_private_mb_after", "renderer_private_mb_peak", "js_heap_mb_after"]
for s in summary:
    line = f"{s['electron']} {s['fps']:>3} {s['arm']:<7}"
    for c in cols:
        if c in s: line += f" {c}={s[c]['median']}[{s[c]['min']}-{s[c]['max']}]"
    for k in s:
        if k.endswith("us_per_draw") or k.startswith("lazy.seek_ms") or k.endswith("miss_draws"):
            line += f" {k}={s[k]['median']}"
    print(line)
