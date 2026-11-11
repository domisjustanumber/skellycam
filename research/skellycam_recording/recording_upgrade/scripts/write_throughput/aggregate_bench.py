"""Aggregate bench JSONs across repetitions: median and min-max per (set, writer, model, payload, cams, profile).
Prints Markdown tables (one per set folder) for BENCH.md. Added by the bench runner 2026-11-09.
Run (repo root): .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/write_throughput/aggregate_bench.py [sets...]
"""
from __future__ import annotations

import json
import statistics as stt
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wt_common as W  # noqa: E402


def mm(vals, nd):
    vals = [v for v in vals if isinstance(v, (int, float))]
    if not vals:
        return ""
    md = stt.median(vals)
    if len(vals) == 1:
        return f"{md:.{nd}f}"
    return f"{md:.{nd}f} ({min(vals):.{nd}f}-{max(vals):.{nd}f})"


def main():
    sets = sys.argv[1:] or sorted(p.name for p in W.BENCH_RESULTS.iterdir() if p.is_dir()
                                  and p.name not in ("sysinfo", "usability", "warmup"))
    for sname in sets:
        g = defaultdict(list)
        for j in sorted((W.BENCH_RESULTS / sname).glob("*.json")):
            s = json.loads(j.read_text())["summary"]
            g[(s["payload"], s["profile"], s["cams"], s["model"], s["writer"])].append(s)
        if not g:
            continue
        print(f"\n### {sname} (n = repetitions; values = median (min-max) when n > 1)\n")
        cols = ["writer", "model", "cams", "profile", "payload", "n", "written/produced", "dropped",
                "write ms p50", "write ms p99", "write ms p99.9", "write ms max", "grab late ms p99", "grab late ms max",
                "tick->written ms max", "CPU %/cam", "sys busy %", "MsMpEng CPU s", "MB/s"]
        print("| " + " | ".join(cols) + " |")
        print("|" + "---|" * len(cols))
        for k in sorted(g, key=lambda k: (k[0], k[1], k[2], k[3], k[4])):
            rs = g[k]
            pl, prof, cams, model, wr = k
            wp = f"{sum(r['written'] for r in rs)}/{sum(r['produced'] for r in rs)}"
            row = [wr, model, str(cams), prof, pl, str(len(rs)), wp, str(sum(r["dropped"] for r in rs)),
                   mm([r["write_ms_all"]["p50"] for r in rs], 3), mm([r["write_ms_all"]["p99"] for r in rs], 2),
                   mm([r["write_ms_all"]["p99.9"] for r in rs], 1), mm([r["write_ms_all"]["max"] for r in rs], 1),
                   mm([r["grab_lateness_ms_all"]["p99"] for r in rs], 2),
                   mm([r["grab_lateness_ms_all"]["max"] for r in rs], 1),
                   mm([r["tick_to_written_ms_all"]["max"] for r in rs], 1),
                   mm([r["our_cpu_pct_of_one_core_per_cam"] for r in rs], 1),
                   mm([r["system_busy_pct_all_cpus"] for r in rs], 1),
                   mm([r["msmpeng_cpu_s"] for r in rs], 1),
                   mm([r["throughput_MBps_over_duration"] for r in rs], 0)]
            print("| " + " | ".join(row) + " |")


if __name__ == "__main__":
    main()
